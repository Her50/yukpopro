"""
Phase 3 — Verticales métier (mondiales, sans RAG figé pour les codes).

ARCHITECTURE :
- 5 verticales SEED (banque_finance, pharma_sante, immobilier, education,
  rh_paie) servent d'EXEMPLES few-shot pour le LLM dynamique. Elles ne
  limitent PAS l'app à 5 secteurs.
- Pour TOUT autre secteur (BTP, agriculture, restauration, transport,
  e-commerce, tourisme, énergie, manufacturing, IT/SaaS, médias, sport,
  ONG, gouvernement, art/culture, etc.), `detecter_vertical_dynamique_llm()`
  génère le descripteur vertical à la volée via Sonnet (sites officiels,
  templates inspirations, ton, lexique, couleurs typiques) avec cache
  Redis 7 jours par (metier, secteur, pays).
- Couverture effective : TOUS les secteurs du monde, dans TOUS les pays,
  avec adaptation automatique aux régulateurs nationaux et aux conventions
  sectorielles.

⚠️ POLITIQUES NON-NÉGOCIABLES :

1. **Aucune régionalisation forcée** — l'app sert tout utilisateur au monde.
2. **Aucune réglementation hardcodée** — recherche web temps réel via
   `recherche_officielle_metier.chercher_reglementation()`, fallback LLM
   avec mention "à vérifier sur source officielle".
3. **Détection silencieuse** depuis profil.metier + profil.secteur + pays.
   L'utilisateur ne voit JAMAIS un sélecteur de secteur.
4. **Aucune limite à 5 secteurs** — le LLM compose dynamiquement.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger("yukpo_assurance.bureau.verticales_metier")


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
        # Sites officiels GLOBAUX pour recherche web temps réel (Serper).
        # Le LLM ajoute les régulateurs nationaux selon profil.pays
        # (FED/SEC US, BoE/FCA UK, ECB/EBA EU, MAS Singapour, BEAC CEMAC,
        # BCEAO UEMOA, RBI Inde, BCB Brésil, BCRA Argentine, etc.)
        "sites_officiels_globaux": [
            "bis.org",          # Bâle, standards prudentiels mondiaux
            "fatf-gafi.org",    # GAFI lutte blanchiment
            "imf.org",          # FMI macro
            "worldbank.org",
            "ifrs.org",          # standards comptables IFRS
            "iaisweb.org",       # International Association of Insurance Supervisors
            "ohada.org",         # Afrique zone OHADA (sous-régional)
            "cima-afrique.org",  # Assurance CEMAC/UEMOA (sous-régional)
            "eba.europa.eu",     # European Banking Authority
            "sec.gov",           # USA
        ],
        "domaines_expertise": [
            "Réglementation prudentielle (Bâle III/IV, ratios capital)",
            "Comptabilité (IFRS, GAAP US, normes nationales OHADA/SYSCOHADA, etc.)",
            "Assurance (IAIS mondiale, CIMA Afrique, Solvency II EU, NAIC US)",
            "Lutte anti-blanchiment (GAFI/FATF, sanctions OFAC/EU)",
            "Le LLM s'adapte au pays : régulateur national + cadre régional",
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
        "sites_officiels_globaux": [
            "who.int", "fda.gov", "ema.europa.eu",
            "ich.org",            # International Council on Harmonisation
            "pharmacopeia.cn",    # USP/Pharmacopeia
            "edqm.eu",            # European Pharmacopoeia
            "ansm.sante.fr",      # France
            "mhra.gov.uk",        # UK
            "pmda.go.jp",         # Japon
            "afro.who.int",       # OMS Afrique
            "oceac.org",          # CEMAC
        ],
        "domaines_expertise": [
            "AMM (FDA US, EMA Europe, AFMPS BE, MHRA UK, PMDA JP, ANSM FR, AMA nationale)",
            "Protocoles cliniques OMS et guidelines régionales",
            "Pharmacopées (USP, Eur.Ph., JP, BP, pharmacopée nationale)",
            "Listes médicaments essentiels nationales",
            "Le LLM identifie le régulateur pertinent selon profil.pays",
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
        "sites_officiels_globaux": [
            "ohada.org",        # Afrique zone OHADA
            "fiabci.org",       # Fédération internationale des professions immobilières
            "uli.org",          # Urban Land Institute (référence US/global)
            "rics.org",         # Royal Institution of Chartered Surveyors (UK/global)
            "fnaim.fr",         # France (best practices francophones)
            "nar.realtor",      # National Association of Realtors USA
        ],
        "domaines_expertise": [
            "Droit foncier (OHADA Afrique, Code civil français, Common law UK/US, etc.)",
            "Baux d'habitation/commercial (durée, garanties, charges) — varie par pays",
            "Copropriété (régimes nationaux différents)",
            "Mandats et déontologie (RICS, NAR, FNAIM, etc.)",
            "Le LLM s'adapte au cadre juridique du pays user",
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
        "sites_officiels_globaux": [
            "unesco.org",
            "oecd.org",                    # OCDE éducation, PISA
            "iau-aiu.net",                 # International Assoc. of Universities
            "ed.gov",                      # US Dept of Education
            "education.gouv.fr",           # France
            "gov.uk/government/organisations/department-for-education",  # UK
            "minedub.cm",                  # Cameroun (exemple)
        ],
        "domaines_expertise": [
            "Programmes officiels nationaux (variant par pays — Common Core US, "
            "Programmes EN UK, MINEDUB Cameroun, etc.)",
            "Systèmes d'évaluation (notation /20 FR, GPA US, A-Level UK, etc.)",
            "Diplômes officiels (équivalences via NARIC/CAMES/UNESCO)",
            "Statuts établissements (publics/privés — varie par pays)",
            "Le LLM identifie le système éducatif selon profil.pays",
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
        "sites_officiels_globaux": [
            "ilo.org",                     # OIT (référence mondiale)
            "shrm.org",                    # Society for Human Resource Mgmt (US/global)
            "cipd.co.uk",                  # CIPD (UK)
            "service-public.fr",           # France droit du travail
            "dol.gov",                     # US Dept of Labor
            "gov.uk/topic/employing-people",  # UK
            "ohada.org",                   # OHADA Afrique
            "cnps.cm",                     # exemple caisse sociale
        ],
        "domaines_expertise": [
            "Code du travail (variant par pays — Code FR, FLSA US, ERA UK, "
            "loi nationale Afrique CEMAC/UEMOA, etc.)",
            "Cotisations sociales (régimes nationaux)",
            "Conventions OIT ratifiées",
            "Conventions collectives sectorielles (par pays)",
            "Le LLM identifie le cadre juridique selon profil.pays",
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

    Pour détection plus profonde depuis un brief libre (si profil vide),
    utiliser `detecter_vertical_depuis_brief()` (LLM Haiku micro-call).
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


async def detecter_vertical_depuis_brief(brief: str) -> Optional[str]:
    """
    Refinement Phase 3+ : si profil.metier vide, détecte la vertical
    directement depuis le brief utilisateur via Haiku micro-call (~30 tokens).

    Échec silencieux → None. Cache enabled (utiliser_cache=True).
    """
    if not brief or len(brief.strip()) < 15:
        return None
    # Heuristique rapide : essai mots-clés direct sur le brief
    txt_low = brief.lower()
    scores: dict[str, int] = {}
    for key, vert in VERTICALES_METIER.items():
        for mot in vert.get("mots_cles_metier", []):
            if mot.lower() in txt_low:
                scores[key] = scores.get(key, 0) + 1
    if scores and max(scores.values()) >= 2:
        return max(scores, key=scores.get)
    # Fallback Haiku si heuristique faible
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        prompt = (
            f"Classifie le secteur d'activité du brief utilisateur dans une"
            f" SEULE catégorie parmi : banque_finance, pharma_sante,"
            f" immobilier, education, rh_paie, autre.\n\n"
            f"Brief : «{brief[:1500]}»\n\n"
            f"Réponds UNIQUEMENT par 1 mot (la catégorie). Pas d'explication."
        )
        rep = await ia_client.appeler(
            prompt=prompt, mode=ModeIA.PRECISION,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
            max_tokens_override=20, utiliser_cache=True,
        )
        cat = (rep.contenu or "").strip().lower().split()[0]
        if cat in VERTICALES_METIER:
            return cat
    except Exception:
        pass
    return None


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
        "domaines_expertise": vert.get("domaines_expertise", []),
        "sites_officiels_globaux": vert.get("sites_officiels_globaux", [])[:10],
        "templates_inspirations": vert.get("templates_inspirations", [])[:25],
        "ton_recommande": vert.get("ton_recommande", ""),
        "lexique_prefere": vert.get("lexique_prefere", []),
        "mots_eviter": vert.get("mots_eviter", []),
        "couleurs_typiques": vert.get("couleurs_typiques", ""),
        "polices_typiques": vert.get("polices_typiques", ""),
    }


# ─── Verticalité DYNAMIQUE LLM (couverture mondiale tous secteurs) ──────────


def _cle_cache_vertical(metier: str, secteur: str, pays: str) -> str:
    """Hash stable pour cache Redis (7j TTL)."""
    raw = f"{(metier or '').lower().strip()}|{(secteur or '').lower().strip()}|{(pays or '').upper().strip()}"
    return f"vert:dyn:{hashlib.sha1(raw.encode()).hexdigest()[:24]}"


async def _lire_cache_vertical(cle: str) -> Optional[dict]:
    """Lecture cache Redis (silencieux si Redis down)."""
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        raw = await r.get(cle)
        await r.aclose()
        if raw:
            return json.loads(raw if isinstance(raw, str) else raw.decode())
    except Exception:
        return None
    return None


async def _ecrire_cache_vertical(cle: str, descripteur: dict) -> None:
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        await r.set(cle, json.dumps(descripteur), ex=7 * 86400)  # 7 jours
        await r.aclose()
    except Exception:
        pass


async def detecter_vertical_dynamique_llm(
    metier: Optional[str] = None,
    secteur: Optional[str] = None,
    pays: Optional[str] = None,
    brief: Optional[str] = None,
) -> Optional[dict]:
    """
    Génère DYNAMIQUEMENT un descripteur vertical pour TOUT secteur mondial.

    Pour les 5 verticales SEED (banque_finance, pharma_sante, immobilier,
    education, rh_paie) → utilise les exemples hardcodés (pré-validés).

    Pour TOUT autre secteur (BTP, agriculture, restauration, transport,
    e-commerce, tourisme, énergie, IT/SaaS, médias, sport, ONG, gouvernement,
    art/culture, mining, télécoms, automobile, aéronautique, mode, beauté,
    fitness, jeux vidéo, blockchain, etc.) → Sonnet 4.6 compose le descripteur
    avec :
      - sites_officiels_globaux (régulateurs mondiaux du secteur)
      - sites_officiels_pays (régulateurs nationaux de `pays`)
      - templates_inspirations (15-25 documents/visuels typiques)
      - ton_recommande, lexique_prefere, mots_eviter
      - couleurs_typiques, polices_typiques
      - domaines_expertise (5-8 axes)

    Cache Redis 7 jours par (metier, secteur, pays). Coût marginal :
    ~2000 tokens Sonnet × tarif → ~0.5 FCFA, absorbé par marge LLM 12×.

    Retourne le descripteur (shape compatible descripteur_vertical_pour_llm)
    ou None si tout échoue.
    """
    metier_n = (metier or "").strip()
    secteur_n = (secteur or "").strip()
    if not (metier_n or secteur_n or brief):
        return None

    # 1. Si un des 5 SEED matche → utiliser direct (rapide, qualité validée)
    seed_key = detecter_vertical(metier_n, secteur_n)
    if seed_key:
        d = descripteur_vertical_pour_llm(seed_key)
        if d:
            d["source"] = "seed"
            return d

    # 2. Cache hit ?
    cle = _cle_cache_vertical(metier_n, secteur_n, pays or "")
    cached = await _lire_cache_vertical(cle)
    if cached:
        cached["source"] = "cache"
        return cached

    # 3. Sonnet compose le descripteur
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        seed_examples = [
            {"vertical": k, "label": v["label"],
             "sites_officiels_globaux": v["sites_officiels_globaux"][:6],
             "ton_recommande": v["ton_recommande"][:200],
             "couleurs_typiques": v["couleurs_typiques"]}
            for k, v in list(VERTICALES_METIER.items())[:3]
        ]
        prompt = f"""Tu es un expert en stratégie sectorielle mondiale. Compose un descripteur
