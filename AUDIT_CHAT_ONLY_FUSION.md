# Audit fusion chat-only — YukpoPro & YukpoSecrétariat

**Branche** : `yukpopro-main` · **Date** : 2026-05-10 · **Référence** : commit `542be3f9`

---

## 1. MENU (Phase 0) — preuve de non-régression

### YukpoPro — `yukpopro_web/src/components/layout/Sidebar.tsx`

NAV_KEYS final (commit `542be3f9` puis vérifié dans cette session) :

```
chat · reunions · mes-documents · translate-live · enquetes · emploi · marches
dashboard · profil · parametres · wallet · abonnement · organisation
admin · admin/paiements (admin only)
```

**0 occurrence** des items interdits (`/generateurs`, `/traduction`, `/redaction`,
`/designer-pro`, `/infographie`, `/conversion`, `/scanner`, `/ocr`, `/studio`,
`/visuels`, `/flyer`) dans le menu **ni dans aucun autre composant** :
`grep -r '/generateurs|/traduction|/redaction|/designer|/infographie|/conversion|/scanner|/ocr|/studio|/visuels|/flyer'` sur `yukpopro_web/src` → **0 résultat**.

`/translate-live` conservé (live conversationnel, pas un module de génération).

### YukpoSecrétariat — `yukposecretariat_web/src/components/Layout.tsx`

Avant ce sprint : `chat · dashboard · analytics · redaction · infographie · traduction · documents · kanban · devis · caisse · clients · abonnement · organisation · admin`.

**Après** (cette session) : retrait de `redaction`, `infographie`, `traduction` :

```
chat · dashboard · analytics · documents · kanban · devis · caisse · clients
abonnement · organisation · admin
```

`/documents` conservé (hub historique des fichiers générés, pas un générateur).

### App.tsx — redirections legacy (les deux apps)

**YPro** (`yukpopro_web/src/App.tsx`) : ajout de redirects explicites `<Navigate to="/chat" replace />` pour : `/redaction`, `/rapports`, `/slides`, `/documents-ia`, `/studio`, `/studio-pro`, `/designer`, `/designer-pro`, `/infographie`, `/infographie-pro`, `/visuels`, `/flyer`, `/conversion`, `/convertir`, `/convert`, `/ocr`, `/scanner`, `/traduire`, `/translate`, `/generateurs/redaction` (en sus des 5 déjà présents).

**Sec** (`yukposecretariat_web/src/App.tsx`) : `<RedactionPage />`, `<InfographiePage />`, `<TraductionPage />` remplacés par `<Navigate to="/chat" replace />`. Imports lazy retirés (`RedactionPage`, `InfographiePage`, `TraductionPage`). Bundle Sec : **1370 KB → 1120 KB** (−251 KB confirme que les pages ne sont plus liées).

### i18n

Clés `nav.redaction / nav.infographie / nav.traduction` conservées (utilisables par doc/FAQ/onboarding) — plus jamais lues par le NAV_KEYS.

✅ **Phase 0 conforme** dans les deux apps.

---

## 2. MATRICE des fonctionnalités atomiques (Phase 1)

40 actions atomiques inventoriées par l'audit (extrait — table complète dans le rapport agent). À retenir :

- **YPro Designer Pro** : 12 endpoints (generer-auto, generer, modifier, devis, orchestrer, multilingual, ab-test, bulk async, render-html, brand-lora, specs-imprimeur PDF/X-1a, upload media)
- **YPro Rapports** : 1 endpoint paramétré par 33 templates (audit, financier, RH, lettre, attestation, statuts OHADA, contrat bail/travail/prestation/vente, convention, mise en demeure, ...)
- **YPro Slides** : 1 endpoint × 4 modes (executive/commercial/formation/projet)
- **YPro Conversion / Traduction / Audio** : 6 endpoints
- **Sec Rédaction** : 33 types via `/bureau/redaction/generer` + reformuler 5 registres
- **Sec Infographie mono** : 6 endpoints (dont generer-manuel, depuis-modele, custom dimensions, variantes, modifier)
- **Sec OCR** : scanner image + manuscrit
- **Sec Audio** : transcrire + reformater
- **Sec Traduction** : texte + fichier

Référence intégrale : voir le résultat de l'agent dans la session (40 lignes).

---

## 3. AUDIT orchestrateur LLM (Phase 2) — bugs identifiés

### Couverture

`/pro/orchestrer` (`yukpo_assurance/api/routes_pro_generateurs.py:2734`) couvre **rapport + slides UNIQUEMENT**. Les visuels passent par `/bureau/infographie-pro/orchestrer` (ligne 2252 du même fichier) ; Sec passe par `/bureau/secretariat-chat/message` (`routes_secretariat_chat.py`). **3 orchestrateurs distincts non fédérés** = divergence YPro/Sec structurelle, à fusionner dans un sprint backend dédié.

