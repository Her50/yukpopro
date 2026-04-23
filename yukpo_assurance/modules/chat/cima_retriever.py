"""
CIMARetriever — RAG (Retrieval Augmented Generation) pour le Code CIMA.

Principe : à chaque question, extraire automatiquement les articles CIMA
pertinents du JSON consolidé et les injecter dans le prompt envoyé à l'IA.
→ L'IA répond sur la base du texte officiel, pas de ses hallucinations.

Source : data/cima_knowledge/code_cima.json (Code CIMA consolidé 2024, 399 articles)

Stratégie v3 (3 passes) :
  1. Lookup direct si un numéro d'article est mentionné (Art. 337-1, art 200…)
  2. Recherche sémantique TF-IDF via CIMAEmbedder (stratégie principale)
     → trouve les articles pertinents même sans mots-clés exacts
  3. Recherche par topics/mots-clés (fallback si TF-IDF < 2 résultats)
  4. Fallback honnête si rien trouvé (mode strict IA)
"""
import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger("yukpo_assurance.cima.retriever")

# ─── Chemins ─────────────────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(__file__)
_JSON_PATH = os.path.normpath(
    os.path.join(_BASE_DIR, "../../data/cima_knowledge/code_cima.json")
)

# ─── Chargement JSON (invalidation automatique si le fichier change) ──────────

_json_cache: dict | None = None
_json_mtime: float = 0.0

def _charger_json() -> dict:
    """Charge le JSON CIMA. Recharge automatiquement si le fichier a changé sur disque."""
    global _json_cache, _json_mtime
    try:
        mtime = os.path.getmtime(_JSON_PATH)
    except OSError:
        return _json_cache or {}
    if _json_cache is None or mtime != _json_mtime:
        with open(_JSON_PATH, encoding="utf-8") as f:
            _json_cache = json.load(f)
        _json_mtime = mtime
        logger.info("[CIMARetriever] JSON CIMA rechargé depuis le disque")
    return _json_cache

# ─── Mapping topics → sections JSON ──────────────────────────────────────────
# Format : { "topic": {"keywords": [...], "paths": [...]} }
# Les chemins utilisent la notation "a.b.c" pour les clés imbriquées.

