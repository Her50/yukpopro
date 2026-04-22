"""
AgentCVEmploi — Agent IA de rédaction CV et lettre de motivation.

Flux principal :
  1. L'utilisateur envoie une offre d'emploi (texte collé ou fichier joint)
  2. L'agent analyse l'offre et identifie les mots-clés / compétences requises
  3. Il génère un CV ATS-optimisé adapté à l'offre en utilisant le profil stocké
  4. Il génère une lettre de motivation personnalisée
  5. Il propose des points de négociation et conseils d'entretien

Sources de données profil :
  - ProfilProfessionnelDB.cv_texte         : CV de référence (uploadé ou saisi)
  - ProfilProfessionnelDB.profil_recherche_emploi : description profil candidat
  - ProfilProfessionnelDB.metier / niveau / specialite / entreprise

Outils :
  - analyser_offre_emploi   : extrait les mots-clés, compétences, niveau requis
  - generer_cv              : CV chronologique ou fonctionnel adapté à l'offre
  - generer_lettre_motivation : lettre formelle personnalisée
  - adapter_cv_offre        : adapte un CV existant à une offre spécifique
  - conseils_entretien      : prépare l'entretien sur la base de l'offre

PATTERNS YUKPOASSURANCE :
  - type_agent = TypeAgent.PRO_CV_EMPLOI
  - Fonctions IA via ia_client.appeler()
  - Profil lu depuis self._profil (ProfilProfessionnelDB)
"""
from __future__ import annotations

import logging
from typing import Any

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_cv_emploi")


