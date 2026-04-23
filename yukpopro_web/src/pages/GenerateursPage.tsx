import { useState, FormEvent, useRef, DragEvent, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, Presentation, Download, CheckCircle, Loader, BookOpen, ArrowRight, Upload, X, FolderOpen, RefreshCw, Palette, Sparkles, Image as ImageIcon, Save, ChevronDown, Wand2, Settings2, FileImage, Maximize2 } from "lucide-react";
import toast from "react-hot-toast";
import ReactMarkdown from "react-markdown";
import { Card, Button, Textarea, Badge, Select } from "@/components/ui";
import { DemoBanner } from "@/components/DemoBanner";
import { generateurApi, infographieApi, GabaritInfographie, ResultatInfographieReponse } from "@/api/client";
import { useGenerateurStore } from "@/store/generateurStore";

type Tab = "rapport" | "slides" | "modeles" | "conversion" | "infographie";
type InfogMode = "brief" | "manuel" | "modele" | "custom";

interface Template {
  label: string;
  description: string;
  type: "rapport" | "slides";
  typeDoc: string;
  mode: string;
  sujet: string;
  contexte: string;
}

interface CategorieTemplates {
  categorie: string;
  emoji: string;
  templates: Template[];
}

const TEMPLATES_PAR_METIER: CategorieTemplates[] = [
  {
    categorie: "Comptabilité & Finance",
    emoji: "🧮",
    templates: [
      {
        label: "Bilan SYSCOHADA commenté",
        description: "Bilan annuel avec analyse des ratios clés (liquidité, solvabilité, rentabilité)",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "complet",
        sujet: "Bilan comptable SYSCOHADA annoté avec analyse financière",
        contexte: "Préparer un bilan SYSCOHADA révisé avec ratios clés : liquidité générale, solvabilité, rentabilité des capitaux propres. Inclure tableau de flux de trésorerie et notes explicatives.",
      },
      {
        label: "Note de calcul IS + TVA",
        description: "Calcul détaillé de l'Impôt sur les Sociétés et de la TVA collectée/déductible",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "standard",
        sujet: "Note de calcul IS et TVA — exercice fiscal",
        contexte: "Calcul de l'IS selon le régime applicable (taux normal, minimum de perception) et réconciliation TVA (collectée, déductible, solde à décaisser). Référencer le CGI applicable.",
      },
      {
        label: "Rapport d'audit interne",
        description: "Rapport d'audit des procédures comptables et points de contrôle interne",
        type: "rapport",
        typeDoc: "rapport_audit",
        mode: "complet",
        sujet: "Rapport d'audit interne des procédures comptables et financières",
        contexte: "Évaluation du contrôle interne, identification des risques (fraude, erreurs, non-conformités), recommandations correctives avec plan d'action priorisé.",
      },
      {
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
    categorie: "Juridique & Conformité",
    emoji: "⚖️",
    templates: [
      {
        label: "Note juridique OHADA",
        description: "Analyse d'une problématique juridique selon le droit OHADA",
        type: "rapport",
        typeDoc: "note_juridique",
        mode: "standard",
        sujet: "Note juridique — analyse de conformité OHADA",
        contexte: "Analyse des actes uniformes OHADA applicables, jurisprudence CCJA, risques juridiques identifiés et recommandations pratiques.",
      },
      {
        label: "Rapport de due diligence",
        description: "Due diligence juridique et financière pour acquisition ou partenariat",
        type: "rapport",
        typeDoc: "rapport_audit",
        mode: "complet",
        sujet: "Rapport de due diligence — acquisition / partenariat stratégique",
        contexte: "Audit juridique (statuts, contrats, litiges), fiscal (arriérés, redressements), social (CNPS, contrats de travail), immobilier. Synthèse risques et recommandations.",
      },
      {
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
    categorie: "RH & Management",
    emoji: "👥",
    templates: [
      {
        label: "Rapport bilan social",
        description: "Bilan social annuel — effectifs, rémunérations, formation, absentéisme",
        type: "rapport",
        typeDoc: "rapport_rh",
        mode: "complet",
        sujet: "Bilan social annuel — indicateurs RH et analyse",
        contexte: "Effectifs (pyramide des âges, turn-over), rémunérations (masse salariale, SMIG comparé), formation (plan, coûts, taux de réalisation), absentéisme, conformité Code du travail.",
      },
      {
        label: "Plan de restructuration RH",
        description: "Note de restructuration des effectifs avec plan social",
        type: "rapport",
        typeDoc: "plan_action",
        mode: "standard",
        sujet: "Plan de restructuration des effectifs et plan social",
        contexte: "Justification économique, critères de sélection, mesures d'accompagnement (indemnités légales selon Code du travail, outplacement), calendrier de mise en œuvre.",
      },
      {
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
    categorie: "Banque & Microfinance",
    emoji: "🏦",
    templates: [
      {
        label: "Rapport analyse crédit PME",
        description: "Analyse de risque crédit pour une PME — scoring et décision",
        type: "rapport",
        typeDoc: "rapport_financier",
        mode: "standard",
        sujet: "Analyse crédit PME — dossier de financement",
        contexte: "Analyse des états financiers SYSCOHADA, scoring crédit, ratios COBAC (endettement, couverture), garanties proposées, recommandation d'octroi avec conditions.",
      },
      {
        label: "Note ratios prudentiels COBAC",
        description: "Calcul et commentaire des ratios prudentiels COBAC",
        type: "rapport",
        typeDoc: "note_de_synthese",
        mode: "standard",
        sujet: "Note d'analyse des ratios prudentiels COBAC",
        contexte: "Calcul des ratios COBAC : solvabilité (8%), liquidité (≥100%), transformation, division des risques. Comparaison vs normes réglementaires et plan d'action correctif si nécessaire.",
      },
      {
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
    categorie: "Commerce & Business",
    emoji: "📈",
    templates: [
      {
        label: "Business plan complet",
        description: "Business plan structuré pour création ou développement d'activité",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Business plan — création / développement d'activité",
        contexte: "Executive summary, étude de marché (PESTEL, Porter), modèle économique (BMC), plan marketing, plan opérationnel, projections financières sur 3 ans (P&L, BFR, TRI).",
      },
      {
        label: "Rapport analyse de marché",
        description: "Étude de marché sectorielle pour un pays d'Afrique subsaharienne",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Analyse de marché sectorielle — Afrique subsaharienne",
        contexte: "Taille du marché, acteurs clés, parts de marché, tendances, barrières à l'entrée, opportunités, menaces concurrentielles, recommandations de positionnement.",
      },
      {
        label: "Pitch deck investisseurs",
        description: "Présentation de levée de fonds pour investisseurs africains / internationaux",
        type: "slides",
        typeDoc: "pitch_projet",
        mode: "pitch",
        sujet: "Pitch deck — levée de fonds startup / PME",
        contexte: "Problème / Solution, taille du marché, traction (métriques clés), modèle économique, roadmap, équipe, besoins de financement, utilisation des fonds, exit potentiel.",
      },
      {
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
    categorie: "ONG & Projets",
    emoji: "🌍",
    templates: [
      {
        label: "Rapport d'activités ONG",
        description: "Rapport annuel d'activités pour bailleurs et partenaires",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport annuel d'activités — organisation",
        contexte: "Résumé exécutif, réalisations par axe stratégique, indicateurs d'impact atteints vs cibles, utilisation des ressources financières, leçons apprises, perspectives.",
      },
      {
        label: "Note conceptuelle projet",
        description: "Note conceptuelle pour soumission à un appel à projets / bailleur",
        type: "rapport",
        typeDoc: "note_de_synthese",
        mode: "standard",
        sujet: "Note conceptuelle — proposition de projet",
        contexte: "Contexte et justification, objectifs (général et spécifiques), bénéficiaires, approche et méthodologie, résultats attendus, cadre logique simplifié, budget indicatif.",
      },
      {
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
    categorie: "Ingénierie & BTP",
    emoji: "🏗️",
    templates: [
      {
        label: "Rapport d'avancement travaux",
        description: "Rapport mensuel d'avancement d'un chantier",
        type: "rapport",
        typeDoc: "compte_rendu",
        mode: "standard",
        sujet: "Rapport d'avancement mensuel — chantier de construction",
        contexte: "Avancement physique par lot, planning prévisionnel vs réel, décompte financier, ressources mobilisées, réserves / non-conformités, plan d'actions, photos commentées.",
      },
      {
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
    categorie: "Santé Publique & Épidémiologie",
    emoji: "🏥",
    templates: [
      {
        label: "Rapport de situation épidémiologique",
        description: "Rapport de situation épidémio hebdomadaire ou mensuel",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "standard",
        sujet: "Rapport de situation épidémiologique — analyse et recommandations",
        contexte: "Description de la situation (cas confirmés, incidence, létalité), analyse par zone géographique et groupe démographique, courbe épidémique, facteurs de risque, mesures en cours, recommandations de riposte.",
      },
      {
        label: "Protocole d'enquête épidémiologique",
        description: "Protocole complet pour enquête de terrain en santé publique",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Protocole d'enquête épidémiologique de terrain",
        contexte: "Justification et objectifs, hypothèses, type d'étude (transversale/cas-témoins/cohorte), population cible et échantillonnage, variables et outils de collecte, procédures de terrain, plan d'analyse, considérations éthiques, calendrier et budget.",
      },
      {
        label: "Rapport d'évaluation programme santé",
        description: "Évaluation mi-parcours ou finale d'un programme de santé",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport d'évaluation d'un programme de santé publique",
        contexte: "Contexte et description du programme, méthodologie d'évaluation, analyse de la pertinence, efficacité, efficience, impact et durabilité (critères OCDE/CAD), indicateurs atteints vs cibles, leçons apprises, recommandations.",
      },
      {
        label: "Formation — Outils de santé publique",
        description: "Support de formation sur les outils et méthodes en santé publique",
        type: "slides",
        typeDoc: "formation",
        mode: "detaille",
        sujet: "Formation — Outils et méthodes en santé publique",
        contexte: "Objectifs pédagogiques, modules : épidémiologie descriptive, surveillance épidémiologique, enquêtes de terrain, analyse des données de santé, outils OMS/CDC/ECOWAS, exercices pratiques avec études de cas africains.",
      },
      {
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
    categorie: "Recherche & Protocoles d'étude",
    emoji: "🔬",
    templates: [
      {
        label: "Protocole d'étude / recherche",
        description: "Protocole scientifique complet pour étude ou recherche",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Protocole d'étude — recherche scientifique ou opérationnelle",
        contexte: "Titre et résumé, introduction et revue de littérature, problématique et justification, objectifs (général et spécifiques), hypothèses, méthodologie (type d'étude, population, échantillonnage, variables, outils), plan d'analyse statistique, aspects éthiques, calendrier, budget prévisionnel, bibliographie.",
      },
      {
        label: "Rapport d'enquête / sondage",
        description: "Rapport de résultats d'une enquête quantitative ou qualitative",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport de résultats d'enquête",
        contexte: "Contexte et objectifs de l'enquête, méthodologie (type, échantillon, outils), résultats descriptifs (fréquences, moyennes, tableaux croisés), analyse inférentielle (tests statistiques), interprétation, conclusions et recommandations, annexes (questionnaire, tableaux détaillés).",
      },
      {
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
    categorie: "Suivi & Évaluation de projets",
    emoji: "📊",
    templates: [
      {
        label: "Rapport de suivi S&E",
        description: "Rapport trimestriel ou semestriel de suivi-évaluation d'un projet",
        type: "rapport",
        typeDoc: "rapport_analyse",
        mode: "complet",
        sujet: "Rapport de suivi et évaluation — projet de développement",
        contexte: "Rappel des objectifs et indicateurs du cadre logique, avancement physique et financier par composante, analyse des indicateurs (atteints vs cibles, tendances), analyse des écarts, facteurs d'influence (risques, hypothèses), leçons apprises, recommandations et plan d'action correctif, perspectives.",
      },
      {
        label: "Cadre de mesure de la performance",
        description: "Document CMP / tableau de bord indicateurs d'un projet",
        type: "rapport",
        typeDoc: "plan_action",
        mode: "standard",
        sujet: "Cadre de mesure de la performance — indicateurs et plan de S&E",
        contexte: "Cadre logique ou théorie du changement, sélection et définition des indicateurs SMART (intrants, extrants, effets, impact), sources de vérification, fréquence de collecte, responsabilités, valeurs de référence (baseline) et cibles.",
      },
      {
        label: "Présentation S&E bailleur",
        description: "Slides de rapport de suivi à destination du bailleur ou comité",
        type: "slides",
        typeDoc: "rapport_direction",
        mode: "detaille",
        sujet: "Présentation rapport S&E — bailleur / comité de pilotage",
        contexte: "Rappel des objectifs, tableau de bord des indicateurs clés, avancement physique et financier, points saillants (succès et défis), risques en cours, actions correctives, prochaines étapes.",
      },
      {
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
];

const TYPES_RAPPORT = [
  { value: "rapport_analyse",   label: "Rapport d'analyse" },
  { value: "note_de_synthese",  label: "Note de synthèse" },
  { value: "note_juridique",    label: "Note juridique" },
  { value: "rapport_financier", label: "Rapport financier" },
  { value: "rapport_rh",        label: "Rapport RH" },
  { value: "plan_action",       label: "Plan d'action" },
  { value: "compte_rendu",      label: "Compte-rendu" },
  { value: "rapport_audit",     label: "Rapport d'audit" },
];

const MODES_RAPPORT = [
  { value: "flash",    label: "Flash — 1 page (rapide)" },
  { value: "standard", label: "Standard — 3-5 pages" },
  { value: "complet",  label: "Complet — 10-30 pages" },
  { value: "expert",   label: "Expert — 40-80 pages (exhaustif)" },
];

const TYPES_SLIDES = [
  { value: "bilan_activite",      label: "Bilan d'activité" },
  { value: "proposition_client",  label: "Proposition client" },
  { value: "rapport_direction",   label: "Rapport direction / CA" },
  { value: "formation",           label: "Support de formation" },
  { value: "pitch_projet",        label: "Pitch projet / Startup" },
  { value: "analyse_marche",      label: "Analyse de marché" },
  { value: "rapport_financier",   label: "Présentation financière" },
];

const MODES_SLIDES = [
  { value: "executive", label: "Exécutif — 5-8 slides" },
  { value: "detaille",  label: "Détaillé — 10-15 slides" },
  { value: "pitch",     label: "Pitch — 8-12 slides impactants" },
  { value: "expert",    label: "Expert — 25-40 slides (exhaustif)" },
];

const TYPES_SORTIE_FICHIERS = [
  { value: "rapport_analyse",        label: "Rapport d'analyse (DOCX)" },
  { value: "rapport_financier",      label: "Rapport financier (DOCX)" },
  { value: "rapport_audit",          label: "Rapport d'audit (DOCX)" },
  { value: "note_de_synthese",       label: "Note de synthèse (DOCX)" },
  { value: "note_juridique",         label: "Note juridique (DOCX)" },
  { value: "plan_action",            label: "Plan d'action (DOCX)" },
  { value: "rapport_direction",      label: "Présentation direction (PPTX)" },
  { value: "bilan_activite",         label: "Bilan d'activité (PPTX)" },
  { value: "proposition_client",     label: "Proposition client (PPTX)" },
  { value: "pitch_projet",           label: "Pitch projet (PPTX)" },
];

const EXTENSIONS_ACCEPTEES = ".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.md,.pptx";
const FORMATS_SLIDES = new Set(["rapport_direction","bilan_activite","proposition_client","pitch_projet","formation","analyse_marche"]);

export const GenerateursPage = () => {
  const navigate = useNavigate();
  // Onglet persisté dans le store → survit à la navigation
  const tab = useGenerateurStore((s) => s.tab) as Tab;
  const setTab = (t: Tab) => useGenerateurStore.getState().setTab(t);
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
      .catch(() => toast.error("Impossible de charger les gabarits"));
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
      toast.error("Décrivez votre besoin (min 10 caractères)"); return;
    }
    if (infogMode === "manuel" && !infogTitre.trim()) { toast.error("Titre requis"); return; }
    if (infogMode === "modele") {
      if (!infogModele) { toast.error("Choisissez une image modèle"); return; }
      if (infogBrief.trim().length < 10) { toast.error("Décrivez votre besoin (min 10 caractères)"); return; }
    }
    if (infogMode === "custom") {
      if (infogBrief.trim().length < 10) { toast.error("Décrivez votre besoin (min 10 caractères)"); return; }
      if (infogW <= 0 || infogH <= 0) { toast.error("Dimensions invalides"); return; }
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
      successMsg: "Infographie générée et sauvegardée dans Mes Documents !",
      onError: (err) => {
        const status = err?.response?.status;
        const detail: string = err?.response?.data?.detail || "";
        if (status === 402 && detail.startsWith("CREDITS_EPUISES")) {
          const restants = /restants=(\d+)/.exec(detail)?.[1] ?? "0";
          const plan     = /plan=([^|]+)/.exec(detail)?.[1] ?? "—";
          toast((t) => (
            <span className="text-sm">
              Crédits insuffisants ({restants} restants, plan {plan}).
              <button
                onClick={() => { toast.dismiss(t.id); navigate("/abonnement"); }}
                className="ml-2 px-2 py-1 bg-yukpo-500 text-white rounded text-xs font-semibold"
              >
                Recharger / Upgrader
              </button>
            </span>
          ), { duration: 8000, icon: "💳" });
        } else if (status === 403 && detail.startsWith("MODULE_NON_AUTORISE")) {
          toast((t) => (
            <span className="text-sm">
              Module Infographie non inclus dans votre plan.
              <button
                onClick={() => { toast.dismiss(t.id); navigate("/abonnement"); }}
                className="ml-2 px-2 py-1 bg-purple-500 text-white rounded text-xs font-semibold"
              >
                Upgrader
              </button>
            </span>
          ), { duration: 8000, icon: "🔒" });
        } else {
          toast.error(detail || "Erreur lors de la génération");
        }
      },
    });
  };

  const handleTelechargerInfog = (kind: "pdf" | "png") => {
    if (!infogResult) return;
    const b64 = kind === "pdf" ? infogResult.pdf_base64 : infogResult.png_base64;
    const id  = kind === "pdf" ? infogResult.pdf_id     : infogResult.png_id;
    if (!b64 || !id) { toast.error("Fichier indisponible"); return; }
    const mime = kind === "pdf" ? "application/pdf" : "image/png";
    const a = document.createElement("a");
    a.href = `data:${mime};base64,${b64}`;
    a.download = id;
    a.click();
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
      { successMsg: "Conversion réussie !", errorMsg: "Erreur lors de la conversion" },
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
    if (!instructionFichiers.trim()) return toast.error("Décrivez ce que vous souhaitez générer");
    if (fichiers.length === 0) return toast.error("Ajoutez au moins un fichier source");
    const estSlides = FORMATS_SLIDES.has(typeSortieFichiers);
    await runJob("fichiers", () => generateurApi.analyserEtGenerer({
      instruction: instructionFichiers,
      type_sortie: estSlides ? "slides" : "rapport",
      type_doc: typeSortieFichiers,
      mode: modeFichiers,
      format_sortie: estSlides ? "pptx" : "docx",
      fichiers,
    }), { successMsg: `Document généré depuis ${fichiers.length} fichier(s) !` });
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
      }), { successMsg: `Rapport généré depuis ${fichiersRapport.length} fichier(s) !` });
    } else {
      await runJob("rapport", () => generateurApi.rapport({
        sujet: sujetRapport,
        type_rapport: typeRapport,
        mode: modeRapport,
        contexte: contexteRapport || undefined,
        format_sortie: formatRapport as "docx" | "markdown",
      }), { successMsg: "Rapport généré avec succès !" });
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
      }), { successMsg: `Présentation générée depuis ${fichiersSlides.length} fichier(s) !` });
    } else {
      await runJob("slides", () => generateurApi.slides({
        sujet: sujetSlides,
        type_pres: typeSlides,
        mode: modeSlides,
        contexte: contexteSlides || undefined,
        format_sortie: formatSlides as "pptx" | "markdown",
      }), { successMsg: "Présentation générée !" });
    }
  };

  return (
    <div className="p-6 pb-24 space-y-6 max-w-5xl mx-auto animate-fade-in">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-display font-bold text-white flex items-center gap-2">
          Yukpo Studio
          <span className="text-xs font-semibold px-2 py-0.5 bg-corp-600/15 border border-corp-600/30 text-corp-600 rounded-full tracking-wide">PRO</span>
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Rapports d'analyse · Présentations PowerPoint · Analyse de fichiers · Conversion · Bibliothèque de modèles
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl flex-wrap" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
        {([
          { id: "rapport",    icon: <FileText className="w-4 h-4" />,      label: "Rapports Word" },
          { id: "slides",     icon: <Presentation className="w-4 h-4" />,  label: "PowerPoint" },
          { id: "conversion", icon: <RefreshCw className="w-4 h-4" />,     label: "Conversion" },
          { id: "modeles",    icon: <BookOpen className="w-4 h-4" />,      label: "Bibliothèque" },
          { id: "infographie", icon: <Palette className="w-4 h-4" />,     label: "Infographie Pro" },
        ] as const).map(({ id, icon, label }) => (
          <button
            key={id}
            onClick={() => { setTab(id as Tab); }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === id ? "bg-yukpo-500 text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            {icon} {label}
            {id === "infographie" && <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full bg-pink-500/20 text-pink-400 font-semibold">PRO</span>}
          </button>
        ))}
      </div>

      {/* Bibliothèque de modèles — accordéon */}
      {tab === "modeles" && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 mb-3">
            {TEMPLATES_PAR_METIER.reduce((s, c) => s + c.templates.length, 0)} modèles — cliquez sur une rubrique pour voir les modèles disponibles
          </p>
          {TEMPLATES_PAR_METIER.map((cat) => {
            const isOpen = openCat === cat.categorie;
            return (
              <div key={cat.categorie} className="rounded-xl border border-slate-700/60 overflow-hidden">
                <button
                  onClick={() => setOpenCat(isOpen ? null : cat.categorie)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800 transition-colors"
                  style={{ background: "var(--ykp-surface)" }}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-xl">{cat.emoji}</span>
                    <div className="text-left">
                      <p className="text-sm font-semibold text-white">{cat.categorie}</p>
                      <p className="text-xs text-slate-500">
                        {cat.templates.length} modèle{cat.templates.length > 1 ? "s" : ""}
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
                        key={tpl.label}
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
                          toast.success(`Modèle "${tpl.label}" chargé`);
                        }}
                        className="group text-left p-3 rounded-xl hover:border-yukpo-500/60 hover:bg-yukpo-500/5 transition-all"
                        style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}
                      >
                        <div className="flex items-start justify-between gap-1.5 mb-1">
                          <p className="text-xs font-semibold text-white group-hover:text-yukpo-300 transition-colors leading-snug">
                            {tpl.label}
                          </p>
                          <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                            tpl.type === "rapport"
                              ? "bg-blue-500/15 text-blue-300"
                              : "bg-purple-500/15 text-purple-300"
                          }`}>
                            {tpl.type === "rapport" ? "DOCX" : "PPTX"}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 leading-snug line-clamp-2">{tpl.description}</p>
                        <div className="flex items-center gap-0.5 text-[10px] text-yukpo-400 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          Utiliser <ArrowRight className="w-2.5 h-2.5" />
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
                <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Fichiers sources *</p>
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
                        {fichiers.length > 0 ? `${fichiers.length} fichier(s) chargé(s)` : "Glissez vos fichiers ici"}
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
                  Instruction de génération *
                </label>
                <textarea
                  placeholder="Ex: Génère un rapport d'analyse financière basé sur ces données Excel, avec tendances, ratios clés et recommandations. Analyse les évolutions année par année et mets en évidence les anomalies."
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
                  label="Type de document généré"
                  options={TYPES_SORTIE_FICHIERS}
                  value={typeSortieFichiers}
                  onChange={(e) => setTypeSortieFichiers(e.target.value)}
                />
              </div>
              <div className="w-full sm:w-44">
                <Select
                  label="Niveau de détail"
                  options={[
                    { value: "flash",    label: "Flash — rapide" },
                    { value: "standard", label: "Standard" },
                    { value: "complet",  label: "Complet" },
                    { value: "executive", label: "Exécutif" },
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
                  Analyser et générer
                </Button>
              </div>
            </div>
          </form>

          {/* Résultat */}
          {loading && (
            <Card className="p-6 flex items-center gap-4">
              <Loader className="w-6 h-6 text-yukpo-400 animate-spin shrink-0" />
              <div>
                <p className="text-white font-medium text-sm">Yukpo Pro analyse et génère votre document…</p>
                <p className="text-slate-400 text-xs mt-0.5">Yukpo lit vos fichiers et rédige le document professionnel</p>
              </div>
            </Card>
          )}
          {!loading && resultat && (
            <Card className="p-5 space-y-3 animate-fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 text-green-400" />
                  <span className="text-sm font-semibold text-white">Document généré !</span>
                </div>
                <button
                  type="button"
                  onClick={() => { setResultat(null); setFichiers([]); setInstructionFichiers(""); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-600 text-slate-400 text-xs font-medium hover:border-yukpo-500 hover:text-yukpo-300 transition-all"
                >
                  <Upload className="w-3 h-3" /> Générer un autre
                </button>
              </div>
              {resultat.fichier && (
                <a
                  href={generateurApi.telecharger(resultat.fichier)}
                  download={resultat.fichier}
                  className="flex items-center gap-3 p-3 bg-[#0054A6]/10 dark:bg-yukpo-500/20 border border-[#0054A6]/30 dark:border-yukpo-500/40 rounded-xl hover:bg-[#0054A6]/15 dark:hover:bg-yukpo-500/30 transition-colors"
                >
                  <Download className="w-5 h-5 text-[#0054A6] dark:text-yukpo-400" />
                  <div>
                    <p className="text-sm font-medium text-white">{resultat.fichier}</p>
                    <p className="text-xs text-slate-400">Cliquer pour télécharger</p>
                  </div>
                </a>
              )}
              {resultat.markdown && (
                <div className="max-h-64 overflow-y-auto">
                  <p className="text-xs text-slate-500 mb-2">Aperçu :</p>
                  <div className="p-3 bg-slate-900 rounded-xl border border-slate-700 text-xs">
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
            <p className="text-sm text-slate-400">Convertissez un fichier vers un autre format en un clic.<br />PDF → Word, Excel → CSV, Image → Word (OCR), et bien d'autres.</p>
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
                  <p className="text-sm font-medium text-slate-300">Déposez votre fichier ici</p>
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
                  label="Convertir vers"
                  options={ciblsDispos}
                  value={formatCible}
                  onChange={(e) => setFormatCible(e.target.value)}
                />
                <Button type="submit" loading={loadingConv} icon={<RefreshCw className="w-4 h-4" />} className="w-full">
                  Convertir
                </Button>
              </>
            )}
          </form>

          {loadingConv && (
            <Card className="p-5 flex items-center gap-4">
              <Loader className="w-5 h-5 text-yukpo-400 animate-spin" />
              <p className="text-sm text-white">Conversion en cours…</p>
            </Card>
          )}

          {!loadingConv && resultatConv && (
            <Card className="p-5 space-y-3 animate-fade-in">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <span className="text-sm font-semibold text-white">
                  {resultatConv.format_source.toUpperCase()} → {resultatConv.format_cible.replace(".", "").toUpperCase()} — Conversion réussie !
                </span>
              </div>
              <a
                href={generateurApi.telecharger(resultatConv.fichier_converti)}
                download={resultatConv.fichier_converti}
                className="flex items-center gap-3 p-3 bg-[#0054A6]/10 dark:bg-yukpo-500/20 border border-[#0054A6]/30 dark:border-yukpo-500/40 rounded-xl hover:bg-[#0054A6]/15 dark:hover:bg-yukpo-500/30 transition-colors"
              >
                <Download className="w-5 h-5 text-[#0054A6] dark:text-yukpo-400" />
                <div>
                  <p className="text-sm font-medium text-white">{resultatConv.fichier_converti}</p>
                  <p className="text-xs text-slate-400">Cliquer pour télécharger</p>
                </div>
              </a>
              <button
                type="button"
                onClick={() => { setFichierConv(null); setResultatConv(null); }}
                className="text-xs text-slate-400 hover:text-white underline"
              >
                Convertir un autre fichier
              </button>
            </Card>
          )}
        </div>
      )}

      {/* ── Tab Infographie Pro (print-ready PDF + PNG preview) ───────────── */}
      {tab === "infographie" && (
        <div className="space-y-4">
          {/* Étape 1 : choix du sous-mode */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {([
              { id: "brief",  icon: <Wand2 className="w-4 h-4" />,      label: "Brief libre IA",       desc: "Décris, l'IA compose" },
              { id: "manuel", icon: <Settings2 className="w-4 h-4" />,  label: "Spec manuelle",        desc: "Sans IA, contrôle total" },
              { id: "modele", icon: <FileImage className="w-4 h-4" />,  label: "Depuis un modèle",     desc: "Upload + brief inspiré" },
              { id: "custom", icon: <Maximize2 className="w-4 h-4" />,  label: "Format sur mesure",    desc: "Dimensions libres mm" },
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
                    Gabarit ({infogGabarits.length} disponibles)
                  </label>
                  <select value={infogGabarit} onChange={e => setInfogGabarit(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500">
                    {Object.entries(gabaritsParCategorie).map(([cat, items]) => (
                      <optgroup key={cat} label={cat.toUpperCase()}>
                        {items.map(g => (
                          <option key={g.cle} value={g.cle}>
                            {g.label} — {g.width_mm}×{g.height_mm}mm — {g.prix_fcfa.toLocaleString("fr-FR")} FCFA
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  {gabaritCourant && (
                    <p className="text-[11px] text-slate-500 mt-1">{gabaritCourant.description} · bleed {gabaritCourant.bleed_mm}mm</p>
                  )}
                </div>
              )}

              {/* Mode CUSTOM : dimensions */}
              {infogMode === "custom" && (
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-xs font-semibold text-slate-400 mb-1 block">Largeur (mm)</label>
                    <input type="number" min={10} max={3000} value={infogW} onChange={e => setInfogW(Number(e.target.value))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-400 mb-1 block">Hauteur (mm)</label>
                    <input type="number" min={10} max={3000} value={infogH} onChange={e => setInfogH(Number(e.target.value))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-400 mb-1 block">Bleed (mm)</label>
                    <input type="number" min={0} max={20} value={infogBleed} onChange={e => setInfogBleed(Number(e.target.value))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500" />
                  </div>
                </div>
              )}

              {/* Mode MODÈLE : upload */}
              {infogMode === "modele" && (
                <div>
                  <label className="text-xs font-semibold text-slate-400 mb-1.5 block">Image modèle (PNG/JPG/WEBP, max 10 Mo)</label>
                  <input ref={infogModeleRef} type="file" accept="image/png,image/jpeg,image/jpg,image/webp"
                    onChange={e => setInfogModele(e.target.files?.[0] || null)} className="hidden" />
                  <button type="button" onClick={() => infogModeleRef.current?.click()}
                    className="w-full flex items-center gap-2 px-3 py-2 border border-dashed border-slate-700 hover:border-yukpo-500 rounded-lg text-sm text-slate-400 hover:text-white transition-all">
                    <Upload className="w-4 h-4" />
                    {infogModele ? `${infogModele.name} (${(infogModele.size / 1024).toFixed(0)} Ko)` : "Uploader un visuel modèle (style, couleurs, layout)"}
                  </button>
                </div>
              )}

              {/* Étape 3 : champs spécifiques au mode */}
              {(infogMode === "brief" || infogMode === "modele" || infogMode === "custom") && (
                <div>
                  <label className="text-xs font-semibold text-slate-400 mb-1.5 block">Brief créatif *</label>
                  <textarea value={infogBrief} onChange={e => setInfogBrief(e.target.value)} rows={5} required
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500 resize-none"
                    placeholder="Ex: Flyer pour la formation 'Souscription Risques Industriels' organisée par YukpoAssurance Douala, le 15 mai 2026 à l'hôtel Hilton. Cible : courtiers et souscripteurs CIMA. Contact : +237 690 11 22 33. Style moderne et institutionnel." />
                </div>
              )}

              {infogMode === "manuel" && (
                <>
                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="col-span-2">
                      <label className="text-xs font-semibold text-slate-400 mb-1 block">Titre principal *</label>
                      <input value={infogTitre} onChange={e => setInfogTitre(e.target.value)} required maxLength={60}
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500" />
                    </div>
                    <input value={infogSousTitre} onChange={e => setInfogSousTitre(e.target.value)} maxLength={80}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder="Sous-titre" />
                    <select value={infogPalette} onChange={e => setInfogPalette(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500">
                      {infogPalettes.map(p => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
                    </select>
                    <input value={infogOrg} onChange={e => setInfogOrg(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder="Nom de l'organisation" />
                    <input value={infogContact} onChange={e => setInfogContact(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder="Tel / email / adresse" />
                    <input value={infogDate} onChange={e => setInfogDate(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder="Date événement" />
                    <input value={infogLieu} onChange={e => setInfogLieu(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder="Lieu" />
                    <input value={infogSlogan} onChange={e => setInfogSlogan(e.target.value)}
                      className="col-span-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500"
                      placeholder="Slogan / accroche" />
                  </div>
                  <textarea value={infogCorps} onChange={e => setInfogCorps(e.target.value)} rows={2} maxLength={300}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500 resize-none"
                    placeholder="Corps de texte principal (max 300 caractères)" />
                  <textarea value={infogDetails} onChange={e => setInfogDetails(e.target.value)} rows={3}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yukpo-500 resize-none"
                    placeholder="Détails (1 par ligne, max 6 lignes)" />
                </>
              )}

              {/* Pays cible (sauf manuel) */}
              {infogMode !== "manuel" && (
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="text-xs font-semibold text-slate-400 mb-1 block">Pays cible</label>
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

              {/* Bouton générer */}
              <button type="submit" disabled={infogLoading}
                className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-corp-600 to-corp-500 hover:from-corp-700 hover:to-corp-600 disabled:opacity-50 text-white font-semibold rounded-xl transition-all text-sm">
                {infogLoading
                  ? <><Loader className="w-4 h-4 animate-spin" /> Yukpo Pro compose votre infographie…</>
                  : <><Sparkles className="w-4 h-4" /> Générer l'infographie print-ready</>}
              </button>
              <p className="text-[11px] text-slate-500 text-center">PDF 300 DPI, traits de coupe, bleed inclus · PNG preview · sauvegarde automatique dans Mes Documents</p>
            </form>

            {/* Aperçu — 2 colonnes */}
            <div className="lg:col-span-2 flex flex-col gap-4">
              {infogResult ? (
                <Card className="p-4 flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-white flex items-center gap-2">
                      <ImageIcon className="w-4 h-4 text-pink-400" /> Aperçu
                    </span>
                    <div className="flex gap-2 flex-wrap justify-end">
                      {infogResult.png_id && (
                        <button type="button" onClick={() => setInfogZoom(true)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/50 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-all">
                          <Maximize2 className="w-3.5 h-3.5" /> Zoom
                        </button>
                      )}
                      {infogResult.pdf_id && (
                        <button type="button" onClick={() => handleTelechargerInfog("pdf")}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-yukpo-500/20 hover:bg-yukpo-500/30 text-yukpo-300 rounded-lg text-xs font-medium transition-all">
                          <Download className="w-3.5 h-3.5" /> PDF print-ready
                        </button>
                      )}
                      {infogResult.png_id && (
                        <button type="button" onClick={() => handleTelechargerInfog("png")}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/50 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-all">
                          <Download className="w-3.5 h-3.5" /> PNG
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
                      Preview PNG indisponible — téléchargez le PDF
                    </div>
                  )}
                  {infogResult.specification && (
                    <div className="text-xs text-slate-400 space-y-1 border-t border-slate-700/60 pt-2">
                      <p><span className="text-slate-500">Titre :</span> {infogResult.specification.titre}</p>
                      {infogResult.specification.palette && (
                        <p><span className="text-slate-500">Palette :</span> {infogResult.specification.palette}</p>
                      )}
                      {typeof infogResult.prix_fcfa === "number" && infogResult.prix_fcfa > 0 && (
                        <p><span className="text-slate-500">Tarif imprimé indicatif :</span> {infogResult.prix_fcfa.toLocaleString("fr-FR")} FCFA</p>
                      )}
                    </div>
                  )}
                  <span className="flex items-center gap-1.5 text-[11px] text-green-400">
                    <Save className="w-3 h-3" /> Sauvegardé dans Mes Documents
                  </span>
                </Card>
              ) : (
                <Card className="flex flex-col items-center justify-center gap-4 p-12 border-dashed min-h-[400px]">
                  <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-corp-600/15 to-bright-400/10 flex items-center justify-center">
                    <Palette className="w-8 h-8 text-purple-400" />
                  </div>
                  <div className="text-center">
                    <p className="text-white font-semibold mb-1">Infographie Pro — Print-Ready</p>
                    <p className="text-slate-500 text-sm">Cartes de visite · Flyers · Affiches · Diplômes<br />Faire-part · Roll-ups · Posts sociaux · Bâches</p>
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

      <div className={`grid grid-cols-1 lg:grid-cols-5 gap-6 items-start ${tab === "modeles" || tab === "conversion" || tab === "infographie" ? "hidden" : ""}`}>
        {/* Form */}
        <div className="lg:col-span-3 space-y-4">
          {tab === "rapport" ? (
            <form onSubmit={handleGenererRapport} className="space-y-3">
              <Textarea
                label="Sujet du rapport *"
                placeholder="Ex: Analyse de la situation financière de l'entreprise XYZ pour l'exercice 2024…"
                value={sujetRapport}
                onChange={(e) => setSujetRapport(e.target.value)}
                rows={2}
              />
              <div className="grid grid-cols-2 gap-3">
                <Select label="Type de rapport" options={TYPES_RAPPORT} value={typeRapport} onChange={(e) => setTypeRapport(e.target.value)} />
                <Select label="Mode" options={MODES_RAPPORT} value={modeRapport} onChange={(e) => setModeRapport(e.target.value)} />
              </div>
              <Textarea
                label="Contexte / Données supplémentaires"
                placeholder="Données financières, informations spécifiques, instructions particulières…"
                value={contexteRapport}
                onChange={(e) => setContexteRapport(e.target.value)}
                rows={3}
              />
              {/* Zone fichiers intégrée */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-slate-400">
                    Fichiers d'analyse <span className="text-slate-600 font-normal">(optionnel — Excel, PDF, CSV, DOCX…)</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => fileRapportRef.current?.click()}
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors"
                  >
                    <Upload className="w-3.5 h-3.5" /> Ajouter fichiers
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
                    Yukpo analysera automatiquement ces fichiers pour enrichir le rapport
                  </p>
                )}
              </div>
              <div className="flex gap-3 items-center">
                {fichiersRapport.length === 0 && (
                  <div className="flex gap-2">
                    {["docx", "markdown"].map((fmt) => (
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
                  {fichiersRapport.length > 0 ? `Analyser et générer (${fichiersRapport.length} fichier${fichiersRapport.length > 1 ? "s" : ""})` : "Générer le rapport"}
                </Button>
              </div>
            </form>
          ) : (
            <form onSubmit={handleGenererSlides} className="space-y-3">
              <Textarea
                label="Sujet de la présentation *"
                placeholder="Ex: Résultats financiers Q3 2024 pour le conseil d'administration…"
                value={sujetSlides}
                onChange={(e) => setSujetSlides(e.target.value)}
                rows={2}
              />
              <div className="grid grid-cols-2 gap-3">
                <Select label="Type de présentation" options={TYPES_SLIDES} value={typeSlides} onChange={(e) => setTypeSlides(e.target.value)} />
                <Select label="Mode" options={MODES_SLIDES} value={modeSlides} onChange={(e) => setModeSlides(e.target.value)} />
              </div>
              <Textarea
                label="Contexte / Données"
                placeholder="Données clés à inclure, KPIs, messages principaux…"
                value={contexteSlides}
                onChange={(e) => setContexteSlides(e.target.value)}
                rows={3}
              />
              {/* Zone fichiers intégrée */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-slate-400">
                    Fichiers d'analyse <span className="text-slate-600 font-normal">(optionnel — Excel, PDF, CSV…)</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => fileSlidesRef.current?.click()}
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors"
                  >
                    <Upload className="w-3.5 h-3.5" /> Ajouter fichiers
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
                    Yukpo analysera ces fichiers pour construire les slides
                  </p>
                )}
              </div>
              <div className="flex gap-3 items-center">
                {fichiersSlides.length === 0 && (
                  <div className="flex gap-2">
                    {["pptx", "markdown"].map((fmt) => (
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
                  {fichiersSlides.length > 0 ? `Analyser et générer (${fichiersSlides.length} fichier${fichiersSlides.length > 1 ? "s" : ""})` : "Générer les slides"}
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
                <p className="text-white font-medium text-sm">Yukpo Pro rédige votre document…</p>
                <p className="text-slate-400 text-xs mt-1">Yukpo construit un document professionnel de haute qualité</p>
              </div>
            </Card>
          ) : resultat ? (
            <Card className="p-5 space-y-4 animate-fade-in">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <span className="text-sm font-semibold text-white">Document généré !</span>
              </div>

              {/* Téléchargement */}
              {resultat.fichier && (
                <a
                  href={generateurApi.telecharger(resultat.fichier)}
                  download={resultat.fichier}
                  className="flex items-center gap-3 p-3 bg-yukpo-500/20 border border-yukpo-500/40 rounded-xl hover:bg-yukpo-500/30 transition-colors group"
                >
                  <Download className="w-5 h-5 text-[#0054A6] dark:text-yukpo-400" />
                  <div>
                    <p className="text-sm font-medium text-white">{resultat.fichier}</p>
                    <p className="text-xs text-slate-400">Cliquer pour télécharger</p>
                  </div>
                </a>
              )}

              {/* Aperçu Markdown */}
              {resultat.markdown && (
                <div className="max-h-80 overflow-y-auto">
                  <p className="text-xs text-slate-500 mb-2">Aperçu :</p>
                  <div className="p-3 bg-slate-900 rounded-xl border border-slate-700 text-xs">
                    <ReactMarkdown className="prose prose-sm prose-invert max-w-none">
                      {resultat.markdown.slice(0, 2000)}
                    </ReactMarkdown>
                    {(resultat.markdown.length || 0) > 2000 && (
                      <p className="text-slate-500 mt-2">… (aperçu tronqué)</p>
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
                  ? "Votre rapport DOCX apparaîtra ici"
                  : "Votre présentation PPTX apparaîtra ici"}
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

