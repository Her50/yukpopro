/**
 * MesLeadsPage — YukpoSecrétariat
 *
 * Wrapper qui monte <LeadsDashboard> de @yukpo/leads-dashboard.
 * Utilise httpRoot (baseURL /api/v1) car les endpoints leads sont sous
 * /api/v1/pro/landing-* (backend unifié yukpo_assurance).
 */
import { LeadsDashboard } from '@yukpo/leads-dashboard'
import { useTranslation } from 'react-i18next'
import { httpRoot } from '@/api/client'

export default function MesLeadsPage() {
  const { t } = useTranslation()
  return <LeadsDashboard http={httpRoot as any} t={t as any} />
}
