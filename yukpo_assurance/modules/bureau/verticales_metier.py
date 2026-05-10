"""
Phase 3 — Verticales métier.

Catalogue de connaissances sectorielles injecté dans les prompts orchestrateurs
(Designer Pro + G1 documents). Le LLM utilise ces données comme **inspiration
et garde-fous métier**, jamais comme limite stricte.

Si le brief user demande quelque chose hors des templates listés → l'IA
invente un template approprié en se basant sur les conventions du secteur
(format légal, vocabulaire, références réglementaires).

Détection vertical = `profil.metier` ou `profil.secteur` (champs existants
dans ProfilDesigner / ProfilPro). L'utilisateur ne voit JAMAIS de sélecteur
"choisis une vertical" — c'est dérivé silencieusement de son profil.

5 verticales couvertes :
  - banque_finance     : banques, micro-crédit, assurance, conseil financier
  - pharma_sante       : pharmacies, cliniques, hôpitaux, labos
  - immobilier         : agences immo, promoteurs, syndics
  - education          : écoles primaires/secondaires, universités, formation
  - rh_paie            : services RH, cabinets paie, intérim, recrutement
"""
from __future__ import annotations

from typing import Optional


VERTICALES_METIER: dict[str, dict] = {
    # ──────────────────────────────────────────────────────────────────────
    "banque_finance": {
        "label": "Banque / Finance / Assurance",
        "mots_cles_metier": [
            "banque", "agence bancaire", "microfinance", "MFI", "MFB", "BICEC",
            "Ecobank", "UBA", "SGBC", "Afriland", "BEAC", "BCEAO", "CIMA",
            "assurance", "assureur", "courtier", "actuaire", "sinistre", "bilan",
            "audit comptable", "cabinet conseil", "fiduciaire", "expert-comptable",
        ],
        "regulations": [
            "CIMA (Conférence Interafricaine des Marchés d'Assurances)",
            "BEAC / BCEAO (politique monétaire CEMAC/UEMOA)",
            "OHADA (Acte uniforme comptabilité — SYSCOHADA)",
            "Bâle III (ratios prudentiels banques)",
            "GAFI / TRACFIN (lutte blanchiment Afrique)",
        ],
        "templates_inspirations": [
            # Documents internes
            "Rapport d'audit comptable annuel (format SYSCOHADA)",
            "État financier IFRS / SYSCOHADA (bilan + compte de résultat)",
            "Note de crédit interne (analyse risque emprunteur)",
            "Procès-verbal de conseil d'administration",
            "Rapport de sinistre auto/habitation (CIMA)",
            "Manuel de procédures KYC / lutte anti-blanchiment",
            # Documents clients
            "Contrat d'ouverture de compte (avec mentions légales BEAC)",
            "Contrat de prêt immobilier / professionnel",
            "Conditions générales de vente (CGV) micro-assurance",
            "Police d'assurance auto/habitation/santé",
            "Lettre de relance impayé (3 niveaux : amiable → mise en demeure)",
            "Attestation de garantie bancaire",
            # Visuels marketing
            "Plaquette commerciale produit épargne",
            "Brochure tarifaire (8 pages, transparence BEAC)",
            "Carte de visite personnel commercial banque",
            "Affiche agence (offre du mois, taux d'intérêt)",
            "Magazine annuel investisseurs (rapport CSR + financier)",
        ],
        "ton_recommande": "professionnel, rassurant, vouvoiement systématique, vocabulaire technique précis (taux nominal, TEG, garantie, sinistre). Pas de familiarités, pas d'anglicismes superflus.",
        "lexique_prefere": ["client", "souscripteur", "bénéficiaire", "garantie",
                            "prime", "échéance", "capital", "intérêts"],
        "mots_eviter": ["facile", "easy", "promo", "deal", "kif", "lol"],
        "couleurs_typiques": "bleu marine #003D82 / vert finance #006633 / accents or #FFB800",
        "polices_typiques": "Inter, Helvetica, Lato (sans-serif sobres) ou Playfair Display pour les chartes premium",
    },
    # ──────────────────────────────────────────────────────────────────────
    "pharma_sante": {
        "label": "Pharma / Santé",
        "mots_cles_metier": [
            "pharmacie", "officine", "clinique", "hôpital", "CHU", "centre de santé",
            "laboratoire", "biologie médicale", "infirmier", "médecin", "ordonnance",
            "consultation", "patient", "posologie", "principe actif", "DCI",
            "AMM", "OCEAC", "OMS", "OMD",
        ],
        "regulations": [
            "OCEAC (Organisation pour la Coordination de la lutte contre les Endémies en Afrique Centrale)",
            "WHO/OMS guidelines (médicaments essentiels)",
            "Liste des médicaments essentiels nationale (LME)",
            "Code de déontologie médicale (Ordre des Médecins)",
            "Pharmacopée africaine (médicaments traditionnels)",
        ],
        "templates_inspirations": [
            # Documents médicaux
            "Ordonnance médicale (avec posologie + DCI)",
            "Compte-rendu de consultation",
            "Bilan biologique (analyses laboratoire)",
            "Certificat médical (aptitude/incapacité/maladie)",
            "Fiche de soins infirmier",
            "Protocole médical CHU (procédure intervention)",
            "Compte-rendu opératoire",
            # Documents officine
            "Étiquette médicament avec posologie",
            "Fiche conseil patient (effets secondaires)",
            "Note de garde de pharmacie",
            "Inventaire stock médicaments (ordre alphabétique DCI)",
            # Visuels patient/communication
            "Brochure prévention sanitaire (paludisme, VIH, COVID)",
            "Flyer campagne vaccination",
            "Affiche horaires garde",
            "Programme journée santé scolaire",
            "Magazine trimestriel CHU (avancées + témoignages patients)",
        ],
        "ton_recommande": "rigoureux, scientifique, empathique. Vocabulaire médical avec terminologie DCI et latin si pertinent. Ne jamais minimiser un risque. Rappels obligatoires : 'sous prescription médicale', 'avis du médecin'.",
        "lexique_prefere": ["patient", "posologie", "principe actif", "prescription",
                            "effet indésirable", "contre-indication", "diagnostic"],
        "mots_eviter": ["pilule miracle", "guérison garantie", "sans risque",
                        "100% efficace", "remède naturel"],
        "couleurs_typiques": "vert médical #00875A / bleu confiance #1976D2 / blanc + croix rouge selon contexte",
        "polices_typiques": "Inter, Open Sans, Lato (lisibilité maximale). Pas de polices fantaisie sur ordonnances.",
    },
    # ──────────────────────────────────────────────────────────────────────
    "immobilier": {
        "label": "Immobilier",
        "mots_cles_metier": [
            "agence immobilière", "promoteur", "syndic", "copropriété", "bail",
            "location", "vente", "achat", "loyer", "notaire", "cadastre", "titre foncier",
            "OHADA droit foncier", "loi camerounaise immobilier",
        ],
        "regulations": [
            "OHADA (Acte uniforme sociétés commerciales — SCI)",
            "Code foncier national (Cameroun, Sénégal, Côte d'Ivoire selon pays)",
            "Loi sur les baux à usage d'habitation (durée, dépôt garantie, état des lieux)",
            "Réglementation copropriété (charges, assemblée générale)",
        ],
        "templates_inspirations": [
            # Documents légaux
            "Bail à usage d'habitation (3-6-9 ans, avec OHADA)",
            "Bail commercial",
            "Mandat de vente exclusif/simple",
            "Mandat de gestion locative",
            "État des lieux d'entrée/sortie",
            "Quittance de loyer mensuelle",
            "Avis d'échéance loyer",
            "Procès-verbal d'assemblée générale copropriété",
            # Marketing/Vente
            "Fiche détaillée d'un bien (photos + DPE + plan)",
            "Brochure programme neuf (16-24 pages)",
            "Plan masse résidentiel (légende + lots)",
            "Carte de visite agent immobilier",
            "Flyer journée portes ouvertes",
            "Magazine trimestriel agence (biens vendus + tendances marché)",
        ],
        "ton_recommande": "professionnel, descriptif, valorisant sans exagération. Toujours mentionner OHADA / titre foncier / cadastre selon le pays. Annoncer prix en FCFA (XAF/XOF) ET en euros pour expat.",
        "lexique_prefere": ["bien immobilier", "preneur", "bailleur", "loyer",
                            "dépôt de garantie", "charges récupérables", "honoraires"],
        "mots_eviter": ["affaire en or", "occasion à saisir", "prix cassé"],
        "couleurs_typiques": "marron terre #6D4C41 / vert nature #2E7D32 / accent gold #C9A227",
        "polices_typiques": "Playfair Display (titres luxe) + Lato/Inter corps",
    },
    # ──────────────────────────────────────────────────────────────────────
    "education": {
        "label": "Éducation / Formation",
        "mots_cles_metier": [
            "école", "lycée", "collège", "université", "centre de formation",
            "élève", "étudiant", "enseignant", "directeur", "censeur", "proviseur",
            "bulletin", "diplôme", "attestation", "scolarité", "rentrée",
            "BAC", "BEPC", "CEP", "BEP", "BTS", "licence", "master",
            "MINESEC", "MINESUP", "MINEDUB",
        ],
        "regulations": [
            "MINEDUB / MINESEC / MINESUP (ministères Cameroun)",
            "Programmes officiels nationaux",
            "Système d'évaluation (notation /20 ou /100 selon pays)",
            "OHADA pour établissements privés (statuts SCI ou GIC)",
        ],
        "templates_inspirations": [
            # Documents scolaires
            "Bulletin de notes trimestriel (matières + moyennes + appréciations)",
            "Bulletin annuel de fin d'année",
            "Diplôme/Attestation de fin de cycle",
            "Certificat de scolarité",
            "Convocation parents d'élèves",
            "Avis de passage en classe supérieure",
            "Calendrier scolaire annuel",
            # Communication
            "Livret d'accueil rentrée scolaire",
            "Programme journée portes ouvertes",
            "Brochure établissement (présentation, infrastructures, frais)",
            "Carte d'étudiant",
            "Badge accès parents/visiteurs",
            "Affiche rentrée scolaire",
            "Magazine annuel école (réussites + projets pédagogiques)",
            "Programme cérémonie de remise des diplômes",
            # Documents pédagogiques
            "Fiche de préparation de cours",
            "Cahier de textes numérique",
            "Protocole anti-violence scolaire",
        ],
        "ton_recommande": "bienveillant, motivant, accessible aux parents (FR + langue locale parfois). Pour les élèves : encourageant. Pour les diplômes : solennel et formel.",
        "lexique_prefere": ["élève", "étudiant", "apprenant", "famille",
                            "réussite", "progression", "compétence", "savoir"],
        "mots_eviter": ["mauvais élève", "nul", "incapable", "raté"],
        "couleurs_typiques": "bleu école #1565C0 / vert savoir #2E7D32 / accent jaune motivation #FBC02D",
        "polices_typiques": "Cormorant ou Playfair (diplômes solennels) · Inter/Lato (bulletins/communication)",
    },
    # ──────────────────────────────────────────────────────────────────────
    "rh_paie": {
        "label": "Ressources Humaines / Paie",
        "mots_cles_metier": [
            "ressources humaines", "RH", "DRH", "paie", "salarié", "employé",
            "contrat de travail", "CDI", "CDD", "intérim", "recrutement",
            "fiche de paie", "bulletin de salaire", "CNPS", "IRPP",
            "prime de transport", "13e mois", "congés payés",
            "OIT", "code du travail",
        ],
        "regulations": [
            "Code du travail national (Cameroun loi n°92/007, Sénégal, Côte d'Ivoire selon pays)",
            "CNPS (Cotisations sociales)",
            "OIT (Organisation Internationale du Travail) — conventions ratifiées",
            "OHADA (statuts sociétés employeuses)",
            "Convention collective sectorielle (banque, BTP, hôtellerie, etc.)",
        ],
        "templates_inspirations": [
            # Contrats et avenants
            "Contrat de travail CDI (avec OHADA + Code du travail local)",
            "Contrat de travail CDD",
            "Contrat de stage rémunéré/non rémunéré",
            "Avenant au contrat (changement poste, salaire, lieu)",
            "Lettre de mutation",
            "Lettre de promotion",
            # Paie et social
            "Bulletin de salaire mensuel (CNPS, IRPP, primes, retenues)",
            "Attestation de salaire pour dossier visa/banque",
            "Reçu solde de tout compte (STC)",
            "Certificat de travail",
            "Attestation de présence",
            # Procédures RH
            "Lettre de convocation entretien préalable",
            "Lettre de licenciement (motivation Code du travail)",
            "Lettre d'avertissement disciplinaire",
            "Lettre de mise à pied",
            "Procès-verbal de réunion DP/CHSCT",
            # Recrutement
            "Offre d'emploi interne/externe",
            "Lettre de réponse négative candidature",
            "Lettre d'embauche / promesse d'embauche",
            # Communication interne
            "Note de service",
            "Charte éthique entreprise",
            "Livret d'accueil nouveau collaborateur (16 pages)",
            "Organigramme entreprise (visuel)",
            "Rapport annuel social (RSE + statistiques sociales)",
        ],
        "ton_recommande": "formel, juridiquement précis, vouvoiement obligatoire. Citer systématiquement les références légales (article du Code du travail, convention collective applicable).",
        "lexique_prefere": ["salarié", "collaborateur", "employeur", "rémunération",
                            "convention collective", "ancienneté", "préavis"],
        "mots_eviter": ["viré", "licencié sec", "embauché vite fait", "boss"],
        "couleurs_typiques": "bleu corporate #003366 / gris professionnel #607D8B / accent rouge #C62828 (urgent uniquement)",
        "polices_typiques": "Inter, Helvetica, Arial (clarté juridique). Times New Roman pour les contrats notariés.",
    },
}


