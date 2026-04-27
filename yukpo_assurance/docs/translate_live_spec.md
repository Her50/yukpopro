# YukpoTranslate Live — Spécification technique (Sprint 1)

Version : 1.0  
Statut : MVP opérationnel — sous-titres bilingues temps réel  
Auteur : Équipe YukpoPro

---

## 1. Portée Sprint 1

Livrable : PWA `/translate` intégrée dans `yukpopro_web` + route WebSocket backend.

**Inclus** :
- Capture micro navigateur (`getUserMedia`) — cas d'usage « salle physique »
- Capture onglet/écran (`getDisplayMedia`) — cas d'usage Zoom/Meet/YouTube dans navigateur
- Streaming audio chunks 16 kHz mono → backend via WebSocket
- STT streaming (Deepgram Nova-3) avec détection automatique de langue
- Traduction GPT-4o-mini vers langue cible choisie
- Affichage sous-titres bilingues live (texte original + traduit)
- Débit crédits à la minute (via `service_credits.debiter_forfait_fcfa`)
- Auth JWT via query-param `?token=...` (convention existante de `routes_collaboration`)

**Non inclus (Sprint 2-3)** :
- TTS voix simultanée (Azure Neural / ElevenLabs)
- App mobile Expo
- Langues africaines (NLLB-200)
- Capture d'apps natives (Zoom desktop, Teams desktop)

---

## 2. Architecture

```
┌────────────────────────────────┐       ┌──────────────────────────────┐
│ PWA  yukpopro_web/translate    │       │ Backend FastAPI              │
│                                │       │                              │
│ getUserMedia / getDisplayMedia │──WS──▶│ /api/v1/translate/live/ws    │
│ AudioContext + AudioWorklet    │ JSON+ │                              │
│ PCM16 16kHz mono               │ bytes │ DeepgramStreamingClient      │
│                                │       │   ↓ (transcript + language)  │
│                                │◀─WS───│ Translator (GPT-4o-mini)     │
│ Sous-titres bilingues          │ JSON  │   ↓                          │
│                                │       │ push caption frames          │
│                                │       │ credit debit per minute      │
└────────────────────────────────┘       └──────────────────────────────┘
```

**Latence cible** : 1.5-3 s end-to-end (STT interim ≤ 500 ms, traduction ≤ 800 ms par utterance finale).

---

## 3. Protocole WebSocket

URL : `ws://host/api/v1/translate/live/ws?token=<jwt>&target=<lang>&source=<auto|fr|en|...>`

### 3.1 Handshake

Le serveur :
1. Valide le JWT via `_decoder_token` (auth.py).
2. Vérifie le solde de crédits via `verifier_solde_suffisant` → refuse avec `close(code=4002)` si épuisé.
3. Accepte la connexion et envoie un message `ready` :

```json
{ "type": "ready", "session_id": "…uuid…", "source": "auto", "target": "fr", "ts": 1714000000.0 }
```

### 3.2 Messages client → serveur

| Type | Payload | Notes |
|---|---|---|
| `audio` (binary frame) | PCM16 LE mono 16 kHz | ~100-300 ms par chunk |
| `config` (text/JSON) | `{ "type":"config", "target":"en", "source":"auto" }` | Change la langue cible en live |
| `ping` (text) | `"ping"` | Heartbeat 30s |
| `stop` (text/JSON) | `{ "type":"stop" }` | Fin de session propre |

### 3.3 Messages serveur → client

```json
{ "type": "transcript", "text": "…", "lang": "fr", "is_final": false, "utterance_id": "u42", "ts": 1714000001.1 }
{ "type": "translation", "source_text": "…", "translated_text": "…", "source_lang": "fr", "target_lang": "en", "utterance_id": "u42", "ts": 1714000002.0 }
{ "type": "usage", "minutes": 1.0, "credits_debited": 20, "credits_remaining": 4980 }
{ "type": "error", "code": "stt_unavailable", "message": "…" }
{ "type": "pong" }
```

### 3.4 Codes de clôture

| Code | Cause |
|---|---|
| 1000 | Fin normale (client `stop` ou navigateur ferme) |
| 4001 | Token JWT invalide / manquant |
| 4002 | Crédits épuisés (`CREDITS_EPUISES`) |
| 4003 | Rate-limit connexion (ex : > 2 sessions simultanées) |
| 4100 | Erreur provider STT (Deepgram down) |

---

## 4. Pipeline backend

Module : `yukpo_assurance/modules/translate_live/`

### 4.1 Composants

| Fichier | Rôle |
|---|---|
| `__init__.py` | Exports publics |
| `session.py` | Orchestrateur : ouvre Deepgram, router messages, push translations, débit crédits |
| `deepgram_client.py` | Wrapper streaming Deepgram (si clé absente → fallback simulation) |
| `translator.py` | Traduction par `ia_client` (GPT-4o-mini, pas de RAG, 1 appel par utterance finale) |
| `languages.py` | Table ISO 639-1 supportées, normalisation |

### 4.2 Gestion crédits

Tarif effectif STT+traduction (Option A) : ~0.60 $/h ≈ 360 FCFA/h = 6 FCFA/min.  
Marge Yukpo ×20 → **120 crédits/minute active**.

