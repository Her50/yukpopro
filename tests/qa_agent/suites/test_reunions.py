"""Suite G — Réunions (audio → transcription → rapport)."""
from __future__ import annotations

import requests

from ..common import RunContext, fixtures_dir, safe_filename
from ..quality.evaluateur import evaluer_artefact
from ..quality.verifs import similarite_textes
from ..suites.test_copilote import _login_api
from .base import make_result


def _hdr(t): return {"Authorization": f"Bearer {t}"}


async def run(ctx: RunContext, context) -> dict:
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        return make_result("Réunions", "FAIL", 0, defauts=["login API impossible"])

    fdir = fixtures_dir()
    audio = fdir / "reunion_60s_fr.m4a"
    if not audio.exists():
        audio = fdir / "reunion_60s_fr.mp3"
    transcript_ref = fdir / "reunion_60s_fr.txt"
    if not audio.exists() or not transcript_ref.exists():
        return make_result("Réunions", "SKIP", None,
                           defauts=["fixtures audio réunion manquantes (edge-tts ou ffmpeg absent)"])

    defauts: list[str] = []
    notes: list[int] = []
    artefacts: list[str] = []

    files = [("fichier", (audio.name, audio.open("rb"), "audio/mpeg"))]
    data = {
        "titre": "Comité de souscription — Dossier Risque Industriel ACME",
        "participants": "Directeur technique, Actuaire, Commercial",
    }
    transcription_text = ""
    rapport_id = None
    for path in ("/api/v1/pro/reunions/transcrire", "/api/v1/pro/reunions/upload",
                 "/api/v1/bureau/audio/transcrire"):
        try:
            r = requests.post(api + path, headers=_hdr(token),
                              files=files, data=data,
                              timeout=ctx.cfg["timeouts"]["reunion_transcription_s"])
            if r.status_code in (200, 201):
                d = r.json()
                transcription_text = (d.get("transcription") or
                                      d.get("texte") or d.get("text") or "")
                rapport_id = d.get("rapport_fichier_id") or d.get("fichier_id")
                break
        except Exception:
            continue
    for f in files:
        try:
            f[1][1].close()
        except Exception:
            pass

    if not transcription_text:
        defauts.append("aucun endpoint transcription disponible / réponse vide")
        return make_result("Réunions", "FAIL", 1, defauts=defauts)

    ref = transcript_ref.read_text(encoding="utf-8")
    sim = similarite_textes(ref, transcription_text)
    if sim < ctx.cfg["quality"]["transcription_min_accuracy"]:
        defauts.append(f"précision transcription faible: {sim:.2f} "
                       f"(<{ctx.cfg['quality']['transcription_min_accuracy']})")
    notes.append(min(10, max(0, int(sim * 10))))

    if rapport_id:
        dst = ctx.downloads_dir / f"reunion_rapport_{safe_filename(str(rapport_id))}.md"
        for path in (f"/api/v1/bureau/documents/telecharger/{rapport_id}",
                     f"/api/v1/pro/documents/telecharger/{rapport_id}"):
            try:
                r = requests.get(api + path, headers=_hdr(token), timeout=30)
                if r.status_code == 200:
                    dst.write_bytes(r.content)
                    break
            except Exception:
                continue
        if dst.exists():
            artefacts.append(str(dst.relative_to(ctx.artifacts_dir)))
            eval_res = evaluer_artefact(dst, "Rapport réunion",
                                         attendus={"sections": ["participants", "décisions",
                                                                "plan d'action"],
                                                   "format": "markdown"})
            notes.append(eval_res.get("note", 5))
            defauts.extend(eval_res.get("defauts", []))

    moyenne = round(sum(notes) / max(1, len(notes)))
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Réunions (audio→rapport)", status, moyenne,
                       defauts=defauts, artefacts=artefacts,
                       note_text=f"similarité transcription={sim:.2f}")
