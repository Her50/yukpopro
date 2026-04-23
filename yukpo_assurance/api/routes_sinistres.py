"""Routes sinistres — déclaration, instruction, fraude"""
import base64
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

logger = logging.getLogger("yukpo_assurance.api.sinistres")
from pydantic import BaseModel
from typing import Optional
from datetime import date

from modules.sinistres.reception import DeclarationSinistre, reception_sinistres
from modules.sinistres.fraude_detector import FraudeDetector, fraude_detector
from modules.sinistres.fraude_reseau import fraude_reseau_detector
from modules.copilote.assistant_quotidien import assistant
from core.orass_connector import orass
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(get_current_user)])


class DeclarationRequest(BaseModel):
    numero_police: str
    date_sinistre: date
    heure_sinistre: Optional[str] = None
    lieu: str
    nature: str
    description: str
    nom_declarant: str
    telephone_declarant: str
    photos_b64: list[str] = []
    constat_b64: Optional[str] = None
    tiers_impliques: list[dict] = []
    blesses: bool = False
    canal: str = "app"


class RapportRequest(BaseModel):
    donnees_sinistre: dict


@router.get("/fraude/{numero_sinistre}/reseau")
async def analyser_fraude_reseau(
    numero_sinistre: str,
    current_user: TokenData = Depends(require_permission("sinistres:read")),
):
    """Détection de fraude organisée / réseau sur un sinistre"""
    resultat = await fraude_reseau_detector.analyser(numero_sinistre)
    return {
        "numero_sinistre": numero_sinistre,
        "reseau_detecte": resultat.reseau_detecte,
        "score_reseau": resultat.score_reseau,
        "acteurs_suspects": resultat.acteurs_suspects,
        "pattern_identifie": resultat.pattern_identifie,
        "recommandation": resultat.recommandation,
    }


@router.get("/fraude/{numero_sinistre}/score")
async def score_fraude_individuel(
    numero_sinistre: str,
    current_user: TokenData = Depends(require_permission("sinistres:read")),
):
    """Score de fraude individuel (0-100) pour un sinistre"""
    sinistre = await orass.recuperer_sinistre(numero_sinistre)
    if not sinistre:
        raise HTTPException(404, "Sinistre introuvable")
    import dataclasses
    resultat = await fraude_detector.analyser(dataclasses.asdict(sinistre))
    return resultat


