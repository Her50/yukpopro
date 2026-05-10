"""
Sprint 2.2 — Endpoints SAML SSO.

Public (initié par utilisateur depuis frontend SSO button) :
  GET  /saml/login?compagnie_id=X     → redirige vers IdP avec SAMLRequest
  POST /saml/acs?compagnie_id=X       → callback ACS, valide assertion, mint JWT, redirect
  GET  /saml/metadata?compagnie_id=X  → notre SP metadata XML (à donner à l'IdP)

Admin org (JWT requis) :
  GET    /admin/saml/config            → config SAML actuelle de l'org
  POST   /admin/saml/parse-metadata    → parse XML metadata IdP collé
  PUT    /admin/saml/config            → upsert config SAML
  DELETE /admin/saml/config            → désactive SSO

Tous les endpoints retournent 503 si python3-saml n'est pas installé
(env Windows local). En prod Linux : opérationnel.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.saml_sso")
router = APIRouter()


# ─── Modèles ──────────────────────────────────────────────────────────────────


class SamlConfigUpsert(BaseModel):
    idp_metadata_xml: Optional[str] = Field(default=None,
        description="XML metadata complet de l'IdP. Si fourni, parse auto pour entity/SSO/cert.")
    idp_entity_id: Optional[str] = None
    idp_sso_url: Optional[str] = None
    idp_x509_cert: Optional[str] = None
    sp_entity_id: str = Field(..., description="Notre URL canonique d'app (ex: https://app.yukpomnang.com)")
    sp_acs_url: str = Field(..., description="Notre ACS URL (ex: https://yukpopro-backend.fly.dev/api/v1/saml/acs)")
    attr_email: str = Field(default="email")
    attr_nom: str = Field(default="displayName")
    attr_role: str = Field(default="role")
    role_par_defaut: str = Field(default="agent")
    auto_provision: bool = Field(default=True)


class SamlConfigResponse(BaseModel):
    config_id: str
    compagnie_id: int
    actif: bool
    idp_entity_id: str
    idp_sso_url: str
    sp_entity_id: str
    sp_acs_url: str
    attr_email: str
    attr_nom: str
    attr_role: str
    role_par_defaut: str
    auto_provision: bool
    cree_le: str
    modifie_le: str


def _row_to_response(row) -> SamlConfigResponse:
    return SamlConfigResponse(
        config_id=row.config_id, compagnie_id=row.compagnie_id, actif=row.actif,
        idp_entity_id=row.idp_entity_id, idp_sso_url=row.idp_sso_url,
        sp_entity_id=row.sp_entity_id, sp_acs_url=row.sp_acs_url,
        attr_email=row.attr_email, attr_nom=row.attr_nom, attr_role=row.attr_role,
        role_par_defaut=row.role_par_defaut, auto_provision=row.auto_provision,
        cree_le=row.cree_le.isoformat(),
        modifie_le=row.modifie_le.isoformat() if row.modifie_le else row.cree_le.isoformat(),
    )


# ─── Endpoints PUBLICS — flow SSO ─────────────────────────────────────────────


@router.get("/login", tags=["SAML SSO"])
async def saml_login(compagnie_id: int, request: Request):
    """Redirige vers l'IdP avec un SAMLRequest signé."""
    from core import saml_sso as sso
    if not sso.is_available():
        raise HTTPException(503, "SAML non disponible sur ce déploiement.")
    from core.database import async_session_maker, SamlConfigDB
    async with async_session_maker() as db:
        cfg = (await db.execute(
            select(SamlConfigDB).where(
                SamlConfigDB.compagnie_id == compagnie_id, SamlConfigDB.actif == True  # noqa
            )
        )).scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, f"SAML non configuré pour compagnie {compagnie_id}")
    auth = await sso.init_auth(request, cfg)
    sso_url = auth.login()
    return RedirectResponse(url=sso_url, status_code=302)


