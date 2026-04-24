"""
Routes admin — gestion des paiements MoMo (validation manuelle + auto-match IA).

Endpoints (tous réservés aux rôles admin/super_admin/yukpo_owner) :
  GET  /pending             — liste des commandes en attente/provisoire
  GET  /all                 — toutes les commandes récentes
  POST /{id}/valider         — valide une commande
  POST /{id}/rejeter         — rejette une commande
  POST /upload-releve        — upload PDF/image/CSV relevé MoMo, parse IA, auto-match
  POST /cron/auto-annulation — job d'annulation des provisoires > 3h (peut aussi tourner en CRON)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import CommandePaiementDB, UtilisateurDB, async_session_maker
from modules.pro.service_paiement_commande import (
    ADMIN_ROLES,
    annuler_commandes_expirees,
    auto_match_releve,
    rejeter_commande,
    valider_commande,
)

logger = logging.getLogger("yukpo_assurance.api.admin_paiements")
router = APIRouter()


async def get_db():
    async with async_session_maker() as session:
        yield session


def _check_admin(user: TokenData):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Accès admin requis")


def _serialiser_commande(cmd: CommandePaiementDB, user_info: Optional[dict] = None) -> dict:
    return {
        "id":                  cmd.id,
        "reference":           cmd.reference,
        "user_id":             cmd.user_id,
        "user":                user_info,
        "type":                cmd.type,
        "plan_ou_pack":        cmd.plan_ou_pack,
        "montant_fcfa":        cmd.montant_fcfa,
        "operateur":           cmd.operateur,
        "numero_destinataire": cmd.numero_destinataire,
        "numero_expediteur":   cmd.numero_expediteur,
        "tx_id":               cmd.tx_id,
        "statut":              cmd.statut,
        "motif_rejet":         cmd.motif_rejet,
        "valide_par":          cmd.valide_par,
        "valide_le":           cmd.valide_le.isoformat() if cmd.valide_le else None,
        "match_source":        cmd.match_source,
        "cree_le":             cmd.cree_le.isoformat(),
        "deadline":            cmd.deadline.isoformat(),
        "en_retard":           cmd.deadline < datetime.utcnow() and cmd.statut in ("attente", "provisoire"),
    }


async def _charger_user_info(user_id: int, db: AsyncSession) -> dict:
    u = await db.get(UtilisateurDB, user_id)
    if not u:
        return {"id": user_id, "email": None, "nom": None}
    return {"id": u.id, "email": u.email, "username": u.username, "nom": f"{u.prenoms or ''} {u.nom}".strip()}


# ══════════════════════════════════════════════════════════════════════════════
# Listes
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/pending", summary="Commandes en attente / provisoires")
async def lister_pending(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin(current_user)
    stmt = (
        select(CommandePaiementDB)
        .where(CommandePaiementDB.statut.in_(("attente", "provisoire")))
        .order_by(desc(CommandePaiementDB.cree_le))
    )
    commandes = (await db.execute(stmt)).scalars().all()
    result = []
    for cmd in commandes:
        u = await _charger_user_info(cmd.user_id, db)
        result.append(_serialiser_commande(cmd, u))
    return {"commandes": result, "total": len(result)}


@router.get("/all", summary="Toutes les commandes récentes (90 jours)")
async def lister_toutes(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin(current_user)
    limite = datetime.utcnow() - timedelta(days=90)
    stmt = (
        select(CommandePaiementDB)
        .where(CommandePaiementDB.cree_le >= limite)
        .order_by(desc(CommandePaiementDB.cree_le))
        .limit(500)
    )
    commandes = (await db.execute(stmt)).scalars().all()
    result = []
    for cmd in commandes:
        u = await _charger_user_info(cmd.user_id, db)
        result.append(_serialiser_commande(cmd, u))
    return {"commandes": result, "total": len(result)}


# ══════════════════════════════════════════════════════════════════════════════
# Actions admin
# ══════════════════════════════════════════════════════════════════════════════

class RejetRequest(BaseModel):
    motif: str = Field(..., min_length=3, max_length=300)


@router.post("/{commande_id}/valider", summary="Valider manuellement une commande")
async def valider(
    commande_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin(current_user)
    try:
        cmd = await valider_commande(commande_id, current_user.user_id, "manuel", db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"succes": True, "commande": _serialiser_commande(cmd)}


@router.post("/{commande_id}/rejeter", summary="Rejeter une commande (rollback auto)")
async def rejeter(
    commande_id: int,
    req: RejetRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin(current_user)
    try:
        cmd = await rejeter_commande(commande_id, current_user.user_id, req.motif, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"succes": True, "commande": _serialiser_commande(cmd)}


# ══════════════════════════════════════════════════════════════════════════════
# Upload relevé + parsing IA
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/upload-releve", summary="Upload PDF/image/CSV relevé MoMo — parse IA + auto-match")
async def upload_releve(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload un relevé de paiements MoMo. L'IA extrait les lignes
    (téléphone expéditeur, montant, tx_id, date) puis tente un auto-match
    avec les commandes en attente/provisoire.
    Match = (montant identique) ET (4 derniers chiffres du tel identiques).
    """
    _check_admin(current_user)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (max 10 Mo)")

    # Extraction IA du contenu
    try:
        paiements = await _extraire_paiements_releve(content, file.filename or "releve", file.content_type or "")
    except Exception as e:
        logger.error(f"[AdminPaiement] Extraction IA échouée : {e}")
        raise HTTPException(500, f"Erreur extraction IA : {e}")

    if not paiements:
        return {
            "succes": True,
            "message": "Aucune ligne de paiement détectée dans le relevé.",
            "matches": [],
            "non_matches": [],
            "total_lignes": 0,
        }

    # Auto-match
    result = await auto_match_releve(paiements, current_user.user_id, db)
    return {"succes": True, **result, "paiements_extraits": paiements}


