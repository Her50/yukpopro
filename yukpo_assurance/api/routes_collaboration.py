"""
YukpoAssurance — Routes API Collaboration
Gestion documentaire : versioning, workflows d'approbation, annotations, WebSocket temps réel.
"""
import base64
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData, _decoder_token
from core.database import (
    get_db, DocumentCollabDB, VersionDocDB,
    WorkflowApprovalDB, CommentaireDocDB, NotificationDB,
)
from modules.collaboration.gestionnaire_docs import (
    gestionnaire_ws, determiner_workflow, creer_etapes_workflow,
    etape_suivante, document_entierement_approuve,
    generer_reference_document, creer_entree_historique, TYPES_DOCUMENT,
)

router = APIRouter()


# ─── Modèles Pydantic ─────────────────────────────────────────────────────────

class DocumentCreate(BaseModel):
    titre: str
    type_document: str
    description: Optional[str] = None
    approbateurs: list = []   # [{user_id, nom, role}]
    montant_associe: float = 0

class VersionCreate(BaseModel):
    document_id: int
    contenu_b64: Optional[str] = None   # fichier encodé base64
    nom_fichier: Optional[str] = None
    texte_contenu: Optional[str] = None  # ou texte brut
    changelog: Optional[str] = None

class CommentaireCreate(BaseModel):
    document_id: int
    version_id: Optional[int] = None
    contenu: str
    page: Optional[int] = None

class DecisionApproval(BaseModel):
    decision: str   # "approuve" | "rejete" | "retour_corrections"
    commentaire: Optional[str] = None


# ─── DOCUMENTS ────────────────────────────────────────────────────────────────

