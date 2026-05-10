import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || '/api/v1/bureau'

const api = axios.create({
  baseURL: BASE,
  timeout: 30_000,  // 30s par défaut pour éviter "page qui tourne indéfiniment"
                    // (les routes longues redéfinissent leur timeout localement)
})

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('bureau_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('bureau_token')
      window.location.href = '/login'
    }
    if (err.response?.status === 402) {
      const detail = err.response?.data?.detail
      const msg = typeof detail === 'object' ? detail?.message : (typeof detail === 'string' && detail.startsWith('CREDITS_EPUISES') ? 'Crédits épuisés — rechargez ou changez de plan.' : detail)
      import('react-hot-toast').then(({ default: toast }) => {
        toast.error(msg || 'Crédits épuisés', {
          duration: 6000,
          icon: '💳',
        })
        setTimeout(() => { window.location.href = '/abonnement' }, 2000)
      })
    }
    return Promise.reject(err)
  },
)

// ─── Auth (partagée avec YukpoPro) ────────────────────────────────────────────
const authApi = axios.create({
  baseURL: import.meta.env.VITE_API_URL?.replace('/bureau', '') || '/api/v1',
  timeout: 15_000,
})
authApi.interceptors.request.use(cfg => {
  const token = localStorage.getItem('bureau_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

export const authAPI = {
  login: (email: string, password: string) =>
    authApi.post('/auth/token', { username: email, password }, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }),
  me: () => authApi.get('/auth/me'),
  updateProfile: (data: { nom?: string; prenoms?: string; telephone?: string }) =>
    authApi.patch('/auth/profile', data),
}

// ─── Organisations (plan Entreprise — partagées avec YukpoPro) ───────────────
export interface Organisation {
  id: number
  nom: string
  slug: string
  owner_id: number
  plan: string
  prix_par_siege_fcfa: number
  devise: string
  max_seats: number | null
  statut: string
  domain_auto_join: string | null
  domain_verifie: boolean
  pays: string | null
  secteur: string | null
  settings: Record<string, unknown>
  cree_le: string
  mon_role?: 'owner' | 'admin' | 'member'
}

export interface OrgMembre {
  id: number
  org_id: number
  user_id: number
  role: 'owner' | 'admin' | 'member'
  statut: string
  joined_at: string
  last_active_at: string
  email: string
  nom: string
  username: string
}

export interface OrgInvite {
  id: number
  org_id: number
  email: string
  role: 'admin' | 'member'
  statut: string
  invite_par: number
  expires_at: string
  cree_le: string
  accepte_le: string | null
  token?: string
  lien_acceptation?: string
}

export interface OrgFacture {
  id: number
  org_id: number
  period_debut: string
  period_fin: string
  sieges_max: number
  sieges_factures: number
  prix_unitaire_fcfa: number
  montant_total_fcfa: number
  devise: string
  statut: string
  transaction_ref: string | null
  paye_le: string | null
}

export const orgsAPI = {
  monOrg: async (): Promise<Organisation | null> => {
    try {
      const r = await authApi.get('/pro/orgs/me')
      return r.data as Organisation
    } catch (err: unknown) {
      const e = err as { response?: { status?: number } }
      if (e?.response?.status === 404) return null
      throw err
    }
  },
  creer: (payload: {
    nom: string; pays?: string; secteur?: string;
    prix_par_siege_fcfa?: number; devise?: string;
    max_seats?: number | null; domain_auto_join?: string;
  }) => authApi.post('/pro/orgs', payload).then(r => r.data as Organisation),
  update: (orgId: number, payload: Partial<Organisation>) =>
    authApi.patch(`/pro/orgs/${orgId}`, payload).then(r => r.data as Organisation),
  membres: (orgId: number) =>
    authApi.get(`/pro/orgs/${orgId}/members`).then(r => r.data as { membres: OrgMembre[]; mon_role: string }),
  changerRole: (orgId: number, userId: number, role: 'admin' | 'member') =>
    authApi.patch(`/pro/orgs/${orgId}/members/${userId}`, { role }).then(r => r.data),
  retirerMembre: (orgId: number, userId: number) =>
    authApi.delete(`/pro/orgs/${orgId}/members/${userId}`).then(r => r.data),
  quitter: (orgId: number) =>
    authApi.post(`/pro/orgs/${orgId}/leave`).then(r => r.data),
  invitations: (orgId: number) =>
    authApi.get(`/pro/orgs/${orgId}/invites`).then(r => r.data as { invitations: OrgInvite[] }),
  inviter: (orgId: number, email: string, role: 'admin' | 'member' = 'member') =>
    authApi.post(`/pro/orgs/${orgId}/invites`, { email, role }).then(r => r.data as OrgInvite),
  revoquerInvite: (orgId: number, inviteId: number) =>
    authApi.delete(`/pro/orgs/${orgId}/invites/${inviteId}`).then(r => r.data),
  detailInvite: (token: string) =>
    authApi.get(`/pro/orgs/invites/${token}`).then(r => r.data as { invitation: OrgInvite; organisation: Partial<Organisation> & { nom: string } }),
  accepterInvite: (token: string) =>
    authApi.post(`/pro/orgs/invites/${token}/accept`).then(r => r.data as { message: string; org_id: number; role: string }),
  factures: (orgId: number) =>
    authApi.get(`/pro/orgs/${orgId}/billing`).then(r => r.data as { factures: OrgFacture[] }),
}

// ─── Rédaction ────────────────────────────────────────────────────────────────
export const redactionAPI = {
  types: () => api.get('/redaction/types'),
  generer: (data: Record<string, unknown>) => api.post('/redaction/generer', data),
  reformuler: (data: { texte: string; registre: string; pays: string }) => api.post('/redaction/reformuler', data),
  calculerPrix: (type_doc: string, nb_mots_estime: number) =>
    api.post('/redaction/calculer-prix', { type_doc, nb_mots_estime }),
  telecharger: (fichier_id: string) =>
    api.get(`/redaction/fichier/${fichier_id}`, { responseType: 'blob' }),
}

// ─── OCR ──────────────────────────────────────────────────────────────────────
export const ocrAPI = {
  scanner: (formData: FormData) =>
    api.post('/ocr/scanner', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  manuscrit: (formData: FormData) =>
    api.post('/ocr/manuscrit', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  telecharger: (fichier_id: string) =>
    api.get(`/ocr/fichier/${fichier_id}`, { responseType: 'blob' }),
}

// ─── Audio ────────────────────────────────────────────────────────────────────
export const audioAPI = {
  types: () => api.get('/audio/types'),
  transcrire: (formData: FormData) =>
    api.post('/audio/transcrire', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    }),
  telecharger: (fichier_id: string) =>
    api.get(`/audio/fichier/${fichier_id}`, { responseType: 'blob' }),
}

// ─── Infographie ──────────────────────────────────────────────────────────────
export interface ProfilInfographie {
  metier?: string;
  secteur?: string;
  nom_organisation?: string;
  audience?: string;
  ton?: string;
  couleur_primaire_hex?: string;
  couleurs_accents_hex?: string[];
}

export const infographieAPI = {
  gabarits: () => api.get('/infographie/gabarits'),
  generer: (data: {
    brief: string;
    type_gabarit: string;
    pays?: string;
    profil?: ProfilInfographie;
    export_cmyk?: boolean;
    export_svg?: boolean;
    dpi_preview?: number;
  }) => api.post('/infographie/generer', data, { timeout: 180_000 }),
  genererVariantes: (data: {
    brief: string;
    type_gabarit: string;
    pays?: string;
    profil?: ProfilInfographie;
    nombre?: number;
  }) => api.post('/infographie/generer-variantes', data, { timeout: 240_000 }),
  genererManuel: (data: Record<string, unknown>) =>
    api.post('/infographie/generer-manuel', data, { timeout: 180_000 }),
  genererDepuisModele: (formData: FormData) =>
    api.post('/infographie/generer-depuis-modele', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180_000,
    }),
  genererCustom: (data: {
    width_mm: number;
    height_mm: number;
    bleed_mm?: number;
    brief: string;
    pays?: string;
    profil?: ProfilInfographie;
    export_cmyk?: boolean;
    export_svg?: boolean;
  }) => api.post('/infographie/generer-custom', data, { timeout: 180_000 }),
  telecharger: (fichier_id: string) =>
    api.get(`/infographie/fichier/${fichier_id}`, { responseType: 'blob' }),
  modifier: (data: { fichier_id: string; instructions: string; pays?: string }) =>
    api.post('/infographie/modifier', data, { timeout: 180_000 }),
}

// ─── Infographie Pro (multi-page IA + médiathèque) ────────────────────────────
export const infographieProAPI = {
  projets: () => api.get('/bureau/infographie-pro/projets'),
  uploadMedia: (formData: FormData) =>
    api.post('/bureau/infographie-pro/medias', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000,
    }),
  listerMedias: (params: { portee: 'session' | 'compte'; categorie?: string; session_id?: string }) =>
    api.get('/bureau/infographie-pro/medias', { params }),
  supprimerMedia: (media_id: string, portee: 'session' | 'compte', session_id?: string) =>
    api.delete(`/bureau/infographie-pro/medias/${media_id}`, { params: { portee, session_id } }),
  generer: (data: {
    cle_projet: string; brief: string; pays?: string; langue?: string;
    profil?: ProfilInfographie; medias_refs?: string[]; export_cmyk?: boolean;
    directives_visuelles?: Record<string, number>;
  }) => api.post('/bureau/infographie-pro/generer', data, { timeout: 360_000 }),
  genererAuto: (data: {
    brief: string; pays?: string; langue?: string;
    profil?: ProfilInfographie; medias_refs?: string[];
    cle_projet_hint?: string; export_cmyk?: boolean;
    directives_visuelles?: Record<string, number>;
  }) => api.post('/bureau/infographie-pro/generer-auto', data, { timeout: 360_000 }),
  modifier: (data: {
    projet_id: string; instructions: string;
    medias_refs_supplementaires?: string[]; pays?: string;
    directives_visuelles?: Record<string, number>;
  }) => api.post('/bureau/infographie-pro/modifier', data, { timeout: 360_000 }),
  // Sprint 1.7 — Auto-orchestrateur LLM : 1 prompt → analyse complète
  orchestrer: (data: {
    prompt: string; pays?: string; langue?: string;
    profil?: ProfilInfographie;
  }) => api.post('/bureau/infographie-pro/orchestrer', data, { timeout: 60_000 }),
  // Sprint UX4 — Devis automatique avant génération
  devis: (data: {
    brief: string; pays?: string; langue?: string;
    medias_refs?: string[]; cle_projet?: string;
  }) => api.post('/bureau/infographie-pro/devis', data, { timeout: 60_000 }),
  // Sprint UX3 — Bulk CSV/XLSX
  bulkAnalyser: (formData: FormData) =>
    api.post('/bureau/infographie-pro/bulk/analyser', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60_000,
    }),
  bulkLancer: (data: {
    rows: any[]; template_brief: string; mapping: Record<string, string>;
    cle_projet: string; mode_visuel?: string; pays?: string; langue?: string;
    accepter_cout: boolean;
  }) => api.post('/bureau/infographie-pro/bulk/lancer', data, { timeout: 600_000 }),
  // Sprint 1.6 — Brand LoRA
  brandLoraList: () => api.get('/bureau/infographie-pro/brand-lora'),
  brandLoraTrain: (data: {
    label: string; trigger_word: string; description?: string;
    images_refs: string[]; accepter_cout: boolean;
  }) => api.post('/bureau/infographie-pro/brand-lora/entrainer', data, { timeout: 60_000 }),
  brandLoraDelete: (lora_id: string) =>
    api.delete(`/bureau/infographie-pro/brand-lora/${lora_id}`),
}

