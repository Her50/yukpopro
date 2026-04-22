"""
Bureau Rédaction — Routes FastAPI pour la génération de documents IA.

Endpoints :
  GET  /api/v1/bureau/redaction/types           — Liste des 30+ types de documents
  POST /api/v1/bureau/redaction/generer         — Génère un document (JSON → Markdown + .docx)
  POST /api/v1/bureau/redaction/reformuler      — Reformule un texte dans un registre donné
  POST /api/v1/bureau/redaction/calculer-prix   — Calcule le prix FCFA d'un document
  GET  /api/v1/bureau/redaction/historique      — Historique des docs générés (auth requise)
"""
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.bureau_redaction")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─── Schémas ──────────────────────────────────────────────────────────────────

class DemandeGeneration(BaseModel):
    type_doc: str = Field(..., description="Clé du type de document (ex: lettre_administrative)")
    informations: dict = Field(
        default_factory=dict,
        description="Champs du document : destinataire, objet, date, montant, etc.",
        examples=[{"destinataire": "M. le Directeur Général", "objet": "Demande de congé", "duree": "15 jours"}],
    )
    pays: str = Field(default="CM", description="Code pays : CM SN CI TG BJ CG GA RDC BF ML NE")
    reformuler_texte: Optional[str] = Field(None, description="Texte existant à reformuler (si fourni, 'informations' optionnel)")
    style_supplementaire: Optional[str] = Field(None, description="Instructions de style additionnelles")


class DemandeReformulation(BaseModel):
    texte: str = Field(..., min_length=10, description="Texte à reformuler")
    registre: str = Field(
        default="admin",
        description="Registre cible : admin | juridique | commercial | academique | simple",
    )
    pays: str = Field(default="CM")


class DemandePrix(BaseModel):
    type_doc: str
    nb_mots_estime: int = Field(default=300, ge=50, le=10000)


class ReponseDocument(BaseModel):
    titre: str
    contenu_markdown: str
    type_doc: str
    prix_fcfa: int
    nb_mots: int
    a_fichier_word: bool
    fichier_id: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/types", tags=["Bureau — Rédaction"])
async def lister_types():
    """Retourne le catalogue complet des types de documents disponibles."""
    from modules.bureau.redacteur import TYPES_DOCUMENTS, CATEGORIES
    return {
        "types": [
            {
                "cle": cle,
                "label": info["label"],
                "categorie": info["categorie"],
                "complexite": info["complexite"],
                "prix_base_fcfa": info["prix_base_fcfa"],
                "description": info["description"],
            }
            for cle, info in TYPES_DOCUMENTS.items()
        ],
        "categories": CATEGORIES,
        "total": len(TYPES_DOCUMENTS),
    }


@router.post("/generer", tags=["Bureau — Rédaction"])
async def generer_document(
    demande: DemandeGeneration,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Génère un document professionnel adapté à l'Afrique francophone.
    Retourne le contenu Markdown + (si python-docx disponible) le fichier .docx en base64.
    """
    from modules.bureau.redacteur import generer_document as _generer, DemandeDocument
    import base64

    try:
        req = DemandeDocument(
            type_doc=demande.type_doc,
            informations=demande.informations,
            pays=demande.pays,
            reformuler_texte=demande.reformuler_texte,
            style_supplementaire=demande.style_supplementaire,
            user_id=current_user.user_id,
        )
        doc = await _generer(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Bureau Rédaction] Erreur génération : {e}")
        raise HTTPException(status_code=500, detail=f"Génération échouée : {e}")

    fichier_id = None
    word_b64 = None
    if doc.contenu_word:
        fichier_id = f"bureau_doc_{current_user.user_id}_{demande.type_doc}_{int(__import__('time').time())}.docx"
        chemin = _DATA_DIR / fichier_id
        chemin.write_bytes(doc.contenu_word)
        word_b64 = base64.b64encode(doc.contenu_word).decode()

    return {
        "titre": doc.titre,
        "contenu_markdown": doc.contenu_markdown,
        "type_doc": doc.type_doc,
        "prix_fcfa": doc.prix_fcfa,
        "nb_mots": doc.nb_mots,
        "a_fichier_word": bool(doc.contenu_word),
        "fichier_id": fichier_id,
        "word_base64": word_b64,
        "meta": doc.meta,
    }


@router.post("/reformuler", tags=["Bureau — Rédaction"])
async def reformuler_texte(
    demande: DemandeReformulation,
    current_user: TokenData = Depends(get_current_user),
):
    """Reformule un texte dans le registre administratif/juridique/commercial africain."""
    from modules.bureau.redacteur import reformuler_texte as _reformuler

    registres_valides = {"admin", "juridique", "commercial", "academique", "simple"}
    if demande.registre not in registres_valides:
        raise HTTPException(status_code=400, detail=f"Registre invalide. Valides : {registres_valides}")

    try:
        resultat = await _reformuler(demande.texte, demande.registre, demande.pays)
    except Exception as e:
        logger.error(f"[Bureau Reformulation] Erreur : {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "texte_original": demande.texte,
        "texte_reformule": resultat,
        "registre": demande.registre,
        "pays": demande.pays,
    }


@router.post("/calculer-prix", tags=["Bureau — Rédaction"])
async def calculer_prix(demande: DemandePrix):
    """Calcule le prix estimé en FCFA pour un type de document et une longueur donnée."""
    from modules.bureau.redacteur import calculer_prix as _prix, TYPES_DOCUMENTS

    if demande.type_doc not in TYPES_DOCUMENTS:
        raise HTTPException(status_code=404, detail=f"Type inconnu : {demande.type_doc}")

    prix = _prix(demande.type_doc, demande.nb_mots_estime)
    info = TYPES_DOCUMENTS[demande.type_doc]
    return {
        "type_doc": demande.type_doc,
        "label": info["label"],
        "prix_fcfa": prix,
        "nb_mots_estime": demande.nb_mots_estime,
        "complexite": info["complexite"],
    }


@router.get("/fichier/{fichier_id}", tags=["Bureau — Rédaction"])
async def telecharger_document(
    fichier_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Télécharge un document Word précédemment généré."""
    # Validation anti path traversal
    if "/" in fichier_id or "\\" in fichier_id or ".." in fichier_id:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")

    chemin = _DATA_DIR / fichier_id
    if not chemin.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    # Vérification appartenance (fichier_id contient user_id)
    if f"_{current_user.user_id}_" not in fichier_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    return Response(
        content=chemin.read_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fichier_id}"'},
    )
