import { useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, Modal, ActivityIndicator, Dimensions, Alert,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { DemoBanner } from '../../src/components/DemoBanner'

const SCREEN_W = Dimensions.get('window').width

// ─── Types ────────────────────────────────────────────────────────────────────
type Etape = 'lead' | 'contact' | 'proposition' | 'negociation' | 'gagne' | 'perdu'
type Famille = 'vie' | 'non_vie'

interface Prospect {
  id: string
  nom: string
  entreprise?: string
  telephone: string
  email: string
  etape: Etape
  famille: Famille
  produit: string
  valeur_estimee: number
  date_creation: string
  commercial: string
  notes: string
}

// ─── Config ────────────────────────────────────────────────────────────────────
const ETAPES: { key: Etape; label: string; couleur: string }[] = [
  { key: 'lead',        label: 'Lead',         couleur: '#94a3b8' },
  { key: 'contact',     label: 'Contact',      couleur: '#3b82f6' },
  { key: 'proposition', label: 'Proposition',  couleur: '#f59e0b' },
  { key: 'negociation', label: 'Négociation',  couleur: '#8b5cf6' },
  { key: 'gagne',       label: 'Gagné',        couleur: '#10b981' },
  { key: 'perdu',       label: 'Perdu',        couleur: '#ef4444' },
]

const PRODUITS: { label: string; famille: Famille }[] = [
  { label: 'Assurance Auto',        famille: 'non_vie' },
  { label: 'MRH / Incendie',        famille: 'non_vie' },
  { label: 'Responsabilité Civile', famille: 'non_vie' },
  { label: 'Transport marchandises',famille: 'non_vie' },
  { label: 'Vie Entière',           famille: 'vie' },
  { label: 'Décès temporaire',      famille: 'vie' },
  { label: 'Épargne-Retraite',      famille: 'vie' },
  { label: 'Prévoyance ITT/IPP',    famille: 'vie' },
  { label: 'Éducation / Capital',   famille: 'vie' },
  { label: 'Maladie / Santé',       famille: 'vie' },
]

const DEMO_PROSPECTS: Prospect[] = [
  {
    id: 'p1', nom: 'Diallo Moussa', entreprise: 'SARL Diallo & Fils',
    telephone: '+237 6 91 22 33 44', email: 'diallo@sarl.cm',
    etape: 'proposition', famille: 'non_vie', produit: 'Assurance Auto',
    valeur_estimee: 450000, date_creation: '2026-03-15', commercial: 'Kamga Eric', notes: '',
  },
  {
    id: 'p2', nom: 'Ngo Madeleine', entreprise: '',
    telephone: '+237 6 75 44 55 66', email: 'madeleine.ngo@gmail.com',
    etape: 'contact', famille: 'vie', produit: 'Épargne-Retraite',
    valeur_estimee: 1200000, date_creation: '2026-03-20', commercial: 'Talla Sophie', notes: '',
  },
  {
    id: 'p3', nom: 'Biya Constructions', entreprise: 'SA Biya Constructions',
    telephone: '+237 2 22 00 11 22', email: 'dg@biyaconst.cm',
    etape: 'negociation', famille: 'non_vie', produit: 'Responsabilité Civile',
    valeur_estimee: 3800000, date_creation: '2026-02-10', commercial: 'Kamga Eric', notes: '',
  },
  {
    id: 'p4', nom: 'Fofana Ibrahim', entreprise: '',
    telephone: '+237 6 55 77 88 99', email: 'fofana.i@yahoo.fr',
    etape: 'gagne', famille: 'vie', produit: 'Décès temporaire',
    valeur_estimee: 720000, date_creation: '2026-01-28', commercial: 'Talla Sophie', notes: '',
  },
  {
    id: 'p5', nom: 'Transport Ekanga', entreprise: 'SARL Ekanga',
    telephone: '+237 2 33 44 55 66', email: 'ekanga@transport.cm',
    etape: 'lead', famille: 'non_vie', produit: 'Transport marchandises',
    valeur_estimee: 980000, date_creation: '2026-04-01', commercial: 'Kamga Eric', notes: '',
  },
]

const PERFORMANCES = [
  { nom: 'Kamga Eric',   prospects: 28, gagnes: 14, valeur: '18.4M', taux: 50 },
  { nom: 'Talla Sophie', prospects: 22, gagnes: 13, valeur: '14.2M', taux: 59 },
  { nom: 'Mbida Jules',  prospects: 19, gagnes: 8,  valeur: '9.8M',  taux: 42 },
  { nom: 'Owona Claire', prospects: 15, gagnes: 6,  valeur: '7.1M',  taux: 40 },
]

// ─── Helpers ───────────────────────────────────────────────────────────────────
const etapeCfg = (e: Etape) => ETAPES.find(x => x.key === e) ?? ETAPES[0]
const fmt = (n: number) => n >= 1_000_000
  ? (n / 1_000_000).toFixed(1) + ' M'
  : (n / 1_000).toFixed(0) + ' k'

// ─── Sous-composants ───────────────────────────────────────────────────────────
function EtapeBadge({ etape }: { etape: Etape }) {
  const cfg = etapeCfg(etape)
  return (
    <View style={[s.badge, { backgroundColor: cfg.couleur + '20' }]}>
      <Text style={[s.badgeText, { color: cfg.couleur }]}>{cfg.label}</Text>
    </View>
  )
}

function ProspectCard({ p, onPress }: { p: Prospect; onPress: () => void }) {
  const isVie = p.famille === 'vie'
  return (
    <TouchableOpacity style={[s.card, { borderLeftColor: isVie ? '#ec4899' : '#3b82f6' }]} onPress={onPress}>
      <View style={s.cardHeader}>
        <View style={{ flex: 1 }}>
          <Text style={s.cardNom}>{p.nom}</Text>
          {p.entreprise ? <Text style={s.cardEntreprise}>{p.entreprise}</Text> : null}
        </View>
        <EtapeBadge etape={p.etape} />
      </View>
      <View style={s.cardRow}>
        <View style={[s.famBadge, { backgroundColor: isVie ? '#fdf2f8' : '#eff6ff' }]}>
          <Text style={[s.famText, { color: isVie ? '#db2777' : '#1d4ed8' }]}>
            {isVie ? 'Vie' : 'Non-Vie'}
          </Text>
        </View>
        <Text style={s.produitText}>{p.produit}</Text>
      </View>
      <View style={s.cardFooter}>
        <Text style={s.valeurText}>{fmt(p.valeur_estimee)} XAF</Text>
        <Text style={s.commercialText}>{p.commercial}</Text>
      </View>
    </TouchableOpacity>
  )
}

// ─── Modal détail prospect ─────────────────────────────────────────────────────
function ModalDetail({
  prospect, visible, onClose, onUpdate,
}: {
  prospect: Prospect | null
  visible: boolean
  onClose: () => void
  onUpdate: (p: Prospect) => void
}) {
  const [genIA, setGenIA] = useState(false)
  const [proposition, setProposition] = useState('')

  if (!prospect) return null

  const avancer = () => {
    const ordre: Etape[] = ['lead', 'contact', 'proposition', 'negociation', 'gagne']
    const idx = ordre.indexOf(prospect.etape)
    if (idx < ordre.length - 1) {
      onUpdate({ ...prospect, etape: ordre[idx + 1] })
    }
  }

  const genererProposition = async () => {
    setGenIA(true)
    setProposition('')
    try {
      const res = await fetch('http://localhost:8000/api/v1/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: `Génère une proposition commerciale pour ${prospect.nom}${prospect.entreprise ? ' (' + prospect.entreprise + ')' : ''}, produit : ${prospect.produit}, valeur estimée : ${prospect.valeur_estimee.toLocaleString()} XAF. Compagnie zone CIMA.`,
          context: 'commercial',
        }),
      })
      const data = await res.json()
      setProposition(data.response ?? '')
    } catch {
      setProposition(
        `Madame/Monsieur ${prospect.nom},\n\nNous avons le plaisir de vous soumettre notre proposition pour votre couverture ${prospect.produit}.\n\nSur la base de votre profil, nous vous proposons une prime annuelle estimée à ${fmt(prospect.valeur_estimee)} XAF, incluant les garanties optimales conformément aux exigences CIMA.\n\nNous restons disponibles pour tout renseignement complémentaire.\n\nCordialement,\nL'équipe Commerciale`
      )
    } finally {
      setGenIA(false)
    }
  }

  const cfg = etapeCfg(prospect.etape)

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <ScrollView style={{ flex: 1, backgroundColor: '#f8fafc' }}>
        {/* Header */}
        <View style={s.modalHeader}>
          <View style={{ flex: 1 }}>
            <Text style={s.modalNom}>{prospect.nom}</Text>
            {prospect.entreprise ? <Text style={s.modalEntreprise}>{prospect.entreprise}</Text> : null}
          </View>
          <TouchableOpacity onPress={onClose} style={s.closeBtn}>
            <Ionicons name="close" size={22} color="#64748b" />
          </TouchableOpacity>
        </View>

        <View style={{ padding: 16, gap: 12 }}>
          {/* Etape + avancer */}
          <View style={s.detailCard}>
            <Text style={s.sectionTitle}>Étape pipeline</Text>
            <View style={[s.etapeRow]}>
              {ETAPES.filter(e => !['gagne','perdu'].includes(e.key)).map(e => (
                <View key={e.key} style={[s.etapeStep, {
                  backgroundColor: e.key === prospect.etape ? cfg.couleur : '#e2e8f0',
                }]}>
                  <Text style={{ fontSize: 9, color: e.key === prospect.etape ? '#fff' : '#94a3b8', fontWeight: '600' }}>
                    {e.label}
                  </Text>
                </View>
              ))}
            </View>
            {!['gagne','perdu'].includes(prospect.etape) && (
              <TouchableOpacity style={s.avancerBtn} onPress={avancer}>
                <Ionicons name="arrow-forward-circle-outline" size={16} color="#fff" />
                <Text style={s.avancerText}>Avancer dans le pipeline</Text>
              </TouchableOpacity>
            )}
            {prospect.etape === 'gagne' && (
              <View style={[s.avancerBtn, { backgroundColor: '#10b981' }]}>
                <Ionicons name="checkmark-circle-outline" size={16} color="#fff" />
                <Text style={s.avancerText}>Dossier gagné — transmettre à Souscription</Text>
              </View>
            )}
          </View>

          {/* Infos contact */}
          <View style={s.detailCard}>
            <Text style={s.sectionTitle}>Contact</Text>
            <View style={s.infoRow}>
              <Ionicons name="call-outline" size={14} color="#64748b" />
              <Text style={s.infoText}>{prospect.telephone}</Text>
            </View>
            <View style={s.infoRow}>
              <Ionicons name="mail-outline" size={14} color="#64748b" />
              <Text style={s.infoText}>{prospect.email}</Text>
            </View>
            <View style={s.infoRow}>
              <Ionicons name="person-outline" size={14} color="#64748b" />
              <Text style={s.infoText}>Commercial : {prospect.commercial}</Text>
            </View>
            <View style={s.infoRow}>
              <Ionicons name="calendar-outline" size={14} color="#64748b" />
              <Text style={s.infoText}>Créé le {prospect.date_creation}</Text>
            </View>
          </View>

          {/* Produit & valeur */}
          <View style={s.detailCard}>
            <Text style={s.sectionTitle}>Opportunité</Text>
            <View style={s.infoRow}>
              <Ionicons name="shield-outline" size={14} color="#64748b" />
              <Text style={s.infoText}>{prospect.produit}</Text>
            </View>
            <View style={s.infoRow}>
              <Ionicons name="cash-outline" size={14} color="#64748b" />
              <Text style={[s.infoText, { fontWeight: '700', color: '#1e293b' }]}>
                {prospect.valeur_estimee.toLocaleString()} XAF
              </Text>
            </View>
            <View style={s.infoRow}>
              <Ionicons name={prospect.famille === 'vie' ? 'heart-outline' : 'car-outline'} size={14} color="#64748b" />
              <Text style={s.infoText}>Branche {prospect.famille === 'vie' ? 'Vie' : 'Non-Vie'}</Text>
            </View>
          </View>

          {/* Génération proposition IA */}
          <View style={s.detailCard}>
            <Text style={s.sectionTitle}>Proposition commerciale (IA)</Text>
            <TouchableOpacity style={s.iaBtn} onPress={genererProposition} disabled={genIA}>
              {genIA
                ? <ActivityIndicator size="small" color="#fff" />
                : <Ionicons name="sparkles-outline" size={16} color="#fff" />
              }
              <Text style={s.iaBtnText}>{genIA ? 'Génération…' : 'Générer avec YukpoPro'}</Text>
            </TouchableOpacity>
            {proposition ? (
              <View style={s.propositionBox}>
                <Text style={s.propositionText}>{proposition}</Text>
              </View>
            ) : null}
          </View>
        </View>
      </ScrollView>
    </Modal>
  )
}

