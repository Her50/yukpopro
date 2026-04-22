"""
YukpoAssurance — Copilote assistant quotidien
Couvre TOUTES les garanties d'assurance vie et non-vie zone CIMA.
Le cœur de l'expérience utilisateur : réponses métier instantanées,
rédaction assistée, veille réglementaire, support décisionnel.
Plus performant que Copilot car entièrement orienté assurance CIMA.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orchestrateur import ContexteRequete, DomaineMétier, orchestrateur
from modules.cima.code_cima_engine import cima_engine

logger = logging.getLogger("yukpo_assurance.copilote")


# ─── Base de connaissances garanties CIMA complète ────────────────────────────
# Référence exhaustive pour toutes les branches et garanties en zone CIMA.
# Utilisée par expliquer_garantie() et comme contexte enrichi dans les prompts.

GARANTIES_CIMA: dict[str, dict] = {
    # ── BRANCHE 10 — AUTOMOBILE ───────────────────────────────────────────────
    "B10_RC_obligatoire": {
        "branche": "10 — Automobile",
        "nom": "Responsabilité Civile Automobile (obligatoire)",
        "base_legale": "Art. 200-251 Code CIMA — Livre II Assurances Obligatoires",
        "objet": "Couvre les dommages corporels et matériels causés aux tiers lors d'un accident de circulation.",
        "garanties": ["Dommages corporels tiers (décès, invalidité, frais médicaux)", "Dommages matériels tiers", "Défense pénale", "Recours des tiers"],
        "exclusions": ["Faute intentionnelle de l'assuré", "Conduite sous ivresse", "Véhicule non déclaré ou modifié", "Usage hors conditions du contrat"],
        "plafonds": {"corporel": "Illimité (Art. 215 CIMA)", "materiel": "25 000 000 XAF (plancher réglementaire)"},
        "delais": {"declaration": "5 jours ouvrés (Art. 12 CIMA)", "reglement": "30 jours après accord parties"},
        "pièces_requises": ["Déclaration sinistre", "Constat amiable ou PV police", "Photos des dégâts", "CNI conducteur", "Permis de conduire", "Carte grise"],
        "particularite": "Seule assurance automobile obligatoire en zone CIMA. Tiers lésé a action directe contre assureur (Art. 7 CIMA).",
    },
    "B10_dommages_corps": {
        "branche": "10 — Automobile",
        "nom": "Dommages Tous Risques / Corps de Véhicule",
        "base_legale": "Art. 30-33 Code CIMA + conditions particulières",
        "objet": "Indemnise les dommages subis par le véhicule assuré, quelle que soit la responsabilité.",
        "garanties": ["Collision toutes causes", "Accident sans tiers identifié", "Tentative de vol", "Catastrophe naturelle", "Attentat"],
        "exclusions": ["Usure normale et vétusté", "Panne mécanique sans sinistre", "Faute intentionnelle", "Conduite sans permis"],
        "plafonds": {"vehicule": "Valeur vénale ou valeur de remplacement selon contrat"},
        "regles": ["Règle proportionnelle si sous-assurance (Art. 31 CIMA)", "Vétusté déduite selon barème", "Franchise contractuelle appliquée"],
        "bonus_malus": "CRM de 0,50 (bonus max après 13 ans sans sinistre) à 3,50 (malus max)",
    },
    "B10_vol_incendie": {
        "branche": "10 — Automobile",
        "nom": "Vol et Incendie",
        "objet": "Garantit le véhicule contre le vol total, les tentatives de vol avec dommages, l'incendie et la foudre.",
        "garanties": ["Vol total", "Vol partiel avec dommages", "Incendie", "Foudre directe", "Explosion"],
        "exclusions": ["Vol par un assuré ou membre de la famille vivant au foyer", "Oubli ou imprudence grossière", "Incendie suite à mauvais entretien mécanique"],
        "plafonds": {"vehicule": "Valeur vénale au jour du sinistre"},
    },
    "B10_bris_glace": {
        "branche": "10 — Automobile",
        "nom": "Bris de Glace",
        "objet": "Couvre le remplacement ou la réparation des vitrages du véhicule.",
        "garanties": ["Pare-brise", "Vitres latérales", "Lunette arrière", "Toit ouvrant vitré", "Optiques (si stipulé)"],
        "exclusions": ["Rayures sans bris", "Carrosserie et phares non vitrés"],
        "plafonds": {"bris_glace": "Généralement 500 000 XAF plafond"},
    },

    # ── BRANCHE 20 — INCENDIE & RISQUES DIVERS (IRD) ─────────────────────────
    "B20_incendie": {
        "branche": "20 — Incendie & Risques Divers",
        "nom": "Incendie — Garantie de Base",
        "base_legale": "Art. 30-35 Code CIMA + circulaires techniques CIMA IRD",
        "objet": "Couvre les dommages causés par l'incendie, l'explosion, la foudre et leurs conséquences.",
        "garanties": ["Incendie accidentel", "Explosion", "Foudre directe et indirecte", "Dommages imputables aux secours", "Dommages aux immeubles et biens mobiliers"],
        "exclusions": ["Incendie allumé volontairement par l'assuré", "Dommages de fermentation/autocombustion non signalés", "Guerre civile"],
        "plafonds": {"bien_immobilier": "Valeur de reconstruction à neuf ou vénale", "mobilier": "Valeur au moment du sinistre"},
        "regles": ["Valeur déclarée = valeur assurée → règle proportionnelle si sous-assurance", "Vétusté selon barème technique"],
    },
    "B20_degats_eaux": {
        "branche": "20 — Incendie & Risques Divers",
        "nom": "Dégâts des Eaux",
        "objet": "Indemnise les dommages causés par la rupture ou le débordement de canalisations, infiltrations, etc.",
        "garanties": ["Rupture de canalisations fixes", "Débordement d'appareils", "Infiltrations par toitures défectueuses", "Inondations internes", "Dommages causés aux tiers"],
        "exclusions": ["Dégâts dûs à un défaut d'entretien notoire", "Infiltrations par fondations", "Humidité diffuse sans rupture"],
    },
    "B20_vol": {
        "branche": "20 — Incendie & Risques Divers",
        "nom": "Vol avec Effraction",
        "objet": "Garantit les pertes et dommages consécutifs à un vol ou tentative de vol avec effraction.",
        "garanties": ["Vol de marchandises et stocks", "Vol de matériel et mobilier", "Dommages d'effraction (portes, fenêtres)", "Agression sur personnel"],
        "exclusions": ["Vol commis par le personnel ou complice", "Vol sans traces d'effraction", "Valeurs (espèces > seuil contractuel)"],
        "plafonds": {"valeurs": "Espèces limitées à 5% de la somme assurée en général"},
    },
    "B20_perte_exploitation": {
        "branche": "20 — Incendie & Risques Divers",
        "nom": "Pertes d'Exploitation",
        "objet": "Compense la perte de marge brute consécutive à un sinistre garanti (incendie, explosion, etc.).",
        "garanties": ["Perte de marge brute", "Frais supplémentaires d'exploitation", "Salaires du personnel maintenu"],
        "periode_indemnisation": "Généralement 12 à 36 mois selon contrat",
        "formule": "Indemnité = (Marge brute annuelle × Taux réduction CA) × Durée d'interruption",
    },
    "B20_bris_machines": {
        "branche": "20 — Incendie & Risques Divers",
        "nom": "Bris de Machines",
        "objet": "Couvre les dommages matériels aux machines et équipements dus à des causes accidentelles soudaines.",
        "garanties": ["Court-circuit et surtension", "Erreur de manœuvre", "Corps étrangers", "Rupture mécanique", "Explosion interne"],
        "exclusions": ["Usure, rouille, corrosion progressive", "Dommages esthétiques sans atteinte fonctionnelle"],
    },
    "B20_RC_exploitation": {
        "branche": "20 — Incendie & Risques Divers / RC Générale",
        "nom": "Responsabilité Civile Exploitation",
        "objet": "Couvre les dommages causés aux tiers dans le cadre de l'activité professionnelle de l'assuré.",
        "garanties": ["Dommages corporels, matériels et immatériels", "Accidents sur site", "Dommages causés par le personnel"],
        "exclusions": ["RC produits après livraison (garantie séparée)", "Dommages intentionnels", "Amendes et pénalités"],
    },

    # ── BRANCHE 30 — RC GÉNÉRALE ──────────────────────────────────────────────
    "B30_RC_professionnelle": {
        "branche": "30 — RC Générale",
        "nom": "Responsabilité Civile Professionnelle",
        "objet": "Couvre les dommages causés aux clients et tiers dans l'exercice d'une profession réglementée.",
        "sous_branches": {
            "RC_medicale": "Erreur médicale, faute de diagnostic, complication opératoire (médecins, cliniques)",
            "RC_architecte": "Vices de construction, défauts de conformité (architectes, maîtres d'œuvre)",
            "RC_expert_comptable": "Erreur comptable, omission fiscale (experts-comptables, commissaires aux comptes)",
            "RC_avocat": "Erreur procédurale, rédaction défectueuse d'actes",
        },
        "garanties": ["Dommages corporels, matériels, immatériels consécutifs", "Frais de défense", "Dommages immatériels purs (selon extension)"],
        "exclusions": ["Faute intentionnelle ou dolosive", "Amendes et pénalités", "Dommages liés à une activité non déclarée"],
    },
    "B30_RC_construction": {
        "branche": "30 — RC Générale / Construction",
        "nom": "Tous Risques Chantier (TRC) + Dommages-Ouvrage (DO)",
        "objet": "TRC couvre les dommages matériels pendant le chantier. DO garantit la réparation des malfaçons 10 ans après réception.",
        "garanties": ["TRC: incendie, vol, tempête, accidents sur chantier", "DO: vices cachés, malfaçons structurelles, effondrement"],
        "base_legale": "Garantie décennale Art. 1792 applicable dans les pays CIMA",
    },
    "B30_RC_produits": {
        "branche": "30 — RC Générale",
        "nom": "Responsabilité Civile Produits Livrés",
        "objet": "Couvre les dommages causés par un produit après sa livraison ou mise sur le marché.",
        "garanties": ["Dommages corporels et matériels causés par défaut du produit", "Frais de rappel (extension)"],
        "exclusions": ["Dommages au produit lui-même", "Dommages intentionnels", "Produits pharmaceutiques (régime spécial)"],
    },

    # ── BRANCHE 40 — ACCIDENTS CORPORELS ─────────────────────────────────────
    "B40_deces_accidentel": {
        "branche": "40 — Accidents Corporels",
        "nom": "Décès Accidentel",
        "base_legale": "Art. 50-98 Code CIMA + barèmes CIMA Art. 258",
        "objet": "Verse un capital au(x) bénéficiaire(s) en cas de décès de l'assuré suite à un accident.",
        "garanties": ["Capital décès accidentel", "Capital décès toutes causes (si étendu)", "Frais funéraires dans la limite du capital"],
        "exclusions": ["Suicide (sauf après 2 ans d'assurance-vie)", "Accidents lors de sports dangereux non déclarés", "Guerre"],
        "baremes": "Capital librement convenu ou selon barème employeur",
    },
    "B40_invalidite": {
        "branche": "40 — Accidents Corporels",
        "nom": "Invalidité Permanente (IPT/IPP)",
        "objet": "Verse un capital ou une rente proportionnels au taux d'invalidité suite à un accident.",
        "sous_garanties": {
            "IPT": "Invalidité Permanente Totale (taux ≥ 66%) — capital 100%",
            "IPP": "Invalidité Permanente Partielle — capital proratisé selon barème",
        },
        "baremes_cima": {
            "perte_main_dominante": "60%",
            "perte_œil": "25%",
            "perte_bras": "65%",
            "perte_jambe": "55%",
            "perte_ouïe_totale": "35%",
        },
        "calcul": "Indemnité IPP = Capital × Taux IPP (selon barème Art. 258 CIMA)",
    },
    "B40_ITT": {
        "branche": "40 — Accidents Corporels",
        "nom": "Incapacité Temporaire Totale (ITT)",
        "objet": "Verse une indemnité journalière pendant la période d'arrêt de travail suite à accident.",
        "garanties": ["Indemnité journalière dès le 1er jour ou après franchise (3/8/15 jours)"],
        "calcul": "IJ × Nombre jours ITT (plafonné à la durée maximale contractuelle, généralement 365/730 jours)",
    },
    "B40_frais_medicaux": {
        "branche": "40 — Accidents Corporels",
        "nom": "Frais Médicaux Accident",
        "objet": "Rembourse les frais médicaux engagés suite à un accident corporel.",
        "garanties": ["Honoraires médicaux", "Frais chirurgicaux", "Hospitalisation", "Médicaments", "Prothèses", "Rééducation"],
        "plafonds": "Fixés aux conditions particulières (ex: 500 000 à 5 000 000 XAF)",
    },

    # ── BRANCHE 50 — TRANSPORT ────────────────────────────────────────────────
    "B50_CMR": {
        "branche": "50 — Transport",
        "nom": "Responsabilité Civile Transporteur CMR",
        "base_legale": "Convention CMR (Marchandises Routières) + Art. 308-320 CIMA (Branche 50)",
        "objet": "Couvre la responsabilité du transporteur en cas de perte, avarie ou retard de marchandises.",
        "plafond": "8,33 DTS (Droits de Tirage Spéciaux) par kg brut de marchandises perdues/avariées",
        "plafond_xaf": "~6 000 XAF/kg (variable selon taux DTS/XAF)",
        "exclusions": ["Force majeure", "Vice propre de la marchandise", "Emballage défectueux", "Faute du chargeur"],
        "delai_declaration": "7 jours pour avarie visible, 21 jours pour avarie non visible",
    },
    "B50_marchandises": {
        "branche": "50 — Transport",
        "nom": "Marchandises Transportées",
        "formules": {
            "tous_risques": "Couvre toutes pertes et avaries sauf exclusions nommées",
            "FAP_sauf": "Franchise d'Avaries Particulières sauf — couvre seulement les risques énumérés (naufrage, incendie, collision)",
        },
        "garanties_TR": ["Avaries particulières", "Avaries communes", "Frais de sauvetage", "Vol total", "Chute lors manutention"],
        "exclusions_communes": ["Vice propre", "Retard", "Pertes en poids/volume dans limites tolérées"],
    },
    "B50_corps_flotte": {
        "branche": "50 — Transport",
        "nom": "Corps de Véhicules (Flotte Transport)",
        "objet": "Couvre les dommages matériels aux véhicules de transport (poids lourds, camions, semi-remorques).",
        "garanties": ["Collision", "Accident sans tiers", "Incendie", "Vol", "Catastrophe naturelle"],
    },

    # ── MRH — MULTIRISQUE HABITATION ──────────────────────────────────────────
    "MRH_pack": {
        "branche": "MRH — Multirisque Habitation",
        "nom": "Multirisque Habitation",
        "base_legale": "Circulaire CIMA 2024-001 sur microassurance MRH + Art. 20-35 CIMA",
        "objet": "Produit packagé couvrant les principaux risques du logement en une seule police.",
        "garanties": [
            "Incendie, explosion, foudre",
            "Vol avec effraction",
            "RC locataire (dommages causés à l'immeuble ou aux voisins)",
            "RC propriétaire non-occupant",
            "Dégâts des eaux",
            "Catastrophes naturelles (catnat) selon zone",
            "Bris de glace (vitrages, miroirs)",
            "Objets de valeur (bijoux, art) — sur déclaration spécifique",
            "Électroménager — panne électrique accidentelle",
            "Perte de loyers (propriétaire)",
        ],
        "zones_catnat_cima": {
            "zone_rouge": ["Douala (Wouri)", "Abidjan littoral", "Cotonou"],
            "zone_orange": ["Yaoundé", "Dakar côte", "Libreville"],
            "zone_verte": ["Villes intérieures CEMAC"],
        },
        "microassurance": "Formule simplifiée disponible pour logements < 50m² (Circ. 2024-001, prime < 50 000 XAF/an)",
    },

    # ── BRANCHE VIE ───────────────────────────────────────────────────────────
    "VIE_capital_deces": {
        "branche": "Vie — Prévoyance",
        "nom": "Capital-Décès Toutes Causes",
        "base_legale": "Art. 50-70 Code CIMA + tables de mortalité CIMA-2016",
        "objet": "Verse un capital aux bénéficiaires désignés au décès de l'assuré, quelle qu'en soit la cause.",
        "types": {
            "temporaire_deces": "Couvre le décès pendant une durée déterminée (1 à 30 ans)",
            "vie_entiere": "Couvre le décès à tout moment (pas de terme)",
        },
        "beneficiaire": "Librement désigné — personne physique ou morale (Art. 4 CIMA)",
        "exclusions": ["Suicide dans les 2 premières années (Art. 65 CIMA)", "Guerre", "Actes terroristes sauf extension"],
        "tables_mortalite": "Tables TD 88-90 (hommes), TV 88-90 (femmes) ou tables CIMA-2016",
        "calcul_prime": "PM = PV(prestations futures) − PV(primes futures) selon méthode prospective",
    },
    "VIE_mixte": {
        "branche": "Vie — Épargne",
        "nom": "Assurance Vie Mixte",
        "objet": "Verse le capital soit à l'échéance si l'assuré est vivant (épargne), soit au décès avant l'échéance.",
        "garanties": ["Capital vie à terme (épargne constituée)", "Capital décès (protection famille)", "Exonération de primes en cas d'invalidité (option)"],
        "avantage_fiscal": "Exonération d'impôt sur les primes selon législation pays membre",
        "valeur_rachat": "Possible après 2 ans de cotisations (Art. 75 CIMA) — valeur de rachat = provisions mathématiques × coefficient",
    },
    "VIE_rente": {
        "branche": "Vie — Rente",
        "nom": "Rente Viagère",
        "objet": "Verse une rente régulière à vie à l'assuré, garantissant un revenu à la retraite.",
        "types": {
            "immediate": "Rente commence dès la souscription en échange d'un capital unique",
            "differee": "Rente commence à une date future — phase de constitution d'abord",
            "avec_annuites_garanties": "En cas de décès précoce, les annuités restantes sont versées aux héritiers",
            "rente_conjoint": "Rente continue à 60% ou 100% au conjoint survivant",
        },
        "calcul": "Rente annuelle = Capital × Taux de conversion (selon tables de mortalité + taux technique)",
    },
    "VIE_epargne": {
        "branche": "Vie — Épargne",
        "nom": "Épargne-Capitalisation",
        "objet": "Contrat d'accumulation d'épargne avec garantie de capital et rendement minimum garanti.",
        "garanties": ["Capital garanti à terme", "Taux technique garanti (≥ 3,5% zone CIMA en général)", "Participation aux bénéfices"],
        "avantages": ["Disponibilité (rachat partiel après délai)", "Transmission simplifiée", "Pas de droits de succession sur capital vie"],
    },
    "VIE_credit_vie": {
        "branche": "Vie — Prévoyance Crédit",
        "nom": "Assurance Crédit-Vie (Solde Restant Dû)",
        "objet": "Rembourse le solde restant dû d'un crédit en cas de décès ou d'invalidité de l'emprunteur.",
        "garanties": ["Décès — solde dû intégral remboursé à la banque", "IAD — solde dû remboursé", "ITT (option) — mensualités prises en charge pendant arrêt"],
        "beneficiaire": "Établissement prêteur (banque, microfinance)",
        "base_legale": "Art. 86-91 CIMA — Assurance en groupe",
    },
    "VIE_prevoyance_collective": {
        "branche": "Vie — Prévoyance Groupe",
        "nom": "Prévoyance Collective Employeur",
        "objet": "Contrat groupe souscrit par l'employeur couvrant les salariés contre les risques vie/invalidité.",
        "garanties": [
            "Capital décès toutes causes × n fois le salaire brut annuel",
            "Rente éducation pour enfants à charge",
            "Rente de conjoint",
            "Capital IAD (Invalidité Absolue et Définitive)",
            "ITT : indemnité journalière maintien de salaire",
        ],
        "designation": "Bénéficiaires légaux ou désignés — conjoints, enfants, ayants droit",
    },

    # ── BRANCHE 80 — MALADIE / SANTÉ ─────────────────────────────────────────
    "B80_frais_medicaux": {
        "branche": "80 — Maladie / Santé",
        "nom": "Frais Médicaux (Assurance Maladie)",
        "base_legale": "Art. 50-65 Code CIMA — Assurances de personnes",
        "objet": "Rembourse les frais de santé engagés par l'assuré et ses ayants droit.",
        "garanties": [
            "Consultations médicales généralistes et spécialistes",
            "Hospitalisation en chambre (1 ou 2 lits selon formule)",
            "Frais chirurgicaux et anesthésie",
            "Médicaments sur ordonnance",
            "Maternité (accouchement normal + complications)",
            "Optique (verres + montures sur ordonnance)",
            "Dentaire (soins + prothèses selon barème)",
            "Kinésithérapie et paramédicaux",
            "Évacuation sanitaire internationale",
            "Rapatriement de corps",
        ],
        "niveaux": {
            "economique": "Hospitalisation publique, médicaments génériques, remboursement 70%",
            "confort": "Hospitalisation privée, médicaments de marque, remboursement 80%",
            "prestige": "Chambre individuelle, cliniques agréées, remboursement 90-100%, évacuation internationale",
        },
        "delai_carence": {"maternite": "9 mois", "soins_dentaires": "6 mois", "optique": "12 mois"},
        "exclusions": ["Maladies préexistantes non déclarées", "Médecine esthétique", "Cures thermales", "Maladies sexuellement transmissibles (sauf extension)"],
    },

    # ── ACCIDENTS DE TRAVAIL ──────────────────────────────────────────────────
    "AT_complementaire": {
        "branche": "Accidents de Travail Complémentaire",
        "nom": "Accidents de Travail et Maladies Professionnelles (régime complémentaire)",
        "objet": "Complète le régime obligatoire de sécurité sociale pour les accidents de travail.",
        "garanties": ["Complément de rente incapacité", "Capital décès complémentaire", "Frais médicaux non pris en charge par la CNPS"],
        "note": "Le régime de base est géré par la CNPS (Cameroun), CNSS (Sénégal/CI), etc. L'assureur couvre le complément.",
    },
}


@dataclass
class SessionCopilote:
    """Session conversationnelle avec le copilote"""
    user_id: int
    role: str
    historique: list[dict] = field(default_factory=list)
    contexte_actif: Optional[str] = None  # numéro police, sinistre actif


class AssistantQuotidien:
    """
    Copilote IA YukpoAssurance — assistant de productivité quotidien.

    Capacités :
    1. Q&R réglementaire CIMA avec citation d'articles
    2. Rédaction de courriers, rapports, emails professionnels
    3. Analyse de clauses contractuelles
    4. Calculs techniques (primes, provisions, ratios)
    5. Veille réglementaire et alertes CRCA
    6. Formation continue intégrée
    7. Résumé de dossiers complexes
    """

    async def repondre(
        self,
        question: str,
        session: SessionCopilote,
        images_b64: Optional[list[str]] = None,
    ) -> dict:
        """Point d'entrée principal du copilote"""

        # Détection automatique du domaine selon la question
        domaine = self._detecter_domaine(question)

        # Enrichissement avec le contexte de session
        texte_enrichi = question
        if session.contexte_actif:
            texte_enrichi = f"[Contexte actif: {session.contexte_actif}]\n\n{question}"

        resultat = await orchestrateur.orchestrer(
            ContexteRequete(
                domaine=domaine,
                texte=texte_enrichi,
                images_b64=images_b64 or [],
                user_id=session.user_id,
                role_utilisateur=session.role,
                historique=session.historique[-6:],  # 6 derniers tours
            )
        )

        # Mise à jour de l'historique
        session.historique.append({"role": "user", "contenu": question})
        session.historique.append({"role": "assistant", "contenu": resultat.reponse})

        return {
            "reponse": resultat.reponse,
            "domaine_detecte": domaine.value,
            "modele": resultat.modele_utilise,
            "actions_suggerees": resultat.actions_suggerees,
        }

    # ──────────────────────────────────────────────────────────────
    # FONCTIONS SPÉCIALISÉES
    # ──────────────────────────────────────────────────────────────

    async def rediger_courrier(
        self,
        type_courrier: str,
        donnees: dict,
        role: str = "agent",
    ) -> str:
        """
        Rédaction assistée de courriers professionnels d'assurance.
        Types : mise en demeure, lettre de position, notification règlement,
                demande de pièces, résiliation, refus, relance...
        """
        templates = {
            "notification_reglement": "notification de règlement de sinistre",
            "demande_pieces": "demande de pièces complémentaires",
            "lettre_position": "lettre de position (refus partiel ou total de prise en charge)",
            "mise_en_demeure": "mise en demeure pour prime impayée",
            "accusé_reception": "accusé de réception de déclaration de sinistre",
            "resiliation": "notification de résiliation de contrat",
            "relance_renouvellement": "relance pour renouvellement de contrat",
        }

        libelle = templates.get(type_courrier, type_courrier)

        prompt = f"""
Rédige un {libelle} pour une compagnie d'assurance en zone CIMA (Cameroun).

Données du dossier :
{donnees}

Instructions :
- Ton : professionnel, courtois, précis
- Format : lettre officielle avec en-tête, référence, objet, corps, formule de politesse
- Cite les références réglementaires CIMA si applicable
- Langue : français professionnel camerounais
- Longueur : adaptée au type de courrier (concis pour un accusé, complet pour une lettre de position)
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION)
        return reponse.contenu

    async def analyser_clause_contrat(self, texte_clause: str) -> dict:
        """Analyse et explication d'une clause contractuelle"""
        prompt = f"""
Tu es juriste spécialisé en droit des assurances CIMA.

Analyse cette clause contractuelle :
{texte_clause}

Explique :
1. Ce que cette clause signifie en langage simple
2. Les droits et obligations de l'assuré
3. Les droits et obligations de l'assureur
4. Les situations où cette clause s'applique
5. Les éventuelles limites ou exclusions
6. Si cette clause est conforme au Code CIMA (Article applicable)
7. Les points de vigilance pour l'assuré

Retourne une analyse claire et structurée.
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
        return {"analyse": reponse.contenu, "clause_analysee": texte_clause[:200] + "..."}

    async def expliquer_article_cima(self, numero_article: str) -> dict:
        """Explication détaillée d'un article du Code CIMA"""
        return await cima_engine.repondre_question_cima(
            question=f"Explique-moi l'article {numero_article} du Code CIMA. "
                     f"Donne le texte, la signification pratique, et des exemples concrets.",
        )

    async def calculer_indemnite_sinistre(self, donnees_sinistre: dict) -> dict:
        """Calcul assisté de l'indemnité d'un sinistre"""
        prompt = f"""
Tu es expert en liquidation de sinistres pour une compagnie d'assurance en zone CIMA.

Calcule l'indemnité pour ce sinistre :
{donnees_sinistre}

Applique les règles CIMA :
- Déduction de la franchise contractuelle
- Application de la règle proportionnelle si sous-assurance
- Vétusté selon barème
- Déduction des sauvetages et récupérations

Retourne en JSON :
{{
  "valeur_dommage_total": 0,
  "franchise_deduite": 0,
  "vetuste_deduite": 0,
  "regle_proportionnelle": false,
  "indemnite_nette": 0,
  "part_assureur": 0,
  "part_reassureur_estimee": 0,
  "detail_calcul": {{}},
  "base_reglementaire": ""
}}
"""
        reponse = await ia_client.appeler(
            prompt=prompt, mode=ModeIA.PRECISION, json_attendu=True
        )
        return reponse.as_json()

    async def generer_rapport_sinistre(self, donnees: dict) -> str:
        """Génération automatique d'un rapport d'expertise sinistre"""
        prompt = f"""
Génère un rapport d'expertise de sinistre automobile professionnel.

Données du dossier :
{donnees}

Le rapport doit inclure :
1. Identification des parties et du véhicule
2. Circonstances du sinistre
3. Description des dommages constatés
4. Évaluation des réparations (avec détail pièces et main d'œuvre)
5. Conclusion et montant d'indemnité proposé
6. Éventuelles réserves de l'expert

Format : rapport officiel d'expertise, style technique et juridique.
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION)
        return reponse.contenu

    async def expliquer_garantie(
        self,
        garantie: str,
        niveau_detail: str = "complet",
        public: str = "agent",
    ) -> dict:
        """
        Explication pédagogique d'une garantie d'assurance.

        :param garantie: Nom ou code de la garantie (ex: "RC obligatoire auto", "capital décès", "IPP")
        :param niveau_detail: "rapide" | "complet" | "expert"
        :param public: "agent" | "client" | "manager"
        """
        # Recherche dans la base locale
        garantie_lower = garantie.lower()
        fiche_trouvee = None
        for cle, fiche in GARANTIES_CIMA.items():
            if any(mot in garantie_lower for mot in cle.lower().split("_")) or \
               garantie_lower in fiche.get("nom", "").lower():
                fiche_trouvee = fiche
                break

        contexte_fiche = ""
        if fiche_trouvee:
            contexte_fiche = f"\nFiche technique disponible :\n{fiche_trouvee}\n"

        niveaux = {
            "rapide": "Réponds en 3-4 phrases simples.",
            "complet": "Réponds avec : définition, garanties couvertes, exclusions principales, plafonds, base légale CIMA.",
            "expert": "Réponds avec tous les détails techniques : articles CIMA précis, calculs, barèmes, comparaison avec marché international.",
        }
        publics = {
            "agent": "language professionnel assurance, termes techniques explicités",
            "client": "langage simple, éviter le jargon, exemples concrets de la vie courante",
            "manager": "vision synthétique, enjeux risque et financiers, conformité réglementaire",
        }

        prompt = f"""
