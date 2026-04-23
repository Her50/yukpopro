"""Suite J — Marchés publics."""
from __future__ import annotations

from datetime import datetime

import requests

from ..common import RunContext
from ..suites.test_copilote import _login_api
from .base import make_result


def _hdr(t): return {"Authorization": f"Bearer {t}"}


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        return make_result("Marchés publics", "FAIL", 0, defauts=["login API impossible"])

    defauts: list[str] = []
    marches = []
    for path in ("/api/v1/pro/marches/rechercher", "/api/v1/pro/marches",
                 "/api/v1/pro/agents/marches"):
        try:
            r = requests.get(api + path, headers=_hdr(token), timeout=60)
            if r.status_code == 200:
                d = r.json()
                marches = d if isinstance(d, list) else (d.get("results") or d.get("items") or [])
                if marches:
                    break
        except Exception:
            continue

    if not marches:
        return make_result("Marchés publics", "FAIL", 0,
                           defauts=["aucun endpoint marchés public répondant"])

    if len(marches) < 2:
        defauts.append(f"trop peu de résultats: {len(marches)} (<2)")

    expirees = 0
    sans_url = 0
    sans_pays = 0
    today = datetime.utcnow().date()
    for m in marches[:10]:
        if not isinstance(m, dict):
            continue
        date_lim = m.get("date_limite") or m.get("deadline") or m.get("date_depot")
        if isinstance(date_lim, str):
            try:
                if datetime.fromisoformat(date_lim[:10]).date() < today:
                    expirees += 1
            except Exception:
                pass
        if not (m.get("url") or m.get("source_url") or m.get("lien")):
            sans_url += 1
        if not (m.get("pays") or m.get("country")):
            sans_pays += 1
    if expirees:
        defauts.append(f"{expirees} marchés expirés en tête de liste")
    if sans_url:
        defauts.append(f"{sans_url} marchés sans URL source")
    if sans_pays:
        defauts.append(f"{sans_pays} marchés sans pays renseigné")

    score = max(0, 9 - 2 * (len(defauts)))
    status = "PASS" if score >= 7 else "PARTIAL" if score >= 5 else "FAIL"
    return make_result("Marchés publics", status, score, defauts=defauts,
                       note_text=f"{len(marches)} marchés trouvés")
