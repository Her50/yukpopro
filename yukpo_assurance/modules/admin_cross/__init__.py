"""Admin cross-app — agrégation de consommation IA YukpoPro + YukpoSecrétariat.

Module utilisé par api/routes_admin_cross.py pour :
  - classifier les modèles IA en fournisseurs (Anthropic / OpenAI / fal / Replicate)
  - définir et évaluer les seuils d'alerte (MVP statique)
  - agréger les requêtes sur les deux tables consommations_tokens + consommations_bureau
"""
from .providers import classifier_provider, PROVIDERS_KNOWN
from .alerts import evaluer_alertes, SEUILS_DEFAUT, AlerteSpec

__all__ = [
    "classifier_provider",
    "PROVIDERS_KNOWN",
    "evaluer_alertes",
    "SEUILS_DEFAUT",
    "AlerteSpec",
]
