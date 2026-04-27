"""Agent RH & Organisation — complet : congés, paie, contrats, disciplinaire, DSN, formation, recrutement, pointage."""
from __future__ import annotations
import json, logging
from datetime import date, datetime, timedelta
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.rh")

# ─── Constantes légales (Code Travail OHADA + Loi Cameroun) ──────────────────
CONGE_PAR_MOIS   = 2.5          # Art. 89 CT — jours ouvrables
CNPS_SALARIE     = 0.042        # 4,2%
CNPS_PATRONAL    = 0.112        # 11,2%
PLAFOND_CNPS     = 750_000      # FCFA/mois
SMIG_CAMEROUN    = 41_875       # FCFA/mois (2024)
DUREE_PREAVIS = {"essai": 0, "cdd": 0, "cdi_cadre": 3, "cdi_maitrise": 2, "cdi_execution": 1}  # mois

_JOURS_FERIES_CM = {"01-01", "02-11", "05-01", "05-20", "08-15", "12-25"}

def _jours_ouvrables(d1: date, d2: date, pays: str = "CM") -> int:
    feries = _JOURS_FERIES_CM if pays == "CM" else set()
    count  = 0
    cur    = d1
    while cur <= d2:
        if cur.weekday() < 5 and cur.strftime("%m-%d") not in feries:
            count += 1
        cur += timedelta(days=1)
    return count

def _calculer_irpp(assiette_mensuelle: float) -> int:
    tranches = [
        (0,         2_000_000, 0.00),
        (2_000_000, 3_000_000, 0.10),
        (3_000_000, 5_000_000, 0.15),
        (5_000_000,10_000_000, 0.25),
        (10_000_000,15_000_000, 0.35),
        (15_000_000, float("inf"), 0.385),
    ]
    annuel = assiette_mensuelle * 12
    irpp_annuel = 0.0
    for borne_inf, borne_sup, taux in tranches:
        if annuel <= borne_inf: break
        irpp_annuel += (min(annuel, borne_sup) - borne_inf) * taux
    return round(irpp_annuel / 12)

def _indemnite_licenciement(salaire_brut: float, anciennete_ans: float) -> float:
    """Indemnité légale de licenciement Cameroun (Art. 34 CT)."""
    # 20% salaire mensuel par année pour les 10 premières, 30% au-delà
    if anciennete_ans < 2: return 0
    part1 = min(anciennete_ans, 10) * salaire_brut * 0.20
    part2 = max(0, anciennete_ans - 10) * salaire_brut * 0.30
    return round(part1 + part2)


