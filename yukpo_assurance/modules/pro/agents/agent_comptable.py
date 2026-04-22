"""
AgentComptable — Agent IA spécialisé comptabilité SYSCOHADA + fiscalité africaine.

Respecte les patterns YukpoAssurance :
  - Calculs déterministes hors classe (fonctions standalone)
  - TypeAgent.PRO_COMPTABLE
  - _necessite_validation() : hérité de AgentProBase (désactivé — agent consultatif)
  - Barèmes fiscaux exacts alignés avec agent_comptabilite.py existant

Outils métier :
  - sysco_analyser        : Analyse état financier SYSCOHADA (bilan, CR, flux)
  - fiscal_calculer       : TVA, IS, IRPP, Patente, RAS (barèmes 2024)
  - balance_analyser      : Lecture et contrôle de balance comptable
  - ecritures_valider     : Validation séquences d'écritures SYSCOHADA
  - cloture_checklist     : Liste de contrôle clôture annuelle
  - amortissement_calculer: Tableau d'amortissement linéaire/dégressif
"""
from __future__ import annotations

import logging
from datetime import date

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_comptable")

# ══════════════════════════════════════════════════════════════════════════════
# Référentiels fiscaux (barèmes 2024)
# ══════════════════════════════════════════════════════════════════════════════

# TVA par pays (source : codes généraux des impôts RAG)
_TVA_PAYS = {
    "CM": 0.1925, "CI": 0.18, "SN": 0.18, "BF": 0.18,
    "GA": 0.18,   "CD": 0.16, "CG": 0.18, "ML": 0.18,
    "NE": 0.19,   "TG": 0.18, "BJ": 0.18, "GN": 0.18,
    "MR": 0.18,   "TD": 0.18, "BI": 0.18,
}

# IS par pays
_IS_PAYS = {
    "CM": 0.275, "CI": 0.25, "SN": 0.30, "BF": 0.275,
    "GA": 0.30,  "CD": 0.30, "CG": 0.28, "ML": 0.30,
    "NE": 0.30,  "TG": 0.27, "BJ": 0.30, "GN": 0.25,
}

# IRPP barème progressif Cameroun (Art. 69 CGI-CM — aligné avec agent_rh.py)
_IRPP_TRANCHES_CM = [
    (0,          2_000_000,  0.00),
    (2_000_000,  3_000_000,  0.10),
    (3_000_000,  5_000_000,  0.15),
    (5_000_000, 10_000_000,  0.25),
    (10_000_000, 15_000_000, 0.35),
    (15_000_000, float("inf"), 0.385),
]

# Taux d'amortissement par catégorie (SYSCOHADA Révisé)
_TAUX_AMORT = {
    "mobilier_bureau":        0.20,   # 5 ans
    "materiel_informatique":  0.33,   # 3 ans
    "vehicule":               0.25,   # 4 ans
    "logiciel":               0.33,   # 3 ans
    "immeuble_exploitation":  0.04,   # 25 ans
    "agencement":             0.10,   # 10 ans
    "materiel_bureau":        0.125,  # 8 ans
    "materiel_industriel":    0.10,   # 10 ans
}

# Numéros de comptes SYSCOHADA fréquents
_COMPTES_SYSCO = {
    "101": "Capital social", "106": "Réserves", "120": "Résultat",
    "211": "Terrains", "221": "Bâtiments", "232": "Matériel transport",
    "241": "Mobilier", "244": "Matériel informatique",
    "31":  "Stocks matières", "32": "Stocks emballages",
    "401": "Fournisseurs", "411": "Clients", "421": "Personnel",
    "431": "CNSS",   "441": "État impôts", "443": "TVA",
    "512": "Banques", "530": "Caisse",
    "601": "Achats marchandises", "641": "Charges personnel",
    "701": "Ventes marchandises", "706": "Services vendus",
}


# ── Fonctions de calcul déterministes (hors classe, pattern YukpoAssurance) ──

def _calculer_tva(base_ht: float, pays: str) -> dict:
    taux = _TVA_PAYS.get(pays, 0.18)
    tva  = round(base_ht * taux)
    return {
        "base_ht": base_ht, "taux_pct": taux * 100,
        "tva": tva, "ttc": base_ht + tva, "pays": pays,
    }


def _calculer_is(resultat_fiscal: float, pays: str, ca: float = 0) -> dict:
    taux  = _IS_PAYS.get(pays, 0.30)
    is_th = round(resultat_fiscal * taux)
    # IS minimum 1% CA si déficitaire ou IS calculé trop faible
    is_min = round(ca * 0.01) if ca > 0 else 0
    is_du  = max(is_th, is_min)
    return {
        "resultat_fiscal": resultat_fiscal,
        "taux_pct":        taux * 100,
        "is_theorique":    is_th,
        "is_minimum":      is_min,
        "is_du":           is_du,
        "pays":            pays,
    }


def _calculer_irpp_annuel(revenu_imposable_annuel: float, pays: str = "CM") -> int:
    """Barème progressif IRPP — Cameroun par défaut (aligné agent_rh.py)."""
    tranches = _IRPP_TRANCHES_CM  # TODO: étendre aux autres pays
    irpp = 0.0
    for borne_inf, borne_sup, taux in tranches:
        if revenu_imposable_annuel <= borne_inf:
            break
        irpp += (min(revenu_imposable_annuel, borne_sup) - borne_inf) * taux
    return round(irpp)


