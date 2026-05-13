import axios from "axios";
import toast from "react-hot-toast";

type AxiosErrorLike<T = unknown> = {
  response?: { status?: number; data?: T };
  message?: string;
};
import type {
  CopiloteResponse,
  AgentChatRequest,
  AgentChatResponse,
  GenererRapportRequest,
  GenererSlidesRequest,
  GenerateurResult,
  RechercheRAGRequest,
  RechercheRAGResponse,
  ProfilPro,
  TraductionRequest,
  TraductionResponse,
  DocumentHistorique,
} from "@/types";

// ── Axios instance ────────────────────────────────────────────────────────────

// Instance axios partagée — exposée pour les composants externes
// (ex: @yukpo/admin-dashboard) qui ont besoin d'hériter de l'auth + baseURL
// configurés ici (intercepteurs JWT + gestion 401 ci-dessous).
export const http: any = axios.create({
  baseURL: "/api/v1",
  timeout: 120_000,  // 2 min — agents Yukpo peuvent être lents
  headers: { "Content-Type": "application/json" },
});

// Injecter le token JWT à chaque requête
http.interceptors.request.use((config: any) => {
  const token = localStorage.getItem("yukpopro_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Gestion centralisée des erreurs
http.interceptors.response.use(
  (res: any) => res,
  (error: AxiosErrorLike<{ detail?: string }>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("yukpopro_token");
      localStorage.removeItem("yukpopro_user");
      window.location.href = "/login";
    } else if (error.response?.status === 429) {
      toast.error("Trop de requêtes — veuillez patienter.");
    } else if (error.response?.status && error.response.status >= 500) {
      const msg = error.response.data?.detail || "Erreur serveur inattendue.";
      toast.error(msg.slice(0, 120));
    }
    return Promise.reject(error);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authApi = {
  login: async (email: string, password: string) => {
    const { data } = await http.post("/auth/login", { username: email, password });
    return data as { access_token: string; token_type: string };
  },

  register: async (payload: { email: string; password: string; nom: string; prenom?: string }) => {
    const { data } = await http.post("/auth/register/pro", payload);
    return data;
  },

  me: async () => {
    const { data } = await http.get("/auth/me");
    return data;
  },

  changerMotDePasse: async (ancien_mdp: string, nouveau_mdp: string) => {
    const { data } = await http.post("/auth/change-password", null, {
      params: { ancien_mdp, nouveau_mdp },
    });
    return data as { succes: boolean; message: string };
  },
};

// ── Profil Pro ────────────────────────────────────────────────────────────────

export const profilApi = {
  get: async (): Promise<ProfilPro> => {
    const { data } = await http.get("/pro/profil/");
    return data;
  },

  create: async (payload: Partial<ProfilPro>): Promise<ProfilPro> => {
    const { data } = await http.post("/pro/profil/", payload);
    return data;
  },

  update: async (payload: Partial<ProfilPro>): Promise<ProfilPro> => {
    const { data } = await http.put("/pro/profil/", payload);
    return data;
  },

  uploadPhoto: async (file: File): Promise<{ message: string; chemin: string }> => {
    const form = new FormData();
    form.append("fichier", file);
    const { data } = await http.post("/pro/profil/photo", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  getPhotoBlobUrl: async (): Promise<string> => {
    const response = await http.get("/pro/profil/photo", { responseType: "blob" });
    return URL.createObjectURL(response.data);
  },

  supprimerPhoto: async (): Promise<void> => {
    await http.delete("/pro/profil/photo");
  },
};

// ── Chat unifié (YukpoPro) — orchestrateur principal ─────────────────────────

export interface UploadedFile {
  nom: string;
  contenu: string; // base64 data URL
  type: string;
}

export interface ChatSendRequest {
  message: string;
  pays?: string;
  fichiers?: UploadedFile[];
  document_ref?: {
    id: number;
    titre: string;
    type_doc: string;
    contenu_genere?: string;
  };
}

export interface ChatResponse {
  reponse: string;
  agent_utilise?: string;
  session_id?: string;
  fichiers_generes?: string[] | null;
  actions?: Array<{ label: string; action: string }>;
  cout_llm?: import("@/types").CoutLLM | null;
  navigation_suggestions?: import("@/types").NavigationSuggestion[];
}

export const chatApi = {
  /**
   * Point d'entrée unique — le backend orchestre agents, traduction, analyse.
   * Essaie /pro/copilote/chat (pro) puis fallback /copilote/chat (assurance).
   */
  send: async (req: ChatSendRequest): Promise<ChatResponse> => {
    try {
      // 600 s : aligné avec le backend (designer polling 570s + marge).
      // Permet aux générations Freeform denses (20 cartes recto-verso +
      // web search Serper + Haiku 20 entries + render 6 planches) de
      // remonter leur lien de téléchargement dans le chat plutôt que
      // de timeout et forcer l'utilisateur à aller dans Mes Documents.
      const { data } = await http.post("/pro/copilote/chat", req, { timeout: 600_000 });
      return data;
    } catch (err: any) {
      if (err.response?.status === 404 || err.response?.status === 422) {
        const { data } = await http.post("/copilote/chat", {
          question: req.message,
          compagnie_id: 1,
        }, { timeout: 600_000 });
        return { reponse: data.reponse || data.message || JSON.stringify(data) };
      }
      throw err;
    }
  },

  suggestions: async (): Promise<string[]> => {
    try {
      const { data } = await http.get("/pro/copilote/suggestions");
      return data.suggestions ?? [];
    } catch {
      return [];
    }
  },

  nouveauSession: async (): Promise<void> => {
    await http.post("/pro/copilote/nouveau", {}).catch(() => {});
  },
};

// ── Copilote (alias rétrocompatibilité) ───────────────────────────────────────

export const copiloteApi = {
  chat: async (message: string, pays?: string): Promise<CopiloteResponse> => {
    const { data } = await http.post("/pro/copilote/chat", { message, pays }, { timeout: 300_000 });
    return data;
  },

  nouveau: async (): Promise<void> => {
    await http.post("/pro/copilote/nouveau", {});
  },

  historique: async () => {
    const { data } = await http.get("/pro/copilote/historique");
    return data;
  },

  suggestions: async () => {
    const { data } = await http.get("/pro/copilote/suggestions");
    return data;
  },

  welcome: async (): Promise<{ message: string; from_llm: boolean; cached: boolean }> => {
    const { data } = await http.get("/pro/copilote/welcome");
    return data;
  },
};

// ── Agent IA ──────────────────────────────────────────────────────────────────

export const agentApi = {
  chat: async (req: AgentChatRequest): Promise<AgentChatResponse> => {
    const { data } = await http.post("/pro/agent/chat", req);
    return data;
  },

  recherche: async (req: RechercheRAGRequest): Promise<RechercheRAGResponse> => {
    const { data } = await http.post("/pro/agent/recherche", req);
    return data;
  },
};

// ── Générateurs ───────────────────────────────────────────────────────────────

export const generateurApi = {
  rapport: async (req: GenererRapportRequest): Promise<GenerateurResult> => {
    const { data } = await http.post("/pro/rapports/generer", req, { timeout: 360_000 });
    return data;
  },

  typesRapports: async () => {
    const { data } = await http.get("/pro/rapports/types");
    return data;
  },

  slides: async (req: GenererSlidesRequest): Promise<GenerateurResult> => {
    const { data } = await http.post("/pro/slides/generer", req, { timeout: 360_000 });
    return data;
  },

  typesSlides: async () => {
    const { data } = await http.get("/pro/slides/types");
    return data;
  },

  /**
   * Visuel marketing single-page via GEOMETRIC PLACEMENT (LLM Vision + Python math).
   *
   * Différence vs freeform :
   *   • LLM raisonne en VISION sémantique (bbox + forme + mask + focal_point)
   *   • Anti-collision math intégrée
   *   • Audit Vision auto-critique avec retry (jusqu'à 2 itérations)
   *   • Logos vectoriels Recraft v3 SVG natifs
   *   • Composition pro niveau Adobe InDesign / Figma
   *
   * Sortie : PNG haute résolution (300 DPI). Option PDF/X-1a + SVG export.
   */
  geometricPlacement: async (req: {
    brief: string;
    page_w_mm?: number;        // défaut A4 portrait 210
    page_h_mm?: number;        // défaut A4 portrait 297
    bleed_mm?: number;
    medias_refs?: string[];
    brand_kit?: Record<string, any> | null;
    inspiration?: string;
    langue?: string;
    modele?: "sonnet" | "opus" | "haiku";
    dpi?: number;
    revision_visuelle?: boolean;
    max_iterations_revision?: number;
    score_seuil_ok?: number;
    export_pdf?: boolean;
    profil_icc?: "fogra39" | "psocoated_v3" | "gracol_us";
    export_svg?: boolean;
  }): Promise<{
    ok: boolean; png_id: string; png_base64: string; size_kb: number;
    pdf_id: string | null; pdf_size_kb: number | null;
    svg_id: string | null; svg_size_kb: number | null;
    placement_plan: any; nb_items: number;
    medias_utilises: string[];
    revisions_journal: any[];
  }> => {
    const { data } = await http.post(
      "/bureau/infographie-pro/geometric-placement", req,
      { timeout: 600_000 },
    );
    return data;
  },

  /**
   * Slides Web Interactives — Reveal.js HTML autonome partageable URL.
   * Plus léger que PPTX, animations fluides, mode présentateur, export PDF.
   */
  slidesWeb: async (req: {
    sujet: string;
    type_pres?: string;
    mode?: string;
    contexte?: string;
    langue?: string;
    generer_images_hero?: boolean;
    brand_kit?: Record<string, any> | null;
  }): Promise<{
    ok: boolean; html_id: string; fichier_genere: string;
    url_telechargement: string; size_kb: number; nb_slides: number;
    theme_used: string; titre: string; format: string;
  }> => {
    const { data } = await http.post("/pro/slides-web/generer", req, { timeout: 600_000 });
    return data;
  },

  /**
   * Vidéo IA text-to-video — Kling 1.6 / LTX-Video via fal.ai, Wan2.1
   * Replicate fallback. Sortie MP4 5-10s.
   *
   * Coûts utilisateur (par 5s, ×2 si 10s) :
   *   • standard (LTX)        : 60 XAF
   *   • premium  (Kling std)  : 240 XAF
   *   • ultra    (Kling pro)  : 600 XAF  ← SOTA qualité broadcast/cinema
   */
  video: async (req: {
    prompt: string;
    duree_s?: number;
    mode?: "standard" | "premium" | "ultra";
    aspect_ratio?: "16:9" | "9:16" | "1:1" | "4:3";
    seed?: number;
  }): Promise<{
    ok: boolean; fichier_id: string; url_telechargement: string;
    duree_s: number; mode: string; aspect_ratio: string;
    size_kb: number; cout_fcfa: number;
  }> => {
    const { data } = await http.post("/bureau/video/generer", req, { timeout: 600_000 });
    return data;
  },

  /**
   * Landing Page Web statique — HTML+Tailwind production-ready single-file.
   * Auto-sections (hero, features, stats, pricing, FAQ, etc.) + favicon SVG.
   */
  landingPage: async (req: {
    sujet: string;
    objectif?: string;
    cible?: string;
    ton?: string;
    contexte?: string;
    langue?: string;
    generer_images?: boolean;
    brand_kit?: Record<string, any> | null;
  }): Promise<{
    ok: boolean; html_id: string; fichier_genere: string;
    url_telechargement: string; size_kb: number; nb_sections: number;
    sections_actives: string[]; titre: string; format: string;
  }> => {
    const { data } = await http.post("/pro/landing-page/generer", req, { timeout: 600_000 });
    return data;
  },

  /**
   * Publie une landing déjà générée sur Netlify (sous-domaine custom).
   * Phase A Sprint 1 — partage URL public + QR code.
   */
  publierLanding: async (req: {
    fichier_id: string;
    slug: string;
    plan?: "free" | "pro" | "business";
    footer_custom?: string;
  }): Promise<{
    ok: boolean; site_id: string; slug: string;
    url_public: string; qr_png_b64: string;
    plan: string; is_new: boolean;
  }> => {
    const { data } = await http.post("/pro/landing-page/publier", req, { timeout: 120_000 });
    return data;
  },

  /**
   * Sprint G1 — Auto-orchestrateur génération documents.
   * L'utilisateur tape un brief en langage naturel, le backend détecte
   * automatiquement le type d'output, le template, le mode et le format.
   * Retourne un devis estimé + payload prêt-à-l'emploi pour l'endpoint cible.
   * Utilisé depuis ChatPage pour intégrer les générations directement dans le chat.
   */
  orchestrer: async (params: {
    brief: string;
    contexte_fichiers?: string;
    langue_forcee?: string;
    type_sortie_force?: "rapport" | "slides";
    mode_force?: "flash" | "standard" | "complet" | "expert";
  }): Promise<{
    intent_detecte: string;
    type_sortie: "rapport" | "slides";
    template_id: string;
    template_label: string;
    mode_recommande: "flash" | "standard" | "complet" | "expert";
    format_sortie: "docx" | "pptx" | "markdown";
    langue: string;
    parametres_extraits: Record<string, string>;
    credits_estimes: number;
    fcfa_user: number;
    duree_estimee_secondes: number;
    credits_disponibles: number;
    peut_payer: boolean;
    fallback_si_solde_insuffisant: { mode: string; credits: number; fcfa_user: number } | null;
    endpoint_cible: string;
    payload_pret: Record<string, unknown>;
    raisonnement: string;
  }> => {
    const { data } = await http.post("/pro/orchestrer", params, { timeout: 60_000 });
    return data;
  },

  // Variante multipart : envoie les bytes des fichiers joints (images
  // manuscrites, scans, PDF, DOCX, XLSX…) au backend pour OCR Vision +
  // extraction texte natif. Le contenu extrait est injecté dans
  // `payload_pret.contexte` pour que la génération aval (rapport/slides/
  // visuel) rédige à partir du contenu réel des fichiers.
  orchestrerMultipart: async (params: {
    brief: string;
    fichiers: { nom: string; type: string; bytes: ArrayBuffer | Uint8Array }[];
    langue_forcee?: string;
    type_sortie_force?: string;
    mode_force?: string;
    ambition?: string;
  }) => {
    const fd = new FormData();
    fd.append("brief", params.brief);
    if (params.langue_forcee) fd.append("langue_forcee", params.langue_forcee);
    if (params.type_sortie_force) fd.append("type_sortie_force", params.type_sortie_force);
    if (params.mode_force) fd.append("mode_force", params.mode_force);
    if (params.ambition) fd.append("ambition", params.ambition);
    for (const f of params.fichiers) {
      // Copie défensive dans un ArrayBuffer dédié (évite l'erreur TS sur
      // SharedArrayBuffer non assignable à BlobPart).
      const src = f.bytes instanceof Uint8Array ? f.bytes : new Uint8Array(f.bytes);
      const buf = new ArrayBuffer(src.byteLength);
      new Uint8Array(buf).set(src);
      const blob = new Blob([buf], { type: f.type || "application/octet-stream" });
      fd.append("fichiers", blob, f.nom);
    }
    // Timeout généreux : OCR Vision ~5-15s/image, plusieurs images possibles.
    const { data } = await http.post("/pro/orchestrer-multipart", fd, {
      timeout: 180_000,
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  // Détection auto du bon endpoint selon le préfixe filename :
  // les fichiers Bureau (designerpro, freeform, ocr, audio, redaction,
  // slides_sec, video) sont stockés sous /bureau/documents/ ;
  // les rapports/slides Pro sous /pro/generateurs/fichier/.
  telecharger: (nomFichier: string) => {
    const isBureau = /^bureau_/i.test(nomFichier);
    return isBureau
      ? `/api/v1/bureau/documents/${encodeURIComponent(nomFichier)}`
      : `/api/v1/pro/generateurs/fichier/${encodeURIComponent(nomFichier)}`;
  },

  analyserEtGenerer: async (params: {
    instruction: string;
    type_sortie?: "rapport" | "slides";
    type_doc?: string;
    mode?: string;
    format_sortie?: string;
    fichiers: File[];
  }): Promise<GenerateurResult> => {
    const form = new FormData();
    form.append("instruction", params.instruction);
    form.append("type_sortie", params.type_sortie ?? "rapport");
    form.append("type_doc", params.type_doc ?? "rapport_analyse");
    form.append("mode", params.mode ?? "standard");
    form.append("format_sortie", params.format_sortie ?? "docx");
    params.fichiers.forEach((f) => form.append("fichiers", f));
    const { data } = await http.post("/pro/analyser-et-generer", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 360_000,
    });
    return data;
  },

  traduire: async (req: TraductionRequest): Promise<TraductionResponse> => {
    const { data } = await http.post("/pro/traduire", req, { timeout: 360_000 });
    return data;
  },

  traduireFichier: async (formData: FormData): Promise<TraductionResponse & { fichier_source?: string }> => {
    const { data } = await http.post("/pro/traduire-fichier", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 360_000,
    });
    return data;
  },

  convertirFichier: async (fichier: File, formatCible: string): Promise<{
    fichier_converti: string;
    format_source: string;
    format_cible: string;
    taille_octets: number;
  }> => {
    const form = new FormData();
    form.append("fichier", fichier);
    form.append("format_cible", formatCible);
    const { data } = await http.post("/pro/convertir-fichier", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  // ── Historique documents générés ─────────────────────────────────────────

  historiqueDocuments: async (type_doc?: string) => {
    const { data } = await http.get("/pro/documents/historique", {
      params: { type_doc, limite: 50 },
    });
    return data as { total: number; documents: DocumentHistorique[] };
  },

  sauvegarderDocument: async (doc: {
    titre: string;
    type_doc: string;
    fichier?: string;
    contenu_source?: string;
    contenu_genere?: string;
    session_id?: string;
    meta?: Record<string, unknown>;
  }) => {
    const { data } = await http.post("/pro/documents/", doc);
    return data as { id: number; titre: string; cree_le: string };
  },

  mettreAJourDocument: async (doc_id: number, updates: {
    titre?: string;
    fichier?: string;
    contenu_genere?: string;
    contenu_source?: string;
    meta?: Record<string, unknown>;
  }) => {
    const { data } = await http.patch(`/pro/documents/${doc_id}`, updates);
    return data;
  },

  supprimerDocument: async (doc_id: number) => {
    const { data } = await http.delete(`/pro/documents/${doc_id}`);
    return data;
  },

  analyserData: async (donnees: unknown, titre?: string) => {
    const { data } = await http.post("/pro/data/analyser", { donnees, titre });
    return data;
  },

  uploadData: async (file: File) => {
    const fd = new FormData();
    fd.append("fichier", file);
    const { data } = await http.post("/pro/data/upload", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
};

// ── Organisations (plan Entreprise) ──────────────────────────────────────────

export interface Organisation {
  id: number;
  nom: string;
  slug: string;
  owner_id: number;
  plan: string;
  prix_par_siege_fcfa: number;
  devise: string;
  max_seats: number | null;
  statut: string;
  domain_auto_join: string | null;
  domain_verifie: boolean;
  pays: string | null;
  secteur: string | null;
  settings: Record<string, any>;
  cree_le: string;
  mon_role?: "owner" | "admin" | "member";
}

export interface OrgMembre {
  id: number;
  org_id: number;
  user_id: number;
  role: "owner" | "admin" | "member";
  statut: string;
  joined_at: string;
  last_active_at: string;
  email: string;
  nom: string;
  username: string;
}

export interface OrgInvite {
  id: number;
  org_id: number;
  email: string;
  role: "admin" | "member";
  statut: string;
  invite_par: number;
  expires_at: string;
  cree_le: string;
  accepte_le: string | null;
  token?: string;
  lien_acceptation?: string;
}

export interface OrgFacture {
  id: number;
  org_id: number;
  period_debut: string;
  period_fin: string;
  sieges_max: number;
  sieges_factures: number;
  prix_unitaire_fcfa: number;
  montant_total_fcfa: number;
  devise: string;
  statut: string;
  transaction_ref: string | null;
  paye_le: string | null;
}

export const orgsApi = {
  monOrg: async (): Promise<Organisation | null> => {
    try {
      const { data } = await http.get("/pro/orgs/me");
      return data;
    } catch (err: any) {
      if (err?.response?.status === 404) return null;
      throw err;
    }
  },
  creer: async (payload: {
    nom: string; pays?: string; secteur?: string;
    prix_par_siege_fcfa?: number; devise?: string;
    max_seats?: number | null; domain_auto_join?: string;
  }): Promise<Organisation> => {
    const { data } = await http.post("/pro/orgs", payload);
    return data;
  },
  update: async (orgId: number, payload: Partial<Organisation>): Promise<Organisation> => {
    const { data } = await http.patch(`/pro/orgs/${orgId}`, payload);
    return data;
  },
  membres: async (orgId: number): Promise<{ membres: OrgMembre[]; mon_role: string }> => {
    const { data } = await http.get(`/pro/orgs/${orgId}/members`);
    return data;
  },
  changerRole: async (orgId: number, userId: number, role: "admin" | "member") => {
    const { data } = await http.patch(`/pro/orgs/${orgId}/members/${userId}`, { role });
    return data;
  },
  retirerMembre: async (orgId: number, userId: number) => {
    const { data } = await http.delete(`/pro/orgs/${orgId}/members/${userId}`);
    return data;
  },
  quitter: async (orgId: number) => {
    const { data } = await http.post(`/pro/orgs/${orgId}/leave`);
    return data;
  },
  invitations: async (orgId: number): Promise<{ invitations: OrgInvite[] }> => {
    const { data } = await http.get(`/pro/orgs/${orgId}/invites`);
    return data;
  },
  inviter: async (orgId: number, email: string, role: "admin" | "member" = "member"): Promise<OrgInvite> => {
    const { data } = await http.post(`/pro/orgs/${orgId}/invites`, { email, role });
    return data;
  },
  revoquerInvite: async (orgId: number, inviteId: number) => {
    const { data } = await http.delete(`/pro/orgs/${orgId}/invites/${inviteId}`);
    return data;
  },
  detailInvite: async (token: string) => {
    const { data } = await http.get(`/pro/orgs/invites/${token}`);
    return data as { invitation: OrgInvite; organisation: Partial<Organisation> & { nom: string } };
  },
  accepterInvite: async (token: string) => {
    const { data } = await http.post(`/pro/orgs/invites/${token}/accept`);
    return data as { message: string; org_id: number; role: string };
  },
  factures: async (orgId: number): Promise<{ factures: OrgFacture[] }> => {
    const { data } = await http.get(`/pro/orgs/${orgId}/billing`);
    return data;
  },
};

// ── Abonnement ────────────────────────────────────────────────────────────────

export const abonnementApi = {
  monAbonnement: async () => {
    const { data } = await http.get("/pro/abonnement/");
    return data;
  },
  plans: async () => {
    const { data } = await http.get("/pro/abonnement/plans");
    return data;
  },
  initierPaiement: async (payload: { plan: string; operateur: string; numero_telephone: string; pays?: string }) => {
    const { data } = await http.post("/pro/abonnement/initier", payload);
    return data;
  },
  confirmerPaiement: async (reference_paiement: string, numero_expediteur: string, transaction_id?: string) => {
    const { data } = await http.post("/pro/abonnement/confirmer", { reference_paiement, numero_expediteur, transaction_id });
    return data;
  },
  historique: async () => {
    const { data } = await http.get("/pro/abonnement/historique");
    return data;
  },
  packsCredits: async () => {
    const { data } = await http.get("/pro/abonnement/packs-credits");
    return data;
  },
  initierRecharge: async (payload: { pack_id: string; operateur: string; numero_telephone: string; pays?: string }) => {
    const { data } = await http.post("/pro/abonnement/initier-recharge", payload);
    return data;
  },
  confirmerRecharge: async (reference_paiement: string, numero_expediteur: string, transaction_id?: string) => {
    const { data } = await http.post("/pro/abonnement/confirmer-recharge", { reference_paiement, numero_expediteur, transaction_id });
    return data;
  },
  wallet: async (jours = 30) => {
    const { data } = await http.get("/pro/abonnement/wallet", { params: { jours } });
    return data;
  },
};

// ── Paiement v2 — multi-provider unifié ──────────────────────────────────────

export type ProviderName =
  | "mtn_momo" | "orange_money" | "cinetpay" | "flutterwave"
  | "notchpay" | "stripe" | "paypal" | "campay" | "wave" | "legacy_manual";

export type PaymentMethod = "mobile_money" | "card" | "bank_transfer" | "wallet" | "paypal";

export interface PaymentInitiatePayload {
  type: "abonnement" | "recharge" | "service";
  plan_ou_pack?: string;
  amount: number;
  currency?: string;
  customer_phone: string;
  customer_email?: string;
  customer_name?: string;
  country_code?: string;
  method?: PaymentMethod;
  preferred_provider?: ProviderName;
  return_url?: string;
  cancel_url?: string;
  metadata?: Record<string, unknown>;
}

export interface PaymentInitiateResponse {
  reference: string;
  provider: ProviderName;
  status: string;
  payment_url?: string;
  ussd_instructions?: string;
  provider_reference?: string;
  error_message?: string;
}

export const paiementV2Api = {
  initier: async (payload: PaymentInitiatePayload): Promise<PaymentInitiateResponse> => {
    const { data } = await http.post("/paiement/v2/initier", payload);
    return data;
  },
  statut: async (reference: string) => {
    const { data } = await http.get(`/paiement/v2/transactions/${reference}`);
    return data;
  },
  providersDispo: async (phone: string, country?: string): Promise<{
    country: string | null;
    providers: ProviderName[];
    fallback_manual: ProviderName;
  }> => {
    const { data } = await http.get("/paiement/v2/providers", {
      params: { phone, country },
    });
    return data;
  },
  health: async () => {
    const { data } = await http.get("/paiement/v2/health");
    return data;
  },
};

// ── Admin — Paiements MoMo ───────────────────────────────────────────────────

export const adminPaiementsApi = {
  pending: async () => {
    const { data } = await http.get("/admin/paiements/pending");
    return data;
  },
  all: async () => {
    const { data } = await http.get("/admin/paiements/all");
    return data;
  },
  valider: async (id: number) => {
    const { data } = await http.post(`/admin/paiements/${id}/valider`);
    return data;
  },
  rejeter: async (id: number, motif: string) => {
    const { data } = await http.post(`/admin/paiements/${id}/rejeter`, { motif });
    return data;
  },
  uploadReleve: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const { data } = await http.post("/admin/paiements/upload-releve", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
  cronAutoAnnulation: async () => {
    const { data } = await http.post("/admin/paiements/cron/auto-annulation");
    return data;
  },
};

// ── Admin ─────────────────────────────────────────────────────────────────────

export const adminApi = {
  utilisateurs: async (params: { page?: number; par_page?: number; search?: string; plan?: string; statut?: string } = {}) => {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("par_page", String(params.par_page ?? 50));
    if (params.search) qs.set("search", params.search);
    if (params.plan) qs.set("plan", params.plan);
    if (params.statut) qs.set("statut", params.statut);
    const { data } = await http.get(`/pro/admin/utilisateurs?${qs.toString()}`);
    return data;
  },
  detailsUtilisateur: async (userId: number) => {
    const { data } = await http.get(`/pro/admin/utilisateurs/${userId}`);
    return data;
  },
  stats: async () => {
    const { data } = await http.get("/pro/admin/stats");
    return data;
  },
  statsAvancees: async (params: { pays?: string; continent?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.pays) qs.set("pays", params.pays);
    if (params.continent) qs.set("continent", params.continent);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    const { data } = await http.get(`/pro/admin/stats/avancees${suffix}`);
    return data;
  },
  statsRevenus: async (params: { date_debut?: string; date_fin?: string; pays?: string; continent?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.date_debut) qs.set("date_debut", params.date_debut);
    if (params.date_fin) qs.set("date_fin", params.date_fin);
    if (params.pays) qs.set("pays", params.pays);
    if (params.continent) qs.set("continent", params.continent);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    const { data } = await http.get(`/pro/admin/stats/revenus${suffix}`);
    return data;
  },
  geoOptions: async () => {
    const { data } = await http.get("/pro/admin/geo/options");
    return data;
  },
  changerMetier: async (userId: number, metier: string, pays?: string) => {
    const { data } = await http.put(`/pro/admin/utilisateurs/${userId}/metier`, { metier, pays });
    return data;
  },
  forcerAbonnement: async (userId: number, plan: string, creditsBonus = 0, dureeJours = 30) => {
    const { data } = await http.put(`/pro/admin/utilisateurs/${userId}/abonnement`,
      { plan, credits_bonus: creditsBonus, duree_jours: dureeJours });
    return data;
  },
  bloquer: async (userId: number, motif?: string, dureeHeures?: number) => {
    const { data } = await http.post(`/pro/admin/utilisateurs/${userId}/bloquer`,
      { motif, duree_heures: dureeHeures });
    return data;
  },
  debloquer: async (userId: number) => {
    const { data } = await http.post(`/pro/admin/utilisateurs/${userId}/debloquer`);
    return data;
  },
  creditsBonus: async (userId: number, montant: number, motif?: string) => {
    const { data } = await http.post(`/pro/admin/utilisateurs/${userId}/credits-bonus`,
      { montant, motif });
    return data;
  },
  promotion: async (
    montant: number,
    cible: "tous" | "plan" | "ids" | "consommation",
    opts: {
      plan?: string;
      user_ids?: number[];
      motif?: string;
      seuil_credits_min?: number;
      seuil_credits_max?: number;
      seuil_appels_min?: number;
      periode_jours?: number;
      pays?: string;
      continent?: string;
    } = {},
  ) => {
    const { data } = await http.post(`/pro/admin/promotions`, { montant, cible, ...opts });
    return data;
  },
  agents: async () => {
    const { data } = await http.get("/pro/admin/agents");
    return data;
  },
};

// ── Réunions Pro ──────────────────────────────────────────────────────────────

// ── Emploi / Veille emploi ────────────────────────────────────────────────────

export interface OffreEmploi {
  titre:         string;
  entreprise:    string;
  lieu?:         string;
  description?:  string;
  resume?:       string;
  url?:          string;
  source?:       string;
  source_type?:  "reel" | "simule";
  date_pub?:     string;
  date_publication?: string;
  score?:        number;
  type_contrat?: string;
  salaire?:      string;
}

export interface ConfigEmploi {
  recherche_emploi_active:    boolean;
  frequence_recherche_heures: number;
  profil_recherche_emploi:    string;
  derniere_recherche_emploi:  string | null;
  offres_emploi_recentes:     OffreEmploi[];
  metier?:       string;
  pays?:         string;
  cv_disponible?: boolean;
}

export const emploiApi = {
  getConfig: async (): Promise<ConfigEmploi> => {
    const { data } = await http.get("/pro/profil/");
    return data;
  },

  mettreAJourConfig: async (payload: {
    profil_recherche_emploi?: string;
    frequence_recherche_heures?: number;
  }): Promise<ConfigEmploi> => {
    const { data } = await http.put("/pro/profil/", payload);
    return data;
  },

  activerVeille: async () => {
    const { data } = await http.post("/pro/profil/veille-emploi/activer");
    return data;
  },

  desactiverVeille: async () => {
    const { data } = await http.post("/pro/profil/veille-emploi/desactiver");
    return data;
  },

  lancerRecherche: async (): Promise<{ nb_offres: number; offres: OffreEmploi[] }> => {
    const { data } = await http.post("/pro/profil/veille-emploi/rechercher");
    return { nb_offres: data.nb_offres || 0, offres: data.offres || [] };
  },

  uploadCV: async (cvTexte: string) => {
    const formData = new FormData();
    formData.append("cv_texte", cvTexte);
    const { data } = await http.post("/pro/profil/cv", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  uploadCVFichier: async (file: File) => {
    const formData = new FormData();
    formData.append("fichier", file);
    const { data } = await http.post("/pro/profil/cv", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  supprimerCV: async () => {
    const { data } = await http.delete("/pro/profil/cv");
    return data;
  },
};

// ── Marchés Publics ───────────────────────────────────────────────────────────

export interface MarchePublic {
  titre:        string;
  organisme?:   string;
  lieu?:        string;
  resume?:      string;
  url?:         string;
  source?:      string;
  source_type?: "reel" | "simule";
  date_pub?:    string;
  secteur?:     string;
}

export const marchesApi = {
  getRecents: async (): Promise<MarchePublic[]> => {
    const { data } = await http.get("/pro/profil/");
    return (data.marches_publics_recents || []) as MarchePublic[];
  },

  lancerRecherche: async (): Promise<{ nb_marches: number; marches: MarchePublic[] }> => {
    const { data } = await http.post("/pro/profil/marches/rechercher");
    return { nb_marches: data.nb_marches || 0, marches: (data.marches || []) as MarchePublic[] };
  },
};

// ─── R1-R5 — Session unifiée bureau (modifications incrémentales) ──────────
//
// Permet au chat YukpoPro de proposer une "suite logique" sur le dernier
// document généré ("change la couleur en bleu", "ajoute une page", "supprime
// la section 3") → route vers /modifier du pipeline mémorisé au lieu de
// régénérer from scratch via /pro/orchestrer + /generer.
//
// Workflow recommandé côté ChatPage :
//   1. Au chargement : bureauSessionApi.courante()
//   2. Pour chaque message user : bureauSessionApi.intent(message) → renvoie
//      {intent, route_modifier?, dernier_fichier_id?}.
//      Si intent === 'modification' + route_modifier → POST route_modifier
//      avec {fichier_id: dernier_fichier_id, instructions: message}.
//      Sinon → flow standard /pro/orchestrer + /pro/rapports/generer etc.
//   3. Optionnel : reset() pour bouton "Nouvelle conversation".
//
// Pipelines supportés : infographe | freeform | designer_pro | rapport |
// slides | geometric — TOUS visuels composites + documents bureau.
export const bureauSessionApi = {
  courante: async () => {
    const { data } = await http.get("/bureau/session/courante");
    return data as {
      session_id: string;
      pipeline: string | null;
      dernier_fichier_id: string | null;
      dernier_brief: string | null;
      a_dernier_fichier: boolean;
      derniere_interaction: string | null;
    };
  },
  intent: async (message: string) => {
    const { data } = await http.post("/bureau/session/intent", { message });
    return data as {
      intent: "modification" | "nouvelle_demande" | "ambigu";
      confiance: number;
      pipeline: string | null;
      dernier_fichier_id: string | null;
      route_modifier?: string | null;
      recommandation?: string;
    };
  },
  reset: async () => {
    await http.post("/bureau/session/reset", {});
  },
  // Helper : exécute le /modifier suggéré par /session/intent. Le route
  // backend renvoie un chemin ABSOLU (/api/v1/...) — on l'utilise tel quel
  // (axios racine, auth héritée par l'intercepteur global).
  executeModifier: async (routeModifier: string, fichier_id: string, instructions: string) => {
    const { data } = await http.post(
      routeModifier.replace(/^\/api\/v1/, ""),  // http.baseURL = "/api/v1"
      { fichier_id, instructions },
      { timeout: 180_000 },
    );
    return data;
  },
};

export const reunionsApi = {
  transcrireDirect: async (formData: FormData): Promise<{
    transcription: string;
    transcription_originale?: string;
    langue_detectee: string;
    traduit: boolean;
    longueur: number;
  }> => {
    const { data } = await http.post("/pro/reunions/transcrire-direct", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120_000,
    });
    return data;
  },

  importerReplay: async (file: File, langue: string = "auto"): Promise<{
    transcription: string;
    langue_detectee: string;
    traduit: boolean;
    longueur: number;
    source: "video" | "audio" | "sous-titres";
    format_source: string;
    participants_detectes?: string[];
    duree_secondes?: number;
    nb_segments?: number;
  }> => {
    const formData = new FormData();
    formData.append("fichier", file);
    formData.append("langue", langue);
    const { data } = await http.post("/pro/reunions/importer-replay", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 600_000,  // gros replay vidéo possible
    });
    return data;
  },

  genererRapport: async (payload: {
    transcription: string;
    titre?: string;
    participants?: string;
    langue?: string;
    contexte?: string;
    duree_secondes?: number;
  }): Promise<{ rapport: string; titre: string; langue: string; fichier?: string; sauvegarde_mes_documents?: boolean }> => {
    const { data } = await http.post("/pro/reunions/generer-rapport", payload, { timeout: 180_000 });
    return data;
  },

  rapportDocxDepuisMarkdown: async (payload: {
    rapport_markdown: string;
    titre?: string;
    participants?: string;
    date?: string;
  }): Promise<{ fichier: string; longueur: number }> => {
    const { data } = await http.post("/pro/reunions/rapport-docx", payload, { timeout: 180_000 });
    return data;
  },
};

// ── Infographie Pro (anciennement Marketing) ─────────────────────────────────

export interface GabaritInfographie {
  cle: string;
  label: string;
  width_mm: number;
  height_mm: number;
  bleed_mm: number;
  categorie: string;
  description: string;
  prix_fcfa: number;
}

export interface SpecificationInfographieData {
  titre: string;
  sous_titre?: string | null;
  corps?: string | null;
  details?: string[];
  palette?: string;
  nom_organisation?: string | null;
  contact?: string | null;
  slogan?: string | null;
  date_evenement?: string | null;
  lieu?: string | null;
}

export interface ProfilInfographie {
  metier?: string;
  secteur?: string;
  nom_organisation?: string;
  audience?: string;
  ton?: "formel" | "chaleureux" | "jeune" | "premium" | "sobre" | string;
  couleur_primaire_hex?: string;
  couleurs_accents_hex?: string[];
}

export interface ResultatInfographieReponse {
  gabarit: string;
  titre?: string;
  palette?: string;
  specification: SpecificationInfographieData | null;
  pdf_id: string | null;
  png_id: string | null;
  pdf_base64: string | null;
  png_base64: string | null;
  pdf_cmyk_id?: string | null;
  pdf_cmyk_base64?: string | null;
  png_preview_id?: string | null;
  png_preview_base64?: string | null;
  svg_id?: string | null;
  svg_base64?: string | null;
  prix_fcfa: number;
  meta?: Record<string, any>;
  analyse_modele?: string;
  dimensions_mm?: { width: number; height: number; bleed: number };
}

export interface VarianteInfographie extends ResultatInfographieReponse {
  index: number;
  variante: string;
}

export interface ResultatVariantesReponse {
  gabarit: string;
  nombre_variantes: number;
  variantes: VarianteInfographie[];
  note?: string;
}

export const infographieApi = {
  listerGabarits: async (): Promise<{ gabarits: GabaritInfographie[]; palettes: string[] }> => {
    const { data } = await http.get("/bureau/infographie/gabarits");
    return data;
  },

  genererDepuisBrief: async (payload: {
    brief: string;
    type_gabarit: string;
    pays?: string;
    profil?: ProfilInfographie;
    export_cmyk?: boolean;
    export_svg?: boolean;
    dpi_preview?: number;
  }): Promise<ResultatInfographieReponse> => {
    const { data } = await http.post("/bureau/infographie/generer", payload, { timeout: 120_000 });
    return data;
  },

  genererVariantes: async (payload: {
    brief: string;
    type_gabarit: string;
    pays?: string;
    profil?: ProfilInfographie;
    nombre?: number;
  }): Promise<ResultatVariantesReponse> => {
    const { data } = await http.post("/bureau/infographie/generer-variantes", payload, { timeout: 180_000 });
    return data;
  },

  genererManuel: async (payload: {
    type_gabarit: string;
    titre: string;
    sous_titre?: string;
    corps?: string;
    details?: string[];
    palette?: string;
    nom_organisation?: string;
    contact?: string;
    slogan?: string;
    date_evenement?: string;
    lieu?: string;
    couleur_primaire_hex?: string;
    couleurs_accents_hex?: string[];
    export_cmyk?: boolean;
    export_svg?: boolean;
  }): Promise<ResultatInfographieReponse> => {
    const { data } = await http.post("/bureau/infographie/generer-manuel", payload, { timeout: 90_000 });
    return data;
  },

  genererDepuisModele: async (payload: {
    modele: File;
    brief: string;
    type_gabarit: string;
    pays?: string;
  }): Promise<ResultatInfographieReponse> => {
    const fd = new FormData();
    fd.append("modele", payload.modele);
    fd.append("brief", payload.brief);
    fd.append("type_gabarit", payload.type_gabarit);
    fd.append("pays", payload.pays || "CM");
    const { data } = await http.post("/bureau/infographie/generer-depuis-modele", fd, {
      timeout: 180_000,
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  genererCustom: async (payload: {
    width_mm: number;
    height_mm: number;
    bleed_mm?: number;
    brief: string;
    pays?: string;
    profil?: ProfilInfographie;
    export_cmyk?: boolean;
    export_svg?: boolean;
  }): Promise<ResultatInfographieReponse> => {
    const { data } = await http.post("/bureau/infographie/generer-custom", payload, { timeout: 120_000 });
    return data;
  },

  modifier: async (payload: {
    fichier_id: string;
    instructions: string;
    pays?: string;
  }): Promise<ResultatInfographieReponse> => {
    const { data } = await http.post("/bureau/infographie/modifier", payload, { timeout: 120_000 });
    return data;
  },

  urlTelechargement: (fichier_id: string): string => {
    const base = (http.defaults.baseURL || "").replace(/\/$/, "");
    return `${base}/bureau/infographie/fichier/${encodeURIComponent(fichier_id)}`;
  },
};

// ── Designer Pro (Infographie multi-page IA) ─────────────────────────────────

export const infographieProApi = {
  projets: async () => (await http.get("/bureau/infographie-pro/projets")).data,
  uploadMedia: async (formData: FormData) =>
    (await http.post("/bureau/infographie-pro/medias", formData, {
      headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000,
    })).data,
  listerMedias: async (params: { portee: "session" | "compte"; categorie?: string; session_id?: string }) =>
    (await http.get("/bureau/infographie-pro/medias", { params })).data,
  supprimerMedia: async (media_id: string, portee: "session" | "compte", session_id?: string) =>
    (await http.delete(`/bureau/infographie-pro/medias/${media_id}`, { params: { portee, session_id } })).data,
  generer: async (payload: {
    cle_projet: string; brief: string; pays?: string; langue?: string;
    profil?: ProfilInfographie; medias_refs?: string[]; export_cmyk?: boolean;
    directives_visuelles?: Record<string, number>;
  }) => (await http.post("/bureau/infographie-pro/generer", payload, { timeout: 360_000 })).data,
  genererAuto: async (payload: {
    brief: string; pays?: string; langue?: string;
    profil?: ProfilInfographie; medias_refs?: string[];
    cle_projet_hint?: string; export_cmyk?: boolean;
    directives_visuelles?: Record<string, number>;
  }) => (await http.post("/bureau/infographie-pro/generer-auto", payload, { timeout: 360_000 })).data,
  modifier: async (payload: {
    projet_id: string; instructions: string;
    medias_refs_supplementaires?: string[]; pays?: string;
    directives_visuelles?: Record<string, number>;
  }) => (await http.post("/bureau/infographie-pro/modifier", payload, { timeout: 360_000 })).data,
  // Sprint 1.7 — Auto-orchestrateur LLM : 1 prompt → analyse complète
  orchestrer: async (payload: {
    prompt: string; pays?: string; langue?: string;
    profil?: ProfilInfographie;
  }) => (await http.post("/bureau/infographie-pro/orchestrer", payload, { timeout: 60_000 })).data,
  // Sprint UX4 — Devis automatique avant génération
  devis: async (payload: {
    brief: string; pays?: string; langue?: string;
    medias_refs?: string[]; cle_projet?: string;
  }) => (await http.post("/bureau/infographie-pro/devis", payload, { timeout: 60_000 })).data,
  // Sprint L1.3 — Export multilingual
  multilingual: async (payload: {
    projet_id: string; langues_cibles: string[];
  }) => (await http.post("/bureau/infographie-pro/multilingual", payload, { timeout: 600_000 })).data,
  // Sprint C1 — Chat conversationnel multi-tours
  chatSession: async () =>
    (await http.get("/bureau/infographie-pro/chat/session")).data,
  chatMessage: async (payload: {
    message: string; medias_refs?: string[]; pays?: string; langue?: string;
  }) => (await http.post("/bureau/infographie-pro/chat/message", payload, { timeout: 60_000 })).data,
  chatUpdateProjetActif: async (projet_id: string) =>
    (await http.post("/bureau/infographie-pro/chat/session/projet-actif", { projet_id })).data,
  chatReset: async () =>
    (await http.post("/bureau/infographie-pro/chat/reset", {})).data,
  // Sprint UX3 — Bulk CSV/XLSX
  bulkAnalyser: async (formData: FormData) =>
    (await http.post("/bureau/infographie-pro/bulk/analyser", formData, {
      headers: { "Content-Type": "multipart/form-data" }, timeout: 60_000,
    })).data,
  bulkLancer: async (payload: {
    rows: any[]; template_brief: string; mapping: Record<string, string>;
    cle_projet: string; mode_visuel?: string; pays?: string; langue?: string;
    accepter_cout: boolean;
  }) => (await http.post("/bureau/infographie-pro/bulk/lancer", payload, { timeout: 600_000 })).data,
  // Sprint 1.6 — Brand LoRA (training par organisation)
  brandLoraList: async () =>
    (await http.get("/bureau/infographie-pro/brand-lora")).data,
  brandLoraTrain: async (payload: {
    label: string; trigger_word: string; description?: string;
    images_refs: string[]; accepter_cout: boolean;
  }) => (await http.post("/bureau/infographie-pro/brand-lora/entrainer", payload,
    { timeout: 60_000 })).data,
  brandLoraDelete: async (lora_id: string) =>
    (await http.delete(`/bureau/infographie-pro/brand-lora/${lora_id}`)).data,
};

// ── Enquêtes & Études ────────────────────────────────────────────────────────

export const enquetesApi = {
  lister: async (): Promise<{ etudes: any[] }> => {
    const { data } = await http.get("/enquetes/");
    return data;
  },

  creer: async (payload: {
    titre: string; contexte: string; methodologie: string; mode: string;
    population_cible?: string; terrain?: string; questions_recherche?: string[];
  }): Promise<any> => {
    const { data } = await http.post("/enquetes/", payload);
    return data;
  },

  getEtude: async (id: string): Promise<any> => {
    const { data } = await http.get(`/enquetes/${id}`);
    return data;
  },

  uploaderAudio: async (etude_id: string, file: File, locuteur = "Répondant"): Promise<any> => {
    const fd = new FormData();
    fd.append("audio", file, file.name);
    fd.append("locuteur", locuteur);
    const { data } = await http.post(`/enquetes/${etude_id}/audio`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 180_000,
    });
    return data;
  },

  analyser: async (etude_id: string): Promise<any> => {
    const { data } = await http.post(`/enquetes/${etude_id}/analyser`, {}, { timeout: 180_000 });
    return data;
  },

  genererRapport: async (etude_id: string, format = "json"): Promise<any> => {
    const { data } = await http.post(
      `/enquetes/${etude_id}/rapport`,
      null,
      { params: { format_rapport: format }, timeout: 180_000 }
    );
    return data;
  },

  getRapport: async (etude_id: string): Promise<any> => {
    const { data } = await http.get(`/enquetes/${etude_id}/rapport`);
    return data;
  },

  analyserIntelligent: async (etude_id: string): Promise<any> => {
    const { data } = await http.post(`/enquetes/${etude_id}/analyser-intelligent`, {}, { timeout: 180_000 });
    return data;
  },

  listerTranscriptions: async (etude_id: string): Promise<any> => {
    const { data } = await http.get(`/enquetes/${etude_id}/transcriptions`);
    return data;
  },

  analyserQuantitatif: async (etude_id: string): Promise<any> => {
    const { data } = await http.post(`/enquetes/${etude_id}/analyser-quantitatif`, {}, { timeout: 180_000 });
    return data;
  },

  analyserCommentaires: async (etude_id: string): Promise<any> => {
    const { data } = await http.post(`/enquetes/${etude_id}/analyser-commentaires`, {}, { timeout: 180_000 });
    return data;
  },

  creerFormulaire: async (etude_id: string, payload: {
    titre: string; description?: string; questions: any[];
  }): Promise<any> => {
    const { data } = await http.post(`/enquetes/${etude_id}/formulaire`, payload);
    return data;
  },

  genererFormulaireIa: async (payload: {
    description: string; titre: string; objectif: string;
    population: string; n_questions?: number; creer_dans_etude?: string;
  }): Promise<any> => {
    const { data } = await http.post("/enquetes/generer-formulaire-ia", payload, { timeout: 180_000 });
    return data;
  },

  donneesFormulaire: async (etude_id: string): Promise<any> => {
    const { data } = await http.get(`/enquetes/${etude_id}/formulaire/donnees`);
    return data;
  },

  xlsformUrl: (etude_id: string): string =>
    `/api/v1/enquetes/${etude_id}/formulaire/xlsform`,

  csvDonneesUrl: (etude_id: string): string =>
    `/api/v1/enquetes/${etude_id}/formulaire/donnees.csv`,

  majFormulaire: async (formulaire_id: string, payload: {
    titre?: string; description?: string; actif?: boolean; questions: any[];
  }): Promise<any> => {
    const { data } = await http.put(`/enquetes/formulaire/${formulaire_id}/structure`, payload);
    return data;
  },

  getFormulairePublic: async (formulaire_id: string): Promise<any> => {
    const { data } = await http.get(`/enquetes/formulaire/${formulaire_id}`);
    return data;
  },

  soumettreFormulaire: async (formulaire_id: string, reponses: Record<string, any>): Promise<any> => {
    const { data } = await http.post(`/enquetes/formulaire/${formulaire_id}/soumettre`, reponses);
    return data;
  },

  // Dictionnaire des variables
  getDictionnaire: async (etude_id: string): Promise<any> => {
    const { data } = await http.get(`/enquetes/${etude_id}/dictionnaire`);
    return data;
  },
  setDictionnaire: async (etude_id: string, variables: Record<string, any>): Promise<any> => {
    const { data } = await http.put(`/enquetes/${etude_id}/dictionnaire`, { variables });
    return data;
  },
  genererDictionnaireIa: async (etude_id: string): Promise<any> => {
    const { data } = await http.post(`/enquetes/${etude_id}/dictionnaire/generer-ia`, {}, { timeout: 120_000 });
    return data;
  },

  // Plan d'analyse
  getPlanAnalyse: async (etude_id: string): Promise<any> => {
    const { data } = await http.get(`/enquetes/${etude_id}/plan-analyse`);
    return data;
  },
  setPlanAnalyse: async (etude_id: string, plan_analyse: string): Promise<any> => {
    const { data } = await http.put(`/enquetes/${etude_id}/plan-analyse`, { plan_analyse });
    return data;
  },
  genererPlanAnalyseIa: async (etude_id: string): Promise<any> => {
    const { data } = await http.post(`/enquetes/${etude_id}/plan-analyse/generer-ia`, {}, { timeout: 180_000 });
    return data;
  },

  questionnaireDocxUrl: (etude_id: string): string =>
    `/api/v1/enquetes/${etude_id}/questionnaire.docx`,
  planAnalyseDocxUrl: (etude_id: string): string =>
    `/api/v1/enquetes/${etude_id}/plan-analyse.docx`,

  uploadProtocole: async (
    etude_id: string,
    file: File,
    params: { titre: string; objectif?: string; population?: string; n_questions?: number }
  ): Promise<any> => {
    const fd = new FormData();
    fd.append("fichier", file, file.name);
    fd.append("etude_id", etude_id);
    fd.append("titre", params.titre);
    fd.append("objectif", params.objectif || "");
    fd.append("population", params.population || "");
    fd.append("n_questions", String(params.n_questions || 20));
    const { data } = await http.post("/enquetes/upload-protocole", fd, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 240_000,
    });
    return data;
  },
};

export default http;
