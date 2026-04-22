"""
Bureau Gestionnaire — Gestion opérationnelle pour secrétariats africains.

Modules :
  - File de travaux Kanban (bons de travail)
  - Devis & Facturation PDF en FCFA
  - Caisse journalière
  - Mini-CRM clients
"""
from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("yukpo_assurance.bureau.gestionnaire")


# ─── Kanban — File de travaux ─────────────────────────────────────────────────

class StatutTravail(str, Enum):
    EN_ATTENTE = "en_attente"
    EN_COURS = "en_cours"
    EN_REVISION = "en_revision"
    LIVRE = "livre"
    PAYE = "paye"
    ANNULE = "annule"


@dataclass
class BonTravail:
    id: Optional[int]
    client_nom: str
    description: str
    type_travail: str           # redaction | ocr | infographie | impression | saisie | autre
    statut: StatutTravail = StatutTravail.EN_ATTENTE
    montant_fcfa: int = 0
    acompte_fcfa: int = 0
    echeance: Optional[date] = None
    notes: str = ""
    cree_le: datetime = field(default_factory=datetime.utcnow)
    modifie_le: datetime = field(default_factory=datetime.utcnow)


# ─── Devis & Facturation ──────────────────────────────────────────────────────

@dataclass
class LigneDevis:
    description: str
    quantite: float = 1.0
    prix_unitaire_fcfa: int = 0
    unite: str = "u"

    @property
    def total(self) -> int:
        return int(self.quantite * self.prix_unitaire_fcfa)


@dataclass
class Devis:
    client_nom: str
    client_contact: str
    lignes: list[LigneDevis]
    reference: Optional[str] = None
    date_devis: date = field(default_factory=date.today)
    validite_jours: int = 15
    notes: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    nom_secretariat: str = "Mon Secrétariat"
    adresse_secretariat: str = ""
    tel_secretariat: str = ""

    @property
    def sous_total(self) -> int:
        return sum(l.total for l in self.lignes)

    @property
    def tva(self) -> int:
        return int(self.sous_total * 0.1925)  # TVA Cameroun 19.25%

    @property
    def total_ttc(self) -> int:
        return self.sous_total + self.tva


def generer_pdf_devis(devis: Devis, est_facture: bool = False) -> bytes:
    """
    Génère un PDF devis ou facture en FCFA via ReportLab.
    Inclut : logo (si fourni), coordonnées, tableau lignes, total TVA incluse.
    """
    from reportlab.lib.pagesizes import A4, mm
    from reportlab.lib.colors import Color, HexColor
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    w, h = A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    titre_doc = "FACTURE" if est_facture else "DEVIS"
    couleur_titre = Color(0, 0.4, 0.8) if not est_facture else Color(0.1, 0.5, 0.1)

    # En-tête
    c.setFillColor(couleur_titre)
    c.rect(0, h - 70 * mm, w, 70 * mm, fill=True, stroke=False)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 28)
    c.drawRightString(w - 20 * mm, h - 25 * mm, titre_doc)

    ref = devis.reference or f"{titre_doc[:3]}-{datetime.now().strftime('%Y%m%d%H%M')}"
    c.setFont("Helvetica", 10)
    c.drawRightString(w - 20 * mm, h - 35 * mm, f"Réf. : {ref}")
    c.drawRightString(w - 20 * mm, h - 42 * mm, f"Date : {devis.date_devis.strftime('%d/%m/%Y')}")
    if not est_facture:
        c.drawRightString(w - 20 * mm, h - 49 * mm, f"Valide {devis.validite_jours} jours")

    # Infos secrétariat
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, h - 22 * mm, devis.nom_secretariat)
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 30 * mm, devis.adresse_secretariat[:60])
    c.drawString(20 * mm, h - 37 * mm, f"Tél : {devis.tel_secretariat}")

    # Client
    y_client = h - 90 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y_client, "DESTINATAIRE :")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y_client - 7 * mm, devis.client_nom)
    c.drawString(20 * mm, y_client - 14 * mm, devis.client_contact)

    # Tableau lignes
    y_tableau = y_client - 35 * mm
    entetes = [["N°", "Description", "Qté", "Unité", "P.U. (FCFA)", "Total (FCFA)"]]
    donnees = entetes[:]
    for i, ligne in enumerate(devis.lignes, 1):
        donnees.append([
            str(i),
            ligne.description[:50],
            f"{ligne.quantite:.0f}" if ligne.quantite == int(ligne.quantite) else f"{ligne.quantite:.2f}",
            ligne.unite,
            f"{ligne.prix_unitaire_fcfa:,}".replace(",", " "),
            f"{ligne.total:,}".replace(",", " "),
        ])

    largeurs_col = [10 * mm, 75 * mm, 15 * mm, 15 * mm, 30 * mm, 30 * mm]
    table = Table(donnees, colWidths=largeurs_col)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), couleur_titre),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, Color(0.95, 0.97, 1.0)]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])
    table.setStyle(style)
    table.wrapOn(c, w, h)
    table.drawOn(c, 20 * mm, y_tableau - len(donnees) * 7 * mm)

    y_totaux = y_tableau - len(donnees) * 7 * mm - 15 * mm

    # Totaux
    def ligne_total(label: str, montant: int, gras: bool = False):
        nonlocal y_totaux
        fonte = "Helvetica-Bold" if gras else "Helvetica"
        taille = 11 if gras else 10
        c.setFont(fonte, taille)
        c.drawRightString(w - 50 * mm, y_totaux, label)
        c.drawRightString(w - 20 * mm, y_totaux, f"{montant:,} FCFA".replace(",", " "))
        y_totaux -= 7 * mm

    ligne_total("Sous-total HT :", devis.sous_total)
    ligne_total("TVA (19.25%) :", devis.tva)
    c.setStrokeColor(couleur_titre)
    c.setLineWidth(1)
    c.line(w - 90 * mm, y_totaux + 5 * mm, w - 20 * mm, y_totaux + 5 * mm)
    ligne_total("TOTAL TTC :", devis.total_ttc, gras=True)

    # Notes
    if devis.notes:
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.grey)
        c.drawString(20 * mm, 30 * mm, f"Note : {devis.notes[:120]}")

    # Pied de page
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawCentredString(w / 2, 15 * mm, "Paiement : Espèces | Orange Money | MTN MoMo")
    c.drawCentredString(w / 2, 10 * mm, f"Document généré par YukpoSecrétariat — {date.today().strftime('%d/%m/%Y')}")

    c.save()
    return buf.getvalue()


