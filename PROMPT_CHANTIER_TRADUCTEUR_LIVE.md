# Prompt — Chantier Traducteur Live Temps Réel (YukpoTranslate)

> Prompt **autonome** pour une nouvelle session Claude Code — concevoir et prototyper une app de traduction vocale temps réel, fonctionnant en **web** (sans installation pour les interlocuteurs) et **mobile**. À exécuter **après** validation des deux missions du prompt [PROMPT_AGENT_TEST_YUKPOPRO.md](PROMPT_AGENT_TEST_YUKPOPRO.md), indépendamment du prompt QA.

---

## Contexte & objectif produit

**YukpoTranslate** : traducteur vocal simultané persistant. L'utilisateur porte l'app (web ou mobile) ; ses interlocuteurs n'ont rien à installer. Dès qu'un interlocuteur parle une autre langue que celle choisie, l'app traduit automatiquement, de façon fluide, dans l'oreille de l'utilisateur (voix ou sous-titres).

### Cas d'usage prioritaires

1. **Réunion physique** — utilisateur en salle avec participants multilingues ; app sur laptop/téléphone, mic capte l'ambiance, restitue dans ses écouteurs.
2. **Réunion en ligne web** (Zoom/Teams/Google Meet/Webex) — utilisateur ouvre la réunion dans son navigateur ; l'app web capture l'audio de l'onglet et traduit en direct. **Aucune installation côté participants distants**.
3. **YouTube / vidéos en ligne** — capture audio d'un onglet vidéo et traduit live.
4. **Vidéo/audio local sur téléphone ou ordinateur** — capture audio système et traduit.

Marché pertinent : Afrique francophone, CIMA/OHADA (FR↔EN↔PT↔AR + langues locales Wolof, Yoruba, Swahili, Hausa, Lingala, Douala).

---

## Faisabilité technique — réponse directe

### ✅ Web pur (sans installation pour les autres)

**Oui, possible** via PWA (Progressive Web App) hébergée en HTTPS. APIs navigateur :
- `navigator.mediaDevices.getUserMedia({audio:true})` — mic pour salle physique
- `navigator.mediaDevices.getDisplayMedia({audio:true, video:false})` — capture audio d'un onglet (Zoom/Meet web, YouTube) ou de tout le système. Chrome/Edge OK, Firefox limité.
- `AudioContext` + `AudioWorklet` — traitement audio bas niveau
- `MediaStreamTrack` pipeline → WebSocket vers backend → traduction → retour audio/texte → `AudioContext` playback

**Limite** : pour capturer l'audio d'une **app native** (Zoom client, Teams desktop), il faut un virtual audio device (BlackHole macOS, VB-Cable Windows, PulseAudio Linux) **installé côté utilisateur** — PAS côté interlocuteurs. Si la réunion est dans l'onglet navigateur, `getDisplayMedia` suffit, zéro install.

### ✅ Mobile (iOS + Android)

Via React Native (`expo-av`, `react-native-audio-recorder-player`, `@react-native-voice/voice` ou natif). Sur iOS 17+, capture audio système possible via ReplayKit (avec permission). Sur Android, AudioPlaybackCapture API (app target ≥ Q, certaines restrictions DRM).

### ✅ Asymétrique par design

Seul l'utilisateur installe ou ouvre l'app. Interlocuteurs : rien. Confirmé par les produits existants (Otter.ai, Krisp, Meeple, Interprefy, Timekettle).

---

## Référence d'inspiration — projet yukpomnang2

