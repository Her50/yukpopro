"""Tests du service de notifications."""
import pytest


@pytest.mark.asyncio
async def test_envoyer_whatsapp_mode_simulation():
    """En mode simulation (Twilio non configuré) → succès simulé."""
    from core.notifications import envoyer_whatsapp
    ok = await envoyer_whatsapp(
        destinataire="+225 07 01 01 01 01",
        contenu="Test message de notification",
    )
    assert ok is True


@pytest.mark.asyncio
async def test_envoyer_alerte_churn():
    from core.notifications import envoyer_alerte_churn
    ok = await envoyer_alerte_churn(
        telephone="+226 70 22 22 22",
        nom_assure="Ouédraogo Blaise",
        message_commercial="Nous avons une offre spéciale pour vous.",
        numero_police="AUTO-2023-005541",
    )
    assert ok is True


@pytest.mark.asyncio
async def test_messages_en_echec_initialement_vide():
    from core.notifications import messages_en_echec, _failed
    _failed.clear()
    assert messages_en_echec() == []


@pytest.mark.asyncio
async def test_confirmation_sinistre():
    from core.notifications import envoyer_confirmation_sinistre
    ok = await envoyer_confirmation_sinistre(
        telephone="+237 6 99 11 11 11",
        nom_assure="MBARGA Jean-Paul",
        numero_sinistre="SIN-2025-00001",
        delai_jours=10,
    )
    assert ok is True
