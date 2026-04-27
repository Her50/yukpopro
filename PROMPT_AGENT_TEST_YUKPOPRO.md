# Prompt — Remplacement Marketing → Infographie + Agent de Test Humain YukpoPro

> Ce prompt est **autonome** : il sera exécuté dans une nouvelle session Claude Code sans historique. Toutes les informations nécessaires sont incluses.

---

## Contexte global du projet

**YukpoPro** est une plateforme SaaS professionnelle construite dans `yukpo_assurance/` (backend FastAPI) + `yukpopro_web/` (React + Vite) + `yukpopro_mobile/` (React Native Expo). Le backend est déployé sur **Fly.io** (`yukpopro-backend.fly.dev`), le web sur **Vercel** (branche `yukpopro-main`, auto-deploy).

Un module parallèle **YukpoSecrétariat** (product standalone secrétaires/infographistes) partage l'infrastructure : ses routes sont sous `/api/v1/bureau/*` (rédaction IA, OCR, traduction, audio→doc, **infographie**, gestion, abonnement). L'infographie secrétariat est **nettement plus complète et aboutie** que l'ancien module marketing de YukpoPro.

**Branche de travail** : `yukpopro-main` (push ici déclenche les deploys).
**Credentials admin (mode `ORASS_MODE=simulation`)** : email `admin@yukpopro.cm`, mot de passe `Admin123!` (le mot de passe en base est ignoré en simulation — seul `yukpo2025` ou `Admin123!` passent).

### URLs de production (à utiliser dans les tests E2E)

| Ressource | URL |
|---|---|
| **Web (Vercel)** | `https://yukpopro-web.vercel.app` |
| **Backend API (Fly.io)** | `https://yukpopro-backend.fly.dev` |
| **Health check** | `https://yukpopro-backend.fly.dev/health` |
| **Docs OpenAPI** | `https://yukpopro-backend.fly.dev/docs` |

Le web appelle l'API via rewrites Vercel (`/api/*` → Fly.io) définis dans [yukpopro_web/vercel.json](yukpopro_web/vercel.json) ; en local la variable est `VITE_API_URL`.

### Infos déploiement & debug

**Fly.io** — app `yukpopro-backend`, région `cdg` (Paris), port 8080, config dans [yukpo_assurance/fly.toml](yukpo_assurance/fly.toml).
Secrets pertinents déjà configurés côté Fly (ne PAS les réécrire) : `SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASSWORD`, `ORASS_MODE=simulation`, `DATABASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.

Commandes utiles (Git Bash sous Windows) :
```bash
# Déclencher deploy = push
git push origin yukpopro-main

# Statut des workflows GitHub Actions
gh run list --branch yukpopro-main --limit 3

# Logs build/deploy GitHub Actions
gh run view <RUN_ID> --log-failed | tail -60

# Logs runtime Fly.io (diagnose crash au boot)
~/.fly/bin/flyctl.exe logs -a yukpopro-backend --no-tail | tail -60

# Status machines Fly
~/.fly/bin/flyctl.exe status -a yukpopro-backend

# Restart manuel
~/.fly/bin/flyctl.exe machine restart -a yukpopro-backend

# Test backend health
curl -sS https://yukpopro-backend.fly.dev/health

# Ouvrir la page web (Windows)
start https://yukpopro-web.vercel.app
```

**Développement local** (optionnel) :
```bash
# Backend
cd yukpo_assurance && uvicorn api.main:app --reload --port 8000

# Web
cd yukpopro_web && npm install && npm run dev     # http://localhost:5173

