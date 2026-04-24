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
    # Défaut générique pour les pays non listés
    "_DEFAULT": {
        "nom_complet": "Pays africain",
        "zone_eco": "Afrique subsaharienne",
        "devise": "Monnaie locale",
        "banque_centrale": "Banque centrale nationale",
        "fiscal": "Code des impôts national applicable",
        "travail": "Code du travail national applicable",
        "commercial": "Droit commercial national · OHADA si pays membre",
        "comptable": "SYSCOHADA si pays OHADA, sinon normes comptables nationales",
        "assurance": "Code CIMA si pays membre (zone CIMA), sinon réglementation nationale",
        "specificites": "Vérifier le cadre juridique spécifique du pays concerné",
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


def _prompt_systeme_copilote(profil, pays: str, langue: str) -> str:
    """
    Construit le prompt système hyper-contextualisé du copilote.
    Injecte le cadre juridique précis du pays + profil métier pour
    éliminer les hallucinations et garantir des réponses précises et localisées.
    """
    metier = getattr(profil, "metier", "") or "professionnel"
    nom = getattr(profil, "nom", "") or ""
    pays_code = (getattr(profil, "pays", "") or pays or "CM").upper()
    secteur = getattr(profil, "secteur", "") or ""
    niveau = getattr(profil, "niveau_expertise", "") or "intermediaire"
    experience = getattr(profil, "annees_experience", None)

    # Récupérer le cadre juridique du pays
    cadre = _CADRE_JURIDIQUE_PAYS.get(pays_code, _CADRE_JURIDIQUE_PAYS["_DEFAULT"])
    pays_nom = cadre["nom_complet"]
    zone_eco = cadre["zone_eco"]
    devise = cadre["devise"]
    banque_centrale = cadre["banque_centrale"]
    specificites = cadre.get("specificites", "")

    # Corpus prioritaire selon le métier
    corpus_metier = _METIER_CORPUS_PRIORITAIRE.get(metier, _METIER_CORPUS_PRIORITAIRE["autre"])
    corpus_str = "\n   - ".join(corpus_metier)

    # Niveau d'expertise → ajuster le ton
    ton_niveau = {
        "debutant":      "Explique les concepts avec des exemples simples. Définis les termes techniques.",
        "intermediaire": "Réponds avec précision technique, en supposant une bonne base professionnelle.",
        "senior":        "Réponds de pair à pair, avec précision technique maximale et nuances pratiques.",
        "expert":        "Réponse d'expert à expert — détail technique complet, références précises, nuances jurisprudentielles.",
    }.get(niveau, "Réponds avec précision technique adaptée au profil.")

    exp_str = f", {experience} ans d'expérience" if experience else ""

    return f"""Tu es **Yukpo Copilote**, l'assistant personnel de {nom or 'ce professionnel'} — {metier.replace('_', ' ')}{f' dans le secteur {secteur}' if secteur else ''}{exp_str}.

═══════════════════════════════════════════════════
  CONTEXTE UTILISATEUR — LOCALISATION PRÉCISE
═══════════════════════════════════════════════════
▸ Pays         : {pays_nom} ({pays_code})
▸ Zone économique : {zone_eco}
▸ Devise       : {devise}
▸ Banque centrale : {banque_centrale}
▸ Métier       : {metier.replace('_', ' ').title()}
▸ Secteur      : {secteur or 'Non spécifié'}
▸ Niveau       : {niveau}
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

CORPUS JURIDIQUE PRIORITAIRE POUR CE PROFIL ({metier.upper()}) :
   - {corpus_str}

COUVERTURE DES DOCUMENTS RAG INDEXÉS (ce que Yukpo a réellement en base documentaire) :
{"▸ CGI indexé : " + ", ".join(_RAG_COUVERTURE["CGI_indexé"]) if pays_code in _RAG_COUVERTURE["CGI_indexé"] else "▸ CGI : NON INDEXÉ pour " + pays_code + " → ta mémoire de formation est la source principale"}
{"▸ Code du travail indexé" if pays_code in _RAG_COUVERTURE["travail_indexé"] else "▸ Code du travail : NON INDEXÉ pour " + pays_code}
{"▸ Code pénal indexé" if pays_code in _RAG_COUVERTURE["penal_indexé"] else "▸ Code pénal : NON INDEXÉ pour " + pays_code}
▸ OHADA : tous les actes uniformes indexés (AUS, AUDCG, SYSCOHADA, AUPCAP, AUSCGIE…)
▸ Normes ISO 45001 (SST) + Conventions OIT : indexées
→ IMPORTANT : si un corpus RAG est injecté dans le message, utilise-le en priorité pour les citations.
→ Si aucun corpus n'est injecté pour ce pays/domaine, réponds avec ta mémoire de formation + label [Mémoire IA].

═══════════════════════════════════════════════════
  RÈGLES ANTI-HALLUCINATION — PRIORITÉ ABSOLUE
═══════════════════════════════════════════════════

**RÈGLE 1 — CORPUS RAG (Si le message contient === CORPUS RÉGLEMENTAIRE === ou === ARTICLES CODE CIMA ===) :**
→ Cite le texte EXACTEMENT tel qu'il apparaît dans le corpus, entre guillemets.
→ Indique TOUJOURS la source : nom du texte + numéro d'article + pays.
→ N'invente AUCUN article, n'extrapole PAS au-delà de ce qui est écrit.
→ Si le corpus contient l'article demandé : tu dois reproduire le texte officiel mot pour mot, puis analyser.
→ Format : **Article X [Nom du texte, {pays_nom}]** : "texte exact" → [ANALYSE] ton commentaire.

**RÈGLE 2 — SOURCE PRINCIPALE = TA MÉMOIRE DE FORMATION (RAG = citation complémentaire) :**
→ Ta connaissance de formation (Claude/GPT) EST LA SOURCE PRIMAIRE. Tu réponds TOUJOURS avec ta connaissance des textes juridiques, fiscaux, comptables officiels.
→ Le corpus RAG (=== CORPUS RÉGLEMENTAIRE ===), QUAND IL EST PRÉSENT, est une source de citation officielle supplémentaire — utilise-le pour CITER mot pour mot avec références précises.
→ NE PAS attendre du RAG pour répondre : si aucun corpus n'est injecté, réponds quand même avec ta mémoire de formation.
→ MAIS marque systématiquement : `[Mémoire IA — vérifier la version officielle en vigueur]` pour toute affirmation sur articles/taux/barèmes non issus du corpus RAG injecté.
→ Cite le numéro d'article et le texte exact tel que tu le connais — c'est utile même avec la réserve.
→ Précise TOUJOURS la version/date si connue : "selon le Code du travail {pays_nom} (version estimée à la date de formation)"
→ JAMAIS de réponse vague type "selon la loi" sans citer l'article précis ou au minimum le chapitre concerné.

**RÈGLE 3 — COMPTABILITÉ (SYSCOHADA / IFRS / normes nationales) :**
→ Les réponses comptables DOIVENT référencer le plan comptable applicable : {cadre['comptable']}
→ Cite les numéros de comptes SYSCOHADA exacts (ex : "Compte 601 — Achats de marchandises")
→ Indique les journaux concernés (Achats, Ventes, Trésorerie, OD)
→ Précise les règles d'évaluation/amortissement applicables à {pays_nom}
→ Si SYSCOHADA ne s'applique pas ({pays_nom}) : utilise les normes indiquées ci-dessus.

**RÈGLE 4 — FISCALITÉ (CGI / TVA / IS) :**
→ Toute réponse fiscale doit préciser : le taux exact en vigueur à {pays_nom}, la base imposable, les exonérations éventuelles.
→ Cite l'article du CGI {pays_nom} concerné si tu le connais, avec `[Mémoire IA]` si non indexé.
→ Les taux et seuils : utilise ceux de {pays_nom} tels que définis dans {cadre['fiscal']}.
→ JAMAIS mélanger des taux d'un autre pays.

**RÈGLE 5 — DROIT DU TRAVAIL :**
→ Applique EXCLUSIVEMENT le {cadre['travail']}.
→ Les indemnités, préavis, congés payés doivent être calculés selon les barèmes de {pays_nom}.
→ Si la convention collective sectorielle s'applique, la mentionner.

**RÈGLE 6 — MONTANTS ET DEVISES :**
→ Tous les montants sont en {devise} sauf demande explicite de conversion.
→ Exemples concrets avec des montants réels en {devise.split('—')[0].strip()}.

**RÈGLE 7 — HORS AFRIQUE / PAYS NON AFRICAINS :**
→ Si l'utilisateur pose une question sur un autre pays (France, Belgique, etc.) :
→ Réponds normalement avec ta connaissance de formation — tu es compétent sur tous les systèmes juridiques.
→ Marque `[Hors corpus Yukpo — réponse mémoire IA]` pour rappeler que tu n'as pas de RAG spécifique à ce pays.

═══════════════════════════════════════════════════
  COMPORTEMENT ET STYLE
═══════════════════════════════════════════════════
▸ Ton niveau d'expertise : {ton_niveau}
▸ Langue principale      : {"anglais" if langue == "en" else "français"} professionnel
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

**AGENTS SPÉCIALISÉS (activés automatiquement) :**
DRH · Comptable · DAF · Banquier · Juriste · Commercial · DAA · Ingénieur · Microfinance · ONG · Douanier · CV/Emploi
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

            # 2. Recherche corpus réglementaire (OHADA, fiscal, travail…)
            # Priorité : TF-IDF cloud (toujours disponible) > sentence_transformers (local)
            try:
                from modules.rag.rag_tfidf_retriever import tfidf_retriever, rechercher_tfidf
                from modules.rag.rag_embedder import rag_embedder_manager
                metier_profil = getattr(profil, "metier", "") or ""

                # S'assurer que l'index TF-IDF est initialisé (démarre si besoin)
                if not tfidf_retriever.pret:
                    rag_embedder_manager._charger_modele()  # active le TF-IDF en background

                # Recherche via TF-IDF (mode cloud) ou sentence_transformers (mode local)
                _rag_fn = (
                    rechercher_tfidf if tfidf_retriever.pret
                    else None
                )
                if not _rag_fn and rag_embedder_manager.modele_pret:
                    from modules.rag.rag_retriever import rechercher_pour_metier, rechercher_corpus_reglementaire
                    _rag_fn = lambda q, **kw: (rechercher_pour_metier(q, metier_profil, pays) if metier_profil else rechercher_corpus_reglementaire(q, pays))  # noqa

                if _rag_fn is not None:
                    res_rag = await asyncio.wait_for(
                        asyncio.to_thread(
                            rechercher_tfidf if tfidf_retriever.pret else _rag_fn,
                            req.message,
                            pays=pays,
                            metier=metier_profil or None,
                        ) if tfidf_retriever.pret else asyncio.to_thread(_rag_fn, req.message),
                        timeout=6.0,
                    )
                    if res_rag:
                        parties_rag.append(res_rag)

            except asyncio.TimeoutError:
                logger.warning("[Copilote] RAG timeout (>6s)")
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
            if current_user.role in ("admin", "super_admin", "yukpo_owner"):
                ok, _credits, msg_credits = True, 0.0, "ok"
            else:
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
            "session_id":         session["session_id"],
            "reponse":            reponse_copilote,
            "agent_utilise":      agent_utilise,
            "resultat_agent":     resultat_agent,
            "nb_messages_session": len(session["messages"]),
            "profil_metier":      getattr(profil, "metier", None),
            "fichiers_generes":   fichiers_generes_copilote,
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
