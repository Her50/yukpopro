import { useState, useEffect, useRef } from 'react'
import { ScaleIcon, CheckCircleIcon, XCircleIcon, PaperAirplaneIcon } from '@heroicons/react/24/outline'
import { cimaAPI } from '../api/client'
import { RatioCIMA } from '../api/types'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { clsx } from 'clsx'

const DEMO_RATIOS: RatioCIMA[] = [
  // Non-Vie
  { nom: 'Marge de solvabilité (Non-Vie)', valeur: 142.8, seuil_min: 100, unite: '%', conforme: true, description: 'Actif net / Exigence réglementaire — Art. 337 CIMA' },
  { nom: 'Ratio S/P Non-Vie', valeur: 68.4, seuil_max: 65, unite: '%', conforme: false, description: 'Sinistres payés + PSAP / Primes acquises — toutes branches Non-Vie' },
  { nom: 'Taux couverture provisions Non-Vie', valeur: 108.2, seuil_min: 100, unite: '%', conforme: true, description: 'Actifs représentatifs / Provisions techniques brutes Non-Vie' },
  // Vie
  { nom: 'Provisions mathématiques Vie', valeur: 104.6, seuil_min: 100, unite: '%', conforme: true, description: 'PM constituées / PM théoriques — méthode prospective CIMA' },
  { nom: 'Ratio S/P Vie', valeur: 38.2, seuil_max: 55, unite: '%', conforme: true, description: 'Prestations vie payées / Primes vie acquises' },
  { nom: 'Taux couverture provisions Vie', valeur: 105.8, seuil_min: 100, unite: '%', conforme: true, description: 'Actifs représentatifs / PM + PSAP Vie' },
  // Communs
  { nom: 'Ratio frais généraux', valeur: 22.1, seuil_max: 30, unite: '%', conforme: true, description: 'Frais de gestion / Primes émises toutes branches' },
  { nom: 'Ratio de liquidité', valeur: 1.45, seuil_min: 1, unite: 'x', conforme: true, description: 'Actifs liquides / Passifs exigibles à court terme' },
  { nom: 'Taux de réassurance', valeur: 12.3, seuil_max: 50, unite: '%', conforme: true, description: 'Primes cédées / Primes brutes — limite excédent de sinistres' },
]

// Source : Code CIMA consolidé 2024 — Art. 400, Annexe réglementaire états C1-C20
const ETATS_CIMA = [
  { code: 'C1',  label: 'Résultat technique Non-Vie',           famille: 'non_vie', description: 'Primes, sinistres, PSAP, commissions, frais — solde technique Non-Vie', echeance: '31 mars' },
  { code: 'C2',  label: 'Résultat technique Vie',               famille: 'vie',     description: 'Primes vie, prestations, PM, produits financiers, solde technique Vie — Art. 423 CIMA', echeance: '31 mars' },
  { code: 'C3',  label: 'Bilan',                                famille: 'commun',  description: 'Actif (placements, créances, trésorerie) et Passif (provisions, capitaux propres)', echeance: '31 mars' },
  { code: 'C4',  label: 'État des placements',                  famille: 'commun',  description: 'Portefeuille placements, rendement, actifs représentatifs — Art. 335 CIMA', echeance: '31 mars' },
  { code: 'C5',  label: 'Provisions techniques Non-Vie',        famille: 'non_vie', description: 'PSAP (Art. 334-2), PPNA (Art. 334-1), PRC pour risques croissants (Art. 334-3) par branche', echeance: '31 mars' },
  { code: 'C6',  label: 'Provisions mathématiques Vie',         famille: 'vie',     description: 'PM par police et par contrat — méthode prospective obligatoire (Art. 334-4 CIMA)', echeance: '31 mars' },
  { code: 'C7',  label: 'Marge de solvabilité',                 famille: 'commun',  description: 'Calcul exigence réglementaire Non-Vie (23%/26%) et Vie (4% PM) — Art. 337/338 CIMA', echeance: '31 mars' },
  { code: 'C8',  label: 'Cessions en réassurance',              famille: 'commun',  description: 'Primes cédées, sinistres récupérés, dépôts — tous traités XL et quote-part', echeance: '31 mars' },
  { code: 'C9',  label: 'Statistiques sinistres automobiles',   famille: 'non_vie', description: 'Dossiers RC auto : déclarés, réglés, PSAP — délais Art. 231 CIMA', echeance: '31 mars' },
  { code: 'C10', label: 'Statistiques sinistres Vie',           famille: 'vie',     description: 'Sinistres vie déclarés, réglés, provisions — délai 30 jours Art. 73 CIMA', echeance: '31 mars' },
  { code: 'C11', label: 'État de concordance',                  famille: 'commun',  description: 'Rapprochement entre états financiers et états prudentiels CRCA', echeance: '31 mars' },
  { code: 'C12', label: 'Production par branche',               famille: 'commun',  description: 'Primes émises par branche et département (auto, vie, IRD, RC, transport…)', echeance: '31 mars' },
  { code: 'C13', label: 'Intermédiaires d\'assurance',          famille: 'commun',  description: 'Agents, courtiers, commissions — Art. 502-520 CIMA', echeance: '31 mars' },
  { code: 'C14', label: 'Rapport du commissaire aux comptes',   famille: 'commun',  description: 'Rapport CAC certifiant les états financiers annuels — délai 30 avril', echeance: '30 avril' },
  { code: 'C15', label: 'Rapport du Conseil d\'Administration', famille: 'commun',  description: 'Rapport de gestion CA : activité, résultats, perspectives — délai 30 avril', echeance: '30 avril' },
  { code: 'C16', label: 'Engagements hors bilan',               famille: 'commun',  description: 'Cautions, garanties données, engagements conditionnels hors bilan', echeance: '31 mars' },
  { code: 'C17', label: 'Stats trimestrielles production',      famille: 'commun',  description: 'Primes par branche, évolution trimestrielle — délai T+30 jours', echeance: 'T+30j' },
  { code: 'C18', label: 'Stats trimestrielles sinistres',       famille: 'commun',  description: 'Sinistres déclarés, réglés, PSAP par trimestre — délai T+30 jours', echeance: 'T+30j' },
  { code: 'C19', label: 'Rapport d\'audit interne',             famille: 'commun',  description: 'Rapport annuel d\'audit interne — contrôle interne et conformité', echeance: '31 mars' },
  { code: 'C20', label: 'Plan de réassurance',                  famille: 'commun',  description: 'Programme réassurance N+1 : traités XL, quote-part, sinistres catastrophiques — Art. 312 CIMA', echeance: '31 janvier' },
]

