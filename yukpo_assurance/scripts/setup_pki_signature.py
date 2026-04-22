#!/usr/bin/env python3
"""
YukpoAssurance — Configuration Signature Électronique PKI
===========================================================
Script d'intégration et de test pour la signature PKI qualifiée.

La signature actuelle (SHA-256 + HMAC) est suffisante pour la gestion interne.
Ce script configure la signature PKI qualifiée pour les documents légaux :
contrats, avenants, quittances, rapports réglementaires CIMA.

Niveaux de signature supportés :
  1. HMAC-SHA256 interne (existant)     → GED interne, archivage
  2. PKI auto-signée (ce script)        → Proof of concept / recette
  3. PKI via CA reconnue CEMAC/UEMOA    → Production légale (recommandé)
  4. eIDAS qualifié (Docusign, Yousign) → Contrats transfrontaliers

Autorités de certification recommandées zone CIMA :
  - Cameroun : ANTIC (Agence Nationale des TIC) — cert.antic.cm
  - Côte d'Ivoire : ANSSI CI — anssi.gouv.ci
  - Sénégal : ADIE — adie.sn
  - Multi-pays : Certinomis Africa, Docusign, Yousign (eIDAS)

Usage :
    # Générer une PKI auto-signée pour les tests
    python scripts/setup_pki_signature.py --action generer-ca --org "YukpoAssurance Tests"

    # Tester la signature d'un PDF
    python scripts/setup_pki_signature.py --action tester-signature --pdf contrat_test.pdf

    # Vérifier un PDF signé
    python scripts/setup_pki_signature.py --action verifier --pdf contrat_signe.pdf

    # Guide intégration Docusign
    python scripts/setup_pki_signature.py --action guide-docusign

    # Guide intégration Yousign (moins cher, RGPD)
    python scripts/setup_pki_signature.py --action guide-yousign
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

GREEN  = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"
BLUE   = "\033[94m"; RESET  = "\033[0m";  BOLD = "\033[1m"

def ok(m):    print(f"  {GREEN}✓{RESET}  {m}")
def warn(m):  print(f"  {YELLOW}⚠{RESET}  {m}")
def fail(m):  print(f"  {RED}✗{RESET}  {m}")
def info(m):  print(f"  {BLUE}ℹ{RESET}  {m}")
def header(m):print(f"\n{BOLD}{BLUE}{'─'*62}{RESET}\n{BOLD}  {m}{RESET}\n{'─'*62}")


PKI_DIR = Path("data/pki")


# ─── 1. Génération d'une PKI auto-signée ────────────────────────────────────

def generer_ca(org: str, pays: str, validite_jours: int = 3650) -> None:
    """
    Génère une CA (Certificate Authority) auto-signée + certificat serveur.
    Suffisant pour les tests et la recette interne.
    NON reconnu légalement — utiliser une CA tierce pour la production.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        fail("cryptography non installée — pip install cryptography")
        sys.exit(1)

    header("Génération PKI auto-signée")
    PKI_DIR.mkdir(parents=True, exist_ok=True)

    # ── Clé CA ────────────────────────────────────────────────────────────
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    ca_key_path = PKI_DIR / "ca.key.pem"
    with open(ca_key_path, "wb") as f:
        f.write(ca_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.BestAvailableEncryption(b"yukpo_ca_passphrase_change_me"),
        ))
    ok(f"Clé CA générée (RSA 4096) → {ca_key_path}")
    warn("Protéger ca.key.pem — accès restreint (chmod 600)")

    # ── Certificat CA ─────────────────────────────────────────────────────
    ca_subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, pays[:2].upper()),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
        x509.NameAttribute(NameOID.COMMON_NAME, f"{org} Root CA"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "PKI"),
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=validite_jours))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=True,
            key_cert_sign=True, crl_sign=True,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    ca_cert_path = PKI_DIR / "ca.cert.pem"
    with open(ca_cert_path, "wb") as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    ok(f"Certificat CA généré ({validite_jours // 365} ans) → {ca_cert_path}")

    # ── Clé et certificat signature documents ─────────────────────────────
    doc_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    doc_key_path = PKI_DIR / "signing.key.pem"
    with open(doc_key_path, "wb") as f:
        f.write(doc_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),  # clé utilisée par l'app — sans passphrase
        ))
    ok(f"Clé signature documents (RSA 2048) → {doc_key_path}")

    doc_subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, pays[:2].upper()),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
        x509.NameAttribute(NameOID.COMMON_NAME, f"{org} Document Signing"),
    ])
    doc_cert = (
        x509.CertificateBuilder()
        .subject_name(doc_subject)
        .issuer_name(ca_subject)
        .public_key(doc_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=True,
            key_cert_sign=False, crl_sign=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.OID_EMAIL_PROTECTION]),
            critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    doc_cert_path = PKI_DIR / "signing.cert.pem"
    with open(doc_cert_path, "wb") as f:
        f.write(doc_cert.public_bytes(serialization.Encoding.PEM))
    ok(f"Certificat signature documents → {doc_cert_path}")

    # ── Ajouter dans .env ──────────────────────────────────────────────────
    env_block = f"""
# ── Signature PKI (auto-signée — remplacer par CA officielle en prod) ─────────
PKI_CA_CERT_PATH={ca_cert_path}
PKI_SIGNING_KEY_PATH={doc_key_path}
PKI_SIGNING_CERT_PATH={doc_cert_path}
PKI_CA_PASSPHRASE=yukpo_ca_passphrase_change_me
PKI_ENABLED=true
"""
    env_example = Path(".env.example")
    if env_example.exists():
        content = env_example.read_text()
        if "PKI_CA_CERT_PATH" not in content:
            with open(env_example, "a") as f:
                f.write(env_block)
            ok(".env.example mis à jour avec les variables PKI")
    else:
        print(env_block)

    header("Résumé PKI générée")
    info(f"CA :          {ca_cert_path}")
    info(f"Clé signe :   {doc_key_path}")
    info(f"Cert signe :   {doc_cert_path}")
    warn("PKI auto-signée — valable pour tests/recette uniquement")
    warn("Pour la production légale, obtenir un certificat auprès d'une CA reconnue")
    info("Autorités recommandées zone CIMA : ANTIC (Cameroun), ANSSI CI, ADIE (Sénégal)")


