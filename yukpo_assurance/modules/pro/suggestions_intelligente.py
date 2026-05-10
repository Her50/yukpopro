"""
Suggestions intelligentes post-génération — Yukpo Pro & Secrétariat.

Après chaque génération réussie (rapport, slides, visuel, conversion, etc.),
appelle Claude Haiku 4.5 pour générer 3-5 suggestions de suites pertinentes
adaptées au contexte précis. Le frontend les affiche comme chips cliquables
sous le résultat dans le chat.

Pourquoi Haiku :
- Coût négligeable : ~300 tokens in + 200 out = ~$0.0006 = 0.4 FCFA réel
- Vitesse : ~500 ms (transparent pour l'user)
- Suffisant : la tâche est de la suggestion contextuelle, pas du raisonnement complexe

Coût absorbé dans le forfait de génération existant — pas de facturation
séparée. Ratio coût/valeur ridiculement faible.

Usage :
    from modules.pro.suggestions_intelligente import generer_suggestions_suite

    suggestions = await generer_suggestions_suite(
        type_doc="rapport_audit",
        brief_original="Audit comptable Brasserie du Wouri Q1 2026",
        meta_resultat={"nb_pages": 18, "langue": "fr", "format": "docx"},
        manques_detectes=["taille_print_non_precisee"],
    )
    # → [
    #     {"action": "convertir_slides", "label": "Convertir en présentation",
    #      "prompt_suggere": "Transforme ce rapport en slides exécutif 12 slides"},
    #     {"action": "traduire_en", "label": "Traduire en anglais",
    #      "prompt_suggere": "Traduis ce rapport en anglais"},
    #     ...
    #   ]
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.suggestions")


async def generer_suggestions_suite(
    *,
    type_doc: str,
    brief_original: str,
    meta_resultat: Optional[dict] = None,
    manques_detectes: Optional[list[str]] = None,
    nb_max: int = 5,
) -> list[dict]:
    """
    Génère 3-5 suggestions de suite contextuelles après une génération.

    Args:
        type_doc : type de document produit (ex: "rapport_audit",
            "slides_executive", "convention", "infographie_flyer_a5",
            "designerpro_livret_mariage_4p", "ocr", "audio", "traduction").
        brief_original : la demande initiale de l'utilisateur (langage libre).
        meta_resultat : métadonnées du résultat (nb_pages, langue, format,
            mode_visuel, palette, etc.).
        manques_detectes : éléments manquants ou par défaut détectés
            (ex: ["taille_print_non_precisee", "logo_non_fourni"]).
        nb_max : nombre maximum de suggestions à retourner (3-5).

    Returns:
        Liste de dicts {action, label, prompt_suggere} ; chaque suggestion
        propose à l'user UNE action concrète à enchaîner. En cas d'échec
        Haiku, retourne une liste vide (gracieux, pas bloquant).
    """
    nb_max = max(3, min(7, nb_max))
    meta_resultat = meta_resultat or {}
    manques_detectes = manques_detectes or []

    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire

        meta_str = ", ".join(f"{k}={v}" for k, v in meta_resultat.items() if v)
        manques_str = ", ".join(manques_detectes) if manques_detectes else "(aucun)"

        prompt = (
            f"Tu es assistant IA Yukpo. L'utilisateur vient de recevoir un "
            f"document généré par l'application. Tu dois lui suggérer "
            f"{nb_max} actions de suite PERTINENTES et CONCRÈTES qu'il "
            f"pourrait demander dans le chat pour améliorer / décliner / "
            f"approfondir / traduire / convertir / personnaliser ce résultat.\n\n"
            f"BRIEF INITIAL DE L'UTILISATEUR :\n"
            f"« {brief_original[:600]} »\n\n"
            f"DOCUMENT PRODUIT :\n"
            f"- type : {type_doc}\n"
            f"- méta : {meta_str or '(rien)'}\n"
            f"- éléments par défaut / manquants détectés : {manques_str}\n\n"
            f"RÈGLES CRITIQUES :\n"
            f"1. Suggestions ADAPTÉES au type de document. Exemples :\n"
            f"   - rapport → convertir en slides, traduire, ajouter un volet,\n"
            f"     synthétiser en note executive, exporter en PDF…\n"
            f"   - slides → générer notes orateur, version print A3, ajouter\n"
            f"     graphiques, traduire, extraire une slide en flyer…\n"
            f"   - visuel/infographie → préciser taille print (A3, A4, A5,\n"
            f"     bannière web, post Instagram), traduire le texte du visuel,\n"
            f"     décliner en plusieurs variantes, ajouter QR code, modifier\n"
            f"     la palette, version CMJN imprimerie…\n"
            f"   - convention/contrat → ajouter un avenant, générer la version\n"
            f"     anglaise, créer une lettre de notification, ajouter clause…\n"
            f"   - traduction → revoir le ton, traduire vers une 2e langue,\n"
            f"     adapter au registre formel/informel…\n"
            f"   - OCR/audio → reformuler, traduire, structurer en rapport,\n"
            f"     extraire les actions à mener…\n\n"
            f"2. Si des MANQUES sont détectés (taille non précisée, logo "
            f"manquant, langue par défaut, etc.), prioriser des suggestions "
            f"qui les CORRIGENT.\n\n"
            f"3. Chaque suggestion DOIT contenir un `prompt_suggere` que "
            f"l'utilisateur peut envoyer TEL QUEL dans le chat — phrases "
            f"complètes, en français, prêtes à l'emploi.\n\n"
            f"4. action : court identifiant snake_case (ex: 'convertir_slides',\n"
            f"   'traduire_en_anglais', 'preciser_taille_a3', 'ajouter_qr',\n"
            f"   'export_cmjn', 'decliner_variantes', 'creer_avenant').\n\n"
            f"5. label : court (3-7 mots), commence par un verbe d'action en\n"
            f"   français, sans emoji.\n\n"
            f"FORMAT JSON STRICT (liste de {nb_max} objets) :\n"
            f"[\n"
            f'  {{"action": "convertir_slides", "label": "Convertir en présentation",\n'
            f'   "prompt_suggere": "Transforme ce rapport en présentation exécutive 12 slides."}},\n'
            f'  ...\n'
            f"]\n\n"
            f"Retourne UNIQUEMENT le tableau JSON, sans markdown ni commentaire."
        )

        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.REDACTION,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
            json_attendu=True,
            max_tokens_override=1200,
            utiliser_cache=False,
        )
        contenu = (rep.contenu or "").strip()

        import json as _json
        import re as _re

        # Extraction tolérante : si Haiku retourne du markdown ou du texte,
        # on extrait la première liste JSON.
        try:
            data = _json.loads(contenu)
        except _json.JSONDecodeError:
            m = _re.search(r"\[.*\]", contenu, _re.DOTALL)
            data = _json.loads(m.group()) if m else []

        if not isinstance(data, list):
            return []

        # Normalisation + sanitization
        suggestions: list[dict] = []
        for item in data[:nb_max]:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "").strip()[:60]
            label = str(item.get("label") or "").strip()[:80]
            prompt_suggere = str(item.get("prompt_suggere") or "").strip()[:400]
            if action and label and prompt_suggere:
                suggestions.append({
                    "action": action,
                    "label": label,
                    "prompt_suggere": prompt_suggere,
                })
        return suggestions[:nb_max]

    except Exception as e:
        logger.debug(f"[Suggestions] Génération non bloquante échouée : {e}")
        return []


def detecter_manques_visuel(meta: dict, brief: str) -> list[str]:
    """Détecte les éléments par défaut / manquants typiques sur un visuel."""
    manques: list[str] = []
    brief_lower = (brief or "").lower()

    # Taille / format print non précisée
    formats_print = ("a3", "a4", "a5", "carte de visite", "flyer", "affiche",
                     "bannière", "instagram", "facebook", "whatsapp")
    if not any(f in brief_lower for f in formats_print):
        manques.append("taille_print_non_precisee")

    # Langue
    if not meta.get("langue") or meta.get("langue") == "fr":
        if not any(lg in brief_lower for lg in ("anglais", "english", "espagnol", "wolof")):
            manques.append("langue_par_defaut_francais")

    # CMJN print-ready
    if not meta.get("export_cmyk"):
        manques.append("non_export_cmjn")

    # Logo
    if "logo" not in brief_lower and not (meta.get("medias_utilises") or 0) > 0:
        manques.append("logo_non_fourni")

    return manques


def detecter_manques_doc(meta: dict, brief: str) -> list[str]:
    """Détecte les manques typiques sur un document texte (rapport, slides, etc.)."""
    manques: list[str] = []
    brief_lower = (brief or "").lower()

    # Pas de période précisée
    if not any(p in brief_lower for p in ("q1", "q2", "q3", "q4", "trimestre",
                                           "annuel", "mensuel", "semestre", "2024", "2025", "2026")):
        manques.append("periode_non_precisee")

    # Langue par défaut
    if (meta.get("langue") or "fr") == "fr" and "anglais" not in brief_lower:
        manques.append("langue_par_defaut_francais")

    # Pas d'entité nommée
    if not meta.get("nom_entreprise") and "entreprise" in brief_lower:
        manques.append("nom_entreprise_non_precisee")

    # Format de sortie
    if not meta.get("format") or meta.get("format") == "docx":
        if "présentation" in brief_lower or "powerpoint" in brief_lower:
            manques.append("format_default_docx")

    return manques
