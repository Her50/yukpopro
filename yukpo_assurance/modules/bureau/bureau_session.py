"""
Bureau Session — gestion unifiée de la session de chat bureau pour
modifications incrémentales sur TOUS les pipelines de génération
(infographe mono, freeform, designer_pro, rapport, slides, geometric).

Sans ce module : chaque message user → régénération from scratch (perte
de cohérence, coût LLM ×2, pas de "suite logique").

Avec ce module : l'utilisateur reçoit un visuel/document, puis dit
"change la couleur en bleu" / "ajoute une page" / "supprime la section 3"
→ le détecteur Sonnet classe `intent ∈ {nouvelle_demande, modification}`,
et si modification → route vers `/modifier` du pipeline mémorisé avec le
`dernier_fichier_id` + le contexte (`dernier_brief`, `dernier_layout_json`).

TTL session : 30 minutes après dernière interaction. Au-delà → considéré
comme nouvelle demande (l'user revient sur un sujet différent).
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Literal, Optional

from sqlalchemy import select

logger = logging.getLogger("yukpo_assurance.bureau.session")

# ─── Pipelines reconnus (sources et cibles de modification) ──────────────────
Pipeline = Literal[
    "infographe",        # mono-page catalog (gabarits figés)
    "freeform",          # LLM-composed layout libre — TOUT visuel composite
                         # (carte, flyer, affiche, banderole, faire-part,
                         # brochure, livret simple, diplôme, certificat, badge,
                         # ticket, programme, catalogue, carton invitation,
                         # menu, poster, étiquette produit, coupon, etc.)
    "designer_pro",      # multi-page Designer Pro catalog (livret, brochure,
                         # livre photo, magazine, rapport annuel — gabarits
                         # multi-page enrichis avec gestion médias)
    "rapport",           # DOCX rapport
    "slides",            # PPTX presentation
    "geometric",         # geometric_placement (LLM vision + Python math)
]

SESSION_TTL_MIN = 30  # minutes d'inactivité avant expiration


async def get_or_create_session(user_id: int) -> "BureauSessionDB":
    """
    Retourne la session active de l'utilisateur (créée si aucune dans le TTL).
    Une seule session active à la fois — la plus récente.
    """
    from core.database import BureauSessionDB, async_session_maker
    cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MIN)
    async with async_session_maker() as db:
        res = await db.execute(
            select(BureauSessionDB).where(
                BureauSessionDB.user_id == user_id,
                BureauSessionDB.derniere_interaction >= cutoff,
            ).order_by(BureauSessionDB.derniere_interaction.desc()).limit(1)
        )
        sess = res.scalar_one_or_none()
        if sess is not None:
            return sess
        sess = BureauSessionDB(
            session_id=str(uuid.uuid4()), user_id=user_id,
            pipeline=None, dernier_fichier_id=None,
            dernier_brief=None, dernier_layout_json=None,
            historique=[],
        )
        db.add(sess)
        await db.commit()
        await db.refresh(sess)
        return sess


async def update_session_apres_generation(
    user_id: int,
    pipeline: Pipeline,
    fichier_id: str,
    brief: str,
    layout_json: Optional[dict] = None,
) -> None:
    """
    Met à jour la session APRÈS chaque génération réussie. Appelé par chaque
    route /generer ou pipeline async pour mémoriser le dernier fichier.
    """
    from core.database import BureauSessionDB, async_session_maker
    async with async_session_maker() as db:
        sess = await get_or_create_session(user_id)
        # Re-fetch dans la même session SQLAlchemy pour update
        res = await db.execute(
            select(BureauSessionDB).where(BureauSessionDB.session_id == sess.session_id)
        )
        s = res.scalar_one_or_none()
        if s is None:
            return
        s.pipeline = pipeline
        s.dernier_fichier_id = fichier_id
        s.dernier_brief = (brief or "")[:2000]
        s.dernier_layout_json = layout_json
        s.derniere_interaction = datetime.utcnow()
        # Historique tronqué à 30 messages
        hist = list(s.historique or [])
        hist.append({
            "role": "yukpo",
            "ts": datetime.utcnow().isoformat(),
            "fichier_id": fichier_id,
            "pipeline": pipeline,
            "brief_court": (brief or "")[:300],
        })
        s.historique = hist[-30:]
        await db.commit()


# ─── Détecteur d'intent : modification vs nouvelle demande ───────────────────

PROMPT_INTENT_SYSTEME = """Tu es CLASSIFIEUR D'INTENT pour un chat bureau IA.

L'utilisateur a (peut-être) reçu un document généré il y a quelques instants,
et il envoie maintenant un nouveau message. Tu dois déterminer si :
  - "nouvelle_demande"  : l'user demande un NOUVEAU document totalement
                          différent (sujet, format, type changent).
  - "modification"      : l'user veut MODIFIER le dernier document généré
                          (touche ciblée : couleur, texte, page ajoutée,
                          section supprimée, élément déplacé…).
  - "ambigu"            : impossible de trancher sans plus de contexte
                          (par défaut traiter comme "nouvelle_demande").

