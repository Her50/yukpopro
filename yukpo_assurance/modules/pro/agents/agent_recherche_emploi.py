"""
AgentRechercheEmploi — Agent IA de veille et recherche d'emploi automatique.

Fonctionnement :
  1. L'utilisateur configure son profil de recherche (poste, secteur, pays, prétentions)
  2. L'agent active une veille périodique (via scheduler_emploi.py)
  3. À chaque cycle, il interroge les sources d'offres disponibles (RSS, sites emploi)
  4. Il filtre et évalue chaque offre par rapport au profil
  5. Il notifie l'utilisateur des meilleures correspondances

Sources d'offres :
  - Indeed.com RSS (ex: cm.indeed.com, ci.indeed.com)
  - Emploi.cm / Emploi.ci / Emploi.sn (sites nationaux africains)
  - LinkedIn Jobs RSS (si disponible)
  - Jobberman Africa (Nigeria, Ghana, Kenya — extendable)

Outils :
  - configurer_recherche     : définit ou met à jour le profil de recherche
  - voir_offres_recentes     : affiche les offres trouvées lors de la dernière veille
  - lancer_recherche_manuelle: déclenche une recherche immédiate
  - activer_veille           : active la veille automatique + configure la fréquence
  - desactiver_veille        : désactive la veille automatique
  - evaluer_compatibilite    : évalue si une offre correspond au profil (score 0-100)

PATTERNS YUKPOASSURANCE :
  - type_agent = TypeAgent.PRO_RECHERCHE_EMPLOI
  - DB : ProfilProfessionnelDB (offres_emploi_recentes JSON, recherche_emploi_active, etc.)
  - Scheduler : modules/pro/scheduler_emploi.py (asyncio boucle par user)
"""
from __future__ import annotations

import logging
from typing import Any

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_recherche_emploi")


