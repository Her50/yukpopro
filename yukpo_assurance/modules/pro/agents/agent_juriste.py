"""
AgentJuriste — Agent IA spécialisé pour les juristes et avocats africains.

Outils métier :
  - contrat_rediger        : Rédaction / analyse de contrats commerciaux OHADA
  - acte_constitutif       : Création / modification de sociétés (SARL, SA, SAS…)
  - contentieux_analyser   : Stratégie procédurale et analyse des risques contentieux
  - reglementation_verifier: Vérification de conformité réglementaire
  - modele_juridique       : Modèles d'actes courants (mise en demeure, procuration…)

Référentiels :
  - Actes Uniformes OHADA (AUSCGIE, AUDCG, AUS, AUPSRVE, AUPDC…)
  - Codes de commerce, codes civils nationaux
  - Droit des contrats africain
  - Droit de l'arbitrage (OHADA, CIRDI)

PATTERNS YUKPOASSURANCE :
  - Fonctions déterministes standalone (hors classe)
  - type_agent = TypeAgent.PRO_JURISTE
  - _necessite_validation() → hérité de AgentProBase (False)
  - _prompt_questions_specifiques() implémenté
"""
from __future__ import annotations

import logging

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_juriste")


# ══════════════════════════════════════════════════════════════════════════════
# Constantes OHADA
# ══════════════════════════════════════════════════════════════════════════════

# Formes sociales OHADA (AUSCGIE)
_FORMES_SOCIALES: dict[str, dict] = {
    "sarl": {
        "label":          "SARL — Société à Responsabilité Limitée",
        "capital_min":     1,        # OHADA : 1 FCFA depuis 2014
        "associes_min":    1,
        "associes_max":    50,
        "organes":        ["assemblée générale des associés", "gérant(s)"],
        "ref_ohada":      "AUSCGIE art. 309-383",
    },
    "sa": {
        "label":          "SA — Société Anonyme",
        "capital_min":     10_000_000,
        "associes_min":    1,        # SA unipersonnelle depuis 2014
        "associes_max":    None,
        "organes":        ["assemblée générale", "conseil d'administration ou administrateur général", "commissaires aux comptes"],
        "ref_ohada":      "AUSCGIE art. 385-853",
    },
    "sas": {
        "label":          "SAS — Société par Actions Simplifiée",
        "capital_min":     1,
        "associes_min":    1,
        "associes_max":    None,
        "organes":        ["assemblée des actionnaires", "président"],
        "ref_ohada":      "AUSCGIE art. 853-1 à 853-23 (réforme 2014)",
    },
    "snc": {
        "label":          "SNC — Société en Nom Collectif",
        "capital_min":     0,
        "associes_min":    2,
        "associes_max":    None,
        "organes":        ["associés gérants"],
        "ref_ohada":      "AUSCGIE art. 270-308",
    },
    "gi": {
        "label":          "GIE — Groupement d'Intérêt Économique",
        "capital_min":     0,
        "associes_min":    2,
        "associes_max":    None,
        "organes":        ["administrateur(s)"],
        "ref_ohada":      "AUSCGIE art. 869-882",
    },
}

# Délais procéduraux indicatifs (jours)
_DELAIS_PROC = {
    "mise_en_demeure":   15,   # délai de grâce minimum en FCFA
    "appel":             30,
    "pourvoi_cassation": 60,
    "arbitrage_cci":     180,
    "ccja_delai":        120,  # CCJA OHADA
}

# Clauses essentielles par type de contrat
_CLAUSES_ESSENTIELLES: dict[str, list[str]] = {
    "vente":        ["identification des parties", "description du bien", "prix et modalités de paiement",
                     "transfert de propriété", "garanties", "réserve de propriété", "juridiction"],
    "prestation":   ["identification des parties", "description des services", "délais d'exécution",
                     "rémunération", "obligations des parties", "propriété intellectuelle",
                     "responsabilité", "résiliation", "confidentialité"],
    "bail":         ["identification des parties", "description du local", "durée", "loyer et charges",
                     "dépôt de garantie", "état des lieux", "usage", "travaux", "résiliation"],
    "distribution": ["territoire exclusif", "objectifs de vente", "prix de revente",
                     "stocks minimum", "formation", "durée", "non-concurrence"],
    "partenariat":  ["objet", "apports des parties", "gouvernance", "partage des revenus",
                     "propriété intellectuelle", "durée", "exclusivité", "sortie"],
}


