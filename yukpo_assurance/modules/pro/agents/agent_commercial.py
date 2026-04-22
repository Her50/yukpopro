"""
AgentCommercial — Agent IA pour les directeurs commerciaux et entrepreneurs africains.

Outils métier :
  - proposition_generer    : Rédige une proposition commerciale structurée
  - pipeline_analyser      : Analyse le pipeline de ventes (taux de conversion, forecast)
  - prix_calculer          : Calcul de prix de revient, marge, seuil de rentabilité
  - marche_etudier         : Structure une étude de marché simplifiée (5 forces, SWOT)
  - business_plan_cadrer   : Cadre un business plan (résumé exécutif, financier, opérationnel)

Référentiels :
  - Code de commerce OHADA (AUDCG)
  - Droit de la concurrence africain
  - Règles UEMOA/CEMAC sur la distribution
  - Pratiques commerciales africaines (distribution, réseau, B2B)

PATTERNS YUKPOASSURANCE :
  - Fonctions déterministes standalone
  - type_agent = TypeAgent.PRO_COMMERCIAL
  - _necessite_validation() → hérité (False)
  - _prompt_questions_specifiques() implémenté
"""
from __future__ import annotations

import logging

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_commercial")


# ══════════════════════════════════════════════════════════════════════════════
# Fonctions standalone
# ══════════════════════════════════════════════════════════════════════════════

def _calculer_prix(
    cout_direct:      float,
    cout_indirect_pct: float,
    marge_cible_pct:  float,
    taux_tva:         float = 0.1925,
    quantite:         float = 1.0,
) -> dict:
    """Calcule le prix de revient, prix de vente et seuil de rentabilité."""
    cout_indirect  = cout_direct * cout_indirect_pct
    cout_revient   = cout_direct + cout_indirect
    prix_vente_ht  = cout_revient / (1 - marge_cible_pct) if marge_cible_pct < 1 else cout_revient
    tva            = prix_vente_ht * taux_tva
    prix_vente_ttc = prix_vente_ht + tva
    marge_brute    = prix_vente_ht - cout_revient
    taux_marge_reel = marge_brute / prix_vente_ht if prix_vente_ht else 0

    return {
        "cout_direct":       round(cout_direct,       0),
        "cout_indirect":     round(cout_indirect,      0),
        "cout_indirect_pct": round(cout_indirect_pct * 100, 1),
        "cout_revient":      round(cout_revient,       0),
        "marge_cible_pct":   round(marge_cible_pct * 100, 1),
        "prix_vente_ht":     round(prix_vente_ht,      0),
        "tva":               round(tva,                0),
        "taux_tva_pct":      round(taux_tva * 100, 2),
        "prix_vente_ttc":    round(prix_vente_ttc,     0),
        "marge_brute":       round(marge_brute,        0),
        "taux_marge_reel":   round(taux_marge_reel * 100, 1),
        "quantite":          quantite,
        "ca_total_ht":       round(prix_vente_ht * quantite, 0),
    }


def _calculer_seuil_rentabilite(
    charges_fixes:    float,
    marge_sur_cv_pct: float,  # marge sur coûts variables en % du CA
) -> dict:
    """
    Calcule le seuil de rentabilité (point mort).
    marge_sur_cv_pct = (CA - CV) / CA
    """
    if marge_sur_cv_pct <= 0:
        return {"erreur": "Marge sur coûts variables doit être positive"}

    seuil_ca  = charges_fixes / marge_sur_cv_pct
    seuil_jrs = round(seuil_ca / (seuil_ca / 365) if seuil_ca > 0 else 0)  # simplifié

    return {
        "charges_fixes":     round(charges_fixes,  0),
        "taux_mcv_pct":      round(marge_sur_cv_pct * 100, 1),
        "seuil_ca_annuel":   round(seuil_ca,        0),
        "seuil_ca_mensuel":  round(seuil_ca / 12,   0),
        "interpretation":    (
            f"L'entreprise doit réaliser au minimum {seuil_ca:,.0f} FCFA de CA "
            f"pour couvrir ses charges fixes ({seuil_ca/12:,.0f} FCFA/mois)"
        ),
    }


