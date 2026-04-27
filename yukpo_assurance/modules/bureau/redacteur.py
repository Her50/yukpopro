"""
Bureau Rédacteur — Génération IA de documents administratifs et professionnels.

30+ types de documents calibrés pour l'administration africaine francophone :
style OHADA, administrations CM/SN/CI/TG, registre formel attendu.
Export .docx via python-docx. Calculateur de prix selon complexité.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("yukpo_assurance.bureau.redacteur")

# ─── Catalogue des types de documents ────────────────────────────────────────

TYPES_DOCUMENTS: dict[str, dict] = {
    # Administration générale
    "lettre_administrative": {
        "label": "Lettre administrative",
        "categorie": "administration",
        "complexite": 1,
        "prix_base_fcfa": 500,
        "description": "Lettre formelle à une administration publique",
        "style": "Ton officiel, objet en majuscules, formule de politesse complète OHADA",
    },
    "demande_emploi": {
        "label": "Lettre de demande d'emploi",
        "categorie": "emploi",
        "complexite": 2,
        "prix_base_fcfa": 800,
        "description": "Lettre de motivation adaptée au marché africain francophone",
        "style": "Ton professionnel, accroche directe, valorisation expérience locale",
    },
    "cv": {
        "label": "Curriculum Vitae",
        "categorie": "emploi",
        "complexite": 3,
        "prix_base_fcfa": 2000,
        "description": "CV structuré selon les standards camerounais/CEMAC",
        "style": "Format chronologique inverse, compétences en tête, références locales",
    },
    "contrat_travail": {
        "label": "Contrat de travail",
        "categorie": "juridique",
        "complexite": 4,
        "prix_base_fcfa": 3000,
        "description": "Contrat conforme au Code du travail camerounais",
        "style": "Clauses CNPS, période d'essai légale, durée déterminée/indéterminée",
    },
    "contrat_prestation": {
        "label": "Contrat de prestation de services",
        "categorie": "juridique",
        "complexite": 3,
        "prix_base_fcfa": 2500,
        "description": "Contrat B2B conforme au droit OHADA",
        "style": "Objet précis, livrables, délais, pénalités, juridiction OHADA",
    },
    "rapport_stage": {
        "label": "Rapport de stage",
        "categorie": "academique",
        "complexite": 4,
        "prix_base_fcfa": 3500,
        "description": "Rapport académique selon normes universitaires africaines",
        "style": "Introduction, organisation d'accueil, missions, bilan, perspectives",
    },
    "memoire_partie": {
        "label": "Partie de mémoire / TFE",
        "categorie": "academique",
        "complexite": 5,
        "prix_base_fcfa": 5000,
        "description": "Rédaction d'une section de mémoire universitaire",
        "style": "Vocabulaire académique, citations APA, plan thématique rigoureux",
    },
    "attestation_travail": {
        "label": "Attestation de travail",
        "categorie": "rh",
        "complexite": 1,
        "prix_base_fcfa": 300,
        "description": "Attestation employeur pour un salarié",
        "style": "Format court, référence légale, cachet employeur",
    },
    "attestation_stage": {
        "label": "Attestation de stage",
        "categorie": "rh",
        "complexite": 1,
        "prix_base_fcfa": 300,
        "description": "Attestation de fin de stage pour étudiant",
        "style": "Données stagiaire, période, service d'accueil",
    },
    "pv_reunion": {
        "label": "Procès-verbal de réunion",
        "categorie": "administration",
        "complexite": 2,
        "prix_base_fcfa": 800,
        "description": "PV officiel conforme aux pratiques africaines",
        "style": "Ordre du jour, présents, délibérations, résolutions, signatures",
    },
    "pv_ag": {
        "label": "Procès-verbal d'Assemblée Générale",
        "categorie": "juridique",
        "complexite": 4,
        "prix_base_fcfa": 4000,
        "description": "PV AG conforme à l'Acte Uniforme OHADA sur les sociétés",
        "style": "AUSCGIE Art. 133+, quorum, vote, résolutions numérotées, mention légale",
    },
    "procuration": {
        "label": "Procuration",
        "categorie": "juridique",
        "complexite": 2,
        "prix_base_fcfa": 1000,
        "description": "Acte de délégation de pouvoir",
        "style": "Mandant/mandataire, étendue des pouvoirs, durée, légalisation",
    },
    "mise_en_demeure": {
        "label": "Mise en demeure",
        "categorie": "juridique",
        "complexite": 3,
        "prix_base_fcfa": 2000,
        "description": "Lettre de mise en demeure avec valeur légale",
        "style": "Référence légale, délai de mise en conformité, voie d'exécution",
    },
    "reclamation": {
        "label": "Lettre de réclamation",
        "categorie": "administration",
        "complexite": 2,
        "prix_base_fcfa": 600,
        "description": "Réclamation formelle auprès d'une administration",
        "style": "Exposé des faits, préjudice, demande précise, délai de réponse",
    },
    "plan_affaires": {
        "label": "Plan d'affaires (Business Plan)",
        "categorie": "commercial",
        "complexite": 5,
        "prix_base_fcfa": 8000,
        "description": "Business plan pour PME africaine (banque, investisseurs)",
        "style": "Résumé exécutif, marché, stratégie, finances, BFR, projection 3 ans",
    },
    "etude_marche": {
        "label": "Étude de marché",
        "categorie": "commercial",
        "complexite": 4,
        "prix_base_fcfa": 5000,
        "description": "Analyse du marché local (Cameroun/UEMOA/CEMAC)",
        "style": "Segmentation locale, prix FCFA, canaux distribution africains",
    },
    "devis_commercial": {
        "label": "Devis commercial",
        "categorie": "commercial",
        "complexite": 1,
        "prix_base_fcfa": 300,
        "description": "Devis professionnel en FCFA",
        "style": "Référence, validité, HT/TTC TVA 19.25%, conditions paiement",
    },
    "facture": {
        "label": "Facture",
        "categorie": "commercial",
        "complexite": 1,
        "prix_base_fcfa": 300,
        "description": "Facture conforme aux exigences fiscales camerounaises",
        "style": "N° contribuable, NIU, TVA, conditions paiement Cameroun",
    },
    "communique_presse": {
        "label": "Communiqué de presse",
        "categorie": "communication",
        "complexite": 2,
        "prix_base_fcfa": 1500,
        "description": "Communiqué de presse professionnel",
        "style": "Lead journalistique, corps, citation dirigeant, contact presse",
    },
    "discours": {
        "label": "Discours officiel",
        "categorie": "communication",
        "complexite": 3,
        "prix_base_fcfa": 2500,
        "description": "Discours pour cérémonie officielle",
        "style": "Formules protocolaires africaines, structure rhétorique, conclusion mobilisatrice",
    },
    "rapport_activite": {
        "label": "Rapport d'activité",
        "categorie": "gestion",
        "complexite": 3,
        "prix_base_fcfa": 2000,
        "description": "Rapport mensuel/annuel d'activité d'une structure",
        "style": "Résultats, indicateurs, analyse, perspectives, annexes",
    },
    "note_service": {
        "label": "Note de service",
        "categorie": "administration",
        "complexite": 1,
        "prix_base_fcfa": 200,
        "description": "Note de service interne",
        "style": "Objet précis, destinataires, date d'effet, signataire hiérarchique",
    },
    "note_information": {
        "label": "Note d'information",
        "categorie": "administration",
        "complexite": 1,
        "prix_base_fcfa": 200,
        "description": "Note d'information diffusée en interne",
        "style": "Points clés, clarté, synthèse, diffusion ciblée",
    },
    "appel_offre": {
        "label": "Dossier d'appel d'offres",
        "categorie": "marche_public",
        "complexite": 5,
        "prix_base_fcfa": 8000,
        "description": "DAO conforme ARMP Cameroun / Code des marchés publics",
        "style": "Spécifications techniques, critères notation, clauses ARMP, cautionnement",
    },
    "offre_marche": {
        "label": "Offre technique et financière",
        "categorie": "marche_public",
        "complexite": 4,
        "prix_base_fcfa": 5000,
        "description": "Soumission à un appel d'offres ARMP",
        "style": "Méthodologie, moyens humains, BPU/DQE en FCFA, références similaires",
    },
    "statuts_entreprise": {
        "label": "Statuts d'entreprise",
        "categorie": "juridique",
        "complexite": 5,
        "prix_base_fcfa": 6000,
        "description": "Statuts SARL/SA conformes à l'AUSCGIE OHADA",
        "style": "AUSCGIE, capital minimal OHADA, associés, gérance, répartition parts",
    },
    "rapport_expertise": {
        "label": "Rapport d'expertise",
        "categorie": "technique",
        "complexite": 4,
        "prix_base_fcfa": 4000,
        "description": "Rapport d'expertise technique ou judiciaire",
        "style": "Mission, constatations, analyse, conclusions, pièces jointes",
    },
    "accord_partenariat": {
        "label": "Accord de partenariat",
        "categorie": "juridique",
        "complexite": 3,
        "prix_base_fcfa": 2500,
        "description": "Convention de partenariat entre deux structures",
        "style": "Objet, engagements, ressources, durée, résiliation, droit OHADA",
    },
    "compte_rendu": {
        "label": "Compte rendu de visite / mission",
        "categorie": "administration",
        "complexite": 2,
        "prix_base_fcfa": 600,
        "description": "Compte rendu de déplacement ou visite terrain",
        "style": "Contexte, constats, recommandations, suivi actions",
    },
    "rapport_medical": {
        "label": "Certificat / rapport médical",
        "categorie": "sante",
        "complexite": 2,
        "prix_base_fcfa": 500,
        "description": "Document médical administratif",
        "style": "Identification patient, diagnostic simplifié, conclusion administrative",
    },
    "lettre_resiliation": {
        "label": "Lettre de résiliation de contrat",
        "categorie": "juridique",
        "complexite": 2,
        "prix_base_fcfa": 800,
        "description": "Résiliation formelle d'un contrat",
        "style": "Référence contrat, motif, délai de préavis, décompte final",
    },
    "descriptif_projet": {
        "label": "Description de projet (fiche projet)",
        "categorie": "gestion",
        "complexite": 3,
        "prix_base_fcfa": 2000,
        "description": "Fiche de projet pour bailleur ou administration",
        "style": "Contexte, objectifs SMART, activités, budget FCFA, indicateurs",
    },
}

CATEGORIES = {
    "administration": "Administration",
    "emploi": "Emploi & RH",
    "juridique": "Juridique & OHADA",
    "academique": "Académique",
    "rh": "Ressources Humaines",
    "commercial": "Commercial",
    "communication": "Communication",
    "gestion": "Gestion",
    "marche_public": "Marchés Publics",
    "technique": "Technique",
    "sante": "Santé",
}


@dataclass
class DemandeDocument:
    type_doc: str
    informations: dict           # Champs spécifiques au type (noms, dates, montants…)
    pays: str = "CM"             # CM | SN | CI | TG | BJ | CG | GA | RDC
    langue: str = "fr"
    reformuler_texte: Optional[str] = None   # Texte existant à reformuler/corriger
    style_supplementaire: Optional[str] = None
    user_id: Optional[int] = None


@dataclass
class DocumentGenere:
    titre: str
    contenu_markdown: str
    contenu_word: Optional[bytes] = None
    type_doc: str = ""
    prix_fcfa: int = 0
    nb_mots: int = 0
    meta: dict = field(default_factory=dict)


def calculer_prix(type_doc: str, nb_mots_estime: int = 300) -> int:
    """Retourne le prix en FCFA selon le type et la longueur estimée."""
    info = TYPES_DOCUMENTS.get(type_doc, {})
    base = info.get("prix_base_fcfa", 500)
    complexite = info.get("complexite", 2)
    # Bonus longueur : +100 FCFA par tranche de 200 mots au-delà de 300
    bonus_longueur = max(0, (nb_mots_estime - 300) // 200) * 100
    return base + bonus_longueur * complexite


def _construire_prompt_systeme(type_doc: str, pays: str) -> str:
    """Prompt système calibré sur le style administratif africain francophone."""
    info = TYPES_DOCUMENTS.get(type_doc, {})
    style_guide = info.get("style", "")
    noms_pays = {
        "CM": "Cameroun", "SN": "Sénégal", "CI": "Côte d'Ivoire",
        "TG": "Togo", "BJ": "Bénin", "CG": "Congo", "GA": "Gabon",
        "RDC": "RD Congo", "BF": "Burkina Faso", "ML": "Mali", "NE": "Niger",
    }
    pays_nom = noms_pays.get(pays, "Cameroun")
    return f"""Tu es un expert en rédaction administrative et professionnelle pour l'Afrique francophone subsaharienne, spécialisé dans les documents au {pays_nom}.

