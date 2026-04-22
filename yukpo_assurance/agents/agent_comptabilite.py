"""Agent Comptabilité & Finance — PCSA complet, analytique, fiscalité, trésorerie, clôtures."""
from __future__ import annotations
import json, logging
from datetime import date
from core.agent_orchestrateur import TypeAgent
from core.workflow_engine import coder_ecriture_comptable
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.comptabilite")

# ─── Plan Comptable Spécifique Assurances (PCSA) ────────────────────────────
_COMPTES_PCSA = {
    "101": "Capital social", "106": "Réserves", "120": "Résultat exercice",
    "300": "Provisions pour sinistres à payer (PSAP)",
    "310": "Provisions mathématiques vie",
    "320": "Provisions pour risques en cours (PRC)",
    "330": "Provision pour égalisation",
    "400": "Assurés — primes à recevoir",
    "401": "Réassureurs — comptes courants",
    "410": "Fournisseurs", "441": "Impôts sur le résultat",
    "445": "TVA collectée / déductible",
    "461": "Débiteurs divers", "462": "Créances douteuses",
    "512": "Banques", "514": "Mobile Money", "530": "Caisse",
    "600": "Sinistres et pertes", "605": "Frais d'expertise",
    "616": "Primes cédées réassurance", "630": "Commissions apporteurs",
    "640": "Charges de personnel", "650": "Impôts et taxes",
    "660": "Charges financières", "680": "Dotations provisions techniques",
    "700": "Primes acquises", "701": "Primes émises brutes",
    "705": "Primes acceptées réassurance",
    "730": "Produits des placements", "780": "Reprises provisions techniques",
}

# Taux amortissement par catégorie d'actif
_TAUX_AMORTISSEMENT = {
    "mobilier_bureau": 0.20,       # 5 ans linéaire
    "materiel_informatique": 0.33, # 3 ans dégressif
    "vehicule": 0.25,              # 4 ans
    "logiciel": 0.33,              # 3 ans
    "immeuble_exploitation": 0.04, # 25 ans
    "agencement": 0.10,            # 10 ans
}

# Taux de TVA par pays (CIMA)
_TVA_PAYS = {
    "CM": 0.1925, "CI": 0.18, "SN": 0.18, "GA": 0.18,
    "CG": 0.18,   "TG": 0.18, "BJ": 0.18, "BF": 0.18,
    "ML": 0.18,   "NE": 0.19, "GN": 0.18,
}


def _calculer_amortissement(valeur_achat: float, categorie: str, annees: int) -> dict:
    taux = _TAUX_AMORTISSEMENT.get(categorie, 0.20)
    valeur_nette = valeur_achat
    tableau = []
    for an in range(1, annees + 1):
        dot = min(round(valeur_achat * taux), valeur_nette)
        valeur_nette = max(0, valeur_nette - dot)
        tableau.append({"annee": an, "dotation": dot, "valeur_nette": valeur_nette})
        if valeur_nette == 0:
            break
    return {"valeur_achat": valeur_achat, "categorie": categorie, "taux_pct": taux * 100, "tableau": tableau}


def _calculer_provision_creance_douteuse(montant: float, anciennete_jours: int) -> dict:
    """Provision créances douteuses par tranche d'ancienneté."""
    if anciennete_jours < 90:
        taux, libelle = 0.0, "Pas de provision — < 90 jours"
    elif anciennete_jours < 180:
        taux, libelle = 0.25, "Provision 25% — 90 à 180 jours"
    elif anciennete_jours < 360:
        taux, libelle = 0.50, "Provision 50% — 180 à 360 jours"
    else:
        taux, libelle = 1.00, "Provision 100% — > 360 jours (créance irrécouvrable)"
    return {"montant_creance": montant, "anciennete_jours": anciennete_jours,
            "taux_provision_pct": taux * 100, "montant_provision": round(montant * taux),
            "libelle": libelle}


class AgentComptabilite(BaseAgent):
    type_agent = TypeAgent.COMPTABILITE

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Comptabilité & Finance de YukpoAssurance, expert en comptabilité des assurances CIMA.

