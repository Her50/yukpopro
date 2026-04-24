// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
  user_id: number;
  email: string;
  nom: string;
  prenom?: string;
  role: string;
  token: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  nom: string;
  prenom?: string;
}

// ── Profil Pro ────────────────────────────────────────────────────────────────

export type NiveauExpertise = "debutant" | "intermediaire" | "senior" | "expert";

export interface ProfilPro {
  user_id: number;
  metier: string;
  secteur: string;
  pays: string;
  ville?: string;
  entreprise?: string;
  niveau_expertise: NiveauExpertise;
  annees_experience?: number;
  bio?: string;
  xp_points: number;
  nb_requetes_agent: number;
  nb_requetes_rag: number;
  nb_rapports_generes: number;
  nb_slides_generes: number;
  nb_requetes_copilote: number;
  nb_traductions: number;
  niveau_pro: string;
}

export const METIERS = [
  { value: "analyste_credit",       label: "Analyste crédit" },
  { value: "architecte",            label: "Architecte / BTP" },
  { value: "auditeur",              label: "Auditeur" },
  { value: "banquier",              label: "Banquier / Analyste crédit" },
  { value: "charge_projets_ong",    label: "Chargé de projets ONG" },
  { value: "commercial",            label: "Commercial / Business Dev" },
  { value: "comptable",             label: "Comptable / Expert-comptable" },
  { value: "conducteur_travaux",    label: "Conducteur de travaux" },
  { value: "consultant",            label: "Consultant" },
  { value: "coordinateur_ong",      label: "Coordinateur ONG" },
  { value: "credit_officer",        label: "Credit Officer / IMF" },
  { value: "daa",                   label: "Data Analyst / BI" },
  { value: "data_scientist",        label: "Data Scientist" },
  { value: "daf",                   label: "Directeur Financier (DAF)" },
  { value: "directeur_commercial",  label: "Directeur commercial" },
  { value: "douanier",              label: "Douanier / Agent transit" },
  { value: "drh",                   label: "DRH / Responsable RH" },
  { value: "entrepreneur",          label: "Entrepreneur / CEO" },
  { value: "fiscaliste",            label: "Fiscaliste" },
  { value: "gestionnaire_rh",       label: "Gestionnaire RH / Paie" },
  { value: "ingenieur",             label: "Ingénieur / Chef de projet" },
  { value: "juriste",               label: "Juriste / Avocat" },
  { value: "medecin",               label: "Médecin / Professionnel de santé" },
  { value: "notaire",               label: "Notaire" },
  { value: "pharmacien",            label: "Pharmacien" },
  { value: "responsable_microfinance", label: "Responsable Microfinance (SFD)" },
  { value: "trader",                label: "Trader / Gestionnaire actifs" },
  { value: "transitaire",           label: "Transitaire / Commerce international" },
  { value: "autre",                 label: "Autre" },
] as const;

export const SECTEURS_ACTIVITE = [
  { value: "administration_publique",label: "Administration publique" },
  { value: "agriculture_agro",       label: "Agriculture / Agro-industrie" },
  { value: "assurance",              label: "Assurance" },
  { value: "btp_construction",       label: "BTP / Construction" },
  { value: "commerce_distribution",  label: "Commerce / Distribution" },
  { value: "comptabilite_audit",     label: "Comptabilité / Audit / Fiscal" },
  { value: "education_formation",    label: "Éducation / Formation" },
  { value: "energie_mines",          label: "Énergie / Mines / Environnement" },
  { value: "finance_banque",         label: "Finance / Banque" },
  { value: "immobilier",             label: "Immobilier" },
  { value: "industrie_manufacture",  label: "Industrie / Manufacture" },
  { value: "juridique_notariat",     label: "Juridique / Notariat" },
  { value: "microfinance_imf",       label: "Microfinance / IMF" },
  { value: "ong_developpement",      label: "ONG / Développement / Humanitaire" },
  { value: "recherche_conseil",      label: "Recherche / Conseil" },
  { value: "ressources_humaines",    label: "Ressources humaines" },
  { value: "sante_pharmacie",        label: "Santé / Pharmacie" },
  { value: "technologie_numerique",  label: "Technologie / Numérique" },
  { value: "telecom_medias",         label: "Télécommunications / Médias" },
  { value: "tourisme_hotellerie",    label: "Tourisme / Hôtellerie" },
  { value: "transport_logistique",   label: "Transport / Logistique" },
  { value: "autre",                  label: "Autre" },
] as const;

