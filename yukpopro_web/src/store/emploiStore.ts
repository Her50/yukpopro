import { create } from "zustand";

/**
 * Persistance Veille Emploi — drafts (CV, profil de recherche) + filtres
 * survivent à la navigation. La config backend est rechargée au mount.
 */

type CvMode = "texte" | "fichier";

interface EmploiState {
  showConfig: boolean;
  profilTexte: string;
  frequence: number;
  cvTexte: string;
  cvMode: CvMode;
  keyword: string;
  expandedIdx: number | null;
  hydratedFromBackend: boolean;

  markHydrated: () => void;
  setShowConfig: (v: boolean) => void;
  setProfilTexte: (v: string) => void;
  setFrequence: (v: number) => void;
  setCvTexte: (v: string) => void;
  setCvMode: (v: CvMode) => void;
  setKeyword: (v: string) => void;
  setExpandedIdx: (v: number | null) => void;
}

export const useEmploiStore = create<EmploiState>((set) => ({
  showConfig: false,
  profilTexte: "",
  frequence: 24,
  cvTexte: "",
  cvMode: "texte",
  keyword: "",
  expandedIdx: null,
  hydratedFromBackend: false,

  markHydrated: () => set({ hydratedFromBackend: true }),
  setShowConfig: (v) => set({ showConfig: v }),
  setProfilTexte: (v) => set({ profilTexte: v }),
  setFrequence: (v) => set({ frequence: v }),
  setCvTexte: (v) => set({ cvTexte: v }),
  setCvMode: (v) => set({ cvMode: v }),
  setKeyword: (v) => set({ keyword: v }),
  setExpandedIdx: (v) => set({ expandedIdx: v }),
}));
