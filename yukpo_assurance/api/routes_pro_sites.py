"""Routes Mini-sites multi-pages (Phase C).

Endpoints (tous sous /api/v1/pro/sites) :

  POST   /sites/generer            : génère un site complet via LLM
  GET    /sites                    : liste sites du user
  GET    /sites/{slug}             : détail + liste pages
  POST   /sites/{slug}/publier     : déploie sur Netlify (multi-fichiers)
  PATCH  /sites/{slug}/pages/{type}: modifie une page via LLM
  POST   /sites/{slug}/articles    : génère un article de blog
  GET    /sites/{slug}/articles    : liste les articles
  PATCH  /sites/{slug}/articles/{slug_article}: maj article (publier, programmer)
  DELETE /sites/{slug}             : supprime le site (DB + Netlify)

Tous les endpoints sont AUTHENTIFIÉS (ownership vérifié sur user_id).
Facturation : pré-check + CostAdvisor + débit forfait existant
(`pdf_generation` pour publish, `docx_generation` pour génération, etc.).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import (
    SiteArticleDB, SiteDB, SitePageDB, async_session_maker,
)

logger = logging.getLogger("yukpo_assurance.api.pro_sites")

router = APIRouter()


async def _get_db():
    async with async_session_maker() as session:
        yield session


# ─── Schemas ──────────────────────────────────────────────────────────────────

class GenererSiteRequest(BaseModel):
    brief: str = Field(..., min_length=10, max_length=3000,
        description="Brief utilisateur (ex: 'cabinet d'expertise comptable à Douala')")
    types_pages: Optional[list[str]] = Field(
        default=None,
        description="Pages à composer. Défaut : home, services, equipe, blog_index, "
                    "contact, mentions_legales, confidentialite",
    )
    langue: str = Field("fr", max_length=8)
    cible: Optional[str] = Field(None, max_length=600)
    ton: Optional[str] = Field(None, max_length=200)
    brand_kit: Optional[dict] = Field(default=None)
    generer_images: bool = Field(default=True)
    confirmer_cout: bool = Field(default=False,
        description="Set par frontend après confirmation modale CostAdvisor")


class PublierSiteRequest(BaseModel):
    plan: str = Field("free", pattern=r"^(free|pro|business)$")
    confirmer_cout: bool = Field(default=False)


class PatchPageRequest(BaseModel):
    instructions: str = Field(..., min_length=5, max_length=2000,
        description="Instructions de modification en langage naturel")
    confirmer_cout: bool = Field(default=False)


class GenererArticleRequest(BaseModel):
    sujet: str = Field(..., min_length=10, max_length=600)
    auteur: Optional[str] = Field(None, max_length=120)
    langue: str = Field("fr", max_length=8)
    cible: Optional[str] = Field(None, max_length=400)
    ton: Optional[str] = Field(None, max_length=200)
    publier_immediatement: bool = Field(default=False)
    publier_dans_jours: Optional[int] = Field(
        None, ge=0, le=365,
        description="Si fourni, publication programmée dans N jours")
    confirmer_cout: bool = Field(default=False)


# ─── Helpers ──────────────────────────────────────────────────────────────────

_SLUGS_RESERVES = {
    "www", "api", "app", "admin", "support", "docs", "blog",
    "yukpo", "yukpopro", "yukposec", "yukposecretariat",
    "mail", "smtp", "ftp", "cdn", "static", "assets", "img",
    "test", "staging", "prod", "production", "dev",
}


def _slugify(s: str, maxlen: int = 60) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", s.lower().strip())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return (s or "site")[:maxlen]


async def _verifier_site_ownership(
    slug: str, user_id: int, db: AsyncSession,
) -> SiteDB:
    site = (await db.execute(
        select(SiteDB).where(SiteDB.slug == slug)
    )).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Site introuvable")
    if site.user_id != user_id:
        raise HTTPException(403, "Site non possédé")
    return site


# ─── Endpoint /generer ───────────────────────────────────────────────────────

@router.post("/sites/generer", summary="Génère un mini-site multi-pages (LLM Sonnet)")
async def generer_site_endpoint(
    req: GenererSiteRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Pipeline : LLM compose SiteSpec → images IA → save DB (brouillon).

    Le site reste en `brouillon` jusqu'à appel explicite à `/publier`.
    Coût élevé (LLM Sonnet 10k+ tokens + N images IA premium) → passe
    par CostAdvisor pour demander confirmation si > 25% du solde.
    """
    from api.routes_pro_generateurs import _pre_check_credits, _ADMIN_ROLES
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    # CostAdvisor préventif
    if not req.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        n_pages = len(req.types_pages) if req.types_pages else 7
        mult = max(1.0, n_pages / 5.0) * (1.4 if req.generer_images else 1.0)
        cout = estimer_cout_module("site_multi_page", multiplicateur=mult)
        v = await advisor.evaluer(
            current_user.user_id, cout, module="site_multi_page",
        )
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    from modules.pro.site_builder import (
        generer_specification_site, enrichir_images_site,
        TYPES_PAGES_VALIDES,
    )
    from modules.bureau.service_credits_bureau import debiter_llm_unifie

    # 1. Spec LLM
    try:
        spec, usages = await generer_specification_site(
            brief=req.brief, types_pages=req.types_pages,
            langue=req.langue, brand_kit=req.brand_kit,
            cible=req.cible, ton=req.ton,
        )
    except Exception as e:
        logger.error(f"[Sites/generer] LLM spec échec user={current_user.user_id}: {e}")
        raise HTTPException(500, f"Erreur LLM : {str(e)[:200]}")

    # 2. Images IA + auto-pickup Brand LoRA org (Phase C.5) — best-effort
    if req.generer_images:
        try:
            compagnie_id = getattr(current_user, "compagnie_id", None)
            spec = await enrichir_images_site(spec, compagnie_id=compagnie_id)
        except Exception as e:
            logger.warning(f"[Sites/generer] images échec : {e}")

    # 3. Slug auto depuis le nom de marque
    nom_marque = spec.get("nom_marque") or req.brief[:60]
    slug = _slugify(nom_marque, 50)
    # Unicité — suffixe -N si collision
    suffix = 0
    base = slug
    while True:
        exist = (await db.execute(
            select(SiteDB).where(SiteDB.slug == slug)
        )).scalar_one_or_none()
        if not exist or exist.user_id == current_user.user_id:
            break
        suffix += 1
        slug = f"{base}-{suffix}"
        if suffix > 100:
            raise HTTPException(409, "Slug en collision — réessayez")

    # 4. Persistance DB — un site + N pages
    if exist and exist.user_id == current_user.user_id:
        # Régénération : on update le site existant
        site = exist
        site.brief = req.brief
        site.theme_json = req.brand_kit or {}
        site.brand_kit_json = req.brand_kit
        site.langue_principale = req.langue
        site.derniere_modif = datetime.utcnow()
        # Reset pages → on les recrée toutes
        await db.execute(
            SitePageDB.__table__.delete().where(SitePageDB.site_id == site.id)
        )
    else:
        site = SiteDB(
            user_id=current_user.user_id,
            slug=slug, nom=nom_marque, brief=req.brief,
            theme_json=req.brand_kit or {},
            brand_kit_json=req.brand_kit,
            langue_principale=req.langue,
            langues_actives_json=[req.langue],
            statut="brouillon",
        )
        db.add(site)
        await db.flush()  # pour récupérer site.id

    pages_data = spec.get("pages") or {}
    from modules.pro.site_builder import _SLUGS_DEFAUT
    for ordre, (type_page, page_spec) in enumerate(pages_data.items()):
        page = SitePageDB(
            site_id=site.id,
            type=type_page,
            slug_page=_SLUGS_DEFAUT.get(type_page, type_page),
            titre_seo=(page_spec.get("titre_seo") or "")[:120],
            description_seo=(page_spec.get("description_seo") or "")[:200],
            contenu_json=page_spec,
            ordre=ordre,
            langue=req.langue,
            publiee=True,
        )
        db.add(page)

    await db.commit()
    await db.refresh(site)

    # 5. Débit LLM
    try:
        for u in usages:
            await debiter_llm_unifie(
                user_id=current_user.user_id,
                modele=u.get("modele", "claude-sonnet-4-6"),
                tokens_input=int(u.get("tokens_in", 0)),
                tokens_output=int(u.get("tokens_out", 0)),
                module="sites_generer",
            )
    except Exception as _e:
        logger.warning(f"[Sites/generer] débit LLM non bloquant : {_e}")

    return {
        "ok": True,
        "site_id": site.id,
        "slug": site.slug,
        "nom": site.nom,
        "statut": site.statut,
        "nb_pages": len(pages_data),
        "types_pages": list(pages_data.keys()),
        "url_publier": f"/api/v1/pro/sites/{site.slug}/publier",
    }


