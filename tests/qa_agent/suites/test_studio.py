"""Suite F — Yukpo Studio (rapport, slides, multi-fichiers)."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from ..common import RunContext, fixtures_dir, safe_filename
from ..quality.evaluateur import evaluer_artefact
from ..quality.verifs import structure_docx, structure_pptx
from ..suites.test_copilote import _login_api
from .base import make_result

log = logging.getLogger("qa_agent.suite.studio")


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _post_json(api, path, token, body, timeout=180):
    try:
        r = requests.post(api + path, headers={**_hdr(token), "Content-Type": "application/json"},
                          json=body, timeout=timeout)
        return r.status_code, r.json() if "json" in r.headers.get("content-type", "") else r.text
    except Exception as e:
        return 0, str(e)


def _telecharger_fichier(api, nom_fichier, token, dst: Path) -> bool:
    """Download via /api/v1/pro/generateurs/fichier/{nom_fichier}"""
    if not nom_fichier:
        return False
    # strip leading path separators
    nom_propre = Path(nom_fichier).name
    for path in (
        f"/api/v1/pro/generateurs/fichier/{nom_propre}",
        f"/api/v1/pro/generateurs/fichier/{nom_fichier}",
        f"/api/v1/bureau/documents/telecharger/{nom_propre}",
    ):
        try:
            r = requests.get(api + path, headers=_hdr(token), timeout=60)
            if r.status_code == 200 and r.content and len(r.content) > 100:
                dst.write_bytes(r.content)
                return True
        except Exception:
            continue
    return False


async def _test_rapport_simple(ctx, api, token) -> dict:
    code, data = _post_json(api, "/api/v1/pro/rapports/generer", token, {
        "sujet": "Étude de marché assurance santé Cameroun 2025",
        "mode": "complet",
        "format_sortie": "docx",
    }, timeout=ctx.cfg["timeouts"]["rapport_simple_s"])
    if code != 200 or not isinstance(data, dict):
        return {"status": "FAIL", "score": 0,
                "defauts": [f"rapport simple: HTTP {code} — {str(data)[:200]}"]}
    nom = data.get("fichier") or data.get("nom_fichier") or data.get("fichier_id")
    if not nom:
        return {"status": "FAIL", "score": 0, "defauts": [f"champ 'fichier' manquant: {list(data.keys())}"]}
    dst = ctx.downloads_dir / f"rapport_simple_{safe_filename(str(nom))}"
    if not dst.suffix:
        dst = dst.with_suffix(".docx")
    if not _telecharger_fichier(api, nom, token, dst):
        return {"status": "FAIL", "score": 1, "defauts": [f"download '{nom}' impossible"]}
    try:
        struct = structure_docx(dst)
    except Exception as e:
        return {"status": "FAIL", "score": 2, "defauts": [f"docx illisible: {e}"]}
    defauts = []
    if struct["nb_paragraphs"] < 20:
        defauts.append(f"contenu court: {struct['nb_paragraphs']} paragraphes")
    if struct["nb_headings"] < 3:
        defauts.append(f"structure faible: {struct['nb_headings']} titres")
    eval_res = evaluer_artefact(dst, "Rapport IA simple",
                                 attendus={"min_pages": 5, "format": "docx",
                                           "sections": ["synthèse", "marché", "recommandations"]})
    defauts.extend(eval_res.get("defauts", []))
    return {"status": eval_res.get("verdict", "PARTIAL"),
            "score": eval_res.get("note"), "defauts": defauts,
            "artefact": str(dst.relative_to(ctx.artifacts_dir))}


async def _test_rapport_multi(ctx, api, token) -> dict:
    fdir = fixtures_dir()
    files_def = [("sinistres_2024.xlsx", fdir / "sinistres_2024.xlsx"),
                 ("rapport_concurrent.pdf", fdir / "rapport_concurrent.pdf"),
                 ("notes_equipe.docx", fdir / "notes_equipe.docx")]
    for name, p in files_def:
        if not p.exists():
            return {"status": "SKIP", "score": None, "defauts": [f"fixture manquante: {name}"]}
    files = [("fichiers", (name, p.open("rb"), "application/octet-stream"))
             for name, p in files_def]
    data_form = {
        "instruction": "Génère un rapport analytique stratégique basé sur l'analyse croisée de ces 3 documents",
        "mode": "complet",
        "format_sortie": "docx",
    }
    try:
        r = requests.post(api + "/api/v1/pro/analyser-et-generer",
                          headers=_hdr(token), files=files, data=data_form,
                          timeout=ctx.cfg["timeouts"]["rapport_multi_s"])
        resp = r.json() if "json" in r.headers.get("content-type", "") else {}
        code = r.status_code
    except Exception as e:
        return {"status": "FAIL", "score": 0, "defauts": [f"exception: {e}"]}
    finally:
        for f in files:
            try: f[1][1].close()
            except: pass
    if code != 200 or not resp:
        return {"status": "FAIL", "score": 0,
                "defauts": [f"HTTP {code} — {str(resp)[:200]}"]}
    nom = resp.get("fichier") or resp.get("nom_fichier")
    if not nom:
        return {"status": "FAIL", "score": 0, "defauts": [f"champ 'fichier' manquant: {list(resp.keys())}"]}
    dst = ctx.downloads_dir / f"rapport_multi_{safe_filename(str(nom))}"
    if not dst.suffix:
        dst = dst.with_suffix(".docx")
    if not _telecharger_fichier(api, nom, token, dst):
        return {"status": "FAIL", "score": 1, "defauts": ["download impossible"]}
    eval_res = evaluer_artefact(dst, "Rapport multi-fichiers",
                                 attendus={"doit_citer": ["sinistres", "concurrent", "auto connecté"]})
    return {"status": eval_res.get("verdict", "PARTIAL"), "score": eval_res.get("note"),
            "defauts": eval_res.get("defauts", []),
            "artefact": str(dst.relative_to(ctx.artifacts_dir))}


async def _test_slides(ctx, api, token) -> dict:
    code, data = _post_json(api, "/api/v1/pro/slides/generer", token, {
        "sujet": "Étude de marché assurance santé Cameroun 2025",
        "mode": "executive",
        "format_sortie": "pptx",
    }, timeout=ctx.cfg["timeouts"]["slides_s"])
    if code != 200 or not isinstance(data, dict):
        return {"status": "FAIL", "score": 0,
                "defauts": [f"slides: HTTP {code} — {str(data)[:200]}"]}
    nom = data.get("fichier") or data.get("nom_fichier")
    if not nom:
        return {"status": "FAIL", "score": 0, "defauts": [f"champ 'fichier' manquant: {list(data.keys())}"]}
    dst = ctx.downloads_dir / f"slides_{safe_filename(str(nom))}"
    if not dst.suffix:
        dst = dst.with_suffix(".pptx")
    if not _telecharger_fichier(api, nom, token, dst):
        return {"status": "FAIL", "score": 1, "defauts": [f"download '{nom}' impossible"]}
    try:
        struct = structure_pptx(dst)
    except Exception as e:
        return {"status": "FAIL", "score": 2, "defauts": [f"pptx illisible: {e}"]}
    defauts = []
    if struct["nb_slides"] < 8:
        defauts.append(f"slides insuffisantes: {struct['nb_slides']} (<10 attendu)")
    eval_res = evaluer_artefact(dst, "Slides IA",
                                 attendus={"min_slides": 10, "structure": "intro/contenu/reco/conclusion"})
    defauts.extend(eval_res.get("defauts", []))
    return {"status": eval_res.get("verdict", "PARTIAL"), "score": eval_res.get("note"),
            "defauts": defauts, "artefact": str(dst.relative_to(ctx.artifacts_dir))}


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    token = _login_api(api, ctx.cfg["credentials"]["email"], ctx.cfg["credentials"]["password"])
    if not token:
        return make_result("Yukpo Studio", "FAIL", 0, defauts=["login API impossible"])

    sub = {
        "F.1 Rapport simple": await _test_rapport_simple(ctx, api, token),
        "F.2 Rapport multi-fichiers": await _test_rapport_multi(ctx, api, token),
        "F.4 Slides": await _test_slides(ctx, api, token),
    }
    notes = [s["score"] for s in sub.values() if s.get("score") is not None]
    moyenne = round(sum(notes) / max(1, len(notes))) if notes else 0
    defauts: list[str] = []
    artefacts: list[str] = []
    for nom, s in sub.items():
        for d in s.get("defauts", []):
            defauts.append(f"[{nom}] {d}")
        if s.get("artefact"):
            artefacts.append(s["artefact"])
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Yukpo Studio (rapport+slides)", status, moyenne,
                       defauts=defauts, artefacts=artefacts,
                       note_text=", ".join(f"{n}={s.get('score')}" for n, s in sub.items()))
