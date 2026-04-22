"""Agent Réassurance & Cessions — traités proportionnels, XS perte, bordereaux."""
from __future__ import annotations
import json, logging
from datetime import date
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.reassurance")

# ─── Barèmes réassurance ─────────────────────────────────────────────────────

# Commission de réassurance selon type de traité (%)
_COMM_REASSURANCE = {
    "quote_part":      20.0,   # 20% commission fixe
    "excedent_plein":  17.5,
    "excess_sinistre": 0.0,    # pas de commission XS sinistre
    "excess_perte":    0.0,
    "catastrophe":     0.0,
    "facultatif":      15.0,
}

# Taux de cession typiques par branche CIMA
_TAUX_CESSION_BRANCHE = {
    "rc_auto":             0.20,   # 20%
    "mrh":                 0.25,
    "transport":           0.35,   # risque élevé
    "rc_pro":              0.30,
    "accident_corporel":   0.15,
    "construction":        0.50,   # DO/TRC — cession majoritaire
    "vie_temporaire":      0.10,
    "vie_emprunteur":      0.25,
    "vie_epargne":         0.05,
}

# Priorités XS sinistre par branche (FCFA)
_PRIORITE_XS = {
    "rc_auto":    15_000_000,
    "mrh":        10_000_000,
    "transport":  20_000_000,
    "construction": 50_000_000,
    "rc_pro":     25_000_000,
}


def _calculer_cession_quote_part(
    prime_brute: float,
    sinistres: float,
    taux_cession: float,
    commission_pct: float,
) -> dict:
    """Calcul d'un traité en quote-part."""
    prime_cedee     = prime_brute * taux_cession
    sinistre_cede   = sinistres  * taux_cession
    commission      = prime_cedee * commission_pct / 100
    solde_cedant    = prime_cedee - sinistre_cede - commission
    return {
        "prime_cedee_fcfa":    round(prime_cedee),
        "sinistre_cede_fcfa":  round(sinistre_cede),
        "commission_fcfa":     round(commission),
        "solde_compte_fcfa":   round(solde_cedant),  # + = bénéfice réassureur
        "taux_cession_pct":    taux_cession * 100,
    }


def _calculer_cession_xs_sinistre(
    sinistre: float,
    priorite: float,
    portee: float,
) -> dict:
    """Calcul XS sinistre : réassureur paie au-delà de la priorité."""
    part_cedant    = min(sinistre, priorite)
    part_reassureur = min(max(sinistre - priorite, 0), portee)
    return {
        "sinistre_total_fcfa":     round(sinistre),
        "part_cedant_fcfa":        round(part_cedant),
        "part_reassureur_fcfa":    round(part_reassureur),
        "priorite_fcfa":           round(priorite),
        "portee_fcfa":             round(portee),
    }


def _calculer_ristourne_benefice(
    prime_cedee: float,
    sinistre_cede: float,
    commission: float,
    frais_gestion_pct: float = 5.0,
    seuil_benefice_pct: float = 70.0,
    taux_ristourne_pct: float = 50.0,
) -> dict:
    """Clause de participation aux bénéfices (ristourne bénéficiaire)."""
    frais          = prime_cedee * frais_gestion_pct / 100
    s_r_ratio      = (sinistre_cede + commission + frais) / prime_cedee * 100 if prime_cedee else 100
    benefice_brut  = prime_cedee - sinistre_cede - commission - frais
    ristourne      = max(benefice_brut * taux_ristourne_pct / 100, 0) if s_r_ratio < seuil_benefice_pct else 0
    return {
        "sr_ratio_pct":        round(s_r_ratio, 2),
        "benefice_brut_fcfa":  round(max(benefice_brut, 0)),
        "ristourne_fcfa":      round(ristourne),
        "eligible_ristourne":  s_r_ratio < seuil_benefice_pct,
    }


class AgentReassurance(BaseAgent):
    type_agent = TypeAgent.REASSURANCE

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Réassurance de YukpoAssurance, expert en cessions et récupérations CIMA.

TYPES DE TRAITÉS GÉRÉS :
- Proportionnels : Quote-part (QP), Excédent de plein (XL)
- Non-proportionnels : Excess-Loss (XS) par risque, XS par événement, Excédent de perte annuelle (Stop Loss)
- Facultatif : cession affaire par affaire pour risques hors capacité

WORKFLOW BORDEREAU TRIMESTRIEL :
1. consolider_portefeuille → récupérer primes et sinistres par branche
2. calculer_cession → quote-part ou XS selon traité
3. etablir_bordereau → bordereau de primes + bordereau de sinistres
4. verifier_ristourne → clause de participation aux bénéfices
5. soumettre_bordereau → validation comptable + envoi réassureur

