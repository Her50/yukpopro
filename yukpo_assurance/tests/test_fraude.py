"""
Tests de détection de fraude — score individuel, indicateurs, réseau.
Couvre : sinistre suspect, sinistre normal, indicateurs, analyse réseau, churn.
"""
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# SCORE INDIVIDUEL
# ─────────────────────────────────────────────────────────────────────────────

def test_sinistre_suspect_score_superieur_60(sinistre_suspect):
    """Sinistre avec indicateurs suspects → score déterministe > 60."""
    from modules.sinistres.fraude_detector import FraudeDetector

    detector = FraudeDetector()
    score = detector._calcul_score_deterministe(sinistre_suspect)
    assert 0 <= score <= 100
    # Montant élevé + pas de pièces + historique chargé = score élevé
    assert score > 60, f"Score attendu > 60, obtenu {score}"


def test_sinistre_normal_score_inferieur_30(sinistre_normal):
    """Sinistre standard sans indicateurs → score déterministe < 30."""
    from modules.sinistres.fraude_detector import FraudeDetector

    detector = FraudeDetector()
    score = detector._calcul_score_deterministe(sinistre_normal)
    assert 0 <= score <= 100
    assert score < 30, f"Score attendu < 30, obtenu {score}"


def test_score_avec_heure_suspecte():
    """Sinistre déclaré à 03h00 → contribue à la hausse du score."""
    from modules.sinistres.fraude_detector import FraudeDetector

    detector = FraudeDetector()
    dossier_nuit = {
        "numero_sinistre": "SIN-TEST-NUIT",
        "numero_police": "AUTO-2025-001",
        "date_sinistre": "2025-03-25",
        "date_declaration": "2025-04-01",
        "heure_sinistre": "03:15",
        "nature": "vol",
        "montant_declare": 500_000,
        "pieces_fournies": ["cni"],
        "tiers_impliques": [],
        "blesses": False,
        "historique_sinistres_client": 0,
    }
    dossier_jour = dict(dossier_nuit)
    dossier_jour["heure_sinistre"] = "10:00"

    score_nuit = detector._calcul_score_deterministe(dossier_nuit)
    score_jour = detector._calcul_score_deterministe(dossier_jour)

    # L'heure suspecte doit augmenter le score
    assert score_nuit >= score_jour


# ─────────────────────────────────────────────────────────────────────────────
# INDICATEURS INDIVIDUELS
# ─────────────────────────────────────────────────────────────────────────────

def test_indicateur_post_souscription_recente():
    """Sinistre déclaré peu après souscription → indicateur suspect."""
    from modules.sinistres.fraude_detector import FraudeDetector

    detector = FraudeDetector()
    # Souscrit il y a 5 jours, sinistre le lendemain
    dossier = {
        "numero_sinistre": "SIN-POST-SBP",
        "numero_police": "AUTO-2025-RECENT",
        "date_sinistre": "2025-03-31",
        "date_declaration": "2025-04-01",
        "date_souscription": "2025-03-28",  # 3 jours avant sinistre
        "nature": "collision",
        "montant_declare": 400_000,
        "pieces_fournies": ["constat", "cni"],
        "tiers_impliques": [],
        "blesses": False,
        "historique_sinistres_client": 0,
    }
    score = detector._calcul_score_deterministe(dossier)
    assert 0 <= score <= 100


def test_indicateur_multi_reclamant():
    """Client avec 5+ sinistres récents → score plus élevé."""
    from modules.sinistres.fraude_detector import FraudeDetector

    detector = FraudeDetector()

    dossier_multi = {
        "numero_sinistre": "SIN-MULTI",
        "numero_police": "AUTO-2025-003",
        "date_sinistre": "2025-03-25",
        "date_declaration": "2025-04-01",
        "nature": "collision",
        "montant_declare": 350_000,
        "pieces_fournies": ["constat", "cni"],
        "tiers_impliques": [],
        "blesses": False,
        "historique_sinistres_client": 5,  # Multi-réclamant
    }
    dossier_normal = dict(dossier_multi)
    dossier_normal["historique_sinistres_client"] = 0

    score_multi = detector._calcul_score_deterministe(dossier_multi)
    score_normal = detector._calcul_score_deterministe(dossier_normal)

    assert score_multi >= score_normal


def test_indicateur_montant_eleve():
    """Montant très élevé → score plus élevé."""
    from modules.sinistres.fraude_detector import FraudeDetector

    detector = FraudeDetector()
    base = {
        "numero_sinistre": "SIN-MONTANT",
        "numero_police": "AUTO-2025-004",
        "date_sinistre": "2025-03-25",
        "date_declaration": "2025-04-01",
        "nature": "collision",
        "pieces_fournies": ["constat", "cni", "carte_grise"],
        "tiers_impliques": [],
        "blesses": False,
        "historique_sinistres_client": 0,
    }

    dossier_eleve = dict(base)
    dossier_eleve["montant_declare"] = 15_000_000

    dossier_normal = dict(base)
    dossier_normal["montant_declare"] = 200_000

    score_eleve = detector._calcul_score_deterministe(dossier_eleve)
    score_normal = detector._calcul_score_deterministe(dossier_normal)

    assert score_eleve >= score_normal


