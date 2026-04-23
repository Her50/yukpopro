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
from datetime import datetime, timezone
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
            cree_le=datetime.now(timezone.utc),
            modifie_le=datetime.now(timezone.utc),
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

class CopiloteChatRequest(BaseModel):
    message:    str  = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = None
    pays:       Optional[str] = None
    langue:     str = Field("fr", description="fr ou en")
    fichiers:   Optional[List[FichierChat]] = None


class NouvelleSessionRequest(BaseModel):
    raison: Optional[str] = Field(None, description="Ex: 'nouveau projet', 'sujet différent'")


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _get_session(user_id: int) -> dict:
    """Récupère ou crée une session copilote pour l'utilisateur."""
    if user_id not in _SESSIONS:
        _SESSIONS[user_id] = {
            "session_id": uuid.uuid4().hex,
            "messages": [],
            "cree_le": datetime.now(timezone.utc).isoformat(),
            "dernier_message": None,
            "nb_appels_agent": 0,
        }
    return _SESSIONS[user_id]


def _ajouter_message(session: dict, role: str, contenu: str, meta: dict | None = None):
    """Ajoute un message à l'historique de session (FIFO avec max)."""
    session["messages"].append({
        "role": role,
        "content": contenu,
        "ts": datetime.now(timezone.utc).isoformat(),
        "meta": meta or {},
    })
    session["dernier_message"] = datetime.now(timezone.utc).isoformat()
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
- "conversation" → question générale, explication, conseil, salutation (bonjour, merci...), discussion sans demande de document ni de calcul technique

RÈGLE CRITIQUE FICHIERS JOINTS: Si des fichiers sont joints ET l'utilisateur demande une analyse directe (pas une génération de document Word/PDF), classer en "agent_metier" avec agent="daa".

SOUS-TYPES generateur (choisir le plus précis):
- "contrat" : contrat (bail, travail, prestation, vente, service), convention, avenant, lettre officielle, lettre commerciale, mise en demeure, résiliation, attestation, certificat, statuts, règlement intérieur, PV, note de service, charte, cahier des charges
- "rapport" : rapport, note de synthèse, plan d'action, compte-rendu, business plan, analyse, étude, note juridique
- "slides" : présentation PowerPoint, slides, deck, support de formation
- "cv" : CV, curriculum vitae, lettre de motivation, lettre d'emploi

TYPES PRÉCIS (choisir le plus proche):
rapport_analyse, rapport_financier, rapport_rh, rapport_audit, note_de_synthese, note_juridique, plan_action, compte_rendu, business_plan,
contrat_bail, contrat_travail, contrat_prestation, contrat_vente, convention, statuts, reglement_interieur,
lettre_officielle, lettre_commerciale, lettre_mise_en_demeure, lettre_resiliation, lettre_emploi,
attestation, certificat, proces_verbal,
slides_bilan_activite, slides_rapport_direction, slides_proposition_client, slides_pitch_projet, slides_formation,
cv, lettre_motivation

AGENTS DISPONIBLES (pour agent_metier):
drh, comptable, daf, juriste, banquier, commercial, daa, ingenieur, microfinance, ong, douanier, cv_emploi, recherche_emploi

FORMAT: "docx" pour Word, "pptx" pour PowerPoint
LANGUE_CIBLE (si traduction): fr, en, es, pt, ar
FORMAT_CIBLE (si conversion): docx, pdf, pptx, xlsx, csv, txt, jpg

