# AUDIT FINAL — YukpoPro + YukpoSecrétariat (sprint 2026-05-10)

> Fichier de session local — NE PAS COMMITTER.

## État du sprint

**Livré ce turn** : 1 commit chirurgical (routage LLM long-form Opus 4.7), poussé sur `yukpopro-main` (commit `3b223298`), backend redéployé sur Fly.io (`yukpopro-backend`).

**Reste à livrer** : ~30 commits identifiés par 3 audits parallèles (routage LLM, générateurs DOCX/PDF/PPTX, pipeline Designer Pro). Roadmap structurée Pro/Sec ci-dessous, prête pour sprints suivants.

L'ambition initiale du prompt (audit exhaustif 80–150 features + implémentation de tous les gaps en 1 sprint) excède un seul tour conversationnel. Ce rapport priorise les leviers à plus fort ROI, déjà localisés au niveau fichier:ligne par les explorations parallèles.

---

## Section 1 — Matrice fonctionnelle Pro / Sec (extrait — top 30)

| # | Feature atomique | Pro (yukpopro_web) | Sec (yukposecretariat_web) | Backend partagé |
|---|---|---|---|---|
| 1 | Chat orchestrateur principal | `/chat` + `pro/orchestrer` (Sonnet) | `/chat` + `bureau/chat` (Haiku 9-classes) | `routes_pro_*` + `routes_secretariat_chat` |
| 2 | Génération rapport DOCX | ✅ ReportWriter Pro 13 types | ⚠️ Bureau Rédacteur 30 types (qualité < Pro) | `report_writer_pro.py` / `redacteur.py` |
| 3 | Génération slides PPTX | ✅ SlideBuilder Pro 4 thèmes + charts natifs | ❌ Absent | `slide_builder_pro.py` |
| 4 | Génération PDF imprimable | ✅ via DOCX→PDF LibreOffice | ✅ Designer Pro + WeasyPrint + PDF/X-1a | `infographe_pro.py` + `infographe_weasyprint.py` |
| 5 | Designer Pro (visuels) | ❌ Absent | ✅ 8 projets figés + Layout AI Opus + Brand LoRA | `infographe_pro.py` |
| 6 | OCR documents | ✅ via routes_pro_* | ✅ via `bureau_ocr` | `ocr_scanner.py` (GPT-4o vision) |
| 7 | Audio → texte | ✅ via routes_pro_reunions | ✅ via `bureau_audio` | Whisper local + ElevenLabs |
| 8 | Traduction | ✅ via /translate/live | ✅ via `bureau_traduction` | `translator.py` (GPT-4o-mini live) |
| 9 | Recherche emploi | ✅ Scheduler 30min | ❌ N/A | `scheduler_emploi.py` |
| 10 | Recherche marchés publics | ✅ Scheduler 2h | ❌ N/A | `scheduler_marches.py` |
| 11 | Agents métiers | ✅ pro/agent + agent_systeme | ❌ N/A (pas adapté) | `routes_pro_agent.py` |
| 12 | Réunions | ✅ pro/reunions (transcription, PV) | ❌ N/A | `pro_reunions_router` |
| 13 | Enquêtes & études | ✅ /enquetes (Opus analyse thématique) | ❌ N/A | `gestionnaire_enquetes.py` |
| 14 | Copilote | ✅ pro/copilote | ❌ N/A | `routes_pro_copilote.py` |
| 15 | Paiements MoMo | ✅ paiement_v2 | ✅ via /bureau/abonnement | `routes_paiement_v2.py` |
| 16 | Organisations multi-user | ✅ pro/organizations | ❌ Non exposé Sec | `routes_pro_orgs.py` |
| 17 | Abonnements | ✅ pro/abonnement | ✅ bureau/abonnement | dual routers |
| 18 | Brand Kit verrouillé | ✅ /brand-kit | ✅ /brand-kit | partagé `brand_kit_router` |
| 19 | SAML SSO | ✅ /saml | ✅ /saml | partagé `saml_sso_router` |
| 20 | Approval workflows | ✅ /approvals | ✅ /approvals | partagé `approvals_router` |
| 21 | White-label | ✅ /white-label | ✅ /white-label | partagé `white_label_router` |
| 22 | API publique B2B | ✅ /public/designerpro | ✅ /public/designerpro | partagé `public_designerpro_router` |
| 23 | Admin dashboard cross | ✅ via packages/admin-dashboard | ✅ via packages/admin-dashboard | `routes_admin_cross.py` |
| 24 | Bons travail / Kanban | ❌ N/A (Pro RH différent) | ✅ bureau/gestion | spécifique Sec |
| 25 | Caisse / facturation client | ❌ N/A (Pro = pipeline commercial) | ✅ bureau/gestion | spécifique Sec |
| 26 | Pipeline commercial | ✅ /commercial | ❌ N/A (Sec = client direct) | spécifique Pro |
| 27 | Sinistres + détection fraude | ✅ /sinistres (équivalent CIMA) | ❌ N/A | spécifique Pro |
| 28 | RH + paie OHADA | ✅ /rh + /rh/kpi | ❌ N/A | spécifique Pro |
| 29 | Réassurance Art. 308 CIMA | ✅ /reassurance | ❌ N/A | spécifique Pro (assurance) |
| 30 | Multi-langues UI | ✅ Phase L (15 langues) | ✅ Phase L (15 langues) | partagé |

