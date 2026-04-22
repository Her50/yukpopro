import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { FileWithPath } from 'react-dropzone'
import {
  PaperAirplaneIcon, StopIcon, ArrowDownTrayIcon, PaperClipIcon,
  DocumentTextIcon, XMarkIcon,
} from '@heroicons/react/24/outline'
import { MessageBubble, TypingIndicator, StreamingBubble } from './MessageBubble'
import { FileUploadZone } from './FileUploadZone'
import { ChatMessage } from '../api/types'
import { clsx } from 'clsx'
import { useCompagnieStore } from '../store/compagnieStore'

// Catégories de questions rapides CIMA groupées par domaine
const SUGGESTIONS_RAPIDES = [
  {
    categorie: 'Auto & Transport',
    couleur: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100',
    questions: [
      'RC obligatoire auto : plafonds et exclusions CIMA',
      'Tous risques vs tiers simple : quelle différence ?',
      'CMR transport : calcul indemnité 8,33 DTS/kg',
      'Comment calculer une prime automobile ?',
    ],
  },
  {
    categorie: 'Vie & Prévoyance',
    couleur: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100',
    questions: [
      'Vie mixte : valeur de rachat Art. 75 CIMA',
      'Tables de mortalité TD/TV 88-90 vs CIMA-2016',
      'Différence capital-décès et rente viagère',
      'Crédit-vie : garanties et exclusions',
    ],
  },
  {
    categorie: 'Santé & Accidents',
    couleur: 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100',
    questions: [
      'Barèmes IPT/IPP : main, œil, bras, jambe',
      'Frais médicaux : niveaux économique, confort, prestige',
      'ITT : franchise et calcul indemnité journalière',
      'Prévoyance collective : couverture minimale CIMA',
    ],
  },
  {
    categorie: 'MRH & Entreprises',
    couleur: 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100',
    questions: [
      'MRH multirisque habitation : garanties de base',
      'Zones catnat Cameroun : rouge/orange/vert',
      'RC professionnelle médecin vs architecte',
      'Bris de machine : qu\'est-ce qui est couvert ?',
    ],
  },
  {
    categorie: 'Réglementation CIMA',
    couleur: 'bg-violet-50 text-violet-700 border-violet-200 hover:bg-violet-100',
    questions: [
      'États C1-C20 : quel état pour quel indicateur ?',
      'Calcul PSAP : méthodes dossier par dossier, chain-ladder',
      'Marge de solvabilité : ratio minimum et calcul',
      'Délais réglementaires règlement sinistres',
    ],
  },
  {
    categorie: 'Documents IA',
    couleur: 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100',
    questions: [
      'Génère une lettre de mise en demeure sinistre auto Art. 12 CIMA',
      'Rédige un avenant de modification de contrat vie',
      'Génère un PV de comité sinistres mensuel',
      'Rédige un rapport d\'expertise dommages MRH',
      'Génère une attestation de souscription auto',
      'Rédige un courrier de rejet sinistre avec motivation CIMA',
    ],
  },
]

interface ChatWindowProps {
  messages: ChatMessage[]
  isLoading: boolean
  isStreaming: boolean
  streamingContent: string
  onSendMessage: (content: string) => void
  onStopStream: () => void
}