JSON REQUIS (tous les champs, null si non applicable):
{{"intention": "...", "sous_type": "...", "type_doc": "...", "agent": null, "format": "docx", "langue_cible": null, "format_cible": null, "confiance": 0.9}}"""

    try:
        reponse = await asyncio.wait_for(
            ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.PRECISION,
                utiliser_cache=False,
                max_tokens_override=100,
            ),
            timeout=6.0,
        )
        raw = reponse.contenu.strip() if hasattr(reponse, "contenu") else str(reponse).strip()
        # Extraire le JSON même s'il est entouré de markdown
        match = _re.search(r"\{.*?\}", raw, _re.DOTALL)
        if match:
            raw = match.group(0)
        result = json.loads(raw)

        # Valider et normaliser
        if result.get("intention") not in {"generateur", "agent_metier", "traduction", "conversion", "conversation"}:
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

    # Mots-clés réglementaires sectoriels
    mots_cles_reglementaires = [
        "ohada", "syscohada", "acte uniforme", "brvm",
        "code cima", "cima", "crca",
        "cgi", "code général des impôts", "code des impôts",
        "code du travail", "droit du travail",
        "cobac", "bceao", "cemac", "uemoa", "cnps", "lacobac",
        "tva", "irpp", "imposition", "déclaration fiscale",
        "exonération fiscale", "crédit d'impôt",
        "sarl", "suarl",
        "marge de solvabilité", "provision technique", "état c",
        "traité de réassurance",
        "selon le code", "texte de loi", "texte officiel",
        "quelle est la loi", "est-ce légal", "est-ce conforme",
        "selon la réglementation", "réglementairement",
        "incoterm", "droits de douane",
        "jurisprudence", "tribunal", "cour", "jugement", "arrêt",
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


def _prompt_systeme_copilote(profil, pays: str, langue: str) -> str:
    """Construit le prompt système personnalisé du copilote."""
    metier = getattr(profil, "metier", "") or "professionnel"
    nom = getattr(profil, "nom", "") or ""
    pays_profil = getattr(profil, "pays", "") or pays or "Afrique francophone"
    secteur = getattr(profil, "secteur", "") or ""

    identite = f"Tu es **Yukpo Copilote**, l'assistant personnel de {nom or 'votre collaborateur'}" if nom else "Tu es **Yukpo Copilote**, l'assistant personnel intelligent"

    return f"""
{identite}, un professionnel en {metier}{' dans le secteur ' + secteur if secteur else ''} basé en {pays_profil}.

**Qui tu es :**
Tu es un assistant IA de très haut niveau, comme avoir un conseiller expert, un ami brillant et polyvalent
qui comprend à la fois le monde des affaires africain et international.
Tu combines la profondeur d'un expert métier avec la chaleur d'une conversation naturelle.

**Ce que tu fais :**
- Tu réponds à TOUTES les questions : métier, actualité, rédaction, calculs, conseils stratégiques, culture générale
- Tu t'exprimes de façon naturelle, directe, sans jargon inutile sauf si le professionnel en a besoin
- Tu connais parfaitement le contexte africain francophone : droit OHADA, SYSCOHADA, CIMA, marchés africains, UEMOA, CEMAC
- Tu adaptes tes réponses au niveau et au contexte de {metier}
- Quand tu fais un calcul ou une analyse complexe, tu expliques le raisonnement clairement
- Tu mémorises le contexte de la conversation et y fais référence naturellement

**Ton style :**
- Comme deux collègues qui se parlent franchement, pas comme un chatbot formel
- Concis quand la réponse est simple, détaillé quand la profondeur est utile
- Tu utilises des exemples concrets tirés de l'environnement {pays_profil}
- Langue principale : {"anglais" if langue == "en" else "français"} professionnel africain

**Agents spécialisés intégrés dans Yukpo Pro (13 agents, appelés automatiquement selon le contexte) :**
- **Agent DRH** : paie, bulletins de salaire, CNPS, contrats de travail, recrutement, évaluation, plan de formation
- **Agent Comptable** : SYSCOHADA, déclarations fiscales, TVA, IRPP, bilans, trésorerie, comptabilité analytique
- **Agent DAF** : tableau de bord financier, budget, trésorerie, reporting, contrôle de gestion, directeur financier
- **Agent Banquier** : crédit, analyse financière, TEG, KYC, scoring, tableaux d'amortissement, ratios
- **Agent Juriste** : droit OHADA, textes de loi, contrats, actionnariat, litiges, recherche juridique
- **Agent Commercial** : business plan, stratégie vente, étude de marché, marketing, proposition commerciale
- **Agent DAA** : analyse de données, statistiques, KPI, tableaux de bord, data science, visualisation
- **Agent Ingénieur** : gestion de projet, BTP, cahiers des charges, appels d'offres, planning, architecture
- **Agent Microfinance** : PAR30, portefeuille crédit, SFD, IMF, crédit solidaire
- **Agent ONG** : logframe, bailleurs de fonds, M&E, reporting, indicateurs, développement
- **Agent Douanier** : incoterms, droits de douane, régimes douaniers, import/export, transit, commerce international
- **Agent CV/Emploi** : rédaction CV, lettre de motivation, préparation entretien, candidature
- **Agent Recherche Emploi** : veille offres d'emploi, job search, opportunités professionnelles

