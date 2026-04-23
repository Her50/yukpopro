"""Suite A — Authentification."""
from __future__ import annotations

import logging

from ..browser import login, screenshot
from ..common import RunContext
from .base import make_result, safe_goto

log = logging.getLogger("qa_agent.suite.auth")


async def run(ctx: RunContext, context) -> dict:
    web = ctx.cfg["web_url"]
    creds = ctx.cfg["credentials"]
    page = await context.new_page()
    screens: list[str] = []
    defauts: list[str] = []
    score = 10

    if not await safe_goto(page, f"{web}/login", ctx.cfg["timeouts"]["navigation_ms"]):
        return make_result("Authentification", "FAIL", 0,
                           defauts=["impossible de charger /login"],
                           screenshots=screens)
    screens.append(await screenshot(page, ctx, "auth_login_initial"))

    try:
        await page.fill('input[type="email"], input[name="email"]', creds["email"], timeout=4000)
        await page.fill('input[type="password"], input[name="password"]', "WRONG_PASSWORD", timeout=4000)
        for sel in ['button[type="submit"]', 'button:has-text("Connexion")', 'button:has-text("Se connecter")']:
            try:
                await page.click(sel, timeout=2000)
                break
            except Exception:
                continue
        await page.wait_for_timeout(2000)
        body = (await page.content()).lower()
        if "incorrect" not in body and "invalide" not in body and "erreur" not in body:
            defauts.append("pas de message d'erreur visible sur mauvais mot de passe")
            score -= 2
        if "utilisateur inconnu" in body or "user not found" in body:
            defauts.append("fuite d'info: distinction email inconnu vs mauvais mdp")
            score -= 2
        screens.append(await screenshot(page, ctx, "auth_login_wrong_pwd"))
    except Exception as e:
        defauts.append(f"test mauvais mdp echec: {e}")
        score -= 3

    ok = await login(page, ctx)
    screens.append(await screenshot(page, ctx, "auth_login_success"))
    if not ok:
        return make_result("Authentification", "FAIL", max(0, score - 5),
                           defauts=defauts + ["login admin echoue"],
                           screenshots=screens)

    try:
        await page.reload(wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1500)
        if "/login" in page.url:
            defauts.append("session non persistee apres refresh")
            score -= 3
        screens.append(await screenshot(page, ctx, "auth_after_refresh"))
    except Exception as e:
        defauts.append(f"refresh echec: {e}")
        score -= 1

    try:
        for sel in ['button:has-text("Déconnexion")', 'button:has-text("Logout")',
                    '[data-testid="logout"]', 'a:has-text("Déconnexion")']:
            try:
                await page.click(sel, timeout=2000)
                break
            except Exception:
                continue
        await page.wait_for_timeout(1500)
        if "/login" not in page.url:
            defauts.append("logout n'a pas redirige vers /login (a verifier manuellement)")
            score -= 1
    except Exception:
        defauts.append("bouton logout introuvable (UX)")
        score -= 1

    await page.close()
    score = max(0, score)
    status = "PASS" if score >= 7 else "PARTIAL" if score >= 5 else "FAIL"
    return make_result("Authentification", status, score,
                       defauts=defauts, screenshots=screens)