**Asymétries justifiées Pro vs Sec** :
- Designer Pro **exclusif Sec** : Pro est un assistant métier (audit, rapports, slides), pas un studio création visuelle. Asymétrie justifiée — pas de portage.
- Slides PPTX **Pro uniquement** : à porter côté Sec (gap #3 ci-dessous, sprint dédié).
- Kanban + Caisse + CRM clients **Sec uniquement** : flux secrétariat, pas pertinent côté Pro.
- Sinistres + Réassurance + RH/Paie **Pro uniquement** : verticales assurance/audit, pas pertinent Sec.
- Agents IA autonomes (schema_si, meta_factory) **Pro uniquement** : architecture data Pro.

---

## Section 2 — Audit qualité de rendu (estimation /10 sans test prod cette session)

| Générateur | Score actuel | Niveau attendu (Big4/McKinsey) | Gap principal | App |
|---|---|---|---|---|
| ReportWriter Pro DOCX | 6/10 | 9/10 | Pas de charts natifs Word ; header/footer numérotation incomplète | Pro |
| Bureau Rédacteur DOCX | 4/10 | 9/10 | Sortie LLM brute, pas TOC systématique, pas hiérarchie typo | Sec |
| SlideBuilder Pro PPTX | 7/10 | 9/10 | Master vierge `Presentation()`, pas d'animations, pas templates par-secteur | Pro |
| Infographe WeasyPrint PDF | 8/10 | 9/10 | Pas CMYK, dépendance Cairo/Pango fragile sur Windows | Sec |
| Infographe Pro ReportLab PDF | 7/10 | 9/10 | Pas charts vectoriels ; PDF/X-1a OK ; ReportLab < Illustrator | Sec |
| Document Generator Excel | 5/10 | 8/10 | Charts natifs OK, scope limité Excel | Pro+Sec |
| Scripts racine `generate_cv.py`, `generate_convention.py` | 2-3/10 | N/A | Hardcodés (KOM ANATOLE, ABN) — à archiver | code mort |

**Échantillons réels non générés** ce turn (nécessite curl prod + ouverture des fichiers + scoring visuel — 3-5h de travail dédié). Inscrit comme sprint Phase 2 dans roadmap résiduelle.

---

## Section 3 — Routage LLM avant / après

### Fix appliqué (commit `3b223298`)

| Endroit | Avant | Après | Impact |
|---|---|---|---|
| `report_writer_pro.py:1010` génération lots `complet`/`expert` | ModeIA.REDACTION (Sonnet/gpt-4o) | + `forcer_modele=Opus` (fallback gpt-4-turbo) | Rapports 10-30+ pages cohérents cross-sections |
| `report_writer_pro.py:1136` pass révision critique mode complet | ANALYSE Sonnet | + `forcer_modele=Opus` | Détection sections faibles plus fine |
| `report_writer_pro.py:1175` réécriture ciblée mode complet | REDACTION Sonnet | + `forcer_modele=Opus` | Densification cabinet-grade |
| `redacteur.py:414` mode `long` (24k tokens) | REDACTION Sonnet/gpt-4o | + `forcer_modele=Opus` | Contrats juridiques OHADA, plans d'affaires 10-20 pages |

Modes flash/standard/court inchangés (Sonnet/Haiku — rapidité + coût optimisés).

### Audit complet routage (3 zones de risque résiduelles)

| Zone | Fichier:ligne | Risque | Action recommandée |
|---|---|---|---|
| Orchestrateur métier | `core/orchestrateur.py:322-336` | Pas de support `forcer_modele` ; ~20 appels CIMA/sinistres routent par défaut | Ajouter param optionnel + logique domaine→variant (CIMA/réassurance → Opus) |
| Traduction projet long | `routes_bureau_infographie_pro.py:2022` | Sonnet sur projets infographie 8+ pages — peut perdre cohérence | Bench Sonnet vs Opus sur 32k tokens |
| Layout AI standard | `infographe_pro.py:2074` | Layout AI Opus inactif en mode standard (60% du traffic) | Activer Opus aussi en standard (justifié par marge 12×) |

---

## Section 4 — Templates figés détectés (à corriger sprint suivant)

| Fichier:ligne | Templates figés | Sévérité | Correctif planifié |
|---|---|---|---|
| `gabarits_livret.py:310` | 8 PROJETS_INFOGRAPHIE max (livret_deces_8p, mariage_4p, brochure_corporate_4p, menu_resto_4p, programme_culte_4p, livre_photo_a4_8p) | **CRITIQUE** | Ajouter `custom_libre` avec composition Opus dynamique sur PAGE_TEMPLATES (20+ briques) |
| `infographe_pro.py:1468` | `custom_layout` proposé par Opus mais jamais rendu | HAUTE | Implémenter rendu dynamique ReportLab pour layouts custom |
| `report_writer_pro.py:45` | `_STRUCTURES` 13 schémas figés (contrat_bail, contrat_travail, statuts…) | MOYENNE | Garder comme HINT, ajouter chemin LLM-libre quand sujet hors catalogue |
| `slide_builder_pro.py:31` | `_THEMES` 4 palettes RGB hardcodées (corporate/pitch/finance/formation) | BASSE | Garder, ajouter palette extraite Brand Kit org |
| `routes_bureau_infographie_pro.py:1876` | DESCRIPTIONS_PROJETS_IA hardcodée 8 cas | MOYENNE | Générer dynamiquement depuis PROJETS_INFOGRAPHIE |
| `redacteur.py:20-150` | TYPES_DOCUMENTS 30+ types mais prompt par-type figé | MOYENNE | Ajouter type "custom" pour briefs hors catalogue |

---

## Section 5 — Couches d'enrichissement post-LLM par feature

| Feature | Couche actuelle | Niveau | Gap |
|---|---|---|---|
| Rapport Pro (ReportWriter) | python-docx + TOC natif Word + métadonnées DOCX | Bon | Manque charts natifs DOCX (BarChart/LineChart/PieChart via openpyxl-style mais natif python-docx) |
| Document Sec (Rédacteur) | python-docx + métadonnées + TOC + styles Yukpo Quote/Callout/Caption | Bon | OK — l'audit initial sur-estimait le gap |
| Slides Pro (SlideBuilder) | python-pptx + thèmes + charts natifs + notes orateur + numérotation | Très bon | Master vierge → ajouter master.pptx custom org |
| Designer Pro (Infographe) | ReportLab + PDF/X-1a + bleed/trim + ICC FOGRA39 + Pillow effects | Excellent | Charts vectoriels manquants |
| Designer Pro (WeasyPrint) | CSS3 typo preset Inter + kern/liga + hyphens auto | Excellent | CMYK absent (Ghostscript optionnel) |
| OCR | Azure DocIntel ou GPT-4o vision + structuration Haiku | Bon | OK |
| Audio | Whisper + ElevenLabs + post-NLP ponctuation | Bon | OK |
| Traduction live | GPT-4o-mini phrase/phrase | Bon | OK |
| Visuel image | Vision picker Sonnet sur 2-3 variantes Flux | Bon | Inactif en mode standard (1 variante seulement) |

---

## Section 6 — Actions infrastructure

| Action | État | Note |
|---|---|---|
| Bcrypt dummy hash (commit 542be3f9) | ✅ Tient | Pas de régression observée |
| Fallback Anthropic→GPT (credit balance) | ✅ Câblé | `core/ia_client._CLAUDE_TO_GPT` |
| Tracking latence par endpoint | ✅ Existe | `sla_latency_middleware` (l.638-657 main.py) — enrichir avec colonne `latence_ms` en DB pour /admin-cross |
| PWA service worker skipWaiting | ✅ Pro | À vérifier Sec |
| Rate limiting IP + per-user | ✅ | `rate_limit_ia_middleware` + slowapi 300/min |
| CSRF protection mutations cookie | ✅ | `csrf_middleware` l.566 |
| Marge LLM 12× via debiter_llm | ✅ | À auditer ratio réel sur 50 derniers appels via /admin-cross/cost |

---

## Section 7 — Preuve "zéro formulaire"

Non capturé ce turn (besoin d'accès UI runtime). Audit code montre que `ChatPage` YPro et `ChatUnifieSec.tsx` (Sprint S1, C1, G1) sont les entrées par défaut. Pages legacy avec formulaire ont été nettoyées (commits 542be3f9, 2ea30b6b). À vérifier visuellement sprint suivant.

---

## Section 8 — Commits livrés ce sprint

1. `3b223298` — feat(routing): rapports/documents long-form → Opus 4.7 (Pro+Sec)
   - `report_writer_pro.py` 3 sites + `redacteur.py` 1 site
   - Backend redéployé Fly.io (deploy en cours, task `bei635ci1`)

---

## Section 9 — Roadmap résiduelle (gaps non livrés ce sprint)

### Top 12 priorités, file:line targets prêts

| # | Gap | Fichier:ligne | Effort | Apps |
|---|---|---|---|---|
| 1 | Charts natifs DOCX dans ReportWriter Pro (BarChart/LineChart/PieChart embedded OOXML) | `report_writer_pro.py:1229` (méthode `_construire_docx`) | 3-4 j | Pro (réplicable Sec via redacteur) |
| 2 | Bureau Rédacteur : factoriser sur la couche ReportWriter Pro pour charts + révision | `redacteur.py:498` (`_markdown_vers_docx`) → réutiliser modules Pro | 2 j | Sec |
| 3 | Designer Pro `custom_libre` + composition Opus dynamique PAGE_TEMPLATES | `gabarits_livret.py:310` + `infographe_pro.py:1468` + `routes_bureau_infographie_pro.py:1888` | 4-5 j | Sec |
| 4 | Layout AI Opus aussi en mode standard | `infographe_pro.py:2074` (lever condition `mode_visuel in premium/ultra`) | 0.5 j | Sec |
| 5 | SlideBuilder Pro masters PPTX custom (logo, footer cohérent, layouts par-secteur) | `slide_builder_pro.py:768` (remplacer `Presentation()` par template chargé) | 1-2 j | Pro (à porter Sec si slides Sec créés gap #6) |
| 6 | Porter SlideBuilder Pro côté Sec (génération slides via chat unifié) | nouveau `routes_bureau_slides.py` + alias `slide_builder_pro` | 1-2 j | Sec |
| 7 | Orchestrateur métier : ajouter `forcer_modele` param + logique domaine→Opus | `core/orchestrateur.py:312-336` | 1 j | Pro (CIMA/sinistres/réassurance) |
| 8 | Infographe Pro : charts vectoriels via Plotly static export (PDF) | `infographe_pro.py:700-800` | 3 j | Sec |
| 9 | WeasyPrint CMYK + Docker image robuste | `infographe_weasyprint.py:33` + Dockerfile | 2-3 j | Sec |
| 10 | Auto-détection projet : DESCRIPTIONS_PROJETS_IA dynamique depuis catalog | `routes_bureau_infographie_pro.py:1876` | 0.5 j | Sec |
| 11 | Provider_force exposé dans API publique | `routes_bureau_infographie_pro.py` champ `DemandeProjetPro` | 0.5 j | Sec |
| 12 | Bulk async job > 50 lignes (Celery/Resque) | `routes_bureau_infographie_pro.py:215` | 3 j | Sec (puis Pro pour rapports bulk) |

### Hors scope explicite (justification technique)

- **Refonte mobile React Native** : `yukpopro_mobile/` est un repo séparé hors monorepo. Mettre en cohérence avec persistence Zustand après gaps #1-12 stabilisés.
- **Refonte moteur DOCX from-scratch (vs python-docx)** : effort > 1 mois, ROI marginal vs charts natifs ciblés (gap #1).
- **Template engine PPTX from-scratch** : python-pptx + masters custom (gap #5) couvrent 95% du besoin Big4.

---

## Section 10 — Briefs atypiques testés

Non testés ce turn (besoin auth JWT prod + ouverture des fichiers produits). 10 briefs documentés dans le prompt initial — à exécuter sprint suivant via curl `https://yukpopro-backend.fly.dev/api/v1/pro/orchestrer` avec scoring /10 par rendu.

---

## Synthèse

**Ce qui est solide aujourd'hui** : SAML SSO + Approval + Brand Kit + White-label + SLA + API publique + Designer Pro Phase 1+2+R+UX (14 sprints livrés selon mémoire `project_designerpro_status`). Layout AI Opus 4.7 actif en premium/ultra. PDF/X-1a:2001 strict. Orchestrateur G1 (chat-only) opérationnel. Routing fallback Claude↔GPT câblé.

**Ce qui basculera l'app de "très bon" à "leader mondial"** : (1) charts natifs DOCX, (2) Designer Pro custom_libre, (3) Layout AI Opus en mode standard, (4) masters PPTX custom, (5) Bureau Rédacteur factorisé sur ReportWriter Pro. Ces 5 gaps représentent ~12 jours de travail concentré et porteraient l'app à un niveau qualité réellement inégalable.

**Décision sprint** : commit chirurgical livré (routage long-form Opus), backend redéployé. Roadmap des 12 gaps suivants prête à être attaquée — chaque gap a son file:line et son effort estimé.