// ─── Traduction ───────────────────────────────────────────────────────────────
export const traductionAPI = {
  traduireTexte: (data: { contenu: string; langue_source: string; langue_cible: string; contexte_metier?: string; format_sortie?: string }) =>
    api.post('/traduction/texte', data),
  traduireFichier: (formData: FormData) =>
    api.post('/traduction/fichier', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 }),
  telecharger: (fichier_id: string) =>
    api.get(`/traduction/fichier/${fichier_id}`, { responseType: 'blob' }),
}

// ─── Abonnement & Crédits ─────────────────────────────────────────────────────
export const abonnementAPI = {
  plans: () => api.get('/abonnement/plans'),
  monAbonnement: () => api.get('/abonnement/'),
  initier: (data: { plan: string; operateur: string; numero_telephone: string; pays?: string }) =>
    api.post('/abonnement/initier', data),
  confirmer: (data: { reference_paiement: string; transaction_id?: string }) =>
    api.post('/abonnement/confirmer', data),
  packsCredits: () => api.get('/abonnement/packs-credits'),
  initierRecharge: (data: { pack_id: string; operateur: string; numero_telephone: string; pays?: string }) =>
    api.post('/abonnement/initier-recharge', data),
  initierRechargeCustom: (data: { montant_fcfa: number; operateur: string; numero_telephone: string; pays?: string }) =>
    api.post('/abonnement/initier-recharge-custom', data),
  wallet: (jours: number = 30) =>
    api.get('/abonnement/wallet', { params: { jours } }),
  confirmerRecharge: (data: { reference_paiement: string; transaction_id?: string }) =>
    api.post('/abonnement/confirmer-recharge', data),
  historique: () => api.get('/abonnement/historique'),
}

