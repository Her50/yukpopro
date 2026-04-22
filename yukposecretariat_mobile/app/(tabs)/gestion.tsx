import { useState } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  TextInput, Modal, ActivityIndicator, Alert, Linking,
} from 'react-native'
import { useAuth } from '../../src/context/AuthContext'
import { gestionAPI } from '../../src/api/client'
import { useEffect } from 'react'

type Onglet = 'kanban' | 'caisse' | 'clients'

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

interface BonTravail {
  id: number; client_nom: string; description: string;
  statut: string; montant_fcfa: number; reste_a_payer: number
}

interface Transaction {
  id: number; type: string; montant_fcfa: number; libelle: string; mode_paiement: string
}

interface Client {
  id: number; nom: string; telephone: string; nb_commandes: number; total_paye_fcfa: number
}

const MODES_PAIEMENT = [
  { code: 'especes', label: '💵 Espèces' },
  { code: 'orange_money', label: '🟠 Orange Money' },
  { code: 'mtn_momo', label: '🟡 MTN MoMo' },
  { code: 'virement', label: '🏦 Virement' },
]

export default function GestionScreen() {
  const [onglet, setOnglet] = useState<Onglet>('kanban')
  const { logout } = useAuth()

  // Kanban
  const [travaux, setTravaux] = useState<BonTravail[]>([])
  const [showModalTravail, setShowModalTravail] = useState(false)
  const [formTravail, setFormTravail] = useState({ client_nom: '', description: '', montant_fcfa: '0' })
  const [loadingTravail, setLoadingTravail] = useState(false)

  // Caisse
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [rapport, setRapport] = useState<{ total_entrees?: number; solde?: number } | null>(null)
  const [showModalCaisse, setShowModalCaisse] = useState(false)
  const [formCaisse, setFormCaisse] = useState({ type: 'entree', montant_fcfa: '', libelle: '', mode_paiement: 'especes' })

  // CRM
  const [clients, setClients] = useState<Client[]>([])
  const [showModalClient, setShowModalClient] = useState(false)
  const [formClient, setFormClient] = useState({ nom: '', telephone: '' })
  const [whatsappMsg] = useState('Bonjour, votre document est prêt.')

  useEffect(() => {
    chargerTravaux()
    chargerCaisse()
    chargerClients()
  }, [])

  const chargerTravaux = async () => {
    try {
      const r = await gestionAPI.travaux()
      setTravaux(r.data.travaux ?? [])
    } catch { /* non bloquant */ }
  }

  const chargerCaisse = async () => {
    try {
      const r = await gestionAPI.transactions()
      setTransactions(r.data.transactions ?? [])
      setRapport(r.data.rapport ?? null)
    } catch { /* non bloquant */ }
  }

  const chargerClients = async () => {
    try {
      const r = await gestionAPI.clients()
      setClients(r.data.clients ?? [])
    } catch { /* non bloquant */ }
  }

  const creerTravail = async () => {
    setLoadingTravail(true)
    try {
      await gestionAPI.creerTravail({
        ...formTravail, montant_fcfa: +formTravail.montant_fcfa,
      })
      setShowModalTravail(false)
      setFormTravail({ client_nom: '', description: '', montant_fcfa: '0' })
      chargerTravaux()
    } catch { Alert.alert('Erreur', 'Création échouée') }
    finally { setLoadingTravail(false) }
  }

  const ajouterTransaction = async () => {
    try {
      await gestionAPI.enregistrerTransaction({
        ...formCaisse, montant_fcfa: +formCaisse.montant_fcfa,
      })
      setShowModalCaisse(false)
      setFormCaisse({ type: 'entree', montant_fcfa: '', libelle: '', mode_paiement: 'especes' })
      chargerCaisse()
    } catch { Alert.alert('Erreur') }
  }

  const creerClient = async () => {
    try {
      await gestionAPI.creerClient(formClient)
      setShowModalClient(false)
      setFormClient({ nom: '', telephone: '' })
      chargerClients()
    } catch { Alert.alert('Erreur') }
  }

  const envoyerWhatsapp = async (clientId: number) => {
    try {
      const r = await gestionAPI.whatsappClient(clientId, whatsappMsg)
      Linking.openURL(r.data.whatsapp_url)
    } catch { Alert.alert('Erreur') }
  }

  const avancerStatut = async (id: number, statut: string) => {
    const ordre = ['en_attente', 'en_cours', 'en_revision', 'livre', 'paye']
    const idx = ordre.indexOf(statut)
    if (idx < ordre.length - 1) {
      await gestionAPI.modifierTravail(id, { statut: ordre[idx + 1] })
      chargerTravaux()
    }
  }

  return (
    <View style={s.container}>
      {/* Onglets */}
      <View style={s.tabsBar}>
        {(['kanban', 'caisse', 'clients'] as Onglet[]).map(o => (
          <TouchableOpacity
            key={o}
            style={[s.tab, onglet === o && s.tabActive]}
            onPress={() => setOnglet(o)}
          >
            <Text style={[s.tabText, onglet === o && s.tabTextActive]}>
              {o === 'kanban' ? '📋 Kanban' : o === 'caisse' ? '💰 Caisse' : '👥 Clients'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView style={{ flex: 1 }}>
        {/* KANBAN */}
        {onglet === 'kanban' && (
          <View style={s.section}>
            <TouchableOpacity style={s.addBtn} onPress={() => setShowModalTravail(true)}>
              <Text style={s.addBtnText}>+ Nouveau bon de travail</Text>
            </TouchableOpacity>
            {travaux.map(b => (
              <View key={b.id} style={s.itemCard}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={s.itemTitle}>{b.client_nom}</Text>
                  <Text style={s.statut}>{b.statut.replace('_', ' ')}</Text>
                </View>
                <Text style={s.itemDesc}>{b.description}</Text>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                  <Text style={s.montant}>{formatFCFA(b.montant_fcfa)}</Text>
                  {b.reste_a_payer > 0 && (
                    <Text style={{ color: '#ea580c', fontSize: 12 }}>Reste: {formatFCFA(b.reste_a_payer)}</Text>
                  )}
                </View>
                {b.statut !== 'paye' && (
                  <TouchableOpacity style={s.avancerBtn} onPress={() => avancerStatut(b.id, b.statut)}>
                    <Text style={s.avancerText}>→ Avancer</Text>
                  </TouchableOpacity>
                )}
              </View>
            ))}
          </View>
        )}

        {/* CAISSE */}
        {onglet === 'caisse' && (
          <View style={s.section}>
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }}>
              <View style={[s.kpi, { backgroundColor: '#f0fdf4' }]}>
                <Text style={{ color: '#16a34a', fontWeight: '700', fontSize: 14 }}>
                  {formatFCFA(rapport?.total_entrees ?? 0)}
                </Text>
                <Text style={{ color: '#6b7280', fontSize: 11 }}>Entrées</Text>
              </View>
              <View style={[s.kpi, { backgroundColor: '#eff6ff' }]}>
                <Text style={{ color: '#2563eb', fontWeight: '700', fontSize: 14 }}>
                  {formatFCFA(rapport?.solde ?? 0)}
                </Text>
                <Text style={{ color: '#6b7280', fontSize: 11 }}>Solde</Text>
              </View>
            </View>
            <TouchableOpacity style={s.addBtn} onPress={() => setShowModalCaisse(true)}>
              <Text style={s.addBtnText}>+ Enregistrer</Text>
            </TouchableOpacity>
            {transactions.map(t => (
              <View key={t.id} style={s.itemCard}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={s.itemTitle}>{t.libelle}</Text>
                  <Text style={{ color: t.type === 'entree' ? '#16a34a' : '#dc2626', fontWeight: '700' }}>
                    {t.type === 'entree' ? '+' : '-'}{formatFCFA(t.montant_fcfa)}
                  </Text>
                </View>
                <Text style={s.itemDesc}>{t.mode_paiement.replace('_', ' ')}</Text>
              </View>
            ))}
          </View>
        )}

        {/* CLIENTS */}
        {onglet === 'clients' && (
          <View style={s.section}>
            <TouchableOpacity style={s.addBtn} onPress={() => setShowModalClient(true)}>
              <Text style={s.addBtnText}>+ Nouveau client</Text>
            </TouchableOpacity>
            {clients.map(c => (
              <View key={c.id} style={s.itemCard}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={s.itemTitle}>{c.nom}</Text>
                  <TouchableOpacity
                    style={{ backgroundColor: '#22c55e', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}
                    onPress={() => envoyerWhatsapp(c.id)}
                  >
                    <Text style={{ color: '#fff', fontSize: 12, fontWeight: '600' }}>WhatsApp</Text>
                  </TouchableOpacity>
                </View>
                <Text style={s.itemDesc}>📞 {c.telephone}</Text>
                <Text style={s.itemDesc}>{c.nb_commandes} commandes · {formatFCFA(c.total_paye_fcfa)}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Modals */}
      <Modal visible={showModalTravail} animationType="slide" transparent>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <Text style={s.modalTitle}>Nouveau bon de travail</Text>
            {['client_nom', 'description'].map(k => (
              <TextInput key={k} style={s.modalInput} placeholder={k === 'client_nom' ? 'Nom du client' : 'Description'}
                value={formTravail[k as keyof typeof formTravail]}
                onChangeText={v => setFormTravail(f => ({ ...f, [k]: v }))}
              />
            ))}
            <TextInput style={s.modalInput} placeholder="Montant (FCFA)" keyboardType="numeric"
              value={formTravail.montant_fcfa}
              onChangeText={v => setFormTravail(f => ({ ...f, montant_fcfa: v }))}
            />
            <TouchableOpacity style={s.modalBtn} onPress={creerTravail} disabled={loadingTravail}>
              {loadingTravail ? <ActivityIndicator color="#fff" /> : <Text style={s.modalBtnText}>Créer</Text>}
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowModalTravail(false)} style={{ marginTop: 10, alignItems: 'center' }}>
              <Text style={{ color: '#9ca3af' }}>Annuler</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      <Modal visible={showModalCaisse} animationType="slide" transparent>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <Text style={s.modalTitle}>Enregistrer une transaction</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
              {['entree', 'sortie'].map(t => (
                <TouchableOpacity key={t} style={[s.chip, formCaisse.type === t && { backgroundColor: '#2563eb' }]}
                  onPress={() => setFormCaisse(f => ({ ...f, type: t }))}>
                  <Text style={{ color: formCaisse.type === t ? '#fff' : '#6b7280', fontSize: 13 }}>
                    {t === 'entree' ? '+ Entrée' : '- Sortie'}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput style={s.modalInput} placeholder="Montant (FCFA)" keyboardType="numeric"
              value={formCaisse.montant_fcfa} onChangeText={v => setFormCaisse(f => ({ ...f, montant_fcfa: v }))} />
            <TextInput style={s.modalInput} placeholder="Libellé"
              value={formCaisse.libelle} onChangeText={v => setFormCaisse(f => ({ ...f, libelle: v }))} />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {MODES_PAIEMENT.map(m => (
                  <TouchableOpacity key={m.code} style={[s.chip, formCaisse.mode_paiement === m.code && { backgroundColor: '#2563eb' }]}
                    onPress={() => setFormCaisse(f => ({ ...f, mode_paiement: m.code }))}>
                    <Text style={{ color: formCaisse.mode_paiement === m.code ? '#fff' : '#6b7280', fontSize: 12 }}>{m.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
            <TouchableOpacity style={s.modalBtn} onPress={ajouterTransaction}>
              <Text style={s.modalBtnText}>Enregistrer</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowModalCaisse(false)} style={{ marginTop: 10, alignItems: 'center' }}>
              <Text style={{ color: '#9ca3af' }}>Annuler</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      <Modal visible={showModalClient} animationType="slide" transparent>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <Text style={s.modalTitle}>Nouveau client</Text>
            <TextInput style={s.modalInput} placeholder="Nom complet"
              value={formClient.nom} onChangeText={v => setFormClient(f => ({ ...f, nom: v }))} />
            <TextInput style={s.modalInput} placeholder="Téléphone" keyboardType="phone-pad"
              value={formClient.telephone} onChangeText={v => setFormClient(f => ({ ...f, telephone: v }))} />
            <TouchableOpacity style={s.modalBtn} onPress={creerClient}>
              <Text style={s.modalBtnText}>Créer le client</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowModalClient(false)} style={{ marginTop: 10, alignItems: 'center' }}>
              <Text style={{ color: '#9ca3af' }}>Annuler</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb', paddingTop: 52 },
  tabsBar: { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabActive: { borderBottomWidth: 2, borderBottomColor: '#2563eb' },
  tabText: { fontSize: 12, color: '#9ca3af', fontWeight: '500' },
  tabTextActive: { color: '#2563eb', fontWeight: '700' },
  section: { padding: 16 },
  addBtn: { backgroundColor: '#2563eb', borderRadius: 12, paddingVertical: 12, alignItems: 'center', marginBottom: 16 },
  addBtnText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  itemCard: { backgroundColor: '#fff', borderRadius: 14, padding: 14, marginBottom: 10, shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, elevation: 2 },
  itemTitle: { fontSize: 14, fontWeight: '600', color: '#111827', flex: 1 },
  itemDesc: { fontSize: 12, color: '#9ca3af', marginTop: 4 },
  montant: { fontSize: 13, fontWeight: '700', color: '#2563eb' },
  statut: { fontSize: 11, backgroundColor: '#eff6ff', color: '#2563eb', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, fontWeight: '600' },
  avancerBtn: { marginTop: 10, backgroundColor: '#eff6ff', borderRadius: 8, paddingVertical: 8, alignItems: 'center' },
  avancerText: { color: '#2563eb', fontSize: 13, fontWeight: '600' },
  kpi: { flex: 1, borderRadius: 14, padding: 14, alignItems: 'center' },
  chip: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20, backgroundColor: '#f3f4f6' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalCard: { backgroundColor: '#fff', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24 },
  modalTitle: { fontSize: 17, fontWeight: '700', color: '#111827', marginBottom: 16 },
  modalInput: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, marginBottom: 10, fontSize: 14, color: '#111827' },
  modalBtn: { backgroundColor: '#2563eb', borderRadius: 14, paddingVertical: 14, alignItems: 'center', marginTop: 4 },
  modalBtnText: { color: '#fff', fontSize: 15, fontWeight: '600' },
})
