/**
 * Popup — interface utilisateur Start/Stop.
 */

const $ = (id) => document.getElementById(id);

const tokenInput   = $("token");
const backendInput = $("backend");
const sourceSelect = $("source");
const targetSelect = $("target");
const btnStart     = $("btn-start");
const statusEl     = $("status");
const liveSubEl    = $("live-sub");

let actif = false;

// Charger config sauvegardée
chrome.storage.local.get(
  ["yt_token", "yt_backend", "yt_source", "yt_target"],
  (data) => {
    if (data.yt_token)   tokenInput.value   = data.yt_token;
    if (data.yt_backend) backendInput.value = data.yt_backend;
    if (data.yt_source)  sourceSelect.value = data.yt_source;
    if (data.yt_target)  targetSelect.value = data.yt_target;
    if (!backendInput.value) backendInput.value = "https://app.yukpoassurance.com";
  }
);

// État initial
chrome.runtime.sendMessage({ type: "YT_GET_STATE" }, (resp) => {
  if (resp?.etat?.actif) {
    actif = true;
    majBouton();
  }
});

btnStart.addEventListener("click", async () => {
  if (actif) {
    await chrome.runtime.sendMessage({ type: "YT_STOP_SESSION" });
    actif = false;
    liveSubEl.style.display = "none";
    setStatus("idle", "Arrêté");
    majBouton();
    return;
  }
  const config = {
    token: tokenInput.value.trim(),
    backend_url: backendInput.value.trim(),
    source: sourceSelect.value,
    target: targetSelect.value,
  };
  if (!config.token) {
    setStatus("error", "Token requis");
    return;
  }
  chrome.storage.local.set({
    yt_token: config.token,
    yt_backend: config.backend_url,
    yt_source: config.source,
    yt_target: config.target,
  });
  setStatus("idle", "Connexion…");
  btnStart.disabled = true;
  chrome.runtime.sendMessage({ type: "YT_START_SESSION", config }, (resp) => {
    btnStart.disabled = false;
    if (resp?.ok) {
      actif = true;
      liveSubEl.style.display = "block";
      liveSubEl.innerHTML = `<div class="src">🔴 En écoute…</div>`;
      setStatus("live", "🔴 Traduction en cours");
      majBouton();
    } else {
      setStatus("error", resp?.error || "Démarrage impossible");
    }
  });
});

// Relais events live depuis offscreen
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "YT_LIVE_EVENT") {
    const ev = msg.event;
    if (ev.type === "transcript" && ev.is_final) {
      liveSubEl.innerHTML = `<div class="src">[${ev.lang || "?"}] ${ev.text}</div>`;
    } else if (ev.type === "translation") {
      liveSubEl.innerHTML =
        `<div class="src">${ev.source_text}</div>` +
        `<div class="dst">→ ${ev.translated_text}</div>`;
    } else if (ev.type === "error") {
      setStatus("error", ev.message || ev.code);
    } else if (ev.type === "usage") {
      setStatus("live", `🔴 ${ev.minutes.toFixed(1)} min · ${Math.round(ev.credits_debited_total)} crédits`);
    }
  } else if (msg.type === "YT_SESSION_ENDED") {
    actif = false;
    setStatus("idle", "Session terminée");
    majBouton();
  }
});

function setStatus(kind, text) {
  statusEl.className = `status status-${kind}`;
  statusEl.textContent = text;
}

function majBouton() {
  if (actif) {
    btnStart.textContent = "Arrêter la traduction";
    btnStart.className = "btn-danger";
  } else {
    btnStart.textContent = "Démarrer la traduction";
    btnStart.className = "btn-primary";
  }
}
