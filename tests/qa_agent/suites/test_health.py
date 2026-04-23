"""Smoke health check backend."""
from __future__ import annotations

import requests

from ..common import RunContext
from .base import make_result


async def run(ctx: RunContext, context) -> dict:
    health = ctx.cfg["health_url"]
    try:
        r = requests.get(health, timeout=10)
        if r.status_code == 200:
            return make_result("Backend health", "PASS", 10,
                               note_text=f"GET {health} → 200")
        return make_result("Backend health", "FAIL", 2,
                           defauts=[f"HTTP {r.status_code} sur {health}"])
    except Exception as e:
        return make_result("Backend health", "FAIL", 0,
                           defauts=[f"exception: {e}"])
