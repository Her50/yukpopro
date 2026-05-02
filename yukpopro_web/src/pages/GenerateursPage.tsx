import { useState, FormEvent, useRef, DragEvent, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileText, Presentation, Download, CheckCircle, Loader, BookOpen, ArrowRight, Upload, X, FolderOpen, RefreshCw, Palette, Sparkles, Image as ImageIcon, Save, ChevronDown, Wand2, Settings2, FileImage, Maximize2 } from "lucide-react";
import toast from "react-hot-toast";
import ReactMarkdown from "react-markdown";
import { Card, Button, Textarea, Badge, Select } from "@/components/ui";
import { DemoBanner } from "@/components/DemoBanner";
import { generateurApi, infographieApi, GabaritInfographie, ResultatInfographieReponse } from "@/api/client";
import { useGenerateurStore } from "@/store/generateurStore";
import { formatAmount } from "@/services/paysDevise";
import DesignerProPanel from "@/components/DesignerProPanel";

type Tab = "rapport" | "slides" | "modeles" | "conversion" | "infographie" | "fichiers";
type InfogMode = "brief" | "manuel" | "modele" | "custom";

interface Template {
  key: string;
  label: string;
  description: string;
  type: "rapport" | "slides";
  typeDoc: string;
  mode: string;
  sujet: string;
  contexte: string;
}

interface CategorieTemplates {
  key: string;
  categorie: string;
  emoji: string;
  templates: Template[];
}