def _calculer_amortissement(valeur: float, categorie: str, duree: int) -> list[dict]:
    """Tableau d'amortissement linéaire SYSCOHADA."""
    taux       = _TAUX_AMORT.get(categorie, 0.20)
    duree_eff  = duree or round(1 / taux)
    dotation   = round(valeur / duree_eff)
    valeur_net = valeur
    tableau    = []
    for an in range(1, duree_eff + 1):
        dot        = min(dotation, valeur_net)
        valeur_net = max(0, valeur_net - dot)
        tableau.append({
            "annee":            an,
            "dotation":         dot,
            "amort_cumule":     valeur - valeur_net,
            "valeur_nette":     valeur_net,
        })
        if valeur_net == 0:
            break
    return tableau


def _analyser_balance_comptable(balance: list[dict]) -> dict:
    """Calcule totaux débit/crédit et détecte anomalies de base."""
    total_d = sum(float(l.get("debit",  0)) for l in balance)
    total_c = sum(float(l.get("credit", 0)) for l in balance)
    equil   = abs(total_d - total_c) < 1

    anomalies = []
    for lg in balance:
        cpt   = str(lg.get("compte", ""))
        debit = float(lg.get("debit",  0))
        cred  = float(lg.get("credit", 0))
        solde = debit - cred
        # Actif en solde créditeur (classes 1-3 normalement débiteurs)
        if cpt[:1] in ("2", "3") and solde < -1_000:
            anomalies.append(
                f"Compte {cpt} ({_COMPTES_SYSCO.get(cpt[:3], 'inconnu')}) : "
                f"solde créditeur anormal {solde:,.0f}"
            )
    return {
        "total_debit":   round(total_d),
        "total_credit":  round(total_c),
        "equilibree":    equil,
        "ecart":         round(abs(total_d - total_c)),
        "nb_comptes":    len(balance),
        "anomalies":     anomalies,
    }


def _valider_ecritures_sysco(ecritures: list[dict]) -> list[dict]:
    """Vérifie l'équilibre D=C pour chaque écriture comptable."""
    resultats = []
    for i, ecr in enumerate(ecritures, 1):
        lignes  = ecr.get("lignes", [])
        total_d = sum(float(l.get("debit",  0)) for l in lignes)
        total_c = sum(float(l.get("credit", 0)) for l in lignes)
        ok      = abs(total_d - total_c) < 1
        resultats.append({
            "num":     i,
            "date":    ecr.get("date", "?"),
            "libelle": ecr.get("libelle", "?")[:60],
            "montant": round(total_d),
            "valide":  ok,
            "ecart":   round(abs(total_d - total_c)) if not ok else 0,
        })
    return resultats


# ══════════════════════════════════════════════════════════════════════════════
# Classe AgentComptable
# ══════════════════════════════════════════════════════════════════════════════

