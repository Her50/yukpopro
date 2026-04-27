"""
Médiathèque utilisateur pour le module Infographie Pro.

Deux niveaux :
  - **Session** (volatile, TTL 24h) : photos, illustrations, témoignages, scans uploadés
    pour un projet en cours. Auto-purge passé le TTL.
  - **Compte** (persistant) : logos, bannières, signatures, cachets — réutilisables
    sur tous les futurs projets de l'utilisateur.

Chaque média est :
  - Stocké sur disque (sécurisé : nom = uuid, jamais le nom utilisateur)
  - Indexé en JSON sidecar (catégorie, label, dimensions, dominant_color)
  - Optimisé via Pillow (downscale auto si > 4096px, conversion sRGB,
    pré-calcul couleur dominante pour harmonisation palette)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yukpo_assurance.bureau.mediatheque")

_BASE_DIR = Path(__file__).parent.parent.parent / "data" / "mediatheque"
_SESSION_DIR = _BASE_DIR / "sessions"     # data/mediatheque/sessions/{session_id}/
_COMPTE_DIR = _BASE_DIR / "comptes"       # data/mediatheque/comptes/{user_id}/
_SESSION_DIR.mkdir(parents=True, exist_ok=True)
_COMPTE_DIR.mkdir(parents=True, exist_ok=True)

SESSION_TTL_SECONDES = 24 * 3600
TAILLE_MAX_BYTES = 15 * 1024 * 1024
DIMENSION_MAX_PX = 4096

CATEGORIES_SESSION = {
    "photo",          # Portraits, photos d'événement
    "illustration",   # Décors, motifs, fonds
    "scan",           # Documents scannés (témoignages manuscrits, citations)
    "qr",             # QR codes pré-générés (RSVP, dons, etc.)
    "icone",          # Icônes décoratives
}
CATEGORIES_COMPTE = {
    "logo",
    "banniere",
    "signature",
    "cachet",
    "filigrane",
    "tampon",
}


@dataclass
class Media:
    media_id: str
    categorie: str
    label: str
    nom_fichier_origine: str
    chemin: str                  # chemin disque relatif à _BASE_DIR
    mime: str
    taille_bytes: int
    largeur_px: int
    hauteur_px: int
    couleur_dominante_hex: Optional[str] = None
    portee: str = "session"      # "session" | "compte"
    propriétaire_id: str = ""    # session_id ou user_id selon portée
    cree_le: float = field(default_factory=time.time)
    expire_le: Optional[float] = None
    meta: dict = field(default_factory=dict)


def _calculer_couleur_dominante(image_pillow) -> Optional[str]:
    """Extrait la couleur dominante d'une image (utile pour harmonisation palette IA)."""
    try:
        img = image_pillow.convert("RGB").resize((50, 50))
        pixels = list(img.getdata())
        if not pixels:
            return None
        r = sum(p[0] for p in pixels) // len(pixels)
        g = sum(p[1] for p in pixels) // len(pixels)
        b = sum(p[2] for p in pixels) // len(pixels)
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return None


def _normaliser_image(contenu: bytes, mime: str) -> tuple[bytes, str, int, int, Optional[str]]:
    """
    Normalise une image : conversion sRGB, downscale si > DIMENSION_MAX_PX,
    re-encode en JPEG (qualité 90) ou PNG selon transparence.
    Retourne (contenu_normalisé, mime_final, w, h, couleur_dominante_hex).
    Si mime non-image (ex: SVG), retourne contenu inchangé.
    """
    if not mime.startswith("image/") or mime in ("image/svg+xml",):
        # SVG : conserver tel quel — pas de normalisation Pillow
        return contenu, mime, 0, 0, None

    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(contenu))
        img.load()
    except Exception as e:
        logger.warning(f"[Mediatheque] Image illisible : {e}")
        raise ValueError(f"Image invalide : {e}")

    a_transparence = (img.mode in ("RGBA", "LA")) or ("transparency" in img.info)
    w, h = img.size

    # Downscale si nécessaire
    if max(w, h) > DIMENSION_MAX_PX:
        ratio = DIMENSION_MAX_PX / max(w, h)
        nw, nh = int(w * ratio), int(h * ratio)
        img = img.resize((nw, nh), Image.LANCZOS)
        w, h = nw, nh

    # Conversion sRGB
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if a_transparence else "RGB")

    couleur_dom = _calculer_couleur_dominante(img)

    import io as _io
    buf = _io.BytesIO()
    if a_transparence:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "image/png", w, h, couleur_dom
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue(), "image/jpeg", w, h, couleur_dom


def _index_path(portee: str, owner_id: str) -> Path:
    racine = _SESSION_DIR if portee == "session" else _COMPTE_DIR
    rep = racine / owner_id
    rep.mkdir(parents=True, exist_ok=True)
    return rep / "_index.json"


def _charger_index(portee: str, owner_id: str) -> dict[str, Media]:
    idx = _index_path(portee, owner_id)
    if not idx.exists():
        return {}
    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
        return {k: Media(**v) for k, v in data.items()}
    except Exception as e:
        logger.warning(f"[Mediatheque] Index corrompu {idx} : {e}")
        return {}


