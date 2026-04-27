import { useState, useRef } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, Modal, ActivityIndicator, Alert, Dimensions,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'

const SCREEN_W = Dimensions.get('window').width

// ─── Types ────────────────────────────────────────────────────────────────────
type StatutPiece = 'en_attente' | 'analyse_en_cours' | 'valide' | 'rejete'
type TypeFournisseur = 'garage' | 'clinique' | 'pharmacie' | 'expert' | 'avocat' | 'pompes_funebres' | 'autre'

interface PieceFournisseur {
  id: string
  fournisseur: string
  type_fournisseur: TypeFournisseur
  sinistre_ref: string
  type_document: string
  fichier_nom: string
  date_envoi: string
  statut: StatutPiece
  score_ia: number | null
  analyse_ia: string
  importer_orass: boolean
}

// ─── Config ────────────────────────────────────────────────────────────────────
const TYPES_FOURNISSEUR: { key: TypeFournisseur; label: string; icon: string; couleur: string }[] = [
  { key: 'garage',          label: 'Garage / Carrosserie', icon: 'car-outline',           couleur: '#3b82f6' },
  { key: 'clinique',        label: 'Clinique / Hôpital',   icon: 'medkit-outline',         couleur: '#ef4444' },
  { key: 'pharmacie',       label: 'Pharmacie',             icon: 'flask-outline',          couleur: '#10b981' },
  { key: 'expert',          label: 'Expert sinistre',       icon: 'search-outline',         couleur: '#f59e0b' },
  { key: 'avocat',          label: 'Avocat / Huissier',     icon: 'scale-outline',          couleur: '#8b5cf6' },
  { key: 'pompes_funebres', label: 'Pompes funèbres',       icon: 'flower-outline',         couleur: '#64748b' },
  { key: 'autre',           label: 'Autre',                 icon: 'ellipsis-horizontal',    couleur: '#94a3b8' },
]

const TYPES_DOCUMENTS = [
  'Facture de réparation',
  'Rapport médical',
  'Ordonnance / Facture pharmacie',
  'Rapport d\'expertise',
  'Constat amiable',
  'Certificat de décès',
  'Devis de réparation',
  'Bulletin de sortie',
  'Jugement / Décision',
  'Autre document',
]

const DEMO_PIECES: PieceFournisseur[] = [
  {
    id: 'f1', fournisseur: 'Garage Central Yaoundé',
    type_fournisseur: 'garage', sinistre_ref: 'SIN-2026-0342',
    type_document: 'Facture de réparation', fichier_nom: 'facture_reparation_342.pdf',
    date_envoi: '2026-04-08 14:32', statut: 'en_attente',
    score_ia: null, analyse_ia: '', importer_orass: false,
  },
  {
    id: 'f2', fournisseur: 'Clinique Les Sœurs',
    type_fournisseur: 'clinique', sinistre_ref: 'SIN-2026-0289',
    type_document: 'Rapport médical', fichier_nom: 'rapport_medical_289.pdf',
    date_envoi: '2026-04-07 09:15', statut: 'analyse_en_cours',
    score_ia: 78, analyse_ia: 'Montant cohérent avec les tarifs conventionnels. Actes correspondant au diagnostic déclaré. Aucune anomalie détectée.', importer_orass: false,
  },
  {
    id: 'f3', fournisseur: 'Expert Assurance SARL',
    type_fournisseur: 'expert', sinistre_ref: 'SIN-2026-0301',
    type_document: 'Rapport d\'expertise', fichier_nom: 'rapport_expertise_301.pdf',
    date_envoi: '2026-04-06 16:45', statut: 'valide',
    score_ia: 92, analyse_ia: 'Document authentique. Valeur de remplacement dans les normes marché. Recommandation : importer vers ORASS.', importer_orass: true,
  },
  {
    id: 'f4', fournisseur: 'Pharmacie du Centre',
    type_fournisseur: 'pharmacie', sinistre_ref: 'SIN-2026-0255',
    type_document: 'Ordonnance / Facture pharmacie', fichier_nom: 'facture_pharma_255.pdf',
    date_envoi: '2026-04-05 11:20', statut: 'rejete',
    score_ia: 34, analyse_ia: 'ALERTE : Montant facturé (185 000 XAF) anormalement élevé par rapport au diagnostic. Médicaments non listés au référentiel CIMA. Risque de fraude élevé.', importer_orass: false,
  },
]

