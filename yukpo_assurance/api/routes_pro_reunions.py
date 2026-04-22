"""
Routes Pro — Transcription & Rapport de Réunion
Accessible à tous les utilisateurs Pro (sans restriction de permission "reunions").
Prend en charge les réunions multilingues : Whisper transcrit, Claude traduit vers la
langue principale choisie par l'utilisateur.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import get_db, DocumentGenereDB

logger = logging.getLogger("yukpo_assurance.pro_reunions")

# Répertoire de sortie pour les rapports
_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated"

router = APIRouter()

# ── Codes langue ISO 639-1 → noms complets pour les prompts ──────────────────

WHISPER_MAX_BYTES = 24 * 1024 * 1024  # 24 MB — Whisper API hard limit is 25 MB

LANGUE_LABELS: dict[str, str] = {
    "fr": "français",
    "en": "anglais",
    "ar": "arabe",
    "sw": "swahili",
    "pt": "portugais",
    "es": "espagnol",
    "de": "allemand",
    "zh": "chinois",
    "wo": "wolof",
    "ha": "haoussa",
    "yo": "yoruba",
    "bm": "bambara",
    "ln": "lingala",
    "mg": "malgache",
}


# ── Transcription directe (sans reunion_id) ───────────────────────────────────

@router.post(
    "/transcrire-direct",
    summary="Transcription audio multilingue — Pro",
)
async def transcrire_direct_pro(
    audio: UploadFile = File(...),
    langue: str = Form("auto"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Transcrit un fichier audio via Whisper.

    - `langue="auto"` : Whisper détecte la langue automatiquement.
    - `langue="fr"` (ou autre code ISO 639-1) : si l'audio contient plusieurs langues,
      Whisper transcrit au mieux, puis Claude traduit / normalise le résultat dans
      la langue cible choisie par l'utilisateur.

    Formats acceptés : mp3, mp4, m4a, wav, webm, ogg, flac, opus.
    Fichiers volumineux (> 24 MB) découpés automatiquement en chunks.
    """
    contenu = await audio.read()
    taille_mb = len(contenu) / (1024 * 1024)
    if len(contenu) < 1000:
        raise HTTPException(400, "Fichier audio trop court ou vide")

    # Déterminer le MIME / extension — Whisper est sensible au nom du fichier
    mime_entrant = (audio.content_type or "").lower()
    nom_original = audio.filename or ""
    ext = _extraire_extension(nom_original, mime_entrant)
    mime_whisper = _mime_pour_whisper(ext)
    nom_fichier = f"enregistrement.{ext}"

    logger.info(
        f"[ProReunions] Transcription demandée | user={current_user.user_id} "
        f"ext={ext} taille={taille_mb:.2f}MB langue={langue}"
    )

    try:
        from config.settings import settings
        import openai

        if not settings.OPENAI_API_KEY:
            raise HTTPException(503, "Clé OpenAI non configurée — transcription indisponible")

        client_oai = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # ── Étape 1 : Whisper — chunked si > 24 MB, verbose_json sur le 1er chunk
        # pour la détection de langue. Auto-detect → meilleure précision multilingue.
        texte_brut, langue_detectee = await _transcrire_chunks_pro(
            contenu=contenu,
            nom_fichier=nom_fichier,
            mime_whisper=mime_whisper,
            client_oai=client_oai,
        )

        logger.info(
            f"[ProReunions] Whisper OK | langue_detectée={langue_detectee} "
            f"longueur={len(texte_brut)} chars"
        )

        if not texte_brut:
            raise HTTPException(422, "Aucun texte détecté dans l'audio — vérifiez le fichier")

        # ── Étape 2 : Traduction si la langue cible est explicite et différente
        # de la langue détectée (ou si l'audio est multilingue)
        texte_final = texte_brut
        traduit = False

        if langue and langue != "auto":
            langue_cible_label = LANGUE_LABELS.get(langue, langue)
            # On traduit si : langue détectée != langue cible, OU si on n'est pas sûr
            # (unknown ou plusieurs segments dans des langues différentes)
            besoin_traduction = (
                langue_detectee.lower() not in (langue, langue_cible_label)
                and langue_detectee != "unknown"
            ) or langue_detectee == "unknown"

            if not besoin_traduction:
                # Vérification rapide : si le texte contient des caractères d'une autre
                # écriture (arabe, chinois…) alors que la cible est latin, on traduit quand même
                besoin_traduction = _scripts_mixtes(texte_brut, langue)

            if besoin_traduction or langue != langue_detectee.lower():
                texte_final = await _traduire_transcription(
                    texte=texte_brut,
                    langue_source_detectee=langue_detectee,
                    langue_cible=langue,
                    langue_cible_label=langue_cible_label,
                    settings=settings,
                )
                traduit = True

        import asyncio as _asyncio
        from modules.pro.service_credits import debiter_forfait_fcfa as _debiter
        _asyncio.create_task(_debiter(int(current_user.user_id), max(1.0, taille_mb * 3.6), "whisper_transcription"))

        return {
            "transcription": texte_final,
            "transcription_originale": texte_brut if traduit else None,
            "langue_detectee": langue_detectee,
            "langue_cible": langue,
            "traduit": traduit,
            "longueur": len(texte_final),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[ProReunions] Erreur transcription: {exc}", exc_info=True)
        raise HTTPException(500, f"Erreur transcription : {str(exc)[:300]}")


# ── Génération de rapport de réunion ─────────────────────────────────────────

class RapportReunionRequest(BaseModel):
    transcription: str
    titre: Optional[str] = "Réunion"
    participants: Optional[str] = None   # liste libre, ex: "Jean, Marie, Ahmed"
    langue: str = "fr"
    contexte: Optional[str] = None       # secteur, entreprise, etc.


@router.post("/generer-rapport", summary="Génère un rapport structuré depuis la transcription")
async def generer_rapport_reunion(
    req: RapportReunionRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Génère un rapport de réunion complet à partir de la transcription :
    - Participants identifiés (si non fournis)
    - Synthèse des discussions
    - Décisions prises
    - Plan d'action (responsable, délai, priorité)
    - Points reportés
    - Prochaines étapes

    La réponse est en Markdown.
    """
    if len(req.transcription.strip()) < 50:
        raise HTTPException(400, "Transcription trop courte pour générer un rapport")

    logger.info(
        f"[ProReunions] Génération rapport : titre='{req.titre}' "
        f"participants='{req.participants}' langue={req.langue} "
        f"transcription_len={len(req.transcription)}"
    )

    langue_label = LANGUE_LABELS.get(req.langue, req.langue)

    # ── Transcription (chunked summarization si très longue) ──────────────────
    transcription_pour_prompt = await _preparer_transcription_pour_rapport(req.transcription, req.langue)

    # ── Participants (pour contexte seulement — rapport anonymisé) ────────────
    participants_list = req.participants.strip() if req.participants else ""
    participants_section = (
        f"- Participants présents : {participants_list}"
        if participants_list else "- Participants : [Identifiés depuis la transcription]"
    )

    # ── Prompt système strict — rapport anonymisé ──────────────────────────────
    prompt_systeme = (
        f"Tu es un expert en gestion de réunions professionnelles africaines (OHADA, CIMA, SYSCOHADA). "
        f"Tu génères des rapports précis, fidèles au contenu réel de la transcription. "
        f"RÈGLES ABSOLUES :\n"
        f"1. RAPPORT ANONYMISÉ : n'attribue JAMAIS une déclaration à une personne nommée. "
        f"Écris 'Il a été souligné que...', 'La réunion a conclu...', 'Il a été décidé...', "
        f"'Les participants ont convenu...', 'Il a été proposé...'. JAMAIS 'Jean a dit...'. "
        f"2. Utilise UNIQUEMENT les informations présentes dans la transcription. "
        f"3. Si une information n'est pas dans la transcription, écris 'Non mentionné'. "
        f"4. N'invente aucune date, chiffre ou décision absente de la transcription. "
        f"5. Le rapport est rédigé en {langue_label}.\n"
        f"6. Fais ressortir TOUS les points saillants et décisions concrètes."
    )

    contexte_str = f"\nCONTEXTE : {req.contexte}" if req.contexte else ""

    prompt = f"""Génère un rapport de réunion professionnel, structuré et anonymisé en **{langue_label}**.

RÉUNION : {req.titre}{contexte_str}
{participants_section}

---
TRANSCRIPTION COMPLÈTE :
{transcription_pour_prompt}
---

Génère le rapport en Markdown avec EXACTEMENT cette structure :

# Rapport de Réunion — {req.titre}

## Informations générales
- Date : [extraite du contexte ou "Non mentionnée"]
{participants_section}
- Durée estimée : [si déductible, sinon "Non précisée"]
- Contexte / Objet : {req.contexte or "Réunion professionnelle"}

## Synthèse exécutive
[3-5 phrases résumant les points clés de la réunion — anonymisé, orienté résultats]

## Points clés discutés
[Bullets thématiques — ce qui A ÉTÉ DIT/DÉBATTU, sans attribution à des personnes]
- [Thème 1] : [Synthèse anonymisée]
- [Thème 2] : [Synthèse anonymisée]
...

## Décisions actées
[Liste numérotée des décisions formelles — si aucune : "Aucune décision formelle actée lors de cette réunion"]
1. [Décision 1 anonymisée]
...

## Plan d'action
| Action | Responsable | Délai | Priorité |
|--------|-------------|-------|----------|
| [Action concrète] | [Rôle/Fonction ou nom si listé] | [Délai mentionné] | Haute/Moyenne/Basse |

## Points en suspens / Reportés
[Points non résolus mentionnés — si aucun : "Aucun point reporté"]

## Prochaines étapes
[Actions immédiates et suite donnée à la réunion]

---
*Rapport généré par Yukpo Pro — basé sur transcription audio*
"""

    try:
        from core.ia_client import ia_client, ModeIA
        from modules.pro.service_credits import verifier_et_debiter

        reponse_ia = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.REDACTION,
            systeme=prompt_systeme,
            max_tokens_override=4000,
            utiliser_cache=False,
        )
        rapport = reponse_ia.contenu

        # Débit crédits (fire-and-forget — ne bloque pas la réponse)
        import asyncio as _asyncio
        _asyncio.create_task(verifier_et_debiter(
            user_id=current_user.user_id,
            modele=reponse_ia.modele_utilise or "claude-sonnet-4-6",
            tokens_input=reponse_ia.tokens_input or 2000,
            tokens_output=reponse_ia.tokens_output or 1000,
            module="rapport_reunion",
        ))

        # Générer DOCX depuis le rapport Markdown
        nom_fichier = None
        sauvegarde = False
        try:
            reports_dir = _DATA_DIR / "pro_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            titre_safe = (req.titre or "reunion").replace(" ", "_").replace("/", "-")[:40]
            nom_fichier = f"rapport_reunion_{titre_safe}_{ts}.docx"
            chemin_out = reports_dir / nom_fichier

            docx_bytes = _construire_rapport_docx(rapport, req.titre or "Réunion", req.participants)
            chemin_out.write_bytes(docx_bytes)
            logger.info(f"[ProReunions] DOCX rapport généré : {chemin_out}")

            # Sauvegarder dans Mes Documents
            doc = DocumentGenereDB(
                user_id=current_user.user_id,
                titre=f"Rapport : {req.titre or 'Réunion'}",
                type_doc="rapport_reunion",
                fichier=nom_fichier,
                contenu_source=req.transcription[:1000],
                contenu_genere=rapport[:5000],
                session_id=None,
                meta={"langue": req.langue, "participants": req.participants or "", "source": "reunion"},
                cree_le=datetime.utcnow(),
                modifie_le=datetime.utcnow(),
            )
            db.add(doc)
            await db.commit()
            sauvegarde = True
            logger.info(f"[ProReunions] Rapport sauvegardé dans Mes Documents")
        except Exception as e_doc:
            logger.warning(f"[ProReunions] DOCX/sauvegarde échoué : {e_doc}")

        return {
            "rapport": rapport,
            "titre": req.titre,
            "langue": req.langue,
            "longueur": len(rapport),
            "fichier": nom_fichier,
            "sauvegarde_mes_documents": sauvegarde,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[ProReunions] Erreur rapport: {exc}", exc_info=True)
        raise HTTPException(500, f"Erreur génération rapport : {str(exc)[:300]}")


# ── Régénération DOCX depuis Markdown édité ──────────────────────────────────

class RapportDocxDepuisMarkdownRequest(BaseModel):
    rapport_markdown: str = Field(..., min_length=10, max_length=100_000)
    titre:            str = Field("Réunion", max_length=300)
    participants:     Optional[str] = Field(None, max_length=500)
    date:             Optional[str] = Field(None, max_length=50)


@router.post("/rapport-docx", summary="Génère un DOCX depuis un rapport Markdown édité")
async def rapport_docx_depuis_markdown(req: RapportDocxDepuisMarkdownRequest):
    """Convertit un rapport Markdown (éventuellement édité par l'utilisateur) en DOCX haute qualité."""
    try:
        docx_bytes = _construire_rapport_docx(req.rapport_markdown, req.titre, req.participants)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        titre_safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (req.titre or "reunion"))[:40]
        nom_fichier = f"rapport_reunion_{titre_safe}_{ts}.docx"
        rapports_dir = _DATA_DIR / "pro_reports"
        rapports_dir.mkdir(parents=True, exist_ok=True)
        chemin_out = rapports_dir / nom_fichier
        chemin_out.write_bytes(docx_bytes)
        return {
            "fichier": nom_fichier,
            "longueur": len(req.rapport_markdown),
        }
    except Exception as exc:
        logger.error(f"[ProReunions] Erreur rapport-docx: {exc}", exc_info=True)
        raise HTTPException(500, f"Erreur génération DOCX : {str(exc)[:200]}")


# ── Helpers privés ────────────────────────────────────────────────────────────

def _inline_runs(paragraph, texte: str, taille=None, couleur=None):
    """Ajoute du texte avec **gras** et *italique* inline dans un paragraphe."""
    import re
    from docx.shared import Pt, RGBColor as _RGB
    parties = re.split(r'(\*\*(?:[^*]|\*(?!\*))+\*\*|\*[^*]+\*)', texte)
    for partie in parties:
        if partie.startswith('**') and partie.endswith('**') and len(partie) > 4:
            run = paragraph.add_run(partie[2:-2])
            run.bold = True
        elif partie.startswith('*') and partie.endswith('*') and len(partie) > 2:
            run = paragraph.add_run(partie[1:-1])
            run.italic = True
        elif partie:
            run = paragraph.add_run(partie)
        else:
            continue
        if taille:
            run.font.size = Pt(taille)
        if couleur:
            run.font.color.rgb = _RGB(*couleur)


def _construire_rapport_docx(rapport_md: str, titre: str, participants: Optional[str] = None) -> bytes:
    """Construit un DOCX haute qualité depuis le rapport Markdown de réunion."""
    import re
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    BLEU  = (0x00, 0x47, 0xAB)
    BLEU2 = (0x1C, 0x4E, 0x80)
    GRIS  = (0x55, 0x65, 0x81)
    BLANC = (0xFF, 0xFF, 0xFF)
    NUIT  = (0x1A, 0x1A, 0x2E)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width   = Cm(21)
    sec.page_height  = Cm(29.7)
    sec.left_margin  = Cm(2.5)
    sec.right_margin = Cm(2.5)
    sec.top_margin   = Cm(2.5)
    sec.bottom_margin = Cm(2.5)

    # ── Page de garde ─────────────────────────────────────────────────────────
    # Bande de couleur simulée via paragraph border
    p_band = doc.add_paragraph()
    p_band.paragraph_format.space_before = Pt(0)
    p_band.paragraph_format.space_after  = Pt(0)
    run_band = p_band.add_run("  ")
    run_band.font.size = Pt(28)
    # Fond via shading XML
    pPr = p_band._p.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), '0047AB')
    pPr.append(shd)

    doc.add_paragraph()

    # Titre principal
    p_titre = doc.add_paragraph()
    p_titre.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_titre.paragraph_format.space_before = Pt(6)
    p_titre.paragraph_format.space_after  = Pt(4)
    run_t = p_titre.add_run(titre.upper())
    run_t.bold = True
    run_t.font.size = Pt(20)
    run_t.font.color.rgb = RGBColor(*NUIT)

    # Sous-titre / type
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_sub.paragraph_format.space_after = Pt(2)
    run_sub = p_sub.add_run("RAPPORT DE RÉUNION")
    run_sub.font.size = Pt(12)
    run_sub.font.color.rgb = RGBColor(*BLEU)
    run_sub.bold = True

    # Date + participants
    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_after = Pt(4)
    run_meta = p_meta.add_run(f"Généré le {datetime.now().strftime('%d %B %Y à %H:%M')}")
    run_meta.font.size = Pt(10)
    run_meta.font.color.rgb = RGBColor(*GRIS)
    run_meta.italic = True

    if participants:
        p_part = doc.add_paragraph()
        p_part.paragraph_format.space_after = Pt(4)
        run_p = p_part.add_run(f"Participants : {participants}")
        run_p.font.size = Pt(10)
        run_p.font.color.rgb = RGBColor(*GRIS)

    # Trait séparateur
    p_sep = doc.add_paragraph()
    p_sep.paragraph_format.space_before = Pt(6)
    p_sep.paragraph_format.space_after  = Pt(12)
    pPr2 = p_sep._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '12')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), '0047AB')
    pBdr.append(bottom)
    pPr2.append(pBdr)

    doc.add_page_break()

    # ── Corps du rapport — ligne par ligne ────────────────────────────────────
    lignes = rapport_md.split("\n")
    i = 0
    while i < len(lignes):
        ligne = lignes[i]
        s = ligne.strip()

        if not s or s.startswith("---"):
            i += 1
            continue

        # Titres
        if s.startswith("#### "):
            h = doc.add_heading(s[5:].strip(), level=4)
            h.paragraph_format.space_before = Pt(8)
            if h.runs: h.runs[0].font.size = Pt(11)
            i += 1; continue

        if s.startswith("### "):
            h = doc.add_heading(s[4:].strip(), level=3)
            h.paragraph_format.space_before = Pt(10)
            if h.runs:
                h.runs[0].font.size = Pt(12)
                h.runs[0].font.color.rgb = RGBColor(*BLEU2)
            i += 1; continue

        if s.startswith("## "):
            h = doc.add_heading(s[3:].strip(), level=2)
            h.paragraph_format.space_before = Pt(14)
            h.paragraph_format.space_after  = Pt(6)
            if h.runs:
                h.runs[0].font.size = Pt(14)
                h.runs[0].font.color.rgb = RGBColor(*BLEU)
            # Trait sous le titre de section
            pPr_h = h._p.get_or_add_pPr()
            pBdr_h = OxmlElement('w:pBdr')
            bot_h = OxmlElement('w:bottom')
            bot_h.set(qn('w:val'), 'single')
            bot_h.set(qn('w:sz'), '4')
            bot_h.set(qn('w:space'), '1')
            bot_h.set(qn('w:color'), '0047AB')
            pBdr_h.append(bot_h)
            pPr_h.append(pBdr_h)
            i += 1; continue

        if s.startswith("# "):
            h = doc.add_heading(s[2:].strip(), level=1)
            h.paragraph_format.space_before = Pt(16)
            if h.runs:
                h.runs[0].font.size = Pt(16)
                h.runs[0].font.color.rgb = RGBColor(*BLEU)
            i += 1; continue

        # Tableau Markdown
        if '|' in s:
            tbl_lines = []
            while i < len(lignes) and '|' in lignes[i]:
                tbl_lines.append(lignes[i])
                i += 1
            rows = [l for l in tbl_lines if not re.match(r'^\|[\s\-:|\s]+\|$', l.strip())]
            if len(rows) >= 2:
                cols = [c.strip() for c in rows[0].split('|') if c.strip()]
                if cols:
                    tbl = doc.add_table(rows=len(rows), cols=len(cols))
                    tbl.style = 'Table Grid'
                    for ri, row_line in enumerate(rows):
                        cells = [c.strip().strip('*') for c in row_line.split('|') if c.strip()]
                        for ci in range(len(cols)):
                            val = cells[ci] if ci < len(cells) else ""
                            cell = tbl.cell(ri, ci)
                            cell.text = ""
                            p_cell = cell.paragraphs[0]
                            _inline_runs(p_cell, val, taille=10)
                            if ri == 0 and p_cell.runs:
                                for r in p_cell.runs:
                                    r.bold = True
                                    r.font.color.rgb = RGBColor(*BLANC)
                                p_cell.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            if ri == 0:
                                tc = cell._tc
                                tcPr = tc.get_or_add_tcPr()
                                shd_c = OxmlElement('w:shd')
                                shd_c.set(qn('w:val'), 'clear')
                                shd_c.set(qn('w:color'), 'auto')
                                shd_c.set(qn('w:fill'), '0047AB')
                                tcPr.append(shd_c)
                    doc.add_paragraph()
            continue

        # Sous-bullet (indentation 2+)
        if re.match(r'^\s{2,}[-•*]\s', ligne):
            txt = re.sub(r'^\s+[-•*]\s+', '', ligne).strip()
            p_obj = doc.add_paragraph()
            p_obj.paragraph_format.left_indent       = Cm(1.4)
            p_obj.paragraph_format.first_line_indent = Cm(-0.5)
            p_obj.paragraph_format.space_before      = Pt(1)
            p_obj.paragraph_format.space_after       = Pt(1)
            marker = p_obj.add_run("–  ")
            marker.font.color.rgb = RGBColor(0x00, 0x47, 0xAB)
            marker.font.size = Pt(9)
            marker.bold = False
            _inline_runs(p_obj, txt, taille=10, couleur=RGBColor(0x44, 0x44, 0x44))
            i += 1; continue

        # Bullet
        if re.match(r'^[-•*►▶→]\s', s):
            txt = re.sub(r'^[-•*►▶→]\s+', '', s).strip()
            p_obj = doc.add_paragraph()
            p_obj.paragraph_format.left_indent       = Cm(0.7)
            p_obj.paragraph_format.first_line_indent = Cm(-0.7)
            p_obj.paragraph_format.space_before      = Pt(3)
            p_obj.paragraph_format.space_after       = Pt(1)
            marker = p_obj.add_run("▪  ")
            marker.font.color.rgb = RGBColor(0x00, 0x47, 0xAB)
            marker.font.size = Pt(11)
            marker.bold = True
            _inline_runs(p_obj, txt, taille=11)
            i += 1; continue

        # Numéroté
        if re.match(r'^\d+[.)]\s', s):
            num_m = re.match(r'^(\d+)[.)]\s+', s)
            num   = num_m.group(1) if num_m else "1"
            txt   = re.sub(r'^\d+[.)]\s+', '', s).strip()
            p_obj = doc.add_paragraph()
            p_obj.paragraph_format.left_indent       = Cm(0.7)
            p_obj.paragraph_format.first_line_indent = Cm(-0.7)
            p_obj.paragraph_format.space_before      = Pt(3)
            p_obj.paragraph_format.space_after       = Pt(1)
            marker = p_obj.add_run(f"{num}.  ")
            marker.font.color.rgb = RGBColor(0x00, 0x47, 0xAB)
            marker.font.size = Pt(11)
            marker.bold = True
            _inline_runs(p_obj, txt, taille=11)
            i += 1; continue

        # Ligne gras seule (sous-titre)
        m = re.match(r'^\*\*(.+)\*\*$', s)
        if m:
            p_obj = doc.add_paragraph()
            p_obj.paragraph_format.space_before = Pt(8)
            p_obj.paragraph_format.space_after  = Pt(4)
            run = p_obj.add_run(m.group(1))
            run.bold = True
            run.font.size = Pt(12)
            run.font.color.rgb = RGBColor(*NUIT)
            i += 1; continue

        # Citation / note (> text)
        if s.startswith("> "):
            p_obj = doc.add_paragraph()
            p_obj.paragraph_format.left_indent = Cm(1)
            p_obj.paragraph_format.space_before = Pt(4)
            p_obj.paragraph_format.space_after  = Pt(4)
            # Trait gauche via border
            pPr_q = p_obj._p.get_or_add_pPr()
            pBdr_q = OxmlElement('w:pBdr')
            left_q = OxmlElement('w:left')
            left_q.set(qn('w:val'), 'single')
            left_q.set(qn('w:sz'), '12')
            left_q.set(qn('w:space'), '8')
            left_q.set(qn('w:color'), '0047AB')
            pBdr_q.append(left_q)
            pPr_q.append(pBdr_q)
            _inline_runs(p_obj, s[2:], taille=11, couleur=GRIS)
            i += 1; continue

        # Paragraphe normal — accumuler les lignes consécutives
        para_parts = [s]
        j = i + 1
        while j < len(lignes):
            ns = lignes[j].strip()
            if (not ns or ns.startswith(("#", "-", "*", "•", "|", "►", "▶", "→", ">"))
                    or re.match(r'^\d+[.)]\s', ns)
                    or re.match(r'^[-*_]{3,}$', ns)
                    or re.match(r'^\s{2,}[-•]\s', lignes[j])):
                break
            para_parts.append(ns)
            j += 1
        p_obj = doc.add_paragraph()
        p_obj.paragraph_format.space_before = Pt(4)
        p_obj.paragraph_format.space_after  = Pt(4)
        _inline_runs(p_obj, " ".join(para_parts), taille=11)
        i = j
        continue

    # ── En-tête et pied de page ───────────────────────────────────────────────
    header = sec.header
    p_hdr  = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p_hdr.clear()
    p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run_hdr = p_hdr.add_run(f"{titre}  •  Rapport de réunion")
    run_hdr.font.size = Pt(8)
    run_hdr.font.color.rgb = RGBColor(*GRIS)
    run_hdr.italic = True

    footer = sec.footer
    p_ftr  = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p_ftr.clear()
    p_ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_ftr = p_ftr.add_run(f"Yukpo Pro  •  {datetime.now().strftime('%d/%m/%Y')}     ")
    run_ftr.font.size = Pt(8)
    run_ftr.font.color.rgb = RGBColor(*GRIS)
    # Numéro de page
    run_pg = p_ftr.add_run()
    for tag, text in [('begin', ''), ('', ' PAGE '), ('end', '')]:
        fc = OxmlElement('w:fldChar')
        if tag: fc.set(qn('w:fldCharType'), tag)
        else:
            it = OxmlElement('w:instrText')
            it.set(qn('xml:space'), 'preserve')
            it.text = text
            run_pg._r.append(it)
            continue
        run_pg._r.append(fc)
    run_pg.font.size = Pt(8)
    run_pg.font.color.rgb = RGBColor(*BLEU)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


