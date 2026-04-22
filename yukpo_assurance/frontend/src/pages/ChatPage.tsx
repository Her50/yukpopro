import { useEffect, useState, useRef } from 'react'
import {
  PlusIcon, ChatBubbleLeftIcon, PencilSquareIcon,
  CheckIcon, XMarkIcon, DocumentTextIcon,
  ChartBarSquareIcon, SparklesIcon,
} from '@heroicons/react/24/outline'
import { ChatWindow } from '../components/ChatWindow'
import { useChat } from '../hooks/useChat'
import { format } from 'date-fns'
import { fr } from 'date-fns/locale'
import { clsx } from 'clsx'
import { RapportsModule } from '../components/RapportsModule'

type ViewTab = 'conversation' | 'rapports'

// ─── Composant renommage inline ───────────────────────────────────────────────

function SessionItem({
  session,
  isActive,
  onSelect,
  onRename,
}: {
  session: { id: string; titre: string; created_at: string }
  isActive: boolean
  onSelect: () => void
  onRename: (id: string, titre: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.titre)
  const inputRef = useRef<HTMLInputElement>(null)

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setDraft(session.titre)
    setEditing(true)
    setTimeout(() => inputRef.current?.select(), 50)
  }

  const confirm = () => {
    const t = draft.trim()
    if (t && t !== session.titre) onRename(session.id, t)
    setEditing(false)
  }

  const cancel = () => { setDraft(session.titre); setEditing(false) }

  return (
    <div
      className={clsx(
        'group relative w-full text-left rounded-lg transition-colors cursor-pointer',
        isActive ? 'bg-primary-600' : 'hover:bg-gray-200'
      )}
      onClick={() => !editing && onSelect()}
    >
      {editing ? (
        <div className="flex items-center gap-1 px-2 py-1.5" onClick={e => e.stopPropagation()}>
          <input
            ref={inputRef}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') confirm(); if (e.key === 'Escape') cancel() }}
            className="flex-1 min-w-0 text-xs bg-white border border-primary-400 rounded px-2 py-1 text-gray-800 outline-none"
            autoFocus
          />
          <button onClick={confirm} className="p-0.5 text-green-600 hover:text-green-700"><CheckIcon className="w-3.5 h-3.5" /></button>
          <button onClick={cancel} className="p-0.5 text-red-500 hover:text-red-600"><XMarkIcon className="w-3.5 h-3.5" /></button>
        </div>
      ) : (
        <div className="flex items-center gap-1 px-3 py-2.5">
          <div className="flex-1 min-w-0">
            <p className={clsx('font-medium truncate text-sm', isActive ? 'text-white' : 'text-gray-700')}>
              {session.titre}
            </p>
            <p className={clsx('text-xs mt-0.5', isActive ? 'text-primary-100' : 'text-gray-400')}>
              {format(new Date(session.created_at), 'd MMM', { locale: fr })}
            </p>
          </div>
          <button
            onClick={startEdit}
            className={clsx(
              'opacity-0 group-hover:opacity-100 p-1 rounded transition-opacity flex-shrink-0',
              isActive ? 'text-primary-200 hover:text-white hover:bg-primary-700' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-300'
            )}
            title="Renommer"
          >
            <PencilSquareIcon className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Page principale ──────────────────────────────────────────────────────────

export function ChatPage() {
  const {
    sessions,
    currentSession,
    messages,
    isLoading,
    isStreaming,
    streamingContent,
    loadSessions,
    createSession,
    selectSession,
    sendMessage,
    stopStream,
    renameSession,
  } = useChat()

  const [viewTab, setViewTab] = useState<ViewTab>('conversation')

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  return (
    <div className="flex h-full bg-white overflow-hidden">

      {/* ── Sidebar sessions ─────────────────────────────────────────────── */}
      <div className="w-64 flex-shrink-0 border-r border-gray-200 flex flex-col bg-gray-50">

        {/* Bouton nouvelle conversation */}
        <div className="p-3 border-b border-gray-200 space-y-2">
          <button
            onClick={() => { createSession(); setViewTab('conversation') }}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-primary-600 px-3 py-2.5 text-sm font-medium text-white hover:bg-primary-700 transition-colors shadow-sm"
          >
            <PlusIcon className="h-4 w-4" />
            Nouvelle conversation
          </button>
          <button
            onClick={() => setViewTab('rapports')}
            className={clsx(
              'w-full flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-colors border',
              viewTab === 'rapports'
                ? 'bg-amber-50 border-amber-300 text-amber-700'
                : 'border-gray-200 text-gray-600 hover:bg-gray-100'
            )}
          >
            <ChartBarSquareIcon className="h-4 w-4" />
            Générer un rapport
          </button>
        </div>

        {/* Liste sessions */}
        <div className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
          {sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center px-4">
              <ChatBubbleLeftIcon className="h-8 w-8 text-gray-300 mb-2" />
              <p className="text-xs text-gray-400">Aucune conversation. Commencez par en créer une.</p>
            </div>
          ) : (
            sessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={currentSession?.id === session.id && viewTab === 'conversation'}
                onSelect={() => { selectSession(session); setViewTab('conversation') }}
                onRename={renameSession}
              />
            ))
          )}
        </div>

        {/* Tip renommage */}
        <div className="px-3 pb-3">
          <p className="text-xs text-gray-400 flex items-center gap-1">
            <PencilSquareIcon className="w-3 h-3" />
            Survolez une session pour la renommer
          </p>
        </div>
      </div>

      {/* ── Zone principale ───────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Tabs Conversation / Rapports */}
        <div className="border-b border-gray-200 bg-white flex-shrink-0">
          <nav className="flex px-4 gap-1">
            {[
              { key: 'conversation' as ViewTab, label: 'Conversation', icon: SparklesIcon },
              { key: 'rapports' as ViewTab, label: 'Rapports & Documents', icon: DocumentTextIcon },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setViewTab(tab.key)}
                className={clsx(
                  'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                  viewTab === tab.key
                    ? 'border-primary-600 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                )}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}

            {/* Titre session courante */}
            {viewTab === 'conversation' && currentSession && (
              <div className="ml-auto flex items-center self-center">
                <span className="text-xs text-gray-400 max-w-xs truncate">{currentSession.titre}</span>
                <button
                  onClick={() => {
                    const t = prompt('Renommer la session :', currentSession.titre)
                    if (t?.trim()) renameSession(currentSession.id, t.trim())
                  }}
                  className="ml-2 p-1 text-gray-400 hover:text-gray-600 rounded"
                  title="Renommer"
                >
                  <PencilSquareIcon className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </nav>
        </div>

        {/* Contenu */}
        {viewTab === 'conversation' && (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <ChatWindow
              messages={messages}
              isLoading={isLoading}
              isStreaming={isStreaming}
              streamingContent={streamingContent}
              onSendMessage={(content) => sendMessage(content, false)}
              onStopStream={stopStream}
            />
          </div>
        )}

        {viewTab === 'rapports' && (
          <div className="flex-1 overflow-y-auto p-6">
            <RapportsModule module="general" />
          </div>
        )}
      </div>
    </div>
  )
}