# ══════════════════════════════════════════════════════════════════════════════
# Fonctions standalone
# ══════════════════════════════════════════════════════════════════════════════

def _analyser_contrat(
    type_contrat: str,
    contenu:      str | None,
    action:       str,
    parties:      dict,
    pays:         str,
) -> str:
    """Analyse ou vérifie les clauses essentielles d'un contrat."""
    clauses = _CLAUSES_ESSENTIELLES.get(type_contrat.lower(), _CLAUSES_ESSENTIELLES["prestation"])

    lignes = [f"ANALYSE CONTRAT {type_contrat.upper()} — {pays}\n"]

    if action == "verifier" and contenu:
        lignes.append("VÉRIFICATION DES CLAUSES ESSENTIELLES :\n")
        for clause in clauses:
            present = clause.lower() in contenu.lower()
            icone   = "✅" if present else "❌"
            lignes.append(f"  {icone} {clause.capitalize()}")
        manquantes = [c for c in clauses if c.lower() not in (contenu or "").lower()]
        if manquantes:
            lignes.append(f"\n⚠️  CLAUSES MANQUANTES ({len(manquantes)}) :")
            for c in manquantes:
                lignes.append(f"   - {c}")
        lignes.append("\nRISQUES JURIDIQUES POTENTIELS :")
        lignes.append("  - Contrat incomplet pouvant être requalifié ou annulé")
        lignes.append("  - Absence de clause de résiliation = résiliation judiciaire uniquement")

    elif action == "rediger":
        lignes.append("STRUCTURE DE CONTRAT RECOMMANDÉE :\n")
        lignes.append("PRÉAMBULE")
        lignes.append("   • Contexte et intentions des parties\n")
        for i, clause in enumerate(clauses, 1):
            lignes.append(f"ARTICLE {i}. {clause.upper()}")
            lignes.append(f"   [Rédaction personnalisée selon vos spécificités]\n")
        lignes.append("ARTICLE FINAL. JURIDICTION ET LOI APPLICABLE")
        lignes.append(f"   Tribunal compétent : Tribunal de Commerce de [Ville] ({pays})")
        lignes.append(f"   Loi applicable : droit {pays} et Actes Uniformes OHADA\n")
        lignes.append("⚠️  Ce modèle est indicatif. Faire rédiger par un juriste qualifié.")

    elif action == "analyser" and contenu:
        lignes.append("POINTS D'ATTENTION IDENTIFIÉS :\n")
        risques = [
            ("résiliation", "Vérifier les conditions et délais de résiliation"),
            ("responsabilité", "S'assurer du plafonnement de responsabilité"),
            ("clause compromissoire", "Arbitrage ou juridiction étatique ?"),
            ("force majeure",  "Définition et procédure en cas de force majeure"),
            ("pénalités",      "Proportionnalité des pénalités (risque annulation)"),
        ]
        for mot, conseil in risques:
            present = mot in (contenu or "").lower()
            icone   = "✅" if present else "⚠️ "
            lignes.append(f"  {icone} {mot.capitalize()} : {conseil}")

    return "\n".join(lignes)


