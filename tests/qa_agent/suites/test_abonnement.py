"""Suite N — Abonnement: plans, packs, débit crédits, recharge."""
from __future__ import annotations

import requests

from ..common import RunContext
from ..suites.test_copilote import _login_api
from .base import make_result


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _get(api, path, token):
    try:
        r = requests.get(api + path, headers=_hdr(token), timeout=20)
        return r.status_code, r.json() if r.status_code == 200 else r.text
    except Exception as e:
        return 0, str(e)


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    token = _login_api(api, ctx.cfg["credentials"]["email"], ctx.cfg["credentials"]["password"])
    if not token:
        return make_result("Abonnement", "FAIL", 0, defauts=["login API impossible"])

    defauts = []
    score = 9

    # Mon abonnement
    code1, abon = _get(api, "/api/v1/pro/abonnement/", token)
    if code1 != 200:
        defauts.append(f"GET /pro/abonnement/ HTTP {code1}")
        score -= 3
    else:
        for k in ("plan", "credits_restants"):
            if isinstance(abon, dict) and k not in abon:
                defauts.append(f"champ '{k}' manquant dans abonnement")
                score -= 1

    # Plans
    code2, plans_resp = _get(api, "/api/v1/pro/abonnement/plans", token)
    if code2 != 200:
        defauts.append(f"GET /pro/abonnement/plans HTTP {code2}")
        score -= 2
    else:
        plans = plans_resp.get("plans", []) if isinstance(plans_resp, dict) else plans_resp
        if not plans:
            defauts.append("aucun plan disponible")
            score -= 1
        elif isinstance(plans[0], dict):
            for k in ("nom", "prix_fcfa"):
                if k not in plans[0]:
                    defauts.append(f"plan: champ '{k}' manquant")

    # Packs crédits
    code3, packs_resp = _get(api, "/api/v1/pro/abonnement/packs-credits", token)
    if code3 != 200:
        defauts.append(f"GET /pro/abonnement/packs-credits HTTP {code3}")
        score -= 1
    packs = (packs_resp.get("packs", []) if isinstance(packs_resp, dict) else []) if code3 == 200 else []

    # Historique
    code4, hist = _get(api, "/api/v1/pro/abonnement/historique", token)
    if code4 != 200:
        defauts.append(f"GET /pro/abonnement/historique HTTP {code4}")
        score -= 1

    credits_avant = (abon or {}).get("credits_utilises") if isinstance(abon, dict) else None

    # Test initier-recharge (sans paiement)
    pack_id = None
    if packs and isinstance(packs[0], dict):
        pack_id = packs[0].get("id")
    if pack_id:
        try:
            r = requests.post(api + "/api/v1/pro/abonnement/initier-recharge",
                              headers={**_hdr(token), "Content-Type": "application/json"},
                              json={"pack_id": pack_id, "operateur": "mtn_momo",
                                    "numero_telephone": "+237699123456", "pays": "CM"},
                              timeout=30)
            if r.status_code != 200:
                defauts.append(f"initier-recharge HTTP {r.status_code}: {r.text[:150]}")
                score -= 1
            else:
                d = r.json()
                ref = d.get("reference_paiement") or d.get("reference") or d.get("ref")
                if not ref:
                    defauts.append(f"réponse recharge sans référence: {list(d.keys())}")
                    score -= 1
        except Exception as e:
            defauts.append(f"initier-recharge exception: {e}")
            score -= 1

        # Vérifier que le solde n'a pas bougé sans confirmation
        code5, abon2 = _get(api, "/api/v1/pro/abonnement/", token)
        if code5 == 200 and isinstance(abon2, dict) and credits_avant is not None:
            credits_apres = abon2.get("credits_utilises")
            if credits_apres is not None and credits_apres < credits_avant:
                defauts.append("solde débité sans confirmation paiement (faille sécurité)")
                score -= 5
    else:
        defauts.append("aucun pack disponible pour tester initier-recharge")

    score = max(0, score)
    status = "PASS" if score >= 7 else "PARTIAL" if score >= 5 else "FAIL"
    return make_result("Abonnement (plans+packs+recharge)", status, score,
                       defauts=defauts,
                       note_text=f"plan={abon.get('plan') if isinstance(abon,dict) else '?'}, "
                                 f"credits={abon.get('credits_restants') if isinstance(abon,dict) else '?'}")
