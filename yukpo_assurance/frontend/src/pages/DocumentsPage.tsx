import { useState, useRef, useEffect, useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  DocumentTextIcon,
  ArrowDownTrayIcon,
  SparklesIcon,
  PresentationChartBarIcon,
  TableCellsIcon,
  DocumentIcon,
  ClockIcon,
  ArrowPathIcon,
  ChevronRightIcon,
  XMarkIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { documentsAPI, DocHistoriqueBackend } from '../api/client'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const schema = z.object({
  type_document: z.enum(['docx', 'pdf', 'pptx', 'excel']),
  prompt: z.string().min(10, 'Décrivez plus précisément le document souhaité'),
  contexte: z.string().optional(),
})

type FormValues = z.infer<typeof schema>

// ─── Templates spécialisés ──────────────────────────────────────────────────

const TEMPLATES_SPECIALISES = [
  {
    categorie: 'Rapports Réglementaires',
    couleur: 'bg-indigo-50 border-indigo-200',
    iconeCat: '⚖️',
    templates: [
      {
        label: 'Rapport Conformité CIMA',
        type: 'pdf' as const,
        endpoint: '/api/v1/documents/rapport-cima-annuel',
        prompt: 'Rapport conformité CIMA complet — ratios prudentiels, états C1-C20, alertes réglementaires',
        icon: '📋',
      },
      {
        label: 'Présentation CA (PPTX)',
        type: 'pptx' as const,
        endpoint: '/api/v1/documents/presentation-ca',
        prompt: 'Présentation pour le Conseil d\'Administration — résultats, ratios CIMA, perspectives',
        icon: '📊',
      },
      {
        label: 'État C12 Réassurance',
        type: 'pdf' as const,
        endpoint: '/api/v1/reassurance/etat-c12/2024',
        prompt: 'État C12 CIMA — cessions en réassurance, bordereau, conformité Art. 312',
        icon: '🛡️',
      },
    ],
  },
  {
    categorie: 'Tableaux de Bord Excel',
    couleur: 'bg-green-50 border-green-200',
    iconeCat: '📈',
    templates: [
      {
        label: 'Dashboard Sinistres',
        type: 'excel' as const,
        endpoint: '/api/v1/documents/tableau-de-bord-excel',
        prompt: 'Tableau de bord Excel sinistres — par branche, fraudes détectées, tendances, S/P',
        icon: '📉',
      },
      {
        label: 'Tableau CIMA (États C1-C20)',
        type: 'excel' as const,
        endpoint: '/api/v1/cima/etats-excel',
        prompt: 'Tous les états réglementaires C1 à C20 — provisions, marges, ratios — format Excel CRCA',
        icon: '📊',
      },
      {
        label: 'Rapport Activité Mensuel',
        type: 'excel' as const,
        endpoint: '/api/v1/documents/rapport-activite',
        prompt: 'Rapport mensuel d\'activité — primes, sinistres, commissions, charges par branche',
        icon: '📅',
      },
    ],
  },
  {
    categorie: 'Rapports Sinistres',
    couleur: 'bg-red-50 border-red-200',
    iconeCat: '🚨',
    templates: [
      {
        label: 'Rapport Sinistres Auto (PDF)',
        type: 'pdf' as const,
        endpoint: '/api/v1/documents/rapport-sinistres',
        prompt: 'Rapport sinistres automobiles — déclarations du mois, fraudes, provisions PSAP, délais de règlement',
        icon: '🚗',
      },
      {
        label: 'Présentation Fraude (PPTX)',
        type: 'pptx' as const,
        endpoint: '/api/v1/documents/presentation-avancee',
        prompt: 'Présentation détection fraude — scores ML, patterns identifiés, cas suspects, recommandations',
        icon: '🔍',
      },
    ],
  },
]

const EXEMPLES_PROMPTS = [
  'Génère un rapport mensuel de sinistres Auto avec analyse des tendances et graphiques par branche',
  'Crée une présentation PowerPoint de résultats commerciaux Q1 2025 avec KPIs et carte de chaleur',
  'Rédige un rapport PSAP et provisions techniques conforme Art. 334 CIMA pour l\'exercice 2024',
  'Produis un tableau de bord Excel de suivi des courtiers avec commissions et objectifs',
  'Génère un rapport d\'analyse de la marge de solvabilité avec alertes CIMA et recommandations IA',
]

// Legacy local type kept for display helpers only
interface DocHistorique {
  id: number
  nom: string
  type: string
  date: string
  url?: string
}

interface SSEProgress {
  etape: string
  progression: number
  detail?: string
}

// ─── Composant principal ───────────────────────────────────────────────────

export function DocumentsPage() {
  const [isGenerating, setIsGenerating] = useState(false)
  const [generatedDoc, setGeneratedDoc] = useState<{ url?: string; nom_fichier?: string; type?: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sseProgress, setSseProgress] = useState<SSEProgress | null>(null)
  const [historique, setHistorique] = useState<DocHistoriqueBackend[]>([])
  const [histLoading, setHistLoading] = useState(false)
  const [onglet, setOnglet] = useState<'generer' | 'templates' | 'historique'>('generer')
  const eventSourceRef = useRef<EventSource | null>(null)

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { type_document: 'pdf' },
  })

  const selectedType = watch('type_document')

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => { eventSourceRef.current?.close() }
  }, [])

  // Charger l'historique depuis le backend
  const chargerHistorique = useCallback(async () => {
    setHistLoading(true)
    try {
      const res = await documentsAPI.historique()
      setHistorique(res.documents)
    } catch { /* ignore */ }
    finally { setHistLoading(false) }
  }, [])

  useEffect(() => { chargerHistorique() }, [chargerHistorique])

  // ─── Génération avec SSE ─────────────────────────────────────────────

  const genererAvecSSE = async (payload: FormValues) => {
    setIsGenerating(true)
    setError(null)
    setGeneratedDoc(null)
    setSseProgress({ etape: 'Initialisation', progression: 5 })

    const token = localStorage.getItem('access_token')

    // Try SSE streaming first for long docs
    try {
      const params = new URLSearchParams({
        prompt: payload.prompt,
        type_document: payload.type_document,
        contexte: payload.contexte || '',
        token: token || '',
      })

      const es = new EventSource(`${BASE_URL}/api/v1/streaming/generer-document?${params}`)
      eventSourceRef.current = es

      const sauvegarderDoc = async (doc: { url?: string; nom_fichier?: string; type?: string }, promptUsed: string) => {
        try {
          await documentsAPI.sauvegarder({
            titre: doc.nom_fichier || promptUsed.slice(0, 100),
            type_doc: doc.type === 'pptx' ? 'slides' : doc.type === 'xlsx' || doc.type === 'excel' ? 'autre' : 'rapport',
            fichier: doc.nom_fichier,
            contenu_source: promptUsed,
            meta: { type_format: doc.type },
          })
          chargerHistorique()
        } catch { /* non bloquant */ }
      }

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'progress') {
            setSseProgress({ etape: data.etape, progression: data.progression, detail: data.detail })
          } else if (data.type === 'complete') {
            setGeneratedDoc(data.document)
            setSseProgress(null)
            setIsGenerating(false)
            es.close()
            sauvegarderDoc(data.document, payload.prompt)
          } else if (data.type === 'error') {
            setError(data.message)
            setSseProgress(null)
            setIsGenerating(false)
            es.close()
          }
        } catch { /* ignore parse errors */ }
      }

      es.onerror = async () => {
        es.close()
        // Fallback to regular POST
        try {
          const result = await documentsAPI.generer(payload)
          setGeneratedDoc(result as { url?: string; nom_fichier?: string; type?: string })
          sauvegarderDoc(result as { url?: string; nom_fichier?: string; type?: string }, payload.prompt)
        } catch (err: unknown) {
          const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          setError(msg || 'Erreur lors de la génération. Veuillez réessayer.')
        } finally {
          setSseProgress(null)
          setIsGenerating(false)
        }
      }
    } catch {
      setError('Impossible de lancer la génération.')
      setSseProgress(null)
      setIsGenerating(false)
    }
  }

  // ─── Supprimer document ───────────────────────────────────────────────

  const supprimerDoc = async (id: number) => {
    try {
      await documentsAPI.supprimer(id)
      setHistorique(prev => prev.filter(d => d.id !== id))
    } catch { /* ignore */ }
  }

  // ─── Template rapide ─────────────────────────────────────────────────

  const utiliserTemplate = (template: typeof TEMPLATES_SPECIALISES[0]['templates'][0]) => {
    setValue('type_document', template.type)
    setValue('prompt', template.prompt)
    setOnglet('generer')
  }

  // ─── Icône type doc ──────────────────────────────────────────────────

  const iconeType = (type: string) => {
    const icons: Record<string, React.ReactNode> = {
      pdf: <DocumentIcon className="w-4 h-4 text-red-500" />,
      docx: <DocumentTextIcon className="w-4 h-4 text-blue-500" />,
      pptx: <PresentationChartBarIcon className="w-4 h-4 text-orange-500" />,
      excel: <TableCellsIcon className="w-4 h-4 text-green-500" />,
    }
    return icons[type] || <DocumentTextIcon className="w-4 h-4 text-gray-500" />
  }

  const couleurType: Record<string, string> = {
    pdf: 'border-red-300 bg-red-50 text-red-700',
    docx: 'border-blue-300 bg-blue-50 text-blue-700',
    pptx: 'border-orange-300 bg-orange-50 text-orange-700',
    excel: 'border-green-300 bg-green-50 text-green-700',
  }

  return (
    <div className="space-y-6">

      {/* En-tête */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
        <p className="text-sm text-gray-500 mt-1">
          Génération IA — PDF · Word · PowerPoint · Excel · Rapports CIMA automatisés
        </p>
      </div>

      {/* Onglets */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {[
            { key: 'generer', label: 'Générer un document', icon: SparklesIcon },
            { key: 'templates', label: 'Templates spécialisés', icon: PresentationChartBarIcon },
            { key: 'historique', label: `Historique${historique.length > 0 ? ` (${historique.length})` : ''}`, icon: ClockIcon },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setOnglet(t.key as typeof onglet)}
              className={`flex items-center gap-2 pb-3 text-sm font-medium border-b-2 transition-colors ${
                onglet === t.key
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Onglet Générer ─────────────────────────────────────────────── */}
      {onglet === 'generer' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Formulaire */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <form onSubmit={handleSubmit(genererAvecSSE)} className="space-y-5">

              {/* Type */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Format</label>
                <div className="grid grid-cols-2 gap-2">
                  {([
                    { value: 'pdf', label: 'PDF', icon: '📄' },
                    { value: 'docx', label: 'Word', icon: '📝' },
                    { value: 'pptx', label: 'PowerPoint', icon: '📊' },
                    { value: 'excel', label: 'Excel', icon: '📈' },
                  ] as { value: FormValues['type_document']; label: string; icon: string }[]).map(({ value, label, icon }) => (
                    <label
                      key={value}
                      className={clsx(
                        'flex items-center gap-2 border-2 rounded-xl p-3 cursor-pointer transition-all',
                        selectedType === value ? couleurType[value] + ' border-current' : 'border-gray-200 hover:border-gray-300 bg-white'
                      )}
                    >
                      <input type="radio" value={value} {...register('type_document')} className="hidden" />
                      <span className="text-lg">{icon}</span>
                      <span className="text-sm font-medium">{label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Prompt */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Description du document</label>
                <textarea
                  {...register('prompt')}
                  rows={5}
                  placeholder="Ex: Génère un rapport mensuel de sinistres auto avec graphiques par branche, analyse S/P et provisions PSAP..."
                  className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 outline-none resize-none"
                />
                {errors.prompt && <p className="text-xs text-red-600 mt-1">{errors.prompt.message}</p>}
              </div>

              {/* Contexte */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Contexte <span className="text-gray-400">(optionnel)</span>
                </label>
                <textarea
                  {...register('contexte')}
                  rows={2}
                  placeholder="Ex: Compagnie ABC Assurances, Cameroun, exercice 2024..."
                  className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:border-primary-500 outline-none resize-none"
                />
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700 flex items-start gap-2">
                  <XMarkIcon className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={isGenerating}
                className="w-full flex items-center justify-center gap-2 bg-primary-600 text-white rounded-xl py-3 text-sm font-semibold hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed transition-all shadow-md shadow-primary-600/20"
              >
                {isGenerating ? (
                  <><ArrowPathIcon className="w-4 h-4 animate-spin" /> Génération en cours…</>
                ) : (
                  <><SparklesIcon className="w-5 h-5" /> Générer le document</>
                )}
              </button>
            </form>

            {/* Exemples */}
            <div className="mt-5">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Exemples de prompts</p>
              <div className="space-y-1.5">
                {EXEMPLES_PROMPTS.map((ex, i) => (
                  <button
                    key={i}
                    onClick={() => setValue('prompt', ex)}
                    className="w-full text-left text-xs text-gray-600 bg-gray-50 hover:bg-gray-100 rounded-lg px-3 py-2 transition-colors flex items-start gap-2"
                  >
                    <ChevronRightIcon className="w-3 h-3 mt-0.5 flex-shrink-0 text-gray-400" />
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Résultat / Preview */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 flex flex-col">
            <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
              <DocumentTextIcon className="h-4 w-4 text-primary-600" />
              Aperçu du document
            </h3>

            {/* Progression SSE */}
            {isGenerating && (
              <div className="flex-1 flex flex-col items-center justify-center">
                <div className="w-full max-w-xs">
                  {sseProgress && (
                    <>
                      <div className="flex justify-between text-xs text-gray-600 mb-2">
                        <span>{sseProgress.etape}</span>
                        <span>{sseProgress.progression}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2 mb-3">
                        <div
                          className="bg-primary-500 h-2 rounded-full transition-all duration-500"
                          style={{ width: `${sseProgress.progression}%` }}
                        />
                      </div>
                      {sseProgress.detail && (
                        <p className="text-xs text-gray-400 text-center">{sseProgress.detail}</p>
                      )}
                    </>
                  )}
                  <div className="flex items-center justify-center gap-2 mt-4">
                    <ArrowPathIcon className="w-5 h-5 animate-spin text-primary-500" />
                    <span className="text-sm text-gray-500">YukpoPro génère votre document…</span>
                  </div>
                  <p className="text-xs text-gray-400 text-center mt-1">Powered by Claude Opus + python-pptx / fpdf2 / openpyxl</p>
                </div>
              </div>
            )}

            {/* Doc généré */}
            {!isGenerating && generatedDoc && (
              <div className="flex-1 flex flex-col gap-4">
                <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    {iconeType(generatedDoc.type || 'pdf')}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-green-800">Document prêt !</p>
                    <p className="text-xs text-green-600 mt-0.5">{generatedDoc.nom_fichier}</p>
                  </div>
                </div>

                {generatedDoc.url && (
                  <>
                    {(generatedDoc.type === 'pdf') && (
                      <div className="flex-1 min-h-64 border border-gray-200 rounded-xl overflow-hidden">
                        <iframe src={`${BASE_URL}${generatedDoc.url}`} className="w-full h-full min-h-64" title="Aperçu PDF" />
                      </div>
                    )}
                    <a
                      href={`${BASE_URL}${generatedDoc.url}`}
                      download={generatedDoc.nom_fichier}
                      className="flex items-center justify-center gap-2 bg-primary-600 text-white rounded-xl py-3 text-sm font-medium hover:bg-primary-700 transition-colors"
                    >
                      <ArrowDownTrayIcon className="h-4 w-4" />
                      Télécharger — {generatedDoc.nom_fichier}
                    </a>
                  </>
                )}
              </div>
            )}

            {/* État vide */}
            {!isGenerating && !generatedDoc && (
              <div className="flex-1 flex flex-col items-center justify-center text-center py-12">
                <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center mb-4">
                  <DocumentTextIcon className="h-8 w-8 text-gray-400" />
                </div>
                <p className="text-sm text-gray-500">Le document généré apparaîtra ici</p>
                <p className="text-xs text-gray-400 mt-1">Renseignez le formulaire et cliquez sur "Générer"</p>
                <div className="mt-6 grid grid-cols-2 gap-3 text-xs text-gray-400">
                  {['Thèmes couleur pro', 'KPI cards', 'Graphiques Python', 'Export haute qualité'].map(f => (
                    <div key={f} className="flex items-center gap-1.5">
                      <span className="text-green-400">✓</span> {f}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Onglet Templates spécialisés ──────────────────────────────── */}
      {onglet === 'templates' && (
        <div className="space-y-6">
          {TEMPLATES_SPECIALISES.map((cat) => (
            <div key={cat.categorie} className={`rounded-xl border p-5 ${cat.couleur}`}>
              <h3 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
                <span className="text-base">{cat.iconeCat}</span>
                {cat.categorie}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {cat.templates.map((t) => (
                  <button
                    key={t.label}
                    onClick={() => utiliserTemplate(t)}
                    className="bg-white rounded-xl border border-gray-200 p-4 text-left hover:border-primary-400 hover:shadow-md transition-all group"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xl">{t.icon}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${couleurType[t.type]} font-medium`}>{t.type.toUpperCase()}</span>
                    </div>
                    <p className="text-sm font-semibold text-gray-800 group-hover:text-primary-700 transition-colors">{t.label}</p>
                    <p className="text-xs text-gray-500 mt-1 line-clamp-2">{t.prompt}</p>
                    <div className="flex items-center gap-1 mt-3 text-xs text-primary-600 font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                      Utiliser ce template <ChevronRightIcon className="w-3 h-3" />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Onglet Historique ─────────────────────────────────────────── */}
      {onglet === 'historique' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-800">
              Documents générés ({historique.length})
            </h3>
            <button
              onClick={chargerHistorique}
              disabled={histLoading}
              className="text-xs text-gray-500 hover:text-primary-600 flex items-center gap-1"
            >
              <ArrowPathIcon className={clsx('w-3.5 h-3.5', histLoading && 'animate-spin')} />
              Actualiser
            </button>
          </div>

          {histLoading && historique.length === 0 ? (
            <div className="py-12 text-center text-gray-400 text-sm">Chargement…</div>
          ) : historique.length === 0 ? (
            <div className="py-12 text-center">
              <DocumentTextIcon className="w-10 h-10 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-400">Aucun document généré pour l'instant</p>
              <p className="text-xs text-gray-300 mt-1">Les documents générés apparaîtront ici automatiquement</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Document</th>
                  <th className="text-center px-4 py-2.5 text-xs font-medium text-gray-600">Type</th>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Date</th>
                  <th className="text-center px-4 py-2.5 text-xs font-medium text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {historique.map((doc, i) => {
                  const ext = doc.fichier ? doc.fichier.split('.').pop() || doc.type_doc : doc.type_doc
                  const dateStr = doc.cree_le ? new Date(doc.cree_le).toLocaleDateString('fr-FR', {
                    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
                  }) : '—'
                  return (
                    <tr key={doc.id} className={`${i % 2 === 0 ? '' : 'bg-gray-50'} hover:bg-blue-50 transition-colors`}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {iconeType(ext)}
                          <div className="min-w-0">
                            <p className="text-gray-800 font-medium text-xs truncate max-w-xs">{doc.titre}</p>
                            {doc.fichier && <p className="text-gray-400 text-xs truncate max-w-xs">{doc.fichier}</p>}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${couleurType[ext] || 'border-gray-200 bg-gray-50 text-gray-600'}`}>
                          {doc.type_doc.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{dateStr}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-center gap-3">
                          {doc.fichier && (
                            <a
                              href={`${BASE_URL}/api/v1/documents/telecharger/${doc.fichier}`}
                              download={doc.fichier}
                              className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-1"
                            >
                              <ArrowDownTrayIcon className="w-3.5 h-3.5" /> Télécharger
                            </a>
                          )}
                          <button
                            onClick={() => supprimerDoc(doc.id)}
                            className="text-xs text-red-400 hover:text-red-600 flex items-center gap-1"
                          >
                            <TrashIcon className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