class AgentCVEmploi(AgentProBase):
    """
    Agent spécialisé dans la rédaction de CV et de lettres de motivation
    adaptés aux offres d'emploi du marché africain francophone.
    """

    type_agent: TypeAgent = TypeAgent.PRO_CV_EMPLOI

    def _prompt_systeme_metier(self) -> str:
        metier = self._metier or "professionnel"
        pays = self._pays or "Afrique francophone"
        cv_dispo = bool(getattr(self._profil, "cv_texte", None))
        profil_emploi = getattr(self._profil, "profil_recherche_emploi", "") or ""

        return f"""Tu es un expert en recrutement et rédaction de CV pour le marché africain francophone ({pays}).
Tu maîtrises :
- Les standards CV français (1-2 pages, chronologique inversé, compétences STAR)
- L'optimisation ATS (Applicant Tracking System) avec mots-clés
- Les codes du marché de l'emploi en Afrique francophone (CEMAC, UEMOA, Maghreb)
- La rédaction de lettres de motivation formelles selon les standards africains
- Les techniques de valorisation du parcours africain (expériences multi-pays, langues, secteur informel valorisé)

PROFIL UTILISATEUR :
- Métier actuel : {metier}
- Pays : {pays}
- CV de référence disponible : {"OUI" if cv_dispo else "NON — générer à partir du profil"}
{f"- Profil recherché : {profil_emploi}" if profil_emploi else ""}

RÈGLES STRICTES :
- Toujours adapter le CV à l'offre spécifique (pas de CV générique)
- Mettre en avant les réalisations chiffrées (ex: "Réduction des délais de 30%", "Gestion d'un portefeuille de 500 M FCFA")
- Utiliser la terminologie locale (FCFA, SYSCOHADA, OHADA, COBAC...)
- Format lettre : Lieu et date en haut à droite, formule de politesse africaine appropriée
- Ne jamais inventer des expériences — si des informations manquent, indiquer les placeholders clairs"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "Pour générer ton CV ou ta lettre de motivation, partage :\n"
            "  • L'offre d'emploi (texte ou fichier joint)\n"
            "  • Tes expériences professionnelles clés (postes, entreprises, durée, réalisations)\n"
            "  • Tes formations et certifications\n"
            "  • Le poste visé et tes prétentions salariales (optionnel)"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "analyser_offre_emploi",
                "description": (
                    "Analyse une offre d'emploi et extrait les compétences requises, "
                    "le niveau d'expérience, les mots-clés ATS et les points clés à valoriser dans le CV."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "texte_offre": {
                            "type": "string",
                            "description": "Texte complet de l'offre d'emploi",
                        },
                        "poste": {
                            "type": "string",
                            "description": "Intitulé du poste (si non extrait de l'offre)",
                        },
                        "entreprise_recruteur": {
                            "type": "string",
                            "description": "Nom de l'entreprise recruteur",
                        },
                    },
                    "required": ["texte_offre"],
                },
            },
            {
                "name": "generer_cv",
                "description": (
                    "Génère un CV complet et optimisé pour une offre d'emploi spécifique. "
                    "Utilise le profil utilisateur et le CV de référence s'il est disponible. "
                    "Peut générer le CV en DOCX ou PDF téléchargeable directement dans le chat."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "texte_offre": {
                            "type": "string",
                            "description": "Texte de l'offre d'emploi pour l'adaptation",
                        },
                        "experiences": {
                            "type": "string",
                            "description": "Expériences professionnelles (si non dans le profil stocké)",
                        },
                        "formations": {
                            "type": "string",
                            "description": "Diplômes et formations",
                        },
                        "competences": {
                            "type": "string",
                            "description": "Compétences techniques et soft skills",
                        },
                        "format_cv": {
                            "type": "string",
                            "description": "chronologique | fonctionnel | combiné (défaut: chronologique)",
                        },
                        "longueur": {
                            "type": "string",
                            "description": "1_page | 2_pages (défaut: 1_page pour <5 ans, 2_pages sinon)",
                        },
                        "format_sortie": {
                            "type": "string",
                            "description": "docx | pdf | markdown — format du document généré (défaut: docx)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "generer_lettre_motivation",
                "description": (
                    "Génère une lettre de motivation formelle et personnalisée, "
                    "adaptée à l'offre et aux codes professionnels africains. "
                    "Peut générer la lettre en DOCX ou PDF téléchargeable directement dans le chat."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "texte_offre": {
                            "type": "string",
                            "description": "Texte de l'offre d'emploi",
                        },
                        "entreprise_recruteur": {
                            "type": "string",
                            "description": "Nom de l'entreprise recruteur",
                        },
                        "nom_destinataire": {
                            "type": "string",
                            "description": "Nom du RH ou DRH si connu (ex: M. Jean Dupont)",
                        },
                        "motivations_specifiques": {
                            "type": "string",
                            "description": "Motivations particulières pour ce poste/entreprise",
                        },
                        "pretentions_salariales": {
                            "type": "string",
                            "description": "Prétentions salariales si à mentionner (ex: 800 000 FCFA/mois)",
                        },
                        "disponibilite": {
                            "type": "string",
                            "description": "Date de disponibilité (ex: immédiatement, 1 mois de préavis)",
                        },
                        "format_sortie": {
                            "type": "string",
                            "description": "docx | pdf | markdown — format du document généré (défaut: docx)",
                        },
                    },
                    "required": ["texte_offre"],
                },
            },
            {
                "name": "adapter_cv_offre",
                "description": (
                    "Prend un CV existant (texte) et l'adapte à une offre spécifique : "
                    "reformulation, réorganisation, ajout de mots-clés ATS manquants."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "cv_existant": {
                            "type": "string",
                            "description": "Texte du CV existant à adapter (ou laisser vide pour utiliser le CV stocké dans le profil)",
                        },
                        "texte_offre": {
                            "type": "string",
                            "description": "Texte de l'offre cible",
                        },
                        "type_adaptation": {
                            "type": "string",
                            "description": "mots_cles | reformulation_complete | accroche_seule",
                        },
                    },
                    "required": ["texte_offre"],
                },
            },
            {
                "name": "conseils_entretien",
                "description": (
                    "Prépare un guide d'entretien personnalisé basé sur l'offre d'emploi : "
                    "questions probables, réponses STAR suggérées, points à valoriser, "
                    "questions à poser au recruteur."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "texte_offre": {
                            "type": "string",
                            "description": "Texte de l'offre d'emploi",
                        },
                        "type_entretien": {
                            "type": "string",
                            "description": "rh | technique | direction | panel",
                        },
                        "stade": {
                            "type": "string",
                            "description": "premier_entretien | deuxieme_entretien | test_technique",
                        },
                    },
                    "required": ["texte_offre"],
                },
            },
        ]

    async def _executer_outil_metier(
        self,
        nom: str,
        params: dict,
        user_id: int,
        execution_id: str,
    ) -> Any:
        from core.ia_client import ModeIA, ia_client

        # Enrichir le contexte avec le CV stocké dans le profil
        cv_reference = ""
        if self._profil:
            cv_reference = getattr(self._profil, "cv_texte", "") or ""

        if nom == "analyser_offre_emploi":
            prompt = _prompt_analyser_offre(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        if nom == "generer_cv":
            prompt = _prompt_generer_cv(params, self._profil, cv_reference)
            rep = await ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.REDACTION,
                max_tokens_override=4096,
            )
            contenu_cv = rep.contenu
            format_sortie = params.get("format_sortie", "docx")
            if format_sortie in ("docx", "pdf"):
                return await _generer_document_cv(contenu_cv, "cv", format_sortie, self._profil)
            return contenu_cv

        if nom == "generer_lettre_motivation":
            prompt = _prompt_lettre_motivation(params, self._profil)
            rep = await ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.REDACTION,
                max_tokens_override=2048,
            )
            contenu_lm = rep.contenu
            format_sortie = params.get("format_sortie", "docx")
            if format_sortie in ("docx", "pdf"):
                return await _generer_document_cv(contenu_lm, "lettre", format_sortie, self._profil)
            return contenu_lm

        if nom == "adapter_cv_offre":
            cv_a_adapter = params.get("cv_existant", "") or cv_reference
            if not cv_a_adapter:
                return "Aucun CV trouvé. Veuillez coller votre CV ou l'uploader dans votre profil via /profil/cv."
            prompt = _prompt_adapter_cv(params, cv_a_adapter)
            rep = await ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.REDACTION,
                max_tokens_override=4096,
            )
            return rep.contenu

        if nom == "conseils_entretien":
            prompt = _prompt_conseils_entretien(params, self._profil)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        return f"[Outil '{nom}' non reconnu par AgentCVEmploi]"


# ──────────────────────────────────────────────────────────────────────────────
# Constructeurs de prompts
# ──────────────────────────────────────────────────────────────────────────────

def _ctx_profil(profil) -> str:
    """Extrait un résumé du profil utilisateur pour injection dans les prompts."""
    if not profil:
        return ""
    lignes = []
    if getattr(profil, "metier", None):
        lignes.append(f"Métier actuel : {profil.metier}")
    if getattr(profil, "specialite", None):
        lignes.append(f"Spécialité : {profil.specialite}")
    if getattr(profil, "niveau", None):
        lignes.append(f"Niveau : {profil.niveau}")
    if getattr(profil, "entreprise", None):
        lignes.append(f"Entreprise actuelle : {profil.entreprise}")
    if getattr(profil, "secteur_activite", None):
        lignes.append(f"Secteur : {profil.secteur_activite}")
    if getattr(profil, "pays", None):
        lignes.append(f"Pays : {profil.pays}")
    if getattr(profil, "profil_recherche_emploi", None):
        lignes.append(f"Objectif candidat : {profil.profil_recherche_emploi}")
    return "\n".join(lignes) if lignes else ""


async def _generer_document_cv(
    contenu: str,
    type_doc: str,
    format_sortie: str,
    profil,
) -> str:
    """
    Génère le fichier DOCX/PDF et retourne une réponse texte avec le chemin du fichier.
    Le chemin est encapsulé dans un tag spécial pour que le copilote puisse l'extraire.
    """
    try:
        from modules.pro.cv_document_builder import CvDocumentBuilder
        builder = CvDocumentBuilder(profil=profil)
        if type_doc == "cv":
            res = await builder.generer_cv(contenu, nom_base="cv_yukpo", format_sortie=format_sortie)
        else:
            res = await builder.generer_lettre(contenu, nom_base="lettre_motivation_yukpo", format_sortie=format_sortie)

        chemin = res.get("chemin_fichier", "")
        nom_fichier = res.get("nom_fichier", "")
        label = "CV" if type_doc == "cv" else "Lettre de motivation"
        fmt = format_sortie.upper()

        return (
            f"**{label} généré{'e' if type_doc == 'lettre' else ''} en {fmt}.**\n\n"
            f"Fichier prêt : `{nom_fichier}`\n\n"
            f"<!-- FICHIER_GENERE:{chemin} -->\n\n"
            + contenu[:800]
            + "\n\n*[Document complet dans le fichier joint]*"
        )
    except Exception as e:
        logger.warning(f"[AgentCVEmploi] Génération fichier échouée ({e}) — retour texte")
        return contenu


def _prompt_analyser_offre(params: dict) -> str:
    texte = params.get("texte_offre", "")
    poste = params.get("poste", "")
    entreprise = params.get("entreprise_recruteur", "")

    return f"""Tu es un expert en recrutement spécialisé sur le marché africain francophone.

