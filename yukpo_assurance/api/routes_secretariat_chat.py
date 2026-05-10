"""
Sprint S1 — Chat Unifié YukpoSecrétariat.

Un SEUL endpoint qui détecte ce que l'utilisateur veut faire (rédaction, OCR,
transcription audio, infographie mono-page, infographie pro multi-page,
traduction, traduction de fichier) et retourne le routage suggéré pour le
frontend.

Plus de tabs séparés. L'utilisateur tape un message + (optionnel) attache un
fichier (image/PDF/audio) ou un message vocal → Yukpo route automatiquement.

Intentions classifiées (Haiku 4.5, ~80 tokens, ~0.1 FCFA réel) :
  - redaction        : "rédige une lettre de motivation pour..." / "écris-moi un courrier..."
  - ocr_image        : fichier image attaché → /bureau/ocr/scanner
  - ocr_manuscrit    : "transcris ce manuscrit" + image → /bureau/ocr/manuscrit
  - audio_transcrire : fichier audio attaché → /bureau/audio/transcrire
  - infographie_mono : "carte de visite", "flyer A5", "diplôme" → /bureau/infographie
  - designer_pro     : "livret 8 pages", "brochure", "magazine" → /bureau/infographie-pro
  - traduction_texte : "traduis ce texte en X" → /bureau/traduction/texte
  - traduction_fichier : fichier PDF/DOCX + "traduis" → /bureau/traduction/fichier
  - inconnu          : ambigu → demander clarification

Le backend renvoie {intent, routage: {endpoint, payload_template}, confiance}.
Le frontend regarde et appelle l'endpoint approprié automatiquement.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.secretariat_chat")
router = APIRouter()


_INTENTS = (
    "redaction", "ocr_image", "ocr_manuscrit", "audio_transcrire",
    "infographie_mono", "designer_pro", "traduction_texte", "traduction_fichier",
    "inconnu",
)


class SecChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=5000)
    has_image: bool = Field(default=False,
        description="Si l'user a attaché une image (jpg/png) → OCR/Designer Pro réf. style")
    has_pdf: bool = Field(default=False,
        description="Si l'user a attaché un PDF → OCR/traduction fichier")
    has_audio: bool = Field(default=False,
        description="Si l'user a attaché un audio (mp3/wav/m4a) → transcription")
    pays: str = Field(default="CM")
    langue: str = Field(default="fr")


class SecChatMessageResponse(BaseModel):
    intent: str
    confiance: float
    raison: str
    routage: dict
    suggestion_questions: list[str] = Field(default_factory=list)


@router.post("/message", response_model=SecChatMessageResponse,
             tags=["Secrétariat — Chat Unifié"])
async def chat_unifie_message(
    demande: SecChatMessageRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Sprint S1 — Détecte ce que l'user veut faire et retourne le routage.

    Le frontend appelle cet endpoint en premier puis route :
      - intent='redaction' → POST /bureau/redaction/generer
      - intent='ocr_image' → POST /bureau/ocr/scanner avec l'image jointe
      - intent='audio_transcrire' → POST /bureau/audio/transcrire avec l'audio
      - intent='designer_pro' → POST /bureau/infographie-pro/chat/message (sous-chat C1)
      - intent='infographie_mono' → POST /bureau/infographie/generer
      - intent='traduction_texte' → POST /bureau/traduction/texte
      - intent='traduction_fichier' → POST /bureau/traduction/fichier
      - intent='inconnu' → afficher suggestion_questions à l'user
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    import json
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, debiter_llm,
    )

    # Pas de blocage acces : toutes les intentions Sec valides → on accepte
    autorise, plan, _ = await verifier_acces_module(current_user.user_id, "documents")
    if not autorise:
        # Fallback : redaction (la plupart des plans secrétariat ont accès)
        autorise, plan, _ = await verifier_acces_module(current_user.user_id, "redaction")

    # Phase 3 — Contexte vertical métier (profil + fallback brief si vide)
    bloc_vertical_sec = ""
    try:
        from core.database import async_session_maker as _asm
        from modules.pro.service_profil import get_or_create as _get_profil
        from modules.bureau import verticales_metier as _vm
        async with _asm() as _db:
            profil_obj, _ = await _get_profil(current_user.user_id, _db)
        metier = getattr(profil_obj, "metier", None) or ""
        secteur = getattr(profil_obj, "secteur_activite", None) or ""
        pays_user = getattr(profil_obj, "pays", None) or demande.pays or None
        # Verticalité DYNAMIQUE LLM : couvre TOUS secteurs mondiaux
        descripteur_vert = await _vm.detecter_vertical_dynamique_llm(
            metier=metier, secteur=secteur, pays=pays_user, brief=demande.message,
        )
        if descripteur_vert:
            bloc_vertical_sec = _vm.construire_bloc_prompt_vertical(
                pays=pays_user, descripteur=descripteur_vert,
            )
    except Exception:
        pass

    contexte_attachments = []
    if demande.has_image: contexte_attachments.append("image (jpg/png)")
    if demande.has_pdf: contexte_attachments.append("PDF")
    if demande.has_audio: contexte_attachments.append("audio (mp3/wav/m4a)")
    ctx_attach = (
        f"Attachements : {', '.join(contexte_attachments)}"
        if contexte_attachments else "Aucun fichier attaché."
    )

    prompt = (
        f"Tu es ASSISTANT D'ORCHESTRATION pour YukpoSecrétariat. L'utilisateur tape\n"
        f"un message + (optionnel) attache un fichier. Tu dois détecter son INTENTION\n"
        f"parmi 9 catégories.\n\n"
        f"MESSAGE : «{demande.message[:2000]}»\n"
        f"{ctx_attach}\n"
        f"Pays : {demande.pays}   Langue : {demande.langue}\n"
        f"{bloc_vertical_sec}\n"
        f"INTENTIONS POSSIBLES :\n"
        f"  - redaction          : l'user veut RÉDIGER un texte (lettre, courrier, email,\n"
        f"    note, contrat, mémo, CV, motivation, communiqué, rapport, etc.)\n"
        f"  - ocr_image          : l'user a attaché une IMAGE et veut en extraire le texte\n"
        f"    (\"scanne ce document\", \"extrais le texte\", \"OCR\")\n"
        f"  - ocr_manuscrit      : OCR mais sur un texte MANUSCRIT (\"transcris cette note\n"
        f"    écrite à la main\")\n"
        f"  - audio_transcrire   : audio attaché + l'user veut transcription / minutes /\n"
        f"    compte-rendu de réunion / dictée (\"transcris cet audio\", \"compte-rendu\")\n"
        f"  - infographie_mono   : visuel UNE seule page : carte de visite, flyer A5/A4,\n"
        f"    affiche A3/A2, faire-part recto unique, diplôme, en-tête, banderole,\n"
        f"    carte de vœux. Mots-clés : \"carte de visite\", \"flyer\", \"affiche\",\n"
        f"    \"diplôme\", \"badge\", \"étiquette\".\n"
        f"  - designer_pro       : visuel MULTI-PAGE (livret, brochure, magazine, livre\n"
        f"    photo, programme cérémonie/culte, rapport annuel, faire-part livret,\n"
        f"    menu restaurant). Mots-clés : \"livret\", \"brochure\", \"livre photo\",\n"
        f"    \"magazine\", \"X pages\", \"plié\", \"programme cérémonie\".\n"
        f"  - traduction_texte   : traduire un TEXTE saisi inline (\"traduis: bonjour…\n"
        f"    en anglais\")\n"
        f"  - traduction_fichier : PDF/DOCX attaché + \"traduis ce document en X\"\n"
        f"  - inconnu            : si vraiment ambigu — pose questions de clarification\n\n"
        f"RÈGLES :\n"
        f"  1. Si fichier audio attaché → presque toujours audio_transcrire\n"
        f"     (sauf si l'user dit explicitement autre chose)\n"
        f"  2. Si fichier image attaché + mots OCR/scan → ocr_image\n"
        f"  3. Si fichier PDF attaché + \"traduis\" → traduction_fichier\n"
        f"  4. Si pas d'attachement et message court (\"flyer pour mon resto\")\n"
        f"     → infographie_mono ou designer_pro selon mots-clés\n"
        f"  5. Reste suggéré : si confiance < 0.75, propose 1-2 questions de\n"
        f"     clarification dans 'suggestion_questions'.\n\n"
        f"FORMAT JSON STRICT :\n"
        f"{{\n"
        f'  "intent": "...", "confiance": 0.92, "raison": "...",\n'
        f'  "suggestion_questions": ["...", "..."]\n'
        f"}}\n\n"
        f"Retourne UNIQUEMENT le JSON."
    )

    try:
        rep = await ia_client.appeler(
            prompt=prompt, mode=ModeIA.PRECISION, json_attendu=True,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
            max_tokens_override=300, utiliser_cache=True,
        )
    except Exception as e:
        logger.error(f"[SecChat] LLM échec : {e}")
        raise HTTPException(500, f"Orchestrateur indisponible : {e}")

    try:
        data = json.loads(rep.contenu)
    except Exception:
        import re
        m = re.search(r'\{.*\}', rep.contenu, re.DOTALL)
        data = json.loads(m.group()) if m else {"intent": "inconnu", "confiance": 0.0}

    intent = data.get("intent", "inconnu")
    if intent not in _INTENTS:
        intent = "inconnu"

    # Routage explicite par intent (frontend appelle l'endpoint cible)
    routage_par_intent = {
        "redaction": {
            "endpoint": "/api/v1/bureau/redaction/generer",
            "method": "POST",
            "payload_template": {
                "type_doc": "lettre",   # à raffiner par sous-classification si besoin
                "brief": demande.message, "pays": demande.pays, "langue": demande.langue,
            },
            "hint": "L'API retourne fichier_id + texte généré, à télécharger via /redaction/fichier/{id}",
        },
        "ocr_image": {
            "endpoint": "/api/v1/bureau/ocr/scanner", "method": "POST",
            "payload_template": {"_form_data": True, "fichier": "<image attached>"},
            "hint": "Multipart : envoyer l'image en form data sous 'fichier'.",
        },
        "ocr_manuscrit": {
            "endpoint": "/api/v1/bureau/ocr/manuscrit", "method": "POST",
            "payload_template": {"_form_data": True, "fichier": "<image attached>"},
            "hint": "Multipart : envoyer l'image manuscrite.",
        },
        "audio_transcrire": {
            "endpoint": "/api/v1/bureau/audio/transcrire", "method": "POST",
            "payload_template": {"_form_data": True, "audio": "<audio attached>",
                                  "type_doc": "transcription"},
            "hint": "Multipart : envoyer l'audio en form data.",
        },
        "infographie_mono": {
            "endpoint": "/api/v1/bureau/infographie/generer", "method": "POST",
            "payload_template": {
                "brief": demande.message, "pays": demande.pays,
                "type_gabarit": "auto",   # backend doit auto-detecter via brief
            },
            "hint": "Le backend infographie auto-detecte le type_gabarit selon le brief.",
        },
        "designer_pro": {
            # Bascule sur le sous-chat conversationnel C1 (intent C1 va re-router
            # vers /generer-auto ou /modifier selon projet_actif Designer Pro)
            "endpoint": "/api/v1/bureau/infographie-pro/chat/message", "method": "POST",
            "payload_template": {
                "message": demande.message, "pays": demande.pays, "langue": demande.langue,
            },
            "hint": "Bascule sur le chat conversationnel Designer Pro (Sprint C1) pour intent fin.",
        },
        "traduction_texte": {
            "endpoint": "/api/v1/bureau/traduction/texte", "method": "POST",
            "payload_template": {
                "contenu": demande.message,
                "langue_source": "auto", "langue_cible": demande.langue,
            },
            "hint": "Si la langue cible n'est pas explicite dans le message, demander clarif.",
        },
        "traduction_fichier": {
            "endpoint": "/api/v1/bureau/traduction/fichier", "method": "POST",
            "payload_template": {"_form_data": True, "fichier": "<file attached>",
                                  "langue_cible": demande.langue},
            "hint": "Multipart : envoyer le PDF/DOCX. Langue cible doit être extraite du msg.",
        },
        "inconnu": {
            "endpoint": None, "method": None, "payload_template": {},
            "hint": "Afficher suggestion_questions à l'utilisateur.",
        },
    }
    routage = routage_par_intent.get(intent, routage_par_intent["inconnu"])

    # Débit LLM Haiku tracé
    try:
        await debiter_llm(
            current_user.user_id, modele=rep.modele_utilise,
            tokens_input=int(rep.tokens_input or 0),
            tokens_output=int(rep.tokens_output or 0),
            module="documents",
        )
    except Exception:
        pass

    return SecChatMessageResponse(
        intent=intent, confiance=float(data.get("confiance", 0.5)),
        raison=str(data.get("raison", ""))[:300], routage=routage,
        suggestion_questions=(data.get("suggestion_questions") or [])[:3],
    )


# ─── Phase 3 — Recherche officielle temps réel (sites mondiaux) ──────────────


class DemandeRechercheOfficielle(BaseModel):
    question: str = Field(..., min_length=5, max_length=500,
        description="Question réglementaire/métier (ex: 'délai de préavis CDI', 'AMM antibiotique', 'durée bail commercial')")
    vertical: Optional[str] = Field(default=None,
        description="banque_finance | pharma_sante | immobilier | education | rh_paie. Si null, auto-détection profil.")
    pays: Optional[str] = Field(default=None, max_length=3,
        description="Code ISO 3166-1 alpha-2 du pays user (CM, FR, US, IN, BR…). Si null, profil utilisé.")


@router.post("/recherche-officielle", tags=["Secrétariat — Chat Unifié"])
async def recherche_officielle_endpoint(
    demande: DemandeRechercheOfficielle,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Phase 3 — Recherche web officielle temps réel par vertical métier.
    Pas de RAG figé. Utilise Serper.dev sur sites officiels mondiaux + nationaux
    selon vertical et pays.

    Retourne {sources_trouvees, extraits, raison_echec}.
    Si SERPER_API_KEY absent → raison_echec explicite, le LLM bascule sur ses
    connaissances natives en signalant "à vérifier".
    """
    from modules.bureau import (
        recherche_officielle_metier as _rom,
        verticales_metier as _vm,
    )
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, debiter_forfait,
    )

    # Vertical : explicite ou détecté depuis profil
    vert_key = demande.vertical
    pays = demande.pays
    if not vert_key or not pays:
        try:
            from core.database import async_session_maker as _asm
            from modules.pro.service_profil import get_or_create as _get_profil
            async with _asm() as _db:
                profil_obj, _ = await _get_profil(current_user.user_id, _db)
            if not vert_key:
                vert_key = _vm.detecter_vertical(
                    getattr(profil_obj, "metier", "") or "",
                    getattr(profil_obj, "secteur_activite", "") or "",
                )
            if not pays:
                pays = getattr(profil_obj, "pays", None)
        except Exception:
            pass

    autorise, plan, _ = await verifier_acces_module(current_user.user_id, "documents")
    if not autorise:
        raise HTTPException(403, "Module documents non autorisé")

    result = await _rom.chercher_reglementation(
        question=demande.question, vertical=vert_key, pays=pays,
    )

    # Débit léger (1 FCFA = 20 cr) — couvre 1 appel Serper (~$0.001)
    try:
        await debiter_forfait(current_user.user_id, "document_download",
                              module="documents", multiplicateur=1.0)
    except Exception:
        pass

    return {
        "ok": result.get("raison_echec") is None,
        "vertical_utilisee": vert_key,
        "pays_utilise": pays,
        **result,
    }


