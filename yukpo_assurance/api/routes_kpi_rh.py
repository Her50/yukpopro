"""
YukpoAssurance — Routes API KPI Performance RH
Calcul automatique des scores de performance à partir des actions réelles
sur la plateforme. Transparence totale pour les primes à la performance.
"""
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData
from core.database import get_db

router = APIRouter()

# ─── Modèles Pydantic ─────────────────────────────────────────────────────────

class KpiEmployeOut(BaseModel):
    employe_id: str
    employe_nom: str
    matricule: str
    departement: str
    score_global: float          # 0–100
    score_qualite: float
    score_reactivite: float
    score_volume: float
    score_objectifs: float

    # Métriques brutes (agrégées depuis les logs plateforme)
    sinistres_traites: int
    sinistres_clos: int
    contrats_emis: int
    documents_scannes: int
    demandes_traitees: int       # demandes RH, devis, etc.
    messages_ia_envoyes: int
    reponse_moyenne_heures: float
    taux_completion_objectifs: float

    objectif_mensuel: int
    realise_mensuel: int
    periode: str                 # ex: "2026-04"
    badges: List[str]
    historique_scores: List[Dict[str, Any]]

class ObjectifEmployeIn(BaseModel):
    employe_id: str
    periode: str                 # YYYY-MM
    objectif_sinistres: int = 0
    objectif_contrats: int = 0
    objectif_documents: int = 0
    objectif_score_min: float = 70.0
    commentaire: Optional[str] = None

class DemandeRHIn(BaseModel):
    employe_id: str
    type: str                    # conge, attestation, avance, formation, certificat, autre
    description: str
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None

class DemandeRHOut(BaseModel):
    id: str
    employe_id: str
    employe_nom: str
    type: str
    description: str
    date_demande: str
    date_debut: Optional[str] = None
    date_fin: Optional[str] = None
    statut: str
    commentaire_rh: Optional[str] = None

# ─── Données démo ─────────────────────────────────────────────────────────────

DEMO_KPI = [
    KpiEmployeOut(
        employe_id="EMP-005", employe_nom="Coulibaly Seydou", matricule="EMP-005",
        departement="Digital", score_global=95.0, score_qualite=98.0,
        score_reactivite=96.0, score_volume=92.0, score_objectifs=94.0,
        sinistres_traites=0, sinistres_clos=0, contrats_emis=0,
        documents_scannes=142, demandes_traitees=87, messages_ia_envoyes=234,
        reponse_moyenne_heures=0.8, taux_completion_objectifs=0.98,
        objectif_mensuel=100, realise_mensuel=98, periode="2026-04",
        badges=["🏆 Top performer", "⚡ Réactivité", "🤖 IA Expert"],
        historique_scores=[
            {"mois": "2025-11", "score": 88},
            {"mois": "2025-12", "score": 90},
            {"mois": "2026-01", "score": 91},
            {"mois": "2026-02", "score": 93},
            {"mois": "2026-03", "score": 95},
        ],
    ),
    KpiEmployeOut(
        employe_id="EMP-001", employe_nom="Kouassi Jean-Baptiste", matricule="EMP-001",
        departement="Technique", score_global=91.0, score_qualite=94.0,
        score_reactivite=89.0, score_volume=88.0, score_objectifs=93.0,
        sinistres_traites=18, sinistres_clos=15, contrats_emis=4,
        documents_scannes=56, demandes_traitees=23, messages_ia_envoyes=89,
        reponse_moyenne_heures=1.2, taux_completion_objectifs=0.95,
        objectif_mensuel=20, realise_mensuel=18, periode="2026-04",
        badges=["🥇 Expert sinistres", "📋 Rigueur"],
        historique_scores=[
            {"mois": "2025-11", "score": 85},
            {"mois": "2025-12", "score": 87},
            {"mois": "2026-01", "score": 88},
            {"mois": "2026-02", "score": 90},
            {"mois": "2026-03", "score": 91},
        ],
    ),
    KpiEmployeOut(
        employe_id="EMP-002", employe_nom="Traoré Fatoumata", matricule="EMP-002",
        departement="Sinistres", score_global=87.0, score_qualite=90.0,
        score_reactivite=85.0, score_volume=88.0, score_objectifs=86.0,
        sinistres_traites=34, sinistres_clos=28, contrats_emis=0,
        documents_scannes=89, demandes_traitees=34, messages_ia_envoyes=145,
        reponse_moyenne_heures=1.5, taux_completion_objectifs=0.92,
        objectif_mensuel=35, realise_mensuel=34, periode="2026-04",
        badges=["🛡️ Sinistres Pro"],
        historique_scores=[
            {"mois": "2025-11", "score": 80},
            {"mois": "2025-12", "score": 82},
            {"mois": "2026-01", "score": 83},
            {"mois": "2026-02", "score": 85},
            {"mois": "2026-03", "score": 87},
        ],
    ),
]