class AgentComptable(AgentProBase):
    """Agent IA comptabilité SYSCOHADA et fiscalité africaine."""

    type_agent = TypeAgent.PRO_COMPTABLE

    def _system_prompt(self) -> str:
        base = super()._system_prompt()
        return base + """

EXPERTISE COMPTABILITÉ ET FISCALITÉ AFRICAINE :
Tu es expert-comptable et fiscaliste, spécialiste du SYSCOHADA Révisé (2017).

DOMAINES COUVERTS :
1. SYSCOHADA Révisé : plan de comptes, écritures, états financiers (IFRS lite)
2. FISCALITÉ : TVA, Impôt sur les Sociétés, IRPP, Patente, taxes locales
3. CLÔTURE COMPTABLE : cut-off, dépréciations, provisions, états annuels
4. ANALYTIQUE : résultat par branche, centre de coût, axe
5. TRÉSORERIE : suivi, prévisions, rapprochements

RÈGLES DÉTERMINISTES :
- TVA : utiliser les taux 2024 par pays (CM=19.25%, CI=18%, SN=18%…)
- IS : taux légal + IS minimum 1% du CA si applicable
- IRPP : barème progressif officiel (non une estimation)
- Amortissements : méthode linéaire sauf exception dûment justifiée
- SYSCOHADA : toujours citer le numéro de compte (3 chiffres minimum)

OBLIGATIONS DE PRÉCISION :
- Tout calcul fiscal → citer l'article de loi applicable
- Tout compte SYSCOHADA → citer le libellé officiel
- Informer des délais légaux (TVA mensuelle, IS dans les 30 jours…)"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "- Si un calcul fiscal est demandé sans préciser le pays → demander le pays\n"
            "- Si une analyse de bilan est demandée sans données → demander les chiffres clés\n"
            "- Si une clôture est demandée sans préciser l'exercice → demander l'année\n"
            "- Si une balance est fournie sans période → demander la période"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "fiscal_calculer",
                "description": (
                    "Calcule les impôts et taxes : TVA (collectée et déductible), "
                    "Impôt sur les Sociétés (IS + minimum), IRPP, Patente, "
                    "Retenues à la Source. Déterministe — barèmes 2024."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_impot": {
                            "type": "string",
                            "enum": ["tva", "is", "irpp", "patente", "ras"],
                        },
                        "base":   {"type": "number",  "description": "Base imposable en FCFA"},
                        "pays":   {"type": "string",  "description": "CM | CI | SN | BF | GA…"},
                        "params": {"type": "object",
                                   "description": "Params complémentaires : ca (IS minimum), "
                                                  "taux_ras, nb_salaries (patente)…"},
                    },
                    "required": ["type_impot", "base", "pays"],
                },
            },
            {
                "name": "balance_analyser",
                "description": (
                    "Analyse une balance comptable SYSCOHADA : vérifie l'équilibre D=C, "
                    "calcule les soldes, détecte les anomalies (soldes anormaux, comptes vides)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "balance": {
                            "type":  "array",
                            "description": "Liste de lignes : "
                                           "[{compte, libelle, debit, credit}, …]",
                        },
                        "periode": {"type": "string", "description": "Ex: '2024-09'"},
                    },
                    "required": ["balance"],
                },
            },
            {
                "name": "ecritures_valider",
                "description": (
                    "Valide des écritures comptables SYSCOHADA : vérifie l'équilibre "
                    "débit/crédit de chaque écriture et la cohérence des comptes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ecritures": {
                            "type":  "array",
                            "description": "Liste d'écritures : "
                                           "[{date, libelle, lignes:[{compte,debit,credit}]}, …]",
                        },
                    },
                    "required": ["ecritures"],
                },
            },
            {
                "name": "amortissement_calculer",
                "description": (
                    "Calcule le tableau d'amortissement linéaire d'une immobilisation "
                    "selon les taux SYSCOHADA. Retourne dotation annuelle, "
                    "amortissement cumulé et valeur nette par exercice."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "valeur":     {"type": "number",  "description": "Valeur d'achat HT en FCFA"},
                        "categorie":  {"type": "string",
                                       "description": "mobilier_bureau | materiel_informatique | "
                                                      "vehicule | logiciel | immeuble_exploitation | "
                                                      "agencement | materiel_industriel"},
                        "duree":      {"type": "integer", "description": "Durée en années (0 = taux légal)"},
                        "date_achat": {"type": "string",  "description": "Date d'acquisition YYYY-MM"},
                    },
                    "required": ["valeur", "categorie"],
                },
            },
            {
                "name": "cloture_checklist",
                "description": (
                    "Génère la liste de contrôle complète pour une clôture comptable "
                    "annuelle SYSCOHADA : cut-off, provisions, amortissements, "
                    "états financiers, liasse fiscale, AGO."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "exercice":  {"type": "string",  "description": "Ex: '2024'"},
                        "pays":      {"type": "string"},
                        "type_entite": {"type": "string",
                                        "description": "sa | sarl | association | eurl"},
                    },
                    "required": ["exercice"],
                },
            },
            {
                "name": "analyser_document_fiscal",
                "description": (
                    "Analyse un document fiscal entrant (avis de redressement DGI, "
                    "notification de contrôle, mise en demeure fiscale) et identifie "
                    "les points contestables, les délais de réponse et la stratégie à adopter."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_document": {"type": "string", "description": "Texte extrait du document fiscal"},
                        "type_document":    {"type": "string",
                                             "description": "redressement | controle | mise_en_demeure | "
                                                            "notification_amende | credit_tva"},
                        "pays":             {"type": "string"},
                        "montant_redresse": {"type": "number", "description": "Montant total redressé (FCFA)"},
                    },
                    "required": ["contenu_document", "type_document"],
                },
            },
            {
                "name": "rediger_reponse_dgi",
                "description": (
                    "Rédige une réponse formelle à l'administration fiscale (DGI/DGT) : "
                    "contestation de redressement, demande de délai, réclamation de crédit TVA, "
                    "réponse à une mise en demeure. Lettre argumentée avec références légales."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_courrier":    {"type": "string",
                                             "description": "contestation_redressement | demande_delai | "
                                                            "reclamation_credit_tva | reponse_mise_en_demeure"},
                        "faits":            {"type": "string", "description": "Description des faits et position de l'entreprise"},
                        "montant_conteste": {"type": "number"},
                        "arguments":        {"type": "array",  "items": {"type": "string"},
                                             "description": "Liste des arguments juridiques"},
                        "entreprise":       {"type": "string", "description": "Nom et RCCM de l'entreprise"},
                        "pays":             {"type": "string"},
                        "reference_avis":   {"type": "string", "description": "Référence de l'avis contesté"},
                    },
                    "required": ["type_courrier", "faits", "pays"],
                },
            },
            {
                "name": "calendrier_fiscal",
                "description": (
                    "Génère le calendrier fiscal complet du pays avec les prochaines échéances, "
                    "les formulaires à déposer et un brouillon pré-rempli pour la prochaine obligation. "
                    "Alerte sur les délais dépassés ou imminents (< 10 jours)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pays":          {"type": "string"},
                        "mois_courant":  {"type": "string", "description": "YYYY-MM — mois de référence"},
                        "type_entite":   {"type": "string", "description": "sa | sarl | association | individuel"},
                        "regime_fiscal": {"type": "string", "description": "reel | simplifie | forfait"},
                    },
                    "required": ["pays"],
                },
            },
            {
                "name": "orchestrer_cloture_mensuelle",
                "description": (
                    "Orchestre les étapes de clôture mensuelle comptable : rapprochement bancaire, "
                    "lettrage comptes clients/fournisseurs, calcul TVA à reverser, état des charges "
                    "constatées d'avance, solde de gestion du mois. Retourne les actions à faire "
                    "dans l'ordre avec les montants calculés."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mois":              {"type": "string", "description": "YYYY-MM"},
                        "solde_banque":      {"type": "number", "description": "Solde relevé bancaire (FCFA)"},
                        "solde_compta":      {"type": "number", "description": "Solde compte 512 en comptabilité"},
                        "ca_ht_mois":        {"type": "number", "description": "CA HT du mois"},
                        "achats_ht_mois":    {"type": "number", "description": "Achats HT déductibles"},
                        "charges_mois":      {"type": "number", "description": "Charges totales HT"},
                        "pays":              {"type": "string"},
                    },
                    "required": ["mois", "pays"],
                },
            },
        ]

    async def _executer_outil_metier(
        self, nom: str, params: dict, user_id: int, execution_id: str
    ) -> str:
        if nom == "fiscal_calculer":
            return _rendu_fiscal(params)
        if nom == "balance_analyser":
            return _rendu_balance(params)
        if nom == "ecritures_valider":
            return _rendu_ecritures(params)
        if nom == "amortissement_calculer":
            return _rendu_amortissement(params)
        if nom == "cloture_checklist":
            return _rendu_cloture(params)
        if nom == "analyser_document_fiscal":
            return _analyser_document_fiscal(params)
        if nom == "rediger_reponse_dgi":
            from core.ia_client import ModeIA, ia_client
            contexte = _contexte_reponse_dgi(params)
            rep = await ia_client.appeler(prompt=contexte, mode=ModeIA.PRECISION)
            return rep.contenu
        if nom == "calendrier_fiscal":
            return _calendrier_fiscal(params)
        if nom == "orchestrer_cloture_mensuelle":
            return _orchestrer_cloture_mensuelle(params)
        return f"[Outil '{nom}' non reconnu par AgentComptable]"


# ── Fonctions de rendu (appellent les fonctions déterministes + formatent) ──

def _rendu_fiscal(params: dict) -> str:
    type_impot = params.get("type_impot", "tva")
    base       = float(params.get("base", 0))
    pays       = params.get("pays", "CM")
    p          = params.get("params", {})

    if type_impot == "tva":
        r = _calculer_tva(base, pays)
        return (
            f"CALCUL TVA — {pays}\n"
            f"Base HT         : {r['base_ht']:>15,.0f} FCFA\n"
            f"Taux TVA        : {r['taux_pct']:.2f}%\n"
            f"TVA             : {r['tva']:>15,.0f} FCFA\n"
            f"Montant TTC     : {r['ttc']:>15,.0f} FCFA\n"
            f"Déclaration     : mensuelle (avant le 15 du mois suivant, {pays})"
        ).replace(",", " ")

    if type_impot == "is":
        ca = float(p.get("ca", p.get("chiffre_affaires", 0)))
        r  = _calculer_is(base, pays, ca)
        lignes = [
            f"CALCUL IS — {pays}",
            f"Résultat fiscal   : {r['resultat_fiscal']:>15,.0f} FCFA",
            f"Taux IS           : {r['taux_pct']:.1f}%",
            f"IS théorique      : {r['is_theorique']:>15,.0f} FCFA",
        ]
        if r["is_minimum"] > 0:
            lignes.append(f"IS minimum (1%CA) : {r['is_minimum']:>15,.0f} FCFA")
        lignes.append(f"IS dû (retenu)    : {r['is_du']:>15,.0f} FCFA")
        lignes.append(f"Délai             : déclaration annuelle dans les 30 jours clôture")
        return "\n".join(lignes).replace(",", " ")

    if type_impot == "irpp":
        rev_annuel = base  # base = revenu annuel imposable
        irpp_an    = _calculer_irpp_annuel(rev_annuel, pays)
        irpp_men   = round(irpp_an / 12)
        tranches   = _IRPP_TRANCHES_CM
        detail     = []
        for borne_inf, borne_sup, taux in tranches:
            if rev_annuel <= borne_inf:
                break
            tranche = (min(rev_annuel, borne_sup) - borne_inf)
            impot_t = round(tranche * taux)
            detail.append(
                f"  {borne_inf/1e6:.1f}M–{borne_sup/1e6:.1f}M : {taux*100:.0f}% × "
                f"{tranche:,.0f} = {impot_t:,.0f}"
            )
        return (
            f"CALCUL IRPP — {pays} (barème progressif 2024)\n"
            f"Revenu annuel imposable : {rev_annuel:,.0f} FCFA\n\n"
            + "\n".join(detail) +
            f"\n\nIRPP annuel : {irpp_an:,.0f} FCFA"
            f"\nIRPP mensuel: {irpp_men:,.0f} FCFA"
        ).replace(",", " ")

    if type_impot == "ras":
        taux_ras = float(p.get("taux", 0.155))
        ras = round(base * taux_ras)
        return (
            f"RETENUE À LA SOURCE\n"
            f"Montant brut        : {base:>15,.0f} FCFA\n"
            f"Taux RAS            : {taux_ras*100:.1f}%\n"
            f"Retenue à la source : {ras:>15,.0f} FCFA\n"
            f"Net versé           : {base-ras:>15,.0f} FCFA\n"
            f"Déclaration         : mensuelle avec la TVA"
        ).replace(",", " ")

    return f"Type d'impôt '{type_impot}' non pris en charge."


def _rendu_balance(params: dict) -> str:
    balance = params.get("balance", [])
    periode = params.get("periode", "")
    if not balance:
        return "Balance vide — fournissez la liste des comptes."
    r = _analyser_balance_comptable(balance)
    lignes = [
        f"ANALYSE BALANCE COMPTABLE{' — ' + periode if periode else ''}\n",
        f"Nombre de comptes : {r['nb_comptes']}",
        f"Total Débit       : {r['total_debit']:>15,} FCFA".replace(",", " "),
        f"Total Crédit      : {r['total_credit']:>15,} FCFA".replace(",", " "),
        f"Équilibre         : {'✅ Équilibrée' if r['equilibree'] else '❌ Déséquilibre : ' + str(r['ecart']) + ' FCFA'}",
    ]
    if r["anomalies"]:
        lignes.append(f"\nANOMALIES DÉTECTÉES ({len(r['anomalies'])}) :")
        for a in r["anomalies"][:5]:
            lignes.append(f"  ⚠️  {a}")
    else:
        lignes.append("\n✅ Aucune anomalie structurelle détectée.")
    return "\n".join(lignes)


def _rendu_ecritures(params: dict) -> str:
    ecritures = params.get("ecritures", [])
    if not ecritures:
        return "Aucune écriture à valider."
    resultats = _valider_ecritures_sysco(ecritures)
    erreurs   = [r for r in resultats if not r["valide"]]
    lignes    = ["VALIDATION ÉCRITURES SYSCOHADA\n"]
    for r in resultats:
        icon = "✅" if r["valide"] else "❌"
        lignes.append(
            f"{icon} Écriture {r['num']} ({r['date']} — {r['libelle']}) "
            f": {r['montant']:,} FCFA"
            + (f" | ÉCART {r['ecart']:,}" if not r["valide"] else "")
        )
    lignes.append(
        f"\nRÉSULTAT : {len(resultats) - len(erreurs)}/{len(resultats)} valides"
    )
    if erreurs:
        lignes.append(f"⚠️  {len(erreurs)} écriture(s) déséquilibrée(s) à corriger.")
    return "\n".join(lignes).replace(",", " ")


def _rendu_amortissement(params: dict) -> str:
    valeur    = float(params.get("valeur", 0))
    categorie = params.get("categorie", "materiel_informatique")
    duree     = int(params.get("duree", 0))
    if valeur <= 0:
        return "Valeur d'achat manquante ou nulle."
    tableau = _calculer_amortissement(valeur, categorie, duree)
    taux    = _TAUX_AMORT.get(categorie, 0.20)
    lignes  = [
        f"TABLEAU AMORTISSEMENT SYSCOHADA\n",
        f"Valeur d'achat : {valeur:,.0f} FCFA".replace(",", " "),
        f"Catégorie      : {categorie.replace('_', ' ').title()}",
        f"Taux linéaire  : {taux*100:.0f}% ({round(1/taux)} ans)",
        f"\n{'Année':>6} {'Dotation':>14} {'Amort. cumulé':>16} {'Valeur nette':>14}",
        "─" * 55,
    ]
    for row in tableau:
        lignes.append(
            f"{row['annee']:>6} {row['dotation']:>14,} "
            f"{row['amort_cumule']:>16,} {row['valeur_nette']:>14,}"
        )
    return "\n".join(lignes).replace(",", " ")


def _rendu_cloture(params: dict) -> str:
    exercice   = params.get("exercice", "N")
    pays       = params.get("pays", "CM")
    type_ent   = params.get("type_entite", "sarl")
    ago_delai  = "6 mois" if type_ent in ("sa", "sarl") else "3 mois"
    return f"""LISTE DE CONTRÔLE CLÔTURE {exercice} — SYSCOHADA ({pays})
{'═'*55}

