# -*- coding: utf-8 -*-
"""Inject `key:` field into TEMPLATES_PAR_METIER entries in GenerateursPage.tsx.
Matches order with DATA in _migrate_templates.py."""
import re
from pathlib import Path

# Slugs in same order as TEMPLATES_PAR_METIER (19 cats; templates flat order)
CAT_SLUGS = [
    "comptabilite_finance", "juridique_conformite", "rh_management",
    "banque_microfinance", "commerce_business", "ong_projets",
    "ingenierie_btp", "sante_publique", "recherche_protocoles",
    "suivi_evaluation", "assurance_cima", "energie_mines",
    "agriculture", "transport_logistique", "tech_digital",
    "education_formation", "immobilier", "tourisme",
    "communication_marketing",
]

# Flat template slugs in encounter order
TPL_SLUGS = [
    "bilan_syscohada", "note_is_tva", "audit_interne", "presentation_resultats",
    "note_juridique_ohada", "due_diligence", "conformite_cima",
    "bilan_social", "restructuration_rh", "formation_management",
    "analyse_credit_pme", "ratios_cobac", "comite_credit",
    "business_plan", "analyse_marche", "pitch_deck", "prospection",
    "rapport_activites_ong", "note_conceptuelle", "presentation_bailleur",
    "avancement_travaux", "note_technique_etude",
    "situation_epidemio", "protocole_enquete_epidemio", "evaluation_programme_sante",
    "formation_sante_publique", "presentation_programme_sante",
    "protocole_etude", "rapport_enquete", "presentation_protocole",
    "rapport_se", "cadre_mesure_performance", "presentation_se_bailleur", "evaluation_finale",
    "solvabilite_cima", "tarification_actuarielle", "gestion_sinistre", "ca_assurance",
    "eies_minier", "production_mensuelle", "rentabilite_mines",
    "plan_agricole", "etude_filiere", "campagne_agricole",
    "audit_supply_chain", "transport_urbain", "bp_flotte_transport",
    "cdc_si", "audit_cybersecurite", "pitch_tech_startup",
    "plan_strategique_etablissement", "rapport_pedagogique", "module_formation_pro",
    "faisabilite_immobiliere", "expertise_immobiliere",
    "bp_hotel", "performance_hoteliere",
    "plan_communication", "brief_creatif", "bilan_campagne_com",
]

p = Path(__file__).parent.parent / "pages" / "GenerateursPage.tsx"
src = p.read_text(encoding="utf-8")

# Locate the TEMPLATES_PAR_METIER block
start = src.index("const TEMPLATES_PAR_METIER")
end_marker = "\n];\n"
end = src.index(end_marker, start) + len(end_marker)
block = src[start:end]

# Inject category keys: replace `    categorie: "...",` -> add `    key: "<slug>",\n` BEFORE
cat_iter = iter(CAT_SLUGS)
def repl_cat(m):
    return f'    key: "{next(cat_iter)}",\n{m.group(0)}'
new_block = re.sub(r'^    categorie: "[^"]+",', repl_cat, block, flags=re.M)

# Inject template keys: replace `        label: "...",` -> add `        key: "<slug>",\n` BEFORE
tpl_iter = iter(TPL_SLUGS)
def repl_tpl(m):
    return f'        key: "{next(tpl_iter)}",\n{m.group(0)}'
new_block = re.sub(r'^        label: "[^"]+",', repl_tpl, new_block, flags=re.M)

# Update interfaces
new_src = src.replace(
    "interface Template {\n  label: string;",
    "interface Template {\n  key: string;\n  label: string;",
)
new_src = new_src.replace(
    "interface CategorieTemplates {\n  categorie: string;",
    "interface CategorieTemplates {\n  key: string;\n  categorie: string;",
)
new_src = new_src.replace(block, new_block)

p.write_text(new_src, encoding="utf-8")
print(f"OK — injected {len(CAT_SLUGS)} cat keys + {len(TPL_SLUGS)} template keys")
