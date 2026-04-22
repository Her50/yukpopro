/**
 * Écran Yukpo Agents — Interface mobile agents IA autonomes.
 * Branding Yukpo : #0054A6 / #00B0F0 / #1e2640
 */
import React, { useState, useRef, useCallback } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, ScrollView,
  StyleSheet, ActivityIndicator, Keyboard, Platform,
  StatusBar, Dimensions, Image, Alert,
} from 'react-native'
import { LinearGradient } from 'expo-linear-gradient'
import { Ionicons } from '@expo/vector-icons'
import { router } from 'expo-router'
import * as ImagePicker from 'expo-image-picker'
import * as DocumentPicker from 'expo-document-picker'

const API = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'
const { width: SCREEN_W } = Dimensions.get('window')

type AgentType =
  | 'auto' | 'sinistres' | 'souscription' | 'vie' | 'conformite'
  | 'commercial' | 'rh' | 'juridique' | 'comptabilite' | 'intelligence'
  | 'reassurance' | 'placement' | 'provisions' | 'etats_cima' | 'schema_si' | 'meta_factory'
  | 'deploiement_si' | 'maladie' | 'sinistres_auto' | 'risques_divers'

const AGENTS: { value: AgentType; label: string; emoji: string }[] = [
  { value: 'auto',          label: 'Auto-détection',   emoji: '🤖' },
  { value: 'sinistres',     label: 'Sinistres',         emoji: '🚗' },
  { value: 'souscription',  label: 'Souscription',      emoji: '📋' },
  { value: 'vie',           label: 'Vie & Prévoyance',  emoji: '🫀' },
  { value: 'conformite',    label: 'Conformité',        emoji: '📊' },
  { value: 'commercial',    label: 'Commercial',        emoji: '💼' },
  { value: 'rh',            label: 'RH',               emoji: '👥' },
  { value: 'juridique',     label: 'Juridique',         emoji: '⚖️' },
  { value: 'comptabilite',  label: 'Comptabilité',      emoji: '💰' },
  { value: 'intelligence',  label: 'Intelligence',      emoji: '🔍' },
  { value: 'reassurance',   label: 'Réassurance',       emoji: '🔄' },
  { value: 'placement',     label: 'Placement',         emoji: '📈' },
  { value: 'provisions',    label: 'Provisions CIMA',   emoji: '🧮' },
  { value: 'etats_cima',    label: 'États CIMA',        emoji: '📑' },
  { value: 'schema_si',     label: 'Schéma SI',          emoji: '🔬' },
  { value: 'meta_factory',  label: 'MetaFactory',        emoji: '🏭' },
  { value: 'deploiement_si',label: 'Déploiement SI',     emoji: '🔌' },
  { value: 'maladie',        label: 'Maladie & Santé',    emoji: '🏥' },
  { value: 'sinistres_auto', label: 'Sinistres RC Auto',  emoji: '🚦' },
  { value: 'risques_divers', label: 'Risques Divers',     emoji: '🏗️' },
]

const EXEMPLES = [
  { emoji: '🚗', label: 'Sinistre auto',    text: 'Instruis le sinistre SIN-2025-042 de A à Z' },
  { emoji: '📋', label: 'Souscription',     text: 'Émet une police RC auto pour M. Dupont, Cameroun' },
  { emoji: '🫀', label: 'Assurance Vie',    text: 'Souscris un contrat épargne mixte pour Mme Mbarga, 35 ans' },
  { emoji: '📊', label: 'Conformité',       text: 'Calcule les ratios prudentiels T1-2025' },
  { emoji: '🧮', label: 'Provisions',       text: 'Calcule toutes les provisions techniques CIMA de l\'exercice' },
  { emoji: '📑', label: 'États CIMA',       text: 'Génère la liasse C1-C12 et contrôle la cohérence inter-états' },
]

interface Etape {
  id: string; type: string; libelle: string; detail: string
  statut: string; duree_ms: number; donnees: Record<string, unknown>
}

interface QuestionEnAttente {
  id: string
  question: string
  contexte_question: string
  choix_possibles: string[]
  type_reponse: 'texte_libre' | 'choix_multiple' | 'oui_non' | 'nombre' | 'date' | 'image' | 'images'
  nombre_images_max: number
  formats_acceptes: string[]
}

interface MediaSelectionne {
  uri: string
  nom: string
  type: string  // MIME
  estImage: boolean
}