class AgentRH(BaseAgent):
    type_agent = TypeAgent.RH

    def _system_prompt(self) -> str:
        return """Tu es l'Agent RH de YukpoAssurance, expert en gestion des ressources humaines OHADA / Cameroun.

DOMAINES COUVERTS :
1. CONGÉS & ABSENCES : solde, approbation, absences maladie, maternité, exceptionnel
2. PAIE : bulletin complet (CNPS, IRPP, HS, primes), masse salariale, 13ème mois
3. CONTRATS : CDI/CDD/stage — rédaction, modification, rupture, préavis, indemnités
4. RECRUTEMENT : offre, sourcing, entretiens, embauche, intégration (onboarding)
5. FORMATION : plan annuel, inscriptions, suivi, certifications réglementaires CIMA
6. ÉVALUATIONS : objectifs, entretien annuel, score performance, décisions RH
7. DISCIPLINAIRE : avertissements, sanctions, procédures licenciement
8. POINTAGE & TEMPS : gestion heures supplémentaires, absences non justifiées
9. DÉCLARATIONS SOCIALES : CNPS mensuel, DSN, bordereaux cotisations
10. ACCIDENTS TRAVAIL : déclaration, suivi, indemnisation CNPS
11. AVANTAGES SOCIAUX : mutuelle, transport, logement, assurance groupe employés

RÈGLES ABSOLUES :
- Calculs de paie = DÉTERMINISTES (barèmes légaux CNPS/IRPP/SMIG)
- IA uniquement pour rédaction contrats, lettres, plans de formation, rapports
- TOUTE INSERTION EN BASE (nouvel employé, contrat, bulletin) → validation RH obligatoire
- Congé > 10 jours → validation DRH
- Licenciement → validation DG + service juridique
- Données RH = CONFIDENTIELLES — accès par rôle"""

    def _definir_outils(self) -> list[dict]:
        return [
            # ── Congés ──
            {
                "name": "gerer_conge",
                "description": "Traite une demande de congé : vérification solde, calcul durée, validation DRH",
                "input_schema": {"type": "object", "properties": {
                    "employe_id":  {"type": "string"},
                    "type_conge":  {"type": "string", "enum": ["annuel", "maladie", "maternite", "paternite", "exceptionnel", "sans_solde", "recuperation"]},
                    "date_debut":  {"type": "string"},
                    "date_fin":    {"type": "string"},
                    "action":      {"type": "string", "enum": ["verifier_solde", "demander", "approuver", "rejeter"]},
                    "motif":       {"type": "string"},
                    "justificatif_base64": {"type": "string"},
                }, "required": ["employe_id", "type_conge", "action"]},
            },
            # ── Paie ──
            {
                "name": "calculer_bulletin_paie",
                "description": "Calcule le bulletin de paie complet avec toutes retenues légales (déterministe) — présente pour validation avant enregistrement",
                "input_schema": {"type": "object", "properties": {
                    "employe_id":     {"type": "string"},
                    "salaire_base":   {"type": "number"},
                    "heures_supp":    {"type": "number"},
                    "primes":         {"type": "number"},
                    "avantages_nature": {"type": "number"},
                    "retenues_supp":  {"type": "number"},
                    "avance_salaire": {"type": "number"},
                    "jours_absence":  {"type": "integer"},
                    "mois":           {"type": "string"},
                    "annee":          {"type": "integer"},
                }, "required": ["employe_id", "salaire_base", "mois", "annee"]},
            },
            {
                "name": "traiter_masse_salariale",
                "description": "Génère la masse salariale mensuelle complète + bordereau CNPS (présente pour validation)",
                "input_schema": {"type": "object", "properties": {
                    "mois":  {"type": "string"},
                    "annee": {"type": "integer"},
                    "departement": {"type": "string"},
                }, "required": ["mois", "annee"]},
            },
            # ── Contrats ──
            {
                "name": "gerer_contrat",
                "description": "Création, modification, rupture de contrats de travail — rédaction IA + validation avant insertion",
                "input_schema": {"type": "object", "properties": {
                    "action":        {"type": "string", "enum": ["rediger_cdi", "rediger_cdd", "rediger_stage", "modifier", "rompre_periode_essai", "calcul_preavis", "calcul_indemnites", "rupture_conventionnelle"]},
                    "employe_id":    {"type": "string"},
                    "poste":         {"type": "string"},
                    "salaire":       {"type": "number"},
                    "date_debut":    {"type": "string"},
                    "duree_mois":    {"type": "integer", "description": "Pour CDD"},
                    "motif_rupture": {"type": "string"},
                    "anciennete_ans": {"type": "number"},
                }, "required": ["action"]},
            },
            # ── Recrutement ──
            {
                "name": "gerer_recrutement",
                "description": "Pipeline complet recrutement : offre → entretien → embauche → onboarding",
                "input_schema": {"type": "object", "properties": {
                    "action":         {"type": "string", "enum": ["publier_offre", "lister_candidats", "scorer_cv", "planifier_entretien", "evaluer_candidat", "embaucher", "onboarding"]},
                    "poste":          {"type": "string"},
                    "description":    {"type": "string"},
                    "profil_requis":  {"type": "string"},
                    "candidat_id":    {"type": "string"},
                    "date_entretien": {"type": "string"},
                    "cv_base64":      {"type": "string"},
                    "note":           {"type": "number"},
                    "commentaire":    {"type": "string"},
                }, "required": ["action"]},
            },
            # ── Formation ──
            {
                "name": "gerer_formation",
                "description": "Plan formation, inscriptions, certifications CIMA obligatoires, suivi completion",
                "input_schema": {"type": "object", "properties": {
                    "action":       {"type": "string", "enum": ["plan_annuel", "inscrire", "valider", "certifications_reglementaires", "lister_catalogue"]},
                    "employe_id":   {"type": "string"},
                    "formation_id": {"type": "string"},
                    "departement":  {"type": "string"},
                    "annee":        {"type": "integer"},
                }, "required": ["action"]},
            },
            # ── Évaluation & performance ──
            {
                "name": "evaluer_performance",
                "description": "Évaluation annuelle complète : score + rapport + décision RH (promotion/plan de performance)",
                "input_schema": {"type": "object", "properties": {
                    "employe_id":   {"type": "string"},
                    "periode":      {"type": "string"},
                    "objectifs":    {"type": "array", "items": {"type": "object"}},
                    "realisations": {"type": "array", "items": {"type": "object"}},
                    "mode":         {"type": "string", "enum": ["calculer_score", "rapport_ia", "decision_rh"]},
                }, "required": ["employe_id", "periode"]},
            },
            # ── Disciplinaire ──
            {
                "name": "gerer_disciplinaire",
                "description": "Procédures disciplinaires : avertissement, mise à pied, licenciement — présente pour validation avant enregistrement",
                "input_schema": {"type": "object", "properties": {
                    "employe_id":  {"type": "string"},
                    "type_sanction": {"type": "string", "enum": ["avertissement_oral", "avertissement_ecrit", "blame", "mise_a_pied", "licenciement_faute_simple", "licenciement_faute_grave", "licenciement_economique"]},
                    "faits":       {"type": "string", "description": "Description détaillée des faits"},
                    "date_faits":  {"type": "string"},
                    "anciennete_ans": {"type": "number"},
                    "salaire_brut": {"type": "number"},
                }, "required": ["employe_id", "type_sanction", "faits"]},
            },
            # ── Pointage & heures ──
            {
                "name": "gerer_pointage",
                "description": "Enregistrement pointages, heures supplémentaires, absences non justifiées",
                "input_schema": {"type": "object", "properties": {
                    "employe_id": {"type": "string"},
                    "action":     {"type": "string", "enum": ["enregistrer_pointage", "relever_absences", "heures_supp_mois", "rapport_retards"]},
                    "date":       {"type": "string"},
                    "heure_entree": {"type": "string"},
                    "heure_sortie": {"type": "string"},
                    "mois":       {"type": "string"},
                    "annee":      {"type": "integer"},
                }, "required": ["employe_id", "action"]},
            },
            # ── Déclarations sociales ──
            {
                "name": "declarations_sociales",
                "description": "Bordereau CNPS mensuel, DSN, attestation CNPS, déclaration accident travail",
                "input_schema": {"type": "object", "properties": {
                    "type_declaration": {"type": "string", "enum": ["bordereau_cnps", "attestation_cotisations", "accident_travail", "maladie_professionnelle"]},
                    "mois":   {"type": "string"},
                    "annee":  {"type": "integer"},
                    "employe_id": {"type": "string"},
                    "description_accident": {"type": "string"},
                }, "required": ["type_declaration", "annee"]},
            },
            # ── Accidents de travail ──
            {
                "name": "declarer_accident_travail",
                "description": "Déclare et suit un accident de travail : formulaire CNPS, suivi arrêt, indemnisation",
                "input_schema": {"type": "object", "properties": {
                    "employe_id":   {"type": "string"},
                    "date_accident": {"type": "string"},
                    "description":  {"type": "string"},
                    "gravite":      {"type": "string", "enum": ["leger", "moyen", "grave", "mortel"]},
                    "jours_arret":  {"type": "integer"},
                    "action":       {"type": "string", "enum": ["declarer", "suivre", "cloture"]},
                }, "required": ["employe_id", "date_accident", "description", "gravite"]},
            },
            # ── Planning ──
            {
                "name": "planning_equipe",
                "description": "Planning absences, gardes, disponibilités, réunions",
                "input_schema": {"type": "object", "properties": {
                    "departement": {"type": "string"},
                    "date_debut":  {"type": "string"},
                    "date_fin":    {"type": "string"},
                    "vue":         {"type": "string", "enum": ["absences", "gardes", "disponibilites", "reunions", "charge_travail"]},
                }, "required": ["departement"]},
            },
            # ── Notifications ──
            {
                "name": "notifier_employe",
                "description": "Envoie une notification RH (congé, bulletin, rappel, sanction)",
                "input_schema": {"type": "object", "properties": {
                    "employe_id": {"type": "string"},
                    "type_notif": {"type": "string", "enum": ["conge_approuve", "conge_rejete", "bulletin_dispo", "formation", "rappel_evaluation", "convocation_entretien", "sanction"]},
                    "message":    {"type": "string"},
                }, "required": ["employe_id", "type_notif", "message"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT RH — quand demander une information :

1. EMPLOYÉ NON IDENTIFIÉ (matricule / nom ambigu)
   → "Quel est le matricule ou le nom complet de l'employé concerné ? (Ex: MAT-2021-045 ou 'MBARGA Paul, Département Sinistres')"
   type_reponse: texte_libre

2. TYPE DE CONGÉ NON PRÉCISÉ
   → "Quel type de congé ou d'absence l'employé souhaite-t-il prendre ?"
   type_reponse: choix_multiple  choix: ["Congé annuel payé", "Congé maladie (certificat médical requis)", "Congé maternité / paternité", "Congé exceptionnel (événement familial)", "Absence pour formation", "Congé sans solde"]

3. DATES DE CONGÉ MANQUANTES
   → "Quelles sont les dates de début et de fin du congé souhaité ? (Format : JJ/MM/AAAA → JJ/MM/AAAA)"
   type_reponse: texte_libre

4. POSTE À POURVOIR NON DÉFINI (recrutement)
   → "Pour quel poste souhaitez-vous lancer le recrutement ? Précisez le département, le niveau d'expérience requis et si c'est un CDI ou CDD."
   type_reponse: texte_libre

5. PÉRIODE DE PAIE CIBLÉE
   → "Pour quel mois et quelle année souhaitez-vous le traitement de la paie ?"
   type_reponse: texte_libre

6. TYPE DE CONTRAT POUR MODIFICATION
   → "Quelle modification souhaitez-vous apporter au contrat de travail ?"
   type_reponse: choix_multiple  choix: ["Augmentation de salaire", "Changement de poste / promotion", "Passage CDI vers CDD ou inversement", "Modification du temps de travail", "Rupture conventionnelle", "Licenciement économique", "Fin de période d'essai"]

7. MOTIF DISCIPLINAIRE (si pertinent)
   → "Pouvez-vous décrire brièvement les faits justifiant cette mesure disciplinaire ? (Ces informations resteront confidentielles dans le dossier employé)"
   type_reponse: texte_libre

8. PRIME EXCEPTIONNELLE — MONTANT ET MOTIF
   → "Quel est le montant de la prime exceptionnelle (en FCFA) et quel en est le motif ? (Performance, ancienneté, 13ème mois, etc.)"
   type_reponse: texte_libre

9. PIÈCES JUSTIFICATIVES CONGÉ / ABSENCE (arrêt maladie, certificat)
   → "Veuillez scanner et transmettre la pièce justificative pour cette absence : arrêt de travail médical, certificat de présence aux funérailles, ou attestation d'hospitalisation selon le motif déclaré."
   type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

10. DIPLÔMES / CV POUR RECRUTEMENT (dossier candidat)
    → "Pour le recrutement, pouvez-vous transmettre les diplômes et/ou le CV du candidat retenu ? Ces documents seront archivés dans le dossier employé."
    type_reponse: images  nombre_images_max: 5  formats_acceptes: ["pdf", "jpg", "png"]

11. CNI / PASSEPORT NOUVEL EMPLOYÉ (KYC RH)
    → "Veuillez scanner la pièce d'identité (CNI ou passeport recto/verso) du nouvel employé pour constitution de son dossier administratif."
    type_reponse: images  nombre_images_max: 2  formats_acceptes: ["jpg", "png", "pdf"]

PROGRESSION : Identification employé → Nature de la demande → Dates / Montants → Pièces justificatives (scan) → Validation.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            # ── CONGÉS ──
            if nom == "gerer_conge":
                from core.orass_connector import orass
                emp_id = params["employe_id"]
                action = params["action"]

                if action == "verifier_solde":
                    info = await orass.get_employe(emp_id)
                    anciennete_mois = info.get("anciennete_mois", 0)
                    conges_pris     = info.get("conges_pris_annee", 0)
                    acquis          = round(anciennete_mois * CONGE_PAR_MOIS)
                    solde           = max(0, acquis - conges_pris)
                    return json.dumps({
                        "employe_id": emp_id, "acquis_jours": acquis,
                        "pris_jours": conges_pris, "solde_jours": solde,
                        "fondement": "Art. 89 Code Travail OHADA",
                    }, ensure_ascii=False)

                if action == "demander":
                    d1    = date.fromisoformat(params["date_debut"])
                    d2    = date.fromisoformat(params["date_fin"])
                    jours = _jours_ouvrables(d1, d2)
                    info  = await orass.get_employe(emp_id)
                    solde = max(0, round(info.get("anciennete_mois", 0) * CONGE_PAR_MOIS) - info.get("conges_pris_annee", 0))
                    faisable = (jours <= solde) or params["type_conge"] != "annuel"
                    # TOUJOURS présenter pour validation avant enregistrement
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "conge_rh",
                        "employe_id": emp_id, "type_conge": params["type_conge"],
                        "date_debut": params.get("date_debut"), "date_fin": params.get("date_fin"),
                        "jours_ouvr": jours, "solde_disponible": solde, "faisable": faisable,
                        "motif": params.get("motif", ""),
                        "necessite_validation_drh": jours > 10,
                        "user_id": user_id, "execution_id": execution_id,
                    })
                    return json.dumps({
                        "statut": "soumis_validation",
                        "jours_demandes": jours, "solde_disponible": solde, "faisable": faisable,
                        "message": f"Demande de congé {params['type_conge']} ({jours} jours) soumise pour validation {'DRH' if jours > 10 else 'responsable'}"
                    }, ensure_ascii=False)

                return f"Action congé '{action}' : consulter le responsable RH"

            # ── PAIE ──
            if nom == "calculer_bulletin_paie":
                salaire_base    = params["salaire_base"]
                heures_supp     = params.get("heures_supp", 0)
                primes          = params.get("primes", 0)
                avantages       = params.get("avantages_nature", 0)
                retenues_supp   = params.get("retenues_supp", 0)
                avance          = params.get("avance_salaire", 0)
                jours_abs       = params.get("jours_absence", 0)

                # Déduction absences non justifiées
                taux_journalier = salaire_base / 26
                deduction_abs   = round(jours_abs * taux_journalier)

                # Heures supplémentaires (majoration 20% ≤8h, 40% >8h)
                taux_hor = salaire_base / 173.33
                hs_8     = min(heures_supp, 8)
                hs_plus  = max(0, heures_supp - 8)
                hs_mnt   = round(hs_8 * taux_hor * 1.20 + hs_plus * taux_hor * 1.40)

                salaire_brut = salaire_base - deduction_abs + hs_mnt + primes + avantages

                # CNPS salarié (plafonné)
                cnps_sal  = round(min(salaire_brut, PLAFOND_CNPS) * CNPS_SALARIE)
                # IRPP
                assiette  = (salaire_brut - cnps_sal) * 0.70
                irpp      = _calculer_irpp(assiette)
                # Part patronale
                cnps_pat  = round(min(salaire_brut, PLAFOND_CNPS) * CNPS_PATRONAL)

                total_ret = cnps_sal + irpp + retenues_supp + avance
                net       = max(0, round(salaire_brut - total_ret))
                cout_tot  = round(salaire_brut + cnps_pat)

                bulletin = {
                    "employe_id": params["employe_id"],
                    "periode": f"{params['mois']}/{params['annee']}",
                    "salaire_base": salaire_base,
                    "deduction_absences": deduction_abs,
                    "hs_montant": hs_mnt,
                    "primes": primes,
                    "avantages_nature": avantages,
                    "salaire_brut": round(salaire_brut),
                    "cnps_salarie": cnps_sal,
                    "irpp": irpp,
                    "autres_retenues": retenues_supp,
                    "avance_deduite": avance,
                    "total_retenues": round(total_ret),
                    "net_a_payer": net,
                    "cnps_patronal": cnps_pat,
                    "cout_total_employeur": cout_tot,
                }
                # Validation obligatoire avant enregistrement en BDD
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "bulletin_paie",
                    "bulletin": bulletin,
                    "montant": net,
                    "user_id": user_id, "execution_id": execution_id,
                })
                return json.dumps(bulletin | {"statut": "soumis_validation_avant_enregistrement"}, ensure_ascii=False)

            if nom == "traiter_masse_salariale":
                from core.orass_connector import orass
                employes = await orass.get_employes(departement=params.get("departement"))
                total_brut = total_net = total_cnps_pat = total_irpp = 0
                lignes = []
                for emp in employes:
                    sal   = emp.get("salaire_base", 0)
                    cnps  = round(min(sal, PLAFOND_CNPS) * CNPS_SALARIE)
                    irpp  = _calculer_irpp((sal - cnps) * 0.70)
                    net   = sal - cnps - irpp
                    cp    = round(min(sal, PLAFOND_CNPS) * CNPS_PATRONAL)
                    total_brut  += sal
                    total_net   += net
                    total_cnps_pat += cp
                    total_irpp  += irpp
                    lignes.append({"id": emp.get("id"), "nom": emp.get("nom"), "brut": sal, "net": net})
                masse = {
                    "periode": f"{params['mois']}/{params['annee']}",
                    "nb_employes": len(employes),
                    "total_brut": total_brut,
                    "total_net": total_net,
                    "total_cnps_patronal": total_cnps_pat,
                    "total_irpp": total_irpp,
                    "cout_total_employeur": total_brut + total_cnps_pat,
                    "lignes": lignes[:20],
                }
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "masse_salariale",
                    "masse_salariale": masse,
                    "montant": total_net,
                    "user_id": user_id, "execution_id": execution_id,
                })
                return json.dumps(masse | {"statut": "soumis_validation_DRH_avant_virement"}, ensure_ascii=False)

            # ── CONTRATS ──
            if nom == "gerer_contrat":
                action = params["action"]
                from core.ia_client import ModeIA, ia_client

                if action in ("rediger_cdi", "rediger_cdd", "rediger_stage"):
                    type_contrat = action.replace("rediger_", "").upper()
                    prompt = f"""Rédige un contrat de travail {type_contrat} conforme au Code du travail camerounais et à l'OHADA.
Poste : {params.get('poste', 'N/D')}
Salaire brut mensuel : {params.get('salaire', 0):,.0f} FCFA
Date de début : {params.get('date_debut', date.today().isoformat())}
{'Durée : ' + str(params.get('duree_mois')) + ' mois' if params.get('duree_mois') else ''}
Inclure : identification parties, poste, rémunération, période essai, congés, CNPS, clauses confidentialité et non-concurrence."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    # Présenter contrat pour validation avant enregistrement
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "contrat_travail",
                        "type_contrat": type_contrat,
                        "poste": params.get("poste"),
                        "salaire": params.get("salaire"),
                        "contrat_redige": rep.contenu[:500],  # aperçu
                        "user_id": user_id, "execution_id": execution_id,
                    })
                    return f"Contrat {type_contrat} rédigé — soumis pour validation RH avant signature\n\n{rep.contenu}"

                if action == "calcul_indemnites":
                    sal = params.get("salaire_brut", 0) or params.get("salaire", 0)
                    anc = params.get("anciennete_ans", 0)
                    ind = _indemnite_licenciement(sal, anc)
                    preavis_mois = DUREE_PREAVIS.get("cdi_execution", 1)
                    return json.dumps({
                        "salaire_brut": sal,
                        "anciennete_ans": anc,
                        "indemnite_legale_fcfa": ind,
                        "preavis_mois": preavis_mois,
                        "total_sortie": ind + sal * preavis_mois,
                        "fondement": "Art. 34 Code Travail Cameroun",
                    }, ensure_ascii=False)

                if action in ("licenciement_faute_simple", "licenciement_economique", "rupture_conventionnelle"):
                    # Validation DG + juridique obligatoire
                    from core.approval_queue import approval_queue
                    sal = params.get("salaire", 0)
                    anc = params.get("anciennete_ans", 0)
                    ind = _indemnite_licenciement(sal, anc) if action != "licenciement_faute_grave" else 0
                    await approval_queue.ajouter({
                        "type": "rupture_contrat",
                        "employe_id": params.get("employe_id"),
                        "motif": params.get("motif_rupture", action),
                        "indemnite_estimee": ind,
                        "montant": ind,
                        "user_id": user_id, "execution_id": execution_id,
                    })
                    return f"Procédure de rupture soumise — validation DG + Juridique requise. Indemnité estimée : {ind:,.0f} FCFA".replace(",", " ")

                return f"Action contrat '{action}' — traitement en cours"

            # ── RECRUTEMENT ──
            if nom == "gerer_recrutement":
                from core.orass_connector import orass
                action = params["action"]

                if action == "publier_offre":
                    from core.ia_client import ModeIA, ia_client
                    prompt = f"""Rédige une offre d'emploi attractive pour une compagnie d'assurance CIMA.
