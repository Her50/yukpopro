/**
 * AgentSelector — Sélecteur du type d'agent (auto-détection ou manuel).
 */
import { CpuChipIcon as Bot, ChevronDownIcon as ChevronDown } from '@heroicons/react/24/outline'
import { useState } from 'react'
import type { AgentType } from '../../store/agentStore'

const AGENTS: { value: AgentType; label: string; emoji: string; description: string }[] = [
  { value: 'auto', label: 'Auto-détection', emoji: '🤖', description: 'L\'agent est sélectionné automatiquement' },
  { value: 'sinistres', label: 'Sinistres & Fraude', emoji: '🚗', description: 'Instruction, règlement, fraude' },
  { value: 'souscription', label: 'Souscription & Tarification', emoji: '📋', description: 'Police, prime, KYC, émission non-vie' },
  { value: 'vie', label: 'Assurance Vie & Prévoyance', emoji: '🫀', description: 'Épargne, retraite, décès, rachat, avances' },
  { value: 'conformite', label: 'Conformité CIMA', emoji: '📊', description: 'Ratios, états réglementaires, audit' },
  { value: 'commercial', label: 'Commercial & Apporteurs', emoji: '💼', description: 'CRM, commissions, rétention' },
  { value: 'rh', label: 'RH & Organisation', emoji: '👥', description: 'Congés, paie, recrutement, formations' },
  { value: 'juridique', label: 'Juridique & Contentieux', emoji: '⚖️', description: 'Recours, mises en demeure, transactions' },
  { value: 'comptabilite', label: 'Comptabilité & Finance', emoji: '💰', description: 'PCSA, rapprochement, clôtures' },
  { value: 'intelligence', label: 'Intelligence & Veille', emoji: '🔍', description: 'KPI, rapports direction, veille' },
  { value: 'reassurance', label: 'Réassurance & Cessions', emoji: '🔄', description: 'Traités, bordereaux, récupérations sinistres' },
  { value: 'placement', label: 'Placement & Actuariat', emoji: '📈', description: 'Portefeuille actifs, ALM, projections, stress tests' },
  { value: 'provisions', label: 'Provisions Techniques CIMA', emoji: '🧮', description: 'PPNA, PSAP, IBNR, PM, PPB, PTS, PREC — calcul et dotation' },
  { value: 'etats_cima', label: 'États Réglementés CIMA', emoji: '📑', description: 'Génération C1-C12, contrôle cohérence, soumission CRCA' },
  { value: 'schema_si',    label: 'Schéma & Connaissance SI',      emoji: '🔬', description: 'Introspection ORASS/Mercure, cartographie, correction accès agents' },
  { value: 'meta_factory', label: 'MetaFactory — Création d\'agents', emoji: '🏭', description: 'Détecte les workflows manquants, génère de nouveaux agents autonomes' },
  { value: 'deploiement_si', label: 'Déploiement SI', emoji: '🔌', description: 'Connecte YukpoAssurance au SI de la compagnie : ORASS, Mercure, Sage, API REST' },
  { value: 'maladie', label: 'Sinistres Maladie & Santé', emoji: '🏥', description: 'BPC, remboursements médicaux, hospitalisation, maternité, invalidité' },
  { value: 'sinistres_auto', label: 'Sinistres RC Auto', emoji: '🚦', description: 'Barème CIMA Art.200-264 : matériel (VRADE), corporel (DFP/ITT/pretium), décès, subrogation' },
  { value: 'risques_divers', label: 'Risques Divers', emoji: '🏗️', description: 'RC Pro, Dommages Ouvrage, ACI, Agriculture, Crédit/Caution, Protection Juridique, MRH, Assistance' },
]

interface Props {
  value: AgentType
  onChange: (v: AgentType) => void
}

export function AgentSelector({ value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const selected = AGENTS.find((a) => a.value === value) ?? AGENTS[0]

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-sm hover:border-indigo-300 transition-colors w-full"
      >
        <span>{selected.emoji}</span>
        <span className="font-medium text-gray-700">{selected.label}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-gray-400 ml-auto transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 right-0 mb-1 bg-white border border-gray-200 rounded-xl shadow-xl z-20 overflow-hidden">
            <div className="p-2 max-h-80 overflow-y-auto">
              {AGENTS.map((agent) => (
                <button
                  key={agent.value}
                  onClick={() => { onChange(agent.value); setOpen(false) }}
                  className={`w-full flex items-start gap-3 px-3 py-2 rounded-lg text-left hover:bg-indigo-50 transition-colors ${
                    agent.value === value ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700'
                  }`}
                >
                  <span className="text-lg mt-0.5">{agent.emoji}</span>
                  <div>
                    <div className="text-sm font-medium">{agent.label}</div>
                    <div className="text-xs text-gray-400">{agent.description}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
