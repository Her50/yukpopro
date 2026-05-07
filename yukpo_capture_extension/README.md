# Yukpo Capture — Extension Chrome

Capture l'audio des réunions **Microsoft Teams**, **Google Meet**, **Zoom**,
**Webex** directement dans le navigateur, et l'envoie à Yukpo Pro pour
transcription + génération automatique du PV.

## Pourquoi cette extension ?

L'utilisateur participe à une réunion en ligne en tant que **participant
normal**. Pas besoin d'être l'organisateur, pas besoin que l'admin entreprise
autorise un bot, pas besoin d'enregistrement cloud activé. La capture se fait
**localement dans le navigateur**.

## Installation (mode développeur)

1. Télécharge ce dossier `yukpo_capture_extension/`.
2. Ouvre Chrome → `chrome://extensions`.
3. Active **Mode développeur** (en haut à droite).
4. Clique **Charger l'extension non empaquetée** → sélectionne le dossier.
5. L'icône Yukpo Capture apparaît dans la barre d'extensions.

## Première utilisation

1. Connecte-toi à **Yukpo Pro** dans ton navigateur.
2. Va dans **Paramètres → Connecter mon extension**.
3. Copie le token affiché.
4. Clique l'icône Yukpo Capture → ouvre **Configuration** → colle le token →
   **Enregistrer**.

## Pendant une réunion

1. Ouvre l'onglet de la réunion (Teams / Meet / Zoom / Webex).
2. Clique l'icône **Yukpo Capture** → un badge confirme la détection.
3. Clique **Démarrer la capture**.
   - L'audio de la réunion est capturé via `chrome.tabCapture`.
   - Ton micro est aussi capturé (option cochée) pour t'entendre toi-même.
   - Une icône **REC** rouge apparaît sur l'extension.
4. À la fin de la réunion, clique **Arrêter et envoyer à Yukpo**.
5. Le replay est uploadé vers `/api/v1/pro/reunions/importer-replay`.
6. Une notification Chrome confirme la transcription.
7. Va sur Yukpo Pro → **Réunions** → tu peux générer le PV.

## Permissions demandées

| Permission | Usage |
|------------|-------|
| `tabCapture` | Capter l'audio de l'onglet de la réunion |
| `activeTab` | Identifier l'onglet actif (détection plateforme) |
| `offscreen` | Tenir le `MediaRecorder` (impossible en service worker MV3) |
| `storage` | Mémoriser ton token Yukpo et tes préférences |
| `notifications` | Te notifier la fin de la transcription |

Aucune donnée ne quitte l'extension à part l'audio envoyé à ton instance
Yukpo Pro (que tu configures dans le popup).

## Limitations connues

- L'audio capturé inclut toute l'audio de l'onglet (réunion + sons système
  joués dans cet onglet). Coupe les notifications sonores avant.
- Si tu changes d'onglet pendant l'enregistrement, l'audio de l'onglet de
  réunion reste capturé (c'est volontaire).
- Sur **Zoom Desktop App**, la capture ne marche pas — il faut utiliser
  Zoom Web (zoom.us) dans le navigateur.

## Roadmap

- [ ] Streaming chunked upload (utile pour les réunions > 1h)
- [ ] Auto-arrêt à la fin de la réunion (détection page close)
- [ ] Upload directement à `/reunions/{id}` pour rattacher à une réunion existante
- [ ] Édition Manifest V3 → publication Chrome Web Store
