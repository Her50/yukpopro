"""Suite F — Yukpo Studio (rapport, slides, modeles, conversion)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

from ..common import RunContext, fixtures_dir, safe_filename
from ..quality.evaluateur import evaluer_artefact
from ..quality.verifs import (compter_pages_pdf, structure_docx, structure_pptx,
                               texte_pdf)
from ..suites.test_copilote import _login_api
from .base import make_result

log = logging.getLogger("qa_agent.suite.studio")


def _post(api: str, path: str, token: str, json_body=None, files=None,
          data=None, timeout: int = 180) -> tuple[int, dict | bytes]:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.post(api + path, headers=headers, json=json_body,
                          files=files, data=data, timeout=timeout)
        if "application/json" in r.headers.get("content-type", ""):
            return r.status_code, r.json()
        return r.status_code, r.content
    except Exception as e:
        return 0, {"error": str(e)}


def _telecharger(api: str, fichier_id: str, token: str, dst: Path) -> bool:
    headers = {"Authorization": f"Bearer {token}"}
    for path in (
        f"/api/v1/pro/generateurs/document/{fichier_id}",
        f"/api/v1/bureau/documents/telecharger/{fichier_id}",
        f"/api/v1/pro/documents/telecharger/{fichier_id}",
    ):
        try:
            r = requests.get(api + path, headers=headers, timeout=60, stream=True)
            if r.status_code == 200 and r.content:
                dst.write_bytes(r.content)
                return True
        except Exception:
            continue
    return False


async def _test_rapport_simple(ctx, api, token) -> dict:
    code, data = _post(api, "/api/v1/pro/generateurs/rapport-ia", token, json_body={
        "sujet": "Étude de marché assurance santé Cameroun 2025",
        "mode": "approfondi",
        "format": "docx",
    }, timeout=ctx.cfg["timeouts"]["rapport_simple_s"])
    if code != 200 or not isinstance(data, dict):
        return {"status": "FAIL", "score": 0,
                "defauts": [f"rapport simple: HTTP {code} — {str(data)[:200]}"]}
    fid = data.get("fichier_id") or data.get("id")
    if not fid:
        return {"status": "FAIL", "score": 0,
                "defauts": ["fichier_id manquant dans réponse"]}
    dst = ctx.downloads_dir / f"rapport_simple_{safe_filename(str(fid))}.docx"
    if not _telecharger(api, fid, token, dst):
        return {"status": "FAIL", "score": 1, "defauts": ["téléchargement DOCX impossible"]}
    try:
        struct = structure_docx(dst)
    except Exception as e:
        return {"status": "FAIL", "score": 2, "defauts": [f"docx illisible: {e}"]}
    eval_res = evaluer_artefact(dst, "Rapport IA simple",
                                 attendus={"min_pages": 5, "format": "docx",
                                           "sections": ["exec summary", "marché", "concurrence", "PESTEL", "reco"]})
    defauts = list(eval_res.get("defauts", []))
    if struct["nb_paragraphs"] < 30:
        defauts.append(f"trop court: {struct['nb_paragraphs']} paragraphes")
    if struct["nb_headings"] < 4:
        defauts.append(f"structure faible: {struct['nb_headings']} titres")
    return {"status": eval_res.get("verdict", "PARTIAL"),
            "score": eval_res.get("note"),
            "defauts": defauts,
            "artefact": str(dst.relative_to(ctx.artifacts_dir))}


async def _test_rapport_multi(ctx, api, token) -> dict:
    fdir = fixtures_dir()
    files_paths = {
        "sinistres_2024.xlsx": fdir / "sinistres_2024.xlsx",
        "rapport_concurrent.pdf": fdir / "rapport_concurrent.pdf",
        "notes_equipe.docx": fdir / "notes_equipe.docx",
    }
    for name, p in files_paths.items():
        if not p.exists():
            return {"status": "SKIP", "score": None,
                    "defauts": [f"fixture manquante: {name}"]}
    files = [("fichiers", (name, p.open("rb"),
                            "application/octet-stream"))
             for name, p in files_paths.items()]
    data = {
        "instruction": "Génère un rapport analytique stratégique basé sur l'analyse "
                       "croisée de ces 3 documents",
        "format": "docx",
    }
    code, resp = _post(api, "/api/v1/pro/analyser-et-generer", token,
                       files=files, data=data,
                       timeout=ctx.cfg["timeouts"]["rapport_multi_s"])
    for f in files:
        try:
            f[1][1].close()
        except Exception:
            pass
    if code != 200 or not isinstance(resp, dict):
        return {"status": "FAIL", "score": 0,
                "defauts": [f"HTTP {code} — {str(resp)[:200]}"]}
    fid = resp.get("fichier_id") or resp.get("id")
    if not fid:
        return {"status": "FAIL", "score": 0, "defauts": ["fichier_id manquant"]}
    dst = ctx.downloads_dir / f"rapport_multi_{safe_filename(str(fid))}.docx"
    if not _telecharger(api, fid, token, dst):
        return {"status": "FAIL", "score": 1,
                "defauts": ["téléchargement impossible"]}
    eval_res = evaluer_artefact(dst, "Rapport multi-fichiers",
                                 attendus={"min_pages": 6,
                                           "doit_citer": ["sinistres", "concurrent", "auto connecté"]})
    return {"status": eval_res.get("verdict", "PARTIAL"),
            "score": eval_res.get("note"),
            "defauts": eval_res.get("defauts", []),
            "artefact": str(dst.relative_to(ctx.artifacts_dir))}


async def _test_slides(ctx, api, token) -> dict:
    code, data = _post(api, "/api/v1/pro/generateurs/slides-ia", token, json_body={
        "sujet": "Étude de marché assurance santé Cameroun 2025",
        "mode": "approfondi",
    }, timeout=ctx.cfg["timeouts"]["slides_s"])
    if code != 200 or not isinstance(data, dict):
        return {"status": "FAIL", "score": 0,
                "defauts": [f"HTTP {code} — {str(data)[:200]}"]}
    fid = data.get("fichier_id") or data.get("id")
    if not fid:
        return {"status": "FAIL", "score": 0, "defauts": ["fichier_id manquant"]}
    dst = ctx.downloads_dir / f"slides_{safe_filename(str(fid))}.pptx"
    if not _telecharger(api, fid, token, dst):
        return {"status": "FAIL", "score": 1, "defauts": ["téléchargement impossible"]}
    try:
        struct = structure_pptx(dst)
    except Exception as e:
        return {"status": "FAIL", "score": 2, "defauts": [f"pptx illisible: {e}"]}
    defauts = []
    if struct["nb_slides"] < 10:
        defauts.append(f"slides insuffisantes: {struct['nb_slides']} (<10)")
    eval_res = evaluer_artefact(dst, "Slides IA",
                                 attendus={"min_slides": 10, "structure": "intro/contenu/reco/conclusion"})
    defauts.extend(eval_res.get("defauts", []))
    return {"status": eval_res.get("verdict", "PARTIAL"),
            "score": eval_res.get("note"),
            "defauts": defauts,
            "artefact": str(dst.relative_to(ctx.artifacts_dir))}


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        return make_result("Yukpo Studio", "FAIL", 0,
                           defauts=["login API impossible"])

    sub_results = {
        "F.1 Rapport simple": await _test_rapport_simple(ctx, api, token),
        "F.2 Rapport multi-fichiers": await _test_rapport_multi(ctx, api, token),
        "F.4 Slides": await _test_slides(ctx, api, token),
    }

    notes = [s["score"] for s in sub_results.values() if s.get("score") is not None]
    moyenne = round(sum(notes) / max(1, len(notes))) if notes else 0
    defauts: list[str] = []
    artefacts: list[str] = []
    for nom, s in sub_results.items():
        for d in s.get("defauts", []):
            defauts.append(f"[{nom}] {d}")
        if s.get("artefact"):
            artefacts.append(s["artefact"])

    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Yukpo Studio (rapport+slides)", status, moyenne,
                       defauts=defauts, artefacts=artefacts,
                       note_text=", ".join(f"{n}={s.get('score')}" for n, s in sub_results.items()))
