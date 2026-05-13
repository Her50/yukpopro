/**
 * Client API du dashboard cross-app.
 *
 * On accepte une instance HTTP-like injectée par chaque app hôte
 * (yukpopro_web ou yukposecretariat_web) — chaque app a déjà ses propres
 * intercepteurs pour le token JWT et la gestion des 401. Le composant
 * partagé reste agnostique à l'auth et à la lib HTTP utilisée.
 *
 * Le type `HttpClient` est volontairement minimal (duck-typed) pour
 * éviter de coupler ce package partagé à axios — les deux apps utilisent
 * axios mais l'interface ci-dessous suffit.
 */

export type AppScope = "pro" | "sec" | "both";

// Volontairement permissif pour accepter une AxiosInstance ou tout
// client similaire sans coupler le package à axios.
export interface HttpClient {
  get:  (url: string, config?: any) => Promise<any>;
  post: (url: string, data?: any, config?: any) => Promise<any>;
}

// ── Gestion utilisateurs (lecture détaillée + actions) ─────────────────────
// Format unifié pour Pro et Sec — chaque endpoint renvoie une forme
// légèrement différente ; le client normalise vers ce type.
export interface UtilisateurAdminRow {
  app: "pro" | "sec";
  id: number;
  username?: string | null;
  email?: string | null;
  nom?: string | null;
  prenoms?: string | null;
  role?: string | null;
  actif: boolean;
  bloque: boolean;
  bloque_jusqu_au?: string | null;
  cree_le?: string | null;
  derniere_connexion?: string | null;
  nb_connexions: number;
  plan?: string | null;
  credits_alloues: number;
  credits_utilises: number;
  credits_restants: number;
  /** Côté Pro : conso cumulée totale. Côté Sec : crédits restants × 0.6 (équivalent FCFA). */
  conso_total?: number;
  /** Côté Pro : nb appels cumulés. Côté Sec : non fourni par l'endpoint liste. */
  nb_appels_total?: number;
}

export interface ListeUtilisateursResponse {
  utilisateurs: UtilisateurAdminRow[];
  total: number;
  page: number;
  par_page: number;
}

export interface CreditsBonusRequest {
  montant: number;
  motif?: string;
}

export type CiblePromotion = "tous" | "plan" | "ids" | "consommation" | "role";

export interface PromotionRequest {
  montant: number;
  cible: CiblePromotion;
  plan?: string;        // si cible="plan" (Pro uniquement)
  role?: string;        // si cible="role" (Sec uniquement)
  user_ids?: number[];  // si cible="ids"
  motif?: string;
  // Filtres "consommation"
  seuil_credits_min?: number;
  seuil_credits_max?: number;
  seuil_appels_min?: number;
  periode_jours?: number;
  // Filtres géographiques (Pro uniquement)
  pays?: string;
  continent?: string;
}

export interface PromotionResponse {
  succes: boolean;
  beneficiaires?: number;
  beneficiaires_count?: number;
  montant_total?: number;
  message?: string;
}

export interface DashboardKPIs {
  scope: AppScope;
  periode_jours: number;
  utilisateurs: { total: number; actifs: number };
  consommation: {
    pro: { appels: number; fcfa: number; credits: number; tokens_in: number; tokens_out: number };
    sec: { appels: number; fcfa: number; credits: number; tokens_in: number; tokens_out: number };
    total: { appels: number; fcfa: number; credits: number; tokens_in: number; tokens_out: number };
  };
  credits_alloues: { pro: number; sec: number };
  top_features: { app: "pro" | "sec"; module: string; nb_appels: number; fcfa: number }[];
}

export interface UsageDay {
  jour: string;
  nb_appels: number;
  fcfa: number;
  credits: number;
  tokens_in: number;
  tokens_out: number;
  pro_fcfa: number;
  sec_fcfa: number;
}

export interface FeatureRow {
  app: "pro" | "sec";
  module: string;
  nb_appels: number;
  fcfa: number;
  credits: number;
  tokens_in: number;
  tokens_out: number;
}

