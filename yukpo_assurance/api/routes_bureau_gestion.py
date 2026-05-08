"""
Bureau Gestion — Routes FastAPI pour la gestion opérationnelle du secrétariat.

Endpoints :
  Kanban :
    GET    /api/v1/bureau/gestion/travaux           — Liste des bons de travail
    POST   /api/v1/bureau/gestion/travaux           — Créer un bon de travail
    PATCH  /api/v1/bureau/gestion/travaux/{id}      — Mettre à jour statut/montant
    DELETE /api/v1/bureau/gestion/travaux/{id}      — Supprimer

  Devis & Facturation :
    POST /api/v1/bureau/gestion/devis               — Générer un devis PDF
    POST /api/v1/bureau/gestion/facture             — Générer une facture PDF
    GET  /api/v1/bureau/gestion/devis/{id}          — Télécharger PDF

  Caisse :
    GET    /api/v1/bureau/gestion/caisse            — Transactions du jour
    POST   /api/v1/bureau/gestion/caisse            — Enregistrer une transaction
    GET    /api/v1/bureau/gestion/caisse/rapport    — Rapport journalier

  CRM :
    GET    /api/v1/bureau/gestion/clients           — Liste clients
    POST   /api/v1/bureau/gestion/clients           — Créer fiche client
    GET    /api/v1/bureau/gestion/clients/{id}      — Fiche client + historique
    PATCH  /api/v1/bureau/gestion/clients/{id}      — Mettre à jour fiche
    GET    /api/v1/bureau/gestion/clients/{id}/whatsapp — URL WhatsApp
"""
import base64
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from core.auth import TokenData, get_current_user
from core.database import async_session_maker

logger = logging.getLogger("yukpo_assurance.api.bureau_gestion")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


async def get_db():
    async with async_session_maker() as session:
        yield session


# ─── Schémas ──────────────────────────────────────────────────────────────────

_TYPES_TRAVAIL_VALIDES = {
    "redaction_doc",   # Génération de document IA (lettre, contrat, attestation…)
    "scan",            # Numérisation OCR d'un document papier
    "saisie",          # Saisie/retranscription manuelle d'un document existant
    "traduction",      # Traduction d'un document
    "infographie",     # Création visuel/imprimé (flyer, faire-part, brochure…)
    "impression",      # Impression / reprographie
    "audio",           # Transcription audio → document
    "autre",
}


def _normaliser_whatsapp(numero: str, indicatif_defaut: str = "+237") -> str:
    """
    Normalise un numéro WhatsApp au format international E.164.
    Accepte : '+237 690 12 34 56', '690123456', '00237690123456', etc.
    Retourne : '+237690123456'.
    Lève ValueError si invalide.
    """
    if not numero or not numero.strip():
        raise ValueError("Numéro WhatsApp obligatoire")
    raw = numero.strip().replace(" ", "").replace("-", "").replace(".", "")
    # Préfixe 00 → +
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if not raw.startswith("+"):
        # Pas d'indicatif → on ajoute le défaut
        raw = indicatif_defaut + raw
    digits = "".join(c for c in raw[1:] if c.isdigit())
    if not (8 <= len(digits) <= 15):
        raise ValueError(f"Numéro WhatsApp invalide : {numero}")
    return "+" + digits


class BonTravailCreate(BaseModel):
    client_nom: str = Field(min_length=2, max_length=200)
    client_whatsapp: str = Field(..., min_length=8, description="Numéro WhatsApp client au format international (+237…)")
    description: str = Field(min_length=2)
    type_travail: str = "redaction_doc"
    montant_fcfa: int = Field(ge=0, default=0)
    acompte_fcfa: int = Field(ge=0, default=0)
    echeance: Optional[date] = None
    notes: str = ""


class BonTravailUpdate(BaseModel):
    statut: Optional[str] = None
    client_whatsapp: Optional[str] = None
    montant_fcfa: Optional[int] = None
    acompte_fcfa: Optional[int] = None
    notes: Optional[str] = None
    echeance: Optional[date] = None


class TerminerBonTravailRequest(BaseModel):
    message_personnalise: Optional[str] = None
    envoyer_whatsapp: bool = True


class LigneDevisSchema(BaseModel):
    description: str
    quantite: float = 1.0
    prix_unitaire_fcfa: int
    unite: str = "u"


