"""
Générateur de contrats d'assurance — PDF complet avec profil compagnie.
Livraison via email (SMTP) et WhatsApp (Meta Cloud API).
"""

from __future__ import annotations

import io
import os
import textwrap
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

# ReportLab — pip install reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Email async — pip install aiosmtplib
import aiosmtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

# ─────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────

@dataclass
class ProfilCompagnie:
    nom: str
    adresse: str
    ville: str
    pays: str
    telephone: str
    email: str
    site_web: str = ""
    rccm: str = ""
    contribuable: str = ""
    agrement_crca: str = ""
    capital_social: str = ""
    logo_url: str = ""           # chemin local ou URL
    couleur_principale: str = "#003366"
    couleur_secondaire: str = "#E8F0FE"


@dataclass
class GarantieContrat:
    libelle: str
    capital_assure: float
    franchise: float = 0.0
    prime_nette: float = 0.0
    taux_taxe: float = 0.15
    observations: str = ""

    @property
    def taxe(self) -> float:
        return self.prime_nette * self.taux_taxe

    @property
    def prime_ttc(self) -> float:
        return self.prime_nette + self.taxe


@dataclass
class DonneesContrat:
    # Identification police
    numero_police: str
    type_contrat: str          # "AUTO", "MRH", "VIE", "RC", etc.
    branche: str               # libellé long

    # Assuré
    nom_assure: str
    prenom_assure: str = ""
    date_naissance: Optional[date] = None
    adresse_assure: str = ""
    telephone_assure: str = ""
    email_assure: str = ""
    numero_cni: str = ""

    # Période
    date_effet: date = field(default_factory=date.today)
    date_echeance: Optional[date] = None
    duree_mois: int = 12

    # Objet assuré (ex. voiture)
    objet_assure: str = ""          # ex. "Toyota Corolla - AA 123 AB"
    valeur_assure: float = 0.0

    # Garanties
    garanties: List[GarantieContrat] = field(default_factory=list)

    # Intermédiaire
    courtier: str = ""
    apporteur: str = ""

    # Références ORASS / Mercure
    ref_orass: str = ""
    ref_mercure: str = ""

    # Observations / clauses particulières
    clauses_particulieres: str = ""

    @property
    def prime_nette_totale(self) -> float:
        return sum(g.prime_nette for g in self.garanties)

    @property
    def taxe_totale(self) -> float:
        return sum(g.taxe for g in self.garanties)

    @property
    def prime_ttc_totale(self) -> float:
        return self.prime_nette_totale + self.taxe_totale

    @property
    def assure_complet(self) -> str:
        return f"{self.prenom_assure} {self.nom_assure}".strip()


# ─────────────────────────────────────────────────────────────
# Utilitaires formatage
# ─────────────────────────────────────────────────────────────

def _fmt_montant(v: float, devise: str = "FCFA") -> str:
    return f"{v:,.0f} {devise}".replace(",", " ")


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return "—"
    return d.strftime("%d/%m/%Y")


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return colors.Color(r / 255, g / 255, b / 255)


# ─────────────────────────────────────────────────────────────
# Générateur PDF
# ─────────────────────────────────────────────────────────────