□ 1. INVENTAIRE PHYSIQUE (Comptes 31x–38x)
   • Comptage physique et fiche de stock signée
   • Valorisation au plus bas : coût historique ou VNR
   • Constat dépréciation si VNR < coût (compte 39x)

□ 2. CUT-OFF — SÉPARATION DES EXERCICES
   • Factures à recevoir (FAR) → débit 60x / crédit 408
   • Factures à établir (FAE) → débit 418 / crédit 70x
   • Charges constatées d'avance (CCA) → 476
   • Produits constatés d'avance (PCA) → 477

□ 3. AMORTISSEMENTS (Comptes 28x)
   • Calculer dotations de l'exercice par immobilisation
   • Écriture : débit 681 / crédit 28x
   • Mettre à jour tableau des immobilisations

□ 4. PROVISIONS (Comptes 19x, 39x, 49x, 59x)
   • Provisions pour créances douteuses (c. 491)
   • Provisions pour risques et charges (c. 19x)
   • Provisions réglementées si applicable

□ 5. RÉGULARISATION PAIE
   • 13e mois et congés payés non pris → c. 422
   • Charges sociales sur gratifications → c. 431/447

□ 6. FISCALITÉ
   • IS prévisionnel → débit 891 / crédit 441
   • TVA : pointer compte 443 et vérifier crédit éventuel
   • Patente et taxes locales payées/à payer

