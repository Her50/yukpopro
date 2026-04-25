"""Routes Documents — génération Word, PDF, PPT, Excel, Analyse Excel, Rapports + Historique"""
import os
import time
import json
import logging
from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import base64

from modules.documents.generateur import document_generateur
from core.auth import TokenData, get_current_user, require_permission
from config.settings import settings

logger = logging.getLogger("yukpo_assurance.api.documents")

router = APIRouter(dependencies=[Depends(require_permission("documents"))])


async def _pre_check_credits_doc(user_id: int) -> None:
    """Pré-check crédits avant traitement coûteux. Lève 402 CREDITS_EPUISES si épuisé."""
    try:
        from modules.pro.service_credits import verifier_solde_suffisant
        ok, _r, _p, msg = await verifier_solde_suffisant(user_id)
        if not ok:
            raise HTTPException(status_code=402, detail=msg)
    except HTTPException:
        raise
    except Exception as _e:
        logger.debug(f"[Credits/PreCheck] non bloquant: {_e}")


async def _debiter_forfait_doc(user_id: int, cout_fcfa: float, module: str) -> None:
    """Débite un forfait FCFA non-LLM (la marge 20× est appliquée par service_credits)."""
    try:
        from modules.pro.service_credits import debiter_forfait_fcfa
        ok, _c, msg = await debiter_forfait_fcfa(user_id=user_id, cout_fcfa=cout_fcfa, module=module)
        if not ok:
            raise HTTPException(status_code=402, detail=msg)
    except HTTPException:
        raise
    except Exception as _e:
        logger.debug(f"[Credits/Forfait/{module}] non bloquant: {_e}")


async def _debiter_llm_doc(
    user_id: int,
    module: str,
    tokens_input: int,
    tokens_output: int,
    modele: str = "claude-sonnet-4-6",
) -> None:
    """Débite la consommation LLM réelle (marge 20× appliquée par service_credits)."""
    try:
        from modules.pro.service_credits import verifier_et_debiter
        ok, _c, msg = await verifier_et_debiter(
            user_id=user_id, modele=modele,
            tokens_input=tokens_input, tokens_output=tokens_output,
            module=module,
        )
        if not ok:
            raise HTTPException(status_code=402, detail=msg)
    except HTTPException:
        raise
    except Exception as _e:
        logger.debug(f"[Credits/LLM/{module}] non bloquant: {_e}")

# ─── Rate limiter par user_id (pas par IP) ────────────────────────────────────
# Clé = user_id → isolation par tenant, résistant aux proxies/NAT partagés
_DOC_IA_RATE: dict[int, list[float]] = defaultdict(list)
_DOC_IA_MAX_PAR_MINUTE = 6   # 6 générations IA par minute par utilisateur


def _verifier_rate_limit_documents(user_id: int) -> None:
    """Rate limit : max 6 générations documents IA par minute par user_id."""
    maintenant = time.time()
    historique = _DOC_IA_RATE[user_id]
    historique[:] = [t for t in historique if maintenant - t < 60]
    if len(historique) >= _DOC_IA_MAX_PAR_MINUTE:
        raise HTTPException(
            429,
            f"Trop de générations de documents (max {_DOC_IA_MAX_PAR_MINUTE}/min). "
            "Attendez avant de relancer."
        )
    historique.append(maintenant)


class GenerationRequest(BaseModel):
    outline: dict           # Structure JSON complète du document


class GenerationIARequest(BaseModel):
    demande: str            # Description en langage naturel
    document_type: str = "docx"
    contexte: Optional[dict] = None
    theme: str = "blue"


class RapportSinistreRequest(BaseModel):
    donnees_sinistre: dict


class PresentationCARequest(BaseModel):
    donnees: dict
    titre: str = "Revue de Performance"


class TableauBordRequest(BaseModel):
    donnees: dict


class RapportCIMARequest(BaseModel):
    donnees: dict
    annee: int


@router.post("/generer")
async def generer_document(req: GenerationRequest):
    """
    Génère un document depuis un outline JSON complet.
    Formats : docx, pdf, pptx, xlsx.
    """
    doc = await document_generateur.generer(req.outline)
    if not doc:
        raise HTTPException(500, "Échec de la génération du document")
    return doc


