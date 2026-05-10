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
  get: (url: string, config?: any) => Promise<any>;
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
});
