"""
YukpoAssurance — Réception & instruction des sinistres
Flux : déclaration → vérification contrat → pré-expertise IA → workflow instruction
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orass_connector import orass
from core.orchestrateur import ContexteRequete, DomaineMétier, orchestrateur
from modules.sinistres.fraude_detector import FraudeDetector

logger = logging.getLogger("yukpo_assurance.sinistres.reception")


@dataclass
class DeclarationSinistre:
    """Données d'une déclaration de sinistre"""
    numero_police: str
    date_sinistre: date
    heure_sinistre: Optional[str]
    lieu: str
    nature: str
    description: str
    nom_declarant: str
    telephone_declarant: str
    photos_b64: list[str] = field(default_factory=list)
    constat_b64: Optional[str] = None
    tiers_impliques: list[dict] = field(default_factory=list)
    blesses: bool = False
    canal: str = "app"  # "app" | "whatsapp" | "guichet" | "telephone"


@dataclass
class ResultatReception:
    numero_sinistre: str
    statut_contrat: dict
    pre_rapport_ia: dict
    score_fraude: dict
    complexite: str  # "simple" | "moyen" | "complexe"
    actions_immediates: list[str]
    expert_suggere: Optional[str]
    delai_reglementaire_jours: int
    message_client: str


class ReceptionSinistres:
    """
    Module de réception intelligente des sinistres.

    Étape 1 : Vérification contrat dans ORASS
    Étape 2 : Analyse photos par IA (estimation dégâts)
    Étape 3 : Score de fraude
    Étape 4 : Classification complexité
    Étape 5 : Création dans ORASS + notification parties
    """

    def __init__(self):
        self._fraude = FraudeDetector()

    async def traiter_declaration(
        self, declaration: DeclarationSinistre
    ) -> ResultatReception:
        logger.info(
            f"[Sinistres] Nouvelle déclaration — police {declaration.numero_police} "
            f"via {declaration.canal}"
        )

        # 1. Vérification validité du contrat
        statut_contrat = await orass.verifier_validite_contrat(declaration.numero_police)

        if not statut_contrat["valide"]:
            raise ValueError(
                f"Contrat {declaration.numero_police} non valide : {statut_contrat}"
            )

        # 2. Pré-expertise IA sur les photos
        pre_rapport = {}
        if declaration.photos_b64:
            pre_rapport = await self._pre_expertise_photos(declaration)

        # 3. Détection de fraude
        score_fraude = await self._fraude.analyser(
            declaration=declaration,
            historique_police=await orass.lister_sinistres_par_police(
                declaration.numero_police
            ),
            pre_rapport=pre_rapport,
        )

        # 4. Classification de la complexité
        complexite = self._classifier_complexite(declaration, pre_rapport, score_fraude)

        # 5. Création dans ORASS
        donnees_orass = {
            "numero_police": declaration.numero_police,
            "date_sinistre": declaration.date_sinistre.isoformat(),
            "heure": declaration.heure_sinistre,
            "lieu": declaration.lieu,
            "nature": declaration.nature,
            "description": declaration.description,
            "canal": declaration.canal,
            "complexite": complexite,
        }
        numero_sinistre = await orass.creer_sinistre(donnees_orass)

        # 6. Actions immédiates et expert
        actions = self._determiner_actions(complexite, score_fraude)
        expert = self._suggerer_expert(declaration.lieu, declaration.nature)

        # 7. Message client
        message = self._generer_message_client(
            numero_sinistre=numero_sinistre,
            complexite=complexite,
            declarant=declaration.nom_declarant,
        )

        from modules.cima.code_cima_engine import cima_engine
        delai = cima_engine.get_delai_reglementaire(declaration.nature)

        return ResultatReception(
            numero_sinistre=numero_sinistre,
            statut_contrat=statut_contrat,
            pre_rapport_ia=pre_rapport,
            score_fraude=score_fraude,
            complexite=complexite,
            actions_immediates=actions,
            expert_suggere=expert,
            delai_reglementaire_jours=delai["delai_jours"],
            message_client=message,
        )

    async def _pre_expertise_photos(self, declaration: DeclarationSinistre) -> dict:
        """Analyse IA des photos du sinistre"""
        prompt = f"""
Analyse ces photos de sinistre automobile et fournis un pré-rapport d'expertise.

Contexte :
- Nature du sinistre : {declaration.nature}
- Description déclarée : {declaration.description}
- Lieu : {declaration.lieu}
- Date : {declaration.date_sinistre}

Retourne UNIQUEMENT ce JSON :
{{
  "degats_visibles": ["liste des dommages observés"],
  "vehicules_impliques": [
    {{"immatriculation": "", "marque_estimee": "", "dommages": ""}}
  ],
  "estimation_cout_fcfa": 0,
  "fourchette_basse_fcfa": 0,
  "fourchette_haute_fcfa": 0,
  "coherence_avec_declaration": true,
  "anomalies_detectees": [],
  "expertise_physique_necessaire": true,
  "priorite": "urgente|normale|faible",
  "confiance": "haute|moyenne|faible",
  "observations": ""
}}
"""
        reponse = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            images_b64=declaration.photos_b64[:4],  # max 4 photos
            json_attendu=True,
        )
        return reponse.as_json()

    def _classifier_complexite(
        self, declaration: DeclarationSinistre, pre_rapport: dict, score_fraude: dict
    ) -> str:
        score = score_fraude.get("score_fraude", 0)
        estimation = pre_rapport.get("estimation_cout_fcfa", 0)
        blesses = declaration.blesses
        tiers = len(declaration.tiers_impliques)

        if blesses or score > 60 or estimation > 5_000_000 or tiers > 2:
            return "complexe"
        if score > 30 or estimation > 1_000_000 or tiers == 1:
            return "moyen"
        return "simple"

    def _determiner_actions(self, complexite: str, score_fraude: dict) -> list[str]:
        actions = []
        score = score_fraude.get("score_fraude", 0)

        if score > 70:
            actions.append("Escalader immédiatement au service anti-fraude")
            actions.append("Suspendre le paiement en attente d'investigation")
        elif score > 40:
            actions.append("Demander pièces complémentaires au déclarant")
            actions.append("Vérification approfondie des antécédents")

        if complexite == "complexe":
            actions.append("Désigner un expert agréé sous 48h")
            actions.append("Informer le service juridique si blessés")
        elif complexite == "moyen":
            actions.append("Planifier visite d'expertise sous 5 jours")
        else:
            actions.append("Traitement accéléré — règlement sous 48h possible")

        return actions

    def _suggerer_expert(self, lieu: str, nature: str) -> Optional[str]:
        """Suggestion simplifiée d'expert selon la zone géographique"""
        if "Yaoundé" in lieu or "Centre" in lieu:
            return "Cabinet EXPERTISE AUTO CENTRE — Tél: +237 222 XX XX XX"
        if "Douala" in lieu or "Littoral" in lieu:
            return "Cabinet EXPERTISE LITTORAL — Tél: +237 233 XX XX XX"
        return "Expert à désigner selon zone géographique"

    def _generer_message_client(
        self, numero_sinistre: str, complexite: str, declarant: str
    ) -> str:
        delais = {"simple": "48 heures", "moyen": "5 à 7 jours", "complexe": "10 à 15 jours"}
        return (
            f"Cher(e) {declarant},\n\n"
            f"Votre déclaration de sinistre a bien été enregistrée.\n"
            f"Numéro de dossier : {numero_sinistre}\n\n"
            f"Délai de traitement estimé : {delais.get(complexite, '7 jours')}\n\n"
            f"Notre équipe vous contactera prochainement pour la suite de votre dossier.\n"
            f"Pour tout renseignement : mentionnez votre numéro de dossier.\n\n"
            f"Cordialement,\nVotre compagnie d'assurance"
        )


# Instance singleton
reception_sinistres = ReceptionSinistres()