class DevisCreate(BaseModel):
    client_nom: str
    client_contact: str
    lignes: list[LigneDevisSchema]
    reference: Optional[str] = None
    validite_jours: int = 15
    notes: Optional[str] = None
    nom_secretariat: str = "Mon Secrétariat"
    adresse_secretariat: str = ""
    tel_secretariat: str = ""
    inclure_tva: bool = True


class TransactionCreate(BaseModel):
    type: str = Field(..., description="entree | sortie")
    montant_fcfa: int = Field(gt=0)
    libelle: str
    mode_paiement: str = Field(
        default="especes",
        description="especes | orange_money | mtn_momo | virement | cheque",
    )
    reference: Optional[str] = None


class ClientCreate(BaseModel):
    nom: str
    telephone: str
    email: Optional[str] = None
    adresse: Optional[str] = None
    notes: str = ""


class ClientUpdate(BaseModel):
    telephone: Optional[str] = None
    email: Optional[str] = None
    adresse: Optional[str] = None
    notes: Optional[str] = None


# ─── Kanban ───────────────────────────────────────────────────────────────────

@router.get("/travaux", tags=["Bureau — Gestion"])
async def lister_travaux(
    statut: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste les bons de travail, filtrables par statut."""
    try:
        from core.database import BureauBonTravailDB
        q = select(BureauBonTravailDB).where(BureauBonTravailDB.user_id == current_user.user_id)
        if statut:
            q = q.where(BureauBonTravailDB.statut == statut)
        q = q.order_by(BureauBonTravailDB.cree_le.desc())
        res = await db.execute(q)
        bons = res.scalars().all()
        return {
            "travaux": [
                {
                    "id": b.id,
                    "client_nom": b.client_nom,
                    "client_whatsapp": getattr(b, "client_whatsapp", None),
                    "description": b.description,
                    "type_travail": b.type_travail,
                    "statut": b.statut,
                    "montant_fcfa": b.montant_fcfa,
                    "acompte_fcfa": b.acompte_fcfa,
                    "reste_a_payer": b.montant_fcfa - b.acompte_fcfa,
                    "echeance": b.echeance.isoformat() if b.echeance else None,
                    "notes": b.notes,
                    "notif_fin_envoyee": getattr(b, "notif_fin_envoyee", False) or False,
                    "notif_fin_horodatage": (
                        b.notif_fin_horodatage.isoformat()
                        if getattr(b, "notif_fin_horodatage", None) else None
                    ),
                    "cree_le": b.cree_le.isoformat(),
                }
                for b in bons
            ],
            "total": len(bons),
        }
    except ImportError:
        return {"travaux": [], "total": 0, "info": "Modèle DB non encore migré"}


@router.post("/travaux", tags=["Bureau — Gestion"])
async def creer_bon_travail(
    bon: BonTravailCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Crée un nouveau bon de travail (ticket Kanban)."""
    from modules.bureau.service_credits_bureau import verifier_acces_module, debiter_forfait
    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "gestion")
    if not autorise:
        raise HTTPException(403, msg)

    # Validation type travail
    if bon.type_travail not in _TYPES_TRAVAIL_VALIDES:
        raise HTTPException(
            400,
            f"Type de travail invalide. Valides : {sorted(_TYPES_TRAVAIL_VALIDES)}"
        )

    # Validation + normalisation WhatsApp
    try:
        whatsapp_norm = _normaliser_whatsapp(bon.client_whatsapp)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        from core.database import BureauBonTravailDB
        nouveau = BureauBonTravailDB(
            user_id=current_user.user_id,
            client_nom=bon.client_nom,
            client_whatsapp=whatsapp_norm,
            description=bon.description,
            type_travail=bon.type_travail,
            statut="en_attente",
            montant_fcfa=bon.montant_fcfa,
            acompte_fcfa=bon.acompte_fcfa,
            echeance=bon.echeance,
            notes=bon.notes,
            cree_le=datetime.utcnow(),
            modifie_le=datetime.utcnow(),
        )
        db.add(nouveau)
        await db.commit()
        await db.refresh(nouveau)
        try:
            await debiter_forfait(current_user.user_id, "kanban_action", module="gestion")
        except Exception:
            pass
        return {
            "id": nouveau.id, "statut": "en_attente",
            "client_whatsapp": whatsapp_norm,
            "message": "Bon de travail créé",
        }
    except ImportError:
        return {"id": None, "statut": "en_attente", "message": "Enregistrement temporaire (DB non migrée)"}