RÉCUPÉRATION SINISTRE GRAVE :
1. qualifier_sinistre_reassurable → vérifier dépassement priorité
2. notifier_reassureur → avis de sinistre (délai contractuel 30j)
3. suivre_recuperation → état règlement réassureur
4. comptabiliser_recuperation → écriture PCSA compte 66/46

RÈGLES ABSOLUES :
- Calculs cession = déterministes (barèmes traités)
- IA uniquement pour qualification risques atypiques et rédaction correspondances
- Notification réassureur obligatoire pour tout sinistre > priorité XS
- Validation humaine pour : envoi bordereaux, validation ristourne > 5M FCFA"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "calculer_cession_prime",
                "description": "Calcule la cession de prime selon le type de traité (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "branche":          {"type": "string", "enum": list(_TAUX_CESSION_BRANCHE.keys())},
                    "type_traite":      {"type": "string", "enum": ["quote_part", "excedent_plein", "facultatif"]},
                    "prime_brute_fcfa": {"type": "number"},
                    "sinistres_fcfa":   {"type": "number"},
                    "taux_cession_pct": {"type": "number", "description": "Si différent du taux standard branche"},
                    "reassureur":       {"type": "string"},
                }, "required": ["branche", "type_traite", "prime_brute_fcfa"]},
            },
            {
                "name": "calculer_recuperation_xs",
                "description": "Calcule la part récupérable sur un sinistre XS (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "branche":          {"type": "string"},
                    "montant_sinistre": {"type": "number"},
                    "priorite_fcfa":    {"type": "number", "description": "Si différente du standard"},
                    "portee_fcfa":      {"type": "number", "description": "Capacité XS"},
                    "police_id":        {"type": "string"},
                    "reassureur":       {"type": "string"},
                }, "required": ["branche", "montant_sinistre"]},
            },
            {
                "name": "etablir_bordereau",
                "description": "Génère le bordereau trimestriel primes + sinistres pour le réassureur",
                "input_schema": {"type": "object", "properties": {
                    "trimestre":        {"type": "string", "description": "ex: T1-2025"},
                    "reassureur":       {"type": "string"},
                    "type_bordereau":   {"type": "string", "enum": ["primes", "sinistres", "complet"]},
                    "branches":         {"type": "array", "items": {"type": "string"}},
                }, "required": ["trimestre", "reassureur"]},
            },
            {
                "name": "calculer_ristourne_benefice",
                "description": "Calcule la participation aux bénéfices annuelle (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "annee":            {"type": "integer"},
                    "reassureur":       {"type": "string"},
                    "prime_cedee_fcfa": {"type": "number"},
                    "sinistre_cede_fcfa": {"type": "number"},
                    "commission_fcfa":  {"type": "number"},
                    "taux_ristourne_pct": {"type": "number"},
                }, "required": ["prime_cedee_fcfa", "sinistre_cede_fcfa", "commission_fcfa"]},
            },
            {
                "name": "notifier_reassureur_sinistre",
                "description": "Prépare et soumet l'avis de sinistre grave au réassureur",
                "input_schema": {"type": "object", "properties": {
                    "police_id":        {"type": "string"},
                    "sinistre_id":      {"type": "string"},
                    "montant_estime":   {"type": "number"},
                    "reassureur":       {"type": "string"},
                    "description":      {"type": "string"},
                    "date_sinistre":    {"type": "string"},
                }, "required": ["sinistre_id", "montant_estime", "reassureur"]},
            },
            {
                "name": "soumettre_bordereau",
                "description": "Soumet le bordereau validé pour approbation humaine puis envoi réassureur",
                "input_schema": {"type": "object", "properties": {
                    "trimestre":        {"type": "string"},
                    "reassureur":       {"type": "string"},
                    "solde_compte":     {"type": "number"},
                    "bordereau_data":   {"type": "object"},
                }, "required": ["trimestre", "reassureur", "solde_compte"]},
            },
            {
                "name": "consolider_portefeuille_reassurance",
                "description": "Consolide les données de primes et sinistres de la période par branche",
                "input_schema": {"type": "object", "properties": {
                    "trimestre": {"type": "string"},
                    "branche":   {"type": "string"},
                }, "required": ["trimestre"]},
            },
            {
                "name": "rediger_correspondance_reassureur",
                "description": "Rédige une correspondance formelle au réassureur via IA",
                "input_schema": {"type": "object", "properties": {
                    "objet":        {"type": "string"},
                    "contexte":     {"type": "string"},
                    "reassureur":   {"type": "string"},
                    "type_courrier": {"type": "string", "enum": ["avis_sinistre", "demande_accord_fac", "contestation", "reclamation_solde"]},
                }, "required": ["objet", "contexte", "reassureur", "type_courrier"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT RÉASSURANCE — quand demander une information :

1. RÉASSUREUR OU TRAITÉ NON IDENTIFIÉ
   → "Quel est le nom du réassureur ou la référence du traité concerné ? (Ex: Africa Re, CICA Re, Munich Re — ou numéro de traité TR-2024-001)"
   type_reponse: texte_libre

2. TYPE DE TRAITÉ AMBIGU
   → "Quel type de traité de réassurance est concerné par cette opération ?"
   type_reponse: choix_multiple  choix: ["Quote-part (QP) — proportionnel", "Excédent de plein (XL) — proportionnel", "Excess Loss par risque (XS risque)", "Excess Loss par événement (XS cat)", "Stop Loss (excédent de perte annuelle)", "Facultatif — affaire par affaire"]

3. TAUX DE RÉTENTION (PLEIN DE CONSERVATION) MANQUANT
   → "Quel est le plein de conservation de la cédante (en FCFA ou en %) pour ce traité ? (Détermine la part cédée au réassureur)"
   type_reponse: nombre

4. PÉRIODE DU BORDEREAU NON PRÉCISÉE
   → "Pour quel trimestre ou quelle période souhaitez-vous établir le bordereau de cession ?"
   type_reponse: choix_multiple  choix: ["T1 (Janvier–Mars)", "T2 (Avril–Juin)", "T3 (Juillet–Septembre)", "T4 (Octobre–Décembre)", "Bordereau annuel de régularisation"]

5. SINISTRE À DÉCLARER AU RÉASSUREUR — MONTANT SEUIL
   → "Quel est le montant total de ce sinistre (en FCFA) ? (Détermine si la déclaration au réassureur est obligatoire selon la priorité du traité XS)"
   type_reponse: nombre

6. BRANCHE CONCERNÉE (pour sélection du traité applicable)
   → "Quelle branche d'assurance est concernée par cette cession ?"
   type_reponse: choix_multiple  choix: ["RC Auto", "MRH / Incendie", "Transport maritime / aérien", "Risques techniques / Construction", "RC Professionnelle", "Accidents Corporels", "Vie / Prévoyance", "Toutes branches (bordereau global)"]

7. RISTOURNE RÉASSUREUR — TAUX APPLICABLE
   → "Quel est le taux de commission de réassurance (ristourne) prévu au traité pour cette branche (en %) ?"
   type_reponse: nombre

8. BORDEREAU DE RÉASSURANCE À SCANNER (vérification écarts)
   → "Veuillez transmettre le bordereau de réassurance en format PDF ou scan pour vérification des montants cédés vs notre comptabilité ORASS."
   type_reponse: image  nombre_images_max: 1  formats_acceptes: ["pdf", "jpg", "png"]

9. TRAITÉ DE RÉASSURANCE — CLAUSES À ANALYSER
   → "Avez-vous le traité de réassurance signé à transmettre ? Je vais extraire les clauses clés (plein de conservation, priorité XL, taux de commission) pour paramétrage."
   type_reponse: images  nombre_images_max: 3  formats_acceptes: ["pdf", "jpg", "png"]

PROGRESSION : Réassureur/Traité → Type de traité → Bordereau (scan si disponible) → Branche → Période → Montants et taux.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "calculer_cession_prime":
                branche   = params["branche"]
                type_t    = params["type_traite"]
                prime_b   = params["prime_brute_fcfa"]
                sinistres = params.get("sinistres_fcfa", 0)
                taux      = params.get("taux_cession_pct", _TAUX_CESSION_BRANCHE.get(branche, 0.20) * 100) / 100
                comm_pct  = _COMM_REASSURANCE.get(type_t, 15.0)
                result    = _calculer_cession_quote_part(prime_b, sinistres, taux, comm_pct)
                result["branche"]   = branche
                result["type_traite"] = type_t
                result["reassureur"] = params.get("reassureur", "N/A")
                return json.dumps(result, ensure_ascii=False)

            if nom == "calculer_recuperation_xs":
                branche  = params["branche"]
                sinistre = params["montant_sinistre"]
                priorite = params.get("priorite_fcfa", _PRIORITE_XS.get(branche, 10_000_000))
                portee   = params.get("portee_fcfa", priorite * 10)
                result   = _calculer_cession_xs_sinistre(sinistre, priorite, portee)
                result["police_id"]  = params.get("police_id", "")
                result["reassureur"] = params.get("reassureur", "")
                result["recuperable"] = result["part_reassureur_fcfa"] > 0
                return json.dumps(result, ensure_ascii=False)

            if nom == "calculer_ristourne_benefice":
                result = _calculer_ristourne_benefice(
                    prime_cedee=params["prime_cedee_fcfa"],
                    sinistre_cede=params["sinistre_cede_fcfa"],
                    commission=params["commission_fcfa"],
                    taux_ristourne_pct=params.get("taux_ristourne_pct", 50.0),
                )
                result["annee"]     = params.get("annee", date.today().year - 1)
                result["reassureur"] = params.get("reassureur", "")
                return json.dumps(result, ensure_ascii=False)

            if nom == "etablir_bordereau":
                from core.orass_connector import orass
                trimestre = params["trimestre"]
                reassureur = params["reassureur"]
                branches  = params.get("branches", list(_TAUX_CESSION_BRANCHE.keys()))
                # Simulation consolidation — en prod, requête ORASS
                bordereau = {
                    "trimestre":   trimestre,
                    "reassureur":  reassureur,
                    "date_etabli": date.today().isoformat(),
                    "lignes": [],
                }
                total_prime = 0
                total_sin   = 0
                for b in branches[:6]:
                    prime_b = 15_000_000 if b not in ("construction",) else 50_000_000
                    sin_b   = prime_b * 0.35
                    taux    = _TAUX_CESSION_BRANCHE.get(b, 0.20)
                    cession = _calculer_cession_quote_part(prime_b, sin_b, taux, _COMM_REASSURANCE["quote_part"])
                    bordereau["lignes"].append({"branche": b, **cession})
                    total_prime += cession["prime_cedee_fcfa"]
                    total_sin   += cession["sinistre_cede_fcfa"]
                bordereau["total_prime_cedee"]    = total_prime
                bordereau["total_sinistre_cede"]  = total_sin
                bordereau["solde_compte"]         = total_prime - total_sin
                return json.dumps(bordereau, ensure_ascii=False, indent=2)

            if nom == "consolider_portefeuille_reassurance":
                return json.dumps({
                    "trimestre": params["trimestre"],
                    "branche":   params.get("branche", "toutes"),
                    "statut":    "Consolidation simulée — connecter ORASS pour données réelles",
                    "nb_polices_cedees": 142,
                    "prime_brute_total": 87_500_000,
                    "sinistres_total":   24_300_000,
                }, ensure_ascii=False)

            if nom == "soumettre_bordereau":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type":         "bordereau_reassurance",
                    "trimestre":    params["trimestre"],
                    "reassureur":   params["reassureur"],
                    "solde_compte": params["solde_compte"],
                    "bordereau_data": params.get("bordereau_data", {}),
                    "user_id":      user_id,
                    "execution_id": execution_id,
                })
                solde = params["solde_compte"]
                sens  = "à recevoir du réassureur" if solde > 0 else "à verser au réassureur"
                return f"Bordereau {params['trimestre']} soumis pour validation — Solde {abs(solde):,.0f} FCFA {sens}".replace(",", " ")

            if nom == "notifier_reassureur_sinistre":
                from core.approval_queue import approval_queue
                montant = params["montant_estime"]
                await approval_queue.ajouter({
                    "type":           "notification_sinistre_reassureur",
                    "sinistre_id":    params["sinistre_id"],
                    "police_id":      params.get("police_id", ""),
                    "montant_estime": montant,
                    "reassureur":     params["reassureur"],
                    "description":    params.get("description", ""),
                    "user_id":        user_id,
                    "execution_id":   execution_id,
                })
                return (
                    f"Avis de sinistre préparé — Montant estimé : {montant:,.0f} FCFA\n"
                    f"Réassureur : {params['reassureur']}\n"
                    f"En attente de validation avant envoi (délai contractuel 30j)."
                ).replace(",", " ")

            if nom == "rediger_correspondance_reassureur":
                from core.ia_client import ModeIA, ia_client
                prompt = f"""Rédige une correspondance professionnelle à destination d'un réassureur.
Type : {params['type_courrier']}
Objet : {params['objet']}
Réassureur : {params['reassureur']}
Contexte : {params['contexte']}

Utilise un style formel, référence les clauses contractuelles pertinentes si applicable.
Langue : français."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentReassurance] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