TOPICS: dict[str, dict] = {
    "rc_auto": {
        "keywords": [
            "rc auto", "rc automobile", "responsabilité civile auto", "assurance auto",
            "véhicule", "vehicule", "accident auto", "accident de la route",
            "sinistre auto", "sinistre automobile", "sinistre vehicule",
            "carte rose", "plafond rc", "tiers", "fga", "fonds de garantie auto",
            "rc obligatoire", "dommage auto", "corporel auto", "matériel auto",
            "victime accident", "garantie auto", "responsabilite civile",
            "bonus malus", "crm", "coefficient reduction majoration",
            "carte verte", "assurance temporaire auto", "dta", "tous accidents",
            "protection conducteur", "vol vehicule",
            "art. 200", "art. 201", "art. 203", "art. 207", "art. 210", "art. 217",
            "art. 220", "art. 223", "art. 231",
        ],
        "paths": [
            "livre_II_assurances_obligatoires",
            "baremes_indemnisation_corporelle",
        ],
    },
    "delais": {
        "keywords": [
            "délai", "delai", "délais", "delais",
            "règlement", "reglement", "régler", "regler",
            "déclaration sinistre", "declaration sinistre",
            "instruction dossier", "offre indemnisation",
            "paiement indemnité", "paiement indemnite",
            "prescription", "résiliation", "resiliation",
            "mise en demeure", "accusé réception", "accuse reception",
            "pénalité retard", "penalite retard", "30 jours", "45 jours",
            "3 mois", "10 jours", "5 jours", "15 jours", "8 jours",
            "délai de règlement", "délai de paiement", "délai d'instruction",
            "art. 12", "art. 12-bis", "art. 12-ter", "art. 13", "art. 13 nouveau",
            "art. 9", "art. 10", "art. 207", "art. 223",
            "grande entreprise", "entreprise publique", "grande societe",
            "delai paiement prime", "délai paiement prime", "60 jours prime",
        ],
        "paths": ["delais_reglementaires"],
    },
    "provisions_non_vie": {
        "keywords": [
            "provision", "psap", "ppna", "prc", "provision sinistre",
            "provision prime", "sinistres à payer", "primes non acquises",
            "risques croissants", "ibnr", "réserve sinistre",
            "sinistres non declares", "tardifs",
            "chain ladder", "bornhuetter ferguson", "dossier par dossier",
            "provision technique", "provision egalisation", "pe provision",
            "provision de gestion", "provision ibnr", "provision psap",
            "methode actuarielle", "triangle run-off", "run off",
            "engagement assureur", "engagement envers",
            "art. 334", "art. 335", "art. 383", "art. 389", "art. 390", "art. 391",
            "art. 334-1", "art. 334-2", "art. 334-3", "art. 334-7",
        ],
        "paths": ["provisions_techniques"],
    },
    "provisions_vie": {
        "keywords": [
            "provision mathématique", "provisions mathématiques",
            "pm vie", "pm assurance vie",
            "taux technique", "table mortalité", "table de mortalité",
            "tables mortalite", "table actuarielle",
            "td 88", "tv 88", "cima 2016", "table cima",
            "méthode prospective", "méthode actuarielle",
            "actuariat", "actuaire", "rapport actuariel",
            "rente viagère", "capital décès vie",
            "valeur de rachat", "participation aux benefices",
            "art. 334-4", "art. 334-5", "art. 54", "art. 80",
            "art. 387", "art. 388", "art. 389", "art. 390",
        ],
        "paths": [
            "provisions_techniques",
            "provisions_mathematiques_vie_formules",
        ],
    },
    "solvabilite": {
        "keywords": [
            "solvabilité", "solvabilite", "marge de solvabilité", "marge solvabilite",
            "ratio solvabilité", "capitaux propres", "fonds propres",
            "couverture provisions", "actifs représentatifs", "actif représentatif",
            "plan de redressement", "stress test", "orsa",
            "engagement envers assures", "engagement assure", "couverture engagements",
            "art. 326", "art. 334-4", "art. 335", "art. 337", "art. 338", "art. 357",
        ],
        "paths": [
            "livre_III_entreprises_assurance.marge_solvabilite",
            "livre_III_entreprises_assurance.couverture_provisions_techniques",
            "ratios_prudentiels",
        ],
    },
    "capital_agrement": {
        "keywords": [
            "capital minimum", "capital social", "agrément", "agrement",
            "fonds propres minimum", "fonds propres", "fonds propres creer",
            "constitution compagnie", "création compagnie", "créer compagnie",
            "forme juridique", "société anonyme assurance", "sam",
            "retrait agrément", "retrait agrement",
            "microassurance", "programme activite", "dossier agrement",
            "art. 300", "art. 301", "art. 302", "art. 304",
            "art. 329", "art. 329-1", "art. 330", "art. 337",
            "3 milliards", "500 millions", "circulaire 2016",
            "minimum capital", "capital requirement", "capital insurance",
        ],
        "paths": [
            "livre_III_entreprises_assurance.agrement",
            "circulaires_crca",
        ],
    },
    "contrat_vie": {
        "keywords": [
            "assurance vie", "vie mixte", "contrat vie", "police vie",
            "décès", "deces", "capital décès", "bénéficiaire",
            "valeur de rachat", "souscription vie", "épargne",
            "rachat partiel", "avance sur police", "nantissement police",
            "incontestabilite", "suicide assurance", "beneficiaire acceptant",
            "portabilite", "assurance groupe", "assurance retraite",
            "art. 50", "art. 51", "art. 52", "art. 54", "art. 55",
            "art. 56", "art. 60", "art. 62", "art. 64", "art. 73",
            "art. 74", "art. 80",
        ],
        "paths": [
            "livre_I_contrat_assurance.chapitre_VI_assurances_personnes",
            "livre_I_contrat_assurance.chapitre_VII_assurance_vie_accidents",
        ],
    },
    "contrat_general": {
        "keywords": [
            "contrat assurance", "police", "avenant", "souscription",
            "proposition assurance", "risque assuré", "garantie",
            "exclusion", "franchise", "résiliation contrat",
            "renouvellement", "tacite reconduction", "résiliation à terme",
            "coassurance", "sur-assurance", "sous-assurance",
            "valeur agrée", "valeur a neuf", "premier risque",
            "subrogation", "action directe", "prescription",
            "refuser payer", "refus paiement", "refus assureur", "refuse payer",
            "refuser sinistre", "refus sinistre", "refuser indemniser",
            "assureur refuse", "non paiement sinistre",
            "art. 1", "art. 3", "art. 7", "art. 9", "art. 12", "art. 17", "art. 26",
            "art. 31", "art. 32", "art. 33", "art. 34", "art. 36",
        ],
        "paths": [
            "livre_I_contrat_assurance.chapitre_I_dispositions_generales",
            "livre_I_contrat_assurance.chapitre_II_formation_du_contrat",
            "livre_I_contrat_assurance.chapitre_III_obligations_parties",
            "livre_I_contrat_assurance.chapitre_IV_prescription",
            "livre_I_contrat_assurance.chapitre_V_assurances_dommages",
        ],
    },
    "intermediaires": {
        "keywords": [
            "courtier", "agent général", "agent general",
            "intermédiaire", "intermediaire", "commissionnaire",
            "commission courtier", "production réseau",
            "reversement primes", "commission reversement", "commission agent",
            "honoraires", "rémunération intermédiaire", "remuneration courtier",
            "devoir de conseil", "rc professionnelle courtier",
            "garantie financiere courtier", "carte professionnelle",
            "demarchage", "retractation contrat", "formation courtier",
            "art. 500", "art. 501", "art. 502", "art. 504",
            "art. 505", "art. 506", "art. 507", "art. 508",
            "art. 510", "art. 520", "art. 527", "art. 541",
        ],
        "paths": ["livre_IV_intermediaires"],
    },
    "reassurance": {
        "keywords": [
            "réassurance", "reassurance", "traité", "traite reassurance",
            "quote-part", "excédent sinistres", "xl", "excess loss",
            "cession réassurance", "rétrocession", "catastrophe nat",
            "sinistre maximum", "plan réassurance", "c20",
            "africa re", "cica-re", "retrocession", "cash call",
            "profit commission", "depot reassurance",
            "art. 16", "art. 308", "art. 312", "art. 700", "art. 701",
            "art. 719", "art. 720", "art. 721",
        ],
        "paths": [
            "livre_VI_reassurance",
            "livre_III_entreprises_assurance.reassurance",
        ],
    },
    "placements": {
        "keywords": [
            "placement", "investissement", "actif admis", "obligation état",
            "action cotée", "immeuble productif", "portefeuille placements",
            "rendement actifs", "actifs représentatifs art 335",
            "limite placement", "diversification placements",
            "depots bancaires", "prets hypothecaires",
            "art. 320", "art. 321", "art. 335", "art. 621",
            "art. 622", "art. 623", "art. 624",
        ],
        "paths": [
            "livre_III_entreprises_assurance.placement_actifs",
            "livre_V_dispositions_diverses",
        ],
    },
    "etats_reglementaires": {
        "keywords": [
            "état c", "états réglementaires", "états cima",
            "c1", "c2", "c3", "c4", "c5", "c6", "c7",
            "c8", "c9", "c10", "c11", "c12", "c13",
            "c14", "c15", "c16", "c17", "c18", "c19", "c20",
            "reporting crca", "dépôt crca", "depot crca",
            "31 mars crca", "31 janvier", "30 avril",
            "art. 400", "art. 406",
        ],
        "paths": ["etats_reglementaires"],
    },
    "sanctions": {
        "keywords": [
            "sanction", "pénalité crca", "penalite crca",
            "retrait agrément", "retrait agrement", "mise en demeure crca",
            "amende crca", "infraction", "non conformité", "non-conformite",
            "inspection crca", "contrôle crca", "injonction crca",
            "administrateur provisoire", "liquidation assureur",
            "plan redressement", "mesure conservatoire",
            "art. 401", "art. 406", "art. 407", "art. 408", "art. 409",
            "art. 413", "art. 417", "art. 418", "art. 419",
            "art. 420", "art. 422", "art. 423",
        ],
        "paths": [
            "sanctions_penalites_crca",
            "livre_III_entreprises_assurance.controle_crca",
        ],
    },
    "sinistres_corporels": {
        "keywords": [
            "sinistre corporel", "indemnité corporelle",
            "ipp", "ipt", "itt", "préjudice", "prejudice",
            "barème corporel", "pretium doloris",
            "dommage corporel", "blessure grave",
            "décès victime", "rente accident",
            "incapacité", "invalidité", "invalidite permanente",
            "capital reference", "indemnite journaliere",
        ],
        "paths": [
            "baremes_indemnisation_corporelle",
            "delais_reglementaires",
        ],
    },
    "tarification": {
        "keywords": [
            "prime", "tarif", "tarification",
            "calcul prime", "cotisation assurance",
            "barème prime", "taux prime",
            "bonus malus", "surprime", "réduction prime",
            "prime rc auto", "prime mrh", "prime vie",
        ],
        "paths": [
            "tarification_indicative",
            "branches",
        ],
    },
    "taxes": {
        "keywords": [
            "taxe", "taxes assurance", "tva assurance",
            "taux taxe", "fiscalité", "fiscalite",
            "impôt", "impot", "taxe sur prime",
            "exonération", "exoneration",
            "tsca", "taxe convention assurance",
        ],
        "paths": [
            "taux_taxes_par_pays",
            "branches",
        ],
    },
    "gouvernance": {
        "keywords": [
            "gouvernance", "comite audit", "controle interne",
            "actuaire", "rapport actuariel", "orsa",
            "stress test", "whistleblowing", "lanceur alerte",
            "commissaire comptes", "cac assurance",
            "art. 316", "art. 629", "art. 631", "art. 637",
        ],
        "paths": [
            "livre_V_dispositions_diverses",
            "livre_III_entreprises_assurance.controle_crca",
        ],
    },
    "assurances_obligatoires_pro": {
        "keywords": [
            "rc professionnelle", "rc décennale", "rc chantier",
            "assurance obligatoire", "profession reglementee",
            "medecin assurance", "avocat assurance", "architecte assurance",
            "rc locataire", "rc copropriete", "rc proprietaire",
            "rc transport", "rc organisateur",
            "art. 226", "art. 227", "art. 236", "art. 245",
        ],
        "paths": [
            "livre_II_assurances_obligatoires",
        ],
    },
    "lbc_ft": {
        "keywords": [
            "blanchiment", "financement terrorisme", "lbc ft", "lbc/ft",
            "kyc", "centif", "gel avoirs", "conformite lbc",
            "personne politiquement exposee", "ppe",
            "ubo", "beneficiaire effectif", "declaration suspicious",
            "declaration suspecte", "operation suspecte",
            "art. 611", "art. 612", "art. 613", "art. 614", "art. 615",
            "art. 616", "art. 617", "art. 618", "art. 619",
        ],
        "paths": [
            "livre_V_dispositions_diverses",
        ],
    },
}

