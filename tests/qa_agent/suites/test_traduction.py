"""Suite K — Traduction texte + DOCX."""
from __future__ import annotations

import requests

from ..common import RunContext, fixtures_dir, safe_filename
from ..quality.evaluateur import evaluer_artefact
from ..quality.verifs import detecter_langue, structure_docx
from ..suites.test_copilote import _login_api
from .base import make_result


def _hdr(t): return {"Authorization": f"Bearer {t}"}


TEXTE_FR = (
    "La réassurance facultative est une opération par laquelle un assureur cède un risque déterminé "
    "à un réassureur. La provision pour sinistres à payer doit être calculée selon une méthode "
    "statistique reconnue. Le ratio combiné cible recommandé par les régulateurs CIMA est inférieur à 95%."
)


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        return make_result("Traduction", "FAIL", 0, defauts=["login API impossible"])

    defauts: list[str] = []
    notes: list[int] = []
    artefacts: list[str] = []

    payload = {"texte": TEXTE_FR, "langue_source": "fr", "langue_cible": "en"}
    traduction_text = ""
    for path in ("/api/v1/bureau/traduction/texte",
                 "/api/v1/bureau/traduction/traduire",
                 "/api/v1/pro/traduction/texte"):
        try:
            r = requests.post(api + path, headers={**_hdr(token), "Content-Type": "application/json"},
                              json=payload, timeout=60)
            if r.status_code == 200:
                d = r.json()
                traduction_text = d.get("traduction") or d.get("texte_traduit") or d.get("text") or ""
                break
        except Exception:
            continue

    if not traduction_text:
        defauts.append("traduction texte FR→EN: aucun endpoint répondant")
        notes.append(0)
    else:
        lang = detecter_langue(traduction_text)
        if lang != "EN":
            defauts.append(f"langue cible attendue EN, détectée {lang}")
            notes.append(3)
        else:
            ratio = len(traduction_text.split()) / max(1, len(TEXTE_FR.split()))
            if ratio < 0.7 or ratio > 1.4:
                defauts.append(f"ratio mots traduction anormal {ratio:.2f}")
                notes.append(5)
            else:
                notes.append(8)
            for term_fr in ("réassurance", "provision pour sinistres"):
                if term_fr in traduction_text.lower():
                    defauts.append(f"terme FR '{term_fr}' non traduit")

    contrat = fixtures_dir() / "contrat_fr.docx"
    if contrat.exists():
        files = [("fichier", (contrat.name, contrat.open("rb"),
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))]
        data = {"langue_source": "fr", "langue_cible": "en"}
        fid = None
        for path in ("/api/v1/bureau/traduction/document",
                     "/api/v1/bureau/traduction/fichier",
                     "/api/v1/pro/traduction/document"):
            try:
                r = requests.post(api + path, headers=_hdr(token),
                                  files=files, data=data, timeout=180)
                if r.status_code == 200:
                    d = r.json()
                    fid = d.get("fichier_id") or d.get("id")
                    break
            except Exception:
                continue
        for f in files:
            try:
                f[1][1].close()
            except Exception:
                pass

        if fid:
            dst = ctx.downloads_dir / f"contrat_en_{safe_filename(str(fid))}.docx"
            for path in (f"/api/v1/bureau/documents/telecharger/{fid}",
                         f"/api/v1/pro/documents/telecharger/{fid}"):
                try:
                    r = requests.get(api + path, headers=_hdr(token), timeout=60)
                    if r.status_code == 200:
                        dst.write_bytes(r.content)
                        break
                except Exception:
                    continue
            if dst.exists():
                artefacts.append(str(dst.relative_to(ctx.artifacts_dir)))
                src_struct = structure_docx(contrat)
                try:
                    tgt_struct = structure_docx(dst)
                    if abs(tgt_struct["nb_paragraphs"] - src_struct["nb_paragraphs"]) > 5:
                        defauts.append(
                            f"paragraphes source={src_struct['nb_paragraphs']} "
                            f"vs cible={tgt_struct['nb_paragraphs']} (structure altérée)"
                        )
                    if tgt_struct["nb_tables"] != src_struct["nb_tables"]:
                        defauts.append(
                            f"tables source={src_struct['nb_tables']} "
                            f"vs cible={tgt_struct['nb_tables']}"
                        )
                except Exception as e:
                    defauts.append(f"DOCX cible illisible: {e}")
                eval_res = evaluer_artefact(dst, "Traduction DOCX FR→EN",
                                             attendus={"langue_cible": "en",
                                                       "structure_preservee": True})
                notes.append(eval_res.get("note", 5))
                defauts.extend(eval_res.get("defauts", []))
            else:
                defauts.append("download DOCX traduit impossible")
        else:
            defauts.append("traduction DOCX: aucun endpoint répondant")

    moyenne = round(sum(notes) / max(1, len(notes))) if notes else 0
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Traduction (texte+DOCX)", status, moyenne,
                       defauts=defauts, artefacts=artefacts)