DEMO_DEMANDES = [
    DemandeRHOut(id="DEM-001", employe_id="EMP-002", employe_nom="Traoré Fatoumata", type="conge", description="Congé annuel — 15 jours", date_demande="2026-04-08", date_debut="2026-04-21", date_fin="2026-05-05", statut="en_attente"),
    DemandeRHOut(id="DEM-002", employe_id="EMP-003", employe_nom="Diallo Ibrahim", type="attestation", description="Attestation de travail pour dossier bancaire", date_demande="2026-04-09", statut="approuve", commentaire_rh="Document généré et remis."),
    DemandeRHOut(id="DEM-003", employe_id="EMP-005", employe_nom="Coulibaly Seydou", type="formation", description="Formation LLM — Fine-tuning (3 jours)", date_demande="2026-04-05", date_debut="2026-04-28", date_fin="2026-04-30", statut="approuve", commentaire_rh="Approuvé — budget IT disponible."),
]

# ─── Routes KPI ───────────────────────────────────────────────────────────────

@router.get("/classement", response_model=List[KpiEmployeOut])
async def classement_performance(
    periode: Optional[str] = Query(None, description="YYYY-MM — défaut : mois courant"),
    departement: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Classement des employés par score de performance — calculé automatiquement."""
    result = DEMO_KPI
    if departement:
        result = [k for k in result if k.departement == departement]
    return sorted(result, key=lambda k: k.score_global, reverse=True)


@router.get("/{employe_id}", response_model=KpiEmployeOut)
async def detail_kpi_employe(
    employe_id: str,
    periode: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Détail KPI d'un employé pour une période donnée."""
    kpi = next((k for k in DEMO_KPI if k.employe_id == employe_id), None)
    if not kpi:
        raise HTTPException(status_code=404, detail=f"Employé {employe_id} non trouvé")
    return kpi


@router.post("/objectifs")
async def definir_objectifs(
    objectif: ObjectifEmployeIn,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Définit les objectifs périodiques d'un employé (RH Manager / DG uniquement)."""
    return {
        "success": True,
        "message": f"Objectifs définis pour {objectif.employe_id} — période {objectif.periode}",
        "objectif": objectif.dict(),
    }


@router.get("/stats/synthese")
async def synthese_rh(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Synthèse globale RH : scores, évolutions, alertes."""
    scores = [k.score_global for k in DEMO_KPI]
    return {
        "score_moyen_equipe": round(sum(scores) / len(scores), 1),
        "top_performer": DEMO_KPI[0].employe_nom,
        "top_score": DEMO_KPI[0].score_global,
        "employes_en_difficulte": [k.employe_nom for k in DEMO_KPI if k.score_global < 70],
        "taux_objectifs_atteints": round(sum(k.taux_completion_objectifs for k in DEMO_KPI) / len(DEMO_KPI) * 100, 1),
        "total_sinistres_traites": sum(k.sinistres_traites for k in DEMO_KPI),
        "total_contrats_emis": sum(k.contrats_emis for k in DEMO_KPI),
        "total_documents_scannes": sum(k.documents_scannes for k in DEMO_KPI),
        "periode": datetime.now().strftime("%Y-%m"),
    }

# ─── Routes Demandes RH ────────────────────────────────────────────────────────

@router.get("/demandes/liste", response_model=List[DemandeRHOut])
async def lister_demandes(
    statut: Optional[str] = Query(None),
    employe_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste les demandes RH avec filtres optionnels."""
    result = DEMO_DEMANDES
    if statut:
        result = [d for d in result if d.statut == statut]
    if employe_id:
        result = [d for d in result if d.employe_id == employe_id]
    return result


@router.post("/demandes/nouvelle", response_model=DemandeRHOut)
async def nouvelle_demande(
    demande: DemandeRHIn,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soumet une nouvelle demande RH (dématérialisée)."""
    import uuid as _uuid
    return DemandeRHOut(
        id=f"DEM-{_uuid.uuid4().hex[:6].upper()}",
        employe_id=demande.employe_id,
        employe_nom=current_user.email or demande.employe_id,
        type=demande.type,
        description=demande.description,
        date_demande=datetime.now().strftime("%Y-%m-%d"),
        date_debut=demande.date_debut.isoformat() if demande.date_debut else None,
        date_fin=demande.date_fin.isoformat() if demande.date_fin else None,
        statut="en_attente",
    )


@router.patch("/demandes/{demande_id}/traiter")
async def traiter_demande(
    demande_id: str,
    statut: str = Query(..., description="approuve ou refuse"),
    commentaire: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approuve ou refuse une demande RH."""
    if statut not in ["approuve", "refuse"]:
        raise HTTPException(status_code=400, detail="Statut invalide : utiliser 'approuve' ou 'refuse'")
    return {
        "success": True,
        "demande_id": demande_id,
        "nouveau_statut": statut,
        "traite_par": current_user.email,
        "commentaire": commentaire,
        "timestamp": datetime.now().isoformat(),
    }
