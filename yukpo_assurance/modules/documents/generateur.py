"""
YukpoAssurance — Générateur de documents professionnels
Word, PDF, PowerPoint, Excel — haute qualité.
Inspiré de document_generation_service.rs + document_generator.py de yukpomnang2.
Adapté avec des templates spécialisés assurance CIMA.
"""
import asyncio
import base64
import io
import json
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from core.ia_client import ModeIA, ia_client
from config.settings import settings

logger = logging.getLogger("yukpo_assurance.documents")

# Chemin vers le générateur Python (inspiré du PYTHON_SCRIPT de yukpomnang2)
SCRIPT_PATH = Path(__file__).parent.parent.parent / "utils" / "scripts" / "document_generator.py"


class DocumentGenerateur:
    """
    Générateur de documents multi-format pour YukpoAssurance.

    Formats supportés :
    - DOCX (Word) : rapports, courriers, procédures, contrats
    - PDF : états financiers, rapports CRCA, documents officiels
    - PPTX (PowerPoint) : présentations CA, formations, revues de performance
    - XLSX (Excel) : tableaux de bord, états CIMA, analyses sinistres

    Workflow :
    1. L'IA génère un "outline" JSON (structure du document)
    2. Le script document_generator.py produit le fichier binaire
    3. Le fichier est encodé en base64 pour retour au client
    """

    async def generer(self, outline: dict, user_id: int = 0) -> Optional[dict]:
        """
        Génère un document depuis un outline JSON.
        Retourne un objet attachment avec filename, mime_type, data_b64.
        """
        doc_type = outline.get("document_type", "docx").lower()
        titre = outline.get("title", "document")

        ext, mime = self._meta_document(doc_type)
        filename = self._nom_fichier_propre(titre, ext)

        logger.info(f"[DocGen] Génération {doc_type} — {filename}")

        try:
            bytes_doc = await self._appeler_generateur(outline)
        except Exception as e:
            logger.error(f"[DocGen] Erreur génération: {e}")
            return None

        if not bytes_doc:
            return None

        data_b64 = base64.standard_b64encode(bytes_doc).decode()

        return {
            "id": f"yukpo-doc-{uuid.uuid4()}",
            "filename": filename,
            "mime_type": mime,
            "format": ext,
            "size_bytes": len(bytes_doc),
            "data_b64": data_b64,
            "title": titre,
        }

    async def generer_depuis_prompt_ia(
        self,
        demande: str,
        document_type: str = "docx",
        contexte: Optional[dict] = None,
        theme: str = "blue",
        nb_pages_cible: int = 0,
    ) -> Optional[dict]:
        """
        Génère un document depuis une demande en langage naturel.
        Supporte les documents illimités en pages via chunking automatique.
        nb_pages_cible=0 = détection automatique depuis la demande.
        """
        contexte_str = json.dumps(contexte, ensure_ascii=False) if contexte else "{}"

        templates = self._templates_assurance()
        template_desc = templates.get(document_type, "")

        # ── Étape 1 : Générer le plan complet ──────────────────────────────
        prompt_plan = f"""Tu es YukpoAssurance, expert en documents professionnels d'assurance CIMA.

Génère le PLAN COMPLET et STRUCTURÉ d'un document "{document_type}" pour :
"{demande}"

Contexte : {contexte_str}
{f'Modèle suggéré : {template_desc}' if template_desc else ''}

IMPORTANT : Génère un plan EXHAUSTIF et DÉTAILLÉ. Ne te limite pas en nombre de sections.
Chaque section doit avoir un contenu riche et professionnel.

Réponds en JSON UNIQUEMENT (sans markdown) selon ce schéma :
{{
  "document_type": "{document_type}",
  "title": "Titre complet du document",
  "subtitle": "Sous-titre ou date",
  "author": "YukpoAssurance",
  "theme": "{theme}",
  "nb_pages_estimees": 0,
  "sections_plan": [
    {{"id": 1, "titre": "...", "sous_sections": ["...", "..."], "contenu_cle": "..."}}
  ]
}}"""

        try:
            reponse_plan = await ia_client.appeler(
                prompt=prompt_plan,
                mode=ModeIA.REDACTION,
                max_tokens_override=8192,
            )
            plan_text = reponse_plan.contenu.strip()
            if plan_text.startswith("```"):
                import re
                plan_text = re.sub(r"^```(?:json)?\n?", "", plan_text)
                plan_text = re.sub(r"\n?```$", "", plan_text)
            plan = json.loads(plan_text)
        except Exception as e:
            logger.warning(f"[DocGen] Plan IA échoué: {e} — génération directe")
            return await self._generer_document_direct(demande, document_type, contexte_str, theme)

        sections_plan = plan.get("sections_plan", [])

        # ── Étape 2 : Générer le contenu par chunks ──────────────────────────
        # Pour éviter les limites de tokens, on génère le contenu section par section
        CHUNK_SIZE = 5  # Sections par appel IA
        if document_type == "pptx":
            slides = []
            slides.append({
                "title": plan.get("title", demande[:80]),
                "layout": "title",
                "content": plan.get("subtitle", ""),
            })
            for i in range(0, len(sections_plan), CHUNK_SIZE):
                chunk = sections_plan[i:i+CHUNK_SIZE]
                nouvelles_slides = await self._generer_slides_chunk(
                    chunk, demande, contexte_str, plan.get("title", "")
                )
                slides.extend(nouvelles_slides)

            outline = {
                "document_type": "pptx",
                "title": plan.get("title", demande[:80]),
                "subtitle": plan.get("subtitle", ""),
                "author": "YukpoAssurance",
                "theme": theme,
                "slides": slides,
            }
        elif document_type in ("docx", "pdf"):
            sections = []
            for i in range(0, len(sections_plan), CHUNK_SIZE):
                chunk = sections_plan[i:i+CHUNK_SIZE]
                nouvelles_sections = await self._generer_sections_chunk(
                    chunk, demande, contexte_str, plan.get("title", "")
                )
                sections.extend(nouvelles_sections)

            key = "sections" if document_type == "docx" else "pages"
            outline = {
                "document_type": document_type,
                "title": plan.get("title", demande[:80]),
                "subtitle": plan.get("subtitle", ""),
                "author": "YukpoAssurance",
                "theme": theme,
                key: sections,
            }
        elif document_type == "xlsx":
            return await self._generer_excel_ia(demande, contexte_str, theme)
        else:
            return await self._generer_document_direct(demande, document_type, contexte_str, theme)

        return await self.generer(outline)

    async def _generer_slides_chunk(
        self, sections_plan: list, demande: str, contexte: str, titre_doc: str
    ) -> list:
        """Génère les slides pour un chunk de sections."""
        sections_str = json.dumps(sections_plan, ensure_ascii=False, indent=2)
        prompt = f"""Document : "{titre_doc}"
Demande : "{demande}"
Contexte : {contexte[:500]}

Génère le contenu détaillé pour ces sections (JSON array de slides, sans markdown) :
{sections_str}

Pour chaque section, crée 1 à 3 slides selon la complexité. Format par slide :
{{"title": "...", "layout": "content|kpi|table|two_column", "content": "...", "bullets": ["..."], "notes": "..."}}

Retourne UNIQUEMENT le JSON array."""
        try:
            r = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION, max_tokens_override=4096)
            text = r.contenu.strip()
            if text.startswith("```"):
                import re
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            result = json.loads(text)
            return result if isinstance(result, list) else [result]
        except Exception as e:
            logger.warning(f"[DocGen] Chunk slides échoué: {e}")
            return [{"title": s.get("titre", "Section"), "layout": "content", "content": s.get("contenu_cle", "")} for s in sections_plan]

    async def _generer_sections_chunk(
        self, sections_plan: list, demande: str, contexte: str, titre_doc: str
    ) -> list:
        """Génère les sections DOCX/PDF pour un chunk."""
        sections_str = json.dumps(sections_plan, ensure_ascii=False, indent=2)
        prompt = f"""Document : "{titre_doc}"
Demande : "{demande}"
Contexte : {contexte[:500]}

Génère le contenu détaillé pour ces sections (JSON array de sections, sans markdown) :
{sections_str}

Format par section :
{{"heading": "...", "level": 1, "paragraphs": ["...paragraphe complet..."], "bullets": ["..."], "table": null}}

Contenu riche et professionnel. Retourne UNIQUEMENT le JSON array."""
        try:
            r = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION, max_tokens_override=4096)
            text = r.contenu.strip()
            if text.startswith("```"):
                import re
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            result = json.loads(text)
            return result if isinstance(result, list) else [result]
        except Exception as e:
            logger.warning(f"[DocGen] Chunk sections échoué: {e}")
            return [{"heading": s.get("titre", "Section"), "level": 1, "paragraphs": [s.get("contenu_cle", "")]} for s in sections_plan]

    async def _generer_document_direct(
        self, demande: str, document_type: str, contexte: str, theme: str
    ) -> Optional[dict]:
        """Génération directe (fallback) — un seul appel IA avec tokens max."""
        templates = self._templates_assurance()
        template_desc = templates.get(document_type, "")
        prompt = f"""Tu es YukpoAssurance, expert en documents professionnels d'assurance CIMA.

Génère la structure complète d'un document "{document_type}" pour :
"{demande}"

Contexte : {contexte}
{f'Modèle : {template_desc}' if template_desc else ''}

Retourne un JSON COMPLET et DÉTAILLÉ (sans markdown) avec le maximum de contenu possible.
N'abrège rien. Sois exhaustif et professionnel.
"""
        reponse = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.PRECISION,
            json_attendu=True,
            max_tokens_override=settings.IA_MAX_TOKENS_DOCUMENT,
        )
        try:
            outline = reponse.as_json()
            outline["document_type"] = document_type
            outline["theme"] = theme
            return await self.generer(outline)
        except Exception as e:
            logger.error(f"[DocGen/IA] Erreur outline direct: {e}")
            return None

    async def _generer_excel_ia(
        self, demande: str, contexte: str, theme: str
    ) -> Optional[dict]:
        """Génération Excel via IA."""
        templates = self._templates_assurance()
        template_desc = templates.get("xlsx", "")
        prompt = f"""Tu es YukpoAssurance, expert en documents professionnels d'assurance CIMA.

Génère la structure complète d'un tableau Excel pour :
"{demande}"

Contexte : {contexte}
{template_desc}

Retourne un JSON COMPLET (sans markdown) avec autant de feuilles et lignes que nécessaire.
"""
        reponse = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.PRECISION,
            json_attendu=True,
            max_tokens_override=settings.IA_MAX_TOKENS_DOCUMENT,
        )
        try:
            outline = reponse.as_json()
            outline["document_type"] = "xlsx"
            return await self.generer(outline)
        except Exception as e:
            logger.error(f"[DocGen/IA] Erreur outline Excel: {e}")
            return None

    # ──────────────────────────────────────────────────────────────
    # GÉNÉRATEURS SPÉCIALISÉS ASSURANCE
    # ──────────────────────────────────────────────────────────────

    async def rapport_sinistre(self, donnees_sinistre: dict) -> Optional[dict]:
        """Rapport d'expertise sinistre professionnel (DOCX)"""
        outline = {
            "document_type": "docx",
            "title": f"Rapport d'Expertise Sinistre — {donnees_sinistre.get('numero_sinistre', 'N/A')}",
            "subtitle": f"Police : {donnees_sinistre.get('numero_police', 'N/A')}",
            "author": donnees_sinistre.get("expert_assigne", "Expert YukpoAssurance"),
            "theme": "blue",
            "sections": [
                {
                    "heading": "1. Identification des parties",
                    "level": 1,
                    "paragraphs": [
                        f"Assuré : {donnees_sinistre.get('assure', 'N/A')}",
                        f"Numéro de police : {donnees_sinistre.get('numero_police', 'N/A')}",
                        f"Numéro de sinistre : {donnees_sinistre.get('numero_sinistre', 'N/A')}",
                        f"Date du sinistre : {donnees_sinistre.get('date_sinistre', 'N/A')}",
                        f"Lieu : {donnees_sinistre.get('lieu', 'N/A')}",
                    ],
                },
                {
                    "heading": "2. Circonstances du sinistre",
                    "level": 1,
                    "paragraphs": [donnees_sinistre.get("description", "À compléter")],
                },
                {
                    "heading": "3. Dommages constatés",
                    "level": 1,
                    "paragraphs": donnees_sinistre.get("degats", ["À renseigner après expertise"]),
                },
                {
                    "heading": "4. Évaluation et conclusion",
                    "level": 1,
                    "table": {
                        "headers": ["Poste", "Montant HT (FCFA)", "Montant TTC (FCFA)"],
                        "rows": donnees_sinistre.get("lignes_chiffrage", [
                            ["Réparations carrosserie", "0", "0"],
                            ["Pièces de rechange", "0", "0"],
                            ["Main d'œuvre", "0", "0"],
                            ["TOTAL", "0", "0"],
                        ]),
                    },
                },
                {
                    "heading": "5. Proposition d'indemnisation",
                    "level": 1,
                    "paragraphs": [
                        f"Montant total dommages : {donnees_sinistre.get('montant_expertise', 0):,} FCFA",
                        f"Franchise contractuelle : {donnees_sinistre.get('franchise', 0):,} FCFA",
                        f"Indemnité nette proposée : {donnees_sinistre.get('indemnite_nette', 0):,} FCFA",
                        "Base réglementaire : Art. 231 Code CIMA — délai de règlement 30 jours",
                    ],
                },
            ],
        }
        return await self.generer(outline)

    async def rapport_cima_annuel(self, donnees: dict, annee: int) -> Optional[dict]:
        """Rapport annuel de conformité CIMA (PDF)"""
        from modules.cima.code_cima_engine import cima_engine
        conformite = cima_engine.rapport_conformite_global(donnees)

        kpis = []
        if "marge_solvabilite" in conformite.get("ratios", {}):
            ms = conformite["ratios"]["marge_solvabilite"]
            kpis.append({
                "value": f"{ms.get('capitaux_propres_fcfa', 0) / 1_000_000:.0f}M",
                "label": "Capitaux propres (FCFA)",
                "trend": "✓ Conforme" if ms.get("conforme") else "⚠ Insuffisant",
            })

        outline = {
            "document_type": "pdf",
            "title": f"Rapport de Conformité CIMA — Exercice {annee}",
            "subtitle": "Préparé pour la CRCA",
            "author": "Direction Financière — YukpoAssurance",
            "theme": "blue",
            "pages": [
                {
                    "title": "Synthèse Exécutive",
                    "layout": "kpi",
                    "kpis": kpis or [
                        {"value": "20", "label": "États CIMA générés", "trend": "100%"},
                        {"value": str(len(conformite.get("alertes", []))), "label": "Alertes réglementaires", "trend": ""},
                    ],
                },
                {
                    "title": "Ratios Prudentiels",
                    "layout": "table",
                    "table": {
                        "headers": ["Ratio", "Valeur", "Seuil CIMA", "Statut"],
                        "rows": [
                            ["Marge de solvabilité", "Voir état C7", "300M FCFA min", conformite.get("statut_global", "N/A")],
                            ["Couverture provisions", "Voir état C5", "100%", "À vérifier"],
                            ["Taux réassurance", "Voir état C8", "< 50%", "À vérifier"],
                        ],
                    },
                },
                {
                    "title": "Alertes et Actions Requises",
                    "layout": "content",
                    "bullets": [a.get("message", "") for a in conformite.get("alertes", [])] or ["Aucune alerte critique détectée"],
                },
                {
                    "title": "Prochaines Échéances",
                    "layout": "content",
                    "bullets": [f"{e['echeance']} : {e['obligation']}" for e in cima_engine._prochaines_echeances()],
                },
            ],
        }
        return await self.generer(outline)

    async def presentation_ca(
        self, donnees: dict, titre: str = "Revue de Performance Trimestrielle"
    ) -> Optional[dict]:
        """Présentation PowerPoint pour le Conseil d'Administration"""
        outline = {
            "document_type": "pptx",
            "title": titre,
            "subtitle": f"Période : {donnees.get('periode', 'T1 2025')}",
            "author": "Direction Générale",
            "theme": "blue",
            "slides": [
                {
                    "title": "Performance Globale",
                    "layout": "kpi",
                    "kpis": [
                        {"value": f"{donnees.get('primes_nettes', 0) / 1_000_000:.0f}M FCFA", "label": "Primes nettes", "trend": "+12%"},
                        {"value": f"{donnees.get('sinistralite', 0):.0f}%", "label": "Ratio S/P", "trend": donnees.get("tendance_sp", "")},
                        {"value": f"{donnees.get('ratio_combine', 0):.0f}%", "label": "Ratio combiné", "trend": ""},
                        {"value": f"{donnees.get('polices_actives', 0):,}", "label": "Polices actives", "trend": ""},
                    ],
                },
                {
                    "title": "Production par Branche",
                    "layout": "table",
                    "table": {
                        "headers": ["Branche", "Primes (FCFA)", "Sinistres", "S/P"],
                        "rows": [
                            ["Auto", f"{donnees.get('primes_auto', 0):,}", f"{donnees.get('sin_auto', 0):,}", "50%"],
                            ["Vie", f"{donnees.get('primes_vie', 0):,}", f"{donnees.get('sin_vie', 0):,}", "20%"],
                            ["IRD", f"{donnees.get('primes_ird', 0):,}", f"{donnees.get('sin_ird', 0):,}", "40%"],
                            ["RC", f"{donnees.get('primes_rc', 0):,}", f"{donnees.get('sin_rc', 0):,}", "30%"],
                        ],
                    },
                },
                {
                    "title": "Points d'Attention",
                    "layout": "content",
                    "bullets": donnees.get("points_attention", [
                        "Suivi de la sinistralité auto — ratio S/P à surveiller",
                        "Renouvellement des contrats arrivant à échéance",
                        "Conformité CIMA : dépôt états C17/C18 dans les délais",
                    ]),
                },
                {
                    "title": "Plan d'Action",
                    "layout": "content",
                    "bullets": donnees.get("plan_action", [
                        "Renforcer la détection de fraude (objectif : -20% de fraudes)",
                        "Accélérer le traitement des sinistres auto (cible : < 5 jours)",
                        "Former les équipes aux outils IA YukpoAssurance",
                    ]),
                    "notes": "Présentation Conseil d'Administration — Confidentiel",
                },
            ],
        }
        return await self.generer(outline)

    async def tableau_de_bord_excel(self, donnees: dict) -> Optional[dict]:
        """Tableau de bord de gestion en Excel"""
        outline = {
            "document_type": "xlsx",
            "title": f"Tableau de Bord — {donnees.get('periode', 'Période N/A')}",
            "author": "YukpoAssurance",
            "sheets": [
                {
                    "name": "Performance Globale",
                    "headers": ["Indicateur", "Valeur", "Objectif", "Écart", "Statut"],
                    "rows": [
                        ["Primes nettes (FCFA)", f"{donnees.get('primes_nettes', 0):,}", "2.5Mds", "-", "✓"],
                        ["Ratio S/P Auto", f"{donnees.get('sp_auto', 0):.1f}%", "< 70%", "", ""],
                        ["Ratio S/P IRD", f"{donnees.get('sp_ird', 0):.1f}%", "< 65%", "", ""],
                        ["Ratio Combiné", f"{donnees.get('ratio_combine', 0):.1f}%", "< 100%", "", ""],
                        ["Marge Solvabilité", f"{donnees.get('marge_sol', 0):,} FCFA", "300M min", "", ""],
                        ["Polices actives", f"{donnees.get('polices_actives', 0):,}", "", "", ""],
                        ["Sinistres ouverts", f"{donnees.get('sinistres_ouverts', 0):,}", "", "", ""],
                        ["Délai moyen règlement", f"{donnees.get('delai_moyen', 0)} jours", "< 30j CIMA", "", ""],
                    ],
                },
                {
                    "name": "Sinistres par Branche",
                    "headers": ["Branche", "Déclarés", "Réglés", "En cours", "Montant réglé", "Montant en cours"],
                    "rows": donnees.get("sinistres_branches", [
                        ["Auto", "0", "0", "0", "0", "0"],
                        ["Vie", "0", "0", "0", "0", "0"],
                        ["IRD", "0", "0", "0", "0", "0"],
                    ]),
                },
                {
                    "name": "Suivi Provisions CIMA",
                    "headers": ["Provision", "Montant (FCFA)", "Méthode", "Art. CIMA", "Conforme"],
                    "rows": [
                        ["PPNA", f"{donnees.get('ppna', 0):,}", "Prorata temporis", "Art. 334-1", "Oui"],
                        ["PSAP", f"{donnees.get('psap', 0):,}", "Dossier par dossier", "Art. 334-2", "Oui"],
                        ["PM (Vie)", f"{donnees.get('pm', 0):,}", "Actuariel", "Art. 334-4", "Oui"],
                        ["Égalisation", f"{donnees.get('pe', 0):,}", "Taux réglementaire", "Art. 334-7", "Oui"],
                    ],
                },
            ],
        }
        return await self.generer(outline)

    # ──────────────────────────────────────────────────────────────
    # MOTEUR TECHNIQUE
    # ──────────────────────────────────────────────────────────────

    async def _appeler_generateur(self, outline: dict) -> Optional[bytes]:
        """
        Appelle le script document_generator.py via subprocess.
        Inspiré de run_python_generator dans document_generation_service.rs.
        """
        json_input = json.dumps(outline, ensure_ascii=False).encode("utf-8")

        for python_cmd in ["python3", "python"]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    python_cmd,
                    str(SCRIPT_PATH),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=json_input), timeout=300  # 5 min — supporte rapports CIMA 20 états
                )
                if proc.returncode == 0 and stdout:
                    logger.info(f"[DocGen] {len(stdout)} octets générés via {python_cmd}")
                    return stdout
                else:
                    logger.warning(f"[DocGen] {python_cmd} code={proc.returncode}: {stderr.decode()[:300]}")
            except asyncio.TimeoutError:
                logger.error("[DocGen] Timeout génération document")
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.error(f"[DocGen] Erreur subprocess: {e}")

        return None

    def _meta_document(self, doc_type: str) -> tuple[str, str]:
        mimes = {
            "docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "word": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "excel": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "pdf": ("pdf", "application/pdf"),
            "pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            "powerpoint": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        }
        return mimes.get(doc_type, ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))

    def _nom_fichier_propre(self, titre: str, ext: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in titre)
        safe = safe.strip().replace(" ", "_")[:60]
        return f"{safe}.{ext}"

    def _templates_assurance(self) -> dict:
        return {
            "docx": """Structure JSON attendue pour DOCX :
{
  "title": "...", "subtitle": "...", "author": "...", "theme": "blue",
  "sections": [
    {"heading": "Titre section", "level": 1, "paragraphs": ["texte"], "bullets": ["point"]}
  ]
}""",
            "pptx": """Structure JSON attendue pour PPTX :
{
  "title": "...", "subtitle": "...", "author": "...", "theme": "blue",
  "slides": [
    {"title": "Slide", "layout": "content|kpi|table|two_column", "content": "...", "bullets": [...],
     "kpis": [{"value": "95%", "label": "KPI", "trend": "+5%"}],
     "table": {"headers": [...], "rows": [...]}}
  ]
}""",
            "xlsx": """Structure JSON attendue pour XLSX :
{
  "title": "...", "author": "...",
  "sheets": [
    {"name": "Feuille 1", "headers": ["Col1", "Col2"], "rows": [["val1", "val2"]]}
  ]
}""",
            "pdf": """Structure JSON attendue pour PDF :
{
  "title": "...", "subtitle": "...", "author": "...", "theme": "blue",
  "pages": [
    {"title": "Page", "layout": "content|kpi|table|cover", "content": "...", "bullets": [...],
     "kpis": [{"value": "...", "label": "..."}],
     "table": {"headers": [...], "rows": [...]}}
  ]
}""",
        }


# Instance singleton
document_generateur = DocumentGenerateur()
