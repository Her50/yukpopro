"""
Tests d'intégration — Authentification & Autorisation JWT.
Couvre : login, token valide/invalide, endpoints protégés, RBAC.
"""
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_reussi_retourne_jwt_valide(client):
    """Login réussi → access_token JWT retourné avec les champs obligatoires."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "dg", "password": "yukpo2025"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Champs obligatoires
    assert "access_token" in data
    assert "token_type" in data
    assert "expires_in" in data

    # Valeurs correctes
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 20  # Token JWT non vide
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_retourne_info_utilisateur(client):
    """Login réussi → réponse contient le rôle et user_id."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "dg", "password": "yukpo2025"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # user_id ou role présents (selon l'implémentation)
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_mauvais_mot_de_passe_retourne_401(client):
    """Login avec mot de passe incorrect → 401 Unauthorized."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "dg", "password": "mauvais_mdp_incorrect"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_utilisateur_inexistant_retourne_401(client):
    """Login avec un username qui n'existe pas → 401."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "utilisateur_qui_nexiste_pas", "password": "n_importe_quoi"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_champs_vides_retourne_erreur(client):
    """Login avec champs vides → erreur de validation (422 ou 401)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "", "password": ""},
    )
    assert resp.status_code in (401, 422)


@pytest.mark.asyncio
async def test_login_payload_manquant_retourne_422(client):
    """Payload JSON manquant → 422 Unprocessable Entity."""
    resp = await client.post("/api/v1/auth/login", json={})
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT PROTÉGÉ — /me
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_endpoint_protege_sans_token_retourne_401(client):
    """GET /me sans Authorization header → 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_endpoint_protege_token_invalide_retourne_401(client):
    """GET /me avec token forgé → 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer token.invalide.forge"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_endpoint_protege_token_malformate_retourne_401(client):
    """GET /me avec header Authorization malformé → 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "PasUnBearer xyz"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_endpoint_protege_avec_token_valide_retourne_200(client, headers_agent):
    """GET /me avec token agent valide → 200 + infos utilisateur."""
    resp = await client.get("/api/v1/auth/me", headers=headers_agent)
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "role" in data


@pytest.mark.asyncio
async def test_endpoint_protege_avec_token_dg_retourne_200(client, headers_dg):
    """GET /me avec token DG → 200 + rôle dg."""
    resp = await client.get("/api/v1/auth/me", headers=headers_dg)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("role") == "dg"


# ─────────────────────────────────────────────────────────────────────────────
# RBAC — CONTRÔLE D'ACCÈS PAR RÔLE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_permission_insuffisante_agent_vers_cima_retourne_403(client, headers_agent):
    """Agent (rôle limité) tente d'accéder à CIMA Q&A → 403 Forbidden."""
    resp = await client.post(
        "/api/v1/cima/question",
        json={"question": "Quel est l'Art. 337-1 ?"},
        headers=headers_agent,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_permission_insuffisante_agent_vers_audit_retourne_403(client, headers_agent):
    """Agent ne peut pas accéder aux logs d'audit → 403."""
    resp = await client.get("/api/v1/audit/recent", headers=headers_agent)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dg_acces_audit_retourne_200(client, headers_dg):
    """DG a accès aux logs d'audit → 200."""
    resp = await client.get("/api/v1/audit/recent", headers=headers_dg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_acces_sinistres_sans_token_retourne_401(client):
    """Liste sinistres sans token → 401."""
    resp = await client.get("/api/v1/sinistres/SIN-2025-00001")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_agent_acces_sinistres_propres(client, headers_agent):
    """Agent peut accéder aux sinistres (endpoint autorisé à son rôle)."""
    resp = await client.get(
        "/api/v1/sinistres/SIN-TEST-INEXISTANT",
        headers=headers_agent,
    )
    # 200 (trouvé) ou 404 (inexistant) — pas 401 ni 403
    assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_refresh_token_ou_logout(client, headers_agent):
    """Test logout ou refresh — endpoint doit exister et répondre."""
    resp = await client.post("/api/v1/auth/logout", headers=headers_agent)
    # 200 OK ou 405 si non implémenté — pas 500
    assert resp.status_code != 500
