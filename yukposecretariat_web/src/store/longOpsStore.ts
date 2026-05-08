import { create } from 'zustand'

/**
 * Store module-level pour les opérations longues (OCR, Audio, Infographie,
 * Traduction, Rédaction, Devis). Survit au démontage des pages — l'utilisateur
 * peut naviguer ailleurs puis revenir sans perdre le loading, le résultat
 * ni les champs du formulaire.
 *
 * Chaque clé représente une page/opération. Les `forms[key]` sont des
 * dictionnaires génériques : chaque page pousse les champs qu'elle gère.
 */

export type LongOpKey = 'ocr' | 'audio' | 'infographie' | 'traduction' | 'redaction' | 'devis' | 'docameliore'

interface LongOpsState {
  forms: Record<LongOpKey, Record<string, any>>
  loading: Record<LongOpKey, boolean>
  resultats: Record<LongOpKey, any | null>

  setField: (key: LongOpKey, name: string, value: any) => void
  setForm: (key: LongOpKey, patch: Record<string, any>) => void
  getField: <T = any>(key: LongOpKey, name: string, fallback?: T) => T
  setResultat: (key: LongOpKey, resultat: any | null) => void
  run: <T>(key: LongOpKey, fn: () => Promise<T>) => Promise<T | null>
  reset: (key: LongOpKey) => void
}

const emptyForms = (): LongOpsState['forms'] => ({
  ocr: {}, audio: {}, infographie: {}, traduction: {}, redaction: {}, devis: {}, docameliore: {},
})
const emptyLoading = (): LongOpsState['loading'] => ({
  ocr: false, audio: false, infographie: false, traduction: false, redaction: false, devis: false, docameliore: false,
})
const emptyResultats = (): LongOpsState['resultats'] => ({
  ocr: null, audio: null, infographie: null, traduction: null, redaction: null, devis: null, docameliore: null,
})

export const useLongOps = create<LongOpsState>((set, get) => ({
  forms: emptyForms(),
  loading: emptyLoading(),
  resultats: emptyResultats(),

  setField: (key, name, value) => set((s) => ({
    forms: { ...s.forms, [key]: { ...s.forms[key], [name]: value } },
  })),

  setForm: (key, patch) => set((s) => ({
    forms: { ...s.forms, [key]: { ...s.forms[key], ...patch } },
  })),

  getField: (key, name, fallback) => {
    const v = get().forms[key]?.[name]
    return (v === undefined ? fallback : v) as any
  },

  setResultat: (key, resultat) => set((s) => ({
    resultats: { ...s.resultats, [key]: resultat },
  })),

  run: async (key, fn) => {
    if (get().loading[key]) return null
    set((s) => ({ loading: { ...s.loading, [key]: true } }))
    try {
      const out = await fn()
      set((s) => ({ resultats: { ...s.resultats, [key]: out } }))
      return out
    } finally {
      set((s) => ({ loading: { ...s.loading, [key]: false } }))
    }
  },

  reset: (key) => set((s) => ({
    forms: { ...s.forms, [key]: {} },
    loading: { ...s.loading, [key]: false },
    resultats: { ...s.resultats, [key]: null },
  })),
}))

/** Helper : sélecteur typé pour un champ de formulaire. */
export function useLongOpField<T = any>(key: LongOpKey, name: string, fallback: T): [T, (v: T) => void] {
  const value = useLongOps((s) => (s.forms[key]?.[name] ?? fallback) as T)
  const setField = useLongOps((s) => s.setField)
  return [value, (v: T) => setField(key, name, v)]
}
