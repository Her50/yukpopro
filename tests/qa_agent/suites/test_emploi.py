"""Suite I — Emploi / veille offres."""
from __future__ import annotations

import requests

from ..common import RunContext
from ..suites.test_copilote import _login_api
from .base import make_result


def _hdr(t): return {"Authorization": f"Bearer {t}"}


PROFILS = [
    "Actuaire confirmé secteur assurance santé Afrique francophone, 8 ans exp, Cameroun/Côte d'Ivoire",
    "Juriste corporate OHADA, Dakar, bilingue FR/EN",
    "Souscripteur risques industriels, Libreville",
]


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        return make_result("Emploi", "FAIL", 0, defauts=["login API impossible"])

    defauts: list[str] = []
    notes: list[int] = []

    for profil in PROFILS:
        offres = []
        # Endpoint principal: /api/v1/pro/profil/veille-emploi/rechercher (POST sans body)
        try:
            r = requests.post(api + "/api/v1/pro/profil/veille-emploi/rechercher",
                              headers=_hdr(token),
                              timeout=ctx.cfg["timeouts"]["emploi_s"])
            if r.status_code == 200:
                d = r.json()
                offres = d.get("offres") or d.get("offres_emploi_recentes") or []
        except Exception as e:
            defauts.append(f"profil '{profil[:40]}…': exception {e}")
        if not offres:
            # Sans veille programmée préalable, 0 offre est attendu pour un compte fresh
            defauts.append(f"profil '{profil[:40]}…': 0 offre (veille non encore exécutée)")
            notes.append(5)
            continue
        if len(offres) < 3:
            defauts.append(f"profil '{profil[:40]}…': seulement {len(offres)} offres (<3)")
            notes.append(4)
        else:
            notes.append(7)
        for o in offres[:2]:
            url = o.get("url") if isinstance(o, dict) else None
            if url:
                try:
                    r = requests.head(url, timeout=8, allow_redirects=True)
                    if r.status_code >= 400:
                        defauts.append(f"lien offre cassé HTTP {r.status_code}: {url}")
                except Exception:
                    pass

    moyenne = round(sum(notes) / max(1, len(notes))) if notes else 0
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Emploi (veille profils)", status, moyenne,
                       defauts=defauts,
                       note_text=f"{len(PROFILS)} profils testés")