# ─── 2. Test de signature PDF ────────────────────────────────────────────────

def tester_signature_pdf(pdf_path: str) -> None:
    """Test de signature d'un PDF avec la PKI locale."""
    header("Test signature PDF")

    key_path  = PKI_DIR / "signing.key.pem"
    cert_path = PKI_DIR / "signing.cert.pem"

    if not key_path.exists() or not cert_path.exists():
        fail(f"PKI non générée — exécuter d'abord : python {__file__} --action generer-ca")
        sys.exit(1)

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        fail("cryptography non installée — pip install cryptography")
        sys.exit(1)

    # Lire la clé
    with open(key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    # Signer le fichier (ou un contenu test si le PDF n'existe pas)
    p = Path(pdf_path)
    if p.exists():
        contenu = p.read_bytes()
        ok(f"PDF chargé : {pdf_path} ({len(contenu):,} bytes)")
    else:
        contenu = b"Contrat test YukpoAssurance - " + datetime.utcnow().isoformat().encode()
        warn(f"PDF {pdf_path} introuvable — test sur contenu fictif")

    # Signature RSA-PSS
    signature = private_key.sign(contenu, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.MAX_LENGTH,
    ), hashes.SHA256())

    sig_hex = signature.hex()[:64] + "..."
    ok(f"Signature RSA-PSS générée : {sig_hex}")

    # Métadonnées de signature
    with open(cert_path, "rb") as f:
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(f.read())

    meta = {
        "algorithme": "RSA-PSS SHA-256",
        "signataire": cert.subject.get_attributes_for_oid(
            x509.NameOID.COMMON_NAME
        )[0].value,
        "valide_jusqu_au": cert.not_valid_after_utc.isoformat() if hasattr(cert, 'not_valid_after_utc') else str(cert.not_valid_after),
        "signature_hex_debut": signature.hex()[:32],
        "taille_signature_bytes": len(signature),
        "horodatage": datetime.utcnow().isoformat(),
    }
    ok(f"Métadonnées : {json.dumps(meta, ensure_ascii=False, indent=2)}")

    # Sauvegarde de la signature détachée
    sig_path = Path(pdf_path).with_suffix(".sig")
    sig_path.write_bytes(signature)
    ok(f"Signature détachée sauvegardée → {sig_path}")

    info("Intégrer dans modules/documents/signature_electronique.py via PKI_SIGNING_KEY_PATH")


# ─── 3. Guide Docusign ───────────────────────────────────────────────────────