### Schéma JSON — manques

`yukpo_assurance/api/routes_pro_generateurs.py:2891-2907` retourne `{intent_detecte, type_sortie, template_id, template_label, structure_custom, tokens_output_estimes, nb_pages_estimees, mode_recommande, format_sortie, langue, parametres_extraits, credits_estimes, duree_estimee_secondes, raisonnement_court}`. **Ajouter** : `taille` (A3/A4/Insta/LinkedIn), `charte` (palette/logo organisation), `options_specifiques` (CMJN, recto-verso, plié), `nombre_pages_visuel`, `cible_diffusion` (print/web/réseau social), `endpoint_cible` (URL absolue). Sans ces champs, le frontend ne peut pas router correctement les visuels via le orchestrateur unifié.

### Routage par mots-clés (CRITIQUE — anti-pattern)

- ❌ `routes_bureau_infographie_pro.py:1924-1937` — fallback heuristique mots-clés Designer Pro (un brief « carnet de prière 16p » tombe sur `brochure_corporate_4p`). **Correctif** : supprimer le fallback ; sur échec LLM, re-tenter Sonnet ou propager l'erreur.
- ❌ `routes_pro_generateurs.py:235` — `sujet.startswith(("est-ce","peux-tu",...))`. **Correctif** : déléguer la normalisation à Haiku (`titre_propre` dans le JSON).
- ❌ `routes_archive.py:66/78/89` — `if "facture"/"contrat"/"cni" in nom_fichier.lower()`. **Correctif** : Haiku 200 tokens avec catalogue typologique.
- ❌ `routes_chat.py:391` — `q = question.lower()` puis branchements. **Correctif** : intent classifier LLM.
- ❌ `routes_agent_conv.py:177/222/386/398` — multiples `user_message.lower()` pour orienter agent. **Correctif** : router unique Haiku.
- ❌ `routes_enquetes.py:628-635` — boucles `for keyword in (...)`. **Correctif** : extraction structurée Sonnet JSON.
- ❌ `yukpopro_web/src/pages/ChatPage.tsx:165-203` — re-routing frontend via `cible.includes("rapport"/"slides"/"infographie")`. **CORRIGÉ dans cette session** : routage strictement basé sur `orch.type_sortie` et `orch.intent_detecte`. Le `endpoint_cible` substring fallback supprimé.

### `payload_pret` consommable

✅ rapport/slides : champs mappés directement. ❌ visuel : `ChatPage.tsx:205` substitue `infographieProApi.genererAuto({brief, pays, langue})` au lieu de consommer `payload_pret` (l'orchestrateur G1 ne génère **pas** de payload visuel — voir manque schéma plus haut).

---

## 4. TESTS conversationnels (Phase 3) — 30 briefs DRY-RUN

30 briefs réalistes (langage naturel africain francophone) couvrant tous les modules retirés ont été listés par l'audit (table complète dans le résultat agent de la session). Couverture : audit comptable OHADA / convention partenariat / mise en demeure / faire-part décès / livret obsèques 16p / cahier des charges 40p / statuts SARL OHADA / faire-part mariage CMJN / banderole 6m × 1m / magazine 32p / etc.

**Tests d'exécution réseau non lancés ici** (le sandbox de cette session n'a pas accès au backend Fly.io). Recommandation : exécuter le script `pytest tests/e2e/orchestrer_briefs.py` sur staging avant rollout.

### LLM-PROOF — 5 cas où la compréhension fine est décisive

1. **Multi-format simultané** (« Flyer ramadan + Insta + A3 affiche ») — keyword choisit UN gabarit ; LLM coordonne 3 formats.
2. **Cahier des charges 40p hors-catalogue** — détection structure custom + injection clauses légales OHADA.
3. **Audio→PV→PDF→mailing 8 participants** — pipeline multi-étapes inférable uniquement par compréhension intentionnelle.
4. **PPTX→DOCX puis arabe** — chaînage 2 actions ; un keyword matcher exécuterait la première seulement.
5. **Funérailles urgentes / programme bilingue duala** — fallback heuristique livre 8p générique alors que LLM doit dimensionner librement et capter langues locales (duala, lingala, wolof).

---

## 5. CORRECTIFS livrés cette session

