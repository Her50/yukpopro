"""
YukpoAssurance — Pipeline OCR complet (v2 — Production)
Extraction de texte depuis images et PDFs, structuration JSON pour SI assurance.

Workflow :
1. Prétraitement image (deskew, denoise, binarisation adaptative)
2. OCR via Tesseract (multi-langue : fra, eng)
3. Post-traitement (nettoyage, détection structurelle)
4. Structuration JSON via IA Claude (mapping vers structures ORASS/PCSA)
5. Validation des données extraites

Formats supportés : PNG, JPEG, TIFF, BMP, PDF (converti en images)
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.ocr")


class TypeDocument(str, Enum):
    FACTURE          = "facture"
    BORDEREAU        = "bordereau"
    QUITTANCE        = "quittance"
    CONSTAT_SINISTRE = "constat_sinistre"
    RAPPORT_MEDICAL  = "rapport_medical"
    CNI              = "cni"
    PERMIS_CONDUIRE  = "permis_conduire"
    CARTE_GRISE      = "carte_grise"
    ATTESTATION      = "attestation"
    RECU_PAIEMENT    = "recu_paiement"
    BILAN_COMPTABLE  = "bilan_comptable"
    INCONNU          = "inconnu"


@dataclass
class ResultatOCR:
    texte_brut: str
    confiance: float                  # 0.0-1.0
    langue_detectee: str
    type_document: TypeDocument
    donnees_structurees: dict[str, Any]
    champs_manquants: list[str]
    avertissements: list[str] = field(default_factory=list)
    pages_traitees: int = 1


class OCRProcessor:
    """
    Processeur OCR principal pour YukpoAssurance.
    Prétraite, extrait le texte, puis structure les données pour le SI assurance.
    """

    LANGUES_TESSERACT = "fra+eng"   # Français + Anglais (zone CIMA)
    TESSERACT_CONFIG  = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÉÈÊËÎÏÔÙÛÜÇàâäéèêëîïôùûüç/\\-.,;:()@%€$ "

    # ─── Prétraitement image ──────────────────────────────────────────────────

    def _preparer_image(self, image_bytes: bytes) -> "Any":
        """
        Prétraitement de l'image pour améliorer la qualité OCR.
        Pipeline : deskew → denoise → binarisation adaptative → resize.
        """
        try:
            from PIL import Image, ImageFilter, ImageEnhance
            import numpy as np
        except ImportError:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            return img.convert("L")  # Fallback minimal

        img = Image.open(io.BytesIO(image_bytes))

        # Convertir en RGB si nécessaire
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # 1. Redimensionner si trop petit (OCR inefficace < 300 DPI)
        w, h = img.size
        if w < 1000 or h < 1000:
            factor = max(1000 / w, 1000 / h, 2.0)
            img = img.resize((int(w * factor), int(h * factor)), Image.LANCZOS)

        # 2. Convertir en niveaux de gris
        img_gray = img.convert("L")

        # 3. Amélioration du contraste
        enhancer = ImageEnhance.Contrast(img_gray)
        img_gray = enhancer.enhance(2.0)

        # 4. Deskew (correction de l'inclinaison) via numpy si disponible
        try:
            arr = np.array(img_gray)
            # Binarisation simple pour trouver l'angle
            binary = arr < 128
            # Projections horizontales pour détecter l'inclinaison
            from PIL import Image as PILImage
            # Deskew basé sur les moments de l'image
            from scipy.ndimage import rotate as scipy_rotate
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Projections pour angle
                projections = np.sum(binary, axis=1)
                if len(projections) > 10:
                    # Angle optimal = minimise la variance des projections
                    best_angle = 0.0
                    best_var = np.var(projections)
                    for angle in range(-10, 11):
                        rotated = scipy_rotate(binary.astype(float), angle, reshape=False)
                        proj_var = np.var(np.sum(rotated > 0.5, axis=1))
                        if proj_var > best_var:
                            best_var = proj_var
                            best_angle = angle
                    if abs(best_angle) > 0.5:
                        arr_rotated = scipy_rotate(np.array(img_gray), best_angle, reshape=False, cval=255)
                        img_gray = PILImage.fromarray(arr_rotated.astype(np.uint8))
        except Exception:
            pass  # Deskew non critique

        # 5. Filtre de netteté
        try:
            img_gray = img_gray.filter(ImageFilter.SHARPEN)
        except Exception:
            pass

        return img_gray

    def _pdf_vers_images(self, pdf_bytes: bytes) -> list[bytes]:
        """Convertit un PDF en liste d'images (une par page)."""
        images_bytes = []
        try:
            from pdf2image import convert_from_bytes
            images_pil = convert_from_bytes(pdf_bytes, dpi=300, fmt="PNG")
            for img in images_pil:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                images_bytes.append(buf.getvalue())
            return images_bytes
        except ImportError:
            logger.warning("[OCR] pdf2image non disponible — conversion PDF désactivée")
            return []
        except Exception as e:
            logger.error(f"[OCR] Conversion PDF échouée: {e}")
            return []

    # ─── Extraction OCR ───────────────────────────────────────────────────────

    def _extraire_texte_image(self, image_prepara: Any) -> tuple[str, float]:
        """Extrait le texte d'une image préparée. Retourne (texte, confiance 0-1)."""
        try:
            import pytesseract
            # Extraction avec données de confiance
            data = pytesseract.image_to_data(
                image_prepara,
                lang=self.LANGUES_TESSERACT,
                output_type=pytesseract.Output.DICT,
                config=self.TESSERACT_CONFIG,
            )
            # Calculer la confiance moyenne (on ignore les conf=-1)
            confs = [c for c in data["conf"] if int(c) >= 0]
            confiance = sum(confs) / len(confs) / 100.0 if confs else 0.0

            # Extraire le texte
            texte = pytesseract.image_to_string(
                image_prepara,
                lang=self.LANGUES_TESSERACT,
                config=self.TESSERACT_CONFIG,
            )
            return texte.strip(), confiance
        except ImportError:
            logger.error("[OCR] Tesseract non installé. Installez : apt-get install tesseract-ocr tesseract-ocr-fra")
            return "", 0.0
        except Exception as e:
            logger.error(f"[OCR] Extraction texte échouée: {e}")
            return "", 0.0

    # ─── Détection du type de document ───────────────────────────────────────

    def _detecter_type_document(self, texte: str) -> TypeDocument:
        """Détecte automatiquement le type de document depuis le texte extrait."""
        texte_l = texte.lower()

        if any(k in texte_l for k in ["facture", "invoice", "montant dû", "total ht", "tva"]):
            return TypeDocument.FACTURE
        if any(k in texte_l for k in ["bordereau", "prime nette", "bordereau de production"]):
            return TypeDocument.BORDEREAU
        if any(k in texte_l for k in ["quittance", "avis d'échéance", "reçu de paiement prime"]):
            return TypeDocument.QUITTANCE
        if any(k in texte_l for k in ["constat amiable", "déclaration de sinistre", "constat d'accident"]):
            return TypeDocument.CONSTAT_SINISTRE
        if any(k in texte_l for k in ["rapport médical", "certificat médical", "diagnostic", "ordonnance"]):
            return TypeDocument.RAPPORT_MEDICAL
        if any(k in texte_l for k in ["carte nationale", "cni", "numéro national", "né le"]):
            return TypeDocument.CNI
        if any(k in texte_l for k in ["permis de conduire", "catégorie b", "driving licence"]):
            return TypeDocument.PERMIS_CONDUIRE
        if any(k in texte_l for k in ["carte grise", "certificat d'immatriculation", "immatriculé"]):
            return TypeDocument.CARTE_GRISE
        if any(k in texte_l for k in ["attestation d'assurance", "numéro de police", "assuré"]):
            return TypeDocument.ATTESTATION
        if any(k in texte_l for k in ["reçu", "reçu de caisse", "montant reçu"]):
            return TypeDocument.RECU_PAIEMENT
        if any(k in texte_l for k in ["bilan", "résultat net", "actif", "passif", "fonds propres"]):
            return TypeDocument.BILAN_COMPTABLE

        return TypeDocument.INCONNU

    # ─── Structuration via IA ─────────────────────────────────────────────────

    async def _structurer_via_ia(
        self,
        texte_brut: str,
        type_doc: TypeDocument,
        contexte: Optional[dict] = None,
    ) -> dict:
        """
        Utilise Claude pour extraire les champs structurés depuis le texte OCR.
        Retourne un dict JSON compatible avec les structures SI (ORASS/PCSA).
        """
        from core.ia_client import ia_client, ModeIA

        prompts_par_type = {
            TypeDocument.FACTURE: """Extrais ces champs JSON depuis la facture :
{
  "numero_facture": "...",
  "date_facture": "YYYY-MM-DD",
  "fournisseur_nom": "...",
  "fournisseur_adresse": "...",
  "client_nom": "...",
  "montant_ht": 0.0,
  "tva_pct": 0.0,
  "montant_tva": 0.0,
  "montant_ttc": 0.0,
  "devise": "FCFA",
  "nature_frais": "...",
  "compte_pcsa": "...",
  "lignes": [{"designation": "...", "quantite": 1, "prix_unitaire": 0.0, "montant": 0.0}]
}""",
            TypeDocument.QUITTANCE: """Extrais ces champs JSON depuis la quittance :
{
  "numero_quittance": "...",
  "numero_police": "...",
  "nom_assure": "...",
  "periode_debut": "YYYY-MM-DD",
  "periode_fin": "YYYY-MM-DD",
  "prime_nette": 0.0,
  "taxes": 0.0,
  "prime_ttc": 0.0,
  "mode_paiement": "...",
  "branche": "auto|vie|ird|rc|transport|mrh",
  "compagnie": "..."
}""",
            TypeDocument.CONSTAT_SINISTRE: """Extrais ces champs JSON depuis le constat :
{
  "date_accident": "YYYY-MM-DD",
  "heure_accident": "HH:MM",
  "lieu_accident": "...",
  "conducteur_a_nom": "...",
  "conducteur_a_immatriculation": "...",
  "conducteur_a_assureur": "...",
  "conducteur_a_police": "...",
  "conducteur_b_nom": "...",
  "conducteur_b_immatriculation": "...",
  "conducteur_b_assureur": "...",
  "circonstances": "...",
  "responsabilite_estimee_a": 50,
  "blesses": false,
  "dommages_corporels": false
}""",
            TypeDocument.RAPPORT_MEDICAL: """Extrais ces champs JSON depuis le rapport médical :
{
  "patient_nom": "...",
  "date_examen": "YYYY-MM-DD",
  "medecin_nom": "...",
  "diagnostic_principal": "...",
  "code_diagnostic": "...",
  "incapacite_jours": 0,
  "hospitalisation_jours": 0,
  "montant_soins": 0.0,
  "invalidite_permanente_pct": 0,
  "date_consolidation": null,
  "recommandations": "..."
}""",
            TypeDocument.CARTE_GRISE: """Extrais ces champs JSON depuis la carte grise :
{
  "immatriculation": "...",
  "marque": "...",
  "modele": "...",
  "type_vehicule": "...",
  "annee_mise_en_circulation": 0,
  "numero_chassis": "...",
  "puissance_fiscale": 0,
  "energie": "essence|diesel|electrique",
  "proprietaire_nom": "...",
  "proprietaire_adresse": "..."
}""",
            TypeDocument.BORDEREAU: """Extrais ces champs JSON depuis le bordereau :
{
  "numero_bordereau": "...",
  "date_bordereau": "YYYY-MM-DD",
  "courtier_nom": "...",
  "courtier_code": "...",
  "periode": "...",
  "primes_brutes": 0.0,
  "commissions": 0.0,
  "primes_nettes": 0.0,
  "nombre_contrats": 0,
  "branche": "...",
  "observations": "..."
}""",
        }

        schema_json = prompts_par_type.get(
            type_doc,
            '{"type_document": "inconnu", "texte_complet": "...", "donnees": {}}'
        )

        contexte_str = f"\nContexte additionnel : {contexte}" if contexte else ""
        prompt = f"""Tu es un expert en assurance CIMA. Analyse ce texte extrait par OCR et structure les données.

TEXTE OCR :
```
{texte_brut[:6000]}
```
{contexte_str}

SCHÉMA JSON À REMPLIR (retourne UNIQUEMENT le JSON valide, sans markdown) :
{schema_json}

Règles :
- Utilise null pour les champs non trouvés
- Les montants en FCFA (ou EUR si spécifié)
- Dates au format YYYY-MM-DD
- Si le texte OCR est illisible sur certains champs, mets null
- IMPORTANT : retourne UNIQUEMENT le JSON, pas d'explication"""

        try:
            reponse = await ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.PRECISION,
                max_tokens=2048,
            )
            texte_reponse = reponse.contenu.strip()
            # Nettoyer le markdown si présent
            if texte_reponse.startswith("```"):
                texte_reponse = re.sub(r"^```(?:json)?\n?", "", texte_reponse)
                texte_reponse = re.sub(r"\n?```$", "", texte_reponse)
            import json
            return json.loads(texte_reponse)
        except Exception as e:
            logger.error(f"[OCR] Structuration IA échouée: {e}")
            return {"texte_brut": texte_brut[:500], "erreur": str(e)}

    def _valider_donnees(self, donnees: dict, type_doc: TypeDocument) -> tuple[list[str], list[str]]:
        """
        Valide les champs extraits. Retourne (champs_manquants, avertissements).
        """
        CHAMPS_OBLIGATOIRES = {
            TypeDocument.FACTURE:          ["numero_facture", "montant_ttc"],
            TypeDocument.QUITTANCE:        ["numero_police", "prime_ttc", "nom_assure"],
            TypeDocument.CONSTAT_SINISTRE: ["date_accident", "conducteur_a_immatriculation"],
            TypeDocument.RAPPORT_MEDICAL:  ["patient_nom", "date_examen", "diagnostic_principal"],
            TypeDocument.CARTE_GRISE:      ["immatriculation", "marque"],
        }

        manquants = []
        avertissements = []

        champs_req = CHAMPS_OBLIGATOIRES.get(type_doc, [])
        for champ in champs_req:
            if not donnees.get(champ):
                manquants.append(champ)

        # Vérifications métier
        if type_doc == TypeDocument.FACTURE:
            montant = donnees.get("montant_ttc", 0) or 0
            if isinstance(montant, (int, float)) and montant > 50_000_000:
                avertissements.append(f"Montant élevé ({montant:,.0f} FCFA) — validation manuelle requise")

        if type_doc == TypeDocument.QUITTANCE:
            police = donnees.get("numero_police", "")
            if police and not re.match(r'^[A-Z]{2,10}-\d{4}-', str(police)):
                avertissements.append("Format numéro de police non standard")

        return manquants, avertissements

    # ─── Point d'entrée principal ─────────────────────────────────────────────

    async def traiter_image(
        self,
        image_bytes: bytes,
        nom_fichier: str = "document",
        contexte: Optional[dict] = None,
    ) -> ResultatOCR:
        """
        Pipeline complet : prétraitement → OCR → structuration IA.
        Retourne un ResultatOCR avec les données prêtes pour le SI.
        """
        logger.info(f"[OCR] Traitement image: {nom_fichier} ({len(image_bytes)//1024} KB)")

        # Prétraitement
        img_prep = await asyncio.to_thread(self._preparer_image, image_bytes)

        # Extraction texte
        texte_brut, confiance = await asyncio.to_thread(
            self._extraire_texte_image, img_prep
        )

        if not texte_brut:
            return ResultatOCR(
                texte_brut="",
                confiance=0.0,
                langue_detectee="inconnue",
                type_document=TypeDocument.INCONNU,
                donnees_structurees={},
                champs_manquants=[],
                avertissements=["Aucun texte extrait — qualité image insuffisante"],
            )

        # Détection du type
        type_doc = self._detecter_type_document(texte_brut)
        logger.info(f"[OCR] Type détecté: {type_doc.value} (confiance: {confiance:.0%})")

        # Structuration IA
        donnees = await self._structurer_via_ia(texte_brut, type_doc, contexte)

        # Validation
        champs_manquants, avertissements = self._valider_donnees(donnees, type_doc)

        return ResultatOCR(
            texte_brut=texte_brut,
            confiance=confiance,
            langue_detectee="fra" if any(w in texte_brut.lower() for w in ["le", "la", "les", "de", "du"]) else "eng",
            type_document=type_doc,
            donnees_structurees=donnees,
            champs_manquants=champs_manquants,
            avertissements=avertissements,
        )

    async def traiter_pdf(
        self,
        pdf_bytes: bytes,
        nom_fichier: str = "document.pdf",
        contexte: Optional[dict] = None,
    ) -> ResultatOCR:
        """
        Traitement d'un PDF multi-pages.
        Chaque page est traitée séparément, les résultats sont fusionnés.
        """
        logger.info(f"[OCR] Traitement PDF: {nom_fichier} ({len(pdf_bytes)//1024} KB)")

        images = await asyncio.to_thread(self._pdf_vers_images, pdf_bytes)
        if not images:
            return ResultatOCR(
                texte_brut="",
                confiance=0.0,
                langue_detectee="inconnue",
                type_document=TypeDocument.INCONNU,
                donnees_structurees={},
                champs_manquants=[],
                avertissements=["Conversion PDF échouée — vérifier pdf2image et poppler"],
            )

        # Traiter chaque page
        textes_pages = []
        confidences = []
        for i, img_bytes in enumerate(images[:20]):  # Max 20 pages
            img_prep = await asyncio.to_thread(self._preparer_image, img_bytes)
            texte, conf = await asyncio.to_thread(self._extraire_texte_image, img_prep)
            textes_pages.append(f"[PAGE {i+1}]\n{texte}")
            confidences.append(conf)

        texte_complet = "\n\n".join(textes_pages)
        confiance_moy = sum(confidences) / len(confidences) if confidences else 0.0

        # Type basé sur l'ensemble du document
        type_doc = self._detecter_type_document(texte_complet)

        # Structuration IA (premier texte pertinent)
        donnees = await self._structurer_via_ia(texte_complet[:8000], type_doc, contexte)

        champs_manquants, avertissements = self._valider_donnees(donnees, type_doc)

        return ResultatOCR(
            texte_brut=texte_complet,
            confiance=confiance_moy,
            langue_detectee="fra",
            type_document=type_doc,
            donnees_structurees=donnees,
            champs_manquants=champs_manquants,
            avertissements=avertissements,
            pages_traitees=len(images),
        )

    async def traiter_fichier_base64(
        self,
        data_b64: str,
        nom_fichier: str,
        contexte: Optional[dict] = None,
    ) -> ResultatOCR:
        """Traite un fichier encodé en base64 (upload API)."""
        file_bytes = base64.b64decode(data_b64)
        ext = Path(nom_fichier).suffix.lower()
        if ext == ".pdf":
            return await self.traiter_pdf(file_bytes, nom_fichier, contexte)
        else:
            return await self.traiter_image(file_bytes, nom_fichier, contexte)


# Singleton
ocr_processor = OCRProcessor()
