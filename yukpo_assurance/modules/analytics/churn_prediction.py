"""
YukpoAssurance — Prédiction de résiliation (Churn Prediction)
Calcule le risque de résiliation pour chaque contrat et propose
des actions de rétention ciblées.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orass_connector import orass

logger = logging.getLogger("yukpo_assurance.analytics.churn")

PROMPT_CHURN = """Tu es expert en rétention client pour une compagnie d'assurance CIMA.

PROFIL CLIENT :
{profil}

ANALYSE LE RISQUE DE RÉSILIATION :

1. Score de risque résiliation (0-100)
   - 0-30  : Client fidèle stable — surveillance normale
   - 30-60 : Risque modéré — action préventive recommandée
   - 60-80 : Risque élevé — contact urgent requis
   - 80-100: Résiliation imminente — intervention immédiate

2. Facteurs déclencheurs identifiés (liste les 3 principaux)

3. Action recommandée (1 seule, la plus efficace) :
   - Offre de fidélisation (réduction prime X%)
   - Appel commercial personnalisé
   - Restructuration du contrat (garanties mieux adaptées)
   - Accepter la résiliation (client non profitable — LTV négatif)

4. Valeur client estimée sur 3 ans (LTV en FCFA)
   - Prime annuelle × durée probable × (1 - sinistralité attendue)

5. Priorité d'action : URGENT (agir sous 7j) | STANDARD (30j) | FAIBLE (90j)

