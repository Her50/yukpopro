import { useState, useEffect } from 'react'
import {
  ArrowTrendingUpIcon,
  MagnifyingGlassIcon,
  BoltIcon,
  ChartBarIcon,
  GlobeAltIcon,
  NewspaperIcon,
} from '@heroicons/react/24/outline'

interface Trend {
  id: string
  sujet: string
  score: number
  variation_pct: number
  sources: string[]
  resume: string
  pertinence_assurance: string
  date: string
  categorie: 'marche' | 'reglementaire' | 'technologie' | 'sinistres' | 'concurrent'
}

const DEMO_TRENDS: Trend[] = [
  {
    id: '1',
    sujet: 'Micro-assurance mobile en Afrique subsaharienne',
    score: 92,
    variation_pct: +18,
    sources: ['NewsAPI', 'Google Trends'],
    resume: 'L\'adoption de la micro-assurance via Mobile Money croît de 35% en zone CIMA. MTN et Orange Money intègrent des produits d\'assurance automatiques.',
    pertinence_assurance: 'Opportunité de lancement de produits micro-assurance vie et accident liés au Mobile Money.',
    date: '2026-04-08',
    categorie: 'marche',
  },
  {
    id: '2',
    sujet: 'Nouvelles directives CIMA sur les provisions mathématiques',
    score: 88,
    variation_pct: +5,
    sources: ['CIMA', 'CRCA'],
    resume: 'La CIMA publie une circulaire sur le renforcement des provisions mathématiques vie. Entrée en vigueur : 1er juillet 2026.',
    pertinence_assurance: 'Impact direct sur les compagnies vie — révision des tables de mortalité et calcul des PM.',
    date: '2026-04-07',
    categorie: 'reglementaire',
  },
  {
    id: '3',
    sujet: 'IA dans la détection de fraude automobile',
    score: 85,
    variation_pct: +22,
    sources: ['LinkedIn', 'YouTube'],
    resume: 'Les compagnies pionnières réduisent la fraude auto de 40% grâce à l\'analyse d\'images par IA. Retour sur investissement moyen en 8 mois.',
    pertinence_assurance: 'Adoption recommandée du module Fraude IA de YukpoAssurance sur la branche auto.',
    date: '2026-04-07',
    categorie: 'technologie',
  },
  {
    id: '4',
    sujet: 'Hausse sinistres climatiques en zone CEMAC',
    score: 79,
    variation_pct: +31,
    sources: ['NewsAPI', 'Reddit'],
    resume: 'Les inondations au Cameroun et en RCA enregistrent une hausse de 40% en 2025-2026. Les sinistres IRD et MRH explosent.',
    pertinence_assurance: 'Révision tarifaire urgente en IRD/MRH. Renforcement des plafonds de couverture catastrophe.',
    date: '2026-04-06',
    categorie: 'sinistres',
  },
  {
    id: '5',
    sujet: 'Concurrence des insurtechs africaines',
    score: 74,
    variation_pct: +15,
    sources: ['TechCabal', 'LinkedIn'],
    resume: 'Plusieurs insurtechs (Turaco, MIC Global, Lami) lèvent des fonds massifs et attaquent le marché B2C digital en zone CIMA.',
    pertinence_assurance: 'Nécessité d\'accélérer la digitalisation et l\'expérience client pour maintenir la compétitivité.',
    date: '2026-04-05',
    categorie: 'concurrent',
  },
]

const CATEGORIES = {
  marche: { label: 'Marché', color: 'bg-blue-100 text-blue-700' },
  reglementaire: { label: 'Réglementaire', color: 'bg-purple-100 text-purple-700' },
  technologie: { label: 'Technologie', color: 'bg-green-100 text-green-700' },
  sinistres: { label: 'Sinistres', color: 'bg-red-100 text-red-700' },
  concurrent: { label: 'Concurrence', color: 'bg-yellow-100 text-yellow-700' },
}

