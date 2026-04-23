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
    token = _login_api(api, ctx.cfg["credentials"]["email"], ctx.cfg["credentials"]["password"])
    if not token:
        return make_result("Réunions", "FAIL", 0, defauts=["login API impossible"])

    fdir = fixtures_dir()
    audio = next((fdir / f for f in ("reunion_60s_fr.m4a", "reunion_60s_fr.mp3")
                  if (fdir / f).exists()), None)
    transcript_ref = fdir / "reunion_60s_fr.txt"

    if not audio or not transcript_ref.exists():
        return make_result("Réunions", "SKIP", None,
                           defauts=["fixtures audio réunion manquantes (edge-tts ou ffmpeg absent)"])

    defauts, notes, artefacts = [], [], []
    transcription_text = ""

    files = [("audio", (audio.name, audio.open("rb"), "audio/mpeg"))]
    for path in ("/api/v1/pro/reunions/transcrire-direct",
                 "/api/v1/reunions/transcrire"):
        try:
            r = requests.post(api + path, headers=_hdr(token),
                              files=files, data={"langue": "auto"},
                              timeout=ctx.cfg["timeouts"]["reunion_transcription_s"])
            if r.status_code == 200:
                d = r.json()
                transcription_text = (d.get("transcription") or d.get("texte") or
                                      d.get("text") or d.get("transcript") or "")
                break
            elif r.status_code != 404:
                defauts.append(f"transcrire-direct HTTP {r.status_code}: {r.text[:150]}")
        except Exception as e:
            defauts.append(f"exception transcrire: {e}")
            break
    for f in files:
        try: f[1][1].close()
        except: pass

    if not transcription_text:
        return make_result("Réunions", "FAIL", 1,
                           defauts=defauts + ["transcription vide ou endpoint absent"])

    ref = transcript_ref.read_text(encoding="utf-8")
    sim = similarite_textes(ref, transcription_text)
    notes.append(min(10, max(0, int(sim * 10))))
    if sim < ctx.cfg["quality"]["transcription_min_accuracy"]:
        defauts.append(f"précision transcription: {sim:.2f} (<{ctx.cfg['quality']['transcription_min_accuracy']})")

    # Générer rapport depuis la transcription
    try:
        r = requests.post(api + "/api/v1/pro/reunions/generer-rapport",
                          headers={**_hdr(token), "Content-Type": "application/json"},
                          json={"transcription": transcription_text,
                                "titre": "Comité de souscription — Dossier Risque Industriel ACME",
                                "participants": "Directeur technique, Actuaire, Commercial"},
                          timeout=90)
        if r.status_code == 200:
            d = r.json()
            rapport_text = d.get("rapport") or d.get("contenu") or d.get("markdown") or ""
            if rapport_text:
                dst = ctx.downloads_dir / "reunion_rapport.md"
                dst.write_text(rapport_text, encoding="utf-8")
                artefacts.append(str(dst.relative_to(ctx.artifacts_dir)))
                eval_res = evaluer_artefact(dst, "Rapport réunion",
                                             attendus={"sections": ["participants", "décisions", "actions"]})
                notes.append(eval_res.get("note", 5))
                defauts.extend(eval_res.get("defauts", []))
        else:
            defauts.append(f"generer-rapport HTTP {r.status_code}")
    except Exception as e:
        defauts.append(f"generer-rapport exception: {e}")

    moyenne = round(sum(notes) / max(1, len(notes)))
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result("Réunions (audio→rapport)", status, moyenne,
                       defauts=defauts, artefacts=artefacts,
                       note_text=f"similarité={sim:.2f}")
