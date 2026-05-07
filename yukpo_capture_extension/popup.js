/**
 * Yukpo Capture — popup logic
 */

const $ = (id) => document.getElementById(id);

function setStatus(msg, type = "") {
  const el = $("status");
  el.textContent = msg || "";
  el.className = "status " + (type || "");
}

async function loadConfig() {
  const cfg = await chrome.storage.local.get(["yukpoToken", "yukpoBaseUrl", "yukpoLangue"]);
  $("cfg-token").value = cfg.yukpoToken || "";
  $("cfg-url").value = cfg.yukpoBaseUrl || "https://yukpopro-backend.fly.dev";
  $("cfg-langue").value = cfg.yukpoLangue || "auto";
}

async function saveConfig() {
  const token = $("cfg-token").value.trim();
  const baseUrl = $("cfg-url").value.trim() || "https://yukpopro-backend.fly.dev";
  const langue = $("cfg-langue").value;
  await chrome.storage.local.set({
    yukpoToken: token, yukpoBaseUrl: baseUrl, yukpoLangue: langue,
  });
  setStatus("Configuration enregistrée", "ok");
}

async function detectPlatform() {
  const r = await chrome.runtime.sendMessage({ type: "DETECT_PLATFORM" });
  const el = $("platform");
  if (r?.platform && r?.tab) {
    el.className = "platform detected";
    el.textContent = `Réunion détectée : ${r.platform}`;
    return r.tab;
  }
  el.className = "platform none";
  el.textContent = "Aucune réunion détectée — ouvrez Teams / Meet / Zoom dans cet onglet, puis cliquez sur l'extension.";
  return null;
}

async function refreshRecordingState() {
  const { recording } = await chrome.storage.session.get("recording");
  $("btn-start").style.display = recording ? "none" : "block";
  $("btn-stop").style.display  = recording ? "block" : "none";
  $("recording-info").style.display = recording ? "block" : "none";
}

async function start() {
  setStatus("Préparation…");
  const tab = await detectPlatform();
  const cfg = await chrome.storage.local.get(["yukpoToken"]);
  if (!cfg.yukpoToken) {
    setStatus("⚠️ Configurez votre token Yukpo dans Configuration", "err");
    return;
  }
  if (!tab) {
    setStatus("Aucune réunion détectée", "err");
    return;
  }
  const alsoMic = $("also-mic").checked;
  const r = await chrome.runtime.sendMessage({
    type: "START_RECORDING", tabId: tab.id, alsoMic,
  });
  if (!r?.ok) {
    setStatus("Erreur : " + (r?.error || "inconnue"), "err");
    return;
  }
  setStatus("Enregistrement…", "ok");
  refreshRecordingState();
}

async function stop() {
  setStatus("Finalisation et envoi à Yukpo…");
  const r = await chrome.runtime.sendMessage({ type: "STOP_RECORDING" });
  if (!r?.ok) {
    setStatus("Erreur arrêt : " + (r?.error || "inconnue"), "err");
    return;
  }
  setStatus("Audio envoyé — transcription en cours côté Yukpo. Notification à venir.", "ok");
  // refresh dans 1s pour laisser le offscreen flusher
  setTimeout(refreshRecordingState, 1500);
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadConfig();
  await detectPlatform();
  await refreshRecordingState();
});

$("btn-start").addEventListener("click", start);
$("btn-stop").addEventListener("click", stop);
$("btn-save-cfg").addEventListener("click", saveConfig);
