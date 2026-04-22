"""
YukpoPlatform — Configuration multi-secteur d'activité
Architecture plugin : chaque secteur déclare ses modules, labels et permissions.
Scalable : pour ajouter un nouveau secteur, appeler enregistrer_secteur() depuis
n'importe quel fichier avant le démarrage de l'application.

Secteurs = secteurs d'activité économique (assurance, banque, industrie, hôpital…),
           pas des régions géographiques.
"""
from __future__ import annotations

from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# Modules universels (présents dans TOUS les secteurs)
# ─────────────────────────────────────────────────────────────

MODULES_UNIVERSELS: List[str] = [
    "chat",           # Copilote IA générique
    "rh",             # Paie OHADA, congés, évaluations, recrutement
    "collaboration",  # Documents partagés, workflows approbation
    "analytics",      # Tableaux de bord et indicateurs
    "reunions",       # Gestion réunions, transcription, PV
    "documents",      # Génération Word/PDF/Excel
    "audit",          # Piste d'audit et journalisation
    "whatsapp",       # Chatbot WhatsApp clients
    "paiement",       # Paiement Mobile Money
    "agenda",         # Agenda et rappels employés ← NOUVEAU
    "community_manager",  # Community Manager IA ← NOUVEAU
    "trends",             # Veille marché et tendances ← NOUVEAU
]

# Labels universels (surchargeables par secteur)
LABELS_UNIVERSELS: Dict[str, str] = {
    "chat":              "Copilote IA",
    "rh":                "Ressources Humaines",
    "collaboration":     "Collaboration",
    "analytics":         "Analytics & Rapports",
    "reunions":          "Réunions",
    "documents":         "Documents",
    "audit":             "Audit Trail",
    "whatsapp":          "WhatsApp Clients",
    "paiement":          "Paiements",
    "agenda":            "Agenda & Tâches",
    "community_manager": "Community Manager",
    "trends":            "Veille & Tendances",
    "commercial":        "Commercial & Pipeline",
}


# ─────────────────────────────────────────────────────────────
# Registre des secteurs (structure plugin)
# ─────────────────────────────────────────────────────────────

# Chaque entrée du registre :
# {
#   "label": str,                   # Nom affiché
#   "reglementation": str,          # Cadre réglementaire principal
#   "icon": str,                    # Emoji ou code icône
#   "couleur": str,                 # Couleur principale hex
#   "modules": List[str],           # Modules spécifiques + universels auto-ajoutés
#   "nav_labels": Dict[str, str],   # Surcharge des labels pour ce secteur
#   "permissions_supplementaires": List[str],  # Permissions métier spécifiques
#   "kpis_principaux": List[str],   # Indicateurs clés de performance
# }

SECTEURS: Dict[str, dict] = {}


def enregistrer_secteur(code: str, config: dict) -> None:
    """
    Enregistre un nouveau secteur dans la plateforme.
    Appelable depuis n'importe quel module ou plugin externe.
    Les MODULES_UNIVERSELS sont automatiquement ajoutés si absents.
    """
    modules = list(config.get("modules", []))
    for m in MODULES_UNIVERSELS:
        if m not in modules:
            modules.append(m)
    config["modules"] = modules
    SECTEURS[code] = config


# ─────────────────────────────────────────────────────────────
# Déclaration des secteurs built-in
# ─────────────────────────────────────────────────────────────

# ── Assurances (CIMA) ──────────────────────────────────────────────────────────
enregistrer_secteur("assurance", {
    "label":          "Compagnie d'assurance (CIMA)",
    "reglementation": "Code CIMA — CRCA",
    "icon":           "🛡️",
    "couleur":        "#1e3a8a",
    "modules": [
        "sinistres", "cima", "souscription", "comptabilite",
        "commercial", "courtiers", "contrats_clients",
    ],
    "nav_labels": {
        "sinistres":          "Sinistres",
        "cima":               "Conformité CIMA",
        "souscription":       "Souscription",
        "comptabilite":       "Comptabilité OHADA/PCSA",
        "commercial":         "Commercial & Pipeline",
        "courtiers":          "Courtiers & Agents",
        "contrats_clients":   "Contrats Clients PDF",
        "community_manager":  "CM Assurance",
        "trends":             "Veille CIMA & Marché",
    },
    "permissions_supplementaires": [
        "cima:read", "cima:write",
        "sinistres:declare", "sinistres:approve",
        "courtiers:read", "courtiers:write",
        "contrats:generate", "contrats:send",
        "whatsapp:manage",
        "paiement:read", "paiement:write",
        "commercial:read", "commercial:write",
    ],
    "kpis_principaux": [
        "ratio_sinistres", "marge_solvabilite", "taux_recouvrement_primes",
        "delai_moyen_reglement_sinistres", "portefeuille_polices_actives",
    ],
})

