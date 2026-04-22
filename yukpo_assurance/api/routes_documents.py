"""Routes Documents — génération Word, PDF, PPT, Excel, Analyse Excel, Rapports + Historique"""
import os
import time
import json
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

router = APIRouter(dependencies=[Depends(require_permission("documents"))])

# ─── Rate limiter simple en mémoire pour les endpoints documents ──────────────
# (Redis-backed rate limiting est dans core/security.py pour les autres endpoints)
_DOC_IA_RATE: dict[str, list[float]] = defaultdict(list)
_DOC_IA_MAX_PAR_MINUTE = 6   # 6 générations IA par minute max par utilisateur


def _verifier_rate_limit_documents(request: Request) -> None:
    """Rate limit : max 6 générations documents IA par minute par IP."""
    ip = request.client.host if request.client else "unknown"
    maintenant = time.time()
    historique = _DOC_IA_RATE[ip]
    # Nettoyer les entrées > 60 secondes
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
async def generer_depuis_prompt(req: GenerationIARequest, request: Request):
    """
    Génère un document depuis une description en langage naturel.
    L'IA crée la structure, puis génère le fichier.
    Exemple : "Génère un rapport de sinistralité auto pour le T1 2025"
    """
    _verifier_rate_limit_documents(request)
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
    valide, raison = security_service.valider_fichier_upload(
        filename=file.filename or "upload",
        content=content,
        max_size_mb=10.0,
        types_autorises=["png", "jpg", "jpeg", "tiff", "bmp", "gif"],
    )
    if not valide:
        raise HTTPException(status_code=400, detail=raison)

    resultat = await ocr_processor.traiter_image(
        image_bytes=content,
        nom_fichier=file.filename or "image",
        contexte={"compagnie_id": current_user.compagnie_id, "user_id": current_user.user_id},
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
    valide, raison = security_service.valider_fichier_upload(
        filename=file.filename or "upload.pdf",
        content=content,
        max_size_mb=20.0,
        types_autorises=["pdf"],
    )
    if not valide:
        raise HTTPException(status_code=400, detail=raison)

    resultat = await ocr_processor.traiter_pdf(
        pdf_bytes=content,
        nom_fichier=file.filename or "document.pdf",
        contexte={"compagnie_id": current_user.compagnie_id},
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

    resultat = await ocr_processor.traiter_fichier_base64(
        data_b64=data_b64,
        nom_fichier=nom_fichier,
        contexte={**contexte, "compagnie_id": current_user.compagnie_id},
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

async def _extraire_texte_fichier(nom: str, contenu: bytes) -> str:
    """Extrait le texte d'un fichier selon son extension."""
    ext = (nom.rsplit(".", 1)[-1] if "." in nom else "").lower()

    if ext == "txt" or ext == "md":
        return contenu.decode("utf-8", errors="replace")

    if ext == "pdf":
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(contenu))
            texte = "\n".join(p.extract_text() or "" for p in reader.pages)
            if texte.strip():
                return texte
        except Exception:
            pass
        # Fallback OCR Claude
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
    import anthropic

    nom = fichier.filename or "fichier"
    contenu = await fichier.read()

    if len(contenu) > 20 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (max 20 Mo)")

    # 1. Extraction texte
    texte_source = await _extraire_texte_fichier(nom, contenu)
    if not texte_source.strip():
        raise HTTPException(422, "Impossible d'extraire le texte du fichier")

    # Tronquer si trop long
    if len(texte_source) > 30000:
        texte_source = texte_source[:30000] + "\n\n[… document tronqué à 30 000 caractères …]"

    # 2. Traduction via Claude
    prompt_system = (
        f"Tu es un traducteur professionnel spécialisé en assurance et documents d'entreprise. "
        f"Traduis le texte suivant du {langue_source} vers le {langue_cible}. "
        f"Conserve la mise en forme (titres, listes, tableaux en Markdown). "
        f"Retourne uniquement la traduction, sans introduction ni commentaire."
    )
    if contexte_metier:
        prompt_system += f"\nContexte : {contexte_metier}"

    client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=prompt_system,
        messages=[{"role": "user", "content": texte_source}],
    )
    texte_traduit = resp.content[0].text if resp.content else ""

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
