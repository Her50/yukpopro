/**
 * Empêche l'écran de s'éteindre pendant un enregistrement audio long.
 *
 * - Chrome/Edge desktop + Android : Wake Lock API (officielle)
 * - Safari iOS, Firefox, Safari macOS : pas supporté → graceful no-op
 *   (l'utilisateur doit garder l'écran allumé manuellement)
 *
 * Le navigateur libère automatiquement le lock si l'onglet passe en
 * arrière-plan, donc il faut le réacquérir au retour. La fonction
 * `acquireWakeLock` gère ça via un listener visibilitychange.
 */

type Sentinel = { release: () => Promise<void> } | null

let sentinel: Sentinel = null
let visibilityHandlerInstalled = false

async function tryRequest(): Promise<Sentinel> {
  try {
    const wl = (navigator as Navigator & {
      wakeLock?: { request: (type: 'screen') => Promise<Sentinel> }
    }).wakeLock
    if (!wl) return null
    return await wl.request('screen')
  } catch {
    // user denied / not allowed in iframe / etc.
    return null
  }
}

/** Active le wake lock. Re-acquiert automatiquement si l'onglet revient au 1er plan. */
export async function acquireWakeLock(): Promise<boolean> {
  sentinel = await tryRequest()

  if (!visibilityHandlerInstalled) {
    document.addEventListener('visibilitychange', async () => {
      if (sentinel === null) return // pas actif → on n'essaie pas de réacquérir
      if (document.visibilityState === 'visible') {
        sentinel = await tryRequest()
      }
    })
    visibilityHandlerInstalled = true
  }

  return sentinel !== null
}

/** Libère le wake lock si actif. */
export async function releaseWakeLock(): Promise<void> {
  try {
    await sentinel?.release()
  } catch {
    /* déjà libéré */
  }
  sentinel = null
}

/** True si l'API est disponible sur ce navigateur (utile pour afficher un hint). */
export function wakeLockSupported(): boolean {
  return typeof navigator !== 'undefined' && 'wakeLock' in navigator
}
