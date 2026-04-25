import { create } from "zustand";
import type { AgentChatResponse } from "@/types";

/**
 * Persistance Agents Métiers — sélection agent, drafts, dernière réponse
 * survivent à la navigation (typique : poser une question longue, naviguer
 * dans Yukpo Studio le temps de la réponse, revenir lire le résultat).
 */

interface AgentsState {
  selectedAgent: string;
  message: string;
  resultat: AgentChatResponse | null;
  showEtapes: boolean;
  rechercheQuery: string;
  rechercheResult: string | null;

  setSelectedAgent: (v: string) => void;
  setMessage: (v: string) => void;
  setResultat: (v: AgentChatResponse | null) => void;
  setShowEtapes: (v: boolean) => void;
  setRechercheQuery: (v: string) => void;
  setRechercheResult: (v: string | null) => void;
}

export const useAgentsStore = create<AgentsState>((set) => ({
  selectedAgent: "comptable",
  message: "",
  resultat: null,
  showEtapes: false,
  rechercheQuery: "",
  rechercheResult: null,

  setSelectedAgent: (v) => set({ selectedAgent: v }),
  setMessage: (v) => set({ message: v }),
  setResultat: (v) => set({ resultat: v }),
  setShowEtapes: (v) => set({ showEtapes: v }),
  setRechercheQuery: (v) => set({ rechercheQuery: v }),
  setRechercheResult: (v) => set({ rechercheResult: v }),
}));
