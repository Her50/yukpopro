import { create } from "zustand";
import toast from "react-hot-toast";

/**
 * Persistance des traductions texte + fichier.
 * La requête tourne au niveau module : l'utilisateur peut quitter la page,
 * la traduction continue et le résultat est dispo au retour.
 */

type Mode = "texte" | "fichier";

export interface ResultatTraduction {
  texte_traduit: string;
  nb_mots_source: number;
  nb_mots_cible: number;
  chemin_docx?: string;
  fichier_traduit?: string;
  format_sortie?: string;
  sauvegarde_mes_documents?: boolean;
  fichier_source?: string;
}

interface TraductionState {
  mode: Mode;
  loading: Record<Mode, boolean>;
  resultats: Record<Mode, ResultatTraduction | null>;

  setMode: (m: Mode) => void;
  run: (
    mode: Mode,
    fn: () => Promise<ResultatTraduction>,
    opts?: { successMsg?: string; errorMsg?: string },
  ) => Promise<ResultatTraduction | null>;
  setResultat: (mode: Mode, r: ResultatTraduction | null) => void;
  clear: (mode: Mode) => void;
}

const initialLoading: Record<Mode, boolean> = { texte: false, fichier: false };
const initialResultats: Record<Mode, ResultatTraduction | null> = { texte: null, fichier: null };

export const useTraductionStore = create<TraductionState>((set, get) => ({
  mode: "texte",
  loading: { ...initialLoading },
  resultats: { ...initialResultats },

  setMode: (m) => set({ mode: m }),

  run: async (mode, fn, opts) => {
    if (get().loading[mode]) return null;
    set((st) => ({
      loading: { ...st.loading, [mode]: true },
      resultats: { ...st.resultats, [mode]: null },
    }));
    try {
      const res = await fn();
      set((st) => ({
        loading: { ...st.loading, [mode]: false },
        resultats: { ...st.resultats, [mode]: res },
      }));
      if (opts?.successMsg) toast.success(opts.successMsg);
      return res;
    } catch (err: any) {
      set((st) => ({ loading: { ...st.loading, [mode]: false } }));
      const raw = err?.response?.data?.detail ?? err?.response?.data?.message ?? err?.message;
      let msg: string;
      if (typeof raw === "string") {
        msg = raw;
      } else if (Array.isArray(raw)) {
        msg = raw.map((e: any) => e?.msg || e?.message || JSON.stringify(e)).join(" ; ");
      } else if (raw && typeof raw === "object") {
        msg = raw.msg || raw.message || JSON.stringify(raw);
      } else {
        msg = opts?.errorMsg || "Erreur lors de la traduction";
      }
      toast.error(msg.slice(0, 200));
      return null;
    }
  },

  setResultat: (mode, r) => set((st) => ({ resultats: { ...st.resultats, [mode]: r } })),
  clear: (mode) => set((st) => ({
    loading: { ...st.loading, [mode]: false },
    resultats: { ...st.resultats, [mode]: null },
  })),
}));
