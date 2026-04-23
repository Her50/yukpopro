"""Suite H — Enquêtes (upload protocole → XLSForm ODK)."""
from __future__ import annotations

import requests

from ..common import RunContext, fixtures_dir, safe_filename
from ..quality.evaluateur import evaluer_artefact
from ..quality.verifs import structure_xlsform
from ..suites.test_copilote import _login_api
from .base import make_result


def _hdr(t): return {"Authorization": f"Bearer {t}"}


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    token = _login_api(api, ctx.cfg["credentials"]["email"], ctx.cfg["credentials"]["password"])
    if not token:
        return make_result("Enquêtes", "FAIL", 0, defauts=["login API impossible"])

    proto = fixtures_dir() / "protocole_enquete.pdf"
    if not proto.exists():
        return make_result("Enquêtes", "SKIP", None,
                           defauts=["fixture protocole_enquete.pdf manquante"])

    defauts, artefacts, notes = [], [], []

    # 1. Créer une étude
    etude_id = None
    try:
        r = requests.post(api + "/api/v1/enquetes/",
                          headers={**_hdr(token), "Content-Type": "application/json"},
                          json={"titre": "Satisfaction clients assurance auto Douala",
                                "contexte": "Marché auto Cameroun, NPS -12",
                                "population_cible": "Particuliers 25-60 ans Douala",
                                "mode": "mixte", "methodologie": "exploratoire"},
                          timeout=20)
        if r.status_code in (200, 201):
            etude_id = r.json().get("etude_id") or r.json().get("id")
    except Exception as e:
        defauts.append(f"création étude: {e}")

    # 2. Upload protocole → XLSForm via /enquetes/upload-protocole
    files = [("fichier", ("protocole_enquete.pdf", proto.open("rb"), "application/pdf"))]
    data_form: dict = {"titre": "Satisfaction assurance auto Douala", "n_questions": "20"}
    if etude_id:
        data_form["etude_id"] = str(etude_id)
    lien_xlsform = None
    formulaire_id = None
    try:
        r = requests.post(api + "/api/v1/enquetes/upload-protocole",
                          headers=_hdr(token), files=files, data=data_form, timeout=120)
        if r.status_code in (200, 201):
            resp = r.json()
            lien_xlsform = resp.get("lien_xlsform")
            formulaire_id = resp.get("formulaire_id")
            n_gen = resp.get("n_questions", 0)
            if n_gen < 5:
                defauts.append(f"XLSForm: seulement {n_gen} questions générées")
        else:
            defauts.append(f"upload-protocole HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        defauts.append(f"upload-protocole exception: {e}")
    finally:
        for f in files:
            try: f[1][1].close()
            except: pass

    # 3. Télécharger le XLSForm
    dst = None
    if etude_id and lien_xlsform:
        xlsform_url = api + lien_xlsform if lien_xlsform.startswith("/") else lien_xlsform
        try:
            r = requests.get(xlsform_url, headers=_hdr(token), timeout=30)
            if r.status_code == 200 and r.content:
                dst = ctx.downloads_dir / f"xlsform_{safe_filename(str(etude_id))}.xlsx"
                dst.write_bytes(r.content)
                artefacts.append(str(dst.relative_to(ctx.artifacts_dir)))
        except Exception as e:
            defauts.append(f"download XLSForm: {e}")
    if not dst and etude_id:
        try:
            r = requests.get(api + f"/api/v1/enquetes/{etude_id}/formulaire/xlsform",
                             headers=_hdr(token), timeout=30)
            if r.status_code == 200 and r.content:
                dst = ctx.downloads_dir / f"xlsform_{safe_filename(str(etude_id))}.xlsx"
                dst.write_bytes(r.content)
                artefacts.append(str(dst.relative_to(ctx.artifacts_dir)))
        except Exception as e:
            defauts.append(f"download XLSForm (2): {e}")

    if not dst or not dst.exists():
        defauts.append("XLSForm non téléchargeable (formulaire_id requis + etude créée)")
        score = 2 if not etude_id else 3
        return make_result("Enquêtes (XLSForm)", "FAIL", score, defauts=defauts, artefacts=artefacts)

    # 4. Vérifier structure XLSForm
    try:
        struct = structure_xlsform(dst)
    except Exception as e:
        defauts.append(f"XLSForm illisible: {e}")
        return make_result("Enquêtes (XLSForm)", "FAIL", 2, defauts=defauts, artefacts=artefacts)

    if not struct["has_survey"]:
        defauts.append("onglet 'survey' manquant — non conforme ODK")
    if not struct["has_choices"]:
        defauts.append("onglet 'choices' manquant")
    seuil = ctx.cfg["quality"]["enquete_xlsform_min_questions"]
    if struct["nb_questions"] < seuil:
        defauts.append(f"questions insuffisantes: {struct['nb_questions']} (<{seuil})")
    notes.append(max(0, 9 - len([d for d in defauts if "manquant" in d or "insuffisant" in d])))

    eval_res = evaluer_artefact(dst, "XLSForm enquête ODK",
                                 attendus={"min_questions": seuil,
                                           "format": "XLSForm ODK",
                                           "doit_contenir": ["survey", "choices"]})
    notes.append(eval_res.get("note", 5))
    defauts.extend(eval_res.get("defauts", []))

    moyenne = round(sum(notes) / max(1, len(notes)))
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Enquêtes (XLSForm)", status, moyenne, defauts=defauts, artefacts=artefacts,
                       note_text=f"{struct['nb_questions']} questions, sheets={struct['sheets']}")