Facturation :
- Timer côté `session.py` : tick toutes les 10 s → accumule `minutes_streamed`.
- Toutes les 60 s (ou à la déconnexion), appel à `debiter_forfait_fcfa(user_id, cout_fcfa=6.0, module="translate_live")`.
- Si `verifier_solde_suffisant` retourne False → message `error` + `close(4002)`.

### 4.3 STT — Deepgram Nova-3

- URL : `wss://api.deepgram.com/v1/listen?model=nova-3&language=multi&smart_format=true&interim_results=true&encoding=linear16&sample_rate=16000&channels=1`
- Mode `multi` = détection automatique de langue (Nova-3). Si `source` imposée (≠ `auto`), on passe `language=<code>`.
- Header `Authorization: Token <DEEPGRAM_API_KEY>`.
- Réception : JSON contenant `channel.alternatives[0].transcript`, `is_final`, `channel.detected_language`.

**Fallback** : si `DEEPGRAM_API_KEY` absente, le module bascule sur un stub qui renvoie `[STT indisponible — configurez DEEPGRAM_API_KEY]`. Le WS reste utilisable pour dev local (test UI), pas pour production.

### 4.4 Traduction — GPT-4o-mini

Appel `ia_client.generer()` avec prompt minimal :
```
Traduis en {target_lang} (code ISO 639-1) le texte suivant, sans commentaire, en gardant le ton et les noms propres. Texte :
<source_text>
```
Si `source_lang == target_lang` → bypass (aucun appel IA, économie de crédits). Les transcripts `is_final=false` ne sont **pas** traduits (sinon spam API + coût).

---

## 5. Endpoint HTTP auxiliaire

`GET /api/v1/translate/live/langues`  
→ Retourne la liste des langues supportées (ISO code + label). Utilisé par la PWA pour peupler le sélecteur.

`GET /api/v1/translate/live/status`  
→ `{ stt_available, translator_available, price_per_minute_fcfa, price_per_minute_credits }`. Affiché dans l'UI.

---

## 6. Sécurité / conformité

- **Notice d'enregistrement** : l'UI doit afficher un bandeau *« Les participants sont invités à être informés que la conversation peut être transcrite pour traduction »* avant le démarrage, avec bouton « J'ai prévenu mes interlocuteurs ». Obligation légale variable selon les pays — voir doc `translate_live_business.md`.
- **Pas de stockage audio** par défaut. Les chunks PCM traversent le serveur sans être persistés. Le transcript complet est gardé en mémoire côté client uniquement (téléchargeable en `.md`).
- **Rate-limit WS** : 2 sessions simultanées par `user_id`, appliqué dans `session.py` via un dict en mémoire.
- **CSP** : `connect-src 'self' ws: wss:;` déjà présent dans `main.py`.

---

## 7. Choix de stack — justification

| Composant | Choix | Alternative | Raison du choix |
|---|---|---|---|
| STT | Deepgram Nova-3 | Whisper.cpp, Azure, SeamlessStreaming | Nova-3 = détection langue native + multilingue + streaming WS natif + faible latence + pay-as-you-go, pas de GPU |
| Traduction | GPT-4o-mini (via `ia_client` existant) | DeepL, NLLB-200 | Déjà intégré et tracé dans `ia_client`, coût négligeable (~$0.001/utterance), prompt simple, bonne qualité FR/EN/PT/AR |
| TTS | *reporté Sprint 2* | — | Non critique pour MVP, réduit coûts et complexité |
| Transport | WebSocket brut FastAPI | socket.io, WebRTC | Déjà utilisé dans `routes_collaboration`, cohérence maison, simple |
| Capture client | `getUserMedia` + `getDisplayMedia` + `AudioWorklet` | Recorder.js, MediaRecorder WebM | PCM16 brut requis par Deepgram streaming, qualité et latence optimales |

Référence yukpomnang2 : enveloppe JSON `{type, data/payload, ts}`, heartbeat `ping`/`pong`, JWT via query param, reconnexion côté client avec backoff exponentiel. Pattern appliqué ici.

---

## 8. Critères d'acceptation Sprint 1

- [ ] Route WS `/api/v1/translate/live/ws` acceptant un JWT valide
- [ ] Backend démarre sans la clé Deepgram (mode dégradé) et avec (mode plein)
- [ ] Page `/translate` affiche sélecteur langue cible + bouton START
- [ ] Microphone : 30 s d'audio FR → sous-titres FR (orig) + EN (trad) latence < 3s
- [ ] Onglet Zoom/Meet : capture onglet → sous-titres pendant réunion
- [ ] Crédits : 60 s streaming → ~120 crédits débités visibles dans `/abonnement`
- [ ] Clôture propre : navigateur fermé → `close(1000)` → pas de leak side serveur
- [ ] Fallback crédits épuisés → close 4002 + toast utilisateur

---

## 9. Roadmap Sprint 2-3

Sprint 2 :
- TTS streaming Azure Neural (2-3 voix par langue)
- Extension Chrome optionnelle pour overlay sous-titres sur Zoom/Meet/YouTube
- Export transcript final en `.md` et `.docx` dans **Mes Documents**

Sprint 3 :
- App mobile Expo (`yukpopro_mobile`) : onglet « Traduction Live »
- Langues africaines via NLLB-200 (Wolof, Yoruba, Hausa, Swahili, Lingala, Douala)
- Fine-tuning lexique assurance/OHADA
