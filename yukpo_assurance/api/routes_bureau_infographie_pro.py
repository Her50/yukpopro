"""
Bureau Infographie Pro — Endpoints pour projets multi-page + médiathèque utilisateur.

Endpoints :
  GET    /api/v1/bureau/infographie-pro/projets               — Catalogue projets multi-page
  GET    /api/v1/bureau/infographie-pro/template/{template_id} — Description d'un template page

  POST   /api/v1/bureau/infographie-pro/medias                — Upload média (session ou compte)
  GET    /api/v1/bureau/infographie-pro/medias                — Liste médias d'un user/session
  DELETE /api/v1/bureau/infographie-pro/medias/{media_id}     — Supprime un média

  POST   /api/v1/bureau/infographie-pro/generer               — Brief → projet IA → PDF + PNG
  POST   /api/v1/bureau/infographie-pro/generer-auto          — IA détecte type projet (brief libre)
  POST   /api/v1/bureau/infographie-pro/modifier              — Modif projet existant via instructions
  GET    /api/v1/bureau/infographie-pro/projet/{projet_id}    — Récupère JSON projet (pour édition)
"""
import base64
import json
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.bureau_infographie_pro")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_PROJETS_JSON_DIR = Path(__file__).parent.parent / "data" / "generated" / "designerpro_projets"
_PROJETS_JSON_DIR.mkdir(parents=True, exist_ok=True)


# ─── Modèles Pydantic ─────────────────────────────────────────────────────────

class ProfilDesigner(BaseModel):
    metier: Optional[str] = None
    secteur: Optional[str] = None
    nom_organisation: Optional[str] = None
    audience: Optional[str] = None
    ton: Optional[str] = None
    couleur_primaire_hex: Optional[str] = None
    couleurs_accents_hex: Optional[list[str]] = None


class DemandeProjetPro(BaseModel):
    cle_projet: str = Field(..., description="Clé du projet (livret_deces_8p, brochure_corporate_4p, ...)")
    brief: str = Field(..., min_length=10)
    pays: str = Field(default="CM")
    langue: str = Field(default="fr", description="fr|en|ar|es|pt — langue de rédaction")
    profil: Optional[ProfilDesigner] = None
    medias_refs: Optional[list[str]] = Field(default=None,
        description="Références médias session/compte ('session:abc123' ou 'compte:def456')")
    export_cmyk: bool = Field(default=True)
    directives_visuelles: Optional[dict] = Field(default=None,
        description="Curseurs UI : creativite, densite_texte, importance_images, elegance (0–100)")
    mode_visuel: str = Field(default="sans",
        description="'sans' (templates seuls) | 'standard' (Flux schnell rapide) | 'premium' (Flux dev haute qualité)")


class DemandeAutoPro(BaseModel):
    """Génération auto : l'IA choisit elle-même le projet/format selon le brief."""
    brief: str = Field(..., min_length=10)
    pays: str = Field(default="CM")
    langue: str = Field(default="fr")
    profil: Optional[ProfilDesigner] = None
    medias_refs: Optional[list[str]] = None
    cle_projet_hint: Optional[str] = Field(default=None,
        description="Hint optionnel (l'IA peut le suivre ou s'en écarter selon le brief)")
    export_cmyk: bool = Field(default=True)
    directives_visuelles: Optional[dict] = None
    mode_visuel: str = Field(default="sans")


class DemandeModifierProjet(BaseModel):
    projet_id: str = Field(..., description="ID JSON du projet existant à modifier")
    instructions: str = Field(..., min_length=5)
    medias_refs_supplementaires: Optional[list[str]] = None
    pays: str = Field(default="CM")
    directives_visuelles: Optional[dict] = None
    mode_visuel: str = Field(default="sans")


# ─── Médiathèque ──────────────────────────────────────────────────────────────

