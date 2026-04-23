import { useState } from 'react'
import {
  CalendarIcon, PlusIcon, ClockIcon, CheckCircleIcon, XMarkIcon,
  UserGroupIcon, DocumentTextIcon, SparklesIcon, BellIcon, ChevronRightIcon,
  VideoCameraIcon, MapPinIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { apiClient } from '../api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

type TypeReunion = 'comite_sinistres' | 'comite_direction' | 'formation_cima' | 'revue_vie' | 'revue_portefeuille' | 'autre'
type TypeRappel = 'echeance' | 'reunion' | 'tache' | 'cima' | 'sinistre'
type Priorite = 'haute' | 'normale' | 'basse'

interface Reunion {
  id: string
  titre: string
  type: TypeReunion
  date: string
  heure: string
  duree_min: number
  lieu: string
  participants: string[]
  ordre_du_jour: string[]
  statut: 'planifiee' | 'en_cours' | 'terminee' | 'annulee'
  cr_genere?: string
}

interface Rappel {
  id: string
  titre: string
  description: string
  date_heure: string
  type: TypeRappel
  priorite: Priorite
  statut: 'en_attente' | 'complete' | 'annule'
}

// ─── Données démo ─────────────────────────────────────────────────────────────

const DEMO_REUNIONS: Reunion[] = [
  {
    id: '1', titre: 'Comité de gestion des sinistres — Avril 2026', type: 'comite_sinistres',
    date: '2026-04-15', heure: '10:00', duree_min: 120,
    lieu: 'Salle de réunion A — Siège Douala',
    participants: ['DG', 'DT Sinistres', 'Experts', 'Juriste'],
    ordre_du_jour: [
      'Revue dossiers sinistres > 5M FCFA en cours',
      'Analyse score fraude — dossiers suspects',
      'Validation règlements sinistres auto Q1 2026',
      'Point sinistres vie : décès en attente de pièces',
    ],
    statut: 'planifiee',
  },
  {
    id: '2', titre: 'Formation CIMA — Nouvelles directives vie 2026', type: 'formation_cima',
    date: '2026-04-12', heure: '14:00', duree_min: 180,
    lieu: 'Visioconférence Teams',
    participants: ['DT Vie', 'Actuaires', 'Souscripteurs vie', 'DG'],
    ordre_du_jour: [
      'Nouvelles circulaires PM vie CIMA 2026',
      'Tables de mortalité CIMA-2016 vs TD/TV 88-90',
      'Calcul provisions mathématiques — méthode prospective',
      'État C11 vie : modifications de présentation',
    ],
    statut: 'terminee',
    cr_genere: `COMPTE RENDU — Formation CIMA Vie 2026\nDate : 12 Avril 2026\n\n1. Nouvelles circulaires PM vie :\nLes nouvelles directives prévoient une augmentation de 15% des provisions mathématiques pour les contrats de rente viagère. Mise en application au 30/06/2026.\n\n2. Tables de mortalité :\nAdoption recommandée des tables CIMA-2016 pour tous les nouveaux contrats vie. Les anciens contrats peuvent conserver TD/TV 88-90 jusqu'au renouvellement.\n\n3. Provisions mathématiques :\nLa méthode prospective reste obligatoire. Taux technique maximum maintenu à 3,5% pour les contrats à prime fixe.\n\nActions décidées :\n- DT Vie : mise à jour du système de calcul avant le 01/05/2026\n- Actuaires : révision des provisions pour les 47 contrats rente\n- DG : validation du plan de mise en conformité`,
  },
  {
    id: '3', titre: 'Revue portefeuille vie Q1 2026', type: 'revue_vie',
    date: '2026-04-20', heure: '09:00', duree_min: 90,
    lieu: 'Salle de réunion B',
    participants: ['DT Vie', 'Commercial', 'Actuaires'],
    ordre_du_jour: [
      'Performance portefeuille vie : primes émises vs objectifs',
      'Analyse des rachats et résiliations Q1',
      'Revue produits crédit-vie : partenariats bancaires',
      'Opportunités développement prévoyance collective',
    ],
    statut: 'planifiee',
  },
  {
    id: '4', titre: 'Comité de direction mensuel', type: 'comite_direction',
    date: '2026-04-30', heure: '08:30', duree_min: 120,
    lieu: 'Salle de Direction',
    participants: ['DG', 'DAF', 'DT', 'DRH', 'Commercial'],
    ordre_du_jour: [
      'Résultats financiers Q1 2026',
      'Ratio de solvabilité au 31/03/2026',
      'Point états réglementaires C1-C20 CRCA',
      'Stratégie développement assurance vie 2026-2027',
    ],
    statut: 'planifiee',
  },
]

const DEMO_RAPPELS: Rappel[] = [
  { id: '1', titre: 'Dépôt états C1-C20 CRCA', description: 'Délai légal 120 jours après clôture exercice 2025', date_heure: '2026-04-30T09:00:00', type: 'cima', priorite: 'haute', statut: 'en_attente' },
  { id: '2', titre: 'Renouvellement polices auto Q2', description: '23 contrats auto à échéance fin avril', date_heure: '2026-04-20T08:00:00', type: 'echeance', priorite: 'normale', statut: 'en_attente' },
  { id: '3', titre: 'Paiement sinistre SIN-2026-0042', description: 'Délai paiement sinistre auto — limite 45 jours Art. 12 CIMA', date_heure: '2026-04-11T17:00:00', type: 'sinistre', priorite: 'haute', statut: 'en_attente' },
  { id: '4', titre: 'Révision provisions mathématiques', description: 'Mise à jour PM vie Q1 selon nouvelles directives CIMA', date_heure: '2026-05-01T09:00:00', type: 'cima', priorite: 'haute', statut: 'en_attente' },
  { id: '5', titre: 'Encaissement primes vie trimestrielles', description: '18 contrats vie — cotisation T2 2026 à encaisser', date_heure: '2026-04-25T08:00:00', type: 'echeance', priorite: 'normale', statut: 'en_attente' },
  { id: '6', titre: 'Formation CIMA vie — suivi', description: 'Mise à jour des outils de calcul PM', date_heure: '2026-04-12T14:00:00', type: 'tache', priorite: 'normale', statut: 'complete' },
]

// ─── Config ───────────────────────────────────────────────────────────────────

const TYPE_REUNION: Record<TypeReunion, { label: string; icon: string; couleur: string }> = {
  comite_sinistres:   { label: 'Comité Sinistres',     icon: '🛡️', couleur: 'bg-red-100 text-red-700' },
  comite_direction:   { label: 'Comité de Direction',  icon: '🏢', couleur: 'bg-purple-100 text-purple-700' },
  formation_cima:     { label: 'Formation CIMA',        icon: '📚', couleur: 'bg-blue-100 text-blue-700' },
  revue_vie:          { label: 'Revue Vie & Épargne',   icon: '❤️', couleur: 'bg-emerald-100 text-emerald-700' },
  revue_portefeuille: { label: 'Revue Portefeuille',   icon: '📊', couleur: 'bg-orange-100 text-orange-700' },
  autre:              { label: 'Autre',                 icon: '📋', couleur: 'bg-gray-100 text-gray-700' },
}

const TYPE_RAPPEL_CONFIG: Record<TypeRappel, { label: string; couleur: string }> = {
  echeance: { label: 'Échéance', couleur: 'bg-orange-100 text-orange-700' },
  reunion:  { label: 'Réunion',  couleur: 'bg-blue-100 text-blue-700' },
  tache:    { label: 'Tâche',    couleur: 'bg-gray-100 text-gray-700' },
  cima:     { label: 'CIMA',     couleur: 'bg-purple-100 text-purple-700' },
  sinistre: { label: 'Sinistre', couleur: 'bg-red-100 text-red-700' },
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDateRelative(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = Math.ceil((date.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  if (diff < 0) return `Il y a ${Math.abs(diff)}j`
  if (diff === 0) return "Aujourd'hui"
  if (diff === 1) return 'Demain'
  if (diff <= 7) return `Dans ${diff} jours`
  return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

// ─── CR Génération IA ─────────────────────────────────────────────────────────

function CRModal({ reunion, onClose }: { reunion: Reunion; onClose: () => void }) {
  const [loading, setLoading] = useState(!reunion.cr_genere)
  const [cr, setCr] = useState(reunion.cr_genere || '')

  const generer = async () => {
    setLoading(true)
    try {
      const { data } = await apiClient.post('/api/v1/chat/message', {
        session_id: 'cr-generation',
        message: `Génère un compte rendu de réunion complet et professionnel pour :\n
Titre : ${reunion.titre}
Date : ${reunion.date} à ${reunion.heure}
Lieu : ${reunion.lieu}
Participants : ${reunion.participants.join(', ')}
Ordre du jour :
${reunion.ordre_du_jour.map((p, i) => `${i + 1}. ${p}`).join('\n')}

Le CR doit inclure : résumé des discussions, décisions prises, actions à suivre avec responsables et délais, prochaine réunion suggérée. Format professionnel assurance CIMA.`,
      })
      const d = data as Record<string, unknown>
      const msg = d.message as Record<string, unknown> | undefined
      setCr((msg?.content as string) || (d.content as string) || genererDemoCR(reunion))
    } catch {
      setCr(genererDemoCR(reunion))
    }
    setLoading(false)
  }

  if (!reunion.cr_genere && !cr) {
    generer()
  }

  const telecharger = () => {
    const blob = new Blob([cr], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `CR_${reunion.titre.replace(/\s+/g, '_')}_${reunion.date}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between p-5 border-b">
          <div>
            <h3 className="font-bold text-gray-900">Compte Rendu — IA</h3>
            <p className="text-xs text-gray-500">{reunion.titre}</p>
          </div>
          <div className="flex items-center gap-2">
            {cr && (
              <button onClick={telecharger}
                className="text-xs px-3 py-1.5 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-1">
                <DocumentTextIcon className="h-3.5 w-3.5" /> Télécharger
              </button>
            )}
            <button onClick={onClose} aria-label="Fermer" className="p-1.5 text-gray-400 hover:text-gray-600">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex flex-col items-center py-12 space-y-3">
              <SparklesIcon className="h-8 w-8 text-primary-500 animate-pulse" />
              <p className="text-sm font-medium text-gray-700">YukpoPro rédige le compte rendu…</p>
              <p className="text-xs text-gray-400">Analyse de l'ordre du jour et génération du CR en cours</p>
            </div>
          ) : (
            <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">{cr}</pre>
          )}
        </div>
      </div>
    </div>
  )
}

function genererDemoCR(r: Reunion): string {
  const date = new Date(r.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
  return `COMPTE RENDU DE RÉUNION
${r.titre}

📅 Date : ${date} à ${r.heure}
📍 Lieu : ${r.lieu}
👥 Participants : ${r.participants.join(', ')}

═══════════════════════════════════════

ORDRE DU JOUR ET DISCUSSIONS

${r.ordre_du_jour.map((point, i) => `${i + 1}. ${point}
   → Discussion approfondie des équipes concernées.
   → Consensus obtenu sur les orientations à suivre.
   → Points d'attention relevés et documentés.
`).join('\n')}

═══════════════════════════════════════

DÉCISIONS PRISES

${r.ordre_du_jour.map((point, i) => `• Point ${i + 1} — ${point.split(':')[0]} : validé et documenté pour mise en œuvre immédiate.`).join('\n')}

═══════════════════════════════════════

ACTIONS À SUIVRE

| Responsable      | Action                              | Délai         |
|------------------|-------------------------------------|---------------|
${r.participants.slice(0, 3).map(p => `| ${p.padEnd(16)} | Mise en œuvre des décisions point ${r.ordre_du_jour.indexOf(r.ordre_du_jour[r.participants.indexOf(p) % r.ordre_du_jour.length]) + 1} | J+15          |`).join('\n')}

═══════════════════════════════════════

PROCHAINE RÉUNION

Suggérée dans 30 jours — même participants.
Ordre du jour à définir en fonction de l'avancement des actions.

CR rédigé automatiquement par YukpoPro — à valider par le secrétaire de séance.`
}

// ─── Formulaire nouvelle réunion ──────────────────────────────────────────────

function NouvelleReunionForm({ onSave, onClose }: {
  onSave: (r: Reunion) => void
  onClose: () => void
}) {
  const [form, setForm] = useState({
    titre: '', type: 'comite_sinistres' as TypeReunion,
    date: '', heure: '09:00', duree_min: 60, lieu: '',
    participants: '', points: '',
  })

  const handleSave = () => {
    const r: Reunion = {
      id: Date.now().toString(),
      titre: form.titre,
      type: form.type,
      date: form.date,
      heure: form.heure,
      duree_min: form.duree_min,
      lieu: form.lieu,
      participants: form.participants.split(',').map(s => s.trim()).filter(Boolean),
      ordre_du_jour: form.points.split('\n').filter(Boolean),
      statut: 'planifiee',
    }
    onSave(r)
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b">
          <h3 className="font-bold text-gray-900">Planifier une réunion</h3>
          <button onClick={onClose} aria-label="Fermer" className="p-1.5 text-gray-400 hover:text-gray-600"><XMarkIcon className="h-5 w-5" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Titre de la réunion</label>
            <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
              value={form.titre} onChange={e => setForm(p => ({ ...p, titre: e.target.value }))}
              placeholder="Comité sinistres mensuel Avril 2026" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Type</label>
              <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                value={form.type} onChange={e => setForm(p => ({ ...p, type: e.target.value as TypeReunion }))}>
                {Object.entries(TYPE_REUNION).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Durée (min)</label>
              <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                value={form.duree_min} onChange={e => setForm(p => ({ ...p, duree_min: Number(e.target.value) }))}>
                {[30, 60, 90, 120, 180, 240].map(d => <option key={d} value={d}>{d} min</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Date</label>
              <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                value={form.date} onChange={e => setForm(p => ({ ...p, date: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Heure</label>
              <input type="time" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                value={form.heure} onChange={e => setForm(p => ({ ...p, heure: e.target.value }))} />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Lieu / Lien visio</label>
            <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
              value={form.lieu} onChange={e => setForm(p => ({ ...p, lieu: e.target.value }))}
              placeholder="Salle A ou https://teams.microsoft.com/..." />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Participants (séparés par virgule)</label>
            <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
              value={form.participants} onChange={e => setForm(p => ({ ...p, participants: e.target.value }))}
              placeholder="DG, DT Sinistres, Experts, Juriste" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Ordre du jour (un point par ligne)</label>
            <textarea rows={4}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 resize-none"
              value={form.points} onChange={e => setForm(p => ({ ...p, points: e.target.value }))}
              placeholder={"Revue sinistres > 5M FCFA\nAnalyse fraude Q1\nValidation règlements"} />
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={onClose} className="flex-1 border border-gray-300 rounded-lg py-2 text-sm text-gray-600 hover:bg-gray-50">
              Annuler
            </button>
            <button
              onClick={handleSave}
              disabled={!form.titre || !form.date}
              className="flex-1 bg-primary-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              Planifier la réunion
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Page principale ──────────────────────────────────────────────────────────

type Onglet = 'reunions' | 'rappels'

export default function AgendaPage() {
  const [onglet, setOnglet] = useState<Onglet>('reunions')
  const [reunions, setReunions] = useState<Reunion[]>(DEMO_REUNIONS)
  const [rappels, setRappels] = useState<Rappel[]>(DEMO_RAPPELS)
  const [showNouvelle, setShowNouvelle] = useState(false)
  const [crReunion, setCrReunion] = useState<Reunion | null>(null)

  const planifiees = reunions.filter(r => r.statut === 'planifiee').sort((a, b) => a.date.localeCompare(b.date))
  const terminees = reunions.filter(r => r.statut === 'terminee')
  const rappelsEnAttente = rappels.filter(r => r.statut === 'en_attente').sort((a, b) => a.date_heure.localeCompare(b.date_heure))
  const rappelsHaute = rappelsEnAttente.filter(r => r.priorite === 'haute')

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Réunions & Agenda</h1>
          <p className="text-sm text-gray-500 mt-0.5">CR automatique IA · Suivi actions · Rappels CIMA</p>
        </div>
        <button
          onClick={() => setShowNouvelle(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700 shadow-sm transition-colors"
        >
          <PlusIcon className="h-4 w-4" /> Planifier une réunion
        </button>
      </div>

      {/* Stats rapides */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border p-4 text-center">
          <p className="text-2xl font-bold text-gray-900">{planifiees.length}</p>
          <p className="text-xs text-gray-500">Réunions à venir</p>
        </div>
        <div className={clsx('rounded-xl border p-4 text-center', rappelsHaute.length > 0 ? 'bg-red-50 border-red-200' : 'bg-white')}>
          <p className={clsx('text-2xl font-bold', rappelsHaute.length > 0 ? 'text-red-700' : 'text-gray-900')}>{rappelsHaute.length}</p>
          <p className={clsx('text-xs', rappelsHaute.length > 0 ? 'text-red-600' : 'text-gray-500')}>Alertes prioritaires</p>
        </div>
        <div className="bg-white rounded-xl border p-4 text-center">
          <p className="text-2xl font-bold text-gray-900">{terminees.length}</p>
          <p className="text-xs text-gray-500">Réunions terminées</p>
        </div>
      </div>

      {/* Onglets */}
      <div className="flex rounded-xl border border-gray-200 bg-gray-50 p-1 w-fit">
        {([['reunions', 'Réunions', UserGroupIcon], ['rappels', 'Rappels & Échéances', BellIcon]] as const).map(([key, label, Icon]) => (
          <button key={key} onClick={() => setOnglet(key)}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              onglet === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
            <Icon className="h-4 w-4" />
            {label}
            {key === 'rappels' && rappelsHaute.length > 0 && (
              <span className="bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
                {rappelsHaute.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Contenu onglet Réunions */}
      {onglet === 'reunions' && (
        <div className="space-y-6">
          {/* Réunions planifiées */}
          {planifiees.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-semibold text-gray-700">À venir</h2>
              {planifiees.map(r => {
                const cfg = TYPE_REUNION[r.type]
                return (
                  <div key={r.id} className="bg-white border border-gray-200 rounded-xl p-4 hover:border-primary-200 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3 min-w-0">
                        <span className="text-xl flex-shrink-0 mt-0.5">{cfg.icon}</span>
                        <div className="min-w-0">
                          <p className="font-semibold text-gray-900 text-sm">{r.titre}</p>
                          <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 flex-wrap">
                            <span className="flex items-center gap-1">
                              <CalendarIcon className="h-3.5 w-3.5" />
                              {new Date(r.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })} à {r.heure}
                            </span>
                            <span className="flex items-center gap-1">
                              <ClockIcon className="h-3.5 w-3.5" />
                              {r.duree_min} min
                            </span>
                            <span className="flex items-center gap-1">
                              {r.lieu.startsWith('http') ? <VideoCameraIcon className="h-3.5 w-3.5" /> : <MapPinIcon className="h-3.5 w-3.5" />}
                              {r.lieu.startsWith('http') ? 'Visioconférence' : r.lieu}
                            </span>
                          </div>
                          <div className="flex items-center gap-1 mt-2 flex-wrap">
                            {r.participants.slice(0, 4).map(p => (
                              <span key={p} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{p}</span>
                            ))}
                            {r.participants.length > 4 && (
                              <span className="text-xs text-gray-400">+{r.participants.length - 4}</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2 flex-shrink-0">
                        <span className="text-xs font-medium text-primary-600 bg-primary-50 px-2 py-0.5 rounded-full">
                          {formatDateRelative(r.date)}
                        </span>
                        <span className={clsx('text-xs px-2 py-0.5 rounded-full', cfg.couleur)}>
                          {cfg.label}
                        </span>
                      </div>
                    </div>
                    {/* Ordre du jour preview */}
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <p className="text-xs text-gray-400 mb-1">Ordre du jour</p>
                      <div className="space-y-0.5">
                        {r.ordre_du_jour.slice(0, 2).map((p, i) => (
                          <p key={i} className="text-xs text-gray-600">• {p}</p>
                        ))}
                        {r.ordre_du_jour.length > 2 && (
                          <p className="text-xs text-gray-400">+ {r.ordre_du_jour.length - 2} autres points</p>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Réunions terminées */}
          {terminees.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-semibold text-gray-700">Terminées — CR disponibles</h2>
              {terminees.map(r => {
                const cfg = TYPE_REUNION[r.type]
                return (
                  <div key={r.id} className="bg-gray-50 border border-gray-200 rounded-xl p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-xl flex-shrink-0">{cfg.icon}</span>
                        <div className="min-w-0">
                          <p className="font-medium text-gray-700 text-sm truncate">{r.titre}</p>
                          <p className="text-xs text-gray-400">
                            {new Date(r.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}
                            {' · '}{r.participants.length} participants
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={clsx('text-xs px-2 py-0.5 rounded-full', cfg.couleur)}>{cfg.label}</span>
                        <button
                          onClick={() => setCrReunion(r)}
                          className="flex items-center gap-1.5 text-xs text-primary-600 hover:text-primary-700 bg-primary-50 hover:bg-primary-100 px-3 py-1.5 rounded-lg transition-colors font-medium"
                        >
                          <SparklesIcon className="h-3.5 w-3.5" />
                          {r.cr_genere ? 'Voir CR' : 'Générer CR'}
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Contenu onglet Rappels */}
      {onglet === 'rappels' && (
        <div className="space-y-3">
          {rappelsHaute.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-red-700 flex items-center gap-1">
                <BellIcon className="h-3.5 w-3.5" /> Alertes prioritaires
              </p>
              {rappelsHaute.map(r => {
                const cfg = TYPE_RAPPEL_CONFIG[r.type]
                return (
                  <div key={r.id} className="flex items-start justify-between gap-3 bg-white border border-red-100 rounded-lg p-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-gray-900">{r.titre}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{r.description}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <span className={clsx('text-xs px-2 py-0.5 rounded-full', cfg.couleur)}>{cfg.label}</span>
                      <span className="text-xs font-medium text-red-600">{formatDateRelative(r.date_heure)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {rappelsEnAttente.filter(r => r.priorite !== 'haute').map(r => {
            const cfg = TYPE_RAPPEL_CONFIG[r.type]
            return (
              <div key={r.id} className="flex items-start justify-between gap-3 bg-white border border-gray-200 rounded-xl p-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900">{r.titre}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{r.description}</p>
                </div>
                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full', cfg.couleur)}>{cfg.label}</span>
                  <span className="text-xs text-gray-500">{formatDateRelative(r.date_heure)}</span>
                  <button
                    onClick={() => setRappels(prev => prev.map(p => p.id === r.id ? { ...p, statut: 'complete' } : p))}
                    className="text-xs text-green-600 hover:text-green-700 flex items-center gap-1"
                  >
                    <CheckCircleIcon className="h-3.5 w-3.5" /> Marquer fait
                  </button>
                </div>
              </div>
            )
          })}

          {rappels.filter(r => r.statut === 'complete').length > 0 && (
            <p className="text-xs text-gray-400 text-center pt-2">
              {rappels.filter(r => r.statut === 'complete').length} rappel(s) complété(s) ce mois
            </p>
          )}
        </div>
      )}

      {/* Modals */}
      {crReunion && <CRModal reunion={crReunion} onClose={() => setCrReunion(null)} />}
      {showNouvelle && (
        <NouvelleReunionForm
          onSave={r => { setReunions(prev => [r, ...prev]); setShowNouvelle(false) }}
          onClose={() => setShowNouvelle(false)}
        />
      )}
    </div>
  )
}
