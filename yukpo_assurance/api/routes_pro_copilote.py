"""
Yukpo Copilote Pro — Assistant conversationnel IA toujours présent.

Contrairement au chat /agent qui force l'usage d'un agent métier spécialisé,
le Copilote est un compagnon de travail naturel :
  - Conversation fluide sur TOUT sujet (général, métier, actualité africaine)
  - Mémoire de session (continue la conversation sans répéter le contexte)
  - Détection intelligente du moment où un agent spécialisé est utile
  - Routage transparent vers le bon agent (comptable, DRH, DAF, juriste...)
  - Personnalisation selon le profil métier et le pays de l'utilisateur
  - Supporte les questions hors-métier (general knowledge, rédaction, traduction)

Endpoints :
  POST /api/v1/pro/copilote/chat      — Conversation principale (streaming ou direct)
  POST /api/v1/pro/copilote/nouveau   — Réinitialise la session de conversation
  GET  /api/v1/pro/copilote/historique — Historique de la session en cours
  GET  /api/v1/pro/copilote/suggestion — Suggestions de questions selon profil

Design pattern :
  1. Copilote répond directement pour 80% des requêtes (questions, explications, rédaction)
  2. Si détecte une intention métier calculatoire → appelle l'agent spécialisé silencieusement
  3. Retourne le résultat de l'agent enrichi d'un commentaire naturel du copilote
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import async_session_maker

logger = logging.getLogger("yukpo_assurance.api.pro_copilote")

router = APIRouter()

# Stockage in-memory des sessions copilote (TTL géré par rotation)
# En production : Redis avec TTL de 2h
_SESSIONS: dict[int, dict] = {}
_MAX_MESSAGES_SESSION = 40  # messages conservés en mémoire


async def _generer_titre_document(
    message: str,
    type_doc: str,
    contexte: str = "",
    ia_client=None,
) -> str:
    """
    Produit un titre court, contextuel et professionnel pour un document
    généré depuis le chat. Fallback intelligent si le LLM échoue.

    Le titre ne doit JAMAIS être une recopie brute de la question : le LLM
    reformule en libellé adapté au type de document.
    """
    # Fallback sans LLM : nettoyer la question (retirer impératifs/politesse)
    def _fallback(msg: str, td: str) -> str:
        import re as _re
        base = (msg or "").strip().replace("\n", " ")
        # Retire récursivement les amorces verbales/interrogatives jusqu'à stabilité
        amorces = (
            "est-ce que tu peux me ", "est ce que tu peux me ",
            "est-ce que tu peux ", "est ce que tu peux ",
            "est-ce que tu pourrais ", "est ce que tu pourrais ",
            "est-ce que vous pouvez ", "est ce que vous pouvez ",
            "j'aimerais que tu ", "jaimerais que tu ", "j aimerais que tu ",
            "j'aurais besoin de ", "jaurais besoin de ", "j ai besoin de ",
            "il me faut ", "il faut ",
            "génère-moi ", "génère moi ", "génère ", "genere-moi ", "genere moi ", "genere ",
            "gerer-moi ", "gerer moi ", "gerer ", "gérer-moi ", "gérer moi ", "gérer ",
            "rédige-moi ", "rédige moi ", "rédige ", "redige-moi ", "redige moi ", "redige ",
            "fais-moi ", "fais moi ", "fais ",
            "peux-tu me ", "peux tu me ", "peux-tu ", "peux tu ",
            "pourrais-tu me ", "pourrais tu me ", "pourrais-tu ", "pourrais tu ",
            "pouvez-vous ", "pouvez vous ",
            "merci de ", "s'il te plaît ", "s il te plait ", "stp ", "svp ",
            "crée-moi ", "crée moi ", "crée ", "cree-moi ", "cree moi ", "cree ",
            "prépare-moi ", "prépare moi ", "prépare ", "prepare-moi ", "prepare moi ", "prepare ",
            "donne-moi ", "donne moi ", "donner ",
            "écris-moi ", "écris moi ", "écris ", "ecris-moi ", "ecris moi ", "ecris ",
            "produis-moi ", "produis moi ", "produis ",
            "élabore ", "elabore ", "monte-moi ", "monte moi ", "monte ",
        )
        prev = None
        while prev != base:
            prev = base
            low = base.lower()
            for amorce in amorces:
                if low.startswith(amorce):
                    base = base[len(amorce):].lstrip()
                    break
        # Mots-outils résiduels en tête (un, une, le, la, les, des…)
        base = _re.sub(r"^(?:un |une |le |la |les |des |de |du |d'|d )", "", base, flags=_re.IGNORECASE).strip()
        base = base.strip(" .?!,:;").capitalize()
        if len(base) > 80:
            base = base[:80].rstrip() + "…"
        if not base or len(base) < 4:
            libelle_type = (td or "document").replace("_", " ").title()
            base = libelle_type
        return base

    if ia_client is None:
        return _fallback(message, type_doc)

    from core.ia_client import ModeIA

    ctx_extrait = (contexte or "")[:1500]
    libelle_type = (type_doc or "document").replace("_", " ")

    prompt = (
        "Tu génères un TITRE court et professionnel pour un document.\n\n"
        f"Type de document : {libelle_type}\n"
        f"Demande de l'utilisateur : {message[:500]}\n"
        + (f"\nContexte (extrait) :\n{ctx_extrait}\n" if ctx_extrait else "")
        + "\nContraintes IMPÉRATIVES :\n"
        "- Entre 4 et 10 mots\n"
        "- Français, casse normale (pas de MAJUSCULES)\n"
        "- Ne JAMAIS recopier la phrase de l'utilisateur : la REFORMULER en libellé de document\n"
        "- Pas d'amorce verbale (« Génère », « Rédige »…), pas de guillemets, pas de ponctuation finale\n"
        "- Doit refléter le SUJET, pas l'action demandée\n"
        "- Si un sujet précis ressort (client, projet, période), l'inclure\n\n"
        "Exemples :\n"
        "  \"Rédige-moi un rapport d'analyse crédit pour la PME ABC\" → Rapport d'analyse crédit PME ABC\n"
        "  \"génère un bilan d'activité 2024 pour ma direction commerciale\" → Bilan d'activité 2024 — direction commerciale\n"
        "  \"prépare-moi une note juridique sur la rupture conventionnelle\" → Note juridique sur la rupture conventionnelle\n\n"
        "Réponds UNIQUEMENT par le titre, rien d'autre."
    )

    # Tente jusqu'à 2 fois : un titre LLM est CRITIQUE (sinon la question brute
    # finit dans la page de garde, l'en-tête de page et le slug du fichier).
    _BAD_PREFIXES = ("génère", "genere", "rédige", "redige", "fais", "crée", "cree",
                     "est-ce", "est ce", "peux-tu", "peux tu", "pourrais",
                     "j'aimerais", "jaimerais", "il me faut", "il faut")
    for tentative in (1, 2):
        try:
            reponse = await asyncio.wait_for(
                ia_client.appeler(
                    prompt=prompt,
                    mode=ModeIA.PRECISION,
                    utiliser_cache=(tentative == 1),
                    max_tokens_override=40,
                ),
                timeout=8.0 if tentative == 1 else 12.0,
            )
            titre = (reponse.contenu or "").strip().strip('"').strip("'").strip()
            titre = titre.split("\n")[0].strip(" .?!").strip()
            low = titre.lower()
            if 4 <= len(titre) <= 120 and not low.startswith(_BAD_PREFIXES):
                return titre
            logger.debug(f"[Copilote titre] tentative {tentative} rejetée: {titre!r}")
        except Exception as e:
            logger.debug(f"[Copilote titre] tentative {tentative} LLM échec ({e})")

    return _fallback(message, type_doc)


async def _sauvegarder_doc_db(
    db: AsyncSession,
    user_id: str,
    titre: str,
    type_doc: str,
    fichier: Optional[str],
    contenu_genere: str = "",
    session_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    """Sauvegarde automatique d'un document généré dans DocumentGenereDB (non-bloquant)."""
    try:
        from core.database import DocumentGenereDB
        doc = DocumentGenereDB(
            user_id=user_id,
            titre=titre[:200],
            type_doc=type_doc,
            fichier=fichier,
            contenu_source="",
            contenu_genere=contenu_genere[:5000] if contenu_genere else "",
            session_id=session_id,
            meta=meta or {},
            cree_le=datetime.utcnow(),
            modifie_le=datetime.utcnow(),
        )
        db.add(doc)
        await db.commit()
        logger.debug(f"[DocDB] Document sauvegardé: {titre[:50]} ({type_doc})")
    except Exception as e:
        logger.warning(f"[DocDB] Sauvegarde non-bloquante échouée: {e}")


async def get_db():
    async with async_session_maker() as session:
        yield session


# ── Modèles ───────────────────────────────────────────────────────────────────

class FichierChat(BaseModel):
    nom:     str
    contenu: str   # base64 data URL (data:mime;base64,...)
    type:    str   # MIME type

class DocumentRefChat(BaseModel):
    id:             int
    titre:          str
    type_doc:       str
    contenu_genere: Optional[str] = None

class CopiloteChatRequest(BaseModel):
    message:      str  = Field(..., min_length=1, max_length=8000)
    session_id:   Optional[str] = None
    pays:         Optional[str] = None
    langue:       str = Field("fr", description="fr ou en")
    fichiers:     Optional[List[FichierChat]] = None
    document_ref: Optional[DocumentRefChat] = Field(
        None,
        description="Document existant à améliorer (depuis Mes Documents). "
                    "Force l'intention 'generateur' en mode édition.",
    )


class NouvelleSessionRequest(BaseModel):
    raison: Optional[str] = Field(None, description="Ex: 'nouveau projet', 'sujet différent'")


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _get_session(user_id: int) -> dict:
    """Récupère ou crée une session copilote pour l'utilisateur."""
    if user_id not in _SESSIONS:
        _SESSIONS[user_id] = {
            "session_id": uuid.uuid4().hex,
            "messages": [],
            "cree_le": datetime.utcnow().isoformat(),
            "dernier_message": None,
            "nb_appels_agent": 0,
        }
    return _SESSIONS[user_id]


def _ajouter_message(session: dict, role: str, contenu: str, meta: dict | None = None):
    """Ajoute un message à l'historique de session (FIFO avec max)."""
    session["messages"].append({
        "role": role,
        "content": contenu,
        "ts": datetime.utcnow().isoformat(),
        "meta": meta or {},
    })
    session["dernier_message"] = datetime.utcnow().isoformat()
    # Garder seulement les N derniers messages (paires user/assistant)
    if len(session["messages"]) > _MAX_MESSAGES_SESSION:
        session["messages"] = session["messages"][-_MAX_MESSAGES_SESSION:]


def _construire_historique_claude(messages: list[dict], budget_tokens: int = 2000) -> list[dict]:
    """Convertit l'historique en format messages Claude API (troncature par tokens)."""
    try:
        from core.token_optimizer import construire_historique_optimise
        return construire_historique_optimise(messages, budget_tokens=budget_tokens)
    except Exception:
        return [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]


def _extraire_texte_fichiers(fichiers: list) -> str:
    """Extrait le texte de fichiers base64 (Word, PDF, CSV, TXT, Excel)."""
    if not fichiers:
        return ""
    import base64
    import io

    extraits = []
    for f in fichiers:
        try:
            raw_b64 = f.contenu.split(",", 1)[1] if "," in f.contenu else f.contenu
            raw = base64.b64decode(raw_b64 + "==")
            ext = Path(f.nom).suffix.lower()

            if ext in (".docx", ".doc"):
                try:
                    from docx import Document
                    doc = Document(io.BytesIO(raw))
                    texte = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                except ImportError:
                    texte = "[python-docx non installé — impossible de lire le Word]"
            elif ext == ".pdf":
                try:
                    import pdfplumber
                    parties_pdf = []
                    with pdfplumber.open(io.BytesIO(raw)) as pdf:
                        for num_p, page in enumerate(pdf.pages, 1):
                            txt = page.extract_text() or ""
                            if txt.strip():
                                parties_pdf.append(txt)
                            # Extraire aussi les tableaux en texte tabulaire
                            for tbl in page.extract_tables():
                                if tbl and len(tbl) >= 2:
                                    try:
                                        lignes_tbl = []
                                        for row in tbl:
                                            vals = [str(c).strip() if c else "" for c in row]
                                            lignes_tbl.append(" | ".join(vals))
                                        parties_pdf.append(f"[Tableau page {num_p}]\n" + "\n".join(lignes_tbl))
                                    except Exception:
                                        pass
                    texte = "\n\n".join(parties_pdf)
                except ImportError:
                    try:
                        try:
                            from pypdf import PdfReader as _PdfReader
                        except ImportError:
                            from PyPDF2 import PdfReader as _PdfReader  # type: ignore
                        reader = _PdfReader(io.BytesIO(raw))
                        texte = "\n".join(page.extract_text() or "" for page in reader.pages)
                    except ImportError:
                        texte = "[PDF : pdfplumber ou pypdf requis]"
            elif ext in (".xlsx", ".xls"):
                try:
                    import pandas as pd
                    df = pd.read_excel(io.BytesIO(raw))
                    try:
                        texte = df.head(100).to_markdown(index=False)
                    except ImportError:
                        texte = df.head(100).to_string(index=False)
                except ImportError:
                    texte = "[pandas requis pour lire Excel]"
            elif ext == ".csv":
                try:
                    import pandas as pd
                    df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
                    texte = df.head(100).to_markdown(index=False)
                except ImportError:
                    texte = raw.decode("utf-8", errors="ignore")[:3000]
            elif ext in (".txt", ".md"):
                texte = raw.decode("utf-8", errors="ignore")[:10000]
            elif ext in (".pptx",):
                try:
                    from pptx import Presentation
                    prs = Presentation(io.BytesIO(raw))
                    texte = "\n".join(
                        shape.text for slide in prs.slides
                        for shape in slide.shapes if hasattr(shape, "text") and shape.text
                    )
                except ImportError:
                    texte = "[python-pptx requis pour lire PowerPoint]"
            else:
                texte = f"[Format {ext} non supporté pour extraction]"

            extraits.append(f"=== Fichier : {f.nom} ===\n{texte[:8000]}\n")
        except Exception as e:
            extraits.append(f"=== Fichier : {f.nom} ===\n[Erreur lecture : {e}]\n")

    return "\n".join(extraits)


def _detecter_intention_traduction(message: str, a_fichiers: bool) -> dict | None:
    """
    Détecte si la requête est une demande de traduction.
    Fonctionne avec ou sans fichier joint.
    """
    msg = message.lower()
    mots_trad = [
        "traduis", "traduire", "traduction", "translate", "translation",
        "en anglais", "en français", "in english", "en espagnol",
        "en portugais", "en arabe", "en mandarin",
        "convertir en", "version anglaise", "version française",
        "version espagnole",
    ]
    if not any(m in msg for m in mots_trad):
        return None

    langues = {
        "anglais": "en", "english": "en", "in english": "en",
        "français": "fr", "french": "fr", "francais": "fr",
        "espagnol": "es", "spanish": "es",
        "portugais": "pt", "portuguese": "pt",
        "arabe": "ar", "arabic": "ar",
        "mandarin": "zh", "chinois": "zh",
    }
    cible = "en"
    for nom, code in langues.items():
        if nom in msg:
            cible = code
            break

    # Détection format de sortie — supporte word, pdf, docx, texte, pptx
    mots_docx = ["docx", "word", ".doc", "document word", "format word",
                 "en word", "sous word", "fichier word"]
    mots_pdf  = ["pdf", "format pdf", "en pdf", "sous pdf", "fichier pdf"]
    mots_pptx = ["pptx", "powerpoint", "présentation"]
    if any(w in msg for w in mots_docx):
        format_out = "docx"
    elif any(w in msg for w in mots_pdf):
        format_out = "pdf"
    elif any(w in msg for w in mots_pptx):
        format_out = "pptx"
    elif a_fichiers:
        # Si fichier joint, retourner par défaut dans le même format ou docx
        format_out = "docx"
    else:
        format_out = "texte"

    return {"langue_cible": cible, "format_sortie": format_out}


def _detecter_intention_cv(message: str) -> dict | None:
    """
    Détecte si le message est une demande de génération de CV ou lettre de motivation.
    Retourne {"type_doc": "cv"|"lettre", "format_sortie": "docx"|"pdf"|"markdown"} ou None.

    Distingue :
    - Conseil / question → None (laisser le copilote répondre en texte)
    - Génération explicite → dict (créer le document)
    """
    msg = message.lower()

    # ── Verbes de génération explicite ────────────────────────────────────
    verbes_generation = [
        "génère", "génère-moi", "génère moi", "générer", "générer mon",
        "rédige", "rédige-moi", "rédige moi", "rédiger", "rédiger mon",
        "crée", "crée-moi", "crée moi", "créer", "créer mon",
        "fais-moi", "fais moi", "faire mon", "prépare", "prépare-moi",
        "écris", "écris-moi", "produire", "adapte", "adapte mon",
        "je veux un cv", "je veux ma lettre", "je voudrais un cv",
        "donne-moi un cv", "donne moi un cv", "fournis-moi",
    ]
    a_verbe_gen = any(v in msg for v in verbes_generation)

    # ── Mots-clés document CV ──────────────────────────────────────────────
    mots_cv = [
        "cv", "curriculum vitae", "resume", "mon cv",
    ]
    mots_lettre = [
        "lettre de motivation", "lettre motivation", "cover letter",
        "lettre de candidature", "lettre d'accompagnement",
    ]

    est_cv     = any(m in msg for m in mots_cv)
    est_lettre = any(m in msg for m in mots_lettre)

    if not (est_cv or est_lettre):
        return None

    # Si pas de verbe de génération explicite, c'est une question → copilote texte
    if not a_verbe_gen:
        return None

    # ── Détecter le format demandé ─────────────────────────────────────────
    format_sortie = "docx"  # défaut
    if any(w in msg for w in ["en pdf", "format pdf", "fichier pdf", "pdf"]):
        format_sortie = "pdf"
    elif any(w in msg for w in ["en markdown", "format markdown", "texte", "en texte", "sans fichier"]):
        format_sortie = "markdown"

    type_doc = "lettre" if est_lettre else "cv"

    return {"type_doc": type_doc, "format_sortie": format_sortie}


def _normaliser_msg(msg: str) -> str:
    """Normalise un message : minuscules + suppression des accents pour la comparaison."""
    import unicodedata
    nfc = unicodedata.normalize("NFD", msg.lower())
    return "".join(c for c in nfc if unicodedata.category(c) != "Mn")


def _detecter_intention_designer(message: str) -> str | None:
    """
    Détecte si le message demande la création d'un visuel design (livret, flyer,
    brochure, faire-part, programme, menu, livre photo, carte d'invitation, etc.)
    nécessitant le moteur Designer Pro multi-page.
    Retourne 'designer' si pertinent, sinon None.
    """
    msg = _normaliser_msg(message)

    types_visuels = [
        "livret", "faire-part", "faire part", "fairepart",
        "carte d invitation", "carte d'invitation", "carte de visite",
        "carte de remerciement", "carte mariage", "invitation mariage",
        "invitation deces", "invitation décès", "invitation deuil",
        "annonce deces", "annonce décès", "programme funerailles",
        "programme funérailles", "programme de funerailles",
        "programme culte", "programme messe", "programme religieux",
        "brochure", "depliant", "dépliant", "flyer", "tract",
        "menu restaurant", "menu de restaurant", "menu de mariage",
        "livre photo", "livre-photo", "album photo",
        "affiche", "poster", "banniere", "bannière",
        "carton invitation", "carton d invitation",
        "infographie pro", "designer pro", "design multi page",
        "design multi-page", "design plusieurs pages",
        "livret deces", "livret décès", "livret deuil",
        "livret mariage", "livret de mariage",
        "livret programme", "livret de programme",
    ]
    if any(t in msg for t in types_visuels):
        return "designer"

    # Combinaisons verbe + visuel implicite (ex: "fais moi un faire-part")
    verbes = ["genere", "generer", "cree", "creer", "fais", "faire",
              "prepare", "preparer", "concevoir", "design", "designer",
              "monte moi", "donne moi", "je veux", "je voudrais",
              "il me faut", "j ai besoin", "imprimer", "imprime"]
    cibles = ["faire part", "fairepart", "livret", "brochure", "flyer",
              "depliant", "dépliant", "menu", "livre photo", "album",
              "affiche", "poster", "carte"]
    a_verbe = any(v in msg[:200] for v in verbes)
    a_cible = any(c in msg for c in cibles)
    if a_verbe and a_cible:
        return "designer"
    return None


def _detecter_intention_generateur(message: str) -> str | None:
    """
    Détecte si le message est une demande de génération de document téléchargeable.
    Retourne 'contrat', 'rapport', 'slides' ou None.
    Stratégie : vérbe d'action + type de document (sans accent, robuste).
    """
    msg = _normaliser_msg(message)

    # ── Slides / Présentations ─────────────────────────────────────────────────
    patterns_slides = [
        "presentation powerpoint", "presentation ppt", "genere une presentation",
        "creer une presentation", "creer des slides", "faire une presentation",
        "prepare une presentation", "slides sur", "slides pour",
        "presentation direction", "deck de presentation", "support de presentation",
        "genere des slides", "generer des slides",
    ]
    for p in patterns_slides:
        if p in msg:
            return "slides"

    # ── Documents juridiques / Contrats ────────────────────────────────────────
    # Verbe d'action + type de document juridique
    verbes_gen = ["genere", "generer", "cree", "creer", "redige", "rediger",
                  "fais", "faire", "prepare", "preparer", "produis", "produire",
                  "je veux", "je voudrais", "je souhaite", "donne moi", "ecris",
                  "aide moi a rediger", "aide moi a creer", "aide moi a faire",
                  "aide moi a preparer", "aide moi a produire", "aidez moi a",
                  "aide a rediger", "aide a creer", "aide a faire",
                  "peux tu rediger", "peux tu creer", "peux tu generer",
                  "peux tu preparer", "pouvez vous rediger", "pouvez vous creer",
                  "pouvez vous generer", "elabore", "elaborer", "etablis", "etablir"]
    types_contrat = [
        "contrat", "contrat de bail", "contrat de travail", "contrat de prestation",
        "contrat de vente", "contrat de service", "accord", "convention",
        "protocole", "avenant", "addendum", "lettre de mission",
        "lettre commerciale", "lettre officielle", "lettre de resiliation",
        "lettre de mise en demeure", "lettre d'offre", "lettre d'embauche",
        "proces-verbal", "proces verbal", "pv de reunion", "pv d'assemblee",
        "attestation", "attestation de travail", "attestation de salaire",
        "certificat", "memorandum", "memo", "note de service",
        "note juridique", "note de synthese", "note de synthèse",
        "acte", "statuts", "statuts de societe", "reglement interieur",
        "charte", "cahier des charges", "appel d'offres", "appel d'offre",
        "bordereau", "devis", "facture proforma", "bon de commande",
    ]

    # Check : verbe + type doc (dans les 200 premiers chars)
    msg_court = msg[:200]
    a_verbe = any(v in msg_court for v in verbes_gen)
    a_type_contrat = any(t in msg for t in types_contrat)

    if a_verbe and a_type_contrat:
        return "contrat"

    # Patterns directs "en word / docx / pdf / téléchargeable" + type de doc
    mots_format = ["en word", "docx", "en pdf", "telechargeable", "format word",
                   "fichier word", "au format word", "sous word",
                   " word", "word complet", "word s", "word.", "fichier pdf",
                   "format pdf", "document word", "document pdf"]
    a_format = any(f in msg for f in mots_format)
    if a_format and a_type_contrat:
        return "contrat"

    # ── Rapports & Notes génériques ────────────────────────────────────────────
    patterns_rapport = [
        "genere un rapport", "genere-moi un rapport", "genere moi un rapport",
        "generer un rapport", "cree un rapport", "creer un rapport",
        "redige un rapport", "rediger un rapport", "faire un rapport",
        "prepare un rapport", "preparer un rapport", "fais un rapport",
        "je veux un rapport", "je voudrais un rapport", "produire un rapport",
        "draft de rapport", "un draft de", "draft du rapport",
        "genere un document", "generer un document", "genere moi un document",
        "genere-moi un document", "cree un document", "creer un document",
        "je veux un document", "document a telecharger", "document complet",
        "je veux le document", "document word", "document pdf",
        "un document word", "un document pdf", "un fichier word", "un fichier pdf",
        "plan d action", "plan action", "plan de travail",
        "rapport de performance", "rapport financier", "rapport rh",
        "rapport d activite", "rapport activite", "rapport mensuel",
        "rapport annuel", "rapport hebdomadaire",
        "rapport d audit", "rapport audit", "rapport de synthese",
        "note de synthese", "note de service",
        "business plan", "plan d affaires", "plan de projet",
    ]
    for p in patterns_rapport:
        if p in msg:
            return "rapport"

    # Dernier filet : verbe d'action + format explicite (word/pdf/docx) → rapport générique
    if a_verbe and a_format:
        return "rapport"

    return None


