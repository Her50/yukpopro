"""
Configuration pytest pour YukpoAssurance.
Fixtures : client FastAPI, tokens JWT, mock ia_client, DB SQLite in-memory,
           factories de données (sinistres, contrats, courtiers).
"""
import os
import uuid
from datetime import date, datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ─── Variables d'environnement — AVANT tout import applicatif ─────────────────
os.environ.setdefault("ORASS_MODE", "simulation")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_yukpo.db")
os.environ.setdefault("CLAUDE_API_KEY", "test-key-not-real")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only-not-production")
os.environ.setdefault("REDIS_URL", "")  # Pas de Redis en tests

from httpx import ASGITransport, AsyncClient


# ─────────────────────────────────────────────────────────────────────────────
# RÉPONSE IA FICTIVE — utilisée par tous les mocks ia_client
# ─────────────────────────────────────────────────────────────────────────────
IA_FAKE_RESPONSE = {
    "content": (
        "Selon l'Article 337-1 du Code CIMA, la marge de solvabilité minimum "
        "est calculée sur la base des primes nettes ou des sinistres moyens "
        "des trois derniers exercices. Montant: 500 000 000 FCFA."
    ),
    "model": "claude-3-5-sonnet-mock",
    "usage": {"input_tokens": 150, "output_tokens": 80},
    "mode": "mock",
}

