"""Generation rapport QA: markdown + html avec screenshots embarques."""
from __future__ import annotations

import base64
import html as _html
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import RunContext


VERDICT_COULEURS = {"PASS": "#16a34a", "PARTIAL": "#d97706", "FAIL": "#dc2626", "SKIP": "#64748b"}


def _read_b64(p: Path) -> str | None:
    if not p.exists():
        return None
    try:
        return base64.b64encode(p.read_bytes()).decode("ascii")
    except Exception:
        return None


def _fmt_score(score: int | None) -> str:
    if score is None:
        return "—"
    return f"{score}/10"


def generer_markdown(ctx: RunContext, audit_mobile: list[dict] | None = None) -> Path:
    stamp = ctx.started_at.strftime("%Y-%m-%d_%H%M")
    out = ctx.artifacts_dir / f"rapport_qa_{stamp}.md"

    total = len(ctx.results)
    par_statut: dict[str, int] = {}
    for r in ctx.results:
        par_statut[r["status"]] = par_statut.get(r["status"], 0) + 1

    lines = [
        f"# Rapport QA YukpoPro — {stamp}",
        "",
        f"- **Démarré** : {ctx.started_at.isoformat()}Z",
        f"- **Environnement** : `{ctx.cfg['env']}`",
        f"- **Web** : {ctx.cfg['web_url']}",
        f"- **API** : {ctx.cfg['api_url']}",
        f"- **Features testées** : {total}",
        f"- **Bilan** : " + ", ".join(f"{k}={v}" for k, v in par_statut.items()),
        "",
        "## Synthèse par feature",
        "",
        "| Feature | Statut | Score | Défauts | Recommandations |",
        "|---|---|---|---|---|",
    ]
    for r in ctx.results:
        d = r["details"]
        defauts = "; ".join(d.get("defauts", [])[:3]) or "—"
        recos = "; ".join(d.get("recommandations", [])[:3]) or "—"
        lines.append(
            f"| {r['feature']} | {r['status']} | {_fmt_score(r['score'])} | "
            f"{defauts[:120]} | {recos[:120]} |"
        )

    lines += ["", "## Détail par feature", ""]
    for r in ctx.results:
        d = r["details"]
        lines += [
            f"### {r['feature']} — {r['status']} ({_fmt_score(r['score'])})",
            "",
            f"- Verdict: **{d.get('verdict', r['status'])}**",
            f"- Timestamp: {r['timestamp']}",
        ]
        if d.get("note_text"):
            lines.append(f"- Note: {d['note_text']}")
        if d.get("artefacts"):
            lines.append("- Artefacts:")
            for a in d["artefacts"]:
                lines.append(f"  - `{a}`")
        if d.get("screenshots"):
            lines.append("- Screenshots:")
            for s in d["screenshots"]:
                lines.append(f"  - `{s}`")
        if d.get("defauts"):
            lines.append("- Défauts:")
            for x in d["defauts"]:
                lines.append(f"  - {x}")
        if d.get("recommandations"):
            lines.append("- Recommandations:")
            for x in d["recommandations"]:
                lines.append(f"  - {x}")
        lines.append("")

    if audit_mobile:
        lines += ["## Audit parité mobile", "",
                  "| Feature | Écran mobile | API mobile OK | Gaps |",
                  "|---|---|---|---|"]
        for row in audit_mobile:
            lines.append(
                f"| {row['feature']} | {row.get('ecran', '—')} | "
                f"{row.get('api_ok', '—')} | {row.get('gaps', '—')} |"
            )
        lines.append("")

    bugs = collecter_top_bugs(ctx)
    if bugs:
        lines += ["## Top 10 bugs / défauts prioritaires", ""]
        for i, b in enumerate(bugs[:10], 1):
            lines.append(f"{i}. **[{b['feature']}]** {b['titre']} — _{b['severite']}_")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def collecter_top_bugs(ctx: RunContext) -> list[dict[str, str]]:
    bugs: list[dict[str, str]] = []
    for r in ctx.results:
        d = r["details"]
        score = r["score"] if r["score"] is not None else 0
        for defaut in d.get("defauts", []):
            sev = "BLOQUANT" if r["status"] == "FAIL" else (
                "MAJEUR" if r["status"] == "PARTIAL" else "MINEUR"
            )
            bugs.append({
                "feature": r["feature"],
                "titre": defaut[:200],
                "severite": sev,
                "score": str(score),
            })
    sev_order = {"BLOQUANT": 0, "MAJEUR": 1, "MINEUR": 2}
    bugs.sort(key=lambda x: (sev_order.get(x["severite"], 9), int(x["score"])))
    return bugs


