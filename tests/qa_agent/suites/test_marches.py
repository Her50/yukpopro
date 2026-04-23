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
    # Endpoint réel: POST /api/v1/pro/profil/marches/rechercher
    try:
        r = requests.post(api + "/api/v1/pro/profil/marches/rechercher",
                          headers=_hdr(token), timeout=120)
        if r.status_code == 200:
            d = r.json()
            marches = d.get("marches") or d.get("marches_publics_recents") or []
        else:
            defauts.append(f"POST /pro/profil/marches/rechercher HTTP {r.status_code}")
    except Exception as e:
        defauts.append(f"exception marches: {e}")

    if not marches:
        # Pas un FAIL si juste 0 résultat (compte fresh sans veille active)
        return make_result("Marchés publics", "PARTIAL", 5,
                           defauts=defauts + ["0 marché trouvé (compte sans veille active)"],
                           note_text="endpoint OK, dataset vide")

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