def guide_docusign() -> None:
    header("Intégration Docusign (Signature électronique qualifiée)")
    print(f"""
{BOLD}Docusign eSignature — API REST{RESET}
Coût : ~$25/mois (plan personal) ou $40/mois (standard, 5 utilisateurs)
Niveau légal : Avancé (eIDAS, ESIGN USA) — reconnu dans 180 pays

{BOLD}1. Créer un compte Docusign{RESET}
   https://developers.docusign.com/

{BOLD}2. Variables d'environnement à ajouter dans .env{RESET}
   DOCUSIGN_ACCOUNT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   DOCUSIGN_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   DOCUSIGN_CLIENT_SECRET=VOTRE_SECRET
   DOCUSIGN_BASE_URL=https://demo.docusign.net/restapi    # recette
   # DOCUSIGN_BASE_URL=https://www.docusign.net/restapi  # production

{BOLD}3. Installer le SDK{RESET}
   pip install docusign-esign

{BOLD}4. Exemple d'intégration dans modules/documents/signature_electronique.py{RESET}
""")
    print("""
   # Dans la méthode signer_document() :
   import docusign_esign as docusign

   api_client = docusign.ApiClient()
   api_client.set_base_path(settings.DOCUSIGN_BASE_URL)
   api_client.set_oauth_host_name("account-d.docusign.com")  # recette

   # Authentification JWT (recommandé pour intégration serveur)
   token = api_client.request_jwt_application_token(
       client_id=settings.DOCUSIGN_CLIENT_ID,
       rsa_private_key_bytes=Path(settings.DOCUSIGN_RSA_KEY_PATH).read_bytes(),
       oauth_host_name="account-d.docusign.com",
       expires_in=3600,
   )
   api_client.set_default_header("Authorization", f"Bearer {token.access_token}")

   # Créer l'enveloppe (document à signer)
   envelope_def = docusign.EnvelopeDefinition(
       email_subject="Votre contrat YukpoAssurance à signer",
       status="sent",
       documents=[docusign.Document(
           document_base64=base64.b64encode(pdf_bytes).decode(),
           name="contrat.pdf",
           file_extension="pdf",
           document_id="1",
       )],
       recipients=docusign.Recipients(signers=[
           docusign.Signer(
               email=assure_email,
               name=assure_nom,
               recipient_id="1",
               routing_order="1",
               tabs=docusign.Tabs(sign_here_tabs=[
                   docusign.SignHere(
                       anchor_string="SIGNATURE_ASSURE",
                       anchor_y_offset="-20",
                       anchor_units="pixels",
                   )
               ]),
           )
       ]),
   )

   envelopes_api = docusign.EnvelopesApi(api_client)
   result = envelopes_api.create_envelope(settings.DOCUSIGN_ACCOUNT_ID, envelope_definition=envelope_def)
   envelope_id = result.envelope_id
   # → Stocker envelope_id en base pour vérifier la signature plus tard
""")

    info("Documentation complète : https://developers.docusign.com/docs/esign-rest-api/")


# ─── 4. Guide Yousign ────────────────────────────────────────────────────────

