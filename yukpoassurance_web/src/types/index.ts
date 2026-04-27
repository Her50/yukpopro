// ── Auth & User ───────────────────────────────────────────────────────────────

export type UserRole = "user" | "gestionnaire" | "directeur" | "admin" | "super_admin";

export interface User {
  id: number;
  email: string;
  nom?: string;
  prenom?: string;
  role: UserRole;
  compagnie_id?: number;
  compagnie_nom?: string;
  created_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// ── Chat & Agents ─────────────────────────────────────────────────────────────

export type AgentType =
  | "sinistres" | "souscription" | "comptabilite" | "cima"
  | "reassurance" | "commercial" | "rh" | "juridique" | "copilote";

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  loading?: boolean;
  agent_utilise?: string | null;
  fichiers?: string[];
  actions?: ActionAgent[];
  questions?: QuestionAgent[];
  validations?: ValidationAgent[];
  timestamp?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  messages: ChatMessage[];
}

export interface ActionAgent {
  type: "action" | "validation" | "erreur" | "ia" | "resultat";
  label: string;
  details?: string;
  statut?: "succes" | "echec" | "attente";
}

export interface QuestionAgent {
  question: string;
  type_reponse: "texte_libre" | "choix_multiple" | "images" | "date" | "montant";
  choix?: string[];
  champ_id?: string;
}

export interface ValidationAgent {
  id: string;
  type: string;
  description: string;
  montant?: number;
  reference?: string;
  statut: "pending" | "approved" | "rejected";
}

// ── Sinistres ─────────────────────────────────────────────────────────────────

export type StatutSinistre =
  | "ouvert" | "en_cours" | "expertise_en_cours"
  | "relance" | "contentieux" | "accord" | "clos" | "rejet";

export type BrancheAssurance = "auto" | "vie" | "mrh" | "sante" | "transport" | "rc";

export interface EtapeWorkflow {
  id: string;
  label: string;
  date?: string;
  statut: "fait" | "en_cours" | "en_attente" | "na";
}

export interface Sinistre {
  id: string;
  numero: string;
  branche: BrancheAssurance;
  statut: StatutSinistre;
  date_sinistre: string;
  date_declaration: string;
  montant_estime: number;
  montant_regle?: number;
  assure_nom: string;
  assure_email?: string;
  description: string;
  score_fraude?: number;
  police_numero?: string;
  etapes_workflow?: EtapeWorkflow[];
}

// ── Documents ─────────────────────────────────────────────────────────────────

export interface DocGenere {
  id: string;
  backendId?: number;
  titre: string;
  type: string;
  contenu?: string;
  fichier?: string;
  createdAt: string;
  meta?: Record<string, unknown>;
}

// ── Dashboard KPIs ────────────────────────────────────────────────────────────

export interface KpiDashboard {
  primes_nettes_fcfa: number;
  ratio_sp_pct: number;
  marge_solvabilite_pct: number;
  polices_actives: number;
  sinistres_ouverts: number;
  sinistres_en_souffrance: number;
  taux_fraude_pct: number;
  reservations_cima_fcfa: number;
}

// ── Validations ───────────────────────────────────────────────────────────────

export interface ValidationItem {
  id: string;
  type: string;
  description: string;
  montant?: number;
  reference?: string;
  agent?: string;
  statut: "pending" | "approved" | "rejected";
  created_at: string;
  user_id?: number;
}

// ── Abonnement ────────────────────────────────────────────────────────────────

export type PlanAssurance = "decouverte" | "essentiel" | "professionnel" | "entreprise";

export const PLANS_ASSURANCE: Record<PlanAssurance, {
  label: string; prix_fcfa: number; agents: string[]; limite_sinistres: number;
}> = {
  decouverte:    { label: "Découverte",    prix_fcfa: 0,       agents: ["copilote"], limite_sinistres: 5 },
  essentiel:     { label: "Essentiel",     prix_fcfa: 25000,   agents: ["copilote", "sinistres", "souscription"], limite_sinistres: 50 },
  professionnel: { label: "Professionnel", prix_fcfa: 75000,   agents: ["sinistres", "souscription", "comptabilite", "cima", "reassurance"], limite_sinistres: 500 },
  entreprise:    { label: "Entreprise",    prix_fcfa: 200000,  agents: ["tous"], limite_sinistres: -1 },
};

// ── Pays & Données CIMA ───────────────────────────────────────────────────────

export const PAYS_CIMA = [
  "Bénin", "Burkina Faso", "Cameroun", "Centrafrique", "Comores",
  "Congo", "Côte d'Ivoire", "Gabon", "Guinée Bissau", "Guinée Équatoriale",
  "Madagascar", "Mali", "Niger", "RCA", "Rwanda",
  "Sénégal", "Tchad", "Togo",
];
