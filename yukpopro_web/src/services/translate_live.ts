/// <reference types="vite/client" />
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
export interface TranslateEventAudio {
  type: "audio";
  utterance_id: string;
  gender: "male" | "female";
  format: "mp3";
  audioBlob: Blob;
}

export type TranslateEvent =
  | TranslateEventReady
  | TranslateEventTranscript
  | TranslateEventTranslation
  | TranslateEventUsage
  | TranslateEventError
  | TranslateEventAudio
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
  private playbackCtx: AudioContext | null = null;  // contexte dédié lecture TTS (déverrouillé pendant start())
  private workletNode: AudioWorkletNode | null = null;
  private mediaStream: MediaStream | null = null;
  private heartbeat: number | null = null;
  private opts: TranslateLiveOptions;
  private status: TranslateStatus = "idle";
  private stopping = false;
  private _playQueue: ArrayBuffer[] = [];
  private _playing = false;

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
    this._playQueue = [];
    this._playing = false;
    this.setStatus("connecting");

    try {
      // Déverrouiller l'AudioContext pendant le geste utilisateur (clic Start)
      // → autorise la lecture audio depuis les callbacks WebSocket qui arrivent ensuite
      await this._unlockPlaybackCtx();
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
      try { await this.audioCtx.close(); } catch {/* ignore */}
      this.audioCtx = null;
    }
    if (this.playbackCtx) {
      try { await this.playbackCtx.close(); } catch {/* ignore */}
      this.playbackCtx = null;
    }
    this._playQueue = [];
    this._playing = false;
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

  /** Déverrouille l'AudioContext pendant le geste utilisateur initial. */
  private async _unlockPlaybackCtx(): Promise<void> {
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)() as AudioContext;
      // Jouer un buffer silencieux pour activer le contexte
      const buf = ctx.createBuffer(1, 1, 22050);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(0);
      await ctx.resume();
      this.playbackCtx = ctx;
    } catch {/* ignore — lecture via Audio() sinon */}
  }

  /**
   * Joue des octets MP3 via WebAudio (résiste à la politique autoplay Chrome).
   * Appelé depuis les callbacks WebSocket — fonctionne car le contexte a été
   * déverrouillé pendant le clic Start (geste utilisateur).
   */
  async playMp3Bytes(mp3: ArrayBuffer): Promise<void> {
    this._playQueue.push(mp3);
    if (!this._playing) this._drainQueue();
  }

  private async _drainQueue(): Promise<void> {
    if (this._playing || this._playQueue.length === 0) return;
    this._playing = true;
    const mp3 = this._playQueue.shift()!;
    try {
      const ctx = this.playbackCtx;
      if (ctx && ctx.state !== "closed") {
        const audioBuf = await ctx.decodeAudioData(mp3.slice(0));
        const src = ctx.createBufferSource();
        src.buffer = audioBuf;
        src.connect(ctx.destination);
        src.onended = () => {
          this._playing = false;
          this._drainQueue();
        };
        src.start(0);
        return;
      }
    } catch {/* fall through to Audio() */}
    // Fallback : HTML Audio element
    try {
      const blob = new Blob([mp3], { type: "audio/mpeg" });
      const url  = URL.createObjectURL(blob);
      const elem = new Audio(url);
      elem.onended = () => { URL.revokeObjectURL(url); this._playing = false; this._drainQueue(); };
      elem.onerror = () => { URL.revokeObjectURL(url); this._playing = false; this._drainQueue(); };
      await elem.play();
    } catch {
      this._playing = false;
      this._drainQueue();
    }
  }

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
    // Vercel ne proxi pas les WebSockets — on pointe directement vers le backend
    const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || "";
    const wsBase = apiBase
      ? apiBase.replace(/^http/, "ws")
      : (location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host;
    const url = `${wsBase}/api/v1/translate/live/ws`
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
        // Message binaire : frame audio ElevenLabs
        // Format : 4 octets (big-endian) longueur meta JSON + meta JSON + MP3
        if (ev.data instanceof ArrayBuffer) {
          try {
            const buf  = new DataView(ev.data);
            const metaLen = buf.getUint32(0, false);  // big-endian
            const metaBytes = new Uint8Array(ev.data, 4, metaLen);
            const meta = JSON.parse(new TextDecoder().decode(metaBytes)) as {
              type: string; utterance_id: string; gender: "male"|"female"; format: string;
            };
            const audioBytes = new Uint8Array(ev.data, 4 + metaLen);
            if (meta.type === "audio") {
              // Lecture directe via WebAudio (contourne autoplay Chrome)
              void this.playMp3Bytes(audioBytes.buffer.slice(audioBytes.byteOffset, audioBytes.byteOffset + audioBytes.byteLength));
              // Notifier la page pour l'indicateur genre
              const audioBlob = new Blob([audioBytes], { type: "audio/mpeg" });
              this.opts.onEvent({ ...meta, type: "audio", audioBlob } as TranslateEventAudio);
            }
          } catch {/* ignore malformed */}
          return;
        }

        if (typeof ev.data !== "string") return;
        try {
          const obj = JSON.parse(ev.data) as TranslateEvent;
          if (obj.type === "ready") {
            this.setStatus("ready");
            resolve();
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
