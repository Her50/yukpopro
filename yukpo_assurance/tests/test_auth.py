"""Tests d'authentification JWT."""
import pytest


@pytest.mark.asyncio
async def test_login_succes(client):
    """Login avec mot de passe correct → token renvoyé."""
    resp = await client.post("/api/v1/auth/login", json={
        "username": "dg",
        "password": "yukpo2025",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_mauvais_mot_de_passe(client):
    """Login avec mauvais mot de passe → 401."""
    resp = await client.post("/api/v1/auth/login", json={
        "username": "dg",
        "password": "mauvais_mdp",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_avec_token(client, headers_agent):
    """GET /me avec token valide → infos utilisateur."""
    resp = await client.get("/api/v1/auth/me", headers=headers_agent)
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "role" in data
    assert "permissions" in data


@pytest.mark.asyncio
async def test_me_sans_token(client):
    """GET /me sans token → 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_route_protegee_sans_token(client):
    """Accès route sinistres sans token → 401."""
    resp = await client.get("/api/v1/sinistres/SIN-2025-00001")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_acces_refuse_mauvais_role(client, headers_agent):
    """Agent sans permission cima → 403."""
    resp = await client.post(
        "/api/v1/cima/question",
        json={"question": "Qu'est-ce que l'Art. 337-1 ?"},
        headers=headers_agent,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_role_dg_acces_audit(client, headers_dg):
    """DG peut accéder à l'audit trail."""
    resp = await client.get("/api/v1/audit/recent", headers=headers_dg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_role_agent_refuse_audit(client, headers_agent):
    """Agent ne peut pas accéder à l'audit trail."""
    resp = await client.get("/api/v1/audit/recent", headers=headers_agent)
    assert resp.status_code == 403