export interface ProviderRow {
  provider: string;
  nb_appels: number;
  fcfa: number;
  usd: number;
  credits: number;
  tokens_in: number;
  tokens_out: number;
  modeles: string[];
  pct_fcfa: number;
}

export interface UserRow {
  app: "pro" | "sec";
  user_id: number;
  email: string;
  nb_appels: number;
  fcfa: number;
  credits: number;
}

export interface AlerteRow {
  code: string;
  severite: "critical" | "warning" | "info";
  titre: string;
  message: string;
  valeur: number;
  seuil: number;
  contexte: Record<string, unknown>;
  detectee_le: string;
}

export interface AlertesResponse {
  scope: AppScope;
  evaluees_le: string;
  nb_alertes: number;
  par_severite: { critical: number; warning: number; info: number };
  alertes: AlerteRow[];
}

export const adminCrossApi = (http: HttpClient) => ({
  dashboard: async (scope: AppScope, jours = 30): Promise<DashboardKPIs> =>
    (await http.get("/admin-cross/dashboard", { params: { scope, jours } })).data,
  usage: async (scope: AppScope, jours = 30): Promise<{ scope: AppScope; periode_jours: number; series: UsageDay[] }> =>
    (await http.get("/admin-cross/usage", { params: { scope, jours } })).data,
  cost: async (scope: AppScope, jours = 30) =>
    (await http.get("/admin-cross/cost", { params: { scope, jours } })).data,
  byFeature: async (scope: AppScope, jours = 30, limit = 50): Promise<{ scope: AppScope; periode_jours: number; features: FeatureRow[] }> =>
    (await http.get("/admin-cross/by-feature", { params: { scope, jours, limit } })).data,
  byProvider: async (scope: AppScope, jours = 30): Promise<{ scope: AppScope; periode_jours: number; providers: ProviderRow[]; total_fcfa: number }> =>
    (await http.get("/admin-cross/by-provider", { params: { scope, jours } })).data,
  byUser: async (scope: AppScope, jours = 30, limit = 20): Promise<{ scope: AppScope; periode_jours: number; users: UserRow[] }> =>
    (await http.get("/admin-cross/by-user", { params: { scope, jours, limit } })).data,
  alerts: async (scope: AppScope): Promise<AlertesResponse> =>
    (await http.get("/admin-cross/alerts", { params: { scope } })).data,
  thresholds: async () =>
    (await http.get("/admin-cross/thresholds")).data,

  // ── Gestion utilisateurs détaillée (Pro + Sec normalisé) ──────────────
  /**
   * Liste paginée des utilisateurs avec date d'inscription, dernière
   * connexion, plan, crédits restants, conso cumulée. Si scope="both",
   * agrège Pro + Sec (chaque user peut apparaître 1× par app).
   */
  listerUtilisateurs: async (
    scope: AppScope, page = 1, par_page = 50, recherche?: string,
  ): Promise<ListeUtilisateursResponse> => {
    const tasks: Promise<{ rows: UtilisateurAdminRow[]; total: number }>[] = [];
    if (scope === "pro" || scope === "both") {
      tasks.push(
        http.get("/pro/admin/utilisateurs", {
          params: { page, par_page, search: recherche || undefined },
        }).then((r: any) => ({
          rows: (r.data.utilisateurs || []).map((u: any): UtilisateurAdminRow => ({
            app: "pro",
            id: u.id, username: u.username, email: u.email,
            nom: u.nom, prenoms: u.prenoms, role: u.role,
            actif: !!u.actif, bloque: !!u.bloque,
            bloque_jusqu_au: u.bloque_jusqu_au,
            cree_le: u.cree_le,
            derniere_connexion: u.derniere_connexion,
            nb_connexions: u.nb_connexions || 0,
            plan: u.plan,
            credits_alloues: u.credits_alloues || 0,
            credits_utilises: u.credits_utilises || 0,
            credits_restants: u.credits_restants || 0,
            conso_total: u.conso_total || 0,
            nb_appels_total: u.nb_appels_total || 0,
          })),
          total: r.data.total || 0,
        })).catch((): { rows: UtilisateurAdminRow[]; total: number } => ({ rows: [], total: 0 })),
      );
    }
    if (scope === "sec" || scope === "both") {
      tasks.push(
        http.get("/bureau/admin/utilisateurs", {
          params: { page, par_page, recherche: recherche || undefined },
        }).then((r: any) => ({
          rows: (r.data.utilisateurs || []).map((u: any): UtilisateurAdminRow => ({
            app: "sec",
            id: u.id, username: u.username, email: u.email,
            nom: u.nom, prenoms: u.prenoms, role: u.role,
            actif: !!u.actif,
            bloque: !u.actif || !!u.bloque_jusqu_au,
            bloque_jusqu_au: u.bloque_jusqu_au,
            cree_le: u.cree_le,
            derniere_connexion: u.derniere_connexion,
            nb_connexions: u.nb_connexions || 0,
            plan: u.credits?.plan || null,
            credits_alloues: u.credits?.credits_alloues || 0,
            credits_utilises: u.credits?.credits_utilises || 0,
            credits_restants: u.credits?.credits_restants || 0,
            conso_total: u.credits?.credits_utilises || 0,
            nb_appels_total: 0, // non exposé sur Sec liste
          })),
          total: r.data.total || 0,
        })).catch((): { rows: UtilisateurAdminRow[]; total: number } => ({ rows: [], total: 0 })),
      );
    }
    const results = await Promise.all(tasks);
    const utilisateurs = results.flatMap(r => r.rows);
    const total = results.reduce((acc, r) => acc + r.total, 0);
    // Tri par derniere_connexion DESC puis cree_le DESC
    utilisateurs.sort((a, b) => {
      const da = a.derniere_connexion || a.cree_le || "";
      const db = b.derniere_connexion || b.cree_le || "";
      return db.localeCompare(da);
    });
    return { utilisateurs, total, page, par_page };
  },

  /** Ajoute des crédits bonus à un utilisateur spécifique. */
  ajouterCreditsBonus: async (
    app: "pro" | "sec", userId: number, req: CreditsBonusRequest,
  ): Promise<{ succes: boolean; credits_alloues?: number; nouveau_solde?: number; message?: string }> => {
    if (app === "pro") {
      const r = await http.post(
        `/pro/admin/utilisateurs/${userId}/credits-bonus`,
        { montant: req.montant, motif: req.motif },
      );
      return r.data;
    } else {
      // Sec attend `{ credits, raison }` (noms différents)
      const r = await http.post(
        `/bureau/admin/utilisateurs/${userId}/credits-bonus`,
        { credits: req.montant, raison: req.motif },
      );
      return r.data;
    }
  },

  /** Lance une campagne de bonus crédits ciblée. */
  lancerPromotion: async (
    app: "pro" | "sec", req: PromotionRequest,
  ): Promise<PromotionResponse> => {
    const path = app === "pro" ? "/pro/admin/promotions" : "/bureau/admin/promotion";
    const r = await http.post(path, req);
    return r.data;
  },

  /** Blocage / déblocage d'un utilisateur. */
  bloquer: async (
    app: "pro" | "sec", userId: number, opts: { duree_heures?: number; motif?: string } = {},
  ): Promise<{ succes: boolean }> => {
    if (app === "pro") {
      const r = await http.post(
        `/pro/admin/utilisateurs/${userId}/bloquer`,
        { duree_heures: opts.duree_heures, motif: opts.motif },
      );
      return r.data;
    } else {
      // Sec attend `jours` en query
      const jours = Math.max(1, Math.ceil((opts.duree_heures || 7 * 24) / 24));
      const r = await http.post(
        `/bureau/admin/utilisateurs/${userId}/bloquer?jours=${jours}`,
        {},
      );
      return r.data;
    }
  },
  debloquer: async (app: "pro" | "sec", userId: number): Promise<{ succes: boolean }> => {
    const base = app === "pro" ? "/pro/admin/utilisateurs" : "/bureau/admin/utilisateurs";
    const r = await http.post(`${base}/${userId}/debloquer`, {});
    return r.data;
  },
});
