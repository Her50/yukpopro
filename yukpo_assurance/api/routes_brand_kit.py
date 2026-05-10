"""
Sprint 2.4 — Brand Kit verrouillé par organisation.

Endpoints (JWT — admin org typiquement) :
  GET    /                  → récupère le brand kit de l'org
  PUT    /                  → upsert (création ou mise à jour complète)
  PATCH  /                  → modifie partiellement
  DELETE /                  → désactive (actif=False, garde l'historique)
  POST   /check             → brand compliance check d'un PDF/image généré (vision Sonnet)
  GET    /apply-preview     → renvoie le profil/directives qui seront appliqués à la prochaine
                              génération (pour debug UI)

Le pipeline `infographe_pro.generer_projet` consulte automatiquement le
brand kit de l'org de l'utilisateur via helper `apply_brand_kit_overrides()` :
  - profil.couleur_primaire_hex ← brand_kit.couleur_primaire_hex (si user n'override pas)
  - profil.nom_organisation ← brand_kit.nom_organisation
  - polices titre/corps ← brand_kit.font_titre/corps
  - brand_lora_id ← brand_kit.brand_lora_id_defaut
  - prompt enrichi avec ToV + lexique préféré + mots interdits

Strictness :
  0-30  : suggestion pure (l'IA peut ignorer si ça améliore l'output)
  31-70 : recommandation forte (l'IA respecte sauf incohérence majeure)
  71-100: verrou strict (l'IA DOIT respecter — rejet immédiat sinon)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.brand_kit")
router = APIRouter()


class BrandKitUpsert(BaseModel):
    label: Optional[str] = Field(default="Charte officielle", max_length=120)
    couleur_primaire_hex: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    couleur_secondaire_hex: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    couleur_accent_hex: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    couleurs_extras_hex: list[str] = Field(default_factory=list)
    font_titre: str = Field(default="Inter", max_length=80)
    font_corps: str = Field(default="Inter", max_length=80)
    font_accent: Optional[str] = Field(default=None, max_length=80)
    logo_media_ref: Optional[str] = Field(default=None, max_length=120,
        description="Réf média 'compte:xxx' catégorie 'logo'")
    nom_organisation: Optional[str] = Field(default=None, max_length=200)
    baseline: Optional[str] = Field(default=None, max_length=300)
    tone_of_voice: Optional[str] = None
    lexique_prefere: list[str] = Field(default_factory=list)
    mots_interdits: list[str] = Field(default_factory=list)
    brand_lora_id_defaut: Optional[str] = Field(default=None, max_length=36)
    strictness: int = Field(default=70, ge=0, le=100)


class BrandKitResponse(BaseModel):
    kit_id: str
    compagnie_id: int
    label: str
    actif: bool
    couleur_primaire_hex: Optional[str]
    couleur_secondaire_hex: Optional[str]
    couleur_accent_hex: Optional[str]
    couleurs_extras_hex: list[str]
    font_titre: str
    font_corps: str
    font_accent: Optional[str]
    logo_media_ref: Optional[str]
    nom_organisation: Optional[str]
    baseline: Optional[str]
    tone_of_voice: Optional[str]
    lexique_prefere: list[str]
    mots_interdits: list[str]
    brand_lora_id_defaut: Optional[str]
    strictness: int
    cree_le: str
    modifie_le: str


def _row_to_response(row) -> BrandKitResponse:
    return BrandKitResponse(
        kit_id=row.kit_id, compagnie_id=row.compagnie_id, label=row.label, actif=row.actif,
        couleur_primaire_hex=row.couleur_primaire_hex,
        couleur_secondaire_hex=row.couleur_secondaire_hex,
        couleur_accent_hex=row.couleur_accent_hex,
        couleurs_extras_hex=row.couleurs_extras_hex or [],
        font_titre=row.font_titre, font_corps=row.font_corps, font_accent=row.font_accent,
        logo_media_ref=row.logo_media_ref, nom_organisation=row.nom_organisation,
        baseline=row.baseline, tone_of_voice=row.tone_of_voice,
        lexique_prefere=row.lexique_prefere or [],
        mots_interdits=row.mots_interdits or [],
        brand_lora_id_defaut=row.brand_lora_id_defaut,
        strictness=row.strictness or 70,
        cree_le=row.cree_le.isoformat(),
        modifie_le=row.modifie_le.isoformat() if row.modifie_le else row.cree_le.isoformat(),
    )


@router.get("", response_model=Optional[BrandKitResponse], tags=["Brand Kit"])
async def get_brand_kit(current_user: TokenData = Depends(get_current_user)):
    """Brand kit actif de l'org (None si jamais configuré)."""
    from core.database import async_session_maker, BrandKitDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(BrandKitDB).where(
                BrandKitDB.compagnie_id == cid, BrandKitDB.actif == True  # noqa
            )
        )).scalar_one_or_none()
    return _row_to_response(row) if row else None