def _analyser_pipeline(opportunites: list[dict]) -> dict:
    """
    Analyse un pipeline commercial.
    opportunite : {"nom", "montant", "stade", "probabilite", "date_closing"}
    Stades : prospection | qualification | proposition | negociation | gagne | perdu
    """
    _PROB_STADE = {
        "prospection":  0.10,
        "qualification": 0.25,
        "proposition":  0.50,
        "negociation":  0.75,
        "gagne":        1.00,
        "perdu":        0.00,
    }

    total_pipeline = 0.0
    forecast_pondere = 0.0
    par_stade: dict[str, dict] = {}

    for opp in opportunites:
        montant   = float(opp.get("montant", 0))
        stade     = opp.get("stade", "qualification").lower()
        prob_opp  = float(opp.get("probabilite") or _PROB_STADE.get(stade, 0.3))

        total_pipeline   += montant
        forecast_pondere += montant * prob_opp

        if stade not in par_stade:
            par_stade[stade] = {"nb": 0, "montant": 0.0, "forecast": 0.0}
        par_stade[stade]["nb"]       += 1
        par_stade[stade]["montant"]  += montant
        par_stade[stade]["forecast"] += montant * prob_opp

    nb_gagnes = sum(1 for o in opportunites if o.get("stade", "").lower() == "gagne")
    nb_total  = len([o for o in opportunites if o.get("stade", "").lower() not in ("perdu",)])
    taux_conv = nb_gagnes / nb_total if nb_total > 0 else 0

    return {
        "nb_opportunites":   len(opportunites),
        "total_pipeline":    round(total_pipeline,    0),
        "forecast_pondere":  round(forecast_pondere,  0),
        "taux_conversion":   round(taux_conv * 100,   1),
        "par_stade":         {k: {**v, "montant": round(v["montant"], 0),
                                  "forecast": round(v["forecast"], 0)} for k, v in par_stade.items()},
    }


