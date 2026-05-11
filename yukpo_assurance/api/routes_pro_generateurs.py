"""
Routes Générateurs Pro — Rapports Word, présentations PowerPoint, analyse de données et traduction.

Endpoints :
  POST /api/v1/pro/rapports/generer        — Génère un rapport DOCX
  GET  /api/v1/pro/rapports/types          — Types de rapports disponibles
  POST /api/v1/pro/slides/generer          — Génère une présentation PPTX
  GET  /api/v1/pro/slides/types            — Types de présentations disponibles
  POST /api/v1/pro/data/analyser           — Analyse un dataset (JSON/CSV en body)
  POST /api/v1/pro/data/upload             — Upload fichier CSV/Excel pour analyse DAA
  POST /api/v1/pro/traduire                — Traduction de texte (FR↔EN + terminologie métier)
  POST /api/v1/pro/traduire-fichier        — Traduction de fichier uploadé (PDF/DOCX/TXT/XLSX/image)
  GET  /api/v1/pro/generateurs/fichier/{nom} — Télécharge un fichier généré
  GET  /api/v1/pro/documents/historique    — Historique des documents générés
  POST /api/v1/pro/documents/              — Sauvegarder un document généré
  PATCH /api/v1/pro/documents/{doc_id}     — Mettre à jour un document (version améliorée)
  DELETE /api/v1/pro/documents/{doc_id}    — Supprimer un document de l'historique
"""
import asyncio
import base64
import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
import io
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import async_session_maker

logger = logging.getLogger("yukpo_assurance.api.pro_generateurs")

router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated"


async def get_db():
    async with async_session_maker() as session:
        yield session


async def _debiter_credits_generation(
    user_id: int,
    db: AsyncSession,
    module: str,
    tokens_input: int = 2000,
    tokens_output: int = 3000,
    modele: str = "claude-sonnet-4-6",
    reponse_ia=None,
    role: str = "",
) -> None:
    """
    Débite les crédits Yukpo après une génération.
    Si `reponse_ia` (ReponseIA) est fourni, on utilise les tokens/modèle réels.
    Non bloquant sur DB, mais lève 402 CREDITS_EPUISES si crédits épuisés.
    """
    if role in _ADMIN_ROLES:
        return
    try:
        from modules.pro.service_credits import verifier_et_debiter
        if reponse_ia is not None:
            try:
                tokens_input = int(getattr(reponse_ia, "tokens_input", tokens_input) or tokens_input)
                tokens_output = int(getattr(reponse_ia, "tokens_output", tokens_output) or tokens_output)
                modele = getattr(reponse_ia, "modele_utilise", modele) or modele
            except Exception:
                pass
        ok, _c, msg = await verifier_et_debiter(
            user_id=user_id, modele=modele,
            tokens_input=tokens_input, tokens_output=tokens_output,
            module=module, db=db,
        )
        if not ok:
            raise HTTPException(status_code=402, detail=msg)
    except HTTPException:
        raise
    except Exception as _e:
        logger.warning(f"[Credits] Débit {module} non bloquant : {_e}")


_ADMIN_ROLES = ("admin", "super_admin", "yukpo_owner")

async def _pre_check_credits(user_id: int, role: str = "") -> None:
    """Vérifie le solde avant de lancer un traitement coûteux. Lève 402 si épuisé."""
    if role in _ADMIN_ROLES:
        return
    try:
        from modules.pro.service_credits import verifier_solde_suffisant
        ok, restants, plan, msg = await verifier_solde_suffisant(user_id)
        if not ok:
            raise HTTPException(status_code=402, detail=msg)
    except HTTPException:
        raise
    except Exception as _e:
        logger.debug(f"[Credits/PreCheck] non bloquant: {_e}")


async def _sauvegarder_doc_genere(
    db: AsyncSession,
    user_id: str,
    titre: str,
    type_doc: str,
    fichier: Optional[str],
    contenu_genere: str = "",
    session_id: Optional[str] = None,
    meta: Optional[dict] = None,
    fichier_path: Optional[Path] = None,
) -> None:
    """
    Sauvegarde automatiquement un document généré dans DocumentGenereDB.
    Appelé après chaque génération réussie (chat, générateur, agent).
    Si fichier_path est fourni et le fichier existe, son contenu est stocké en base64
    dans meta['fichier_b64'] pour résistance aux redémarrages Fly.io.
    """
    try:
        from core.database import DocumentGenereDB
        meta_final = dict(meta or {})
        if fichier_path and Path(fichier_path).exists():
            try:
                data = Path(fichier_path).read_bytes()
                if len(data) < 20 * 1024 * 1024:  # < 20 MB
                    meta_final["fichier_b64"] = base64.b64encode(data).decode()
            except Exception as _eb:
                logger.debug(f"[DocDB] Lecture b64 échouée (non-bloquant): {_eb}")
        doc = DocumentGenereDB(
            user_id=user_id,
            titre=titre[:200],
            type_doc=type_doc,
            fichier=fichier,
            contenu_source="",
            contenu_genere=contenu_genere[:5000] if contenu_genere else "",
            session_id=session_id,
            meta=meta_final,
            cree_le=datetime.utcnow(),
            modifie_le=datetime.utcnow(),
        )
        db.add(doc)
        await db.commit()
    except Exception as e:
        logger.warning(f"[DocDB] Sauvegarde historique échouée (non-bloquant): {e}")


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class GenererRapportRequest(BaseModel):
    sujet:          str  = Field(..., min_length=5, max_length=3000)
    type_rapport:   str  = Field("rapport_analyse",
                                  description="Tout type connu OU 'custom' avec structure_externe")
    mode:           str  = Field("standard", description="flash | standard | complet | expert")
    contexte:       Optional[str]  = Field(None, max_length=2000)
    donnees:        Optional[dict] = None
    format_sortie:  str  = Field("docx", description="docx | markdown")
    structure_externe: Optional[list[str]] = Field(default=None,
        description="Sections sur-mesure générées par l'orchestrateur G1 quand "
                    "aucun template prédéfini ne convient. ≥3 items requis. "
                    "Pas de plafond arbitraire (jusqu'à 50 sections).")
    tokens_max_output: Optional[int] = Field(default=None,
        description="Plafond tokens output dimensionné par l'orchestrateur G1 "
                    "selon le brief réel (au lieu des valeurs hardcodées des "
                    "modes flash/standard/complet/expert). 800 = note brève, "
                    "100000 = mémoire exhaustif. La SEULE vraie limite côté "
                    "user est son solde crédits.")
    # ── Métadonnées registre — propagées par /orchestrer pour adapter
    # ton/structure/signature sans dépendre du profil métier user ──────────
    registre: Optional[str] = Field(default=None,
        description="Registre détecté : professionnel | familial | associatif | "
                    "hommage | celebration | religieux | educatif | personnel. "
                    "Conditionne signature/cachet/ton/structure.")
    signataire_requis: Optional[bool] = Field(default=None,
        description="Si False, supprime bloc Signature/cachet final "
                    "(adapté familial/hommage/célébration/associatif).")
    ton: Optional[str] = Field(default=None,
        description="formel | neutre | chaleureux | intime | celebre")
    structure_hint: Optional[str] = Field(default=None, max_length=300,
        description="Hint structurel court (ex: 'Ordre du jour + sections "
                    "fidèles aux feuillets') pour guider le LLM.")


class GenererSlidesRequest(BaseModel):
    sujet:          str  = Field(..., min_length=5, max_length=3000)
    type_pres:      str  = Field("rapport_direction",
                                  description="bilan_activite | proposition_client | rapport_direction | "
                                              "formation | pitch_projet | analyse_marche | rapport_financier")
    mode:           str  = Field("executive", description="executive | detaille | pitch")
    contexte:       Optional[str]  = Field(None, max_length=2000)
    donnees:        Optional[dict] = None
    format_sortie:  str  = Field("pptx", description="pptx | markdown")


# ══════════════════════════════════════════════════════════════════════════════
# Routes Rapports
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/rapports/types", summary="Types de rapports disponibles")
async def types_rapports():
    """Liste les types et modes de rapports disponibles."""
    return {
        "types": [
            {"id": "rapport_analyse",   "label": "Rapport d'analyse"},
            {"id": "note_de_synthese",  "label": "Note de synthèse"},
            {"id": "note_juridique",    "label": "Note juridique"},
            {"id": "rapport_financier", "label": "Rapport financier"},
            {"id": "rapport_rh",        "label": "Rapport RH"},
            {"id": "plan_action",       "label": "Plan d'action"},
            {"id": "compte_rendu",      "label": "Compte-rendu"},
            {"id": "rapport_audit",     "label": "Rapport d'audit"},
        ],
        "modes": [
            {"id": "flash",    "label": "Flash (1 page — 2 min)"},
            {"id": "standard", "label": "Standard (5-10 pages — 5 min)"},
            {"id": "complet",  "label": "Complet (15-40 pages — 15 min)"},
            {"id": "expert",   "label": "Expert (50-100 pages — 25 min)"},
        ],
        "formats": ["docx", "markdown"],
    }


@router.post("/rapports/generer", summary="Générer un rapport professionnel")
async def generer_rapport(
    req: GenererRapportRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Génère un rapport professionnel Word (DOCX) ou Markdown.
    Le rapport est personnalisé selon le profil métier de l'utilisateur.
    """
    await _pre_check_credits(current_user.user_id, role=current_user.role)
    from modules.pro.service_profil import get_or_create
    from modules.pro.report_writer_pro import ReportWriterPro

    profil, _ = await get_or_create(current_user.user_id, db)

    # Le LLM Haiku décide si le sujet doit être nettoyé (titre propre vs phrase
    # brute). Triggers structurels : présence de '?', longueur > 90 chars, OU
    # verbe d'action en tête (« génère/crée/fais/produis/rédige/donne-moi… »)
    # qui indique un prompt utilisateur brut plutôt qu'un sujet propre.
    import re as _re_sujet
    sujet_clean = (req.sujet or "").strip()
    _verbe_action_re = _re_sujet.compile(
        r"^(g[ée]n[èeé]re|cr[ée]e|fais|produis|r[ée]dige|donne[- ]?moi|"
        r"compose|construis|prépare|monte|écris|aide[- ]?moi|peux[- ]?tu)\b",
        _re_sujet.IGNORECASE,
    )
    _trigger_titre_llm = (
        "?" in sujet_clean
        or len(sujet_clean) > 90
        or bool(_verbe_action_re.search(sujet_clean))
    )
    if _trigger_titre_llm:
        try:
            from core.ia_client import ia_client
            from api.routes_pro_copilote import _generer_titre_document
            sujet_clean = await _generer_titre_document(
                message=req.sujet,
                type_doc=req.type_rapport,
                contexte=(req.contexte or "")[:1500],
                ia_client=ia_client,
            )
        except Exception as e:
            logger.warning(f"[generer_rapport] dérivation titre échouée: {e}")

    writer = ReportWriterPro(profil=profil)
    # Timeouts adaptatifs — lots parallélisés. Avec chunking standard (3/lot)
    # + recherche web (~50s) le mode standard peut dépasser 240s sur Fly.
    _TIMEOUT_PAR_MODE = {"flash": 150, "standard": 360, "complet": 600, "expert": 900}
    _tmo = _TIMEOUT_PAR_MODE.get(req.mode, 360)
    try:
        resultat = await asyncio.wait_for(
            writer.generer(
                sujet=sujet_clean,
                type_rapport=req.type_rapport,
                mode=req.mode,
                contexte=req.contexte,
                donnees=req.donnees,
                format_sortie=req.format_sortie,
                instruction_utilisateur=req.sujet,
                structure_externe=req.structure_externe,
                tokens_max_output=req.tokens_max_output,
                registre=req.registre,
                signataire_requis=req.signataire_requis,
                ton=req.ton,
                structure_hint=req.structure_hint,
            ),
            timeout=_tmo,
        )
        # Sauvegarder + débiter crédits
        _chemin_r = resultat.get("chemin_fichier") or resultat.get("fichier")
        await _sauvegarder_doc_genere(
            db=db, user_id=current_user.user_id,
            titre=sujet_clean[:100],
            type_doc=req.type_rapport,
            fichier=Path(_chemin_r).name if _chemin_r else None,
            contenu_genere=resultat.get("contenu_markdown", ""),
            meta={"mode": req.mode, "format": req.format_sortie, "source": "generateur"},
            fichier_path=Path(_chemin_r) if _chemin_r else None,
        )
        await _debiter_credits_generation(
            user_id=current_user.user_id, db=db, module="rapport",
            tokens_input=2500, tokens_output=3500,
            role=current_user.role,
        )
        # Ajouter l'URL de téléchargement directement dans la réponse
        nom_fich = Path(_chemin_r or "").name if _chemin_r else None
        if nom_fich:
            resultat["url_telechargement"] = f"/api/v1/pro/generateurs/fichier/{nom_fich}"
            resultat["fichier"] = nom_fich
            resultat["fichier_genere"] = nom_fich   # alias frontend ChatPage YPro
        if "contenu_markdown" in resultat and "markdown" not in resultat:
            resultat["markdown"] = resultat["contenu_markdown"]

        # Suggestions intelligentes post-génération (Haiku, ~0.4 FCFA absorbé)
        try:
            from modules.pro.suggestions_intelligente import (
                generer_suggestions_suite, detecter_manques_doc,
            )
            meta_resultat = {
                "nb_pages": resultat.get("nb_pages"),
                "nb_sections": resultat.get("nb_sections"),
                "langue": "fr",  # langue par défaut, le vrai est dans le payload
                "format": req.format_sortie,
                "mode": req.mode,
            }
            manques = detecter_manques_doc(meta_resultat, req.sujet)
            resultat["suggestions"] = await generer_suggestions_suite(
                type_doc=req.type_rapport,
                brief_original=req.sujet,
                meta_resultat=meta_resultat,
                manques_detectes=manques,
            )
        except Exception as _e_sug:
            logger.debug(f"[Rapports/Suggestions] non bloquant : {_e_sug}")
            resultat["suggestions"] = []

        return resultat
    except HTTPException:
        raise
    except Exception as e:
        from modules.pro.report_writer_pro import SourcesInsuffisantesError
        if isinstance(e, SourcesInsuffisantesError):
            logger.info(f"[GenRapport] Refus sources insuffisantes user={current_user.user_id}: {e.raison}")
            raise HTTPException(
                status_code=422,
                detail={
                    "code":     "sources_insuffisantes",
                    "message":  e.raison,
                    "sources_essayees": e.sources_essayees,
                    "action_recommandee": (
                        "Veuillez joindre un document source vérifiable "
                        "(rapport annuel, états financiers, état CIMA, données comptables) "
                        "pour permettre une rédaction factuelle."
                    ),
                },
            )
        logger.error(f"[GenRapport] Erreur user={current_user.user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur génération : {str(e)[:200]}")


# ══════════════════════════════════════════════════════════════════════════════
# Routes Slides
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/slides/types", summary="Types de présentations disponibles")
async def types_slides():
    """Liste les types et modes de présentations disponibles."""
    return {
        "types": [
            {"id": "bilan_activite",      "label": "Bilan d'activité"},
            {"id": "proposition_client",  "label": "Proposition client"},
            {"id": "rapport_direction",   "label": "Rapport direction / CA"},
            {"id": "formation",           "label": "Support de formation"},
            {"id": "pitch_projet",        "label": "Pitch projet"},
            {"id": "analyse_marche",      "label": "Analyse de marché"},
            {"id": "rapport_financier",   "label": "Présentation financière"},
        ],
        "modes": [
            {"id": "executive", "label": "Exécutif (5-8 slides — rapide)"},
            {"id": "detaille",  "label": "Détaillé (15-25 slides — complet)"},
            {"id": "pitch",     "label": "Pitch (10-20 slides — impactant)"},
            {"id": "expert",    "label": "Expert (25-40 slides — exhaustif)"},
        ],
        "formats": ["pptx", "markdown"],
    }


@router.post("/slides/generer", summary="Générer une présentation PowerPoint")
async def generer_slides(
    req: GenererSlidesRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Génère une présentation PowerPoint (PPTX) professionnelle.
    Personnalisée selon le profil métier de l'utilisateur.
    """
    await _pre_check_credits(current_user.user_id, role=current_user.role)
    from modules.pro.service_profil import get_or_create
    from modules.pro.slide_builder_pro import SlideBuilderPro

    profil, _ = await get_or_create(current_user.user_id, db)

    builder = SlideBuilderPro(profil=profil)
    _TIMEOUT_SLIDES = {"executive": 180, "detaille": 360, "pitch": 240, "expert": 540}
    _tmo = _TIMEOUT_SLIDES.get(req.mode, 240)
    try:
        resultat = await asyncio.wait_for(
            builder.generer(
                sujet=req.sujet,
                type_pres=req.type_pres,
                mode=req.mode,
                contexte=req.contexte,
                donnees=req.donnees,
                format_sortie=req.format_sortie,
            ),
            timeout=_tmo,
        )
        # Sauvegarder + débiter crédits
        _chemin_fich = resultat.get("chemin_fichier") or resultat.get("fichier")
        await _sauvegarder_doc_genere(
            db=db, user_id=current_user.user_id,
            titre=req.sujet[:100],
            type_doc=f"slides_{req.type_pres}",
            fichier=Path(_chemin_fich).name if _chemin_fich else None,
            contenu_genere=resultat.get("contenu_markdown", ""),
            meta={"mode": req.mode, "format": req.format_sortie, "source": "generateur"},
            fichier_path=Path(_chemin_fich) if _chemin_fich else None,
        )
        await _debiter_credits_generation(
            user_id=current_user.user_id, db=db, module="slides",
            tokens_input=2000, tokens_output=2500,
            role=current_user.role,
        )
        nom_fich = Path(resultat.get("chemin_fichier") or "").name if resultat.get("chemin_fichier") else None
        if nom_fich:
            resultat["url_telechargement"] = f"/api/v1/pro/generateurs/fichier/{nom_fich}"
            resultat["fichier"] = nom_fich
            resultat["fichier_genere"] = nom_fich   # alias frontend ChatPage YPro
        # alias pour le frontend
        if "contenu_markdown" in resultat and "markdown" not in resultat:
            resultat["markdown"] = resultat["contenu_markdown"]

        # Suggestions intelligentes post-génération
        try:
            from modules.pro.suggestions_intelligente import (
                generer_suggestions_suite, detecter_manques_doc,
            )
            meta_resultat = {
                "nb_slides": resultat.get("nb_slides"),
                "format": req.format_sortie,
                "mode": req.mode,
                "langue": "fr",
            }
            manques = detecter_manques_doc(meta_resultat, req.sujet)
            resultat["suggestions"] = await generer_suggestions_suite(
                type_doc=f"slides_{req.type_pres}",
                brief_original=req.sujet,
                meta_resultat=meta_resultat,
                manques_detectes=manques,
            )
        except Exception as _e_sug:
            logger.debug(f"[Slides/Suggestions] non bloquant : {_e_sug}")
            resultat["suggestions"] = []

        return resultat
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GenSlides] Erreur user={current_user.user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur génération : {str(e)[:200]}")


# ══════════════════════════════════════════════════════════════════════════════
# Génération depuis fichiers uploadés (multipart)
# ══════════════════════════════════════════════════════════════════════════════

async def _extraire_texte_upload(contenu: bytes, nom: str, user_id: Optional[int] = None) -> str:
    """Extrait le texte d'un fichier uploadé (PDF, DOCX, XLSX, CSV, TXT, PPTX).
    Pour les PDF, bascule auto vers OCR Claude Vision si le texte natif est pauvre
    (scannés). Si user_id fourni, débite les crédits OCR par page."""
    import io
    from pathlib import Path as _Path
    ext = _Path(nom).suffix.lower()
    try:
        if ext in (".docx", ".doc"):
            from docx import Document
            doc = Document(io.BytesIO(contenu))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif ext == ".pdf":
            try:
                from core.pdf_ocr_batch import extraire_texte_pdf
                return await extraire_texte_pdf(contenu, user_id=user_id, module="pdf_ocr_upload_gen")
            except Exception as e:
                logger.warning(f"[GenUpload] extraire_texte_pdf échoué ({e}) → fallback natif")
                try:
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(contenu)) as pdf:
                        return "\n".join(p.extract_text() or "" for p in pdf.pages)
                except ImportError:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(io.BytesIO(contenu))
                    return "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext in (".xlsx", ".xls"):
            import pandas as pd
            xl = pd.ExcelFile(io.BytesIO(contenu))
            blocs = []
            for sheet_name in xl.sheet_names:
                df = xl.parse(sheet_name)
                if df.empty:
                    continue
                blocs.append(f"### Feuille : {sheet_name} ({len(df)} lignes × {len(df.columns)} colonnes)\n")
                blocs.append(df.to_markdown(index=False))
                # Statistiques rapides par feuille
                num_cols = df.select_dtypes(include='number').columns.tolist()
                if num_cols:
                    blocs.append(f"\n**Statistiques {sheet_name}:**\n{df[num_cols].describe().round(2).to_string()}")
                blocs.append("\n")
            return "\n".join(blocs)
        elif ext == ".csv":
            import pandas as pd
            df = pd.read_csv(io.BytesIO(contenu), encoding="utf-8-sig")
            return df.to_markdown(index=False)
        elif ext in (".txt", ".md"):
            return contenu.decode("utf-8", errors="ignore")[:20000]
        elif ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(io.BytesIO(contenu))
            return "\n".join(
                shape.text for slide in prs.slides
                for shape in slide.shapes if hasattr(shape, "text") and shape.text
            )
        elif ext in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp", ".tiff", ".tif"):
            # Images : OCR Vision (GPT-4o primaire, Claude fallback).
            # Gère écriture manuscrite, scans, captures écran, photos de docs.
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".heic": "image/heic", ".heif": "image/heif",
                ".gif": "image/gif", ".bmp": "image/bmp",
                ".tiff": "image/tiff", ".tif": "image/tiff",
            }
            texte = await _ocr_via_claude(contenu, mime_map.get(ext, "image/jpeg"))
            return texte or f"[Aucun texte extractible de l'image {nom}]"
    except Exception as e:
        return f"[Erreur extraction {nom}: {e}]"
    return f"[Format {ext} non supporté]"