// ─── Admin Secrétariat ─────────────────────────────────────────────────────────
export const adminAPI = {
  utilisateurs: (params?: { recherche?: string; page?: number; par_page?: number; actifs_seulement?: boolean }) =>
    api.get('/admin/utilisateurs', { params }),
  detailsUtilisateur: (user_id: number) =>
    api.get(`/admin/utilisateurs/${user_id}`),
  ajouterCredits: (user_id: number, credits: number, raison?: string) =>
    api.post(`/admin/utilisateurs/${user_id}/credits-bonus`, { credits, raison }),
  bloquer: (user_id: number, jours: number = 7) =>
    api.post(`/admin/utilisateurs/${user_id}/bloquer`, null, { params: { jours } }),
  debloquer: (user_id: number) =>
    api.post(`/admin/utilisateurs/${user_id}/debloquer`),
  stats: () => api.get('/admin/stats'),
  statsRevenus: (params?: { date_debut?: string; date_fin?: string }) =>
    api.get('/admin/stats/revenus', { params }),
  lancerPromotion: (data: {
    montant: number; cible: 'tous' | 'ids' | 'consommation' | 'role';
    user_ids?: number[]; role?: string;
    seuil_credits_min?: number; seuil_credits_max?: number; seuil_appels_min?: number;
    periode_jours?: number; motif?: string;
  }) => api.post('/admin/promotion', data),
}