Tu es expert en assurance CIMA. Explique la garantie suivante : "{garantie}"
{contexte_fiche}
Niveau de détail : {niveaux.get(niveau_detail, niveaux['complet'])}
Public : {publics.get(public, publics['agent'])}

Structure ta réponse :
1. **Définition** — Qu'est-ce que cette garantie couvre ?
2. **Ce qui est garanti** — Liste des risques/événements couverts
3. **Ce qui est exclu** — Exclusions principales à connaître
4. **Plafonds et franchises** — Montants importants
5. **Base légale** — Article(s) du Code CIMA applicable(s)
6. **Exemple concret** — Cas pratique en zone CIMA (Cameroun/CI/Sénégal)
7. **Points de vigilance** — Ce que l'agent/client doit savoir absolument
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
        return {
            "garantie": garantie,
            "explication": reponse.contenu,
            "fiche_technique": fiche_trouvee,
            "niveau": niveau_detail,
            "public": public,
        }

    async def comparer_garanties(self, garanties: list[str]) -> dict:
        """Tableau comparatif de plusieurs garanties ou formules"""
        prompt = f"""
Tu es expert en produits d'assurance CIMA. Compare ces garanties/formules :
{garanties}

Produis un tableau comparatif avec :
- Objet de chaque garantie
- Événements couverts (✓) et exclus (✗)
- Plafonds typiques en XAF
- Article CIMA de référence
- Pour qui est-elle recommandée ?
- Prime indicative (ordre de grandeur)

Conclus par une recommandation selon le profil de risque.
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
        return {"comparaison": reponse.contenu, "garanties_comparees": garanties}

    async def veille_reglementaire(self) -> dict:
        """Synthèse des dernières évolutions réglementaires CIMA"""
        prompt = """
