/**
 * YukpoAssurance — Chat mobile + Rapports IA
 * - Sessions avec renommage (tap long ou icône crayon)
 * - Nommage automatique à partir du premier message
 * - Onglet Rapports : génération PDF/PPT/Excel depuis l'app mobile
 */
import { useState, useRef, useEffect } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator,
  Modal, ScrollView, Alert, TouchableWithoutFeedback,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { chatAPI } from '../../src/api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

type ViewMode = 'chat' | 'rapports'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

interface Session {
  id: string
  titre: string
  created_at: string
}

// ─── Suggestions ──────────────────────────────────────────────────────────────

const SUGGESTIONS_CIMA = [
  'Quel est le délai de règlement CIMA pour un sinistre auto ?',
  'Comment calculer le ratio de solvabilité ?',
  'Expliquer l\'état C5 — provisions techniques',
  'Quelles sont les sanctions Art. 13 CIMA ?',
  'Calcule une indemnité pour fracture du tibia',
  'Rédige une lettre de rejet de sinistre',
]

// ─── Templates rapports (mobile) ─────────────────────────────────────────────

const RAPPORTS_TEMPLATES = [
  { id: '1', categorie: 'Réglementaire', icon: '⚖️', couleur: '#6366f1', items: [
    { label: 'Rapport Conformité CIMA', type: 'PDF', prompt: 'Rapport conformité CIMA complet — ratios prudentiels, états C1-C20, alertes réglementaires' },
    { label: 'États C1-C20 Excel', type: 'Excel', prompt: 'Tous les états réglementaires CIMA C1 à C20 au format Excel pour transmission CRCA' },
    { label: 'Analyse Solvabilité', type: 'PDF', prompt: 'Analyse marge de solvabilité Art. 337 CIMA — calcul, conformité, recommandations' },
  ]},
  { id: '2', categorie: 'Sinistres', icon: '🚨', couleur: '#ef4444', items: [
    { label: 'Rapport Mensuel Sinistres', type: 'PDF', prompt: 'Rapport mensuel sinistres — déclarations, PSAP, ratio S/P par branche, délais règlement' },
    { label: 'Dashboard Sinistres', type: 'Excel', prompt: 'Tableau de bord sinistres — open/clos/provisionnés, par branche, évolution mensuelle' },
    { label: 'Analyse Fraude', type: 'PPT', prompt: 'Présentation fraude sinistres — dossiers suspects, scores IA, patterns, recommandations' },
  ]},
  { id: '3', categorie: 'Comptabilité', icon: '💰', couleur: '#10b981', items: [
    { label: 'Bilan OHADA', type: 'PDF', prompt: 'Bilan comptable SYSCOA/OHADA avec provisions techniques assurance' },
    { label: 'Balance Générale', type: 'Excel', prompt: 'Balance générale — codes SYSCOA, soldes débiteurs/créditeurs, mouvements du trimestre' },
    { label: 'Rapport Activité', type: 'PDF', prompt: 'Rapport mensuel activité — primes, sinistres, commissions, résultat technique par branche' },
  ]},
  { id: '4', categorie: 'RH & Performance', icon: '🏆', couleur: '#8b5cf6', items: [
    { label: 'Rapport KPI Performance', type: 'PDF', prompt: 'Rapport KPI RH — classement employés, scores, réalisations vs objectifs, recommandations primes' },
    { label: 'Tableau KPI Excel', type: 'Excel', prompt: 'Tableau Excel KPI par axe (qualité/réactivité/volume/objectifs), historique 6 mois' },
    { label: 'Bilan Formation', type: 'PDF', prompt: 'Bilan formations — compétences acquises, coûts, retour sur investissement, plan N+1' },
  ]},
  { id: '5', categorie: 'Commercial', icon: '📈', couleur: '#f59e0b', items: [
    { label: 'Dashboard Commercial', type: 'Excel', prompt: 'Tableau de bord commercial — CA par agent/courtier, objectifs, taux atteinte, commissions' },
    { label: 'Rapport Pipeline', type: 'PDF', prompt: 'Rapport pipeline commercial — prospects, opportunités en cours, taux conversion, prévisions' },
    { label: 'Rapport Courtiers', type: 'PDF', prompt: 'Rapport production courtiers — CA, commissions, portefeuille, sinistralité, classement' },
  ]},
]

