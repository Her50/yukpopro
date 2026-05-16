"""Extensions routes Enquêtes — importées depuis routes_enquetes.py."""
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import Response

from core.auth import TokenData, get_current_user
from modules.enquetes import gestionnaire_enquetes as ge
from modules.enquetes import helpers_dictionnaire_plan as hdp
from modules.enquetes import facturation as fact
from modules.enquetes.persistence import sauvegarder_etude

# Note : pas de gate par permission — voir routes_enquetes.py
extra_router = APIRouter()


def _etude_owner_ou_404(etude_id: str, user_id: int):
    """Garde-fou ownership identique à routes_enquetes._etude_owner_ou_404.

    Dupliqué ici pour éviter un import circulaire (routes_enquetes inclut
    déjà extra_router). Tout endpoint extra qui prend etude_id en URL
    DOIT passer par ici avant d'appeler hdp.* (qui lit _etudes direct
    sans filtrage ownership).
    """
    etude = ge.get_etude_user(user_id, etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")
    return etude


# ─── Dictionnaire des variables ────────────────────────────────────────────────

@extra_router.get("/{etude_id}/dictionnaire", summary="Récupérer le dictionnaire des variables")
async def get_dictionnaire(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    _etude_owner_ou_404(etude_id, current_user.user_id)
    try:
        res = hdp.get_dictionnaire_variables(etude_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    await fact.debiter(current_user.user_id, "dictionnaire_get")
    return res


@extra_router.put("/{etude_id}/dictionnaire", summary="Enregistrer / modifier le dictionnaire des variables")
async def put_dictionnaire(
    etude_id: str,
    payload: dict = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)
    try:
        variables = payload.get("variables") if isinstance(payload, dict) else None
        if variables is None:
            variables = payload
        res = hdp.set_dictionnaire_variables(etude_id, variables or {})
    except ValueError as e:
        raise HTTPException(404, str(e))
    etude = ge.get_etude(etude_id)
    if etude:
        await sauvegarder_etude(etude, current_user.user_id)
    await fact.debiter(current_user.user_id, "dictionnaire_save")
    return res


@extra_router.post(
    "/{etude_id}/dictionnaire/generer-ia",
    summary="Générer automatiquement le dictionnaire des variables via IA",
)
async def post_dictionnaire_ia(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)
    try:
        res = await hdp.generer_dictionnaire_ia(etude_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur IA : {e}")
    rep_ia = res.pop("_reponse_ia", None) if isinstance(res, dict) else None
    etude = ge.get_etude(etude_id)
    if etude:
        await sauvegarder_etude(etude, current_user.user_id)
    await fact.debiter(current_user.user_id, "dictionnaire_ia", reponse_ia=rep_ia)
    return res


# ─── Plan d'analyse ───────────────────────────────────────────────────────────

@extra_router.get("/{etude_id}/plan-analyse", summary="Récupérer le plan d'analyse")
async def get_plan(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    _etude_owner_ou_404(etude_id, current_user.user_id)
    try:
        res = hdp.get_plan_analyse(etude_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    await fact.debiter(current_user.user_id, "plan_get")
    return res


@extra_router.put("/{etude_id}/plan-analyse", summary="Enregistrer / modifier le plan d'analyse")
async def put_plan(
    etude_id: str,
    payload: dict = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)
    try:
        res = hdp.set_plan_analyse(etude_id, payload.get("plan_analyse", ""))
    except ValueError as e:
        raise HTTPException(404, str(e))
    etude = ge.get_etude(etude_id)
    if etude:
        await sauvegarder_etude(etude, current_user.user_id)
    await fact.debiter(current_user.user_id, "plan_save")
    return res


@extra_router.post(
    "/{etude_id}/plan-analyse/generer-ia",
    summary="Générer le plan d'analyse automatiquement via IA",
)
async def post_plan_ia(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)
    try:
        res = await hdp.generer_plan_analyse_ia(etude_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur IA : {e}")
    rep_ia = res.pop("_reponse_ia", None) if isinstance(res, dict) else None
    etude = ge.get_etude(etude_id)
    if etude:
        await sauvegarder_etude(etude, current_user.user_id)
    await fact.debiter(current_user.user_id, "plan_ia", reponse_ia=rep_ia)
    return res


# ─── Exports DOCX dédiés ──────────────────────────────────────────────────────

@extra_router.get(
    "/{etude_id}/questionnaire.docx",
    summary="Exporter le questionnaire seul (version papier) en Word",
    response_class=Response,
)
async def export_questionnaire_docx(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)
    try:
        content = hdp.generer_questionnaire_docx_bytes(etude_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération : {e}")
    etude = ge.get_etude(etude_id)
    nom_brut = (etude.titre if etude else "questionnaire")
    nom_slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in nom_brut)[:40]
    nom = f"questionnaire_{nom_slug}.docx"
    await fact.debiter(current_user.user_id, "questionnaire_docx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@extra_router.get(
    "/{etude_id}/plan-analyse.docx",
    summary="Exporter le plan d'analyse en Word",
    response_class=Response,
)
async def export_plan_docx(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)
    try:
        content = hdp.generer_plan_analyse_docx_bytes(etude_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération : {e}")
    etude = ge.get_etude(etude_id)
    nom_brut = (etude.titre if etude else "plan_analyse")
    nom_slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in nom_brut)[:40]
    nom = f"plan_analyse_{nom_slug}.docx"
    await fact.debiter(current_user.user_id, "plan_docx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )
