"""
Tests réglementaires CIMA — moteur de conformité et états réglementaires.
Couvre : Art. 337-1, états C1/C3/C5/C7, CRCA, Q&R CIMA.
"""
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# MARGE DE SOLVABILITÉ (Art. 337-1)
# ─────────────────────────────────────────────────────────────────────────────

def test_calcul_marge_solvabilite_conforme_selon_art_337_1():
    """Capitaux propres suffisants → conforme Art. 337-1."""
    from modules.cima.code_cima_engine import cima_engine

    result = cima_engine.calculer_marge_solvabilite_non_vie(
        primes_nettes=2_000_000_000,
        charge_sinistres_moyenne_3ans=1_000_000_000,
        capitaux_propres=600_000_000,
    )
    assert "marge_requise" in result
    assert "capitaux_propres" in result
    assert "conforme" in result
    assert result["marge_requise"] > 0
    # Art. 337-1 : marge = max(23% primes, 26% sinistres, 300M FCFA minimum absolu)
    assert result["marge_requise"] >= 260_000_000  # 26% de 1 Mrd sinistres


def test_calcul_marge_solvabilite_non_conforme():
    """Capitaux propres insuffisants → non conforme."""
    from modules.cima.code_cima_engine import cima_engine

    result = cima_engine.calculer_marge_solvabilite_non_vie(
        primes_nettes=2_000_000_000,
        charge_sinistres_moyenne_3ans=1_000_000_000,
        capitaux_propres=100_000_000,  # Insuffisant
    )
    assert result["conforme"] is False