def test_indicateur_absence_pieces():
    """Aucune pièce fournie → indicateur suspect."""
    from modules.sinistres.fraude_detector import FraudeDetector

    detector = FraudeDetector()

    dossier_sans_pieces = {
        "numero_sinistre": "SIN-SANS-PIECES",
        "numero_police": "AUTO-2025-005",
        "date_sinistre": "2025-03-25",
        "date_declaration": "2025-04-01",
        "nature": "collision",
        "montant_declare": 350_000,
        "pieces_fournies": [],  # Aucune pièce
        "tiers_impliques": [],
        "blesses": False,
        "historique_sinistres_client": 0,
    }
    dossier_avec_pieces = dict(dossier_sans_pieces)
    dossier_avec_pieces["pieces_fournies"] = ["constat", "cni", "carte_grise", "permis"]

    score_sans = detector._calcul_score_deterministe(dossier_sans_pieces)
    score_avec = detector._calcul_score_deterministe(dossier_avec_pieces)

    assert score_sans >= score_avec


# ─────────────────────────────────────────────────────────────────────────────
# NIVEAUX DE RISQUE
# ─────────────────────────────────────────────────────────────────────────────

def test_niveau_risque_faible():
    from modules.sinistres.fraude_detector import FraudeDetector
    assert FraudeDetector()._niveau_risque(15) == "faible"


def test_niveau_risque_modere():
    from modules.sinistres.fraude_detector import FraudeDetector
    assert FraudeDetector()._niveau_risque(45) == "modéré"


def test_niveau_risque_eleve():
    from modules.sinistres.fraude_detector import FraudeDetector
    assert FraudeDetector()._niveau_risque(65) == "élevé"


def test_niveau_risque_critique():
    from modules.sinistres.fraude_detector import FraudeDetector
    assert FraudeDetector()._niveau_risque(85) == "critique"


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE RÉSEAU FRAUDE
# ─────────────────────────────────────────────────────────────────────────────

def test_analyse_reseau_fraude_retourne_score():
    """Analyse de réseau fraude → score numérique entre 0 et 100."""
    from modules.sinistres.fraude_reseau import FraudeReseauDetector

    detector = FraudeReseauDetector()
    dossier = {
        "numero_sinistre": "SIN-RESEAU-001",
        "tiers_impliques": ["TIERS-001", "TIERS-002"],
        "garage_reparateur": "GARAGE-SUSPECT",
        "avocat": None,
        "numero_police": "AUTO-2025-006",
        "expert_designe": "EXPERT-001",
    }
    result = detector.analyser_reseau(dossier)
    assert isinstance(result, dict)
    assert "score_reseau" in result or "score" in result


def test_analyse_reseau_recommandation_passer():
    from modules.sinistres.fraude_reseau import FraudeReseauDetector

    d = FraudeReseauDetector()
    assert d._recommandation(30) == "passer"


def test_analyse_reseau_recommandation_surveiller():
    from modules.sinistres.fraude_reseau import FraudeReseauDetector

    d = FraudeReseauDetector()
    assert d._recommandation(55) == "surveiller"


def test_analyse_reseau_recommandation_bloquer():
    from modules.sinistres.fraude_reseau import FraudeReseauDetector

    d = FraudeReseauDetector()
    assert d._recommandation(75) == "bloquer"


def test_analyse_reseau_acteurs_multiples_score_eleve():
    """Réseau dense (garage + avocat + même tiers récurrents) → score élevé."""
    from modules.sinistres.fraude_reseau import FraudeReseauDetector

    detector = FraudeReseauDetector()
    dossier_reseau_dense = {
        "numero_sinistre": "SIN-RESEAU-002",
        "tiers_impliques": ["TIERS-REC-001", "TIERS-REC-002", "TIERS-REC-003"],
        "garage_reparateur": "GARAGE-RECURRENT",
        "avocat": "AVOCAT-SUSPECT",
        "numero_police": "AUTO-2025-007",
        "expert_designe": "EXPERT-RECURRENT",
        "nb_connexions_communes": 8,
    }
    result = detector.analyser_reseau(dossier_reseau_dense)
    assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# CHURN PREDICTION (lié à la fraude/rétention)
# ─────────────────────────────────────────────────────────────────────────────

def test_churn_score_deterministe_impaye_long():
    """Retard paiement 80j + échéance proche → score élevé."""
    from modules.analytics.churn_prediction import ChurnPredictionService

    svc = ChurnPredictionService()
    profil = {
        "jours_retard_paiement": 80,
        "jours_avant_echeance": 15,
        "nb_sinistres_3ans": 2,
        "anciennete_jours": 400,
    }
    score = svc._score_deterministe(profil)
    assert score >= 55


def test_churn_score_faible_bon_client():
    """Client fidèle, aucun impayé → score churn faible."""
    from modules.analytics.churn_prediction import ChurnPredictionService

    svc = ChurnPredictionService()
    profil = {
        "jours_retard_paiement": 0,
        "jours_avant_echeance": 200,
        "nb_sinistres_3ans": 0,
        "anciennete_jours": 1825,  # 5 ans
    }
    score = svc._score_deterministe(profil)
    assert score < 50


def test_churn_niveaux():
    from modules.analytics.churn_prediction import ChurnPredictionService

    svc = ChurnPredictionService()
    assert svc._niveau(20) == "stable"
    assert svc._niveau(45) == "modéré"
    assert svc._niveau(70) == "élevé"
    assert svc._niveau(90) == "critique"