@router.post("/documents", summary="Créer un document collaboratif")
async def creer_document(
    data: DocumentCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.type_document not in TYPES_DOCUMENT:
        raise HTTPException(400, f"Type invalide. Types disponibles : {TYPES_DOCUMENT}")

    type_workflow = determiner_workflow(data.type_document, data.montant_associe)
    etapes = creer_etapes_workflow(type_workflow, data.approbateurs) if data.approbateurs else []
    reference = generer_reference_document(data.type_document, current_user.compagnie_id)

    doc = DocumentCollabDB(
        compagnie_id=current_user.compagnie_id,
        reference=reference,
        titre=data.titre,
        type_document=data.type_document,
        description=data.description,
        auteur_id=current_user.user_id,
        auteur_nom=current_user.user_nom,
        statut="brouillon",
        version_courante=0,
        type_workflow=type_workflow,
        historique=[creer_entree_historique("Création", current_user.user_nom)],
    )
    db.add(doc)
    await db.flush()

    # Créer les étapes de workflow en DB
    for etape in etapes:
        wf = WorkflowApprovalDB(
            document_id=doc.id,
            compagnie_id=current_user.compagnie_id,
            **etape,
        )
        db.add(wf)

    await db.commit()
    await db.refresh(doc)

    # Notifier les approbateurs
    if etapes:
        premier_approbateur = etapes[0]
        await _notifier(
            db=db,
            user_id=premier_approbateur["approbateur_id"],
            compagnie_id=current_user.compagnie_id,
            type_notif="approbation_demandee",
            titre=f"Document à approuver : {data.titre}",
            message=f"{current_user.user_nom} demande votre approbation pour le document '{data.titre}'",
            document_id=doc.id,
        )

    return {"document_id": doc.id, "reference": reference, "type_workflow": type_workflow, "nb_etapes": len(etapes)}


@router.get("/documents", summary="Lister les documents")
async def lister_documents(
    statut: Optional[str] = None,
    type_document: Optional[str] = None,
    mes_documents: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(DocumentCollabDB).where(DocumentCollabDB.compagnie_id == current_user.compagnie_id)
    if statut:
        q = q.where(DocumentCollabDB.statut == statut)
    if type_document:
        q = q.where(DocumentCollabDB.type_document == type_document)
    if mes_documents:
        q = q.where(DocumentCollabDB.auteur_id == current_user.user_id)
    q = q.order_by(DocumentCollabDB.mise_a_jour.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return {"documents": [_doc_to_dict(d) for d in result.scalars().all()]}


@router.get("/documents/{document_id}", summary="Détail d'un document")
async def get_document(
    document_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(document_id, current_user.compagnie_id, db)

    # Versions
    q_v = select(VersionDocDB).where(VersionDocDB.document_id == document_id).order_by(VersionDocDB.numero_version.desc())
    versions = (await db.execute(q_v)).scalars().all()

    # Étapes workflow
    q_wf = select(WorkflowApprovalDB).where(WorkflowApprovalDB.document_id == document_id).order_by(WorkflowApprovalDB.etape)
    etapes = (await db.execute(q_wf)).scalars().all()

    # Commentaires
    q_c = select(CommentaireDocDB).where(CommentaireDocDB.document_id == document_id).order_by(CommentaireDocDB.cree_le)
    commentaires = (await db.execute(q_c)).scalars().all()

    return {
        **_doc_to_dict(doc),
        "versions": [_version_to_dict(v) for v in versions],
        "workflow": [_etape_to_dict(e) for e in etapes],
        "commentaires": [_commentaire_to_dict(c) for c in commentaires],
    }


# ─── VERSIONS ─────────────────────────────────────────────────────────────────

@router.post("/documents/{document_id}/versions", summary="Soumettre une nouvelle version")
async def nouvelle_version(
    document_id: int,
    data: VersionCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(document_id, current_user.compagnie_id, db)
    if doc.statut in ("approuve", "archive"):
        raise HTTPException(400, f"Document {doc.statut} — impossible d'ajouter une version")

    doc.version_courante = (doc.version_courante or 0) + 1
    doc.statut = "en_review"
    doc.mise_a_jour = datetime.utcnow()
    doc.historique = (doc.historique or []) + [
        creer_entree_historique(f"Version {doc.version_courante} soumise", current_user.user_nom, data.changelog or "")
    ]

    version = VersionDocDB(
        document_id=document_id,
        compagnie_id=current_user.compagnie_id,
        numero_version=doc.version_courante,
        contenu_b64=data.contenu_b64,
        texte_contenu=data.texte_contenu,
        nom_fichier=data.nom_fichier,
        changelog=data.changelog,
        auteur_id=current_user.user_id,
        auteur_nom=current_user.user_nom,
    )
    db.add(version)

    # Relancer les approbations en attente
    q_wf = select(WorkflowApprovalDB).where(
        and_(WorkflowApprovalDB.document_id == document_id, WorkflowApprovalDB.etape == 1)
    )
    premiere_etape = (await db.execute(q_wf)).scalar_one_or_none()
    if premiere_etape:
        premiere_etape.statut = "en_attente"
        # Remettre les autres étapes à "bloquee"
        q_rest = select(WorkflowApprovalDB).where(
            and_(WorkflowApprovalDB.document_id == document_id, WorkflowApprovalDB.etape > 1)
        )
        for e in (await db.execute(q_rest)).scalars().all():
            e.statut = "bloquee"

    await db.commit()
    await db.refresh(version)

    # Notifier les approbateurs
    if premiere_etape:
        await _notifier(
            db=db,
            user_id=premiere_etape.approbateur_id,
            compagnie_id=current_user.compagnie_id,
            type_notif="nouvelle_version",
            titre=f"Nouvelle version : {doc.titre}",
            message=f"Version {doc.version_courante} soumise par {current_user.user_nom}",
            document_id=document_id,
        )

    return {"version_id": version.id, "numero_version": doc.version_courante, "statut": doc.statut}


# ─── APPROBATIONS ─────────────────────────────────────────────────────────────

@router.post("/documents/{document_id}/approuver", summary="Approuver ou rejeter un document")
async def approuver_document(
    document_id: int,
    data: DecisionApproval,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.decision not in ("approuve", "rejete", "retour_corrections"):
        raise HTTPException(400, "Décision invalide")

    doc = await _get_doc_or_404(document_id, current_user.compagnie_id, db)

    # Trouver l'étape en attente assignée à cet utilisateur
    q_wf = select(WorkflowApprovalDB).where(
        and_(
            WorkflowApprovalDB.document_id == document_id,
            WorkflowApprovalDB.approbateur_id == current_user.user_id,
            WorkflowApprovalDB.statut == "en_attente",
        )
    )
    etape = (await db.execute(q_wf)).scalar_one_or_none()
    if not etape:
        raise HTTPException(403, "Vous n'avez pas d'étape en attente pour ce document")

    etape.statut = data.decision
    etape.commentaire = data.commentaire
    etape.date_action = datetime.utcnow()

    # Débloquer l'étape suivante ou finaliser
    if data.decision == "approuve":
        q_next = select(WorkflowApprovalDB).where(
            and_(WorkflowApprovalDB.document_id == document_id, WorkflowApprovalDB.etape == etape.etape + 1)
        )
        etape_suivante_db = (await db.execute(q_next)).scalar_one_or_none()
        if etape_suivante_db:
            etape_suivante_db.statut = "en_attente"
            # Notifier le prochain approbateur
            await _notifier(
                db=db,
                user_id=etape_suivante_db.approbateur_id,
                compagnie_id=current_user.compagnie_id,
                type_notif="approbation_demandee",
                titre=f"Document à approuver : {doc.titre}",
                message=f"Étape {etape_suivante_db.etape} — approbation de {current_user.user_nom} obtenue",
                document_id=document_id,
            )
        else:
            # Toutes les étapes approuvées
            doc.statut = "approuve"
            doc.historique = (doc.historique or []) + [
                creer_entree_historique("Document approuvé", current_user.user_nom, data.commentaire or "")
            ]
            # Notifier l'auteur
            await _notifier(
                db=db,
                user_id=doc.auteur_id,
                compagnie_id=current_user.compagnie_id,
                type_notif="document_approuve",
                titre=f"✅ Votre document a été approuvé",
                message=f"'{doc.titre}' a été approuvé par {current_user.user_nom}",
                document_id=document_id,
            )
    else:
        # Rejet ou retour corrections
        doc.statut = "rejete" if data.decision == "rejete" else "brouillon"
        doc.historique = (doc.historique or []) + [
            creer_entree_historique(
                "Retour corrections" if data.decision == "retour_corrections" else "Document rejeté",
                current_user.user_nom, data.commentaire or ""
            )
        ]
        # Notifier l'auteur
        await _notifier(
            db=db,
            user_id=doc.auteur_id,
            compagnie_id=current_user.compagnie_id,
            type_notif="document_rejete",
            titre=f"❌ Document {data.decision}" if data.decision == "rejete" else "🔁 Corrections demandées",
            message=f"{current_user.user_nom} : {data.commentaire or 'Sans commentaire'}",
            document_id=document_id,
        )

    doc.mise_a_jour = datetime.utcnow()
    await db.commit()

    return {
        "message": f"Document {data.decision}",
        "statut_document": doc.statut,
        "document_id": document_id,
    }


# ─── COMMENTAIRES ─────────────────────────────────────────────────────────────

@router.post("/documents/{document_id}/commentaires", summary="Ajouter un commentaire")
async def ajouter_commentaire(
    document_id: int,
    data: CommentaireCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(document_id, current_user.compagnie_id, db)
    commentaire = CommentaireDocDB(
        document_id=document_id,
        compagnie_id=current_user.compagnie_id,
        version_id=data.version_id,
        auteur_id=current_user.user_id,
        auteur_nom=current_user.user_nom,
        contenu=data.contenu,
        page=data.page,
    )
    db.add(commentaire)
    await db.commit()
    await db.refresh(commentaire)

    # Diffuser en temps réel à tous les collaborateurs de la compagnie
    await gestionnaire_ws.diffuser_compagnie(
        current_user.compagnie_id,
        {
            "type": "nouveau_commentaire",
            "document_id": document_id,
            "auteur": current_user.user_nom,
            "contenu": data.contenu[:100],
        },
        exclure_user=current_user.user_id,
    )

    return {"commentaire_id": commentaire.id, "message": "Commentaire ajouté"}


# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

@router.get("/notifications", summary="Mes notifications")
async def mes_notifications(
    non_lues: bool = True,
    skip: int = 0,
    limit: int = 50,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(NotificationDB).where(
        and_(NotificationDB.user_id == current_user.user_id, NotificationDB.compagnie_id == current_user.compagnie_id)
    )
    if non_lues:
        q = q.where(NotificationDB.lu == False)
    q = q.order_by(NotificationDB.cree_le.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    notifs = result.scalars().all()
    return {
        "notifications": [_notif_to_dict(n) for n in notifs],
        "total_non_lues": sum(1 for n in notifs if not n.lu),
    }


@router.patch("/notifications/{notif_id}/lue", summary="Marquer comme lue")
async def marquer_lue(
    notif_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(NotificationDB).where(
        and_(NotificationDB.id == notif_id, NotificationDB.user_id == current_user.user_id)
    )
    notif = (await db.execute(q)).scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification introuvable")
    notif.lu = True
    await db.commit()
    return {"message": "Notification marquée comme lue"}


@router.patch("/notifications/tout-lire", summary="Tout marquer comme lu")
async def tout_marquer_lu(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(NotificationDB).where(
        and_(NotificationDB.user_id == current_user.user_id, NotificationDB.lu == False)
    )
    notifs = (await db.execute(q)).scalars().all()
    for n in notifs:
        n.lu = True
    await db.commit()
    return {"message": f"{len(notifs)} notification(s) marquée(s) comme lues"}


# ─── WEBSOCKET ────────────────────────────────────────────────────────────────

@router.websocket("/ws/{compagnie_id}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    compagnie_id: int,
    user_id: int,
    token: Optional[str] = Query(None),
):
    """
    WebSocket pour les notifications temps réel.
    Connexion : ws://host/api/v1/collaboration/ws/{compagnie_id}/{user_id}?token=<jwt>
    """
    # Token JWT obligatoire — rejet immédiat si absent
    if not token:
        await websocket.close(code=4001)
        return
    try:
        td = _decoder_token(token)
        # user_id et compagnie_id doivent correspondre exactement au JWT
        if td.user_id != user_id or td.compagnie_id != compagnie_id:
            await websocket.close(code=4003)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    await gestionnaire_ws.connecter(websocket, user_id, compagnie_id)

    try:
        while True:
            data = await websocket.receive_text()
            # Heartbeat keep-alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await gestionnaire_ws.deconnecter(websocket, user_id, compagnie_id)


# ─── RÉFÉRENTIEL ─────────────────────────────────────────────────────────────

@router.get("/referentiel/types-documents")
async def types_documents(current_user: TokenData = Depends(get_current_user)):
    return {"types": TYPES_DOCUMENT}


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_doc_or_404(document_id: int, compagnie_id: int, db: AsyncSession) -> DocumentCollabDB:
    q = select(DocumentCollabDB).where(
        and_(DocumentCollabDB.id == document_id, DocumentCollabDB.compagnie_id == compagnie_id)
    )
    doc = (await db.execute(q)).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document introuvable")
    return doc


async def _notifier(db: AsyncSession, user_id: int, compagnie_id: int, type_notif: str,
                     titre: str, message: str, document_id: Optional[int] = None):
    """Crée une notification en DB et l'envoie en temps réel via WebSocket."""
    notif = NotificationDB(
        compagnie_id=compagnie_id,
        user_id=user_id,
        type_notif=type_notif,
        titre=titre,
        message=message,
        document_id=document_id,
        lu=False,
    )
    db.add(notif)
    # Envoyer en temps réel
    await gestionnaire_ws.envoyer_a_user(user_id, compagnie_id, {
        "type": "notification",
        "notif_type": type_notif,
        "titre": titre,
        "message": message,
        "document_id": document_id,
    })


def _doc_to_dict(d: DocumentCollabDB) -> dict:
    return {
        "id": d.id, "reference": d.reference, "titre": d.titre,
        "type_document": d.type_document, "description": d.description,
        "auteur_nom": d.auteur_nom, "statut": d.statut,
        "version_courante": d.version_courante, "type_workflow": d.type_workflow,
        "historique": d.historique or [],
        "mise_a_jour": str(d.mise_a_jour), "cree_le": str(d.cree_le),
    }

def _version_to_dict(v: VersionDocDB) -> dict:
    return {
        "id": v.id, "numero_version": v.numero_version,
        "nom_fichier": v.nom_fichier, "changelog": v.changelog,
        "auteur_nom": v.auteur_nom, "cree_le": str(v.cree_le),
        "a_fichier": bool(v.contenu_b64),
        "a_texte": bool(v.texte_contenu),
    }

def _etape_to_dict(e: WorkflowApprovalDB) -> dict:
    return {
        "etape": e.etape, "approbateur_id": e.approbateur_id,
        "approbateur_nom": e.approbateur_nom, "approbateur_role": e.approbateur_role,
        "statut": e.statut, "commentaire": e.commentaire,
        "date_action": str(e.date_action) if e.date_action else None,
    }

def _commentaire_to_dict(c: CommentaireDocDB) -> dict:
    return {
        "id": c.id, "auteur_nom": c.auteur_nom, "contenu": c.contenu,
        "page": c.page, "cree_le": str(c.cree_le),
    }

def _notif_to_dict(n: NotificationDB) -> dict:
    return {
        "id": n.id, "type_notif": n.type_notif, "titre": n.titre,
        "message": n.message, "document_id": n.document_id,
        "lu": n.lu, "cree_le": str(n.cree_le),
    }