@router.post("/declarer")
async def declarer_sinistre(
    req: DeclarationRequest,
    current_user: TokenData = Depends(require_permission("sinistres:declare")),
):
    """Déclaration intelligente d'un sinistre — analyse IA + création ORASS"""
    declaration = DeclarationSinistre(**req.model_dump())
    try:
        resultat = await reception_sinistres.traiter_declaration(declaration)
        return {
            "numero_sinistre": resultat.numero_sinistre,
            "statut_contrat": resultat.statut_contrat,
            "pre_rapport": resultat.pre_rapport_ia,
            "score_fraude": resultat.score_fraude,
            "complexite": resultat.complexite,
            "actions_immediates": resultat.actions_immediates,
            "expert_suggere": resultat.expert_suggere,
            "delai_reglementaire_jours": resultat.delai_reglementaire_jours,
            "message_client": resultat.message_client,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{numero_sinistre}")
async def consulter_sinistre(
    numero_sinistre: str,
    current_user: TokenData = Depends(require_permission("sinistres:read")),
):
    """Consultation d'un dossier sinistre"""
    sinistre = await orass.recuperer_sinistre(numero_sinistre)
    if not sinistre:
        raise HTTPException(404, "Sinistre introuvable")
    return sinistre


@router.patch("/{numero_sinistre}/statut")
async def mettre_a_jour_statut(
    numero_sinistre: str,
    body: dict,
    current_user: TokenData = Depends(require_permission("sinistres:update")),
):
    """Mise à jour du statut d'un sinistre"""
    statut = body.get("statut")
    commentaire = body.get("commentaire", "")
    if not statut:
        raise HTTPException(400, "Statut manquant")
    success = await orass.mettre_a_jour_statut_sinistre(numero_sinistre, statut, commentaire)
    return {"success": success, "numero_sinistre": numero_sinistre, "nouveau_statut": statut}


@router.post("/rapport-expertise")
async def generer_rapport_expertise(
    req: RapportRequest,
    current_user: TokenData = Depends(require_permission("sinistres:read")),
):
    """Génération automatique d'un rapport d'expertise sinistre"""
    rapport = await assistant.generer_rapport_sinistre(req.donnees_sinistre)
    return {"rapport": rapport}


_MIMES_AUTORISES = {
    "image/jpeg", "image/png", "image/webp", "image/heic",
    "application/pdf",
    "image/tiff",
}


@router.post("/{numero_sinistre}/pieces")
async def uploader_piece_sinistre(
    numero_sinistre: str,
    fichier: UploadFile = File(...),
    type_piece: str = "photo",   # "photo" | "constat" | "facture" | "expertise" | "autre"
    current_user: TokenData = Depends(require_permission("sinistres:update")),
):
    """
    Upload d'une pièce justificative pour un dossier sinistre.
    Types acceptés : JPEG, PNG, WebP, HEIC, PDF, TIFF.
    Taille max : 20 Mo.
    La pièce est analysée par IA (OCR + extraction de données clés).
    """
    # Pré-check crédits avant l'analyse IA (sinon 402 CREDITS_EPUISES)
    try:
        from modules.pro.service_credits import verifier_solde_suffisant
        ok_solde, _restants, _plan, msg = await verifier_solde_suffisant(current_user.user_id)
        if not ok_solde:
            raise HTTPException(402, msg)
    except HTTPException:
        raise
    except Exception:
        pass

    # Validation taille
    contenu = await fichier.read()
    taille_mb = len(contenu) / (1024 * 1024)
    limite_mb = 20.0
    if taille_mb > limite_mb:
        raise HTTPException(413, f"Fichier trop volumineux : {taille_mb:.1f} Mo (max {limite_mb} Mo)")

    # Validation MIME
    mime = fichier.content_type or "application/octet-stream"
    if mime not in _MIMES_AUTORISES:
        raise HTTPException(
            415,
            f"Type de fichier non supporté : {mime}. "
            f"Formats acceptés : JPEG, PNG, WebP, PDF, TIFF",
        )

    # Analyser la pièce par IA (extraction OCR + données structurées)
    from core.ia_client import ModeIA, ia_client
    est_image = mime.startswith("image/")
    images_b64 = [base64.standard_b64encode(contenu).decode()] if est_image else []

    prompt = f"""Tu analyses une pièce justificative d'un dossier sinistre.
Type de pièce déclaré : {type_piece}
Dossier sinistre : {numero_sinistre}

{"Voici l'image de la pièce." if est_image else "Le document PDF a été fourni."}

Extrais les informations clés :
1. Type de document réel (constat, facture, certificat médical, PV police, photo dommages, etc.)
2. Date du document
3. Montant en FCFA (si applicable)
4. Parties impliquées (noms, plaques, numéros)
5. Description des dommages ou faits constatés
6. Cohérence avec le dossier sinistre {numero_sinistre}
7. Signaux suspects (altérations, incohérences de date, montants anormaux)

Retourne ce JSON :
{{
  "type_document_detecte": "...",
  "date_document": "JJ/MM/AAAA ou null",
  "montant_fcfa": 0,
  "parties": ["..."],
  "resume": "description courte des faits/dommages",
  "coherence": true,
  "signaux_suspects": [],
  "confiance": 0.95
}}"""

    try:
        reponse = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            images_b64=images_b64 if images_b64 else None,
            json_attendu=True,
        )
        analyse = reponse.as_json()

        # Débit crédits (attendu — marge 20× appliquée par service_credits)
        try:
            from modules.pro.service_credits import verifier_et_debiter
            await verifier_et_debiter(
                user_id=current_user.user_id,
                modele=reponse.modele_utilise or "claude-sonnet-4-6",
                tokens_input=reponse.tokens_input or 1500,
                tokens_output=reponse.tokens_output or 500,
                module="sinistres_analyse",
            )
        except Exception as _e:
            logger.debug(f"[Sinistres/Credits] débit non bloquant: {_e}")
    except Exception as e:
        analyse = {"erreur": str(e), "message": "Analyse IA non disponible"}

    return {
        "numero_sinistre": numero_sinistre,
        "fichier": fichier.filename,
        "type_piece": type_piece,
        "taille_mo": round(taille_mb, 2),
        "mime": mime,
        "analyse_ia": analyse,
        "statut": "piece_enregistree",
    }


@router.get("/police/{numero_police}")
async def sinistres_par_police(
    numero_police: str,
    current_user: TokenData = Depends(require_permission("sinistres:read")),
):
    """Liste des sinistres d'une police"""
    sinistres = await orass.lister_sinistres_par_police(numero_police)
    return {"numero_police": numero_police, "sinistres": sinistres}
