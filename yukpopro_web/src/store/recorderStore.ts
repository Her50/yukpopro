import { create } from "zustand";
import { acquireWakeLock, releaseWakeLock } from "@/utils/wakeLock";

// ── Enregistrement audio persistant ──────────────────────────────────────────
// Les ressources (MediaRecorder, MediaStream, timer) vivent au niveau module
// pour survivre aux démontages React lors de la navigation.

let _mediaRecorder: MediaRecorder | null = null;
let _stream: MediaStream | null = null;
let _chunks: Blob[] = [];
let _timer: ReturnType<typeof setInterval> | null = null;
let _speechRecognition: any = null;

interface RecorderState {
  isRecording: boolean;
  isPaused: boolean;
  duration: number;
  audioBlob: Blob | null;
  mimeType: string;
  supported: boolean;
  liveSpeech: string;

  start: (langue: string) => Promise<void>;
  pause: () => void;
  resume: () => void;
  stop: () => Promise<Blob | null>;
  reset: () => void;
  setLiveSpeech: (t: string) => void;
}

/** Retourne le MediaStream actif (null si aucun enregistrement). */
export const getRecorderStream = (): MediaStream | null => _stream;

const _tick = () => {
  _timer = setInterval(() => {
    useRecorderStore.setState((s) => ({ duration: s.duration + 1 }));
  }, 1000);
};

const _stopTimer = () => {
  if (_timer) { clearInterval(_timer); _timer = null; }
};

export const useRecorderStore = create<RecorderState>((set, get) => ({
  isRecording: false,
  isPaused: false,
  duration: 0,
  audioBlob: null,
  mimeType: "",
  supported: typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia,
  liveSpeech: "",

  start: async (langue: string) => {
    if (get().isRecording) return;
    try {
      const audioConstraints: MediaTrackConstraints = {
        echoCancellation: { ideal: true },
        noiseSuppression: { ideal: true },
        autoGainControl: { ideal: true },
        sampleRate: { ideal: 48000 },
        channelCount: { ideal: 2 },
      };
      try {
        _stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
      } catch {
        _stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      const mimeType =
        ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm", "audio/mp4"]
          .find((m) => MediaRecorder.isTypeSupported(m)) || "";
      const mr = new MediaRecorder(_stream, mimeType ? { mimeType, audioBitsPerSecond: 128_000 } : {});
      _mediaRecorder = mr;
      _chunks = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) _chunks.push(e.data); };
      mr.start(500);
      set({ isRecording: true, isPaused: false, duration: 0, audioBlob: null, mimeType: mimeType || "audio/webm", liveSpeech: "" });
      _stopTimer();
      _tick();
      // Empêche l'écran de s'éteindre pendant l'enregistrement (Chrome/Edge/Android).
      // Sur iOS Safari : pas supporté → no-op silencieux, l'utilisateur doit garder l'écran allumé.
      acquireWakeLock();

      // SpeechRecognition best-effort pour live
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SR) {
        try {
          const r = new SR();
          _speechRecognition = r;
          r.lang = langue === "auto" ? (navigator.language || "fr-FR") : `${langue}-${langue.toUpperCase()}`;
          r.continuous = true;
          r.interimResults = true;
          r.onresult = (e: any) => {
            const transcript = Array.from(e.results).map((res: any) => res[0].transcript).join(" ");
            useRecorderStore.setState({ liveSpeech: transcript });
          };
          r.onerror = () => {};
          r.onend = () => {};
          r.start();
        } catch { /* ignore */ }
      }
    } catch {
      set({ supported: false });
      throw new Error("Microphone inaccessible");
    }
  },

  pause: () => {
    if (_mediaRecorder?.state === "recording") {
      _mediaRecorder.pause();
      _stopTimer();
      set({ isPaused: true });
    }
  },

  resume: () => {
    if (_mediaRecorder?.state === "paused") {
      _mediaRecorder.resume();
      _tick();
      set({ isPaused: false });
    }
  },

  stop: () => new Promise<Blob | null>((resolve) => {
    _stopTimer();
    try { _speechRecognition?.stop(); } catch { /* ignore */ }
    _speechRecognition = null;
    const mr = _mediaRecorder;
    if (!mr || mr.state === "inactive") {
      set({ isRecording: false, isPaused: false });
      releaseWakeLock();
      resolve(null);
      return;
    }
    mr.onstop = () => {
      _stream?.getTracks().forEach((t) => t.stop());
      _stream = null;
      const blob = new Blob(_chunks, { type: mr.mimeType || "audio/webm" });
      _mediaRecorder = null;
      set({ audioBlob: blob, isRecording: false, isPaused: false });
      releaseWakeLock();
      resolve(blob);
    };
    mr.stop();
  }),

  reset: () => {
    _stopTimer();
    try { _speechRecognition?.stop(); } catch { /* ignore */ }
    _speechRecognition = null;
    if (_mediaRecorder && _mediaRecorder.state !== "inactive") {
      try { _mediaRecorder.stop(); } catch { /* ignore */ }
    }
    _stream?.getTracks().forEach((t) => t.stop());
    _stream = null;
    _mediaRecorder = null;
    _chunks = [];
    releaseWakeLock();
    set({ isRecording: false, isPaused: false, duration: 0, audioBlob: null, mimeType: "", liveSpeech: "" });
  },

  setLiveSpeech: (t: string) => set({ liveSpeech: t }),
}));
