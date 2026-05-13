"""Classifier d'intent sémantique pour le chat YukpoPro.

Le chat front a historiquement utilisé des regex pour router les briefs
vers le bon pipeline (landing / site / visuel / vidéo / formulaire / etc.).
Limitation : la sémantique échappe aux mots-clés ("génère le portail
web de mon agence" = site web ; "fais-moi un visuel pour mon cabinet"
peut être un site ou un flyer selon le contexte).

Ce module appelle un LLM RAPIDE (Haiku 4.5 / GPT-4.1-nano) qui analyse
le brief et retourne un INTENT classifié + confidence. Le frontend
combine ce résultat avec ses regex (cas évidents = regex prend, cas
ambigus = LLM tranche).

Coût : ~50-200 tokens × Haiku = < 0.5 crédit / classification. Cached
30 min sur prompt identique pour économiser les répétitions.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.chat_intent")

router = APIRouter()


class ClassifierIntentRequest(BaseModel):
    brief: str = Field(..., min_length=3, max_length=4000,
        description="Texte libre du user (message chat)")
    has_files: bool = Field(default=False,
        description="True si des fichiers sont attachés au message")


# Liste fermée d'intents que le LLM doit choisir
_INTENTS_VALIDES = [
    "site_multipage",        # mini-site web complet (home + services + équipe + …)
    "landing_singlepage",    # landing one-pager (campagne, event, produit unique)
    "boutique_ecommerce",    # YukpoShop (catalogue produits + checkout)
    "visuel_a4_print",       # flyer/affiche/poster imprimable single-page
    "infographie_pro",       # carte visite, brochure, livret print premium
    "slides_web",            # présentation Reveal.js partageable URL
    "slides_pptx",           # PowerPoint téléchargeable
    "video_promo",           # vidéo IA Kling/LTX (5-60s)
    "rapport_docx",          # rapport Word/PDF long
    "enquete_formulaire",    # formulaire XLSForm + collecte réponses
    "article_blog",          # article de blog SEO long
    "modification",          # modification incrémentale (ne pas régénérer)
    "analyse_donnees",       # analyse data (Excel, CSV, charts)
    "traduction",            # traduction document
    "ocr_audio_transcription",  # OCR ou transcription audio
    "agent_recherche",       # question recherche / agent / chat conversation
    "autre",                 # fallback ambigu
]


_PROMPT_SYSTEME = """Tu es un classifieur d'intent pour une plateforme \
SaaS B2B africaine (Yukpo). Tu analyses un brief utilisateur libre et tu \
retournes UN SEUL intent parmi cette liste fermée :

  • site_multipage : l'user veut un MINI-SITE WEB avec plusieurs pages
    (accueil + services + équipe + contact + blog…) — ex. "fais le site
    de mon cabinet d'expertise comptable", "génère mon site internet",
    "monte le site vitrine de mon agence", "j'ai besoin d'une présence
    web pour mon business"
  • landing_singlepage : page web UNIQUE (one-pager, campagne, event,
    lancement produit) — ex. "landing page pour le lancement de X",
    "one-pager event", "page web pour ma promo"
  • boutique_ecommerce : catalogue de produits + panier + checkout —
    ex. "ouvre ma boutique", "vendre en ligne", "magasin e-commerce",
    "yukposhop"
  • visuel_a4_print : affiche / flyer / poster / bannière imprimable
    single-page — ex. "fais un flyer", "affiche promo", "bannière"
  • infographie_pro : carte de visite, brochure multi-pages, livret,
    catalogue print, programme événement — ex. "20 cartes de visite",
    "brochure 8 pages", "livret cérémonie"
  • slides_web : présentation interactive HTML (Reveal.js) avec URL
    partageable — ex. "slides web", "présentation interactive en ligne"
  • slides_pptx : PowerPoint téléchargeable — ex. "slides", "ppt",
    "présentation pour réunion"
  • video_promo : vidéo IA 5-60s — ex. "fais une vidéo promo", "reel",
    "spot pub vidéo", "teaser"
  • rapport_docx : rapport Word/PDF long structuré — ex. "rapport
    annuel", "DOCX 20 pages", "audit DSF"
  • enquete_formulaire : formulaire collecte de données (XLSForm) —
    ex. "questionnaire satisfaction", "sondage", "audit conformité",
    "formulaire d'enquête"
  • article_blog : article de blog long SEO — ex. "rédige un article",
    "blog sur la fiscalité"
  • modification : modification INCRÉMENTALE d'un contenu existant —
    ex. "change le titre", "modifie la page services", "remplace X par Y"
  • analyse_donnees : analyse d'un dataset / Excel / CSV — ex. "analyse
    ces ventes", "graphique des résultats"
  • traduction : traduction d'un texte/document
  • ocr_audio_transcription : extraction texte image OU transcription audio
  • agent_recherche : question simple / recherche / chat conversationnel
    sans génération de fichier — ex. "que pense-tu de…", "explique-moi…"
  • autre : ne correspond clairement à aucune catégorie

