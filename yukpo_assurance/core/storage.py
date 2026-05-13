"""
Abstraction stockage artefacts (PDFs, MP4s, HTML générés).

Mode auto-détecté par variables d'environnement :

  • R2_ACCOUNT_ID + R2_ACCESS_KEY_ID + R2_SECRET_ACCESS_KEY + R2_BUCKET
    → Cloudflare R2 (S3-compatible, $0.015/GB, egress gratuit)

  • Sinon → local volume Fly (mode legacy, compatible 100% du code existant)

Le fallback local-only garantit qu'AUCUN endpoint ne casse si R2 n'est
pas configuré. Activation progressive endpoint par endpoint au fur et
à mesure qu'on a confiance.

Endpoints à migrer en priorité (gros volumes) :
  • routes_bureau_freeform.py  (PDFs print-ready ~5-20 MB par job)
  • routes_bureau_video.py     (MP4s 5-60s, jusqu'à 50 MB)
  • routes_pro_generateurs.py  (HTML landing/slides web ~100-300 KB)

Tant que les autres routes (gdrive, audio, agent, etc.) continuent
d'utiliser `Path.write_bytes` direct → elles restent sur le volume Fly.
Migration future : remplacer les `Path.write_bytes` par
`storage.save_artifact(category, name, bytes)`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yukpo_assurance.storage")

# Racine locale (fallback ou tier 1)
_DEFAULT_LOCAL_ROOT = Path(__file__).resolve().parent.parent / "data" / "generated"

# Catégorie → sous-dossier local + préfixe R2
# (Mêmes noms côté local et R2 pour migration symétrique)
_CATEGORIES = {
    "bureau":       "bureau",        # PDFs freeform, infographie, livret, vidéos
    "pro_reports":  "pro_reports",   # DOCX rapports Pro
    "pro_slides":   "pro_slides",    # PPTX slides Pro
    "pro_data":     "pro_data",      # XLSX analyses data
    "attestations": "attestations",  # Attestations assurance
    "contrats":     "contrats_generes",
}


def _r2_enabled() -> bool:
    """True si R2 est configuré côté env (S3-compatible Cloudflare)."""
    return bool(
        os.getenv("R2_ACCOUNT_ID")
        and os.getenv("R2_ACCESS_KEY_ID")
        and os.getenv("R2_SECRET_ACCESS_KEY")
        and os.getenv("R2_BUCKET")
    )


def _r2_client():
    """Retourne un client boto3 S3 configuré pour Cloudflare R2.
    Lazy import car boto3 est lourd (~30 MB) — on l'évite si R2 inactif.
    """
    try:
        import boto3
        from botocore.config import Config
    except ImportError as e:
        raise RuntimeError(
            "boto3 requis pour R2 mais non installé. "
            "Ajoute `boto3>=1.34.0` à requirements-cloud.txt"
        ) from e

    account_id = os.environ["R2_ACCOUNT_ID"]
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        # SigV4 + virtual-hosted style requis pour R2
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


# ── API publique ──────────────────────────────────────────────────────────────

def save_artifact(
    category: str,
    name: str,
    content: bytes,
    content_type: Optional[str] = None,
) -> dict:
    """Sauvegarde un artefact. Écrit en local SI mode local, sinon en R2.

    Returns: dict {storage: "local|r2", path|key: str, size_bytes: int}.
    """
    if category not in _CATEGORIES:
        raise ValueError(f"Catégorie inconnue : {category} (valides : {list(_CATEGORIES)})")
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"Nom de fichier invalide : {name}")

    sous_dossier = _CATEGORIES[category]

    # Tier 1 : R2 si configuré
    if _r2_enabled():
        try:
            client = _r2_client()
            bucket = os.environ["R2_BUCKET"]
            key = f"{sous_dossier}/{name}"
            extra = {}
            if content_type:
                extra["ContentType"] = content_type
            client.put_object(
                Bucket=bucket, Key=key, Body=content, **extra,
            )
            logger.info(f"[storage/R2] uploaded s3://{bucket}/{key} ({len(content)} bytes)")
            return {
                "storage": "r2", "key": key, "bucket": bucket,
                "size_bytes": len(content),
            }
        except Exception as e:
            # Fallback local si R2 échoue ponctuellement (réseau, quota, etc.)
            logger.warning(f"[storage/R2] échec upload, fallback local : {e}")

    # Tier 2 : local volume Fly
    local_root = Path(os.getenv("YUKPO_STORAGE_LOCAL_ROOT") or _DEFAULT_LOCAL_ROOT)
    local_path = local_root / sous_dossier / name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    return {
        "storage": "local", "path": str(local_path),
        "size_bytes": len(content),
    }


def read_artifact(category: str, name: str) -> Optional[bytes]:
    """Lit un artefact. Cherche R2 d'abord (si actif), puis local.

    Returns: bytes ou None si introuvable des deux côtés.
    """
    if category not in _CATEGORIES:
        return None
    if "/" in name or "\\" in name or ".." in name:
        return None
    sous_dossier = _CATEGORIES[category]

    if _r2_enabled():
        try:
            client = _r2_client()
            bucket = os.environ["R2_BUCKET"]
            key = f"{sous_dossier}/{name}"
            resp = client.get_object(Bucket=bucket, Key=key)
            return resp["Body"].read()
        except Exception as e:
            err_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if err_code not in ("NoSuchKey", "404"):
                logger.warning(f"[storage/R2] erreur read {key} : {e}")

    # Fallback local
    local_root = Path(os.getenv("YUKPO_STORAGE_LOCAL_ROOT") or _DEFAULT_LOCAL_ROOT)
    local_path = local_root / sous_dossier / name
    if local_path.exists():
        return local_path.read_bytes()
    return None


def delete_artifact(category: str, name: str) -> bool:
    """Supprime un artefact des 2 storages. Retourne True si supprimé quelque part."""
    if category not in _CATEGORIES:
        return False
    if "/" in name or "\\" in name or ".." in name:
        return False
    sous_dossier = _CATEGORIES[category]
    ok_any = False

    if _r2_enabled():
        try:
            client = _r2_client()
            bucket = os.environ["R2_BUCKET"]
            key = f"{sous_dossier}/{name}"
            client.delete_object(Bucket=bucket, Key=key)
            ok_any = True
        except Exception:
            pass

    local_root = Path(os.getenv("YUKPO_STORAGE_LOCAL_ROOT") or _DEFAULT_LOCAL_ROOT)
    local_path = local_root / sous_dossier / name
    if local_path.exists():
        local_path.unlink()
        ok_any = True
    return ok_any


def signed_url(category: str, name: str, expires_in_s: int = 3600) -> Optional[str]:
    """Génère une URL signée temporaire pour partage public (R2 seulement).

    Idéal pour le futur bouton "Partager" sur landing pages — l'URL signée
    permet d'accéder au fichier R2 sans auth Yukpo, expiration au choix.

    Returns: URL ou None si R2 inactif (utiliser /bureau/documents/{name}?token=)
    """
    if not _r2_enabled() or category not in _CATEGORIES:
        return None
    try:
        client = _r2_client()
        bucket = os.environ["R2_BUCKET"]
        key = f"{_CATEGORIES[category]}/{name}"
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=int(expires_in_s),
        )
        return url
    except Exception as e:
        logger.warning(f"[storage/R2] signed_url échec : {e}")
        return None


def storage_info() -> dict:
    """Diagnostic : retourne l'état du storage configuré."""
    return {
        "r2_enabled": _r2_enabled(),
        "r2_bucket": os.getenv("R2_BUCKET") if _r2_enabled() else None,
        "local_root": str(_DEFAULT_LOCAL_ROOT),
        "categories": list(_CATEGORIES.keys()),
    }