Poste : {params.get('poste')}
Profil requis : {params.get('profil_requis', 'À définir')}
Description mission : {params.get('description', '')}
Format : titre percutant, missions, profil, avantages, modalités candidature."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION)
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "offre_emploi",
                        "poste": params.get("poste"),
                        "offre_redigee": rep.contenu[:300],
                        "user_id": user_id, "execution_id": execution_id,
                    })
                    return f"Offre d'emploi rédigée — soumise pour validation DRH avant publication\n\n{rep.contenu}"

                if action == "scorer_cv":
                    from core.ia_client import ModeIA, ia_client
                    from core.ocr_processor import ocr_processor
                    cv_text = ""
                    if params.get("cv_base64"):
                        cv_text = await ocr_processor.analyser_document(params["cv_base64"], "cv")
                    prompt = f"""Analyse ce CV pour le poste de {params.get('poste', 'N/D')}.
CV : {cv_text}
Profil requis : {params.get('profil_requis', '')}
Évalue : adéquation poste (0-10), expérience assurance, compétences clés, points forts/faibles, recommandation (OUI/NON/PEUT-ÊTRE)."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                    return rep.contenu

                if action == "embaucher":
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "embauche_candidat",
                        "candidat_id": params.get("candidat_id"),
                        "poste": params.get("poste"),
                        "user_id": user_id, "execution_id": execution_id,
                    })
                    return f"Décision d'embauche soumise pour validation DRH — candidat {params.get('candidat_id')}"

                if action == "onboarding":
                    from core.ia_client import ModeIA, ia_client
                    prompt = f"""Génère un plan d'onboarding complet pour un nouveau collaborateur.
