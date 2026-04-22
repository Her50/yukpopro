"""
Routes Profil Pro — Gestion du profil professionnel de l'utilisateur.

Endpoints :
  GET    /api/v1/pro/profil/         — Récupère le profil de l'utilisateur connecté
  POST   /api/v1/pro/profil/         — Crée le profil (première configuration)
  PUT    /api/v1/pro/profil/         — Met à jour le profil (PATCH sémantique)
  POST   /api/v1/pro/profil/memoire  — Ajoute un fait à la mémoire de l'agent
  DELETE /api/v1/pro/profil/memoire  — Efface toute la mémoire de l'agent
  GET    /api/v1/pro/profil/metiers  — Liste des métiers supportés
"""
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import async_session_maker

logger = logging.getLogger("yukpo_assurance.api.pro_profil")

router = APIRouter()


# ── Dépendance DB ──────────────────────────────────────────────────────────────

async def get_db():
    async with async_session_maker() as session:
        yield session


# ── Modèles Pydantic ───────────────────────────────────────────────────────────

class CreerProfilRequest(BaseModel):
    metier:            str  = Field(..., min_length=2, max_length=80,
                                    description="Ex: comptable, DRH, ingenieur, juriste")
    pays:              str  = Field("CM", min_length=2, max_length=5)
    secteur:           str  = Field("prive", description="prive | public | ngo | independant")
    niveau:            str  = Field("senior", description="junior | senior | expert | dirigeant")
    specialite:        Optional[str]  = None
    zone:              Optional[str]  = None
    entreprise:        Optional[str]  = None
    taille_entreprise: Optional[str]  = None
    secteur_activite:  Optional[str]  = None
    langue_reponse:    str  = "fr"
    style_reponse:     str  = "professionnel"
    format_prefere:    str  = "standard"
    preferences:       dict = Field(default_factory=dict)
    contexte_metier:   dict = Field(default_factory=dict)
    abonnement:        str  = "freemium"


class MettreAJourProfilRequest(BaseModel):
    metier:            Optional[str]  = None
    pays:              Optional[str]  = None
    secteur:           Optional[str]  = None
    niveau:            Optional[str]  = None
    specialite:        Optional[str]  = None
    zone:              Optional[str]  = None
    entreprise:        Optional[str]  = None
    taille_entreprise: Optional[str]  = None
    secteur_activite:  Optional[str]  = None
    langue_reponse:    Optional[str]  = None
    style_reponse:     Optional[str]  = None
    format_prefere:    Optional[str]  = None
    preferences:       Optional[dict] = None
    contexte_metier:   Optional[dict] = None


class AjouterMemoireRequest(BaseModel):
    fait: str = Field(..., min_length=5, max_length=500,
                      description="Fait à retenir par l'agent IA")


# ── Liste des métiers supportés ────────────────────────────────────────────────

METIERS_SUPPORTES = [
    {"id": "comptable",          "label": "Comptable / Expert-comptable",    "domaines_rag": ["fiscal", "comptabilite"]},
    {"id": "DRH",                "label": "Directeur des Ressources Humaines","domaines_rag": ["travail"]},
    {"id": "DAF",                "label": "Directeur Administratif et Financier", "domaines_rag": ["fiscal", "comptabilite", "commercial"]},
    {"id": "juriste",            "label": "Juriste / Avocat",                "domaines_rag": ["commercial", "travail", "marches_publics"]},
    {"id": "ingenieur",          "label": "Ingénieur / Chef de projet",       "domaines_rag": ["marches_publics"]},
    {"id": "medecin",            "label": "Médecin / Professionnel de santé", "domaines_rag": ["sante"]},
    {"id": "enseignant",         "label": "Enseignant / Formateur",           "domaines_rag": []},
    {"id": "banquier",           "label": "Banquier / Analyste crédit",       "domaines_rag": ["banque", "fiscal"]},
    {"id": "auditeur",           "label": "Auditeur / Contrôleur de gestion", "domaines_rag": ["fiscal", "comptabilite"]},
    {"id": "gestionnaire_rh",    "label": "Gestionnaire RH / Paie",          "domaines_rag": ["travail"]},
    {"id": "acheteur",           "label": "Acheteur / Responsable logistique","domaines_rag": ["commercial", "marches_publics"]},
    {"id": "architecte",         "label": "Architecte / BTP",                "domaines_rag": ["marches_publics"]},
    {"id": "entrepreneur",       "label": "Entrepreneur / Chef d'entreprise", "domaines_rag": ["commercial", "fiscal"]},
    {"id": "fiscaliste",         "label": "Fiscaliste / Conseiller fiscal",   "domaines_rag": ["fiscal"]},
    {"id": "trader",             "label": "Trader / Analyste marchés",        "domaines_rag": ["banque"]},
    {"id": "pharmacien",         "label": "Pharmacien / Para-médical",        "domaines_rag": ["sante"]},
    {"id": "consultant",         "label": "Consultant / Coach professionnel", "domaines_rag": ["commercial"]},
    {"id": "data_analyst",       "label": "Data Analyst / Business Analyst",  "domaines_rag": []},
    {"id": "directeur_commercial","label": "Directeur Commercial / Marketing","domaines_rag": ["commercial"]},
    {"id": "professionnel",      "label": "Autre professionnel",              "domaines_rag": []},
]


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/metiers", summary="Liste des métiers supportés")
async def lister_metiers():
    """Retourne la liste des métiers avec leurs domaines RAG associés."""
    return {"metiers": METIERS_SUPPORTES, "total": len(METIERS_SUPPORTES)}


