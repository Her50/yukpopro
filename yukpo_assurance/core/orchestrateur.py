"""
YukpoAssurance — Orchestrateur central IA
Point d'entrée unique pour toutes les requêtes.
Inspiré de orchestration_ia.rs de yukpomnang2 : analyse contextuelle,
sélection de modèle, fallback chains, métriques, sécurité.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from core.ia_client import IAClient, ModeIA, ModelePrioritaire, ReponseIA, ia_client
from config.settings import settings

logger = logging.getLogger("yukpo_assurance.orchestrateur")


class DomaineMétier(str, Enum):
    CIMA = "cima"                     # Réglementation, états financiers
    SINISTRES = "sinistres"           # Déclaration, instruction, règlement
    COMPTABILITE = "comptabilite"     # Pièces, rapprochement, OHADA
    SOUSCRIPTION = "souscription"     # Devis, contrats, KYC
    COURTIERS = "courtiers"           # Portail, commissions, suivi
    COPILOTE = "copilote"             # Assistant quotidien généraliste
    OCR = "ocr"                       # Lecture de documents
    FRAUDE = "fraude"                 # Détection fraude sinistres


class NiveauComplexite(str, Enum):
    SIMPLE = "simple"         # Classification, extraction données
    MOYEN = "moyen"           # Analyse, rapport standard
    COMPLEXE = "complexe"     # Raisonnement multi-étapes, CIMA


@dataclass
class ContexteRequete:
    """Contexte enrichi de la requête — inspiré de ContextAnalysis dans orchestration_ia.rs"""
    domaine: DomaineMétier
    texte: str
    images_b64: list[str] = field(default_factory=list)
    documents_b64: list[str] = field(default_factory=list)
    excel_b64: list[str] = field(default_factory=list)
    user_id: Optional[int] = None
    role_utilisateur: str = "agent"  # "agent" | "manager" | "daf" | "dg" | "courtier"
    historique: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ResultatOrchestration:
    """Résultat enrichi de l'orchestration"""
    interaction_id: str
    reponse: str
    domaine: DomaineMétier
    modele_utilise: str
    complexite_detectee: NiveauComplexite
    temps_total_ms: float
    tokens_input: int
    tokens_output: int
    fallback_utilise: bool
    data_structuree: Optional[dict] = None  # JSON extrait si applicable
    actions_suggerees: list[str] = field(default_factory=list)
    niveau_confiance: float = 1.0


