"""Squelette commun a toutes les suites: signature run(ctx, context) -> dict."""
from __future__ import annotations

import logging
from typing import Any

from ..common import RunContext
from ..browser import screenshot

log = logging.getLogger("qa_agent.suite")


async def safe_goto(page, url: str, timeout_ms: int = 30000) -> bool:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return True
    except Exception as e:
        log.warning(f"goto {url} echec: {e}")
        return False


def make_result(feature: str, status: str, score: int | None = None,
                defauts: list[str] | None = None,
                recommandations: list[str] | None = None,
                screenshots: list[str] | None = None,
                artefacts: list[str] | None = None,
                **extra) -> dict[str, Any]:
    return {
        "feature": feature,
        "status": status,
        "score": score,
        "details": {
            "defauts": defauts or [],
            "recommandations": recommandations or [],
            "screenshots": screenshots or [],
            "artefacts": artefacts or [],
            **extra,
        },
    }


def status_from_score(score: int, seuil_pass: int = 7, seuil_partial: int = 5) -> str:
    if score >= seuil_pass:
        return "PASS"
    if score >= seuil_partial:
        return "PARTIAL"
    return "FAIL"
