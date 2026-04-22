"""
Agent Provisions Techniques — Calcul, suivi et conformité des provisions CIMA (Art. 334-339).

PROVISIONS GÉRÉES :
  Non-Vie :
    - PPNA   : Provisions pour Primes Non Acquises  (Art. 334-1°)
    - PSAP   : Provisions pour Sinistres À Payer    (Art. 334-2°) + IBNR
    - PEq    : Provisions pour Égalisation          (Art. 334-4°) — branches variables
    - PREC   : Provisions pour Risques en Cours     (Art. 334-5°)
    - PG     : Provisions de Gestion                (Art. 334-6°)
    - PTS    : Provisions Techniques Spéciales       (Art. 334 bis) — catastrophes, RC auto corporel

  Vie (Livre II CIMA) :
    - PM     : Provisions Mathématiques             (Art. 63)  — taux technique min 3,5%
    - PRC    : Provisions pour Risques Croissants   (Art. 63 bis)
    - PPB    : Provisions pour Participation aux Bénéfices (Art. 81) — min 85% résultat tech vie
    - PEP    : Provisions d'Égalisation Prévoyance  — décès collectif, invalidité

PRINCIPE FONDAMENTAL :
  Tous les calculs sont 100% DÉTERMINISTES (0 IA pour les chiffres).
  L'IA intervient uniquement pour les commentaires et recommandations.
"""
from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from math import ceil
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.provisions_techniques")

# ── Constantes réglementaires CIMA ─────────────────────────────────────────────
_TAUX_TECHNIQUE_VIE_MIN     = 0.035   # Art. 63 CIMA — 3,5% minimum
_PPB_MIN_PCT_RESULTAT_VIE   = 0.85    # Art. 81 — min 85% résultat technique vie attribué
_PTS_TAUX_RC_AUTO_CORPOREL  = 0.04    # 4% des primes nettes RC Auto
_PG_TAUX_PM                 = 0.006   # 0,6% PM pour provisions de gestion vie
_PG_TAUX_PRIMES_NV          = 0.003   # 0,3% primes nettes non-vie pour gestion
_PREC_TAUX_TEST             = 0.50    # Test déficience : 50% primes engagées
_IBNR_TAUX_MOYEN            = 0.12    # 12% des PSAP connues — estimation IBNR standard zone CIMA


class AgentProvisionsTechniques(BaseAgent):
    type_agent = TypeAgent.PROVISIONS

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Provisions Techniques de YukpoAssurance, expert en calcul et contrôle des provisions CIMA.

PRINCIPES :
1. TOUJOURS calculer de façon déterministe — JAMAIS estimer les montants par IA
2. Citer systématiquement l'article CIMA de chaque provision
3. Signaler toute insuffisance de provision immédiatement à la Direction et à la Conformité
4. Toute dotation/reprise de provision → validation humaine avant écriture comptable
5. Les provisions vie (PM) doivent être calculées police par police en cas de contrôle CRCA

PROVISIONS NON-VIE (Art. 334 Code CIMA) :
- PPNA : 1/365ème par jour restant × prime brute — méthode prorata temporis ou 50% forfaitaire
- PSAP : évaluation dossier/dossier + IBNR (12% PSAP connues, minimum)
- PEq  : constituée progressivement pour branches à fort aléa (catastrophe, agricole)
- PREC : si S/P + frais > 50% des primes engagées → dotation complémentaire
- PG   : frais futurs de liquidation des sinistres en cours
- PTS  : RC Auto corporel = 4% primes nettes min, catastrophes selon réglementation

PROVISIONS VIE (Livre II CIMA) :
- PM  : méthode prospective, taux technique ≥ 3,5% — calcul individualisé par police
- PRC : contrats avec primes nettes fixes, risque croissant avec l'âge
- PPB : min 85% du résultat technique vie — alimentation annuelle obligatoire
- PEP : prévoyance collective — 6 mois de cotisations si résultats < 0