@router.patch("/travaux/{bon_id}", tags=["Bureau — Gestion"])
async def modifier_bon_travail(
    bon_id: int,
    mise_a_jour: BonTravailUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Met à jour le statut ou les informations d'un bon de travail."""
    statuts_valides = {"en_attente", "en_cours", "en_revision", "livre", "paye", "annule"}
    if mise_a_jour.statut and mise_a_jour.statut not in statuts_valides:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valides : {statuts_valides}")

    try:
        from core.database import BureauBonTravailDB
        q = select(BureauBonTravailDB).where(
            BureauBonTravailDB.id == bon_id,
            BureauBonTravailDB.user_id == current_user.user_id,
        )
        res = await db.execute(q)
        bon = res.scalar_one_or_none()
        if not bon:
            raise HTTPException(status_code=404, detail="Bon de travail introuvable")

        if mise_a_jour.statut:
            bon.statut = mise_a_jour.statut
        if mise_a_jour.montant_fcfa is not None:
            bon.montant_fcfa = mise_a_jour.montant_fcfa
        if mise_a_jour.acompte_fcfa is not None:
            bon.acompte_fcfa = mise_a_jour.acompte_fcfa
        if mise_a_jour.notes is not None:
            bon.notes = mise_a_jour.notes
        if mise_a_jour.echeance is not None:
            bon.echeance = mise_a_jour.echeance
        bon.modifie_le = datetime.utcnow()
        await db.commit()
        try:
            from modules.bureau.service_credits_bureau import debiter_forfait
            await debiter_forfait(current_user.user_id, "kanban_action", module="gestion")
        except Exception:
            pass
        return {"id": bon_id, "statut": bon.statut, "message": "Mis à jour"}
    except HTTPException:
        raise
    except ImportError:
        return {"id": bon_id, "message": "DB non migrée"}


@router.post("/travaux/{bon_id}/terminer", tags=["Bureau — Gestion"])
async def terminer_bon_travail(
    bon_id: int,
    req: TerminerBonTravailRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Marque un bon de travail comme livré ET envoie un message WhatsApp au client
    pour l'informer que son travail est terminé.
    """
    import os, httpx
    from core.database import BureauBonTravailDB
    q = select(BureauBonTravailDB).where(
        BureauBonTravailDB.id == bon_id,
        BureauBonTravailDB.user_id == current_user.user_id,
    )
    res = await db.execute(q)
    bon = res.scalar_one_or_none()
    if not bon:
        raise HTTPException(404, "Bon de travail introuvable")

    # Met à jour le statut → livre
    bon.statut = "livre"
    bon.modifie_le = datetime.utcnow()

    # Notification WhatsApp via Meta Business API
    notif_status = {"envoye": False, "raison": None}
    if req.envoyer_whatsapp and bon.client_whatsapp:
        whatsapp_phone_id = os.getenv("META_WHATSAPP_PHONE_ID")
        whatsapp_token    = os.getenv("META_WHATSAPP_TOKEN")
        if not (whatsapp_phone_id and whatsapp_token):
            notif_status["raison"] = "WhatsApp non configuré côté serveur"
        else:
            # Numéro destinataire (sans le +)
            dest = bon.client_whatsapp.lstrip("+")
            message = (req.message_personnalise or
                f"Bonjour {bon.client_nom},\n\n"
                f"Bonne nouvelle : votre travail « {bon.description[:80]} » est terminé "
                f"et prêt à être récupéré.\n\n"
                f"{f'Reste à régler : {bon.montant_fcfa - bon.acompte_fcfa} FCFA.' if (bon.montant_fcfa - bon.acompte_fcfa) > 0 else 'Le règlement est à jour, merci.'}\n\n"
                f"Cordialement."
            )
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(
                        f"https://graph.facebook.com/v19.0/{whatsapp_phone_id}/messages",
                        headers={
                            "Authorization": f"Bearer {whatsapp_token}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "messaging_product": "whatsapp",
                            "to": dest,
                            "type": "text",
                            "text": {"body": message},
                        },
                    )
                if r.status_code == 200:
                    notif_status["envoye"] = True
                    bon.notif_fin_envoyee = True
                    bon.notif_fin_horodatage = datetime.utcnow()
                else:
                    notif_status["raison"] = f"Meta API: HTTP {r.status_code} {r.text[:200]}"
                    logger.warning(f"[Kanban/WA] Échec envoi : {notif_status['raison']}")
            except Exception as e:
                notif_status["raison"] = f"Exception : {e}"
                logger.error(f"[Kanban/WA] {e}")

    await db.commit()
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait
        await debiter_forfait(current_user.user_id, "kanban_action", module="gestion")
        if notif_status["envoye"]:
            await debiter_forfait(current_user.user_id, "whatsapp_message", module="gestion")
    except Exception:
        pass

    return {
        "id": bon_id,
        "statut": "livre",
        "whatsapp_envoye":  notif_status["envoye"],
        "whatsapp_destinataire": bon.client_whatsapp,
        "whatsapp_raison":  notif_status["raison"],
        "message": "Travail terminé" + (" + client notifié par WhatsApp" if notif_status["envoye"] else ""),
    }


# ─── Devis & Facturation ──────────────────────────────────────────────────────

@router.post("/devis", tags=["Bureau — Gestion"])
async def generer_devis(
    demande: DevisCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Génère un devis professionnel en PDF (FCFA, TVA 19.25%)."""
    from modules.bureau.gestionnaire import Devis, LigneDevis, generer_pdf_devis
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "gestion")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    lignes = [
        LigneDevis(
            description=l.description,
            quantite=l.quantite,
            prix_unitaire_fcfa=l.prix_unitaire_fcfa,
            unite=l.unite,
        )
        for l in demande.lignes
    ]

    devis = Devis(
        client_nom=demande.client_nom,
        client_contact=demande.client_contact,
        lignes=lignes,
        reference=demande.reference,
        validite_jours=demande.validite_jours,
        notes=demande.notes,
        nom_secretariat=demande.nom_secretariat,
        adresse_secretariat=demande.adresse_secretariat,
        tel_secretariat=demande.tel_secretariat,
    )

    try:
        pdf_bytes = generer_pdf_devis(devis, est_facture=False)
    except Exception as e:
        logger.error(f"[Gestion Devis] Erreur PDF : {e}")
        logger.error(f"[routes_bureau_gestion.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")

    ts = int(__import__("time").time())
    pdf_id = f"bureau_devis_{current_user.user_id}_{ts}.pdf"
    (_DATA_DIR / pdf_id).write_bytes(pdf_bytes)

    try:
        await debiter_forfait(current_user.user_id, "devis_pdf", module="gestion")
    except Exception:
        pass

    return {
        "pdf_id": pdf_id,
        "pdf_base64": base64.b64encode(pdf_bytes).decode(),
        "sous_total": devis.sous_total,
        "tva": devis.tva,
        "total_ttc": devis.total_ttc,
        "reference": devis.reference or pdf_id,
    }


@router.post("/facture", tags=["Bureau — Gestion"])
async def generer_facture(
    demande: DevisCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Génère une facture PDF (même schéma que le devis, marquée FACTURE)."""
    from modules.bureau.gestionnaire import Devis, LigneDevis, generer_pdf_devis
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "gestion")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    lignes = [
        LigneDevis(
            description=l.description,
            quantite=l.quantite,
            prix_unitaire_fcfa=l.prix_unitaire_fcfa,
            unite=l.unite,
        )
        for l in demande.lignes
    ]

    devis = Devis(
        client_nom=demande.client_nom,
        client_contact=demande.client_contact,
        lignes=lignes,
        reference=demande.reference,
        validite_jours=demande.validite_jours,
        notes=demande.notes,
        nom_secretariat=demande.nom_secretariat,
        adresse_secretariat=demande.adresse_secretariat,
        tel_secretariat=demande.tel_secretariat,
    )

    try:
        pdf_bytes = generer_pdf_devis(devis, est_facture=True)
    except Exception as e:
        logger.error(f"[routes_bureau_gestion.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")

    ts = int(__import__("time").time())
    pdf_id = f"bureau_facture_{current_user.user_id}_{ts}.pdf"
    (_DATA_DIR / pdf_id).write_bytes(pdf_bytes)

    try:
        await debiter_forfait(current_user.user_id, "facture_pdf", module="gestion")
    except Exception:
        pass

    return {
        "pdf_id": pdf_id,
        "pdf_base64": base64.b64encode(pdf_bytes).decode(),
        "sous_total": devis.sous_total,
        "tva": devis.tva,
        "total_ttc": devis.total_ttc,
    }


@router.get("/document/{pdf_id}", tags=["Bureau — Gestion"])
async def telecharger_document_gestion(
    pdf_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Télécharge un devis ou facture PDF."""
    if "/" in pdf_id or "\\" in pdf_id or ".." in pdf_id:
        raise HTTPException(status_code=400, detail="Nom invalide")

    chemin = _DATA_DIR / pdf_id
    if not chemin.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    if f"_{current_user.user_id}_" not in pdf_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    return Response(
        content=chemin.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_id}"'},
    )


# ─── Caisse journalière ───────────────────────────────────────────────────────

@router.get("/caisse", tags=["Bureau — Gestion"])
async def lister_transactions(
    date_str: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne les transactions du jour (ou de la date indiquée au format YYYY-MM-DD)."""
    from datetime import timedelta
    try:
        from core.database import BureauTransactionDB
        if date_str:
            try:
                jour = date.fromisoformat(date_str)
            except ValueError:
                raise HTTPException(status_code=400, detail="Format date invalide (YYYY-MM-DD)")
        else:
            jour = date.today()

        debut = datetime.combine(jour, datetime.min.time())
        fin = datetime.combine(jour, datetime.max.time())
        q = select(BureauTransactionDB).where(
            BureauTransactionDB.user_id == current_user.user_id,
            BureauTransactionDB.horodatage >= debut,
            BureauTransactionDB.horodatage <= fin,
        ).order_by(BureauTransactionDB.horodatage.desc())
        res = await db.execute(q)
        txs = res.scalars().all()

        from modules.bureau.gestionnaire import Transaction, calculer_rapport_caisse
        transactions = [
            Transaction(
                type=t.type,
                montant_fcfa=t.montant_fcfa,
                libelle=t.libelle,
                mode_paiement=t.mode_paiement,
            )
            for t in txs
        ]
        rapport = calculer_rapport_caisse(transactions)

        return {
            "date": jour.isoformat(),
            "transactions": [
                {
                    "id": t.id,
                    "type": t.type,
                    "montant_fcfa": t.montant_fcfa,
                    "libelle": t.libelle,
                    "mode_paiement": t.mode_paiement,
                    "horodatage": t.horodatage.isoformat(),
                }
                for t in txs
            ],
            "rapport": rapport,
        }
    except ImportError:
        return {"date": date.today().isoformat(), "transactions": [], "rapport": {}}


@router.post("/caisse", tags=["Bureau — Gestion"])
async def enregistrer_transaction(
    tx: TransactionCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enregistre une entrée ou sortie de caisse."""
    types_valides = {"entree", "sortie"}
    modes_valides = {"especes", "orange_money", "mtn_momo", "virement", "cheque"}
    if tx.type not in types_valides:
        raise HTTPException(status_code=400, detail=f"Type invalide. Valides : {types_valides}")
    if tx.mode_paiement not in modes_valides:
        raise HTTPException(status_code=400, detail=f"Mode invalide. Valides : {modes_valides}")

    from modules.bureau.service_credits_bureau import verifier_acces_module, debiter_forfait
    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "gestion")
    if not autorise:
        raise HTTPException(403, msg)

    try:
        from core.database import BureauTransactionDB
        nouvelle = BureauTransactionDB(
            user_id=current_user.user_id,
            type=tx.type,
            montant_fcfa=tx.montant_fcfa,
            libelle=tx.libelle,
            mode_paiement=tx.mode_paiement,
            reference=tx.reference,
            horodatage=datetime.utcnow(),
        )
        db.add(nouvelle)
        await db.commit()
        await db.refresh(nouvelle)
        try:
            await debiter_forfait(current_user.user_id, "caisse_transaction", module="gestion")
        except Exception:
            pass
        return {"id": nouvelle.id, "message": "Transaction enregistrée"}
    except ImportError:
        return {"id": None, "message": "Enregistrement temporaire (DB non migrée)"}


# ─── Mini-CRM ─────────────────────────────────────────────────────────────────

@router.get("/clients", tags=["Bureau — Gestion"])
async def lister_clients(
    recherche: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste tous les clients du secrétariat, avec recherche par nom."""
    try:
        from core.database import BureauClientDB
        from sqlalchemy import or_, func
        q = select(BureauClientDB).where(BureauClientDB.user_id == current_user.user_id)
        if recherche:
            q = q.where(
                or_(
                    func.lower(BureauClientDB.nom).contains(recherche.lower()),
                    BureauClientDB.telephone.contains(recherche),
                )
            )
        q = q.order_by(BureauClientDB.nom)
        res = await db.execute(q)
        clients = res.scalars().all()
        return {
            "clients": [
                {
                    "id": c.id,
                    "nom": c.nom,
                    "telephone": c.telephone,
                    "email": c.email,
                    "nb_commandes": c.nb_commandes,
                    "total_paye_fcfa": c.total_paye_fcfa,
                    "derniere_visite": c.derniere_visite.isoformat() if c.derniere_visite else None,
                }
                for c in clients
            ],
            "total": len(clients),
        }
    except ImportError:
        return {"clients": [], "total": 0}


@router.post("/clients", tags=["Bureau — Gestion"])
async def creer_client(
    client: ClientCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Crée une nouvelle fiche client."""
    from modules.bureau.service_credits_bureau import verifier_acces_module, debiter_forfait
    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "gestion")
    if not autorise:
        raise HTTPException(403, msg)

    try:
        from core.database import BureauClientDB
        nouveau = BureauClientDB(
            user_id=current_user.user_id,
            nom=client.nom,
            telephone=client.telephone,
            email=client.email,
            adresse=client.adresse,
            notes=client.notes,
            nb_commandes=0,
            total_paye_fcfa=0,
            derniere_visite=date.today(),
            cree_le=datetime.utcnow(),
        )
        db.add(nouveau)
        await db.commit()
        await db.refresh(nouveau)
        try:
            await debiter_forfait(current_user.user_id, "client_action", module="gestion")
        except Exception:
            pass
        return {"id": nouveau.id, "message": "Client créé"}
    except ImportError:
        return {"id": None, "message": "DB non migrée"}


@router.get("/clients/{client_id}", tags=["Bureau — Gestion"])
async def fiche_client(
    client_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne la fiche complète d'un client."""
    try:
        from core.database import BureauClientDB
        q = select(BureauClientDB).where(
            BureauClientDB.id == client_id,
            BureauClientDB.user_id == current_user.user_id,
        )
        res = await db.execute(q)
        c = res.scalar_one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail="Client introuvable")

        return {
            "id": c.id,
            "nom": c.nom,
            "telephone": c.telephone,
            "email": c.email,
            "adresse": c.adresse,
            "notes": c.notes,
            "nb_commandes": c.nb_commandes,
            "total_paye_fcfa": c.total_paye_fcfa,
            "derniere_visite": c.derniere_visite.isoformat() if c.derniere_visite else None,
            "cree_le": c.cree_le.isoformat(),
        }
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=503, detail="DB non migrée")


@router.get("/clients/{client_id}/whatsapp", tags=["Bureau — Gestion"])
async def url_whatsapp_client(
    client_id: int,
    message: str = "Bonjour, votre document est prêt.",
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Génère l'URL WhatsApp deep link pour contacter le client directement."""
    try:
        from core.database import BureauClientDB
        from modules.bureau.gestionnaire import FicheClient, formater_message_whatsapp
        q = select(BureauClientDB).where(
            BureauClientDB.id == client_id,
            BureauClientDB.user_id == current_user.user_id,
        )
        res = await db.execute(q)
        c = res.scalar_one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail="Client introuvable")

        fiche = FicheClient(id=c.id, nom=c.nom, telephone=c.telephone)
        url = formater_message_whatsapp(fiche, message)
        try:
            from modules.bureau.service_credits_bureau import debiter_forfait
            await debiter_forfait(current_user.user_id, "whatsapp_message", module="gestion")
        except Exception:
            pass
        return {"whatsapp_url": url, "telephone": c.telephone, "message": message}
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=503, detail="DB non migrée")