# Mobile
cd yukpopro_mobile && npm install && npx expo start
```

**Déploiements déclenchés automatiquement** par push sur `yukpopro-main` via workflows :
- [.github/workflows/deploy-fly.yml](.github/workflows/deploy-fly.yml) — backend (seulement si `yukpo_assurance/**` change)
- [.github/workflows/deploy-vercel.yml](.github/workflows/deploy-vercel.yml) — web

---

## MISSION 1 — Remplacer intégralement le module Marketing YukpoPro par le module Infographie YukpoSecrétariat

### Ce qu'il faut supprimer (ancien Marketing)

**Backend** — ancien :
- `yukpo_assurance/modules/marketing/visual_generator.py`
- `yukpo_assurance/api/routes_pro_marketing.py` (endpoints `POST /api/v1/pro/marketing/visuel/generer`, `GET /api/v1/pro/marketing/visuels`, `DELETE /api/v1/pro/marketing/visuels/{id}`)
- Enregistrement du router dans `yukpo_assurance/api/main.py`

**Web** — ancien :
- Tab `"marketing"` dans `yukpopro_web/src/pages/GenerateursPage.tsx` (c'est la page **Yukpo Studio** — voir ligne 740, l'identifiant du tab est `"marketing"`, ligne 755)
- Tous les états + fonctions liés à la génération visuel marketing (`handleGenererVisuel`, `marketingApi.genererVisuel`, `VisuelMarketingSpec`, etc.)
- Méthodes `marketingApi` dans `yukpopro_web/src/api/client.ts` (`genererVisuel`, `listerVisuels`, `supprimerVisuel`) et le type `VisuelMarketingSpec`, `VisuelSummary`

**Mobile** — ancien :
- `yukpopro_mobile/src/api/client.ts` → objet `marketingApi` (même méthodes)
- Toute référence dans `yukpopro_mobile/src/screens/GenerateursScreen.tsx` (vérifier)

### Ce qu'il faut brancher (nouveau Infographie)

**Backend — déjà existant, NE PAS RÉÉCRIRE** :
- Module : `yukpo_assurance/modules/bureau/infographe.py`
- Routes : `yukpo_assurance/api/routes_bureau_infographie.py` déjà montées sous `/api/v1/bureau/infographie/*` :
  - `GET  /bureau/infographie/gabarits` — liste gabarits (flyer_a5, carte_visite, diplome, etc.)
  - `POST /bureau/infographie/generer` — brief libre IA → PDF print-ready + preview PNG
  - `POST /bureau/infographie/generer-manuel` — spec directe sans IA
  - `POST /bureau/infographie/generer-depuis-modele` — upload image modèle + brief
  - `POST /bureau/infographie/generer-custom` — format custom (dimensions libres)
  - `GET  /bureau/infographie/fichier/{fichier_id}` — télécharge PDF ou PNG

**Travail à faire** :
1. **Web** : dans [GenerateursPage.tsx](yukpopro_web/src/pages/GenerateursPage.tsx) remplacer le tab `"marketing"` par un tab `"infographie"` (label "Infographie Pro", même badge PRO). Créer toute l'UI de ce tab en mode sophistiqué (multi-étapes : choix gabarit → brief IA OU spec manuelle OU upload modèle → preview PNG avec zoom → download PDF print-ready). Utiliser les 5 endpoints bureau/infographie ci-dessus.
2. **Web — api/client.ts** : ajouter un objet `infographieApi` avec `listerGabarits`, `genererDepuisBrief`, `genererManuel`, `genererDepuisModele` (multipart), `genererCustom`, `urlTelechargement(fichier_id)`. Supprimer `marketingApi` et types associés.
3. **Mobile** : même travail dans `yukpopro_mobile/src/api/client.ts` (ajouter `infographieApi`, retirer `marketingApi`). Dans `GenerateursScreen.tsx` ajouter un onglet/section Infographie avec workflow équivalent (React Native + `expo-document-picker` / `expo-image-picker` pour upload de modèle, affichage preview via `Image` base64).
4. **Backend cleanup** : supprimer `modules/marketing/` + `api/routes_pro_marketing.py` + son enregistrement dans `api/main.py`. S'assurer qu'aucun autre module n'importe `from modules.marketing`.
5. **Visibilité Mes Documents** : vérifier que les PDF/PNG générés par infographie sont persistés dans `data/generated/bureau/` avec le préfixe `bureau_pdf_{user_id}_...` (pour apparaître dans le bureau documents). Si l'endpoint infographie ne le fait pas déjà, ajouter la persistance.

**Commit** : un commit propre `refactor(studio): remplace marketing par infographie (plus complet)` puis push sur `yukpopro-main`. Surveiller le deploy Fly.io (`gh run list --branch yukpopro-main --limit 3`, puis `~/.fly/bin/flyctl.exe logs -a yukpopro-backend --no-tail | tail -40` si échec).

---

## MISSION 2 — Créer l'Agent de Test QA Humain de YukpoPro

> **Ne commencer qu'après validation Mission 1 et confirmation que le deploy est OK.**

### Philosophie

L'agent doit se comporter comme un **vrai QA humain senior** — pas un simple health-checker. Il doit :

- Se connecter à la page web **en production** (`https://yukpopro.vercel.app` ou équivalent — à confirmer avec l'utilisateur) via vrai navigateur (**Playwright headed pour screenshots + headless pour vitesse**).
- Tester **toutes** les fonctionnalités — sans exception, comme listé plus bas.
- Soumettre des **vrais inputs réalistes** (vraies questions copilote, vrais briefs, vrais fichiers PDF/DOCX/audio via fixtures).
- **Télécharger et ouvrir** chaque artefact généré (DOCX, PDF, PNG, XLSForm, audio) et **juger sa qualité** :
  - Lisibilité, cohérence, absence de placeholders bidons (`lorem ipsum`, `TODO`, `{{variable}}` non interpolée, réponses LLM tronquées)
  - Respect du format demandé (nombre de pages, dimensions PDF, structure docx avec titres/sections)
  - Pour les infographies : dimensions print-ready correctes, pas de débordement, rendu graphique pro
  - Pour les rapports IA : profondeur du contenu, pas de réponses "évasives" style `Je suis un LLM et je ne peux pas...`
- Capturer **screenshots systématiques** de chaque écran clé + annoter les défauts.
- Produire un **rapport final structuré** :
  - Par feature : statut (PASS/FAIL/PARTIAL) + qualité rendu (note /10) + captures + critique textuelle + recommandations
  - Synthèse globale : features prêtes prod, features à retravailler, bugs bloquants, dette UX
- **Ne jamais marquer PASS** sur la base d'un seul `200 OK`. Un endpoint qui répond mais produit un document vide ou moche → FAIL.

### Stack de test

- **Playwright (Node ou Python)** pour le pilotage navigateur
- **pypdf / pdfplumber** pour extraire le texte + compter pages des PDF générés
- **python-docx** pour valider structure DOCX (paragraphes, titres, tableaux)
- **Pillow** pour vérifier dimensions + couleurs dominantes des images
- **Claude API (claude-opus-4-7 ou claude-sonnet-4-6)** pour juger la qualité du contenu textuel/visuel des artefacts (passer le texte extrait + screenshot à Claude avec une rubrique de notation)
- Stockage des artefacts : `tests/qa_agent/artifacts/YYYY-MM-DD_HHMM/` (screenshots, downloads, rapports)

### Périmètre fonctionnel — workflows attendus par feature

Pour chaque feature ci-dessous : **parcours utilisateur complet** + **critères de qualité spécifiques**. L'agent doit exécuter chaque parcours intégralement et noter la qualité de chaque artefact produit (pas seulement la présence d'une réponse 200).

#### A. Authentification — [LoginPage.tsx](yukpopro_web/src/pages/LoginPage.tsx)
**Parcours** :
1. Charger `/login` → vérifier rendu complet (logo, champs, pas de flash)
2. Tenter login avec mauvais mot de passe → message d'erreur clair en français
3. Login avec `admin@yukpopro.cm` / `Admin123!` → redirection dashboard
4. Refresh → session persistée (token en localStorage, pas de re-login forcé)
5. Logout → redirection `/login`, token purgé

**Qualité** : pas de fuite d'info sur le mauvais mot de passe ("utilisateur inconnu" vs "mauvais mdp" → générique), loader pendant la requête, champ password en `type=password`.

#### B. Dashboard — [DashboardPage.tsx](yukpopro_web/src/pages/DashboardPage.tsx)
**Parcours** : visiter, screenshot, vérifier widgets présents (métriques, derniers documents, quick actions). Cliquer chaque quick action → la bonne page s'ouvre.
**Qualité** : pas de widgets vides sans message ("aucun document encore" > vide), chiffres cohérents, liens fonctionnels.

#### C. Profil Pro — [ProfilPage.tsx](yukpopro_web/src/pages/ProfilPage.tsx)
**Parcours** :
1. Si pas de profil → formulaire création : remplir (nom complet, fonction, expérience `senior`, secteur `assurance`, pays `Cameroun`, compétences, langues)
2. Soumettre → profil créé
3. Uploader CV (fixture `fixtures/cv_exemple.pdf`)
4. Activer veille emploi avec fréquence 24h
5. Modifier un champ → persistance
**Qualité** : validations (email format, champs requis), message de succès, CV uploadé listé avec taille.

#### D. Copilote — [CopilotePage.tsx](yukpopro_web/src/pages/CopilotePage.tsx) + Chat étendu — [ChatPage.tsx](yukpopro_web/src/pages/ChatPage.tsx)

Le backend expose **148 sources RAG** dans `yukpo_assurance/data/rag_knowledge/` couvrant : conventions collectives (20+ pays), CGI, code civil, famille, pénal, travail, commerce, OHADA (AUDCG, AUS, AUSCGIE, AUA, AUPCAP, AUSCOOP), ISO 45001, OIT, AFCFTA, BRVM, etc. — **PAS seulement CIMA**. Le chat doit exploiter l'ensemble.

**Parcours — couverture multi-sources obligatoire** (minimum 8 questions ciblant différentes sources) :
1. CIMA assurance : "Procédure de déclaration sinistre auto au Cameroun sous CIMA, délais et pièces exigées"
2. OHADA : "Différence entre SARL et SAS sous l'Acte Uniforme OHADA révisé, capital minimum"
3. Code travail : "Durée légale préavis licenciement cadre au Sénégal, indemnités selon convention collective banques"
4. Code pénal : "Sanctions pour abus de biens sociaux au Cameroun, articles précis"
5. CGI fiscalité : "Régime TVA prestations de services entre Côte d'Ivoire et Togo, seuil de franchise"
6. Commerce international : "Incoterms applicables sous CISG pour vente Cameroun→France, transfert de risque"
7. Normes : "Obligations ISO 45001 pour compagnie d'assurance employant 50 personnes"
8. BRVM/finance : "Conditions d'introduction en bourse régionale BRVM pour société anonyme"
9. Question de suivi contextuelle (test mémoire multi-tour sur une des questions ci-dessus)
10. Question hors-sujet délibérée (ex: "Quelle est la recette du ndolé ?") → le copilote doit gentiment recadrer sur son périmètre métier

**Qualité exigée** (chaque réponse notée /10 via Claude API, rubrique) :
- **Sources citées explicitement** : au moins 1 référence précise (article + numéro + code/convention/acte), pas de vague "selon la législation"
- **Profondeur** : > 200 mots, structure claire
- **Applicabilité locale** : pays + secteur cohérents
- **Pas de "je suis un LLM"**, pas d'évasion
- **Multi-source** : vérifier qu'au moins **5 sources RAG différentes** ont été sollicitées sur les 10 questions (examiner les métadonnées de réponse / logs si accessibles)
- **Mémoire contextuelle** : la question de suivi doit référencer le tour précédent sans re-demander le contexte

**Test analyse documents joints (Chat)** :
1. Dans `ChatPage.tsx` (chat unifié avec attachement) : joindre fixture `fixtures/contrat_assurance_exemple.pdf` + message "Analyse ce contrat, liste les clauses à risque pour l'assuré, et génère-moi un rapport de revue"
2. Vérifier : réponse cite des clauses précises du doc joint + propose un rapport téléchargeable OU propose de le générer via Studio
3. Joindre fixture `fixtures/donnees_sinistres.xlsx` + message "Analyse ces données de sinistres et donne-moi les 3 insights clés"
4. Vérifier : réponse mentionne des chiffres précis extraits du fichier (pas inventés), identifie tendances réelles
5. Message langage naturel : "Génère-moi un rapport PPT de 10 slides sur l'analyse des données du fichier joint" → le chat doit **déclencher** la génération Studio sans que l'utilisateur aille sur la page Studio

**Qualité analyse documents** : chiffres extraits = vrais chiffres du fichier (vérifiable : l'agent compare à openpyxl/pypdf), pas d'hallucination, rapport généré téléchargeable et cohérent.

#### E. Agents IA — [AgentsPage.tsx](yukpopro_web/src/pages/AgentsPage.tsx)
**Parcours** : lancer recherche sur 3 questions réglementaires précises (ex: "taux de commission maximum courtier assurance vie CIMA"). Vérifier agrégation multi-sources.
**Qualité** : réponses citent des articles précis (numéros, pages), agrégation sans doublons, pas de réponses contradictoires non signalées.

#### F. Yukpo Studio (Générateurs) — [GenerateursPage.tsx](yukpopro_web/src/pages/GenerateursPage.tsx)
Après Mission 1, onglets : `rapport | slides | modeles | conversion | infographie`.

**F.1 — Rapport IA sans fichiers** :
Sujet "Étude de marché assurance santé Cameroun 2025", mode `approfondi`, format DOCX → télécharger, ouvrir avec python-docx → vérifier ≥ 5 pages, sections (exec summary, marché, concurrence, PESTEL, reco), pas de placeholders, tableaux markdown convertis en vrais tableaux Word si pertinent. Note /10 via Claude API (rubrique : structure, profondeur, pertinence locale, actionabilité).

**F.2 — Rapport IA à partir de fichiers uploadés** (`/pro/analyser-et-generer`) :
1. Préparer 3 fixtures distinctes :
   - `fixtures/sinistres_2024.xlsx` — vraies données fabriquées (50 lignes : date, type sinistre, montant, pays, statut)
   - `fixtures/rapport_concurrent.pdf` — PDF 5 pages
   - `fixtures/notes_equipe.docx` — DOCX texte
2. Uploader les 3, instruction : "Génère un rapport analytique stratégique basé sur l'analyse croisée de ces 3 documents"
3. Format sortie : DOCX
4. Télécharger, ouvrir → vérifier :
   - Le rapport **cite des chiffres précis du fichier Excel** (vérifier via openpyxl en pré-comparant les vraies valeurs)
   - Il référence les conclusions du PDF concurrent
   - Il intègre les points des notes équipe
   - **Pas d'hallucination** (l'agent compare chiffres/faits du rapport aux sources)
   - Graphiques présents ou tableaux de synthèse
5. Note /10 stricte : si chiffres inventés → FAIL immédiat.

**F.3 — Analyse Excel → rapport analytique avec graphiques** :
1. Préparer fixture `fixtures/portefeuille_clients.xlsx` (200+ lignes : client, âge, pays, prime annuelle, sinistres, LTV, canal acquisition)
2. Instruction : "Analyse ce portefeuille clients, produis un rapport avec segmentation, top insights, tendances par pays, graphique répartition par canal, tableau top 10 clients par LTV, et recommandations commerciales actionnables"
3. Vérifier dans le DOCX produit :
   - **Tableaux Word réels** (pas du texte markdown non rendu)
   - **Au moins 1 graphique image** intégré (pie, bar, ou line)
   - **Commentaires qualitatifs précis** sous chaque tableau/graphique (pas "voir ci-dessus")
   - **Recommandations actionnables** numérotées (pas génériques)
4. Vérifier chiffres agrégats (LTV moyenne, total primes, % par pays) = vraies valeurs recalculées depuis le XLSX source.

**F.4 — Slides (PPT structuré avec contenu réel)** :
1. Même sujet que F.1 → PPTX → ouvrir avec python-pptx
2. Vérifier ≥ 10 slides, chaque slide a : titre + contenu structuré (≥ 3 bullets OU 1 tableau OU 1 schéma décrit)
3. Pas de slide vide, pas de "lorem", transitions cohérentes (intro → contenu → reco → conclusion)
4. Si génération à partir de fichiers : tester aussi — instruction "Prépare-moi une présentation COMEX de 12 slides à partir du rapport concurrent joint"
5. Note /10 via Claude API (analyser texte extrait + 3 screenshots de slides exportées en image).

**F.5 — Modèles presets** :
Sélectionner au moins 3 presets (ex: "Plan d'affaires assurance", "Étude de faisabilité", "Plan marketing") → générer chacun → qualité.

**F.6 — Conversion de fichiers** :
1. Uploader DOCX → convertir en PDF → vérifier pages, texte extractible (pypdf), mise en forme conservée
2. Uploader PDF → convertir en DOCX → vérifier éditable, pas juste une image collée
3. Tester formats : DOCX↔PDF, DOCX↔ODT si supporté, XLSX↔CSV

**F.7 — Infographie** (nouveau Mission 1) :
Tester les 4 sous-modes (brief IA, manuel, depuis modèle, custom) sur gabarits `flyer_a5`, `carte_visite`, `diplome`, `affiche_a4` :
- Ouvrir PDF → vérifier **300 DPI**, dimensions correctes (A5 = 148×210mm, CB = 85×55mm, A4 = 210×297mm), pas de débordement texte, fontes embarquées
- Ouvrir PNG preview → analyser via Claude API multimodal (prompt : "Cette infographie est-elle print-ready niveau pro ? Défauts visuels (alignement, contraste, hiérarchie, typographie) ? Note /10 avec justification")
- Vérifier que le fichier est bien dans **Mes Documents** (listing + téléchargement OK)

**F.8 — Quality gate global Yukpo Studio** :
- Tout document produit doit avoir un nom de fichier propre (pas `undefined_xxx.docx`)
- Tous sauvegardés dans Mes Documents (F.6 inclus)
- Temps de génération rapport simple < 90s, rapport multi-fichiers < 180s, slides < 120s, infographie < 60s — sinon flagger lenteur

#### G. Réunions — [ReunionsPage.tsx](yukpopro_web/src/pages/ReunionsPage.tsx)
**Parcours** :
1. Tester **enregistrement direct** si possible via Playwright (grant permissions mic, stream un audio file dans le device audio virtuel) ; sinon fallback upload direct
2. Uploader fixture `fixtures/reunion_60s_fr.m4a` (60s, 2-3 voix, scénario assurance réaliste — ex: réunion comité souscription sur un dossier risque industriel)
3. Attendre transcription (timeout 3min, loader présent)
4. Vérifier transcription retournée + détection langue + multi-locuteurs si supporté
5. Lancer génération rapport avec titre "Comité de souscription — Dossier Risque Industriel ACME", participants "Directeur technique, Actuaire, Commercial"
6. Télécharger rapport Markdown + vérifier persistance Mes Documents
7. Tester aussi scénario audio multilingue (FR + quelques mots EN) pour voir comportement

**Qualité** :
- Transcription > **85% précision** (comparer à `fixtures/reunion_60s_fr.txt` texte de référence via similarité Levenshtein ou ROUGE)
- Rapport structuré : **participants identifiés**, **décisions listées**, **plan d'action avec responsables + échéances**, **points à arbitrer**
- Français correct, pas d'anglicismes mal rendus, Markdown valide (titres ##, listes, tableaux)
- Pas de hallucinations (vérifier que décisions listées existent bien dans le verbatim transcrit)

#### H. Enquêtes — [EnquetesPage.tsx](yukpopro_web/src/pages/EnquetesPage.tsx) (tabs : `audio | formulaire | analyse | rapport`)
**Parcours** :
1. Créer étude : titre "Satisfaction clients assurance auto Douala", contexte, population cible, mode `mixte`, méthodologie `exploratoire`
2. **Option 1 formulaire** — uploader fixture `fixtures/protocole_enquete.pdf` + paramètres (n_questions=20)
3. Vérifier réponse : formulaire créé, `xlsform_fichier_id` présent
4. Aller sur **Mes Documents** → vérifier le XLSForm listé
5. Télécharger le XLSForm → ouvrir (c'est un .xlsx) avec openpyxl → vérifier onglets `survey` + `choices` + `settings`, ≥ 15 questions, types valides (text, select_one, integer)
6. **Onglet audio** : uploader fixture audio terrain → transcription apparaît
7. **Onglet analyse** : lancer analyse qualitative → thèmes identifiés
8. **Onglet rapport** : générer rapport DOCX → vérifier dans Mes Documents
9. Télécharger rapport DOCX → ouvrir → structure académique (intro, méthodo, résultats, discussion, conclusion), ≥ 8 pages, citations de verbatims, pas de placeholders
**Qualité exigée** : XLSForm 100% conforme ODK (ouvrable dans KoboCollect), rapport niveau mémoire recherche.

#### I. Emploi / Veille offres — [EmploiPage.tsx](yukpopro_web/src/pages/EmploiPage.tsx)
**Parcours** :
1. Vérifier état veille (active/inactive), config fréquence
2. Définir 3 profils distincts et relancer :
   - "Actuaire confirmé secteur assurance santé Afrique francophone, 8 ans exp, Cameroun/Côte d'Ivoire"
   - "Juriste corporate OHADA, Dakar, bilingue FR/EN"
   - "Souscripteur risques industriels, Libreville"
3. Lancer recherche, attendre complétion (timeout 2min)
4. Pour chaque profil : vérifier ≥ 3 offres, échantillonner 2 liens → HTTP GET → 200 OK (pas 404)

**Qualité** :
- Offres **matchent réellement le profil** (un agent vérifie via Claude API : "cette offre correspond-elle au profil X ? OUI/NON + raison")
- Métadonnées complètes : titre, entreprise, lieu, type contrat, date publication (< 30 jours de préférence), score
- Localisation : priorité Afrique francophone (CM, CI, SN, TG, BJ, BF, GA, ML, NE, GN, CG)
- Pas d'offres dev web si profil actuaire, pas de stages si profil senior 10 ans

#### J. Marchés Publics / Appels d'offres — [MarchesPage.tsx](yukpopro_web/src/pages/MarchesPage.tsx)
**Parcours** :
1. Lancer recherche marchés publics
2. Vérifier ≥ 2 résultats
3. Pour chaque : vérifier métadonnées (pays, autorité contractante, objet, montant estimé si public, date publication, date limite dépôt, source URL)
4. Échantillonner 2 liens source → vérifier accessibles

**Qualité** :
- **Dates limites non expirées** en tête de liste (tri par urgence)
- Géolocalisation Afrique francophone
- Objet clair (pas juste "Marché public n°XXXX")
- Détection doublons (même marché listé 2x → flag)
- Pertinence secteur (filtrer sur profil utilisateur si possible : assurance, services, IT selon config)

#### K. Traduction — [TraductionPage.tsx](yukpopro_web/src/pages/TraductionPage.tsx)
**Parcours** :
1. **Texte direct** : coller paragraphe FR technique 200 mots (terminologie assurance : "réassurance facultative", "provision pour sinistres à payer", "ratio combiné") → traduire FR→EN → qualité terminologie
2. **Texte direct inverse** : EN→FR sur un paragraphe technique
3. **Fichier DOCX** : uploader `fixtures/contrat_fr.docx` (4-5 pages, titres, listes, tableaux, gras) → traduction EN → télécharger DOCX EN → ouvrir avec python-docx → **vérifier structure préservée** (mêmes titres de niveau 1/2, mêmes tableaux, mêmes listes numérotées)
4. **Fichier PDF** si supporté : uploader `fixtures/document_fr.pdf` → recevoir traduction
5. Langues multiples si supporté : tester FR→ES, FR→PT (Portugais pour Angola/Mozambique)

**Qualité** :
- **Aucune phrase FR intacte** dans la sortie EN (vérifier via détecteur langue lingua)
- **Terminologie métier correcte** (Claude API juge : "réassurance facultative" → "facultative reinsurance", pas "optional reinsurance")
- **Structure 100% préservée** : nb paragraphes identique, mêmes niveaux de titres, mêmes cellules de tableaux
- Nombre de mots cible ≈ source ± 20%
- Persistance Mes Documents

#### L. Chat unifié — [ChatPage.tsx](yukpopro_web/src/pages/ChatPage.tsx)
Voir section D (Copilote + Chat étendu) pour les 10 questions multi-sources et les tests d'analyse de documents joints. En complément ici :

**L.1 — Interface** : dictée vocale (si accessible en test automatisé, sinon noter "non testable en headless"), attachement multi-fichiers (PDF + image + XLSX dans le même message), historique persisté après refresh.

**L.2 — Langage naturel → actions** : tester au moins 5 formulations pour déclencher une génération Studio depuis le chat :
1. "Fais-moi un rapport détaillé sur [sujet]"
2. "Prépare une présentation PPT de 10 slides sur les données du fichier joint"
3. "Traduis ce document en anglais"
4. "Génère un visuel flyer A5 pour [événement]"
5. "Analyse ce PDF et envoie-moi un résumé exécutif en DOCX"

**Qualité** : le chat doit **comprendre l'intention** et soit produire directement l'artefact, soit router vers le bon module avec les paramètres pré-remplis. Pas juste une réponse texte "allez dans Studio pour..." — le chat doit **exécuter**.

**L.3 — Conversation longue (10+ tours)** : tester une conversation de 10 messages sur un dossier (assuré fictif, produit assurance, montage) — vérifier cohérence, absence de contradictions, mémoire de tout le contexte.

#### M. Mes Documents — [HistoriqueDocumentsPage.tsx](yukpopro_web/src/pages/HistoriqueDocumentsPage.tsx)
**Parcours** : lister tous les documents produits pendant la session de test, filtrer par type, télécharger 3 au hasard, supprimer 1.
**Qualité** : classement par date, icônes par type corrects (PDF, DOCX, XLSX), noms lisibles, taille affichée.

#### N. Abonnement, crédits (débit + recharge) — [AbonnementPage.tsx](yukpopro_web/src/pages/AbonnementPage.tsx)

**N.1 — Affichage plans et packs** :
- `GET /pro/abonnement/` → mon abonnement courant (plan, solde, consommés, période)
- `GET /pro/abonnement/plans` → liste plans (gratuit, standard, pro, enterprise) avec tarifs FCFA + EUR
- `GET /pro/abonnement/packs-credits` → packs recharge
- `GET /pro/abonnement/historique` → historique transactions
**Qualité** : tarifs en FCFA **et** EUR/USD, comparatif features lisible, soldes à jour.

**N.2 — Test débit crédits (CRITIQUE)** :
1. Relever solde avant (`credits_utilises_avant`, `credits_restants_avant`)
2. Exécuter 5 actions facturantes distinctes :
   - 1 question Copilote (LLM → débit proportionnel tokens)
   - 1 génération rapport Studio
   - 1 génération infographie
   - 1 analyse de fichier Excel (Studio F.3)
   - 1 traduction fichier
3. Relever solde après
4. Vérifier : `credits_utilises_apres > credits_utilises_avant`, delta cohérent avec les tarifs affichés, historique consommation (`GET /pro/abonnement/historique` ou équivalent) liste chaque action avec module + coût
5. Vérifier que `credits_restants` ne part pas en négatif si insuffisant → message d'erreur clair côté UI

**Qualité** : débits cohérents, pas de sur-débit, pas de double-débit (action exécutée deux fois → 2 débits, pas 3 ou 0), logs `consommations_bureau` / `ConsommationTokenDB` écrits.

**N.3 — Test recharge crédits (sans vrai paiement)** :
1. `POST /pro/abonnement/initier-recharge` avec `{pack_id, operateur: "mtn_money", numero_telephone: "+237XXXXXXXX", pays: "CM"}`
2. Vérifier réponse : `reference_paiement` renvoyé, instructions mobile money affichées
3. **NE PAS** appeler `confirmer-recharge` avec un vrai paiement. À la place : vérifier que sans confirmation, le solde n'augmente pas.
4. Vérifier endpoint `GET /pro/abonnement/historique` reflète la recharge "en attente"
5. Tester expiration : référence expirée (24h) doit retourner 400

**Qualité** : UI donne instructions claires (operator, numéro marchand si pertinent), pas de faille où recharge = crédit sans paiement, références uniques.

**N.4 — Test changement de plan** :
Si disponible : initier upgrade gratuit → standard. Vérifier workflow sans finaliser paiement réel.

#### O. Admin (si rôle admin) — [AdminPage.tsx](yukpopro_web/src/pages/AdminPage.tsx)
**Parcours** : lister utilisateurs, voir stats globales, ne rien supprimer.
**Qualité** : tableau paginé, filtres, pas d'actions destructives sans confirmation.

### Fixtures à créer dans `tests/qa_agent/fixtures/`

L'agent doit **générer lui-même** les fixtures texte/Excel/PDF via python (reportlab, openpyxl, python-docx, pydub pour audio synthétique) pour garantir reproductibilité. Pour l'audio : prérégistrer des voix TTS (Google TTS ou Edge TTS gratuit) puis concaténer → m4a via ffmpeg.

| Nom | Usage | Format | Contenu attendu |
|---|---|---|---|
| `cv_exemple.pdf` | Upload CV profil | PDF 2 pages | CV actuaire Cameroun réaliste |
| `reunion_60s_fr.m4a` + `.txt` | Audio réunion + transcript de référence | m4a + txt | Scénario comité souscription 60s, 2 voix |
| `audio_terrain_enquete.m4a` + `.txt` | Entretien qualitatif | m4a + txt | Entretien client assurance auto 90s |
| `protocole_enquete.pdf` | Upload protocole enquêtes | PDF 4 pages | Protocole satisfaction clients, guide entretien |
| `contrat_fr.docx` | Traduction DOCX | DOCX FR 5 pages | Contrat assurance avec titres, 2 tableaux, listes |
| `document_fr.pdf` | Traduction PDF | PDF 3 pages | Document technique FR |
| `flyer_modele.png` | Modèle infographie | PNG 1024×1024 | Design flyer référence |
| `contrat_assurance_exemple.pdf` | Analyse doc jointe chat | PDF 6 pages | Contrat avec clauses à risque identifiables |
| `donnees_sinistres.xlsx` | Analyse Excel simple chat | XLSX 30 lignes | date/type/montant/pays/statut |
| `sinistres_2024.xlsx` | Multi-fichier Studio F.2 | XLSX 50 lignes | Données sinistres croisables |
| `rapport_concurrent.pdf` | Multi-fichier Studio F.2 | PDF 5 pages | Rapport marché concurrent |
| `notes_equipe.docx` | Multi-fichier Studio F.2 | DOCX 2 pages | Notes internes équipe |
| `portefeuille_clients.xlsx` | Analyse Excel Studio F.3 | XLSX 200 lignes | client/âge/pays/prime/sinistres/LTV/canal |

**Script de génération des fixtures** : `tests/qa_agent/fixtures/generate_fixtures.py` à créer ; il doit être idempotent et déterministe (seed fixe) pour que les comparaisons de chiffres restent valides entre runs.

### Mobile — Audit de parité

Pas de test E2E automatisé mobile dans cette itération. Produire un **tableau d'audit** pour chaque feature web ci-dessus :

| Feature | Écran mobile existe ? | Méthodes API mobile OK ? | Gaps identifiés |
|---|---|---|---|
| Copilote | `CopiloteScreen.tsx` ? | `copiloteApi.chat` ? | ... |
| ... | ... | ... | ... |

**Note** : `EnquetesScreen.tsx` référence des méthodes `analyserQuantitatif`, `analyserIntelligent`, `analyserCommentaires`, `genererFormulaireIa` — elles viennent d'être ajoutées dans `yukpopro_mobile/src/api/client.ts` (commit récent) mais l'UI mobile ne les consomme peut-être pas encore correctement. À valider.

### Structure de l'agent

Créer : `tests/qa_agent/` avec :
- `run_qa.py` (ou `run_qa.ts`) — entrypoint
- `suites/` — un fichier par feature (`test_copilote.py`, `test_studio_infographie.py`, `test_enquetes.py`, etc.)
- `quality/` — module qui appelle Claude API pour noter un artefact : signature `evaluer_artefact(chemin: str, feature: str, attendus: dict) -> {note: int, verdict: str, defauts: [str], recommandations: [str]}`
- `fixtures/` — fichiers de test réalistes (1 PDF protocole enquête, 1 DOCX à traduire, 1 audio 30s, 1 image modèle flyer, 1 CV exemple)
- `report.py` — génère `rapport_qa_YYYY-MM-DD.md` + `rapport_qa_YYYY-MM-DD.html` (avec screenshots embarqués)
- `config.yaml` — URL prod, credentials, seuils de qualité (ex: min 7/10 pour PASS)

### Critères de qualité attendus par l'utilisateur (Yukpo — niveau pro)

L'utilisateur (basé au Cameroun, secteur assurance CIMA) attend un **niveau SaaS pro international** :
- Rapports : min 5 pages bien structurées, sections claires, sources citées, français impeccable
- Infographies : print-ready (300 DPI), typographie propre, branding cohérent
- Copilote : réponses contextualisées pays (Cameroun, Côte d'Ivoire, etc.), références à la réglementation CIMA/OHADA
- Enquêtes : XLSForm conforme standard ODK, questions pertinentes au contexte fourni
- Transcriptions : minimum 90% précision, français courant
- UI : pas de textes anglais résiduels, pas de boutons "disabled" sans raison, feedback utilisateur (toasts, loading states)

Tout écart → **FAIL** + recommandation explicite.

### Livrables de Mission 2

1. Code de l'agent dans `tests/qa_agent/` fonctionnel (runnable via `python tests/qa_agent/run_qa.py` ou `npx playwright test`)
2. Un premier run complet contre la prod, avec rapport généré
3. Commit `feat(qa): agent de test QA humain complet YukpoPro web + audit mobile`
4. Liste priorisée des bugs/défauts détectés (top 10), présentée à l'utilisateur à la fin

---

## Méthode de travail

1. **Démarrer par Mission 1** (plus rapide, débloque Mission 2). Ne pas commencer Mission 2 avant d'avoir le OK utilisateur sur Mission 1 et un deploy backend/web vert.
2. **Planifier avec TodoWrite** les 2 missions en sous-tâches détaillées.
3. **Commits atomiques**, jamais de `git add -A`.
4. **Toujours surveiller les deploys** après push :
   ```bash
   gh run list --branch yukpopro-main --limit 3
   ~/.fly/bin/flyctl.exe logs -a yukpopro-backend --no-tail | tail -60   # si FAIL
   ```
5. **Mémoire** : consulter `C:\Users\23767\.claude\projects\c--Users-23767-digitalisation-assurance\memory\MEMORY.md` au démarrage. Écrire des mémoires si tu découvres des contraintes durables (pas de remarques ponctuelles).
6. **Shell** : bash style Unix (pas de `NUL`, slashes forward).
7. **Langue** : réponses utilisateur en français, concis, dense.

---

## Ce qu'il NE FAUT PAS faire

- Ne pas réécrire le module infographie backend — il existe et fonctionne, on branche seulement.
- Ne pas mock les tests QA — tout passe par vraie prod, vrais endpoints, vrais LLM.
- Ne pas valider une feature sur la seule base d'une réponse HTTP 200.
- Ne pas skip le mobile — audit de parité obligatoire même sans E2E.
- Ne pas créer de documents de planning `.md` intermédiaires sauf si demandé — TodoWrite suffit.

---

**Commencer maintenant par la Mission 1, étape par étape, avec TodoWrite.**
