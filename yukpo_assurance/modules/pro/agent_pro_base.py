"""
AgentProBase — Classe de base pour les agents de la plateforme Pro.

ARCHITECTURE COHÉRENTE AVEC YUKPOASSURANCE :
  - Hérite de BaseAgent (boucle outil, pause/reprise, checkpoints, streaming)
  - _appeler_claude_sync() : hérité de BaseAgent sans surcharge (Claude + fallback GPT-4o)
  - _construire_prompt()   : enrichit le prompt de BaseAgent avec le profil Pro
  - _necessite_validation(): désactivé pour les agents consultatifs (pas de transactions)
  - TypeAgent             : utilise les nouvelles valeurs PRO_* de l'enum

Outils transversaux injectés dans tous les agents Pro :
  - recherche_reglementaire : corpus RAG africain (OHADA, CGI, Code Travail…)
  - calculer_expression     : calculs mathématiques sécurisés (AST)
  - formater_tableau        : rendu Markdown de données tabulaires

Les agents spécialisés (AgentComptable, AgentDRH, AgentDAF…) héritent de cette
classe, implémentent _outils_metier() et _executer_outil_metier().
"""
from __future__ import annotations

import logging
from typing import Optional

from core.agent_orchestrateur import TypeAgent
from core.pays_devise import format_amount, vocabulaire_devise
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.pro.agent_pro_base")


