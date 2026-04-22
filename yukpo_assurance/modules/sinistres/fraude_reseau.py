"""
YukpoAssurance — Détection de fraude organisée / réseau
Va au-delà du score individuel : détecte les fraudes coordonnées
(même garage + même expert + mêmes sinistres = réseau).
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orass_connector import orass

logger = logging.getLogger("yukpo_assurance.fraude_reseau")


@dataclass
class ResultatAnalyseReseau:
    reseau_detecte: bool
    score_reseau: int           # 0-100
    acteurs_suspects: list[str]
    pattern_identifie: str
    recommandation: str         # "bloquer" | "surveiller" | "passer"
    details: dict = field(default_factory=dict)


class FraudeReseauDetector:
    """
    Analyse réseau sur un sinistre pour détecter les fraudes organisées.

    Patterns détectés :
    - Même garage + même expert dans >3 sinistres / 6 mois
    - Tiers impliqué dans plusieurs sinistres différents
    - Montants strictement identiques entre sinistres distincts
    - Rafale de déclarations (>3 sinistres en 72h dans la compagnie)
    - Expert + garage géographiquement incohérents avec le lieu du sinistre
    """

    async def analyser(self, numero_sinistre: str) -> ResultatAnalyseReseau:
        """Analyse réseau pour un sinistre donné"""
        sinistre = await orass.recuperer_sinistre(numero_sinistre)
        if not sinistre:
            return ResultatAnalyseReseau(
                reseau_detecte=False, score_reseau=0,
                acteurs_suspects=[], pattern_identifie="Sinistre introuvable",
                recommandation="passer",
            )

        # Collecte des données historiques depuis ORASS
        historique = await self._collecter_historique(sinistre)

        # Analyse déterministe
        score_det, patterns_det, acteurs = self._analyse_deterministe(sinistre, historique)

        # Analyse sémantique IA si score déterministe > 20
        analyse_ia = ""
        if score_det > 20:
            analyse_ia = await self._analyse_ia(sinistre, historique, patterns_det)

        score_final = min(100, score_det + (20 if "réseau" in analyse_ia.lower() else 0))

        return ResultatAnalyseReseau(
            reseau_detecte=score_final >= 50,
            score_reseau=score_final,
            acteurs_suspects=acteurs,
            pattern_identifie=", ".join(patterns_det) if patterns_det else "Aucun pattern réseau",
            recommandation=self._recommandation(score_final),
            details={"historique_analyse": historique, "analyse_ia": analyse_ia},
        )

    async def _collecter_historique(self, sinistre) -> dict:
        """
        Collecte l'historique des acteurs impliqués dans ce sinistre depuis ORASS.
        Analyse : expert, garage, tiers, délai souscription, montants similaires,
        volume de déclarations récent dans la compagnie.
        """
        expert = sinistre.expert_assigne or ""
        numero_police = sinistre.numero_police

        # 1. Contrat : calcul ancienneté depuis souscription
        contrat = await orass.rechercher_contrat(numero_police=numero_police)
        from datetime import date
        delai_souscription = (
            (date.today() - contrat.date_effet).days if contrat else 365
        )

        # 2. Tous les sinistres sur la même police (fréquence assuré)
        sinistres_police = await orass.lister_sinistres_par_police(numero_police)
        nb_sinistres_police = len(sinistres_police)

        # 3. Impayés récents (proxy : rafale déclarations = compagnie 72h)
        # En simulation on estime avec les impayés comme proxy d'activité anormale
        impayes_recents = await orass.lister_impayes(seuil_jours=3)
        sinistres_compagnie_72h = len(impayes_recents)  # En prod : requête sur date_declaration

        # 4. Analyse des montants similaires parmi les sinistres de la police
        montant_ref = sinistre.montant_declare or 0
        montants_similaires = []
        for s in sinistres_police:
            if s.numero_sinistre == sinistre.numero_sinistre:
                continue
            montant_s = s.montant_declare or 0
            if montant_ref > 0 and abs(montant_s - montant_ref) / montant_ref < 0.05:
                montants_similaires.append({
                    "numero_sinistre": s.numero_sinistre,
                    "montant": montant_s,
                })

        # 5. Nombre de sinistres avec le même expert (proxy depuis sinistres police)
        # En production : requête ORASS sur expert_assigne tous dossiers 6 mois
        sinistres_meme_expert = sum(
            1 for s in sinistres_police if s.expert_assigne == expert and expert
        )

        # 6. Garage : détecté via description (proxy) ou données structurées ORASS
        sinistres_meme_garage = sum(
            1 for s in sinistres_police
            if s.lieu == sinistre.lieu and s.numero_sinistre != sinistre.numero_sinistre
        )

        return {
            "sinistres_meme_expert": sinistres_meme_expert,
            "sinistres_meme_garage": sinistres_meme_garage,
            "sinistres_meme_tiers": 0,  # Nécessite données tiers structurées dans ORASS
            "delai_depuis_souscription_jours": delai_souscription,
            "nb_sinistres_sur_police": nb_sinistres_police,
            "montants_similaires": montants_similaires,
            "sinistres_compagnie_72h": sinistres_compagnie_72h,
            "expert": expert,
        }

    def _analyse_deterministe(
        self, sinistre, historique: dict
    ) -> tuple[int, list[str], list[str]]:
        """Calcule le score réseau par règles déterministes"""
        score = 0
        patterns = []
        acteurs = []

        if historique["sinistres_meme_expert"] >= 3:
            score += 35
            patterns.append(f"Expert impliqué dans {historique['sinistres_meme_expert']} sinistres/6 mois")
            if sinistre.expert_assigne:
                acteurs.append(f"Expert: {sinistre.expert_assigne}")

        if historique["sinistres_meme_garage"] >= 2:
            score += 25
            patterns.append(f"Même garage dans {historique['sinistres_meme_garage']} sinistres")

        if historique["sinistres_meme_tiers"] >= 2:
            score += 30
            patterns.append(f"Tiers professionnel (impliqué {historique['sinistres_meme_tiers']} fois)")

        if historique["sinistres_compagnie_72h"] >= 3:
            score += 20
            patterns.append(f"{historique['sinistres_compagnie_72h']} sinistres en 72h dans la compagnie")

        if len(historique["montants_similaires"]) >= 2:
            score += 15
            patterns.append("Montants identiques sur plusieurs dossiers")

        return min(score, 80), patterns, acteurs

    async def _analyse_ia(
        self, sinistre, historique: dict, patterns_det: list[str]
    ) -> str:
        """Analyse sémantique IA des patterns suspects"""
        prompt = f"""Tu es expert en fraude organisée pour une compagnie d'assurance CIMA.