Retourne UNIQUEMENT ce JSON :
{{
  "score_churn": 0-100,
  "niveau_risque": "stable|modéré|élevé|critique",
  "facteurs_cles": ["facteur 1", "facteur 2", "facteur 3"],
  "action_recommandee": "description de l'action",
  "ltv_fcfa": 000000,
  "priorite": "urgent|standard|faible",
  "message_commercial": "Message personnalisé à envoyer au client (2 phrases max)"
}}"""


@dataclass
class PredictionChurn:
    numero_police: str
    score_churn: int            # 0-100
    niveau_risque: str          # stable | modéré | élevé | critique
    facteurs_cles: list[str]
    action_recommandee: str
    ltv_fcfa: int               # Lifetime Value estimé
    priorite: str               # urgent | standard | faible
    message_commercial: str     # Prêt à envoyer par WhatsApp/email


class ChurnPredictionService:
    """
    Prédit le risque de résiliation de chaque contrat.
    Analyse : ancienneté, sinistres, retards, variation prime, engagement.
    """

    async def predire(self, numero_police: str) -> PredictionChurn:
        """Calcule le score de churn pour un contrat donné"""
        contrat = await orass.rechercher_contrat(numero_police=numero_police)
        if not contrat:
            return PredictionChurn(
                numero_police=numero_police,
                score_churn=0, niveau_risque="inconnu",
                facteurs_cles=[], action_recommandee="Contrat introuvable",
                ltv_fcfa=0, priorite="faible", message_commercial="",
            )

        sinistres = await orass.lister_sinistres_par_police(numero_police)
        impayes = await orass.lister_impayes(seuil_jours=1)
        impaye_ce_contrat = next(
            (i for i in impayes if i.get("numero_police") == numero_police), None
        )

        from datetime import date
        anciennete_jours = (date.today() - contrat.date_effet).days
        nb_sinistres = len(sinistres)
        jours_echeance = (contrat.date_echeance - date.today()).days

        profil = {
            "numero_police": numero_police,
            "branche": contrat.branche,
            "anciennete_jours": anciennete_jours,
            "anciennete_annees": round(anciennete_jours / 365, 1),
            "nb_sinistres_3ans": nb_sinistres,
            "statut_paiement": "impayé" if impaye_ce_contrat else "à jour",
            "jours_retard_paiement": impaye_ce_contrat.get("jours_retard", 0) if impaye_ce_contrat else 0,
            "jours_avant_echeance": jours_echeance,
            "prime_nette_fcfa": contrat.prime_nette,
            "prime_ttc_fcfa": contrat.prime_ttc,
            "statut_contrat": contrat.statut,
            "courtier": contrat.courtier_code,
        }

        try:
            reponse = await ia_client.appeler(
                prompt=PROMPT_CHURN.format(profil=profil),
                mode=ModeIA.ANALYSE,
                json_attendu=True,
            )
            data = reponse.as_json()
            return PredictionChurn(
                numero_police=numero_police,
                score_churn=int(data.get("score_churn", 0)),
                niveau_risque=data.get("niveau_risque", "inconnu"),
                facteurs_cles=data.get("facteurs_cles", []),
                action_recommandee=data.get("action_recommandee", ""),
                ltv_fcfa=int(data.get("ltv_fcfa", 0)),
                priorite=data.get("priorite", "standard"),
                message_commercial=data.get("message_commercial", ""),
            )
        except Exception as e:
            logger.warning(f"[Churn] Erreur prédiction {numero_police}: {e}")
            # Fallback déterministe
            score = self._score_deterministe(profil)
            return PredictionChurn(
                numero_police=numero_police,
                score_churn=score,
                niveau_risque=self._niveau(score),
                facteurs_cles=self._facteurs(profil),
                action_recommandee="Appel commercial recommandé" if score > 40 else "Surveillance standard",
                ltv_fcfa=int(contrat.prime_nette * 3 * 0.6),
                priorite="urgent" if score > 70 else "standard",
                message_commercial="",
            )

    async def analyser_portefeuille_churn(self, limite: int = 20) -> dict:
        """
        Analyse les N contrats les plus à risque du portefeuille.
        À utiliser pour les campagnes de rétention ciblées.
        """
        impayes = await orass.lister_impayes(seuil_jours=30)
        polices_a_risque = [i["numero_police"] for i in impayes[:limite]]

        predictions = []
        for police in polices_a_risque:
            try:
                pred = await self.predire(police)
                predictions.append({
                    "police": pred.numero_police,
                    "score": pred.score_churn,
                    "risque": pred.niveau_risque,
                    "priorite": pred.priorite,
                    "ltv": pred.ltv_fcfa,
                    "action": pred.action_recommandee,
                })
            except Exception:
                continue

        # Trier par score décroissant
        predictions.sort(key=lambda x: x["score"], reverse=True)

        return {
            "nb_analyses": len(predictions),
            "urgents": [p for p in predictions if p["priorite"] == "urgent"],
            "standards": [p for p in predictions if p["priorite"] == "standard"],
            "tous": predictions,
        }

    def _score_deterministe(self, profil: dict) -> int:
        score = 0
        if profil["jours_retard_paiement"] > 60:
            score += 40
        elif profil["jours_retard_paiement"] > 30:
            score += 20
        if profil["jours_avant_echeance"] < 30:
            score += 20
        if profil["nb_sinistres_3ans"] >= 3:
            score += 15
        if profil["anciennete_jours"] < 365:
            score += 10
        return min(score, 85)

    def _niveau(self, score: int) -> str:
        if score < 30:
            return "stable"
        elif score < 60:
            return "modéré"
        elif score < 80:
            return "élevé"
        return "critique"

    def _facteurs(self, profil: dict) -> list[str]:
        facteurs = []
        if profil["jours_retard_paiement"] > 0:
            facteurs.append(f"Retard de paiement : {profil['jours_retard_paiement']} jours")
        if profil["jours_avant_echeance"] < 30:
            facteurs.append(f"Échéance dans {profil['jours_avant_echeance']} jours")
        if profil["nb_sinistres_3ans"] >= 3:
            facteurs.append(f"{profil['nb_sinistres_3ans']} sinistres en 3 ans")
        return facteurs or ["Aucun facteur critique identifié"]


# Singleton
churn_service = ChurnPredictionService()
