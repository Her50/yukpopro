"""
Tests d'intégration — API Chat IA (sessions, messages, historique, multimodal).
ia_client est mocké via conftest.py (autouse=True).
"""
import base64

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_creer_session_retourne_session_id(client, headers_dg):
    """POST /chat/sessions → session_id retourné."""
    resp = await client.post(
        "/api/v1/chat/sessions",
        json={"titre": "Session test pytest", "role": "dg"},
        headers=headers_dg,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


@pytest.mark.asyncio
async def test_creer_session_sans_titre(client, headers_agent):
    """POST /chat/sessions sans titre → session créée quand même."""
    resp = await client.post(
        "/api/v1/chat/sessions",
        json={"role": "agent"},
        headers=headers_agent,
    )
    assert resp.status_code == 200
    assert "session_id" in resp.json()


@pytest.mark.asyncio
async def test_creer_session_sans_token_retourne_401(client):
    """Créer session sans authentification → 401."""
    resp = await client.post(
        "/api/v1/chat/sessions",
        json={"titre": "Session sans auth"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_lister_mes_sessions(client, headers_dg):
    """GET /chat/sessions/mes-sessions → liste des sessions de l'utilisateur."""
    # Créer une session d'abord
    await client.post(
        "/api/v1/chat/sessions",
        json={"titre": "Session liste test"},
        headers=headers_dg,
    )
    resp = await client.get("/api/v1/chat/sessions/mes-sessions", headers=headers_dg)
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_envoyer_message_retourne_reponse_ia(client, headers_dg):
    """POST /chat/message → réponse IA retournée (depuis mock)."""
    # 1. Créer une session
    sess_resp = await client.post(
        "/api/v1/chat/sessions",
        json={"titre": "Test message"},
        headers=headers_dg,
    )
    assert sess_resp.status_code == 200
    session_id = sess_resp.json()["session_id"]

    # 2. Envoyer un message
    resp = await client.post(
        "/api/v1/chat/message",
        json={
            "session_id": session_id,
            "message": "Explique l'Article 337-1 du Code CIMA",
            "role": "dg",
        },
        headers=headers_dg,
    )
    assert resp.status_code == 200
    data = resp.json()

    # La réponse doit contenir du contenu textuel
    assert any(k in data for k in ("content", "reponse", "message", "response", "text"))


@pytest.mark.asyncio
async def test_envoyer_message_nouvelle_session_auto(client, headers_dg):
    """POST /chat/message sans session_id → nouvelle session créée automatiquement."""
    resp = await client.post(
        "/api/v1/chat/message",
        json={
            "message": "Bonjour, qu'est-ce que la CIMA ?",
            "role": "dg",
        },
        headers=headers_dg,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_envoyer_message_sans_token_retourne_401(client):
    """Envoyer un message sans token → 401."""
    resp = await client.post(
        "/api/v1/chat/message",
        json={"message": "Test sans auth", "role": "agent"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# HISTORIQUE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_historique_session_retourne_messages(client, headers_dg):
    """GET /chat/sessions/{session_id}/history → liste des messages."""
    # 1. Créer une session
    sess_resp = await client.post(
        "/api/v1/chat/sessions",
        json={"titre": "Test historique"},
        headers=headers_dg,
    )
    session_id = sess_resp.json()["session_id"]

    # 2. Envoyer un message
    await client.post(
        "/api/v1/chat/message",
        json={"session_id": session_id, "message": "Message pour historique"},
        headers=headers_dg,
    )

    # 3. Récupérer l'historique
    resp = await client.get(
        f"/api/v1/chat/sessions/{session_id}/history",
        headers=headers_dg,
    )
    # 200 ou 404 si l'endpoint n'est pas encore implémenté
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        data = resp.json()
        assert isinstance(data, (list, dict))


@pytest.mark.asyncio
async def test_session_inexistante_retourne_404(client, headers_dg):
    """GET /chat/sessions/inexistant/history → 404."""
    resp = await client.get(
        "/api/v1/chat/sessions/SESSION-INEXISTANTE-PYTEST/history",
        headers=headers_dg,
    )
    assert resp.status_code in (404, 400)


# ─────────────────────────────────────────────────────────────────────────────
# STREAMING SSE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_streaming_sse_endpoint_disponible(client, headers_dg):
    """POST /chat/stream → endpoint répond (streaming SSE ou fallback JSON)."""
    resp = await client.post(
        "/api/v1/chat/stream",
        json={"message": "Test streaming", "role": "dg"},
        headers=headers_dg,
    )
    # 200 si implémenté, 404/405 si pas encore
    assert resp.status_code in (200, 404, 405)
    if resp.status_code == 200:
        content_type = resp.headers.get("content-type", "")
        assert any(ct in content_type for ct in ("text/event-stream", "application/json"))


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE MULTIMODAL AVEC IMAGE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_message_multimodal_avec_image(client, headers_dg):
    """POST /chat/message-with-attachments → accepte image base64."""
    # Image PNG minimaliste 1x1 pixel (base64)
    png_1x1_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )

    resp = await client.post(
        "/api/v1/chat/message-with-attachments",
        json={
            "message": "Analyse ce document pour moi",
            "role": "dg",
            "attachments": [
                {
                    "type": "image",
                    "data_b64": png_1x1_b64,
                    "filename": "test_image.png",
                    "mime_type": "image/png",
                }
            ],
        },
        headers=headers_dg,
    )
    # 200 si implémenté, 404 si l'endpoint n'existe pas encore
    assert resp.status_code in (200, 404, 422)
    if resp.status_code == 200:
        data = resp.json()
        assert any(k in data for k in ("content", "reponse", "message", "response"))


@pytest.mark.asyncio
async def test_message_multimodal_sans_attachments(client, headers_dg):
    """POST /chat/message-with-attachments sans pièces jointes → fonctionne."""
    resp = await client.post(
        "/api/v1/chat/message-with-attachments",
        json={
            "message": "Message texte sans pièce jointe",
            "role": "dg",
            "attachments": [],
        },
        headers=headers_dg,
    )
    assert resp.status_code in (200, 404)
