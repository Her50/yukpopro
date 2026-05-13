/**
 * PublierLandingPage — YukpoSecrétariat
 *
 * Page dédiée pour publier une landing déjà générée (lien depuis le chat).
 */
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import { PublierLandingButton } from '@yukpo/leads-dashboard'
import { landingPageAPI } from '@/api/client'

export default function PublierLandingPage() {
  const { t } = useTranslation()
  const { fichierId } = useParams<{ fichierId: string }>()

  if (!fichierId) {
    return <div className="p-6 text-center text-rose-700">fichier_id manquant.</div>
  }

  const publier = async (req: any) => {
    const { data } = await landingPageAPI.publier(req)
    return data
  }

  return (
    <div className="p-4 md:p-6 max-w-2xl mx-auto">
      <Link to="/chat" className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 mb-4">
        <ArrowLeft className="w-4 h-4" />
        {t('commun.retour_chat', 'Retour au chat')}
      </Link>
      <h1 className="text-2xl md:text-3xl font-bold mb-2">
        {t('landing.publier.page_titre', 'Publier votre landing')}
      </h1>
      <p className="text-sm text-slate-600 mb-6">
        {t('landing.publier.page_sous_titre',
           'Choisissez un sous-domaine custom et déployez en un clic sur Netlify.')}
      </p>
      <PublierLandingButton
        fichierId={fichierId}
        publier={publier}
        plan="free"
        t={t as any}
        variant="full"
      />
    </div>
  )
}
