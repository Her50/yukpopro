"""
Sec — Génération de slides PPTX (port du SlideBuilderPro).

Avant : génération de slides exclusivement côté Pro. Sec n'avait pas de
slides → un secrétaire/infographiste devait basculer côté Pro pour
produire un pitch deck ou un programme de réunion en PPTX.

Maintenant : Sec expose `/bureau/slides/generer` qui réutilise la même
classe SlideBuilderPro (logo cover, footer org, charts natifs PowerPoint,
notes orateur, 4 thèmes visuels) avec un adapter qui convertit le profil
secrétariat en profil compatible.

Pas de duplication de code : la logique reste dans modules.pro.slide_builder_pro
(source unique de vérité Pro+Sec).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData
from core.database import get_db

router = APIRouter()
logger = logging.getLogger("yukpo_assurance.routes_bureau_slides")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


class DemandeSlidesSec(BaseModel):
    sujet: str = Field(..., min_length=5, max_length=3000)
    type_pres: str = Field("rapport_direction",
                            description="bilan_activite | proposition_client | "
                                        "rapport_direction | formation | "
                                        "pitch_projet | analyse_marche | rapport_financier")
    mode: str = Field("executive", description="executive | detaille | pitch")
    contexte: Optional[str] = Field(None, max_length=2000)
    donnees: Optional[dict] = None
    format_sortie: str = Field("pptx", description="pptx | markdown")


class _ProfilAdapter:
    """Adapter minimal : convertit un profil bureau Sec (ou utilisateur basique)
    en interface attendue par SlideBuilderPro (nom_organisation, metier, pays,
    nom, couleur_primaire_hex, logo_b64). Tous les attrs sont optionnels — les
    helpers SlideBuilderPro utilisent getattr(..., None) avec fallbacks."""

    def __init__(self, user_id: int, db: AsyncSession):
        self._user_id = user_id
        self._db = db
        self.nom_organisation = ""
        self.entreprise = ""
        self.metier = "Secrétariat"
        self.pays = "CM"
        self.nom = ""
        self.nom_complet = ""
        self.user_nom = ""
        self.couleur_primaire_hex = ""
        self.logo_b64 = None
        self.logo_base64 = None

    async def hydrater(self) -> "_ProfilAdapter":
        """Charge depuis DB les champs utiles à l'identité PPTX."""
        try:
            from core.database import UtilisateurDB
            from sqlalchemy import select as _sel
            u = (await self._db.execute(
                _sel(UtilisateurDB).where(UtilisateurDB.id == self._user_id)
            )).scalars().first()
            if u:
                self.nom = getattr(u, "nom", "") or ""
                self.nom_complet = self.nom
                self.user_nom = self.nom
                self.pays = (getattr(u, "pays", None) or "CM").upper()
                # Org / branding éventuels (selon ce que Sec stocke)
                self.nom_organisation = (
                    getattr(u, "nom_organisation", None)
                    or getattr(u, "entreprise", None)
                    or ""
                )
                self.entreprise = self.nom_organisation
                self.couleur_primaire_hex = (
                    getattr(u, "couleur_primaire_hex", None) or ""
                )
                self.logo_b64 = (
                    getattr(u, "logo_b64", None)
                    or getattr(u, "logo_base64", None)
                )
        except Exception as e:
            logger.debug(f"[BureauSlides] Hydratation profil: {e}")
        # BrandKit org (Sprint 2.4) — auto-héritage si compagnie_id dispo
        try:
            from api.routes_brand_kit import charger_overrides_brand_kit
            from core.database import UtilisateurDB as _UDB
            from sqlalchemy import select as _sel
            u2 = (await self._db.execute(
                _sel(_UDB).where(_UDB.id == self._user_id)
            )).scalars().first()
            cid = getattr(u2, "compagnie_id", None) if u2 else None
            if cid:
                bk = await charger_overrides_brand_kit(int(cid))
                if isinstance(bk, dict):
                    if not self.couleur_primaire_hex and bk.get("couleur_primaire_hex"):
                        self.couleur_primaire_hex = bk["couleur_primaire_hex"]
                    if not self.logo_b64 and (bk.get("logo_b64") or bk.get("logo")):
                        self.logo_b64 = bk.get("logo_b64") or bk.get("logo")
        except Exception:
            pass
        return self


@router.post("/generer", tags=["Bureau — Slides"])
async def generer_slides_sec(
    demande: DemandeSlidesSec,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Génère un PPTX avec le SlideBuilderPro côté Sec.
    Crédits : forfait `redaction` (déjà dispo) + LLM tokens via debiter_llm."""
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm,
    )
    from modules.pro.slide_builder_pro import SlideBuilderPro

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "redaction")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    profil = await _ProfilAdapter(current_user.user_id, db).hydrater()
    builder = SlideBuilderPro(profil=profil)

    _TIMEOUT = {"executive": 180, "detaille": 360, "pitch": 240, "expert": 540}
    tmo = _TIMEOUT.get(demande.mode, 240)
    try:
        resultat = await asyncio.wait_for(
            builder.generer(
                sujet=demande.sujet,
                type_pres=demande.type_pres,
                mode=demande.mode,
                contexte=demande.contexte,
                donnees=demande.donnees,
                format_sortie=demande.format_sortie,
            ),
            timeout=tmo,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, f"Génération slides trop longue (> {tmo}s)")
    except Exception as e:
        logger.error(f"[BureauSlides] user={current_user.user_id}: {e}")
        raise HTTPException(500, f"Génération échouée : {str(e)[:200]}")

    # Débit LLM (estimation conservative — SlideBuilderPro fait plusieurs appels)
    try:
        await debiter_llm(
            current_user.user_id,
            modele="default",
            tokens_input=2000,
            tokens_output=2500,
            module="redaction",
        )
    except Exception:
        pass

    nom_fich = Path(resultat.get("chemin_fichier") or "").name if resultat.get("chemin_fichier") else None
    if nom_fich:
        # On reroute vers l'endpoint Pro de download de fichier (déjà sécurisé)
        resultat["url_telechargement"] = f"/api/v1/pro/generateurs/fichier/{nom_fich}"
        resultat["fichier"] = nom_fich
    if "contenu_markdown" in resultat and "markdown" not in resultat:
        resultat["markdown"] = resultat["contenu_markdown"]
    return resultat