Poste : {params.get('poste')}
Date d'entrée : {params.get('date_entretien', 'À définir')}
Inclure : J1-J7, J8-J30, J31-J90 — activités, formations, rencontres clés, objectifs premier mois."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION)
                    return rep.contenu

                # lister_candidats / planifier_entretien / evaluer_candidat
                if action == "lister_candidats":
                    data = await orass.get_candidats(poste=params.get("poste"))
                    return json.dumps(data, ensure_ascii=False, default=str)
                if action == "planifier_entretien":
                    await orass.planifier_entretien(
                        candidat_id=params.get("candidat_id"),
                        date_entretien=params.get("date_entretien"),
                    )
                    return f"Entretien planifié le {params.get('date_entretien')} — candidat {params.get('candidat_id')}"
                if action == "evaluer_candidat":
                    await orass.evaluer_candidat(
                        candidat_id=params.get("candidat_id"),
                        note=params.get("note"),
                        commentaire=params.get("commentaire"),
                    )
                    return f"Évaluation enregistrée — candidat {params.get('candidat_id')} : {params.get('note')}/10"
                return "Action recrutement non reconnue"

            # ── FORMATION ──
            if nom == "gerer_formation":
                from core.orass_connector import orass
                action = params["action"]

                if action == "plan_annuel":
                    from core.ia_client import ModeIA, ia_client
                    besoins = await orass.get_besoins_formation(departement=params.get("departement"))
                    prompt = f"""Génère le plan de formation annuel {params.get('annee', date.today().year)} pour {params.get('departement', 'toute la compagnie')}.
Besoins identifiés : {json.dumps(besoins, ensure_ascii=False)}
Inclure : formations réglementaires CIMA obligatoires, priorités métier, budget estimé, calendrier trimestriel."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                    return rep.contenu

                if action == "certifications_reglementaires":
                    return json.dumps({
                        "certifications_obligatoires": [
                            {"titre": "Certification CIMA — Souscription Non-Vie", "periodicite": "Tous les 2 ans", "cible": "Souscripteurs"},
                            {"titre": "Certification CIMA — Gestion Sinistres", "periodicite": "Tous les 2 ans", "cible": "Gestionnaires sinistres"},
                            {"titre": "LCB/FT — Anti-blanchiment", "periodicite": "Annuelle", "cible": "Tous"},
                            {"titre": "Protection données clients CIMA", "periodicite": "Annuelle", "cible": "Tous"},
                            {"titre": "Certif. Actuariat — Calcul provisions", "periodicite": "Tous les 3 ans", "cible": "Actuaires"},
                        ]
                    }, ensure_ascii=False)

                if action == "inscrire":
                    await orass.inscrire_formation(
                        employe_id=params.get("employe_id"),
                        formation_id=params.get("formation_id"),
                    )
                    return f"Employé {params.get('employe_id')} inscrit à la formation {params.get('formation_id')}"
                if action == "valider":
                    await orass.valider_formation(
                        employe_id=params.get("employe_id"),
                        formation_id=params.get("formation_id"),
                    )
                    return "Completion formation validée"
                if action == "lister_catalogue":
                    data = await orass.get_formations(departement=params.get("departement"))
                    return json.dumps(data, ensure_ascii=False, default=str)
                return "Action formation non reconnue"

            # ── ÉVALUATION ──
            if nom == "evaluer_performance":
                mode       = params.get("mode", "calculer_score")
                objectifs  = params.get("objectifs", [])
                realisations = params.get("realisations", [])

                if mode == "calculer_score":
                    if not objectifs:
                        return json.dumps({"score": 0, "message": "Aucun objectif défini"})
                    scores = []
                    for obj in objectifs:
                        cible   = obj.get("cible", 1)
                        realise = next((r.get("valeur", 0) for r in realisations if r.get("id") == obj.get("id")), 0)
                        scores.append(min(1.2, realise / cible if cible else 0) * obj.get("poids", 1))
                    score_g = round(sum(scores) / len(objectifs) * 100, 1)
                    mention = ("Excellent" if score_g >= 90 else "Très bien" if score_g >= 75
                               else "Bien" if score_g >= 60 else "Satisfaisant" if score_g >= 50 else "Insuffisant")
                    return json.dumps({"employe_id": params["employe_id"], "score_global": score_g,
                                       "mention": mention, "periode": params["periode"]}, ensure_ascii=False)

                if mode in ("rapport_ia", "decision_rh"):
                    from core.ia_client import ModeIA, ia_client
                    prompt = f"""Rédige le rapport d'évaluation annuelle pour l'employé {params['employe_id']} — {params['periode']}.
