import { create } from "zustand";

/**
 * Persistance Analyse de Données — résultat upload+analyse statistique survit
 * à la navigation. Module-level (pas localStorage : datasets potentiellement gros).
 */

interface AnalyseState {
  loading: boolean;
  fichierNom: string;
  stats: Record<string, unknown> | null;
  renduMarkdown: string;
  apercu: Record<string, unknown>[] | null;

  setLoading: (v: boolean) => void;
  setResult: (r: {
    fichierNom: string;
    stats: Record<string, unknown> | null;
    renduMarkdown: string;
    apercu: Record<string, unknown>[] | null;
  }) => void;
  reset: () => void;
}

export const useAnalyseStore = create<AnalyseState>((set) => ({
  loading: false,
  fichierNom: "",
  stats: null,
  renduMarkdown: "",
  apercu: null,

  setLoading: (v) => set({ loading: v }),
  setResult: ({ fichierNom, stats, renduMarkdown, apercu }) =>
    set({ fichierNom, stats, renduMarkdown, apercu }),
  reset: () => set({ loading: false, fichierNom: "", stats: null, renduMarkdown: "", apercu: null }),
}));