@router.post("/analyser-et-generer", summary="Générer un document depuis des fichiers uploadés")
async def analyser_et_generer(
    instruction:   str          = Form(..., description="Ce que vous souhaitez générer"),
    type_sortie:   str          = Form("rapport", description="rapport | slides"),
    type_doc:      str          = Form("rapport_analyse", description="Type précis du document"),
    mode:          str          = Form("standard", description="flash | standard | complet | executive"),
    format_sortie: str          = Form("docx", description="docx | pptx | markdown"),
    fichiers:      List[UploadFile] = File(default=[], description="Fichiers source à analyser"),
    current_user:  TokenData    = Depends(get_current_user),
    db:            AsyncSession = Depends(get_db),
):
    """
    Génère un rapport ou une présentation PowerPoint à partir de fichiers uploadés.
    Les fichiers (PDF, DOCX, XLSX, CSV, TXT, PPTX) sont analysés et leur contenu
    sert de contexte pour la génération du document final.

    Exemple d'usages :
    - Uploader un bilan Excel + instruction "analyse financière détaillée" → rapport DOCX
    - Uploader un rapport existant + "présentation direction en 10 slides" → PPTX
    - Uploader un contrat PDF + "synthèse des points clés" → note de synthèse DOCX
    """
    await _pre_check_credits(current_user.user_id, role=current_user.role)
    from modules.pro.service_profil import get_or_create

    if not instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction requise")

    profil, _ = await get_or_create(current_user.user_id, db)

    # ── Extraction du texte de tous les fichiers uploadés ────────────────────
    textes_extraits = []
    noms_fichiers_excel = []
    for f in fichiers:
        contenu_bytes = await f.read()
        texte = await _extraire_texte_upload(contenu_bytes, f.filename or "fichier", user_id=current_user.user_id)
        if texte and not texte.startswith("[Erreur"):
            textes_extraits.append(f"=== {f.filename} ===\n{texte[:80000]}\n")
            if (f.filename or "").lower().endswith((".xlsx", ".xls", ".csv")):
                noms_fichiers_excel.append(f.filename)

    contexte_fichiers = "\n".join(textes_extraits)[:200000] if textes_extraits else None

    if not contexte_fichiers and fichiers:
        raise HTTPException(
            status_code=422,
            detail="Impossible d'extraire le texte des fichiers fournis. "
                   "Formats supportés : PDF, DOCX, XLSX, CSV, TXT, PPTX.",
        )

    # ── Pré-analyse LLM contextuelle des fichiers (surtout Excel/données) ────
    if contexte_fichiers and textes_extraits:
        try:
            from core.ia_client import ModeIA, ia_client
            noms = ", ".join(f.filename for f in fichiers if f.filename)
            prompt_preanalyse = (
                f"Tu es un data analyst senior. Voici des données extraites de fichiers ({noms}).\n"
                f"L'utilisateur demande : '{instruction}'\n\n"
                f"DONNÉES DES FICHIERS :\n{contexte_fichiers[:60000]}\n\n"
                f"Ta mission : faire une pré-analyse approfondie de ces données :\n"
                f"1. Décrire la structure et le contenu des données (colonnes, types, périmètre)\n"
                f"2. Identifier les indicateurs clés, tendances, anomalies visibles\n"
                f"3. Calculer les statistiques importantes (totaux, moyennes, variations, ratios)\n"
                f"4. Identifier ce qui est le plus pertinent par rapport à la demande de l'utilisateur\n"
                f"5. Proposer les axes d'analyse à approfondir dans le document\n\n"
                f"Répondre de façon structurée et dense, en exploitant TOUS les chiffres disponibles."
            )
            rep_preanalyse = await ia_client.appeler(
                prompt=prompt_preanalyse,
                systeme="Tu es un expert data analyst senior africain avec 20 ans d'expérience. "
                        "Tu extrais l'essentiel de données brutes et fournis une analyse structurée.",
                mode=ModeIA.PRECISION,
                max_tokens_override=8000,
                utiliser_cache=False,
            )
            # Injecter la pré-analyse au début du contexte pour guider la rédaction
            contexte_fichiers = (
                f"=== PRÉ-ANALYSE DES DONNÉES PAR YUKPO PRO ===\n"
                f"{rep_preanalyse.contenu}\n\n"
                f"{'═'*60}\n"
                f"DONNÉES BRUTES COMPLÈTES :\n"
                f"{contexte_fichiers}"
            )
        except Exception as _e:
            logger.warning(f"[AnalyserGenerer] Pré-analyse LLM non bloquante : {_e}")

    # Timeout adaptatif selon le mode (expert = chunking parallèle côté writer)
    _TIMEOUT_AG = {"flash": 150, "standard": 240, "complet": 480, "executive": 180,
                   "detaille": 360, "pitch": 240, "expert": 600, "complet_plus": 480}
    _tmo_gen = _TIMEOUT_AG.get(mode, 300)

    # ── Génération selon le type de sortie demandé ──────────────────────────
    try:
        if type_sortie == "slides" or format_sortie == "pptx":
            from modules.pro.slide_builder_pro import SlideBuilderPro
            builder = SlideBuilderPro(profil=profil)
            type_pres_map = {
                "rapport_direction": "rapport_direction",
                "bilan_activite": "bilan_activite",
                "proposition_client": "proposition_client",
                "pitch_projet": "pitch_projet",
                "formation": "formation",
                "analyse_marche": "analyse_marche",
                "rapport_financier": "rapport_financier",
            }
            type_pres = type_pres_map.get(type_doc, "rapport_direction")
            resultat = await asyncio.wait_for(
                builder.generer(
                    sujet=instruction,
                    type_pres=type_pres,
                    mode=mode or "executive",
                    contexte=contexte_fichiers,
                    format_sortie="pptx",
                ),
                timeout=_tmo_gen,
            )
            type_final = f"slides_{type_pres}"
        else:
            from modules.pro.report_writer_pro import ReportWriterPro
            writer = ReportWriterPro(profil=profil)
            resultat = await asyncio.wait_for(
                writer.generer(
                    sujet=instruction,
                    type_rapport=type_doc or "rapport_analyse",
                    mode=mode or "standard",
                    contexte=contexte_fichiers,
                    format_sortie=format_sortie,
                ),
                timeout=_tmo_gen,
            )
            type_final = type_doc

        chemin_fichier = resultat.get("fichier") or resultat.get("chemin_fichier")
        nom_fich = Path(chemin_fichier).name if chemin_fichier else None
        await _sauvegarder_doc_genere(
            db=db, user_id=current_user.user_id,
            titre=instruction[:100],
            type_doc=type_final,
            fichier=nom_fich,
            contenu_genere=resultat.get("contenu_markdown", "")[:5000],
            meta={
                "mode": mode,
                "format": format_sortie,
                "source": "analyser_et_generer",
                "nb_fichiers": len(fichiers),
                "noms_fichiers": [f.filename for f in fichiers],
            },
            fichier_path=Path(chemin_fichier) if chemin_fichier else None,
        )

        # Exposer fichier/markdown/url_telechargement pour que le frontend
        # affiche directement la carte de téléchargement (cf. GenerateursPage).
        if nom_fich:
            resultat["fichier"] = nom_fich
            resultat["url_telechargement"] = f"/api/v1/pro/generateurs/fichier/{nom_fich}"
        if "contenu_markdown" in resultat and "markdown" not in resultat:
            resultat["markdown"] = resultat["contenu_markdown"]

        return {
            **resultat,
            "nb_fichiers_analyses": len(textes_extraits),
            "noms_fichiers": [f.filename for f in fichiers],
        }

    except Exception as e:
        logger.error(f"[AnalyserGenerer] Erreur user={current_user.user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur génération : {str(e)[:300]}")