# ─── Phase 3 — Diagnostic verticales métier ──────────────────────────────────


@router.get("/verticales", tags=["Secrétariat — Chat Unifié"])
async def diagnostic_verticales(current_user: TokenData = Depends(get_current_user)):
    """
    Phase 3 — Retourne la vertical détectée pour cet user (silencieux) +
    le catalogue complet des secteurs supportés. Endpoint de debug pour vérifier
    que le contexte vertical s'injecte bien depuis le profil.
    """
    from modules.bureau import verticales_metier as _vm
    try:
        from core.database import async_session_maker as _asm
        from modules.pro.service_profil import get_or_create as _get_profil
        async with _asm() as _db:
            profil_obj, _ = await _get_profil(current_user.user_id, _db)
        metier = getattr(profil_obj, "metier", None) or ""
        secteur = getattr(profil_obj, "secteur_activite", None) or ""
    except Exception:
        metier = secteur = ""
    detected = _vm.detecter_vertical(metier, secteur)
    return {
        "user_id": current_user.user_id,
        "profil_metier": metier,
        "profil_secteur": secteur,
        "vertical_detectee": detected,
        "vertical_label": (_vm.VERTICALES_METIER.get(detected, {}) or {}).get("label") if detected else None,
        "verticales_supportees": [
            {"key": k, "label": v.get("label"),
             "nb_templates": len(v.get("templates_inspirations", [])),
             "regulations": len(v.get("regulations", []))}
            for k, v in _vm.VERTICALES_METIER.items()
        ],
        "rappel": (
            "Le LLM utilise ce contexte comme inspiration + garde-fous, JAMAIS "
            "comme limite. Si l'user demande hors-catalogue, le LLM invente le "
            "template approprié sur la base des conventions du secteur."
        ),
    }