RÈGLES IMPORTANTES :
1. La SÉMANTIQUE prime sur les mots-clés. "Présence web", "vitrine en
   ligne", "page web professionnelle", "portail entreprise" = très
   probablement site_multipage si plusieurs aspects business mentionnés.
2. "Visuel" + contexte cabinet/entreprise/agence avec MULTIPLES services
   ou équipe = plus probablement site_multipage qu'un flyer A4.
3. "Boutique" / "vendre" / "produits" avec prix/stock = boutique_ecommerce.
4. Si le brief mentionne PLUSIEURS pages/sections/services/équipe →
   site_multipage (pas landing).
5. Si AMBIGU entre 2 intents proches, choisis le plus VOLUMINEUX/COMPLET
   (site > landing > flyer).
6. Si has_files=True (le user a joint un fichier) : c'est probablement
   modification, ocr_audio_transcription, traduction ou analyse_donnees.

Tu RENVOIES UN JSON STRICT (pas de texte avant/après) :
{
  "intent": "site_multipage",
  "confidence": 0.85,
  "raison": "Brief mentionne cabinet + multiples aspects business (analyses, conseils stratégiques, contact, équipe)",
  "indicateurs_secondaires": ["boutique_ecommerce", "landing_singlepage"]
}

`confidence` : 0.0-1.0. Si < 0.5 → mets "autre" et liste indicateurs.
`indicateurs_secondaires` : autres intents probables, par ordre de probabilité.
"""


@router.post(
    "/chat/classify-intent",
    summary="Classifier d'intent sémantique via LLM Haiku (40-200 tokens)",
)
async def classifier_intent(
    payload: ClassifierIntentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """LLM rapide → classifie le brief en un intent défini.

    Le frontend chat combine ce résultat avec ses regex :
    - Regex match clair → utilise la regex (rapide)
    - Regex ambigu/multiple → utilise l'intent LLM
    - Regex aucun match → LLM tranche

    Latence cible : 1-2s (Haiku/GPT-4.1-nano). Cache 30 min.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    user_prompt = (
        f"BRIEF UTILISATEUR :\n{payload.brief[:2000]}\n\n"
        f"has_files = {payload.has_files}\n\n"
        f"Classifie cet intent."
    )
    try:
        rep = await ia_client.appeler(
            prompt=user_prompt,
            systeme=_PROMPT_SYSTEME,
            mode=ModeIA.PRECISION,
            max_tokens_override=600,
            json_attendu=True,
            utiliser_cache=True,
            cache_ttl=1800,  # 30 min — un même brief = même intent
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,  # rapide + pas cher
        )
    except Exception as e:
        logger.warning(f"[Chat/intent] LLM échec : {e}")
        return {
            "intent": "autre", "confidence": 0.0,
            "raison": "Classifier LLM indisponible — fallback regex frontend",
            "indicateurs_secondaires": [],
        }

    texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
    m = re.search(r"\{[\s\S]*\}", texte)
    if not m:
        return {
            "intent": "autre", "confidence": 0.0,
            "raison": "Réponse LLM non parseable",
            "indicateurs_secondaires": [],
        }
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"intent": "autre", "confidence": 0.0,
                "raison": "JSON LLM invalide", "indicateurs_secondaires": []}

    # Validation : l'intent doit être dans la liste fermée
    intent = data.get("intent")
    if intent not in _INTENTS_VALIDES:
        logger.info(f"[Chat/intent] intent hors liste : {intent}")
        intent = "autre"

    # Débit forfait existant (très léger ~50 cr pour Haiku 200 tokens)
    try:
        from modules.bureau.service_credits_bureau import debiter_llm_unifie
        await debiter_llm_unifie(
            user_id=current_user.user_id,
            modele=getattr(rep, "modele_utilise", "claude-haiku-4-5"),
            tokens_input=int(getattr(rep, "tokens_input", 0) or 0),
            tokens_output=int(getattr(rep, "tokens_output", 0) or 0),
            module="chat_classify_intent",
        )
    except Exception:
        pass

    return {
        "intent": intent,
        "confidence": float(data.get("confidence", 0.0)),
        "raison": (data.get("raison") or "")[:300],
        "indicateurs_secondaires": data.get("indicateurs_secondaires", [])[:5],
        "_model": getattr(rep, "modele_utilise", "haiku"),
    }