def detecter_vertical(metier: Optional[str], secteur: Optional[str] = None) -> Optional[str]:
    """
    Devine la vertical à partir des champs profil.metier / profil.secteur.
    Retourne la clé VERTICALES_METIER ou None si aucune correspondance.
    """
    texte = f"{metier or ''} {secteur or ''}".lower()
    if not texte.strip():
        return None
    scores: dict[str, int] = {}
    for key, vert in VERTICALES_METIER.items():
        for mot in vert.get("mots_cles_metier", []):
            if mot.lower() in texte:
                scores[key] = scores.get(key, 0) + 1
    if not scores:
        return None
    return max(scores, key=scores.get)


def descripteur_vertical_pour_llm(vertical_key: str) -> dict:
    """
    Descripteur compact pour injection dans un prompt LLM. Le LLM utilise
    ces infos comme INSPIRATION et GARDE-FOUS, pas comme limite stricte.
    """
    vert = VERTICALES_METIER.get(vertical_key)
    if not vert:
        return {}
    return {
        "vertical": vertical_key,
        "label": vert["label"],
        "regulations_cles": vert.get("regulations", [])[:5],
        "templates_inspirations": vert.get("templates_inspirations", [])[:25],
        "ton_recommande": vert.get("ton_recommande", ""),
        "lexique_prefere": vert.get("lexique_prefere", []),
        "mots_eviter": vert.get("mots_eviter", []),
        "couleurs_typiques": vert.get("couleurs_typiques", ""),
        "polices_typiques": vert.get("polices_typiques", ""),
    }