async def _transcrire_chunks_pro(
    contenu: bytes,
    nom_fichier: str,
    mime_whisper: str,
    client_oai,
) -> tuple[str, str]:
    """
    Transcrit un audio via Whisper en le découpant en chunks si > 24 MB.
    Retourne (texte_complet, langue_detectee).
    verbose_json uniquement sur le 1er chunk pour détecter la langue.
    """
    ext = nom_fichier.rsplit(".", 1)[-1] if "." in nom_fichier else "m4a"
    parties: list[str] = []
    langue_detectee = "unknown"
    offset = 0
    idx = 0

    while offset < len(contenu):
        chunk = contenu[offset: offset + WHISPER_MAX_BYTES]
        offset += WHISPER_MAX_BYTES
        idx += 1
        nom_chunk = f"chunk_{idx:02d}.{ext}"

        if idx == 1:
            resp = await client_oai.audio.transcriptions.create(
                model="whisper-1",
                file=(nom_chunk, chunk, mime_whisper),
                response_format="verbose_json",
            )
            texte = (resp.text or "").strip()
            langue_detectee = getattr(resp, "language", "unknown") or "unknown"
        else:
            resp = await client_oai.audio.transcriptions.create(
                model="whisper-1",
                file=(nom_chunk, chunk, mime_whisper),
                response_format="text",
            )
            texte = str(resp).strip()

        if texte:
            parties.append(texte)

    return "\n".join(parties), langue_detectee


