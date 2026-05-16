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
    # Contexte session : titre du DERNIER livrable généré dans la conversation
    # courante (chat de session). Permet au LLM de bien arbitrer entre
    # qa_simple ("c'est quoi Taiwan ?" sans lien direct au doc) et
    # modification ("tu peux ajouter une section sur Taiwan ?" qui veut
    # enrichir le rapport existant).
    dernier_doc_titre: Optional[str] = Field(
        default=None, max_length=300,
        description="Titre du dernier livrable généré en session (si existant)",
    )
    dernier_doc_type: Optional[str] = Field(
        default=None, max_length=80,
        description="Type du dernier livrable (rapport/visuel/site/...)",
    )


# Liste fermée d'intents que le LLM doit choisir
_INTENTS_VALIDES = [
    "qa_simple",             # question pure / curiosité / explication / conversation (PRIORITÉ)
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
retournes UN SEUL intent parmi cette liste fermée.

🔴 ARBITRAGE qa_simple vs modification — c'est TOI qui décides
   sémantiquement, pas une règle rigide :

   La forme interrogative seule ne suffit PAS à trancher. Tu dois lire
   l'INTENTION de l'utilisateur :

   → qa_simple : l'utilisateur demande à COMPRENDRE / S'INFORMER /
     DISCUTER sur un sujet, sans intention de toucher au livrable
     existant. Curiosité intellectuelle pure.
     Ex : « pourquoi Taiwan est important pour les Chinois ? »
        « c'est quoi Yukpo Pro ? »
        « comment fonctionne la TVA ? »
        « parle-moi de l'OHADA »
        « que penses-tu de l'IA en Afrique ? »

   → modification : l'utilisateur demande à CHANGER / ENRICHIR / CORRIGER
     un livrable déjà généré dans la session. Même formulée en question
     polie, c'est une INSTRUCTION sur le document.
     Indices typiques (présence d'un VERBE D'ACTION sur le doc, OU
     reproche/correction implicite) :
     Ex : « tu peux ajouter une section sur Taiwan dans le rapport ? »
        « et si on rajoutait des chiffres économiques ? »
        « pourquoi tu n'as pas parlé de la position US ? »
        « modifie l'introduction »
        « change le titre »
        « remplace X par Y »
        « complète la partie 2 »
        « régénère avec plus de profondeur »
        « tu as oublié de citer Y »

   Heuristique en cas d'ambiguïté :
   • Si la question porte sur **le SUJET** du document (curiosité sur
     Taiwan, la TVA, OHADA...) → qa_simple
   • Si la question porte sur **le DOCUMENT lui-même** (son contenu, ses
     manques, sa structure, son ton) → modification
   • Si aucun document n'existe dans la session : aucune raison de
     classer en modification — par défaut qa_simple ou production.

Liste fermée :

  • qa_simple : QUESTION pure / curiosité / explication / opinion /
    discussion conversationnelle sur un SUJET. AUCUN livrable à
    produire ni à modifier. Exemples : "pourquoi Taiwan est important ?",
    "c'est quoi Yukpo Pro ?", "comment fonctionne la TVA ?", "parle-moi
    de l'OHADA", "tu connais le SaaS ?", "bonjour", "explique-moi le
    SYSCOHADA", "que penses-tu de l'IA en Afrique ?".
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
  • enquete_formulaire : étude / formulaire collecte de données
    (XLSForm) — ex. "questionnaire satisfaction", "sondage NPS",
    "audit conformité", "formulaire d'enquête", "étude de marché
    pour lancement produit", "test acceptabilité prix consommateur",
    "enquête terrain bénéficiaires ONG", "étude consommateur jus
    corossol". Une demande commençant par "je souhaite faire / lancer
    / mener une étude / une enquête / un sondage" tombe ici.
  • article_blog : article de blog long SEO — ex. "rédige un article",
    "blog sur la fiscalité"
  • modification : modification INCRÉMENTALE d'un contenu existant —
    ex. "change le titre", "modifie la page services", "remplace X par Y"
  • analyse_donnees : analyse d'un dataset / Excel / CSV — ex. "analyse
    ces ventes", "graphique des résultats"
  • traduction : traduction d'un texte/document
  • ocr_audio_transcription : extraction texte image OU transcription audio
  • agent_recherche : recherche métier qui doit déclencher un agent
    spécialisé (juriste/comptable/RH/…), pas une question généraliste —
    réserve qa_simple aux questions sans besoin d'agent vertical.
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

    # Contexte session : si un livrable a été généré récemment, on l'expose
    # au LLM pour qu'il puisse trancher entre qa_simple et modification en
    # fonction de l'INTENTION sémantique (ajouter/modifier vs simple curiosité).
    contexte_session = ""
    if payload.has_files:
        # Principe pur, pas de keyword listing — le LLM Sonnet a la
        # capacité sémantique de comprendre l'INTENTION sans lexique fermé.
        contexte_session = (
            "\n\n📎 has_files = True (un fichier est joint).\n"
            "L'utilisateur a uploadé un fichier ; tu dois identifier ce qu'il "
            "veut FAIRE de ce fichier. qa_simple ne s'applique presque jamais "
            "ici : un fichier est joint pour être TRAITÉ, pas pour engager "
            "une conversation philosophique.\n"
            "\n"
            "Mappe l'INTENTION sémantique vers l'intent technique.\n"
            "\n"
            "⚠️ DISTINCTION CRITIQUE traduction vs conversion :\n"
            "  - TRADUIRE = changer la LANGUE du contenu. Le format de "
            "sortie reste identique à l'entrée. Verbes : traduire, "
            "translate, traduis, mettre en anglais, passer en arabe… "
            "→ **traduction**\n"
            "  - CONVERTIR / TRANSFORMER + format cible explicite (Word, "
            "docx, Excel, pptx) = changer le FORMAT bureautique, langue "
            "identique. → **ocr_audio_transcription**\n"
            "  Si le brief combine les deux (« traduis ce PDF en Word »), "
            "traduction prime — l'endpoint de traduction sait déjà gérer "
            "le format de sortie.\n"
            "\n"
            "Autres intents :\n"
            "  - exploiter les DONNÉES du fichier (statistiques, "
            "graphiques, insights) → analyse_donnees\n"
            "  - retoucher / enrichir / corriger un livrable précédent → "
            "modification\n"
            "  - condenser le contenu (résumé, synthèse, points-clés) → "
            "rapport_docx\n"
            "  - extraire le texte d'image/audio (lire, transcrire) → "
            "ocr_audio_transcription\n"
            "\n"
            "Tu connais la sémantique du français mieux qu'une regex — "
            "décide à partir du verbe et de l'objet, pas d'une liste."
        )
    if payload.dernier_doc_titre:
        contexte_session += (
            f"\n\n📎 CONTEXTE SESSION — dernier livrable généré :\n"
            f"  • Titre : {payload.dernier_doc_titre[:200]}\n"
            f"  • Type  : {payload.dernier_doc_type or 'document'}\n"
            f"\nSi le brief courant fait référence à CE livrable (l'enrichir, "
            f"corriger, ajouter une section, demander pourquoi tel point manque), "
            f"classe en 'modification'. Si le brief est une question d'info sur "
            f"le SUJET du livrable mais SANS vouloir le modifier (ex : "
            f"l'utilisateur veut juste comprendre, discuter), classe en 'qa_simple'."
        )
    if not payload.has_files and not payload.dernier_doc_titre:
        contexte_session = (
            "\n\nAucun fichier joint ni livrable précédent dans la session. "
            "Si le brief n'est pas une commande de production explicite "
            "(verbe impératif + objet livrable), c'est probablement qa_simple "
            "(chat conversationnel)."
        )

    user_prompt = (
        f"BRIEF UTILISATEUR :\n{payload.brief[:2000]}\n\n"
        f"has_files = {payload.has_files}"
        f"{contexte_session}\n\n"
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
            # Sonnet, pas Haiku : la classification d'intent demande de la
            # nuance sémantique (« convertit ce PDF en Word » avec PDF
            # joint = conversion de format = ocr, pas qa_simple). Haiku
            # 4.5 et GPT-4.1-nano misclassifient sur ces cas → routages
            # ratés et frustration utilisateur. Sonnet 4.6 résout ça
            # naturellement sans liste de mots-clés. Cache 30 min reste
            # actif pour économiser sur les briefs répétés.
            forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
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