@router.post("/medias", tags=["Bureau — Designer Pro"])
async def uploader_media(
    fichier: UploadFile = File(...),
    portee: str = Form("session", description="'session' (volatile 24h) | 'compte' (persistant)"),
    categorie: str = Form(..., description="photo|illustration|scan|qr|icone (session) ou logo|banniere|signature|cachet|filigrane|tampon (compte)"),
    label: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None, description="ID de session — requis si portee='session'"),
    current_user: TokenData = Depends(get_current_user),
):
    """Upload un média dans la médiathèque utilisateur."""
    from modules.bureau import mediatheque_session as msm
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if portee == "session":
        if not session_id:
            raise HTTPException(400, "session_id requis pour portee='session'")
        owner_id = session_id
    elif portee == "compte":
        owner_id = str(current_user.user_id)
    else:
        raise HTTPException(400, "portee doit être 'session' ou 'compte'")

    contenu = await fichier.read()
    mime = fichier.content_type or "application/octet-stream"

    try:
        media = msm.ajouter_media(
            portee=portee,
            owner_id=owner_id,
            contenu=contenu,
            nom_fichier=fichier.filename or "upload",
            mime=mime,
            categorie=categorie,
            label=label,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"[Designer Pro/Médias] Upload échoué : {e}")
        raise HTTPException(500, "Upload échoué")

    try:
        await debiter_forfait(current_user.user_id, "designerpro_media_upload",
                              module="infographie")
    except Exception as _e_debit:
        logger.warning(f"[Designer Pro/Media] D\u00e9bit upload non bloquant : {_e_debit}")

    return {
        "ref": f"{media.portee}:{media.media_id}",
        "media_id": media.media_id,
        "portee": media.portee,
        "categorie": media.categorie,
        "label": media.label,
        "mime": media.mime,
        "dimensions_px": [media.largeur_px, media.hauteur_px],
        "couleur_dominante": media.couleur_dominante_hex,
        "taille_bytes": media.taille_bytes,
        "expire_le": media.expire_le,
    }