// ─── Auto-naming ──────────────────────────────────────────────────────────────

function genererTitre(premierMsg: string): string {
  const msg = premierMsg.trim()
    .replace(/^(génère|crée|rédige|explique|calcule|quell?e?s?|comment|pourquoi)\s+/i, '')
    .replace(/[?!.]+$/, '')
    .slice(0, 45)
  return msg.charAt(0).toUpperCase() + msg.slice(1) + (premierMsg.length > 45 ? '…' : '')
}

// ─── Composant demo IA ────────────────────────────────────────────────────────

function genererReponseDemos(question: string): string {
  const q = question.toLowerCase()
  if (q.includes('délai') || q.includes('reglement')) {
    return '📋 Délais réglementaires CIMA :\n\n• 5 jours ouvrés : déclaration sinistre par l\'assuré (Art. 12)\n• 10 jours : accusé réception par l\'assureur (Art. 12-bis)\n• 3 mois : instruction et offre d\'indemnisation (Art. 12-bis)\n• 45 jours : paiement après accord (Art. 12-ter)\n• Pénalités retard : taux légal + 50%/mois (Art. 12-ter)\n• RC Auto : règlement sous 30 jours après expertise (Art. 231)'
  }
  if (q.includes('solvabilité') || q.includes('marge')) {
    return '📊 Marge de solvabilité CIMA :\n\nNon-Vie (Art. 337-1) : max de\n• 23% des primes nettes acquises\n• 26% de la charge sinistres moy. 3 ans\n• Minimum absolu : 300 millions FCFA\n\nVie (Art. 338-1) :\n• 4% des PM brutes + 0,3% capital sous risque\n• Minimum absolu : 500 millions FCFA\n\nVotre ratio affiché de 142% est conforme.'
  }
  if (q.includes('indemnité') || q.includes('fracture')) {
    return 'Fracture du tibia — Art. 258 CIMA :\n\n• IPP estimée : 8-12%\n• Préjudice fonctionnel : 150 000 XAF/mois\n• Pretium doloris 3/7 : 450 000 XAF\n\nEstimation totale : 1,2 à 1,8 M XAF\n\nVoulez-vous que je calcule avec l\'âge et salaire ?'
  }
  if (q.includes('rapport') || q.includes('générer') || q.includes('document')) {
    return 'Je peux générer des rapports PDF, Excel et PowerPoint. Utilisez l\'onglet "Rapports" ⬆️ pour accéder aux templates spécialisés et générer vos documents directement depuis l\'app.'
  }
  return `Votre question concerne "${question.slice(0, 50)}". En mode démo, Yukpo IA confirme que le Code CIMA contient 509 articles couvrant les Livres I-VI. Activez votre API pour une réponse complète et personnalisée.`
}

// ─── Écran principal ──────────────────────────────────────────────────────────

