/**
 * Store Zustand pour les agents IA autonomes.
 * Gère : exécutions en cours, historique, connexion SSE.
 */
import { create } from 'zustand'

export type AgentType =
  | 'auto' | 'sinistres' | 'souscription' | 'vie' | 'conformite'
  | 'commercial' | 'rh' | 'juridique' | 'comptabilite' | 'intelligence'
  | 'reassurance' | 'placement' | 'provisions' | 'etats_cima' | 'schema_si' | 'meta_factory'
  | 'deploiement_si' | 'maladie' | 'sinistres_auto' | 'risques_divers'

export type StatutExecution = 'en_cours' | 'termine' | 'erreur' | 'en_attente_validation'

export interface EtapeAgent {
  id: string
  type: 'action' | 'ia' | 'validation' | 'resultat' | 'erreur'
  libelle: string
  detail: string
  statut: 'en_cours' | 'ok' | 'erreur' | 'ia'
  duree_ms: number
  donnees: Record<string, unknown>
  timestamp: string
}

export interface ActionRequise {
  id: string
  outil: string
  params: Record<string, unknown>
  resultat: string
  user_id: number
  execution_id: string
}

export interface ExecutionAgent {
  execution_id: string
  agent: AgentType
  instruction: string
  statut: StatutExecution
  etapes: EtapeAgent[]
  resume: string
  actions_requises: ActionRequise[]
  erreur?: string
  duree_ms: number
  ia_appelee: boolean
  cout_ia_usd: number
  timestamp: string
}

interface AgentState {
  // Exécution courante
  executionCourante: ExecutionAgent | null
  etapesStream: EtapeAgent[]
  enCours: boolean

  // Historique
  historique: ExecutionAgent[]

  // Agent sélectionné
  agentSelectionne: AgentType

  // Actions
  setAgentSelectionne: (agent: AgentType) => void
  setExecutionCourante: (exec: ExecutionAgent | null) => void
  ajouterEtapeStream: (etape: EtapeAgent) => void
  reinitialiserStream: () => void
  setEnCours: (val: boolean) => void
  ajouterHistorique: (exec: ExecutionAgent) => void
}

export const useAgentStore = create<AgentState>((set) => ({
  executionCourante: null,
  etapesStream: [],
  enCours: false,
  historique: [],
  agentSelectionne: 'auto',

  setAgentSelectionne: (agent) => set({ agentSelectionne: agent }),
  setExecutionCourante: (exec) => set({ executionCourante: exec }),
  ajouterEtapeStream: (etape) =>
    set((s) => ({ etapesStream: [...s.etapesStream, etape] })),
  reinitialiserStream: () => set({ etapesStream: [], executionCourante: null }),
  setEnCours: (val) => set({ enCours: val }),
  ajouterHistorique: (exec) =>
    set((s) => ({ historique: [exec, ...s.historique].slice(0, 100) })),
}))