@router.get("/medias", tags=["Bureau — Designer Pro"])
async def lister_medias(
    portee: str = "session",
    session_id: Optional[str] = None,
    categorie: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    from modules.bureau import mediatheque_session as msm
    if portee == "session":
        if not session_id:
            raise HTTPException(400, "session_id requis pour portee='session'")
        owner_id = session_id
    else:
        owner_id = str(current_user.user_id)
    medias = msm.lister_medias(portee, owner_id, categorie)
    return {
        "medias": [
            {
                "ref": f"{m.portee}:{m.media_id}",
                "media_id": m.media_id,
                "portee": m.portee,
                "categorie": m.categorie,
                "label": m.label,
                "nom_fichier_origine": m.nom_fichier_origine,
                "mime": m.mime,
                "dimensions_px": [m.largeur_px, m.hauteur_px],
                "couleur_dominante": m.couleur_dominante_hex,
                "taille_bytes": m.taille_bytes,
                "cree_le": m.cree_le,
                "expire_le": m.expire_le,
            }
            for m in medias
        ],
        "total": len(medias),
    }


@router.get("/medias/{media_id}/contenu", tags=["Bureau — Designer Pro"])
async def telecharger_media(
    media_id: str,
    portee: str = "session",
    session_id: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Sert le contenu binaire d'un média (preview thumbnail dans le frontend)."""
    from modules.bureau import mediatheque_session as msm
    owner_id = session_id if portee == "session" else str(current_user.user_id)
    if portee == "session" and not session_id:
        raise HTTPException(400, "session_id requis")
    media = msm.recuperer_media(portee, owner_id, media_id)
    if not media:
        raise HTTPException(404, "Média introuvable ou expiré")
    try:
        contenu = msm.lire_bytes(media)
    except Exception:
        raise HTTPException(404, "Fichier média introuvable sur disque")
    return Response(content=contenu, media_type=media.mime)


@router.delete("/medias/{media_id}", tags=["Bureau — Designer Pro"])
async def supprimer_media(
    media_id: str,
    portee: str = "session",
    session_id: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    from modules.bureau import mediatheque_session as msm
    owner_id = session_id if portee == "session" else str(current_user.user_id)
    if portee == "session" and not session_id:
        raise HTTPException(400, "session_id requis")
    ok = msm.supprimer_media(portee, owner_id, media_id)
    if not ok:
        raise HTTPException(404, "Média introuvable")
    return {"supprime": True}


# ─── Catalogue projets ────────────────────────────────────────────────────────

@router.get("/projets", tags=["Bureau — Designer Pro"])
async def lister_projets():
    """Catalogue des projets multi-page disponibles."""
    from modules.bureau import gabarits_livret as catalog
    return {"projets": catalog.lister_projets()}


@router.get("/template/{template_id}", tags=["Bureau — Designer Pro"])
async def detail_template(template_id: str):
    """Détail d'un template de page (slots, ambiance)."""
    from modules.bureau.gabarits_livret import PAGE_TEMPLATES
    if template_id not in PAGE_TEMPLATES:
        raise HTTPException(404, "Template inconnu")
    return PAGE_TEMPLATES[template_id]


# ─── Génération projet ────────────────────────────────────────────────────────

def _persister_projet_pro(user_id, cle_projet: str, ts: int, resultat) -> dict:
    """Sauvegarde tous les artefacts du projet (PDF, CMJN, PNG par page) sur disque
    avec le pattern de nommage compatible 'Mes Documents' (`bureau_designerpro_{uid}_...`)."""
    base = f"bureau_designerpro_{user_id}_{cle_projet}_{ts}"
    out = {
        "pdf_id": None, "pdf_base64": None,
        "pdf_cmyk_id": None, "pdf_cmyk_base64": None,
        "pages_png_ids": [], "pages_png_base64": [],
        "pages_png_hd_ids": [],
        "projet_json_id": None,
    }
    if resultat.pdf_bytes:
        fid = f"{base}.pdf"
        (_DATA_DIR / fid).write_bytes(resultat.pdf_bytes)
        out["pdf_id"] = fid
        out["pdf_base64"] = base64.b64encode(resultat.pdf_bytes).decode()
    if resultat.pdf_cmyk_bytes:
        fid = f"{base}_cmyk.pdf"
        (_DATA_DIR / fid).write_bytes(resultat.pdf_cmyk_bytes)
        out["pdf_cmyk_id"] = fid
        out["pdf_cmyk_base64"] = base64.b64encode(resultat.pdf_cmyk_bytes).decode()
    for idx, png in enumerate(resultat.pages_png or []):
        if not png:
            continue
        fid = f"{base}_p{idx+1}.png"
        (_DATA_DIR / fid).write_bytes(png)
        out["pages_png_ids"].append(fid)
        out["pages_png_base64"].append(base64.b64encode(png).decode())
    for idx, png in enumerate(resultat.pages_png_hd or []):
        if not png or png == (resultat.pages_png[idx] if idx < len(resultat.pages_png) else None):
            continue
        fid = f"{base}_p{idx+1}_hd.png"
        (_DATA_DIR / fid).write_bytes(png)
        out["pages_png_hd_ids"].append(fid)
    # JSON projet (pour modif ultérieure via chat)
    if resultat.projet:
        proj_dict = _projet_en_dict(resultat.projet)
        proj_id = f"{base}.json"
        (_PROJETS_JSON_DIR / proj_id).write_text(
            json.dumps(proj_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        out["projet_json_id"] = proj_id
    return out


def _projet_en_dict(projet) -> dict:
    return {
        "cle_projet": projet.cle_projet,
        "titre": projet.titre,
        "palette": projet.palette,
        "palette_custom": projet.palette_custom,
        "polices": projet.polices,
        "langue": projet.langue,
        "medias_refs": projet.medias_refs,
        "pages": [
            {
                "numero": p.numero,
                "template_id": p.template_id,
                "palette_override": p.palette_override,
                "notes_ia": p.notes_ia,
                "zones": [
                    {"slot_id": z.slot_id, "type": z.type,
                     "contenu": z.contenu, "style": z.style}
                    for z in p.zones
                ],
            } for p in projet.pages
        ],
        "meta": projet.meta,
    }


def _projet_depuis_dict(d: dict):
    from modules.bureau.infographe_pro import ProjetInfographie, Page, Zone
    pages = []
    for p in d.get("pages", []):
        zones = [Zone(slot_id=z["slot_id"], type=z["type"],
                      contenu=z.get("contenu", {}) or {}, style=z.get("style", {}) or {})
                 for z in p.get("zones", [])]
        pages.append(Page(
            numero=int(p["numero"]),
            template_id=p["template_id"],
            zones=zones,
            palette_override=p.get("palette_override"),
            notes_ia=p.get("notes_ia"),
        ))
    return ProjetInfographie(
        cle_projet=d["cle_projet"],
        titre=d["titre"],
        palette=d.get("palette", "classique"),
        palette_custom=d.get("palette_custom"),
        pages=pages,
        medias_refs=d.get("medias_refs", []) or [],
        polices=d.get("polices", {}) or {},
        langue=d.get("langue", "fr"),
        meta=d.get("meta", {}) or {},
    )


def _serialiser_projet_pour_reponse(projet) -> dict:
    return {
        "cle_projet": projet.cle_projet,
        "titre": projet.titre,
        "palette": projet.palette,
        "langue": projet.langue,
        "nombre_pages": len(projet.pages),
        "pages_resume": [
            {"numero": p.numero, "template": p.template_id,
             "nb_zones": len(p.zones)}
            for p in projet.pages
        ],
    }


@router.post("/generer", tags=["Bureau — Designer Pro"])
async def generer_projet(
    demande: DemandeProjetPro,
    current_user: TokenData = Depends(get_current_user),
):
    from modules.bureau import gabarits_livret as catalog
    from modules.bureau.infographe_pro import generer_projet as _gen
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")
    if demande.cle_projet not in catalog.PROJETS_INFOGRAPHIE:
        raise HTTPException(400, f"Projet inconnu : {demande.cle_projet}")

    profil_dict = demande.profil.model_dump(exclude_none=True) if demande.profil else None
    session_id = f"chat_{current_user.user_id}"  # session par défaut = par user
    try:
        resultat = await _gen(
            brief=demande.brief,
            cle_projet=demande.cle_projet,
            user_id=str(current_user.user_id),
            session_id=session_id,
            medias_refs=demande.medias_refs,
            pays=demande.pays,
            profil=profil_dict,
            langue=demande.langue,
            export_cmyk=demande.export_cmyk,
            directives_visuelles=demande.directives_visuelles,
            mode_visuel=demande.mode_visuel,
        )
    except Exception as e:
        logger.error(f"[Designer Pro] Génération échouée : {e}")
        raise HTTPException(500, f"Génération échouée : {e}")

    # Crédits
    try:
        meta = resultat.meta or {}
        if meta.get("tokens_input") or meta.get("tokens_output"):
            await debiter_llm(
                current_user.user_id, modele=meta.get("modele", "default"),
                tokens_input=int(meta.get("tokens_input") or 0),
                tokens_output=int(meta.get("tokens_output") or 0),
                module="infographie",
            )
        if resultat.pdf_bytes:
            # Forfait scalé sur le nombre de pages réellement produites
            # (1 FCFA × nb_pages × 20 = 20 crédits/page). Le LLM est débité
            # séparément via debiter_llm — le total reste cohérent avec la
            # complexité réelle, pas avec un prix marché arbitraire.
            nb_pages = int(resultat.meta.get("nb_pages") or 1) if resultat.meta else 1
            await debiter_forfait(
                current_user.user_id, "designerpro_creation",
                module="infographie", multiplicateur=max(1.0, float(nb_pages)),
            )
            # Forfait images IA (Flux via fal.ai) — débité par image effectivement
            # générée, selon le mode choisi par l'utilisateur. 0 image générée
            # (mode "sans" ou aucun slot image_ia produit par le LLM) → pas de
            # débit supplémentaire.
            nb_imgs = int(resultat.meta.get("nb_images_ia") or 0)
            if nb_imgs > 0:
                forfait_image = (
                    "designerpro_image_premium" if demande.mode_visuel == "premium"
                    else "designerpro_image_standard"
                )
                await debiter_forfait(
                    current_user.user_id, forfait_image,
                    module="infographie", multiplicateur=float(nb_imgs),
                )
    except Exception as e:
        logger.warning(f"[Designer Pro/Crédits] {e}")

    ts = int(time.time())
    artefacts = _persister_projet_pro(current_user.user_id, demande.cle_projet, ts, resultat)

    return {
        "projet": _serialiser_projet_pour_reponse(resultat.projet),
        **artefacts,
        "meta": resultat.meta,
    }


# ── Génération auto (IA choisit le projet) ────────────────────────────────────

DESCRIPTIONS_PROJETS_IA = """\
- livret_deces_8p : Faire-part décès en livret 8 pages (familles, programme obsèques, plan, souvenirs, hommages)
- livret_deces_4p : Faire-part décès condensé 4 pages
- livret_mariage_4p : Faire-part mariage en livret 4 pages plié (invitation, plan, RSVP)
- carte_mariage_pliee : Carte mariage 4 faces format carte plié 105×148
- brochure_corporate_4p : Brochure entreprise 4 pages (couverture, services, témoignages, contact)
- menu_resto_4p : Menu de restaurant 4 pages (couverture, entrées, plats, dos)
- programme_culte_4p : Programme cérémonie/culte 4 pages (déroulement, chants, lectures)
- livre_photo_a4_8p : Album photo 8 pages format carré 21×21
"""


async def _detecter_projet_auto(brief: str, hint: Optional[str] = None,
                                 user_id: Optional[int] = None) -> str:
    """LLM rapide qui choisit la clé de projet la plus pertinente selon le brief.
    Si user_id fourni, débite le coût LLM (faible — ~40 tokens) pour rester équitable."""
    from core.ia_client import ia_client, ModeIA
    prompt = f"""Tu es un assistant de routing. Choisis la clé de projet la plus appropriée
parmi la liste, selon le brief utilisateur.

PROJETS DISPONIBLES :
{DESCRIPTIONS_PROJETS_IA}

BRIEF UTILISATEUR :
\"\"\"{brief[:1500]}\"\"\"

{f'HINT UTILISATEUR : {hint} (utilise-le si cohérent avec le brief, sinon ignore-le).' if hint else ''}

Retourne UNIQUEMENT la clé exacte (ex: "livret_deces_8p"), rien d'autre."""
    try:
        rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION,
                                       max_tokens_override=40, utiliser_cache=True)
        if user_id and (rep.tokens_input or rep.tokens_output):
            try:
                from modules.bureau.service_credits_bureau import debiter_llm as _dl
                await _dl(user_id, modele=rep.modele_utilise,
                          tokens_input=int(rep.tokens_input or 0),
                          tokens_output=int(rep.tokens_output or 0),
                          module="infographie")
            except Exception:
                pass
        cle = rep.contenu.strip().strip('"').strip("'").splitlines()[0].strip()
        from modules.bureau import gabarits_livret as catalog
        if cle in catalog.PROJETS_INFOGRAPHIE:
            return cle
    except Exception as e:
        logger.warning(f"[Designer Pro/Auto] Détection LLM : {e}")
    # Fallback heuristique
    msg = brief.lower()
    if "deuil" in msg or "déc" in msg or "obsèques" in msg or "memoriam" in msg:
        return "livret_deces_8p"
    if "mariage" in msg or "noces" in msg:
        return "livret_mariage_4p"
    if "menu" in msg or "restau" in msg or "carte des plats" in msg:
        return "menu_resto_4p"
    if "brochure" in msg or "plaquette" in msg or "présentation entreprise" in msg:
        return "brochure_corporate_4p"
    if "culte" in msg or "messe" in msg or "cérémonie religieuse" in msg:
        return "programme_culte_4p"
    if "album" in msg or "souvenir" in msg or "livre photo" in msg:
        return "livre_photo_a4_8p"
    return hint if hint else "brochure_corporate_4p"


@router.post("/generer-auto", tags=["Bureau — Designer Pro"])
async def generer_auto(
    demande: DemandeAutoPro,
    current_user: TokenData = Depends(get_current_user),
):
    """L'IA détecte automatiquement le type de projet selon le brief, puis génère."""
    cle = await _detecter_projet_auto(demande.brief, demande.cle_projet_hint,
                                       user_id=current_user.user_id)
    sub = DemandeProjetPro(
        cle_projet=cle,
        brief=demande.brief,
        pays=demande.pays,
        langue=demande.langue,
        profil=demande.profil,
        medias_refs=demande.medias_refs,
        export_cmyk=demande.export_cmyk,
        directives_visuelles=demande.directives_visuelles,
        mode_visuel=demande.mode_visuel,
    )
    res = await generer_projet(sub, current_user)
    if isinstance(res, dict):
        res["cle_projet_detectee"] = cle
    return res


# ── Modification de projet existant ───────────────────────────────────────────

@router.post("/modifier", tags=["Bureau — Designer Pro"])
async def modifier_projet(
    demande: DemandeModifierProjet,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Modifie un projet existant via instructions en langage naturel.
    L'IA reçoit le projet courant + instructions + médias supplémentaires éventuels
    et produit la nouvelle version.
    """
    from modules.bureau.infographe_pro import (
        rendre_projet_pdf, _png_par_page,
    )
    from modules.bureau import mediatheque_session as msm
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if "/" in demande.projet_id or "\\" in demande.projet_id or ".." in demande.projet_id:
        raise HTTPException(400, "ID invalide")
    chemin = _PROJETS_JSON_DIR / demande.projet_id
    if not chemin.exists():
        raise HTTPException(404, "Projet introuvable (peut-être expiré)")
    if f"_{current_user.user_id}_" not in demande.projet_id and current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")

    try:
        ancien_dict = json.loads(chemin.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"Lecture projet : {e}")

    # Charger médias référencés (anciens + supplémentaires)
    refs = list(ancien_dict.get("medias_refs", []) or [])
    refs += demande.medias_refs_supplementaires or []
    session_id = f"chat_{current_user.user_id}"
    medias = msm.resoudre_refs(refs, str(current_user.user_id), session_id)

    # Demander à l'IA d'appliquer les modifications au JSON projet
    from core.ia_client import ia_client, ModeIA
    prompt = f"""Tu es directeur artistique. Voici un projet d'infographie multi-page existant
au format JSON. L'utilisateur demande des modifications. Produis le JSON modifié EN ENTIER,
en conservant tout ce qui n'est pas concerné par les instructions et en appliquant les changements.

INSTRUCTIONS DE MODIFICATION :
\"\"\"{demande.instructions}\"\"\"

DIRECTIVES VISUELLES (curseurs 0–100) : {json.dumps(demande.directives_visuelles or {}, ensure_ascii=False)}

MÉDIATHÈQUE DISPONIBLE (refs réutilisables) :
{json.dumps([msm.descripteur_pour_ia(m) for m in medias.values()], ensure_ascii=False, indent=2)}

PROJET EXISTANT :
{json.dumps(ancien_dict, ensure_ascii=False, indent=2)}

Retourne UNIQUEMENT le nouveau JSON projet complet, sans markdown, sans commentaire."""

    try:
        rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION,
                                       json_attendu=True)
        try:
            nouveau_dict = json.loads(rep.contenu)
        except json.JSONDecodeError:
            import re as _re
            m = _re.search(r"\{.*\}", rep.contenu, _re.DOTALL)
            nouveau_dict = json.loads(m.group()) if m else ancien_dict
    except Exception as e:
        logger.error(f"[Designer Pro/Modifier] LLM : {e}")
        raise HTTPException(500, f"Modification IA échouée : {e}")

    projet = _projet_depuis_dict(nouveau_dict)
    try:
        pdf = rendre_projet_pdf(projet, medias, "rgb")
        pdf_cmyk = rendre_projet_pdf(projet, medias, "cmyk")
    except Exception as e:
        logger.error(f"[Designer Pro/Modifier] Rendu : {e}")
        raise HTTPException(500, f"Rendu modifié : {e}")
    pages_png = _png_par_page(pdf, dpi=150)
    pages_png_hd = _png_par_page(pdf, dpi=300)

    try:
        meta = nouveau_dict.get("meta", {}) or {}
        if rep.tokens_input or rep.tokens_output:
            await debiter_llm(
                current_user.user_id, modele=rep.modele_utilise,
                tokens_input=int(rep.tokens_input or 0),
                tokens_output=int(rep.tokens_output or 0),
                module="infographie",
            )
        # Forfait modification : moitié du forfait création par page (¼ via le
        # multiplicateur 0.25). LLM débité séparément pour la modif elle-même.
        from modules.bureau.service_credits_bureau import debiter_forfait as _df
        nb_pages = 1
        try:
            nb_pages = max(1, int((projet.specification or {}).get("nb_pages") or 1))
        except Exception:
            pass
        await _df(current_user.user_id, "designerpro_modification",
                  module="infographie", multiplicateur=max(0.25 * float(nb_pages), 0.25))
    except Exception as _e_debit:
        logger.warning(f"[Designer Pro/Modifier] D\u00e9bit cr\u00e9dits non bloquant : {_e_debit}")

    # Faux ResultatProjet pour réutiliser _persister
    from modules.bureau.infographe_pro import ResultatProjet
    res = ResultatProjet(
        pdf_bytes=pdf, pdf_cmyk_bytes=pdf_cmyk,
        pages_png=pages_png, pages_png_hd=pages_png_hd,
        projet=projet,
        meta={"modifie_depuis": demande.projet_id, "instructions": demande.instructions[:200]},
    )
    ts = int(time.time())
    artefacts = _persister_projet_pro(current_user.user_id, projet.cle_projet, ts, res)

    return {
        "projet": _serialiser_projet_pour_reponse(projet),
        "modifie_depuis": demande.projet_id,
        **artefacts,
        "meta": res.meta,
    }


@router.get("/projet/{projet_id}", tags=["Bureau — Designer Pro"])
async def lire_projet_json(
    projet_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    if "/" in projet_id or "\\" in projet_id or ".." in projet_id:
        raise HTTPException(400, "ID invalide")
    chemin = _PROJETS_JSON_DIR / projet_id
    if not chemin.exists():
        raise HTTPException(404, "Projet introuvable")
    if f"_{current_user.user_id}_" not in projet_id and current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")
    return json.loads(chemin.read_text(encoding="utf-8"))
