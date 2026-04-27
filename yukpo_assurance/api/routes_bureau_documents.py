"""
Bureau Documents — Listing et téléchargement de tous les documents générés par l'utilisateur.
Routes : /api/v1/bureau/documents/
"""
import logging
import time
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.bureau_documents")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_TYPE_LABELS = {
    "doc": "Rédaction IA",
    "ocr": "Scan / OCR",
    "trad": "Traduction",
    "audio": "Audio → Doc",
    "pdf": "Infographie PDF",
    "designerpro": "Designer Pro (multi-page)",
    "devis": "Devis",
    "facture": "Facture",
}

_ICONS = {
    "doc": "📄", "ocr": "🔍", "trad": "🌐",
    "audio": "🎙️", "pdf": "🎨", "designerpro": "🎨",
    "devis": "📋", "facture": "🧾",
}


def _type_from_nom(nom: str) -> str:
    for k in _TYPE_LABELS:
        if f"_{k}_" in nom or nom.startswith(f"bureau_{k}_"):
            return k
    return "doc"


@router.get("/", summary="Liste tous les documents générés par l'utilisateur")
async def lister_documents(
    current_user: TokenData = Depends(get_current_user),
):
    uid = str(current_user.user_id)
    docs = []
    if _DATA_DIR.exists():
        for f in sorted(_DATA_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not f.is_file():
                continue
            nom = f.name
            # Filtrer par user_id — les noms contiennent _{user_id}_
            if f"_{uid}_" not in nom and current_user.role != "admin":
                continue
            stat = f.stat()
            type_doc = _type_from_nom(nom)
            ext = nom.rsplit(".", 1)[-1].upper() if "." in nom else "?"
            docs.append({
                "fichier_id": nom,
                "type": type_doc,
                "type_label": _TYPE_LABELS.get(type_doc, "Document"),
                "icone": _ICONS.get(type_doc, "📄"),
                "extension": ext,
                "taille_ko": round(stat.st_size / 1024, 1),
                "date_creation": stat.st_mtime,
                "nom_affiche": _nom_affiche(nom),
            })
    return {"documents": docs, "total": len(docs)}


def _nom_affiche(nom: str) -> str:
    parts = nom.replace("bureau_", "").split("_")
    # Retire user_id (numérique) et timestamp
    readable = [p for p in parts if not p.isdigit() and len(p) > 2]
    return " ".join(readable[:4]).title().replace(".Docx", "").replace(".Pdf", "") or nom[:30]


@router.get("/{fichier_id}", summary="Télécharger un document généré")
async def telecharger_document(
    fichier_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    if "/" in fichier_id or "\\" in fichier_id or ".." in fichier_id:
        raise HTTPException(400, detail="Nom de fichier invalide")

    chemin = _DATA_DIR / fichier_id
    if not chemin.exists():
        raise HTTPException(404, detail="Document introuvable")

    if f"_{current_user.user_id}_" not in fichier_id and current_user.role != "admin":
        raise HTTPException(403, detail="Accès refusé")

    ext = fichier_id.rsplit(".", 1)[-1].lower() if "." in fichier_id else ""
    mt_map = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
    }
    media_type = mt_map.get(ext, "application/octet-stream")

    try:
        from modules.bureau.service_credits_bureau import debiter_forfait
        await debiter_forfait(current_user.user_id, "document_download", module="documents")
    except Exception:
        pass

    return Response(
        content=chemin.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{fichier_id}"'},
    )


@router.delete("/{fichier_id}", summary="Supprimer un document généré")
async def supprimer_document(
    fichier_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    if "/" in fichier_id or "\\" in fichier_id or ".." in fichier_id:
        raise HTTPException(400, detail="Nom de fichier invalide")

    chemin = _DATA_DIR / fichier_id
    if not chemin.exists():
        raise HTTPException(404, detail="Document introuvable")

    if f"_{current_user.user_id}_" not in fichier_id and current_user.role != "admin":
        raise HTTPException(403, detail="Accès refusé")

    chemin.unlink()
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait
        await debiter_forfait(current_user.user_id, "document_suppression", module="documents")
    except Exception:
        pass
    return {"supprime": True, "fichier_id": fichier_id}