def construire_bloc_prompt_vertical(vertical_key: Optional[str]) -> str:
    """
    Bloc texte à injecter dans les prompts orchestrateurs (Designer Pro + G1).

    PHILOSOPHIE NON-NÉGOCIABLE : ce contexte est une BIBLIOTHÈQUE d'inspirations
    et de garde-fous métier, PAS une limite. Le LLM doit s'en servir pour gagner
    en pertinence, mais s'autoriser à inventer un template/format hors catalogue
    si le besoin user le justifie.
    """
    if not vertical_key:
        return ""
    desc = descripteur_vertical_pour_llm(vertical_key)
    if not desc:
        return ""
    return f"""
═══════════════════════════════════════════════════
  CONTEXTE MÉTIER — {desc['label']}
═══════════════════════════════════════════════════
Le profil utilisateur indique qu'il travaille dans ce secteur. Utilise ces
connaissances comme INSPIRATION + GARDE-FOUS — JAMAIS comme limite.

Si l'utilisateur demande un format/document HORS de la liste ci-dessous,
INVENTE-LE en respectant les conventions du secteur (réglementations,
vocabulaire, ton). Le catalogue est une bibliothèque, pas une cage.

⚖️ Réglementations à respecter / mentionner si pertinent :
{chr(10).join(f"  - {r}" for r in desc['regulations_cles'])}

📚 Templates fréquents (inspirations, ne pas s'y limiter) :
{chr(10).join(f"  - {t}" for t in desc['templates_inspirations'])}

🗣️ Ton attendu : {desc['ton_recommande']}

✅ Lexique préféré : {', '.join(desc['lexique_prefere'])}
❌ Mots à éviter : {', '.join(desc['mots_eviter'])}

🎨 Codes visuels typiques (Designer Pro) :
   Couleurs : {desc['couleurs_typiques']}
   Polices : {desc['polices_typiques']}

RAPPEL : si l'user demande quelque chose qui n'est PAS dans la liste de
templates ci-dessus, ne refuse PAS — invente le template approprié sur la
base des conventions du secteur. Sois créatif dans le respect des règles
métier.
"""
