"""Classification des modèles IA en fournisseurs.

Heuristique sur le champ `modele` des tables consommations_*. Permet
d'agréger la consommation par éditeur/API (Anthropic, OpenAI, fal,
Replicate, ElevenLabs, Whisper local…) sans nouvelle colonne DB.

Les patterns sont exhaustifs vis-à-vis des modèles utilisés en prod
au moment du sprint dashboard cross-app (mai 2026). Si un nouveau
modèle apparaît, l'ajouter ici plutôt que de tagger UNKNOWN partout.
"""
from __future__ import annotations

PROVIDERS_KNOWN = (
    "anthropic",   # Claude (Sonnet/Opus/Haiku)
    "openai",      # GPT-4o, GPT-4-turbo, GPT-4o-mini, embeddings, Whisper API
    "fal",         # Flux schnell/dev/pro/ultra, Recraft, Ideogram
    "replicate",   # Brand LoRA training, modèles fine-tunés
    "elevenlabs",  # TTS multilingue
    "azure",       # OCR Azure Document Intelligence
    "local",       # Whisper local, modèles embarqués, forfaits
    "unknown",
)


def classifier_provider(modele: str | None) -> str:
    """Retourne le nom du fournisseur en lowercase parmi PROVIDERS_KNOWN.

    Heuristique basée sur des préfixes/sous-chaînes du nom de modèle.
    Robuste à la casse et aux suffixes de version.
    """
    if not modele:
        return "unknown"
    m = str(modele).lower().strip()

    if "claude" in m or m.startswith("anthropic"):
        return "anthropic"
    if m.startswith("gpt-") or "openai" in m or "text-embedding" in m or m == "whisper-1":
        return "openai"
    if m.startswith(("flux-", "fal-", "recraft", "ideogram")) or "fal.ai" in m or m.startswith("flux/"):
        return "fal"
    if "replicate" in m or m.startswith("rep-") or "lora-training" in m:
        return "replicate"
    if "elevenlabs" in m or m.startswith("eleven-") or m.startswith("tts-eleven"):
        return "elevenlabs"
    if "azure" in m or "form-recognizer" in m or "document-intelligence" in m:
        return "azure"
    if m in {"forfait", "local", "whisper-local", "embedded"}:
        return "local"

    return "unknown"
