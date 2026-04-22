"""Agent Placement & Actuariat — gestion des actifs, ALM, projections actuarielles."""
from __future__ import annotations
import json, logging, math
from datetime import date
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.placement_actuariat")

# ─── Tables et constantes actuarielles ───────────────────────────────────────

# Taux technique réglementaire CIMA
TAUX_TECH_CIMA = 0.035  # 3.5% max (Art. 338 CIMA Livre II)
TAUX_TECH_NONVIE = 0.035

# Allocation cible actifs (% du portefeuille) — norme CIMA Art. 335
_ALLOCATION_CIBLE = {
    "obligations_etat":   0.40,   # ≥ 34% CIMA
    "obligations_corp":   0.15,
    "actions_cotees":     0.15,   # ≤ 30% CIMA
    "immobilier":         0.15,   # ≤ 40% CIMA
    "depot_terme":        0.10,
    "fonds_monetaires":   0.05,
}

# Rendements cibles par classe d'actif (%)
_RENDEMENT_ACTIF = {
    "obligations_etat":   5.5,
    "obligations_corp":   7.0,
    "actions_cotees":     10.0,
    "immobilier":         8.0,
    "depot_terme":        5.0,
    "fonds_monetaires":   4.0,
}

# Limites réglementaires CIMA (% de l'actif total) Art. 335
_LIMITES_REGLEMENTAIRES = {
    "obligations_etat":   (0.34, 1.0),    # min 34%
    "obligations_corp":   (0.0,  0.30),
    "actions_cotees":     (0.0,  0.30),
    "immobilier":         (0.0,  0.40),
    "depot_terme":        (0.0,  0.15),
    "fonds_monetaires":   (0.0,  0.10),
}

# Table de mortalité TD 88-90 adaptée CRRAE/CIMA (qx × 1000)
_TABLE_MORTALITE_TD8890 = {
    20: 1.2,  25: 1.5,  30: 1.9,  35: 2.6,  40: 3.8,
    45: 5.9,  50: 9.2,  55: 14.5, 60: 22.0, 65: 35.0, 70: 55.0,
}


def _taux_mortalite(age: int) -> float:
    """Interpolation linéaire taux de mortalité pour un âge donné."""
    ages = sorted(_TABLE_MORTALITE_TD8890.keys())
    if age <= ages[0]:
        return _TABLE_MORTALITE_TD8890[ages[0]] / 1000
    if age >= ages[-1]:
        return _TABLE_MORTALITE_TD8890[ages[-1]] / 1000
    for i in range(len(ages) - 1):
        if ages[i] <= age <= ages[i + 1]:
            a1, a2 = ages[i], ages[i + 1]
            q1, q2 = _TABLE_MORTALITE_TD8890[a1], _TABLE_MORTALITE_TD8890[a2]
            return (q1 + (q2 - q1) * (age - a1) / (a2 - a1)) / 1000
    return 0.01


def _calculer_duration_obligation(
    valeur_nominale: float,
    coupon_pct: float,
    maturite_annees: int,
    taux_marche: float,
) -> dict:
    """Duration de Macaulay et duration modifiée."""
    c = coupon_pct / 100
    r = taux_marche / 100
    flux_actualises = 0.0
    prix = 0.0
    duree_ponderee = 0.0
    for t in range(1, maturite_annees + 1):
        flux = valeur_nominale * c
        if t == maturite_annees:
            flux += valeur_nominale
        pv_flux = flux / (1 + r) ** t
        prix += pv_flux
        duree_ponderee += t * pv_flux
    duration_macaulay = duree_ponderee / prix if prix else 0
    duration_modifiee = duration_macaulay / (1 + r)
    return {
        "prix_fcfa":           round(prix),
        "duration_macaulay":   round(duration_macaulay, 3),
        "duration_modifiee":   round(duration_modifiee, 3),
        "sensibilite_100bp":   round(-duration_modifiee * 0.01 * prix),  # var prix si +100bp
    }