DOMAINES COUVERTS :
1. ÉCRITURES & JOURNAUX : PCSA intégral, écritures automatiques ou forcées, audit trail
2. RAPPROCHEMENT : bancaire, Mobile Money, inter-compagnies, réassurance
3. PROVISIONS TECHNIQUES : PSAP dossier/dossier, PRC, PM vie, égalisation (Art. 334-339 CIMA)
4. COMPTABILITÉ ANALYTIQUE : par branche, département, produit, apporteur
5. BUDGET & CONTRÔLE DE GESTION : saisie budget, suivi mensuel, analyse écarts
6. IMMOBILISATIONS : achats, amortissements, cessions, inventaire
7. CRÉANCES & DETTES : suivi, relances, provisions créances douteuses, dépréciation
8. FISCALITÉ : TVA mensuelle, IS annuel, CMF, IRCM, déclarations CIMAS
9. TRÉSORERIE : état journalier, prévisions 13 semaines, gestion liquidité
10. CLÔTURES : mensuelle, trimestrielle, annuelle — états CIMA, liasses fiscales
11. REPORTING DIRECTION : tableaux de bord financiers, ratios technique/financier

RÈGLES ABSOLUES :
- Toute écriture suit le PCSA (Plan Comptable Spécifique Assurances)
- Calculs déterministes : amortissements, provisions, taxes, ratios
- IA uniquement pour analyses narratives, recommandations, rédaction rapports
- Écritures > 10M FCFA → double signature obligatoire
- Clôture mensuelle → validation DAF obligatoire
- Déclarations fiscales → validation DG avant dépôt"""

    def _definir_outils(self) -> list[dict]:
        return [
            # ── Écritures ──
            {
                "name": "passer_ecriture",
                "description": "Passe une écriture comptable PCSA (déterministe standard ou forcée)",
                "input_schema": {"type": "object", "properties": {
                    "type_operation": {"type": "string", "description": "encaissement_prime, paiement_sinistre, commission_apporteur, etc."},
                    "montant":        {"type": "number"},
                    "reference":      {"type": "string"},
                    "libelle":        {"type": "string"},
                    "date_operation": {"type": "string"},
                    "compte_debit":   {"type": "string"},
                    "compte_credit":  {"type": "string"},
                    "branche":        {"type": "string"},
                    "departement":    {"type": "string"},
                }, "required": ["type_operation", "montant", "reference"]},
            },
            {
                "name": "passer_ecriture_ajustement",
                "description": "Écriture d'ajustement : charges à payer, produits à recevoir, régularisations de fin de période",
                "input_schema": {"type": "object", "properties": {
                    "type_ajustement": {"type": "string", "enum": [
                        "charges_a_payer", "produits_a_recevoir", "charges_constatees_avance",
                        "produits_constates_avance", "variation_change", "actualisation_provision",
                    ]},
                    "montant":  {"type": "number"},
                    "libelle":  {"type": "string"},
                    "periode":  {"type": "string"},
                }, "required": ["type_ajustement", "montant", "periode"]},
            },
            # ── Rapprochement ──
            {
                "name": "rapprochement_bancaire",
                "description": "Rapprochement relevé bancaire/Mobile Money vs grand livre PCSA",
                "input_schema": {"type": "object", "properties": {
                    "compte_banque":  {"type": "string"},
                    "date_debut":     {"type": "string"},
                    "date_fin":       {"type": "string"},
                    "releve_base64":  {"type": "string"},
                }, "required": ["compte_banque", "date_debut", "date_fin"]},
            },
            # ── Provisions techniques ──
            {
                "name": "calculer_provisions_techniques",
                "description": "Calcule et comptabilise les provisions techniques réglementaires CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "type_provision": {"type": "string", "enum": ["psap", "prc", "pm_vie", "provision_egalisation"]},
                    "periode":        {"type": "string"},
                    "branche":        {"type": "string", "enum": ["auto", "mrh", "transport", "rc", "vie", "tous"]},
                    "passer_ecriture": {"type": "boolean", "description": "Passer l'écriture PCSA automatiquement"},
                }, "required": ["type_provision", "periode"]},
            },
            # ── Analytique ──
            {
                "name": "comptabilite_analytique",
                "description": "Résultat technique analytique par branche / département / apporteur / produit",
                "input_schema": {"type": "object", "properties": {
                    "axe":      {"type": "string", "enum": ["branche", "departement", "apporteur", "produit", "region"]},
                    "periode":  {"type": "string"},
                    "annee":    {"type": "integer"},
                    "filtre":   {"type": "string", "description": "Valeur de l'axe ex: 'rc_auto' pour branche"},
                }, "required": ["axe", "annee"]},
            },
            # ── Budget & contrôle ──
            {
                "name": "gerer_budget",
                "description": "Saisie budget annuel, révision, et suivi mensuel par poste/département",
                "input_schema": {"type": "object", "properties": {
                    "action":       {"type": "string", "enum": ["saisir", "reviser", "consulter", "analyser_ecarts"]},
                    "annee":        {"type": "integer"},
                    "departement":  {"type": "string"},
                    "postes":       {"type": "object", "description": "Montants budgétés par poste"},
                    "periode":      {"type": "string"},
                    "realise":      {"type": "object"},
                }, "required": ["action", "annee"]},
            },
            # ── Immobilisations ──
            {
                "name": "gerer_immobilisation",
                "description": "Gestion des actifs immobilisés : acquisition, amortissement, cession, inventaire",
                "input_schema": {"type": "object", "properties": {
                    "action":       {"type": "string", "enum": ["acquisition", "calculer_amortissement", "cession", "inventaire", "revalorisation"]},
                    "libelle":      {"type": "string"},
                    "categorie":    {"type": "string", "enum": list(_TAUX_AMORTISSEMENT.keys())},
                    "valeur_achat": {"type": "number"},
                    "date_achat":   {"type": "string"},
                    "duree_ans":    {"type": "integer"},
                    "valeur_cession": {"type": "number"},
                    "immobilisation_id": {"type": "string"},
                }, "required": ["action"]},
            },
            # ── Créances & dettes ──
            {
                "name": "gerer_creances",
                "description": "Suivi créances clients/assurés : relances, provisions créances douteuses, irrécouvrables",
                "input_schema": {"type": "object", "properties": {
                    "action":       {"type": "string", "enum": ["lister_echeances", "relancer", "provisionner", "passer_en_perte", "encaisser"]},
                    "client_id":    {"type": "string"},
                    "montant":      {"type": "number"},
                    "anciennete_jours": {"type": "integer"},
                    "reference":    {"type": "string"},
                }, "required": ["action"]},
            },
            # ── Fiscalité ──
            {
                "name": "gerer_fiscalite",
                "description": "Calcul et déclaration TVA mensuelle, IS annuel, CMF, IRCM, taxes CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "type_taxe":    {"type": "string", "enum": ["tva", "is", "cmf", "ircm", "taxe_assurance", "declaration_cima"]},
                    "periode":      {"type": "string"},
                    "annee":        {"type": "integer"},
                    "pays":         {"type": "string", "description": "Code ISO pays ex: CM"},
                    "chiffre_affaires": {"type": "number"},
                    "resultat_imposable": {"type": "number"},
                    "tva_collectee": {"type": "number"},
                    "tva_deductible": {"type": "number"},
                }, "required": ["type_taxe", "annee"]},
            },
            # ── Trésorerie ──
            {
                "name": "gerer_tresorerie",
                "description": "État journalier, budget prévisionnel 13 semaines, alertes liquidité",
                "input_schema": {"type": "object", "properties": {
                    "action":   {"type": "string", "enum": ["etat_journalier", "prevision_13_semaines", "alertes_liquidite", "optimiser_placement"]},
                    "date":     {"type": "string"},
                    "horizon_jours": {"type": "integer"},
                }, "required": ["action"]},
            },
            # ── États financiers ──
            {
                "name": "generer_etat_financier",
                "description": "Génère compte de résultat technique, bilan, annexes CIMA",
                "input_schema": {"type": "object", "properties": {
                    "type_etat": {"type": "string", "enum": ["compte_resultat", "bilan", "tresorerie", "provisions", "annexe_cima", "liasse_fiscale"]},
                    "periode":   {"type": "string"},
                    "annee":     {"type": "integer"},
                    "branche":   {"type": "string"},
                }, "required": ["type_etat", "annee"]},
            },
            # ── Ratios ──
            {
                "name": "calculer_ratios_financiers",
                "description": "Calcule les ratios techniques et financiers (combined ratio, ROE, ROA, etc.) (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "primes_acquises":    {"type": "number"},
                    "sinistres_survenus": {"type": "number"},
                    "frais_gestion":      {"type": "number"},
                    "commissions":        {"type": "number"},
                    "produits_placement": {"type": "number"},
                    "fonds_propres":      {"type": "number"},
                    "total_actif":        {"type": "number"},
                }, "required": ["primes_acquises", "sinistres_survenus"]},
            },
            # ── Clôture ──
            {
                "name": "lancer_cloture",
                "description": "Lance la clôture comptable (mensuelle/trimestrielle/annuelle) — validation DAF requise",
                "input_schema": {"type": "object", "properties": {
                    "type_cloture": {"type": "string", "enum": ["mensuelle", "trimestrielle", "annuelle"]},
                    "periode":      {"type": "string"},
                    "annee":        {"type": "integer"},
                    "checklist":    {"type": "array", "items": {"type": "string"}, "description": "Éléments vérifiés avant clôture"},
                }, "required": ["type_cloture", "annee"]},
            },
            # ── OCR & saisie ──
            {
                "name": "ocr_document_comptable",
                "description": "OCR extraction : factures, relevés, bulletins de paie, quittances",
                "input_schema": {"type": "object", "properties": {
                    "image_base64":  {"type": "string"},
                    "type_document": {"type": "string", "enum": ["facture", "releve_bancaire", "quittance", "bulletin_paie", "recu_mobile_money"]},
                    "comptabiliser_auto": {"type": "boolean"},
                }, "required": ["type_document"]},
            },
            # ── Contrôle interne ──
            {
                "name": "controle_interne",
                "description": "Audit trail des écritures, contrôles de cohérence, rapprochements inter-agents",
                "input_schema": {"type": "object", "properties": {
                    "type_controle": {"type": "string", "enum": [
                        "audit_ecritures", "coherence_provisions", "rapprochement_reassurance",
                        "controle_caisses", "verification_interco",
                    ]},
                    "periode":   {"type": "string"},
                    "branche":   {"type": "string"},
                }, "required": ["type_controle", "periode"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT COMPTABILITÉ — quand demander une information :

1. PÉRIODE COMPTABLE NON PRÉCISÉE
   → "Quelle est la période comptable concernée par cette opération ? (Ex: Exercice 2024, ou Mois 03/2025)"
   type_reponse: texte_libre

2. TYPE D'ÉCRITURE COMPTABLE AMBIGU
   → "Quel type d'écriture comptable souhaitez-vous passer ?"
   type_reponse: choix_multiple  choix: ["Encaissement de prime (client → caisse/banque)", "Règlement sinistre (charge → banque)", "Écriture de provision technique (dotation PSAP/PM)", "Commission apporteur", "Écriture de réassurance (cession / rétrocession)", "Régularisation / OD de clôture", "Saisie manuelle forcée"]

3. COMPTE DE CONTREPARTIE MANQUANT (PCSA)
   → "Quel est le compte de contrepartie pour cette écriture ? (Compte PCSA — ex: 401 Fournisseurs, 411 Clients, 512 Banque)"
   type_reponse: texte_libre

4. TYPE DE CLÔTURE NON DÉFINI
   → "Quel type de clôture comptable souhaitez-vous lancer ?"
   type_reponse: choix_multiple  choix: ["Clôture mensuelle (provisions, régularisations)", "Clôture trimestrielle (états de gestion)", "Clôture annuelle (bilan, liasse CIMA)", "Pré-clôture de vérification (sans blocage des comptes)"]

5. RELEVÉ BANCAIRE — PÉRIODE DU RAPPROCHEMENT
   → "Pour quelle banque et quelle période souhaitez-vous effectuer le rapprochement bancaire ?"
   type_reponse: texte_libre

6. MONTANT DE L'ÉCRITURE MANQUANT
   → "Quel est le montant de l'écriture comptable à passer (en FCFA) ?"
   type_reponse: nombre

7. PIÈCE JUSTIFICATIVE RÉFÉRENCÉE
   → "Quelle est la référence de la pièce justificative associée à cette écriture ? (Numéro facture, référence sinistre, numéro quittance, etc.)"
   type_reponse: texte_libre

8. FACTURE FOURNISSEUR À SAISIR (pour imputation automatique via OCR)
   → "Veuillez envoyer la facture fournisseur en photo ou PDF. Je l'analyserai pour extraire automatiquement le montant HT, TVA, TTC et la référence pour l'imputation PCSA."
   type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

9. RELEVÉ BANCAIRE POUR RAPPROCHEMENT (scan du relevé)
   → "Veuillez transmettre le relevé bancaire de la période en format PDF ou photo. Je comparerai les opérations avec les écritures comptables pour identifier les écarts."
   type_reponse: images  nombre_images_max: 3  formats_acceptes: ["pdf", "jpg", "png"]

10. PIÈCES JUSTIFICATIVES MULTIPLES (lot de factures pour traitement en lot)
    → "Transmettez jusqu'à 5 factures ou pièces justificatives à traiter en lot. Chaque document sera analysé par OCR pour extraction automatique des données comptables."
    type_reponse: images  nombre_images_max: 5  formats_acceptes: ["pdf", "jpg", "png"]

PROGRESSION : Période → Type d'opération → Montant → Comptes PCSA → Pièce justificative (scan si disponible). Pour les pièces physiques, privilégier le scan pour extraction OCR automatique vers ORASS/Sage.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "passer_ecriture":
                result = coder_ecriture_comptable(
                    type_operation=params["type_operation"],
                    montant=params["montant"],
                    reference=params["reference"],
                )
                if result.donnees:
                    ecriture = result.donnees.copy()
                    for champ in ("compte_debit", "compte_credit", "libelle"):
                        if params.get(champ):
                            ecriture[champ] = params[champ]
                    if params.get("date_operation"):
                        ecriture["date"] = params["date_operation"]
                    ecriture["branche"]     = params.get("branche", "")
                    ecriture["departement"] = params.get("departement", "")
                    if params["montant"] >= 10_000_000:
                        from core.approval_queue import approval_queue
                        await approval_queue.ajouter({
                            "type": "ecriture_comptable_grande",
                            "ecriture": ecriture,
                            "montant": params["montant"],
                            "user_id": user_id,
                            "execution_id": execution_id,
                        })
                        return f"Écriture > 10M FCFA — soumise pour double signature : {result.message}"
                    from core.orass_connector import orass
                    await orass.passer_ecriture(ecriture)
                    return result.message
                return f"Type '{params['type_operation']}' non standard — saisie manuelle : {result.message}"

            if nom == "passer_ecriture_ajustement":
                type_aj = params["type_ajustement"]
                montant = params["montant"]
                _AJUSTEMENTS = {
                    "charges_a_payer":       ("600", "410", "Charges à payer"),
                    "produits_a_recevoir":   ("400", "700", "Produits à recevoir"),
                    "charges_constatees_avance": ("480", "600", "Charges constatées d'avance"),
                    "produits_constates_avance": ("700", "487", "Produits constatés d'avance"),
                    "variation_change":      ("660", "401", "Perte de change"),
                    "actualisation_provision": ("680", "300", "Actualisation provision"),
                }
                comptes = _AJUSTEMENTS.get(type_aj, ("461", "512", type_aj))
                return json.dumps({
                    "type_ajustement": type_aj,
                    "montant":   montant,
                    "debit":     comptes[0],
                    "credit":    comptes[1],
                    "libelle":   params.get("libelle") or comptes[2],
                    "periode":   params["periode"],
                    "statut":    "À valider avant passage",
                }, ensure_ascii=False)

            if nom == "rapprochement_bancaire":
                transactions_releve = []
                if params.get("releve_base64"):
                    from core.ocr_processor import ocr_processor
                    texte = await ocr_processor.analyser_document(params["releve_base64"], "releve_bancaire")
                    if texte.startswith("["):
                        transactions_releve = json.loads(texte)
                from core.orass_connector import orass
                gl = await orass.get_grand_livre(
                    compte=params["compte_banque"],
                    date_debut=params["date_debut"], date_fin=params["date_fin"],
                )
                solde_gl = sum(e.get("montant", 0) * (1 if e.get("sens") == "debit" else -1) for e in gl)
                non_rappr = [t for t in transactions_releve if not any(
                    abs(e.get("montant", 0) - abs(t.get("montant", 0))) < 1 for e in gl
                )]
                return json.dumps({
                    "compte": params["compte_banque"],
                    "periode": f"{params['date_debut']} → {params['date_fin']}",
                    "nb_ecritures_gl": len(gl),
                    "solde_grand_livre": solde_gl,
                    "nb_non_rapproches": len(non_rappr),
                    "non_rapproches": non_rappr[:10],
                    "statut": "ÉQUILIBRÉ" if len(non_rappr) == 0 else f"{len(non_rappr)} écart(s) à régulariser",
                }, ensure_ascii=False)

            if nom == "calculer_provisions_techniques":
                from core.orass_connector import orass
                type_prov = params["type_provision"]
                donnees = await orass.get_donnees_provisions(
                    periode=params["periode"], branche=params.get("branche", "tous")
                )
                if type_prov == "psap":
                    sins = donnees.get("sinistres_ouverts", [])
                    psap = sum(s.get("montant_estime", 0) for s in sins)
                    res = {"type": "PSAP", "montant": psap, "nb_dossiers": len(sins),
                           "fondement": "Art. 335 CIMA — dossier/dossier"}
                elif type_prov == "prc":
                    primes = donnees.get("primes_emises", 0)
                    jours  = donnees.get("jours_restants_couverture", 180)
                    prc    = round(primes * (jours / 365))
                    res    = {"type": "PRC", "montant": prc, "fondement": "Art. 334-4 CIMA"}
                elif type_prov == "pm_vie":
                    pm    = donnees.get("pm_brutes", 0)
                    res   = {"type": "PM Vie", "montant": pm, "fondement": "Art. 338-1 CIMA prospective"}
                elif type_prov == "provision_egalisation":
                    primes = donnees.get("primes_emises", 0)
                    pe     = round(primes * 0.03)
                    res    = {"type": "Provision Égalisation", "montant": pe, "fondement": "Art. 334-5 CIMA"}
                else:
                    res = {"type": type_prov, "message": "Calcul spécifique requis"}
                if params.get("passer_ecriture") and res.get("montant"):
                    from core.orass_connector import orass as _orass
                    await _orass.passer_ecriture({
                        "compte_debit": "680", "compte_credit": "300",
                        "montant": res["montant"], "libelle": f"Dotation {type_prov} {params['periode']}",
                    })
                    res["ecriture_passee"] = True
                return json.dumps(res, ensure_ascii=False)

            if nom == "comptabilite_analytique":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                data = await orass.get_analytique(
                    axe=params["axe"], annee=params["annee"],
                    periode=params.get("periode"), filtre=params.get("filtre"),
                )
                prompt = f"""Analyse le résultat technique par {params['axe']} pour l'exercice {params['annee']}.
