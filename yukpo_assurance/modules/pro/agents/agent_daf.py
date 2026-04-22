"""
AgentDAF — Agent IA spécialisé pour les DAF africains.

Outils métier :
  - budget_analyser        : Analyse et contrôle budgétaire
  - cashflow_projeter      : Projection de trésorerie (3/6/12 mois)
  - ratios_calculer        : Calcul des ratios financiers (liquidité, solvabilité, rentabilité)
  - investissement_evaluer : Évaluation d'investissement (VAN, TRI, délai récupération)
  - boardpack_generer      : Contenu board pack pour la direction / CA

Expertise :
  - Analyse financière et contrôle de gestion
  - Gestion de trésorerie (cash management)
  - Reporting SYSCOHADA / IFRS simplifié
  - Financement : dette, capital, leasing
  - Budget et prévisions

PATTERNS YUKPOASSURANCE :
  - Calculs déterministes en fonctions standalone (hors classe)
  - type_agent = TypeAgent.PRO_DAF
  - _necessite_validation() → hérité de AgentProBase (retourne False)
  - _prompt_questions_specifiques() implémenté
"""
from __future__ import annotations

import logging
from math import inf

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_daf")


# ══════════════════════════════════════════════════════════════════════════════
# Fonctions de calcul standalone — déterministes, testables hors classe
# ══════════════════════════════════════════════════════════════════════════════

def _analyser_budget(budget: dict, realise: dict, periode: str = "Période") -> dict:
    """
    Analyse d'exécution budgétaire ligne par ligne.
    Retourne un dict avec lignes, alertes et totaux.
    """
    toutes_lignes = sorted(set(list(budget.keys()) + list(realise.keys())))
    resultats = []
    alertes   = []

    total_bud, total_rea = 0.0, 0.0

    for ligne in toutes_lignes:
        bud   = float(budget.get(ligne, 0))
        rea   = float(realise.get(ligne, 0))
        ecart = rea - bud
        pct   = (ecart / bud * 100) if bud != 0 else 0.0
        total_bud += bud
        total_rea += rea

        niveau = "ok"
        if abs(pct) >= 15:
            niveau = "alerte"
            alertes.append({"ligne": ligne, "pct": pct, "ecart": ecart})
        elif abs(pct) >= 5:
            niveau = "attention"

        resultats.append({
            "ligne":  ligne,
            "budget": bud,
            "realise": rea,
            "ecart":  ecart,
            "pct":    round(pct, 1),
            "niveau": niveau,
        })

    ecart_total = total_rea - total_bud
    pct_total   = (ecart_total / total_bud * 100) if total_bud != 0 else 0.0

    return {
        "periode":      periode,
        "lignes":       resultats,
        "alertes":      alertes,
        "total_budget": total_bud,
        "total_realise": total_rea,
        "ecart_total":  ecart_total,
        "pct_total":    round(pct_total, 1),
    }


def _projeter_cashflow(
    encaissements: dict,
    decaissements: dict,
    solde_initial: float = 0.0,
    horizon_mois:  int   = 6,
    ligne_credit:  float = 0.0,
) -> dict:
    """
    Projection mensuelle de trésorerie.
    Accepte un dict {label: montant} ou liste ordonnée.
    """
    mois_labels = [
        "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
        "Juil", "Août", "Sep", "Oct", "Nov", "Déc"
    ]

    enc_vals = list(encaissements.values())
    dec_vals = list(decaissements.values())
    n_enc    = len(enc_vals)
    n_dec    = len(dec_vals)
    moy_enc  = sum(enc_vals) / n_enc if n_enc else 0.0
    moy_dec  = sum(dec_vals) / n_dec if n_dec else 0.0

    mois_data = []
    solde     = solde_initial
    alertes   = []

    for i in range(min(horizon_mois, 12)):
        label = mois_labels[i]
        enc   = float(enc_vals[i] if i < n_enc else moy_enc)
        dec   = float(dec_vals[i] if i < n_dec else moy_dec)
        flux  = enc - dec
        solde += flux

        statut = "ok"
        if solde < 0:
            statut = "credit" if (ligne_credit > 0 and abs(solde) <= ligne_credit) else "deficit"
            alertes.append({"mois": label, "solde": solde, "statut": statut})
        elif solde < dec * 0.5:
            statut = "faible"

        mois_data.append({
            "mois":   label,
            "enc":    enc,
            "dec":    dec,
            "flux":   flux,
            "solde":  solde,
            "statut": statut,
        })

    return {
        "solde_initial":  solde_initial,
        "horizon_mois":   horizon_mois,
        "ligne_credit":   ligne_credit,
        "mois":           mois_data,
        "alertes":        alertes,
        "solde_final":    solde,
    }


