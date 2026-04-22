import { clsx } from 'clsx'
import { ReactNode } from 'react'

interface KPICardProps {
  title: string
  value: string | number
  subtitle?: string
  icon: ReactNode
  trend?: { value: number; label: string }
  color?: 'blue' | 'green' | 'orange' | 'purple'
  className?: string
}

const colorMap = {
  blue: {
    bg: 'bg-blue-50',
    icon: 'bg-primary-600 text-white',
    trend: 'text-primary-600',
  },
  green: {
    bg: 'bg-green-50',
    icon: 'bg-green-600 text-white',
    trend: 'text-green-600',
  },
  orange: {
    bg: 'bg-orange-50',
    icon: 'bg-orange-500 text-white',
    trend: 'text-orange-500',
  },
  purple: {
    bg: 'bg-purple-50',
    icon: 'bg-purple-600 text-white',
    trend: 'text-purple-600',
  },
}

export function KPICard({ title, value, subtitle, icon, trend, color = 'blue', className }: KPICardProps) {
  const colors = colorMap[color]

  return (
    <div
      className={clsx(
        'bg-white rounded-xl border border-gray-100 shadow-sm p-6 transition-shadow hover:shadow-md',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-500 mb-1">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
          {trend && (
            <p className={clsx('text-xs font-medium mt-2', colors.trend)}>
              {trend.value >= 0 ? '+' : ''}
              {trend.value}% {trend.label}
            </p>
          )}
        </div>
        <div className={clsx('flex items-center justify-center w-12 h-12 rounded-xl', colors.icon)}>
          {icon}
        </div>
      </div>
    </div>
  )
}
