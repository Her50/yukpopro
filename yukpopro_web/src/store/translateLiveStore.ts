import { create } from "zustand";
import {
  TranslateLiveClient,
  type SourceMode,
  type TranslateStatus,
  type TranslateEvent,
} from "@/services/translate_live";
import type { TranslateEventAudio } from "@/services/translate_live";
import { getTTSSpeaker } from "@/services/tts_speaker";

export interface Ligne {
  utteranceId: string;
  source: string;
  translated: string;
  sourceLang: string;
  isFinal: boolean;
  ts: number;
  gender?: "male" | "female";
}

interface TranslateLiveState {
  status: TranslateStatus;
  statusMsg: string;
  lignes: Ligne[];
  currentInterim: string;
  minutesUsed: number;
  creditsUsed: number;
  lastGender: "male" | "female" | null;
  active: boolean;

  start: (opts: {
    token: string;
    source: string;
    target: string;
    sourceMode: SourceMode;
    ttsAvailable: boolean;
    externalStream?: MediaStream;
    onError?: (msg: string) => void;
  }) => Promise<void>;
  stop: () => Promise<void>;
  setTarget: (t: string) => void;
}

// Singleton au niveau module — survit aux démontages React
let _client: TranslateLiveClient | null = null;
const _tts = getTTSSpeaker();

export const useTranslateLiveStore = create<TranslateLiveState>((set, get) => ({
  status: "idle",
  statusMsg: "",
  lignes: [],
  currentInterim: "",
  minutesUsed: 0,
  creditsUsed: 0,
  lastGender: null,
  active: false,

  start: async ({ token, source, target, sourceMode, ttsAvailable, externalStream, onError }) => {
    if (get().active) return;
    set({ lignes: [], currentInterim: "", minutesUsed: 0, creditsUsed: 0, active: true });

    const client = new TranslateLiveClient({
      token,
      source,
      target,
      sourceMode,
      externalStream,
      onStatus: (s, details) => {
        set({ status: s, statusMsg: details || "" });
        if (s === "error" && details && onError) onError(details);
      },
      onEvent: (ev: TranslateEvent) => {
        if (ev.type === "transcript") {
          if (!ev.is_final) {
            set({ currentInterim: ev.text });
            return;
          }
          set((st) => ({
            currentInterim: "",
            lignes: [...st.lignes, {
              utteranceId: ev.utterance_id,
              source: ev.text,
              translated: "",
              sourceLang: ev.lang,
              isFinal: true,
              ts: Date.now(),
            }],
          }));
        } else if (ev.type === "translation") {
          const gender = (ev as any).gender as "male" | "female" | undefined;
          if (gender) set({ lastGender: gender });
          set((st) => ({
            lignes: st.lignes.map((l) =>
              l.utteranceId === ev.utterance_id
                ? { ...l, translated: ev.translated_text, sourceLang: ev.source_lang, gender: gender ?? l.gender }
                : l,
            ),
          }));
          if (!ttsAvailable && ev.translated_text && ev.source_lang !== ev.target_lang) {
            _tts.speak(ev.translated_text, ev.target_lang);
          }
        } else if (ev.type === "audio") {
          set({ lastGender: (ev as TranslateEventAudio).gender });
        } else if ((ev as any).type === "warning") {
          // STT indisponible ou autre avertissement serveur — afficher dans le statusMsg
          const w = ev as any;
          set({ statusMsg: w.message || "Avertissement serveur" });
          if (onError && w.code === "stt_unavailable") onError(w.message);
        } else if (ev.type === "usage") {
          set({ minutesUsed: ev.minutes, creditsUsed: ev.credits_debited_total });
        } else if (ev.type === "error") {
          if (onError) onError(ev.message || "Erreur serveur");
        }
      },
    });
    _client = client;
    try {
      await client.start();
    } catch (err: any) {
      set({ active: false, status: "error" });
      if (onError) onError(err?.message || "Impossible de démarrer la session");
    }
  },

  stop: async () => {
    // Annule l'UI et le TTS immédiatement pour débloquer l'interface,
    // même si la fermeture WebSocket tarde.
    _tts.cancel();
    set({ active: false, status: "idle", currentInterim: "" });
    const client = _client;
    _client = null;
    if (!client) return;
    try {
      await Promise.race([
        client.stop(),
        new Promise((resolve) => setTimeout(resolve, 1500)),
      ]);
    } catch { /* ignore */ }
  },

  setTarget: (t: string) => {
    _client?.setTargetLanguage(t);
  },
}));
