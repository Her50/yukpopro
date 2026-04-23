import { useEffect, useState } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  StyleSheet, ActivityIndicator, Alert, Modal, RefreshControl,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { abonnementAPI } from '../../src/api/client'

interface Plan {
  id: string
  nom: string
  prix_fcfa: number
  credits_mois: number
  duree_jours: number
  modules: string[]
  description: string
  label_credits: string
  badge?: string
}

interface PackCredit {
  id: string
  nom: string
  credits: number
  prix_fcfa: number
  description: string
  badge?: string
}

interface MonAbonnement {
  plan: string
  nom_plan: string
  statut: string
  credits_alloues: number
  credits_utilises: number
  credits_restants: number
  pct_utilise: number
  label_credits: string
  modules_autorises: string[]
  date_fin: string | null
  prix_fcfa: number
  renouvellement_le?: string | null
}

interface Instructions {
  montant_fcfa: number
  important: string
  etapes: Record<string, string>
}

const OPERATEURS = [
  { id: 'orange_money', label: 'Orange Money' },
  { id: 'mtn_momo', label: 'MTN MoMo' },
  { id: 'wave', label: 'Wave' },
  { id: 'moov_money', label: 'Moov Money' },
  { id: 'airtel_money', label: 'Airtel Money' },
  { id: 'expressunion', label: 'Express Union' },
]

const MODULE_LABELS: Record<string, string> = {
  redaction: 'Rédaction IA',
  ocr: 'Scan / OCR',
  audio: 'Audio → Doc',
  traduction: 'Traduction',
  infographie: 'Infographie',
  gestion: 'Gestion',
  documents: 'Mes Documents',
}