INDICATEURS de MODIFICATION :
  • Mots-clés : "change", "modifie", "remplace", "ajoute" (à l'existant),
    "supprime", "enlève", "déplace", "agrandis", "réduis", "corrige",
    "améliore", "refais", "encore", "même chose mais", "comme avant mais"
  • Référence implicite : "le titre" (= titre du doc précédent), "cette
    couleur", "ce visuel", "cette page", "ces cartes"
  • Pas de nouvelle entité sujet introduite : continue sur le même contexte
  • Continuité immédiate (< 5 minutes après dernier doc) renforce probabilité

INDICATEURS de NOUVELLE DEMANDE :
  • Sujet/entité radicalement différent ("génère un rapport CIMA" après
    une carte de visite = nouvelle demande, même si user dit "et maintenant")
  • Type de document différent demandé (rapport vs carte vs slide)
  • Mention explicite "nouveau", "autre", "différent"
  • Long délai depuis dernier doc (mais le TTL session de 30 min gère ça)

SORTIE JSON STRICT :
{
  "intent": "modification" | "nouvelle_demande" | "ambigu",
  "confiance": 0.0..1.0,
  "raison": "1 phrase explicative"
}
"""


async def detecter_intent_modification(
    user_message: str,
    dernier_brief: Optional[str],
    dernier_fichier_id: Optional[str],
    dernier_pipeline: Optional[str],
) -> tuple[str, float, dict]:
    """
    Classe le user_message en {modification, nouvelle_demande, ambigu}.

    Retourne (intent, confiance, usage_llm). usage_llm pour facturation
    via debiter_llm par l'appelant.

    Si pas de session active (dernier_fichier_id=None) → automatiquement
    "nouvelle_demande" sans appel LLM (économie).
    """
    if not dernier_fichier_id or not dernier_brief:
        return "nouvelle_demande", 1.0, {"modele": "", "tokens_in": 0, "tokens_out": 0}

    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    user_prompt = (
        f"DERNIER DOCUMENT GÉNÉRÉ :\n"
        f"  • pipeline : {dernier_pipeline or 'inconnu'}\n"
        f"  • fichier_id : {dernier_fichier_id}\n"
        f"  • brief original : \"\"\"{(dernier_brief or '')[:800]}\"\"\"\n\n"
        f"NOUVEAU MESSAGE DE L'UTILISATEUR :\n"
        f"\"\"\"{user_message[:1500]}\"\"\"\n\n"
        f"Classe l'intent. JSON strict, sans markdown."
    )

    try:
        rep = await ia_client.appeler(
            prompt=user_prompt,
            systeme=PROMPT_INTENT_SYSTEME,
            mode=ModeIA.PRECISION,
            # Sonnet : la nuance modification/nouvelle est subtile (ex:
            # "et maintenant fais pareil pour la mairie" → modification
            # OU nouvelle ? dépend du contexte). Haiku rate ces nuances.
            forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
            json_attendu=True,
            max_tokens_override=300,
            utiliser_cache=False,
        )
    except Exception as e:
        logger.warning(f"[BureauSession/Intent] LLM échec : {e}")
        return "nouvelle_demande", 0.5, {"modele": "", "tokens_in": 0, "tokens_out": 0}

    usage = {
        "modele": getattr(rep, "modele_utilise", "") or "",
        "tokens_in": int(getattr(rep, "tokens_input", 0) or 0),
        "tokens_out": int(getattr(rep, "tokens_output", 0) or 0),
    }
    raw = (rep.contenu or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return "nouvelle_demande", 0.5, usage
        try:
            data = json.loads(m.group())
        except Exception:
            return "nouvelle_demande", 0.5, usage
    intent = data.get("intent", "nouvelle_demande")
    if intent not in ("modification", "nouvelle_demande", "ambigu"):
        intent = "nouvelle_demande"
    try:
        confiance = float(data.get("confiance", 0.7))
    except Exception:
        confiance = 0.7
    return intent, confiance, usage


async def reset_session(user_id: int) -> None:
    """
    Force l'expiration de la session courante (= prochaine génération =
    nouvelle session). Utilisé par le bouton "Nouvelle conversation" du chat.
    """
    from core.database import BureauSessionDB, async_session_maker
    async with async_session_maker() as db:
        res = await db.execute(
            select(BureauSessionDB).where(BureauSessionDB.user_id == user_id)
            .order_by(BureauSessionDB.derniere_interaction.desc()).limit(1)
        )
        sess = res.scalar_one_or_none()
        if sess is not None:
            # Pousse derniere_interaction très loin dans le passé → expire
            sess.derniere_interaction = datetime.utcnow() - timedelta(hours=24)
            await db.commit()