def _calculer_ratios(bilan: dict, resultat: dict) -> dict:
    """Calcule les ratios financiers à partir des postes du bilan et du compte de résultat."""
    def g(d, *keys, default=0.0):
        for k in keys:
            if k in d:
                return float(d[k])
        return default

    ac   = g(bilan, "actif_circulant")
    ai   = g(bilan, "actif_immob")
    stk  = g(bilan, "stocks")
    cr   = g(bilan, "creances")
    dsp  = g(bilan, "disponibilites")
    kp   = g(bilan, "capitaux_propres")
    dlt  = g(bilan, "dettes_lt")
    dct  = g(bilan, "dettes_ct")
    ca   = g(resultat, "CA", "chiffre_affaires")
    ebit = g(resultat, "ebitda", "marge_brute")
    rn   = g(resultat, "resultat_net")

    total_actif = ai + ac
    total_dette = dlt + dct

    ratios = {}

    # Liquidité
    if dct > 0:
        ratios["liquidite_generale"]  = round(ac / dct, 3)
        ratios["liquidite_reduite"]   = round((cr + dsp) / dct, 3)
        ratios["liquidite_immediate"] = round(dsp / dct, 3)

    # Solvabilité
    if total_actif > 0:
        ratios["autonomie_financiere_pct"] = round(kp / total_actif * 100, 1)
    if kp > 0:
        ratios["ratio_endettement"] = round(total_dette / kp, 3)
    elif total_dette > 0:
        ratios["ratio_endettement"] = float("inf")

    # Rentabilité
    if ca > 0:
        if ebit > 0:
            ratios["marge_ebitda_pct"] = round(ebit / ca * 100, 1)
        if rn != 0:
            ratios["marge_nette_pct"] = round(rn / ca * 100, 1)
    if kp > 0 and rn != 0:
        ratios["roe_pct"] = round(rn / kp * 100, 1)

    # Gestion
    if ca > 0 and stk > 0:
        rotation = ca / stk
        ratios["rotation_stocks"]    = round(rotation, 2)
        ratios["delai_stocks_jours"] = round(365 / rotation, 1)
    if ca > 0 and cr > 0:
        ratios["dso_jours"] = round(cr / ca * 365, 1)

    return ratios


def _evaluer_investissement(
    investissement_initial: float,
    flux_tresorerie: list[float],
    taux_actualisation:  float,
    valeur_residuelle: float = 0.0,
) -> dict:
    """Calcule VAN, TRI (dichotomie), délai de récupération et IP."""
    flux = list(flux_tresorerie)
    if valeur_residuelle > 0 and flux:
        flux[-1] = flux[-1] + valeur_residuelle

    # VAN
    van = -investissement_initial + sum(
        f / (1 + taux_actualisation) ** (i + 1) for i, f in enumerate(flux)
    )

    # TRI — dichotomie
    def _npv(r: float) -> float:
        return -investissement_initial + sum(f / (1 + r) ** (i + 1) for i, f in enumerate(flux))

    tri = None
    try:
        lo, hi = 0.001, 5.0
        for _ in range(120):
            mid = (lo + hi) / 2
            if _npv(mid) > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo < 0.00005:
                break
        tri = round((lo + hi) / 2, 5)
    except Exception:
        tri = None

    # Délai de récupération (non actualisé)
    cumul = -investissement_initial
    delai = None
    for i, f in enumerate(flux):
        cumul += f
        if cumul >= 0 and delai is None:
            delai = i + 1

    # Indice de profitabilité
    ip = round((van + investissement_initial) / investissement_initial, 4) if investissement_initial else 0

    # Flux actualisés
    flux_actualisés = [
        {"annee": i + 1, "flux": f, "va": round(f / (1 + taux_actualisation) ** (i + 1), 0)}
        for i, f in enumerate(flux)
    ]

    return {
        "investissement":   investissement_initial,
        "taux_pct":         round(taux_actualisation * 100, 2),
        "nb_annees":        len(flux),
        "van":              round(van, 0),
        "van_positive":     van > 0,
        "tri_pct":          round(tri * 100, 2) if tri is not None else None,
        "tri_superieur":    (tri > taux_actualisation) if tri is not None else None,
        "delai_ans":        delai,
        "ip":               ip,
        "ip_positif":       ip > 1,
        "flux_actualisés":  flux_actualisés,
    }


# ── Rendus texte ──────────────────────────────────────────────────────────────

