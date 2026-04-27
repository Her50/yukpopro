"""
Recherche web factuelle pour les rapports professionnels.

Objectif : remplacer la confiance aveugle au RAG local par une recherche web
réelle sur des sites sérieux (institutions, régulateurs, presse spécialisée),
puis extraction des passages pertinents pour injection dans le prompt LLM.

Si aucune source fiable n'est trouvée, la fonction retourne `(None, raison)` :
le générateur doit alors REFUSER de générer le rapport et demander à
l'utilisateur de fournir lui-même la documentation.

Source utilisée : Serper.dev (Google Search API) — clé `SERPER_API_KEY`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.recherche_web")

_HTTP_TIMEOUT = 18

# Domaines considérés sérieux pour rapports financiers / juridiques / audit
# africains. Whitelist priorité décroissante.
_SITES_SERIEUX_GLOBAUX = [
    # Régulateurs régionaux
    "cima-afrique.org", "ohada.org", "ohada.com",
    "beac.int", "bceao.int", "uemoa.int", "cemac.int",
    # IFI / bailleurs
    "imf.org", "worldbank.org", "afdb.org", "banquemondiale.org",
    "afd.fr", "agenceafd.fr", "ifc.org",
    # Stats officielles & ministères
    "ins-cameroun.cm", "insee.fr", "ansd.sn", "inseed.tg",
    "ins-rdc.cd", "ins.ci", "instat.gov.ml", "insae.bj",
    # Presse économique africaine sérieuse
    "jeuneafrique.com", "agenceecofin.com", "financialafrik.com",
    "lemonde.fr", "rfi.fr", "lesechos.fr",
    # Normes
    "iso.org", "ilo.org", "oit.org", "un.org", "unece.org",
]

_SITES_FINANCE = [
    "cima-afrique.org", "beac.int", "bceao.int",
    "imf.org", "worldbank.org", "afdb.org",
    "agenceecofin.com", "financialafrik.com", "jeuneafrique.com",
]

_SITES_JURIDIQUE = [
    "ohada.org", "ohada.com", "cima-afrique.org",
    "ilo.org", "oit.org", "un.org",
    "legifrance.gouv.fr",
]

_SITES_RH_TRAVAIL = [
    "ilo.org", "oit.org", "uemoa.int", "cemac.int",
    "ins-cameroun.cm", "ansd.sn", "afdb.org",
]

_SITES_PAR_TYPE = {
    "rapport_financier": _SITES_FINANCE,
    "rapport_audit":     _SITES_FINANCE,
    "note_juridique":    _SITES_JURIDIQUE,
    "rapport_rh":        _SITES_RH_TRAVAIL,
}


@dataclass
class ResultatRechercheWeb:
    """Bundle d'extraits web pour injection dans un prompt."""
    contexte_formate: str        # texte prêt à injecter dans le prompt LLM
    nb_sources:       int        # nombre de sources distinctes
    sources_urls:     list[str]  # URLs citées (pour traçabilité utilisateur)
    raison_echec:     Optional[str] = None  # rempli si nb_sources == 0


def _api_key_serper() -> str:
    return os.getenv("SERPER_API_KEY", "").strip()


async def _serper_search(
    query: str, sites: list[str], pays_gl: Optional[str], num: int = 10
) -> list[dict]:
    """Appelle Serper.dev et retourne les résultats organiques bruts."""
    api_key = _api_key_serper()
    if not api_key or api_key.startswith("VOTRE"):
        return []

    site_filter = " OR ".join(f"site:{s}" for s in sites[:8])
    q = f"({query}) ({site_filter})" if sites else query

    try:
        import httpx
        payload: dict = {"q": q, "num": num, "hl": "fr"}
        if pays_gl:
            payload["gl"] = pays_gl.lower()

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                json=payload,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            )
        if resp.status_code != 200:
            logger.warning(f"[RechercheWeb] Serper status={resp.status_code}")
            return []
        return (resp.json() or {}).get("organic", []) or []
    except Exception as e:
        logger.warning(f"[RechercheWeb] Serper erreur: {e}")
        return []


async def _telecharger_extrait(url: str, max_chars: int = 4000) -> str:
    """Télécharge une page et extrait le texte principal (best-effort)."""
    try:
        import httpx
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; YukpoBot/1.0)"},
        ) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return ""
        html = resp.text
        # Strip script/style
        html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        html = re.sub(r"<style[\s\S]*?</style>",  " ", html, flags=re.IGNORECASE)
        # Strip tags
        texte = re.sub(r"<[^>]+>", " ", html)
        texte = re.sub(r"&nbsp;", " ", texte)
        texte = re.sub(r"\s+", " ", texte).strip()
        return texte[:max_chars]
    except Exception:
        return ""