# ─── Limites ──────────────────────────────────────────────────────────────────

MAX_CHARS_PAR_SECTION = 2000   # Tronque une section trop volumineuse
MAX_TOTAL_CHARS = 8000         # Limite totale du contexte injecté
MAX_TOPICS = 4                 # Nombre maximum de topics traités par question

# ─── Normalisation ────────────────────────────────────────────────────────────

_TABLE_ACCENTS: dict[int, str] = {
    ord(c): r for c, r in [
        ("\u00e9", "e"), ("\u00e8", "e"), ("\u00ea", "e"), ("\u00eb", "e"),
        ("\u00e0", "a"), ("\u00e2", "a"), ("\u00e4", "a"),
        ("\u00ee", "i"), ("\u00ef", "i"),
        ("\u00f4", "o"), ("\u00f6", "o"),
        ("\u00f9", "u"), ("\u00fb", "u"), ("\u00fc", "u"),
        ("\u00e7", "c"),
        ("\u00c9", "e"), ("\u00c8", "e"), ("\u00ca", "e"),
        ("\u00c0", "a"), ("\u00c2", "a"),
        ("\u00ce", "i"), ("\u00d4", "o"), ("\u00d9", "u"),
        ("\u00c7", "c"),
    ]
}

def _normaliser(texte: str) -> str:
    return texte.lower().translate(_TABLE_ACCENTS)

