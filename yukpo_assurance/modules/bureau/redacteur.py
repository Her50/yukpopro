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
    # Mode de profondeur : "court" (1-2 pages, rapide), "standard" (3-5 pages),
    # "long" (10+ pages — utilise Sonnet/Opus + max_tokens 24k pour rapports
    # détaillés type analyses, business plans, mémoires, etc.)
    mode: str = "standard"  # court | standard | long


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

    # Choix adaptatif modèle + tokens selon le mode demandé.
    # Mode "long" → Sonnet/Opus si dispo (mode REDACTION primaire est Sonnet),
    # max_tokens 24k pour vraiment produire 10+ pages.
    _MAX_TOKENS_PAR_MODE = {
        "court":    4096,
        "standard": getattr(settings, "IA_MAX_TOKENS_DOCUMENT", 8192),
        "long":     24000,
    }
    mode_choisi = (demande.mode or "standard").lower()
    if mode_choisi not in _MAX_TOKENS_PAR_MODE:
        mode_choisi = "standard"
    max_tokens = _MAX_TOKENS_PAR_MODE[mode_choisi]
    # Mode "long" = 10-20 pages équivalentes, contrats juridiques OHADA, plans d'affaires,
    # mémoires. Mérite Opus 4.7 (fallback gpt-4-turbo) — Sonnet/gpt-4o s'essoufflent sur
    # la cohérence documentaire au-delà de ~5000 mots et perdent la rigueur juridique.
    from core.ia_client import ModelePrioritaire as _MP
    _modele_long = _MP.CLAUDE_OPUS if mode_choisi == "long" else None

    if mode_choisi == "long":
        # Indication explicite au LLM de produire un document long et détaillé
        prompt = (
            f"⚠️ MODE LONG — Produis un document EXHAUSTIF et DÉTAILLÉ (10-20 pages "
            f"équivalentes). Sections nombreuses, sous-sections, tableaux récapitulatifs, "
            f"annexes pertinentes, recommandations actionnables. Ne synthétise pas "
            f"prématurément — pousse jusqu'au niveau de détail attendu pour un cabinet "
            f"professionnel.\n\n"
        ) + prompt

    reponse = await ia_client.appeler(
        prompt=prompt,
        mode=ModeIA.REDACTION,  # primaire = Sonnet (équivalent Big4) ; fallback GPT-4o
        systeme=systeme,
        max_tokens_override=max_tokens,
        forcer_modele=_modele_long,  # mode "long" → Opus 4.7 (fallback gpt-4-turbo)
    )

    contenu = reponse.contenu
    nb_mots = len(contenu.split())
    prix = calculer_prix(demande.type_doc, nb_mots)

    # Glossaire auto Haiku (Gap #2 — parite ReportWriter Pro). Pour mode
    # "long" : extraction des 8-15 termes/acronymes techniques (OHADA,
    # SYSCOHADA, BEAC, CIMA, FCFA, IFRS, etc.) avec definitions courtes.
    # Negligeable en cout (~1200 tokens Haiku). Sur mode standard/court,
    # on saute (le doc est trop court pour justifier un glossaire).
    glossaire_items: list[dict] = []
    if mode_choisi == "long":
        try:
            from core.docx_glossaire import generer_glossaire_haiku
            glossaire_items = await generer_glossaire_haiku(contenu, max_termes=12)
        except Exception as _eg:
            logger.debug(f"[Redacteur] Glossaire skip : {_eg}")

    # Export Word — métadonnées DOCX renseignées (auteur=destinataire si fourni
    # sinon "Yukpo Secrétariat", subject=type_doc, keywords=pays+catégorie).
    contenu_word: Optional[bytes] = None
    try:
        meta_docx = {
            "type_doc":  demande.type_doc,
            "categorie": info.get("categorie", ""),
            "pays":      demande.pays,
        }
        contenu_word = _markdown_vers_docx(
            contenu, info["label"], meta=meta_docx,
            glossaire_items=glossaire_items,
        )
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