# ── Banque ─────────────────────────────────────────────────────────────────────
enregistrer_secteur("banque", {
    "label":          "Établissement bancaire",
    "reglementation": "COBAC — BEAC/BCEAO",
    "icon":           "🏦",
    "couleur":        "#0f766e",
    "modules": [
        "credits", "depots", "virements", "kyc",
        "conformite_cobac", "comptabilite", "commercial",
    ],
    "nav_labels": {
        "credits":          "Crédits & Prêts",
        "depots":           "Dépôts & Épargne",
        "virements":        "Virements & Transferts",
        "kyc":              "KYC & Conformité client",
        "conformite_cobac": "Conformité COBAC",
        "commercial":       "Développement commercial",
        "trends":           "Veille bancaire & Fintech",
    },
    "permissions_supplementaires": [
        "credits:read", "credits:write", "credits:approve",
        "depots:read", "depots:write",
        "virements:read", "virements:write",
        "kyc:read", "kyc:write",
        "cobac:read",
    ],
    "kpis_principaux": [
        "ratio_solvabilite_cobac", "npl_ratio", "taux_liquidite",
        "encours_credits", "depots_total",
    ],
})

# ── Microfinance ───────────────────────────────────────────────────────────────
enregistrer_secteur("microfinance", {
    "label":          "Institution de microfinance (IMF)",
    "reglementation": "COBAC / Réglementation nationale IMF",
    "icon":           "🌱",
    "couleur":        "#15803d",
    "modules": [
        "epargne", "credits", "caisses", "comptabilite", "commercial",
    ],
    "nav_labels": {
        "epargne":  "Épargne & Tontines",
        "credits":  "Micro-crédits",
        "caisses":  "Gestion des caisses",
        "trends":   "Tendances micro-finance",
    },
    "permissions_supplementaires": [
        "epargne:read", "epargne:write",
        "credits:read", "credits:write",
        "caisses:read", "caisses:write",
    ],
    "kpis_principaux": ["portefeuille_credits", "taux_remboursement", "epargne_total", "nombre_membres"],
})

# ── Immobilier ─────────────────────────────────────────────────────────────────
enregistrer_secteur("immobilier", {
    "label":          "Agence / Promoteur immobilier",
    "reglementation": "Code foncier national",
    "icon":           "🏢",
    "couleur":        "#92400e",
    "modules": [
        "biens", "locations", "ventes", "syndic", "comptabilite", "commercial",
    ],
    "nav_labels": {
        "biens":     "Portefeuille biens",
        "locations": "Locations & Baux",
        "ventes":    "Transactions immobilières",
        "syndic":    "Syndic de copropriété",
        "trends":    "Tendances immobilières",
    },
    "permissions_supplementaires": [
        "biens:read", "biens:write",
        "locations:read", "locations:write",
        "ventes:read", "ventes:write",
    ],
    "kpis_principaux": ["taux_occupation", "chiffre_affaires", "biens_disponibles", "transactions_mois"],
})

# ── Santé ──────────────────────────────────────────────────────────────────────
enregistrer_secteur("sante", {
    "label":          "Établissement de santé / Clinique",
    "reglementation": "Ministère de la Santé",
    "icon":           "🏥",
    "couleur":        "#0e7490",
    "modules": [
        "patients", "consultations", "facturation", "pharmacie",
        "comptabilite", "commercial",
    ],
    "nav_labels": {
        "patients":      "Patients & Dossiers médicaux",
        "consultations": "Consultations & Ordonnances",
        "facturation":   "Facturation & Assurances",
        "pharmacie":     "Pharmacie & Stocks",
        "trends":        "Veille épidémiologique",
    },
    "permissions_supplementaires": [
        "patients:read", "patients:write",
        "consultations:read", "consultations:write",
        "facturation:read", "facturation:write",
        "pharmacie:read",
    ],
    "kpis_principaux": ["patients_jour", "taux_occupation_lits", "recettes_jour", "stocks_pharmacie"],
})