Analyse cette offre d'emploi et fournis une extraction structurée.

OFFRE D'EMPLOI{f' — {entreprise}' if entreprise else ''}{f' — {poste}' if poste else ''} :
{texte}

EXTRACTION REQUISE :
1. **Poste & niveau** — intitulé exact, niveau d'expérience requis, type de contrat
2. **Compétences techniques obligatoires** — liste priorisée (distinguer requis / souhaité)
3. **Soft skills recherchés** — avec exemples de ce qui sera évalué
4. **Mots-clés ATS** — termes à placer absolument dans le CV pour passer le filtre automatique
5. **Culture d'entreprise** — ce que l'employeur valorise implicitement
6. **Points de vigilance** — critères éliminatoires, conditions particulières
7. **Éléments manquants dans l'offre** — informations à demander ou à vérifier
8. **Conseils d'adaptation CV** — comment positionner le profil pour maximiser les chances

Format : structuré, actionnable, précis."""


def _prompt_generer_cv(params: dict, profil, cv_reference: str) -> str:
    texte_offre = params.get("texte_offre", "")
    experiences = params.get("experiences", "")
    formations = params.get("formations", "")
    competences = params.get("competences", "")
    format_cv = params.get("format_cv", "chronologique")
    longueur = params.get("longueur", "1_page")

    ctx = _ctx_profil(profil)

    sections = []
    if cv_reference:
        sections.append(f"CV DE RÉFÉRENCE (à adapter) :\n{cv_reference[:6000]}")
    elif experiences or formations:
        if experiences:
            sections.append(f"EXPÉRIENCES PROFESSIONNELLES :\n{experiences}")
        if formations:
            sections.append(f"FORMATIONS :\n{formations}")
        if competences:
            sections.append(f"COMPÉTENCES :\n{competences}")
    else:
        sections.append("[Aucun CV de référence fourni — générer un CV modèle avec des placeholders clairs]")

    contenu_reference = "\n\n".join(sections)

    return f"""Tu es un expert en rédaction de CV pour le marché africain francophone.

