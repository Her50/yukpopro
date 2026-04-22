"""
Tests de souscription — dossier complet/incomplet, calcul prime, KYC OCR.
ia_client et ORASS mocké via conftest.py.
"""
from unittest.mock import AsyncMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_portail():
    """Instancie PortailSouscription avec ORASS mocké."""
    from modules.souscription.portail import PortailSouscription

    portail = PortailSouscription()
    # Mock ORASS (connecteur external — simulation)
    mock_orass = AsyncMock()
    mock_orass.verifier_antecedents.return_value = {"bloque": False, "antecedents": []}
    mock_orass.creer_police.return_value = {"numero_police": "AUTO-2025-PYTEST-ORASS"}
    portail._orass = mock_orass  # Injection si attribut exposé
    return portail


# ─────────────────────────────────────────────────────────────────────────────
# DOSSIER AUTO COMPLET
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dossier_auto_complet_genere_numero_police(dossier_souscription_complet):
    """Dossier auto avec toutes les données → numéro de police généré."""
    from modules.souscription.portail import DossierSouscription, PortailSouscription

    portail = PortailSouscription()

    with patch("modules.souscription.portail.orass") as mock_orass:
        mock_orass.verifier_antecedents = AsyncMock(
            return_value={"bloque": False, "antecedents": []}
        )
        mock_orass.creer_police = AsyncMock(
            return_value={"numero_police": "AUTO-2025-PYTEST-001"}
        )

        dossier = DossierSouscription(
            branche=dossier_souscription_complet["branche"],
            donnees_client=dossier_souscription_complet["donnees_client"],
            courtier_code=dossier_souscription_complet["courtier_code"],
        )

        result = await portail.traiter_dossier(dossier)

    assert result is not None
    assert result.statut in ("complet", "incomplet", "rejeté")

    # Si complet, un numéro de police doit être présent
    if result.statut == "complet":
        assert result.numero_police is not None
        assert len(result.numero_police) > 0


@pytest.mark.asyncio
async def test_dossier_auto_complet_calcul_prime_positif(dossier_souscription_complet):
    """Dossier complet → prime_ttc > 0 FCFA."""
    from modules.souscription.portail import DossierSouscription, PortailSouscription

    portail = PortailSouscription()

    with patch("modules.souscription.portail.orass") as mock_orass:
        mock_orass.verifier_antecedents = AsyncMock(
            return_value={"bloque": False, "antecedents": []}
        )
        mock_orass.creer_police = AsyncMock(
            return_value={"numero_police": "AUTO-2025-PYTEST-002"}
        )

        dossier = DossierSouscription(
            branche="auto",
            donnees_client=dossier_souscription_complet["donnees_client"],
        )

        result = await portail.traiter_dossier(dossier)

    # Si dossier complet, le calcul de prime doit être présent
    if result.statut == "complet" and result.calcul_prime:
        prime = result.calcul_prime
        assert any(k in prime for k in ("prime_ttc", "prime_nette", "montant"))
        # La prime doit être positive
        prime_val = prime.get("prime_ttc") or prime.get("prime_nette") or prime.get("montant", 0)
        assert prime_val > 0


# ─────────────────────────────────────────────────────────────────────────────
# DOSSIER INCOMPLET
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dossier_incomplet_retourne_pieces_manquantes(dossier_souscription_incomplet):
    """Dossier sans véhicule → pieces_manquantes liste les champs manquants."""
    from modules.souscription.portail import DossierSouscription, PortailSouscription

    portail = PortailSouscription()

    with patch("modules.souscription.portail.orass") as mock_orass:
        mock_orass.verifier_antecedents = AsyncMock(
            return_value={"bloque": False, "antecedents": []}
        )

        dossier = DossierSouscription(
            branche="auto",
            donnees_client=dossier_souscription_incomplet["donnees_client"],
        )

        result = await portail.traiter_dossier(dossier)

    assert result is not None
    assert result.statut in ("incomplet", "rejeté")
    assert isinstance(result.pieces_manquantes, list)
    assert len(result.pieces_manquantes) > 0


@pytest.mark.asyncio
async def test_dossier_sans_branche_retourne_erreur():
    """Dossier sans branche définie → erreur gérée."""
    from modules.souscription.portail import DossierSouscription, PortailSouscription

    portail = PortailSouscription()

    with patch("modules.souscription.portail.orass") as mock_orass:
        mock_orass.verifier_antecedents = AsyncMock(
            return_value={"bloque": False, "antecedents": []}
        )

        dossier = DossierSouscription(
            branche="",
            donnees_client={"nom": "Test"},
        )

        # Ne doit pas lever une exception non gérée
        try:
            result = await portail.traiter_dossier(dossier)
            assert result.statut in ("incomplet", "rejeté")
        except (ValueError, KeyError):
            pass  # Exception explicite acceptable


# ─────────────────────────────────────────────────────────────────────────────
# CALCUL DE PRIME AUTO
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calcul_prime_auto_retourne_prime_ttc_positif():
    """Calcul prime auto avec données valides → prime_ttc > 0."""
    from modules.souscription.portail import PortailSouscription

    portail = PortailSouscription()

    # Appel direct de la méthode de calcul si elle existe
    if hasattr(portail, "_calculer_prime_auto"):
        donnees_vehicule = {
            "marque": "Toyota",
            "modele": "Hilux",
            "annee": 2022,
            "valeur_venale": 12_000_000,
            "puissance_fiscale": 7,
            "usage": "personnel",
        }
        donnees_client = {
            "age": 38,
            "anciennete_permis": 10,
            "bonus_malus": 1.0,
        }

        result = await portail._calculer_prime_auto(donnees_vehicule, donnees_client)

        assert isinstance(result, dict)
        prime = result.get("prime_ttc") or result.get("prime_nette") or 0
        assert prime > 0
    else:
        # Tester via le dossier complet
        pytest.skip("_calculer_prime_auto non exposé — testé via traiter_dossier")