# ── École / Université ─────────────────────────────────────────────────────────
enregistrer_secteur("ecole", {
    "label":          "École / Université / Centre de formation",
    "reglementation": "Ministère de l'Éducation / Enseignement supérieur",
    "icon":           "🎓",
    "couleur":        "#7c3aed",
    "modules": [
        "eleves", "notes", "bulletins", "paiements_scolarite",
        "comptabilite", "commercial",
    ],
    "nav_labels": {
        "eleves":              "Élèves & Étudiants",
        "notes":               "Notes & Évaluations",
        "bulletins":           "Bulletins & Palmarès",
        "paiements_scolarite": "Scolarités & Paiements",
        "trends":              "Tendances éducatives",
    },
    "permissions_supplementaires": [
        "eleves:read", "eleves:write",
        "notes:read", "notes:write",
        "bulletins:generate",
        "scolarite:read", "scolarite:write",
    ],
    "kpis_principaux": ["effectif_total", "taux_reussite", "paiements_scolarite_taux", "inscriptions_mois"],
})

# ── Transport & Logistique ─────────────────────────────────────────────────────
enregistrer_secteur("transport", {
    "label":          "Transport & Logistique",
    "reglementation": "Code de la route / Réglementation transport",
    "icon":           "🚛",
    "couleur":        "#b45309",
    "modules": [
        "flotte", "missions", "maintenance", "conducteurs",
        "comptabilite", "commercial",
    ],
    "nav_labels": {
        "flotte":      "Flotte de véhicules",
        "missions":    "Missions & Tournées",
        "maintenance": "Maintenance & Entretien",
        "conducteurs": "Conducteurs & Chauffeurs",
        "trends":      "Tendances logistiques",
    },
    "permissions_supplementaires": [
        "flotte:read", "flotte:write",
        "missions:read", "missions:write",
    ],
    "kpis_principaux": ["vehicules_actifs", "missions_mois", "km_parcourus", "couts_carburant"],
})

# ── Cabinet comptable & Audit ──────────────────────────────────────────────────
enregistrer_secteur("cabinet_comptable", {
    "label":          "Cabinet comptable & d'audit",
    "reglementation": "Ordre des Experts-Comptables / OHADA",
    "icon":           "📊",
    "couleur":        "#0f172a",
    "modules": [
        "dossiers_clients", "comptabilite", "audit_externe",
        "declarations_fiscales", "commercial",
    ],
    "nav_labels": {
        "dossiers_clients":      "Dossiers clients",
        "audit_externe":         "Missions d'audit",
        "declarations_fiscales": "Déclarations fiscales",
        "trends":                "Veille fiscale & OHADA",
    },
    "permissions_supplementaires": [
        "dossiers_clients:read", "dossiers_clients:write",
        "audit_externe:read", "audit_externe:write",
        "fiscal:read", "fiscal:write",
    ],
    "kpis_principaux": ["clients_actifs", "dossiers_en_cours", "ca_missions", "echeances_fiscales"],
})

# ── Industrie & Manufacturing ──────────────────────────────────────────────────
enregistrer_secteur("industrie", {
    "label":          "Industrie & Manufacturing",
    "reglementation": "Code du travail / Normes ISO",
    "icon":           "🏭",
    "couleur":        "#374151",
    "modules": [
        "production", "stocks", "qualite", "maintenance_ind",
        "comptabilite", "commercial",
    ],
    "nav_labels": {
        "production":     "Production & Planning",
        "stocks":         "Stocks & Inventaires",
        "qualite":        "Contrôle Qualité",
        "maintenance_ind":"Maintenance industrielle",
        "trends":         "Tendances industrielles",
    },
    "permissions_supplementaires": [
        "production:read", "production:write",
        "stocks:read", "stocks:write",
        "qualite:read",
    ],
    "kpis_principaux": ["taux_production", "taux_rejet", "stock_matiere", "machines_actives"],
})

# ── Commerce & Distribution ────────────────────────────────────────────────────
enregistrer_secteur("commerce", {
    "label":          "Commerce & Distribution",
    "reglementation": "Code de commerce",
    "icon":           "🛒",
    "couleur":        "#dc2626",
    "modules": [
        "produits", "ventes_commerce", "stocks_commerce",
        "clients_commerce", "comptabilite", "commercial",
    ],
    "nav_labels": {
        "produits":         "Catalogue produits",
        "ventes_commerce":  "Ventes & Commandes",
        "stocks_commerce":  "Stock & Approvisionnement",
        "clients_commerce": "CRM Clients",
        "trends":           "Tendances commerciales",
    },
    "permissions_supplementaires": [
        "produits:read", "produits:write",
        "ventes_commerce:read", "ventes_commerce:write",
    ],
    "kpis_principaux": ["ca_jour", "nb_ventes", "panier_moyen", "stock_critique"],
})