const TEMPLATES_PAR_METIER: CategorieTemplates[] = [
  {
    key: "comptabilite_finance",
    categorie: "Comptabilité & Finance",
    emoji: "🧮",
    templates: [
      {
        key: "bilan_syscohada",
        label: "Bilan SYSCOHADA commenté",
        description: "Bilan annuel avec analyse des ratios clés (liquidité, solvabilité, rentabilité)",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "complet",
        sujet: "Bilan comptable SYSCOHADA annoté avec analyse financière",
        contexte: "Préparer un bilan SYSCOHADA révisé avec ratios clés : liquidité générale, solvabilité, rentabilité des capitaux propres. Inclure tableau de flux de trésorerie et notes explicatives.",
      },
      {
        key: "note_is_tva",
        label: "Note de calcul IS + TVA",
        description: "Calcul détaillé de l'Impôt sur les Sociétés et de la TVA collectée/déductible",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "standard",
        sujet: "Note de calcul IS et TVA — exercice fiscal",
        contexte: "Calcul de l'IS selon le régime applicable (taux normal, minimum de perception) et réconciliation TVA (collectée, déductible, solde à décaisser). Référencer le CGI applicable.",
      },
      {
        key: "audit_interne",
        label: "Rapport d'audit interne",
        description: "Rapport d'audit des procédures comptables et points de contrôle interne",
        type: "rapport",
        typeDoc: "rapport_audit",
        mode: "complet",
        sujet: "Rapport d'audit interne des procédures comptables et financières",
        contexte: "Évaluation du contrôle interne, identification des risques (fraude, erreurs, non-conformités), recommandations correctives avec plan d'action priorisé.",
      },
      {
        key: "presentation_resultats",
        label: "Présentation résultats financiers",
        description: "Slides de présentation des résultats au comité de direction",
        type: "slides",
        typeDoc: "rapport_financier",
        mode: "executive",
        sujet: "Résultats financiers — présentation comité de direction",
        contexte: "KPIs financiers clés, évolution CA, marges, EBITDA, comparaison N-1, écarts vs budget, perspectives et actions correctives.",
      },
    ],
  },
  {
    key: "juridique_conformite",
    categorie: "Juridique & Conformité",
    emoji: "⚖️",
    templates: [
      {
        key: "note_juridique_ohada",
        label: "Note juridique OHADA",
        description: "Analyse d'une problématique juridique selon le droit OHADA",
        type: "rapport",
        typeDoc: "note_juridique",
        mode: "standard",
        sujet: "Note juridique — analyse de conformité OHADA",
        contexte: "Analyse des actes uniformes OHADA applicables, jurisprudence CCJA, risques juridiques identifiés et recommandations pratiques.",
      },
      {
        key: "due_diligence",
        label: "Rapport de due diligence",
        description: "Due diligence juridique et financière pour acquisition ou partenariat",
        type: "rapport",
        typeDoc: "rapport_audit",
        mode: "complet",
        sujet: "Rapport de due diligence — acquisition / partenariat stratégique",
        contexte: "Audit juridique (statuts, contrats, litiges), fiscal (arriérés, redressements), social (CNPS, contrats de travail), immobilier. Synthèse risques et recommandations.",
      },
      {
        key: "conformite_cima",
        label: "Note de conformité CIMA",
        description: "Vérification de conformité au Code CIMA pour compagnies d'assurance",
        type: "rapport",
        typeDoc: "note_juridique",
        mode: "standard",
        sujet: "Note de conformité au Code CIMA — compagnie d'assurance",
        contexte: "Vérification des ratios prudentiels CIMA, marge de solvabilité, provisions techniques, couverture des engagements réglementés. Points de non-conformité et plan de régularisation.",
      },
    ],
  },
  {
    key: "rh_management",
    categorie: "RH & Management",
    emoji: "👥",
    templates: [
      {
        key: "bilan_social",
        label: "Rapport bilan social",
        description: "Bilan social annuel — effectifs, rémunérations, formation, absentéisme",
        type: "rapport",
        typeDoc: "rapport_rh",
        mode: "complet",
        sujet: "Bilan social annuel — indicateurs RH et analyse",
        contexte: "Effectifs (pyramide des âges, turn-over), rémunérations (masse salariale, SMIG comparé), formation (plan, coûts, taux de réalisation), absentéisme, conformité Code du travail.",
      },
      {
        key: "restructuration_rh",
        label: "Plan de restructuration RH",
        description: "Note de restructuration des effectifs avec plan social",
        type: "rapport",
        typeDoc: "plan_action",
        mode: "standard",
        sujet: "Plan de restructuration des effectifs et plan social",
        contexte: "Justification économique, critères de sélection, mesures d'accompagnement (indemnités légales selon Code du travail, outplacement), calendrier de mise en œuvre.",
      },
      {
        key: "formation_management",
        label: "Slides séminaire formation",
        description: "Support de formation professionnelle (leadership, gestion d'équipe, etc.)",
        type: "slides",
        typeDoc: "formation",
        mode: "detaille",
        sujet: "Support de formation — développement des compétences managériales",
        contexte: "Objectifs pédagogiques, modules de formation, exercices pratiques, études de cas contextualisés Afrique, plan d'action individuel post-formation.",
      },
    ],
  },
  {
    key: "banque_microfinance",
    categorie: "Banque & Microfinance",
    emoji: "🏦",
    templates: [
      {
        key: "analyse_credit_pme",
        label: "Rapport analyse crédit PME",
        description: "Analyse de risque crédit pour une PME — scoring et décision",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "standard",
        sujet: "Analyse crédit PME — dossier de financement",
        contexte: "Analyse des états financiers SYSCOHADA, scoring crédit, ratios COBAC (endettement, couverture), garanties proposées, recommandation d'octroi avec conditions.",
      },
      {
        key: "ratios_cobac",
        label: "Note ratios prudentiels COBAC",
        description: "Calcul et commentaire des ratios prudentiels COBAC",
        type: "rapport",
        typeDoc: "note_de_synthese",
        mode: "standard",
        sujet: "Note d'analyse des ratios prudentiels COBAC",
        contexte: "Calcul des ratios COBAC : solvabilité (8%), liquidité (≥100%), transformation, division des risques. Comparaison vs normes réglementaires et plan d'action correctif si nécessaire.",
      },
      {
        key: "comite_credit",
        label: "Présentation comité de crédit",
        description: "Slides de présentation d'un dossier au comité de crédit",
        type: "slides",
        typeDoc: "rapport_direction",
        mode: "executive",
        sujet: "Présentation comité de crédit — dossier financement",
        contexte: "Résumé exécutif du client, analyse financière synthétique, structure du financement proposé, garanties, risques identifiés, recommandation.",
      },
    ],
  },
  {
    key: "commerce_business",
    categorie: "Commerce & Business",
    emoji: "📈",
    templates: [
      {
        key: "business_plan",
        label: "Business plan complet",
        description: "Business plan structuré pour création ou développement d'activité",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Business plan — création / développement d'activité",
        contexte: "Executive summary, étude de marché (PESTEL, Porter), modèle économique (BMC), plan marketing, plan opérationnel, projections financières sur 3 ans (P&L, BFR, TRI).",
      },
      {
        key: "analyse_marche",
        label: "Rapport analyse de marché",
        description: "Étude de marché sectorielle pour un pays d'Afrique subsaharienne",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Analyse de marché sectorielle — Afrique subsaharienne",
        contexte: "Taille du marché, acteurs clés, parts de marché, tendances, barrières à l'entrée, opportunités, menaces concurrentielles, recommandations de positionnement.",
      },
      {
        key: "pitch_deck",
        label: "Pitch deck investisseurs",
        description: "Présentation de levée de fonds pour investisseurs africains / internationaux",
        type: "slides",
        typeDoc: "pitch_projet",
        mode: "pitch",
        sujet: "Pitch deck — levée de fonds startup / PME",
        contexte: "Problème / Solution, taille du marché, traction (métriques clés), modèle économique, roadmap, équipe, besoins de financement, utilisation des fonds, exit potentiel.",
      },
      {
        key: "prospection",
        label: "Rapport prospection commerciale",
        description: "Analyse prospects et stratégie de développement commercial",
        type: "rapport",
        typeDoc: "plan_action",
        mode: "standard",
        sujet: "Plan de développement commercial — stratégie prospection",
        contexte: "Segmentation cibles, ICP (Ideal Customer Profile), argumentaire de vente différencié, plan de prospection (actions, calendrier, KPIs), prévisions de pipeline.",
      },
    ],
  },
  {
    key: "ong_projets",
    categorie: "ONG & Projets",
    emoji: "🌍",
    templates: [
      {
        key: "rapport_activites_ong",
        label: "Rapport d'activités ONG",
        description: "Rapport annuel d'activités pour bailleurs et partenaires",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport annuel d'activités — organisation",
        contexte: "Résumé exécutif, réalisations par axe stratégique, indicateurs d'impact atteints vs cibles, utilisation des ressources financières, leçons apprises, perspectives.",
      },
      {
        key: "note_conceptuelle",
        label: "Note conceptuelle projet",
        description: "Note conceptuelle pour soumission à un appel à projets / bailleur",
        type: "rapport",
        typeDoc: "note_de_synthese",
        mode: "standard",
        sujet: "Note conceptuelle — proposition de projet",
        contexte: "Contexte et justification, objectifs (général et spécifiques), bénéficiaires, approche et méthodologie, résultats attendus, cadre logique simplifié, budget indicatif.",
      },
      {
        key: "presentation_bailleur",
        label: "Présentation bailleur de fonds",
        description: "Slides de présentation d'un projet à un bailleur ou comité de pilotage",
        type: "slides",
        typeDoc: "rapport_direction",
        mode: "detaille",
        sujet: "Présentation projet — bailleur / comité de pilotage",
        contexte: "Rappel des objectifs, avancement physique et financier, indicateurs clés, défis rencontrés et solutions, prochaines étapes, besoins de soutien.",
      },
    ],
  },
  {
    key: "ingenierie_btp",
    categorie: "Ingénierie & BTP",
    emoji: "🏗️",
    templates: [
      {
        key: "avancement_travaux",
        label: "Rapport d'avancement travaux",
        description: "Rapport mensuel d'avancement d'un chantier",
        type: "rapport",
        typeDoc: "compte_rendu",
        mode: "standard",
        sujet: "Rapport d'avancement mensuel — chantier de construction",
        contexte: "Avancement physique par lot, planning prévisionnel vs réel, décompte financier, ressources mobilisées, réserves / non-conformités, plan d'actions, photos commentées.",
      },
      {
        key: "note_technique_etude",
        label: "Note technique étude",
        description: "Note technique pour une étude d'ingénierie ou d'avant-projet",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Note technique — étude d'ingénierie / avant-projet",
        contexte: "Contexte et objectifs, hypothèses de base, variantes étudiées, analyse comparative, solution retenue, spécifications techniques, estimatif des coûts.",
      },
    ],
  },
  {
    key: "sante_publique",
    categorie: "Santé Publique & Épidémiologie",
    emoji: "🏥",
    templates: [
      {
        key: "situation_epidemio",
        label: "Rapport de situation épidémiologique",
        description: "Rapport de situation épidémio hebdomadaire ou mensuel",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Rapport de situation épidémiologique — analyse et recommandations",
        contexte: "Description de la situation (cas confirmés, incidence, létalité), analyse par zone géographique et groupe démographique, courbe épidémique, facteurs de risque, mesures en cours, recommandations de riposte.",
      },
      {
        key: "protocole_enquete_epidemio",
        label: "Protocole d'enquête épidémiologique",
        description: "Protocole complet pour enquête de terrain en santé publique",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Protocole d'enquête épidémiologique de terrain",
        contexte: "Justification et objectifs, hypothèses, type d'étude (transversale/cas-témoins/cohorte), population cible et échantillonnage, variables et outils de collecte, procédures de terrain, plan d'analyse, considérations éthiques, calendrier et budget.",
      },
      {
        key: "evaluation_programme_sante",
        label: "Rapport d'évaluation programme santé",
        description: "Évaluation mi-parcours ou finale d'un programme de santé",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport d'évaluation d'un programme de santé publique",
        contexte: "Contexte et description du programme, méthodologie d'évaluation, analyse de la pertinence, efficacité, efficience, impact et durabilité (critères OCDE/CAD), indicateurs atteints vs cibles, leçons apprises, recommandations.",
      },
      {
        key: "formation_sante_publique",
        label: "Formation — Outils de santé publique",
        description: "Support de formation sur les outils et méthodes en santé publique",
        type: "slides",
        typeDoc: "formation",
        mode: "detaille",
        sujet: "Formation — Outils et méthodes en santé publique",
        contexte: "Objectifs pédagogiques, modules : épidémiologie descriptive, surveillance épidémiologique, enquêtes de terrain, analyse des données de santé, outils OMS/CDC/ECOWAS, exercices pratiques avec études de cas africains.",
      },
      {
        key: "presentation_programme_sante",
        label: "Présentation programme santé",
        description: "Slides de présentation d'un programme ou rapport de santé publique",
        type: "slides",
        typeDoc: "rapport_direction",
        mode: "executive",
        sujet: "Présentation programme de santé publique — résultats et perspectives",
        contexte: "Contexte sanitaire, objectifs du programme, indicateurs de performance clés, résultats atteints, défis, prochaines étapes et recommandations pour partenaires et autorités sanitaires.",
      },
    ],
  },
  {
    key: "recherche_protocoles",
    categorie: "Recherche & Protocoles d'étude",
    emoji: "🔬",
    templates: [
      {
        key: "protocole_etude",
        label: "Protocole d'étude / recherche",
        description: "Protocole scientifique complet pour étude ou recherche",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Protocole d'étude — recherche scientifique ou opérationnelle",
        contexte: "Titre et résumé, introduction et revue de littérature, problématique et justification, objectifs (général et spécifiques), hypothèses, méthodologie (type d'étude, population, échantillonnage, variables, outils), plan d'analyse statistique, aspects éthiques, calendrier, budget prévisionnel, bibliographie.",
      },
      {
        key: "rapport_enquete",
        label: "Rapport d'enquête / sondage",
        description: "Rapport de résultats d'une enquête quantitative ou qualitative",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport de résultats d'enquête",
        contexte: "Contexte et objectifs de l'enquête, méthodologie (type, échantillon, outils), résultats descriptifs (fréquences, moyennes, tableaux croisés), analyse inférentielle (tests statistiques), interprétation, conclusions et recommandations, annexes (questionnaire, tableaux détaillés).",
      },
      {
        key: "presentation_protocole",
        label: "Présentation protocole / résultats",
        description: "Slides de présentation d'un protocole ou des résultats d'étude",
        type: "slides",
        typeDoc: "rapport_direction",
        mode: "detaille",
        sujet: "Présentation protocole d'étude / résultats de recherche",
        contexte: "Contexte et problématique, objectifs, méthodologie, résultats clés avec graphiques et tableaux, discussion et limites, conclusions et recommandations, perspectives de recherche.",
      },
    ],
  },
  {
    key: "suivi_evaluation",
    categorie: "Suivi & Évaluation de projets",
    emoji: "📊",
    templates: [
      {
        key: "rapport_se",
        label: "Rapport de suivi S&E",
        description: "Rapport trimestriel ou semestriel de suivi-évaluation d'un projet",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport de suivi et évaluation — projet de développement",
        contexte: "Rappel des objectifs et indicateurs du cadre logique, avancement physique et financier par composante, analyse des indicateurs (atteints vs cibles, tendances), analyse des écarts, facteurs d'influence (risques, hypothèses), leçons apprises, recommandations et plan d'action correctif, perspectives.",
      },
      {
        key: "cadre_mesure_performance",
        label: "Cadre de mesure de la performance",
        description: "Document CMP / tableau de bord indicateurs d'un projet",
        type: "rapport",
        typeDoc: "plan_action",
        mode: "standard",
        sujet: "Cadre de mesure de la performance — indicateurs et plan de S&E",
        contexte: "Cadre logique ou théorie du changement, sélection et définition des indicateurs SMART (intrants, extrants, effets, impact), sources de vérification, fréquence de collecte, responsabilités, valeurs de référence (baseline) et cibles.",
      },
      {
        key: "presentation_se_bailleur",
        label: "Présentation S&E bailleur",
        description: "Slides de rapport de suivi à destination du bailleur ou comité",
        type: "slides",
        typeDoc: "rapport_direction",
        mode: "detaille",
        sujet: "Présentation rapport S&E — bailleur / comité de pilotage",
        contexte: "Rappel des objectifs, tableau de bord des indicateurs clés, avancement physique et financier, points saillants (succès et défis), risques en cours, actions correctives, prochaines étapes.",
      },
      {
        key: "evaluation_finale",
        label: "Évaluation finale de projet",
        description: "Rapport d'évaluation finale selon critères OCDE/CAD",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport d'évaluation finale de projet de développement",
        contexte: "Contexte et description du projet, méthodologie d'évaluation, analyse selon les 5 critères CAD-OCDE (pertinence, efficacité, efficience, impact, durabilité), analyse de genre et transversalité, leçons apprises, recommandations hiérarchisées, conclusion.",
      },
    ],
  },
  {
    key: "assurance_cima",
    categorie: "Assurance & Réassurance CIMA",
    emoji: "🛡️",
    templates: [
      {
        key: "solvabilite_cima",
        label: "Rapport de solvabilité CIMA",
        description: "Rapport annuel de solvabilité selon le Code CIMA révisé",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "complet",
        sujet: "Rapport de solvabilité CIMA — compagnie d'assurance",
        contexte: "Calcul de la marge de solvabilité (primes vs sinistres), provisions techniques (PPNA, PSAP, PSAV), actifs admis en représentation, ratios prudentiels CIMA, mesures correctives si seuils non atteints.",
      },
      {
        key: "tarification_actuarielle",
        label: "Note technique tarification",
        description: "Note actuarielle de tarification d'un produit d'assurance",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Note actuarielle de tarification d'un produit d'assurance",
        contexte: "Analyse sinistralité historique, méthodes actuarielles (fréquence/coût moyen, Chain Ladder, GLM), hypothèses, calcul de prime pure, chargements (gestion, acquisition, sécurité), tarification finale et sensibilités.",
      },
      {
        key: "gestion_sinistre",
        label: "Rapport gestion sinistre",
        description: "Rapport d'expertise et règlement d'un sinistre complexe",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Rapport de gestion sinistre — expertise et règlement",
        contexte: "Rappel des garanties souscrites, circonstances du sinistre, pièces reçues, expertise contradictoire, évaluation des dommages, application des franchises/plafonds, proposition de règlement, motivation juridique.",
      },
      {
        key: "ca_assurance",
        label: "Présentation conseil d'administration",
        description: "Slides de présentation CA compagnie d'assurance",
        type: "slides",
        typeDoc: "rapport_direction",
        mode: "detaille",
        sujet: "Présentation CA — résultats compagnie d'assurance",
        contexte: "Synthèse activité (CA, sinistralité S/P, résultat technique), solvabilité CIMA, placements, perspectives et décisions stratégiques à valider.",
      },
    ],
  },
  {
    key: "energie_mines",
    categorie: "Énergie, Mines & Pétrole",
    emoji: "⛽",
    templates: [
      {
        key: "eies_minier",
        label: "Étude d'impact environnemental",
        description: "EIES complète pour projet minier/énergétique (norme BAD/IFC)",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Étude d'impact environnemental et social — projet minier/énergétique",
        contexte: "Description du projet, état initial (biophysique, social), identification et évaluation des impacts, mesures d'atténuation/compensation, plan de gestion environnementale et sociale (PGES), plan de suivi. Conforme aux standards IFC/BAD.",
      },
      {
        key: "production_mensuelle",
        label: "Rapport production mensuelle",
        description: "Rapport mensuel de production énergie / mines",
        type: "rapport",
        typeDoc: "compte_rendu",
        mode: "standard",
        sujet: "Rapport de production mensuelle — énergie / mines",
        contexte: "Production physique (tonnage/MWh), taux de disponibilité des équipements, incidents HSE, performance vs budget, actions correctives, prévisions mois suivant.",
      },
      {
        key: "rentabilite_mines",
        label: "Note étude rentabilité projet",
        description: "Analyse financière TRI/VAN pour projet énergie ou mines",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "complet",
        sujet: "Étude de rentabilité — projet énergie / mines",
        contexte: "CAPEX/OPEX détaillé, hypothèses de prix et production, modèle financier (P&L, cash-flows, bilan), TRI projet/equity, VAN, analyse de sensibilité (prix, production, taux de change), seuil de rentabilité.",
      },
    ],
  },
  {
    key: "agriculture",
    categorie: "Agriculture & Agro-industrie",
    emoji: "🌾",
    templates: [
      {
        key: "plan_agricole",
        label: "Plan de développement agricole",
        description: "Plan d'affaires exploitation agricole / agro-industrielle",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Plan de développement — exploitation agricole / agro-industrie",
        contexte: "Analyse agronomique (sol, climat, filière), plan cultural, besoins en intrants et équipements, projections de rendement et de chiffre d'affaires, compte d'exploitation prévisionnel, plan de financement, analyse des risques climatiques.",
      },
      {
        key: "etude_filiere",
        label: "Étude de filière agricole",
        description: "Analyse filière (cacao, café, coton, riz, etc.) pays CEMAC/UEMOA",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Étude de filière agricole — diagnostic et recommandations",
        contexte: "Cartographie des acteurs (producteurs, coopératives, industriels, exportateurs), volumes et prix, infrastructures, politiques publiques, contraintes et opportunités, recommandations de structuration de la filière.",
      },
      {
        key: "campagne_agricole",
        label: "Rapport campagne agricole",
        description: "Bilan de campagne — rendements, ventes, marges",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Rapport de campagne agricole",
        contexte: "Superficies emblavées, rendements par culture, volumes produits, prix de cession, charges opérationnelles, marge brute, comparaison campagne précédente, enseignements et plan campagne suivante.",
      },
    ],
  },
  {
    key: "transport_logistique",
    categorie: "Transport & Logistique",
    emoji: "🚚",
    templates: [
      {
        key: "audit_supply_chain",
        label: "Étude logistique — chaîne d'approvisionnement",
        description: "Audit supply chain avec recommandations d'optimisation",
        type: "rapport",
        typeDoc: "rapport_audit",
        mode: "complet",
        sujet: "Audit logistique et chaîne d'approvisionnement",
        contexte: "Cartographie flux physiques et d'information, analyse coûts logistiques (transport, stockage, manutention), délais de livraison, ruptures, recommandations d'optimisation (modal, routier, entreposage, SI, KPIs logistiques).",
      },
      {
        key: "transport_urbain",
        label: "Plan de transport urbain",
        description: "Étude de schéma directeur transport pour collectivité",
        type: "rapport",
        typeDoc: "plan_action",
        mode: "complet",
        sujet: "Schéma directeur de transport urbain",
        contexte: "Diagnostic mobilité (enquêtes origine-destination, offre existante), projections de demande, scénarios d'infrastructure (BRT, bus, voirie), plan de financement, calendrier de mise en œuvre, indicateurs de performance.",
      },
      {
        key: "bp_flotte_transport",
        label: "Business plan flotte transport",
        description: "Dossier de financement création/extension flotte de transport",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Business plan — flotte de transport routier / marchandise",
        contexte: "Étude de marché fret, CAPEX véhicules, OPEX (carburant, entretien, chauffeurs, assurance), tarification, prévisions de CA, rentabilité, plan de financement (leasing, crédit), analyse de risques (carburant, change).",
      },
    ],
  },
  {
    key: "tech_digital",
    categorie: "Tech, Digital & SI",
    emoji: "💻",
    templates: [
      {
        key: "cdc_si",
        label: "Cahier des charges SI",
        description: "Cahier des charges fonctionnel et technique d'un projet SI",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Cahier des charges — projet système d'information",
        contexte: "Contexte et enjeux métier, périmètre, exigences fonctionnelles (use cases), exigences non-fonctionnelles (sécurité, performance, conformité RGPD/CAMTEL), architecture cible, livrables, planning, critères de recette.",
      },
      {
        key: "audit_cybersecurite",
        label: "Rapport d'audit cybersécurité",
        description: "Audit sécurité informatique avec recommandations ISO 27001",
        type: "rapport",
        typeDoc: "rapport_audit",
        mode: "complet",
        sujet: "Rapport d'audit cybersécurité",
        contexte: "Périmètre et méthodologie (ISO 27001, NIST), cartographie des actifs, analyse des vulnérabilités techniques et organisationnelles, tests d'intrusion, évaluation des risques, recommandations hiérarchisées avec plan de remédiation.",
      },
      {
        key: "pitch_tech_startup",
        label: "Pitch deck startup tech",
        description: "Pitch de levée pour startup tech africaine",
        type: "slides",
        typeDoc: "pitch_projet",
        mode: "pitch",
        sujet: "Pitch deck — startup tech africaine",
        contexte: "Problème et insight marché, solution tech, traction (MAU, MRR), modèle économique SaaS, concurrence, équipe fondatrice, plan de croissance Pan-Africain, levée de fonds et utilisation.",
      },
    ],
  },
  {
    key: "education_formation",
    categorie: "Éducation & Formation",
    emoji: "🎓",
    templates: [
      {
        key: "plan_strategique_etablissement",
        label: "Plan stratégique établissement",
        description: "Plan stratégique pluriannuel pour établissement scolaire/universitaire",
        type: "rapport",
        typeDoc: "plan_action",
        mode: "complet",
        sujet: "Plan stratégique — établissement d'enseignement",
        contexte: "Diagnostic (effectifs, taux de réussite, ressources, infrastructures), vision et axes stratégiques, objectifs SMART, plan d'action par axe, plan de financement, gouvernance et suivi.",
      },
      {
        key: "rapport_pedagogique",
        label: "Rapport pédagogique annuel",
        description: "Rapport annuel d'activités pédagogiques",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Rapport pédagogique annuel",
        contexte: "Effectifs et mouvements, résultats aux examens officiels, encadrement pédagogique, programmes parcourus, activités péri-éducatives, difficultés rencontrées, perspectives année suivante.",
      },
      {
        key: "module_formation_pro",
        label: "Module de formation professionnelle",
        description: "Support de formation professionnelle certifiante",
        type: "slides",
        typeDoc: "formation",
        mode: "detaille",
        sujet: "Module de formation professionnelle certifiante",
        contexte: "Objectifs pédagogiques, prérequis, plan du module, contenus théoriques et exercices pratiques, études de cas, modalités d'évaluation, bibliographie et ressources complémentaires.",
      },
    ],
  },
  {
    key: "immobilier",
    categorie: "Immobilier & Construction",
    emoji: "🏢",
    templates: [
      {
        key: "faisabilite_immobiliere",
        label: "Étude de faisabilité immobilière",
        description: "Étude technique, juridique et financière d'un projet immobilier",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Étude de faisabilité — projet immobilier",
        contexte: "Analyse du foncier (titre, servitudes, PLU), étude de marché (offre/demande, prix m²), programme constructible, CAPEX construction, planning, commercialisation, compte d'exploitation, retour sur investissement.",
      },
      {
        key: "expertise_immobiliere",
        label: "Rapport expertise immobilière",
        description: "Rapport d'expertise et valorisation d'un bien immobilier",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Rapport d'expertise immobilière",
        contexte: "Description du bien, titre et régularité juridique, méthodes de valorisation (comparatif, revenu, coût de remplacement), justification de la valeur retenue, conclusion avec marge de précision.",
      },
    ],
  },
  {
    key: "tourisme",
    categorie: "Tourisme & Hôtellerie",
    emoji: "🏨",
    templates: [
      {
        key: "bp_hotel",
        label: "Business plan hôtel / resort",
        description: "Business plan complet pour création hôtel ou resort",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Business plan — hôtel / resort",
        contexte: "Étude de marché touristique, concept et positionnement, programme (chambres, F&B, SPA), CAPEX, prévisions RevPar/ADR/TO, compte d'exploitation 5 ans, plan de financement, stratégie marketing.",
      },
      {
        key: "performance_hoteliere",
        label: "Rapport performance hôtelière",
        description: "Rapport mensuel KPIs hôteliers (TO, ADR, RevPAR, GOP)",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "standard",
        sujet: "Rapport de performance hôtelière mensuelle",
        contexte: "Taux d'occupation, ADR, RevPAR, F&B ratios, GOP, comparaison N-1 et budget, analyse par segment (corporate/leisure/groupes), canaux de distribution, actions commerciales et marketing.",
      },
    ],
  },
  {
    key: "communication_marketing",
    categorie: "Communication & Marketing",
    emoji: "📣",
    templates: [
      {
        key: "plan_communication",
        label: "Plan de communication 360°",
        description: "Stratégie communication multicanale pour marque/produit",
        type: "rapport",
        typeDoc: "plan_action",
        mode: "complet",
        sujet: "Plan de communication 360° — marque / produit",
        contexte: "Diagnostic de marque, insights consommateurs, objectifs SMART, cibles et personas, positionnement, message clé, mix médias (TV, radio, digital, OOH, influenceurs), calendrier, budget, KPIs.",
      },
      {
        key: "brief_creatif",
        label: "Brief créatif campagne",
        description: "Brief créatif pour agence de communication",
        type: "rapport",
        typeDoc: "note_de_synthese",
        mode: "standard",
        sujet: "Brief créatif — campagne de communication",
        contexte: "Contexte, objectifs business et de communication, cible prioritaire, insight consommateur, promesse, ton, mandatories, livrables attendus, calendrier, budget.",
      },
      {
        key: "bilan_campagne_com",
        label: "Rapport bilan campagne",
        description: "Bilan de performance d'une campagne de communication",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Bilan de performance d'une campagne de communication",
        contexte: "Rappel des objectifs, KPIs atteints vs cibles (reach, engagement, conversions, ventes), analyse par canal, ROI, enseignements et recommandations pour les prochaines campagnes.",
      },
    ],
  },
];

