"""
Catalogue de gabarits Infographie Pro multi-page.

Chaque gabarit définit :
  - format physique (largeur/hauteur/bleed) en mm
  - structure logique (liste de templates de pages avec slots typés)
  - palette suggérée
  - prix FCFA

Les templates de pages indiquent quelles **zones** une page peut accueillir, avec
leurs catégories sémantiques. L'IA reçoit ce catalogue et le brief utilisateur,
décide de la composition finale (textes + médias) page par page, puis le moteur
de rendu fabrique le visuel.
"""
from __future__ import annotations

# ─── Templates de pages ───────────────────────────────────────────────────────
# Chaque template décrit le rôle d'une page et les zones qu'elle propose.
# Le moteur rendra la page selon son `template_id`. L'IA remplit les zones
# autorisées (slots).
#
# slots format : list de dicts {id, type, role, description, requis}
#   type : "texte" | "titre" | "image" | "image_user" | "liste" | "carte" |
#          "qr" | "famille" | "temoignage" | "programme" | "ornement" | "filigrane"
#   role : indication sémantique pour l'IA ("portrait_principal", "intro", etc.)

PAGE_TEMPLATES: dict[str, dict] = {
    # ─── Deuil (faire-part livret) ─────────────────────────────────────────────
    "deuil_couverture": {
        "label": "Couverture faire-part décès",
        "description": "Première de couverture sobre : portrait, nom, dates, In Memoriam",
        "ambiance": "deuil",
        "slots": [
            {"id": "ornement_haut", "type": "ornement", "role": "ornement_deuil"},
            {"id": "mention", "type": "texte", "role": "mention_in_memoriam",
             "exemple": "In Memoriam"},
            {"id": "portrait", "type": "image_user", "role": "portrait_defunt",
             "description": "Photo portrait du défunt", "requis": False},
            {"id": "nom", "type": "titre", "role": "nom_defunt",
             "description": "Nom complet du défunt"},
            {"id": "dates", "type": "texte", "role": "dates_naissance_deces",
             "description": "Dates de naissance — décès"},
            {"id": "citation", "type": "texte", "role": "citation_hommage",
             "description": "Courte citation ou verset"},
        ],
    },
    "deuil_familles": {
        "label": "Familles annonçant le deuil",
        "description": "Page liste structurée par famille / branche familiale",
        "ambiance": "deuil",
        "slots": [
            {"id": "intro", "type": "texte", "role": "intro_familles",
             "exemple": "Les familles ... ont la profonde douleur..."},
            {"id": "familles", "type": "famille", "role": "liste_familles",
             "description": "Liste de familles avec membres principaux (jusqu'à 8 familles, 8 membres chacune)"},
            {"id": "annonce", "type": "texte", "role": "annonce_deces",
             "description": "Phrase annonçant le décès du défunt"},
        ],
    },
    "deuil_programme": {
        "label": "Programme des obsèques",
        "description": "Timeline détaillée des cérémonies (veillée, levée du corps, messe, inhumation)",
        "ambiance": "deuil",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_programme",
             "exemple": "Programme des obsèques"},
            {"id": "etapes", "type": "programme", "role": "liste_etapes",
             "description": "Étapes : date, heure, lieu, description (jusqu'à 10 étapes)"},
        ],
    },
    "deuil_plan": {
        "label": "Plan de localisation",
        "description": "Carte + adresses des lieux de cérémonie",
        "ambiance": "deuil",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_plan",
             "exemple": "Plan d'accès"},
            {"id": "carte", "type": "carte", "role": "carte_lieux",
             "description": "Coordonnées GPS lat/lon des lieux principaux"},
            {"id": "adresses", "type": "liste", "role": "adresses_lieux",
             "description": "Adresses détaillées des lieux"},
        ],
    },
    "deuil_mediatheque": {
        "label": "Souvenirs photos",
        "description": "Grille de 3 à 6 photos de la vie du défunt avec légendes",
        "ambiance": "deuil",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_souvenirs",
             "exemple": "Souvenirs"},
            {"id": "photos", "type": "image_user", "role": "grille_photos",
             "description": "3 à 6 photos avec légendes courtes",
             "multiple": True, "max": 6},
        ],
    },
    "deuil_temoignages": {
        "label": "Témoignages et hommages",
        "description": "Citations, anecdotes par auteur (famille, amis, collègues)",
        "ambiance": "deuil",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_hommages",
             "exemple": "Hommages"},
            {"id": "temoignages", "type": "temoignage", "role": "liste_temoignages",
             "description": "Citations + auteurs (jusqu'à 6 témoignages)"},
        ],
    },
    "deuil_remerciements": {
        "label": "Remerciements",
        "description": "Mots de remerciement aux soutiens",
        "ambiance": "deuil",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_remerciements",
             "exemple": "Remerciements"},
            {"id": "corps", "type": "texte", "role": "texte_remerciements"},
            {"id": "signature", "type": "texte", "role": "signature_familles"},
        ],
    },
    "deuil_dos": {
        "label": "Quatrième de couverture",
        "description": "Citation finale + ornement",
        "ambiance": "deuil",
        "slots": [
            {"id": "citation_finale", "type": "texte", "role": "citation_finale"},
            {"id": "ornement", "type": "ornement", "role": "ornement_final"},
            {"id": "contact", "type": "texte", "role": "contact_familles", "requis": False},
        ],
    },
    # ─── Mariage livret ────────────────────────────────────────────────────────
    "mariage_couverture": {
        "label": "Couverture faire-part mariage",
        "description": "Couverture élégante avec noms des mariés et date",
        "ambiance": "mariage",
        "slots": [
            {"id": "ornement_haut", "type": "ornement", "role": "fleurs_dorees"},
            {"id": "mention", "type": "texte", "role": "invitation",
             "exemple": "Vous êtes cordialement invités"},
            {"id": "noms", "type": "titre", "role": "noms_maries",
             "description": "Prénoms des mariés (forme : 'Marie & Jean')"},
            {"id": "date", "type": "texte", "role": "date_mariage"},
            {"id": "lieu_court", "type": "texte", "role": "ville_celebration"},
        ],
    },
    "mariage_invitation": {
        "label": "Page invitation détaillée",
        "description": "Texte d'invitation complet, parents qui invitent, programme",
        "ambiance": "mariage",
        "slots": [
            {"id": "intro", "type": "texte", "role": "parents_invitants"},
            {"id": "annonce", "type": "texte", "role": "annonce_mariage"},
            {"id": "programme", "type": "programme", "role": "deroule_journee",
             "description": "Cérémonie civile, religieuse, vin d'honneur, dîner, bal"},
            {"id": "rsvp", "type": "texte", "role": "rsvp"},
        ],
    },
    "mariage_plan": {
        "label": "Plan d'accès",
        "description": "Plan + adresses cérémonie + réception",
        "ambiance": "mariage",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_plan"},
            {"id": "carte", "type": "carte", "role": "carte_lieux"},
            {"id": "adresses", "type": "liste", "role": "adresses_lieux"},
        ],
    },
    "mariage_dos": {
        "label": "Quatrième mariage",
        "description": "Citation amour + monogramme + RSVP",
        "ambiance": "mariage",
        "slots": [
            {"id": "monogramme", "type": "texte", "role": "monogramme"},
            {"id": "citation", "type": "texte", "role": "citation_amour"},
            {"id": "rsvp_final", "type": "qr", "role": "qr_rsvp", "requis": False},
        ],
    },
    # ─── Brochure corporate ────────────────────────────────────────────────────
    "brochure_couverture": {
        "label": "Couverture brochure",
        "description": "Visuel hero + titre + accroche",
        "ambiance": "corporate",
        "slots": [
            {"id": "logo", "type": "image_user", "role": "logo_marque", "requis": False},
            {"id": "image_hero", "type": "image_user", "role": "visuel_hero", "requis": False},
            {"id": "titre", "type": "titre", "role": "titre_brochure"},
            {"id": "accroche", "type": "texte", "role": "accroche_marketing"},
        ],
    },
    "brochure_propositions": {
        "label": "Page services / produits",
        "description": "Grille services avec icônes, descriptions, bénéfices",
        "ambiance": "corporate",
        "slots": [
            {"id": "titre_section", "type": "titre", "role": "titre_section"},
            {"id": "services", "type": "liste", "role": "liste_services",
             "description": "Jusqu'à 6 services avec titre + description courte"},
            {"id": "image_secondaire", "type": "image_user", "role": "image_illustration", "requis": False},
        ],
    },
    "brochure_temoignages": {
        "label": "Témoignages clients",
        "description": "Citations clients + photos / logos",
        "ambiance": "corporate",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_clients"},
            {"id": "temoignages", "type": "temoignage", "role": "avis_clients"},
            {"id": "logos_clients", "type": "image_user", "role": "logos_partenaires",
             "multiple": True, "max": 8, "requis": False},
        ],
    },
    "brochure_contact": {
        "label": "Page contact / appel à action",
        "description": "Coordonnées + QR + CTA",
        "ambiance": "corporate",
        "slots": [
            {"id": "titre", "type": "titre", "role": "cta_principal"},
            {"id": "contact", "type": "texte", "role": "coordonnees_completes"},
            {"id": "qr", "type": "qr", "role": "qr_site_ou_contact"},
            {"id": "carte", "type": "carte", "role": "plan_acces", "requis": False},
        ],
    },
    # ─── Menu restaurant ───────────────────────────────────────────────────────
    "menu_couverture": {
        "label": "Couverture menu",
        "description": "Logo restaurant + nom + accroche cuisine",
        "ambiance": "tropical",
        "slots": [
            {"id": "logo", "type": "image_user", "role": "logo_restaurant", "requis": False},
            {"id": "nom_resto", "type": "titre", "role": "nom_etablissement"},
            {"id": "accroche", "type": "texte", "role": "accroche_cuisine"},
            {"id": "image_signature", "type": "image_user", "role": "plat_signature", "requis": False},
        ],
    },
    "menu_entrees": {
        "label": "Page entrées / plats / desserts",
        "description": "Liste structurée plats avec prix",
        "ambiance": "tropical",
        "slots": [
            {"id": "titre_section", "type": "titre", "role": "categorie_plats"},
            {"id": "plats", "type": "liste", "role": "carte_plats",
             "description": "Jusqu'à 12 plats : nom, description, prix"},
            {"id": "image", "type": "image_user", "role": "photo_plats", "requis": False},
        ],
    },
    "menu_dos": {
        "label": "Dos menu",
        "description": "Horaires + adresse + contact + carte",
        "ambiance": "tropical",
        "slots": [
            {"id": "horaires", "type": "texte", "role": "horaires_ouverture"},
            {"id": "adresse", "type": "texte", "role": "adresse_complete"},
            {"id": "contact", "type": "texte", "role": "contact_resto"},
            {"id": "qr", "type": "qr", "role": "qr_reservation", "requis": False},
        ],
    },
    # ─── Programme culte / cérémonie ───────────────────────────────────────────
    "programme_couverture": {
        "label": "Couverture programme",
        "description": "Titre cérémonie + ornement + date/lieu",
        "ambiance": "elegance",
        "slots": [
            {"id": "ornement", "type": "ornement", "role": "ornement_solennel"},
            {"id": "titre", "type": "titre", "role": "titre_ceremonie"},
            {"id": "sous_titre", "type": "texte", "role": "sous_titre_evenement"},
            {"id": "date_lieu", "type": "texte", "role": "date_lieu"},
        ],
    },
    "programme_deroulement": {
        "label": "Déroulement de la cérémonie",
        "description": "Liste des séquences (chants, lectures, sermons)",
        "ambiance": "elegance",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_deroulement"},
            {"id": "sequences", "type": "programme", "role": "liste_sequences"},
        ],
    },
    "programme_chants": {
        "label": "Cantiques et lectures",
        "description": "Paroles cantiques, références bibliques",
        "ambiance": "elegance",
        "slots": [
            {"id": "titre", "type": "titre", "role": "titre_chants"},
            {"id": "chants", "type": "liste", "role": "liste_chants_lectures"},
        ],
    },
    # ─── Livre photo souvenirs ─────────────────────────────────────────────────
    "livre_photo_couverture": {
        "label": "Couverture livre photo",
        "description": "Image hero + titre + sous-titre",
        "ambiance": "tropical",
        "slots": [
            {"id": "image_hero", "type": "image_user", "role": "photo_couverture"},
            {"id": "titre", "type": "titre", "role": "titre_album"},
            {"id": "sous_titre", "type": "texte", "role": "sous_titre_album"},
        ],
    },
    "livre_photo_grille": {
        "label": "Page album photo",
        "description": "Grille de 4 à 9 photos avec légendes",
        "ambiance": "tropical",
        "slots": [
            {"id": "photos", "type": "image_user", "role": "grille_album",
             "multiple": True, "max": 9},
            {"id": "legende_page", "type": "texte", "role": "legende_section"},
        ],
    },
}


