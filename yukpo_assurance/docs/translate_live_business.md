# YukpoTranslate Live — Chiffrage & modèle économique

Version : 1.0  
Date : 2026-04-23  
Statut : estimation Sprint 1 — à valider après 50 utilisateurs réels

---

## 1. Coût variable par heure d'utilisation (Sprint 1 — sous-titres seuls)

Hypothèse : 1 heure de streaming audio active (parole + silence), langue FR → EN.

| Composant | Provider | Tarif public | Coût/h |
|---|---|---|---|
| STT streaming | Deepgram Nova-3 | $0.0043 / min | ~$0.26 |
| Traduction | GPT-4o-mini | ~$0.15 in / $0.60 out / 1M tokens. ~400 utterances/h × 40 tokens in + 40 tokens out ≈ 32k tokens | ~$0.02 |
| TTS (Sprint 2+) | — | — | $0.00 (pas encore activé) |
| **Total STT+trad** | — | — | **~$0.28 / h** |

À 600 FCFA / USD : **168 FCFA / h** de coût réel fournisseurs.

---

## 2. Grille Yukpo — transposée dans le modèle crédits existant

Rappel multiplicateur Yukpo : **×20** sur le coût FCFA réel (cf. `service_credits.MULTIPLICATEUR_YUKPO`).

| Durée streaming | Coût réel FCFA | Crédits Yukpo débités | Équivalent FCFA utilisateur |
|---|---|---|---|
| 1 minute | 2.8 | 56 | 2.8 FCFA |
| 15 minutes | 42 | 840 | 42 FCFA |
| 1 heure | 168 | **3 360** | 168 FCFA |
| 10 heures | 1 680 | 33 600 | 1 680 FCFA |

Arrondi technique dans le code : **120 crédits / minute** active (marge supplémentaire pour absorber pics d'usage et frais infra). Ajustable dans `session.py` si les chiffres de production divergent.

---

## 3. Impact sur les plans d'abonnement existants

Crédits mensuels (`CREDITS_PAR_PLAN` dans `service_credits.py`) :

| Plan | Crédits/mois | Équivalent en heures de traduction live | Reste pour autres modules IA |
|---|---:|---:|---|
| Gratuit | 1 000 | ~8 minutes | 0 — plafond très vite atteint |
| Starter | 5 000 | ~42 minutes | 0 crédits pour chat/rapports |
| Pro | 20 000 | ~2 h 46 min | ~5 000 crédits pour autres modules |
| Business | illimité | illimité | illimité |

**Recommandation** :
- Positionner la **traduction live comme feature Pro+** : plafond automatique mensuel suggéré à ~3 h/mois = 21 600 crédits (dépasse Starter, absorbable par Pro).
- Permettre la recharge (packs crédits existants dans `routes_pro_abonnement.py`).
- Afficher clairement dans l'UI : « ~120 crédits par minute ».

---

## 4. Break-even

**Hypothèses** :
- Prix Pro YukpoPro : 3 000 FCFA / mois (source : UI existante).
- Revenu brut par abonné Pro = 3 000 FCFA.
- Coût infra mutualisé YukpoPro : ~50 FCFA / mois / utilisateur (négligeable vs variable).

**Seuil d'alerte** : si un utilisateur Pro dépasse 10 h/mois de traduction live, il consomme 1 680 FCFA de coût variable → marge brute passe de 100% à ~44%.

| Plan | Prix mensuel | Budget coût variable acceptable (marge 40%) | Durée traduction live max |
|---|---:|---:|---:|
| Starter (1 000 FCFA/mois)  | 1 000 | 600 | ~3.5 h/mois |
| Pro (3 000 FCFA/mois)      | 3 000 | 1 800 | ~10 h/mois |
| Business (sur devis)       | négociable | — | illimité technique |

### Action : plafond dur dans `session.py`
- Gratuit : 15 min/jour (équivalent 7 h/mois)
- Starter : 1 h/mois
- Pro : 10 h/mois
- Business : illimité

Alerte UI à 80% du plafond.

---

## 5. Sensibilité aux tarifs Deepgram

Deepgram facture par minute d'audio, pas par caractère. Variation de tarif :
- +50% (renégociation, dévaluation USD) → 4 FCFA/min coût réel → 80 crédits/min → marge reste positive sur Pro jusqu'à ~10 h/mois.
- Alternative Option C (Whisper.cpp self-host + GPU) rentable dès **50 utilisateurs Pro actifs × 5 h/mois** ≈ 250 h/mois de STT. En dessous, Deepgram pay-as-you-go reste plus simple et souvent moins cher.

---

## 6. Risques

| Risque | Impact | Mitigation |
|---|---|---|
| Rupture API Deepgram | Bloque la fonctionnalité | Fallback Whisper.cpp local à déployer en Sprint 2 ; dégradation UX acceptable (latence ↑) |
| Qualité faible langues africaines (Wolof, Swahili…) | Perte de différenciation Afrique | Sprint 3 : NLLB-200 fine-tuné. Au Sprint 1, ne pas promettre ces langues dans l'UI |
| Capture audio YouTube avec DRM | Certaines vidéos refusent `getDisplayMedia` avec audio | Document utilisateur : « fonctionne sur contenu non-DRM. Sinon → utiliser micro vers haut-parleur » |
| Abus de streaming (utilisateur laisse tourner 24h) | Coût exploser | Plafond dur côté session + auto-pause sur inactivité vocale (VAD) 5 min |
| Législation enregistrement conversations | Amende potentielle | Bandeau d'avertissement obligatoire côté UI + mention CGU |

---

## 7. Go / No-Go après Sprint 1

Critères pour lancer Sprint 2 (TTS voix) :
- ≥ 10 utilisateurs Pro actifs ayant testé la fonction au moins 2 fois
- Latence médiane observée < 3 s
- Retours qualitatifs positifs sur utilité
- Coût variable effectif < 200 FCFA / h en moyenne (vérifie l'ordre de grandeur de cette note)

Si critères non atteints : réorienter vers export transcript seul (plus simple, moins cher) ou pivoter vers cas d'usage conférence corporate uniquement.

---

## 8. Pré-requis go-to-production

- [ ] `DEEPGRAM_API_KEY` ajoutée aux secrets Fly.io
- [ ] CGU + mention RGPD traduction mises à jour
- [ ] Plafond dur mensuel par plan implémenté dans `session.py`
- [ ] Dashboard admin : colonne « minutes traduction consommées » / utilisateur
- [ ] Test de charge : 20 sessions WS simultanées (ciblé Pro beta)
