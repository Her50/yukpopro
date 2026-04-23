"""Suite N — Abonnement: plans, packs, débit crédits, recharge sans paiement."""
from __future__ import annotations

import requests

from ..common import RunContext
from ..suites.test_copilote import _login_api
from .base import make_result


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _get(api, path, token):
    try:
        r = requests.get(api + path, headers=_hdr(token), timeout=20)
        return r.status_code, (r.json() if r.status_code == 200 else r.text)
    except Exception as e:
        return 0, str(e)


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        return make_result("Abonnement", "FAIL", 0, defauts=["login API impossible"])

    defauts: list[str] = []
    score = 9

    code1, abon = _get(api, "/api/v1/pro/abonnement/", token)
    if code1 != 200:
        defauts.append(f"GET /pro/abonnement/ HTTP {code1}")
        score -= 3
    else:
        for k in ("plan", "credits_restants", "credits_utilises"):
            if isinstance(abon, dict) and k not in abon:
                defauts.append(f"champ '{k}' manquant dans abonnement")
                score -= 1

    code2, plans = _get(api, "/api/v1/pro/abonnement/plans", token)
    if code2 != 200:
        defauts.append(f"GET /pro/abonnement/plans HTTP {code2}")
        score -= 2
    else:
        if isinstance(plans, list) and plans:
            sample = plans[0] if isinstance(plans[0], dict) else {}
            for k in ("nom", "prix_fcfa"):
                if k not in sample:
                    defauts.append(f"plan: champ '{k}' manquant")
                    score -= 1

    code3, packs = _get(api, "/api/v1/pro/abonnement/packs-credits", token)
    if code3 != 200:
        defauts.append(f"GET /pro/abonnement/packs-credits HTTP {code3}")
        score -= 1

    code4, _hist = _get(api, "/api/v1/pro/abonnement/historique", token)
    if code4 != 200:
        defauts.append(f"GET /pro/abonnement/historique HTTP {code4}")
        score -= 1

    credits_avant = (abon or {}).get("credits_utilises") if isinstance(abon, dict) else None

    pack_id = None
    if isinstance(packs, list) and packs and isinstance(packs[0], dict):
        pack_id = packs[0].get("id")
    if pack_id:
        try:
            r = requests.post(api + "/api/v1/pro/abonnement/initier-recharge",
                              headers={**_hdr(token), "Content-Type": "application/json"},
                              json={"pack_id": pack_id, "operateur": "mtn_money",
                                    "numero_telephone": "+237699123456", "pays": "CM"},
                              timeout=30)
            if r.status_code != 200:
                defauts.append(f"initier-recharge HTTP {r.status_code}")
                score -= 1
            else:
                d = r.json()
                if "reference_paiement" not in d and "reference" not in d:
                    defauts.append("réponse recharge sans référence_paiement")
                    score -= 1
        except Exception as e:
            defauts.append(f"initier-recharge échec: {e}")
            score -= 1
    else:
        defauts.append("aucun pack disponible pour tester recharge")

    code5, abon2 = _get(api, "/api/v1/pro/abonnement/", token)
    if code5 == 200 and isinstance(abon2, dict) and credits_avant is not None:
        credits_apres = abon2.get("credits_utilises")
        if credits_apres is not None and credits_apres < credits_avant:
            defauts.append(f"crédits utilisés ont diminué sans confirmation paiement "
                           f"({credits_avant} → {credits_apres})")
            score -= 4

    score = max(0, score)
    status = "PASS" if score >= 7 else "PARTIAL" if score >= 5 else "FAIL"
    return make_result("Abonnement (plans+débit+recharge)", status, score,
                       defauts=defauts,
                       note_text=f"crédits avant={credits_avant}")
