# Synthèse de session — Persistance des modules longs YukpoPro

**Date** : 23 avril 2026
**Branche** : `yukpopro-main`
**Repo** : `yukpopro.git` (monorepo) + `yukpopro-mobile.git` (séparé)

---

## 1. Objectif

Garantir que toutes les opérations longues (enregistrement de réunion, traduction live, génération Yukpo Studio, traduction de fichier, formulaire "Nouvelle réunion") **continuent en arrière-plan** quand l'utilisateur quitte la page, et que l'état soit intact à son retour.

Ajout : mode **rapporteur-traducteur** dans le module Réunion (traduction live sur le même micro que l'enregistrement).

---

## 2. Architecture retenue

**Principe** : un store Zustand au niveau module par opération asynchrone longue. La page React ne fait que brancher `useStore(s => s.x)` — aucun cleanup au démontage. L'opération vit dans le store, pas dans le composant.

### Stores web (`yukpopro_web/src/store/`)

| Store | Clés persistées | Rôle |
|---|---|---|
| `recorderStore.ts` | `isRecording, isPaused, duration, audioBlob, liveSpeech` + helper `getRecorderStream()` | Enregistrement MediaRecorder avec partage du MediaStream |
| `translateLiveStore.ts` | `status, lignes, currentInterim, minutesUsed, creditsUsed, lastGender, active` | Session WebSocket. Accepte `externalStream` pour réutiliser un micro déjà ouvert |
| `generateurStore.ts` | `tab, loading{key}, resultats{key}` + `run<T>(key, fn, opts)` | Yukpo Studio (5 jobs : rapport, slides, fichiers, conversion, infographie) |
| `traductionStore.ts` | `mode, loading{texte,fichier}, resultats{texte,fichier}` + `run(mode, fn)` | Traduction texte + fichier (OCR peut durer plusieurs minutes) |
| `reunionFormStore.ts` | `isOpen, titre, date, notes, participants, langue, langueCible, traduireLive, transcriptionDone` | Formulaire "Nouvelle réunion" (survit à fermeture de modale + navigation) |

### Stores mobile (`yukpopro_mobile/src/store/`)

- `recorderStore.ts` — expo-av `Audio.Recording` + timer au niveau module
- `generateurStore.ts` — même pattern que web, notifications via `Alert` React Native

### Services modifiés

- `services/translate_live.ts` : option `externalStream?: MediaStream` + flag interne `ownsStream` → `stop()` ne coupe pas les tracks partagées avec le recorder.

---

## 3. Pages refactorées

| Page | Avant | Après |
|---|---|---|
| `GenerateursPage.tsx` | `useState` local pour chaque job + `tab` local → page "vide" au retour | Tout dans `generateurStore` (incluant l'onglet actif) |
| `TraductionPage.tsx` | `loading` / `resultat` local → traduction fichier perdue | `traductionStore` — deux modes isolés |
| `ReunionsPage.tsx` / `FormulaireReunion` | Champs du formulaire perdus à la fermeture, enregistrement seul survivait | `reunionFormStore` + `recorderStore` — tout persiste |
| `TranslateLivePage.tsx` | Utilise déjà le store | Vérifié — session WebSocket continue en arrière-plan |
| Mobile `GenerateursScreen.tsx`, `ReunionsScreen.tsx` | `useState` local | Stores mobiles |

---

## 4. Fonctionnalité nouvelle : rapporteur-traducteur

Dans `FormulaireReunion`, nouvelle checkbox **"Traduire en direct pendant la réunion"** (fond violet translucide) + select langue cible.

Flux :
1. `recorder.start()` ouvre le micro et conserve le MediaStream dans `recorderStore`.
2. Si checkbox cochée → 50 ms plus tard, on récupère le stream via `getRecorderStream()` et on démarre `translateLive.start({ externalStream })`.
3. Une session unique → deux consommateurs (enregistrement + WebSocket STT/TRAD).
4. À l'arrêt : `stopTranslate()` puis `recorder.stop()`. Le flag `ownsStream=false` empêche le translate-live de couper les tracks partagées.

Panneau live dans la modale : dernières 6 lignes `source → traduction`.

---

## 5. UI corrections (fin de session)

- **Fond de la checkbox "Traduire en direct"** : `bg-slate-900/40` → `bg-purple-500/10` + `border-purple-500/30` pour mieux marquer le mode rapporteur-traducteur.
- **Historique sessions ChatPage** :
  - Session active : `bg-slate-700 text-white` → `bg-yukpo-500/20 border border-yukpo-400/40 text-white font-medium` (contraste + identité visuelle yukpo)
  - Session inactive : texte `text-slate-400` → `text-slate-200` (lisibilité accrue)

---

## 6. Commits poussés (branche `yukpopro-main`)

| SHA | Message |
|---|---|
| `548c01a5` | fix(web): persister l'onglet actif Yukpo Studio pour survivre à la navigation |
| `e981548f` | fix(web): persistance Traduction + formulaire Réunion pendant navigation |
| *(à venir)* | ui(web): fond checkbox rapporteur-traducteur + contraste historique sessions chat |

Vercel redéploie automatiquement à chaque push.

---

## 7. Rapporteur-traducteur mobile — IMPLÉMENTÉ (option 2)

**Décision** : `react-native-audio-record` (PCM 16 kHz mono natif). Raison : seule option permettant un vrai streaming PCM temps réel avec un micro unique partagé. `expo-audio` n'expose pas de flux PCM brut ; double recording concurrent bloqué par l'exclusivité session audio iOS.

**Fichiers créés** :
- `yukpopro_mobile/src/services/pcm_recorder.ts` — singleton avec refcount + subscribe, partage les chunks entre recorder (WAV) et translate_live (WS).
- `yukpopro_mobile/src/services/translate_live.ts` — client WebSocket port mobile (transcript/translation/usage events).
- `yukpopro_mobile/src/store/translateLiveStore.ts` — store Zustand module-level (session survit à la navigation).

**Fichiers modifiés** :
- `yukpopro_mobile/src/store/recorderStore.ts` — option `pcmMode` : bascule sur pcm_recorder quand le mode rapporteur-traducteur est actif ; conserve expo-av par défaut (compat Expo Go).
- `yukpopro_mobile/src/screens/ReunionsScreen.tsx` — checkbox violette + sélecteur langue cible + panneau live 6 dernières lignes.
- `yukpopro_mobile/src/api/client.ts` — expose `getApiBaseUrl()` et `getAuthToken()`.
- `yukpopro_mobile/package.json` — ajout `react-native-audio-record` et `buffer`.

**Contrainte** : module natif → **Expo Go ne suffit plus**. Build requis :
```bash
cd yukpopro_mobile
npm install
npx expo prebuild
eas build --profile development --platform android   # ou ios
```
Comportement dégradé si Expo Go : `pcmRecorderAvailable` est `false`, la checkbox affiche "⚠ Dev client requis" et l'enregistrement normal (expo-av) reste fonctionnel.

## 8. Reste à faire

- **TranslateLivePage** : `source` / `sourceMode` / `consentOk` restent en useState local. Pas de bug persistance (session continue), mais le panneau de config se "reset" visuellement à la navigation pendant une session active. UX mineure.

- **Optimisation bundle** : warning Vite (chunk principal 744 kB). Split recommandé si performance chargement devient un enjeu.

- **TTS audio mobile** : le client mobile ignore les frames binaires ElevenLabs. À ajouter si la voix de synthèse est demandée (nécessite décodeur MP3 en RN — `expo-av` Playback).

---

## 8. Comment tester en prod

1. **Yukpo Studio** : onglet Slides → lancer une génération → changer d'onglet Dashboard → revenir. Résultat + onglet "Slides" conservés.
2. **Traduction fichier** : uploader un PDF > 2 min OCR+trad → quitter la page → revenir. Loading ou résultat intact.
3. **Réunion** : ouvrir "Nouvelle réunion" → saisir titre/participants → cocher "Traduire en direct" → démarrer enregistrement → fermer la modale → naviguer vers Dashboard → revenir sur Réunions → rouvrir le formulaire. Tous les champs + enregistrement actif + traduction live intacts.
4. **Translate Live** : lancer session → quitter la page → revenir. Lignes et compteur crédits à jour.
5. **Chat** : historique des sessions → session sélectionnée visible avec contour yukpo, autres clairement lisibles.

---

## 9. Fichiers clés pour reprise

```
yukpopro_web/src/
  store/
    recorderStore.ts          — micro + stream partageable
    translateLiveStore.ts     — session WebSocket
    generateurStore.ts        — 5 jobs Yukpo Studio + tab
    traductionStore.ts        — texte + fichier
    reunionFormStore.ts       — formulaire complet
  services/
    translate_live.ts         — externalStream + ownsStream
  pages/
    GenerateursPage.tsx
    TraductionPage.tsx
    ReunionsPage.tsx          — FormulaireReunion consomme reunionFormStore
    TranslateLivePage.tsx
    ChatPage.tsx              — historique visible

yukpopro_mobile/src/
  store/
    recorderStore.ts
    generateurStore.ts
  screens/
    GenerateursScreen.tsx
    ReunionsScreen.tsx
```

Mémoire Claude mise à jour : `project_persistance_modules.md` indexée dans `MEMORY.md`.
