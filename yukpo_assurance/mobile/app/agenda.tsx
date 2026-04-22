import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, Modal, ActivityIndicator, RefreshControl, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';

const PRIORITES = ['basse', 'normale', 'haute', 'urgente'];
const PRIO_COLORS: Record<string, string> = { basse: '#6B7280', normale: '#3B82F6', haute: '#F59E0B', urgente: '#EF4444' };
const STATUT_COLORS: Record<string, string> = { a_faire: '#6B7280', en_cours: '#3B82F6', bloquee: '#EF4444', terminee: '#10B981', annulee: '#D1D5DB' };
const STATUT_LABELS: Record<string, string> = { a_faire: 'À faire', en_cours: 'En cours', bloquee: 'Bloquée', terminee: 'Terminée', annulee: 'Annulée' };

export default function AgendaScreen() {
  const [tab, setTab] = useState<'taches' | 'resume'>('taches');
  const [taches, setTaches] = useState<any[]>([]);
  const [urgentes, setUrgentes] = useState<any[]>([]);
  const [resume, setResume] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [filterStatut, setFilterStatut] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [formTache, setFormTache] = useState({ titre: '', priorite: 'normale', description: '', date_echeance: '' });
  const [saving, setSaving] = useState(false);

  const token = async () => AsyncStorage.getItem('token');

  const chargerTaches = async () => {
    setLoading(true);
    try {
      const t = await token();
      const params = filterStatut ? `?statut=${filterStatut}` : '';
      const [r1, r2] = await Promise.all([
        fetch(`/api/v1/agenda/taches${params}&limit=50`, { headers: { Authorization: `Bearer ${t}` } }),
        fetch('/api/v1/agenda/taches/urgentes', { headers: { Authorization: `Bearer ${t}` } }),
      ]);
      const [d1, d2] = await Promise.all([r1.json(), r2.json()]);
      setTaches(Array.isArray(d1) ? d1 : []);
      setUrgentes(Array.isArray(d2) ? d2 : []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); setRefreshing(false); }
  };

  const chargerResume = async () => {
    const t = await token();
    const res = await fetch('/api/v1/agenda/resume-journalier', { headers: { Authorization: `Bearer ${t}` } });
    const data = await res.json();
    setResume(data);
  };

  const changerStatut = async (id: number, statut: string) => {
    const t = await token();
    await fetch(`/api/v1/agenda/taches/${id}/statut`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` },
      body: JSON.stringify({ statut }),
    });
    chargerTaches();
  };

  const creerTache = async () => {
    if (!formTache.titre.trim()) { Alert.alert('Titre requis'); return; }
    setSaving(true);
    const t = await token();
    await fetch('/api/v1/agenda/taches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` },
      body: JSON.stringify({ ...formTache, assigne_a: 1, date_echeance: formTache.date_echeance || undefined }),
    });
    setSaving(false);
    setShowModal(false);
    setFormTache({ titre: '', priorite: 'normale', description: '', date_echeance: '' });
    chargerTaches();
  };

  useEffect(() => {
    if (tab === 'taches') chargerTaches();
    if (tab === 'resume') chargerResume();
  }, [tab, filterStatut]);

  const onRefresh = () => { setRefreshing(true); if (tab === 'taches') chargerTaches(); else chargerResume(); };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Ionicons name="calendar-outline" size={22} color="#fff" />
        <Text style={styles.headerTitle}>Agenda & Tâches</Text>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowModal(true)}>
          <Ionicons name="add" size={22} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        {[{ k: 'taches', l: 'Mes tâches' }, { k: 'resume', l: 'Journée' }].map(({ k, l }) => (
          <TouchableOpacity key={k} style={[styles.tab, tab === k && styles.tabActive]}
            onPress={() => setTab(k as any)}>
            <Text style={[styles.tabText, tab === k && styles.tabTextActive]}>{l}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Onglet Tâches */}
      {tab === 'taches' && (
        <ScrollView style={styles.scroll} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
          {/* Urgentes */}
          {urgentes.length > 0 && (
            <View style={styles.urgenteSection}>
              <View style={styles.urgentHeader}>
                <Ionicons name="warning-outline" size={18} color="#F97316" />
                <Text style={styles.urgentTitle}>{urgentes.length} tâche(s) urgente(s) / en retard</Text>
              </View>
              {urgentes.slice(0, 3).map((t: any, i: number) => (
                <View key={i} style={styles.urgentItem}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.urgentItemTitle}>{t.titre}</Text>
                    <Text style={t._en_retard ? styles.retardText : styles.urgentJours}>
                      {t._en_retard ? '🔴 EN RETARD' : `⚠️ J-${t._jours_restants}`}
                    </Text>
                  </View>
                  <TouchableOpacity style={styles.doneBtn} onPress={() => changerStatut(t.id, 'terminee')}>
                    <Ionicons name="checkmark" size={14} color="#10B981" />
                    <Text style={styles.doneBtnText}>OK</Text>
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          )}

          {/* Filtres statut */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filters}>
            {['', 'a_faire', 'en_cours', 'bloquee', 'terminee'].map(s => (
              <TouchableOpacity key={s} style={[styles.filterBtn, filterStatut === s && styles.filterBtnActive]}
                onPress={() => setFilterStatut(s)}>
                <Text style={[styles.filterText, filterStatut === s && styles.filterTextActive]}>
                  {s ? STATUT_LABELS[s] : 'Toutes'}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {loading ? (
            <ActivityIndicator color="#3B82F6" style={{ marginTop: 40 }} />
          ) : taches.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="checkmark-done-outline" size={40} color="#D1D5DB" />
              <Text style={styles.emptyText}>Aucune tâche</Text>
            </View>
          ) : taches.map((t: any) => (
            <View key={t.id} style={styles.tacheCard}>
              <TouchableOpacity onPress={() => changerStatut(t.id, t.statut === 'terminee' ? 'a_faire' : 'terminee')}
                style={[styles.checkbox, t.statut === 'terminee' && styles.checkboxDone]}>
                {t.statut === 'terminee' && <Ionicons name="checkmark" size={14} color="#fff" />}
              </TouchableOpacity>
              <View style={{ flex: 1 }}>
                <View style={styles.tacheHeader}>
                  <Text style={[styles.tacheTitre, t.statut === 'terminee' && styles.tacheTitreTerminee]}
                    numberOfLines={2}>{t.titre}</Text>
                  <View style={[styles.prioBadge, { backgroundColor: PRIO_COLORS[t.priorite] + '20' }]}>
                    <Text style={[styles.prioText, { color: PRIO_COLORS[t.priorite] }]}>{t.priorite}</Text>
                  </View>
                </View>
                {t.date_echeance && (
                  <Text style={styles.echeanceText}>
                    <Ionicons name="time-outline" size={11} /> {new Date(t.date_echeance).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
                  </Text>
                )}
                {t.lien_police && <Text style={styles.liaisonText}>🔗 Police : {t.lien_police}</Text>}
                {t.lien_sinistre && <Text style={styles.liaisonText}>🔗 Sinistre #{t.lien_sinistre}</Text>}
                {/* Progress */}
                {t.statut === 'en_cours' && (
                  <View style={styles.progressRow}>
                    <View style={styles.progressBar}>
                      <View style={[styles.progressFill, { width: `${t.avancement_pct || 0}%` }]} />
                    </View>
                    <Text style={styles.progressText}>{t.avancement_pct || 0}%</Text>
                  </View>
                )}
              </View>
              <View style={styles.statutBadge}>
                <View style={[styles.statutDot, { backgroundColor: STATUT_COLORS[t.statut] || '#6B7280' }]} />
                <Text style={[styles.statutText, { color: STATUT_COLORS[t.statut] || '#6B7280' }]}>
                  {STATUT_LABELS[t.statut] || t.statut}
                </Text>
              </View>
            </View>
          ))}
        </ScrollView>
      )}

      {/* Résumé journalier */}
      {tab === 'resume' && (
        <ScrollView style={styles.scroll} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
          {resume ? (
            <>
              <View style={styles.resumeCard}>
                <Text style={styles.resumeTitle}>📅 {new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}</Text>
                <Text style={styles.resumeBody}>{resume.resume_texte}</Text>
              </View>

              {resume.evenements_du_jour?.length > 0 && (
                <View style={styles.sectionCard}>
                  <Text style={styles.sectionTitle}>🗓️ Événements du jour</Text>
                  {resume.evenements_du_jour.map((e: any, i: number) => (
                    <View key={i} style={styles.evtItem}>
                      <View style={styles.evtBar} />
                      <View>
                        <Text style={styles.evtTitre}>{e.titre}</Text>
                        {e.date_debut && <Text style={styles.evtHeure}>{new Date(e.date_debut).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</Text>}
                      </View>
                    </View>
                  ))}
                </View>
              )}

              {resume.taches_actives?.length > 0 && (
                <View style={styles.sectionCard}>
                  <Text style={styles.sectionTitle}>✅ Tâches actives ({resume.taches_actives.length})</Text>
                  {resume.taches_actives.map((t: any, i: number) => (
                    <View key={i} style={styles.tacheResumeItem}>
                      <View style={[styles.prioDot, { backgroundColor: PRIO_COLORS[t.priorite] || '#6B7280' }]} />
                      <Text style={styles.tacheResumeText}>{t.titre}</Text>
                    </View>
                  ))}
                </View>
              )}
            </>
          ) : (
            <ActivityIndicator color="#3B82F6" style={{ marginTop: 40 }} />
          )}
        </ScrollView>
      )}

      {/* Modal Nouvelle tâche */}
      <Modal visible={showModal} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setShowModal(false)}>
        <SafeAreaView style={styles.modal}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Nouvelle tâche</Text>
            <TouchableOpacity onPress={() => setShowModal(false)}>
              <Ionicons name="close" size={24} color="#374151" />
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.modalBody}>
            <Text style={styles.inputLabel}>Titre *</Text>
            <TextInput style={styles.input} value={formTache.titre} onChangeText={t => setFormTache(f => ({ ...f, titre: t }))} placeholder="Titre de la tâche" />

            <Text style={styles.inputLabel}>Description</Text>
            <TextInput style={[styles.input, { height: 80 }]} value={formTache.description} onChangeText={t => setFormTache(f => ({ ...f, description: t }))} placeholder="Description optionnelle" multiline />

            <Text style={styles.inputLabel}>Priorité</Text>
            <View style={styles.prioRow}>
              {PRIORITES.map(p => (
                <TouchableOpacity key={p} style={[styles.prioBtn, formTache.priorite === p && { backgroundColor: PRIO_COLORS[p], borderColor: PRIO_COLORS[p] }]}
                  onPress={() => setFormTache(f => ({ ...f, priorite: p }))}>
                  <Text style={[styles.prioBtnText, formTache.priorite === p && { color: '#fff' }]}>{p}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.inputLabel}>Échéance (AAAA-MM-JJ HH:MM)</Text>
            <TextInput style={styles.input} value={formTache.date_echeance} onChangeText={t => setFormTache(f => ({ ...f, date_echeance: t }))} placeholder="Ex: 2026-05-15 10:00" />

            <TouchableOpacity style={[styles.saveBtn, saving && { opacity: 0.6 }]} onPress={creerTache} disabled={saving}>
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveBtnText}>Créer la tâche</Text>}
            </TouchableOpacity>
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F9FAFB' },
  header: { backgroundColor: '#1E3A8A', flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 14 },
  headerTitle: { color: '#fff', fontSize: 17, fontWeight: '700', flex: 1 },
  addBtn: { padding: 4 },
  tabs: { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#E5E7EB' },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabActive: { borderBottomWidth: 2, borderBottomColor: '#3B82F6' },
  tabText: { fontSize: 14, color: '#6B7280' },
  tabTextActive: { color: '#3B82F6', fontWeight: '600' },
  scroll: { flex: 1, padding: 12 },
  filters: { marginBottom: 12 },
  filterBtn: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 16, marginRight: 8, backgroundColor: '#F3F4F6' },
  filterBtnActive: { backgroundColor: '#3B82F6' },
  filterText: { fontSize: 13, color: '#6B7280', fontWeight: '500' },
  filterTextActive: { color: '#fff' },
  urgenteSection: { backgroundColor: '#FFF7ED', borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: '#FED7AA' },
  urgentHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
  urgentTitle: { fontSize: 14, fontWeight: '700', color: '#C2410C' },
  urgentItem: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 8, padding: 10, marginBottom: 6 },
  urgentItemTitle: { fontSize: 13, fontWeight: '600', color: '#374151' },
  retardText: { fontSize: 12, color: '#EF4444', fontWeight: '700' },
  urgentJours: { fontSize: 12, color: '#F97316', fontWeight: '600' },
  doneBtn: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: '#D1FAE5', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 },
  doneBtnText: { fontSize: 12, color: '#10B981', fontWeight: '600' },
  tacheCard: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#E5E7EB' },
  checkbox: { width: 22, height: 22, borderRadius: 6, borderWidth: 2, borderColor: '#D1D5DB', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 1 },
  checkboxDone: { backgroundColor: '#10B981', borderColor: '#10B981' },
  tacheHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 4 },
  tacheTitre: { flex: 1, fontSize: 14, fontWeight: '600', color: '#1F2937', lineHeight: 20 },
  tacheTitreTerminee: { color: '#9CA3AF', textDecorationLine: 'line-through' },
  prioBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, flexShrink: 0 },
  prioText: { fontSize: 11, fontWeight: '700' },
  echeanceText: { fontSize: 12, color: '#6B7280', marginBottom: 2 },
  liaisonText: { fontSize: 11, color: '#3B82F6', marginBottom: 2 },
  progressRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  progressBar: { flex: 1, height: 4, backgroundColor: '#E5E7EB', borderRadius: 2 },
  progressFill: { height: 4, backgroundColor: '#3B82F6', borderRadius: 2 },
  progressText: { fontSize: 11, color: '#6B7280', width: 30, textAlign: 'right' },
  statutBadge: { flexDirection: 'row', alignItems: 'center', gap: 5, flexShrink: 0 },
  statutDot: { width: 7, height: 7, borderRadius: 4 },
  statutText: { fontSize: 11, fontWeight: '600' },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyText: { marginTop: 12, fontSize: 14, color: '#9CA3AF' },
  resumeCard: { backgroundColor: '#1E3A8A', borderRadius: 16, padding: 18, marginBottom: 16 },
  resumeTitle: { color: '#BFDBFE', fontSize: 13, fontWeight: '600', marginBottom: 8 },
  resumeBody: { color: '#E0EDFF', fontSize: 14, lineHeight: 22 },
  sectionCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: '#E5E7EB' },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: '#1F2937', marginBottom: 10 },
  evtItem: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: '#F3F4F6' },
  evtBar: { width: 3, height: 32, backgroundColor: '#3B82F6', borderRadius: 2 },
  evtTitre: { fontSize: 14, fontWeight: '500', color: '#374151' },
  evtHeure: { fontSize: 12, color: '#6B7280' },
  tacheResumeItem: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6 },
  prioDot: { width: 8, height: 8, borderRadius: 4, flexShrink: 0 },
  tacheResumeText: { fontSize: 14, color: '#374151', flex: 1 },
  modal: { flex: 1, backgroundColor: '#F9FAFB' },
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: '#E5E7EB', backgroundColor: '#fff' },
  modalTitle: { fontSize: 18, fontWeight: '700', color: '#1F2937' },
  modalBody: { flex: 1, padding: 16 },
  inputLabel: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 6, marginTop: 12 },
  input: { borderWidth: 1, borderColor: '#D1D5DB', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, backgroundColor: '#fff', marginBottom: 4 },
  prioRow: { flexDirection: 'row', gap: 8, marginBottom: 4 },
  prioBtn: { flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: 10, borderWidth: 1.5, borderColor: '#E5E7EB', backgroundColor: '#fff' },
  prioBtnText: { fontSize: 13, fontWeight: '600', color: '#374151' },
  saveBtn: { backgroundColor: '#3B82F6', padding: 16, borderRadius: 12, alignItems: 'center', marginTop: 24, marginBottom: 40 },
  saveBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