RÈGLES ABSOLUES :
1. Style OHADA et administration {pays_nom} : formules protocolaires locales, registre formel attendu
2. JAMAIS de calques américains ou européens (pas de "Cher X", pas de "Best regards", pas de "LLC")
3. Formules d'appel correctes : "Monsieur le Directeur", "Madame la Directrice Générale", etc.
4. Formules de politesse complètes : "Veuillez agréer, Monsieur le Directeur, l'expression de ma considération distinguée."
5. Dates au format français : "Yaoundé, le 22 avril 2026" ou "Abidjan, le {datetime.now().strftime('%d %B %Y')}"
6. Montants en FCFA (jamais en EUR/USD sauf mention expresse)
7. Références légales exactes : Code du travail {pays_nom}, OHADA (AUSCGIE/AUDCG/AU procédures), Code des marchés publics
8. Produire UNIQUEMENT le document final, sans commentaire préliminaire ni explication

STYLE À RESPECTER : {style_guide}

FORMAT DE SORTIE : Document complet, formaté en Markdown propre (titres ##, **gras** pour noms/dates importantes, tableaux si pertinent), prêt à exporter en Word."""


async def generer_document(demande: DemandeDocument) -> DocumentGenere:
    """
    Génère un document professionnel via l'IA.
    Retourne contenu Markdown + .docx si python-docx disponible.
    """
    from core.ia_client import ia_client, ModeIA
    from config.settings import settings

    info = TYPES_DOCUMENTS.get(demande.type_doc)
    if not info:
        raise ValueError(f"Type de document inconnu : {demande.type_doc}")

    pays = demande.pays.upper()
    systeme = _construire_prompt_systeme(demande.type_doc, pays)

    # Construction du prompt utilisateur
    if demande.reformuler_texte:
        prompt = f"""TEXTE À REFORMULER / CORRIGER :
{demande.reformuler_texte}

INSTRUCTIONS : Reformule ce texte dans le style {info['label']} ({pays}), dans le registre administratif attendu. Corrige les fautes, améliore le style, respecte les conventions locales.

INFORMATIONS COMPLÉMENTAIRES :
{_formater_infos(demande.informations)}"""
    else:
        prompt = f"""Rédige un(e) {info['label']} avec les informations suivantes :

{_formater_infos(demande.informations)}

Pays / contexte : {pays}
{f"Précisions : {demande.style_supplementaire}" if demande.style_supplementaire else ""}

Produis le document complet et professionnel."""

    reponse = await ia_client.appeler(
        prompt=prompt,
        mode=ModeIA.REDACTION,
        systeme=systeme,
        max_tokens_override=getattr(settings, "IA_MAX_TOKENS_DOCUMENT", 8192),
    )

    contenu = reponse.contenu
    nb_mots = len(contenu.split())
    prix = calculer_prix(demande.type_doc, nb_mots)

    # Export Word
    contenu_word: Optional[bytes] = None
    try:
        contenu_word = _markdown_vers_docx(contenu, info["label"])
    except Exception as e:
        logger.warning(f"[Rédacteur] Export Word échoué (non bloquant) : {e}")

    return DocumentGenere(
        titre=f"{info['label']} — {datetime.now().strftime('%d/%m/%Y')}",
        contenu_markdown=contenu,
        contenu_word=contenu_word,
        type_doc=demande.type_doc,
        prix_fcfa=prix,
        nb_mots=nb_mots,
        meta={
            "pays": pays,
            "tokens": reponse.tokens_input + reponse.tokens_output,
            "tokens_input": reponse.tokens_input,
            "tokens_output": reponse.tokens_output,
            "modele": reponse.modele_utilise,
        },
    )


async def reformuler_texte(texte: str, registre: str, pays: str = "CM") -> tuple[str, dict]:
    """
    Reformule un texte dans un registre donné (admin, juridique, commercial, academique).
    Utile pour corriger un brouillon client avant d'en faire un document propre.
    """
    from core.ia_client import ia_client, ModeIA

    registres = {
        "admin": "administratif formel (style ministère/préfecture)",
        "juridique": "juridique précis (style tribunal/notariat OHADA)",
        "commercial": "commercial professionnel (style PME africaine)",
        "academique": "académique universitaire (style mémoire/thèse)",
        "simple": "français courant simplifié (compréhensible pour tous)",
    }
    desc_registre = registres.get(registre, registres["admin"])

    systeme = f"""Tu es correcteur et styliste expert pour documents professionnels africains francophones ({pays}).
Reformule le texte fourni dans le registre {desc_registre}.
Corrige les fautes, améliore la fluidité, respecte les conventions locales.
Retourne uniquement le texte reformulé, sans commentaire."""

    reponse = await ia_client.appeler(
        prompt=f"Texte à reformuler :\n\n{texte}",
        mode=ModeIA.REDACTION,
        systeme=systeme,
    )
    meta = {
        "modele": reponse.modele_utilise,
        "tokens_input": reponse.tokens_input,
        "tokens_output": reponse.tokens_output,
    }
    return reponse.contenu, meta


def _formater_infos(infos: dict) -> str:
    """Formate un dict d'informations en liste lisible pour le prompt."""
    lignes = []
    for cle, val in infos.items():
        label = cle.replace("_", " ").capitalize()
        lignes.append(f"- {label} : {val}")
    return "\n".join(lignes) if lignes else "(Générer avec un exemple représentatif)"


def _markdown_vers_docx(markdown: str, titre: str) -> bytes:
    """Convertit du Markdown en .docx via python-docx."""
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    # Marges A4 africaines standard
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.2)
        section.right_margin = Inches(1.2)

    for ligne in markdown.split("\n"):
        ligne = ligne.rstrip()
        if not ligne:
            doc.add_paragraph("")
            continue
        if ligne.startswith("### "):
            p = doc.add_heading(ligne[4:], level=3)
        elif ligne.startswith("## "):
            p = doc.add_heading(ligne[3:], level=2)
        elif ligne.startswith("# "):
            p = doc.add_heading(ligne[2:], level=1)
        elif ligne.startswith("- ") or ligne.startswith("* "):
            doc.add_paragraph(ligne[2:], style="List Bullet")
        else:
            # Gras inline **texte**
            para = doc.add_paragraph()
            _ajouter_run_gras(para, ligne)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _ajouter_run_gras(para, texte: str) -> None:
    """Parse **gras** inline et ajoute les runs correctement."""
    import re
    parties = re.split(r"(\*\*[^*]+\*\*)", texte)
    for partie in parties:
        if partie.startswith("**") and partie.endswith("**"):
            run = para.add_run(partie[2:-2])
            run.bold = True
        else:
            para.add_run(partie)
