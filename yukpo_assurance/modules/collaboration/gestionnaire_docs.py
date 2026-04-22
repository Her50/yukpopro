"""
YukpoAssurance — Module Collaboration
Gestion documentaire avec versioning, workflows d'approbation hiérarchique,
annotations, notifications temps réel via WebSocket.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any

logger = logging.getLogger("yukpo_assurance.collaboration")

# ─── Gestion WebSocket (connexions actives par utilisateur) ───────────────────

class GestionnaireConnexions:
    """Registre des connexions WebSocket actives par user_id et compagnie_id."""

    def __init__(self):
        # {compagnie_id: {user_id: [WebSocket, ...]}}
        self._connexions: Dict[int, Dict[int, List[Any]]] = {}

    async def connecter(self, websocket, user_id: int, compagnie_id: int):
        self._connexions.setdefault(compagnie_id, {}).setdefault(user_id, []).append(websocket)
        logger.info(f"[WS] User {user_id} connecté (compagnie {compagnie_id})")

    async def deconnecter(self, websocket, user_id: int, compagnie_id: int):
        conns = self._connexions.get(compagnie_id, {}).get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info(f"[WS] User {user_id} déconnecté")

    async def envoyer_a_user(self, user_id: int, compagnie_id: int, message: dict):
        """Envoie un message JSON à toutes les connexions d'un utilisateur."""
        import json
        conns = self._connexions.get(compagnie_id, {}).get(user_id, [])
        mortes = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                mortes.append(ws)
        for ws in mortes:
            conns.remove(ws)

    async def diffuser_compagnie(self, compagnie_id: int, message: dict, exclure_user: Optional[int] = None):
        """Diffuse un message à tous les utilisateurs connectés d'une compagnie."""
        for user_id, conns in self._connexions.get(compagnie_id, {}).items():
            if user_id == exclure_user:
                continue
            for ws in conns:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass


# Instance globale
gestionnaire_ws = GestionnaireConnexions()


# ─── Logique de workflow d'approbation ────────────────────────────────────────

TYPES_DOCUMENT = [
    "contrat_travail", "avenant", "note_de_service", "rapport", "devis",
    "bon_de_commande", "bulletin_paie", "attestation", "courrier_officiel",
    "procedure_interne", "rapport_sinistre", "bordereau", "quittance",
    "rapport_conformite_cima", "pv_reunion", "autre",
]

ETAPES_WORKFLOW = {
    "simple":    ["auteur → valideur"],
    "standard":  ["auteur → manager → valideur_final"],
    "complet":   ["auteur → manager → daf → dg"],
    "juridique": ["auteur → juriste → manager → dg"],
}

def determiner_workflow(type_document: str, montant: float = 0) -> str:
    """Détermine le niveau de workflow selon le type et les enjeux financiers."""
    if type_document in ("rapport_conformite_cima", "contrat_travail"):
        return "complet"
    if type_document in ("devis", "bon_de_commande") and montant > 1_000_000:
        return "complet"
    if type_document in ("devis", "bon_de_commande") and montant > 100_000:
        return "standard"
    if type_document in ("bulletin_paie", "bordereau"):
        return "standard"
    return "simple"


def creer_etapes_workflow(
    type_workflow: str,
    approbateurs: List[dict],  # [{"user_id": ..., "nom": ..., "role": ...}]
) -> List[dict]:
    """Génère les étapes d'approbation pour un document."""
    etapes = []
    for i, approbateur in enumerate(approbateurs):
        etapes.append({
            "etape": i + 1,
            "approbateur_id": approbateur["user_id"],
            "approbateur_nom": approbateur["nom"],
            "approbateur_role": approbateur.get("role", "manager"),
            "statut": "en_attente" if i == 0 else "bloquee",
            "commentaire": None,
            "date_action": None,
        })
    return etapes


def etape_suivante(etapes: List[dict]) -> Optional[dict]:
    """Retourne la prochaine étape en attente, ou None si toutes approuvées."""
    for e in etapes:
        if e["statut"] == "en_attente":
            return e
        if e["statut"] == "rejete":
            return None
    return None


def document_entierement_approuve(etapes: List[dict]) -> bool:
    return all(e["statut"] == "approuve" for e in etapes)


# ─── Génération de référence document ─────────────────────────────────────────

def generer_reference_document(type_document: str, compagnie_id: int) -> str:
    annee = datetime.utcnow().year
    mois = datetime.utcnow().month
    uid = str(uuid.uuid4())[:8].upper()
    prefix = type_document[:3].upper()
    return f"{prefix}-{compagnie_id:03d}-{annee}{mois:02d}-{uid}"


# ─── Historique de versions ───────────────────────────────────────────────────

def creer_entree_historique(action: str, auteur_nom: str, commentaire: str = "") -> dict:
    return {
        "date": datetime.utcnow().isoformat(),
        "action": action,
        "auteur": auteur_nom,
        "commentaire": commentaire,
    }


logger.info("[Collaboration] Module Collaboration initialisé")
