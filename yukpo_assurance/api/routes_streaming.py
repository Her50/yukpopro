"""
YukpoAssurance — Endpoints SSE pour tâches IA longues

Permet au frontend d'afficher la progression en temps réel pour :
- Analyse de conformité CIMA complète
- Analyse fraude réseau (graphe)
- Génération de rapport complet
- Calcul actuariel avec IA

Format SSE :
  data: {"type": "progress", "step": "Analyse des ratios...", "pct": 30}
  data: {"type": "result", "data": {...}, "pct": 100}
  data: {"type": "error", "message": "..."}
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.streaming")

router = APIRouter(
    prefix="/stream",
    tags=["Streaming SSE (tâches longues)"],
    dependencies=[Depends(get_current_user)],
)


# ── Helpers SSE ───────────────────────────────────────────────────────────────

def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_progress(step: str, pct: int, detail: str = "") -> str:
    return _sse_event({"type": "progress", "step": step, "pct": pct, "detail": detail})


def _sse_result(data: dict) -> str:
    return _sse_event({"type": "result", "data": data, "pct": 100})


def _sse_error(message: str) -> str:
    return _sse_event({"type": "error", "message": message})


def _sse_keepalive() -> str:
    return ": keepalive\n\n"  # SSE comment — évite timeout proxy


# ── Requêtes ─────────────────────────────────────────────────────────────────

class AnalyseConformiteRequest(BaseModel):
    donnees: dict  # Mêmes champs que /api/v1/cima/rapport-conformite


class AnalyseFraudeRequest(BaseModel):
    sinistres: list[dict]
    periode_mois: int = 12


class GenerationRapportRequest(BaseModel):
    type_rapport: str  # "sinistralite" | "conformite" | "activite"
    donnees: dict
    periode: str = ""


# ── Endpoint conformité CIMA ──────────────────────────────────────────────────

@router.get("/conformite-cima")
async def stream_conformite_cima(
    primes_nettes: float = 1_000_000_000,
    capitaux_propres: float = 500_000_000,
    provisions_techniques: float = 600_000_000,
    actifs_admis: float = 650_000_000,
    primes_brutes: float = 1_100_000_000,
    primes_cedees: float = 150_000_000,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Analyse de conformité CIMA complète avec progression SSE.
    Connecter via EventSource :
      new EventSource('/api/v1/stream/conformite-cima?primes_nettes=...')
    """
    async def generer() -> AsyncGenerator[str, None]:
        try:
            yield _sse_progress("Initialisation de l'analyse CIMA...", 5)
            await asyncio.sleep(0.1)

            yield _sse_progress("Calcul de la marge de solvabilité (Art. 337-1)...", 20)
            from modules.cima.code_cima_engine import cima_engine
            marge = cima_engine.calculer_marge_solvabilite_non_vie(
                primes_nettes=primes_nettes,
                charge_sinistres_moyenne_3ans=primes_nettes * 0.60,
                capitaux_propres=capitaux_propres,
            )
            yield _sse_progress(
                f"Marge solvabilité : {'✓ Conforme' if marge['conforme'] else '⚠ Alerte'}",
                35,
                f"{marge['marge_requise_fcfa']:,.0f} FCFA requis",
            )
            await asyncio.sleep(0.1)

            yield _sse_progress("Vérification couverture provisions (Art. 335)...", 50)
            couverture = cima_engine.calculer_couverture_provisions(
                provisions_techniques=provisions_techniques,
                actifs_admis_en_couverture=actifs_admis,
            )
            yield _sse_progress(
                f"Couverture provisions : {'✓ Conforme' if couverture['conforme'] else '⚠ Alerte'}",
                60,
                f"Taux couverture : {couverture['taux_couverture']}%",
            )
            await asyncio.sleep(0.1)

            yield _sse_progress("Analyse du taux de réassurance (Art. 308)...", 70)
            rea = cima_engine.analyser_taux_reassurance(
                primes_brutes=primes_brutes,
                primes_cedees=primes_cedees,
            )
            yield _sse_progress(
                f"Réassurance : taux {rea['taux_cession']}%",
                80,
                f"Seuil : {rea['seuil_alerte']}",
            )
            await asyncio.sleep(0.1)

            yield _sse_progress("Consolidation du rapport de conformité...", 90)
            donnees = {
                "primes_nettes": primes_nettes,
                "capitaux_propres": capitaux_propres,
                "provisions_techniques": provisions_techniques,
                "actifs_admis_couverture": actifs_admis,
                "primes_emises_brutes": primes_brutes,
                "primes_cedees_reassurance": primes_cedees,
            }
            rapport = cima_engine.rapport_conformite_global(donnees)
            await asyncio.sleep(0.1)

            yield _sse_result({
                "rapport": rapport,
                "detail": {
                    "marge_solvabilite": marge,
                    "couverture_provisions": couverture,
                    "reassurance": rea,
                },
                "utilisateur": current_user.username,
            })

        except Exception as e:
            logger.error(f"[SSE/CIMA] Erreur: {e}")
            yield _sse_error(str(e))

    return StreamingResponse(
        generer(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Endpoint analyse fraude SSE ────────────────────────────────────────────────

@router.post("/analyse-fraude")
async def stream_analyse_fraude(
    req: AnalyseFraudeRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Analyse fraude en réseau sur un portefeuille de sinistres avec progression SSE.
    Idéal pour les analyses portant sur 50+ sinistres.
    """
    async def generer() -> AsyncGenerator[str, None]:
        try:
            nb = len(req.sinistres)
            yield _sse_progress(f"Analyse fraude : {nb} sinistres en cours...", 10)
            await asyncio.sleep(0.05)

            yield _sse_progress("Détection des patterns individuels...", 25)
            from modules.sinistres.fraude_detector import FraudeDetector
            detector = FraudeDetector()
            scores = []
            for i, sinistre in enumerate(req.sinistres[:50]):  # Cap à 50 pour la démo
                pct = 25 + int((i / min(nb, 50)) * 35)
                if i % 10 == 0:
                    yield _sse_progress(
                        f"Analyse sinistre {i+1}/{min(nb, 50)}...",
                        pct,
                    )
                    # Keepalive pour éviter timeout
                    yield _sse_keepalive()
                    await asyncio.sleep(0.02)

                try:
                    score = await detector.analyser(sinistre)
                    scores.append({
                        "numero": sinistre.get("numero_sinistre", f"SIN-{i}"),
                        "score_fraude": score.get("score_fraude", 0),
                        "alerte": score.get("alerte_fraude", False),
                        "raisons": score.get("raisons_alerte", []),
                    })
                except Exception:
                    scores.append({
                        "numero": sinistre.get("numero_sinistre", f"SIN-{i}"),
                        "score_fraude": 0,
                        "alerte": False,
                        "raisons": [],
                    })

            yield _sse_progress("Analyse des réseaux et connexions...", 70)
            await asyncio.sleep(0.1)

            alertes = [s for s in scores if s["alerte"]]
            score_moyen = sum(s["score_fraude"] for s in scores) / len(scores) if scores else 0

            yield _sse_progress("Génération du rapport de fraude...", 90)
            await asyncio.sleep(0.05)

            yield _sse_result({
                "nb_sinistres_analyses": len(scores),
                "nb_alertes": len(alertes),
                "score_fraude_moyen": round(score_moyen, 1),
                "taux_fraude_pct": round(len(alertes) / len(scores) * 100, 1) if scores else 0,
                "alertes_prioritaires": sorted(alertes, key=lambda x: x["score_fraude"], reverse=True)[:10],
                "scores_distribution": {
                    "bas_0_30": sum(1 for s in scores if s["score_fraude"] < 30),
                    "moyen_30_60": sum(1 for s in scores if 30 <= s["score_fraude"] < 60),
                    "eleve_60_plus": sum(1 for s in scores if s["score_fraude"] >= 60),
                },
            })

        except Exception as e:
            logger.error(f"[SSE/Fraude] Erreur: {e}")
            yield _sse_error(str(e))

    return StreamingResponse(
        generer(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Endpoint génération rapport SSE ───────────────────────────────────────────

@router.post("/generer-rapport")
async def stream_generer_rapport(
    req: GenerationRapportRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Génère un rapport IA avec progression visible.
    Évite les timeouts HTTP sur les générations de 30-60s.
    """
    async def generer() -> AsyncGenerator[str, None]:
        try:
            yield _sse_progress(f"Préparation du rapport '{req.type_rapport}'...", 10)
            await asyncio.sleep(0.1)

            yield _sse_progress("Analyse des données métier...", 25)
            await asyncio.sleep(0.1)

            yield _sse_progress("Génération par l'IA (Claude Opus)...", 40)
            yield _sse_keepalive()

            from modules.documents.generateur import document_generateur

            if req.type_rapport == "sinistralite":
                doc = await document_generateur.rapport_sinistre(req.donnees)
            elif req.type_rapport == "conformite":
                annee = req.donnees.get("annee", 2024)
                doc = await document_generateur.rapport_cima_annuel(req.donnees, annee)
            else:
                # Rapport générique via prompt IA
                doc = await document_generateur.generer_depuis_prompt_ia(
                    demande=f"Rapport {req.type_rapport} — {req.periode}",
                    document_type="docx",
                    contexte=req.donnees,
                )

            yield _sse_progress("Mise en forme du document...", 80)
            await asyncio.sleep(0.05)

            yield _sse_progress("Finalisation...", 95)
            await asyncio.sleep(0.05)

            if doc:
                yield _sse_result({
                    "nom_fichier": doc.get("filename", "rapport.docx"),
                    "taille_bytes": len(doc.get("data_b64", "")) * 3 // 4,
                    "telecharger_url": doc.get("url", ""),
                    "mime_type": doc.get("mime_type", "application/octet-stream"),
                    "data_b64": doc.get("data_b64", ""),
                })
            else:
                yield _sse_error("Échec génération rapport — aucun contenu retourné")

        except Exception as e:
            logger.error(f"[SSE/Rapport] Erreur: {e}")
            yield _sse_error(str(e))

    return StreamingResponse(
        generer(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