def _sauver_index(portee: str, owner_id: str, index: dict[str, Media]) -> None:
    idx = _index_path(portee, owner_id)
    serial = {k: asdict(v) for k, v in index.items()}
    idx.write_text(json.dumps(serial, ensure_ascii=False, indent=2), encoding="utf-8")


def ajouter_media(
    portee: str,
    owner_id: str,
    contenu: bytes,
    nom_fichier: str,
    mime: str,
    categorie: str,
    label: Optional[str] = None,
) -> Media:
    """Stocke un média et retourne son descripteur."""
    if portee not in ("session", "compte"):
        raise ValueError("portee doit être 'session' ou 'compte'")
    cats_valides = CATEGORIES_SESSION if portee == "session" else CATEGORIES_COMPTE
    if categorie not in cats_valides:
        raise ValueError(f"Catégorie '{categorie}' invalide pour portée '{portee}'. "
                         f"Valides : {sorted(cats_valides)}")
    if not contenu:
        raise ValueError("Contenu vide")
    if len(contenu) > TAILLE_MAX_BYTES:
        raise ValueError(f"Fichier trop volumineux (max {TAILLE_MAX_BYTES // (1024*1024)} MB)")

    contenu_norm, mime_final, w, h, couleur_dom = _normaliser_image(contenu, mime)

    media_id = uuid.uuid4().hex
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/svg+xml": ".svg",
           "image/webp": ".webp"}.get(mime_final, ".bin")
    racine = _SESSION_DIR if portee == "session" else _COMPTE_DIR
    rep = racine / owner_id
    rep.mkdir(parents=True, exist_ok=True)
    fichier = rep / f"{media_id}{ext}"
    fichier.write_bytes(contenu_norm)

    expire = (time.time() + SESSION_TTL_SECONDES) if portee == "session" else None

    media = Media(
        media_id=media_id,
        categorie=categorie,
        label=label or nom_fichier,
        nom_fichier_origine=nom_fichier,
        chemin=str(fichier.relative_to(_BASE_DIR).as_posix()),
        mime=mime_final,
        taille_bytes=len(contenu_norm),
        largeur_px=w,
        hauteur_px=h,
        couleur_dominante_hex=couleur_dom,
        portee=portee,
        propriétaire_id=owner_id,
        expire_le=expire,
    )
    index = _charger_index(portee, owner_id)
    index[media_id] = media
    _sauver_index(portee, owner_id, index)
    return media


def lister_medias(portee: str, owner_id: str, categorie: Optional[str] = None) -> list[Media]:
    purger_session_expirees(owner_id) if portee == "session" else None
    index = _charger_index(portee, owner_id)
    medias = list(index.values())
    if categorie:
        medias = [m for m in medias if m.categorie == categorie]
    return sorted(medias, key=lambda m: m.cree_le, reverse=True)


def recuperer_media(portee: str, owner_id: str, media_id: str) -> Optional[Media]:
    return _charger_index(portee, owner_id).get(media_id)


def lire_bytes(media: Media) -> bytes:
    return (_BASE_DIR / media.chemin).read_bytes()


def supprimer_media(portee: str, owner_id: str, media_id: str) -> bool:
    index = _charger_index(portee, owner_id)
    if media_id not in index:
        return False
    media = index.pop(media_id)
    try:
        (_BASE_DIR / media.chemin).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"[Mediatheque] Suppression fichier {media.chemin} : {e}")
    _sauver_index(portee, owner_id, index)
    return True


def purger_session_expirees(session_id: str) -> int:
    """Supprime les médias session expirés. Retourne le nombre supprimé."""
    index = _charger_index("session", session_id)
    maintenant = time.time()
    expirees = [mid for mid, m in index.items() if m.expire_le and m.expire_le < maintenant]
    for mid in expirees:
        media = index.pop(mid)
        try:
            (_BASE_DIR / media.chemin).unlink(missing_ok=True)
        except Exception:
            pass
    if expirees:
        _sauver_index("session", session_id, index)
    return len(expirees)


def resoudre_refs(
    refs: list[str],
    user_id: str,
    session_id: str,
) -> dict[str, Media]:
    """
    Résout une liste de références médias (forme : 'session:abc123' ou 'compte:def456')
    en {ref → Media}. Les refs introuvables sont simplement omises.
    """
    out: dict[str, Media] = {}
    for ref in refs or []:
        if ":" not in ref:
            continue
        portee, mid = ref.split(":", 1)
        owner = session_id if portee == "session" else user_id
        media = recuperer_media(portee, owner, mid)
        if media:
            out[ref] = media
    return out


def descripteur_pour_ia(media: Media) -> dict:
    """Représentation compacte d'un média à fournir au LLM pour décider de son usage."""
    return {
        "ref": f"{media.portee}:{media.media_id}",
        "categorie": media.categorie,
        "label": media.label,
        "dimensions_px": [media.largeur_px, media.hauteur_px],
        "couleur_dominante": media.couleur_dominante_hex,
        "ratio": (round(media.largeur_px / media.hauteur_px, 2)
                  if media.hauteur_px else None),
    }