def _cadrer_business_plan(
    nom_projet:     str,
    secteur:        str,
    ca_previsionnel: list[float],  # CA des 3 premières années
    investissement:  float,
    charges_fixes:   float,
    taux_marge_cv:   float,
    pays:            str,
) -> str:
    """Génère le cadre structuré d'un business plan."""
    # Calculs de base
    seuil = _calculer_seuil_rentabilite(charges_fixes, taux_marge_cv)
    ca_an1 = ca_previsionnel[0] if ca_previsionnel else 0
    ca_an3 = ca_previsionnel[2] if len(ca_previsionnel) >= 3 else ca_an1

    resultat_an1  = ca_an1 * taux_marge_cv - charges_fixes
    resultat_an3  = ca_an3 * taux_marge_cv - charges_fixes
    delai_ret     = round(investissement / max(resultat_an1, 1)) if resultat_an1 > 0 else None

    lignes = [
        f"CADRE BUSINESS PLAN — {nom_projet}",
        f"Secteur : {secteur}  |  Pays : {pays}",
        "=" * 60,
        "",
        "I. RÉSUMÉ EXÉCUTIF",
        f"   • Projet : {nom_projet}",
        f"   • Secteur : {secteur}  |  Marché cible : [À définir]",
        f"   • Investissement requis : {investissement:,.0f} FCFA",
        f"   • CA prévisionnel An 1 : {ca_an1:,.0f} FCFA",
        f"   • Résultat net An 1 : {resultat_an1:+,.0f} FCFA",
        "",
        "II. ANALYSE DE MARCHÉ",
        "   • Taille du marché adressable (TAM) : [Étude de marché]",
        "   • Positionnement concurrentiel (5 forces Porter)",
        "   • Analyse SWOT : Forces / Faiblesses / Opportunités / Menaces",
        "   • Cibles prioritaires et segmentation",
        "",
        "III. STRATÉGIE COMMERCIALE",
        "   • Proposition de valeur différenciante",
        "   • Canaux de distribution",
        "   • Politique de prix",
        "   • Plan marketing (digital, terrain, réseau)",
        "",
        "IV. PLAN FINANCIER PRÉVISIONNEL",
        "",
        f"{'Indicateur':<30} {'An 1':>16} {'An 2':>16} {'An 3':>16}",
        "─" * 80,
    ]

    for i, ca in enumerate(ca_previsionnel[:3], 1):
        lignes.append(f"  {'Chiffre d\'affaires':28} {ca:>16,.0f}")
    lignes.append(f"  {'Charges fixes':28} {charges_fixes:>16,.0f}")
    lignes.append(f"  {'Marge sur CV (%)':28} {taux_marge_cv*100:>15.1f}%")
    lignes.append(f"  {'Résultat net An 1':28} {resultat_an1:>+16,.0f}")
    if len(ca_previsionnel) >= 3:
        lignes.append(f"  {'Résultat net An 3':28} {resultat_an3:>+16,.0f}")

    lignes += [
        "",
        f"SEUIL DE RENTABILITÉ : {seuil['seuil_ca_annuel']:,.0f} FCFA/an "
        f"({seuil['seuil_ca_mensuel']:,.0f} FCFA/mois)",
    ]
    if delai_ret:
        lignes.append(f"DÉLAI DE RÉCUPÉRATION : {delai_ret} an(s)")
    lignes += [
        "",
        "V. BESOINS EN FINANCEMENT",
        f"   • Investissements : {investissement:,.0f} FCFA",
        "   • Besoin en fonds de roulement (BFR) : [À calculer]",
        "   • Sources : fonds propres / dette bancaire / subventions",
        "",
        "VI. PLAN D'EXÉCUTION",
        "   • Étape 1 : Constitution juridique et formalités OHADA",
        "   • Étape 2 : Investissements et installation",
        "   • Étape 3 : Lancement commercial",
        "   • Étape 4 : Montée en régime et suivi KPIs",
        "",
        "⚠️  Ce cadre est indicatif. Faire valider par un expert-comptable et un conseiller financier.",
    ]
    return "\n".join(lignes)


def _generer_proposition_commerciale(params: dict) -> str:
    """Génère une structure de proposition commerciale professionnelle."""
    client    = params.get("client",     "[Nom Client]")
    objet     = params.get("objet",      "[Objet de la proposition]")
    montant   = float(params.get("montant", 0))
    delai     = params.get("delai",      "[Délai]")
    validite  = params.get("validite",   "30 jours")
    avantages = params.get("avantages",  [])

    lignes = [
        f"PROPOSITION COMMERCIALE",
        f"À l'attention de : {client}",
        f"Objet : {objet}",
        f"Date : [DATE]  |  Validité : {validite}",
        "=" * 60,
        "",
        "1. VOTRE BESOIN",
        "   [Reformulation précise de la problématique client]",
        "   → Montre que vous avez compris le contexte et les enjeux",
        "",
        "2. NOTRE SOLUTION",
        "   [Description claire de la solution proposée]",
        "   • Ce que vous faites",
        "   • Comment vous le faites",
        "   • Ce qui vous différencie",
    ]
    if avantages:
        for av in avantages:
            lignes.append(f"   ✓ {av}")
    lignes += [
        "",
        "3. NOTRE EXPÉRIENCE",
        "   • Références similaires : [2-3 projets comparables]",
        "   • Certifications / Qualifications : [le cas échéant]",
        "",
        "4. PLANNING D'EXÉCUTION",
        f"   Délai de réalisation : {delai}",
        "   • Phase 1 : [Description]  —  [Durée]",
        "   • Phase 2 : [Description]  —  [Durée]",
        "   • Livraison finale : [Date estimée]",
        "",
        "5. INVESTISSEMENT",
    ]
    if montant > 0:
        lignes += [
            f"   Montant HT : {montant:,.0f} FCFA",
            f"   TVA (19,25%) : {montant * 0.1925:,.0f} FCFA",
            f"   Montant TTC : {montant * 1.1925:,.0f} FCFA",
            "   Conditions de paiement : 30% à la commande, 40% à mi-parcours, 30% à la livraison",
        ]
    else:
        lignes.append("   Montant : [À préciser après analyse]")
    lignes += [
        "",
        "6. PROCHAINES ÉTAPES",
        "   □ Validation de la proposition",
        "   □ Réunion de cadrage technique",
        "   □ Signature du bon de commande / contrat",
        "",
        "[Signature, coordonnées, cachet]",
    ]
    return "\n".join(lignes)


