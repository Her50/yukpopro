"""
Traducteur NLLB-200 (Meta) via Hugging Face Inference API.

NLLB-200 couvre 200 langues incluant les langues africaines peu supportées
par GPT-4o-mini : wolof (wol_Latn), yoruba (yor_Latn), hausa (hau_Latn),
swahili (swh_Latn), lingala (lin_Latn), douala (dua_Latn)…

Utilisé en fallback par `translator.traduire_texte` quand la langue source
ou cible est une langue africaine prioritaire.

Coût : ~0.06 USD / 1M caractères (HF Inference API) — quasi gratuit en pratique.
"""
from __future__ import annotations

import logging
import asyncio
from typing import Optional

import httpx

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.translate_live.nllb")

# Mapping ISO 639-1 → code Flores-200 utilisé par NLLB
FLORES_MAP: dict[str, str] = {
    "fr": "fra_Latn",
    "en": "eng_Latn",
    "es": "spa_Latn",
    "pt": "por_Latn",
    "ar": "arb_Arab",
    "de": "deu_Latn",
    "it": "ita_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
    "ru": "rus_Cyrl",
    "hi": "hin_Deva",
    "tr": "tur_Latn",
    # Afrique sub-saharienne
    "sw":  "swh_Latn",  # Swahili (Kiswahili)
    "ha":  "hau_Latn",  # Hausa
    "yo":  "yor_Latn",  # Yoruba
    "wo":  "wol_Latn",  # Wolof
    "ln":  "lin_Latn",  # Lingala
    "dua": "dua_Latn",  # Douala
    "ig":  "ibo_Latn",  # Igbo
    "zu":  "zul_Latn",  # Zulu
    "xh":  "xho_Latn",  # Xhosa
    "am":  "amh_Ethi",  # Amharic
}

# Langues pour lesquelles NLLB est prioritaire (GPT-4o-mini peu fiable)
LANGUES_NLLB_PRIORITAIRE = {"wo", "yo", "ha", "ln", "dua", "ig", "zu", "xh"}

# Modèle distillé (600M) — bon compromis qualité/latence
NLLB_MODEL = "facebook/nllb-200-distilled-600M"


def _hf_endpoint() -> str:
    return f"https://api-inference.huggingface.co/models/{NLLB_MODEL}"


def nllb_disponible() -> bool:
    """True si le token HF est configuré ET la langue fait partie du mapping."""
    return bool(getattr(settings, "HUGGINGFACE_TOKEN", None))


def doit_utiliser_nllb(source_lang: str, target_lang: str) -> bool:
    """
    Retourne True si l'une des deux langues est dans la liste NLLB prioritaire
    ET NLLB est disponible (token configuré).
    """
    if not nllb_disponible():
        return False
    return source_lang in LANGUES_NLLB_PRIORITAIRE or target_lang in LANGUES_NLLB_PRIORITAIRE


async def traduire_nllb(
    texte: str,
    *,
    source_lang: str,
    target_lang: str,
    timeout: float = 20.0,
) -> Optional[str]:
    """
    Traduit via Hugging Face Inference API (NLLB-200).
    Retourne la traduction ou None en cas d'échec (le caller fera fallback GPT).

    Gère le cold start HF (503 "loading" → retry après 3s, max 2 tentatives).
    """
    token = getattr(settings, "HUGGINGFACE_TOKEN", None)
    if not token:
        return None

    src_code = FLORES_MAP.get(source_lang)
    tgt_code = FLORES_MAP.get(target_lang)
    if not src_code or not tgt_code:
        logger.debug(f"[NLLB] codes non mappés src={source_lang} tgt={target_lang}")
        return None

    payload = {
        "inputs": texte,
        "parameters": {
            "src_lang": src_code,
            "tgt_lang": tgt_code,
            "max_length": 512,
        },
        "options": {"wait_for_model": True},
    }
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        for tentative in range(2):
            try:
                resp = await client.post(_hf_endpoint(), json=payload, headers=headers)
                if resp.status_code == 503:
                    # Modèle en cold-start → attendre
                    logger.info("[NLLB] cold-start HF, retry dans 3s")
                    await asyncio.sleep(3.0)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and data:
                    return (data[0].get("translation_text") or "").strip()
                if isinstance(data, dict) and "translation_text" in data:
                    return (data["translation_text"] or "").strip()
                logger.warning(f"[NLLB] réponse inattendue: {data}")
                return None
            except httpx.HTTPStatusError as e:
                logger.warning(f"[NLLB] HTTP {e.response.status_code}: {e.response.text[:200]}")
                return None
            except Exception as e:
                logger.warning(f"[NLLB] erreur: {e}")
                return None
    return None