# ─── Caisse journalière ───────────────────────────────────────────────────────

@dataclass
class Transaction:
    type: str            # entree | sortie
    montant_fcfa: int
    libelle: str
    mode_paiement: str   # especes | orange_money | mtn_momo | virement | cheque
    reference: Optional[str] = None
    horodatage: datetime = field(default_factory=datetime.utcnow)


def calculer_rapport_caisse(transactions: list[Transaction]) -> dict:
    """Calcule les totaux et solde pour un ensemble de transactions."""
    entrees = [t for t in transactions if t.type == "entree"]
    sorties = [t for t in transactions if t.type == "sortie"]
    total_entrees = sum(t.montant_fcfa for t in entrees)
    total_sorties = sum(t.montant_fcfa for t in sorties)

    par_mode: dict[str, int] = {}
    for t in entrees:
        par_mode[t.mode_paiement] = par_mode.get(t.mode_paiement, 0) + t.montant_fcfa

    return {
        "total_entrees": total_entrees,
        "total_sorties": total_sorties,
        "solde": total_entrees - total_sorties,
        "nb_transactions": len(transactions),
        "par_mode_paiement": par_mode,
        "repartition": [
            {"mode": k, "montant": v, "pourcentage": round(v / total_entrees * 100, 1) if total_entrees else 0}
            for k, v in par_mode.items()
        ],
    }


# ─── Mini-CRM ─────────────────────────────────────────────────────────────────

@dataclass
class FicheClient:
    id: Optional[int]
    nom: str
    telephone: str
    email: Optional[str] = None
    adresse: Optional[str] = None
    notes: str = ""
    nb_commandes: int = 0
    total_paye_fcfa: int = 0
    derniere_visite: Optional[date] = None
    cree_le: datetime = field(default_factory=datetime.utcnow)


def formater_message_whatsapp(client: FicheClient, message: str) -> str:
    """
    Formate un message WhatsApp avec le nom du client.
    Retourne le texte prêt à copier + l'URL deep link wa.me.
    """
    tel_clean = "".join(c for c in client.telephone if c.isdigit() or c == "+")
    if not tel_clean.startswith("+"):
        tel_clean = "+237" + tel_clean  # Préfixe Cameroun par défaut
    texte_encode = message.replace(" ", "%20").replace("\n", "%0A")
    url = f"https://wa.me/{tel_clean.lstrip('+')}?text={texte_encode}"
    return url