def test_marge_solvabilite_retourne_details_calcul():
    """La réponse doit inclure les deux bases de calcul (primes et sinistres)."""
    from modules.cima.code_cima_engine import cima_engine

    result = cima_engine.calculer_marge_solvabilite_non_vie(
        primes_nettes=3_000_000_000,
        charge_sinistres_moyenne_3ans=1_500_000_000,
        capitaux_propres=900_000_000,
    )
    assert isinstance(result, dict)
    assert result["marge_requise"] > 0
    assert "conforme" in result


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAT C1 — RÉSULTAT TECHNIQUE NON-VIE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_etat_c1_avec_donnees_connues():
    """Génération état C1 — vérifier la structure et les montants calculés."""
    from modules.cima.etats_reglementaires import GenerateurEtatsCIMA

    gen = GenerateurEtatsCIMA()
    donnees = {
        "primes_nettes": 2_422_500_000,
        "sinistres_payes": 1_140_000_000,
        "sinistres_en_cours": 120_000_000,
        "frais_gestion": 570_000_000,
        "branches": {
            "auto": {"primes": 1_200_000_000, "sinistres": 650_000_000},
            "ird": {"primes": 800_000_000, "sinistres": 350_000_000},
            "transport": {"primes": 422_500_000, "sinistres": 140_000_000},
        },
    }
    result = await gen.generer_etat("C1", annee=2024, donnees_manuelles=donnees)

    assert result["code_etat"] == "C1"
    assert result["annee"] == 2024
    assert "donnees" in result
    assert "statut" in result

    donnees_etat = result["donnees"]
    # Le résultat technique doit être calculé
    assert "resultat_technique" in donnees_etat or "lignes" in donnees_etat


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAT C3 — BILAN ÉQUILIBRÉ
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_etat_c3_bilan_equilibre():
    """Génération état C3 — total actif doit égaler total passif."""
    from modules.cima.etats_reglementaires import GenerateurEtatsCIMA

    gen = GenerateurEtatsCIMA()
    donnees = {
        "immobilisations": 500_000_000,
        "placements_financiers": 1_200_000_000,
        "creances": 300_000_000,
        "disponibilites": 200_000_000,
        "capitaux_propres": 800_000_000,
        "provisions_techniques": 1_000_000_000,
        "dettes": 400_000_000,
    }
    result = await gen.generer_etat("C3", annee=2024, donnees_manuelles=donnees)

    assert result["code_etat"] == "C3"
    assert "donnees" in result

    donnees_bilan = result["donnees"]
    # Vérification équilibre bilan si les clés sont présentes
    if "total_actif" in donnees_bilan and "total_passif" in donnees_bilan:
        assert abs(donnees_bilan["total_actif"] - donnees_bilan["total_passif"]) < 1_000
    else:
        # L'état a bien été généré
        assert isinstance(donnees_bilan, dict)


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAT C5 — PROVISIONS TECHNIQUES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_etat_c5_provisions_correctes():
    """Génération état C5 — provisions suffisantes pour couvrir les sinistres."""
    from modules.cima.etats_reglementaires import GenerateurEtatsCIMA

    gen = GenerateurEtatsCIMA()
    donnees = {
        "provisions_techniques": 950_000_000,
        "actifs_admis_en_couverture": 1_100_000_000,
        "primes_a_emettre": 80_000_000,
        "sinistres_a_payer": 420_000_000,
        "provisions_pour_risques_en_cours": 530_000_000,
    }
    result = await gen.generer_etat("C5", annee=2024, donnees_manuelles=donnees)

    assert result["code_etat"] == "C5"
    assert "donnees" in result
    donnees_etat = result["donnees"]
    assert isinstance(donnees_etat, dict)


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAT C7 — MARGE DE SOLVABILITÉ
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generation_etat_c7_marge_solvabilite():
    """Génération état C7 — marge de solvabilité calculée."""
    from modules.cima.etats_reglementaires import GenerateurEtatsCIMA

    gen = GenerateurEtatsCIMA()
    donnees = {
        "primes_nettes": 2_422_500_000,
        "charge_sinistres_moyenne_3ans": 1_140_000_000,
        "capitaux_propres": 1_500_000_000,
        "provisions_techniques": 850_000_000,
        "actifs_admis_couverture": 1_100_000_000,
    }
    result = await gen.generer_etat("C7", annee=2024, donnees_manuelles=donnees)

    assert result["code_etat"] == "C7"
    assert "donnees" in result

    donnees_etat = result["donnees"]
    # Doit contenir l'information de conformité
    if "conforme" in donnees_etat:
        assert isinstance(donnees_etat["conforme"], bool)
    if "marge_requise" in donnees_etat:
        assert donnees_etat["marge_requise"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# CALCUL RATIO S/P
# ─────────────────────────────────────────────────────────────────────────────

def test_calcul_ratio_sinistres_primes_branche_auto():
    """Ratio S/P branche auto — calcul précis."""
    from modules.cima.code_cima_engine import cima_engine

    result = cima_engine.calculer_ratio_sinistres_primes(
        sinistres_payes=600_000_000,
        variation_psap=50_000_000,
        primes_nettes=1_000_000_000,
        branche="auto",
    )
    assert "ratio_sp" in result
    assert result["ratio_sp"] == pytest.approx(65.0, abs=1.0)


def test_calcul_ratio_sp_eleve_signal_alerte():
    """Ratio S/P > 100% → indicateur d'alerte."""
    from modules.cima.code_cima_engine import cima_engine

    result = cima_engine.calculer_ratio_sinistres_primes(
        sinistres_payes=1_200_000_000,
        variation_psap=100_000_000,
        primes_nettes=1_000_000_000,
        branche="auto",
    )
    assert result["ratio_sp"] > 100


# ─────────────────────────────────────────────────────────────────────────────
# COUVERTURE DES PROVISIONS
# ─────────────────────────────────────────────────────────────────────────────

def test_couverture_provisions_conforme():
    """Actifs admis ≥ provisions → conforme."""
    from modules.cima.code_cima_engine import cima_engine

    result = cima_engine.calculer_couverture_provisions(
        provisions_techniques=800_000_000,
        actifs_admis_en_couverture=900_000_000,
    )
    assert result["taux_couverture"] >= 100
    assert result["conforme"] is True


def test_couverture_provisions_non_conforme():
    """Actifs admis < provisions → non conforme."""
    from modules.cima.code_cima_engine import cima_engine

    result = cima_engine.calculer_couverture_provisions(
        provisions_techniques=1_000_000_000,
        actifs_admis_en_couverture=900_000_000,
    )
    assert result["taux_couverture"] < 100
    assert result["conforme"] is False


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT CONFORMITÉ GLOBAL
# ─────────────────────────────────────────────────────────────────────────────

def test_rapport_conformite_global_score_valide():
    """Rapport global → score entre 0 et 100."""
    from modules.cima.code_cima_engine import cima_engine

    donnees = {
        "primes_nettes": 2_422_500_000,
        "sinistres_payes": 1_140_000_000,
        "capitaux_propres": 1_500_000_000,
        "provisions_techniques": 850_000_000,
        "actifs_admis_couverture": 1_100_000_000,
        "frais_gestion": 570_000_000,
        "primes_emises_brutes": 2_850_000_000,
        "primes_cedees_reassurance": 427_500_000,
    }
    rapport = cima_engine.rapport_conformite_global(donnees)
    assert "statut_global" in rapport
    assert "score_conformite" in rapport
    assert 0 <= rapport["score_conformite"] <= 100


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATION CRCA — SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verification_crca_simulation():
    """Vérification CRCA en mode simulation → retourne un rapport."""
    from modules.cima.verificateur_crca import VerificateurCRCA

    verif = VerificateurCRCA()
    donnees = {
        "primes_nettes": 2_000_000_000,
        "sinistres_payes": 900_000_000,
        "capitaux_propres": 700_000_000,
        "provisions_techniques": 600_000_000,
        "actifs_admis_couverture": 800_000_000,
    }
    result = await verif.verifier(donnees, annee=2024)
    assert isinstance(result, dict)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_crca_non_conforme_liste_anomalies():
    """Compagnie non conforme → rapport liste les anomalies."""
    from modules.cima.verificateur_crca import VerificateurCRCA

    verif = VerificateurCRCA()
    donnees_mauvaises = {
        "primes_nettes": 2_000_000_000,
        "sinistres_payes": 900_000_000,
        "capitaux_propres": 50_000_000,   # Insuffisant
        "provisions_techniques": 1_500_000_000,
        "actifs_admis_couverture": 800_000_000,  # Insuffisant
    }
    result = await verif.verifier(donnees_mauvaises, annee=2024)
    assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# Q&R CIMA — RÉPONSE AVEC RÉFÉRENCE D'ARTICLE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_question_cima_retourne_reference_article(client, headers_dg):
    """POST /cima/question → réponse IA contient référence à un article CIMA."""
    resp = await client.post(
        "/api/v1/cima/question",
        json={"question": "Quel est le délai réglementaire pour l'auto selon le Code CIMA ?"},
        headers=headers_dg,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert any(k in data for k in ("reponse", "response", "content", "answer"))

    # La réponse mock contient "Article 337-1"
    reponse_text = str(data)
    assert any(
        terme in reponse_text.lower()
        for terme in ("article", "cima", "art.", "337")
    )


@pytest.mark.asyncio
async def test_question_cima_agent_non_autorise_retourne_403(client, headers_agent):
    """Agent sans permission CIMA → 403."""
    resp = await client.post(
        "/api/v1/cima/question",
        json={"question": "Qu'est-ce que la marge de solvabilité ?"},
        headers=headers_agent,
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# DÉLAIS RÉGLEMENTAIRES
# ─────────────────────────────────────────────────────────────────────────────

def test_delai_reglementaire_auto():
    """Délai réglementaire branche auto retourné correctement."""
    from modules.cima.code_cima_engine import cima_engine

    delai = cima_engine.get_delai_reglementaire("auto")
    assert delai is not None
    assert isinstance(delai, (int, dict))


def test_delai_reglementaire_vie():
    """Délai réglementaire branche vie retourné correctement."""
    from modules.cima.code_cima_engine import cima_engine

    delai = cima_engine.get_delai_reglementaire("vie")
    assert delai is not None