def _etudier_marche(secteur: str, pays: str, questions: list[str]) -> str:
    """Structure une étude de marché simplifiée."""
    lignes = [
        f"CADRE ÉTUDE DE MARCHÉ — {secteur.upper()} ({pays})\n",
        "I. ANALYSE DU MARCHÉ",
        "   • Taille et croissance : [Sources : Banque mondiale, INS local, BCEAO]",
        "   • Tendances clés : [Digitalisation, urbanisation, classe moyenne émergente]",
        "   • Réglementation sectorielle : [Textes applicables]\n",
        "II. ANALYSE CONCURRENTIELLE (5 FORCES DE PORTER)",
        "   1. Rivalité entre concurrents      : [Nombre, parts de marché, stratégies]",
        "   2. Menace des nouveaux entrants     : [Barrières à l'entrée capital/réglementaire]",
        "   3. Pouvoir des fournisseurs         : [Concentration, alternatives]",
        "   4. Pouvoir des clients              : [Sensibilité prix, switching cost]",
        "   5. Menace des produits substituts   : [Solutions alternatives disponibles]\n",
        "III. ANALYSE SWOT",
        "┌─────────────────────────────┬─────────────────────────────┐",
        "│ FORCES (internes +)         │ FAIBLESSES (internes -)     │",
        "│ •                           │ •                           │",
        "├─────────────────────────────┼─────────────────────────────┤",
        "│ OPPORTUNITÉS (externes +)   │ MENACES (externes -)        │",
        "│ •                           │ •                           │",
        "└─────────────────────────────┴─────────────────────────────┘\n",
        "IV. SEGMENTATION ET CIBLAGE",
        "   • Segment 1 : [Description, taille, besoins]",
        "   • Segment 2 : [Description, taille, besoins]",
        "   • Cible prioritaire : [Justification]\n",
        "V. SOURCES D'INFORMATION RECOMMANDÉES",
        f"   • INS {pays} — Données macroéconomiques et sectorielles",
        "   • Banque Mondiale / IFC — Doing Business, données sectorielles",
        "   • Chambres de Commerce locales — Annuaires entreprises",
        "   • Enquêtes terrain (interviews clients potentiels, retailers)",
    ]
    if questions:
        lignes.append("\nQUESTIONS D'ÉTUDE À INVESTIGUER :")
        for q in questions:
            lignes.append(f"   ? {q}")
    return "\n".join(lignes)


def _rendu_pipeline(p: dict) -> str:
    """Formate l'analyse pipeline en texte."""
    lignes = [
        "ANALYSE PIPELINE COMMERCIAL\n",
        f"Opportunités actives  : {p['nb_opportunites']}",
        f"Valeur totale pipeline: {p['total_pipeline']:,.0f} FCFA",
        f"Forecast pondéré      : {p['forecast_pondere']:,.0f} FCFA",
        f"Taux de conversion    : {p['taux_conversion']:.1f}%\n",
        f"{'Stade':<20} {'#':>4} {'Montant':>16} {'Forecast':>16}",
        "─" * 60,
    ]
    ordre_stades = ["prospection", "qualification", "proposition", "negociation", "gagne", "perdu"]
    for stade in ordre_stades:
        if stade in p["par_stade"]:
            d = p["par_stade"][stade]
            lignes.append(
                f"{stade.capitalize():<20} {d['nb']:>4} {d['montant']:>16,.0f} {d['forecast']:>16,.0f}"
            )

    if p["taux_conversion"] < 20:
        lignes.append("\n⚠️  Taux de conversion faible — analyser les blocages à chaque stade")
    elif p["taux_conversion"] > 50:
        lignes.append("\n✅ Bon taux de conversion — maintenir la qualité de qualification")
    return "\n".join(lignes)