def _calculer_rendement_portefeuille(actifs: dict[str, float]) -> dict:
    """Calcule le rendement moyen pondéré du portefeuille."""
    total = sum(actifs.values())
    if total == 0:
        return {"rendement_pondere_pct": 0, "total_fcfa": 0}
    rendement = 0.0
    details = {}
    conformite = []
    for classe, montant in actifs.items():
        poids = montant / total
        rend  = _RENDEMENT_ACTIF.get(classe, 5.0)
        rendement += poids * rend
        details[classe] = {
            "montant_fcfa": round(montant),
            "poids_pct":    round(poids * 100, 2),
            "rendement_pct": rend,
            "revenu_fcfa":   round(montant * rend / 100),
        }
        lim_min, lim_max = _LIMITES_REGLEMENTAIRES.get(classe, (0, 1))
        ok = lim_min <= poids <= lim_max
        if not ok:
            conformite.append(f"ALERTE {classe}: {poids*100:.1f}% hors limite [{lim_min*100:.0f}%-{lim_max*100:.0f}%]")
    return {
        "total_fcfa":              round(total),
        "rendement_pondere_pct":   round(rendement, 3),
        "revenu_annuel_fcfa":      round(total * rendement / 100),
        "details_classes":         details,
        "alertes_conformite_cima": conformite,
        "conforme_art335":         len(conformite) == 0,
    }


def _stress_test_actifs(
    portefeuille: dict[str, float],
    scenario: str,
) -> dict:
    """Stress tests réglementaires CIMA — Art. 337."""
    chocs = {
        "taux_hausse_200bp": {
            "obligations_etat":   -0.12,
            "obligations_corp":   -0.15,
            "actions_cotees":     0.0,
            "immobilier":         0.0,
            "depot_terme":        0.0,
            "fonds_monetaires":   0.0,
        },
        "actions_krach_40pct": {
            "obligations_etat":   0.0,
            "obligations_corp":   0.0,
            "actions_cotees":     -0.40,
            "immobilier":         -0.10,
            "depot_terme":        0.0,
            "fonds_monetaires":   0.0,
        },
        "immobilier_chute_25pct": {
            "obligations_etat":   0.0,
            "obligations_corp":   0.0,
            "actions_cotees":     -0.05,
            "immobilier":         -0.25,
            "depot_terme":        0.0,
            "fonds_monetaires":   0.0,
        },
    }
    choc = chocs.get(scenario, chocs["taux_hausse_200bp"])
    total_avant = sum(portefeuille.values())
    total_apres = 0.0
    for classe, montant in portefeuille.items():
        impact = choc.get(classe, 0)
        total_apres += montant * (1 + impact)
    perte = total_avant - total_apres
    return {
        "scenario":               scenario,
        "valeur_avant_fcfa":      round(total_avant),
        "valeur_apres_fcfa":      round(total_apres),
        "perte_fcfa":             round(perte),
        "perte_pct":              round(perte / total_avant * 100, 2) if total_avant else 0,
        "ratio_couverture_avant": round(total_avant / (total_avant * 0.85) * 100, 1),
        "ratio_couverture_apres": round(total_apres / (total_avant * 0.85) * 100, 1),
    }


class AgentPlacementActuariat(BaseAgent):
    type_agent = TypeAgent.PLACEMENT

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Placement & Actuariat de YukpoAssurance, expert en gestion d'actifs et actuariat CIMA.

MISSIONS PLACEMENT (Art. 335-337 CIMA) :
- Gestion portefeuille actifs représentatifs : obligations, actions, immobilier, dépôts
- Respect des règles de dispersion et limites CIMA par classe d'actif
- Optimisation rendement / duration (ALM — adossement actif-passif)
- Reporting investissements au Conseil d'Administration

MISSIONS ACTUARIAT :
- Calcul et validation des provisions mathématiques (PM) vie
- Tables de mortalité et barèmes actuariels
- Projections financières long terme (scenarios 5-20 ans)
- Stress tests réglementaires (Art. 337-1 CIMA)
- Calcul du ratio de solvabilité (marge de solvabilité / minimum requis)

ORDRE D'EXÉCUTION — Revue mensuelle :
1. analyser_portefeuille → composition actuelle vs allocation cible
2. calculer_rendement_portefeuille → rendement pondéré par classe
3. verifier_conformite_art335 → limites réglementaires
4. alm_adossement → duration actif vs duration passif
5. stress_test → scenarios réglementaires
6. recommander_arbitrage → ajustements si nécessaire (IA)
7. soumettre_rapport_ca → validation Conseil

CALCULS DÉTERMINISTES :
- Rendements, duration, prix obligations : formules standard
- Provisions mathématiques : méthode prospective, tables TD 88-90
- Ratio de solvabilité : Art. 337-1 CIMA

