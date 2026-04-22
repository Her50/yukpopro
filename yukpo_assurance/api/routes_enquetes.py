"""
Routes Enquêtes & Études — Analyse qualitative IA + collecte quantitative (KoBoCollect-like)
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from core.auth import TokenData, get_current_user, require_permission
from modules.enquetes import gestionnaire_enquetes as ge

router = APIRouter(dependencies=[Depends(require_permission("enquetes"))])

AUDIO_MIMES = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg",
               "audio/webm", "audio/x-m4a", "application/octet-stream"}


# ─── Schémas Pydantic ─────────────────────────────────────────────────────────

class NouvelleEtudeRequest(BaseModel):
    titre: str
    contexte: str
    questions_recherche: list[str] = []
    methodologie: str = "exploratoire"  # phénoménologique | théorie ancrée | ethnographique | exploratoire
    population_cible: str = ""
    terrain: str = ""
    mode: str = "qualitatif"  # qualitatif | quantitatif | mixte


class QuestionFormulaireIn(BaseModel):
    libelle: str
    type_question: str = "text"
    options: list[str] = []
    obligatoire: bool = True


class NouveauFormulaireRequest(BaseModel):
    titre: str
    description: str = ""
    questions: list[QuestionFormulaireIn]


# ─── Études — CRUD ────────────────────────────────────────────────────────────

@router.post("/", summary="Créer une nouvelle étude")
async def creer_etude(
    payload: NouvelleEtudeRequest,
    current_user: TokenData = Depends(get_current_user),
):
    etude = ge.creer_etude(
        titre=payload.titre,
        contexte=payload.contexte,
        questions_recherche=payload.questions_recherche,
        methodologie=payload.methodologie,
        population_cible=payload.population_cible,
        terrain=payload.terrain,
        mode=payload.mode,
    )
    return {
        "etude_id": etude.etude_id,
        "titre": etude.titre,
        "mode": etude.mode,
        "statut": etude.statut,
        "message": "Étude créée. Uploadez vos audios ou créez un formulaire de collecte.",
    }


@router.get("/", summary="Lister toutes les études")
async def lister_etudes(current_user: TokenData = Depends(get_current_user)):
    return {"etudes": ge.lister_etudes()}


@router.get("/{etude_id}", summary="Détails d'une étude")
async def get_etude(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = ge.get_etude(etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")
    return {
        "etude_id": etude.etude_id,
        "titre": etude.titre,
        "contexte": etude.contexte,
        "questions_recherche": etude.questions_recherche,
        "methodologie": etude.methodologie,
        "population_cible": etude.population_cible,
        "terrain": etude.terrain,
        "mode": etude.mode,
        "statut": etude.statut,
        "n_transcriptions": len(etude.transcriptions),
        "n_themes": len(etude.themes),
        "n_reponses": len(etude.formulaire.reponses) if etude.formulaire else 0,
        "has_analyse": etude.analyse_qualitative is not None or etude.analyse_quantitative is not None,
        "has_rapport": etude.rapport_genere is not None,
        "graphiques_disponibles": list(etude.graphiques.keys()),
    }


# ─── Upload audio + transcription ─────────────────────────────────────────────

@router.post("/{etude_id}/audio", summary="Uploader et transcrire un audio de terrain")
async def uploader_audio(
    etude_id: str,
    audio: UploadFile = File(...),
    locuteur: str = Form("Répondant"),
    date_collecte: Optional[str] = Form(None),
    langue: str = Form("fr"),
    current_user: TokenData = Depends(get_current_user),
):
    etude = ge.get_etude(etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")

    contenu = await audio.read()
    mime = audio.content_type or "audio/mpeg"

    if len(contenu) == 0:
        raise HTTPException(400, "Fichier audio vide")

    try:
        transcription = await ge.transcrire_audio(
            contenu=contenu,
            nom_fichier=audio.filename or "audio.m4a",
            mime=mime,
            locuteur=locuteur,
            date_collecte=date_collecte,
            langue=langue,
        )
        etude.transcriptions.append(transcription)
        etude.statut = "transcription"

        return {
            "locuteur": transcription.locuteur,
            "fichier": transcription.fichier_nom,
            "duree_estimee_min": transcription.duree_estimee_min,
            "extrait": transcription.transcription[:300] + "…" if len(transcription.transcription) > 300 else transcription.transcription,
            "longueur_totale": len(transcription.transcription),
            "n_transcriptions_total": len(etude.transcriptions),
            "message": "Transcription réussie. Uploadez d'autres audios ou lancez l'analyse.",
        }
    except Exception as e:
        raise HTTPException(500, f"Erreur transcription : {e}")


@router.get("/{etude_id}/transcriptions", summary="Lister les transcriptions d'une étude")
async def lister_transcriptions(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = ge.get_etude(etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")
    return {
        "etude_id": etude_id,
        "n_transcriptions": len(etude.transcriptions),
        "transcriptions": [
            {
                "locuteur": t.locuteur,
                "fichier": t.fichier_nom,
                "date_collecte": t.date_collecte,
                "duree_estimee_min": t.duree_estimee_min,
                "extrait": t.transcription[:200] + "…",
                "longueur": len(t.transcription),
            }
            for t in etude.transcriptions
        ],
    }


# ─── Analyse qualitative ───────────────────────────────────────────────────────

@router.post("/{etude_id}/analyser", summary="Lancer l'analyse qualitative IA (codage thématique)")
async def analyser(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = ge.get_etude(etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")

    try:
        if etude.mode in ("qualitatif", "mixte"):
            analyse = await ge.analyser_qualitatif(etude_id)
        elif etude.mode == "quantitatif":
            analyse = await ge.analyser_quantitatif(etude_id)
        else:
            analyse = {}

        return {
            "statut": "analyse_terminee",
            "n_themes": len(etude.themes),
            "graphiques": list(etude.graphiques.keys()),
            "saturation": analyse.get("saturation_atteinte"),
            "message": "Analyse terminée. Générez maintenant le rapport complet.",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse : {e}")


@router.post("/{etude_id}/analyser-quantitatif", summary="Analyse statistique des données collectées")
async def analyser_quantitatif(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    try:
        resultats = await ge.analyser_quantitatif(etude_id)
        return {
            "statut": "analyse_quantitative_terminee",
            "n_reponses": resultats.get("n_reponses", 0),
            "n_questions_analysees": len(resultats.get("questions", [])),
            "graphiques": list(ge.get_etude(etude_id).graphiques.keys()),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse quantitative : {e}")


# ─── Rapport ──────────────────────────────────────────────────────────────────

@router.post("/{etude_id}/rapport", summary="Générer le rapport complet (qualitative + graphiques)")
async def generer_rapport(
    etude_id: str,
    format_rapport: str = "json",  # json | docx | pdf
    current_user: TokenData = Depends(get_current_user),
):
    if format_rapport not in ("json", "docx", "pdf"):
        raise HTTPException(400, "Format invalide : json | docx | pdf")
    try:
        rapport = await ge.generer_rapport(etude_id, format_rapport)
        return rapport
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération rapport : {e}")


@router.get("/{etude_id}/rapport", summary="Récupérer le dernier rapport généré")
async def get_rapport(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = ge.get_etude(etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")
    if not etude.rapport_genere:
        raise HTTPException(404, "Aucun rapport généré — POST /rapport d'abord")
    return etude.rapport_genere


# ─── Formulaire de collecte quantitative ──────────────────────────────────────

@router.post("/{etude_id}/formulaire", summary="Créer un formulaire de collecte de données")
async def creer_formulaire(
    etude_id: str,
    payload: NouveauFormulaireRequest,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        form = ge.creer_formulaire(
            etude_id=etude_id,
            titre=payload.titre,
            description=payload.description,
            questions=[q.model_dump() for q in payload.questions],
        )
        return {
            "formulaire_id": form.formulaire_id,
            "titre": form.titre,
            "n_questions": len(form.questions),
            "lien_collecte": f"/api/v1/enquetes/formulaire/{form.formulaire_id}",
            "message": "Formulaire créé. Partagez le lien de collecte aux répondants.",
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/formulaire/{formulaire_id}", summary="Afficher un formulaire (public — sans auth)")
async def afficher_formulaire(formulaire_id: str):
    """Endpoint public — les répondants accèdent sans authentification."""
    form = ge.get_formulaire_public(formulaire_id)
    if not form or not form.actif:
        raise HTTPException(404, "Formulaire introuvable ou fermé")
    return {
        "formulaire_id": form.formulaire_id,
        "titre": form.titre,
        "description": form.description,
        "questions": [
            {
                "question_id": q.question_id,
                "libelle": q.libelle,
                "type_question": q.type_question,
                "options": q.options,
                "obligatoire": q.obligatoire,
            }
            for q in sorted(form.questions, key=lambda x: x.ordre)
        ],
    }


@router.post("/formulaire/{formulaire_id}/soumettre", summary="Soumettre des réponses (public — sans auth)")
async def soumettre_reponses(formulaire_id: str, reponses: dict):
    """Endpoint public — soumission de réponses par un répondant."""
    ok = ge.soumettre_reponse(formulaire_id, reponses)
    if not ok:
        raise HTTPException(404, "Formulaire introuvable ou fermé")
    return {"message": "Réponses enregistrées. Merci pour votre participation."}


@router.get("/{etude_id}/formulaire/donnees", summary="Voir les données collectées")
async def donnees_formulaire(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = ge.get_etude(etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")
    if not etude.formulaire:
        raise HTTPException(404, "Aucun formulaire créé pour cette étude")
    return {
        "formulaire_id": etude.formulaire.formulaire_id,
        "n_reponses": len(etude.formulaire.reponses),
        "reponses": etude.formulaire.reponses,
    }


# ─── XLSForm export ───────────────────────────────────────────────────────────

@router.get(
    "/{etude_id}/formulaire/xlsform",
    summary="Télécharger le formulaire au format XLSForm (KoBoCollect / ODK / SurveyCTO)",
    response_class=Response,
)
async def telecharger_xlsform(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = ge.get_etude(etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")
    try:
        xlsx_bytes = ge.generer_xlsform_bytes(etude_id)
        nom = f"yukpopro_{etude.titre[:30].replace(' ', '_')}.xlsx"
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nom}"'},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération XLSForm : {e}")


# ─── Génération formulaire par IA ─────────────────────────────────────────────

class GenFormulaireIARequest(BaseModel):
    description: str
    titre: str
    objectif: str
    population: str
    n_questions: int = 15
    creer_dans_etude: Optional[str] = None  # etude_id pour créer automatiquement


@router.post(
    "/generer-formulaire-ia",
    summary="Claude génère un formulaire professionnel depuis une description + export XLSForm",
)
async def generer_formulaire_ia(
    payload: GenFormulaireIARequest,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        resultat = await ge.generer_formulaire_ia(
            description=payload.description,
            titre=payload.titre,
            objectif=payload.objectif,
            population=payload.population,
            n_questions=payload.n_questions,
        )

        # Si un etude_id est fourni, créer le formulaire directement dans l'étude
        formulaire_id = None
        if payload.creer_dans_etude:
            try:
                form = ge.creer_formulaire(
                    etude_id=payload.creer_dans_etude,
                    titre=resultat["titre_formulaire"],
                    description=resultat["description"],
                    questions=resultat["questions"],
                )
                formulaire_id = form.formulaire_id
            except Exception as e:
                pass  # Non bloquant si l'étude n'existe pas

        return {
            **resultat,
            "formulaire_id": formulaire_id,
            "lien_xlsform": f"/api/v1/enquetes/{payload.creer_dans_etude}/formulaire/xlsform" if formulaire_id else None,
            "lien_collecte": f"/api/v1/enquetes/formulaire/{formulaire_id}" if formulaire_id else None,
            "message": (
                "Formulaire généré. "
                + (f"Créé dans l'étude — XLSForm disponible pour KoBoCollect/ODK." if formulaire_id else
                   "Fournissez creer_dans_etude pour l'enregistrer.")
            ),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération IA : {e}")


# ─── Analyse des commentaires (questions ouvertes) ────────────────────────────

@router.post(
    "/{etude_id}/analyser-commentaires",
    summary="Analyse IA des questions ouvertes — thèmes, sentiments, citations représentatives",
)
async def analyser_commentaires(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    try:
        resultats = await ge.analyser_commentaires(etude_id)
        return resultats
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse commentaires : {e}")