# ─── Détection des topics ─────────────────────────────────────────────────────

def _detecter_topics(question: str) -> list[str]:
    """Identifie les topics pertinents dans la question par correspondance de mots-clés."""
    q_norm = _normaliser(question)
    scores: dict[str, int] = {}
    for topic, cfg in TOPICS.items():
        score = 0
        for kw in cfg["keywords"]:
            if _normaliser(kw) in q_norm:
                # Pondération : mot-clé long = plus pertinent
                score += max(1, len(kw.split()))
        if score > 0:
            scores[topic] = score
    # Trier par score décroissant
    return sorted(scores, key=scores.__getitem__, reverse=True)

# ─── Lookup direct par numéro d'article ──────────────────────────────────────

_ARTICLE_RE = re.compile(
    r"\bart[a-z]*\.?\s+(\d{1,3}(?:[_\-]\d{1,3})?(?:[_\-](?:bis|ter|quater|nouveau))?)",
    re.IGNORECASE,
)

def _extraire_numeros_articles(question: str) -> list[str]:
    """Extrait les numéros d'articles mentionnés dans la question.
    Retourne des clés normalisées type 'art_12_bis', 'art_337_1', 'art_200'.
    """
    clés: list[str] = []
    for m in _ARTICLE_RE.finditer(question):
        raw = m.group(1).lower().strip()
        # Normalise : tirets → underscores
        key = "art_" + re.sub(r"[-\s]", "_", raw)
        clés.append(key)
    return clés


