import { create } from "zustand";
import toast from "react-hot-toast";

/**
 * Persistance des générations Yukpo Studio.
 * Les requêtes tournent au niveau module, indépendantes du cycle de vie React :
 * l'utilisateur peut quitter/revenir à la page, le loading et le résultat sont préservés.
 */

type JobKey = "rapport" | "slides" | "fichiers" | "conversion" | "infographie";

interface GenerateurState {
  tab: string;                         // onglet actif — persiste entre navigations
  loading: Record<JobKey, boolean>;
  resultats: Record<JobKey, any>;

  setTab: (t: string) => void;
  run: <T>(
    key: JobKey,
    fn: () => Promise<T>,
    opts?: { successMsg?: string; errorMsg?: string; onError?: (err: any) => void },
  ) => Promise<T | null>;
  setResultat: (key: JobKey, value: any) => void;
  clear: (key: JobKey) => void;
}

const initialLoading: Record<JobKey, boolean> = {
  rapport: false, slides: false, fichiers: false, conversion: false, infographie: false,
};
const initialResultats: Record<JobKey, any> = {
  rapport: null, slides: null, fichiers: null, conversion: null, infographie: null,
};

export const useGenerateurStore = create<GenerateurState>((set, get) => ({
  tab: "rapport",
  loading: { ...initialLoading },
  resultats: { ...initialResultats },

  setTab: (t) => set({ tab: t }),

  run: async (key, fn, opts) => {
    if (get().loading[key]) return null;
    set((st) => ({
      loading: { ...st.loading, [key]: true },
      resultats: { ...st.resultats, [key]: null },
    }));
    try {
      const res = await fn();
      set((st) => ({
        loading: { ...st.loading, [key]: false },
        resultats: { ...st.resultats, [key]: res },
      }));
      if (opts?.successMsg) toast.success(opts.successMsg);
      return res;
    } catch (err: any) {
      set((st) => ({ loading: { ...st.loading, [key]: false } }));
      if (opts?.onError) opts.onError(err);
      else toast.error(opts?.errorMsg || err?.response?.data?.detail || "Erreur lors de la génération");
      return null;
    }
  },

  setResultat: (key, value) =>
    set((st) => ({ resultats: { ...st.resultats, [key]: value } })),

  clear: (key) =>
    set((st) => ({
      loading: { ...st.loading, [key]: false },
      resultats: { ...st.resultats, [key]: null },
    })),
}));
