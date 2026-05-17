"""
Routes Enquêtes & Études — Analyse qualitative IA + collecte quantitative (KoBoCollect-like)
"""
import base64
import json
import logging
import re
import time as _time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yukpo_assurance.api.enquetes")

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from core.auth import TokenData, get_current_user
from modules.enquetes import gestionnaire_enquetes as ge
from modules.enquetes import helpers_dictionnaire_plan as hdp
from modules.enquetes import facturation as fact
from modules.enquetes.persistence import (
    sauvegarder_etude, charger_etudes_user, charger_toutes_etudes,
)
from api._routes_enquetes_extra import extra_router

# Note : pas de gate par permission — module YukpoPro accessible à tout user
# authentifié, l'accès est régulé par les crédits/forfaits, pas par le rôle.
router = APIRouter()
router.include_router(extra_router)

AUDIO_MIMES = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg",
               "audio/webm", "audio/x-m4a", "application/octet-stream"}

PROTOCOLE_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
}

_BUREAU_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_BUREAU_DIR.mkdir(parents=True, exist_ok=True)


# ─── Rate-limit IP simple en mémoire (P2 #7) ───────────────────────────────
# Pour la prod multi-instances → Redis (déjà en deps), mais en mono-instance
# un dict in-memory suffit largement à bloquer un bot naïf.
from collections import deque as _dq
from datetime import datetime  # noqa: E402  (used in soumettre_reponse_publique)
import time as _rl_time

_rl_buckets: dict[str, _dq] = {}  # clé "ip|formulaire_id" → deque[timestamps]
_RL_MAX_PER_MIN = 20
_RL_WINDOW_SEC = 60.0


def _rate_limit_ok(ip: str, formulaire_id: str) -> bool:
    """True si la soumission peut passer ; False si >20 dans la dernière minute."""
    key = f"{ip}|{formulaire_id}"
    now = _rl_time.monotonic()
    bucket = _rl_buckets.get(key)
    if bucket is None:
        bucket = _dq()
        _rl_buckets[key] = bucket
    # Purge fenêtre
    while bucket and (now - bucket[0]) > _RL_WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= _RL_MAX_PER_MIN:
        return False
    bucket.append(now)
    return True


def _etude_owner_ou_404(etude_id: str, user_id: int):
    """Récupère une étude SI elle appartient au user, sinon lève 404.

    Centralise l'autorisation : tout endpoint authentifié qui prend
    `etude_id` en URL DOIT passer par ici, pas par `ge.get_etude` direct
    (qui ne filtre pas par ownership). Le 404 (au lieu de 403) ne révèle
    pas l'existence d'études d'autres users.
    """
    etude = ge.get_etude_user(user_id, etude_id)
    if not etude:
        raise HTTPException(404, "Étude introuvable")
    return etude


def _slug(s: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip())[:n].strip("_")
    return s or "enquete"


def _save_bureau(user_id: int, kind: str, titre: str, ext: str, content: bytes) -> str:
    """Sauve un artefact d'enquête dans bureau/documents. kind: 'xls' | 'rapport'."""
    ts = int(_time.time())
    safe_titre = _slug(titre)
    # Pattern: bureau_doc_{user_id}_{kind}_{titre}_{ts}.{ext}
    # "_doc_" pour être reconnu comme "Rédaction IA" dans le listing bureau
    filename = f"bureau_doc_{user_id}_{kind}_{safe_titre}_{ts}.{ext}"
    path = _BUREAU_DIR / filename
    path.write_bytes(content)
    return filename