def _constituer_societe(forme: str, params: dict, pays: str) -> str:
    """Guide la constitution d'une société OHADA."""
    info   = _FORMES_SOCIALES.get(forme.lower(), _FORMES_SOCIALES["sarl"])
    capital = float(params.get("capital", 0))

    lignes = [f"CONSTITUTION {info['label']} — {pays}\n"]

    # Vérifications de base
    if info["capital_min"] > 0 and capital < info["capital_min"]:
        lignes.append(f"⚠️  Capital insuffisant : minimum {info['capital_min']:,} FCFA "
                      f"({info['ref_ohada']})\n")

    nb_associes = int(params.get("nb_associes", 1))
    if nb_associes < info["associes_min"]:
        lignes.append(f"⚠️  Nombre d'associés insuffisant : minimum {info['associes_min']}\n")
    if info["associes_max"] and nb_associes > info["associes_max"]:
        lignes.append(f"⚠️  Trop d'associés : maximum {info['associes_max']} pour une {forme.upper()}\n")

    lignes += [
        "ÉTAPES DE CONSTITUTION :\n",
        "1. RÉDACTION DES STATUTS",
        "   - Objet social précis (éviter les objets trop larges)",
        "   - Répartition des parts / actions",
        "   - Modalités de prise de décision",
        f"   - Organes : {', '.join(info['organes'])}\n",
        "2. LIBÉRATION DU CAPITAL",
        "   - Ouverture compte bancaire bloqué",
        "   - Dépôt du capital libéré (intégral pour SA, 1/4 minimum pour SARL)",
        "   - Attestation de dépôt de la banque\n",
        "3. FORMALITÉS D'IMMATRICULATION",
        "   - Dépôt au greffe du Tribunal de Commerce",
        "   - Immatriculation au RCCM (Registre du Commerce et du Crédit Mobilier)",
        "   - Publication au Journal Officiel / Annonce légale",
        "   - Obtention du NIU (Numéro d'Identifiant Unique) — administration fiscale",
        "   - CNPS si salariés prévus\n",
        "4. OUVERTURE COMPTE BANCAIRE COURANT",
        "   - Présenter extrait RCCM + statuts + carte dirigeant\n",
        f"Référence OHADA : {info['ref_ohada']}",
        f"\nDÉLAI MOYEN D'IMMATRICULATION : 3-7 jours ouvrables ({pays})",
        "\n⚠️  Faire établir les statuts par un notaire ou juriste qualifié.",
    ]
    return "\n".join(lignes)


def _analyser_contentieux(
    type_litige: str,
    faits:       str,
    montant:     float,
    anciennete:  float,
    pays:        str,
) -> str:
    """Analyse la stratégie procédurale et les risques contentieux."""
    lignes = [f"ANALYSE CONTENTIEUX — {type_litige.upper()} ({pays})\n"]

    # Prescription
    prescriptions = {
        "commercial": 5, "civil": 10, "travail": 2,
        "penal": 3, "fiscal": 3, "administratif": 4,
    }
    prescrip = prescriptions.get(type_litige.lower(), 5)
    if anciennete > prescrip:
        lignes.append(f"⚠️  RISQUE DE PRESCRIPTION : {anciennete:.0f} ans > {prescrip} ans ({type_litige})")
        lignes.append("   Vérifier d'urgence les causes d'interruption/suspension\n")
    else:
        lignes.append(f"✅ Délai de prescription : {prescrip} ans — {prescrip - anciennete:.0f} an(s) restant(s)\n")

    # Stratégie
    lignes += [
        "STRATÉGIE PROCÉDURALE RECOMMANDÉE :\n",
        "1. PHASE AMIABLE (obligatoire dans de nombreuses juridictions OHADA)",
        "   - Mise en demeure formelle (délai : 15 jours minimum)",
        "   - Tentative de médiation / conciliation",
        "   - Documentation : conserver toutes preuves écrites\n",
    ]

    if montant > 0 and montant < 10_000_000:
        lignes += [
            "2. VOIES DE RECOURS (montant < 10 M FCFA)",
            "   - Tribunal de première instance (compétence générale)",
            "   - Procédure d'injonction de payer (OHADA, AUS art. 1-30) — rapide et peu coûteuse",
        ]
    elif montant >= 10_000_000:
        lignes += [
            "2. VOIES DE RECOURS (montant ≥ 10 M FCFA)",
            "   - Tribunal de Commerce si matière commerciale",
            "   - Arbitrage CCJA ou CCI (recommandé pour litiges B2B importants)",
            f"   - Délai arbitrage estimé : {_DELAIS_PROC['ccja_delai']} jours",
        ]

    lignes += [
        "\n3. PREUVES À CONSTITUER D'URGENCE :",
        "   - Contrat signé / correspondances écrites",
        "   - Factures, relevés bancaires, bons de commande",
        "   - Constats d'huissier si nécessaire",
        "   - Témoignages formalisés\n",
        "4. RISQUES FINANCIERS :",
    ]
    if montant > 0:
        provision = montant * 0.30  # provision prudentielle 30%
        lignes.append(f"   - Provision conseillée : {provision:,.0f} FCFA (30% du montant litigieux)")
    lignes.append("   - Frais d'avocat : variable (prévoir honoraires de diligences)")
    lignes.append("   - Durée procédure : 18-36 mois en moyenne en Afrique francophone")
    lignes.append("\n⚠️  Cette analyse est indicative. Consulter un avocat inscrit au barreau local.")

    return "\n".join(lignes)