def generer_html(ctx: RunContext, audit_mobile: list[dict] | None = None) -> Path:
    stamp = ctx.started_at.strftime("%Y-%m-%d_%H%M")
    out = ctx.artifacts_dir / f"rapport_qa_{stamp}.html"

    rows = []
    for r in ctx.results:
        c = VERDICT_COULEURS.get(r["status"], "#475569")
        d = r["details"]
        defauts = "<br>".join(_html.escape(x) for x in d.get("defauts", [])[:5]) or "—"
        recos = "<br>".join(_html.escape(x) for x in d.get("recommandations", [])[:5]) or "—"
        screens_html = ""
        for s in d.get("screenshots", [])[:3]:
            sp = Path(s) if Path(s).is_absolute() else ctx.artifacts_dir / s
            b64 = _read_b64(sp)
            if b64:
                screens_html += (
                    f'<img src="data:image/png;base64,{b64}" '
                    'style="max-width:280px;margin:4px;border:1px solid #ddd"/>'
                )
        rows.append(
            f"<tr>"
            f"<td>{_html.escape(r['feature'])}</td>"
            f"<td><span style=\"background:{c};color:#fff;padding:3px 8px;"
            f"border-radius:4px;font-size:12px\">{r['status']}</span></td>"
            f"<td style=\"text-align:center\">{_fmt_score(r['score'])}</td>"
            f"<td style=\"font-size:13px\">{defauts}</td>"
            f"<td style=\"font-size:13px\">{recos}</td>"
            f"<td>{screens_html}</td>"
            f"</tr>"
        )

    audit_html = ""
    if audit_mobile:
        audit_rows = "".join(
            f"<tr><td>{_html.escape(row['feature'])}</td>"
            f"<td>{_html.escape(str(row.get('ecran', '—')))}</td>"
            f"<td>{_html.escape(str(row.get('api_ok', '—')))}</td>"
            f"<td>{_html.escape(str(row.get('gaps', '—')))}</td></tr>"
            for row in audit_mobile
        )
        audit_html = (
            f"<h2>Audit parité mobile</h2>"
            f"<table><thead><tr><th>Feature</th><th>Écran</th>"
            f"<th>API mobile</th><th>Gaps</th></tr></thead>"
            f"<tbody>{audit_rows}</tbody></table>"
        )

    bugs = collecter_top_bugs(ctx)
    bugs_html = ""
    if bugs:
        items = "".join(
            f"<li><b>[{_html.escape(b['feature'])}]</b> {_html.escape(b['titre'])} "
            f"<i>({b['severite']})</i></li>"
            for b in bugs[:10]
        )
        bugs_html = f"<h2>Top 10 bugs / défauts prioritaires</h2><ol>{items}</ol>"

    html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Rapport QA YukpoPro {stamp}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
margin:24px;color:#1e293b;background:#f8fafc}}
h1{{color:#0f172a}}
table{{border-collapse:collapse;width:100%;background:white;
box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
th,td{{border:1px solid #e2e8f0;padding:10px;vertical-align:top;text-align:left}}
th{{background:#f1f5f9;font-size:13px}}
.summary{{background:white;padding:16px;border-radius:6px;margin-bottom:20px;
box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
</style></head><body>
<h1>Rapport QA YukpoPro — {stamp}</h1>
<div class="summary">
<p><b>Environnement</b>: {ctx.cfg['env']} — <a href="{ctx.cfg['web_url']}">{ctx.cfg['web_url']}</a></p>
<p><b>Démarré</b>: {ctx.started_at.isoformat()}Z — <b>Features</b>: {len(ctx.results)}</p>
</div>
<h2>Synthèse</h2>
<table><thead><tr>
<th>Feature</th><th>Statut</th><th>Score</th><th>Défauts</th>
<th>Recommandations</th><th>Screenshots</th>
</tr></thead><tbody>
{''.join(rows)}
</tbody></table>
{audit_html}
{bugs_html}
</body></html>"""

    out.write_text(html, encoding="utf-8")
    return out
