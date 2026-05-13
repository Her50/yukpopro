import { lazy, type ComponentType, type LazyExoticComponent } from "react";

/**
 * Wrapper autour de React.lazy qui détecte les ChunkLoadError (typique après
 * un déploiement où les anciens chunks hash X ont disparu du CDN mais le SW
 * a précaché l'ancien index.html qui les référence).
 *
 * Stratégie :
 *  1. 1er échec d'import : marque dans sessionStorage + force window.location.reload()
 *     pour récupérer le nouveau index.html (avec les nouveaux hash de chunks).
 *  2. Si l'échec se reproduit après reload : c'est une VRAIE erreur (réseau
 *     coupé, bug build), on laisse propager normalement → Suspense restera
 *     sur fallback, mais on évite la boucle infinie de reload.
 *  3. Au montage réussi du composant racine, on clear le marker (cf App.tsx).
 */
const RELOAD_KEY = "ykp-chunk-reload-attempt";

export function lazyWithRetry<T extends ComponentType<unknown>>(
  importFn: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  return lazy(async () => {
    try {
      return await importFn();
    } catch (err) {
      const alreadyTried = sessionStorage.getItem(RELOAD_KEY);
      if (!alreadyTried) {
        sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
        // Reload force re-fetch de index.html → nouveau manifest → nouveaux
        // chunks. La Promise ne resolved jamais ici car la page se recharge.
        window.location.reload();
        return new Promise<{ default: T }>(() => {});
      }
      // Retry déjà fait → vraie erreur, propage
      throw err;
    }
  });
}

/** À appeler au montage de l'App racine pour clear le marker une fois que
 *  l'app a démarré avec succès. */
export function clearChunkReloadMarker(): void {
  try {
    sessionStorage.removeItem(RELOAD_KEY);
  } catch {
    /* sessionStorage indispo (mode incognito strict) — non bloquant */
  }
}