def _detecter_type_document(message: str) -> str:
    """
    Déduit le type de document depuis le message utilisateur.
    Couvre rapports, contrats, lettres, notes, procès-verbaux, etc.
    """
    msg = _normaliser_msg(message)
    # Contrats et documents juridiques
    if any(w in msg for w in ["contrat de bail", "bail", "location"]):
        return "contrat_bail"
    if any(w in msg for w in ["contrat de travail", "contrat d'embauche"]):
        return "contrat_travail"
    if any(w in msg for w in ["contrat de prestation", "contrat de service", "lettre de mission"]):
        return "contrat_prestation"
    if any(w in msg for w in ["contrat de vente", "protocole de vente", "compromis"]):
        return "contrat_vente"
    if any(w in msg for w in ["convention", "accord", "protocole", "avenant"]):
        return "convention"
    if any(w in msg for w in ["statuts", "statuts de societe", "acte constitutif"]):
        return "statuts"
    if any(w in msg for w in ["reglement interieur", "charte"]):
        return "reglement_interieur"
    if any(w in msg for w in ["contrat"]):
        return "contrat_generique"
    # Lettres et courriers
    if any(w in msg for w in ["lettre de mise en demeure", "mise en demeure"]):
        return "lettre_mise_en_demeure"
    if any(w in msg for w in ["lettre de resiliation", "resiliation"]):
        return "lettre_resiliation"
    if any(w in msg for w in ["lettre d'offre", "lettre d'embauche", "lettre de motivation"]):
        return "lettre_emploi"
    if any(w in msg for w in ["lettre commerciale", "lettre d'affaires", "courrier"]):
        return "lettre_commerciale"
    if any(w in msg for w in ["lettre officielle", "lettre administrative"]):
        return "lettre_officielle"
    # Attestations et certificats
    if any(w in msg for w in ["attestation de travail", "attestation de salaire"]):
        return "attestation"
    if any(w in msg for w in ["certificat"]):
        return "certificat"
    # Procès-verbaux
    if any(w in msg for w in ["proces-verbal", "pv de reunion", "pv d'assemblee", "compte rendu"]):
        return "compte_rendu"
    # Rapports et notes
    if any(w in msg for w in ["financier", "finance", "bilan", "tresorerie"]):
        return "rapport_financier"
    if any(w in msg for w in ["rh", "ressources humaines", "personnel"]):
        return "rapport_rh"
    if any(w in msg for w in ["juridique", "droit", "legal"]):
        return "note_juridique"
    if any(w in msg for w in ["note de service", "note de synthese"]):
        return "note_de_synthese"
    if any(w in msg for w in ["plan d action", "plan action", "plan de travail"]):
        return "plan_action"
    if any(w in msg for w in ["audit", "controle"]):
        return "rapport_audit"
    if any(w in msg for w in ["business plan", "plan d affaires"]):
        return "plan_action"
    return "rapport_analyse"


# Alias pour compatibilité
def _detecter_type_rapport(message: str) -> str:
    return _detecter_type_document(message)


def _extraire_texte_a_traduire(message: str) -> str | None:
    """
    Extrait le texte à traduire depuis le message quand aucun fichier n'est joint.
    Cherche le texte après ':', entre guillemets, ou après des marqueurs courants.
    """
    import re
    msg = message.strip()

    # Texte entre guillemets typographiques ou ASCII
    matches = re.findall(r'[«""\u201c\u00ab](.+?)[»""\u201d\u00bb]', msg, re.DOTALL)
    if matches and len(matches[0].strip()) > 5:
        return matches[0].strip()

    # Texte après ":" ou " : " (séparateur de contenu)
    for sep in [" : ", ": ", ":\n"]:
        if sep in msg:
            parts = msg.split(sep, 1)
            if len(parts) > 1 and len(parts[1].strip()) > 10:
                return parts[1].strip()

    # Texte après "le texte suivant", "ce texte", "le paragraphe"
    for marker in ["le texte suivant\n", "ce texte\n", "le paragraphe\n",
                   "le texte suivant ", "ce texte :", "suivant :"]:
        if marker in msg:
            idx = msg.index(marker) + len(marker)
            reste = msg[idx:].strip()
            if len(reste) > 10:
                return reste

    return None


def _scanner_signaux_agent(msg: str, profil) -> dict:
    """
    Scan synchrone (0 ms, 0 appel IA) : collecte les signaux mots-clés et le profil.
    Retourne {agent, confiance: 'haute'|'moyenne'|'profil'|None, signaux: list[str]}
    - 'haute'  → terme très technique, sans ambiguïté → décision immédiate
    - 'moyenne' → terme sémantique large → à confirmer par le LLM
    - 'profil'  → seul le profil métier oriente, message pas encore analysé
    """
    # ── Haute confiance : termes techniques non-ambigus ─────────────────────
    haute: list[tuple[str, str]] = [
        # DRH
        ("bulletin de paie", "drh"), ("calcul de paie", "drh"),
        ("salaire net", "drh"), ("salaire brut", "drh"),
        ("indemnité de licenciement", "drh"), ("congés payés", "drh"),
        ("contrat cdi", "drh"), ("contrat cdd", "drh"), ("arrêt maladie", "drh"),
        ("fiche de paie", "drh"), ("irpp salarial", "drh"),
        # Comptable
        ("syscohada", "comptable"), ("irpp", "comptable"),
        ("déclaration fiscale", "comptable"), ("déclaration tva", "comptable"),
        ("bilan comptable", "comptable"), ("grand livre", "comptable"),
        ("journaux comptables", "comptable"), ("provision comptable", "comptable"),
        # Banquier
        ("tableau d'amortissement", "banquier"), ("teg", "banquier"),
        ("scoring crédit", "banquier"), ("kyc", "banquier"),
        ("plan de financement", "banquier"), ("dossier de crédit", "banquier"),
        ("garantie bancaire", "banquier"),
        # Juriste
        ("acte constitutif", "juriste"), ("droit ohada", "juriste"),
        ("mise en demeure", "juriste"), ("texte de loi", "juriste"),
        ("textes de loi", "juriste"), ("article de loi", "juriste"),
        ("statuts d'entreprise", "juriste"), ("procédure judiciaire", "juriste"),
        ("clause contractuelle", "juriste"), ("résiliation de contrat", "juriste"),
        ("actionnariat", "juriste"), ("parts sociales", "juriste"),
        ("code des sociétés", "juriste"), ("recherche juridique", "juriste"),
        ("loi sur", "juriste"), ("loi relative", "juriste"),
        ("assemblée générale", "juriste"),
        # Microfinance
        ("par30", "microfinance"), ("portfolio at risk", "microfinance"),
        ("portefeuille de crédit", "microfinance"), ("taux d'impayé", "microfinance"),
        # ONG
        ("logframe", "ong"), ("cadre logique", "ong"),
        ("budget bailleur", "ong"), ("reporting bailleur", "ong"),
        ("cadre de résultats", "ong"),
        # Douanier
        ("droits de douane", "douanier"), ("incoterm", "douanier"),
        ("régime douanier", "douanier"), ("déclaration en douane", "douanier"),
        ("tarif douanier", "douanier"),
        # Ingénieur
        ("chemin critique", "ingenieur"), ("diagramme de gantt", "ingenieur"),
        ("cahier des charges", "ingenieur"), ("appel d'offres", "ingenieur"),
        ("bordereau de prix", "ingenieur"),
        # Commercial
        ("business plan", "commercial"), ("seuil de rentabilité", "commercial"),
        ("pipeline commercial", "commercial"), ("plan marketing", "commercial"),
        # DAA
        ("analyse de données", "daa"), ("analyser les données", "daa"),
        ("dataset", "daa"), ("visualisation de données", "daa"),
        ("statistiques descriptives", "daa"), ("tableau croisé", "daa"),
        # DAF
        ("budget prévisionnel", "daf"), ("contrôle de gestion", "daf"),
        ("reporting financier", "daf"), ("cash flow", "daf"),
        ("flux de trésorerie", "daf"), ("tableau de bord financier", "daf"),
        ("plan de trésorerie", "daf"),
        # CV / emploi
        ("lettre de motivation", "cv_emploi"), ("curriculum vitae", "cv_emploi"),
        ("rédige mon cv", "cv_emploi"), ("génère mon cv", "cv_emploi"),
        ("cover letter", "cv_emploi"), ("améliore mon cv", "cv_emploi"),
        # Recherche emploi
        ("veille emploi", "recherche_emploi"), ("offres d'emploi", "recherche_emploi"),
        ("recherche d'emploi", "recherche_emploi"), ("trouve un emploi", "recherche_emploi"),
        ("cherche un emploi", "recherche_emploi"),
    ]

    # ── Moyenne confiance : termes larges orientant sans certifier ───────────
    moyenne: list[tuple[str, str]] = [
        ("employé", "drh"), ("salarié", "drh"), ("recrutement", "drh"),
        ("ressources humaines", "drh"), ("licenciement", "drh"),
        ("rémunération", "drh"), ("entretien annuel", "drh"),
        ("performance des employés", "drh"), ("plan de formation", "drh"),
        ("contrat de travail", "drh"),
        ("comptabilité", "comptable"), ("fiscalité", "comptable"),
        ("impôt", "comptable"), ("tva", "comptable"),
        ("amortissement", "comptable"), ("bilan", "comptable"),
        ("compte de résultat", "comptable"),
        # DAF — termes financiers de pilotage (pas bancaires ni comptables)
        ("budget", "daf"), ("trésorerie", "daf"), ("reporting", "daf"),
        ("directeur financier", "daf"), ("plan financier", "daf"),
        ("tableau de bord", "daf"),
        ("crédit", "banquier"), ("financement", "banquier"),
        ("investissement", "banquier"), ("analyse financière", "banquier"),
        ("ratio financier", "banquier"), ("taux d'intérêt", "banquier"),
        ("juridique", "juriste"), ("réglementation", "juriste"),
        ("litige", "juriste"), ("conformité", "juriste"),
        ("droit", "juriste"), ("actionnaire", "juriste"),
        ("société anonyme", "juriste"), ("statut juridique", "juriste"),
        ("stratégie commerciale", "commercial"), ("étude de marché", "commercial"),
        ("chiffre d'affaires", "commercial"), ("proposition commerciale", "commercial"),
        ("kpi", "daa"), ("indicateur de performance", "daa"),
        ("analyse de données", "daa"), ("statistiques", "daa"),
        ("gestion de projet", "ingenieur"), ("planning", "ingenieur"),
        ("spécifications techniques", "ingenieur"),
        ("microfinance", "microfinance"), ("crédit solidaire", "microfinance"),
        ("bailleur", "ong"), ("projet de développement", "ong"),
        ("import", "douanier"), ("export", "douanier"), ("douane", "douanier"),
        # CV / emploi (moyenne)
        (" cv ", "cv_emploi"), ("mon cv", "cv_emploi"), ("candidature", "cv_emploi"),
        ("entretien d'embauche", "cv_emploi"),
        # Recherche emploi (moyenne)
        ("offre d'emploi", "recherche_emploi"), ("job", "recherche_emploi"),
        ("poste disponible", "recherche_emploi"), ("chercher un poste", "recherche_emploi"),
    ]

    hits_haute = [(p, a) for p, a in haute if p in msg]
    if hits_haute:
        agents = [a for _, a in hits_haute]
        dominant = Counter(agents).most_common(1)[0][0]
        return {"agent": dominant, "confiance": "haute",
                "signaux": [p for p, a in hits_haute if a == dominant]}

    hits_moyenne = [(p, a) for p, a in moyenne if p in msg]
    if hits_moyenne:
        agents = [a for _, a in hits_moyenne]
        dominant = Counter(agents).most_common(1)[0][0]
        return {"agent": dominant, "confiance": "moyenne",
                "signaux": [p for p, a in hits_moyenne if a == dominant]}

    # Profil déclaré comme signal de dernier recours
    # Couvre les 27 métiers du metiers-config.ts → 13 agents spécialisés
    MAP_METIER: dict[str, str] = {
        # Comptabilité / Finance
        "comptable": "comptable", "expert_comptable": "comptable",
        "fiscaliste": "comptable", "auditeur": "comptable",
        # DAF
        "daf": "daf", "directeur_financier": "daf",
        # Droit
        "juriste": "juriste", "avocat": "juriste", "notaire": "juriste",
        "juriste_entreprise": "juriste",
        # Banque / Finance
        "banquier": "banquier", "analyste_credit": "banquier",
        "trader": "banquier", "gestionnaire_actifs": "banquier",
        "financier": "banquier",
        # RH
        "drh": "drh", "rh": "drh", "ressources_humaines": "drh",
        "gestionnaire_rh": "drh",
        # Ingénierie / BTP
        "ingenieur": "ingenieur", "chef_projet": "ingenieur",
        "architecte": "ingenieur", "conducteur_travaux": "ingenieur",
        "btp": "ingenieur",
        # Data
        "daa": "daa", "data_analyst": "daa",
        "data_scientist": "daa", "statisticien": "daa",
        # Commercial
        "directeur_commercial": "commercial", "commercial": "commercial",
        "entrepreneur": "commercial", "consultant": "commercial",
        "acheteur": "commercial",
        # ONG
        "charge_projets_ong": "ong", "coordinateur_ong": "ong",
        "charge_programme": "ong", "responsable_ong": "ong",
        "charge_de_projet": "ong", "charge_projet_ong": "ong",
        # Microfinance
        "responsable_microfinance": "microfinance",
        "credit_officer": "microfinance", "agent_microfinance": "microfinance",
        "directeur_sfd": "microfinance", "gestionnaire_imf": "microfinance",
        "agent_sfd": "microfinance", "sfd": "microfinance",
        # Douane / Commerce international
        "transitaire": "douanier", "douanier": "douanier",
        "agent_transit": "douanier", "agent_douane": "douanier",
        "declarant_douane": "douanier", "freight_forwarder": "douanier",
        "commerce_international": "douanier",
        # CV / Emploi
        "cv_emploi": "cv_emploi", "candidat": "cv_emploi",
        "recherche_emploi": "recherche_emploi",
        "veille_emploi": "recherche_emploi", "job_search": "recherche_emploi",
    }
    metier = (getattr(profil, "metier", "") or "").lower()
    if metier in MAP_METIER:
        return {"agent": MAP_METIER[metier], "confiance": "profil",
                "signaux": [f"profil:{metier}"]}

    return {"agent": None, "confiance": None, "signaux": []}


async def _detecter_agent_unifie(message: str, profil, ia_client) -> str | None:
    """
    Détection unifiée mots-clés + LLM en un seul pipeline cohérent.

    Étape 1 — Scan synchrone (gratuit, <1 ms)
      → collecte les signaux et leur niveau de confiance

    Étape 2 — Décision selon confiance :
      • haute   → retour immédiat, aucun appel LLM
      • moyenne → UN appel LLM ENRICHI des signaux déjà trouvés
                  (le LLM n'est pas aveugle, il confirme/infirme)
      • profil  → appel LLM seulement si message est actionnable
      • aucun   → appel LLM seulement si message long et actionnable
    """
    from core.ia_client import ModeIA

    msg = message.lower()
    signaux = _scanner_signaux_agent(msg, profil)

    # Cas 1 : signal technique fort → décision sans LLM
    if signaux["confiance"] == "haute":
        logger.debug(f"[Copilote] Agent='{signaux['agent']}' via keywords (haute)")
        return signaux["agent"]

    # Évaluer si le message est actionnable (verbe d'action + longueur suffisante)
    verbes = (
        "aide", "calcule", "analyse", "rédige", "cherche", "recherche",
        "explique", "donne", "dis-moi", "comment", "quels", "quelle", "quel",
        "liste", "trouve", "fais", "prépare", "vérifie", "genere", "génère",
    )
    actionnable = any(v in msg for v in verbes) and len(msg.strip()) > 28

    # Cas 2 : aucun signal ET message court/trivial → copilote répond directement
    if signaux["confiance"] is None and not actionnable:
        return None

    # Cas 3 : signal moyen / profil / message actionnable → LLM avec contexte enrichi
    # On injecte les signaux keywords dans le prompt → le LLM est informé, pas aveugle
    hints_str = ""
    if signaux["signaux"]:
        hints_str = f"\nIndices trouvés dans le message: {', '.join(signaux['signaux'][:5])}"
    if signaux["agent"] and signaux["confiance"] in ("moyenne", "profil"):
        hints_str += f"\nAgent pressenti: {signaux['agent']} (confiance {signaux['confiance']})"

    metier_profil = (getattr(profil, "metier", "") or "professionnel général")
    agents_desc = (
        "drh (paie, RH, contrats de travail, recrutement, évaluation des employés, plan de formation), "
        "comptable (SYSCOHADA, TVA, IRPP, déclarations fiscales, bilans, trésorerie, comptabilité), "
        "daf (tableau de bord financier, trésorerie, reporting, budget, contrôle de gestion, directeur financier), "
        "banquier (crédit, investissement, ratios financiers, analyse financière, scoring), "
        "juriste (droit OHADA, lois, textes législatifs, contrats, actionnariat, litiges, recherche juridique), "
        "commercial (business plan, stratégie vente, étude de marché, marketing, proposition commerciale), "
        "daa (analyse de données, statistiques, KPI, tableaux de bord, visualisation, data science), "
        "ingenieur (projets, BTP, cahiers des charges, planning, appels d'offres, architecture), "
        "microfinance (PAR30, portefeuille de crédit, SFD, crédit solidaire, IMF), "
        "ong (logframe, bailleurs de fonds, M&E, reporting, indicateurs, développement), "
        "douanier (incoterms, droits de douane, import/export, régimes douaniers, transit), "
        "cv_emploi (rédaction CV, lettre de motivation, candidature, entretien d'embauche), "
        "recherche_emploi (veille offres emploi, recherche d'emploi, opportunités, job search)"
    )
    prompt = (
        f"Profil utilisateur: {metier_profil}\n"
        f"Message: \"{message[:500]}\""
        f"{hints_str}\n\n"
        f"Agents disponibles: {agents_desc}\n\n"
        f"Quel agent est LE PLUS ADAPTÉ à cette demande spécifique ?\n"
        f"Réponds avec UN seul mot parmi: "
        f"drh, comptable, daf, banquier, juriste, commercial, daa, ingenieur, microfinance, ong, douanier, cv_emploi, recherche_emploi\n"
        f"— ou AUCUN si c'est une question générale sans expertise métier requise.\n"
        f"Agent:"
    )
    try:
        reponse = await asyncio.wait_for(
            ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.PRECISION,
                utiliser_cache=True,
                max_tokens_override=15,
            ),
            timeout=5.0,
        )
        agent = reponse.contenu.strip().lower().split()[0].rstrip(".,;:()")
        valides = {"drh", "comptable", "daf", "banquier", "juriste", "commercial",
                   "daa", "ingenieur", "microfinance", "ong", "douanier",
                   "cv_emploi", "recherche_emploi"}
        if agent in valides:
            logger.info(f"[Copilote] Agent='{agent}' via LLM unifié (signaux={signaux['signaux']})")
            return agent
        # LLM a dit AUCUN — respecter sauf si signal profil ET message actionnable
        if signaux["confiance"] == "profil" and actionnable:
            return signaux["agent"]
    except Exception as e:
        logger.debug(f"[Copilote] LLM unifié erreur ({e}) → fallback heuristique")
        if signaux["agent"] and signaux["confiance"] in ("moyenne", "profil") and actionnable:
            return signaux["agent"]

    return None


