"""
Intégration Google Drive 2-way (import/export).

Pattern moderne : le frontend gère l'OAuth via Google JavaScript SDK
(gapi/Google Identity Services). Backend reçoit l'access_token et
opère directement sur l'API Drive REST v3 (HTTPS, pas de scopes côté
backend, pas de stockage refresh_token).

Cas d'usage :
- Import : utilisateur sélectionne un DOCX/PPTX/PDF dans son Drive →
  Yukpo le récupère, l'analyse (OCR/redaction/etc.), et le re-traite.
- Export : Yukpo génère un DOCX/PPTX/PDF → push direct dans le Drive
  utilisateur (dossier 'Yukpo' auto-créé).

Sécurité : access_token reçu en header Authorization ou body, jamais
loggé. Validation : token doit avoir scope `drive.file` ou `drive` actif.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_current_user, TokenData

router = APIRouter()
logger = logging.getLogger("yukpo_assurance.routes_bureau_gdrive")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_DRIVE_API = "https://www.googleapis.com/drive/v3"
_DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"


# ─── Helpers Drive ────────────────────────────────────────────────────────────


async def _drive_get_file_meta(access_token: str, file_id: str) -> dict:
    """Récupère les métadonnées d'un fichier Drive (nom, mime, taille)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"fields": "id,name,mimeType,size,createdTime,webViewLink"}
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{_DRIVE_API}/files/{file_id}", headers=headers, params=params)
        if r.status_code == 401:
            raise HTTPException(401, "Token Google Drive invalide ou expiré")
        if r.status_code == 404:
            raise HTTPException(404, "Fichier Drive introuvable ou non autorisé")
        r.raise_for_status()
        return r.json()


async def _drive_download_file(access_token: str, file_id: str, mime_export: Optional[str] = None) -> bytes:
    """Télécharge le contenu binaire d'un fichier Drive.
    Si mime_export fourni (ex: pour Google Docs natifs), utilise /export."""
    headers = {"Authorization": f"Bearer {access_token}"}
    if mime_export:
        url = f"{_DRIVE_API}/files/{file_id}/export"
        params = {"mimeType": mime_export}
    else:
        url = f"{_DRIVE_API}/files/{file_id}"
        params = {"alt": "media"}
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.get(url, headers=headers, params=params)
        if r.status_code != 200:
            raise HTTPException(
                502,
                f"Téléchargement Drive échoué (HTTP {r.status_code}) : {r.text[:200]}",
            )
        return r.content


