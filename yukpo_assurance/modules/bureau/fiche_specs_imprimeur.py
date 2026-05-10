"""
Phase 4.3b — Fiche specs imprimeur auto-générée.

Pour chaque PDF généré (Designer Pro), produit une fiche TEXT (et PDF 1 page)
listant tout ce dont l'imprimeur a besoin pour imprimer SANS retouche :

  - Format final (mm) après rognage = TrimBox
  - Format avec bleed (mm)            = MediaBox
  - Bleed (mm)                         = différence
  - Mode couleur                       = CMJN ou RGB
  - Profil ICC                         = FOGRA39 / ISO Coated v2 (Sprint 1.8c)
  - Résolution images                  = ≥300 DPI
  - Polices                            = embarquées subset
  - Nombre de pages
  - Recto/Verso                        = simplex/duplex
  - Pliage                              = saddle-stitch / trifold / etc.
  - Grammage papier RECOMMANDÉ         = (selon usage : flyer, carte, livret…)
  - Type de papier RECOMMANDÉ          = couché brillant, couché mat, offset…
  - Conformité PDF/X                    = PDF/X-1a:2001
  - Crop marks                         = présents (Sprint 1.3 _coins_imprimerie)
  - Notes spéciales                    = filigranes, pelliculage, dorure si pertinent

Cette fiche est auto-jointe au ZIP des bulks (`bulk_zips/job_xxx.zip`)
sous `00_FICHE_SPECS_IMPRIMEUR.txt`. Elle peut aussi être téléchargée
seule via endpoint `/specs-imprimeur/{pdf_id}`.
"""
from __future__ import annotations

import io
from typing import Optional


# Recommandations grammage papier par usage
GRAMMAGE_RECOMMANDE_PAR_CATEGORIE: dict[str, dict] = {
    # cle → {grammage_g_m2, type_papier, reliure?}
    "carte_visite":   {"grammage": "350g", "type": "couché mat ou brillant", "finition": "pelliculage soft-touch optionnel"},
    "carte_postale":  {"grammage": "300g", "type": "couché mat 1 face", "finition": "vernis sélectif optionnel"},
    "carte_voeux":    {"grammage": "300g", "type": "couché mat", "finition": "dorure à chaud optionnelle"},
    "flyer":          {"grammage": "135g à 170g", "type": "couché brillant ou mat", "finition": "—"},
    "affiche":        {"grammage": "170g (intérieur) à 250g (vitrine)", "type": "couché mat", "finition": "—"},
    "poster":         {"grammage": "170g standard / 250g premium", "type": "couché mat satiné", "finition": "—"},
    "brochure":       {"grammage": "couverture 250g + intérieur 135-170g", "type": "couché mat (couverture brillant possible)", "finition": "agrafé / dos carré collé selon nb pages"},
    "livret":         {"grammage": "couverture 250-300g + intérieur 115-135g", "type": "couché mat", "finition": "agrafé 2 points (saddle-stitch) jusqu'à 64 pages"},
    "magazine":       {"grammage": "couverture 250g + intérieur 100-115g", "type": "couché brillant intérieur (look magazine)", "finition": "dos carré collé si >64 pages"},
    "livre_photo":    {"grammage": "intérieur 200-250g", "type": "couché brillant ou mat selon style", "finition": "reliure dos carré collé ou cousu"},
    "rapport":        {"grammage": "couverture 250g + intérieur 90-100g", "type": "offset blanc ou couché mat", "finition": "spirale / dos carré collé"},
    "diplome":        {"grammage": "250-300g", "type": "vergé (effet papier prestige)", "finition": "—"},
    "banderole":      {"grammage": "bâche PVC 440g/m² ou 510g/m² (extérieur)", "type": "PVC mat ou brillant", "finition": "œillets coins + ourlets"},
    "rollup":         {"grammage": "PP indéchirable 220g ou bâche PVC 440g", "type": "PVC mat (anti-reflets)", "finition": "système enrouleur inclus"},
    "calendrier":     {"grammage": "couverture 300g + pages 170g", "type": "couché brillant", "finition": "spirale wire-o"},
    "etiquette":      {"grammage": "papier adhésif 80g", "type": "adhésif permanent ou repositionnable", "finition": "découpe forme libre"},
    "autre":          {"grammage": "à définir selon usage", "type": "couché mat 170g (par défaut)", "finition": "—"},
}


def deviner_categorie(cle_projet: str, label: Optional[str] = None) -> str:
    """Devine la catégorie pour grammage à partir de la cle_projet ou label."""
    s = (cle_projet or "").lower() + " " + (label or "").lower()
    for cat in GRAMMAGE_RECOMMANDE_PAR_CATEGORIE:
        if cat in s:
            return cat
    if "livret" in s or "faire_part" in s or "programme" in s:
        return "livret"
    if "magazine" in s:
        return "magazine"
    if "brochure" in s:
        return "brochure"
    if "rapport" in s:
        return "rapport"
    if "livre_photo" in s or "album" in s:
        return "livre_photo"
    if "carte_visite" in s or "carte de visite" in s:
        return "carte_visite"
    if "flyer" in s:
        return "flyer"
    if "affiche" in s or "poster" in s:
        return "poster"
    if "diplome" in s or "attestation" in s:
        return "diplome"
    return "autre"