RÈGLE OR : provisions insuffisantes = violation Art. 337-1 → risque de retrait d'agrément"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "calculer_ppna",
                "description": "Calcule les Provisions pour Primes Non Acquises — Art. 334-1° CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "polices": {
                        "type": "array",
                        "description": "Liste des polices actives",
                        "items": {
                            "type": "object",
                            "properties": {
                                "police_id":        {"type": "string"},
                                "prime_brute_ttc":  {"type": "number"},
                                "date_effet":       {"type": "string", "description": "YYYY-MM-DD"},
                                "date_echeance":    {"type": "string", "description": "YYYY-MM-DD"},
                                "branche":          {"type": "string"},
                            }
                        }
                    },
                    "date_inventaire":    {"type": "string", "description": "YYYY-MM-DD — date d'arrêté"},
                    "methode":            {"type": "string", "enum": ["prorata_temporis", "forfait_50pct"]},
                    "fichier_excel_path": {"type": "string", "description": "Chemin fichier Excel si > 1000 polices"},
                }, "required": ["date_inventaire"]},
            },
            {
                "name": "calculer_psap",
                "description": "Calcule les Provisions pour Sinistres À Payer (PSAP + IBNR) — Art. 334-2° CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "sinistres_ouverts": {
                        "type": "array",
                        "description": "Liste des sinistres ouverts avec montants estimés",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reference":         {"type": "string"},
                                "montant_estime":    {"type": "number"},
                                "montant_deja_paye": {"type": "number"},
                                "branche":           {"type": "string"},
                                "date_survenance":   {"type": "string"},
                            }
                        }
                    },
                    "date_inventaire":    {"type": "string"},
                    "avec_ibnr":          {"type": "boolean", "description": "Inclure provision IBNR"},
                    "taux_ibnr_custom":   {"type": "number", "description": "Taux IBNR si différent du 12% standard"},
                    "fichier_excel_path": {"type": "string", "description": "Chemin fichier Excel si > 1000 sinistres"},
                }, "required": ["date_inventaire"]},
            },
            {
                "name": "calculer_pm_portefeuille",
                "description": "Calcule les Provisions Mathématiques totales portefeuille vie — Art. 63 CIMA (déterministe, police par police)",
                "input_schema": {"type": "object", "properties": {
                    "polices_vie": {
                        "type": "array",
                        "description": "Liste des contrats vie actifs",
                        "items": {
                            "type": "object",
                            "properties": {
                                "police_id":         {"type": "string"},
                                "type_produit":      {"type": "string"},
                                "capital_garanti":   {"type": "number"},
                                "prime_annuelle":    {"type": "number"},
                                "age_souscription":  {"type": "integer"},
                                "duree_totale_ans":  {"type": "integer"},
                                "duree_ecoulee_ans": {"type": "integer"},
                                "taux_technique":    {"type": "number"},
                            }
                        }
                    },
                    "date_inventaire":    {"type": "string"},
                    "taux_technique":     {"type": "number", "description": "Taux technique global si différent police par police"},
                    "fichier_excel_path": {"type": "string", "description": "Fichier Excel polices vie si > 1000"},
                }, "required": ["date_inventaire"]},
            },
            {
                "name": "calculer_ppb",
                "description": "Calcule la Provision pour Participation aux Bénéfices — Art. 81 CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "resultat_technique_vie":   {"type": "number", "description": "Résultat technique vie de l'exercice"},
                    "produits_financiers_vie":  {"type": "number", "description": "Produits financiers attribuables vie"},
                    "ppb_precedente":           {"type": "number", "description": "PPB de l'exercice précédent"},
                    "taux_revalorisation_min":  {"type": "number", "description": "Taux min garanti contractuellement"},
                    "pm_totales":               {"type": "number", "description": "PM totales pour calcul taux servi"},
                }, "required": ["resultat_technique_vie", "pm_totales"]},
            },
            {
                "name": "calculer_pts",
                "description": "Calcule les Provisions Techniques Spéciales — Art. 334 bis CIMA (RC Auto corporel, catastrophes)",
                "input_schema": {"type": "object", "properties": {
                    "primes_nettes_rc_auto":    {"type": "number"},
                    "primes_nettes_catastrophe": {"type": "number"},
                    "pts_actuelle":             {"type": "number", "description": "PTS déjà constituée"},
                    "plafond_pts_rc_auto":      {"type": "number", "description": "Plafond réglementaire (Art. 334 bis)"},
                }, "required": []},
            },
            {
                "name": "calculer_prec",
                "description": "Test de suffisance et calcul Provision pour Risques en Cours — Art. 334-5° CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "ppna_branche":   {"type": "number", "description": "PPNA calculée pour la branche"},
                    "sinistres_prev": {"type": "number", "description": "Sinistres estimés sur primes futures"},
                    "frais_prev":     {"type": "number", "description": "Frais estimés sur primes futures"},
                    "branche":        {"type": "string"},
                }, "required": ["ppna_branche", "sinistres_prev", "frais_prev", "branche"]},
            },
            {
                "name": "calculer_prc_vie",
                "description": "Calcule la Provision pour Risques Croissants (Vie) — Art. 63 bis CIMA",
                "input_schema": {"type": "object", "properties": {
                    "primes_nettes_vie": {"type": "number"},
                    "ratio_sinistres_primes_vie": {"type": "number", "description": "S/P vie exercice courant"},
                    "pm_vie":            {"type": "number", "description": "PM totales"},
                }, "required": ["primes_nettes_vie", "ratio_sinistres_primes_vie"]},
            },
            {
                "name": "tableau_provisions_global",
                "description": "Génère le tableau récapitulatif complet de toutes les provisions techniques (inventaire CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "exercice":              {"type": "integer"},
                    "date_inventaire":       {"type": "string"},
                    "ppna":                  {"type": "number"},
                    "psap":                  {"type": "number"},
                    "ibnr":                  {"type": "number"},
                    "prec":                  {"type": "number"},
                    "pg":                    {"type": "number"},
                    "peq":                   {"type": "number"},
                    "pts":                   {"type": "number"},
                    "pm_vie":                {"type": "number"},
                    "prc_vie":               {"type": "number"},
                    "ppb":                   {"type": "number"},
                    "fonds_propres":         {"type": "number"},
                    "actifs_representatifs": {"type": "number"},
                }, "required": ["exercice", "date_inventaire"]},
            },
            {
                "name": "analyser_ibnr",
                "description": "Estime les IBNR (Incurred But Not Reported) par méthode Chain-Ladder ou taux appliqué (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "methode":        {"type": "string", "enum": ["taux_applique", "chain_ladder", "bornhuetter_ferguson"]},
                    "branche":        {"type": "string"},
                    "triangle_dev":   {"type": "array", "description": "Triangle de développement (méthode chain-ladder)", "items": {"type": "array", "items": {"type": "number"}}},
                    "psap_connues":   {"type": "number", "description": "PSAP sur sinistres connus (méthode taux appliqué)"},
                    "taux_ibnr":      {"type": "number", "description": "Taux personnalisé (si méthode taux_applique)"},
                    "prime_acquise":  {"type": "number", "description": "Prime acquise branche (Bornhuetter-Ferguson)"},
                    "ratio_sp_ultime": {"type": "number", "description": "Ratio S/P ultime attendu (B-F)"},
                }, "required": ["methode", "branche"]},
            },
            {
                "name": "verifier_adequation_provisions",
                "description": "Vérifie l'adéquation globale des provisions vs actifs représentatifs — Art. 337 CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "total_provisions_techniques": {"type": "number"},
                    "actifs_representatifs":       {"type": "number"},
                    "fonds_propres":               {"type": "number"},
                    "marge_solvabilite_requise":   {"type": "number"},
                    "date_inventaire":             {"type": "string"},
                }, "required": ["total_provisions_techniques", "actifs_representatifs"]},
            },
            {
                "name": "dotation_reprise_provision",
                "description": "Calcule la dotation ou reprise à passer en comptabilité (déterministe) — VALIDATION OBLIGATOIRE",
                "input_schema": {"type": "object", "properties": {
                    "type_provision":   {"type": "string", "enum": ["ppna","psap","ibnr","pm","ppb","pts","prec","pg","peq","prc"]},
                    "montant_precedent": {"type": "number"},
                    "montant_cible":     {"type": "number"},
                    "exercice":          {"type": "integer"},
                    "branche":           {"type": "string"},
                }, "required": ["type_provision", "montant_precedent", "montant_cible"]},
            },
            {
                "name": "analyser_provisions_ia",
                "description": "Analyse IA de l'adéquation et de l'évolution des provisions — commentaire narratif direction",
                "input_schema": {"type": "object", "properties": {
                    "donnees_provisions": {"type": "object"},
                    "exercice":           {"type": "integer"},
                    "comparatif_n_1":     {"type": "object"},
                    "alertes":            {"type": "array", "items": {"type": "string"}},
                }, "required": ["donnees_provisions", "exercice"]},
            },
            {
                "name": "importer_donnees_excel",
                "description": "Importe et analyse un fichier Excel massif (polices, sinistres, actifs) par blocs de 10 000 lignes",
                "input_schema": {"type": "object", "properties": {
                    "fichier_path":  {"type": "string", "description": "Chemin absolu du fichier Excel ou CSV"},
                    "type_donnees":  {"type": "string", "enum": ["polices_non_vie", "polices_vie", "sinistres", "actifs", "primes_emises"]},
                    "champ_montant": {"type": "string", "description": "Nom de la colonne montant"},
                    "champ_date":    {"type": "string", "description": "Nom de la colonne date"},
                    "filtre_branche": {"type": "string"},
                    "taille_bloc":   {"type": "integer", "description": "Lignes par bloc (défaut 10 000)"},
                }, "required": ["fichier_path", "type_donnees"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT PROVISIONS TECHNIQUES — quand demander une information :

1. EXERCICE COMPTABLE NON PRÉCISÉ
   → "Pour quel exercice ou quelle date d'arrêté souhaitez-vous calculer les provisions techniques ? (Ex: 31/12/2024 ou T3 2025)"
   type_reponse: texte_libre

2. TYPE DE PROVISION CIBLÉE
   → "Quelles provisions techniques souhaitez-vous calculer ou contrôler ?"
   type_reponse: choix_multiple  choix: ["PPNA (Primes non acquises — Art. 334 CIMA)", "PSAP (Sinistres à payer — Art. 336)", "IBNR (Sinistres survenus non déclarés)", "PM (Provisions mathématiques vie — Art. 63)", "PPB (Participation aux bénéfices)", "PRC / PREC (Provisions catastrophes)", "Toutes provisions — liasse complète"]

3. MÉTHODE IBNR NON CHOISIE (PSAP)
   → "Quelle méthode de calcul de l'IBNR souhaitez-vous utiliser ?"
   type_reponse: choix_multiple  choix: ["Chain-Ladder (triangle de développement — méthode CIMA standard)", "Bornhuetter-Ferguson (hybride données internes + marché)", "Cape Cod (ratio de prime à risque)", "Méthode des coûts moyens", "Toutes méthodes — comparaison"]

4. DONNÉES TRIANGLES MANQUANTES
   → "Combien d'années de développement historique avez-vous disponibles pour le triangle de liquidation ? (Plus d'années = IBNR plus précis)"
   type_reponse: choix_multiple  choix: ["2 ans (données limitées — prudence requise)", "3 ans", "5 ans", "7 ans", "10 ans ou plus (données complètes)"]

5. BRANCHE D'ASSURANCE NON FILTRÉE
   → "Souhaitez-vous les provisions pour toutes les branches ou une branche spécifique ?"
   type_reponse: choix_multiple  choix: ["Toutes branches (portefeuille global)", "RC Auto uniquement", "MRH / Incendie", "Transport", "Accidents Corporels", "Vie & Prévoyance (PM uniquement)", "RC Pro / Divers"]

6. TAUX D'ACTUALISATION (PM vie)
   → "Quel taux technique appliquez-vous pour l'actualisation des provisions mathématiques vie ? (Taux maximum autorisé : 60% du taux moyen des obligations d'État Art. 63 CIMA)"
   type_reponse: nombre

7. ALERTE INSUFFISANCE — PLAN D'ACTION REQUIS
   → "Une insuffisance de provision a été détectée. Quelle action souhaitez-vous prendre ?"
   type_reponse: choix_multiple  choix: ["Dotation complémentaire immédiate (avec écriture comptable)", "Plan de régularisation sur 3 ans", "Notification CRCA uniquement", "Contre-expertise — demander un second calcul"]

PROGRESSION : Exercice → Type de provision → Méthode → Données disponibles → Validation.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            # ── PPNA ────────────────────────────────────────────────────────────
            if nom == "calculer_ppna":
                date_inv = date.fromisoformat(params["date_inventaire"])
                methode = params.get("methode", "prorata_temporis")
                polices = params.get("polices", [])

                # Si fichier Excel fourni → charger d'abord
                if params.get("fichier_excel_path") and not polices:
                    polices = await _charger_excel(params["fichier_excel_path"], "polices_non_vie")

                ppna_total = 0.0
                ppna_par_branche: dict[str, float] = {}
                for p in polices:
                    prime = p.get("prime_brute_ttc", 0)
                    date_effet = date.fromisoformat(p.get("date_effet", date_inv.isoformat()))
                    date_ech   = date.fromisoformat(p.get("date_echeance", (date_inv + timedelta(days=365)).isoformat()))
                    if methode == "prorata_temporis":
                        duree_totale = max((date_ech - date_effet).days, 1)
                        jours_restants = max((date_ech - date_inv).days, 0)
                        ppna = prime * jours_restants / duree_totale
                    else:
                        ppna = prime * 0.50  # forfait 50%
                    branche = p.get("branche", "divers")
                    ppna_par_branche[branche] = ppna_par_branche.get(branche, 0) + ppna
                    ppna_total += ppna

                return json.dumps({
                    "type": "PPNA",
                    "base_legale": "Art. 334-1° Code CIMA",
                    "date_inventaire": params["date_inventaire"],
                    "methode": methode,
                    "nb_polices": len(polices),
                    "ppna_total_fcfa": round(ppna_total),
                    "ppna_par_branche": {k: round(v) for k, v in ppna_par_branche.items()},
                }, ensure_ascii=False)

            # ── PSAP + IBNR ─────────────────────────────────────────────────────
            if nom == "calculer_psap":
                date_inv = date.fromisoformat(params["date_inventaire"])
                sinistres = params.get("sinistres_ouverts", [])
                if params.get("fichier_excel_path") and not sinistres:
                    sinistres = await _charger_excel(params["fichier_excel_path"], "sinistres")

                psap_total = 0.0
                psap_par_branche: dict[str, float] = {}
                for s in sinistres:
                    montant = max(s.get("montant_estime", 0) - s.get("montant_deja_paye", 0), 0)
                    branche = s.get("branche", "divers")
                    psap_par_branche[branche] = psap_par_branche.get(branche, 0) + montant
                    psap_total += montant

                ibnr = 0.0
                if params.get("avec_ibnr", True):
                    taux = params.get("taux_ibnr_custom", _IBNR_TAUX_MOYEN)
                    ibnr = psap_total * taux

                return json.dumps({
                    "type": "PSAP + IBNR",
                    "base_legale": "Art. 334-2° Code CIMA",
                    "date_inventaire": params["date_inventaire"],
                    "nb_sinistres": len(sinistres),
                    "psap_dossier_dossier_fcfa": round(psap_total),
                    "ibnr_fcfa": round(ibnr),
                    "psap_ibnr_total_fcfa": round(psap_total + ibnr),
                    "psap_par_branche": {k: round(v) for k, v in psap_par_branche.items()},
                    "taux_ibnr_applique_pct": round(params.get("taux_ibnr_custom", _IBNR_TAUX_MOYEN) * 100, 1),
                    "note": "IBNR = sinistres survenus non encore déclarés",
                }, ensure_ascii=False)

            # ── PM Portefeuille Vie ──────────────────────────────────────────────
            if nom == "calculer_pm_portefeuille":
                from core.workflow_engine import calculer_prime_vie
                date_inv = date.fromisoformat(params["date_inventaire"])
                polices = params.get("polices_vie", [])
                if params.get("fichier_excel_path") and not polices:
                    polices = await _charger_excel(params["fichier_excel_path"], "polices_vie")

                taux_global = params.get("taux_technique", _TAUX_TECHNIQUE_VIE_MIN)
                pm_total = 0.0
                pm_par_produit: dict[str, float] = {}
                nb_insuffisantes = 0
                for p in polices:
                    pm_init = p.get("pm_initiale", 0)
                    prime = p.get("prime_annuelle", 0)
                    taux = p.get("taux_technique", taux_global)
                    duree_ec = p.get("duree_ecoulee_ans", 0)
                    # Méthode prospective simplifiée (Art. 63)
                    pm = pm_init
                    for _ in range(max(duree_ec, 1)):
                        pm = pm * (1 + taux) + prime * 0.90
                    if taux < _TAUX_TECHNIQUE_VIE_MIN:
                        nb_insuffisantes += 1
                    produit = p.get("type_produit", "vie_entiere")
                    pm_par_produit[produit] = pm_par_produit.get(produit, 0) + pm
                    pm_total += pm

                return json.dumps({
                    "type": "PM",
                    "base_legale": "Art. 63 Code CIMA — taux technique minimum 3,5%",
                    "date_inventaire": params["date_inventaire"],
                    "nb_polices": len(polices),
                    "pm_totales_fcfa": round(pm_total),
                    "pm_par_produit": {k: round(v) for k, v in pm_par_produit.items()},
                    "nb_polices_taux_insuffisant": nb_insuffisantes,
                    "alerte_taux": nb_insuffisantes > 0,
                    "taux_technique_min_requis_pct": _TAUX_TECHNIQUE_VIE_MIN * 100,
                }, ensure_ascii=False)

            # ── PPB ──────────────────────────────────────────────────────────────
            if nom == "calculer_ppb":
                res_tech = params["resultat_technique_vie"]
                prod_fin = params.get("produits_financiers_vie", 0)
                pm = params["pm_totales"]
                ppb_prec = params.get("ppb_precedente", 0)
                taux_min_garanti = params.get("taux_revalorisation_min", _TAUX_TECHNIQUE_VIE_MIN)
                # Base PPB = résultat technique + produits financiers excédentaires
                base_ppb = res_tech + prod_fin
                ppb_min_obligatoire = max(base_ppb * _PPB_MIN_PCT_RESULTAT_VIE, 0)
                ppb_min_pour_revalorisation = pm * taux_min_garanti
                ppb_cible = max(ppb_min_obligatoire, ppb_min_pour_revalorisation)
                dotation = max(ppb_cible - ppb_prec, 0)
                from core.approval_queue import approval_queue
                if dotation > 0:
                    await approval_queue.ajouter({
                        "type": "dotation_provision_ppb",
                        "montant": dotation,
                        "ppb_avant": ppb_prec,
                        "ppb_apres": ppb_prec + dotation,
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": f"Dotation PPB : {dotation:,} FCFA — Art. 81 CIMA".replace(",", " "),
                    })
                return json.dumps({
                    "type": "PPB",
                    "base_legale": "Art. 81 Code CIMA — min 85% résultat technique vie",
                    "resultat_technique_vie": round(res_tech),
                    "ppb_minimum_obligatoire": round(ppb_min_obligatoire),
                    "ppb_pour_revalorisation": round(ppb_min_pour_revalorisation),
                    "ppb_cible": round(ppb_cible),
                    "ppb_precedente": round(ppb_prec),
                    "dotation_exercice": round(dotation),
                    "soumis_validation": dotation > 0,
                }, ensure_ascii=False)

            # ── PTS ──────────────────────────────────────────────────────────────
            if nom == "calculer_pts":
                primes_rc = params.get("primes_nettes_rc_auto", 0)
                primes_cat = params.get("primes_nettes_catastrophe", 0)
                pts_actuelle = params.get("pts_actuelle", 0)
                pts_rc_auto_requise = primes_rc * _PTS_TAUX_RC_AUTO_CORPOREL
                # PTS catastrophe : alimentée progressivement — 1% primes cat par an jusqu'à plafond
                pts_cat_annuelle = primes_cat * 0.01
                plafond = params.get("plafond_pts_rc_auto", 50_000_000)
                pts_rc_auto = min(max(pts_rc_auto_requise, pts_actuelle), plafond)
                return json.dumps({
                    "type": "PTS",
                    "base_legale": "Art. 334 bis Code CIMA",
                    "pts_rc_auto_corporel_fcfa": round(pts_rc_auto),
                    "pts_rc_auto_requise_min": round(pts_rc_auto_requise),
                    "pts_catastrophe_dotation_annuelle": round(pts_cat_annuelle),
                    "taux_rc_auto_pct": _PTS_TAUX_RC_AUTO_CORPOREL * 100,
                    "conforme": pts_actuelle >= pts_rc_auto_requise,
                }, ensure_ascii=False)

            # ── PREC ─────────────────────────────────────────────────────────────
            if nom == "calculer_prec":
                ppna = params["ppna_branche"]
                sinistres_prev = params["sinistres_prev"]
                frais_prev = params["frais_prev"]
                branche = params["branche"]
                # Ratio combiné prévisionnel sur primes futures
                ratio = (sinistres_prev + frais_prev) / max(ppna, 1)
                prec = max((sinistres_prev + frais_prev) - ppna, 0) if ratio > _PREC_TAUX_TEST else 0
                return json.dumps({
                    "type": "PREC",
                    "base_legale": "Art. 334-5° Code CIMA",
                    "branche": branche,
                    "ratio_combine_previsionnel_pct": round(ratio * 100, 1),
                    "test_suffisance": ratio > _PREC_TAUX_TEST,
                    "prec_fcfa": round(prec),
                    "seuil_test_pct": _PREC_TAUX_TEST * 100,
                    "dotation_requise": prec > 0,
                }, ensure_ascii=False)

            # ── PRC Vie ──────────────────────────────────────────────────────────
            if nom == "calculer_prc_vie":
                primes = params["primes_nettes_vie"]
                sp = params["ratio_sinistres_primes_vie"]
                pm = params.get("pm_vie", 0)
                # PRC constituée si S/P vie > 85% pendant 3 exercices consécutifs
                # Ici : 1 exercice, on calcule le besoin théorique
                prc = max((sp - 0.85) * primes, 0) if sp > 0.85 else 0
                return json.dumps({
                    "type": "PRC",
                    "base_legale": "Art. 63 bis Code CIMA",
                    "ratio_sp_vie_pct": round(sp * 100, 1),
                    "seuil_declenchement_pct": 85,
                    "prc_calculee_fcfa": round(prc),
                    "dotation_requise": prc > 0,
                    "note": "PRC obligatoire si S/P vie > 85% sur 3 exercices consécutifs",
                }, ensure_ascii=False)

            # ── Tableau Global ───────────────────────────────────────────────────
            if nom == "tableau_provisions_global":
                ex = params["exercice"]
                ppna  = params.get("ppna", 0)
                psap  = params.get("psap", 0)
                ibnr  = params.get("ibnr", 0)
                prec  = params.get("prec", 0)
                pg    = params.get("pg", 0)
                peq   = params.get("peq", 0)
                pts   = params.get("pts", 0)
                pm    = params.get("pm_vie", 0)
                prc   = params.get("prc_vie", 0)
                ppb   = params.get("ppb", 0)
                total_nv = ppna + psap + ibnr + prec + pg + peq + pts
                total_v  = pm + prc + ppb
                total    = total_nv + total_v
                fp       = params.get("fonds_propres", 0)
                actifs   = params.get("actifs_representatifs", 0)
                couverture = round(actifs / max(total, 1) * 100, 1)
                conforme = actifs >= total and couverture >= 100
                tableau = {
                    "exercice": ex,
                    "date_inventaire": params["date_inventaire"],
                    "provisions_non_vie": {
                        "PPNA":  round(ppna),
                        "PSAP":  round(psap),
                        "IBNR":  round(ibnr),
                        "PREC":  round(prec),
                        "PG":    round(pg),
                        "PEq":   round(peq),
                        "PTS":   round(pts),
                        "total": round(total_nv),
                    },
                    "provisions_vie": {
                        "PM":    round(pm),
                        "PRC":   round(prc),
                        "PPB":   round(ppb),
                        "total": round(total_v),
                    },
                    "total_provisions_techniques_fcfa": round(total),
                    "actifs_representatifs_fcfa": round(actifs),
                    "couverture_pct": couverture,
                    "fonds_propres_fcfa": round(fp),
                    "conforme_art_337": conforme,
                    "base_legale": "Art. 334-339 Code CIMA — Provisions techniques",
                }
                if not conforme:
                    tableau["alerte"] = f"INSUFFISANCE DE COUVERTURE : {couverture:.1f}% — Art. 337 CIMA — notification CRCA obligatoire"
                return json.dumps(tableau, ensure_ascii=False)

            # ── IBNR ─────────────────────────────────────────────────────────────
            if nom == "analyser_ibnr":
                methode = params["methode"]
                branche = params["branche"]
                if methode == "taux_applique":
                    psap = params.get("psap_connues", 0)
                    taux = params.get("taux_ibnr", _IBNR_TAUX_MOYEN)
                    ibnr = round(psap * taux)
                    return json.dumps({
                        "methode": "Taux appliqué",
                        "branche": branche,
                        "psap_base": psap,
                        "taux_ibnr_pct": round(taux * 100, 1),
                        "ibnr_fcfa": ibnr,
                        "note": "Standard zone CIMA : 12% PSAP. Adapter selon expérience compagnie.",
                    }, ensure_ascii=False)

                if methode == "chain_ladder":
                    triangle = params.get("triangle_dev", [])
                    if not triangle:
                        return "Triangle de développement non fourni pour Chain-Ladder"
                    # Chain-Ladder : facteurs de développement colonne par colonne
                    n = len(triangle)
                    facteurs = []
                    for col in range(len(triangle[0]) - 1):
                        num = sum(triangle[lig][col + 1] for lig in range(n - col - 1) if col + 1 < len(triangle[lig]))
                        den = sum(triangle[lig][col]     for lig in range(n - col - 1) if col < len(triangle[lig]))
                        facteurs.append(round(num / max(den, 1), 4))
                    # Projection des diagonales futures
                    projections = []
                    for lig in range(n):
                        val = triangle[lig][-1] if triangle[lig] else 0
                        nb_dev_restant = n - 1 - lig
                        for f in facteurs[-nb_dev_restant:]:
                            val *= f
                        projections.append(round(val))
                    ibnr = sum(projections[lig] - (triangle[lig][-1] if triangle[lig] else 0) for lig in range(n))
                    return json.dumps({
                        "methode": "Chain-Ladder",
                        "branche": branche,
                        "facteurs_developpement": facteurs,
                        "projections_definitives": projections,
                        "ibnr_total_fcfa": round(max(ibnr, 0)),
                    }, ensure_ascii=False)

                if methode == "bornhuetter_ferguson":
                    prime = params.get("prime_acquise", 0)
                    sp_ultime = params.get("ratio_sp_ultime", 0.70)
                    sinistres_observes = params.get("psap_connues", 0)
                    # B-F : IBNR = % non développé × (prime × S/P ultime)
                    pct_non_dev = params.get("pct_non_developpe", 0.30)
                    ibnr = round(pct_non_dev * prime * sp_ultime)
                    return json.dumps({
                        "methode": "Bornhuetter-Ferguson",
                        "branche": branche,
                        "prime_acquise": prime,
                        "sp_ultime_pct": round(sp_ultime * 100, 1),
                        "pct_non_developpe": round(pct_non_dev * 100, 1),
                        "sinistres_observes": sinistres_observes,
                        "ibnr_bf_fcfa": ibnr,
                    }, ensure_ascii=False)

                return f"Méthode IBNR '{methode}' non reconnue"

            # ── Adéquation ───────────────────────────────────────────────────────
            if nom == "verifier_adequation_provisions":
                total = params["total_provisions_techniques"]
                actifs = params["actifs_representatifs"]
                fp = params.get("fonds_propres", 0)
                marge_req = params.get("marge_solvabilite_requise", 0)
                couverture = round(actifs / max(total, 1) * 100, 1)
                surplus = actifs - total
                marge_ok = fp >= marge_req if marge_req else True
                conforme = couverture >= 100 and marge_ok
                alertes = []
                if couverture < 100:
                    alertes.append(f"INSUFFISANCE ACTIFS : {couverture:.1f}% — déficit {abs(surplus):,.0f} FCFA".replace(",", " "))
                if not marge_ok:
                    alertes.append(f"MARGE SOLVABILITÉ INSUFFISANTE : {fp:,.0f} FCFA < {marge_req:,.0f} FCFA requis".replace(",", " "))
                return json.dumps({
                    "date_inventaire": params.get("date_inventaire"),
                    "total_provisions": round(total),
                    "actifs_representatifs": round(actifs),
                    "couverture_pct": couverture,
                    "surplus_deficit_fcfa": round(surplus),
                    "fonds_propres": round(fp),
                    "marge_solvabilite_requise": round(marge_req),
                    "marge_ok": marge_ok,
                    "conforme_art_337_cima": conforme,
                    "alertes": alertes,
                    "base_legale": "Art. 337 Code CIMA — Représentation des provisions",
                }, ensure_ascii=False)

            # ── Dotation/Reprise ─────────────────────────────────────────────────
            if nom == "dotation_reprise_provision":
                prec_mnt = params["montant_precedent"]
                cible    = params["montant_cible"]
                delta    = cible - prec_mnt
                sens     = "dotation" if delta > 0 else "reprise" if delta < 0 else "inchangé"
                from core.approval_queue import approval_queue
                if delta != 0:
                    await approval_queue.ajouter({
                        "type": f"{sens}_provision_{params['type_provision']}",
                        "type_provision": params["type_provision"],
                        "branche": params.get("branche", ""),
                        "montant_precedent": prec_mnt,
                        "montant_cible": cible,
                        "delta": abs(delta),
                        "sens": sens,
                        "exercice": params.get("exercice"),
                        "montant": abs(delta),
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": (
                            f"{sens.upper()} {params['type_provision'].upper()} : "
                            f"{abs(delta):,.0f} FCFA — exercice {params.get('exercice', '')} — "
                            f"Art. 334 CIMA"
                        ).replace(",", " "),
                    })
                return json.dumps({
                    "type_provision": params["type_provision"],
                    "montant_precedent_fcfa": round(prec_mnt),
                    "montant_cible_fcfa": round(cible),
                    "delta_fcfa": round(delta),
                    "sens": sens,
                    "soumis_validation": delta != 0,
                    "base_legale": "Art. 334-339 Code CIMA",
                }, ensure_ascii=False)

            # ── Analyse IA ───────────────────────────────────────────────────────
            if nom == "analyser_provisions_ia":
                from core.ia_client import ModeIA, ia_client
                comparatif = params.get("comparatif_n_1", {})
                alertes = params.get("alertes", [])
                prompt = f"""Analyse les provisions techniques de cet exercice.
Exercice : {params['exercice']}
Données provisions :
{json.dumps(params['donnees_provisions'], ensure_ascii=False, indent=2)}

Comparatif N-1 :
{json.dumps(comparatif, ensure_ascii=False, indent=2) if comparatif else "Non fourni"}

Alertes détectées : {alertes}

Analyse (pour Direction et CRCA) :
1. Évolution des provisions vs N-1 — explication des variations significatives
2. Adéquation des provisions aux risques réels
3. Risques d'insuffisance ou de sur-provisionnement
4. Conformité Art. 334-339 CIMA
5. Recommandations pour le prochain exercice
Style : professionnel, concis, orienté action. Citer les articles CIMA précis."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return rep.contenu

            # ── Import Excel massif ──────────────────────────────────────────────
            if nom == "importer_donnees_excel":
                return await _traiter_import_excel(
                    fichier_path=params["fichier_path"],
                    type_donnees=params["type_donnees"],
                    champ_montant=params.get("champ_montant", "prime"),
                    champ_date=params.get("champ_date", "date_effet"),
                    filtre_branche=params.get("filtre_branche"),
                    taille_bloc=params.get("taille_bloc", 10_000),
                )

            return f"Outil '{nom}' non reconnu"

        except Exception as e:
            logger.error(f"[AgentProvisionsTechniques] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _charger_excel(path: str, type_donnees: str) -> list[dict]:
    """Charge un fichier Excel/CSV par blocs de 10 000 lignes et retourne une liste de dicts."""
    import asyncio
    def _sync_load():
        try:
            import pandas as pd
            rows = []
            if path.lower().endswith(".csv"):
                for chunk in pd.read_csv(path, chunksize=10_000, encoding="utf-8-sig"):
                    rows.extend(chunk.fillna(0).to_dict("records"))
            else:
                for chunk in pd.read_excel(path, chunksize=10_000):
                    rows.extend(chunk.fillna(0).to_dict("records"))
            return rows
        except ImportError:
            return []
    return await asyncio.to_thread(_sync_load)


async def _traiter_import_excel(
    fichier_path: str,
    type_donnees: str,
    champ_montant: str = "prime",
    champ_date: str = "date_effet",
    filtre_branche: str | None = None,
    taille_bloc: int = 10_000,
) -> str:
    """Import et agrégation d'un fichier Excel massif par blocs."""
    import asyncio
    def _sync_process():
        try:
            import pandas as pd
            total_lignes = 0
            total_montant = 0.0
            par_branche: dict[str, float] = {}
            nb_blocs = 0

            reader_kwargs = {"chunksize": taille_bloc}
            if fichier_path.lower().endswith(".csv"):
                reader = pd.read_csv(fichier_path, **reader_kwargs, encoding="utf-8-sig")
            else:
                reader = pd.read_excel(fichier_path, **reader_kwargs)

            for chunk in reader:
                nb_blocs += 1
                if filtre_branche and "branche" in chunk.columns:
                    chunk = chunk[chunk["branche"] == filtre_branche]
                total_lignes += len(chunk)
                if champ_montant in chunk.columns:
                    total_montant += chunk[champ_montant].fillna(0).sum()
                if "branche" in chunk.columns and champ_montant in chunk.columns:
                    for branche, groupe in chunk.groupby("branche"):
                        par_branche[str(branche)] = par_branche.get(str(branche), 0) + groupe[champ_montant].fillna(0).sum()

            return json.dumps({
                "fichier": fichier_path.split("\\")[-1].split("/")[-1],
                "type_donnees": type_donnees,
                "nb_lignes_traitees": total_lignes,
                "nb_blocs": nb_blocs,
                "taille_bloc": taille_bloc,
                "total_montant_fcfa": round(total_montant),
                "repartition_branche": {k: round(v) for k, v in sorted(par_branche.items(), key=lambda x: -x[1])},
                "filtre_branche": filtre_branche or "aucun",
            }, ensure_ascii=False)
        except ImportError:
            return json.dumps({"erreur": "pandas non installé — pip install pandas openpyxl"})
        except Exception as e:
            return json.dumps({"erreur": str(e)})

    return await asyncio.to_thread(_sync_process)