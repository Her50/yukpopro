/**
 * TrackingSettingsPage — YukpoSecrétariat
 * Wrapper du panneau partagé.
 */
import { TrackingSettingsPanel } from '@yukpo/leads-dashboard'
import { useTranslation } from 'react-i18next'
import { httpRoot } from '@/api/client'

export default function TrackingSettingsPage() {
  const { t } = useTranslation()
  return <TrackingSettingsPanel http={httpRoot as any} t={t as any} />
}