export function ChatWindow({
  messages,
  isLoading,
  isStreaming,
  streamingContent,
  onSendMessage,
  onStopStream,
}: ChatWindowProps) {
  const [input, setInput] = useState('')
  const [showFileUpload, setShowFileUpload] = useState(false)
  const [showDocPanel, setShowDocPanel] = useState(false)
  const [files, setFiles] = useState<FileWithPath[]>([])
  const [categorieActive, setCategorieActive] = useState(0)
  const { branding } = useCompagnieStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const TYPES_DOC = [
    { label: 'Lettre sinistre', prompt: 'Génère une lettre de notification de sinistre à l\'assuré conforme CIMA' },
    { label: 'Avenant contrat', prompt: 'Génère un avenant de modification de contrat d\'assurance' },
    { label: 'Rapport expertise', prompt: 'Génère un rapport d\'expertise sinistre avec évaluation des dommages' },
    { label: 'PV comité', prompt: 'Génère un PV de comité de gestion des sinistres' },
    { label: 'Rejet sinistre', prompt: 'Génère une lettre de rejet de sinistre motivée selon le Code CIMA' },
    { label: 'Attestation auto', prompt: 'Génère une attestation d\'assurance automobile conforme CIMA' },
    { label: 'Note technique vie', prompt: 'Génère une note technique assurance vie : provisions mathématiques et calcul de prime' },
    { label: 'État C5 CIMA', prompt: 'Génère l\'état réglementaire C5 — provisions techniques toutes branches' },
  ]

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const handleSend = () => {
    if (!input.trim() || isLoading || isStreaming) return
    onSendMessage(input.trim())
    setInput('')
    setFiles([])
    setShowFileUpload(false)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const exportConversation = () => {
    const text = messages
      .map((m) => `[${m.role === 'user' ? 'Vous' : 'YukpoIA'}] ${m.content}`)
      .join('\n\n')
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `conversation-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200">
        <div className="flex items-center gap-3">
          {branding.logo_url && (
            <div className="w-7 h-7 rounded-lg overflow-hidden flex-shrink-0 border border-gray-100">
              <img src={branding.logo_url} alt={branding.nom} className="w-full h-full object-contain" />
            </div>
          )}
          <div>
            <h2 className="font-semibold text-gray-800">Yukpo IA — {branding.nom}</h2>
            <p className="text-xs text-gray-400">Intelligence Artificielle • Expert CIMA Vie & Non-Vie</p>
          </div>
        </div>
        {messages.length > 0 && (
          <button
            onClick={exportConversation}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-primary-600 transition-colors px-3 py-1.5 rounded-lg hover:bg-gray-100"
          >
            <ArrowDownTrayIcon className="h-4 w-4" />
            Exporter
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center w-full max-w-2xl mx-auto py-8 px-2">
            {/* Avatar compagnie */}
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4 shadow-lg overflow-hidden flex-shrink-0"
              style={{ backgroundColor: branding.logo_url ? 'white' : branding.couleur_primaire }}
            >
              {branding.logo_url ? (
                <img src={branding.logo_url} alt={branding.nom} className="w-full h-full object-contain p-1" />
              ) : (
                <span className="text-white text-2xl font-bold select-none">
                  {branding.nom.charAt(0).toUpperCase()}
                </span>
              )}
            </div>

            <h3 className="text-xl font-bold text-gray-800 mb-1">Bonjour, je suis YukpoIA</h3>
            <p className="text-sm text-gray-500 mb-1">
              Assistant IA spécialisé assurance — {branding.nom}
            </p>
            <p className="text-xs text-gray-400 mb-6 text-center max-w-sm">
              Je maîtrise l'ensemble du Code CIMA, toutes les garanties vie et non-vie,
              les états réglementaires C1-C20, le calcul des provisions et la gestion des sinistres.
            </p>

            {/* Onglets catégories */}
            <div className="flex flex-wrap gap-2 justify-center mb-4">
              {SUGGESTIONS_RAPIDES.map((cat, idx) => (
                <button
                  key={cat.categorie}
                  onClick={() => setCategorieActive(idx)}
                  className={clsx(
                    'px-3 py-1.5 rounded-full text-xs font-semibold border transition-all',
                    categorieActive === idx
                      ? 'bg-gray-800 text-white border-gray-800 shadow-sm'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400 hover:text-gray-800'
                  )}
                >
                  {cat.categorie}
                </button>
              ))}
            </div>

            {/* Questions de la catégorie active */}
            <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SUGGESTIONS_RAPIDES[categorieActive].questions.map((q) => (
                <button
                  key={q}
                  onClick={() => onSendMessage(q)}
                  className={clsx(
                    'text-left text-xs px-4 py-3 rounded-xl border font-medium transition-all',
                    SUGGESTIONS_RAPIDES[categorieActive].couleur
                  )}
                >
                  {q}
                </button>
              ))}
            </div>

            <p className="text-xs text-gray-300 mt-6">
              Ou saisissez votre propre question ci-dessous ↓
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isStreaming && streamingContent && <StreamingBubble content={streamingContent} />}
        {(isLoading && !isStreaming) && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Panel génération documents */}
      {showDocPanel && (
        <div className="px-4 py-3 bg-white border-t border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-600">Générer un document IA</span>
            <button onClick={() => setShowDocPanel(false)} className="text-gray-400 hover:text-gray-600">
              <XMarkIcon className="h-4 w-4" />
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {TYPES_DOC.map(d => (
              <button key={d.label}
                onClick={() => { onSendMessage(d.prompt); setShowDocPanel(false) }}
                className="text-xs px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 border border-slate-200 transition-colors"
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* File upload zone */}
      {showFileUpload && (
        <div className="px-4 py-2 bg-white border-t border-gray-200">
          <FileUploadZone
            onFilesAccepted={(f) => setFiles((prev) => [...prev, ...f])}
            currentFiles={files}
            onRemoveFile={(i) => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
          />
        </div>
      )}

      {/* Input */}
      <div className="bg-white border-t border-gray-200 p-4">
        <div className="flex items-end gap-2 rounded-xl border border-gray-300 bg-white px-3 py-2 focus-within:border-primary-500 focus-within:ring-1 focus-within:ring-primary-500 transition-all">
          <button
            type="button"
            onClick={() => setShowFileUpload((v) => !v)}
            title="Joindre un fichier / OCR"
            className={clsx(
              'p-1.5 rounded-lg transition-colors mb-0.5',
              showFileUpload ? 'text-primary-600 bg-primary-50' : 'text-gray-400 hover:text-gray-600'
            )}
          >
            <PaperClipIcon className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={() => setShowDocPanel((v) => !v)}
            title="Générer un document"
            className={clsx(
              'p-1.5 rounded-lg transition-colors mb-0.5',
              showDocPanel ? 'text-slate-600 bg-slate-100' : 'text-gray-400 hover:text-gray-600'
            )}
          >
            <DocumentTextIcon className="h-5 w-5" />
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez une question, demandez un document, analysez un sinistre… (Entrée pour envoyer)"
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-gray-800 placeholder-gray-400 focus:outline-none leading-relaxed max-h-32 overflow-y-auto"
            style={{ minHeight: '24px' }}
            disabled={isLoading || isStreaming}
          />
          {isStreaming ? (
            <button
              onClick={onStopStream}
              className="flex-shrink-0 p-2 rounded-lg bg-red-100 text-red-600 hover:bg-red-200 transition-colors"
            >
              <StopIcon className="h-5 w-5" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="flex-shrink-0 p-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <PaperAirplaneIcon className="h-5 w-5" />
            </button>
          )}
        </div>
        <p className="text-xs text-gray-400 mt-1.5 text-center">
          YukpoIA peut faire des erreurs. Vérifiez les informations importantes.
        </p>
      </div>
    </div>
  )
}
