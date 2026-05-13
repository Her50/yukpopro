"""
Routes Agent Pro — Interface conversationnelle pour les professionnels.

Endpoints :
  POST /api/v1/pro/agent/chat       — Requête directe (réponse complète)
  POST /api/v1/pro/agent/recherche  — Recherche RAG seule (sans boucle agent)
  GET  /api/v1/pro/agent/historique — Dernières sessions de l'utilisateur
"""
import dataclasses
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import async_session_maker

logger = logging.getLogger("yukpo_assurance.api.pro_agent")

router = APIRouter()


async def get_db():
    async with async_session_maker() as session:
        yield session


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class ChatProRequest(BaseModel):
    message:   str  = Field(..., min_length=2, max_length=8000)
    contexte:  dict = Field(default_factory=dict)
    # Surcharge optionnelle des paramètres RAG
    pays:      Optional[str]  = None
    domaine:   Optional[str]  = None


class RechercheRAGProRequest(BaseModel):
    question:  str   = Field(..., min_length=2)
    pays:      Optional[str]  = None
    domaine:   Optional[str]  = None
    top_k:     int   = 8
    seuil:     float = 0.35


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/chat", summary="Chat avec l'agent professionnel IA")
async def chat_agent_pro(
    req: ChatProRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Envoie un message à l'agent IA professionnel.
    L'agent utilise automatiquement le profil métier et le corpus RAG.
    Retourne la réponse complète avec les étapes de raisonnement.
    """
    from modules.pro.service_profil import get_or_create, incrementer_stat
    from modules.pro.agent_pro_base import AgentProBase

    # Récupérer ou créer le profil (onboarding silencieux)
    profil, _ = await get_or_create(current_user.user_id, db)

    # Construire le contexte de la requête
    contexte = dict(req.contexte)
    if req.pays:
        contexte["pays_override"] = req.pays
    if req.domaine:
        contexte["domaine_override"] = req.domaine

    # Choisir l'agent adapté au métier — agent_force permet de surcharger le profil
    agent_force = contexte.get("agent_force")
    agent = _charger_agent_metier(profil, agent_force=agent_force)

    execution_id = f"pro-{current_user.user_id}-{uuid.uuid4().hex[:8]}"

    try:
        resultat = await agent.executer(
            instruction=req.message,
            user_id=current_user.user_id,
            contexte=contexte,
            execution_id=execution_id,
        )

        # Incrémenter les stats + débiter crédits
        await incrementer_stat(current_user.user_id, "nb_requetes_agent", db, xp_gain=2)
        try:
            # Débit pré-estimé avant exécution : on suit le tier mid (Sonnet/
            # gpt-5-mini). Le débit réel post-exécution récupère le modele_utilise
            # depuis ReponseIA et corrige automatiquement.
            from modules.pro.service_credits import verifier_et_debiter
            ok, _c, msg = await verifier_et_debiter(
                user_id=current_user.user_id, modele="gpt-5-mini",
                tokens_input=1500, tokens_output=1000,
                module="agent", db=db,
            )
            if not ok:
                raise HTTPException(status_code=429, detail=msg)
        except HTTPException:
            raise
        except Exception as _e:
            pass  # non bloquant

        return {
            "execution_id": execution_id,
            "reponse":      resultat.resume,
            "statut":       resultat.statut.value,
            "nb_etapes":    len(resultat.etapes),
            "etapes":       [dataclasses.asdict(e) for e in resultat.etapes[:10]],
            "duree_ms":     resultat.duree_totale_ms,
            "profil_metier": profil.metier,
        }

    except Exception as e:
        logger.error(f"[AgentPro] Erreur chat user={current_user.user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur agent : {str(e)[:200]}")


@router.post("/recherche", summary="Recherche RAG réglementaire directe")
async def recherche_rag_pro(
    req: RechercheRAGProRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Recherche directe dans le corpus réglementaire africain.
    Plus rapide que le chat car n'utilise pas la boucle agent.
    """
    from modules.pro.service_profil import get_or_create, incrementer_stat
    from modules.rag.rag_retriever import (
        rechercher_corpus_reglementaire,
        rechercher_pour_metier,
    )

    profil, _ = await get_or_create(current_user.user_id, db)
    pays   = req.pays   or profil.pays
    metier = profil.metier

    try:
        if metier and not req.domaine:
            contexte = rechercher_pour_metier(
                question=req.question,
                metier=metier,
                pays=pays,
                top_k=req.top_k,
            )
        else:
            contexte = rechercher_corpus_reglementaire(
                question=req.question,
                pays=pays,
                domaine=req.domaine,
                top_k=req.top_k,
                seuil_score=req.seuil,
            )

        await incrementer_stat(current_user.user_id, "nb_requetes_rag", db, xp_gain=1)

        return {
            "question":     req.question,
            "contexte_rag": contexte,
            "nb_passages":  contexte.count("####") if contexte else 0,
            "pays":         pays,
            "metier":       metier,
        }
    except Exception as e:
        logger.error(f"[routes_pro_agent.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")


# ── Factory d'agents par métier ────────────────────────────────────────────────

def _charger_agent_metier(profil, agent_force: str | None = None):
    """
    Retourne l'agent spécialisé pour le métier du profil.
    agent_force permet au frontend de sélectionner un agent différent du profil.
    Fallback sur AgentProBase si pas d'agent spécialisé.
    """
    from modules.pro.agent_pro_base import AgentProBase

    # Normalisation agent_force → ID métier backend
    _AGENT_FORCE_MAP = {
        "comptable": "comptable", "fiscal": "fiscaliste", "fiscaliste": "fiscaliste",
        "drh": "drh", "rh": "drh", "gestionnaire_rh": "drh",
        "daf": "daf",
        "juriste": "juriste", "juridique": "juriste", "avocat": "juriste",
        "banquier": "banquier", "banque": "banquier", "banquier_finance": "banquier",
        "ingenieur": "ingenieur",
        "daa": "daa", "data_analyst": "daa",
        "commercial": "commercial",
        "charge_projets_ong": "charge_projets_ong", "ong": "charge_projets_ong",
        "responsable_microfinance": "responsable_microfinance", "microfinance": "responsable_microfinance",
        "transitaire": "transitaire", "douanier": "transitaire",
        "cv_emploi": "cv_emploi",
        "recherche_emploi": "recherche_emploi", "veille_emploi": "recherche_emploi",
    }

    if agent_force:
        metier = _AGENT_FORCE_MAP.get(agent_force.lower(), agent_force.lower())
    else:
        metier = (profil.metier or "").lower() if profil else ""

    # Agents spécialisés disponibles
    if metier == "comptable" or metier == "auditeur" or metier == "fiscaliste":
        try:
            from modules.pro.agents.agent_comptable import AgentComptable
            return AgentComptable(profil=profil)
        except ImportError:
            pass

    if metier in ("drh", "gestionnaire_rh"):
        try:
            from modules.pro.agents.agent_drh import AgentDRH
            return AgentDRH(profil=profil)
        except ImportError:
            pass

    if metier == "daf":
        try:
            from modules.pro.agents.agent_daf import AgentDAF
            return AgentDAF(profil=profil)
        except ImportError:
            pass

    if metier in ("juriste", "avocat", "notaire", "juriste_entreprise"):
        try:
            from modules.pro.agents.agent_juriste import AgentJuriste
            return AgentJuriste(profil=profil)
        except ImportError:
            pass

    if metier in ("banquier", "analyste_credit", "trader", "gestionnaire_actifs", "financier"):
        try:
            from modules.pro.agents.agent_banquier import AgentBanquier
            return AgentBanquier(profil=profil)
        except ImportError:
            pass

    if metier in ("ingenieur", "chef_projet", "architecte", "conducteur_travaux"):
        try:
            from modules.pro.agents.agent_ingenieur import AgentIngenieur
            return AgentIngenieur(profil=profil)
        except ImportError:
            pass

    if metier in ("daa", "data_analyst", "data_scientist", "statisticien"):
        try:
            from modules.pro.agents.agent_daa import AgentDAA
            return AgentDAA(profil=profil)
        except ImportError:
            pass

    if metier in ("directeur_commercial", "commercial", "entrepreneur", "consultant", "acheteur"):
        try:
            from modules.pro.agents.agent_commercial import AgentCommercial
            return AgentCommercial(profil=profil)
        except ImportError:
            pass

    if metier in ("charge_projets_ong", "coordinateur_ong", "charge_programme", "responsable_ong",
                  "charge_de_projet", "charge_projet_ong"):
        try:
            from modules.pro.agents.agent_ong import AgentONG
            return AgentONG(profil=profil)
        except ImportError:
            pass

    if metier in ("responsable_microfinance", "credit_officer", "agent_microfinance",
                  "directeur_sfd", "gestionnaire_imf", "agent_sfd"):
        try:
            from modules.pro.agents.agent_microfinance import AgentMicrofinance
            return AgentMicrofinance(profil=profil)
        except ImportError:
            pass

    if metier in ("transitaire", "douanier", "agent_transit", "agent_douane",
                  "declarant_douane", "freight_forwarder", "commerce_international"):
        try:
            from modules.pro.agents.agent_douanier import AgentDouanier
            return AgentDouanier(profil=profil)
        except ImportError:
            pass

    if metier in ("cv_emploi", "candidat") or metier == "pro_cv_emploi":
        try:
            from modules.pro.agents.agent_cv_emploi import AgentCVEmploi
            return AgentCVEmploi(profil=profil)
        except ImportError:
            pass

    if metier in ("veille_emploi", "job_search", "recherche_emploi") or metier == "pro_recherche_emploi":
        try:
            from modules.pro.agents.agent_recherche_emploi import AgentRechercheEmploi
            return AgentRechercheEmploi(profil=profil)
        except ImportError:
            pass

    # Fallback : agent généraliste
    return AgentProBase(profil=profil)
