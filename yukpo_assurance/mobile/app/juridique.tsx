/**
 * Service Juridique — Mobile
 * Litiges · Assistant IA juridique CIMA · Correspondances · Modèles
 */
import { useState, useRef } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'

// ─── Types ─────────────────────────────────────────────────────────────────────

type OngletType = 'dashboard' | 'litiges' | 'assistant' | 'correspondances'

type StatutDossier = 'ouvert' | 'en_instruction' | 'audience' | 'transige' | 'clos_favorable' | 'clos_defavorable'

interface DossierLitige {
  id: string
  reference: string
  titre: string
  partie_adverse: string
  montant: number
  statut: StatutDossier
  echeance?: string
  risque: 'faible' | 'moyen' | 'eleve'
  juridiction?: string
}

interface MessageIA {
  role: 'user' | 'assistant'
  content: string
}

// ─── Données démo ────────────────────────────────────────────────────────────────

const DOSSIERS_DEMO: DossierLitige[] = [
  {
    id: '1',
    reference: 'JUR-2026-001',
    titre: 'Contestation indemnisation sinistre auto — Moulaye Ahmed',
    partie_adverse: 'Moulaye Ahmed & Associés',
    montant: 8500000,
    statut: 'en_instruction',
    echeance: '2026-04-25',
    risque: 'moyen',
    juridiction: 'TGI Douala',
  },
  {
    id: '2',
    reference: 'JUR-2026-002',
    titre: 'Arbitrage CIMA — Délai règlement sinistre incendie',
    partie_adverse: 'Commission Régionale CIMA',
    montant: 0,
    statut: 'audience',
    echeance: '2026-04-18',
    risque: 'eleve',
    juridiction: 'Commission CIMA',
  },
  {
    id: '3',
    reference: 'JUR-2026-003',
    titre: 'Recours subrogatoire — Sinistre transport',
    partie_adverse: 'CAMTRANS SARL',
    montant: 12000000,
    statut: 'ouvert',
    echeance: '2026-05-10',
    risque: 'moyen',
    juridiction: 'TGI Yaoundé',
  },
  {
    id: '4',
    reference: 'JUR-2025-018',
    titre: 'Litige commission courtier — Cabinet ASCO',
    partie_adverse: 'Cabinet ASCO',
    montant: 2300000,
    statut: 'transige',
    risque: 'faible',
  },
]

const STATUT_COULEUR: Record<StatutDossier, { bg: string; text: string; label: string }> = {
  ouvert: { bg: '#dbeafe', text: '#1d4ed8', label: 'Ouvert' },
  en_instruction: { bg: '#fef3c7', text: '#b45309', label: 'En instruction' },
  audience: { bg: '#ede9fe', text: '#6d28d9', label: 'Audience' },
  transige: { bg: '#d1fae5', text: '#065f46', label: 'Transigé' },
  clos_favorable: { bg: '#d1fae5', text: '#065f46', label: 'Favorable' },
  clos_defavorable: { bg: '#fee2e2', text: '#b91c1c', label: 'Défavorable' },
}

const RISQUE_COULEUR = {
  faible: { bg: '#dcfce7', text: '#15803d' },
  moyen: { bg: '#fef3c7', text: '#b45309' },
  eleve: { bg: '#fee2e2', text: '#b91c1c' },
}

const fmt = (n: number) => n > 0 ? n.toLocaleString('fr-FR') + ' XAF' : '—'

const QUESTIONS_SUGGEREES = [
  'Délais de prescription Code CIMA ?',
  'Comment rédiger une mise en demeure ?',
  'Conditions d\'un recours subrogatoire ?',
  'Procédure arbitrage CIMA Art. 308 ?',
  'Délai règlement sinistre Art. 12 CIMA ?',
]