RÈGLES ABSOLUES :
- 0 IA pour calculs actuariels et de placement (déterministe)
- IA uniquement pour recommandations narratives et rapports
- Arbitrage portefeuille ≥ 10M FCFA → validation DG obligatoire"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "analyser_portefeuille",
                "description": "Analyse la composition actuelle du portefeuille vs allocation cible CIMA",
                "input_schema": {"type": "object", "properties": {
                    "actifs": {
                        "type": "object",
                        "description": "Valeur par classe d'actif en FCFA",
                        "properties": {
                            "obligations_etat": {"type": "number"},
                            "obligations_corp":  {"type": "number"},
                            "actions_cotees":    {"type": "number"},
                            "immobilier":        {"type": "number"},
                            "depot_terme":       {"type": "number"},
                            "fonds_monetaires":  {"type": "number"},
                        },
                    },
                    "date_valeur": {"type": "string"},
                }, "required": ["actifs"]},
            },
            {
                "name": "calculer_duration_obligation",
                "description": "Calcule la duration de Macaulay et duration modifiée d'une obligation",
                "input_schema": {"type": "object", "properties": {
                    "valeur_nominale": {"type": "number"},
                    "coupon_pct":      {"type": "number"},
                    "maturite_annees": {"type": "integer"},
                    "taux_marche_pct": {"type": "number"},
                    "emetteur":        {"type": "string"},
                    "isin":            {"type": "string"},
                }, "required": ["valeur_nominale", "coupon_pct", "maturite_annees", "taux_marche_pct"]},
            },
            {
                "name": "calculer_provisions_mathematiques",
                "description": "Calcule les PM prospectives du portefeuille vie (déterministe, tables CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "polices_vie": {
                        "type": "array",
                        "description": "Liste des contrats vie actifs",
                        "items": {
                            "type": "object",
                            "properties": {
                                "police_id":     {"type": "string"},
                                "age_souscription": {"type": "integer"},
                                "age_actuel":    {"type": "integer"},
                                "duree_totale":  {"type": "integer"},
                                "capital":       {"type": "number"},
                                "type_produit":  {"type": "string"},
                                "prime_annuelle": {"type": "number"},
                            },
                        },
                    },
                    "taux_tech_pct": {"type": "number", "description": "Taux technique (max 3.5% CIMA)"},
                }, "required": ["polices_vie"]},
            },
            {
                "name": "stress_test_actifs",
                "description": "Exécute les stress tests réglementaires CIMA Art. 337-1",
                "input_schema": {"type": "object", "properties": {
                    "actifs": {"type": "object"},
                    "scenarios": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["taux_hausse_200bp", "actions_krach_40pct", "immobilier_chute_25pct"]
                        },
                    },
                }, "required": ["actifs"]},
            },
            {
                "name": "calculer_ratio_solvabilite",
                "description": "Calcule le ratio de solvabilité réglementaire CIMA Art. 337-1",
                "input_schema": {"type": "object", "properties": {
                    "fonds_propres_fcfa":    {"type": "number"},
                    "provisions_tech_fcfa":  {"type": "number"},
                    "primes_brutes_fcfa":    {"type": "number"},
                    "sinistres_bruts_fcfa":  {"type": "number"},
                    "actifs_total_fcfa":     {"type": "number"},
                }, "required": ["fonds_propres_fcfa", "provisions_tech_fcfa", "primes_brutes_fcfa"]},
            },
            {
                "name": "alm_adossement",
                "description": "Analyse l'adossement actif-passif (duration matching)",
                "input_schema": {"type": "object", "properties": {
                    "duration_passif":    {"type": "number", "description": "Duration engagement passif (années)"},
                    "actifs_durations":   {"type": "object", "description": "Duration par classe actif"},
                    "actifs_montants":    {"type": "object"},
                }, "required": ["duration_passif", "actifs_montants"]},
            },
            {
                "name": "recommander_arbitrage",
                "description": "Recommande des arbitrages de portefeuille via IA sur base de l'analyse",
                "input_schema": {"type": "object", "properties": {
                    "analyse_portefeuille": {"type": "object"},
                    "contraintes":          {"type": "string", "description": "Contraintes de marché ou réglementaires"},
                    "horizon":              {"type": "string", "enum": ["court_terme", "moyen_terme", "long_terme"]},
                }, "required": ["analyse_portefeuille"]},
            },
            {
                "name": "soumettre_rapport_investissements",
                "description": "Soumet le rapport mensuel investissements pour validation CA/DG",
                "input_schema": {"type": "object", "properties": {
                    "periode":              {"type": "string"},
                    "rendement_pct":        {"type": "number"},
                    "valeur_portefeuille":  {"type": "number"},
                    "conformite_cima":      {"type": "boolean"},
                    "alertes":              {"type": "array", "items": {"type": "string"}},
                }, "required": ["periode", "rendement_pct", "valeur_portefeuille"]},
            },
            {
                "name": "projections_actuarielles",
                "description": "Projections financières à 5/10/20 ans (survie, besoin PM, flux)",
                "input_schema": {"type": "object", "properties": {
                    "nb_assures_vie":       {"type": "integer"},
                    "age_moyen":            {"type": "integer"},
                    "pm_totale_fcfa":       {"type": "number"},
                    "prime_annuelle_total": {"type": "number"},
                    "horizon_ans":          {"type": "integer", "enum": [5, 10, 20]},
                    "taux_croissance_pct":  {"type": "number"},
                }, "required": ["nb_assures_vie", "age_moyen", "pm_totale_fcfa", "horizon_ans"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT PLACEMENT & ACTUARIAT — quand demander une information :

1. HORIZON D'INVESTISSEMENT NON DÉFINI
   → "Sur quel horizon d'investissement souhaitez-vous optimiser le portefeuille d'actifs ? (Détermine la duration cible pour l'adossement actif-passif Art. 335 CIMA)"
   type_reponse: choix_multiple  choix: ["Court terme (< 1 an)", "Moyen terme (1 à 5 ans)", "Long terme (> 5 ans)", "ALM intégral (adossement passif vie)"]

2. TYPE D'ACTIF CIBLE NON PRÉCISÉ
   → "Sur quelle classe d'actifs souhaitez-vous concentrer l'analyse ou l'investissement ?"
   type_reponse: choix_multiple  choix: ["Obligations d'État CEMAC / CEDEAO", "Actions cotées (bourse régionale BRVM)", "Immobilier (actif représentatif Art. 335)", "Dépôts bancaires à terme", "OPCVM / fonds d'investissement", "Analyse globale du portefeuille actuel"]

3. MONTANT DISPONIBLE À INVESTIR MANQUANT
   → "Quel est le montant disponible à investir ou à réallouer dans le portefeuille (en FCFA) ?"
   type_reponse: nombre

4. PROFIL DE RISQUE / TOLÉRANCE INCERTAINE
   → "Quelle est la tolérance au risque pour ce portefeuille ?"
   type_reponse: choix_multiple  choix: ["Sécuritaire (capital garanti, obligations souveraines uniquement)", "Modéré (obligations + 20% actions max)", "Dynamique (obligations + actions + immobilier)", "Selon les contraintes CIMA Art. 335-337 strictes"]

5. DONNÉES PORTEFEUILLE VIE POUR CALCUL ACTUARIEL
   → "Pour le calcul actuariel, j'ai besoin du portefeuille vie. Pouvez-vous me communiquer le nombre d'assurés vie et l'âge moyen ?"
   type_reponse: texte_libre

6. TAUX TECHNIQUE APPLIQUÉ (PM vie)
   → "Quel est le taux technique garanti appliqué aux provisions mathématiques de ce portefeuille vie ? (Min 3,5% selon Art. 63 CIMA)"
   type_reponse: nombre

7. STRESS TEST — SCÉNARIO DE CHOC
   → "Quel scénario de stress test souhaitez-vous appliquer ?"
   type_reponse: choix_multiple  choix: ["Choc taux d'intérêt +200 bp", "Choc actions -30%", "Choc immobilier -20%", "Choc mortalité +20% (pandémie)", "Scénario catastrophe naturelle zone CIMA", "Scénario combiné (multi-chocs)"]

PROGRESSION : Type analyse → Horizon → Classe d'actifs → Montants → Contraintes CIMA.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "analyser_portefeuille":
                actifs = params["actifs"]
                result = _calculer_rendement_portefeuille(actifs)
                # Calcul écarts vs allocation cible
                total  = result["total_fcfa"]
                ecarts = {}
                for classe, cible_pct in _ALLOCATION_CIBLE.items():
                    actuel = actifs.get(classe, 0)
                    poids  = actuel / total if total else 0
                    ecarts[classe] = {
                        "actuel_pct": round(poids * 100, 2),
                        "cible_pct":  cible_pct * 100,
                        "ecart_pct":  round((poids - cible_pct) * 100, 2),
                    }
                result["ecarts_allocation"] = ecarts
                result["date_valeur"] = params.get("date_valeur", date.today().isoformat())
                return json.dumps(result, ensure_ascii=False, indent=2)

            if nom == "calculer_duration_obligation":
                result = _calculer_duration_obligation(
                    valeur_nominale=params["valeur_nominale"],
                    coupon_pct=params["coupon_pct"],
                    maturite_annees=params["maturite_annees"],
                    taux_marche=params["taux_marche_pct"],
                )
                result["emetteur"] = params.get("emetteur", "")
                result["isin"]     = params.get("isin", "")
                return json.dumps(result, ensure_ascii=False)

            if nom == "calculer_provisions_mathematiques":
                taux = min(params.get("taux_tech_pct", 3.5), 3.5) / 100  # Art. 338 CIMA : max 3.5%
                polices = params.get("polices_vie", [])
                total_pm = 0.0
                details  = []
                for p in polices:
                    age_s = p.get("age_souscription", 30)
                    age_a = p.get("age_actuel", age_s)
                    duree = p.get("duree_totale", 20)
                    cap   = p.get("capital", 5_000_000)
                    prime = p.get("prime_annuelle", cap * 0.02)
                    duree_restante = duree - (age_a - age_s)
                    if duree_restante <= 0:
                        continue
                    # PM prospective simplifiée
                    qx   = _taux_mortalite(age_a)
                    ax   = sum(
                        cap * qx * (1 + qx * 0.5) ** k / (1 + taux) ** (k + 1)
                        for k in range(duree_restante)
                    )
                    axn  = sum(
                        1.0 / (1 + taux) ** (k + 1) * (1 - qx) ** k
                        for k in range(duree_restante)
                    )
                    pm = max(ax - prime * axn, 0)
                    total_pm += pm
                    details.append({
                        "police_id": p.get("police_id", ""),
                        "age_actuel": age_a,
                        "duree_restante": duree_restante,
                        "pm_fcfa": round(pm),
                    })
                return json.dumps({
                    "total_pm_fcfa": round(total_pm),
                    "nb_polices":    len(details),
                    "taux_tech_pct": taux * 100,
                    "details":       details[:10],  # limiter réponse
                    "methode":       "prospective_td8890_cima",
                }, ensure_ascii=False, indent=2)

            if nom == "stress_test_actifs":
                actifs    = params["actifs"]
                scenarios = params.get("scenarios", [
                    "taux_hausse_200bp", "actions_krach_40pct", "immobilier_chute_25pct"
                ])
                resultats = {}
                for sc in scenarios:
                    resultats[sc] = _stress_test_actifs(actifs, sc)
                pire_cas = min(resultats.values(), key=lambda r: r["valeur_apres_fcfa"])
                return json.dumps({
                    "scenarios": resultats,
                    "pire_cas":  pire_cas["scenario"],
                    "perte_max_fcfa": pire_cas["perte_fcfa"],
                    "recommandation": "Renforcer fonds propres" if pire_cas["ratio_couverture_apres"] < 100 else "Solvabilité maintenue dans tous les scénarios",
                }, ensure_ascii=False, indent=2)

            if nom == "calculer_ratio_solvabilite":
                fp    = params["fonds_propres_fcfa"]
                pt    = params["provisions_tech_fcfa"]
                pb    = params["primes_brutes_fcfa"]
                sb    = params["sinistres_bruts_fcfa"]
                # Marge minimale CIMA = max(16% primes, 23% sinistres) Art. 337-1
                marge_min_primes   = pb * 0.16
                marge_min_sinistres = sb * 0.23
                marge_min          = max(marge_min_primes, marge_min_sinistres)
                ratio              = fp / marge_min * 100 if marge_min else 0
                return json.dumps({
                    "fonds_propres_fcfa":        round(fp),
                    "marge_solvabilite_min_fcfa": round(marge_min),
                    "ratio_solvabilite_pct":      round(ratio, 1),
                    "conforme_art337":            ratio >= 100,
                    "statut": "CONFORME" if ratio >= 100 else ("ALERTE" if ratio >= 90 else "INSUFFISANT"),
                    "commentaire": f"{'✓ Solvabilité satisfaisante' if ratio >= 100 else f'⚠ Déficit estimé à {round(marge_min - fp):,} FCFA'.replace(',', ' ')}",
                }, ensure_ascii=False)

            if nom == "alm_adossement":
                dur_passif = params["duration_passif"]
                montants   = params["actifs_montants"]
                durations  = params.get("actifs_durations", {
                    "obligations_etat": 5.0,
                    "obligations_corp": 4.0,
                    "actions_cotees":   1.5,
                    "immobilier":       8.0,
                    "depot_terme":      1.0,
                    "fonds_monetaires": 0.25,
                })
                total = sum(montants.values())
                dur_actif = sum(
                    montants.get(k, 0) / total * durations.get(k, 3.0)
                    for k in montants
                ) if total else 0
                gap = dur_actif - dur_passif
                return json.dumps({
                    "duration_actif_annees":  round(dur_actif, 2),
                    "duration_passif_annees": round(dur_passif, 2),
                    "gap_duration":           round(gap, 2),
                    "statut_alm": "OK" if abs(gap) <= 0.5 else ("SOUS_IMMUNISE" if gap < -0.5 else "SUR_IMMUNISE"),
                    "recommandation": (
                        "Portefeuille bien adossé" if abs(gap) <= 0.5
                        else f"Allonger la duration actif de {abs(gap):.1f} ans" if gap < -0.5
                        else f"Raccourcir la duration actif de {gap:.1f} ans"
                    ),
                }, ensure_ascii=False)

            if nom == "projections_actuarielles":
                n      = params["nb_assures_vie"]
                age    = params["age_moyen"]
                pm     = params["pm_totale_fcfa"]
                prime  = params.get("prime_annuelle_total", pm * 0.05)
                crois  = params.get("taux_croissance_pct", 5.0) / 100
                horiz  = params["horizon_ans"]
                taux   = TAUX_TECH_CIMA
                proj   = []
                n_actuel = n
                pm_actuel = pm
                for annee in range(1, horiz + 1):
                    qx      = _taux_mortalite(age + annee)
                    deces   = round(n_actuel * qx)
                    n_actuel = max(n_actuel - deces + round(n * crois), 0)
                    pm_actuel = pm_actuel * (1 + taux) + prime * n_actuel - deces * (pm_actuel / max(n_actuel, 1))
                    proj.append({
                        "annee":        annee,
                        "assures":      n_actuel,
                        "deces_estimes": deces,
                        "pm_totale_fcfa": round(pm_actuel),
                    })
                return json.dumps({
                    "horizon_ans": horiz,
                    "projections": proj,
                    "pm_finale_fcfa": round(pm_actuel),
                    "croissance_portefeuille": f"{crois*100:.1f}%/an",
                }, ensure_ascii=False, indent=2)

            if nom == "recommander_arbitrage":
                from core.ia_client import ModeIA, ia_client
                analyse = json.dumps(params["analyse_portefeuille"], ensure_ascii=False, indent=2)
                prompt = f"""Tu es actuaire et gérant de portefeuille pour une compagnie d'assurance CIMA.

Analyse du portefeuille actuel :
{analyse}

Contraintes : {params.get('contraintes', 'Standard CIMA Art. 335')}
Horizon : {params.get('horizon', 'moyen_terme')}

Recommande des arbitrages précis (acheter/vendre par classe d'actif, montants FCFA)
en respectant les limites réglementaires CIMA. Justifie chaque recommandation."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            if nom == "soumettre_rapport_investissements":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type":              "rapport_investissements",
                    "periode":           params["periode"],
                    "rendement_pct":     params["rendement_pct"],
                    "valeur_portefeuille": params["valeur_portefeuille"],
                    "conformite_cima":   params.get("conformite_cima", True),
                    "alertes":           params.get("alertes", []),
                    "user_id":           user_id,
                    "execution_id":      execution_id,
                })
                return (
                    f"Rapport investissements {params['periode']} soumis pour validation CA\n"
                    f"Rendement : {params['rendement_pct']:.2f}% — "
                    f"Portefeuille : {params['valeur_portefeuille']:,.0f} FCFA"
                ).replace(",", " ")

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentPlacementActuariat] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
