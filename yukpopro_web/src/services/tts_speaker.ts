/**
 * YukpoTranslate Live — lecteur vocal (TTS) utilisant l'API Web Speech du navigateur.
 *
 * Gratuit, universel (Chrome, Edge, Safari, Firefox), sans latence réseau.
 * Qualité moyenne pour le FR/EN, basique pour l'arabe/portugais/africain.
 * Pour une qualité studio → brancher Azure Neural TTS ou ElevenLabs (cf. docs).
 */

export interface TTSSpeaker {
  /** Ajoute un texte à la file d'attente vocale. */
  speak(text: string, lang: string): void;
  /** Interrompt immédiatement la lecture et vide la file d'attente. */
  cancel(): void;
  /** Vérifie si l'API est supportée par le navigateur. */
  isSupported(): boolean;
  /** Active ou désactive la lecture. */
  setEnabled(enabled: boolean): void;
}

const LANG_MAP: Record<string, string> = {
  fr: "fr-FR", en: "en-US", es: "es-ES", pt: "pt-BR", de: "de-DE",
  it: "it-IT", ar: "ar-SA", zh: "zh-CN", ja: "ja-JP", ru: "ru-RU",
  sw: "sw-KE", ha: "ha-NE", yo: "yo-NG", wo: "fr-FR",  // Wolof → FR fallback
  ln: "fr-FR", dua: "fr-FR",                            // Lingala/Douala fallback
};

class WebSpeechSpeaker implements TTSSpeaker {
  private enabled = true;
  private queue: { text: string; lang: string }[] = [];
  private speaking = false;
  private voicesCache: SpeechSynthesisVoice[] = [];

  constructor() {
    if (this.isSupported()) {
      const refresh = () => {
        this.voicesCache = window.speechSynthesis.getVoices();
      };
      refresh();
      window.speechSynthesis.addEventListener("voiceschanged", refresh);
    }
  }

  isSupported(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    if (!enabled) this.cancel();
  }

  speak(text: string, lang: string): void {
    if (!this.enabled || !text.trim() || !this.isSupported()) return;
    this.queue.push({ text: text.trim(), lang });
    this._pump();
  }

  cancel(): void {
    this.queue = [];
    if (this.isSupported()) {
      try { window.speechSynthesis.cancel(); } catch { /* ignore */ }
    }
    this.speaking = false;
  }

  private _pump(): void {
    if (this.speaking || this.queue.length === 0) return;
    const { text, lang } = this.queue.shift()!;
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = LANG_MAP[lang] || lang || "fr-FR";
    utter.rate = 1.05;
    utter.pitch = 1.0;
    utter.volume = 1.0;

    // Choix de la meilleure voix disponible pour cette langue
    const voice = this.voicesCache.find(
      (v) => v.lang.toLowerCase().startsWith(utter.lang.toLowerCase().slice(0, 2)),
    );
    if (voice) utter.voice = voice;

    utter.onend = () => {
      this.speaking = false;
      this._pump();
    };
    utter.onerror = () => {
      this.speaking = false;
      this._pump();
    };

    this.speaking = true;
    try {
      window.speechSynthesis.speak(utter);
    } catch {
      this.speaking = false;
    }
  }
}

let _instance: TTSSpeaker | null = null;

export function getTTSSpeaker(): TTSSpeaker {
  if (!_instance) _instance = new WebSpeechSpeaker();
  return _instance;
}
