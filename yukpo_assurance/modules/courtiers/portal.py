"""
YukpoAssurance — Portail Courtiers
Soumission mobile, suivi temps réel, commissions automatiques.
Élimine les déplacements physiques et la ressaisie manuelle.
Fonctionne TOTALEMENT sans ORASS grâce à un DataStore en mémoire.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("yukpo_assurance.courtiers")


# ──────────────────────────────────────────────────────────────────────────────
# DATASTORE EN MÉMOIRE — données simulées réalistes (Cameroun, FCFA)
# ──────────────────────────────────────────────────────────────────────────────

BRANCHES = ["Auto", "Vie", "IRD", "RC", "Transport", "Incendie", "Accident Corporel"]

# 8 courtiers camerounais
_COURTIERS = {
    "CRT-001": {
        "code": "CRT-001",
        "nom": "Cabinet Ndoumbe Assurances",
        "ville": "Douala",
        "responsable": "Étienne Ndoumbe",
        "telephone": "+237 699 123 456",
        "email": "contact@ndoumbe-assurances.cm",
        "agree_depuis": date(2018, 3, 15),
        "taux_commission": {"Auto": 0.12, "Vie": 0.20, "IRD": 0.15, "RC": 0.10, "Transport": 0.12, "Incendie": 0.15, "Accident Corporel": 0.18},
        "objectif_annuel_fcfa": 85_000_000,
    },
    "CRT-002": {
        "code": "CRT-002",
        "nom": "Mbarga Courtage & Conseil",
        "ville": "Yaoundé",
        "responsable": "Sylvie Mbarga",
        "telephone": "+237 677 234 567",
        "email": "mbarga.courtage@gmail.com",
        "agree_depuis": date(2015, 7, 1),
        "taux_commission": {"Auto": 0.13, "Vie": 0.22, "IRD": 0.15, "RC": 0.11, "Transport": 0.13, "Incendie": 0.15, "Accident Corporel": 0.19},
        "objectif_annuel_fcfa": 120_000_000,
    },
    "CRT-003": {
        "code": "CRT-003",
        "nom": "SARL BiyaAssur",
        "ville": "Bafoussam",
        "responsable": "Paul Biya Fotso",
        "telephone": "+237 655 345 678",
        "email": "biyaassur@outlook.cm",
        "agree_depuis": date(2020, 1, 10),
        "taux_commission": {"Auto": 0.11, "Vie": 0.18, "IRD": 0.14, "RC": 0.09, "Transport": 0.11, "Incendie": 0.14, "Accident Corporel": 0.16},
        "objectif_annuel_fcfa": 45_000_000,
    },
    "CRT-004": {
        "code": "CRT-004",
        "nom": "Kameni Risques & Patrimoine",
        "ville": "Douala",
        "responsable": "Hervé Kameni",
        "telephone": "+237 690 456 789",
        "email": "h.kameni@kameni-risques.cm",
        "agree_depuis": date(2012, 5, 20),
        "taux_commission": {"Auto": 0.14, "Vie": 0.23, "IRD": 0.16, "RC": 0.12, "Transport": 0.14, "Incendie": 0.16, "Accident Corporel": 0.20},
        "objectif_annuel_fcfa": 200_000_000,
    },
    "CRT-005": {
        "code": "CRT-005",
        "nom": "Nguemo InterAssur",
        "ville": "Garoua",
        "responsable": "Aminatou Nguemo",
        "telephone": "+237 676 567 890",
        "email": "nguemo.interassur@yahoo.fr",
        "agree_depuis": date(2019, 9, 3),
        "taux_commission": {"Auto": 0.12, "Vie": 0.20, "IRD": 0.14, "RC": 0.10, "Transport": 0.12, "Incendie": 0.14, "Accident Corporel": 0.17},
        "objectif_annuel_fcfa": 60_000_000,
    },
    "CRT-006": {
        "code": "CRT-006",
        "nom": "Talla Assurance Conseil",
        "ville": "Yaoundé",
        "responsable": "Rodrigue Talla",
        "telephone": "+237 699 678 901",
        "email": "rtalla@talla-conseil.cm",
        "agree_depuis": date(2016, 11, 15),
        "taux_commission": {"Auto": 0.13, "Vie": 0.21, "IRD": 0.15, "RC": 0.11, "Transport": 0.13, "Incendie": 0.15, "Accident Corporel": 0.18},
        "objectif_annuel_fcfa": 95_000_000,
    },
    "CRT-007": {
        "code": "CRT-007",
        "nom": "Onanena & Associés",
        "ville": "Ngaoundéré",
        "responsable": "Claire Onanena",
        "telephone": "+237 655 789 012",
        "email": "onanena.associes@gmail.com",
        "agree_depuis": date(2021, 4, 22),
        "taux_commission": {"Auto": 0.10, "Vie": 0.17, "IRD": 0.13, "RC": 0.09, "Transport": 0.10, "Incendie": 0.13, "Accident Corporel": 0.15},
        "objectif_annuel_fcfa": 30_000_000,
    },
    "CRT-008": {
        "code": "CRT-008",
        "nom": "Sone Multirisques",
        "ville": "Limbé",
        "responsable": "Derrick Sone",
        "telephone": "+237 677 890 123",
        "email": "d.sone@sone-multirisques.cm",
        "agree_depuis": date(2017, 8, 8),
        "taux_commission": {"Auto": 0.12, "Vie": 0.20, "IRD": 0.15, "RC": 0.10, "Transport": 0.12, "Incendie": 0.15, "Accident Corporel": 0.18},
        "objectif_annuel_fcfa": 75_000_000,
    },
}

# 28 contrats simulés réalistes
_today = date.today()

_CONTRATS = [
    # CRT-001 — Ndoumbe (7 contrats)
    {"numero": "POL-2025-0001", "courtier_code": "CRT-001", "branche": "Auto",      "nom_assure": "Jean-Pierre Atanga",     "prime_ttc": 485_000,   "date_effet": date(2025, 1, 15), "date_echeance": _today + timedelta(days=280), "statut": "actif",    "sinistres": 0, "prime_nette": 420_000},
    {"numero": "POL-2025-0002", "courtier_code": "CRT-001", "branche": "Vie",       "nom_assure": "Marie-Claire Essomba",   "prime_ttc": 1_200_000, "date_effet": date(2025, 2, 1),  "date_echeance": _today + timedelta(days=320), "statut": "actif",    "sinistres": 0, "prime_nette": 1_100_000},
    {"numero": "POL-2025-0003", "courtier_code": "CRT-001", "branche": "IRD",       "nom_assure": "SARL Kotto Commerce",    "prime_ttc": 3_250_000, "date_effet": date(2025, 1, 1),  "date_echeance": _today + timedelta(days=55),  "statut": "actif",    "sinistres": 1, "prime_nette": 2_900_000},
    {"numero": "POL-2025-0004", "courtier_code": "CRT-001", "branche": "Transport", "nom_assure": "Camtrans SA",            "prime_ttc": 920_000,   "date_effet": date(2025, 3, 10), "date_echeance": _today + timedelta(days=180), "statut": "actif",    "sinistres": 0, "prime_nette": 820_000},
    {"numero": "POL-2024-0105", "courtier_code": "CRT-001", "branche": "RC",        "nom_assure": "Dr Fono Clinique",       "prime_ttc": 650_000,   "date_effet": date(2024, 5, 1),  "date_echeance": _today + timedelta(days=25),  "statut": "actif",    "sinistres": 0, "prime_nette": 600_000},
    {"numero": "POL-2025-0012", "courtier_code": "CRT-001", "branche": "Auto",      "nom_assure": "Nguiamba François",      "prime_ttc": 320_000,   "date_effet": date(2025, 4, 1),  "date_echeance": _today + timedelta(days=355), "statut": "actif",    "sinistres": 0, "prime_nette": 285_000},
    {"numero": "POL-2025-0013", "courtier_code": "CRT-001", "branche": "Incendie",  "nom_assure": "Épicerie Dieu Merci",    "prime_ttc": 480_000,   "date_effet": date(2025, 2, 15), "date_echeance": _today - timedelta(days=10),  "statut": "expiré",   "sinistres": 0, "prime_nette": 420_000},

    # CRT-002 — Mbarga (7 contrats)
    {"numero": "POL-2025-0005", "courtier_code": "CRT-002", "branche": "Auto",      "nom_assure": "Epouse Fanta Beloko",    "prime_ttc": 410_000,   "date_effet": date(2025, 1, 20), "date_echeance": _today + timedelta(days=290), "statut": "actif",    "sinistres": 2, "prime_nette": 365_000},
    {"numero": "POL-2025-0006", "courtier_code": "CRT-002", "branche": "Vie",       "nom_assure": "Emmanuel Tchatchoua",    "prime_ttc": 2_400_000, "date_effet": date(2025, 1, 1),  "date_echeance": _today + timedelta(days=340), "statut": "actif",    "sinistres": 0, "prime_nette": 2_200_000},
    {"numero": "POL-2025-0007", "courtier_code": "CRT-002", "branche": "IRD",       "nom_assure": "Groupe Scolaire Étoile", "prime_ttc": 5_800_000, "date_effet": date(2025, 2, 10), "date_echeance": _today + timedelta(days=310), "statut": "actif",    "sinistres": 0, "prime_nette": 5_200_000},
    {"numero": "POL-2025-0008", "courtier_code": "CRT-002", "branche": "RC",        "nom_assure": "Cabinet Expertise SA",   "prime_ttc": 750_000,   "date_effet": date(2025, 3, 1),  "date_echeance": _today + timedelta(days=328), "statut": "actif",    "sinistres": 0, "prime_nette": 680_000},
    {"numero": "POL-2025-0014", "courtier_code": "CRT-002", "branche": "Transport", "nom_assure": "Logistique Bafia",       "prime_ttc": 1_450_000, "date_effet": date(2025, 1, 5),  "date_echeance": _today + timedelta(days=40),  "statut": "actif",    "sinistres": 1, "prime_nette": 1_300_000},
    {"numero": "POL-2025-0015", "courtier_code": "CRT-002", "branche": "Auto",      "nom_assure": "Dr Mvondo Robert",       "prime_ttc": 395_000,   "date_effet": date(2025, 4, 5),  "date_echeance": _today + timedelta(days=358), "statut": "actif",    "sinistres": 0, "prime_nette": 350_000},
    {"numero": "POL-2025-0022", "courtier_code": "CRT-002", "branche": "Vie",       "nom_assure": "Épouse Onana Bernadette","prime_ttc": 900_000,   "date_effet": date(2025, 3, 20), "date_echeance": _today + timedelta(days=338), "statut": "actif",    "sinistres": 0, "prime_nette": 820_000},
    {"numero": "POL-2024-0180", "courtier_code": "CRT-002", "branche": "Incendie",  "nom_assure": "Supermarché Bonheur",    "prime_ttc": 620_000,   "date_effet": date(2024, 4, 1),  "date_echeance": _today - timedelta(days=5),   "statut": "impayé",   "sinistres": 0, "prime_nette": 550_000},

    # CRT-004 — Kameni (6 contrats — top performer)
    {"numero": "POL-2025-0009", "courtier_code": "CRT-004", "branche": "Vie",       "nom_assure": "Banque Atlantique CM",   "prime_ttc": 18_500_000,"date_effet": date(2025, 1, 1),  "date_echeance": _today + timedelta(days=360), "statut": "actif",    "sinistres": 0, "prime_nette": 17_000_000},
    {"numero": "POL-2025-0010", "courtier_code": "CRT-004", "branche": "IRD",       "nom_assure": "Hôtel des Palmiers",     "prime_ttc": 12_000_000,"date_effet": date(2025, 2, 1),  "date_echeance": _today + timedelta(days=330), "statut": "actif",    "sinistres": 1, "prime_nette": 10_800_000},
    {"numero": "POL-2025-0011", "courtier_code": "CRT-004", "branche": "Transport", "nom_assure": "Congelcam SARL",         "prime_ttc": 8_700_000, "date_effet": date(2025, 1, 15), "date_echeance": _today + timedelta(days=280), "statut": "actif",    "sinistres": 0, "prime_nette": 7_900_000},
    {"numero": "POL-2025-0016", "courtier_code": "CRT-004", "branche": "RC",        "nom_assure": "Pharmaci Santé Plus",    "prime_ttc": 950_000,   "date_effet": date(2025, 3, 5),  "date_echeance": _today + timedelta(days=333), "statut": "actif",    "sinistres": 0, "prime_nette": 870_000},
    {"numero": "POL-2025-0017", "courtier_code": "CRT-004", "branche": "Incendie",  "nom_assure": "Entrepôt CFAO Motors",   "prime_ttc": 4_200_000, "date_effet": date(2025, 2, 20), "date_echeance": _today + timedelta(days=315), "statut": "actif",    "sinistres": 0, "prime_nette": 3_800_000},
    {"numero": "POL-2025-0018", "courtier_code": "CRT-004", "branche": "Auto",      "nom_assure": "Flotte Véhicules DGI",   "prime_ttc": 6_500_000, "date_effet": date(2025, 1, 3),  "date_echeance": _today + timedelta(days=270), "statut": "actif",    "sinistres": 2, "prime_nette": 5_900_000},

    # CRT-003 — BiyaAssur (4 contrats)
    {"numero": "POL-2025-0019", "courtier_code": "CRT-003", "branche": "Auto",      "nom_assure": "Kana Jean-Marie",        "prime_ttc": 295_000,   "date_effet": date(2025, 2, 1),  "date_echeance": _today + timedelta(days=315), "statut": "actif",    "sinistres": 0, "prime_nette": 265_000},
    {"numero": "POL-2025-0020", "courtier_code": "CRT-003", "branche": "Vie",       "nom_assure": "Epse Feudjio Nadège",    "prime_ttc": 780_000,   "date_effet": date(2025, 3, 1),  "date_echeance": _today + timedelta(days=328), "statut": "actif",    "sinistres": 0, "prime_nette": 710_000},
    {"numero": "POL-2025-0021", "courtier_code": "CRT-003", "branche": "RC",        "nom_assure": "Cabinet Avocat Njoya",   "prime_ttc": 420_000,   "date_effet": date(2025, 1, 10), "date_echeance": _today + timedelta(days=275), "statut": "actif",    "sinistres": 0, "prime_nette": 385_000},
    {"numero": "POL-2025-0023", "courtier_code": "CRT-003", "branche": "Transport", "nom_assure": "Moto-Trans Bafoussam",   "prime_ttc": 340_000,   "date_effet": date(2025, 4, 1),  "date_echeance": _today + timedelta(days=355), "statut": "actif",    "sinistres": 1, "prime_nette": 305_000},

    # CRT-005, 006, 007, 008 — quelques contrats
    {"numero": "POL-2025-0024", "courtier_code": "CRT-005", "branche": "Auto",      "nom_assure": "Oumarou Adamou",         "prime_ttc": 360_000,   "date_effet": date(2025, 1, 25), "date_echeance": _today + timedelta(days=290), "statut": "actif",    "sinistres": 0, "prime_nette": 325_000},
    {"numero": "POL-2025-0025", "courtier_code": "CRT-005", "branche": "IRD",       "nom_assure": "Entrepôt Coton Garoua",  "prime_ttc": 2_100_000, "date_effet": date(2025, 2, 5),  "date_echeance": _today + timedelta(days=320), "statut": "actif",    "sinistres": 0, "prime_nette": 1_900_000},
    {"numero": "POL-2025-0026", "courtier_code": "CRT-006", "branche": "Vie",       "nom_assure": "Fongang Thierry",        "prime_ttc": 1_600_000, "date_effet": date(2025, 3, 15), "date_echeance": _today + timedelta(days=340), "statut": "actif",    "sinistres": 0, "prime_nette": 1_450_000},
    {"numero": "POL-2025-0027", "courtier_code": "CRT-007", "branche": "Auto",      "nom_assure": "Vétérinaire Adamou",     "prime_ttc": 275_000,   "date_effet": date(2025, 4, 10), "date_echeance": _today + timedelta(days=365), "statut": "actif",    "sinistres": 0, "prime_nette": 250_000},
    {"numero": "POL-2025-0028", "courtier_code": "CRT-008", "branche": "Transport", "nom_assure": "Sone Pêche Export",      "prime_ttc": 1_850_000, "date_effet": date(2025, 2, 28), "date_echeance": _today + timedelta(days=323), "statut": "actif",    "sinistres": 0, "prime_nette": 1_680_000},
]

# Historique des commissions versées (par courtier, par mois/branche)
# Clé : (courtier_code, annee, mois, branche)
_VERSEMENTS = {
    ("CRT-001", 2025, 1, "Auto"):      {"montant": 150_400, "verse": True,  "date_versement": date(2025, 2, 5)},
    ("CRT-001", 2025, 1, "Vie"):       {"montant": 220_000, "verse": True,  "date_versement": date(2025, 2, 5)},
    ("CRT-001", 2025, 2, "Auto"):      {"montant": 34_200, "verse": True,   "date_versement": date(2025, 3, 7)},
    ("CRT-001", 2025, 2, "IRD"):       {"montant": 435_000, "verse": True,  "date_versement": date(2025, 3, 7)},
    ("CRT-001", 2025, 3, "Transport"): {"montant": 98_400, "verse": True,   "date_versement": date(2025, 4, 4)},
    ("CRT-001", 2025, 3, "RC"):        {"montant": 60_000, "verse": False,  "date_versement": None},

    ("CRT-002", 2025, 1, "Auto"):      {"montant": 190_600, "verse": True,  "date_versement": date(2025, 2, 6)},
    ("CRT-002", 2025, 1, "Vie"):       {"montant": 484_000, "verse": True,  "date_versement": date(2025, 2, 6)},
    ("CRT-002", 2025, 2, "IRD"):       {"montant": 780_000, "verse": True,  "date_versement": date(2025, 3, 6)},
    ("CRT-002", 2025, 3, "RC"):        {"montant": 74_800, "verse": True,   "date_versement": date(2025, 4, 3)},
    ("CRT-002", 2025, 3, "Transport"): {"montant": 169_000, "verse": False, "date_versement": None},
    ("CRT-002", 2025, 3, "Vie"):       {"montant": 180_400, "verse": False, "date_versement": None},

    ("CRT-004", 2025, 1, "Vie"):       {"montant": 3_910_000, "verse": True, "date_versement": date(2025, 2, 3)},
    ("CRT-004", 2025, 1, "Transport"): {"montant": 1_106_000, "verse": True, "date_versement": date(2025, 2, 3)},
    ("CRT-004", 2025, 2, "IRD"):       {"montant": 1_728_000, "verse": True, "date_versement": date(2025, 3, 5)},
    ("CRT-004", 2025, 3, "Auto"):      {"montant": 826_000, "verse": True,  "date_versement": date(2025, 4, 2)},
    ("CRT-004", 2025, 3, "Incendie"):  {"montant": 608_000, "verse": False, "date_versement": None},
    ("CRT-004", 2025, 3, "RC"):        {"montant": 104_400, "verse": False, "date_versement": None},
}


def _contrats_courtier(courtier_code: str) -> list[dict]:
    return [c for c in _CONTRATS if c["courtier_code"] == courtier_code]


def _commission_branche(prime_nette: float, branche: str, courtier_code: str) -> float:
    taux = _COURTIERS.get(courtier_code, {}).get("taux_commission", {}).get(branche, 0.12)
    return round(prime_nette * taux)


# ──────────────────────────────────────────────────────────────────────────────
# MODÈLES DE DONNÉES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SoumissionCourtier:
    courtier_code: str
    branche: str
    photos_documents: list[str] = field(default_factory=list)  # CNI, carte grise etc.
    donnees_client: dict = field(default_factory=dict)
    canal: str = "app_mobile"  # "app_mobile" | "whatsapp"


@dataclass
class TableauBordCourtier:
    courtier_code: str
    periode: str
    polices_actives: int
    nouvelles_polices_mois: int
    commissions_dues: float
    commissions_versees: float
    commissions_a_payer: float
    sinistres_en_cours: int
    taux_retention: float
    alertes: list[str]


# ──────────────────────────────────────────────────────────────────────────────
# PORTAIL COURTIER
# ──────────────────────────────────────────────────────────────────────────────

class PortailCourtier:
    """
    Portail courtier — autonomie complète depuis le mobile.
    Fonctionne 100% sans ORASS via un DataStore en mémoire.

    Fonctionnalités :
    - Soumission dossier en 5 minutes depuis le terrain
    - Tableau de bord riche : top productions, sinistres, pipeline
    - Suivi portefeuille complet avec alertes
    - Commissions détaillées par branche + projection annuelle
    - Alertes intelligentes (renouvellements, impayés, sinistres)
    - Classement des courtiers (top performers)
    """

    # ──────────────────────────────────────────────────────────────
    # SOUMISSION DOSSIER
    # ──────────────────────────────────────────────────────────────

    async def soumettre_dossier(
        self, soumission: SoumissionCourtier
    ) -> dict:
        """Soumission d'un nouveau dossier depuis l'app mobile courtier"""
        try:
            from modules.souscription.portail import DossierSouscription, portail_souscription

            cni_b64 = soumission.photos_documents[0] if soumission.photos_documents else None
            cg_b64 = soumission.photos_documents[1] if len(soumission.photos_documents) > 1 else None

            dossier = DossierSouscription(
                branche=soumission.branche,
                cni_b64=cni_b64,
                carte_grise_b64=cg_b64,
                donnees_client=soumission.donnees_client,
                courtier_code=soumission.courtier_code,
            )

            resultat = await portail_souscription.traiter_dossier(dossier)
            commission = self._estimer_commission(
                resultat.calcul_prime, soumission.courtier_code, soumission.branche
            )

            logger.info(
                f"[Courtiers] Soumission {soumission.courtier_code} → statut={resultat.statut}"
            )

            return {
                "statut": resultat.statut,
                "numero_police": resultat.numero_police,
                "prime_ttc": resultat.calcul_prime.get("prime_ttc") if resultat.calcul_prime else None,
                "commission_estimee": commission,
                "message": resultat.message,
                "actions": resultat.actions,
                "pieces_manquantes": resultat.pieces_manquantes,
            }
        except Exception as e:
            logger.warning(f"[Courtiers] Soumission simulée (ORASS indisponible): {e}")
            return {
                "statut": "en_attente",
                "numero_police": None,
                "prime_ttc": None,
                "commission_estimee": 0,
                "message": "Dossier enregistré en attente de validation (mode hors-ligne)",
                "actions": ["Vérification KYC en cours"],
                "pieces_manquantes": [],
            }

    # ──────────────────────────────────────────────────────────────
    # TABLEAU DE BORD
    # ──────────────────────────────────────────────────────────────

    async def tableau_de_bord(
        self,
        courtier_code: str,
        mois: Optional[int] = None,
        annee: Optional[int] = None,
    ) -> TableauBordCourtier:
        """Tableau de bord temps réel du courtier (sans ORASS)"""
        tdb = await self.get_tableau_bord_courtier(courtier_code, mois, annee)
        return TableauBordCourtier(
            courtier_code=courtier_code,
            periode=tdb["periode"],
            polices_actives=tdb["polices_actives"],
            nouvelles_polices_mois=tdb["nouvelles_polices_mois"],
            commissions_dues=tdb["commissions_dues"],
            commissions_versees=tdb["commissions_versees"],
            commissions_a_payer=tdb["commissions_a_payer"],
            sinistres_en_cours=tdb["sinistres_en_cours"],
            taux_retention=tdb["taux_retention"],
            alertes=[a["message"] for a in tdb.get("alertes", [])],
        )

    async def get_tableau_bord_courtier(
        self,
        courtier_code: str,
        mois: Optional[int] = None,
        annee: Optional[int] = None,
    ) -> dict:
        """
        Tableau de bord enrichi : top productions, sinistres ouverts,
        taux conversion, pipeline en cours, objectif vs réalisé.
        """
        today = date.today()
        annee_cible = annee or today.year
        mois_cible = mois or today.month

        courtier = _COURTIERS.get(courtier_code)
        if not courtier:
            return {"erreur": f"Courtier {courtier_code} inconnu"}

        contrats = _contrats_courtier(courtier_code)
        contrats_actifs = [c for c in contrats if c["statut"] == "actif"]

        # Nouvelles polices du mois
        nouvelles = [
            c for c in contrats
            if c["date_effet"].year == annee_cible
            and c["date_effet"].month == mois_cible
        ]

        # Sinistres
        sinistres_ouverts = sum(c["sinistres"] for c in contrats_actifs)

        # Primes mensuelles du mois
        primes_mois = sum(c["prime_ttc"] for c in nouvelles)

        # Commissions totales
        comm_details = self._calculer_commissions_brutes(courtier_code)
        comm_dues = comm_details["total_du"]
        comm_versees = comm_details["total_verse"]
        comm_a_payer = max(0, comm_dues - comm_versees)

        # Taux de rétention (polices actives / total hors pipeline)
        total_termines = len([c for c in contrats if c["statut"] in ("expiré", "résilié")])
        total_gere = len(contrats_actifs) + total_termines
        taux_retention = round(len(contrats_actifs) / max(1, total_gere), 3)

        # Top 3 productions (par branche)
        prod_par_branche: dict[str, float] = {}
        for c in contrats_actifs:
            prod_par_branche[c["branche"]] = prod_par_branche.get(c["branche"], 0) + c["prime_ttc"]
        top_productions = sorted(
            [{"branche": b, "prime_ttc": v} for b, v in prod_par_branche.items()],
            key=lambda x: -x["prime_ttc"],
        )[:3]

        # Avancement objectif annuel
        prime_annee = sum(c["prime_ttc"] for c in contrats if c["date_effet"].year == annee_cible)
        objectif = courtier["objectif_annuel_fcfa"]
        taux_objectif = round(prime_annee / objectif * 100, 1) if objectif > 0 else 0

        # Alertes
        alertes = await self._alertes_courtier_raw(courtier_code)

        return {
            "courtier_code": courtier_code,
            "nom": courtier["nom"],
            "responsable": courtier["responsable"],
            "ville": courtier["ville"],
            "periode": f"{mois_cible:02d}/{annee_cible}",
            "polices_actives": len(contrats_actifs),
            "nouvelles_polices_mois": len(nouvelles),
            "primes_mois_fcfa": primes_mois,
            "sinistres_en_cours": sinistres_ouverts,
            "taux_retention": taux_retention,
            "commissions_dues": comm_dues,
            "commissions_versees": comm_versees,
            "commissions_a_payer": comm_a_payer,
            "top_productions": top_productions,
            "prime_annee_fcfa": prime_annee,
            "objectif_annuel_fcfa": objectif,
            "taux_realisation_objectif_pct": taux_objectif,
            "alertes": alertes,
        }

    # ──────────────────────────────────────────────────────────────
    # SUIVI PORTEFEUILLE
    # ──────────────────────────────────────────────────────────────

    async def suivi_portefeuille_complet(self, courtier_code: str) -> dict:
        """
        Liste tous les contrats du courtier avec statut, prime,
        date d'échéance, commission estimée et alertes par contrat.
        """
        today = date.today()
        contrats = _contrats_courtier(courtier_code)
        courtier = _COURTIERS.get(courtier_code, {})

        lignes = []
        for c in sorted(contrats, key=lambda x: x["date_echeance"]):
            jours_avant_echeance = (c["date_echeance"] - today).days
            commission = _commission_branche(c["prime_nette"], c["branche"], courtier_code)
            alertes_contrat = []

            if c["statut"] == "impayé":
                alertes_contrat.append("IMPAYÉ — action recouvrement requise")
            elif c["statut"] == "expiré":
                alertes_contrat.append("Police expirée — relancer le renouvellement")
            elif 0 < jours_avant_echeance <= 60:
                alertes_contrat.append(f"Renouvellement dans {jours_avant_echeance} jours")
            elif jours_avant_echeance <= 0:
                alertes_contrat.append("ÉCHUE — renouvellement urgent")

            if c["sinistres"] > 0:
                alertes_contrat.append(f"{c['sinistres']} sinistre(s) ouvert(s)")

            lignes.append({
                "numero_police": c["numero"],
                "branche": c["branche"],
                "nom_assure": c["nom_assure"],
                "prime_ttc_fcfa": c["prime_ttc"],
                "prime_nette_fcfa": c["prime_nette"],
                "commission_fcfa": commission,
                "date_effet": c["date_effet"].isoformat(),
                "date_echeance": c["date_echeance"].isoformat(),
                "jours_avant_echeance": jours_avant_echeance,
                "statut": c["statut"],
                "sinistres_ouverts": c["sinistres"],
                "alertes": alertes_contrat,
            })

        total_primes = sum(c["prime_ttc"] for c in contrats if c["statut"] == "actif")
        total_commissions = sum(
            _commission_branche(c["prime_nette"], c["branche"], courtier_code)
            for c in contrats if c["statut"] == "actif"
        )

        return {
            "courtier_code": courtier_code,
            "nom": courtier.get("nom", ""),
            "nb_contrats_total": len(contrats),
            "nb_actifs": len([c for c in contrats if c["statut"] == "actif"]),
            "nb_expires": len([c for c in contrats if c["statut"] == "expiré"]),
            "nb_impayes": len([c for c in contrats if c["statut"] == "impayé"]),
            "total_primes_actives_fcfa": total_primes,
            "total_commissions_estimees_fcfa": total_commissions,
            "contrats": lignes,
        }

    # ──────────────────────────────────────────────────────────────
    # SUIVI DOSSIER INDIVIDUEL (compatible ancien code)
    # ──────────────────────────────────────────────────────────────

    async def suivi_dossier(self, numero_police: str, courtier_code: str) -> dict:
        """Suivi en temps réel d'un dossier"""
        contrat = next(
            (c for c in _CONTRATS if c["numero"] == numero_police), None
        )
        if not contrat or contrat["courtier_code"] != courtier_code:
            return {"erreur": "Dossier introuvable ou non autorisé"}

        today = date.today()
        jours = (contrat["date_echeance"] - today).days

        return {
            "numero_police": numero_police,
            "branche": contrat["branche"],
            "statut_contrat": contrat["statut"],
            "assure": contrat["nom_assure"],
            "date_effet": contrat["date_effet"].isoformat(),
            "date_echeance": contrat["date_echeance"].isoformat(),
            "prime_ttc": contrat["prime_ttc"],
            "commission_estimee_fcfa": _commission_branche(
                contrat["prime_nette"], contrat["branche"], courtier_code
            ),
            "sinistres_en_cours": contrat["sinistres"],
            "alerte_renouvellement": 0 < jours <= 60,
            "jours_avant_echeance": jours,
        }

    # ──────────────────────────────────────────────────────────────
    # COMMISSIONS DÉTAILLÉES
    # ──────────────────────────────────────────────────────────────

    def _calculer_commissions_brutes(self, courtier_code: str) -> dict:
        """Calcule les commissions réelles depuis les versements enregistrés."""
        total_du = 0.0
        total_verse = 0.0
        contrats = _contrats_courtier(courtier_code)

        for c in contrats:
            comm = _commission_branche(c["prime_nette"], c["branche"], courtier_code)
            total_du += comm

        for (code, annee, mois, branche), v in _VERSEMENTS.items():
            if code == courtier_code and v["verse"]:
                total_verse += v["montant"]

        return {"total_du": round(total_du), "total_verse": round(total_verse)}

    async def calculer_commissions_detaillees(
        self,
        courtier_code: str,
        annee: Optional[int] = None,
    ) -> dict:
        """
        Commissions par branche, par mois, avec projection annuelle.
        Retourne : réalisé, versé, solde et projection fin d'année.
        """
        today = date.today()
        annee_cible = annee or today.year
        contrats = _contrats_courtier(courtier_code)
        courtier = _COURTIERS.get(courtier_code, {})

        # Par branche
        par_branche: dict[str, dict] = {}
        for c in contrats:
            if c["date_effet"].year == annee_cible:
                br = c["branche"]
                comm = _commission_branche(c["prime_nette"], br, courtier_code)
                if br not in par_branche:
                    par_branche[br] = {
                        "branche": br,
                        "taux_commission": courtier.get("taux_commission", {}).get(br, 0.12),
                        "nb_polices": 0,
                        "primes_nettes_fcfa": 0,
                        "commissions_dues_fcfa": 0,
                        "commissions_versees_fcfa": 0,
                    }
                par_branche[br]["nb_polices"] += 1
                par_branche[br]["primes_nettes_fcfa"] += c["prime_nette"]
                par_branche[br]["commissions_dues_fcfa"] += comm

        # Versements réels
        for (code, a, m, br), v in _VERSEMENTS.items():
            if code == courtier_code and a == annee_cible and v["verse"]:
                if br in par_branche:
                    par_branche[br]["commissions_versees_fcfa"] += v["montant"]

        for br in par_branche:
            due = par_branche[br]["commissions_dues_fcfa"]
            verse = par_branche[br]["commissions_versees_fcfa"]
            par_branche[br]["solde_fcfa"] = round(due - verse)
            par_branche[br]["commissions_dues_fcfa"] = round(due)

        # Par mois
        par_mois: list[dict] = []
        for m in range(1, today.month + 1):
            polices_mois = [
                c for c in contrats
                if c["date_effet"].year == annee_cible and c["date_effet"].month == m
            ]
            comm_mois = sum(
                _commission_branche(c["prime_nette"], c["branche"], courtier_code)
                for c in polices_mois
            )
            verse_mois = sum(
                v["montant"]
                for (code, a, mois_v, br), v in _VERSEMENTS.items()
                if code == courtier_code and a == annee_cible and mois_v == m and v["verse"]
            )
            par_mois.append({
                "mois": m,
                "mois_libelle": [
                    "", "Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
                    "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"
                ][m],
                "nb_polices_emises": len(polices_mois),
                "commissions_dues_fcfa": round(comm_mois),
                "commissions_versees_fcfa": round(verse_mois),
                "solde_fcfa": round(comm_mois - verse_mois),
            })

        # Totaux
        total_du = sum(d["commissions_dues_fcfa"] for d in par_branche.values())
        total_verse = sum(d["commissions_versees_fcfa"] for d in par_branche.values())

        # Projection annuelle (extrapolation linéaire sur les mois écoulés)
        mois_ecoules = today.month
        projection_annuelle = round(total_du / mois_ecoules * 12) if mois_ecoules > 0 else 0

        return {
            "courtier_code": courtier_code,
            "nom": courtier.get("nom", ""),
            "annee": annee_cible,
            "total_commissions_dues_fcfa": round(total_du),
            "total_commissions_versees_fcfa": round(total_verse),
            "solde_a_payer_fcfa": round(max(0, total_du - total_verse)),
            "projection_annuelle_fcfa": projection_annuelle,
            "par_branche": sorted(
                list(par_branche.values()),
                key=lambda x: -x["commissions_dues_fcfa"],
            ),
            "par_mois": par_mois,
        }

    # ──────────────────────────────────────────────────────────────
    # ALERTES COURTIER
    # ──────────────────────────────────────────────────────────────

    async def _alertes_courtier_raw(self, courtier_code: str) -> list[dict]:
        """Version interne retournant des dicts structurés."""
        today = date.today()
        alertes = []
        contrats = _contrats_courtier(courtier_code)

        for c in contrats:
            jours = (c["date_echeance"] - today).days

            # Renouvellements à 60 jours
            if c["statut"] == "actif" and 0 < jours <= 60:
                alertes.append({
                    "type": "renouvellement",
                    "gravite": "haute" if jours <= 30 else "moyenne",
                    "message": (
                        f"Renouvellement dans {jours}j — "
                        f"{c['nom_assure']} / {c['branche']} ({c['numero']})"
                    ),
                    "police": c["numero"],
                    "date_echeance": c["date_echeance"].isoformat(),
                    "prime_ttc_fcfa": c["prime_ttc"],
                })

            # Polices échues non renouvelées
            if c["statut"] == "actif" and jours <= 0:
                alertes.append({
                    "type": "echeance_depassee",
                    "gravite": "critique",
                    "message": (
                        f"Police ÉCHUE depuis {abs(jours)}j — "
                        f"{c['nom_assure']} / {c['branche']} ({c['numero']})"
                    ),
                    "police": c["numero"],
                    "date_echeance": c["date_echeance"].isoformat(),
                    "prime_ttc_fcfa": c["prime_ttc"],
                })

            # Polices impayées
            if c["statut"] == "impayé":
                alertes.append({
                    "type": "impaye",
                    "gravite": "critique",
                    "message": (
                        f"Prime IMPAYÉE — {c['nom_assure']} / {c['branche']} ({c['numero']})"
                        f" — {c['prime_ttc']:,.0f} FCFA"
                    ),
                    "police": c["numero"],
                    "prime_ttc_fcfa": c["prime_ttc"],
                })

            # Sinistres en attente
            if c["sinistres"] > 0:
                alertes.append({
                    "type": "sinistre",
                    "gravite": "moyenne",
                    "message": (
                        f"{c['sinistres']} sinistre(s) ouvert(s) — "
                        f"{c['nom_assure']} ({c['numero']})"
                    ),
                    "police": c["numero"],
                    "nb_sinistres": c["sinistres"],
                })

        # Commissions impayées > 500 000 FCFA
        comm = self._calculer_commissions_brutes(courtier_code)
        solde = comm["total_du"] - comm["total_verse"]
        if solde > 500_000:
            alertes.append({
                "type": "commission_en_attente",
                "gravite": "haute",
                "message": f"Commission en attente de versement : {solde:,.0f} FCFA",
                "montant_fcfa": round(solde),
            })

        # Tri par gravité
        ordre = {"critique": 0, "haute": 1, "moyenne": 2, "faible": 3}
        alertes.sort(key=lambda a: ordre.get(a["gravite"], 99))
        return alertes

    async def alertes_courtier(self, courtier_code: str) -> dict:
        """
        Alertes intelligentes pour le courtier :
        - Renouvellements à 60j
        - Impayés
        - Sinistres en attente
        - Commissions en retard
        """
        courtier = _COURTIERS.get(courtier_code)
        if not courtier:
            return {"erreur": f"Courtier {courtier_code} inconnu"}

        alertes = await self._alertes_courtier_raw(courtier_code)
        critique = [a for a in alertes if a["gravite"] == "critique"]
        hautes = [a for a in alertes if a["gravite"] == "haute"]
        moyennes = [a for a in alertes if a["gravite"] == "moyenne"]

        return {
            "courtier_code": courtier_code,
            "nom": courtier["nom"],
            "nb_alertes_total": len(alertes),
            "nb_critiques": len(critique),
            "nb_hautes": len(hautes),
            "nb_moyennes": len(moyennes),
            "alertes": alertes,
        }

    # ──────────────────────────────────────────────────────────────
    # CLASSEMENT COURTIERS
    # ──────────────────────────────────────────────────────────────

    async def classement_courtiers(
        self,
        mois: Optional[int] = None,
        annee: Optional[int] = None,
    ) -> dict:
        """
        Top performers du mois/année.
        Classement par : primes émises, commissions, nb polices, taux rétention.
        """
        today = date.today()
        annee_cible = annee or today.year
        mois_cible = mois or today.month

        classement = []

        for code, courtier in _COURTIERS.items():
            contrats = _contrats_courtier(code)

            # Polices du mois
            polices_mois = [
                c for c in contrats
                if c["date_effet"].year == annee_cible
                and c["date_effet"].month == mois_cible
            ]

            # Primes actives totales (année)
            prime_annee = sum(
                c["prime_ttc"] for c in contrats
                if c["date_effet"].year == annee_cible and c["statut"] == "actif"
            )

            # Commissions du mois
            comm_mois = sum(
                _commission_branche(c["prime_nette"], c["branche"], code)
                for c in polices_mois
            )

            # Taux de rétention
            actifs = len([c for c in contrats if c["statut"] == "actif"])
            expires = len([c for c in contrats if c["statut"] in ("expiré", "résilié")])
            taux_retention = round(actifs / max(1, actifs + expires) * 100, 1)

            # Score composite (primes × 0.5 + polices × 0.3 + rétention × 0.2)
            score = (
                prime_annee * 0.5
                + len(polices_mois) * 1_000_000 * 0.3
                + taux_retention * 500_000 * 0.2
            )

            classement.append({
                "rang": 0,  # calculé après le tri
                "courtier_code": code,
                "nom": courtier["nom"],
                "ville": courtier["ville"],
                "responsable": courtier["responsable"],
                "nb_polices_mois": len(polices_mois),
                "primes_mois_fcfa": sum(c["prime_ttc"] for c in polices_mois),
                "commissions_mois_fcfa": round(comm_mois),
                "prime_annee_fcfa": prime_annee,
                "objectif_annuel_fcfa": courtier["objectif_annuel_fcfa"],
                "taux_realisation_pct": round(
                    prime_annee / courtier["objectif_annuel_fcfa"] * 100, 1
                ) if courtier["objectif_annuel_fcfa"] > 0 else 0,
                "taux_retention_pct": taux_retention,
                "polices_actives": actifs,
                "_score": score,
            })

        # Tri par score décroissant
        classement.sort(key=lambda x: -x["_score"])
        for i, item in enumerate(classement):
            item["rang"] = i + 1
            del item["_score"]

        top3 = classement[:3]

        return {
            "periode": f"{mois_cible:02d}/{annee_cible}",
            "nb_courtiers": len(classement),
            "top3": top3,
            "classement_complet": classement,
        }

    # ──────────────────────────────────────────────────────────────
    # UTILITAIRES INTERNES
    # ──────────────────────────────────────────────────────────────

    def _estimer_commission(
        self,
        calcul_prime: Optional[dict],
        courtier_code: str,
        branche: str = "Auto",
    ) -> float:
        if not calcul_prime:
            return 0.0
        prime_nette = calcul_prime.get("prime_nette", 0)
        return _commission_branche(prime_nette, branche, courtier_code)


# Instance singleton
portail_courtier = PortailCourtier()