async def rechercher_sources_pour_rapport(
    sujet:          str,
    type_rapport:   str,
    pays_iso2:      Optional[str] = None,
    nb_sources_min: int            = 3,
    timeout_total:  float          = 45.0,
) -> ResultatRechercheWeb:
    """
    Recherche web réelle pour enrichir un rapport.

    Stratégie :
      1. Serper.dev sur sites whitelistés du domaine (CIMA, OHADA, BM, FMI…).
      2. Élargissement à la liste globale si < nb_sources_min trouvées.
      3. Téléchargement parallèle des top résultats (extraits texte).
      4. Si toujours < nb_sources_min après extraction → échec explicite.

    Retour :
      - succès : ResultatRechercheWeb avec contexte_formate non vide,
                 raison_echec=None
      - échec  : nb_sources=0, contexte_formate="", raison_echec="..."
    """
    if not _api_key_serper():
        return ResultatRechercheWeb(
            contexte_formate="",
            nb_sources=0,
            sources_urls=[],
            raison_echec=(
                "La recherche web n'est pas configurée sur ce serveur "
                "(clé SERPER_API_KEY absente)."
            ),
        )

    sujet = (sujet or "").strip()
    if not sujet:
        return ResultatRechercheWeb(
            contexte_formate="",
            nb_sources=0,
            sources_urls=[],
            raison_echec="Sujet vide.",
        )

    sites_cibles = _SITES_PAR_TYPE.get(type_rapport, _SITES_SERIEUX_GLOBAUX)

    try:
        # Pass 1 : domaine ciblé
        organiques = await asyncio.wait_for(
            _serper_search(sujet, sites_cibles, pays_iso2, num=10),
            timeout=12.0,
        )
        # Pass 2 : élargissement si peu de résultats
        if len(organiques) < nb_sources_min:
            extras = await asyncio.wait_for(
                _serper_search(sujet, _SITES_SERIEUX_GLOBAUX, pays_iso2, num=10),
                timeout=12.0,
            )
            vus = {r.get("link", "") for r in organiques}
            for r in extras:
                if r.get("link", "") not in vus:
                    organiques.append(r)

        if not organiques:
            return ResultatRechercheWeb(
                contexte_formate="",
                nb_sources=0,
                sources_urls=[],
                raison_echec=(
                    "Aucun résultat web trouvé sur des sources fiables "
                    f"(régulateurs, IFI, instituts statistiques) pour : « {sujet[:120]} »."
                ),
            )

        # Téléchargement parallèle des extraits (limité à top 6)
        top = organiques[:6]
        extraits = await asyncio.wait_for(
            asyncio.gather(*[_telecharger_extrait(r.get("link", "")) for r in top],
                           return_exceptions=True),
            timeout=timeout_total - 12.0,
        )

        blocs: list[str] = []
        urls: list[str]  = []
        for r, ext in zip(top, extraits):
            url    = r.get("link", "")
            titre  = (r.get("title") or "").strip()
            snip   = (r.get("snippet") or "").strip()
            corps  = ext if isinstance(ext, str) and ext else snip
            if not corps or len(corps) < 60:
                continue
            urls.append(url)
            blocs.append(
                f"#### {titre}\n"
                f"Source : {url}\n"
                f"Extrait : {corps[:2500]}\n"
            )

        if len(urls) < nb_sources_min:
            return ResultatRechercheWeb(
                contexte_formate="",
                nb_sources=len(urls),
                sources_urls=urls,
                raison_echec=(
                    f"Seulement {len(urls)} source(s) exploitable(s) trouvée(s) "
                    f"(minimum requis : {nb_sources_min}). "
                    f"Sujet : « {sujet[:120]} »."
                ),
            )

        contexte = "\n".join(blocs)
        return ResultatRechercheWeb(
            contexte_formate=contexte,
            nb_sources=len(urls),
            sources_urls=urls,
            raison_echec=None,
        )

    except asyncio.TimeoutError:
        return ResultatRechercheWeb(
            contexte_formate="",
            nb_sources=0,
            sources_urls=[],
            raison_echec="Timeout de la recherche web (sites sources lents/indisponibles).",
        )
    except Exception as e:
        logger.exception("[RechercheWeb] Erreur inattendue")
        return ResultatRechercheWeb(
            contexte_formate="",
            nb_sources=0,
            sources_urls=[],
            raison_echec=f"Erreur technique recherche web : {e}",
        )
