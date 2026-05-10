"""
Générateur de glossaire auto pour documents DOCX.

Source partagée Pro (ReportWriter) + Sec (Bureau Rédacteur).
Scanne le contenu via Haiku 4.5 → retourne 8-15 termes/acronymes
techniques avec définitions courtes (1 phrase).

Niveau Big4 — chaque rapport finit par une page glossaire qui
explique OHADA, SYSCOHADA, BEAC, CIMA, FCFA, IFRS, etc. au
lecteur non-spécialiste.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger("yukpo_assurance.docx_glossaire")


async def generer_glossaire_haiku(contenu_complet: str, max_termes: int = 15) -> list[dict]:
    """
    Appelle Haiku 4.5 pour extraire 8 à `max_termes` acronymes/termes
    techniques d'un contenu textuel + leurs définitions courtes.

    Retourne [{"terme": "OHADA", "definition": "..."}] ou [] si échec.
    Cap contenu à 30k chars (Haiku context window).

    Coût : ~1200 tokens output × tarif Haiku = négligeable (~0.01 FCFA).
    """
    contenu = (contenu_complet or "")[:30000]
    if not contenu.strip():
        return []
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        prompt = (
            "Lis ce document et extrais les 8 à 15 acronymes et termes "
            "techniques métier les plus importants à expliquer pour un "
            "lecteur non-spécialiste.\n\n"
            f"DOCUMENT :\n\"\"\"{contenu}\"\"\"\n\n"
            "Réponds UNIQUEMENT en JSON strict :\n"
            '{"glossaire": [{"terme": "OHADA", "definition": "Organisation '
            "pour l'Harmonisation en Afrique du Droit des Affaires — "
            'traité régional adopté en 1993 par 17 États africains."}, ...]}\n\n'
            "RÈGLES : pas de termes triviaux (ex: 'rapport', 'analyse'). "
            "Privilégier acronymes (OHADA, SYSCOHADA, BEAC, CIMA, FCFA, IFRS), "
            "concepts juridiques/financiers/techniques propres au domaine, "
            "noms d'institutions citées. Définitions courtes (1 phrase max). "
            "Si moins de 8 termes pertinents identifiés, retourner moins."
        )
        rep = await ia_client.appeler(
            prompt=prompt,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
            mode=ModeIA.PRECISION,
            json_attendu=True,
            max_tokens_override=1200,
        )
        try:
            data = json.loads(rep.contenu or "{}")
        except json.JSONDecodeError:
            import re as _re
            m = _re.search(r'\{[\s\S]*\}', rep.contenu or "")
            data = json.loads(m.group()) if m else {}
        items = (data.get("glossaire") or [])[:max_termes]
        return [
            {"terme": (i.get("terme") or "").strip(),
             "definition": (i.get("definition") or "").strip()}
            for i in items
            if (i.get("terme") or "").strip() and (i.get("definition") or "").strip()
        ]
    except Exception as e:
        logger.debug(f"[docx_glossaire] Echec : {e}")
        return []


def ajouter_glossaire_au_doc(doc, glossaire_items: list[dict]) -> bool:
    """
    Ajoute une page glossaire au DOCX en argument (python-docx Document).
    Retourne True si ajouté (≥3 termes valides), False sinon.

    Style Big4 : page break + heading 'Glossaire' + intro italique grise +
    liste structurée terme/définition (terme en bleu Yukpo gras).
    """
    if len(glossaire_items) < 3:
        return False
    try:
        from docx.shared import Pt, RGBColor
        doc.add_page_break()
        h = doc.add_heading("Glossaire", level=1)
        if h.runs:
            h.runs[0].font.color.rgb = RGBColor(0x00, 0x47, 0xAB)
        p_intro = doc.add_paragraph()
        r_intro = p_intro.add_run(
            "Définitions des acronymes et termes techniques utilisés "
            "dans ce document."
        )
        r_intro.italic = True
        r_intro.font.size = Pt(10)
        r_intro.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        doc.add_paragraph()
        for item in glossaire_items:
            terme = item.get("terme", "").strip()
            defn = item.get("definition", "").strip()
            if not terme or not defn:
                continue
            p_g = doc.add_paragraph()
            r_t = p_g.add_run(f"{terme} : ")
            r_t.bold = True
            r_t.font.size = Pt(11)
            r_t.font.color.rgb = RGBColor(0x00, 0x47, 0xAB)
            r_d = p_g.add_run(defn)
            r_d.font.size = Pt(11)
            p_g.paragraph_format.space_after = Pt(6)
        return True
    except Exception as e:
        logger.debug(f"[docx_glossaire] Render échoué : {e}")
        return False