def _markdown_vers_docx(
    markdown: str, titre: str,
    meta: Optional[dict] = None,
    glossaire_items: Optional[list[dict]] = None,
) -> bytes:
    """
    Convertit du Markdown en .docx via python-docx.

    Upgrade TOP 3 :
    - Métadonnées DOCX (auteur, sujet, mots-clés, catégorie) renseignées.
    - Header (titre court) + Footer (Page X / Y) sauf sur page de garde.
    - Page de garde minimale (titre + date).
    - Sommaire Word natif (field TOC) si le markdown contient ≥2 H1/H2 — sinon
      pas de page de sommaire (lettres simples, attestations).
    - updateFields=true → Word/LibreOffice recalculent TOC + numéros à l'ouverture.
    """
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()
    meta = meta or {}

    # ── ADD-1 — Styles custom Yukpo Quote / Callout / Caption (Big4) ──────
    try:
        from docx.shared import RGBColor as _RGB
        from docx.enum.style import WD_STYLE_TYPE
        if "Yukpo Quote" not in doc.styles:
            qstyle = doc.styles.add_style("Yukpo Quote", WD_STYLE_TYPE.PARAGRAPH)
            qstyle.font.italic = True
            qstyle.font.color.rgb = _RGB(0x4a, 0x5a, 0x6a)
            qstyle.font.size = Pt(11)
            qstyle.paragraph_format.left_indent = Cm(1)
            qstyle.paragraph_format.right_indent = Cm(1)
            qstyle.paragraph_format.space_before = Pt(8)
            qstyle.paragraph_format.space_after = Pt(8)
            ppr_q = qstyle.element.get_or_add_pPr()
            pbdr = OxmlElement("w:pBdr")
            left_b = OxmlElement("w:left")
            left_b.set(qn("w:val"), "single"); left_b.set(qn("w:sz"), "12")
            left_b.set(qn("w:space"), "8"); left_b.set(qn("w:color"), "1d4ed8")
            pbdr.append(left_b); ppr_q.append(pbdr)
        if "Yukpo Callout" not in doc.styles:
            cstyle = doc.styles.add_style("Yukpo Callout", WD_STYLE_TYPE.PARAGRAPH)
            cstyle.font.size = Pt(10.5)
            cstyle.font.color.rgb = _RGB(0x14, 0x2a, 0x4a)
            cstyle.paragraph_format.space_before = Pt(8)
            cstyle.paragraph_format.space_after = Pt(8)
            ppr_c = cstyle.element.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "E8F0FA")
            ppr_c.append(shd)
            pbdr2 = OxmlElement("w:pBdr")
            for side in ("top", "left", "bottom", "right"):
                b = OxmlElement(f"w:{side}")
                b.set(qn("w:val"), "single"); b.set(qn("w:sz"), "4")
                b.set(qn("w:space"), "4"); b.set(qn("w:color"), "B0CDE6")
                pbdr2.append(b)
            ppr_c.append(pbdr2)
        if "Yukpo Caption" not in doc.styles:
            cap = doc.styles.add_style("Yukpo Caption", WD_STYLE_TYPE.PARAGRAPH)
            cap.font.italic = True
            cap.font.size = Pt(9.5)
            cap.font.color.rgb = _RGB(0x66, 0x77, 0x88)
            cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_after = Pt(8)
    except Exception:
        pass

    # ── Polices pro (TOP 5) — Calibri / Calibri Light comme Big4. ─────────
    try:
        normal = doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)
        rpr = normal.element.get_or_add_rPr()
        rfonts = OxmlElement("w:rFonts")
        rfonts.set(qn("w:ascii"), "Calibri")
        rfonts.set(qn("w:hAnsi"), "Calibri")
        rfonts.set(qn("w:eastAsia"), "Calibri")
        rfonts.set(qn("w:cs"), "Calibri")
        for child in rpr.findall(qn("w:rFonts")):
            rpr.remove(child)
        rpr.append(rfonts)
        for hname in ("Heading 1", "Heading 2", "Heading 3"):
            try:
                h_style = doc.styles[hname]
                h_style.font.name = "Calibri Light"
                h_rpr = h_style.element.get_or_add_rPr()
                h_rfonts = OxmlElement("w:rFonts")
                h_rfonts.set(qn("w:ascii"), "Calibri Light")
                h_rfonts.set(qn("w:hAnsi"), "Calibri Light")
                h_rfonts.set(qn("w:eastAsia"), "Calibri Light")
                h_rfonts.set(qn("w:cs"), "Calibri Light")
                for child in h_rpr.findall(qn("w:rFonts")):
                    h_rpr.remove(child)
                h_rpr.append(h_rfonts)
            except KeyError:
                pass
    except Exception:
        pass

    # ── Métadonnées (Fichier > Propriétés sous Word) ───────────────────────
    try:
        cp = doc.core_properties
        cp.title = titre[:255]
        cp.subject = str(meta.get("type_doc") or "")[:255]
        cp.author = "Yukpo Secrétariat"
        cp.last_modified_by = "Yukpo Secrétariat"
        kw = [meta.get("type_doc"), meta.get("categorie"), meta.get("pays")]
        cp.keywords = ", ".join(filter(None, [str(k) for k in kw if k]))[:255]
        cp.category = "Document"
        cp.comments = "Généré par Yukpo Secrétariat"
    except Exception:
        pass

    # ── updateFields=true (recalcul TOC + PAGE/NUMPAGES à l'ouverture) ────
    try:
        s_el = doc.settings.element
        uf = OxmlElement("w:updateFields"); uf.set(qn("w:val"), "true")
        existing = s_el.find(qn("w:updateFields"))
        if existing is not None: s_el.remove(existing)
        s_el.append(uf)
    except Exception:
        pass

    # ── Marges A4 africaines standard + 1ère page différente ──────────────
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3)
        section.right_margin = Cm(2.5)
        section.header_distance = Cm(1.2)
        section.footer_distance = Cm(1.2)
        section.different_first_page_header_footer = True

    # ── Header (titre court, italique gris) ────────────────────────────────
    for section in doc.sections:
        h_para = section.header.paragraphs[0]
        h_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        titre_court = (titre[:80] + "…") if len(titre) > 80 else titre
        h_run = h_para.add_run(titre_court)
        h_run.font.size = Pt(8.5)
        h_run.font.color.rgb = RGBColor(0x77, 0x77, 0x77)
        h_run.italic = True

        # Footer "Page X / Y" centré
        f_para = section.footer.paragraphs[0]
        f_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        f_run = f_para.add_run("Page ")
        f_run.font.size = Pt(8.5)
        f_run.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        def _fld(instr: str):
            r = f_para.add_run(); r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(0x77, 0x77, 0x77)
            beg = OxmlElement("w:fldChar"); beg.set(qn("w:fldCharType"), "begin")
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = instr
            sep = OxmlElement("w:fldChar"); sep.set(qn("w:fldCharType"), "separate")
            tt = OxmlElement("w:t"); tt.text = "1"
            end = OxmlElement("w:fldChar"); end.set(qn("w:fldCharType"), "end")
            r._r.append(beg); r._r.append(it); r._r.append(sep); r._r.append(tt); r._r.append(end)

        _fld("PAGE"); f_para.add_run(" / ").font.size = Pt(8.5); _fld("NUMPAGES")

    # ── Page de garde minimale (titre + date) ──────────────────────────────
    p_titre = doc.add_paragraph()
    p_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_titre.paragraph_format.space_before = Pt(120)
    r_t = p_titre.add_run(titre.upper())
    r_t.bold = True; r_t.font.size = Pt(20)
    r_t.font.color.rgb = RGBColor(0x1d, 0x4e, 0xd8)

    p_date = doc.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_d = p_date.add_run(datetime.now().strftime("%d %B %Y"))
    r_d.font.size = Pt(10); r_d.italic = True
    r_d.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

    # ── Sommaire Word natif si ≥2 H1/H2 dans le contenu ────────────────────
    nb_titres = sum(
        1 for l in markdown.splitlines()
        if l.lstrip().startswith("# ") or l.lstrip().startswith("## ")
    )
    if nb_titres >= 2:
        doc.add_page_break()
        p_toc_t = doc.add_paragraph()
        r_tt = p_toc_t.add_run("SOMMAIRE")
        r_tt.bold = True; r_tt.font.size = Pt(14)
        r_tt.font.color.rgb = RGBColor(0x1d, 0x4e, 0xd8)

        p_toc = doc.add_paragraph()
        run_toc = p_toc.add_run()
        beg = OxmlElement("w:fldChar")
        beg.set(qn("w:fldCharType"), "begin"); beg.set(qn("w:dirty"), "true")
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve")
        it.text = ' TOC \\o "1-3" \\h \\z \\u '
        sep = OxmlElement("w:fldChar"); sep.set(qn("w:fldCharType"), "separate")
        ph = OxmlElement("w:t")
        ph.text = "Sommaire — clic droit > Mettre à jour le champ"
        end = OxmlElement("w:fldChar"); end.set(qn("w:fldCharType"), "end")
        run_toc._r.append(beg); run_toc._r.append(it)
        run_toc._r.append(sep); run_toc._r.append(ph); run_toc._r.append(end)

    doc.add_page_break()

    # ── Corps Markdown → DOCX (handlers Quote/Callout ADD-1) ──────────────
    lignes_md = markdown.split("\n")
    i = 0
    while i < len(lignes_md):
        ligne = lignes_md[i].rstrip()
        if not ligne:
            doc.add_paragraph("")
            i += 1
            continue
        if ligne.startswith("### "):
            doc.add_heading(ligne[4:], level=3)
            i += 1
        elif ligne.startswith("## "):
            doc.add_heading(ligne[3:], level=2)
            i += 1
        elif ligne.startswith("# "):
            doc.add_heading(ligne[2:], level=1)
            i += 1
        elif ligne.lstrip().startswith("> "):
            quote_lines = []
            while i < len(lignes_md) and lignes_md[i].lstrip().startswith("> "):
                quote_lines.append(lignes_md[i].lstrip()[2:].rstrip())
                i += 1
            try:
                doc.add_paragraph(" ".join(quote_lines), style="Yukpo Quote")
            except KeyError:
                p_q = doc.add_paragraph(" ".join(quote_lines))
                for r_q in p_q.runs:
                    r_q.italic = True
        elif ligne.startswith("!!! "):
            rest = ligne[4:].strip()
            label, _, body = rest.partition(":")
            body_lines = [body.strip()] if body else [label.strip()]
            i += 1
            while i < len(lignes_md) and lignes_md[i].startswith("    "):
                body_lines.append(lignes_md[i].strip())
                i += 1
            try:
                doc.add_paragraph(" ".join(body_lines), style="Yukpo Callout")
            except KeyError:
                doc.add_paragraph(" ".join(body_lines))
        elif ligne.startswith("- ") or ligne.startswith("* "):
            doc.add_paragraph(ligne[2:], style="List Bullet")
            i += 1
        elif '|' in ligne and (i + 1 < len(lignes_md)) and '|' in lignes_md[i + 1]:
            # Tableau markdown : rendu DOCX natif + chart auto si colonnes
            # numériques. Factorisé via core/docx_charts (partagé avec
            # report_writer_pro côté Pro — meme moteur, meme rendu).
            from core.docx_charts import (
                generer_png_depuis_tableau,
                detecter_colonnes_numeriques,
                parser_tableau_markdown,
            )
            from docx.shared import Pt as _Pt, RGBColor as _RGB, Inches as _Inches
            from docx.enum.text import WD_ALIGN_PARAGRAPH as _WDA
            from docx.oxml.ns import qn as _qn
            from docx.oxml import OxmlElement as _OxmlElement

            headers_t, data_rows, i_after = parser_tableau_markdown(lignes_md, i)
            if not headers_t:
                # ligne avec '|' mais pas un tableau valide → run normal
                para = doc.add_paragraph()
                _ajouter_run_gras(para, ligne)
                i += 1
                continue

            cols_num = detecter_colonnes_numeriques(headers_t, data_rows)
            all_rows = [
                lignes_md[k] for k in range(i, i_after)
                if not __import__('re').match(
                    r'^\|[\s\-:|\s]+\|$', lignes_md[k].strip()
                )
            ]
            tbl = doc.add_table(rows=len(all_rows), cols=len(headers_t))
            tbl.style = 'Table Grid'
            tbl.autofit = True
            for ri, row_line in enumerate(all_rows):
                cells = [c.strip() for c in row_line.split('|') if c.strip()]
                for ci in range(len(headers_t)):
                    val = cells[ci].strip('*') if ci < len(cells) else ""
                    cell = tbl.cell(ri, ci)
                    cell.text = val
                    para = cell.paragraphs[0]
                    if para.runs:
                        run = para.runs[0]
                        run.font.size = _Pt(10)
                        if ri == 0:
                            run.bold = True
                            run.font.color.rgb = _RGB(0xFF, 0xFF, 0xFF)
                    if ri == 0:
                        para.paragraph_format.alignment = _WDA.CENTER
                    elif ci in cols_num:
                        para.paragraph_format.alignment = _WDA.RIGHT
                    tc = cell._tc
                    tcPr = tc.get_or_add_tcPr()
                    shd = _OxmlElement('w:shd')
                    shd.set(_qn('w:val'), 'clear')
                    shd.set(_qn('w:color'), 'auto')
                    if ri == 0:
                        shd.set(_qn('w:fill'), '0047AB')
                    elif ri % 2 == 0:
                        shd.set(_qn('w:fill'), 'F4F7FB')
                    else:
                        shd.set(_qn('w:fill'), 'FFFFFF')
                    tcPr.append(shd)
            doc.add_paragraph()

            # Chart auto si tableau quantifiable
            if cols_num and len(data_rows) >= 2:
                png = generer_png_depuis_tableau(
                    headers=headers_t, rows=data_rows, colonnes_num=cols_num,
                )
                if png:
                    try:
                        import io as _io
                        p_img = doc.add_paragraph()
                        p_img.alignment = _WDA.CENTER
                        run_img = p_img.add_run()
                        run_img.add_picture(_io.BytesIO(png), width=_Inches(5.8))
                        doc.add_paragraph()
                    except Exception as _e_img:
                        logger.debug(f"[Rédacteur] Chart image: {_e_img}")
            i = i_after
        else:
            para = doc.add_paragraph()
            _ajouter_run_gras(para, ligne)
            i += 1

    # ── ADD-1 — Bloc signature en fin (placeholder destinataire/expéditeur) ─
    # Standard administratif : ligne signature + libellé "Signature et cachet".
    # Pour une lettre/attestation/certificat, c'est le marqueur de pro qui
    # manquait. Pas de "Fait le ..." ici (déjà dans la page de garde via date).
    try:
        doc.add_paragraph()
        p_sig = doc.add_paragraph()
        p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_line = p_sig.add_run("\n_______________________________")
        r_line.font.size = Pt(10)
        p_sig_lab = doc.add_paragraph()
        p_sig_lab.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_lab = p_sig_lab.add_run("Signature et cachet")
        r_lab.italic = True; r_lab.font.size = Pt(9)
    except Exception:
        pass

    # Glossaire auto (Gap #2) — page finale Big4-grade si caller l'a pre-genere
    if glossaire_items:
        try:
            from core.docx_glossaire import ajouter_glossaire_au_doc
            ajouter_glossaire_au_doc(doc, glossaire_items)
        except Exception as _eg:
            logger.debug(f"[Redacteur] Render glossaire : {_eg}")

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