// Templates personnalisés ajoutés par l'utilisateur (persistés en localStorage).
// Survit aux recharges et permet d'enrichir la bibliothèque sans déploiement.
const KEY_TEMPLATES_PERSO = "yukpo_pro_templates_perso_v1";
function chargerTemplatesPerso(): CategorieTemplates[] {
  try {
    const raw = localStorage.getItem(KEY_TEMPLATES_PERSO);
    return raw ? (JSON.parse(raw) as CategorieTemplates[]) : [];
  } catch { return []; }
}
function sauverTemplatesPerso(cats: CategorieTemplates[]) {
  try { localStorage.setItem(KEY_TEMPLATES_PERSO, JSON.stringify(cats)); } catch {}
}

const TYPES_RAPPORT_VALUES = [
  "rapport_analyse","note_de_synthese","note_juridique","rapport_financier",
  "rapport_rh","plan_action","compte_rendu","rapport_audit",
];

const MODES_RAPPORT_VALUES = ["flash","standard","complet","expert"];

const TYPES_SLIDES_VALUES = [
  "bilan_activite","proposition_client","rapport_direction","formation",
  "pitch_projet","analyse_marche","rapport_financier",
];

const MODES_SLIDES_VALUES = ["executive","detaille","pitch","expert"];

const TYPES_SORTIE_FICHIERS_VALUES = [
  "rapport_analyse","rapport_financier","rapport_audit","note_de_synthese",
  "note_juridique","plan_action","rapport_direction","bilan_activite",
  "proposition_client","pitch_projet",
];

const EXTENSIONS_ACCEPTEES = ".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.md,.pptx";
const FORMATS_SLIDES = new Set(["rapport_direction","bilan_activite","proposition_client","pitch_projet","formation","analyse_marche"]);