def _rendu_budget(a: dict) -> str:
    """Formate l'analyse budgétaire en texte."""
    lignes = [f"ANALYSE BUDGÉTAIRE — {a['periode']}\n"]
    lignes.append(
        f"{'Ligne':30} {'Budget':>14} {'Réalisé':>14} {'Écart':>14} {'%':>7}"
    )
    lignes.append("─" * 82)

    for r in a["lignes"]:
        icon = "⚠️  " if r["niveau"] == "alerte" else ("!  " if r["niveau"] == "attention" else "   ")
        lignes.append(
            f"{icon}{r['ligne']:<28} {r['budget']:>14,.0f} {r['realise']:>14,.0f} "
            f"{r['ecart']:>+14,.0f} {r['pct']:>+6.1f}%"
        )

    lignes.append("─" * 82)
    lignes.append(
        f"{'TOTAL':30} {a['total_budget']:>14,.0f} {a['total_realise']:>14,.0f} "
        f"{a['ecart_total']:>+14,.0f} {a['pct_total']:>+6.1f}%"
    )

    if a["alertes"]:
        lignes.append(f"\n⚠️  ÉCARTS SIGNIFICATIFS (> ±15%) :")
        for al in a["alertes"]:
            lignes.append(f"  - {al['ligne']} : {al['pct']:+.1f}%  ({al['ecart']:+,.0f} FCFA)")

    return "\n".join(lignes)


def _rendu_cashflow(r: dict) -> str:
    """Formate la projection de trésorerie en texte."""
    lignes = [f"PROJECTION TRÉSORERIE — {r['horizon_mois']} mois\n"]
    lignes.append(
        f"{'Mois':<8} {'Encaissements':>16} {'Décaissements':>16} "
        f"{'Flux net':>13} {'Solde':>16} {'État':>8}"
    )
    lignes.append("─" * 83)

    etats = {"ok": "✅", "faible": "⚠️  LBL", "credit": "⚡ CRD", "deficit": "❌ DFT"}
    for m in r["mois"]:
        lignes.append(
            f"{m['mois']:<8} {m['enc']:>16,.0f} {m['dec']:>16,.0f} "
            f"{m['flux']:>+13,.0f} {m['solde']:>16,.0f} {etats.get(m['statut'], ''):>8}"
        )

    lignes.append(f"\nSolde initial  : {r['solde_initial']:,.0f} FCFA")
    lignes.append(f"Solde final    : {r['solde_final']:,.0f} FCFA")
    if r["ligne_credit"] > 0:
        lignes.append(f"Ligne de crédit: {r['ligne_credit']:,.0f} FCFA")

    if r["alertes"]:
        lignes.append("\n⚠️  RISQUES DE TRÉSORERIE IDENTIFIÉS :")
        for al in r["alertes"]:
            lignes.append(f"  {al['mois']} : solde {al['solde']:,.0f} FCFA ({al['statut']})")
        lignes += [
            "\nACTIONS RECOMMANDÉES :",
            "  - Accélérer les encaissements (relance clients, escompte)",
            "  - Négocier les délais de paiement fournisseurs",
            "  - Activer la ligne de crédit si nécessaire",
            "  - Rationaliser les décaissements non-urgents",
        ]
    else:
        lignes.append("\n✅ Trésorerie prévisionnelle positive sur toute la période.")

    return "\n".join(lignes)


def _rendu_ratios(ratios: dict) -> str:
    """Formate les ratios financiers avec seuils de benchmark."""
    lignes = ["RATIOS FINANCIERS\n"]

    normes = {
        "liquidite_generale":      ("> 1.5", lambda v: "✅" if v > 1.5 else ("⚠️" if v > 1 else "❌")),
        "liquidite_reduite":       ("> 1.0", lambda v: "✅" if v > 1 else ("⚠️" if v > 0.7 else "❌")),
        "liquidite_immediate":     ("> 0.3", lambda v: "✅" if v > 0.3 else "⚠️"),
        "autonomie_financiere_pct":("> 30%", lambda v: "✅" if v > 30 else "⚠️"),
        "ratio_endettement":       ("< 2",   lambda v: "✅" if v < 2 else "⚠️"),
        "marge_ebitda_pct":        ("> 15%", lambda v: "✅" if v > 15 else "⚠️"),
        "marge_nette_pct":         ("> 5%",  lambda v: "✅" if v > 5 else "⚠️"),
        "roe_pct":                 ("> 10%", lambda v: "✅" if v > 10 else "⚠️"),
        "dso_jours":               ("< 60j", lambda v: "✅" if v < 60 else "⚠️"),
    }

    sections = [
        ("LIQUIDITÉ", ["liquidite_generale", "liquidite_reduite", "liquidite_immediate"]),
        ("SOLVABILITÉ", ["autonomie_financiere_pct", "ratio_endettement"]),
        ("RENTABILITÉ", ["marge_ebitda_pct", "marge_nette_pct", "roe_pct"]),
        ("GESTION", ["rotation_stocks", "delai_stocks_jours", "dso_jours"]),
    ]

    for titre, keys in sections:
        disponibles = [(k, ratios[k]) for k in keys if k in ratios]
        if not disponibles:
            continue
        lignes.append(f"── {titre} ──")
        for k, v in disponibles:
            norme, eval_fn = normes.get(k, ("", lambda _: ""))
            try:
                icone = eval_fn(v)
            except Exception:
                icone = ""
            libelle = k.replace("_", " ")
            if v == float("inf"):
                lignes.append(f"  {libelle:<30} : ∞   {icone}  (norme {norme})")
            else:
                lignes.append(f"  {libelle:<30} : {v:<8.2f} {icone}  (norme {norme})")
        lignes.append("")

    return "\n".join(lignes).rstrip()