@router.post("/acs", tags=["SAML SSO"])
async def saml_acs(compagnie_id: int, request: Request, response: Response):
    """
    Assertion Consumer Service : reçoit l'assertion signée de l'IdP, valide,
    extrait les attributs, mint un JWT YukpoPro, redirige vers le frontend.
    """
    from core import saml_sso as sso
    if not sso.is_available():
        raise HTTPException(503, "SAML non disponible.")
    from core.database import async_session_maker, SamlConfigDB, UtilisateurDB
    from core.auth import creer_token as _creer_jwt
    from datetime import datetime as _dt

    async with async_session_maker() as db:
        cfg = (await db.execute(
            select(SamlConfigDB).where(
                SamlConfigDB.compagnie_id == compagnie_id, SamlConfigDB.actif == True  # noqa
            )
        )).scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, "SAML non configuré")

        auth = await sso.init_auth(request, cfg)
        auth.process_response()
        errors = auth.get_errors()
        if errors:
            err_msg = ", ".join(errors)
            logger.warning(f"[SAML] assertion errors compagnie={compagnie_id} : {err_msg}")
            raise HTTPException(401, f"Assertion SAML invalide : {err_msg}")
        if not auth.is_authenticated():
            raise HTTPException(401, "Authentification SAML échouée")

        # Extract attrs
        attrs = auth.get_attributes() or {}
        nameid = auth.get_nameid()  # typiquement l'email
        email = (attrs.get(cfg.attr_email) or [nameid])[0] if attrs.get(cfg.attr_email) else nameid
        nom = (attrs.get(cfg.attr_nom) or [email])[0] if attrs.get(cfg.attr_nom) else email
        role = (attrs.get(cfg.attr_role) or [cfg.role_par_defaut])[0] if attrs.get(cfg.attr_role) else cfg.role_par_defaut

        if not email:
            raise HTTPException(400, "Email absent de l'assertion SAML")

        # Trouve ou provisionne l'utilisateur
        user = (await db.execute(
            select(UtilisateurDB).where(UtilisateurDB.email == email)
        )).scalar_one_or_none()
        if not user:
            if not cfg.auto_provision:
                raise HTTPException(403, f"Utilisateur {email} inconnu (auto-provision désactivé)")
            user = UtilisateurDB(
                email=email, nom=nom or email.split("@")[0],
                role=role or "agent",
                compagnie_id=compagnie_id,
                mot_de_passe_hash="!SSO!",  # marqueur : login via SSO uniquement
                actif=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"[SAML] auto-provisioned user email={email} compagnie={compagnie_id}")
        else:
            # MAJ role si l'IdP source de vérité
            if role and user.role != role:
                user.role = role
                await db.commit()

    # Mint JWT
    token = _creer_jwt(
        user_id=user.user_id, user_nom=user.nom, role=user.role,
        compagnie_id=user.compagnie_id,
    )

    # Set cookie + redirect vers frontend dashboard
    redirect_url = "https://yukpopro.yukpomnang.com/?sso=ok"
    resp = RedirectResponse(url=redirect_url, status_code=303)
    resp.set_cookie(
        key="auth_token", value=f"Bearer {token}",
        httponly=True, secure=True, samesite="lax",
        max_age=int(timedelta(days=7).total_seconds()),
    )
    return resp


@router.get("/metadata", tags=["SAML SSO"])
async def saml_sp_metadata(compagnie_id: int):
    """SP metadata XML — à fournir à l'IdP lors de la configuration."""
    from core import saml_sso as sso
    if not sso.is_available():
        raise HTTPException(503, "SAML non disponible.")
    from core.database import async_session_maker, SamlConfigDB
    from onelogin.saml2.settings import OneLogin_Saml2_Settings

    async with async_session_maker() as db:
        cfg = (await db.execute(
            select(SamlConfigDB).where(SamlConfigDB.compagnie_id == compagnie_id)
        )).scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, "SAML non configuré pour cette compagnie")
    settings_obj = OneLogin_Saml2_Settings(
        sso._build_settings_dict(cfg), sp_validation_only=True,
    )
    metadata = settings_obj.get_sp_metadata()
    errors = settings_obj.validate_metadata(metadata)
    if errors:
        raise HTTPException(500, f"Metadata SP invalide : {errors}")
    return PlainTextResponse(content=metadata, media_type="application/xml")


# ─── Endpoints ADMIN org (JWT) ────────────────────────────────────────────────


@router.get("/admin/config", response_model=Optional[SamlConfigResponse], tags=["SAML SSO Admin"])
async def admin_get_config(current_user: TokenData = Depends(get_current_user)):
    """Retourne la config SAML actuelle de l'org (ou null)."""
    from core.database import async_session_maker, SamlConfigDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        cfg = (await db.execute(
            select(SamlConfigDB).where(SamlConfigDB.compagnie_id == cid)
        )).scalar_one_or_none()
    return _row_to_response(cfg) if cfg else None


