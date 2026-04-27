"""
Bureau OCR Scanner — Scan → Texte structuré → .docx propre.

Pipeline :
  1. Upload image (JPG/PNG/TIFF/PDF scan)
  2. Prétraitement Pillow (deskew, contraste, recadrage)
  3. Claude Vision OCR → texte structuré
  4. Claude reformate en Markdown propre
  5. Export .docx via python-docx
"""
from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("yukpo_assurance.bureau.ocr_scanner")


@dataclass
class ResultatOCR:
    texte_brut: str
    texte_structure: str
    contenu_word: Optional[bytes] = None
    confiance: float = 0.0          # 0.0–1.0 estimé par le modèle
    type_document: str = "inconnu"  # lettre | formulaire | tableau | manuscrit | recu
    meta: dict = field(default_factory=dict)


def _pretraiter_image(image_bytes: bytes, mime: str = "image/jpeg") -> bytes:
    """
    Prétraitement Pillow : amélioration contraste, conversion RGB.
    Deskew et recadrage si possible.
    Retourne les bytes de l'image améliorée.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        img = Image.open(io.BytesIO(image_bytes))

        # Conversion RGB (évite RGBA/P → JPEG error)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Amélioration contraste
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        # Amélioration netteté
        img = img.filter(ImageFilter.SHARPEN)

        # Redimensionnement si trop petit (OCR moins fiable < 800px)
        w, h = img.size
        if min(w, h) < 800:
            scale = 800 / min(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92, optimize=True)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[OCR] Prétraitement Pillow échoué, image brute utilisée : {e}")
        return image_bytes


async def scanner_image(
    image_bytes: bytes,
    mime: str = "image/jpeg",
    langue: str = "fr",
    type_attendu: Optional[str] = None,  # lettre | formulaire | recu | manuscrit | tableau
    export_word: bool = True,
) -> ResultatOCR:
    """
    Pipeline complet : image → texte → Markdown structuré → (optionnel) .docx.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    # 1. Prétraitement image
    image_bytes = _pretraiter_image(image_bytes, mime)
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    # 2. OCR Claude Vision
    hint_type = f" Il s'agit probablement d'un(e) {type_attendu}." if type_attendu else ""
    prompt_ocr = f"""Analyse cette image et extrait TOUT le texte visible.{hint_type}

Instructions :
1. Retranscris chaque mot exactement tel qu'il apparaît (incluant les fautes d'orthographe originales)
2. Préserve la mise en page : titres, paragraphes, listes, tableaux
3. Pour les tableaux : utilise le format Markdown |col1|col2|
4. Indique [ILLISIBLE] pour les parties non déchiffrables
5. Commence directement par le texte, sans commentaire préliminaire
6. Si c'est manuscrit : transcris fidèlement, signal [INCERTAIN: mot] quand tu n'es pas sûr

Retourne uniquement le texte transcrit, en Markdown."""

    reponse_ocr = await ia_client.appeler(
        prompt=prompt_ocr,
        mode=ModeIA.ANALYSE,
        forcer_modele=ModelePrioritaire.GPT4O,   # GPT-4o vision = meilleur pour OCR images
        images_b64=[f"data:{mime};base64,{image_b64}"],
    )
    texte_brut = reponse_ocr.contenu

    # 3. Structuration IA
    prompt_structure = f"""Voici un texte extrait par OCR d'un document scanné :

{texte_brut}

Reformate ce texte en Markdown propre et structuré :
- Identifie le type de document (lettre, formulaire, reçu, tableau, manuscrit, contrat, etc.)
- Corrige les erreurs OCR évidentes (lettres inversées, mots coupés par le scan)
- Préserve les informations importantes : dates, montants, noms, références
- Organise avec des titres ## si le document a des sections
- Format tables proprement si présentes
- Retourne d'abord une ligne : TYPE: [type_document]
- Puis le document formaté"""

    reponse_struct = await ia_client.appeler(
        prompt=prompt_structure,
        mode=ModeIA.REDACTION,
        forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,   # légère structuration texte → Haiku
    )
    texte_structure = reponse_struct.contenu

    # Extraction type détecté
    type_doc = "document"
    lignes = texte_structure.split("\n")
    if lignes and lignes[0].startswith("TYPE:"):
        type_doc = lignes[0].replace("TYPE:", "").strip().lower()
        texte_structure = "\n".join(lignes[1:]).strip()

    # Confiance estimée (heuristique sur nb de [ILLISIBLE])
    nb_illisible = texte_brut.count("[ILLISIBLE]")
    nb_mots = max(len(texte_brut.split()), 1)
    confiance = max(0.1, 1.0 - (nb_illisible / nb_mots * 10))

    # 4. Export Word
    contenu_word: Optional[bytes] = None
    if export_word:
        try:
            from modules.bureau.redacteur import _markdown_vers_docx
            contenu_word = _markdown_vers_docx(texte_structure, f"Document scanné — {type_doc}")
        except Exception as e:
            logger.warning(f"[OCR] Export Word échoué : {e}")

    return ResultatOCR(
        texte_brut=texte_brut,
        texte_structure=texte_structure,
        contenu_word=contenu_word,
        confiance=round(confiance, 2),
        type_document=type_doc,
        meta={"tokens": reponse_ocr.tokens_total + reponse_struct.tokens_total},
    )


async def scanner_notes_manuscrites(
    image_bytes: bytes,
    mime: str = "image/jpeg",
    formater_en: str = "lettre",  # lettre | rapport | liste | paragraphe
) -> ResultatOCR:
    """
    Spécialisé notes manuscrites → document formaté.
    Pipeline : lecture cursive → nettoyage → mise en forme finale.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    image_bytes = _pretraiter_image(image_bytes, mime)
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    prompt = f"""Tu es spécialiste en lecture d'écriture cursive africaine (français camerounais/ivoirien/sénégalais).

Lis attentivement ces notes manuscrites et :
1. Transcris fidèlement chaque mot (signal [INCERTAIN: alternative] si ambigu)
2. Reconstitue le sens là où l'écriture est difficile, selon le contexte
3. Produis un document formaté de type "{formater_en}" en français professionnel
4. Corrige discrètement les fautes sans dénaturer le sens voulu par l'auteur

Produis directement le document final, prêt à être utilisé."""

    reponse = await ia_client.appeler(
        prompt=prompt,
        mode=ModeIA.REDACTION,
        forcer_modele=ModelePrioritaire.GPT4O,   # GPT-4o vision — lecture cursive africaine
        images_b64=[f"data:{mime};base64,{image_b64}"],
    )

    texte = reponse.contenu

    contenu_word: Optional[bytes] = None
    try:
        from modules.bureau.redacteur import _markdown_vers_docx
        contenu_word = _markdown_vers_docx(texte, "Notes manuscrites formatées")
    except Exception as e:
        logger.warning(f"[OCR-Manuscrit] Export Word échoué : {e}")

    return ResultatOCR(
        texte_brut=texte,
        texte_structure=texte,
        contenu_word=contenu_word,
        confiance=0.8,
        type_document="manuscrit",
        meta={"tokens": reponse.tokens_total},
    )
