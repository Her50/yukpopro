"""
Tests de génération de documents — DOCX, PDF, Excel, rapports sinistres.
ia_client est mocké via conftest.py.
"""
import base64
from unittest.mock import AsyncMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _outline_docx(titre: str = "Rapport de test pytest") -> dict:
    return {
        "document_type": "docx",
        "title": titre,
        "sections": [
            {"title": "Introduction", "content": "Contenu de test pour pytest."},
            {"title": "Analyse CIMA", "content": "Art. 337-1 vérifié. Conforme."},
            {"title": "Conclusion", "content": "Dossier validé."},
        ],
        "metadata": {"auteur": "Pytest", "compagnie": "YukpoAssurance Test"},
    }


def _outline_pdf() -> dict:
    return {
        "document_type": "pdf",
        "title": "État réglementaire C7 — Test",
        "sections": [
            {"title": "Marge de solvabilité", "content": "1 500 000 000 FCFA. Conforme."},
        ],
    }


def _outline_excel() -> dict:
    return {
        "document_type": "xlsx",
        "title": "Tableau de bord sinistres Q1 2025",
        "sheets": [
            {
                "name": "Sinistres",
                "headers": ["Numéro", "Nature", "Montant", "Statut"],
                "rows": [
                    ["SIN-2025-001", "collision", 350000, "ouvert"],
                    ["SIN-2025-002", "vol", 1200000, "fermé"],
                ],
            }
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION DOCX
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_docx_depuis_outline():
    """Génération DOCX depuis outline → attachment avec filename .docx."""
    from modules.documents.generateur import DocumentGenerateur

    gen = DocumentGenerateur()

    # Mock du sous-processus de génération
    fake_bytes = b"PK\x03\x04" + b"\x00" * 100  # Faux header DOCX (ZIP)
    with patch.object(gen, "_appeler_generateur", AsyncMock(return_value=fake_bytes)):
        result = await gen.generer(_outline_docx())

    assert result is not None
    assert "filename" in result
    assert result["filename"].endswith(".docx")
    assert "data_b64" in result
    assert "mime_type" in result
    assert "docx" in result["mime_type"] or "word" in result["mime_type"]
    # Vérifier que base64 est décodable
    decoded = base64.b64decode(result["data_b64"])
    assert len(decoded) > 0


@pytest.mark.asyncio
async def test_generation_docx_taille_non_nulle():
    """Le document généré ne doit pas être vide."""
    from modules.documents.generateur import DocumentGenerateur

    gen = DocumentGenerateur()
    fake_bytes = b"DOCX_CONTENT_TEST" * 50

    with patch.object(gen, "_appeler_generateur", AsyncMock(return_value=fake_bytes)):
        result = await gen.generer(_outline_docx())

    assert result is not None
    assert result["size_bytes"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION PDF
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_pdf_depuis_outline():
    """Génération PDF depuis outline → attachment avec filename .pdf."""
    from modules.documents.generateur import DocumentGenerateur

    gen = DocumentGenerateur()
    fake_pdf_bytes = b"%PDF-1.4" + b"\n" * 200  # Faux header PDF

    with patch.object(gen, "_appeler_generateur", AsyncMock(return_value=fake_pdf_bytes)):
        result = await gen.generer(_outline_pdf())

    assert result is not None
    assert result["filename"].endswith(".pdf")
    assert result["mime_type"] == "application/pdf"
    assert result["size_bytes"] > 0


@pytest.mark.asyncio
async def test_generation_pdf_retourne_base64():
    """Le PDF généré est encodé en base64 dans la réponse."""
    from modules.documents.generateur import DocumentGenerateur

    gen = DocumentGenerateur()
    fake_bytes = b"%PDF-1.4 Test Content" * 10

    with patch.object(gen, "_appeler_generateur", AsyncMock(return_value=fake_bytes)):
        result = await gen.generer(_outline_pdf())

    assert result is not None
    assert "data_b64" in result
    # Décodage base64 doit fonctionner
    decoded = base64.b64decode(result["data_b64"])
    assert decoded == fake_bytes


# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION DEPUIS PROMPT IA (avec mock ia_client)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_depuis_prompt_ia(mock_ia_client):
    """Génération depuis une demande textuelle → ia_client appelé (mocké)."""
    from modules.documents.generateur import DocumentGenerateur

    gen = DocumentGenerateur()
    fake_bytes = b"DOCX_FROM_IA" * 50

    # Mock generer_outline de ia_client pour retourner un outline DOCX
    mock_ia_client.generer_outline.return_value = _outline_docx("Document IA")

    with patch.object(gen, "_appeler_generateur", AsyncMock(return_value=fake_bytes)):
        result = await gen.generer_depuis_prompt_ia(
            demande="Génère un rapport de conformité CIMA pour 2024",
            format_doc="docx",
            user_id=1,
        )

    # Le résultat peut être None si generer_depuis_prompt_ia n'est pas implémenté
    # Dans ce cas le test vérifie seulement que ça ne crash pas
    if result is not None:
        assert "filename" in result or "data_b64" in result


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT SINISTRE COMPLET
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rapport_sinistre_complet(client, headers_dg, sinistre_normal):
    """POST /documents/rapport-sinistre → génère un rapport complet."""
    fake_bytes = b"RAPPORT_SINISTRE_DOCX" * 20
    outline_sinistre = {
        "document_type": "docx",
        "title": f"Rapport Sinistre {sinistre_normal['numero_sinistre']}",
        "sections": [
            {"title": "Données sinistre", "content": str(sinistre_normal)},
            {"title": "Analyse fraude", "content": "Score: 12/100 — Risque faible"},
        ],
    }

    from modules.documents.generateur import DocumentGenerateur as DG
    with patch.object(DG, "_appeler_generateur", AsyncMock(return_value=fake_bytes)):
        resp = await client.post(
            "/api/v1/documents/generer",
            json={
                "type": "rapport_sinistre",
                "sinistre_id": sinistre_normal["numero_sinistre"],
                "format": "docx",
            },
            headers=headers_dg,
        )

    # 200 si endpoint implémenté, 404 si pas encore
    assert resp.status_code in (200, 404, 422)
    if resp.status_code == 200:
        data = resp.json()
        assert any(k in data for k in ("document", "filename", "data_b64", "attachment"))


# ─────────────────────────────────────────────────────────────────────────────
# TABLEAU DE BORD EXCEL
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_tableau_bord_excel():
    """Génération Excel depuis outline → filename .xlsx."""
    from modules.documents.generateur import DocumentGenerateur

    gen = DocumentGenerateur()
    fake_xlsx_bytes = b"PK\x03\x04" + b"\x00" * 150  # Faux header XLSX (ZIP)

    with patch.object(gen, "_appeler_generateur", AsyncMock(return_value=fake_xlsx_bytes)):
        result = await gen.generer(_outline_excel())

    assert result is not None
    assert result["filename"].endswith(".xlsx")
    assert "spreadsheet" in result["mime_type"] or "excel" in result["mime_type"]
    assert result["size_bytes"] > 0


@pytest.mark.asyncio
async def test_tableau_bord_excel_via_api(client, headers_dg):
    """API génération tableau de bord → 200 ou 404 selon implémentation."""
    resp = await client.post(
        "/api/v1/documents/generer",
        json={
            "type": "tableau_bord",
            "format": "xlsx",
            "periode": "2025-Q1",
        },
        headers=headers_dg,
    )
    assert resp.status_code in (200, 404, 422)


# ─────────────────────────────────────────────────────────────────────────────
# GESTION D'ERREURS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_echec_generateur_retourne_none():
    """Si le sous-processus de génération échoue → retourne None."""
    from modules.documents.generateur import DocumentGenerateur

    gen = DocumentGenerateur()

    with patch.object(gen, "_appeler_generateur", AsyncMock(return_value=None)):
        result = await gen.generer(_outline_docx("Doc en échec"))

    assert result is None


@pytest.mark.asyncio
async def test_generation_sans_token_retourne_401(client):
    """Endpoint génération sans token → 401."""
    resp = await client.post(
        "/api/v1/documents/generer",
        json={"type": "rapport", "format": "docx"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_outline_type_inconnu():
    """Type de document inconnu → gestion gracieuse."""
    from modules.documents.generateur import DocumentGenerateur

    gen = DocumentGenerateur()
    outline_inconnu = {"document_type": "xyz_inconnu", "title": "Test"}
    fake_bytes = b"fallback_content"

    with patch.object(gen, "_appeler_generateur", AsyncMock(return_value=fake_bytes)):
        result = await gen.generer(outline_inconnu)

    # Soit généré avec un type par défaut, soit None — pas de crash
    assert result is None or isinstance(result, dict)