def _verifier_conformite(
    domaine:  str,
    activite: str,
    pays:     str,
    elements: list[str],
) -> str:
    """Vérifie la conformité réglementaire d'une activité."""
    lignes = [f"VÉRIFICATION CONFORMITÉ — {domaine.upper()} ({pays})\n"]

    # Obligations communes OHADA
    obligations_ohada = [
        ("Immatriculation RCCM",              "AUDCG art. 25 — obligatoire pour tout commerçant"),
        ("Livres de commerce",                "AUDCG art. 13 — registre journalier et livre inventaire"),
        ("Comptes annuels",                   "AUSCGIE — dépôt au greffe dans 4 mois de la clôture"),
        ("Déclaration d'existence fiscale",   "CGI local — dans 30 jours de la création"),
        ("Assurance responsabilité civile",   "Selon secteur — souvent obligatoire"),
    ]

    lignes.append("OBLIGATIONS OHADA GÉNÉRALES :")
    for obligation, ref in obligations_ohada:
        fourni = any(obligation.lower()[:10] in el.lower() for el in elements)
        icone  = "✅" if fourni else "☐"
        lignes.append(f"  {icone} {obligation:<40} ({ref})")

    # Obligations spécifiques par domaine
    specifiques: dict[str, list[tuple[str, str]]] = {
        "banque":    [("Agrément COBAC/BCEAO", "Réglementation bancaire UMAC/UEMOA"),
                      ("Capital minimum réglementaire", "Circulaire COBAC")],
        "assurance": [("Agrément CIMA", "Code CIMA art. 306"), ("Capital minimum 1 Md FCFA", "CIMA")],
        "import":    [("Agrément importateur", "Code des douanes"), ("Registre d'importateur", "Douanes")],
        "btp":       [("Registre entreprise BTP", "Code BTP local"), ("Attestation technique", "Ordre des ingénieurs")],
        "sante":     [("Autorisation d'exercice", "Code de la santé"), ("Inscription Ordre médical", "Loi santé")],
    }

    extras = specifiques.get(domaine.lower(), [])
    if extras:
        lignes.append(f"\nOBLIGATIONS SPÉCIFIQUES {domaine.upper()} :")
        for obl, ref in extras:
            lignes.append(f"  ☐ {obl:<40} ({ref})")

    lignes.append("\n⚠️  Cette liste est indicative. Les exigences varient par pays et sont sujettes à révision.")
    return "\n".join(lignes)


