/**
 * YukpoTranslate Live — Service worker (MV3).
 *
 * Orchestre le cycle de vie :
 *   popup → background : demande start
 *   background : tabCapture.getMediaStreamId(tab) + crée offscreen document
 *   offscreen : capture audio + ouvre WS → backend YukpoAssurance
 *   offscreen → background : relaie transcripts/translations
 *   background → content script : injecte overlay avec sous-titres
 */

const OFFSCREEN_PATH = "offscreen.html";
const OFFSCREEN_REASONS = ["USER_MEDIA", "AUDIO_PLAYBACK"];

let etatSession = {
  actif: false,
  tabId: null,
  config: null,
};

// ── Helpers ─────────────────────────────────────────────────────────────────

async function hasOffscreen() {
  if (!chrome.offscreen) return false;
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
  });
  return contexts.length > 0;
}

async function createOffscreen() {
  if (await hasOffscreen()) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_PATH,
    reasons: OFFSCREEN_REASONS,
    justification: "Audio capture via tabCapture pour streaming WebSocket de traduction temps réel.",
  });
}

async function closeOffscreen() {
  if (await hasOffscreen()) {
    try { await chrome.offscreen.closeDocument(); } catch { /* ignore */ }
  }
}

// ── Gestion des messages du popup / offscreen / content ────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case "YT_GET_STATE":
          sendResponse({ ok: true, etat: etatSession });
          break;

        case "YT_START_SESSION":
          await demarrerSession(msg.config);
          sendResponse({ ok: true });
          break;

        case "YT_STOP_SESSION":
          await arreterSession();
          sendResponse({ ok: true });
          break;

        case "YT_OFFSCREEN_EVENT":
          // Forward event from offscreen to content script on the captured tab
          if (etatSession.tabId) {
            try {
              await chrome.tabs.sendMessage(etatSession.tabId, {
                type: "YT_SUBTITLE_EVENT",
                event: msg.event,
              });
            } catch { /* tab may be closed */ }
          }
          // Forward to popup too
          try { chrome.runtime.sendMessage({ type: "YT_LIVE_EVENT", event: msg.event }); } catch {}
          sendResponse({ ok: true });
          break;

        case "YT_OFFSCREEN_CLOSED":
          etatSession.actif = false;
          try { chrome.runtime.sendMessage({ type: "YT_SESSION_ENDED" }); } catch {}
          sendResponse({ ok: true });
          break;

        default:
          sendResponse({ ok: false, error: "Unknown message type" });
      }
    } catch (err) {
      console.error("[YukpoTranslate] background error:", err);
      sendResponse({ ok: false, error: String(err?.message || err) });
    }
  })();
  return true; // async response
});

// ── Démarrage / Arrêt session ──────────────────────────────────────────────

async function demarrerSession(config) {
  const { token, source, target, backend_url } = config;
  if (!token) throw new Error("Token manquant. Connectez-vous sur YukpoPro d'abord.");

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("Aucun onglet actif.");

  const streamId = await new Promise((resolve, reject) => {
    chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id }, (id) => {
      if (chrome.runtime.lastError || !id) {
        reject(new Error(chrome.runtime.lastError?.message || "Capture audio refusée"));
      } else {
        resolve(id);
      }
    });
  });

  await createOffscreen();

  // Donne un court délai pour que l'offscreen document soit prêt à recevoir
  await new Promise((r) => setTimeout(r, 150));

  await chrome.runtime.sendMessage({
    type: "YT_OFFSCREEN_START",
    streamId,
    token,
    source: source || "auto",
    target: target || "fr",
    backend_url: backend_url || "wss://app.yukpoassurance.com",
  });

  etatSession = { actif: true, tabId: tab.id, config };

  // Injecte le content script si besoin
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch { /* déjà injecté ou page protégée */ }

  // Notifie le content script pour afficher l'overlay
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "YT_OVERLAY_SHOW", target });
  } catch { /* ignore */ }
}

async function arreterSession() {
  try { await chrome.runtime.sendMessage({ type: "YT_OFFSCREEN_STOP" }); } catch {}
  await closeOffscreen();
  if (etatSession.tabId) {
    try { await chrome.tabs.sendMessage(etatSession.tabId, { type: "YT_OVERLAY_HIDE" }); } catch {}
  }
  etatSession = { actif: false, tabId: null, config: null };
}

chrome.tabs.onRemoved.addListener((tabId) => {
  if (etatSession.tabId === tabId) {
    arreterSession().catch(() => {});
  }
});
