/**
 * YukpoPro — Interface de chat unifiée
 * Remplace CopilotePage, AgentsPage, GenerateursPage, AnalysePage, TraductionPage
 * Un seul chat intelligent qui orchestre tous les agents et outils.
 */
import React, { useState, useRef, useEffect, useCallback, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import {
  Send, Plus, Trash2, MessageSquare, Paperclip, X,
  ChevronLeft, ChevronRight, Bot, Sparkles, Download,
  FileText, Image, Table, Globe, BarChart2,
  Pencil, Save, User as UserIcon, Mic, MicOff,
  Copy, Check, Camera,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuthStore, useProfilStore, useCopiloteStore, useDocsStore } from "@/store";
import { chatApi, profilApi, copiloteApi, reunionsApi, generateurApi, infographieProApi, bureauSessionApi, http, type UploadedFile } from "@/api/client";
import { acquireWakeLock, releaseWakeLock } from "@/utils/wakeLock";
import { cn } from "@/components/ui";
import type { CopiloteMessage, NavigationSuggestion, SuggestionSuite } from "@/types";
import { METIERS, PAYS_AFRIQUE } from "@/types";
import { METIERS_CONFIG } from "@/data/metiers-config";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AttachedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  content?: string; // base64 ou texte extrait
}

// ── Composant principal ───────────────────────────────────────────────────────

