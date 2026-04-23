/**
 * Offscreen document — capture audio de l'onglet + WebSocket vers backend.
 *
 * Pourquoi offscreen ? Les Service Workers MV3 ne peuvent pas utiliser
 * AudioContext ni MediaStream. Chrome fournit un document persistant pour ça.
 */

let ws = null;
let audioCtx = null;
let mediaStream = null;
let workletNode = null;

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "YT_OFFSCREEN_START") {
        await demarrer(msg);
        sendResponse({ ok: true });
      } else if (msg.type === "YT_OFFSCREEN_STOP") {
        await arreter();
        sendResponse({ ok: true });
      }
    } catch (err) {
      console.error("[YukpoOffscreen]", err);
      forwardEvent({ type: "error", code: "offscreen_error", message: String(err?.message || err) });
      sendResponse({ ok: false, error: String(err?.message || err) });
    }
  })();
  return true;
});

async function demarrer({ streamId, token, source, target, backend_url }) {
  // 1. Acquisition du MediaStream via tabCapture streamId
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
    video: false,
  });

  // 2. WebSocket vers le backend YukpoAssurance
  const wsUrl = toWsUrl(backend_url) +
    `/api/v1/translate/live/ws?token=${encodeURIComponent(token)}` +
    `&source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`;
  ws = new WebSocket(wsUrl);
  ws.binaryType = "arraybuffer";

  ws.onmessage = (ev) => {
    if (typeof ev.data !== "string") return;
    try {
      const obj = JSON.parse(ev.data);
      forwardEvent(obj);
    } catch { /* ignore */ }
  };
  ws.onerror = () => {
    forwardEvent({ type: "error", code: "ws_error", message: "Erreur WebSocket" });
  };
  ws.onclose = (ev) => {
    forwardEvent({ type: "error", code: "ws_closed", message: `Connexion fermée (${ev.code})` });
    try { chrome.runtime.sendMessage({ type: "YT_OFFSCREEN_CLOSED" }); } catch {}
  };

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("WebSocket timeout")), 10_000);
    ws.onopen = () => {
      clearTimeout(timer);
      resolve();
    };
  });

  // 3. Rejoue l'audio local pour que l'utilisateur entende toujours l'onglet
  const audioOut = new AudioContext();
  const srcOut = audioOut.createMediaStreamSource(mediaStream);
  srcOut.connect(audioOut.destination);

  // 4. Pipeline PCM16 16 kHz → WebSocket
  audioCtx = new AudioContext();
  await audioCtx.audioWorklet.addModule(chrome.runtime.getURL("pcm-worklet.js"));

  const source2 = audioCtx.createMediaStreamSource(mediaStream);
  workletNode = new AudioWorkletNode(audioCtx, "pcm-worklet");
  workletNode.port.onmessage = (ev) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try { ws.send(ev.data); } catch { /* ignore */ }
  };
  source2.connect(workletNode);
}

async function arreter() {
  if (workletNode) { try { workletNode.disconnect(); } catch {} workletNode = null; }
  if (audioCtx) { try { await audioCtx.close(); } catch {} audioCtx = null; }
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
  if (ws) {
    try { ws.send(JSON.stringify({ type: "stop" })); } catch {}
    try { ws.close(1000, "user stop"); } catch {}
    ws = null;
  }
}

function toWsUrl(url) {
  if (!url) return "wss://app.yukpoassurance.com";
  return url.replace(/^http:/i, "ws:").replace(/^https:/i, "wss:").replace(/\/$/, "");
}

function forwardEvent(event) {
  try {
    chrome.runtime.sendMessage({ type: "YT_OFFSCREEN_EVENT", event });
  } catch { /* ignore */ }
}
