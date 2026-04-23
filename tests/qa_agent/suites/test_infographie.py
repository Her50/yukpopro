"""Suite F.7 — Infographie (4 sous-modes, 4 gabarits)."""
from __future__ import annotations

from pathlib import Path

import requests

from ..common import RunContext, fixtures_dir, safe_filename
from ..quality.evaluateur import evaluer_artefact
from ..quality.verifs import dimensions_pdf_mm, image_dimensions
from ..suites.test_copilote import _login_api
from .base import make_result


GABARITS_TEST = ["flyer_a5", "carte_visite", "diplome", "affiche_a4"]
DIM_ATTENDUES = {
    "flyer_a5": (148.0, 210.0),
    "carte_visite": (85.0, 55.0),
    "diplome": (297.0, 210.0),
    "affiche_a4": (210.0, 297.0),
}


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _telecharger_fichier(api, fichier_id, token, dst: Path) -> bool:
    for path in (
        f"/api/v1/bureau/infographie/fichier/{fichier_id}",
        f"/api/v1/bureau/documents/telecharger/{fichier_id}",
    ):
        try:
            r = requests.get(api + path, headers=_hdr(token), timeout=60)
            if r.status_code == 200 and r.content:
                dst.write_bytes(r.content)
                return True
        except Exception:
            continue
    return False


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        return make_result("Infographie", "FAIL", 0, defauts=["login API impossible"])

    try:
        r = requests.get(api + "/api/v1/bureau/infographie/gabarits",
                         headers=_hdr(token), timeout=15)
        if r.status_code != 200:
            return make_result("Infographie", "FAIL", 0,
                               defauts=[f"GET gabarits HTTP {r.status_code}"])
        gabarits_data = r.json()
    except Exception as e:
        return make_result("Infographie", "FAIL", 0, defauts=[f"GET gabarits: {e}"])

    gabarits_ids = []
    if isinstance(gabarits_data, list):
        gabarits_ids = [g.get("id") for g in gabarits_data if isinstance(g, dict)]
    elif isinstance(gabarits_data, dict):
        gabarits_ids = list(gabarits_data.keys())

    a_tester = [g for g in GABARITS_TEST if g in gabarits_ids][:3]
    if not a_tester:
        a_tester = gabarits_ids[:2]
    if not a_tester:
        return make_result("Infographie", "FAIL", 0, defauts=["aucun gabarit disponible"])

    notes = []
    defauts: list[str] = []
    artefacts: list[str] = []

    for gid in a_tester:
        payload = {
            "gabarit": gid,
            "brief": f"Flyer professionnel pour ASSUR-CIMA, journée client à Yaoundé "
                     f"le 12 avril 2026 — design moderne, palette bleu/or, FR.",
            "pays": "CM",
        }
        try:
            r = requests.post(api + "/api/v1/bureau/infographie/generer",
                              headers={**_hdr(token), "Content-Type": "application/json"},
                              json=payload,
                              timeout=ctx.cfg["timeouts"]["infographie_s"])
            if r.status_code in (402, 403):
                defauts.append(f"{gid}: HTTP {r.status_code} (crédits/plan) — verifier abonnement test")
                continue
            if r.status_code != 200:
                defauts.append(f"{gid}: HTTP {r.status_code} — {r.text[:150]}")
                continue
            data = r.json()
        except Exception as e:
            defauts.append(f"{gid}: exception {e}")
            continue

        pdf_id = data.get("pdf_fichier_id") or data.get("fichier_pdf_id")
        png_id = data.get("png_fichier_id") or data.get("preview_fichier_id") or data.get("fichier_png_id")

        if pdf_id:
            pdf_dst = ctx.downloads_dir / f"infog_{gid}_{safe_filename(str(pdf_id))}.pdf"
            if _telecharger_fichier(api, pdf_id, token, pdf_dst):
                artefacts.append(str(pdf_dst.relative_to(ctx.artifacts_dir)))
                try:
                    w, h = dimensions_pdf_mm(pdf_dst)
                    target = DIM_ATTENDUES.get(gid)
                    if target:
                        tw, th = target
                        if not ((abs(w - tw) < 5 and abs(h - th) < 5) or
                                (abs(w - th) < 5 and abs(h - tw) < 5)):
                            defauts.append(f"{gid}: dim PDF {w:.0f}x{h:.0f}mm "
                                           f"!= attendu {tw:.0f}x{th:.0f}mm")
                except Exception as e:
                    defauts.append(f"{gid}: lecture dim PDF echec ({e})")
            else:
                defauts.append(f"{gid}: download PDF impossible")

        if png_id:
            png_dst = ctx.downloads_dir / f"infog_{gid}_{safe_filename(str(png_id))}.png"
            if _telecharger_fichier(api, png_id, token, png_dst):
                artefacts.append(str(png_dst.relative_to(ctx.artifacts_dir)))
                try:
                    w, h = image_dimensions(png_dst)
                    if w < 600 or h < 600:
                        defauts.append(f"{gid}: PNG preview faible ({w}x{h})")
                except Exception:
                    pass
                eval_res = evaluer_artefact(png_dst, f"Infographie {gid}",
                                             attendus={"print_ready": True, "type": "flyer"})
                notes.append(eval_res.get("note", 5))
                defauts.extend(f"{gid}: {d}" for d in eval_res.get("defauts", []))

    moyenne = round(sum(notes) / max(1, len(notes))) if notes else 0
    if moyenne == 0 and defauts:
        return make_result("Infographie", "FAIL", 0, defauts=defauts, artefacts=artefacts)
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Infographie", status, moyenne, defauts=defauts,
                       artefacts=artefacts,
                       note_text=f"moyenne {moyenne}/10 sur {len(a_tester)} gabarits")