# ─── Catalogue de projets multi-page ──────────────────────────────────────────

PROJETS_INFOGRAPHIE: dict[str, dict] = {
    "livret_deces_8p": {
        "label": "Livret faire-part de décès — 8 pages",
        "description": "Livret professionnel 8 pages : couverture, familles, programme, plan, "
                       "souvenirs photos, témoignages, remerciements, dos.",
        "categorie": "evenement",
        "format_mm": (148, 210),       # A5 portrait — plié à partir d'A4
        "bleed_mm": 3,
        "pages": [
            "deuil_couverture",
            "deuil_familles",
            "deuil_programme",
            "deuil_plan",
            "deuil_mediatheque",
            "deuil_temoignages",
            "deuil_remerciements",
            "deuil_dos",
        ],
        "palette": "deuil",
        "prix_fcfa": 12000,
        "polices": {"titre": "Cormorant", "corps": "Lato"},
    },
    "livret_deces_4p": {
        "label": "Livret faire-part de décès — 4 pages (essentiel)",
        "description": "Version condensée : couverture, familles+programme, plan, dos.",
        "categorie": "evenement",
        "format_mm": (148, 210),
        "bleed_mm": 3,
        "pages": [
            "deuil_couverture",
            "deuil_familles",
            "deuil_programme",
            "deuil_dos",
        ],
        "palette": "deuil",
        "prix_fcfa": 7000,
        "polices": {"titre": "Cormorant", "corps": "Lato"},
    },
    "livret_mariage_4p": {
        "label": "Livret faire-part mariage — 4 pages plié",
        "description": "Couverture, invitation détaillée, plan d'accès, dos avec QR RSVP.",
        "categorie": "evenement",
        "format_mm": (148, 210),
        "bleed_mm": 3,
        "pages": [
            "mariage_couverture",
            "mariage_invitation",
            "mariage_plan",
            "mariage_dos",
        ],
        "palette": "mariage",
        "prix_fcfa": 8000,
        "polices": {"titre": "Playfair Display", "corps": "Lato"},
    },
    "brochure_corporate_4p": {
        "label": "Brochure corporate — 4 pages",
        "description": "Présentation entreprise : couverture, services, témoignages, contact.",
        "categorie": "corporate",
        "format_mm": (210, 297),       # A4 portrait
        "bleed_mm": 3,
        "pages": [
            "brochure_couverture",
            "brochure_propositions",
            "brochure_temoignages",
            "brochure_contact",
        ],
        "palette": "corporate",
        "prix_fcfa": 15000,
        "polices": {"titre": "Inter", "corps": "Inter"},
    },
    "menu_resto_4p": {
        "label": "Menu restaurant — 4 pages",
        "description": "Carte restaurant : couverture, entrées, plats/desserts, dos.",
        "categorie": "commercial",
        "format_mm": (148, 210),
        "bleed_mm": 3,
        "pages": [
            "menu_couverture",
            "menu_entrees",   # entrées
            "menu_entrees",   # plats principaux
            "menu_dos",
        ],
        "palette": "tropical",
        "prix_fcfa": 9000,
        "polices": {"titre": "Playfair Display", "corps": "Lato"},
    },
    "programme_culte_4p": {
        "label": "Programme cérémonie / culte — 4 pages",
        "description": "Couverture, déroulement, cantiques/lectures, dos.",
        "categorie": "evenement",
        "format_mm": (148, 210),
        "bleed_mm": 3,
        "pages": [
            "programme_couverture",
            "programme_deroulement",
            "programme_chants",
            "programme_couverture",
        ],
        "palette": "elegance",
        "prix_fcfa": 7000,
        "polices": {"titre": "Cormorant", "corps": "Lato"},
    },
    "livre_photo_a4_8p": {
        "label": "Livre photo — 8 pages A4",
        "description": "Album photo avec couverture + 6 pages grille + dos.",
        "categorie": "evenement",
        "format_mm": (210, 210),       # carré 21x21 album souvenir
        "bleed_mm": 3,
        "pages": [
            "livre_photo_couverture",
            "livre_photo_grille",
            "livre_photo_grille",
            "livre_photo_grille",
            "livre_photo_grille",
            "livre_photo_grille",
            "livre_photo_grille",
            "livre_photo_couverture",
        ],
        "palette": "tropical",
        "prix_fcfa": 18000,
        "polices": {"titre": "Playfair Display", "corps": "Lato"},
    },
    "carte_mariage_pliee": {
        "label": "Carte mariage pliée — 4 faces",
        "description": "Carte format 105×148 pliée (recto, intérieur G, intérieur D, dos).",
        "categorie": "evenement",
        "format_mm": (105, 148),
        "bleed_mm": 3,
        "pages": [
            "mariage_couverture",
            "mariage_invitation",
            "mariage_plan",
            "mariage_dos",
        ],
        "palette": "mariage",
        "prix_fcfa": 6500,
        "polices": {"titre": "Playfair Display", "corps": "Lato"},
    },
    # ── Sprint 1.8b — Pages illimitées (livres, magazines, rapports longs) ──
    "livre_photo_a4_16p": {
        "label": "Livre photo — 16 pages A4 carré",
        "description": "Album photo riche : couverture, 14 pages grille variées, dos.",
        "categorie": "evenement",
        "format_mm": (210, 210),
        "bleed_mm": 3,
        "pages": ["livre_photo_couverture"]
                 + ["livre_photo_grille"] * 14
                 + ["livre_photo_couverture"],
        "palette": "tropical",
        "prix_fcfa": 30000,
        "polices": {"titre": "Playfair Display", "corps": "Lato"},
    },
    "livre_photo_a4_24p": {
        "label": "Livre photo — 24 pages A4 carré",
        "description": "Album souvenirs grande capacité : couverture, 22 pages grille, dos.",
        "categorie": "evenement",
        "format_mm": (210, 210),
        "bleed_mm": 3,
        "pages": ["livre_photo_couverture"]
                 + ["livre_photo_grille"] * 22
                 + ["livre_photo_couverture"],
        "palette": "tropical",
        "prix_fcfa": 42000,
        "polices": {"titre": "Playfair Display", "corps": "Lato"},
    },
    "livre_photo_a4_32p": {
        "label": "Livre photo — 32 pages A4 carré (premium)",
        "description": "Album luxe : couverture, 30 pages grille (mix portrait/paysage/full), dos.",
        "categorie": "evenement",
        "format_mm": (210, 210),
        "bleed_mm": 3,
        "pages": ["livre_photo_couverture"]
                 + ["livre_photo_grille"] * 30
                 + ["livre_photo_couverture"],
        "palette": "tropical",
        "prix_fcfa": 56000,
        "polices": {"titre": "Playfair Display", "corps": "Lato"},
    },
    "magazine_corporate_12p": {
        "label": "Magazine corporate — 12 pages A4",
        "description": "Magazine d'entreprise : édito, 4 reportages, 4 témoignages, contact, dos.",
        "categorie": "corporate",
        "format_mm": (210, 297),
        "bleed_mm": 3,
        "pages": [
            "brochure_couverture",
            "brochure_propositions",
            "brochure_propositions",
            "brochure_propositions",
            "brochure_propositions",
            "brochure_temoignages",
            "brochure_temoignages",
            "brochure_temoignages",
            "brochure_temoignages",
            "brochure_propositions",
            "brochure_contact",
            "brochure_couverture",
        ],
        "palette": "corporate",
        "prix_fcfa": 38000,
        "polices": {"titre": "Inter", "corps": "Inter"},
    },
    "magazine_corporate_24p": {
        "label": "Magazine corporate — 24 pages A4",
        "description": "Magazine premium : couverture, 20 pages contenu varié, contact, dos.",
        "categorie": "corporate",
        "format_mm": (210, 297),
        "bleed_mm": 3,
        "pages": ["brochure_couverture"]
                 + (["brochure_propositions", "brochure_temoignages"] * 10)
                 + ["brochure_contact", "brochure_couverture"],
        "palette": "corporate",
        "prix_fcfa": 68000,
        "polices": {"titre": "Inter", "corps": "Inter"},
    },
    "rapport_annuel_32p": {
        "label": "Rapport annuel — 32 pages A4",
        "description": "Rapport financier/CSR : couverture, mot du DG, 26 pages contenu, contact, dos.",
        "categorie": "corporate",
        "format_mm": (210, 297),
        "bleed_mm": 3,
        "pages": ["brochure_couverture"]
                 + (["brochure_propositions", "brochure_propositions",
                     "brochure_temoignages"] * 10)
                 + ["brochure_contact", "brochure_couverture"],
        "palette": "corporate",
        "prix_fcfa": 95000,
        "polices": {"titre": "Inter", "corps": "Inter"},
    },
    # ── ADD-3 — Compléments catalogue multi-page (gaps audit) ──────────────
    "dossier_presse_8p": {
        "label": "Dossier de presse — 8 pages A4",
        "description": "Couverture impactante, communiqué, fiche société, faits marquants, "
                       "interviews, photos HD, contacts presse, dos. Format média/relations publiques.",
        "categorie": "corporate",
        "format_mm": (210, 297),
        "bleed_mm": 3,
        "pages": ["brochure_couverture", "brochure_propositions", "brochure_propositions",
                  "brochure_temoignages", "brochure_temoignages", "brochure_temoignages",
                  "brochure_contact", "brochure_couverture"],
        "palette": "corporate",
        "prix_fcfa": 22000,
        "polices": {"titre": "Inter", "corps": "Inter"},
    },
    "cahier_charges_16p": {
        "label": "Cahier des charges technique — 16 pages",
        "description": "Document de spécification appel d'offres : contexte, périmètre, "
                       "exigences fonctionnelles/techniques, planning, budget, critères de recette, annexes.",
        "categorie": "corporate",
        "format_mm": (210, 297),
        "bleed_mm": 3,
        "pages": ["brochure_couverture"]
                 + (["brochure_propositions"] * 12)
                 + ["brochure_temoignages", "brochure_contact", "brochure_couverture"],
        "palette": "corporate",
        "prix_fcfa": 38000,
        "polices": {"titre": "Inter", "corps": "Inter"},
    },
    "memoire_technique_24p": {
        "label": "Mémoire technique appel d'offres — 24 pages",
        "description": "Réponse à appel d'offres marché public/privé : approche méthodologique, "
                       "expertise équipe, références similaires, planning détaillé, prix.",
        "categorie": "corporate",
        "format_mm": (210, 297),
        "bleed_mm": 3,
        "pages": ["brochure_couverture"]
                 + (["brochure_propositions", "brochure_propositions",
                     "brochure_temoignages"] * 7)
                 + ["brochure_contact", "brochure_couverture"],
        "palette": "corporate",
        "prix_fcfa": 65000,
        "polices": {"titre": "Inter", "corps": "Inter"},
    },
    "catalogue_produits_16p": {
        "label": "Catalogue produits — 16 pages",
        "description": "Catalogue commercial structuré : couverture, sommaire, 12 pages produits "
                       "avec photos + caractéristiques + prix, contact distributeur, dos.",
        "categorie": "commercial",
        "format_mm": (210, 297),
        "bleed_mm": 3,
        "pages": ["brochure_couverture"]
                 + (["brochure_propositions", "brochure_propositions",
                     "brochure_propositions"] * 4)
                 + ["brochure_contact", "brochure_couverture"],
        "palette": "corporate",
        "prix_fcfa": 35000,
        "polices": {"titre": "Playfair Display", "corps": "Lato"},
    },
    "book_photographe_24p": {
        "label": "Book photographe — 24 pages portfolio",
        "description": "Portfolio photo grand format A4 portrait : couverture impact, 22 pages "
                       "photos en double-page ou pleine page, contact pro. Pour photographes pro.",
        "categorie": "corporate",
        "format_mm": (210, 297),
        "bleed_mm": 3,
        "pages": ["livre_photo_couverture"]
                 + (["livre_photo_grille"] * 22)
                 + ["livre_photo_couverture"],
        "palette": "moderne",
        "prix_fcfa": 60000,
        "polices": {"titre": "Playfair Display", "corps": "Inter"},
    },
}


