import { useTranslation } from 'react-i18next'
import { Sparkles } from 'lucide-react'

export interface Suggestion {
  action?: string
  label: string
  prompt_suggere: string
}

export default function SuggestionsChips({
  suggestions, onPick,
}: {
  suggestions: Suggestion[] | undefined
  onPick: (prompt: string) => void
}) {
  const { t } = useTranslation()
  if (!suggestions || suggestions.length === 0) return null
  const list = suggestions.slice(0, 5)
  return (
    <div className="border-t border-gray-100 pt-3 mt-3">
      <p className="text-[11px] text-gray-500 font-semibold mb-1.5 flex items-center gap-1">
        <Sparkles size={11} className="text-violet-500" />
        {t('chatUnifie.suggestionsLabel', 'Suggestions')}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {list.map((s, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onPick(s.prompt_suggere)}
            title={s.prompt_suggere}
            className="rounded-full bg-gray-100 hover:bg-violet-100 hover:text-violet-700 text-gray-700 text-xs px-3 py-1.5 transition-colors max-w-full truncate"
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )
}