# ─── Endpoint /publier ───────────────────────────────────────────────────────

@router.post(
    "/sites/{slug}/publier",
    summary="Déploie le site multi-pages sur Netlify (sous-domaine custom)",
)
async def publier_site_endpoint(
    req: PublierSiteRequest,
    slug: str = Path(..., min_length=3, max_length=60,
                     pattern=r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Build ZIP arborescence + déploie sur Netlify."""
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    if slug in _SLUGS_RESERVES:
        raise HTTPException(409, f"Slug réservé : {slug!r}")

    site = await _verifier_site_ownership(slug, current_user.user_id, db)

    # Cost preview
    if not req.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        cout = estimer_cout_module("site_publish")
        v = await advisor.evaluer(current_user.user_id, cout, module="site_publish")
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    from modules.pro.landing_publisher import (
        publier_site_multipage, is_active as _netlify_active, NetlifyError,
    )
    if not _netlify_active():
        raise HTTPException(
            503, "NETLIFY_API_TOKEN non configuré côté serveur.",
        )

    # Reconstitue la SiteSpec à partir des SitePageDB (langue principale)
    # + récupère les pages traduites (Phase C4) groupées par langue.
    pages_db = (await db.execute(
        select(SitePageDB).where(SitePageDB.site_id == site.id)
                          .order_by(SitePageDB.ordre)
    )).scalars().all()
    if not pages_db:
        raise HTTPException(400, "Site sans pages — relancer la génération")

    pages_dict = {}
    pages_par_langue: dict[str, dict] = {}
    for p in pages_db:
        if p.langue == site.langue_principale:
            pages_dict[p.type] = p.contenu_json
        else:
            pages_par_langue.setdefault(p.langue, {})[p.type] = p.contenu_json
    articles_db = (await db.execute(
        select(SiteArticleDB).where(SiteArticleDB.site_id == site.id)
                              .where(SiteArticleDB.publie.is_(True))
                              .order_by(desc(SiteArticleDB.publie_le))
    )).scalars().all()
    articles_data = [
        {
            "slug": a.slug, "titre": a.titre, "resume": a.resume,
            "hero_image_url": a.hero_image_url, "publie": True,
            "auteur": a.auteur, "contenu_md": a.contenu_md,
            "langue": a.langue, "seo_titre": a.seo_titre,
            "seo_desc": a.seo_desc,
        } for a in articles_db
    ]

    spec_complete = {
        "nom_marque": site.nom,
        "langue_principale": site.langue_principale,
        "nav": {"ordre_pages": [p.type for p in pages_db]},
        "footer": {
            "copyright": f"© {datetime.utcnow().year} {site.nom}",
            "liens_legaux": [
                {"label": "Mentions légales", "url": "/mentions-legales"},
                {"label": "Confidentialité", "url": "/confidentialite"},
            ],
            "reseaux_sociaux": [],
        },
        "pages": pages_dict,
    }

    base_domain = os.getenv("LANDING_DOMAIN_BASE", "yukpomnang.com")
    url_public_pressenti = f"https://{slug}.{base_domain}"

    from modules.pro.site_builder import construire_arborescence_zip
    files = construire_arborescence_zip(
        spec_complete,
        slug_site=slug,
        brand_kit=site.brand_kit_json,
        url_public=url_public_pressenti,
        articles=articles_data,
        pages_par_langue=pages_par_langue or None,
    )

    # Deploy
    try:
        res = await publier_site_multipage(
            files, slug,
            site_id_existant=site.netlify_site_id,
        )
    except NetlifyError as e:
        logger.error(f"[Sites/publier] Netlify échec user={current_user.user_id}: {e}")
        raise HTTPException(502, f"Erreur Netlify : {str(e)[:200]}")

    # Maj DB
    if res.get("is_new"):
        site.netlify_site_id = res["site_id"]
        site.url_public = res["url_public"] or url_public_pressenti
        site.publie_le = datetime.utcnow()
    site.statut = "publie"
    site.plan = req.plan
    site.derniere_modif = datetime.utcnow()
    await db.commit()

    # Débit forfait existant `pdf_generation` (sémantique : artefact publié)
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "pdf_generation",
            module="sites_publish",
            multiplicateur=max(1.0, len(pages_db) / 3.0),  # plus de pages = plus cher
        )
    except Exception as _e:
        logger.warning(f"[Sites/publier] débit non bloquant : {_e}")

    return {
        "ok": True,
        "site_id": site.id,
        "slug": site.slug,
        "url_public": site.url_public,
        "nb_pages": len(pages_db),
        "nb_articles": len(articles_data),
        "is_new_netlify_site": res.get("is_new", False),
    }


# ─── Endpoints lecture ───────────────────────────────────────────────────────

@router.get("/sites", summary="Liste les sites du user connecté")
async def lister_sites(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    res = await db.execute(
        select(SiteDB).where(SiteDB.user_id == current_user.user_id)
                       .order_by(desc(SiteDB.derniere_modif))
    )
    sites = res.scalars().all()
    return {
        "sites": [
            {
                "id": s.id, "slug": s.slug, "nom": s.nom,
                "statut": s.statut, "plan": s.plan,
                "url_public": s.url_public,
                "langue_principale": s.langue_principale,
                "cree_le": s.cree_le.isoformat(),
                "publie_le": s.publie_le.isoformat() if s.publie_le else None,
                "derniere_modif": s.derniere_modif.isoformat(),
            } for s in sites
        ]
    }


@router.get("/sites/{slug}", summary="Détail d'un site + liste pages + articles")
async def detail_site(
    slug: str = Path(..., min_length=3, max_length=60),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    site = await _verifier_site_ownership(slug, current_user.user_id, db)
    pages = (await db.execute(
        select(SitePageDB).where(SitePageDB.site_id == site.id)
                           .order_by(SitePageDB.ordre)
    )).scalars().all()
    articles = (await db.execute(
        select(SiteArticleDB).where(SiteArticleDB.site_id == site.id)
                              .order_by(desc(SiteArticleDB.cree_le))
    )).scalars().all()
    return {
        "site": {
            "id": site.id, "slug": site.slug, "nom": site.nom,
            "statut": site.statut, "plan": site.plan,
            "url_public": site.url_public,
            "brief": site.brief,
            "langue_principale": site.langue_principale,
            "langues_actives": site.langues_actives_json or [],
        },
        "pages": [
            {
                "type": p.type, "slug_page": p.slug_page,
                "titre_seo": p.titre_seo, "ordre": p.ordre,
                "langue": p.langue, "publiee": p.publiee,
            } for p in pages
        ],
        "articles": [
            {
                "slug": a.slug, "titre": a.titre, "resume": a.resume,
                "publie": a.publie,
                "publie_le": a.publie_le.isoformat() if a.publie_le else None,
            } for a in articles
        ],
    }


# ─── Modification incrémentale d'une page ────────────────────────────────────

@router.patch(
    "/sites/{slug}/pages/{type}",
    summary="Modifie incrémentalement une page via LLM",
)
async def modifier_page(
    req: PatchPageRequest,
    slug: str = Path(..., min_length=3, max_length=60),
    type: str = Path(..., max_length=32),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """LLM Sonnet applique les instructions sur le contenu_json de la page,
    en respectant la structure existante (économie tokens + cohérence)."""
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    if not req.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        cout = estimer_cout_module("site_page_modif")
        v = await advisor.evaluer(current_user.user_id, cout, module="site_page_modif")
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    site = await _verifier_site_ownership(slug, current_user.user_id, db)
    page = (await db.execute(
        select(SitePageDB).where(SitePageDB.site_id == site.id)
                           .where(SitePageDB.type == type)
    )).scalar_one_or_none()
    if not page:
        raise HTTPException(404, f"Page {type} introuvable sur ce site")

    from core.ia_client import ia_client, ModeIA
    prompt_systeme = (
        "Tu reçois une SPEC JSON d'une page web + des instructions de "
        "modification. Tu renvoies la SPEC JSON modifiée (même structure, "
        "même clés, seules les valeurs concernées par les instructions "
        "changent). Pas de texte avant/après — JSON strict uniquement."
    )
    prompt_user = (
        f"SPEC ACTUELLE :\n{json.dumps(page.contenu_json, ensure_ascii=False)}\n\n"
        f"INSTRUCTIONS DE MODIFICATION :\n{req.instructions}\n\n"
        f"Produis la SPEC JSON modifiée."
    )
    try:
        rep = await ia_client.appeler(
            prompt=prompt_user, systeme=prompt_systeme,
            mode=ModeIA.REDACTION, max_tokens_override=8000,
            json_attendu=True, utiliser_cache=False,
        )
        import re as _re
        texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
        m = _re.search(r"\{[\s\S]*\}", texte)
        if not m:
            raise ValueError("LLM n'a pas produit de JSON parseable")
        nouvelle_spec = json.loads(m.group(0))
    except Exception as e:
        logger.error(f"[Sites/page/modif] LLM échec : {e}")
        raise HTTPException(500, f"Erreur modif LLM : {str(e)[:200]}")

    page.contenu_json = nouvelle_spec
    page.titre_seo = (nouvelle_spec.get("titre_seo") or page.titre_seo)[:120]
    page.description_seo = (nouvelle_spec.get("description_seo") or page.description_seo)[:200] if nouvelle_spec.get("description_seo") else page.description_seo
    page.modifie_le = datetime.utcnow()
    site.derniere_modif = datetime.utcnow()
    await db.commit()

    try:
        from modules.bureau.service_credits_bureau import debiter_llm_unifie
        await debiter_llm_unifie(
            user_id=current_user.user_id,
            modele=getattr(rep, "modele_utilise", "claude-sonnet-4-6"),
            tokens_input=int(getattr(rep, "tokens_input", 0) or 0),
            tokens_output=int(getattr(rep, "tokens_output", 0) or 0),
            module="sites_page_modif",
        )
    except Exception:
        pass

    return {"ok": True, "type": type, "modifie_le": page.modifie_le.isoformat()}


# ─── Endpoints article de blog ────────────────────────────────────────────────

@router.post(
    "/sites/{slug}/articles",
    summary="Génère un article de blog AI-powered et l'ajoute au site",
)
async def generer_article(
    req: GenererArticleRequest,
    slug: str = Path(..., min_length=3, max_length=60),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    if not req.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        cout = estimer_cout_module("site_blog_article")
        v = await advisor.evaluer(current_user.user_id, cout, module="site_blog_article")
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    site = await _verifier_site_ownership(slug, current_user.user_id, db)

    from modules.pro.site_builder import generer_article_blog
    try:
        article_data, usages = await generer_article_blog(
            sujet=req.sujet, nom_marque=site.nom, langue=req.langue,
            cible=req.cible, ton=req.ton,
        )
    except Exception as e:
        logger.error(f"[Sites/article] LLM échec user={current_user.user_id}: {e}")
        raise HTTPException(500, f"Erreur génération article : {str(e)[:200]}")

    from datetime import timedelta
    publie_le = None
    publie = False
    if req.publier_immediatement:
        publie = True
        publie_le = datetime.utcnow()
    elif req.publier_dans_jours is not None:
        publie_le = datetime.utcnow() + timedelta(days=req.publier_dans_jours)
        publie = req.publier_dans_jours == 0

    article = SiteArticleDB(
        site_id=site.id,
        slug=_slugify(article_data.get("slug") or article_data.get("titre", ""), 100),
        titre=article_data.get("titre", "Article"),
        resume=article_data.get("resume"),
        contenu_md=article_data.get("contenu_md"),
        hero_image_url=article_data.get("hero_image_url"),
        auteur=req.auteur or site.nom,
        langue=req.langue,
        seo_titre=article_data.get("seo_titre"),
        seo_desc=article_data.get("seo_desc"),
        seo_keywords_json=article_data.get("seo_keywords"),
        publie=publie,
        publie_le=publie_le,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)

    try:
        from modules.bureau.service_credits_bureau import debiter_llm_unifie
        for u in usages:
            await debiter_llm_unifie(
                user_id=current_user.user_id,
                modele=u.get("modele", "claude-sonnet-4-6"),
                tokens_input=int(u.get("tokens_in", 0)),
                tokens_output=int(u.get("tokens_out", 0)),
                module="sites_article",
            )
    except Exception:
        pass

    return {
        "ok": True,
        "slug_article": article.slug, "titre": article.titre,
        "publie": article.publie,
        "publie_le": article.publie_le.isoformat() if article.publie_le else None,
    }


class ModifierParChatRequest(BaseModel):
    """Helper : modification par instruction libre depuis le chat YukpoPro.

    Le user dit "modifie le titre de ma page services en …" — backend :
    1. Trouve son dernier site (ou le seul) en DB
    2. LLM détermine quel TYPE de page est concerné par l'instruction
    3. Route vers le PATCH /pages/{type}/modifier classique
    """
    instructions: str = Field(..., min_length=5, max_length=2000)
    slug: Optional[str] = Field(None,
        description="Si fourni, cible ce slug. Sinon prend le dernier site du user.")
    type_page_force: Optional[str] = Field(None,
        description="Si fourni, contourne la détection LLM du type")
    confirmer_cout: bool = Field(default=False)


@router.post(
    "/sites/modifier-par-chat",
    summary="Helper chat — modifie une page du dernier site du user (LLM dispatcher)",
)
async def modifier_site_par_chat(
    req: ModifierParChatRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Pipeline :
       1. Trouve le site (slug fourni OU dernier modif du user)
       2. Si type_page non forcé, LLM rapide détecte le type concerné
       3. Patch la page via le pipeline /modifier existant
    """
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    if not req.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        cout = estimer_cout_module("site_page_modif")
        v = await advisor.evaluer(current_user.user_id, cout, module="site_page_modif")
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    # 1. Trouve le site cible
    if req.slug:
        site = await _verifier_site_ownership(req.slug, current_user.user_id, db)
    else:
        site = (await db.execute(
            select(SiteDB)
            .where(SiteDB.user_id == current_user.user_id)
            .order_by(desc(SiteDB.derniere_modif))
            .limit(1)
        )).scalar_one_or_none()
        if not site:
            raise HTTPException(404,
                "Aucun site trouvé pour cet utilisateur. Générez-en un d'abord.")

    # 2. Quels types de pages existent sur ce site ?
    pages_db = (await db.execute(
        select(SitePageDB.type, SitePageDB.titre_seo)
        .where(SitePageDB.site_id == site.id)
        .where(SitePageDB.langue == site.langue_principale)
    )).all()
    types_dispo = [(t, ts) for t, ts in pages_db]

    # 3. Détecte le type page (sauf si forcé)
    type_page = req.type_page_force
    if not type_page:
        # Heuristique rapide regex sur l'instruction
        import re as _re
        instr_lower = req.instructions.lower()
        hints = {
            "home":             [r"\b(accueil|home|page principale)\b"],
            "services":         [r"\b(services?|prestations?|offres?)\b"],
            "equipe":           [r"\b(équipe|equipe|team|membres?|collabor)\b"],
            "blog_index":       [r"\b(blog|articles?)\b"],
            "contact":          [r"\b(contact|coordon|adresse|horaires?|téléphone)\b"],
            "tarifs":           [r"\b(tarifs?|prix|pricing)\b"],
            "a_propos":         [r"\b(à\s*propos|about|histoire|qui\s*sommes)\b"],
            "portfolio":        [r"\b(portfolio|réalisations|réussites|cases?)\b"],
            "faq":              [r"\b(faq|questions?\s*fréquentes?)\b"],
            "mentions_legales": [r"\b(mentions?\s*légales?|legal)\b"],
            "cgv":              [r"\b(cgv|conditions?\s*(générales?|de\s*vente))\b"],
            "confidentialite":  [r"\b(confidentialité|privacy|rgpd|données\s*personnelles)\b"],
        }
        types_existant_set = {t for t, _ in types_dispo}
        for cand, patterns in hints.items():
            if cand not in types_existant_set:
                continue
            for p in patterns:
                if _re.search(p, instr_lower):
                    type_page = cand
                    break
            if type_page:
                break

        # Fallback LLM si pas trouvé par regex
        if not type_page and types_existant_set:
            from core.ia_client import ia_client, ModeIA, ModelePrioritaire
            choix = ", ".join(sorted(types_existant_set))
            rep = await ia_client.appeler(
                prompt=(
                    f"Instruction du user : « {req.instructions} »\n"
                    f"Types de pages disponibles : {choix}\n\n"
                    f"Réponds UNIQUEMENT par UN SEUL type parmi la liste, "
                    f"celui qui correspond le mieux à l'instruction. Pas d'explication."
                ),
                systeme="Tu détermines quelle page d'un site web l'utilisateur "
                        "veut modifier d'après son instruction. Réponse en 1 mot.",
                mode=ModeIA.PRECISION,
                max_tokens_override=20,
                utiliser_cache=False,
                forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
            )
            type_candidate = (rep.contenu or "").strip().lower().split()[0] if rep.contenu else ""
            if type_candidate in types_existant_set:
                type_page = type_candidate

        if not type_page:
            # Dernier recours : 'home' si dispo, sinon 1re page
            type_page = "home" if "home" in types_existant_set else (
                list(types_existant_set)[0] if types_existant_set else None
            )
        if not type_page:
            raise HTTPException(400,
                "Impossible de déterminer la page à modifier. Précisez (ex. 'page services').")

    # 4. Récupère la page + applique modif via LLM Sonnet (reuse pattern existant)
    page = (await db.execute(
        select(SitePageDB).where(SitePageDB.site_id == site.id)
                           .where(SitePageDB.type == type_page)
                           .where(SitePageDB.langue == site.langue_principale)
    )).scalar_one_or_none()
    if not page:
        raise HTTPException(404, f"Page {type_page} introuvable sur le site")

    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    prompt_systeme = (
        "Tu reçois une SPEC JSON d'une page web + des instructions de "
        "modification. Tu renvoies la SPEC JSON modifiée (même structure, "
        "même clés, seules les valeurs concernées par les instructions "
        "changent). Préserve les URLs, image_url, _image_url, slugs. "
        "Pas de texte avant/après — JSON strict uniquement."
    )
    prompt_user = (
        f"SPEC ACTUELLE :\n{json.dumps(page.contenu_json, ensure_ascii=False)}\n\n"
        f"INSTRUCTIONS DE MODIFICATION :\n{req.instructions}\n\n"
        f"Produis la SPEC JSON modifiée."
    )
    rep = await ia_client.appeler(
        prompt=prompt_user, systeme=prompt_systeme,
        mode=ModeIA.REDACTION, max_tokens_override=10000,
        json_attendu=True, utiliser_cache=False,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    import re as _re2
    texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
    m = _re2.search(r"\{[\s\S]*\}", texte)
    if not m:
        raise HTTPException(500, "LLM n'a pas produit de JSON parseable")
    nouvelle_spec = json.loads(m.group(0))

    page.contenu_json = nouvelle_spec
    page.titre_seo = (nouvelle_spec.get("titre_seo") or page.titre_seo or "")[:120] if nouvelle_spec.get("titre_seo") else page.titre_seo
    page.modifie_le = datetime.utcnow()
    site.derniere_modif = datetime.utcnow()
    site.statut = "brouillon" if site.statut == "publie" else site.statut
    await db.commit()

    try:
        from modules.bureau.service_credits_bureau import debiter_llm_unifie
        await debiter_llm_unifie(
            user_id=current_user.user_id,
            modele=getattr(rep, "modele_utilise", "claude-opus-4-7"),
            tokens_input=int(getattr(rep, "tokens_input", 0) or 0),
            tokens_output=int(getattr(rep, "tokens_output", 0) or 0),
            module="sites_modifier_chat",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "site_slug": site.slug,
        "type_page_modifiee": type_page,
        "site_publie": site.statut == "publie",
        "url_publique": site.url_public,
        "message": (
            f"Page «{type_page}» modifiée. " +
            ("Republie le site pour propager les changements en ligne." if site.url_public else "")
        ),
    }


class TraduirePageRequest(BaseModel):
    langues: list[str] = Field(
        ..., min_length=1, max_length=10,
        description="Codes ISO 639-1 cibles : ['en', 'ar', 'wo', 'douala']",
    )
    confirmer_cout: bool = Field(default=False)


@router.post(
    "/sites/{slug}/pages/{type}/traduire",
    summary="Phase C4 — Traduit une page vers N langues (crée des entrées SitePageDB par langue)",
)
async def traduire_page(
    req: TraduirePageRequest,
    slug: str = Path(..., min_length=3, max_length=60),
    type: str = Path(..., max_length=32),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Pour chaque langue cible : LLM Sonnet traduit le contenu_json de la
    page (en préservant la structure JSON + les image_url déjà générées)
    et crée une nouvelle entrée SitePageDB avec `langue=<cible>`.

    Les URLs sur le site publié deviennent : /en/services, /ar/الخدمات, etc.
    """
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    if not req.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        cout = estimer_cout_module("site_traduction_page",
                                    multiplicateur=len(req.langues))
        v = await advisor.evaluer(current_user.user_id, cout,
                                   module="site_traduction_page")
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    site = await _verifier_site_ownership(slug, current_user.user_id, db)
    page_source = (await db.execute(
        select(SitePageDB)
        .where(SitePageDB.site_id == site.id)
        .where(SitePageDB.type == type)
        .where(SitePageDB.langue == site.langue_principale)
    )).scalar_one_or_none()
    if not page_source:
        raise HTTPException(404, f"Page {type} introuvable (langue principale)")

    from core.ia_client import ia_client, ModeIA
    import re as _re

    traductions = {}
    erreurs = []
    for langue in req.langues:
        langue = langue.lower().strip()
        if langue == site.langue_principale:
            continue
        # Sauter si déjà traduite
        existante = (await db.execute(
            select(SitePageDB)
            .where(SitePageDB.site_id == site.id)
            .where(SitePageDB.type == type)
            .where(SitePageDB.langue == langue)
        )).scalar_one_or_none()
        if existante:
            traductions[langue] = "existante"
            continue

        prompt_systeme = (
            f"Tu reçois une SPEC JSON d'une page web (texte FR) + une langue "
            f"cible (code ISO {langue}). Tu renvoies la même SPEC JSON avec "
            f"TOUS les textes traduits dans la langue cible. Préserve : "
            f"  • toutes les clés JSON (ne pas renommer)\n"
            f"  • toutes les URLs (cta_url, image_url, _image_url, slugs)\n"
            f"  • tous les codes/IDs/icônes émoji\n"
            f"Traduis UNIQUEMENT les valeurs texte humaines (titres, "
            f"descriptions, labels, bios, contenu_md). Pas de texte avant/après. "
            f"JSON strict uniquement."
        )
        prompt_user = (
            f"SPEC FR :\n{json.dumps(page_source.contenu_json, ensure_ascii=False)}\n\n"
            f"Traduis vers : {langue}"
        )
        try:
            rep = await ia_client.appeler(
                prompt=prompt_user, systeme=prompt_systeme,
                mode=ModeIA.REDACTION, max_tokens_override=8000,
                json_attendu=True, utiliser_cache=False,
            )
            texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
            m = _re.search(r"\{[\s\S]*\}", texte)
            if not m:
                raise ValueError("LLM n'a pas produit de JSON parseable")
            spec_traduite = json.loads(m.group(0))

            nouvelle_page = SitePageDB(
                site_id=site.id, type=type,
                slug_page=page_source.slug_page,
                titre_seo=(spec_traduite.get("titre_seo") or "")[:120],
                description_seo=(spec_traduite.get("description_seo") or "")[:200],
                contenu_json=spec_traduite,
                ordre=page_source.ordre,
                langue=langue, publiee=True,
            )
            db.add(nouvelle_page)
            traductions[langue] = "ok"

            try:
                from modules.bureau.service_credits_bureau import debiter_llm_unifie
                await debiter_llm_unifie(
                    user_id=current_user.user_id,
                    modele=getattr(rep, "modele_utilise", "claude-sonnet-4-6"),
                    tokens_input=int(getattr(rep, "tokens_input", 0) or 0),
                    tokens_output=int(getattr(rep, "tokens_output", 0) or 0),
                    module="sites_traduction",
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[Sites/traduire] {type} → {langue} échec : {e}")
            erreurs.append({"langue": langue, "erreur": str(e)[:200]})

    # Maj langues_actives_json du site
    langues_actuelles = set(site.langues_actives_json or [site.langue_principale])
    langues_actuelles.update(k for k, v in traductions.items() if v == "ok")
    site.langues_actives_json = sorted(langues_actuelles)
    site.derniere_modif = datetime.utcnow()
    await db.commit()

    return {
        "ok": True, "type": type,
        "traductions": traductions, "erreurs": erreurs,
        "langues_actives_site": site.langues_actives_json,
    }


class PreviewLoraABRequest(BaseModel):
    """Phase C.5 — Body pour /brand-ai/preview-ab."""
    prompt: str = Field(..., min_length=10, max_length=600,
        description="Description de l'image à générer (EN recommandé, "
                    "ex. 'modern office workspace in Douala, professionals "
                    "collaborating, natural lighting')")
    confirmer_cout: bool = Field(default=False)


@router.post(
    "/brand-ai/preview-ab",
    summary="Phase C.5 — Génère 2 hero images comparatives (sans LoRA / avec LoRA brand)",
)
async def preview_lora_ab(
    req: PreviewLoraABRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Génère DEUX images identiques pour comparer l'effet du Brand LoRA :
      • Image A : sans LoRA (style générique fal.ai)
      • Image B : avec LoRA actif de la compagnie (cohérence brand)

    Le marchand visualise l'impact du LoRA avant de l'activer/désactiver
    en prod. Si la compagnie n'a pas de LoRA actif, retourne uniquement
    l'image A + message explicatif.
    """
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    if not req.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        # 2 images premium → 2× le coût d'une image standard
        cout = estimer_cout_module("designerpro_image_premium", multiplicateur=2.0)
        v = await advisor.evaluer(current_user.user_id, cout,
                                   module="brand_ai_preview_ab")
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    compagnie_id = getattr(current_user, "compagnie_id", None) or 1
    from modules.pro.site_builder import _resolve_brand_lora
    lora_url, trigger_word = await _resolve_brand_lora(compagnie_id)

    import base64
    from modules.bureau import image_gen as _ig

    # Image A — sans LoRA
    try:
        png_a = await _ig.generer_image(
            prompt=req.prompt, mode="premium",
            format_="landscape_16_9", timeout_s=120.0,
            brand_lora_url=None, brand_lora_scale=0.0,
        )
        image_a_url = (
            "data:image/png;base64," + base64.b64encode(png_a).decode()
            if png_a else None
        )
    except Exception as e:
        logger.warning(f"[Brand-AI/preview] image A échec : {e}")
        image_a_url = None

    # Image B — avec LoRA (si dispo)
    image_b_url = None
    if lora_url:
        prompt_lora = f"{trigger_word} {req.prompt}" if trigger_word else req.prompt
        try:
            png_b = await _ig.generer_image(
                prompt=prompt_lora, mode="premium",
                format_="landscape_16_9", timeout_s=120.0,
                brand_lora_url=lora_url, brand_lora_scale=0.85,
            )
            image_b_url = (
                "data:image/png;base64," + base64.b64encode(png_b).decode()
                if png_b else None
            )
        except Exception as e:
            logger.warning(f"[Brand-AI/preview] image B échec : {e}")

    # Débit forfait existant (2 × premium)
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "designerpro_image_premium",
            module="brand_ai_preview_ab",
            multiplicateur=2.0 if image_b_url else 1.0,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "image_a_url": image_a_url,
        "image_b_url": image_b_url,
        "has_brand_lora": bool(lora_url),
        "trigger_word": trigger_word,
        "lora_url": lora_url,
        "message": (
            "Brand LoRA actif — comparez la cohérence visuelle."
            if lora_url else
            "Aucun Brand LoRA configuré pour votre organisation. "
            "Entraînez-en un dans Designer Pro pour activer cette comparaison."
        ),
    }


@router.delete(
    "/sites/{slug}",
    summary="Supprime un site (DB + Netlify)",
)
async def supprimer_site(
    slug: str = Path(..., min_length=3, max_length=60),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    site = await _verifier_site_ownership(slug, current_user.user_id, db)
    if site.netlify_site_id:
        try:
            from modules.pro.landing_publisher import supprimer_site as _supprimer_netlify
            await _supprimer_netlify(site.netlify_site_id)
        except Exception as e:
            logger.warning(f"[Sites/delete] Netlify cleanup échec : {e}")
    await db.execute(
        SiteDB.__table__.delete().where(SiteDB.id == site.id)
    )
    await db.commit()
    return {"ok": True}
