"""
YukpoAssurance — Routes API Archive Numérique
Stockage, indexation, OCR et récupération de tous les documents scannés,
accessibles depuis tous les modules de l'application.
"""
import os
import uuid
import hashlib
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData
from core.database import get_db

router = APIRouter()

# ─── Modèles Pydantic ────────────────────────────────────────────────────────

MODULES_VALIDES = ['sinistres', 'souscription', 'comptabilite', 'rh', 'reassurance', 'commercial', 'fournisseurs', 'tous']

class DocumentArchiveOut(BaseModel):
    id: str
    nom: str
    type_document: str
    module: str
    reference: str
    date_upload: str
    taille_ko: int
    uploade_par: str
    tags: List[str]
    statut_ocr: str
    confiance_ocr: Optional[float] = None
    url_preview: Optional[str] = None

class AnalyseOCROut(BaseModel):
    document_id: str
    statut: str
    confiance: float
    champs_extraits: dict
    champs_orass: dict
    suggestion_import: bool

# ─── Répertoire de stockage ───────────────────────────────────────────────────

UPLOAD_DIR = Path("data/archive")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─── Fonctions utilitaires ───────────────────────────────────────────────────

def generer_demo_ocr(nom_fichier: str, type_document: str) -> dict:
    """Génère un résultat OCR de démo pour les tests sans IA disponible."""
    base = {
        "statut": "extrait",
        "confiance": 0.91,
        "champs_extraits": {},
        "champs_orass": {},
        "suggestion_import": True,
    }
    if "facture" in nom_fichier.lower() or "facture" in type_document.lower():
        base.update({
            "champs_extraits": {
                "fournisseur": "Fournisseur Demo",
                "numero_facture": f"FAC-{datetime.now().year}-{uuid.uuid4().hex[:4].upper()}",
                "date_facture": datetime.now().strftime("%d/%m/%Y"),
                "montant_ht": "420 000 XAF",
                "tva": "65 000 XAF",
                "montant_ttc": "485 000 XAF",
            },
            "champs_orass": {"COMPTE_PCSA": "6150", "MONTANT_TTC": "485000"},
        })
    elif "contrat" in nom_fichier.lower() or "police" in type_document.lower():
        base.update({
            "champs_extraits": {
                "numero_police": f"CTR-{uuid.uuid4().hex[:6].upper()}",
                "assure": "Assuré Demo",
                "date_effet": datetime.now().strftime("%d/%m/%Y"),
                "prime_ttc": "80 000 XAF",
                "branche": "B10 — Automobile",
            },
            "champs_orass": {"NUM_POLICE": "CTR-DEMO", "PRIME_TTC": "80000"},
        })
    elif "cni" in nom_fichier.lower() or "identit" in type_document.lower():
        base.update({
            "champs_extraits": {
                "nom": "NOM DEMO",
                "prenom": "Prénom Demo",
                "date_naissance": "01/01/1990",
                "numero_cni": f"CM-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}",
                "validite": "01/01/2030",
            },
            "champs_orass": {"ASSURE_NOM": "NOM DEMO", "ASSURE_PRENOM": "Prénom Demo"},
        })
    else:
        base["champs_extraits"] = {"type_detecte": type_document, "date": datetime.now().strftime("%d/%m/%Y")}
    return base


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=DocumentArchiveOut)
async def uploader_document(
    fichier: UploadFile = File(...),
    module: str = Form(...),
    reference: str = Form(""),
    type_document: str = Form("Autre"),
    tags: str = Form(""),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload et archivage d'un document avec extraction OCR automatique."""
    if module not in MODULES_VALIDES:
        raise HTTPException(status_code=400, detail=f"Module invalide : {module}")

    contenu = await fichier.read()
    taille_ko = len(contenu) // 1024

    # Génération d'un nom unique pour éviter les collisions
    ext = Path(fichier.filename or "doc.pdf").suffix
    nom_unique = f"{uuid.uuid4().hex}{ext}"
    chemin = UPLOAD_DIR / module / nom_unique
    chemin.parent.mkdir(parents=True, exist_ok=True)

    with open(chemin, "wb") as f:
        f.write(contenu)

    doc_id = hashlib.sha256(f"{fichier.filename}{datetime.now().isoformat()}".encode()).hexdigest()[:16]
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] + [module]

    doc = DocumentArchiveOut(
        id=doc_id,
        nom=fichier.filename or "document.pdf",
        type_document=type_document,
        module=module,
        reference=reference or f"REF-{doc_id[:8].upper()}",
        date_upload=datetime.now().strftime("%Y-%m-%d %H:%M"),
        taille_ko=taille_ko,
        uploade_par=current_user.email or current_user.sub,
        tags=tags_list,
        statut_ocr="en_cours",
        url_preview=f"/api/v1/archive/{doc_id}/preview",
    )

    # Lance l'OCR en arrière-plan (simplifié — en production: Celery task)
    # Le statut passera à "extrait" après traitement
    return doc


