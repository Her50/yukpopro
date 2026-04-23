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
        for path in ("/api/v1/pro/profil/veille/lancer",
                     "/api/v1/pro/emploi/rechercher",
                     "/api/v1/pro/agents/emploi"):
            try:
                r = requests.post(api + path, headers={**_hdr(token), "Content-Type": "application/json"},
                                  json={"profil": profil, "limite": 5},
                                  timeout=ctx.cfg["timeouts"]["emploi_s"])
                if r.status_code == 200:
                    d = r.json()
                    offres = d.get("offres") or d.get("results") or d.get("items") or []
                    break
            except Exception:
                continue
        if not offres:
            defauts.append(f"profil '{profil[:40]}…': 0 offres ou endpoint indisponible")
            notes.append(0)
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