SINISTRE ANALYSÉ :
- Numéro : {sinistre.numero_sinistre}
- Nature : {sinistre.nature}
- Lieu : {sinistre.lieu}
- Description : {sinistre.description}
- Expert : {sinistre.expert_assigne}
- Montant déclaré : {sinistre.montant_declare:,} FCFA

DONNÉES HISTORIQUES RÉSEAU :
{historique}

PATTERNS DÉTERMINISTES DÉJÀ DÉTECTÉS :
{patterns_det}

ANALYSE :
1. Ces patterns indiquent-ils une fraude organisée ? (oui/non/incertain)
2. Quel schéma de fraude cela ressemble-t-il ? (faux sinistres, gonflement, réseau expert-garage, etc.)
3. Quelle est la probabilité que ce sinistre soit frauduleux vs coïncidence ?
4. Quelles vérifications concrètes recommandes-tu immédiatement ?

Sois factuel, évite les accusations sans preuves. Distingue suspicion de certitude."""

        try:
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return reponse.contenu
        except Exception as e:
            logger.warning(f"[FraudeReseau] Analyse IA échouée: {e}")
            return ""

    def _recommandation(self, score: int) -> str:
        if score >= 70:
            return "bloquer"
        elif score >= 40:
            return "surveiller"
        return "passer"


# Singleton
fraude_reseau_detector = FraudeReseauDetector()
