/**
 * Yukpo Capture — content script
 * Injecté sur les pages Teams / Meet / Zoom / Webex.
 * Affiche un petit badge flottant pour rappeler à l'utilisateur qu'il peut
 * lancer la capture depuis l'icône d'extension.
 */
(() => {
  if (window.__yukpoCaptureInjected) return;
  window.__yukpoCaptureInjected = true;

  const badge = document.createElement("div");
  badge.id = "__yukpo-capture-badge";
  badge.innerHTML = "🎙 Yukpo Capture prêt — clic sur l'icône d'extension pour démarrer";
  badge.style.cssText = `
    position: fixed; bottom: 20px; right: 20px;
    background: linear-gradient(135deg, #8b5cf6, #3b82f6);
    color: white; font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
    font-size: 12px; font-weight: 500;
    padding: 8px 14px; border-radius: 20px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    z-index: 2147483647; cursor: default;
    opacity: 0.92; pointer-events: none;
    transition: opacity 0.4s;
  `;
  // Affiché 6s puis fade
  document.body && document.body.appendChild(badge);
  setTimeout(() => {
    badge.style.opacity = "0";
    setTimeout(() => badge.remove(), 800);
  }, 6000);
})();
