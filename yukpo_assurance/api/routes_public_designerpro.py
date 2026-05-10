"""
Sprint 2.1 — API publique Designer Pro (auth par clé API, pas JWT).

Endpoints sous /api/v1/public/designerpro/* — destinés aux intégrations B2B
(ERP clients, sites marketing, automations CRM/Slack/n8n/Zapier).

Authentification : header `X-API-Key: ypro_live_xxx` ou `Authorization: Bearer ypro_live_xxx`.
Rate limit : per-key (configurable par l'admin de l'org, défaut 100/h, 1000/jour).

Documentation OpenAPI auto-générée par FastAPI sous /docs (filtrée par tag).
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.api_key_auth import ApiKeyIdentity, get_api_key_identity, require_scope

logger = logging.getLogger("yukpo_assurance.api.public_designerpro")
router = APIRouter()


# ─── Modèles publics (volontairement simplifiés vs internes) ──────────────────


class PublicGenererRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=5000,
        description="Brief en langage naturel — détecté automatiquement par l'IA")
    pays: str = Field(default="CM", max_length=3)
    langue: str = Field(default="fr", max_length=8)
    cle_projet: Optional[str] = Field(default=None,
        description="Forcer un gabarit spécifique (cf /catalogue). Sinon auto-detect.")
    mode_visuel: str = Field(default="standard",
        pattern="^(sans|standard|premium|ultra|ultra_plus)$")
    images_b64: Optional[list[str]] = Field(default=None,
        description="Images en base64 à utiliser comme médias (jpeg/png). Max 30.")
    couleur_primaire_hex: Optional[str] = Field(default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$")
    nom_organisation: Optional[str] = Field(default=None, max_length=200)


class PublicGenererResponse(BaseModel):
    ok: bool
    cle_projet: str
    titre: str
    nombre_pages: int
    download_url: Optional[str] = None
    pdf_base64: Optional[str] = None
    print_ready_pdf_base64: Optional[str] = None
    cout_credits: float
    rate_limit_remaining_hour: int
    rate_limit_remaining_day: int


# ─── Endpoints publics ────────────────────────────────────────────────────────


@router.get("/health", tags=["Public API — Designer Pro"])
async def public_health():
    """Santé de l'API publique. Aucune auth requise."""
    return {"ok": True, "service": "yukpopro-designerpro-public-api", "version": "v1"}


@router.get("/catalogue", tags=["Public API — Designer Pro"])
async def public_catalogue(
    identity: ApiKeyIdentity = Depends(require_scope("designerpro:read")),
):
    """Catalogue complet des gabarits disponibles (mono-page + multi-page)."""
    from modules.bureau import gabarits_livret as catalog_multi
    from modules.bureau.infographe import GABARITS as catalog_mono
    return {
        "mono_page": [
            {"cle": c, "label": v.get("label"), "categorie": v.get("categorie"),
             "format_mm": [v.get("width_mm"), v.get("height_mm")],
             "description": v.get("description"), "prix_fcfa": v.get("prix_fcfa")}
            for c, v in catalog_mono.items()
        ],
        "multi_page": [
            {"cle": c, "label": v.get("label"), "categorie": v.get("categorie"),
             "format_mm": list(v.get("format_mm") or []),
             "nombre_pages": len(v.get("pages") or []),
             "description": v.get("description"), "prix_fcfa": v.get("prix_fcfa")}
            for c, v in catalog_multi.PROJETS_INFOGRAPHIE.items()
        ],
    }


@router.post("/orchestrer", tags=["Public API — Designer Pro"])
async def public_orchestrer(
    payload: dict,
    identity: ApiKeyIdentity = Depends(require_scope("designerpro:orchestrer")),
):
    """
    Auto-orchestration : 1 prompt → analyse complète (type/cle/confiance/manques/
    questions/recommandation_medias). Voir doc interne /orchestrer pour le schéma.
    """
    from api.routes_bureau_infographie_pro import (
        DemandeOrchestrer, orchestrer as _orch_internal,
    )
    # Adapter : on bypass JWT et passe une TokenData synthétique
    from core.auth import TokenData
    fake_user = TokenData(
        user_id=identity.user_id, user_nom=f"api:{identity.label}",
        role="agent", compagnie_id=identity.compagnie_id,
    )
    try:
        demande = DemandeOrchestrer(**payload)
    except Exception as e:
        raise HTTPException(400, f"Payload invalide : {e}")
    return await _orch_internal(demande, fake_user)


@router.post("/generate", response_model=PublicGenererResponse,
             tags=["Public API — Designer Pro"])
