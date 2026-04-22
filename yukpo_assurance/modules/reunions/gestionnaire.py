"""
YukpoAssurance — Gestionnaire de réunions IA
Outil complet pour les réunions professionnelles dans les compagnies d'assurance :
- Transcription audio en temps réel (Whisper)
- Synthèse intelligente des discussions
- Extraction automatique des décisions et actions
- Génération du PV / compte-rendu officiel
- Proposition d'agenda à partir de la réunion précédente
- Suivi des actions (qui fait quoi, avant quelle date)
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from core.ia_client import ModeIA, ia_client
from modules.documents.generateur import DocumentGenerateur

logger = logging.getLogger("yukpo_assurance.reunions")


@dataclass
class ParticipantReunion:
    nom: str
    poste: str
    present: bool = True
    procuration: Optional[str] = None  # nom de la personne représentée


@dataclass
class ActionReunion:
    """Action / tâche décidée en réunion"""
    responsable: str
    description: str
    echeance: Optional[date]
    statut: str = "en_attente"  # "en_attente" | "en_cours" | "réalisé" | "reporté"
    priorite: str = "normale"   # "urgente" | "normale" | "faible"


@dataclass
class Reunion:
    """Réunion complète avec tout son contexte"""
    reunion_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    titre: str = ""
    type_reunion: str = "ordinaire"  # "CA" | "CODIR" | "technique" | "sinistres" | "ordinaire"
    date_reunion: date = field(default_factory=date.today)
    heure_debut: Optional[str] = None
    heure_fin: Optional[str] = None
    lieu: str = ""
    president_seance: str = ""
    participants: list[ParticipantReunion] = field(default_factory=list)
    ordre_du_jour: list[str] = field(default_factory=list)
    audio_b64: Optional[str] = None           # Audio si enregistrement
    transcription_brute: Optional[str] = None  # Texte transcrit
    notes_manuelles: Optional[str] = None      # Notes prises pendant la réunion
    synthese: Optional[str] = None
    decisions: list[str] = field(default_factory=list)
    actions: list[ActionReunion] = field(default_factory=list)
    points_reportes: list[str] = field(default_factory=list)
    pv_genere: Optional[dict] = None           # Fichier PV généré
    statut: str = "en_cours"                   # "en_cours" | "terminée" | "pv_validé"


# Cache RAM (source de vérité en production = DB)
_reunions: dict[str, Reunion] = {}


async def _persister_reunion(reunion: "Reunion") -> None:
    """Sauvegarde ou met à jour une réunion en DB (fire-and-forget)."""
    try:
        from core.database import async_session_maker, ReunionDB, ActionReunionDB
        from sqlalchemy import select
        async with async_session_maker() as db:
            result = await db.execute(
                select(ReunionDB).where(ReunionDB.id == reunion.reunion_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = ReunionDB(id=reunion.reunion_id)
                db.add(row)
            row.titre = reunion.titre
            row.type_reunion = reunion.type_reunion
            row.lieu = reunion.lieu
            row.president_seance = reunion.president_seance
            row.statut = reunion.statut
            row.ordre_du_jour = reunion.ordre_du_jour
            row.participants = [
                {"nom": p.nom, "poste": p.poste, "present": p.present, "procuration": p.procuration}
                for p in reunion.participants
            ]
            row.transcription = reunion.transcription_brute
            row.notes_manuelles = reunion.notes_manuelles
            row.synthese = reunion.synthese
            row.decisions = reunion.decisions
            row.points_reportes = reunion.points_reportes
            row.date_reunion = datetime.combine(reunion.date_reunion, datetime.min.time()) if isinstance(reunion.date_reunion, date) else reunion.date_reunion
            row.mise_a_jour = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
            # Remplacer les actions
            await db.execute(
                __import__("sqlalchemy", fromlist=["delete"]).delete(ActionReunionDB).where(
                    ActionReunionDB.reunion_id == reunion.reunion_id
                )
            )
            for action in reunion.actions:
                db.add(ActionReunionDB(
                    reunion_id=reunion.reunion_id,
                    responsable=action.responsable,
                    description=action.description,
                    echeance=datetime.combine(action.echeance, datetime.min.time()) if action.echeance else None,
                    statut=action.statut,
                    priorite=action.priorite,
                ))
            await db.commit()
    except Exception as e:
        logger.warning(f"[Réunions] Persistance DB échouée (non critique): {e}")


async def charger_reunions_depuis_db(limite: int = 100) -> None:
    """Charge les réunions récentes depuis la DB dans le cache RAM au démarrage."""
    global _reunions
    try:
        from core.database import async_session_maker, ReunionDB, ActionReunionDB
        from sqlalchemy import select, desc
        from sqlalchemy.orm import selectinload
        async with async_session_maker() as db:
            result = await db.execute(
                select(ReunionDB)
                .options(selectinload(ReunionDB.actions))
                .order_by(desc(ReunionDB.date_reunion))
                .limit(limite)
            )
            rows = result.scalars().all()
            for row in rows:
                r = Reunion(
                    reunion_id=row.id,
                    titre=row.titre,
                    type_reunion=row.type_reunion,
                    lieu=row.lieu or "",
                    president_seance=row.president_seance or "",
                    statut=row.statut,
                    ordre_du_jour=row.ordre_du_jour or [],
                    participants=[
                        ParticipantReunion(
                            nom=p["nom"], poste=p["poste"],
                            present=p.get("present", True),
                            procuration=p.get("procuration"),
                        )
                        for p in (row.participants or [])
                    ],
                    transcription_brute=row.transcription,
                    notes_manuelles=row.notes_manuelles,
                    synthese=row.synthese,
                    decisions=row.decisions or [],
                    points_reportes=row.points_reportes or [],
                    date_reunion=row.date_reunion.date() if row.date_reunion else date.today(),
                    actions=[
                        ActionReunion(
                            responsable=a.responsable,
                            description=a.description,
                            echeance=a.echeance.date() if a.echeance else None,
                            statut=a.statut,
                            priorite=a.priorite,
                        )
                        for a in (row.actions or [])
                    ],
                )
                _reunions[r.reunion_id] = r
        logger.info(f"[Réunions] {len(rows)} réunions chargées depuis la DB")
    except Exception as e:
        logger.warning(f"[Réunions] Chargement DB échoué (non critique): {e}")


class GestionnaireReunions:
    """
    Gestionnaire complet de réunions pour compagnies d'assurance.

    Flux d'une réunion :
    1. Création avec ordre du jour
    2. Enregistrement audio OU saisie de notes pendant la réunion
    3. Transcription automatique (Whisper si audio)
    4. Analyse IA : synthèse, décisions, actions à suivre
    5. Génération du PV officiel (Word ou PDF)
    6. Proposition agenda réunion suivante
    7. Suivi des actions jusqu'à leur réalisation
    """

    def __init__(self):
        self._gen = DocumentGenerateur()

    # ──────────────────────────────────────────────────────────────
    # GESTION DES RÉUNIONS
    # ──────────────────────────────────────────────────────────────

    def creer_reunion(
        self,
        titre: str,
        type_reunion: str = "ordinaire",
        ordre_du_jour: Optional[list[str]] = None,
        participants: Optional[list[dict]] = None,
        lieu: str = "",
        president_seance: str = "",
    ) -> Reunion:
        reunion = Reunion(
            titre=titre,
            type_reunion=type_reunion,
            ordre_du_jour=ordre_du_jour or [],
            lieu=lieu,
            president_seance=president_seance,
            participants=[
                ParticipantReunion(**p) for p in (participants or [])
            ],
        )
        _reunions[reunion.reunion_id] = reunion
        logger.info(f"[Réunions] Créée: {reunion.reunion_id} — {titre}")
        import asyncio
        asyncio.ensure_future(_persister_reunion(reunion))
        return reunion

    def get_reunion(self, reunion_id: str) -> Optional[Reunion]:
        return _reunions.get(reunion_id)

    def lister_reunions(self) -> list[dict]:
        return [
            {
                "reunion_id": r.reunion_id,
                "titre": r.titre,
                "date": r.date_reunion.isoformat(),
                "type": r.type_reunion,
                "statut": r.statut,
                "nb_actions": len(r.actions),
                "actions_en_attente": len([a for a in r.actions if a.statut == "en_attente"]),
            }
            for r in sorted(_reunions.values(), key=lambda x: x.date_reunion, reverse=True)
        ]

    # ──────────────────────────────────────────────────────────────
    # TRANSCRIPTION & ANALYSE IA
    # ──────────────────────────────────────────────────────────────

    async def transcrire_audio(self, reunion_id: str, audio_b64: str, mime: str = "audio/mp4") -> str:
        """Transcrit l'audio de la réunion via Whisper"""
        reunion = self.get_reunion(reunion_id)
        if not reunion:
            raise ValueError(f"Réunion {reunion_id} introuvable")

        logger.info(f"[Réunions] Transcription audio réunion {reunion_id}")

        try:
            import base64
            import openai
            from config.settings import settings

            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            audio_bytes = base64.b64decode(audio_b64)

            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=(f"reunion_{reunion_id}.mp4", audio_bytes, mime),
                language="fr",
                response_format="text",
            )

            reunion.transcription_brute = transcription
            reunion.audio_b64 = audio_b64
            logger.info(f"[Réunions] Transcription OK: {len(transcription)} caractères")
            return transcription

        except Exception as e:
            logger.error(f"[Réunions] Erreur transcription: {e}")
            raise

    async def analyser_reunion(self, reunion_id: str) -> dict:
        """
        Analyse complète de la réunion :
        - Synthèse des discussions
        - Extraction des décisions
        - Liste des actions avec responsables et échéances
        - Points non résolus à reporter
        """
        reunion = self.get_reunion(reunion_id)
        if not reunion:
            raise ValueError(f"Réunion {reunion_id} introuvable")

        contenu_reunion = reunion.transcription_brute or reunion.notes_manuelles
        if not contenu_reunion:
            raise ValueError("Aucun contenu à analyser (ni transcription, ni notes)")

        participants_str = ", ".join(
            f"{p.nom} ({p.poste})" for p in reunion.participants if p.present
        )
        odj_str = "\n".join(f"{i+1}. {point}" for i, point in enumerate(reunion.ordre_du_jour))

        prompt = f"""Tu es le secrétaire de séance d'une compagnie d'assurance en zone CIMA.

Analyse le compte-rendu de cette réunion et extrais les informations structurées.

RÉUNION : {reunion.titre}
TYPE : {reunion.type_reunion}
DATE : {reunion.date_reunion}
LIEU : {reunion.lieu}
PRÉSIDENT DE SÉANCE : {reunion.president_seance}
PARTICIPANTS : {participants_str}

ORDRE DU JOUR :
{odj_str}

CONTENU DE LA RÉUNION (transcription / notes) :
{contenu_reunion}

Retourne UNIQUEMENT ce JSON :
{{
  "synthese": "résumé exécutif en 3-5 phrases des points clés discutés",
  "points_traites": [
    {{"point": "intitulé du point ODJ", "resume": "résumé de la discussion", "conclusion": ""}}
  ],
  "decisions": [
    "Décision 1 prise formellement",
    "Décision 2..."
  ],
  "actions": [
    {{
      "responsable": "NOM Prénom",
      "description": "Action à réaliser",
      "echeance": "JJ/MM/AAAA ou null",
      "priorite": "urgente|normale|faible"
    }}
  ],
  "points_reportes": [
    "Point qui n'a pas été traité et doit passer à la prochaine réunion"
  ],
  "date_prochaine_reunion_suggeree": "JJ/MM/AAAA ou null",
  "duree_estimee_prochaine": "1h|2h|demi-journée",
  "observations": "observations générales du secrétaire"
}}
"""
        reponse = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.PRECISION,
            json_attendu=True,
        )

        data = reponse.as_json()

        # Mise à jour de la réunion
        reunion.synthese = data.get("synthese", "")
        reunion.decisions = data.get("decisions", [])
        reunion.points_reportes = data.get("points_reportes", [])
        reunion.actions = [
            ActionReunion(
                responsable=a.get("responsable", ""),
                description=a.get("description", ""),
                echeance=self._parse_date(a.get("echeance")),
                priorite=a.get("priorite", "normale"),
            )
            for a in data.get("actions", [])
        ]

        logger.info(
            f"[Réunions] Analyse OK: {len(reunion.decisions)} décisions, "
            f"{len(reunion.actions)} actions"
        )
        import asyncio
        asyncio.ensure_future(_persister_reunion(reunion))

        return {
            "reunion_id": reunion_id,
            "synthese": reunion.synthese,
            "decisions": reunion.decisions,
            "actions": [
                {
                    "responsable": a.responsable,
                    "description": a.description,
                    "echeance": a.echeance.isoformat() if a.echeance else None,
                    "priorite": a.priorite,
                    "statut": a.statut,
                }
                for a in reunion.actions
            ],
            "points_reportes": reunion.points_reportes,
            "date_prochaine_suggeree": data.get("date_prochaine_reunion_suggeree"),
            "observations": data.get("observations", ""),
        }

    # ──────────────────────────────────────────────────────────────
    # GÉNÉRATION DE DOCUMENTS
    # ──────────────────────────────────────────────────────────────

    async def generer_pv(
        self, reunion_id: str, format: str = "docx"
    ) -> Optional[dict]:
        """Génère le procès-verbal officiel de la réunion"""
        reunion = self.get_reunion(reunion_id)
        if not reunion or not reunion.synthese:
            raise ValueError("Réunion non analysée — lancez d'abord analyser_reunion()")

        participants_table = [
            [p.nom, p.poste, "Présent" if p.present else f"Excusé ({p.procuration or 'N/A'})"]
            for p in reunion.participants
        ]

        actions_table = [
            [
                a.responsable,
                a.description,
                a.echeance.isoformat() if a.echeance else "À définir",
                a.priorite.upper(),
                a.statut,
            ]
            for a in reunion.actions
        ]

        outline = {
            "document_type": format,
            "title": f"Procès-Verbal — {reunion.titre}",
            "subtitle": f"Réunion du {reunion.date_reunion.strftime('%d/%m/%Y')}",
            "author": f"Secrétaire de séance — YukpoAssurance",
            "theme": "blue",
            "sections": [
                {
                    "heading": "1. Informations Générales",
                    "level": 1,
                    "paragraphs": [
                        f"Date : {reunion.date_reunion.strftime('%d %B %Y')}",
                        f"Heure : {reunion.heure_debut or 'N/A'} – {reunion.heure_fin or 'N/A'}",
                        f"Lieu : {reunion.lieu or 'Siège social'}",
                        f"Président de séance : {reunion.president_seance}",
                        f"Type : {reunion.type_reunion.upper()}",
                    ],
                },
                {
                    "heading": "2. Participants",
                    "level": 1,
                    "table": {
                        "headers": ["Nom & Prénom", "Fonction", "Présence"],
                        "rows": participants_table,
                    },
                },
                {
                    "heading": "3. Ordre du Jour",
                    "level": 1,
                    "bullets": reunion.ordre_du_jour,
                },
                {
                    "heading": "4. Synthèse des Discussions",
                    "level": 1,
                    "paragraphs": [reunion.synthese],
                },
                {
                    "heading": "5. Décisions Prises",
                    "level": 1,
                    "bullets": reunion.decisions or ["Aucune décision formelle prise lors de cette séance"],
                },
                {
                    "heading": "6. Actions à Suivre",
                    "level": 1,
                    "table": {
                        "headers": ["Responsable", "Action", "Échéance", "Priorité", "Statut"],
                        "rows": actions_table or [["N/A", "Aucune action définie", "N/A", "N/A", "N/A"]],
                    },
                },
                {
                    "heading": "7. Points Reportés",
                    "level": 1,
                    "bullets": reunion.points_reportes or ["Tous les points de l'ordre du jour ont été traités"],
                },
                {
                    "heading": "8. Clôture",
                    "level": 1,
                    "paragraphs": [
                        f"La séance est levée à {reunion.heure_fin or 'N/A'}.",
                        "Le présent procès-verbal a été rédigé par YukpoAssurance et sera soumis à validation.",
                        f"Date de la prochaine réunion : À confirmer",
                    ],
                },
            ],
        }

        pv = await self._gen.generer(outline)
        if pv:
            reunion.pv_genere = pv
            reunion.statut = "terminée"
        return pv

    async def proposer_agenda_prochain(self, reunion_id: str) -> dict:
        """
        Propose l'agenda de la prochaine réunion basé sur :
        - Points reportés de la réunion actuelle
        - Actions en retard ou urgentes
        - Contexte réglementaire CIMA (échéances)
        """
        reunion = self.get_reunion(reunion_id)
        if not reunion:
            raise ValueError(f"Réunion {reunion_id} introuvable")

        from modules.cima.code_cima_engine import cima_engine
        echeances = cima_engine._prochaines_echeances()

        actions_urgentes = [
            f"{a.description} (resp. {a.responsable})"
            for a in reunion.actions
            if a.priorite == "urgente" and a.statut == "en_attente"
        ]

        prompt = f"""Tu es le secrétaire général d'une compagnie d'assurance en zone CIMA.

Propose un ordre du jour structuré pour la prochaine réunion de type "{reunion.type_reunion}"
basé sur les éléments suivants :

POINTS REPORTÉS DE LA RÉUNION PRÉCÉDENTE :
{chr(10).join(reunion.points_reportes) or "Aucun"}

ACTIONS URGENTES EN ATTENTE :
{chr(10).join(actions_urgentes) or "Aucune"}

PROCHAINES ÉCHÉANCES RÉGLEMENTAIRES CIMA :
{chr(10).join(f"- {e['echeance']} : {e['obligation']}" for e in echeances[:4])}

DÉCISIONS PRÉCÉDENTES À SUIVRE :
{chr(10).join(reunion.decisions[:3]) if reunion.decisions else "Aucune"}

Retourne ce JSON :
{{
  "titre_reunion": "...",
  "type": "{reunion.type_reunion}",
  "duree_estimee": "1h30|2h|demi-journée",
  "ordre_du_jour": [
    {{"numero": 1, "point": "...", "duree_estimee": "15min", "responsable": "...", "priorite": "urgente|normale"}}
  ],
  "documents_a_preparer": ["..."],
  "participants_suggeres": ["..."],
  "notes_preparatoires": "..."
}}
"""
        reponse = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.REDACTION,
            json_attendu=True,
        )

        agenda_data = reponse.as_json()

        # Génération du document agenda
        agenda_doc = await self._generer_document_agenda(agenda_data, reunion)

        return {
            "agenda": agenda_data,
            "document_agenda": agenda_doc,
            "reunion_precedente": reunion_id,
        }

    async def _generer_document_agenda(self, agenda: dict, reunion_precedente: Reunion) -> Optional[dict]:
        """Génère un document Word de convocation / ordre du jour"""
        points_odj = agenda.get("ordre_du_jour", [])
        outline = {
            "document_type": "docx",
            "title": f"Convocation & Ordre du Jour — {agenda.get('titre_reunion', 'Prochaine Réunion')}",
            "subtitle": f"Suite à la réunion du {reunion_precedente.date_reunion.strftime('%d/%m/%Y')}",
            "author": "Direction Générale — YukpoAssurance",
            "theme": "blue",
            "sections": [
                {
                    "heading": "Objet de la réunion",
                    "level": 1,
                    "paragraphs": [
                        f"Type : {agenda.get('type', 'Ordinaire')}",
                        f"Durée estimée : {agenda.get('duree_estimee', '2h')}",
                        f"Participants suggérés : {', '.join(agenda.get('participants_suggeres', []))}",
                    ],
                },
                {
                    "heading": "Ordre du Jour",
                    "level": 1,
                    "table": {
                        "headers": ["N°", "Point", "Durée", "Responsable", "Priorité"],
                        "rows": [
                            [str(p.get("numero", i+1)), p.get("point", ""), p.get("duree_estimee", ""), p.get("responsable", ""), p.get("priorite", "normale")]
                            for i, p in enumerate(points_odj)
                        ],
                    },
                },
                {
                    "heading": "Documents à préparer",
                    "level": 1,
                    "bullets": agenda.get("documents_a_preparer", ["Aucun document spécifique"]),
                },
                {
                    "heading": "Notes préparatoires",
                    "level": 1,
                    "paragraphs": [agenda.get("notes_preparatoires", "")],
                },
            ],
        }
        return await self._gen.generer(outline)

    # ──────────────────────────────────────────────────────────────
    # SUIVI DES ACTIONS
    # ──────────────────────────────────────────────────────────────

    def tableau_actions(self) -> dict:
        """Vue consolidée de toutes les actions en cours sur toutes les réunions"""
        toutes_actions = []
        for reunion in _reunions.values():
            for action in reunion.actions:
                en_retard = (
                    action.echeance
                    and action.echeance < date.today()
                    and action.statut == "en_attente"
                )
                toutes_actions.append({
                    "reunion_titre": reunion.titre,
                    "reunion_date": reunion.date_reunion.isoformat(),
                    "responsable": action.responsable,
                    "description": action.description,
                    "echeance": action.echeance.isoformat() if action.echeance else None,
                    "priorite": action.priorite,
                    "statut": action.statut,
                    "en_retard": en_retard,
                })

        urgentes = [a for a in toutes_actions if a["priorite"] == "urgente" and a["statut"] != "réalisé"]
        en_retard = [a for a in toutes_actions if a["en_retard"]]

        return {
            "total_actions": len(toutes_actions),
            "en_attente": len([a for a in toutes_actions if a["statut"] == "en_attente"]),
            "en_cours": len([a for a in toutes_actions if a["statut"] == "en_cours"]),
            "realisees": len([a for a in toutes_actions if a["statut"] == "réalisé"]),
            "urgentes": urgentes,
            "en_retard": en_retard,
            "toutes": toutes_actions,
        }

    def mettre_a_jour_action(
        self, reunion_id: str, index_action: int, nouveau_statut: str
    ) -> bool:
        reunion = self.get_reunion(reunion_id)
        if not reunion or index_action >= len(reunion.actions):
            return False
        reunion.actions[index_action].statut = nouveau_statut
        import asyncio
        asyncio.ensure_future(_persister_reunion(reunion))
        return True

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        if not date_str:
            return None
        try:
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        except Exception:
            pass
        return None


# Instance singleton
gestionnaire_reunions = GestionnaireReunions()