**CAPACITÉS DE GÉNÉRATION DE DOCUMENTS (CRITIQUE) :**
Yukpo Pro PEUT générer et télécharger directement depuis ce chat :
- **Contrats** : bail, travail, prestation, vente, convention, avenant, protocole
- **Lettres** : officielle, commerciale, mise en demeure, résiliation, offre d'emploi
- **Attestations** : attestation de travail, de salaire, certificats
- **Documents RH** : règlement intérieur, statuts, procès-verbaux
- **Rapports** : financier, RH, audit, analyse, note de synthèse, plan d'action
- **Présentations PowerPoint** : pour direction, conseil d'administration, clients
- **Traductions** : tout document en FR/EN/ES/PT avec export DOCX

RÈGLE ABSOLUE : Quand l'utilisateur demande de générer/créer/rédiger un document,
tu NE DIS JAMAIS "je ne peux pas" — le backend génère automatiquement le fichier.
Si un lien `/api/v1/...` ou un nom de fichier apparaît dans le résultat de l'agent ci-dessous,
cite-le tel quel comme lien de téléchargement.
NE JAMAIS inventer ou promettre un lien de téléchargement si aucun lien réel n'est fourni dans le résultat.

**FORMATAGE MARKDOWN OBLIGATOIRE :**
- Utilise **gras** pour les termes clés, montants, noms propres importants
- Utilise des listes à puces (- ou •) quand tu énumères 3+ éléments
- Utilise des titres (## ou ###) pour structurer les réponses longues
- Utilise `code` pour les formules, articles de loi, références réglementaires
- Met en forme les tableaux en markdown quand tu présentes des données comparatives
- Chaque réponse doit être visuellement structurée, pas du texte brut

**Ton style de réponse :**
- Expert du contexte africain : OHADA, SYSCOHADA, CIMA, droit du travail camerounais/ivoirien/sénégalais
- Tu cites des articles de loi, des montants FCFA concrets, des procédures réelles
- Tu poses des questions de clarification si besoin pour personnaliser le document
- Pas de préambule vide ("Bien sûr !", "Je serais ravi de...") — va droit au contenu

**CODE CIMA / OHADA / TEXTES JURIDIQUES — RÈGLE :**
1. Si le contexte contient des articles (=== ARTICLES CODE CIMA === ou === CORPUS RÉGLEMENTAIRE ===) :
   → Cite les articles avec leurs numéros EXACTS et le texte fourni, puis donne ton analyse.
2. Si aucun article n'est fourni dans le contexte mais l'utilisateur pose une question juridique précise :
   → Réponds depuis ta connaissance de formation, en indiquant clairement :
   "[Réponse depuis mémoire IA — non indexé dans le corpus Yukpo, vérifier le texte officiel]"
   → Fournis quand même le texte de l'article tel que tu le connais, avec son numéro et sa portée.
3. NE JAMAIS refuser de répondre sur un article juridique — toujours apporter une réponse utile.

**Interdictions absolues :**
- NE JAMAIS dire "je ne peux pas générer un document" — le backend génère tout
- NE JAMAIS dire "copiez ce texte dans Word" — Yukpo génère le fichier téléchargeable
- NE JAMAIS donner une liste de formules Excel à copier — générer le rapport directement
- NE JAMAIS demander à l'utilisateur d'aller dans un autre module
- NE JAMAIS répondre en texte brut sans aucun formatage markdown
- NE JAMAIS dire "je ne peux pas lire ce fichier Excel/CSV/Word" — le backend extrait automatiquement le contenu des fichiers joints et te le transmet. Si tu vois [Données des fichiers joints] dans le prompt, lis et analyse-les directement.
- NE JAMAIS dire "je n'ai pas accès au fichier" — quand un fichier est joint, son contenu textuel est inclus dans ce message.

**ANALYSE DE FICHIERS (FICHIERS JOINTS) :**
Quand l'utilisateur joint un fichier (Excel, CSV, Word, PDF), son contenu est extrait et fourni
dans la section [Données des fichiers joints] ou [Voici le contenu des fichiers joints].
Tu DOIS analyser ce contenu directement et répondre avec précision sur les données réelles du fichier.
Ne jamais prétendre ne pas avoir accès au fichier.
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
    pays = req.pays or getattr(profil, "pays", "") or "CM"

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
    _intention    = orchestration["intention"]
    _sous_type    = orchestration.get("sous_type") or ""
    _type_doc_o   = orchestration.get("type_doc") or ""
    _agent_orch   = orchestration.get("agent")
    _format_orch  = orchestration.get("format") or "docx"
    _lc_orch      = orchestration.get("langue_cible") or "en"
    _fc_orch      = orchestration.get("format_cible") or _format_orch

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
            contexte_gen = "\n\n".join(contexte_gen_parts) or None

            if _sous_type == "slides":
                from modules.pro.slide_builder_pro import SlideBuilderPro
                builder = SlideBuilderPro(profil=profil)
                type_pres_map = {
                    "slides_bilan_activite": "bilan_activite",
                    "slides_rapport_direction": "rapport_direction",
                    "slides_proposition_client": "proposition_client",
                    "slides_pitch_projet": "pitch_projet",
                    "slides_formation": "formation",
                }
                type_pres = type_pres_map.get(_type_doc_o, "rapport_direction")
                res_doc = await asyncio.wait_for(
                    builder.generer(
                        sujet=req.message,
                        type_pres=type_pres,
                        mode="executive",
                        contexte=contexte_gen,
                        format_sortie="pptx",
                    ),
                    timeout=90.0,
                )
                ext = "PPTX"
                type_doc_gen = _type_doc_o or "slides"
            else:
                from modules.pro.report_writer_pro import ReportWriterPro
                writer = ReportWriterPro(profil=profil)
                type_doc_gen = _type_doc_o or _detecter_type_document(req.message)
                res_doc = await asyncio.wait_for(
                    writer.generer(
                        sujet=req.message,
                        type_rapport=type_doc_gen,
                        mode="standard",
                        contexte=contexte_gen,
                        format_sortie="docx",
                    ),
                    timeout=90.0,
                )
                ext = "DOCX"

            chemin_fichier = res_doc.get("fichier") or res_doc.get("chemin_fichier")
            apercu = res_doc.get("apercu", "")
            fichiers_msg = f"\n\n*(Basé sur {len(req.fichiers)} fichier(s) joint(s))*" if contenu_fichiers else ""
            reponse_gen = (
                f"**Document {ext} généré avec succès — prêt à télécharger.**{fichiers_msg}\n\n"
                + (apercu[:1200] if apercu else "Votre document est prêt.")
            )

            _ajouter_message(session, "user", req.message)
            _ajouter_message(session, "assistant", reponse_gen, {"agent_utilise": "generateur"})
            await incrementer_stat(current_user.user_id, "nb_documents_generes", db, xp_gain=3)
            await _sauvegarder_doc_db(
                db=db, user_id=current_user.user_id,
                titre=req.message[:100],
                type_doc=type_doc_gen,
                fichier=chemin_fichier,
                contenu_genere=apercu,
                session_id=session["session_id"],
                meta={"source": "chat", "format": ext.lower(), "avec_fichiers": bool(contenu_fichiers)},
            )

            return {
                "session_id":          session["session_id"],
                "reponse":             reponse_gen,
                "agent_utilise":       "generateur",
                "resultat_agent":      None,
                "nb_messages_session": len(session["messages"]),
                "profil_metier":       getattr(profil, "metier", None),
                "fichiers_generes":    [chemin_fichier] if chemin_fichier else None,
            }
        except asyncio.TimeoutError:
            logger.warning("[Copilote-Gen] Timeout génération document — réponse texte")
        except Exception as e:
            logger.warning(f"[Copilote-Gen] Génération échouée: {e}")
            # Fallback : le copilote répond avec le contenu en texte

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
                    timeout=60.0,
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
                    timeout=60.0,
                )
                contenu_doc = rep_lm.contenu if hasattr(rep_lm, "contenu") else str(rep_lm)
                nom_base    = "lettre_motivation_yukpo"

            # ── Construire le fichier DOCX/PDF ────────────────────────────
            builder_cv = CvDocumentBuilder(profil=profil)

            if type_doc == "cv":
                res_cv = await asyncio.wait_for(
                    builder_cv.generer_cv(contenu_doc, nom_base=nom_base, format_sortie=format_sortie_cv),
                    timeout=20.0,
                )
            else:
                res_cv = await asyncio.wait_for(
                    builder_cv.generer_lettre(contenu_doc, nom_base=nom_base, format_sortie=format_sortie_cv),
                    timeout=20.0,
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
            await _sauvegarder_doc_db(
                db=db, user_id=current_user.user_id,
                titre=req.message[:100],
                type_doc="lettre_emploi" if type_doc == "lettre" else "cv",
                fichier=chemin_cv,
                contenu_genere=contenu_doc[:2000],
                session_id=session["session_id"],
                meta={"source": "chat", "format": format_sortie_cv},
            )

            return {
                "session_id":          session["session_id"],
                "reponse":             reponse_cv,
                "agent_utilise":       "cv_emploi",
                "resultat_agent":      None,
                "nb_messages_session": len(session["messages"]),
                "profil_metier":       getattr(profil, "metier", None),
                "fichiers_generes":    [chemin_cv] if chemin_cv else None,
            }

        except asyncio.TimeoutError:
            logger.warning("[Copilote-CV] Timeout génération document CV — fallback texte")
        except Exception as e_cv:
            logger.warning(f"[Copilote-CV] Génération CV échouée: {e_cv}")
            # Fallback : le copilote répond en texte (boucle normale)

    # ── Étape 0f : RAG en parallèle (contexte réglementaire) ─────────────────
    # L'agent est déjà connu via l'orchestrateur (_agent_orch).
    # On lance juste le RAG si pertinent, pendant que l'agent réfléchit.
    a_fichiers_joints = bool(contenu_fichiers or images_b64_chat)
    contexte_rag  = ""
    # Utiliser l'agent détecté par l'orchestrateur LLM.
    # Si intention != agent_metier mais _agent_orch est non null (signal profil),
    # on l'utilise quand même pour enrichir la réponse copilote.
    agent_detecte = _agent_orch if _intention == "agent_metier" else None

    if not a_fichiers_joints and _intention in ("agent_metier", "conversation"):

        async def _tache_rag() -> str:
            if not _besoin_rag(req.message):
                return ""
            parties_rag = []

            # 1. Recherche CIMA si question liée à l'assurance/CIMA
            _MOTS_CIMA = {
                "cima", "assurance", "sinistre", "prime", "garantie", "indemnisation",
                "rc auto", "responsabilité civile", "vie", "capitalisation", "réassurance",
                "microassurance", "police", "souscription assurance", "contrat assurance",
                "couverture assurance", "branche assurance", "agrément", "solvabilité",
                "provisions techniques", "compagnie d'assurance",
                # Captures "article 13 nouveau" et toute question sur un article précis
                "article", "art.", "art ",
            }
            msg_lower = req.message.lower()
            if any(mot in msg_lower for mot in _MOTS_CIMA):
                try:
                    from modules.chat.cima_retriever import rechercher_articles
                    res_cima = await asyncio.wait_for(
                        asyncio.to_thread(rechercher_articles, req.message),
                        timeout=5.0,
                    )
                    if res_cima and res_cima.strip():
                        parties_rag.append(f"=== ARTICLES CODE CIMA ===\n{res_cima}")
                except asyncio.TimeoutError:
                    logger.warning("[Copilote] CIMA retriever timeout (>5s)")
                except Exception as e:
                    logger.warning(f"[Copilote] CIMA retriever indisponible: {e}")

            # 2. Recherche corpus réglementaire général (OHADA, fiscal, travail…)
            try:
                from modules.rag.rag_embedder import rag_embedder_manager
                from modules.rag.rag_retriever import rechercher_pour_metier, rechercher_corpus_reglementaire
                metier_profil = getattr(profil, "metier", "") or ""
                if rag_embedder_manager.modele_pret:
                    if metier_profil:
                        res = await asyncio.wait_for(
                            asyncio.to_thread(rechercher_pour_metier, req.message, metier_profil, pays),
                            timeout=4.0,
                        )
                        if res:
                            parties_rag.append(res)
                    if not parties_rag or not any("CODE CIMA" in p for p in parties_rag):
                        res2 = await asyncio.wait_for(
                            asyncio.to_thread(rechercher_corpus_reglementaire, req.message, pays),
                            timeout=4.0,
                        )
                        if res2:
                            parties_rag.append(res2)
            except asyncio.TimeoutError:
                logger.warning("[Copilote] RAG timeout (>4s)")
            except Exception as e:
                logger.warning(f"[Copilote] RAG indisponible: {e}")

            return "\n\n".join(parties_rag)

        contexte_rag = await _tache_rag()

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

        return {
            "session_id":       session["session_id"],
            "reponse":          reponse_copilote,
            "agent_utilise":    agent_utilise,
            "resultat_agent":   resultat_agent,
            "nb_messages_session": len(session["messages"]),
            "profil_metier":    getattr(profil, "metier", None),
            "fichiers_generes": fichiers_generes_copilote,
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
        "cree_le": datetime.now(timezone.utc).isoformat(),
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