Données : {json.dumps(data, ensure_ascii=False, indent=2)}
Identifie les axes rentables/déficitaires, causes et recommandations."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return json.dumps({"donnees": data, "analyse": rep.contenu}, ensure_ascii=False)

            if nom == "gerer_budget":
                action = params["action"]
                from core.orass_connector import orass
                if action == "saisir":
                    await orass.saisir_budget(annee=params["annee"], departement=params.get("departement"), postes=params.get("postes", {}))
                    return f"Budget {params['annee']} saisi pour {params.get('departement', 'tous')} — {len(params.get('postes', {}))} postes"
                if action == "reviser":
                    await orass.reviser_budget(annee=params["annee"], postes=params.get("postes", {}))
                    return f"Budget {params['annee']} révisé"
                if action == "consulter":
                    data = await orass.get_budget(annee=params["annee"], departement=params.get("departement"))
                    return json.dumps(data, ensure_ascii=False, default=str)
                if action == "analyser_ecarts":
                    budget  = params.get("postes", {})
                    realise = params.get("realise", {})
                    ecarts  = {
                        k: {"budget": budget.get(k, 0), "realise": realise.get(k, 0),
                            "ecart": realise.get(k, 0) - budget.get(k, 0),
                            "ecart_pct": round((realise.get(k, 0) - budget.get(k, 0)) / budget.get(k, 1) * 100, 1)}
                        for k in set(list(budget) + list(realise))
                    }
                    from core.ia_client import ModeIA, ia_client
                    prompt = f"Analyse les écarts budgétaires {params['periode']} :\n{json.dumps(ecarts, indent=2)}\nCommente les écarts > ±10% et recommande des actions."
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                    return json.dumps({"ecarts": ecarts, "analyse": rep.contenu}, ensure_ascii=False)
                return "Action budget non reconnue"

            if nom == "gerer_immobilisation":
                action = params["action"]
                if action == "calculer_amortissement":
                    res = _calculer_amortissement(
                        valeur_achat=params["valeur_achat"],
                        categorie=params.get("categorie", "mobilier_bureau"),
                        annees=params.get("duree_ans", 5),
                    )
                    return json.dumps(res, ensure_ascii=False)
                if action == "acquisition":
                    from core.orass_connector import orass
                    await orass.enregistrer_immobilisation({
                        "libelle": params["libelle"], "categorie": params["categorie"],
                        "valeur_achat": params["valeur_achat"], "date_achat": params.get("date_achat", date.today().isoformat()),
                    })
                    return f"Immobilisation '{params['libelle']}' enregistrée — {params['valeur_achat']:,.0f} FCFA".replace(",", " ")
                if action == "inventaire":
                    from core.orass_connector import orass
                    data = await orass.get_inventaire_immobilisations()
                    return json.dumps(data, ensure_ascii=False, default=str)
                return f"Action immobilisation '{action}' non implémentée"

            if nom == "gerer_creances":
                action = params["action"]
                if action == "provisionner":
                    res = _calculer_provision_creance_douteuse(
                        montant=params["montant"],
                        anciennete_jours=params.get("anciennete_jours", 0),
                    )
                    if res["montant_provision"] >= 10_000_000:
                        from core.approval_queue import approval_queue
                        await approval_queue.ajouter({
                            "type": "provision_creance_douteuse",
                            "montant": res["montant_provision"],
                            "reference": params.get("reference"),
                            "user_id": user_id, "execution_id": execution_id,
                        })
                        return f"Provision créance douteuse soumise pour validation : {json.dumps(res, ensure_ascii=False)}"
                    return json.dumps(res, ensure_ascii=False)
                if action == "lister_echeances":
                    from core.orass_connector import orass
                    data = await orass.get_creances_echues()
                    return json.dumps(data, ensure_ascii=False, default=str)
                if action in ("relancer", "passer_en_perte", "encaisser"):
                    from core.orass_connector import orass
                    await orass.update_creance(
                        client_id=params.get("client_id"), reference=params.get("reference"),
                        action=action, montant=params.get("montant"),
                    )
                    return f"Créance {action} — client {params.get('client_id')}"
                return f"Action créance '{action}' non reconnue"

            if nom == "gerer_fiscalite":
                type_t = params["type_taxe"]
                annee  = params["annee"]
                pays   = params.get("pays", "CM")
                if type_t == "tva":
                    collectee  = params.get("tva_collectee", 0)
                    deductible = params.get("tva_deductible", 0)
                    solde      = collectee - deductible
                    res = {
                        "type": "TVA", "annee": annee, "periode": params.get("periode"),
                        "tva_collectee": collectee, "tva_deductible": deductible,
                        "solde_a_payer": max(0, solde),
                        "credit_tva":   max(0, -solde),
                        "compte_debit":  "445.1", "compte_credit": "512",
                    }
                elif type_t == "is":
                    resultat = params.get("resultat_imposable", 0)
                    is_taux  = {"CM": 0.33, "CI": 0.25, "SN": 0.30}.get(pays, 0.30)
                    is_du    = max(round(resultat * is_taux), 0)
                    res = {"type": "IS", "taux_pct": is_taux * 100, "base_imposable": resultat,
                           "is_du": is_du, "pays": pays}
                elif type_t == "cmf":
                    ca = params.get("chiffre_affaires", 0)
                    cmf_taux = {"CM": 0.005, "CI": 0.005, "SN": 0.003}.get(pays, 0.005)
                    cmf = round(ca * cmf_taux)
                    res = {"type": "CMF (contribution minimale forfaitaire)", "taux_pct": cmf_taux * 100,
                           "base_ca": ca, "montant_cmf": cmf, "pays": pays}
                else:
                    res = {"type": type_t, "message": "Calcul fiscal spécifique — consulter le service fiscal"}
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "declaration_fiscale",
                    "type_taxe": type_t, "annee": annee,
                    "montant": res.get("solde_a_payer") or res.get("is_du") or res.get("montant_cmf", 0),
                    "donnees": res, "user_id": user_id, "execution_id": execution_id,
                })
                return json.dumps(res | {"statut": "Soumis pour validation DG avant dépôt"}, ensure_ascii=False)

            if nom == "gerer_tresorerie":
                action = params["action"]
                from core.orass_connector import orass
                if action == "etat_journalier":
                    data = await orass.get_etat_tresorerie(date=params.get("date", date.today().isoformat()))
                    return json.dumps(data, ensure_ascii=False, default=str)
                if action == "prevision_13_semaines":
                    from core.ia_client import ModeIA, ia_client
                    historique = await orass.get_flux_tresorerie_historique(horizon_jours=90)
                    prompt = f"""Établis le budget de trésorerie prévisionnel sur 13 semaines.
Flux historiques : {json.dumps(historique, ensure_ascii=False)}
Structure : encaissements prévisionnels par semaine, décaissements, solde cumulé, alertes si solde < seuil."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu
                if action == "alertes_liquidite":
                    data = await orass.get_etat_tresorerie(date=date.today().isoformat())
                    solde = data.get("solde_total", 0)
                    seuil = 50_000_000
                    alerte = solde < seuil
                    return json.dumps({
                        "solde_tresorerie": solde, "seuil_alerte": seuil,
                        "alerte": alerte,
                        "message": f"ALERTE : Solde trésorerie {solde:,.0f} FCFA en dessous du seuil {seuil:,.0f} FCFA".replace(",", " ") if alerte else "Trésorerie satisfaisante",
                    }, ensure_ascii=False)
                return f"Action trésorerie '{action}' non reconnue"

            if nom == "generer_etat_financier":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                data = await orass.get_donnees_financieres(
                    type_etat=params["type_etat"], annee=params["annee"],
                    periode=params.get("periode"), branche=params.get("branche"),
                )
                prompt = f"""Génère l'état financier '{params['type_etat']}' pour l'exercice {params['annee']}.