@router.put("", response_model=BrandKitResponse, tags=["Brand Kit"])
async def upsert_brand_kit(
    demande: BrandKitUpsert, current_user: TokenData = Depends(get_current_user),
):
    """Upsert le brand kit de l'org (création ou remplacement complet)."""
    from core.database import async_session_maker, BrandKitDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(BrandKitDB).where(BrandKitDB.compagnie_id == cid)
        )).scalar_one_or_none()
        if row:
            row.label = demande.label or "Charte officielle"
            row.actif = True
            row.couleur_primaire_hex = demande.couleur_primaire_hex
            row.couleur_secondaire_hex = demande.couleur_secondaire_hex
            row.couleur_accent_hex = demande.couleur_accent_hex
            row.couleurs_extras_hex = demande.couleurs_extras_hex
            row.font_titre = demande.font_titre
            row.font_corps = demande.font_corps
            row.font_accent = demande.font_accent
            row.logo_media_ref = demande.logo_media_ref
            row.nom_organisation = demande.nom_organisation
            row.baseline = demande.baseline
            row.tone_of_voice = demande.tone_of_voice
            row.lexique_prefere = demande.lexique_prefere
            row.mots_interdits = demande.mots_interdits
            row.brand_lora_id_defaut = demande.brand_lora_id_defaut
            row.strictness = demande.strictness
            row.modifie_le = datetime.utcnow()
        else:
            row = BrandKitDB(
                kit_id=str(uuid.uuid4()), compagnie_id=cid, actif=True,
                label=demande.label or "Charte officielle",
                couleur_primaire_hex=demande.couleur_primaire_hex,
                couleur_secondaire_hex=demande.couleur_secondaire_hex,
                couleur_accent_hex=demande.couleur_accent_hex,
                couleurs_extras_hex=demande.couleurs_extras_hex,
                font_titre=demande.font_titre, font_corps=demande.font_corps,
                font_accent=demande.font_accent,
                logo_media_ref=demande.logo_media_ref,
                nom_organisation=demande.nom_organisation,
                baseline=demande.baseline,
                tone_of_voice=demande.tone_of_voice,
                lexique_prefere=demande.lexique_prefere,
                mots_interdits=demande.mots_interdits,
                brand_lora_id_defaut=demande.brand_lora_id_defaut,
                strictness=demande.strictness,
            )
            db.add(row)
        await db.commit()
        await db.refresh(row)
    logger.info(f"[BrandKit] Upsert compagnie={cid} kit={row.kit_id}")
    return _row_to_response(row)


@router.delete("", tags=["Brand Kit"])
async def disable_brand_kit(current_user: TokenData = Depends(get_current_user)):
    """Désactive le brand kit (actif=False, on garde la row pour audit)."""
    from core.database import async_session_maker, BrandKitDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(BrandKitDB).where(BrandKitDB.compagnie_id == cid)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Aucun brand kit configuré")
        row.actif = False
        row.modifie_le = datetime.utcnow()
        await db.commit()
    return {"ok": True, "compagnie_id": cid, "actif": False}


@router.get("/apply-preview", tags=["Brand Kit"])
async def preview_overrides(current_user: TokenData = Depends(get_current_user)):
    """Renvoie le profil/directives qui seront appliqués automatiquement
    à la prochaine génération Designer Pro de cet user (debug UI)."""
    overrides = await charger_overrides_brand_kit(getattr(current_user, "compagnie_id", None) or 1)
    return {"compagnie_id": current_user.compagnie_id, **overrides}


class BrandComplianceCheck(BaseModel):
    """Demande de vérification d'un visuel généré contre le brand kit."""
    image_b64: str = Field(..., description="PNG/JPEG du visuel à vérifier (base64)")


