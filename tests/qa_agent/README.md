# Agent QA YukpoPro

Agent de test QA "humain senior" pour la plateforme YukpoPro web (`https://yukpopro-web.vercel.app`).

Combine **Playwright** (parcours navigateur), **appels API directs** (validation profonde, indépendante de l'UI) et **Claude API** (jugement qualité du contenu produit : rapports, slides, infographies, traductions).

## Installation

```bash
cd tests/qa_agent
pip install -r requirements.txt
playwright install chromium
export ANTHROPIC_API_KEY=sk-...
```

## Lancement

```bash
# Toutes les suites en prod
python -m tests.qa_agent.run_qa --env prod

# Suites ciblées
python -m tests.qa_agent.run_qa --env prod --suites health,auth,copilote

# Sans regen fixtures
python -m tests.qa_agent.run_qa --env prod --no-fixtures
```

Rapports + artefacts générés dans `tests/qa_agent/artifacts/YYYY-MM-DD_HHMM/`.

## Structure

| Fichier | Rôle |
|---|---|
| `run_qa.py` | Entrypoint asyncio orchestrateur |
| `config.yaml` | URLs, credentials test, seuils qualité |
| `common.py` | RunContext + chargement config |
| `browser.py` | Helpers Playwright (login, screenshot, download) |
| `mobile_audit.py` | Audit statique parité web/mobile |
| `report.py` | Génération rapports markdown + html |
| `quality/evaluateur.py` | Notation contenu via Claude API |
| `quality/verifs.py` | Vérifs déterministes (PDF, DOCX, XLSForm…) |
| `fixtures/generate_fixtures.py` | Génère fixtures déterministes (seed fixe) |
| `suites/test_*.py` | Une suite par feature |

## Suites disponibles

`health, auth, dashboard, copilote, studio, infographie, enquetes, reunions, traduction, emploi, marches, abonnement, documents`

## Critères qualité (config.yaml)

- `min_score_pass: 7` (sur 10)
- `min_score_partial: 5`
- Rapport ≥ 5 pages, slides ≥ 10, XLSForm ≥ 15 questions
- Transcription ≥ 85% similarité Levenshtein avec référence

Toute suite qui ne valide pas un endpoint via `200 OK` SEUL : la qualité du contenu produit est notée par Claude API (rubrique structurée → JSON).