// ─── Onglet Performances ───────────────────────────────────────────────────────
function OngletPerformances() {
  const total = PERFORMANCES.reduce((acc, p) => acc + p.gagnes, 0)
  const totalProspects = PERFORMANCES.reduce((acc, p) => acc + p.prospects, 0)

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
      {/* KPIs */}
      <View style={s.kpiRow}>
        {[
          { label: 'Prospects', value: totalProspects.toString(), icon: 'people-outline', c: '#3b82f6' },
          { label: 'Convertis', value: total.toString(), icon: 'checkmark-circle-outline', c: '#10b981' },
          { label: 'Pipeline', value: '47.5 M', icon: 'cash-outline', c: '#f59e0b' },
          { label: 'Conv. moy.', value: '47%', icon: 'trending-up-outline', c: '#8b5cf6' },
        ].map((k, i) => (
          <View key={i} style={s.kpiCard}>
            <View style={[s.kpiIcon, { backgroundColor: k.c + '20' }]}>
              <Ionicons name={k.icon as never} size={18} color={k.c} />
            </View>
            <Text style={s.kpiValue}>{k.value}</Text>
            <Text style={s.kpiLabel}>{k.label}</Text>
          </View>
        ))}
      </View>

      {/* Classement */}
      <View style={s.card}>
        <Text style={s.sectionTitle}>Classement commerciaux</Text>
        {PERFORMANCES.map((p, i) => (
          <View key={i} style={s.rankRow}>
            <View style={[s.rankNum, { backgroundColor: i === 0 ? '#fef08a' : '#f1f5f9' }]}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: '#374151' }}>{i + 1}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.rankNom}>{p.nom}</Text>
              <Text style={s.rankSub}>{p.prospects} prospects · {p.gagnes} gagnés</Text>
              <View style={s.progressBar}>
                <View style={[s.progressFill, { width: `${p.taux}%`, backgroundColor: i === 0 ? '#10b981' : '#3b82f6' }]} />
              </View>
            </View>
            <View style={{ alignItems: 'flex-end' }}>
              <Text style={s.rankValeur}>{p.valeur}</Text>
              <Text style={[s.rankTaux, { color: p.taux >= 50 ? '#10b981' : '#f59e0b' }]}>{p.taux}%</Text>
            </View>
          </View>
        ))}
      </View>

      {/* Répartition Vie / Non-Vie */}
      <View style={s.card}>
        <Text style={s.sectionTitle}>Répartition pipeline</Text>
        {[
          { label: 'Non-Vie (Auto, MRH, RC, Transport)', pct: 58, c: '#3b82f6' },
          { label: 'Vie (Épargne, Décès, Prévoyance…)',   pct: 42, c: '#ec4899' },
        ].map((r, i) => (
          <View key={i} style={{ marginTop: 10 }}>
            <View style={s.repartRow}>
              <Text style={s.repartLabel}>{r.label}</Text>
              <Text style={[s.repartPct, { color: r.c }]}>{r.pct}%</Text>
            </View>
            <View style={s.progressBar}>
              <View style={[s.progressFill, { width: `${r.pct}%`, backgroundColor: r.c }]} />
            </View>
          </View>
        ))}
      </View>
    </ScrollView>
  )
}

