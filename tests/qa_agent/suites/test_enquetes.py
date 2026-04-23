"""Suite H — Enquêtes (XLSForm + analyses + rapport)."""
from __future__ import annotations

from pathlib import Path

import requests

from ..common import RunContext, fixtures_dir, safe_filename
from ..quality.evaluateur import evaluer_artefact
from ..quality.verifs import structure_xlsform, structure_docx
from ..suites.test_copilote import _login_api
from .base import make_result


def _hdr(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        return make_result("Enquêtes", "FAIL", 0, defauts=["login API impossible"])

    proto = fixtures_dir() / "protocole_enquete.pdf"
    if not proto.exists():
        return make_result("Enquêtes", "SKIP", None,
                           defauts=["fixture protocole_enquete.pdf manquante"])

    defauts: list[str] = []
    artefacts: list[str] = []
    notes: list[int] = []

    etude_id = None
    payload_etude = {
        "titre": "Satisfaction clients assurance auto Douala",
        "contexte": "Marché auto Cameroun, NPS sectoriel -12, 400 répondants visés",
        "population_cible": "Particuliers 25-60 ans Douala",
        "mode": "mixte",
        "methodologie": "exploratoire",
    }
    for path in ("/api/v1/pro/enquetes/etudes", "/api/v1/enquetes/etudes",
                 "/api/v1/pro/enquetes/creer"):
        try:
            r = requests.post(api + path, headers={**_hdr(token), "Content-Type": "application/json"},
                              json=payload_etude, timeout=30)
            if r.status_code in (200, 201):
                d = r.json()
                etude_id = d.get("id") or d.get("etude_id")
                break
        except Exception:
            continue
    if not etude_id:
        defauts.append("création étude impossible (endpoint introuvable)")

    xlsform_id = None
    files = [("fichier", ("protocole_enquete.pdf", proto.open("rb"), "application/pdf"))]
    data = {"n_questions": "20"}
    if etude_id:
        data["etude_id"] = str(etude_id)
    for path in ("/api/v1/pro/enquetes/formulaire/generer-depuis-protocole",
                 "/api/v1/pro/enquetes/xlsform/generer",
                 "/api/v1/pro/enquetes/generer-formulaire"):
        try:
            r = requests.post(api + path, headers=_hdr(token),
                              files=files, data=data, timeout=120)
            if r.status_code in (200, 201):
                d = r.json()
                xlsform_id = (d.get("xlsform_fichier_id") or d.get("fichier_id")
                              or d.get("id"))
                break
        except Exception:
            continue
    for f in files:
        try:
            f[1][1].close()
        except Exception:
            pass

    if not xlsform_id:
        defauts.append("génération XLSForm impossible")
        return make_result("Enquêtes", "FAIL", 0, defauts=defauts)

    dst = ctx.downloads_dir / f"xlsform_{safe_filename(str(xlsform_id))}.xlsx"
    for path in (
        f"/api/v1/bureau/documents/telecharger/{xlsform_id}",
        f"/api/v1/pro/documents/telecharger/{xlsform_id}",
        f"/api/v1/pro/enquetes/formulaire/{xlsform_id}",
    ):
        try:
            r = requests.get(api + path, headers=_hdr(token), timeout=30)
            if r.status_code == 200 and r.content:
                dst.write_bytes(r.content)
                break
        except Exception:
            continue

    if not dst.exists():
        defauts.append("download XLSForm impossible")
        return make_result("Enquêtes", "FAIL", 1, defauts=defauts)

    artefacts.append(str(dst.relative_to(ctx.artifacts_dir)))
    try:
        struct = structure_xlsform(dst)
    except Exception as e:
        defauts.append(f"XLSForm illisible: {e}")
        return make_result("Enquêtes", "FAIL", 2, defauts=defauts, artefacts=artefacts)

    if not struct["has_survey"]:
        defauts.append("onglet 'survey' manquant — non conforme ODK")
    if not struct["has_choices"]:
        defauts.append("onglet 'choices' manquant")
    if not struct["has_settings"]:
        defauts.append("onglet 'settings' manquant")
    seuil_q = ctx.cfg["quality"]["enquete_xlsform_min_questions"]
    if struct["nb_questions"] < seuil_q:
        defauts.append(f"questions insuffisantes: {struct['nb_questions']} (<{seuil_q})")

    eval_struct = 8
    if defauts:
        eval_struct -= min(5, len(defauts))
    notes.append(eval_struct)

    eval_qual = evaluer_artefact(dst, "XLSForm enquête",
                                  attendus={"min_questions": seuil_q,
                                            "format": "ODK XLSForm",
                                            "doit_contenir": ["survey", "choices", "settings"]})
    notes.append(eval_qual.get("note", 5))
    defauts.extend(eval_qual.get("defauts", []))

    moyenne = round(sum(notes) / max(1, len(notes)))
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Enquêtes (XLSForm)", status, moyenne,
                       defauts=defauts, artefacts=artefacts,
                       note_text=f"{struct['nb_questions']} questions, "
                                 f"sheets={struct['sheets']}")