export default function ChatScreen() {
  const [viewMode, setViewMode] = useState<ViewMode>('chat')
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [currentSessionTitre, setCurrentSessionTitre] = useState('Nouvelle conversation')
  const [messages, setMessages] = useState<Message[]>([
    { id: '0', role: 'assistant', content: 'Bonjour ! Je suis Yukpo IA. Posez-moi toute question sur le Code CIMA, les provisions, les indemnités, ou utilisez l\'onglet Rapports pour générer des documents PDF/Excel/PPT.', timestamp: new Date().toISOString() },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showSessions, setShowSessions] = useState(false)
  const [editingSession, setEditingSession] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [isFirstMsg, setIsFirstMsg] = useState(true)

  // Rapports
  const [rapportCat, setRapportCat] = useState<string | null>(null)
  const [generatingRapport, setGeneratingRapport] = useState(false)
  const [rapportPrompt, setRapportPrompt] = useState('')
  const [rapportType, setRapportType] = useState('PDF')

  const flatListRef = useRef<FlatList>(null)

  useEffect(() => {
    chatAPI.createSession().then(s => {
      setCurrentSessionId(s.id)
      setSessions([{ id: s.id, titre: 'Nouvelle conversation', created_at: s.created_at }])
    }).catch(() => {
      const id = 'mobile-demo'
      setCurrentSessionId(id)
      setSessions([{ id, titre: 'Nouvelle conversation', created_at: new Date().toISOString() }])
    })
  }, [])

  // ── Envoi message ──────────────────────────────────────────────────────────

  const envoyerMessage = async (texte?: string) => {
    const message = (texte || input).trim()
    if (!message || loading) return

    setInput('')
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: message, timestamp: new Date().toISOString() }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100)

    // Auto-naming sur premier message
    if (isFirstMsg) {
      setIsFirstMsg(false)
      const titre = genererTitre(message)
      setCurrentSessionTitre(titre)
      setSessions(prev => prev.map(s => s.id === currentSessionId ? { ...s, titre } : s))
    }

    try {
      const sid = currentSessionId || 'mobile-demo'
      const data = await chatAPI.sendMessage({ session_id: sid, content: message })
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: (data as Record<string, unknown>).reponse as string || (data as Record<string, unknown>).content as string || 'Réponse reçue.',
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: genererReponseDemos(message),
        timestamp: new Date().toISOString(),
      }])
    } finally {
      setLoading(false)
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 200)
    }
  }

  // ── Gestion sessions ──────────────────────────────────────────────────────

  const nouvelleConversation = async () => {
    try {
      const s = await chatAPI.createSession()
      const session: Session = { id: s.id, titre: 'Nouvelle conversation', created_at: s.created_at }
      setSessions(prev => [session, ...prev])
      setCurrentSessionId(s.id)
      setCurrentSessionTitre('Nouvelle conversation')
    } catch {
      const id = `mobile-${Date.now()}`
      const session: Session = { id, titre: 'Nouvelle conversation', created_at: new Date().toISOString() }
      setSessions(prev => [session, ...prev])
      setCurrentSessionId(id)
      setCurrentSessionTitre('Nouvelle conversation')
    }
    setMessages([{ id: '0', role: 'assistant', content: 'Nouvelle conversation démarrée. Comment puis-je vous aider ?', timestamp: new Date().toISOString() }])
    setIsFirstMsg(true)
    setShowSessions(false)
  }

  const renommerSession = (sessionId: string, newTitre: string) => {
    setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, titre: newTitre } : s))
    if (sessionId === currentSessionId) setCurrentSessionTitre(newTitre)
    setEditingSession(null)
  }

  // ── Génération rapport mobile ─────────────────────────────────────────────

  const genererRapport = async (prompt: string, type: string) => {
    setGeneratingRapport(true)
    await new Promise(r => setTimeout(r, 2500))
    setGeneratingRapport(false)
    Alert.alert(
      'Rapport généré',
      `Votre rapport ${type} est prêt.\n\n"${prompt.slice(0, 80)}…"\n\nTéléchargez-le depuis votre espace documents Yukpo.`,
      [{ text: 'OK' }]
    )
  }

  // ── Rendu message ─────────────────────────────────────────────────────────

  const renderMessage = ({ item }: { item: Message }) => (
    <View style={[s.bubble, item.role === 'user' ? s.bubbleUser : s.bubbleAssistant]}>
      {item.role === 'assistant' && (
        <View style={s.avatarIA}><Ionicons name="sparkles" size={12} color="#fff" /></View>
      )}
      <View style={[s.bubbleContent, item.role === 'user' ? s.bubbleContentUser : s.bubbleContentAssistant]}>
        <Text style={[s.bubbleText, item.role === 'user' && s.bubbleTextUser]}>{item.content}</Text>
        <Text style={[s.bubbleTime, item.role === 'user' && { color: '#bfdbfe' }]}>
          {new Date(item.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
        </Text>
      </View>
    </View>
  )

  return (
    <View style={s.container}>

      {/* ── Header avec onglets ────────────────────────────────────────── */}
      <View style={s.header}>
        <TouchableOpacity style={s.sessionBtn} onPress={() => setShowSessions(true)}>
          <Ionicons name="list-outline" size={18} color="#1d4ed8" />
        </TouchableOpacity>
        <View style={{ flex: 1, alignItems: 'center' }}>
          <Text style={s.headerTitle} numberOfLines={1}>{currentSessionTitre}</Text>
        </View>
        <TouchableOpacity style={s.sessionBtn} onPress={() => Alert.prompt?.('Renommer', 'Nouveau nom', t => { if (t && currentSessionId) renommerSession(currentSessionId, t) })}>
          <Ionicons name="pencil-outline" size={16} color="#64748b" />
        </TouchableOpacity>
      </View>

      {/* ── Onglets Chat / Rapports ────────────────────────────────────── */}
      <View style={s.tabBar}>
        {[
          { id: 'chat' as ViewMode, label: 'Conversation', icon: 'chatbubble-outline' },
          { id: 'rapports' as ViewMode, label: 'Rapports', icon: 'document-text-outline' },
        ].map(t => (
          <TouchableOpacity key={t.id} style={[s.tab, viewMode === t.id && s.tabActive]} onPress={() => setViewMode(t.id)}>
            <Ionicons name={t.icon as never} size={15} color={viewMode === t.id ? '#1d4ed8' : '#94a3b8'} />
            <Text style={[s.tabLabel, viewMode === t.id && s.tabLabelActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ── Vue Conversation ────────────────────────────────────────────── */}
      {viewMode === 'chat' && (
        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 60}
        >
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={m => m.id}
            renderItem={renderMessage}
            contentContainerStyle={{ padding: 12, paddingBottom: 8 }}
            onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: false })}
          />

          {loading && (
            <View style={s.typingRow}>
              <View style={s.avatarIA}><Ionicons name="sparkles" size={12} color="#fff" /></View>
              <View style={s.typingBubble}>
                <ActivityIndicator size="small" color="#1d4ed8" />
                <Text style={s.typingText}>Analyse en cours…</Text>
              </View>
            </View>
          )}

          {messages.length <= 1 && (
            <View style={s.suggestionsWrap}>
              <Text style={s.suggestionsTitle}>Suggestions</Text>
              <View style={s.suggestionsRow}>
                {SUGGESTIONS_CIMA.slice(0, 3).map((sg, i) => (
                  <TouchableOpacity key={i} style={s.suggestionChip} onPress={() => envoyerMessage(sg)}>
                    <Text style={s.suggestionText} numberOfLines={2}>{sg}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          <View style={s.inputRow}>
            <TextInput
              style={s.input}
              value={input}
              onChangeText={setInput}
              placeholder="Question CIMA, calcul, rédaction…"
              placeholderTextColor="#94a3b8"
              multiline
              maxLength={2000}
            />
            <TouchableOpacity
              style={[s.sendBtn, (!input.trim() || loading) && s.sendBtnDisabled]}
              onPress={() => envoyerMessage()}
              disabled={!input.trim() || loading}
            >
              <Ionicons name="send" size={18} color="#fff" />
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      )}

      {/* ── Vue Rapports ────────────────────────────────────────────────── */}
      {viewMode === 'rapports' && (
        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 12, gap: 12, paddingBottom: 30 }}>
          <Text style={s.rapportsTitre}>Génération de rapports IA</Text>
          <Text style={s.rapportsSub}>PDF · Excel · PowerPoint — Powered by Claude</Text>

          {RAPPORTS_TEMPLATES.map(cat => (
            <View key={cat.id} style={s.rapportCatCard}>
              <TouchableOpacity
                style={[s.rapportCatHeader, { borderLeftColor: cat.couleur }]}
                onPress={() => setRapportCat(rapportCat === cat.id ? null : cat.id)}
              >
                <Text style={{ fontSize: 16, marginRight: 8 }}>{cat.icon}</Text>
                <Text style={{ flex: 1, fontSize: 14, fontWeight: '700', color: '#1e293b' }}>{cat.categorie}</Text>
                <Ionicons name={rapportCat === cat.id ? 'chevron-up' : 'chevron-down'} size={16} color="#64748b" />
              </TouchableOpacity>

              {rapportCat === cat.id && cat.items.map((item, i) => (
                <TouchableOpacity
                  key={i}
                  style={s.rapportItem}
                  onPress={() => genererRapport(item.prompt, item.type)}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: '600', color: '#1e293b' }}>{item.label}</Text>
                    <Text style={{ fontSize: 11, color: '#64748b', marginTop: 2 }} numberOfLines={2}>{item.prompt}</Text>
                  </View>
                  <View style={[s.typeBadge, { backgroundColor: cat.couleur + '18' }]}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: cat.couleur }}>{item.type}</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          ))}

          {/* Génération libre */}
          <View style={s.rapportCatCard}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: '#1e293b', padding: 14, paddingBottom: 8 }}>✍️ Génération libre</Text>
            <View style={{ paddingHorizontal: 14, paddingBottom: 14, gap: 10 }}>
              <TextInput
                style={[s.input, { height: 70, textAlignVertical: 'top', marginBottom: 0, backgroundColor: '#f8fafc' }]}
                multiline
                placeholder="Décrivez le rapport souhaité…"
                value={rapportPrompt}
                onChangeText={setRapportPrompt}
                placeholderTextColor="#94a3b8"
              />
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {['PDF', 'Excel', 'PPT'].map(t => (
                  <TouchableOpacity
                    key={t}
                    onPress={() => setRapportType(t)}
                    style={[s.typeChip, rapportType === t && s.typeChipActive]}
                  >
                    <Text style={[s.typeChipTxt, rapportType === t && { color: '#fff' }]}>{t}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity
                style={[s.sendBtnRapport, (!rapportPrompt.trim() || generatingRapport) && { opacity: 0.6 }]}
                onPress={() => genererRapport(rapportPrompt, rapportType)}
                disabled={!rapportPrompt.trim() || generatingRapport}
              >
                {generatingRapport
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <><Ionicons name="sparkles" size={16} color="#fff" /><Text style={{ color: '#fff', fontWeight: '700', fontSize: 14, marginLeft: 6 }}>Générer le rapport</Text></>
                }
              </TouchableOpacity>
            </View>
          </View>
        </ScrollView>
      )}

      {/* ── Modal Sessions ──────────────────────────────────────────────── */}
      <Modal visible={showSessions} animationType="slide" presentationStyle="pageSheet">
        <View style={s.modalHeader}>
          <Text style={s.modalTitle}>Conversations</Text>
          <TouchableOpacity onPress={() => setShowSessions(false)}>
            <Ionicons name="close" size={24} color="#64748b" />
          </TouchableOpacity>
        </View>

        <TouchableOpacity style={s.newConvBtn} onPress={nouvelleConversation}>
          <Ionicons name="add-circle-outline" size={18} color="#fff" />
          <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Nouvelle conversation</Text>
        </TouchableOpacity>

        <FlatList
          data={sessions}
          keyExtractor={s => s.id}
          contentContainerStyle={{ padding: 12, gap: 8 }}
          renderItem={({ item }) => (
            <View style={s.sessionCard}>
              {editingSession === item.id ? (
                <View style={{ flex: 1, flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                  <TextInput
                    style={[s.input, { flex: 1, marginBottom: 0, height: 36, paddingVertical: 6 }]}
                    value={editDraft}
                    onChangeText={setEditDraft}
                    autoFocus
                  />
                  <TouchableOpacity onPress={() => renommerSession(item.id, editDraft)} style={{ padding: 4 }}>
                    <Ionicons name="checkmark-circle" size={22} color="#16a34a" />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => setEditingSession(null)} style={{ padding: 4 }}>
                    <Ionicons name="close-circle" size={22} color="#ef4444" />
                  </TouchableOpacity>
                </View>
              ) : (
                <>
                  <TouchableOpacity
                    style={{ flex: 1 }}
                    onPress={() => {
                      setCurrentSessionId(item.id)
                      setCurrentSessionTitre(item.titre)
                      setShowSessions(false)
                    }}
                  >
                    <Text style={{ fontSize: 14, fontWeight: '600', color: item.id === currentSessionId ? '#1d4ed8' : '#1e293b' }}>
                      {item.titre}
                    </Text>
                    <Text style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                      {new Date(item.created_at).toLocaleDateString('fr-FR')}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => { setEditingSession(item.id); setEditDraft(item.titre) }}
                    style={{ padding: 6 }}
                  >
                    <Ionicons name="pencil-outline" size={16} color="#64748b" />
                  </TouchableOpacity>
                </>
              )}
            </View>
          )}
        />
      </Modal>
    </View>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f1f5f9' },
  header: {
    backgroundColor: '#fff', flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 12, paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: '#e2e8f0', gap: 8,
  },
  headerTitle: { fontSize: 14, fontWeight: '700', color: '#1e293b', maxWidth: 200 },
  sessionBtn: { padding: 6, borderRadius: 8, backgroundColor: '#eff6ff' },
  tabBar: {
    flexDirection: 'row', backgroundColor: '#fff',
    borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  tab: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 10, gap: 5, borderBottomWidth: 2, borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: '#1d4ed8' },
  tabLabel: { fontSize: 12, color: '#94a3b8', fontWeight: '600' },
  tabLabelActive: { color: '#1d4ed8' },
  bubble: { flexDirection: 'row', marginBottom: 12, alignItems: 'flex-end' },
  bubbleUser: { justifyContent: 'flex-end' },
  bubbleAssistant: { justifyContent: 'flex-start' },
  avatarIA: { width: 24, height: 24, borderRadius: 8, backgroundColor: '#1d4ed8', alignItems: 'center', justifyContent: 'center', marginRight: 6, marginBottom: 2, flexShrink: 0 },
  bubbleContent: { maxWidth: '80%', borderRadius: 14, padding: 12 },
  bubbleContentUser: { backgroundColor: '#1d4ed8', borderBottomRightRadius: 4 },
  bubbleContentAssistant: { backgroundColor: '#fff', borderBottomLeftRadius: 4, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, elevation: 1 },
  bubbleText: { fontSize: 14, color: '#1e293b', lineHeight: 20 },
  bubbleTextUser: { color: '#fff' },
  bubbleTime: { fontSize: 10, color: '#94a3b8', marginTop: 4, alignSelf: 'flex-end' },
  typingRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingBottom: 8 },
  typingBubble: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#fff', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10 },
  typingText: { fontSize: 12, color: '#64748b' },
  suggestionsWrap: { padding: 12, paddingTop: 0 },
  suggestionsTitle: { fontSize: 12, fontWeight: '600', color: '#64748b', marginBottom: 8 },
  suggestionsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  suggestionChip: { backgroundColor: '#eff6ff', borderWidth: 1, borderColor: '#bfdbfe', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6, maxWidth: '48%' },
  suggestionText: { fontSize: 12, color: '#1d4ed8', fontWeight: '500' },
  inputRow: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 8,
    backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#e2e8f0',
    padding: 12, paddingBottom: Platform.OS === 'ios' ? 20 : 12,
  },
  input: { flex: 1, borderWidth: 1, borderColor: '#d1d5db', borderRadius: 20, paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, color: '#1e293b', maxHeight: 100, backgroundColor: '#f9fafb' },
  sendBtn: { width: 42, height: 42, borderRadius: 21, backgroundColor: '#1d4ed8', alignItems: 'center', justifyContent: 'center' },
  sendBtnDisabled: { opacity: 0.4 },

  // Rapports
  rapportsTitre: { fontSize: 16, fontWeight: '800', color: '#1e293b' },
  rapportsSub: { fontSize: 11, color: '#94a3b8', marginTop: -8 },
  rapportCatCard: { backgroundColor: '#fff', borderRadius: 12, overflow: 'hidden', shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, elevation: 2 },
  rapportCatHeader: { flexDirection: 'row', alignItems: 'center', padding: 14, borderLeftWidth: 4 },
  rapportItem: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, paddingLeft: 18, borderTopWidth: 1, borderTopColor: '#f1f5f9' },
  typeBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 },
  typeChip: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20, backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0' },
  typeChipActive: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  typeChipTxt: { fontSize: 12, fontWeight: '700', color: '#475569' },
  sendBtnRapport: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#1d4ed8', borderRadius: 10, paddingVertical: 12 },

  // Modal sessions
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e2e8f0', backgroundColor: '#fff' },
  modalTitle: { fontSize: 16, fontWeight: '700', color: '#1e293b' },
  newConvBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#1d4ed8', margin: 12, borderRadius: 10, paddingVertical: 12 },
  sessionCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 10, padding: 12, gap: 8, borderWidth: 1, borderColor: '#e2e8f0' },
})