def _generer_modele(type_acte: str, params: dict) -> str:
    """Génère un modèle d'acte juridique courant."""
    destinataire = params.get("destinataire", "[NOM DESTINATAIRE]")
    objet        = params.get("objet",        "[Objet de l'acte]")
    montant      = float(params.get("montant", 0))
    delai        = int(params.get("delai_jours", 15))
    expediteur   = params.get("expediteur",   "[NOM EXPÉDITEUR]")
    ville        = params.get("ville",        "[Ville]")

    if type_acte == "mise_en_demeure":
        lignes = [
            f"LETTRE DE MISE EN DEMEURE\n",
            f"À {destinataire}\n",
            f"Objet : Mise en demeure — {objet}\n",
            f"Madame/Monsieur,\n",
            "Par la présente, nous vous mettons en demeure de :",
        ]
        if montant > 0:
            lignes.append(f"  - Régler la somme de {montant:,.0f} FCFA FCFA qui nous est due au titre de {objet}")
        else:
            lignes.append(f"  - Exécuter vos obligations contractuelles relatives à : {objet}")
        lignes += [
            f"\nCe, dans un délai de {delai} jours à compter de la réception de la présente,",
            "faute de quoi nous nous verrons contraints d'engager toute procédure judiciaire",
            "que nous estimerions utile pour la défense de nos droits, dont les frais resteraient",
            "entièrement à votre charge.\n",
            "Nous demeurons à votre disposition pour tout règlement amiable.\n",
            f"Fait à {ville}, le [DATE]\n",
            f"{expediteur}",
            "\n⚠️  Envoyer par LRAR ou remise contre récépissé pour valeur probante.",
        ]

    elif type_acte == "procuration":
        lignes = [
            "PROCURATION GÉNÉRALE / SPÉCIALE\n",
            "Je soussigné(e), [MANDANT — Nom, prénom, qualité, domicile]\n",
            "donne par la présente pouvoir à [MANDATAIRE — Nom, prénom, qualité],\n",
            "à l'effet de me représenter et d'agir en mon nom pour :",
            f"  {objet}\n",
            "À cet effet, le mandataire pourra accomplir tous actes nécessaires",
            "à l'exécution du présent mandat.\n",
            "La présente procuration est valable jusqu'au [DATE EXPIRATION]",
            "sauf révocation expresse anticipée.\n",
            f"Fait à {ville}, le [DATE]\n",
            "Signature du mandant : _______________",
            "\nVu pour légalisation de signature : [Autorité compétente]",
        ]

    elif type_acte == "reconnaissance_dette":
        lignes = [
            "RECONNAISSANCE DE DETTE\n",
            "Je soussigné(e), [DÉBITEUR — Nom, prénom, domicile],\n",
            f"reconnais devoir à {destinataire} (ci-après le Créancier),",
            f"la somme de {montant:,.0f} FCFA ({montant:,.0f} francs CFA),",
            f"au titre de : {objet}\n",
            f"Je m'engage à rembourser cette somme avant le [DATE ÉCHÉANCE],",
            "avec intérêts au taux de [TAUX]% l'an en cas de retard.\n",
            f"Fait à {ville}, le [DATE], en deux exemplaires originaux.\n",
            "Signature du débiteur : _______________",
        ]

    else:
        lignes = [
            f"MODÈLE {type_acte.upper()}\n",
            "Ce type d'acte nécessite une rédaction sur mesure.",
            "Éléments à inclure :",
            "  - Identification complète des parties",
            "  - Objet précis de l'acte",
            "  - Obligations de chaque partie",
            "  - Conditions de validité et date d'effet",
            "  - Signatures légalisées",
            "\n⚠️  Consulter un juriste ou notaire pour la rédaction.",
        ]

    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Classe AgentJuriste
# ══════════════════════════════════════════════════════════════════════════════