Objectifs : {json.dumps(objectifs, ensure_ascii=False)}
Réalisations : {json.dumps(realisations, ensure_ascii=False)}
Structure : synthèse performance, points forts, axes amélioration, {'recommandation RH (promotion/maintien/PIR/départ)' if mode == 'decision_rh' else 'feedback constructif'}."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    if mode == "decision_rh":
                        from core.approval_queue import approval_queue
                        await approval_queue.ajouter({
                            "type": "decision_rh_evaluation",
                            "employe_id": params["employe_id"],
                            "rapport_resume": rep.contenu[:400],
                            "user_id": user_id, "execution_id": execution_id,
                        })
                        return f"Rapport d'évaluation soumis pour validation DRH\n\n{rep.contenu}"
                    return rep.contenu
                return "Mode évaluation non reconnu"

            # ── DISCIPLINAIRE ──
            if nom == "gerer_disciplinaire":
                from core.ia_client import ModeIA, ia_client
                sanction   = params["type_sanction"]
                emp_id     = params["employe_id"]
                is_grave   = "licenciement" in sanction

                prompt = f"""Rédige une {'lettre de licenciement' if is_grave else 'notification disciplinaire'} professionnelle.
Employé : {emp_id}
Sanction : {sanction.replace('_', ' ')}
Faits : {params['faits']}
Date des faits : {params.get('date_faits', 'N/D')}
Conforme au Code du Travail Cameroun et OHADA. Inclure les voies de recours."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)

                if is_grave:
                    sal = params.get("salaire_brut", 0)
                    anc = params.get("anciennete_ans", 0)
                    ind = _indemnite_licenciement(sal, anc) if sanction != "licenciement_faute_grave" else 0
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "sanction_disciplinaire_grave",
                        "employe_id": emp_id, "sanction": sanction,
                        "faits_resume": params["faits"][:200],
                        "indemnite_estimee": ind, "montant": ind,
                        "lettre_redigee": rep.contenu[:400],
                        "user_id": user_id, "execution_id": execution_id,
                    })
                    return f"Procédure {sanction} rédigée — soumise pour validation DG + Juridique\n\n{rep.contenu}"

                # Avertissements — validation RH hiérarchique
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "avertissement_rh",
                    "employe_id": emp_id, "sanction": sanction,
                    "faits_resume": params["faits"][:200],
                    "user_id": user_id, "execution_id": execution_id,
                })
                return f"Notification {sanction} rédigée — soumise pour validation responsable\n\n{rep.contenu}"

            # ── POINTAGE ──
            if nom == "gerer_pointage":
                from core.orass_connector import orass
                action = params["action"]
                if action == "enregistrer_pointage":
                    # Présenter pour validation avant enregistrement
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "pointage_employe",
                        "employe_id": params["employe_id"],
                        "date": params.get("date"),
                        "heure_entree": params.get("heure_entree"),
                        "heure_sortie": params.get("heure_sortie"),
                        "user_id": user_id, "execution_id": execution_id,
                    })
                    return f"Pointage {params.get('date')} soumis pour validation"
                if action in ("relever_absences", "heures_supp_mois", "rapport_retards"):
                    data = await orass.get_pointage(
                        employe_id=params["employe_id"],
                        action=action,
                        mois=params.get("mois"), annee=params.get("annee"),
                    )
                    return json.dumps(data, ensure_ascii=False, default=str)
                return f"Action pointage '{action}' non reconnue"

            # ── DÉCLARATIONS SOCIALES ──
            if nom == "declarations_sociales":
                type_d = params["type_declaration"]
                annee  = params["annee"]
                if type_d == "bordereau_cnps":
                    from core.orass_connector import orass
                    employes = await orass.get_employes()
                    total_sal  = sum(e.get("salaire_base", 0) for e in employes)
                    cnps_sal   = round(min(total_sal, PLAFOND_CNPS * len(employes)) * CNPS_SALARIE)
                    cnps_pat   = round(min(total_sal, PLAFOND_CNPS * len(employes)) * CNPS_PATRONAL)
                    bordereau  = {
                        "type": "Bordereau CNPS",
                        "periode": f"{params.get('mois', '01')}/{annee}",
                        "nb_employes": len(employes),
                        "masse_salariale": total_sal,
                        "cnps_salarie": cnps_sal,
                        "cnps_patronal": cnps_pat,
                        "total_a_verser": cnps_sal + cnps_pat,
                    }
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "declaration_cnps",
                        "bordereau": bordereau, "montant": cnps_sal + cnps_pat,
                        "user_id": user_id, "execution_id": execution_id,
                    })
                    return json.dumps(bordereau | {"statut": "soumis_validation_avant_depot"}, ensure_ascii=False)
                return json.dumps({"type": type_d, "periode": f"{params.get('mois', '01')}/{annee}",
                                   "message": "À traiter selon les formulaires CNPS en vigueur"}, ensure_ascii=False)

            # ── ACCIDENTS TRAVAIL ──
            if nom == "declarer_accident_travail":
                from core.approval_queue import approval_queue
                gravite = params["gravite"]
                await approval_queue.ajouter({
                    "type": "accident_travail",
                    "employe_id": params["employe_id"],
                    "date_accident": params["date_accident"],
                    "description": params["description"],
                    "gravite": gravite,
                    "jours_arret": params.get("jours_arret", 0),
                    "user_id": user_id, "execution_id": execution_id,
                })
                return (
                    f"Accident de travail {gravite} déclaré — soumis pour validation et transmission CNPS\n"
                    f"Employé : {params['employe_id']} — Date : {params['date_accident']}\n"
                    f"Délai légal déclaration CNPS : 72h"
                )

            # ── PLANNING ──
            if nom == "planning_equipe":
                from core.orass_connector import orass
                data = await orass.get_planning(
                    departement=params["departement"],
                    date_debut=params.get("date_debut"),
                    date_fin=params.get("date_fin"),
                    vue=params.get("vue", "absences"),
                )
                return json.dumps(data, ensure_ascii=False, default=str)

            # ── NOTIFICATIONS ──
            if nom == "notifier_employe":
                from core.orass_connector import orass
                from core.notifications import notifications
                emp = await orass.get_employe(params["employe_id"])
                tel = emp.get("telephone", "")
                if tel:
                    await notifications.envoyer(
                        canal="whatsapp", destinataire=tel, message=params["message"],
                    )
                return f"Notification '{params['type_notif']}' envoyée à {params['employe_id']}"

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentRH] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