_TRANSCRIPTION_MAX_DIRECT = 60_000  # chars — seuil avant résumé par segments


async def _preparer_transcription_pour_rapport(transcription: str, langue: str = "fr") -> str:
    """
    Retourne la transcription prête pour le prompt de rapport.
    Si > 60K chars (typique 4H+), résume par segments de 50K puis concatène.
    Les résumés intermédiaires sont produits dans `langue`.
    """
    if len(transcription) <= _TRANSCRIPTION_MAX_DIRECT:
        return transcription

    from core.ia_client import ia_client, ModeIA

    langue_label = LANGUE_LABELS.get(langue, langue)
    taille_seg = 50_000
    recouvrement = 1_000
    segments: list[str] = []
    pos = 0
    while pos < len(transcription):
        fin = min(pos + taille_seg, len(transcription))
        segments.append(transcription[pos:fin])
        pos = fin - recouvrement if fin < len(transcription) else fin

    logger.info(f"[ProReunions] Transcription longue ({len(transcription)} chars) → {len(segments)} segments")

    resumes: list[str] = []
    for i, seg in enumerate(segments, 1):
        resp = await ia_client.appeler(
            prompt=(
                f"Résume fidèlement en {langue_label} ce segment {i}/{len(segments)} "
                f"de transcription de réunion. "
                f"Conserve TOUTES les décisions, actions, chiffres, noms et points importants. "
                f"Réponds UNIQUEMENT en {langue_label}. Résumé en 1500 mots max :\n\n{seg}"
            ),
            mode=ModeIA.ANALYSE,
            max_tokens_override=2000,
            utiliser_cache=False,
        )
        resumes.append(f"=== Segment {i}/{len(segments)} ===\n{resp.contenu.strip()}")

    return "\n\n".join(resumes)


