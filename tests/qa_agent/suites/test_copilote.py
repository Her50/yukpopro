"""Suite D — Copilote multi-sources RAG."""
from __future__ import annotations

import json
import logging
import os

import requests

from ..browser import login, screenshot
from ..common import RunContext
from ..quality.evaluateur import _client as anthropic_client
from .base import make_result, safe_goto

log = logging.getLogger("qa_agent.suite.copilote")

QUESTIONS = [
    ("CIMA assurance", "Procédure de déclaration sinistre auto au Cameroun sous CIMA, délais et pièces exigées"),
    ("OHADA", "Différence entre SARL et SAS sous l'Acte Uniforme OHADA révisé, capital minimum"),
    ("Travail", "Durée légale préavis licenciement cadre au Sénégal, indemnités selon convention collective banques"),
    ("Pénal", "Sanctions pour abus de biens sociaux au Cameroun, articles précis"),
    ("CGI fiscalité", "Régime TVA prestations de services entre Côte d'Ivoire et Togo, seuil de franchise"),
    ("Commerce intl", "Incoterms applicables sous CISG pour vente Cameroun→France, transfert de risque"),
    ("ISO 45001", "Obligations ISO 45001 pour compagnie d'assurance employant 50 personnes"),
    ("BRVM", "Conditions d'introduction en bourse régionale BRVM pour société anonyme"),
]
SUIVI = "Quels sont les délais spécifiques pour les sinistres corporels dans la première question ?"
HORS_SUJET = "Quelle est la recette du ndolé ?"


def _login_api(api: str, email: str, password: str) -> str | None:
    for path in ("/api/v1/auth/login", "/api/v1/login"):
        try:
            r = requests.post(api + path, json={"email": email, "password": password},
                              timeout=15)
            if r.status_code == 200:
                data = r.json()
                return data.get("access_token") or data.get("token")
        except Exception:
            continue
    return None


def _evaluer_reponse(question: str, reponse: str, axe: str) -> dict:
    cli = anthropic_client()
    if cli is None or not reponse:
        return {"note": 5 if reponse else 0,
                "defauts": [] if reponse else ["reponse vide"]}
    prompt = (
        f"Tu juges la qualité d'une réponse Copilote (assurance/droit Afrique francophone).\n"
        f"Axe principal: {axe}\nQuestion: {question}\nRéponse: {reponse[:6000]}\n\n"
        "Critères: source citée (article+code), profondeur (>200 mots), localisation,\n"
        "absence de 'je suis un LLM'. Renvoie JSON {\"note\":0-10,\"defauts\":[...]}"
    )
    try:
        resp = cli.messages.create(
            model=os.getenv("QA_CLAUDE_MODEL", "claude-opus-4-7"),
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        s = text.find("{"); e = text.rfind("}")
        if s >= 0 and e > s:
            return json.loads(text[s:e+1])
    except Exception as e:
        log.warning(f"eval Claude echec: {e}")
    return {"note": 5, "defauts": ["eval Claude indisponible"]}


def _ask_copilote(api: str, token: str | None, question: str,
                  conversation_id: str | None = None) -> tuple[str, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload: dict = {"question": question}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    candidates = ["/api/v1/pro/copilote/chat", "/api/v1/copilote/chat",
                  "/api/v1/pro/copilote/ask", "/api/v1/copilote/ask"]
    last_err = None
    for path in candidates:
        try:
            r = requests.post(api + path, headers=headers, json=payload, timeout=90)
            if r.status_code == 200:
                data = r.json()
                txt = (data.get("reponse") or data.get("answer") or
                       data.get("message") or data.get("response") or "")
                return str(txt), data
            last_err = f"{path} -> {r.status_code}"
        except Exception as e:
            last_err = str(e)
    return "", {"error": last_err}


async def run(ctx: RunContext, context) -> dict:
    web = ctx.cfg["web_url"]
    api = ctx.cfg["api_url"]
    creds = ctx.cfg["credentials"]
    page = None
    screens: list[str] = []
    defauts: list[str] = []
    if context is not None:
        try:
            page = await context.new_page()
            await login(page, ctx)
            if await safe_goto(page, f"{web}/copilote", 15000):
                await page.wait_for_timeout(1500)
                screens.append(await screenshot(page, ctx, "copilote_home"))
        except Exception as e:
            log.warning(f"navigateur copilote: {e}")

    token = _login_api(api, creds["email"], creds["password"])
    if not token:
        defauts.append("login API echec — endpoints /api/v1/auth/login & /login inaccessibles")

    notes: list[int] = []
    sources_uniques: set[str] = set()
    conversation_id = None
    for axe, q in QUESTIONS:
        reponse, meta = _ask_copilote(api, token, q, conversation_id)
        if not conversation_id:
            conversation_id = meta.get("conversation_id")
        if not reponse:
            defauts.append(f"{axe}: reponse vide ({meta.get('error')})")
            notes.append(0)
            continue
        eval_q = _evaluer_reponse(q, reponse, axe)
        notes.append(int(eval_q.get("note", 0)))
        for d in eval_q.get("defauts", []):
            defauts.append(f"{axe}: {d}")
        for s in (meta.get("sources") or []):
            if isinstance(s, dict):
                sources_uniques.add(str(s.get("source") or s.get("nom") or s.get("type") or ""))
            else:
                sources_uniques.add(str(s))

    suivi_resp, _ = _ask_copilote(api, token, SUIVI, conversation_id)
    if suivi_resp and "première question" in suivi_resp.lower() and "?" in suivi_resp:
        defauts.append("suivi: ne semble pas garder le contexte (reformule la question)")
    elif not suivi_resp:
        defauts.append("suivi: pas de reponse")

    hs_resp, _ = _ask_copilote(api, token, HORS_SUJET, conversation_id)
    if hs_resp and ("ndolé" in hs_resp.lower() and "recette" in hs_resp.lower()):
        defauts.append("hors-sujet: copilote a repondu en cuisine au lieu de recadrer")

    if len(sources_uniques) < 5:
        defauts.append(f"diversite RAG faible: {len(sources_uniques)} sources distinctes (<5)")

    if page is not None:
        try:
            await page.close()
        except Exception:
            pass
    moyenne = round(sum(notes) / max(1, len(notes)))
    status = "PASS" if moyenne >= 7 else "PARTIAL" if moyenne >= 5 else "FAIL"
    return make_result(
        "Copilote (RAG multi-sources)", status, moyenne,
        defauts=defauts,
        recommandations=["enrichir citations (article + code)" if moyenne < 8 else ""],
        screenshots=screens,
        note_text=f"moyenne {moyenne}/10 sur {len(notes)} questions, "
                  f"{len(sources_uniques)} sources distinctes",
    )