class AgentJuriste(AgentProBase):
    """Agent spécialisé Droit des affaires / Droit du travail africain."""

    type_agent = TypeAgent.PRO_JURISTE

    def _system_prompt(self) -> str:
        base = super()._system_prompt()
        return base + """

EXPERTISE JURIDIQUE :
Tu es un juriste d'affaires expert en droit OHADA et droit africain francophone.

COMPÉTENCES CLÉS :
- Droit des sociétés OHADA (AUSCGIE, AUDCG) : constitution, modifications, dissolution
- Droit des contrats : rédaction, négociation, analyse de risques
- Droit du travail africain : contrats, ruptures, droit disciplinaire
- Contentieux et arbitrage : stratégie procédurale, CCJA, CCI, arbitrage local
- Droit fiscal africain : conformité, optimisation fiscale licite
- Marchés publics : procédures ARMP, contrats État

ACTES UNIFORMES OHADA À MAÎTRISER :
- AUSCGIE : droit des sociétés et GIE
- AUDCG : droit commercial général (commerçants, fonds de commerce, bail commercial)
- AUS : sûretés (hypothèques, nantissements, cautionnements)
- AUPSRVE : procédures simplifiées et voies d'exécution
- AUPDC : procédures collectives d'apurement du passif (faillite, règlement préventif)
- AUA : arbitrage OHADA et CCJA

RÈGLES IMPORTANTES :
- Toujours citer les textes exacts (articles, Actes Uniformes, lois nationales)
- Distinguer le droit OHADA uniforme des dispositions nationales
- Souligner les risques juridiques et les sanctions applicables
- Recommander systématiquement de consulter un avocat pour les actes engageants
- Ne jamais donner de conseil juridique comme si tu étais avocat inscrit au barreau
"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "- Si le pays d'exercice est inconnu et pertinent : demander (impact droit national vs OHADA)\n"
            "- Si la forme sociale n'est pas précisée pour la création d'entreprise : "
            "demander (SARL, SA, SAS, SNC, GIE)\n"
            "- Si le type de litige ou montant est nécessaire à l'analyse : demander\n"
            "- Si l'analyse d'un contrat est demandée sans le texte : demander de le fournir\n"
            "- Ne jamais redemander les informations déjà dans le profil ou la conversation"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "contrat_rediger",
                "description": (
                    "Rédige ou analyse un contrat commercial selon le droit OHADA. "
                    "Actions : rediger (structure complète), verifier (clauses essentielles), "
                    "analyser (risques juridiques)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_contrat": {
                            "type": "string",
                            "description": "vente | prestation | bail | distribution | partenariat | autre",
                        },
                        "action": {
                            "type": "string",
                            "description": "rediger | verifier | analyser",
                        },
                        "contenu": {
                            "type": "string",
                            "description": "Texte du contrat à analyser ou vérifier",
                        },
                        "parties": {
                            "type": "object",
                            "description": "Parties impliquées (optionnel)",
                        },
                        "pays": {"type": "string"},
                    },
                    "required": ["type_contrat", "action"],
                },
            },
            {
                "name": "acte_constitutif",
                "description": (
                    "Guide la constitution ou modification d'une société OHADA : "
                    "SARL, SA, SAS, SNC, GIE. Indique les étapes, formalités et textes applicables."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "forme_sociale": {
                            "type": "string",
                            "description": "sarl | sa | sas | snc | gi",
                        },
                        "action": {
                            "type": "string",
                            "description": "constituer | modifier | dissoudre | transformer",
                        },
                        "capital":      {"type": "number",  "description": "Capital social en FCFA"},
                        "nb_associes":  {"type": "integer"},
                        "objet_social": {"type": "string"},
                        "pays":         {"type": "string"},
                    },
                    "required": ["forme_sociale", "action"],
                },
            },
            {
                "name": "contentieux_analyser",
                "description": (
                    "Analyse la stratégie procédurale d'un litige : prescription, "
                    "voies de recours, preuves à constituer, risques financiers."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_litige": {
                            "type": "string",
                            "description": "commercial | civil | travail | penal | fiscal | administratif",
                        },
                        "faits":       {"type": "string",  "description": "Description factuelle du litige"},
                        "montant":     {"type": "number",  "description": "Montant en jeu en FCFA"},
                        "anciennete":  {"type": "number",  "description": "Ancienneté du litige en années"},
                        "pays":        {"type": "string"},
                    },
                    "required": ["type_litige", "pays"],
                },
            },
            {
                "name": "reglementation_verifier",
                "description": (
                    "Vérifie la conformité réglementaire d'une activité ou entreprise : "
                    "obligations OHADA, formalités locales, licences requises."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "domaine": {
                            "type": "string",
                            "description": "commercial | banque | assurance | import | btp | sante | autre",
                        },
                        "activite": {
                            "type": "string",
                            "description": "Description de l'activité",
                        },
                        "pays": {"type": "string"},
                        "elements_existants": {
                            "type": "array",
                            "description": "Documents / autorisations déjà en possession",
                        },
                    },
                    "required": ["domaine", "pays"],
                },
            },
            {
                "name": "modele_juridique",
                "description": (
                    "Génère un modèle d'acte juridique courant : mise en demeure, "
                    "procuration, reconnaissance de dette, etc."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_acte": {
                            "type": "string",
                            "description": "mise_en_demeure | procuration | reconnaissance_dette | "
                                           "cession_parts | resiliation",
                        },
                        "destinataire": {"type": "string"},
                        "objet":        {"type": "string"},
                        "montant":      {"type": "number"},
                        "delai_jours":  {"type": "integer", "description": "Délai accordé (défaut 15j)"},
                        "expediteur":   {"type": "string"},
                        "ville":        {"type": "string"},
                    },
                    "required": ["type_acte"],
                },
            },
            {
                "name": "analyser_document_juridique",
                "description": (
                    "Analyse un document juridique soumis (contrat, jugement, assignation, "
                    "correspondance adverse) et identifie les risques et actions requises."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_document": {"type": "string", "description": "Texte du document juridique"},
                        "type_document": {"type": "string", "description": "contrat/jugement/assignation/lettre_adverse/statuts/pv_ag"},
                        "position": {"type": "string", "description": "demandeur/defendeur/conseil/tiers"},
                        "pays": {"type": "string"},
                    },
                    "required": ["contenu_document"],
                },
            },
            {
                "name": "orchestrer_mise_en_demeure",
                "description": (
                    "Orchestre le processus complet de mise en demeure : "
                    "rédaction, envoi, délais, escalade judiciaire si non-réponse."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "debiteur": {"type": "string"},
                        "objet_litige": {"type": "string"},
                        "montant": {"type": "number"},
                        "historique": {"type": "string", "description": "Historique des tentatives de règlement"},
                        "pays": {"type": "string"},
                    },
                    "required": ["debiteur", "objet_litige"],
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
        if nom == "contrat_rediger":
            return _analyser_contrat(
                type_contrat = params.get("type_contrat", "prestation"),
                contenu      = params.get("contenu"),
                action       = params.get("action", "verifier"),
                parties      = params.get("parties", {}),
                pays         = params.get("pays") or self._pays or "CM",
            )
        if nom == "acte_constitutif":
            return _constituer_societe(
                forme  = params.get("forme_sociale", "sarl"),
                params = params,
                pays   = params.get("pays") or self._pays or "CM",
            )
        if nom == "contentieux_analyser":
            return _analyser_contentieux(
                type_litige = params.get("type_litige", "commercial"),
                faits       = params.get("faits", ""),
                montant     = float(params.get("montant", 0)),
                anciennete  = float(params.get("anciennete", 0)),
                pays        = params.get("pays") or self._pays or "CM",
            )
        if nom == "reglementation_verifier":
            return _verifier_conformite(
                domaine  = params.get("domaine", "commercial"),
                activite = params.get("activite", ""),
                pays     = params.get("pays") or self._pays or "CM",
                elements = params.get("elements_existants", []),
            )
        if nom == "modele_juridique":
            return _generer_modele(params.get("type_acte", "mise_en_demeure"), params)

        if nom == "analyser_document_juridique":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_doc_juridique(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        if nom == "orchestrer_mise_en_demeure":
            return _orchestrer_mise_en_demeure(params)

        return f"[Outil '{nom}' non reconnu par AgentJuriste]"


# ---------------------------------------------------------------------------
# Fonctions standalone — nouvelles automatisations juriste
# ---------------------------------------------------------------------------

def _prompt_analyse_doc_juridique(params: dict) -> str:
    contenu = params.get("contenu_document", "")
    type_doc = params.get("type_document", "contrat")
    position = params.get("position", "conseil")
    pays = params.get("pays", "CM")

    types_labels = {
        "contrat": "contrat",
        "jugement": "jugement ou décision de justice",
        "assignation": "assignation en justice",
        "lettre_adverse": "courrier de la partie adverse",
        "statuts": "statuts de société",
        "pv_ag": "procès-verbal d'assemblée générale",
    }
    label = types_labels.get(type_doc, type_doc)

    return f"""Tu es un avocat d'affaires spécialisé en droit OHADA et droit africain ({pays}).