// ─── Helpers ───────────────────────────────────────────────────────────────────
const statutCfg = (s: StatutPiece) => {
  const map = {
    en_attente:         { label: 'En attente',     couleur: '#f59e0b', bg: '#fffbeb' },
    analyse_en_cours:   { label: 'Analyse en cours', couleur: '#3b82f6', bg: '#eff6ff' },
    valide:             { label: 'Validé',          couleur: '#10b981', bg: '#f0fdf4' },
    rejete:             { label: 'Rejeté',          couleur: '#ef4444', bg: '#fef2f2' },
  }
  return map[s]
}

const fournisseurCfg = (t: TypeFournisseur) =>
  TYPES_FOURNISSEUR.find(x => x.key === t) ?? TYPES_FOURNISSEUR[TYPES_FOURNISSEUR.length - 1]

// ─── Portail fournisseur (vue fournisseur) ─────────────────────────────────────
function PortailFournisseur({ onEnvoi }: { onEnvoi: (p: PieceFournisseur) => void }) {
  const [typeFourn, setTypeFourn] = useState<TypeFournisseur>('garage')
  const [sinistreRef, setSinistreRef] = useState('')
  const [typeDoc, setTypeDoc] = useState(TYPES_DOCUMENTS[0])
  const [nomFourn, setNomFourn] = useState('')
  const [envoi, setEnvoi] = useState(false)
  const [succes, setSucces] = useState(false)

  const scanner = async () => {
    // Simule la sélection d'un document (caméra / galerie)
    Alert.alert(
      'Capturer le document',
      'Choisissez la source',
      [
        { text: 'Caméra', onPress: () => soumettreDocument('scan_camera_' + Date.now() + '.jpg') },
        { text: 'Galerie', onPress: () => soumettreDocument('import_galerie_' + Date.now() + '.pdf') },
        { text: 'Annuler', style: 'cancel' },
      ]
    )
  }

  const soumettreDocument = async (fichier: string) => {
    if (!sinistreRef.trim()) {
      Alert.alert('Référence requise', 'Veuillez saisir la référence du sinistre.')
      return
    }
    if (!nomFourn.trim()) {
      Alert.alert('Nom requis', 'Veuillez renseigner votre nom / raison sociale.')
      return
    }
    setEnvoi(true)
    await new Promise(r => setTimeout(r, 1200))
    const piece: PieceFournisseur = {
      id: Date.now().toString(),
      fournisseur: nomFourn,
      type_fournisseur: typeFourn,
      sinistre_ref: sinistreRef.toUpperCase(),
      type_document: typeDoc,
      fichier_nom: fichier,
      date_envoi: new Date().toISOString().replace('T', ' ').slice(0, 16),
      statut: 'en_attente',
      score_ia: null,
      analyse_ia: '',
      importer_orass: false,
    }
    onEnvoi(piece)
    setEnvoi(false)
    setSucces(true)
    setSinistreRef('')
    setTimeout(() => setSucces(false), 3000)
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }}>
      {/* Bandeau intro */}
      <View style={ps.infoBanner}>
        <Ionicons name="information-circle-outline" size={18} color="#1d4ed8" />
        <Text style={ps.infoText}>
          Identifiez-vous et scannez vos documents. Ils seront transmis directement au bon dossier.
        </Text>
      </View>

      {/* Succès */}
      {succes && (
        <View style={ps.successBanner}>
          <Ionicons name="checkmark-circle-outline" size={18} color="#16a34a" />
          <Text style={ps.successText}>Document envoyé avec succès !</Text>
        </View>
      )}

      {/* Identité fournisseur */}
      <View style={ps.card}>
        <Text style={ps.sectionTitle}>Votre identité</Text>
        <Text style={ps.fieldLabel}>Nom / Raison sociale *</Text>
        <TextInput
          style={ps.input}
          placeholder="Ex: Garage Central Yaoundé"
          value={nomFourn}
          onChangeText={setNomFourn}
        />
        <Text style={[ps.fieldLabel, { marginTop: 10 }]}>Type de prestataire</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
          {TYPES_FOURNISSEUR.map(t => (
            <TouchableOpacity
              key={t.key}
              style={[ps.typeChip, typeFourn === t.key && { backgroundColor: t.couleur, borderColor: t.couleur }]}
              onPress={() => setTypeFourn(t.key)}
            >
              <Ionicons name={t.icon as never} size={12} color={typeFourn === t.key ? '#fff' : '#64748b'} />
              <Text style={[ps.typeChipText, typeFourn === t.key && { color: '#fff' }]}>{t.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Référence sinistre */}
      <View style={ps.card}>
        <Text style={ps.sectionTitle}>Référence du dossier</Text>
        <Text style={ps.fieldLabel}>N° sinistre *</Text>
        <TextInput
          style={ps.input}
          placeholder="SIN-2026-XXXX"
          value={sinistreRef}
          onChangeText={setSinistreRef}
          autoCapitalize="characters"
        />
        <Text style={[ps.fieldLabel, { marginTop: 10 }]}>Type de document</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 6 }}>
          <View style={{ flexDirection: 'row', gap: 8, paddingRight: 8 }}>
            {TYPES_DOCUMENTS.map(d => (
              <TouchableOpacity
                key={d}
                style={[ps.docChip, typeDoc === d && ps.docChipActive]}
                onPress={() => setTypeDoc(d)}
              >
                <Text style={[ps.docChipText, typeDoc === d && { color: '#fff' }]}>{d}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>
      </View>

      {/* Bouton scan */}
      <TouchableOpacity style={ps.scanBtn} onPress={scanner} disabled={envoi}>
        {envoi ? (
          <ActivityIndicator size="small" color="#fff" />
        ) : (
          <Ionicons name="camera-outline" size={28} color="#fff" />
        )}
        <Text style={ps.scanText}>{envoi ? 'Envoi en cours…' : 'Scanner / Importer le document'}</Text>
      </TouchableOpacity>

      <Text style={ps.hint}>
        Le document sera automatiquement acheminé vers le dossier sinistre concerné et analysé par notre IA.
      </Text>
    </ScrollView>
  )
}

// ─── File d'attente (vue employé compagnie) ────────────────────────────────────
function FileAttente({ pieces, onUpdate }: { pieces: PieceFournisseur[]; onUpdate: (p: PieceFournisseur) => void }) {
  const [selected, setSelected] = useState<PieceFournisseur | null>(null)
  const [analysing, setAnalysing] = useState<string | null>(null)

  const analyserIA = async (piece: PieceFournisseur) => {
    setAnalysing(piece.id)
    const updated = { ...piece, statut: 'analyse_en_cours' as StatutPiece }
    onUpdate(updated)
    await new Promise(r => setTimeout(r, 2000))

    // Demo : score aléatoire 20-95
    const score = Math.floor(Math.random() * 75) + 20
    const analyses = [
      score >= 80
        ? `Document authentique. Montant conforme aux tarifs de référence. Aucune anomalie détectée. Recommandation : valider et importer vers ORASS.`
        : score >= 50
        ? `Document plausible. Quelques écarts mineurs avec les tarifs conventionnels. Vérification manuelle recommandée avant import.`
        : `ALERTE : Anomalies détectées. Montant disproportionné (${(score * 1200).toLocaleString()} XAF d'écart). Risque fraude ${score < 35 ? 'élevé' : 'modéré'}. Validation manuelle obligatoire.`,
    ]
    const analysed: PieceFournisseur = {
      ...updated,
      statut: 'en_attente',
      score_ia: score,
      analyse_ia: analyses[0],
    }
    onUpdate(analysed)
    if (selected?.id === piece.id) setSelected(analysed)
    setAnalysing(null)
  }

  const valider = (piece: PieceFournisseur) => {
    const updated: PieceFournisseur = { ...piece, statut: 'valide', importer_orass: true }
    onUpdate(updated)
    if (selected?.id === piece.id) setSelected(updated)
    Alert.alert('Validé', `Document importé dans ORASS/Mercure — dossier ${piece.sinistre_ref}`)
  }

  const rejeter = (piece: PieceFournisseur) => {
    Alert.alert(
      'Rejeter le document',
      'Confirmer le rejet de cette pièce ?',
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Rejeter', style: 'destructive',
          onPress: () => {
            const updated: PieceFournisseur = { ...piece, statut: 'rejete' }
            onUpdate(updated)
            if (selected?.id === piece.id) setSelected(updated)
          },
        },
      ]
    )
  }

  const enAttente = pieces.filter(p => p.statut === 'en_attente').length
  const analyses = pieces.filter(p => p.statut === 'analyse_en_cours').length

  return (
    <>
      {/* Stats */}
      <View style={fa.statsRow}>
        {[
          { label: 'En attente', value: enAttente, c: '#f59e0b' },
          { label: 'En analyse', value: analyses, c: '#3b82f6' },
          { label: 'Validés', value: pieces.filter(p => p.statut === 'valide').length, c: '#10b981' },
          { label: 'Rejetés', value: pieces.filter(p => p.statut === 'rejete').length, c: '#ef4444' },
        ].map((k, i) => (
          <View key={i} style={[fa.statCard, { borderTopColor: k.c }]}>
            <Text style={[fa.statValue, { color: k.c }]}>{k.value}</Text>
            <Text style={fa.statLabel}>{k.label}</Text>
          </View>
        ))}
      </View>

      <ScrollView contentContainerStyle={{ padding: 12, paddingBottom: 30, gap: 10 }}>
        {pieces.map(piece => {
          const cfg = statutCfg(piece.statut)
          const fourn = fournisseurCfg(piece.type_fournisseur)
          return (
            <TouchableOpacity key={piece.id} style={fa.pieceCard} onPress={() => setSelected(piece)}>
              <View style={fa.pieceHeader}>
                <View style={[fa.fournIcon, { backgroundColor: fourn.couleur + '20' }]}>
                  <Ionicons name={fourn.icon as never} size={18} color={fourn.couleur} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={fa.fournNom}>{piece.fournisseur}</Text>
                  <Text style={fa.pieceRef}>{piece.sinistre_ref} · {piece.type_document}</Text>
                </View>
                <View style={[fa.statutBadge, { backgroundColor: cfg.bg }]}>
                  <Text style={[fa.statutText, { color: cfg.couleur }]}>{cfg.label}</Text>
                </View>
              </View>

              <View style={fa.pieceFooter}>
                <Text style={fa.pieceDate}>{piece.date_envoi}</Text>
                {piece.score_ia !== null && (
                  <View style={[fa.scoreBadge, {
                    backgroundColor: piece.score_ia >= 70 ? '#dcfce7' : piece.score_ia >= 45 ? '#fffbeb' : '#fef2f2',
                  }]}>
                    <Text style={{
                      fontSize: 11, fontWeight: '700',
                      color: piece.score_ia >= 70 ? '#16a34a' : piece.score_ia >= 45 ? '#d97706' : '#dc2626',
                    }}>
                      IA {piece.score_ia}/100
                    </Text>
                  </View>
                )}
              </View>

              {/* Actions rapides */}
              {piece.statut === 'en_attente' && (
                <View style={fa.actionsRow}>
                  {piece.score_ia === null && (
                    <TouchableOpacity
                      style={[fa.actionBtn, { backgroundColor: '#7c3aed' }]}
                      onPress={() => analyserIA(piece)}
                      disabled={analysing === piece.id}
                    >
                      {analysing === piece.id
                        ? <ActivityIndicator size="small" color="#fff" />
                        : <Ionicons name="sparkles-outline" size={14} color="#fff" />
                      }
                      <Text style={fa.actionText}>{analysing === piece.id ? 'Analyse…' : 'Analyser IA'}</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity style={[fa.actionBtn, { backgroundColor: '#10b981' }]} onPress={() => valider(piece)}>
                    <Ionicons name="checkmark-outline" size={14} color="#fff" />
                    <Text style={fa.actionText}>Valider → ORASS</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[fa.actionBtn, { backgroundColor: '#ef4444' }]} onPress={() => rejeter(piece)}>
                    <Ionicons name="close-outline" size={14} color="#fff" />
                    <Text style={fa.actionText}>Rejeter</Text>
                  </TouchableOpacity>
                </View>
              )}
            </TouchableOpacity>
          )
        })}

        {pieces.length === 0 && (
          <View style={{ alignItems: 'center', paddingVertical: 60, gap: 10 }}>
            <Ionicons name="checkmark-done-circle-outline" size={48} color="#cbd5e1" />
            <Text style={{ fontSize: 14, color: '#94a3b8' }}>Aucune pièce en attente</Text>
          </View>
        )}
      </ScrollView>

      {/* Modal détail */}
      <Modal
        visible={!!selected}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setSelected(null)}
      >
        {selected && (
          <ScrollView style={{ flex: 1, backgroundColor: '#f8fafc' }}>
            <View style={fa.modalHeader}>
              <View style={{ flex: 1 }}>
                <Text style={fa.modalTitre}>{selected.fournisseur}</Text>
                <Text style={fa.modalSub}>{selected.type_document} — {selected.sinistre_ref}</Text>
              </View>
              <TouchableOpacity onPress={() => setSelected(null)} style={{ padding: 6, borderRadius: 8, backgroundColor: '#f1f5f9' }}>
                <Ionicons name="close" size={22} color="#64748b" />
              </TouchableOpacity>
            </View>

            <View style={{ padding: 16, gap: 12 }}>
              {/* Infos */}
              <View style={fa.detailCard}>
                <Text style={fa.detailSection}>Informations</Text>
                {[
                  ['Fournisseur', selected.fournisseur],
                  ['Type', fournisseurCfg(selected.type_fournisseur).label],
                  ['Sinistre', selected.sinistre_ref],
                  ['Document', selected.type_document],
                  ['Fichier', selected.fichier_nom],
                  ['Reçu le', selected.date_envoi],
                ].map(([k, v]) => (
                  <View key={k} style={fa.infoRow}>
                    <Text style={fa.infoKey}>{k}</Text>
                    <Text style={fa.infoVal}>{v}</Text>
                  </View>
                ))}
              </View>

              {/* Analyse YukpoPro */}
              {selected.score_ia !== null && (
                <View style={[fa.detailCard, {
                  borderLeftWidth: 4,
                  borderLeftColor: selected.score_ia >= 70 ? '#10b981' : selected.score_ia >= 45 ? '#f59e0b' : '#ef4444',
                }]}>
                  <Text style={fa.detailSection}>Analyse YukpoPro</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Text style={{ fontSize: 32, fontWeight: '800', color: selected.score_ia >= 70 ? '#10b981' : selected.score_ia >= 45 ? '#d97706' : '#dc2626' }}>
                      {selected.score_ia}
                    </Text>
                    <Text style={{ fontSize: 16, color: '#94a3b8', fontWeight: '600' }}>/100</Text>
                    <Text style={{ fontSize: 12, color: '#64748b', flex: 1 }}>Score de confiance</Text>
                  </View>
                  <Text style={{ fontSize: 13, color: '#374151', lineHeight: 20 }}>{selected.analyse_ia}</Text>
                </View>
              )}

              {/* Bouton analyse si pas encore analysé */}
              {selected.statut === 'en_attente' && selected.score_ia === null && (
                <TouchableOpacity
                  style={[fa.modalActionBtn, { backgroundColor: '#7c3aed' }]}
                  onPress={() => analyserIA(selected)}
                  disabled={analysing === selected.id}
                >
                  {analysing === selected.id
                    ? <ActivityIndicator size="small" color="#fff" />
                    : <Ionicons name="sparkles-outline" size={18} color="#fff" />
                  }
                  <Text style={fa.modalActionText}>
                    {analysing === selected.id ? 'Analyse en cours…' : 'Lancer l\'analyse YukpoPro'}
                  </Text>
                </TouchableOpacity>
              )}

              {/* Actions valider / rejeter */}
              {selected.statut === 'en_attente' && (
                <View style={{ gap: 10 }}>
                  <TouchableOpacity
                    style={[fa.modalActionBtn, { backgroundColor: '#10b981' }]}
                    onPress={() => valider(selected)}
                  >
                    <Ionicons name="cloud-upload-outline" size={18} color="#fff" />
                    <Text style={fa.modalActionText}>Valider et importer vers ORASS/Mercure</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[fa.modalActionBtn, { backgroundColor: '#ef4444' }]}
                    onPress={() => rejeter(selected)}
                  >
                    <Ionicons name="close-circle-outline" size={18} color="#fff" />
                    <Text style={fa.modalActionText}>Rejeter le document</Text>
                  </TouchableOpacity>
                </View>
              )}

              {/* Statut final */}
              {['valide', 'rejete'].includes(selected.statut) && (
                <View style={[fa.detailCard, { backgroundColor: selected.statut === 'valide' ? '#f0fdf4' : '#fef2f2' }]}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons
                      name={selected.statut === 'valide' ? 'checkmark-circle-outline' : 'close-circle-outline'}
                      size={22}
                      color={selected.statut === 'valide' ? '#16a34a' : '#dc2626'}
                    />
                    <Text style={{ fontSize: 14, fontWeight: '700', color: selected.statut === 'valide' ? '#16a34a' : '#dc2626' }}>
                      {selected.statut === 'valide' ? 'Document importé dans ORASS/Mercure' : 'Document rejeté'}
                    </Text>
                  </View>
                </View>
              )}
            </View>
          </ScrollView>
        )}
      </Modal>
    </>
  )
}

