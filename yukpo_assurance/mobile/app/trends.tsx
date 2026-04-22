import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';

const REGIONS = ['CM', 'SN', 'CI', 'NG', 'ALL'];
const PERIODES = ['24h', '7d', '30d'];

export default function TrendsScreen() {
  const [tab, setTab] = useState<'pulse' | 'veille'>('pulse');
  const [region, setRegion] = useState('CM');
  const [periode, setPeriode] = useState('24h');
  const [pulse, setPulse] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [veille, setVeille] = useState<any[]>([]);
  const [selectedTrend, setSelectedTrend] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

  const token = async () => AsyncStorage.getItem('token');

  const chargerPulse = async () => {
    setLoading(true);
    try {
      const t = await token();
      const res = await fetch(`/api/v1/trends/pulse?region=${region}&periode=${periode}`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      const data = await res.json();
      setPulse(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); setRefreshing(false); }
  };

  const chargerVeille = async () => {
    const t = await token();
    const res = await fetch('/api/v1/trends/veille-reglementaire', {
      headers: { Authorization: `Bearer ${t}` },
    });
    const data = await res.json();
    setVeille(data.elements || []);
  };

  useEffect(() => {
    if (tab === 'pulse') chargerPulse();
    if (tab === 'veille') chargerVeille();
  }, [tab, region, periode]);

  const onRefresh = () => { setRefreshing(true); if (tab === 'pulse') chargerPulse(); else chargerVeille(); };

  const ScorePill = ({ score, label, color }: { score: number; label: string; color: string }) => (
    <View style={[styles.scorePill, { backgroundColor: color + '20' }]}>
      <Text style={[styles.scoreLabel, { color }]}>{label}</Text>
      <Text style={[styles.scoreValue, { color }]}>{score.toFixed(0)}</Text>
    </View>
  );

  const impactColor: Record<string, string> = {
    critique: '#EF4444', élevé: '#F97316', moyen: '#F59E0B', faible: '#6B7280',
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="pulse-outline" size={22} color="#fff" />
        <Text style={styles.headerTitle}>Veille & Tendances</Text>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        {[{ k: 'pulse', l: 'Tendances' }, { k: 'veille', l: 'Réglementaire' }].map(({ k, l }) => (
          <TouchableOpacity key={k} style={[styles.tab, tab === k && styles.tabActive]}
            onPress={() => setTab(k as any)}>
            <Text style={[styles.tabText, tab === k && styles.tabTextActive]}>{l}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'pulse' && (
        <>
          {/* Filtres */}
          <View style={styles.filtersRow}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {REGIONS.map(r => (
                <TouchableOpacity key={r} style={[styles.filterBtn, region === r && styles.filterBtnActive]} onPress={() => setRegion(r)}>
                  <Text style={[styles.filterText, region === r && styles.filterTextActive]}>{r}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <View style={styles.sep} />
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {PERIODES.map(p => (
                <TouchableOpacity key={p} style={[styles.filterBtn, periode === p && styles.filterBtnActive]} onPress={() => setPeriode(p)}>
                  <Text style={[styles.filterText, periode === p && styles.filterTextActive]}>{p}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          <ScrollView style={styles.scroll} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
            {/* Résumé */}
            {pulse?.resume_executif && (
              <View style={styles.resumeBox}>
                <Text style={styles.resumeText}>{pulse.resume_executif}</Text>
                {pulse.tendances_en_hausse?.length > 0 && (
                  <View style={styles.hausseTags}>
                    <Text style={styles.hausseLabel}>🔥 En hausse :</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                      {pulse.tendances_en_hausse.map((t: string, i: number) => (
                        <View key={i} style={styles.hausseTag}><Text style={styles.hausseTagText}>{t}</Text></View>
                      ))}
                    </ScrollView>
                  </View>
                )}
              </View>
            )}

            {loading ? (
              <ActivityIndicator color="#3B82F6" size="large" style={{ marginTop: 40 }} />
            ) : (
              (pulse?.tendances || []).map((t: any, i: number) => (
                <TouchableOpacity key={i} style={styles.trendCard}
                  onPress={() => setSelectedTrend(selectedTrend?.sujet === t.sujet ? null : t)}>
                  <View style={styles.trendHeader}>
                    <Text style={styles.trendSujet} numberOfLines={2}>{t.sujet}</Text>
                    <Text style={[styles.momentum, { color: t.momentum_pct > 0 ? '#10B981' : '#EF4444' }]}>
                      {t.momentum_pct > 0 ? '↑' : '↓'} {Math.abs(t.momentum_pct).toFixed(1)}%
                    </Text>
                  </View>
                  <View style={styles.scoresRow}>
                    <ScorePill score={t.score_opportunite} label="Opp" color={t.score_opportunite >= 80 ? '#10B981' : t.score_opportunite >= 60 ? '#F59E0B' : '#6B7280'} />
                    <ScorePill score={t.score_social} label="Social" color="#3B82F6" />
                    <ScorePill score={t.score_commerce} label="Commerce" color="#8B5CF6" />
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                    {t.categories?.slice(0, 3).map((c: string, j: number) => (
                      <View key={j} style={styles.categoryTag}><Text style={styles.categoryText}>{c}</Text></View>
                    ))}
                  </ScrollView>

                  {selectedTrend?.sujet === t.sujet && (
                    <View style={styles.expandedSection}>
                      <Text style={styles.resumeContent}>{t.resume}</Text>
                      {t.recommandations?.length > 0 && (
                        <>
                          <Text style={styles.recommTitle}>Actions recommandées :</Text>
                          {t.recommandations.map((r: string, j: number) => (
                            <View key={j} style={styles.recommItem}>
                              <Ionicons name="chevron-forward" size={14} color="#3B82F6" />
                              <Text style={styles.recommText}>{r}</Text>
                            </View>
                          ))}
                        </>
                      )}
                    </View>
                  )}
                </TouchableOpacity>
              ))
            )}
          </ScrollView>
        </>
      )}

      {tab === 'veille' && (
        <ScrollView style={styles.scroll} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
          {veille.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="book-outline" size={40} color="#D1D5DB" />
              <Text style={styles.emptyText}>Aucune actualité réglementaire</Text>
            </View>
          ) : veille.map((v: any, i: number) => (
            <View key={i} style={styles.veilleCard}>
              <View style={styles.veilleHeader}>
                <Text style={styles.veilleTitle} numberOfLines={2}>{v.titre}</Text>
                <View style={[styles.impactBadge, { backgroundColor: (impactColor[v.impact] || '#6B7280') + '20' }]}>
                  <Text style={[styles.impactText, { color: impactColor[v.impact] || '#6B7280' }]}>{v.impact}</Text>
                </View>
              </View>
              <Text style={styles.veilleDate}>{v.date}</Text>
              <Text style={styles.veilleResume}>{v.resume}</Text>
              {v.action_requise && (
                <View style={styles.actionBox}>
                  <Ionicons name="warning-outline" size={14} color="#F59E0B" />
                  <Text style={styles.actionText}>{v.action_requise}</Text>
                </View>
              )}
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F9FAFB' },
  header: { backgroundColor: '#1E3A8A', flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 14 },
  headerTitle: { color: '#fff', fontSize: 17, fontWeight: '700' },
  tabs: { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#E5E7EB' },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabActive: { borderBottomWidth: 2, borderBottomColor: '#3B82F6' },
  tabText: { fontSize: 14, color: '#6B7280' },
  tabTextActive: { color: '#3B82F6', fontWeight: '600' },
  filtersRow: { backgroundColor: '#fff', paddingVertical: 8, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: '#F3F4F6', flexDirection: 'row', alignItems: 'center' },
  filterBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, marginRight: 6, backgroundColor: '#F3F4F6' },
  filterBtnActive: { backgroundColor: '#3B82F6' },
  filterText: { fontSize: 13, color: '#6B7280', fontWeight: '500' },
  filterTextActive: { color: '#fff' },
  sep: { width: 1, height: 20, backgroundColor: '#E5E7EB', marginHorizontal: 8 },
  scroll: { flex: 1, padding: 12 },
  resumeBox: { backgroundColor: '#EFF6FF', borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: '#BFDBFE' },
  resumeText: { fontSize: 13, color: '#1E40AF', lineHeight: 20 },
  hausseTags: { marginTop: 8, flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6 },
  hausseLabel: { fontSize: 12, color: '#3B82F6', fontWeight: '600' },
  hausseTag: { backgroundColor: '#DBEAFE', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
  hausseTagText: { fontSize: 12, color: '#1D4ED8' },
  trendCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: '#E5E7EB' },
  trendHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10, gap: 8 },
  trendSujet: { flex: 1, fontSize: 14, fontWeight: '600', color: '#1F2937', lineHeight: 20 },
  momentum: { fontSize: 13, fontWeight: '700' },
  scoresRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  scorePill: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  scoreLabel: { fontSize: 11, fontWeight: '600' },
  scoreValue: { fontSize: 13, fontWeight: '700' },
  categoryTag: { backgroundColor: '#F3F4F6', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 8, marginRight: 6 },
  categoryText: { fontSize: 11, color: '#6B7280' },
  expandedSection: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#F3F4F6' },
  resumeContent: { fontSize: 13, color: '#374151', lineHeight: 20, marginBottom: 10 },
  recommTitle: { fontSize: 12, fontWeight: '700', color: '#374151', marginBottom: 6 },
  recommItem: { flexDirection: 'row', alignItems: 'flex-start', gap: 4, marginBottom: 4 },
  recommText: { flex: 1, fontSize: 12, color: '#6B7280', lineHeight: 18 },
  veilleCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: '#E5E7EB' },
  veilleHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 4 },
  veilleTitle: { flex: 1, fontSize: 14, fontWeight: '600', color: '#1F2937', lineHeight: 20 },
  veilleDate: { fontSize: 12, color: '#9CA3AF', marginBottom: 8 },
  veilleResume: { fontSize: 13, color: '#374151', lineHeight: 20, marginBottom: 10 },
  impactBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, flexShrink: 0 },
  impactText: { fontSize: 11, fontWeight: '700' },
  actionBox: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, backgroundColor: '#FFFBEB', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#FDE68A' },
  actionText: { flex: 1, fontSize: 12, color: '#92400E', lineHeight: 18 },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyText: { marginTop: 12, fontSize: 14, color: '#9CA3AF', textAlign: 'center' },
});