export const ChatPage = () => {
  const { t } = useTranslation();
  const { user } = useAuthStore();
  const { profil } = useProfilStore();
  const {
    sessions, activeSessionId, isLoading,
    newSession, selectSession, deleteSession,
    addMessage, updateLastAssistantMessage, setLoading, clearSession,
    activeMessages, activeSession, activeDocument, setActiveDocument,
  } = useCopiloteStore();
  const { addDocument } = useDocsStore();

  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  // BATCH-4 — queue multi-input pendant génération (push pendant isLoading,
  // flush automatique dès que la réponse en cours termine).
  type PendingItem = { content: string; files: AttachedFile[] };
  const [pendingQueue, setPendingQueue] = useState<PendingItem[]>([]);
  const [historySidebarOpen, setHistorySidebarOpen] = useState(() => window.innerWidth >= 768);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  const [uploadingFile, setUploadingFile] = useState(false);
  const [profilModalOpen, setProfilModalOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [audioModalOpen, setAudioModalOpen] = useState(false);
  const [audioSeconds, setAudioSeconds] = useState(0);
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Détecter mobile/desktop
  useEffect(() => {
    const check = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setHistorySidebarOpen(false);
    };
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Camera scan (document/reçu/carte) — getUserMedia + capture canvas → File
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [cameraModalOpen, setCameraModalOpen] = useState(false);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);

  const messages = activeMessages();
  const metierCtx = METIERS_CONFIG[profil?.metier ?? "default"] ?? METIERS_CONFIG.default;
  const suggestions = metierCtx.suggestions;

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeSessionId]);

  // Helper transversal : réécrit les URLs auth-protégées Yukpo dans un
  // texte markdown (réponse chat) pour suffixer ?token=JWT. Sans ça, les
  // liens [Télécharger](https://yukpopro-backend.fly.dev/api/v1/pro/
  // generateurs/fichier/xxx.docx) sont GET par le browser SANS header
  // Authorization → 401. Le backend get_current_user accepte ?token= en
  // query (priorité 3 SSE-compat).
  const _rewriteDocumentLinks = useCallback((text: string): string => {
    if (!text) return text;
    const tok = localStorage.getItem("yukpopro_token") || "";
    if (!tok) return text;
    // Match URLs auth-protégées dans le markdown : couvre relatives ET absolues
    return text.replace(
      /(https?:\/\/[^\s)]+)?(\/api\/v1\/(?:bureau\/documents|pro\/generateurs\/fichier|bureau\/video\/fichier)\/[^\s)]+)/g,
      (full) => {
        if (full.includes("token=")) return full;
        return full + (full.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(tok);
      },
    );
  }, []);

  // Pre-warm backend Fly (scale-to-zero) — un GET /health/live silencieux au
  // mount + à chaque retour de focus onglet réveille la machine en parallèle
  // de la composition utilisateur, évitant un 504 sur la 1ʳᵉ requête lourde
  // (sites/generer, freeform, vidéo) après une pause >5min.
  // /health/live est root-level (pas sous /api/v1) et touche aucun store →
  // réveille la machine en ~5-10s sans charger DB/Redis.
  useEffect(() => {
    const base = (http as any).defaults?.baseURL || "";
    const wakeUrl = base.replace(/\/api\/v\d+\/?$/, "") + "/health/live";
    const wake = () => {
      try { fetch(wakeUrl, { method: "GET", mode: "cors" }).catch(() => {}); }
      catch { /* noop */ }
    };
    wake();
    const onFocus = () => wake();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  // BATCH-4 — Flush queue dès que isLoading repasse à false et qu'il y a
  // des items en attente. Déclenche sendMessage avec le 1er item de la file.
  useEffect(() => {
    if (!isLoading && pendingQueue.length > 0) {
      const next = pendingQueue[0];
      setPendingQueue(prev => prev.slice(1));
      // Petit delay pour laisser le DOM/store se stabiliser
      setTimeout(() => sendMessage(next.content, next.files), 80);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, pendingQueue.length]);

  const retirerDeLaQueue = (idx: number) =>
    setPendingQueue(prev => prev.filter((_, i) => i !== idx));

  // ── Envoi de message ───────────────────────────────────────────────────────

  const sendMessage = useCallback(async (content: string, files: AttachedFile[] = []) => {
    if (!content.trim() && files.length === 0) return;
    // BATCH-4 : pendant génération en cours → mise en file d'attente au lieu
    // de bloquer. L'envoi réel sera déclenché par le useEffect de flush dès
    // que isLoading repasse à false.
    if (isLoading) {
      setPendingQueue(prev => [...prev, { content, files }]);
      toast(t("chat.queued", "Mis en file d'attente — sera envoyé après la réponse en cours"),
            { icon: "📥", duration: 3000 });
      return;
    }

    const userMsg: CopiloteMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: content.trim(),
      timestamp: new Date().toISOString(),
      fichiers: files.map(f => f.name),
    };

    addMessage(userMsg);
    setInput("");
    setAttachedFiles([]);
    setLoading(true);

    // Message assistant "en cours..."
    const assistantMsg: CopiloteMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      loading: true,
    };
    addMessage(assistantMsg);

    try {
      const activeDoc = activeDocument();

      // Audio attachés → transcription Whisper auto AVANT orchestrer/copilote.
      // Sans ça, _extraire_texte_fichiers backend skip les .mp3/.wav/.webm
      // (silently ignorés). On transcrit en texte qu'on injecte dans le brief
      // pour que la suite du flow (rapport Word, traduction, analyse) marche.
      const isAudio = (f: AttachedFile) =>
        f.type.startsWith("audio/") || /\.(mp3|wav|m4a|webm|ogg)$/i.test(f.name);
      const audioFiles = files.filter(isAudio);
      const otherFiles = files.filter(f => !isAudio(f));
      if (audioFiles.length > 0) {
        for (const af of audioFiles) {
          if (!af.content) continue;
          try {
            const bytes = atob(af.content);
            const arr = new Uint8Array(bytes.length);
            for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
            const blob = new Blob([arr], { type: af.type || "audio/webm" });
            const fd = new FormData();
            fd.append("audio", blob, af.name);
            fd.append("langue", "auto");
            const res = await reunionsApi.transcrireDirect(fd);
            const txt = (res.transcription || "").trim();
            if (txt) {
              content = content.trim()
                ? `${content.trim()}\n\n[Transcription "${af.name}"]\n${txt}`
                : `[Transcription "${af.name}"]\n${txt}`;
            }
          } catch (e: any) {
            // eslint-disable-next-line no-console
            console.warn(`[ChatPage] Transcription "${af.name}" échouée:`, e);
            toast.error(`Transcription "${af.name}" échouée`);
          }
        }
        files = otherFiles;
      }

      // ─── Nouveaux pipelines : slides web + landing page (intent client-side) ─
      // Détection keyword AVANT orchestrer LLM pour gain de latence + clarté.
      // Patterns reconnus (FR + EN) :
      //   • "slides web", "présentation web", "présentation interactive",
      //     "reveal.js", "présentation partage url" → /slides-web/generer
      //   • "landing page", "page d'accueil web", "site web une page",
      //     "page web produit", "landing", "one-pager" → /landing-page/generer
      // Si match, on appelle directement l'endpoint (ignore orchestrer).
      if (files.length === 0 && content.trim()) {
        const txt = content.toLowerCase();

        // ─── Classifier LLM sémantique (priorité sur regex) ──────────────
        // Cf. memory feedback-llm-first-routing : la sémantique prime sur
        // les mots-clés. Appel Haiku rapide ~1-2s qui classifie le brief
        // en un intent fermé (site_multipage / landing / boutique / visuel
        // /…). On l'utilise pour TRANCHER les cas ambigus que les regex
        // peuvent rater.
        //
        // Best-effort : si l'appel échoue ou est lent (>4s), on fallback
        // directement sur les regex (latence prime). Pas de blocage.
        let llmIntent: { intent: string; confidence: number } | null = null;
        try {
          // On passe le contexte session (dernier livrable généré) pour que
          // le LLM puisse arbitrer correctement qa_simple vs modification :
          // une même question peut être pure curiosité OU vouloir enrichir
          // le doc existant — seul le LLM peut trancher sémantiquement.
          const _docsList = useDocsStore.getState().documents;
          const _dernierDoc = _docsList && _docsList.length > 0
            ? _docsList[0] : null;
          const llmCall = http.post("/chat/classify-intent",
            {
              brief: content,
              has_files: files.length > 0,
              dernier_doc_titre: _dernierDoc?.titre || null,
              dernier_doc_type:  _dernierDoc?.type  || null,
            },
            { timeout: 5_000 },
          );
          // race avec timeout 4s — on ne laisse pas le classifier ralentir
          const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error("classify-timeout")), 4_000));
          const res: any = await Promise.race([llmCall, timeout]).catch(() => null);
          if (res?.data?.intent && res.data.confidence >= 0.55) {
            llmIntent = { intent: res.data.intent, confidence: res.data.confidence };
          }
        } catch { /* fallback silencieux sur regex */ }

        // 🔴 SHORT-CIRCUIT qa_simple — décision 100% sémantique côté LLM :
        // si le classifier a tranché qa_simple, on bascule direct sur
        // chatApi.send sans passer par les détecteurs de modification/
        // site/visuel/etc. Le LLM (cf. /chat/classify-intent) a accès au
        // contexte session ET sait distinguer une vraie question
        // ("pourquoi Taiwan est important ?") d'une modif formulée en
        // question ("tu peux ajouter une section sur Taiwan ?"). On lui
        // fait confiance — pas de regex sur la forme interrogative.
        if (llmIntent?.intent === "qa_simple") {
          try {
            updateLastAssistantMessage("💬 …", null);
            const res = await chatApi.send({
              message: content.trim(),
              pays: profil?.pays,
              fichiers: files.map(f => ({ nom: f.name, contenu: f.content || "", type: f.type })),
              skip_orchestration: true,
            });
            updateLastAssistantMessage(
              _rewriteDocumentLinks(res.reponse), res.agent_utilise ?? null,
              res.fichiers_generes ?? undefined,
              res.cout_llm ?? null,
              res.navigation_suggestions ?? [],
            );
          } catch (err: any) {
            const msg = err?.response?.data?.detail || t("chat.connectionError");
            updateLastAssistantMessage(`⚠️ ${typeof msg === "string" ? msg : "Erreur"}`, null);
          }
          return;
        }

        // ─── Détection PRIORITAIRE site web multi-pages ──────────────────
        // Placée TOUT EN HAUT pour éviter que "génère un visuel pour mon
        // cabinet" (visuelMarketingMatch) ou "génère une landing" capturent
        // un brief qui demande clairement un site web professionnel.
        //
        // Regex élargie : capte mon/le/un/notre site, site web/internet/
        // professionnel/vitrine/business/pro, pour mon cabinet/entreprise/
        // agence/boutique/société, multi-pages, mini-site, etc.
        const siteWebMatchPrioritaire =
          // Verbe action + "site"
          /\b(g[ée]n[èe]re|cr[ée]e|fais|monte|construis|d[ée]veloppe|veux|conçois|produis)\b[^.]{0,80}\b(?:mon|le|un|notre|nouveau)?\s*(?:nouveau|petit)?\s*(?:mini[-\s]?)?site\b/i.test(txt)
          // "site (web|internet|professionnel|pro|vitrine|complet)"
          || /\bsite\s+(?:web|internet|professionnel|pro|vitrine|complet|business|d['']entreprise|de\s*(?:mon|notre|ma|son))/i.test(txt)
          // "site pour mon/notre cabinet/entreprise/agence/boutique"
          || /\bsite\s+(?:pour|de|du|pour\s+(?:mon|notre|ma|la|le))\s+\S+/i.test(txt)
          // Mini-site, multi-pages explicite, X pages
          || /\b(mini[-\s]?site|multi[-\s]?pages?|\d+\s*pages?|site\s+\d+\s+pages?)\b/i.test(txt);
        // Exclusions : ne PAS catcher si clair single-page/landing
        const exclureSite =
          /\b(une\s*seule\s*page|une\s*page|one[-\s]?pager|landing\s*page)\b/i.test(txt)
          && !/\bmulti[-\s]?pages?|\d+\s*pages?\b/i.test(txt);

        // LLM Sonnet décide en PRIMAIRE (sémantique forte), regex en fallback
        // uniquement si LLM indispo/timeout (>4s). Garde-fou exclureSite
        // s'applique aux 2 (évite "une seule page / one-pager / landing").
        const wantsSite = !exclureSite && (
          llmIntent
            ? llmIntent.intent === "site_multipage"
            : siteWebMatchPrioritaire
        );
        if (wantsSite) {
          try {
            updateLastAssistantMessage(
              "🌐 Génération du mini-site multi-pages en cours… (~30-90s)\n_Yukpo compose 7-9 sections par page + paragraphes narratifs denses + images IA hero._",
              null,
            );
            const result = await generateurApi.genererSite({
              brief: content, langue: "fr", generer_images: true,
            });
            updateLastAssistantMessage(
              `✓ Site **${result.nom}** généré (${result.nb_pages} pages : ${result.types_pages.join(", ")}).\n\n🌍 Publication Netlify en cours…`,
              null,
            );
            // Auto-publication — l'utilisateur a demandé "génère un site web",
            // pas "génère un brouillon". On enchaîne le deploy Netlify pour
            // qu'il obtienne une URL live immédiatement.
            try {
              const pub = await generateurApi.publierSite(result.slug, "free", true);
              const customUrl = (pub.url_public || `https://${result.slug}.yukpomnang.com`).replace(/^http:/, "https:");
              const fallbackUrl = pub.fallback_netlify_url || null;
              let msg = `✓ Site **${result.nom}** publié (${result.nb_pages} pages).\n\n`;
              // URL .netlify.app fonctionne immédiatement (SSL Netlify natif).
              // Custom domain *.yukpomnang.com a un délai de 5-15 min pour
              // provisionner son cert Let's Encrypt → afficher les deux.
              if (fallbackUrl && pub.is_new_netlify_site) {
                msg += `🌐 **URL accessible maintenant** : [${fallbackUrl}](${fallbackUrl})\n\n`;
                msg += `🔗 **URL personnalisée** (active dans ~5-15 min, le temps du certificat SSL) : ${customUrl}`;
              } else {
                msg += `🌐 [Ouvrir le site](${customUrl})`;
              }
              updateLastAssistantMessage(msg, null);
              toast.success("Site publié !");
            } catch (pubErr: any) {
              const d = pubErr?.response?.data?.detail || pubErr?.message || "inconnue";
              updateLastAssistantMessage(
                `✓ Site **${result.nom}** généré (${result.nb_pages} pages).\n\n` +
                `⚠ Publication automatique échouée : ${String(d).slice(0, 200)}\n\n` +
                `[🚀 Publier manuellement](/mes-sites)`,
                null,
              );
            }
            return;
          } catch (e: any) {
            const detail = e?.response?.data?.detail || e?.message || "inconnue";
            updateLastAssistantMessage(`❌ Erreur génération site : ${String(detail).slice(0, 200)}`, null);
            return;
          }
        }

        // ─── Pipeline GEOMETRIC PLACEMENT (visuel marketing single-page) ─
        // LLM Vision + math précise + anti-collision + audit retry.
        // Détection AVANT freeform/orchestrateur pour les briefs marketing
        // qui demandent un single-page premium. Pour multi-page (livret,
        // brochure, faire-part) → laisse passer à l'orchestrateur freeform.
        //
        // Patterns qui matchent (single-page marketing) :
        //   • "génère/crée/fais un visuel marketing/promo/pub"
        //   • "affiche/poster/flyer/bannière/banner"
        //   • "promotion/concours/tirage/tombola/giveaway/cashback"
        //   • "publicité/campagne/teaser/launch"
        // Patterns qui NE matchent PAS (multi-page → freeform) :
        //   • "faire-part" (livret cérémonie)
        //   • "livret/brochure/catalogue/programme"
        //   • "20 cartes / 100 cartes" (impression bulk)
        //   • "rapport/cv" (document texte)
        const visuelMarketingMatch =
          /(g[ée]n[èe]re|cr[ée]e|fais|produis|conçois)[^.]*\b(visuel|affiche|poster|flyer|banni[èe]re|banner)\b/i.test(txt)
          || /\b(visuel|affiche|poster|flyer)\s+(marketing|promo|pub|publicit[ée]|annonce|teaser|campagne)\b/i.test(txt)
          || /(promotion|concours|tombola|tirage|giveaway|cashback|loterie)\b/i.test(txt);
        const exclureMultiPage =
          /\bfaire[- ]?part\b|\blivret\b|\bbrochure\b|\bcatalogue\b|\bprogramme\b/i.test(txt)
          || /\b\d{1,3}\s*(cartes?\s+(de\s+)?visite|cartes?\b)/i.test(txt)
          || /\brapport\b|\bcv\b|\bm[ée]mo\b/i.test(txt)
          // Garde-fou : si le brief mentionne "site web/internet/pro" ou
          // une page de site (services/équipe/contact), ce n'est PAS un
          // visuel A4 single-page mais un site multi-pages déjà capté
          // plus haut. Permet d'éviter le mauvais routage observé.
          || /\bsite\s+(web|internet|professionnel|pro|vitrine|complet|business)\b/i.test(txt)
          || /\b(mini[-\s]?site|multi[-\s]?pages?|site\s+\d+\s+pages?)\b/i.test(txt)
          || /\bpage\s+(services?|équipe|equipe|contact|tarifs?|blog|à\s*propos|mentions)\b/i.test(txt);
        if (visuelMarketingMatch && !exclureMultiPage) {
          try {
            updateLastAssistantMessage(
              "🎨 Génération du visuel marketing via **placement géométrique** "
              + "(LLM Vision + math précise + audit qualité auto)…\n"
              + "_Latence estimée : 2-4 min._",
              null,
            );
            // Détection aspect ratio/format depuis le brief
            // (reel/story = portrait 9:16, banner = landscape, défaut A4)
            const isReel = /reel|story|tiktok|vertical|portrait\s*9\s*:\s*16/i.test(txt);
            const isBanner = /banni[èe]re|banner|leaderboard|skyscraper|landscape/i.test(txt);
            const isSquare = /carr[ée]|square|insta\s*post|1\s*:\s*1/i.test(txt);
            let page_w_mm = 210, page_h_mm = 297; // A4 portrait défaut
            if (isReel) { page_w_mm = 108; page_h_mm = 192; }       // 9:16
            else if (isBanner) { page_w_mm = 297; page_h_mm = 105; } // 2.83:1
            else if (isSquare) { page_w_mm = 200; page_h_mm = 200; } // 1:1

            const result = await generateurApi.geometricPlacement({
              brief: content,
              page_w_mm, page_h_mm,
              bleed_mm: 3,
              modele: "opus",  // Opus pour creative writing pro marketing
              dpi: 300,
              revision_visuelle: true,   // audit Vision + retry auto
              max_iterations_revision: 2,
              score_seuil_ok: 7.5,
              export_pdf: true,           // PDF/X-1a print-ready inclus
              export_svg: false,
            });
            const fid = (result as any).png_id;
            const tok = localStorage.getItem("yukpopro_token") || "";
            const baseUrl = `/api/v1/bureau/documents/${fid}`;
            const url = baseUrl + "?token=" + encodeURIComponent(tok);
            const pdfUrl = (result as any).pdf_id
              ? `/api/v1/bureau/documents/${(result as any).pdf_id}?token=${encodeURIComponent(tok)}`
              : null;
            const revisions = ((result as any).revisions_journal || []) as any[];
            const finalScore = revisions.length > 0
              ? (revisions[revisions.length - 1]?.audit?.score_qualite_sur_10 ?? "?")
              : "?";
            updateLastAssistantMessage(
              `✓ Visuel marketing généré via placement géométrique\n`
              + `**${result.nb_items}** éléments composés · score qualité : **${finalScore}/10** · ${revisions.length} itération${revisions.length > 1 ? "s" : ""} d'amélioration\n\n`
              + `[🖼 Voir le PNG](${url})`
              + (pdfUrl ? `   ·   [📄 PDF print-ready](${pdfUrl})` : ""),
              null,
              fid ? [fid] : undefined,
            );
            if (fid) {
              addDocument({
                titre: content.slice(0, 80),
                type: "visuel",
                fichier: fid,
                contexteConversation: content,
              });
              toast.success("Visuel marketing prêt");
            }
            return;
          } catch (e: any) {
            // Fallback vers orchestrateur si geometric échoue
            console.warn("[ChatPage] geometric-placement fallback :", e?.message);
            // Continue le flow normal (orchestrateur → freeform)
          }
        }

        // ─── Pipeline vidéo IA (text-to-video Kling/LTX) ──────────────
        // Détection AVANT slides-web/landing : sinon "vidéo de présentation"
        // pourrait router vers présentation. Parsing intelligent du prompt :
        //   • durée : "10s/dix secondes" → 10s, sinon 5s défaut
        //   • aspect : "reel/story/tiktok/9:16/vertical" → 9:16,
        //              "insta feed/carré/1:1" → 1:1, "4:3" → 4:3, sinon 16:9
        //   • mode : "ultra/cinéma/broadcast/sora/haute qualité" → ultra,
        //            "rapide/eco/pas cher/ltx" → standard, sinon premium
        // ── Modification vidéo précédente — passe AVANT generation vidéo ──
        // Si la session contient un dernier doc vidéo et que l'user demande
        // une modif (audio, segment, trim, regen), on route vers
        // /bureau/video/modifier (in_place=true → écrase l'original, pas
        // de brouillons multiples dans /mes-documents).
        const _docsList2 = useDocsStore.getState().documents;
        const _dernierVideo = (_docsList2 || []).find(d =>
          (d.type === "video" || d.type === "visuel")
          && /\.(mp4|webm|mov)$/i.test(d.fichier || "")
        );
        // LLM Sonnet décide en PRIMAIRE — il sait que "refais la vidéo"
        // = modification. Regex utilisée UNIQUEMENT si LLM indispo/timeout.
        // Le filtre objet (/vid[ée]o|son|audio|voix/) garde la discrimination
        // entre modification vidéo vs modification site/visuel.
        const veutModifVideo = !!_dernierVideo && (
          llmIntent
            ? (llmIntent.intent === "modification" && /vid[ée]o|son|audio|voix/i.test(txt))
            : (/\b(refais|refait|change|remplace|modifie|coupe|trim|raccourci|enl[èe]ve|supprime|ajoute|met)\b[^.]*\b(la\s*)?(vid[ée]o|audio|son|voix(?:[- ]?off)?|narration|extrait|segment|portion|partie|d[ée]but|fin)\b/i.test(txt)
               || /\b(voix\s*(?:plus|homme|femme|grave|aigu[eë]|f[ée]minine|masculine)|narrateur|narratrice)\b/i.test(txt))
        );
        if (veutModifVideo && _dernierVideo) {
          try {
            // Analyse rapide du brief pour décider de l'action (LLM-first
            // possible mais ici signal sémantique fort → décision claire).
            const wantsAudioOnly = /\b(voix|audio|son|narration|narrateur|narratrice|voix[- ]?off)\b/i.test(txt)
                                && !/\b(vid[ée]o|image|s[ée]quence)\b/i.test(txt);
            const wantsVideoOnly = /\b(refais\s*la\s*vid[ée]o|regen[ée]re\s*la\s*vid[ée]o|change\s*la\s*vid[ée]o|nouvelle\s*vid[ée]o|autre\s*angle)\b/i.test(txt)
                                && !/\b(audio|son|voix)\b/i.test(txt);
            const wantsTrim = /\b(coupe|trim|raccourci|garde\s*seulement|les\s*\d+\s*premi[èe]res?)\b/i.test(txt);
            const wantsEffaceAudio = /\b(enl[èe]ve|supprime|retire|coupe)\s*(le\s*)?(son|audio|voix)\b|\bsans\s*(son|audio|voix)\b|\bmuet\b/i.test(txt);

            let actionVideo: "replacer_audio" | "regenerer_video" | "regenerer_avec_audio" | "trim" | "effacer_audio";
            if (wantsEffaceAudio) actionVideo = "effacer_audio";
            else if (wantsTrim) actionVideo = "trim";
            else if (wantsVideoOnly) actionVideo = "regenerer_video";
            else if (wantsAudioOnly) actionVideo = "replacer_audio";
            else actionVideo = "regenerer_avec_audio";

            const voixMod: "male" | "female" | undefined =
              /\bvoix\s*(?:d['e]?)?\s*homme|man['s']*\s*voice|male\s*voice|narrateur\s*homme|voix\s*masculine/i.test(txt) ? "male"
              : /\bvoix\s*(?:d['e]?\s*)?femme|woman['s']*\s*voice|female\s*voice|narratrice|voix\s*f[ée]minine/i.test(txt) ? "female"
              : undefined;

            // Extraction intervalle "de Xs à Ys" / "entre X et Y"
            let tDeb: number | undefined, tFin: number | undefined;
            const mInt = txt.match(/\b(?:de|entre|à\s*partir\s*de)\s*(\d+)\s*(?:s|sec(?:ondes?)?)?\s*(?:à|jusqu['e]?\s*à|et)\s*(\d+)\s*s?/i);
            if (mInt) {
              tDeb = parseFloat(mInt[1]); tFin = parseFloat(mInt[2]);
            } else {
              const mGarde = txt.match(/\b(?:garde|coupe\s*à|trim\s*à)\s*(\d+)\s*s/i);
              if (mGarde) { tDeb = 0; tFin = parseFloat(mGarde[1]); }
            }

            updateLastAssistantMessage(
              `🎬 Modification vidéo en cours (${actionVideo}${voixMod ? ", voix " + voixMod : ""}` +
              (tDeb !== undefined && tFin !== undefined ? `, [${tDeb}s→${tFin}s]` : "") +
              `)…\n_La même vidéo sera mise à jour (pas de nouveau brouillon)._`,
              null,
            );

            const tok = localStorage.getItem("yukpopro_token") || "";
            const { data: modifResult } = await http.post(
              "/bureau/video/modifier",
              {
                fichier_id: _dernierVideo.fichier,
                action: actionVideo,
                prompt: content,
                voix: voixMod,
                t_debut: tDeb,
                t_fin: tFin,
                in_place: true,
              },
              { timeout: 600_000 },
            );
            const fidMod = modifResult.fichier_id;
            const baseUrl = modifResult.url_telechargement;
            // ?v=ts pour bust le cache navigateur (même fichier_id mais nouveau contenu)
            const cacheBust = `&v=${Date.now()}`;
            const urlMod = baseUrl + (baseUrl.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(tok) + cacheBust;
            updateLastAssistantMessage(
              `✓ Vidéo mise à jour (${actionVideo}${modifResult.audio_meta?.voix ? `, voix ${modifResult.audio_meta.voix}` : ""}, ${modifResult.size_kb} KB) — ${_dernierVideo.fichier}\n` +
              `[▶ Lire / Télécharger MP4](${urlMod})`,
              null,
              fidMod ? [fidMod] : undefined,
            );
            // Met à jour le doc existant côté store (pas de nouveau brouillon)
            try {
              const { useDocsStore: _useDocs } = await import("@/store");
              const _d = _useDocs.getState().documents.find(x => x.fichier === _dernierVideo.fichier);
              if (_d) {
                _useDocs.getState().updateDocument(_d.id, {
                  titre: (_dernierVideo.titre || "Vidéo") + " (modifiée)",
                });
              }
            } catch { /* non bloquant */ }
            toast.success("Vidéo modifiée");
            return;
          } catch (eMod: any) {
            const det = eMod?.response?.data?.detail || eMod?.message || "inconnue";
            updateLastAssistantMessage(`❌ Modification vidéo échouée : ${String(det).slice(0, 200)}`, null);
            return;
          }
        }

        const videoMatch = /(g[ée]n[èe]re|cr[ée]e|fais|produis|veux)[^.]*\bvid[ée]o\b|\bvid[ée]o\s+(promo|tv|pub|reels?|teaser)|\bteaser\b|\breel\b|short\s*video|clip\s*vid[ée]o|spot\s*(pub|tv|publicitaire)|motion\s*ad/i.test(txt);
        if (videoMatch) {
          try {
            // Durée 5-60s : extraction depuis le prompt.
            //   • "Ns / N sec / N secondes" → N (clamped 5-60)
            //   • "1 min / 1 minute / 60 secondes / une minute" → 60
            //   • "30 secondes / trente secondes" → 30
            //   • défaut 5s
            let duree_s = 5;
            const mMin = txt.match(/\b(1|une?)\s*(min(?:ute)?s?)\b/);
            if (mMin) {
              duree_s = 60;
            } else {
              const mSec = txt.match(/\b(\d{1,2})\s*s(?:ec(?:ondes?)?)?\b/);
              if (mSec) {
                duree_s = Math.max(5, Math.min(60, parseInt(mSec[1], 10)));
              } else {
                const motsToNum: Record<string, number> = {
                  "cinq": 5, "dix": 10, "quinze": 15, "vingt": 20, "vingt-cinq": 25,
                  "trente": 30, "trente-cinq": 35, "quarante": 40, "quarante-cinq": 45,
                  "cinquante": 50, "cinquante-cinq": 55, "soixante": 60,
                };
                for (const [mot, n] of Object.entries(motsToNum)) {
                  if (new RegExp(`\\b${mot}\\s*secondes?\\b`, "i").test(txt)) {
                    duree_s = n; break;
                  }
                }
              }
            }
            // Arrondi à un multiple de 5 (granularité Kling)
            duree_s = Math.max(5, Math.min(60, Math.round(duree_s / 5) * 5));
            const aspect_ratio: "9:16" | "1:1" | "4:3" | "16:9" =
              /\breel|story|tiktok|insta\s*story|9\s*:\s*16|vertical/.test(txt) ? "9:16"
              : /\binsta\s*(feed|post)?|carr[ée]|square|1\s*:\s*1/.test(txt) ? "1:1"
              : /\b4\s*:\s*3|classique\b/.test(txt) ? "4:3"
              : "16:9";
            const mode: "standard" | "premium" | "ultra" =
              /ultra|cin[ée]ma|broadcast|sora|sota|haute\s*qualit[ée]|tv\s*pro|professionnel|qualit[ée]\s*max/.test(txt) ? "ultra"
              : /rapide|standard|\b(eco|pas\s*cher|low[-\s]?cost)\b|ltx/.test(txt) ? "standard"
              : "premium";
            // Voix-off : détection "avec son / avec voix / avec audio /
            // narration / voix-off / sans son". Et homme/femme si précisé.
            const avecSon = /\b(avec\s*(?:du\s*)?(?:son|audio|voix)|\bvoix[- ]?off\b|narration|with\s*(?:audio|sound|voice)|sonoris[ée]e?|narr[ée]e?)\b/i.test(txt)
              && !/\bsans\s*(?:son|audio|voix)\b|silencieux|silent|muet/i.test(txt);
            const voix: "male" | "female" | undefined =
              /\bvoix\s*(?:d['e]?)?\s*homme|man['s']*\s*voice|male\s*voice|narrateur\s*homme/i.test(txt) ? "male"
              : /\bvoix\s*(?:d['e]?\s*)?femme|woman['s']*\s*voice|female\s*voice|narratrice|voix\s*f[ée]minine/i.test(txt) ? "female"
              : undefined;
            const coutXAF = ({ standard: 60, premium: 240, ultra: 600 } as const)[mode] * Math.ceil(duree_s / 5);
            const coutAudio = avecSon ? Math.max(5, Math.round(duree_s * 0.7)) : 0;
            const nbClips = Math.ceil(duree_s / 10);
            const solo = mode === "standard" ? 15 : mode === "premium" ? 60 : 180;
            const latStr = nbClips === 1 ? `~${solo}s` : `~${Math.round(solo / 60)}-${Math.round(solo / 60) + 1} min`;
            updateLastAssistantMessage(
              `🎥 Génération vidéo en cours (${duree_s}s · ${aspect_ratio} · ${mode}` +
              (avecSon ? ` + 🎙️ voix-off${voix ? " " + voix : " auto"}` : "") +
              `, ~${coutXAF + coutAudio} XAF)…\n` +
              (nbClips > 1
                ? `_${nbClips} clips × 10s générés en parallèle puis stitchés FFmpeg crossfade. Latence ${latStr}` +
                  (avecSon ? " + ~3s TTS ElevenLabs." : ".") +
                  `_`
                : `_Latence estimée : ${latStr}` + (avecSon ? " + ~3s TTS." : ".") + `_`),
              null,
            );
            const result = await generateurApi.video({
              prompt: content, duree_s, mode, aspect_ratio,
              avec_son: avecSon, voix,
            });
            const fid = result.fichier_id;
            const tok = localStorage.getItem("yukpopro_token") || "";
            const baseUrl = result.url_telechargement;
            const url = baseUrl + (baseUrl.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(tok);
            const audioOk = !!(result.avec_son && result.audio_meta?.tts_ok && result.audio_meta?.mux_ok);
            const audioLabel = audioOk
              ? ` 🎙️ ${result.audio_meta?.voix || "auto"} (${result.audio_meta?.langue || "fr"})`
              : (avecSon ? " ⚠️ audio non disponible (TTS indispo)" : "");
            updateLastAssistantMessage(
              `✓ Vidéo ${duree_s}s ${aspect_ratio} (${mode}${audioLabel}, ${result.size_kb} KB) — ${result.cout_fcfa} XAF\n` +
              `[▶ Lire / Télécharger MP4](${url})`,
              null,
              fid ? [fid] : undefined,
            );
            if (fid) {
              addDocument({
                titre: content.slice(0, 80),
                // Type "video" dédié → onglet filtre "Vidéos" dans
                // /mes-documents. Différencié de "visuel" (cartes,
                // flyers, livrets PDF) pour faciliter la recherche.
                type: "video",
                fichier: fid,
                contexteConversation: content,
              });
              toast.success("Vidéo prête");
            }
            return;
          } catch (e: any) {
            const detail = e?.response?.data?.detail || e?.message || "inconnue";
            updateLastAssistantMessage(
              `❌ Erreur génération vidéo : ${detail}`,
              null,
            );
            return;
          }
        }

        // Modification incrémentale site multi-pages (placée AVANT toutes
        // les détections de génération — sinon "modifie la page services"
        // serait capté par siteMultiMatch).
        const modifSiteMatch = /\b(modif|change|mets?\s*à\s*jour|adapte|corrige|remplace|ajoute|enlève|supprime)\b[^.]*\b(mon\s*site|ma\s*page|le\s*site|la\s*page|sur\s*(?:le|mon|notre)\s*site|home|accueil|services?|équipe|equipe|contact|tarifs?|mentions|blog)\b/i.test(txt);
        if (modifSiteMatch) {
          try {
            updateLastAssistantMessage(
              "🔧 Modification incrémentale en cours… (Yukpo identifie la page concernée et applique le changement)",
              null,
            );
            const res = await generateurApi.modifierSiteParChat(content);
            const repub = res.url_publique && res.site_publie === false
              ? `\n\n⚠️ Site publié précédemment : [republie-le depuis /mes-sites](/mes-sites) pour propager les changements en ligne.`
              : "";
            updateLastAssistantMessage(
              `✓ Page **${res.type_page_modifiee}** du site \`${res.site_slug}\` modifiée.${repub}`,
              null,
            );
            toast.success("Modification appliquée");
            return;
          } catch (e: any) {
            const detail = e?.response?.data?.detail || e?.message || "inconnue";
            // 404 = pas de site → fallback flow normal
            if (e?.response?.status === 404) {
              // Continue avec les autres détections (le user n'a peut-être pas
              // encore généré de site — fallback chat normal)
            } else {
              updateLastAssistantMessage(`❌ Erreur modification : ${String(detail).slice(0, 200)}`, null);
              return;
            }
          }
        }

        // Phase D — détection intent boutique e-commerce AVANT site multi-pages
        // LLM Sonnet décide en PRIMAIRE ; regex en fallback uniquement si LLM
        // indispo (sémantique forte > liste de mots-clés).
        const boutiqueMatch = /\b(g[ée]n[èe]re|cr[ée]e|fais|monte|ouvre|d[ée]marre)[^.]*\b(boutique|shop|magasin|e-?commerce|vendre\s+en\s+ligne)\b|\b(boutique\s+en\s+ligne|magasin\s+en\s+ligne|yukpo\s*shop)\b|\bimport\s+(?:ia|magique)\s+(?:de\s+)?(?:produits?|articles?)\b/i.test(txt);
        const wantsBoutique = llmIntent
          ? llmIntent.intent === "boutique_ecommerce"
          : boutiqueMatch;
        if (wantsBoutique) {
          // Pré-suggestion LLM (~1s Haiku) : nom + description + devise + pays
          // déduits du brief chat → MaBoutiquePage les lit depuis sessionStorage
          // et pré-remplit le formulaire d'init. L'user peut tout modifier.
          updateLastAssistantMessage("🛒 Préparation de ta boutique YukpoShop…", null);
          try {
            const sug = await generateurApi.shopSuggererInit(content);
            sessionStorage.setItem("yukposhop_init_suggestions", JSON.stringify({
              ...sug, brief_origine: content, expires_at: Date.now() + 30 * 60_000,
            }));
            updateLastAssistantMessage(
              `🛒 **Boutique e-commerce YukpoShop**\n\n` +
              `J'ai pré-rempli le formulaire d'ouverture avec ces suggestions (modifiable) :\n` +
              `• **Nom** : ${sug.nom}\n` +
              `• **Description** : ${sug.description}\n` +
              `• **Devise** : ${sug.devise} · **Pays** : ${sug.pays_principal}\n\n` +
              `Vérifie / ajuste puis confirme la création :\n` +
              `🎯 [→ Ouvrir ma boutique](/ma-boutique)\n\n` +
              `_Tu pourras ensuite ajouter des produits via **Magic Import IA** (1-10 photos → fiche produit complète auto)._`,
              null,
            );
          } catch {
            // Fallback silencieux si LLM indispo : ancien message statique
            updateLastAssistantMessage(
              `🛒 **Boutique e-commerce YukpoShop**\n\n` +
              `Pour démarrer :\n` +
              `1. [Ouvrir ma boutique](/ma-boutique) — initialise + dashboard\n` +
              `2. Upload 1-10 photos → Magic Import Yukpo Vision compose la fiche produit complète\n` +
              `3. Publier → storefront sur \`<slug>.yukpomnang.com\`\n\n` +
              `🎯 [→ Aller à ma boutique](/ma-boutique)`,
              null,
            );
          }
          return;
        }

        // Phase E1 — détection génération de formulaire/enquête AVANT site multi-pages
        // (un brief "génère un questionnaire/sondage/formulaire" ne doit pas
        // capter dans site_multi).
        // LLM Sonnet décide en PRIMAIRE — il sait que "je souhaite faire une
        // étude de marché pour mon nouveau produit" = enquete_formulaire,
        // même avec typos ou formulation non-impérative. Regex en fallback
        // uniquement si Sonnet timeout/indispo (>4s).
        // 4 branches OR car \b ne fonctionne pas avant 'é' en JS (boundary ASCII)
        const enqueteMatch =
          /(g[ée]n[èe]re|cr[ée]e|fais|produis|monte|lance|m[èe]ne|r[ée]alise|souhaite|veux|aimerais|besoin\s+d['e])[^.]*\b(formulaire|questionnaire|sondage|enqu[êe]te|kobo|xlsform|collecte\s*de\s*donn[ée]es)\b/i.test(txt)
          || /(g[ée]n[èe]re|cr[ée]e|fais|produis|monte|lance|m[èe]ne|r[ée]alise|souhaite|veux|aimerais|besoin\s+d['e])[^.]*[ée]tude\b/i.test(txt)
          || /\b(formulaire|questionnaire|sondage|enqu[êe]te)\s*(de\s*)?(satisfaction|client|audit|conformit[ée]|terrain|sant[ée]|march[ée]|opinion|consommateurs?|produit|acceptabilit[ée]|prix|usage)\b/i.test(txt)
          || /[ée]tude\s+(de\s+|du\s+|sur\s+)?(march[ée]|consommateurs?|produit|acceptabilit[ée]|prix|usage|client[èe]le|cible|opinion|terrain)/i.test(txt);
        const wantsEnquete = llmIntent
          ? llmIntent.intent === "enquete_formulaire"
          : enqueteMatch;
        if (wantsEnquete) {
          try {
            updateLastAssistantMessage(
              "📋 Génération de votre formulaire / étude en cours… (~20-40s)\n_Yukpo compose 15-40 questions XLSForm + dictionnaire variables._",
              null,
            );
            const { data } = await http.post(
              "/enquetes/generer-par-prompt",
              { brief: content, langue: "fr" },
              { timeout: 180_000 },
            );
            updateLastAssistantMessage(
              `✓ **${data.titre}** — ${data.nb_questions} questions générées.\n\n` +
              `🔗 **Lien public de collecte** : copie/colle ce lien pour récolter des réponses :\n` +
              `\`${window.location.origin}${data.lien_public}\`\n\n` +
              `📊 [Voir l'étude et analyser les réponses](/enquetes/${data.etude_id})\n` +
              `📥 [Télécharger XLSForm](${data.lien_xlsform_download})\n\n` +
              (data.analyses_suggerees?.length
                ? `_Analyses suggérées une fois les réponses collectées :_\n` +
                  data.analyses_suggerees.map((a: string) => `- ${a}`).join("\n")
                : ""),
              null,
            );
            toast.success("Formulaire prêt — partagez le lien public");
            return;
          } catch (e: any) {
            const detail = e?.response?.data?.detail || e?.message || "inconnue";
            updateLastAssistantMessage(`❌ Erreur génération formulaire : ${String(detail).slice(0, 200)}`, null);
            return;
          }
        }

        // Phase C — détection site multi-pages AVANT landing single-page
        // (l'utilisateur dit "site 5 pages" → on prend site_multi, pas landing)
        const siteMultiMatch = /(site\s*(web\s*)?(multi[-\s]?pages?|vitrine|complet|\d+\s*pages?)|mini[-\s]?site|site\s*pro|cr[ée][ée]?\s*(un|le)?\s*site|g[ée]n[èe]re\s+un\s+site)/i.test(txt)
          && !/une\s*page|une\s*seule\s*page|one[-\s]?pager|landing/i.test(txt);
        if (siteMultiMatch) {
          try {
            updateLastAssistantMessage(
              "🌐 Génération du mini-site multi-pages en cours… (~30-90s)\n_Yukpo compose 5-7 pages + images IA hero._",
              null,
            );
            const result = await generateurApi.genererSite({
              brief: content, langue: "fr", generer_images: true,
            });
            updateLastAssistantMessage(
              `✓ Site **${result.nom}** généré (${result.nb_pages} pages : ${result.types_pages.join(", ")}).\n\n🌍 Publication Netlify en cours…`,
              null,
            );
            // Auto-publication — l'utilisateur a demandé "génère un site web",
            // pas "génère un brouillon". On enchaîne le deploy Netlify pour
            // qu'il obtienne une URL live immédiatement.
            try {
              const pub = await generateurApi.publierSite(result.slug, "free", true);
              const customUrl = (pub.url_public || `https://${result.slug}.yukpomnang.com`).replace(/^http:/, "https:");
              const fallbackUrl = pub.fallback_netlify_url || null;
              let msg = `✓ Site **${result.nom}** publié (${result.nb_pages} pages).\n\n`;
              // URL .netlify.app fonctionne immédiatement (SSL Netlify natif).
              // Custom domain *.yukpomnang.com a un délai de 5-15 min pour
              // provisionner son cert Let's Encrypt → afficher les deux.
              if (fallbackUrl && pub.is_new_netlify_site) {
                msg += `🌐 **URL accessible maintenant** : [${fallbackUrl}](${fallbackUrl})\n\n`;
                msg += `🔗 **URL personnalisée** (active dans ~5-15 min, le temps du certificat SSL) : ${customUrl}`;
              } else {
                msg += `🌐 [Ouvrir le site](${customUrl})`;
              }
              updateLastAssistantMessage(msg, null);
              toast.success("Site publié !");
            } catch (pubErr: any) {
              const d = pubErr?.response?.data?.detail || pubErr?.message || "inconnue";
              updateLastAssistantMessage(
                `✓ Site **${result.nom}** généré (${result.nb_pages} pages).\n\n` +
                `⚠ Publication automatique échouée : ${String(d).slice(0, 200)}\n\n` +
                `[🚀 Publier manuellement](/mes-sites)`,
                null,
              );
            }
            return;
          } catch (e: any) {
            const detail = e?.response?.data?.detail || e?.message || "inconnue";
            updateLastAssistantMessage(`❌ Erreur génération site : ${String(detail).slice(0, 200)}`, null);
            return;
          }
        }

        const slidesWebMatch = /(slides?\s*web|pr[ée]sentation\s*(web|interactive|reveal|partage|en ligne)|reveal\.?js|html\s*pr[ée]sentation)/i.test(txt);
        const landingMatch = /(landing\s*page|landing|one[-\s]?pager|page\s*(d'?accueil|produit|web\s*unique)|site\s*(web\s*)?une\s*page)/i.test(txt);
        if (slidesWebMatch || landingMatch) {
          try {
            updateLastAssistantMessage(
              slidesWebMatch ? "🎬 Génération de la présentation Reveal.js…"
                             : "🌐 Génération de la landing page web…",
              null,
            );
            const result = slidesWebMatch
              ? await generateurApi.slidesWeb({ sujet: content })
              : await generateurApi.landingPage({ sujet: content });
            const baseUrl = (result as any).url_telechargement;
            const fid = (result as any).fichier_genere;
            // Le lien markdown est rendu en <a href> qui hit le backend SANS
            // header Authorization (le browser ne propage pas axios defaults).
            // Backend `get_current_user` accepte ?token=... en query (priorité
            // 3, SSE-compat). On suffixe le JWT pour que l'ouverture marche
            // sans re-auth.
            const tok = localStorage.getItem("yukpopro_token") || "";
            const url = baseUrl + (baseUrl.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(tok);
            // Sprint A1 — Si landing, ajouter lien "Publier en ligne"
            // (page dédiée /publier-landing/:fichierId → modale Netlify).
            const lienPublier = (!slidesWebMatch && fid)
              ? `\n\n[🚀 Publier en ligne (sous-domaine yukpomnang.com)](/publier-landing/${encodeURIComponent(fid)})`
              : "";
            updateLastAssistantMessage(
              (slidesWebMatch ? "✓ Présentation web Reveal.js générée"
                              : "✓ Landing page web générée") +
              ` — ${result.size_kb} KB.\n[Ouvrir dans le navigateur](${url})${lienPublier}`,
              null,
              fid ? [fid] : undefined,
            );
            if (fid) {
              addDocument({
                titre: result.titre || content.slice(0, 80),
                type: "visuel",
                fichier: fid,
                contexteConversation: content,
              });
              toast.success(slidesWebMatch ? "Présentation web prête" : "Landing prête");
            }
            return;
          } catch (e: any) {
            // Fallback flow normal si l'endpoint échoue
            console.warn("[ChatPage] slides-web/landing fallback :", e?.message);
          }
        }
      }

      // R1-R5 — DÉTECTION MODIFICATION INCRÉMENTALE EN PREMIER
      // Si l'user a un document précédent en session + son message classe
      // 'modification', on route vers /modifier du pipeline mémorisé au lieu
      // de regénérer from scratch via orchestrer + /generer. Évite perte
      // de cohérence + coût LLM ×2.
      // Pas de fichier joint = condition (un fichier joint = nouvelle intent).
      if (files.length === 0 && content.trim()) {
        try {
          const intent = await bureauSessionApi.intent(content);
          if (intent.intent === "modification" && intent.route_modifier && intent.dernier_fichier_id) {
            const modData = await bureauSessionApi.executeModifier(
              intent.route_modifier, intent.dernier_fichier_id, content,
            );
            const fichier_modif = (modData as any)?.fichier_id
                                || (modData as any)?.fichier_genere
                                || (modData as any)?.fichier;
            updateLastAssistantMessage(
              `✓ Modification appliquée sur le document précédent (${intent.pipeline}).` +
              (fichier_modif ? `\n[Télécharger](${generateurApi.telecharger(fichier_modif)})` : ""),
              null,
              fichier_modif ? [fichier_modif] : undefined,
            );
            if (fichier_modif) {
              addDocument({
                titre: `Modification : ${content.slice(0, 60)}`,
                type: intent.pipeline === "rapport" ? "rapport"
                    : intent.pipeline === "slides" ? "slides" : "visuel",
                fichier: fichier_modif,
                contexteConversation: content,
              });
              toast.success("Modification appliquée");
            }
            return;
          }
        } catch (_e_intent) {
          // Si /session/intent échoue → fallback flow standard orchestrer
        }
      }

      // Sprint G1 — Orchestrateur silencieux (boîte noire) :
      // 1. Détecter intent + devis interne (sans afficher au user)
      // 2. Si intent = génération doc/visuel ET peut_payer → générer silencieux
      // 3. Si intent = génération ET solde insuffisant → afficher carte amber bloquante
      // 4. Sinon (conversationnel/ambigu) → flow chatApi.send normal
      const briefAvecContexte = content.trim() + (activeDoc ?
        `\n\n[Contexte : doc actif "${activeDoc.titre}" type=${activeDoc.type_doc}]` : "");

      let orch: any = null;
      try {
        // Si l'utilisateur a joint des fichiers non-audio (images manuscrites,
        // scans, photos de documents, PDF, DOCX, XLSX…) → bascule sur l'endpoint
        // multipart qui OCR-vision les images et extrait le texte natif des
        // autres formats AVANT l'orchestration LLM. Le contenu extrait est
        // ensuite injecté dans payload_pret.contexte pour que la rédaction
        // aval (rapport/slides/visuel/traduction) s'appuie sur le contenu
        // réel des fichiers, pas juste leur nom.
        if (files.length > 0) {
          const filesWithBytes = files.filter(f => !!f.content);
          if (filesWithBytes.length > 0) {
            const fichiersPayload = filesWithBytes.map(f => {
              const b64 = f.content!.includes(",") ? f.content!.split(",")[1] : f.content!;
              const bytes = atob(b64);
              const arr = new Uint8Array(bytes.length);
              for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
              return { nom: f.name, type: f.type || "application/octet-stream", bytes: arr };
            });
            orch = await generateurApi.orchestrerMultipart({
              brief: briefAvecContexte,
              fichiers: fichiersPayload,
            });
          }
        }
        // Fallback : pas de fichiers ou bytes absents → orchestrer JSON classique
        if (!orch) {
          orch = await generateurApi.orchestrer({
            brief: briefAvecContexte,
            contexte_fichiers: files.length > 0
              ? files.map(f => `${f.name} (${f.type})`).join(", ") : undefined,
          });
        }
      } catch { /* fallback silencieux : pas d'orchestration → flow normal */ }

      // ── Architecture plan-driven : orchestrateur LLM (Opus 4.7) compose
      //    un PLAN d'exécution complet { endpoint, method, payload, label,
      //    file_field_hints }. Le frontend exécute ce plan AVEUGLÉMENT, sans
      //    aucun string matching sur intent_detecte / type_sortie. Cela laisse
      //    le LLM router intelligemment vers n'importe quel endpoint backend
      //    (rapport, slides, visuel imprimable, vidéo, traduction, redaction,
      //    OCR, ou tout endpoint ajouté ultérieurement) sans modification du
      //    frontend. Compat ascendante : si plan absent (ancien backend),
      //    fallback sur l'endpoint_cible legacy + check sur peut_payer.
      const plan = orch?.plan;
      const hasPlan = plan && plan.endpoint && plan.payload;
      const hasLegacyCible = orch?.endpoint_cible && orch?.payload_pret;
      const isGeneration = orch && (hasPlan || hasLegacyCible);

      // Cas 1 : génération détectée mais SOLDE INSUFFISANT → toast + lien recharge.
      if (isGeneration && orch.peut_payer === false) {
        updateLastAssistantMessage(
          `⚠️ Crédits insuffisants pour cette tâche.\n\n[→ Recharger mon compte](/abonnement)`,
          null,
        );
        toast.error("Crédits insuffisants. Rechargez votre compte pour continuer.", { duration: 6000 });
        return;
      }

      // Cas 2 : génération détectée + solde OK → exécuter le PLAN aveuglément.
      if (isGeneration && orch.peut_payer === true) {
        try {
          // Source de vérité : orch.plan (nouveau) avec fallback legacy
          const endpoint: string = plan?.endpoint || orch.endpoint_cible;
          const method: string = (plan?.method || "POST").toUpperCase();
          const payload: any = plan?.payload || orch.payload_pret;
          const label: string = plan?.label || orch.template_label || "Document";
          const fileFieldHints: string[] = plan?.file_field_hints || [
            "fichier_genere", "fichier", "pdf_id", "fichier_id",
            "url_telechargement", "download_url",
          ];

          // L'instance axios `http` a baseURL=/api/v1, donc on strip
          // ce préfixe de l'endpoint si présent pour éviter le double.
          const url = endpoint.startsWith("/api/v1/")
            ? endpoint.slice("/api/v1".length)
            : endpoint;

          // Timeout adapté à la durée estimée (par défaut 5 min, max 15 min)
          const timeoutMs = Math.min(
            900_000,
            Math.max(120_000, (orch.duree_estimee_secondes || 120) * 1000 + 60_000),
          );
          const reqConf = { timeout: timeoutMs };

          // ── Sprint chat-everything : endpoints multipart (traduction
          //    fichier, OCR). Le plan signale needs_file_upload=true et
          //    upload_field_name. Si l'utilisateur a joint un fichier
          //    non-audio (audio = déjà transcrit en amont), on reconstruit
          //    la requête en FormData et on injecte le fichier.
          let r: any;
          if (plan?.needs_file_upload === true) {
            // L'endpoint exige un fichier joint (OCR, traduction de fichier,
            // conversion PDF→Word…). Si l'user a oublié de l'attacher OU si
            // le base64 n'est pas encore prêt, on rejette explicitement
            // plutôt que d'envoyer un payload malformé → backend 422 +
            // chat LLM qui hallucine un faux succès.
            if (files.length === 0) {
              updateLastAssistantMessage(
                `📎 **Fichier requis** — pour réaliser cette opération (« ${label} »), ` +
                `joins ton document via l'icône trombone, puis renvoie ta demande.`,
                null,
              );
              return;
            }
            const af = files[0];
            if (!af.content) {
              updateLastAssistantMessage(
                `⏳ **Fichier en cours de lecture…** réessaie dans 1 seconde ` +
                `(le téléchargement local de **${af.name}** n'est pas encore terminé).`,
                null,
              );
              return;
            }
            const fd = new FormData();
            const bytes = atob(af.content.includes(",") ? af.content.split(",")[1] : af.content);
            const arr = new Uint8Array(bytes.length);
            for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
            const blob = new Blob([arr], { type: af.type || "application/octet-stream" });
            fd.append(plan.upload_field_name || "fichier", blob, af.name);
            // Tous les autres champs du payload deviennent des Form fields
            for (const [k, v] of Object.entries(payload || {})) {
              if (v !== undefined && v !== null) fd.append(k, String(v));
            }
            r = (await http.post(url, fd, {
              ...reqConf,
              headers: { "Content-Type": "multipart/form-data" },
            })).data;
          } else {
            r = method === "POST"
              ? (await http.post(url, payload, reqConf)).data
              : method === "PUT"
                ? (await http.put(url, payload, reqConf)).data
                : (await http.get(url, { params: payload, ...reqConf })).data;
          }

          // ── Mode async (job_id + polling) — ex: Freeform avec Flux Pro Ultra
          // qui prend 30-90s. Le backend retourne immédiatement {async:true,
          // job_id, status_url}. On poll toutes les 4s jusqu'à done|failed.
          if (r && r.async === true && r.job_id && r.status_url) {
            const startTime = Date.now();
            const maxWaitMs = 1_200_000;   // 20 min max (cumul de jobs queue sur shared-cpu-1x)
            const pollIntervalMs = 5_000;
            const statusUrl = r.status_url.startsWith("/api/v1/")
              ? r.status_url.slice("/api/v1".length)
              : r.status_url;
            // Affichage transitoire dans le chat
            updateLastAssistantMessage(
              `⏳ Génération en cours — composition + rendu PDF (recto-verso si applicable). Comptez 2-8 min selon densité et charge serveur. Je vous tiens au courant…`,
              null, undefined, null, undefined, undefined,
            );
            const jobIdSafe = r.job_id;
            while (Date.now() - startTime < maxWaitMs) {
              await new Promise(res => setTimeout(res, pollIntervalMs));
              try {
                const poll: any = (await http.get(statusUrl, { timeout: 30_000 })).data;
                const st = poll?.statut;
                if (st === "done") { r = poll; break; }
                if (st === "failed") {
                  throw new Error(poll?.erreur || "Génération échouée");
                }
                // pending/composing/running → continue polling
              } catch (pollErr: any) {
                // Erreur 404 = job expiré (TTL 1h) ou timeout réseau ponctuel
                if (pollErr?.response?.status === 404) {
                  throw new Error("Job introuvable (expiré ?)");
                }
                // Sinon on retente au tour suivant (network blip, etc.)
              }
            }
            if (r?.async === true) {
              // Polling 20min épuisé sans 'done' — le job continue en background
              // côté backend. On affiche un message clair AVEC le job_id +
              // lien vers Mes Documents, et on NE FALLBACK PAS sur chat
              // normal (ça créerait une 2e requête lente et confuserait l'user).
              updateLastAssistantMessage(
                `⏳ **Génération encore en cours en arrière-plan** (job ${jobIdSafe.slice(0, 8)}…).\n\n` +
                `Le rendu prend plus longtemps que prévu (forte densité ou charge serveur). ` +
                `Le PDF apparaîtra automatiquement dans **[Mes Documents](/mes-documents)** dans 1-3 minutes.\n\n` +
                `Pas besoin de relancer — la tâche est sauvée.`,
                null, undefined, null, undefined, undefined,
              );
              return;  // sort proprement de sendMessage sans fallback chat
            }
          }

          // Extraction générique du fichier depuis la réponse.
          // Essai 1 : réponses multi-pages (Designer Pro projets)
          const fichiers: string[] = [];
          if (Array.isArray(r.pages)) {
            for (const p of r.pages) {
              if (p?.fichier_id) fichiers.push(p.fichier_id);
              else if (p?.url) fichiers.push(p.url);
            }
          }
          // Essai 2 : champ unique selon les hints du plan (multi-alias)
          if (fichiers.length === 0) {
            for (const hint of fileFieldHints) {
              const v = r?.[hint];
              if (typeof v === "string" && v) {
                fichiers.push(v);
                break;
              }
            }
          }

          // Construction de l'URL de téléchargement : on privilégie
          // download_url / url_telechargement de la réponse (l'endpoint
          // sait où il a stocké le fichier). Sinon on applique le
          // pattern fourni par le plan. Sinon fallback Pro hardcodé.
          //
          // CRITIQUE : suffixer ?token= sur les URLs qui pointent vers des
          // endpoints nécessitant auth (/bureau/documents/*, /pro/generateurs/
          // fichier/*). Sinon le markdown [Télécharger](url) rendu dans le
          // chat crée un <a href> que le browser GET sans header
          // Authorization → 401. Le backend get_current_user accepte
          // ?token= en query (priorité 3, SSE-compat).
          const _suffixToken = (url: string): string => {
            if (!url) return url;
            if (url.includes("token=")) return url;
            // Détection : URL contient un chemin auth-protégé Yukpo, qu'elle
            // soit relative ("/api/v1/...") ou absolue ("https://yukpopro-
            // backend.fly.dev/api/v1/..."). En prod le frontend appelle
            // l'absolu (cf. API_BASE_URL=https://...) donc startsWith("/api/v1")
            // ne match jamais → token jamais ajouté → 401 sur download.
            // Solution : utiliser .includes() sur les segments du chemin.
            const needsAuth =
              url.includes("/api/v1/bureau/documents/")
              || url.includes("/api/v1/pro/generateurs/fichier/")
              || url.includes("/api/v1/bureau/video/fichier/");
            if (!needsAuth) return url;
            // Si URL externe (autre domaine), ne pas exposer le token Yukpo
            try {
              if (/^https?:\/\//.test(url)) {
                const u = new URL(url);
                if (!u.hostname.endsWith("yukpomnang.com")
                    && !u.hostname.endsWith("fly.dev")) {
                  return url;
                }
              }
            } catch { /* URL parsing échoué : on continue */ }
            const tok = localStorage.getItem("yukpopro_token") || "";
            if (!tok) return url;
            return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(tok);
          };
          const buildDownloadUrl = (fichier: string): string => {
            let base: string;
            if (typeof r.download_url === "string" && r.download_url) base = r.download_url;
            else if (typeof r.url_telechargement === "string" && r.url_telechargement) base = r.url_telechargement;
            else {
              const pattern = plan?.download_url_pattern;
              if (typeof pattern === "string" && pattern.includes("{fichier}")) {
                base = pattern.replace("{fichier}", fichier);
              } else if (endpoint.startsWith("/api/v1/bureau/")) {
                base = `/api/v1/bureau/documents/${fichier}`;
              } else {
                base = generateurApi.telecharger(fichier);
              }
            }
            return _suffixToken(base);
          };
          const downloadUrl = fichiers.length > 0 ? buildDownloadUrl(fichiers[0]) : "";

          // Construction du message visible dans le chat avec le lien
          // markdown clickable + indication recto-verso si applicable.
          const nbPages = Number(r?.nb_pages) || 0;
          const versoHint =
            nbPages > 1
              ? `\n\n💡 *Impression recto-verso* : duplex long-edge (par défaut). Planches numérotées RECTO/VERSO en haut.`
              : "";

          // Questions d'amélioration ciblées (audit Sonnet Vision côté backend).
          // Chaque question = 2-4 propositions actionnables. On les mappe en
          // chips SuggestionSuite cliquables — clic = proposition pré-remplie
          // dans le textarea, l'user peut éditer ou envoyer tel quel.
          const questionsAmel = Array.isArray(r?.questions_amelioration)
            ? r.questions_amelioration : [];
          const ameliorationChips: SuggestionSuite[] = [];
          for (const q of questionsAmel) {
            if (!q || !Array.isArray(q.propositions)) continue;
            q.propositions.forEach((prop: string, i: number) => {
              if (typeof prop !== "string" || !prop.trim()) return;
              ameliorationChips.push({
                action: `amelioration_${q.axe || "libre"}_${i}`,
                label: prop.length > 60 ? prop.slice(0, 57) + "…" : prop,
                prompt_suggere: prop,
              });
            });
          }
          let questionsHint = "";
          if (questionsAmel.length > 0) {
            const score = r?.audit_qualite?.score_qualite_sur_10;
            const scoreStr = typeof score === "number"
              ? ` *(audit : ${score}/10)*` : "";
            questionsHint = `\n\n💬 **Pistes d'amélioration**${scoreStr} — clique un chip ci-dessous pour itérer :`;
            for (const q of questionsAmel) {
              if (q?.question) questionsHint += `\n• ${q.question}`;
            }
          }

          const allSuggestions: SuggestionSuite[] = [
            ...ameliorationChips,
            ...((r.suggestions as SuggestionSuite[]) ?? []),
          ];

          updateLastAssistantMessage(
            `🎨 **${label} généré${nbPages > 1 ? ` — ${nbPages} pages` : ""}.**` +
            (downloadUrl ? `\n\n📥 **[Télécharger le PDF](${downloadUrl})**` : "") +
            versoHint +
            questionsHint,
            null,
            fichiers.length > 0 ? fichiers : undefined,
            null, undefined,
            allSuggestions.length > 0 ? allSuggestions : undefined,
          );
          if (fichiers.length > 0) {
            addDocument({
              titre: label,
              type: orch.type_sortie || plan?.type_resultat || "document",
              fichier: fichiers[0],
              contexteConversation: content,
            });
            toast.success(`${label} prêt`);
          }
          return;
        } catch (genErr: any) {
          // ⚠️ NE PAS fallback sur chat conversationnel : le LLM hallucinerait
          // un faux succès avec un lien de téléchargement bidon (vu en prod :
          // OCR scanner 400 → chat répond "Conversion effectuée avec succès"
          // + lien 401). Afficher l'erreur explicite à l'utilisateur.
          // eslint-disable-next-line no-console
          console.warn("[ChatPage/G1] génération échouée:", genErr);
          const status = genErr?.response?.status;
          const detail = genErr?.response?.data?.detail
                       || genErr?.message
                       || "Erreur inconnue";
          let msg = `❌ La génération a échoué`;
          if (status === 400) {
            msg += ` — requête invalide.\n\n_Détail :_ ${String(detail).slice(0, 200)}\n\n` +
                   `Vérifie le format du fichier joint ou reformule ton brief.`;
          } else if (status === 402) {
            msg = `⚠️ Crédits insuffisants pour cette opération.\n\n[→ Recharger mon compte](/abonnement)`;
          } else if (status === 503) {
            msg += ` — service temporairement indisponible.\n\nRéessaie dans 1-2 minutes.`;
          } else {
            msg += ` (HTTP ${status || "?"}).\n\n_Détail :_ ${String(detail).slice(0, 200)}`;
          }
          updateLastAssistantMessage(msg, null);
          return;  // pas de fallback — message d'erreur clair affiché
        }
      }

      // Cas 3 (par défaut) : conversationnel/ambigu → chatApi.send normal
      // Optim : si l'orchestrateur (au-dessus) a déjà tranché qa_simple
      // (route_to_chat=true), on passe skip_orchestration=true pour bypass
      // le classifier interne du chat (gpt-4o-mini ~1.5-2s). Le LLM principal
      // est appelé directement → tour de chat -1.5 à -2.5s.
      const orchSaidQa = orch && (orch as any).route_to_chat === true;
      const res = await chatApi.send({
        message: content.trim(),
        pays: profil?.pays,
        fichiers: files.map(f => ({ nom: f.name, contenu: f.content || "", type: f.type })),
        document_ref: activeDoc ? {
          id: activeDoc.id,
          titre: activeDoc.titre,
          type_doc: activeDoc.type_doc,
          contenu_genere: activeDoc.contenu_genere,
        } : undefined,
        skip_orchestration: orchSaidQa || undefined,
      });

      updateLastAssistantMessage(
        _rewriteDocumentLinks(res.reponse),
        res.agent_utilise ?? null,
        res.fichiers_generes ?? undefined,
        res.cout_llm ?? null,
        res.navigation_suggestions ?? [],
      );

      // Sauvegarder les documents générés dans l'historique
      if (res.fichiers_generes && res.fichiers_generes.length > 0) {
        res.fichiers_generes.forEach(f => {
          addDocument({
            titre: content.slice(0, 60) || f,
            type: f.endsWith(".docx") ? "rapport" : f.endsWith(".pptx") ? "slides" : "traduction",
            fichier: f,
            contexteConversation: content,
          });
        });
        const nb = res.fichiers_generes.length;
        toast.success(nb === 1 ? "Document prêt — lien de téléchargement disponible" : `${nb} documents prêts au téléchargement`);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.code === "CREDITS_EPUISES") {
        updateLastAssistantMessage(
          `⚠️ **${detail.message}** ${detail.action}\n\n[→ Recharger mes crédits / Changer de plan](/abonnement)`,
          null,
        );
        toast.error(t("chat.creditsExpired"));
      } else {
        const msg = typeof detail === "string" ? detail : t("chat.connectionError");
        updateLastAssistantMessage(`⚠️ ${msg}`, null);
        toast.error(t("chat.yukpoError"));
      }
    } finally {
      setLoading(false);
    }
  }, [isLoading, profil, addMessage, updateLastAssistantMessage, setLoading]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(input, attachedFiles);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input, attachedFiles);
    }
  };

  // ── Upload de fichier ──────────────────────────────────────────────────────

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    setUploadingFile(true);

    for (const file of files) {
      try {
        const content = await readFileAsBase64(file);
        setAttachedFiles(prev => [...prev, {
          id: crypto.randomUUID(),
          name: file.name,
          size: file.size,
          type: file.type,
          content,
        }]);
      } catch {
        toast.error(`Impossible de lire ${file.name}`);
      }
    }
    setUploadingFile(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeFile = (id: string) =>
    setAttachedFiles(prev => prev.filter(f => f.id !== id));

  // ── Helpers ────────────────────────────────────────────────────────────────

  const handleNewSession = () => {
    newSession();
    setInput("");
    setAttachedFiles([]);
  };

  // ── Enregistrement audio (MediaRecorder + SpeechRecognition) ─────────────

  const startRecording = async () => {
    // Essai 1 : SpeechRecognition (Chrome/Edge) — transcription en temps réel, mode continu
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SR) {
      const recognition = new SR();
      recognitionRef.current = recognition;
      recognition.lang = "fr-FR";
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      let finalTranscript = "";

      recognition.onresult = (e: any) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const res = e.results[i];
          if (res.isFinal) finalTranscript += res[0].transcript + " ";
          else interim += res[0].transcript;
        }
        // Afficher en direct dans le champ texte
        setInput(finalTranscript + interim);
      };
      recognition.onerror = (e: any) => {
        if (e.error !== "aborted") toast.error(t("chat.micError", { err: e.error }));
        stopRecording(false);
      };
      recognition.onend = () => {
        // Ne pas arrêter si l'utilisateur n'a pas cliqué stop
        if (isRecording) recognition.start();
      };
      recognition.start();
      setIsRecording(true);
      setAudioModalOpen(true);
      setAudioSeconds(0);
      timerRef.current = setInterval(() => setAudioSeconds(s => s + 1), 1000);
      acquireWakeLock();
      return;
    }

    // Essai 2 : MediaRecorder (Firefox, Safari, etc.) — enregistrement blob
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        await envoyerAudio(blob);
      };

      mr.start(500);
      setIsRecording(true);
      setAudioModalOpen(true);
      setAudioSeconds(0);
      timerRef.current = setInterval(() => setAudioSeconds(s => s + 1), 1000);
      // Empêche l'écran de s'éteindre pendant l'enregistrement (Chrome/Edge/Android).
      acquireWakeLock();
    } catch (err) {
      toast.error(t("chat.micPermissionError"));
    }
  };

  const stopRecording = (send = true) => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }

    // SpeechRecognition
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
      setIsRecording(false);
      setAudioModalOpen(false);
      releaseWakeLock();
      if (send && input.trim()) {
        sendMessage(input.trim(), []);
        setInput("");
      }
      return;
    }

    // MediaRecorder — onstop déclenchera envoyerAudio() qui transcrira puis enverra
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      // Si l'utilisateur annule (send=false), on désactive le flag pour bypass envoyerAudio
      if (!send) (mediaRecorderRef.current as MediaRecorder & { _cancelled?: boolean })._cancelled = true;
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    setAudioModalOpen(false);
    releaseWakeLock();
  };

  const envoyerAudio = async (blob: Blob) => {
    const mr = mediaRecorderRef.current as (MediaRecorder & { _cancelled?: boolean }) | null;
    if (mr?._cancelled) return; // utilisateur a annulé l'enregistrement
    // Transcription côté serveur via Whisper (endpoint réunion réutilisé).
    // Une fois transcrit, on envoie le résultat comme un message texte normal —
    // l'orchestrateur du chat le traite alors comme une question écrite classique.
    const toastId = toast.loading(t("chat.audioTranscribing"));
    try {
      const fd = new FormData();
      fd.append("audio", blob, `audio_${Date.now()}.webm`);
      fd.append("langue", "auto");
      const res = await reunionsApi.transcrireDirect(fd);
      const texte = (res.transcription || "").trim();
      if (!texte) {
        toast.error(t("chat.audioTranscriptionEmpty"), { id: toastId });
        return;
      }
      toast.dismiss(toastId);
      sendMessage(texte, []);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || t("chat.audioTranscriptionError"), { id: toastId });
    }
  };

  const blobToBase64 = (blob: Blob): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve((reader.result as string).split(",")[1] || "");
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });

  const toggleRecording = () => {
    if (isRecording) stopRecording(true);
    else startRecording();
  };

  // ── Camera scan (document, reçu, carte de visite, identité, etc.) ────────
  // getUserMedia { facingMode: "environment" } pour utiliser la caméra arrière
  // sur mobile (meilleure résolution + autofocus). Sur desktop, prend la
  // webcam par défaut. Capture via canvas → JPG 90% qualité → injecte comme
  // File dans le pipeline d'attachement existant (handleFileSelect).
  const handleCameraClick = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
      setCameraStream(stream);
      setCameraModalOpen(true);
      setTimeout(() => {
        if (videoRef.current) videoRef.current.srcObject = stream;
      }, 100);
    } catch (err: any) {
      toast.error(t("chat.cameraPermissionError", "Accès caméra refusé"));
    }
  };

  const closeCameraModal = () => {
    if (cameraStream) {
      cameraStream.getTracks().forEach((tr) => tr.stop());
      setCameraStream(null);
    }
    setCameraModalOpen(false);
  };

  const capturePhoto = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;
    canvasRef.current.width = videoRef.current.videoWidth;
    canvasRef.current.height = videoRef.current.videoHeight;
    ctx.drawImage(videoRef.current, 0, 0);
    canvasRef.current.toBlob(
      (blob) => {
        if (!blob) return;
        const file = new File(
          [blob],
          `scan_${Date.now()}.jpg`,
          { type: "image/jpeg" },
        );
        // Réutilise handleFileSelect via un FileList synthétique
        const dt = new DataTransfer();
        dt.items.add(file);
        if (fileInputRef.current) {
          fileInputRef.current.files = dt.files;
          fileInputRef.current.dispatchEvent(new Event("change", { bubbles: true }));
        }
        closeCameraModal();
      },
      "image/jpeg",
      0.92,
    );
  };

  const formatDureeAudio = (sec: number) => {
    const m = Math.floor(sec / 60).toString().padStart(2, "0");
    const s = (sec % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  };

  const fileIcon = (type: string) => {
    if (type.startsWith("image/")) return <Image className="w-3.5 h-3.5" />;
    if (type.includes("spreadsheet") || type.includes("excel") || type.includes("csv"))
      return <Table className="w-3.5 h-3.5" />;
    return <FileText className="w-3.5 h-3.5" />;
  };

  // ── Rendu ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full overflow-hidden" style={{ background: "transparent" }}>

      {/* ── Sidebar historique ─────────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {historySidebarOpen && (
          <>
            {/* Overlay backdrop sur mobile */}
            {isMobile && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setHistorySidebarOpen(false)}
                className="fixed inset-0 bg-black/50 z-20"
              />
            )}

            <motion.div
              initial={isMobile ? { x: -280 } : { width: 0, opacity: 0 }}
              animate={isMobile ? { x: 0 } : { width: 260, opacity: 1 }}
              exit={isMobile ? { x: -280 } : { width: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className={cn(
                "flex flex-col bg-slate-900 border-r border-slate-800 overflow-hidden",
                isMobile
                  ? "fixed left-0 top-0 h-full w-72 z-30 shadow-2xl flex-shrink-0"
                  : "flex-shrink-0"
              )}
              style={!isMobile ? { width: 260 } : undefined}
            >
              {/* Header */}
              <div className="p-3 border-b border-slate-800 flex-shrink-0 flex gap-2">
                <button
                  onClick={handleNewSession}
                  className="flex-1 flex items-center gap-2 px-3 py-2.5 rounded-xl bg-yukpo-600 hover:bg-yukpo-500 text-white text-sm font-semibold transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  {t('chat.newConversation')}
                </button>
                {isMobile && (
                  <button
                    onClick={() => setHistorySidebarOpen(false)}
                    className="p-2.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>

              {/* Sessions */}
              <div className="flex-1 overflow-y-auto py-2">
                {sessions.length === 0 ? (
                  <p className="text-center text-slate-500 text-xs mt-8 px-4">
                    {t('chat.noConversations')}
                  </p>
                ) : (
                  sessions.map((session) => (
                    <div
                      key={session.id}
                      className={cn(
                        "group flex items-center gap-2 mx-2 px-3 py-2.5 rounded-xl cursor-pointer text-sm transition-colors",
                        session.id === activeSessionId
                          ? "bg-yukpo-500/20 border border-yukpo-400/40 text-white font-medium"
                          : "text-slate-200 hover:bg-slate-800 hover:text-white"
                      )}
                      onClick={() => { selectSession(session.id); if (isMobile) setHistorySidebarOpen(false); }}
                    >
                      <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                      <span className="flex-1 truncate">{session.title}</span>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
                        className="opacity-0 group-hover:opacity-100 hover:text-red-400 transition-opacity p-0.5"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ── Zone principale ─────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Header */}
        <div className="flex-shrink-0 flex items-center gap-3 px-4 py-3 border-b border-slate-800 bg-slate-900">
          <button
            onClick={() => setHistorySidebarOpen(!historySidebarOpen)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
          >
            {historySidebarOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>

          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-yukpo-gradient flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <div className="min-w-0">
              <h1 className="text-white font-semibold text-sm">Yukpo Pro</h1>
              <p className="text-slate-400 text-xs truncate">
                {activeSession()?.title && messages.length > 0
                  ? activeSession()!.title
                  : `${metierCtx.label} · ${profil?.pays ?? "Afrique"}`}
              </p>
            </div>
          </div>

          <button
            onClick={() => setProfilModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-slate-700 transition-colors border border-slate-700"
            title={t('chat.editProfile')}
          >
            <Pencil className="w-3.5 h-3.5" />
            {messages.length === 0 && <span className="hidden sm:inline">{t('chat.myProfile')}</span>}
          </button>

          {messages.length > 0 && (
            <button
              onClick={handleNewSession}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-slate-700 transition-colors border border-slate-700"
            >
              <Plus className="w-3.5 h-3.5" />
              {t('chat.new')}
            </button>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            // ── Écran de bienvenue ──────────────────────────────────────────
            <WelcomeScreen
              profil={profil}
              user={user}
              metierCtx={metierCtx}
              suggestions={[]}
              onSuggestion={() => {}}
              onEditProfil={() => setProfilModalOpen(true)}
            />
          ) : (
            // ── Messages ────────────────────────────────────────────────────
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onPickSuggestion={(prompt) => {
                    setInput(prompt);
                    inputRef.current?.focus();
                  }}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* ── Zone d'input ───────────────────────────────────────────────── */}
        <div className="flex-shrink-0 bg-slate-900 border-t border-slate-800 px-4 py-4">
          <div className="max-w-3xl mx-auto">

            {/* Document en cours d'édition */}
            {activeDocument() && (
              <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-lg bg-yukpo-500/10 border border-yukpo-500/30 text-xs">
                <Pencil className="w-3.5 h-3.5 text-yukpo-400 flex-shrink-0" />
                <span className="text-slate-300">{t("chat.editingDocument")}</span>
                <span className="text-yukpo-300 font-medium truncate max-w-md">{activeDocument()?.titre}</span>
                <button
                  type="button"
                  onClick={() => setActiveDocument(null)}
                  className="ml-auto text-slate-400 hover:text-red-400"
                  title={t("chat.exitEditMode")}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* BATCH-4 — File d'attente messages pendant génération */}
            {pendingQueue.length > 0 && (
              <div className="mb-3 px-3 py-2 bg-yukpo-900/40 border border-yukpo-700/50 rounded-xl text-xs">
                <p className="text-yukpo-200 font-medium flex items-center gap-1.5">
                  <Plus className="w-3.5 h-3.5" />
                  {pendingQueue.length} {pendingQueue.length === 1 ? "message en attente" : "messages en attente"}
                  <span className="text-slate-400 font-normal ml-1">
                    — envoi{pendingQueue.length > 1 ? "s" : ""} après la réponse en cours
                  </span>
                </p>
                <ul className="mt-1 space-y-0.5">
                  {pendingQueue.map((p, i) => (
                    <li key={i} className="flex items-center gap-2 text-slate-300">
                      <span className="text-slate-500 font-mono">#{i + 1}</span>
                      <span className="flex-1 truncate">
                        {p.content || `[${p.files.length} fichier${p.files.length > 1 ? "s" : ""}]`}
                        {p.files.length > 0 && p.content && (
                          <span className="text-slate-500 ml-1">
                            (+{p.files.length} fichier{p.files.length > 1 ? "s" : ""})
                          </span>
                        )}
                      </span>
                      <button onClick={() => retirerDeLaQueue(i)}
                        className="text-red-400 hover:text-red-300" title="Retirer de la file">
                        <X className="w-3 h-3" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Fichiers attachés */}
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {attachedFiles.map(f => (
                  <div key={f.id} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-700 border border-slate-600 text-xs text-slate-300">
                    {fileIcon(f.type)}
                    <span className="max-w-[120px] truncate">{f.name}</span>
                    <span className="text-slate-500">{formatFileSize(f.size)}</span>
                    <button onClick={() => removeFile(f.id)} className="hover:text-red-400 ml-1">
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div className={cn(
                "flex items-end gap-2 rounded-2xl border transition-colors bg-slate-800",
                isLoading ? "border-slate-700" : "border-slate-600 focus-within:border-yukpo-500"
              )}>
                {/* Bouton fichier */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadingFile}
                  className="flex-shrink-0 p-3 text-slate-400 hover:text-yukpo-400 transition-colors disabled:opacity-40"
                  title={t("chat.attachFileTitle")}
                >
                  {uploadingFile
                    ? <div className="w-5 h-5 border-2 border-slate-500 border-t-yukpo-400 rounded-full animate-spin" />
                    : <Paperclip className="w-5 h-5" />
                  }
                </button>

                {/* Bouton micro */}
                <button
                  type="button"
                  onClick={toggleRecording}
                  className={cn(
                    "flex-shrink-0 p-3 transition-colors disabled:opacity-40",
                    isRecording
                      ? "text-red-400 animate-pulse"
                      : "text-slate-400 hover:text-yukpo-400"
                  )}
                  title={isRecording ? t("chat.stopDictation") : t("chat.voiceDictation")}
                >
                  {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
                </button>

                {/* Bouton caméra (scan document/reçu/carte) */}
                <button
                  type="button"
                  onClick={handleCameraClick}
                  disabled={uploadingFile}
                  className="flex-shrink-0 p-3 text-slate-400 hover:text-yukpo-400 transition-colors disabled:opacity-40"
                  title={t("chat.cameraCapture", "Scanner un document avec la caméra")}
                >
                  <Camera className="w-5 h-5" />
                </button>

                {/* Input texte */}
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    e.target.style.height = "auto";
                    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    attachedFiles.length > 0
                      ? t('chat.attachPlaceholder')
                      : t('chat.mainPlaceholder')
                  }
                  className="flex-1 bg-transparent text-white text-sm placeholder-slate-500 py-3 pr-2 resize-none focus:outline-none min-h-[48px] max-h-[160px] overflow-y-auto"
                  style={{ height: "48px" }}
                />

                {/* Bouton envoyer — pendant génération, le bouton reste actif
                    pour mettre en file d'attente (BATCH-4). Disabled uniquement
                    si rien à envoyer. */}
                <button
                  type="submit"
                  disabled={!input.trim() && attachedFiles.length === 0}
                  title={isLoading
                    ? t("chat.queueAdd", "Mettre en file (envoi après la réponse en cours)")
                    : t("chat.send", "Envoyer")}
                  className={cn(
                    "flex-shrink-0 m-2 p-2 rounded-xl text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                    isLoading
                      ? "bg-yukpo-500 hover:bg-yukpo-400"
                      : "bg-yukpo-600 hover:bg-yukpo-500"
                  )}
                >
                  {isLoading
                    ? <Plus className="w-4 h-4" />
                    : <Send className="w-4 h-4" />
                  }
                </button>
              </div>
            </form>

            <p className="text-center text-slate-600 text-xs mt-2">
              {t('chat.disclaimer')}
            </p>
          </div>
        </div>
      </div>

      {/* Input fichier caché — large couverture MIME pour tous les usages
          (documents, slides, tableurs, images, audio, archives, texte) */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.odt,.rtf,.xls,.xlsx,.ods,.csv,.tsv,.ppt,.pptx,.odp,.txt,.md,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tiff,.tif,.svg,.heic,.heif,.mp3,.wav,.m4a,.ogg,.webm,.zip"
        onChange={handleFileSelect}
        className="hidden"
      />

      {/* ── Modal Camera (scan document) ─────────────────────────────────── */}
      <AnimatePresence>
        {cameraModalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-slate-900 border border-slate-700 rounded-2xl p-4 w-full max-w-md shadow-2xl"
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-white font-semibold text-sm flex items-center gap-2">
                  <Camera className="w-4 h-4 text-yukpo-400" />
                  {t("chat.cameraCapture", "Scanner un document")}
                </h3>
                <button
                  onClick={closeCameraModal}
                  className="p-1 text-slate-400 hover:text-white"
                  aria-label="Fermer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full rounded-lg mb-3 bg-black aspect-video object-cover"
              />
              <canvas ref={canvasRef} className="hidden" />
              <div className="flex gap-2">
                <button
                  onClick={closeCameraModal}
                  className="flex-1 px-4 py-2 rounded-lg border border-slate-600 text-slate-400 hover:text-white hover:border-slate-500 text-sm"
                >
                  {t("common.cancel", "Annuler")}
                </button>
                <button
                  onClick={capturePhoto}
                  className="flex-1 px-4 py-2 rounded-lg bg-yukpo-600 hover:bg-yukpo-500 text-white font-medium flex items-center justify-center gap-2 text-sm"
                >
                  <Camera className="w-4 h-4" />
                  {t("chat.takePhoto", "Capturer")}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Modal Audio ─────────────────────────────────────────────────── */}
      <AnimatePresence>
        {audioModalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-slate-900 border border-slate-700 rounded-2xl p-8 w-full max-w-sm shadow-2xl text-center"
            >
              {/* Animation micro */}
              <div className="relative w-20 h-20 mx-auto mb-6">
                <div className="absolute inset-0 rounded-full bg-red-500/20 animate-ping" />
                <div className="absolute inset-2 rounded-full bg-red-500/30 animate-ping animation-delay-75" />
                <div className="relative w-20 h-20 rounded-full bg-red-500/20 border-2 border-red-500 flex items-center justify-center">
                  <Mic className="w-8 h-8 text-red-400" />
                </div>
              </div>

              <h3 className="text-white font-bold text-lg mb-1">{t('chat.recordingTitle')}</h3>
              <p className="text-slate-400 text-sm mb-3">
                {recognitionRef.current
                  ? t('chat.speakRealtime')
                  : t('chat.speakClear')}
              </p>

              {/* Transcription en temps réel */}
              {input && (
                <div className="bg-slate-800 rounded-xl p-3 mb-4 text-left">
                  <p className="text-slate-300 text-sm leading-relaxed line-clamp-4">{input}</p>
                </div>
              )}

              {/* Timer */}
              <div className="font-mono text-2xl text-red-400 font-bold mb-6">
                {formatDureeAudio(audioSeconds)}
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={() => { stopRecording(false); setInput(""); }}
                  className="flex-1 px-4 py-3 rounded-xl border border-slate-600 text-slate-400 hover:text-white hover:border-slate-500 transition-colors text-sm font-medium"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={() => stopRecording(true)}
                  className="flex-1 px-4 py-3 rounded-xl bg-yukpo-600 hover:bg-yukpo-500 text-white transition-colors text-sm font-bold flex items-center justify-center gap-2"
                >
                  <Send className="w-4 h-4" />
                  {t('common.send')}
                </button>
              </div>

              <p className="text-slate-600 text-xs mt-3">
                {recognitionRef.current
                  ? t("chat.transcriptionAuto")
                  : t("chat.audioMessage")}
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Modale édition profil */}
      <AnimatePresence>
        {profilModalOpen && (
          <ProfilModal
            profil={profil}
            onClose={() => setProfilModalOpen(false)}
            onSaved={(updated) => {
              useProfilStore.getState().setProfil(updated);
              setProfilModalOpen(false);
              toast.success(t("chat.profileUpdated"));
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
};

// ── Écran de bienvenue ────────────────────────────────────────────────────────

// ── Construit le message de bienvenue contextuel ─────────────────────────────

const PAYS_LABELS: Record<string, string> = {
  CM: "Cameroun", CI: "Côte d'Ivoire", SN: "Sénégal", BF: "Burkina Faso",
  TG: "Togo", BJ: "Bénin", ML: "Mali", NE: "Niger", GA: "Gabon",
  CG: "Congo", CD: "RD Congo", TD: "Tchad", CF: "Centrafrique",
  GN: "Guinée", DZ: "Algérie", MA: "Maroc", TN: "Tunisie",
  MG: "Madagascar", MR: "Mauritanie", GQ: "Guinée équatoriale",
  RW: "Rwanda", BI: "Burundi", DJ: "Djibouti", FR: "France",
};

function buildWelcomeText(profil: any, metierCtx: typeof METIERS_CONFIG[string]): string {
  if (!profil?.metier) {
    return "Je suis Yukpo Pro, votre assistant professionnel intelligent. Posez-moi une question, envoyez un document à analyser ou traduire, ou demandez-moi de générer un rapport — je comprends le langage naturel et m'adapte à votre demande.";
  }
  const paysNom = profil.pays ? (PAYS_LABELS[profil.pays] || profil.pays) : "";
  const surPays = paysNom ? ` au ${paysNom}` : " en Afrique";
  const metierLabel = metierCtx.label || "professionnels";
  const agents = metierCtx.agents.slice(0, 2).map((a) => `l'${a}`).join(" et ");
  return `Je suis Yukpo Pro, votre assistant IA dédié aux ${metierLabel.toLowerCase()}${surPays}. Je peux analyser vos documents, générer des rapports, traduire vos fichiers et mobiliser ${agents || "des agents spécialisés"} pour des analyses pointues. Posez-moi votre première question ou envoyez un document.`;
}

const WelcomeScreen = ({
  profil, user, metierCtx, onEditProfil,
}: {
  profil: any; user: any; metierCtx: typeof METIERS_CONFIG[string];
  suggestions: string[]; onSuggestion: (s: string) => void; onEditProfil: () => void;
}) => {
  const { t } = useTranslation();
  const prenom = user?.prenom || user?.nom?.split(" ")[0] || "";
  const fallbackText = React.useMemo(() => buildWelcomeText(profil, metierCtx), [profil, metierCtx]);
  const [welcomeText, setWelcomeText] = React.useState<string>(fallbackText);

  React.useEffect(() => {
    let cancelled = false;
    copiloteApi
      .welcome()
      .then((res) => {
        if (!cancelled && res?.message) setWelcomeText(res.message);
      })
      .catch(() => {
        // garde le fallback grammaticalement correct
      });
    return () => { cancelled = true; };
  }, [profil?.metier, profil?.pays, profil?.niveau_expertise]);

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 max-w-xl mx-auto w-full text-center">
      <div className="w-16 h-16 rounded-2xl bg-yukpo-gradient flex items-center justify-center mb-6 shadow-lg shadow-yukpo-500/20">
        <span className="text-2xl">{metierCtx.emoji}</span>
      </div>

      <h2 className="text-2xl font-display font-bold text-white mb-1">
        {prenom ? t('chat.hello', { name: prenom }) : t('chat.helloDefault')}
      </h2>

      <p className="text-yukpo-400 text-xs font-semibold uppercase tracking-widest mb-5">
        Yukpo Pro — Assistant IA
      </p>

      <p className="text-slate-300 text-[15px] leading-relaxed mb-6 max-w-md">
        {welcomeText}
      </p>

      <button
        onClick={onEditProfil}
        className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-yukpo-400 transition-colors underline underline-offset-2"
      >
        <Pencil className="w-3 h-3" />
        {profil?.metier ? t('chat.editProfile') : t('chat.configureProfile')}
      </button>
    </div>
  );
};

// ── Bulle de message ──────────────────────────────────────────────────────────

const SuggestionsSuiteChips = ({
  suggestions, onPick,
}: {
  suggestions: SuggestionSuite[];
  onPick: (prompt: string) => void;
}) => {
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <div className="mt-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">Suggestions de suite</div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <button
            key={s.action}
            type="button"
            onClick={() => onPick(s.prompt_suggere)}
            title={s.prompt_suggere}
            className="px-3 py-1.5 rounded-full border border-yukpo-500/40 bg-yukpo-500/10 text-yukpo-200 text-xs font-medium hover:bg-yukpo-500/20 hover:border-yukpo-400 transition-colors"
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
};

const NavSuggestionButtons = ({ suggestions }: { suggestions: NavigationSuggestion[] }) => {
  const navigate = useNavigate();
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {suggestions.map((s) => (
        <button
          key={s.route}
          onClick={() => navigate(s.route)}
          title={s.description}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors"
          style={{
            background: "rgba(0,84,166,0.15)",
            borderColor: "rgba(0,176,240,0.35)",
            color: "#00B0F0",
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(0,84,166,0.3)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(0,84,166,0.15)"; }}
        >
          <span>→</span>
          {s.label}
        </button>
      ))}
    </div>
  );
};

const MessageBubble = ({
  message, onPickSuggestion,
}: {
  message: CopiloteMessage;
  onPickSuggestion?: (prompt: string) => void;
}) => {
  const isUser = message.role === "user";
  const proseRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation();

  const handleCopy = async () => {
    const raw = (message.content as string) || "";
    if (!raw) return;
    const html = proseRef.current?.innerHTML || "";
    try {
      if (html && typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/html": new Blob([html], { type: "text/html" }),
            "text/plain": new Blob([raw], { type: "text/plain" }),
          }),
        ]);
      } else {
        await navigator.clipboard.writeText(raw);
      }
      setCopied(true);
      toast.success(t("chat.messageCopied"));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      try {
        await navigator.clipboard.writeText(raw);
        setCopied(true);
        toast.success(t("chat.messageCopied"));
        setTimeout(() => setCopied(false), 2000);
      } catch {
        toast.error(t("chat.copyFailed"));
      }
    }
  };

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end"
      >
        <div className="max-w-[80%]">
          {message.fichiers && message.fichiers.length > 0 && (
            <div className="flex flex-wrap gap-1.5 justify-end mb-1.5">
              {message.fichiers.map((f, i) => (
                <span key={i} className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-700 text-slate-300 text-xs">
                  <Paperclip className="w-3 h-3" />
                  {f}
                </span>
              ))}
            </div>
          )}
          <div className="bg-yukpo-500/20 border border-yukpo-400/30 text-slate-100 rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
            {message.content as string}
          </div>
        </div>
      </motion.div>
    );
  }

  // Assistant
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3"
    >
      <div className="w-8 h-8 rounded-xl bg-yukpo-gradient flex items-center justify-center flex-shrink-0 mt-0.5">
        <Sparkles className="w-4 h-4 text-white" />
      </div>

      <div className="flex-1 min-w-0">
        {/* Badge agent utilisé */}
        {message.agent_utilise && (
          <div className="flex items-center gap-1.5 mb-1.5">
            <Bot className="w-3 h-3 text-yukpo-400" />
            <span className="text-xs text-yukpo-400 font-medium">{message.agent_utilise}</span>
          </div>
        )}

        {/* Contenu */}
        {message.loading ? (
          <div className="flex gap-1 items-center py-2">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className="w-2 h-2 rounded-full bg-slate-500 animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
        ) : (
          <div>
            <div ref={proseRef} className="prose prose-invert prose-sm max-w-none text-slate-200
              prose-headings:text-white prose-headings:font-semibold
              prose-strong:text-white prose-code:text-yukpo-300
              prose-pre:bg-slate-800 prose-pre:border prose-pre:border-slate-700
              prose-blockquote:border-yukpo-500 prose-blockquote:text-slate-300
              prose-a:text-yukpo-400 prose-li:text-slate-300">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // Renderer custom pour <a> : injection automatique du JWT
                  // sur les URLs auth-protégées Yukpo (téléchargements
                  // DOCX/PDF/MP4 servis par /api/v1/bureau/documents/* et
                  // /api/v1/pro/generateurs/fichier/*). Robuste aux vieux
                  // liens générés AVANT le déploiement du token-injection
                  // côté code : on intercepte au RENDU, pas à la création.
                  a: ({ href, children, ...rest }) => {
                    let finalHref = href || "";
                    try {
                      if (finalHref && !finalHref.includes("token=")) {
                        const needsAuth =
                          finalHref.includes("/api/v1/bureau/documents/")
                          || finalHref.includes("/api/v1/pro/generateurs/fichier/")
                          || finalHref.includes("/api/v1/bureau/video/fichier/")
                          || finalHref.includes("/api/v1/bureau/ocr/fichier/");
                        if (needsAuth) {
                          const tok = localStorage.getItem("yukpopro_token") || "";
                          if (tok) {
                            finalHref += (finalHref.includes("?") ? "&" : "?")
                              + "token=" + encodeURIComponent(tok);
                          }
                        }
                      }
                    } catch { /* fallback : on garde href brut */ }
                    return (
                      <a {...rest} href={finalHref} target="_blank" rel="noopener noreferrer">
                        {children}
                      </a>
                    );
                  },
                }}
              >{message.content as string}</ReactMarkdown>
            </div>
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={handleCopy}
                aria-label={t("chat.copyMessage")}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium bg-white hover:bg-slate-100 text-slate-700 hover:text-slate-900 border border-slate-300 shadow-sm"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? t("common.copied") : t("common.copy")}
              </button>
            </div>
          </div>
        )}

        {/* Fichiers générés — carte téléchargement proéminente */}
        {message.fichiers && message.fichiers.length > 0 && !message.loading && (
          <div className="mt-4 rounded-xl border-2 border-emerald-500/40 bg-gradient-to-br from-emerald-500/10 to-yukpo-500/10 p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                <Download className="w-4 h-4 text-emerald-300" />
              </div>
              <div>
                <div className="text-sm font-semibold text-emerald-100">
                  {message.fichiers.length === 1 ? "Document prêt à télécharger" : `${message.fichiers.length} documents prêts à télécharger`}
                </div>
                <div className="text-[11px] text-slate-400">Cliquez pour récupérer votre fichier — également disponible dans <a href="/mes-documents" className="underline hover:text-yukpo-300">Mes documents</a></div>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              {message.fichiers.map((f, i) => {
                const nomFichier = f.split(/[/\\]/).pop() || f;
                const ext = (nomFichier.split(".").pop() || "").toLowerCase();
                // Titre humain dérivé du filename technique :
                //   bureau_freeform_10_faire_part_1778601522.pdf
                //   → "Faire-part"
                //   bureau_designerpro_10_custom_libre_<ts>.pdf
                //   → "Designer Pro"
                //   rapport_analyse_standard_xxx_yyy_20260512_1140.docx
                //   → "Rapport — Xxx Yyy"
                const titreHumain = (() => {
                  let core = nomFichier.replace(/\.[a-z0-9]+$/i, "");
                  // strip leading 'bureau_<sous-module>_<userId>_'
                  core = core.replace(/^bureau_[a-z]+_\d+_/i, "");
                  // strip trailing '_<unix-ts>' ou '_<date>_<time>'
                  core = core.replace(/_\d{8,}(_\d{3,4})?$/i, "");
                  core = core.replace(/_cmyk$/i, "");
                  if (!core) return nomFichier;
                  // Smart capitalize : remplace _ par espace, première lettre majuscule
                  const mots = core.split(/[_-]+/).filter(Boolean);
                  if (mots.length === 0) return nomFichier;
                  // Acronymes courts (≤4 lettres) → tout en majuscules (MTN, ACME)
                  const titrise = mots.map((m, idx) => {
                    if (idx === 0) {
                      return m.charAt(0).toUpperCase() + m.slice(1);
                    }
                    if (m.length <= 4 && /^[a-z]+$/.test(m)) {
                      return m.toUpperCase();
                    }
                    return m;
                  }).join(" ");
                  // Correctifs lisibilité courants
                  return titrise
                    .replace(/^Faire Part/i, "Faire-part")
                    .replace(/^Carte Visite/i, "Carte de visite")
                    .replace(/^Cv Graphique/i, "CV graphique")
                    .replace(/^Post Social/i, "Post réseau social")
                    .replace(/^Marque Place/i, "Marque-place")
                    .replace(/Standard /i, "")
                    .replace(/Rapport Analyse/i, "Rapport d'analyse");
                })();
                const labelExt = ext === "docx" ? "Word"
                  : ext === "pptx" ? "PowerPoint"
                  : ext === "pdf" ? "PDF"
                  : ext === "xlsx" ? "Excel"
                  : ext === "mp4" ? "Vidéo MP4"
                  : ext === "png" ? "Image PNG"
                  : ext === "jpg" ? "Image JPG"
                  : ext.toUpperCase();
                const iconeExt = ext === "docx" ? "📄"
                  : ext === "pptx" ? "📊"
                  : ext === "pdf" ? "📕"
                  : ext === "xlsx" ? "📈"
                  : ext === "mp4" ? "🎞️"
                  : ext === "png" || ext === "jpg" ? "🖼️"
                  : "📎";
                // Détection automatique du bon endpoint backend selon le préfixe
                // du filename (les fichiers Bureau Freeform / Designer Pro / OCR /
                // Audio / Redaction / Slides Sec sont stockés sous /bureau/documents,
                // les rapports/slides Pro sous /pro/generateurs/fichier).
                // CRITIQUE : on suffixe ?token=JWT car un <a href> classique
                // fait un GET SANS header Authorization → 401. Le backend
                // get_current_user accepte token= en query (priorité 3 SSE-compat).
                // En prod, on pointe sur l'URL ABSOLUE backend Fly (les routes
                // /api/v1/* ne sont pas proxifiées par Netlify, cf. API_BASE_URL).
                const isBureauFile = /^bureau_/i.test(nomFichier);
                const _envBase = (typeof import.meta !== "undefined" &&
                  (import.meta as any).env?.VITE_API_URL) || null;
                const _isProd = typeof import.meta !== "undefined" &&
                  Boolean((import.meta as any).env?.PROD);
                const _apiBase = _envBase ||
                  (_isProd ? "https://yukpopro-backend.fly.dev/api/v1" : "/api/v1");
                const _path = isBureauFile
                  ? `/bureau/documents/${encodeURIComponent(nomFichier)}`
                  : `/pro/generateurs/fichier/${encodeURIComponent(nomFichier)}`;
                const _tok = localStorage.getItem("yukpopro_token") || "";
                const downloadUrl = _apiBase + _path + (_tok ? `?token=${encodeURIComponent(_tok)}` : "");
                return (
                  <div
                    key={i}
                    className="flex items-center gap-3 px-4 py-3 rounded-lg bg-slate-800/60 border border-emerald-500/30 hover:border-emerald-400/60 transition-colors"
                  >
                    <div className="text-2xl flex-shrink-0" aria-hidden>
                      {iconeExt}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold text-emerald-100 truncate" title={nomFichier}>
                        {titreHumain}
                      </div>
                      <div className="text-[11px] text-slate-400">
                        Format : {labelExt}
                      </div>
                    </div>
                    <a
                      href={downloadUrl}
                      download={nomFichier}
                      className="flex-shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
                    >
                      <Download className="w-4 h-4" />
                      <span>Télécharger</span>
                    </a>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Boutons de navigation vers les modules */}
        {message.navigation_suggestions && message.navigation_suggestions.length > 0 && !message.loading && (
          <NavSuggestionButtons suggestions={message.navigation_suggestions} />
        )}

        {/* Sprint G1 — Suggestions intelligentes post-génération (Haiku) */}
        {message.suggestions_suite && message.suggestions_suite.length > 0 && !message.loading && (
          <SuggestionsSuiteChips
            suggestions={message.suggestions_suite}
            onPick={(prompt) => onPickSuggestion?.(prompt)}
          />
        )}

        {/* Tokens consommés (transparent, discret — pas de montant) */}
        {message.cout_llm && !message.loading && (
          <div className="mt-2 flex items-center gap-2 text-[10px] text-slate-500">
            <span title={`Modèle : ${message.cout_llm.modele} · ${message.cout_llm.tokens_input} in + ${message.cout_llm.tokens_output} out`}>
              💡 {message.cout_llm.tokens_input + message.cout_llm.tokens_output} tokens
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
};

// ── Modale édition profil ──────────────────────────────────────────────────────

const NIVEAUX_EXPERTISE_KEYS = [
  { value: "debutant",      key: "expertiseDebutant" },
  { value: "intermediaire", key: "expertiseIntermediaire" },
  { value: "senior",        key: "expertiseSenior" },
  { value: "expert",        key: "expertiseExpert" },
] as const;

const ProfilModal = ({
  profil, onClose, onSaved,
}: {
  profil: any;
  onClose: () => void;
  onSaved: (updated: any) => void;
}) => {
  const { t } = useTranslation();
  const [metier, setMetier]     = useState(profil?.metier || "");
  const [pays, setPays]         = useState(profil?.pays || "CM");
  const [secteur, setSecteur]   = useState(profil?.secteur || "");
  const [entreprise, setEntreprise] = useState(profil?.entreprise || "");
  const [niveau, setNiveau]     = useState(profil?.niveau_expertise || "intermediaire");
  const [annees, setAnnees]     = useState(String(profil?.annees_experience || ""));
  const [bio, setBio]           = useState(profil?.bio || "");
  const [saving, setSaving]     = useState(false);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await profilApi.update({
        metier, pays, secteur, entreprise,
        niveau_expertise: niveau as any,
        annees_experience: annees ? parseInt(annees) : undefined,
        bio,
      });
      onSaved(updated);
    } catch {
      toast.error(t("chat.profileUpdateError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      {/* Overlay */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/60 z-40"
      />

      {/* Panel slide-over droite */}
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 28, stiffness: 300 }}
        className="fixed right-0 top-0 h-full w-full sm:max-w-md bg-slate-900 border-l border-slate-700 z-50 flex flex-col shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700 flex-shrink-0">
          <div className="flex items-center gap-2">
            <UserIcon className="w-4 h-4 text-yukpo-400" />
            <h2 className="text-white font-semibold text-sm">{t('chat.modalTitle')}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="px-5 py-3 text-xs text-slate-400 border-b border-slate-800 flex-shrink-0">
          {t('chat.modalDesc')}
        </p>

        {/* Formulaire */}
        <div className="flex-1 overflow-y-auto">
          <form id="profil-form" onSubmit={handleSave} className="p-5 space-y-4">
            {/* Métier */}
            <div>
              <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('chat.profession')}</label>
              <select
                value={metier}
                onChange={(e) => setMetier(e.target.value)}
                className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
              >
                <option value="">{t("chat.selectProfession")}</option>
                {METIERS.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>

            {/* Pays + Niveau */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.pays')}</label>
                <select
                  value={pays}
                  onChange={(e) => setPays(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                >
                  {PAYS_AFRIQUE.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.niveau')}</label>
                <select
                  value={niveau}
                  onChange={(e) => setNiveau(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                >
                  {NIVEAUX_EXPERTISE_KEYS.map((n) => (
                    <option key={n.value} value={n.value}>{t(`chat.${n.key}`)}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Secteur + Entreprise */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.secteur')}</label>
                <input
                  type="text"
                  value={secteur}
                  onChange={(e) => setSecteur(e.target.value)}
                  placeholder={t("chat.secteurPlaceholder")}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.entreprise')}</label>
                <input
                  type="text"
                  value={entreprise}
                  onChange={(e) => setEntreprise(e.target.value)}
                  placeholder={t("chat.entreprisePlaceholder")}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                />
              </div>
            </div>

            {/* Années d'expérience */}
            <div>
              <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.annees')}</label>
              <input
                type="number"
                min="0"
                max="50"
                value={annees}
                onChange={(e) => setAnnees(e.target.value)}
                placeholder={t("chat.anneesPlaceholder")}
                className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
              />
            </div>

            {/* Bio */}
            <div>
              <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.bio')}</label>
              <textarea
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                placeholder={t("chat.bioPlaceholder")}
                rows={3}
                className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-yukpo-500"
              />
            </div>
          </form>
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-slate-700 flex-shrink-0 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-600 text-slate-300 hover:text-white hover:border-slate-500 text-sm transition-colors"
          >
            {t('common.cancel')}
          </button>
          <button
            type="submit"
            form="profil-form"
            disabled={saving}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-yukpo-600 hover:bg-yukpo-500 text-white text-sm font-semibold transition-colors disabled:opacity-50"
          >
            {saving
              ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              : <Save className="w-4 h-4" />
            }
            {saving ? t('common.saving') : t('common.save')}
          </button>
        </div>
      </motion.div>
    </>
  );
};

// ── Helper lecture fichier ─────────────────────────────────────────────────────

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
