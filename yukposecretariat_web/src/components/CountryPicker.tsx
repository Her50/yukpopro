import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Search, Check } from 'lucide-react'
import { COUNTRIES, findCountry, searchCountries } from '../data/countries'

interface Props {
  value: string
  onChange: (code: string) => void
  label?: string
  className?: string
}

export function CountryPicker({ value, onChange, label, className }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = findCountry(value) || COUNTRIES[0]
  const results = useMemo(() => searchCountries(query).slice(0, 100), [query])

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
          <span className="flex items-center gap-2">
            <span className="text-lg leading-none">{selected.flag}</span>
            <span className="text-gray-800">{selected.name}</span>
          </span>
          <ChevronDown size={16} className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>

        {open && (
          <div className="absolute z-30 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100">
              <Search size={14} className="text-gray-400" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Rechercher un pays…"
                className="flex-1 text-sm outline-none bg-transparent"
              />
            </div>
            <ul className="max-h-64 overflow-y-auto py-1" role="listbox">
              {results.length === 0 && (
                <li className="px-3 py-2 text-xs text-gray-400">Aucun résultat</li>
              )}
              {results.map((c) => (
                <li key={c.code}>
                  <button
                    type="button"
                    onClick={() => { onChange(c.code); setOpen(false) }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-orange-50 ${c.code === value ? 'bg-orange-50/50' : ''}`}
                  >
                    <span className="text-lg leading-none">{c.flag}</span>
                    <span className="flex-1 text-left text-gray-800">{c.name}</span>
                    {c.code === value && <Check size={14} className="text-orange-500" />}
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