// ─── Mes Documents ────────────────────────────────────────────────────────────
export const documentsAPI = {
  lister: () => api.get('/documents/'),
  telecharger: (fichier_id: string) =>
    api.get(`/documents/${fichier_id}`, { responseType: 'blob' }),
  supprimer: (fichier_id: string) =>
    api.delete(`/documents/${fichier_id}`),
}

// ─── Gestion ──────────────────────────────────────────────────────────────────
export const gestionAPI = {
  // Kanban
  travaux: (statut?: string) => api.get('/gestion/travaux', { params: statut ? { statut } : {} }),
  creerTravail: (data: Record<string, unknown>) => api.post('/gestion/travaux', data),
  modifierTravail: (id: number, data: Record<string, unknown>) => api.patch(`/gestion/travaux/${id}`, data),
  terminerTravail: (id: number, data?: { message_personnalise?: string; envoyer_whatsapp?: boolean }) =>
    api.post(`/gestion/travaux/${id}/terminer`, data || { envoyer_whatsapp: true }),

  // Devis & Facture
  genererDevis: (data: Record<string, unknown>) => api.post('/gestion/devis', data),
  genererFacture: (data: Record<string, unknown>) => api.post('/gestion/facture', data),
  telechargerDoc: (pdf_id: string) => api.get(`/gestion/document/${pdf_id}`, { responseType: 'blob' }),

  // Caisse
  transactions: (date?: string) => api.get('/gestion/caisse', { params: date ? { date_str: date } : {} }),
  enregistrerTransaction: (data: Record<string, unknown>) => api.post('/gestion/caisse', data),

  // CRM
  clients: (recherche?: string) => api.get('/gestion/clients', { params: recherche ? { recherche } : {} }),
  creerClient: (data: Record<string, unknown>) => api.post('/gestion/clients', data),
  ficheClient: (id: number) => api.get(`/gestion/clients/${id}`),
  whatsappClient: (id: number, message: string) =>
    api.get(`/gestion/clients/${id}/whatsapp`, { params: { message } }),
}

export default api