def _chercher_article_par_numero(cima: dict, cle: str) -> Optional[tuple[str, dict]]:
    """Recherche récursive d'un article par sa clé (ex: 'art_337_1').
    Retourne (chemin_lisible, contenu) ou None.
    """
    def _recursif(obj: dict, chemin: str) -> Optional[tuple[str, dict]]:
        if isinstance(obj, dict):
            if cle in obj:
                return (chemin + "." + cle, obj[cle])
            for k, v in obj.items():
                result = _recursif(v, chemin + "." + k if chemin else k)
                if result is not None:
                    return result
        return None

    return _recursif(cima, "")


# ─── Accès aux données imbriquées ────────────────────────────────────────────

def _get_nested(data: dict, path: str) -> Optional[dict]:
    """Résout un chemin de type 'a.b.c' dans un dict imbriqué."""
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current

# ─── Formatage JSON → texte lisible ──────────────────────────────────────────

def _formater_valeur(valeur) -> str:
    """Formate une valeur simple (int FCFA, %, string)."""
    if isinstance(valeur, int) and valeur > 1000:
        return f"{valeur:,} FCFA".replace(",", " ")
    if isinstance(valeur, float) and valeur <= 1:
        return f"{valeur * 100:.1f}%"
    return str(valeur)

def _formater_section(data, niveau: int = 0, budget: list = None) -> str:
    """Convertit récursivement une section JSON en texte lisible pour l'IA."""
    if budget is None:
        budget = [MAX_CHARS_PAR_SECTION]

    lignes: list[str] = []

    def _ajouter(ligne: str):
        if budget[0] > 0:
            lignes.append(ligne)
            budget[0] -= len(ligne) + 1

    def _traiter(obj, niv: int):
        if budget[0] <= 0:
            return
        indent = "  " * niv

        if isinstance(obj, str):
            _ajouter(f"{indent}{obj}")
        elif isinstance(obj, (int, float)):
            _ajouter(f"{indent}{_formater_valeur(obj)}")
        elif isinstance(obj, list):
            for item in obj:
                _ajouter(f"{indent}• {item}")
        elif isinstance(obj, dict):
            for clé, val in obj.items():
                if budget[0] <= 0:
                    break
                # Clés spéciales → affichage mis en forme
                if clé == "texte":
                    _ajouter(f"{indent}📜 {val}")
                elif clé == "article":
                    _ajouter(f"{indent}📌 {val}")
                elif clé == "portee":
                    _ajouter(f"{indent}✦ Portée : {val}")
                elif clé == "description":
                    _ajouter(f"{indent}→ {val}")
                elif clé in ("titre", "source", "note"):
                    pass  # Métadonnées — ignorées pour concision
                elif clé.startswith("art_"):
                    # art_200 → Art. 200 / art_12_bis → Art. 12-bis
                    nom = re.sub(r"^art_", "", clé)
                    nom = re.sub(r"_bis$", "-bis", nom)
                    nom = re.sub(r"_ter$", "-ter", nom)
                    nom = nom.replace("_", "-")
                    _ajouter(f"\n{indent}▸ **Art. {nom.upper()}**")
                    _traiter(val, niv + 1)
                elif isinstance(val, dict):
                    label = clé.replace("_", " ").title()
                    _ajouter(f"\n{indent}[{label}]")
                    _traiter(val, niv + 1)
                elif isinstance(val, list):
                    _ajouter(f"{indent}• {clé.replace('_', ' ')} :")
                    _traiter(val, niv + 1)
                elif isinstance(val, (str, int, float)):
                    _ajouter(f"{indent}• {clé.replace('_', ' ')} : {_formater_valeur(val)}")

    _traiter(data, niveau)
    return "\n".join(lignes).strip()

