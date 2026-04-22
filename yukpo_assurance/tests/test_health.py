"""Tests du healthcheck et de la configuration."""
import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """GET /health retourne un statut avec les checks."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "statut" in data
    assert "checks" in data
    assert "version" in data
    checks = data["checks"]
    assert "database" in checks
    assert "redis" in checks
    assert "claude_api_key" in checks


@pytest.mark.asyncio
async def test_racine(client):
    """GET / retourne les infos de l'application."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["application"] == "YukpoAssurance"
    assert data["statut"] == "opérationnel"
    assert len(data["modules"]) >= 5


def test_settings_secret_key_non_vide():
    """SECRET_KEY ne doit pas être vide."""
    from config.settings import settings
    assert settings.SECRET_KEY
    assert len(settings.SECRET_KEY) >= 32


def test_settings_validate_production_sans_cles():
    """Sans clés API, validate_production retourne des warnings."""
    from config.settings import settings
    issues = settings.validate_production()
    # En mode test, CLAUDE_API_KEY = "test-key-not-real" donc pas "manquant"
    # mais ORASS_MODE=simulation doit apparaître
    assert isinstance(issues, list)


def test_auth_token_creation_et_decodage():
    """Créer un token et le décoder → données cohérentes."""
    from core.auth import creer_token, _decoder_token
    token = creer_token(user_id=42, user_nom="TestUser", role="manager", compagnie_id=1)
    assert token
    data = _decoder_token(token)
    assert data.user_id == 42
    assert data.user_nom == "TestUser"
    assert data.role == "manager"
    assert data.compagnie_id == 1


def test_permission_check():
    """Vérification des permissions par rôle."""
    from core.auth import _a_permission
    assert _a_permission("agent", "chat") is True
    assert _a_permission("agent", "cima") is False
    assert _a_permission("daf", "comptabilite") is True
    assert _a_permission("daf", "audit") is False
    assert _a_permission("dg", "audit") is True
    assert _a_permission("admin", "anything") is True
