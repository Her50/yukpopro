/**
 * Yukpo Capture — Offscreen document
 * Tient le MediaStream et le MediaRecorder (ce que le service worker MV3 ne peut pas).
 */

let mediaRecorder = null;
let audioChunks = [];
let tabStream = null;
let micStream = null;
let mixedStream = null;
let audioCtx = null;

async function startRecording(streamId, alsoMic) {
  // 1. Audio de l'onglet (réunion)
  tabStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
    video: false,
  });

  // 2. Mic local optionnel
  if (alsoMic) {
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: false,
      });
    } catch (e) {
      console.warn("[YukpoCapture] Pas d'accès micro :", e);
    }
  }

  // 3. Mixer si on a les 2 sources, sinon utiliser celle disponible
  audioCtx = new AudioContext();
  const dest = audioCtx.createMediaStreamDestination();
  audioCtx.createMediaStreamSource(tabStream).connect(dest);
  if (micStream) {
    audioCtx.createMediaStreamSource(micStream).connect(dest);
  }
  mixedStream = dest.stream;

  // 4. Re-router l'audio de l'onglet vers les haut-parleurs (sinon mute pour l'utilisateur)
  const playback = new Audio();
  playback.srcObject = tabStream;
  playback.play().catch(() => {});

  // 5. MediaRecorder en WebM/Opus (compatible Whisper)
  audioChunks = [];
  mediaRecorder = new MediaRecorder(mixedStream, {
    mimeType: "audio/webm;codecs=opus",
    audioBitsPerSecond: 96000,
  });
  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) audioChunks.push(e.data);
  };
  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, { type: "audio/webm" });
    audioChunks = [];
    const buf = await blob.arrayBuffer();
    const u8 = new Uint8Array(buf);
    let bin = "";
    // Encode base64 par chunks pour éviter stack overflow sur gros fichiers
    const CHUNK = 0x8000;
    for (let i = 0; i < u8.length; i += CHUNK) {
      bin += String.fromCharCode.apply(null, u8.subarray(i, i + CHUNK));
    }
    const dataB64 = btoa(bin);
    chrome.runtime.sendMessage({
      type: "OFFSCREEN_RECORDED", dataB64, mime: "audio/webm",
    });
    cleanup();
  };
  mediaRecorder.start(2000); // chunks de 2s
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
}

function cleanup() {
  [tabStream, micStream, mixedStream].forEach(s => {
    s?.getTracks().forEach(t => t.stop());
  });
  tabStream = null; micStream = null; mixedStream = null;
  audioCtx?.close().catch(() => {});
  audioCtx = null;
  mediaRecorder = null;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "OFFSCREEN_START") {
        await startRecording(msg.streamId, !!msg.alsoMic);
        sendResponse({ ok: true });
      } else if (msg.type === "OFFSCREEN_STOP") {
        stopRecording();
        sendResponse({ ok: true });
      }
    } catch (e) {
      console.error("[YukpoCapture/offscreen]", e);
      cleanup();
      sendResponse({ ok: false, error: e.message || String(e) });
    }
  })();
  return true;
});
