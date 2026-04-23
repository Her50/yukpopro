"""
YukpoTranslate Live — Module de traduction vocale temps réel.

Pipeline :
  Client (PWA/mobile) → WS backend → Deepgram STT streaming
    → GPT-4o-mini traduction → push sous-titres bilingues → client.

Composants publics :
  - TranslateLiveSession : orchestrateur par connexion WS
  - DeepgramStreamingClient : wrapper STT streaming
  - traduire_texte : helper traduction simple (via ia_client)
  - LANGUES_SUPPORTEES : référentiel ISO 639-1
  - tarif_credits_par_minute : constante utilisée pour le débit crédits
"""
from modules.translate_live.languages import LANGUES_SUPPORTEES, normaliser_code_langue
from modules.translate_live.translator import traduire_texte
from modules.translate_live.session import TranslateLiveSession, CREDITS_PAR_MINUTE, COUT_FCFA_PAR_MINUTE
from modules.translate_live.deepgram_client import DeepgramStreamingClient, deepgram_disponible

__all__ = [
    "TranslateLiveSession",
    "DeepgramStreamingClient",
    "deepgram_disponible",
    "traduire_texte",
    "LANGUES_SUPPORTEES",
    "normaliser_code_langue",
    "CREDITS_PAR_MINUTE",
    "COUT_FCFA_PAR_MINUTE",
]