Un **WebSocket déjà développé et fonctionnel** existe dans le projet sœur `C:\Users\23767\yukpomnang2\` (stack Rust/Axum côté backend). La nouvelle session **doit s'en inspirer directement** (ne pas réinventer la plomberie WS).

**Fichiers à étudier en priorité** :
- `backend/src/routes/chat_reactions_routes.rs` — WS chat (reactions temps réel)
- `backend/src/routes/delivery_chat_routes.rs` — WS chat livraison
- `backend/src/services/conferences_lives_service.rs` — **probable pipeline audio/vidéo live le plus proche du besoin traducteur**
- `backend/src/config/live_streaming.rs` — config streaming
- `backend/src/config/timeouts.rs` — timeouts WS (keepalive, reconnexion)

**Patterns à réutiliser** :
- `WebSocketUpgrade` d'Axum (backend) ↔ client WS React — handshake avec token JWT
- Enveloppe JSON des messages (schéma commun)
- Heartbeat/keepalive + gestion reconnexion côté client
- Architecture service (séparation route → service → handler stream)

**Note stack** : YukpoPro backend est FastAPI (Python), pas Rust. Donc transcrire le pattern Rust/Axum → FastAPI `WebSocket` (equivalent `fastapi.WebSocket` + `accept()` + `receive_bytes()/receive_json()`). Le **design** se copie, **l'implémentation** se réécrit en Python. Lire, comprendre, adapter — pas de copier-coller.

**Commande de repérage complémentaire** si besoin :
```bash
cd /c/Users/23767/yukpomnang2
grep -rln -iE "WebSocketUpgrade|axum::extract::ws|on_upgrade" backend/src --include="*.rs"
```

## Architecture recommandée

```
┌────────────────────────────────────────────────────────────────┐
│ Client (PWA web OU mobile)                                      │
│   Capture audio (getUserMedia / getDisplayMedia / AVAudioSession)│
│   VAD (Voice Activity Detection) local → chunks 200-500ms       │
│   WebSocket → backend                                           │
└────────────────┬───────────────────────────────────────────────┘
                 ▼
┌────────────────────────────────────────────────────────────────┐
│ Backend (FastAPI + websockets, même infra YukpoPro Fly.io)      │
│   Router audio stream                                           │
│   STT streaming (Deepgram OU Whisper.cpp local OU Seamless)     │
│   Détection langue par utterance                                │
│   Si langue ≠ langue cible utilisateur : traduction             │
│     → GPT-4o-mini / DeepL / NLLB-200                            │
│   TTS streaming (ElevenLabs / Azure Neural / Piper local)       │
│   Push → WebSocket → client                                     │
└────────────────────────────────────────────────────────────────┘
                 ▼
