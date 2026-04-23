import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'

interface DemoBannerProps {
  message?: string
  className?: string
}

export function DemoBanner({ message, className = '' }: DemoBannerProps) {
  return (
    <div
      role="status"
      className={`flex items-center gap-2 px-4 py-2 rounded-lg border border-amber-200 bg-amber-50 text-amber-800 text-xs ${className}`}
    >
      <ExclamationTriangleIcon className="h-4 w-4 flex-shrink-0 text-amber-500" />
      <span>
        {message ?? 'Données de démonstration — connectez votre source de données pour voir vos indicateurs réels.'}
      </span>
    </div>
  )
}
