import { create } from "zustand";

/**
 * Persistance Marchés Publics — filtres libres survivent à la navigation.
 * La liste des marchés est rechargée depuis le backend au mount.
 */

interface MarchesState {
  keyword: string;
  filtreSecteur: string;
  filtreSource: string;
  showSources: boolean;
  frequence: number;

  setKeyword: (v: string) => void;
  setFiltreSecteur: (v: string) => void;
  setFiltreSource: (v: string) => void;
  setShowSources: (v: boolean) => void;
  setFrequence: (v: number) => void;
  resetFiltres: () => void;
}

export const useMarchesStore = create<MarchesState>((set) => ({
  keyword: "",
  filtreSecteur: "",
  filtreSource: "",
  showSources: false,
  frequence: 6,

  setKeyword: (v) => set({ keyword: v }),
  setFiltreSecteur: (v) => set({ filtreSecteur: v }),
  setFiltreSource: (v) => set({ filtreSource: v }),
  setShowSources: (v) => set({ showSources: v }),
  setFrequence: (v) => set({ frequence: v }),
  resetFiltres: () => set({ keyword: "", filtreSecteur: "", filtreSource: "" }),
}));