def _rendu_investissement(r: dict) -> str:
    """Formate l'évaluation d'investissement en texte."""
    lignes = [
        "ÉVALUATION D'INVESTISSEMENT\n",
        f"Investissement initial  : {r['investissement']:,.0f} FCFA",
        f"Taux d'actualisation    : {r['taux_pct']:.1f}%",
        f"Durée                   : {r['nb_annees']} ans\n",
        "FLUX DE TRÉSORERIE :",
    ]
    for fv in r["flux_actualisés"]:
        lignes.append(
            f"  Année {fv['annee']} : {fv['flux']:>14,.0f} FCFA  "
            f"(VA : {fv['va']:>12,.0f} FCFA)"
        )

    lignes.append("\n" + "─" * 50)
    van_icon = "✅ Rentable" if r["van_positive"] else "❌ Non rentable"
    lignes.append(f"VAN                     : {r['van']:>+14,.0f} FCFA  {van_icon}")

    if r["tri_pct"] is not None:
        tri_icon = "✅" if r["tri_superieur"] else "❌"
        lignes.append(
            f"TRI                     : {r['tri_pct']:>7.1f}%  {tri_icon}  "
            f"(seuil : {r['taux_pct']:.1f}%)"
        )
    if r["delai_ans"]:
        delai_icon = "✅" if r["delai_ans"] <= 3 else "⚠️"
        lignes.append(f"Délai récupération      : {r['delai_ans']:>7} ans  {delai_icon}")
    else:
        lignes.append(f"Délai récupération      : > {r['nb_annees']} ans  ❌")
    ip_icon = "✅" if r["ip_positif"] else "❌"
    lignes.append(f"Indice profitabilité    : {r['ip']:>7.2f}    {ip_icon}  (seuil : 1.0)")

    lignes.append("\nCONCLUSION :")
    if r["van_positive"] and r.get("tri_superieur"):
        lignes.append("  ✅ Projet financièrement viable — à approuver sous réserve des risques opérationnels")
    elif r["van_positive"]:
        lignes.append("  ⚠️  VAN positive mais TRI à surveiller — analyser la sensibilité des hypothèses")
    else:
        lignes.append("  ❌ Projet non rentable aux conditions actuelles — revoir les hypothèses ou renoncer")

    return "\n".join(lignes)


def _generer_boardpack(
    donnees_financieres: dict,
    periode: str,
    donnees_ops: dict = None,
    messages_cles: list = None,
    niveau_detail: str = "synthese",
) -> str:
    """Génère le contenu textuel d'un board pack direction."""
    donnees_ops   = donnees_ops   or {}
    messages_cles = messages_cles or []

    ca     = float(donnees_financieres.get("CA", donnees_financieres.get("chiffre_affaires", 0)))
    tresor = float(donnees_financieres.get("tresorerie", 0))
    marge  = float(donnees_financieres.get("marge", donnees_financieres.get("marge_nette", 0)))
    dette  = float(donnees_financieres.get("dette_nette", 0))
    ebitda = float(donnees_financieres.get("ebitda", 0))

    lignes = [f"BOARD PACK — {periode}", "=" * 60, ""]

    lignes.append("1. MESSAGES CLÉS POUR LA DIRECTION")
    if messages_cles:
        for msg in messages_cles:
            lignes.append(f"   ► {msg}")
    else:
        if ca > 0:
            lignes.append(f"   ► Chiffre d'affaires : {ca:,.0f} FCFA")
        if ebitda > 0 and ca > 0:
            lignes.append(f"   ► EBITDA : {ebitda:,.0f} FCFA ({ebitda/ca*100:.1f}% du CA)")
        lignes.append(f"   ► Trésorerie : {tresor:+,.0f} FCFA")

    lignes += ["", "2. TABLEAU DE BORD FINANCIER"]
    kpis = [
        ("Chiffre d'affaires",  ca,     "FCFA"),
        ("EBITDA",              ebitda, "FCFA"),
        ("Marge nette",         marge,  "%"),
        ("Trésorerie nette",    tresor, "FCFA"),
        ("Dette nette",         dette,  "FCFA"),
    ]
    for label, valeur, unite in kpis:
        if valeur != 0:
            fmt = f"{valeur:.1f}%" if unite == "%" else f"{valeur:,.0f} FCFA"
            lignes.append(f"   {label:<28} : {fmt}")

    if donnees_ops and niveau_detail == "complet":
        lignes += ["", "3. INDICATEURS OPÉRATIONNELS"]
        for k, v in donnees_ops.items():
            lignes.append(f"   {k:<28} : {v}")

    lignes += ["", "4. RISQUES ET POINTS DE VIGILANCE"]
    risques = []
    if tresor < 0:
        risques.append("❌  Trésorerie négative — plan d'urgence requis")
    if dette > 0 and ca > 0 and dette / ca > 2:
        risques.append("⚠️  Endettement élevé (dette > 2× CA)")
    if ebitda > 0 and ca > 0 and ebitda / ca < 0.05:
        risques.append("⚠️  Marge EBITDA insuffisante (< 5%)")
    if not risques:
        lignes.append("   ✅ Aucun risque majeur identifié")
    else:
        for r in risques:
            lignes.append(f"   {r}")

    lignes += [
        "",
        "5. DÉCISIONS REQUISES",
        "   ☐ Approbation des états financiers",
        "   ☐ Validation du budget révisé (si applicable)",
    ]
    if tresor < 0:
        lignes.append("   ☐ Plan d'urgence trésorerie à approuver en séance")

    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Classe AgentDAF