// Échéances CRCA — Art. 400 Code CIMA (délai 3 mois après clôture exercice 31/12)
const ECHEANCES = [
  { date: '31 janvier 2026', label: 'C20 — Plan de réassurance 2026 à déposer à la CRCA (Art. 312 CIMA)', urgent: true },
  { date: '31 mars 2026',    label: 'C1–C13, C16, C19 — États financiers et prudentiels annuels exercice 2025 (Art. 400 CIMA)', urgent: true },
  { date: '30 avril 2026',   label: 'C14 & C15 — Rapport CAC + Rapport CA exercice 2025 (Art. 400 CIMA)', urgent: true },
  { date: '30 avril 2026',   label: 'C17/C18 — Stats trimestrielles Q1 2026 (délai T+30 jours)', urgent: false },
  { date: '31 juillet 2026', label: 'C17/C18 — Stats trimestrielles Q2 2026 (délai T+30 jours)', urgent: false },
]

interface QAMessage {
  role: 'user' | 'assistant'
  content: string
}

export function CIMAPage() {
  const [ratios, setRatios] = useState<RatioCIMA[]>([])
  const [isLoadingRatios, setIsLoadingRatios] = useState(true)
  const [messages, setMessages] = useState<QAMessage[]>([])
  const [question, setQuestion] = useState('')
  const [isAsking, setIsAsking] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const load = async () => {
      setIsLoadingRatios(true)
      try {
        const data = await cimaAPI.getRatios() as Record<string, unknown>
        setRatios(Array.isArray(data) ? data : (data.ratios as typeof DEMO_RATIOS) || DEMO_RATIOS)
      } catch {
        setRatios(DEMO_RATIOS)
      } finally {
        setIsLoadingRatios(false)
      }
    }
    load()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const askQuestion = async () => {
    if (!question.trim() || isAsking) return
    const q = question.trim()
    setQuestion('')
    setMessages((prev) => [...prev, { role: 'user', content: q }])
    setIsAsking(true)
    try {
      const data = await cimaAPI.poserQuestion(q) as Record<string, unknown>
      setMessages((prev) => [...prev, { role: 'assistant', content: (data.reponse as string) || (data.answer as string) || 'Réponse reçue.' }])
    } catch {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: 'Désolé, je n\'ai pas pu répondre à cette question. Vérifiez votre connexion à l\'API.',
      }])
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-primary-600 rounded-xl flex items-center justify-center">
          <ScaleIcon className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Réglementation CIMA</h1>
          <p className="text-sm text-gray-400">Ratios prudentiels • Q&R réglementaire • Échéances</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: ratios + echéances */}
        <div className="lg:col-span-1 space-y-5">
          {/* Ratios */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Ratios prudentiels</h3>
            {isLoadingRatios ? (
              <LoadingSpinner label="Chargement..." />
            ) : (
              <div className="space-y-3">
                {ratios.map((ratio) => (
                  <div
                    key={ratio.nom}
                    className={clsx(
                      'p-3 rounded-xl border',
                      ratio.conforme ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-gray-700 truncate">{ratio.nom}</p>
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{ratio.description}</p>
                      </div>
                      {ratio.conforme ? (
                        <CheckCircleIcon className="h-5 w-5 text-green-500 flex-shrink-0" />
                      ) : (
                        <XCircleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
                      )}
                    </div>
                    <div className="flex items-center justify-between mt-2">
                      <span className={clsx('text-base font-bold', ratio.conforme ? 'text-green-700' : 'text-red-700')}>
                        {ratio.valeur}{ratio.unite}
                      </span>
                      <span className="text-xs text-gray-400">
                        {ratio.seuil_min && `min: ${ratio.seuil_min}${ratio.unite}`}
                        {ratio.seuil_max && `max: ${ratio.seuil_max}${ratio.unite}`}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Echéances */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Calendrier réglementaire</h3>
            <div className="space-y-3">
              {ECHEANCES.map((e) => (
                <div
                  key={e.label}
                  className={clsx(
                    'flex gap-3 items-start p-3 rounded-xl border text-sm',
                    e.urgent ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-gray-50'
                  )}
                >
                  <div className={clsx(
                    'text-xs font-bold px-2 py-1 rounded-lg flex-shrink-0',
                    e.urgent ? 'bg-red-600 text-white' : 'bg-gray-200 text-gray-600'
                  )}>
                    {e.date.split(' ')[0]}
                  </div>
                  <div>
                    <p className={clsx('text-xs font-medium', e.urgent ? 'text-red-700' : 'text-gray-700')}>{e.label}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{e.date}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Q&R chat */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-gray-100 shadow-sm flex flex-col" style={{ minHeight: '600px' }}>
          <div className="p-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-700">Questions réglementaires CIMA</h3>
            <p className="text-xs text-gray-400 mt-0.5">Posez vos questions sur le Code des Assurances CIMA</p>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="py-4 space-y-4">
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Non-Vie</p>
                  <div className="flex flex-wrap gap-2">
                    {[
                      'Calcul de la marge de solvabilité Non-Vie',
                      'Méthodes de calcul PSAP : dossier par dossier vs chain-ladder',
                      'Délais réglementaires règlement sinistres auto CIMA',
                      'Quels sont les ratios prudentiels obligatoires ?',
                    ].map(q => (
                      <button key={q} onClick={() => setQuestion(q)}
                        className="text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded-full px-3 py-1.5 transition-colors">
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Vie & Épargne</p>
                  <div className="flex flex-wrap gap-2">
                    {[
                      'Calcul des provisions mathématiques — méthode prospective',
                      'Tables de mortalité CIMA-2016 vs TD/TV 88-90',
                      'Exigences PM vie Art. 334 CIMA — couverture actifs représentatifs',
                      'Taux technique maximum contrats vie en zone CIMA',
                      'Valeur de rachat vie mixte Art. 75 CIMA',
                    ].map(q => (
                      <button key={q} onClick={() => setQuestion(q)}
                        className="text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 rounded-full px-3 py-1.5 transition-colors">
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">États réglementaires C1-C20</p>
                  <div className="flex flex-wrap gap-2">
                    {ETATS_CIMA.map(e => (
                      <button key={e.code}
                        onClick={() => setQuestion(`Explique l'état réglementaire ${e.code} — ${e.label}`)}
                        className={clsx(
                          'text-xs border rounded-full px-2.5 py-1 transition-colors font-medium',
                          e.famille === 'vie'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                            : e.famille === 'non_vie'
                            ? 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100'
                            : 'bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100'
                        )}>
                        {e.code}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-gray-400 mt-1">Vert = Vie · Bleu = Non-Vie · Gris = Commun</p>
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={clsx(
                  'flex',
                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                )}
              >
                <div
                  className={clsx(
                    'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
                    msg.role === 'user'
                      ? 'bg-primary-600 text-white rounded-tr-sm'
                      : 'bg-gray-100 text-gray-800 rounded-tl-sm'
                  )}
                >
                  {msg.content}
                </div>
              </div>
            ))}
            {isAsking && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-2.5">
                  <div className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <span key={i} className="w-2 h-2 bg-gray-400 rounded-full animate-pulse" style={{ animationDelay: `${i * 0.2}s` }} />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="p-4 border-t border-gray-100">
            <div className="flex items-center gap-2 rounded-xl border border-gray-300 px-3 py-2 focus-within:border-primary-500">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && askQuestion()}
                placeholder="Ex: Quels sont les délais de déclaration des sinistres selon le CIMA ?"
                className="flex-1 text-sm bg-transparent focus:outline-none placeholder-gray-400"
              />
              <button
                onClick={askQuestion}
                disabled={!question.trim() || isAsking}
                className="p-1.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-40 transition-colors"
              >
                <PaperAirplaneIcon className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