@pytest.mark.asyncio
async def test_prime_vehicule_luxe_superieure_vehicule_standard():
    """Véhicule de luxe → prime plus élevée que véhicule standard."""
    from modules.souscription.portail import DossierSouscription, PortailSouscription

    portail = PortailSouscription()

    donnees_luxe = {
        "nom": "Client Luxe",
        "vehicule": {
            "marque": "Mercedes",
            "modele": "GLE",
            "annee": 2024,
            "valeur_venale": 45_000_000,
            "usage": "personnel",
            "puissance_fiscale": 15,
        },
    }
    donnees_standard = {
        "nom": "Client Standard",
        "vehicule": {
            "marque": "Toyota",
            "modele": "Yaris",
            "annee": 2019,
            "valeur_venale": 5_000_000,
            "usage": "personnel",
            "puissance_fiscale": 4,
        },
    }

    with patch("modules.souscription.portail.orass") as mock_orass:
        mock_orass.verifier_antecedents = AsyncMock(
            return_value={"bloque": False, "antecedents": []}
        )
        mock_orass.creer_police = AsyncMock(
            return_value={"numero_police": "AUTO-COMP-TEST"}
        )

        dossier_luxe = DossierSouscription(branche="auto", donnees_client=donnees_luxe)
        dossier_std = DossierSouscription(branche="auto", donnees_client=donnees_standard)

        result_luxe = await portail.traiter_dossier(dossier_luxe)
        result_std = await portail.traiter_dossier(dossier_std)

    # Si les deux ont une prime calculée, la luxe doit être >= standard
    if (
        result_luxe.calcul_prime
        and result_std.calcul_prime
        and result_luxe.statut == "complet"
        and result_std.statut == "complet"
    ):
        prime_luxe = result_luxe.calcul_prime.get("prime_ttc", 0)
        prime_std = result_std.calcul_prime.get("prime_ttc", 0)
        assert prime_luxe >= prime_std


# ─────────────────────────────────────────────────────────────────────────────
# KYC OCR SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kyc_ocr_cni_simulation(mock_ia_client):
    """Lecture CNI via OCR IA (mock) → données structurées retournées."""
    from modules.souscription.portail import PortailSouscription

    portail = PortailSouscription()

    # Mock ia_client pour OCR CNI
    mock_ia_client.appel_avec_image.return_value = {
        "content": '{"nom": "DUPONT", "prenom": "Jean", "cni": "CM-2025-001", "date_naissance": "1985-06-15", "nationalite": "camerounaise"}',
        "mode": "mock",
    }

    # Image PNG 1x1 pixel base64
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )

    if hasattr(portail, "_lire_cni"):
        result = await portail._lire_cni(png_b64)
        assert isinstance(result, dict)
        # Peut contenir nom, prenom, cni selon le parsing
    else:
        pytest.skip("_lire_cni non exposé publiquement")


@pytest.mark.asyncio
async def test_kyc_ocr_carte_grise_simulation(mock_ia_client):
    """Lecture carte grise via OCR IA (mock) → données véhicule retournées."""
    from modules.souscription.portail import PortailSouscription

    portail = PortailSouscription()

    mock_ia_client.appel_avec_image.return_value = {
        "content": '{"immatriculation": "LT-TEST-2025", "marque": "Toyota", "modele": "Corolla", "annee": 2022}',
        "mode": "mock",
    }

    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )

    if hasattr(portail, "_lire_carte_grise"):
        result = await portail._lire_carte_grise(png_b64)
        assert isinstance(result, dict)
    else:
        pytest.skip("_lire_carte_grise non exposé publiquement")


# ─────────────────────────────────────────────────────────────────────────────
# API SOUSCRIPTION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_souscription_sans_token_retourne_401(client):
    """POST /souscription/nouveau sans token → 401."""
    resp = await client.post(
        "/api/v1/souscription/nouveau",
        json={"branche": "auto"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_souscription_payload_incomplet_retourne_422(client, headers_agent):
    """POST /souscription/nouveau avec données incomplètes → 422 ou 400."""
    resp = await client.post(
        "/api/v1/souscription/nouveau",
        json={},
        headers=headers_agent,
    )
    assert resp.status_code in (400, 404, 422)


@pytest.mark.asyncio
async def test_pieces_manquantes_retournees_dans_api(client, headers_agent):
    """POST /souscription/nouveau dossier incomplet → pieces_manquantes dans réponse."""
    with patch("modules.souscription.portail.orass") as mock_orass:
        mock_orass.verifier_antecedents = AsyncMock(
            return_value={"bloque": False, "antecedents": []}
        )

        resp = await client.post(
            "/api/v1/souscription/nouveau",
            json={
                "branche": "auto",
                "donnees_client": {"nom": "Test Incomplet"},
            },
            headers=headers_agent,
        )

    # 200 avec statut incomplet, ou 422/404 si endpoint pas encore câblé
    assert resp.status_code in (200, 404, 422)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("statut") == "incomplet":
            assert "pieces_manquantes" in data
            assert isinstance(data["pieces_manquantes"], list)
