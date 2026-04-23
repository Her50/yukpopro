"""Suite M — Mes Documents (listing, types, persistance)."""
from __future__ import annotations

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
        return make_result("Mes Documents", "FAIL", 0, defauts=["login API impossible"])

    defauts: list[str] = []
    docs = []
    for path in ("/api/v1/bureau/documents/lister",
                 "/api/v1/pro/documents",
                 "/api/v1/pro/documents/lister"):
        try:
            r = requests.get(api + path, headers=_hdr(token), timeout=20)
            if r.status_code == 200:
                d = r.json()
                docs = d if isinstance(d, list) else (d.get("documents") or d.get("items") or [])
                if docs:
                    break
        except Exception:
            continue

    if not docs:
        return make_result("Mes Documents", "FAIL", 0,
                           defauts=["aucun endpoint listing documents répondant"])

    types_distincts = set()
    sans_nom = 0
    sans_taille = 0
    sans_date = 0
    bureau_pdf_count = 0
    for d in docs[:50]:
        if not isinstance(d, dict):
            continue
        nom = d.get("nom") or d.get("nom_fichier") or d.get("filename") or ""
        if not nom or "undefined" in nom.lower():
            sans_nom += 1
        types_distincts.add(d.get("type") or d.get("type_document") or "?")
        if not d.get("taille") and not d.get("taille_octets") and not d.get("size"):
            sans_taille += 1
        if not (d.get("date") or d.get("date_creation") or d.get("created_at")):
            sans_date += 1
        if "bureau_pdf_" in nom or "bureau_png_" in nom:
            bureau_pdf_count += 1

    if sans_nom:
        defauts.append(f"{sans_nom} documents avec nom invalide/undefined")
    if sans_date:
        defauts.append(f"{sans_date} documents sans date")
    score = 8 - min(5, len(defauts))
    status = "PASS" if score >= 7 else "PARTIAL" if score >= 5 else "FAIL"
    return make_result("Mes Documents", status, max(0, score),
                       defauts=defauts,
                       note_text=f"{len(docs)} docs total, types={list(types_distincts)[:6]}, "
                                 f"prefixe bureau_pdf_={bureau_pdf_count}")