async def public_generate(
    req: PublicGenererRequest,
    identity: ApiKeyIdentity = Depends(require_scope("designerpro:generate")),
):
    """
    Génère un visuel Designer Pro complet. Endpoint principal de l'API publique.

    Flow :
      1. Si `cle_projet` n'est pas fourni → auto-detect via l'orchestrateur LLM
      2. Si `images_b64` fourni → upload comme médias session puis utilisation
      3. Génération via le pipeline standard (Layout AI + variants + Flux + print-ready)
      4. Retourne le PDF print-ready (PDF/X-1a:2001) + download_url

    Le débit de crédits se fait sur la compagnie de la clé API.
    """
    from core.auth import TokenData
    from modules.bureau import mediatheque_session as msm
    from modules.bureau.infographe_pro import generer_projet
    from modules.bureau import gabarits_livret as catalog_multi
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )
    from api.routes_bureau_infographie_pro import (
        DemandeOrchestrer, orchestrer as _orch_internal,
    )

    fake_user = TokenData(
        user_id=identity.user_id, user_nom=f"api:{identity.label}",
        role="agent", compagnie_id=identity.compagnie_id,
    )

    autorise, plan, msg = await verifier_acces_module(identity.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(identity.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    # 1. Détecter cle_projet si absent
    cle_projet = req.cle_projet
    if not cle_projet:
        try:
            orch = await _orch_internal(
                DemandeOrchestrer(prompt=req.prompt, pays=req.pays, langue=req.langue),
                fake_user,
            )
            cle_projet = orch.cle_projet
        except Exception as e:
            raise HTTPException(500, f"Auto-detection échouée : {e}")
    if cle_projet not in catalog_multi.PROJETS_INFOGRAPHIE:
        raise HTTPException(400, f"cle_projet '{cle_projet}' inconnue (multi-page seulement). Voir /catalogue.")

    # 2. Upload images_b64 → médias session
    medias_refs: list[str] = []
    session_id = f"api_{identity.key_id}"
    if req.images_b64:
        for i, b64 in enumerate(req.images_b64[:30]):
            try:
                contenu = base64.b64decode(b64)
                m = msm.ajouter_media(
                    portee="session", owner_id=session_id, contenu=contenu,
                    nom_fichier=f"api_image_{i}.png", mime="image/png",
                    categorie="photo", label=f"API upload {i}",
                )
                medias_refs.append(f"session:{m.media_id}")
            except Exception as e:
                logger.warning(f"[public/generate] image_b64 #{i} ignorée : {e}")

    # 3. Profil client
    profil = None
    if req.nom_organisation or req.couleur_primaire_hex:
        profil = {
            "nom_organisation": req.nom_organisation,
            "couleur_primaire_hex": req.couleur_primaire_hex,
        }

    # 4. Génération
    try:
        resultat = await generer_projet(
            brief=req.prompt, cle_projet=cle_projet,
            user_id=str(identity.user_id), session_id=session_id,
            medias_refs=medias_refs, pays=req.pays, profil=profil,
            langue=req.langue, export_cmyk=True,
            mode_visuel=req.mode_visuel,
        )
    except Exception as e:
        logger.error(f"[public/generate] Génération échouée : {e}")
        raise HTTPException(500, f"Génération échouée : {e}")

    # 5. Débits crédits (LLM + forfaits comme la route interne)
    cout_total = 0.0
    try:
        meta = resultat.meta or {}
        if meta.get("tokens_input") or meta.get("tokens_output"):
            _, dbt, _ = await debiter_llm(
                identity.user_id, modele=meta.get("modele", "default"),
                tokens_input=int(meta.get("tokens_input") or 0),
                tokens_output=int(meta.get("tokens_output") or 0),
                module="infographie",
            )
            cout_total += dbt
        if resultat.pdf_bytes:
            nb_pages = int(meta.get("nb_pages") or meta.get("nombre_pages") or 1)
            _, dbt, _ = await debiter_forfait(
                identity.user_id, "designerpro_creation",
                module="infographie", multiplicateur=max(1.0, float(nb_pages)),
            )
            cout_total += dbt
        nb_imgs = int(meta.get("nb_images_ia") or 0)
        if nb_imgs > 0:
            forfait = {
                "ultra_plus": "designerpro_image_ultra_plus",
                "ultra": "designerpro_image_ultra",
                "premium": "designerpro_image_premium",
            }.get(req.mode_visuel, "designerpro_image_standard")
            _, dbt, _ = await debiter_forfait(
                identity.user_id, forfait, module="infographie",
                multiplicateur=float(nb_imgs),
            )
            cout_total += dbt
    except Exception as e:
        logger.warning(f"[public/generate] Crédits : {e}")

    # 6. Récupère les rate limit headers depuis state pour les inclure dans la réponse
    return PublicGenererResponse(
        ok=True,
        cle_projet=cle_projet,
        titre=(resultat.projet.titre if resultat.projet else cle_projet) or cle_projet,
        nombre_pages=(resultat.meta or {}).get("nombre_pages") or 0,
        pdf_base64=base64.b64encode(resultat.pdf_bytes).decode("ascii") if resultat.pdf_bytes else None,
        print_ready_pdf_base64=base64.b64encode(resultat.pdf_cmyk_bytes).decode("ascii") if resultat.pdf_cmyk_bytes else None,
        cout_credits=round(cout_total, 1),
        rate_limit_remaining_hour=identity.rate_limit_per_hour,
        rate_limit_remaining_day=identity.rate_limit_per_day,
    )


@router.get("/me", tags=["Public API — Designer Pro"])
async def public_me(identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    """Info sur la clé API utilisée (pour debug intégration)."""
    return {
        "key_id": identity.key_id, "label": identity.label,
        "compagnie_id": identity.compagnie_id, "scopes": identity.scopes,
        "rate_limit_per_hour": identity.rate_limit_per_hour,
        "rate_limit_per_day": identity.rate_limit_per_day,
    }