class AgentRechercheEmploi(AgentProBase):
    """
    Agent de veille emploi automatique pour les professionnels africains.
    Recherche périodiquement des offres adaptées au profil de l'utilisateur.
    """

    type_agent: TypeAgent = TypeAgent.PRO_RECHERCHE_EMPLOI

    def _prompt_systeme_metier(self) -> str:
        metier = self._metier or "professionnel"
        pays = self._pays or "Afrique francophone"
        profil_emploi = getattr(self._profil, "profil_recherche_emploi", "") or ""
        veille_active = getattr(self._profil, "recherche_emploi_active", False)
        freq = getattr(self._profil, "frequence_recherche_heures", 24)

        return f"""Tu es un chasseur de têtes digital spécialisé sur le marché de l'emploi africain francophone.
Tu aides les professionnels à trouver des opportunités correspondant exactement à leur profil.

PROFIL UTILISATEUR :
- Métier : {metier}
- Pays de recherche principal : {pays}
- Veille automatique : {"ACTIVÉE (toutes les " + str(freq) + "h)" if veille_active else "DÉSACTIVÉE"}
{f"- Profil de recherche : {profil_emploi}" if profil_emploi else "- Profil de recherche : non configuré"}

TU SAIS :
- Quels sites d'emploi sont actifs dans chaque pays africain (Indeed, Emploi.cm, Jobberman, etc.)
- Comment évaluer la correspondance entre un profil et une offre (score 0-100)
- Comment rédiger des candidatures spontanées percutantes
- Les salaires du marché par métier / pays / niveau d'expérience en Afrique francophone

RÈGLES :
- Toujours indiquer la source et la date de chaque offre présentée
- Évaluer honnêtement la compatibilité (ne pas sur-vendre les correspondances)
- Prioriser les offres en CDI ou CDD long terme sauf préférence contraire"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "Pour configurer ta recherche d'emploi, indique :\n"
            "  • Le(s) poste(s) ou domaine(s) recherché(s)\n"
            "  • Le(s) pays ou ville(s) ciblé(s)\n"
            "  • Ton niveau d'expérience et tes prétentions salariales\n"
            "  • La fréquence souhaitée pour la veille automatique (ex: toutes les 12h, 24h)"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "configurer_recherche",
                "description": (
                    "Configure ou met à jour le profil de recherche d'emploi de l'utilisateur. "
                    "Définit le poste ciblé, le secteur, le pays, les prétentions et la fréquence de veille."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "poste_cible": {
                            "type": "string",
                            "description": "Intitulé du poste recherché (ex: Responsable Comptable, DAF, DRH)",
                        },
                        "secteurs": {
                            "type": "string",
                            "description": "Secteurs d'activité visés (ex: banque, industrie, ONG, service)",
                        },
                        "pays_cibles": {
                            "type": "string",
                            "description": "Pays ou villes ciblés (ex: Cameroun, Côte d'Ivoire, Sénégal)",
                        },
                        "pretentions_salariales": {
                            "type": "string",
                            "description": "Fourchette salariale minimum/maximum (ex: 800 000 - 1 500 000 FCFA)",
                        },
                        "type_contrat": {
                            "type": "string",
                            "description": "CDI | CDD | Freelance | Tous types",
                        },
                        "niveau_experience": {
                            "type": "string",
                            "description": "junior (0-2 ans) | confirme (3-7 ans) | senior (>7 ans) | direction",
                        },
                        "disponibilite": {
                            "type": "string",
                            "description": "immediat | 1_mois | 3_mois",
                        },
                        "description_libre": {
                            "type": "string",
                            "description": "Description libre complémentaire (compétences clés, secteur de prédilection...)",
                        },
                    },
                    "required": ["poste_cible"],
                },
            },
            {
                "name": "voir_offres_recentes",
                "description": (
                    "Affiche les offres d'emploi trouvées lors de la dernière veille automatique "
                    "ou de la dernière recherche manuelle."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filtre_score_min": {
                            "type": "integer",
                            "description": "Score de compatibilité minimum à afficher (0-100, défaut: 50)",
                        },
                        "nb_max": {
                            "type": "integer",
                            "description": "Nombre maximum d'offres à afficher (défaut: 10)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "lancer_recherche_manuelle",
                "description": (
                    "Lance immédiatement une recherche d'offres d'emploi sur les sites africains "
                    "selon le profil configuré. Résultats disponibles dans voir_offres_recentes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mots_cles_supplementaires": {
                            "type": "string",
                            "description": "Mots-clés additionnels pour affiner cette recherche",
                        },
                        "pays_override": {
                            "type": "string",
                            "description": "Forcer la recherche sur un pays spécifique",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "activer_veille",
                "description": (
                    "Active la veille emploi automatique avec une fréquence configurable. "
                    "L'agent cherchera des offres périodiquement et vous notifiera des nouvelles trouvées."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "frequence_heures": {
                            "type": "integer",
                            "description": "Fréquence en heures (ex: 12, 24, 48 — défaut: 24)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "desactiver_veille",
                "description": "Désactive la veille emploi automatique.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "evaluer_compatibilite",
                "description": (
                    "Évalue la compatibilité entre le profil utilisateur et une offre d'emploi spécifique. "
                    "Score 0-100 avec détail des forces, lacunes et conseils d'adaptation."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "texte_offre": {
                            "type": "string",
                            "description": "Texte de l'offre d'emploi à évaluer",
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

        if nom == "configurer_recherche":
            return await _configurer_recherche(params, user_id)

        if nom == "voir_offres_recentes":
            return await _voir_offres_recentes(params, user_id)

        if nom == "lancer_recherche_manuelle":
            return await _lancer_recherche_manuelle(params, user_id, self._profil)

        if nom == "activer_veille":
            return await _activer_veille(params, user_id)

        if nom == "desactiver_veille":
            return await _desactiver_veille(user_id)

        if nom == "evaluer_compatibilite":
            prompt = _prompt_evaluer_compatibilite(params, self._profil)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        return f"[Outil '{nom}' non reconnu par AgentRechercheEmploi]"


# ──────────────────────────────────────────────────────────────────────────────
# Fonctions d'action (DB + scheduler)
# ──────────────────────────────────────────────────────────────────────────────

async def _configurer_recherche(params: dict, user_id: int) -> str:
    """Sauvegarde le profil de recherche dans ProfilProfessionnelDB."""
    try:
        from core.database import async_session_maker
        from modules.pro.service_profil import get_or_create

        async with async_session_maker() as db:
            profil, _ = await get_or_create(user_id, db)

            # Construire la description du profil de recherche
            elements = []
            if params.get("poste_cible"):
                elements.append(f"Poste : {params['poste_cible']}")
            if params.get("secteurs"):
                elements.append(f"Secteur : {params['secteurs']}")
            if params.get("pays_cibles"):
                elements.append(f"Pays : {params['pays_cibles']}")
            if params.get("pretentions_salariales"):
                elements.append(f"Prétentions : {params['pretentions_salariales']}")
            if params.get("type_contrat"):
                elements.append(f"Contrat : {params['type_contrat']}")
            if params.get("niveau_experience"):
                elements.append(f"Niveau : {params['niveau_experience']}")
            if params.get("disponibilite"):
                elements.append(f"Disponibilité : {params['disponibilite']}")
            if params.get("description_libre"):
                elements.append(params["description_libre"])

            profil.profil_recherche_emploi = "\n".join(elements)

            from sqlalchemy import update
            from modules.pro.profil_pro import ProfilProfessionnelDB
            await db.execute(
                update(ProfilProfessionnelDB)
                .where(ProfilProfessionnelDB.user_id == user_id)
                .values(profil_recherche_emploi=profil.profil_recherche_emploi)
            )
            await db.commit()

        poste = params.get("poste_cible", "votre poste cible")
        return (
            f"✅ **Profil de recherche configuré avec succès**\n\n"
            f"**Poste cible :** {poste}\n"
            f"{'**Pays :** ' + params['pays_cibles'] + chr(10) if params.get('pays_cibles') else ''}"
            f"{'**Secteur :** ' + params['secteurs'] + chr(10) if params.get('secteurs') else ''}"
            f"{'**Prétentions :** ' + params['pretentions_salariales'] + chr(10) if params.get('pretentions_salariales') else ''}"
            f"\nUtilisez **activer_veille** pour démarrer la recherche automatique, "
            f"ou **lancer_recherche_manuelle** pour une recherche immédiate."
        )
    except Exception as e:
        logger.error(f"[AgentRechercheEmploi] configurer_recherche error: {e}")
        return f"Erreur lors de la configuration : {e}"


async def _voir_offres_recentes(params: dict, user_id: int) -> str:
    """Retourne les offres stockées dans le profil."""
    try:
        from core.database import async_session_maker
        from modules.pro.service_profil import get_or_create

        async with async_session_maker() as db:
            profil, _ = await get_or_create(user_id, db)

        offres = getattr(profil, "offres_emploi_recentes", []) or []
        score_min = int(params.get("filtre_score_min", 50))
        nb_max = int(params.get("nb_max", 10))
        derniere = getattr(profil, "derniere_recherche_emploi", None)

        if not offres:
            veille = getattr(profil, "recherche_emploi_active", False)
            if veille:
                return (
                    "Aucune offre trouvée lors de la dernière veille.\n"
                    "La prochaine recherche sera effectuée automatiquement.\n"
                    "Utilisez **lancer_recherche_manuelle** pour une recherche immédiate."
                )
            return (
                "Aucune offre disponible.\n"
                "Configurez d'abord votre profil avec **configurer_recherche**, "
                "puis lancez une recherche avec **lancer_recherche_manuelle** "
                "ou activez la veille avec **activer_veille**."
            )

        offres_filtrees = [o for o in offres if o.get("score", 0) >= score_min][:nb_max]

        if not offres_filtrees:
            return f"Aucune offre avec un score ≥ {score_min}. Abaissez le filtre ou relancez une recherche."

        lignes = [
            f"## Offres d'emploi récentes",
            f"Dernière recherche : {derniere.strftime('%d/%m/%Y %H:%M') if derniere else 'inconnue'}",
            f"Affichage : {len(offres_filtrees)} offre(s) avec score ≥ {score_min}",
            "",
        ]
        for i, offre in enumerate(offres_filtrees, 1):
            score = offre.get("score", "?")
            emoji = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"
            lignes += [
                f"### {i}. {offre.get('titre', 'Poste')} — {offre.get('entreprise', '')}",
                f"  {emoji} Score compatibilité : **{score}/100**",
                f"  📍 Lieu : {offre.get('lieu', 'Non précisé')}",
                f"  📅 Publiée : {offre.get('date_publication', 'Date inconnue')}",
                f"  💼 Contrat : {offre.get('type_contrat', 'Non précisé')}",
                f"  🔗 Source : {offre.get('source', '')}",
            ]
            if offre.get("url"):
                lignes.append(f"  👉 Lien : {offre['url']}")
            if offre.get("resume"):
                lignes.append(f"  📄 Résumé : {offre['resume'][:200]}...")
            lignes.append("")

        lignes.append("💡 Utilisez **evaluer_compatibilite** pour une analyse détaillée d'une offre.")
        return "\n".join(lignes)

    except Exception as e:
        logger.error(f"[AgentRechercheEmploi] voir_offres error: {e}")
        return f"Erreur lors de la récupération des offres : {e}"


async def _lancer_recherche_manuelle(params: dict, user_id: int, profil) -> str:
    """Lance une recherche d'offres immédiate et stocke les résultats."""
    try:
        from modules.pro.scheduler_emploi import rechercher_offres_pour_user
        mots_cles_sup = params.get("mots_cles_supplementaires", "")
        pays_override = params.get("pays_override", "")

        nb_trouvees = await rechercher_offres_pour_user(
            user_id=user_id,
            profil=profil,
            mots_cles_extra=mots_cles_sup,
            pays_override=pays_override,
        )

        if nb_trouvees == 0:
            return (
                "Recherche effectuée — aucune nouvelle offre trouvée correspondant à votre profil.\n"
                "Essayez d'élargir vos critères dans **configurer_recherche** "
                "ou ajoutez des mots-clés supplémentaires."
            )
        return (
            f"✅ **Recherche terminée** — **{nb_trouvees} offre(s)** trouvée(s) et sauvegardées.\n"
            f"Utilisez **voir_offres_recentes** pour les consulter."
        )
    except Exception as e:
        logger.error(f"[AgentRechercheEmploi] recherche_manuelle error: {e}")
        return f"Erreur lors de la recherche : {e}"


