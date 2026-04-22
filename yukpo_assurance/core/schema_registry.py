"""
SchemaRegistry — Registre partagé de la connaissance du schéma SI.

Rôle :
  - Persiste la carte complète du schéma base de données (tables, colonnes, FK, index, types)
  - Fournit une API de lookup sémantique : "où sont les sinistres ?" → table + colonnes
  - Permet à tous les agents d'obtenir les noms de champs exacts avant lecture/écriture
  - Détecte les dérives de schéma entre deux introspections
  - Expose un mapping "concept métier" → "table.colonne" pour chaque SI connecté

Usage par les autres agents :
  from core.schema_registry import schema_registry
  mapping = schema_registry.lookup("sinistre", "montant")
  # → {"si": "orass", "table": "SIN_DOSSIERS", "colonne": "MNT_SINISTRE_TTC", "type": "decimal(15,2)"}
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("yukpo_assurance.schema_registry")

# Chemin de persistance du registre
_REGISTRY_PATH = Path(__file__).parent.parent / "data" / "schema_registry.json"
_REGISTRY_PATH.parent.mkdir(exist_ok=True)


class SchemaRegistry:
    """
    Registre central de schéma — singleton partagé par tous les agents.

    Structure interne :
    {
      "si_name": {
        "tables": {
          "TABLE_NAME": {
            "colonnes": [{"nom": "...", "type": "...", "nullable": ..., "pk": ...}],
            "cles_etrangeres": [...],
            "index": [...],
            "description_metier": "...",  # renseigné par l'AgentSchemaSI
            "concepts": ["sinistre", "dossier", ...]  # tags sémantiques
          }
        },
        "mappings_metier": {
          "concept.champ": "TABLE.COLONNE"  # ex: "sinistre.montant" → "SIN_DOSSIERS.MNT_SINISTRE"
        },
        "derniere_introspection": "ISO datetime",
        "version_schema": "hash MD5 du schéma courant"
      }
    }
    """

    def __init__(self):
        self._registre: dict[str, Any] = {}
        self._charge()

    def _charge(self):
        if _REGISTRY_PATH.exists():
            try:
                with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
                    self._registre = json.load(f)
            except Exception as e:
                logger.warning(f"[SchemaRegistry] Erreur lecture : {e}")
                self._registre = {}

    def _sauvegarder(self):
        try:
            with open(_REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(self._registre, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"[SchemaRegistry] Erreur sauvegarde : {e}")

    # ── API lecture ──────────────────────────────────────────────────────────────

    def lookup(self, concept: str, champ: str, si: str = "orass") -> dict | None:
        """
        Cherche le mapping technique pour un concept métier.
        Ex: lookup("sinistre", "montant") → {"table": "SIN_DOSSIERS", "colonne": "MNT_SINISTRE_TTC", ...}
        """
        cle = f"{concept}.{champ}".lower()
        si_data = self._registre.get(si, {})
        mappings = si_data.get("mappings_metier", {})
        if cle in mappings:
            loc = mappings[cle]  # ex: "SIN_DOSSIERS.MNT_SINISTRE_TTC"
            table, colonne = loc.split(".", 1) if "." in loc else (loc, "")
            table_data = si_data.get("tables", {}).get(table, {})
            col_data = next((c for c in table_data.get("colonnes", []) if c["nom"] == colonne), {})
            return {"si": si, "table": table, "colonne": colonne, **col_data}
        # Recherche par fuzzy (concept dans tags table)
        for tname, tdata in si_data.get("tables", {}).items():
            if concept.lower() in [c.lower() for c in tdata.get("concepts", [])]:
                for col in tdata.get("colonnes", []):
                    if champ.lower() in col["nom"].lower():
                        return {"si": si, "table": tname, "colonne": col["nom"], **col}
        return None

    def get_table(self, table_name: str, si: str = "orass") -> dict | None:
        return self._registre.get(si, {}).get("tables", {}).get(table_name.upper())

    def rechercher_tables_concept(self, concept: str, si: str = "orass") -> list[str]:
        """Retourne les tables associées à un concept métier."""
        tables = []
        for tname, tdata in self._registre.get(si, {}).get("tables", {}).items():
            if concept.lower() in " ".join(tdata.get("concepts", [])).lower():
                tables.append(tname)
            if concept.lower() in tdata.get("description_metier", "").lower():
                tables.append(tname)
        return list(set(tables))

    def lister_si(self) -> list[str]:
        return list(self._registre.keys())

    def get_schema_si(self, si: str) -> dict:
        return self._registre.get(si, {})

    def get_stats(self, si: str) -> dict:
        si_data = self._registre.get(si, {})
        nb_tables = len(si_data.get("tables", {}))
        nb_colonnes = sum(len(t.get("colonnes", [])) for t in si_data.get("tables", {}).values())
        nb_mappings = len(si_data.get("mappings_metier", {}))
        return {
            "si": si,
            "nb_tables": nb_tables,
            "nb_colonnes": nb_colonnes,
            "nb_mappings_metier": nb_mappings,
            "derniere_introspection": si_data.get("derniere_introspection", "jamais"),
            "version_schema": si_data.get("version_schema", "inconnue"),
        }

    # ── API écriture ─────────────────────────────────────────────────────────────

    def enregistrer_schema(self, si: str, tables: dict, mappings: dict | None = None):
        import hashlib
        schema_str = json.dumps(tables, sort_keys=True)
        version = hashlib.md5(schema_str.encode()).hexdigest()[:8]
        if si not in self._registre:
            self._registre[si] = {}
        self._registre[si]["tables"] = tables
        self._registre[si]["derniere_introspection"] = datetime.utcnow().isoformat()
        self._registre[si]["version_schema"] = version
        if mappings:
            self._registre[si]["mappings_metier"] = mappings
        self._sauvegarder()
        logger.info(f"[SchemaRegistry] Schéma {si} enregistré — {len(tables)} tables — version {version}")

    def ajouter_mapping(self, si: str, concept_champ: str, table_colonne: str):
        if si not in self._registre:
            self._registre[si] = {}
        if "mappings_metier" not in self._registre[si]:
            self._registre[si]["mappings_metier"] = {}
        self._registre[si]["mappings_metier"][concept_champ.lower()] = table_colonne
        self._sauvegarder()

    def ajouter_description_table(self, si: str, table: str, description: str, concepts: list[str]):
        if si not in self._registre or "tables" not in self._registre[si]:
            return
        if table.upper() in self._registre[si]["tables"]:
            self._registre[si]["tables"][table.upper()]["description_metier"] = description
            self._registre[si]["tables"][table.upper()]["concepts"] = concepts
            self._sauvegarder()

    def detecter_derive(self, si: str, nouveau_schema: dict) -> list[dict]:
        """Compare le schéma actuel avec le précédent et retourne les différences."""
        ancien = self._registre.get(si, {}).get("tables", {})
        derives = []
        # Tables ajoutées
        for t in nouveau_schema:
            if t not in ancien:
                derives.append({"type": "table_ajoutee", "table": t})
        # Tables supprimées
        for t in ancien:
            if t not in nouveau_schema:
                derives.append({"type": "table_supprimee", "table": t, "gravite": "critique"})
        # Colonnes modifiées
        for t in nouveau_schema:
            if t in ancien:
                cols_old = {c["nom"]: c for c in ancien[t].get("colonnes", [])}
                cols_new = {c["nom"]: c for c in nouveau_schema[t].get("colonnes", [])}
                for col in cols_old:
                    if col not in cols_new:
                        derives.append({"type": "colonne_supprimee", "table": t, "colonne": col, "gravite": "critique"})
                for col in cols_new:
                    if col not in cols_old:
                        derives.append({"type": "colonne_ajoutee", "table": t, "colonne": col})
                    elif cols_old[col].get("type") != cols_new[col].get("type"):
                        derives.append({"type": "type_modifie", "table": t, "colonne": col,
                                        "ancien_type": cols_old[col].get("type"),
                                        "nouveau_type": cols_new[col].get("type"), "gravite": "critique"})
        return derives

    def generer_requete_select(self, si: str, concept: str, filtres: dict | None = None, limite: int = 100) -> str:
        """Génère une requête SELECT validée pour un concept métier."""
        tables = self.rechercher_tables_concept(concept, si)
        if not tables:
            return f"-- Concept '{concept}' non trouvé dans le registre {si}"
        table = tables[0]
        tdata = self.get_table(table, si) or {}
        cols = ", ".join(c["nom"] for c in tdata.get("colonnes", [])[:20])  # max 20 colonnes
        where = ""
        if filtres:
            conditions = []
            for k, v in filtres.items():
                col_mapping = self.lookup(concept, k, si)
                col_name = col_mapping["colonne"] if col_mapping else k.upper()
                val = f"'{v}'" if isinstance(v, str) else str(v)
                conditions.append(f"{col_name} = {val}")
            where = f"\nWHERE {' AND '.join(conditions)}" if conditions else ""
        return f"SELECT TOP {limite} {cols}\nFROM {table}{where};"


# Singleton global
schema_registry = SchemaRegistry()