def lister_projets() -> list[dict]:
    """Retourne le catalogue exposé à l'API/frontend."""
    return [
        {
            "cle": cle,
            "label": p["label"],
            "description": p["description"],
            "categorie": p["categorie"],
            "nombre_pages": len(p["pages"]),
            "format_mm": list(p["format_mm"]),
            "palette": p["palette"],
            "prix_fcfa": p["prix_fcfa"],
        }
        for cle, p in PROJETS_INFOGRAPHIE.items()
    ]


def descripteur_pour_ia(cle_projet: str) -> dict:
    """Description détaillée du projet et de ses pages pour le prompt IA."""
    proj = PROJETS_INFOGRAPHIE[cle_projet]
    pages = []
    for idx, tpl_id in enumerate(proj["pages"]):
        tpl = PAGE_TEMPLATES[tpl_id]
        pages.append({
            "numero": idx + 1,
            "template": tpl_id,
            "label": tpl["label"],
            "description": tpl["description"],
            "ambiance": tpl["ambiance"],
            "slots": tpl["slots"],
        })
    return {
        "cle": cle_projet,
        "label": proj["label"],
        "format_mm": list(proj["format_mm"]),
        "nombre_pages": len(proj["pages"]),
        "palette_suggérée": proj["palette"],
        "pages": pages,
    }
