"""
YukpoAssurance — Tarification Prédictive ML
Couche Machine Learning sur le moteur actuariel — sklearn RandomForest.

Architecture :
1. Feature engineering depuis le profil risque (age, zone, usage, antécédents...)
2. RandomForestRegressor — prédiction du score de risque 0-100
3. GradientBoostingClassifier — classification segment (bon/moyen/mauvais risque)
4. Entraînement sur données synthétiques CIMA-calibrées (remplacées par données réelles en prod)
5. Persistence du modèle avec joblib (rechargement à chaud)
6. Feedback loop : enregistrement des sinistres réels pour ré-entraînement
"""
from __future__ import annotations

import json
import logging
import math
import os
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("yukpo_assurance.tarification.ml")

# Dossier de persistance des modèles
_MODELS_DIR = Path(__file__).parent.parent.parent / "data" / "ml_models"
_MODELS_DIR.mkdir(parents=True, exist_ok=True)
_FEEDBACK_DIR = Path(__file__).parent.parent.parent / "data" / "ml_feedback"
_FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

_MODEL_RISK_PATH = _MODELS_DIR / "risk_score_model.pkl"
_MODEL_SEGMENT_PATH = _MODELS_DIR / "segment_model.pkl"
_SCALER_PATH = _MODELS_DIR / "feature_scaler.pkl"


# ── Feature names ─────────────────────────────────────────────────────────────
FEATURE_NAMES = [
    # Conducteur
    "age_conducteur",          # âge en années
    "anciennete_permis",       # années de permis
    "nb_sinistres_3ans",       # sinistres déclarés sur 3 ans
    "nb_infractions_3ans",     # infractions constatées
    "score_bonus_malus",       # 0.50 (max bonus) → 3.50 (max malus), CRM CIMA
    # Véhicule
    "puissance_fiscale_cv",    # chevaux fiscaux
    "age_vehicule_ans",        # âge du véhicule
    "valeur_venale_mfcfa",     # valeur vénale en millions FCFA
    "usage_code",              # 0=particulier 1=societe 2=utilitaire 3=taxi 4=transport_commun
    # Contexte
    "zone_risque",             # 0=faible 1=moyen 2=eleve (Maroua=0, Douala=2)
    "saison_pluie",            # 1 si souscription en saison des pluies (avril-oct)
    "branche_code",            # 0=auto_rc 1=auto_tr 2=ird 3=rc_pro 4=transport
    # Compagnie
    "taux_cession_reassurance",# 0-1
    "ratio_sp_branche",        # ratio sinistres/primes branche sur 12 mois
]


@dataclass
class ProfilRisqueML:
    """Profil risque pour la prédiction ML."""
    # Conducteur
    age_conducteur: int = 35
    anciennete_permis: int = 10
    nb_sinistres_3ans: int = 0
    nb_infractions_3ans: int = 0
    score_bonus_malus: float = 1.0    # CRM neutre

    # Véhicule
    puissance_fiscale_cv: int = 6
    age_vehicule_ans: int = 5
    valeur_venale_mfcfa: float = 5.0
    usage: str = "particulier"        # particulier|societe|utilitaire|taxi|transport_commun

    # Contexte
    zone: str = "yaounde"             # yaounde|douala|bafoussam|garoua|maroua|autres
    mois_souscription: int = 6        # 1-12
    branche: str = "auto_rc"          # auto_rc|auto_tr|ird|rc_pro|transport

    # Compagnie
    taux_cession_reassurance: float = 0.15
    ratio_sp_branche: float = 0.62