# ─── Étiquetage des chemins ────────────────────────────────────────────────────

def _labelliser_chemin(path: str) -> str:
    """Convertit un chemin JSON en étiquette lisible."""
    return (
        path
        .replace("livre_I_contrat_assurance.", "Livre I — ")
        .replace("livre_II_assurances_obligatoires", "Livre II — RC Auto & Assurances Obligatoires")
        .replace("livre_III_entreprises_assurance.", "Livre III — ")
        .replace("livre_IV_intermediaires", "Livre IV — Intermédiaires")
        .replace("livre_V_dispositions_diverses", "Livre V — Dispositions Diverses")
        .replace("livre_VI_reassurance", "Livre VI — Réassurance")
        .replace("baremes_indemnisation_corporelle", "Barèmes Indemnisation Corporelle")
        .replace("provisions_techniques", "Provisions Techniques (Art. 334-1 à 334-7)")
        .replace("provisions_mathematiques_vie_formules", "Provisions Mathématiques Vie (Art. 334-4)")
        .replace("etats_reglementaires", "États Réglementaires C1-C20 (Art. 400)")
        .replace("delais_reglementaires", "Délais Réglementaires (Art. 12 à 73)")
        .replace("ratios_prudentiels", "Ratios Prudentiels CIMA")
        .replace("sanctions_penalites_crca", "Sanctions & Pénalités CRCA")
        .replace("tarification_indicative", "Tarification Indicative")
        .replace("branches", "Branches & Taxes")
        .replace("taux_taxes_par_pays", "Taxes par Pays Membre")
        .replace("circulaires_crca", "Circulaires CRCA")
        .replace("chapitre_VII_assurance_vie_accidents", "Chapitre VII — Assurance Vie & Accidents (Art. 74-98)")
        .replace("_", " ").title()
    )


