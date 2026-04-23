"""Entrypoint Agent QA YukpoPro.

Usage:
    python -m tests.qa_agent.run_qa --env prod
    python -m tests.qa_agent.run_qa --env prod --suites health,auth,copilote
    python -m tests.qa_agent.run_qa --env prod --no-fixtures
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import sys
import traceback
from pathlib import Path

from contextlib import asynccontextmanager

from .browser import lancer_navigateur
from .common import RunContext, load_config, setup_logging
from .mobile_audit import auditer
from .report import generer_html, generer_markdown


@asynccontextmanager
async def _no_browser():
    yield None


SUITES_NEED_BROWSER = {"auth", "dashboard", "copilote"}


SUITES = [
    ("health", "tests.qa_agent.suites.test_health"),
    ("auth", "tests.qa_agent.suites.test_auth"),
    ("dashboard", "tests.qa_agent.suites.test_dashboard"),
    ("copilote", "tests.qa_agent.suites.test_copilote"),
    ("studio", "tests.qa_agent.suites.test_studio"),
    ("infographie", "tests.qa_agent.suites.test_infographie"),
    ("enquetes", "tests.qa_agent.suites.test_enquetes"),
    ("reunions", "tests.qa_agent.suites.test_reunions"),
    ("traduction", "tests.qa_agent.suites.test_traduction"),
    ("emploi", "tests.qa_agent.suites.test_emploi"),
    ("marches", "tests.qa_agent.suites.test_marches"),
    ("abonnement", "tests.qa_agent.suites.test_abonnement"),
    ("documents", "tests.qa_agent.suites.test_documents"),
]


async def _exec_suite(name: str, module_path: str, ctx: RunContext, context, log) -> dict:
    try:
        mod = importlib.import_module(module_path)
        log.info(f">>suite {name}")
        result = await mod.run(ctx, context)
        log.info(f"[OK] suite {name} → {result.get('status')} (score={result.get('score')})")
        return result
    except Exception as e:
        log.error(f"[KO] suite {name} crashed: {e}\n{traceback.format_exc()}")
        return {
            "feature": name,
            "status": "FAIL",
            "score": 0,
            "details": {"defauts": [f"crash: {e}"], "recommandations": [],
                        "screenshots": [], "artefacts": []},
        }


async def _main_async(args) -> int:
    log = setup_logging(args.log_level)
    cfg = load_config(args.env)
    ctx = RunContext(cfg=cfg)

    if not args.no_fixtures:
        log.info("Generation fixtures (idempotent)…")
        try:
            from .fixtures.generate_fixtures import main as gen_main
            gen_main()
        except Exception as e:
            log.warning(f"fixtures echec partiel: {e}")

    suites_demandees = (
        [s.strip() for s in args.suites.split(",") if s.strip()] if args.suites else None
    )
    a_executer = [(n, m) for n, m in SUITES
                  if not suites_demandees or n in suites_demandees]
    if not a_executer:
        log.error(f"aucune suite ne correspond a {args.suites}")
        return 2

    log.info(f"Suites a executer: {[n for n,_ in a_executer]}")

    try:
        import playwright  # noqa: F401
        browser_ctx = lancer_navigateur(ctx)
    except ImportError:
        log.warning("playwright absent — suites navigateur sautées (auth, dashboard)")
        browser_ctx = _no_browser()
        a_executer = [(n, m) for (n, m) in a_executer if n not in SUITES_NEED_BROWSER]

    async with browser_ctx as context:
        for name, module_path in a_executer:
            res = await _exec_suite(name, module_path, ctx, context, log)
            ctx.record(
                feature=res["feature"],
                status=res["status"],
                score=res["score"],
                details=res["details"],
            )

    log.info("Audit parite mobile...")
    audit = auditer()

    md = generer_markdown(ctx, audit_mobile=audit)
    html = generer_html(ctx, audit_mobile=audit)
    log.info(f"Rapport markdown: {md}")
    log.info(f"Rapport html:     {html}")

    fails = sum(1 for r in ctx.results if r["status"] == "FAIL")
    return 1 if fails else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent QA YukpoPro")
    parser.add_argument("--env", default="prod", choices=["prod", "local"])
    parser.add_argument("--suites", default="", help="liste comma-separee, ex: health,auth")
    parser.add_argument("--no-fixtures", action="store_true",
                        help="ne pas (re)generer les fixtures")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
