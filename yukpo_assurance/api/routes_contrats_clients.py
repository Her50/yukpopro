"""
Routes FastAPI — Génération et livraison des contrats clients.
- POST /generer          : générer un contrat PDF (retourne bytes ou sauvegarde)
- POST /envoyer          : générer + envoyer par email et/ou WhatsApp
- GET  /telecharger/{id} : télécharger un contrat déjà généré
- GET  /liste            : liste des contrats émis
- POST /depuis-orass     : générer à partir d'une police ORASS
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, CompagnieDB
from core.auth import get_current_user, TokenData
from core.multitenancy import require_module
from core.orass_connector import OrassConnector
from modules.contrats.generateur_contrats import (
    DonneesContrat,
    GarantieContrat,
    GestionnaireContratsClients,
    ProfilCompagnie,
    ServiceLivraisonContrat,
)

router = APIRouter(prefix="/contrats-clients", tags=["Contrats Clients"])

# Dossier de stockage des PDFs générés
CONTRATS_DIR = Path(os.getenv("CONTRATS_DIR", "data/contrats_generes"))
CONTRATS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# Schémas
# ─────────────────────────────────────────────────────────────

class GarantieSchema(BaseModel):
    libelle: str
    capital_assure: float = 0.0
    franchise: float = 0.0
    prime_nette: float
    taux_taxe: float = 0.15
    observations: str = ""


class GenererContratSchema(BaseModel):
    # Identification
    numero_police: str
    type_contrat: str = "AUTO"
    branche: str = "Responsabilité Civile Automobile"

    # Assuré
    nom_assure: str
    prenom_assure: str = ""
    date_naissance: Optional[date] = None
    adresse_assure: str = ""
    telephone_assure: str = ""
    email_assure: str = ""
    numero_cni: str = ""

    # Période
    date_effet: date = Field(default_factory=date.today)
    date_echeance: Optional[date] = None
    duree_mois: int = 12

    # Objet
    objet_assure: str = ""
    valeur_assure: float = 0.0

    # Garanties
    garanties: List[GarantieSchema] = []

    # Intermédiaire
    courtier: str = ""
    apporteur: str = ""

    # Références SI
    ref_orass: str = ""
    ref_mercure: str = ""

    # Clauses
    clauses_particulieres: str = ""


class EnvoyerContratSchema(BaseModel):
    contrat: GenererContratSchema
    email: Optional[str] = None
    whatsapp: Optional[str] = None


class DepuisOrassSchema(BaseModel):
    numero_police: str
    email: Optional[str] = None
    whatsapp: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _get_compagnie(compagnie_id: int, db: AsyncSession) -> Optional[CompagnieDB]:
    r = await db.execute(select(CompagnieDB).where(CompagnieDB.id == compagnie_id))
    return r.scalar_one_or_none()


def _build_profil(compagnie: CompagnieDB) -> ProfilCompagnie:
    return ProfilCompagnie(
        nom=compagnie.nom or "",
        adresse=compagnie.adresse or "",
        ville=compagnie.ville or "",
        pays=compagnie.pays or "",
        telephone=compagnie.telephone or "",
        email=compagnie.email_contact or "",
        site_web=compagnie.site_web or "",
        rccm=compagnie.rccm or "",
        contribuable=compagnie.numero_contribuable or "",
        agrement_crca=compagnie.agrement_crca or "",
        capital_social=compagnie.capital_social or "",
        logo_url=compagnie.logo_url or "",
        couleur_principale=compagnie.couleur_principale or "#003366",
        couleur_secondaire=compagnie.couleur_secondaire or "#E8F0FE",
    )


def _build_livraison(compagnie: CompagnieDB) -> ServiceLivraisonContrat:
    return ServiceLivraisonContrat(
        smtp_host=compagnie.smtp_host or "",
        smtp_port=compagnie.smtp_port or 587,
        smtp_user=compagnie.smtp_user or "",
        smtp_password=compagnie.smtp_password or "",
        smtp_from=compagnie.smtp_from or compagnie.email_contact or "",
        whatsapp_phone_id=compagnie.whatsapp_phone_id or "",
        whatsapp_token=compagnie.whatsapp_token or "",
    )


def _schema_to_donnees(schema: GenererContratSchema) -> DonneesContrat:
    garanties = [
        GarantieContrat(
            libelle=g.libelle,
            capital_assure=g.capital_assure,
            franchise=g.franchise,
            prime_nette=g.prime_nette,
            taux_taxe=g.taux_taxe,
            observations=g.observations,
        )
        for g in schema.garanties
    ]
    return DonneesContrat(
        numero_police=schema.numero_police,
        type_contrat=schema.type_contrat,
        branche=schema.branche,
        nom_assure=schema.nom_assure,
        prenom_assure=schema.prenom_assure,
        date_naissance=schema.date_naissance,
        adresse_assure=schema.adresse_assure,
        telephone_assure=schema.telephone_assure,
        email_assure=schema.email_assure,
        numero_cni=schema.numero_cni,
        date_effet=schema.date_effet,
        date_echeance=schema.date_echeance,
        duree_mois=schema.duree_mois,
        objet_assure=schema.objet_assure,
        valeur_assure=schema.valeur_assure,
        garanties=garanties,
        courtier=schema.courtier,
        apporteur=schema.apporteur,
        ref_orass=schema.ref_orass,
        ref_mercure=schema.ref_mercure,
        clauses_particulieres=schema.clauses_particulieres,
    )


def _sauvegarder_pdf(pdf_bytes: bytes, nom_fichier: str) -> Path:
    chemin = CONTRATS_DIR / nom_fichier
    chemin.write_bytes(pdf_bytes)
    return chemin


# ─────────────────────────────────────────────────────────────
# Générer (retourne le PDF directement)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/generer",
    response_class=Response,
    dependencies=[Depends(require_module("contrats_clients"))],
)
async def generer_contrat(
    payload: GenererContratSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Génère le PDF et le retourne directement en réponse."""
    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    profil = _build_profil(compagnie)
    gestionnaire = GestionnaireContratsClients(profil)
    contrat = _schema_to_donnees(payload)
    pdf_bytes = gestionnaire.generer_pdf(contrat)

    nom_fichier = f"Contrat_{payload.numero_police}_{payload.nom_assure.upper()}.pdf"
    _sauvegarder_pdf(pdf_bytes, nom_fichier)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nom_fichier}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


