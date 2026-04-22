"""
CvDocumentBuilder — Générateur DOCX pour CV et lettres de motivation.

Interface principale :
    builder = CvDocumentBuilder(profil)
    chemin = await builder.generer_cv(contenu_md, nom_base="cv_jean_dupont")
    chemin = await builder.generer_lettre(contenu_txt, nom_base="lm_jean_dupont")

Sorties :
    - DOCX  (python-docx)   — format éditable par défaut
    - PDF   (via LibreOffice si disponible, sinon fallback Markdown)
    - Markdown — toujours disponible

Layout CV :
    - En-tête coloré avec nom + titre professionnel + coordonnées
    - Sections structurées (EXPÉRIENCE, FORMATION, COMPÉTENCES…)
    - Police : Calibri 11, marges 2.5 cm, couleur accent Yukpo #0047AB

Layout Lettre de motivation :
    - Bloc adresse expéditeur/destinataire
    - Corps avec paragraphes justifiés
    - Formule de politesse + signature
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.cv_document_builder")

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "generated" / "cv_docs"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Couleurs de la charte Yukpo
_COULEUR_ACCENT   = (0x00, 0x47, 0xAB)   # bleu Yukpo
_COULEUR_SECONDAIRE = (0x1A, 0x1A, 0x2E) # bleu marine
_COULEUR_TEXTE    = (0x33, 0x33, 0x33)   # gris foncé
_COULEUR_GRIS     = (0x77, 0x77, 0x77)   # gris moyen


class CvDocumentBuilder:
    """Constructeur de documents CV/LM avec python-docx."""

    def __init__(self, profil=None):
        self._profil = profil

    # ──────────────────────────────────────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────────────────────────────────────

    async def generer_cv(
        self,
        contenu_md: str,
        nom_base: str = "cv",
        format_sortie: str = "docx",
    ) -> dict:
        """
        Génère un CV au format DOCX ou PDF à partir de texte Markdown.
        Retourne {"chemin_fichier": str, "nom_fichier": str, "format": str}.
        """
        nom_fichier = self._nom_unique(nom_base, format_sortie)
        chemin = _OUTPUT_DIR / nom_fichier

        if format_sortie == "docx":
            chemin = await self._construire_cv_docx(chemin, contenu_md)
        elif format_sortie == "pdf":
            chemin_docx = await self._construire_cv_docx(
                _OUTPUT_DIR / nom_fichier.replace(".pdf", ".docx"), contenu_md
            )
            chemin = self._convertir_pdf(chemin_docx, chemin)
        else:
            # Markdown pur
            chemin = _OUTPUT_DIR / nom_fichier
            chemin.write_text(contenu_md, encoding="utf-8")

        return {
            "chemin_fichier": str(chemin),
            "nom_fichier": chemin.name,
            "format": format_sortie,
        }

    async def generer_lettre(
        self,
        contenu_txt: str,
        nom_base: str = "lettre_motivation",
        format_sortie: str = "docx",
    ) -> dict:
        """
        Génère une lettre de motivation au format DOCX ou PDF.
        Retourne {"chemin_fichier": str, "nom_fichier": str, "format": str}.
        """
        nom_fichier = self._nom_unique(nom_base, format_sortie)
        chemin = _OUTPUT_DIR / nom_fichier

        if format_sortie == "docx":
            chemin = await self._construire_lettre_docx(chemin, contenu_txt)
        elif format_sortie == "pdf":
            chemin_docx = await self._construire_lettre_docx(
                _OUTPUT_DIR / nom_fichier.replace(".pdf", ".docx"), contenu_txt
            )
            chemin = self._convertir_pdf(chemin_docx, chemin)
        else:
            chemin = _OUTPUT_DIR / nom_fichier
            chemin.write_text(contenu_txt, encoding="utf-8")

        return {
            "chemin_fichier": str(chemin),
            "nom_fichier": chemin.name,
            "format": format_sortie,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Construction DOCX — CV
    # ──────────────────────────────────────────────────────────────────────────

    async def _construire_cv_docx(self, chemin: Path, contenu_md: str) -> Path:
        """Construit le fichier DOCX CV."""
        try:
            from docx import Document
            from docx.shared import Pt, RGBColor, Cm
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError:
            logger.warning("[CvDocumentBuilder] python-docx non disponible — fallback Markdown")
            chemin_md = chemin.with_suffix(".md")
            chemin_md.write_text(contenu_md, encoding="utf-8")
            return chemin_md

        doc = Document()

        # ── Marges ────────────────────────────────────────────────────────
        for section in doc.sections:
            section.top_margin    = Cm(2.0)
            section.bottom_margin = Cm(2.0)
            section.left_margin   = Cm(2.5)
            section.right_margin  = Cm(2.0)

        # ── Parser le Markdown en sections CV ─────────────────────────────
        blocs = _parser_md_cv(contenu_md)

        for bloc in blocs:
            typ = bloc["type"]
            texte = bloc["texte"]

            if typ == "h1":
                # Nom du candidat (premier H1)
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(texte.upper())
                run.bold = True
                run.font.size = Pt(18)
                run.font.color.rgb = RGBColor(*_COULEUR_SECONDAIRE)
                p.paragraph_format.space_after = Pt(2)

            elif typ == "titre_pro":
                # Titre professionnel (ligne en italique sous le nom)
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(texte)
                run.italic = True
                run.font.size = Pt(12)
                run.font.color.rgb = RGBColor(*_COULEUR_ACCENT)
                p.paragraph_format.space_after = Pt(4)

            elif typ == "contact":
                # Ligne de contact (email, tél, ville)
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(texte)
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(*_COULEUR_GRIS)
                p.paragraph_format.space_after = Pt(6)
                # Ligne horizontale de séparation
                _ajouter_separateur(doc)

            elif typ == "h2":
                # Titre de section (EXPÉRIENCE, FORMATION, etc.)
                doc.add_paragraph()  # espace avant
                p = doc.add_paragraph()
                run = p.add_run(texte.upper())
                run.bold = True
                run.font.size = Pt(12)
                run.font.color.rgb = RGBColor(*_COULEUR_ACCENT)
                p.paragraph_format.space_after = Pt(2)
                _ajouter_separateur_fin(doc)

            elif typ == "h3":
                # Sous-titre (poste ou diplôme)
                p = doc.add_paragraph()
                run = p.add_run(texte)
                run.bold = True
                run.font.size = Pt(11)
                run.font.color.rgb = RGBColor(*_COULEUR_TEXTE)
                p.paragraph_format.space_before = Pt(4)
                p.paragraph_format.space_after  = Pt(1)

            elif typ == "bullet":
                p = doc.add_paragraph(style="List Bullet")
                _ajouter_texte_gras_inline(p, texte, Pt(10.5))
                p.paragraph_format.space_after = Pt(1)

            elif typ == "texte":
                if not texte.strip():
                    continue
                p = doc.add_paragraph()
                _ajouter_texte_gras_inline(p, texte, Pt(10.5))
                p.paragraph_format.space_after = Pt(2)

        # ── Pied de page discret ───────────────────────────────────────────
        _ajouter_pied_cv(doc)

        chemin_docx = chemin.with_suffix(".docx")
        doc.save(str(chemin_docx))
        logger.info(f"[CvDocumentBuilder] CV généré : {chemin_docx.name}")
        return chemin_docx

    # ──────────────────────────────────────────────────────────────────────────
    # Construction DOCX — Lettre de motivation
    # ──────────────────────────────────────────────────────────────────────────

    async def _construire_lettre_docx(self, chemin: Path, contenu_txt: str) -> Path:
        """Construit le fichier DOCX lettre de motivation."""
        try:
            from docx import Document
            from docx.shared import Pt, RGBColor, Cm
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError:
            logger.warning("[CvDocumentBuilder] python-docx non disponible — fallback Markdown")
            chemin_md = chemin.with_suffix(".md")
            chemin_md.write_text(contenu_txt, encoding="utf-8")
            return chemin_md

        doc = Document()

        # ── Marges ────────────────────────────────────────────────────────
        for section in doc.sections:
            section.top_margin    = Cm(3.0)
            section.bottom_margin = Cm(2.5)
            section.left_margin   = Cm(3.0)
            section.right_margin  = Cm(2.5)

        # ── En-tête discret ───────────────────────────────────────────────
        p_header = doc.add_paragraph()
        run_h = p_header.add_run("Lettre de Motivation")
        run_h.font.size = Pt(9)
        run_h.font.color.rgb = RGBColor(*_COULEUR_GRIS)
        run_h.italic = True

        doc.add_paragraph()

        # ── Corps de la lettre ─────────────────────────────────────────────
        # Détecter les paragraphes naturels du texte
        paragraphes = [p.strip() for p in contenu_txt.split("\n\n") if p.strip()]

        for i, para in enumerate(paragraphes):
            # Supprimer les astérisques Markdown résiduels
            para_propre = re.sub(r"\*\*(.+?)\*\*", r"\1", para)
            para_propre = re.sub(r"\*(.+?)\*", r"\1", para_propre)

            p = doc.add_paragraph()
            run = p.add_run(para_propre)
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(*_COULEUR_TEXTE)

            # Justification pour les paragraphes de corps
            if i > 2:  # Sauter les blocs d'adresse
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

            p.paragraph_format.space_after = Pt(6)

        # ── Pied de page discret ───────────────────────────────────────────
        _ajouter_pied_lettre(doc)

        chemin_docx = chemin.with_suffix(".docx")
        doc.save(str(chemin_docx))
        logger.info(f"[CvDocumentBuilder] Lettre générée : {chemin_docx.name}")
        return chemin_docx

    # ──────────────────────────────────────────────────────────────────────────
    # Conversion PDF
    # ──────────────────────────────────────────────────────────────────────────

    def _convertir_pdf(self, chemin_docx: Path, chemin_pdf: Path) -> Path:
        """
        Convertit DOCX en PDF via LibreOffice (si disponible).
        Fallback : retourne le DOCX si LibreOffice absent.
        """
        import subprocess
        import shutil

        # Chercher LibreOffice
        for cmd in ("libreoffice", "soffice", "libreoffice7"):
            if shutil.which(cmd):
                try:
                    subprocess.run(
                        [cmd, "--headless", "--convert-to", "pdf",
                         "--outdir", str(chemin_pdf.parent), str(chemin_docx)],
                        check=True, capture_output=True, timeout=30,
                    )
                    # LibreOffice crée le PDF avec le même nom de base
                    pdf_cree = chemin_pdf.parent / (chemin_docx.stem + ".pdf")
                    if pdf_cree.exists():
                        return pdf_cree
                except Exception as e:
                    logger.warning(f"[CvDocumentBuilder] Conversion PDF échouée: {e}")
                break

        logger.info("[CvDocumentBuilder] LibreOffice absent — retour DOCX en lieu de PDF")
        return chemin_docx  # Retourner le DOCX si PDF impossible

    # ──────────────────────────────────────────────────────────────────────────
    # Utilitaires
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _nom_unique(nom_base: str, format_sortie: str) -> str:
        ext = {"docx": ".docx", "pdf": ".pdf", "markdown": ".md"}.get(format_sortie, ".docx")
        # Nettoyer le nom de base
        nom_propre = re.sub(r"[^a-zA-Z0-9_-]", "_", nom_base)[:40]
        uid = uuid.uuid4().hex[:6]
        horodatage = datetime.now().strftime("%Y%m%d")
        return f"{nom_propre}_{horodatage}_{uid}{ext}"


# ──────────────────────────────────────────────────────────────────────────────
# Parseur Markdown CV → blocs sémantiques
# ──────────────────────────────────────────────────────────────────────────────

def _parser_md_cv(contenu_md: str) -> list[dict]:
    """
    Transforme le Markdown généré par l'IA en blocs sémantiques pour le DOCX.
    Identifie : nom (h1), titre_pro (italique sous h1), contact, sections (h2),
    sous-titres (h3), bullets, texte.
    """
    blocs = []
    lignes = contenu_md.split("\n")
    apres_h1 = False
    h1_count = 0

    for ligne in lignes:
        ligne_propre = ligne.strip()
        if not ligne_propre:
            continue

        # H1 — Nom du candidat
        if ligne_propre.startswith("# "):
            texte = ligne_propre[2:].strip()
            # Nettoyer le Markdown inline
            texte = re.sub(r"\*\*(.+?)\*\*", r"\1", texte)
            blocs.append({"type": "h1", "texte": texte})
            apres_h1 = True
            h1_count += 1
            continue

        # H2 — Titre de section principale
        if ligne_propre.startswith("## "):
            texte = ligne_propre[3:].strip()
            texte = re.sub(r"\*\*(.+?)\*\*", r"\1", texte)
            blocs.append({"type": "h2", "texte": texte})
            apres_h1 = False
            continue

        # H3 — Sous-titre (poste, diplôme)
        if ligne_propre.startswith("### "):
            texte = ligne_propre[4:].strip()
            texte = re.sub(r"\*\*(.+?)\*\*", r"\1", texte)
            blocs.append({"type": "h3", "texte": texte})
            apres_h1 = False
            continue

        # Bullet point
        if ligne_propre.startswith("- ") or ligne_propre.startswith("* ") or ligne_propre.startswith("• "):
            texte = ligne_propre[2:].strip()
            blocs.append({"type": "bullet", "texte": texte})
            apres_h1 = False
            continue

        # Ligne de contact (contient @ ou tél patterns)
        if apres_h1 and h1_count == 1 and (
            "@" in ligne_propre
            or re.search(r"\+?\d[\d\s\-\(\)]{6,}", ligne_propre)
            or any(c in ligne_propre.lower() for c in ("linkedin", "github", "tel:", "tél:"))
        ):
            texte = re.sub(r"\*\*(.+?)\*\*", r"\1", ligne_propre)
            blocs.append({"type": "contact", "texte": texte})
            continue

        # Ligne en italique après H1 = titre professionnel
        if apres_h1 and h1_count == 1 and ligne_propre.startswith("*") and ligne_propre.endswith("*"):
            texte = ligne_propre.strip("*").strip()
            blocs.append({"type": "titre_pro", "texte": texte})
            continue

        # Texte normal
        texte = re.sub(r"\*\*(.+?)\*\*", r"\1", ligne_propre)  # supprimer gras inline
        blocs.append({"type": "texte", "texte": texte})

    return blocs


# ──────────────────────────────────────────────────────────────────────────────
# Helpers python-docx
# ──────────────────────────────────────────────────────────────────────────────

def _ajouter_separateur(doc):
    """Ajoute une ligne horizontale (simulée par un paragraphe avec bordure basse)."""
    try:
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        from docx.shared import Pt, RGBColor

        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after  = Pt(4)
        # Bordure basse via XML
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "0047AB")
        pBdr.append(bottom)
        pPr.append(pBdr)
    except Exception:
        doc.add_paragraph()


def _ajouter_separateur_fin(doc):
    """Ligne fine sous les titres de section."""
    try:
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        from docx.shared import Pt

        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(2)
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "2")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "CCCCCC")
        pBdr.append(bottom)
        pPr.append(pBdr)
    except Exception:
        pass


def _ajouter_texte_gras_inline(p, texte: str, taille):
    """Ajoute un run en gérant les **texte** gras inline restants."""
    from docx.shared import RGBColor

    parties = re.split(r"(\*\*[^*]+\*\*)", texte)
    for partie in parties:
        if partie.startswith("**") and partie.endswith("**"):
            run = p.add_run(partie[2:-2])
            run.bold = True
        else:
            run = p.add_run(partie)
        run.font.size = taille
        run.font.color.rgb = RGBColor(*_COULEUR_TEXTE)


def _ajouter_pied_cv(doc):
    """Pied de page discret : 'Généré par Yukpo Pro'."""
    try:
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        section = doc.sections[0]
        footer  = section.footer
        p = footer.paragraphs[0]
        p.clear()
        run = p.add_run(f"Document généré par Yukpo Pro — {datetime.now().strftime('%d/%m/%Y')}")
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        pass


def _ajouter_pied_lettre(doc):
    """Pied de page lettre."""
    try:
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        section = doc.sections[0]
        footer  = section.footer
        p = footer.paragraphs[0]
        p.clear()
        run = p.add_run(f"Lettre générée par Yukpo Pro — {datetime.now().strftime('%d/%m/%Y')}")
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        pass
