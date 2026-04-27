import { create } from "zustand";

/**
 * Persistance navigation + brouillons du module Enquêtes (web).
 * Module-level — survit aux navigations, pas au refresh (par design : les
 * études et leurs détails sont rechargés depuis le backend).
 */

type DetailTab = "audio" | "formulaire" | "collecte" | "analyse" | "rapport";
type FormView = "none" | "builder" | "preview" | "analytics" | "dictionnaire" | "plan";

interface CreateForm {
  titre: string;
  contexte: string;
  methodologie: string;
  mode: string;
  population_cible: string;
  terrain: string;
  questions_recherche: string;
}

interface GenIAForm {
  description: string;
  titre: string;
  objectif: string;
  population: string;
  n_questions: number;
}

interface ProtocoleParams {
  titre: string;
  objectif: string;
  population: string;
  n_questions: number;
}

interface EnqueteState {
  // Navigation
  expandedId: string | null;
  activeTab: DetailTab;
  formView: FormView;
  genIAMode: boolean;

  // Brouillons (préservés pendant la rédaction)
  createForm: CreateForm;
  genIAForm: GenIAForm;
  protocoleParams: ProtocoleParams;

  // Résultats coûteux à régénérer
  formulaire: any | null;
  analyseResult: any | null;
  analyseType: string | null;
  rapport: any | null;

  // Setters
  setExpandedId: (id: string | null) => void;
  setActiveTab: (t: DetailTab) => void;
  setFormView: (v: FormView) => void;
  setGenIAMode: (v: boolean) => void;
  setCreateForm: (f: CreateForm) => void;
  patchCreateForm: (p: Partial<CreateForm>) => void;
  setGenIAForm: (f: GenIAForm) => void;
  patchGenIAForm: (p: Partial<GenIAForm>) => void;
  setProtocoleParams: (p: ProtocoleParams) => void;
  patchProtocoleParams: (p: Partial<ProtocoleParams>) => void;
  setFormulaire: (f: any | null) => void;
  setAnalyseResult: (r: any | null) => void;
  setAnalyseType: (t: string | null) => void;
  setRapport: (r: any | null) => void;
  resetEtudeContext: () => void;
}

const initialCreateForm: CreateForm = {
  titre: "", contexte: "", methodologie: "exploratoire", mode: "qualitatif",
  population_cible: "", terrain: "", questions_recherche: "",
};
const initialGenIAForm: GenIAForm = {
  description: "", titre: "", objectif: "", population: "", n_questions: 15,
};
const initialProtocoleParams: ProtocoleParams = {
  titre: "", objectif: "", population: "", n_questions: 20,
};

export const useEnqueteStore = create<EnqueteState>((set) => ({
  expandedId: null,
  activeTab: "audio",
  formView: "none",
  genIAMode: false,

  createForm: { ...initialCreateForm },
  genIAForm: { ...initialGenIAForm },
  protocoleParams: { ...initialProtocoleParams },

  formulaire: null,
  analyseResult: null,
  analyseType: null,
  rapport: null,

  setExpandedId: (id) => set({ expandedId: id }),
  setActiveTab: (t) => set({ activeTab: t }),
  setFormView: (v) => set({ formView: v }),
  setGenIAMode: (v) => set({ genIAMode: v }),
  setCreateForm: (f) => set({ createForm: f }),
  patchCreateForm: (p) => set((st) => ({ createForm: { ...st.createForm, ...p } })),
  setGenIAForm: (f) => set({ genIAForm: f }),
  patchGenIAForm: (p) => set((st) => ({ genIAForm: { ...st.genIAForm, ...p } })),
  setProtocoleParams: (p) => set({ protocoleParams: p }),
  patchProtocoleParams: (p) => set((st) => ({ protocoleParams: { ...st.protocoleParams, ...p } })),
  setFormulaire: (f) => set({ formulaire: f }),
  setAnalyseResult: (r) => set({ analyseResult: r }),
  setAnalyseType: (t) => set({ analyseType: t }),
  setRapport: (r) => set({ rapport: r }),

  resetEtudeContext: () =>
    set({
      activeTab: "audio",
      formView: "none",
      genIAMode: false,
      formulaire: null,
      analyseResult: null,
      analyseType: null,
      rapport: null,
    }),
}));