async def _orchestrer_llm(
    message: str,
    profil,
    ia_client,
    a_fichiers: bool = False,
    contenu_fichiers: str = "",
) -> dict:
    """
    Orchestrateur IA central — remplace toutes les détections par mots-clés.

    Un seul appel gpt-4o-mini (~300ms, ~$0.0001) classifie :
      - intention  : generateur | agent_metier | traduction | conversation
      - sous_type  : contrat | rapport | slides | cv (si generateur)
      - type_doc   : type précis du document (contrat_bail, rapport_financier…)
      - agent      : agent spécialisé (juriste, drh, comptable…)
      - format     : docx | pptx
      - langue_cible : fr | en | es | pt (si traduction)

    Fallback automatique vers les mots-clés si le LLM est indisponible.
    """
    import json
    import re as _re
    from core.ia_client import ModeIA

    metier = (getattr(profil, "metier", "") or "professionnel") if profil else "professionnel"
    pays   = (getattr(profil, "pays",   "") or "Afrique")       if profil else "Afrique"
    fichiers_ctx = "Fichiers joints: OUI — l'utilisateur a envoyé des documents" if a_fichiers else "Fichiers joints: NON"

    prompt = f"""Tu es l'orchestrateur de Yukpo Pro, plateforme professionnelle africaine.
Analyse ce message et retourne UNIQUEMENT un objet JSON valide. Pas de markdown, pas d'explication.

Message: \"{message[:700]}\"
Profil: {metier} | Pays: {pays}
{fichiers_ctx}

RÈGLES DE CLASSIFICATION:
- "generateur" → l'utilisateur veut CRÉER/GÉNÉRER/RÉDIGER un document téléchargeable, OU demande si Yukpo PEUT créer/générer un tel document (même sous forme de question comme "est-ce que tu peux me générer...", "peux-tu créer...", "tu peux faire un rapport..."). Dans ce cas, générer directement le document demandé.
- "agent_metier" → question technique MÉTIER nécessitant un expert (calcul de paie, analyse de bilan, recherche juridique, scoring crédit, droits de douane...). AUSSI quand des fichiers sont joints et l'utilisateur demande une ANALYSE du fichier ("analyse ce fichier", "fais une analyse de ce devis", "examine ce document", "que contient ce fichier", "analyse mes données", "lis ce fichier"). NE PAS utiliser pour des questions sur les capacités de Yukpo.
- "traduction" → traduire un texte ou document vers une autre langue
- "conversion" → CONVERTIR/TRANSFORMER un fichier d'un FORMAT à un autre (ex: "convertis ce PDF en Word", "transforme en Excel", "change en DOCX", "PDF vers Word", "Word en PDF", "XLSX en CSV", "image en Word"). UNIQUEMENT quand un fichier est joint ET l'utilisateur demande une conversion de format. Placer "format_cible" dans la réponse (docx, pdf, pptx, xlsx, csv, txt, jpg).
- "designer" → l'utilisateur veut CRÉER UN VISUEL/IMPRIMÉ DESIGN, mono ou multi-page, avec mise en page graphique (typographie soignée, palette, ornements, photos, plans). Cas typiques (non exhaustifs — analyse l'INTENTION, pas seulement les mots) :
   • Cérémonies & événements : faire-part de décès/mariage/baptême, livret obsèques/messe/culte, programme de cérémonie, carte d'invitation, carte de remerciement, carton, livret hommage, livret souvenir
   • Marketing & corporate : brochure, dépliant, flyer, tract, plaquette, affiche, poster, bannière, kakemono, carte de visite, plan d'accès stylisé
   • Restauration & retail : menu restaurant, carte des vins, étiquette produit
   • Albums & souvenirs : livre photo, album, fanzine, livret de fin d'année
   Indices : références à pages multiples ("livret"), mises en page artistiques, photos/témoignages/citations à intégrer, cérémonies religieuses ou familiales, demandes "imprimable / pour l'imprimerie / quadrichromie / CMJN", besoin de plan/QR/famille/programme dans un même document. CHOISIS "designer" même si le mot exact n'apparaît pas tant que l'intention est de produire un imprimé graphique (≠ rapport texte). NE PAS utiliser pour : un simple Word/PDF texte (rapport, contrat, lettre) → "generateur".
- "conversation" → question générale, explication, conseil, salutation (bonjour, merci...), discussion sans demande de document ni de calcul technique

RÈGLE CRITIQUE FICHIERS JOINTS: Si des fichiers sont joints ET l'utilisateur demande une analyse directe (pas une génération de document Word/PDF), classer en "agent_metier" avec agent="daa".

SOUS-TYPES generateur (choisir le plus précis):
- "contrat" : contrat (bail, travail, prestation, vente, service), convention, avenant, lettre officielle, lettre commerciale, mise en demeure, résiliation, attestation, certificat, statuts, règlement intérieur, PV, note de service, charte, cahier des charges
- "rapport" : rapport, note de synthèse, plan d'action, compte-rendu, business plan, analyse, étude, note juridique
- "slides" : présentation PowerPoint, slides, deck, support de formation
- "tableur" : tableau Excel, classeur XLSX, tableau de bord, suivi de KPIs, modèle financier, base de données
- "cv" : CV, curriculum vitae, lettre de motivation, lettre d'emploi

TYPES PRÉCIS (choisir le plus proche):
rapport_analyse, rapport_financier, rapport_rh, rapport_audit, note_de_synthese, note_juridique, plan_action, compte_rendu, business_plan,
contrat_bail, contrat_travail, contrat_prestation, contrat_vente, convention, statuts, reglement_interieur,
lettre_officielle, lettre_commerciale, lettre_mise_en_demeure, lettre_resiliation, lettre_emploi,
attestation, certificat, proces_verbal,
slides_bilan_activite, slides_rapport_direction, slides_proposition_client, slides_pitch_projet, slides_formation,
tableur_kpi, tableur_financier, tableur_suivi, tableur_generique,
cv, lettre_motivation

AGENTS DISPONIBLES (pour agent_metier):
drh, comptable, daf, juriste, banquier, commercial, daa, ingenieur, microfinance, ong, douanier, cv_emploi, recherche_emploi

FORMAT (format de sortie demandé par l'utilisateur — DÉTECTER finement) :
  - "docx" : Word (par défaut pour rapport/contrat sans précision)
  - "pdf"  : PDF (si user dit "en pdf", "format pdf", "fichier pdf")
  - "pptx" : PowerPoint (par défaut pour slides)
  - "xlsx" : Excel (par défaut pour tableur ; ou si user dit "en excel", "tableau excel", "xlsx")
  - "markdown" : si demandé explicitement

MODE (longueur/profondeur demandée) :
  - "flash"    : note express 1-2 pages / 5-7 slides
  - "standard" : 3-5 pages / 10-15 slides (DÉFAUT)
  - "complet"  : 10-30 pages / 20-30 slides (si user dit "complet", "détaillé", "approfondi", "exhaustif")
  - "expert"   : 30+ pages / 30-40 slides (si user dit "expert", "très détaillé", "rapport d'expertise", "très complet")

STYLE_SPECIFIQUE : si l'utilisateur précise un style ou cabinet de référence
  ("style cabinet d'avocat", "format Big4", "norme CIMA stricte", "ton McKinsey",
  "registre administratif", "ton institutionnel BAD/AFD"…), le retourner verbatim.
  Sinon : null.

LANGUE_CIBLE (si traduction): fr, en, es, pt, ar
FORMAT_CIBLE (si conversion): docx, pdf, pptx, xlsx, csv, txt, jpg

MODULES DISPONIBLES (pour modules_suggeres) :
- "reunions"       : gestion de réunions, PV, ordre du jour, compte rendu de réunion
- "traduction"     : traduction de documents
- "translate_live" : interprétation simultanée, traduction en temps réel
- "generateur"     : générer Word/PowerPoint/PDF (rapports, contrats, slides, business plans)
- "emploi"         : offres d'emploi, CV, lettres de motivation, recrutement
- "marches"        : marchés publics, appels d'offres, DAO
- "enquetes"       : enquêtes, sondages, questionnaires
- "designer"       : faire-part, livrets, brochures, flyers, menus, cartes d'invitation, livres photo, dépliants — visuels multi-page imprimables
- "mes_documents"  : retrouver, consulter ou télécharger des documents générés
- "dashboard"      : statistiques d'utilisation, tableau de bord

modules_suggeres : liste de 0 à 2 clés de modules dont la pertinence est évidente pour ce message. Laisser [] si aucun module n'est spécifiquement adapté à la demande (conversation générale, question juridique, etc.).

JSON REQUIS (tous les champs, null si non applicable):
{{"intention": "...", "sous_type": "...", "type_doc": "...", "agent": null, "format": "docx", "mode": "standard", "style_specifique": null, "langue_cible": null, "format_cible": null, "confiance": 0.9, "modules_suggeres": []}}"""

    try:
        reponse = await asyncio.wait_for(
            ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.PRECISION,
                utiliser_cache=False,
                max_tokens_override=300,  # élargi pour mode + style_specifique
            ),
            timeout=8.0,
        )
        raw = reponse.contenu.strip() if hasattr(reponse, "contenu") else str(reponse).strip()
        # Extraire le JSON même s'il est entouré de markdown
        match = _re.search(r"\{.*?\}", raw, _re.DOTALL)
        if match:
            raw = match.group(0)
        result = json.loads(raw)

        # Valider et normaliser
        if result.get("intention") not in {"generateur", "agent_metier", "traduction", "conversion", "conversation", "designer"}:
            result["intention"] = "conversation"

        logger.info(
            f"[Orchestrateur] intention={result.get('intention')} sous_type={result.get('sous_type')} "
            f"agent={result.get('agent')} type_doc={result.get('type_doc')}"
        )
        return result

    except Exception as e:
        logger.warning(f"[Orchestrateur] LLM indisponible ({e}) — fallback mots-clés")
        return _orchestrer_fallback_keywords(message, profil, a_fichiers)


def _detecter_intention_conversion(message: str, a_fichiers: bool) -> dict | None:
    """
    Détecte si la requête est une demande de conversion de format de fichier.
    Ex: "convertis ce PDF en Word", "transforme en Excel", "change le format en DOCX".
    Retourne {"format_cible": "docx"|"pdf"|"pptx"|"xlsx"|"csv"|"txt"|"jpg"} ou None.
    """
    if not a_fichiers:
        return None
    msg = message.lower()
    mots_conv = [
        "convertis", "converti", "convertir", "convert",
        "transforme", "transformer", "change en", "changer en",
        "passe en", "passer en", "exporte en", "exporter en",
        "vers", "en format", "au format", "change le format",
        "pdf vers", "word vers", "excel vers", "docx vers",
    ]
    if not any(m in msg for m in mots_conv):
        return None

    formats = {
        "word": "docx", "docx": "docx", ".doc ": "docx", "en doc ": "docx",
        "pdf": "pdf",
        "powerpoint": "pptx", "pptx": "pptx", "présentation": "pptx",
        "excel": "xlsx", "xlsx": "xlsx", "xls ": "xlsx",
        "csv": "csv",
        "texte": "txt", "txt": "txt", ".txt": "txt",
        "image": "jpg", "jpg": "jpg", "jpeg": "jpg", "png": "jpg",
    }
    format_cible = "docx"
    for mot, fmt in formats.items():
        if mot in msg:
            format_cible = fmt
            break
    return {"format_cible": format_cible}


def _orchestrer_fallback_keywords(message: str, profil, a_fichiers: bool) -> dict:
    """Fallback mots-clés quand le LLM orchestrateur est indisponible."""
    # Conversion de format (priorité sur traduction si fichier joint)
    intention_conv = _detecter_intention_conversion(message, a_fichiers)
    if intention_conv:
        return {
            "intention": "conversion",
            "sous_type": "conversion",
            "type_doc": None,
            "agent": None,
            "format": intention_conv.get("format_cible", "docx"),
            "langue_cible": None,
            "format_cible": intention_conv.get("format_cible", "docx"),
            "confiance": 0.85,
        }

    # Traduction
    intention_trad = _detecter_intention_traduction(message, a_fichiers)
    if intention_trad:
        return {
            "intention": "traduction",
            "sous_type": "traduction",
            "type_doc": None,
            "agent": None,
            "format": intention_trad.get("format_sortie", "docx"),
            "langue_cible": intention_trad.get("langue_cible", "en"),
            "confiance": 0.8,
        }

    # CV
    intention_cv = _detecter_intention_cv(message)
    if intention_cv:
        return {
            "intention": "generateur",
            "sous_type": "cv",
            "type_doc": intention_cv.get("type_doc", "cv"),
            "agent": None,
            "format": intention_cv.get("format_sortie", "docx"),
            "langue_cible": None,
            "confiance": 0.75,
        }

    # Designer Pro (visuels multi-page : faire-part, livrets, brochures, flyers…)
    intention_design = _detecter_intention_designer(message)
    if intention_design:
        return {
            "intention": "designer",
            "sous_type": "designer",
            "type_doc": "designerpro",
            "agent": None,
            "format": "pdf",
            "langue_cible": None,
            "confiance": 0.85,
        }

    # Générateur document
    intention_gen = _detecter_intention_generateur(message)
    if intention_gen:
        return {
            "intention": "generateur",
            "sous_type": intention_gen,
            "type_doc": _detecter_type_document(message),
            "agent": None,
            "format": "pptx" if intention_gen == "slides" else "docx",
            "langue_cible": None,
            "confiance": 0.7,
        }

    # Agent métier (scan haute confiance)
    signaux = _scanner_signaux_agent(message.lower(), profil)
    if signaux.get("confiance") == "haute":
        return {
            "intention": "agent_metier",
            "sous_type": None,
            "type_doc": None,
            "agent": signaux["agent"],
            "format": None,
            "langue_cible": None,
            "confiance": 0.9,
        }

    return {
        "intention": "conversation",
        "sous_type": None,
        "type_doc": None,
        "agent": signaux.get("agent"),
        "format": None,
        "langue_cible": None,
        "confiance": 0.5,
    }


_RE_ARTICLE_RAG = re.compile(
    r"\bart\.?\s*\d+|\barticle\s+\d+|\bart\s+\d+",
    re.IGNORECASE,
)
_RE_CODE_RAG = re.compile(
    r"\bcode\s+(civil|p[eé]nal|p[eé]nale|du\s+travail|de\s+commerce|minier|mini[eè]re|foncier|fonci[eè]re|"
    r"de\s+proc[eé]dure|des\s+imp[oô]ts|famille|d[ée]ontologie|[eé]lectoral)",
    re.IGNORECASE,
)
_RE_LOI_RAG = re.compile(
    r"\b(loi|d[eé]cret|ordonnance|arr[eê]t[eé]|circulaire|r[eè]glement)\s+(n[o°]?\s*\d|du\s+\d)",
    re.IGNORECASE,
)

def _besoin_rag(message: str) -> bool:
    """
    Détermine si le message nécessite une recherche RAG dans le corpus réglementaire.
    """
    msg = message.strip()
    if len(msg) < 10:
        return False

    msg_lower = msg.lower()

    # Toute mention d'un numéro d'article → RAG obligatoire
    if _RE_ARTICLE_RAG.search(msg_lower):
        return True

    # Tout code juridique nommé explicitement
    if _RE_CODE_RAG.search(msg_lower):
        return True

    # Toute référence à une loi/décret/ordonnance numérotée
    if _RE_LOI_RAG.search(msg_lower):
        return True

    # Mots-clés réglementaires, juridiques, comptables, fiscaux
    mots_cles_reglementaires = [
        # OHADA / Droit des affaires
        "ohada", "syscohada", "acte uniforme", "audcg", "aus ", "aucap", "aupcap", "auscoop",
        "brvm", "rccm", "sarl", "suarl", "sa ", "sas ", "gic ", "coopérative",
        # CIMA / Assurance
        "code cima", "cima", "crca", "sinistre", "indemnisation", "prime d'assurance",
        "marge de solvabilité", "provision technique", "branche vie", "branche iard",
        "traité de réassurance", "agent général", "courtier assurance",
        # Fiscal
        "cgi", "code général des impôts", "code des impôts", "loi de finances",
        "tva", "irpp", "is ", "bnc ", "bic ", "imposition", "déclaration fiscale",
        "exonération fiscale", "crédit d'impôt", "droit d'enregistrement",
        "retenue à la source", "précompte", "acompte provisionnel",
        "taxe professionnelle", "patente", "impôt foncier",
        # Comptabilité SYSCOHADA
        "syscohada", "plan comptable", "pcg", "journal", "grand livre", "bilan",
        "compte de résultat", "flux de trésorerie", "amortissement", "provision",
        "immobilisation", "stock", "créance", "dette fournisseur", "charge", "produit",
        "dotation aux amortissements", "réévaluation", "consolidation", "normes ifrs",
        "commissaire aux comptes", "expert comptable agréé",
        # Droit du travail / RH
        "code du travail", "droit du travail", "cnps", "cnss", "ipres", "inps", "ssnit",
        "contrat de travail", "licenciement", "indemnité", "préavis", "congé annuel",
        "heure supplémentaire", "salaire minimum", "smig", "convention collective",
        "règlement intérieur", "accident du travail", "maladie professionnelle",
        # Bancaire / BEAC-BCEAO
        "cobac", "bceao", "beac", "cemac", "uemoa", "bank al-maghrib", "bcrg",
        "ratio de solvabilité", "tier 1", "ration cooke", "réserve obligatoire",
        "crédit documentaire", "lettre de garantie", "nantissement",
        # Procédures judiciaires
        "selon le code", "texte de loi", "texte officiel", "disposition légale",
        "quelle est la loi", "est-ce légal", "est-ce conforme", "est légal",
        "selon la réglementation", "réglementairement", "infraction", "sanction pénale",
        "jurisprudence", "tribunal", "cour d'appel", "jugement", "arrêt", "décision de justice",
        # Douane / Commerce international
        "incoterm", "droits de douane", "tarif extérieur commun", "tec ", "valeur en douane",
        "régime douanier", "transit", "entrepôt sous douane", "admission temporaire",
        # Marchés publics
        "marché public", "appel d'offres", "dao ", "cahier des charges", "attribution marché",
        "bon de commande", "délégation de service public",
    ]
    return any(mot in msg_lower for mot in mots_cles_reglementaires)


_EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_MIME_IMAGE = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
}


def _extraire_texte_fichier(fichier) -> str:
    """
    Extrait le texte lisible d'un fichier joint (base64 ou texte brut).
    Supporte : TXT/CSV/JSON/MD, PDF, DOCX, XLSX, PPTX.
    Pour les images, retourne une description courte — les données visuelles
    sont transmises séparément via _extraire_images_fichiers().
    """
    import base64
    nom = fichier.nom.lower()
    ext = "." + nom.rsplit(".", 1)[-1] if "." in nom else ""
    contenu = fichier.contenu or ""

    # Si déjà du texte brut (pas de data URL)
    if not contenu.startswith("data:"):
        return contenu[:12000]

    try:
        b64 = contenu.split(",", 1)[1] if "," in contenu else contenu
        data = base64.b64decode(b64)

        # ── Texte brut / Markdown / CSV / JSON / XML ──────────────────────
        if ext in (".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm"):
            return data.decode("utf-8", errors="replace")[:14000]

        # ── PDF ───────────────────────────────────────────────────────────
        if ext == ".pdf":
            import io
            # Tentative 1 : pdfplumber (meilleur pour les tableaux)
            try:
                import pdfplumber
                parties_pdf = []
                with pdfplumber.open(io.BytesIO(data)) as pdf:
                    for num_p, page in enumerate(pdf.pages[:20], 1):
                        txt = page.extract_text() or ""
                        if txt.strip():
                            parties_pdf.append(txt)
                        for tbl in page.extract_tables():
                            if tbl and len(tbl) >= 2:
                                try:
                                    lignes_tbl = []
                                    for row in tbl:
                                        vals = [str(c).strip() if c else "" for c in row]
                                        lignes_tbl.append(" | ".join(vals))
                                    parties_pdf.append(f"[Tableau page {num_p}]\n" + "\n".join(lignes_tbl))
                                except Exception:
                                    pass
                texte = "\n\n".join(parties_pdf)
                if texte.strip():
                    return texte[:14000]
            except ImportError:
                pass
            # Tentative 2 : pypdf / PyPDF2
            for lib in ("pypdf", "PyPDF2"):
                try:
                    mod = __import__(lib)
                    reader = mod.PdfReader(io.BytesIO(data))
                    texte = "\n".join(p.extract_text() or "" for p in reader.pages[:20])
                    if texte.strip():
                        return texte[:14000]
                except (ImportError, Exception):
                    continue
            return f"[PDF : {fichier.nom} — installez pdfplumber pour l'extraction des tableaux]"

        # ── DOCX ──────────────────────────────────────────────────────────
        if ext in (".docx", ".doc"):
            try:
                import io, zipfile
                import re as _re
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    if "word/document.xml" in z.namelist():
                        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
                        texte = _re.sub(r"<[^>]+>", " ", xml)
                        texte = _re.sub(r"\s+", " ", texte).strip()
                        return texte[:14000]
            except Exception:
                pass
            return f"[DOCX : {fichier.nom} — extraction échouée]"

        # ── Excel XLSX ────────────────────────────────────────────────────
        if ext in (".xlsx", ".xls"):
            import io
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
                lignes = []
                for sheet_nom in wb.sheetnames[:5]:
                    ws = wb[sheet_nom]
                    lignes.append(f"\n=== {sheet_nom} ===")
                    for i, row in enumerate(ws.iter_rows(values_only=True)):
                        if i >= 300:
                            lignes.append("… [tronqué à 300 lignes]")
                            break
                        vals = [str(c) if c is not None else "" for c in row]
                        if any(v.strip() for v in vals):
                            lignes.append(" | ".join(vals))
                return "\n".join(lignes)[:14000]
            except ImportError:
                pass
            try:
                import xlrd
                wb = xlrd.open_workbook(file_contents=data)
                lignes = []
                for idx in range(min(5, wb.nsheets)):
                    ws = wb.sheet_by_index(idx)
                    lignes.append(f"\n=== {ws.name} ===")
                    for r in range(min(300, ws.nrows)):
                        vals = [str(ws.cell_value(r, c)) for c in range(ws.ncols)]
                        lignes.append(" | ".join(vals))
                return "\n".join(lignes)[:14000]
            except ImportError:
                pass
            return f"[Excel : {fichier.nom} — installez openpyxl pour l'extraction]"

        # ── PowerPoint PPTX ───────────────────────────────────────────────
        if ext == ".pptx":
            try:
                import io, zipfile
                import re as _re
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    slides = sorted(f for f in z.namelist()
                                    if f.startswith("ppt/slides/slide") and f.endswith(".xml"))
                    lignes = []
                    for i, s in enumerate(slides[:25]):
                        xml = z.read(s).decode("utf-8", errors="replace")
                        texte = _re.sub(r"<[^>]+>", " ", xml)
                        texte = _re.sub(r"\s+", " ", texte).strip()
                        if texte:
                            lignes.append(f"[Slide {i+1}] {texte[:600]}")
                    return "\n\n".join(lignes)[:12000]
            except Exception:
                pass
            return f"[PPTX : {fichier.nom} — extraction partielle non disponible]"

        # ── Images — analysées par vision IA, pas en texte ───────────────
        if ext in _EXTENSIONS_IMAGE:
            return f"[IMAGE : {fichier.nom} — analysée par vision IA]"

        return f"[{fichier.nom} — format {ext} non supporté]"

    except Exception as e:
        logger.warning(f"[Copilote] Extraction fichier {fichier.nom} échouée : {e}")
        return f"[{fichier.nom} — erreur d'extraction]"


def _extraire_images_fichiers(fichiers: list) -> list[str]:
    """
    Extrait les images des fichiers joints sous forme de base64 brut.
    Retourne une liste de strings base64 compatibles avec ia_client(images_b64=...).
    Claude Vision accepte : PNG, JPEG, WEBP, GIF. Taille max ~5 Mo par image.
    """
    import base64
    images_b64 = []
    for fichier in fichiers:
        nom = fichier.nom.lower()
        ext = "." + nom.rsplit(".", 1)[-1] if "." in nom else ""
        if ext not in _EXTENSIONS_IMAGE:
            continue
        contenu = fichier.contenu or ""
        try:
            b64 = contenu.split(",", 1)[1] if contenu.startswith("data:") else contenu
            # Vérification rapide + limite ~5 Mo (base64 ~4/3 de la taille binaire)
            if len(b64) > 7_000_000:
                logger.warning(f"[Copilote] Image {fichier.nom} trop grande (>5 Mo) — ignorée")
                continue
            base64.b64decode(b64[:64])  # validation
            images_b64.append(b64)
        except Exception as e:
            logger.warning(f"[Copilote] Image {fichier.nom} invalide : {e}")
    return images_b64



