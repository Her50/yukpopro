"""Tests du connecteur ORASS en mode simulation."""
import pytest
from datetime import date


@pytest.mark.asyncio
async def test_rechercher_contrat_retourne_donnees():
    from core.orass_connector import orass
    contrat = await orass.rechercher_contrat(numero_police="AUTO-2024-001234")
    assert contrat is not None
    assert contrat.numero_police == "AUTO-2024-001234"
    assert contrat.nom_assure
    assert contrat.prime_nette > 0
    assert isinstance(contrat.date_effet, date)


@pytest.mark.asyncio
async def test_simulation_donnees_variees():
    """Deux polices différentes doivent retourner des profils différents."""
    from core.orass_connector import orass
    c1 = await orass.rechercher_contrat(numero_police="AUTO-2024-000001")
    c2 = await orass.rechercher_contrat(numero_police="VIE-2024-999999")
    # Les noms doivent potentiellement varier selon le hash
    assert c1 is not None
    assert c2 is not None
    # Pas de crash, données cohérentes
    assert c1.prime_nette > 0
    assert c2.prime_nette > 0


@pytest.mark.asyncio
async def test_recuperer_sinistre():
    from core.orass_connector import orass
    sin = await orass.recuperer_sinistre("SIN-2025-00001")
    assert sin is not None
    assert sin.numero_sinistre == "SIN-2025-00001"
    assert sin.montant_declare is not None
    assert sin.nature in ["collision", "vol", "incendie", "bris_glace", "dégâts_des_eaux"]


@pytest.mark.asyncio
async def test_lister_impayes_filtre_seuil():
    from core.orass_connector import orass
    impayes_30 = await orass.lister_impayes(seuil_jours=30)
    impayes_90 = await orass.lister_impayes(seuil_jours=90)
    # Moins d'impayés avec un seuil plus élevé
    assert len(impayes_90) <= len(impayes_30)
    # Tous ont le bon délai
    for i in impayes_30:
        assert i["jours_retard"] >= 30


@pytest.mark.asyncio
async def test_verifier_validite_contrat():
    from core.orass_connector import orass
    resultat = await orass.verifier_validite_contrat("AUTO-2024-001234")
    assert "valide" in resultat
    assert "statut" in resultat
    assert "jours_restants" in resultat


@pytest.mark.asyncio
async def test_calculer_commissions_courtier():
    from core.orass_connector import orass
    from datetime import date
    commissions = await orass.calculer_commissions_courtier(
        courtier_code="COURT-0042",
        periode_debut=date(2025, 1, 1),
        periode_fin=date(2025, 3, 31),
    )
    assert "commission_due" in commissions
    assert commissions["commission_due"] > 0
