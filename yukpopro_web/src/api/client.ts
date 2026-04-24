import axios, { AxiosInstance, AxiosError } from "axios";
import toast from "react-hot-toast";
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

const http: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  timeout: 120_000,  // 2 min — agents Yukpo peuvent être lents
  headers: { "Content-Type": "application/json" },
});

// Injecter le token JWT à chaque requête
http.interceptors.request.use((config) => {
  const token = localStorage.getItem("yukpopro_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Gestion centralisée des erreurs
http.interceptors.response.use(
  (res) => res,
  (error: AxiosError<{ detail?: string }>) => {
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
    const { data } = await http.patch("/pro/profil/", payload);
    return data;
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
      const { data } = await http.post("/pro/copilote/chat", req);
      return data;
    } catch (err: any) {
      if (err.response?.status === 404 || err.response?.status === 422) {
        // Fallback vers le copilote assurance (champ question, pas message)
        const { data } = await http.post("/copilote/chat", {
          question: req.message,
          compagnie_id: 1,
        });
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
    const { data } = await http.post("/pro/copilote/chat", { message, pays });
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
    const { data } = await http.post("/pro/rapports/generer", req, { timeout: 270_000 });
    return data;
  },

  typesRapports: async () => {
    const { data } = await http.get("/pro/rapports/types");
    return data;
  },

  slides: async (req: GenererSlidesRequest): Promise<GenerateurResult> => {
    const { data } = await http.post("/pro/slides/generer", req, { timeout: 270_000 });
    return data;
  },

  typesSlides: async () => {
    const { data } = await http.get("/pro/slides/types");
    return data;
  },

  telecharger: (nomFichier: string) =>
    `/api/v1/pro/generateurs/fichier/${encodeURIComponent(nomFichier)}`,

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
      timeout: 270_000,
    });
    return data;
  },

  traduire: async (req: TraductionRequest): Promise<TraductionResponse> => {
    const { data } = await http.post("/pro/traduire", req, { timeout: 270_000 });
    return data;
  },

  traduireFichier: async (formData: FormData): Promise<TraductionResponse & { fichier_source?: string }> => {
    const { data } = await http.post("/pro/traduire-fichier", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 270_000,
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
  confirmerPaiement: async (reference_paiement: string, transaction_id?: string) => {
    const { data } = await http.post("/pro/abonnement/confirmer", { reference_paiement, transaction_id });
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
  confirmerRecharge: async (reference_paiement: string, transaction_id?: string) => {
    const { data } = await http.post("/pro/abonnement/confirmer-recharge", { reference_paiement, transaction_id });
    return data;
  },
};

// ── Admin ─────────────────────────────────────────────────────────────────────

export const adminApi = {
  utilisateurs: async (page = 1, parPage = 50) => {
    const { data } = await http.get(`/pro/admin/utilisateurs?page=${page}&par_page=${parPage}`);
    return data;
  },
  stats: async () => {
    const { data } = await http.get("/pro/admin/stats");
    return data;
  },
  changerMetier: async (userId: number, metier: string, pays?: string) => {
    const { data } = await http.put(`/pro/admin/utilisateurs/${userId}/metier`, { metier, pays });
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
  titre:      string;
  organisme?: string;
  lieu?:      string;
  resume?:    string;
  url?:       string;
  source?:    string;
  date_pub?:  string;
  secteur?:   string;
}

export const marchesApi = {
  getRecents: async (): Promise<MarchePublic[]> => {
    const { data } = await http.get("/pro/profil/");
    return (data.marches_publics_recents || []) as MarchePublic[];
  },

  lancerRecherche: async (): Promise<{ nb_marches: number }> => {
    const { data } = await http.post("/pro/profil/marches/rechercher");
    return { nb_marches: data.nb_marches || 0 };
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

export interface ResultatInfographieReponse {
  gabarit: string;
  titre?: string;
  palette?: string;
  specification: SpecificationInfographieData | null;
  pdf_id: string | null;
  png_id: string | null;
  pdf_base64: string | null;
  png_base64: string | null;
  prix_fcfa: number;
  meta?: Record<string, any>;
  analyse_modele?: string;
  dimensions_mm?: { width: number; height: number; bleed: number };
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
  }): Promise<ResultatInfographieReponse> => {
    const { data } = await http.post("/bureau/infographie/generer", payload, { timeout: 90_000 });
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
  }): Promise<ResultatInfographieReponse> => {
    const { data } = await http.post("/bureau/infographie/generer-manuel", payload, { timeout: 60_000 });
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
      timeout: 120_000,
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
  }): Promise<ResultatInfographieReponse> => {
    const { data } = await http.post("/bureau/infographie/generer-custom", payload, { timeout: 90_000 });
    return data;
  },

  urlTelechargement: (fichier_id: string): string => {
    const base = (http.defaults.baseURL || "").replace(/\/$/, "");
    return `${base}/bureau/infographie/fichier/${encodeURIComponent(fichier_id)}`;
  },
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
