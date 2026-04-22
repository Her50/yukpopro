"""
YukpoAssurance — Vérificateur de conformité CRCA
Simule une inspection du Contrôle Régional des Compagnies d'Assurance.
Prépare proactivement la compagnie aux contrôles CRCA.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orass_connector import orass
from modules.cima.code_cima_engine import cima_engine

logger = logging.getLogger("yukpo_assurance.cima.crca")


@dataclass
class PointInspection:
    article: str
    libelle: str
    valeur_actuelle: str
    valeur_seuil: str
    statut: str             # "CONFORME" | "À_RISQUE" | "NON_CONFORME"
    mesure_corrective: Optional[str] = None
    delai_jours: Optional[int] = None


@dataclass
class RapportInspectionCRCA:
    annee: int
    statut_global: str      # "CONFORME" | "À_RISQUE" | "NON_CONFORME"
    score_conformite: int   # 0-100
    points_inspectes: list[PointInspection]
    alertes_critiques: list[str]
    plan_action: str        # Commentaire IA avec actions prioritaires
    pret_inspection: bool


class VerificateurCRCA:
    """
    Vérifie la conformité CIMA comme un inspecteur du CRCA.
    Grille basée sur les points officiels de contrôle CRCA zone CIMA.
    """

    PROMPT_INSPECTION = """Tu es inspecteur senior du CRCA (Conférence Régionale des Contrôles d'Assurance).
Tu inspectes cette compagnie selon la grille officielle d'inspection CIMA.

DONNÉES DE LA COMPAGNIE pour l'exercice {annee} :
{donnees}

RAPPORT DE CONFORMITÉ TECHNIQUE CALCULÉ :
{rapport_technique}

En tant qu'inspecteur du CRCA, rédige :

1. UN PLAN D'ACTION PRIORITAIRE (5-8 points) pour les 30 prochains jours
   - Actions urgentes (seuils violés)
   - Actions préventives (ratios qui approchent des seuils)
   - Documents à préparer pour le dossier CRCA

2. UN COMMENTAIRE GLOBAL (3 phrases) résumant l'état de la compagnie :
   - Ce qui est conforme
   - Les risques principaux
   - La recommandation de l'inspecteur (contrôle surprise possible ? amende probable ?)

FORMAT : Sois direct, factuel, comme un vrai inspecteur. Cite les articles CIMA précis.
Ton rapport sera lu par la Direction Générale."""

    async def inspecter(self, annee: int = 2025) -> RapportInspectionCRCA:
        """Effectue l'inspection complète selon la grille CRCA"""
        donnees = await orass.export_donnees_cima(annee)
        rapport_tech = cima_engine.rapport_conformite_global(donnees)

        # Construction des points d'inspection
        points = self._construire_grille_inspection(donnees, rapport_tech)

        # Score global
        nb_conformes = sum(1 for p in points if p.statut == "CONFORME")
        score = int(nb_conformes / len(points) * 100) if points else 0

        # Alertes critiques
        alertes = [
            f"{p.article} : {p.libelle} — {p.valeur_actuelle} (seuil: {p.valeur_seuil})"
            for p in points if p.statut == "NON_CONFORME"
        ]

        # Plan d'action IA
        plan_action = await self._generer_plan_action(annee, donnees, rapport_tech)

        nb_non_conformes = sum(1 for p in points if p.statut == "NON_CONFORME")
        statut_global = (
            "NON_CONFORME" if nb_non_conformes > 0
            else "À_RISQUE" if score < 80
            else "CONFORME"
        )

        return RapportInspectionCRCA(
            annee=annee,
            statut_global=statut_global,
            score_conformite=score,
            points_inspectes=points,
            alertes_critiques=alertes,
            plan_action=plan_action,
            pret_inspection=score >= 85 and nb_non_conformes == 0,
        )

    def _construire_grille_inspection(self, donnees: dict, rapport: dict) -> list[PointInspection]:
        """Construit la grille de contrôle CRCA avec les valeurs réelles"""
        primes = donnees.get("primes_nettes", 1)
        sinistres = donnees.get("sinistres_payes", 0)
        cp = donnees.get("capitaux_propres", 0)
        prov = donnees.get("provisions_techniques", 0)
        actifs = donnees.get("actifs_admis_couverture", 0)
        cedees = donnees.get("primes_cedees_reassurance", 0)
        brutes = donnees.get("primes_emises_brutes", 1)
        frais = donnees.get("frais_gestion", 0)

        marge = max(primes * 0.23, sinistres * 0.26, 300_000_000)
        couverture = actifs / prov * 100 if prov else 0
        sp = sinistres / primes * 100 if primes else 0
        rc = (sinistres + frais) / primes * 100 if primes else 0
        taux_reassurance = cedees / brutes * 100 if brutes else 0

        def statut_ratio(valeur, seuil_min=None, seuil_max=None, inverse=False):
            if seuil_min is not None:
                ok = valeur >= seuil_min
            elif seuil_max is not None:
                ok = valeur <= seuil_max
            else:
                ok = True
            if inverse:
                ok = not ok
            if ok:
                return "CONFORME"
            # Zone grise (±10% du seuil)
            if seuil_min and valeur >= seuil_min * 0.9:
                return "À_RISQUE"
            if seuil_max and valeur <= seuil_max * 1.1:
                return "À_RISQUE"
            return "NON_CONFORME"

        points = [
            PointInspection(
                article="Art. 337-1",
                libelle="Marge de solvabilité non-vie",
                valeur_actuelle=f"{cp / 1_000_000:.0f}M FCFA",
                valeur_seuil=f"{marge / 1_000_000:.0f}M FCFA (min 300M)",
                statut=statut_ratio(cp, seuil_min=marge),
                mesure_corrective="Augmentation de capital ou réduction du volume d'affaires" if cp < marge else None,
                delai_jours=90,
            ),
            PointInspection(
                article="Art. 335",
                libelle="Couverture des provisions techniques",
                valeur_actuelle=f"{couverture:.1f}%",
                valeur_seuil="≥ 100%",
                statut=statut_ratio(couverture, seuil_min=100),
                mesure_corrective="Renforcement des actifs admis ou réduction des provisions" if couverture < 100 else None,
                delai_jours=30,
            ),
            PointInspection(
                article="Art. 308",
                libelle="Taux de réassurance branche auto",
                valeur_actuelle=f"{taux_reassurance:.1f}%",
                valeur_seuil="≤ 50%",
                statut=statut_ratio(taux_reassurance, seuil_max=50),
                mesure_corrective="Révision programme de réassurance" if taux_reassurance > 50 else None,
                delai_jours=180,
            ),
            PointInspection(
                article="Art. 231",
                libelle="Ratio Sinistres / Primes (S/P)",
                valeur_actuelle=f"{sp:.1f}%",
                valeur_seuil="≤ 70% (recommandé)",
                statut="CONFORME" if sp <= 70 else "À_RISQUE" if sp <= 80 else "NON_CONFORME",
                mesure_corrective="Révision tarifaire urgente et politique de souscription" if sp > 80 else None,
            ),
            PointInspection(
                article="Ratio combiné",
                libelle="Ratio combiné (S+Frais)/Primes",
                valeur_actuelle=f"{rc:.1f}%",
                valeur_seuil="< 100%",
                statut=statut_ratio(rc, seuil_max=100),
                mesure_corrective="Plan de redressement technique requis" if rc >= 100 else None,
                delai_jours=60,
            ),
            PointInspection(
                article="Art. 12",
                libelle="Délai accusé réception sinistres (10j)",
                valeur_actuelle="Vérifier dans ORASS",
                valeur_seuil="≤ 10 jours ouvrables",
                statut="À_RISQUE",  # À alimenter depuis ORASS réel
                mesure_corrective="Mise en place alerte automatique à J+8",
            ),
            PointInspection(
                article="États CIMA",
                libelle="Dépôt états C1-C20 dans les délais",
                valeur_actuelle="À vérifier",
                valeur_seuil="120 jours après clôture exercice",
                statut="À_RISQUE",
                mesure_corrective="Automatisation via module CIMA YukpoAssurance",
            ),
        ]
        return points

    async def _generer_plan_action(self, annee: int, donnees: dict, rapport: dict) -> str:
        """Génère un plan d'action IA pour préparer l'inspection CRCA"""
        try:
            prompt = self.PROMPT_INSPECTION.format(
                annee=annee,
                donnees=donnees,
                rapport_technique=rapport,
            )
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION)
            return reponse.contenu
        except Exception as e:
            logger.warning(f"[CRCA] Plan action IA échoué: {e}")
            return "Voir les alertes critiques ci-dessus pour les actions prioritaires."

    async def verifier(self, donnees: dict, annee: int) -> dict:
        """Vérifie la conformité à partir de données manuelles (mode test/simulation).
        Contrairement à inspecter(), ne requiert pas de connexion ORASS.
        """
        rapport_tech = cima_engine.rapport_conformite_global(donnees)
        points = self._construire_grille_inspection(donnees, rapport_tech)

        nb_conformes = sum(1 for p in points if p.statut == "CONFORME")
        score = int(nb_conformes / len(points) * 100) if points else 0
        nb_non_conformes = sum(1 for p in points if p.statut == "NON_CONFORME")

        alertes = [
            f"{p.article} : {p.libelle} — {p.valeur_actuelle} (seuil: {p.valeur_seuil})"
            for p in points if p.statut == "NON_CONFORME"
        ]

        statut_global = (
            "NON_CONFORME" if nb_non_conformes > 0
            else "À_RISQUE" if score < 80
            else "CONFORME"
        )

        rapport = RapportInspectionCRCA(
            annee=annee,
            statut_global=statut_global,
            score_conformite=score,
            points_inspectes=points,
            alertes_critiques=alertes,
            plan_action="Simulation — plan d'action IA désactivé en mode test.",
            pret_inspection=score >= 85 and nb_non_conformes == 0,
        )
        return self.rapport_to_dict(rapport)

    def rapport_to_dict(self, rapport: RapportInspectionCRCA) -> dict:
        return {
            "annee": rapport.annee,
            "statut_global": rapport.statut_global,
            "score_conformite": rapport.score_conformite,
            "pret_inspection_crca": rapport.pret_inspection,
            "alertes_critiques": rapport.alertes_critiques,
            "plan_action_prioritaire": rapport.plan_action,
            "grille_inspection": [
                {
                    "article": p.article,
                    "libelle": p.libelle,
                    "valeur_actuelle": p.valeur_actuelle,
                    "valeur_seuil": p.valeur_seuil,
                    "statut": p.statut,
                    "mesure_corrective": p.mesure_corrective,
                    "delai_jours": p.delai_jours,
                }
                for p in rapport.points_inspectes
            ],
        }


# Singleton
verificateur_crca = VerificateurCRCA()