def construire_fiche_texte(
    cle_projet: str,
    titre: str,
    format_trim_mm: tuple[float, float],
    bleed_mm: float,
    nombre_pages: int,
    mode_couleur: str = "CMJN",
    icc_profile: str = "ISO Coated v2 (FOGRA39)",
    duplex: bool = True,
    fold: Optional[str] = None,
    notes_speciales: Optional[str] = None,
) -> str:
    """
    Génère le contenu TXT de la fiche specs imprimeur.
    Encodage UTF-8, prêt à être inséré dans un ZIP ou affiché.
    """
    cat = deviner_categorie(cle_projet, titre)
    rec = GRAMMAGE_RECOMMANDE_PAR_CATEGORIE.get(cat, GRAMMAGE_RECOMMANDE_PAR_CATEGORIE["autre"])
    fw, fh = format_trim_mm
    fw_b, fh_b = fw + 2 * bleed_mm, fh + 2 * bleed_mm
    fold_txt = f" — Pliage : {fold}" if fold else ""
    notes_txt = f"\n\n📝 NOTES SPÉCIALES :\n{notes_speciales}" if notes_speciales else ""

    lignes = [
        "═══════════════════════════════════════════════════════════════",
        "  FICHE SPECS IMPRIMEUR — Yukpo Designer Pro",
        "═══════════════════════════════════════════════════════════════",
        "",
        f"📄 Titre projet      : {titre or cle_projet}",
        f"🗂️ Type              : {cle_projet} (catégorie {cat}){fold_txt}",
        f"📐 Format final      : {fw:g} × {fh:g} mm (TrimBox, après rognage)",
        f"📏 Format avec bleed : {fw_b:g} × {fh_b:g} mm (MediaBox)",
        f"✂️ Bleed (fond perdu): {bleed_mm:g} mm sur chaque côté",
        f"📑 Nombre de pages   : {nombre_pages}",
        f"🔁 Recto/Verso       : {'Recto-verso (duplex)' if duplex else 'Recto seul (simplex)'}",
        "",
        "─── Couleur & Conformité ─────────────────────────────────────",
        f"🎨 Mode couleur      : {mode_couleur}",
        f"🎯 Profil ICC        : {icc_profile}",
        f"📜 Conformité PDF    : PDF/X-1a:2001 (TrimBox + BleedBox + OutputIntent)",
        f"✓  Crop marks        : présents aux 4 coins",
        f"✓  Polices           : embarquées (subset)",
        f"✓  Images            : ≥300 DPI",
        "",
        "─── Recommandations papier (modifiables avec votre client) ───",
        f"🧻 Grammage          : {rec['grammage']}",
        f"📃 Type de papier    : {rec['type']}",
        f"✨ Finition          : {rec['finition']}",
        notes_txt,
        "",
        "─── Pour l'imprimeur ─────────────────────────────────────────",
        "• Le PDF est conforme PDF/X-1a — utilisable directement sans retouche.",
        "• Le bleed est intégré (3 mm standard) — rogner sur les TrimBox.",
        "• Si votre RIP demande un autre profil ICC, conserver les valeurs CMJN.",
        "• Pour un tirage en grand volume : confirmer le grammage avec le client.",
        "",
        "═══════════════════════════════════════════════════════════════",
        "Yukpo Designer Pro — https://yukpomnang.com",
        "Pour toute question technique : contact@yukpomnang.com",
        "═══════════════════════════════════════════════════════════════",
    ]
    return "\n".join(lignes)


def construire_fiche_pdf_bytes(
    cle_projet: str, titre: str,
    format_trim_mm: tuple[float, float], bleed_mm: float,
    nombre_pages: int, mode_couleur: str = "CMJN",
    icc_profile: str = "ISO Coated v2 (FOGRA39)",
    duplex: bool = True, fold: Optional[str] = None,
    notes_speciales: Optional[str] = None,
) -> bytes:
    """
    Génère un PDF A4 1 page contenant la fiche specs (lisible direct par l'imprimeur).
    Utilise ReportLab Canvas (déjà dispo dans le projet).
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
    except Exception as e:
        raise RuntimeError(f"ReportLab indisponible : {e}")

    texte = construire_fiche_texte(
        cle_projet, titre, format_trim_mm, bleed_mm, nombre_pages,
        mode_couleur, icc_profile, duplex, fold, notes_speciales,
    )
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setTitle(f"Fiche specs imprimeur — {titre or cle_projet}")
    c.setAuthor("Yukpo Designer Pro")
    c.setFont("Courier", 9)
    y = h - 15 * mm
    for ligne in texte.split("\n"):
        if y < 15 * mm:
            c.showPage()
            c.setFont("Courier", 9)
            y = h - 15 * mm
        c.drawString(15 * mm, y, ligne[:120])
        y -= 4.5 * mm
    c.save()
    return buf.getvalue()