// ─── Formulaire nouveau prospect ───────────────────────────────────────────────
function FormulaireProspect({ onAjouter }: { onAjouter: (p: Prospect) => void }) {
  const [visible, setVisible] = useState(false)
  const [form, setForm] = useState({
    nom: '', entreprise: '', telephone: '', email: '',
    produit: PRODUITS[0].label, notes: '',
  })

  const valider = () => {
    if (!form.nom || !form.telephone) {
      Alert.alert('Champs requis', 'Nom et téléphone sont obligatoires.')
      return
    }
    const produit = PRODUITS.find(p => p.label === form.produit)!
    onAjouter({
      id: Date.now().toString(),
      nom: form.nom,
      entreprise: form.entreprise,
      telephone: form.telephone,
      email: form.email,
      etape: 'lead',
      famille: produit.famille,
      produit: form.produit,
      valeur_estimee: 500000,
      date_creation: new Date().toISOString().slice(0, 10),
      commercial: 'Moi',
      notes: form.notes,
    })
    setForm({ nom: '', entreprise: '', telephone: '', email: '', produit: PRODUITS[0].label, notes: '' })
    setVisible(false)
  }

  return (
    <>
      <TouchableOpacity style={s.fabBtn} onPress={() => setVisible(true)}>
        <Ionicons name="add" size={24} color="#fff" />
      </TouchableOpacity>

      <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setVisible(false)}>
        <ScrollView style={{ flex: 1, backgroundColor: '#f8fafc' }}>
          <View style={s.modalHeader}>
            <Text style={s.modalNom}>Nouveau prospect</Text>
            <TouchableOpacity onPress={() => setVisible(false)} style={s.closeBtn}>
              <Ionicons name="close" size={22} color="#64748b" />
            </TouchableOpacity>
          </View>
          <View style={{ padding: 16, gap: 12 }}>
            {[
              { key: 'nom', label: 'Nom complet *', placeholder: 'Diallo Moussa' },
              { key: 'entreprise', label: 'Entreprise', placeholder: 'SARL Diallo & Fils' },
              { key: 'telephone', label: 'Téléphone *', placeholder: '+237 6 XX XX XX XX' },
              { key: 'email', label: 'Email', placeholder: 'contact@email.com' },
            ].map(f => (
              <View key={f.key}>
                <Text style={s.fieldLabel}>{f.label}</Text>
                <TextInput
                  style={s.textInput}
                  placeholder={f.placeholder}
                  value={(form as never)[f.key]}
                  onChangeText={v => setForm(prev => ({ ...prev, [f.key]: v }))}
                  keyboardType={f.key === 'telephone' ? 'phone-pad' : f.key === 'email' ? 'email-address' : 'default'}
                />
              </View>
            ))}

            <View>
              <Text style={s.fieldLabel}>Produit</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 6 }}>
                <View style={{ flexDirection: 'row', gap: 8, paddingRight: 16 }}>
                  {PRODUITS.map(p => (
                    <TouchableOpacity
                      key={p.label}
                      style={[s.produitChip, {
                        backgroundColor: form.produit === p.label
                          ? (p.famille === 'vie' ? '#ec4899' : '#1d4ed8')
                          : '#e2e8f0',
                      }]}
                      onPress={() => setForm(prev => ({ ...prev, produit: p.label }))}
                    >
                      <Text style={{ fontSize: 11, fontWeight: '600', color: form.produit === p.label ? '#fff' : '#475569' }}>
                        {p.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            </View>

            <View>
              <Text style={s.fieldLabel}>Notes</Text>
              <TextInput
                style={[s.textInput, { height: 72, textAlignVertical: 'top' }]}
                multiline
                placeholder="Contexte, besoins exprimés…"
                value={form.notes}
                onChangeText={v => setForm(prev => ({ ...prev, notes: v }))}
              />
            </View>

            <TouchableOpacity style={s.submitBtn} onPress={valider}>
              <Ionicons name="checkmark-circle-outline" size={18} color="#fff" />
              <Text style={s.submitText}>Créer le prospect</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </Modal>
    </>
  )
}

// ─── Screen principal ──────────────────────────────────────────────────────────
type OngletType = 'pipeline' | 'prospects' | 'performances'

export default function CommercialScreen() {
  const [onglet, setOnglet] = useState<OngletType>('pipeline')
  const [prospects, setProspects] = useState<Prospect[]>(DEMO_PROSPECTS)
  const [selected, setSelected] = useState<Prospect | null>(null)
  const [filtreEtape, setFiltreEtape] = useState<Etape | 'all'>('all')

  const ajouter = (p: Prospect) => setProspects(prev => [p, ...prev])
  const mettreAJour = (p: Prospect) => {
    setProspects(prev => prev.map(x => x.id === p.id ? p : x))
    setSelected(p)
  }

  const filtres = filtreEtape === 'all' ? prospects : prospects.filter(p => p.etape === filtreEtape)

  return (
    <View style={{ flex: 1, backgroundColor: '#f1f5f9' }}>
      {/* Onglets */}
      <View style={s.tabs}>
        {([
          { key: 'pipeline', label: 'Pipeline', icon: 'git-network-outline' },
          { key: 'prospects', label: 'Prospects', icon: 'people-outline' },
          { key: 'performances', label: 'Perf.', icon: 'bar-chart-outline' },
        ] as { key: OngletType; label: string; icon: string }[]).map(t => (
          <TouchableOpacity
            key={t.key}
            style={[s.tab, onglet === t.key && s.tabActive]}
            onPress={() => setOnglet(t.key)}
          >
            <Ionicons name={t.icon as never} size={15} color={onglet === t.key ? '#1d4ed8' : '#94a3b8'} />
            <Text style={[s.tabText, onglet === t.key && s.tabTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <DemoBanner style={{ marginHorizontal: 12, marginTop: 8 }} />

      {/* ── Pipeline (kanban horizontal) ── */}
      {onglet === 'pipeline' && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', padding: 12, gap: 12 }}>
            {ETAPES.map(etape => {
              const liste = prospects.filter(p => p.etape === etape.key)
              const total = liste.reduce((a, p) => a + p.valeur_estimee, 0)
              return (
                <View key={etape.key} style={[s.kanbanCol, { width: SCREEN_W * 0.7 }]}>
                  <View style={[s.kanbanHeader, { borderTopColor: etape.couleur }]}>
                    <Text style={[s.kanbanTitle, { color: etape.couleur }]}>{etape.label}</Text>
                    <View style={[s.kanbanBadge, { backgroundColor: etape.couleur + '20' }]}>
                      <Text style={[s.kanbanCount, { color: etape.couleur }]}>{liste.length}</Text>
                    </View>
                  </View>
                  <Text style={s.kanbanTotal}>{fmt(total)} XAF</Text>
                  <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
                    {liste.map(p => (
                      <ProspectCard key={p.id} p={p} onPress={() => setSelected(p)} />
                    ))}
                    {liste.length === 0 && (
                      <View style={s.emptyCol}>
                        <Text style={{ fontSize: 12, color: '#cbd5e1' }}>Aucun prospect</Text>
                      </View>
                    )}
                  </ScrollView>
                </View>
              )
            })}
          </View>
        </ScrollView>
      )}

      {/* ── Liste prospects ── */}
      {onglet === 'prospects' && (
        <>
          {/* Filtres par étape */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filtreBar}>
            <View style={{ flexDirection: 'row', gap: 8, padding: 12 }}>
              <TouchableOpacity
                style={[s.filtreChip, filtreEtape === 'all' && s.filtreChipActive]}
                onPress={() => setFiltreEtape('all')}
              >
                <Text style={[s.filtreText, filtreEtape === 'all' && { color: '#fff' }]}>Tous ({prospects.length})</Text>
              </TouchableOpacity>
              {ETAPES.map(e => {
                const cnt = prospects.filter(p => p.etape === e.key).length
                if (cnt === 0) return null
                return (
                  <TouchableOpacity
                    key={e.key}
                    style={[s.filtreChip, filtreEtape === e.key && { backgroundColor: e.couleur }]}
                    onPress={() => setFiltreEtape(e.key)}
                  >
                    <Text style={[s.filtreText, filtreEtape === e.key && { color: '#fff' }]}>
                      {e.label} ({cnt})
                    </Text>
                  </TouchableOpacity>
                )
              })}
            </View>
          </ScrollView>
          <ScrollView contentContainerStyle={{ padding: 12, paddingBottom: 80, gap: 10 }}>
            {filtres.map(p => (
              <ProspectCard key={p.id} p={p} onPress={() => setSelected(p)} />
            ))}
            {filtres.length === 0 && (
              <View style={s.emptyState}>
                <Ionicons name="people-outline" size={40} color="#cbd5e1" />
                <Text style={s.emptyText}>Aucun prospect</Text>
              </View>
            )}
          </ScrollView>
          <FormulaireProspect onAjouter={ajouter} />
        </>
      )}

      {/* ── Performances ── */}
      {onglet === 'performances' && <OngletPerformances />}

      {/* Modal détail */}
      <ModalDetail
        prospect={selected}
        visible={!!selected}
        onClose={() => setSelected(null)}
        onUpdate={mettreAJour}
      />
    </View>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  tabs: {
    flexDirection: 'row', backgroundColor: '#fff',
    borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10 },
  tabActive: { borderBottomWidth: 2, borderBottomColor: '#1d4ed8' },
  tabText: { fontSize: 12, fontWeight: '600', color: '#94a3b8' },
  tabTextActive: { color: '#1d4ed8' },

  card: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14,
    borderLeftWidth: 3, borderLeftColor: '#3b82f6',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06, shadowRadius: 3, elevation: 2,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 6 },
  cardNom: { fontSize: 14, fontWeight: '700', color: '#1e293b' },
  cardEntreprise: { fontSize: 11, color: '#64748b', marginTop: 1 },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  valeurText: { fontSize: 13, fontWeight: '700', color: '#1e293b' },
  commercialText: { fontSize: 11, color: '#94a3b8' },
  produitText: { fontSize: 11, color: '#475569' },

  famBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  famText: { fontSize: 10, fontWeight: '700' },

  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  badgeText: { fontSize: 10, fontWeight: '700' },

  kanbanCol: {
    backgroundColor: '#f8fafc', borderRadius: 12,
    padding: 10, flex: 1, minHeight: 400,
    borderWidth: 1, borderColor: '#e2e8f0',
  },
  kanbanHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderTopWidth: 3, paddingTop: 8, marginBottom: 2 },
  kanbanTitle: { fontSize: 13, fontWeight: '700' },
  kanbanBadge: { width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  kanbanCount: { fontSize: 11, fontWeight: '700' },
  kanbanTotal: { fontSize: 11, color: '#94a3b8', marginBottom: 8 },
  emptyCol: { alignItems: 'center', paddingVertical: 30 },

  filtreBar: { backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e8f0', maxHeight: 52 },
  filtreChip: {
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20,
    backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0',
  },
  filtreChipActive: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  filtreText: { fontSize: 11, fontWeight: '600', color: '#475569' },

  emptyState: { alignItems: 'center', paddingVertical: 60, gap: 10 },
  emptyText: { fontSize: 14, color: '#94a3b8' },

  fabBtn: {
    position: 'absolute', bottom: 20, right: 20,
    width: 54, height: 54, borderRadius: 27,
    backgroundColor: '#1d4ed8', alignItems: 'center', justifyContent: 'center',
    shadowColor: '#1d4ed8', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4, shadowRadius: 8, elevation: 6,
  },

  modalHeader: {
    flexDirection: 'row', alignItems: 'flex-start', padding: 16,
    borderBottomWidth: 1, borderBottomColor: '#e2e8f0', gap: 12,
    backgroundColor: '#fff',
  },
  modalNom: { fontSize: 18, fontWeight: '700', color: '#1e293b' },
  modalEntreprise: { fontSize: 12, color: '#64748b', marginTop: 2 },
  closeBtn: { padding: 6, borderRadius: 8, backgroundColor: '#f1f5f9' },

  detailCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05, shadowRadius: 3, elevation: 1,
  },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#374151', marginBottom: 10 },

  etapeRow: { flexDirection: 'row', gap: 4, flexWrap: 'wrap', marginBottom: 10 },
  etapeStep: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },

  avancerBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#1d4ed8', padding: 10, borderRadius: 8,
  },
  avancerText: { color: '#fff', fontSize: 13, fontWeight: '600' },

  infoRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  infoText: { fontSize: 13, color: '#374151' },

  iaBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#7c3aed', padding: 10, borderRadius: 8, marginBottom: 10,
  },
  iaBtnText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  propositionBox: { backgroundColor: '#f8f7ff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e9d5ff' },
  propositionText: { fontSize: 12, color: '#374151', lineHeight: 18 },

  fieldLabel: { fontSize: 12, fontWeight: '600', color: '#374151', marginBottom: 4 },
  textInput: {
    backgroundColor: '#fff', borderWidth: 1, borderColor: '#d1d5db',
    borderRadius: 8, padding: 10, fontSize: 13, color: '#1e293b',
  },
  produitChip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20 },
  submitBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#1d4ed8', padding: 14, borderRadius: 10,
  },
  submitText: { color: '#fff', fontSize: 15, fontWeight: '700' },

  kpiRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 4 },
  kpiCard: {
    width: (SCREEN_W - 52) / 2,
    backgroundColor: '#fff', borderRadius: 12, padding: 12,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06, shadowRadius: 3, elevation: 2,
  },
  kpiIcon: { width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  kpiValue: { fontSize: 18, fontWeight: '800', color: '#1e293b' },
  kpiLabel: { fontSize: 10, color: '#64748b', marginTop: 2 },

  rankRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 10 },
  rankNum: { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  rankNom: { fontSize: 13, fontWeight: '600', color: '#1e293b' },
  rankSub: { fontSize: 11, color: '#64748b', marginTop: 1 },
  rankValeur: { fontSize: 13, fontWeight: '700', color: '#1e293b' },
  rankTaux: { fontSize: 11, fontWeight: '600' },

  progressBar: { height: 6, backgroundColor: '#e2e8f0', borderRadius: 3, marginTop: 4, overflow: 'hidden' },
  progressFill: { height: 6, borderRadius: 3 },

  repartRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  repartLabel: { fontSize: 12, color: '#374151', flex: 1 },
  repartPct: { fontSize: 13, fontWeight: '700' },
})