métier complet pour le secteur d'activité indiqué.

CONTEXTE :
- Métier déclaré : "{metier_n or '(non précisé)'}"
- Secteur déclaré : "{secteur_n or '(non précisé)'}"
- Pays utilisateur : "{pays or '(non précisé)'}"
- Brief contextuel : "{(brief or '')[:800]}"

EXEMPLES DE DESCRIPTEURS VALIDÉS (pour t'inspirer du format) :
{json.dumps(seed_examples, ensure_ascii=False, indent=2)}

PRODUIS UN DESCRIPTEUR JSON STRICT pour le secteur courant. Règles :

1. `sites_officiels_globaux` : 6-10 régulateurs/organisations MONDIALES du
   secteur (ex: pour aviation → ICAO, IATA, EASA, FAA ; pour télécom → ITU,
   GSMA, BEREC, FCC ; pour mining → ICMM, World Bank, OECD ; pour gaming →
   ESA, PEGI, ESRB, IGDA). PAS de site fantaisiste.

2. `sites_officiels_pays` : 4-8 régulateurs/organismes NATIONAUX du pays
   `{pays or 'US'}` SPÉCIFIQUES au secteur (ex: pour pharma+US → fda.gov,
   nih.gov ; pour finance+UK → fca.org.uk, bankofengland.co.uk).

3. `domaines_expertise` : 5-8 axes de connaissance du secteur (réglementation,
   normes, certifications, processus, outils standards…).

4. `templates_inspirations` : 18-25 documents/visuels TYPIQUES produits
   dans ce secteur (rapports, contrats, brochures, certificats, bilans,
   plans, fiches techniques, etc.).

5. `ton_recommande` : 1-2 phrases sur le registre attendu.

6. `lexique_prefere` : 8-12 mots du jargon professionnel à privilégier.

7. `mots_eviter` : 4-8 mots inappropriés ou cliché à éviter.

8. `couleurs_typiques` : palette représentative (3 couleurs hex avec
   nom usage, ex: "bleu marine #003D82 / vert #006633 / accent or #FFB800").

9. `polices_typiques` : 2-4 familles de polices adaptées au registre.

FORMAT JSON STRICT :
{{
  "vertical": "slug_court_minuscule_underscore",
  "label": "Nom du secteur (français + anglais entre parenthèses)",
  "domaines_expertise": ["...", "..."],
  "sites_officiels_globaux": ["domain.org", "..."],
  "sites_officiels_pays": ["domain.gov.{(pays or 'us').lower()}", "..."],
  "templates_inspirations": ["...", "..."],
  "ton_recommande": "...",
  "lexique_prefere": ["...", "..."],
  "mots_eviter": ["...", "..."],
  "couleurs_typiques": "...",
  "polices_typiques": "..."
}}

Retourne UNIQUEMENT le JSON, sans commentaire."""
        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
            json_attendu=True,
            max_tokens_override=2500,
            utiliser_cache=False,
        )
        try:
            descripteur = json.loads(rep.contenu or "{}")
        except json.JSONDecodeError:
            import re as _re
            m = _re.search(r'\{[\s\S]*\}', rep.contenu or "")
            descripteur = json.loads(m.group()) if m else {}

        # Validation minimale : au moins quelques champs significatifs
        if not (descripteur.get("sites_officiels_globaux") or descripteur.get("templates_inspirations")):
            logger.info(f"[VerticalDyn] Descripteur LLM trop pauvre pour {metier_n}/{secteur_n}/{pays}")
            return None

        descripteur.setdefault("vertical", "custom_dynamique")
        descripteur.setdefault("label", metier_n or secteur_n or "Secteur custom")
        # Fusion sites globaux + pays pour usage unifié
        sites = list(descripteur.get("sites_officiels_globaux") or [])
        sites.extend(descripteur.get("sites_officiels_pays") or [])
        descripteur["sites_officiels_globaux"] = list(dict.fromkeys(sites))[:15]
        descripteur["source"] = "llm_dynamique"

        # Cache pour 7 jours
        await _ecrire_cache_vertical(cle, descripteur)
        logger.info(
            f"[VerticalDyn] Descripteur compose pour {metier_n}/{secteur_n}/{pays} "
            f"({len(descripteur.get('templates_inspirations', []))} templates)"
        )
        return descripteur
    except Exception as e:
        logger.warning(f"[VerticalDyn] Echec composition Sonnet : {e}")
        return None


def construire_bloc_prompt_vertical(
    vertical_key: Optional[str] = None,
    pays: Optional[str] = None,
    descripteur: Optional[dict] = None,
) -> str:
    """
    Bloc texte à injecter dans les prompts orchestrateurs (Designer Pro + G1).

    `descripteur` (optionnel) : descripteur dynamique généré par
    `detecter_vertical_dynamique_llm()`. Si fourni, prime sur `vertical_key`
    qui n'est qu'un raccourci pour les SEED hardcodés.

    PHILOSOPHIE NON-NÉGOCIABLE :
    1. BIBLIOTHÈQUE d'inspirations + garde-fous, JAMAIS une cage.
    2. App MONDIALE : le LLM s'adapte au `pays` user (régulateur national,
       cadre juridique, conventions). Couvre TOUS les secteurs via
       composition LLM dynamique (cf. detecter_vertical_dynamique_llm).
    3. AUCUN article/date/montant hardcodé : recherche web temps réel via
       `recherche_officielle_metier` ou mention "à vérifier".
    """
    if descripteur:
        desc = descripteur
    elif vertical_key:
        desc = descripteur_vertical_pour_llm(vertical_key)
    else:
        return ""
    if not desc:
        return ""
    pays_ctx = f" (pays user : {pays})" if pays else ""
    return f"""