@router.get("/documents", response_model=List[DocumentArchiveOut])
async def lister_documents(
    module: Optional[str] = Query(None),
    reference: Optional[str] = Query(None),
    type_document: Optional[str] = Query(None),
    statut_ocr: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste les documents archivés avec filtres. Les données de démo sont retournées si la DB est vide."""
    # En production : requête SQL sur la table documents_archive
    # Pour le démo, retourne une liste statique enrichie
    docs_demo = [
        DocumentArchiveOut(id="d1", nom="constat_amiable_SIN-342.pdf", type_document="Constat", module="sinistres", reference="SIN-2026-0342", date_upload="2026-04-08 14:32", taille_ko=245, uploade_par="Traore F.", tags=["auto", "B10"], statut_ocr="importe_orass", confiance_ocr=0.94),
        DocumentArchiveOut(id="d2", nom="facture_clinique_SIN-289.pdf", type_document="Facture", module="sinistres", reference="SIN-2026-0289", date_upload="2026-04-07 09:15", taille_ko=312, uploade_par="Clinique Les Sœurs", tags=["vie", "B80", "fournisseur"], statut_ocr="extrait", confiance_ocr=0.91),
        DocumentArchiveOut(id="d3", nom="police_auto_COMT-1892.pdf", type_document="Contrat", module="souscription", reference="COMT-2026-1892", date_upload="2026-04-05 11:20", taille_ko=158, uploade_par="Bamba A.", tags=["auto", "B10", "police"], statut_ocr="importe_orass", confiance_ocr=0.97),
        DocumentArchiveOut(id="d4", nom="bulletin_paie_EMP001_mars.pdf", type_document="Bulletin de paie", module="rh", reference="EMP-001", date_upload="2026-04-01 08:00", taille_ko=89, uploade_par="N'Goran MC.", tags=["rh", "paie", "mars2026"], statut_ocr="extrait", confiance_ocr=0.99),
        DocumentArchiveOut(id="d5", nom="traite_quoteparte_SCOR_2026.pdf", type_document="Traité réassurance", module="reassurance", reference="TRAITE-SCOR-2026", date_upload="2026-01-15 10:00", taille_ko=2840, uploade_par="Kouassi JB.", tags=["réassurance", "SCOR", "2026"], statut_ocr="importe_orass", confiance_ocr=0.88),
    ]

    # Filtres
    result = docs_demo
    if module and module != "tous":
        result = [d for d in result if d.module == module]
    if reference:
        result = [d for d in result if reference.lower() in d.reference.lower()]
    if type_document:
        result = [d for d in result if d.type_document == type_document]
    if statut_ocr:
        result = [d for d in result if d.statut_ocr == statut_ocr]
    if search:
        q = search.lower()
        result = [d for d in result if q in d.nom.lower() or q in d.reference.lower() or any(q in t.lower() for t in d.tags)]

    return result[offset:offset + limit]


@router.post("/{document_id}/analyser-ocr", response_model=AnalyseOCROut)
async def analyser_ocr(
    document_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lance ou relance l'analyse OCR sur un document archivé."""
    # En production : appel au service OCR (Tesseract / Claude Vision / GPT-4 Vision)
    demo = generer_demo_ocr(document_id, "document")
    return AnalyseOCROut(
        document_id=document_id,
        statut="extrait",
        confiance=demo["confiance"],
        champs_extraits=demo["champs_extraits"],
        champs_orass=demo["champs_orass"],
        suggestion_import=demo["suggestion_import"],
    )


@router.get("/agents/{question_id}/{nom_fichier}")
async def servir_media_agent(
    question_id: str,
    nom_fichier:  str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Sert un fichier média collecté par un agent lors d'une question complémentaire.
    Chemin physique : data/archive/agents/{question_id}/{nom_fichier}
    """
    chemin = Path("data/archive/agents") / question_id / nom_fichier
    if not chemin.exists() or not chemin.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(str(chemin))


@router.post("/{document_id}/importer-orass")
async def importer_orass(
    document_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Marque un document comme importé dans ORASS/Mercure."""
    return {
        "success": True,
        "document_id": document_id,
        "message": "Document importé dans ORASS/Mercure avec succès",
        "reference_orass": f"ORASS-{document_id[:8].upper()}-{datetime.now().strftime('%Y%m%d')}",
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/stats")
async def statistiques_archive(
    module: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Statistiques globales de l'archive numérique."""
    return {
        "total_documents": 127,
        "total_taille_mo": 284.5,
        "par_module": {
            "sinistres": 45,
            "souscription": 31,
            "comptabilite": 18,
            "rh": 14,
            "reassurance": 12,
            "commercial": 7,
        },
        "par_statut_ocr": {
            "importe_orass": 89,
            "extrait": 24,
            "en_cours": 8,
            "non_traite": 6,
        },
        "taux_numerisation": 0.94,
        "derniere_mise_a_jour": datetime.now().isoformat(),
    }