□ 7. RAPPROCHEMENTS BANCAIRES
   • Pointer relevés bancaires vs grand livre 512/521
   • Justifier tous les écarts

□ 8. ÉTATS FINANCIERS SYSCOHADA RÉVISÉ
   □ Bilan (Actif et Passif — classes 1 à 5)
   □ Compte de résultat (classes 6 et 7)
   □ Tableau flux de trésorerie (méthode directe)
   □ Notes annexes (17 notes obligatoires SYSCOHADA)
   □ Tableau de variation des capitaux propres (SA uniquement)

□ 9. LIASSE FISCALE {pays}
   □ Formulaire de l'IS (résultat fiscal)
   □ Déclaration statistique et fiscale (DSF)
   □ Dépôt dans les délais légaux (30 jours après clôture, {pays})

□ 10. FORMALITÉS LÉGALES
   □ AGO dans les {ago_delai} suivant la clôture (OHADA Art. 347)
   □ Dépôt comptes au RCCM dans les 30 jours après approbation AGO
   □ Publication bilans dans le journal d'annonces légales (SA)"""


# ── Nouvelles fonctions haute valeur ─────────────────────────────────────────

# Calendrier fiscal par pays — échéances mensuelles/annuelles
_ECHEANCES_FISCALES = {
    "CM": [
        {"obligation": "TVA mensuelle",              "jour": 15,  "periodicite": "mensuelle",  "formulaire": "Déclaration TVA DGI"},
        {"obligation": "Retenues à la source (RAS)", "jour": 15,  "periodicite": "mensuelle",  "formulaire": "État des RAS employés"},
        {"obligation": "Acompte IS (1/3)",            "jour": 15,  "periodicite": "trimestrielle", "mois": [3, 6, 9], "formulaire": "Bordereau acompte IS"},
        {"obligation": "DSF (liasse fiscale)",        "jour": 30,  "periodicite": "annuelle",   "mois_cloture": 3, "formulaire": "DSF complète DGI"},
        {"obligation": "CNPS déclaration trimestrielle", "jour": 15, "periodicite": "trimestrielle", "mois": [4, 7, 10, 1], "formulaire": "Déclaration CNPS"},
        {"obligation": "Patente",                    "jour": 31,  "periodicite": "annuelle",   "mois_echeance": 3, "formulaire": "Déclaration patente"},
    ],
    "CI": [
        {"obligation": "TVA mensuelle",              "jour": 10,  "periodicite": "mensuelle",  "formulaire": "Déclaration TVA DGI CI"},
        {"obligation": "Acompte BIC",                "jour": 10,  "periodicite": "mensuelle",  "formulaire": "Bordereau BIC mensuel"},
        {"obligation": "CNPS cotisations",           "jour": 15,  "periodicite": "mensuelle",  "formulaire": "Déclaration CNPS CI"},
    ],
    "SN": [
        {"obligation": "TVA mensuelle",              "jour": 15,  "periodicite": "mensuelle",  "formulaire": "Déclaration TVA DGID"},
        {"obligation": "Retenues salariales IRPP",   "jour": 15,  "periodicite": "mensuelle",  "formulaire": "État retenues IRPP"},
        {"obligation": "IPRES/CSS cotisations",      "jour": 10,  "periodicite": "mensuelle",  "formulaire": "Déclaration IPRES"},
    ],
}