export const PAYS_MONDE = [
  { value: "AF", label: "Afghanistan" },
  { value: "ZA", label: "Afrique du Sud" },
  { value: "AL", label: "Albanie" },
  { value: "DZ", label: "Algérie" },
  { value: "DE", label: "Allemagne" },
  { value: "AD", label: "Andorre" },
  { value: "AO", label: "Angola" },
  { value: "SA", label: "Arabie Saoudite" },
  { value: "AR", label: "Argentine" },
  { value: "AM", label: "Arménie" },
  { value: "AU", label: "Australie" },
  { value: "AT", label: "Autriche" },
  { value: "AZ", label: "Azerbaïdjan" },
  { value: "BH", label: "Bahreïn" },
  { value: "BD", label: "Bangladesh" },
  { value: "BY", label: "Bélarus" },
  { value: "BE", label: "Belgique" },
  { value: "BJ", label: "Bénin" },
  { value: "BO", label: "Bolivie" },
  { value: "BA", label: "Bosnie-Herzégovine" },
  { value: "BW", label: "Botswana" },
  { value: "BR", label: "Brésil" },
  { value: "BG", label: "Bulgarie" },
  { value: "BF", label: "Burkina Faso" },
  { value: "BI", label: "Burundi" },
  { value: "KH", label: "Cambodge" },
  { value: "CM", label: "Cameroun" },
  { value: "CA", label: "Canada" },
  { value: "CV", label: "Cap-Vert" },
  { value: "CF", label: "Centrafrique" },
  { value: "CL", label: "Chili" },
  { value: "CN", label: "Chine" },
  { value: "CY", label: "Chypre" },
  { value: "CO", label: "Colombie" },
  { value: "KM", label: "Comores" },
  { value: "CG", label: "Congo-Brazzaville" },
  { value: "KP", label: "Corée du Nord" },
  { value: "KR", label: "Corée du Sud" },
  { value: "CR", label: "Costa Rica" },
  { value: "CI", label: "Côte d'Ivoire" },
  { value: "HR", label: "Croatie" },
  { value: "CU", label: "Cuba" },
  { value: "DK", label: "Danemark" },
  { value: "DJ", label: "Djibouti" },
  { value: "EG", label: "Égypte" },
  { value: "AE", label: "Émirats arabes unis" },
  { value: "EC", label: "Équateur" },
  { value: "ER", label: "Érythrée" },
  { value: "ES", label: "Espagne" },
  { value: "EE", label: "Estonie" },
  { value: "SZ", label: "Eswatini" },
  { value: "ET", label: "Éthiopie" },
  { value: "FI", label: "Finlande" },
  { value: "FR", label: "France" },
  { value: "GA", label: "Gabon" },
  { value: "GM", label: "Gambie" },
  { value: "GE", label: "Géorgie" },
  { value: "GH", label: "Ghana" },
  { value: "GR", label: "Grèce" },
  { value: "GT", label: "Guatemala" },
  { value: "GN", label: "Guinée" },
  { value: "GQ", label: "Guinée équatoriale" },
  { value: "GW", label: "Guinée-Bissau" },
  { value: "HT", label: "Haïti" },
  { value: "HN", label: "Honduras" },
  { value: "HU", label: "Hongrie" },
  { value: "IN", label: "Inde" },
  { value: "ID", label: "Indonésie" },
  { value: "IQ", label: "Irak" },
  { value: "IR", label: "Iran" },
  { value: "IE", label: "Irlande" },
  { value: "IS", label: "Islande" },
  { value: "IL", label: "Israël" },
  { value: "IT", label: "Italie" },
  { value: "JM", label: "Jamaïque" },
  { value: "JP", label: "Japon" },
  { value: "JO", label: "Jordanie" },
  { value: "KZ", label: "Kazakhstan" },
  { value: "KE", label: "Kenya" },
  { value: "KG", label: "Kirghizistan" },
  { value: "KW", label: "Koweït" },
  { value: "LA", label: "Laos" },
  { value: "LS", label: "Lesotho" },
  { value: "LV", label: "Lettonie" },
  { value: "LB", label: "Liban" },
  { value: "LR", label: "Liberia" },
  { value: "LY", label: "Libye" },
  { value: "LT", label: "Lituanie" },
  { value: "LU", label: "Luxembourg" },
  { value: "MG", label: "Madagascar" },
  { value: "MY", label: "Malaisie" },
  { value: "MW", label: "Malawi" },
  { value: "MV", label: "Maldives" },
  { value: "ML", label: "Mali" },
  { value: "MT", label: "Malte" },
  { value: "MA", label: "Maroc" },
  { value: "MU", label: "Maurice" },
  { value: "MR", label: "Mauritanie" },
  { value: "MX", label: "Mexique" },
  { value: "MD", label: "Moldavie" },
  { value: "MC", label: "Monaco" },
  { value: "MN", label: "Mongolie" },
  { value: "ME", label: "Monténégro" },
  { value: "MZ", label: "Mozambique" },
  { value: "MM", label: "Myanmar" },
  { value: "NA", label: "Namibie" },
  { value: "NP", label: "Népal" },
  { value: "NI", label: "Nicaragua" },
  { value: "NE", label: "Niger" },
  { value: "NG", label: "Nigeria" },
  { value: "NO", label: "Norvège" },
  { value: "NZ", label: "Nouvelle-Zélande" },
  { value: "OM", label: "Oman" },
  { value: "UG", label: "Ouganda" },
  { value: "UZ", label: "Ouzbékistan" },
  { value: "PK", label: "Pakistan" },
  { value: "PS", label: "Palestine" },
  { value: "PA", label: "Panama" },
  { value: "PY", label: "Paraguay" },
  { value: "NL", label: "Pays-Bas" },
  { value: "PE", label: "Pérou" },
  { value: "PH", label: "Philippines" },
  { value: "PL", label: "Pologne" },
  { value: "PT", label: "Portugal" },
  { value: "QA", label: "Qatar" },
  { value: "CD", label: "RD Congo" },
  { value: "DO", label: "République dominicaine" },
  { value: "CZ", label: "République tchèque" },
  { value: "RO", label: "Roumanie" },
  { value: "GB", label: "Royaume-Uni" },
  { value: "RU", label: "Russie" },
  { value: "RW", label: "Rwanda" },
  { value: "SV", label: "Salvador" },
  { value: "SN", label: "Sénégal" },
  { value: "RS", label: "Serbie" },
  { value: "SL", label: "Sierra Leone" },
  { value: "SG", label: "Singapour" },
  { value: "SK", label: "Slovaquie" },
  { value: "SI", label: "Slovénie" },
  { value: "SO", label: "Somalie" },
  { value: "SD", label: "Soudan" },
  { value: "SS", label: "Soudan du Sud" },
  { value: "LK", label: "Sri Lanka" },
  { value: "SE", label: "Suède" },
  { value: "CH", label: "Suisse" },
  { value: "SR", label: "Suriname" },
  { value: "SY", label: "Syrie" },
  { value: "TJ", label: "Tadjikistan" },
  { value: "TW", label: "Taïwan" },
  { value: "TZ", label: "Tanzanie" },
  { value: "TD", label: "Tchad" },
  { value: "TH", label: "Thaïlande" },
  { value: "TG", label: "Togo" },
  { value: "TN", label: "Tunisie" },
  { value: "TM", label: "Turkménistan" },
  { value: "TR", label: "Turquie" },
  { value: "UA", label: "Ukraine" },
  { value: "UY", label: "Uruguay" },
  { value: "VE", label: "Venezuela" },
  { value: "VN", label: "Vietnam" },
  { value: "YE", label: "Yémen" },
  { value: "ZM", label: "Zambie" },
  { value: "ZW", label: "Zimbabwe" },
] as const;

