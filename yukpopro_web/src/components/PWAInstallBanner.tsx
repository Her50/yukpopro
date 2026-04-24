import { useState, useEffect } from 'react'
import { Download, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function PWAInstallBanner() {
  const { i18n } = useTranslation()
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [visible, setVisible] = useState(false)
  const [installing, setInstalling] = useState(false)

  useEffect(() => {
    // Ne pas afficher si déjà installé (standalone) ou si déjà refusé cette session
    if (window.matchMedia('(display-mode: standalone)').matches) return
    if (sessionStorage.getItem('pwa_banner_dismissed')) return

    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e as BeforeInstallPromptEvent)
      setVisible(true)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  const handleInstall = async () => {
    if (!deferredPrompt) return
    setInstalling(true)
    await deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    if (outcome === 'accepted') setVisible(false)
    setInstalling(false)
    setDeferredPrompt(null)
  }

  const handleDismiss = () => {
    sessionStorage.setItem('pwa_banner_dismissed', '1')
    setVisible(false)
  }

  if (!visible) return null

  const isRtl = i18n.dir() === 'rtl'

  return (
    <div
      dir={isRtl ? 'rtl' : 'ltr'}
      className="fixed top-0 left-0 right-0 z-[9999] flex items-center gap-3 px-4 py-3
        bg-gradient-to-r from-violet-700 to-purple-600 text-white shadow-lg
        animate-in slide-in-from-top duration-300"
    >
      <img src="/icons/icon-72x72.png" alt="YukpoPro" className="w-9 h-9 rounded-xl shrink-0" />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold leading-tight">Installer YukpoPro</p>
        <p className="text-xs text-purple-200 leading-tight mt-0.5 hidden sm:block">
          Accès rapide depuis l'écran d'accueil, fonctionne hors-ligne
        </p>
      </div>

      <button
        onClick={handleInstall}
        disabled={installing}
        className="flex items-center gap-1.5 bg-white text-purple-700 font-semibold text-xs
          px-3 py-1.5 rounded-lg shrink-0 hover:bg-purple-50 transition-colors disabled:opacity-60"
      >
        <Download size={13} />
        {installing ? 'Installation…' : 'Installer'}
      </button>

      <button
        onClick={handleDismiss}
        className="text-purple-200 hover:text-white transition-colors p-1 shrink-0"
        aria-label="Fermer"
      >
        <X size={16} />
      </button>
    </div>
  )
}