# ══════════════════════════════════════════════════════════════════════════════

class AgentDAF(AgentProBase):
    """Agent spécialisé Direction Administrative et Financière."""

    type_agent = TypeAgent.PRO_DAF

    # ── Prompt ──────────────────────────────────────────────────────────────

    def _system_prompt(self) -> str:
        base = super()._system_prompt()
        return base + """

EXPERTISE DIRECTION FINANCIÈRE :
Tu es un DAF expert en finance d'entreprise en Afrique francophone.

COMPÉTENCES CLÉS :
- Analyse financière : ratios (liquidité, solvabilité, rentabilité, gestion)
- Contrôle de gestion : budget, écarts, reporting mensuel / trimestriel
- Trésorerie : cash management, prévisions, lignes de crédit
- Financement : dette bancaire, leasing, financement OHADA, marchés de capitaux
- Reporting : board pack, états financiers SYSCOHADA
- Évaluation d'investissement : VAN, TRI, délai de récupération, IP

RÈGLES IMPORTANTES :
- Exprimer tous les montants en FCFA sauf instruction contraire
- Utiliser les ratios standards africains (SYSCOHADA, UEMOA, CEMAC)
- Identifier clairement les risques financiers avec niveau de criticité
- Proposer des solutions concrètes et chiffrées
- Citer les dispositions OHADA en matière de financement / reporting
"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "- Si analyse budgétaire et données budget/réalisé manquantes : "
            "demander les chiffres par ligne budgétaire\n"
            "- Si projection trésorerie et horizon non précisé : "
            "demander l'horizon (3, 6 ou 12 mois)\n"
            "- Si évaluation investissement et taux d'actualisation non précisé : "
            "suggérer 12% (coût du capital typique Afrique) et demander confirmation\n"
            "- Si ratios et données bilan absentes : demander les postes clés du bilan\n"
            "- Ne jamais redemander les informations déjà présentes dans le profil"
        )

    # ── Outils métier ────────────────────────────────────────────────────────

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "budget_analyser",
                "description": (
                    "Analyse l'exécution budgétaire : compare réalisé vs budget, "
                    "calcule les écarts et identifie les déviations significatives (> 5% et > 15%)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "budget": {
                            "type": "object",
                            "description": "Budget par ligne : {'ventes': 500000000, 'charges_personnel': 120000000}",
                        },
                        "realise": {
                            "type": "object",
                            "description": "Réalisé à date par ligne (mêmes clés que budget)",
                        },
                        "periode": {"type": "string", "description": "Période, ex: 'T3 2024'"},
                        "type_analyse": {
                            "type": "string",
                            "description": "mensuel | trimestriel | annuel | ytd",
                        },
                    },
                    "required": ["budget", "realise"],
                },
            },
            {
                "name": "cashflow_projeter",
                "description": (
                    "Projette les flux de trésorerie sur 3, 6 ou 12 mois. "
                    "Identifie les besoins de financement et les excédents de trésorerie."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "encaissements": {
                            "type": "object",
                            "description": "Encaissements mensuels prévisionnels {mois: montant}",
                        },
                        "decaissements": {
                            "type": "object",
                            "description": "Décaissements mensuels prévisionnels {mois: montant}",
                        },
                        "solde_initial": {
                            "type": "number",
                            "description": "Trésorerie de départ en FCFA",
                        },
                        "horizon_mois":  {"type": "integer", "description": "3, 6 ou 12"},
                        "ligne_credit":  {
                            "type": "number",
                            "description": "Ligne de crédit disponible en FCFA (optionnel)",
                        },
                    },
                    "required": ["encaissements", "decaissements"],
                },
            },
            {
                "name": "ratios_calculer",
                "description": (
                    "Calcule les ratios financiers (liquidité, solvabilité, rentabilité, gestion) "
                    "à partir des postes du bilan et du compte de résultat."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "bilan": {
                            "type": "object",
                            "description": "Postes bilan : actif_circulant, actif_immob, stocks, "
                                           "creances, disponibilites, capitaux_propres, dettes_lt, dettes_ct",
                        },
                        "resultat": {
                            "type": "object",
                            "description": "CA, charges_variables, charges_fixes, ebitda, resultat_net",
                        },
                        "secteur": {
                            "type": "string",
                            "description": "Secteur pour benchmarking (optionnel)",
                        },
                    },
                    "required": ["bilan"],
                },
            },
            {
                "name": "investissement_evaluer",
                "description": (
                    "Évalue un projet d'investissement : VAN, TRI, délai de récupération, "
                    "indice de profitabilité. Recommande ou déconseille l'investissement."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "investissement_initial": {
                            "type": "number",
                            "description": "Coût initial en FCFA",
                        },
                        "flux_tresorerie": {
                            "type": "array",
                            "description": "Flux annuels prévisionnels (liste de montants FCFA)",
                        },
                        "taux_actualisation": {
                            "type": "number",
                            "description": "Taux d'actualisation (ex : 0.12 pour 12%)",
                        },
                        "valeur_residuelle": {
                            "type": "number",
                            "description": "Valeur résiduelle en fin de projet (optionnel)",
                        },
                    },
                    "required": ["investissement_initial", "flux_tresorerie", "taux_actualisation"],
                },
            },
            {
                "name": "boardpack_generer",
                "description": (
                    "Génère le contenu d'un board pack (dossier pour la direction / CA) : "
                    "messages clés, tableau de bord financier, risques, décisions requises."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "donnees_financieres": {
                            "type": "object",
                            "description": "KPIs financiers : CA, marge, ebitda, tresorerie, dette_nette",
                        },
                        "donnees_ops": {
                            "type": "object",
                            "description": "KPIs opérationnels (optionnel)",
                        },
                        "periode": {"type": "string", "description": "Période concernée"},
                        "messages_cles": {
                            "type": "array",
                            "description": "Messages clés à faire passer (optionnel)",
                        },
                        "niveau_detail": {
                            "type": "string",
                            "description": "synthese | complet",
                        },
                    },
                    "required": ["donnees_financieres", "periode"],
                },
            },
            {
                "name": "orchestrer_cloture_mensuelle_daf",
                "description": (
                    "Orchestre la clôture mensuelle DAF multi-domaine : "
                    "checklist comptable, rapprochements bancaires, reporting direction."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mois": {"type": "integer", "description": "Mois de clôture (1-12)"},
                        "annee": {"type": "integer"},
                        "pays": {"type": "string"},
                        "nb_entites": {"type": "integer", "description": "Nombre d'entités à consolider"},
                    },
                    "required": [],
                },
            },
            {
                "name": "analyser_document_financier_daf",
                "description": (
                    "Analyse un document financier entrant (rapport d'audit, états financiers, "
                    "rapport commissaire aux comptes, scoring bancaire) avec vue DAF."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_document": {"type": "string", "description": "Texte ou description du document"},
                        "type_document": {"type": "string", "description": "rapport_audit/etats_financiers/rapport_cac/notation_banque/rapport_dgi"},
                        "angle_analyse": {"type": "string", "description": "tresorerie/risque/rentabilite/conformite"},
                    },
                    "required": ["contenu_document"],
                },
            },
            {
                "name": "calendrier_financier_daf",
                "description": (
                    "Génère le calendrier financier annuel complet d'une DAF : "
                    "clôtures, reporting, obligations fiscales, assemblées."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "annee": {"type": "integer"},
                        "pays": {"type": "string"},
                        "type_societe": {"type": "string", "description": "sarl/sa/ong/groupe"},
                    },
                    "required": ["pays"],
                },
            },
        ]

    # ── Dispatch ─────────────────────────────────────────────────────────────

    async def _executer_outil_metier(
        self,
        nom:          str,
        params:       dict,
        user_id:      int,
        execution_id: str,
    ) -> str:
        if nom == "budget_analyser":
            return _rendu_budget(
                _analyser_budget(
                    budget  = params.get("budget",  {}),
                    realise = params.get("realise", {}),
                    periode = params.get("periode", "Période"),
                )
            )

        if nom == "cashflow_projeter":
            return _rendu_cashflow(
                _projeter_cashflow(
                    encaissements = params.get("encaissements", {}),
                    decaissements = params.get("decaissements", {}),
                    solde_initial = float(params.get("solde_initial", 0)),
                    horizon_mois  = int(params.get("horizon_mois", 6)),
                    ligne_credit  = float(params.get("ligne_credit", 0)),
                )
            )

        if nom == "ratios_calculer":
            return _rendu_ratios(
                _calculer_ratios(
                    bilan    = params.get("bilan",    {}),
                    resultat = params.get("resultat", {}),
                )
            )

        if nom == "investissement_evaluer":
            flux = [float(f) for f in params.get("flux_tresorerie", [])]
            if not flux or float(params.get("investissement_initial", 0)) <= 0:
                return "Données insuffisantes. Fournir `investissement_initial` et `flux_tresorerie`."
            return _rendu_investissement(
                _evaluer_investissement(
                    investissement_initial = float(params.get("investissement_initial", 0)),
                    flux_tresorerie        = flux,
                    taux_actualisation     = float(params.get("taux_actualisation", 0.12)),
                    valeur_residuelle      = float(params.get("valeur_residuelle", 0)),
                )
            )

        if nom == "boardpack_generer":
            return _generer_boardpack(
                donnees_financieres = params.get("donnees_financieres", {}),
                periode             = params.get("periode", "Période"),
                donnees_ops         = params.get("donnees_ops", {}),
                messages_cles       = params.get("messages_cles", []),
                niveau_detail       = params.get("niveau_detail", "synthese"),
            )

        if nom == "orchestrer_cloture_mensuelle_daf":
            return _orchestrer_cloture_mensuelle_daf(params)

        if nom == "analyser_document_financier_daf":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_doc_financier_daf(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        if nom == "calendrier_financier_daf":
            return _calendrier_financier_daf(params)

        return f"[Outil '{nom}' non reconnu par AgentDAF]"


# ---------------------------------------------------------------------------
# Fonctions standalone — nouvelles automatisations DAF
# ---------------------------------------------------------------------------

def _orchestrer_cloture_mensuelle_daf(params: dict) -> str:
    from datetime import date
    mois = int(params.get("mois", date.today().month))
    annee = int(params.get("annee", date.today().year))
    pays = params.get("pays", "CM")
    nb_entites = int(params.get("nb_entites", 1))

    noms_mois = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    nom_mois = noms_mois[mois] if 1 <= mois <= 12 else f"Mois {mois}"

    lignes = [
        f"## Workflow Clôture Mensuelle DAF — {nom_mois} {annee}",
        f"Pays : {pays} | Nombre d'entités : {nb_entites}",
        "",
        "### Semaine de clôture — J-3 à J-1",
        "  ✅ Relance des services pour transmission des pièces en attente",
        "  ✅ Lettrage des comptes clients (encaissements du mois)",
        "  ✅ Lettrage des comptes fournisseurs (paiements du mois)",
        "  ✅ Vérification que toutes les factures fournisseurs sont saisies",
        "  ✅ Calcul des provisions à comptabiliser (charges à payer, produits à recevoir)",
        "",
        "### Jour J — Arrêtés comptables",
        "  ✅ Rapprochement bancaire tous comptes",
        "  ✅ Pointage caisse (si espèces en circulation)",
        "  ✅ Vérification soldes comptes de tiers (clients/fournisseurs anormaux)",
        "  ✅ Contrôle comptes d'attente (en instance de lettrage)",
        "  ✅ Amortissements mensuels (immobilisations)",
        "  ✅ Constatation des charges financières (intérêts d'emprunts)",
        "",
        "### J+2 — Calcul des indicateurs",
        "  ✅ CA du mois vs objectif vs N-1",
        "  ✅ Résultat d'exploitation provisoire",
        "  ✅ Position de trésorerie nette",
        "  ✅ Écart budgétaire par poste principal",
    ]
    if nb_entites > 1:
        lignes += [
            "",
            f"### Consolidation ({nb_entites} entités)",
            "  ✅ Éliminer les transactions intra-groupe",
            "  ✅ Retraitements OHADA si nécessaire",
            "  ✅ Reporting consolidé pour la direction",
        ]
    lignes += [
        "",
        "### J+3 à J+5 — Reporting direction",
        "  ✅ Tableau de bord mensuel (1 page) envoyé à la direction",
        "  ✅ Note d'alerte si dépassement budgétaire > 10%",
        "  ✅ Flash trésorerie prévisionnelle 30 jours",
        "",
        f"Clôture annuelle : obligations comptables SYSCOHADA révisé — états financiers à déposer avant le 30 avril N+1 ({pays}).",
    ]
    return "\n".join(lignes)


def _prompt_analyse_doc_financier_daf(params: dict) -> str:
    contenu = params.get("contenu_document", "")
    type_doc = params.get("type_document", "rapport_audit")
    angle = params.get("angle_analyse", "risque")

    types_labels = {
        "rapport_audit": "rapport d'audit externe",
        "etats_financiers": "états financiers (bilan + compte de résultat)",
        "rapport_cac": "rapport du commissaire aux comptes",
        "notation_banque": "rapport de notation / scoring bancaire",
        "rapport_dgi": "rapport de vérification DGI / redressement fiscal",
    }
    label = types_labels.get(type_doc, type_doc)

    angles = {
        "tresorerie": "l'impact sur la trésorerie et le besoin en fonds de roulement",
        "risque": "les risques financiers et opérationnels identifiés",
        "rentabilite": "la rentabilité et les leviers d'amélioration",
        "conformite": "la conformité réglementaire et fiscale",
    }
    focus = angles.get(angle, "l'ensemble des dimensions financières")

    return f"""Tu es un Directeur Administratif et Financier (DAF) expérimenté en entreprises africaines, expert SYSCOHADA.

