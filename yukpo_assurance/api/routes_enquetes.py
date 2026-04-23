"""
Routes Enquêtes & Études — Analyse qualitative IA + collecte quantitative (KoBoCollect-like)
"""
import base64
import re
import time as _time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from core.auth import TokenData, get_current_user, require_permission
from modules.enquetes import gestionnaire_enquetes as ge

router = APIRouter(dependencies=[Depends(require_permission("enquetes"))])

AUDIO_MIMES = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg",
               "audio/webm", "audio/x-m4a", "application/octet-stream"}

PROTOCOLE_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
}

_BUREAU_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_BUREAU_DIR.mkdir(parents=True, exist_ok=True)


def _slug(s: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip())[:n].strip("_")
    return s or "enquete"


def _save_bureau(user_id: int, kind: str, titre: str, ext: str, content: bytes) -> str:
    """Sauve un artefact d'enquête dans bureau/documents. kind: 'xls' | 'rapport'."""
    ts = int(_time.time())
    safe_titre = _slug(titre)
    # Pattern: bureau_doc_{user_id}_{kind}_{titre}_{ts}.{ext}
    # "_doc_" pour être reconnu comme "Rédaction IA" dans le listing bureau
    filename = f"bureau_doc_{user_id}_{kind}_{safe_titre}_{ts}.{ext}"
    path = _BUREAU_DIR / filename
    path.write_bytes(content)
    return filename


def _extract_text_from_upload(filename: str, content: bytes) -> str:
    """Extrait le texte d'un PDF / DOCX / TXT."""
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "txt":
        return content.decode("utf-8", errors="ignore")
    if ext == "pdf":
        try:
            from io import BytesIO
            try:
                from pypdf import PdfReader
            except ImportError:
                from PyPDF2 import PdfReader
            reader = PdfReader(BytesIO(content))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            raise ValueError(f"Impossible de lire le PDF : {e}")
    if ext in ("docx", "doc"):
        try:
            from io import BytesIO
            from docx import Document
            doc = Document(BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise ValueError(f"Impossible de lire le DOCX : {e}")
    raise ValueError(f"Format non supporté : {ext}. Utilisez PDF, DOCX ou TXT.")


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
        # Persister rapport DOCX/PDF dans Mes Documents
        etude = ge.get_etude(etude_id)
        titre = etude.titre if etude else "rapport"
        try:
            if format_rapport == "docx" and rapport.get("fichier_docx"):
                content = base64.b64decode(rapport["fichier_docx"])
                fichier_id = _save_bureau(current_user.user_id, "rapport", titre, "docx", content)
                rapport["fichier_id_bureau"] = fichier_id
            elif format_rapport == "pdf" and rapport.get("fichier_pdf"):
                content = base64.b64decode(rapport["fichier_pdf"])
                fichier_id = _save_bureau(current_user.user_id, "rapport", titre, "pdf", content)
                rapport["fichier_id_bureau"] = fichier_id
        except Exception:
            pass
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
        nom = f"yukpopro_{_slug(etude.titre)}.xlsx"
        # Persister dans Mes Documents
        try:
            _save_bureau(current_user.user_id, "xls", etude.titre, "xlsx", xlsx_bytes)
        except Exception:
            pass
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nom}"'},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération XLSForm : {e}")


# ─── Upload protocole / outils de collecte (KoBoCollect pro) ───────────────────

class ProtocoleUploadResponse(BaseModel):
    titre_formulaire: str
    n_questions: int
    formulaire_id: Optional[str]
    lien_xlsform: Optional[str]
    lien_collecte: Optional[str]
    message: str