def _extraire_extension(nom_fichier: str, mime: str) -> str:
    """Déduit l'extension la plus fiable entre le nom de fichier et le MIME."""
    if "." in nom_fichier:
        ext = nom_fichier.rsplit(".", 1)[-1].lower()
        if ext in {"mp3", "mp4", "m4a", "wav", "webm", "ogg", "flac", "opus", "aac", "3gp"}:
            return ext

    mime_map = {
        "audio/mpeg": "mp3",
        "audio/mp4": "mp4",
        "audio/m4a": "m4a",
        "audio/x-m4a": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
        "audio/opus": "opus",
        "audio/aac": "aac",
        "audio/3gpp": "3gp",
        "video/mp4": "mp4",
        "video/webm": "webm",
    }
    return mime_map.get(mime, "m4a")


def _mime_pour_whisper(ext: str) -> str:
    """Retourne le MIME type correct pour l'API Whisper."""
    mime_map = {
        "mp3": "audio/mpeg",
        "mp4": "audio/mp4",
        "m4a": "audio/mp4",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "opus": "audio/opus",
        "aac": "audio/aac",
        "3gp": "audio/3gpp",
    }
    return mime_map.get(ext, "audio/mp4")


def _scripts_mixtes(texte: str, langue_cible: str) -> bool:
    """
    Détecte si le texte contient des caractères d'écritures non-latines
    alors que la langue cible est latine (ou vice-versa).
    """
    langues_latines = {"fr", "en", "es", "pt", "de", "wo", "ha", "yo", "bm", "ln", "mg"}
    langues_arabes = {"ar"}
    langues_cjk = {"zh", "ja", "ko"}

    if langue_cible in langues_latines:
        # Chercher des caractères arabes ou CJK dans le texte
        for c in texte:
            code = ord(c)
            if 0x0600 <= code <= 0x06FF:  # Arabe
                return True
            if 0x4E00 <= code <= 0x9FFF:  # CJK
                return True
    return False


