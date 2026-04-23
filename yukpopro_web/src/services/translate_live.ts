/**
 * YukpoTranslate Live — client TypeScript.
 *
 * Responsabilités :
 *  - ouvrir la WebSocket `/api/v1/translate/live/ws?token=...`
 *  - capturer l'audio (micro ou onglet/écran)
 *  - downsampler vers PCM16 16 kHz mono via AudioWorklet, puis forward au WS
 *  - exposer un stream d'événements (transcripts, translations, usage, erreurs)
 *  - gérer reconnexion douce et heartbeat (ping 30 s)
 *
 * Protocole : voir docs/translate_live_spec.md §3.
 */

export type SourceMode = "microphone" | "display";
export type TranslateStatus =
  | "idle"
  | "connecting"
  | "ready"
  | "streaming"
  | "stopping"
  | "closed"
  | "error";

export interface TranslateEventReady {
  type: "ready";
  session_id: string;
  source: string;
  target: string;
  stt_available: boolean;
  credits_per_minute: number;
}
export interface TranslateEventTranscript {
  type: "transcript";
  text: string;
  lang: string;
  is_final: boolean;
  utterance_id: string;
}
export interface TranslateEventTranslation {
  type: "translation";
  source_text: string;
  translated_text: string;
  source_lang: string;
  target_lang: string;
  utterance_id: string;
}
export interface TranslateEventUsage {
  type: "usage";
  minutes: number;
  credits_debited_total: number;
  credits_debited_last: number;
}
export interface TranslateEventError {
  type: "error";
  code: string;
  message: string;
}
export type TranslateEvent =
  | TranslateEventReady
  | TranslateEventTranscript
  | TranslateEventTranslation
  | TranslateEventUsage
  | TranslateEventError
  | { type: "pong" }
  | { type: "stopped" }
  | { type: "config_ack"; source: string; target: string };

export interface TranslateLiveOptions {
  token: string;
  source: string;              // "auto" ou ISO 639-1
  target: string;              // ISO 639-1
  sourceMode: SourceMode;
  onEvent: (e: TranslateEvent) => void;
  onStatus: (status: TranslateStatus, details?: string) => void;
}

export class TranslateLiveClient {
  private ws: WebSocket | null = null;
  private audioCtx: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private mediaStream: MediaStream | null = null;
  private heartbeat: number | null = null;
  private opts: TranslateLiveOptions;
  private status: TranslateStatus = "idle";
  private stopping = false;

  constructor(opts: TranslateLiveOptions) {
    this.opts = opts;
  }

  getStatus(): TranslateStatus {
    return this.status;
  }

  private setStatus(s: TranslateStatus, details?: string) {
    this.status = s;
    this.opts.onStatus(s, details);
  }

  async start(): Promise<void> {
    if (this.status !== "idle" && this.status !== "closed" && this.status !== "error") {
      return;
    }
    this.stopping = false;
    this.setStatus("connecting");

    try {
      await this._acquireMedia();
      await this._connectWS();
      await this._setupAudioPipeline();
      this.setStatus("streaming");
    } catch (err: any) {
      const msg = err?.message || String(err);
      this.setStatus("error", msg);
      await this.stop();
      throw err;
    }
  }

  async stop(): Promise<void> {
    if (this.stopping) return;
    this.stopping = true;
    this.setStatus("stopping");

    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
    try {
      this.ws?.send(JSON.stringify({ type: "stop" }));
    } catch {/* ignore */}

    try {
      this.workletNode?.disconnect();
    } catch {/* ignore */}
    this.workletNode = null;

    if (this.audioCtx) {
      try {
        await this.audioCtx.close();
      } catch {/* ignore */}
      this.audioCtx = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }

    try {
      this.ws?.close(1000, "client stop");
    } catch {/* ignore */}
    this.ws = null;

    this.setStatus("closed");
  }

  setTargetLanguage(target: string): void {
    this.opts.target = target;
    try {
      this.ws?.send(JSON.stringify({ type: "config", target }));
    } catch {/* ignore */}
  }

  // ── Internals ──────────────────────────────────────────────────────────

  private async _acquireMedia(): Promise<void> {
    if (this.opts.sourceMode === "display") {
      if (!(navigator.mediaDevices as any).getDisplayMedia) {
        throw new Error("Capture d'onglet non supportée par ce navigateur");
      }
      // NOTE: Chrome/Edge — utilisateur doit choisir onglet + activer « partager l'audio »
      const stream = await (navigator.mediaDevices as any).getDisplayMedia({
        audio: true,
        video: { width: 1, height: 1 },  // video minimal (non utilisée mais requis)
      });
      const audioTracks = stream.getAudioTracks();
      if (audioTracks.length === 0) {
        stream.getTracks().forEach((t: MediaStreamTrack) => t.stop());
        throw new Error(
          "Aucune piste audio partagée. Cochez « Partager l'audio » dans la boîte de dialogue.",
        );
      }
      // Arrête la piste vidéo inutile, on garde audio
      stream.getVideoTracks().forEach((t: MediaStreamTrack) => t.stop());
      this.mediaStream = new MediaStream(audioTracks);
    } else {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    }
  }

  private async _connectWS(): Promise<void> {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/api/v1/translate/live/ws`
      + `?token=${encodeURIComponent(this.opts.token)}`
      + `&source=${encodeURIComponent(this.opts.source)}`
      + `&target=${encodeURIComponent(this.opts.target)}`;

    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      let opened = false;

      ws.onopen = () => {
        opened = true;
        this.heartbeat = window.setInterval(() => {
          try { ws.send("ping"); } catch {/* ignore */}
        }, 30_000);
      };

      ws.onmessage = (ev) => {
        if (typeof ev.data !== "string") return;
        try {
          const obj = JSON.parse(ev.data) as TranslateEvent;
          if (obj.type === "ready") {
            this.setStatus("ready");
            resolve();
          } else if (obj.type === "error") {
            this.opts.onEvent(obj);
          } else {
            this.opts.onEvent(obj);
          }
        } catch {/* ignore non-JSON */}
      };

      ws.onerror = () => {
        if (!opened) reject(new Error("Connexion WebSocket impossible"));
      };

      ws.onclose = (ev) => {
        if (this.heartbeat) {
          clearInterval(this.heartbeat);
          this.heartbeat = null;
        }
        if (!this.stopping) {
          const codeMsg =
            ev.code === 4001 ? "Non authentifié" :
            ev.code === 4002 ? "Crédits épuisés" :
            ev.code === 4003 ? "Trop de sessions simultanées" :
            ev.code === 4005 ? "Plafond mensuel atteint" :
            ev.code === 4100 ? "Service de transcription indisponible" :
            `Connexion fermée (${ev.code})`;
          this.setStatus("error", codeMsg);
        }
        if (!opened) reject(new Error("WebSocket fermée avant d'être prête"));
      };

      this.ws = ws;
    });
  }

  private async _setupAudioPipeline(): Promise<void> {
    if (!this.mediaStream || !this.ws) return;
    this.audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    await this.audioCtx.audioWorklet.addModule("/worklets/pcm-worklet.js");

    const source = this.audioCtx.createMediaStreamSource(this.mediaStream);
    const node = new AudioWorkletNode(this.audioCtx, "pcm-worklet");

    node.port.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      try {
        this.ws.send(ev.data);
      } catch {/* ignore */}
    };

    source.connect(node);
    // Ne PAS connecter node à destination — on ne veut pas écho/re-lecture
    this.workletNode = node;
  }
}