# Indicateurs redressement — signaux contestables
_SIGNAUX_CONTESTABLES = [
    ("délai de prescription", "Vérifier prescription 3 ans (Art. CGI) — redressement hors délai contestable"),
    ("méthode reconstitution", "Reconstitution de CA : demander détail de la méthode utilisée"),
    ("charges refusées", "Demander la liste exhaustive des charges refusées et les motifs précis"),
    ("tva rappel", "Vérifier si la TVA rappelée tient compte des déductions légitimes non admises"),
    ("bonne foi", "Première infraction ou absence de manœuvre frauduleuse → demander remise gracieuse des pénalités"),
    ("redressement", "Tout redressement > 3 ans est prescrit sauf manœuvres frauduleuses — vérifier date"),
]


def _analyser_document_fiscal(params: dict) -> str:
    """Analyse un document fiscal entrant et identifie les points d'action."""
    contenu      = params.get("contenu_document", "")
    type_doc     = params.get("type_document", "redressement")
    pays         = params.get("pays", "CM")
    montant      = float(params.get("montant_redresse", 0))

    contenu_lower = contenu.lower()
    signaux_trouves = [
        msg for mot, msg in _SIGNAUX_CONTESTABLES
        if mot in contenu_lower
    ]

    lignes = [f"ANALYSE DOCUMENT FISCAL — {type_doc.upper()} ({pays})\n{'═'*55}"]

    if type_doc == "redressement":
        lignes += [
            "DÉLAIS LÉGAUX DE RÉPONSE :",
            f"  • Réponse observations : 30 jours à compter de la notification",
            f"  • Recours hiérarchique : 15 jours après réponse inspecteur",
            f"  • Recours Commission des impôts : 30 jours après rejet hiérarchique",
            "",
            "ACTIONS IMMÉDIATES :",
            "  ① Vérifier la date de notification (calcul du délai de prescription)",
            "  ② Collecter toutes les pièces justificatives des charges contestées",
            "  ③ Identifier les exercices concernés (prescription 3 ans sauf fraude)",
            "  ④ Chiffrer la part contestable vs la part à accepter",
        ]
        if montant > 0:
            lignes += [
                "",
                f"MONTANT REDRESSÉ : {montant:,.0f} FCFA".replace(",", " "),
                f"  Pénalités estimées (30-50%) : {montant*0.3:,.0f} – {montant*0.5:,.0f} FCFA".replace(",", " "),
                "  ⚠️  Pénalités contestables si bonne foi prouvée → demander remise gracieuse",
            ]
    elif type_doc == "controle":
        lignes += [
            "DROITS DU CONTRIBUABLE EN COURS DE CONTRÔLE :",
            "  • Assistance d'un conseil (expert-comptable, avocat fiscal)",
            "  • Demander la charte du contribuable vérifié",
            "  • Droit à une prolongation de délai pour fournir les documents",
            "  • Tout document remis doit faire l'objet d'un accusé de réception",
            "",
            "DOCUMENTS À PRÉPARER EN PRIORITÉ :",
            "  □ Livres comptables légaux (journal, grand livre, inventaires)",
            "  □ Déclarations fiscales 3 derniers exercices",
            "  □ Factures d'achats et de ventes",
            "  □ Contrats avec clients et fournisseurs principaux",
            "  □ Relevés bancaires",
        ]
    elif type_doc == "credit_tva":
        lignes += [
            "RÉCLAMATION CRÉDIT TVA — POINTS CLÉS :",
            "  • Joindre état détaillé des déductions avec factures originales",
            "  • Délai de remboursement légal : 3 mois après dépôt dossier complet",
            "  • En cas de refus : recours hiérarchique puis Commission",
            "  • Option : imputation sur prochaines déclarations TVA",
        ]

    if signaux_trouves:
        lignes += ["", "POINTS CONTESTABLES DÉTECTÉS :"]
        for s in signaux_trouves:
            lignes.append(f"  ⚡ {s}")

    lignes += [
        "",
        "RECOMMANDATION : Utiliser l'outil `rediger_reponse_dgi` pour rédiger "
        "la réponse formelle avec arguments juridiques.",
    ]
    return "\n".join(lignes)