@router.post("/check", tags=["Brand Kit"])
async def brand_compliance_check(
    demande: BrandComplianceCheck,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Brand compliance checker via Sonnet vision : note (0-100) le respect de
    la charte sur palette/logo/ToV. Renvoie warnings actionnables.
    """
    from core.database import async_session_maker, BrandKitDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        kit = (await db.execute(
            select(BrandKitDB).where(
                BrandKitDB.compagnie_id == cid, BrandKitDB.actif == True  # noqa
            )
        )).scalar_one_or_none()
    if not kit:
        raise HTTPException(404, "Aucun brand kit actif. Configure-le d'abord via PUT /brand-kit.")
    try:
        from core.ia_client import ia_client, ModelePrioritaire
        prompt = (
            f"Tu es BRAND COMPLIANCE OFFICER pour {kit.nom_organisation or 'cette org'}.\n"
            f"Vérifie que le visuel respecte la CHARTE OFFICIELLE :\n"
            f"  - Palette : primaire={kit.couleur_primaire_hex} / secondaire={kit.couleur_secondaire_hex} / accent={kit.couleur_accent_hex}\n"
            f"  - Polices titre={kit.font_titre} / corps={kit.font_corps}\n"
            f"  - Baseline : {kit.baseline or '(aucune)'}\n"
            f"  - Tone of voice : {kit.tone_of_voice or '(aucun)'}\n"
            f"  - Lexique préféré : {kit.lexique_prefere or []}\n"
            f"  - Mots interdits  : {kit.mots_interdits or []}\n"
            f"  - Strictness : {kit.strictness}/100\n\n"
            f"Note sur 100 le respect de la charte. Liste 0-5 warnings actionnables.\n"
            f"Format JSON STRICT :\n"
            f"{{\"score\": 85, \"verdict\": \"compliant|warning|non_compliant\",\n"
            f" \"warnings\": [\"...\"], \"raison\": \"...\"}}\n\n"
            f"Retourne UNIQUEMENT le JSON."
        )
        rep = await ia_client.appeler(
            prompt=prompt, json_attendu=True,
            forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
            images_b64=[demande.image_b64],
        )
        import json as _json
        try:
            data = _json.loads(rep.contenu)
        except Exception:
            import re as _re
            m = _re.search(r'\{.*\}', rep.contenu, _re.DOTALL)
            data = _json.loads(m.group()) if m else {"score": 0, "verdict": "non_compliant",
                                                       "warnings": ["LLM JSON invalid"], "raison": ""}
        return {"ok": True, "kit_id": kit.kit_id, **data}
    except Exception as e:
        logger.error(f"[BrandKit/check] {e}")
        raise HTTPException(500, f"Compliance check échoué : {e}")


# ─── Helper appliqué dans le pipeline de génération ──────────────────────────


async def charger_overrides_brand_kit(compagnie_id: int) -> dict:
    """
    Helper interne : retourne les overrides à appliquer à un appel
    `generer_projet` (profil + directives + brand_lora_id).
    Appelé par routes_bureau_infographie_pro.generer_projet.
    """
    from core.database import async_session_maker, BrandKitDB
    async with async_session_maker() as db:
        kit = (await db.execute(
            select(BrandKitDB).where(
                BrandKitDB.compagnie_id == compagnie_id, BrandKitDB.actif == True  # noqa
            )
        )).scalar_one_or_none()
    if not kit:
        return {"brand_kit_active": False}
    profil_overrides = {
        "nom_organisation": kit.nom_organisation,
        "couleur_primaire_hex": kit.couleur_primaire_hex,
        "couleurs_accents_hex": [c for c in [kit.couleur_secondaire_hex, kit.couleur_accent_hex,
                                              *(kit.couleurs_extras_hex or [])] if c],
    }
    polices_overrides = {"titre": kit.font_titre, "corps": kit.font_corps}
    directives_brand = {
        "tone_of_voice": kit.tone_of_voice,
        "lexique_prefere": kit.lexique_prefere or [],
        "mots_interdits": kit.mots_interdits or [],
        "baseline": kit.baseline,
        "strictness": kit.strictness or 70,
    }
    return {
        "brand_kit_active": True,
        "kit_id": kit.kit_id,
        "profil_overrides": profil_overrides,
        "polices_overrides": polices_overrides,
        "directives_brand": directives_brand,
        "brand_lora_id_defaut": kit.brand_lora_id_defaut,
        "logo_media_ref": kit.logo_media_ref,
    }