En tant qu'expert en réglementation CIMA, fournis une synthèse des points réglementaires
clés que les compagnies d'assurance de la zone CIMA doivent maîtriser en 2024-2025 :

1. Principales obligations prudentielles (ratios, provisions, couverture)
2. Délais réglementaires importants à respecter
3. États financiers obligatoires et leurs échéances
4. Points d'attention fréquemment relevés lors des inspections CRCA
5. Évolutions réglementaires récentes ou annoncées

Structure ta réponse par thème avec des rappels pratiques pour les équipes.
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.COPILOTE)
        return {
            "synthese": reponse.contenu,
            "date_maj": "2025",
            "source": "Code CIMA + circulaires CRCA",
        }

    async def former_equipe(self, sujet: str, niveau: str = "operationnel") -> dict:
        """
        Formation intégrée — explications adaptées au niveau de l'équipe.
        Niveaux : "operationnel" | "manager" | "direction"
        """
        niveaux_desc = {
            "operationnel": "agents de production, gestionnaires sinistres, comptables",
            "manager": "chefs de département, directeurs techniques",
            "direction": "DG, DAF, membres du Conseil d'Administration",
        }

        prompt = f"""
Tu es formateur expert en assurance pour des équipes en zone CIMA.

Prépare un module de formation sur le sujet : "{sujet}"
Public cible : {niveaux_desc.get(niveau, niveau)}

Le module doit inclure :
1. Objectifs pédagogiques (3-5 points)
2. Contenu principal (structuré, progressif)
3. Exemples concrets tirés de la pratique assurance camerounaise
4. Points clés à retenir (résumé mémorisable)
5. Quiz de validation (3-5 questions avec réponses)
6. Ressources complémentaires

Adapte le vocabulaire et la profondeur technique au niveau du public cible.
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION)
        return {
            "sujet": sujet,
            "niveau": niveau,
            "module_formation": reponse.contenu,
        }

    # ──────────────────────────────────────────────────────────────
    # DÉTECTION AUTOMATIQUE DU DOMAINE
    # ──────────────────────────────────────────────────────────────

    def _detecter_domaine(self, question: str) -> DomaineMétier:
        q = question.lower()

        # Sinistres
        if any(m in q for m in [
            "sinistre", "accident", "déclaration", "expertise", "règlement",
            "dossier sinistre", "indemnité", "dommage", "blessé", "victime",
        ]):
            return DomaineMétier.SINISTRES

        # CIMA réglementaire
        if any(m in q for m in [
            "cima", "crca", "article", "réglementaire", "provision", "marge",
            "solvabilité", "ratio", "état c", "psap", "ppna", "pm vie", "prc",
            "circulaire", "délai réglementaire", "sanction", "amende crca",
        ]):
            return DomaineMétier.CIMA

        # Comptabilité
        if any(m in q for m in [
            "comptab", "facture", "écriture", "rapprochement", "bilan",
            "ohada", "imputation", "pcsa", "journal", "grand-livre",
        ]):
            return DomaineMétier.COMPTABILITE

        # Souscription / garanties
        if any(m in q for m in [
            "souscription", "contrat", "police", "prime", "garantie", "devis",
            "kyc", "branche", "couvre", "couverture", "exclusion", "franchise",
            "rc obligatoire", "tous risques", "bris de glace", "vol", "incendie",
            "mrh", "multirisque", "vie mixte", "capital décès", "invalidité",
            "ipp", "ipt", "itt", "frais médicaux", "hospitalisation", "rente",
            "épargne", "capitalisation", "crédit-vie", "cmr", "transport",
        ]):
            return DomaineMétier.SOUSCRIPTION

        # Courtiers
        if any(m in q for m in [
            "courtier", "commission", "intermédiaire", "apporteur",
            "production courtier", "bordereau", "état de commissions",
        ]):
            return DomaineMétier.COURTIERS

        # Fraude
        if any(m in q for m in [
            "fraude", "suspect", "frauduleux", "investigation", "signal",
            "anomalie", "incohérence", "faux documents",
        ]):
            return DomaineMétier.FRAUDE

        return DomaineMétier.COPILOTE


# Sessions en mémoire (en production : Redis ou DB)
_sessions: dict[int, SessionCopilote] = {}


def get_or_create_session(user_id: int, role: str = "agent") -> SessionCopilote:
    if user_id not in _sessions:
        _sessions[user_id] = SessionCopilote(user_id=user_id, role=role)
    return _sessions[user_id]


# Instance singleton
assistant = AssistantQuotidien()

assistant_copilote = assistant  # alias