PROFIL CANDIDAT :
{ctx or '[Profil non renseigné — utiliser des placeholders]'}

{contenu_reference}

OFFRE D'EMPLOI CIBLE :
{texte_offre or '[Offre non fournie — générer un CV général pour le métier du profil]'}

INSTRUCTIONS DE GÉNÉRATION :
- Format : CV {format_cv}, {longueur.replace('_', ' ')} maximum
- En-tête : Nom Prénom, Titre professionnel, Téléphone, Email, Ville/Pays, LinkedIn (si pertinent)
- Section accroche (3 lignes max) : valoriser l'expérience et la valeur ajoutée pour CE poste
- Expériences : ordre chronologique inversé, bullet points STAR avec chiffres (FCFA, %, nombre)
- Formations : diplômes + certifications professionnelles (OHADA, SYSCOHADA, COBAC si applicable)
- Compétences : techniques (logiciels, langages, référentiels) + langues + informatique
- Optimisation ATS : intégrer les mots-clés exacts de l'offre de façon naturelle
- Langue : français professionnel, terminologie métier africaine appropriée
- Si informations manquantes : mettre des placeholders clairs entre [crochets]

Générer le CV complet en format Markdown structuré."""


def _prompt_lettre_motivation(params: dict, profil) -> str:
    texte_offre = params.get("texte_offre", "")
    entreprise = params.get("entreprise_recruteur", "l'entreprise")
    destinataire = params.get("nom_destinataire", "")
    motivations = params.get("motivations_specifiques", "")
    pretentions = params.get("pretentions_salariales", "")
    disponibilite = params.get("disponibilite", "dès que possible")

    ctx = _ctx_profil(profil)
    pays = getattr(profil, "pays", "CM") if profil else "CM"

    villes = {"CM": "Douala", "CI": "Abidjan", "SN": "Dakar", "GA": "Libreville",
              "BF": "Ouagadougou", "ML": "Bamako", "CD": "Kinshasa"}
    ville = villes.get(pays, "Abidjan")

    from datetime import date
    date_str = date.today().strftime("%d %B %Y")

    if destinataire:
        formule_appel = f"Madame, Monsieur {destinataire},"
    else:
        formule_appel = "Madame, Monsieur,"

    return f"""Tu es un expert en rédaction de candidatures pour le marché africain francophone.