export const PAYS_AFRIQUE = PAYS_MONDE; // alias rétrocompat

// ── Copilote ──────────────────────────────────────────────────────────────────

export interface CoutLLM {
  modele: string;
  tokens_input: number;
  tokens_output: number;
  cout_reel_usd: number;
  marge: number;
  cout_app_usd: number;
  cout_app_xaf: number | null;   // null si hors zone CFA
  devise_cout: string | null;    // "XAF" | "XOF" | null (null → afficher USD)
}

export interface NavigationSuggestion {
  label: string;
  route: string;
  icon: string;
  description: string;
}

export interface CopiloteMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  agent_utilise?: string | null;
  loading?: boolean;
  fichiers?: string[];       // noms des fichiers attachés (user) ou générés (assistant)
  document_ref?: { id: number; titre: string; type: string };
  cout_llm?: CoutLLM | null;
  navigation_suggestions?: NavigationSuggestion[];
}

export interface CopiloteResponse {
  session_id: string;
  reponse: string;
  agent_utilise: string | null;
  resultat_agent: string | null;
  nb_messages_session: number;
  profil_metier: string | null;
  fichiers_generes?: string[] | null;
  cout_llm?: CoutLLM | null;
  navigation_suggestions?: NavigationSuggestion[];
}

// ── Agents ────────────────────────────────────────────────────────────────────