@dataclass
class PredictionML:
    """Résultat de la prédiction ML."""
    score_risque: float              # 0-100 (0=risque très faible, 100=risque extrême)
    segment_risque: str              # "bon_risque" | "risque_moyen" | "risque_eleve"
    coefficient_ml: float            # facteur à appliquer sur la prime actuarielle (0.7-1.5)
    prime_suggestion_fcfa: float     # prime suggérée (actuarielle × coefficient_ml)
    prime_actuarielle_fcfa: float    # prime de base sans ML
    gain_precision_pct: float        # gain estimé de précision vs tarif forfaitaire
    features_importance: dict        # top features ayant influencé la prédiction
    confiance: str                   # "haute" | "moyenne" | "faible"
    modele_version: str = "1.0"


class MLTarification:
    """
    Moteur de tarification prédictive ML pour YukpoAssurance.
    Intègre RandomForest sur le moteur actuariel existant.
    """

    def __init__(self):
        self._risk_model = None
        self._segment_model = None
        self._scaler = None
        self._model_trained = False
        self._training_samples = 0
        self._last_trained = None
        self._version_modele: str = "1.0"

        # Tentative de chargement des modèles persistés
        self._charger_modeles()
        self._version_modele = self._charger_version()

        # Si pas de modèles sauvegardés, entraîner sur données synthétiques
        if not self._model_trained:
            logger.info("[MLTarif] Aucun modèle trouvé — entraînement sur données synthétiques")
            self.entrainer()

    # ─── Entraînement ─────────────────────────────────────────────────────────

    def entrainer(self, donnees_reelles: Optional[list[dict]] = None) -> dict:
        """
        Entraîne les modèles ML.
        Si donnees_reelles est fourni, utilise ces données.
        Sinon, génère des données synthétiques calibrées CIMA.
        """
        try:
            from sklearn.ensemble import RandomForestRegressor, GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import cross_val_score
        except ImportError:
            logger.error("[MLTarif] scikit-learn non installé — tarification ML désactivée")
            return {"statut": "erreur", "detail": "scikit-learn requis : pip install scikit-learn"}

        t0 = time.monotonic()

        if donnees_reelles:
            X, y_score, y_segment = self._preparer_features_reelles(donnees_reelles)
        else:
            X, y_score, y_segment = self._generer_donnees_synthetiques(n=5000)

        # Scaler
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Modèle 1 : RandomForest score risque (0-100)
        rf = RandomForestRegressor(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        rf.fit(X_scaled, y_score)

        # Modèle 2 : GradientBoosting segment (bon/moyen/eleve)
        gb = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        )
        gb.fit(X_scaled, y_segment)

        # Cross-validation score
        cv_scores = cross_val_score(rf, X_scaled, y_score, cv=5, scoring="neg_mean_absolute_error")
        mae_moyen = -cv_scores.mean()

        self._risk_model = rf
        self._segment_model = gb
        self._scaler = scaler
        self._model_trained = True
        self._training_samples = len(X)
        self._last_trained = time.time()

        # Persistance
        self._sauvegarder_modeles()

        duree = time.monotonic() - t0
        logger.info(
            f"[MLTarif] Modèles entraînés — {len(X)} samples, MAE={mae_moyen:.2f}, "
            f"durée={duree:.1f}s"
        )

        return {
            "statut": "ok",
            "nb_samples": len(X),
            "mae_cv": round(mae_moyen, 2),
            "duree_secondes": round(duree, 1),
            "features": FEATURE_NAMES,
        }

    # ─── Prédiction ───────────────────────────────────────────────────────────

    def predire(
        self,
        profil: ProfilRisqueML,
        prime_actuarielle_fcfa: float,
    ) -> PredictionML:
        """
        Prédit le score de risque et la prime ajustée pour un profil.
        Intègre les résultats ML avec la prime actuarielle de base.
        """
        if not self._model_trained:
            return self._fallback_actuariel(profil, prime_actuarielle_fcfa)

        try:
            features = self._profil_to_features(profil)
            X = np.array([features])
            X_scaled = self._scaler.transform(X)

            score = float(np.clip(self._risk_model.predict(X_scaled)[0], 0, 100))
            segment_idx = self._segment_model.predict(X_scaled)[0]
            segment_map = {0: "bon_risque", 1: "risque_moyen", 2: "risque_eleve"}
            segment = segment_map.get(segment_idx, "risque_moyen")

            # Coefficient d'ajustement basé sur le score (0.70 à 1.50)
            coeff = self._score_to_coeff(score)
            prime_suggeree = prime_actuarielle_fcfa * coeff

            # Importance des features
            importance = self._top_features(self._risk_model.feature_importances_, n=5)

            confiance = "haute" if self._training_samples >= 1000 else "moyenne"

            return PredictionML(
                score_risque=round(score, 1),
                segment_risque=segment,
                coefficient_ml=round(coeff, 3),
                prime_suggestion_fcfa=round(prime_suggeree),
                prime_actuarielle_fcfa=round(prime_actuarielle_fcfa),
                gain_precision_pct=round(abs(1 - coeff) * 100, 1),
                features_importance=importance,
                confiance=confiance,
                modele_version="1.0",
            )

        except Exception as e:
            logger.warning(f"[MLTarif] Prédiction échouée: {e} — fallback actuariel")
            return self._fallback_actuariel(profil, prime_actuarielle_fcfa)

    def predire_lot(
        self,
        profils: list[tuple[ProfilRisqueML, float]],
    ) -> list[PredictionML]:
        """Prédiction en lot (vectorisé — efficient pour batch scoring)."""
        if not self._model_trained or not profils:
            return [self._fallback_actuariel(p, pa) for p, pa in profils]

        try:
            features_list = [self._profil_to_features(p) for p, _ in profils]
            X = np.array(features_list)
            X_scaled = self._scaler.transform(X)

            scores = np.clip(self._risk_model.predict(X_scaled), 0, 100)
            segments = self._segment_model.predict(X_scaled)
            segment_map = {0: "bon_risque", 1: "risque_moyen", 2: "risque_eleve"}
            importance = self._top_features(self._risk_model.feature_importances_, n=5)

            resultats = []
            for i, (profil, prime_actuarielle) in enumerate(profils):
                score = float(scores[i])
                coeff = self._score_to_coeff(score)
                resultats.append(PredictionML(
                    score_risque=round(score, 1),
                    segment_risque=segment_map.get(segments[i], "risque_moyen"),
                    coefficient_ml=round(coeff, 3),
                    prime_suggestion_fcfa=round(prime_actuarielle * coeff),
                    prime_actuarielle_fcfa=round(prime_actuarielle),
                    gain_precision_pct=round(abs(1 - coeff) * 100, 1),
                    features_importance=importance,
                    confiance="haute" if self._training_samples >= 1000 else "moyenne",
                ))
            return resultats

        except Exception as e:
            logger.warning(f"[MLTarif] Prédiction lot échouée: {e}")
            return [self._fallback_actuariel(p, pa) for p, pa in profils]

    def rapport_performance(self) -> dict:
        """Rapport de performance du modèle ML."""
        if not self._model_trained:
            return {"statut": "non_entraine"}

        feature_importances = {}
        if self._risk_model:
            feature_importances = dict(zip(
                FEATURE_NAMES,
                [round(float(v), 4) for v in self._risk_model.feature_importances_],
            ))
            feature_importances = dict(sorted(
                feature_importances.items(), key=lambda x: x[1], reverse=True
            ))

        nb_feedbacks = self._compter_feedbacks()
        return {
            "statut": "ok",
            "training_samples": self._training_samples,
            "modele_type": "RandomForestRegressor + GradientBoostingClassifier",
            "feature_importances": feature_importances,
            "derniere_mise_a_jour": self._last_trained,
            "version_modele": self._version_modele,
            "nb_feedbacks_collectes": nb_feedbacks,
            "pret_pour_retrainement": nb_feedbacks >= 100,
            "modeles_persistes": {
                "risk_score": str(_MODEL_RISK_PATH),
                "segment": str(_MODEL_SEGMENT_PATH),
            },
        }

    # ─── Feedback loop ────────────────────────────────────────────────────────

    def enregistrer_feedback(
        self,
        profil: ProfilRisqueML,
        prime_proposee_fcfa: float,
        prime_reelle_fcfa: float,
        sinistre_survenu: bool,
        montant_sinistre_fcfa: float = 0.0,
        metadata: dict = None,
    ) -> bool:
        """
        Enregistre un feedback réel (sinistre survenu ou non) pour le ré-entraînement.
        Les données s'accumulent dans data/ml_feedback/ en JSON-Lines.
        Quand > 100 feedbacks → déclenche automatiquement un ré-entraînement.
        """
        feedback = {
            **{k: getattr(profil, k) for k in [
                "age_conducteur", "anciennete_permis", "nb_sinistres_3ans",
                "nb_infractions_3ans", "score_bonus_malus", "puissance_fiscale_cv",
                "age_vehicule_ans", "valeur_venale_mfcfa", "usage",
                "zone", "mois_souscription", "branche",
                "taux_cession_reassurance", "ratio_sp_branche",
            ]},
            "prime_proposee_fcfa": prime_proposee_fcfa,
            "prime_reelle_fcfa": prime_reelle_fcfa,
            "sinistre_survenu": sinistre_survenu,
            "montant_sinistre_fcfa": montant_sinistre_fcfa,
            "score_risque_reel": min(100, max(0, (montant_sinistre_fcfa / max(prime_reelle_fcfa, 1)) * 40))
                                  if sinistre_survenu else max(0, (prime_reelle_fcfa - prime_proposee_fcfa) / max(prime_proposee_fcfa, 1) * 10),
            "timestamp": time.time(),
            **(metadata or {}),
        }
        try:
            _FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
            chemin = _FEEDBACK_DIR / "feedbacks.jsonl"
            with open(chemin, "a", encoding="utf-8") as f:
                f.write(json.dumps(feedback, ensure_ascii=False) + "\n")
            logger.debug(f"[MLTarif] Feedback enregistré — sinistre={sinistre_survenu}")

            # Auto-retrainement si seuil atteint
            nb = self._compter_feedbacks()
            if nb >= 100 and nb % 100 == 0:
                logger.info(f"[MLTarif] Seuil feedback atteint ({nb}) → ré-entraînement auto")
                self.retrainer_sur_feedbacks()
            return True
        except Exception as e:
            logger.warning(f"[MLTarif] Feedback non enregistré: {e}")
            return False

    def retrainer_sur_feedbacks(self) -> dict:
        """Ré-entraîne le modèle en combinant données synthétiques + feedbacks réels."""
        feedbacks = self._charger_feedbacks()
        if not feedbacks:
            return {"statut": "aucun_feedback", "detail": "Aucun feedback disponible"}
        logger.info(f"[MLTarif] Ré-entraînement sur {len(feedbacks)} feedbacks réels")
        resultat = self.entrainer(donnees_reelles=feedbacks)
        # Incrémenter la version
        self._version_modele = f"v{int(self._version_modele.lstrip('v')) + 1}"
        self._sauvegarder_version()
        return {**resultat, "version": self._version_modele, "feedbacks_utilises": len(feedbacks)}

    def _charger_feedbacks(self) -> list[dict]:
        chemin = _FEEDBACK_DIR / "feedbacks.jsonl"
        if not chemin.exists():
            return []
        feedbacks = []
        try:
            with open(chemin, encoding="utf-8") as f:
                for ligne in f:
                    try:
                        feedbacks.append(json.loads(ligne.strip()))
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[MLTarif] Chargement feedbacks échoué: {e}")
        return feedbacks

    def _compter_feedbacks(self) -> int:
        chemin = _FEEDBACK_DIR / "feedbacks.jsonl"
        if not chemin.exists():
            return 0
        try:
            with open(chemin, encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def _sauvegarder_version(self):
        try:
            with open(_MODELS_DIR / "version.txt", "w") as f:
                f.write(self._version_modele)
        except Exception:
            pass

    def _charger_version(self) -> str:
        try:
            v_path = _MODELS_DIR / "version.txt"
            if v_path.exists():
                return v_path.read_text().strip() or "1.0"
        except Exception:
            pass
        return "1.0"

    def evaluer_derive(self) -> dict:
        """
        Évalue la dérive du modèle sur les feedbacks récents.
        Retourne un rapport avec métriques et recommandation de ré-entraînement.
        """
        feedbacks = self._charger_feedbacks()
        if len(feedbacks) < 10:
            return {"statut": "insuffisant", "nb_feedbacks": len(feedbacks), "minimum_requis": 10}

        erreurs = []
        for fb in feedbacks[-200:]:  # 200 derniers feedbacks
            profil = ProfilRisqueML(
                age_conducteur=fb.get("age_conducteur", 35),
                anciennete_permis=fb.get("anciennete_permis", 10),
                nb_sinistres_3ans=fb.get("nb_sinistres_3ans", 0),
                nb_infractions_3ans=fb.get("nb_infractions_3ans", 0),
                score_bonus_malus=fb.get("score_bonus_malus", 1.0),
                puissance_fiscale_cv=fb.get("puissance_fiscale_cv", 6),
                age_vehicule_ans=fb.get("age_vehicule_ans", 5),
                valeur_venale_mfcfa=fb.get("valeur_venale_mfcfa", 5.0),
                usage=fb.get("usage", "particulier"),
                zone=fb.get("zone", "yaounde"),
                mois_souscription=fb.get("mois_souscription", 6),
                branche=fb.get("branche", "auto_rc"),
                taux_cession_reassurance=fb.get("taux_cession_reassurance", 0.15),
                ratio_sp_branche=fb.get("ratio_sp_branche", 0.62),
            )
            pred = self.predire(profil, fb.get("prime_reelle_fcfa", 100000))
            reel = fb.get("score_risque_reel", 50)
            erreurs.append(abs(pred.score_risque - reel))

        mae = sum(erreurs) / len(erreurs) if erreurs else 0
        derive_detectee = mae > 15  # Seuil de dérive : MAE > 15 points

        return {
            "statut": "ok",
            "nb_feedbacks_evalues": len(feedbacks[-200:]),
            "mae_actuelle": round(mae, 2),
            "seuil_derive": 15.0,
            "derive_detectee": derive_detectee,
            "recommandation": "Ré-entraîner le modèle" if derive_detectee else "Modèle stable",
            "version_actuelle": self._version_modele,
        }

    # ─── Feature engineering ──────────────────────────────────────────────────

    def _profil_to_features(self, profil: ProfilRisqueML) -> list[float]:
        usage_map = {
            "particulier": 0, "societe": 1, "utilitaire": 2,
            "taxi": 3, "transport_commun": 4,
        }
        zone_map = {
            "maroua": 0, "garoua": 0, "bertoua": 0, "ebolowa": 0,
            "ngaoundere": 0, "bafoussam": 1, "buea": 1, "autres": 1,
            "yaounde": 2, "douala": 2,
        }
        branche_map = {
            "auto_rc": 0, "auto_tr": 1, "ird": 2, "rc_pro": 3, "transport": 4,
        }
        saison_pluie = 1 if profil.mois_souscription in (4, 5, 6, 7, 8, 9, 10) else 0

        return [
            float(profil.age_conducteur),
            float(profil.anciennete_permis),
            float(profil.nb_sinistres_3ans),
            float(profil.nb_infractions_3ans),
            float(profil.score_bonus_malus),
            float(profil.puissance_fiscale_cv),
            float(profil.age_vehicule_ans),
            float(profil.valeur_venale_mfcfa),
            float(usage_map.get(profil.usage, 0)),
            float(zone_map.get(profil.zone, 1)),
            float(saison_pluie),
            float(branche_map.get(profil.branche, 0)),
            float(profil.taux_cession_reassurance),
            float(profil.ratio_sp_branche),
        ]

    def _preparer_features_reelles(
        self, donnees: list[dict]
    ) -> tuple:
        """Convertit des données réelles (sinistres/polices) en matrices numpy."""
        X, y_score, y_segment = [], [], []
        for d in donnees:
            p = ProfilRisqueML(
                age_conducteur=d.get("age_conducteur", 35),
                anciennete_permis=d.get("anciennete_permis", 10),
                nb_sinistres_3ans=d.get("nb_sinistres_3ans", 0),
                nb_infractions_3ans=d.get("nb_infractions_3ans", 0),
                score_bonus_malus=d.get("score_bonus_malus", 1.0),
                puissance_fiscale_cv=d.get("puissance_fiscale_cv", 6),
                age_vehicule_ans=d.get("age_vehicule_ans", 5),
                valeur_venale_mfcfa=d.get("valeur_venale_mfcfa", 5.0),
                usage=d.get("usage", "particulier"),
                zone=d.get("zone", "yaounde"),
                mois_souscription=d.get("mois_souscription", 6),
                branche=d.get("branche", "auto_rc"),
                taux_cession_reassurance=d.get("taux_cession_reassurance", 0.15),
                ratio_sp_branche=d.get("ratio_sp_branche", 0.62),
            )
            score = float(d.get("score_risque_reel", 50))
            segment = 0 if score < 35 else (1 if score < 65 else 2)
            X.append(self._profil_to_features(p))
            y_score.append(score)
            y_segment.append(segment)

        return np.array(X), np.array(y_score), np.array(y_segment)

    def _generer_donnees_synthetiques(
        self, n: int = 5000
    ) -> tuple:
        """
        Génère des données synthétiques pour l'entraînement initial.
        Modèle de risque calibré pour la zone CIMA (Cameroun).
        """
        rng = np.random.RandomState(42)
        X, y_score, y_segment = [], [], []

        for _ in range(n):
            age = rng.randint(18, 75)
            anciennete = min(age - 18, rng.randint(0, 50))
            sinistres = rng.choice([0, 0, 0, 1, 1, 2, 3], p=[0.55, 0.0, 0.0, 0.25, 0.0, 0.12, 0.08])
            infractions = rng.choice([0, 0, 1, 2], p=[0.70, 0.0, 0.22, 0.08])
            crm = rng.uniform(0.50, 3.50)
            puissance = rng.randint(2, 14)
            age_veh = rng.randint(0, 25)
            valeur = rng.uniform(0.5, 50.0)
            usage = rng.randint(0, 5)
            zone = rng.randint(0, 3)
            saison = rng.randint(0, 2)
            branche = rng.randint(0, 5)
            taux_rea = rng.uniform(0.05, 0.50)
            ratio_sp = rng.uniform(0.40, 1.20)

            # Score de risque (modèle synthétique calibré CIMA)
            score = (
                max(0, 30 - age) * 0.5           # jeunes conducteurs = risque +
                + anciennete * (-0.3)             # expérience = risque -
                + sinistres * 12                  # sinistres passés = risque ++
                + infractions * 8                 # infractions = risque +
                + (crm - 1.0) * 15               # malus = risque +
                + (puissance - 6) * 1.2          # grosse cylindrée = risque +
                + max(0, age_veh - 8) * 1.5      # vieux véhicule = risque +
                + zone * 5                        # zone Douala = risque +
                + saison * 4                      # saison pluie = risque +
                + (usage >= 3) * 15              # taxi/transport = risque ++
                + max(0, ratio_sp - 0.7) * 20    # mauvais S/P branche = risque +
                + rng.normal(0, 5)               # bruit
            )
            score = float(np.clip(score + 30, 0, 100))
            segment = 0 if score < 35 else (1 if score < 65 else 2)

            X.append([
                age, anciennete, sinistres, infractions, crm,
                puissance, age_veh, valeur, usage,
                zone, saison, branche, taux_rea, ratio_sp,
            ])
            y_score.append(score)
            y_segment.append(segment)

        return np.array(X), np.array(y_score), np.array(y_segment)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _score_to_coeff(self, score: float) -> float:
        """
        Convertit le score de risque (0-100) en coefficient multiplicateur.
        Bon risque (0-34)   : 0.70 – 0.90  (réduction prime)
        Risque moyen (35-64): 0.95 – 1.10  (neutre)
        Risque élevé (65+)  : 1.15 – 1.50  (majoration prime)
        """
        if score < 35:
            return 0.90 - (35 - score) / 35 * 0.20   # 0.70 à 0.90
        elif score < 65:
            return 0.95 + (score - 35) / 30 * 0.15   # 0.95 à 1.10
        else:
            return 1.15 + (score - 65) / 35 * 0.35   # 1.15 à 1.50

    def _top_features(self, importances, n: int = 5) -> dict:
        idx = np.argsort(importances)[::-1][:n]
        return {
            FEATURE_NAMES[i]: round(float(importances[i]), 4)
            for i in idx
        }

    def _fallback_actuariel(
        self, profil: ProfilRisqueML, prime_actuarielle: float
    ) -> PredictionML:
        """Fallback sans ML — score actuariel simple."""
        score = min(100, max(0,
            profil.nb_sinistres_3ans * 15
            + profil.nb_infractions_3ans * 8
            + (profil.score_bonus_malus - 1.0) * 20
            + (profil.age_conducteur < 25) * 10
        ))
        coeff = self._score_to_coeff(score)
        segment = "bon_risque" if score < 35 else ("risque_moyen" if score < 65 else "risque_eleve")
        return PredictionML(
            score_risque=score,
            segment_risque=segment,
            coefficient_ml=coeff,
            prime_suggestion_fcfa=round(prime_actuarielle * coeff),
            prime_actuarielle_fcfa=round(prime_actuarielle),
            gain_precision_pct=0.0,
            features_importance={},
            confiance="faible",
            modele_version="fallback_actuariel",
        )

    # ─── Persistance ──────────────────────────────────────────────────────────

    def _sauvegarder_modeles(self):
        try:
            with open(_MODEL_RISK_PATH, "wb") as f:
                pickle.dump(self._risk_model, f)
            with open(_MODEL_SEGMENT_PATH, "wb") as f:
                pickle.dump(self._segment_model, f)
            with open(_SCALER_PATH, "wb") as f:
                pickle.dump(self._scaler, f)
            logger.info(f"[MLTarif] Modèles sauvegardés dans {_MODELS_DIR}")
        except Exception as e:
            logger.warning(f"[MLTarif] Sauvegarde modèles échouée: {e}")

    def _charger_modeles(self):
        try:
            if not (_MODEL_RISK_PATH.exists() and _MODEL_SEGMENT_PATH.exists() and _SCALER_PATH.exists()):
                return
            with open(_MODEL_RISK_PATH, "rb") as f:
                self._risk_model = pickle.load(f)
            with open(_MODEL_SEGMENT_PATH, "rb") as f:
                self._segment_model = pickle.load(f)
            with open(_SCALER_PATH, "rb") as f:
                self._scaler = pickle.load(f)
            self._model_trained = True
            self._training_samples = 5000  # estimé
            logger.info("[MLTarif] Modèles chargés depuis disque")
        except Exception as e:
            logger.warning(f"[MLTarif] Chargement modèles échoué: {e}")
            self._model_trained = False


# Instance singleton (entraîne si nécessaire au démarrage)
ml_tarification = MLTarification()
