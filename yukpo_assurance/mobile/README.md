# YukpoAssurance Mobile

Application React Native (Expo) pour les compagnies d'assurance zone CIMA.

## Écrans disponibles

| Écran | Route | Description |
|-------|-------|-------------|
| Dashboard | `/(tabs)/dashboard` | KPIs, alertes CIMA, accès rapides |
| Sinistres | `/(tabs)/sinistres` | Liste, détail, score fraude |
| Scanner OCR | `/(tabs)/scanner` | Camera → Claude Vision → champs ORASS |
| Copilote IA | `/(tabs)/chat` | Chat CIMA — questions, calculs, rédaction |
| Courtiers | `/(tabs)/courtiers` | Productions, commissions, objectifs |
| Souscription | `/souscription` | Wizard 4 étapes — branche → client → prime → validation |
| Login | `/login` | Authentification JWT sécurisée |

## Installation

```bash
cd mobile
npm install
npx expo start
```

## Configuration

Créer un fichier `.env` à la racine :

```bash
EXPO_PUBLIC_API_URL=https://api.yukpo-assurance.cm
# ou en local :
EXPO_PUBLIC_API_URL=http://192.168.1.100:8000
```

## Build production

```bash
# Android APK
npx eas build --platform android --profile production

# iOS IPA
npx eas build --platform ios --profile production
```

## Architecture

```
mobile/
├── app/                    # Expo Router — routes = fichiers
│   ├── _layout.tsx         # Layout racine (AuthProvider, PaperProvider)
│   ├── index.tsx           # Redirect auth/login
│   ├── login.tsx           # Page de connexion
│   ├── souscription.tsx    # Wizard souscription
│   └── (tabs)/
│       ├── _layout.tsx     # Bottom tab navigator
│       ├── dashboard.tsx   # Tableau de bord
│       ├── sinistres.tsx   # Gestion sinistres
│       ├── scanner.tsx     # Scanner OCR
│       ├── chat.tsx        # Copilote IA
│       └── courtiers.tsx   # Portail courtiers
├── src/
│   ├── api/client.ts       # Axios + JWT interceptors
│   └── context/
│       └── AuthContext.tsx # Auth state + SecureStore
├── app.json                # Configuration Expo
├── babel.config.js
├── package.json
└── tsconfig.json
```

## Fonctionnalités clés

- **OCR multi-documents** : CNI, carte grise, factures garage/hôpital, constats, certificats médicaux
- **Double-check Claude Vision + GPT-4o** : confiance affichée en temps réel
- **Champs ORASS** : mapping automatique des champs extraits vers les codes ORASS natifs
- **JWT SecureStore** : token stocké de façon sécurisée (iOS Keychain / Android Keystore)
- **Mode offline-ready** : fallback démo si API indisponible
- **Copilote CIMA** : base de connaissance complète Code CIMA Livres I-VI