@router.post("/generer-depuis-prompt")
async def generer_depuis_prompt(
    req: GenerationIARequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Génère un document depuis une description en langage naturel.
    L'IA crée la structure, puis génère le fichier.
    Exemple : "Génère un rapport de sinistralité auto pour le T1 2025"
    """
    _verifier_rate_limit_documents(current_user.user_id)
    doc = await document_generateur.generer_depuis_prompt_ia(
        demande=req.demande,
        document_type=req.document_type,
        contexte=req.contexte,
        theme=req.theme,
    )
    if not doc:
        raise HTTPException(500, "Échec de la génération IA du document")
    return doc


@router.post("/rapport-sinistre")
async def rapport_sinistre(req: RapportSinistreRequest):
    """Génère un rapport d'expertise sinistre professionnel (DOCX)"""
    doc = await document_generateur.rapport_sinistre(req.donnees_sinistre)
    if not doc:
        raise HTTPException(500, "Échec génération rapport sinistre")
    return doc


@router.post("/rapport-cima")
async def rapport_cima(req: RapportCIMARequest):
    """Génère le rapport annuel de conformité CIMA (PDF)"""
    doc = await document_generateur.rapport_cima_annuel(req.donnees, req.annee)
    if not doc:
        raise HTTPException(500, "Échec génération rapport CIMA")
    return doc


@router.post("/presentation-ca")
async def presentation_ca(req: PresentationCARequest):
    """Génère une présentation PowerPoint pour le Conseil d'Administration"""
    doc = await document_generateur.presentation_ca(req.donnees, req.titre)
    if not doc:
        raise HTTPException(500, "Échec génération présentation CA")
    return doc


@router.post("/tableau-de-bord-excel")
async def tableau_de_bord_excel(req: TableauBordRequest):
    """Génère un tableau de bord Excel avec indicateurs CIMA"""
    doc = await document_generateur.tableau_de_bord_excel(req.donnees)
    if not doc:
        raise HTTPException(500, "Échec génération tableau de bord Excel")
    return doc


@router.get("/telecharger/{filename}")
async def telecharger_document(
    filename: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Télécharge un document généré par son nom de fichier"""
    # Sécurité : empêcher path traversal (y compris encodages URL %2F, %252F, etc.)
    import urllib.parse as _up
    filename_decoded = _up.unquote(_up.unquote(filename))  # double décodage pour %252F
    if any(c in filename_decoded for c in ("..", "/", "\\", "%")):
        raise HTTPException(400, "Nom de fichier invalide")
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    filepath = os.path.abspath(os.path.join(output_dir, filename))
    # Vérifier que le fichier est bien dans le dossier autorisé
    if not filepath.startswith(os.path.abspath(output_dir)):
        raise HTTPException(400, "Chemin non autorisé")
    if not os.path.exists(filepath):
        raise HTTPException(404, f"Fichier '{filename}' introuvable")
    return FileResponse(filepath, filename=filename)


@router.get("/formats")
async def formats_disponibles():
    """Liste les formats de documents disponibles"""
    return {
        "formats": [
            {"code": "docx", "libelle": "Word (.docx)", "usage": "Rapports, courriers, PV, contrats"},
            {"code": "pdf", "libelle": "PDF (.pdf)", "usage": "États CIMA, documents officiels, rapports direction"},
            {"code": "pptx", "libelle": "PowerPoint (.pptx)", "usage": "Présentations CA, formations, revues"},
            {"code": "xlsx", "libelle": "Excel (.xlsx)", "usage": "Tableaux de bord, états financiers, analyses"},
        ],
        "themes": ["blue", "green", "purple", "orange", "dark", "light"],
        "specialises": [
            "rapport_sinistre — Rapport d'expertise sinistre",
            "rapport_cima — Conformité CIMA annuelle",
            "presentation_ca — Présentation Conseil d'Administration",
            "tableau_de_bord_excel — Dashboard Excel indicateurs CIMA",
            "analyser-excel — Analyse approfondie fichier Excel (SI ou upload)",
            "rapport-activite — Rapport activité hebdomadaire/mensuel PPT avec graphiques",
            "presentation-avancee — Présentation PPT haute qualité via IA",
        ],
    }


# ─────────────────────────────────────────────────────────────
# Analyse Excel approfondie
# ─────────────────────────────────────────────────────────────

@router.post("/analyser-excel")
async def analyser_excel_upload(
    fichier: UploadFile = File(..., description="Fichier Excel (.xlsx ou .xls)"),
    feuille: Optional[str] = Form(None, description="Nom de la feuille à analyser (optionnel)"),
    contexte: str = Form("", description="Contexte métier pour l'IA (secteur, objectif...)"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Analyse approfondie d'un fichier Excel uploadé.
    Retourne : statistiques, graphiques (base64), commentaire IA, alertes.
    """
    await _pre_check_credits_doc(current_user.user_id)
    from modules.documents.analyseur_excel import analyser_excel

    nom = fichier.filename or "fichier.xlsx"
    if not nom.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Seuls les formats .xlsx et .xls sont supportés")

    contenu = await fichier.read()
    if len(contenu) > settings.MAX_EXCEL_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"Fichier trop volumineux (max {settings.MAX_EXCEL_SIZE_MB} MB)")

    try:
        resultat = await analyser_excel(
            contenu=contenu,
            nom_fichier=nom,
            feuille=feuille,
            contexte_utilisateur=contexte,
            claude_api_key=settings.CLAUDE_API_KEY,
            openai_api_key=settings.OPENAI_API_KEY,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))

    # Débit IA (commentaire Claude) + forfait non-LLM (pandas + matplotlib)
    nb_graphs = len(resultat.graphiques) if getattr(resultat, "graphiques", None) else 0
    nb_lignes = int(getattr(resultat, "nb_lignes", 0) or 0)
    await _debiter_llm_doc(
        user_id=current_user.user_id, module="analyse_excel",
        tokens_input=max(2000, nb_lignes // 10),
        tokens_output=3000, modele="claude-sonnet-4-6",
    )
    # Forfait : complexité ∝ (nb graphiques × 1 FCFA) + (lignes / 1000 FCFA)
    cout = nb_graphs * 1.0 + max(0.5, nb_lignes / 1000.0)
    await _debiter_forfait_doc(current_user.user_id, cout, "analyse_excel_stats")

    return {
        "nom_fichier": resultat.nom_fichier,
        "feuilles": resultat.feuilles,
        "feuille_active": resultat.feuille_active,
        "nb_lignes": resultat.nb_lignes,
        "nb_colonnes": resultat.nb_colonnes,
        "resume_ia": resultat.resume_ia,
        "points_cles": resultat.points_cles,
        "alertes": resultat.alertes,
        "tableau_resume": resultat.tableau_resume,
        "correlations": resultat.correlations,
        "graphiques": [
            {
                "titre": g.titre,
                "type": g.type_graphique,
                "image_base64": g.image_base64,
                "description": g.description,
            }
            for g in resultat.graphiques
        ],
    }


@router.post("/analyser-excel-si")
async def analyser_excel_depuis_si(
    chemin_si: str = Form(..., description="Chemin absolu du fichier dans le SI"),
    contexte: str = Form("", description="Contexte métier pour l'IA"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Analyse un fichier Excel/CSV depuis le système de fichiers du SI.
    Le chemin doit être accessible depuis le serveur applicatif.
    """
    await _pre_check_credits_doc(current_user.user_id)
    from modules.documents.analyseur_excel import analyser_excel_depuis_si as _analyser_si

    try:
        resultat = await _analyser_si(
            chemin=chemin_si,
            contexte_utilisateur=contexte,
            claude_api_key=settings.CLAUDE_API_KEY,
            openai_api_key=settings.OPENAI_API_KEY,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))

    nb_graphs = len(resultat.graphiques) if getattr(resultat, "graphiques", None) else 0
    nb_lignes = int(getattr(resultat, "nb_lignes", 0) or 0)
    await _debiter_llm_doc(
        user_id=current_user.user_id, module="analyse_excel_si",
        tokens_input=max(2000, nb_lignes // 10),
        tokens_output=3000, modele="claude-sonnet-4-6",
    )
    cout = nb_graphs * 1.0 + max(0.5, nb_lignes / 1000.0)
    await _debiter_forfait_doc(current_user.user_id, cout, "analyse_excel_si_stats")

    return {
        "nom_fichier": resultat.nom_fichier,
        "feuilles": resultat.feuilles,
        "feuille_active": resultat.feuille_active,
        "nb_lignes": resultat.nb_lignes,
        "nb_colonnes": resultat.nb_colonnes,
        "resume_ia": resultat.resume_ia,
        "points_cles": resultat.points_cles,
        "alertes": resultat.alertes,
        "tableau_resume": resultat.tableau_resume,
        "correlations": resultat.correlations,
        "graphiques": [
            {"titre": g.titre, "type": g.type_graphique,
             "image_base64": g.image_base64, "description": g.description}
            for g in resultat.graphiques
        ],
    }


# ─────────────────────────────────────────────────────────────
# Rapport d'activité (hebdomadaire / mensuel)
# ─────────────────────────────────────────────────────────────

class RapportActiviteRequest(BaseModel):
    periode: str                     # ex: "Semaine 15 — 7 au 13 avril 2025"
    type_rapport: str = "mensuel"    # "hebdomadaire" | "mensuel"
    donnees: Dict[str, Any]          # Voir doc generateur_rapports.py
    auteur: str = ""
    compagnie_nom: str = "YukpoAssurance"
    theme: str = "corporate_blue"    # "corporate_blue" | "dark_pro" | "green_finance"


@router.post("/rapport-activite")
async def generer_rapport_activite(
    req: RapportActiviteRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Génère un rapport d'activité PPT haute qualité avec graphiques Python.
    Retourne le fichier PPTX encodé en base64 + URL de téléchargement.
    """
    await _pre_check_credits_doc(current_user.user_id)
    from modules.documents.generateur_rapports import generer_rapport_activite as _gen

    try:
        pptx_bytes = _gen(
            periode=req.periode,
            type_rapport=req.type_rapport,
            donnees=req.donnees,
            auteur=req.auteur or current_user.username,
            compagnie_nom=req.compagnie_nom,
            theme=req.theme,
        )
    except Exception as e:
        raise HTTPException(500, f"Erreur génération rapport : {e}")

    # Forfait PPTX avec graphiques matplotlib — coût proportionnel à la taille
    taille_mo = max(1, len(pptx_bytes) // (1024 * 1024))
    await _debiter_forfait_doc(
        current_user.user_id,
        cout_fcfa=2.0 * taille_mo,   # ~2 FCFA/Mo × 20× marge
        module=f"rapport_activite_{req.type_rapport}",
    )

    # Sauvegarder et retourner
    safe_nom = req.periode.replace(" ", "_").replace("—", "-")[:40]
    nom_fichier = f"rapport_{req.type_rapport}_{safe_nom}.pptx"
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    os.makedirs(output_dir, exist_ok=True)
    chemin = os.path.join(output_dir, nom_fichier)
    with open(chemin, "wb") as f:
        f.write(pptx_bytes)

    return {
        "nom_fichier": nom_fichier,
        "taille_bytes": len(pptx_bytes),
        "telecharger_url": f"/api/v1/documents/telecharger/{nom_fichier}",
        "base64": base64.b64encode(pptx_bytes).decode(),
    }


# ─────────────────────────────────────────────────────────────
# Présentation avancée (IA + graphiques Python)

# ─────────────────────────────────────────────────────────────

class PresentationAvanceeRequest(BaseModel):
    demande: str                      # ex: "Présentation bilan sinistres T1 2025"
    contexte: Dict[str, Any] = {}    # données contextuelles
    auteur: str = ""
    compagnie_nom: str = "YukpoAssurance"
    theme: str = "corporate_blue"
    mode: str = "ia"                  # "ia" = génération IA | "config" = slides_config direct
    slides_config: Optional[List[Dict[str, Any]]] = None  # si mode="config"


@router.post("/presentation-avancee")
async def generer_presentation_avancee(
    req: PresentationAvanceeRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Génère une présentation PowerPoint haute qualité.
    - mode "ia"     : l'IA structure la présentation depuis la demande en langage naturel
    - mode "config" : structure fournie directement via slides_config
    Chaque slide peut contenir des graphiques matplotlib générés côté serveur.
    """
    await _pre_check_credits_doc(current_user.user_id)
    from modules.documents.generateur_rapports import (
        generer_presentation_depuis_ia,
        generer_presentation_personnalisee,
    )

    try:
        if req.mode == "config" and req.slides_config:
            pptx_bytes = generer_presentation_personnalisee(
                titre=req.demande,
                slides_config=req.slides_config,
                auteur=req.auteur or current_user.username,
                compagnie_nom=req.compagnie_nom,
                theme=req.theme,
            )
        else:
            pptx_bytes = await generer_presentation_depuis_ia(
                demande=req.demande,
                contexte=req.contexte,
                auteur=req.auteur or current_user.username,
                compagnie_nom=req.compagnie_nom,
                theme=req.theme,
                claude_api_key=settings.CLAUDE_API_KEY,
                openai_api_key=settings.OPENAI_API_KEY,
            )
    except Exception as e:
        raise HTTPException(500, f"Erreur génération présentation : {e}")

    # Débit : mode "ia" = IA + PPTX ; mode "config" = forfait seul
    nb_slides = len(req.slides_config or []) or 10
    if req.mode == "ia":
        await _debiter_llm_doc(
            user_id=current_user.user_id, module="presentation_avancee_ia",
            tokens_input=2500, tokens_output=max(2000, nb_slides * 300),
            modele="claude-sonnet-4-6",
        )
    taille_mo = max(1, len(pptx_bytes) // (1024 * 1024))
    await _debiter_forfait_doc(
        current_user.user_id,
        cout_fcfa=2.0 * taille_mo + 0.5 * nb_slides,
        module="presentation_avancee_render",
    )

    nom_safe = req.demande.replace(" ", "_")[:50]
    nom_fichier = f"presentation_{nom_safe}.pptx"
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, nom_fichier), "wb") as f:
        f.write(pptx_bytes)

    return {
        "nom_fichier": nom_fichier,
        "taille_bytes": len(pptx_bytes),
        "telecharger_url": f"/api/v1/documents/telecharger/{nom_fichier}",
        "base64": base64.b64encode(pptx_bytes).decode(),
    }


# ─── Routes OCR ────────────────────────────────────────────────────────────────

from core.ocr_processor import ocr_processor  # noqa: E402


@router.post("/ocr/image")
async def ocr_image_upload(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
):
    """
    OCR sur image uploadée (PNG, JPEG, TIFF, BMP).
    Extrait et structure les données pour le SI assurance.
    """
    from core.security import security_service
    content = await file.read()
    valide, safe_filename, raison = security_service.valider_fichier_upload(
        filename=file.filename or "upload",
        content=content,
        max_size_mb=10.0,
        types_autorises=["png", "jpg", "jpeg", "tiff", "bmp", "gif"],
    )
    if not valide:
        raise HTTPException(status_code=400, detail=raison)

    await _pre_check_credits_doc(current_user.user_id)
    resultat = await ocr_processor.traiter_image(
        image_bytes=content,
        nom_fichier=file.filename or "image",
        contexte={"compagnie_id": current_user.compagnie_id, "user_id": current_user.user_id},
    )
    # OCR image unique = 1 appel Claude Vision ≈ 1500 tokens in / 800 out
    await _debiter_llm_doc(
        user_id=current_user.user_id, module="ocr_image_documents",
        tokens_input=1500, tokens_output=800, modele="claude-sonnet-4-6",
    )
    return {
        "type_document": resultat.type_document.value,
        "confiance": round(resultat.confiance, 3),
        "langue": resultat.langue_detectee,
        "donnees_structurees": resultat.donnees_structurees,
        "champs_manquants": resultat.champs_manquants,
        "avertissements": resultat.avertissements,
        "texte_brut_extrait": resultat.texte_brut[:500] + "..." if len(resultat.texte_brut) > 500 else resultat.texte_brut,
    }


@router.post("/ocr/pdf")
async def ocr_pdf_upload(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
):
    """
    OCR sur PDF multi-pages. Traite jusqu'à 20 pages.
    """
    from core.security import security_service
    content = await file.read()
    valide, safe_filename, raison = security_service.valider_fichier_upload(
        filename=file.filename or "upload.pdf",
        content=content,
        max_size_mb=20.0,
        types_autorises=["pdf"],
    )
    if not valide:
        raise HTTPException(status_code=400, detail=raison)

    await _pre_check_credits_doc(current_user.user_id)
    resultat = await ocr_processor.traiter_pdf(
        pdf_bytes=content,
        nom_fichier=file.filename or "document.pdf",
        contexte={"compagnie_id": current_user.compagnie_id},
    )
    # OCR PDF — débit par page traitée
    nb_pages = int(getattr(resultat, "pages_traitees", 0) or 1)
    await _debiter_llm_doc(
        user_id=current_user.user_id, module="ocr_pdf_documents",
        tokens_input=1500 * nb_pages, tokens_output=800 * nb_pages,
        modele="claude-sonnet-4-6",
    )
    return {
        "type_document": resultat.type_document.value,
        "confiance": round(resultat.confiance, 3),
        "langue": resultat.langue_detectee,
        "pages_traitees": resultat.pages_traitees,
        "donnees_structurees": resultat.donnees_structurees,
        "champs_manquants": resultat.champs_manquants,
        "avertissements": resultat.avertissements,
    }


@router.post("/ocr/base64")
async def ocr_base64(
    request: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """
    OCR sur fichier encodé en base64 (pour apps mobiles).
    Body: {"data_b64": "...", "nom_fichier": "document.pdf", "contexte": {}}
    """
    data_b64 = request.get("data_b64", "")
    nom_fichier = request.get("nom_fichier", "document")
    contexte = request.get("contexte", {})

    if not data_b64:
        raise HTTPException(status_code=400, detail="Champ 'data_b64' requis")

    await _pre_check_credits_doc(current_user.user_id)
    resultat = await ocr_processor.traiter_fichier_base64(
        data_b64=data_b64,
        nom_fichier=nom_fichier,
        contexte={**contexte, "compagnie_id": current_user.compagnie_id},
    )
    nb_pages = int(getattr(resultat, "pages_traitees", 0) or 1)
    await _debiter_llm_doc(
        user_id=current_user.user_id, module="ocr_base64",
        tokens_input=1500 * nb_pages, tokens_output=800 * nb_pages,
        modele="claude-sonnet-4-6",
    )
    return {
        "type_document": resultat.type_document.value,
        "confiance": round(resultat.confiance, 3),
        "donnees_structurees": resultat.donnees_structurees,
        "champs_manquants": resultat.champs_manquants,
        "avertissements": resultat.avertissements,
    }


# ─────────────────────────────────────────────────────────────
# Signature Électronique
# ─────────────────────────────────────────────────────────────

class SignerDocumentRequest(BaseModel):
    pdf_base64: str                        # PDF encodé en base64
    type_document: str = "document"        # contrat_assurance | etat_reglementaire | autre
    numero_reference: Optional[str] = None # Numéro police, sinistre, état CIMA...
    compagnie_nom: str = "YukpoAssurance"


class VerifierSignatureRequest(BaseModel):
    pdf_original_base64: str   # PDF ORIGINAL (avant tampon) encodé en base64
    manifest_json: str         # Manifest retourné lors de la signature


@router.post("/signature/signer")
async def signer_document(
    req: SignerDocumentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Signe électroniquement un document PDF.
    Retourne : PDF signé (avec tampon visible), manifest HMAC-SHA256, ID de signature.
    La signature est enregistrée en base de données pour l'audit trail.
    """
    from modules.documents.signature_electronique import signature_service, InfoSignataire

    try:
        pdf_bytes = base64.b64decode(req.pdf_base64)
    except Exception:
        raise HTTPException(400, "pdf_base64 invalide — encodage base64 attendu")

    signataire = InfoSignataire(
        user_id=current_user.user_id,
        nom_complet=current_user.username,
        role=current_user.role,
        compagnie_id=current_user.compagnie_id or 0,
        compagnie_nom=req.compagnie_nom,
        email=getattr(current_user, "email", None),
    )

    try:
        resultat = await signature_service.signer_pdf(
            pdf_bytes=pdf_bytes,
            signataire=signataire,
            type_document=req.type_document,
            numero_reference=req.numero_reference,
        )
    except Exception as e:
        raise HTTPException(500, f"Erreur signature : {e}")

    return {
        "signature_id": resultat.signature_id,
        "hash_sha256": resultat.hash_sha256,
        "timestamp_utc": resultat.timestamp_utc,
        "pdf_signe_base64": resultat.pdf_signe_b64,
        "manifest_json": resultat.manifest_json,
        "signataire": {
            "nom": signataire.nom_complet,
            "role": signataire.role,
            "compagnie": req.compagnie_nom,
        },
        "valide": resultat.valide,
    }


@router.post("/signature/verifier")
async def verifier_signature(
    req: VerifierSignatureRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Vérifie l'intégrité d'un document signé via YukpoAssurance.
    Compare le hash SHA-256 du PDF original avec celui enregistré dans le manifest.
    Vérifie également la signature HMAC du manifest (anti-falsification).
    """
    from modules.documents.signature_electronique import signature_service

    try:
        pdf_bytes = base64.b64decode(req.pdf_original_base64)
    except Exception:
        raise HTTPException(400, "pdf_original_base64 invalide")

    resultat = signature_service.verifier(pdf_bytes, req.manifest_json)

    return {
        "valide": resultat.valide,
        "signature_id": resultat.signature_id,
        "timestamp_utc": resultat.timestamp_utc,
        "signataire": resultat.signataire_nom,
        "hash_attendu": resultat.hash_attendu,
        "hash_calcule": resultat.hash_calcule,
        "detail": resultat.detail,
    }


@router.get("/signature/{signature_id}")
async def consulter_signature(
    signature_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Consulte les métadonnées d'une signature depuis l'audit trail DB."""
    from core.database import async_session_maker, SignatureDB
    from sqlalchemy import select

    async with async_session_maker() as db:
        result = await db.execute(
            select(SignatureDB).where(SignatureDB.signature_id == signature_id)
        )
        sig = result.scalar_one_or_none()

    if not sig:
        raise HTTPException(404, f"Signature '{signature_id}' introuvable")

    return {
        "signature_id": sig.signature_id,
        "hash_sha256": sig.hash_sha256,
        "timestamp_utc": sig.timestamp_utc,
        "signataire_nom": sig.signataire_nom,
        "signataire_role": sig.signataire_role,
        "compagnie_id": sig.compagnie_id,
        "cree_le": sig.cree_le.isoformat() if sig.cree_le else None,
    }


# ─────────────────────────────────────────────────────────────
# Historique documents générés (persisté en base)
# ─────────────────────────────────────────────────────────────

def _doc_to_dict(doc) -> dict:
    return {
        "id": doc.id,
        "titre": doc.titre,
        "type_doc": doc.type_doc,
        "fichier": doc.fichier,
        "contenu_source": doc.contenu_source,
        "contenu_genere": doc.contenu_genere,
        "session_id": doc.session_id,
        "meta": doc.meta or {},
        "cree_le": doc.cree_le.isoformat() if doc.cree_le else None,
        "modifie_le": doc.modifie_le.isoformat() if doc.modifie_le else None,
    }


@router.get("/historique")
async def historique_documents(
    type_doc: Optional[str] = Query(None, description="Filtrer par type : rapport | slides | traduction | autre"),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user),
):
    """Liste les documents générés par l'utilisateur courant (ou toute la compagnie pour admin)."""
    from core.database import async_session_maker, DocumentGenereDB
    from sqlalchemy import select, desc

    async with async_session_maker() as db:
        q = select(DocumentGenereDB).where(
            DocumentGenereDB.compagnie_id == current_user.compagnie_id
        )
        if type_doc:
            q = q.where(DocumentGenereDB.type_doc == type_doc)
        q = q.order_by(desc(DocumentGenereDB.cree_le)).limit(limit)
        result = await db.execute(q)
        docs = result.scalars().all()

    return {"documents": [_doc_to_dict(d) for d in docs], "total": len(docs)}


class SauvegarderDocumentRequest(BaseModel):
    titre: str
    type_doc: str = "autre"      # rapport | slides | traduction | autre
    fichier: Optional[str] = None
    contenu_source: Optional[str] = None
    contenu_genere: Optional[str] = None
    session_id: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


@router.post("/historique")
async def sauvegarder_document(
    payload: SauvegarderDocumentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Enregistre un document généré dans l'historique persistant."""
    from core.database import async_session_maker, DocumentGenereDB

    async with async_session_maker() as db:
        doc = DocumentGenereDB(
            user_id=current_user.user_id,
            compagnie_id=current_user.compagnie_id,
            titre=payload.titre,
            type_doc=payload.type_doc,
            fichier=payload.fichier,
            contenu_source=payload.contenu_source,
            contenu_genere=payload.contenu_genere,
            session_id=payload.session_id,
            meta=payload.meta or {},
            cree_le=datetime.utcnow(),
            modifie_le=datetime.utcnow(),
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

    return _doc_to_dict(doc)


@router.delete("/historique/{doc_id}")
async def supprimer_document(
    doc_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    """Supprime un document de l'historique (doit appartenir à la même compagnie)."""
    from core.database import async_session_maker, DocumentGenereDB
    from sqlalchemy import select

    async with async_session_maker() as db:
        result = await db.execute(
            select(DocumentGenereDB).where(
                DocumentGenereDB.id == doc_id,
                DocumentGenereDB.compagnie_id == current_user.compagnie_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(404, "Document introuvable")
        await db.delete(doc)
        await db.commit()

    return {"ok": True, "id": doc_id}


# ─────────────────────────────────────────────────────────────
# Traduction de fichier (PDF, DOCX, TXT, images via OCR)
# ─────────────────────────────────────────────────────────────

async def _extraire_texte_fichier(nom: str, contenu: bytes, user_id: Optional[int] = None) -> str:
    """Extrait le texte d'un fichier selon son extension.
    Si user_id fourni et PDF scanné, débite les crédits OCR par page."""
    ext = (nom.rsplit(".", 1)[-1] if "." in nom else "").lower()

    if ext == "txt" or ext == "md":
        return contenu.decode("utf-8", errors="replace")

    if ext == "pdf":
        # Extraction native si texte exploitable, sinon OCR Claude Vision par lots
        try:
            from core.pdf_ocr_batch import extraire_texte_pdf
            return await extraire_texte_pdf(contenu, user_id=user_id, module="pdf_ocr_upload_doc")
        except Exception as e:
            logger.warning(f"[Documents] extraire_texte_pdf échoué ({e}) → fallback OCR page unique")
            return await _ocr_via_claude(contenu, nom)

    if ext in ("doc", "docx"):
        try:
            import io
            from docx import Document as DocxDocument
            doc = DocxDocument(io.BytesIO(contenu))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            return await _ocr_via_claude(contenu, nom)

    if ext in ("xls", "xlsx", "csv"):
        try:
            import io
            import pandas as pd
            if ext == "csv":
                df = pd.read_csv(io.BytesIO(contenu), nrows=500)
            else:
                df = pd.read_excel(io.BytesIO(contenu), nrows=500)
            return df.to_string(index=False)
        except Exception as e:
            return f"[Erreur lecture tableur : {e}]"

    if ext in ("pptx", "ppt"):
        try:
            import io
            from pptx import Presentation
            prs = Presentation(io.BytesIO(contenu))
            lignes = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        lignes.append(shape.text)
            return "\n".join(lignes)
        except Exception as e:
            return f"[Erreur lecture présentation : {e}]"

    if ext in ("png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"):
        return await _ocr_via_claude(contenu, nom)

    # Tentative texte brut
    try:
        return contenu.decode("utf-8", errors="replace")
    except Exception:
        return "[Format non supporté pour l'extraction de texte]"


async def _ocr_via_claude(contenu: bytes, nom_fichier: str) -> str:
    """OCR d'une image ou PDF via Claude Vision."""
    import anthropic
    ext = (nom_fichier.rsplit(".", 1)[-1] if "." in nom_fichier else "jpeg").lower()
    media_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "bmp": "image/png", "webp": "image/webp",
        "pdf": "application/pdf",
    }
    media_type = media_map.get(ext, "image/jpeg")
    data_b64 = base64.standard_b64encode(contenu).decode("utf-8")

    client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data_b64},
                },
                {
                    "type": "text",
                    "text": "Extrais tout le texte visible dans ce document. Retourne uniquement le texte brut, sans commentaires.",
                },
            ],
        }],
    )
    return msg.content[0].text if msg.content else ""


@router.post("/traduire-fichier")
async def traduire_fichier(
    fichier: UploadFile = File(..., description="Fichier à traduire (PDF, DOCX, TXT, image…)"),
    langue_source: str = Form("fr", description="Code langue source (fr, en, es…)"),
    langue_cible: str = Form("en", description="Code langue cible"),
    contexte_metier: str = Form("", description="Contexte métier pour la traduction"),
    format_sortie: str = Form("texte", description="texte | docx"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Traduit un fichier uploadé (PDF, DOCX, TXT, images…).
    Extrait le texte, traduit via Claude, et retourne le résultat en texte ou DOCX.
    """
    await _pre_check_credits_doc(current_user.user_id)
    nom = fichier.filename or "fichier"
    contenu = await fichier.read()

    _limite_mo = getattr(settings, "MAX_DOC_SIZE_MB", 50)
    if len(contenu) > _limite_mo * 1024 * 1024:
        raise HTTPException(413, f"Fichier trop volumineux (max {_limite_mo} Mo)")

    # 1. Extraction texte (OCR par page débité si PDF scanné)
    texte_source = await _extraire_texte_fichier(nom, contenu, user_id=current_user.user_id)
    if not texte_source.strip():
        raise HTTPException(422, "Impossible d'extraire le texte du fichier")

    # 2. Traduction via chunking (taille illimitée — lots parallèles Claude Sonnet)
    from api.routes_pro_generateurs import _traduire_texte_en_chunks
    texte_traduit = await _traduire_texte_en_chunks(
        texte=texte_source,
        src=langue_source,
        dst=langue_cible,
        metier=contexte_metier or "assurance et documents d'entreprise",
    )

    # 3. Débit LLM (Claude Sonnet) proportionnel aux mots source+cible
    nb_mots_src = len(texte_source.split())
    nb_mots_dst = len(texte_traduit.split())
    await _debiter_llm_doc(
        user_id=current_user.user_id,
        module="traduire_fichier_documents",
        tokens_input=max(500, int(nb_mots_src * 1.3)),
        tokens_output=max(400, int(nb_mots_dst * 1.3)),
        modele="claude-sonnet-4-6",
    )

    # 3. Format sortie
    if format_sortie == "docx":
        try:
            from docx import Document as DocxDocument
            import io
            doc = DocxDocument()
            doc.add_heading(f"Traduction — {nom}", 0)
            for ligne in texte_traduit.split("\n"):
                if ligne.strip().startswith("# "):
                    doc.add_heading(ligne.strip()[2:], 1)
                elif ligne.strip().startswith("## "):
                    doc.add_heading(ligne.strip()[3:], 2)
                else:
                    doc.add_paragraph(ligne)
            buf = io.BytesIO()
            doc.save(buf)
            buf.seek(0)
            docx_bytes = buf.getvalue()
            # Sauvegarder
            nom_sortie = f"traduction_{nom.rsplit('.', 1)[0]}.docx"
            output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, nom_sortie), "wb") as f:
                f.write(docx_bytes)
            return {
                "langue_source": langue_source,
                "langue_cible": langue_cible,
                "nb_mots_source": len(texte_source.split()),
                "nb_mots_cible": len(texte_traduit.split()),
                "texte_traduit": texte_traduit,
                "chemin_docx": nom_sortie,
                "telecharger_url": f"/api/v1/documents/telecharger/{nom_sortie}",
            }
        except Exception as e:
            # Si docx échoue, retour texte
            pass

    return {
        "langue_source": langue_source,
        "langue_cible": langue_cible,
        "nb_mots_source": len(texte_source.split()),
        "nb_mots_cible": len(texte_traduit.split()),
        "texte_traduit": texte_traduit,
        "chemin_docx": None,
        "telecharger_url": None,
    }
