import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Search, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { LANGUAGES, findLanguage } from '../data/languages'
import { normalize } from '../data/countries'

interface Props {
  value: string
  onChange: (code: string) => void
  label?: string
  className?: string
}

export function LanguagePicker({ value, onChange, label, className }: Props) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Noms de langues localisés via Intl.DisplayNames.
  const displayNames = useMemo(() => {
    try { return new Intl.DisplayNames([i18n.language], { type: 'language' }) }
    catch { return null }
  }, [i18n.language])
  const localized = (code: string, fallback: string): string =>
    displayNames?.of(code) || fallback

  const selectedRaw = findLanguage(value) || LANGUAGES.find((l) => l.code === 'fr') || LANGUAGES[0]
  const selected = { ...selectedRaw, name: localized(selectedRaw.code, selectedRaw.name) }

  const results = useMemo(() => {
    const n = normalize(query.trim())
    const items = LANGUAGES.map(l => ({ ...l, name: localized(l.code, l.name) }))
    if (!n) return items.slice(0, 100)
    return items.filter(l =>
      normalize(l.name).includes(n) || normalize(l.native).includes(n) || l.code.toLowerCase().includes(n),
    ).slice(0, 100)
  }, [query, displayNames])

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 10)
    else setQuery('')
  }, [open])

  return (
    <div className={className}>
      {label && <label className="block text-sm font-semibold text-gray-700 mb-2">{label}</label>}
      <div ref={wrapRef} className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-center justify-between gap-2 border border-gray-300 rounded-xl px-4 py-2.5 text-sm bg-white hover:border-orange-400 focus:outline-none focus:ring-2 focus:ring-orange-400"
        >
          <span className="text-gray-800 truncate">{selected.name} <span className="text-gray-400">({selected.native})</span></span>
          <ChevronDown size={16} className={`text-gray-400 transition-transform shrink-0 ${open ? 'rotate-180' : ''}`} />
        </button>

        {open && (
          <div className="absolute z-30 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100">
              <Search size={14} className="text-gray-400" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('common.searchLanguage')}
                className="flex-1 text-sm outline-none bg-transparent"
              />
            </div>
            <ul className="max-h-64 overflow-y-auto py-1" role="listbox">
              {results.length === 0 && (
                <li className="px-3 py-2 text-xs text-gray-400">{t('common.noResults')}</li>
              )}
              {results.map((l) => (
                <li key={l.code}>
                  <button
                    type="button"
                    onClick={() => { onChange(l.code); setOpen(false) }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-orange-50 ${l.code === value ? 'bg-orange-50/50' : ''}`}
                  >
                    <span className="flex-1 text-left text-gray-800">{l.name} <span className="text-gray-400">({l.native})</span></span>
                    {l.code === value && <Check size={14} className="text-orange-500" />}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