Analyse ce {label} avec un focus sur {focus}.

DOCUMENT :
{contenu}

ANALYSE DAF REQUISE :
1. **Conclusions principales** — ce que ce document révèle en 3 points clés
2. **Risques identifiés** — financiers, fiscaux, opérationnels, réputationnels
3. **Points d'action immédiats** — décisions à prendre dans les 30 jours
4. **Impact sur les états financiers** — provisions à constituer, ajustements nécessaires
5. **Message pour le COMEX / Conseil** — comment présenter ça à la direction
6. **Recommandations stratégiques** — actions moyen terme

Style : direct, tonalité DAF expérimenté, chiffré si possible."""


def _calendrier_financier_daf(params: dict) -> str:
    from datetime import date
    annee = int(params.get("annee", date.today().year))
    pays = params.get("pays", "CM")
    type_societe = params.get("type_societe", "sarl")

    lignes = [
        f"## Calendrier Financier DAF {annee} — {pays} ({type_societe.upper()})",
        "",
        "### Obligations Récurrentes Mensuelles",
        f"  J+5 : Déclaration et paiement TVA (si régime mensuel)",
        f"  J+10 : Déclaration retenues à la source (salaires, prestataires)",
        f"  J+15 : Rapprochements bancaires",
        f"  J+20 : Tableau de bord mensuel à la direction",
        "",
        "### Obligations Trimestrielles",
        f"  Fin avril, juillet, octobre, janvier : Acomptes IS (CM: 2,2% CA/trimestre)",
        f"  Fin du trimestre : Reporting consolidé si groupe",
        "",
        "### Calendrier Annuel Critique",
    ]

    if pays == "CM":
        lignes += [
            f"  15 mars {annee} : Déclaration annuelle IS et liasse fiscale",
            f"  31 mars {annee} : Dépôt états financiers au Greffe du Tribunal",
            f"  30 avril {annee} : AG ordinaire approbation comptes {annee - 1}",
            f"  15 mars {annee + 1} : Prochaine déclaration IS",
        ]
    elif pays == "CI":
        lignes += [
            f"  30 avril {annee} : Déclaration annuelle BIC/IS",
            f"  30 juin {annee} : Dépôt états financiers SYSCOHADA au greffe",
            f"  30 juin {annee} : AG ordinaire approbation comptes",
        ]
    elif pays == "SN":
        lignes += [
            f"  30 avril {annee} : Déclaration IS et liasse fiscale (DGID)",
            f"  30 juin {annee} : Dépôt au greffe du Tribunal de Commerce",
            f"  30 juin {annee} : AG ordinaire approbation comptes",
        ]
    else:
        lignes += [
            f"  Mars-avril {annee} : Déclaration annuelle IS (vérifier délai exact pays)",
            f"  Avant 30 juin {annee} : AG approbation comptes + dépôt au greffe",
        ]

    lignes += [
        "",
        "### Opérations Budgétaires",
        f"  Septembre-octobre {annee} : Kick-off budget {annee + 1}",
        f"  Novembre {annee} : Arbitrages budgétaires avec directions",
        f"  Décembre {annee} : Validation et communication budget {annee + 1}",
        "",
        "⚠️ Vérifier les dates exactes auprès de la DGI locale — les délais peuvent évoluer.",
    ]
    return "\n".join(lignes)