export interface AgentChatRequest {
  message: string;
  contexte?: Record<string, unknown>;
  pays?: string;
  domaine?: string;
}

export interface AgentChatResponse {
  execution_id: string;
  reponse: string;
  statut: string;
  nb_etapes: number;
  duree_ms: number;
  profil_metier: string;
}

// ── Générateurs ───────────────────────────────────────────────────────────────

export interface GenererRapportRequest {
  sujet: string;
  type_rapport: string;
  mode: string;
  contexte?: string;
  format_sortie?: "docx" | "markdown";
}

export interface GenererSlidesRequest {
  sujet: string;
  type_pres: string;
  mode: string;
  contexte?: string;
  format_sortie?: "pptx" | "markdown";
}

export interface GenerateurResult {
  fichier?: string;
  chemin?: string;
  markdown?: string;
  type: string;
  mode: string;
  sujet: string;
}

// ── RAG ───────────────────────────────────────────────────────────────────────

export interface RechercheRAGRequest {
  question: string;
  pays?: string;
  domaine?: string;
  top_k?: number;
}

export interface RechercheRAGResponse {
  question: string;
  contexte_rag: string;
  nb_passages: number;
  pays: string;
  metier: string;
}

// ── Traduction ────────────────────────────────────────────────────────────────

export interface TraductionRequest {
  contenu: string;
  langue_source: string;
  langue_cible: string;
  contexte_metier?: string;
  format_sortie?: string;
  sujet?: string;
}

export interface TraductionResponse {
  langue_source: string;
  langue_cible: string;
  nb_mots_source: number;
  nb_mots_cible: number;
  texte_traduit: string;
  chemin_docx?: string;
  fichier_traduit?: string;
  format_sortie?: string;
  sauvegarde_mes_documents?: boolean;
  fichier_source?: string;
}

// ── Abonnement ────────────────────────────────────────────────────────────────

export type PlanAbonnement = "gratuit" | "starter" | "pro" | "business";

export interface Abonnement {
  plan: PlanAbonnement;
  statut: "actif" | "expire" | "suspendu" | "essai";
  date_debut: string;
  date_fin: string | null;
  requetes_utilisees_jour: number;
  quota_jour: number;
  operateur?: string;
  numero_telephone?: string;
  reference_paiement?: string;
}

export interface PlanDetail {
  id: PlanAbonnement;
  nom: string;
  prix_fcfa: number;
  devise: string;
  periode: string;
  quota_jour: number;       // reste le nom technique (compat backend)
  credits_mois: number;     // valeur affichée à l'utilisateur
  agents: string;
  features: string[];
  couleur: string;
  badge?: string;
}

