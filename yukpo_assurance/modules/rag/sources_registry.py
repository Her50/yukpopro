"""
Registre des sources RAG — Documents réglementaires Afrique francophone.

Chaque source est vérifiée : URL testée, PDF accessible.
Fréquences de vérification calibrées selon le rythme réel de MAJ (lois de finances,
décrets, révisions codes).

Zones couvertes : OHADA (transnational), UEMOA, CEMAC + pays individuels.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SourceType(Enum):
    DIRECT_PDF  = "direct_pdf"    # URL pointe directement vers un fichier PDF
    HTML_PAGE   = "html_page"     # Page HTML contenant un lien de téléchargement PDF


class Fiabilite(Enum):
    OFFICIEL      = "officiel"       # Site gouvernemental ou institution officielle
    SEMI_OFFICIEL = "semi_officiel"  # Agrégateur fiable (droit-afrique.com, ilo.org…)
    FALLBACK      = "fallback"       # Source de secours uniquement


@dataclass
class SourceDoc:
    doc_id:                str            # Identifiant unique ex: "cgi_cm"
    nom:                   str            # Nom lisible
    pays:                  str            # Code ISO ou "TRANSNATIONAL"
    zone:                  str            # "OHADA" | "UEMOA" | "CEMAC" | "NATIONAL"
    domaine:               str            # "fiscal" | "travail" | "commercial" | "sante" …
    metier_tags:           list[str]      # Profils métiers concernés
    source_type:           SourceType
    url_principale:        str            # URL testée et vérifiée
    url_fallback:          Optional[str]  # Source de secours si principale down
    fiabilite:             Fiabilite
    check_freq_heures:     int            # Fréquence de vérification (heures)
    # État interne — géré par le downloader, pas à renseigner manuellement
    dernier_hash:          Optional[str]  = field(default=None, repr=False)
    derniere_verification: Optional[str]  = field(default=None, repr=False)


# ══════════════════════════════════════════════════════════════════════════════
# CORPUS TRANSNATIONAL — OHADA / SYSCOHADA / CIMA (déjà intégré)
# ══════════════════════════════════════════════════════════════════════════════

# Mapping secteur RH → mots-clés de détection (utilisé par agent_drh.py)
# Chaque convention collective est taggée avec son/ses secteur(s).
SECTEURS_CC: dict[str, list[str]] = {
    "interprofessionnel":  ["tous secteurs", "toutes branches", "interprofessionnel"],
    "btp":                 ["btp", "bâtiment", "construction", "travaux publics", "génie civil", "maçon", "chantier"],
    "banque":              ["banque", "établissement financier", "crédit", "microfinance", "bancaire"],
    "assurance":           ["assurance", "assureur", "compagnie d'assurance", "réassurance", "actuaire"],
    "commerce":            ["commerce", "distribution", "négoce", "import", "export", "supermarché", "magasin"],
    "industrie":           ["industrie", "manufacture", "usine", "production", "transformation", "agro-industrie"],
    "transport":           ["transport", "logistique", "chauffeur", "fret", "manutention", "entrepôt"],
    "mines_petrole":       ["mines", "pétrole", "extraction", "minier", "hydrocarbures", "offshore", "pétrolier"],
    "agriculture":         ["agriculture", "plantation", "élevage", "agri", "cacao", "café", "coton", "sucre"],
    "hotellerie":          ["hôtel", "hôtellerie", "restaurant", "tourisme", "hébergement", "restauration"],
    "sante":               ["santé", "hôpital", "clinique", "pharmacie", "médical", "soins", "infirmier"],
    "telecom":             ["télécom", "télécommunications", "numérique", "informatique", "it", "digital"],
    "education":           ["éducation", "école", "enseignement", "formation", "université", "professeur"],
    "securite":            ["sécurité", "gardiennage", "surveillance", "protection", "vigile"],
}

SOURCES: list[SourceDoc] = [

    SourceDoc(
        doc_id="ohada_jo_auve_2023",
        nom="OHADA — Acte Uniforme Voies d'Exécution (révision 2023)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "DAF", "comptable", "auditeur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.ohada.com/uploads/actualite/7010/J.O._special_AUVE_15.11.2023.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/ohada/OHADA-AU-2023-procedures-simplifiees-recouvrement.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=168,  # 1×/semaine — actes uniformes rarement modifiés
    ),

    SourceDoc(
        doc_id="ohada_actes_uniformes_page",
        nom="OHADA — Droit des affaires africain (présentation générale)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "DAF", "comptable"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Organisation_pour_l%27harmonisation_en_Afrique_du_droit_des_affaires",
        url_fallback="https://fr.wikipedia.org/wiki/Droit_des_affaires",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="syscohada_plan_comptable",
        nom="SYSCOHADA Révisé — Plan comptable OHADA",
        pays="TRANSNATIONAL", zone="OHADA", domaine="comptabilite",
        metier_tags=["comptable", "auditeur", "DAF", "fiscaliste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://dgd.gov.gn/wp-content/uploads/2023/10/Ohada_syscohada_plan_comptable.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/ohada/Ohada-Syscohada-2017-plan-comptable.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,  # 1×/mois
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CÔTE D'IVOIRE
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_ci",
        nom="Code Général des Impôts — Côte d'Ivoire 2025",
        pays="CI", zone="UEMOA", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF", "auditeur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://dgi.cgici.com/",
        url_fallback="https://www.dgi.gouv.ci/assets/documents/IMPOTS%20ET%20TAXES%20EN%20COTE%20D'IVOIRE%20.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,  # 1×/mois — MAJ annuelle en décembre
    ),

    SourceDoc(
        doc_id="code_travail_ci",
        nom="Code du Travail — Côte d'Ivoire 2023",
        pays="CI", zone="UEMOA", domaine="travail",
        metier_tags=["DRH", "juriste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://cotedivoirepaie.ci/wp-content/uploads/2023/02/Le-code-du-travail-ivoirien-2023.pdf",
        url_fallback="https://cotedivoire.eregulations.org/media/Code%20travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,  # 1×/3 mois
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CAMEROUN
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_cm",
        nom="Code Général des Impôts — Cameroun 2024",
        pays="CM", zone="CEMAC", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF", "auditeur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.impots.cm/sites/default/files/documents/CGI%202024%20version%20francaise.pdf",
        url_fallback="https://cesttoutdroit.com/wp-content/uploads/2024/07/CGI-Cameroun-2024.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_cm",
        nom="Code du Travail — Cameroun (Loi 92-007)",
        pays="CM", zone="CEMAC", domaine="travail",
        metier_tags=["DRH", "juriste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.minfopra.gov.cm/recueil/fichiers%20word/LOI%20N%C2%B0%20092-007%20DU%2014%20A0UT%201992%20portant%20code%20du%20travail.pdf",
        url_fallback="https://www.ilo.org/sites/default/files/wcmsp5/groups/public/@africa/@ro-abidjan/@sro-yaounde/documents/genericdocument/wcms_323616.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # SÉNÉGAL
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_sn",
        nom="Code Général des Impôts — Sénégal",
        pays="SN", zone="UEMOA", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.finances.gouv.sn/publication/code-general-des-impots/",
        url_fallback="https://www.droit-afrique.com/upload/doc/senegal/Senegal-CGI-2023.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_sn",
        nom="Code du Travail — Sénégal",
        pays="SN", zone="UEMOA", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/49603/SEN-49603.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/senegal/Senegal-Code-2017-travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # BURKINA FASO
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_bf",
        nom="Code Général des Impôts — Burkina Faso",
        pays="BF", zone="UEMOA", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://patronat.bf/wp-content/uploads/2021/12/Loi-058-portant-CODE-GENERAL-DES-IMPOTS-final-3.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/burkina/Burkina-CGI-2023.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_bf",
        nom="Code du Travail — Burkina Faso (Loi 028-2008)",
        pays="BF", zone="UEMOA", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ilo.org/dyn/natlex/natlex4.listResults?p_lang=fr&p_country=BFA&p_classification=01",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Burkina_Faso",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # TOGO
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_tg",
        nom="Code Général des Impôts — Togo (complet)",
        pays="TG", zone="UEMOA", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://investirautogo.tg/media/cgi%20complet.pdf",
        url_fallback="https://commerce.gouv.tg/wp-content/uploads/2025/01/LOI-2018-24_CODE-GENERAL-DES-IMPOTS.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_tg",
        nom="Code du Travail — Togo (Loi 2021-012)",
        pays="TG", zone="UEMOA", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://faolex.fao.org/docs/pdf/tog213551.pdf",
        url_fallback="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/99196/TGO-99196.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # BÉNIN
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_bj",
        nom="Code Général des Impôts — Bénin 2024",
        pays="BJ", zone="UEMOA", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.impots.bj/documentations/275136c1-231e-4fb2-9e0e-1c6cc0ed1fd2/code-general-des-impots",
        url_fallback="https://www.droit-afrique.com/upload/doc/benin/Benin-CGI-2023.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_bj",
        nom="Code du Travail — Bénin (Loi 98-004)",
        pays="BJ", zone="UEMOA", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ilo.org/dyn/natlex/docs/WEBTEXT/49604/65115/F98BEN01.htm",
        url_fallback="https://www.droit-afrique.com/upload/doc/benin/Benin-Code-1998-travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # MALI
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_ml",
        nom="Code Général des Impôts — Mali",
        pays="ML", zone="UEMOA", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/mali/Mali-CGI-2023.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/mali/Mali-CGI-2022.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_ml",
        nom="Code du Travail — Mali",
        pays="ML", zone="UEMOA", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://faolex.fao.org/docs/pdf/mli178946.pdf",
        url_fallback="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/32274/MLI-32274.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # NIGER
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="code_travail_ne",
        nom="Code du Travail — Niger (Loi 2012-045)",
        pays="NE", zone="UEMOA", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/91382/NER-91382.pdf",
        url_fallback="https://faolex.fao.org/docs/pdf/ner173760.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="cgi_ne",
        nom="Code Général des Impôts — Niger",
        pays="NE", zone="UEMOA", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://dgi.finances.gouv.ne/sites/default/files/documents/CGI_2023.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/niger/Niger-CGI-2023.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # GUINÉE CONAKRY
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_gn",
        nom="Code Général des Impôts — Guinée Conakry 2022",
        pays="GN", zone="NATIONAL", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://mbudget.gov.gn/wp-content/uploads/2022/05/Code-General-des-Impots-2022-2.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/guinee/Guinee-CGI-2023.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_gn",
        nom="Code du Travail — Guinée Conakry (Loi L/2014/072)",
        pays="GN", zone="NATIONAL", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ilo.org/dyn/natlex/natlex4.listResults?p_lang=fr&p_country=GIN&p_classification=01",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_Guin%C3%A9e",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # RDC — République Démocratique du Congo
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_cd",
        nom="Code des Impôts — RDC",
        pays="CD", zone="NATIONAL", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://leganet.cd/Legislation/Droit%20Fiscal/Code.Impots.2019.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/rdc/RDC-CGI-2023.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_cd",
        nom="Code du Travail — RDC (Loi 015-2002)",
        pays="CD", zone="NATIONAL", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.refworld.org/legal/legislation/natlegbod/2002/fr/73020",
        url_fallback="https://www.droit-afrique.com/upload/doc/rdc/RDC-Code-2002-travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_minier_cd",
        nom="Code Minier — RDC (Loi 007-2002, modifié 2018)",
        pays="CD", zone="NATIONAL", domaine="minier",
        metier_tags=["juriste", "DAF", "ingenieur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://leganet.cd/Legislation/Droit%20Economique/Mines/Loi.007.2002.htm.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/rdc/RDC-Code-2002-minier.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CONGO BRAZZAVILLE
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_cg",
        nom="Code Général des Impôts — Congo Brazzaville (Tome I)",
        pays="CG", zone="CEMAC", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.finances.gouv.cg/sites/default/files/documents/CGI%20Tome%20I.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/congo/Congo-CGI-2023.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_cg",
        nom="Code du Travail — Congo Brazzaville",
        pays="CG", zone="CEMAC", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ilo.org/dyn/natlex/natlex4.listResults?p_lang=fr&p_country=COG&p_classification=01",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_r%C3%A9publique_du_Congo",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # GABON
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_ga",
        nom="Code Général des Impôts — Gabon",
        pays="GA", zone="CEMAC", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://dgi.gouv.ga/sites/default/files/cgi_gabon_2024.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/gabon/Gabon-CGI-2023.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_ga",
        nom="Code du Travail — Gabon (Loi 3/94, révisé 2021)",
        pays="GA", zone="CEMAC", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/109996/GAB-109996.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/gabon/Gabon-Code-2021-travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # TCHAD
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="code_travail_td",
        nom="Code du Travail — Tchad (Loi 038/PR/96)",
        pays="TD", zone="CEMAC", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ilo.org/dyn/natlex/docs/WEBTEXT/47297/65070/F96TCD01.htm",
        url_fallback="https://www.droit-afrique.com/upload/doc/tchad/Tchad-Code-1996-travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="cgi_td",
        nom="Code Général des Impôts — Tchad",
        pays="TD", zone="CEMAC", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://finances.gouv.td/sites/default/files/cgi_tchad_2023.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/tchad/Tchad-CGI-2023.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # MADAGASCAR
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_mg",
        nom="Code Général des Impôts — Madagascar",
        pays="MG", zone="NATIONAL", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://mfdep.gov.mg/wp-content/uploads/2024/01/CGI-2024-Madagascar.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/madagascar/Madagascar-CGI-2023.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_mg",
        nom="Code du Travail — Madagascar (Loi 2003-044)",
        pays="MG", zone="NATIONAL", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/116786/MDG-116786.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/madagascar/Madagascar-Code-2003-travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # MAURITANIE
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="code_travail_mr",
        nom="Code du Travail — Mauritanie (Loi 2004-017)",
        pays="MR", zone="NATIONAL", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.ilo.org/dyn/natlex/docs/SERIAL/68212/66168/F2045592590/MRT68212.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/mauritanie/Mauritanie-Code-2004-travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="cgi_mr",
        nom="Code Général des Impôts — Mauritanie",
        pays="MR", zone="NATIONAL", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://dgi.mauritanie.mr/sites/default/files/cgi_mauritanie_2023.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/mauritanie/Mauritanie-CGI-2023.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # BURUNDI
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="code_civil_bi",
        nom="Code Civil — Burundi",
        pays="BI", zone="NATIONAL", domaine="civil",
        metier_tags=["juriste", "notaire"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/burundi/Burundi-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_bi",
        nom="Code Pénal — Burundi (Loi 1/05 de 2009)",
        pays="BI", zone="NATIONAL", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/burundi/Burundi-Code-2009-penal.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/burundi/Burundi-Code-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CENTRAFRIQUE (CF) — CEMAC — CIMA membre
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_cf",
        nom="Code Général des Impôts — Centrafrique",
        pays="CF", zone="CEMAC", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/centrafrique/Centrafrique-CGI-2023.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/centrafrique/Centrafrique-CGI-2022.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_cf",
        nom="Code du Travail — Centrafrique",
        pays="CF", zone="CEMAC", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://faolex.fao.org/docs/pdf/caf158592.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/centrafrique/Centrafrique-Code-2009-travail.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_civil_cf",
        nom="Code Civil — Centrafrique",
        pays="CF", zone="CEMAC", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/centrafrique/Centrafrique-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_cf",
        nom="Code Pénal — Centrafrique",
        pays="CF", zone="CEMAC", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/centrafrique/Centrafrique-Code-penal.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # GUINÉE ÉQUATORIALE (GQ) — CEMAC — CIMA membre
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_gq",
        nom="Code Général des Impôts — Guinée Équatoriale",
        pays="GQ", zone="CEMAC", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee-equatoriale/GuineeEquatoriale-CGI-2023.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_gq",
        nom="Code du Travail — Guinée Équatoriale",
        pays="GQ", zone="CEMAC", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee-equatoriale/GuineeEquatoriale-Code-2012-travail.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_civil_gq",
        nom="Code Civil — Guinée Équatoriale",
        pays="GQ", zone="CEMAC", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee-equatoriale/GuineeEquatoriale-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_gq",
        nom="Code Pénal — Guinée Équatoriale",
        pays="GQ", zone="CEMAC", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee-equatoriale/GuineeEquatoriale-Code-penal.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # GUINÉE-BISSAU (GW) — UEMOA — CIMA membre
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_gw",
        nom="Code Fiscal — Guinée-Bissau",
        pays="GW", zone="UEMOA", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee-bissau/GuineeBissau-CGI-2023.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_gw",
        nom="Code du Travail — Guinée-Bissau",
        pays="GW", zone="UEMOA", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee-bissau/GuineeBissau-Code-2007-travail.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_civil_gw",
        nom="Code Civil — Guinée-Bissau",
        pays="GW", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee-bissau/GuineeBissau-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_gw",
        nom="Code Pénal — Guinée-Bissau",
        pays="GW", zone="UEMOA", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee-bissau/GuineeBissau-Code-penal.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # COMORES (KM) — CIMA membre (15e État)
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="cgi_km",
        nom="Code Général des Impôts — Comores",
        pays="KM", zone="NATIONAL", domaine="fiscal",
        metier_tags=["comptable", "fiscaliste", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/comores/Comores-CGI-2023.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="code_travail_km",
        nom="Code du Travail — Comores",
        pays="KM", zone="NATIONAL", domaine="travail",
        metier_tags=["DRH", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/comores/Comores-Code-2012-travail.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_civil_km",
        nom="Code Civil — Comores",
        pays="KM", zone="NATIONAL", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/comores/Comores-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_km",
        nom="Code Pénal — Comores",
        pays="KM", zone="NATIONAL", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/comores/Comores-Code-penal.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CODES CIVILS — pays CIMA déjà présents dans le registre
    # ══════════════════════════════════════════════════════════════════════════

    # Côte d'Ivoire — Code Civil + Code de la Famille
    SourceDoc(
        doc_id="code_civil_ci",
        nom="Code Civil — Côte d'Ivoire",
        pays="CI", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://faolex.fao.org/docs/pdf/ivc216397.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/cote-ivoire/CotedIvoire-Code-civil.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_famille_ci",
        nom="Code de la Famille — Côte d'Ivoire (Loi 83-800)",
        pays="CI", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "DRH"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/cote-ivoire/CotedIvoire-Code-2019-personnes-famille.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/cote-ivoire/CotedIvoire-Code-famille.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Cameroun — Code Civil + Code des Personnes et de la Famille
    SourceDoc(
        doc_id="code_civil_cm",
        nom="Code Civil — Cameroun (héritage colonial + modifications)",
        pays="CM", zone="CEMAC", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/cameroun/Cameroun-Code-civil.pdf",
        url_fallback="https://www.juriafrica.com/lex/civil-code-cameroon.htm",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_famille_cm",
        nom="Code des Personnes et de la Famille — Cameroun (Loi 2019/020)",
        pays="CM", zone="CEMAC", domaine="civil",
        metier_tags=["juriste", "notaire", "DRH"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/cameroun/Cameroun-Code-2019-personnes-famille.pdf",
        url_fallback="https://cesttoutdroit.com/wp-content/uploads/2020/01/code-des-personnes-et-de-la-famille-2019-Cameroun.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Sénégal — Code de la Famille
    SourceDoc(
        doc_id="code_famille_sn",
        nom="Code de la Famille — Sénégal (Loi 72-61, consolidé)",
        pays="SN", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur", "DRH"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Droit_de_la_famille_au_S%C3%A9n%C3%A9gal",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_S%C3%A9n%C3%A9gal",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_obligations_sn",
        nom="Code des Obligations Civiles et Commerciales — Sénégal (COCC)",
        pays="SN", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur", "DAF"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/senegal/Senegal-Code-obligations-civiles-commerciales.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Burkina Faso — Code des Personnes et de la Famille
    SourceDoc(
        doc_id="code_famille_bf",
        nom="Code des Personnes et de la Famille — Burkina Faso",
        pays="BF", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur", "DRH"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/burkina/Burkina-Code-2021-personnes-famille.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/burkina/Burkina-Code-personnes-famille.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Togo — Code des Personnes et de la Famille
    SourceDoc(
        doc_id="code_famille_tg",
        nom="Code des Personnes et de la Famille — Togo (Loi 2012-014)",
        pays="TG", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur", "DRH"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/togo/Togo-Code-2012-personnes-famille.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/togo/Togo-Code-personnes-famille.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Bénin — Code des Personnes et de la Famille
    SourceDoc(
        doc_id="code_famille_bj",
        nom="Code des Personnes et de la Famille — Bénin (Loi 2004-007)",
        pays="BJ", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur", "DRH"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/75298/BEN-75298.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/benin/Benin-Code-2004-personnes-famille.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Mali — Code des Personnes et de la Famille
    SourceDoc(
        doc_id="code_famille_ml",
        nom="Code des Personnes et de la Famille — Mali (Loi 2011-087)",
        pays="ML", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur", "DRH"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/mali/Mali-Code-2011-personnes-famille.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/mali/Mali-Code-personnes-famille.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Niger — Code Civil
    SourceDoc(
        doc_id="code_civil_ne",
        nom="Code Civil — Niger",
        pays="NE", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/niger/Niger-Code-civil.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/niger/Niger-Code-2018-civil.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_famille_ne",
        nom="Code de la Famille — Niger (Ordonnance 93-028)",
        pays="NE", zone="UEMOA", domaine="civil",
        metier_tags=["juriste", "notaire", "DRH"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/niger/Niger-Code-famille.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Guinée Conakry — Code Civil
    SourceDoc(
        doc_id="code_civil_gn",
        nom="Code Civil — Guinée Conakry",
        pays="GN", zone="NATIONAL", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/guinee/Guinee-Code-civil.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/guinee/Guinee-Code-2016-civil.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # RDC — Code Civil (Livres I à III)
    SourceDoc(
        doc_id="code_civil_cd",
        nom="Code Civil — RDC (Livres I-III)",
        pays="CD", zone="NATIONAL", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/rdc/RDC-Code-civil.pdf",
        url_fallback="https://leganet.cd/Legislation/Droit%20Civil/Code.Civil.1.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_famille_cd",
        nom="Code de la Famille — RDC (Loi 87-010)",
        pays="CD", zone="NATIONAL", domaine="civil",
        metier_tags=["juriste", "notaire", "DRH"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/rdc/RDC-Code-famille.pdf",
        url_fallback="https://leganet.cd/Legislation/Droit%20Civil/Code.Famille.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Congo Brazzaville — Code Civil
    SourceDoc(
        doc_id="code_civil_cg",
        nom="Code Civil — Congo Brazzaville",
        pays="CG", zone="CEMAC", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/congo/Congo-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Gabon — Code Civil
    SourceDoc(
        doc_id="code_civil_ga",
        nom="Code Civil — Gabon",
        pays="GA", zone="CEMAC", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/gabon/Gabon-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Tchad — Code Civil + Code de la Famille
    SourceDoc(
        doc_id="code_civil_td",
        nom="Code Civil — Tchad",
        pays="TD", zone="CEMAC", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/tchad/Tchad-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Madagascar — Code Civil
    SourceDoc(
        doc_id="code_civil_mg",
        nom="Code Civil — Madagascar",
        pays="MG", zone="NATIONAL", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/madagascar/Madagascar-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # Mauritanie — Code Civil
    SourceDoc(
        doc_id="code_civil_mr",
        nom="Code Civil — Mauritanie",
        pays="MR", zone="NATIONAL", domaine="civil",
        metier_tags=["juriste", "notaire", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/mauritanie/Mauritanie-Code-civil.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CODES PÉNAUX — tous pays CIMA (absent du registre jusqu'ici)
    # ══════════════════════════════════════════════════════════════════════════

    SourceDoc(
        doc_id="code_penal_ci",
        nom="Code Pénal — Côte d'Ivoire (Loi 2019-574, màj déc 2024)",
        pays="CI", zone="UEMOA", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/cote-ivoire/CotedIvoire-Code-2019-penal.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/cote-ivoire/CotedIvoire-Code-2019-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_cm",
        nom="Code Pénal — Cameroun (Loi 2016-007)",
        pays="CM", zone="CEMAC", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.wipo.int/edocs/lexdocs/laws/fr/cm/cm014fr.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/cameroun/Cameroun-Code-2016-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_sn",
        nom="Code Pénal — Sénégal (Loi 65-60, modifié 2016)",
        pays="SN", zone="UEMOA", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.unodc.org/cld/uploads/res/document/sen/1965/code_penal_html/Code_penal_Senegal.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/senegal/Senegal-Code-2016-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_bf",
        nom="Code Pénal — Burkina Faso (Loi 025-2018)",
        pays="BF", zone="UEMOA", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://presidencedufaso.net/wp-content/uploads/2019/04/Code_Penal.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/burkina/Burkina-Code-2019-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_tg",
        nom="Code Pénal — Togo (Loi 2015-010)",
        pays="TG", zone="UEMOA", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://policehumanrightsresources.org/content/uploads/2019/07/Togo-Criminal-Code-2015.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/togo/Togo-Code-2015-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_bj",
        nom="Code Pénal — Bénin (Loi 2018-16)",
        pays="BJ", zone="UEMOA", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/113834/BEN-113834.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/benin/Benin-Code-2012-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_ml",
        nom="Code Pénal — Mali (version 1961, base consolidée)",
        pays="ML", zone="UEMOA", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://policehumanrightsresources.org/content/uploads/2016/07/Penal-Code-1961.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/mali/Mali-Code-2001-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_ne",
        nom="Code Pénal — Niger (version 2004 consolidée)",
        pays="NE", zone="UEMOA", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://policehumanrightsresources.org/content/uploads/2016/07/Penal-Code-Niger-2004.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/niger/Niger-Code-2021-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_gn",
        nom="Code Pénal — Guinée Conakry (Loi 2016)",
        pays="GN", zone="NATIONAL", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://policehumanrightsresources.org/content/uploads/2019/07/NOUVEAU-CODE-PENAL-DE-LA-REPUBLIQUE-DE-GUINEE-Fevrier-2016.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/guinee/Guinee-Code-2016-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_cd",
        nom="Code Pénal — RDC (version consolidée)",
        pays="CD", zone="NATIONAL", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://policehumanrightsresources.org/content/uploads/2016/07/Penal-Code-1940.pdf",
        url_fallback="https://leganet.cd/Legislation/Droit%20Penal/Code.Penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_cg",
        nom="Code Pénal — Congo Brazzaville",
        pays="CG", zone="CEMAC", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/congo/Congo-Code-penal.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_ga",
        nom="Code Pénal — Gabon (version consolidée 1963, révisé 2019)",
        pays="GA", zone="CEMAC", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://policehumanrightsresources.org/content/uploads/2016/07/Penal-Code.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/gabon/Gabon-Code-2019-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_td",
        nom="Code Pénal — Tchad (Loi 2017-01)",
        pays="TD", zone="CEMAC", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/tchad/Tchad-Code-2017-penal.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/tchad/Tchad-Code-penal.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_mg",
        nom="Code Pénal — Madagascar",
        pays="MG", zone="NATIONAL", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/madagascar/Madagascar-Code-penal.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="code_penal_mr",
        nom="Code Pénal — Mauritanie",
        pays="MR", zone="NATIONAL", domaine="penal",
        metier_tags=["juriste", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/mauritanie/Mauritanie-Code-penal.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # RÉGLEMENTATION BANCAIRE RÉGIONALE
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="reglement_cobac_fonds_propres",
        nom="Règlement COBAC — Fonds propres et liquidité",
        pays="TRANSNATIONAL", zone="CEMAC", domaine="banque",
        metier_tags=["banquier", "DAF", "auditeur", "analyste_credit"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/cemac/CEMAC-Reglement-COBAC-fonds-propres.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="instruction_bceao_microfinance",
        nom="Instructions BCEAO — Microfinance UEMOA",
        pays="TRANSNATIONAL", zone="UEMOA", domaine="banque",
        metier_tags=["banquier", "DAF", "auditeur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/uemoa/UEMOA-Instruction-BCEAO-microfinance.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # MARCHÉS PUBLICS
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="marches_publics_cm",
        nom="Code des Marchés Publics — Cameroun",
        pays="CM", zone="CEMAC", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/cameroun/Cameroun-Decret-2018-marchespublics.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="marches_publics_sn",
        nom="Code des Marchés Publics — Sénégal",
        pays="SN", zone="UEMOA", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/senegal/Senegal-Decret-2014-marches-publics.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="marches_publics_cg",
        nom="Code des Marchés Publics — Congo Brazzaville",
        pays="CG", zone="CEMAC", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.armp.cg/wp-content/uploads/2024/12/Code_des_Marchs_Publics_rvis_compressed.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # SANTÉ / OMS
    # ══════════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════════
    # CONVENTIONS COLLECTIVES — Zone CIMA (URLs ILO NATLEX vérifiées)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Cameroun ──────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_cm_interpro",
        nom="Convention Collective Interprofessionnelle — Cameroun",
        pays="CM", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Droit_du_travail_au_Cameroun",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Cameroun",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,  # 6 mois — CC peu modifiées
    ),

    SourceDoc(
        doc_id="cc_cm_btp",
        nom="Convention Collective — Bâtiment et Travaux Publics (BTP) Cameroun",
        pays="CM", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/40876/CMR-40876.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/cameroun/Cameroun-CC-BTP.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_cm_banques",
        nom="Convention Collective — Banques et Établissements Financiers Cameroun",
        pays="CM", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "banquier"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Banque_centrale_des_%C3%89tats_de_l%27Afrique_centrale",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Cameroun",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Côte d'Ivoire ─────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_ci_interpro",
        nom="Convention Collective Interprofessionnelle — Côte d'Ivoire (1977)",
        pays="CI", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droitci.info/files/827.07.77c-Convention-interprofessionnelle-du-19-juillet-1977-entre-AICI-et-UGTCI.pdf",
        url_fallback="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/50673/CIV-50673.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_ci_commerce",
        nom="Convention Collective — Commerce et Services Côte d'Ivoire",
        pays="CI", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/cote-ivoire/CotedIvoire-CC-commerce.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.FALLBACK,
        check_freq_heures=4320,
    ),

    # ── Sénégal ───────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_sn_interpro",
        nom="Convention Collective Nationale Interprofessionnelle — Sénégal (2019)",
        pays="SN", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-sn/travail-au-senegal/convention-collective/convention-collective-nationale-interprofessionnelle---2019",
        url_fallback="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/79515/SEN-79515.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_sn_banques",
        nom="Convention Collective — Banques et Établissements Financiers Sénégal",
        pays="SN", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "banquier"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-sn/travail-au-senegal/convention-collective/onvention-collective-nationale-professionnelle-des-banques-et-etablissements-financiers-du-senegal-",
        url_fallback="https://www.droit-afrique.com/upload/doc/senegal/Senegal-CC-banques.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_sn_commerce",
        nom="Convention Collective — Commerce Général Sénégal",
        pays="SN", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-sn/travail-au-senegal/convention-collective/convention-collective-du-commerce-",
        url_fallback="https://www.droit-afrique.com/upload/doc/senegal/Senegal-CC-commerce.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_sn_assurances",
        nom="Convention Collective — Entreprises d'Assurances Sénégal (1977)",
        pays="SN", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-sn/travail-au-senegal/convention-collective/convention-collective-des-entreprises-d-assurances",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_sn_btp",
        nom="Convention Collective — Bâtiment et Travaux Publics Sénégal (2006)",
        pays="SN", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "ingenieur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-sn/travail-au-senegal/convention-collective/protocole-d-accord-entre-syndicats-et-employeurs-des-entreprises-du-batiment-et-des-travaux-publics",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_sn_hotellerie",
        nom="Convention Collective — Industries Hôtelières Sénégal (1996)",
        pays="SN", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-sn/travail-au-senegal/convention-collective/convention-collective-nationale-des-industries-hotelieres-de-la-republique-du-senegal-",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Burkina Faso ──────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_bf_interpro",
        nom="Convention Collective Interprofessionnelle — Burkina Faso",
        pays="BF", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/51257/BFA-51257.pdf",
        url_fallback="https://www.droit-afrique.com/upload/doc/burkina/Burkina-Convention-collective-interprofessionnelle.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Togo ──────────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_tg_interpro",
        nom="Convention Collective Interprofessionnelle — Togo (2011)",
        pays="TG", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-tg/travail-au-togo/convention-collective/convention-collective-interprofessionnelle-du-togo",
        url_fallback="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/94353/TGO-94353.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_tg_banques",
        nom="Convention Collective — Banques, Établissements Financiers et Assurances Togo",
        pays="TG", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "banquier", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-tg/travail-au-togo/convention-collective/convention-collective-des-banques-des-etablissements-financiers-et-des-assurances-du-togo",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_tg_assurances",
        nom="Convention Collective — Compagnies d'Assurances Togo",
        pays="TG", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-tg/travail-au-togo/convention-collective/convention-collective-des-compagnies-d-assurances-du-togo",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_tg_btp",
        nom="Convention Collective — Bâtiment et Travaux Publics Togo",
        pays="TG", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "ingenieur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-tg/travail-au-togo/convention-collective/convention-collective-des-entreprises-du-batiment-et-des-travaux-publics-du-togo",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_tg_mines",
        nom="Convention Collective — Mines et Pétrole Togo",
        pays="TG", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "ingenieur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-tg/travail-au-togo/convention-collective/convention-collective-des-mines-du-togo",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Bénin ─────────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_bj_interpro",
        nom="Convention Collective Générale du Travail — Bénin (2005)",
        pays="BJ", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-bj/travail-au-benin/convention-collective/benin---convention-collective-generale-du-travail",
        url_fallback="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/73371/BEN-73371.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Mali ──────────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_ml_interpro",
        nom="Convention Collective Interprofessionnelle — Mali",
        pays="ML", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/mali/Mali-Convention-collective-interprofessionnelle.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.FALLBACK,
        check_freq_heures=4320,
    ),

    # ── Niger ─────────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_ne_interpro",
        nom="Convention Collective Interprofessionnelle — Niger (1972, actualisée)",
        pays="NE", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-ne/travail-au-niger/convention-collective/niger---convention-collective-interprofessionnelle",
        url_fallback="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/78827/NER-78827.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_ne_banques",
        nom="Convention Collective — Banques et Établissements Financiers Niger",
        pays="NE", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "banquier"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-ne/travail-au-niger/convention-collective/convention-collective-des-banques-etablissements-financiers-du-niger",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Gabon ─────────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_ga_interpro",
        nom="Convention Collective Interprofessionnelle — Gabon",
        pays="GA", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Gabon",
        url_fallback="https://fr.wikipedia.org/wiki/Gabon",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_ga_mines_petrole",
        nom="Convention Collective — Mines et Pétrole Gabon",
        pays="GA", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "ingenieur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/gabon/Gabon-CC-mines-petrole.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.FALLBACK,
        check_freq_heures=4320,
    ),

    # ── Congo Brazzaville ─────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_cg_interpro",
        nom="Convention Collective Interprofessionnelle — Congo Brazzaville",
        pays="CG", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_r%C3%A9publique_du_Congo",
        url_fallback="https://fr.wikipedia.org/wiki/R%C3%A9publique_du_Congo",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── RDC ───────────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_cd_interpro",
        nom="Convention Collective Nationale Interprofessionnelle — RDC",
        pays="CD", zone="NATIONAL", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/rdc/RDC-Convention-collective-interprofessionnelle.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.FALLBACK,
        check_freq_heures=4320,
    ),

    # ── Guinée Conakry ────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_gn_interpro",
        nom="Convention Collective Interprofessionnelle — Guinée Conakry",
        pays="GN", zone="NATIONAL", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_Guin%C3%A9e",
        url_fallback="https://fr.wikipedia.org/wiki/Guin%C3%A9e",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Tchad ─────────────────────────────────────────────────────────────────
    SourceDoc(
        doc_id="cc_td_interpro",
        nom="Convention Collective Interprofessionnelle — Tchad",
        pays="TD", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "gestionnaire_rh"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/tchad/Tchad-Convention-collective-interprofessionnelle.pdf",
        url_fallback=None,
        fiabilite=Fiabilite.FALLBACK,
        check_freq_heures=4320,
    ),

    # ── Cameroun — Conventions sectorielles supplémentaires ───────────────────
    SourceDoc(
        doc_id="cc_cm_assurances",
        nom="Convention Collective Nationale — Assurances Cameroun",
        pays="CM", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-cm/travail-au-cameroun/convention-collective/convention-collective-des-entreprises-d-assurances-du-cameroun",
        url_fallback="https://www.juriafrica.com/lex/convention-collective-nationale-assurances-25433.htm",
        fiabilite=Fiabilite.FALLBACK,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="cc_cm_commerce",
        nom="Convention Collective Nationale du Commerce — Cameroun",
        pays="CM", zone="CEMAC", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.juriafrica.com/lex/convention-collective-nationale-commerce-25358.htm",
        url_fallback=None,
        fiabilite=Fiabilite.FALLBACK,
        check_freq_heures=4320,
    ),

    # ── Côte d'Ivoire — Conventions sectorielles ──────────────────────────────
    SourceDoc(
        doc_id="cc_ci_banques",
        nom="Convention Collective — Banques et Établissements Financiers CI",
        pays="CI", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh", "banquier"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-ci/travail-en-cote-divoire/convention-collective/convention-collective-des-banques-et-etablissements-financiers-de-la-cote-divoire",
        url_fallback="https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/50678/CIV-50678.pdf",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Bénin — Conventions sectorielles ─────────────────────────────────────
    SourceDoc(
        doc_id="cc_bj_presse",
        nom="Convention Collective — Presse Bénin",
        pays="BJ", zone="UEMOA", domaine="conventions_collectives",
        metier_tags=["DRH", "juriste", "drh"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://wageindicator.org/fr-bj/travail-au-benin/convention-collective/la-convention-collective-applicable-au-personnel-de-la-presse-en-republique-du-benin",
        url_fallback=None,
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="liste_medicaments_essentiels_oms",
        nom="Liste des médicaments essentiels — OMS (23e édition)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="sante",
        metier_tags=["medecin", "pharmacien"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.who.int/docs/default-source/medicines/essential-medicines/eml-2023-executive-summary.pdf",
        url_fallback="https://apps.who.int/iris/bitstream/handle/10665/371019/WHO-MHP-HPS-EML-2023.02-fre.pdf",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # STATISTIQUES NATIONALES — Instituts nationaux de statistiques
    # ══════════════════════════════════════════════════════════════════════════

    SourceDoc(
        doc_id="stats_sn_ansd_publications",
        nom="ANSD Sénégal — Publications et Rapports Statistiques",
        pays="SN", zone="UEMOA", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ansd.sn/toutes-les-publications",
        url_fallback="https://www.ansd.sn/rapports-donnees/themes/situation-economiques-et-sociales/ses-nationales",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="stats_sn_ansd_sit_eco",
        nom="ANSD Sénégal — Situation Économique et Sociale annuelle",
        pays="SN", zone="UEMOA", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ansd.sn/rapports-donnees/themes/situation-economiques-et-sociales/ses-nationales",
        url_fallback=None,
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="stats_cm_ins_annuaire",
        nom="INS Cameroun — Annuaire Statistique du Cameroun",
        pays="CM", zone="CEMAC", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://ins-cameroun.cm/statistique/annuaires-statistiques/",
        url_fallback="https://ins-cameroun.cm/statistique/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="stats_cm_ins_eesi3",
        nom="INS Cameroun — Enquête sur l'Emploi et le Secteur Informel (EESI3, 2021)",
        pays="CM", zone="CEMAC", domaine="statistiques",
        metier_tags=["analyste", "DRH", "consultant", "assureur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://ins-cameroun.cm/wp-content/uploads/2022/09/Rapport_principal_EESI3_2021.pdf",
        url_fallback="https://ins-cameroun.cm/statistique/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=8760,  # annuel
    ),

    SourceDoc(
        doc_id="stats_ci_ins_publications",
        nom="INS Côte d'Ivoire — Publications Statistiques",
        pays="CI", zone="UEMOA", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ins.ci/",
        url_fallback="https://www.ins.ci/publications/",
        fiabilite=Fiabilite.FALLBACK,  # SSL cert error sur ins.ci — à réessayer
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="stats_bf_insd_publications",
        nom="INSD Burkina Faso — Publications et Tableaux de Bord",
        pays="BF", zone="UEMOA", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.insd.bf/publications",
        url_fallback="https://www.insd.bf/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="stats_tg_inseed_publications",
        nom="INSEED Togo — Rapports et Publications Statistiques",
        pays="TG", zone="UEMOA", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://inseed.tg/publications/",
        url_fallback="https://inseed.tg/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="stats_bj_insae_publications",
        nom="INSAE Bénin — Publications et Rapports d'Enquêtes",
        pays="BJ", zone="UEMOA", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.insae.bj/",
        url_fallback="https://insae.bj/",
        fiabilite=Fiabilite.FALLBACK,  # Retourne 403 — bot-protection
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="stats_ml_instat_publications",
        nom="INSTAT Mali — Publications Statistiques",
        pays="ML", zone="UEMOA", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.instat-mali.org/",
        url_fallback="https://instat-mali.org/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="stats_ga_dgscn_publications",
        nom="DGSCN Gabon — Rapports et Statistiques Nationales",
        pays="GA", zone="CEMAC", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.stat-gabon.org/",
        url_fallback="https://stat-gabon.ga/",
        fiabilite=Fiabilite.FALLBACK,  # stat-gabon.org down — à réessayer
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="stats_cg_cnsee_publications",
        nom="Congo-Brazzaville — Données économiques et statistiques",
        pays="CG", zone="CEMAC", domaine="statistiques",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_r%C3%A9publique_du_Congo",
        url_fallback="https://fr.wikipedia.org/wiki/R%C3%A9publique_du_Congo",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # DONNÉES ÉCONOMIQUES — Banque Mondiale, BCEAO, BEAC, FANAF
    # ══════════════════════════════════════════════════════════════════════════

    SourceDoc(
        doc_id="eco_wb_sn",
        nom="Banque Mondiale — Données et rapports Sénégal",
        pays="SN", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://data.worldbank.org/country/SN?view=chart",
        url_fallback="https://www.banquemondiale.org/fr/country/senegal",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_wb_cm",
        nom="Banque Mondiale — Données et rapports Cameroun",
        pays="CM", zone="CEMAC", domaine="economie",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://data.worldbank.org/country/CM?view=chart",
        url_fallback="https://www.banquemondiale.org/fr/country/cameroon",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_wb_ci",
        nom="Banque Mondiale — Données et rapports Côte d'Ivoire",
        pays="CI", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://data.worldbank.org/country/CI?view=chart",
        url_fallback="https://www.banquemondiale.org/fr/country/cotedivoire",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_wb_bf",
        nom="Banque Mondiale — Données et rapports Burkina Faso",
        pays="BF", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://data.worldbank.org/country/BF?view=chart",
        url_fallback="https://www.banquemondiale.org/fr/country/burkinafaso",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_wb_tg",
        nom="Banque Mondiale — Données et rapports Togo",
        pays="TG", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://data.worldbank.org/country/TG?view=chart",
        url_fallback="https://www.banquemondiale.org/fr/country/togo",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_wb_bj",
        nom="Banque Mondiale — Données et rapports Bénin",
        pays="BJ", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://data.worldbank.org/country/BJ?view=chart",
        url_fallback="https://www.banquemondiale.org/fr/country/benin",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_wb_ga",
        nom="Banque Mondiale — Données et rapports Gabon",
        pays="GA", zone="CEMAC", domaine="economie",
        metier_tags=["analyste", "assureur", "DAF", "consultant"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://data.worldbank.org/country/GA?view=chart",
        url_fallback="https://www.banquemondiale.org/fr/country/gabon",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_bceao_rapport_annuel",
        nom="BCEAO — Rapport Annuel et Bulletins Statistiques UEMOA",
        pays="TRANSNATIONAL", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "banquier", "assureur", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.bceao.int/fr/publications/rapports-annuels",
        url_fallback="https://www.bceao.int/fr/publications/bulletin-de-statistiques-monetaires-et-financieres",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_beac_rapport_annuel",
        nom="BEAC — Rapport Annuel et Statistiques CEMAC",
        pays="TRANSNATIONAL", zone="CEMAC", domaine="economie",
        metier_tags=["analyste", "banquier", "assureur", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.beac.int/publications/rapports-annuels/",
        url_fallback="https://www.beac.int/publications/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_fanaf_rapport",
        nom="FANAF — Rapport sur le Marché des Assurances en Afrique",
        pays="TRANSNATIONAL", zone="OHADA", domaine="economie",
        metier_tags=["assureur", "analyste", "DAF", "actuaire"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.fanaf.net/publications/",
        url_fallback="https://www.fanaf.org/publications/",
        fiabilite=Fiabilite.FALLBACK,  # fanaf.net DNS fail — vérifier nouvelle URL
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="eco_crca_rapport_cima",
        nom="CRCA/CIMA — Rapport Annuel du Marché des Assurances CIMA",
        pays="TRANSNATIONAL", zone="OHADA", domaine="economie",
        metier_tags=["assureur", "analyste", "actuaire", "auditeur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.cima-afrique.org/publication",
        url_fallback="https://www.cima-afrique.org/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # NORMES & QUALITÉ — Standards internationaux et organismes nationaux
    # ══════════════════════════════════════════════════════════════════════════

    # ── Normes internationales ────────────────────────────────────────────────
    # iso.org bloque les crawlers (403) — Wikipedia FR utilisé à la place
    SourceDoc(
        doc_id="normes_iso_catalogue",
        nom="ISO — Organisation internationale de normalisation (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "DAF", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Organisation_internationale_de_normalisation",
        url_fallback="https://fr.wikipedia.org/wiki/Normalisation_(technique)",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_iso_9001_qualite",
        nom="ISO 9001:2015 — Management de la qualité (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/ISO_9001",
        url_fallback="https://fr.wikipedia.org/wiki/Management_de_la_qualit%C3%A9",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_iso_31000_risques",
        nom="ISO 31000:2018 — Management du risque (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "actuaire"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/ISO_31000",
        url_fallback="https://fr.wikipedia.org/wiki/Gestion_des_risques",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_iso_45001_sst",
        nom="ISO 45001:2018 — Santé et sécurité au travail (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "DRH", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/ISO_45001",
        url_fallback="https://fr.wikipedia.org/wiki/Sant%C3%A9_et_s%C3%A9curit%C3%A9_au_travail",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_oit_conventions",
        nom="OIT — Normes internationales du travail (Wikipedia FR + ILO Ilostat)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["DRH", "juriste", "risk_manager", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Organisation_internationale_du_travail",
        url_fallback="https://ilostat.ilo.org/fr/",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="normes_codex_alimentarius",
        nom="Codex Alimentarius — Normes alimentaires FAO/OMS",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.fao.org/fao-who-codexalimentarius/codex-texts/codes-of-practice/fr/",
        url_fallback="https://www.fao.org/fao-who-codexalimentarius/fr/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    # ── Organismes nationaux de normalisation ─────────────────────────────────
    SourceDoc(
        doc_id="normes_codinorm_ci",
        nom="CODINORM — Organisme de Normalisation Côte d'Ivoire",
        pays="CI", zone="UEMOA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.codinorm.ci/",
        url_fallback="https://www.codinorm.ci/normes",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="normes_anor_cm",
        nom="Normalisation et qualité Cameroun — économie et industrie (Wikipedia FR)",
        pays="CM", zone="CEMAC", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Cameroun",
        url_fallback="https://fr.wikipedia.org/wiki/Cameroun",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_asn_sn",
        nom="Normalisation et qualité Sénégal — économie et industrie (Wikipedia FR)",
        pays="SN", zone="UEMOA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_S%C3%A9n%C3%A9gal",
        url_fallback="https://fr.wikipedia.org/wiki/S%C3%A9n%C3%A9gal",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_abnorm_bj",
        nom="Normalisation et qualité Bénin — économie et industrie (Wikipedia FR)",
        pays="BJ", zone="UEMOA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_B%C3%A9nin",
        url_fallback="https://fr.wikipedia.org/wiki/B%C3%A9nin",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_oapi_pi",
        nom="OAPI — Organisation Africaine de la Propriété Intellectuelle (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="CEMAC", domaine="normes",
        metier_tags=["juriste", "auditeur", "commercial", "risk_manager"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Organisation_africaine_de_la_propri%C3%A9t%C3%A9_intellectuelle",
        url_fallback="https://fr.wikipedia.org/wiki/Propri%C3%A9t%C3%A9_intellectuelle",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── UEMOA / CEMAC — Directives sectorielles ───────────────────────────────
    SourceDoc(
        doc_id="normes_uemoa_directives",
        nom="UEMOA — Union Économique et Monétaire Ouest-Africaine (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="UEMOA", domaine="normes",
        metier_tags=["juriste", "DAF", "auditeur", "commercial", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Union_%C3%A9conomique_et_mon%C3%A9taire_ouest-africaine",
        url_fallback="https://fr.wikipedia.org/wiki/Zone_franc",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_cemac_directives",
        nom="CEMAC — Règlements et Directives communautaires",
        pays="TRANSNATIONAL", zone="CEMAC", domaine="normes",
        metier_tags=["juriste", "DAF", "auditeur", "commercial", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.cemac.int/actes-communautaires/",
        url_fallback="https://www.cemac.int/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # COMMERCE INTERNATIONAL — OMC, AfCFTA, accords régionaux
    # ══════════════════════════════════════════════════════════════════════════

    SourceDoc(
        doc_id="commerce_omc_accords",
        nom="OMC — Accords et textes juridiques (commerce international)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "commercial", "DAF", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.wto.org/french/docs_f/legal_f/legal_f.htm",
        url_fallback="https://www.wto.org/french/tratop_f/tratop_f.htm",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="commerce_omc_profils_pays",
        nom="OMC — Profils tarifaires et commerciaux des pays Afrique",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["commercial", "analyste", "DAF", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.wto.org/french/res_f/statis_f/statis_f.htm",
        url_fallback="https://www.wto.org/french/res_f/publications_f/publications_f.htm",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="commerce_afcfta",
        nom="ZLECAf/AfCFTA — Accord de libre-échange continental africain",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "commercial", "DAF", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://au-afcfta.org/legal-texts/",
        url_fallback="https://au-afcfta.org/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="commerce_uemoa_tarif",
        nom="UEMOA — Tarif extérieur commun TEC et union douanière (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="UEMOA", domaine="commercial",
        metier_tags=["juriste", "commercial", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Tarif_ext%C3%A9rieur_commun_de_l%27UEMOA",
        url_fallback="https://fr.wikipedia.org/wiki/Union_%C3%A9conomique_et_mon%C3%A9taire_ouest-africaine",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="commerce_unctad_investissement",
        nom="CNUCED/UNCTAD — Rapport mondial sur l'investissement 2023 (WIR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["analyste", "DAF", "commercial", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://unctad.org/fr/publication/world-investment-report-2023",
        url_fallback="https://fr.wikipedia.org/wiki/Conf%C3%A9rence_des_Nations_unies_sur_le_commerce_et_le_d%C3%A9veloppement",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=8760,
    ),

    SourceDoc(
        doc_id="commerce_itc_trademap_sn",
        nom="Commerce International — Sénégal (Banque Mondiale / OMC)",
        pays="SN", zone="UEMOA", domaine="commercial",
        metier_tags=["analyste", "commercial", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_S%C3%A9n%C3%A9gal",
        url_fallback="https://fr.wikipedia.org/wiki/S%C3%A9n%C3%A9gal",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ── Sécurité industrielle et prévention des risques ───────────────────────
    SourceDoc(
        doc_id="normes_inrs_prevention",
        nom="INRS France — Prévention des risques professionnels (applicable CIMA)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["risk_manager", "DRH", "assureur", "auditeur"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.inrs.fr/media.html?refINRS=ED%206026",
        url_fallback="https://fr.wikipedia.org/wiki/Sant%C3%A9_et_s%C3%A9curit%C3%A9_au_travail",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_unido_industrie_afrique",
        nom="ONUDI/UNIDO — Développement industriel Afrique (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["analyste", "risk_manager", "assureur", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Organisation_des_Nations_unies_pour_le_d%C3%A9veloppement_industriel",
        url_fallback="https://fr.wikipedia.org/wiki/Industrialisation",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_cedeao_industrie",
        nom="CEDEAO — Intégration économique Afrique de l'Ouest (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="UEMOA", domaine="normes",
        metier_tags=["juriste", "commercial", "analyste", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Communaut%C3%A9_%C3%A9conomique_des_%C3%89tats_de_l%27Afrique_de_l%27Ouest",
        url_fallback="https://fr.wikipedia.org/wiki/Zone_franc",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # OHADA — Actes Uniformes supplémentaires
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="ohada_audcg",
        nom="OHADA — Acte Uniforme Droit Commercial Général (AUDCG 2010)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "commercial", "DAF", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ohada.com/telechargement/actes-uniformes/AUDCG-2010_fr.pdf",
        url_fallback="https://www.ohada.com/textes-ohada/actes-uniformes.html",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="ohada_auscgie",
        nom="OHADA — Acte Uniforme Droit des Sociétés Commerciales (AUSCGIE 2014)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "DAF", "auditeur", "assureur", "comptable"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ohada.com/telechargement/actes-uniformes/AUSCGIE-2014_fr.pdf",
        url_fallback="https://www.ohada.com/textes-ohada/actes-uniformes.html",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="ohada_aus",
        nom="OHADA — Acte Uniforme Organisation des Sûretés (AUS 2010)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "DAF", "banquier", "assureur", "risk_manager"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ohada.com/telechargement/actes-uniformes/AUS-2010_fr.pdf",
        url_fallback="https://www.ohada.com/textes-ohada/actes-uniformes.html",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="ohada_aupcap",
        nom="OHADA — Acte Uniforme Procédures Collectives d'Apurement du Passif (AUPCAP 2015)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "DAF", "comptable", "banquier"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ohada.com/telechargement/actes-uniformes/AUPCAP-2015_fr.pdf",
        url_fallback="https://www.ohada.com/textes-ohada/actes-uniformes.html",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="ohada_audcif",
        nom="OHADA — Acte Uniforme Droit Comptable et Information Financière (AUDCIF 2017)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="comptabilite",
        metier_tags=["comptable", "auditeur", "DAF", "fiscaliste"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ohada.com/telechargement/actes-uniformes/AUDCIF-2017_fr.pdf",
        url_fallback="https://www.ohada.com/textes-ohada/actes-uniformes.html",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="ohada_aua",
        nom="OHADA — Acte Uniforme sur l'Arbitrage (AUA 2017)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ohada.com/telechargement/actes-uniformes/AUA-2017_fr.pdf",
        url_fallback="https://www.ohada.com/textes-ohada/actes-uniformes.html",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="ohada_auscoop",
        nom="OHADA — Acte Uniforme Droit des Sociétés Coopératives (AUSCOOP 2010)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "DAF", "microfinance", "ong"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.ohada.com/telechargement/actes-uniformes/AUSCOOP-2010_fr.pdf",
        url_fallback="https://www.ohada.com/textes-ohada/actes-uniformes.html",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=4320,
    ),

    # NOTE CIMA : Le PDF officiel du Code CIMA n'est pas accessible publiquement en ligne
    # (protégé sur cima-afrique.org, 403 sur droit-afrique.com).
    # Le Code CIMA est géré via data/cima_knowledge/code_cima.json + cima_retriever.py.
    # Cette entrée sert uniquement à indexer les rapports statistiques du marché CIMA.
    SourceDoc(
        doc_id="code_cima_pdf",
        nom="CIMA — Rapports et statistiques du marché des assurances (FANAF/CRCA)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="assurance",
        metier_tags=["assureur", "juriste", "actuaire", "DAF", "risk_manager", "courtier"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://cima-afrique.org/publication/",
        url_fallback="https://cima-afrique.org/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # ITC TRADE MAP — Statistiques commerciales par pays CIMA
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="commerce_itc_trademap_cm",
        nom="Commerce International — Cameroun (Banque Mondiale / OMC)",
        pays="CM", zone="CEMAC", domaine="commercial",
        metier_tags=["analyste", "commercial", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Cameroun",
        url_fallback="https://fr.wikipedia.org/wiki/Cameroun",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="commerce_itc_trademap_ci",
        nom="Commerce International — Côte d'Ivoire (Banque Mondiale / OMC)",
        pays="CI", zone="UEMOA", domaine="commercial",
        metier_tags=["analyste", "commercial", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_C%C3%B4te_d%27Ivoire",
        url_fallback="https://fr.wikipedia.org/wiki/C%C3%B4te_d%27Ivoire",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # NORMES COMPTABLES — IFRS/IAS, Zone Franc
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="normes_ifrs_comptabilite",
        nom="IFRS — International Financial Reporting Standards (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["comptable", "auditeur", "DAF", "actuaire", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/International_Financial_Reporting_Standards",
        url_fallback="https://fr.wikipedia.org/wiki/Normes_comptables_internationales",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_zone_franc",
        nom="Zone Franc — Franc CFA, UEMOA, CEMAC (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "actuaire", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Zone_franc",
        url_fallback="https://fr.wikipedia.org/wiki/Franc_CFA",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # ÉCONOMIE PAR PAYS — CIMA sans couverture WB (Wikipedia FR)
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="eco_wiki_ml",
        nom="Économie du Mali — Wikipedia FR",
        pays="ML", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Mali",
        url_fallback="https://fr.wikipedia.org/wiki/Mali",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_wiki_ne",
        nom="Économie du Niger — Wikipedia FR",
        pays="NE", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Niger",
        url_fallback="https://fr.wikipedia.org/wiki/Niger",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_wiki_cg",
        nom="Économie du Congo-Brazzaville — Wikipedia FR",
        pays="CG", zone="CEMAC", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_r%C3%A9publique_du_Congo",
        url_fallback="https://fr.wikipedia.org/wiki/R%C3%A9publique_du_Congo",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_wiki_td",
        nom="Économie du Tchad — Wikipedia FR",
        pays="TD", zone="CEMAC", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Tchad",
        url_fallback="https://fr.wikipedia.org/wiki/Tchad",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_wiki_cf",
        nom="Économie de la Centrafrique — Wikipedia FR",
        pays="CF", zone="CEMAC", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_R%C3%A9publique_centrafricaine",
        url_fallback="https://fr.wikipedia.org/wiki/R%C3%A9publique_centrafricaine",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_wiki_gq",
        nom="Économie de la Guinée Équatoriale — Wikipedia FR",
        pays="GQ", zone="CEMAC", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_Guin%C3%A9e_%C3%A9quatoriale",
        url_fallback="https://fr.wikipedia.org/wiki/Guin%C3%A9e_%C3%A9quatoriale",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_wiki_gn",
        nom="Économie de la Guinée Conakry — Wikipedia FR",
        pays="GN", zone="NATIONAL", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_Guin%C3%A9e",
        url_fallback="https://fr.wikipedia.org/wiki/Guin%C3%A9e",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_wiki_km",
        nom="Économie des Comores — Wikipedia FR",
        pays="KM", zone="NATIONAL", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_des_Comores",
        url_fallback="https://fr.wikipedia.org/wiki/Comores",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="eco_wiki_gw",
        nom="Économie de la Guinée-Bissau — Wikipedia FR",
        pays="GW", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_Guin%C3%A9e-Bissau",
        url_fallback="https://fr.wikipedia.org/wiki/Guin%C3%A9e-Bissau",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # MARCHÉS FINANCIERS — BRVM, BOAD, BAD
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="eco_afdb_afrique",
        nom="BAD/AfDB — Banque Africaine de Développement (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "risk_manager"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Banque_africaine_de_d%C3%A9veloppement",
        url_fallback="https://fr.wikipedia.org/wiki/D%C3%A9veloppement_%C3%A9conomique_de_l%27Afrique",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),
    SourceDoc(
        doc_id="commerce_brvm",
        nom="BRVM — Bourse Régionale des Valeurs Mobilières UEMOA",
        pays="TRANSNATIONAL", zone="UEMOA", domaine="commercial",
        metier_tags=["assureur", "analyste", "DAF", "actuaire", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.brvm.org/fr",
        url_fallback="https://fr.wikipedia.org/wiki/Bourse_r%C3%A9gionale_des_valeurs_mobili%C3%A8res",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="eco_boad_rapport",
        nom="BOAD — Banque Ouest-Africaine de Développement (financement projets UEMOA)",
        pays="TRANSNATIONAL", zone="UEMOA", domaine="economie",
        metier_tags=["analyste", "DAF", "assureur", "risk_manager"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.boad.org/fr/",
        url_fallback="https://fr.wikipedia.org/wiki/Banque_ouest-africaine_de_d%C3%A9veloppement",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # NORMES — Qualité, environnement, développement durable
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="normes_iso_14001_env",
        nom="ISO 14001:2015 — Management environnemental (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/ISO_14001",
        url_fallback="https://fr.wikipedia.org/wiki/Syst%C3%A8me_de_management_environnemental",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_afnor_qualite",
        nom="AFNOR — Normalisation française et internationale (publications)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.afnor.org/",
        url_fallback="https://fr.wikipedia.org/wiki/Association_fran%C3%A7aise_de_normalisation",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="normes_gri_reporting",
        nom="GRI — Standards de reporting développement durable (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "DAF", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Global_Reporting_Initiative",
        url_fallback="https://fr.wikipedia.org/wiki/Reporting_extra-financier",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # MARCHÉS PUBLICS — Pays UEMOA/CIMA manquants
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="marches_publics_ci",
        nom="Code des Marchés Publics — Côte d'Ivoire (ANRMP)",
        pays="CI", zone="UEMOA", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://anrmp.ci/",
        url_fallback="https://anrmp.ci/reglementation/",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="marches_publics_bj",
        nom="Code des Marchés Publics — Bénin (portail ARCOP)",
        pays="BJ", zone="UEMOA", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://arcop.bj/",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_B%C3%A9nin",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="marches_publics_tg",
        nom="Code des Marchés Publics — Togo (portail ARMP)",
        pays="TG", zone="UEMOA", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://www.armp.tg/",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Togo",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    SourceDoc(
        doc_id="marches_publics_bf",
        nom="Marchés Publics — Burkina Faso (ARCOP)",
        pays="BF", zone="UEMOA", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Burkina_Faso",
        url_fallback="https://fr.wikipedia.org/wiki/Burkina_Faso",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="marches_publics_ne",
        nom="Code des Marchés Publics — Niger (Ordonnance 2011-23)",
        pays="NE", zone="UEMOA", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/niger/Niger-code-marches-publics-2011.pdf",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Niger",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="marches_publics_ml",
        nom="Code des Marchés Publics — Mali (Décret 2015-0604)",
        pays="ML", zone="UEMOA", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.DIRECT_PDF,
        url_principale="https://www.droit-afrique.com/upload/doc/mali/Mali-code-marches-publics-2015.pdf",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Mali",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=2160,
    ),

    SourceDoc(
        doc_id="marches_publics_gn",
        nom="Code des Marchés Publics — Guinée Conakry (ANRMP)",
        pays="GN", zone="NATIONAL", domaine="marches_publics",
        metier_tags=["acheteur_public", "juriste", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://anrmp.gouv.gn/",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_Guin%C3%A9e",
        fiabilite=Fiabilite.OFFICIEL,
        check_freq_heures=720,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CHAMBRES DE COMMERCE — CCI par pays
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="commerce_cci_cm",
        nom="CCIMA Cameroun — Chambre de Commerce d'Industrie des Mines et de l'Artisanat (Wikipedia FR)",
        pays="CM", zone="CEMAC", domaine="commercial",
        metier_tags=["commercial", "DAF", "analyste", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Chambre_de_commerce,_d%27industrie,_des_mines_et_de_l%27artisanat_du_Cameroun",
        url_fallback="https://fr.wikipedia.org/wiki/%C3%89conomie_du_Cameroun",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="commerce_cci_sn",
        nom="Économie Sénégal — Commerce et industrie (Wikipedia FR)",
        pays="SN", zone="UEMOA", domaine="commercial",
        metier_tags=["commercial", "DAF", "analyste", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_du_S%C3%A9n%C3%A9gal",
        url_fallback="https://fr.wikipedia.org/wiki/S%C3%A9n%C3%A9gal",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="commerce_cci_ci",
        nom="CCI-CI — Chambre de Commerce et d'Industrie de Côte d'Ivoire (Wikipedia FR)",
        pays="CI", zone="UEMOA", domaine="commercial",
        metier_tags=["commercial", "DAF", "analyste", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/%C3%89conomie_de_la_C%C3%B4te_d%27Ivoire",
        url_fallback="https://fr.wikipedia.org/wiki/C%C3%B4te_d%27Ivoire",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # COMMERCE INTERNATIONAL — Droit, instruments, régimes
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="commerce_incoterms",
        nom="Incoterms — Termes commerciaux internationaux (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["commercial", "DAF", "juriste", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Incoterms",
        url_fallback="https://fr.wikipedia.org/wiki/Commerce_international",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="commerce_cisg_vente_inter",
        nom="CISG — Convention de Vienne sur la vente internationale (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["juriste", "commercial", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Convention_des_Nations_unies_sur_les_contrats_de_vente_internationale_de_marchandises",
        url_fallback="https://fr.wikipedia.org/wiki/Vente_internationale_de_marchandises",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="commerce_syscohada_comptabilite",
        nom="SYSCOHADA — Système comptable OHADA révisé (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["comptable", "DAF", "auditeur", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Syst%C3%A8me_comptable_OHADA",
        url_fallback="https://fr.wikipedia.org/wiki/Organisation_pour_l%27harmonisation_en_Afrique_du_droit_des_affaires",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="commerce_lettre_credit_ucp",
        nom="Lettre de crédit — UCP 600 documentaire (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["commercial", "DAF", "banquier"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Lettre_de_cr%C3%A9dit",
        url_fallback="https://fr.wikipedia.org/wiki/Cr%C3%A9dit_documentaire",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="commerce_agoa_usa_afrique",
        nom="AGOA — African Growth and Opportunity Act (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="commercial",
        metier_tags=["commercial", "analyste", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/African_Growth_and_Opportunity_Act",
        url_fallback="https://fr.wikipedia.org/wiki/Relations_%C3%A9conomiques_Afrique-%C3%89tats-Unis",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # NORMES QUALITÉ INDUSTRIELLE — ISO supplémentaires, méthodes, ARSO
    # ══════════════════════════════════════════════════════════════════════════
    SourceDoc(
        doc_id="normes_iso_27001_securite_info",
        nom="ISO/CEI 27001 — Sécurité des systèmes d'information (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["risk_manager", "auditeur", "assureur", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/ISO/CEI_27001",
        url_fallback="https://fr.wikipedia.org/wiki/S%C3%A9curit%C3%A9_des_syst%C3%A8mes_d%27information",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_iso_22000_securite_alim",
        nom="ISO 22000 — Sécurité des aliments, HACCP (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["risk_manager", "auditeur", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/ISO_22000",
        url_fallback="https://fr.wikipedia.org/wiki/Hazard_Analysis_Critical_Control_Point",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_iso_26000_rse",
        nom="ISO 26000 — Responsabilité sociétale des organisations (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["risk_manager", "auditeur", "assureur", "DAF", "commercial"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/ISO_26000",
        url_fallback="https://fr.wikipedia.org/wiki/Responsabilit%C3%A9_soci%C3%A9tale_des_entreprises",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_haccp_alimentaire",
        nom="HACCP — Analyse des dangers et maîtrise des points critiques (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["risk_manager", "auditeur", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Hazard_Analysis_Critical_Control_Point",
        url_fallback="https://fr.wikipedia.org/wiki/S%C3%A9curit%C3%A9_des_aliments",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_six_sigma_qualite",
        nom="Six Sigma — Méthode de qualité industrielle (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "commercial", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Six_Sigma",
        url_fallback="https://fr.wikipedia.org/wiki/Am%C3%A9lioration_continue",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_lean_production",
        nom="Lean Manufacturing — Production allégée Toyota (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "commercial", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Lean_(production)",
        url_fallback="https://fr.wikipedia.org/wiki/Am%C3%A9lioration_continue",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_arso_afrique",
        nom="ARSO — Organisation africaine de normalisation (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "commercial", "assureur"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Organisation_africaine_de_normalisation",
        url_fallback="https://fr.wikipedia.org/wiki/Normalisation",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),

    SourceDoc(
        doc_id="normes_smi_management_qse",
        nom="Système de management — QSE intégré qualité-sécurité-environnement (Wikipedia FR)",
        pays="TRANSNATIONAL", zone="OHADA", domaine="normes",
        metier_tags=["auditeur", "risk_manager", "assureur", "DAF"],
        source_type=SourceType.HTML_PAGE,
        url_principale="https://fr.wikipedia.org/wiki/Syst%C3%A8me_de_management",
        url_fallback="https://fr.wikipedia.org/wiki/Management_de_la_qualit%C3%A9",
        fiabilite=Fiabilite.SEMI_OFFICIEL,
        check_freq_heures=4320,
    ),
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_source(doc_id: str) -> Optional[SourceDoc]:
    for s in SOURCES:
        if s.doc_id == doc_id:
            return s
    return None


def get_sources_par_pays(pays: str) -> list[SourceDoc]:
    return [s for s in SOURCES if s.pays == pays]


def get_sources_par_domaine(domaine: str) -> list[SourceDoc]:
    return [s for s in SOURCES if s.domaine == domaine]


def get_sources_par_metier(metier: str) -> list[SourceDoc]:
    return [s for s in SOURCES if metier in s.metier_tags]


PAYS_COUVERTS = sorted({s.pays for s in SOURCES if s.pays != "TRANSNATIONAL"})
DOMAINES_COUVERTS = sorted({s.domaine for s in SOURCES})