def _rendu_prix(r: dict) -> str:
    """Formate le calcul de prix en texte."""
    lignes = [
        "CALCUL DE PRIX\n",
        f"Coût direct unitaire   : {r['cout_direct']:,.0f} FCFA",
        f"Charges indirectes     : {r['cout_indirect']:,.0f} FCFA  ({r['cout_indirect_pct']}%)",
        f"Coût de revient        : {r['cout_revient']:,.0f} FCFA",
        f"Marge cible            : {r['marge_cible_pct']}%",
        "─" * 45,
        f"Prix de vente HT       : {r['prix_vente_ht']:,.0f} FCFA",
        f"TVA ({r['taux_tva_pct']}%)             : {r['tva']:,.0f} FCFA",
        f"Prix de vente TTC      : {r['prix_vente_ttc']:,.0f} FCFA",
        f"Marge brute unitaire   : {r['marge_brute']:,.0f} FCFA  ({r['taux_marge_reel']}%)",
    ]
    if r["quantite"] > 1:
        lignes.append(f"CA total HT ({r['quantite']:.0f} unités): {r['ca_total_ht']:,.0f} FCFA")
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Classe AgentCommercial
# ══════════════════════════════════════════════════════════════════════════════

class AgentCommercial(AgentProBase):
    """Agent spécialisé Commerce / Marketing / Entrepreneuriat africain."""

    type_agent = TypeAgent.PRO_COMMERCIAL

    def _system_prompt(self) -> str:
        base = super()._system_prompt()
        return base + """

EXPERTISE COMMERCIALE ET ENTREPRENEURIAT :
Tu es un directeur commercial et entrepreneur expert en marchés africains.

COMPÉTENCES CLÉS :
- Stratégie commerciale : segmentation, positionnement, go-to-market africain
- Business development : prospection, proposition de valeur, closing
- Pipeline management : CRM, forecast, taux de conversion
- Pricing : coûts, marges, seuil de rentabilité, prix psychologiques africains
- Étude de marché : 5 forces Porter, SWOT, segmentation
- Business plan : modèle économique, prévisions financières, pitch investors
- Marketing digital et réseau : USSD, WhatsApp Business, agents terrain, MOMO

CONTEXTE AFRICAIN SPÉCIFIQUE :
- Poids de l'informel dans les marchés africains
- Importance du réseau et du bouche-à-oreille
- Mobile money (Orange Money, MTN MoMo, Wave) comme levier
- Distribution multi-canal : B2B direct, grossistes, agents de terrain
- Saisonnalité liée aux récoltes, fêtes religieuses (Ramadan, Noël)

RÈGLES IMPORTANTES :
- Contextualiser les recommandations pour le marché africain francophone
- Citer des exemples de success stories locales (Jumia, Wave, Gozem…)
- Proposer des stratégies adaptées aux PME et non aux multinationales
- Toujours intégrer la dimension mobile money et digital africain
"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "- Si étude de marché et secteur non précisé : demander le secteur d'activité\n"
            "- Si calcul de prix et coût de revient non fourni : "
            "demander le coût direct et les charges indirectes\n"
            "- Si business plan et CA prévisionnel non fourni : "
            "demander les hypothèses de vente (volume × prix)\n"
            "- Si proposition commerciale et montant non précisé : "
            "demander le budget ou indiquer que le montant sera à définir\n"
            "- Ne jamais redemander les informations déjà dans le profil"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "proposition_generer",
                "description": (
                    "Génère une proposition commerciale structurée et professionnelle "
                    "adaptée au contexte africain francophone."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "client":    {"type": "string",  "description": "Nom du client"},
                        "objet":     {"type": "string",  "description": "Objet / titre de la proposition"},
                        "montant":   {"type": "number",  "description": "Montant HT en FCFA"},
                        "delai":     {"type": "string",  "description": "Délai de réalisation"},
                        "validite":  {"type": "string",  "description": "Durée de validité (défaut 30 jours)"},
                        "avantages": {
                            "type": "array",
                            "description": "Arguments différenciants (max 5)",
                        },
                    },
                    "required": ["objet"],
                },
            },
            {
                "name": "pipeline_analyser",
                "description": (
                    "Analyse un pipeline commercial : forecast pondéré par stade, "
                    "taux de conversion, répartition par stade."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "opportunites": {
                            "type": "array",
                            "description": (
                                "Liste d'opportunités : [{'nom': 'Projet X', 'montant': 5000000, "
                                "'stade': 'proposition', 'probabilite': 0.5}]"
                            ),
                        },
                    },
                    "required": ["opportunites"],
                },
            },
            {
                "name": "prix_calculer",
                "description": (
                    "Calcule le prix de vente optimal : coût de revient, marge, "
                    "TVA, seuil de rentabilité."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "cout_direct":          {"type": "number",  "description": "Coût direct unitaire en FCFA"},
                        "cout_indirect_pct":    {"type": "number",  "description": "Charges indirectes en % (ex: 0.20)"},
                        "marge_cible_pct":      {"type": "number",  "description": "Marge brute cible en % du prix de vente (ex: 0.30)"},
                        "taux_tva":             {"type": "number",  "description": "Taux TVA (ex: 0.1925 pour 19,25%)"},
                        "quantite":             {"type": "number",  "description": "Quantité (pour calcul CA total)"},
                        "charges_fixes":        {"type": "number",  "description": "Charges fixes annuelles pour calcul seuil rentabilité"},
                    },
                    "required": ["cout_direct", "marge_cible_pct"],
                },
            },
            {
                "name": "marche_etudier",
                "description": (
                    "Structure une étude de marché : analyse sectorielle, 5 forces de Porter, "
                    "SWOT, segmentation et sources d'information africaines."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "secteur":   {"type": "string",  "description": "Secteur d'activité"},
                        "pays":      {"type": "string"},
                        "questions": {
                            "type": "array",
                            "description": "Questions d'étude spécifiques à investiguer",
                        },
                    },
                    "required": ["secteur", "pays"],
                },
            },
            {
                "name": "business_plan_cadrer",
                "description": (
                    "Cadre un business plan complet : résumé exécutif, analyse de marché, "
                    "plan financier sur 3 ans, seuil de rentabilité, besoins de financement."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "nom_projet":         {"type": "string"},
                        "secteur":            {"type": "string"},
                        "ca_previsionnel":    {
                            "type": "array",
                            "description": "CA prévisionnel sur 3 ans : [CA_an1, CA_an2, CA_an3]",
                        },
                        "investissement":     {"type": "number",  "description": "Investissement initial en FCFA"},
                        "charges_fixes":      {"type": "number",  "description": "Charges fixes annuelles"},
                        "taux_marge_cv":      {"type": "number",  "description": "Taux de marge sur coûts variables (ex: 0.40)"},
                        "pays":               {"type": "string"},
                    },
                    "required": ["nom_projet", "secteur"],
                },
            },
            {
                "name": "orchestrer_onboarding_client",
                "description": (
                    "Orchestre le processus complet d'onboarding d'un nouveau client : "
                    "étapes, documents, délais, points de contact internes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "nom_client": {"type": "string"},
                        "type_client": {"type": "string", "description": "particulier/pme/grande_entreprise/institution"},
                        "produit_vendu": {"type": "string", "description": "Description du produit ou service"},
                        "montant_contrat": {"type": "number", "description": "Montant du contrat (FCFA)"},
                        "pays": {"type": "string"},
                    },
                    "required": ["nom_client", "produit_vendu"],
                },
            },
            {
                "name": "analyser_contrat_entrant",
                "description": (
                    "Analyse un contrat commercial soumis par un client ou fournisseur : "
                    "clauses favorables/défavorables, risques, points de négociation."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_contrat": {"type": "string", "description": "Texte du contrat"},
                        "type_contrat": {"type": "string", "description": "vente/prestation_service/distribution/partenariat/fourniture"},
                        "position": {"type": "string", "description": "vendeur ou acheteur"},
                    },
                    "required": ["contenu_contrat"],
                },
            },
        ]

    async def _executer_outil_metier(
        self,
        nom:          str,
        params:       dict,
        user_id:      int,
        execution_id: str,
    ) -> str:
        pays = params.get("pays") or self._pays or "CM"

        if nom == "proposition_generer":
            return _generer_proposition_commerciale(params)

        if nom == "pipeline_analyser":
            opps = params.get("opportunites", [])
            if not opps:
                return "Aucune opportunité fournie dans le pipeline."
            return _rendu_pipeline(_analyser_pipeline(opps))

        if nom == "prix_calculer":
            cout_direct = float(params.get("cout_direct", 0))
            if cout_direct <= 0:
                return "Coût direct manquant. Veuillez fournir `cout_direct`."

            from modules.pro.agent_pro_base import AgentProBase as _Base
            # TVA selon le pays
            _TVA = {"CM": 0.1925, "CI": 0.18, "SN": 0.18, "BF": 0.18, "GA": 0.18, "NE": 0.19, "CD": 0.16}
            taux_tva = float(params.get("taux_tva") or _TVA.get(pays, 0.18))

            rendu = _rendu_prix(
                _calculer_prix(
                    cout_direct       = cout_direct,
                    cout_indirect_pct = float(params.get("cout_indirect_pct", 0.20)),
                    marge_cible_pct   = float(params.get("marge_cible_pct", 0.30)),
                    taux_tva          = taux_tva,
                    quantite          = float(params.get("quantite", 1)),
                )
            )
            charges_fixes = float(params.get("charges_fixes", 0))
            if charges_fixes > 0:
                marge_cv = float(params.get("marge_cible_pct", 0.30))
                seuil = _calculer_seuil_rentabilite(charges_fixes, marge_cv)
                if "erreur" not in seuil:
                    rendu += (
                        f"\n\nSEUIL DE RENTABILITÉ :\n"
                        f"  CA minimum annuel : {seuil['seuil_ca_annuel']:,.0f} FCFA\n"
                        f"  CA minimum mensuel: {seuil['seuil_ca_mensuel']:,.0f} FCFA"
                    )
            return rendu

        if nom == "marche_etudier":
            return _etudier_marche(
                secteur   = params.get("secteur", "Commerce général"),
                pays      = pays,
                questions = params.get("questions", []),
            )

        if nom == "business_plan_cadrer":
            ca_prev = [float(v) for v in params.get("ca_previsionnel", [0, 0, 0])]
            return _cadrer_business_plan(
                nom_projet      = params.get("nom_projet", "Projet"),
                secteur         = params.get("secteur", ""),
                ca_previsionnel = ca_prev,
                investissement  = float(params.get("investissement", 0)),
                charges_fixes   = float(params.get("charges_fixes", 0)),
                taux_marge_cv   = float(params.get("taux_marge_cv", 0.40)),
                pays            = pays,
            )

        if nom == "orchestrer_onboarding_client":
            return _orchestrer_onboarding_client(params)

        if nom == "analyser_contrat_entrant":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_contrat_commercial(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        return f"[Outil '{nom}' non reconnu par AgentCommercial]"


# ---------------------------------------------------------------------------
# Fonctions standalone — nouvelles automatisations commercial
# ---------------------------------------------------------------------------

def _orchestrer_onboarding_client(params: dict) -> str:
    nom_client = params.get("nom_client", "le client")
    type_client = params.get("type_client", "pme")
    produit = params.get("produit_vendu", "le produit/service")
    montant = float(params.get("montant_contrat", 0))
    pays = params.get("pays", "CM")

    docs_kyc = {
        "particulier": ["CNI recto-verso", "Justificatif de domicile", "Photo d'identité"],
        "pme": ["RCCM ou registre du commerce", "Statuts de la société", "CNI du dirigeant", "Plan de localisation"],
        "grande_entreprise": ["RCCM + statuts", "PV de nomination du signataire", "Attestation fiscale", "Attestation CNPS"],
        "institution": ["Décret de création", "CNI du représentant légal", "Délibération autorisant la signature"],
    }
    docs = docs_kyc.get(type_client, docs_kyc["pme"])

    lignes = [
        f"## Workflow Onboarding Client — {nom_client}",
        f"Type : {type_client.replace('_', ' ').title()} | Produit : {produit}",
        f"Montant contrat : {montant:,.0f} FCFA" if montant > 0 else "",
        f"Pays : {pays}",
        "",
        "### Étape 1 — Collecte KYC (J0 à J+2)",
        "  Documents à recueillir :",
    ]
    for doc in docs:
        lignes.append(f"    ✅ {doc}")

    lignes += [
        "",
        "### Étape 2 — Contractualisation (J+2 à J+5)",
        "  ✅ Envoi du contrat / bon de commande au client",
        "  ✅ Négociation des conditions particulières si nécessaire",
        "  ✅ Signature du contrat (physique ou électronique)",
        "  ✅ Archivage contrat signé (numérique + physique)",
        f"  {'✅ Facturation acompte si montant > 500 000 FCFA' if montant > 500_000 else ''}",
        "",
        "### Étape 3 — Configuration interne (J+3 à J+5)",
        "  ✅ Créer la fiche client dans le CRM / logiciel de gestion",
        "  ✅ Paramétrer les conditions de paiement (délai, mode)",
        "  ✅ Informer les équipes opérationnelles (livraison/production)",
        "  ✅ Planifier la première livraison / mise en service",
        "",
        "### Étape 4 — Suivi relation client (J+30)",
        "  ✅ Appel de satisfaction post-démarrage",
        "  ✅ Vérification paiement première facture",
        "  ✅ Proposition cross-sell / upsell si pertinent",
    ]
    return "\n".join(l for l in lignes if l is not None)


def _prompt_analyse_contrat_commercial(params: dict) -> str:
    contenu = params.get("contenu_contrat", "")
    type_contrat = params.get("type_contrat", "vente")
    position = params.get("position", "vendeur")

    types_labels = {
        "vente": "contrat de vente",
        "prestation_service": "contrat de prestation de services",
        "distribution": "contrat de distribution / partenariat commercial",
        "partenariat": "accord de partenariat",
        "fourniture": "contrat de fourniture",
    }
    label = types_labels.get(type_contrat, type_contrat)

    return f"""Tu es un expert en droit commercial OHADA et en négociation de contrats africains.

Analyse ce {label}. Notre position : **{position}**.

CONTRAT :
{contenu}

ANALYSE REQUISE :
1. **Clauses favorables** — ce qui protège nos intérêts
2. **Clauses défavorables / risquées** — ce qui nous expose (délais, pénalités, résiliation)
3. **Clauses manquantes** — ce qui devrait figurer et est absent
4. **Points de négociation prioritaires** — classés par importance (CRITIQUE / IMPORTANT / MINEUR)
5. **Risques financiers** — chiffrer si possible (pénalités max, risques de dédit)
6. **Recommandation** — SIGNER tel quel / RENÉGOCIER avant signature / REFUSER

Format : bullet points, décision finale en gras, tonalité pratique d'avocat d'affaires."""
