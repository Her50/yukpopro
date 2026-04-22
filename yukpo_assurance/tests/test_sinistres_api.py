"""Tests des routes sinistres via l'API."""
import pytest
from datetime import date


@pytest.mark.asyncio
async def test_declarer_sinistre_requiert_auth(client):
    """Déclaration sans token → 401."""
    resp = await client.post("/api/v1/sinistres/declarer", json={
        "numero_police": "AUTO-2024-001234",
        "date_sinistre": str(date.today()),
        "lieu": "Abidjan",
        "nature": "collision",
        "description": "Test",
        "nom_declarant": "Test",
        "telephone_declarant": "+225 07 01 01 01",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_consulter_sinistre_agent(client, headers_agent):
    """Agent peut consulter un sinistre."""
    resp = await client.get("/api/v1/sinistres/SIN-2025-00001", headers=headers_agent)
    assert resp.status_code == 200
    data = resp.json()
    assert "numero_sinistre" in data or "numero_police" in data


@pytest.mark.asyncio
async def test_sinistres_par_police(client, headers_agent):
    """Liste des sinistres d'une police."""
    resp = await client.get(
        "/api/v1/sinistres/police/AUTO-2024-001234",
        headers=headers_agent,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "sinistres" in data


@pytest.mark.asyncio
async def test_fraude_reseau_requiert_auth(client):
    """Analyse fraude sans token → 401."""
    resp = await client.get("/api/v1/sinistres/fraude/SIN-2025-00001/reseau")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_fraude_reseau_avec_auth(client, headers_agent):
    """Analyse fraude réseau avec token agent."""
    resp = await client.get(
        "/api/v1/sinistres/fraude/SIN-2025-00001/reseau",
        headers=headers_agent,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "reseau_detecte" in data
    assert "score_reseau" in data
    assert 0 <= data["score_reseau"] <= 100
    assert data["recommandation"] in ("bloquer", "surveiller", "passer")