export default function TrendsPage() {
  const [trends, setTrends] = useState<Trend[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterCategorie, setFilterCategorie] = useState('')
  const [selectedTrend, setSelectedTrend] = useState<Trend | null>(null)

  useEffect(() => {
    const load = async () => {
      setIsLoading(true)
      try {
        const res = await fetch('/api/v1/trends/snapshot', {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
        })
        if (res.ok) {
          const data = await res.json()
          setTrends(Array.isArray(data.tendances) ? data.tendances : DEMO_TRENDS)
        } else {
          setTrends(DEMO_TRENDS)
        }
      } catch {
        setTrends(DEMO_TRENDS)
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [])

  const filtered = trends.filter((t) => {
    const matchSearch = !search || t.sujet.toLowerCase().includes(search.toLowerCase())
    const matchCat = !filterCategorie || t.categorie === filterCategorie
    return matchSearch && matchCat
  })

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <ArrowTrendingUpIcon className="h-6 w-6 text-primary-600" />
            Veille & Tendances
          </h2>
          <p className="text-sm text-gray-500">IA analyse le marché assurance africain en temps réel</p>
        </div>
        <button
          onClick={() => window.location.reload()}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-xl text-sm hover:bg-primary-700 transition-colors"
        >
          <BoltIcon className="h-4 w-4" />
          Actualiser
        </button>
      </div>

      {/* Stats rapides */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Tendances suivies', value: trends.length, icon: ChartBarIcon, color: 'text-primary-600' },
          { label: 'Score moyen', value: trends.length ? Math.round(trends.reduce((s, t) => s + t.score, 0) / trends.length) : 0, icon: ArrowTrendingUpIcon, color: 'text-green-600' },
          { label: 'Alertes règlement.', value: trends.filter(t => t.categorie === 'reglementaire').length, icon: GlobeAltIcon, color: 'text-purple-600' },
          { label: 'Opportunités', value: trends.filter(t => t.categorie === 'marche').length, icon: NewspaperIcon, color: 'text-blue-600' },
        ].map((stat) => (
          <div key={stat.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
            <stat.icon className={`h-5 w-5 ${stat.color} mb-2`} />
            <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
            <p className="text-xs text-gray-500 mt-1">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Filtres */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher une tendance..."
            className="w-full pl-9 pr-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:border-primary-500 outline-none"
          />
        </div>
        <select
          value={filterCategorie}
          onChange={(e) => setFilterCategorie(e.target.value)}
          className="border border-gray-300 rounded-xl px-3 py-2.5 text-sm bg-white"
        >
          <option value="">Toutes catégories</option>
          {Object.entries(CATEGORIES).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
      </div>

      {/* Liste des tendances */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((trend) => (
            <div
              key={trend.id}
              className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 hover:border-primary-200 transition-colors cursor-pointer"
              onClick={() => setSelectedTrend(trend === selectedTrend ? null : trend)}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${CATEGORIES[trend.categorie].color}`}>
                      {CATEGORIES[trend.categorie].label}
                    </span>
                    <span className={`text-xs font-medium ${trend.variation_pct > 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {trend.variation_pct > 0 ? '▲' : '▼'} {Math.abs(trend.variation_pct)}%
                    </span>
                    <span className="text-xs text-gray-400">{trend.date}</span>
                  </div>
                  <h3 className="font-semibold text-gray-900 text-sm">{trend.sujet}</h3>
                  <p className="text-xs text-gray-500 mt-1 line-clamp-2">{trend.resume}</p>
                </div>
                <div className="flex flex-col items-center">
                  <div className="w-12 h-12 rounded-full bg-primary-50 flex items-center justify-center">
                    <span className="text-sm font-bold text-primary-600">{trend.score}</span>
                  </div>
                  <span className="text-xs text-gray-400 mt-1">score</span>
                </div>
              </div>

              {selectedTrend?.id === trend.id && (
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <p className="text-sm text-gray-600 mb-3">{trend.resume}</p>
                  <div className="bg-primary-50 rounded-lg p-3">
                    <p className="text-xs font-semibold text-primary-700 mb-1">Pertinence assurance :</p>
                    <p className="text-sm text-primary-800">{trend.pertinence_assurance}</p>
                  </div>
                  <div className="flex gap-2 mt-3">
                    {trend.sources.map((s) => (
                      <span key={s} className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">{s}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
