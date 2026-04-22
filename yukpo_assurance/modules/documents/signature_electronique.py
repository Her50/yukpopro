"""
YukpoAssurance — Signature Électronique de Documents PDF
Implémentation : hash SHA-256 + métadonnées signataire + tampon visible fpdf2

Approche retenue (adaptée zone CIMA / pas de PKI tiers) :
1. Hash SHA-256 du contenu PDF brut → empreinte cryptographique
2. Métadonnées signataire (user_id, nom, rôle, timestamp, compagnie)
3. Enregistrement en DB avec la chaîne hash → vérification ultérieure
4. Tampon de signature visible ajouté au PDF via fpdf2
5. Manifest JSON signé (pour systèmes qui lisent les métadonnées)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

logger = logging.getLogger("yukpo_assurance.signature")


@dataclass
class InfoSignataire:
    user_id: int
    nom_complet: str
    role: str
    compagnie_id: int
    compagnie_nom: str
    email: Optional[str] = None


@dataclass
class ResultatSignature:
    signature_id: str
    hash_sha256: str
    timestamp_utc: str
    signataire: InfoSignataire
    pdf_signe_b64: str                 # PDF avec tampon visible
    manifest_json: str                 # JSON signable pour vérification
    valide: bool = True


@dataclass
class ResultatVerification:
    valide: bool
    signature_id: str
    timestamp_utc: str
    signataire_nom: str
    hash_attendu: str
    hash_calcule: str
    detail: str


class SignatureElectronique:
    """
    Service de signature électronique pour YukpoAssurance.

    Usage type :
        sig = await signature_service.signer_pdf(pdf_bytes, signataire, type_doc)
        await signature_service.persister(sig)   # en DB
        ok = signature_service.verifier(pdf_bytes, sig.signature_id)
    """

    # Clé HMAC pour le manifest (en prod : charger depuis settings/vault)
    _HMAC_KEY_ENV = "SIGNATURE_HMAC_KEY"

    def __init__(self):
        from config.settings import settings
        self._hmac_key = (
            getattr(settings, "SIGNATURE_HMAC_KEY", None)
            or settings.SECRET_KEY
        ).encode()

    # ─── API principale ───────────────────────────────────────────────────────

    async def signer_pdf(
        self,
        pdf_bytes: bytes,
        signataire: InfoSignataire,
        type_document: str = "document",
        numero_reference: Optional[str] = None,
    ) -> ResultatSignature:
        """
        Signe un PDF :
        1. Calcule le hash SHA-256 du contenu original
        2. Construit le manifest signé (HMAC-SHA256)
        3. Ajoute un tampon visible sur le PDF
        Retourne ResultatSignature (pdf_signe_b64 + manifest_json).
        """
        signature_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # 1. Hash du document original
        hash_doc = hashlib.sha256(pdf_bytes).hexdigest()

        # 2. Manifest signable
        manifest = {
            "signature_id": signature_id,
            "hash_sha256": hash_doc,
            "timestamp_utc": timestamp,
            "type_document": type_document,
            "reference": numero_reference or "",
            "signataire": {
                "user_id": signataire.user_id,
                "nom": signataire.nom_complet,
                "role": signataire.role,
                "compagnie_id": signataire.compagnie_id,
                "compagnie": signataire.compagnie_nom,
                "email": signataire.email or "",
            },
        }
        manifest_str = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        hmac_sig = self._signer_hmac(manifest_str)
        manifest_final = {**manifest, "hmac_sha256": hmac_sig}

        # 3. Tampon visible sur le PDF
        try:
            pdf_signe = self._apposer_tampon(
                pdf_bytes,
                signataire=signataire,
                signature_id=signature_id,
                timestamp=timestamp,
                hash_doc=hash_doc,
                type_document=type_document,
                reference=numero_reference,
            )
        except Exception as e:
            logger.warning(f"[Signature] Tampon PDF échoué ({e}) — PDF original conservé")
            pdf_signe = pdf_bytes

        logger.info(
            f"[Signature] Signé: {signature_id} | doc={type_document} "
            f"| signataire={signataire.nom_complet} | hash={hash_doc[:16]}..."
        )

        return ResultatSignature(
            signature_id=signature_id,
            hash_sha256=hash_doc,
            timestamp_utc=timestamp,
            signataire=signataire,
            pdf_signe_b64=base64.b64encode(pdf_signe).decode(),
            manifest_json=json.dumps(manifest_final, ensure_ascii=False),
            valide=True,
        )

    def verifier(
        self,
        pdf_bytes: bytes,
        manifest_json: str,
    ) -> ResultatVerification:
        """
        Vérifie l'intégrité d'un document signé :
        1. Recalcule le hash SHA-256 du PDF (doit correspondre au manifest)
        2. Vérifie la signature HMAC du manifest
        """
        try:
            manifest = json.loads(manifest_json)
        except Exception:
            return ResultatVerification(
                valide=False,
                signature_id="?",
                timestamp_utc="?",
                signataire_nom="?",
                hash_attendu="?",
                hash_calcule="?",
                detail="Manifest JSON invalide",
            )

        signature_id = manifest.get("signature_id", "?")
        hash_attendu = manifest.get("hash_sha256", "")
        hmac_attendu = manifest.get("hmac_sha256", "")
        signataire_nom = manifest.get("signataire", {}).get("nom", "?")
        timestamp = manifest.get("timestamp_utc", "?")

        # 1. Vérifier HMAC du manifest
        manifest_sans_hmac = {k: v for k, v in manifest.items() if k != "hmac_sha256"}
        manifest_str = json.dumps(manifest_sans_hmac, ensure_ascii=False, sort_keys=True)
        hmac_calcule = self._signer_hmac(manifest_str)

        if not hmac.compare_digest(hmac_calcule, hmac_attendu):
            return ResultatVerification(
                valide=False,
                signature_id=signature_id,
                timestamp_utc=timestamp,
                signataire_nom=signataire_nom,
                hash_attendu=hash_attendu,
                hash_calcule="(HMAC invalide)",
                detail="Manifest altéré — signature HMAC incorrecte",
            )

        # 2. Vérifier hash du document
        # Note : si le PDF a été tamponné, on compare au hash original pré-tampon
        hash_actuel = hashlib.sha256(pdf_bytes).hexdigest()

        if hash_actuel != hash_attendu:
            return ResultatVerification(
                valide=False,
                signature_id=signature_id,
                timestamp_utc=timestamp,
                signataire_nom=signataire_nom,
                hash_attendu=hash_attendu,
                hash_calcule=hash_actuel,
                detail="Document modifié après signature (hash SHA-256 différent)",
            )

        return ResultatVerification(
            valide=True,
            signature_id=signature_id,
            timestamp_utc=timestamp,
            signataire_nom=signataire_nom,
            hash_attendu=hash_attendu,
            hash_calcule=hash_actuel,
            detail="Signature valide — document intègre",
        )

    # ─── Persistance (audit trail) ────────────────────────────────────────────

    async def persister(self, resultat: ResultatSignature) -> bool:
        """Enregistre la signature en DB pour l'audit trail."""
        try:
            from core.database import async_session_maker, SignatureDB
            async with async_session_maker() as db:
                db.add(SignatureDB(
                    signature_id=resultat.signature_id,
                    hash_sha256=resultat.hash_sha256,
                    timestamp_utc=resultat.timestamp_utc,
                    user_id=resultat.signataire.user_id,
                    signataire_nom=resultat.signataire.nom_complet,
                    signataire_role=resultat.signataire.role,
                    compagnie_id=resultat.signataire.compagnie_id,
                    manifest_json=resultat.manifest_json,
                ))
                await db.commit()
                logger.info(f"[Signature] Persisté: {resultat.signature_id}")
                return True
        except Exception as e:
            logger.warning(
                f"[Signature] Persistance échouée ({type(e).__name__}) — "
                "signature valide mais non enregistrée en DB"
            )
            return False

    # ─── Tampon visible PDF ───────────────────────────────────────────────────

    def _apposer_tampon(
        self,
        pdf_bytes: bytes,
        signataire: InfoSignataire,
        signature_id: str,
        timestamp: str,
        hash_doc: str,
        type_document: str,
        reference: Optional[str],
    ) -> bytes:
        """
        Ajoute une page de signature au PDF avec :
        - Cadre « SIGNÉ ÉLECTRONIQUEMENT »
        - Nom, rôle, compagnie, date/heure
        - ID de signature (UUID)
        - Hash SHA-256 (premiers 32 chars)
        - Instructions de vérification
        """
        try:
            from fpdf import FPDF
        except ImportError:
            raise ImportError("fpdf2 requis : pip install fpdf2")

        # Lire le PDF existant pour obtenir le nombre de pages
        # (fpdf2 ne peut pas modifier un PDF existant — on ajoute une nouvelle page)
        # Approche : on crée une "page de signature" et on concatène via pikepdf/pypdf si dispo
        # Fallback : retourner le PDF original (le manifest reste la preuve cryptographique)

        try:
            return self._ajouter_page_signature_pypdf(
                pdf_bytes, signataire, signature_id, timestamp, hash_doc,
                type_document, reference
            )
        except Exception:
            return self._creer_pdf_certificat_seul(
                signataire, signature_id, timestamp, hash_doc,
                type_document, reference, pdf_bytes
            )

    def _ajouter_page_signature_pypdf(
        self, pdf_bytes, signataire, signature_id, timestamp, hash_doc,
        type_document, reference
    ) -> bytes:
        """Tente d'ajouter une page de signature avec pypdf."""
        from pypdf import PdfWriter, PdfReader
        from fpdf import FPDF

        # Générer la page de signature
        page_sig_bytes = self._generer_page_signature_fpdf(
            signataire, signature_id, timestamp, hash_doc, type_document, reference
        )

        reader_original = PdfReader(BytesIO(pdf_bytes))
        reader_sig = PdfReader(BytesIO(page_sig_bytes))
        writer = PdfWriter()

        for page in reader_original.pages:
            writer.add_page(page)
        for page in reader_sig.pages:
            writer.add_page(page)

        out = BytesIO()
        writer.write(out)
        return out.getvalue()

    def _generer_page_signature_fpdf(
        self, signataire, signature_id, timestamp, hash_doc,
        type_document, reference
    ) -> bytes:
        """Génère une page PDF de certificat de signature avec fpdf2."""
        from fpdf import FPDF

        ts_display = timestamp.replace("T", " ").replace("+00:00", " UTC")[:25]
        hash_court = hash_doc[:32] + "..."

        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.add_page()
        pdf.set_margins(20, 20, 20)

        # En-tête
        pdf.set_fill_color(30, 80, 160)
        pdf.rect(0, 0, 210, 18, "F")
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(0, 4)
        pdf.cell(210, 10, "CERTIFICAT DE SIGNATURE ELECTRONIQUE", align="C")

        # Sous-titre
        pdf.set_fill_color(240, 245, 255)
        pdf.rect(0, 18, 210, 8, "F")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(60, 60, 60)
        pdf.set_xy(0, 20)
        pdf.cell(210, 5, f"YukpoAssurance — {signataire.compagnie_nom}", align="C")

        # Cadre principal
        pdf.set_text_color(0, 0, 0)
        pdf.set_draw_color(30, 80, 160)
        pdf.set_line_width(0.5)
        pdf.rect(15, 32, 180, 120)

        # Icône check
        pdf.set_fill_color(34, 139, 34)
        pdf.ellipse(95, 35, 20, 20, "F")
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(95, 39)
        pdf.cell(20, 12, "OK", align="C")

        pdf.set_text_color(34, 139, 34)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_xy(15, 60)
        pdf.cell(180, 8, "DOCUMENT SIGNE ELECTRONIQUEMENT", align="C")

        # Lignes d'info
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        info_lines = [
            ("Type de document", f"{type_document.replace('_', ' ').title()}"),
            ("Référence", reference or "—"),
            ("Signataire", signataire.nom_complet),
            ("Rôle", signataire.role.upper()),
            ("Compagnie", signataire.compagnie_nom),
            ("Date & Heure", ts_display),
            ("ID Signature", signature_id),
            ("Empreinte SHA-256", hash_court),
        ]
        y = 75
        for label, valeur in info_lines:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_xy(20, y)
            pdf.cell(50, 6, f"{label} :", align="L")
            pdf.set_font("Helvetica", "", 9)
            pdf.set_xy(70, y)
            pdf.cell(120, 6, str(valeur), align="L")
            y += 7

        # Ligne de séparation
        pdf.set_draw_color(200, 200, 200)
        pdf.line(20, y + 2, 190, y + 2)

        # Note vérification
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(100, 100, 100)
        pdf.set_xy(15, y + 6)
        pdf.multi_cell(
            180, 5,
            "Ce document a été signé électroniquement via le système YukpoAssurance. "
            "La validité peut être vérifiée en soumettant le manifest de signature à "
            "l'API /api/v1/documents/signature/verifier.",
            align="C",
        )

        # Pied de page
        pdf.set_fill_color(30, 80, 160)
        pdf.rect(0, 282, 210, 15, "F")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(0, 286)
        pdf.cell(210, 5, "YukpoAssurance — Signature Electronique Certifiee", align="C")

        return bytes(pdf.output())

    def _creer_pdf_certificat_seul(
        self, signataire, signature_id, timestamp, hash_doc,
        type_document, reference, pdf_original_bytes
    ) -> bytes:
        """Fallback : retourne le PDF original (pypdf non dispo)."""
        logger.info("[Signature] pypdf non dispo — PDF original retourné sans tampon visuel")
        return pdf_original_bytes

    # ─── HMAC helpers ─────────────────────────────────────────────────────────

    def _signer_hmac(self, contenu: str) -> str:
        return hmac.new(self._hmac_key, contenu.encode(), hashlib.sha256).hexdigest()

    # ─── Utilitaire : signer un contrat généré ────────────────────────────────

    async def signer_contrat(
        self,
        pdf_b64: str,
        signataire: InfoSignataire,
        numero_police: str,
    ) -> ResultatSignature:
        """Raccourci pour signer un contrat d'assurance."""
        pdf_bytes = base64.b64decode(pdf_b64)
        result = await self.signer_pdf(
            pdf_bytes=pdf_bytes,
            signataire=signataire,
            type_document="contrat_assurance",
            numero_reference=numero_police,
        )
        await self.persister(result)
        return result

    async def signer_etat_reglementaire(
        self,
        pdf_b64: str,
        signataire: InfoSignataire,
        code_etat: str,
        exercice: str,
    ) -> ResultatSignature:
        """Raccourci pour signer un état réglementaire (C1, C3, C5...)."""
        pdf_bytes = base64.b64decode(pdf_b64)
        result = await self.signer_pdf(
            pdf_bytes=pdf_bytes,
            signataire=signataire,
            type_document=f"etat_reglementaire_{code_etat}",
            numero_reference=f"{code_etat}-{exercice}",
        )
        await self.persister(result)
        return result

    # ─── Backend PKI externe (Docusign / Yousign) ─────────────────────────────
    # Activer via SIGNATURE_BACKEND=docusign ou yousign dans .env
    # Script de configuration : scripts/setup_pki_signature.py

    async def demander_signature_externe(
        self,
        pdf_bytes: bytes,
        signataire_email: str,
        signataire_nom: str,
        type_document: str,
        numero_reference: Optional[str] = None,
    ) -> dict:
        """
        Délègue la signature à un prestataire tiers PKI (Docusign ou Yousign).
        Utilisé pour les contrats légaux nécessitant une signature qualifiée.

        Retourne un dict avec :
          - backend : "docusign" | "yousign"
          - request_id : identifiant de la demande de signature
          - signature_url : lien direct de signature (si disponible)
          - statut : "en_attente"
        """
        from config.settings import settings
        backend = getattr(settings, "SIGNATURE_BACKEND", "hmac")

        if backend == "yousign":
            return await self._signer_via_yousign(
                pdf_bytes, signataire_email, signataire_nom, type_document, numero_reference
            )
        elif backend == "docusign":
            return await self._signer_via_docusign(
                pdf_bytes, signataire_email, signataire_nom, type_document, numero_reference
            )
        else:
            # Mode hmac ou pki_local — signature interne immédiate
            info_sig = InfoSignataire(
                user_id=0,
                nom_complet=signataire_nom,
                role="signataire_externe",
                compagnie_id=0,
                compagnie_nom="",
                email=signataire_email,
            )
            result = await self.signer_pdf(pdf_bytes, info_sig, type_document, numero_reference)
            return {
                "backend": "hmac_interne",
                "request_id": result.signature_id,
                "signature_url": None,
                "statut": "signe",
                "manifest_json": result.manifest_json,
            }

    async def _signer_via_yousign(
        self,
        pdf_bytes: bytes,
        email: str,
        nom: str,
        type_doc: str,
        reference: Optional[str],
    ) -> dict:
        """Envoi vers l'API Yousign v3."""
        try:
            import httpx
            import base64 as b64
            from config.settings import settings
        except ImportError:
            raise RuntimeError("httpx requis pour Yousign — pip install httpx")

        api_key  = getattr(settings, "YOUSIGN_API_KEY", "")
        base_url = getattr(settings, "YOUSIGN_BASE_URL", "https://staging-api.yousign.app/v3")

        if not api_key:
            raise RuntimeError("YOUSIGN_API_KEY non configurée dans .env")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            # Upload du document
            doc_resp = await client.post("/documents", json={
                "nature": "signable_document",
                "content": b64.b64encode(pdf_bytes).decode(),
                "filename": f"{type_doc}_{reference or 'doc'}.pdf",
            }, headers=headers)
            doc_resp.raise_for_status()
            doc_id = doc_resp.json()["id"]

            # Créer la demande de signature
            sign_resp = await client.post("/signature_requests", json={
                "name": f"{type_doc} — {reference or ''}",
                "delivery_mode": "email",
                "documents": [{"id": doc_id}],
                "signers": [{
                    "info": {
                        "first_name": nom.split()[0] if " " in nom else nom,
                        "last_name":  nom.split()[-1] if " " in nom else "",
                        "email": email,
                        "locale": "fr",
                    },
                    "fields": [{
                        "document_id": doc_id,
                        "type": "signature",
                        "page": 1,
                        "x": 390, "y": 690, "width": 150, "height": 50,
                    }],
                }],
            }, headers=headers)
            sign_resp.raise_for_status()
            request_id = sign_resp.json()["id"]

            # Activer (envoie l'email au signataire)
            await client.post(f"/signature_requests/{request_id}/activate", headers=headers)

        logger.info(f"[Signature] Yousign demande créée : {request_id} pour {email}")
        return {
            "backend": "yousign",
            "request_id": request_id,
            "signature_url": None,  # envoyé par email
            "statut": "en_attente",
        }

    async def _signer_via_docusign(
        self,
        pdf_bytes: bytes,
        email: str,
        nom: str,
        type_doc: str,
        reference: Optional[str],
    ) -> dict:
        """Envoi vers l'API Docusign eSignature."""
        try:
            import docusign_esign as ds
            import base64 as b64
            from config.settings import settings
        except ImportError:
            raise RuntimeError("docusign-esign requis — pip install docusign-esign")

        account_id = getattr(settings, "DOCUSIGN_ACCOUNT_ID", "")
        client_id  = getattr(settings, "DOCUSIGN_CLIENT_ID", "")
        rsa_path   = getattr(settings, "DOCUSIGN_RSA_KEY_PATH", "")
        base_url   = getattr(settings, "DOCUSIGN_BASE_URL", "https://demo.docusign.net/restapi")

        if not all([account_id, client_id, rsa_path]):
            raise RuntimeError(
                "Variables Docusign manquantes — configurer DOCUSIGN_ACCOUNT_ID, "
                "DOCUSIGN_CLIENT_ID, DOCUSIGN_RSA_KEY_PATH dans .env"
            )

        api_client = ds.ApiClient()
        api_client.set_base_path(base_url)
        rsa_key = Path(rsa_path).read_bytes()
        oauth_host = "account-d.docusign.com" if "demo" in base_url else "account.docusign.com"

        token = api_client.request_jwt_application_token(
            client_id=client_id,
            rsa_private_key_bytes=rsa_key,
            oauth_host_name=oauth_host,
            expires_in=3600,
        )
        api_client.set_default_header("Authorization", f"Bearer {token.access_token}")

        envelope_def = ds.EnvelopeDefinition(
            email_subject=f"Votre {type_doc.replace('_', ' ')} à signer — YukpoAssurance",
            status="sent",
            documents=[ds.Document(
                document_base64=b64.b64encode(pdf_bytes).decode(),
                name=f"{type_doc}_{reference or 'document'}.pdf",
                file_extension="pdf",
                document_id="1",
            )],
            recipients=ds.Recipients(signers=[
                ds.Signer(
                    email=email,
                    name=nom,
                    recipient_id="1",
                    routing_order="1",
                    tabs=ds.Tabs(sign_here_tabs=[
                        ds.SignHere(
                            anchor_string="SIGNATURE_ASSURE",
                            anchor_y_offset="-20",
                            anchor_units="pixels",
                        )
                    ]),
                )
            ]),
        )

        envelopes_api = ds.EnvelopesApi(api_client)
        result = envelopes_api.create_envelope(
            account_id,
            envelope_definition=envelope_def,
        )

        logger.info(f"[Signature] Docusign enveloppe créée : {result.envelope_id} pour {email}")
        return {
            "backend": "docusign",
            "request_id": result.envelope_id,
            "signature_url": None,
            "statut": "en_attente",
        }


# Instance singleton
signature_service = SignatureElectronique()