class Orchestrateur:
    """
    Orchestrateur central de YukpoAssurance.

    Pipeline d'une requête :
    1. Validation sécurité
    2. Détection du domaine et de la complexité
    3. Construction du prompt système enrichi (contexte métier assurance)
    4. Sélection du mode IA optimal
    5. Appel IA avec fallback
    6. Post-traitement et structuration de la réponse
    7. Collecte des métriques
    """

    def __init__(self, client: IAClient = ia_client):
        self._ia = client
        self._compteur_requetes = 0
        self._erreurs = 0

    # ──────────────────────────────────────────────────────────────
    # POINT D'ENTRÉE PRINCIPAL
    # ──────────────────────────────────────────────────────────────

    async def orchestrer(self, contexte: ContexteRequete) -> ResultatOrchestration:
        interaction_id = str(uuid.uuid4())
        debut = time.monotonic()
        self._compteur_requetes += 1

        logger.info(
            f"[Orchestrateur] #{self._compteur_requetes} "
            f"domaine={contexte.domaine.value} user={contexte.user_id}"
        )

        # 1. Validation sécurité
        if not self._valider_securite(contexte):
            raise ValueError("Contenu non conforme aux politiques de sécurité YukpoAssurance")

        # 2. Analyse contextuelle
        complexite = self._detecter_complexite(contexte)
        mode = self._selectionner_mode(contexte.domaine, complexite)
        modele_force = self._selectionner_modele_force(contexte.domaine, complexite)

        # 3. Construction du système prompt métier
        systeme = self._construire_systeme_prompt(contexte.domaine, contexte.role_utilisateur)

        # 4. Enrichissement du prompt avec contexte historique
        prompt_enrichi = self._enrichir_prompt(contexte)

        # 5. Collecte des médias
        images = list(contexte.images_b64) + list(contexte.documents_b64)

        # 6. Appel IA
        try:
            reponse: ReponseIA = await self._ia.appeler(
                prompt=prompt_enrichi,
                mode=mode,
                systeme=systeme,
                images_b64=images or None,
                json_attendu=self._json_attendu(contexte.domaine),
                max_tokens_override=self._max_tokens_domaine(contexte.domaine, contexte.texte),
                forcer_modele=modele_force,
            )
        except Exception as e:
            self._erreurs += 1
            logger.error(f"[Orchestrateur] Erreur IA: {e}")
            raise

        # 7. Post-traitement
        data_structuree = None
        actions = []
        if self._json_attendu(contexte.domaine):
            try:
                data_structuree = json.loads(reponse.contenu)
                actions = self._extraire_actions(data_structuree, contexte.domaine)
            except json.JSONDecodeError:
                pass

        duree_ms = (time.monotonic() - debut) * 1000
        logger.info(
            f"[Orchestrateur] #{interaction_id[:8]} terminé en {duree_ms:.0f}ms "
            f"modèle={reponse.modele_utilise}"
        )

        return ResultatOrchestration(
            interaction_id=interaction_id,
            reponse=reponse.contenu,
            domaine=contexte.domaine,
            modele_utilise=reponse.modele_utilise,
            complexite_detectee=complexite,
            temps_total_ms=duree_ms,
            tokens_input=reponse.tokens_input,
            tokens_output=reponse.tokens_output,
            fallback_utilise=reponse.fallback_utilise,
            data_structuree=data_structuree,
            actions_suggerees=actions,
        )

    # ──────────────────────────────────────────────────────────────
    # PROMPTS SYSTÈME PAR DOMAINE
    # ──────────────────────────────────────────────────────────────

    def _construire_systeme_prompt(
        self, domaine: DomaineMétier, role: str
    ) -> str:
        base = (
            "Tu es YukpoAssurance, l'IA spécialisée pour les compagnies d'assurance "
            "opérant en zone CIMA (Conférence Interafricaine des Marchés d'Assurances). "
            "Tu maîtrises parfaitement le Code CIMA, les normes OHADA, les systèmes "
            "ORASS et Mercure, et les pratiques du marché camerounais, ivoirien et sénégalais. "
            "Tu t'exprimes toujours en français professionnel, avec précision et clarté. "
            f"Tu parles à un(e) {self._libelle_role(role)}.\n\n"
        )

        domaine_prompts = {
            DomaineMétier.CIMA: (
                "DOMAINE : Réglementation CIMA\n"
                "Tu as une connaissance exhaustive du Code CIMA (14 livres) et de toutes ses circulaires. "
                "Pour chaque question réglementaire, tu cites l'article précis du Code CIMA. "
                "Tu génères des états financiers réglementés (C1 à C20) conformes aux exigences de la CRCA. "
                "Tu calcules les ratios prudentiels : marge de solvabilité, couverture des provisions, "
                "taux de réassurance, ratio de liquidité. Si un ratio est hors seuil, tu alertes immédiatement."
            ),
            DomaineMétier.SINISTRES: (
                "DOMAINE : Gestion des sinistres\n"
                "Tu guides l'instruction des dossiers sinistres de la déclaration au règlement. "
                "Tu détectes les signaux de fraude (incohérences dates, montants anormaux, récidivistes). "
                "Tu génères les pré-rapports d'expertise, les lettres de position et les avis de règlement. "
                "Tu connais les délais réglementaires CIMA : 30 jours pour les sinistres auto, "
                "3 mois pour les sinistres complexes (Article 12 Code CIMA)."
            ),
            DomaineMétier.COMPTABILITE: (
                "DOMAINE : Comptabilité & Finance\n"
                "Tu appliques le Plan Comptable Spécifique aux Assurances (PCSA) CIMA et les normes OHADA. "
                "Tu lis et extrais les données des factures, relevés bancaires et quittances de primes. "
                "Tu proposes les imputations comptables selon les règles métier assurance. "
                "Tu effectues le rapprochement bancaire et détectes les anomalies comptables."
            ),
            DomaineMétier.SOUSCRIPTION: (
                "DOMAINE : Souscription & Production\n"
                "Tu guides la souscription des contrats pour TOUTES les branches CIMA :\n"
                "NON-VIE :\n"
                "• Branche 10 — Automobile RC : RC obligatoire (Art. 200-251 CIMA), dommages tous risques, "
                "vol, incendie, bris de glace, défense-recours, catastrophes naturelles. "
                "Bonus-malus (CRM 0.50 à 3.50), usage personnel/professionnel/taxi/transport.\n"
                "• Branche 20 — Incendie & Risques Divers (IRD) : incendie, explosion, foudre, "
                "tempête-grêle-neige, dégâts des eaux, vol avec effraction, vandalisme, "
                "responsabilité civile exploitation, pertes d'exploitation après sinistre, "
                "bris de machines, bris de glaces, tous risques informatiques.\n"
                "• Branche 30 — RC Générale : RC produits livrés, RC exploitation, "
                "RC professionnelle (médecins, architectes, experts-comptables, avocats), "
                "RC construction (DO + TRC), RC employeur, RC vie privée.\n"
                "• Branche 40 — Accidents Corporels Individuels : décès accidentel (capital), "
                "invalidité permanente totale (IPT), invalidité permanente partielle (IPP), "
                "incapacité temporaire totale (ITT), frais médicaux/chirurgicaux/pharmaceutiques, "
                "frais funéraires, hospitalisation.\n"
                "• Branche 50 — Transport : corps de véhicules (flotte), RC transporteur, "
                "CMR (Conv. Marchandises Route, plafond 8,33 DTS/kg brut), "
                "marchandises tous risques / FAP sauf, transport maritime corps & facultés, "
                "fret aérien, transport fluvial et lagunaire.\n"
                "• Branche 60 — Aviation : corps d'aéronef, RC aéronautique passagers & tiers, "
                "annulation vol, bagages, RC aéroport.\n"
                "• MRH (Multirisque Habitation) : incendie + vol + RC locataire/propriétaire + "
                "dégâts des eaux + catnat + bris de glace + objets de valeur + "
                "électroménager + perte de loyers. Zones catnat CIMA (Circ. 2024-001).\n"
                "VIE :\n"
                "• Capital-décès toutes causes (temporaire décès, vie entière).\n"
                "• Vie mixte : épargne + décès (versement capital à terme ou au décès).\n"
                "• Rente viagère : immédiate ou différée, avec/sans annuités garanties.\n"
                "• Épargne-capitalisation : bon de capitalisation, PEP, épargne retraite.\n"
                "• Prévoyance individuelle : invalidité absolue et définitive (IAD), "
                "arrêt de travail longue durée, exonération de primes.\n"
                "• Prévoyance collective (groupe) : décès-invalidité, frais médicaux groupe, "
                "IJ journalière, maternité, hospitalisation.\n"
                "• Maladie / Santé (Branche 80) : frais médicaux ambulatoires, hospitalisation, "
                "maternité, optique, dentaire, évacuation sanitaire, assistance rapatriement.\n"
                "• Assurance crédit-vie : solde restant dû en cas de décès/invalidité emprunteur.\n"
                "• Accidents de travail / Maladies professionnelles (régime complémentaire).\n\n"
                "Pour chaque branche tu cites l'article CIMA applicable, les exclusions légales, "
                "les plafonds réglementaires, et tu vérifies la complétude KYC (CNI, carte grise, etc.)."
            ),
            DomaineMétier.COURTIERS: (
                "DOMAINE : Courtiers & Intermédiaires\n"
                "Tu accompagnes les courtiers dans leur activité quotidienne. "
                "Tu calcules les commissions selon les barèmes en vigueur et les accords avec la compagnie. "
                "Tu fournis un suivi en temps réel des dossiers soumis et des encaissements. "
                "Tu génères les états de commissions et les attestations de courtage."
            ),
            DomaineMétier.OCR: (
                "DOMAINE : Lecture de documents\n"
                "Tu lis et extrais les données structurées des documents d'assurance : "
                "factures de garage, factures d'hôpital, constats amiables, CNI, cartes grises, "
                "fiches de souscription, quittances de primes. "
                "Tu retournes UNIQUEMENT du JSON valide et structuré. "
                "Tu signales les anomalies et incohérences détectées. "
                "Tu évalues ton niveau de confiance : haute / moyenne / faible."
            ),
            DomaineMétier.FRAUDE: (
                "DOMAINE : Détection de fraude\n"
                "Tu analyses les dossiers sinistres pour détecter les signaux de fraude. "
                "Indicateurs que tu surveilles : dates incohérentes, garages non référencés, "
                "montants inhabituels, assuré multi-réclamant, photos manipulées, "
                "déclarations contradictoires, timing suspect post-souscription. "
                "Tu fournis un score de risque de fraude (0-100) et une liste d'indicateurs détectés."
            ),
            DomaineMétier.COPILOTE: (
                "DOMAINE : Copilote assurance CIMA — Assistant omniscient\n"
                "Tu es l'assistant quotidien des équipes de compagnies d'assurance en zone CIMA. "
                "Tu réponds à TOUTE question métier avec précision et exemples concrets.\n\n"
                "GARANTIES NON-VIE que tu maîtrises parfaitement :\n"
                "Auto (B10) : RC obligatoire, dommages TR, vol, incendie, bris de glace, "
                "défense-recours, assistance panne/accident, bonus-malus CRM.\n"
                "Incendie/IRD (B20) : incendie, explosion, foudre, tempête, grêle, neige, "
                "dégâts des eaux, vol avec effraction, vandalisme, bris de machines, "
                "pertes d'exploitation, bris de glaces, risques informatiques.\n"
                "RC Générale (B30) : RC exploitation, RC produits livrés, RC après livraison, "
                "RC professionnelle médicale (faute médicale), RC architectes et BTP (DO+TRC), "
                "RC employeur, RC vie privée, RC locataire.\n"
                "Accidents Corporels (B40) : décès accidentel (capital), IPT, IPP par barème, "
                "ITT (indemnité journalière), frais médicaux, chirurgicaux, pharmaceutiques, "
                "hospitalisation, frais funéraires (plafond CIMA Art. 258).\n"
                "Transport (B50) : corps flotte, RC transporteur terrestre, CMR (8,33 DTS/kg), "
                "marchandises tous risques et FAP sauf, fret maritime et aérien.\n"
                "Aviation (B60) : corps aéronef, RC passagers, RC tiers au sol, bagages.\n"
                "MRH : incendie + vol + RC + dégâts des eaux + catnat + bris de glace + "
                "objets de valeur + électroménager + perte de loyers.\n\n"
                "GARANTIES VIE que tu maîtrises :\n"
                "Capital-décès toutes causes, Temporaire décès, Vie entière, Vie mixte, "
                "Rente viagère immédiate/différée, Épargne-capitalisation, Crédit-vie, "
                "IAD (Invalidité Absolue Définitive), Prévoyance individuelle et collective, "
                "Frais médicaux groupe, IJ, Maternité, Hospitalisation, Évacuation sanitaire.\n\n"
                "CALCULS que tu sais faire : prime nette, prime TTC, PSAP (3 méthodes), "
                "PPNA (prorata/quart/huitième), PM Vie (prospective, tables CIMA-2016), "
                "PRC, marge solvabilité, ratio S/P, coefficient CRM, règle proportionnelle, "
                "franchise absolue/relative, valeur vénale vs valeur de remplacement.\n\n"
                "Tu proposes toujours : 1) la réponse directe, 2) l'article CIMA applicable, "
                "3) un exemple concret, 4) les pièges à éviter."
            ),
        }

        return base + domaine_prompts.get(domaine, domaine_prompts[DomaineMétier.COPILOTE])

    # ──────────────────────────────────────────────────────────────
    # LOGIQUE INTERNE
    # ──────────────────────────────────────────────────────────────

    def _detecter_complexite(self, contexte: ContexteRequete) -> NiveauComplexite:
        texte = contexte.texte.lower()
        if contexte.domaine in (DomaineMétier.CIMA, DomaineMétier.FRAUDE):
            return NiveauComplexite.COMPLEXE
        if any(mot in texte for mot in ["calcule", "ratio", "état", "rapport", "analyser"]):
            return NiveauComplexite.MOYEN
        if contexte.images_b64 or contexte.documents_b64:
            return NiveauComplexite.MOYEN
        return NiveauComplexite.SIMPLE

    def _selectionner_mode(
        self, domaine: DomaineMétier, complexite: NiveauComplexite
    ) -> ModeIA:
        if domaine == DomaineMétier.CIMA:
            return ModeIA.PRECISION
        if domaine in (DomaineMétier.FRAUDE, DomaineMétier.SINISTRES):
            return ModeIA.ANALYSE
        if domaine in (DomaineMétier.COMPTABILITE, DomaineMétier.SOUSCRIPTION):
            return ModeIA.ANALYSE
        if domaine == DomaineMétier.OCR:
            return ModeIA.PRECISION
        if complexite == NiveauComplexite.SIMPLE:
            return ModeIA.COPILOTE
        return ModeIA.REDACTION

    def _selectionner_modele_force(
        self, domaine: DomaineMétier, complexite: NiveauComplexite,
    ) -> Optional[ModelePrioritaire]:
        """
        Force la variante LLM selon le domaine + la complexité.
        Avant : tout passait par le mode → Sonnet par défaut sur tâches REDACTION/ANALYSE.
        Après : domaines régulateurs (CIMA, FRAUDE) en complexité COMPLEXE forcent Opus 4.7
        (raisonnement haut de gamme, fallback gpt-4-turbo). OCR reste sur défaut (vision
        gérée par GPT-4o ailleurs). Domaines simples gardent défaut (économie tokens).
        """
        if complexite == NiveauComplexite.COMPLEXE and domaine in (
            DomaineMétier.CIMA,
            DomaineMétier.FRAUDE,
        ):
            return ModelePrioritaire.CLAUDE_OPUS
        # Sinistres complexes (multi-pièces, fraude potentielle) : Opus aussi
        if complexite == NiveauComplexite.COMPLEXE and domaine == DomaineMétier.SINISTRES:
            return ModelePrioritaire.CLAUDE_OPUS
        return None

    def _enrichir_prompt(self, contexte: ContexteRequete) -> str:
        prompt = contexte.texte
        if contexte.historique:
            # 8 derniers tours (vs 4 précédemment) pour contexte plus riche
            historique_str = "\n".join(
                f"[{h['role'].upper()}]: {h['contenu'][:500]}"  # cap 500 chars/tour
                for h in contexte.historique[-8:]
            )
            prompt = f"HISTORIQUE DE LA CONVERSATION:\n{historique_str}\n\nNOUVELLE QUESTION:\n{prompt}"
        return prompt

    def _json_attendu(self, domaine: DomaineMétier) -> bool:
        return domaine in (DomaineMétier.OCR, DomaineMétier.FRAUDE)

    def _valider_securite(self, contexte: ContexteRequete) -> bool:
        """
        Validation de sécurité robuste utilisant le module security.
        Couvre unicode, base64, variantes, et patterns connus de jailbreak.
        """
        from core.security import security_service
        valide, raison = security_service.valider_prompt(
            contexte.texte, user_id=contexte.user_id
        )
        if not valide:
            logger.warning(
                f"[Orchestrateur] Prompt rejeté user={contexte.user_id}: {raison}"
            )
        return valide

    def _extraire_actions(self, data: dict, domaine: DomaineMétier) -> list[str]:
        """Actions suggérées pour TOUS les domaines (vs 2 seulement précédemment)."""
        actions = []

        if domaine == DomaineMétier.FRAUDE:
            score = data.get("score_fraude", 0)
            if score > 70:
                actions.append("Escalader immédiatement au service anti-fraude")
                actions.append("Suspendre le règlement en attente d'investigation")
                actions.append("Notifier le responsable de département")
            elif score > 40:
                actions.append("Demander pièces complémentaires au déclarant")
                actions.append("Vérification approfondie des antécédents")
            else:
                actions.append("Traitement normal — vigilance standard")

        elif domaine == DomaineMétier.OCR:
            confiance = data.get("confiance", "haute")
            if confiance == "faible":
                actions.append("Vérification manuelle requise — OCR peu fiable")
                actions.append("Resoumettre l'image avec meilleure qualité")
            elif confiance == "moyenne":
                actions.append("Valider les montants avant enregistrement ORASS")
            anomalies = data.get("anomalies", [])
            if anomalies:
                actions.append(f"Anomalies détectées : {', '.join(anomalies[:3])}")

        elif domaine == DomaineMétier.CIMA:
            alerte = data.get("alerte") or ""
            if "CRITIQUE" in alerte.upper():
                actions.append("Action immédiate requise — contacter la CRCA")
                actions.append("Préparer un plan de régularisation")
            elif alerte:
                actions.append("Analyser la situation avec le service actuariat")

        elif domaine == DomaineMétier.SINISTRES:
            complexite = data.get("complexite", "simple")
            if complexite == "complexe":
                actions.append("Désigner un expert agréé sous 48h")
                actions.append("Informer le service juridique")
            elif complexite == "moyen":
                actions.append("Planifier visite d'expertise sous 5 jours")
            else:
                actions.append("Traitement accéléré — règlement sous 48h possible")

        elif domaine == DomaineMétier.SOUSCRIPTION:
            pieces_manquantes = data.get("pieces_manquantes", [])
            if pieces_manquantes:
                actions.append(f"Demander : {', '.join(pieces_manquantes[:3])}")
            else:
                actions.append("Dossier complet — émettre le contrat")

        elif domaine == DomaineMétier.COMPTABILITE:
            validation = data.get("validation_requise", False)
            if validation:
                actions.append("Validation manuelle requise avant enregistrement")
            else:
                actions.append("Enregistrement automatique possible dans ORASS")

        elif domaine == DomaineMétier.COURTIERS:
            actions.append("Confirmer les données avec le courtier")
            actions.append("Émettre l'état de commissions")

        elif domaine == DomaineMétier.COPILOTE:
            actions.append("Consulter les documents associés si nécessaire")

        return actions

    def _max_tokens_domaine(self, domaine: DomaineMétier, texte: str) -> Optional[int]:
        """
        Retourne `max_tokens_override` selon le domaine et la complexité détectée.
        - Domaines longs (CIMA, états financiers, rapports) → IA_MAX_TOKENS_DOCUMENT (32768)
        - Domaines standards → None (utilise IA_MAX_TOKENS = 16384 par défaut)
        - OCR, fraude simple → 4096 suffisant (économie de coût)
        """
        texte_lower = texte.lower()

        # Détection de demandes de rapports très longs
        mots_rapport_long = ["c1", "c2", "c3", "c4", "c5", "état financier", "rapport annuel",
                              "bilan", "compte de résultat", "toutes les provisions", "c1 à c20",
                              "rapport complet", "plan de réassurance", "c20"]
        if domaine == DomaineMétier.CIMA and any(m in texte_lower for m in mots_rapport_long):
            return settings.IA_MAX_TOKENS_DOCUMENT  # 32768

        # Domaines à réponse naturellement longue
        if domaine in (DomaineMétier.CIMA,):
            return settings.IA_MAX_TOKENS  # 16384

        # OCR et fraude : réponse JSON compacte
        if domaine in (DomaineMétier.OCR, DomaineMétier.FRAUDE):
            return 4096

        return None  # Utilise IA_MAX_TOKENS par défaut

    def _libelle_role(self, role: str) -> str:
        libelles = {
            "agent": "agent de production / gestionnaire",
            "manager": "manager / chef de département",
            "daf": "Directeur Administratif et Financier",
            "dg": "Directeur Général",
            "courtier": "courtier / intermédiaire d'assurance",
        }
        return libelles.get(role, "professionnel de l'assurance")

    def statistiques(self) -> dict:
        return {
            "total_requetes": self._compteur_requetes,
            "erreurs": self._erreurs,
            "taux_erreur": f"{self._erreurs / max(self._compteur_requetes, 1):.1%}",
            "metriques_modeles": self._ia.rapport_metriques(),
        }


# Instance singleton
orchestrateur = Orchestrateur()