class AgentProBase(BaseAgent):
    """
    Agent de base pour la plateforme Pro.

    Respecte STRICTEMENT le contrat de BaseAgent :
      - _definir_outils()       → liste des outils (format Anthropic tool_use)
      - _executer_outil()       → dispatch vers l'implémentation
      - _system_prompt()        → instructions spécifiques
      - _necessite_validation() → désactivé pour les agents consultatifs Pro
      - _construire_prompt()    → enrichi du profil métier
      - _appeler_claude_sync()  → HÉRITÉ sans surcharge (BaseAgent gère tout)
    """

    type_agent: TypeAgent = TypeAgent.PRO_GENERIQUE

    def __init__(
        self,
        profil=None,          # ProfilProfessionnelDB | None
        rag_top_k:   int   = 6,
        rag_seuil:   float = 0.35,
    ):
        super().__init__()
        self._profil    = profil
        self._rag_top_k = rag_top_k
        self._rag_seuil = rag_seuil
        self._metier    = profil.metier if profil else None
        self._pays      = profil.pays   if profil else None

    def _format_montant(self, montant) -> str:
        """Formate un montant dans la devise du pays de l'utilisateur."""
        return format_amount(montant, self._pays)

    def _vocabulaire_devise(self) -> str:
        """Mention 'devise locale (CODE)' pour les prompts LLM."""
        return vocabulaire_devise(self._pays)

    # ══════════════════════════════════════════════════════════════════════════
    # Méthodes abstraites requises par BaseAgent
    # ══════════════════════════════════════════════════════════════════════════

    def _system_prompt(self) -> str:
        """
        System prompt enrichi du profil professionnel.
        Surchargé par chaque agent métier avec ses règles de domaine.
        """
        devise_locale = self._vocabulaire_devise()
        lignes = [
            "Tu es un assistant IA expert pour les professionnels en Afrique francophone.",
            "Tu maîtrises le droit OHADA, la fiscalité africaine (CIMA zone, UEMOA, CEMAC),",
            "et les pratiques professionnelles locales.",
            "",
            f"DEVISE LOCALE : Les montants doivent être exprimés en {devise_locale}",
            f"  (devise du pays de l'utilisateur). Si un outil retourne un montant en FCFA",
            f"  alors que la devise locale n'est pas FCFA, mentionne la conversion approximative",
            f"  et utilise systématiquement {devise_locale} dans ta narration et tes recommandations.",
            "",
            "PRINCIPES FONDAMENTAUX :",
            "- Réponds toujours en tenant compte du contexte africain francophone.",
            "- Cite les textes réglementaires applicables avec les numéros d'articles exacts.",
            "- Sois précis, pratique et actionnable.",
            "- Indique clairement quand une question nécessite un conseil professionnel certifié.",
            "- Utilise `recherche_cima` pour TOUTE question sur le Code CIMA, l'assurance CIMA,",
            "  les articles du Code CIMA, les plafonds, délais, obligations d'assurance.",
            "- Utilise `recherche_reglementaire` pour OHADA, fiscalité, droit du travail,",
            "  réglementations hors Code CIMA.",
            "",
            "CODE CIMA — RÈGLES OBLIGATOIRES :",
            "- Dès qu'une question mentionne CIMA, assurance, sinistre, prime, garantie,",
            "  indemnisation, RC auto, vie, capitalisation, microassurance → utilise `recherche_cima`.",
            "- Si `recherche_cima` retourne des articles, cite-les TEXTUELLEMENT avec",
            "  leur numéro exact (Art. 13, Art. 200-1, etc.).",
            "- Ne jamais inventer ou paraphraser le texte d'un article CIMA : cite exactement",
            "  ce que le corpus retourne.",
            "- Si aucun article n'est trouvé, indique-le clairement et recommande à l'utilisateur",
            "  de consulter le texte officiel CIMA disponible auprès de la CRCA.",
            "- INTERDIT : Ne jamais inventer ou paraphraser le texte d'un article CIMA.",
            "- INTERDIT : Ne jamais utiliser tes connaissances générales pour combler un article manquant.",
        ]
        if self._profil:
            lignes.append("")
            lignes.append(self._profil.to_contexte_agent())
        return "\n".join(lignes)

    def _definir_outils(self) -> list[dict]:
        """Outils de base + outils métier des sous-classes."""
        outils_base = [
            {
                "name": "recherche_cima",
                "description": (
                    "Recherche les articles EXACTS du Code CIMA (Code des Assurances des États membres "
                    "de la CIMA — 412 articles indexés). "
                    "UTILISE cet outil pour TOUTE question sur : assurance vie/non-vie, RC auto, "
                    "sinistres, primes, garanties, indemnisation, plafonds CIMA, délais réglementaires, "
                    "microassurance, capitalisation, réassurance, réglementation des compagnies, "
                    "agrément, provisions techniques, solvabilité. "
                    "Retourne le texte officiel des articles avec leurs numéros exacts."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "Question précise sur le Code CIMA. "
                                "Tu peux mentionner un numéro d'article (ex: 'Art. 13 nouveau') "
                                "ou décrire le sujet (ex: 'délai de déclaration sinistre RC auto')."
                            ),
                        },
                    },
                    "required": ["question"],
                },
            },
            {
                "name": "recherche_reglementaire",
                "description": (
                    "Recherche dans le corpus réglementaire africain : OHADA, codes généraux des impôts, "
                    "codes du travail, conventions collectives, codes de commerce, codes civils/pénaux, "
                    "règlements UEMOA/CEMAC, marchés publics, normes qualité… "
                    "UTILISE cet outil dès qu'une question porte sur un texte de loi, "
                    "une obligation légale, ou une réglementation — QUEL QUE SOIT ton profil métier. "
                    "La recherche est globale : un DRH peut trouver un article fiscal, "
                    "un comptable peut trouver une clause de convention collective. "
                    "Précise `domaine` uniquement si tu es certain du type de document recherché."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "Question juridique, fiscale ou réglementaire précise",
                        },
                        "pays": {
                            "type": "string",
                            "description": "Code pays ISO-2 (CM, CI, SN, BF, GA, CG…). "
                                           "Laisser vide pour recherche multi-pays.",
                        },
                        "domaine": {
                            "type": "string",
                            "description": (
                                "Optionnel — à préciser seulement si tu connais le type exact. "
                                "fiscal | travail | commercial | comptabilite | civil | penal | "
                                "conventions_collectives | banque | marches_publics | minier | sante | normes. "
                                "Si omis, la recherche couvre tout le corpus."
                            ),
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Nombre de passages à retourner (défaut : 6, max : 12)",
                            "default": 6,
                        },
                    },
                    "required": ["question"],
                },
            },
            {
                "name": "calculer_expression",
                "description": (
                    "Évalue une expression mathématique ou financière simple. "
                    "Utile pour : calculs fiscaux (TVA, IS, IRPP), paie (CNSS, IRPP), "
                    "ratios financiers, amortissements, intérêts. "
                    "Supporte : +, -, *, /, **, % et parenthèses."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Expression Python valide, ex: '(2500000 * 0.1925)' "
                                           "ou '(base - deductions) * taux'",
                        },
                        "description": {
                            "type": "string",
                            "description": "Description du calcul pour contextualiser le résultat",
                        },
                    },
                    "required": ["expression"],
                },
            },
            {
                "name": "formater_tableau",
                "description": (
                    "Formate une liste de données en tableau Markdown bien structuré. "
                    "Utile pour présenter : bulletins de paie, bilans, comparatifs, "
                    "tableaux d'amortissement, analyses budgétaires."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "donnees": {
                            "type":  "array",
                            "items": {"type": "object"},
                            "description": "Liste de dictionnaires avec des clés uniformes",
                        },
                        "titre": {
                            "type": "string",
                            "description": "Titre du tableau",
                        },
                        "total_ligne": {
                            "type": "boolean",
                            "description": "Ajouter une ligne de totaux (pour colonnes numériques)",
                            "default": False,
                        },
                    },
                    "required": ["donnees"],
                },
            },
        ]
        return outils_base + self._outils_metier()

    async def _executer_outil(
        self,
        nom:          str,
        params:       dict,
        user_id:      int,
        execution_id: str,
    ) -> str:
        """Dispatch vers les outils de base ou métier."""
        if nom == "recherche_cima":
            return await self._outil_recherche_cima(params)
        if nom == "recherche_reglementaire":
            return await self._outil_recherche_rag(params)
        if nom == "calculer_expression":
            return self._outil_calculer(params)
        if nom == "formater_tableau":
            return self._outil_formater_tableau(params)
        return await self._executer_outil_metier(nom, params, user_id, execution_id)

    # ══════════════════════════════════════════════════════════════════════════
    # Surcharge des comportements BaseAgent
    # ══════════════════════════════════════════════════════════════════════════

    def _necessite_validation(self, outil: str, params: dict, resultat: str) -> bool:
        """
        Les agents Pro sont consultatifs : pas de transactions financières directes,
        pas d'insertions en base, pas d'envois de courriers réels.
        → Aucune pause de validation humaine requise.
        Exception : si l'agent génère un document à signer (workflow futur).
        """
        return False

    def _construire_prompt(self, instruction: str, contexte: dict) -> str:
        """
        Enrichit le prompt de base avec :
        - Le pays et métier du profil (si fourni dans le contexte)
        - Les éventuels fichiers joints (Excel, PDF, CSV)
        """
        import json

        parties = [f"INSTRUCTION : {instruction}"]

        # Contexte supplémentaire depuis la requête API
        if contexte:
            ctx_filtre = {k: v for k, v in contexte.items()
                          if k not in ("pays_override", "domaine_override")}
            if ctx_filtre:
                parties.append(f"CONTEXTE :\n{json.dumps(ctx_filtre, ensure_ascii=False, indent=2)}")

        # Injecter le guide de questions spécifiques (méthode BaseAgent)
        guide = self._prompt_questions_specifiques()
        if guide:
            parties.append(
                "━━━ GUIDE : DEMANDE D'INFORMATIONS COMPLÉMENTAIRES ━━━\n"
                "Quand une information essentielle manque, utilise "
                "`demander_information_utilisateur` de façon PROGRESSIVE :\n"
                "• Pose UNE question à la fois\n"
                "• Dès réponse reçue, continue ou pose la suivante\n"
                f"\nSCÉNARIOS SPÉCIFIQUES :\n{guide}"
            )

        return "\n\n".join(parties)

    def _prompt_questions_specifiques(self) -> str:
        """
        Guide contextuel pour savoir quand demander des informations.
        Surchargé par chaque agent métier.
        """
        return (
            "- Si le pays d'exercice est inconnu et pertinent : demander le pays\n"
            "- Si le montant ou l'exercice fiscal est nécessaire au calcul : demander\n"
            "- Ne jamais demander des informations déjà présentes dans le profil utilisateur"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Outils métier — à surcharger par les sous-classes
    # ══════════════════════════════════════════════════════════════════════════

    def _outils_metier(self) -> list[dict]:
        """Outils métier supplémentaires. Retourne [] par défaut."""
        return []

    async def _executer_outil_metier(
        self,
        nom:          str,
        params:       dict,
        user_id:      int,
        execution_id: str,
    ) -> str:
        """Exécution des outils métier. À surcharger dans les sous-classes."""
        return f"[Outil '{nom}' non reconnu par {self.__class__.__name__}]"

    # ══════════════════════════════════════════════════════════════════════════
    # Implémentation des outils de base
    # ══════════════════════════════════════════════════════════════════════════

    async def _outil_recherche_cima(self, params: dict) -> str:
        """Recherche dans le Code CIMA (412 articles officiels)."""
        import asyncio
        try:
            from modules.chat.cima_retriever import rechercher_articles

            question = params.get("question", "").strip()
            if not question:
                return "Erreur : question vide."

            resultat = await asyncio.to_thread(rechercher_articles, question)

            if not resultat or not resultat.strip():
                return (
                    "ARTICLE_NON_TROUVE: Aucun article correspondant n'a été trouvé dans le corpus CIMA. "
                    "Informez l'utilisateur que l'article n'est pas dans la base documentaire et "
                    "recommandez de consulter le texte officiel du Code CIMA auprès de la CRCA "
                    "(Commission Régionale de Contrôle des Assurances) ou sur le site officiel de la CIMA. "
                    "N'inventez pas et ne paraphrasez pas le texte d'un article CIMA."
                )
            return resultat

        except Exception as e:
            logger.warning(f"[AgentProBase] Erreur CIMA retriever : {e}")
            return (
                f"CORPUS_INDISPONIBLE: Le corpus CIMA est temporairement indisponible ({type(e).__name__}). "
                "Informez l'utilisateur que la base documentaire est inaccessible et invitez-le "
                "à réessayer ou à consulter directement les textes officiels CIMA/CRCA. "
                "N'inventez pas de contenu d'article."
            )

    async def _outil_recherche_rag(self, params: dict) -> str:
        """Recherche dans le corpus RAG réglementaire africain."""
        try:
            from modules.rag.rag_retriever import (
                rechercher_corpus_reglementaire,
                rechercher_pour_metier,
            )

            question = params.get("question", "").strip()
            if not question:
                return "Erreur : question vide."

            pays    = params.get("pays") or self._pays
            domaine = params.get("domaine")
            top_k   = min(int(params.get("top_k", self._rag_top_k)), 12)

            # Recherche par métier (meilleure pertinence) si pas de domaine forcé
            if self._metier and not domaine:
                contexte = rechercher_pour_metier(
                    question=question,
                    metier=self._metier,
                    pays=pays,
                    top_k=top_k,
                )
            else:
                contexte = rechercher_corpus_reglementaire(
                    question=question,
                    pays=pays,
                    domaine=domaine,
                    top_k=top_k,
                    seuil_score=self._rag_seuil,
                )

            if not contexte or not contexte.strip():
                return (
                    "DOCUMENT_NON_INDEXE: Aucun passage trouvé dans le corpus réglementaire pour cette question. "
                    "Informez l'utilisateur que ce document ou texte n'est pas encore indexé dans notre base. "
                    "Orientez-le vers les sources officielles (OHADA, CRCA, ministères compétents). "
                    "N'inventez pas de contenu juridique à partir de vos connaissances générales."
                )
            return contexte

        except Exception as e:
            logger.warning(f"[AgentProBase] Erreur RAG : {e}")
            return (
                f"CORPUS_INDISPONIBLE: Le corpus réglementaire est temporairement indisponible ({type(e).__name__}). "
                "Informez l'utilisateur et invitez-le à réessayer. "
                "N'inventez pas de contenu juridique."
            )

    def _outil_calculer(self, params: dict) -> str:
        """Évalue une expression mathématique via AST (sans eval() non contrôlé)."""
        import ast
        import operator as op

        expression  = params.get("expression", "").strip()
        description = params.get("description", "")

        if not expression:
            return "Erreur : expression vide."

        _OPS = {
            ast.Add:  op.add,   ast.Sub:  op.sub,
            ast.Mult: op.mul,   ast.Div:  op.truediv,
            ast.Pow:  op.pow,   ast.Mod:  op.mod,
            ast.UAdd: op.pos,   ast.USub: op.neg,
        }

        def _eval(node):
            if isinstance(node, ast.Constant):
                if not isinstance(node.value, (int, float)):
                    raise ValueError("Seuls les nombres sont autorisés")
                return node.value
            if isinstance(node, ast.BinOp):
                return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp):
                return _OPS[type(node.op)](_eval(node.operand))
            raise ValueError(f"Opération non autorisée : {type(node).__name__}")

        try:
            tree   = ast.parse(expression, mode="eval")
            result = _eval(tree.body)
            # Arrondi intelligent
            if isinstance(result, float):
                result = round(result, 2)
                if result == int(result):
                    result = int(result)
            label = f" ({description})" if description else ""
            # Format selon la devise du pays utilisateur
            if isinstance(result, (int, float)) and abs(result) >= 1000:
                fmt = self._format_montant(result)
            else:
                fmt = str(result)
            return f"Calcul{label} : `{expression}` = **{fmt}**"
        except KeyError:
            return f"Erreur : opérateur non supporté dans `{expression}`"
        except ZeroDivisionError:
            return f"Erreur : division par zéro dans `{expression}`"
        except Exception as e:
            return f"Erreur de calcul : {e}"

    @staticmethod
    def _outil_formater_tableau(params: dict) -> str:
        """Formate une liste de dicts en tableau Markdown."""
        donnees    = params.get("donnees", [])
        titre      = params.get("titre", "")
        total_line = params.get("total_ligne", False)

        if not donnees or not isinstance(donnees, list):
            return "Aucune donnée à afficher."

        try:
            colonnes = list(donnees[0].keys())
            header   = "| " + " | ".join(str(c) for c in colonnes) + " |"
            sep      = "| " + " | ".join(":---" for _ in colonnes) + " |"
            lignes   = [header, sep]

            for row in donnees:
                vals = []
                for c in colonnes:
                    v = row.get(c, "")
                    if isinstance(v, float) and abs(v) >= 1000:
                        v = f"{v:,.0f}".replace(",", " ")
                    elif isinstance(v, int) and abs(v) >= 1000:
                        v = f"{v:,}".replace(",", " ")
                    vals.append(str(v))
                lignes.append("| " + " | ".join(vals) + " |")

            # Ligne de totaux pour les colonnes numériques
            if total_line:
                totaux = []
                for c in colonnes:
                    vals_num = [row.get(c, 0) for row in donnees
                                if isinstance(row.get(c), (int, float))]
                    if vals_num and len(vals_num) == len(donnees):
                        s = sum(vals_num)
                        if isinstance(s, float):
                            s = round(s, 2)
                        totaux.append(f"**{s:,.0f}**".replace(",", " "))
                    else:
                        totaux.append("**—**")
                lignes.append("| " + " | ".join(totaux) + " |")

            result = "\n".join(lignes)
            if titre:
                result = f"**{titre}**\n\n" + result
            return result
        except Exception as e:
            return f"Erreur de formatage tableau : {e}"