@router.post("/admin/parse-metadata", tags=["SAML SSO Admin"])
async def admin_parse_metadata(
    payload: dict, current_user: TokenData = Depends(get_current_user),
):
    """Parse un metadata IdP collé → extrait entity_id/sso_url/x509_cert."""
    from core import saml_sso as sso
    if not sso.is_available():
        raise HTTPException(503, "SAML non disponible.")
    xml = (payload or {}).get("xml", "")
    if not xml or len(xml) < 100:
        raise HTTPException(400, "XML metadata manquant ou trop court")
    try:
        parsed = sso.parse_idp_metadata(xml)
        return parsed
    except Exception as e:
        raise HTTPException(400, f"Parse échoué : {e}")


@router.put("/admin/config", response_model=SamlConfigResponse, tags=["SAML SSO Admin"])
async def admin_upsert_config(
    demande: SamlConfigUpsert, current_user: TokenData = Depends(get_current_user),
):
    """Upsert la config SAML de l'org. Si idp_metadata_xml fourni → parse auto."""
    from core import saml_sso as sso
    if not sso.is_available():
        raise HTTPException(503, "SAML non disponible.")
    from core.database import async_session_maker, SamlConfigDB
    cid = getattr(current_user, "compagnie_id", None) or 1

    # Si XML fourni, on extrait
    entity_id = demande.idp_entity_id
    sso_url = demande.idp_sso_url
    cert = demande.idp_x509_cert
    if demande.idp_metadata_xml and (not entity_id or not sso_url or not cert):
        try:
            parsed = sso.parse_idp_metadata(demande.idp_metadata_xml)
            entity_id = entity_id or parsed["entity_id"]
            sso_url = sso_url or parsed["sso_url"]
            cert = cert or parsed["x509_cert"]
        except Exception as e:
            raise HTTPException(400, f"Parse XML métadata échoué : {e}")

    if not (entity_id and sso_url and cert):
        raise HTTPException(400, "idp_entity_id, idp_sso_url et idp_x509_cert tous requis (directement ou via idp_metadata_xml)")

    async with async_session_maker() as db:
        cfg = (await db.execute(
            select(SamlConfigDB).where(SamlConfigDB.compagnie_id == cid)
        )).scalar_one_or_none()
        if cfg:
            cfg.idp_metadata_xml = demande.idp_metadata_xml or cfg.idp_metadata_xml
            cfg.idp_entity_id = entity_id
            cfg.idp_sso_url = sso_url
            cfg.idp_x509_cert = cert
            cfg.sp_entity_id = demande.sp_entity_id
            cfg.sp_acs_url = demande.sp_acs_url
            cfg.attr_email = demande.attr_email
            cfg.attr_nom = demande.attr_nom
            cfg.attr_role = demande.attr_role
            cfg.role_par_defaut = demande.role_par_defaut
            cfg.auto_provision = demande.auto_provision
            cfg.actif = True
            cfg.modifie_le = datetime.utcnow()
        else:
            cfg = SamlConfigDB(
                config_id=str(uuid.uuid4()), compagnie_id=cid, actif=True,
                idp_metadata_xml=demande.idp_metadata_xml or "",
                idp_entity_id=entity_id, idp_sso_url=sso_url, idp_x509_cert=cert,
                sp_entity_id=demande.sp_entity_id, sp_acs_url=demande.sp_acs_url,
                attr_email=demande.attr_email, attr_nom=demande.attr_nom,
                attr_role=demande.attr_role, role_par_defaut=demande.role_par_defaut,
                auto_provision=demande.auto_provision,
            )
            db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return _row_to_response(cfg)


@router.delete("/admin/config", tags=["SAML SSO Admin"])
async def admin_disable_config(current_user: TokenData = Depends(get_current_user)):
    """Désactive le SAML pour l'org (actif=False, on garde la row pour audit)."""
    from core.database import async_session_maker, SamlConfigDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        cfg = (await db.execute(
            select(SamlConfigDB).where(SamlConfigDB.compagnie_id == cid)
        )).scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, "Config SAML inexistante")
        cfg.actif = False
        cfg.modifie_le = datetime.utcnow()
        await db.commit()
    return {"ok": True, "compagnie_id": cid, "actif": False}
