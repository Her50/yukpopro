# -*- coding: utf-8 -*-
"""Migrate TEMPLATES_PAR_METIER into i18n. Injects keys into fr.json + en.json.
Other languages auto-fallback to FR via i18next config.
Run once: python _migrate_templates.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

# (cat_slug, fr_label, en_label, [(tpl_slug, fr_label, en_label, fr_desc, en_desc), ...])
DATA = [
    ("comptabilite_finance", "Comptabilité & Finance", "Accounting & Finance", [
        ("bilan_syscohada", "Bilan SYSCOHADA commenté", "Annotated SYSCOHADA balance sheet",
         "Bilan annuel avec analyse des ratios clés (liquidité, solvabilité, rentabilité)",
         "Annual balance sheet with key ratio analysis (liquidity, solvency, profitability)"),
        ("note_is_tva", "Note de calcul IS + TVA", "Corporate tax + VAT calculation note",
         "Calcul détaillé de l'Impôt sur les Sociétés et de la TVA collectée/déductible",
         "Detailed corporate income tax and collected/deductible VAT calculation"),
        ("audit_interne", "Rapport d'audit interne", "Internal audit report",
         "Rapport d'audit des procédures comptables et points de contrôle interne",
         "Audit report on accounting procedures and internal control points"),
        ("presentation_resultats", "Présentation résultats financiers", "Financial results presentation",
         "Slides de présentation des résultats au comité de direction",
         "Slide deck presenting results to the executive committee"),
    ]),
    ("juridique_conformite", "Juridique & Conformité", "Legal & Compliance", [
        ("note_juridique_ohada", "Note juridique OHADA", "OHADA legal note",
         "Analyse d'une problématique juridique selon le droit OHADA",
         "Analysis of a legal issue under OHADA law"),
        ("due_diligence", "Rapport de due diligence", "Due diligence report",
         "Due diligence juridique et financière pour acquisition ou partenariat",
         "Legal and financial due diligence for acquisition or partnership"),
        ("conformite_cima", "Note de conformité CIMA", "CIMA compliance note",
         "Vérification de conformité au Code CIMA pour compagnies d'assurance",
         "CIMA Code compliance check for insurance companies"),
    ]),
    ("rh_management", "RH & Management", "HR & Management", [
        ("bilan_social", "Rapport bilan social", "Social audit report",
         "Bilan social annuel — effectifs, rémunérations, formation, absentéisme",
         "Annual social audit — workforce, compensation, training, absenteeism"),
        ("restructuration_rh", "Plan de restructuration RH", "HR restructuring plan",
         "Note de restructuration des effectifs avec plan social",
         "Workforce restructuring note with social plan"),
        ("formation_management", "Slides séminaire formation", "Training seminar slides",
         "Support de formation professionnelle (leadership, gestion d'équipe, etc.)",
         "Professional training material (leadership, team management, etc.)"),
    ]),
    ("banque_microfinance", "Banque & Microfinance", "Banking & Microfinance", [
        ("analyse_credit_pme", "Rapport analyse crédit PME", "SME credit analysis report",
         "Analyse de risque crédit pour une PME — scoring et décision",
         "Credit risk analysis for an SME — scoring and decision"),
        ("ratios_cobac", "Note ratios prudentiels COBAC", "COBAC prudential ratios note",
         "Calcul et commentaire des ratios prudentiels COBAC",
         "Calculation and commentary on COBAC prudential ratios"),
        ("comite_credit", "Présentation comité de crédit", "Credit committee presentation",
         "Slides de présentation d'un dossier au comité de crédit",
         "Slide deck presenting a file to the credit committee"),
    ]),
    ("commerce_business", "Commerce & Business", "Commerce & Business", [
        ("business_plan", "Business plan complet", "Complete business plan",
         "Business plan structuré pour création ou développement d'activité",
         "Structured business plan for creation or business development"),
        ("analyse_marche", "Rapport analyse de marché", "Market analysis report",
         "Étude de marché sectorielle pour un pays d'Afrique subsaharienne",
         "Sectoral market study for a sub-Saharan African country"),
        ("pitch_deck", "Pitch deck investisseurs", "Investor pitch deck",
         "Présentation de levée de fonds pour investisseurs africains / internationaux",
         "Fundraising presentation for African / international investors"),
        ("prospection", "Rapport prospection commerciale", "Sales prospecting report",
         "Analyse prospects et stratégie de développement commercial",
         "Prospect analysis and commercial development strategy"),
    ]),
    ("ong_projets", "ONG & Projets", "NGO & Projects", [
        ("rapport_activites_ong", "Rapport d'activités ONG", "NGO activity report",
         "Rapport annuel d'activités pour bailleurs et partenaires",
         "Annual activity report for donors and partners"),
        ("note_conceptuelle", "Note conceptuelle projet", "Project concept note",
         "Note conceptuelle pour soumission à un appel à projets / bailleur",
         "Concept note for submission to a call for proposals / donor"),
        ("presentation_bailleur", "Présentation bailleur de fonds", "Donor presentation",
         "Slides de présentation d'un projet à un bailleur ou comité de pilotage",
         "Slide deck presenting a project to a donor or steering committee"),
    ]),
    ("ingenierie_btp", "Ingénierie & BTP", "Engineering & Construction", [
        ("avancement_travaux", "Rapport d'avancement travaux", "Construction progress report",
         "Rapport mensuel d'avancement d'un chantier",
         "Monthly progress report for a construction site"),
        ("note_technique_etude", "Note technique étude", "Technical study note",
         "Note technique pour une étude d'ingénierie ou d'avant-projet",
         "Technical note for an engineering or preliminary project study"),
    ]),
    ("sante_publique", "Santé Publique & Épidémiologie", "Public Health & Epidemiology", [
        ("situation_epidemio", "Rapport de situation épidémiologique", "Epidemiological situation report",
         "Rapport de situation épidémio hebdomadaire ou mensuel",
         "Weekly or monthly epidemiological situation report"),
        ("protocole_enquete_epidemio", "Protocole d'enquête épidémiologique", "Epidemiological survey protocol",
         "Protocole complet pour enquête de terrain en santé publique",
         "Complete protocol for public health field investigation"),
        ("evaluation_programme_sante", "Rapport d'évaluation programme santé", "Health program evaluation report",
         "Évaluation mi-parcours ou finale d'un programme de santé",
         "Mid-term or final evaluation of a health program"),
        ("formation_sante_publique", "Formation — Outils de santé publique", "Training — Public health tools",
         "Support de formation sur les outils et méthodes en santé publique",
         "Training material on public health tools and methods"),
        ("presentation_programme_sante", "Présentation programme santé", "Health program presentation",
         "Slides de présentation d'un programme ou rapport de santé publique",
         "Slide deck for a public health program or report"),
    ]),
    ("recherche_protocoles", "Recherche & Protocoles d'étude", "Research & Study Protocols", [
        ("protocole_etude", "Protocole d'étude / recherche", "Study / research protocol",
         "Protocole scientifique complet pour étude ou recherche",
         "Complete scientific protocol for a study or research project"),
        ("rapport_enquete", "Rapport d'enquête / sondage", "Survey / poll report",
         "Rapport de résultats d'une enquête quantitative ou qualitative",
         "Results report of a quantitative or qualitative survey"),
        ("presentation_protocole", "Présentation protocole / résultats", "Protocol / results presentation",
         "Slides de présentation d'un protocole ou des résultats d'étude",
         "Slide deck presenting a protocol or study results"),
    ]),
    ("suivi_evaluation", "Suivi & Évaluation de projets", "Monitoring & Evaluation", [
        ("rapport_se", "Rapport de suivi S&E", "M&E monitoring report",
         "Rapport trimestriel ou semestriel de suivi-évaluation d'un projet",
         "Quarterly or semi-annual monitoring & evaluation report for a project"),
        ("cadre_mesure_performance", "Cadre de mesure de la performance", "Performance measurement framework",
         "Document CMP / tableau de bord indicateurs d'un projet",
         "PMF document / project indicators dashboard"),
        ("presentation_se_bailleur", "Présentation S&E bailleur", "M&E donor presentation",
         "Slides de rapport de suivi à destination du bailleur ou comité",
         "Monitoring report slides for the donor or steering committee"),
        ("evaluation_finale", "Évaluation finale de projet", "Final project evaluation",
         "Rapport d'évaluation finale selon critères OCDE/CAD",
         "Final evaluation report following OECD/DAC criteria"),
    ]),
    ("assurance_cima", "Assurance & Réassurance CIMA", "Insurance & CIMA Reinsurance", [
        ("solvabilite_cima", "Rapport de solvabilité CIMA", "CIMA solvency report",
         "Rapport annuel de solvabilité selon le Code CIMA révisé",
         "Annual solvency report under the revised CIMA Code"),
        ("tarification_actuarielle", "Note technique tarification", "Actuarial pricing note",
         "Note actuarielle de tarification d'un produit d'assurance",
         "Actuarial pricing note for an insurance product"),
        ("gestion_sinistre", "Rapport gestion sinistre", "Claims management report",
         "Rapport d'expertise et règlement d'un sinistre complexe",
         "Expert report and settlement of a complex claim"),
        ("ca_assurance", "Présentation conseil d'administration", "Board of directors presentation",
         "Slides de présentation CA compagnie d'assurance",
         "Board presentation slides for an insurance company"),
    ]),
    ("energie_mines", "Énergie, Mines & Pétrole", "Energy, Mining & Oil", [
        ("eies_minier", "Étude d'impact environnemental", "Environmental impact assessment",
         "EIES complète pour projet minier/énergétique (norme BAD/IFC)",
         "Full ESIA for a mining/energy project (AfDB/IFC standard)"),
        ("production_mensuelle", "Rapport production mensuelle", "Monthly production report",
         "Rapport mensuel de production énergie / mines",
         "Monthly production report for energy / mining"),
        ("rentabilite_mines", "Note étude rentabilité projet", "Project profitability study",
         "Analyse financière TRI/VAN pour projet énergie ou mines",
         "IRR/NPV financial analysis for an energy or mining project"),
    ]),
    ("agriculture", "Agriculture & Agro-industrie", "Agriculture & Agribusiness", [
        ("plan_agricole", "Plan de développement agricole", "Agricultural development plan",
         "Plan d'affaires exploitation agricole / agro-industrielle",
         "Business plan for an agricultural / agribusiness operation"),
        ("etude_filiere", "Étude de filière agricole", "Agricultural value chain study",
         "Analyse filière (cacao, café, coton, riz, etc.) pays CEMAC/UEMOA",
         "Value chain analysis (cocoa, coffee, cotton, rice, etc.) for CEMAC/WAEMU countries"),
        ("campagne_agricole", "Rapport campagne agricole", "Agricultural campaign report",
         "Bilan de campagne — rendements, ventes, marges",
         "Campaign review — yields, sales, margins"),
    ]),
    ("transport_logistique", "Transport & Logistique", "Transport & Logistics", [
        ("audit_supply_chain", "Étude logistique — chaîne d'approvisionnement", "Logistics study — supply chain",
         "Audit supply chain avec recommandations d'optimisation",
         "Supply chain audit with optimization recommendations"),
        ("transport_urbain", "Plan de transport urbain", "Urban transport plan",
         "Étude de schéma directeur transport pour collectivité",
         "Master transport plan study for a local authority"),
        ("bp_flotte_transport", "Business plan flotte transport", "Transport fleet business plan",
         "Dossier de financement création/extension flotte de transport",
         "Financing file for creating/expanding a transport fleet"),
    ]),
    ("tech_digital", "Tech, Digital & SI", "Tech, Digital & IS", [
        ("cdc_si", "Cahier des charges SI", "IS specifications document",
         "Cahier des charges fonctionnel et technique d'un projet SI",
         "Functional and technical specifications for an IS project"),
        ("audit_cybersecurite", "Rapport d'audit cybersécurité", "Cybersecurity audit report",
         "Audit sécurité informatique avec recommandations ISO 27001",
         "IT security audit with ISO 27001 recommendations"),
        ("pitch_tech_startup", "Pitch deck startup tech", "Tech startup pitch deck",
         "Pitch de levée pour startup tech africaine",
         "Fundraising pitch for an African tech startup"),
    ]),
    ("education_formation", "Éducation & Formation", "Education & Training", [
        ("plan_strategique_etablissement", "Plan stratégique établissement", "Institution strategic plan",
         "Plan stratégique pluriannuel pour établissement scolaire/universitaire",
         "Multi-year strategic plan for a school or university"),
        ("rapport_pedagogique", "Rapport pédagogique annuel", "Annual academic report",
         "Rapport annuel d'activités pédagogiques",
         "Annual report of academic activities"),
        ("module_formation_pro", "Module de formation professionnelle", "Professional training module",
         "Support de formation professionnelle certifiante",
         "Certifying professional training material"),
    ]),
    ("immobilier", "Immobilier & Construction", "Real Estate & Construction", [
        ("faisabilite_immobiliere", "Étude de faisabilité immobilière", "Real estate feasibility study",
         "Étude technique, juridique et financière d'un projet immobilier",
         "Technical, legal and financial study of a real estate project"),
        ("expertise_immobiliere", "Rapport expertise immobilière", "Real estate appraisal report",
         "Rapport d'expertise et valorisation d'un bien immobilier",
         "Appraisal and valuation report for a real estate asset"),
    ]),
    ("tourisme", "Tourisme & Hôtellerie", "Tourism & Hospitality", [
        ("bp_hotel", "Business plan hôtel / resort", "Hotel / resort business plan",
         "Business plan complet pour création hôtel ou resort",
         "Complete business plan for creating a hotel or resort"),
        ("performance_hoteliere", "Rapport performance hôtelière", "Hotel performance report",
         "Rapport mensuel KPIs hôteliers (TO, ADR, RevPAR, GOP)",
         "Monthly hotel KPI report (Occ, ADR, RevPAR, GOP)"),
    ]),
    ("communication_marketing", "Communication & Marketing", "Communication & Marketing", [
        ("plan_communication", "Plan de communication 360°", "360° communication plan",
         "Stratégie communication multicanale pour marque/produit",
         "Multichannel communication strategy for a brand/product"),
        ("brief_creatif", "Brief créatif campagne", "Campaign creative brief",
         "Brief créatif pour agence de communication",
         "Creative brief for a communication agency"),
        ("bilan_campagne_com", "Rapport bilan campagne", "Campaign review report",
         "Bilan de performance d'une campagne de communication",
         "Performance review of a communication campaign"),
    ]),
]


def build_section(lang):
    cats = {}
    items = {}
    for cat_slug, fr_l, en_l, tpls in DATA:
        cats[cat_slug] = fr_l if lang == "fr" else en_l
        for tpl_slug, fr_tl, en_tl, fr_d, en_d in tpls:
            items[tpl_slug] = {
                "label":       fr_tl if lang == "fr" else en_tl,
                "description": fr_d  if lang == "fr" else en_d,
            }
    return {"categories": cats, "items": items}


def merge_into(file_path, section):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("generateurs", {})["templates"] = section
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


for lang in ["fr", "en"]:
    section = build_section(lang)
    merge_into(HERE / f"{lang}.json", section)
    print(f"OK {lang} — {len(section['categories'])} cats, {len(section['items'])} items")

n_strings = sum(2 + 2 * len(t) for _, _, _, t in DATA)
print(f"Total: {n_strings} strings × 2 langs (FR/EN). Other 13 langs auto-fallback to FR.")