# ── Référentiels juridiques par pays ─────────────────────────────────────────
# Injectés dans le prompt système pour hyper-contextualiser les réponses LLM
_CADRE_JURIDIQUE_PAYS: dict[str, dict] = {
    "CM": {
        "nom_complet": "Cameroun",
        "zone_eco": "CEMAC (Communauté Économique et Monétaire de l'Afrique Centrale)",
        "devise": "Franc CFA BEAC (XAF) — 1 EUR ≈ 655,957 XAF",
        "banque_centrale": "BEAC (Banque des États de l'Afrique Centrale) / COBAC (supervision bancaire)",
        "fiscal": "CGI Cameroun (Code Général des Impôts) + loi de finances annuelle · TVA 19,25% · IS 30% · IRPP barème progressif · TF, TP, TPF · Taxe spéciale sur les revenus · DGI Yaoundé",
        "travail": "Code du travail du Cameroun (Loi n°92/007 du 14 août 1992 + modifications) · CNPS (retraite, AT, allocations familiales) · FASS · Convention collective applicable par secteur",
        "commercial": "Actes uniformes OHADA : AUDCG, AUS (sociétés commerciales), AUCAP, AUPCAP, AUSCOOP, AUPSRVE, AUDT · Registre du Commerce de Yaoundé/Douala (RCCM)",
        "comptable": "SYSCOHADA Révisé (Règlement n°01/2017/CM/OHADA du 30/11/2017) · Plan Comptable Général OHADA · Commissaires aux comptes (ONECCA Cameroun)",
        "assurance": "Code des assurances CIMA (Conférence Interafricaine des Marchés d'Assurances) · CRCA Cameroun · Branches IARD, Vie, Réassurance",
        "bancaire": "Réglementation COBAC · Lois sur le crédit · BEAC instruments de politique monétaire",
        "civil": "Code civil camerounais (héritage du Code civil français 1804 + adaptations camerounaises)",
        "penal": "Code pénal camerounais (Loi n°2016/007 du 12 juillet 2016)",
        "constitutionnel": "Constitution du Cameroun du 2 juin 1972, révisée le 18 janvier 1996",
        "specificites": "Système bijuridique (droit civil francophone + common law anglophone) · Zones francophones et anglophones · 10 régions",
    },
    "CI": {
        "nom_complet": "Côte d'Ivoire",
        "zone_eco": "UEMOA (Union Économique et Monétaire Ouest Africaine)",
        "devise": "Franc CFA BCEAO (XOF) — 1 EUR ≈ 655,957 XOF",
        "banque_centrale": "BCEAO (Banque Centrale des États de l'Afrique de l'Ouest) / BCEAO Abidjan",
        "fiscal": "CGI Côte d'Ivoire (Code Général des Impôts CI) · TVA 18% · BIC 25% · BNC · IRVM · Contribution employeur · DGI Abidjan",
        "travail": "Code du travail de Côte d'Ivoire (Loi n°2015-532 du 20 juillet 2015) · CNPS CI · Convention collective interprofessionnelle",
        "commercial": "Actes uniformes OHADA · RCCM Abidjan · Bourse Régionale des Valeurs Mobilières (BRVM Abidjan)",
        "comptable": "SYSCOHADA Révisé · ONECCA-CI (Ordre National des Experts-Comptables et Comptables Agréés de CI)",
        "assurance": "Code CIMA · CRCA Côte d'Ivoire",
        "civil": "Code civil ivoirien",
        "penal": "Code pénal de Côte d'Ivoire (Loi n°2019-574 du 26 juin 2019)",
        "specificites": "Principale économie UEMOA · Zone FCFA Ouest · BRVM pour les marchés financiers",
    },
    "SN": {
        "nom_complet": "Sénégal",
        "zone_eco": "UEMOA",
        "devise": "Franc CFA BCEAO (XOF)",
        "banque_centrale": "BCEAO / Agence principale de Dakar",
        "fiscal": "CGI Sénégal · TVA 18% · IS 30% · DGE (Direction des Grandes Entreprises) · DGID Dakar",
        "travail": "Code du travail sénégalais (Loi n°97-17 du 1er décembre 1997) · IPRES · CSS (sécurité sociale)",
        "commercial": "Actes uniformes OHADA · RCCM Dakar",
        "comptable": "SYSCOHADA Révisé · ONECCA Sénégal",
        "assurance": "Code CIMA · DRASS (Direction de la Réglementation et de la Supervision des Assurances)",
        "civil": "Code de la famille sénégalais (Loi n°72-61 du 12 juin 1972)",
        "penal": "Code pénal sénégalais",
        "specificites": "Hub régional UEMOA · Port de Dakar · Pôle financier Dakar",
    },
    "TG": {
        "nom_complet": "Togo",
        "zone_eco": "UEMOA",
        "devise": "Franc CFA BCEAO (XOF)",
        "banque_centrale": "BCEAO / Agence principale de Lomé",
        "fiscal": "CGI Togo · TVA 18% · IS 27% · Direction Générale des Impôts Lomé",
        "travail": "Code du travail togolais (Loi n°2021-012 du 18 juin 2021) · CNSS Togo",
        "commercial": "Actes uniformes OHADA · RCCM Lomé",
        "comptable": "SYSCOHADA Révisé",
        "assurance": "Code CIMA · DSARS Togo",
        "penal": "Code pénal togolais (Loi n°2015-010 du 24 novembre 2015)",
        "specificites": "Port franc de Lomé · Zone de libre-échange",
    },
    "BJ": {
        "nom_complet": "Bénin",
        "zone_eco": "UEMOA",
        "devise": "Franc CFA BCEAO (XOF)",
        "banque_centrale": "BCEAO / Cotonou",
        "fiscal": "CGI Bénin · TVA 18% · IS 30%",
        "travail": "Code du travail béninois (Loi n°98-004 du 27 janvier 1998) · CNSS Bénin",
        "commercial": "Actes uniformes OHADA",
        "comptable": "SYSCOHADA Révisé",
        "assurance": "Code CIMA",
        "specificites": "Commerce régional Afrique de l'Ouest",
    },
    "BF": {
        "nom_complet": "Burkina Faso",
        "zone_eco": "UEMOA",
        "devise": "Franc CFA BCEAO (XOF)",
        "banque_centrale": "BCEAO / Ouagadougou",
        "fiscal": "CGI Burkina Faso · TVA 18% · IS 27,5%",
        "travail": "Code du travail du Burkina Faso (Loi n°028-2008/AN du 13 mai 2008) · CNSS BF",
        "commercial": "Actes uniformes OHADA",
        "comptable": "SYSCOHADA Révisé",
        "assurance": "Code CIMA",
        "specificites": "Mines (or) · Agriculture · Sahel",
    },
    "ML": {
        "nom_complet": "Mali",
        "zone_eco": "UEMOA",
        "devise": "Franc CFA BCEAO (XOF)",
        "banque_centrale": "BCEAO / Bamako",
        "fiscal": "CGI Mali · TVA 18% · IS 30%",
        "travail": "Code du travail malien (Loi n°2017-021) · INPS Mali",
        "commercial": "Actes uniformes OHADA",
        "comptable": "SYSCOHADA Révisé",
        "assurance": "Code CIMA",
        "specificites": "Mines (or) · Agriculture · Secteur minier actif",
    },
    "GA": {
        "nom_complet": "Gabon",
        "zone_eco": "CEMAC",
        "devise": "Franc CFA BEAC (XAF)",
        "banque_centrale": "BEAC / Libreville · COBAC",
        "fiscal": "CGI Gabon · TVA 18% · IS 30%",
        "travail": "Code du travail gabonais (Loi n°3/94 du 21 novembre 1994) · CNSS Gabon",
        "commercial": "Actes uniformes OHADA",
        "comptable": "SYSCOHADA Révisé",
        "assurance": "Code CIMA",
        "specificites": "Pétrole · Mines · Forêts · Revenu par tête élevé en Afrique subsaharienne",
    },
    "CG": {
        "nom_complet": "République du Congo (Congo-Brazzaville)",
        "zone_eco": "CEMAC",
        "devise": "Franc CFA BEAC (XAF)",
        "banque_centrale": "BEAC / Brazzaville · COBAC",
        "fiscal": "CGI Congo · TVA 18,9% · IS 30%",
        "travail": "Code du travail congolais (Loi n°6-96 du 6 mars 1996) · CNSS Congo",
        "commercial": "Actes uniformes OHADA",
        "comptable": "SYSCOHADA Révisé",
        "assurance": "Code CIMA",
        "specificites": "Pétrole · CEMAC · Congo-Brazzaville (distinct de RDC)",
    },
    "GN": {
        "nom_complet": "Guinée (Conakry)",
        "zone_eco": "Hors UEMOA/CEMAC — CEDEAO",
        "devise": "Franc guinéen (GNF)",
        "banque_centrale": "BCRG (Banque Centrale de la République de Guinée)",
        "fiscal": "Code général des impôts Guinée · TVA 18% · IS 35%",
        "travail": "Code du travail guinéen (Loi L/2014/072/CNT du 10 janvier 2014) · CNSS Guinée",
        "commercial": "Actes uniformes OHADA",
        "comptable": "SYSCOHADA Révisé",
        "assurance": "Non zone CIMA — réglementation nationale",
        "specificites": "Mines (bauxite, or) · Monnaie propre (GNF) · Non membre UEMOA ni CEMAC",
    },
    "CD": {
        "nom_complet": "République Démocratique du Congo (RDC)",
        "zone_eco": "SADC / CEEAC — hors OHADA jusqu'à récemment",
        "devise": "Franc congolais (CDF)",
        "banque_centrale": "Banque Centrale du Congo (BCC) / Kinshasa",
        "fiscal": "Code général des impôts RDC · TVA 16% · IS 30%",
        "travail": "Code du travail RDC (Loi n°015-2002 du 16 octobre 2002)",
        "commercial": "Actes uniformes OHADA (adhésion 2012) · Droit commercial congolais",
        "comptable": "SYSCOHADA Révisé (depuis adoption OHADA)",
        "assurance": "Réglementation ARCA (Autorité de Régulation et de Contrôle des Assurances)",
        "specificites": "Mines (cuivre, cobalt, coltan) · Vaste territoire · Franc congolais (pas FCFA)",
    },
    "MG": {
        "nom_complet": "Madagascar",
        "zone_eco": "SADC — hors OHADA",
        "devise": "Ariary malgache (MGA)",
        "banque_centrale": "Banque Centrale de Madagascar (BFM) / Antananarivo",
        "fiscal": "CGI Madagascar · TVA 20% · IS 20%",
        "travail": "Code du travail malgache (Loi n°2003-044)",
        "commercial": "Droit commercial national (non OHADA)",
        "comptable": "Plan Comptable Général 2005 (propre)",
        "assurance": "Réglementation nationale des assurances (ARO/NY HAVANA)",
        "specificites": "Île — hors zone FCFA · Ariary · Non membre OHADA",
    },
    "MA": {
        "nom_complet": "Maroc",
        "zone_eco": "Afrique du Nord — Accord Agadir · Zone de libre-échange Afrique",
        "devise": "Dirham marocain (MAD)",
        "banque_centrale": "Bank Al-Maghrib / Rabat",
        "fiscal": "CGI Maroc (Loi de finances annuelle) · TVA 20% · IS 31% · IR barème progressif · DGI Rabat",
        "travail": "Code du travail marocain (Loi n°65-99) · CNSS Maroc · AMO (assurance maladie)",
        "commercial": "Code de commerce marocain · Loi sur les SA · Loi SARL · Bourse de Casablanca",
        "comptable": "Code Général de la Normalisation Comptable (CGNC) · Plan Comptable Général marocain · ISCAE",
        "assurance": "Code des assurances marocain (Loi n°17-99) · ACAPS (Autorité de Contrôle des Assurances et de la Prévoyance Sociale)",
        "civil": "Code de la famille (Moudawwana) · Dahir des obligations et contrats (DOC)",
        "penal": "Code pénal marocain",
        "specificites": "Dirham (non FCFA) · Casablanca Finance City · Non membre OHADA · Liens forts avec Europe",
    },
    "TN": {
        "nom_complet": "Tunisie",
        "zone_eco": "Afrique du Nord — Accord d'association UE",
        "devise": "Dinar tunisien (TND)",
        "banque_centrale": "Banque Centrale de Tunisie (BCT) / Tunis",
        "fiscal": "Code de l'IRPP et de l'IS Tunisie · TVA 19% · IS 15-25% · DGE Tunis",
        "travail": "Code du travail tunisien (Loi n°66-27 du 30 avril 1966) · CNSS Tunisie · CNAM",
        "commercial": "Code des sociétés commerciales (CSC) de 2000 · Bourse de Tunis",
        "comptable": "Système comptable des entreprises (SCE) tunisien · Norme comptable NC · OECT",
        "assurance": "Code des assurances tunisien · Comité Général des Assurances (CGA)",
        "specificites": "Dinar tunisien · Non membre OHADA · Proximité Europe · Offshore banking",
    },
    "GH": {
        "nom_complet": "Ghana",
        "zone_eco": "CEDEAO — Commonwealth",
        "devise": "Cedi ghanéen (GHS)",
        "banque_centrale": "Bank of Ghana / Accra",
        "fiscal": "Income Tax Act 2015 (Act 896) · VAT 15% · Corporate Tax 25% · GRA (Ghana Revenue Authority)",
        "travail": "Labour Act 2003 (Act 651) · SSNIT (pension)",
        "commercial": "Companies Act 2019 (Act 992) · Ghana Stock Exchange · SEC Ghana",
        "comptable": "IFRS (International Financial Reporting Standards) · ICAG (Institute of Chartered Accountants Ghana)",
        "assurance": "Insurance Act 2021 (Act 1061) · NIC (National Insurance Commission)",
        "specificites": "Anglophone · Common law · Cedi (non FCFA) · Pétrole, cacao, or · Non OHADA",
    },
    "NG": {
        "nom_complet": "Nigeria",
        "zone_eco": "CEDEAO — Commonwealth — Anglophone",
        "devise": "Naira nigérian (NGN)",
        "banque_centrale": "Central Bank of Nigeria (CBN) / Abuja",
        "fiscal": "Companies Income Tax Act (CITA) · VAT 7.5% · Corporate Tax 30% · FIRS (Federal Inland Revenue Service)",
        "travail": "Labour Act Cap L1 LFN 2004 · Pension Reform Act 2014 · PENCOM",
        "commercial": "Companies and Allied Matters Act 2020 (CAMA) · Nigerian Stock Exchange (NGX)",
        "comptable": "IFRS / IPSAS · ICAN (Institute of Chartered Accountants of Nigeria)",
        "assurance": "Insurance Act 2003 · NAICOM (National Insurance Commission)",
        "specificites": "Plus grande économie Afrique · Naira · Common law · Anglophone · Pétrole · Non OHADA",
    },
    "ZA": {
        "nom_complet": "Afrique du Sud",
        "zone_eco": "SADC — G20 — BRICS",
        "devise": "Rand sud-africain (ZAR)",
        "banque_centrale": "South African Reserve Bank (SARB) / Pretoria",
        "fiscal": "Income Tax Act 58/1962 · VAT Act 89/1991 (VAT 15%) · Corporate Tax 27% · SARS (South African Revenue Service)",
        "travail": "Labour Relations Act 66/1995 · Basic Conditions of Employment Act · UIF · COIDA",
        "commercial": "Companies Act 71/2008 · JSE (Johannesburg Stock Exchange) · FSCA",
        "comptable": "IFRS / IFRS for SMEs · SAICA (South African Institute of Chartered Accountants)",
        "assurance": "Insurance Act 18/2017 · FSCA (Financial Sector Conduct Authority)",
        "civil": "Common law (héritage anglais + droit romano-hollandais)",
        "specificites": "Rand (ZAR) · Common law + droit civil · JSE · Économie la plus industrialisée d'Afrique · 11 langues officielles",
    },
    "KE": {
        "nom_complet": "Kenya",
        "zone_eco": "CAE (Communauté d'Afrique de l'Est) — Commonwealth",
        "devise": "Shilling kényan (KES)",
        "banque_centrale": "Central Bank of Kenya (CBK) / Nairobi",
        "fiscal": "Income Tax Act Cap 470 · VAT Act 2013 (16%) · Corporate Tax 30% · KRA (Kenya Revenue Authority)",
        "travail": "Employment Act 2007 · Labour Relations Act 2007 · NSSF · NHIF",
        "commercial": "Companies Act 2015 · Nairobi Securities Exchange (NSE) · CMA Kenya",
        "comptable": "IFRS · ICPAK (Institute of Certified Public Accountants of Kenya)",
        "assurance": "Insurance Act Cap 487 · IRA (Insurance Regulatory Authority)",
        "specificites": "Shilling kényan · Common law · Hub financier Afrique de l'Est · Nairobi International Financial Centre",
    },
    "ET": {
        "nom_complet": "Éthiopie",
        "zone_eco": "IGAD — UA",
        "devise": "Birr éthiopien (ETB)",
        "banque_centrale": "National Bank of Ethiopia (NBE) / Addis-Abeba",
        "fiscal": "Income Tax Proclamation 979/2016 · VAT 15% · Business Profit Tax 30% · ERCA",
        "travail": "Labour Proclamation 1156/2019 · PSNP",
        "commercial": "Commercial Code 2021 · Ethiopian Capital Market Authority",
        "comptable": "IFRS (adoption progressive) · Normes nationales transitoires",
        "assurance": "Insurance Business Proclamation 746/2012 · NBE supervision",
        "specificites": "Birr · Droit civil (héritage franco-éthiopien) · 2ème population Afrique · Non anglophone",
    },
    "MU": {
        "nom_complet": "Maurice (Île Maurice)",
        "zone_eco": "COMESA — SADC — Commonwealth",
        "devise": "Roupie mauricienne (MUR)",
        "banque_centrale": "Bank of Mauritius / Port-Louis",
        "fiscal": "Income Tax Act 1995 · VAT Act 1998 (15%) · Corporate Tax 15% · MRA (Mauritius Revenue Authority)",
        "travail": "Workers' Rights Act 2019 · NPF (National Pensions Fund) · NSF",
        "commercial": "Companies Act 2001 · Stock Exchange of Mauritius (SEM) · FSC",
        "comptable": "IFRS · MIPA (Mauritius Institute of Professional Accountants)",
        "assurance": "Insurance Act 2005 · FSC (Financial Services Commission)",
        "specificites": "Roupie mauricienne · Common law + droit civil · Centre financier offshore · Bilingue français/anglais · Fiscalité attractive",
    },
    "FR": {
        "nom_complet": "France",
        "zone_eco": "Union Européenne — Zone Euro",
        "devise": "Euro (EUR) — Banque centrale européenne (BCE)",
        "banque_centrale": "Banque de France / Paris — sous tutelle BCE",
        "fiscal": "Code général des impôts (CGI) France · TVA 20% (taux normal) · IS 25% (taux normal) · IRPP barème progressif · DGFiP · Liasse fiscale 2050-2058",
        "travail": "Code du travail français (Partie législative L.) · URSSAF · CPAM · Retraite AGIRC-ARRCO · Conventions collectives (IDCC) · CSE (Comité Social et Économique)",
        "commercial": "Code de commerce français · SA, SAS, SARL, EURL, SCI · AMF (Autorité des marchés financiers) · Euronext Paris",
        "comptable": "Plan Comptable Général (PCG 2014) · Normes ANC · IFRS pour cotés en bourse · Commissaires aux comptes (CNCC) · Experts-comptables (CNOEC)",
        "assurance": "Code des assurances français · ACPR (Autorité de Contrôle Prudentiel et de Résolution) · Solvabilité II",
        "civil": "Code civil français (depuis 1804, réformé 2016) · Code de procédure civile",
        "penal": "Code pénal français · Code de procédure pénale",
        "specificites": "Droit civil (Code Napoléon) · Non OHADA · Zone Euro · Sécurité sociale universelle · Retraite obligatoire · Droit du travail très protecteur",
    },
    "BE": {
        "nom_complet": "Belgique",
        "zone_eco": "Union Européenne — Zone Euro",
        "devise": "Euro (EUR)",
        "banque_centrale": "Banque Nationale de Belgique (BNB) / Bruxelles — sous tutelle BCE",
        "fiscal": "Code des impôts sur les revenus 1992 (CIR92) · TVA 21% · Impôt des sociétés 25% · SPF Finances · Précompte mobilier et immobilier",
        "travail": "Code du travail belge · ONSS (Office National de Sécurité Sociale) · ONEM (chômage) · Fonds de sécurité d'existence · CP (commissions paritaires)",
        "commercial": "Code des sociétés et associations (CSA 2019) · SA, SRL, SC, ASBL · FSMA · Euronext Bruxelles",
        "comptable": "Droit comptable belge (loi du 17/07/1975) · Plan comptable minimum normalisé (PCMN) · IRE (Réviseurs d'entreprises) · ITAA (Experts-comptables)",
        "assurance": "Code des assurances belge (loi du 4/04/2014) · BNB supervision assurance",
        "specificites": "Euro · Trois régions (Bruxelles, Wallonie, Flandre) · Trois langues officielles · Non OHADA · Droit civil + common law influences",
    },
    "CH": {
        "nom_complet": "Suisse",
        "zone_eco": "Hors UE — AELE (Association Européenne de Libre-Échange)",
        "devise": "Franc suisse (CHF)",
        "banque_centrale": "Banque Nationale Suisse (BNS/SNB) / Berne-Zurich",
        "fiscal": "Loi sur l'impôt fédéral direct (LIFD) · TVA 8.1% (taux normal) · Impôt cantonal et communal variable · AFC (Administration Fédérale des Contributions)",
        "travail": "Code des obligations (CO) · Loi sur le travail (LTr) · AVS/AI/APG · LAA · LPP (prévoyance professionnelle 2e pilier)",
        "commercial": "Code des obligations (CO) - Livre V · SA, Sàrl, SC · SIX Swiss Exchange · FINMA",
        "comptable": "Swiss GAAP RPC (Recommandations relatives à la présentation des comptes) · IFRS pour cotés · EXPERTsuisse",
        "assurance": "Loi sur le contrat d'assurance (LCA) · FINMA (Autorité de surveillance des marchés financiers)",
        "specificites": "CHF (Franc suisse) · Non UE · Fédéralisme fiscal (impôt cantonal) · 4 langues · Secret bancaire allégé · Place financière mondiale · Non OHADA",
    },
    "DE": {
        "nom_complet": "Allemagne",
        "zone_eco": "Union Européenne — Zone Euro",
        "devise": "Euro (EUR)",
        "banque_centrale": "Deutsche Bundesbank / Francfort — sous tutelle BCE",
        "fiscal": "Einkommensteuergesetz (EStG) · Körperschaftsteuergesetz (KStG) · IS 15% + Taxe solidarité 5.5% + Gewerbesteuer (~14%) = ~30% · TVA 19% · Finanzamt",
        "travail": "Bürgerliches Gesetzbuch (BGB) - droit du travail · Betriebsverfassungsgesetz (BetrVG) · Deutsche Rentenversicherung · Bundesagentur für Arbeit",
        "commercial": "Handelsgesetzbuch (HGB) · GmbH, AG, OHG · Deutsche Börse (DAX) · BaFin",
        "comptable": "Handelsgesetzbuch (HGB) - 3e livre · Grundsätze ordnungsmäßiger Buchführung (GoB) · IFRS pour cotés · WPK (Wirtschaftsprüferkammer)",
        "assurance": "Versicherungsaufsichtsgesetz (VAG) · BaFin supervision · Solvabilité II",
        "specificites": "Euro · Droit civil germanique · Cogestion (Mitbestimmung) · Codétermination salariale · Bundesrat/Bundestag · Non OHADA",
    },
    "GB": {
        "nom_complet": "Royaume-Uni",
        "zone_eco": "Hors UE (post-Brexit) — Commonwealth",
        "devise": "Livre sterling (GBP)",
        "banque_centrale": "Bank of England / Londres",
        "fiscal": "Income Tax Act 2007 · Corporation Tax 25% · VAT 20% · HMRC (His Majesty's Revenue and Customs) · PAYE",
        "travail": "Employment Rights Act 1996 · National Minimum Wage Act 1998 · National Insurance · Pension Act 2008 · ACAS",
        "commercial": "Companies Act 2006 · London Stock Exchange (LSE) · FCA (Financial Conduct Authority) · PRA",
        "comptable": "UK GAAP (FRS 100-105) · IFRS UK · ICAEW (Institute of Chartered Accountants in England and Wales) · ICAS · ACCA",
        "assurance": "Financial Services and Markets Act 2000 (FSMA) · FCA/PRA · Lloyd's of London",
        "civil": "Common law (droit coutumier) · Equity · Précédent (stare decisis)",
        "specificites": "GBP · Common law · Post-Brexit · Non UE · Non OHADA · Centre financier mondial (City of London)",
    },
    "US": {
        "nom_complet": "États-Unis",
        "zone_eco": "USMCA (ex-ALENA) — G7 — G20",
        "devise": "Dollar américain (USD)",
        "banque_centrale": "Federal Reserve (Fed) / Washington D.C.",
        "fiscal": "Internal Revenue Code (IRC) · Corporate Tax 21% (TCJA 2017) · Sales Tax (État) · IRS · Form 1120 (société) · Form 1040 (particuliers)",
        "travail": "Fair Labor Standards Act (FLSA) · National Labor Relations Act (NLRA) · FMLA · OSHA · Social Security Administration · At-will employment",
        "commercial": "Uniform Commercial Code (UCC) · Delaware General Corporation Law · NYSE/NASDAQ · SEC (Securities and Exchange Commission)",
        "comptable": "US GAAP (Generally Accepted Accounting Principles) · FASB · PCAOB · AICPA · CPA (Certified Public Accountant)",
        "assurance": "Réglementation État par État · NAIC (National Association of Insurance Commissioners) · Surplus Lines",
        "civil": "Common law + droit constitutionnel fédéral · Système fédéral (lois fédérales + 50 États)",
        "specificites": "USD · Common law · Système fédéral · Non OHADA · Fiscalité par État · Marché financier mondial · Litiges class action",
    },
    "CA": {
        "nom_complet": "Canada",
        "zone_eco": "USMCA — G7 — Commonwealth",
        "devise": "Dollar canadien (CAD)",
        "banque_centrale": "Banque du Canada / Ottawa",
        "fiscal": "Loi de l'impôt sur le revenu (LIR) · Impôt fédéral sociétés 15% + provincial ~12% = ~27% · TPS 5% + TVP/TVH provinciale · ARC (Agence du revenu du Canada)",
        "travail": "Code canadien du travail (CCT) · Lois provinciales du travail · RPC/RRQ · AE (assurance-emploi) · CNESST (Québec)",
        "commercial": "Loi canadienne sur les sociétés par actions (LCSA) · Loi sur les sociétés par actions (Québec) · TSX · ACVM",
        "comptable": "IFRS (cotés) · NCECF (Normes comptables pour les entreprises à capital fermé) · CPA Canada",
        "assurance": "Loi sur les sociétés d'assurances (fédérale) · BSIF · AMF (Québec)",
        "specificites": "CAD · Système fédéral biculturel · Common law (hors Québec) + droit civil (Québec) · Bilingue français/anglais · Non OHADA",
    },
    "PT": {
        "nom_complet": "Portugal",
        "zone_eco": "Union Européenne — Zone Euro",
        "devise": "Euro (EUR)",
        "banque_centrale": "Banco de Portugal / Lisbonne — sous tutelle BCE",
        "fiscal": "Código do IRC (Imposto sobre o Rendimento das Pessoas Coletivas) · IRC 21% · IVA 23% · AT (Autoridade Tributária e Aduaneira)",
        "travail": "Código do Trabalho (CT 2009) · Segurança Social · CITE · ACT",
        "commercial": "Código das Sociedades Comerciais (CSC) · SA, Lda · Euronext Lisbonne · CMVM",
        "comptable": "SNC (Sistema de Normalização Contabilística) · IFRS pour cotés · OROC (Revisores Oficiais de Contas) · OCC",
        "assurance": "Lei 147/2015 (Solvabilité II) · ASF (Autoridade de Supervisão de Seguros e Fundos de Pensões)",
        "specificites": "Euro · Droit civil (Code Napoléon influence) · Lusophone · Liens historiques avec PALOP (Angola, Mozambique, Cap-Vert…) · Non OHADA",
    },
    "ES": {
        "nom_complet": "Espagne",
        "zone_eco": "Union Européenne — Zone Euro",
        "devise": "Euro (EUR)",
        "banque_centrale": "Banco de España / Madrid — sous tutelle BCE",
        "fiscal": "Ley del Impuesto sobre Sociedades (LIS) · IS 25% · IVA 21% · IRPF · AEAT (Agencia Estatal de Administración Tributaria)",
        "travail": "Estatuto de los Trabajadores (ET) · Seguridad Social · SEPE · Convenios Colectivos · ERE",
        "commercial": "Ley de Sociedades de Capital (LSC) · SA, SL · BME (Bolsa y Mercados Españoles) · CNMV",
        "comptable": "Plan General de Contabilidad (PGC 2007) · IFRS pour cotés · ICAC · REA (Registro de Economistas Auditores)",
        "assurance": "Ley de Ordenación y Supervisión de los Seguros Privados · DGS (Dirección General de Seguros) · Solvabilité II",
        "specificites": "Euro · Droit civil · Non OHADA · 17 Communautés autonomes · Langues officielles régionales · Hub ibéro-américain",
    },
    "IT": {
        "nom_complet": "Italie",
        "zone_eco": "Union Européenne — Zone Euro",
        "devise": "Euro (EUR)",
        "banque_centrale": "Banca d'Italia / Rome — sous tutelle BCE",
        "fiscal": "TUIR (Testo Unico delle Imposte sui Redditi) · IRES 24% · IRAP ~3.9% · IVA 22% · Agenzia delle Entrate",
        "travail": "Codice Civile (art. 2094+) · Statuto dei Lavoratori (L.300/1970) · INPS · INAIL · CCNL (contratti collettivi nazionali)",
        "commercial": "Codice Civile (livre V) · SPA, SRL, SNC · Borsa Italiana (Euronext) · Consob · Banca d'Italia",
        "comptable": "Codice Civile + OIC (Organismi Italiani di Contabilità) · IFRS pour cotés · CNDCEC (Commercialisti)",
        "assurance": "Codice delle Assicurazioni Private (D.Lgs. 209/2005) · IVASS (Instituto per la Vigilanza sulle Assicurazioni) · Solvabilité II",
        "specificites": "Euro · Droit civil romano-germanique · Non OHADA · G7 · PME/PMI nombreuses · Districts industriels",
    },
    "DZ": {
        "nom_complet": "Algérie",
        "zone_eco": "Afrique du Nord — Accord d'association UE — ZLECAf",
        "devise": "Dinar algérien (DZD)",
        "banque_centrale": "Banque d'Algérie / Alger",
        "fiscal": "Code des impôts directs et taxes assimilées (CIDTA) · Code des taxes sur le chiffre d'affaires (CTCA) · TVA 19% · IBS 19-26% · DGI Alger",
        "travail": "Code du travail algérien (Loi n°90-11 du 21/04/1990 + modifications) · CNAS · CASNOS · CNR",
        "commercial": "Code de commerce algérien · EURL, SARL, SPA · Bourse d'Alger (SGBV)",
        "comptable": "Système Comptable Financier (SCF 2010) — inspiré des normes IAS/IFRS · Conseil National de la Comptabilité (CNC) · ONEC",
        "assurance": "Code des assurances algérien (Ordonnance n°95-07 modifiée) · CNA (Commission Nationale des Assurances)",
        "civil": "Code civil algérien (Ordonnance n°75-58) — inspiré du droit civil français et du droit musulman",
        "penal": "Code pénal algérien (Ordonnance n°66-156)",
        "specificites": "DZD (Dinar algérien) · Non OHADA · Non FCFA · Droit civil mixte (civil français + droit musulman) · Hydrocarbures (pétrole, gaz) · Sonatrach",
    },
    # Défaut générique pour les pays non listés
    "_DEFAULT": {
        "nom_complet": "Ce pays",
        "zone_eco": "À préciser selon le pays",
        "devise": "Monnaie nationale applicable",
        "banque_centrale": "Banque centrale nationale",
        "fiscal": "Code des impôts national en vigueur — TVA, impôt société, impôt revenu selon les règles locales",
        "travail": "Code du travail national applicable — conventions collectives, sécurité sociale",
        "commercial": "Droit commercial national · Droit des sociétés local · Marchés boursiers nationaux",
        "comptable": "Normes comptables nationales (IFRS si pays appliquant les standards internationaux, sinon plan comptable local)",
        "assurance": "Réglementation nationale des assurances — autorité de supervision locale",
        "specificites": "Appliquer le cadre juridique spécifique du pays de l'utilisateur — demander confirmation si nécessaire",
    },
}