# ══════════════════════════════════════════════════════════════════════════════
# Téléchargement des fichiers générés
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/generateurs/fichier/{nom_fichier:path}", summary="Télécharger un fichier généré")
async def telecharger_fichier(
    nom_fichier:  str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Télécharge un fichier généré (DOCX, PPTX, Markdown).
    Le nom_fichier doit correspondre à un fichier dans le répertoire generated/pro_*.
    """
    # Sécurité : empêcher les path traversal
    safe_name = Path(nom_fichier).name
    if not safe_name or ".." in safe_name:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")

    # Chercher dans tous les sous-dossiers générés (rapports, slides, data)
    for sous_dossier in ("pro_reports", "pro_slides", "pro_data"):
        chemin = _DATA_DIR / sous_dossier / safe_name
        if chemin.exists():
            mime_type = mimetypes.guess_type(str(chemin))[0] or "application/octet-stream"
            return FileResponse(
                path=str(chemin),
                filename=safe_name,
                media_type=mime_type,
            )

    # Fallback : récupérer depuis la DB (résiste aux redémarrages Fly.io)
    try:
        from core.database import DocumentGenereDB
        async with async_session_maker() as _db:
            row = await _db.execute(
                select(DocumentGenereDB)
                .where(DocumentGenereDB.fichier == safe_name)
                .where(DocumentGenereDB.user_id == current_user.user_id)
                .order_by(desc(DocumentGenereDB.cree_le))
                .limit(1)
            )
            doc = row.scalar_one_or_none()
        if doc and isinstance(doc.meta, dict) and doc.meta.get("fichier_b64"):
            data = base64.b64decode(doc.meta["fichier_b64"])
            mime_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
            return StreamingResponse(
                io.BytesIO(data),
                media_type=mime_type,
                headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
            )
    except Exception as _ef:
        logger.debug(f"[Fichier/Fallback] DB lookup échoué: {_ef}")

    raise HTTPException(
        status_code=404,
        detail=f"Fichier '{safe_name}' introuvable. Veuillez régénérer le document.",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Routes Data Analyst (AgentDAA)
# ══════════════════════════════════════════════════════════════════════════════

class AnalyseDataRequest(BaseModel):
    donnees:       object = Field(..., description="Dataset : liste de dicts ou dict de listes")
    titre:         Optional[str]  = None
    colonnes:      Optional[list] = None
    avec_tendance: bool           = False
    colonne_serie: Optional[str]  = None  # colonne pour la tendance


@router.post("/data/analyser", summary="Analyse statistique d'un dataset (JSON)")
async def analyser_dataset_json(
    req: AnalyseDataRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyse statistique descriptive directe d'un dataset fourni en JSON.
    Retourne : statistiques par colonne, valeurs manquantes, outliers.
    """
    from modules.pro.agents.agent_daa import _charger_donnees, _stats_descriptives, _rendu_stats, _calculer_tendance, _rendu_tendance

    try:
        df = _charger_donnees(req.donnees)
        if req.colonnes:
            df = df[[c for c in req.colonnes if c in df.columns]]

        stats  = _stats_descriptives(df)
        rendu  = _rendu_stats(stats, req.titre or "Analyse descriptive")

        tendance = None
        if req.avec_tendance and req.colonne_serie and req.colonne_serie in df.columns:
            serie    = df[req.colonne_serie].dropna().tolist()
            tendance = _calculer_tendance(serie)

        return {
            "nb_lignes":     len(df),
            "nb_colonnes":   len(df.columns),
            "colonnes":      list(df.columns),
            "stats":         stats,
            "rendu_markdown": rendu,
            "tendance":       tendance,
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"pandas non installé : {e}")
    except Exception as e:
        logger.error(f"[AnalyseData] {e}")
        logger.warning(f"[routes_pro_generateurs.py] {e}")
        raise HTTPException(status_code=400, detail="Données invalides")


@router.post("/data/upload", summary="Upload CSV/Excel/PDF pour analyse DAA multi-feuilles")
async def upload_fichier_data(
    fichier:      UploadFile = File(..., description="CSV, Excel (.xlsx/.xls) ou PDF"),
    avec_ia:      bool       = True,
    current_user: TokenData  = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """
    Upload un fichier CSV, Excel (multi-feuilles) ou PDF de rapport SI.
    Retourne :
    - Stats descriptives par feuille/tableau
    - Interprétation IA niveau Data Analyst Senior (si avec_ia=True)
    - Graphiques auto générés
    - Aperçu JSON pour usage dans /agent/chat
    """
    import io
    from modules.pro.agents.agent_daa import (
        _stats_descriptives, _rendu_stats,
        _lire_excel_multi_feuilles, _consolider_feuilles,
        _calculer_correlations, _auto_generer_graphiques,
        _interpreter_donnees_llm,
        _extraire_pdf_tableaux_et_contexte, _resumer_pdf_pour_llm,
    )

    extension = Path(fichier.filename or "").suffix.lower()
    if extension not in (".csv", ".xlsx", ".xls", ".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Format non supporté. Formats acceptés : CSV, XLSX, XLS, PDF",
        )

    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="pandas non installé sur le serveur.",
        )

    try:
        contenu = await fichier.read()
        nom_fichier = fichier.filename or "données"

        # ── Lecture selon le format ───────────────────────────────────────────

        if extension == ".pdf":
            # Extraction tableaux PDF
            dataframes, texte_pdf = _extraire_pdf_tableaux_et_contexte(contenu)
            if not dataframes:
                # Retourner le texte brut si pas de tableau
                if texte_pdf:
                    return {
                        "fichier":          nom_fichier,
                        "format":           "pdf",
                        "type_contenu":     "texte",
                        "texte_extrait":    texte_pdf[:8000],
                        "nb_tableaux":      0,
                        "message":          "Aucun tableau structuré détecté — PDF texte uniquement.",
                        "conseil":          "Envoyez ce PDF dans le chat Yukpo Pro pour une analyse narrative.",
                    }
                raise HTTPException(status_code=422, detail="PDF vide ou non extractible.")

            feuilles = {f"Tableau_{i+1}": df for i, df in enumerate(dataframes)}
            df_principal = dataframes[0]
            contexte_source = f"PDF rapport — {len(dataframes)} tableau(x) extrait(s)\n{texte_pdf[:2000]}"

        elif extension in (".xlsx", ".xls"):
            # Lecture multi-feuilles
            feuilles = _lire_excel_multi_feuilles(contenu, limite_lignes=10000)
            if not feuilles:
                raise HTTPException(status_code=422, detail="Excel vide ou illisible.")
            df_principal = _consolider_feuilles(feuilles)
            contexte_source = f"Excel {len(feuilles)} feuille(s): {', '.join(feuilles.keys())}"

        else:
            # CSV
            try:
                df = pd.read_csv(io.BytesIO(contenu), sep=None, engine="python", encoding="utf-8-sig")
            except Exception:
                df = pd.read_csv(io.BytesIO(contenu), sep=";", encoding="utf-8-sig")
            feuilles = {"Données": df}
            df_principal = df
            contexte_source = "CSV"

        # ── Stats par feuille ─────────────────────────────────────────────────
        stats_par_feuille: dict = {}
        rendus_md: list[str]   = []
        apercu_par_feuille: dict = {}

        for nom_f, df_f in feuilles.items():
            tronque = len(df_f) > 5000
            if tronque:
                df_f = df_f.head(5000)
            stats = _stats_descriptives(df_f)
            stats_par_feuille[nom_f] = stats
            rendus_md.append(_rendu_stats(stats, f"{nom_fichier} — {nom_f}"))
            apercu_par_feuille[nom_f] = df_f.head(100).to_dict(orient="records")

        # ── Corrélations sur le DataFrame principal ───────────────────────────
        correlations = {}
        try:
            correlations = _calculer_correlations(df_principal)
        except Exception:
            pass

        # ── Graphiques automatiques ───────────────────────────────────────────
        chemins_graphiques: list[str] = []
        try:
            chemins_graphiques = _auto_generer_graphiques(df_principal, nom_fichier.rsplit(".", 1)[0])
        except Exception as eg:
            logger.warning(f"[UploadData] Graphiques auto échoués : {eg}")

        # ── Interprétation IA ─────────────────────────────────────────────────
        interpretation_ia = ""
        if avec_ia:
            try:
                profil = await _get_profil_optionnel(current_user.user_id, db)
                metier = getattr(profil, "metier", "") if profil else ""
                pays   = getattr(profil, "pays", "Afrique francophone") if profil else "Afrique francophone"
                feuilles_info = (
                    f"\n**Source fichier** : {contexte_source}\n"
                    f"**Feuilles/tableaux** : {', '.join(feuilles.keys())}\n"
                    f"**Total lignes** : {sum(len(df) for df in feuilles.values()):,}"
                )
                interpretation_ia = await _interpreter_donnees_llm(
                    df=df_principal,
                    stats={k: v for fstats in stats_par_feuille.values() for k, v in fstats.items()},
                    correlations=correlations,
                    contexte_metier=metier,
                    titre=nom_fichier,
                    pays=pays,
                    feuilles_info=feuilles_info,
                )
            except Exception as ei:
                logger.warning(f"[UploadData] Interprétation IA échouée : {ei}")
                interpretation_ia = "Interprétation IA indisponible — utilisez le chat pour une analyse approfondie."

        return {
            "fichier":              nom_fichier,
            "format":               extension.lstrip("."),
            "nb_feuilles":          len(feuilles),
            "noms_feuilles":        list(feuilles.keys()),
            "nb_lignes_total":      sum(len(df) for df in feuilles.values()),
            "nb_colonnes":          len(df_principal.columns),
            "colonnes":             list(df_principal.columns),
            "stats_par_feuille":    stats_par_feuille,
            "apercu_par_feuille":   apercu_par_feuille,
            "correlations":         correlations,
            "graphiques":           [Path(c).name for c in chemins_graphiques],
            "interpretation_ia":    interpretation_ia,
            "rendu_markdown":       "\n\n".join(rendus_md),
            "conseil": (
                "Posez vos questions dans le chat Yukpo Pro pour une analyse ciblée. "
                "Les données sont prêtes pour des croisements, tendances et recommandations."
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UploadData] {e}")
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier : {str(e)[:200]}")


async def _get_profil_optionnel(user_id: int, db):
    """Retourne le profil pro ou None si non trouvé."""
    try:
        from modules.pro.service_profil import get_profil_pro
        return await get_profil_pro(user_id, db)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Route Traduction de documents
# ══════════════════════════════════════════════════════════════════════════════

class TraduireDocumentRequest(BaseModel):
    contenu:        str  = Field(..., min_length=1, max_length=50_000,
                                  description="Texte ou contenu du document à traduire")
    langue_source:  str  = Field("fr", description="Langue source (fr, en, es, pt...)")
    langue_cible:   str  = Field("en", description="Langue cible (en, fr, es, pt...)")
    contexte_metier: Optional[str] = Field(None, description="Contexte métier pour la terminologie (ex: comptabilite, juridique, rh)")
    format_sortie:  str  = Field("texte", description="texte | docx | markdown")
    sujet:          Optional[str] = Field(None, description="Titre/sujet du document pour nommer le fichier")


@router.post("/traduire", summary="Traduire un document professionnel")
async def traduire_document(
    req: TraduireDocumentRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Traduit un document professionnel avec terminologie métier appropriée.
    Supporte FR ↔ EN et autres langues. Génère optionnellement un DOCX.
    La traduction utilise Claude pour respecter la terminologie sectorielle africaine.
    """
    await _pre_check_credits(current_user.user_id, role=current_user.role)
    from modules.pro.service_profil import get_or_create, incrementer_stat
    from core.ia_client import ModeIA, ia_client

    profil, _ = await get_or_create(current_user.user_id, db)
    metier = getattr(profil, "metier", "") or ""
    contexte_metier = req.contexte_metier or metier

    # Construire le prompt de traduction
    langue_noms = {
        "fr": "français", "en": "anglais", "es": "espagnol",
        "pt": "portugais", "ar": "arabe", "zh": "mandarin",
    }
    src = langue_noms.get(req.langue_source, req.langue_source)
    dst = langue_noms.get(req.langue_cible, req.langue_cible)

    prompt_sys = (
        f"Tu es un traducteur professionnel expert en terminologie d'affaires africaine. "
        f"Tu traduis du {src} vers le {dst} avec une précision absolue. "
        f"Tu respectes la terminologie technique du secteur {contexte_metier or 'professionnel'}. "
        f"Pour les termes spécifiques africains (SYSCOHADA, CIMA, OHADA, COBAC, UEMOA, CEMAC, FCFA), "
        f"tu les traduis ou les expliques selon l'usage international. "
        f"Tu conserves la mise en forme (titres, listes, tableaux). "
        f"Tu réponds uniquement avec le texte traduit, sans préambule ni commentaire."
    )

    prompt_user = (
        f"Traduis le texte suivant du {src} vers le {dst} :\n\n"
        f"---\n{req.contenu[:40_000]}\n---"
    )

    try:
        # max_tokens proportionnel à la taille du texte source : un mot ≈ 1.5 token,
        # la cible fait ~1.3× la source selon les langues. On garde une marge confortable
        # mais on évite de demander 8192 pour 5 mots (latence × 5).
        _nb_mots_src = len(req.contenu.split())
        _max_out = max(256, min(8192, int(_nb_mots_src * 4) + 256))
        reponse_ia = await ia_client.appeler(
            prompt=prompt_user,
            mode=ModeIA.REDACTION,
            systeme=prompt_sys,
            max_tokens_override=_max_out,
            utiliser_cache=False,
        )
        texte_traduit = reponse_ia.contenu if hasattr(reponse_ia, "contenu") else str(reponse_ia)

        await incrementer_stat(current_user.user_id, "nb_traductions", db, xp_gain=1)
        # Débit crédits basé sur la longueur réelle du texte
        nb_mots = len(req.contenu.split())
        await _debiter_credits_generation(
            user_id=current_user.user_id, db=db, module="traduction",
            tokens_input=max(500, nb_mots * 2),
            tokens_output=max(400, nb_mots * 2),
            reponse_ia=reponse_ia,
            role=current_user.role,
        )

        # Générer DOCX si demandé — écriture directe (pas de relance LLM).
        # ReportWriterPro restructure le texte via IA, ce qui dénature une traduction
        # et multiplie la latence par 3-5×. On veut juste un DOCX brut du texte traduit.
        chemin_docx = None
        if req.format_sortie == "docx":
            try:
                from docx import Document
                from pathlib import Path
                _doc = Document()
                _doc.add_heading(req.sujet or f"Traduction {src} → {dst}", level=1)
                for _para in (texte_traduit or "").split("\n"):
                    _doc.add_paragraph(_para)
                _data_dir = Path(__file__).resolve().parent.parent / "data" / "generated" / "traductions"
                _data_dir.mkdir(parents=True, exist_ok=True)
                _ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                _slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in (req.sujet or "traduction"))[:40]
                _path = _data_dir / f"trad_{_slug}_{_ts}.docx"
                _doc.save(str(_path))
                chemin_docx = str(_path)
            except Exception as e_doc:
                logger.warning(f"[Traduction] Impossible de générer DOCX : {e_doc}")

        return {
            "langue_source":  req.langue_source,
            "langue_cible":   req.langue_cible,
            "nb_mots_source": len(req.contenu.split()),
            "nb_mots_cible":  len(texte_traduit.split()),
            "texte_traduit":  texte_traduit,
            "chemin_docx":    chemin_docx,
            "contexte_metier": contexte_metier,
        }

    except Exception as e:
        logger.error(f"[Traduction] user={current_user.user_id} : {e}")
        raise HTTPException(status_code=500, detail=f"Erreur traduction : {str(e)[:200]}")


# ══════════════════════════════════════════════════════════════════════════════
# Route Traduction de fichier uploadé
# ══════════════════════════════════════════════════════════════════════════════

LANGUES_NOM = {
    "fr": "français", "en": "anglais", "es": "espagnol",
    "pt": "portugais", "ar": "arabe", "zh": "mandarin",
}

MAX_FILE_SIZE_MB = 20


async def _extraire_texte_fichier(fichier: UploadFile, contenu: bytes) -> str:
    """
    Extrait le texte brut d'un fichier uploadé selon son type.
    Supporte : PDF, DOCX, TXT, MD, CSV, XLSX, XLS, images (OCR Claude Vision).
    """
    nom = (fichier.filename or "").lower()
    mime = fichier.content_type or ""

    # ── PDF ──────────────────────────────────────────────────────────────────
    if nom.endswith(".pdf") or "pdf" in mime:
        try:
            import pypdf
            import io as _io
            reader = pypdf.PdfReader(_io.BytesIO(contenu))

            # Vérifier si le PDF est protégé/chiffré
            if reader.is_encrypted:
                raise ValueError(
                    "Le PDF est protégé par mot de passe et ne peut pas être lu. "
                    "Déprotégez-le avant de le soumettre."
                )

            texte = "\n\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()

            if not texte:
                # PDF scanné (image) : tenter l'OCR page par page via PyMuPDF si disponible
                try:
                    import fitz  # PyMuPDF
                    doc_fitz = fitz.open(stream=contenu, filetype="pdf")
                    pages_b64: list[str] = []
                    import base64
                    for page in doc_fitz:
                        pix = page.get_pixmap(dpi=150)
                        pages_b64.append(
                            base64.standard_b64encode(pix.tobytes("png")).decode()
                        )
                    # OCR sur la première page (meilleure représentativité)
                    if pages_b64:
                        texte_ocr = await _ocr_via_claude(
                            base64.standard_b64decode(pages_b64[0]), "image/png"
                        )
                        # OCR pages suivantes si nécessaire
                        for pg_b64 in pages_b64[1:6]:
                            t = await _ocr_via_claude(
                                base64.standard_b64decode(pg_b64), "image/png"
                            )
                            if t:
                                texte_ocr += "\n\n" + t
                        if texte_ocr.strip():
                            return texte_ocr[:50_000]
                except ModuleNotFoundError:
                    pass  # PyMuPDF non installé → message d'erreur clair
                except Exception as _e_ocr:
                    logger.warning(f"[TraductionFichier] OCR PDF échoué : {_e_ocr}")

                raise ValueError(
                    "Ce PDF ne contient pas de texte extractible (PDF scanné ou image). "
                    "Convertissez-le d'abord en PDF avec texte sélectionnable, "
                    "ou envoyez directement l'image (PNG/JPEG) pour l'OCR."
                )

            return texte[:50_000]
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Impossible de lire le PDF : {str(e)[:150]}")

    # ── DOCX ─────────────────────────────────────────────────────────────────
    if nom.endswith(".docx") or "wordprocessingml" in mime:
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(contenu))
            lignes = []
            for para in doc.paragraphs:
                if para.text.strip():
                    lignes.append(para.text)
            # Inclure les tableaux
            for table in doc.tables:
                for row in table.rows:
                    lignes.append(" | ".join(cell.text for cell in row.cells))
            return "\n".join(lignes)[:50_000]
        except Exception as e:
            raise ValueError(f"Impossible de lire le fichier Word : {e}")

    # ── TXT / MD / CSV texte ──────────────────────────────────────────────────
    if nom.endswith((".txt", ".md", ".csv")) or "text/" in mime:
        try:
            return contenu.decode("utf-8", errors="replace")[:50_000]
        except Exception:
            return contenu.decode("latin-1", errors="replace")[:50_000]

    # ── Excel / XLSX / XLS ───────────────────────────────────────────────────
    if nom.endswith((".xlsx", ".xls")) or "spreadsheet" in mime or "excel" in mime:
        try:
            import pandas as pd
            import io
            df = pd.read_excel(io.BytesIO(contenu), sheet_name=None)
            parties = []
            for sheet_name, sheet_df in df.items():
                parties.append(f"=== Feuille : {sheet_name} ===")
                parties.append(sheet_df.to_string(index=False))
            return "\n\n".join(parties)[:50_000]
        except Exception as e:
            raise ValueError(f"Impossible de lire le fichier Excel : {e}")

    # ── Images (PNG, JPEG, TIFF, BMP) → OCR via Claude Vision ───────────────
    if nom.endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif")) or "image/" in mime:
        return await _ocr_via_claude(contenu, mime or "image/png")

    # ── PPTX ─────────────────────────────────────────────────────────────────
    if nom.endswith(".pptx") or "presentationml" in mime:
        try:
            from pptx import Presentation
            import io
            prs = Presentation(io.BytesIO(contenu))
            lignes = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        lignes.append(shape.text.strip())
            return "\n".join(lignes)[:50_000]
        except Exception as e:
            raise ValueError(f"Impossible de lire le fichier PowerPoint : {e}")

    raise ValueError(
        f"Format non supporté : '{nom}'. Formats acceptés : PDF, DOCX, PPTX, TXT, CSV, XLSX, PNG, JPG."
    )


async def _detecter_registre(brief: str, contexte: str = "") -> dict:
    """Classe le registre d'un brief en une étape Haiku (~50ms, ~0.5 FCFA).

    Retourne un dict {registre, signataire_requis, ton, structure_hint} :
    - registre : "professionnel" | "familial" | "associatif" | "hommage" |
                 "celebration" | "religieux" | "educatif" | "personnel"
    - signataire_requis : bool — true uniquement si registre=professionnel
                          + contexte formel (contrat, convention, note interne…)
    - ton : "formel" | "neutre" | "chaleureux" | "intime" | "celebre"
    - structure_hint : court hint string pour guider la structure

    Permet à G1/ReportWriter d'adapter automatiquement template, signature,
    ton et structure sans dépendre du profil métier (qui peut être "Banquier"
    même quand le doc demandé est un compte-rendu de réunion familiale).

    Fallback gracieux : si Haiku échoue, retourne registre="professionnel"
    par défaut (comportement actuel — aucune régression).
    """
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        import json as _j
        prompt = (
            "Classe ce brief utilisateur en une catégorie de REGISTRE pour "
            "adapter le ton, la structure et la mise en forme du document "
            "généré.\n\n"
            f"BRIEF : « {brief[:800]} »\n"
            f"CONTEXTE EXTRAIT : « {(contexte or '')[:500]} »\n\n"
            "CATÉGORIES (choisis UNE valeur) :\n"
            "- professionnel : rapport entreprise, audit, contrat, note "
            "interne, convention, analyse business, étude marché.\n"
            "- familial : réunion famille, conseil familial, compte-rendu "
            "familial, événements intimes.\n"
            "- associatif : tontine, AG association, cercle, club, "
            "communauté, réunion quartier.\n"
            "- hommage : funérailles, deuil, commémoration, anniversaire "
            "de décès, hommage posthume.\n"
            "- celebration : mariage, naissance, baptême, anniversaire, "
            "fête, cérémonie joyeuse.\n"
            "- religieux : compte-rendu paroissial, réunion confrérie, "
            "synaxe, retraite spirituelle.\n"
            "- educatif : cours, formation, support pédagogique, "
            "manuel élève.\n"
            "- personnel : note personnelle, journal, mémo intime.\n\n"
            "RETOURNE JSON STRICT (sans markdown) :\n"
            '{"registre": "<categorie>", '
            '"signataire_requis": <true|false>, '
            '"ton": "<formel|neutre|chaleureux|intime|celebre>", '
            '"structure_hint": "<5-15 mots décrivant la structure attendue>"}\n\n'
            "signataire_requis = true UNIQUEMENT pour contrats, conventions, "
            "notes officielles, contre-rendus signables ; false pour tout le "
            "reste (familial, hommage, célébration, associatif, etc.)."
        )
        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
            json_attendu=True,
            max_tokens_override=300,
            utiliser_cache=True,
        )
        contenu = (rep.contenu or "{}").strip()
        try:
            data = _j.loads(contenu)
        except _j.JSONDecodeError:
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", contenu)
            data = _j.loads(m.group()) if m else {}
        registre = str(data.get("registre") or "professionnel").lower().strip()
        if registre not in (
            "professionnel", "familial", "associatif", "hommage",
            "celebration", "religieux", "educatif", "personnel",
        ):
            registre = "professionnel"
        return {
            "registre": registre,
            "signataire_requis": bool(data.get("signataire_requis", registre == "professionnel")),
            "ton": str(data.get("ton") or "neutre").lower()[:20],
            "structure_hint": str(data.get("structure_hint") or "")[:200],
        }
    except Exception as e:
        logger.debug(f"[DetectRegistre] échec gracieux : {e}")
        return {
            "registre": "professionnel",
            "signataire_requis": True,
            "ton": "formel",
            "structure_hint": "",
        }


async def _ocr_via_claude(image_bytes: bytes, mime_type: str) -> str:
    """
    Extrait le texte d'une image via Vision IA.
    Utilise ia_client.analyser_image() : GPT-4o Vision en primaire, Claude Vision en fallback.
    """
    import base64
    from core.ia_client import ia_client, ModeIA

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    try:
        # ia_client.analyser_image() gère GPT-4o primaire + Claude fallback automatiquement
        reponse = await ia_client.analyser_image_vision(
            image_b64=b64,
            prompt="Extrais tout le texte visible dans cette image. Retourne uniquement le texte extrait, sans commentaire.",
            mode=ModeIA.PRECISION,
        )
        return reponse.contenu if reponse else ""
    except Exception:
        # Fallback direct Claude si ia_client ne supporte pas analyser_image
        from config.settings import settings
        if not settings.CLAUDE_API_KEY or not settings.CLAUDE_API_KEY.startswith("sk-ant-"):
            return "[OCR indisponible — aucune clé Vision IA configurée]"
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}},
                    {"type": "text", "text": "Extrais tout le texte visible. Retourne uniquement le texte."},
                ],
            }],
        )
        return resp.content[0].text if resp.content else ""


# ── Constantes traduction grands documents ────────────────────────────────────
_CHUNK_CHARS   = 18_000   # ~4 500 tokens input par lot LLM
_BATCH_PARAS   = 60       # paragraphes max par lot DOCX/PPTX
_TIMEOUT_TRAD  = 180.0    # 3 minutes par appel LLM traduction
_MAX_TOK_TRAD  = 6_000    # tokens sortie par appel
_PARALLEL_MAX  = 4        # lots simultanés (rate-limit friendly)


async def _appeler_llm_traduction(prompt_sys: str, prompt_user: str) -> str:
    """
    Appel LLM dédié traduction : timeout 3 min, pas de retry,
    priorité Claude → fallback GPT-4o selon disponibilité.
    """
    import asyncio
    from config.settings import settings as _s

    # 1. Claude primaire (timeout long)
    key = getattr(_s, "CLAUDE_API_KEY", "") or ""
    if key.startswith("sk-ant-"):
        try:
            import anthropic as _ant
            client = _ant.AsyncAnthropic(api_key=key, timeout=_TIMEOUT_TRAD)
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=_MAX_TOK_TRAD,
                temperature=0.15,
                system=prompt_sys,
                messages=[{"role": "user", "content": prompt_user}],
            )
            return resp.content[0].text if resp.content else ""
        except Exception as _e:
            logger.warning(f"[Trad/Claude] échoué : {_e} → fallback GPT-4o")

    # 2. GPT-4o fallback (timeout long)
    if getattr(_s, "OPENAI_API_KEY", None):
        import openai as _oa
        client = _oa.AsyncOpenAI(api_key=_s.OPENAI_API_KEY, timeout=_TIMEOUT_TRAD, max_retries=0)
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system",  "content": prompt_sys},
                {"role": "user",    "content": prompt_user},
            ],
            max_tokens=_MAX_TOK_TRAD,
            temperature=0.15,
        )
        return resp.choices[0].message.content or ""

    raise RuntimeError("Aucun modèle IA disponible pour la traduction (clés manquantes ou épuisées)")


async def _traduire_texte_en_chunks(
    texte: str,
    src: str,
    dst: str,
    metier: str,
) -> str:
    """
    Traduit un texte de taille illimitée par lots parallèles (_CHUNK_CHARS par lot).
    Préserve l'ordre et réassemble.
    """
    import asyncio, re

    prompt_sys = (
        f"Tu es un traducteur professionnel expert en terminologie d'affaires africaine. "
        f"Tu traduis du {src} vers le {dst} avec une précision absolue. "
        f"Terminologie : {metier or 'professionnel africain (OHADA, CIMA, SYSCOHADA)'}. "
        f"Tu conserves titres, listes et tableaux. "
        f"Réponds UNIQUEMENT avec le texte traduit, sans préambule ni commentaire."
    )

    # Découper en chunks
    chunks = []
    for i in range(0, max(1, len(texte)), _CHUNK_CHARS):
        chunk = texte[i: i + _CHUNK_CHARS]
        if chunk.strip():
            chunks.append((len(chunks), chunk))

    if not chunks:
        return ""

    sema = asyncio.Semaphore(_PARALLEL_MAX)

    async def traduire_chunk(idx: int, texte_chunk: str) -> tuple[int, str]:
        async with sema:
            nb = len(chunks)
            pfx = f" (partie {idx + 1}/{nb})" if nb > 1 else ""
            prompt_user = f"Traduis du {src} vers le {dst}{pfx} :\n\n---\n{texte_chunk}\n---"
            trad = await _appeler_llm_traduction(prompt_sys, prompt_user)
            return idx, trad

    resultats = await asyncio.gather(*[traduire_chunk(i, c) for i, c in chunks])
    resultats_tries = sorted(resultats, key=lambda x: x[0])
    return "\n\n".join(t for _, t in resultats_tries)


def _remplacer_texte_paragraphe(para, nouveau_texte: str) -> None:
    """
    Remplace le texte d'un paragraphe python-docx EN PLACE.
    Préserve la mise en forme du premier run (police, taille, couleur, gras, italique…).
    Supprime les runs suivants pour éviter les doublons.
    """
    from docx.oxml.ns import qn

    p_elem = para._p
    r_tag  = qn("w:r")
    t_tag  = qn("w:t")
    XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

    runs = p_elem.findall(r_tag)

    if not runs:
        # Aucun run existant — ajouter simplement
        para.add_run(nouveau_texte)
        return

    # ── Écrire le texte traduit dans le premier run ────────────────────────────
    first_run = runs[0]
    t_elems = first_run.findall(t_tag)
    if t_elems:
        t_elems[0].text = nouveau_texte
        # Conserver les espaces de début/fin (attribut XML obligatoire)
        t_elems[0].set(XML_SPACE, "preserve")
        # Supprimer les w:t supplémentaires dans ce run
        for t in t_elems[1:]:
            first_run.remove(t)
    else:
        from lxml import etree
        t = etree.SubElement(first_run, t_tag)
        t.text = nouveau_texte
        t.set(XML_SPACE, "preserve")

    # ── Supprimer les runs suivants (le texte est maintenant dans runs[0]) ─────
    for run in runs[1:]:
        p_elem.remove(run)


async def _traduire_docx_avec_structure(
    contenu: bytes,
    langue_source: str,
    langue_cible: str,
    metier: str,
) -> tuple[bytes, str]:
    """
    Traduit un DOCX en préservant TOUTE la mise en forme (polices, tailles,
    couleurs, tableaux, en-têtes, pieds de page…).
    Supporte les documents de taille illimitée via batching + parallélisme.
    Retourne (bytes_docx_traduit, apercu_texte_traduit).
    """
    import io, re, asyncio
    from docx import Document

    doc = Document(io.BytesIO(contenu))

    # ── Collecter tous les paragraphes ────────────────────────────────────────
    paras: list = []
    for para in doc.paragraphs:
        if para.text.strip():
            paras.append(para)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if para.text.strip():
                        paras.append(para)
    for section in doc.sections:
        for hf in (section.header, section.footer,
                   section.even_page_header, section.even_page_footer,
                   section.first_page_header, section.first_page_footer):
            try:
                for para in hf.paragraphs:
                    if para.text.strip():
                        paras.append(para)
                for table in hf.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            for para in cell.paragraphs:
                                if para.text.strip():
                                    paras.append(para)
            except Exception:
                pass

    if not paras:
        raise ValueError("Document vide ou aucun texte extractible")

    src = LANGUES_NOM.get(langue_source, langue_source)
    dst = LANGUES_NOM.get(langue_cible, langue_cible)

    prompt_sys = (
        f"Tu es un traducteur professionnel expert. Tu traduis du {src} vers le {dst}. "
        f"RÈGLE ABSOLUE : conserve EXACTEMENT les balises §N§ au début de chaque ligne. "
        f"Ne modifie jamais le format §N§. Traduis uniquement le texte après la balise. "
        f"Ne fusionne pas les lignes. Ne supprime aucune ligne balisée. "
        f"Terminologie : {metier or 'professionnel africain (OHADA, CIMA, SYSCOHADA)'}."
    )
    pat = re.compile(r"§(\d+)§\s*(.*)")

    # ── Découper en lots de _BATCH_PARAS paragraphes (ou _CHUNK_CHARS chars) ──
    def faire_lots() -> list[list[tuple[int, object]]]:
        lots, lot_courant, chars = [], [], 0
        for i, p in enumerate(paras):
            n = len(p.text)
            if lot_courant and (len(lot_courant) >= _BATCH_PARAS or chars + n > _CHUNK_CHARS):
                lots.append(lot_courant)
                lot_courant, chars = [], 0
            lot_courant.append((i, p))
            chars += n
        if lot_courant:
            lots.append(lot_courant)
        return lots

    lots = faire_lots()
    logger.info(f"[Trad/DOCX] {len(paras)} paragraphes → {len(lots)} lots")

    sema = asyncio.Semaphore(_PARALLEL_MAX)

    async def traduire_lot(lot: list[tuple[int, object]]) -> dict[int, str]:
        texte_balise = "\n".join(f"§{i}§ {p.text}" for i, p in lot)
        prompt_user = (
            f"Traduis chaque ligne du {src} vers le {dst} en conservant les balises §N§ :\n\n"
            f"{texte_balise}"
        )
        async with sema:
            raw = await _appeler_llm_traduction(prompt_sys, prompt_user)

        traduits: dict[int, str] = {}
        for line in raw.split("\n"):
            m = pat.match(line.strip())
            if m:
                traduits[int(m.group(1))] = m.group(2).strip()

        # Fallback ligne-à-ligne si les balises sont ignorées
        if not traduits:
            lines_src = [p.text for _, p in lot]
            lines_trad = [l for l in raw.split("\n") if l.strip()]
            for (i, _), trad in zip(lot, lines_trad):
                traduits[i] = trad

        return traduits

    resultats = await asyncio.gather(*[traduire_lot(lot) for lot in lots])
    traduits_final: dict[int, str] = {}
    for d in resultats:
        traduits_final.update(d)

    # ── Appliquer les traductions EN PLACE ────────────────────────────────────
    for i, para in enumerate(paras):
        trad = traduits_final.get(i)
        if trad:
            _remplacer_texte_paragraphe(para, trad)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    apercu = " ".join(
        traduits_final.get(i, "") for i in range(min(80, len(paras)))
        if traduits_final.get(i, "").strip()
    )[:3000]
    return buf.read(), apercu


def _construire_docx_depuis_texte_traduit(texte: str, titre: str, src: str, dst: str) -> bytes:
    """
    Construit un DOCX propre depuis du texte traduit (non-DOCX source).
    Interprète les marqueurs Markdown : # ## ### - * 1.  et gras **...**
    pour recréer une structure lisible plutôt qu'un bloc de texte brut.
    """
    import io
    import re
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    doc.add_heading(f"{titre}", level=1)

    lines = texte.split("\n")
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("### "):
            doc.add_heading(s[4:], level=3)
        elif s.startswith("## "):
            doc.add_heading(s[3:], level=2)
        elif s.startswith("# "):
            doc.add_heading(s[2:], level=1)
        elif s.startswith(("- ", "• ", "* ")):
            try:
                doc.add_paragraph(s[2:], style="List Bullet")
            except Exception:
                doc.add_paragraph(s[2:])
        elif re.match(r"^\d+\.\s", s):
            try:
                doc.add_paragraph(s, style="List Number")
            except Exception:
                doc.add_paragraph(s)
        else:
            # Paragraphe normal — traiter le gras **...**
            p = doc.add_paragraph()
            parts = re.split(r"\*\*(.*?)\*\*", s)
            for j, part in enumerate(parts):
                run = p.add_run(part)
                if j % 2 == 1:  # Texte entre ** **
                    run.bold = True

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


async def _traduire_pptx_avec_structure(
    contenu: bytes,
    langue_source: str,
    langue_cible: str,
    metier: str,
) -> tuple[bytes, str]:
    """
    Traduit un PPTX en préservant la structure des slides (titres, corps, notes).
    Supporte les présentations de taille illimitée via batching + parallélisme.
    Retourne (bytes_pptx_traduit, apercu_texte_traduit).
    """
    import asyncio
    import io
    import re
    from pptx import Presentation

    prs = Presentation(io.BytesIO(contenu))
    src_name = LANGUES_NOM.get(langue_source, langue_source)
    dst_name = LANGUES_NOM.get(langue_cible, langue_cible)

    prompt_sys = (
        f"Tu es un traducteur professionnel expert en terminologie d'affaires africaine. "
        f"Tu traduis du {src_name} vers le {dst_name}. "
        f"RÈGLE ABSOLUE : conserve EXACTEMENT les balises §N§ au début de chaque ligne. "
        f"Ne modifie jamais le format §N§. Traduis uniquement le texte après la balise. "
        f"Terminologie : {metier or 'professionnel africain (OHADA, CIMA, SYSCOHADA)'}."
    )
    pat = re.compile(r"§(\d+)§\s*(.*)")

    # Extraire tous les textes indexés
    elements: list[dict] = []
    for si, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if not hasattr(shape, "text_frame"):
                continue
            for pi, para in enumerate(shape.text_frame.paragraphs):
                txt = "".join(r.text for r in para.runs)
                if txt.strip():
                    elements.append({"si": si, "shape_id": shape.shape_id, "pi": pi, "text": txt})

    if not elements:
        return contenu, ""

    # Découper en lots
    lots: list[list[int]] = []
    lot_courant: list[int] = []
    chars_courant = 0
    for i, elem in enumerate(elements):
        taille = len(elem["text"])
        if lot_courant and (len(lot_courant) >= _BATCH_PARAS or chars_courant + taille > _CHUNK_CHARS):
            lots.append(lot_courant)
            lot_courant, chars_courant = [], 0
        lot_courant.append(i)
        chars_courant += taille
    if lot_courant:
        lots.append(lot_courant)

    logger.info(f"[Trad/PPTX] {len(elements)} éléments → {len(lots)} lots")

    traductions: dict[int, str] = {}
    sema = asyncio.Semaphore(_PARALLEL_MAX)

    async def traduire_lot(indices: list[int]) -> None:
        numbered = "\n".join(f"§{i}§ {elements[i]['text']}" for i in indices)
        prompt_user = (
            f"Traduis chaque ligne ci-dessous du {src_name} vers le {dst_name} "
            f"en conservant les balises §N§ :\n\n{numbered}"
        )
        async with sema:
            raw = await _appeler_llm_traduction(prompt_sys, prompt_user)
        for line in raw.split("\n"):
            m = pat.match(line.strip())
            if m:
                traductions[int(m.group(1))] = m.group(2).strip()

    await asyncio.gather(*[traduire_lot(lot) for lot in lots])

    # Réinjecter dans le PPTX
    for i, elem in enumerate(elements):
        if i not in traductions:
            continue
        slide = prs.slides[elem["si"]]
        for shape in slide.shapes:
            if shape.shape_id == elem["shape_id"] and hasattr(shape, "text_frame"):
                try:
                    para = shape.text_frame.paragraphs[elem["pi"]]
                    if para.runs:
                        para.runs[0].text = traductions[i]
                        for run in para.runs[1:]:
                            run.text = ""
                except Exception:
                    pass
                break

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)

    apercu = " ".join(
        traductions.get(i, "") for i in range(min(80, len(elements)))
        if traductions.get(i, "").strip()
    )[:3000]
    return buf.read(), apercu


@router.post("/traduire-fichier", summary="Traduire un fichier uploadé")
async def traduire_fichier(
    fichier: UploadFile = File(..., description="Fichier à traduire (PDF, DOCX, TXT, XLSX, image...)"),
    langue_source: str = Form("fr"),
    langue_cible: str = Form("en"),
    contexte_metier: str = Form(""),
    format_sortie: str = Form("docx", description="texte | docx"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Traduit un fichier uploadé (PDF, DOCX, PPTX, TXT, CSV, XLSX, image).
    - Extrait le texte du fichier
    - Traduit avec terminologie métier africaine préservée
    - Retourne la traduction + génère optionnellement un DOCX téléchargeable
    """
    await _pre_check_credits(current_user.user_id, role=current_user.role)
    from modules.pro.service_profil import get_or_create, incrementer_stat

    # Vérification taille
    contenu = await fichier.read()
    taille_mb = len(contenu) / (1024 * 1024)
    if taille_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(413, f"Fichier trop volumineux ({taille_mb:.1f} MB). Maximum {MAX_FILE_SIZE_MB} MB.")

    if not fichier.filename:
        raise HTTPException(400, "Nom de fichier requis")

    # Récupération profil
    profil, _ = await get_or_create(current_user.user_id, db)
    metier = contexte_metier or getattr(profil, "metier", "") or ""

    src = LANGUES_NOM.get(langue_source, langue_source)
    dst = LANGUES_NOM.get(langue_cible, langue_cible)
    nom_fichier_base = Path(fichier.filename).stem
    nom_ext = Path(fichier.filename).suffix.lower()

    # Traduire + générer le fichier de sortie
    chemin_fichier_traduit = None
    texte_traduit = ""
    texte_source = ""
    sortie_bytes = b""
    ext_out = ".docx"
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    try:
        if nom_ext in (".docx", ".doc"):
            sortie_bytes, texte_traduit = await _traduire_docx_avec_structure(
                contenu=contenu,
                langue_source=langue_source,
                langue_cible=langue_cible,
                metier=metier,
            )
            texte_source = texte_traduit
            ext_out = ".docx"

        elif nom_ext == ".pptx":
            sortie_bytes, texte_traduit = await _traduire_pptx_avec_structure(
                contenu=contenu,
                langue_source=langue_source,
                langue_cible=langue_cible,
                metier=metier,
            )
            texte_source = texte_traduit
            ext_out = ".pptx"

        else:
            # PDF, TXT, CSV, XLSX, image → extraire le texte puis traduire en chunks
            try:
                texte_source = await _extraire_texte_fichier(fichier, contenu)
            except ValueError as e:
                raise HTTPException(422, str(e))
            except Exception as e:
                logger.error(f"[TraductionFichier] Extraction échouée : {e}")
                raise HTTPException(500, f"Erreur lors de la lecture du fichier : {str(e)[:200]}")

            if not texte_source.strip():
                raise HTTPException(422, "Aucun texte trouvé dans le fichier. Le fichier est peut-être vide ou chiffré.")

            texte_traduit = await _traduire_texte_en_chunks(
                texte=texte_source,
                src=src,
                dst=dst,
                metier=metier,
            )
            sortie_bytes = _construire_docx_depuis_texte_traduit(
                texte=texte_traduit,
                titre=f"Traduction {src} → {dst} : {nom_fichier_base}",
                src=src,
                dst=dst,
            )
            ext_out = ".docx"

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TraductionFichier] Erreur : {e}")
        raise HTTPException(500, f"Erreur lors de la traduction : {str(e)[:200]}")

    await incrementer_stat(current_user.user_id, "nb_traductions", db, xp_gain=2)
    nb_mots_src = len(texte_source.split()) if texte_source else 0
    await _debiter_credits_generation(
        user_id=current_user.user_id, db=db, module="traduction_fichier",
        tokens_input=max(500, nb_mots_src * 2),
        tokens_output=max(400, nb_mots_src * 2),
        modele="claude-sonnet-4-6",
        role=current_user.role,
    )

    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        reports_dir = _DATA_DIR / "pro_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        nom_out = f"traduction_{nom_fichier_base}_{langue_cible}_{ts}{ext_out}"
        chemin_out = reports_dir / nom_out
        chemin_out.write_bytes(sortie_bytes)
        chemin_fichier_traduit = nom_out  # Nom seul — le frontend construit l'URL
        logger.info(f"[TraductionFichier] Fichier traduit généré : {chemin_out}")

        # Sauvegarder dans Mes Documents
        await _sauvegarder_doc_genere(
            db=db,
            user_id=current_user.user_id,
            titre=f"Traduction {src}→{dst} : {nom_fichier_base}",
            type_doc="traduction",
            fichier=nom_out,
            contenu_genere=texte_traduit[:3000],
            meta={
                "langue_source": langue_source,
                "langue_cible": langue_cible,
                "fichier_source": fichier.filename,
                "format_sortie": ext_out.lstrip("."),
                "contexte_metier": metier,
            },
        )
    except Exception as e_doc:
        logger.warning(f"[TraductionFichier] Génération fichier échouée : {e_doc}")

    logger.info(
        f"[TraductionFichier] user={current_user.user_id} "
        f"fichier={fichier.filename} {langue_source}→{langue_cible} "
        f"mots_source={len(texte_source.split())} mots_cible={len(texte_traduit.split())}"
    )

    return {
        "fichier_source": fichier.filename,
        "langue_source": langue_source,
        "langue_cible": langue_cible,
        "nb_mots_source": len(texte_source.split()),
        "nb_mots_cible": len(texte_traduit.split()),
        "texte_traduit": texte_traduit,
        "chemin_docx": chemin_fichier_traduit,  # Compatibilité frontend existant
        "fichier_traduit": chemin_fichier_traduit,
        "format_sortie": (nom_ext.lstrip(".") if nom_ext in (".docx", ".pptx") else "docx"),
        "sauvegarde_mes_documents": chemin_fichier_traduit is not None,
        "contexte_metier": metier,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Routes Historique Documents Générés
# ══════════════════════════════════════════════════════════════════════════════

class SauvegarderDocumentRequest(BaseModel):
    titre: str = Field(..., min_length=3, max_length=200)
    type_doc: str = Field("rapport", description="rapport | slides | traduction | autre")
    fichier: Optional[str] = Field(None, description="Nom du fichier généré")
    contenu_source: Optional[str] = Field(None, description="Prompt / demande initiale")
    contenu_genere: Optional[str] = Field(None, description="Contenu markdown généré (aperçu)")
    session_id: Optional[str] = None
    meta: Optional[dict] = None


class MettreAJourDocumentRequest(BaseModel):
    titre: Optional[str] = None
    fichier: Optional[str] = None
    contenu_genere: Optional[str] = None
    contenu_source: Optional[str] = None
    meta: Optional[dict] = None


@router.get("/documents/historique", summary="Historique des documents générés")
async def historique_documents(
    limite: int = 50,
    offset: int = 0,
    type_doc: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne l'historique des documents générés par l'utilisateur, du plus récent au plus ancien."""
    from core.database import DocumentGenereDB

    q = select(DocumentGenereDB).where(
        DocumentGenereDB.user_id == current_user.user_id
    )
    if type_doc:
        q = q.where(DocumentGenereDB.type_doc == type_doc)
    q = q.order_by(desc(DocumentGenereDB.cree_le)).offset(offset).limit(min(limite, 100))

    result = await db.execute(q)
    docs = result.scalars().all()

    return {
        "total": len(docs),
        "documents": [
            {
                "id": d.id,
                "titre": d.titre,
                "type_doc": d.type_doc,
                "fichier": d.fichier,
                "contenu_source": d.contenu_source,
                "contenu_genere": (d.contenu_genere or "")[:500],
                "session_id": d.session_id,
                "meta": d.meta or {},
                "cree_le": d.cree_le.isoformat() if d.cree_le else None,
                "modifie_le": d.modifie_le.isoformat() if d.modifie_le else None,
            }
            for d in docs
        ],
    }


@router.post("/documents/", summary="Sauvegarder un document généré", status_code=201)
async def sauvegarder_document(
    req: SauvegarderDocumentRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sauvegarde un document généré dans l'historique persisté."""
    from core.database import DocumentGenereDB

    doc = DocumentGenereDB(
        user_id=current_user.user_id,
        titre=req.titre,
        type_doc=req.type_doc,
        fichier=req.fichier,
        contenu_source=req.contenu_source,
        contenu_genere=req.contenu_genere,
        session_id=req.session_id,
        meta=req.meta or {},
        cree_le=datetime.utcnow(),
        modifie_le=datetime.utcnow(),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    logger.info(f"[Documents] Sauvegardé doc={doc.id} user={current_user.user_id} titre='{req.titre}'")
    return {"id": doc.id, "titre": doc.titre, "cree_le": doc.cree_le.isoformat()}


@router.patch("/documents/{doc_id}", summary="Mettre à jour un document (version améliorée)")
async def mettre_a_jour_document(
    doc_id: int,
    req: MettreAJourDocumentRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Met à jour un document existant dans l'historique.
    Utilisé quand l'utilisateur demande à l'IA d'améliorer un document via le chat.
    """
    from core.database import DocumentGenereDB

    result = await db.execute(
        select(DocumentGenereDB).where(
            DocumentGenereDB.id == doc_id,
            DocumentGenereDB.user_id == current_user.user_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document introuvable")

    if req.titre is not None:
        doc.titre = req.titre
    if req.fichier is not None:
        doc.fichier = req.fichier
    if req.contenu_genere is not None:
        doc.contenu_genere = req.contenu_genere
    if req.contenu_source is not None:
        doc.contenu_source = req.contenu_source
    if req.meta is not None:
        doc.meta = {**(doc.meta or {}), **req.meta}
    doc.modifie_le = datetime.utcnow()

    await db.commit()
    return {"succes": True, "id": doc.id, "modifie_le": doc.modifie_le.isoformat()}


@router.delete("/documents/{doc_id}", summary="Supprimer un document de l'historique")
async def supprimer_document(
    doc_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Supprime un document de l'historique de l'utilisateur."""
    from core.database import DocumentGenereDB

    result = await db.execute(
        select(DocumentGenereDB).where(
            DocumentGenereDB.id == doc_id,
            DocumentGenereDB.user_id == current_user.user_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document introuvable")

    await db.delete(doc)
    await db.commit()
    return {"succes": True}


# ── Conversion de format de fichier ──────────────────────────────────────────

# Matrice de conversions supportées
CONVERSIONS_SUPPORTEES = {
    # source_ext → {cible_ext: description}
    ".pdf":  {".docx": "PDF → Word",  ".pptx": "PDF → PowerPoint", ".txt": "PDF → Texte"},
    ".docx": {".pdf": "Word → PDF",   ".pptx": "Word → PowerPoint", ".txt": "Word → Texte"},
    ".doc":  {".docx": "Doc → Docx",  ".txt": "Doc → Texte"},
    ".pptx": {".docx": "PowerPoint → Word", ".pdf": "PowerPoint → PDF", ".txt": "PowerPoint → Texte"},
    ".xlsx": {".docx": "Excel → Word", ".csv": "Excel → CSV",  ".txt": "Excel → Texte"},
    ".xls":  {".docx": "Excel → Word", ".csv": "Excel → CSV"},
    ".csv":  {".xlsx": "CSV → Excel",  ".docx": "CSV → Word"},
    ".txt":  {".docx": "Texte → Word", ".pdf": "Texte → PDF"},
    ".md":   {".docx": "Markdown → Word", ".html": "Markdown → HTML"},
    ".html": {".docx": "HTML → Word",  ".txt": "HTML → Texte"},
    ".odt":  {".docx": "ODT → Word"},
    ".rtf":  {".docx": "RTF → Word"},
    ".jpg":  {".docx": "Image → Word (OCR)", ".txt": "Image → Texte (OCR)"},
    ".jpeg": {".docx": "Image → Word (OCR)", ".txt": "Image → Texte (OCR)"},
    ".png":  {".docx": "Image → Word (OCR)", ".txt": "Image → Texte (OCR)"},
}


def _postprocess_docx_bullets(docx_bytes: bytes) -> bytes:
    """Correction minimale : ajoute uniquement l'indentation suspendue sur les
    paragraphes commençant par '-' ou '–'. Ne touche ni le texte ni les runs
    (pas de reconstruction), ce qui préserve gras, italique, couleurs et images."""
    import io, re
    from docx import Document as _Doc
    from docx.shared import Cm as _Cm, Pt as _Pt
    from docx.oxml.ns import qn as _qn

    _IMAGE_TAGS = {_qn('w:drawing'), _qn('w:pict'), _qn('w:object'), _qn('v:shape')}

    doc = _Doc(io.BytesIO(docx_bytes))

    for para in doc.paragraphs:
        txt = para.text.strip()
        if not txt:
            continue
        # Ne pas toucher les paragraphes contenant des images/formes
        if any(e.tag in _IMAGE_TAGS for e in para._p.iter()):
            continue
        # Ne pas toucher les textbox
        p = para._p.getparent()
        in_tb = False
        while p is not None:
            if p.tag == _qn('w:txbxContent'):
                in_tb = True; break
            p = p.getparent()
        if in_tb:
            continue

        pf = para.paragraph_format
        # Déjà indenté — laisser tranquille
        if pf.left_indent and pf.left_indent > _Cm(0.3):
            continue

        if re.match(r'^[-–]\s+\S', txt):        # "- texte" ou "– texte"
            pf.left_indent       = _Cm(0.9)
            pf.first_line_indent = _Cm(-0.9)
            pf.space_before      = _Pt(2)
        elif re.match(r'^[-–]\S', txt):          # "-texte" sans espace
            pf.left_indent       = _Cm(0.5)
            pf.first_line_indent = _Cm(-0.5)
            pf.space_before      = _Pt(2)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def _convertir_vers_docx(contenu: bytes, nom: str, ext_src: str) -> bytes:
    """Convertit n'importe quel format supporté vers DOCX en préservant la structure."""
    import io, re
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    # 1. Extraire le texte source
    texte = ""

    if ext_src in (".docx", ".doc"):
        # DOCX → DOCX : copie directe (déjà du DOCX)
        return contenu

    elif ext_src == ".pptx":
        from pptx import Presentation
        prs = Presentation(io.BytesIO(contenu))
        sections = []
        for i, slide in enumerate(prs.slides):
            titre_slide = ""
            corps_slide = []
            for shape in slide.shapes:
                if hasattr(shape, "text_frame"):
                    t = shape.text_frame.text.strip()
                    if not t:
                        continue
                    # Heuristique : première shape ou placeholder titre
                    if shape.shape_type == 13 or (not titre_slide and len(t) < 100):
                        titre_slide = t
                    else:
                        corps_slide.append(t)
            if titre_slide or corps_slide:
                sections.append({"titre": titre_slide or f"Slide {i+1}", "corps": corps_slide})

        # Reconstruire DOCX structuré depuis slides
        doc = Document()
        doc.add_heading(Path(nom).stem, level=1)
        for s in sections:
            doc.add_heading(s["titre"], level=2)
            for c in s["corps"]:
                for line in c.split("\n"):
                    if line.strip():
                        doc.add_paragraph(line.strip())
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    elif ext_src in (".xlsx", ".xls"):
        import pandas as pd
        xls = pd.ExcelFile(io.BytesIO(contenu))
        doc = Document()
        doc.add_heading(Path(nom).stem, level=1)
        for sheet_name in xls.sheet_names:
            df = xls.parse(sheet_name)
            doc.add_heading(f"Feuille : {sheet_name}", level=2)
            # Tableau Word
            cols = list(df.columns)
            tbl = doc.add_table(rows=1, cols=len(cols))
            try:
                tbl.style = "Table Grid"
            except Exception:
                pass
            for j, col in enumerate(cols):
                tbl.cell(0, j).text = str(col)
            for _, row in df.iterrows():
                row_cells = tbl.add_row().cells
                for j, val in enumerate(row):
                    row_cells[j].text = "" if str(val) == "nan" else str(val)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    elif ext_src == ".csv":
        import pandas as pd
        df = pd.read_csv(io.BytesIO(contenu), encoding="utf-8", errors="replace")
        doc = Document()
        doc.add_heading(Path(nom).stem, level=1)
        cols = list(df.columns)
        tbl = doc.add_table(rows=1, cols=len(cols))
        try:
            tbl.style = "Table Grid"
        except Exception:
            pass
        for j, col in enumerate(cols):
            tbl.cell(0, j).text = str(col)
        for _, row in df.iterrows():
            r = tbl.add_row().cells
            for j, val in enumerate(row):
                r[j].text = "" if str(val) == "nan" else str(val)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    elif ext_src == ".pdf":
        import tempfile, subprocess as _sp

        # ── Méthode 1 : pdf2docx (fidélité maximale : layout, images, tableaux) ──
        try:
            from pdf2docx import Converter as _Pdf2Docx
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as _tf_pdf:
                _tf_pdf.write(contenu)
                _pdf_path = _tf_pdf.name
            _docx_path = _pdf_path.replace(".pdf", ".docx")
            cv = _Pdf2Docx(_pdf_path)
            cv.convert(_docx_path, start=0, end=None)
            cv.close()
            import os
            result_bytes = Path(_docx_path).read_bytes()
            os.unlink(_pdf_path)
            os.unlink(_docx_path)
            return result_bytes
        except Exception as _e1:
            logger.warning(f"[Conversion] pdf2docx échoué ({_e1}) — fallback LibreOffice")

        # ── Méthode 2 : LibreOffice (fallback — très bonne fidélité aussi) ────────
        try:
            import os, tempfile
            _lo = r"C:\Program Files\LibreOffice\program\soffice.exe"
            if not Path(_lo).exists():
                raise FileNotFoundError("LibreOffice non trouvé")
            with tempfile.TemporaryDirectory() as _tmpdir:
                _pdf_tmp = Path(_tmpdir) / "source.pdf"
                _pdf_tmp.write_bytes(contenu)
                _sp.run(
                    [_lo, "--headless", "--convert-to", "docx",
                     "--outdir", _tmpdir, str(_pdf_tmp)],
                    timeout=60, check=True, capture_output=True,
                )
                _out = Path(_tmpdir) / "source.docx"
                if _out.exists():
                    return _out.read_bytes()
                raise FileNotFoundError("LibreOffice n'a pas produit de .docx")
        except Exception as _e2:
            logger.warning(f"[Conversion] LibreOffice échoué ({_e2}) — fallback fitz")

        # ── Méthode 3 : fitz (PyMuPDF) — extraction structurée texte/style ───────
        try:
            import fitz  # PyMuPDF
            from docx import Document as _Document
            from docx.shared import Pt as _Pt, RGBColor as _RGB
            from docx.oxml.ns import qn as _qn
            from docx.oxml import OxmlElement as _OxmlElement

            doc_pdf = fitz.open(stream=contenu, filetype="pdf")
            doc = _Document()
            for section in doc.sections:
                from docx.shared import Cm
                section.top_margin = Cm(2.5)
                section.bottom_margin = Cm(2.5)
                section.left_margin = Cm(2.5)
                section.right_margin = Cm(2.5)

            titre_doc = Path(nom).stem
            doc.add_heading(titre_doc, level=1)

            for page_num, page in enumerate(doc_pdf):
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        spans = line.get("spans", [])
                        if not spans:
                            continue
                        font_size = max(s.get("size", 11) for s in spans)
                        is_bold = any(
                            ("bold" in s.get("font", "").lower() or s.get("flags", 0) & 16)
                            for s in spans
                        )
                        line_text = "".join(s.get("text", "") for s in spans).strip()
                        if not line_text:
                            continue
                        if font_size >= 18:
                            doc.add_heading(line_text, level=1)
                        elif font_size >= 15:
                            doc.add_heading(line_text, level=2)
                        elif font_size >= 13:
                            doc.add_heading(line_text, level=3)
                        elif is_bold and font_size >= 11:
                            p = doc.add_paragraph()
                            run = p.add_run(line_text)
                            run.bold = True
                            run.font.size = _Pt(font_size)
                        else:
                            p = doc.add_paragraph()
                            for span in spans:
                                txt = span.get("text", "")
                                if not txt:
                                    continue
                                run = p.add_run(txt)
                                flags = span.get("flags", 0)
                                run.bold = bool(flags & 16) or "bold" in span.get("font", "").lower()
                                run.italic = bool(flags & 2)
                                run.font.size = _Pt(min(max(span.get("size", 11), 8), 28))
                                color = span.get("color", 0)
                                if color and color != 0:
                                    r = (color >> 16) & 0xFF
                                    g = (color >> 8) & 0xFF
                                    b = color & 0xFF
                                    run.font.color.rgb = _RGB(r, g, b)

                if page_num < len(doc_pdf) - 1:
                    _p = doc.add_paragraph()
                    _run = _p.add_run()
                    _br = _OxmlElement('w:br')
                    _br.set(_qn('w:type'), 'page')
                    _run._r.append(_br)

            doc_pdf.close()
            buf = io.BytesIO()
            doc.save(buf)
            return buf.getvalue()

        except Exception as _e:
            # Fallback pdfplumber si fitz échoue
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(contenu)) as pdf:
                    pages_texte = [p.extract_text() or "" for p in pdf.pages]
                texte = "\n\n".join(t for t in pages_texte if t.strip())
            except Exception:
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(contenu))
                    texte = "\n\n".join(p.extract_text() or "" for p in reader.pages)
                except Exception:
                    texte = "[Extraction PDF non disponible]"

    elif ext_src in (".html", ".htm"):
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(contenu.decode("utf-8", errors="replace"), "html.parser")
            texte = soup.get_text(separator="\n")
        except ImportError:
            texte = contenu.decode("utf-8", errors="replace")

    elif ext_src in (".txt", ".md", ".rtf", ".odt"):
        texte = contenu.decode("utf-8", errors="replace")

    elif ext_src in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        # OCR via Claude Vision
        import base64
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        b64 = base64.b64encode(contenu).decode()
        reponse = await ia_client.appeler(
            prompt="Extrait tout le texte visible dans cette image, en préservant la structure (titres, listes, tableaux).",
            mode=ModeIA.ANALYSE,
            forcer_modele=ModelePrioritaire.GPT4O,
            images_b64=[f"data:image/{ext_src.lstrip('.')};base64,{b64}"],
            max_tokens_override=4000,
        )
        texte = reponse.contenu if hasattr(reponse, "contenu") else str(reponse)
    else:
        texte = contenu.decode("utf-8", errors="replace")

    # Construire DOCX depuis le texte extrait
    if not texte.strip():
        texte = "[Aucun texte extractible depuis ce fichier]"
    return _construire_docx_depuis_texte_traduit(texte, Path(nom).stem, "source", "cible")


async def _convertir_vers_txt(contenu: bytes, nom: str, ext_src: str) -> bytes:
    """Extrait le texte brut vers TXT."""
    import io
    if ext_src in (".docx", ".doc"):
        from docx import Document
        doc = Document(io.BytesIO(contenu))
        return "\n".join(p.text for p in doc.paragraphs).encode("utf-8")
    elif ext_src == ".pptx":
        from pptx import Presentation
        prs = Presentation(io.BytesIO(contenu))
        lignes = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text_frame"):
                    lignes.append(shape.text_frame.text)
        return "\n".join(lignes).encode("utf-8")
    elif ext_src in (".xlsx", ".xls"):
        import pandas as pd
        df = pandas.read_excel(io.BytesIO(contenu))
        return df.to_string(index=False).encode("utf-8")
    elif ext_src == ".csv":
        return contenu  # déjà texte
    else:
        try:
            docx_bytes = await _convertir_vers_docx(contenu, nom, ext_src)
            from docx import Document
            doc = Document(io.BytesIO(docx_bytes))
            return "\n".join(p.text for p in doc.paragraphs).encode("utf-8")
        except Exception:
            return contenu


async def _convertir_vers_pptx(contenu: bytes, nom: str, ext_src: str) -> bytes:
    """Convertit PDF → PPTX.

    Cascade :
    1. LibreOffice --convert-to pptx  (meilleur résultat natif)
    2. fitz render page → image → slide (pixel-perfect, non éditable)
    3. fitz texte → python-pptx text boxes (dernier recours éditable)
    """
    import io, subprocess as _sp, tempfile

    if ext_src != ".pdf":
        raise ValueError(f"Seule la conversion PDF→PPTX est supportée (reçu {ext_src})")

    # ── Méthode 1 : LibreOffice ───────────────────────────────────────────────
    _lo = r"C:\Program Files\LibreOffice\program\soffice.exe"
    if Path(_lo).exists():
        try:
            with tempfile.TemporaryDirectory() as _tmpdir:
                _pdf_tmp = Path(_tmpdir) / "source.pdf"
                _pdf_tmp.write_bytes(contenu)
                _sp.run(
                    [_lo, "--headless", "--convert-to", "pptx",
                     "--outdir", _tmpdir, str(_pdf_tmp)],
                    timeout=120, check=True, capture_output=True,
                )
                _out = Path(_tmpdir) / "source.pptx"
                if _out.exists():
                    return _out.read_bytes()
        except Exception as _e1:
            logger.warning(f"[Conversion] LibreOffice PDF→PPTX échoué ({_e1}) — fallback images")

    # ── Méthode 2 : fitz render → images dans slides (pixel-perfect) ─────────
    try:
        import fitz
        from pptx import Presentation
        from pptx.util import Inches, Pt as _Pt2
        from pptx.enum.text import PP_ALIGN
        import base64

        doc_pdf = fitz.open(stream=contenu, filetype="pdf")
        prs = Presentation()

        # Détecter l'orientation de la 1ère page pour configurer la présentation
        first_page = doc_pdf[0]
        pw, ph = first_page.rect.width, first_page.rect.height
        if pw > ph:
            # Paysage
            prs.slide_width  = Inches(13.33)
            prs.slide_height = Inches(7.5)
        else:
            # Portrait
            prs.slide_width  = Inches(7.5)
            prs.slide_height = Inches(10.0)

        blank_layout = prs.slide_layouts[6]  # layout vide

        for page in doc_pdf:
            # 220 DPI → qualité suffisante pour grands écrans (FullHD/4K)
            mat = fitz.Matrix(220 / 72, 220 / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")

            slide = prs.slides.add_slide(blank_layout)
            # Insérer l'image pleine-diapositive
            from io import BytesIO as _BIO
            slide.shapes.add_picture(
                _BIO(img_bytes),
                left=0, top=0,
                width=prs.slide_width,
                height=prs.slide_height,
            )

        doc_pdf.close()
        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()

    except Exception as _e2:
        logger.warning(f"[Conversion] fitz→images PPTX échoué ({_e2}) — fallback texte")

    # ── Méthode 3 : fitz texte → python-pptx text boxes ──────────────────────
    import fitz
    from pptx import Presentation
    from pptx.util import Inches, Pt as _Pt3, Emu
    from pptx.dml.color import RGBColor as _PRGB

    doc_pdf = fitz.open(stream=contenu, filetype="pdf")
    prs = Presentation()
    prs.slide_width  = Inches(13.33)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    for page in doc_pdf:
        slide = prs.slides.add_slide(blank_layout)
        blocks = page.get_text("dict")["blocks"]
        page_w, page_h = page.rect.width, page.rect.height
        slide_w = prs.slide_width
        slide_h = prs.slide_height
        scale_x = slide_w / page_w
        scale_y = slide_h / page_h

        for block in blocks:
            if block.get("type") != 0:
                continue
            bx0, by0, bx1, by1 = block["bbox"]
            bw = max(bx1 - bx0, 10)
            bh = max(by1 - by0, 10)
            txBox = slide.shapes.add_textbox(
                int(bx0 * scale_x), int(by0 * scale_y),
                int(bw * scale_x), int(bh * scale_y),
            )
            tf = txBox.text_frame
            tf.word_wrap = True
            first_para = True
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                p = tf.paragraphs[0] if first_para else tf.add_paragraph()
                first_para = False
                for span in spans:
                    txt = span.get("text", "")
                    if not txt:
                        continue
                    from pptx.util import Pt as _Pt3
                    run = p.add_run()
                    run.text = txt
                    flags = span.get("flags", 0)
                    run.font.bold   = bool(flags & 16) or "bold" in span.get("font", "").lower()
                    run.font.italic = bool(flags & 2)
                    sz = min(max(int(span.get("size", 11)), 6), 48)
                    run.font.size = _Pt3(sz)
                    color = span.get("color", 0)
                    if color:
                        r = (color >> 16) & 0xFF
                        g = (color >> 8) & 0xFF
                        b = color & 0xFF
                        run.font.color.rgb = _PRGB(r, g, b)

    doc_pdf.close()
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


async def _convertir_vers_csv(contenu: bytes, ext_src: str) -> bytes:
    """Convertit Excel → CSV."""
    import io, pandas as pd
    if ext_src in (".xlsx", ".xls"):
        df = pd.read_excel(io.BytesIO(contenu))
        return df.to_csv(index=False).encode("utf-8")
    return contenu


async def _convertir_vers_xlsx(contenu: bytes, ext_src: str) -> bytes:
    """Convertit CSV → Excel."""
    import io, pandas as pd
    if ext_src == ".csv":
        df = pd.read_csv(io.BytesIO(contenu), encoding="utf-8", errors="replace")
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        return buf.getvalue()
    return contenu


@router.post("/convertir-fichier", summary="Convertir un fichier vers un autre format")
async def convertir_fichier(
    fichier: UploadFile = File(..., description="Fichier à convertir"),
    format_cible: str = Form(..., description="Format cible : docx, pdf, txt, csv, xlsx, pptx"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Convertit un fichier vers un autre format en préservant la structure :
    - PDF → DOCX, TXT
    - DOCX → TXT, CSV
    - PPTX → DOCX, TXT
    - XLSX/XLS → CSV, DOCX, TXT
    - CSV → XLSX, DOCX
    - Images → DOCX, TXT (via OCR Claude Vision)
    - TXT/MD → DOCX
    """
    await _pre_check_credits(current_user.user_id, role=current_user.role)
    contenu = await fichier.read()
    if len(contenu) > 50 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (max 50 MB)")

    nom = fichier.filename or "fichier"
    ext_src = Path(nom).suffix.lower()
    ext_cible = f".{format_cible.lower().lstrip('.')}"

    logger.info(f"[Conversion] {ext_src} → {ext_cible} : {nom}")

    # Vérification support
    cibles_supportees = CONVERSIONS_SUPPORTEES.get(ext_src, {})
    if not cibles_supportees:
        raise HTTPException(422, f"Format source non supporté : {ext_src}. Formats acceptés : {', '.join(CONVERSIONS_SUPPORTEES.keys())}")
    if ext_cible not in cibles_supportees:
        raise HTTPException(422, f"Conversion {ext_src} → {ext_cible} non supportée. Cibles possibles : {', '.join(cibles_supportees.keys())}")

    # Si source == cible, retourner directement
    if ext_src == ext_cible:
        raise HTTPException(400, "Le format source et cible sont identiques")

    try:
        # ── Effectuer la conversion ────────────────────────────────────────────
        if ext_cible == ".docx":
            sortie_bytes = await _convertir_vers_docx(contenu, nom, ext_src)
        elif ext_cible == ".pptx":
            sortie_bytes = await _convertir_vers_pptx(contenu, nom, ext_src)
        elif ext_cible == ".txt":
            sortie_bytes = await _convertir_vers_txt(contenu, nom, ext_src)
        elif ext_cible == ".csv":
            sortie_bytes = await _convertir_vers_csv(contenu, ext_src)
        elif ext_cible == ".xlsx":
            sortie_bytes = await _convertir_vers_xlsx(contenu, ext_src)
        elif ext_cible == ".pdf":
            # PDF via libreoffice si disponible, sinon DOCX intermédiaire
            try:
                import subprocess
                docx_bytes = await _convertir_vers_docx(contenu, nom, ext_src)
                _DATA_DIR.mkdir(parents=True, exist_ok=True)
                tmp_docx = _DATA_DIR / "tmp_conv.docx"
                tmp_docx.write_bytes(docx_bytes)
                subprocess.run(
                    ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(_DATA_DIR), str(tmp_docx)],
                    check=True, timeout=30, capture_output=True,
                )
                pdf_path = _DATA_DIR / "tmp_conv.pdf"
                if pdf_path.exists():
                    sortie_bytes = pdf_path.read_bytes()
                    pdf_path.unlink(missing_ok=True)
                    tmp_docx.unlink(missing_ok=True)
                else:
                    raise FileNotFoundError("PDF non généré par LibreOffice")
            except Exception as e_pdf:
                logger.warning(f"[Conversion] PDF via LibreOffice échoué ({e_pdf}) — fallback DOCX")
                sortie_bytes = await _convertir_vers_docx(contenu, nom, ext_src)
                ext_cible = ".docx"
        else:
            raise HTTPException(422, f"Format cible {ext_cible} non encore implémenté")

        # ── Sauvegarder le fichier converti ───────────────────────────────────
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        reports_dir = _DATA_DIR / "pro_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        nom_base = Path(nom).stem
        nom_sortie = f"conv_{nom_base}_{ts}{ext_cible}"
        chemin_sortie = reports_dir / nom_sortie
        chemin_sortie.write_bytes(sortie_bytes)

        # Sauvegarder dans Mes Documents
        await _sauvegarder_doc_genere(
            db=db, user_id=current_user.user_id,
            titre=f"Conversion {ext_src.upper()} → {ext_cible.upper()} : {nom_base}",
            type_doc="conversion",
            fichier=nom_sortie,
            contenu_genere=f"Converti depuis {nom}",
            meta={"format_source": ext_src, "format_cible": ext_cible, "fichier_source": nom},
        )

        # Forfait non-LLM pour la conversion (I/O + python-docx) — complexité ∝ taille
        try:
            from modules.pro.service_credits import debiter_forfait_fcfa
            taille_mo = max(1, len(sortie_bytes) // (1024 * 1024))
            await debiter_forfait_fcfa(
                user_id=current_user.user_id,
                cout_fcfa=1.0 * taille_mo,      # ~1 FCFA/Mo × marge 20×
                module="conversion_fichier",
            )
        except Exception as _e:
            logger.debug(f"[Credits/Conversion] forfait non bloquant: {_e}")

        return {
            "fichier_converti": nom_sortie,
            "format_source": ext_src,
            "format_cible": ext_cible,
            "taille_octets": len(sortie_bytes),
            "sauvegarde_mes_documents": True,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[Conversion] Erreur : {exc}", exc_info=True)
        raise HTTPException(500, f"Erreur lors de la conversion : {str(exc)[:300]}")


# ═════════════════════════════════════════════════════════════════════════════
# Sprint G1 — Auto-orchestrateur génération documents YukpoPro.
# ═════════════════════════════════════════════════════════════════════════════
# L'utilisateur tape un brief en langage naturel + (optionnel) uploade des
# fichiers. Sonnet 4.6 détecte intent + template + mode + format + langue,
# retourne un devis estimé. Le frontend (ChatPage) affiche la carte de
# confirmation, puis si l'user confirme, appelle l'endpoint cible avec
# payload_pret en bypass.
# ═════════════════════════════════════════════════════════════════════════════

# Catalogue des templates pro (synchronisé avec _STRUCTURES de
# modules/pro/report_writer_pro.py — source de vérité côté backend).
# (id, type_sortie, label, métier dominant, mots-clés indicatifs).
#
# IMPORTANT : tout type_id présent ici DOIT exister dans _STRUCTURES sinon
# ReportWriterPro fallback sur "rapport_analyse" — c'est exactement le bug
# qui faisait que toutes les conventions étaient générées comme des rapports.
_CATALOGUE_TEMPLATES_G1 = [
    # ── Rapports d'analyse / synthèse ────────────────────────────────────
    ("rapport_audit",     "rapport", "Rapport d'audit",         "auditeur",   "audit interne externe contrôle CIMA OHADA"),
    ("rapport_financier", "rapport", "Rapport financier",       "DAF",        "états financiers bilan compte résultat trésorerie"),
    ("note_de_synthese",  "rapport", "Note de synthèse",        "analyste",   "synthèse résumé executif briefing condensé"),
    ("rapport_analyse",   "rapport", "Rapport d'analyse",       "analyste",   "analyse données performance KPI étude"),
    ("plan_action",       "rapport", "Plan d'action",           "consultant", "plan stratégique roadmap mesures actions"),
    ("compte_rendu",      "rapport", "Compte-rendu",            "secretaire", "CR réunion compte-rendu PV délibération"),
    ("rapport_rh",        "rapport", "Rapport RH",              "DRH",        "ressources humaines social bilan effectifs"),
    ("note_juridique",    "rapport", "Note juridique",          "juriste",    "note juridique avis légal analyse droit OHADA"),
    # ── Documents JURIDIQUES STRUCTURÉS (Préambule / Articles / Signatures) ──
    ("convention",          "rapport", "Convention",                "juriste", "convention partenariat collaboration accord protocole MOU"),
    ("contrat_bail",        "rapport", "Contrat de bail",           "juriste", "bail location commercial habitation immobilier loyer"),
    ("contrat_travail",     "rapport", "Contrat de travail",        "DRH",     "contrat travail CDI CDD embauche salarié employé"),
    ("contrat_prestation",  "rapport", "Contrat de prestation",     "juriste", "prestation service freelance consultant honoraires"),
    ("contrat_vente",       "rapport", "Contrat de vente",          "juriste", "vente cession achat acquisition bien"),
    ("contrat_generique",   "rapport", "Contrat générique",         "juriste", "contrat accord engagement partie clauses"),
    ("statuts",             "rapport", "Statuts de société",        "juriste", "statuts SARL SA SAS création société entreprise OHADA"),
    ("reglement_interieur", "rapport", "Règlement intérieur",       "juriste", "règlement intérieur entreprise discipline procédures"),
    # ── Lettres / courriers officiels ────────────────────────────────────
    ("lettre_officielle",       "rapport", "Lettre officielle",       "secretaire", "lettre officielle administration courrier formel"),
    ("lettre_commerciale",      "rapport", "Lettre commerciale",      "commercial", "lettre commerciale prospection offre"),
    ("lettre_mise_en_demeure",  "rapport", "Lettre de mise en demeure","juriste",    "mise en demeure huissier dette impayé sommation"),
    ("lettre_resiliation",      "rapport", "Lettre de résiliation",   "secretaire", "résiliation contrat fin abonnement"),
    ("lettre_emploi",           "rapport", "Lettre de motivation/CV", "candidat",   "candidature emploi motivation CV"),
    ("attestation",             "rapport", "Attestation",             "secretaire", "attestation employeur travail présence salaire"),
    ("certificat",              "rapport", "Certificat",              "secretaire", "certificat scolaire médical conformité"),
    # ── Présentations / slides ───────────────────────────────────────────
    ("slides_executive",  "slides",  "Présentation direction",   "directeur",  "présentation CA résultats trimestriels conseil"),
    ("slides_commercial", "slides",  "Présentation commerciale", "commercial", "pitch produit présentation client offre"),
    ("slides_formation",  "slides",  "Présentation formation",   "formateur",  "support formation cours pédagogique"),
    ("slides_projet",     "slides",  "Présentation projet",      "chef projet","présentation projet jalons livrables"),
    # ── Visuels imprimables / Designer Pro (PDF print-ready CMYK) ────────
    # Tout ce qui est CARTE DE VISITE, FLYER, AFFICHE, BROCHURE, LIVRET,
    # MENU, PROGRAMME, CV graphique, INVITATION, FAIRE-PART, packaging,
    # banderole, kakemono, dépliant, etc. → route vers Designer Pro
    # (/api/v1/bureau/infographie-pro/generer-auto). PAS un Word/PPTX.
    ("infographie_carte_visite", "visuel", "Carte de visite",       "tous",   "carte visite business card 8 cartes A4 vCard QR"),
    ("infographie_flyer",        "visuel", "Flyer / Affiche",       "tous",   "flyer affiche A3 A4 A5 poster banderole campagne pub"),
    ("infographie_brochure",     "visuel", "Brochure / Plaquette",  "tous",   "brochure plaquette dépliant 3 volets corporate"),
    ("infographie_livret",       "visuel", "Livret / Programme",    "tous",   "livret faire-part mariage décès programme cérémonie"),
    ("infographie_menu",         "visuel", "Menu restaurant",       "resto",  "menu carte restaurant entrées plats desserts"),
    ("infographie_cv_graphique", "visuel", "CV graphique",          "candidat","CV graphique designer portfolio profil"),
    ("infographie_invitation",   "visuel", "Invitation / Save-the-date", "tous", "invitation save the date événement gala"),
    ("infographie_packaging",    "visuel", "Packaging produit",     "marque", "packaging emballage étiquette produit"),
    ("infographie_post_social",  "visuel", "Post réseaux sociaux",  "marketing","post Instagram LinkedIn Facebook story banner"),
    ("infographie_album",        "visuel", "Album / Livre photo",   "tous",   "album photo livre photo magazine portfolio"),
    ("infographie_rapport_visuel","visuel","Rapport annuel visuel", "marketing","rapport annuel magazine 24 32 pages corporate visuel"),
    ("infographie_custom",       "visuel", "Visuel sur mesure",     "tous",   "visuel imprimable autre BD packaging dépliant custom format"),
]
_CREDITS_PAR_MODE_G1 = {"flash": 2000, "standard": 4500, "complet": 12000, "expert": 25000}
_DUREE_PAR_MODE_G1 = {"flash": 120, "standard": 300, "complet": 900, "expert": 1500}


class DemandeOrchestrer(BaseModel):
    brief: str = Field(..., min_length=10,
        description="Description en langage naturel du document souhaité")
    contexte_fichiers: Optional[str] = Field(default=None,
        description="Texte déjà extrait des fichiers uploadés (côté frontend)")
    langue_forcee: Optional[str] = Field(default=None,
        description="Force une langue cible (sinon auto-détection)")
    type_sortie_force: Optional[str] = Field(default=None,
        description="Force 'rapport' ou 'slides' (sinon auto)")
    mode_force: Optional[str] = Field(default=None,
        description="(legacy) Force un mode hardcodé. Préférer 'ambition' libre.")
    ambition: Optional[str] = Field(default=None,
        description="Brief libre sur la profondeur attendue. Ex: "
                    "'court 2 pages', 'exhaustif comme un livre blanc', "
                    "'détaillé pour conseil d'administration'. Le LLM "
                    "dimensionne tokens / sections en conséquence — pas de "
                    "plafond arbitraire de mode (flash/standard/complet/expert).")


@router.post("/orchestrer", summary="Sprint G1 — Auto-orchestrateur génération documents")
async def orchestrer_generation_doc(
    demande: DemandeOrchestrer,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sprint G1 — Reçoit un brief utilisateur, détecte automatiquement le type
    d'output (rapport/slides), le template précis dans le catalogue, le mode,
    le format et la langue, et retourne un devis prêt-à-l'emploi.

    Le ChatPage affiche la carte de confirmation, puis appelle l'endpoint cible
    (`/rapports/generer` ou `/slides/generer`) avec `payload_pret` (zéro choix
    manuel pour l'utilisateur).

    Coût LLM : ~2k tokens in + 500 out (Sonnet) = ~$0.013 = 7.8 FCFA réel.
    Forfait `copilote_orchestrer` ≈ 1 FCFA → 12 FCFA user → marge 1.5×.
    Loss leader assumé : marge récupérée sur la génération qui suit.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    from modules.pro.service_credits import (
        verifier_solde_suffisant, debiter_forfait_fcfa,
    )
    import json as _json
    import re as _re

    ok, restants, _plan, _msg = await verifier_solde_suffisant(current_user.user_id)
    if not ok:
        raise HTTPException(402,
            f"CREDITS_EPUISES|restants={int(restants)}|orchestrer requiert au moins 10 crédits")

    catalogue_str = "\n".join(
        f"- {tid} ({ttype}) : {tlabel} — métier {tmetier} — mots-clés : {tkw}"
        for (tid, ttype, tlabel, tmetier, tkw) in _CATALOGUE_TEMPLATES_G1
    )
    contexte_block = ""
    if demande.contexte_fichiers:
        ctx = demande.contexte_fichiers[:8000]
        contexte_block = f"\n\nCONTEXTE FICHIERS UPLOADÉS :\n{ctx}\n"

    if demande.ambition:
        ambition_block = (f"L'utilisateur a précisé : « {demande.ambition} » "
                          f"— adapte tokens et sections en conséquence.")
    else:
        ambition_block = ("Pas d'indication explicite — déduis le "
                          "dimensionnement du brief lui-même.")

    # Phase 3 — Contexte vertical métier (profil + fallback brief si vide)
    bloc_vertical_g1 = ""
    try:
        from modules.pro.service_profil import get_or_create as _get_profil
        from modules.bureau import verticales_metier as _vm
        async with async_session_maker() as _db:
            profil_obj, _ = await _get_profil(current_user.user_id, _db)
        metier = getattr(profil_obj, "metier", None) or ""
        secteur = getattr(profil_obj, "secteur_activite", None) or ""
        pays_user = getattr(profil_obj, "pays", None) or None
        # Verticalité DYNAMIQUE LLM : couvre TOUS les secteurs mondiaux
        descripteur_vert = await _vm.detecter_vertical_dynamique_llm(
            metier=metier, secteur=secteur,
            pays=pays_user, brief=demande.brief,
        )
        if descripteur_vert:
            bloc_vertical_g1 = _vm.construire_bloc_prompt_vertical(
                pays=pays_user, descripteur=descripteur_vert,
            )
    except Exception:
        pass

    prompt = f"""Tu es directeur de production documentaire. Analyse ce brief et retourne
un JSON STRICT décrivant exactement ce que tu vas produire.

BRIEF UTILISATEUR :
\"\"\"{demande.brief}\"\"\"
{contexte_block}{bloc_vertical_g1}
CATALOGUE DES TEMPLATES PRÉDÉFINIS (à privilégier si l'un correspond) :
{catalogue_str}

⚠️ FLEXIBILITÉ TOTALE — si AUCUN template du catalogue ne correspond
   parfaitement au besoin de l'utilisateur, tu DOIS générer une
   structure SUR MESURE en mettant template_id="custom" et en remplissant
   le champ "structure_custom" avec une liste de 5-15 sections adaptées
   précisément au brief. Cette flexibilité permet à Yukpo de produire
   N'IMPORTE QUEL type de document : manuel utilisateur, charte éthique,
   livre blanc, mémoire technique, dossier de candidature, appel d'offres,
   étude de faisabilité, business plan détaillé, document pédagogique,
   etc. Tu adaptes le plan, le ton et la structure au besoin réel de l'user.

   Quand utiliser un template du catalogue :
   - Le label du template décrit EXACTEMENT le document demandé
   - Les mots-clés du template apparaissent explicitement dans le brief
   - Le format imposé (rapport, contrat, lettre, slides) correspond à
     ce que l'user attend

   Quand basculer en custom :
   - Le brief décrit un document hybride / spécifique non couvert
   - L'user demande un format particulier (ex: "manuel en 6 chapitres",
     "dossier de presse 10 pages", "cahier des charges technique")
   - Aucun mot-clé du catalogue ne se retrouve dans le brief

REGLES :
1. template_id = EXACTEMENT un id du catalogue ci-dessus (jamais inventer).

   ⚠️ CRITIQUE — distinction RAPPORT vs SLIDES vs INFOGRAPHIE :
   Trois grandes familles d'output. La famille décide l'endpoint backend.

   FAMILLE INFOGRAPHIE (visuel imprimable PDF print-ready CMYK) — route
   vers Designer Pro. Le brief décrit un OBJET VISUEL/IMPRIMABLE :
   - Cartes de visite (1 ou plusieurs personnes, recto-verso, vCard QR…)
   - Flyer, affiche, poster, banderole, kakemono, billboard
   - Brochure, plaquette commerciale, dépliant 2/3 volets
   - Livret événement (faire-part mariage/décès, programme cérémonie/culte)
   - Menu de restaurant, carte des vins
   - CV graphique design, portfolio créatif
   - Invitation, save-the-date, ticket événement
   - Packaging produit, étiquette, dosette
   - Post réseaux sociaux (Instagram, LinkedIn, Facebook story/feed)
   - Album photo, livre photo, magazine, rapport annuel VISUEL
   - BD éducative, infographie ludique, mind map, schéma

   Mots-clés déclencheurs (non exhaustifs) : "carte de visite", "flyer",
   "affiche", "brochure", "plaquette", "dépliant", "livret",
   "faire-part", "invitation", "menu", "programme", "CV graphique",
   "packaging", "post Instagram", "story", "album", "magazine",
   "imprimable", "imprimerie", "CMYK", "print", "bleed", "marges
   techniques", "à imprimer", "format A3/A4/A5/A6/carré", "8 cartes
   par feuille", "recto-verso plié", "QR vCard".

   → type_sortie = "visuel", template_id = un id "infographie_*"
     du catalogue (carte_visite, flyer, brochure, livret, menu,
     cv_graphique, invitation, packaging, post_social, album,
     rapport_visuel, OU custom pour briefs atypiques).

   ⚠️ NE JAMAIS confondre :
   - "5 cartes de visite imprimables" → INFOGRAPHIE (PAS un rapport
     Word qui *présente* les cartes de visite en texte !)
   - "flyer A3 anti-tabac" → INFOGRAPHIE (PAS un rapport sur le tabac)
   - "menu de restaurant" → INFOGRAPHIE (PAS un rapport sur le menu)
   - "CV graphique designer" → INFOGRAPHIE (PAS un rapport CV)
   - "brochure produit" → INFOGRAPHIE (PAS un rapport produit)

   ⚠️ DISTINCTION RAPPORT vs DOCUMENT JURIDIQUE :
   - Si le brief mentionne explicitement « convention », « contrat »,
     « bail », « statuts », « règlement », « accord », « MOU » → utilise
     le template juridique structuré correspondant (convention, contrat_bail,
     contrat_travail, contrat_prestation, contrat_vente, contrat_generique,
     statuts, reglement_interieur). Ces templates produisent un format
     « Préambule / Parties / Articles numérotés / Signatures » conforme
     au droit OHADA.
   - Si le brief mentionne « note juridique », « avis juridique »,
     « analyse juridique » → note_juridique (rapport d'analyse, pas
     contrat). Ce n'est PAS la même chose qu'une convention.
   - Si le brief mentionne « lettre », « courrier », « mise en demeure »,
     « attestation », « certificat » → utilise le template lettre_* /
     attestation / certificat correspondant (PAS un rapport).
   - rapport_analyse / rapport_audit / rapport_financier / rapport_rh /
     plan_action / compte_rendu / note_de_synthese : uniquement pour de
     vrais rapports d'analyse, JAMAIS pour des contrats ou conventions.

2. type_sortie ∈ rapport | slides | visuel | traduction_texte | traduction_fichier | ocr.
   - "rapport" : DOCX (rapports d'analyse, contrats, lettres, attestations)
   - "slides" : PPTX (présentations direction/commercial/formation/projet)
   - "visuel" : PDF print-ready CMYK (visuels imprimables Designer Pro :
     cartes de visite, flyers, brochures, livrets, menus, CV graphique,
     invitations, packaging, posts réseaux sociaux, albums, etc.)
   - "traduction_texte" : l'user demande de traduire un TEXTE saisi
     inline dans le chat (sans fichier attaché). Ex : "Traduis ceci en
     anglais : Bonjour, comment allez-vous ?". Préserve la structure
     du texte, terminologie métier africaine SYSCOHADA/OHADA si pertinent.
   - "traduction_fichier" : l'user a JOINT un fichier (PDF/DOCX/XLSX/TXT)
     et demande sa traduction. Ex : "Traduis ce contrat en anglais"
     avec un .docx en pièce. Le backend préserve mise en page, styles,
     tableaux. NE PAS produire un nouveau document — traduire en place.
   - "ocr" : l'user a joint une IMAGE (photo, scan, capture) ou un PDF
     scanné et demande l'extraction / la transcription du texte. Ex :
     "Scanne cette facture et extrais les données", "Transcris ce
     manuscrit". Le backend rend un DOCX structuré.

   ⚠️ DISTINCTION CRITIQUE :
   - "Traduis ce contrat en anglais" + fichier joint → traduction_fichier
   - "Rédige un contrat en anglais" → rapport (génération from scratch)
   - "Voici ma facture scannée, lis-la" → ocr
   - "Fais-moi une facture-modèle" → rapport
   - "Traduis cette phrase : ..." (texte inline) → traduction_texte

3. **dimensionnement libre — tu décides** la profondeur réelle attendue
   en lisant le brief :
   - nb_sections_cible : 3 (mémo court) à 30 (livre blanc), selon le besoin réel
   - tokens_output_estimes : 800 (note rapide) à 100 000 (mémoire exhaustif)
   - nb_pages_estimees : déduit des tokens (~1 page = ~600 tokens output)
   Tu N'ES PAS contraint par les anciens modes flash/standard/complet/expert.
   Tu dimensionnes **librement** selon le brief :
     • "Note rapide pour réunion"             → 3-5 sections, 800-2000 tokens
     • "Compte-rendu trimestriel"             → 6-10 sections, 4000-8000 tokens
     • "Audit comptable annuel détaillé"      → 12-20 sections, 15000-30000 tokens
     • "Mémoire technique appel d'offres 80p" → 25-30 sections, 50000-90000 tokens
     • "Convention 2 articles simple"         → 4 sections, 600-1200 tokens
     • "Statuts SARL OHADA complets"          → 15-25 sections, 8000-20000 tokens
   La SEULE limite réelle est le solde crédits de l'utilisateur (vérifié plus
   tard par le backend). Toi tu produis l'estimation honnête.
4. mode_recommande : déduit-le de tokens_output_estimes :
   - <= 2000 tokens   → "flash"
   - <= 8000 tokens   → "standard"
   - <= 25000 tokens  → "complet"
   - > 25000 tokens   → "expert"
   (utilisé uniquement comme alias technique pour le backend, pas comme
    plafond — la vraie source de vérité = tokens_output_estimes)
5. format_sortie : "docx" pour rapports/contrats/lettres, "pptx" pour slides,
   "markdown" si demandé explicitement.
6. langue : ISO court (fr/en/es/pt/ar/de/zh/sw/wo/ha/ln/am/ru/hi/tr) — auto-détection.
7. parametres_extraits : entités explicites du brief uniquement (parties
   contractantes, dates, montants, lieu, objet, durée, etc.).
8. credits_estimes : calculé à partir des tokens (~1 cr = 5 tokens output) +
   un overhead sections × 100 cr. Formule simple :
     credits_estimes = (tokens_output_estimes / 5) + (nb_sections_cible × 100)
   Ex : 8000 tokens + 8 sections → 1600 + 800 = 2400 cr
9. duree_estimee_secondes : tokens_output / 100 (Sonnet débite ~100 tok/s)
   minimum 60s, maximum 1800s.

⚠️ AMBITION UTILISATEUR : {ambition_block}

FORMAT JSON STRICT :
{{
  "intent_detecte": "generation_rapport" | "generation_slides" | "generation_visuel" | "traduction_texte" | "traduction_fichier" | "ocr" | "ambigu",
  "type_sortie": "rapport" | "slides" | "visuel" | "traduction_texte" | "traduction_fichier" | "ocr",
  "template_id": "id_du_catalogue OU 'custom' si rien ne convient",
  "template_label": "Label humain (ex: 'Manuel utilisateur logiciel ERP')",
  "structure_custom": ["Section 1", "Section 2", "..."],  // dimensionne LIBREMENT (3 à 30 sections selon le brief), obligatoire si template_id="custom"
  "tokens_output_estimes": 8000,                          // 800 (note brève) à 100000 (mémoire exhaustif)
  "nb_pages_estimees": 13,                                // dérivé : tokens_output / 600
  "mode_recommande": "flash" | "standard" | "complet" | "expert",  // alias backend (≤2000=flash, ≤8000=standard, ≤25000=complet, >25000=expert)
  "format_sortie": "docx" | "pptx" | "markdown",
  "langue": "fr|en|...",
  "parametres_extraits": {{ "nom_entreprise": "...", "periode": "..." }},
  "credits_estimes": 4500,                                // = (tokens_output / 5) + (nb_sections × 100)
  "duree_estimee_secondes": 80,                           // = max(60, min(1800, tokens_output / 100))
  "raisonnement_court": "Pourquoi ce dimensionnement (1 phrase max, en français)"
}}

EXEMPLES de structure_custom (à adapter au brief réel) :
- Manuel utilisateur ERP : ["Présentation du logiciel", "Installation et configuration",
  "Module Comptabilité", "Module Facturation", "Module Stock", "Gestion des utilisateurs",
  "Sauvegarde et restauration", "Dépannage", "Support technique", "Annexes"]
- Cahier des charges technique : ["Contexte du projet", "Périmètre fonctionnel",
  "Exigences fonctionnelles", "Exigences non-fonctionnelles", "Architecture cible",
  "Contraintes techniques", "Planning prévisionnel", "Budget", "Critères de recette",
  "Annexes"]
- Charte éthique entreprise : ["Préambule", "Nos valeurs", "Engagement envers les clients",
  "Respect des collaborateurs", "Lutte contre la corruption", "Protection des données",
  "Développement durable", "Application et sanctions", "Contacts conformité"]

Retourne UNIQUEMENT le JSON, sans commentaire, sans markdown."""

    try:
        # Opus 4.7 — orchestration = "directeur de production documentaire" qui
        # comprend l'intention métier réelle, distingue carte de visite imprimable
        # vs rapport texte sur des cartes, slides exécutifs vs DOCX synthèse, etc.
        # Sonnet hésitait sur les cas atypiques. Opus tranche correctement.
        # Fallback gpt-4-turbo si Anthropic indispo (même tier raisonnement).
        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.PRECISION,
            json_attendu=True,
            forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
            max_tokens_override=1500,
        )
        contenu = rep.contenu or "{}"
        try:
            data = _json.loads(contenu)
        except _json.JSONDecodeError:
            m = _re.search(r"\{.*\}", contenu, _re.DOTALL)
            data = _json.loads(m.group()) if m else {}
    except Exception as e:
        logger.error(f"[G1/Orchestrer] Échec LLM : {e}")
        raise HTTPException(500, f"Orchestration échouée : {str(e)[:200]}")

    ids_valides = {tid for (tid, *_) in _CATALOGUE_TEMPLATES_G1}
    template_id = data.get("template_id") or "rapport_analyse"
    structure_custom = data.get("structure_custom")

    # Cas spécial : template_id = "custom" ⇒ on utilise structure_custom
    # générée par le LLM (flexibilité totale, document sur-mesure).
    if template_id == "custom":
        if not (isinstance(structure_custom, list) and len(structure_custom) >= 3):
            # LLM a dit "custom" sans fournir de structure → fallback
            template_id = "rapport_analyse"
            structure_custom = None
            data["template_id"] = template_id
    elif template_id not in ids_valides:
        # template inconnu hors catalogue : on tente d'inférer depuis le LLM
        # → si structure_custom existe, on bascule en custom
        if isinstance(structure_custom, list) and len(structure_custom) >= 3:
            template_id = "custom"
            data["template_id"] = "custom"
        else:
            type_s = data.get("type_sortie") or "rapport"
            candidats = [t for t in _CATALOGUE_TEMPLATES_G1 if t[1] == type_s]
            template_id = candidats[0][0] if candidats else "rapport_analyse"
            data["template_id"] = template_id
            structure_custom = None

    if demande.type_sortie_force in ("rapport", "slides"):
        data["type_sortie"] = demande.type_sortie_force
    if demande.langue_forcee:
        data["langue"] = demande.langue_forcee
    if demande.mode_force in _CREDITS_PAR_MODE_G1:
        data["mode_recommande"] = demande.mode_force

    # Dimensionnement DYNAMIQUE (le LLM décide) — pas de plafond hardcodé.
    # On lit en priorité tokens_output_estimes ; on déduit le mode pour
    # rétrocompatibilité backend, mais c'est tokens qui est la source.
    tokens_output_est = int(data.get("tokens_output_estimes") or 0)
    nb_sections_cible = 0
    sc = data.get("structure_custom")
    if isinstance(sc, list):
        nb_sections_cible = len(sc)

    if tokens_output_est <= 0:
        # Fallback : on utilise mode hardcodé si LLM n'a pas dimensionné.
        mode_rec_legacy = data.get("mode_recommande") or "standard"
        tokens_output_est = {
            "flash": 1500, "standard": 6000, "complet": 18000, "expert": 50000,
        }.get(mode_rec_legacy, 6000)

    # Déduction du mode_recommande à partir des tokens (alias backend)
    if tokens_output_est <= 2000:
        mode_rec = "flash"
    elif tokens_output_est <= 8000:
        mode_rec = "standard"
    elif tokens_output_est <= 25000:
        mode_rec = "complet"
    else:
        mode_rec = "expert"

    # Crédits = formule tokens + sections (jamais de plafond arbitraire)
    credits_calcules = (tokens_output_est // 5) + (nb_sections_cible * 100)
    credits_estimes = max(500, int(data.get("credits_estimes") or credits_calcules))

    # Durée estimée = tokens / vitesse Sonnet (~100 tok/s), borné [60, 1800]
    duree_calculee = max(60, min(1800, tokens_output_est // 100))
    duree_estimee = int(data.get("duree_estimee_secondes") or duree_calculee)

    fcfa_user = int(credits_estimes * 0.6)
    solde_credits = float(restants)
    peut_payer = solde_credits >= credits_estimes

    type_sortie = data.get("type_sortie") or "rapport"
    # Sécurité : si template_id pointe sur infographie_* mais type_sortie="rapport"
    # (LLM hésitant), corriger automatiquement le type_sortie.
    if isinstance(template_id, str) and template_id.startswith("infographie_"):
        type_sortie = "visuel"
        data["type_sortie"] = "visuel"
    if type_sortie == "slides":
        endpoint_cible = "/api/v1/pro/slides/generer"
        payload_pret = {
            "type_doc": template_id.replace("slides_", ""),
            "instruction": demande.brief,
            "mode": mode_rec,
            "langue": data.get("langue") or "fr",
            "format_sortie": data.get("format_sortie") or "pptx",
        }
    elif type_sortie == "visuel":
        # FREEFORM unique — le LLM compose des primitives géométriques sans
        # template rigide, supporte TOUT visuel imprimable (carte visite 8-up,
        # flyer A3, BD, packaging, CV graphique, post social, affiche, dépliant,
        # custom). Designer Pro classique reste accessible via son endpoint
        # direct /api/v1/bureau/infographie-pro/* mais on ne route plus les
        # demandes ambiguës vers son custom_libre (qui force-fit sur des
        # PAGE_TEMPLATES inadaptés et produit du junk).
        # Pour les livrets/brochures/menus rodés, le LLM Freeform compose un
        # layout adapté ; pour les cas atypiques, idem — flexibilité totale.
        endpoint_cible = "/api/v1/bureau/freeform/generer"
        payload_pret = {
            "brief": demande.brief,
            "pays": "CM",
            "langue": data.get("langue") or "fr",
            "export_cmyk": True,
        }
    elif type_sortie == "traduction_texte":
        # Traduction d'un texte inline (sans fichier joint). Le brief
        # contient le texte à traduire. Langue cible déduite par le LLM
        # depuis le brief (par défaut anglais si origine fr, sinon fr).
        langue_source = (data.get("langue") or "fr").lower()
        langue_cible_extr = (data.get("parametres_extraits") or {}).get("langue_cible")
        if not langue_cible_extr:
            langue_cible_extr = "en" if langue_source == "fr" else "fr"
        endpoint_cible = "/api/v1/pro/traduire"
        payload_pret = {
            "contenu": demande.brief,
            "langue_source": langue_source,
            "langue_cible": str(langue_cible_extr).lower()[:5],
            "format_sortie": data.get("format_sortie") or "docx",
            "sujet": (data.get("template_label") or "Traduction")[:200],
        }
    elif type_sortie == "traduction_fichier":
        # Traduction d'un fichier joint. Le frontend uploadera le fichier
        # via POST multipart sur cet endpoint. file_field_hints contient
        # les variantes possibles ; le ChatPage gère l'upload côté client.
        langue_source = (data.get("langue") or "fr").lower()
        langue_cible_extr = (data.get("parametres_extraits") or {}).get("langue_cible")
        if not langue_cible_extr:
            langue_cible_extr = "en" if langue_source == "fr" else "fr"
        endpoint_cible = "/api/v1/pro/traduire-fichier"
        payload_pret = {
            "langue_source": langue_source,
            "langue_cible": str(langue_cible_extr).lower()[:5],
        }
    elif type_sortie == "ocr":
        # OCR : l'utilisateur a joint une image/PDF scanné. Le ChatPage
        # uploadera le fichier en multipart. On utilise l'endpoint /bureau/ocr/
        # scanner qui gère aussi bien images photo, scans, captures écran.
        endpoint_cible = "/api/v1/bureau/ocr/scanner"
        payload_pret = {
            "langue": (data.get("langue") or "fr").lower()[:5],
        }
    else:
        endpoint_cible = "/api/v1/pro/rapports/generer"
        # ── Détection registre (Haiku ~50ms, ~0.5 FCFA absorbé) ─────────────
        # Évite que l'app force un template "compte-rendu professionnel" pour
        # une réunion de famille, une cérémonie d'hommage, une AG associative,
        # etc. Si le registre n'est pas pro, on bascule sur template "custom"
        # qui laisse le LLM dériver la structure depuis le brief réel.
        registre_meta = await _detecter_registre(
            brief=demande.brief,
            contexte=(demande.contexte_fichiers or "")[:1500],
        )
        template_effectif = template_id
        if registre_meta["registre"] != "professionnel":
            template_effectif = "custom"
        # Le backend /rapports/generer attend `sujet` + `type_rapport`, pas
        # `instruction`/`type_doc`. On formate le payload conformément.
        payload_pret = {
            "sujet":         demande.brief,
            "type_rapport":  template_effectif,
            "mode":          mode_rec,
            "format_sortie": data.get("format_sortie") or "docx",
            # Source de vérité du dimensionnement — sera honoré par
            # ReportWriterPro plutôt que les valeurs hardcodées des modes.
            "tokens_max_output": int(tokens_output_est),
            # Métadonnées registre propagées vers ReportWriterPro pour
            # adapter ton/structure/signature/cachet sans hardcodage.
            "registre":           registre_meta["registre"],
            "signataire_requis":  registre_meta["signataire_requis"],
            "ton":                registre_meta["ton"],
        }
        if registre_meta.get("structure_hint"):
            payload_pret["structure_hint"] = registre_meta["structure_hint"]
        # Si l'orchestrateur a généré une structure sur-mesure (template
        # custom), on la transmet via le param structure_externe — sans
        # limite arbitraire de 20 sections (cap technique 50 = safety).
        if template_effectif == "custom" and isinstance(structure_custom, list) and structure_custom:
            payload_pret["structure_externe"] = [str(s)[:120] for s in structure_custom][:50]

    params_extraits = data.get("parametres_extraits") or {}
    if isinstance(params_extraits, dict) and params_extraits:
        # Sérialiser les paramètres extraits dans le contexte texte (le
        # backend /rapports/generer accepte un champ contexte multi-line)
        ctx_lines = [f"{k} : {v}" for k, v in params_extraits.items() if v]
        if ctx_lines:
            payload_pret["contexte"] = "\n".join(ctx_lines)[:2000]

    try:
        await debiter_forfait_fcfa(
            user_id=current_user.user_id,
            cout_fcfa=1.0,
            module="copilote_orchestrer",
        )
    except Exception as _e:
        logger.debug(f"[G1/Orchestrer] forfait non bloquant : {_e}")

    fallback = None
    if not peut_payer:
        ordre = ["flash", "standard", "complet", "expert"]
        try:
            idx = ordre.index(mode_rec)
            for i in range(idx - 1, -1, -1):
                cand_mode = ordre[i]
                cand_credits = _CREDITS_PAR_MODE_G1[cand_mode]
                if solde_credits >= cand_credits:
                    fallback = {
                        "mode": cand_mode,
                        "credits": cand_credits,
                        "fcfa_user": int(cand_credits * 0.6),
                    }
                    break
        except ValueError:
            pass

    # ── PLAN d'exécution complet (architecture data-driven, plan-driven) ──
    # Le frontend NE FAIT AUCUN string matching sur intent_detecte/type_sortie.
    # Il lit `plan` et exécute aveuglément : POST plan.endpoint avec plan.payload,
    # affiche plan.label, extrait le fichier via plan.file_field_hints.
    # Le LLM (Opus 4.7) compose entièrement la décision : peu importe que ce
    # soit rapport, slides, visuel imprimable, vidéo, traduction ou tout autre
    # endpoint futur, le frontend n'a pas à connaître les types métier.
    template_label = data.get("template_label") or template_id.replace("_", " ").title()
    type_resultat = (
        "pdf"  if type_sortie == "visuel"
        else "pptx" if type_sortie == "slides"
        else "txt"  if type_sortie == "traduction_texte" and (data.get("format_sortie") or "docx") == "texte"
        else "docx"  # rapport, traduction_*, ocr → DOCX par défaut
    )
    # Endpoints qui exigent un upload multipart (fichier joint) plutôt
    # qu'un POST JSON. Le frontend détecte ce flag et reconstruit la
    # requête en FormData en injectant le fichier joint par l'utilisateur.
    needs_file_upload = type_sortie in ("traduction_fichier", "ocr")
    upload_field_name = "fichier"  # nom du champ FormData attendu par les deux endpoints concernés

    # Pattern de téléchargement par type d'endpoint final
    if endpoint_cible.startswith("/api/v1/pro/"):
        dl_pattern = "/api/v1/pro/generateurs/fichier/{fichier}"
    elif endpoint_cible.startswith("/api/v1/bureau/ocr"):
        dl_pattern = "/api/v1/bureau/ocr/fichier/{fichier}"
    else:
        dl_pattern = "/api/v1/bureau/documents/{fichier}"

    plan = {
        "label": template_label,
        "explication_user": data.get("raisonnement_court") or "",
        "endpoint": endpoint_cible,
        "method": "POST",
        "payload": payload_pret,
        "type_resultat": type_resultat,
        # Sprint chat-everything : l'endpoint exige un upload multipart
        # avec le fichier joint par l'utilisateur (traduction_fichier, OCR).
        # Le frontend regarde ce flag et construit une requête FormData.
        "needs_file_upload": needs_file_upload,
        "upload_field_name": upload_field_name,
        # Indices au frontend pour extraire le fichier de la réponse, dans
        # l'ordre de priorité. Le frontend essaye chaque clé jusqu'à hit.
        "file_field_hints": [
            "fichier_genere", "fichier", "pdf_id",
            "fichier_id", "url_telechargement", "download_url",
        ],
        # Construction de l'URL finale pour téléchargement direct (le
        # frontend peut concaténer si besoin).
        "download_url_pattern": dl_pattern,
    }

    return {
        # Champs legacy conservés pour compat ascendante (anciens clients) :
        "intent_detecte":         data.get("intent_detecte") or "generation_rapport",
        "type_sortie":            type_sortie,
        "template_id":            template_id,
        "template_label":         template_label,
        "mode_recommande":        mode_rec,
        "format_sortie":          data.get("format_sortie") or ("pptx" if type_sortie == "slides" else "docx"),
        "langue":                 data.get("langue") or "fr",
        "parametres_extraits":    params_extraits,
        "credits_estimes":        credits_estimes,
        "fcfa_user":              fcfa_user,
        "duree_estimee_secondes": duree_estimee,
        "credits_disponibles":    int(solde_credits),
        "peut_payer":             peut_payer,
        "fallback_si_solde_insuffisant": fallback,
        "endpoint_cible":         endpoint_cible,
        "payload_pret":           payload_pret,
        "raisonnement":           data.get("raisonnement_court") or "",
        "structure_custom":       structure_custom if template_id == "custom" else None,
        "tokens_output_estimes":  int(tokens_output_est),
        "nb_pages_estimees":      max(1, int(tokens_output_est) // 600),
        "nb_sections_cible":      nb_sections_cible or None,
        # NEW : plan exécutable — la source de vérité pour le frontend
        "plan":                   plan,
    }


@router.post("/orchestrer-multipart", summary="Sprint G1 — Orchestrateur avec fichiers joints (images, PDF, DOCX, XLSX…)")
async def orchestrer_avec_fichiers(
    brief:         str               = Form(..., description="Brief utilisateur (langage naturel)"),
    langue_forcee: Optional[str]     = Form(default=None),
    type_sortie_force: Optional[str] = Form(default=None),
    mode_force:    Optional[str]     = Form(default=None),
    ambition:      Optional[str]     = Form(default=None),
    fichiers:      List[UploadFile]  = File(default=[], description="Fichiers source (images manuscrites/scans, PDF, DOCX, XLSX, CSV, TXT, PPTX)"),
    current_user:  TokenData         = Depends(get_current_user),
    db:            AsyncSession      = Depends(get_db),
):
    """
    Variante multipart de `/orchestrer` qui accepte des fichiers joints :
    - images (.jpg/.jpeg/.png/.heic/.webp/…) → OCR Vision GPT-4o/Claude pour
      extraire texte manuscrit, scans, captures, photos de documents.
    - documents (.pdf/.docx/.xlsx/.csv/.txt/.pptx) → extraction native.

    Le texte extrait est concaténé dans `contexte_fichiers` avant d'être
    passé au LLM orchestrateur pour qu'il comprenne la vraie intention. Le
    payload final (rapport/slides/visuel/traduction…) hérite du contexte
    dans `payload_pret["contexte"]` afin que la rédaction en aval s'appuie
    sur le contenu réel des fichiers, pas sur leur nom.

    Permet par exemple : « génère le rapport Word de cette réunion à partir
    de ces photos manuscrites » → OCR des photos → contexte injecté →
    rapport rédigé sur le contenu transcrit.
    """
    blocs_contexte: list[str] = []
    for f in fichiers or []:
        if not f or not f.filename:
            continue
        try:
            contenu = await f.read()
            if not contenu:
                continue
            txt = await _extraire_texte_upload(contenu, f.filename, user_id=current_user.user_id)
            if txt and not txt.startswith("["):
                blocs_contexte.append(f"### Fichier : {f.filename}\n{txt.strip()}")
            elif txt:
                # message d'erreur extraction — on l'inclut quand même pour traçabilité
                blocs_contexte.append(f"### Fichier : {f.filename}\n{txt}")
        except Exception as e:
            logger.warning(f"[OrchestrerMultipart] Échec extraction {f.filename} : {e}")
            blocs_contexte.append(f"### Fichier : {f.filename}\n[Erreur extraction : {e}]")

    contexte_fichiers = "\n\n".join(blocs_contexte) if blocs_contexte else None
    # Cap pour éviter d'exploser le prompt LLM (l'orchestrateur tronque
    # déjà à 8000 chars mais on garde le texte intégral pour réinjection
    # dans le payload aval).
    contexte_complet = contexte_fichiers
    contexte_pour_orchestre = (contexte_fichiers[:8000] if contexte_fichiers else None)

    demande = DemandeOrchestrer(
        brief=brief,
        contexte_fichiers=contexte_pour_orchestre,
        langue_forcee=langue_forcee,
        type_sortie_force=type_sortie_force,
        mode_force=mode_force,
        ambition=ambition,
    )
    resultat = await orchestrer_generation_doc(
        demande=demande, current_user=current_user, db=db,
    )

    # Injecter le contexte EXTRAIT (intégral, pas tronqué 8k) dans le
    # payload final pour que la génération aval (rapport/slides/visuel)
    # rédige à partir du contenu réel des fichiers. La rédaction lit
    # `contexte` ou `sources_externes` selon le pipeline.
    if isinstance(resultat, dict) and contexte_complet:
        payload = resultat.get("payload_pret") or {}
        if isinstance(payload, dict):
            # Concatène avec contexte existant si déjà rempli (params extraits)
            ctx_existant = payload.get("contexte") or ""
            cap = 60_000  # ~15k tokens — supporté par GPT-4-turbo / Opus
            new_ctx = (f"{ctx_existant}\n\n" if ctx_existant else "") + contexte_complet
            payload["contexte"] = new_ctx[:cap]
            resultat["payload_pret"] = payload
            # Met à jour aussi plan.payload si le frontend lit depuis là
            plan = resultat.get("plan") or {}
            if isinstance(plan, dict):
                plan_payload = plan.get("payload") or {}
                if isinstance(plan_payload, dict):
                    plan_payload["contexte"] = payload["contexte"]
                    plan["payload"] = plan_payload
                    resultat["plan"] = plan
            resultat["fichiers_extraits"] = [
                {"nom": f.filename, "taille_extrait": len(b)}
                for f, b in zip(fichiers or [], blocs_contexte)
            ]

    return resultat