export const GenerateursPage = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  // Onglet persisté dans le store → survit à la navigation
  const tab = useGenerateurStore((s) => s.tab) as Tab;
  const setTab = (tt: Tab) => useGenerateurStore.getState().setTab(tt);
  const [openCat, setOpenCat] = useState<string | null>(null);

  // Persistance des jobs (survit à la navigation)
  const runJob = useGenerateurStore((s) => s.run);
  const clearJob = useGenerateurStore((s) => s.clear);
  const storeLoading = useGenerateurStore((s) => s.loading);
  const storeResultats = useGenerateurStore((s) => s.resultats);

  // Pour les onglets rapport/slides/fichiers on partage le même "loading" + "resultat"
  // selon l'onglet actif. Les jobs en arrière-plan restent indépendants par clé.
  const currentJobKey: "rapport" | "slides" | "fichiers" =
    tab === "slides" ? "slides" : tab === "conversion" ? "fichiers" : tab === "rapport" ? "rapport" : "fichiers";
  const loading = storeLoading[currentJobKey];
  const resultat = storeResultats[currentJobKey] as { fichier?: string; markdown?: string; chemin?: string } | null;
  const setResultat = (v: any) => useGenerateurStore.getState().setResultat(currentJobKey, v);

  // Rapport
  const [sujetRapport, setSujetRapport] = useState("");
  const [typeRapport, setTypeRapport] = useState("rapport_analyse");
  const [modeRapport, setModeRapport] = useState("standard");
  const [contexteRapport, setContexteRapport] = useState("");
  const [formatRapport, setFormatRapport] = useState("docx");

  // Slides
  const [sujetSlides, setSujetSlides] = useState("");
  const [typeSlides, setTypeSlides] = useState("rapport_direction");
  const [modeSlides, setModeSlides] = useState("executive");
  const [contexteSlides, setContexteSlides] = useState("");
  const [formatSlides, setFormatSlides] = useState("pptx");

  // Depuis fichiers (onglet dédié)
  const [fichiers, setFichiers] = useState<File[]>([]);
  const [instructionFichiers, setInstructionFichiers] = useState("");
  const [typeSortieFichiers, setTypeSortieFichiers] = useState("rapport_analyse");
  const [modeFichiers, setModeFichiers] = useState("standard");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fichiers intégrés dans les onglets rapport/slides
  const [fichiersRapport, setFichiersRapport] = useState<File[]>([]);
  const [fichiersSlides, setFichiersSlides]   = useState<File[]>([]);
  const fileRapportRef = useRef<HTMLInputElement>(null);
  const fileSlidesRef  = useRef<HTMLInputElement>(null);

  // ── Infographie Pro (print-ready PDF + PNG preview) ──────────────────────
  const [infogDesignerMode, setInfogDesignerMode] = useState<"monopages" | "multipages">("multipages");
  const [infogMode, setInfogMode]               = useState<InfogMode>("brief");
  const [infogGabarits, setInfogGabarits]       = useState<GabaritInfographie[]>([]);
  const [infogPalettes, setInfogPalettes]       = useState<string[]>([]);
  const [infogGabarit, setInfogGabarit]         = useState<string>("flyer_a5");
  const [infogPays, setInfogPays]               = useState<string>("CM");
  const infogLoading = storeLoading.infographie;
  const infogResult = storeResultats.infographie as ResultatInfographieReponse | null;
  const setInfogResult = (v: ResultatInfographieReponse | null) => useGenerateurStore.getState().setResultat("infographie", v);
  const [infogZoom, setInfogZoom]               = useState(false);
  // Brief IA
  const [infogBrief, setInfogBrief]             = useState("");
  // Manuel
  const [infogPalette, setInfogPalette]         = useState("classique");
  const [infogTitre, setInfogTitre]             = useState("");
  const [infogSousTitre, setInfogSousTitre]     = useState("");
  const [infogCorps, setInfogCorps]             = useState("");
  const [infogDetails, setInfogDetails]         = useState("");
  const [infogOrg, setInfogOrg]                 = useState("");
  const [infogContact, setInfogContact]         = useState("");
  const [infogSlogan, setInfogSlogan]           = useState("");
  const [infogDate, setInfogDate]               = useState("");
  const [infogLieu, setInfogLieu]               = useState("");
  // Modèle (upload image)
  const [infogModele, setInfogModele]           = useState<File | null>(null);
  const infogModeleRef                          = useRef<HTMLInputElement>(null);
  // Custom (dimensions libres)
  const [infogW, setInfogW]                     = useState<number>(148);
  const [infogH, setInfogH]                     = useState<number>(210);
  const [infogBleed, setInfogBleed]             = useState<number>(3);

  useEffect(() => {
    if (tab !== "infographie" || infogGabarits.length > 0) return;
    infographieApi.listerGabarits()
      .then(d => {
        setInfogGabarits(d.gabarits);
        setInfogPalettes(d.palettes);
        if (d.palettes?.length) setInfogPalette(d.palettes[0]);
      })
      .catch(() => toast.error(t("generateurs.loadGabaritFailed")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const gabaritsParCategorie = infogGabarits.reduce<Record<string, GabaritInfographie[]>>((acc, g) => {
    (acc[g.categorie] ||= []).push(g);
    return acc;
  }, {});
  const gabaritCourant = infogGabarits.find(g => g.cle === infogGabarit);

  const handleGenererInfographie = async (e: FormEvent) => {
    e.preventDefault();
    // Validations synchrones (avant de lancer le job)
    if (infogMode === "brief" && infogBrief.trim().length < 10) {
      toast.error(t("generateurs.briefMin10")); return;
    }
    if (infogMode === "manuel" && !infogTitre.trim()) { toast.error(t("generateurs.titleRequired")); return; }
    if (infogMode === "modele") {
      if (!infogModele) { toast.error(t("generateurs.chooseModelImage")); return; }
      if (infogBrief.trim().length < 10) { toast.error(t("generateurs.briefMin10")); return; }
    }
    if (infogMode === "custom") {
      if (infogBrief.trim().length < 10) { toast.error(t("generateurs.briefMin10")); return; }
      if (infogW <= 0 || infogH <= 0) { toast.error(t("generateurs.invalidDimensions")); return; }
    }

    await runJob("infographie", async () => {
      if (infogMode === "brief") {
        return await infographieApi.genererDepuisBrief({ brief: infogBrief, type_gabarit: infogGabarit, pays: infogPays });
      } else if (infogMode === "manuel") {
        return await infographieApi.genererManuel({
          type_gabarit: infogGabarit,
          titre: infogTitre,
          sous_titre: infogSousTitre || undefined,
          corps: infogCorps || undefined,
          details: infogDetails.split("\n").map(s => s.trim()).filter(Boolean),
          palette: infogPalette,
          nom_organisation: infogOrg || undefined,
          contact: infogContact || undefined,
          slogan: infogSlogan || undefined,
          date_evenement: infogDate || undefined,
          lieu: infogLieu || undefined,
        });
      } else if (infogMode === "modele") {
        return await infographieApi.genererDepuisModele({
          modele: infogModele!, brief: infogBrief, type_gabarit: infogGabarit, pays: infogPays,
        });
      } else {
        return await infographieApi.genererCustom({
          width_mm: infogW, height_mm: infogH, bleed_mm: infogBleed, brief: infogBrief, pays: infogPays,
        });
      }
    }, {
      successMsg: t("generateurs.infogSavedDocs"),
      onError: (err) => {
        const status = err?.response?.status;
        const detail: string = err?.response?.data?.detail || "";
        if (status === 402 && detail.startsWith("CREDITS_EPUISES")) {
          const restants = /restants=(\d+)/.exec(detail)?.[1] ?? "0";
          const plan     = /plan=([^|]+)/.exec(detail)?.[1] ?? "—";
          toast((to) => (
            <span className="text-sm">
              {t("generateurs.creditsInsufficient", { restants, plan })}
              <button
                onClick={() => { toast.dismiss(to.id); navigate("/abonnement"); }}
                className="ml-2 px-2 py-1 bg-yukpo-500 text-white rounded text-xs font-semibold"
              >
                {t("generateurs.rechargeUpgrade")}
              </button>
            </span>
          ), { duration: 8000, icon: "💳" });
        } else if (status === 403 && detail.startsWith("MODULE_NON_AUTORISE")) {
          toast((to) => (
            <span className="text-sm">
              {t("generateurs.moduleInfogNotIncluded")}
              <button
                onClick={() => { toast.dismiss(to.id); navigate("/abonnement"); }}
                className="ml-2 px-2 py-1 bg-purple-500 text-white rounded text-xs font-semibold"
              >
                {t("generateurs.upgrade")}
              </button>
            </span>
          ), { duration: 8000, icon: "🔒" });
        } else {
          toast.error(detail || t("generateurs.generationError"));
        }
      },
    });
  };

  const handleTelechargerInfog = (kind: "pdf" | "png" | "pdf_cmyk" | "png_hd" | "svg") => {
    if (!infogResult) return;
    const map: Record<string, { b64?: string; id?: string; mime: string }> = {
      pdf:      { b64: infogResult.pdf_base64 ?? undefined,         id: infogResult.pdf_id ?? undefined,         mime: "application/pdf" },
      png:      { b64: (infogResult.png_preview_base64 || infogResult.png_base64) ?? undefined, id: (infogResult.png_preview_id || infogResult.png_id) ?? undefined, mime: "image/png" },
      pdf_cmyk: { b64: infogResult.pdf_cmyk_base64 ?? undefined,    id: infogResult.pdf_cmyk_id ?? undefined,    mime: "application/pdf" },
      png_hd:   { b64: infogResult.png_base64 ?? undefined,         id: infogResult.png_id ?? undefined,         mime: "image/png" },
      svg:      { b64: infogResult.svg_base64 ?? undefined,         id: infogResult.svg_id ?? undefined,         mime: "image/svg+xml" },
    };
    const item = map[kind];
    if (!item.b64 || !item.id) { toast.error(t("generateurs.fileUnavailable")); return; }
    const a = document.createElement("a");
    a.href = `data:${item.mime};base64,${item.b64}`;
    a.download = item.id;
    a.click();
  };

  // ── Variantes (4 directions créatives en parallèle) ─────────────────────
  const [infogVariantes, setInfogVariantes] = useState<Array<{ direction: string; resultat: ResultatInfographieReponse }> | null>(null);
  const [infogRetoucheInstr, setInfogRetoucheInstr] = useState("");

  const handleGenererVariantes = async () => {
    if (infogBrief.trim().length < 10) { toast.error(t("generateurs.briefMin10")); return; }
    setInfogVariantes(null);
    await runJob("infographie", async () => {
      const data = await infographieApi.genererVariantes({
        brief: infogBrief, type_gabarit: infogGabarit, pays: infogPays, nombre: 4,
      });
      const wrapped = (data.variantes || []).map((v) => ({ direction: v.variante, resultat: v as ResultatInfographieReponse }));
      setInfogVariantes(wrapped);
      // On pose la 1ère variante comme résultat principal pour l'aperçu
      if (wrapped[0]) return wrapped[0].resultat;
      return null;
    }, { successMsg: t("generateurs.fourVariantsGenerated") });
  };

  const handleRetoucher = async () => {
    if (!infogResult?.pdf_id) { toast.error(t("generateurs.noInfogToRetouch")); return; }
    if (infogRetoucheInstr.trim().length < 5) { toast.error(t("generateurs.specifyChange")); return; }
    await runJob("infographie", async () => {
      const r = await infographieApi.modifier({
        fichier_id: infogResult.pdf_id!, instructions: infogRetoucheInstr, pays: infogPays,
      });
      setInfogRetoucheInstr("");
      return r;
    }, { successMsg: t("generateurs.infogRetouched") });
  };

  // ── Conversion de format ──────────────────────────────────────────────────
  const [fichierConv, setFichierConv] = useState<File | null>(null);
  const [formatCible, setFormatCible] = useState("docx");
  const loadingConv = storeLoading.conversion;
  const resultatConv = storeResultats.conversion as { fichier_converti: string; format_source: string; format_cible: string } | null;
  const setResultatConv = (v: any) => useGenerateurStore.getState().setResultat("conversion", v);
  const fileConvRef = useRef<HTMLInputElement>(null);

  const CONVERSIONS_MAP: Record<string, { label: string; cibles: { value: string; label: string }[] }> = {
    ".pdf":  { label: "PDF",        cibles: [{ value: "docx", label: "Word (DOCX)" }, { value: "pptx", label: "PowerPoint (PPTX)" }, { value: "txt", label: "Texte (TXT)" }] },
    ".docx": { label: "Word",       cibles: [{ value: "pdf", label: "PDF" }, { value: "pptx", label: "PowerPoint" }, { value: "txt", label: "Texte" }] },
    ".doc":  { label: "Word (doc)", cibles: [{ value: "docx", label: "Word DOCX" }, { value: "txt", label: "Texte" }] },
    ".pptx": { label: "PowerPoint", cibles: [{ value: "docx", label: "Word (DOCX)" }, { value: "pdf", label: "PDF" }, { value: "txt", label: "Texte" }] },
    ".xlsx": { label: "Excel",      cibles: [{ value: "csv", label: "CSV" }, { value: "docx", label: "Word" }, { value: "txt", label: "Texte" }] },
    ".xls":  { label: "Excel",      cibles: [{ value: "csv", label: "CSV" }, { value: "docx", label: "Word" }] },
    ".csv":  { label: "CSV",        cibles: [{ value: "xlsx", label: "Excel (XLSX)" }, { value: "docx", label: "Word" }] },
    ".txt":  { label: "Texte",      cibles: [{ value: "docx", label: "Word (DOCX)" }] },
    ".jpg":  { label: "Image JPG",  cibles: [{ value: "docx", label: "Word (OCR)" }, { value: "txt", label: "Texte (OCR)" }] },
    ".jpeg": { label: "Image JPEG", cibles: [{ value: "docx", label: "Word (OCR)" }, { value: "txt", label: "Texte (OCR)" }] },
    ".png":  { label: "Image PNG",  cibles: [{ value: "docx", label: "Word (OCR)" }, { value: "txt", label: "Texte (OCR)" }] },
  };

  const extConv = fichierConv ? `.${fichierConv.name.split(".").pop()!.toLowerCase()}` : "";
  const ciblsDispos = CONVERSIONS_MAP[extConv]?.cibles ?? [{ value: "docx", label: "Word (DOCX)" }];

  const handleConvertir = async (e: FormEvent) => {
    e.preventDefault();
    if (!fichierConv) return;
    await runJob(
      "conversion",
      () => generateurApi.convertirFichier(fichierConv, formatCible),
      { successMsg: t("generateurs.conversionSuccess"), errorMsg: t("generateurs.conversionError") },
    );
  };

  const ajouterFichiers = (nouv: FileList | null) => {
    if (!nouv) return;
    const liste = Array.from(nouv);
    setFichiers(prev => {
      const noms = new Set(prev.map(f => f.name));
      return [...prev, ...liste.filter(f => !noms.has(f.name))];
    });
  };

  const retirerFichier = (index: number) =>
    setFichiers(prev => prev.filter((_, i) => i !== index));

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    ajouterFichiers(e.dataTransfer.files);
  };

  const handleAnalyserEtGenerer = async (e: FormEvent) => {
    e.preventDefault();
    if (!instructionFichiers.trim()) return toast.error(t("generateurs.describeWhatToGenerate"));
    if (fichiers.length === 0) return toast.error(t("generateurs.addAtLeastOneFile"));
    const estSlides = FORMATS_SLIDES.has(typeSortieFichiers);
    await runJob("fichiers", () => generateurApi.analyserEtGenerer({
      instruction: instructionFichiers,
      type_sortie: estSlides ? "slides" : "rapport",
      type_doc: typeSortieFichiers,
      mode: modeFichiers,
      format_sortie: estSlides ? "pptx" : "docx",
      fichiers,
    }), { successMsg: t("generateurs.documentFromFiles", { count: fichiers.length }) });
  };

  const handleGenererRapport = async (e: FormEvent) => {
    e.preventDefault();
    if (!sujetRapport.trim()) return;
    if (fichiersRapport.length > 0) {
      const instruction = [sujetRapport, contexteRapport].filter(Boolean).join("\n\n");
      await runJob("rapport", () => generateurApi.analyserEtGenerer({
        instruction,
        type_sortie: "rapport",
        type_doc: typeRapport,
        mode: modeRapport,
        format_sortie: "docx",
        fichiers: fichiersRapport,
      }), { successMsg: t("generateurs.reportFromFiles", { count: fichiersRapport.length }) });
    } else {
      await runJob("rapport", () => generateurApi.rapport({
        sujet: sujetRapport,
        type_rapport: typeRapport,
        mode: modeRapport,
        contexte: contexteRapport || undefined,
        format_sortie: formatRapport as "docx" | "pdf" | "markdown",
      }), { successMsg: t("generateurs.reportSuccess") });
    }
  };

  const handleGenererSlides = async (e: FormEvent) => {
    e.preventDefault();
    if (!sujetSlides.trim()) return;
    if (fichiersSlides.length > 0) {
      const instruction = [sujetSlides, contexteSlides].filter(Boolean).join("\n\n");
      await runJob("slides", () => generateurApi.analyserEtGenerer({
        instruction,
        type_sortie: "slides",
        type_doc: typeSlides,
        mode: modeSlides,
        format_sortie: "pptx",
        fichiers: fichiersSlides,
      }), { successMsg: t("generateurs.presentationFromFiles", { count: fichiersSlides.length }) });
    } else {
      await runJob("slides", () => generateurApi.slides({
        sujet: sujetSlides,
        type_pres: typeSlides,
        mode: modeSlides,
        contexte: contexteSlides || undefined,
        format_sortie: formatSlides as "pptx" | "pdf" | "markdown",
      }), { successMsg: t("generateurs.presentationSuccess") });
    }
  };

  return (
    <div className="p-6 pb-24 space-y-6 max-w-5xl mx-auto animate-fade-in">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-display font-bold text-white flex items-center gap-2">
          {t('generateurs.title')}
          <span className="text-xs font-semibold px-2 py-0.5 bg-corp-600/15 border border-corp-600/30 text-corp-600 rounded-full tracking-wide">PRO</span>
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          {t('generateurs.subtitle')}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl flex-wrap" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
        {([
          { id: "rapport",    icon: <FileText className="w-4 h-4" />,      label: t('generateurs.tabRapport') },
          { id: "slides",     icon: <Presentation className="w-4 h-4" />,  label: t('generateurs.tabSlides') },
          { id: "conversion", icon: <RefreshCw className="w-4 h-4" />,     label: t('generateurs.tabConversion') },
          { id: "modeles",    icon: <BookOpen className="w-4 h-4" />,      label: t('generateurs.tabModeles') },
          { id: "infographie", icon: <Sparkles className="w-4 h-4" />,   label: t('generateurs.tabDesignerPro', 'Designer Pro') },
        ] as const).map(({ id, icon, label }) => (
          <button
            key={id}
            onClick={() => { setTab(id as Tab); }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === id ? "bg-yukpo-500 text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* Bibliothèque de modèles — accordéon */}
      {tab === "modeles" && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 mb-3">
            {t("generateurs.modelsHint", { total: TEMPLATES_PAR_METIER.reduce((s, c) => s + c.templates.length, 0) })}
          </p>
          {TEMPLATES_PAR_METIER.map((cat) => {
            const isOpen = openCat === cat.key;
            return (
              <div key={cat.key} className="rounded-xl border border-slate-700/60 overflow-hidden">
                <button
                  onClick={() => setOpenCat(isOpen ? null : cat.key)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800 transition-colors"
                  style={{ background: "var(--ykp-surface)" }}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-xl">{cat.emoji}</span>
                    <div className="text-left">
                      <p className="text-sm font-semibold text-white">{t(`generateurs.templates.categories.${cat.key}`, cat.categorie)}</p>
                      <p className="text-xs text-slate-500">
                        {t("generateurs.modelsCount", { count: cat.templates.length, plural: cat.templates.length > 1 ? "s" : "" })}
                        {" · "}
                        {cat.templates.filter(t => t.type === "rapport").length > 0 && (
                          <span className="text-blue-400">{cat.templates.filter(t => t.type === "rapport").length} DOCX</span>
                        )}
                        {cat.templates.filter(t => t.type === "rapport").length > 0 && cat.templates.filter(t => t.type === "slides").length > 0 && " · "}
                        {cat.templates.filter(t => t.type === "slides").length > 0 && (
                          <span className="text-purple-400">{cat.templates.filter(t => t.type === "slides").length} PPTX</span>
                        )}
                      </p>
                    </div>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
                </button>

                {isOpen && (
                  <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-2 p-3" style={{ background: "var(--ykp-elevated)", borderTop: "1px solid var(--ykp-border)" }}>
                    {cat.templates.map((tpl) => (
                      <button
                        key={tpl.key}
                        onClick={() => {
                          if (tpl.type === "rapport") {
                            setSujetRapport(tpl.sujet);
                            setTypeRapport(tpl.typeDoc);
                            setModeRapport(tpl.mode);
                            setContexteRapport(tpl.contexte);
                            setFormatRapport("docx");
                          } else {
                            setSujetSlides(tpl.sujet);
                            setTypeSlides(tpl.typeDoc);
                            setModeSlides(tpl.mode);
                            setContexteSlides(tpl.contexte);
                            setFormatSlides("pptx");
                          }
                          setTab(tpl.type as Tab);
                          setResultat(null);
                          toast.success(t("generateurs.modelLoaded", { label: t(`generateurs.templates.items.${tpl.key}.label`, tpl.label) }));
                        }}
                        className="group text-left p-3 rounded-xl hover:border-yukpo-500/60 hover:bg-yukpo-500/5 transition-all"
                        style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}
                      >
                        <div className="flex items-start justify-between gap-1.5 mb-1">
                          <p className="text-xs font-semibold text-white group-hover:text-yukpo-300 transition-colors leading-snug">
                            {t(`generateurs.templates.items.${tpl.key}.label`, tpl.label)}
                          </p>
                          <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                            tpl.type === "rapport"
                              ? "bg-blue-500/15 text-blue-300"
                              : "bg-purple-500/15 text-purple-300"
                          }`}>
                            {tpl.type === "rapport" ? "DOCX" : "PPTX"}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 leading-snug line-clamp-2">{t(`generateurs.templates.items.${tpl.key}.description`, tpl.description)}</p>
                        <div className="flex items-center gap-0.5 text-[10px] text-yukpo-400 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          {t("generateurs.useTemplate")} <ArrowRight className="w-2.5 h-2.5" />
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Onglet Depuis fichiers ─────────────────────────────────────────── */}
      {tab === "fichiers" && (
        <div className="space-y-4">
          <form onSubmit={handleAnalyserEtGenerer}>
            {/* Ligne 1 : zone dépôt compacte + instruction côte à côte */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 items-stretch">
              {/* Zone de dépôt compacte */}
              <div className="flex flex-col">
                <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">{t("generateurs.filesSources")}</p>
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`flex flex-col justify-center flex-1 min-h-[160px] gap-3 px-4 py-4 rounded-xl border-2 border-dashed cursor-pointer transition-all ${
                    dragOver
                      ? "border-yukpo-400 bg-yukpo-500/10"
                      : fichiers.length > 0
                        ? "border-yukpo-500/50 bg-yukpo-500/5"
                        : "border-slate-600 hover:border-slate-500"
                  }`}
                  style={!dragOver && fichiers.length === 0 ? { background: "var(--ykp-surface)" } : {}}
                >
                  <div className="flex items-center gap-3">
                    <FolderOpen className={`w-6 h-6 shrink-0 ${fichiers.length > 0 ? "text-yukpo-400" : "text-slate-500"}`} />
                    <div>
                      <p className="text-sm font-medium text-slate-300">
                        {fichiers.length > 0 ? t('generateurs.filesLoaded', { count: fichiers.length }) : t('generateurs.dropFilesHere')}
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5">PDF, DOCX, XLSX, CSV, TXT, PPTX</p>
                    </div>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept={EXTENSIONS_ACCEPTEES}
                    className="hidden"
                    onChange={(e) => ajouterFichiers(e.target.files)}
                  />
                </div>

                {/* Liste des fichiers */}
                {fichiers.length > 0 && (
                  <div className="mt-2 space-y-1 max-h-32 overflow-y-auto">
                    {fichiers.map((f, i) => (
                      <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 bg-slate-800 rounded-lg border border-slate-700">
                        <FileText className="w-3 h-3 text-blue-400 shrink-0" />
                        <span className="text-xs text-slate-300 flex-1 truncate">{f.name}</span>
                        <span className="text-xs text-slate-500">{(f.size / 1024).toFixed(0)} Ko</span>
                        <button type="button" onClick={() => retirerFichier(i)} className="text-slate-500 hover:text-red-400">
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Instruction */}
              <div className="flex flex-col">
                <label className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">
                  {t("generateurs.instructionLabel")}
                </label>
                <textarea
                  placeholder={t("generateurs.filesInstructionPlaceholder")}
                  value={instructionFichiers}
                  onChange={(e) => setInstructionFichiers(e.target.value)}
                  className="flex-1 min-h-[160px] w-full rounded-xl border border-slate-600 bg-slate-800/60 px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-yukpo-500 focus:ring-1 focus:ring-yukpo-500/40 resize-none transition-colors"
                />
              </div>
            </div>

            {/* Ligne 2 : Type de sortie + Mode + Bouton sur la même ligne */}
            <div className="flex flex-col sm:flex-row items-end gap-3">
              <div className="flex-1">
                <Select
                  label={t('generateurs.docType')}
                  options={TYPES_SORTIE_FICHIERS_VALUES.map(v => ({ value: v, label: t(`generateurs.lists.sortie.${v}`) }))}
                  value={typeSortieFichiers}
                  onChange={(e) => setTypeSortieFichiers(e.target.value)}
                />
              </div>
              <div className="w-full sm:w-44">
                <Select
                  label={t('generateurs.mode')}
                  options={[
                    { value: "flash",    label: t("generateurs.modeFlash") },
                    { value: "standard", label: t("generateurs.modeStandard") },
                    { value: "complet",  label: t("generateurs.modeComplet") },
                    { value: "executive", label: t("generateurs.modeExecutive") },
                  ]}
                  value={modeFichiers}
                  onChange={(e) => setModeFichiers(e.target.value)}
                />
              </div>
              {/* Bouton toujours visible sur la même ligne */}
              <div className="w-full sm:w-auto shrink-0 pb-0.5">
                <Button
                  type="submit"
                  loading={loading}
                  disabled={!instructionFichiers.trim() || fichiers.length === 0}
                  icon={<Upload className="w-4 h-4" />}
                  className="w-full sm:w-auto whitespace-nowrap"
                >
                  {t('generateurs.analyser')}
                </Button>
              </div>
            </div>
          </form>

          {/* Résultat */}
          {loading && (
            <Card className="p-6 flex items-center gap-4">
              <Loader className="w-6 h-6 text-yukpo-400 animate-spin shrink-0" />
              <div>
                <p className="text-white font-medium text-sm">{t("generateurs.analyzing")}</p>
                <p className="text-slate-400 text-xs mt-0.5">{t("generateurs.analyzingHelper")}</p>
              </div>
            </Card>
          )}
          {!loading && resultat && (
            <Card className="p-5 space-y-3 animate-fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 text-green-400" />
                  <span className="text-sm font-semibold text-white">{t("generateurs.documentReady")}</span>
                </div>
                <button
                  type="button"
                  onClick={() => { setResultat(null); setFichiers([]); setInstructionFichiers(""); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-600 text-slate-400 text-xs font-medium hover:border-yukpo-500 hover:text-yukpo-300 transition-all"
                >
                  <Upload className="w-3 h-3" /> {t("generateurs.generateAnother")}
                </button>
              </div>
              {resultat.fichier && (
                <a
                  href={generateurApi.telecharger(resultat.fichier)}
                  download={resultat.fichier}
                  className="flex items-center gap-3 p-4 bg-blue-50 dark:bg-yukpo-500/20 border border-blue-200 dark:border-yukpo-500/40 rounded-xl hover:bg-blue-100 dark:hover:bg-yukpo-500/30 transition-colors group"
                >
                  <Download className="w-5 h-5 shrink-0 text-blue-600 dark:text-yukpo-400" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{resultat.fichier}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("generateurs.clickToDownload")}</p>
                  </div>
                  <Download className="w-4 h-4 shrink-0 ml-auto text-blue-400 dark:text-yukpo-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                </a>
              )}
              {resultat.markdown && (
                <div className="max-h-64 overflow-y-auto">
                  <p className="text-xs text-slate-500 mb-2">{t("generateurs.preview")}</p>
                  <div className="p-3 bg-slate-100 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 text-xs">
                    <ReactMarkdown className="prose prose-sm prose-invert max-w-none">
                      {resultat.markdown.slice(0, 2000)}
                    </ReactMarkdown>
                  </div>
                </div>
              )}
            </Card>
          )}
        </div>
      )}

      {/* ── Onglet Conversion de format ───────────────────────────────────── */}
      {tab === "conversion" && (
        <div className="max-w-xl mx-auto space-y-5">
          <div className="text-center">
            <p className="text-sm text-slate-400">{t("generateurs.convertSubtitle")}<br />{t("generateurs.convertSubtitle2")}</p>
          </div>
          <form onSubmit={handleConvertir} className="space-y-4">
            {/* Zone dépôt */}
            <div
              onClick={() => fileConvRef.current?.click()}
              className={`flex flex-col items-center justify-center gap-3 p-8 rounded-2xl border-2 border-dashed cursor-pointer transition-all ${
                fichierConv ? "border-yukpo-500/50 bg-yukpo-500/5" : "border-slate-600 hover:border-slate-500"
              }`}
              style={!fichierConv ? { background: "var(--ykp-surface)" } : {}}
            >
              <RefreshCw className={`w-8 h-8 ${fichierConv ? "text-yukpo-400" : "text-slate-500"}`} />
              {fichierConv ? (
                <div className="text-center">
                  <p className="text-sm font-medium text-white">{fichierConv.name}</p>
                  <p className="text-xs text-slate-400 mt-1">{(fichierConv.size / 1024).toFixed(0)} Ko — {CONVERSIONS_MAP[extConv]?.label ?? extConv.toUpperCase()}</p>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-300">{t("generateurs.dropFileHere")}</p>
                  <p className="text-xs text-slate-500 mt-1">PDF, DOCX, PPTX, XLSX, CSV, TXT, JPG, PNG</p>
                </div>
              )}
              <input
                ref={fileConvRef}
                type="file"
                className="hidden"
                accept=".pdf,.docx,.doc,.pptx,.xlsx,.xls,.csv,.txt,.md,.jpg,.jpeg,.png"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setFichierConv(f);
                  setResultatConv(null);
                  if (f) {
                    const ext = `.${f.name.split(".").pop()!.toLowerCase()}`;
                    const cibles = CONVERSIONS_MAP[ext]?.cibles ?? [];
                    if (cibles.length > 0) setFormatCible(cibles[0].value);
                  }
                }}
              />
            </div>

            {fichierConv && (
              <>
                <Select
                  label={t('generateurs.convertTo')}
                  options={ciblsDispos}
                  value={formatCible}
                  onChange={(e) => setFormatCible(e.target.value)}
                />
                <Button type="submit" loading={loadingConv} icon={<RefreshCw className="w-4 h-4" />} className="w-full">
                  {t("generateurs.convertCta")}
                </Button>
              </>
            )}
          </form>

          {loadingConv && (
            <Card className="p-5 flex items-center gap-4">
              <Loader className="w-5 h-5 text-yukpo-400 animate-spin" />
              <p className="text-sm text-white">{t("generateurs.converting")}</p>
            </Card>
          )}

          {!loadingConv && resultatConv && (
            <Card className="p-5 space-y-3 animate-fade-in">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <span className="text-sm font-semibold text-white">
                  {resultatConv.format_source.toUpperCase()} → {resultatConv.format_cible.replace(".", "").toUpperCase()} — {t("generateurs.conversionSuccess")}
                </span>
              </div>
              <a
                href={generateurApi.telecharger(resultatConv.fichier_converti)}
                download={resultatConv.fichier_converti}
                className="flex items-center gap-3 p-4 bg-blue-50 dark:bg-yukpo-500/20 border border-blue-200 dark:border-yukpo-500/40 rounded-xl hover:bg-blue-100 dark:hover:bg-yukpo-500/30 transition-colors group"
              >
                <Download className="w-5 h-5 shrink-0 text-blue-600 dark:text-yukpo-400" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{resultatConv.fichier_converti}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Cliquer pour télécharger</p>
                </div>
              </a>
              <button
                type="button"
                onClick={() => { setFichierConv(null); setResultatConv(null); }}
                className="text-xs text-slate-400 hover:text-white underline"
              >
                {t("generateurs.convertAnother")}
              </button>
            </Card>
          )}
        </div>
      )}

      {/* ── Tab Designer Pro ────────────────────────────────────────────────── */}
      {tab === "infographie" && (
        <div className="space-y-4">
          {/* Sélecteur mono-page / multi-page */}
          <div className="flex gap-1 bg-gray-100 border border-gray-200 p-1 rounded-xl w-fit">
            {([
              { id: "multipages", label: `✨ ${t("generateurs.designerMultiPage")}`, desc: t("generateurs.designerMultiPageDesc") },
              { id: "monopages",  label: `🖨️ ${t("generateurs.designerMonoPage")}`,    desc: t("generateurs.designerMonoPageDesc") },
            ] as const).map(m => (
              <button key={m.id} onClick={() => setInfogDesignerMode(m.id)}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                  infogDesignerMode === m.id
                    ? "bg-white shadow-sm border border-gray-200 text-amber-700"
                    : "text-gray-800 hover:text-gray-900"
                }`}
                title={m.desc}>
                {m.label}
              </button>
            ))}
          </div>

          {infogDesignerMode === "multipages" ? (
            <DesignerProPanel />
          ) : (
          <div className="space-y-4">
          {/* Étape 1 : choix du sous-mode */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {([
              { id: "brief",  icon: <Wand2 className="w-4 h-4" />,      label: t("generateurs.subModeBrief"),  desc: t("generateurs.subModeBriefDesc") },
              { id: "manuel", icon: <Settings2 className="w-4 h-4" />,  label: t("generateurs.subModeManuel"), desc: t("generateurs.subModeManuelDesc") },
              { id: "modele", icon: <FileImage className="w-4 h-4" />,  label: t("generateurs.subModeModele"), desc: t("generateurs.subModeModeleDesc") },
              { id: "custom", icon: <Maximize2 className="w-4 h-4" />,  label: t("generateurs.subModeCustom"), desc: t("generateurs.subModeCustomDesc") },
            ] as const).map(({ id, icon, label, desc }) => (
              <button key={id} type="button" onClick={() => { setInfogMode(id); setInfogResult(null); }}
                className={`flex flex-col items-start gap-1 p-3 rounded-xl border transition-all text-left ${
                  infogMode === id
                    ? "border-corp-500"
                    : "hover:border-slate-600"
                }`}
                style={infogMode === id
                  ? { background: "rgba(0,84,166,0.12)", border: "1px solid #0054A6", color: "var(--ykp-text-primary)" }
                  : { background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)", color: "var(--ykp-text-secondary)" }}>
                <span className="flex items-center gap-2 text-sm font-semibold">{icon} {label}</span>
                <span className="text-[11px] text-slate-500">{desc}</span>
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
            {/* Formulaire — 3 colonnes */}
            <form onSubmit={handleGenererInfographie} className="space-y-3 lg:col-span-3">
              {/* Étape 2 : sélection du gabarit (sauf custom) */}
              {infogMode !== "custom" && (
                <div>
                  <label className="text-xs font-semibold text-slate-400 mb-1.5 block">
                    {t("generateurs.gabaritLabel", { count: infogGabarits.length })}
                  </label>
                  <select value={infogGabarit} onChange={e => setInfogGabarit(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500">
                    {Object.entries(gabaritsParCategorie).map(([cat, items]) => (
                      <optgroup key={cat} label={cat.toUpperCase()}>
                        {items.map(g => (
                          <option key={g.cle} value={g.cle}>
                            {g.label} — {g.width_mm}×{g.height_mm}mm — {g.prix_fcfa.toLocaleString("fr-FR")} {t("generateurs.credits")}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  {gabaritCourant && (
                    <p className="text-[11px] text-slate-500 mt-1">{gabaritCourant.description} · {t("generateurs.gabaritBleed", { mm: gabaritCourant.bleed_mm })}</p>
                  )}
                </div>
              )}

              {/* Mode CUSTOM : dimensions */}
              {infogMode === "custom" && (
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-xs font-semibold text-slate-400 mb-1 block">{t("generateurs.widthMm")}</label>
                    <input type="number" min={10} max={3000} value={infogW} onChange={e => setInfogW(Number(e.target.value))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-400 mb-1 block">{t("generateurs.heightMm")}</label>
                    <input type="number" min={10} max={3000} value={infogH} onChange={e => setInfogH(Number(e.target.value))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-400 mb-1 block">{t("generateurs.bleedMm")}</label>
                    <input type="number" min={0} max={20} value={infogBleed} onChange={e => setInfogBleed(Number(e.target.value))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500" />
                  </div>
                </div>
              )}

              {/* Mode MODÈLE : upload */}
              {infogMode === "modele" && (
                <div>
                  <label className="text-xs font-semibold text-slate-400 mb-1.5 block">{t("generateurs.modelImageLabel")}</label>
                  <input ref={infogModeleRef} type="file" accept="image/png,image/jpeg,image/jpg,image/webp"
                    onChange={e => setInfogModele(e.target.files?.[0] || null)} className="hidden" />
                  <button type="button" onClick={() => infogModeleRef.current?.click()}
                    className="w-full flex items-center gap-2 px-3 py-2 border border-dashed border-slate-700 hover:border-yukpo-500 rounded-lg text-sm text-slate-400 hover:text-white transition-all">
                    <Upload className="w-4 h-4" />
                    {infogModele ? `${infogModele.name} (${(infogModele.size / 1024).toFixed(0)} Ko)` : t("generateurs.uploadModelVisual")}
                  </button>
                </div>
              )}

              {/* Étape 3 : champs spécifiques au mode */}
              {(infogMode === "brief" || infogMode === "modele" || infogMode === "custom") && (
                <div>
                  <label className="text-xs font-semibold text-slate-400 mb-1.5 block">{t("generateurs.creativeBrief")}</label>
                  <textarea value={infogBrief} onChange={e => setInfogBrief(e.target.value)} rows={5} required
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500 resize-none"
                    placeholder={t('generateurs.briefPlaceholder')} />
                </div>
              )}

              {infogMode === "manuel" && (
                <>
                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="col-span-2">
                      <label className="text-xs font-semibold text-slate-400 mb-1 block">{t("generateurs.mainTitle")}</label>
                      <input value={infogTitre} onChange={e => setInfogTitre(e.target.value)} required maxLength={60}
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500" />
                    </div>
                    <input value={infogSousTitre} onChange={e => setInfogSousTitre(e.target.value)} maxLength={80}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder={t('generateurs.infogSubtitlePlaceholder')} />
                    <select value={infogPalette} onChange={e => setInfogPalette(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500">
                      {infogPalettes.map(p => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
                    </select>
                    <input value={infogOrg} onChange={e => setInfogOrg(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder={t('generateurs.infogOrgPlaceholder')} />
                    <input value={infogContact} onChange={e => setInfogContact(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder={t('generateurs.infogContactPlaceholder')} />
                    <input value={infogDate} onChange={e => setInfogDate(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder={t('generateurs.infogDatePlaceholder')} />
                    <input value={infogLieu} onChange={e => setInfogLieu(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder={t('generateurs.infogLieuPlaceholder')} />
                    <input value={infogSlogan} onChange={e => setInfogSlogan(e.target.value)}
                      className="col-span-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder={t('generateurs.infogSloganPlaceholder')} />
                  </div>
                  <textarea value={infogCorps} onChange={e => setInfogCorps(e.target.value)} rows={2} maxLength={300}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500 resize-none"
                    placeholder={t('generateurs.infogCorpsPlaceholder')} />
                  <textarea value={infogDetails} onChange={e => setInfogDetails(e.target.value)} rows={3}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500 resize-none"
                    placeholder={t('generateurs.infogDetailsPlaceholder')} />
                </>
              )}

              {/* Pays cible (sauf manuel) */}
              {infogMode !== "manuel" && (
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="text-xs font-semibold text-slate-400 mb-1 block">{t("generateurs.targetCountry")}</label>
                    <select value={infogPays} onChange={e => setInfogPays(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500">
                      <option value="CM">Cameroun</option>
                      <option value="CI">Côte d'Ivoire</option>
                      <option value="SN">Sénégal</option>
                      <option value="TG">Togo</option>
                      <option value="BJ">Bénin</option>
                      <option value="BF">Burkina Faso</option>
                      <option value="GA">Gabon</option>
                      <option value="ML">Mali</option>
                      <option value="NE">Niger</option>
                      <option value="GN">Guinée</option>
                      <option value="CG">Congo</option>
                      <option value="CD">RDC</option>
                      <option value="TD">Tchad</option>
                    </select>
                  </div>
                </div>
              )}

              {/* Boutons générer (1 visuel ou 4 variantes en parallèle) */}
              <div className="flex flex-col sm:flex-row gap-2">
                <button type="submit" disabled={infogLoading}
                  className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-corp-600 to-corp-500 hover:from-corp-700 hover:to-corp-600 disabled:opacity-50 text-white font-semibold rounded-xl transition-all text-sm">
                  {infogLoading
                    ? <><Loader className="w-4 h-4 animate-spin" /> {t("generateurs.infogComposing")}</>
                    : <><Sparkles className="w-4 h-4" /> {t("generateurs.infogOneVisual")}</>}
                </button>
                {infogMode === "brief" && (
                  <button type="button" onClick={handleGenererVariantes} disabled={infogLoading}
                    className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-pink-500/20 hover:bg-pink-500/30 disabled:opacity-50 text-pink-200 font-semibold rounded-xl transition-all text-sm border border-pink-500/30"
                    title={t("generateurs.infogFourVariants")}>
                    <Wand2 className="w-4 h-4" /> {t("generateurs.infogFourVariants")}
                  </button>
                )}
              </div>
              <p className="text-[11px] text-slate-500 text-center">{t("generateurs.infogFooter")}</p>
            </form>

            {/* Aperçu — 2 colonnes */}
            <div className="lg:col-span-2 flex flex-col gap-4">
              {/* Galerie variantes IA (si générées) */}
              {infogVariantes && infogVariantes.length > 1 && (
                <Card className="p-3">
                  <p className="text-xs font-semibold text-white mb-2 flex items-center gap-1.5">
                    <Wand2 className="w-3.5 h-3.5 text-pink-400" /> {(infogVariantes?.length ?? 4)} {t("generateurs.infogVariantsTitle")}
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {infogVariantes.map((v, idx) => {
                      const actif = infogResult?.pdf_id === v.resultat?.pdf_id;
                      return (
                        <button key={idx} type="button"
                          onClick={() => setInfogResult(v.resultat)}
                          className={`relative rounded-lg overflow-hidden border-2 transition-all ${actif ? "border-pink-400 ring-2 ring-pink-400/40" : "border-slate-700/60 hover:border-slate-500"}`}
                          title={v.direction}>
                          {v.resultat?.png_base64 ? (
                            <img src={`data:image/png;base64,${v.resultat.png_base64}`} alt={v.direction}
                              className="w-full h-32 object-contain bg-white" />
                          ) : (
                            <div className="w-full h-32 bg-slate-800 flex items-center justify-center text-xs text-slate-500">
                              {v.direction}
                            </div>
                          )}
                          <div className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[10px] px-1.5 py-0.5 capitalize">
                            {v.direction}{actif && " ✓"}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </Card>
              )}
              {infogResult ? (
                <Card className="p-4 flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-white flex items-center gap-2">
                      <ImageIcon className="w-4 h-4 text-pink-400" /> {t("generateurs.preview").replace(/[ :]+$/, "")}
                    </span>
                    <div className="flex gap-2 flex-wrap justify-end">
                      {infogResult.png_id && (
                        <button type="button" onClick={() => setInfogZoom(true)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/50 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-all">
                          <Maximize2 className="w-3.5 h-3.5" /> {t("generateurs.zoom")}
                        </button>
                      )}
                      {infogResult.pdf_id && (
                        <button type="button" onClick={() => handleTelechargerInfog("pdf")}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-yukpo-500/20 hover:bg-yukpo-500/30 text-yukpo-300 rounded-lg text-xs font-medium transition-all">
                          <Download className="w-3.5 h-3.5" /> {t("generateurs.infogPdfRgb")}
                        </button>
                      )}
                      {infogResult.pdf_cmyk_id && (
                        <button type="button" onClick={() => handleTelechargerInfog("pdf_cmyk")}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 rounded-lg text-xs font-medium transition-all"
                          title={t("generateurs.infogPdfCmykTitle")}>
                          <Download className="w-3.5 h-3.5" /> {t("generateurs.infogPdfCmyk")}
                        </button>
                      )}
                      {infogResult.svg_id && (
                        <button type="button" onClick={() => handleTelechargerInfog("svg")}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 rounded-lg text-xs font-medium transition-all"
                          title={t("generateurs.infogSvgTitle")}>
                          <Download className="w-3.5 h-3.5" /> {t("generateurs.infogSvg")}
                        </button>
                      )}
                      {infogResult.png_id && (
                        <button type="button" onClick={() => handleTelechargerInfog("png_hd")}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/50 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-all"
                          title="PNG 300 dpi">
                          <Download className="w-3.5 h-3.5" /> {t("generateurs.infogPngHd")}
                        </button>
                      )}
                    </div>
                  </div>
                  {infogResult.png_base64 ? (
                    <img src={`data:image/png;base64,${infogResult.png_base64}`} alt="Aperçu infographie"
                      className="w-full rounded-xl border border-white/10 object-contain max-h-[520px] bg-white" />
                  ) : (
                    <div className="flex flex-col items-center justify-center gap-2 p-8 rounded-xl text-slate-400 text-sm" style={{ background: "var(--ykp-elevated)" }}>
                      <FileText className="w-8 h-8" />
                      {t("generateurs.previewPngUnavailable")}
                    </div>
                  )}
                  {infogResult.specification && (
                    <div className="text-xs text-slate-400 space-y-1 border-t border-slate-700/60 pt-2">
                      <p><span className="text-slate-500">{t("generateurs.specTitle")}</span> {infogResult.specification.titre}</p>
                      {infogResult.specification.palette && (
                        <p><span className="text-slate-500">{t("generateurs.specPalette")}</span> {infogResult.specification.palette}</p>
                      )}
                      {typeof infogResult.prix_fcfa === "number" && infogResult.prix_fcfa > 0 && (
                        <p><span className="text-slate-500">{t("generateurs.indicativePrintPrice")}</span> {formatAmount(infogResult.prix_fcfa, infogPays)}</p>
                      )}
                    </div>
                  )}
                  <span className="flex items-center gap-1.5 text-[11px] text-green-400">
                    <Save className="w-3 h-3" /> {t("generateurs.savedToDocs")}
                  </span>

                  {/* Retouche IA — instructions libres pour modifier le visuel */}
                  <div className="border-t border-slate-700/60 pt-3 mt-1 flex flex-col gap-2">
                    <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                      <Wand2 className="w-3.5 h-3.5 text-pink-400" /> {t("generateurs.infogRetouchTitle")}
                    </span>
                    <Textarea
                      value={infogRetoucheInstr}
                      onChange={e => setInfogRetoucheInstr(e.target.value)}
                      placeholder={t("generateurs.infogRetouchPlaceholder")}
                      rows={2}
                    />
                    <Button type="button" onClick={handleRetoucher} disabled={infogLoading || !infogRetoucheInstr.trim()} variant="secondary" className="self-end text-xs">
                      {infogLoading ? <><Loader className="w-3.5 h-3.5 animate-spin" /> {t("generateurs.infogRetouching")}</> : <><Sparkles className="w-3.5 h-3.5" /> {t("generateurs.infogRetouchApply")}</>}
                    </Button>
                  </div>
                </Card>
              ) : (
                <Card className="flex flex-col items-center justify-center gap-4 p-12 border-dashed min-h-[400px]">
                  <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-corp-600/15 to-bright-400/10 flex items-center justify-center">
                    <Palette className="w-8 h-8 text-purple-400" />
                  </div>
                  <div className="text-center">
                    <p className="text-white font-semibold mb-1">{t("generateurs.infogProTitle")}</p>
                    <p className="text-slate-500 text-sm">{t("generateurs.infogProDesc")}<br />{t("generateurs.infogProDesc2")}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 justify-center max-w-sm">
                    {["Flyer A5", "Carte visite", "Diplôme", "Roll-up", "Insta Post", "Affiche A2"].map(t => (
                      <span key={t} className="px-2.5 py-1 bg-slate-800 rounded-full text-xs text-slate-400">{t}</span>
                    ))}
                  </div>
                </Card>
              )}
            </div>
          </div>

          {/* Modal zoom PNG */}
          {infogZoom && infogResult?.png_base64 && (
            <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur flex items-center justify-center p-4" onClick={() => setInfogZoom(false)}>
              <div className="relative max-w-5xl max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
                <button onClick={() => setInfogZoom(false)}
                  className="absolute top-2 right-2 z-10 p-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-white">
                  <X className="w-4 h-4" />
                </button>
                <img src={`data:image/png;base64,${infogResult.png_base64}`} alt="Aperçu zoom"
                  className="rounded-xl bg-white" />
              </div>
            </div>
          )}
        </div>
          )}
        </div>
      )}

      <div className={`grid grid-cols-1 lg:grid-cols-5 gap-6 items-start ${tab === "modeles" || tab === "conversion" || tab === "infographie" ? "hidden" : ""}`}>
        {/* Form */}
        <div className="lg:col-span-3 space-y-4">
          {tab === "rapport" ? (
            <form onSubmit={handleGenererRapport} className="space-y-3">
              <Textarea
                label={t('generateurs.subjectRapport')}
                placeholder={t('generateurs.subjectRapportPlaceholder')}
                value={sujetRapport}
                onChange={(e) => setSujetRapport(e.target.value)}
                rows={2}
              />
              <div className="grid grid-cols-2 gap-3">
                <Select label={t('generateurs.typeRapport')} options={TYPES_RAPPORT_VALUES.map(v => ({ value: v, label: t(`generateurs.lists.typeRapport.${v}`) }))} value={typeRapport} onChange={(e) => setTypeRapport(e.target.value)} />
                <Select label={t('generateurs.mode')} options={MODES_RAPPORT_VALUES.map(v => ({ value: v, label: t(`generateurs.lists.modeRapport.${v}`) }))} value={modeRapport} onChange={(e) => setModeRapport(e.target.value)} />
              </div>
              <Textarea
                label={t('generateurs.contextExtra')}
                placeholder={t('generateurs.contextExtraPlaceholder')}
                value={contexteRapport}
                onChange={(e) => setContexteRapport(e.target.value)}
                rows={3}
              />
              {/* Zone fichiers intégrée */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-slate-400">
                    {t("generateurs.filesAnalysis")} <span className="text-slate-600 font-normal">{t("generateurs.filesAnalysisHint")}</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => fileRapportRef.current?.click()}
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors"
                  >
                    <Upload className="w-3.5 h-3.5" /> {t("generateurs.addFiles")}
                  </button>
                  <input
                    ref={fileRapportRef}
                    type="file"
                    multiple
                    accept={EXTENSIONS_ACCEPTEES}
                    className="hidden"
                    onChange={(e) => {
                      const nouv = Array.from(e.target.files || []);
                      setFichiersRapport(prev => {
                        const noms = new Set(prev.map(f => f.name));
                        return [...prev, ...nouv.filter(f => !noms.has(f.name))];
                      });
                      e.target.value = "";
                    }}
                  />
                </div>
                {fichiersRapport.length > 0 && (
                  <div className="space-y-1 max-h-24 overflow-y-auto">
                    {fichiersRapport.map((f, i) => (
                      <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 bg-slate-800 rounded-lg border border-yukpo-500/30">
                        <FileText className="w-3 h-3 text-yukpo-400 shrink-0" />
                        <span className="text-xs text-slate-300 flex-1 truncate">{f.name}</span>
                        <span className="text-xs text-slate-500">{(f.size / 1024).toFixed(0)} Ko</span>
                        <button type="button" onClick={() => setFichiersRapport(prev => prev.filter((_, j) => j !== i))} className="text-slate-500 hover:text-red-400">
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {fichiersRapport.length > 0 && (
                  <p className="text-xs text-yukpo-400 mt-1.5 flex items-center gap-1">
                    <Sparkles className="w-3 h-3" />
                    {t("generateurs.filesEnrichReport")}
                  </p>
                )}
              </div>
              <div className="flex gap-3 items-center">
                {fichiersRapport.length === 0 && (
                  <div className="flex gap-2">
                    {["docx", "pdf", "markdown"].map((fmt) => (
                      <label key={fmt} className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer text-sm transition-colors ${
                        formatRapport === fmt ? "border-yukpo-500 bg-yukpo-500/10 text-yukpo-300" : "border-slate-600 text-slate-400 hover:border-slate-500"
                      }`}>
                        <input type="radio" name="fmt-r" value={fmt} checked={formatRapport === fmt} onChange={() => setFormatRapport(fmt)} className="hidden" />
                        {fmt.toUpperCase()}
                      </label>
                    ))}
                  </div>
                )}
                <Button type="submit" loading={loading} icon={<FileText className="w-4 h-4" />}>
                  {fichiersRapport.length > 0 ? t('generateurs.generateWithFiles', { count: fichiersRapport.length, plural: fichiersRapport.length > 1 ? "s" : "" }) : t('generateurs.generateReport')}
                </Button>
              </div>
            </form>
          ) : (
            <form onSubmit={handleGenererSlides} className="space-y-3">
              <Textarea
                label={t('generateurs.subjectSlides')}
                placeholder={t('generateurs.subjectSlidesPlaceholder')}
                value={sujetSlides}
                onChange={(e) => setSujetSlides(e.target.value)}
                rows={2}
              />
              <div className="grid grid-cols-2 gap-3">
                <Select label={t('generateurs.typeSlides')} options={TYPES_SLIDES_VALUES.map(v => ({ value: v, label: t(`generateurs.lists.typeSlides.${v}`) }))} value={typeSlides} onChange={(e) => setTypeSlides(e.target.value)} />
                <Select label={t('generateurs.mode')} options={MODES_SLIDES_VALUES.map(v => ({ value: v, label: t(`generateurs.lists.modeSlides.${v}`) }))} value={modeSlides} onChange={(e) => setModeSlides(e.target.value)} />
              </div>
              <Textarea
                label={t('generateurs.contextData')}
                placeholder={t('generateurs.contextDataPlaceholder')}
                value={contexteSlides}
                onChange={(e) => setContexteSlides(e.target.value)}
                rows={3}
              />
              {/* Zone fichiers intégrée */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-slate-400">
                    {t("generateurs.filesAnalysis")} <span className="text-slate-600 font-normal">{t("generateurs.filesAnalysisHintSlides")}</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => fileSlidesRef.current?.click()}
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors"
                  >
                    <Upload className="w-3.5 h-3.5" /> {t("generateurs.addFiles")}
                  </button>
                  <input
                    ref={fileSlidesRef}
                    type="file"
                    multiple
                    accept={EXTENSIONS_ACCEPTEES}
                    className="hidden"
                    onChange={(e) => {
                      const nouv = Array.from(e.target.files || []);
                      setFichiersSlides(prev => {
                        const noms = new Set(prev.map(f => f.name));
                        return [...prev, ...nouv.filter(f => !noms.has(f.name))];
                      });
                      e.target.value = "";
                    }}
                  />
                </div>
                {fichiersSlides.length > 0 && (
                  <div className="space-y-1 max-h-24 overflow-y-auto">
                    {fichiersSlides.map((f, i) => (
                      <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 bg-slate-800 rounded-lg border border-yukpo-500/30">
                        <FileText className="w-3 h-3 text-yukpo-400 shrink-0" />
                        <span className="text-xs text-slate-300 flex-1 truncate">{f.name}</span>
                        <span className="text-xs text-slate-500">{(f.size / 1024).toFixed(0)} Ko</span>
                        <button type="button" onClick={() => setFichiersSlides(prev => prev.filter((_, j) => j !== i))} className="text-slate-500 hover:text-red-400">
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {fichiersSlides.length > 0 && (
                  <p className="text-xs text-yukpo-400 mt-1.5 flex items-center gap-1">
                    <Sparkles className="w-3 h-3" />
                    {t("generateurs.filesEnrichSlides")}
                  </p>
                )}
              </div>
              <div className="flex gap-3 items-center">
                {fichiersSlides.length === 0 && (
                  <div className="flex gap-2">
                    {["pptx", "pdf", "markdown"].map((fmt) => (
                      <label key={fmt} className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer text-sm transition-colors ${
                        formatSlides === fmt ? "border-yukpo-500 bg-yukpo-500/10 text-yukpo-300" : "border-slate-600 text-slate-400 hover:border-slate-500"
                      }`}>
                        <input type="radio" name="fmt-s" value={fmt} checked={formatSlides === fmt} onChange={() => setFormatSlides(fmt)} className="hidden" />
                        {fmt.toUpperCase()}
                      </label>
                    ))}
                  </div>
                )}
                <Button type="submit" loading={loading} icon={<Presentation className="w-4 h-4" />}>
                  {fichiersSlides.length > 0 ? t('generateurs.generateWithFiles', { count: fichiersSlides.length, plural: fichiersSlides.length > 1 ? "s" : "" }) : t('generateurs.generateSlides')}
                </Button>
              </div>
            </form>
          )}
        </div>

        {/* Résultat */}
        <div className="lg:col-span-2 lg:sticky lg:top-6">
          {loading ? (
            <Card className="p-8 flex flex-col items-center justify-center gap-4 h-full min-h-48">
              <Loader className="w-8 h-8 text-yukpo-400 animate-spin" />
              <div className="text-center">
                <p className="text-white font-medium text-sm">{t("generateurs.writingDocument")}</p>
                <p className="text-slate-400 text-xs mt-1">{t("generateurs.writingDocumentHelper")}</p>
              </div>
            </Card>
          ) : resultat ? (
            <Card className="p-5 space-y-4 animate-fade-in">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <span className="text-sm font-semibold text-white">{t("generateurs.documentReady")}</span>
              </div>

              {/* Téléchargement */}
              {resultat.fichier && (
                <a
                  href={generateurApi.telecharger(resultat.fichier)}
                  download={resultat.fichier}
                  className="flex items-center gap-3 p-4 bg-blue-50 dark:bg-yukpo-500/20 border border-blue-200 dark:border-yukpo-500/40 rounded-xl hover:bg-blue-100 dark:hover:bg-yukpo-500/30 transition-colors group"
                >
                  <Download className="w-5 h-5 shrink-0 text-blue-600 dark:text-yukpo-400" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{resultat.fichier}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("generateurs.clickToDownload")}</p>
                  </div>
                </a>
              )}

              {/* Aperçu Markdown */}
              {resultat.markdown && (
                <div className="max-h-80 overflow-y-auto">
                  <p className="text-xs text-slate-500 mb-2">{t("generateurs.preview")}</p>
                  <div className="p-3 bg-slate-100 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 text-xs">
                    <ReactMarkdown className="prose prose-sm prose-invert max-w-none">
                      {resultat.markdown.slice(0, 2000)}
                    </ReactMarkdown>
                    {(resultat.markdown.length || 0) > 2000 && (
                      <p className="text-slate-500 mt-2">{t("generateurs.previewTruncated")}</p>
                    )}
                  </div>
                </div>
              )}
            </Card>
          ) : (
            <Card className="p-8 flex flex-col items-center justify-center gap-3 h-full min-h-48 border-dashed">
              {tab === "rapport" ? <FileText className="w-12 h-12 text-slate-600" /> : <Presentation className="w-12 h-12 text-slate-600" />}
              <p className="text-slate-500 text-sm text-center">
                {tab === "rapport"
                  ? t("generateurs.rapportPlaceholder")
                  : t("generateurs.slidesPlaceholder")}
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