Rédige une lettre de motivation formelle et convaincante.

PROFIL CANDIDAT :
{ctx or '[Profil à compléter]'}

OFFRE D'EMPLOI :
{texte_offre}

PARAMÈTRES :
- Entreprise recruteur : {entreprise}
- Formule d'appel : {formule_appel}
- Motivations spécifiques : {motivations or "à construire à partir du profil et de l'offre"}
- Prétentions salariales : {pretentions or 'non mentionnées'}
- Disponibilité : {disponibilite}
- Ville : {ville}, le {date_str}

STRUCTURE DE LA LETTRE :
1. En-tête : coordonnées candidat (gauche) + coordonnées entreprise (droite) + lieu/date
2. Objet : "Candidature au poste de [Titre exact de l'offre]"
3. Formule d'appel
4. §1 — Accroche (2-3 phrases) : montrer qu'on connaît l'entreprise et le poste
5. §2 — Valorisation du parcours : 3 réalisations clés en lien direct avec l'offre
6. §3 — Motivation pour CE poste / CETTE entreprise : pourquoi eux, pourquoi maintenant
7. §4 — Disponibilité, prétentions (si demandées), demande d'entretien
8. Formule de politesse : formule africaine appropriée (respectueuse et professionnelle)
9. Signature

Style : formel, enthousiaste mais sobre, sans flatterie excessive. Longueur : 3/4 de page maximum.
Générer la lettre complète en format texte (pas Markdown)."""


def _prompt_adapter_cv(params: dict, cv_existant: str) -> str:
    texte_offre = params.get("texte_offre", "")
    type_adaptation = params.get("type_adaptation", "mots_cles")

    instructions = {
        "mots_cles": (
            "Identifier les mots-clés ATS manquants et proposer leur intégration naturelle "
            "dans les sections appropriées du CV. Lister les modifications suggérées."
        ),
        "reformulation_complete": (
            "Reformuler l'intégralité du CV pour l'aligner sur l'offre : "
            "réorganiser les priorités, reformuler les bullet points avec les termes de l'offre, "
            "ajuster l'accroche. Fournir le CV complet reformulé."
        ),
        "accroche_seule": (
            "Réécrire uniquement l'accroche/titre professionnel pour qu'elle corresponde "
            "exactement au profil recherché dans l'offre."
        ),
    }
    instruction = instructions.get(type_adaptation, instructions["mots_cles"])

    return f"""Tu es un expert en optimisation de CV pour le marché africain francophone.

CV EXISTANT :
{cv_existant[:6000]}

OFFRE D'EMPLOI CIBLE :
{texte_offre}

MISSION : {instruction}

Réponse structurée avec avant/après pour chaque modification proposée."""


def _prompt_conseils_entretien(params: dict, profil) -> str:
    texte_offre = params.get("texte_offre", "")
    type_entretien = params.get("type_entretien", "rh")
    stade = params.get("stade", "premier_entretien")
    ctx = _ctx_profil(profil)

    types_labels = {
        "rh": "entretien RH (culture, motivation, parcours)",
        "technique": "entretien technique (compétences métier approfondies)",
        "direction": "entretien avec la direction (vision, leadership, stratégie)",
        "panel": "entretien panel (plusieurs interlocuteurs simultanément)",
    }
    label = types_labels.get(type_entretien, type_entretien)

    return f"""Tu es un coach carrière spécialisé dans la préparation aux entretiens en Afrique francophone.

PROFIL CANDIDAT :
{ctx or '[À compléter]'}

OFFRE D'EMPLOI :
{texte_offre}

TYPE : {label} | STADE : {stade.replace('_', ' ')}

GUIDE DE PRÉPARATION REQUIS :
1. **5 questions probables** — formulées comme le recruteur les posera réellement, avec réponse STAR suggérée
2. **Questions pièges à anticiper** — et comment les retourner à son avantage
3. **Points forts à valoriser** — arguments clés à placer impérativement
4. **Faiblesses à gérer** — comment présenter les écarts entre profil et offre
5. **5 questions pertinentes à poser au recruteur** — qui montrent sérieux et préparation
6. **Codes comportementaux** — tenue, ponctualité, posture, codes culturels locaux
7. **Négociation salariale** — quand aborder le sujet, comment répondre à "quelles sont vos prétentions ?"

Format : pratique, bullet points, prêt à l'usage le jour J."""