Analyse ce {label}. Notre position : **{position}**.

DOCUMENT :
{contenu}

ANALYSE REQUISE :
1. **Nature et portée** — ce que ce document établit juridiquement
2. **Obligations créées** — ce que chaque partie est tenue de faire / ne pas faire
3. **Droits et recours** — ce dont nous disposons
4. **Risques identifiés** — éléments pouvant nous être défavorables
5. **Vices ou irrégularités** — problèmes de forme ou fond pouvant invalider l'acte
6. **Délais critiques** — dates de prescription, délais de réponse, délais d'appel
7. **Actions immédiates recommandées** — ce que nous devons faire dans les 48h/7j/30j

Format : structuré, délais en gras, niveau d'urgence par action (IMMÉDIAT / URGENT / NORMAL)."""


def _orchestrer_mise_en_demeure(params: dict) -> str:
    from datetime import date, timedelta
    debiteur = params.get("debiteur", "le débiteur")
    objet = params.get("objet_litige", "l'objet du litige")
    montant = float(params.get("montant", 0))
    historique = params.get("historique", "")
    pays = params.get("pays", "CM")

    aujourd_hui = date.today()
    j15 = aujourd_hui + timedelta(days=15)
    j30 = aujourd_hui + timedelta(days=30)
    j45 = aujourd_hui + timedelta(days=45)

    lignes = [
        f"## Workflow Mise en Demeure — {debiteur}",
        f"Objet : {objet}",
        f"Montant : {montant:,.0f} FCFA" if montant > 0 else "",
        f"Pays : {pays}",
        f"Historique : {historique}" if historique else "",
        "",
        f"### Étape 1 — Mise en demeure formelle ({aujourd_hui.strftime('%d/%m/%Y')})",
        "  ✅ Rédiger lettre de mise en demeure (utiliser outil modele_juridique → mise_en_demeure)",
        "  ✅ Envoyer par lettre recommandée avec accusé de réception",
        "  ✅ Envoyer copie par email (preuve complémentaire)",
        f"  ✅ Délai accordé au débiteur : 15 jours (jusqu'au {j15.strftime('%d/%m/%Y')})",
        "  ✅ Archiver l'accusé de réception dès réception",
        "",
        f"### Étape 2 — Sans réponse au {j15.strftime('%d/%m/%Y')}",
        "  📋 Envoyer un rappel + copie avocat en copie visible",
        "  📋 Tenter règlement amiable / médiation si relation commerciale à préserver",
        "  📋 Constituer le dossier de preuve (contrats, factures, échanges)",
        "",
        f"### Étape 3 — Procédure judiciaire (à partir du {j30.strftime('%d/%m/%Y')})",
    ]

    if pays == "CM":
        lignes += [
            "  ⚖️ Options procédurales (Cameroun) :",
            "    • Injonction de payer (AUPSRVE OHADA) — rapide, peu coûteux",
            "    • Assignation en référé d'urgence si urgence",
            "    • Saisie conservatoire sur comptes bancaires",
        ]
    elif pays == "CI":
        lignes += [
            "  ⚖️ Options procédurales (Côte d'Ivoire) :",
            "    • Requête en injonction de payer (CCJA / TPI Abidjan)",
            "    • Saisie-attribution de créances",
        ]
    else:
        lignes += [
            "  ⚖️ Options procédurales (OHADA) :",
            "    • Injonction de payer — Acte Uniforme OHADA sur voies d'exécution",
            "    • Saisie-attribution ou saisie-vente selon actifs disponibles",
        ]

    lignes += [
        "",
        f"### Étape 4 — Exécution forcée ({j45.strftime('%d/%m/%Y')} et après)",
        "  ✅ Signification du titre exécutoire par huissier",
        "  ✅ Saisie des avoirs identifiés",
        "  ✅ Récupération des fonds + frais de justice",
        "",
        f"⚠️ Prescription action en paiement (OHADA) : 5 ans — ne pas attendre.",
    ]
    return "\n".join(l for l in lignes if l is not None)