const TEMPLATES_JURIDIQUES = [
  { id: 'mise_en_demeure', label: 'Mise en demeure', icon: 'warning-outline' },
  { id: 'accord_transactionnel', label: 'Accord transactionnel', icon: 'handshake-outline' },
  { id: 'recours_cima', label: 'Recours CIMA', icon: 'shield-checkmark-outline' },
  { id: 'convention_subrogation', label: 'Convention de subrogation', icon: 'swap-horizontal-outline' },
  { id: 'assignation', label: 'Notification assignation', icon: 'document-text-outline' },
  { id: 'requete_arbitrage', label: 'Requête en arbitrage', icon: 'scale-outline' },
]

// ─── Dashboard ─────────────────────────────────────────────────────────────────

function OngletDashboard({ dossiers }: { dossiers: DossierLitige[] }) {
  const actifs = dossiers.filter(d => !['clos_favorable', 'clos_defavorable', 'transige'].includes(d.statut))
  const totalLitige = dossiers.reduce((s, d) => s + d.montant, 0)
  const enAudience = dossiers.filter(d => d.statut === 'audience').length
  const risqueEleve = dossiers.filter(d => d.risque === 'eleve').length

  const today = new Date()
  const echeances = dossiers
    .filter(d => d.echeance)
    .map(d => ({ ...d, diff: Math.ceil((new Date(d.echeance!).getTime() - today.getTime()) / 86400000) }))
    .sort((a, b) => a.diff - b.diff)

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 16 }} showsVerticalScrollIndicator={false}>
      {/* KPIs */}
      <View style={styles.grid2}>
        {[
          { label: 'Dossiers actifs', value: actifs.length.toString(), icon: 'briefcase-outline', color: '#1d4ed8', bg: '#dbeafe' },
          { label: 'Montant en litige', value: fmt(totalLitige), icon: 'scale-outline', color: '#b45309', bg: '#fef3c7' },
          { label: 'Audiences', value: enAudience.toString(), icon: 'shield-outline', color: '#6d28d9', bg: '#ede9fe' },
          { label: 'Risque élevé', value: risqueEleve.toString(), icon: 'warning-outline', color: '#b91c1c', bg: '#fee2e2' },
        ].map(k => (
          <View key={k.label} style={[styles.kpiCard, { flex: 1 }]}>
            <View style={[styles.kpiIcon, { backgroundColor: k.bg }]}>
              <Ionicons name={k.icon as any} size={18} color={k.color} />
            </View>
            <Text style={styles.kpiValue}>{k.value}</Text>
            <Text style={styles.kpiLabel}>{k.label}</Text>
          </View>
        ))}
      </View>

      {/* Alerte CIMA */}
      <View style={styles.alertBox}>
        <Ionicons name="information-circle-outline" size={18} color="#b45309" style={{ marginTop: 1 }} />
        <Text style={styles.alertText}>
          <Text style={{ fontWeight: '700' }}>Délais CIMA :</Text> Règlement sinistre 30j (Art. 12) · Rejet motivé par écrit (Art. 18) · Arbitrage avant juridiction (Art. 308)
        </Text>
      </View>

      {/* Échéances */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Prochaines échéances</Text>
        {echeances.map(d => (
          <View key={d.id} style={styles.echeanceRow}>
            <View style={[styles.echeanceDay, {
              backgroundColor: d.diff < 7 ? '#fee2e2' : d.diff < 30 ? '#fef3c7' : '#f3f4f6',
            }]}>
              <Text style={[styles.echeanceDayNum, { color: d.diff < 7 ? '#b91c1c' : d.diff < 30 ? '#b45309' : '#4b5563' }]}>
                {d.diff < 0 ? '!' : d.diff}
              </Text>
              <Text style={[styles.echeanceDayLabel, { color: d.diff < 7 ? '#b91c1c' : d.diff < 30 ? '#b45309' : '#9ca3af' }]}>
                {d.diff < 0 ? 'Passée' : 'j'}
              </Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.echeanceTitre} numberOfLines={1}>{d.titre}</Text>
              <Text style={styles.echeanceRef}>{d.reference} · {d.juridiction || 'Interne'}</Text>
            </View>
            <View style={[styles.badge, { backgroundColor: STATUT_COULEUR[d.statut].bg }]}>
              <Text style={[styles.badgeText, { color: STATUT_COULEUR[d.statut].text }]}>
                {STATUT_COULEUR[d.statut].label}
              </Text>
            </View>
          </View>
        ))}
      </View>
    </ScrollView>
  )
}