def _extract_text_from_upload(filename: str, content: bytes) -> str:
    """Extrait le texte d'un PDF / DOCX / TXT."""
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "txt":
        return content.decode("utf-8", errors="ignore")
    if ext == "pdf":
        try:
            from io import BytesIO
            try:
                from pypdf import PdfReader
            except ImportError:
                from PyPDF2 import PdfReader
            reader = PdfReader(BytesIO(content))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            raise ValueError(f"Impossible de lire le PDF : {e}")
    if ext in ("docx", "doc"):
        try:
            from io import BytesIO
            from docx import Document
            doc = Document(BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise ValueError(f"Impossible de lire le DOCX : {e}")
    raise ValueError(f"Format non supporté : {ext}. Utilisez PDF, DOCX ou TXT.")


# ─── Schémas Pydantic ─────────────────────────────────────────────────────────

class NouvelleEtudeRequest(BaseModel):
    titre: str
    contexte: str = ""
    questions_recherche: list[str] = []
    methodologie: str = "exploratoire"  # phénoménologique | théorie ancrée | ethnographique | exploratoire
    population_cible: str = ""
    terrain: str = ""
    mode: str = "qualitatif"  # qualitatif | quantitatif | mixte


class QuestionFormulaireIn(BaseModel):
    libelle: str
    type_question: str = "text"
    options: list[str] = []
    obligatoire: bool = True
    # Champs XLSForm étendus (optionnels — exposés à l'éditeur visuel)
    hint: str = ""
    section_id: str = ""
    section_label: str = ""
    relevant: str = ""
    constraint: str = ""
    constraint_message: str = ""
    appearance: str = ""
    parameters: str = ""
    name_xlsform: str = ""
    ordre: int = 0


class NouveauFormulaireRequest(BaseModel):
    titre: str
    description: str = ""
    questions: list[QuestionFormulaireIn]


class MajFormulaireRequest(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None
    actif: Optional[bool] = None
    questions: list[QuestionFormulaireIn]


# ─── Phase E1 — Génération étude + formulaire par PROMPT ────────────────────


class GenererParPromptRequest(BaseModel):
    """Phase E1 — Body pour /enquetes/generer-par-prompt."""
    brief: str
    nb_questions_cible: Optional[int] = None
    profil_cible: Optional[str] = None
    langue: str = "fr"
    confirmer_cout: bool = False


@router.post(
    "/generer-par-prompt/stream",
    summary="Phase E1 — Génération étude/formulaire en streaming SSE (~30-60s sans UI gelée)",
)
async def generer_par_prompt_stream(
    payload: GenererParPromptRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Version SSE de `/generer-par-prompt`. Le client reçoit :
      • `data: {"step": "advisor"}` puis `{"step": "llm"}` puis
        `{"step": "saving"}` puis `{"step": "done", "etude_id": "..."}`.
      • En cas d'erreur : `{"step": "error", "detail": "..."}` puis close.

    Évite le timeout perçu (60s d'attente UI gelée) — front affiche une
    barre de progression réactive. Le LLM Opus n'est pas streamé token-par-
    token (génération JSON structurée), mais les étapes pipeline le sont.
    """
    import asyncio as _aio

    async def _gen():
        try:
            yield {"event": "step", "data": json.dumps({"step": "precheck"})}
            await fact.precheck(current_user.user_id)
            await charger_etudes_user(current_user.user_id)

            if not payload.confirmer_cout:
                yield {"event": "step", "data": json.dumps({"step": "advisor"})}
                from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
                cout = estimer_cout_module(
                    "enquete_generer",
                    multiplicateur=(payload.nb_questions_cible or 20) / 20.0,
                )
                v = await advisor.evaluer(
                    current_user.user_id, cout, module="enquete_generer",
                )
                if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
                    yield {"event": "step", "data": json.dumps({"step": "error", "code": 402, "detail": v.detail_pour_402()})}
                    return

            yield {"event": "step", "data": json.dumps({"step": "llm", "estimation_s": 30})}
            from modules.enquetes.enquete_ai import generer_etude_et_formulaire_par_prompt
            etude, formulaire, usages = await generer_etude_et_formulaire_par_prompt(
                brief=payload.brief,
                nb_questions_cible=payload.nb_questions_cible,
                profil_cible=payload.profil_cible,
                langue=payload.langue,
            )

            yield {"event": "step", "data": json.dumps({"step": "saving"})}
            try:
                await sauvegarder_etude(etude, current_user.user_id)
            except Exception as e:
                logger.warning(f"[Enquetes/stream] sauvegarde non bloquante : {e}")

            try:
                from modules.bureau.service_credits_bureau import debiter_llm_unifie
                for u in usages:
                    await debiter_llm_unifie(
                        user_id=current_user.user_id,
                        modele=u.get("modele", "claude-sonnet-4-6"),
                        tokens_input=int(u.get("tokens_in", 0)),
                        tokens_output=int(u.get("tokens_out", 0)),
                        module="enquetes_prompt",
                    )
            except Exception:
                pass

            yield {"event": "step", "data": json.dumps({
                "step": "done",
                "etude_id": etude.etude_id,
                "formulaire_id": formulaire.formulaire_id,
                "titre": etude.titre,
                "nb_questions": len(formulaire.questions),
                "lien_public": f"/api/v1/enquetes/public/{formulaire.formulaire_id}/page",
                "lien_xlsform_download": f"/api/v1/enquetes/{etude.etude_id}/formulaire/xlsform",
                "analyses_suggerees": getattr(etude, "analyses_suggerees", []),
            })}
        except Exception as e:
            logger.error(f"[Enquetes/stream] échec user={current_user.user_id}: {e}")
            yield {"event": "step", "data": json.dumps({"step": "error", "detail": str(e)[:300]})}

    # ping=15s pour garder la connexion ouverte derrière les proxies.
    # Import paresseux : sse_starlette est dans requirements.txt mais
    # absent en dev léger, évite de casser les autres routes au boot.
    from sse_starlette.sse import EventSourceResponse
    return EventSourceResponse(_gen(), ping=15)


@router.post(
    "/generer-par-prompt",
    summary="Phase E1 — Génère une étude+formulaire complet depuis un brief en langage naturel",
)
async def generer_par_prompt(
    payload: GenererParPromptRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Pipeline : Sonnet compose étude + formulaire XLSForm-class complet
    (10-40 questions structurées avec relevant/constraint) en un seul appel.

    Retourne {etude_id, formulaire_id, lien_public, lien_xlsform_download,
    analyses_suggerees}.
    """
    await fact.precheck(current_user.user_id)
    await charger_etudes_user(current_user.user_id)

    # CostAdvisor préventif (analyse coûteuse : LLM 12k+ tokens)
    if not payload.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        cout = estimer_cout_module(
            "enquete_generer",
            multiplicateur=(payload.nb_questions_cible or 20) / 20.0,
        )
        v = await advisor.evaluer(
            current_user.user_id, cout, module="enquete_generer",
        )
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    from modules.enquetes.enquete_ai import generer_etude_et_formulaire_par_prompt
    try:
        etude, formulaire, usages = await generer_etude_et_formulaire_par_prompt(
            brief=payload.brief,
            nb_questions_cible=payload.nb_questions_cible,
            profil_cible=payload.profil_cible,
            langue=payload.langue,
        )
    except Exception as e:
        logger.error(f"[Enquetes/prompt] LLM échec user={current_user.user_id}: {e}")
        raise HTTPException(500, f"Erreur génération : {str(e)[:200]}")

    # Persistance + débit LLM. Signature : (etude, user_id) — NE PAS
    # inverser : précédemment l'inversion provoquait des erreurs silencieuses
    # (try/except non bloquant) → études perdues après redémarrage machine
    # scale-to-zero → 404 sur le XLSForm download et le lien public.
    try:
        await sauvegarder_etude(etude, current_user.user_id)
    except Exception as e:
        logger.warning(f"[Enquetes/prompt] sauvegarde non bloquante : {e}")

    try:
        from modules.bureau.service_credits_bureau import debiter_llm_unifie
        for u in usages:
            await debiter_llm_unifie(
                user_id=current_user.user_id,
                modele=u.get("modele", "claude-sonnet-4-6"),
                tokens_input=int(u.get("tokens_in", 0)),
                tokens_output=int(u.get("tokens_out", 0)),
                module="enquetes_prompt",
            )
    except Exception as _e:
        logger.debug(f"[Enquetes/prompt] débit LLM non bloquant : {_e}")

    return {
        "ok": True,
        "etude_id": etude.etude_id,
        "formulaire_id": formulaire.formulaire_id,
        "titre": etude.titre,
        "nb_questions": len(formulaire.questions),
        # Lien public HTML PWA (sert /public/{fid}/page qui rend le formulaire
        # mobile-first responsive offline-first). Le /page final est OBLIGATOIRE
        # — sans lui c'est un 404.
        "lien_public": f"/api/v1/enquetes/public/{formulaire.formulaire_id}/page",
        "lien_xlsform_download": f"/api/v1/enquetes/{etude.etude_id}/formulaire/xlsform",
        "analyses_suggerees": getattr(etude, "analyses_suggerees", []),
    }


# ─── Phase E3 — Suivi temps réel + stats par étude ───────────────────────────


@router.get(
    "/mes-enquetes",
    summary="Phase E3 — Liste détaillée des études du user avec stats temps réel",
)
async def lister_mes_enquetes(
    current_user: TokenData = Depends(get_current_user),
):
    """Pour chaque étude : nb_réponses, dernier_repondant, taux_completion,
    sparkline (compte par jour sur 7 derniers jours), lien public.

    Filtré strictement aux études dont current_user est propriétaire
    (cf `lister_etudes_user`) — ne fuit aucune étude tierce.
    """
    await charger_etudes_user(current_user.user_id)
    from datetime import datetime, timedelta
    from collections import Counter

    out = []
    for etude_meta in ge.lister_etudes_user(current_user.user_id):
        etude_obj = ge.get_etude_user(current_user.user_id, etude_meta["etude_id"])
        if not etude_obj:
            continue

        formulaire = etude_obj.formulaire
        nb_reponses = 0
        dernier_repondant = None
        sparkline = []
        if formulaire and formulaire.reponses:
            reponses = formulaire.reponses
            nb_reponses = len(reponses)
            # Dernier répondant
            dernier_repondant = max(
                (r.get("_timestamp") or r.get("created_at") for r in reponses
                 if isinstance(r, dict)),
                default=None,
            )
            # Sparkline 7 derniers jours
            today = datetime.utcnow().date()
            counts = Counter()
            for r in reponses:
                ts = r.get("_timestamp") if isinstance(r, dict) else None
                if ts:
                    try:
                        d = datetime.fromisoformat(ts.replace("Z", "")).date()
                        if (today - d).days < 7:
                            counts[d.isoformat()] += 1
                    except Exception:
                        pass
            sparkline = [
                {"date": (today - timedelta(days=i)).isoformat(),
                 "n": counts.get((today - timedelta(days=i)).isoformat(), 0)}
                for i in range(6, -1, -1)
            ]

        nb_questions = len(formulaire.questions) if formulaire else 0
        taux_completion_moy = 0
        if formulaire and formulaire.reponses and nb_questions:
            total_complet = sum(
                len([v for v in r.values() if v not in (None, "", [])])
                / nb_questions
                for r in formulaire.reponses if isinstance(r, dict)
            )
            taux_completion_moy = round(
                100 * total_complet / len(formulaire.reponses), 1,
            )

        out.append({
            "etude_id": etude_obj.etude_id,
            "titre": etude_obj.titre,
            "methodologie": getattr(etude_obj, "methodologie", "mixte"),
            "formulaire_id": formulaire.formulaire_id if formulaire else None,
            "nb_questions": nb_questions,
            "nb_reponses": nb_reponses,
            "dernier_repondant": dernier_repondant,
            "taux_completion_pct": taux_completion_moy,
            "sparkline_7j": sparkline,
            "lien_public": (
                f"/api/v1/enquetes/public/{formulaire.formulaire_id}/page"
                if formulaire else None
            ),
            "has_analyse": (
                etude_obj.analyse_qualitative is not None
                or etude_obj.analyse_quantitative is not None
            ),
        })
    out.sort(key=lambda e: e.get("nb_reponses", 0), reverse=True)
    return {"enquetes": out}


# ─── Phase E2 — PWA collecte publique (HTML responsive offline-first) ────────


def _construire_html_formulaire_public(formulaire) -> str:
    """Génère un HTML PWA mobile-first pour le formulaire public.

    Caractéristiques :
      • Mobile-first responsive Tailwind CDN
      • IndexedDB queue offline → resync auto à la reconnexion
      • Honeypot anti-spam + validation côté client
      • Multi-section avec navigation prev/next
      • Géoloc auto si question geopoint
      • Capture photo si question image
    """
    import html as _html

    # Mapping type interne QuestionFormulaire → type attendu par le JS PWA
    _TYPE_PWA = {
        "text": "text", "note": "text",
        "number": "integer", "rating": "integer",
        "select_one": "select_one", "likert": "select_one", "oui_non": "select_one",
        "select_multiple": "select_multiple",
        "date": "date", "geopoint": "geopoint",
        "image": "image",
    }

    questions_json = json.dumps([
        {
            # Clé pandas/CSV/relevant : name_xlsform si dispo, sinon question_id
            "id":    q.name_xlsform or q.question_id,
            "label": q.libelle,
            "hint":  q.hint,
            "type":  _TYPE_PWA.get(q.type_question, "text"),
            "required": q.obligatoire,
            "section":  q.section_label,
            "relevant": q.relevant,
            # Priorise choices_meta (value↔label propre du LLM E1).
            # Fallback options legacy si choices_meta vide.
            "choices":  (q.choices_meta if q.choices_meta else
                         [{"value": str(o), "label": str(o)} for o in (q.options or [])]),
            "constraint": q.constraint,
        }
        for q in formulaire.questions
    ], ensure_ascii=False)
    sections_json = json.dumps(formulaire.sections or [], ensure_ascii=False)
    titre = _html.escape(formulaire.titre)
    desc = _html.escape(formulaire.description or "")
    fid = _html.escape(formulaire.formulaire_id)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>{titre}</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#7B3FE4">
<link rel="manifest" href="/api/v1/enquetes/public/{fid}/manifest.json">
<link rel="icon" type="image/svg+xml" href="/api/v1/enquetes/public/{fid}/icon.svg">
<link rel="apple-touch-icon" href="/api/v1/enquetes/public/{fid}/icon.svg">
<script src="https://cdn.tailwindcss.com"></script>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#f8fafc}}
.input{{width:100%;padding:0.875rem;border:1px solid #cbd5e1;border-radius:0.625rem;font-size:1rem;min-height:48px}}
.input:focus{{outline:0;border-color:#7B3FE4;box-shadow:0 0 0 3px rgba(123,63,228,0.15)}}
.btn-primary{{background:#7B3FE4;color:#fff;padding:0.875rem 1.5rem;border:0;border-radius:0.625rem;font-weight:600;min-height:48px;width:100%;cursor:pointer}}
.btn-secondary{{background:#f1f5f9;color:#0f172a;padding:0.875rem 1.5rem;border:0;border-radius:0.625rem;font-weight:600;min-height:48px;flex:1;cursor:pointer}}
.choice{{display:flex;align-items:center;gap:0.5rem;padding:0.875rem;border:2px solid #e2e8f0;border-radius:0.625rem;margin-bottom:0.5rem;cursor:pointer;min-height:48px}}
.choice:has(:checked){{border-color:#7B3FE4;background:#faf5ff}}
.progress{{height:4px;background:#e2e8f0;border-radius:2px;overflow:hidden}}
.progress-bar{{height:100%;background:#7B3FE4;transition:width 0.3s}}
@media (max-width:640px){{body{{padding:0}}}}
</style>
</head>
<body>
<div class="max-w-2xl mx-auto p-4 md:p-8 min-h-screen">
  <header class="mb-6">
    <h1 class="text-2xl md:text-3xl font-bold text-slate-900 mb-2">{titre}</h1>
    <p class="text-slate-600">{desc}</p>
    <div class="progress mt-4"><div id="progress-bar" class="progress-bar" style="width:0%"></div></div>
  </header>
  <div id="offline-banner" class="hidden mb-4 p-3 rounded-lg bg-amber-100 text-amber-900 text-sm">
    📡 Vous êtes hors-ligne. Vos réponses sont sauvegardées localement et seront envoyées dès la reconnexion.
  </div>
  <main id="form-container"></main>
  <footer id="form-footer" class="flex gap-2 mt-6"></footer>
</div>

<script>
const FID = "{fid}";
const QUESTIONS = {questions_json};
const SECTIONS = {sections_json};
const API_BASE = window.location.origin;
const reponses = {{}};
let currentIdx = 0;

// ── IndexedDB queue offline ──────────────────────────────────────────────
const DB_NAME = "yukpo_form_queue";
const STORE = "submissions";
function openDB() {{
  return new Promise((resolve, reject) => {{
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {{
      req.result.createObjectStore(STORE, {{ keyPath: "id", autoIncrement: true }});
    }};
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  }});
}}
async function enqueue(payload) {{
  try {{
    const db = await openDB();
    await new Promise((resolve, reject) => {{
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).add({{ payload, ts: Date.now() }});
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
    }});
  }} catch (e) {{ console.warn("IndexedDB enqueue failed", e); }}
}}
async function flushQueue() {{
  try {{
    const db = await openDB();
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    const items = await new Promise(r => {{
      const req = store.getAll();
      req.onsuccess = () => r(req.result || []);
    }});
    for (const it of items) {{
      try {{
        const r = await fetch(`${{API_BASE}}/api/v1/enquetes/public/${{FID}}/reponse`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(it.payload),
        }});
        if (r.ok) store.delete(it.id);
      }} catch (e) {{ break; }} // network down → on garde
    }}
  }} catch (e) {{ console.warn("flushQueue failed", e); }}
}}
window.addEventListener("online", () => {{
  document.getElementById("offline-banner").classList.add("hidden");
  flushQueue();
}});
window.addEventListener("offline", () => {{
  document.getElementById("offline-banner").classList.remove("hidden");
}});
if (!navigator.onLine) document.getElementById("offline-banner").classList.remove("hidden");

// ── Render question courante ─────────────────────────────────────────────
// Mini-parser whitelist XLSForm. Remplace Function() pour éliminer le
// XSS stocké : un propriétaire d'étude malveillant pouvait injecter du
// JS arbitraire dans `relevant` exécuté chez chaque répondant.
// Tokens supportés : ${{nom}}, 'literal', "literal", number, true/false,
// == != > >= < <=, and or not, ( ). Tout autre token → faux conservateur.
function evalRelevant(expr) {{
  if (!expr) return true;
  try {{
    const toks = tokenize(expr);
    if (!toks.length) return true;
    const p = {{ i: 0, t: toks }};
    const v = parseOr(p);
    return p.i === toks.length ? !!v : true;
  }} catch (e) {{ return true; }}
}}
function tokenize(s) {{
  const out = [];
  let i = 0;
  const isDigit = c => c >= '0' && c <= '9';
  const isIdStart = c => (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c === '_';
  const isIdPart = c => isIdStart(c) || isDigit(c);
  while (i < s.length) {{
    const c = s[i];
    if (c === ' ' || c === '\\t' || c === '\\n') {{ i++; continue; }}
    if (c === '(' || c === ')') {{ out.push({{ k: c }}); i++; continue; }}
    if (c === '$' && s[i+1] === '{{') {{
      let j = i + 2; while (j < s.length && s[j] !== '}}') j++;
      const name = s.slice(i + 2, j);
      if (!/^[a-zA-Z0-9_]+$/.test(name)) throw 0;
      out.push({{ k: 'var', v: name }});
      i = j + 1; continue;
    }}
    if (c === '\\'' || c === '"') {{
      let j = i + 1; while (j < s.length && s[j] !== c) j++;
      out.push({{ k: 'lit', v: s.slice(i + 1, j) }});
      i = j + 1; continue;
    }}
    if (isDigit(c) || (c === '-' && isDigit(s[i+1]))) {{
      let j = i + 1; while (j < s.length && (isDigit(s[j]) || s[j] === '.')) j++;
      out.push({{ k: 'lit', v: parseFloat(s.slice(i, j)) }});
      i = j; continue;
    }}
    if (c === '=' || c === '!' || c === '<' || c === '>') {{
      let op = c;
      if (s[i+1] === '=') {{ op += '='; i += 2; }} else {{ i++; }}
      if (op === '=') op = '==';
      out.push({{ k: 'op', v: op }});
      continue;
    }}
    if (isIdStart(c)) {{
      let j = i + 1; while (j < s.length && isIdPart(s[j])) j++;
      const w = s.slice(i, j).toLowerCase();
      if (w === 'and' || w === 'or' || w === 'not') out.push({{ k: w }});
      else if (w === 'true')  out.push({{ k: 'lit', v: true }});
      else if (w === 'false') out.push({{ k: 'lit', v: false }});
      else throw 0;
      i = j; continue;
    }}
    throw 0;
  }}
  return out;
}}
function peek(p, k) {{ return p.i < p.t.length && p.t[p.i].k === k; }}
function eat(p, k) {{ if (!peek(p, k)) throw 0; return p.t[p.i++]; }}
function parseOr(p) {{
  let v = parseAnd(p);
  while (peek(p, 'or')) {{ p.i++; v = parseAnd(p) || v; }}
  return v;
}}
function parseAnd(p) {{
  let v = parseCmp(p);
  while (peek(p, 'and')) {{ p.i++; const r = parseCmp(p); v = v && r; }}
  return v;
}}
function parseCmp(p) {{
  const a = parseAtom(p);
  if (peek(p, 'op')) {{
    const op = eat(p, 'op').v;
    const b = parseAtom(p);
    if (op === '==') return a == b;
    if (op === '!=') return a != b;
    if (op === '>')  return Number(a) >  Number(b);
    if (op === '>=') return Number(a) >= Number(b);
    if (op === '<')  return Number(a) <  Number(b);
    if (op === '<=') return Number(a) <= Number(b);
    throw 0;
  }}
  return a;
}}
function parseAtom(p) {{
  if (peek(p, 'not')) {{ p.i++; return !parseAtom(p); }}
  if (peek(p, '(')) {{ p.i++; const v = parseOr(p); eat(p, ')'); return v; }}
  if (peek(p, 'lit')) return p.t[p.i++].v;
  if (peek(p, 'var')) {{
    const name = p.t[p.i++].v;
    const v = reponses[name];
    return Array.isArray(v) ? v.join(',') : (v == null ? '' : v);
  }}
  throw 0;
}}

function renderQuestion() {{
  // skip questions dont relevant=false
  while (currentIdx < QUESTIONS.length && !evalRelevant(QUESTIONS[currentIdx].relevant)) {{
    currentIdx++;
  }}
  if (currentIdx >= QUESTIONS.length) return renderFinal();
  const q = QUESTIONS[currentIdx];
  const ctn = document.getElementById("form-container");

  document.getElementById("progress-bar").style.width =
    ((currentIdx / QUESTIONS.length) * 100) + "%";

  let inputHtml = "";
  const val = reponses[q.id] || "";
  if (q.type === "select_one") {{
    inputHtml = q.choices.map(c =>
      `<label class="choice"><input type="radio" name="${{q.id}}" value="${{c.value}}" ${{val === c.value ? "checked" : ""}}><span>${{c.label}}</span></label>`
    ).join("");
  }} else if (q.type === "select_multiple") {{
    const vals = Array.isArray(val) ? val : [];
    inputHtml = q.choices.map(c =>
      `<label class="choice"><input type="checkbox" name="${{q.id}}" value="${{c.value}}" ${{vals.includes(c.value) ? "checked" : ""}}><span>${{c.label}}</span></label>`
    ).join("");
  }} else if (q.type === "integer" || q.type === "decimal") {{
    inputHtml = `<input type="number" name="${{q.id}}" value="${{val}}" class="input" ${{q.type === "decimal" ? 'step="0.01"' : ""}}>`;
  }} else if (q.type === "date") {{
    inputHtml = `<input type="date" name="${{q.id}}" value="${{val}}" class="input">`;
  }} else if (q.type === "time") {{
    inputHtml = `<input type="time" name="${{q.id}}" value="${{val}}" class="input">`;
  }} else if (q.type === "image") {{
    inputHtml = `<input type="file" name="${{q.id}}" accept="image/*" capture="environment" class="input">`;
  }} else if (q.type === "audio") {{
    inputHtml = `<input type="file" name="${{q.id}}" accept="audio/*" capture="user" class="input">`;
  }} else if (q.type === "geopoint") {{
    inputHtml = `<button type="button" id="geo-btn" class="btn-secondary">📍 Capturer ma position</button><input type="hidden" name="${{q.id}}" id="geo-input" value="${{val}}">`;
  }} else {{
    inputHtml = `<textarea name="${{q.id}}" class="input" rows="4">${{val}}</textarea>`;
  }}

  ctn.innerHTML = `
    <div class="bg-white rounded-xl shadow-md p-5 mb-4">
      <p class="text-xs uppercase tracking-wider text-violet-600 font-semibold mb-1">${{q.section || "Question"}}</p>
      <h2 class="text-xl font-bold text-slate-900 mb-2">${{q.label}}${{q.required ? ' <span class="text-rose-500">*</span>' : ""}}</h2>
      ${{q.hint ? `<p class="text-sm text-slate-500 mb-3">${{q.hint}}</p>` : ""}}
      <div class="mt-4">${{inputHtml}}</div>
      <p class="text-xs text-slate-400 mt-3">Question ${{currentIdx + 1}}/${{QUESTIONS.length}}</p>
    </div>
  `;
  document.getElementById("form-footer").innerHTML = `
    ${{currentIdx > 0 ? '<button type="button" class="btn-secondary" id="btn-prev">← Précédent</button>' : ""}}
    <button type="button" class="btn-primary" id="btn-next">${{currentIdx === QUESTIONS.length - 1 ? "Envoyer" : "Suivant →"}}</button>
  `;
  if (currentIdx > 0) document.getElementById("btn-prev").onclick = () => {{ currentIdx--; renderQuestion(); }};
  document.getElementById("btn-next").onclick = onNext;

  if (q.type === "geopoint") {{
    document.getElementById("geo-btn").onclick = () => {{
      if (!navigator.geolocation) return alert("Géolocalisation non disponible");
      navigator.geolocation.getCurrentPosition(
        p => {{
          const v = `${{p.coords.latitude}},${{p.coords.longitude}}`;
          document.getElementById("geo-input").value = v;
          document.getElementById("geo-btn").textContent = `✓ ${{v}}`;
        }},
        err => alert("Erreur géolocalisation: " + err.message),
        {{ enableHighAccuracy: true, timeout: 10000 }}
      );
    }};
  }}
}}

function onNext() {{
  const q = QUESTIONS[currentIdx];
  let val;
  if (q.type === "select_multiple") {{
    val = [...document.querySelectorAll(`input[name="${{q.id}}"]:checked`)].map(i => i.value);
  }} else if (q.type === "select_one") {{
    const r = document.querySelector(`input[name="${{q.id}}"]:checked`);
    val = r ? r.value : null;
  }} else {{
    const el = document.querySelector(`[name="${{q.id}}"]`);
    val = el ? el.value : null;
  }}
  if (q.required && (val === null || val === "" || (Array.isArray(val) && !val.length))) {{
    return alert("Cette question est obligatoire.");
  }}
  reponses[q.id] = val;
  currentIdx++;
  renderQuestion();
}}

async function renderFinal() {{
  const ctn = document.getElementById("form-container");
  document.getElementById("progress-bar").style.width = "100%";
  ctn.innerHTML = `<div class="bg-white rounded-xl shadow-md p-8 text-center">
    <div class="text-5xl mb-3">⏳</div>
    <h2 class="text-xl font-bold mb-2">Envoi en cours…</h2></div>`;
  document.getElementById("form-footer").innerHTML = "";

  const payload = {{ formulaire_id: FID, reponses, _hp_bot: "" }};
  try {{
    if (navigator.onLine) {{
      const r = await fetch(`${{API_BASE}}/api/v1/enquetes/public/${{FID}}/reponse`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload),
      }});
      if (!r.ok) throw new Error("HTTP " + r.status);
    }} else {{
      await enqueue(payload);
    }}
    ctn.innerHTML = `<div class="bg-emerald-50 border-2 border-emerald-200 rounded-xl p-8 text-center">
      <div class="text-5xl mb-3">✅</div>
      <h2 class="text-2xl font-bold text-emerald-900 mb-2">Merci !</h2>
      <p class="text-slate-700">Votre réponse a été enregistrée${{navigator.onLine ? "" : " hors-ligne (envoi automatique à la reconnexion)"}}.</p>
    </div>`;
  }} catch (e) {{
    await enqueue(payload);
    ctn.innerHTML = `<div class="bg-amber-50 rounded-xl p-8 text-center">
      <div class="text-5xl mb-3">📡</div>
      <h2 class="text-xl font-bold mb-2">Sauvegardé hors-ligne</h2>
      <p class="text-slate-700">Pas de réseau actuellement — envoi automatique dès reconnexion.</p>
    </div>`;
  }}
}}

renderQuestion();
flushQueue();

// Enregistre le service worker — cache HTML+assets pour vrai offline
// (les POST réponses restent gérées par la queue IndexedDB ci-dessus).
if ("serviceWorker" in navigator) {{
  navigator.serviceWorker.register("/api/v1/enquetes/public/{fid}/sw.js")
    .catch(e => console.warn("SW register failed", e));
}}
</script>
</body>
</html>
"""


@router.get(
    "/public/{formulaire_id}/page",
    response_class=HTMLResponse,
    summary="Phase E2 — HTML PWA mobile-first responsive offline-first du formulaire",
)
async def page_formulaire_public(formulaire_id: str):
    """Sert le HTML PWA du formulaire. PUBLIC (pas d'auth)."""
    formulaire = await ge.get_formulaire_public(formulaire_id)
    if not formulaire:
        raise HTTPException(404, "Formulaire introuvable")
    return HTMLResponse(_construire_html_formulaire_public(formulaire))


# ─── P2 #6 — PWA assets (manifest + icons SVG + service worker) ────────────
# Chrome accepte SVG comme icon depuis 2021 (purpose="any maskable"). Pas
# besoin de générer du PNG. Le SW est minimal (cache GET HTML + assets pour
# vrai offline-first ; les POST passent par IndexedDB queue déjà en place).

_PWA_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
    '<rect width="512" height="512" fill="#7B3FE4" rx="80"/>'
    '<text x="256" y="335" text-anchor="middle" font-family="system-ui,sans-serif" '
    'font-size="280" font-weight="700" fill="white">Y</text>'
    '</svg>'
)


@router.get(
    "/public/{formulaire_id}/manifest.json",
    summary="PWA manifest (installable Android Chrome / iOS Safari)",
)
async def manifest_pwa(formulaire_id: str):
    """Manifest installable. Icons SVG (any + maskable) — Chrome OK."""
    formulaire = await ge.get_formulaire_public(formulaire_id)
    if not formulaire:
        raise HTTPException(404, "Formulaire introuvable")
    icon_url = f"/api/v1/enquetes/public/{formulaire_id}/icon.svg"
    return {
        "name": formulaire.titre or "Formulaire Yukpo",
        "short_name": (formulaire.titre or "Form")[:12],
        "start_url": f"/api/v1/enquetes/public/{formulaire_id}/page",
        "scope": f"/api/v1/enquetes/public/{formulaire_id}/",
        "display": "standalone",
        "orientation": "portrait",
        "theme_color": "#7B3FE4",
        "background_color": "#ffffff",
        "icons": [
            {"src": icon_url, "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
            {"src": icon_url, "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"},
        ],
    }


@router.get(
    "/public/{formulaire_id}/icon.svg",
    summary="Icône PWA SVG (cachable 1 an)",
)
async def icon_pwa(formulaire_id: str):
    return Response(
        content=_PWA_ICON_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get(
    "/public/{formulaire_id}/sw.js",
    summary="Service worker minimal (cache HTML + assets pour vrai offline)",
)
async def service_worker(formulaire_id: str):
    """SW : cache GET (page HTML, manifest, icon, Tailwind CDN) → ouvre la
    page hors-ligne. Les POST réponses passent par IndexedDB queue déjà en
    place dans le HTML PWA.
    """
    page_url = f"/api/v1/enquetes/public/{formulaire_id}/page"
    manifest_url = f"/api/v1/enquetes/public/{formulaire_id}/manifest.json"
    icon_url = f"/api/v1/enquetes/public/{formulaire_id}/icon.svg"
    sw = f"""
const CACHE = "yukpo-form-{formulaire_id}-v1";
const ASSETS = [
  "{page_url}",
  "{manifest_url}",
  "{icon_url}",
  "https://cdn.tailwindcss.com",
];
self.addEventListener("install", e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS).catch(()=>null)));
  self.skipWaiting();
}});
self.addEventListener("activate", e => {{
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
}});
self.addEventListener("fetch", e => {{
  if (e.request.method !== "GET") return; // POST passent direct (queue IDB)
  e.respondWith(
    caches.match(e.request).then(hit =>
      hit || fetch(e.request).then(r => {{
        if (r.ok) {{
          const clone = r.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone)).catch(()=>null);
        }}
        return r;
      }}).catch(() => hit || new Response("Offline", {{ status: 503 }}))
    )
  );
}});
"""
    return Response(
        content=sw, media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


class SoumettreReponseRequest(BaseModel):
    formulaire_id: str
    reponses: dict
    _hp_bot: Optional[str] = ""


@router.post(
    "/public/{formulaire_id}/reponse",
    summary="Phase E2 — Endpoint public d'ingestion réponses (no auth, honeypot)",
)
async def soumettre_reponse_publique(
    formulaire_id: str,
    payload: SoumettreReponseRequest,
    request: Request,
):
    """Reçoit les réponses depuis le HTML public ou la queue IndexedDB.

    INSERT atomique dans `enquetes_reponses` (P2 #4) — pas de race
    read-modify-write sur le JSON blob de EtudeDB.data. Le cache RAM
    `etude.formulaire.reponses` est aussi mis à jour pour cohérence
    avec les analyses en cours (qui lisent encore depuis la RAM).
    """
    # Honeypot
    if payload._hp_bot:
        logger.info(f"[Enquetes/public] honeypot trigger {formulaire_id}")
        return {"ok": True}

    # Rate-limit IP : 20 réponses/min/IP (un répondant honnête en soumet 1).
    # Le honeypot seul est trivial à contourner ; combiner avec un quota IP
    # bloque les bots qui essaient de noyer les analyses.
    client_ip = request.client.host if request.client else "anon"
    if not _rate_limit_ok(client_ip, formulaire_id):
        raise HTTPException(429, "Trop de soumissions. Patientez 1 minute.")

    formulaire = await ge.get_formulaire_public(formulaire_id)
    if not formulaire:
        raise HTTPException(404, "Formulaire introuvable")

    etude_id_for_form = ge._formulaires_publics.get(formulaire_id)
    if not etude_id_for_form:
        raise HTTPException(404, "Formulaire introuvable")

    # Hash IP (pas IP brute — anti-spam analytics sans tracking nominatif)
    import hashlib as _hl
    ip_hash = _hl.sha256(client_ip.encode()).hexdigest()[:32]
    ua = (request.headers.get("user-agent") or "")[:300]

    # INSERT atomique table dédiée
    reponses_data = dict(payload.reponses)
    reponses_data["_soumis_le"] = datetime.utcnow().isoformat()
    try:
        from core.database import async_session_maker, EnqueteReponseDB
        async with async_session_maker() as session:
            session.add(EnqueteReponseDB(
                formulaire_id=formulaire_id,
                etude_id=etude_id_for_form,
                reponses=reponses_data,
                ip_hash=ip_hash,
                user_agent=ua,
            ))
            await session.commit()
    except Exception as e:
        logger.warning(f"[Enquetes/public] INSERT DB échoué (fallback RAM): {e}")

    # Mirror RAM pour les analyses en cours dans la même process
    success = ge.soumettre_reponse(formulaire_id, reponses_data)
    if not success:
        raise HTTPException(400, "Réponse invalide")

    # Débit forfait sur le marchand propriétaire (lookup direct via ownership)
    try:
        owner_id = ge._etude_owner.get(etude_id_for_form)
        if owner_id:
            from modules.bureau.service_credits_bureau import debiter_forfait_unifie
            await debiter_forfait_unifie(
                owner_id, "client_action",
                module="enquete_reponse",
            )
    except Exception:
        pass

    return {"ok": True}


# ─── Phase E4 — Analyse à la demande par PROMPT ──────────────────────────────


class AnalyserParPromptRequest(BaseModel):
    prompt: str
    confirmer_cout: bool = False
    # True → injecter l'historique des analyses précédentes de l'étude
    # dans le prompt LLM. UX : "compare maintenant par genre" → Sonnet sait
    # à quoi se réfère "compare" sans qu'on répète tout le contexte.
    avec_historique: bool = False


@router.post(
    "/{etude_id}/analyser-prompt",
    summary="Phase E4 — Analyse conversationnelle (LLM plan + pandas + charts + synthèse)",
)
async def analyser_par_prompt_endpoint(
    etude_id: str,
    payload: AnalyserParPromptRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Pipeline : Sonnet compose un plan JSON d'opérations pandas
    (filter/groupby/agg/chart/llm_synthese), backend exécute en sandbox,
    génère graphiques PNG + synthèse Sonnet finale.

    Retourne {titre_analyse, tableaux, graphiques, synthese_md, plan_execute}.
    """
    await fact.precheck(current_user.user_id)
    await charger_etudes_user(current_user.user_id)
    # Garde-fou ownership AVANT toute opération coûteuse / LLM
    _etude_owner_ou_404(etude_id, current_user.user_id)

    # CostAdvisor — coût varie selon complexité (simple vs complexe)
    if not payload.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        # Estimation par défaut "complexe" (sécurité — on préfère que le
        # user confirme une analyse cher plutôt que d'être surpris)
        cout = estimer_cout_module("enquete_analyse_complexe")
        v = await advisor.evaluer(
            current_user.user_id, cout, module="enquete_analyse_complexe",
        )
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    from modules.enquetes.enquete_ai import analyser_par_prompt
    historique = None
    if payload.avec_historique:
        etude_ref = ge.get_etude(etude_id)
        historique = getattr(etude_ref, "analyses_prompt_results", None) or []
    try:
        resultat = await analyser_par_prompt(etude_id, payload.prompt, historique=historique)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"[Enquetes/analyse-prompt] échec user={current_user.user_id}: {e}")
        raise HTTPException(500, f"Erreur analyse : {str(e)[:200]}")

    # Phase E5 — stocke le résultat sur l'étude pour intégration au rapport final
    try:
        from datetime import datetime as _dt
        etude_obj = ge.get_etude(etude_id)
        if etude_obj is not None:
            if not hasattr(etude_obj, "analyses_prompt_results") or etude_obj.analyses_prompt_results is None:
                etude_obj.analyses_prompt_results = []
            etude_obj.analyses_prompt_results.append({
                "prompt": payload.prompt,
                "ts": _dt.utcnow().isoformat(),
                "titre": resultat.get("titre_analyse"),
                "description": resultat.get("description"),
                "tableaux": resultat.get("tableaux", []),
                "graphiques_keys": list((resultat.get("graphiques") or {}).keys()),
                "synthese_md": resultat.get("synthese_md"),
                "n_reponses_analyses": resultat.get("n_reponses_analyses"),
            })
            # Fusionne les graphiques dans le store global de l'étude pour le rapport
            for k, b64 in (resultat.get("graphiques") or {}).items():
                etude_obj.graphiques[f"analyse_prompt_{k}"] = b64
    except Exception as _e:
        logger.debug(f"[Enquetes/analyse-prompt] storage analyse non bloquant : {_e}")

    # Débit forfait existant `pdf_generation` (sémantique : artefact analytique)
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "pdf_generation",
            module="enquetes_analyse_prompt",
        )
    except Exception:
        pass

    return {"ok": True, **resultat}


# ─── Études — CRUD ────────────────────────────────────────────────────────────

@router.post("/", summary="Créer une nouvelle étude")
async def creer_etude(
    payload: NouvelleEtudeRequest,
    current_user: TokenData = Depends(get_current_user),
):
    await fact.precheck(current_user.user_id)
    await charger_etudes_user(current_user.user_id)
    try:
        etude = ge.creer_etude(
            titre=payload.titre,
            contexte=payload.contexte,
            questions_recherche=payload.questions_recherche,
            methodologie=payload.methodologie,
            population_cible=payload.population_cible,
            terrain=payload.terrain,
            mode=payload.mode,
        )
    except Exception:
        logger.exception(f"[Enquêtes] Échec création étude user={current_user.user_id}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne lors de la création")
    await sauvegarder_etude(etude, current_user.user_id)
    await fact.debiter(current_user.user_id, "etude_create")
    return {
        "etude_id": etude.etude_id,
        "titre": etude.titre,
        "mode": etude.mode,
        "statut": etude.statut,
        "message": "Étude créée. Uploadez vos audios ou créez un formulaire de collecte.",
    }


class DupliquerEtudeRequest(BaseModel):
    nouveau_titre: Optional[str] = None


class InviterRepondantsRequest(BaseModel):
    """Diffusion du lien public d'un formulaire à une liste de contacts."""
    telephones: list[str] = []  # numéros WhatsApp internationaux (+237...)
    emails: list[str] = []
    message: Optional[str] = None  # texte personnalisé optionnel


@router.post(
    "/{etude_id}/inviter",
    summary="Diffuser le lien public du formulaire par WhatsApp / Email (infra Yukpo)",
)
async def inviter_repondants(
    etude_id: str,
    payload: InviterRepondantsRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
):
    """Envoie le lien public à N contacts (WhatsApp + email). Utilise
    l'infra notifications Yukpo existante (Twilio + SendGrid).
    Retourne le compte par canal et les destinataires en échec.
    """
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    if not etude.formulaire:
        raise HTTPException(400, "Cette étude n'a pas de formulaire — créez-en un d'abord.")
    await fact.precheck(current_user.user_id)

    base = str(request.base_url).rstrip("/")
    lien_public = f"{base}/api/v1/enquetes/public/{etude.formulaire.formulaire_id}/page"
    texte = payload.message or (
        f"Bonjour, votre avis nous intéresse pour l'étude « {etude.titre} ». "
        f"Répondez en ~3 minutes : {lien_public}"
    )
    # S'assurer que le lien est dans le texte même si l'user le sort
    if lien_public not in texte:
        texte = texte.rstrip(".!? ") + f"\n\n{lien_public}"

    from core.notifications import envoyer_whatsapp, _envoyer_email

    wa_ok, wa_fail = 0, []
    for tel in payload.telephones:
        tel = (tel or "").strip()
        if not tel:
            continue
        try:
            if await envoyer_whatsapp(tel, texte, metadata={"etude_id": etude_id}):
                wa_ok += 1
            else:
                wa_fail.append(tel)
        except Exception as e:
            logger.warning(f"[Enquetes/inviter] WhatsApp {tel} : {e}")
            wa_fail.append(tel)

    em_ok, em_fail = 0, []
    sujet = f"Enquête « {etude.titre[:60]} » — votre avis compte"
    for em in payload.emails:
        em = (em or "").strip()
        if not em:
            continue
        try:
            if await _envoyer_email(em, texte, sujet=sujet):
                em_ok += 1
            else:
                em_fail.append(em)
        except Exception as e:
            logger.warning(f"[Enquetes/inviter] Email {em} : {e}")
            em_fail.append(em)

    # Débit forfait par invitation envoyée (sémantique : whatsapp_message
    # pour les WA, client_action pour les emails — cohérent avec les autres
    # modules de notif Yukpo)
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        for _ in range(wa_ok):
            await debiter_forfait_unifie(current_user.user_id, "whatsapp_message", module="enquete_invitation")
        for _ in range(em_ok):
            await debiter_forfait_unifie(current_user.user_id, "client_action", module="enquete_invitation_email")
    except Exception:
        pass

    return {
        "lien_public": lien_public,
        "whatsapp_ok": wa_ok, "whatsapp_echecs": wa_fail,
        "email_ok": em_ok, "email_echecs": em_fail,
        "message": f"{wa_ok + em_ok} invitation(s) envoyée(s).",
    }


@router.post("/{etude_id}/dupliquer", summary="Dupliquer une étude (wave 2 NPS, audit répété)")
async def dupliquer_etude_endpoint(
    etude_id: str,
    payload: Optional[DupliquerEtudeRequest] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Crée une copie de l'étude (formulaire + dictionnaire + plan d'analyse)
    avec un nouveau etude_id et un formulaire_id frais. Les réponses,
    transcriptions et analyses NE sont PAS copiées (campagne neuve).
    """
    _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)
    clone = ge.dupliquer_etude(etude_id, payload.nouveau_titre if payload else None)
    if not clone:
        raise HTTPException(404, "Étude introuvable")
    await sauvegarder_etude(clone, current_user.user_id)
    await fact.debiter(current_user.user_id, "etude_create")
    return {
        "etude_id": clone.etude_id,
        "titre": clone.titre,
        "formulaire_id": clone.formulaire.formulaire_id if clone.formulaire else None,
        "n_questions": len(clone.formulaire.questions) if clone.formulaire else 0,
        "message": "Étude dupliquée — campagne prête à diffuser.",
    }


@router.get("/", summary="Lister toutes les études")
async def lister_etudes(current_user: TokenData = Depends(get_current_user)):
    # Charger les études de cet utilisateur depuis la DB si pas encore en RAM
    await charger_etudes_user(current_user.user_id)
    await fact.debiter(current_user.user_id, "etude_list")
    return {"etudes": ge.lister_etudes_user(current_user.user_id)}


@router.get("/{etude_id}", summary="Détails d'une étude")
async def get_etude(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.debiter(current_user.user_id, "etude_get")
    return {
        "etude_id": etude.etude_id,
        "titre": etude.titre,
        "contexte": etude.contexte,
        "questions_recherche": etude.questions_recherche,
        "methodologie": etude.methodologie,
        "population_cible": etude.population_cible,
        "terrain": etude.terrain,
        "mode": etude.mode,
        "statut": etude.statut,
        "n_transcriptions": len(etude.transcriptions),
        "n_themes": len(etude.themes),
        "n_reponses": len(etude.formulaire.reponses) if etude.formulaire else 0,
        "has_analyse": etude.analyse_qualitative is not None or etude.analyse_quantitative is not None,
        "has_rapport": etude.rapport_genere is not None,
        "graphiques_disponibles": list(etude.graphiques.keys()),
    }


# ─── Upload audio + transcription ─────────────────────────────────────────────

@router.post("/{etude_id}/audio", summary="Uploader et transcrire un audio de terrain")
async def uploader_audio(
    etude_id: str,
    audio: UploadFile = File(...),
    locuteur: str = Form("Répondant"),
    date_collecte: Optional[str] = Form(None),
    langue: str = Form("fr"),
    current_user: TokenData = Depends(get_current_user),
):
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)

    contenu = await audio.read()
    mime = audio.content_type or "audio/mpeg"

    if len(contenu) == 0:
        raise HTTPException(400, "Fichier audio vide")

    try:
        transcription = await ge.transcrire_audio(
            contenu=contenu,
            nom_fichier=audio.filename or "audio.m4a",
            mime=mime,
            locuteur=locuteur,
            date_collecte=date_collecte,
            langue=langue,
        )
        etude.transcriptions.append(transcription)
        etude.statut = "transcription"
        await sauvegarder_etude(etude, current_user.user_id)
        await fact.debiter(current_user.user_id, "audio_transcription")

        return {
            "locuteur": transcription.locuteur,
            "fichier": transcription.fichier_nom,
            "duree_estimee_min": transcription.duree_estimee_min,
            "extrait": transcription.transcription[:300] + "…" if len(transcription.transcription) > 300 else transcription.transcription,
            "longueur_totale": len(transcription.transcription),
            "n_transcriptions_total": len(etude.transcriptions),
            "message": "Transcription réussie. Uploadez d'autres audios ou lancez l'analyse.",
        }
    except Exception as e:
        raise HTTPException(500, f"Erreur transcription : {e}")


@router.get("/{etude_id}/transcriptions", summary="Lister les transcriptions d'une étude")
async def lister_transcriptions(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.debiter(current_user.user_id, "transcription_list")
    return {
        "etude_id": etude_id,
        "n_transcriptions": len(etude.transcriptions),
        "transcriptions": [
            {
                "locuteur": t.locuteur,
                "fichier": t.fichier_nom,
                "date_collecte": t.date_collecte,
                "duree_estimee_min": t.duree_estimee_min,
                "extrait": t.transcription[:200] + "…",
                "longueur": len(t.transcription),
            }
            for t in etude.transcriptions
        ],
    }


# ─── Analyse qualitative ───────────────────────────────────────────────────────

@router.post("/{etude_id}/analyser", summary="Lancer l'analyse qualitative IA (codage thématique)")
async def analyser(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)

    try:
        if etude.mode in ("qualitatif", "mixte"):
            analyse = await ge.analyser_qualitatif(etude_id)
            await fact.debiter(current_user.user_id, "analyse_qualitative")
        elif etude.mode == "quantitatif":
            analyse = await ge.analyser_quantitatif(etude_id)
            await fact.debiter(current_user.user_id, "analyse_quantitative")
        else:
            analyse = {}

        await sauvegarder_etude(etude, current_user.user_id)
        return {
            "statut": "analyse_terminee",
            "n_themes": len(etude.themes),
            "graphiques": list(etude.graphiques.keys()),
            "saturation": analyse.get("saturation_atteinte"),
            "message": "Analyse terminée. Générez maintenant le rapport complet.",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse : {e}")


@router.post("/{etude_id}/analyser-quantitatif", summary="Analyse statistique des données collectées")
async def analyser_quantitatif(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    await fact.precheck(current_user.user_id)
    try:
        resultats = await ge.analyser_quantitatif(etude_id)
        etude = ge.get_etude(etude_id)
        if etude:
            await sauvegarder_etude(etude, current_user.user_id)
        await fact.debiter(current_user.user_id, "analyse_quantitative")
        return {
            "statut": "analyse_quantitative_terminee",
            "n_reponses": resultats.get("n_reponses", 0),
            "n_questions_analysees": len(resultats.get("questions", [])),
            "graphiques": list(etude.graphiques.keys()) if etude else [],
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse quantitative : {e}")


# ─── Rapport ──────────────────────────────────────────────────────────────────

@router.post("/{etude_id}/rapport", summary="Générer le rapport complet (qualitative + graphiques)")
async def generer_rapport(
    etude_id: str,
    format_rapport: str = "json",  # json | docx | pdf
    current_user: TokenData = Depends(get_current_user),
):
    if format_rapport not in ("json", "docx", "pdf"):
        raise HTTPException(400, "Format invalide : json | docx | pdf")
    await fact.precheck(current_user.user_id)
    try:
        rapport = await ge.generer_rapport(etude_id, format_rapport)
        await fact.debiter(current_user.user_id, "rapport")
        etude = ge.get_etude(etude_id)
        if etude:
            await sauvegarder_etude(etude, current_user.user_id)
        # Persister rapport DOCX/PDF dans Mes Documents
        titre = etude.titre if etude else "rapport"
        try:
            if format_rapport == "docx" and rapport.get("fichier_docx"):
                content = base64.b64decode(rapport["fichier_docx"])
                fichier_id = _save_bureau(current_user.user_id, "rapport", titre, "docx", content)
                rapport["fichier_id_bureau"] = fichier_id
            elif format_rapport == "pdf" and rapport.get("fichier_pdf"):
                content = base64.b64decode(rapport["fichier_pdf"])
                fichier_id = _save_bureau(current_user.user_id, "rapport", titre, "pdf", content)
                rapport["fichier_id_bureau"] = fichier_id
        except Exception:
            pass
        return rapport
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération rapport : {e}")


@router.get("/{etude_id}/rapport", summary="Récupérer le dernier rapport généré")
async def get_rapport(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    if not etude.rapport_genere:
        raise HTTPException(404, "Aucun rapport généré — POST /rapport d'abord")
    await fact.debiter(current_user.user_id, "rapport_get")
    return etude.rapport_genere


# ─── Formulaire de collecte quantitative ──────────────────────────────────────

@router.post("/{etude_id}/formulaire", summary="Créer un formulaire de collecte de données")
async def creer_formulaire(
    etude_id: str,
    payload: NouveauFormulaireRequest,
    current_user: TokenData = Depends(get_current_user),
):
    await fact.precheck(current_user.user_id)
    try:
        form = ge.creer_formulaire(
            etude_id=etude_id,
            titre=payload.titre,
            description=payload.description,
            questions=[q.model_dump() for q in payload.questions],
        )
        etude = ge.get_etude(etude_id)
        if etude:
            await sauvegarder_etude(etude, current_user.user_id)
        await fact.debiter(current_user.user_id, "formulaire_create")
        return {
            "formulaire_id": form.formulaire_id,
            "titre": form.titre,
            "n_questions": len(form.questions),
            "lien_collecte": f"/api/v1/enquetes/formulaire/{form.formulaire_id}",
            "message": "Formulaire créé. Partagez le lien de collecte aux répondants.",
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/formulaire/{formulaire_id}", summary="Afficher un formulaire (public — sans auth)")
async def afficher_formulaire(formulaire_id: str):
    """Endpoint public — les répondants accèdent sans authentification."""
    form = await ge.get_formulaire_public(formulaire_id)
    if not form or not form.actif:
        raise HTTPException(404, "Formulaire introuvable ou fermé")
    return {
        "formulaire_id": form.formulaire_id,
        "titre": form.titre,
        "description": form.description,
        "questions": [
            {
                "question_id": q.question_id,
                "libelle": q.libelle,
                "type_question": q.type_question,
                "options": q.options,
                "obligatoire": q.obligatoire,
                "ordre": q.ordre,
                "hint": q.hint,
                "section_id": q.section_id,
                "section_label": q.section_label,
                "relevant": q.relevant,
                "constraint": q.constraint,
                "constraint_message": q.constraint_message,
                "appearance": q.appearance,
                "parameters": q.parameters,
                "name_xlsform": q.name_xlsform,
            }
            for q in sorted(form.questions, key=lambda x: x.ordre)
        ],
    }


@router.put("/formulaire/{formulaire_id}/structure", summary="Mettre à jour la structure d'un formulaire")
async def maj_formulaire(
    formulaire_id: str,
    payload: MajFormulaireRequest,
    current_user: TokenData = Depends(get_current_user),
):
    await fact.precheck(current_user.user_id)
    form = ge.mettre_a_jour_formulaire(
        formulaire_id=formulaire_id,
        titre=payload.titre,
        description=payload.description,
        actif=payload.actif,
        questions=[q.model_dump() for q in payload.questions],
    )
    if not form:
        raise HTTPException(404, "Formulaire introuvable")
    # Retrouver l'étude parente et persister
    etude_id_for_form = ge._formulaires_publics.get(formulaire_id)
    if etude_id_for_form:
        etude = ge.get_etude(etude_id_for_form)
        if etude:
            await sauvegarder_etude(etude, current_user.user_id)
    await fact.debiter(current_user.user_id, "formulaire_maj")
    return {
        "formulaire_id": form.formulaire_id,
        "titre": form.titre,
        "description": form.description,
        "actif": form.actif,
        "n_questions": len(form.questions),
        "message": "Formulaire mis à jour.",
    }


@router.post("/formulaire/{formulaire_id}/soumettre", summary="Soumettre des réponses (public — sans auth)")
async def soumettre_reponses(formulaire_id: str, reponses: dict):
    """Endpoint public — soumission de réponses par un répondant."""
    ok = ge.soumettre_reponse(formulaire_id, reponses)
    if not ok:
        raise HTTPException(404, "Formulaire introuvable ou fermé")
    # Persister la nouvelle réponse (endpoint public — pas de user_id, on cherche le propriétaire)
    from core.database import async_session_maker, EtudeDB
    from sqlalchemy import select as _sel
    etude_id_for_form = ge._formulaires_publics.get(formulaire_id)
    if etude_id_for_form:
        etude = ge.get_etude(etude_id_for_form)
        if etude:
            try:
                async with async_session_maker() as _s:
                    _row = (await _s.execute(
                        _sel(EtudeDB).where(EtudeDB.etude_id == etude_id_for_form)
                    )).scalars().first()
                    owner_id = _row.user_id if _row else 0
                if owner_id:
                    await sauvegarder_etude(etude, owner_id)
            except Exception:
                pass
    return {"message": "Réponses enregistrées. Merci pour votre participation."}


@router.get("/{etude_id}/formulaire/donnees", summary="Voir les données collectées")
async def donnees_formulaire(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    if not etude.formulaire:
        raise HTTPException(404, "Aucun formulaire créé pour cette étude")
    await fact.debiter(current_user.user_id, "formulaire_donnees")
    return {
        "formulaire_id": etude.formulaire.formulaire_id,
        "n_reponses": len(etude.formulaire.reponses),
        "reponses": etude.formulaire.reponses,
    }


@router.get(
    "/{etude_id}/formulaire/donnees.csv",
    summary="Exporter les réponses collectées au format CSV",
    response_class=Response,
)
async def exporter_donnees_csv(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    import csv
    import io
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    if not etude.formulaire:
        raise HTTPException(404, "Aucun formulaire créé pour cette étude")
    await fact.precheck(current_user.user_id)

    form = etude.formulaire
    questions = sorted(form.questions, key=lambda q: q.ordre)
    col_ids = [q.question_id for q in questions]
    col_names = [q.name_xlsform or q.libelle[:40] or q.question_id for q in questions]

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(col_names + ["_soumis_le"])
    for r in form.reponses:
        row = []
        for qid in col_ids:
            val = r.get(qid, "")
            if isinstance(val, (list, dict)):
                val = str(val)
            row.append(val)
        row.append(r.get("_soumis_le", ""))
        writer.writerow(row)

    nom = f"yukpopro_{_slug(etude.titre)}_donnees.csv"
    await fact.debiter(current_user.user_id, "csv_export")
    return Response(
        content=("\ufeff" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


# ─── XLSForm export ───────────────────────────────────────────────────────────

@router.get(
    "/{etude_id}/formulaire/xlsform",
    summary="Télécharger le formulaire au format XLSForm (KoBoCollect / ODK / SurveyCTO)",
    response_class=Response,
)
async def telecharger_xlsform(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    etude = _etude_owner_ou_404(etude_id, current_user.user_id)
    await fact.precheck(current_user.user_id)
    try:
        xlsx_bytes = ge.generer_xlsform_bytes(etude_id)
        nom = f"yukpopro_{_slug(etude.titre)}.xlsx"
        # Persister dans Mes Documents
        try:
            _save_bureau(current_user.user_id, "xls", etude.titre, "xlsx", xlsx_bytes)
        except Exception:
            pass
        await fact.debiter(current_user.user_id, "xlsform_export")
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nom}"'},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération XLSForm : {e}")


# ─── Upload protocole / outils de collecte (KoBoCollect pro) ───────────────────

class ProtocoleUploadResponse(BaseModel):
    titre_formulaire: str
    n_questions: int
    formulaire_id: Optional[str]
    lien_xlsform: Optional[str]
    lien_collecte: Optional[str]
    message: str


@router.post(
    "/upload-protocole",
    summary="Upload PDF/DOCX du protocole — Claude génère automatiquement le formulaire XLSForm",
)
async def upload_protocole(
    fichier: UploadFile = File(...),
    etude_id: Optional[str] = Form(None),
    titre: str = Form("Enquête"),
    objectif: str = Form(""),
    population: str = Form(""),
    n_questions: int = Form(20),
    current_user: TokenData = Depends(get_current_user),
):
    """Workflow pro : uploader le protocole d'enquête → Claude construit le formulaire complet."""
    await fact.precheck(current_user.user_id)
    content = await fichier.read()
    if len(content) == 0:
        raise HTTPException(400, "Fichier vide")
    from config.settings import settings as _s
    _limite_mo = getattr(_s, "MAX_DOC_SIZE_MB", 50)
    if len(content) > _limite_mo * 1024 * 1024:
        raise HTTPException(400, f"Fichier trop volumineux (> {_limite_mo} Mo)")

    try:
        texte = _extract_text_from_upload(fichier.filename or "", content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if len(texte.strip()) < 50:
        raise HTTPException(400, "Texte extrait trop court — vérifiez le fichier")

    # Extraction sémantique objectif/population par LLM Haiku (~1s) plutôt
    # qu'un `find()` sur mot-clé : "absence d'objectif" matchait avant,
    # un titre "Objectifs annexes" tronquait à 300 chars hors contexte, etc.
    # Le LLM lit le protocole en entier et sort 2 phrases précises.
    if not objectif or not population:
        try:
            from core.ia_client import ia_client, ModeIA, ModelePrioritaire
            import json as _json, re as _re
            extraction_prompt = (
                "Lis ce protocole d'enquête et extrait UNIQUEMENT en JSON :\n"
                '{"objectif": "...", "population": "..."}\n'
                "- objectif : 1-2 phrases (finalité de l'étude)\n"
                "- population : 1 phrase (cible/échantillon)\n"
                "Si pas mentionné, mets \"\". Pas de markdown, pas de texte autour.\n\n"
                f"PROTOCOLE :\n{texte[:6000]}"
            )
            rep = await ia_client.appeler(
                prompt=extraction_prompt,
                mode=ModeIA.PRECISION,
                json_attendu=True,
                forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
                max_tokens_override=300,
                utiliser_cache=True, cache_ttl=3600,
            )
            raw = (getattr(rep, "contenu", "") or "").strip()
            m = _re.search(r"\{[\s\S]*\}", raw)
            data = _json.loads(m.group(0)) if m else {}
            if not objectif:
                objectif = (data.get("objectif") or "").strip()[:500]
            if not population:
                population = (data.get("population") or "").strip()[:300]
        except Exception as _e:
            logger.debug(f"[Enquetes/protocole] extraction LLM non bloquante : {_e}")

    try:
        resultat = await ge.generer_formulaire_ia(
            description=texte[:8000],
            titre=titre,
            objectif=objectif or "Enquête terrain",
            population=population or "Population cible",
            n_questions=n_questions,
        )
        await fact.debiter(current_user.user_id, "protocole_upload")
    except Exception as e:
        raise HTTPException(500, f"Erreur IA : {e}")

    formulaire_id = None
    if etude_id:
        try:
            form = ge.creer_formulaire(
                etude_id=etude_id,
                titre=resultat["titre_formulaire"],
                description=resultat.get("description", ""),
                questions=resultat["questions"],
                sections=resultat.get("sections_metadata", []),
            )
            formulaire_id = form.formulaire_id
            etude_after = ge.get_etude(etude_id)
            if etude_after:
                await sauvegarder_etude(etude_after, current_user.user_id)
            # Persister le XLSForm dans Mes Documents
            try:
                xls_bytes = ge.generer_xlsform_bytes(etude_id)
                _save_bureau(current_user.user_id, "xls", resultat["titre_formulaire"], "xlsx", xls_bytes)
            except Exception:
                pass
        except Exception as e:
            raise HTTPException(400, f"Étude introuvable ou invalide : {e}")

    return ProtocoleUploadResponse(
        titre_formulaire=resultat["titre_formulaire"],
        n_questions=len(resultat["questions"]),
        formulaire_id=formulaire_id,
        lien_xlsform=f"/api/v1/enquetes/{etude_id}/formulaire/xlsform" if formulaire_id else None,
        lien_collecte=f"/api/v1/enquetes/formulaire/{formulaire_id}" if formulaire_id else None,
        message=(
            f"Protocole analysé ({len(texte)} car.) — {len(resultat['questions'])} questions générées par IA. "
            + ("XLSForm sauvegardé dans Mes Documents." if formulaire_id else "Fournissez etude_id pour créer le formulaire.")
        ),
    )


# ─── Génération formulaire par IA ─────────────────────────────────────────────

class GenFormulaireIARequest(BaseModel):
    description: str
    titre: str
    objectif: str
    population: str
    n_questions: int = 15
    creer_dans_etude: Optional[str] = None  # etude_id pour créer automatiquement


@router.post(
    "/generer-formulaire-ia",
    summary="Claude génère un formulaire professionnel depuis une description + export XLSForm",
)
async def generer_formulaire_ia(
    payload: GenFormulaireIARequest,
    current_user: TokenData = Depends(get_current_user),
):
    await fact.precheck(current_user.user_id)
    try:
        resultat = await ge.generer_formulaire_ia(
            description=payload.description,
            titre=payload.titre,
            objectif=payload.objectif,
            population=payload.population,
            n_questions=payload.n_questions,
        )
        await fact.debiter(current_user.user_id, "formulaire_ia")

        # Si un etude_id est fourni, créer le formulaire directement dans l'étude
        formulaire_id = None
        if payload.creer_dans_etude:
            try:
                form = ge.creer_formulaire(
                    etude_id=payload.creer_dans_etude,
                    titre=resultat["titre_formulaire"],
                    description=resultat["description"],
                    questions=resultat["questions"],
                    sections=resultat.get("sections_metadata", []),
                )
                formulaire_id = form.formulaire_id
                etude_after = ge.get_etude(payload.creer_dans_etude)
                if etude_after:
                    await sauvegarder_etude(etude_after, current_user.user_id)
                # Persister XLSForm dans Mes Documents
                try:
                    xls_bytes = ge.generer_xlsform_bytes(payload.creer_dans_etude)
                    _save_bureau(current_user.user_id, "xls", resultat["titre_formulaire"], "xlsx", xls_bytes)
                except Exception:
                    pass
            except Exception as e:
                pass  # Non bloquant si l'étude n'existe pas

        return {
            **resultat,
            "formulaire_id": formulaire_id,
            "lien_xlsform": f"/api/v1/enquetes/{payload.creer_dans_etude}/formulaire/xlsform" if formulaire_id else None,
            "lien_collecte": f"/api/v1/enquetes/formulaire/{formulaire_id}" if formulaire_id else None,
            "message": (
                "Formulaire généré. "
                + (f"Créé dans l'étude — XLSForm disponible pour KoBoCollect/ODK." if formulaire_id else
                   "Fournissez creer_dans_etude pour l'enregistrer.")
            ),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération IA : {e}")


# ─── Analyse des commentaires (questions ouvertes) ────────────────────────────

@router.post(
    "/{etude_id}/analyser-commentaires",
    summary="Analyse IA des questions ouvertes — thèmes, sentiments, citations représentatives",
)
async def analyser_commentaires(etude_id: str, current_user: TokenData = Depends(get_current_user)):
    await fact.precheck(current_user.user_id)
    try:
        resultats = await ge.analyser_commentaires(etude_id)
        etude = ge.get_etude(etude_id)
        if etude:
            await sauvegarder_etude(etude, current_user.user_id)
        await fact.debiter(current_user.user_id, "analyse_commentaires")
        return resultats
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse commentaires : {e}")


# ─── Analyse quantitative intelligente (guidée par LLM) ───────────────────────

@router.post(
    "/{etude_id}/analyser-intelligent",
    summary="Claude décide quelles variables croiser selon le contexte analytique (pas de croisement mécanique)",
)
async def analyser_quantitatif_intelligent(
    etude_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Claude lit l'objectif de l'étude, les questions de recherche et les données,
    puis sélectionne les croisements et analyses les plus pertinents.
    Résultats : croisements ciblés + Chi² + descriptives prioritaires + graphiques.
    """
    await fact.precheck(current_user.user_id)
    try:
        resultats = await ge.analyser_quantitatif_intelligent(etude_id)
        etude = ge.get_etude(etude_id)
        if etude:
            await sauvegarder_etude(etude, current_user.user_id)
        await fact.debiter(current_user.user_id, "analyse_intelligente")
        return {
            "statut": "analyse_intelligente_terminee",
            "n_reponses": resultats["n_reponses"],
            "n_croisements": len(resultats["croisements_cibles"]),
            "n_descriptives": len(resultats["analyses_descriptives"]),
            "hypotheses": resultats["hypotheses"],
            "note_methodologique": resultats["note_methodologique"],
            "graphiques": resultats["graphiques"],
            "croisements_cibles": resultats["croisements_cibles"],
            "analyses_descriptives": resultats["analyses_descriptives"],
            "plan_analyse": resultats["plan_analyse"],
            "message": "Analyse ciblée terminée. Générez le rapport pour la synthèse complète.",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse intelligente : {e}")
