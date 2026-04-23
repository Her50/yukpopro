import { create } from "zustand";

/**
 * Persistance du formulaire de nouvelle réunion (titre, notes, participants, langue…)
 * entre les ouvertures/fermetures de la modale ET entre les navigations de page.
 * L'enregistrement audio tourne en parallèle via recorderStore — les deux doivent survivre.
 */

export interface ParticipantForm { nom: string; role?: string; }

interface ReunionFormState {
  isOpen: boolean;

  titre: string;
  date: string;
  notes: string;
  participants: ParticipantForm[];
  langue: string;
  langueCible: string;
  traduireLive: boolean;
  transcriptionDone: boolean;

  open: () => void;
  close: () => void;
  reset: () => void;

  setTitre: (v: string) => void;
  setDate: (v: string) => void;
  setNotes: (v: string | ((prev: string) => string)) => void;
  setParticipants: (p: ParticipantForm[]) => void;
  setLangue: (v: string) => void;
  setLangueCible: (v: string) => void;
  setTraduireLive: (v: boolean) => void;
  setTranscriptionDone: (v: boolean) => void;
}

const todayStr = () => new Date().toISOString().slice(0, 10);

const initial = {
  titre: "",
  date: todayStr(),
  notes: "",
  participants: [{ nom: "", role: "" }] as ParticipantForm[],
  langue: "auto",
  langueCible: "fr",
  traduireLive: false,
  transcriptionDone: false,
};

export const useReunionFormStore = create<ReunionFormState>((set, get) => ({
  isOpen: false,
  ...initial,

  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  reset: () => set({ isOpen: false, ...initial, date: todayStr() }),

  setTitre: (v) => set({ titre: v }),
  setDate: (v) => set({ date: v }),
  setNotes: (v) =>
    set({ notes: typeof v === "function" ? (v as (p: string) => string)(get().notes) : v }),
  setParticipants: (p) => set({ participants: p }),
  setLangue: (v) => set({ langue: v }),
  setLangueCible: (v) => set({ langueCible: v }),
  setTraduireLive: (v) => set({ traduireLive: v }),
  setTranscriptionDone: (v) => set({ transcriptionDone: v }),
}));
