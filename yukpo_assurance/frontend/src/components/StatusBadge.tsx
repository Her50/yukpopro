import { clsx } from 'clsx'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

interface StatusBadgeProps {
  variant: BadgeVariant
  label: string
  className?: string
}

const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-green-100 text-green-800 ring-green-600/20',
  warning: 'bg-yellow-100 text-yellow-800 ring-yellow-600/20',
  danger: 'bg-red-100 text-red-800 ring-red-600/20',
  info: 'bg-blue-100 text-blue-800 ring-blue-600/20',
  neutral: 'bg-gray-100 text-gray-700 ring-gray-500/20',
}

export function StatusBadge({ variant, label, className }: StatusBadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset',
        variantStyles[variant],
        className
      )}
    >
      {label}
    </span>
  )
}

export function FraudeBadge({ score }: { score: number }) {
  if (score < 30) return <StatusBadge variant="success" label={`${score}% — Faible`} />
  if (score < 60) return <StatusBadge variant="warning" label={`${score}% — Moyen`} />
  return <StatusBadge variant="danger" label={`${score}% — Élevé`} />
}

export function statutToVariant(statut: string): BadgeVariant {
  const map: Record<string, BadgeVariant> = {
    ouvert: 'info',
    en_cours: 'warning',
    clos: 'success',
    rejet: 'danger',
    actif: 'success',
    inactif: 'neutral',
    conge: 'warning',
    lead: 'neutral',
    contact: 'info',
    proposition: 'warning',
    negociation: 'warning',
    gagne: 'success',
    perdu: 'danger',
    en_attente: 'warning',
    accepte: 'success',
    refuse: 'danger',
  }
  return map[statut] || 'neutral'
}