# ── ONG / Association ──────────────────────────────────────────────────────────
enregistrer_secteur("ong", {
    "label":          "ONG / Association / Fondation",
    "reglementation": "Loi sur les associations",
    "icon":           "🤝",
    "couleur":        "#059669",
    "modules": [
        "beneficiaires", "projets", "dons", "rapports_bailleurs",
        "comptabilite", "commercial",
    ],
    "nav_labels": {
        "beneficiaires":   "Bénéficiaires",
        "projets":         "Projets & Programmes",
        "dons":            "Dons & Subventions",
        "rapports_bailleurs": "Rapports bailleurs",
        "trends":          "Tendances sociales",
    },
    "permissions_supplementaires": [
        "projets:read", "projets:write",
        "dons:read",
        "rapports_bailleurs:generate",
    ],
    "kpis_principaux": ["beneficiaires_actifs", "projets_en_cours", "budget_restant", "taux_execution"],
})

# ── Hôtellerie & Restauration ──────────────────────────────────────────────────
enregistrer_secteur("hotellerie", {
    "label":          "Hôtellerie & Restauration",
    "reglementation": "Code du tourisme / Hygiène HACCP",
    "icon":           "🏨",
    "couleur":        "#d97706",
    "modules": [
        "reservations", "chambres", "restaurant", "spa",
        "comptabilite", "commercial",
    ],
    "nav_labels": {
        "reservations": "Réservations",
        "chambres":     "Chambres & Disponibilités",
        "restaurant":   "Restaurant & Bar",
        "trends":       "Tendances tourisme",
    },
    "permissions_supplementaires": [
        "reservations:read", "reservations:write",
        "chambres:read", "chambres:write",
    ],
    "kpis_principaux": ["taux_occupation", "revpar", "adr", "satisfaction_client"],
})


# ─────────────────────────────────────────────────────────────
# Permissions de base communes
# ─────────────────────────────────────────────────────────────

PERMISSIONS_BASE: Dict[str, set] = {
    "agent":   {"chat", "documents:read", "rh:read", "agenda:read", "agenda:write"},
    "manager": {
        "chat", "documents", "rh:read", "rh:approve",
        "analytics:read", "collaboration:read", "collaboration:write",
        "agenda:read", "agenda:write", "agenda:admin",
        "commercial:read", "commercial:write",
        "community_manager:read", "trends:read",
    },
    "daf": {
        "chat", "documents", "comptabilite", "rh:read", "rh:paie",
        "analytics", "collaboration:read", "collaboration:write",
        "agenda:read", "agenda:write",
        "commercial:read",
        "paiement:read",
        "trends:read",
    },
    "dg": {"*"},
    "admin": {"*"},
}


# ─────────────────────────────────────────────────────────────
# API Publique
# ─────────────────────────────────────────────────────────────

def get_secteur(code: str) -> Optional[dict]:
    """Retourne la config d'un secteur, ou None s'il n'existe pas."""
    return SECTEURS.get(code)


def get_secteur_strict(code: str) -> dict:
    """Retourne la config d'un secteur ou lève ValueError."""
    s = SECTEURS.get(code)
    if s is None:
        raise ValueError(f"Secteur '{code}' inconnu. Valides : {list(SECTEURS)}")
    return s


def modules_actifs(secteur_code: str) -> List[str]:
    """Retourne la liste des modules actifs pour un secteur."""
    return SECTEURS.get(secteur_code, {}).get("modules", list(MODULES_UNIVERSELS))


def secteur_autorise_module(secteur_code: str, module: str) -> bool:
    """Vérifie qu'un module est disponible pour un secteur donné."""
    return module in modules_actifs(secteur_code)


def label_module(secteur_code: str, module: str) -> str:
    """Retourne le libellé personnalisé d'un module pour un secteur."""
    secteur = SECTEURS.get(secteur_code, {})
    nav = secteur.get("nav_labels", {})
    if module in nav:
        return nav[module]
    return LABELS_UNIVERSELS.get(module, module.replace("_", " ").capitalize())


def kpis_secteur(secteur_code: str) -> List[str]:
    """Retourne les KPIs principaux d'un secteur."""
    return SECTEURS.get(secteur_code, {}).get("kpis_principaux", [])


def lister_secteurs() -> List[Dict]:
    """Retourne la liste simplifiée de tous les secteurs enregistrés."""
    return [
        {
            "code": code,
            "label": info["label"],
            "reglementation": info.get("reglementation", ""),
            "icon": info.get("icon", ""),
            "couleur": info.get("couleur", "#000000"),
            "nb_modules": len(info.get("modules", [])),
        }
        for code, info in SECTEURS.items()
    ]
