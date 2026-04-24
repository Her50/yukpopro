"""
Traduction texte → texte via le `ia_client` existant (GPT-4o-mini en priorité via
ModeIA.COPILOTE, faible coût, latence < 1s pour phrases courtes).

Utilisé par `TranslateLiveSession` sur chaque utterance finale.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.ia_client import ia_client, ModeIA, ModelePrioritaire
from modules.translate_live.languages import nom_humain, normaliser_code_langue
try:
    from modules.translate_live.nllb_translator import (
        doit_utiliser_nllb,
        traduire_nllb,
    )
except ImportError:
    def doit_utiliser_nllb(source_lang: str, target_lang: str) -> bool:  # type: ignore[misc]
        return False

    async def traduire_nllb(texte: str, *, source_lang: str, target_lang: str, timeout: float = 20.0):  # type: ignore[misc]
        return None

logger = logging.getLogger("yukpo_assurance.translate_live.translator")

_SYSTEME = (
    "Tu es un traducteur professionnel spécialisé en interprétation simultanée. "
    "Tu traduis fidèlement, sans commentaire, sans préfixe, sans guillemets. "
    "Tu préserves les noms propres, les chiffres et le ton (formel / familier). "
    "Si le texte source est déjà dans la langue cible, renvoie-le inchangé."
)


async def traduire_texte(
    texte: str,
    *,
    source_lang: Optional[str] = None,
    target_lang: str,
) -> str:
    """
    Traduit `texte` vers `target_lang` (code ISO 639-1).
    Si `source_lang == target_lang` (après normalisation), retourne le texte tel quel
    sans appel IA (économie crédits).

    Retourne une chaîne vide si `texte` est vide ou ne contient que des espaces.
    Ne lève jamais — en cas d'erreur IA, retourne le texte original en fallback.
    """
    src = normaliser_code_langue(source_lang, defaut="auto")
    tgt = normaliser_code_langue(target_lang, defaut="en")
    corps = (texte or "").strip()
    if not corps:
        return ""
    if src != "auto" and src == tgt:
        return corps

    # Langues africaines → NLLB-200 prioritaire si disponible (qualité supérieure
    # à GPT-4o-mini pour wolof, yoruba, hausa, lingala, douala…)
    if src != "auto" and doit_utiliser_nllb(src, tgt):
        trad = await traduire_nllb(corps, source_lang=src, target_lang=tgt)
        if trad:
            return trad
        logger.info(f"[Translator] NLLB échoué, fallback GPT pour {src}→{tgt}")

    prompt = (
        f"Traduis en {nom_humain(tgt)} le texte suivant. "
        f"Ne renvoie QUE la traduction, sans guillemets ni commentaire.\n\n"
        f"Texte à traduire :\n{corps}"
    )

    try:
        reponse = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.COPILOTE,
            systeme=_SYSTEME,
            # Privilégier GPT-4o-mini (bon marché + rapide pour traduction courte)
            forcer_modele=ModelePrioritaire.GPT4O,
            utiliser_cache=True,
            cache_ttl=86400,  # même phrase traduite plusieurs fois = cache 24h
        )
        texte_trad = (reponse.contenu or "").strip()
        # Nettoyage : guillemets ou préfixes type "Translation: ..."
        if texte_trad.startswith(('"', "«")) and texte_trad.endswith(('"', "»")):
            texte_trad = texte_trad[1:-1].strip()
        if ":" in texte_trad[:30]:
            prefix = texte_trad.split(":", 1)[0].lower()
            if any(p in prefix for p in ("translation", "traduction", "trad")):
                texte_trad = texte_trad.split(":", 1)[1].strip()
        return texte_trad or corps
    except Exception as e:
        logger.warning(f"[Translator] Fallback texte source — erreur IA : {e}")
        return corps
