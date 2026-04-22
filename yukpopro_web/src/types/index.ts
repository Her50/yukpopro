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
  { value: "comptable",             label: "Comptable / Expert-comptable" },
  { value: "fiscaliste",            label: "Fiscaliste" },
  { value: "auditeur",              label: "Auditeur" },
  { value: "drh",                   label: "DRH / Responsable RH" },
  { value: "gestionnaire_rh",       label: "Gestionnaire RH / Paie" },
  { value: "daf",                   label: "Directeur Financier (DAF)" },
  { value: "juriste",               label: "Juriste / Avocat" },
  { value: "notaire",               label: "Notaire" },
  { value: "banquier",              label: "Banquier / Analyste crédit" },
  { value: "analyste_credit",       label: "Analyste crédit" },
  { value: "trader",                label: "Trader / Gestionnaire actifs" },
  { value: "ingenieur",             label: "Ingénieur / Chef de projet" },
  { value: "architecte",            label: "Architecte / BTP" },
  { value: "conducteur_travaux",    label: "Conducteur de travaux" },
  { value: "daa",                   label: "Data Analyst / BI" },
  { value: "data_scientist",        label: "Data Scientist" },
  { value: "directeur_commercial",  label: "Directeur commercial" },
  { value: "commercial",            label: "Commercial / Business Dev" },
  { value: "entrepreneur",          label: "Entrepreneur / CEO" },
  { value: "consultant",            label: "Consultant" },
  { value: "charge_projets_ong",    label: "Chargé de projets ONG" },
  { value: "coordinateur_ong",      label: "Coordinateur ONG" },
  { value: "responsable_microfinance", label: "Responsable Microfinance (SFD)" },
  { value: "credit_officer",        label: "Credit Officer / IMF" },
  { value: "transitaire",           label: "Transitaire / Commerce international" },
  { value: "douanier",              label: "Douanier / Agent transit" },
  { value: "medecin",               label: "Médecin / Professionnel de santé" },
  { value: "pharmacien",            label: "Pharmacien" },
] as const;

export const PAYS_AFRIQUE = [
  { value: "CM", label: "Cameroun" },
  { value: "CI", label: "Côte d'Ivoire" },
  { value: "SN", label: "Sénégal" },
  { value: "BF", label: "Burkina Faso" },
  { value: "GA", label: "Gabon" },
  { value: "CG", label: "Congo-Brazzaville" },
  { value: "CD", label: "RD Congo" },
  { value: "ML", label: "Mali" },
  { value: "BJ", label: "Bénin" },
  { value: "TG", label: "Togo" },
  { value: "GN", label: "Guinée" },
  { value: "NE", label: "Niger" },
  { value: "CF", label: "Centrafrique" },
  { value: "TD", label: "Tchad" },
  { value: "GQ", label: "Guinée Équatoriale" },
  { value: "MG", label: "Madagascar" },
  { value: "MR", label: "Mauritanie" },
  { value: "BI", label: "Burundi" },
  { value: "RW", label: "Rwanda" },
] as const;

// ── Copilote ──────────────────────────────────────────────────────────────────

export interface CopiloteMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  agent_utilise?: string | null;
  loading?: boolean;
  fichiers?: string[];       // noms des fichiers attachés (user) ou générés (assistant)
  document_ref?: { id: number; titre: string; type: string };  // référence document pour amélioration
}

export interface CopiloteResponse {
  session_id: string;
  reponse: string;
  agent_utilise: string | null;
  resultat_agent: string | null;
  nb_messages_session: number;
  profil_metier: string | null;
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
  { id: "orange_money",  label: "Orange Money",   pays: ["CM","CI","SN","ML","BF","GN","CD","MG"], logo: "🟠" },
  { id: "mtn_momo",     label: "MTN MoMo",        pays: ["CM","CI","BJ","GH","UG","RW"],           logo: "🟡" },
  { id: "wave",         label: "Wave",             pays: ["SN","CI","ML","BF","GN"],               logo: "🔵" },
  { id: "moov_money",   label: "Moov Money",       pays: ["CI","BJ","TG","NE","BF","TD","CF"],     logo: "🟢" },
  { id: "airtel_money", label: "Airtel Money",     pays: ["CD","CG","TD","MG","RW","BI"],          logo: "🔴" },
  { id: "expressunion", label: "Express Union",    pays: ["CM"],                                   logo: "🟤" },
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
