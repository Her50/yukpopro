"""Helpers Playwright: lancement navigateur, login, screenshots, downloads."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from .common import RunContext, safe_filename

log = logging.getLogger("qa_agent.browser")

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
except ImportError:
    async_playwright = None  # type: ignore


@asynccontextmanager
async def lancer_navigateur(ctx: RunContext):
    if async_playwright is None:
        raise RuntimeError("playwright non installé — pip install playwright + playwright install chromium")
    pw_cfg = ctx.cfg["playwright"]
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=pw_cfg["headless"],
            slow_mo=pw_cfg.get("slow_mo_ms", 0),
        )
        context = await browser.new_context(
            viewport={"width": pw_cfg["viewport"]["width"],
                      "height": pw_cfg["viewport"]["height"]},
            accept_downloads=True,
            locale="fr-FR",
        )
        try:
            yield context
        finally:
            await context.close()
            await browser.close()


async def screenshot(page: "Page", ctx: RunContext, label: str) -> str:
    name = safe_filename(label) + ".png"
    path = ctx.screenshots_dir / name
    try:
        await page.screenshot(path=str(path), full_page=True)
    except Exception as e:
        log.warning(f"screenshot {label} echec: {e}")
    return str(path.relative_to(ctx.artifacts_dir))


async def login(page: "Page", ctx: RunContext) -> bool:
    creds = ctx.cfg["credentials"]
    web = ctx.cfg["web_url"]
    try:
        await page.goto(f"{web}/login", wait_until="domcontentloaded",
                        timeout=ctx.cfg["timeouts"]["navigation_ms"])
    except Exception as e:
        log.error(f"navigation /login echec: {e}")
        return False

    selectors_email = ['input[type="email"]', 'input[name="email"]',
                       'input[placeholder*="email" i]', 'input[id*="email" i]']
    selectors_pwd = ['input[type="password"]', 'input[name="password"]']
    selectors_btn = ['button[type="submit"]', 'button:has-text("Connexion")',
                     'button:has-text("Se connecter")', 'button:has-text("Login")']

    async def _try_fill(selectors: list[str], value: str) -> bool:
        for sel in selectors:
            try:
                await page.fill(sel, value, timeout=2500)
                return True
            except Exception:
                continue
        return False

    if not await _try_fill(selectors_email, creds["email"]):
        log.error("champ email introuvable")
        return False
    if not await _try_fill(selectors_pwd, creds["password"]):
        log.error("champ password introuvable")
        return False

    for sel in selectors_btn:
        try:
            await page.click(sel, timeout=2000)
            break
        except Exception:
            continue
    else:
        log.error("bouton submit introuvable")
        return False

    try:
        await page.wait_for_url(lambda u: "/login" not in u,
                                timeout=ctx.cfg["timeouts"]["navigation_ms"])
        return True
    except Exception:
        return False


async def telecharger_via_clic(page: "Page", ctx: RunContext, selector: str,
                                timeout_ms: int = 30000, label: str = "fichier") -> Path | None:
    try:
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            await page.click(selector)
        download = await dl_info.value
        target = ctx.downloads_dir / safe_filename(f"{label}_{download.suggested_filename}")
        await download.save_as(str(target))
        log.info(f"download {target.name}")
        return target
    except Exception as e:
        log.warning(f"download {label} echec: {e}")
        return None
