# YukpoTranslate Live — Extension Chrome

Sous-titres traduits en temps réel pour Zoom, Google Meet, Microsoft Teams, YouTube, et toute page web avec audio.

## Installation (dev / sideload)

1. Ouvrez `chrome://extensions`
2. Activez **Mode développeur** (coin haut droit)
3. Cliquez **Charger l'extension non empaquetée**
4. Sélectionnez le dossier `yukpopro_web/extension/`
5. Épinglez l'icône dans la barre d'outils

## Utilisation

1. Connectez-vous sur https://app.yukpoassurance.com
2. Ouvrez l'onglet cible (Zoom, Meet, YouTube…)
3. Cliquez l'icône **YukpoTranslate Live** dans la barre
4. Collez votre token JWT (disponible dans les DevTools → Application → Local Storage → `token`)
5. Choisissez la langue cible
6. Cliquez **Démarrer la traduction**
7. Les sous-titres s'affichent en overlay en bas de page

## Architecture

- `manifest.json` — MV3 permissions (tabCapture, offscreen, scripting)
- `background.js` — Service worker : orchestration session
- `offscreen.html/js` — Capture audio + WebSocket (les SW MV3 n'ont pas d'AudioContext)
- `content.js` — Overlay DOM injecté dans la page active
- `popup.html/js` — UI Start/Stop + config
- `pcm-worklet.js` — Downsampling PCM16 16 kHz mono

## Obtenir le token

Dans YukpoPro :
1. F12 → onglet **Application** → **Local Storage** → `https://app.yukpoassurance.com`
2. Copiez la valeur de la clé `token`

## Icônes

Placez 3 icônes PNG dans `icons/` : `icon-16.png`, `icon-48.png`, `icon-128.png`.
