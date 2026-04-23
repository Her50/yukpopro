import { ReactNode } from 'react'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export function EmptyState({ icon, title, description, action, className = '' }: EmptyStateProps) {
  return (
    <div
      role="status"
      className={`flex flex-col items-center justify-center text-center py-12 px-6 ${className}`}
    >
      <div className="text-slate-500 mb-3" aria-hidden="true">
        {icon}
      </div>
      <p className="text-sm font-semibold text-slate-200">{title}</p>
      {description && (
        <p className="text-xs text-slate-400 mt-1 max-w-sm">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