Données : {json.dumps(data, ensure_ascii=False, indent=2)}
Format : tableau PCSA structuré, totaux, ratios clés, commentaire analytique concis."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return rep.contenu

            if nom == "calculer_ratios_financiers":
                primes     = params["primes_acquises"]
                sinistres  = params["sinistres_survenus"]
                frais      = params.get("frais_gestion", 0)
                commissions= params.get("commissions", 0)
                placements = params.get("produits_placement", 0)
                fp         = params.get("fonds_propres", 1)
                actif      = params.get("total_actif", 1)
                loss_ratio = round(sinistres / primes * 100, 1) if primes else 0
                expense_ratio = round((frais + commissions) / primes * 100, 1) if primes else 0
                combined_ratio = loss_ratio + expense_ratio
                resultat_tech  = primes - sinistres - frais - commissions + placements
                return json.dumps({
                    "loss_ratio_pct":       loss_ratio,
                    "expense_ratio_pct":    expense_ratio,
                    "combined_ratio_pct":   combined_ratio,
                    "resultat_technique":   round(resultat_tech),
                    "roe_pct":              round(resultat_tech / fp * 100, 1) if fp else 0,
                    "roa_pct":              round(resultat_tech / actif * 100, 1) if actif else 0,
                    "rentable":             combined_ratio < 100,
                    "commentaire": (
                        "Très rentable — combined < 85%" if combined_ratio < 85 else
                        "Rentable" if combined_ratio < 95 else
                        "Équilibré" if combined_ratio < 100 else
                        f"DÉFICITAIRE — {combined_ratio - 100:.1f}% au-dessus du seuil"
                    ),
                }, ensure_ascii=False)

            if nom == "lancer_cloture":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "cloture_comptable",
                    "type_cloture": params["type_cloture"],
                    "periode": params.get("periode"),
                    "annee": params["annee"],
                    "checklist": params.get("checklist", []),
                    "user_id": user_id, "execution_id": execution_id,
                })
                return f"Clôture {params['type_cloture']} {params.get('periode', params['annee'])} soumise pour validation DAF"

            if nom == "ocr_document_comptable":
                from core.ocr_processor import ocr_processor
                texte = await ocr_processor.analyser_document(
                    params.get("image_base64", ""), params["type_document"],
                )
                if params.get("comptabiliser_auto") and texte:
                    try:
                        doc_data = json.loads(texte)
                        if doc_data.get("montant") and doc_data.get("type"):
                            result = coder_ecriture_comptable(
                                type_operation=doc_data["type"],
                                montant=doc_data["montant"],
                                reference=doc_data.get("numero", "OCR-AUTO"),
                            )
                            return f"OCR extrait + comptabilisé automatiquement : {result.message}\n{texte}"
                    except Exception:
                        pass
                return texte

            if nom == "controle_interne":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                type_ctrl = params["type_controle"]
                data = await orass.get_audit_trail(type_ctrl=type_ctrl, periode=params["periode"], branche=params.get("branche"))
                prompt = f"""Effectue un contrôle interne de type '{type_ctrl}' pour la période {params['periode']}.
Données : {json.dumps(data, ensure_ascii=False, indent=2)}
Identifie : anomalies, erreurs d'imputation, doublons, écarts non justifiés, risques de fraude interne."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return json.dumps({"type_controle": type_ctrl, "periode": params["periode"],
                                   "nb_lignes_analysees": len(data) if isinstance(data, list) else 0,
                                   "rapport": rep.contenu}, ensure_ascii=False)

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentComptabilite] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