async def _traduire_transcription(
    texte: str,
    langue_source_detectee: str,
    langue_cible: str,
    langue_cible_label: str,
    settings=None,
) -> str:
    """
    Traduit/normalise la transcription vers la langue cible via Claude ou GPT.
    Gère les transcriptions multilingues en produisant un texte cohérent et fluide.
    """
    prompt = f"""Tu es un traducteur professionnel spécialisé dans la transcription de réunions multilingues.

La transcription ci-dessous provient d'une réunion où plusieurs langues ont pu être utilisées
(langue détectée principalement : {langue_source_detectee}).

Ta tâche : Traduis et normalise l'intégralité de cette transcription en **{langue_cible_label}**.

Règles importantes :
- Traduis fidèlement le sens, ne résume pas et ne reformule pas
- Si une phrase est déjà dans la langue cible, conserve-la telle quelle
- Préserve les noms propres (personnes, lieux, entreprises)
- Garde les nombres, dates et références exactes
- Pour les termes techniques ou jargon métier sans équivalent, conserve le terme original entre parenthèses
- Ne rajoute aucun commentaire, préambule ou note

TRANSCRIPTION ORIGINALE :
{texte[:6000]}

TRANSCRIPTION EN {langue_cible_label.upper()} :"""

    try:
        from core.ia_client import ia_client, ModeIA

        reponse_ia = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            max_tokens_override=4096,
            utiliser_cache=False,
        )
        return reponse_ia.contenu.strip()

    except Exception as exc:
        logger.warning(f"[ProReunions] Traduction échouée, retour texte brut: {exc}")

    return texte  # Fallback : retourner le texte brut si la traduction échoue
