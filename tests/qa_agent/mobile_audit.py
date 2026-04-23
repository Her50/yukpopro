"""Audit statique de parite mobile vs web (sans E2E)."""
from __future__ import annotations

import re
from pathlib import Path

from .common import REPO_ROOT

WEB_PAGES = REPO_ROOT / "yukpopro_web" / "src" / "pages"
MOBILE_SCREENS = REPO_ROOT / "yukpopro_mobile" / "src" / "screens"
MOBILE_API = REPO_ROOT / "yukpopro_mobile" / "src" / "api" / "client.ts"

PARITE = [
    ("Authentification", "LoginPage.tsx", "LoginScreen.tsx", "authApi"),
    ("Dashboard", "DashboardPage.tsx", "DashboardScreen.tsx", None),
    ("Profil", "ProfilPage.tsx", "ProfilScreen.tsx", "profilApi"),
    ("Copilote", "CopilotePage.tsx", "CopiloteScreen.tsx", "copiloteApi"),
    ("Chat", "ChatPage.tsx", "ChatScreen.tsx", "chatApi"),
    ("Agents", "AgentsPage.tsx", "AgentsScreen.tsx", "agentsApi"),
    ("Yukpo Studio", "GenerateursPage.tsx", "GenerateursScreen.tsx", "infographieApi"),
    ("Réunions", "ReunionsPage.tsx", "ReunionsScreen.tsx", "reunionsApi"),
    ("Enquêtes", "EnquetesPage.tsx", "EnquetesScreen.tsx", "enquetesApi"),
    ("Emploi", "EmploiPage.tsx", "EmploiScreen.tsx", "emploiApi"),
    ("Marchés publics", "MarchesPage.tsx", "MarchesScreen.tsx", "marchesApi"),
    ("Traduction", "TraductionPage.tsx", "TraductionScreen.tsx", "traductionApi"),
    ("Mes Documents", "HistoriqueDocumentsPage.tsx", "DocumentsScreen.tsx", "documentsApi"),
    ("Abonnement", "AbonnementPage.tsx", "AbonnementScreen.tsx", "abonnementApi"),
    ("Admin", "AdminPage.tsx", "AdminScreen.tsx", None),
]


def _exists_anywhere(rootdir: Path, basename: str) -> Path | None:
    if not rootdir.exists():
        return None
    candidate = rootdir / basename
    if candidate.exists():
        return candidate
    for p in rootdir.rglob(basename):
        return p
    base_no_ext = basename.rsplit(".", 1)[0]
    for p in rootdir.rglob(f"{base_no_ext}*.tsx"):
        return p
    return None


def _api_object_present(api_var: str | None, src: str) -> bool:
    if not api_var:
        return True
    return bool(re.search(rf"\b(export\s+const\s+)?{re.escape(api_var)}\b", src))


def auditer() -> list[dict]:
    api_src = MOBILE_API.read_text(encoding="utf-8", errors="ignore") if MOBILE_API.exists() else ""
    rows = []
    for feature, web_file, mobile_file, api_var in PARITE:
        web_path = _exists_anywhere(WEB_PAGES, web_file)
        mobile_path = _exists_anywhere(MOBILE_SCREENS, mobile_file)
        api_ok = _api_object_present(api_var, api_src) if api_var else True
        gaps = []
        if web_path and not mobile_path:
            gaps.append(f"écran mobile manquant: {mobile_file}")
        if api_var and not api_ok:
            gaps.append(f"objet API manquant côté mobile: {api_var}")
        rows.append({
            "feature": feature,
            "ecran": "OK" if mobile_path else f"MANQUANT ({mobile_file})",
            "api_ok": "OK" if api_ok else "MANQUANT",
            "gaps": "; ".join(gaps) or "—",
        })
    return rows


if __name__ == "__main__":
    for r in auditer():
        print(r)