async def _extraire_paiements_releve(content: bytes, filename: str, content_type: str) -> list[dict]:
    """Extrait les paiements d'un relevé via IA multi-format (PDF, image, CSV, Excel, texte)."""
    import json
    import re
    fname = filename.lower()

    # CSV / texte — parsing direct
    if fname.endswith(".csv") or fname.endswith(".txt") or "text" in content_type:
        return _parser_csv_ou_texte(content.decode("utf-8", errors="ignore"))

    # Excel
    if fname.endswith((".xlsx", ".xls")):
        try:
            import openpyxl  # type: ignore
            from io import BytesIO
            wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
            lignes = []
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    lignes.append(" | ".join(str(c) if c is not None else "" for c in row))
            return _parser_csv_ou_texte("\n".join(lignes))
        except Exception as e:
            logger.warning(f"Excel parse fallback vers IA: {e}")

    # PDF / image → extraction via LLM (Claude ou GPT-4o vision)
    return await _extraire_via_ia(content, filename, content_type)


def _parser_csv_ou_texte(texte: str) -> list[dict]:
    """Heuristique : chaque ligne avec un montant + tel est considérée comme un paiement."""
    import re
    lignes = []
    for row in texte.splitlines():
        # Téléphone (7-15 chiffres, éventuellement préfixé)
        tel_match = re.search(r"\+?\d[\d\s\-]{7,17}", row)
        # Montant (nombre entier, éventuellement formaté avec espaces/points)
        montants = re.findall(r"\b\d{1,3}(?:[\s.,]\d{3})+\b|\b\d{3,7}\b", row)
        if not tel_match or not montants:
            continue
        tel = re.sub(r"\D", "", tel_match.group(0))
        montant = int(re.sub(r"\D", "", montants[-1]))
        tx_match = re.search(r"(TX|REF|TRANS)[A-Z0-9]{6,}", row.upper())
        if montant < 100 or montant > 1_000_000:
            continue
        lignes.append({
            "tel":     tel,
            "montant": montant,
            "tx_id":   tx_match.group(0) if tx_match else None,
            "date":    None,
        })
    return lignes


async def _extraire_via_ia(content: bytes, filename: str, content_type: str) -> list[dict]:
    """Utilise un LLM vision (Claude ou GPT-4o) pour lire un PDF scanné ou une image."""
    import base64
    import json

    b64 = base64.b64encode(content).decode("utf-8")
    is_pdf = filename.lower().endswith(".pdf")
    media_type = content_type or ("application/pdf" if is_pdf else "image/jpeg")

    prompt = (
        "Tu reçois un relevé de paiements Mobile Money (MTN MoMo / Orange Money / Wave / etc.). "
        "Extrais TOUTES les transactions de crédit (paiements reçus). "
        'Réponds UNIQUEMENT en JSON : {"paiements": [{"tel": "6XXXXXXXX", "montant": 20037, "tx_id": "TX123456", "date": "2026-04-24"}, ...]}. '
        "Le champ 'tel' est le numéro de l'expéditeur (celui qui a envoyé l'argent). "
        "Le 'montant' est un entier en FCFA. Si date absente, mets null. Ignore les débits et les frais."
    )

    # Essai Claude
    try:
        from anthropic import AsyncAnthropic
        import os
        client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document" if is_pdf else "image",
                     "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        txt = msg.content[0].text
        match = _extraire_json(txt)
        return match.get("paiements", []) if match else []
    except Exception as e:
        logger.warning(f"Claude vision échoué, fallback GPT-4o: {e}")

    # Fallback GPT-4o
    try:
        from openai import AsyncOpenAI
        import os
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        data_url = f"data:{media_type};base64,{b64}"
        resp = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        )
        txt = resp.choices[0].message.content or ""
        match = _extraire_json(txt)
        return match.get("paiements", []) if match else []
    except Exception as e:
        logger.error(f"GPT-4o vision échoué: {e}")
        return []


def _extraire_json(texte: str) -> Optional[dict]:
    import json
    import re
    # Cherche un bloc JSON dans la réponse
    m = re.search(r"\{.*\}", texte, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CRON — auto-annulation
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/cron/auto-annulation", summary="Annule les commandes provisoires > 3h (CRON)")
async def cron_auto_annulation(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin(current_user)
    n = await annuler_commandes_expirees(db)
    return {"succes": True, "annulees": n}
