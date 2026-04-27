"""
Bureau Transcripteur — Audio → Texte → Document professionnel.

Pipeline :
  1. Réception audio (WAV/MP3/M4A/WebM)
  2. Transcription via OpenAI Whisper API
  3. Claude reformate en document structuré (PV, rapport, lettre, etc.)
  4. Export .docx
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("yukpo_assurance.bureau.transcripteur")

FORMATS_AUDIO_ACCEPTES = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}

TYPES_DOCUMENT_CIBLE = {
    "pv_reunion": "Procès-verbal de réunion",
    "compte_rendu": "Compte rendu",
    "lettre": "Lettre professionnelle",
    "rapport": "Rapport",
    "dictee": "Texte dicté (mise en page simple)",
    "liste_taches": "Liste de tâches / notes d'action",
    "declaration": "Déclaration / déposition",
}


@dataclass
class ResultatTranscription:
    transcription_brute: str
    document_formate: str
    contenu_word: Optional[bytes] = None
    duree_secondes: Optional[float] = None
    langue_detectee: str = "fr"
    type_document: str = "texte"
    meta: dict = field(default_factory=dict)


async def transcrire_audio(
    audio_bytes: bytes,
    nom_fichier: str = "audio.wav",
    type_document_cible: str = "dictee",
    pays: str = "CM",
    informations_contexte: Optional[dict] = None,
) -> ResultatTranscription:
    """
    Transcrit un fichier audio via Whisper puis formate le texte via Claude.

    audio_bytes : contenu binaire du fichier audio
    type_document_cible : voir TYPES_DOCUMENT_CIBLE
    informations_contexte : infos supplémentaires pour guider Claude (participants, objet réunion…)
    """
    import openai
    from config.settings import settings
    from core.ia_client import ia_client, ModeIA

    # 1. Transcription Whisper
    openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = nom_fichier

    try:
        whisper_response = await openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="fr",
            response_format="verbose_json",
        )
        transcription_brute = whisper_response.text
        duree = getattr(whisper_response, "duration", None)
        langue = getattr(whisper_response, "language", "fr")
    except Exception as e:
        logger.error(f"[Transcripteur] Whisper échoué : {e}")
        raise RuntimeError(f"Transcription audio échouée : {e}")

    # 2. Formatage Claude
    type_label = TYPES_DOCUMENT_CIBLE.get(type_document_cible, "document")
    contexte_str = ""
    if informations_contexte:
        contexte_str = "\n".join(f"- {k} : {v}" for k, v in informations_contexte.items())
        contexte_str = f"\nCONTEXTE FOURNI :\n{contexte_str}\n"

    pays_noms = {
        "CM": "Cameroun", "SN": "Sénégal", "CI": "Côte d'Ivoire",
        "TG": "Togo", "BJ": "Bénin",
    }
    pays_nom = pays_noms.get(pays, "Cameroun")

    systeme = f"""Tu es expert en rédaction professionnelle pour l'Afrique francophone ({pays_nom}).
Tu transformes des transcriptions orales brutes en documents professionnels impeccables.
Corrige les répétitions, hésitations, phrases inachevées typiques du discours oral.
Respecte les conventions administratives locales ({pays_nom}).
Produis uniquement le document final, sans commentaire."""

    prompt = f"""Voici la transcription brute d'un enregistrement audio :

---
{transcription_brute}
---
{contexte_str}
OBJECTIF : Transforme cette transcription en {type_label} professionnel.
Instructions spécifiques selon le type :
- PV réunion : ordre du jour déduit, présents listés, résolutions numérotées
- Compte rendu : résumé structuré, faits marquants, suites à donner
- Lettre : respecter formules protocolaires africaines, objet clair
- Rapport : introduction, développement, conclusion, recommandations
- Dictée : reformuler en prose propre, corriger les faux départs et répétitions
- Liste tâches : bullet points numérotés avec responsable si mentionné

Produis le document complet en Markdown."""

    reponse = await ia_client.appeler(
        prompt=prompt,
        mode=ModeIA.REDACTION,
        systeme=systeme,
    )
    document_formate = reponse.contenu

    # 3. Export Word
    contenu_word: Optional[bytes] = None
    try:
        from modules.bureau.redacteur import _markdown_vers_docx
        contenu_word = _markdown_vers_docx(document_formate, type_label)
    except Exception as e:
        logger.warning(f"[Transcripteur] Export Word échoué : {e}")

    return ResultatTranscription(
        transcription_brute=transcription_brute,
        document_formate=document_formate,
        contenu_word=contenu_word,
        duree_secondes=duree,
        langue_detectee=langue,
        type_document=type_document_cible,
        meta={"tokens": reponse.tokens_total, "pays": pays},
    )