function fmtFcfa(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

type Onglet = 'plans' | 'recharge' | 'historique'
type TypeEnAttente = 'plan' | 'recharge' | null

export default function AbonnementScreen() {
  const [onglet, setOnglet] = useState<Onglet>('plans')
  const [monAbo, setMonAbo] = useState<MonAbonnement | null>(null)
  const [plans, setPlans] = useState<Plan[]>([])
  const [packs, setPacks] = useState<PackCredit[]>([])
  const [historique, setHistorique] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const [planChoisi, setPlanChoisi] = useState<string | null>(null)
  const [packChoisi, setPackChoisi] = useState<string | null>(null)
  const [operateur, setOperateur] = useState('orange_money')
  const [numero, setNumero] = useState('')
  const [reference, setReference] = useState<string | null>(null)
  const [instructions, setInstructions] = useState<Instructions | null>(null)
  const [typeEnAttente, setTypeEnAttente] = useState<TypeEnAttente>(null)
  const [operateurPickerOpen, setOperateurPickerOpen] = useState(false)
  const [initiating, setInitiating] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const chargerTout = async () => {
    try {
      const [abo, p, pk] = await Promise.all([
        abonnementAPI.monAbonnement(),
        abonnementAPI.plans(),
        abonnementAPI.packsCredits(),
      ])
      setMonAbo(abo.data)
      setPlans(p.data.plans || [])
      setPacks(pk.data.packs || [])
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const chargerHistorique = async () => {
    try {
      const r = await abonnementAPI.historique()
      setHistorique(r.data)
    } catch { /* ignore */ }
  }

  useEffect(() => { chargerTout() }, [])

  useEffect(() => {
    if (onglet === 'historique') chargerHistorique()
  }, [onglet])

  const onRefresh = () => {
    setRefreshing(true)
    chargerTout()
    if (onglet === 'historique') chargerHistorique()
  }

  const initier = async () => {
    if (!numero || numero.length < 8) {
      Alert.alert('Numéro invalide', 'Entrez un numéro de téléphone valide.')
      return
    }
    setInitiating(true)
    try {
      const r = planChoisi
        ? await abonnementAPI.initier({ plan: planChoisi, operateur, numero_telephone: numero })
        : await abonnementAPI.initierRecharge({ pack_id: packChoisi!, operateur, numero_telephone: numero })
      setReference(r.data.reference)
      setInstructions(r.data.instructions)
      setTypeEnAttente(planChoisi ? 'plan' : 'recharge')
    } catch (e: any) {
      Alert.alert('Erreur', e.response?.data?.detail || "Impossible d'initier le paiement")
    } finally {
      setInitiating(false)
    }
  }

  const confirmer = async () => {
    if (!reference) return
    setConfirming(true)
    try {
      if (typeEnAttente === 'plan') {
        await abonnementAPI.confirmer({ reference_paiement: reference })
        Alert.alert('Succès', 'Abonnement activé !')
      } else {
        await abonnementAPI.confirmerRecharge({ reference_paiement: reference })
        Alert.alert('Succès', 'Crédits ajoutés !')
      }
      setReference(null); setInstructions(null); setTypeEnAttente(null)
      setPlanChoisi(null); setPackChoisi(null); setNumero('')
      chargerTout()
      chargerHistorique()
    } catch (e: any) {
      Alert.alert('Erreur', e.response?.data?.detail || 'Erreur de confirmation')
    } finally {
      setConfirming(false)
    }
  }

  const fermerModals = () => {
    setReference(null); setInstructions(null); setTypeEnAttente(null)
    setPlanChoisi(null); setPackChoisi(null); setNumero('')
  }

  if (loading) {
    return (
      <View style={[s.container, { justifyContent: 'center', alignItems: 'center' }]}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    )
  }

  const planEnCours = planChoisi ? plans.find(p => p.id === planChoisi) : null
  const packEnCours = packChoisi ? packs.find(p => p.id === packChoisi) : null

  return (
    <>
      <ScrollView
        style={s.container}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#2563eb" />}
      >
        <View style={s.header}>
          <Ionicons name="card" size={28} color="#fff" />
          <View style={{ marginLeft: 12, flex: 1 }}>
            <Text style={s.title}>Abonnement & Crédits</Text>
            <Text style={s.subtitle}>Gérez votre plan et vos crédits Yukpo</Text>
          </View>
        </View>

        {monAbo && (
          <View style={s.aboCard}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <View style={{ flex: 1 }}>
                <Text style={s.aboLabel}>Plan actif</Text>
                <Text style={s.aboPlan}>{monAbo.nom_plan}</Text>
                <Text style={s.aboSubtle}>{monAbo.label_credits}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={s.aboLabel}>Crédits restants</Text>
                <Text style={s.aboCredits}>
                  {Math.round(monAbo.credits_restants).toLocaleString('fr-FR')}
                </Text>
                <Text style={s.aboSubtle}>sur {monAbo.credits_alloues.toLocaleString('fr-FR')}</Text>
              </View>
            </View>
            <View style={s.progressBar}>
              <View style={[s.progressFill, { width: `${Math.min(100, monAbo.pct_utilise)}%` }]} />
            </View>
            <View style={s.modulesRow}>
              {monAbo.modules_autorises?.map(m => (
                <View key={m} style={s.moduleBadge}>
                  <Text style={s.moduleBadgeText}>{MODULE_LABELS[m] || m}</Text>
                </View>
              ))}
            </View>
            {monAbo.renouvellement_le && (
              <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 10 }}>
                <Ionicons name="time-outline" size={12} color="#bfdbfe" />
                <Text style={[s.aboSubtle, { marginLeft: 4 }]}>
                  Renouvellement : {monAbo.renouvellement_le}
                </Text>
              </View>
            )}
          </View>
        )}

        <View style={s.tabs}>
          {([['plans', 'Plans'], ['recharge', 'Recharger'], ['historique', 'Historique']] as const).map(([k, label]) => (
            <TouchableOpacity
              key={k}
              onPress={() => setOnglet(k)}
              style={[s.tab, onglet === k && s.tabActive]}
            >
              <Text style={[s.tabText, onglet === k && s.tabTextActive]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {onglet === 'plans' && (
          <View style={s.cardsList}>
            {plans.map(p => {
              const actuel = monAbo?.plan === p.id
              return (
                <View key={p.id} style={s.card}>
                  {p.badge && (
                    <View style={s.cardBadge}>
                      <Text style={s.cardBadgeText}>{p.badge}</Text>
                    </View>
                  )}
                  <Text style={s.cardTitle}>{p.nom}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'baseline', marginTop: 4 }}>
                    <Text style={s.cardPrice}>
                      {p.prix_fcfa === 0 ? 'Gratuit' : fmtFcfa(p.prix_fcfa)}
                    </Text>
                    {p.prix_fcfa > 0 && <Text style={s.cardPriceMois}> / mois</Text>}
                  </View>
                  <Text style={s.cardDesc}>{p.description}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 8 }}>
                    <Ionicons name="flash" size={14} color="#2563eb" />
                    <Text style={s.cardCredits}>{p.label_credits}</Text>
                  </View>
                  <View style={s.modulesRow}>
                    {p.modules.map(m => (
                      <View key={m} style={s.modulePill}>
                        <Text style={s.modulePillText}>{MODULE_LABELS[m] || m}</Text>
                      </View>
                    ))}
                  </View>
                  {p.id !== 'gratuit' && (
                    <TouchableOpacity
                      disabled={actuel}
                      onPress={() => setPlanChoisi(p.id)}
                      style={[s.cardBtn, actuel && s.cardBtnDisabled]}
                    >
                      <Text style={s.cardBtnText}>
                        {actuel ? 'Plan actuel' : 'Choisir ce plan'}
                      </Text>
                    </TouchableOpacity>
                  )}
                </View>
              )
            })}
          </View>
        )}

        {onglet === 'recharge' && (
          <View style={s.cardsList}>
            {packs.map(p => (
              <View key={p.id} style={s.card}>
                {p.badge && (
                  <View style={[s.cardBadge, { backgroundColor: '#fef3c7' }]}>
                    <Text style={[s.cardBadgeText, { color: '#b45309' }]}>{p.badge}</Text>
                  </View>
                )}
                <Ionicons name="cube" size={24} color="#2563eb" style={{ marginBottom: 4 }} />
                <Text style={s.cardTitle}>{p.nom}</Text>
                <Text style={s.cardCredits}>
                  {p.credits.toLocaleString('fr-FR')} <Text style={s.cardCreditsLabel}>crédits</Text>
                </Text>
                <Text style={s.cardPriceSmall}>{fmtFcfa(p.prix_fcfa)}</Text>
                <TouchableOpacity onPress={() => setPackChoisi(p.id)} style={s.cardBtn}>
                  <Ionicons name="add-circle-outline" size={14} color="#fff" />
                  <Text style={[s.cardBtnText, { marginLeft: 4 }]}>Acheter</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {onglet === 'historique' && (
          <View style={{ padding: 16, gap: 16 }}>
            <View>
              <Text style={s.histTitle}>Abonnements</Text>
              <View style={s.histList}>
                {(!historique?.historique_abonnements || historique.historique_abonnements.length === 0) && (
                  <Text style={s.histEmpty}>Aucun abonnement passé.</Text>
                )}
                {historique?.historique_abonnements?.map((h: any) => (
                  <View key={h.reference} style={s.histItem}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.histPrimary}>{h.plan}</Text>
                      <Text style={s.histSecondary}>{h.operateur} · {h.reference}</Text>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={s.histPrimary}>{fmtFcfa(h.montant_fcfa)}</Text>
                      <Text style={s.histSecondary}>
                        {new Date(h.date).toLocaleDateString('fr-FR')}
                      </Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>
            <View>
              <Text style={s.histTitle}>Recharges de crédits</Text>
              <View style={s.histList}>
                {(!historique?.historique_recharges || historique.historique_recharges.length === 0) && (
                  <Text style={s.histEmpty}>Aucune recharge passée.</Text>
                )}
                {historique?.historique_recharges?.map((h: any) => (
                  <View key={h.reference} style={s.histItem}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.histPrimary}>{h.pack_nom}</Text>
                      <Text style={s.histSecondary}>
                        {h.credits.toLocaleString('fr-FR')} crédits · {h.reference}
                      </Text>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={s.histPrimary}>{fmtFcfa(h.montant)}</Text>
                      <Text style={s.histSecondary}>{h.date}</Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>

      {/* Modal paiement */}
      <Modal
        transparent
        visible={(!!planChoisi || !!packChoisi) && !reference}
        animationType="slide"
        onRequestClose={fermerModals}
      >
        <View style={s.modalOverlay}>
          <View style={s.modalContent}>
            <Text style={s.modalTitle}>
              Paiement : {planEnCours?.nom || packEnCours?.nom}
            </Text>

            <Text style={s.modalLabel}>Opérateur Mobile Money</Text>
            <TouchableOpacity style={s.select} onPress={() => setOperateurPickerOpen(true)}>
              <Text>{OPERATEURS.find(o => o.id === operateur)?.label}</Text>
              <Ionicons name="chevron-down" size={16} color="#6b7280" />
            </TouchableOpacity>

            <Text style={s.modalLabel}>Numéro de téléphone</Text>
            <TextInput
              value={numero}
              onChangeText={t => setNumero(t.replace(/[^0-9+]/g, ''))}
              placeholder="ex: 690000001"
              keyboardType="phone-pad"
              style={s.input}
            />

            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <TouchableOpacity onPress={fermerModals} style={s.btnSecondary}>
                <Text style={s.btnSecondaryText}>Annuler</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={initier}
                disabled={initiating || !numero || numero.length < 8}
                style={[s.btnPrimary, (initiating || !numero || numero.length < 8) && s.btnDisabled]}
              >
                {initiating
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Text style={s.btnPrimaryText}>Initier le paiement</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Opérateur picker */}
      <Modal transparent visible={operateurPickerOpen} animationType="fade" onRequestClose={() => setOperateurPickerOpen(false)}>
        <TouchableOpacity style={s.modalOverlay} activeOpacity={1} onPress={() => setOperateurPickerOpen(false)}>
          <View style={[s.modalContent, { maxHeight: 400 }]}>
            <Text style={s.modalTitle}>Choisir un opérateur</Text>
            {OPERATEURS.map(o => (
              <TouchableOpacity
                key={o.id}
                style={[s.optionRow, operateur === o.id && s.optionRowActive]}
                onPress={() => { setOperateur(o.id); setOperateurPickerOpen(false) }}
              >
                <Text style={[s.optionText, operateur === o.id && s.optionTextActive]}>{o.label}</Text>
                {operateur === o.id && <Ionicons name="checkmark" size={18} color="#2563eb" />}
              </TouchableOpacity>
            ))}
          </View>
        </TouchableOpacity>
      </Modal>

      {/* Modal instructions */}
      <Modal transparent visible={!!reference && !!instructions} animationType="slide" onRequestClose={fermerModals}>
        <View style={s.modalOverlay}>
          <View style={s.modalContent}>
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
              <Ionicons name="checkmark-circle" size={22} color="#16a34a" />
              <Text style={[s.modalTitle, { marginLeft: 8, flex: 1 }]}>
                Paiement initié
              </Text>
            </View>
            <Text style={s.refBadge}>Référence : {reference}</Text>

            {instructions && (
              <>
                <View style={s.amountBox}>
                  <Text style={s.amountLabel}>Montant</Text>
                  <Text style={s.amountValue}>{fmtFcfa(instructions.montant_fcfa)}</Text>
                  <Text style={s.amountImportant}>{instructions.important}</Text>
                </View>

                <ScrollView style={{ maxHeight: 220 }}>
                  {Object.entries(instructions.etapes || {}).map(([k, v]) => (
                    <View key={k} style={s.etapeBox}>
                      <Text style={s.etapeTitle}>{k}</Text>
                      <Text style={s.etapeText}>{String(v)}</Text>
                    </View>
                  ))}
                </ScrollView>
              </>
            )}

            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
              <TouchableOpacity onPress={fermerModals} style={s.btnSecondary}>
                <Text style={s.btnSecondaryText}>Fermer</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={confirmer}
                disabled={confirming}
                style={[s.btnPrimary, { backgroundColor: '#16a34a' }, confirming && s.btnDisabled]}
              >
                {confirming
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Text style={s.btnPrimaryText}>J'ai payé — Confirmer</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  header: {
    backgroundColor: '#2563eb',
    paddingTop: 56,
    paddingBottom: 28,
    paddingHorizontal: 20,
    flexDirection: 'row',
    alignItems: 'center',
  },
  title: { fontSize: 20, fontWeight: '700', color: '#fff' },
  subtitle: { fontSize: 12, color: '#bfdbfe', marginTop: 2 },

  aboCard: {
    backgroundColor: '#1d4ed8',
    marginHorizontal: 16,
    marginTop: -18,
    padding: 16,
    borderRadius: 16,
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 10,
    elevation: 5,
  },
  aboLabel: { fontSize: 10, color: '#bfdbfe', textTransform: 'uppercase', letterSpacing: 0.5 },
  aboPlan: { fontSize: 22, fontWeight: '700', color: '#fff', marginTop: 2 },
  aboCredits: { fontSize: 22, fontWeight: '700', color: '#fff', marginTop: 2 },
  aboSubtle: { fontSize: 11, color: '#bfdbfe', marginTop: 2 },
  progressBar: { marginTop: 12, height: 6, borderRadius: 99, backgroundColor: 'rgba(255,255,255,0.25)', overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#fff', borderRadius: 99 },

  modulesRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  moduleBadge: { backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: 99, paddingHorizontal: 10, paddingVertical: 4 },
  moduleBadgeText: { fontSize: 10, color: '#fff', fontWeight: '600' },

  modulePill: { backgroundColor: '#f3f4f6', borderRadius: 99, paddingHorizontal: 8, paddingVertical: 3 },
  modulePillText: { fontSize: 9, color: '#374151', fontWeight: '600' },

  tabs: { flexDirection: 'row', paddingHorizontal: 16, marginTop: 20, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  tab: { paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: 'transparent' },
  tabActive: { borderBottomColor: '#2563eb' },
  tabText: { fontSize: 13, color: '#6b7280', fontWeight: '600' },
  tabTextActive: { color: '#2563eb' },

  cardsList: { padding: 16, gap: 12 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: '#000',
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1,
  },
  cardBadge: { alignSelf: 'flex-start', backgroundColor: '#dbeafe', borderRadius: 99, paddingHorizontal: 8, paddingVertical: 3, marginBottom: 6 },
  cardBadgeText: { fontSize: 10, color: '#1d4ed8', fontWeight: '700' },
  cardTitle: { fontSize: 16, fontWeight: '700', color: '#111827' },
  cardPrice: { fontSize: 22, fontWeight: '700', color: '#2563eb' },
  cardPriceMois: { fontSize: 12, color: '#6b7280' },
  cardPriceSmall: { fontSize: 14, fontWeight: '600', color: '#111827', marginTop: 2 },
  cardDesc: { fontSize: 12, color: '#6b7280', marginTop: 4 },
  cardCredits: { fontSize: 13, color: '#1d4ed8', fontWeight: '600', marginLeft: 4 },
  cardCreditsLabel: { fontSize: 10, color: '#6b7280', fontWeight: '400' },
  cardBtn: {
    backgroundColor: '#2563eb',
    borderRadius: 10,
    paddingVertical: 10,
    marginTop: 12,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
  },
  cardBtnDisabled: { backgroundColor: '#9ca3af' },
  cardBtnText: { color: '#fff', fontSize: 13, fontWeight: '600' },

  histTitle: { fontSize: 15, fontWeight: '700', color: '#111827', marginBottom: 8 },
  histList: { backgroundColor: '#fff', borderRadius: 12, borderWidth: 1, borderColor: '#e5e7eb', overflow: 'hidden' },
  histEmpty: { padding: 14, fontSize: 12, color: '#9ca3af' },
  histItem: { flexDirection: 'row', padding: 12, borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  histPrimary: { fontSize: 13, fontWeight: '600', color: '#111827' },
  histSecondary: { fontSize: 10, color: '#9ca3af', marginTop: 2 },

  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalContent: { backgroundColor: '#fff', padding: 20, borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  modalTitle: { fontSize: 16, fontWeight: '700', color: '#111827', marginBottom: 12 },
  modalLabel: { fontSize: 12, fontWeight: '600', color: '#374151', marginTop: 8, marginBottom: 4 },
  select: {
    borderWidth: 1, borderColor: '#d1d5db', borderRadius: 10,
    paddingHorizontal: 12, paddingVertical: 10,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  input: {
    borderWidth: 1, borderColor: '#d1d5db', borderRadius: 10,
    paddingHorizontal: 12, paddingVertical: 10, fontSize: 14,
  },

  btnPrimary: { backgroundColor: '#2563eb', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 10, minWidth: 140, alignItems: 'center' },
  btnPrimaryText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  btnSecondary: { backgroundColor: '#f3f4f6', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 10 },
  btnSecondaryText: { color: '#374151', fontSize: 13, fontWeight: '600' },
  btnDisabled: { opacity: 0.5 },

  optionRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14, borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  optionRowActive: { backgroundColor: '#eff6ff' },
  optionText: { fontSize: 14, color: '#374151' },
  optionTextActive: { color: '#2563eb', fontWeight: '600' },

  refBadge: { fontSize: 12, color: '#1d4ed8', backgroundColor: '#dbeafe', padding: 8, borderRadius: 8, marginBottom: 10 },
  amountBox: { backgroundColor: '#fef3c7', borderWidth: 1, borderColor: '#fde68a', borderRadius: 10, padding: 10, marginBottom: 12 },
  amountLabel: { fontSize: 11, color: '#92400e', fontWeight: '600' },
  amountValue: { fontSize: 18, fontWeight: '700', color: '#92400e', marginTop: 2 },
  amountImportant: { fontSize: 12, color: '#78350f', marginTop: 4, fontWeight: '600' },
  etapeBox: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 10, padding: 10, marginBottom: 8 },
  etapeTitle: { fontSize: 12, fontWeight: '700', color: '#2563eb', textTransform: 'capitalize', marginBottom: 4 },
  etapeText: { fontSize: 12, color: '#374151' },
})
