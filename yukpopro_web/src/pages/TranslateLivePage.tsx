/**
 * YukpoTranslate Live — traduction vocale simultanée (Sprint 1 : sous-titres).
 *
 * Capture micro OU onglet/écran → streaming WebSocket → sous-titres bilingues
 * (texte original + texte traduit) live, avec débit crédits à la minute.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  Mic, MonitorSpeaker, Play, Square, Languages, Radio, AlertCircle,
  CheckCircle2, Loader2, Download, Clock, Coins, Info, Copy,
  Volume2, VolumeX, Save,
} from "lucide-react";
import { Card, Button, Select, Badge } from "@/components/ui";
import { DemoBanner } from "@/components/DemoBanner";
import http from "@/api/client";
import { useAuthStore } from "@/store";
import {
  TranslateLiveClient,
  type SourceMode,
  type TranslateStatus,
  type TranslateEvent,
} from "@/services/translate_live";
import { getTTSSpeaker } from "@/services/tts_speaker";
import type { TranslateEventAudio } from "@/services/translate_live";

interface Langue {
  code: string;
  label: string;
  flag: string;
  stt: boolean;
  trad: boolean;
}

interface Ligne {
  utteranceId: string;
  source: string;
  translated: string;
  sourceLang: string;
  isFinal: boolean;
  ts: number;
  gender?: "male" | "female";
}

export const TranslateLivePage = () => {
  const token = useAuthStore((s) => s.token);

  const [langues, setLangues] = useState<Langue[]>([]);
  const [creditsPerMin, setCreditsPerMin] = useState<number>(120);
  const [costFcfaPerMin, setCostFcfaPerMin] = useState<number>(6);

  const [source, setSource] = useState<string>("auto");
  const [target, setTarget] = useState<string>("fr");
  const [sourceMode, setSourceMode] = useState<SourceMode>("microphone");
  const [consentOk, setConsentOk] = useState<boolean>(false);

  const [status, setStatus] = useState<TranslateStatus>("idle");
  const [statusMsg, setStatusMsg] = useState<string>("");
  const [lignes, setLignes] = useState<Ligne[]>([]);
  const [currentInterim, setCurrentInterim] = useState<string>("");
  const [minutesUsed, setMinutesUsed] = useState<number>(0);
  const [creditsUsed, setCreditsUsed] = useState<number>(0);
  const [ttsAvailable, setTtsAvailable] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [lastGender, setLastGender] = useState<"male"|"female"|null>(null);
  const [tipsOpen, setTipsOpen] = useState<boolean>(false);

  const clientRef = useRef<TranslateLiveClient | null>(null);
  const lignesRef = useRef<HTMLDivElement>(null);
  const ttsRef = useRef(getTTSSpeaker());  // fallback browser TTS si ElevenLabs absent

  // ── Chargement référentiel ───────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const [{ data: langs }, { data: st }] = await Promise.all([
          http.get("/translate/live/langues"),
          http.get("/translate/live/status"),
        ]);
        setLangues(langs.langues || []);
        setCreditsPerMin(st.price_per_minute_credits || 120);
        setCostFcfaPerMin(st.price_per_minute_fcfa || 6);
        setTtsAvailable(!!st.tts_available);
      } catch {
        // silencieux — backend vérifie la clé au démarrage de la session
      }
    })();
  }, []);

  // ── Autoscroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    lignesRef.current?.scrollTo({ top: lignesRef.current.scrollHeight, behavior: "smooth" });
  }, [lignes, currentInterim]);

  // ── Clean up au démontage ────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      clientRef.current?.stop();
    };
  }, []);

  const languesCible = useMemo(
    () => langues.filter((l) => l.code !== "auto" && l.trad),
    [langues],
  );
  const languesSource = langues;

  const handleStart = async () => {
    if (!token) {
      toast.error("Session expirée — reconnectez-vous.");
      return;
    }
    if (!consentOk) {
      toast.error("Veuillez confirmer le consentement des interlocuteurs.");
      return;
    }
    setLignes([]);
    setCurrentInterim("");
    setMinutesUsed(0);
    setCreditsUsed(0);

    const client = new TranslateLiveClient({
      token,
      source,
      target,
      sourceMode,
      onStatus: (s, details) => {
        setStatus(s);
        setStatusMsg(details || "");
        if (s === "error" && details) toast.error(details);
      },
      onEvent: (ev: TranslateEvent) => {
        if (ev.type === "transcript") {
          if (!ev.is_final) {
            setCurrentInterim(ev.text);
            return;
          }
          setCurrentInterim("");
          setLignes((prev) => [
            ...prev,
            {
              utteranceId: ev.utterance_id,
              source: ev.text,
              translated: "",
              sourceLang: ev.lang,
              isFinal: true,
              ts: Date.now(),
            },
          ]);
        } else if (ev.type === "translation") {
          const gender = (ev as any).gender as "male"|"female"|undefined;
          if (gender) setLastGender(gender);
          setLignes((prev) =>
            prev.map((l) =>
              l.utteranceId === ev.utterance_id
                ? { ...l, translated: ev.translated_text, sourceLang: ev.source_lang, gender: gender ?? l.gender }
                : l,
            ),
          );
          // Fallback navigateur TTS si ElevenLabs absent
          if (!ttsAvailable && ev.translated_text && ev.source_lang !== ev.target_lang) {
            ttsRef.current.speak(ev.translated_text, ev.target_lang);
          }
        } else if (ev.type === "audio") {
          // Lecture gérée par TranslateLiveClient.playMp3Bytes — juste mettre à jour l'UI
          setLastGender((ev as TranslateEventAudio).gender);
        } else if (ev.type === "usage") {
          setMinutesUsed(ev.minutes);
          setCreditsUsed(ev.credits_debited_total);
        } else if (ev.type === "error") {
          toast.error(ev.message || "Erreur serveur");
        }
      },
    });
    clientRef.current = client;

    try {
      await client.start();
    } catch (err: any) {
      toast.error(err?.message || "Impossible de démarrer la session");
    }
  };

  const handleStop = async () => {
    await clientRef.current?.stop();
    clientRef.current = null;
    ttsRef.current.cancel();
  };

  const handleSauvegarderMesDocuments = async () => {
    if (lignes.length === 0) {
      toast.error("Aucune transcription à sauvegarder");
      return;
    }
    setSaving(true);
    try {
      const dateStr = new Date().toLocaleString("fr-FR");
      const md = [
        `# Transcription YukpoTranslate Live`,
        ``,
        `- Date : ${dateStr}`,
        `- Source : ${sourceMode === "microphone" ? "Microphone" : "Onglet / Écran"}`,
        `- Langue cible : ${target}`,
        `- Durée : ${minutesUsed.toFixed(1)} min`,
        `- Crédits : ${Math.round(creditsUsed)}`,
        ``,
        `## Dialogue bilingue`,
        ``,
        ...lignes.map((l) => `**[${l.sourceLang}] ${l.source}**\n\n→ ${l.translated || "_(non traduit)_"}\n`),
      ].join("\n");
      await http.post("/documents/historique", {
        titre: `Traduction Live — ${dateStr}`,
        type_doc: "traduction",
        contenu_source: lignes.map((l) => `[${l.sourceLang}] ${l.source}`).join("\n"),
        contenu_genere: md,
        meta: {
          module: "translate_live",
          target_lang: target,
          minutes: minutesUsed,
          credits: Math.round(creditsUsed),
          nb_utterances: lignes.length,
          source_mode: sourceMode,
        },
      });
      toast.success("Transcription sauvegardée dans Mes Documents");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Sauvegarde impossible");
    } finally {
      setSaving(false);
    }
  };

  const handleCopierTranscription = () => {
    const texte = lignes
      .map((l) => `[${l.sourceLang}] ${l.source}\n→ ${l.translated || "…"}`)
      .join("\n\n");
    navigator.clipboard.writeText(texte);
    toast.success("Transcription copiée");
  };

  const handleTelechargerMd = () => {
    const md = [
      `# Transcription YukpoTranslate Live`,
      ``,
      `- Date : ${new Date().toLocaleString()}`,
      `- Langue cible : ${target}`,
      `- Durée : ${minutesUsed.toFixed(1)} min`,
      ``,
      `## Dialogue`,
      ``,
      ...lignes.map((l) => `**[${l.sourceLang}] ${l.source}**\n\n→ ${l.translated || "_(traduction manquante)_"}\n`),
    ].join("\n");
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `translate-live-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const isStreaming = status === "streaming" || status === "ready";
  const canStart = status === "idle" || status === "closed" || status === "error";

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <DemoBanner />
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100 flex items-center gap-2">
            <Radio className="w-7 h-7 text-yukpo-400" />
            Traduction Live
            <Badge variant="purple" size="sm">BETA</Badge>
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Sous-titres bilingues en temps réel — micro ou onglet Zoom/Meet/YouTube.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <div className="flex items-center gap-1 text-gray-300">
            <Clock className="w-4 h-4" />
            <span>{minutesUsed.toFixed(1)} min</span>
          </div>
          <div className="flex items-center gap-1 text-gold-400">
            <Coins className="w-4 h-4" />
            <span>{Math.round(creditsUsed)} crédits</span>
          </div>
        </div>
      </div>

      {/* Configuration */}
      <Card className="p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Source audio</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                disabled={isStreaming}
                onClick={() => setSourceMode("microphone")}
                className={`flex items-center justify-center gap-2 py-2.5 rounded-xl border text-sm font-medium transition
                  ${sourceMode === "microphone"
                    ? "border-yukpo-500/40 bg-yukpo-500/10 text-yukpo-200"
                    : "border-white/10 text-gray-400 hover:text-gray-200"}
                  disabled:opacity-50`}
              >
                <Mic className="w-4 h-4" /> Micro
              </button>
              <button
                disabled={isStreaming}
                onClick={() => setSourceMode("display")}
                className={`flex items-center justify-center gap-2 py-2.5 rounded-xl border text-sm font-medium transition
                  ${sourceMode === "display"
                    ? "border-yukpo-500/40 bg-yukpo-500/10 text-yukpo-200"
                    : "border-white/10 text-gray-400 hover:text-gray-200"}
                  disabled:opacity-50`}
              >
                <MonitorSpeaker className="w-4 h-4" /> Onglet / Écran
              </button>
            </div>
            {sourceMode === "display" && (
              <p className="text-[11px] text-gray-500 mt-1.5 flex items-start gap-1">
                <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                Cochez <em>« Partager l'audio »</em> dans la boîte de dialogue du navigateur.
              </p>
            )}
            {sourceMode === "microphone" && (
              <div className="mt-2 rounded-lg text-[11px] overflow-hidden"
                style={{ background: "rgba(0,84,166,0.08)", border: "1px solid rgba(0,176,240,0.15)" }}>
                <button
                  type="button"
                  onClick={() => setTipsOpen((o) => !o)}
                  className="w-full flex items-center justify-between px-2.5 py-2 text-bright-400 font-semibold hover:bg-white/[0.03] transition"
                >
                  <span className="flex items-center gap-1">
                    <Info className="w-3 h-3 flex-shrink-0" /> Conseil selon le contexte
                  </span>
                  <span className="text-gray-500 text-[10px]">{tipsOpen ? "▲" : "▼"}</span>
                </button>
                {tipsOpen && (
                  <div className="px-2.5 pb-2.5 text-slate-400 space-y-1.5 border-t border-white/[0.06]">
                    <p className="mt-1.5"><span className="text-slate-300 font-medium">Réunion en ligne (Zoom/Teams)</span> — utilise plutôt le mode <em>Onglet / Écran</em> pour capter l'audio directement depuis l'application, sans dépendre du micro.</p>
                    <p><span className="text-slate-300 font-medium">Réunion physique (petite salle, 1–4 personnes)</span> — le micro intégré de l'ordinateur suffit si tu es proche des interlocuteurs.</p>
                    <p><span className="text-slate-300 font-medium">Grande salle / table de conférence</span> — connecte un micro USB omnidirectionnel au centre de la table (ex. Jabra Speak 510, Anker PowerConf S3 — câble USB, plug-and-play). Il capte 360° jusqu'à 3–4 m sans driver. Version sans fil : Jabra Speak 710 (Bluetooth).</p>
                    <p><span className="text-slate-300 font-medium">Plusieurs utilisateurs YukpoPro dans la même salle</span> — un seul micro au centre suffit pour tout le monde. Chaque participant lit les sous-titres sur son propre écran. Si tu actives la voix 🔊, utilise <strong>obligatoirement des écouteurs</strong> — sinon la voix TTS sort dans la salle et crée une boucle audio.</p>
                    <p className="text-amber-400/80">⚡ <strong>Voix 🔊 activée = écouteurs obligatoires.</strong></p>
                  </div>
                )}
              </div>
            )}
          </div>

          <div>
            <label className="text-xs text-gray-400 mb-1 block">Langue parlée (source)</label>
            <Select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              disabled={isStreaming}
              options={languesSource.map((l) => ({
                value: l.code,
                label: `${l.flag} ${l.label}${l.stt ? "" : " (STT limité)"}`,
              }))}
            />
          </div>

          <div>
            <label className="text-xs text-gray-400 mb-1 block">Langue cible (traduction)</label>
            <Select
              value={target}
              onChange={(e) => {
                setTarget(e.target.value);
                clientRef.current?.setTargetLanguage(e.target.value);
              }}
              options={languesCible.map((l) => ({
                value: l.code,
                label: `${l.flag} ${l.label}`,
              }))}
            />
          </div>
        </div>

        {/* Consentement */}
        <div className="flex items-start gap-2 p-3 rounded-lg border border-white/10 bg-black/20">
          <input
            id="consent"
            type="checkbox"
            className="mt-1"
            checked={consentOk}
            onChange={(e) => setConsentOk(e.target.checked)}
            disabled={isStreaming}
          />
          <label htmlFor="consent" className="text-xs text-gray-300 cursor-pointer">
            Je confirme que les interlocuteurs sont informés que la conversation est
            transcrite à des fins de traduction. Aucun audio n'est conservé côté serveur.
          </label>
        </div>

        {/* Tarif */}
        <div className="flex items-center justify-between text-xs text-gray-400 border-t border-white/5 pt-3">
          <div>
            Tarif : <span className="text-yukpo-300 font-semibold">{creditsPerMin} crédits / min</span>
            {" "}≈ {costFcfaPerMin} FCFA / min coût réel
          </div>
          <div className="text-gray-500">
            Limite : 2 sessions simultanées / utilisateur
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {canStart ? (
            <Button
              variant="primary"
              size="lg"
              icon={<Play className="w-5 h-5" />}
              onClick={handleStart}
              disabled={!consentOk || !token}
            >
              Démarrer la traduction
            </Button>
          ) : (
            <Button
              variant="danger"
              size="lg"
              icon={<Square className="w-5 h-5" />}
              onClick={handleStop}
            >
              Arrêter
            </Button>
          )}

          {status === "connecting" && (
            <div className="flex items-center gap-2 text-sm text-yukpo-300">
              <Loader2 className="w-4 h-4 animate-spin" /> Connexion…
            </div>
          )}
          {status === "ready" && (
            <div className="flex items-center gap-2 text-sm text-green-400">
              <CheckCircle2 className="w-4 h-4" /> Prêt — parlez pour commencer
            </div>
          )}
          {status === "streaming" && (
            <div className="flex items-center gap-2 text-sm text-yukpo-300">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
              </span>
              Traduction en cours
            </div>
          )}
          {status === "error" && statusMsg && (
            <div className="text-sm text-red-400 flex items-center gap-2">
              <AlertCircle className="w-4 h-4" /> {statusMsg}
            </div>
          )}
        </div>
      </Card>

      {/* Transcription live */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <div className="flex items-center gap-2 text-sm text-gray-300">
            <Languages className="w-4 h-4 text-yukpo-400" />
            Transcription live — original (gauche) / traduit (droite)
          </div>
          <div className="flex items-center gap-2">
            {/* Indicateur TTS ElevenLabs / genre détecté */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium"
              style={ttsAvailable
                ? { background: "rgba(0,176,240,0.08)", border: "1px solid rgba(0,176,240,0.25)", color: "#7dd3fc" }
                : { background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.10)", color: "#6b7280" }}>
              {ttsAvailable
                ? <Volume2 className="w-3.5 h-3.5" />
                : <VolumeX className="w-3.5 h-3.5" />}
              {ttsAvailable
                ? (lastGender ? (lastGender === "male" ? "♂ Voix homme" : "♀ Voix femme") : "Voix TTS")
                : "Voix TTS —"}
            </div>
            <Button variant="ghost" size="sm" icon={<Copy className="w-4 h-4" />} onClick={handleCopierTranscription}
              disabled={lignes.length === 0}>Copier</Button>
            <Button variant="ghost" size="sm" icon={<Download className="w-4 h-4" />} onClick={handleTelechargerMd}
              disabled={lignes.length === 0}>Exporter .md</Button>
            <Button variant="ghost" size="sm" icon={<Save className="w-4 h-4" />} onClick={handleSauvegarderMesDocuments}
              disabled={lignes.length === 0 || saving}>
              {saving ? "Enregistrement…" : "Mes Documents"}
            </Button>
          </div>
        </div>

        <div ref={lignesRef} className="max-h-[55vh] overflow-y-auto p-4 space-y-3">
          {lignes.length === 0 && !currentInterim && (
            <div className="text-sm text-gray-500 text-center py-10">
              {isStreaming
                ? "En attente de parole…"
                : "Aucune transcription. Démarrez une session pour commencer."}
            </div>
          )}
          {lignes.map((l) => (
            <div
              key={l.utteranceId}
              className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 rounded-lg bg-white/[0.03] border border-white/[0.05]"
            >
              <div>
                <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1 flex items-center gap-1.5">
                  {l.sourceLang}
                  {l.gender && (
                    <span className="text-[10px] px-1 rounded"
                      style={{ background: "rgba(255,255,255,0.06)", color: l.gender === "male" ? "#7dd3fc" : "#f9a8d4" }}>
                      {l.gender === "male" ? "♂" : "♀"}
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-200">{l.source}</div>
              </div>
              <div className="border-l-0 md:border-l border-white/10 md:pl-3">
                <div className="text-[10px] uppercase tracking-wide text-yukpo-400 mb-1">
                  {target}
                </div>
                <div className="text-sm text-yukpo-100">
                  {l.translated || <span className="text-gray-500 italic">traduction…</span>}
                </div>
              </div>
            </div>
          ))}
          {currentInterim && (
            <div className="p-3 rounded-lg bg-yukpo-500/5 border border-yukpo-500/20">
              <div className="text-[10px] uppercase tracking-wide text-yukpo-400 mb-1">en cours</div>
              <div className="text-sm text-gray-300 italic">{currentInterim}</div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};