IA_FAKE_OUTLINE = {
    "document_type": "docx",
    "title": "Rapport de test",
    "sections": [
        {"title": "Introduction", "content": "Contenu de test généré par le mock IA."},
        {"title": "Analyse", "content": "Données analysées : conformité CIMA vérifiée."},
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE — BASE DE DONNÉES (SQLite en mémoire pour la session)
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session", autouse=True)
async def creer_tables_test():
    """Crée les tables SQLite une seule fois avant tous les tests."""
    from core.database import engine, init_db

    await init_db()
    yield
    await engine.dispose()
    try:
        os.remove("test_yukpo.db")
    except (FileNotFoundError, PermissionError):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE — MOCK ia_client (pas d'appels IA réels pendant les tests)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_ia_client():
    """
    Mock global de ia_client pour tous les tests.
    Retourne une réponse fixe sans appel réseau.
    """
    from core.ia_client import ReponseIA

    fake_reponse_ia = ReponseIA(
        contenu=IA_FAKE_RESPONSE["content"],
        modele_utilise=IA_FAKE_RESPONSE["model"],
    )

    mock = AsyncMock()
    mock.chat.return_value = IA_FAKE_RESPONSE
    mock.complete.return_value = IA_FAKE_RESPONSE["content"]
    mock.generer_outline.return_value = IA_FAKE_OUTLINE
    mock.appel_avec_image.return_value = IA_FAKE_RESPONSE
    mock.appeler.return_value = fake_reponse_ia

    with patch("core.ia_client.ia_client", mock):
        with patch("modules.chat.yukpo_ia_assurance.ia_client", mock):
            with patch("modules.cima.etats_reglementaires.ia_client", mock):
                with patch("modules.documents.generateur.ia_client", mock):
                    with patch("modules.souscription.portail.ia_client", mock):
                        with patch("modules.cima.verificateur_crca.ia_client", mock):
                            try:
                                from core.orchestrateur import orchestrateur as _orchestrateur
                                with patch.object(_orchestrateur, "_ia", mock):
                                    yield mock
                            except ImportError:
                                yield mock


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE — CLIENT HTTP FastAPI
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Client HTTP asynchrone pour l'API FastAPI (sans serveur réel)."""
    from api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES — TOKENS JWT PAR RÔLE
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def token_agent(client: AsyncClient) -> str:
    """Token JWT pour un utilisateur de rôle 'agent'."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "testagent", "password": "yukpo2025"},
    )
    assert resp.status_code == 200, f"Login agent échoué: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def token_manager(client: AsyncClient) -> str:
    """Token JWT pour un utilisateur de rôle 'manager' (directeur technique)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "daf", "password": "yukpo2025"},
    )
    assert resp.status_code == 200, f"Login manager échoué: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def token_admin(client: AsyncClient) -> str:
    """Token JWT pour un utilisateur de rôle 'dg' (admin)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "dg", "password": "yukpo2025"},
    )
    assert resp.status_code == 200, f"Login admin échoué: {resp.text}"
    return resp.json()["access_token"]


# Alias pour compatibilité avec les fixtures existantes
@pytest_asyncio.fixture
async def token_dg(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "dg", "password": "yukpo2025"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def token_daf(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "daf", "password": "yukpo2025"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES — HEADERS AUTH
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def headers_agent(token_agent: str) -> dict:
    return {"Authorization": f"Bearer {token_agent}"}


@pytest_asyncio.fixture
async def headers_manager(token_manager: str) -> dict:
    return {"Authorization": f"Bearer {token_manager}"}


@pytest_asyncio.fixture
async def headers_admin(token_admin: str) -> dict:
    return {"Authorization": f"Bearer {token_admin}"}


@pytest_asyncio.fixture
async def headers_dg(token_dg: str) -> dict:
    return {"Authorization": f"Bearer {token_dg}"}


@pytest_asyncio.fixture
async def headers_daf(token_daf: str) -> dict:
    return {"Authorization": f"Bearer {token_daf}"}


# ─────────────────────────────────────────────────────────────────────────────
# FACTORIES — DONNÉES DE TEST
# ─────────────────────────────────────────────────────────────────────────────

def make_sinistre(
    numero: str | None = None,
    nature: str = "collision",
    montant: int = 350_000,
    suspect: bool = False,
) -> dict:
    """Factory — crée un dossier sinistre de test."""
    numero = numero or f"SIN-TEST-{uuid.uuid4().hex[:8].upper()}"
    base = {
        "numero_sinistre": numero,
        "numero_police": "AUTO-2025-PYTEST-001",
        "date_sinistre": (date.today() - timedelta(days=5)).isoformat(),
        "date_declaration": date.today().isoformat(),
        "nature": nature,
        "description": "Accrochage au carrefour durant tests pytest",
        "lieu": "Yaoundé, Carrefour Bastos",
        "montant_declare": montant,
        "pieces_fournies": ["constat_amiable", "cni", "carte_grise", "permis"],
        "tiers_impliques": [],
        "blesses": False,
        "historique_sinistres_client": 0,
        "branche": "auto",
        "statut": "ouvert",
    }
    if suspect:
        base.update(
            {
                "heure_sinistre": "02:30",
                "montant_declare": 9_500_000,
                "pieces_fournies": [],
                "historique_sinistres_client": 6,
                "nature": "vol",
            }
        )
    return base


def make_contrat(
    numero_police: str | None = None,
    branche: str = "auto",
    actif: bool = True,
) -> dict:
    """Factory — crée un contrat/police de test."""
    numero_police = numero_police or f"AUTO-2025-PYTEST-{uuid.uuid4().hex[:6].upper()}"
    return {
        "numero_police": numero_police,
        "branche": branche,
        "date_effet": (date.today() - timedelta(days=180)).isoformat(),
        "date_echeance": (date.today() + timedelta(days=185)).isoformat(),
        "prime_ttc": 185_000,
        "statut": "actif" if actif else "résilié",
        "assure": {
            "nom": "Dupont Test",
            "cni": "CM-TEST-123456",
            "telephone": "+237600000001",
            "adresse": "Yaoundé, BP 0001",
        },
        "vehicule": {
            "immatriculation": "CE-TEST-2024",
            "marque": "Toyota",
            "modele": "Corolla",
            "annee": 2022,
            "valeur_venale": 8_500_000,
        },
        "compagnie_code": "PYTEST_COMPAGNIE",
        "courtier_code": "PYTEST_COURTIER",
    }


def make_courtier(code: str | None = None) -> dict:
    """Factory — crée un courtier de test."""
    code = code or f"CRTIER-PYTEST-{uuid.uuid4().hex[:4].upper()}"
    return {
        "code": code,
        "raison_sociale": "Cabinet Test Assurances",
        "responsable": "Jean Test",
        "email": "test@cabinettest.cm",
        "telephone": "+237699000001",
        "agrement": f"AGR-PYTEST-{code}",
        "ville": "Yaoundé",
        "actif": True,
        "portefeuille": {
            "nombre_contrats": 45,
            "primes_ttc_annuelles": 12_500_000,
        },
    }


def make_dossier_souscription_auto(complet: bool = True) -> dict:
    """Factory — dossier souscription auto pour tests."""
    base = {
        "branche": "auto",
        "donnees_client": {
            "nom": "Martin Test",
            "prenom": "Pierre",
            "cni_numero": "CM-2025-PYTEST",
            "date_naissance": "1985-06-15",
            "adresse": "Douala, Akwa BP 999",
            "telephone": "+237677000001",
            "profession": "Ingénieur",
            "vehicule": {
                "immatriculation": "LT-PYTEST-2025",
                "marque": "Toyota",
                "modele": "Hilux",
                "annee": 2023,
                "valeur_venale": 14_000_000,
                "usage": "personnel",
                "puissance_fiscale": 7,
            },
        },
        "courtier_code": "PYTEST_COURTIER",
        "agent_code": "PYTEST_AGENT",
    }
    if not complet:
        # Dossier incomplet : vehicule absent
        del base["donnees_client"]["vehicule"]
    return base


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES UTILISANT LES FACTORIES
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def sinistre_normal() -> dict:
    return make_sinistre()


@pytest.fixture
def sinistre_suspect() -> dict:
    return make_sinistre(suspect=True)


@pytest.fixture
def contrat_auto() -> dict:
    return make_contrat()


@pytest.fixture
def courtier_test() -> dict:
    return make_courtier()


@pytest.fixture
def dossier_souscription_complet() -> dict:
    return make_dossier_souscription_auto(complet=True)


@pytest.fixture
def dossier_souscription_incomplet() -> dict:
    return make_dossier_souscription_auto(complet=False)