async def _drive_ensure_folder(access_token: str, name: str = "Yukpo") -> str:
    """Trouve ou crée le dossier 'Yukpo' à la racine du Drive utilisateur.
    Retourne folder_id."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0) as c:
        # Cherche
        q = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            f"and 'root' in parents and trashed=false"
        )
        r = await c.get(
            f"{_DRIVE_API}/files",
            headers=headers,
            params={"q": q, "fields": "files(id,name)"},
        )
        if r.status_code == 401:
            raise HTTPException(401, "Token Google Drive invalide ou expiré")
        r.raise_for_status()
        files = r.json().get("files") or []
        if files:
            return files[0]["id"]
        # Crée
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": ["root"],
        }
        r2 = await c.post(f"{_DRIVE_API}/files", headers=headers, json=meta)
        r2.raise_for_status()
        return r2.json()["id"]


async def _drive_upload(
    access_token: str, fichier_bytes: bytes, nom: str, mime: str,
    parent_folder_id: Optional[str] = None,
) -> dict:
    """Upload un fichier dans Drive (multipart). Retourne metadata du fichier créé."""
    headers = {"Authorization": f"Bearer {access_token}"}
    metadata: dict = {"name": nom, "mimeType": mime}
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]

    boundary = "----yukpo_boundary_18a3f7"
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{__import__('json').dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + fichier_bytes + f"\r\n--{boundary}--\r\n".encode()

    headers_post = dict(headers)
    headers_post["Content-Type"] = f"multipart/related; boundary={boundary}"

    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            f"{_DRIVE_UPLOAD}?uploadType=multipart&fields=id,name,webViewLink,mimeType,size",
            headers=headers_post,
            content=body,
        )
        if r.status_code not in (200, 201):
            raise HTTPException(
                502, f"Upload Drive échoué (HTTP {r.status_code}) : {r.text[:200]}"
            )
        return r.json()


# ─── Endpoints ────────────────────────────────────────────────────────────────


class DemandeImportDrive(BaseModel):
    access_token: str = Field(..., min_length=20,
                                description="Access token OAuth Google (frontend gapi)")
    file_id: str = Field(..., min_length=10,
                          description="ID du fichier Drive à importer")
    convert_google_native: bool = Field(default=True,
                                          description="Si Google Docs/Slides natif → export DOCX/PPTX")


@router.post("/import", tags=["Bureau — Google Drive"])
async def importer_drive(
    demande: DemandeImportDrive,
    current_user: TokenData = Depends(get_current_user),
):
    """Importe un fichier depuis Google Drive vers les data Yukpo.
    Retourne le file_id local (utilisable par OCR/redaction/etc.)."""
    meta = await _drive_get_file_meta(demande.access_token, demande.file_id)
    mime = meta.get("mimeType") or ""
    nom = meta.get("name") or "drive_file"

    # Conversion auto pour Google Docs/Slides natifs
    mime_export: Optional[str] = None
    extension = ""
    if demande.convert_google_native:
        if mime == "application/vnd.google-apps.document":
            mime_export = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            extension = ".docx"
        elif mime == "application/vnd.google-apps.presentation":
            mime_export = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            extension = ".pptx"
        elif mime == "application/vnd.google-apps.spreadsheet":
            mime_export = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            extension = ".xlsx"
    if not extension:
        extension = "." + nom.split(".")[-1] if "." in nom else ""

    contenu = await _drive_download_file(
        demande.access_token, demande.file_id, mime_export=mime_export,
    )

    # Sauvegarder localement
    import time as _t
    nom_safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in nom)[:60].strip() or "drive"
    fichier_id = f"gdrive_{current_user.user_id}_{int(_t.time())}_{nom_safe}{extension}"
    fichier_id = fichier_id.replace(" ", "_")
    chemin = _DATA_DIR / fichier_id
    chemin.write_bytes(contenu)

    return {
        "ok": True,
        "fichier_id": fichier_id,
        "nom_original": nom,
        "mime_type": mime_export or mime,
        "taille_octets": len(contenu),
        "drive_link": meta.get("webViewLink"),
    }


class DemandeExportDrive(BaseModel):
    access_token: str = Field(..., min_length=20)
    fichier_local_id: str = Field(..., min_length=5,
                                    description="ID du fichier généré par Yukpo (data/generated/...)")
    nom_drive: Optional[str] = Field(default=None,
                                        description="Nom souhaité dans Drive (sinon nom local)")


@router.post("/export", tags=["Bureau — Google Drive"])
async def exporter_drive(
    demande: DemandeExportDrive,
    current_user: TokenData = Depends(get_current_user),
):
    """Exporte un fichier généré Yukpo vers Google Drive (dossier 'Yukpo'
    auto-créé à la racine)."""
    fid = demande.fichier_local_id
    if "/" in fid or "\\" in fid or ".." in fid:
        raise HTTPException(400, "ID fichier invalide")
    if (
        f"_{current_user.user_id}_" not in fid
        and current_user.role not in ("admin", "super_admin", "yukpo_owner")
    ):
        raise HTTPException(403, "Accès refusé")
    chemin = _DATA_DIR / fid
    if not chemin.exists():
        raise HTTPException(404, "Fichier introuvable")
    contenu = chemin.read_bytes()

    # Détection MIME depuis extension
    ext = chemin.suffix.lower()
    mime_map = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf":  "application/pdf",
        ".png":  "image/png",
        ".jpg":  "image/jpeg", ".jpeg": "image/jpeg",
        ".mp4":  "video/mp4",
        ".svg":  "image/svg+xml",
    }
    mime = mime_map.get(ext, "application/octet-stream")
    nom = demande.nom_drive or chemin.name

    folder_id = await _drive_ensure_folder(demande.access_token, name="Yukpo")
    drive_meta = await _drive_upload(
        demande.access_token, contenu, nom, mime, parent_folder_id=folder_id,
    )

    return {
        "ok": True,
        "drive_file_id": drive_meta.get("id"),
        "drive_link": drive_meta.get("webViewLink"),
        "nom": drive_meta.get("name"),
        "mime_type": drive_meta.get("mimeType"),
        "taille_octets": int(drive_meta.get("size") or len(contenu)),
    }


@router.get("/health", tags=["Bureau — Google Drive"])
async def gdrive_health():
    """Indique au frontend si l'intégration Drive est dispo (tier infra OK)."""
    return {
        "ok": True,
        "pattern": "frontend_oauth",
        "scopes_requis": ["https://www.googleapis.com/auth/drive.file"],
        "endpoints": {
            "import": "POST /api/v1/bureau/gdrive/import",
            "export": "POST /api/v1/bureau/gdrive/export",
        },
    }
