/**
 * YukpoAssurance — Composant génération de rapports
 * Utilisé dans YukpoPro (mode général) et dans chaque module (templates spécialisés)
 * Génération IA : PDF · Word · PowerPoint · Excel
 */
import { useState, useRef, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  DocumentTextIcon, ArrowDownTrayIcon, SparklesIcon,
  PresentationChartBarIcon, TableCellsIcon, DocumentIcon,
  ClockIcon, ArrowPathIcon, ChevronRightIcon, XMarkIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { documentsAPI } from '../api/client'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const schema = z.object({
  type_document: z.enum(['docx', 'pdf', 'pptx', 'excel']),
  prompt: z.string().min(10, 'Décrivez plus précisément le rapport souhaité'),
  contexte: z.string().optional(),
})
type FormValues = z.infer<typeof schema>

export type ModuleRapport =
  | 'general' | 'sinistres' | 'comptabilite' | 'rh'
  | 'reassurance' | 'souscription' | 'commercial' | 'cima' | 'courtiers'

// ─── Templates par module ─────────────────────────────────────────────────────

interface Template {
  label: string
  type: FormValues['type_document']
  prompt: string
  icon: string
  endpoint?: string
}

interface CategorieTemplate {
  categorie: string
  couleur: string
  iconeCat: string
  templates: Template[]
}

const TEMPLATES: Record<ModuleRapport, CategorieTemplate[]> = {
  general: [
    {
      categorie: 'Rapports Réglementaires', couleur: 'bg-indigo-50 border-indigo-200', iconeCat: '⚖️',
      templates: [
        { label: 'Rapport Conformité CIMA', type: 'pdf', prompt: 'Rapport conformité CIMA complet — ratios prudentiels, états C1-C20, alertes réglementaires', icon: '📋' },
        { label: 'Présentation CA (PPTX)', type: 'pptx', prompt: 'Présentation pour le Conseil d\'Administration — résultats, ratios CIMA, perspectives', icon: '📊' },
        { label: 'État C12 Réassurance', type: 'pdf', prompt: 'État C12 CIMA — cessions en réassurance, bordereau, conformité Art. 312', icon: '🛡️' },
      ],
    },
    {
      categorie: 'Tableaux de Bord Excel', couleur: 'bg-green-50 border-green-200', iconeCat: '📈',
      templates: [
        { label: 'Dashboard Sinistres', type: 'excel', prompt: 'Tableau de bord Excel sinistres — par branche, fraudes détectées, tendances, S/P', icon: '📉' },
        { label: 'États CIMA C1-C20', type: 'excel', prompt: 'Tous les états réglementaires C1 à C20 — provisions, marges, ratios — format Excel CRCA', icon: '📊' },
        { label: 'Rapport Activité Mensuel', type: 'excel', prompt: 'Rapport mensuel activité — primes, sinistres, commissions, charges par branche', icon: '📅' },
      ],
    },
    {
      categorie: 'Rapports Stratégiques', couleur: 'bg-purple-50 border-purple-200', iconeCat: '🎯',
      templates: [
        { label: 'Rapport Fraude (PPTX)', type: 'pptx', prompt: 'Présentation détection fraude — scores ML, patterns identifiés, cas suspects, recommandations', icon: '🔍' },
        { label: 'Rapport PSAP Provisions', type: 'pdf', prompt: 'Rapport PSAP et provisions techniques conforme Art. 334 CIMA pour l\'exercice en cours', icon: '🏦' },
        { label: 'Analyse Solvabilité', type: 'pdf', prompt: 'Analyse marge de solvabilité avec alertes CIMA et recommandations — Art. 337', icon: '📐' },
      ],
    },
  ],
  sinistres: [
    {
      categorie: 'Rapports Sinistres', couleur: 'bg-red-50 border-red-200', iconeCat: '🚨',
      templates: [
        { label: 'Rapport Mensuel Sinistres', type: 'pdf', prompt: 'Rapport mensuel sinistres — déclarations, provisions PSAP, délais règlement, ratio S/P par branche', icon: '📋' },
        { label: 'Tableau Sinistres Excel', type: 'excel', prompt: 'Tableau de bord Excel sinistres — open/clos/provisionnés, par branche, par expert, évolution mensuelle', icon: '📊' },
        { label: 'Présentation Fraude', type: 'pptx', prompt: 'Présentation fraude sinistres — dossiers suspects, scores IA, patterns détectés, recommandations', icon: '🔍' },
      ],
    },
    {
      categorie: 'Analyses & Provisions', couleur: 'bg-orange-50 border-orange-200', iconeCat: '🏦',
      templates: [
        { label: 'Rapport PSAP Détaillé', type: 'pdf', prompt: 'État détaillé des provisions pour sinistres à payer (PSAP) — Art. 334 CIMA, par branche et exercice', icon: '📐' },
        { label: 'Analyse Sinistres Auto', type: 'pdf', prompt: 'Analyse approfondie sinistres automobiles — fréquence, sévérité, délais, fraudes, tendances', icon: '🚗' },
        { label: 'Rapport Sinistres Corporels', type: 'pdf', prompt: 'Rapport sinistres corporels — IPP, indemnités Art. 258 CIMA, délais 8 mois, litiges pendants', icon: '🏥' },
      ],
    },
  ],
  comptabilite: [
    {
      categorie: 'États Financiers OHADA', couleur: 'bg-green-50 border-green-200', iconeCat: '💰',
      templates: [
        { label: 'Bilan Comptable OHADA', type: 'pdf', prompt: 'Bilan comptable SYSCOA/OHADA — actif, passif, capitaux propres, provisions techniques assurance', icon: '📋' },
        { label: 'Compte de Résultat', type: 'pdf', prompt: 'Compte de résultat détaillé — primes acquises, charges sinistres, frais généraux, résultat net', icon: '📈' },
        { label: 'Balance Générale Excel', type: 'excel', prompt: 'Balance générale tous comptes — codes SYSCOA, soldes débiteurs/créditeurs, provisions, mouvements', icon: '⚖️' },
      ],
    },
    {
      categorie: 'Rapports de Gestion', couleur: 'bg-blue-50 border-blue-200', iconeCat: '📊',
      templates: [
        { label: 'Rapport Activité Mensuel', type: 'pdf', prompt: 'Rapport mensuel de gestion — primes émises, sinistres payés, charges, résultat technique par branche', icon: '📅' },
        { label: 'Tableau Suivi Trésorerie', type: 'excel', prompt: 'Tableau de bord trésorerie — entrées/sorties, soldes journaliers, projections, alertes liquidité', icon: '💸' },
        { label: 'États CIMA C1-C20', type: 'excel', prompt: 'Tous les états réglementaires CIMA C1 à C20 au format Excel pour transmission CRCA', icon: '🏛️' },
      ],
    },
  ],
  rh: [
    {
      categorie: 'Rapports Performance', couleur: 'bg-violet-50 border-violet-200', iconeCat: '🏆',
      templates: [
        { label: 'Rapport KPI Performance', type: 'pdf', prompt: 'Rapport performance RH — classement employés, scores KPI, réalisations vs objectifs, badges, recommandations primes', icon: '🎯' },
        { label: 'Tableau KPI Excel', type: 'excel', prompt: 'Tableau Excel KPI performance — scores par axe (qualité/réactivité/volume/objectifs), historique 6 mois, comparatif', icon: '📊' },
        { label: 'Présentation Performance CA', type: 'pptx', prompt: 'Présentation PowerPoint performance RH pour Direction — top performers, évolutions, plan primes objectivé', icon: '🎤' },
      ],
    },
    {
      categorie: 'Documents RH', couleur: 'bg-teal-50 border-teal-200', iconeCat: '📁',
      templates: [
        { label: 'Rapport Masse Salariale', type: 'excel', prompt: 'Analyse masse salariale — salaires par poste/département, charges sociales, évolution annuelle, budget prévisionnel', icon: '💼' },
        { label: 'Bilan Formation', type: 'pdf', prompt: 'Bilan des formations effectuées — compétences acquises, coûts, efficacité, plan formation N+1', icon: '🎓' },
        { label: 'Rapport Congés & Absences', type: 'excel', prompt: 'Suivi congés et absences — soldes par employé, taux absentéisme, planification équipes, alertes', icon: '📅' },
      ],
    },
  ],
  reassurance: [
    {
      categorie: 'États Réglementaires', couleur: 'bg-cyan-50 border-cyan-200', iconeCat: '🛡️',
      templates: [
        { label: 'État C12 CIMA', type: 'pdf', prompt: 'État C12 CIMA réassurance — cessions par traité, sinistres cédés, primes cédées, Art. 312, conformité', icon: '📋' },
        { label: 'Bordereau Primes Excel', type: 'excel', prompt: 'Bordereau électronique des primes cédées — par réassureur, traité, branche, période, avec accusés de réception', icon: '📊' },
        { label: 'Bordereau Sinistres Excel', type: 'excel', prompt: 'Bordereau électronique sinistres cédés — déclarations, règlements, recours, par réassureur et traité', icon: '📉' },
      ],
    },
    {
      categorie: 'Analyses Réassurance', couleur: 'bg-sky-50 border-sky-200', iconeCat: '📐',
      templates: [
        { label: 'Rapport Programme Réassurance', type: 'pdf', prompt: 'Rapport programme de réassurance — traités XS, quote-part, facultatives, plein de conservation, analyse coût/bénéfice', icon: '🔄' },
        { label: 'Analyse Cessions (PPTX)', type: 'pptx', prompt: 'Présentation analyse cessions réassurance — taux de cession par branche, économies sinistres, optimisation programme', icon: '📈' },
      ],
    },
  ],
  souscription: [
    {
      categorie: 'Rapports Portefeuille', couleur: 'bg-emerald-50 border-emerald-200', iconeCat: '📋',
      templates: [
        { label: 'Rapport Portefeuille Mensuel', type: 'pdf', prompt: 'Rapport mensuel portefeuille — polices actives, nouvelles souscriptions, résiliations, taux rétention, prime moyenne', icon: '📈' },
        { label: 'Analyse Portefeuille Excel', type: 'excel', prompt: 'Analyse portefeuille — répartition par branche, âge polices, historique sinistralité assuré, profil risque', icon: '📊' },
        { label: 'Rapport Renouvellements', type: 'excel', prompt: 'Suivi renouvellements — échéances 30/60/90 jours, taux conversion, primes à renouveler, alertes expirations', icon: '🔄' },
      ],
    },
    {
      categorie: 'Tarification & Production', couleur: 'bg-lime-50 border-lime-200', iconeCat: '🎯',
      templates: [
        { label: 'Analyse Tarification', type: 'pdf', prompt: 'Rapport analyse tarification — comparatif marché, prime technique vs commerciale, taux de chargement, élasticité', icon: '💲' },
        { label: 'Rapport Production Mensuel', type: 'pdf', prompt: 'Rapport production mensuel — nouvelles affaires par branche, canal, zone géographique, objectifs vs réalisé', icon: '🏭' },
      ],
    },
  ],
  commercial: [
    {
      categorie: 'Pipeline & Activité', couleur: 'bg-amber-50 border-amber-200', iconeCat: '📈',
      templates: [
        { label: 'Rapport Pipeline Commercial', type: 'pdf', prompt: 'Rapport pipeline commercial — prospects, opportunités en cours, taux conversion, prévisions CA, entonnoir de vente', icon: '🔮' },
        { label: 'Dashboard Commercial Excel', type: 'excel', prompt: 'Tableau de bord commercial Excel — CA par agent/courtier, objectifs, taux atteinte, classement, commissions', icon: '📊' },
        { label: 'Analyse Ventes (PPTX)', type: 'pptx', prompt: 'Présentation analyse ventes — performances équipe, top produits, zones géographiques, plan d\'action', icon: '🎤' },
      ],
    },
    {
      categorie: 'Courtiers & Partenaires', couleur: 'bg-yellow-50 border-yellow-200', iconeCat: '🤝',
      templates: [
        { label: 'Rapport Courtiers', type: 'excel', prompt: 'Rapport production courtiers — CA par courtier, commissions, portefeuille, sinistralité, classement mensuel', icon: '💼' },
        { label: 'Analyse Canaux Distribution', type: 'pdf', prompt: 'Analyse canaux de distribution — direct vs intermédiaires, coût acquisition, rentabilité par canal', icon: '🔀' },
      ],
    },
  ],
  cima: [
    {
      categorie: 'États Réglementaires CIMA', couleur: 'bg-indigo-50 border-indigo-200', iconeCat: '⚖️',
      templates: [
        { label: 'Rapport Conformité Annuel', type: 'pdf', prompt: 'Rapport conformité CIMA annuel — tous ratios prudentiels, états C1-C20, provisions, alertes, plan correctif', icon: '📋' },
        { label: 'États C1-C20 Excel', type: 'excel', prompt: 'Tous les états réglementaires CIMA C1 à C20 — format transmission CRCA, ratios, provisions, marges', icon: '📊' },
        { label: 'Présentation CRCA (PPTX)', type: 'pptx', prompt: 'Présentation pour la CRCA — résultats prudentiels, points d\'attention, plan d\'action réglementaire', icon: '🏛️' },
      ],
    },
    {
      categorie: 'Provisions & Solvabilité', couleur: 'bg-blue-50 border-blue-200', iconeCat: '🏦',
      templates: [
        { label: 'Analyse Marge Solvabilité', type: 'pdf', prompt: 'Analyse marge de solvabilité Art. 337 CIMA — calcul, respect minimum 100%, comparatif secteur, recommandations', icon: '📐' },
        { label: 'Rapport Provisions Techniques', type: 'pdf', prompt: 'Rapport provisions techniques — PSAP, IBNR, PM vie, provisions mathématiques, conformité Art. 334 CIMA', icon: '🔐' },
      ],
    },
  ],
  courtiers: [
    {
      categorie: 'Production & Commissions', couleur: 'bg-orange-50 border-orange-200', iconeCat: '💼',
      templates: [
        { label: 'Rapport Commissions', type: 'excel', prompt: 'Rapport commissions courtiers — commissions dues par produit/branche, encaissées, en attente, historique', icon: '💰' },
        { label: 'Classement Production', type: 'pdf', prompt: 'Classement production courtiers — top 10, CA mensuel/annuel, taux progression, portefeuille géré, sinistralité', icon: '🏆' },
        { label: 'Analyse Rentabilité Courtiers', type: 'excel', prompt: 'Analyse rentabilité par courtier — ratio commissions/primes, sinistralité apportée, marge nette, scoring', icon: '📊' },
      ],
    },
  ],
}

// ─── Exemples de prompts par module ──────────────────────────────────────────

const EXEMPLES: Partial<Record<ModuleRapport, string[]>> = {
  general: [
    'Génère un rapport mensuel sinistres Auto avec analyse S/P et provisions PSAP',
    'Crée une présentation PowerPoint résultats Q1 avec KPIs et graphiques',
    'Produis un tableau Excel de tous les états CIMA C1-C20 pour la CRCA',
  ],
  sinistres: [
    'Rapport sinistres automobiles du mois avec fraudes détectées et ratio S/P',
    'Analyse des sinistres corporels — IPP, délais, litiges pendants',
    'Tableau Excel sinistres ouverts par expert avec âge moyen du dossier',
  ],
  comptabilite: [
    'Bilan OHADA au 31 mars avec provisions techniques assurance',
    'Balance générale avec codes SYSCOA et mouvements du trimestre',
    'Rapport trésorerie — flux, soldes, alertes liquidité pour la DG',
  ],
  rh: [
    'Rapport KPI mensuel — classement performance, scores, recommandations primes',
    'Analyse masse salariale Q1 par département avec comparatif N-1',
    'Bilan formation — compétences acquises, coûts, retour sur investissement',
  ],
  reassurance: [
    'État C12 CIMA réassurance pour le dernier exercice',
    'Bordereau Excel primes cédées par traité et réassureur',
    'Analyse programme réassurance — coût/bénéfice, taux de cession optimaux',
  ],
  souscription: [
    'Rapport portefeuille mensuel — nouvelles polices, résiliations, taux rétention',
    'Analyse tarification branche Auto — prime technique vs marché',
    'Suivi renouvellements — polices expirant dans 30 jours avec primes',
  ],
  commercial: [
    'Dashboard commercial Excel — CA, objectifs, classement agents du mois',
    'Rapport pipeline commercial — prospects chauds, taux conversion, prévisions',
    'Analyse distribution — rentabilité par canal, courtiers top 10',
  ],
  cima: [
    'Rapport conformité CIMA annuel avec tous les ratios prudentiels',
    'États C1-C20 format Excel prêt pour transmission à la CRCA',
    'Analyse marge solvabilité — Art. 337, comparatif secteur, recommandations',
  ],
  courtiers: [
    'Classement production courtiers du mois avec commissions calculées',
    'Analyse rentabilité par courtier — sinistralité apportée vs commissions',
    'Rapport commissions en attente — montants, échéances, courtiers',
  ],
}

// ─── Couleurs par type de document ───────────────────────────────────────────

const COULEUR_TYPE: Record<string, string> = {
  pdf: 'border-red-300 bg-red-50 text-red-700',
  docx: 'border-blue-300 bg-blue-50 text-blue-700',
  pptx: 'border-orange-300 bg-orange-50 text-orange-700',
  excel: 'border-green-300 bg-green-50 text-green-700',
}

interface SSEProgress { etape: string; progression: number; detail?: string }

interface HistoriqueDoc { id: string; nom: string; type: string; date: string; taille: string }

const HISTORIQUE_DEMO: HistoriqueDoc[] = [
  { id: '1', nom: 'rapport_conformite_cima_mars_2026.pdf', type: 'pdf', date: '2026-03-28 14:32', taille: '2.4 MB' },
  { id: '2', nom: 'presentation_ca_q1_2026.pptx', type: 'pptx', date: '2026-03-25 09:15', taille: '8.1 MB' },
  { id: '3', nom: 'dashboard_sinistres_fev_2026.xlsx', type: 'excel', date: '2026-03-12 16:05', taille: '1.8 MB' },
  { id: '4', nom: 'rapport_psap_2025.pdf', type: 'pdf', date: '2026-03-01 11:20', taille: '3.2 MB' },
  { id: '5', nom: 'etat_c12_reassurance_2026.pdf', type: 'pdf', date: '2026-02-28 17:45', taille: '1.1 MB' },
]

// ─── Composant principal ──────────────────────────────────────────────────────

interface RapportsModuleProps {
  module: ModuleRapport
  /** Pré-remplir le contexte (ex: référence sinistre) */
  contexteInitial?: string
}

export function RapportsModule({ module, contexteInitial }: RapportsModuleProps) {
  const [onglet, setOnglet] = useState<'generer' | 'templates' | 'historique'>('templates')
  const [isGenerating, setIsGenerating] = useState(false)
  const [generatedDoc, setGeneratedDoc] = useState<{ url?: string; nom_fichier?: string; type?: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sseProgress, setSseProgress] = useState<SSEProgress | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const templates = TEMPLATES[module] ?? TEMPLATES.general
  const exemples = EXEMPLES[module] ?? EXEMPLES.general ?? []

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { type_document: 'pdf', contexte: contexteInitial || '' },
  })
  const selectedType = watch('type_document')

  useEffect(() => { return () => eventSourceRef.current?.close() }, [])

  const iconeType = (type: string) => {
    const icons: Record<string, React.ReactNode> = {
      pdf: <DocumentIcon className="w-4 h-4 text-red-500" />,
      docx: <DocumentTextIcon className="w-4 h-4 text-blue-500" />,
      pptx: <PresentationChartBarIcon className="w-4 h-4 text-orange-500" />,
      excel: <TableCellsIcon className="w-4 h-4 text-green-500" />,
    }
    return icons[type] || <DocumentTextIcon className="w-4 h-4 text-gray-500" />
  }

  const generer = async (payload: FormValues) => {
    setIsGenerating(true)
    setError(null)
    setGeneratedDoc(null)
    setSseProgress({ etape: 'Initialisation', progression: 5 })

    const token = localStorage.getItem('access_token')
    try {
      const params = new URLSearchParams({
        prompt: payload.prompt,
        type_document: payload.type_document,
        contexte: payload.contexte || '',
        token: token || '',
      })
      const es = new EventSource(`${BASE_URL}/api/v1/streaming/generer-document?${params}`)
      eventSourceRef.current = es

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'progress') setSseProgress({ etape: data.etape, progression: data.progression, detail: data.detail })
          else if (data.type === 'complete') { setGeneratedDoc(data.document); setSseProgress(null); setIsGenerating(false); es.close() }
          else if (data.type === 'error') { setError(data.message); setSseProgress(null); setIsGenerating(false); es.close() }
        } catch { /* ignore */ }
      }
      es.onerror = async () => {
        es.close()
        try {
          const result = await documentsAPI.generer(payload)
          setGeneratedDoc(result as { url?: string; nom_fichier?: string; type?: string })
        } catch (err: unknown) {
          const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          setError(msg || 'Erreur lors de la génération.')
        } finally { setSseProgress(null); setIsGenerating(false) }
      }
    } catch { setError('Impossible de lancer la génération.'); setSseProgress(null); setIsGenerating(false) }
  }

  const utiliserTemplate = (t: Template) => {
    setValue('type_document', t.type)
    setValue('prompt', t.prompt)
    setOnglet('generer')
  }

  return (
    <div className="space-y-4">
      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <SparklesIcon className="w-5 h-5 text-primary-600" />
            Génération de rapports IA
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">PDF · Word · PowerPoint · Excel — Powered by Claude + Python</p>
        </div>
      </div>

      {/* Onglets */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-4">
          {[
            { key: 'templates', label: 'Templates', icon: PresentationChartBarIcon },
            { key: 'generer', label: 'Génération libre', icon: SparklesIcon },
            { key: 'historique', label: `Historique (${HISTORIQUE_DEMO.length})`, icon: ClockIcon },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setOnglet(t.key as typeof onglet)}
              className={`flex items-center gap-1.5 pb-2.5 text-sm font-medium border-b-2 transition-colors ${
                onglet === t.key ? 'border-primary-600 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Templates ──────────────────────────────────────────────────────── */}
      {onglet === 'templates' && (
        <div className="space-y-5">
          {templates.map(cat => (
            <div key={cat.categorie} className={`rounded-xl border p-4 ${cat.couleur}`}>
              <h3 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                <span>{cat.iconeCat}</span>{cat.categorie}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {cat.templates.map(t => (
                  <button
                    key={t.label}
                    onClick={() => utiliserTemplate(t)}
                    className="bg-white rounded-xl border border-gray-200 p-3.5 text-left hover:border-primary-400 hover:shadow-md transition-all group"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-lg">{t.icon}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${COULEUR_TYPE[t.type]}`}>{t.type.toUpperCase()}</span>
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

      {/* ── Génération libre ───────────────────────────────────────────────── */}
      {onglet === 'generer' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Formulaire */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <form onSubmit={handleSubmit(generer)} className="space-y-4">
              {/* Format */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Format de sortie</label>
                <div className="grid grid-cols-2 gap-2">
                  {([
                    { value: 'pdf', label: 'PDF', icon: '📄' },
                    { value: 'docx', label: 'Word', icon: '📝' },
                    { value: 'pptx', label: 'PowerPoint', icon: '📊' },
                    { value: 'excel', label: 'Excel', icon: '📈' },
                  ] as { value: FormValues['type_document']; label: string; icon: string }[]).map(({ value, label, icon }) => (
                    <label key={value} className={clsx('flex items-center gap-2 border-2 rounded-xl p-3 cursor-pointer transition-all', selectedType === value ? COULEUR_TYPE[value] + ' border-current' : 'border-gray-200 hover:border-gray-300 bg-white')}>
                      <input type="radio" value={value} {...register('type_document')} className="hidden" />
                      <span className="text-lg">{icon}</span>
                      <span className="text-sm font-medium">{label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Prompt */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Description du rapport</label>
                <textarea {...register('prompt')} rows={4} placeholder="Décrivez le rapport souhaité en détail..." className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 outline-none resize-none" />
                {errors.prompt && <p className="text-xs text-red-600 mt-1">{errors.prompt.message}</p>}
              </div>

              {/* Contexte */}
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1.5">Contexte <span className="text-gray-400">(optionnel)</span></label>
                <input {...register('contexte')} placeholder="Compagnie, exercice, branche…" className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:border-primary-500 outline-none" />
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700 flex items-start gap-2">
                  <XMarkIcon className="w-4 h-4 flex-shrink-0 mt-0.5" />{error}
                </div>
              )}

              <button type="submit" disabled={isGenerating} className="w-full flex items-center justify-center gap-2 bg-primary-600 text-white rounded-xl py-3 text-sm font-semibold hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed transition-all shadow-md shadow-primary-600/20">
                {isGenerating
                  ? <><ArrowPathIcon className="w-4 h-4 animate-spin" /> Génération en cours…</>
                  : <><SparklesIcon className="w-5 h-5" /> Générer le rapport</>
                }
              </button>
            </form>

            {/* Exemples */}
            <div className="mt-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Exemples pour ce module</p>
              <div className="space-y-1.5">
                {exemples.map((ex, i) => (
                  <button key={i} onClick={() => setValue('prompt', ex)} className="w-full text-left text-xs text-gray-600 bg-gray-50 hover:bg-gray-100 rounded-lg px-3 py-2 transition-colors flex items-start gap-2">
                    <ChevronRightIcon className="w-3 h-3 mt-0.5 flex-shrink-0 text-gray-400" />{ex}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Résultat */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 flex flex-col">
            <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
              <DocumentTextIcon className="h-4 w-4 text-primary-600" />Aperçu du document
            </h3>

            {isGenerating && (
              <div className="flex-1 flex flex-col items-center justify-center">
                <div className="w-full max-w-xs">
                  {sseProgress && (
                    <>
                      <div className="flex justify-between text-xs text-gray-600 mb-2">
                        <span>{sseProgress.etape}</span><span>{sseProgress.progression}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2 mb-3">
                        <div className="bg-primary-500 h-2 rounded-full transition-all duration-500" style={{ width: `${sseProgress.progression}%` }} />
                      </div>
                      {sseProgress.detail && <p className="text-xs text-gray-400 text-center">{sseProgress.detail}</p>}
                    </>
                  )}
                  <div className="flex items-center justify-center gap-2 mt-4">
                    <ArrowPathIcon className="w-5 h-5 animate-spin text-primary-500" />
                    <span className="text-sm text-gray-500">YukpoPro génère votre document…</span>
                  </div>
                </div>
              </div>
            )}

            {!isGenerating && generatedDoc && (
              <div className="flex-1 flex flex-col gap-4">
                <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    {iconeType(generatedDoc.type || 'pdf')}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-green-800">Rapport prêt !</p>
                    <p className="text-xs text-green-600 mt-0.5">{generatedDoc.nom_fichier}</p>
                  </div>
                </div>
                {generatedDoc.url && (
                  <>
                    {generatedDoc.type === 'pdf' && (
                      <div className="flex-1 min-h-64 border border-gray-200 rounded-xl overflow-hidden">
                        <iframe src={`${BASE_URL}${generatedDoc.url}`} className="w-full h-full min-h-64" title="Aperçu PDF" />
                      </div>
                    )}
                    <a href={`${BASE_URL}${generatedDoc.url}`} download={generatedDoc.nom_fichier} className="flex items-center justify-center gap-2 bg-primary-600 text-white rounded-xl py-3 text-sm font-medium hover:bg-primary-700 transition-colors">
                      <ArrowDownTrayIcon className="h-4 w-4" />Télécharger — {generatedDoc.nom_fichier}
                    </a>
                  </>
                )}
              </div>
            )}

            {!isGenerating && !generatedDoc && (
              <div className="flex-1 flex flex-col items-center justify-center text-center py-10">
                <div className="w-14 h-14 bg-gray-100 rounded-2xl flex items-center justify-center mb-4">
                  <DocumentTextIcon className="h-7 w-7 text-gray-400" />
                </div>
                <p className="text-sm text-gray-500">Le rapport généré apparaîtra ici</p>
                <p className="text-xs text-gray-400 mt-1">Choisissez un template ou décrivez votre rapport</p>
                <div className="mt-5 grid grid-cols-2 gap-2.5 text-xs text-gray-400">
                  {['Thèmes couleur pro', 'KPI cards auto', 'Graphiques Python', 'Export haute qualité'].map(f => (
                    <div key={f} className="flex items-center gap-1.5"><span className="text-green-400">✓</span> {f}</div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Historique ─────────────────────────────────────────────────────── */}
      {onglet === 'historique' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-800">Rapports générés récemment</h3>
            <button className="text-xs text-gray-500 hover:text-gray-700">Tout effacer</button>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Fichier</th>
                <th className="text-center px-4 py-2.5 text-xs font-medium text-gray-600">Type</th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Date</th>
                <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Taille</th>
                <th className="text-center px-4 py-2.5 text-xs font-medium text-gray-600">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {HISTORIQUE_DEMO.map((doc, i) => (
                <tr key={doc.id} className={`${i % 2 === 0 ? '' : 'bg-gray-50'} hover:bg-blue-50 transition-colors`}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">{iconeType(doc.type)}<span className="text-gray-800 font-medium text-xs">{doc.nom}</span></div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${COULEUR_TYPE[doc.type]}`}>{doc.type.toUpperCase()}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{doc.date}</td>
                  <td className="px-4 py-3 text-right text-gray-500 text-xs">{doc.taille}</td>
                  <td className="px-4 py-3 text-center">
                    <button className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-1 mx-auto">
                      <ArrowDownTrayIcon className="w-3.5 h-3.5" /> Télécharger
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