async def _activer_veille(params: dict, user_id: int) -> str:
    """Active la veille automatique pour l'utilisateur."""
    try:
        freq = int(params.get("frequence_heures", 24))
        freq = max(6, min(168, freq))  # entre 6h et 1 semaine

        from core.database import async_session_maker
        from modules.pro.profil_pro import ProfilProfessionnelDB
        from sqlalchemy import update

        async with async_session_maker() as db:
            await db.execute(
                update(ProfilProfessionnelDB)
                .where(ProfilProfessionnelDB.user_id == user_id)
                .values(
                    recherche_emploi_active=True,
                    frequence_recherche_heures=freq,
                )
            )
            await db.commit()

        return (
            f"✅ **Veille emploi activée** — recherche toutes les **{freq} heures**\n\n"
            f"L'agent va parcourir les sites d'offres d'emploi africains selon votre profil "
            f"et vous notifier des meilleures correspondances.\n\n"
            f"Utilisez **desactiver_veille** pour arrêter la veille à tout moment."
        )
    except Exception as e:
        logger.error(f"[AgentRechercheEmploi] activer_veille error: {e}")
        return f"Erreur lors de l'activation : {e}"


async def _desactiver_veille(user_id: int) -> str:
    """Désactive la veille automatique."""
    try:
        from core.database import async_session_maker
        from modules.pro.profil_pro import ProfilProfessionnelDB
        from sqlalchemy import update

        async with async_session_maker() as db:
            await db.execute(
                update(ProfilProfessionnelDB)
                .where(ProfilProfessionnelDB.user_id == user_id)
                .values(recherche_emploi_active=False)
            )
            await db.commit()

        return (
            "⏸️ **Veille emploi désactivée.**\n"
            "Vos offres récentes restent disponibles dans **voir_offres_recentes**.\n"
            "Réactivez à tout moment avec **activer_veille**."
        )
    except Exception as e:
        logger.error(f"[AgentRechercheEmploi] desactiver_veille error: {e}")
        return f"Erreur : {e}"


