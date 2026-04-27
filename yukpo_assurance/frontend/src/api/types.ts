// Auth
export interface LoginCredentials {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: number
  email: string
  nom: string
  prenom: string
  role: string
  compagnie?: string
}

// Chat
export interface ChatSession {
  id: string
  titre: string
  created_at: string
  updated_at: string
  messages_count?: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  session_id: string
  metadata?: Record<string, unknown>
}

export interface SendMessageRequest {
  session_id: string
  content: string
  fichiers?: string[]
}

export interface SendMessageResponse {
  message: ChatMessage
  session_id: string
}

// Analytics / Dashboard
export interface DashboardData {
  primes_nettes: number
  ratio_sp: number
  marge_solvabilite: number
  polices_actives: number
  primes_par_branche: BrancheData[]
  repartition_charges: ChargeData[]
  alertes_cima: AlerteCIMA[]
  narrative_ia: string
  annee: number
}

export interface BrancheData {
  branche: string
  primes: number
  sinistres: number
}

export interface ChargeData {
  categorie: string
  montant: number
  pourcentage: number
}

export interface AlerteCIMA {
  id: string
  type: 'warning' | 'error' | 'info'
  message: string
  echeance?: string
  ratio?: string
}

// Sinistres
export type StatutSinistre = 'ouvert' | 'en_cours' | 'expertise_en_cours' | 'relance' | 'contentieux' | 'accord' | 'clos' | 'rejet'
export type BrancheAssurance = 'auto' | 'vie' | 'mrh' | 'sante' | 'transport' | 'rc'

export interface EtapeWorkflow {
  id: string
  label: string
  date?: string
  statut: 'fait' | 'en_cours' | 'en_attente' | 'na'
}

export interface Sinistre {
  id: string
  numero: string
  branche: BrancheAssurance
  statut: StatutSinistre
  date_sinistre: string
  date_declaration: string
  montant_estime: number
  montant_regle?: number
  assure_nom: string
  assure_email?: string
  description: string
  score_fraude?: number
  police_numero?: string
  etapes_workflow?: EtapeWorkflow[]
}

export interface DeclarerSinistreRequest {
  branche: BrancheAssurance
  date_sinistre: string
  description: string
  montant_estime: number
  assure_nom: string
  assure_email?: string
  police_numero?: string
  documents?: string[]
}

export interface ScoreFraude {
  score: number
  niveau: 'faible' | 'moyen' | 'eleve'
  facteurs: string[]
  recommandation: string
}

// Documents
export type TypeDocument = 'docx' | 'pdf' | 'pptx' | 'excel'

export interface GenererDocumentRequest {
  prompt: string
  type_document: TypeDocument
  contexte?: string
}

export interface GenererDocumentResponse {
  url: string
  nom_fichier: string
  type: TypeDocument
  taille_octets: number
  preview_url?: string
}

// CIMA
export interface RatioCIMA {
  nom: string
  valeur: number
  seuil_min?: number
  seuil_max?: number
  unite: string
  conforme: boolean
  description: string
}

export interface QuestionCIMARequest {
  question: string
  contexte?: string
}

export interface QuestionCIMAResponse {
  reponse: string
  sources: string[]
  articles_cites?: string[]
}

// Courtiers
export interface TableauBordCourtier {
  production_mensuelle: number
  commissions_dues: number
  portefeuille_actif: number
  top_produits: ProduitPerformance[]
  evolution_production: EvolutionData[]
}

export interface ProduitPerformance {
  produit: string
  primes: number
  contrats: number
}

export interface EvolutionData {
  mois: string
  production: number
  objectif: number
}

// RH
export interface Employe {
  id: string
  matricule: string
  nom: string
  prenom: string
  poste: string
  departement: string
  date_embauche: string
  salaire_brut: number
  statut: 'actif' | 'inactif' | 'conge'
  email: string
}

// Commercial
export interface Prospect {
  id: string
  nom: string
  email?: string
  telephone?: string
  branche_interet: BrancheAssurance
  etape: 'lead' | 'contact' | 'proposition' | 'negociation' | 'gagne' | 'perdu'
  valeur_estimee: number
  date_creation: string
  commercial_assigne?: string
  notes?: string
}

// Souscription
export interface SouscriptionRequest {
  branche: BrancheAssurance
  client_nom: string
  client_email: string
  client_telephone: string
  client_adresse: string
  date_naissance?: string
  details_risque: Record<string, unknown>
  documents?: string[]
}

export interface SouscriptionResponse {
  numero_police: string
  prime_annuelle: number
  prime_mensuelle: number
  date_effet: string
  date_echeance: string
  garanties: Garantie[]
  statut: 'en_attente' | 'accepte' | 'refuse'
}

export interface Garantie {
  nom: string
  capital_garanti: number
  franchise?: number
}

// Generic API response
export interface ApiError {
  detail: string
  code?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}
