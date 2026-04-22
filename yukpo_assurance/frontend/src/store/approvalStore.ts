/**
 * Store Zustand pour la file de validation humaine.
 */
import { create } from 'zustand'

export type StatutValidation = 'en_attente' | 'approuve' | 'rejete' | 'expire' | 'escalade'

export interface ValidationItem {
  id: string
  type: string
  description: string
  donnees: Record<string, unknown>
  montant: number
  statut: StatutValidation
  user_id: number
  execution_id: string
  validateur_id?: number
  validateur_nom?: string
  commentaire: string
  cree_le: string
  traite_le?: string
  expires_le: string
  peut_reprendre: boolean
  // Champs spécifiques aux questions de clarification
  question?: string
  contexte_question?: string
  choix_possibles?: string[]
  type_reponse?: 'texte_libre' | 'choix_multiple' | 'oui_non' | 'nombre' | 'date' | 'image' | 'images'
  nombre_images_max?: number
  formats_acceptes?: string[]
  medias_urls?: string[]
}

export interface ValidationStats {
  total: number
  en_attente: number
  approuves: number
  rejetes: number
  montant_en_attente_fcfa: number
}

interface ApprovalState {
  items: ValidationItem[]
  stats: ValidationStats
  chargement: boolean
  derniereReprise: { execution_id: string; statut: string; resume: string } | null

  setItems: (items: ValidationItem[]) => void
  setStats: (stats: ValidationStats) => void
  setChargement: (val: boolean) => void
  mettreAJourItem: (id: string, updates: Partial<ValidationItem>) => void
  retirerItem: (id: string) => void
  setDerniereReprise: (reprise: ApprovalState['derniereReprise']) => void
}

export const useApprovalStore = create<ApprovalState>((set) => ({
  items: [],
  stats: { total: 0, en_attente: 0, approuves: 0, rejetes: 0, montant_en_attente_fcfa: 0 },
  chargement: false,
  derniereReprise: null,

  setItems: (items) => set({ items }),
  setStats: (stats) => set({ stats }),
  setChargement: (val) => set({ chargement: val }),
  mettreAJourItem: (id, updates) =>
    set((s) => ({
      items: s.items.map((i) => (i.id === id ? { ...i, ...updates } : i)),
    })),
  retirerItem: (id) =>
    set((s) => ({ items: s.items.filter((i) => i.id !== id) })),
  setDerniereReprise: (reprise) => set({ derniereReprise: reprise }),
}))