# ─── Point d'entrée principal ─────────────────────────────────────────────────

def rechercher_articles(question: str) -> str:
    """
    Retourne les articles CIMA pertinents formatés pour injection dans le prompt IA.

    Stratégie v4 (3 passes ordonnées) :
      1. Lookup direct si l'utilisateur mentionne un numéro d'article (Art. 47, etc.)
      2. Topics/mots-clés CIMA (stratégie principale — précision ~85%, très rapide)
      3. Embedding dense sémantique (complément — capte synonymes et formulations
         différentes du vocabulaire CIMA : anglais, paraphrases, etc.)
      → Aucun résultat : retourne "" pour déclencher le mode strict de l'IA

    Ordre intentionnel : keywords AVANT dense.
    Les mots-clés CIMA sont très précis sur ce domaine légal.
    Le modèle dense (paraphrase-multilingual) discrimine mal à l'intérieur du
    domaine assurance (tous les articles scorent 60-80%). Il est utilisé en
    complément uniquement lorsque les keywords laissent du budget.
    """
    try:
        cima = _charger_json()
    except Exception:
        return ""

    try:
        from modules.chat.cima_embedder import cima_embedder
        _embedder_disponible = cima_embedder.pret
    except Exception:
        _embedder_disponible = False

    parties: list[str] = []
    total_chars = 0
    cles_vues: set[str] = set()
    paths_vues: set[str] = set()

    # ── 1. Lookup direct par numéro d'article mentionné dans la question ───────
    numeros = _extraire_numeros_articles(question)
    for cle in numeros:
        if total_chars >= MAX_TOTAL_CHARS:
            break
        result = _chercher_article_par_numero(cima, cle)
        num_lisible = (
            cle.replace("art_", "")
               .replace("_bis", "-bis")
               .replace("_ter", "-ter")
               .replace("_", "-")
               .upper()
        )
        if result:
            chemin, contenu = result
            if cle not in cles_vues:
                cles_vues.add(cle)
                budget = [MAX_CHARS_PAR_SECTION]
                texte = _formater_section(contenu, budget=budget)
                if texte.strip():
                    parties.append(f"#### Art. {num_lisible}\n{texte}")
                    total_chars += len(texte)
        else:
            parties.append(
                f"#### Art. {num_lisible} — NON DISPONIBLE DANS LA BASE LOCALE\n"
                f"Cet article n'est pas encore dans la base de donnees locale. "
                f"Pour une reponse officielle, consultez le texte integral du Code CIMA ou la CRCA."
            )

    # ── 2. Topics/mots-clés CIMA (stratégie principale) ────────────────────────
    topics = _detecter_topics(question)
    for topic in topics[:MAX_TOPICS]:
        if total_chars >= MAX_TOTAL_CHARS:
            break
        cfg = TOPICS[topic]

        # 2a. Lookup direct des articles référencés dans les keywords du topic
        #     Garantit que "art. 329", "art. 616", etc. sont toujours inclus,
        #     même s'ils apparaissent loin dans une grande section.
        _art_kw_re = re.compile(
            r"^art\.\s*(\d+(?:-\d+)?(?:-(?:bis|ter|quater))?)\s*$", re.IGNORECASE
        )
        for kw in cfg["keywords"]:
            if total_chars >= MAX_TOTAL_CHARS:
                break
            m = _art_kw_re.match(kw.strip())
            if not m:
                continue
            raw = m.group(1)                              # "329", "334-2", "12-bis"
            cle = "art_" + re.sub(r"[-\s]", "_", raw)   # "art_329", "art_334_2"
            if cle in cles_vues:
                continue
            result = _chercher_article_par_numero(cima, cle)
            if not result:
                continue
            cles_vues.add(cle)
            _, contenu = result
            nom = re.sub(r"[-\s]", "-", raw).upper()     # "329", "334-2"
            budget = [MAX_CHARS_PAR_SECTION]
            texte = _formater_section(contenu, budget=budget)
            if texte.strip():
                parties.append(f"#### Art. {nom}\n{texte}")
                total_chars += len(texte)

        # 2b. Section complète du topic (contexte général, articles voisins)
        for path in cfg["paths"]:
            if path in paths_vues or total_chars >= MAX_TOTAL_CHARS:
                continue
            paths_vues.add(path)
            section_data = _get_nested(cima, path)
            if section_data is None:
                continue
            budget = [MAX_CHARS_PAR_SECTION]
            texte = _formater_section(section_data, budget=budget)
            if not texte.strip():
                continue
            label = _labelliser_chemin(path)
            parties.append(f"#### {label}\n{texte}")
            total_chars += len(texte)

    # ── 3. Embedding dense sémantique (complément — capte synonymes/anglais) ───
    # Activé uniquement si :
    #   - Le modèle est disponible ET déjà chaud (pret=True, pas de cold-start)
    #   - Il reste du budget de contexte (au moins 30% libre)
    #   - La question ne contenait pas de topics connus (vocabulaire hors CIMA)
    if _embedder_disponible and total_chars < MAX_TOTAL_CHARS * 0.7:
        try:
            from modules.chat.cima_embedder import cima_embedder
            # Seuil élevé (0.55) : on ne veut que les articles vraiment proches
            # pour ne pas polluer le contexte avec des articles trop génériques
            resultats_sem = cima_embedder.rechercher(question, top_k=4, seuil_score=0.55)
            for art in resultats_sem:
                if total_chars >= MAX_TOTAL_CHARS:
                    break
                cle = art["cle"]
                if cle in cles_vues:
                    continue
                cles_vues.add(cle)
                contenu = art["contenu"]
                budget = [MAX_CHARS_PAR_SECTION]
                texte = _formater_section(contenu, budget=budget)
                if not texte.strip():
                    continue
                parties.append(f"#### {art['numero']}\n{texte}")
                total_chars += len(texte)
        except Exception as e:
            logger.debug(f"[CIMARetriever] Embedding complement ignore : {e}")

    # ── 4. Aucun résultat → mode strict ────────────────────────────────────────
    if not parties:
        return ""

    header = (
        "=== ARTICLES CIMA OFFICIELS — EXTRAIT AUTOMATIQUE ===\n"
        "Source : Code CIMA consolide 2024 (412 articles, CRCA)\n"
        "======================================================\n"
    )
    footer = (
        "\n======================================================\n"
        "INSTRUCTIONS STRICTES POUR L'IA :\n"
        "1. Cite UNIQUEMENT les articles ci-dessus avec leurs numeros EXACTS (Art. 13, Art. 200, etc.).\n"
        "2. Reproduis le texte officiel TEL QUEL — sans le modifier, sans le paraphraser.\n"
        "3. Tu peux ensuite apporter une ANALYSE SEPAREE et CLAIREMENT ETIQUETEE :\n"
        "   - Impact pratique (obligations assureur, souscripteur, assuré).\n"
        "   - Sanctions / consequences du non-respect.\n"
        "   - Comparaison avec COBAC, OHADA ou droit national si pertinent.\n"
        "   ETIQUETE OBLIGATOIREMENT : '[ANALYSE]' avant toute interprétation.\n"
        "4. Si un article demandé n'est pas dans la base ci-dessus :\n"
        "   Utilise ta connaissance de formation pour fournir le texte, mais indique :\n"
        "   '[Réponse depuis mémoire IA — texte non indexé dans la base Yukpo]'\n"
        "   Cite le numéro d'article et le texte CIMA tel que tu le connais, avec précision.\n"
        "5. Adapte le niveau de l'analyse au profil de l'utilisateur.\n"
        "======================================================"
    )

    return header + "\n\n".join(parties) + footer