// ─── Screen principal ──────────────────────────────────────────────────────────
type OngletType = 'portail' | 'file_attente'

export default function FournisseurScreen() {
  const [onglet, setOnglet] = useState<OngletType>('portail')
  const [pieces, setPieces] = useState<PieceFournisseur[]>(DEMO_PIECES)
  const router = useRouter()

  const enAttente = pieces.filter(p => p.statut === 'en_attente').length

  const ajouterPiece = (p: PieceFournisseur) => setPieces(prev => [p, ...prev])
  const mettreAJour = (p: PieceFournisseur) => setPieces(prev => prev.map(x => x.id === p.id ? p : x))

  return (
    <View style={{ flex: 1, backgroundColor: '#f1f5f9' }}>
      {/* Header */}
      <View style={ms.header}>
        <TouchableOpacity onPress={() => router.back()} style={ms.backBtn}>
          <Ionicons name="arrow-back" size={20} color="#1e293b" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={ms.headerTitle}>Portail Fournisseurs</Text>
          <Text style={ms.headerSub}>Documents & File d'attente</Text>
        </View>
        {enAttente > 0 && (
          <View style={ms.notifBadge}>
            <Text style={ms.notifText}>{enAttente}</Text>
          </View>
        )}
      </View>

      {/* Onglets */}
      <View style={ms.tabs}>
        <TouchableOpacity
          style={[ms.tab, onglet === 'portail' && ms.tabActive]}
          onPress={() => setOnglet('portail')}
        >
          <Ionicons name="camera-outline" size={16} color={onglet === 'portail' ? '#1d4ed8' : '#94a3b8'} />
          <Text style={[ms.tabText, onglet === 'portail' && ms.tabTextActive]}>Portail fournisseur</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[ms.tab, onglet === 'file_attente' && ms.tabActive]}
          onPress={() => setOnglet('file_attente')}
        >
          <Ionicons name="time-outline" size={16} color={onglet === 'file_attente' ? '#1d4ed8' : '#94a3b8'} />
          <Text style={[ms.tabText, onglet === 'file_attente' && ms.tabTextActive]}>File d'attente</Text>
          {enAttente > 0 && (
            <View style={ms.tabBadge}>
              <Text style={ms.tabBadgeText}>{enAttente}</Text>
            </View>
          )}
        </TouchableOpacity>
      </View>

      {onglet === 'portail'
        ? <PortailFournisseur onEnvoi={ajouterPiece} />
        : <FileAttente pieces={pieces} onUpdate={mettreAJour} />
      }
    </View>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const ms = StyleSheet.create({
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: '#fff', padding: 16, paddingTop: 20,
    borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  backBtn: { padding: 6, borderRadius: 8, backgroundColor: '#f1f5f9' },
  headerTitle: { fontSize: 16, fontWeight: '700', color: '#1e293b' },
  headerSub: { fontSize: 11, color: '#64748b', marginTop: 1 },
  notifBadge: { backgroundColor: '#ef4444', borderRadius: 12, paddingHorizontal: 8, paddingVertical: 3 },
  notifText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  tabs: {
    flexDirection: 'row', backgroundColor: '#fff',
    borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10 },
  tabActive: { borderBottomWidth: 2, borderBottomColor: '#1d4ed8' },
  tabText: { fontSize: 12, fontWeight: '600', color: '#94a3b8' },
  tabTextActive: { color: '#1d4ed8' },
  tabBadge: { backgroundColor: '#ef4444', borderRadius: 10, paddingHorizontal: 5, paddingVertical: 1 },
  tabBadgeText: { color: '#fff', fontSize: 9, fontWeight: '700' },
})

const ps = StyleSheet.create({
  infoBanner: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8,
    backgroundColor: '#eff6ff', borderRadius: 10, padding: 12,
    borderWidth: 1, borderColor: '#bfdbfe',
  },
  infoText: { flex: 1, fontSize: 12, color: '#1e40af', lineHeight: 17 },
  successBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#f0fdf4', borderRadius: 10, padding: 12,
    borderWidth: 1, borderColor: '#bbf7d0',
  },
  successText: { fontSize: 13, color: '#15803d', fontWeight: '600' },
  card: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05, shadowRadius: 3, elevation: 1,
  },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#374151', marginBottom: 10 },
  fieldLabel: { fontSize: 12, fontWeight: '600', color: '#374151', marginBottom: 4 },
  input: {
    backgroundColor: '#f8fafc', borderWidth: 1, borderColor: '#d1d5db',
    borderRadius: 8, padding: 10, fontSize: 13, color: '#1e293b',
  },
  typeChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20,
    backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0',
  },
  typeChipText: { fontSize: 11, fontWeight: '600', color: '#64748b' },
  docChip: {
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20,
    backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0',
  },
  docChipActive: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  docChipText: { fontSize: 11, fontWeight: '600', color: '#475569' },
  scanBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12,
    backgroundColor: '#1d4ed8', borderRadius: 14, padding: 18,
    shadowColor: '#1d4ed8', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35, shadowRadius: 8, elevation: 5,
  },
  scanText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  hint: { fontSize: 11, color: '#94a3b8', textAlign: 'center', lineHeight: 16 },
})

