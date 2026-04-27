"""
ReportWriter Pro — Générateur de rapports professionnels par IA.

Modes :
  - flash    : 1 page, réponse rapide, synthèse exécutive
  - standard : 3-5 pages, rapport complet structuré
  - complet  : 10-30 pages, rapport d'expertise approfondi

Sorties supportées :
  - DOCX (python-docx) — format éditable
  - PDF  (conversion via LibreOffice ou reportlab)
  - Markdown (toujours disponible, fallback)

Structures de rapports :
  - note_de_synthese    : résumé analytique d'un sujet
  - rapport_analyse     : analyse structurée avec recommandations
  - note_juridique      : analyse juridique avec références légales
  - rapport_financier   : analyse financière avec tableaux
  - rapport_rh          : bilan RH ou note sociale
  - plan_action         : plan d'action structuré
  - compte_rendu        : compte-rendu de réunion/événement
  - rapport_audit       : rapport d'audit ou de contrôle
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.report_writer")

# Répertoire de sortie
_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "generated" / "pro_reports"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Schémas de rapport par mode
# ══════════════════════════════════════════════════════════════════════════════

_STRUCTURES = {
    # ── Contrats et documents juridiques ──────────────────────────────────────
    "contrat_bail": {
        "flash":    ["Parties", "Objet du bail", "Durée et loyer", "Obligations", "Signatures"],
        "standard": ["Page de garde", "Parties au contrat", "Objet et désignation du bien",
                     "Durée du bail", "Loyer et charges", "Dépôt de garantie",
                     "Obligations du bailleur", "Obligations du locataire",
                     "Résiliation et renouvellement", "Dispositions diverses", "Signatures"],
        "complet":  ["Page de garde", "Parties au contrat", "Objet et désignation du bien",
                     "État des lieux", "Durée du bail", "Loyer et indexation",
                     "Charges et provisions", "Dépôt de garantie", "Assurances",
                     "Obligations du bailleur", "Obligations du locataire",
                     "Travaux et aménagements", "Résiliation", "Renouvellement",
                     "Clause pénale", "Élection de domicile", "Juridiction compétente",
                     "Dispositions finales", "Signatures et paraphes"],
    },
    "contrat_travail": {
        "flash":    ["Parties", "Poste et rémunération", "Durée", "Obligations", "Signatures"],
        "standard": ["Page de garde", "Parties", "Poste et missions", "Durée et période d'essai",
                     "Rémunération", "Lieu de travail", "Temps de travail",
                     "Obligations et confidentialité", "Résiliation", "Signatures"],
        "complet":  ["Page de garde", "Parties", "Poste et description des missions",
                     "Durée et période d'essai", "Rémunération et avantages",
                     "Lieu de travail et mobilité", "Temps de travail et congés",
                     "Obligations du salarié", "Obligations de l'employeur",
                     "Confidentialité et non-concurrence", "Propriété intellectuelle",
                     "Résiliation et préavis", "Droit applicable", "Signatures"],
    },
    "contrat_prestation": {
        "flash":    ["Parties", "Objet", "Prix", "Durée", "Signatures"],
        "standard": ["Page de garde", "Parties", "Objet de la prestation", "Délais et livrables",
                     "Prix et modalités de paiement", "Obligations réciproques",
                     "Confidentialité", "Résiliation", "Signatures"],
        "complet":  ["Page de garde", "Parties", "Objet et périmètre", "Livrables détaillés",
                     "Délais et planning", "Prix et facturation", "Conditions de paiement",
                     "Droits de propriété intellectuelle", "Confidentialité",
                     "Garanties et responsabilités", "Résiliation", "Litiges", "Signatures"],
    },
    "contrat_vente": {
        "flash":    ["Parties", "Objet", "Prix", "Livraison", "Signatures"],
        "standard": ["Page de garde", "Parties", "Objet de la vente", "Prix et paiement",
                     "Livraison et transfert de propriété", "Garanties",
                     "Résolution et litiges", "Signatures"],
        "complet":  ["Page de garde", "Parties", "Objet et description détaillée",
                     "Conditions tarifaires", "Modalités de paiement",
                     "Livraison et incoterms", "Transfert de propriété et des risques",
                     "Garanties légales et contractuelles", "Force majeure",
                     "Résolution et pénalités", "Droit applicable", "Signatures"],
    },
    "convention": {
        "flash":    ["Parties", "Objet", "Engagements", "Durée", "Signatures"],
        "standard": ["Page de garde", "Parties", "Objet de la convention",
                     "Engagements des parties", "Modalités d'exécution",
                     "Durée et renouvellement", "Résiliation", "Signatures"],
        "complet":  ["Page de garde", "Préambule", "Parties", "Objet",
                     "Engagements réciproques", "Modalités d'exécution", "Financement",
                     "Gouvernance et suivi", "Durée", "Résiliation", "Confidentialité",
                     "Litiges", "Dispositions finales", "Signatures"],
    },
    "contrat_generique": {
        "flash":    ["Parties", "Objet", "Engagements", "Durée", "Signatures"],
        "standard": ["Page de garde", "Parties au contrat", "Objet du contrat",
                     "Engagements des parties", "Conditions financières",
                     "Durée et renouvellement", "Résiliation", "Droit applicable", "Signatures"],
        "complet":  ["Page de garde", "Parties", "Préambule", "Objet", "Définitions",
                     "Engagements des parties", "Conditions financières",
                     "Durée", "Résiliation et conséquences", "Confidentialité",
                     "Force majeure", "Litiges", "Dispositions finales", "Signatures"],
    },
    "statuts": {
        "flash":    ["Dénomination", "Objet social", "Capital", "Gérance", "Durée"],
        "standard": ["Dénomination sociale", "Forme juridique", "Objet social", "Siège social",
                     "Durée", "Capital social et parts", "Gérance et direction",
                     "Assemblées générales", "Dissolution"],
        "complet":  ["Dénomination sociale", "Forme juridique", "Objet social", "Siège social",
                     "Durée de la société", "Capital social", "Parts sociales / Actions",
                     "Cession des parts", "Gérance", "Assemblées générales ordinaires",
                     "Assemblées générales extraordinaires", "Commissaires aux comptes",
                     "Exercice social et résultats", "Dissolution et liquidation", "Clauses finales"],
    },
    "reglement_interieur": {
        "flash":    ["Objet", "Règles de conduite", "Sanctions", "Entrée en vigueur"],
        "standard": ["Objet et champ d'application", "Règles générales de conduite",
                     "Horaires et organisation du travail", "Santé et sécurité",
                     "Procédure disciplinaire", "Harcèlement et discrimination",
                     "Entrée en vigueur"],
        "complet":  ["Objet et champ d'application", "Règles générales de conduite",
                     "Horaires, congés et absences", "Utilisation des équipements",
                     "Confidentialité et protection des données", "Santé et sécurité",
                     "Procédure disciplinaire et sanctions", "Harcèlement moral et sexuel",
                     "Représentation du personnel", "Réclamations et litiges internes",
                     "Entrée en vigueur et révision"],
    },
    # ── Lettres et courriers ───────────────────────────────────────────────────
    "lettre_officielle": {
        "flash":    ["En-tête", "Objet", "Corps", "Signature"],
        "standard": ["En-tête et coordonnées", "Destinataire", "Lieu et date",
                     "Objet", "Corps de la lettre", "Formule de politesse", "Signature"],
        "complet":  ["En-tête et coordonnées expéditeur", "Destinataire et fonction",
                     "Lieu et date", "Références", "Objet", "Pièces jointes",
                     "Corps détaillé", "Formule de politesse", "Signature et cachet"],
    },
    "lettre_commerciale": {
        "flash":    ["En-tête", "Objet commercial", "Proposition", "Appel à l'action"],
        "standard": ["En-tête", "Destinataire", "Date et référence", "Objet",
                     "Introduction et contexte", "Proposition", "Conditions",
                     "Appel à l'action", "Formule de politesse", "Signature"],
        "complet":  ["En-tête professionnel", "Destinataire", "Date et référence",
                     "Objet commercial précis", "Introduction contextualisée",
                     "Proposition de valeur détaillée", "Conditions commerciales",
                     "Arguments différenciateurs", "Offre et validité",
                     "Appel à l'action", "Formule de politesse", "Signature"],
    },
    "lettre_mise_en_demeure": {
        "flash":    ["Parties", "Faits", "Mise en demeure", "Délai", "Signature"],
        "standard": ["En-tête", "Destinataire", "Date", "Objet",
                     "Rappel des faits", "Base légale",
                     "Mise en demeure formelle", "Délai et conséquences", "Signature"],
        "complet":  ["En-tête et coordonnées", "Destinataire et qualité",
                     "Lieu et date", "Objet et références",
                     "Rappel des faits et chronologie", "Base légale et contractuelle",
                     "Manquements constatés", "Mise en demeure formelle",
                     "Délai impératif", "Conséquences en cas d'inaction",
                     "Réserve de tous droits", "Signature"],
    },
    "lettre_resiliation": {
        "flash":    ["Parties", "Référence contrat", "Motif", "Date d'effet", "Signature"],
        "standard": ["En-tête", "Destinataire", "Date", "Objet",
                     "Référence du contrat", "Motif de résiliation",
                     "Date d'effet et préavis", "Formalités de restitution", "Signature"],
        "complet":  ["En-tête", "Destinataire", "Lieu et date", "Référence contrat",
                     "Objet", "Motif détaillé de résiliation", "Base légale ou contractuelle",
                     "Date d'effet et respect du préavis", "Modalités de restitution",
                     "Règlement des sommes dues", "Levée des garanties", "Signature"],
    },
    "lettre_emploi": {
        "flash":    ["En-tête", "Poste visé", "Motivations", "Compétences", "Signature"],
        "standard": ["En-tête candidat", "Destinataire RH", "Date et référence",
                     "Objet et poste", "Paragraphe accroche",
                     "Expériences et compétences", "Motivations",
                     "Disponibilité", "Formule de politesse", "Signature"],
        "complet":  ["En-tête candidat", "Destinataire et recruteur",
                     "Référence de l'offre", "Accroche percutante",
                     "Parcours et accomplissements clés", "Compétences spécifiques au poste",
                     "Motivations pour l'entreprise et le secteur",
                     "Valeur ajoutée proposée", "Disponibilité et prétentions",
                     "Formule de politesse", "Signature"],
    },
    # ── Attestations ──────────────────────────────────────────────────────────
    "attestation": {
        "flash":    ["En-tête", "Identité", "Attestation", "Date", "Cachet"],
        "standard": ["En-tête entreprise", "Identité du soussigné",
                     "Objet de l'attestation", "Informations attestées",
                     "Déclaration sur l'honneur", "Lieu et date", "Cachet et signature"],
        "complet":  ["En-tête entreprise", "Identité et qualité du soussigné",
                     "Objet et nature de l'attestation", "Identité du bénéficiaire",
                     "Informations certifiées (période, poste, salaire…)",
                     "Déclaration sur l'honneur", "Usage prévu",
                     "Lieu et date", "Cachet officiel et signature"],
    },
    "certificat": {
        "flash":    ["En-tête", "Certifie que", "Date", "Signature"],
        "standard": ["En-tête officiel", "Titre du certificat", "Identité du bénéficiaire",
                     "Objet certifié", "Conditions d'obtention", "Date et validité", "Signature"],
        "complet":  ["En-tête officiel", "Titre et référence", "Identité du bénéficiaire",
                     "Objet et portée du certificat", "Critères et conditions d'obtention",
                     "Période de validité", "Restrictions éventuelles",
                     "Date d'émission", "Signatures et cachets autorisés"],
    },
    "note_de_synthese": {
        "flash":    ["Objet", "Synthèse", "Conclusion"],
        "standard": ["Page de garde", "Objet", "Contexte", "Analyse", "Recommandations", "Conclusion"],
        "complet":  ["Page de garde", "Sommaire", "Objet", "Contexte et enjeux", "Analyse détaillée",
                     "Cadre réglementaire", "Recommandations", "Plan de mise en oeuvre", "Conclusion",
                     "Annexes"],
    },
    "rapport_analyse": {
        "flash":    ["Résumé exécutif", "Constats clés", "Recommandations"],
        "standard": ["Page de garde", "Résumé exécutif", "Introduction", "Méthodologie",
                     "Analyse", "Constats", "Recommandations", "Conclusion"],
        "complet":  ["Page de garde", "Sommaire", "Résumé exécutif", "Introduction",
                     "Contexte et objectifs", "Méthodologie", "Analyse approfondie",
                     "Constats et observations", "Risques et opportunités",
                     "Recommandations stratégiques", "Plan d'action", "Conclusion", "Annexes"],
    },
    "note_juridique": {
        "flash":    ["Question de droit", "Analyse", "Avis"],
        "standard": ["En-tête", "Question de droit", "Cadre légal applicable",
                     "Analyse juridique", "Jurisprudence", "Avis et recommandations"],
        "complet":  ["En-tête", "Objet", "Question de droit", "Textes applicables",
                     "Analyse et interprétation", "Jurisprudence OHADA / nationale",
                     "Position doctrinale", "Risques juridiques", "Avis motivé",
                     "Recommandations pratiques", "Annexes"],
    },
    "rapport_financier": {
        "flash":    ["Résumé financier", "Indicateurs clés", "Conclusion"],
        "standard": ["Page de garde", "Résumé exécutif", "Situation financière",
                     "Analyse des résultats", "Ratios et indicateurs", "Recommandations"],
        "complet":  ["Page de garde", "Sommaire", "Résumé exécutif", "Contexte",
                     "Bilan et compte de résultat", "Analyse des flux de trésorerie",
                     "Ratios de performance", "Analyse comparative", "Prévisions",
                     "Points d'attention SYSCOHADA", "Recommandations", "Annexes"],
    },
    "rapport_rh": {
        "flash":    ["Situation RH", "Indicateurs", "Actions"],
        "standard": ["Page de garde", "Synthèse RH", "Effectifs et mouvements",
                     "Paie et charges sociales", "Formation", "Recommandations"],
        "complet":  ["Page de garde", "Sommaire", "Synthèse exécutive", "Contexte",
                     "Effectifs et pyramide des âges", "Recrutement et turnover",
                     "Paie et charges sociales CNAMGS/CNSS", "Formation et compétences",
                     "Climat social", "Conformité droit du travail", "Recommandations",
                     "Plan d'action RH", "Annexes"],
    },
    "plan_action": {
        "flash":    ["Objectif", "Actions prioritaires", "Responsables"],
        "standard": ["Contexte", "Objectifs", "Actions", "Responsables", "Délais", "Indicateurs"],
        "complet":  ["Contexte et enjeux", "Vision et objectifs stratégiques",
                     "Plan d'action détaillé", "Ressources nécessaires",
                     "Risques et mitigations", "Indicateurs de suivi (KPIs)",
                     "Gouvernance et comité de pilotage", "Calendrier", "Annexes"],
    },
    "compte_rendu": {
        "flash":    ["Participants", "Points abordés", "Décisions", "Actions"],
        "standard": ["En-tête", "Participants", "Ordre du jour", "Compte-rendu des échanges",
                     "Décisions prises", "Actions et responsables"],
        "complet":  ["En-tête", "Participants et excusés", "Ordre du jour",
                     "Ouverture et approbation PV précédent", "Compte-rendu détaillé",
                     "Questions diverses", "Décisions", "Actions (qui/quoi/quand)",
                     "Prochaine réunion"],
    },
    "rapport_audit": {
        "flash":    ["Périmètre", "Constats majeurs", "Recommandations prioritaires"],
        "standard": ["Page de garde", "Périmètre et objectifs", "Méthodologie",
                     "Constats et observations", "Évaluation des risques",
                     "Recommandations", "Plan de remédiation"],
        "complet":  ["Page de garde", "Lettre de mission", "Sommaire", "Synthèse",
                     "Périmètre et objectifs", "Méthodologie d'audit",
                     "Constats détaillés par domaine", "Évaluation des risques (matrice)",
                     "Recommandations classées par priorité", "Plan de remédiation",
                     "Suivi des recommandations antérieures", "Conclusion", "Annexes"],
    },
}

# Limites de tokens selon le mode (par appel IA — Claude Sonnet 4.6 cap pratique ~64k)
# Bumpés : un rapport "standard" 6 sections × ~3000 mots ≈ 24k tokens compressés ;
# avec chunking 3 sections/lot, chaque lot peut prendre 16k tokens confortablement.
_TOKENS_PAR_MODE = {
    "flash":    6000,
    "standard": 16000,   # par LOT (avec chunking actif) — total possible >40k
    "complet":  32000,   # par lot
    "expert":   48000,   # par lot
}

# Taille des lots pour la génération par chunks (modes longs).
# Chaque lot = un appel IA dédié → contourne le plafond de tokens par appel
# et permet vraiment d'atteindre le niveau de détail demandé.
# AVANT : standard=99 (1 seul appel pour 6 sections → compression forte, perte de détail).
# APRÈS : standard chunké aussi (3 sections/lot) pour pousser jusqu'au détail demandé.
_SECTIONS_PAR_LOT = {
    "flash":    99,    # pas de chunking — synthèse courte
    "standard": 3,     # ~2 lots pour 6 sections — chaque section dispose de tokens
    "complet":  3,     # ~4 lots pour 11 sections
    "expert":   2,     # lots très serrés → sections très denses
}


def _analyser_excel_pandas(contexte: str) -> str:
    """
    Analyse statistique approfondie des données tabulaires (Excel/CSV extraits).
    Génère un rapport d'analyse de niveau data analyst senior injecté dans le prompt.
    """
    try:
        import io
        import pandas as pd
        import re

        lignes = [l for l in contexte.split('\n') if '|' in l and len(l.strip()) > 5]
        if len(lignes) < 3:
            return contexte

        # Parser toutes les tables markdown présentes (multi-feuilles)
        blocs_tables = re.split(r'###\s*Feuille\s*:', contexte)
        all_stats = [
            f"\n{'═'*70}",
            "ANALYSE DATA ANALYST SENIOR — DONNÉES EXTRAITES DES FICHIERS",
            f"{'═'*70}\n",
        ]

        for bloc in blocs_tables:
            lignes_bloc = [l for l in bloc.split('\n') if '|' in l and len(l.strip()) > 5]
            if len(lignes_bloc) < 3:
                continue

            # Nom de la feuille si présent
            nom_feuille = bloc.split('\n')[0].strip().split('(')[0].strip() or "Données"

            try:
                data_str = "\n".join(l for l in lignes_bloc if not re.match(r'^\s*[-|]+\s*$', l))
                df = pd.read_csv(io.StringIO(data_str), sep='|', skipinitialspace=True)
                df = df.dropna(axis=1, how='all')
                df.columns = [c.strip() for c in df.columns if c.strip()]
                df = df.dropna(how='all').reset_index(drop=True)
                # Convertir colonnes numériques
                for col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(' ', '').str.replace(',', '.'), errors='ignore')
            except Exception:
                continue

            if df.empty or len(df.columns) == 0:
                continue

            num_cols = df.select_dtypes(include='number').columns.tolist()
            cat_cols = df.select_dtypes(exclude='number').columns.tolist()

            all_stats += [
                f"## {nom_feuille}",
                f"Dimensions : {len(df)} lignes × {len(df.columns)} colonnes",
                f"Colonnes numériques : {', '.join(num_cols) or 'aucune'}",
                f"Colonnes textuelles : {', '.join(cat_cols) or 'aucune'}",
                "",
            ]

            if num_cols:
                desc = df[num_cols].describe().round(2)
                all_stats.append("### Statistiques descriptives complètes :")
                all_stats.append(desc.to_string())
                all_stats.append("")

                # Totaux et agrégats métier
                totaux = {col: df[col].sum() for col in num_cols}
                all_stats.append("### Totaux et agrégats :")
                for col, tot in totaux.items():
                    mean = df[col].mean()
                    pct_var = ((df[col].iloc[-1] - df[col].iloc[0]) / abs(df[col].iloc[0]) * 100) if len(df) > 1 and df[col].iloc[0] != 0 else 0
                    all_stats.append(f"- **{col}** : Total = {tot:,.2f} | Moyenne = {mean:,.2f} | Variation 1ère→dernière ligne = {pct_var:+.1f}%")
                all_stats.append("")

                # Détection outliers (IQR)
                all_stats.append("### Détection des valeurs atypiques (méthode IQR) :")
                for col in num_cols[:6]:
                    Q1, Q3 = df[col].quantile(0.25), df[col].quantile(0.75)
                    IQR = Q3 - Q1
                    outliers = df[(df[col] < Q1 - 1.5 * IQR) | (df[col] > Q3 + 1.5 * IQR)]
                    if not outliers.empty:
                        all_stats.append(f"- **{col}** : {len(outliers)} valeur(s) atypique(s) détectée(s)")
                all_stats.append("")

                # Tendances temporelles si colonne date détectée
                date_cols = [c for c in df.columns if any(k in c.lower() for k in ['date', 'mois', 'année', 'annee', 'period', 'trimestre'])]
                if date_cols and num_cols:
                    all_stats.append(f"### Tendances temporelles (axe : {date_cols[0]}) :")
                    try:
                        gb = df.groupby(date_cols[0])[num_cols[:3]].sum().round(2)
                        all_stats.append(gb.to_string())
                    except Exception:
                        pass
                    all_stats.append("")

                # Corrélations
                if len(num_cols) >= 2:
                    corr = df[num_cols].corr().round(2)
                    all_stats.append("### Matrice de corrélations :")
                    all_stats.append(corr.to_string())
                    # Corrélations fortes
                    corr_fortes = []
                    for i in range(len(num_cols)):
                        for j in range(i+1, len(num_cols)):
                            v = corr.iloc[i, j]
                            if abs(v) >= 0.7:
                                signe = "positive forte" if v > 0 else "négative forte"
                                corr_fortes.append(f"  → {num_cols[i]} ↔ {num_cols[j]} : r={v:.2f} ({signe})")
                    if corr_fortes:
                        all_stats.append("Corrélations significatives (|r| ≥ 0.7) :")
                        all_stats.extend(corr_fortes)
                    all_stats.append("")

            if cat_cols:
                all_stats.append("### Distribution des variables catégorielles :")
                for col in cat_cols[:8]:
                    vc = df[col].value_counts()
                    top5 = vc.head(5)
                    total = vc.sum()
                    dist = ", ".join(f"{v}: {n} ({n/total*100:.1f}%)" for v, n in top5.items())
                    all_stats.append(f"- **{col}** ({vc.nunique()} valeurs uniques) : {dist}")
                all_stats.append("")

            # Valeurs manquantes
            missing = df.isnull().sum()
            if missing.any():
                all_stats.append("### Qualité des données — Valeurs manquantes :")
                for col, cnt in missing[missing > 0].items():
                    all_stats.append(f"- {col} : {cnt} manquantes ({cnt/len(df)*100:.1f}%)")
                all_stats.append("")

        all_stats.append(f"{'═'*70}\n")
        return "\n".join(all_stats) + "\n\nDONNÉES BRUTES COMPLÈTES :\n" + contexte

    except Exception:
        return contexte


# ══════════════════════════════════════════════════════════════════════════════
# Erreurs métier
# ══════════════════════════════════════════════════════════════════════════════

class SourcesInsuffisantesError(Exception):
    """
    Levée quand aucune source vérifiable (pièces jointes, RAG, recherche web)
    ne permet de rédiger un rapport factuel. L'API doit la convertir en message
    clair pour l'utilisateur lui demandant de fournir la documentation.
    """
    def __init__(self, raison: str, sources_essayees: Optional[list[str]] = None):
        super().__init__(raison)
        self.raison = raison
        self.sources_essayees = sources_essayees or []


# ══════════════════════════════════════════════════════════════════════════════
# Classe principale
# ══════════════════════════════════════════════════════════════════════════════

class ReportWriterPro:
    """Générateur de rapports professionnels avec IA + python-docx."""

    def __init__(self, profil=None):
        self._profil = profil

    async def generer(
        self,
        sujet:                 str,
        type_rapport:          str = "rapport_analyse",
        mode:                  str = "standard",
        contexte:              Optional[str] = None,
        donnees:               Optional[dict] = None,
        langue:                str = "fr",
        format_sortie:         str = "docx",   # "docx" | "markdown"
        instruction_utilisateur: Optional[str] = None,
        forcer_recherche_web:  bool = False,
    ) -> dict:
        """
        Génère un rapport professionnel.

        Args:
            sujet:         Sujet principal du rapport
            type_rapport:  Type de rapport (voir _STRUCTURES)
            mode:          "flash" | "standard" | "complet"
            contexte:      Contexte supplémentaire à fournir à l'IA
            donnees:       Données à intégrer (tableaux, chiffres…)
            langue:        Langue du rapport ("fr" par défaut)
            format_sortie: "docx" | "markdown"

        Returns:
            dict avec : chemin_fichier, nom_fichier, contenu_markdown,
                        nb_sections, mode, type_rapport
        """
        if type_rapport not in _STRUCTURES:
            type_rapport = "rapport_analyse"
        if mode not in ("flash", "standard", "complet", "expert"):
            mode = "standard"

        # Le mode expert utilise la structure "complet" étendue
        structure_mode = "complet" if mode == "expert" else mode
        structure_brute = _STRUCTURES[type_rapport][structure_mode]

        # Sections meta non-LLM : "Page de garde" est dessinée nativement par
        # _construire_docx ; "Sommaire" devrait être un champ TOC Word, pas
        # une section narrative. On les retire AVANT l'appel LLM pour éviter
        # qu'elles n'apparaissent comme "1. Page de garde" / "2. Sommaire"
        # dans le corps du document.
        _SECTIONS_META = {"page de garde", "sommaire", "table des matières", "table des matieres"}
        structure = [s for s in structure_brute if s.strip().lower() not in _SECTIONS_META]
        if not structure:  # garde-fou
            structure = structure_brute

        # 1. Générer le contenu via IA
        contenu_sections = await self._generer_contenu_ia(
            sujet=sujet,
            type_rapport=type_rapport,
            mode=mode,
            structure=structure,
            contexte=contexte,
            donnees=donnees,
            langue=langue,
            instruction_utilisateur=instruction_utilisateur,
            forcer_recherche_web=forcer_recherche_web,
        )

        # 2. Construire le document
        nom_fichier = self._nom_fichier(sujet, type_rapport, mode)

        if format_sortie == "docx":
            chemin = await self._construire_docx(
                nom_fichier=nom_fichier,
                sujet=sujet,
                type_rapport=type_rapport,
                mode=mode,
                sections=contenu_sections,
            )
            chemin_str = str(chemin)
        else:
            chemin_str = None

        # Markdown toujours généré (fallback + aperçu)
        contenu_md = self._sections_vers_markdown(sujet, contenu_sections)

        # 3. Incrémenter stats
        if self._profil:
            try:
                from core.database import async_session_maker
                from modules.pro.service_profil import incrementer_stat
                async with async_session_maker() as db:
                    await incrementer_stat(self._profil.user_id, "nb_rapports", db, xp_gain=5)
            except Exception:
                pass

        return {
            "chemin_fichier":  chemin_str,
            "nom_fichier":     nom_fichier + (".docx" if format_sortie == "docx" else ".md"),
            "contenu_markdown": contenu_md,
            "nb_sections":     len(contenu_sections),
            "mode":            mode,
            "type_rapport":    type_rapport,
            "sujet":           sujet,
            "genere_le":       datetime.utcnow().isoformat(),
        }

    # ── Génération IA du contenu ───────────────────────────────────────────────

    async def _generer_contenu_ia(
        self,
        sujet:        str,
        type_rapport: str,
        mode:         str,
        structure:    list[str],
        contexte:     Optional[str],
        donnees:      Optional[dict],
        langue:       str,
        instruction_utilisateur: Optional[str] = None,
        forcer_recherche_web:    bool = False,
    ) -> list[dict]:
        """
        Appelle l'IA pour générer le contenu de chaque section.
        Retourne une liste de dicts : {"titre": ..., "contenu": ...}
        """
        from core.ia_client import ModeIA, ia_client
        from core.pays_devise import vocabulaire_devise

        # Construire le système prompt
        metier_info = ""
        pays_info   = ""
        if self._profil:
            metier_info = f"Métier du demandeur : {self._profil.metier}"
            pays_info   = f"Pays : {self._profil.pays}"
        devise_locale = vocabulaire_devise(self._profil.pays if self._profil else None)

        system = (
            "Tu es un expert senior polyvalent en Afrique francophone : rédacteur de rapports professionnels, "
            "analyste financier, data analyst, juriste d'entreprise et consultant en stratégie, "
            "avec 25 ans d'expérience au service de multinationales, cabinets d'audit Big4, "
            "bailleurs de fonds (Banque Mondiale, AFD, BAD) et conseils d'administration. "
            "Tu maîtrises : droit OHADA/UEMOA/CEMAC, fiscalité africaine (CGI, TVA, IRPP, IS, TSE), "
            "comptabilité SYSCOHADA révisé 2017, finance d'entreprise, analyse de données avancée, "
            "management RH, gestion de projet, marchés africains. "
            f"{metier_info} {pays_info}\n\n"
            "🚫 RÈGLE NUMÉRO 1 — INTERDICTION ABSOLUE D'INVENTER OU DE MOBILISER TA MÉMOIRE :\n"
            "• Tu n'as PAS le droit d'utiliser tes connaissances d'entraînement comme source de chiffres.\n"
            "• Toute donnée chiffrée, tout taux, tout montant, toute citation réglementaire DOIT venir "
            "explicitement des SOURCES FOURNIES dans le contexte du prompt utilisateur "
            "(pièces jointes, RAG corpus, sources web vérifiées avec URL).\n"
            "• Si une donnée nécessaire n'est PAS dans les sources fournies, tu écris textuellement : "
            "« Donnée non disponible dans les sources fournies — à collecter auprès de [organisme précis] » "
            "et tu poursuis. Tu ne combles JAMAIS un trou par estimation, extrapolation ou souvenir.\n"
            "• Aucun placeholder type X%, Y FCFA, A1, B1, [chiffre], [montant], [date] n'est toléré.\n"
            "• Chaque chiffre cité doit être suivi de sa source entre parenthèses : "
            "(Source : nom_institution / URL / nom_du_fichier_joint).\n\n"
            "RÈGLES DE RÉDACTION :\n"
            "1. EXPLOITATION TOTALE DES SOURCES : analyser ligne par ligne tableaux/extraits fournis, "
            "extraire TOUS les chiffres réels, calculer ratios, tendances, anomalies, corrélations.\n"
            "2. Contenu DENSE, LONG et PROFESSIONNEL — chaque section exhaustive, sous-sections, "
            "tableaux récapitulatifs, analyses croisées. Pousse jusqu'au niveau de détail demandé "
            "par l'utilisateur, ne synthétise PAS prématurément.\n"
            "3. TABLEAUX OBLIGATOIRES : inclure dans chaque section pertinente (format markdown). "
            "Chaque cellule chiffrée doit être traçable à une source du contexte.\n"
            "4. Cite les textes réglementaires EXACTS (article précis, alinéa, année de révision) "
            "uniquement s'ils figurent dans les sources fournies.\n"
            "5. Calculs financiers (ROE, ROA, BFR, marges…) UNIQUEMENT sur données réelles fournies, "
            "avec formule explicite et chiffres source.\n"
            "6. Recommandations ACTIONNABLES avec responsables, délais, KPIs.\n"
            f"7. Devise locale obligatoire pour les montants : {devise_locale}.\n"
            "   Vocabulaire africain : BEAC/BCEAO, CEMAC/UEMOA, CNSS/CNPS/CNAMGS, SYSCOHADA.\n"
            "8. Style cabinet Big4/McKinsey/Deloitte : synthèse percutante, pyramidale, insights "
            "non-évidents, regard critique étayé par les sources."
        )

        # Enrichir le contexte Excel avec une analyse statistique approfondie
        contexte_enrichi = contexte
        if contexte and ("===" in contexte or " | " in contexte or "Feuille :" in contexte):
            contexte_enrichi = _analyser_excel_pandas(contexte)

        # ── Enrichissement RAG automatique pour rapports techniques ──────────
        # Sans pièce jointe, le LLM n'a aucune donnée à exploiter et produit des
        # placeholders (X%, A1, B1...). On injecte le corpus réglementaire/stats.
        _TYPES_RAG = {
            "rapport_financier", "rapport_audit", "rapport_rh",
            "note_juridique", "note_de_synthese", "rapport_analyse",
        }
        if type_rapport in _TYPES_RAG:
            try:
                from modules.rag.rag_retriever import (
                    rechercher_pour_metier, rechercher_corpus_reglementaire,
                )
                pays_profil = self._profil.pays if self._profil else None
                metier_profil = self._profil.metier if self._profil else None
                requete_rag = (instruction_utilisateur or sujet or "").strip()
                contexte_rag = ""
                if requete_rag:
                    if metier_profil:
                        contexte_rag = rechercher_pour_metier(
                            question=requete_rag,
                            metier=metier_profil,
                            pays=pays_profil,
                            top_k=10,
                        )
                    else:
                        contexte_rag = rechercher_corpus_reglementaire(
                            question=requete_rag,
                            pays=pays_profil,
                            top_k=10,
                        )
                if contexte_rag:
                    bloc_rag = (
                        f"\n\n{'═'*60}\n"
                        f"DONNÉES RÉGLEMENTAIRES & STATISTIQUES OFFICIELLES "
                        f"(corpus indexé — citer textuellement) :\n"
                        f"{'═'*60}\n{contexte_rag}"
                    )
                    contexte_enrichi = (contexte_enrichi or "") + bloc_rag
                    logger.info(
                        f"[ReportWriter] RAG injecté ({len(contexte_rag)} chars) "
                        f"pour {type_rapport} pays={pays_profil}"
                    )
                else:
                    logger.warning(
                        f"[ReportWriter] RAG vide pour {type_rapport} "
                        f"(question={requete_rag[:80]!r}, pays={pays_profil})"
                    )
            except Exception as e:
                logger.warning(f"[ReportWriter] Enrichissement RAG échoué: {e}")

        # ── Recherche web réelle (sources fiables) ───────────────────────────
        # Déclenchée si :
        #   - forcer_recherche_web=True (régénération suite à plainte utilisateur), OU
        #   - rapport technique sans pièce jointe ni RAG exploitable.
        # Si AUCUNE source fiable n'est trouvée → on refuse de générer (lève
        # SourcesInsuffisantesError) plutôt que de laisser le LLM inventer.
        sources_urls_web: list[str] = []
        _besoin_web = type_rapport in _TYPES_RAG and (
            forcer_recherche_web
            or not (contexte_enrichi and len(contexte_enrichi) > 500)
        )
        if _besoin_web:
            try:
                from modules.pro.recherche_web_pro import rechercher_sources_pour_rapport
                pays_profil = self._profil.pays if self._profil else None
                requete_web = (instruction_utilisateur or sujet or "").strip()
                resultat_web = await rechercher_sources_pour_rapport(
                    sujet=requete_web,
                    type_rapport=type_rapport,
                    pays_iso2=pays_profil,
                    nb_sources_min=3,
                    timeout_total=50.0,
                )
                if resultat_web.contexte_formate:
                    bloc_web = (
                        f"\n\n{'═'*60}\n"
                        f"SOURCES WEB VÉRIFIÉES "
                        f"({resultat_web.nb_sources} sources institutionnelles/IFI/régulateurs — "
                        f"À CITER explicitement avec leur URL) :\n"
                        f"{'═'*60}\n{resultat_web.contexte_formate}"
                    )
                    contexte_enrichi = (contexte_enrichi or "") + bloc_web
                    sources_urls_web = resultat_web.sources_urls
                    logger.info(
                        f"[ReportWriter] Web injecté: {resultat_web.nb_sources} sources, "
                        f"{len(resultat_web.contexte_formate)} chars"
                    )
                elif forcer_recherche_web or not contexte_enrichi:
                    # Aucune source trouvée et pas de fallback → REFUS
                    raise SourcesInsuffisantesError(
                        raison=(
                            resultat_web.raison_echec
                            or "Aucune source fiable trouvée pour ce sujet."
                        ),
                        sources_essayees=resultat_web.sources_urls,
                    )
            except SourcesInsuffisantesError:
                raise
            except Exception as e:
                logger.warning(f"[ReportWriter] Recherche web échouée: {e}")
                if forcer_recherche_web and not contexte_enrichi:
                    raise SourcesInsuffisantesError(
                        raison=f"Recherche web indisponible : {e}",
                    )

        # ── Garde-fou final : pas de données du tout ⇒ refus ─────────────────
        # Pour un rapport technique, refuser d'inventer si rien n'est exploitable.
        if type_rapport in _TYPES_RAG and not contexte_enrichi:
            raise SourcesInsuffisantesError(
                raison=(
                    "Aucune source vérifiable disponible pour ce rapport "
                    "(pas de pièces jointes, pas de correspondance dans le corpus "
                    "réglementaire local, pas de résultat sur les sites web fiables). "
                    "Veuillez fournir un document source (rapport annuel, données "
                    "comptables, état CIMA, etc.) pour permettre une rédaction factuelle."
                ),
            )

        # Construire le prompt utilisateur
        sections_str = "\n".join(f"{i+1}. **{s}**" for i, s in enumerate(structure))
        donnees_str  = f"\n\nDONNÉES À INTÉGRER :\n{donnees}" if donnees else ""

        # Passer TOUT le contexte sans limite artificielle (Claude 200K tokens)
        contexte_str = f"\n\n{'═'*60}\nCONTEXTE ET DONNÉES SOURCE (À EXPLOITER INTÉGRALEMENT) :\n{'═'*60}\n{contexte_enrichi}" if contexte_enrichi else ""

        nbre_mots = {
            "flash":    "600-1200 mots, synthèse dense",
            "standard": "2000-4000 mots par section avec tableaux",
            "complet":  "4000-8000 mots par section, sous-sections détaillées, tableaux et analyses croisées",
            "expert":   "8000-15000 mots par section, niveau thèse de doctorat professionnel, exhaustif",
        }[mode]

        a_des_donnees = bool(contexte_enrichi)
        instructions_donnees = (
            "\n\n⚠️ DONNÉES RÉELLES FOURNIES — OBLIGATIONS STRICTES :\n"
            "• Reprendre TOUS les chiffres réels des fichiers dans le rapport (ne rien omettre)\n"
            "• Créer des tableaux de synthèse avec les données réelles (format markdown)\n"
            "• Calculer les ratios, variations, moyennes, totaux à partir de ces données\n"
            "• Identifier et commenter les tendances, anomalies, points d'attention\n"
            "• Baser chaque recommandation sur les données concrètes fournies\n"
            "• Si plusieurs feuilles Excel : analyser et croiser les données inter-feuilles\n"
        ) if a_des_donnees else ""

        # ── Génération par lots pour modes longs (contournement plafond tokens) ──
        import asyncio
        import json

        taille_lot = _SECTIONS_PAR_LOT.get(mode, 99)
        lots: list[list[str]] = [
            structure[i:i + taille_lot] for i in range(0, len(structure), taille_lot)
        ] if taille_lot < len(structure) else [structure]

        instruction_brute = (instruction_utilisateur or sujet).strip()
        a_du_rag_ou_donnees = bool(contexte_enrichi)
        regle_anti_placeholder = (
            "\n\n🚫 INTERDICTION ABSOLUE D'UTILISER DES PLACEHOLDERS :\n"
            "• Ne JAMAIS écrire X%, Y FCFA, A1, B1, G1, H1, [chiffre], [montant], [à compléter], etc.\n"
            "• Tous les chiffres DOIVENT venir soit du contexte fourni (pièces jointes/RAG), "
            "soit de connaissances réglementaires officielles vérifiables (ex: SMIG CIMA, taux IS, plafonds CNPS).\n"
            "• Si une donnée précise n'est PAS disponible dans le contexte ni dans tes connaissances "
            "officielles : écris explicitement 'Donnée non disponible dans les sources fournies — "
            "à collecter auprès de [source recommandée]' au lieu d'inventer un placeholder.\n"
            "• Préfère un rapport plus court avec des données réelles à un rapport long avec des trous."
        ) if a_du_rag_ou_donnees else (
            "\n\n⚠️ AUCUNE DONNÉE SOURCE FOURNIE — RÈGLE STRICTE :\n"
            "• Tu n'as ni pièces jointes ni RAG ciblé. Base-toi UNIQUEMENT sur tes connaissances "
            "officielles vérifiables (textes CIMA, OHADA, SYSCOHADA, codes nationaux, statistiques "
            "publiques notoires) et CITE les sources précises (article, année, organisme).\n"
            "• Pour tout chiffre que tu ne peux pas sourcer avec certitude, écris : "
            "'Donnée à collecter — non publique au moment de la rédaction'. "
            "JAMAIS de X, Y, A1, B1 ou autres placeholders.\n"
            "• Le rapport peut être plus court mais doit rester FACTUEL."
        )

        def _construire_prompt_lot(sous_structure: list[str], idx_lot: int, total_lots: int) -> str:
            sections_lot_str = "\n".join(
                f"{i+1}. **{s}**" for i, s in enumerate(sous_structure)
            )
            entete_lot = (
                f"⚙️ LOT {idx_lot + 1}/{total_lots} du rapport — "
                f"Génère UNIQUEMENT les {len(sous_structure)} sections ci-dessous. "
                f"Les autres lots seront concaténés.\n\n"
            ) if total_lots > 1 else ""
            return (
                f"{entete_lot}"
                f"Génère un rapport professionnel de type '{type_rapport}' "
                f"en mode '{mode}'.\n\n"
                f"{'═'*60}\n"
                f"TITRE DU DOCUMENT : {sujet}\n"
                f"DEMANDE EXACTE DE L'UTILISATEUR : {instruction_brute}\n"
                f"{'═'*60}\n\n"
                f"SECTIONS DE CE LOT ({len(sous_structure)} sections) :\n{sections_lot_str}"
                f"{contexte_str}{donnees_str}"
                f"{instructions_donnees}{regle_anti_placeholder}\n\n"
                f"EXIGENCES DE CONTENU :\n"
                f"• Chaque section : {nbre_mots}\n"
                f"• Langue : {langue}\n"
                f"• Niveau : document de référence signable par un directeur ou DG\n"
                f"• Inclure dans chaque section : analyse, tableaux, chiffres, références réglementaires\n"
                f"• Terminer la dernière section par des recommandations hiérarchisées (priorité 1/2/3) avec KPIs\n"
                f"• Format professionnel : titres clairs, listes à puces, tableaux markdown\n\n"
                f"FORMAT DE RÉPONSE — JSON strict :\n"
                f'{{"sections": [{{"titre": "Nom exact de section", "contenu": "Contenu complet et détaillé..."}}]}}\n'
                f"OBLIGATOIRE : inclure LES {len(sous_structure)} sections de CE LOT dans l'ordre exact. "
                f"Chaque section doit être COMPLÈTE et AUTONOME."
            )

        async def _generer_un_lot(sous_structure: list[str], idx: int, total: int) -> list[dict]:
            reponse = await ia_client.appeler(
                prompt=_construire_prompt_lot(sous_structure, idx, total),
                systeme=system,
                mode=ModeIA.REDACTION,  # Claude Sonnet 4.6 primaire, GPT-4o fallback
                max_tokens_override=_TOKENS_PAR_MODE[mode],
                json_attendu=True,
                utiliser_cache=False,
            )
            return self._parser_sections_json(reponse.contenu, sous_structure)

        if len(lots) == 1:
            return await _generer_un_lot(lots[0], 0, 1)

        # Parallélisation des lots : gain de latence net, chaque lot ~15-30s
        resultats = await asyncio.gather(
            *[_generer_un_lot(lot, i, len(lots)) for i, lot in enumerate(lots)],
            return_exceptions=True,
        )

        sections: list[dict] = []
        for i, res in enumerate(resultats):
            if isinstance(res, Exception):
                logger.warning(f"[ReportWriter] Lot {i+1} échoué : {res} → sections placeholder")
                sections.extend({"titre": t, "contenu": f"[Lot {i+1} indisponible]"} for t in lots[i])
            else:
                sections.extend(res)
        return sections

    def _parser_sections_json(self, texte: str, structure: list[str]) -> list[dict]:
        """Parse la réponse IA en sections structurées (robuste)."""
        import json
        import re

        # Tentative JSON
        try:
            # Chercher le JSON dans la réponse (peut y avoir du texte avant/après)
            match = re.search(r'\{[\s\S]*"sections"[\s\S]*\}', texte)
            if match:
                data = json.loads(match.group())
                sections = data.get("sections", [])
                if sections and isinstance(sections, list):
                    return [
                        {"titre": s.get("titre", "Section"), "contenu": s.get("contenu", "")}
                        for s in sections
                    ]
        except Exception:
            pass

        # Fallback : découper par les titres de la structure
        sections = []
        for titre in structure:
            # Chercher le contenu après chaque titre
            pattern = re.escape(titre) + r"[:\s\n]+(.*?)(?=" + "|".join(
                re.escape(t) for t in structure if t != titre
            ) + r"|$)"
            match = re.search(pattern, texte, re.DOTALL | re.IGNORECASE)
            contenu = match.group(1).strip() if match else f"[Contenu {titre} à renseigner]"
            sections.append({"titre": titre, "contenu": contenu})

        # Fallback final : retourner le texte brut en une section
        if not sections:
            sections = [{"titre": "Rapport", "contenu": texte}]

        return sections

    # ── Construction DOCX ──────────────────────────────────────────────────────

    async def _construire_docx(
        self,
        nom_fichier:  str,
        sujet:        str,
        type_rapport: str,
        mode:         str,
        sections:     list[dict],
    ) -> Path:
        """Construit le fichier DOCX avec python-docx."""
        try:
            from docx import Document
            from docx.shared import Pt, RGBColor, Cm, Inches
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn
        except ImportError:
            # python-docx non disponible — retourner le markdown sauvegardé
            logger.warning("[ReportWriter] python-docx non disponible — génération Markdown uniquement")
            chemin = _OUTPUT_DIR / (nom_fichier + ".md")
            return chemin

        doc = Document()

        # ── Styles de page ────────────────────────────────────────────────
        sections_doc = doc.sections
        for section in sections_doc:
            section.top_margin    = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin   = Cm(3)
            section.right_margin  = Cm(2.5)

        # Compteurs pour numérotation automatique
        _compteur_tableau = [0]
        _compteur_figure  = [0]

        # ── Page de garde ─────────────────────────────────────────────────
        # Logo / en-tête (texte si pas d'image)
        p_header = doc.add_paragraph()
        p_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_header.add_run("RAPPORT PROFESSIONNEL")
        run.bold  = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x00, 0x47, 0xAB)

        doc.add_paragraph()

        # Titre principal
        p_titre = doc.add_paragraph()
        p_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_titre = p_titre.add_run(sujet.upper())
        run_titre.bold = True
        run_titre.font.size = Pt(18)
        run_titre.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)

        doc.add_paragraph()

        # Sous-titre type + mode
        labels = {
            "rapport_analyse":   "Rapport d'analyse",
            "note_de_synthese":  "Note de synthèse",
            "note_juridique":    "Note juridique",
            "rapport_financier": "Rapport financier",
            "rapport_rh":        "Rapport RH",
            "plan_action":       "Plan d'action",
            "compte_rendu":      "Compte-rendu",
            "rapport_audit":     "Rapport d'audit",
        }
        label = labels.get(type_rapport, type_rapport.replace("_", " ").title())
        modes_label = {"flash": "Note express", "standard": "Version standard", "complet": "Version complète", "expert": "Version expert"}

        p_sous = doc.add_paragraph()
        p_sous.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_sous = p_sous.add_run(f"{label}  •  {modes_label.get(mode, mode)}")
        run_sous.font.size = Pt(12)
        run_sous.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        doc.add_paragraph()

        # Métadonnées profil
        if self._profil:
            p_meta = doc.add_paragraph()
            p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
            meta = f"Rédigé par : {self._profil.metier.title()}"
            if self._profil.entreprise:
                meta += f"  •  {self._profil.entreprise}"
            run_meta = p_meta.add_run(meta)
            run_meta.font.size = Pt(10)
            run_meta.italic = True

        # Date
        p_date = doc.add_paragraph()
        p_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_date = p_date.add_run(datetime.now().strftime("%d %B %Y"))
        run_date.font.size = Pt(10)
        run_date.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        doc.add_page_break()

        # ── Corps du rapport (rendu ligne par ligne, robuste) ─────────────
        import re as _re

        def _rendu_contenu(doc, texte: str):
            """Convertit du Markdown en DOCX ligne par ligne."""
            lignes = texte.split("\n")
            i = 0
            while i < len(lignes):
                ligne = lignes[i]
                s = ligne.strip()
                if not s:
                    i += 1
                    continue

                # ── Titres de section ───────────────────────────────────
                if s.startswith("#### "):
                    h = doc.add_heading(s[5:].strip(), level=3)
                    if h.runs: h.runs[0].font.size = Pt(11)
                    i += 1; continue
                if s.startswith("### "):
                    h = doc.add_heading(s[4:].strip(), level=2)
                    if h.runs:
                        h.runs[0].font.color.rgb = RGBColor(0x22, 0x5A, 0x8A)
                        h.runs[0].font.size = Pt(12)
                    i += 1; continue
                if s.startswith("## "):
                    h = doc.add_heading(s[3:].strip(), level=2)
                    if h.runs:
                        h.runs[0].font.color.rgb = RGBColor(0x00, 0x47, 0xAB)
                        h.runs[0].font.size = Pt(13)
                    i += 1; continue
                if s.startswith("# "):
                    h = doc.add_heading(s[2:].strip(), level=1)
                    if h.runs:
                        h.runs[0].font.color.rgb = RGBColor(0x00, 0x47, 0xAB)
                        h.runs[0].font.size = Pt(14)
                    i += 1; continue

                # ── Séparateur horizontal ───────────────────────────────
                if _re.match(r'^[-*_]{3,}$', s):
                    doc.add_paragraph()
                    i += 1; continue

                # ── Tableau Markdown ────────────────────────────────────
                if '|' in s:
                    # Collecter toutes les lignes du tableau
                    tbl_lignes = []
                    while i < len(lignes) and '|' in lignes[i]:
                        tbl_lignes.append(lignes[i])
                        i += 1
                    # Filtrer la ligne de séparateur (---)
                    rows = [l for l in tbl_lignes if not _re.match(r'^\|[\s\-:|\s]+\|$', l.strip())]
                    if len(rows) >= 2:
                        cols = [c.strip() for c in rows[0].split('|') if c.strip()]
                        if cols:
                            _compteur_tableau[0] += 1
                            tbl = doc.add_table(rows=len(rows), cols=len(cols))
                            tbl.style = 'Table Grid'
                            for ri, row_line in enumerate(rows):
                                cells = [c.strip() for c in row_line.split('|') if c.strip()]
                                for ci in range(len(cols)):
                                    val = cells[ci].strip('*') if ci < len(cells) else ""
                                    cell = tbl.cell(ri, ci)
                                    cell.text = val
                                    if cell.paragraphs[0].runs:
                                        run = cell.paragraphs[0].runs[0]
                                        run.font.size = Pt(10)
                                        if ri == 0:
                                            run.bold = True
                                            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                                            cell.paragraphs[0].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
                                    if ri == 0:
                                        from docx.oxml.ns import qn as _qn
                                        from docx.oxml import OxmlElement as _OxmlElement
                                        tc = cell._tc
                                        tcPr = tc.get_or_add_tcPr()
                                        shd = _OxmlElement('w:shd')
                                        shd.set(_qn('w:val'), 'clear')
                                        shd.set(_qn('w:color'), 'auto')
                                        shd.set(_qn('w:fill'), '0047AB')
                                        tcPr.append(shd)
                            doc.add_paragraph()
                    continue

                # ── Bullet sous-indentés (  - ou    •) ──────────────────
                if _re.match(r'^\s{2,}[-•*]\s', ligne):
                    txt = _re.sub(r'^\s+[-•*]\s+', '', ligne).strip()
                    try: p_obj = doc.add_paragraph(style="List Bullet 2")
                    except: p_obj = doc.add_paragraph()
                    _ajouter_inline(p_obj, txt, Pt(10))
                    i += 1; continue

                # ── Listes à puces ───────────────────────────────────────
                if _re.match(r'^[-•*►▶→]\s', s):
                    txt = _re.sub(r'^[-•*►▶→]\s+', '', s).strip()
                    try: p_obj = doc.add_paragraph(style="List Bullet")
                    except: p_obj = doc.add_paragraph()
                    _ajouter_inline(p_obj, txt, Pt(11))
                    i += 1; continue

                # ── Listes numérotées ────────────────────────────────────
                if _re.match(r'^\d+[.)]\s', s):
                    txt = _re.sub(r'^\d+[.)]\s+', '', s).strip()
                    try: p_obj = doc.add_paragraph(style="List Number")
                    except: p_obj = doc.add_paragraph()
                    _ajouter_inline(p_obj, txt, Pt(11))
                    i += 1; continue

                # ── Sous-titre gras seul (ligne entière en **gras**) ─────
                m_bold_title = _re.match(r'^\*\*(.+)\*\*$', s)
                if m_bold_title:
                    p_obj = doc.add_paragraph()
                    run = p_obj.add_run(m_bold_title.group(1))
                    run.bold = True
                    run.font.size = Pt(12)
                    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
                    i += 1; continue

                # ── Paragraphe normal avec gras/italic inline ────────────
                # Accumuler les lignes consécutives en un paragraphe
                para_lines = [s]
                j = i + 1
                while j < len(lignes):
                    ns = lignes[j].strip()
                    if (not ns or ns.startswith(("#", "-", "*", "•", "|", "►", "▶", "→"))
                            or _re.match(r'^\d+[.)]\s', ns)
                            or _re.match(r'^[-*_]{3,}$', ns)):
                        break
                    para_lines.append(ns)
                    j += 1
                para_text = " ".join(para_lines)
                p_obj = doc.add_paragraph()
                _ajouter_inline(p_obj, para_text, Pt(11))
                i = j
                continue

        def _ajouter_inline(paragraphe, texte: str, taille=None):
            """Rendu inline : **gras**, *italique*, texte normal."""
            parties = _re.split(r'(\*\*(?:[^*]|\*(?!\*))+\*\*|\*[^*]+\*)', texte)
            for partie in parties:
                if partie.startswith('**') and partie.endswith('**') and len(partie) > 4:
                    run = paragraphe.add_run(partie[2:-2])
                    run.bold = True
                elif partie.startswith('*') and partie.endswith('*') and len(partie) > 2:
                    run = paragraphe.add_run(partie[1:-1])
                    run.italic = True
                elif partie:
                    run = paragraphe.add_run(partie)
                else:
                    continue
                if taille:
                    run.font.size = taille

        for i, section in enumerate(sections):
            titre   = section.get("titre", f"Section {i+1}")
            contenu = section.get("contenu", "")

            # Titre de section principal
            heading = doc.add_heading(f"{i+1}. {titre}", level=1)
            if heading.runs:
                heading.runs[0].font.color.rgb = RGBColor(0x00, 0x47, 0xAB)
                heading.runs[0].font.size = Pt(14)

            if contenu:
                _rendu_contenu(doc, contenu)

            doc.add_paragraph()

        # ── En-tête et pied de page avec pagination ───────────────────────
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn as _qn

        footer_section = doc.sections[0]

        # En-tête : titre du rapport + confidentiel
        header = footer_section.header
        p_header_doc = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        p_header_doc.clear()
        p_header_doc.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run_hdr = p_header_doc.add_run(f"{sujet[:60]}  •  Confidentiel")
        run_hdr.font.size = Pt(8)
        run_hdr.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        run_hdr.italic = True

        # Pied de page : texte gauche + numéro de page centré
        footer = footer_section.footer
        p_footer = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        p_footer.clear()
        p_footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

        run_footer_left = p_footer.add_run(
            f"Yukpo Pro  •  {datetime.now().strftime('%d/%m/%Y')}     "
        )
        run_footer_left.font.size = Pt(8)
        run_footer_left.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        # Numéro de page automatique via champ XML
        def _ajouter_num_page(paragraph):
            run_pg = paragraph.add_run()
            fldChar1 = OxmlElement('w:fldChar')
            fldChar1.set(_qn('w:fldCharType'), 'begin')
            instrText = OxmlElement('w:instrText')
            instrText.set(_qn('xml:space'), 'preserve')
            instrText.text = ' PAGE '
            fldChar2 = OxmlElement('w:fldChar')
            fldChar2.set(_qn('w:fldCharType'), 'end')
            run_pg._r.append(fldChar1)
            run_pg._r.append(instrText)
            run_pg._r.append(fldChar2)
            run_pg.font.size = Pt(8)
            run_pg.font.color.rgb = RGBColor(0x00, 0x47, 0xAB)

        _ajouter_num_page(p_footer)
        run_sep = p_footer.add_run(" / ")
        run_sep.font.size = Pt(8)
        run_sep.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        def _ajouter_nb_pages(paragraph):
            run_pg = paragraph.add_run()
            fldChar1 = OxmlElement('w:fldChar')
            fldChar1.set(_qn('w:fldCharType'), 'begin')
            instrText = OxmlElement('w:instrText')
            instrText.set(_qn('xml:space'), 'preserve')
            instrText.text = ' NUMPAGES '
            fldChar2 = OxmlElement('w:fldChar')
            fldChar2.set(_qn('w:fldCharType'), 'end')
            run_pg._r.append(fldChar1)
            run_pg._r.append(instrText)
            run_pg._r.append(fldChar2)
            run_pg.font.size = Pt(8)
            run_pg.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        _ajouter_nb_pages(p_footer)

        # Sauvegarder
        chemin = _OUTPUT_DIR / (nom_fichier + ".docx")
        doc.save(str(chemin))
        logger.info(f"[ReportWriter] DOCX généré : {chemin}")
        return chemin

    # ── Helpers DOCX ──────────────────────────────────────────────────────────

    @staticmethod
    def _ajouter_tableau_docx(doc, texte_table: str):
        """Convertit un tableau markdown en tableau DOCX formaté."""
        try:
            from docx.shared import Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            lignes = [l.strip() for l in texte_table.split('\n') if '|' in l]
            lignes = [l for l in lignes if not all(c in '-|: ' for c in l)]
            if len(lignes) < 2:
                doc.add_paragraph(texte_table)
                return
            cols = [c.strip() for c in lignes[0].split('|') if c.strip()]
            if not cols:
                return
            table = doc.add_table(rows=len(lignes), cols=len(cols))
            table.style = 'Table Grid'
            for row_idx, ligne in enumerate(lignes):
                cellules = [c.strip() for c in ligne.split('|') if c.strip()]
                row = table.rows[row_idx]
                for col_idx, val in enumerate(cellules[:len(cols)]):
                    cell = row.cells[col_idx]
                    cell.text = val.strip('*')
                    run = cell.paragraphs[0].runs
                    if run:
                        run[0].font.size = Pt(10)
                        if row_idx == 0:
                            run[0].bold = True
                            run[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                            cell.paragraphs[0].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    # En-tête : fond bleu
                    if row_idx == 0:
                        from docx.oxml.ns import qn
                        from docx.oxml import OxmlElement
                        tc = cell._tc
                        tcPr = tc.get_or_add_tcPr()
                        shd = OxmlElement('w:shd')
                        shd.set(qn('w:val'), 'clear')
                        shd.set(qn('w:color'), 'auto')
                        shd.set(qn('w:fill'), '0047AB')
                        tcPr.append(shd)
            doc.add_paragraph()
        except Exception:
            doc.add_paragraph(texte_table)

    @staticmethod
    def _ajouter_texte_inline(paragraphe, texte: str):
        """Ajoute du texte avec gras/italique inline (**gras**, *italique*)."""
        import re
        parties = re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*)', texte)
        for partie in parties:
            if partie.startswith('**') and partie.endswith('**'):
                run = paragraphe.add_run(partie[2:-2])
                run.bold = True
            elif partie.startswith('*') and partie.endswith('*'):
                run = paragraphe.add_run(partie[1:-1])
                run.italic = True
            elif partie:
                paragraphe.add_run(partie)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _nom_fichier(sujet: str, type_rapport: str, mode: str) -> str:
        """Génère un nom de fichier propre depuis le sujet."""
        import re
        slug = re.sub(r"[^\w\s-]", "", sujet.lower())
        slug = re.sub(r"[\s_-]+", "_", slug)[:40]
        ts   = datetime.now().strftime("%Y%m%d_%H%M")
        return f"{type_rapport}_{mode}_{slug}_{ts}"

    @staticmethod
    def _sections_vers_markdown(sujet: str, sections: list[dict]) -> str:
        """Convertit les sections en Markdown."""
        lignes = [f"# {sujet}\n"]
        lignes.append(f"*Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}*\n")
        for i, section in enumerate(sections):
            lignes.append(f"\n## {i+1}. {section['titre']}\n")
            lignes.append(section.get("contenu", ""))
        return "\n".join(lignes)