class GenerateurContratPDF:

    def __init__(self, compagnie: ProfilCompagnie):
        self.compagnie = compagnie
        self._styles = getSampleStyleSheet()
        self._couleur = _hex_to_rgb(compagnie.couleur_principale)
        self._couleur2 = _hex_to_rgb(compagnie.couleur_secondaire)

    # ── Styles ──────────────────────────────────────────────

    def _style(self, name: str, **kwargs) -> ParagraphStyle:
        base = self._styles["Normal"]
        return ParagraphStyle(name, parent=base, **kwargs)

    # ── En-tête compagnie ───────────────────────────────────

    def _entete(self, contrat: DonneesContrat) -> list:
        elements = []
        cmp = self.compagnie

        # Ligne logo + nom compagnie
        logo_cell = ""
        if cmp.logo_url and Path(cmp.logo_url).exists():
            try:
                img = Image(cmp.logo_url, width=3.5 * cm, height=1.5 * cm)
                logo_cell = img
            except Exception:
                logo_cell = Paragraph(cmp.nom, self._style("logo_txt",
                    fontSize=14, textColor=self._couleur, fontName="Helvetica-Bold"))
        else:
            logo_cell = Paragraph(cmp.nom, self._style("logo_txt",
                fontSize=14, textColor=self._couleur, fontName="Helvetica-Bold"))

        info_compagnie = Paragraph(
            f"<b>{cmp.nom}</b><br/>"
            f"{cmp.adresse} — {cmp.ville}, {cmp.pays}<br/>"
            f"Tél : {cmp.telephone}  |  {cmp.email}<br/>"
            f"RCCM : {cmp.rccm}  |  N° Contribuable : {cmp.contribuable}<br/>"
            f"Agrément CRCA : {cmp.agrement_crca}  |  Capital : {cmp.capital_social}",
            self._style("cmp_info", fontSize=8, leading=12)
        )

        titre_doc = Paragraph(
            f"<b>CONTRAT D'ASSURANCE</b><br/>"
            f"<font size='9'>{contrat.branche}</font>",
            self._style("titre_doc", fontSize=13, textColor=self._couleur,
                        fontName="Helvetica-Bold", alignment=TA_RIGHT)
        )

        ref_doc = Paragraph(
            f"<b>N° Police :</b> {contrat.numero_police}<br/>"
            f"<b>Date émission :</b> {_fmt_date(date.today())}",
            self._style("ref_doc", fontSize=8, alignment=TA_RIGHT)
        )

        table = Table(
            [[logo_cell, info_compagnie, [titre_doc, Spacer(1, 4), ref_doc]]],
            colWidths=[3.5 * cm, 9 * cm, 5.5 * cm],
        )
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)
        elements.append(HRFlowable(width="100%", thickness=2, color=self._couleur,
                                   spaceAfter=6, spaceBefore=6))
        return elements

    # ── Bloc section ────────────────────────────────────────

    def _section(self, titre: str) -> list:
        bg = self._couleur
        p = Paragraph(f"<b>{titre.upper()}</b>",
                      self._style(f"sec_{titre}", fontSize=9, textColor=colors.white,
                                  fontName="Helvetica-Bold"))
        t = Table([[p]], colWidths=[18 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        return [Spacer(1, 0.3 * cm), t, Spacer(1, 0.15 * cm)]

    # ── Tableau 2 colonnes (clé: valeur) ───────────────────

    def _kv_table(self, rows: list[tuple[str, str]]) -> Table:
        data = [[
            Paragraph(f"<b>{k}</b>", self._style("kv_k", fontSize=8)),
            Paragraph(str(v), self._style("kv_v", fontSize=8)),
        ] for k, v in rows]
        t = Table(data, colWidths=[6 * cm, 12 * cm])
        t.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _hex_to_rgb("#f5f8ff")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ]))
        return t

    # ── Tableau garanties ───────────────────────────────────

    def _tableau_garanties(self, garanties: List[GarantieContrat]) -> Table:
        header = [
            Paragraph("<b>Garantie</b>", self._style("gh", fontSize=8, textColor=colors.white,
                                                      fontName="Helvetica-Bold")),
            Paragraph("<b>Capital assuré</b>", self._style("gh2", fontSize=8, textColor=colors.white,
                                                            fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            Paragraph("<b>Franchise</b>", self._style("gh3", fontSize=8, textColor=colors.white,
                                                       fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            Paragraph("<b>Prime nette</b>", self._style("gh4", fontSize=8, textColor=colors.white,
                                                         fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            Paragraph("<b>Taxe (15%)</b>", self._style("gh5", fontSize=8, textColor=colors.white,
                                                        fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            Paragraph("<b>Prime TTC</b>", self._style("gh6", fontSize=8, textColor=colors.white,
                                                       fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        ]
        rows = [header]
        for g in garanties:
            rows.append([
                Paragraph(g.libelle, self._style("gc", fontSize=8)),
                Paragraph(_fmt_montant(g.capital_assure), self._style("gr", fontSize=8, alignment=TA_RIGHT)),
                Paragraph(_fmt_montant(g.franchise), self._style("gr2", fontSize=8, alignment=TA_RIGHT)),
                Paragraph(_fmt_montant(g.prime_nette), self._style("gr3", fontSize=8, alignment=TA_RIGHT)),
                Paragraph(_fmt_montant(g.taxe), self._style("gr4", fontSize=8, alignment=TA_RIGHT)),
                Paragraph(_fmt_montant(g.prime_ttc), self._style("gr5", fontSize=8, alignment=TA_RIGHT)),
            ])

        # Ligne total
        prime_nette_tot = sum(g.prime_nette for g in garanties)
        taxe_tot = sum(g.taxe for g in garanties)
        ttc_tot = prime_nette_tot + taxe_tot
        rows.append([
            Paragraph("<b>TOTAL</b>", self._style("gtot", fontSize=8, fontName="Helvetica-Bold")),
            Paragraph("", self._style("g_empty")),
            Paragraph("", self._style("g_empty2")),
            Paragraph(f"<b>{_fmt_montant(prime_nette_tot)}</b>",
                      self._style("gtn", fontSize=8, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            Paragraph(f"<b>{_fmt_montant(taxe_tot)}</b>",
                      self._style("gtt", fontSize=8, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            Paragraph(f"<b>{_fmt_montant(ttc_tot)}</b>",
                      self._style("gtttc", fontSize=8, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        ])

        t = Table(rows, colWidths=[5.5 * cm, 3 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self._couleur),
            ("BACKGROUND", (0, -1), (-1, -1), _hex_to_rgb("#DDEEFF")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, _hex_to_rgb("#f5f8ff")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("LINEBELOW", (0, -1), (-1, -1), 1.5, self._couleur),
        ]))
        return t

    # ── Pied de page légal CIMA ─────────────────────────────

    def _pied_page(self, contrat: DonneesContrat) -> list:
        elements = []
        elements.append(Spacer(1, 0.4 * cm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        elements.append(Spacer(1, 0.15 * cm))

        texte_legal = (
            "Conformément au Code des Assurances de la Conférence Interafricaine des Marchés d'Assurances (CIMA), "
            "le présent contrat est régi par le Traité de la CIMA et ses annexes. "
            "Les délais de prescription sont de 2 ans pour les assurances de dommages (Art. 26 Code CIMA) "
            "et de 10 ans pour les assurances sur la vie (Art. 93 Code CIMA). "
            "Toute déclaration de sinistre doit être effectuée dans les délais prévus aux conditions particulières "
            "et au plus tard conformément à l'article 12 du Code CIMA. "
            f"Agrément CRCA N° {self.compagnie.agrement_crca}."
        )
        if contrat.courtier:
            texte_legal += f"  Intermédiaire : {contrat.courtier}."

        elements.append(Paragraph(texte_legal,
                                  self._style("legal", fontSize=6.5, textColor=colors.grey,
                                              leading=9)))
        elements.append(Spacer(1, 0.2 * cm))

        # Signatures
        sig_data = [
            [Paragraph("<b>L'Assuré(e)</b>", self._style("sig1", fontSize=8, alignment=TA_CENTER)),
             Paragraph("<b>Lu et approuvé</b>", self._style("sig2", fontSize=8, alignment=TA_CENTER)),
             Paragraph(f"<b>Pour {self.compagnie.nom}</b>",
                       self._style("sig3", fontSize=8, alignment=TA_CENTER))],
            [Spacer(1, 1.5 * cm), Spacer(1, 1.5 * cm), Spacer(1, 1.5 * cm)],
            [Paragraph("Signature", self._style("sig4", fontSize=7, textColor=colors.grey,
                                                 alignment=TA_CENTER)),
             Paragraph("Cachet et Signature", self._style("sig5", fontSize=7, textColor=colors.grey,
                                                           alignment=TA_CENTER)),
             Paragraph("Le Directeur Général", self._style("sig6", fontSize=7, textColor=colors.grey,
                                                            alignment=TA_CENTER))],
        ]
        sig_table = Table(sig_data, colWidths=[6 * cm, 6 * cm, 6 * cm])
        sig_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOX", (0, 0), (0, -1), 0.5, colors.lightgrey),
            ("BOX", (1, 0), (1, -1), 0.5, colors.lightgrey),
            ("BOX", (2, 0), (2, -1), 0.5, colors.lightgrey),
        ]))
        elements.append(sig_table)
        return elements

    # ── Génération principale ───────────────────────────────

    def generer(self, contrat: DonneesContrat) -> bytes:
        """Retourne les bytes du PDF généré."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            title=f"Contrat {contrat.numero_police}",
            author=self.compagnie.nom,
        )

        elements: list = []

        # ── En-tête
        elements += self._entete(contrat)

        # ── Assuré
        elements += self._section("1. Informations de l'assuré(e)")
        rows_assure = [
            ("Nom & Prénom", contrat.assure_complet),
            ("Date de naissance", _fmt_date(contrat.date_naissance)),
            ("Adresse", contrat.adresse_assure or "—"),
            ("Téléphone", contrat.telephone_assure or "—"),
            ("Email", contrat.email_assure or "—"),
            ("N° CNI / Passeport", contrat.numero_cni or "—"),
        ]
        elements.append(self._kv_table(rows_assure))

        # ── Objet assuré
        if contrat.objet_assure:
            elements += self._section("2. Objet assuré")
            elements.append(self._kv_table([
                ("Description", contrat.objet_assure),
                ("Valeur déclarée", _fmt_montant(contrat.valeur_assure) if contrat.valeur_assure else "—"),
            ]))

        # ── Période
        elements += self._section("3. Période de couverture")
        elements.append(self._kv_table([
            ("Date d'effet", _fmt_date(contrat.date_effet)),
            ("Date d'échéance", _fmt_date(contrat.date_echeance)),
            ("Durée", f"{contrat.duree_mois} mois"),
            ("Référence ORASS / Mercure", contrat.ref_orass or contrat.ref_mercure or "—"),
        ]))

        # ── Garanties & primes
        elements += self._section("4. Garanties souscrites et primes")
        if contrat.garanties:
            elements.append(self._tableau_garanties(contrat.garanties))
        else:
            elements.append(Paragraph("Aucune garantie enregistrée.",
                                      self._style("no_g", fontSize=8, textColor=colors.grey)))

        # ── Prime totale encadrée
        elements.append(Spacer(1, 0.3 * cm))
        prime_box = Table(
            [[Paragraph(
                f"<b>PRIME TOTALE À PAYER : {_fmt_montant(contrat.prime_ttc_totale)}</b>",
                self._style("prime_ttc", fontSize=11, textColor=colors.white,
                            fontName="Helvetica-Bold", alignment=TA_CENTER)
            )]],
            colWidths=[18 * cm],
        )
        prime_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self._couleur),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(prime_box)

        # ── Clauses particulières
        if contrat.clauses_particulieres:
            elements += self._section("5. Clauses particulières")
            elements.append(Paragraph(contrat.clauses_particulieres,
                                      self._style("clauses", fontSize=8, leading=12)))

        # ── Pied de page
        elements += self._pied_page(contrat)

        doc.build(elements)
        buffer.seek(0)
        return buffer.read()


# ─────────────────────────────────────────────────────────────
# Service de livraison
# ─────────────────────────────────────────────────────────────

class ServiceLivraisonContrat:
    """Envoie le contrat PDF par email et/ou WhatsApp."""

    def __init__(
        self,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        smtp_from: str = "",
        whatsapp_phone_id: str = "",
        whatsapp_token: str = "",
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.smtp_from = smtp_from
        self.whatsapp_phone_id = whatsapp_phone_id
        self.whatsapp_token = whatsapp_token

    # ── Email ────────────────────────────────────────────────

    async def envoyer_email(
        self,
        destinataire: str,
        sujet: str,
        corps_html: str,
        pdf_bytes: bytes,
        nom_fichier: str,
        compagnie_nom: str,
    ) -> bool:
        if not self.smtp_host:
            return False
        msg = MIMEMultipart("mixed")
        msg["From"] = f"{compagnie_nom} <{self.smtp_from}>"
        msg["To"] = destinataire
        msg["Subject"] = sujet

        # Corps HTML
        msg.attach(MIMEText(corps_html, "html", "utf-8"))

        # Pièce jointe PDF
        attach = MIMEApplication(pdf_bytes, _subtype="pdf")
        attach.add_header("Content-Disposition", "attachment", filename=nom_fichier)
        msg.attach(attach)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
            )
            return True
        except Exception as exc:
            print(f"[SMTP] Erreur envoi email : {exc}")
            return False

    # ── WhatsApp document ────────────────────────────────────

    async def envoyer_whatsapp_document(
        self,
        numero: str,
        pdf_bytes: bytes,
        nom_fichier: str,
        caption: str,
    ) -> bool:
        """Upload le PDF sur Meta puis envoie le document au client."""
        if not self.whatsapp_phone_id or not self.whatsapp_token:
            return False

        headers = {"Authorization": f"Bearer {self.whatsapp_token}"}
        base = f"https://graph.facebook.com/v19.0/{self.whatsapp_phone_id}"

        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Upload le fichier sur le serveur Meta
            upload_url = f"https://graph.facebook.com/v19.0/{self.whatsapp_phone_id}/media"
            files = {
                "file": (nom_fichier, pdf_bytes, "application/pdf"),
                "messaging_product": (None, "whatsapp"),
                "type": (None, "application/pdf"),
            }
            r = await client.post(upload_url, headers=headers, files=files)
            if r.status_code != 200:
                print(f"[WhatsApp] Upload échoué : {r.text}")
                return False
            media_id = r.json().get("id")

            # 2. Envoie le message document
            payload = {
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "document",
                "document": {
                    "id": media_id,
                    "filename": nom_fichier,
                    "caption": caption,
                },
            }
            r2 = await client.post(
                f"{base}/messages", headers={**headers, "Content-Type": "application/json"},
                json=payload,
            )
            return r2.status_code == 200


# ─────────────────────────────────────────────────────────────
# Façade principale
# ─────────────────────────────────────────────────────────────

class GestionnaireContratsClients:
    """
    Point d'entrée unique pour générer et livrer un contrat client.

    Usage :
        gestionnaire = GestionnaireContratsClients(compagnie, livraison)
        pdf = await gestionnaire.generer_et_livrer(contrat, email="...", whatsapp="...")
    """

    def __init__(
        self,
        compagnie: ProfilCompagnie,
        service_livraison: Optional[ServiceLivraisonContrat] = None,
    ):
        self.generateur = GenerateurContratPDF(compagnie)
        self.livraison = service_livraison or ServiceLivraisonContrat()
        self.compagnie = compagnie

    def generer_pdf(self, contrat: DonneesContrat) -> bytes:
        """Génère le PDF et retourne les bytes."""
        return self.generateur.generer(contrat)

    def _nom_fichier(self, contrat: DonneesContrat) -> str:
        return f"Contrat_{contrat.numero_police}_{contrat.nom_assure.upper()}.pdf"

    def _corps_email(self, contrat: DonneesContrat) -> str:
        cmp = self.compagnie
        return f"""
        <html><body style="font-family:Arial,sans-serif;color:#333;">
        <div style="max-width:600px;margin:auto;">
          <div style="background:{cmp.couleur_principale};padding:20px;text-align:center;">
            <h2 style="color:white;margin:0;">{cmp.nom}</h2>
            <p style="color:#cce0ff;margin:4px 0;">Votre contrat d'assurance</p>
          </div>
          <div style="padding:24px;">
            <p>Madame / Monsieur <strong>{contrat.assure_complet}</strong>,</p>
            <p>Nous avons le plaisir de vous faire parvenir votre contrat d'assurance
            <strong>{contrat.branche}</strong> N° <strong>{contrat.numero_police}</strong>.</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr style="background:#f0f4ff;">
                <td style="padding:8px;border:1px solid #dde;font-weight:bold;">N° Police</td>
                <td style="padding:8px;border:1px solid #dde;">{contrat.numero_police}</td>
              </tr>
              <tr>
                <td style="padding:8px;border:1px solid #dde;font-weight:bold;">Date d'effet</td>
                <td style="padding:8px;border:1px solid #dde;">{_fmt_date(contrat.date_effet)}</td>
              </tr>
              <tr style="background:#f0f4ff;">
                <td style="padding:8px;border:1px solid #dde;font-weight:bold;">Date d'échéance</td>
                <td style="padding:8px;border:1px solid #dde;">{_fmt_date(contrat.date_echeance)}</td>
              </tr>
              <tr>
                <td style="padding:8px;border:1px solid #dde;font-weight:bold;">Prime TTC</td>
                <td style="padding:8px;border:1px solid #dde;font-weight:bold;color:{cmp.couleur_principale};">
                  {_fmt_montant(contrat.prime_ttc_totale)}</td>
              </tr>
            </table>
            <p>Veuillez trouver votre contrat en pièce jointe au format PDF.</p>
            <p style="font-size:12px;color:#888;">
              Pour toute question, contactez-nous au {cmp.telephone} ou à {cmp.email}.
            </p>
          </div>
          <div style="background:#f5f5f5;padding:12px;text-align:center;font-size:11px;color:#999;">
            {cmp.nom} — Agrément CRCA N° {cmp.agrement_crca} — {cmp.adresse}, {cmp.ville}
          </div>
        </div>
        </body></html>
        """

    async def generer_et_livrer(
        self,
        contrat: DonneesContrat,
        email: Optional[str] = None,
        whatsapp: Optional[str] = None,
    ) -> dict:
        """
        Génère le PDF et le livre via email et/ou WhatsApp.
        Retourne un dict : {pdf_bytes, email_envoye, whatsapp_envoye, nom_fichier}
        """
        pdf_bytes = self.generer_pdf(contrat)
        nom_fichier = self._nom_fichier(contrat)

        resultats = {
            "pdf_bytes": pdf_bytes,
            "nom_fichier": nom_fichier,
            "email_envoye": False,
            "whatsapp_envoye": False,
        }

        if email:
            resultats["email_envoye"] = await self.livraison.envoyer_email(
                destinataire=email,
                sujet=f"Votre contrat {contrat.branche} — Police N° {contrat.numero_police}",
                corps_html=self._corps_email(contrat),
                pdf_bytes=pdf_bytes,
                nom_fichier=nom_fichier,
                compagnie_nom=self.compagnie.nom,
            )

        if whatsapp:
            caption = (
                f"Votre contrat {contrat.branche} — Police N° {contrat.numero_police}\n"
                f"Période : {_fmt_date(contrat.date_effet)} → {_fmt_date(contrat.date_echeance)}\n"
                f"Prime TTC : {_fmt_montant(contrat.prime_ttc_totale)}"
            )
            resultats["whatsapp_envoye"] = await self.livraison.envoyer_whatsapp_document(
                numero=whatsapp,
                pdf_bytes=pdf_bytes,
                nom_fichier=nom_fichier,
                caption=caption,
            )

        return resultats