┌────────────────────────────────────────────────────────────────┐
│ Client : lecture audio traduit OU sous-titres overlay           │
│   Mode VOICE : AudioContext playback (casque)                   │
│   Mode CAPTIONS : overlay HTML sur la page / écran              │
│   Mode DUAL : les deux                                          │
└────────────────────────────────────────────────────────────────┘
```

**Latence budgétée** : 1.5-3 secondes end-to-end en cloud ; <1s nécessite [Meta SeamlessStreaming](https://github.com/facebookresearch/seamless_communication) sur GPU dédié.

---

## Stack — options avec coûts réels (2026)

### Option A — Cloud premium (qualité max, latence min)

| Composant | Service | Coût |
|---|---|---|
| STT streaming | **Deepgram Nova-3** | $0.0043/min ≈ $0.26/h |
| Détection langue | Inclus Deepgram | — |
| Traduction | **GPT-4o-mini** | ~$0.001/utterance (négligeable) |
| TTS voix naturelle | **ElevenLabs Turbo v2** streaming | ~$0.30/h voix parlée |
| Alternative TTS | **Azure Neural TTS** | $16/M chars ≈ $0.10/h |

**Total : ~0.60-0.80 $/heure d'utilisation active.**

### Option B — Cloud éco (bon compromis)

| Composant | Service | Coût |
|---|---|---|
| STT | **Azure Speech** streaming + traduction intégrée | ~$1/h combo |
| TTS | **Azure Neural TTS** | $0.10/h |

**Total : ~1 $/heure.** Avantage : single vendor, SLA simple.

### Option C — Hybride local+cloud (coût variable ≈ 0)

| Composant | Solution | Coût |
|---|---|---|
| STT | **Whisper.cpp** (base ou small) sur backend | $0 (CPU) |
| Détection langue | Whisper retourne la langue | $0 |
| Traduction | **NLLB-200-distilled-1.3B** local OU GPT-4o-mini | $0 local OU ~$0.001/utterance |
| TTS | **Piper TTS** local | $0 |

**Total : ~0 $/h variable, +infra GPU ~$50-200/mois pour latence acceptable.** Trade-off : qualité inférieure sur langues africaines, latence 2-4s.

### Option D — Tout-en-un open source (ambitieux)

[**Meta SeamlessStreaming**](https://github.com/facebookresearch/seamless_communication) — speech-to-speech direct, 100+ langues, **vraie** simultanée <500ms mais requiert GPU T4/A10 (~$0.50/h sur Fly.io GPU machines ou Modal.com).

**Recommandation YukpoTranslate** : démarrer **Option A** (Deepgram + GPT-4o-mini + Azure TTS) pour MVP rapide et qualité. Migrer vers C/D progressivement pour réduire coût variable quand volume monte.

---

## Coûts infra + monétisation

**Infra backend** : ~$30-50/mois (Fly.io CPU machine déjà en place mutualisée avec YukpoPro) + WebSocket scaling.

**Modèle tarifaire suggéré** :
- **Free** : 15 min/jour (≈ 7h/mois × $0.70 = $5/utilisateur cost)
- **Pro** : 3000 FCFA/mois (≈ $5) → 30h/mois ($21 cost → marge négative sans pallier haute)
- **Ajuster** : Pro 5000-7500 FCFA/mois pour marge positive

⚠️ **Attention** : à forte utilisation, les coûts STT/TTS cloud dépassent vite un abonnement SaaS bas-de-gamme. **Le plan éco Option C** avec Whisper local sur GPU partagé devient pertinent dès ~50 utilisateurs pro actifs.

---

## Comparatif produits existants (benchmark)

| Produit | Plateforme | Asymétrique | Langues AFR | Prix |
|---|---|---|---|---|
| Otter.ai | Web+app | Oui (caption seul) | Non | $10-30/mois |
| Krisp | Desktop | Oui | Non | $8/mois |
| Interprefy | Web (réunions) | Oui | Limité | Entreprise |
| Timekettle | Hardware earbuds | Oui | Partiel | 200-400$ one-shot |
| Google Translate | App mobile | Partiel conversation | Wolof/Swahili limité | Gratuit |
| Microsoft Translator | Web+app+Teams | Oui (Teams intégré) | Swahili | Gratuit base |

**Différentiateurs YukpoTranslate** : langues africaines de qualité (via NLLB-200 fine-tuné + dictionnaires métier assurance/banque), pricing FCFA adapté Afrique, mode overlay web universel (Zoom/Meet/YouTube sans bot).

---

## MVP progressif — 3 sprints

### Sprint 1 (2 semaines) — Web PWA "salle physique"

Livrable : PWA `translate.yukpo.cm` (sous-domaine du projet).
- Page unique : bouton START → `getUserMedia` mic → stream WebSocket → affichage sous-titres bilingues live (ORIG + TRAD)
- Langues de départ : FR↔EN, FR↔PT, FR↔AR
- Stack : Option A (Deepgram + GPT-4o-mini + caption seul, pas encore de TTS voix)
- Backend : nouveau router `/api/v1/translate/live/ws` dans `yukpo_assurance/api/routes_translate_live.py`
- Critères succès : latence < 3s, compréhension > 90% sur audio clair

### Sprint 2 (2 semaines) — Web "réunion en ligne"

- Ajouter capture onglet via `getDisplayMedia({audio:true})` (Zoom/Meet/YouTube dans navigateur)
- Ajouter TTS streaming (Azure Neural ou ElevenLabs) pour mode voix
- Mode overlay : extension Chrome optionnelle qui affiche les sous-titres par-dessus Zoom/Meet/YouTube (pas obligatoire, la PWA suffit avec sous-titres dans sa propre fenêtre)
- Gestion 3-4 langues simultanées dans la même réunion (détection auto par utterance)

### Sprint 3 (3 semaines) — Mobile + langues africaines

- App mobile Expo : `yukpo_translate_mobile/` ou tab dans `yukpopro_mobile/`
- Capture mic + haut-parleur/casque
- iOS : AVAudioSession ; Android : AudioPlaybackCapture
- Ajouter **NLLB-200** pour langues Wolof, Yoruba, Hausa, Swahili, Lingala
- Fine-tuning lexique assurance/banque/OHADA

---

## Intégration dans l'écosystème YukpoPro

- **Backend** : nouveau module `yukpo_assurance/modules/translate_live/` + route `/api/v1/translate/live/*`
- **Crédits** : débiter crédits à la minute (cf. modèle `CreditIAUserDB` ou nouveau `TranslationMinutesDB`)
- **Abonnement** : ajouter feature `translate_live_minutes` aux plans existants
- **Web** : nouvelle page `/translate` dans `yukpopro_web/src/pages/TranslatePage.tsx` OU app séparée `translate.yukpo.cm`
- **Mobile** : nouvel écran `TranslateScreen.tsx` dans `yukpopro_mobile`
- **Mes Documents** : sauvegarde optionnelle de la transcription complète post-réunion (MD/DOCX) — réutilise le bureau documents storage existant

---

## Ce qu'il faut livrer concrètement dans cette session

1. **Document de spec technique détaillé** : `docs/translate_live_spec.md`
   - Diagrammes de flux WebSocket (client ↔ backend)
   - Protocole message (JSON : `{type: "audio_chunk"/"translation"/"caption", payload, lang_from, lang_to, ts}`)
   - API endpoints
   - Choix final de stack (justifié)

2. **Prototype backend minimal** — Sprint 1 seulement :
   - `yukpo_assurance/api/routes_translate_live.py` avec endpoint WebSocket `/api/v1/translate/live/ws`
   - `yukpo_assurance/modules/translate_live/deepgram_client.py` — wrapper streaming STT
   - `yukpo_assurance/modules/translate_live/translator.py` — traduction GPT-4o-mini
   - Test local avec un fichier audio simulé en streaming chunks

3. **Prototype web minimal** — Sprint 1 :
   - Nouvelle page `yukpopro_web/src/pages/TranslatePage.tsx` avec : bouton START, affichage sous-titres bilingues, indicateur latence, sélecteur langue cible
   - Service `yukpopro_web/src/services/translate_live.ts` : WebSocket + MediaRecorder
   - Pas besoin de finir Sprint 2/3 dans cette session

4. **Document de chiffrage** : `docs/translate_live_business.md`
   - Coûts cloud réels (utiliser les tarifs ci-dessus)
   - Break-even par tier d'utilisateurs
   - Risques (rupture API, qualité langues africaines, DRM YouTube sur capture)

5. **Décision Go/No-Go** : après MVP Sprint 1, l'utilisateur décide Sprint 2-3.

---

## Pré-requis & secrets à provisionner

- Compte **Deepgram** (key streaming) — gratuit 200h puis paid
- Compte **ElevenLabs** OU **Azure Speech** — pour TTS
- Secrets Fly.io à ajouter : `DEEPGRAM_API_KEY`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` (ou `ELEVENLABS_API_KEY`)
- Domaine : sous-domaine `translate.yukpo.cm` OU page `/translate` dans l'app existante
- Si Option C retenue plus tard : GPU (Fly.io `a10` machine, ou Modal.com, ou RunPod)

---

## Méthode

1. Démarrer par **lecture de la spec** et présentation du choix de stack à l'utilisateur pour validation avant de coder
2. **TodoWrite** pour tracer les sous-tâches
3. **Commits atomiques** : un par composant (backend WS, client PWA, spec, business)
4. Pas de vraie intégration Zoom/Teams/YouTube au Sprint 1 — le navigateur + `getDisplayMedia` fait tout
5. Tests : fichier audio FR 60s + fichier EN 60s rejoués en streaming vers le WS → valider bout-en-bout
6. **Pas** d'achat API ni de déploiement tant que l'utilisateur n'a pas validé le chiffrage

---

## Ce qu'il NE FAUT PAS faire

- Ne pas prétendre que la latence <500ms est gratuite — elle nécessite GPU + SeamlessStreaming.
- Ne pas activer automatiquement le TTS voix au Sprint 1 — commencer par sous-titres (moins cher, valide le pipeline).
- Ne pas toucher à YukpoPro existant au Sprint 1 (module isolé).
- Ne pas promettre captures d'apps natives (Zoom client Windows) en web pur — c'est un desktop app séparé, hors scope Sprint 1-2.
- Ne pas ignorer la législation (enregistrement de conversations : lois variables par pays ; l'app doit prévenir les participants dans des contextes pro — feature notice à afficher).

---

**Démarrer par la spec + choix de stack, valider avec l'utilisateur, puis coder le MVP Sprint 1.**