// ─── Litiges ─────────────────────────────────────────────────────────────────────

function OngletLitiges({ dossiers }: { dossiers: DossierLitige[] }) {
  const [selected, setSelected] = useState<DossierLitige | null>(null)

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }} showsVerticalScrollIndicator={false}>
      {dossiers.map(d => (
        <TouchableOpacity key={d.id} style={styles.card} onPress={() => setSelected(d === selected ? null : d)}>
          <View style={styles.rowBetween}>
            <Text style={styles.refText}>{d.reference}</Text>
            <View style={[styles.badge, { backgroundColor: RISQUE_COULEUR[d.risque].bg }]}>
              <Text style={[styles.badgeText, { color: RISQUE_COULEUR[d.risque].text }]}>
                Risque {d.risque}
              </Text>
            </View>
          </View>
          <Text style={styles.dossTitre} numberOfLines={2}>{d.titre}</Text>
          <View style={styles.rowBetween}>
            <Text style={styles.partieText}>{d.partie_adverse}</Text>
            <View style={[styles.badge, { backgroundColor: STATUT_COULEUR[d.statut].bg }]}>
              <Text style={[styles.badgeText, { color: STATUT_COULEUR[d.statut].text }]}>
                {STATUT_COULEUR[d.statut].label}
              </Text>
            </View>
          </View>

          {selected?.id === d.id && (
            <View style={styles.detailBox}>
              <View style={styles.grid2}>
                <View>
                  <Text style={styles.detailLabel}>Montant</Text>
                  <Text style={styles.detailValue}>{fmt(d.montant)}</Text>
                </View>
                <View>
                  <Text style={styles.detailLabel}>Juridiction</Text>
                  <Text style={styles.detailValue}>{d.juridiction || '—'}</Text>
                </View>
                <View>
                  <Text style={styles.detailLabel}>Prochaine échéance</Text>
                  <Text style={styles.detailValue}>
                    {d.echeance ? new Date(d.echeance).toLocaleDateString('fr-FR') : '—'}
                  </Text>
                </View>
              </View>
            </View>
          )}
        </TouchableOpacity>
      ))}
    </ScrollView>
  )
}

// ─── Assistant IA ─────────────────────────────────────────────────────────────────