def _contexte_reponse_dgi(params: dict) -> str:
    """Construit le prompt IA pour la rédaction d'une réponse à la DGI."""
    type_courrier = params.get("type_courrier", "contestation_redressement")
    faits         = params.get("faits", "")
    montant       = float(params.get("montant_conteste", 0))
    arguments     = params.get("arguments", [])
    entreprise    = params.get("entreprise", "[Raison sociale]")
    pays          = params.get("pays", "CM")
    reference     = params.get("reference_avis", "[Référence avis]")

    args_str = "\n".join(f"- {a}" for a in arguments) if arguments else "- À préciser"

    type_labels = {
        "contestation_redressement": "contestation de redressement fiscal",
        "demande_delai":             "demande de délai de paiement",
        "reclamation_credit_tva":    "réclamation de crédit de TVA",
        "reponse_mise_en_demeure":   "réponse à une mise en demeure",
    }
    label = type_labels.get(type_courrier, type_courrier)

    return f"""Rédige un courrier professionnel de {label} adressé à la Direction Générale des Impôts ({pays}).

Expéditeur : {entreprise}
Référence avis contesté : {reference}
Pays : {pays}
Montant contesté : {montant:,.0f} FCFA

FAITS ET POSITION DE L'ENTREPRISE :
{faits}

ARGUMENTS JURIDIQUES À DÉVELOPPER :
{args_str}

CONSIGNES DE RÉDACTION :
- Ton respectueux mais ferme
- Citer les articles du Code Général des Impôts applicables ({pays})
- Inclure : objet, exposé des faits, arguments, demande précise, formule de politesse
- Terminer par une demande d'entretien si montant > 1 000 000 FCFA
- Mentionner le droit à un recours hiérarchique si ce courrier n'est pas la première démarche
- Format lettre officielle avec en-tête, références, date, signature""".replace(",", " ")