@router.post(
    "/upload-protocole",
    summary="Upload PDF/DOCX du protocole — Claude génère automatiquement le formulaire XLSForm",
)
async def upload_protocole(
    fichier: UploadFile = File(...),
    etude_id: Optional[str] = Form(None),
    titre: str = Form("Enquête"),
    objectif: str = Form(""),
    population: str = Form(""),
    n_questions: int = Form(20),
    current_user: TokenData = Depends(get_current_user),
):
    """Workflow pro : uploader le protocole d'enquête → Claude construit le formulaire complet."""
    content = await fichier.read()
    if len(content) == 0:
        raise HTTPException(400, "Fichier vide")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop volumineux (> 20 Mo)")

    try:
        texte = _extract_text_from_upload(fichier.filename or "", content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if len(texte.strip()) < 50:
        raise HTTPException(400, "Texte extrait trop court — vérifiez le fichier")

    # Extraire objectif / population si non fournis (heuristique rapide)
    if not objectif:
        for keyword in ("objectif", "objectifs", "finalité", "problématique"):
            idx = texte.lower().find(keyword)
            if idx >= 0:
                objectif = texte[idx:idx + 300].replace("\n", " ").strip()
                break
    if not population:
        for keyword in ("population", "échantillon", "cible", "répondants"):
            idx = texte.lower().find(keyword)
            if idx >= 0:
                population = texte[idx:idx + 200].replace("\n", " ").strip()
                break

    try:
        resultat = await ge.generer_formulaire_ia(
            description=texte[:8000],
            titre=titre,
            objectif=objectif or "Enquête terrain",
            population=population or "Population cible",
            n_questions=n_questions,
        )
    except Exception as e:
        raise HTTPException(500, f"Erreur IA : {e}")

    formulaire_id = None
    if etude_id:
        try:
            form = ge.creer_formulaire(
                etude_id=etude_id,
                titre=resultat["titre_formulaire"],
                description=resultat.get("description", ""),
                questions=resultat["questions"],
                sections=resultat.get("sections_metadata", []),
            )
            formulaire_id = form.formulaire_id
            # Persister le XLSForm dans Mes Documents
            try:
                xls_bytes = ge.generer_xlsform_bytes(etude_id)
                _save_bureau(current_user.user_id, "xls", resultat["titre_formulaire"], "xlsx", xls_bytes)
            except Exception:
                pass
        except Exception as e:
            raise HTTPException(400, f"Étude introuvable ou invalide : {e}")

    return ProtocoleUploadResponse(
        titre_formulaire=resultat["titre_formulaire"],
        n_questions=len(resultat["questions"]),
        formulaire_id=formulaire_id,
        lien_xlsform=f"/api/v1/enquetes/{etude_id}/formulaire/xlsform" if formulaire_id else None,
        lien_collecte=f"/api/v1/enquetes/formulaire/{formulaire_id}" if formulaire_id else None,
        message=(
            f"Protocole analysé ({len(texte)} car.) — {len(resultat['questions'])} questions générées par IA. "
            + ("XLSForm sauvegardé dans Mes Documents." if formulaire_id else "Fournissez etude_id pour créer le formulaire.")
        ),
    )


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
                    sections=resultat.get("sections_metadata", []),
                )
                formulaire_id = form.formulaire_id
                # Persister XLSForm dans Mes Documents
                try:
                    xls_bytes = ge.generer_xlsform_bytes(payload.creer_dans_etude)
                    _save_bureau(current_user.user_id, "xls", resultat["titre_formulaire"], "xlsx", xls_bytes)
                except Exception:
                    pass
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


# ─── Analyse quantitative intelligente (guidée par LLM) ───────────────────────

@router.post(
    "/{etude_id}/analyser-intelligent",
    summary="Claude décide quelles variables croiser selon le contexte analytique (pas de croisement mécanique)",
)
async def analyser_quantitatif_intelligent(
    etude_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Claude lit l'objectif de l'étude, les questions de recherche et les données,
    puis sélectionne les croisements et analyses les plus pertinents.
    Résultats : croisements ciblés + Chi² + descriptives prioritaires + graphiques.
    """
    try:
        resultats = await ge.analyser_quantitatif_intelligent(etude_id)
        return {
            "statut": "analyse_intelligente_terminee",
            "n_reponses": resultats["n_reponses"],
            "n_croisements": len(resultats["croisements_cibles"]),
            "n_descriptives": len(resultats["analyses_descriptives"]),
            "hypotheses": resultats["hypotheses"],
            "note_methodologique": resultats["note_methodologique"],
            "graphiques": resultats["graphiques"],
            "croisements_cibles": resultats["croisements_cibles"],
            "analyses_descriptives": resultats["analyses_descriptives"],
            "plan_analyse": resultats["plan_analyse"],
            "message": "Analyse ciblée terminée. Générez le rapport pour la synthèse complète.",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse intelligente : {e}")
