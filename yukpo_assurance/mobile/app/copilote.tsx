import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, Alert, ActivityIndicator,
} from 'react-native'
import { useState } from 'react'
import { api } from '../src/api/client'

type Onglet = 'chat' | 'courrier' | 'clause' | 'formation' | 'indemnite'

const TYPES_COURRIER = [
  'mise_en_demeure', 'lettre_resiliation', 'avis_sinistre',
  'proposition_indemnisation', 'relance_cotisation', 'reponse_reclamation',
]

export default function CopiloteScreen() {
  const [onglet, setOnglet] = useState<Onglet>('chat')

  // Chat
  const [question, setQuestion] = useState('')
  const [reponse, setReponse] = useState('')
  const [loadingChat, setLoadingChat] = useState(false)

  // Courrier
  const [typeCourrier, setTypeCourrier] = useState('mise_en_demeure')
  const [nomAssure, setNomAssure] = useState('')
  const [numPolice, setNumPolice] = useState('')
  const [courrier, setCourrier] = useState('')
  const [loadingCourrier, setLoadingCourrier] = useState(false)

  // Clause
  const [clause, setClause] = useState('')
  const [analyseClause, setAnalyseClause] = useState<any>(null)
  const [loadingClause, setLoadingClause] = useState(false)

  // Formation
  const [sujet, setSujet] = useState('')
  const [formation, setFormation] = useState('')
  const [loadingFormation, setLoadingFormation] = useState(false)

  // Indemnité
  const [typeSinistre, setTypeSinistre] = useState('auto')
  const [montant, setMontant] = useState('')
  const [franchise, setFranchise] = useState('')
  const [indemnite, setIndemnite] = useState<any>(null)
  const [loadingIndemnite, setLoadingIndemnite] = useState(false)

  const envoyerChat = async () => {
    if (!question.trim()) return
    setLoadingChat(true)
    try {
      const r = await api.post('/copilote/chat', { question })
      setReponse(r.data.reponse ?? JSON.stringify(r.data))
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail ?? 'Erreur copilote')
    } finally {
      setLoadingChat(false)
    }
  }

  const redigerCourrier = async () => {
    if (!nomAssure.trim()) return Alert.alert('Requis', 'Nom de l\'assuré requis')
    setLoadingCourrier(true)
    try {
      const r = await api.post('/copilote/rediger-courrier', {
        type_courrier: typeCourrier,
        donnees: { nom_assure: nomAssure, numero_police: numPolice },
      })
      setCourrier(r.data.courrier ?? r.data.contenu ?? JSON.stringify(r.data))
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail ?? 'Erreur rédaction')
    } finally {
      setLoadingCourrier(false)
    }
  }

  const analyserClause = async () => {
    if (!clause.trim()) return
    setLoadingClause(true)
    try {
      const r = await api.post('/copilote/analyser-clause', { clause })
      setAnalyseClause(r.data)
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail ?? 'Erreur analyse')
    } finally {
      setLoadingClause(false)
    }
  }

  const genererFormation = async () => {
    if (!sujet.trim()) return
    setLoadingFormation(true)
    try {
      const r = await api.post('/copilote/former', { sujet, niveau: 'operationnel' })
      setFormation(r.data.contenu ?? r.data.formation ?? JSON.stringify(r.data))
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail ?? 'Erreur formation')
    } finally {
      setLoadingFormation(false)
    }
  }

  const calculerIndemnite = async () => {
    setLoadingIndemnite(true)
    try {
      const r = await api.post('/copilote/calculer-indemnite', {
        type_sinistre: typeSinistre,
        montant_dommages: Number(montant) || 0,
        franchise: Number(franchise) || 0,
        taux_responsabilite: 100,
      })
      setIndemnite(r.data)
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail ?? 'Erreur calcul')
    } finally {
      setLoadingIndemnite(false)
    }
  }

  const TABS: { key: Onglet; label: string }[] = [
    { key: 'chat',       label: 'Chat DG' },
    { key: 'courrier',   label: 'Courrier' },
    { key: 'clause',     label: 'Clause' },
    { key: 'formation',  label: 'Formation' },
    { key: 'indemnite',  label: 'Indemnité' },
  ]

  return (
    <ScrollView style={styles.container}>
      {/* Onglets scrollable */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsScroll}>
        <View style={styles.tabs}>
          {TABS.map(({ key, label }) => (
            <TouchableOpacity key={key} style={[styles.tab, onglet === key && styles.tabActive]}
              onPress={() => setOnglet(key)}>
              <Text style={[styles.tabText, onglet === key && styles.tabTextActive]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* ── Chat ── */}
      {onglet === 'chat' && (
        <View style={styles.section}>
          <TextInput style={[styles.input, { height: 90, textAlignVertical: 'top' }]}
            multiline placeholder="Posez une question à votre copilote DG..."
            value={question} onChangeText={setQuestion} />
          <TouchableOpacity style={styles.btn} onPress={envoyerChat} disabled={loadingChat}>
            {loadingChat
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.btnText}>Envoyer</Text>}
          </TouchableOpacity>
          {reponse ? (
            <View style={styles.card}>
              <Text style={styles.cardLabel}>Réponse du copilote</Text>
              <Text style={styles.cardBody}>{reponse}</Text>
            </View>
          ) : null}
        </View>
      )}

      {/* ── Courrier ── */}
      {onglet === 'courrier' && (
        <View style={styles.section}>
          <Text style={styles.label}>Type de courrier</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {TYPES_COURRIER.map((t) => (
                <TouchableOpacity key={t} style={[styles.chip, typeCourrier === t && styles.chipActive]}
                  onPress={() => setTypeCourrier(t)}>
                  <Text style={[styles.chipText, typeCourrier === t && styles.chipTextActive]}>
                    {t.replace(/_/g, ' ')}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
          <TextInput style={styles.input} placeholder="Nom de l'assuré *"
            value={nomAssure} onChangeText={setNomAssure} />
          <TextInput style={styles.input} placeholder="Numéro de police"
            value={numPolice} onChangeText={setNumPolice} />
          <TouchableOpacity style={styles.btn} onPress={redigerCourrier} disabled={loadingCourrier}>
            {loadingCourrier
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.btnText}>Rédiger le courrier</Text>}
          </TouchableOpacity>
          {courrier ? (
            <View style={styles.card}>
              <Text style={styles.cardLabel}>Courrier généré</Text>
              <Text style={styles.cardBodyMono}>{courrier}</Text>
            </View>
          ) : null}
        </View>
      )}

      {/* ── Clause ── */}
      {onglet === 'clause' && (
        <View style={styles.section}>
          <TextInput style={[styles.input, { height: 130, textAlignVertical: 'top' }]}
            multiline placeholder="Collez le texte de la clause à analyser..."
            value={clause} onChangeText={setClause} />
          <TouchableOpacity style={styles.btn} onPress={analyserClause} disabled={loadingClause}>
            {loadingClause
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.btnText}>Analyser la clause</Text>}
          </TouchableOpacity>
          {analyseClause && (
            <View style={styles.card}>
              {analyseClause.conformite !== undefined && (
                <View style={[styles.badge, { backgroundColor: analyseClause.conformite ? '#dcfce7' : '#fee2e2' }]}>
                  <Text style={{ color: analyseClause.conformite ? '#15803d' : '#dc2626', fontWeight: '700', fontSize: 12 }}>
                    {analyseClause.conformite ? '✓ Conforme CIMA' : '✗ Non-conformité'}
                  </Text>
                </View>
              )}
              {analyseClause.analyse && <Text style={styles.cardBody}>{analyseClause.analyse}</Text>}
              {analyseClause.risques?.map((r: string, i: number) => (
                <Text key={i} style={styles.risque}>⚠ {r}</Text>
              ))}
            </View>
          )}
        </View>
      )}

      {/* ── Formation ── */}
      {onglet === 'formation' && (
        <View style={styles.section}>
          <TextInput style={styles.input} placeholder="Ex : Gestion des sinistres auto CIMA"
            value={sujet} onChangeText={setSujet} />
          <TouchableOpacity style={styles.btn} onPress={genererFormation} disabled={loadingFormation}>
            {loadingFormation
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.btnText}>Générer le module</Text>}
          </TouchableOpacity>
          {formation ? (
            <View style={styles.card}>
              <Text style={styles.cardLabel}>Module de formation</Text>
              <Text style={styles.cardBody}>{formation}</Text>
            </View>
          ) : null}
        </View>
      )}

      {/* ── Indemnité ── */}
      {onglet === 'indemnite' && (
        <View style={styles.section}>
          <Text style={styles.label}>Type de sinistre</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {['auto', 'incendie', 'vie', 'rc', 'transport'].map((t) => (
                <TouchableOpacity key={t} style={[styles.chip, typeSinistre === t && styles.chipActive]}
                  onPress={() => setTypeSinistre(t)}>
                  <Text style={[styles.chipText, typeSinistre === t && styles.chipTextActive]}>{t.toUpperCase()}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
          <TextInput style={styles.input} placeholder="Montant dommages (FCFA)"
            value={montant} onChangeText={setMontant} keyboardType="numeric" />
          <TextInput style={styles.input} placeholder="Franchise (FCFA)"
            value={franchise} onChangeText={setFranchise} keyboardType="numeric" />
          <TouchableOpacity style={styles.btn} onPress={calculerIndemnite} disabled={loadingIndemnite}>
            {loadingIndemnite
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.btnText}>Calculer l'indemnité</Text>}
          </TouchableOpacity>
          {indemnite && (
            <View style={styles.card}>
              {indemnite.montant_indemnite !== undefined && (
                <Text style={styles.montantIndemnite}>
                  {Number(indemnite.montant_indemnite).toLocaleString('fr-FR')} FCFA
                </Text>
              )}
              {indemnite.detail && <Text style={styles.cardBody}>{indemnite.detail}</Text>}
            </View>
          )}
        </View>
      )}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container:        { flex: 1, backgroundColor: '#f9fafb' },
  tabsScroll:       { backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  tabs:             { flexDirection: 'row', paddingHorizontal: 8 },
  tab:              { paddingHorizontal: 16, paddingVertical: 13 },
  tabActive:        { borderBottomWidth: 2, borderBottomColor: '#4f46e5' },
  tabText:          { fontSize: 13, color: '#9ca3af', fontWeight: '600' },
  tabTextActive:    { color: '#4f46e5' },
  section:          { padding: 16, gap: 10 },
  label:            { fontSize: 12, color: '#6b7280', fontWeight: '600', marginBottom: 2 },
  input:            { backgroundColor: '#fff', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12, fontSize: 13, color: '#111827', borderWidth: 1, borderColor: '#e5e7eb' },
  btn:              { backgroundColor: '#4f46e5', borderRadius: 10, paddingVertical: 13, alignItems: 'center' },
  btnText:          { color: '#fff', fontWeight: '700', fontSize: 14 },
  chip:             { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: '#f3f4f6' },
  chipActive:       { backgroundColor: '#4f46e5' },
  chipText:         { fontSize: 11, color: '#6b7280', fontWeight: '600' },
  chipTextActive:   { color: '#fff' },
  card:             { backgroundColor: '#fff', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#e5e7eb', gap: 8 },
  cardLabel:        { fontSize: 11, color: '#6b7280', fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  cardBody:         { fontSize: 13, color: '#374151', lineHeight: 20 },
  cardBodyMono:     { fontSize: 12, color: '#374151', lineHeight: 19, fontFamily: 'monospace' },
  badge:            { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, alignSelf: 'flex-start' },
  risque:           { fontSize: 12, color: '#dc2626' },
  montantIndemnite: { fontSize: 28, fontWeight: '800', color: '#4f46e5', textAlign: 'center', paddingVertical: 8 },
})