function OngletAssistant({ dossiers }: { dossiers: DossierLitige[] }) {
  const [messages, setMessages] = useState<MessageIA[]>([
    { role: 'assistant', content: 'Bonjour ! Je suis Yukpo Juridique — assistant IA spécialisé droit des assurances CIMA. Posez-moi vos questions : délais, recours, rédaction de lettres légales, procédures, jurisprudence…' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<ScrollView>(null)

  const envoyer = async (msg?: string) => {
    const texte = msg || input.trim()
    if (!texte) return
    setMessages(prev => [...prev, { role: 'user', content: texte }])
    setInput('')
    setLoading(true)
    setTimeout(() => {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Réponse IA (mode démo) sur : "${texte}"\n\n**Éléments Code CIMA :**\n• Art. 12 : Délai règlement 30 jours après production pièces\n• Art. 13 : Prescription biennale\n• Art. 18 : Rejet motivé obligatoirement\n• Art. 308 : Arbitrage CIMA avant juridiction\n\nConnectez le backend YukpoPro pour une réponse complète.`,
      }])
      setLoading(false)
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100)
    }, 1200)
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      {/* Questions suggérées */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 8, gap: 8 }}
      >
        {QUESTIONS_SUGGEREES.map(q => (
          <TouchableOpacity key={q} onPress={() => envoyer(q)} style={styles.qSuggeree}>
            <Text style={styles.qSuggereeText}>{q}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Messages */}
      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: 12, gap: 12 }}
        showsVerticalScrollIndicator={false}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
      >
        {messages.map((m, i) => (
          <View key={i} style={[styles.msgRow, m.role === 'user' ? styles.msgUser : styles.msgAI]}>
            {m.role === 'assistant' && (
              <View style={styles.msgAvatar}>
                <Ionicons name="scale-outline" size={14} color="#7c3aed" />
              </View>
            )}
            <View style={[styles.msgBubble, m.role === 'user' ? styles.msgBubbleUser : styles.msgBubbleAI]}>
              <Text style={[styles.msgText, m.role === 'user' ? { color: '#fff' } : { color: '#1f2937' }]}>
                {m.content}
              </Text>
            </View>
          </View>
        ))}
        {loading && (
          <View style={[styles.msgRow, styles.msgAI]}>
            <View style={styles.msgAvatar}>
              <Ionicons name="scale-outline" size={14} color="#7c3aed" />
            </View>
            <View style={[styles.msgBubble, styles.msgBubbleAI]}>
              <ActivityIndicator size="small" color="#7c3aed" />
            </View>
          </View>
        )}
      </ScrollView>

      {/* Input */}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.chatInput}
          placeholder="Posez votre question juridique CIMA…"
          placeholderTextColor="#9ca3af"
          value={input}
          onChangeText={setInput}
          multiline
          editable={!loading}
        />
        <TouchableOpacity
          style={[styles.sendBtn, (!input.trim() || loading) && { opacity: 0.4 }]}
          onPress={() => envoyer()}
          disabled={!input.trim() || loading}
        >
          <Ionicons name="sparkles-outline" size={18} color="#fff" />
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  )
}

// ─── Correspondances ──────────────────────────────────────────────────────────────

function OngletCorrespondances({ dossiers }: { dossiers: DossierLitige[] }) {
  const [templateChoisi, setTemplateChoisi] = useState<string | null>(null)
  const [dossierRef, setDossierRef] = useState('')
  const [contexte, setContexte] = useState('')
  const [lettre, setLettre] = useState('')
  const [loading, setLoading] = useState(false)

  const generer = () => {
    setLoading(true)
    const dossier = dossiers.find(d => d.id === dossierRef)
    const template = TEMPLATES_JURIDIQUES.find(t => t.id === templateChoisi)
    setTimeout(() => {
      const today = new Date().toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' })
      const ref = dossier?.reference || 'N/A'
      const partie = dossier?.partie_adverse || contexte || '[Partie adverse]'
      const lettres: Record<string, string> = {
        mise_en_demeure: `Douala, le ${today}\n\nMISE EN DEMEURE\n\nMonsieur/Madame ${partie},\n\nPar la présente, nous vous mettons en demeure de vous acquitter de vos obligations relatives au dossier ${ref} dans un délai de 15 jours.\n\nA défaut, nous engagerons toute procédure judiciaire utile à la protection de nos intérêts.\n\nSous toutes réserves.\n\nLe Service Juridique`,
        accord_transactionnel: `Douala, le ${today}\n\nACCORD TRANSACTIONNEL\n\nEntre notre compagnie et ${partie},\n\nDossier référence : ${ref}\n\nIl est convenu ce qui suit :\nArt. 1 : Versement d'une indemnité transactionnelle\nArt. 2 : Renonciation à tout recours judiciaire\nArt. 3 : Force de chose jugée\n\nFait à Douala,\nLe Service Juridique`,
        recours_cima: `Douala, le ${today}\n\nà l'attention de la Commission Régionale CIMA\n\nObjet : Recours — Dossier ${ref}\n\nMonsieur le Président,\n\nNous vous saisissons conformément à l'article 308 du Code CIMA concernant notre dossier ${ref} opposant notre compagnie à ${partie}.\n\n${contexte || 'Nous sollicitons votre intervention dans le règlement de ce différend.'}\n\nVeuillez agréer, Monsieur le Président, nos plus respectueuses salutations.\n\nLe Directeur Juridique`,
      }
      setLettre(lettres[templateChoisi || ''] || `Douala, le ${today}\n\nObjet : ${template?.label} — Dossier ${ref}\n\n${contexte}\n\nCordialement,\nLe Service Juridique`)
      setLoading(false)
    }, 1000)
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }} showsVerticalScrollIndicator={false}>
      {/* Sélection template */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Choisir un modèle</Text>
        <View style={styles.grid2}>
          {TEMPLATES_JURIDIQUES.map(t => (
            <TouchableOpacity
              key={t.id}
              onPress={() => setTemplateChoisi(t.id)}
              style={[styles.templateCard, templateChoisi === t.id && styles.templateCardSelected]}
            >
              <Ionicons name={t.icon as any} size={20} color={templateChoisi === t.id ? '#7c3aed' : '#6b7280'} />
              <Text style={[styles.templateLabel, templateChoisi === t.id && { color: '#7c3aed' }]}>{t.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {templateChoisi && (
        <View style={styles.card}>
          {/* Dossier */}
          <Text style={styles.fieldLabel}>Dossier concerné</Text>
          <View style={styles.pickerWrapper}>
            {dossiers.map(d => (
              <TouchableOpacity
                key={d.id}
                onPress={() => setDossierRef(dossierRef === d.id ? '' : d.id)}
                style={[styles.pickerOption, dossierRef === d.id && styles.pickerOptionSelected]}
              >
                <Text style={[styles.pickerOptionText, dossierRef === d.id && { color: '#7c3aed', fontWeight: '600' }]} numberOfLines={1}>
                  {d.reference} — {d.titre}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Contexte */}
          <Text style={[styles.fieldLabel, { marginTop: 8 }]}>Contexte / détails</Text>
          <TextInput
            style={styles.textareaSmall}
            placeholder="Précisez le contexte, montants, motifs…"
            placeholderTextColor="#9ca3af"
            value={contexte}
            onChangeText={setContexte}
            multiline
            numberOfLines={3}
          />

          <TouchableOpacity
            style={[styles.btnPrimary, loading && { opacity: 0.6 }]}
            onPress={generer}
            disabled={loading}
          >
            <Ionicons name="sparkles-outline" size={16} color="#fff" />
            <Text style={styles.btnPrimaryText}>
              {loading ? 'Rédaction en cours…' : 'Générer avec YukpoPro'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {lettre !== '' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Lettre générée</Text>
          <TextInput
            style={styles.textarea}
            value={lettre}
            onChangeText={setLettre}
            multiline
          />
          <View style={styles.rowGap8}>
            <TouchableOpacity
              style={[styles.btnPrimary, { flex: 1 }]}
              onPress={() => Alert.alert('Envoi', 'La lettre sera envoyée via le système de messagerie.')}
            >
              <Ionicons name="send-outline" size={14} color="#fff" />
              <Text style={styles.btnPrimaryText}>Envoyer</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.btnSecondary, { flex: 1 }]}
              onPress={() => Alert.alert('Export', 'Export PDF disponible sur web.')}
            >
              <Ionicons name="download-outline" size={14} color="#374151" />
              <Text style={styles.btnSecondaryText}>Exporter</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </ScrollView>
  )
}

// ─── Page principale ─────────────────────────────────────────────────────────────

export default function JuridiquePage() {
  const router = useRouter()
  const [onglet, setOnglet] = useState<OngletType>('dashboard')
  const [dossiers] = useState<DossierLitige[]>(DOSSIERS_DEMO)

  const ONGLETS: { key: OngletType; label: string; icon: string }[] = [
    { key: 'dashboard', label: 'Dashboard', icon: 'grid-outline' },
    { key: 'litiges', label: 'Litiges', icon: 'scale-outline' },
    { key: 'assistant', label: 'Assistant IA', icon: 'sparkles-outline' },
    { key: 'correspondances', label: 'Lettres', icon: 'document-text-outline' },
  ]

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#1f2937" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Service Juridique</Text>
          <Text style={styles.headerSub}>Litiges · IA CIMA · Correspondances</Text>
        </View>
        <View style={styles.headerBadge}>
          <Ionicons name="scale-outline" size={16} color="#7c3aed" />
        </View>
      </View>

      {/* Onglets */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBar} contentContainerStyle={{ paddingHorizontal: 12 }}>
        {ONGLETS.map(o => (
          <TouchableOpacity
            key={o.key}
            onPress={() => setOnglet(o.key)}
            style={[styles.tabBtn, onglet === o.key && styles.tabBtnActive]}
          >
            <Ionicons name={o.icon as any} size={14} color={onglet === o.key ? '#7c3aed' : '#6b7280'} />
            <Text style={[styles.tabLabel, onglet === o.key && styles.tabLabelActive]}>{o.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Contenu */}
      <View style={{ flex: 1 }}>
        {onglet === 'dashboard' && <OngletDashboard dossiers={dossiers} />}
        {onglet === 'litiges' && <OngletLitiges dossiers={dossiers} />}
        {onglet === 'assistant' && <OngletAssistant dossiers={dossiers} />}
        {onglet === 'correspondances' && <OngletCorrespondances dossiers={dossiers} />}
      </View>
    </View>
  )
}

// ─── Styles ──────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },

  header: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 16, paddingTop: 52, paddingBottom: 12,
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#f3f4f6',
  },
  backBtn: { padding: 4 },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#1f2937' },
  headerSub: { fontSize: 11, color: '#6b7280', marginTop: 1 },
  headerBadge: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: '#ede9fe', alignItems: 'center', justifyContent: 'center',
  },

  tabBar: {
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#f3f4f6',
    maxHeight: 48, flexGrow: 0,
  },
  tabBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 14, paddingVertical: 12, marginRight: 4,
    borderBottomWidth: 2, borderBottomColor: 'transparent',
  },
  tabBtnActive: { borderBottomColor: '#7c3aed' },
  tabLabel: { fontSize: 13, color: '#6b7280', fontWeight: '500' },
  tabLabelActive: { color: '#7c3aed', fontWeight: '600' },

  card: {
    backgroundColor: '#fff', borderRadius: 16,
    borderWidth: 1, borderColor: '#e5e7eb',
    padding: 14, gap: 10,
  },
  cardTitle: { fontSize: 13, fontWeight: '700', color: '#1f2937' },

  grid2: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },

  kpiCard: {
    backgroundColor: '#fff', borderRadius: 14,
    borderWidth: 1, borderColor: '#e5e7eb',
    padding: 12, gap: 6, minWidth: '45%',
  },
  kpiIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  kpiValue: { fontSize: 15, fontWeight: '800', color: '#1f2937' },
  kpiLabel: { fontSize: 10, color: '#6b7280' },

  alertBox: {
    backgroundColor: '#fefce8', borderWidth: 1, borderColor: '#fcd34d',
    borderRadius: 12, padding: 12, flexDirection: 'row', gap: 8, alignItems: 'flex-start',
  },
  alertText: { flex: 1, fontSize: 11, color: '#92400e', lineHeight: 16 },

  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 20 },
  badgeText: { fontSize: 10, fontWeight: '600' },

  echeanceRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  echeanceDay: {
    width: 40, height: 40, borderRadius: 10,
    alignItems: 'center', justifyContent: 'center',
  },
  echeanceDayNum: { fontSize: 14, fontWeight: '800', lineHeight: 16 },
  echeanceDayLabel: { fontSize: 9 },
  echeanceTitre: { fontSize: 12, fontWeight: '600', color: '#1f2937' },
  echeanceRef: { fontSize: 10, color: '#9ca3af' },

  refText: { fontSize: 10, fontWeight: '500', color: '#6b7280', fontFamily: 'monospace' },
  dossTitre: { fontSize: 13, fontWeight: '700', color: '#1f2937' },
  partieText: { fontSize: 11, color: '#6b7280', flex: 1 },

  detailBox: {
    backgroundColor: '#f9fafb', borderRadius: 10,
    padding: 10, marginTop: 8,
    borderWidth: 1, borderColor: '#f3f4f6',
  },
  detailLabel: { fontSize: 10, color: '#9ca3af' },
  detailValue: { fontSize: 12, fontWeight: '600', color: '#1f2937' },

  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  rowGap8: { flexDirection: 'row', gap: 8 },

  // Assistant IA
  qSuggeree: {
    paddingHorizontal: 12, paddingVertical: 7,
    backgroundColor: '#ede9fe', borderRadius: 20,
    borderWidth: 1, borderColor: '#c4b5fd',
  },
  qSuggereeText: { fontSize: 11, color: '#5b21b6', fontWeight: '500' },

  msgRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-end' },
  msgUser: { justifyContent: 'flex-end' },
  msgAI: { justifyContent: 'flex-start' },
  msgAvatar: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: '#ede9fe', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
  },
  msgBubble: { maxWidth: '78%', borderRadius: 16, padding: 12 },
  msgBubbleUser: { backgroundColor: '#7c3aed', borderBottomRightRadius: 4 },
  msgBubbleAI: {
    backgroundColor: '#fff', borderWidth: 1, borderColor: '#e5e7eb',
    borderBottomLeftRadius: 4,
  },
  msgText: { fontSize: 13, lineHeight: 19 },

  inputRow: {
    flexDirection: 'row', gap: 8, padding: 12,
    backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#e5e7eb',
  },
  chatInput: {
    flex: 1, backgroundColor: '#f3f4f6', borderRadius: 20,
    paddingHorizontal: 14, paddingVertical: 10,
    fontSize: 13, color: '#1f2937', maxHeight: 80,
  },
  sendBtn: {
    width: 42, height: 42, borderRadius: 21,
    backgroundColor: '#7c3aed', alignItems: 'center', justifyContent: 'center',
  },

  // Correspondances
  templateCard: {
    flex: 1, minWidth: '45%', padding: 12, borderRadius: 12,
    borderWidth: 1.5, borderColor: '#e5e7eb', backgroundColor: '#fff',
    alignItems: 'center', gap: 4,
  },
  templateCardSelected: { borderColor: '#7c3aed', backgroundColor: '#faf5ff' },
  templateLabel: { fontSize: 11, fontWeight: '500', color: '#374151', textAlign: 'center' },

  fieldLabel: { fontSize: 12, fontWeight: '600', color: '#374151' },

  pickerWrapper: { gap: 6 },
  pickerOption: {
    paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: 8, borderWidth: 1, borderColor: '#e5e7eb',
    backgroundColor: '#f9fafb',
  },
  pickerOptionSelected: { borderColor: '#7c3aed', backgroundColor: '#faf5ff' },
  pickerOptionText: { fontSize: 12, color: '#4b5563' },

  textareaSmall: {
    borderWidth: 1, borderColor: '#d1d5db', borderRadius: 10,
    padding: 10, fontSize: 13, color: '#1f2937', minHeight: 70, textAlignVertical: 'top',
  },
  textarea: {
    borderWidth: 1, borderColor: '#d1d5db', borderRadius: 10,
    padding: 10, fontSize: 12, color: '#1f2937', minHeight: 180,
    fontFamily: 'monospace', textAlignVertical: 'top',
  },

  btnPrimary: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: '#7c3aed', borderRadius: 10, paddingVertical: 12,
  },
  btnPrimaryText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  btnSecondary: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    borderWidth: 1, borderColor: '#d1d5db', borderRadius: 10,
    paddingVertical: 12, backgroundColor: '#fff',
  },
  btnSecondaryText: { color: '#374151', fontWeight: '600', fontSize: 13 },
})