export const PLANS: PlanDetail[] = [
  {
    id: "gratuit",
    nom: "Gratuit",
    prix_fcfa: 0,
    devise: "FCFA",
    periode: "toujours",
    quota_jour: 10,
    credits_mois: 500,
    agents: "Tous les 13 agents",
    features: [
      "500 crédits Yukpo / mois (~10 échanges)",
      "Accès à tous les 13 agents Yukpo",
      "Générateur de documents (2/mois)",
      "Chat Yukpo Pro",
    ],
    couleur: "from-slate-600 to-slate-700",
  },
  {
    id: "starter",
    nom: "Starter",
    prix_fcfa: 3000,
    devise: "FCFA",
    periode: "mois",
    quota_jour: 50,
    credits_mois: 5000,
    agents: "Tous les 13 agents",
    features: [
      "5 000 crédits Yukpo / mois (~100 échanges)",
      "Tous les 13 agents Yukpo",
      "10 documents générés / mois",
      "Traduction de fichiers",
      "Gestion des réunions",
    ],
    couleur: "from-yukpo-600 to-yukpo-700",
  },
  {
    id: "pro",
    nom: "Pro",
    prix_fcfa: 7500,
    devise: "FCFA",
    periode: "mois",
    quota_jour: 200,
    credits_mois: 20000,
    agents: "Tous les 13 agents",
    badge: "Populaire",
    features: [
      "20 000 crédits Yukpo / mois (~400 échanges)",
      "Tous les 13 agents Yukpo + mémoire étendue",
      "Documents illimités (Word, PPT)",
      "Traduction + export DOCX",
      "Analyse de données avancée",
      "Réunions illimitées",
      "Support prioritaire",
    ],
    couleur: "from-purple-600 to-yukpo-600",
  },
  {
    id: "business",
    nom: "Business",
    prix_fcfa: 20000,
    devise: "FCFA",
    periode: "mois",
    quota_jour: 9999,
    credits_mois: 99999,
    agents: "Tous les 13 agents",
    features: [
      "Crédits Yukpo illimités",
      "Tous les 13 agents Yukpo",
      "Accès API Yukpo Pro",
      "Multi-utilisateurs (5 comptes)",
      "Tableau de bord analytique",
      "Intégration WhatsApp",
      "Support dédié 24/7",
    ],
    couleur: "from-gold-600 to-amber-600",
  },
];

export const OPERATEURS_MOBILE_MONEY = [
  { id: "orange_money",  label: "Orange Money",   pays: ["CM","CI","SN","ML","BF","GN","CD","MG"], logo: "https://logo.clearbit.com/orange.com" },
  { id: "mtn_momo",     label: "MTN MoMo",        pays: ["CM","CI","BJ","GH","UG","RW"],           logo: "https://logo.clearbit.com/mtn.com" },
  { id: "wave",         label: "Wave",             pays: ["SN","CI","ML","BF","GN"],               logo: "https://logo.clearbit.com/wave.com" },
  { id: "moov_money",   label: "Moov Money",       pays: ["CI","BJ","TG","NE","BF","TD","CF"],     logo: "https://logo.clearbit.com/moov-africa.com" },
  { id: "airtel_money", label: "Airtel Money",     pays: ["CD","CG","TD","MG","RW","BI"],          logo: "https://logo.clearbit.com/airtel.com" },
  { id: "expressunion", label: "Express Union",    pays: ["CM"],                                   logo: "https://logo.clearbit.com/expressunion.cm" },
];

// ── Documents générés (historique persisté) ──────────────────────────────────

export interface DocumentHistorique {
  id: number;
  titre: string;
  type_doc: "rapport" | "slides" | "traduction" | "autre";
  fichier?: string;
  contenu_source?: string;
  contenu_genere?: string;
  session_id?: string;
  meta: Record<string, unknown>;
  cree_le: string;
  modifie_le: string;
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export interface DashboardStats {
  xp_points: number;
  niveau_pro: string;
  nb_requetes_agent: number;
  nb_requetes_copilote: number;
  nb_rapports_generes: number;
  nb_slides_generes: number;
  nb_traductions: number;
}