def _prompt_evaluer_compatibilite(params: dict, profil) -> str:
    texte_offre = params.get("texte_offre", "")
    metier = getattr(profil, "metier", "") if profil else ""
    niveau = getattr(profil, "niveau", "") if profil else ""
    specialite = getattr(profil, "specialite", "") if profil else ""
    profil_emploi = getattr(profil, "profil_recherche_emploi", "") if profil else ""
    cv_texte = getattr(profil, "cv_texte", "") if profil else ""

    ctx_candidat = f"Métier : {metier} | Niveau : {niveau}"
    if specialite:
        ctx_candidat += f" | Spécialité : {specialite}"
    if profil_emploi:
        ctx_candidat += f"\nProfil recherche : {profil_emploi}"
    if cv_texte:
        ctx_candidat += f"\nExtrait CV :\n{cv_texte[:2000]}"

    return f"""Tu es un expert en recrutement spécialisé Afrique francophone.

Évalue la compatibilité entre ce candidat et cette offre d'emploi.

PROFIL CANDIDAT :
{ctx_candidat}

OFFRE D'EMPLOI :
{texte_offre}

ÉVALUATION REQUISE :
1. **Score global de compatibilité : XX/100** (avec justification en 2 lignes)
2. **Points forts du profil** pour ce poste (ce qui joue en faveur)
3. **Lacunes identifiées** (écarts entre profil et offre, avec gravité FAIBLE/MOYEN/CRITIQUE)
4. **Probabilité de passer la présélection ATS** : HAUTE / MOYENNE / FAIBLE
5. **Recommandation** : POSTULER / POSTULER AVEC ADAPTATION / NE PAS POSTULER
6. **Si postuler : 3 actions à faire** avant d'envoyer la candidature

Format : structuré, score en gras, tonalité directe et honnête."""