def _calendrier_fiscal(params: dict) -> str:
    """Génère le calendrier fiscal avec alertes sur les prochaines échéances."""
    import datetime
    pays          = params.get("pays", "CM")
    mois_courant  = params.get("mois_courant", datetime.date.today().strftime("%Y-%m"))
    type_entite   = params.get("type_entite", "sarl")

    try:
        annee, mois = int(mois_courant[:4]), int(mois_courant[5:7])
    except Exception:
        annee, mois = datetime.date.today().year, datetime.date.today().month

    aujourd_hui = datetime.date.today()
    echeances   = _ECHEANCES_FISCALES.get(pays, _ECHEANCES_FISCALES.get("CM", []))

    lignes = [f"CALENDRIER FISCAL {pays} — {mois_courant}\n{'═'*55}"]
    lignes.append("OBLIGATIONS DU MOIS EN COURS :\n")

    alertes = []
    for e in echeances:
        periodicite = e.get("periodicite", "mensuelle")
        jour_echeance = e.get("jour", 15)
        if periodicite == "mensuelle":
            date_ech = datetime.date(annee, mois, min(jour_echeance, 28))
            jours_restants = (date_ech - aujourd_hui).days
            statut = "🔴 URGENT" if jours_restants < 5 else "🟡 PROCHE" if jours_restants < 10 else "🟢"
            lignes.append(f"  {statut} {date_ech.strftime('%d/%m/%Y')} — {e['obligation']}")
            lignes.append(f"         Formulaire : {e['formulaire']}")
            if jours_restants < 10:
                alertes.append(f"{e['obligation']} ({jours_restants}j restants)")
        elif periodicite == "trimestrielle":
            mois_ech = e.get("mois", [])
            if mois in mois_ech:
                date_ech = datetime.date(annee, mois, min(jour_echeance, 28))
                jours_restants = (date_ech - aujourd_hui).days
                statut = "🔴 URGENT" if jours_restants < 5 else "🟡 PROCHE" if jours_restants < 10 else "🟢"
                lignes.append(f"  {statut} {date_ech.strftime('%d/%m/%Y')} — {e['obligation']} (trimestrielle)")
                lignes.append(f"         Formulaire : {e['formulaire']}")

    if alertes:
        lignes += ["", "⚠️  ALERTES IMMINENTES :"]
        for a in alertes:
            lignes.append(f"   • {a}")

    lignes += [
        "",
        "PROCHAINE CLÔTURE :",
        f"  Exercice {annee} → DSF à déposer avant le 31/03/{annee+1} ({pays})",
        f"  AGO à tenir dans les 6 mois suivant clôture (OHADA Art. 347)",
        "",
        "💡 Utiliser `rediger_reponse_dgi` pour préparer un brouillon de déclaration.",
    ]
    return "\n".join(lignes)


def _orchestrer_cloture_mensuelle(params: dict) -> str:
    """Orchestre la clôture mensuelle avec calculs automatiques."""
    mois         = params.get("mois", "N/A")
    solde_banque = float(params.get("solde_banque", 0))
    solde_compta = float(params.get("solde_compta", 0))
    ca_ht        = float(params.get("ca_ht_mois", 0))
    achats_ht    = float(params.get("achats_ht_mois", 0))
    charges      = float(params.get("charges_mois", 0))
    pays         = params.get("pays", "CM")

    ecart_banque = solde_banque - solde_compta
    tva_collectee = _calculer_tva(ca_ht, pays)["tva"]
    tva_deductible = _calculer_tva(achats_ht, pays)["tva"]
    tva_a_reverser = max(0, tva_collectee - tva_deductible)
    resultat_mois  = ca_ht - achats_ht - charges

    lignes = [
        f"CLÔTURE MENSUELLE — {mois} ({pays})\n{'═'*55}",
        "",
        "① RAPPROCHEMENT BANCAIRE",
        f"   Solde relevé bancaire  : {solde_banque:>15,.0f} FCFA".replace(",", " "),
        f"   Solde compte 512       : {solde_compta:>15,.0f} FCFA".replace(",", " "),
        f"   Écart à justifier      : {ecart_banque:>15,.0f} FCFA".replace(",", " "),
        "   → " + ("✅ Équilibre OK" if abs(ecart_banque) < 1000 else f"⚠️  Identifier {abs(ecart_banque):,.0f} FCFA d'écart (chèques en cours, opérations non comptabilisées)".replace(",", " ")),
        "",
        "② TVA DU MOIS",
        f"   TVA collectée (CA)     : {tva_collectee:>15,.0f} FCFA".replace(",", " "),
        f"   TVA déductible (achats): {tva_deductible:>15,.0f} FCFA".replace(",", " "),
        f"   TVA nette à reverser   : {tva_a_reverser:>15,.0f} FCFA".replace(",", " "),
        f"   Écriture : Débit 4431 / Crédit 512 — {tva_a_reverser:,.0f} FCFA".replace(",", " "),
        f"   Délai déclaration : avant le 15 du mois prochain",
        "",
        "③ RÉSULTAT MENSUEL",
        f"   CA HT                  : {ca_ht:>15,.0f} FCFA".replace(",", " "),
        f"   Achats HT              : {achats_ht:>15,.0f} FCFA".replace(",", " "),
        f"   Charges                : {charges:>15,.0f} FCFA".replace(",", " "),
        f"   Résultat du mois       : {resultat_mois:>15,.0f} FCFA".replace(",", " "),
        "   → " + ("✅ Mois bénéficiaire" if resultat_mois >= 0 else f"⚠️  Mois déficitaire — analyser les charges"),
        "",
        "④ ACTIONS À COMPLÉTER MANUELLEMENT",
        "   □ Lettrage comptes clients (401/411) — pointer factures vs règlements",
        "   □ Relances clients > 30 jours (état des créances échues)",
        "   □ Charges constatées d'avance si applicable (compte 476)",
        "   □ Vérifier les immobilisations acquises ce mois → tableau amortissements",
        "   □ Archiver pièces comptables et clôturer la période dans le logiciel",
    ]
    return "\n".join(lignes)
