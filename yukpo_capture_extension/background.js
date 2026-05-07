/**
 * Yukpo Capture — Service Worker (Manifest V3)
 *
 * Coordonne la capture audio des onglets de réunion :
 *  - Reçoit "start" / "stop" depuis le popup
 *  - Crée un offscreen document (recording.html) qui fait le MediaRecorder
 *    (le service worker MV3 ne peut pas tenir de MediaStream)
 *  - Récupère le blob, l'upload vers Yukpo Pro
 */

const OFFSCREEN_URL = chrome.runtime.getURL("offscreen.html");

const DOMAIN_LABELS = {
  "teams.microsoft.com": "Microsoft Teams",
  "teams.live.com":      "Microsoft Teams",
  "meet.google.com":     "Google Meet",
  "zoom.us":             "Zoom",
  "zoom.com":            "Zoom",
  "webex.com":           "Webex",
};

function detectMeetingPlatform(url) {
  if (!url) return null;
  for (const [host, label] of Object.entries(DOMAIN_LABELS)) {
    if (url.includes(host)) return label;
  }
  return null;
}

async function ensureOffscreen() {
  const existing = await chrome.offscreen.hasDocument().catch(() => false);
  if (existing) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ["USER_MEDIA"],
    justification: "Capture audio des réunions Teams/Meet/Zoom pour transcription Yukpo.",
  });
}

async function startCapture(tabId, alsoMic) {
  await ensureOffscreen();
  // Récupère un streamId qui sera consommé côté offscreen via getUserMedia
  const streamId = await new Promise((resolve, reject) => {
    chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, (id) => {
      if (chrome.runtime.lastError || !id) {
        reject(new Error(chrome.runtime.lastError?.message || "Impossible d'obtenir le streamId"));
      } else {
        resolve(id);
      }
    });
  });
  await chrome.runtime.sendMessage({
    type: "OFFSCREEN_START",
    streamId, alsoMic,
  });
  await chrome.storage.session.set({ recording: true, recordingTabId: tabId });
  await chrome.action.setBadgeText({ text: "REC" });
  await chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
}

async function stopCapture() {
  await chrome.runtime.sendMessage({ type: "OFFSCREEN_STOP" });
  await chrome.action.setBadgeText({ text: "" });
}

async function uploadToYukpo(blob, langue, baseUrl, token) {
  const fd = new FormData();
  const filename = `yukpo-capture-${Date.now()}.webm`;
  fd.append("fichier", blob, filename);
  fd.append("langue", langue || "auto");
  const url = `${baseUrl.replace(/\/+$/, "")}/api/v1/pro/reunions/importer-replay`;
  const r = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(data.detail || `HTTP ${r.status}`);
  }
  return data;
}

// ── Messages ──────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "DETECT_PLATFORM") {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        const tab = tabs[0];
        sendResponse({
          tab: tab ? { id: tab.id, url: tab.url, title: tab.title } : null,
          platform: detectMeetingPlatform(tab?.url),
        });
        return;
      }
      if (msg.type === "START_RECORDING") {
        await startCapture(msg.tabId, !!msg.alsoMic);
        sendResponse({ ok: true });
        return;
      }
      if (msg.type === "STOP_RECORDING") {
        await stopCapture();
        sendResponse({ ok: true });
        return;
      }
      if (msg.type === "UPLOAD_BLOB") {
        const cfg = await chrome.storage.local.get(["yukpoBaseUrl", "yukpoToken", "yukpoLangue"]);
        const baseUrl = cfg.yukpoBaseUrl || "https://yukpopro-backend.fly.dev";
        if (!cfg.yukpoToken) {
          throw new Error("Token Yukpo manquant — connectez-vous d'abord depuis le popup");
        }
        // Le blob arrive en base64 ; on le reconvertit
        const bin = atob(msg.dataB64);
        const arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        const blob = new Blob([arr], { type: msg.mime || "audio/webm" });
        const data = await uploadToYukpo(blob, cfg.yukpoLangue || "auto", baseUrl, cfg.yukpoToken);
        await chrome.notifications.create({
          type: "basic",
          iconUrl: "icons/icon-128.png",
          title: "Yukpo — Transcription terminée",
          message: `Replay transcrit (${data.longueur || 0} caractères). Ouvrez Réunions sur Yukpo Pro pour générer le PV.`,
        });
        sendResponse({ ok: true, data });
        return;
      }
      if (msg.type === "OFFSCREEN_RECORDED") {
        // Reroute vers UPLOAD_BLOB
        const r = await chrome.runtime.sendMessage({
          type: "UPLOAD_BLOB", dataB64: msg.dataB64, mime: msg.mime,
        });
        sendResponse(r);
        return;
      }
      sendResponse({ ok: false, error: "Type inconnu" });
    } catch (e) {
      console.error("[YukpoCapture] background error:", e);
      sendResponse({ ok: false, error: e.message || String(e) });
    }
  })();
  return true; // async sendResponse
});

// Action click sans popup → ouvre le popup (Manifest V3 le gère via default_popup)
chrome.runtime.onInstalled.addListener(() => {
  chrome.action.setBadgeText({ text: "" });
});