def guide_yousign() -> None:
    header("Intégration Yousign (Alternative RGPD, serveurs France/UE)")
    print(f"""
{BOLD}Yousign — API REST{RESET}
Coût : à partir de €26/mois (3 utilisateurs) ou €0.15/signature (API)
Niveau légal : Qualifié eIDAS — reconnu dans l'UE et reconnu dans les pays OHADA
Avantage CIMA : Conforme RGPD, données hébergées en France

{BOLD}1. Créer un compte{RESET}
   https://yousign.com/fr-fr/api-signature-electronique

{BOLD}2. Variables d'environnement{RESET}
   YOUSIGN_API_KEY=VOTRE_CLE_API_YOUSIGN
   YOUSIGN_BASE_URL=https://staging-api.yousign.app/v3  # recette
   # YOUSIGN_BASE_URL=https://api.yousign.app/v3        # production

{BOLD}3. Installer les dépendances{RESET}
   pip install httpx  # déjà inclus dans requirements.txt

{BOLD}4. Exemple d'intégration{RESET}
""")
    print("""
   import httpx, base64

   async def signer_via_yousign(pdf_bytes: bytes, signataire: dict) -> str:
       headers = {
           "Authorization": f"Bearer {settings.YOUSIGN_API_KEY}",
           "Content-Type": "application/json",
       }
       async with httpx.AsyncClient(base_url=settings.YOUSIGN_BASE_URL) as client:
           # 1. Uploader le document
           upload_r = await client.post("/documents", json={
               "nature": "signable_document",
               "content": base64.b64encode(pdf_bytes).decode(),
               "filename": "contrat_assurance.pdf",
           }, headers=headers)
           doc_id = upload_r.json()["id"]

           # 2. Créer la demande de signature
           sign_r = await client.post("/signature_requests", json={
               "name": f"Contrat {signataire['police_numero']}",
               "delivery_mode": "email",
               "documents": [{"id": doc_id}],
               "signers": [{
                   "info": {
                       "first_name": signataire["prenom"],
                       "last_name": signataire["nom"],
                       "email": signataire["email"],
                       "phone_number": signataire.get("telephone", ""),
                       "locale": "fr",
                   },
                   "fields": [{
                       "document_id": doc_id,
                       "type": "signature",
                       "page": 1,
                       "x": 400, "y": 700,
                       "width": 150, "height": 50,
                   }],
               }],
           }, headers=headers)
           request_id = sign_r.json()["id"]

           # 3. Activer (envoyer le lien par email au signataire)
           await client.post(f"/signature_requests/{request_id}/activate", headers=headers)

           return request_id  # → Stocker en base pour webhook de confirmation
""")

    info("Documentation : https://developers.yousign.com/reference/introduction")
    info("Webhook de confirmation : configurer YOUSIGN_WEBHOOK_SECRET dans .env")


# ─── 5. Mise à jour signature_electronique.py ──────────────────────────────

def afficher_integration_module() -> None:
    """Montre comment brancher la PKI dans le module de signature existant."""
    header("Intégration dans modules/documents/signature_electronique.py")
    print(f"""
{BOLD}Le module existant (SHA-256 + HMAC) doit être étendu avec un backend PKI.{RESET}
Ajouter une méthode signer_pki() qui délègue à Docusign ou Yousign selon la config :

    # Dans config/settings.py :
    SIGNATURE_BACKEND: str = "hmac"  # "hmac" | "pki_local" | "docusign" | "yousign"

    # Dans modules/documents/signature_electronique.py :
    class SignatureElectronique:
        async def signer(self, pdf_bytes, signataire, type_doc) -> dict:
            backend = settings.SIGNATURE_BACKEND
            if backend == "hmac":
                return await self._signer_hmac(pdf_bytes, signataire, type_doc)
            elif backend == "pki_local":
                return await self._signer_pki_local(pdf_bytes, signataire, type_doc)
            elif backend == "docusign":
                return await self._signer_docusign(pdf_bytes, signataire, type_doc)
            elif backend == "yousign":
                return await self._signer_yousign(pdf_bytes, signataire, type_doc)
            raise ValueError(f"Backend signature inconnu : {{backend}}")

{BOLD}Stratégie recommandée pour déploiement progressif :{RESET}
    Phase 1 (maintenant)  : SIGNATURE_BACKEND=hmac      → usage interne/GED
    Phase 2 (3 mois)      : SIGNATURE_BACKEND=pki_local → tests + recette
    Phase 3 (production)  : SIGNATURE_BACKEND=yousign   → contrats légaux clients
""")


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="YukpoAssurance — PKI Signature Configuration")
    parser.add_argument("--action", choices=[
        "generer-ca", "tester-signature", "verifier",
        "guide-docusign", "guide-yousign", "integration",
    ], default="integration")
    parser.add_argument("--org",   default="YukpoAssurance")
    parser.add_argument("--pays",  default="CM", help="Code pays ISO 2 lettres")
    parser.add_argument("--pdf",   default="test_contrat.pdf")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═'*62}{RESET}")
    print(f"{BOLD}  YukpoAssurance — Configuration PKI / Signature Électronique{RESET}")
    print(f"{BOLD}{'═'*62}{RESET}\n")

    if args.action == "generer-ca":
        generer_ca(args.org, args.pays)
    elif args.action == "tester-signature":
        tester_signature_pdf(args.pdf)
    elif args.action == "guide-docusign":
        guide_docusign()
    elif args.action == "guide-yousign":
        guide_yousign()
    elif args.action == "integration":
        afficher_integration_module()
        guide_yousign()
    else:
        warn(f"Action {args.action} non implémentée")


if __name__ == "__main__":
    main()
