/**
 * AgentPage — Interface principale Yukpo Agents Yukpo.
 *
 * Layout :
 *   Gauche  : Zone conversation branded Yukpo
 *   Droite  : Timeline actions + validations humaines
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  PaperAirplaneIcon as Send,
  BoltIcon as Zap,
  ExclamationTriangleIcon as AlertTriangle,
  ArrowPathIcon as RotateCcw,
  SignalIcon as Activity,
  SparklesIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline'
import { useAgentStore, type AgentType } from '../store/agentStore'
import { useApprovalStore } from '../store/approvalStore'
import { ActionTimeline } from '../components/AgentChat/ActionTimeline'
import { ApprovalCard } from '../components/AgentChat/ApprovalCard'
import { QuestionCard } from '../components/AgentChat/QuestionCard'
import { AgentSelector } from '../components/AgentChat/AgentSelector'
import { useCompagnieStore } from '../store/compagnieStore'

const API = import.meta.env.VITE_API_URL ?? ''

// ─── Types locaux ─────────────────────────────────────────────────────────────
interface ConvMessage {
  id: string
  role: 'user' | 'agent'
  content: string
  timestamp: string
  resultStatus?: 'termine' | 'erreur' | 'en_attente_validation'
}

interface ClarificationState {
  question: string
  choix: Array<{ label: string; emoji: string; agentType: AgentType; description: string }>
  pendingInstruction: string
}

// ─── Règles de clarification (client-side, toujours actives) ─────────────────
const GREETING_REGEX = /^(bonjour|bonsoir|salut|slt|coucou|hello|hi|hey|bonne?\s*journ[eé]e|bonne?\s*nuit|bonne?\s*soir[eé]e)\b[!.,\s]*$/i

const CLARIFICATION_RULES: Array<{
  test: (s: string) => boolean
  question: string
  choix: ClarificationState['choix']
}> = [
  // Salutation pure → menu général (toujours, quel que soit l'agent sélectionné)
  {
    test: (s) => GREETING_REGEX.test(s.trim()),
    question: 'Bonjour ! Comment puis-je vous aider aujourd\'hui ?',
    choix: [
      { label: 'Déclarer un sinistre', emoji: '📋', agentType: 'sinistres', description: 'Auto, maladie, risques divers' },
      { label: 'Souscrire un contrat', emoji: '✍️', agentType: 'souscription', description: 'Nouvelle police ou avenant' },
      { label: 'Conformité CIMA', emoji: '🛡️', agentType: 'conformite', description: 'États réglementaires, ratios prudentiels' },
      { label: 'Autre demande', emoji: '💬', agentType: 'auto', description: 'Laissez Yukpo choisir le bon agent' },
      { label: 'Comptabilité / Finance', emoji: '📊', agentType: 'comptabilite', description: 'Journaux, rapports financiers, balances' },
    ],
  },
  {
    test: (s) =>
      /\bsinistre[s]?\b/i.test(s) &&
      !/\b(auto|voiture|véhicule|maladie|santé|médical|hospitalisation|rc\s*pro|décennale|incendie|vol|habitation|transport)\b/i.test(s),
    question: 'Quel type de sinistre souhaitez-vous traiter ?',
    choix: [
      { label: 'Auto / RC Auto', emoji: '🚗', agentType: 'sinistres_auto', description: 'Accident de véhicule, collision, RC Auto' },
      { label: 'Maladie / Santé', emoji: '🏥', agentType: 'maladie', description: 'Hospitalisation, consultation, médicaments, lunettes' },
      { label: 'Risques Divers', emoji: '🏗️', agentType: 'risques_divers', description: 'RC Pro, Dommages Ouvrage, ACI, MRH, Agriculture...' },
    ],
  },
  {
    test: (s) =>
      /\b(souscrire|souscription|nouvelle\s+police|nouveau\s+contrat|émettre\s+une\s+police|créer\s+un\s+contrat)\b/i.test(s) &&
      !/\b(auto|vie|épargne|décès|habitation|rc\s*pro|maladie|groupe)\b/i.test(s),
    question: 'Quelle branche d\'assurance souhaitez-vous souscrire ?',
    choix: [
      { label: 'Auto', emoji: '🚗', agentType: 'souscription', description: 'RC Auto, Tous Risques, flotte' },
      { label: 'Vie & Épargne', emoji: '💼', agentType: 'vie', description: 'Capital décès, épargne, retraite, rente' },
      { label: 'Risques Divers', emoji: '🏗️', agentType: 'risques_divers', description: 'MRH, RC Pro, DO, Agriculture, Caution...' },
      { label: 'Maladie / Groupe', emoji: '🏥', agentType: 'maladie', description: 'Assurance maladie individuelle ou de groupe' },
    ],
  },
  {
    test: (s) =>
      /\b(aide|aider|assist|besoin|comment\s+faire|que\s+faire|je\s+voudrais|je\s+veux)\b/i.test(s) &&
      !/\b(sinistre|police|contrat|rapport|provision|état|bordereau|calcul|ratio|schéma)\b/i.test(s),
    question: 'Comment puis-je vous aider aujourd\'hui ?',
    choix: [
      { label: 'Déclarer un sinistre', emoji: '📋', agentType: 'sinistres', description: 'Auto, maladie, risques divers' },
      { label: 'Souscrire un contrat', emoji: '✍️', agentType: 'souscription', description: 'Nouvelle police ou avenant' },
      { label: 'Conformité CIMA', emoji: '🛡️', agentType: 'conformite', description: 'États réglementaires, ratios prudentiels' },
      { label: 'Autre demande', emoji: '💬', agentType: 'auto', description: 'Laissez Yukpo choisir le bon agent' },
    ],
  },
]

interface ExecutionInterrompue {
  execution_id: string
  agent_type: AgentType
  instruction: string
  saved_at: string
}

export default function AgentPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [instruction, setInstruction]  = useState(searchParams.get('instruction') ?? '')
  const [agentType, setAgentType]      = useState<AgentType>('auto')
  const [erreurConnexion, setErreurConnexion] = useState('')
  const [executionsInterrompues, setExecutionsInterrompues] = useState<ExecutionInterrompue[]>([])
  const [convMessages, setConvMessages]     = useState<ConvMessage[]>([])
  const [clarification, setClarification]   = useState<ClarificationState | null>(null)
  const chatContainerRef                     = useRef<HTMLDivElement>(null)
  const messagesEndRef                       = useRef<HTMLDivElement>(null)
  const textareaRef                     = useRef<HTMLTextAreaElement>(null)
  const { branding }                    = useCompagnieStore()

  // Pré-remplissage depuis la sidebar (query param)
  useEffect(() => {
    const instr = searchParams.get('instruction')
    if (instr) {
      setInstruction(instr)
      setSearchParams({}, { replace: true })
      textareaRef.current?.focus()
    }
  }, [])

  const {
    etapesStream,
    executionCourante,
    enCours,
    ajouterEtapeStream,
    reinitialiserStream,
    setEnCours,
    setExecutionCourante,
  } = useAgentStore()

  const { items: validations, setItems } = useApprovalStore()
  const validationsEnAttente = validations.filter((v) => v.statut === 'en_attente')
  const questionsEnAttente   = validationsEnAttente.filter((v) => v.type === 'question_utilisateur')
  const approbationsEnAttente = validationsEnAttente.filter((v) => v.type !== 'question_utilisateur')

  // Défini AVANT les useEffect et lancerInstruction qui le référencent
  const chargerValidations = useCallback(async () => {
    try {
      const token = localStorage.getItem('access_token') || ''
      const res = await fetch(`${API}/api/v1/agent/validations`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setItems(data.validations ?? [])
      }
    } catch { /* ignore */ }
  }, [setItems])

  // Chargement initial des validations en attente (questions ou approbations)
  useEffect(() => {
    chargerValidations()
  }, [chargerValidations])

  // Vérifier les exécutions interrompues (coupure réseau/courant)
  useEffect(() => {
    const token = localStorage.getItem('access_token') || ''
    if (!token) return
    fetch(`${API}/api/v1/agent/executions_interrompues`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.executions?.length) setExecutionsInterrompues(d.executions) })
      .catch(() => {})
  }, [])

  // Helper : vérifie si le token JWT est expiré
  const isTokenExpired = (token: string): boolean => {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      return payload.exp * 1000 < Date.now()
    } catch { return true }
  }

  // Helper : vérifie le token et redirige vers login si expiré/absent
  const verifierToken = (): string | null => {
    const token = localStorage.getItem('access_token')
    if (!token || isTokenExpired(token)) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
      return null
    }
    return token
  }

  // Scroll : amène toujours le bas de la conversation en vue
  useEffect(() => {
    // Petit délai pour laisser le DOM se rendre (QuestionCard, indicateur)
    const id = setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }, 80)
    return () => clearTimeout(id)
  }, [convMessages, clarification, questionsEnAttente, enCours])

  // Lancer avec un agent déjà choisi (depuis boutons clarification ou reprise checkpoint)
  const lancerAvecAgent = useCallback(async (instr: string, agent: AgentType, resumeExecutionId?: string) => {
    const token = verifierToken()
    if (!token) return

    setClarification(null)

    reinitialiserStream()
    setEnCours(true)
    setErreurConnexion('')
    let sseClosed = false
    let finRecu = false
    const fermerLocal = (source: EventSource) => { if (!sseClosed) { sseClosed = true; source.close() } }

    const timeoutId = setTimeout(() => {
      if (!finRecu) {
        setEnCours(false)
        setErreurConnexion('Délai dépassé — le serveur met trop de temps à répondre.')
        setConvMessages(prev => [...prev, {
          id: `a_${Date.now()}`,
          role: 'agent',
          content: 'Délai dépassé. Vérifiez que le backend est démarré.',
          timestamp: new Date().toISOString(),
          resultStatus: 'erreur',
        }])
        chargerValidations()
      }
    }, 120_000)

    try {
      // Si reprise depuis checkpoint, utiliser l'endpoint dédié
      const url = resumeExecutionId
        ? `${API}/api/v1/agent/stream/reprendre/${resumeExecutionId}?token=${encodeURIComponent(token)}`
        : `${API}/api/v1/agent/stream?instruction=${encodeURIComponent(instr)}&agent_type=${agent}&token=${encodeURIComponent(token)}`
      const source = new EventSource(url)

      source.onmessage = (event) => {
        clearTimeout(timeoutId)
        try {
          const etape = JSON.parse(event.data)
          if (etape.type === 'fin') {
            finRecu = true
            fermerLocal(source)
            setEnCours(false)
            chargerValidations()
            return
          }
          if (etape.type === 'erreur') {
            ajouterEtapeStream(etape)
            const msg = etape.detail || etape.libelle || 'Erreur inconnue'
            setErreurConnexion(`Erreur agent : ${msg}`)
            setConvMessages(prev => [...prev, {
              id: `a_${Date.now()}`,
              role: 'agent',
              content: `❌ ${msg}`,
              timestamp: new Date().toISOString(),
              resultStatus: 'erreur',
            }])
            return
          }
          ajouterEtapeStream(etape)
          if (etape.type === 'resultat') {
            const status = etape.donnees?.validation_en_cours ? 'en_attente_validation'
              : etape.donnees?.statut === 'erreur' ? 'erreur' : 'termine'
            setExecutionCourante({
              execution_id: etape.donnees?.execution_id ?? '',
              agent,
              instruction: instr,
              statut: status,
              etapes: [],
              resume: etape.detail,
              actions_requises: [],
              duree_ms: etape.donnees?.duree_ms ?? 0,
              ia_appelee: etape.donnees?.ia_appelee ?? false,
              cout_ia_usd: 0,
              timestamp: new Date().toISOString(),
            })
            if (etape.detail) {
              setConvMessages(prev => {
                const last = prev[prev.length - 1]
                if (last?.role === 'agent' && last.content === etape.detail) return prev
                return [...prev, { id: `a_${Date.now()}`, role: 'agent', content: etape.detail, timestamp: new Date().toISOString(), resultStatus: status }]
              })
            }
            chargerValidations()
          }
          if (etape.type === 'question') {
            chargerValidations()
          }
        } catch { /* ignore parse errors */ }
      }

      source.onerror = () => {
        clearTimeout(timeoutId)
        fermerLocal(source)
        setEnCours(false)
        if (!finRecu) {
          const msg = 'Connexion perdue. Vérifiez que le backend est démarré.'
          setErreurConnexion(msg)
          setConvMessages(prev => [...prev, {
            id: `a_${Date.now()}`,
            role: 'agent',
            content: `❌ ${msg}`,
            timestamp: new Date().toISOString(),
            resultStatus: 'erreur',
          }])
          chargerValidations()
        }
      }
    } catch (err) {
      clearTimeout(timeoutId)
      setEnCours(false)
      setErreurConnexion(`Erreur : ${err}`)
    }
  }, [chargerValidations, reinitialiserStream, setEnCours, setExecutionCourante, ajouterEtapeStream])

  const lancerInstruction = useCallback(async () => {
    if (!instruction.trim() || enCours) return

    const instr = instruction.trim()
    setInstruction('')
    setClarification(null)

    // ── Si un agent est en attente d'une réponse → router vers la question active ──
    if (questionsEnAttente.length > 0) {
      const questionActive = questionsEnAttente[0]
      const token = verifierToken()
      if (!token) return
      setConvMessages(prev => [...prev, {
        id: `u_${Date.now()}`, role: 'user', content: instr, timestamp: new Date().toISOString(),
      }])
      setEnCours(true)
      try {
        const res = await fetch(`${API}/api/v1/agent/repondre/${questionActive.id}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ reponse: instr }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (data.reprise?.resume) {
          setConvMessages(prev => [...prev, {
            id: `a_${Date.now()}`, role: 'agent',
            content: data.reprise.resume,
            timestamp: new Date().toISOString(),
            resultStatus: data.reprise.statut === 'en_attente_validation' ? 'en_attente_validation' : 'termine',
          }])
        }
        chargerValidations()
      } catch (err) {
        setConvMessages(prev => [...prev, {
          id: `a_${Date.now()}`, role: 'agent',
          content: `❌ Erreur lors de la réponse à l'agent : ${err}`,
          timestamp: new Date().toISOString(), resultStatus: 'erreur',
        }])
      } finally {
        setEnCours(false)
      }
      return
    }

    // Ajouter le message utilisateur dans la conversation immédiatement
    setConvMessages(prev => [...prev, {
      id: `u_${Date.now()}`,
      role: 'user',
      content: instr,
      timestamp: new Date().toISOString(),
    }])

    // Salutation pure → réponse locale immédiate (pas de round-trip)
    if (CLARIFICATION_RULES[0].test(instr)) {
      const instrLower = instr.trim().toLowerCase()
      const salutation = /bonsoir/i.test(instrLower) ? 'Bonsoir'
        : /bonne\s*nuit/i.test(instrLower) ? 'Bonne nuit'
        : /salut|slt|coucou/i.test(instrLower) ? 'Salut'
        : /hello|hi|hey/i.test(instrLower) ? 'Hello'
        : 'Bonjour'
      const question = `${salutation} ! Comment puis-je vous aider aujourd'hui ?`
      setClarification({ question, choix: CLARIFICATION_RULES[0].choix, pendingInstruction: instr })
      setConvMessages(prev => [...prev, {
        id: `a_${Date.now()}`, role: 'agent',
        content: question,
        timestamp: new Date().toISOString(),
      }])
      return
    }

    // Si agent=auto → passer par le Copilote conversationnel
    if (agentType === 'auto') {
      setEnCours(true)
      setErreurConnexion('')
      const token = verifierToken()
      if (!token) return
      const histoMessages = [...convMessages, { id: `u_tmp`, role: 'user' as const, content: instr, timestamp: new Date().toISOString() }]
      try {
        const res = await fetch(`${API}/api/v1/agent/converser`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ messages: histoMessages.map(m => ({ role: m.role === 'user' ? 'user' : 'agent', content: m.content })) }),
        })
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let agentLance = false
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'chat' && data.content) {
                setConvMessages(prev => {
                  const last = prev[prev.length - 1]
                  if (last?.role === 'agent' && last.content === data.content) return prev
                  return [...prev, { id: `a_${Date.now()}`, role: 'agent', content: data.content, timestamp: new Date().toISOString() }]
                })
              } else if (data.type === 'lancer_agent' && data.agent_type) {
                agentLance = true
                setAgentType(data.agent_type)
                lancerAvecAgent(data.instruction || instr, data.agent_type)
              }
            } catch { /* ignore */ }
          }
        }
        if (!agentLance) setEnCours(false)
      } catch (err) {
        setEnCours(false)
        // Fallback sur les règles locales si le Copilote est indisponible
        for (const rule of CLARIFICATION_RULES.slice(1)) {
          if (rule.test(instr)) {
            setClarification({ question: rule.question, choix: rule.choix, pendingInstruction: instr })
            setConvMessages(prev => [...prev, { id: `a_${Date.now()}`, role: 'agent', content: rule.question, timestamp: new Date().toISOString() }])
            return
          }
        }
        setConvMessages(prev => [...prev, { id: `a_${Date.now()}`, role: 'agent', content: `❌ Service indisponible : ${err}`, timestamp: new Date().toISOString(), resultStatus: 'erreur' }])
      }
      return
    }

    // Agent pré-sélectionné → lancement direct SSE
    reinitialiserStream()
    setEnCours(true)
    setErreurConnexion('')

    const token = verifierToken()
    if (!token) return
    let sseClosed = false
    let finRecu = false
    const fermer = (source: EventSource) => { if (!sseClosed) { sseClosed = true; source.close() } }

    const timeoutId = setTimeout(() => {
      if (!finRecu) {
        setEnCours(false)
        const msg = 'Délai dépassé — le serveur met trop de temps à répondre. Vérifiez que le backend est démarré et que CLAUDE_API_KEY est configurée dans .env'
        setErreurConnexion(msg)
        setConvMessages(prev => [...prev, { id: `a_${Date.now()}`, role: 'agent', content: `⏱️ ${msg}`, timestamp: new Date().toISOString(), resultStatus: 'erreur' }])
        chargerValidations()
      }
    }, 120_000)

    try {
      const url = `${API}/api/v1/agent/stream?instruction=${encodeURIComponent(instr)}&agent_type=${agentType}&token=${encodeURIComponent(token)}`
      const source = new EventSource(url)

      source.onmessage = (event) => {
        clearTimeout(timeoutId)
        try {
          const etape = JSON.parse(event.data)
          if (etape.type === 'fin') {
            finRecu = true
            fermer(source)
            setEnCours(false)
            chargerValidations()
            return
          }
          if (etape.type === 'erreur') {
            ajouterEtapeStream(etape)
            const msg = etape.detail || etape.libelle || 'Erreur inconnue'
            setErreurConnexion(`Erreur agent : ${msg}`)
            setConvMessages(prev => [...prev, { id: `a_${Date.now()}`, role: 'agent', content: `❌ ${msg}`, timestamp: new Date().toISOString(), resultStatus: 'erreur' }])
            return
          }
          ajouterEtapeStream(etape)
          if (etape.type === 'resultat') {
            const status = etape.donnees?.validation_en_cours ? 'en_attente_validation'
              : etape.donnees?.statut === 'erreur' ? 'erreur' : 'termine'
            setExecutionCourante({
              execution_id: etape.donnees?.execution_id ?? '',
              agent: agentType,
              instruction: instr,
              statut: status,
              etapes: [],
              resume: etape.detail,
              actions_requises: [],
              duree_ms: etape.donnees?.duree_ms ?? 0,
              ia_appelee: etape.donnees?.ia_appelee ?? false,
              cout_ia_usd: 0,
              timestamp: new Date().toISOString(),
            })
            if (etape.detail) {
              setConvMessages(prev => {
                const last = prev[prev.length - 1]
                if (last?.role === 'agent' && last.content === etape.detail) return prev
                return [...prev, { id: `a_${Date.now()}`, role: 'agent', content: etape.detail, timestamp: new Date().toISOString(), resultStatus: status }]
              })
            }
            chargerValidations()
          }
          if (etape.type === 'question') { chargerValidations() }
        } catch { /* ignore parse errors */ }
      }

      source.onerror = () => {
        clearTimeout(timeoutId)
        fermer(source)
        setEnCours(false)
        if (!finRecu) {
          const msg = 'Connexion perdue avec le backend. Causes possibles :\n1. Backend non démarré → uvicorn api.main:app --reload --port 8000\n2. CLAUDE_API_KEY non configurée dans yukpo_assurance/.env'
          setErreurConnexion(msg)
          setConvMessages(prev => [...prev, { id: `a_${Date.now()}`, role: 'agent', content: `❌ ${msg}`, timestamp: new Date().toISOString(), resultStatus: 'erreur' }])
          chargerValidations()
        }
      }
    } catch (err) {
      clearTimeout(timeoutId)
      console.error('[AgentPage] Erreur:', err)
      setEnCours(false)
      setErreurConnexion(`Erreur : ${err}`)
    }
  }, [instruction, agentType, enCours, chargerValidations, reinitialiserStream, setEnCours, setExecutionCourante, ajouterEtapeStream])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); lancerInstruction() }
  }

  // ── Réinitialisation complète de la conversation ─────────────────────────
  const reinitialiserConversation = useCallback(() => {
    setConvMessages([])
    setClarification(null)
    setErreurConnexion('')
    setAgentType('auto')
    setInstruction('')
    reinitialiserStream()
    setEnCours(false)
    setItems([])            // vider les questions/validations en attente
    setExecutionCourante(null)
    textareaRef.current?.focus()
  }, [reinitialiserStream, setEnCours, setExecutionCourante, setItems])

  return (
    <div className="flex h-full bg-gray-50">

      {/* ─── GAUCHE : conversation ───────────────────────────────────────── */}
      <div className="flex flex-col w-full max-w-2xl border-r border-gray-200 bg-white">

        {/* Header Yukpo branded */}
        <div
          className="relative overflow-hidden px-6 py-5 border-b border-blue-900/20"
          style={{ background: 'linear-gradient(135deg, #0054A6 0%, #003476 60%, #1e2640 100%)' }}
        >
          {/* Motif décoratif */}
          <div className="absolute inset-0 opacity-10"
            style={{
              backgroundImage: 'radial-gradient(circle at 80% 20%, #00B0F0 0%, transparent 50%), radial-gradient(circle at 10% 80%, #00B0F0 0%, transparent 40%)',
            }}
          />

          <div className="relative flex items-start gap-4">
            {/* Logo Y */}
            <div
              className="flex-shrink-0 w-12 h-12 rounded-2xl flex items-center justify-center shadow-lg"
              style={{ background: 'linear-gradient(135deg, #00B0F0, #0054A6)' }}
            >
              {branding.logo_url ? (
                <img src={branding.logo_url} alt={branding.nom} className="w-8 h-8 object-contain" />
              ) : (
                <span className="text-white font-black text-xl tracking-tight">Y</span>
              )}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-white font-black text-xl tracking-tight">{branding.nom || 'Yukpo'}</span>
                <span
                  className="text-xs font-bold px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(0,176,240,0.25)', color: '#7dd3fc', border: '1px solid rgba(0,176,240,0.3)' }}
                >
                  Agents Yukpo
                </span>
              </div>
              <p className="text-blue-200 text-xs font-medium">
                L'intelligence au service de votre compagnie CIMA
              </p>
            </div>

            {questionsEnAttente.length > 0 && (
              <div className="flex-shrink-0 flex items-center gap-1.5 bg-blue-500/20 border border-blue-400/40 px-3 py-1.5 rounded-full animate-pulse">
                <span className="text-blue-200 text-xs font-bold">❓ {questionsEnAttente.length} question{questionsEnAttente.length > 1 ? 's' : ''}</span>
              </div>
            )}
            {approbationsEnAttente.length > 0 && (
              <div className="flex-shrink-0 flex items-center gap-1.5 bg-orange-500/20 border border-orange-400/40 px-3 py-1.5 rounded-full animate-pulse">
                <ShieldCheckIcon className="w-3.5 h-3.5 text-orange-300" />
                <span className="text-orange-200 text-xs font-bold">{approbationsEnAttente.length} en attente</span>
              </div>
            )}
            {/* Bouton nouvelle conversation — visible si la conversation a commencé */}
            {convMessages.length > 0 && (
              <button
                onClick={reinitialiserConversation}
                title="Nouvelle conversation"
                className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-all hover:bg-white/20"
                style={{ background: 'rgba(255,255,255,0.1)', color: '#bfdbfe', border: '1px solid rgba(255,255,255,0.2)' }}
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Nouveau
              </button>
            )}
          </div>

          {/* Tagline strip */}
          <div className="relative mt-4 flex items-center gap-4 text-xs">
            {[
              { icon: '⚡', text: '15 agents spécialisés' },
              { icon: '🛡️', text: 'Conformité CIMA' },
              { icon: '🤖', text: 'Vie & Non-Vie' },
            ].map((item) => (
              <div key={item.text} className="flex items-center gap-1 text-blue-200/80">
                <span>{item.icon}</span>
                <span>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Zone conversation */}
        <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-6 space-y-4">

          {/* Historique conversation — QuestionCard intercalée au bon endroit */}
          {(() => {
            // Index du dernier message agent "en_attente_validation" → QuestionCard s'insère juste après
            const lastPendingIdx = convMessages.reduce(
              (last, m, i) => (m.role === 'agent' && m.resultStatus === 'en_attente_validation' ? i : last),
              -1
            )
            return convMessages.map((msg, index) => (
              <div key={msg.id}>
                {/* Bulle de message */}
                <div className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'agent' && (
                    <div
                      className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center mr-2 mt-0.5"
                      style={{ background: 'linear-gradient(135deg, #0054A6, #00B0F0)' }}
                    >
                      <SparklesIcon className="w-4 h-4 text-white" />
                    </div>
                  )}
                  <div
                    className={`max-w-sm px-4 py-3 rounded-2xl text-sm shadow-sm ${
                      msg.role === 'user'
                        ? 'rounded-br-md text-white'
                        : msg.resultStatus === 'erreur'
                        ? 'bg-red-50 border border-red-200 text-red-700 rounded-bl-md'
                        : msg.resultStatus === 'en_attente_validation'
                        ? 'bg-orange-50 border border-orange-200 text-orange-800 rounded-bl-md'
                        : 'bg-blue-50 border border-blue-100 text-gray-700 rounded-bl-md'
                    }`}
                    style={msg.role === 'user' ? { background: 'linear-gradient(135deg, #0054A6, #003476)' } : {}}
                  >
                    <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                    {msg.resultStatus === 'en_attente_validation' && (
                      <p className="text-xs mt-1 text-orange-600 font-medium">⏳ En attente de validation humaine</p>
                    )}
                  </div>
                </div>

                {/* QuestionCard inline — juste après le message de question de l'agent */}
                {index === lastPendingIdx && questionsEnAttente.length > 0 && !enCours && (
                  <div className="ml-10 mt-3">
                    <QuestionCard
                      item={questionsEnAttente[0]}
                      onRefresh={chargerValidations}
                      numeroQuestion={questionsEnAttente.length}
                    />
                  </div>
                )}
              </div>
            ))
          })()}

          {/* Boutons de clarification */}
          {clarification && (
            <div className="ml-10 flex flex-row gap-2 overflow-x-auto pb-1" style={{ scrollbarWidth: 'none' }}>
              {clarification.choix.map((choix) => (
                <button
                  key={choix.agentType}
                  onClick={() => {
                    setAgentType(choix.agentType)
                    lancerAvecAgent(clarification.pendingInstruction, choix.agentType)
                  }}
                  className="flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-xl border border-blue-200 bg-white hover:bg-blue-50 hover:border-blue-400 transition-all text-left shadow-sm hover:shadow-md group"
                >
                  <span className="text-base">{choix.emoji}</span>
                  <div>
                    <div className="text-xs font-bold text-gray-800 group-hover:text-blue-700 whitespace-nowrap">{choix.label}</div>
                    <div className="text-xs text-gray-400 leading-tight whitespace-nowrap">{choix.description}</div>
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Indicateur de travail de l'agent — visible pendant tout le traitement */}
          {enCours && (
            <div className="flex items-start gap-2">
              {/* Avatar agent animé */}
              <div
                className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center shadow-sm"
                style={{ background: 'linear-gradient(135deg, #0054A6, #00B0F0)', animation: 'pulse 1.5s ease-in-out infinite' }}
              >
                <SparklesIcon className="w-4 h-4 text-white" />
              </div>
              <div className="flex-1 max-w-xs px-4 py-3 rounded-2xl rounded-bl-md bg-blue-50 border border-blue-100 shadow-sm">
                {/* Ligne action courante */}
                <div className="flex items-center gap-2 mb-2">
                  {/* Icône loupe contextuelle animée */}
                  <svg className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#0054A6', animation: 'spin 2s linear infinite' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
                  </svg>
                  <span className="text-xs font-semibold text-blue-700 truncate">
                    {etapesStream.length > 0
                      ? etapesStream[etapesStream.length - 1].libelle
                      : 'Analyse en cours…'}
                  </span>
                </div>
                {/* Points animés */}
                <div className="flex items-center gap-1.5">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="w-2 h-2 rounded-full"
                      style={{ background: '#00B0F0', animation: `bounce 1.2s ${i * 0.25}s infinite` }}
                    />
                  ))}
                  <span className="text-xs text-blue-500 ml-1">
                    {etapesStream.length > 0 ? `${etapesStream.length} étape${etapesStream.length > 1 ? 's' : ''}` : 'Yukpo réfléchit…'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Ancre scroll — tout en bas, après tout le contenu */}
          <div ref={messagesEndRef} />

          {/* Exécutions interrompues — proposer la reprise */}
          {executionsInterrompues.length > 0 && convMessages.length === 0 && (
            <div className="rounded-2xl p-4 bg-amber-50 border border-amber-200">
              <p className="text-sm font-bold text-amber-800 mb-2">⚡ Exécution interrompue détectée</p>
              {executionsInterrompues.map(ex => (
                <div key={ex.execution_id} className="flex items-center justify-between gap-3 mb-2">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-amber-900 truncate">{ex.instruction}</p>
                    <p className="text-xs text-amber-600">{ex.agent_type} — {new Date(ex.saved_at).toLocaleString('fr')}</p>
                  </div>
                  <button
                    onClick={() => {
                      setExecutionsInterrompues(prev => prev.filter(e => e.execution_id !== ex.execution_id))
                      lancerAvecAgent(ex.instruction, ex.agent_type as AgentType, ex.execution_id)
                    }}
                    className="flex-shrink-0 px-3 py-1 text-xs font-bold rounded-lg text-white"
                    style={{ background: '#0054A6' }}
                  >
                    Reprendre
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Erreur connexion */}
          {erreurConnexion && convMessages.length === 0 && (
            <div className="rounded-2xl p-4 bg-red-50 border border-red-200">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle className="w-4 h-4 text-red-500" />
                <span className="text-sm font-bold text-red-700">Erreur de connexion</span>
              </div>
              <p className="text-xs text-red-600 leading-relaxed">{erreurConnexion}</p>
              <code className="block mt-2 text-xs bg-red-100 rounded px-2 py-1 text-red-800 font-mono">
                cd yukpo_assurance && uvicorn api.main:app --reload --port 8000
              </code>
            </div>
          )}

          {convMessages.length === 0 && !enCours && (
            <div className="text-center py-10">
              {/* Illustration Yukpo */}
              <div
                className="w-20 h-20 rounded-3xl mx-auto mb-5 flex items-center justify-center shadow-xl"
                style={{ background: 'linear-gradient(135deg, #0054A6, #00B0F0)' }}
              >
                <SparklesIcon className="w-10 h-10 text-white" />
              </div>
              <h2 className="text-2xl font-black text-gray-800 mb-1">
                Bonjour, que puis-je faire ?
              </h2>
              <p className="text-gray-400 text-sm max-w-sm mx-auto leading-relaxed mb-8">
                Donnez une instruction en français. Yukpo Agents analyse, décide et exécute
                le processus complet — il s'arrête uniquement pour les décisions importantes.
              </p>

              <div className="grid grid-cols-2 gap-3 max-w-lg mx-auto">
                {EXEMPLES.map((ex) => (
                  <button
                    key={ex.label}
                    onClick={() => setInstruction(ex.instruction)}
                    className="group text-left p-4 rounded-2xl border border-gray-200 hover:border-blue-400 hover:shadow-md transition-all bg-white"
                    style={{ '--hover-bg': '#f0f7ff' } as React.CSSProperties}
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#f0f7ff')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'white')}
                  >
                    <div className="text-2xl mb-2">{ex.icon}</div>
                    <div className="text-xs font-bold text-gray-700 group-hover:text-blue-700 mb-1">{ex.label}</div>
                    <div className="text-xs text-gray-400 line-clamp-2 leading-relaxed">{ex.instruction}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* Zone saisie */}
        <div className="p-4 border-t border-gray-100 bg-white">
          <AgentSelector value={agentType} onChange={setAgentType} />

          {/* Bannière "agent en attente" si question active — invite à répondre ici */}
          {questionsEnAttente.length > 0 && !enCours && (
            <div className="mt-2 mb-1 flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium"
              style={{ background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' }}>
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
              </svg>
              L'agent attend votre réponse — tapez ci-dessous ou utilisez le formulaire ci-dessus
            </div>
          )}

          <div className="flex gap-2 mt-3">
            <textarea
              ref={textareaRef}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                questionsEnAttente.length > 0 && !enCours
                  ? 'Répondez à la question de l\'agent…'
                  : 'Ex : Instruis le sinistre SIN-2025-042 de A à Z…'
              }
              rows={2}
              disabled={enCours}
              className="flex-1 resize-none rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:ring-2 disabled:opacity-50 transition-all"
              style={{ '--tw-ring-color': '#0054A6' } as React.CSSProperties}
              onFocus={(e) => { e.currentTarget.style.borderColor = '#0054A6'; e.currentTarget.style.background = '#fff' }}
              onBlur={(e) => { e.currentTarget.style.borderColor = ''; e.currentTarget.style.background = '' }}
            />
            <button
              onClick={lancerInstruction}
              disabled={!instruction.trim() || enCours}
              className="self-end px-4 py-3 text-white rounded-xl font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm hover:shadow-md"
              style={{ background: instruction.trim() && !enCours ? 'linear-gradient(135deg, #0054A6, #00B0F0)' : '#94a3b8' }}
            >
              {enCours
                ? <Activity className="w-5 h-5 animate-pulse" />
                : <Send className="w-5 h-5" />}
            </button>
          </div>

          {/* Barre d'actions rapides */}
          <div className="flex items-center justify-between mt-2">
            <p className="text-xs text-gray-400 flex items-center gap-1">
              <span className="font-semibold" style={{ color: '#0054A6' }}>YukpoPro</span>
              <span>· Entrée pour envoyer · Shift+Entrée pour saut de ligne</span>
            </p>
            {convMessages.length > 0 && (
              <div className="flex items-center gap-1">
                {/* Changer d'agent */}
                <button
                  onClick={() => { setAgentType('auto'); setInstruction(''); textareaRef.current?.focus() }}
                  title="Changer d'agent"
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-gray-500 hover:text-blue-600 hover:bg-blue-50 transition-all"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 3M21 7.5H7.5" />
                  </svg>
                  Changer d'agent
                </button>
                {/* Nouvelle conversation */}
                <button
                  onClick={reinitialiserConversation}
                  title="Recommencer depuis le début"
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-gray-500 hover:text-red-600 hover:bg-red-50 transition-all"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Recommencer
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ─── DROITE : timeline + validations ─────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header droite */}
        <div className="flex items-center gap-2 px-6 py-4 border-b border-gray-200 bg-white">
          <div className="w-2 h-2 rounded-full" style={{ background: enCours ? '#00B0F0' : '#22c55e' }} />
          <Zap className="w-4 h-4" style={{ color: '#0054A6' }} />
          <h2 className="text-sm font-bold text-gray-700">Journal d'exécution</h2>
          {enCours && (
            <span className="ml-auto flex items-center gap-1.5 text-xs font-semibold" style={{ color: '#0054A6' }}>
              <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#00B0F0' }} />
              Yukpo agent actif...
            </span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {validationsEnAttente.map((validation) =>
            validation.type === 'question_utilisateur' ? (
              <QuestionCard key={validation.id} item={validation} onRefresh={chargerValidations} />
            ) : (
              <ApprovalCard key={validation.id} item={validation} onRefresh={chargerValidations} />
            )
          )}

          {etapesStream.length > 0 && (
            <ActionTimeline etapes={etapesStream} enCours={enCours} />
          )}

          {etapesStream.length === 0 && validationsEnAttente.length === 0 && (
            <div className="text-center py-16">
              <div
                className="w-14 h-14 rounded-2xl mx-auto mb-4 flex items-center justify-center opacity-30"
                style={{ background: 'linear-gradient(135deg, #0054A6, #00B0F0)' }}
              >
                <RotateCcw className="w-7 h-7 text-white" />
              </div>
              <p className="text-sm text-gray-400">Les actions Yukpo apparaîtront ici en temps réel</p>
            </div>
          )}
        </div>

        {/* Footer branded */}
        <div className="px-4 py-2 border-t border-gray-100 flex items-center justify-between">
          <span className="text-xs text-gray-400">
            Propulsé par <span className="font-bold" style={{ color: '#0054A6' }}>Yukpo Intelligence</span>
          </span>
          <span className="text-xs text-gray-300">Zone CIMA · 15 pays</span>
        </div>
      </div>
    </div>
  )
}

// Injection CSS pour l'animation bounce des dots de chargement
if (typeof document !== 'undefined' && !document.getElementById('yukpo-bounce-style')) {
  const s = document.createElement('style')
  s.id = 'yukpo-bounce-style'
  s.textContent = `@keyframes bounce { 0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)} }`
  document.head.appendChild(s)
}

const EXEMPLES = [
  {
    icon: '🚗',
    label: 'Sinistre auto',
    instruction: 'Instruis le sinistre SIN-2025-042 : vérifie la police, calcule l\'indemnisation et génère le courrier',
  },
  {
    icon: '📋',
    label: 'Souscription',
    instruction: 'Émet une police RC auto pour M. Dupont, VP 1600cm³, Cameroun, usage personnel',
  },
  {
    icon: '🫀',
    label: 'Assurance Vie',
    instruction: 'Souscris un contrat épargne mixte pour Mme Mbarga, 35 ans, capital 5 000 000 FCFA sur 20 ans',
  },
  {
    icon: '📊',
    label: 'Conformité',
    instruction: 'Calcule les ratios prudentiels du trimestre T1-2025 et génère le rapport CRCA',
  },
  {
    icon: '🔄',
    label: 'Réassurance',
    instruction: 'Établis le bordereau de cession trimestriel T1-2025 pour le réassureur Africa Re',
  },
  {
    icon: '📈',
    label: 'Placement',
    instruction: 'Analyse le portefeuille d\'actifs et calcule le ratio de solvabilité Art. 337-1 CIMA',
  },
  {
    icon: '🧮',
    label: 'Provisions techniques',
    instruction: 'Calcule toutes les provisions techniques CIMA : PPNA, PSAP avec IBNR Chain-Ladder, PM portefeuille vie',
  },
  {
    icon: '📑',
    label: 'États CIMA',
    instruction: 'Génère la liasse complète des états C1-C12 exercice 2025 et contrôle la cohérence inter-états',
  },
  {
    icon: '🔬',
    label: 'Schéma SI',
    instruction: 'Introspecte le schéma ORASS, cartographie les tables sinistres et polices, et améliore les accès agents',
  },
  {
    icon: '🏭',
    label: 'MetaFactory',
    instruction: 'Analyse la couverture agents vs schéma SI, détecte les workflows non couverts et génère de nouveaux agents autonomes',
  },
]
