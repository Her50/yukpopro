/**
 * Client API du dashboard leads. Pattern aligné avec @yukpo/admin-dashboard :
 * on accepte une instance HTTP injectée par l'app hôte (axios ou compatible),
 * elle gère JWT + 401 → le package reste agnostique.
 */

export interface HttpClient {
  get:    (url: string, config?: any) => Promise<any>;
  patch:  (url: string, data?: any, config?: any) => Promise<any>;
}

export type StatutLead =
  | "non_lu" | "lu" | "contacte" | "converti" | "perdu";

export interface LeadRow {
  id: number;
  slug: string;
  nom: string | null;
  email: string | null;
  telephone: string | null;
  message: string | null;
  source: string;
  statut: StatutLead;
  notes: string | null;
  created_at: string;
}

export interface LeadsListResponse {
  leads: LeadRow[];
  total: number;
  par_statut: Record<string, number>;
  taux_conversion_pct: number;
  limit: number;
  offset: number;
}

export interface PublicationRow {
  slug: string;
  url_public: string;
  plan: "free" | "pro" | "business";
  html_fichier_id: string;
  cree_le: string;
  derniere_modif: string;
}

export interface LeadPatchInput {
  statut?: StatutLead;
  notes?: string;
}

export const leadsApi = (http: HttpClient) => ({
  /** Liste paginée des leads, filtres optionnels. */
  list: async (params?: {
    slug?: string; statut?: StatutLead;
    jours?: number; limit?: number; offset?: number;
  }): Promise<LeadsListResponse> => {
    const res = await http.get("/pro/landing-leads", { params });
    return res.data as LeadsListResponse;
  },

  /** Liste des landings publiées (pour filtre slug). */
  publications: async (): Promise<{ publications: PublicationRow[] }> => {
    const res = await http.get("/pro/landing-publications");
    return res.data;
  },

  /** Maj statut / notes d'un lead. */
  patch: async (lead_id: number, patch: LeadPatchInput) => {
    const res = await http.patch(`/pro/landing-leads/${lead_id}`, patch);
    return res.data;
  },

  /** URL CSV à ouvrir dans un nouvel onglet (auth via cookie/JWT par axios). */
  exportCsvUrl: (params?: { slug?: string; jours?: number }): string => {
    const qs = new URLSearchParams();
    if (params?.slug) qs.set("slug", params.slug);
    if (params?.jours) qs.set("jours", String(params.jours));
    return `/api/v1/pro/landing-leads/export.csv${qs.toString() ? "?" + qs.toString() : ""}`;
  },
});