# ─────────────────────────────────────────────────────────────
# Envoyer (générer + livrer email / WhatsApp)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/envoyer",
    dependencies=[Depends(require_module("contrats_clients"))],
)
async def envoyer_contrat(
    payload: EnvoyerContratSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Génère le contrat et l'envoie par email et/ou WhatsApp."""
    if not payload.email and not payload.whatsapp:
        raise HTTPException(400, "Fournir au moins un email ou un numéro WhatsApp")

    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    profil = _build_profil(compagnie)
    livraison = _build_livraison(compagnie)
    gestionnaire = GestionnaireContratsClients(profil, livraison)
    contrat = _schema_to_donnees(payload.contrat)

    resultat = await gestionnaire.generer_et_livrer(
        contrat=contrat,
        email=payload.email,
        whatsapp=payload.whatsapp,
    )

    # Sauvegarde locale
    _sauvegarder_pdf(resultat["pdf_bytes"], resultat["nom_fichier"])

    return {
        "numero_police": payload.contrat.numero_police,
        "nom_fichier": resultat["nom_fichier"],
        "email_envoye": resultat["email_envoye"],
        "whatsapp_envoye": resultat["whatsapp_envoye"],
        "prime_ttc": contrat.prime_ttc_totale,
    }


# ─────────────────────────────────────────────────────────────
# Générer depuis ORASS
# ─────────────────────────────────────────────────────────────

@router.post(
    "/depuis-orass",
    dependencies=[Depends(require_module("contrats_clients"))],
)
async def contrat_depuis_orass(
    payload: DepuisOrassSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère les données d'une police depuis ORASS/Mercure
    et génère le contrat PDF, puis l'envoie.
    """
    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    # Récupération ORASS
    connector = OrassConnector()
    contrat_orass = await connector.rechercher_contrat(numero_police=payload.numero_police)
    if not contrat_orass:
        raise HTTPException(404, f"Police {payload.numero_police} non trouvée dans ORASS/Mercure")

    # Construire les données contrat depuis ORASS
    # Les champs correspondent au dataclass Contrat de orass_connector
    garanties = []
    for g in getattr(contrat_orass, "garanties", []):
        garanties.append(GarantieContrat(
            libelle=g.get("libelle", ""),
            capital_assure=g.get("capital", 0.0),
            franchise=g.get("franchise", 0.0),
            prime_nette=g.get("prime_nette", 0.0),
        ))

    # Si pas de garanties dans ORASS, créer une garantie générique avec la prime totale
    if not garanties and getattr(contrat_orass, "prime_nette", 0):
        garanties.append(GarantieContrat(
            libelle=getattr(contrat_orass, "branche", "RC Auto"),
            capital_assure=0.0,
            prime_nette=getattr(contrat_orass, "prime_nette", 0.0),
        ))

    contrat = DonneesContrat(
        numero_police=contrat_orass.numero_police,
        type_contrat=getattr(contrat_orass, "type_contrat", "AUTO"),
        branche=getattr(contrat_orass, "branche", "Assurance"),
        nom_assure=getattr(contrat_orass, "nom", ""),
        prenom_assure=getattr(contrat_orass, "prenom", ""),
        date_naissance=getattr(contrat_orass, "date_naissance", None),
        telephone_assure=getattr(contrat_orass, "telephone", ""),
        date_effet=getattr(contrat_orass, "date_effet", date.today()),
        date_echeance=getattr(contrat_orass, "date_echeance", None),
        objet_assure=getattr(contrat_orass, "objet_assure", ""),
        garanties=garanties,
        ref_orass=payload.numero_police,
    )

    profil = _build_profil(compagnie)
    livraison = _build_livraison(compagnie)
    gestionnaire = GestionnaireContratsClients(profil, livraison)

    email_dest = payload.email or getattr(contrat_orass, "email", None)
    whatsapp_dest = payload.whatsapp or getattr(contrat_orass, "telephone", None)

    resultat = await gestionnaire.generer_et_livrer(
        contrat=contrat,
        email=email_dest,
        whatsapp=whatsapp_dest,
    )
    _sauvegarder_pdf(resultat["pdf_bytes"], resultat["nom_fichier"])

    return {
        "numero_police": payload.numero_police,
        "nom_fichier": resultat["nom_fichier"],
        "assure": contrat.assure_complet,
        "prime_ttc": contrat.prime_ttc_totale,
        "email_envoye": resultat["email_envoye"],
        "whatsapp_envoye": resultat["whatsapp_envoye"],
    }


# ─────────────────────────────────────────────────────────────
# Télécharger un contrat déjà généré
# ─────────────────────────────────────────────────────────────

@router.get(
    "/telecharger/{nom_fichier}",
    response_class=Response,
    dependencies=[Depends(require_module("contrats_clients"))],
)
async def telecharger_contrat(
    nom_fichier: str,
    _: TokenData = Depends(get_current_user),
):
    # Sécurité : on ne permet que les noms sans chemin
    safe_nom = Path(nom_fichier).name
    chemin = CONTRATS_DIR / safe_nom

    if not chemin.exists():
        raise HTTPException(404, "Fichier introuvable")

    pdf_bytes = chemin.read_bytes()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_nom}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


# ─────────────────────────────────────────────────────────────
# Liste des contrats générés
# ─────────────────────────────────────────────────────────────

@router.get(
    "/liste",
    dependencies=[Depends(require_module("contrats_clients"))],
)
async def lister_contrats(
    _: TokenData = Depends(get_current_user),
    limit: int = Query(50, le=200),
):
    """Liste les fichiers PDF générés récemment (dossier local)."""
    fichiers = sorted(
        CONTRATS_DIR.glob("Contrat_*.pdf"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]

    return [
        {
            "nom_fichier": f.name,
            "taille_ko": round(f.stat().st_size / 1024, 1),
            "genere_le": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc),
        }
        for f in fichiers
    ]