═══════════════════════════════════════════════════
  CONTEXTE MÉTIER — {desc['label']}{pays_ctx}
═══════════════════════════════════════════════════
Le profil utilisateur indique qu'il travaille dans ce secteur. Utilise ces
connaissances comme INSPIRATION + GARDE-FOUS — JAMAIS comme limite.

Si l'utilisateur demande un format/document HORS de la liste ci-dessous,
INVENTE-LE en respectant les conventions du secteur. Le catalogue est une
bibliothèque, pas une cage.

🌍 Domaines d'expertise sectoriels (mondiaux, à adapter au pays user) :
{chr(10).join(f"  - {d}" for d in desc['domaines_expertise'])}

🔗 Sites officiels GLOBAUX pour citer une source (recherche web possible
   via outil dédié — JAMAIS de citation d'article/date/montant inventée) :
{chr(10).join(f"  - {s}" for s in desc['sites_officiels_globaux'])}

📚 Templates fréquents (inspirations universelles, à adapter au pays) :
{chr(10).join(f"  - {t}" for t in desc['templates_inspirations'])}

🗣️ Ton attendu : {desc['ton_recommande']}

✅ Lexique préféré : {', '.join(desc['lexique_prefere'])}
❌ Mots à éviter : {', '.join(desc['mots_eviter'])}

🎨 Codes visuels typiques (Designer Pro) :
   Couleurs : {desc['couleurs_typiques']}
   Polices : {desc['polices_typiques']}

═══ RÈGLES NON-NÉGOCIABLES ═══

1. **Pays user** = adapte les références au cadre juridique national :
   - profil.pays connu → cite régulateur/code/loi du pays + sources officielles
     nationales en plus des sites globaux ci-dessus
   - profil.pays inconnu → reste générique mondial, n'invente AUCUNE
     référence nationale

2. **Aucune fabrication de réference** : si tu cites un article de loi, une
   date, un montant, un taux → c'est SOIT issu d'une recherche web
   officielle (signaler la source), SOIT marqué "à vérifier sur source
   officielle". Tu ne fabriques JAMAIS un numéro d'article ni une date.

3. **Hors catalogue ≠ refus** : si l'user demande quelque chose qui n'est
   PAS dans la liste de templates, INVENTE-le sur la base des conventions
   du secteur. Sois créatif dans le respect des règles métier.
"""