const fa = StyleSheet.create({
  statsRow: {
    flexDirection: 'row', gap: 8, padding: 12,
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  statCard: {
    flex: 1, backgroundColor: '#f8fafc', borderRadius: 8, padding: 10,
    alignItems: 'center', borderTopWidth: 3,
  },
  statValue: { fontSize: 20, fontWeight: '800' },
  statLabel: { fontSize: 9, color: '#94a3b8', fontWeight: '600', marginTop: 2, textAlign: 'center' },

  pieceCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 12,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06, shadowRadius: 3, elevation: 2,
  },
  pieceHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 8 },
  fournIcon: { width: 38, height: 38, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  fournNom: { fontSize: 14, fontWeight: '700', color: '#1e293b' },
  pieceRef: { fontSize: 11, color: '#64748b', marginTop: 2 },
  statutBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  statutText: { fontSize: 10, fontWeight: '700' },
  pieceFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  pieceDate: { fontSize: 11, color: '#94a3b8' },
  scoreBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  actionsRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
  },
  actionText: { color: '#fff', fontSize: 11, fontWeight: '700' },

  modalHeader: {
    flexDirection: 'row', alignItems: 'flex-start', padding: 16,
    borderBottomWidth: 1, borderBottomColor: '#e2e8f0', gap: 12, backgroundColor: '#fff',
  },
  modalTitre: { fontSize: 17, fontWeight: '700', color: '#1e293b' },
  modalSub: { fontSize: 12, color: '#64748b', marginTop: 2 },
  detailCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05, shadowRadius: 3, elevation: 1,
  },
  detailSection: { fontSize: 13, fontWeight: '700', color: '#374151', marginBottom: 10 },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
  infoKey: { fontSize: 12, color: '#94a3b8', fontWeight: '600' },
  infoVal: { fontSize: 12, color: '#1e293b', fontWeight: '500', flex: 1, textAlign: 'right' },
  modalActionBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    padding: 14, borderRadius: 10,
  },
  modalActionText: { color: '#fff', fontSize: 14, fontWeight: '700' },
})
