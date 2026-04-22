import { useState, useCallback, useRef } from 'react'
import { chatAPI } from '../api/client'
import { ChatMessage, ChatSession } from '../api/types'

/** Génère un nom intelligent à partir du premier message utilisateur */
function genererTitreSession(premierMessage: string): string {
  const msg = premierMessage.trim()
  // Nettoyer la ponctuation excessive, prendre les 50 premiers caractères
  const titre = msg
    .replace(/^(génère|crée|rédige|explique|calcule|quell?e?s?|comment|pourquoi)\s+/i, '')
    .replace(/[?!.]+$/, '')
    .slice(0, 52)
  return titre.charAt(0).toUpperCase() + titre.slice(1) + (msg.length > 52 ? '…' : '')
}

export function useChat() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const eventSourceRef = useRef<EventSource | null>(null)
  const isFirstMessageRef = useRef(true)

  const loadSessions = useCallback(async () => {
    try {
      const sessions = await chatAPI.getSessions()
      setSessions(sessions)
      // Auto-sélectionner la session la plus récente si aucune n'est active
      if (sessions.length > 0) {
        setCurrentSession(sessions[0])
        isFirstMessageRef.current = false
      }
    } catch {
      setSessions([])
    }
  }, [])

  const createSession = useCallback(async (titre?: string, resetMessages = true) => {
    const session = await chatAPI.createSession(titre)
    setSessions((prev) => [session, ...prev])
    setCurrentSession(session)
    if (resetMessages) setMessages([])
    isFirstMessageRef.current = true // Nouvelle session → premier message
    return session
  }, [])

  const selectSession = useCallback((session: ChatSession) => {
    setCurrentSession(session)
    setMessages([])
    isFirstMessageRef.current = false // Session existante
  }, [])

  const renameSession = useCallback((sessionId: string, newTitle: string) => {
    setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, titre: newTitle } : s))
    setCurrentSession(prev => prev?.id === sessionId ? { ...prev, titre: newTitle } : prev)
    // Best-effort API call (ignore errors)
    try {
      chatAPI.renameSession?.(sessionId, newTitle)
    } catch { /* ignore */ }
  }, [])

  const sendMessage = useCallback(
    async (content: string, useStream = true) => {
      if (!content.trim()) return

      // Ajouter le message utilisateur IMMÉDIATEMENT (avant tout appel réseau)
      // Cela garantit que le message s'affiche même si la création de session échoue
      const placeholderSessionId = currentSession?.id || 'pending'
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
        session_id: placeholderSessionId,
      }
      setMessages((prev) => [...prev, userMsg])

      let session = currentSession
      if (!session) {
        try {
          session = await createSession(undefined, false) // false = don't clear the user message we just added
        } catch {
          setMessages((prev) => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              role: 'assistant' as const,
              content: '⚠️ Impossible de contacter le serveur. Vérifiez que le backend est démarré (`uvicorn api.main:app --reload`).',
              created_at: new Date().toISOString(),
              session_id: placeholderSessionId,
            },
          ])
          return
        }
      }

      // Auto-naming : renommer la session sur le premier message si titre générique
      if (isFirstMessageRef.current && (session.titre === 'Nouvelle conversation' || session.titre.startsWith('Session'))) {
        const titreAuto = genererTitreSession(content)
        isFirstMessageRef.current = false
        renameSession(session.id, titreAuto)
      } else {
        isFirstMessageRef.current = false
      }

      if (useStream) {
        setIsStreaming(true)
        setStreamingContent('')

        const streamUrl = chatAPI.getStreamUrl(session.id, content)
        const es = new EventSource(streamUrl)
        eventSourceRef.current = es

        let accumulated = ''

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.chunk && !data.done) {
              accumulated += data.chunk
              setStreamingContent(accumulated)
            }
            if (data.done) {
              setIsStreaming(false)
              const finalContent = data.full_content || accumulated
              const assistantMsg: ChatMessage = {
                id: `assistant-${Date.now()}`,
                role: 'assistant',
                content: finalContent,
                created_at: new Date().toISOString(),
                session_id: session!.id,
              }
              setMessages((prev) => [...prev, assistantMsg])
              setStreamingContent('')
              es.close()
            }
          } catch {
            // ignore parse errors
          }
        }

        es.onerror = () => {
          setIsStreaming(false)
          es.close()
          // Fallback : essayer en mode non-stream
          setIsLoading(true)
          chatAPI.sendMessage({ session_id: session!.id, content })
            .then((respRaw: unknown) => {
              const resp = respRaw as Record<string, unknown>
              const msg = resp.message as Record<string, unknown> | undefined
              // Le backend retourne "reponse" (pas "content") — supporter les deux
              const texte = (msg?.content as string)
                || (resp.content as string)
                || (resp.reponse as string)
                || (resp.response as string)
                || ''
              const assistantMsg: ChatMessage = {
                id: (msg?.id as string) || `assistant-${Date.now()}`,
                role: 'assistant',
                content: texte || 'Une erreur est survenue. Vérifiez votre clé API.',
                created_at: (msg?.created_at as string) || new Date().toISOString(),
                session_id: session!.id,
              }
              setMessages((prev) => [...prev, assistantMsg])
            })
            .catch(() => {
              const errMsg: ChatMessage = {
                id: `error-${Date.now()}`,
                role: 'assistant',
                content: '⚠️ Yukpo IA indisponible. Vérifiez que `CLAUDE_API_KEY` ou `OPENAI_API_KEY` est valide dans le fichier `.env` côté backend.',
                created_at: new Date().toISOString(),
                session_id: session!.id,
              }
              setMessages((prev) => [...prev, errMsg])
            })
            .finally(() => setIsLoading(false))
        }
      } else {
        setIsLoading(true)
        try {
          const respRaw = await chatAPI.sendMessage({ session_id: session.id, content })
          const resp = respRaw as Record<string, unknown>
          const respMsg = resp.message as Record<string, unknown> | undefined
          const texteNonStream = (respMsg?.content as string)
            || (resp.content as string)
            || (resp.reponse as string)
            || (resp.response as string)
            || ''
          const assistantMsg: ChatMessage = {
            id: (respMsg?.id as string) || `assistant-${Date.now()}`,
            role: 'assistant',
            content: texteNonStream,
            created_at: (respMsg?.created_at as string) || new Date().toISOString(),
            session_id: session.id,
          }
          setMessages((prev) => [...prev, assistantMsg])
        } finally {
          setIsLoading(false)
        }
      }
    },
    [currentSession, createSession]
  )

  const stopStream = useCallback(() => {
    eventSourceRef.current?.close()
    setIsStreaming(false)
    setStreamingContent('')
  }, [])

  return {
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
  }
}