@router.get("/", summary="Récupérer mon profil professionnel")
async def get_mon_profil(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne le profil professionnel de l'utilisateur connecté."""
    from modules.pro.service_profil import get_profil
    profil = await get_profil(current_user.user_id, db)
    if not profil:
        raise HTTPException(
            status_code=404,
            detail="Profil professionnel non créé. Utilisez POST /api/v1/pro/profil/",
        )
    return profil.to_dict()


@router.post("/", summary="Créer mon profil professionnel", status_code=201)
async def creer_mon_profil(
    req: CreerProfilRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Crée le profil professionnel de l'utilisateur connecté.
    À n'appeler qu'une fois — utiliser PUT pour les mises à jour.
    """
    from modules.pro.service_profil import creer_profil
    try:
        profil = await creer_profil(
            user_id=current_user.user_id,
            data=req.model_dump(exclude_none=True),
            db=db,
        )
        return profil.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/", summary="Mettre à jour mon profil professionnel")
async def mettre_a_jour_mon_profil(
    req: MettreAJourProfilRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Met à jour les champs fournis (PATCH sémantique).
    Les champs non fournis restent inchangés.
    """
    from modules.pro.service_profil import mettre_a_jour, get_or_create
    # Auto-crée le profil si absent (cas onboarding simplifié)
    profil, _ = await get_or_create(current_user.user_id, db)
    data = req.model_dump(exclude_none=True)
    if not data:
        return profil.to_dict()
    profil = await mettre_a_jour(current_user.user_id, data, db)
    return profil.to_dict()


@router.post("/memoire", summary="Ajouter un fait à la mémoire de l'agent")
async def ajouter_memoire(
    req: AjouterMemoireRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ajoute un fait persistant que l'agent IA doit mémoriser
    entre toutes les sessions (ex : 'Mon logiciel comptable est SAGE 100').
    """
    from modules.pro.service_profil import ajouter_memoire, get_or_create
    await get_or_create(current_user.user_id, db)
    profil = await ajouter_memoire(current_user.user_id, req.fait, db)
    return {
        "message":  "Fait mémorisé",
        "memoire":  profil.memoire_agent,
        "nb_faits": len(profil.memoire_agent or []),
    }


@router.delete("/memoire", summary="Effacer toute la mémoire de l'agent")
async def effacer_memoire(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Efface tous les faits mémorisés par l'agent pour cet utilisateur."""
    from modules.pro.service_profil import get_profil
    profil = await get_profil(current_user.user_id, db)
    if not profil:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    profil.memoire_agent = []
    await db.commit()
    return {"message": "Mémoire effacée"}


@router.post("/cv", summary="Uploader ou coller son CV pour la recherche d'emploi")
async def uploader_cv(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cv_texte: Optional[str]  = Form(None, description="CV collé en texte brut ou Markdown"),
    fichier: Optional[UploadFile] = File(None, description="Fichier CV (PDF, DOCX, TXT)"),
):
    """
    Sauvegarde le CV de l'utilisateur pour l'alimenter dans la génération automatique
    de CV/lettres de motivation et dans la veille emploi.

    Deux modes :
      - **Fichier** : uploader un PDF, DOCX ou TXT — le texte est extrait automatiquement
      - **Texte** : coller directement le contenu du CV dans le champ `cv_texte`
    """
    from modules.pro.service_profil import get_or_create
    from modules.pro.profil_pro import ProfilProfessionnelDB
    from sqlalchemy import update

    profil, _ = await get_or_create(current_user.user_id, db)

    cv_contenu = ""
    chemin_fichier = None

    # ── Mode fichier ──────────────────────────────────────────────────────
    if fichier:
        ext = Path(fichier.filename or "cv.txt").suffix.lower()
        if ext not in (".pdf", ".docx", ".doc", ".txt", ".md"):
            raise HTTPException(
                status_code=400,
                detail="Format non supporté. Utilisez PDF, DOCX ou TXT.",
            )

        contenu_raw = await fichier.read()

        # Extraction du texte
        try:
            if ext == ".pdf":
                try:
                    import io
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(io.BytesIO(contenu_raw))
                        cv_contenu = "\n".join(p.extract_text() or "" for p in reader.pages[:10])
                    except ImportError:
                        import PyPDF2
                        reader = PyPDF2.PdfReader(io.BytesIO(contenu_raw))
                        cv_contenu = "\n".join(p.extract_text() or "" for p in reader.pages[:10])
                except Exception:
                    cv_contenu = "[Extraction PDF échouée — veuillez coller le texte manuellement]"

            elif ext in (".docx", ".doc"):
                try:
                    import io, zipfile, re as _re
                    with zipfile.ZipFile(io.BytesIO(contenu_raw)) as z:
                        if "word/document.xml" in z.namelist():
                            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
                            cv_contenu = _re.sub(r"<[^>]+>", " ", xml)
                            cv_contenu = _re.sub(r"\s+", " ", cv_contenu).strip()
                except Exception:
                    cv_contenu = "[Extraction DOCX échouée — veuillez coller le texte manuellement]"

            else:  # .txt / .md
                cv_contenu = contenu_raw.decode("utf-8", errors="replace")

        except Exception as e:
            cv_contenu = f"[Erreur extraction : {e}]"

        # Sauvegarder le fichier physique
        try:
            data_dir = Path(__file__).parents[1] / "data" / "cv_uploads"
            data_dir.mkdir(parents=True, exist_ok=True)
            nom_fichier = f"cv_{current_user.user_id}_{uuid.uuid4().hex[:8]}{ext}"
            chemin = data_dir / nom_fichier
            chemin.write_bytes(contenu_raw)
            chemin_fichier = str(chemin.relative_to(Path(__file__).parents[1]))
        except Exception:
            pass

    # ── Mode texte collé ──────────────────────────────────────────────────
    elif cv_texte:
        cv_contenu = cv_texte.strip()[:50_000]  # limite 50k caractères
    else:
        raise HTTPException(
            status_code=400,
            detail="Fournir soit un fichier (`fichier`) soit du texte (`cv_texte`).",
        )

    if not cv_contenu.strip():
        raise HTTPException(status_code=422, detail="CV vide après extraction.")

    # Sauvegarder en DB
    await db.execute(
        update(ProfilProfessionnelDB)
        .where(ProfilProfessionnelDB.user_id == current_user.user_id)
        .values(
            cv_texte=cv_contenu[:50_000],
            cv_fichier_chemin=chemin_fichier,
        )
    )
    await db.commit()

    return {
        "message": "CV sauvegardé avec succès",
        "source": "fichier" if fichier else "texte",
        "nb_caracteres": len(cv_contenu),
        "fichier_chemin": chemin_fichier,
        "extrait": cv_contenu[:300] + "..." if len(cv_contenu) > 300 else cv_contenu,
    }


@router.delete("/cv", summary="Supprimer le CV stocké")
async def supprimer_cv(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Supprime le CV et le fichier associé du profil."""
    from modules.pro.profil_pro import ProfilProfessionnelDB
    from sqlalchemy import update

    await db.execute(
        update(ProfilProfessionnelDB)
        .where(ProfilProfessionnelDB.user_id == current_user.user_id)
        .values(cv_texte=None, cv_fichier_chemin=None)
    )
    await db.commit()
    return {"message": "CV supprimé"}


@router.post("/veille-emploi/activer", summary="Activer la veille emploi automatique")
async def activer_veille_emploi(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from modules.pro.profil_pro import ProfilProfessionnelDB
    from sqlalchemy import update
    await db.execute(
        update(ProfilProfessionnelDB)
        .where(ProfilProfessionnelDB.user_id == current_user.user_id)
        .values(recherche_emploi_active=True)
    )
    await db.commit()
    return {"actif": True, "message": "Veille emploi activée"}


@router.post("/veille-emploi/desactiver", summary="Désactiver la veille emploi automatique")
async def desactiver_veille_emploi(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from modules.pro.profil_pro import ProfilProfessionnelDB
    from sqlalchemy import update
    await db.execute(
        update(ProfilProfessionnelDB)
        .where(ProfilProfessionnelDB.user_id == current_user.user_id)
        .values(recherche_emploi_active=False)
    )
    await db.commit()
    return {"actif": False, "message": "Veille emploi désactivée"}


@router.post("/veille-emploi/rechercher", summary="Lancer une recherche emploi immédiate")
async def lancer_recherche_emploi(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from modules.pro.scheduler_emploi import rechercher_offres_pour_user
    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    nb = await rechercher_offres_pour_user(user_id=current_user.user_id, profil=profil)
    # Recharger le profil pour les offres fraîches
    await db.refresh(profil)
    offres = profil.offres_emploi_recentes or []
    return {"nb_offres": nb, "offres": offres}


@router.post("/marches/rechercher", summary="Lancer une recherche d'appels d'offres immédiate")
async def lancer_recherche_marches(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from modules.pro.scheduler_marches import rechercher_marches_pour_user
    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    nb = await rechercher_marches_pour_user(user_id=current_user.user_id, profil=profil)
    await db.refresh(profil)
    marches = profil.marches_publics_recents or []
    return {"nb_marches": nb, "marches": marches}


@router.get("/badges", summary="Mes badges et progression XP")
async def mes_badges(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne les badges débloqués et la progression XP."""
    from modules.pro.service_profil import get_profil
    profil = await get_profil(current_user.user_id, db)
    if not profil:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return {
        "badges":    profil.badges or [],
        "points_xp": profil.points_xp,
        "niveau_xp": profil.niveau_xp,
        "stats":     profil.stats_usage or {},
    }
