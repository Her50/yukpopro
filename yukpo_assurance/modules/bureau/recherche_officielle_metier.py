"""
Phase 3+ — Recherche web officielle par vertical métier.

Wrapper autour de `modules.pro.recherche_web_pro._serper_search` qui :
  1. Détecte la vertical depuis profil.metier/secteur
  2. Combine les sites officiels globaux du secteur + sites du pays user
  3. Lance Serper.dev sur cette whitelist
  4. Retourne extraits + sources URL pour citation

Si SERPER_API_KEY absent → fallback : signaler que la recherche n'est pas
disponible et que le LLM doit utiliser ses connaissances natives en
marquant explicitement "à vérifier sur source officielle".

Usage typique (depuis un orchestrateur LLM ou un endpoint chat) :
    from modules.bureau.recherche_officielle_metier import (
        chercher_reglementation,
    )
    result = await chercher_reglementation(
        question="Quel est le délai de préavis CDI au Cameroun ?",
        vertical="rh_paie", pays="CM",
    )
    # → {sources_trouvees: [...], extraits: [{url, titre, texte}]}
"""
from __future__ import annotations

import logging
from typing import Optional

from . import verticales_metier as _vm

logger = logging.getLogger("yukpo_assurance.bureau.recherche_officielle_metier")


# ── Sites nationaux par pays (best effort, mondialisé) ──────────────────────
# Le LLM doit aussi inférer dynamiquement, mais on fournit un seed pour les
# pays/régulateurs les plus courants. Pas une cage : extensible.
SITES_NATIONAUX_PAR_PAYS: dict[str, list[str]] = {
    # Afrique francophone
    "CM": ["beac.int", "minfi.gov.cm", "cnps.cm", "minedub.cm",
           "minesec.gov.cm", "minesup.gov.cm"],
    "SN": ["bceao.int", "ipres.sn", "education.gouv.sn"],
    "CI": ["bceao.int", "cnps.ci", "men.gouv.ci"],
    "BJ": ["bceao.int"],
    "BF": ["bceao.int"],
    "TG": ["bceao.int"],
    "ML": ["bceao.int"],
    "NE": ["bceao.int"],
    "GN": ["bceao.int"],
    "GA": ["beac.int"],
    "CG": ["beac.int"],
    "CD": [],
    # Afrique anglophone
    "NG": ["cbn.gov.ng", "sec.gov.ng", "fmoh.gov.ng"],
    "GH": ["bog.gov.gh", "moh.gov.gh"],
    "KE": ["centralbank.go.ke"],
    "ZA": ["resbank.co.za", "fsca.co.za"],
    "EG": ["cbe.org.eg"],
    "MA": ["bkam.ma"],
    # Europe
    "FR": ["legifrance.gouv.fr", "service-public.fr", "ansm.sante.fr",
           "education.gouv.fr", "fnaim.fr"],
    "BE": ["fsma.be", "afmps.be"],
    "DE": ["bafin.de", "bgbl.de"],
    "ES": ["boe.es"],
    "IT": ["bancaditalia.it"],
    "UK": ["fca.org.uk", "bankofengland.co.uk", "mhra.gov.uk",
           "gov.uk"],
    "CH": ["finma.ch", "swissmedic.ch"],
    # Amériques
    "US": ["sec.gov", "federalreserve.gov", "fda.gov", "dol.gov", "ed.gov"],
    "CA": ["bankofcanada.ca", "canada.ca"],
    "BR": ["bcb.gov.br", "anvisa.gov.br"],
    "MX": ["banxico.org.mx", "cofepris.gob.mx"],
    "AR": ["bcra.gob.ar"],
    # Asie / Pacifique
    "IN": ["rbi.org.in", "sebi.gov.in", "cdsco.gov.in"],
    "CN": ["pbc.gov.cn", "nmpa.gov.cn"],
    "JP": ["boj.or.jp", "fsa.go.jp", "pmda.go.jp"],
    "SG": ["mas.gov.sg"],
    "AE": ["centralbank.ae"],
    "AU": ["rba.gov.au", "asic.gov.au"],
}


def sites_pour_recherche(vertical_key: Optional[str], pays: Optional[str] = None) -> list[str]:
    """
    Combine sites officiels globaux du secteur + sites nationaux du pays.
    """
    sites: list[str] = []
    if vertical_key:
        vert = _vm.VERTICALES_METIER.get(vertical_key, {})
        sites.extend(vert.get("sites_officiels_globaux", [])[:10])
    if pays:
        pc = pays.upper()
        sites.extend(SITES_NATIONAUX_PAR_PAYS.get(pc, []))
    # Dédupliquer en gardant l'ordre
    seen = set()
    out: list[str] = []
    for s in sites:
        if s and s not in seen:
            out.append(s); seen.add(s)
    return out


async def chercher_reglementation(
    question: str,
    vertical: Optional[str] = None,
    pays: Optional[str] = None,
    max_extraits: int = 5,
) -> dict:
    """
    Recherche web temps réel sur sites officiels (Serper) pour répondre à une
    question réglementaire/métier. Renvoie {sources_trouvees, extraits, raison_echec}.

    Si SERPER_API_KEY absent → renvoie raison_echec explicite ; le caller doit
    alors signaler au LLM d'utiliser ses connaissances natives en marquant
    "à vérifier sur source officielle".
    """
    try:
        from modules.pro.recherche_web_pro import _serper_search, _telecharger_extrait
    except Exception as e:
        return {
            "sources_trouvees": [],
            "extraits": [],
            "raison_echec": f"Serper indisponible : {e}",
        }
    sites = sites_pour_recherche(vertical, pays)
    if not sites:
        sites = ["bis.org", "ilo.org", "who.int", "ohada.org",
                 "sec.gov", "ifrs.org"]   # fallback global
    pays_gl = (pays or "").lower() or None
    try:
        organic = await _serper_search(question, sites, pays_gl, num=8)
    except Exception as e:
        logger.warning(f"[Recherche officielle] Serper erreur : {e}")
        organic = []
    if not organic:
        return {
            "sources_trouvees": [],
            "extraits": [],
            "raison_echec": "Aucun résultat sur sites officiels — utiliser connaissances LLM avec mention 'à vérifier'",
        }
    extraits: list[dict] = []
    sources_urls: list[str] = []
    for hit in organic[:max_extraits]:
        url = hit.get("link") or ""
        titre = hit.get("title") or ""
        snippet = hit.get("snippet") or ""
        if not url:
            continue
        sources_urls.append(url)
        # Best-effort full extract si court snippet
        texte = snippet
        if len(snippet) < 200:
            try:
                full = await _telecharger_extrait(url, max_chars=2000)
                if full:
                    texte = full
            except Exception:
                pass
        extraits.append({"url": url, "titre": titre, "texte": texte[:2000]})
    return {
        "sources_trouvees": sources_urls,
        "extraits": extraits,
        "raison_echec": None,
    }
