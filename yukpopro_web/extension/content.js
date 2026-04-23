/**
 * Content script — overlay sous-titres sur Zoom / Meet / YouTube / toute page.
 *
 * Reçoit les events du background (YT_SUBTITLE_EVENT) et affiche/met à jour
 * le bloc de sous-titres en bas de l'écran. Design minimal, sombre, drag-lock.
 */

(() => {
  if (window.__yukpoTranslateInjected) return;
  window.__yukpoTranslateInjected = true;

  let overlay = null;
  let originalEl = null;
  let translatedEl = null;
  let targetLang = "fr";

  const CSS = `
    .yt-overlay {
      position: fixed;
      left: 50%;
      bottom: 60px;
      transform: translateX(-50%);
      min-width: 320px;
      max-width: 85vw;
      z-index: 2147483647;
      background: rgba(17, 24, 39, 0.92);
      color: #F3F4F6;
      border-radius: 12px;
      padding: 14px 18px;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      font-size: 18px;
      line-height: 1.4;
      box-shadow: 0 10px 40px rgba(0,0,0,0.5);
      border: 1px solid rgba(139, 92, 246, 0.4);
      backdrop-filter: blur(10px);
      pointer-events: auto;
      user-select: text;
    }
    .yt-overlay-hidden { display: none !important; }
    .yt-row { display: flex; align-items: flex-start; gap: 10px; margin-top: 4px; }
    .yt-badge {
      flex-shrink: 0;
      font-size: 10px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 6px;
      background: rgba(139, 92, 246, 0.25);
      color: #C4B5FD;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-top: 2px;
    }
    .yt-badge-src { background: rgba(107, 114, 128, 0.3); color: #D1D5DB; }
    .yt-text { flex: 1; }
    .yt-text-src { color: #D1D5DB; font-size: 15px; opacity: 0.85; }
    .yt-text-dst { color: #E9D5FF; font-weight: 500; }
    .yt-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: #9CA3AF;
      margin-bottom: 4px;
    }
    .yt-close {
      cursor: pointer;
      background: none;
      border: none;
      color: #9CA3AF;
      font-size: 16px;
      padding: 0 4px;
    }
    .yt-close:hover { color: #F3F4F6; }
  `;

  function creerOverlay(target) {
    targetLang = target || "fr";
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);

    overlay = document.createElement("div");
    overlay.className = "yt-overlay";
    overlay.innerHTML = `
      <div class="yt-header">
        <span>🔴 YukpoTranslate Live — ${targetLang.toUpperCase()}</span>
        <button class="yt-close" title="Masquer">✕</button>
      </div>
      <div class="yt-row">
        <span class="yt-badge yt-badge-src" data-role="src-lang">···</span>
        <div class="yt-text yt-text-src" data-role="src-text">En attente de parole…</div>
      </div>
      <div class="yt-row">
        <span class="yt-badge" data-role="dst-lang">${targetLang.toUpperCase()}</span>
        <div class="yt-text yt-text-dst" data-role="dst-text">—</div>
      </div>
    `;
    document.body.appendChild(overlay);
    originalEl = overlay.querySelector('[data-role="src-text"]');
    translatedEl = overlay.querySelector('[data-role="dst-text"]');
    overlay.querySelector(".yt-close").addEventListener("click", () => masquerOverlay());

    // Drag
    let drag = null;
    overlay.querySelector(".yt-header").addEventListener("mousedown", (e) => {
      const r = overlay.getBoundingClientRect();
      drag = { dx: e.clientX - r.left, dy: e.clientY - r.top };
      e.preventDefault();
    });
    document.addEventListener("mousemove", (e) => {
      if (!drag || !overlay) return;
      overlay.style.left = `${e.clientX - drag.dx}px`;
      overlay.style.top = `${e.clientY - drag.dy}px`;
      overlay.style.bottom = "auto";
      overlay.style.transform = "none";
    });
    document.addEventListener("mouseup", () => { drag = null; });
  }

  function masquerOverlay() {
    if (overlay) overlay.classList.add("yt-overlay-hidden");
  }

  function supprimerOverlay() {
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    overlay = null;
    originalEl = null;
    translatedEl = null;
  }

  function appliquerEvent(event) {
    if (!overlay) return;
    if (event.type === "transcript") {
      if (originalEl) originalEl.textContent = event.text || "…";
      const srcLangEl = overlay.querySelector('[data-role="src-lang"]');
      if (srcLangEl) srcLangEl.textContent = (event.lang || "").toUpperCase() || "···";
    } else if (event.type === "translation") {
      if (translatedEl) translatedEl.textContent = event.translated_text || "—";
      if (originalEl) originalEl.textContent = event.source_text || originalEl.textContent;
    } else if (event.type === "error") {
      if (translatedEl) translatedEl.textContent = `⚠ ${event.message || event.code}`;
    }
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "YT_OVERLAY_SHOW") {
      if (!overlay) creerOverlay(msg.target);
      else overlay.classList.remove("yt-overlay-hidden");
    } else if (msg.type === "YT_OVERLAY_HIDE") {
      supprimerOverlay();
    } else if (msg.type === "YT_SUBTITLE_EVENT") {
      appliquerEvent(msg.event);
    }
  });
})();