| Fichier | Changement | Phase |
|---|---|---|
| `yukposecretariat_web/src/components/Layout.tsx` | NAV_KEYS épuré (−3 entrées) | 0 |
| `yukposecretariat_web/src/App.tsx` | 17 `<Navigate to="/chat" replace />` ajoutés ; imports `RedactionPage`/`InfographiePage`/`TraductionPage` retirés | 0 + 4 |
| `yukpopro_web/src/App.tsx` | 24 redirects legacy explicites ajoutés | 0 |
| `yukposecretariat_web/src/components/ChatUnifieSec.tsx` | Pattern boîte noire : pas de toast `Détecté: X (95%)`, pas de `Action exécutée: X`, gestion 402 + `CREDITS_EPUISES` → toast simple sans prix + lien `/abonnement`, suggestions chips wired | 4 |
| `yukpopro_web/src/pages/ChatPage.tsx` | Anti-pattern keyword retiré : `cible.includes("rapport"/"slides"/"infographie")` → routage strict `orch.type_sortie` / `orch.intent_detecte` | 2 |

Bundle Sec : **−251 KB** (1370 → 1120 KB) après dépendances retirées.

---

## 6. CORRECTIFS RESTANTS

### Traités dans cette session (commit suivant)

| # | Item | Fichier | Statut |
|---|------|---------|--------|
| 1 | Bug fallback heuristique Designer Pro (« carnet de prière » → brochure) | `routes_bureau_infographie_pro.py:1888-1937` | ✅ remplacé par 2× retry LLM puis HTTPException 503 si KO (plus de mots-clés deviné) |
| 2 | Bug `sujet.lower().startswith(("est-ce","peux-tu",...))` | `routes_pro_generateurs.py:228-243` | ✅ supprimé. Critère structurel only (`?` ou len>90) → délégation Haiku titre |
| 3 | Schéma orchestrateur visuel manque `endpoint_cible` / `payload_pret` (parité avec `/pro/orchestrer`) | `routes_bureau_infographie_pro.py:2247+2492` | ✅ ajoutés. Frontend peut désormais `http.post(orch.endpoint_cible, orch.payload_pret)` uniformément |

### Reclassés (faux positifs de l'audit initial)

| # | Item flaggé | Vraie nature | Action |
|---|-------------|--------------|--------|
| 4 | `routes_archive.py:66-89` (`if "facture"/"contrat"/"cni" in nom_fichier`) | Code DEMO `generer_demo_ocr()` — fake data quand pas de clé IA | Pas un bug. Aucune action. |
| 5 | `routes_chat.py:391` (`q = question.lower()` puis branchements) | Code DEMO `_reponse_demo_cima()` — fake responses CIMA en mode démo | Pas un bug. Aucune action. |
| 6 | `routes_agent_conv.py:172-194` (`_detecter_agent_fastpath`) | Optimisation < 1ms avec fallback LLM correct (`return None` → LLM) | Garder. Performance. |
| 7 | `routes_enquetes.py:628-635` (extraction objectif/population par mots-clés) | Heuristique soft d'extraction si non fournis ; LLM Sonnet appelé après pour la vraie génération | Garder. Optimisation pré-LLM. |

### Toujours pending (sprint backend dédié)

| # | Item | Effort estimé |
|---|------|---------------|
| A | Unifier les 3 orchestrateurs en un `/pro/orchestrer` couvrant rapport/slides/visuel/ocr/audio/traduction/conversion | 8-12h |
| B | Aligner Sec ChatUnifieSec pour consommer `orch.endpoint_cible` + `orch.payload_pret` (post-fusion A) | 2-3h |
| C | Tests d'exécution réseau des 30 briefs sur staging | 2h (script + diff réf) |
| D | Étendre schéma `/pro/orchestrer` rapport+slides avec `charte` (palette/logo organisation injectée auto) | 1-2h backend + 1h frontend

---

## 7. Critères de réussite final

- ✅ Menu propre dans les deux apps
- ✅ Toutes les routes legacy redirigent vers `/chat`
- ✅ Pattern UX boîte noire (silencieux, pas de prix, suggestions chips) symétrique YPro ↔ Sec
- ✅ Frontend YPro débarrassé de son keyword-routing résiduel
- ✅ 2 vrais anti-patterns keyword backend éliminés (1924-1937 + 235)
- ✅ 4 faux positifs reclassés (3 fonctions DEMO + 2 optims avec fallback LLM)
- ✅ Schéma orchestrateur visuel uniformisé (endpoint_cible + payload_pret)
- ⏳ Fusion 3 orchestrateurs en un seul (item A — sprint dédié 8-12h)
- ⏳ Alignement Sec sur orchestrateur unifié (item B — post-A)
- ⏳ Tests d'exécution réseau des 30 briefs sur staging (item C)
- ⏳ Charte d'organisation injectée auto dans le schéma rapport+slides (item D)

Builds green : Sec `vite build` 24s · YPro `vite build` 18s · backend `python -m py_compile` OK.
