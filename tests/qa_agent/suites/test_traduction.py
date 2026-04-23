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
    "La réassurance facultative est une opération par laquelle un assureur cède un risque "
    "déterminé à un réassureur. La provision pour sinistres à payer doit être calculée selon "
    "une méthode statistique reconnue. Le ratio combiné cible recommandé par les régulateurs "
    "CIMA est inférieur à 95%. L'Acte Uniforme OHADA sur le droit commercial général encadre "
    "les obligations contractuelles des acteurs du marché dans la zone CEMAC."
)


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    token = _login_api(api, ctx.cfg["credentials"]["email"], ctx.cfg["credentials"]["password"])
    if not token:
        return make_result("Traduction", "FAIL", 0, defauts=["login API impossible"])

    defauts, notes, artefacts = [], [], []

    # 1. Texte FR → EN
    try:
        r = requests.post(api + "/api/v1/bureau/traduction/texte",
                          headers={**_hdr(token), "Content-Type": "application/json"},
                          json={"contenu": TEXTE_FR, "langue_source": "fr", "langue_cible": "en"},
                          timeout=60)
        if r.status_code == 200:
            d = r.json()
            trad = d.get("texte_traduit") or d.get("traduction") or d.get("text") or ""
            if not trad:
                defauts.append("réponse traduction texte: champ texte_traduit vide")
                notes.append(0)
            else:
                lang = detecter_langue(trad)
                if lang not in ("EN", "UNK"):
                    notes.append(8)
                else:
                    ratio = len(trad.split()) / max(1, len(TEXTE_FR.split()))
                    notes.append(7 if 0.7 <= ratio <= 1.5 else 5)
                    if ratio < 0.5 or ratio > 2.0:
                        defauts.append(f"ratio mots traduction anormal {ratio:.2f}")
        else:
            defauts.append(f"traduction texte HTTP {r.status_code}: {r.text[:150]}")
            notes.append(0)
    except Exception as e:
        defauts.append(f"traduction texte exception: {e}")
        notes.append(0)

    # 2. Fichier DOCX FR → EN
    contrat = fixtures_dir() / "contrat_fr.docx"
    if contrat.exists():
        files = [("fichier", (contrat.name, contrat.open("rb"),
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))]
        try:
            r = requests.post(api + "/api/v1/bureau/traduction/fichier",
                              headers=_hdr(token), files=files,
                              data={"langue_source": "fr", "langue_cible": "en"},
                              timeout=180)
            if r.status_code == 200:
                d = r.json()
                fid = d.get("fichier_id") or d.get("id")
                if fid:
                    dl_r = requests.get(api + f"/api/v1/bureau/traduction/fichier/{fid}",
                                        headers=_hdr(token), timeout=60)
                    if dl_r.status_code == 200 and dl_r.content:
                        dst = ctx.downloads_dir / f"contrat_en_{safe_filename(fid)}.docx"
                        dst.write_bytes(dl_r.content)
                        artefacts.append(str(dst.relative_to(ctx.artifacts_dir)))
                        src_struct = structure_docx(contrat)
                        try:
                            tgt_struct = structure_docx(dst)
                            if abs(tgt_struct["nb_tables"] - src_struct["nb_tables"]) > 1:
                                defauts.append(f"tables source={src_struct['nb_tables']} "
                                               f"vs cible={tgt_struct['nb_tables']}")
                        except Exception as e:
                            defauts.append(f"DOCX traduit illisible: {e}")
                        eval_res = evaluer_artefact(dst, "Traduction DOCX FR→EN",
                                                     attendus={"langue_cible": "anglais",
                                                               "structure_preservee": True})
                        notes.append(eval_res.get("note", 5))
                        defauts.extend(eval_res.get("defauts", []))
                    else:
                        defauts.append(f"download DOCX traduit HTTP {dl_r.status_code}")
                else:
                    defauts.append(f"fichier_id manquant dans réponse: {list(d.keys())}")
            else:
                defauts.append(f"traduction fichier HTTP {r.status_code}: {r.text[:150]}")
        except Exception as e:
            defauts.append(f"traduction fichier exception: {e}")
        finally:
            for f in files:
                try: f[1][1].close()
                except: pass

    moyenne = round(sum(notes) / max(1, len(notes))) if notes else 0
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Traduction (texte+DOCX)", status, moyenne,
                       defauts=defauts, artefacts=artefacts)
