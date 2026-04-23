"""Suite B — Dashboard."""
from __future__ import annotations

from ..browser import login, screenshot
from ..common import RunContext
from .base import make_result, safe_goto


async def run(ctx: RunContext, context) -> dict:
    web = ctx.cfg["web_url"]
    page = await context.new_page()
    if not await login(page, ctx):
        return make_result("Dashboard", "FAIL", 0, defauts=["login impossible"])
    screens = []
    defauts = []
    score = 9

    if not await safe_goto(page, f"{web}/dashboard", ctx.cfg["timeouts"]["navigation_ms"]):
        await safe_goto(page, web, ctx.cfg["timeouts"]["navigation_ms"])
    await page.wait_for_timeout(2000)
    screens.append(await screenshot(page, ctx, "dashboard_home"))

    body = (await page.content()).lower()
    if "<main" not in body and "<section" not in body:
        defauts.append("page tres pauvre (pas de section/main)")
        score -= 3
    if any(m in body for m in ["lorem ipsum", "todo", "{{"]):
        defauts.append("placeholders non remplaces detectes")
        score -= 3
    if len(body) < 5000:
        defauts.append(f"contenu HTML tres court ({len(body)} chars)")
        score -= 2

    await page.close()
    score = max(0, score)
    status = "PASS" if score >= 7 else "PARTIAL" if score >= 5 else "FAIL"
    return make_result("Dashboard", status, score, defauts=defauts, screenshots=screens)
