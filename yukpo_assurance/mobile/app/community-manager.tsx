import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';

const PLATEFORMES = ['facebook', 'instagram', 'linkedin', 'whatsapp', 'twitter'];
const PLAT_COLORS: Record<string, string> = {
  facebook: '#1877F2', instagram: '#E4405F', linkedin: '#0A66C2',
  whatsapp: '#25D366', twitter: '#1DA1F2',
};
const PLAT_ICONS: Record<string, string> = {
  facebook: 'logo-facebook', instagram: 'logo-instagram', linkedin: 'logo-linkedin',
  whatsapp: 'logo-whatsapp', twitter: 'logo-twitter',
};
const TYPES = ['actualite', 'produit', 'conseil', 'promo', 'campagne'];

export default function CommunityManagerScreen() {
  const [tab, setTab] = useState<'generer' | 'posts'>('generer');
  const [plateforme, setPlateforme] = useState('facebook');
  const [typeContenu, setTypeContenu] = useState('actualite');
  const [sujet, setSujet] = useState('');
  const [trend, setTrend] = useState('');
  const [generating, setGenerating] = useState(false);
  const [postGenere, setPostGenere] = useState<any>(null);
  const [posts, setPosts] = useState<any[]>([]);
  const [loadingPosts, setLoadingPosts] = useState(false);

  const generer = async () => {
    if (!sujet.trim()) { Alert.alert('Sujet requis', 'Veuillez saisir un sujet'); return; }
    setGenerating(true);
    try {
      const token = await AsyncStorage.getItem('token');
      const res = await fetch('/api/v1/community-manager/generer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ sujet, plateforme, type_contenu: typeContenu, ton: 'professionnel', inject_trend: trend || undefined }),
      });
      const data = await res.json();
      setPostGenere(data);
    } catch (e) { Alert.alert('Erreur', 'Génération impossible'); }
    finally { setGenerating(false); }
  };

  const chargerPosts = async () => {
    setLoadingPosts(true);
    const token = await AsyncStorage.getItem('token');
    const res = await fetch('/api/v1/community-manager/posts?limit=20', {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    setPosts(Array.isArray(data) ? data : []);
    setLoadingPosts(false);
  };

  const changerStatut = async (id: number, statut: string) => {
    const token = await AsyncStorage.getItem('token');
    await fetch(`/api/v1/community-manager/posts/${id}/statut`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ statut }),
    });
    chargerPosts();
  };

  const statutColor: Record<string, string> = {
    brouillon: '#6B7280', planifie: '#3B82F6', publie: '#10B981', echoue: '#EF4444',
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Ionicons name="megaphone-outline" size={22} color="#fff" />
        <Text style={styles.headerTitle}>Community Manager IA</Text>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        {[{ k: 'generer', l: 'Générer' }, { k: 'posts', l: 'Posts' }].map(({ k, l }) => (
          <TouchableOpacity key={k} style={[styles.tab, tab === k && styles.tabActive]}
            onPress={() => { setTab(k as any); if (k === 'posts') chargerPosts(); }}>
            <Text style={[styles.tabText, tab === k && styles.tabTextActive]}>{l}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'generer' && (
        <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: 32 }}>
          {/* Plateformes */}
          <Text style={styles.sectionLabel}>Plateforme</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
            {PLATEFORMES.map(p => (
              <TouchableOpacity key={p} onPress={() => setPlateforme(p)}
                style={[styles.platBtn, plateforme === p && { backgroundColor: PLAT_COLORS[p], borderColor: PLAT_COLORS[p] }]}>
                <Ionicons name={PLAT_ICONS[p] as any} size={18} color={plateforme === p ? '#fff' : PLAT_COLORS[p]} />
                <Text style={[styles.platText, plateforme === p && { color: '#fff' }]}>{p}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {/* Type */}
          <Text style={styles.sectionLabel}>Type de contenu</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
            {TYPES.map(t => (
              <TouchableOpacity key={t} onPress={() => setTypeContenu(t)}
                style={[styles.typeBtn, typeContenu === t && styles.typeBtnActive]}>
                <Text style={[styles.typeBtnText, typeContenu === t && styles.typeBtnTextActive]}>{t}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {/* Sujet */}
          <Text style={styles.sectionLabel}>Sujet *</Text>
          <TextInput
            style={styles.input}
            value={sujet}
            onChangeText={setSujet}
            placeholder="Ex: Assurance auto — offre spéciale..."
            multiline
          />

          {/* Tendance */}
          <Text style={styles.sectionLabel}>Tendance à injecter (optionnel)</Text>
          <TextInput
            style={styles.input}
            value={trend}
            onChangeText={setTrend}
            placeholder="Ex: Saison des pluies..."
          />

          <TouchableOpacity style={[styles.genBtn, generating && styles.genBtnDisabled]} onPress={generer} disabled={generating}>
            {generating ? <ActivityIndicator color="#fff" /> : <Ionicons name="send" size={18} color="#fff" />}
            <Text style={styles.genBtnText}>{generating ? 'Génération en cours…' : 'Générer avec l\'IA'}</Text>
          </TouchableOpacity>

          {/* Résultat */}
          {postGenere && (
            <View style={styles.resultCard}>
              <View style={styles.resultHeader}>
                <Ionicons name={PLAT_ICONS[postGenere.plateforme] as any} size={18} color={PLAT_COLORS[postGenere.plateforme] || '#3B82F6'} />
                <Text style={styles.resultPlatLabel}>{postGenere.plateforme}</Text>
                <View style={[styles.statutBadge, { backgroundColor: (statutColor[postGenere.statut] || '#6B7280') + '20' }]}>
                  <Text style={[styles.statutText, { color: statutColor[postGenere.statut] || '#6B7280' }]}>{postGenere.statut}</Text>
                </View>
              </View>
              <Text style={styles.legendeText}>{postGenere.legende}</Text>
              {postGenere.hashtags?.length > 0 && (
                <Text style={styles.hashtagsText}>{postGenere.hashtags.join(' ')}</Text>
              )}
              {postGenere.legende_variante_b && (
                <>
                  <Text style={styles.variantLabel}>Version B (A/B test)</Text>
                  <Text style={[styles.legendeText, { backgroundColor: '#EFF6FF' }]}>{postGenere.legende_variante_b}</Text>
                </>
              )}
              <View style={styles.actionRow}>
                <TouchableOpacity style={[styles.actionBtn, { backgroundColor: '#3B82F6' }]}
                  onPress={() => changerStatut(postGenere.id, 'planifie')}>
                  <Text style={styles.actionBtnText}>Planifier</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.actionBtn, { backgroundColor: '#10B981' }]}
                  onPress={() => changerStatut(postGenere.id, 'publie')}>
                  <Text style={styles.actionBtnText}>Marquer publié</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>
      )}

      {tab === 'posts' && (
        <ScrollView style={styles.scroll}>
          {loadingPosts ? (
            <ActivityIndicator color="#3B82F6" style={{ marginTop: 40 }} />
          ) : posts.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="create-outline" size={40} color="#D1D5DB" />
              <Text style={styles.emptyText}>Aucun post — générez votre premier contenu</Text>
            </View>
          ) : posts.map(p => (
            <View key={p.id} style={styles.postCard}>
              <View style={styles.postCardHeader}>
                <Ionicons name={PLAT_ICONS[p.plateforme] as any || 'globe-outline'} size={18} color={PLAT_COLORS[p.plateforme] || '#6B7280'} />
                <Text style={styles.postPlatText}>{p.plateforme}</Text>
                <Text style={styles.postTypeText}>{p.type_contenu}</Text>
                <View style={[styles.statutBadge, { backgroundColor: (statutColor[p.statut] || '#6B7280') + '20', marginLeft: 'auto' }]}>
                  <Text style={[styles.statutText, { color: statutColor[p.statut] || '#6B7280' }]}>{p.statut}</Text>
                </View>
              </View>
              <Text style={styles.postLegende} numberOfLines={3}>{p.legende}</Text>
              {p.hashtags?.length > 0 && (
                <Text style={styles.hashtagsText} numberOfLines={1}>{p.hashtags.slice(0, 4).join(' ')}</Text>
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
  scroll: { flex: 1, padding: 16 },
  sectionLabel: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 8 },
  platBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 20, borderWidth: 1.5, borderColor: '#E5E7EB', marginRight: 8, backgroundColor: '#fff' },
  platText: { fontSize: 13, fontWeight: '500', color: '#374151' },
  typeBtn: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, borderWidth: 1.5, borderColor: '#E5E7EB', marginRight: 8, backgroundColor: '#fff' },
  typeBtnActive: { backgroundColor: '#3B82F6', borderColor: '#3B82F6' },
  typeBtnText: { fontSize: 13, color: '#374151' },
  typeBtnTextActive: { color: '#fff', fontWeight: '600' },
  input: { borderWidth: 1, borderColor: '#D1D5DB', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, backgroundColor: '#fff', marginBottom: 16, minHeight: 48 },
  genBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#3B82F6', padding: 16, borderRadius: 12, marginBottom: 20 },
  genBtnDisabled: { opacity: 0.6 },
  genBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  resultCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, borderWidth: 1, borderColor: '#E5E7EB', marginBottom: 16 },
  resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 },
  resultPlatLabel: { fontSize: 14, fontWeight: '600', color: '#374151', flex: 1 },
  legendeText: { fontSize: 14, color: '#1F2937', backgroundColor: '#F9FAFB', padding: 12, borderRadius: 8, lineHeight: 22, marginBottom: 10 },
  hashtagsText: { fontSize: 12, color: '#3B82F6', marginBottom: 8 },
  variantLabel: { fontSize: 12, fontWeight: '600', color: '#6B7280', marginBottom: 6 },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: 4 },
  actionBtn: { flex: 1, padding: 12, borderRadius: 8, alignItems: 'center' },
  actionBtnText: { color: '#fff', fontWeight: '600', fontSize: 13 },
  postCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#E5E7EB', marginBottom: 10 },
  postCardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  postPlatText: { fontSize: 13, fontWeight: '600', color: '#374151' },
  postTypeText: { fontSize: 11, color: '#9CA3AF', backgroundColor: '#F3F4F6', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  postLegende: { fontSize: 13, color: '#374151', lineHeight: 20, marginBottom: 6 },
  statutBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 },
  statutText: { fontSize: 11, fontWeight: '600' },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyText: { marginTop: 12, fontSize: 14, color: '#9CA3AF', textAlign: 'center' },
});