# Mapping métier → domaines juridiques prioritaires
_METIER_CORPUS_PRIORITAIRE: dict[str, list[str]] = {
    "expert_comptable":    ["comptable (SYSCOHADA, Plan Comptable)", "fiscal (CGI, TVA, IS, IRPP)", "commercial (OHADA-AUS, AUDCG)", "social (Code du travail, CNPS)"],
    "juriste":             ["commercial (Actes uniformes OHADA)", "civil (Code civil)", "pénal (Code pénal)", "procédures (AUPSRVE, AUDT)", "travail (Code du travail)"],
    "fiscal":              ["fiscal (CGI, TVA, IS, IRPP, droits d'enregistrement)", "comptable (lien comptabilité-fiscalité)", "commercial (optimisation fiscale)"],
    "auditeur":            ["comptable (SYSCOHADA, normes audit)", "fiscal (conformité CGI)", "commercial (governance OHADA)"],
    "conseiller_assurance":["assurance (Code CIMA, branches, provisions techniques)", "commercial (contrats assurance)", "fiscal (fiscalité assurances)"],
    "banquier":            ["bancaire (réglementation COBAC/BCEAO)", "commercial (crédit, garanties OHADA)", "fiscal (TVA bancaire, retenues à la source)"],
    "charge_projets_ong":  ["travail (Code du travail, conventions collectives)", "commercial (marchés publics)", "fiscal (exonérations ONG)"],
    "responsable_microfinance": ["bancaire (réglementation SFD/IMF BCEAO/COBAC)", "commercial (droit des sûretés OHADA)", "travail (Code du travail)"],
    "transitaire":         ["commercial (incoterms, code douanier, CEMAC/UEMOA TEC)", "fiscal (droits de douane, TVA import)"],
    "consultant":          ["commercial (contrats de prestation, OHADA)", "fiscal (facturation, TVA, BNC)", "travail (statut consultant vs salarié)"],
    "entrepreneur":        ["commercial (création SARL/SA, statuts OHADA)", "fiscal (régimes d'imposition, CGI)", "travail (droit du travail employeur)"],
    "autre":               ["commercial (OHADA)", "fiscal (CGI)", "travail (Code du travail)"],
}

# Couverture réelle des documents RAG indexés par pays/domaine
# Utilisé dans le prompt pour que le LLM sache quand attendre du contexte RAG vs sa mémoire
_RAG_COUVERTURE = {
    "CGI_indexé":    ["CM", "CI", "SN", "TG", "BF", "CG", "GN"],
    "travail_indexé": ["CM", "CI", "SN", "TG", "BF", "CG", "GA", "CF"],
    "penal_indexé":  ["CM", "CI", "SN", "TG", "BF", "CG", "GA", "GN", "CD", "MG", "CF"],
    "OHADA_indexé":  ["tous les pays OHADA (AUS, AUDCG, AUPCAP, AUSCOOP, AUSCGIE, AUA, SYSCOHADA)"],
    "normes_ISO":    ["ISO 45001 (SST) — applicable à tous pays"],
    "normes_OIT":    ["Conventions OIT — applicables à tous membres"],
    "non_couvert":   ["MA", "TN", "GH", "NG", "CD (partiel)", "MG"],
}


# ── Navigation modules — suggestions contextuelles ───────────────────────────
_NAVIGATION_MAP = [
    {
        "keywords": ["réunion", "reunion", "procès-verbal", "proces verbal", "pv réunion",
                     "ordre du jour", "compte rendu réunion", "rédiger pv", "rapport réunion"],
        "label": "Module Réunions", "route": "/reunions", "icon": "users",
        "description": "Gérer vos réunions, générer PV et rapports automatiquement",
    },
    {
        "keywords": ["traduire", "traduction", "translate", "traducteur", "version anglaise",
                     "version française", "document traduit"],
        "label": "Traduction Documents", "route": "/traduction", "icon": "languages",
        "description": "Traduire des documents dans plusieurs langues",
    },
    {
        "keywords": ["traduction live", "interprétation", "simultané", "microphone traduction",
                     "traduction temps réel", "interprète"],
        "label": "Traduction Live", "route": "/translate-live", "icon": "mic",
        "description": "Interprétation en temps réel via microphone",
    },
    {
        "keywords": ["rapport word", "générer rapport", "creer rapport", "document word",
                     "fichier docx", "slides powerpoint", "présentation ppt", "business plan",
                     "générer document", "yukpo studio", "studio", "mes generateurs"],
        "label": "Yukpo Studio", "route": "/generateurs", "icon": "file-text",
        "description": "Générer rapports, contrats, slides et autres documents téléchargeables",
    },
    {
        "keywords": ["emploi", "recrutement", "offre emploi", "cherche emploi",
                     "candidature", "cv", "lettre de motivation", "poste disponible"],
        "label": "Offres d'emploi", "route": "/emploi", "icon": "briefcase",
        "description": "Rechercher des offres d'emploi et préparer votre candidature",
    },
    {
        "keywords": ["marché public", "appel d'offres", "appel offres", "dao", "dossier appel",
                     "marchés publics", "soumission", "avis d'appel"],
        "label": "Marchés Publics", "route": "/marches", "icon": "building-2",
        "description": "Suivre les appels d'offres et marchés publics",
    },
    {
        "keywords": ["enquête", "sondage", "questionnaire", "formulaire enquête",
                     "collecter données", "survey"],
        "label": "Module Enquêtes", "route": "/enquetes", "icon": "clipboard-list",
        "description": "Créer et gérer des enquêtes et sondages professionnels",
    },
    {
        "keywords": ["mes documents", "historique documents", "documents générés",
                     "télécharger mes fichiers", "retrouver document"],
        "label": "Mes Documents", "route": "/mes-documents", "icon": "folder-open",
        "description": "Retrouver et télécharger tous vos documents générés",
    },
    {
        "keywords": ["tableau de bord", "dashboard", "statistiques", "mes stats",
                     "mon activité", "xp points"],
        "label": "Dashboard", "route": "/dashboard", "icon": "bar-chart-2",
        "description": "Voir vos statistiques d'utilisation et votre progression",
    },
]


# Table de résolution : clé LLM → entrée _NAVIGATION_MAP
_MODULE_KEY_TO_ROUTE = {
    "reunions":       "/reunions",
    "traduction":     "/traduction",
    "translate_live": "/translate-live",
    "generateur":     "/generateurs",
    "emploi":         "/emploi",
    "marches":        "/marches",
    "enquetes":       "/enquetes",
    "mes_documents":  "/mes-documents",
    "dashboard":      "/dashboard",
}


def _suggestions_modules(
    message: str,
    intention: str = "",
    modules_llm: list[str] | None = None,
) -> list[dict]:
    """
    Retourne 0-2 suggestions de navigation.
    Priorité : résultat LLM (modules_llm) → fallback mots-clés.
    """
    # Construire l'index route → entrée pour lookups rapides
    _route_map = {e["route"]: e for e in _NAVIGATION_MAP}

    suggestions: list[dict] = []

    # 1. Suggestions issues de l'orchestrateur LLM (compréhension sémantique)
    if modules_llm:
        for key in modules_llm:
            route = _MODULE_KEY_TO_ROUTE.get(key)
            if route and route in _route_map:
                e = _route_map[route]
                suggestions.append({
                    "label": e["label"], "route": e["route"],
                    "icon": e["icon"],   "description": e["description"],
                })
            if len(suggestions) >= 2:
                break

    # 2. Fallback mots-clés si le LLM n'a rien retourné
    if not suggestions:
        msg = message.lower()
        for entry in _NAVIGATION_MAP:
            if any(kw in msg for kw in entry["keywords"]):
                suggestions.append({
                    "label": entry["label"], "route": entry["route"],
                    "icon": entry["icon"],   "description": entry["description"],
                })
            if len(suggestions) >= 2:
                break

    return suggestions[:2]