export default function AgentScreen() {
  const [instruction, setInstruction]   = useState('')
  const [agentType, setAgentType]       = useState<AgentType>('auto')
  const [enCours, setEnCours]           = useState(false)
  const [etapes, setEtapes]             = useState<Etape[]>([])
  const [resume, setResume]             = useState('')
  const [aValidation, setAValidation]   = useState(false)
  const [showAgents, setShowAgents]     = useState(false)
  const [question, setQuestion]         = useState<QuestionEnAttente | null>(null)
  const [reponseQ, setReponseQ]         = useState('')
  const [mediasQ, setMediasQ]           = useState<MediaSelectionne[]>([])
  const [envoyantReponse, setEnvoyantReponse] = useState(false)
  const [historiqueQ, setHistoriqueQ]   = useState<{ question: string; reponse: string }[]>([])
  const [numeroQuestion, setNumeroQuestion] = useState(0)
  const scrollRef                        = useRef<ScrollView>(null)

  const lancer = useCallback(async () => {
    if (!instruction.trim() || enCours) return
    Keyboard.dismiss()
    setEnCours(true)
    setEtapes([])
    setResume('')
    setAValidation(false)
    setQuestion(null)
    setReponseQ('')
    setMediasQ([])
    setHistoriqueQ([])
    setNumeroQuestion(0)

    // Récupérer le token JWT depuis SecureStore (même clé que le client mobile)
    let token = ''
    try {
      const { default: SecureStore } = await import('expo-secure-store')
      token = (await SecureStore.getItemAsync('access_token')) ?? ''
    } catch { /* expo-secure-store non disponible */ }

    try {
      const res = await fetch(`${API}/api/v1/agent/instruire`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ instruction, agent_type: agentType, contexte: {} }),
      })
      if (res.ok) {
        const data = await res.json()
        setEtapes(data.etapes ?? [])
        setResume(data.resume ?? '')

        const enAttente = data.statut === 'en_attente_validation'
        setAValidation(enAttente)

        // Détecter si une question a été posée par l'agent
        if (enAttente && data.actions_requises?.length > 0) {
          const premierItem = data.actions_requises[0]
          if (premierItem.question) {
            // Charger les détails de la question depuis l'API
            _chargerQuestion(premierItem.id)
          }
        }
      }
    } catch (err) {
      setEtapes([{ id: '0', type: 'erreur', libelle: 'Erreur réseau', detail: String(err), statut: 'erreur', duree_ms: 0, donnees: {} }])
    } finally {
      setEnCours(false)
      setInstruction('')
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 200)
    }
  }, [instruction, agentType, enCours])

  const _chargerQuestion = async (itemId: string) => {
    try {
      const res = await fetch(`${API}/api/v1/agent/validations/${itemId}`)
      if (res.ok) {
        const data = await res.json()
        if (data.type === 'question_utilisateur') {
          setQuestion({
            id:                data.id,
            question:          data.question ?? data.description,
            contexte_question: data.contexte_question ?? '',
            choix_possibles:   data.choix_possibles ?? [],
            type_reponse:      data.type_reponse ?? 'texte_libre',
            nombre_images_max: data.nombre_images_max ?? 1,
            formats_acceptes:  data.formats_acceptes ?? ['jpg', 'png', 'pdf'],
          })
        }
      }
    } catch { /* ignore */ }
  }

  // ── Picker image depuis caméra ou galerie ──────────────────────────────────
  const ouvrirPickerImage = useCallback(async (source: 'camera' | 'gallery') => {
    if (!question) return
    const nbMax = question.nombre_images_max ?? 1
    if (mediasQ.length >= nbMax) {
      Alert.alert('Limite atteinte', `Maximum ${nbMax} fichier(s) autorisé(s)`)
      return
    }
    let result: ImagePicker.ImagePickerResult
    if (source === 'camera') {
      const perm = await ImagePicker.requestCameraPermissionsAsync()
      if (!perm.granted) { Alert.alert('Permission refusée', 'Autoriser l\'accès à la caméra dans les paramètres'); return }
      result = await ImagePicker.launchCameraAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.8 })
    } else {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync()
      if (!perm.granted) { Alert.alert('Permission refusée', 'Autoriser l\'accès à la galerie dans les paramètres'); return }
      result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.8,
        allowsMultipleSelection: question.type_reponse === 'images',
        selectionLimit: nbMax - mediasQ.length,
      })
    }
    if (!result.canceled && result.assets) {
      const nouveaux: MediaSelectionne[] = result.assets.map((a) => ({
        uri:      a.uri,
        nom:      a.fileName ?? `photo_${Date.now()}.jpg`,
        type:     a.mimeType ?? 'image/jpeg',
        estImage: true,
      }))
      setMediasQ((prev) => [...prev, ...nouveaux].slice(0, nbMax))
    }
  }, [question, mediasQ.length])

  const ouvrirPickerDocument = useCallback(async () => {
    if (!question) return
    const nbMax = question.nombre_images_max ?? 1
    if (mediasQ.length >= nbMax) {
      Alert.alert('Limite atteinte', `Maximum ${nbMax} fichier(s) autorisé(s)`)
      return
    }
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      multiple: question.type_reponse === 'images',
    })
    if (!result.canceled && result.assets) {
      const nouveaux: MediaSelectionne[] = result.assets.map((a) => ({
        uri:      a.uri,
        nom:      a.name,
        type:     a.mimeType ?? 'application/pdf',
        estImage: (a.mimeType ?? '').startsWith('image/'),
      }))
      setMediasQ((prev) => [...prev, ...nouveaux].slice(0, nbMax))
    }
  }, [question, mediasQ.length])

  const supprimerMediaQ = (idx: number) => setMediasQ((prev) => prev.filter((_, i) => i !== idx))

  const envoyerReponse = useCallback(async () => {
    const estMedia = question?.type_reponse === 'image' || question?.type_reponse === 'images'
    if (!question || envoyantReponse) return
    if (estMedia && mediasQ.length === 0) return
    if (!estMedia && !reponseQ.trim()) return
    Keyboard.dismiss()
    setEnvoyantReponse(true)
    try {
      let res: Response

      if (estMedia && mediasQ.length > 0) {
        // Multipart avec fichiers
        const form = new FormData()
        form.append('reponse', reponseQ.trim() || `${mediasQ.length} fichier(s) fourni(s)`)
        for (const m of mediasQ) {
          form.append('medias', { uri: m.uri, name: m.nom, type: m.type } as any)
        }
        res = await fetch(`${API}/api/v1/agent/repondre/${question.id}/medias`, {
          method: 'POST',
          headers: { 'Content-Type': 'multipart/form-data' },
          body: form,
        })
      } else {
        res = await fetch(`${API}/api/v1/agent/repondre/${question.id}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reponse: reponseQ.trim() }),
        })
      }
      if (res.ok) {
        const data = await res.json()
        // Archiver la question/réponse dans l'historique
        if (question) {
          const estMedia = question.type_reponse === 'image' || question.type_reponse === 'images'
          const reponseAffichee = estMedia
            ? `${mediasQ.length} fichier(s) envoyé(s)`
            : reponseQ.trim()
          setHistoriqueQ((prev) => [...prev, { question: question.question, reponse: reponseAffichee }])
          setNumeroQuestion((prev) => prev + 1)
        }
        setQuestion(null)
        setReponseQ('')
        setMediasQ([])
        setAValidation(false)
        if (data.reprise) {
          // Ajouter les nouvelles étapes à la timeline
          const nouvEtapes: Etape[] = data.reprise.etapes ?? []
          setEtapes((prev) => [...prev, ...nouvEtapes])
          setResume(data.reprise.resume ?? '')
          setAValidation(data.reprise.statut === 'en_attente_validation')
          // Vérifier si une nouvelle question a été posée
          if (data.reprise.nouvelle_question && data.reprise.etapes?.length > 0) {
            const derniereEtape = data.reprise.etapes[data.reprise.etapes.length - 1]
            if (derniereEtape?.donnees?.question_id) {
              _chargerQuestion(String(derniereEtape.donnees.question_id))
            }
          }
        }
        setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 300)
      }
    } catch (err) {
      console.error('[Agent Mobile] Erreur réponse:', err)
    } finally {
      setEnvoyantReponse(false)
    }
  }, [question, reponseQ, mediasQ, envoyantReponse])

  const agentSel    = AGENTS.find((a) => a.value === agentType) ?? AGENTS[0]
  const estSysteme  = agentType === 'schema_si' || agentType === 'meta_factory'

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0054A6" />

      {/* ── Header Yukpo branded ── */}
      <LinearGradient
        colors={['#0054A6', '#003476', '#1e2640']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.header}
      >
        {/* Halo décoratif */}
        <View style={styles.headerHalo} />

        <View style={styles.headerRow}>
          {/* Logo Y */}
          <LinearGradient
            colors={['#00B0F0', '#0054A6']}
            style={styles.logoBox}
          >
            <Text style={styles.logoLetter}>Y</Text>
          </LinearGradient>

          <View style={styles.headerText}>
            <View style={styles.headerTitleRow}>
              <Text style={styles.headerBrand}>Yukpo</Text>
              <View style={styles.badgeIA}>
                <Text style={styles.badgeIAText}>Agents IA</Text>
              </View>
            </View>
            <Text style={styles.headerSub}>L'intelligence CIMA au service de votre compagnie</Text>
          </View>

          {aValidation && (
            <View style={styles.validBadge}>
              <Ionicons name="shield-checkmark" size={12} color="#fbbf24" />
              <Text style={styles.validBadgeText}>1 validation</Text>
            </View>
          )}
        </View>

        {/* Chips stats */}
        <View style={styles.statsRow}>
          {[
            { icon: '⚡', text: '15 agents' },
            { icon: '🛡️', text: 'Conformité CIMA' },
            { icon: '🌍', text: '15 pays' },
          ].map((s) => (
            <View key={s.text} style={styles.statChip}>
              <Text style={styles.statChipText}>{s.icon} {s.text}</Text>
            </View>
          ))}
        </View>
      </LinearGradient>

      {/* ── Zone contenu ── */}
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* État vide → exemples */}
        {etapes.length === 0 && !enCours && (
          <View style={styles.emptyState}>
            <LinearGradient
              colors={['#0054A6', '#00B0F0']}
              style={styles.emptyIcon}
            >
              <Text style={{ fontSize: 32 }}>✨</Text>
            </LinearGradient>
            <Text style={styles.emptyTitle}>Bonjour, que puis-je faire ?</Text>
            <Text style={styles.emptyDesc}>
              Donnez une instruction en français. Yukpo Agents exécute le processus complet.
            </Text>

            <View style={styles.exemplesGrid}>
              {EXEMPLES.map((ex) => (
                <TouchableOpacity
                  key={ex.text}
                  style={styles.exempleCard}
                  onPress={() => setInstruction(ex.text)}
                  activeOpacity={0.75}
                >
                  <Text style={styles.exempleEmoji}>{ex.emoji}</Text>
                  <Text style={styles.exempleLabel}>{ex.label}</Text>
                  <Text style={styles.exempleText} numberOfLines={2}>{ex.text}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* Loading */}
        {enCours && (
          <LinearGradient
            colors={['#eff6ff', '#dbeafe']}
            style={styles.chargementCard}
          >
            <ActivityIndicator color="#0054A6" size="small" />
            <View>
              <Text style={styles.chargementTitle}>Yukpo agent actif...</Text>
              <Text style={styles.chargementSub}>Agent {agentSel.label} en cours d'exécution</Text>
            </View>
          </LinearGradient>
        )}

        {/* Étapes */}
        {etapes.map((etape, idx) => (
          <EtapeItem key={etape.id || idx} etape={etape} />
        ))}

        {/* Carte question complémentaire de l'agent */}
        {question && !enCours && (
          <View style={[styles.questionCard, estSysteme && styles.questionCardSysteme]}>

            {/* ── Historique Q&A précédents ── */}
            {historiqueQ.length > 0 && (
              <View style={styles.historiqueContainer}>
                {historiqueQ.map((h, i) => (
                  <View key={i} style={styles.historiqueItem}>
                    <View style={styles.historiqueQuestion}>
                      <Ionicons name="help-circle-outline" size={12} color="#94a3b8" style={{ marginTop: 1 }} />
                      <Text style={styles.historiqueQuestionText}>{h.question}</Text>
                    </View>
                    <View style={styles.historiqueReponse}>
                      <Text style={styles.historiqueArrow}>↳</Text>
                      <Text style={styles.historiqueReponseText}>{h.reponse}</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}

            {/* ── En-tête ── */}
            <LinearGradient
              colors={estSysteme ? ['#f5f3ff', '#eef2ff'] : ['#eff6ff', '#e0f2fe']}
              style={styles.questionHeaderBg}
            >
              <View style={styles.questionHeader}>
                <LinearGradient
                  colors={estSysteme ? ['#7c3aed', '#4f46e5'] : ['#0054A6', '#00B0F0']}
                  style={styles.questionIconBox}
                >
                  <Ionicons
                    name={estSysteme ? 'hardware-chip-outline' : 'help-circle-outline'}
                    size={16}
                    color="#fff"
                  />
                </LinearGradient>
                <View style={{ flex: 1 }}>
                  <View style={styles.questionBadgeRow}>
                    {estSysteme ? (
                      <View style={[styles.badgeChip, styles.badgeChipSysteme]}>
                        <Ionicons name="shield-checkmark-outline" size={10} color="#7c3aed" />
                        <Text style={[styles.questionBadge, styles.questionBadgeSysteme]}>Question système Yukpo</Text>
                      </View>
                    ) : (
                      <Text style={styles.questionBadge}>Complément d'information requis</Text>
                    )}
                    <View style={[styles.badgePause, estSysteme && styles.badgePauseSysteme]}>
                      <Text style={[styles.badgePauseText, estSysteme && styles.badgePauseTextSysteme]}>
                        Agent en pause
                      </Text>
                    </View>
                    {numeroQuestion > 0 && (
                      <Text style={styles.numeroBadge}>Q {numeroQuestion + 1}</Text>
                    )}
                  </View>
                  <Text style={styles.questionText}>{question.question}</Text>
                  {!!question.contexte_question && (
                    <View style={[styles.contexteBox, estSysteme && styles.contexteBoxSysteme]}>
                      <Text style={styles.questionContexte}>{question.contexte_question}</Text>
                    </View>
                  )}
                </View>
              </View>
            </LinearGradient>

            {/* ── Zone réponse ── */}
            <View style={styles.reponseZone}>
              {/* Oui / Non */}
              {question.type_reponse === 'oui_non' && (
                <View style={styles.choixRow}>
                  {['Oui', 'Non'].map((opt) => (
                    <TouchableOpacity
                      key={opt}
                      style={[styles.choixBtn, reponseQ === opt && (opt === 'Oui' ? styles.choixBtnOui : styles.choixBtnNon)]}
                      onPress={() => setReponseQ(opt)}
                      activeOpacity={0.8}
                    >
                      <Text style={[styles.choixBtnLabel, reponseQ === opt && styles.choixBtnLabelActive]}>
                        {opt === 'Oui' ? '✓ Oui' : '✗ Non'}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              {/* Choix multiple */}
              {question.type_reponse === 'choix_multiple' && question.choix_possibles.length > 0 && (
                <View style={styles.choixMultiple}>
                  {question.choix_possibles.map((opt) => (
                    <TouchableOpacity
                      key={opt}
                      style={[styles.choixChip, reponseQ === opt && (estSysteme ? styles.choixChipActiveSysteme : styles.choixChipActive)]}
                      onPress={() => setReponseQ(opt)}
                      activeOpacity={0.8}
                    >
                      <Text style={[styles.choixChipLabel, reponseQ === opt && styles.choixChipLabelActive]}>
                        {opt}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              {/* Texte libre / nombre / date */}
              {(question.type_reponse === 'texte_libre' || question.type_reponse === 'nombre' || question.type_reponse === 'date') && (
                <TextInput
                  style={[styles.questionInput, estSysteme && styles.questionInputSysteme]}
                  value={reponseQ}
                  onChangeText={setReponseQ}
                  placeholder={question.type_reponse === 'nombre' ? 'Entrez un nombre...' : 'Votre réponse...'}
                  placeholderTextColor="#94a3b8"
                  keyboardType={question.type_reponse === 'nombre' ? 'numeric' : 'default'}
                  multiline={question.type_reponse === 'texte_libre'}
                  editable={!envoyantReponse}
                  autoFocus
                />
              )}

              {/* IMAGE / IMAGES — picker caméra + galerie + documents */}
              {(question.type_reponse === 'image' || question.type_reponse === 'images') && (
                <View style={styles.mediaZone}>
                  {/* Boutons de sélection */}
                  <View style={styles.mediaBtnsRow}>
                    <TouchableOpacity
                      style={[styles.mediaBtn, estSysteme && styles.mediaBtnSysteme]}
                      onPress={() => ouvrirPickerImage('camera')}
                      disabled={envoyantReponse || mediasQ.length >= question.nombre_images_max}
                      activeOpacity={0.8}
                    >
                      <Ionicons name="camera-outline" size={18} color="#fff" />
                      <Text style={styles.mediaBtnText}>Caméra</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.mediaBtn, estSysteme && styles.mediaBtnSysteme]}
                      onPress={() => ouvrirPickerImage('gallery')}
                      disabled={envoyantReponse || mediasQ.length >= question.nombre_images_max}
                      activeOpacity={0.8}
                    >
                      <Ionicons name="images-outline" size={18} color="#fff" />
                      <Text style={styles.mediaBtnText}>Galerie</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.mediaBtn, { backgroundColor: '#64748b' }]}
                      onPress={ouvrirPickerDocument}
                      disabled={envoyantReponse || mediasQ.length >= question.nombre_images_max}
                      activeOpacity={0.8}
                    >
                      <Ionicons name="document-outline" size={18} color="#fff" />
                      <Text style={styles.mediaBtnText}>Document</Text>
                    </TouchableOpacity>
                  </View>

                  <Text style={styles.mediaHint}>
                    {mediasQ.length}/{question.nombre_images_max} fichier(s) — JPG · PNG · PDF
                  </Text>

                  {/* Prévisualisations */}
                  {mediasQ.length > 0 && (
                    <View style={styles.mediaPreviewRow}>
                      {mediasQ.map((m, idx) => (
                        <View key={idx} style={styles.mediaPreviewItem}>
                          {m.estImage ? (
                            <Image source={{ uri: m.uri }} style={styles.mediaPreviewImg} resizeMode="cover" />
                          ) : (
                            <View style={styles.mediaPreviewDoc}>
                              <Ionicons name="document-text-outline" size={24} color="#dc2626" />
                              <Text style={styles.mediaPreviewDocNom} numberOfLines={2}>{m.nom}</Text>
                            </View>
                          )}
                          <TouchableOpacity
                            style={styles.mediaPreviewDelete}
                            onPress={() => supprimerMediaQ(idx)}
                          >
                            <Ionicons name="close-circle" size={20} color="#ef4444" />
                          </TouchableOpacity>
                        </View>
                      ))}
                    </View>
                  )}

                  {/* Commentaire optionnel */}
                  <TextInput
                    style={[styles.questionInput, { marginTop: 8 }]}
                    value={reponseQ}
                    onChangeText={setReponseQ}
                    placeholder="Commentaire optionnel..."
                    placeholderTextColor="#94a3b8"
                    multiline
                    editable={!envoyantReponse}
                  />
                </View>
              )}

              {/* Bouton envoyer */}
              {((): React.ReactNode => {
                const estMediaQ = question.type_reponse === 'image' || question.type_reponse === 'images'
                const peutEnvoyer = estMediaQ ? mediasQ.length > 0 : reponseQ.trim().length > 0
                return (
                  <>
                    <TouchableOpacity
                      style={[styles.btnRepondre, (!peutEnvoyer || envoyantReponse) && styles.btnRepondreDisabled]}
                      onPress={envoyerReponse}
                      disabled={!peutEnvoyer || envoyantReponse}
                      activeOpacity={0.85}
                    >
                      <LinearGradient
                        colors={
                          peutEnvoyer && !envoyantReponse
                            ? (estSysteme ? ['#7c3aed', '#4f46e5'] : ['#0054A6', '#00B0F0'])
                            : ['#94a3b8', '#94a3b8']
                        }
                        style={styles.btnRepondreGradient}
                      >
                        {envoyantReponse
                          ? <ActivityIndicator color="#fff" size="small" />
                          : <Ionicons name="send" size={16} color="#fff" />}
                        <Text style={styles.btnRepondreText}>
                          {envoyantReponse ? 'Agent reprend...' : "Envoyer — l'agent continue"}
                        </Text>
                      </LinearGradient>
                    </TouchableOpacity>
                    <Text style={[styles.agentReprend, estSysteme && styles.agentReprendSysteme]}>
                      L'agent reprendra automatiquement avec votre réponse
                    </Text>
                  </>
                )
              })()}
            </View>
          </View>
        )}

        {/* Résumé */}
        {resume !== '' && !enCours && !question && (
          <View style={[styles.resumeCard, aValidation && styles.resumeAttente]}>
            <View style={styles.resumeHeader}>
              <Ionicons
                name={aValidation ? 'hourglass-outline' : 'checkmark-circle'}
                size={18}
                color={aValidation ? '#f97316' : '#0054A6'}
              />
              <Text style={[styles.resumeLabel, aValidation && styles.resumeLabelAttente]}>
                {aValidation ? 'En attente de validation humaine' : 'Résultat Yukpo'}
              </Text>
            </View>
            <Text style={styles.resumeText}>{resume}</Text>
            {aValidation && !question && (
              <TouchableOpacity
                style={styles.btnValidations}
                onPress={() => router.push('/(tabs)/validations')}
                activeOpacity={0.85}
              >
                <LinearGradient
                  colors={['#f97316', '#ea580c']}
                  style={styles.btnValidationsGradient}
                >
                  <Ionicons name="shield-checkmark-outline" size={15} color="#fff" />
                  <Text style={styles.btnValidationsText}>Valider maintenant</Text>
                </LinearGradient>
              </TouchableOpacity>
            )}
          </View>
        )}
      </ScrollView>

      {/* ── Zone saisie ── */}
      <View style={styles.inputZone}>
        {/* Sélecteur agent */}
        <TouchableOpacity
          style={styles.agentSelector}
          onPress={() => setShowAgents(!showAgents)}
          activeOpacity={0.8}
        >
          <Text style={styles.agentSelectorEmoji}>{agentSel.emoji}</Text>
          <Text style={styles.agentSelectorLabel}>{agentSel.label}</Text>
          <Ionicons
            name={showAgents ? 'chevron-up' : 'chevron-down'}
            size={14}
            color="#0054A6"
            style={{ marginLeft: 'auto' }}
          />
        </TouchableOpacity>

        {/* Dropdown agents */}
        {showAgents && (
          <View style={styles.agentDropdown}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ paddingVertical: 6 }}>
              {AGENTS.map((a) => (
                <TouchableOpacity
                  key={a.value}
                  style={[styles.agentChip, agentType === a.value && styles.agentChipActive]}
                  onPress={() => { setAgentType(a.value); setShowAgents(false) }}
                  activeOpacity={0.8}
                >
                  <Text style={styles.agentChipEmoji}>{a.emoji}</Text>
                  <Text style={[styles.agentChipLabel, agentType === a.value && styles.agentChipLabelActive]}>
                    {a.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Input + bouton envoi */}
        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={instruction}
            onChangeText={setInstruction}
            placeholder="Donnez une instruction à Yukpo Agents..."
            placeholderTextColor="#94a3b8"
            multiline
            editable={!enCours}
            maxLength={500}
          />
          <TouchableOpacity
            style={[styles.sendBtn, (!instruction.trim() || enCours) && styles.sendBtnDisabled]}
            onPress={lancer}
            disabled={!instruction.trim() || enCours}
            activeOpacity={0.85}
          >
            <LinearGradient
              colors={instruction.trim() && !enCours ? ['#0054A6', '#00B0F0'] : ['#94a3b8', '#94a3b8']}
              style={styles.sendBtnGradient}
            >
              {enCours
                ? <ActivityIndicator color="#fff" size="small" />
                : <Ionicons name="send" size={18} color="#fff" />}
            </LinearGradient>
          </TouchableOpacity>
        </View>

        {/* Branding footer */}
        <View style={styles.poweredBy}>
          <Text style={styles.poweredByText}>
            Propulsé par{' '}
            <Text style={styles.poweredByBrand}>Yukpo Intelligence</Text>
            {' '}· Zone CIMA
          </Text>
        </View>
      </View>
    </View>
  )
}

function EtapeItem({ etape }: { etape: Etape }) {
  const isValidation = etape.type === 'validation'
  const isQuestion   = etape.type === 'question'

  let iconName  = 'ellipse-outline'
  let iconColor = '#94a3b8'

  if (isQuestion) {
    iconName  = 'help-circle-outline'
    iconColor = '#0054A6'
  } else if (isValidation) {
    iconName  = 'shield-checkmark-outline'
    iconColor = '#f97316'
  } else if (etape.statut === 'ok') {
    iconName  = 'checkmark-circle'
    iconColor = '#0054A6'
  } else if (etape.statut === 'erreur') {
    iconName  = 'close-circle'
    iconColor = '#ef4444'
  } else if (etape.statut === 'en_cours') {
    iconName  = 'time-outline'
    iconColor = '#00B0F0'
  } else if (etape.type === 'ia') {
    iconName  = 'sparkles-outline'
    iconColor = '#a855f7'
  }

  return (
    <View style={[
      styles.etapeItem,
      isValidation && styles.etapeValidation,
      isQuestion   && styles.etapeQuestion,
    ]}>
      <Ionicons name={iconName as any} size={18} color={iconColor} />
      <View style={styles.etapeContent}>
        <Text style={styles.etapeLibelle}>{etape.libelle}</Text>
        {etape.detail !== '' && (
          <Text style={styles.etapeDetail} numberOfLines={2}>{etape.detail}</Text>
        )}
        {isQuestion && (
          <Text style={styles.etapeQuestionHint}>↓ Répondez ci-dessous</Text>
        )}
      </View>
      {etape.duree_ms > 0 && (
        <Text style={styles.etapeDuree}>
          {etape.duree_ms < 1000 ? `${etape.duree_ms}ms` : `${(etape.duree_ms / 1000).toFixed(1)}s`}
        </Text>
      )}
    </View>
  )
}

// ─── Styles ──────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },

  // Header
  header: { paddingTop: Platform.OS === 'ios' ? 56 : 40, paddingBottom: 16, paddingHorizontal: 16 },
  headerHalo: {
    position: 'absolute', top: -40, right: -40,
    width: 180, height: 180, borderRadius: 90,
    backgroundColor: '#00B0F0', opacity: 0.08,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  logoBox: {
    width: 48, height: 48, borderRadius: 14,
    alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 6,
  },
  logoLetter: { color: '#fff', fontSize: 22, fontWeight: '900' },
  headerText: { flex: 1 },
  headerTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerBrand: { color: '#fff', fontSize: 20, fontWeight: '900', letterSpacing: -0.5 },
  badgeIA: {
    backgroundColor: 'rgba(0,176,240,0.25)', borderRadius: 10,
    paddingHorizontal: 8, paddingVertical: 2, borderWidth: 1, borderColor: 'rgba(0,176,240,0.4)',
  },
  badgeIAText: { color: '#7dd3fc', fontSize: 10, fontWeight: '700' },
  headerSub: { color: 'rgba(186,230,253,0.85)', fontSize: 11, marginTop: 2 },
  validBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: 'rgba(251,191,36,0.2)', borderRadius: 10,
    paddingHorizontal: 8, paddingVertical: 4, borderWidth: 1, borderColor: 'rgba(251,191,36,0.4)',
  },
  validBadgeText: { color: '#fbbf24', fontSize: 10, fontWeight: '700' },
  statsRow: { flexDirection: 'row', gap: 6 },
  statChip: {
    backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 8,
    paddingHorizontal: 10, paddingVertical: 4,
  },
  statChipText: { color: 'rgba(186,230,253,0.8)', fontSize: 10, fontWeight: '500' },

  // Scroll
  scroll: { flex: 1 },
  scrollContent: { padding: 16, paddingBottom: 24 },

  // Empty state
  emptyState: { alignItems: 'center', paddingTop: 20 },
  emptyIcon: { width: 72, height: 72, borderRadius: 22, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  emptyTitle: { fontSize: 20, fontWeight: '900', color: '#1e293b', marginBottom: 6, letterSpacing: -0.3 },
  emptyDesc: { fontSize: 13, color: '#64748b', textAlign: 'center', maxWidth: 280, lineHeight: 20, marginBottom: 20 },
  exemplesGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, width: '100%' },
  exempleCard: {
    width: (SCREEN_W - 48) / 2,
    backgroundColor: '#fff', borderRadius: 14, padding: 12,
    borderWidth: 1, borderColor: '#e2e8f0',
  },
  exempleEmoji: { fontSize: 22, marginBottom: 4 },
  exempleLabel: { fontSize: 11, fontWeight: '800', color: '#0054A6', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  exempleText: { fontSize: 11, color: '#64748b', lineHeight: 16 },

  // Loading
  chargementCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    borderRadius: 14, padding: 14, marginBottom: 8,
  },
  chargementTitle: { fontSize: 14, fontWeight: '700', color: '#0054A6' },
  chargementSub: { fontSize: 11, color: '#64748b', marginTop: 2 },

  // Etapes
  etapeItem: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 10,
    backgroundColor: '#fff', borderRadius: 12, padding: 12, marginBottom: 6,
    borderWidth: 1, borderColor: '#f1f5f9',
    shadowColor: '#000', shadowOpacity: 0.03, shadowRadius: 4, elevation: 1,
  },
  etapeValidation: { borderColor: '#fed7aa', backgroundColor: '#fff7ed' },
  etapeQuestion:   { borderColor: '#bfdbfe', backgroundColor: '#eff6ff' },
  etapeContent: { flex: 1 },
  etapeLibelle: { fontSize: 13, fontWeight: '700', color: '#1e293b' },
  etapeDetail: { fontSize: 11, color: '#64748b', marginTop: 3, lineHeight: 16 },
  etapeQuestionHint: { fontSize: 10, color: '#0054A6', marginTop: 3, fontWeight: '600' },
  etapeDuree: { fontSize: 10, color: '#94a3b8', flexShrink: 0 },

  // Question complémentaire
  questionCard: {
    backgroundColor: '#fff', borderRadius: 16, marginBottom: 8, overflow: 'hidden',
    borderWidth: 2, borderColor: '#bfdbfe',
    shadowColor: '#0054A6', shadowOpacity: 0.08, shadowRadius: 8, elevation: 3,
  },
  questionCardSysteme: { borderColor: '#ddd6fe' },

  // Historique Q&A
  historiqueContainer: {
    paddingHorizontal: 12, paddingTop: 10, paddingBottom: 8,
    borderBottomWidth: 1, borderBottomColor: '#f1f5f9', gap: 8,
  },
  historiqueItem: { gap: 2 },
  historiqueQuestion: { flexDirection: 'row', alignItems: 'flex-start', gap: 6 },
  historiqueQuestionText: { flex: 1, fontSize: 11, color: '#94a3b8', fontStyle: 'italic', lineHeight: 16 },
  historiqueReponse: { flexDirection: 'row', gap: 6, marginLeft: 18 },
  historiqueArrow: { fontSize: 11, color: '#16a34a', fontWeight: '700' },
  historiqueReponseText: { flex: 1, fontSize: 11, color: '#374151', fontWeight: '600', lineHeight: 16 },

  // En-tête question
  questionHeaderBg: { paddingHorizontal: 14, paddingVertical: 12 },
  questionHeader: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  questionIconBox: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center', flexShrink: 0,
  },
  questionBadgeRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6, marginBottom: 4 },
  badgeChip: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    backgroundColor: '#eff6ff', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2,
  },
  badgeChipSysteme: { backgroundColor: '#f5f3ff' },
  badgePause: {
    backgroundColor: '#dbeafe', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2,
  },
  badgePauseSysteme: { backgroundColor: '#ede9fe' },
  badgePauseText: { fontSize: 10, color: '#1d4ed8', fontWeight: '600' },
  badgePauseTextSysteme: { color: '#7c3aed' },
  numeroBadge: { fontSize: 10, color: '#94a3b8', marginLeft: 'auto' as any },
  questionBadge: { fontSize: 10, fontWeight: '700', color: '#0054A6', textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  questionBadgeSysteme: { color: '#7c3aed' },
  questionText: { fontSize: 14, fontWeight: '700', color: '#1e293b', lineHeight: 20 },
  contexteBox: {
    marginTop: 6, paddingLeft: 8,
    borderLeftWidth: 2, borderLeftColor: '#bfdbfe',
  },
  contexteBoxSysteme: { borderLeftColor: '#c4b5fd' },
  questionContexte: { fontSize: 11, color: '#64748b', lineHeight: 16, fontStyle: 'italic' },

  // Zone réponse
  reponseZone: { paddingHorizontal: 14, paddingBottom: 12, paddingTop: 10 },
  choixRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  choixBtn: {
    flex: 1, paddingVertical: 10, borderRadius: 12,
    alignItems: 'center', borderWidth: 2, borderColor: '#e2e8f0', backgroundColor: '#fff',
  },
  choixBtnOui:  { borderColor: '#16a34a', backgroundColor: '#16a34a' },
  choixBtnNon:  { borderColor: '#dc2626', backgroundColor: '#dc2626' },
  choixBtnLabel: { fontSize: 14, fontWeight: '700', color: '#374151' },
  choixBtnLabelActive: { color: '#fff' },
  choixMultiple: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 },
  choixChip: {
    paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20,
    borderWidth: 1.5, borderColor: '#e2e8f0', backgroundColor: '#fff',
  },
  choixChipActive: { borderColor: '#0054A6', backgroundColor: '#0054A6' },
  choixChipActiveSysteme: { borderColor: '#7c3aed', backgroundColor: '#7c3aed' },
  choixChipLabel: { fontSize: 12, color: '#374151', fontWeight: '500' },
  choixChipLabelActive: { color: '#fff', fontWeight: '700' },
  questionInput: {
    backgroundColor: '#f8fafc', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10,
    fontSize: 14, color: '#1e293b', borderWidth: 1.5, borderColor: '#bfdbfe',
    marginBottom: 10, maxHeight: 80,
  },
  questionInputSysteme: { borderColor: '#c4b5fd' },
  btnRepondre: { borderRadius: 12, overflow: 'hidden', marginTop: 4 },
  btnRepondreDisabled: { opacity: 0.45 },
  btnRepondreGradient: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    paddingVertical: 12, paddingHorizontal: 16,
  },
  btnRepondreText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  agentReprend: { fontSize: 10, textAlign: 'center', color: '#0054A6', opacity: 0.7, marginTop: 6 },
  agentReprendSysteme: { color: '#7c3aed' },

  // Médias (image / images)
  mediaZone: { gap: 10 },
  mediaBtnsRow: { flexDirection: 'row', gap: 8 },
  mediaBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
    paddingVertical: 9, borderRadius: 10, backgroundColor: '#0054A6',
  },
  mediaBtnSysteme: { backgroundColor: '#7c3aed' },
  mediaBtnText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  mediaHint: { fontSize: 10, color: '#94a3b8', textAlign: 'center' },
  mediaPreviewRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  mediaPreviewItem: { position: 'relative', width: 80, height: 80, borderRadius: 10, overflow: 'hidden', borderWidth: 1, borderColor: '#e2e8f0' },
  mediaPreviewImg: { width: '100%', height: '100%' },
  mediaPreviewDoc: {
    width: '100%', height: '100%', backgroundColor: '#fef2f2',
    alignItems: 'center', justifyContent: 'center', padding: 4,
  },
  mediaPreviewDocNom: { fontSize: 8, color: '#dc2626', textAlign: 'center', marginTop: 2 },
  mediaPreviewDelete: { position: 'absolute', top: 2, right: 2 },

  // Résumé
  resumeCard: {
    backgroundColor: '#eff6ff', borderRadius: 14, padding: 16,
    borderWidth: 1.5, borderColor: '#bfdbfe', marginTop: 4,
  },
  resumeAttente: { backgroundColor: '#fff7ed', borderColor: '#fed7aa' },
  resumeHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  resumeLabel: { fontSize: 13, fontWeight: '800', color: '#0054A6' },
  resumeLabelAttente: { color: '#ea580c' },
  resumeText: { fontSize: 13, color: '#374151', lineHeight: 20 },
  btnValidations: { marginTop: 12 },
  btnValidationsGradient: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10,
    alignSelf: 'flex-start',
  },
  btnValidationsText: { color: '#fff', fontSize: 13, fontWeight: '700' },

  // Zone saisie
  inputZone: {
    backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#e2e8f0',
    padding: 12, paddingBottom: Platform.OS === 'ios' ? 30 : 12,
  },
  agentSelector: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#eff6ff', borderRadius: 10,
    paddingHorizontal: 12, paddingVertical: 8,
    borderWidth: 1, borderColor: '#bfdbfe', marginBottom: 8,
  },
  agentSelectorEmoji: { fontSize: 16 },
  agentSelectorLabel: { fontSize: 13, fontWeight: '700', color: '#0054A6' },
  agentDropdown: { marginBottom: 8, paddingLeft: 2 },
  agentChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#f1f5f9', borderRadius: 20,
    paddingHorizontal: 12, paddingVertical: 7, marginRight: 8,
  },
  agentChipActive: { backgroundColor: '#0054A6' },
  agentChipEmoji: { fontSize: 14 },
  agentChipLabel: { fontSize: 12, color: '#374151', fontWeight: '500' },
  agentChipLabelActive: { color: '#fff', fontWeight: '700' },
  inputRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-end' },
  input: {
    flex: 1, backgroundColor: '#f8fafc', borderRadius: 12,
    paddingHorizontal: 14, paddingVertical: 10,
    fontSize: 14, color: '#1e293b', borderWidth: 1, borderColor: '#e2e8f0',
    maxHeight: 100,
  },
  sendBtn: { width: 46, height: 46 },
  sendBtnDisabled: { opacity: 0.45 },
  sendBtnGradient: { width: 46, height: 46, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  poweredBy: { alignItems: 'center', marginTop: 6 },
  poweredByText: { fontSize: 10, color: '#94a3b8' },
  poweredByBrand: { color: '#0054A6', fontWeight: '700' },
})
