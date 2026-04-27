# Clés de production — YukpoTranslate Live

Ce document liste **toutes les clés API** nécessaires pour que YukpoTranslate Live fonctionne en production, et comment les obtenir.

Le module fonctionne déjà sans la plupart de ces clés (mode dégradé), mais l'expérience complète (streaming STT + traduction africaine + TTS studio) nécessite leur provisionnement.

---

## 1. Deepgram — STT streaming (OBLIGATOIRE pour la production)

**Usage** : transcription audio temps réel (Nova-3, multi-langue, low-latency).
**Requise pour** : WebSocket `/api/v1/translate/live/ws` + endpoint REST `/chunk`.

### Obtenir la clé
1. Aller sur https://console.deepgram.com/signup
2. Créer un compte — **200 USD de crédits offerts** à l'inscription (≈ 45 000 minutes de STT)
3. Dashboard → **API Keys** → **Create a New API Key**
4. Scope : `Member` (suffit pour l'inférence)
5. Copier la clé (format : 40 caractères alphanum)

### Tarification
- Nova-3 streaming : **0,0043 USD / minute** (≈ 2,6 FCFA/min)
- Facturation à la seconde, pas de forfait mensuel
- Crédit prépayé ou post-paiement (CB + ACH)

### Configuration
```bash
# .env local
DEEPGRAM_API_KEY=sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Fly.io production
fly secrets set DEEPGRAM_API_KEY=sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Sans la clé
Le module démarre en **mode dégradé** : WebSocket accepté, mais aucune transcription retournée. Utile pour dev UI sans facturer.

---

## 2. OpenAI — Traduction (DÉJÀ CONFIGURÉE)

**Usage** : traduction texte via GPT-4o-mini (rapide + bon marché pour phrases courtes).

La clé `OPENAI_API_KEY` est **déjà configurée** via `core.ia_client` pour le reste de l'app. Aucune action supplémentaire.

### Tarification pertinente pour Translate Live
- GPT-4o-mini : 0,15 USD / 1M tokens input, 0,60 USD / 1M tokens output
- Une phrase de 20 mots ≈ 150 tokens in + 150 out = **0,0001 USD** (~0,06 FCFA)

---

## 3. Hugging Face — NLLB-200 langues africaines (RECOMMANDÉE)

**Usage** : traduction haute qualité pour wolof, yoruba, hausa, lingala, douala, igbo, zulu, xhosa, amharic (où GPT-4o-mini est moins fiable).

### Obtenir le token
1. Aller sur https://huggingface.co/join (gratuit)
2. **Settings** → **Access Tokens** → **New token**
3. Type : `Read`
4. Nom : `yukpo-translate-nllb`
5. Copier le token (format : `hf_xxxxxxxxxxxxxxxxx`)

### Tarification
- **Inference API gratuite** : 30 000 caractères/mois par modèle
- Au-delà : Inference Endpoints dédiés (~0,06 USD/h, facultatif)
- Pour la production, abonnement **HF Pro** à 9 USD/mois = 2 Go RAM × Inference illimitée

### Configuration
```bash
# .env local
HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Fly.io
fly secrets set HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Sans le token
Fallback transparent sur GPT-4o-mini (traductions correctes pour swahili, plus approximatives pour wolof/yoruba).

---

## 4. Azure Speech — TTS Neural (OPTIONNELLE, Sprint 2+)

**Usage** : synthèse vocale studio qualité pour voix naturelle (contre le TTS gratuit du navigateur).

Le frontend utilise déjà `window.speechSynthesis` (gratuit, universel). Azure Neural TTS est un **upgrade premium** pour qualité broadcasting.

### Obtenir la clé
1. Créer un compte Azure : https://azure.microsoft.com/fr-fr/free (200 USD de crédits 30 jours)
2. Portail Azure → **Créer une ressource** → **Speech Services**
3. Nom : `yukpo-speech`, Région : `westeurope` ou `francecentral`
4. Plan tarifaire : **F0 (gratuit)** — 500 000 caractères/mois neural voices
5. Onglet **Keys & Endpoint** → copier **Key 1** et la **Region**

### Tarification
- F0 : gratuit jusqu'à 500 000 caractères/mois neural
- S0 : **16 USD / 1M caractères** neural (≈ 10 000 FCFA pour 1M caractères)

### Configuration
```bash
AZURE_SPEECH_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AZURE_SPEECH_REGION=westeurope
```

### Intégration (à compléter si souhaité)
Le code actuel utilise le TTS gratuit du navigateur. Pour brancher Azure :
1. Installer `azure-cognitiveservices-speech` dans `requirements.txt`
2. Créer `modules/translate_live/azure_tts.py`
3. Ajouter endpoint `POST /api/v1/translate/live/tts` (retourne MP3 streaming)
4. Côté frontend : remplacer `getTTSSpeaker()` par un client qui lit le flux MP3

---

## 5. ElevenLabs — Voix clonées (OPTIONNELLE, premium)

**Usage** : voix hyperréalistes multilingues (qualité studio supérieure à Azure).

### Obtenir la clé
1. https://elevenlabs.io → créer un compte
2. **Profile** → **API Keys** → copier
3. Plan **Starter** : 22 USD/mois = 30 000 caractères (TTS haute fidélité)

### Sans la clé
Non utilisée par défaut. Intégration optionnelle future.

---

## 6. Twilio — WhatsApp (déjà configurée)

**Usage** : notifications (non liée à Translate Live mais présente dans le projet).
Configuration existante — pas d'action pour Translate Live.

---

## Checklist production minimale

Pour un déploiement production **full-featured** :

| Service | Priorité | Obligatoire ? | Coût mensuel estimé (100 utilisateurs × 30 min) |
|---------|----------|---------------|------------------------------------------------|
| Deepgram | **Critique** | Oui | ~13 USD |
| OpenAI | **Critique** | Déjà OK | ~0,30 USD |
| Hugging Face | Recommandée | Non (fallback GPT) | 0 USD (plan gratuit) |
| Azure Speech | Optionnelle | Non (navigateur) | 0 USD (F0) |
| ElevenLabs | Optionnelle | Non | 0 USD |

**Total minimum viable : ~13 USD/mois** pour Deepgram, le reste est géré par les clés existantes ou des tiers gratuits.

---

## Commandes récap — Fly.io

```bash
# Provisionnement initial (ordre recommandé)
fly secrets set DEEPGRAM_API_KEY=sk_xxx
fly secrets set HUGGINGFACE_TOKEN=hf_xxx

# Optionnel (TTS premium)
fly secrets set AZURE_SPEECH_KEY=xxx
fly secrets set AZURE_SPEECH_REGION=westeurope

# Vérifier
fly secrets list

# Redéployer pour activer
fly deploy
```

## Endpoints de diagnostic

Une fois les clés provisionnées, valider :

```bash
# Vérifier la disponibilité (remplace <token> par un JWT valide)
curl -H "Authorization: Bearer <token>" \
  https://app.yukpoassurance.com/api/v1/translate/live/status

# Réponse attendue :
{
  "stt_available": true,          # Deepgram OK
  "translator_available": true,   # OpenAI OK
  "tts_available": false,         # Azure non branché (normal)
  "price_per_minute_credits": 120,
  "price_per_minute_fcfa": 6.0
}

# Lister les langues
curl -H "Authorization: Bearer <token>" \
  https://app.yukpoassurance.com/api/v1/translate/live/langues
```

## Sécurité

- **Ne jamais committer** une clé en clair dans le repo
- `.env` est listé dans `.gitignore`
- Rotation des clés recommandée tous les 6 mois
- Sur Fly.io, utiliser `fly secrets` plutôt que `fly.toml` `env`
- Côté client (web/mobile) : le token JWT utilisateur est le seul secret transmis
- **Jamais de clé Deepgram/HF/Azure côté client** — toutes les requêtes externes passent par le backend