def _prompt_systeme_copilote(profil, pays: str, langue: str) -> str:
    """
    Construit le prompt système hyper-contextualisé du copilote.
    Injecte le cadre juridique précis du pays + profil métier pour
    éliminer les hallucinations et garantir des réponses précises et localisées.
    """
    metier = getattr(profil, "metier", "") or ""
    nom = getattr(profil, "nom", "") or ""
    pays_code = (getattr(profil, "pays", "") or pays or "").upper()
    # secteur_activite = secteur économique réel ("finance_banque", etc.)
    secteur = getattr(profil, "secteur_activite", "") or getattr(profil, "secteur", "") or ""
    niveau = getattr(profil, "niveau", "") or "senior"
    prefs = getattr(profil, "preferences", None) or {}
    experience = prefs.get("annees_experience")
    pays_connu = bool(pays_code)
    metier_connu = bool(metier)

    # Récupérer le cadre juridique du pays (fallback _DEFAULT si pays inconnu ou non renseigné)
    cadre = _CADRE_JURIDIQUE_PAYS.get(pays_code, _CADRE_JURIDIQUE_PAYS["_DEFAULT"])
    pays_nom = cadre["nom_complet"] if pays_connu else "(pays non renseigné dans le profil)"
    zone_eco = cadre["zone_eco"] if pays_connu else "—"
    devise = cadre["devise"] if pays_connu else "—"
    banque_centrale = cadre["banque_centrale"] if pays_connu else "—"
    specificites = cadre.get("specificites", "") if pays_connu else ""

    # Corpus prioritaire selon le métier (si connu)
    if metier_connu and metier in _METIER_CORPUS_PRIORITAIRE:
        corpus_metier = _METIER_CORPUS_PRIORITAIRE[metier]
    else:
        corpus_metier = _METIER_CORPUS_PRIORITAIRE.get("autre", [
            "Adapter le corpus au métier réel de l'utilisateur",
            "Fiscal, social, commercial, sectoriel — selon la question posée",
        ])
    corpus_str = "\n   - ".join(corpus_metier)

    # Niveau d'expertise → ajuster le ton
    ton_niveau = {
        "junior":        "Explique les concepts avec des exemples simples. Définis les termes techniques.",
        "debutant":      "Explique les concepts avec des exemples simples. Définis les termes techniques.",
        "intermediaire": "Réponds avec précision technique, en supposant une bonne base professionnelle.",
        "senior":        "Réponds de pair à pair, avec précision technique maximale et nuances pratiques.",
        "expert":        "Réponse d'expert à expert — détail technique complet, références précises, nuances jurisprudentielles.",
        "dirigeant":     "Réponse synthétique orientée décision — enjeux, risques, arbitrages. Moins de détail technique, plus de vision stratégique.",
    }.get(niveau, "Réponds avec précision technique adaptée au profil.")

    exp_str = f", {experience} ans d'expérience" if experience else ""
    annee_courante = datetime.utcnow().year

    metier_label = metier.replace('_', ' ') if metier_connu else "professionnel (métier non précisé)"
    return f"""Tu es **Yukpo Pro**, la plateforme IA des professionnels — **disponible à l'international**, tous pays et tous métiers confondus. Tu assistes {nom or 'ce professionnel'}{(' — ' + metier_label) if metier_connu else ''}{f' dans le secteur {secteur}' if secteur else ''}{exp_str}.

═══════════════════════════════════════════════════
  IDENTITÉ YUKPO PRO (à utiliser quand on te demande « c'est quoi Yukpo Pro ? »)
═══════════════════════════════════════════════════
Yukpo Pro est une plateforme IA professionnelle **internationale** qui accompagne les professionnels dans leur travail quotidien : analyse de documents, génération de rapports/contrats/slides/CV, traduction, gestion de réunions, agents spécialisés métier, études et enquêtes.
▸ Elle **n'est pas limitée** à une zone géographique ni à une liste fixe de métiers.
▸ Elle s'adapte dynamiquement au pays ET au métier renseignés dans le profil utilisateur.
▸ Quand l'utilisateur demande une présentation, **personnalise la réponse avec son profil** (ci-dessous) : cite son métier, son pays, son secteur. Si le profil est vide, reste générique et invite l'utilisateur à le compléter.

═══════════════════════════════════════════════════
  CONTEXTE UTILISATEUR — LOCALISATION
═══════════════════════════════════════════════════
▸ Pays         : {pays_nom}{f' ({pays_code})' if pays_connu else ''}
▸ Zone économique : {zone_eco}
▸ Devise       : {devise}
▸ Banque centrale : {banque_centrale}
▸ Métier       : {metier_label.title() if metier_connu else 'Non renseigné'}
▸ Secteur      : {secteur or 'Non spécifié'}
▸ Niveau       : {niveau}
▸ Année de référence : {annee_courante} (utilise les taux et textes applicables à cette année ; marque `[À vérifier — version officielle en vigueur]` en cas de doute sur la mise à jour)
{f'▸ Spécificités  : {specificites}' if specificites else ''}

═══════════════════════════════════════════════════
  CADRE JURIDIQUE ET RÉGLEMENTAIRE APPLICABLE
═══════════════════════════════════════════════════
▸ Fiscal       : {cadre['fiscal']}
▸ Travail      : {cadre['travail']}
▸ Commercial   : {cadre['commercial']}
▸ Comptable    : {cadre['comptable']}
▸ Assurance    : {cadre['assurance']}
{f"▸ Civil        : {cadre['civil']}" if cadre.get('civil') else ''}
{f"▸ Pénal        : {cadre['penal']}" if cadre.get('penal') else ''}

DOMAINES JURIDIQUES PRIORITAIRES POUR CE PROFIL ({metier.upper()}) :
   - {corpus_str}

═══════════════════════════════════════════════════
  RÈGLES ANTI-HALLUCINATION — PRIORITÉ ABSOLUE
═══════════════════════════════════════════════════

**RÈGLE 1 — SOURCE UNIQUE = TA MÉMOIRE DE FORMATION :**
→ Tu réponds EXCLUSIVEMENT depuis ta connaissance des textes juridiques, fiscaux, comptables, normatifs officiels. Pas de RAG, pas de web : uniquement ta mémoire — qui est étendue et mondiale.
→ Tu maîtrises les cadres internationaux (IFRS, ISO, OIT, OCDE, GDPR, Bâle, conventions internationales) ainsi que les cadres régionaux et nationaux — OHADA, SYSCOHADA, CIMA, CEMAC/UEMOA pour l'Afrique francophone ; common law pour l'Afrique anglophone ; droit continental pour l'Europe ; US GAAP / IRC pour l'Amérique du Nord ; droit chinois, japonais, indien, brésilien, russe, etc. **Adapte-toi systématiquement au pays réel de l'utilisateur**.
→ NE PAS inventer d'article, de taux, de barème que tu ne connais pas — dis-le clairement si tu n'es pas sûr.
→ Marque `[À vérifier — version officielle en vigueur]` pour tout article/taux dont tu n'es pas certain à 100 %.
→ Cite l'article précis et son texte tel que tu le connais — même avec la réserve, c'est utile.
→ Précise toujours le texte de référence : "selon le [Code/Loi] {pays_nom} (à confirmer sur la version en vigueur)".
→ JAMAIS de réponse vague type "selon la loi" sans citer l'article précis ou au minimum le chapitre.

**RÈGLE 2 — PRÉCISION CONTEXTUELLE ABSOLUE :**
→ Toute réponse juridique, fiscale, comptable ou RH doit être contextualisée à {pays_nom}.
→ N'utilise JAMAIS les taux/règles d'un autre pays pour répondre — même si tu ne connais pas tous les détails de {pays_nom}, dis-le clairement et donne ce que tu sais.
→ Si tu ne connais pas le droit local précis : dis "je ne suis pas certain du droit {pays_nom} sur ce point — voici ce que je sais + conseillez de vérifier avec un professionnel local".

**RÈGLE 3 — COMPTABILITÉ (SYSCOHADA / IFRS / normes nationales) :**
→ Les réponses comptables DOIVENT référencer le plan comptable applicable : {cadre['comptable']}
→ Cite les numéros de comptes SYSCOHADA exacts (ex : "Compte 601 — Achats de marchandises")
→ Indique les journaux concernés (Achats, Ventes, Trésorerie, OD)
→ Précise les règles d'évaluation/amortissement applicables à {pays_nom}
→ Si SYSCOHADA ne s'applique pas ({pays_nom}) : utilise les normes indiquées ci-dessus.

**RÈGLE 4 — FISCALITÉ (CGI / TVA / IS) :**
→ Toute réponse fiscale doit préciser : le taux exact en vigueur à {pays_nom}, la base imposable, les exonérations éventuelles.
→ Cite l'article du CGI {pays_nom} concerné si tu le connais, avec `[À vérifier — version officielle en vigueur]` si tu n'es pas certain de la version à jour.
→ Les taux et seuils : utilise ceux de {pays_nom} tels que définis dans {cadre['fiscal']}.
→ JAMAIS mélanger des taux d'un autre pays.

**RÈGLE 5 — DROIT DU TRAVAIL :**
→ Applique EXCLUSIVEMENT le {cadre['travail']}.
→ Les indemnités, préavis, congés payés doivent être calculés selon les barèmes de {pays_nom}.
→ Si la convention collective sectorielle s'applique, la mentionner.

**RÈGLE 6 — MONTANTS ET DEVISES :**
→ Si la devise du pays utilisateur est connue ({devise}), exprime les montants dans cette devise sauf demande explicite de conversion.
→ Si la devise n'est pas renseignée, demande à l'utilisateur dans quelle devise il souhaite des exemples, ou utilise une devise neutre (USD/EUR) en le signalant.

**RÈGLE 7 — COUVERTURE MONDIALE HOMOGÈNE :**
→ Yukpo Pro sert des professionnels partout dans le monde — Afrique, Europe, Amériques, Asie, Moyen-Orient, Océanie. Tu dois répondre avec la même rigueur technique pour **tout** pays.
→ Ne dis JAMAIS « je ne connais pas ce pays » ni « je ne suis pas spécialiste de cette juridiction ». Tu as une connaissance étendue des systèmes juridiques et fiscaux mondiaux — utilise-la.
→ Si le pays n'est pas renseigné dans le profil : demande-le avant de donner des taux ou articles précis, sauf si la question porte sur des normes internationales (IFRS, ISO, OIT, OCDE, GDPR, Bâle…).
→ Ancre systématiquement chaque réponse dans le contexte de l'utilisateur : son pays ({pays_nom}), sa zone économique ({zone_eco}), sa devise ({devise}), son métier ({metier_label}), son secteur ({secteur or 'non spécifié'}). Les exemples, montants, cas pratiques doivent être tirés de ce contexte — pas d'un autre pays.

═══════════════════════════════════════════════════
  COMPORTEMENT ET STYLE
═══════════════════════════════════════════════════
▸ Ton niveau d'expertise : {ton_niveau}
▸ Langue de réponse      : RÉPONDS TOUJOURS dans la même langue que la question de l'utilisateur (français, anglais, espagnol, portugais, arabe, allemand, etc.). Détecte la langue du message courant et adapte ta réponse — même si les messages précédents étaient dans une autre langue. Langue par défaut si ambiguë : {"anglais" if langue == "en" else "français"} professionnel.
▸ Exemples               : toujours tirés du contexte réel de {pays_nom}
▸ Style                  : direct et factuel — pas de préambule vide ("Bien sûr !", "Je serais ravi de...")

**FORMATAGE OBLIGATOIRE :**
- **Gras** pour les articles de loi, montants, termes clés
- Listes à puces pour 3+ éléments
- Titres `##` ou `###` pour les réponses longues
- `` `code` `` pour les numéros d'articles, formules, comptes comptables
- Tableaux markdown pour les données comparatives (taux, barèmes, seuils)

═══════════════════════════════════════════════════
  CAPACITÉS DE GÉNÉRATION (NE JAMAIS REFUSER)
═══════════════════════════════════════════════════
Yukpo génère directement : contrats (bail, travail, prestation), lettres, attestations, rapports (financier, RH, audit), présentations PowerPoint, CV, traductions DOCX.
JAMAIS "je ne peux pas" pour un document — le backend génère automatiquement.
Si un lien `/api/v1/...` est dans le résultat : le citer tel quel comme lien de téléchargement.

**FICHIERS JOINTS :**
Le contenu des fichiers (Excel, CSV, Word, PDF) est extrait et fourni dans [Données des fichiers joints].
Analyser directement ce contenu — JAMAIS prétendre ne pas avoir accès au fichier.

**AGENTS SPÉCIALISÉS (activés automatiquement selon la demande) :**
Yukpo Pro embarque un catalogue évolutif d'agents experts — RH, comptable, fiscal, financier, juridique, commercial, ingénierie, microfinance, ONG/bailleurs, douane, CV/emploi, etc. — et **n'est PAS limité** à cette liste : si la question relève d'un autre métier (santé, éducation, logistique, data, etc.), tu réponds directement avec l'expertise appropriée. Ne JAMAIS dire « Yukpo Pro ne couvre pas mon métier ».

═══════════════════════════════════════════════════
  MODULES DE L'APPLICATION — GUIDE D'ORIENTATION
═══════════════════════════════════════════════════
▸ **Chat Yukpo Pro**      : vous êtes ici — assistant IA conversationnel polyvalent
▸ **Yukpo Studio**        : `/generateurs` — génère rapports, contrats, slides, business plans en Word/PowerPoint
▸ **Réunions**            : `/reunions` — gestion réunions, génération PV automatique, rapports de réunion
▸ **Traduction Documents**: `/traduction` — traduction de documents dans plusieurs langues
▸ **Traduction Live**     : `/translate-live` — interprétation simultanée en temps réel (microphone)
▸ **Offres d'emploi**     : `/emploi` — recherche d'emploi, CV, lettres de motivation
▸ **Marchés Publics**     : `/marches` — appels d'offres, DAO, suivi marchés publics
▸ **Enquêtes**            : `/enquetes` — création de sondages et questionnaires professionnels
▸ **Mes Documents**       : `/mes-documents` — retrouver et télécharger tous les documents générés
▸ **Dashboard**           : `/dashboard` — statistiques d'utilisation et progression

RÈGLE ORIENTATION : Quand l'utilisateur pose une question sur une fonctionnalité spécifique ou que son besoin correspond à un module, mentionnez le module par son nom dans votre réponse. Le système ajoutera automatiquement un bouton d'accès rapide.
""".strip()


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/chat", summary="Conversation avec Yukpo Copilote")
async def copilote_chat(
    req: CopiloteChatRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Point d'entrée conversationnel principal.
    Le copilote répond directement ou route vers l'agent spécialisé si besoin.
    Maintient la mémoire de session pour une conversation naturelle et continue.
    """
    from modules.pro.service_profil import get_or_create, incrementer_stat
    from core.ia_client import ModeIA, ia_client

    profil, _ = await get_or_create(current_user.user_id, db)
    session = _get_session(current_user.user_id)
    # ⚠️ Pas de fallback "CM" ici : Yukpo Pro est international. Si le profil
    # n'a pas encore de pays, on laisse vide pour que le LLM ne suppose PAS
    # un pays par défaut (évite les réponses contextualisées à tort au Cameroun).
    pays = req.pays or getattr(profil, "pays", "") or ""

    agent_utilise = None
    resultat_agent = None
    # La détection unifiée (mots-clés + LLM) est lancée après l'extraction des fichiers

    # ── Étape 0 : Extraction du contenu des fichiers joints ────────────────────
    contenu_fichiers = ""
    images_b64_chat: list[str] = []
    if req.fichiers:
        contenu_fichiers = _extraire_texte_fichiers(req.fichiers)
        images_b64_chat  = _extraire_images_fichiers(req.fichiers)

    # ── Étape 0b : Orchestration LLM — classification unifiée ───────────────
    # Un seul appel gpt-4o-mini remplace les 3 détections par mots-clés + la
    # détection d'agent. Fallback automatique vers les mots-clés si LLM indispo.
    orchestration = await _orchestrer_llm(
        message=req.message,
        profil=profil,
        ia_client=ia_client,
        a_fichiers=bool(req.fichiers),
        contenu_fichiers=contenu_fichiers,
    )
    _intention      = orchestration["intention"]
    _sous_type      = orchestration.get("sous_type") or ""
    _type_doc_o     = orchestration.get("type_doc") or ""
    _agent_orch     = orchestration.get("agent")
    _format_orch    = (orchestration.get("format") or "docx").lower()
    _mode_orch      = (orchestration.get("mode") or "standard").lower()
    _style_orch     = orchestration.get("style_specifique") or ""
    _lc_orch        = orchestration.get("langue_cible") or "en"
    _fc_orch        = orchestration.get("format_cible") or _format_orch
    _modules_llm    = orchestration.get("modules_suggeres") or []  # suggestions sémantiques LLM
    # Validation
    if _format_orch not in {"docx", "pdf", "pptx", "xlsx", "markdown"}:
        _format_orch = "docx"
    if _mode_orch not in {"flash", "standard", "complet", "expert"}:
        _mode_orch = "standard"

    # ── Étape 0b-ter : Détection plainte "données simulées" ─────────────────
    # Si l'utilisateur conteste un document précédent ("tu as inventé",
    # "données simulées", "vraies données"...), on relance la génération du
    # MÊME type de document avec recherche web forcée, plutôt que de tomber
    # dans une réponse Q/R générique.
    _PLAINTE_DONNEES_PATTERNS = (
        "tu as simul", "vous avez simul", "tu as invent", "vous avez invent",
        "données simul", "donnees simul", "données réelles", "donnees reelles",
        "vraies données", "vraies donnees", "données fictives", "donnees fictives",
        "placeholders", "place holder", "tu fais semblant",
        "n'a pas utilisé les données", "n a pas utilise les donnees",
        "rapport vide", "document vide", "contenu vide", "rempli de x",
        "rempli de placeholders", "tu n'as pas cherché", "tu n as pas cherche",
        "données réelles", "regenere", "régénère", "recommence",
        "refais avec", "refais le",
    )
    _msg_low_plainte = (req.message or "").lower()
    _est_plainte_donnees = any(p in _msg_low_plainte for p in _PLAINTE_DONNEES_PATTERNS)
    _force_web_search = False
    if _est_plainte_donnees:
        # Retrouver le dernier document généré dans la session (≤ 8 messages)
        _last_doc_meta = None
        for _m in reversed(session.get("messages", [])[-8:]):
            if (_m.get("role") == "assistant"
                    and (_m.get("meta") or {}).get("agent_utilise") == "generateur"):
                _last_doc_meta = _m.get("meta") or {}
                break
        if _last_doc_meta:
            _intention = "generateur"
            _force_web_search = True
            # On garde _type_doc_o si déjà connu, sinon on essaie de le déduire
            if not _type_doc_o:
                _type_doc_o = _last_doc_meta.get("type_doc") or "rapport_analyse"
            _sous_type = _sous_type or "rapport"
            logger.info(
                f"[Copilote] Plainte 'données simulées' détectée → "
                f"régénération forcée avec web search (type={_type_doc_o})"
            )

    # ── Étape 0b-bis : Mode édition document existant ──────────────────────
    # Si l'utilisateur a ouvert un document depuis "Mes Documents" et demande
    # une amélioration dans le chat, on bypass le classifier et on force la
    # génération en mode édition avec le type et le contenu d'origine.
    # `_effective_doc_ref` peut venir du frontend OU d'une auto-détection
    # de l'intention « modifier le rapport précédent » dans la session.
    _effective_doc_ref = req.document_ref

    # Auto-détection : l'utilisateur veut MODIFIER le dernier doc généré
    # On vérifie même si l'orchestrateur a classé en 'conversation' — un
    # message court type « complète la section X » sera mal classé sinon.
    if _effective_doc_ref is None and _intention in ("generateur", "conversation", "agent_metier"):
        _MODIFICATION_PATTERNS = (
            "modifie", "modifier", "modification",
            "ajoute", "ajouter", "rajoute", "rajouter",
            "complete", "complète", "completer", "compléter",
            "enleve", "enlève", "enlever", "supprime", "supprimer",
            "remplace", "remplacer",
            "change", "changer",
            "ameliore", "améliore", "ameliorer", "améliorer",
            "reformule", "reformuler",
            "developpe", "développe", "developper", "développer",
            "approfondi", "approfondir",
            "ce rapport", "ce document", "ce fichier", "celui-ci", "celui ci",
            "le rapport precedent", "le rapport précédent",
            "le doc precedent", "le doc précédent",
            "le document genere", "le document généré",
            "tu viens de generer", "tu viens de générer",
            "tu as genere", "tu as généré",
            "que tu as fait", "que tu viens de faire",
            "dans le rapport", "dans le document",
            "section ", "chapitre ", "paragraphe ",
            "page ", "tableau ",
            "rendre plus", "rends-le plus", "rends le plus",
        )
        _msg_low_modif = (req.message or "").lower()
        _est_modification = any(p in _msg_low_modif for p in _MODIFICATION_PATTERNS)
        if _est_modification:
            # Retrouver le dernier document généré dans la session
            _last_gen_meta = None
            for _m in reversed(session.get("messages", [])[-12:]):
                if (_m.get("role") == "assistant"
                        and (_m.get("meta") or {}).get("agent_utilise") == "generateur"
                        and (_m.get("meta") or {}).get("titre")):
                    _last_gen_meta = _m.get("meta") or {}
                    break
            if _last_gen_meta:
                from types import SimpleNamespace as _SNS
                _effective_doc_ref = _SNS(
                    id=_last_gen_meta.get("doc_id") or 0,
                    titre=_last_gen_meta.get("titre", "Document précédent"),
                    type_doc=_last_gen_meta.get("type_doc") or "rapport_analyse",
                    contenu_genere=_last_gen_meta.get("apercu", "") or "",
                    meta=_last_gen_meta,
                )
                # Force l'intention generateur si l'orchestrateur s'est trompé
                _intention = "generateur"
                logger.info(
                    f"[Copilote] Modification détectée → mode édition activé "
                    f"sur dernier doc '{(_last_gen_meta.get('titre') or '')[:50]}' "
                    f"(type={_last_gen_meta.get('type_doc')})"
                )

    if _effective_doc_ref is not None:
        _intention  = "generateur"
        _type_doc_o = _effective_doc_ref.type_doc or _type_doc_o
        if _type_doc_o.startswith("slides") or _type_doc_o in (
            "bilan_activite", "rapport_direction", "proposition_client",
            "pitch_projet", "formation", "analyse_marche",
        ):
            _sous_type = "slides"
            _format_orch = "pptx"
        elif _type_doc_o in ("cv", "lettre_emploi", "lettre_motivation"):
            _sous_type = "cv"
        elif _type_doc_o.startswith("tableur"):
            _sous_type = "tableur"
            _format_orch = "xlsx"
        else:
            _sous_type = _sous_type or "rapport"

    # ── Étape 0c : Traduction ─────────────────────────────────────────────────
    texte_a_traduire_chat = contenu_fichiers
    if _intention == "traduction" and not texte_a_traduire_chat:
        texte_a_traduire_chat = _extraire_texte_a_traduire(req.message)
    if _intention == "traduction" and texte_a_traduire_chat:
        from core.ia_client import ModeIA, ia_client
        from modules.pro.service_profil import get_or_create, incrementer_stat

        metier = getattr(profil, "metier", "") or ""
        lc = _lc_orch
        langue_noms = {"fr": "français", "en": "anglais", "es": "espagnol",
                       "pt": "portugais", "ar": "arabe", "zh": "mandarin"}
        dst = langue_noms.get(lc, lc)

        prompt_sys_trad = (
            f"Tu es un traducteur professionnel expert en terminologie d'affaires africaine. "
            f"Tu traduis vers le {dst} avec précision absolue. "
            f"Tu respectes la terminologie du secteur {metier or 'professionnel'}, "
            f"en conservant les termes OHADA, SYSCOHADA, CIMA, COBAC, UEMOA, CEMAC, FCFA. "
            f"Tu conserves la mise en forme (titres, listes, tableaux). "
            f"Tu réponds UNIQUEMENT avec le texte traduit, sans préambule."
        )
        prompt_trad = (
            f"Traduis le texte suivant vers le {dst} :\n\n"
            f"---\n{texte_a_traduire_chat[:35000]}\n---"
        )
        try:
            reponse_ia = await ia_client.appeler(
                prompt=prompt_trad,
                mode=ModeIA.REDACTION,
                systeme=prompt_sys_trad,
                max_tokens_override=8192,
                utiliser_cache=False,
            )
            texte_traduit = reponse_ia.contenu if hasattr(reponse_ia, "contenu") else str(reponse_ia)
            await incrementer_stat(current_user.user_id, "nb_traductions", db, xp_gain=2)

            # Générer le fichier traduit en préservant la mise en forme si DOCX/PPTX
            chemin_docx = None
            try:
                import base64
                from datetime import datetime as _dt
                from api.routes_pro_generateurs import (
                    _traduire_docx_avec_structure,
                    _traduire_pptx_avec_structure,
                    _construire_docx_depuis_texte_traduit,
                    _DATA_DIR,
                )
                reports_dir = _DATA_DIR / "pro_reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")

                nom_fichier_src = (req.fichiers[0].nom if req.fichiers else "traduction")
                nom_base = Path(nom_fichier_src).stem
                nom_ext  = Path(nom_fichier_src).suffix.lower()
                metier   = getattr(profil, "metier", "") or ""

                # Décoder les bytes du fichier source si disponible
                fichier_bytes = None
                if req.fichiers and req.fichiers[0].contenu:
                    raw = req.fichiers[0].contenu
                    if "base64," in raw:
                        raw = raw.split("base64,", 1)[1]
                    try:
                        fichier_bytes = base64.b64decode(raw)
                    except Exception:
                        fichier_bytes = None

                if fichier_bytes and nom_ext in (".docx", ".doc"):
                    # Préservation complète de la mise en forme DOCX
                    sortie_bytes = await _traduire_docx_avec_structure(
                        contenu=fichier_bytes,
                        langue_source="fr",
                        langue_cible=lc,
                        metier=metier,
                    )
                    chemin_out = reports_dir / f"trad_{nom_base}_{ts}.docx"
                    chemin_out.write_bytes(sortie_bytes)
                    chemin_docx = str(chemin_out)

                elif fichier_bytes and nom_ext == ".pptx":
                    # Préservation complète de la mise en forme PPTX
                    sortie_bytes = await _traduire_pptx_avec_structure(
                        contenu=fichier_bytes,
                        langue_source="fr",
                        langue_cible=lc,
                        metier=metier,
                    )
                    chemin_out = reports_dir / f"trad_{nom_base}_{ts}.pptx"
                    chemin_out.write_bytes(sortie_bytes)
                    chemin_docx = str(chemin_out)

                else:
                    # Autres formats → DOCX depuis le texte traduit
                    sortie_bytes = _construire_docx_depuis_texte_traduit(
                        texte=texte_traduit,
                        titre=f"Traduction {dst} — {nom_base}",
                        src="source",
                        dst=dst,
                    )
                    chemin_out = reports_dir / f"trad_{nom_base}_{ts}.docx"
                    chemin_out.write_bytes(sortie_bytes)
                    chemin_docx = str(chemin_out)

            except Exception as e_doc:
                logger.warning(f"[Copilote-Trad] Fichier traduit échoué: {e_doc}")

            reponse_finale = f"**Traduction vers le {dst} effectuée.**\n\n{texte_traduit}"
            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", reponse_finale)

            return {
                "session_id": session["session_id"],
                "reponse": reponse_finale,
                "agent_utilise": "traducteur",
                "resultat_agent": None,
                "nb_messages_session": len(session["messages"]),
                "profil_metier": metier,
                "fichiers_generes": [chemin_docx] if chemin_docx else None,
            }
        except Exception as e:
            logger.error(f"[Copilote-Trad] {e}")
            # Fallback : continuer avec le copilote normal

    # ── Étape 0c.5 : Conversion de format fichier ─────────────────────────────
    if _intention == "conversion" and req.fichiers:
        try:
            import base64 as _b64
            from pathlib import Path as _Path
            from datetime import datetime as _dt
            from api.routes_pro_generateurs import (
                CONVERSIONS_SUPPORTEES,
                _DATA_DIR as _GEN_DATA_DIR,
            )

            fichier_src = req.fichiers[0]
            raw_b64 = fichier_src.contenu
            if "base64," in raw_b64:
                raw_b64 = raw_b64.split("base64,", 1)[1]
            fichier_bytes = _b64.b64decode(raw_b64)

            nom_src = fichier_src.nom
            ext_src = _Path(nom_src).suffix.lower()  # avec le point, ex: ".pdf"
            ext_src_bare = ext_src.lstrip(".")        # sans point, ex: "pdf"
            format_cible = _fc_orch                   # ex: "docx"

            # Vérifier que la conversion est supportée (CONVERSIONS_SUPPORTEES: .ext → {.ext: desc})
            cibles_dict = CONVERSIONS_SUPPORTEES.get(ext_src, {})
            ext_cible_dot = f".{format_cible}"
            if ext_cible_dot not in cibles_dict:
                # Prendre la première cible disponible
                format_cible = list(cibles_dict.keys())[0].lstrip(".") if cibles_dict else "docx"

            # Appeler la logique de conversion directement
            from api.routes_pro_generateurs import (
                _convertir_vers_docx, _convertir_vers_txt,
                _convertir_vers_csv, _convertir_vers_xlsx,
            )

            if format_cible == "docx":
                res_bytes = await _convertir_vers_docx(fichier_bytes, nom_src, ext_src)
                ext_out = "docx"
            elif format_cible == "csv":
                res_bytes = await _convertir_vers_csv(fichier_bytes, ext_src)
                ext_out = "csv"
            elif format_cible == "xlsx":
                res_bytes = await _convertir_vers_xlsx(fichier_bytes, ext_src)
                ext_out = "xlsx"
            elif format_cible == "txt":
                res_bytes = await _convertir_vers_txt(fichier_bytes, nom_src, ext_src)
                ext_out = "txt"
            elif format_cible == "pdf":
                try:
                    import subprocess as _sp
                    from api.routes_pro_generateurs import _DATA_DIR as _GDIR
                    docx_bytes = await _convertir_vers_docx(fichier_bytes, nom_src, ext_src)
                    _GDIR.mkdir(parents=True, exist_ok=True)
                    tmp_d = _GDIR / "tmp_conv_chat.docx"
                    tmp_d.write_bytes(docx_bytes)
                    _sp.run(["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(_GDIR), str(tmp_d)],
                            check=True, timeout=30, capture_output=True)
                    pdf_p = _GDIR / "tmp_conv_chat.pdf"
                    res_bytes = pdf_p.read_bytes() if pdf_p.exists() else docx_bytes
                    for _p in [pdf_p, tmp_d]:
                        try: _p.unlink()
                        except: pass
                    ext_out = "pdf" if pdf_p.exists() else "docx"
                except Exception:
                    res_bytes = await _convertir_vers_docx(fichier_bytes, nom_src, ext_src)
                    ext_out = "docx"
            else:
                res_bytes = await _convertir_vers_docx(fichier_bytes, nom_src, ext_src)
                ext_out = "docx"

            # Sauvegarder le fichier converti
            reports_dir = _GEN_DATA_DIR / "pro_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
            nom_base = _Path(nom_src).stem
            chemin_out = reports_dir / f"conv_{nom_base}_{ts}.{ext_out}"
            chemin_out.write_bytes(res_bytes)

            formats_lisibles = {
                "docx": "Word (DOCX)", "pdf": "PDF", "pptx": "PowerPoint",
                "xlsx": "Excel (XLSX)", "csv": "CSV", "txt": "Texte",
            }
            label_in  = ext_src_bare.upper()
            label_out = formats_lisibles.get(ext_out, ext_out.upper())
            reponse_conv = (
                f"**Conversion {label_in} → {label_out} effectuée avec succès.**\n\n"
                f"Votre fichier `{nom_src}` a été converti en **{label_out}**.\n"
                f"Il est prêt à télécharger."
            )

            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", reponse_conv, {"agent_utilise": "convertisseur"})
            await _sauvegarder_doc_db(
                db=db, user_id=current_user.user_id,
                titre=f"Conversion {label_in}→{label_out} — {nom_base}",
                type_doc="conversion",
                fichier=str(chemin_out),
                contenu_genere="",
                session_id=session["session_id"],
                meta={"source": "chat", "format_source": ext_src, "format_cible": ext_out},
            )
            return {
                "session_id":          session["session_id"],
                "reponse":             reponse_conv,
                "agent_utilise":       "convertisseur",
                "resultat_agent":      None,
                "nb_messages_session": len(session["messages"]),
                "profil_metier":       getattr(profil, "metier", None),
                "fichiers_generes":    [str(chemin_out)],
            }
        except Exception as e_conv:
            logger.warning(f"[Copilote-Conv] Conversion échouée: {e_conv}")
            # Fallback : répondre en texte

    # ── Étape 0c-bis : Designer Pro (visuels multi-page) ─────────────────────
    if _intention == "designer":
        try:
            from api.routes_bureau_infographie_pro import (
                generer_auto as _designer_generer_auto,
                modifier_projet as _designer_modifier,
                DemandeAutoPro, DemandeModifierProjet, ProfilDesigner,
            )
            from modules.pro.service_profil import get_or_create, incrementer_stat

            # Mode édition : si un document_ref pointe vers un projet designer
            ref_projet_id = None
            if req.document_ref is not None:
                meta_ref = getattr(req.document_ref, "meta", None) or {}
                if isinstance(meta_ref, dict) and meta_ref.get("projet_id"):
                    ref_projet_id = meta_ref["projet_id"]
                elif (req.document_ref.type_doc or "").startswith("designerpro"):
                    ref_projet_id = meta_ref.get("projet_id") if isinstance(meta_ref, dict) else None

            metier_p = getattr(profil, "metier", None)
            secteur_p = getattr(profil, "secteur", None) or getattr(profil, "domaine", None)
            pays_p = (getattr(profil, "pays", None) or "CM")[:2].upper()
            profil_designer = ProfilDesigner(
                metier=metier_p,
                secteur=secteur_p,
                nom_organisation=getattr(profil, "organisation", None) or getattr(profil, "entreprise", None),
            )

            if ref_projet_id:
                dem = DemandeModifierProjet(
                    projet_id=ref_projet_id,
                    instructions=req.message,
                    pays=pays_p,
                )
                resultat = await asyncio.wait_for(
                    _designer_modifier(dem, current_user), timeout=320.0
                )
            else:
                dem = DemandeAutoPro(
                    brief=req.message,
                    pays=pays_p,
                    langue=(_lc_orch or "fr"),
                    profil=profil_designer,
                )
                resultat = await asyncio.wait_for(
                    _designer_generer_auto(dem, current_user), timeout=320.0
                )

            res_d = resultat if isinstance(resultat, dict) else {}
            projet_info = res_d.get("projet") or {}
            cle_detectee = res_d.get("cle_projet_detectee") or projet_info.get("cle_projet") or "designer"
            pdf_id = res_d.get("pdf_id") or res_d.get("pdf_cmyk_id")
            from api.routes_bureau_infographie_pro import _DATA_DIR as _DESIGN_DATA_DIR
            chemin_pdf = str(_DESIGN_DATA_DIR / pdf_id) if pdf_id else None
            projet_id = res_d.get("projet_json_id")
            n_pages = projet_info.get("nombre_pages") or len(res_d.get("pages_png_ids", []) or [])

            reponse_design = (
                f"🎨 **Visuel généré — {cle_detectee} ({n_pages} page{'s' if n_pages > 1 else ''}).**\n\n"
                f"Le PDF prêt à imprimer est disponible dans **Mes Documents**. "
                f"Pour modifier (changer un texte, remplacer une photo, ajuster les couleurs…), "
                f"décrivez-moi simplement les changements souhaités."
            )

            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", reponse_design,
                             {"agent_utilise": "designer", "projet_id": projet_id, "cle_projet": cle_detectee})
            await incrementer_stat(current_user.user_id, "nb_documents_generes", db, xp_gain=4)

            await _sauvegarder_doc_db(
                db=db, user_id=current_user.user_id,
                titre=f"Visuel {cle_detectee}"[:100],
                type_doc=f"designerpro_{cle_detectee}",
                fichier=chemin_pdf,
                contenu_genere="",
                session_id=session["session_id"],
                meta={"source": "chat", "format": "pdf", "projet_id": projet_id,
                      "cle_projet": cle_detectee, "nb_pages": n_pages},
            )

            return {
                "session_id":           session["session_id"],
                "reponse":              reponse_design,
                "agent_utilise":        "designer",
                "resultat_agent":       {"projet_id": projet_id, "cle_projet": cle_detectee, "nb_pages": n_pages},
                "nb_messages_session":  len(session["messages"]),
                "profil_metier":        getattr(profil, "metier", None),
                "fichiers_generes":     [chemin_pdf] if chemin_pdf else None,
                "navigation_suggestions": [
                    {"label": "Designer Pro", "route": "/secretariat/infographie",
                     "icon": "image", "description": "Affiner le visuel ou changer le format"},
                ],
            }
        except asyncio.TimeoutError:
            logger.warning("[Copilote-Designer] Timeout génération visuel")
            _msg_d = ("⚠️ La génération du visuel a pris trop de temps. "
                      "Reprenez avec un brief plus court ou utilisez **Designer Pro** directement.")
            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", _msg_d, {"agent_utilise": "designer"})
            return {
                "session_id": session["session_id"], "reponse": _msg_d,
                "agent_utilise": "designer", "resultat_agent": None,
                "nb_messages_session": len(session["messages"]),
                "profil_metier": getattr(profil, "metier", None),
                "fichiers_generes": None,
                "navigation_suggestions": [{"label": "Designer Pro", "route": "/secretariat/infographie",
                                            "icon": "image", "description": "Ouvrir le module"}],
            }
        except HTTPException as he:
            logger.warning(f"[Copilote-Designer] {he.status_code}: {he.detail}")
            _msg_d = f"⚠️ {he.detail}"
            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", _msg_d, {"agent_utilise": "designer"})
            return {
                "session_id": session["session_id"], "reponse": _msg_d,
                "agent_utilise": "designer", "resultat_agent": None,
                "nb_messages_session": len(session["messages"]),
                "profil_metier": getattr(profil, "metier", None),
                "fichiers_generes": None, "navigation_suggestions": [],
            }
        except Exception as e_d:
            logger.warning(f"[Copilote-Designer] Génération échouée: {e_d}")
            # Fallback : tomber sur generateur classique (rapport/contrat)
            _intention = "generateur"
            _sous_type = "rapport"

    # ── Étape 0d : Génération de document depuis le chat ─────────────────────
    # Déclenché par l'orchestrateur (LLM) — y compris quand des fichiers sont
    # joints et servent de contexte pour le document généré.
    if _intention == "generateur" and _sous_type != "cv":
        try:
            # Construire le contexte : historique conversation + fichiers joints
            historique_gen = _construire_historique_claude(session["messages"], budget_tokens=1500)
            hist_conv = ""
            if historique_gen:
                hist_conv = "\n".join(
                    f"{'Utilisateur' if m['role'] == 'user' else 'Yukpo'}: {m['content']}"
                    for m in historique_gen
                )
            contexte_gen_parts = []
            if hist_conv:
                contexte_gen_parts.append(f"[Contexte de la conversation]\n{hist_conv}")
            if contenu_fichiers:
                contexte_gen_parts.append(f"[Données des fichiers joints]\n{contenu_fichiers[:6000]}")

            # Mode édition : on injecte le contenu source et les instructions utilisateur
            _is_edit = _effective_doc_ref is not None
            if _is_edit:
                dref = _effective_doc_ref
                contexte_gen_parts.insert(
                    0,
                    f"[Document source à améliorer — titre: {dref.titre}]\n"
                    f"{(dref.contenu_genere or '')[:8000]}"
                )
                contexte_gen_parts.append(
                    f"[Instructions d'amélioration demandées par l'utilisateur]\n{req.message}"
                )
                # Le "sujet" transmis au builder devient le titre original pour
                # éviter que le prompt d'édition ne se retrouve dans le slug du fichier.
                sujet_gen = dref.titre
            else:
                # Le sujet sert aussi d'en-tête dans le document généré : on
                # génère un vrai titre via LLM plutôt que de recopier la question.
                type_doc_pour_titre = _type_doc_o or _detecter_type_document(req.message)
                sujet_gen = await _generer_titre_document(
                    message=req.message,
                    type_doc=type_doc_pour_titre,
                    contexte="\n\n".join(contexte_gen_parts),
                    ia_client=ia_client,
                )

            contexte_gen = "\n\n".join(contexte_gen_parts) or None
            # Style spécifique demandé par l'utilisateur (cabinet d'avocat, Big4…)
            if _style_orch:
                contexte_gen = (contexte_gen or "") + (
                    f"\n\n[STYLE / RÉFÉRENTIEL DEMANDÉ PAR L'UTILISATEUR]\n"
                    f"{_style_orch}\n"
                    f"Adapte le ton, le vocabulaire, la mise en page et les références à ce style."
                )

            if _sous_type == "slides":
                from modules.pro.slide_builder_pro import SlideBuilderPro
                builder = SlideBuilderPro(profil=profil)
                type_pres_map = {
                    "slides_bilan_activite": "bilan_activite",
                    "slides_rapport_direction": "rapport_direction",
                    "slides_proposition_client": "proposition_client",
                    "slides_pitch_projet": "pitch_projet",
                    "slides_formation": "formation",
                    "bilan_activite": "bilan_activite",
                    "rapport_direction": "rapport_direction",
                    "proposition_client": "proposition_client",
                    "pitch_projet": "pitch_projet",
                    "formation": "formation",
                    "analyse_marche": "analyse_marche",
                }
                type_pres = type_pres_map.get(_type_doc_o, "rapport_direction")
                # Mapping mode rapport → mode slides
                _MODE_SLIDES = {
                    "flash": "executive", "standard": "executive",
                    "complet": "detaille", "expert": "expert",
                }
                mode_slides = _MODE_SLIDES.get(_mode_orch, "executive")
                # Format slides : pptx par défaut, pdf si demandé
                fmt_slides = "pdf" if _format_orch == "pdf" else "pptx"
                res_doc = await asyncio.wait_for(
                    builder.generer(
                        sujet=sujet_gen,
                        type_pres=type_pres,
                        mode=mode_slides,
                        contexte=contexte_gen,
                        format_sortie=fmt_slides,
                    ),
                    timeout=300.0 if mode_slides in ("detaille", "expert") else 240.0,
                )
                ext = fmt_slides.upper()
                type_doc_gen = _type_doc_o or "slides"
            elif _sous_type == "tableur" or _format_orch == "xlsx":
                # Génération Excel via DocumentGenerateur
                from modules.documents.generateur import DocumentGenerateur
                xls_builder = DocumentGenerateur()
                demande_excel = (req.message or sujet_gen).strip()
                ctx_excel = (contexte_gen or "")[:6000]
                res_xls = await asyncio.wait_for(
                    xls_builder._generer_excel_ia(
                        demande=demande_excel, contexte=ctx_excel, theme="blue",
                    ),
                    timeout=240.0,
                )
                # Le DocumentGenerateur retourne un dict avec data_b64 — on persiste en fichier
                if res_xls and res_xls.get("data_b64"):
                    import base64 as _b64
                    from pathlib import Path as _P
                    _xls_dir = _P("data/generated/pro_data")
                    _xls_dir.mkdir(parents=True, exist_ok=True)
                    _filename = res_xls.get("filename") or f"{sujet_gen[:40].replace(' ', '_')}.xlsx"
                    _xls_path = _xls_dir / _filename
                    _xls_path.write_bytes(_b64.b64decode(res_xls["data_b64"]))
                    res_doc = {
                        "chemin_fichier": str(_xls_path),
                        "fichier": str(_xls_path),
                        "nom_fichier": _filename,
                        "apercu": res_xls.get("title", ""),
                    }
                else:
                    res_doc = {"fichier": None, "chemin_fichier": None, "apercu": "Échec génération Excel"}
                ext = "XLSX"
                type_doc_gen = _type_doc_o or "tableur_generique"
            else:
                from modules.pro.report_writer_pro import ReportWriterPro
                writer = ReportWriterPro(profil=profil)
                type_doc_gen = _type_doc_o or _detecter_type_document(req.message)
                # Format rapport : docx par défaut ; pdf si demandé
                fmt_rapport = "pdf" if _format_orch == "pdf" else (
                    "markdown" if _format_orch == "markdown" else "docx"
                )
                res_doc = await asyncio.wait_for(
                    writer.generer(
                        sujet=sujet_gen,
                        type_rapport=type_doc_gen,
                        mode=_mode_orch,
                        contexte=contexte_gen,
                        format_sortie=fmt_rapport,
                        instruction_utilisateur=req.message,
                        forcer_recherche_web=_force_web_search,
                    ),
                    timeout=480.0 if _force_web_search or _mode_orch in ("complet", "expert") else 360.0,
                )
                ext = fmt_rapport.upper()

            chemin_fichier = res_doc.get("fichier") or res_doc.get("chemin_fichier")
            apercu = res_doc.get("apercu", "")
            fichiers_msg = f"\n\n*(Basé sur {len(req.fichiers)} fichier(s) joint(s))*" if contenu_fichiers else ""
            reponse_gen = (
                f"**Document {ext} généré avec succès — prêt à télécharger.**{fichiers_msg}\n\n"
                + (apercu[:1200] if apercu else "Votre document est prêt.")
            )

            _ajouter_message(session, "user", req.message)
            # Meta enrichi pour permettre la modification ultérieure dans le chat
            # (auto-détection de l'intention "modifie ce rapport").
            titre_sauv = (_effective_doc_ref.titre if _is_edit else sujet_gen)[:100]
            meta_msg = {
                "agent_utilise": "generateur",
                "titre": titre_sauv,
                "type_doc": type_doc_gen,
                "format": ext.lower(),
                "sujet": sujet_gen,
                "apercu": (apercu or "")[:6000],
                "chemin_fichier": chemin_fichier,
            }
            _ajouter_message(session, "assistant", reponse_gen, meta_msg)
            await incrementer_stat(current_user.user_id, "nb_documents_generes", db, xp_gain=3)
            meta_sauv = {
                "source": "chat",
                "format": ext.lower(),
                "avec_fichiers": bool(contenu_fichiers),
            }
            if _is_edit:
                meta_sauv["edited_from"] = getattr(_effective_doc_ref, "id", 0) or 0
                meta_sauv["instructions"] = req.message[:500]
            await _sauvegarder_doc_db(
                db=db, user_id=current_user.user_id,
                titre=titre_sauv,
                type_doc=type_doc_gen,
                fichier=chemin_fichier,
                contenu_genere=apercu,
                session_id=session["session_id"],
                meta=meta_sauv,
            )

            return {
                "session_id":           session["session_id"],
                "reponse":              reponse_gen,
                "agent_utilise":        "generateur",
                "resultat_agent":       None,
                "nb_messages_session":  len(session["messages"]),
                "profil_metier":        getattr(profil, "metier", None),
                "fichiers_generes":     [chemin_fichier] if chemin_fichier else None,
                "navigation_suggestions": [],
            }
        except asyncio.TimeoutError:
            logger.warning("[Copilote-Gen] Timeout génération document")
            _msg_err = (
                "⚠️ **La génération du document a pris trop de temps.** Essayez avec une demande plus courte, "
                "ou utilisez **Yukpo Studio** qui offre plus de contrôle sur la génération."
            )
            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", _msg_err, {"agent_utilise": "generateur"})
            return {
                "session_id":           session["session_id"],
                "reponse":              _msg_err,
                "agent_utilise":        "generateur",
                "resultat_agent":       None,
                "nb_messages_session":  len(session["messages"]),
                "profil_metier":        getattr(profil, "metier", None),
                "fichiers_generes":     None,
                "navigation_suggestions": [{"label": "Yukpo Studio", "route": "/generateurs", "icon": "file-text", "description": "Générer des documents avec plus de contrôle"}],
            }
        except Exception as e:
            # Refus volontaire : sources insuffisantes pour rédiger factuellement
            from modules.pro.report_writer_pro import SourcesInsuffisantesError
            if isinstance(e, SourcesInsuffisantesError):
                logger.info(f"[Copilote-Gen] Refus sources insuffisantes: {e.raison}")
                _sources_txt = ""
                if e.sources_essayees:
                    _sources_txt = "\n\n**Sources consultées sans succès :**\n" + "\n".join(
                        f"- {u}" for u in e.sources_essayees[:5]
                    )
                _msg_refus = (
                    f"📚 **Je préfère ne pas générer ce document avec des données inventées.**\n\n"
                    f"{e.raison}\n\n"
                    f"**Pour produire un rapport fiable, merci de me fournir :**\n"
                    f"- les états financiers / comptes audités concernés (PDF, Excel)\n"
                    f"- ou tout document source officiel (rapport annuel, état CIMA, "
                    f"délibération conseil d'administration…)\n"
                    f"- ou des données chiffrées brutes que je puisse exploiter\n\n"
                    f"Sans source vérifiable, je ne peux pas rédiger un rapport "
                    f"professionnel sans risque d'erreur factuelle.{_sources_txt}"
                )
                _ajouter_message(session, "user", req.message)
                _ajouter_message(session, "assistant", _msg_refus, {"agent_utilise": "generateur", "refus_sources": True})
                return {
                    "session_id":           session["session_id"],
                    "reponse":              _msg_refus,
                    "agent_utilise":        "generateur",
                    "resultat_agent":       None,
                    "nb_messages_session":  len(session["messages"]),
                    "profil_metier":        getattr(profil, "metier", None),
                    "fichiers_generes":     None,
                    "navigation_suggestions": [],
                }
            logger.warning(f"[Copilote-Gen] Génération échouée: {e}")
            _msg_err2 = (
                f"⚠️ **Erreur lors de la génération du document.** "
                f"Essayez de reformuler votre demande, ou utilisez **Yukpo Studio** pour plus de contrôle."
            )
            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", _msg_err2, {"agent_utilise": "generateur"})
            return {
                "session_id":           session["session_id"],
                "reponse":              _msg_err2,
                "agent_utilise":        "generateur",
                "resultat_agent":       None,
                "nb_messages_session":  len(session["messages"]),
                "profil_metier":        getattr(profil, "metier", None),
                "fichiers_generes":     None,
                "navigation_suggestions": [{"label": "Yukpo Studio", "route": "/generateurs", "icon": "file-text", "description": "Générer des documents avec plus de contrôle"}],
            }

    # ── Étape 0e : Génération CV / Lettre de motivation ──────────────────────
    if _intention == "generateur" and _sous_type == "cv":
        try:
            from core.ia_client import ModeIA as ModeIAcv, ia_client as ia_cv
            from modules.pro.cv_document_builder import CvDocumentBuilder
            from modules.pro.agents.agent_cv_emploi import (
                _prompt_generer_cv, _prompt_lettre_motivation, _ctx_profil,
            )

            # Déterminer le type précis (cv ou lettre)
            type_doc = "cv" if (_type_doc_o or "").startswith("cv") or _type_doc_o == "cv" else "lettre"
            if "lettre" in (_type_doc_o or "") or "motivation" in req.message.lower():
                type_doc = "lettre"
            format_sortie_cv = _format_orch or "docx"

            # ── Appel IA pour générer le contenu ──────────────────────────
            # Récupérer le CV de référence s'il existe
            cv_ref = getattr(profil, "cv_texte", "") or "" if profil else ""

            if type_doc == "cv":
                prompt_cv = _prompt_generer_cv(
                    params={"texte_offre": req.message},
                    profil=profil,
                    cv_reference=cv_ref,
                )
                rep_cv = await asyncio.wait_for(
                    ia_cv.appeler(prompt=prompt_cv, mode=ModeIAcv.REDACTION, max_tokens_override=4096),
                    timeout=120.0,
                )
                contenu_doc = rep_cv.contenu if hasattr(rep_cv, "contenu") else str(rep_cv)
                nom_base    = "cv_yukpo"
            else:
                prompt_lm = _prompt_lettre_motivation(
                    params={"texte_offre": req.message},
                    profil=profil,
                )
                rep_lm = await asyncio.wait_for(
                    ia_cv.appeler(prompt=prompt_lm, mode=ModeIAcv.REDACTION, max_tokens_override=2048),
                    timeout=120.0,
                )
                contenu_doc = rep_lm.contenu if hasattr(rep_lm, "contenu") else str(rep_lm)
                nom_base    = "lettre_motivation_yukpo"

            # ── Construire le fichier DOCX/PDF ────────────────────────────
            builder_cv = CvDocumentBuilder(profil=profil)

            if type_doc == "cv":
                res_cv = await asyncio.wait_for(
                    builder_cv.generer_cv(contenu_doc, nom_base=nom_base, format_sortie=format_sortie_cv),
                    timeout=60.0,
                )
            else:
                res_cv = await asyncio.wait_for(
                    builder_cv.generer_lettre(contenu_doc, nom_base=nom_base, format_sortie=format_sortie_cv),
                    timeout=60.0,
                )

            chemin_cv = res_cv.get("chemin_fichier")
            label_doc = "CV" if type_doc == "cv" else "Lettre de motivation"
            fmt_label = format_sortie_cv.upper()

            reponse_cv = (
                f"**{label_doc} généré{'e' if type_doc == 'lettre' else ''} "
                f"en {fmt_label} — prêt à télécharger.**\n\n"
                + (contenu_doc[:1500] if format_sortie_cv == "markdown" else contenu_doc[:800])
                + ("\n\n*[Document complet dans le fichier joint]*" if format_sortie_cv != "markdown" else "")
            )

            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", reponse_cv, {"agent_utilise": "cv_emploi"})
            await incrementer_stat(current_user.user_id, "nb_documents_generes", db, xp_gain=3)
            # Sauvegarder dans l'historique documents
            titre_cv = (await _generer_titre_document(
                message=req.message,
                type_doc="lettre_motivation" if type_doc == "lettre" else "cv",
                contexte=contenu_doc[:1500] if isinstance(contenu_doc, str) else "",
                ia_client=ia_cv,
            ))[:100]
            await _sauvegarder_doc_db(
                db=db, user_id=current_user.user_id,
                titre=titre_cv,
                type_doc="lettre_emploi" if type_doc == "lettre" else "cv",
                fichier=chemin_cv,
                contenu_genere=contenu_doc[:2000],
                session_id=session["session_id"],
                meta={"source": "chat", "format": format_sortie_cv},
            )

            return {
                "session_id":           session["session_id"],
                "reponse":              reponse_cv,
                "agent_utilise":        "cv_emploi",
                "resultat_agent":       None,
                "nb_messages_session":  len(session["messages"]),
                "profil_metier":        getattr(profil, "metier", None),
                "fichiers_generes":     [chemin_cv] if chemin_cv else None,
                "navigation_suggestions": [{"label": "Offres d'emploi", "route": "/emploi", "icon": "briefcase", "description": "Trouver des offres et gérer vos candidatures"}],
            }

        except (asyncio.TimeoutError, Exception) as e_cv:
            logger.warning(f"[Copilote-CV] Génération CV échouée: {e_cv}")
            _msg_cv_err = (
                "⚠️ **Erreur lors de la génération du document.** Reformulez votre demande "
                "ou accédez au module **Offres d'emploi** pour générer votre CV avec plus d'options."
            )
            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", _msg_cv_err, {"agent_utilise": "cv_emploi"})
            return {
                "session_id":           session["session_id"],
                "reponse":              _msg_cv_err,
                "agent_utilise":        "cv_emploi",
                "resultat_agent":       None,
                "nb_messages_session":  len(session["messages"]),
                "profil_metier":        getattr(profil, "metier", None),
                "fichiers_generes":     None,
                "navigation_suggestions": [{"label": "Offres d'emploi", "route": "/emploi", "icon": "briefcase", "description": "Générer CV et lettres de motivation"}],
            }

    # ── Étape 0f : RAG en parallèle (contexte réglementaire) ─────────────────
    # L'agent est déjà connu via l'orchestrateur (_agent_orch).
    # On lance juste le RAG si pertinent, pendant que l'agent réfléchit.
    a_fichiers_joints = bool(contenu_fichiers or images_b64_chat)
    contexte_rag  = ""
    # Utiliser l'agent détecté par l'orchestrateur LLM.
    # Si intention != agent_metier mais _agent_orch est non null (signal profil),
    # on l'utilise quand même pour enrichir la réponse copilote.
    agent_detecte = _agent_orch if _intention == "agent_metier" else None

    # Architecture LLM-first : on ne fait plus de RAG corpus documentaire.
    # Le prompt système est hyper-contextualisé (pays, métier, cadre juridique).
    # Le LLM répond depuis sa connaissance de formation, sans injection de documents.
    contexte_rag = ""

    # ── Étape 1 : Appel agent spécialisé si pertinent ─────────────────────────
    # Le DAA peut traiter des fichiers joints (Excel, CSV) — les autres agents non.
    _agent_accepte_fichiers = agent_detecte in ("daa", "data_analyst", "comptable", "daf", "banquier")
    if agent_detecte and (not a_fichiers_joints or _agent_accepte_fichiers):
        try:
            from api.routes_pro_agent import _charger_agent_metier
            import types

            # Créer un profil compatible avec le métier détecté.
            # SimpleNamespace n'a pas to_contexte_agent() → on l'ajoute manuellement.
            _m = agent_detecte
            _p = pays
            _s = getattr(profil, "secteur", "")
            _n = getattr(profil, "nom", "")
            _niv = getattr(profil, "niveau_expertise", "intermediaire")
            profil_override = types.SimpleNamespace(
                metier=_m, pays=_p, secteur=_s, nom=_n, niveau_expertise=_niv,
            )
            profil_override.to_contexte_agent = lambda: (
                f"Profil: {_n or 'Professionnel'} — Métier: {_m} — Pays: {_p} — Niveau: {_niv}"
                + (f" — Secteur: {_s}" if _s else "")
            )
            agent = _charger_agent_metier(profil_override)

            # Enrichir l'instruction avec le contenu des fichiers si présents
            instruction_agent = req.message
            if contenu_fichiers and _agent_accepte_fichiers:
                # Cas particulier : PDF pour AgentDAA → directive d'utiliser l'outil pdf_analyser
                a_pdf = False
                if agent_detecte == "daa" and req.fichiers:
                    a_pdf = any(
                        Path(getattr(f, "nom", "") or getattr(f, "name", "")).suffix.lower() == ".pdf"
                        for f in req.fichiers
                    )

                if a_pdf:
                    instruction_agent = (
                        f"{req.message}\n\n"
                        f"[Contenu du rapport PDF — texte et tableaux extraits]\n{contenu_fichiers[:8000]}\n\n"
                        f"[DIRECTIVE ANALYSE PDF : Utilise l'outil 'pdf_analyser' en passant le texte extrait "
                        f"ci-dessus via le paramètre 'texte_extrait'. Réalise une analyse complète des données, "
                        f"des tableaux et indicateurs présents dans ce rapport.]"
                    )
                else:
                    instruction_agent = (
                        f"{req.message}\n\n"
                        f"[Données des fichiers joints]\n{contenu_fichiers[:6000]}"
                    )

            # Injecter le contexte réglementaire RAG dans l'instruction de l'agent.
            # Sans cela, l'agent répond depuis sa seule mémoire d'entraînement
            # sans accès aux textes CIMA/OHADA extraits du corpus.
            if contexte_rag and contexte_rag.strip():
                instruction_agent = (
                    instruction_agent
                    + f"\n\n[CONTEXTE RÉGLEMENTAIRE — textes officiels extraits du corpus]\n{contexte_rag[:6000]}\n"
                    + "[FIN CONTEXTE — cite les articles ci-dessus textuellement, ne paraphrase pas]"
                )

            execution_id = f"copilote-{current_user.user_id}-{uuid.uuid4().hex[:6]}"
            res = await agent.executer(
                instruction=instruction_agent,
                user_id=current_user.user_id,
                contexte={"pays_override": pays, "via_copilote": True},
                execution_id=execution_id,
            )
            resultat_agent = res.resume
            agent_utilise = agent_detecte
            session["nb_appels_agent"] += 1
        except Exception as e:
            logger.warning(f"[Copilote] Agent {agent_detecte} indisponible: {e}")
            resultat_agent = None  # Fallback sur réponse directe

    # ── Étape 2 : Réponse copilote (directe ou enrichissant le résultat agent) ─
    try:
        prompt_sys = _prompt_systeme_copilote(profil, pays, req.langue)

        # Construire le message utilisateur enrichi
        if contenu_fichiers or images_b64_chat:
            # Priorité au traitement des fichiers/images joints
            if images_b64_chat and not contenu_fichiers:
                # Images pures — pas de texte extrait, tout est dans la vision
                prompt_user = (
                    f"{req.message}\n\n"
                    f"[Analyse l'image ou les images jointes et réponds précisément à la demande.]"
                )
            elif images_b64_chat and contenu_fichiers:
                # Mix image + document texte
                prompt_user = (
                    f"L'utilisateur demande : {req.message}\n\n"
                    f"Contenu des fichiers texte :\n{contenu_fichiers}\n\n"
                    f"[Des images sont également jointes — analyse-les aussi.]"
                )
            else:
                # Documents texte uniquement
                prompt_user = (
                    f"L'utilisateur demande : {req.message}\n\n"
                    f"Voici le contenu des fichiers joints :\n{contenu_fichiers}\n\n"
                    f"Analyse ce contenu et réponds précisément à la demande."
                )
            agent_utilise = "document"
        elif resultat_agent:
            # Le copilote commente le résultat de l'agent
            fichiers_ctx = f"\n\n[Fichiers joints]\n{contenu_fichiers}" if contenu_fichiers else ""
            prompt_user = (
                f"{req.message}{fichiers_ctx}\n\n"
                f"[Résultat de l'analyse technique]\n{resultat_agent}\n\n"
                f"Explique ce résultat de façon naturelle et donne des conseils pratiques "
                f"basés sur ce contexte {pays}."
            )
        elif contexte_rag:
            # Enrichissement via RAG
            agent_utilise = "rag"
            historique = _construire_historique_claude(session["messages"], budget_tokens=800)
            hist_str = ""
            if historique:
                hist_str = "\n".join(
                    f"{'Utilisateur' if m['role'] == 'user' else 'Copilote'}: {m['content']}"
                    for m in historique
                )
            prompt_user = (
                f"{contexte_rag}\n\n"
                + (f"[Contexte conversation]\n{hist_str}\n\n" if hist_str else "")
                + f"[Question utilisateur]\n{req.message}"
            )
        else:
            # Inclure l'historique dans le prompt pour simuler la mémoire de session
            historique = _construire_historique_claude(session["messages"], budget_tokens=2000)
            if historique:
                hist_str = "\n".join(
                    f"{'Utilisateur' if m['role'] == 'user' else 'Copilote'}: {m['content']}"
                    for m in historique
                )
                prompt_user = f"[Contexte de la conversation]\n{hist_str}\n\n[Nouveau message]\n{req.message}"
            else:
                fichiers_ctx = f"\n\n[Contenu des fichiers joints]\n{contenu_fichiers}" if contenu_fichiers else ""
                # Pour les messages d'introduction, forcer une réponse dense et personnalisée
                _msg_low = req.message.lower()
                if any(w in _msg_low for w in [
                    "comment tu peux m'aider", "comment tu peux m\u2019aider",
                    "comment peux-tu m'aider", "comment peux-tu m\u2019aider",
                    "que peux-tu faire", "tu peux faire quoi",
                    "comment peux-tu", "tu peux m'aider",
                    "tes capacités", "tes fonctionnalités",
                    "qu'est-ce que tu peux", "qu'est ce que tu peux",
                    "comment tu m'aides", "qu'est-ce que tu fais",
                    "c'est quoi tes capacit", "tu peux faire quoi pour moi",
                ]):
                    prompt_user = (
                        f"{req.message}\n\n"
                        f"INSTRUCTION CRITIQUE : Réponds en 3-4 phrases MAXIMUM. "
                        f"Mentionne 2-3 cas d'usage CONCRETS et spécifiques pour ce professionnel. "
                        f"Pose UNE question précise pour démarrer une tâche réelle maintenant. "
                        f"INTERDIT : listes à puces, énumération de 6+ capacités, réponse générique."
                        + fichiers_ctx
                    )
                else:
                    prompt_user = req.message + fichiers_ctx

        # Log stats tokens (monitoring)
        try:
            from core.token_optimizer import stats_prompt
            _stats = stats_prompt(prompt_sys or "", [{"role": "user", "content": prompt_user}])
            logger.debug(
                f"[Copilote] Tokens — system:{_stats['tokens_system']} "
                f"prompt:{_stats['tokens_historique']} total:{_stats['total_input']}"
            )
        except Exception:
            pass

        # ── Vérification solde AVANT appel IA (évite de brûler des $ inutilement) ──
        try:
            from modules.pro.service_credits import verifier_solde_suffisant
            _ok_solde, _solde, _plan_solde, _msg_solde = await verifier_solde_suffisant(
                user_id=current_user.user_id,
                cout_estime_usd=0.10,
                db=db,
            )
            if not _ok_solde:
                if _msg_solde.startswith("CREDITS_EPUISES"):
                    parts = _msg_solde.split("|")
                    raise HTTPException(status_code=402, detail={
                        "code":    "CREDITS_EPUISES",
                        "message": f"Crédits Yukpo épuisés ({parts[1] if len(parts)>1 else '?'}/{parts[2] if len(parts)>2 else '?'} ce mois).",
                        "action":  "Rechargez vos crédits ou changez de plan pour continuer.",
                        "url":     "/abonnement",
                    })
                raise HTTPException(status_code=402, detail=_msg_solde)
        except HTTPException:
            raise
        except Exception as _e_solde:
            logger.warning(f"[Credits] Pré-check copilote non bloquant : {_e_solde}")

        # Appel IA via ia_client singleton — timeout global de 45s
        # Si images présentes → vision (Claude Opus / GPT-4o), timeout +10s
        _timeout_ia = 55.0 if images_b64_chat else 45.0
        try:
            reponse_ia = await asyncio.wait_for(
                ia_client.appeler(
                    prompt=prompt_user,
                    mode=ModeIA.COPILOTE,
                    systeme=prompt_sys,
                    max_tokens_override=4096,
                    utiliser_cache=False,  # Conversations dynamiques — pas de cache
                    images_b64=images_b64_chat or None,
                ),
                timeout=_timeout_ia,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=503,
                detail="Temps de réponse IA dépassé. Réessayez dans quelques instants.",
            )
        reponse_copilote = reponse_ia.contenu if hasattr(reponse_ia, "contenu") else str(reponse_ia)

        # ── Débit crédits Yukpo selon tokens réels consommés ─────────────────
        try:
            from modules.pro.service_credits import verifier_et_debiter
            ok, _credits, msg_credits = await verifier_et_debiter(
                    user_id=current_user.user_id,
                    modele=getattr(reponse_ia, "modele_utilise", "gpt-4o"),
                    tokens_input=getattr(reponse_ia, "tokens_input", 500),
                    tokens_output=getattr(reponse_ia, "tokens_output", 200),
                    module="copilote",
                    session_id=session.get("session_id"),
                    db=db,
                )
            if not ok:
                # msg_credits = "CREDITS_EPUISES|utilises|alloues"
                if msg_credits.startswith("CREDITS_EPUISES|"):
                    parts = msg_credits.split("|")
                    utilises = parts[1] if len(parts) > 1 else "?"
                    alloues  = parts[2] if len(parts) > 2 else "?"
                    raise HTTPException(status_code=402, detail={
                        "code":    "CREDITS_EPUISES",
                        "message": f"Crédits Yukpo épuisés ({utilises}/{alloues} ce mois).",
                        "action":  "Rechargez vos crédits ou changez de plan pour continuer.",
                        "url":     "/abonnement",
                    })
                raise HTTPException(status_code=402, detail=msg_credits)
        except HTTPException:
            raise
        except Exception as _e:
            logger.warning(f"[Credits] Débit copilote non bloquant : {_e}")

        # Sauvegarder dans l'historique de session
        _ajouter_message(session, "user", req.message)
        _ajouter_message(session, "assistant", reponse_copilote, {
            "agent_utilise": agent_utilise,
            "resultat_agent_inclus": bool(resultat_agent),
        })

        await incrementer_stat(current_user.user_id, "nb_requetes_copilote", db, xp_gain=1)

        # Extraire les chemins de fichiers embarqués dans la réponse agent (CV, LM…)
        fichiers_generes_copilote = None
        import re as _re_files
        tags_fichiers = _re_files.findall(r"<!-- FICHIER_GENERE:(.+?) -->", reponse_copilote)
        if tags_fichiers:
            fichiers_generes_copilote = [t.strip() for t in tags_fichiers]
            # Nettoyer le tag HTML caché de la réponse affichée
            reponse_copilote = _re_files.sub(r"<!-- FICHIER_GENERE:.+? -->", "", reponse_copilote).strip()

        # ── Calcul coût LLM réel + marge application ─────────────────────
        _tokens_in  = getattr(reponse_ia, "tokens_input",  0) or 0
        _tokens_out = getattr(reponse_ia, "tokens_output", 0) or 0
        _modele_id  = getattr(reponse_ia, "modele_utilise", "") or ""
        # Tarifs USD / 1M tokens (input / output)
        _TARIFS = {
            "claude-opus":        (15.0,  75.0),
            "claude-sonnet":      (3.0,   15.0),
            "claude-haiku":       (0.25,  1.25),
            "gpt-4o":             (2.5,   10.0),
            "gpt-4o-mini":        (0.15,  0.60),
        }
        _tarif_in, _tarif_out = next(
            (v for k, v in _TARIFS.items() if k in _modele_id.lower()),
            (3.0, 15.0),  # défaut : Sonnet
        )
        _cout_reel_usd = (
            (_tokens_in  * _tarif_in  / 1_000_000) +
            (_tokens_out * _tarif_out / 1_000_000)
        )
        _MARGE = 20.0
        _cout_avec_marge_usd = _cout_reel_usd * _MARGE
        # Conversion locale : XAF/XOF (zone FCFA) ≈ 655.957 XAF per EUR ≈ 601 per USD
        # Pour les autres devises (MAD, GHS, NGN, GNF…) on ne convertit pas → affiche USD
        _pays_code_cout = (getattr(profil, "pays", "") or pays or "CM").upper()
        _cadre_cout = _CADRE_JURIDIQUE_PAYS.get(_pays_code_cout, _CADRE_JURIDIQUE_PAYS["_DEFAULT"])
        _devise_str = _cadre_cout.get("devise", "")
        # Extraire l'ISO code de la devise (ex: "Franc CFA BEAC (XAF)" → "XAF")
        import re as _re_devise
        _devise_iso_match = _re_devise.search(r"\(([A-Z]{3})\)", _devise_str)
        _devise_iso = _devise_iso_match.group(1) if _devise_iso_match else "USD"
        _CFA_DEVISES = {"XAF", "XOF"}
        if _devise_iso in _CFA_DEVISES:
            _cout_local = round(_cout_avec_marge_usd * 601, 0)  # 1 USD ≈ 601 FCFA
        else:
            _cout_local = None  # pas de conversion → afficher USD côté client

        return {
            "session_id":           session["session_id"],
            "reponse":              reponse_copilote,
            "agent_utilise":        agent_utilise,
            "resultat_agent":       resultat_agent,
            "nb_messages_session":  len(session["messages"]),
            "profil_metier":        getattr(profil, "metier", None),
            "fichiers_generes":     fichiers_generes_copilote,
            "navigation_suggestions": _suggestions_modules(req.message, _intention, _modules_llm),
            # Coût LLM transparent
            "cout_llm": {
                "modele":        _modele_id,
                "tokens_input":  _tokens_in,
                "tokens_output": _tokens_out,
                "cout_reel_usd": round(_cout_reel_usd, 6),
                "marge":         _MARGE,
                "cout_app_usd":  round(_cout_avec_marge_usd, 4),
                "cout_app_xaf":  _cout_local,   # None si hors zone CFA
                "devise_cout":   _devise_iso if _devise_iso in _CFA_DEVISES else None,
            },
        }

    except HTTPException:
        raise  # Laisser passer les HTTPException (503, 401, etc.)
    except (RuntimeError, Exception) as e:
        err_str = str(e)
        logger.error(f"[Copilote] Erreur user={current_user.user_id}: {type(e).__name__}: {err_str[:300]}")
        # Message utilisateur selon le type d'erreur
        if "budget" in err_str.lower():
            detail = "Quota IA journalier atteint. Réessayez demain."
            status = 429
        elif "configurez" in err_str.lower() or "clé" in err_str.lower():
            detail = "Service IA non configuré. Contactez l'administrateur."
            status = 503
        elif "indisponible" in err_str.lower() or "circuit" in err_str.lower():
            detail = "Service IA temporairement indisponible. Réessayez dans quelques instants."
            status = 503
        elif "authentication" in err_str.lower() or "401" in err_str:
            detail = "Clé API IA invalide. Contactez l'administrateur."
            status = 503
        elif "rate_limit" in err_str.lower() or "429" in err_str:
            detail = "Limite de requêtes IA atteinte. Réessayez dans quelques secondes."
            status = 429
        else:
            detail = "Erreur interne. Réessayez dans quelques instants."
            status = 500
        raise HTTPException(status_code=status, detail=detail)


@router.post("/nouveau", summary="Démarrer une nouvelle session de conversation")
async def nouvelle_session_copilote(
    req: NouvelleSessionRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Réinitialise la mémoire de session du copilote.
    Utile quand l'utilisateur veut changer de sujet sans historique.
    """
    ancien_id = _SESSIONS.get(current_user.user_id, {}).get("session_id", "N/A")
    _SESSIONS[current_user.user_id] = {
        "session_id": uuid.uuid4().hex,
        "messages": [],
        "cree_le": datetime.utcnow().isoformat(),
        "dernier_message": None,
        "nb_appels_agent": 0,
        "raison_nouveau": req.raison,
    }
    return {
        "message": "Nouvelle session démarrée",
        "session_id": _SESSIONS[current_user.user_id]["session_id"],
        "ancien_session_id": ancien_id,
    }


@router.get("/historique", summary="Historique de la session en cours")
async def historique_copilote(
    current_user: TokenData = Depends(get_current_user),
    limit: int = 20,
):
    """
    Retourne l'historique de conversation de la session courante.
    """
    session = _get_session(current_user.user_id)
    messages = session["messages"][-limit:]
    return {
        "session_id":      session["session_id"],
        "nb_messages":     len(session["messages"]),
        "cree_le":         session["cree_le"],
        "dernier_message": session["dernier_message"],
        "nb_appels_agent": session.get("nb_appels_agent", 0),
        "messages":        messages,
    }


# ── Message d'accueil personnalisé (LLM + cache) ──────────────────────────────

_PAYS_NOMS: dict[str, str] = {
    "CM": "Cameroun", "CI": "Côte d'Ivoire", "SN": "Sénégal", "BF": "Burkina Faso",
    "TG": "Togo", "BJ": "Bénin", "ML": "Mali", "NE": "Niger", "GA": "Gabon",
    "CG": "Congo", "CD": "RD Congo", "TD": "Tchad", "CF": "Centrafrique",
    "GN": "Guinée", "DZ": "Algérie", "MA": "Maroc", "TN": "Tunisie",
    "MG": "Madagascar", "MR": "Mauritanie", "GQ": "Guinée équatoriale",
    "RW": "Rwanda", "BI": "Burundi", "DJ": "Djibouti", "KM": "Comores",
    "SC": "Seychelles", "MU": "Maurice", "ZA": "Afrique du Sud", "NG": "Nigeria",
    "GH": "Ghana", "KE": "Kenya", "ET": "Éthiopie", "EG": "Égypte", "LY": "Libye",
    "AO": "Angola", "MZ": "Mozambique", "ZW": "Zimbabwe", "ZM": "Zambie",
    "UG": "Ouganda", "TZ": "Tanzanie", "SD": "Soudan", "SS": "Soudan du Sud",
    "LR": "Liberia", "SL": "Sierra Leone", "GM": "Gambie", "CV": "Cabo Verde",
    "ST": "Sao Tomé", "GW": "Guinée-Bissau", "ER": "Érythrée", "SO": "Somalie",
    "BW": "Botswana", "NA": "Namibie", "LS": "Lesotho", "SZ": "Eswatini",
    "MW": "Malawi", "FR": "France", "BE": "Belgique", "CA": "Canada", "CH": "Suisse",
}

_METIER_LABELS_PLURIEL: dict[str, str] = {
    "comptable": "comptables",
    "drh": "responsables RH",
    "daf": "directeurs financiers",
    "juriste": "juristes",
    "banquier": "banquiers et analystes crédit",
    "analyste_credit": "analystes crédit",
    "trader": "gestionnaires d'actifs",
    "commercial": "commerciaux",
    "ingenieur": "ingénieurs",
    "transitaire": "transitaires",
    "charge_projets_ong": "chargés de projets ONG",
    "responsable_microfinance": "responsables microfinance",
    "notaire": "notaires",
    "huissier": "huissiers",
    "avocat": "avocats",
    "medecin": "médecins",
    "pharmacien": "pharmaciens",
    "daa": "directeurs administratifs",
    "douanier": "douaniers",
    "cv_emploi": "candidats",
    "recherche_emploi": "candidats",
    "generique": "professionnels",
}

_WELCOME_CACHE: dict[tuple, str] = {}


def _welcome_fallback(metier_pluriel: str, pays_nom: str, prenom: str) -> str:
    salutation = f"Bonjour {prenom}" if prenom else "Bonjour"
    if metier_pluriel and metier_pluriel != "professionnels":
        contexte = f"Je suis Yukpo Pro, votre assistant IA dédié aux {metier_pluriel} au {pays_nom}."
    else:
        contexte = f"Je suis Yukpo Pro, votre assistant IA pour les professionnels au {pays_nom}."
    return (
        f"{salutation} ! {contexte} "
        "Je peux analyser vos documents, générer des rapports, traduire vos fichiers "
        "et mobiliser des agents spécialisés pour des analyses pointues. "
        "Posez-moi votre première question ou envoyez un document."
    )


@router.get("/welcome", summary="Message d'accueil personnalisé (LLM + cache)")
async def welcome_copilote(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne un message d'accueil grammaticalement correct et contextualisé
    pour l'écran d'entrée du chat Copilote. Généré par LLM avec fallback
    template, caché par signature de profil (métier, pays, niveau, prénom).
    """
    from modules.pro.service_profil import get_or_create
    from core.ia_client import ModeIA, ia_client
    from core.database import UtilisateurDB
    from sqlalchemy import select

    profil, _ = await get_or_create(current_user.user_id, db)
    metier_key = (getattr(profil, "metier", "") or "generique").lower()
    pays_code = (getattr(profil, "pays", "") or "CM").upper()
    niveau = (getattr(profil, "niveau", "") or "").lower()

    prenom = ""
    try:
        res = await db.execute(select(UtilisateurDB).where(UtilisateurDB.id == current_user.user_id))
        u = res.scalar_one_or_none()
        if u:
            prenom = (getattr(u, "prenoms", "") or "").split(" ")[0].strip()
            if not prenom:
                prenom = (getattr(u, "nom", "") or "").split(" ")[0].strip()
    except Exception as e:
        logger.debug(f"[Copilote welcome] lecture utilisateur échouée ({e})")

    metier_pluriel = _METIER_LABELS_PLURIEL.get(
        metier_key, metier_key.replace("_", " ") + "s" if metier_key else "professionnels"
    )
    pays_nom = _PAYS_NOMS.get(pays_code, pays_code)

    cache_key = (metier_key, pays_code, niveau, prenom)
    if cache_key in _WELCOME_CACHE:
        return {"message": _WELCOME_CACHE[cache_key], "from_llm": True, "cached": True}

    fallback = _welcome_fallback(metier_pluriel, pays_nom, prenom)

    prompt = (
        "Rédige UN SEUL message d'accueil en français, chaleureux et naturel, "
        "pour un utilisateur qui se connecte à Yukpo Pro "
        "(assistant IA pour professionnels africains).\n\n"
        f"Profil utilisateur :\n"
        f"- Prénom : {prenom or '(inconnu)'}\n"
        f"- Métier (pluriel, à utiliser tel quel) : {metier_pluriel}\n"
        f"- Pays (nom complet, à utiliser tel quel) : {pays_nom}\n"
        f"- Niveau : {niveau or 'professionnel'}\n\n"
        "Contraintes IMPÉRATIVES :\n"
        "- 2 à 3 phrases, grammaire française irréprochable\n"
        "- Commencer par « Bonjour » + prénom si connu\n"
        "- Mentionner que Yukpo Pro peut : analyser des documents, générer des rapports, "
        "traduire, activer des agents spécialisés\n"
        "- Terminer par une invitation à poser une question ou envoyer un document\n"
        "- Ton professionnel mais accessible, PAS de listes, PAS de markdown\n"
        "- Ne JAMAIS utiliser un code pays brut (CM, TG…), toujours le nom complet\n"
        "- Formuler « dédié aux {métier pluriel} » — jamais « aux professionnels en X »\n\n"
        "Réponds uniquement par le message, sans préambule ni guillemets."
    )

    try:
        reponse = await asyncio.wait_for(
            ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.REDACTION,
                utiliser_cache=True,
                max_tokens_override=250,
            ),
            timeout=6.0,
        )
        texte = (reponse.contenu or "").strip().strip('"').strip("'").strip()
        if 40 <= len(texte) <= 800 and "\n\n" not in texte:
            _WELCOME_CACHE[cache_key] = texte
            return {"message": texte, "from_llm": True, "cached": False}
        logger.debug(f"[Copilote welcome] réponse LLM rejetée (len={len(texte)})")
    except Exception as e:
        logger.debug(f"[Copilote welcome] LLM indispo ({e}) → fallback template")

    return {"message": fallback, "from_llm": False, "cached": False}


@router.get("/suggestions", summary="Suggestions de questions personnalisées")
async def suggestions_copilote(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne des suggestions de questions pertinentes selon le profil métier.
    Utile pour l'onboarding et l'engagement.
    """
    from modules.pro.service_profil import get_or_create

    profil, _ = await get_or_create(current_user.user_id, db)
    metier = getattr(profil, "metier", "") or "generique"
    pays = getattr(profil, "pays", "") or "CM"

    suggestions_par_metier: dict[str, list[str]] = {
        "comptable": [
            f"Comment calculer l'IRPP d'un salarié avec 850 000 FCFA de salaire brut au {pays} ?",
            "Quelles sont les nouveautés SYSCOHADA révisé pour les provisions ?",
            "Aide-moi à préparer une liasse fiscale simplifiée",
            "Quels sont les taux de TVA applicables aux prestations de services ?",
        ],
        "drh": [
            "Calcule le bulletin de paie d'un salarié avec 3 ans d'ancienneté et 2 enfants",
            f"Quelles sont les obligations de l'employeur en cas de licenciement économique au {pays} ?",
            "Rédige un contrat de travail à durée déterminée pour un commercial",
            "Comment calculer les congés payés d'un salarié partant en mission ?",
        ],
        "juriste": [
            "Quelles sont les formalités de création d'une SARL en zone OHADA ?",
            "Rédige une clause de non-concurrence solide pour un contrat de travail",
            "Quel est le délai de prescription pour une action en paiement commercial ?",
            "Explique les différences entre OHADA et droit national en matière contractuelle",
        ],
        "banquier": [
            "Calcule le TEG d'un crédit immobilier de 15M FCFA sur 20 ans",
            "Comment structurer un crédit syndiqué pour un projet industriel ?",
            "Quels sont les ratios COBAC que je dois surveiller ce trimestre ?",
            "Explique-moi la procédure KYC pour un client entreprise dans la zone CEMAC",
        ],
        "ingenieur": [
            "Aide-moi à planifier un chantier de construction en CPM avec 8 tâches",
            "Quels sont les seuils d'appel d'offres pour les travaux au Cameroun ?",
            "Comment rédiger un DAO conforme aux règles ARMP ?",
            "Calcule les coefficients de charges pour un chantier de génie civil",
        ],
        "daf": [
            "Analyse ces ratios de mon bilan et dis-moi ce qui cloche",
            "Projette mon cashflow sur 12 mois avec ces données",
            "Comment optimiser ma structure de financement face à la hausse des taux CEMAC ?",
            "Aide-moi à préparer mon board pack mensuel",
        ],
        "charge_projets_ong": [
            "Construis un cadre logique pour un projet WASH de 18 mois",
            "Prépare un budget au format AFD pour un projet de 250M FCFA",
            "Comment rédiger un rapport d'avancement mi-parcours pour un bailleur DFID ?",
            "Quels indicateurs SMART pour un projet de renforcement de capacités ?",
        ],
        "responsable_microfinance": [
            "Calcule le PAR30 de mon portefeuille avec ces données de retards",
            "Quel est le taux usuraire maximal autorisé par le COBAC en zone CEMAC ?",
            "Aide-moi à concevoir un produit de crédit agricole adapté aux saisonniers",
            "Analyse ce bilan de SFD et identifie les ratios hors norme",
        ],
        "transitaire": [
            "Calcule les droits de douane pour l'importation de matériaux de construction au Cameroun",
            "Quelle est la différence entre CIF et FOB et lequel choisir à l'import ?",
            "Quels documents sont obligatoires pour une importation de produits alimentaires ?",
            "Dans quel régime douanier placer du matériel de chantier temporaire ?",
        ],
        "generique": [
            "Qu'est-ce que la zone CEMAC et quels pays en font partie ?",
            "Aide-moi à rédiger un email professionnel en anglais pour un partenaire",
            "Explique-moi les fondamentaux du droit OHADA en 5 points",
            "Quelles sont les meilleures pratiques de gestion de projet en Afrique ?",
        ],
    }

    # Choisir les suggestions selon le métier
    suggestions = (
        suggestions_par_metier.get(metier)
        or suggestions_par_metier.get(metier.lower())
        or suggestions_par_metier["generique"]
    )

    return {
        "profil_metier": metier,
        "pays": pays,
        "suggestions": suggestions,
        "message_accueil": (
            f"Bonjour ! Je suis Yukpo Copilote, votre assistant professionnel. "
            f"Je suis là pour vous aider sur tous vos sujets métier et au-delà. "
            f"Posez-moi n'importe quelle question !"
        ),
    }
