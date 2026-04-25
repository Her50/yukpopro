/**
 * EmploiPage — Veille emploi & offres matchées par Yukpo Pro (Web)
 *
 * Fonctionnalités :
 *  - Tableau de bord des offres d'emploi matchées périodiquement
 *  - Activation / désactivation de la veille automatique
 *  - Configuration du profil de recherche (description libre)
 *  - Fréquence de recherche paramétrable
 *  - Lancement manuel d'une recherche
 *  - Score de compatibilité par offre
 *  - Upload / gestion du CV
 *  - Ouverture des offres en nouvel onglet
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Briefcase, Bell, BellOff, Search, Settings, RefreshCw,
  ExternalLink, FileText, Upload, Trash2, Clock, CheckCircle,
  AlertCircle, ChevronDown, ChevronUp, Zap, X,
} from "lucide-react";
import { emploiApi, type OffreEmploi, type ConfigEmploi } from "@/api/client";
import { useEmploiStore } from "@/store/emploiStore";
import { DemoBanner } from "@/components/DemoBanner";

// ── Helpers ───────────────────────────────────────────────────────────────────

const scoreColor = (score?: number) => {
  if (!score) return "text-slate-400";
  if (score >= 75) return "text-emerald-400";
  if (score >= 50) return "text-amber-400";
  return "text-red-400";
};

const scoreBg = (score?: number) => {
  if (!score) return "bg-slate-700";
  if (score >= 75) return "bg-emerald-500/20 border border-emerald-500/30";
  if (score >= 50) return "bg-amber-500/20 border border-amber-500/30";
  return "bg-red-500/20 border border-red-500/30";
};

const scoreLabel = (score?: number) => {
  if (!score) return "–";
  if (score >= 75) return "Excellent";
  if (score >= 50) return "Bon";
  return "Partiel";
};

const formatDate = (iso?: string | null) => {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit", month: "short", year: "numeric",
  });
};

const FREQUENCES = [
  { val: 6,  label: "6 heures" },
  { val: 12, label: "12 heures" },
  { val: 24, label: "24 heures" },
  { val: 48, label: "2 jours" },
  { val: 72, label: "3 jours" },
];

// ── Composant principal ───────────────────────────────────────────────────────

export const EmploiPage = () => {
  const { t } = useTranslation();
  // Store persistant (drafts + filtres survivent à la navigation)
  const showConfig    = useEmploiStore(s => s.showConfig);
  const setShowConfig = useEmploiStore(s => s.setShowConfig);
  const profilTexte   = useEmploiStore(s => s.profilTexte);
  const setProfilTexte = useEmploiStore(s => s.setProfilTexte);
  const frequence     = useEmploiStore(s => s.frequence);
  const setFrequence  = useEmploiStore(s => s.setFrequence);
  const cvTexte       = useEmploiStore(s => s.cvTexte);
  const setCvTexte    = useEmploiStore(s => s.setCvTexte);
  const cvMode        = useEmploiStore(s => s.cvMode);
  const setCvMode     = useEmploiStore(s => s.setCvMode);
  const keyword       = useEmploiStore(s => s.keyword);
  const setKeyword    = useEmploiStore(s => s.setKeyword);
  const expandedIdx   = useEmploiStore(s => s.expandedIdx);
  const setExpandedIdx = useEmploiStore(s => s.setExpandedIdx);

  // État éphémère
  const [config, setConfig]           = useState<ConfigEmploi | null>(null);
  const [loading, setLoading]         = useState(true);
  const [searching, setSearching]     = useState(false);
  const [saving, setSaving]           = useState(false);
  const [uploadingCV, setUploadingCV] = useState(false);
  const [toast, setToast]             = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  const offres = useMemo(() => config?.offres_emploi_recentes || [], [config]);
  const offresFiltrees = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return offres;
    return offres.filter(o =>
      o.titre?.toLowerCase().includes(kw) ||
      o.entreprise?.toLowerCase().includes(kw) ||
      o.lieu?.toLowerCase().includes(kw) ||
      o.description?.toLowerCase().includes(kw) ||
      o.resume?.toLowerCase().includes(kw)
    );
  }, [offres, keyword]);

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  // ── Chargement ──────────────────────────────────────────────────────────────

  const charger = useCallback(async () => {
    setLoading(true);
    try {
      const data = await emploiApi.getConfig();
      setConfig(data);
      // Hydratation initiale uniquement : préserve les éventuels drafts non sauvegardés
      // si l'utilisateur revient sur la page après navigation.
      const st = useEmploiStore.getState();
      if (!st.hydratedFromBackend) {
        setProfilTexte(data.profil_recherche_emploi || "");
        setFrequence(data.frequence_recherche_heures || 24);
        st.markHydrated();
      }
    } catch {
      setConfig({
        recherche_emploi_active: false,
        frequence_recherche_heures: 24,
        profil_recherche_emploi: "",
        derniere_recherche_emploi: null,
        offres_emploi_recentes: [],
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { charger(); }, [charger]);

  // ── Toggle veille ────────────────────────────────────────────────────────────

  const toggleVeille = async () => {
    if (!config) return;
    const nouvelEtat = !config.recherche_emploi_active;
    try {
      if (nouvelEtat) await emploiApi.activerVeille();
      else            await emploiApi.desactiverVeille();
      setConfig({ ...config, recherche_emploi_active: nouvelEtat });
      showToast(nouvelEtat ? "Veille activée" : "Veille désactivée");
    } catch {
      showToast("Action impossible", "err");
    }
  };

  // ── Recherche manuelle ───────────────────────────────────────────────────────

  const lancerRecherche = async () => {
    setSearching(true);
    try {
      const result = await emploiApi.lancerRecherche();
      await charger();
      showToast(`${result.nb_offres} offre(s) trouvée(s) pour votre profil`);
    } catch {
      showToast("Recherche impossible — réessayez", "err");
    } finally {
      setSearching(false);
    }
  };

  // ── Sauvegarder config ───────────────────────────────────────────────────────

  const sauvegarderConfig = async () => {
    setSaving(true);
    try {
      await emploiApi.mettreAJourConfig({
        profil_recherche_emploi: profilTexte,
        frequence_recherche_heures: frequence,
      });
      await charger();
      setShowConfig(false);
      showToast("Configuration sauvegardée");
    } catch {
      showToast("Sauvegarde impossible", "err");
    } finally {
      setSaving(false);
    }
  };

  // ── Upload CV texte ───────────────────────────────────────────────────────────

  const uploadCVTexte = async () => {
    if (!cvTexte.trim()) return;
    setUploadingCV(true);
    try {
      await emploiApi.uploadCV(cvTexte);
      await charger();
      setCvTexte("");
      showToast("CV enregistré avec succès");
    } catch {
      showToast("Erreur upload CV", "err");
    } finally {
      setUploadingCV(false);
    }
  };

  // ── Upload CV fichier ─────────────────────────────────────────────────────────

  const uploadCVFichier = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingCV(true);
    try {
      await emploiApi.uploadCVFichier(file);
      await charger();
      showToast(`CV "${file.name}" enregistré`);
    } catch {
      showToast("Erreur upload CV", "err");
    } finally {
      setUploadingCV(false);
      e.target.value = "";
    }
  };

  const supprimerCV = async () => {
    try {
      await emploiApi.supprimerCV();
      await charger();
      showToast("CV supprimé");
    } catch {
      showToast("Suppression impossible", "err");
    }
  };

  // ── Rendu ─────────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4">
        <div className="w-10 h-10 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-slate-400">{t('emploi.loading')}</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 pb-24 space-y-6">
      <DemoBanner />
      {/* ── Toast ─────────────────────────────────────────────────────────── */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-medium transition-all
          ${toast.type === "ok" ? "bg-emerald-900/90 border border-emerald-500/40 text-emerald-300" : "bg-red-900/90 border border-red-500/40 text-red-300"}`}>
          {toast.type === "ok" ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          {toast.msg}
        </div>
      )}

      {/* ── En-tête ───────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Briefcase className="text-violet-400" size={24} />
            {t('emploi.watchTitle')}
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            {keyword
              ? <><span className="text-violet-400 font-medium">{offresFiltrees.length}</span> sur {offres.length} offre{offres.length !== 1 ? "s" : ""}</>
              : <><span className="text-violet-400 font-medium">{offres.length}</span> offre{offres.length !== 1 ? "s" : ""} disponible{offres.length !== 1 ? "s" : ""}</>
            }
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={lancerRecherche}
            disabled={searching}
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-sm font-semibold rounded-xl transition-colors"
          >
            {searching
              ? <RefreshCw size={15} className="animate-spin" />
              : <Search size={15} />
            }
            {searching ? t('emploi.searching') : t('emploi.searchNow')}
          </button>
          <button
            onClick={() => setShowConfig(!showConfig)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl border transition-colors
              ${showConfig
                ? "bg-violet-600/30 border-violet-500/50 text-violet-300"
                : "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700"}`}
          >
            <Settings size={15} />
            Config
          </button>
        </div>
      </div>

      {/* ── Panneau de configuration ──────────────────────────────────────── */}
      {showConfig && (
        <div className="rounded-2xl p-6 space-y-5" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
          <h2 className="text-white font-bold text-base flex items-center gap-2">
            <Settings size={16} className="text-violet-400" />
            {t('emploi.configTitle')}
          </h2>

          {/* Veille on/off */}
          <div className="flex items-center justify-between p-4 rounded-xl" style={{ background: "var(--ykp-elevated)", border: "1px solid var(--ykp-border)" }}>
            <div className="flex items-center gap-3">
              {config?.recherche_emploi_active
                ? <Bell size={18} className="text-violet-400" />
                : <BellOff size={18} className="text-slate-400" />
              }
              <div>
                <p className="text-white font-semibold text-sm">{t('emploi.watchAuto')}</p>
                <p className="text-slate-400 text-xs">
                  {config?.recherche_emploi_active
                    ? t('emploi.watchActiveFreq', { hours: config.frequence_recherche_heures })
                    : t('marches.watchDesc', 'Inactive')}
                </p>
              </div>
            </div>
            <button
              onClick={toggleVeille}
              className={`relative w-12 h-6 rounded-full transition-colors focus:outline-none
                ${config?.recherche_emploi_active ? "bg-violet-600" : "bg-slate-600"}`}
            >
              <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform
                ${config?.recherche_emploi_active ? "translate-x-7" : "translate-x-1"}`} />
            </button>
          </div>

          {/* Fréquence */}
          <div>
            <label className="text-slate-300 text-sm font-semibold block mb-2">
              {t('emploi.searchFreq')}
            </label>
            <div className="flex flex-wrap gap-2">
              {FREQUENCES.map((f) => (
                <button
                  key={f.val}
                  onClick={() => setFrequence(f.val)}
                  className={`px-4 py-2 text-sm rounded-xl border transition-colors
                    ${frequence === f.val
                      ? "bg-violet-600/30 border-violet-500/60 text-violet-300 font-semibold"
                      : "bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500"}`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Profil de recherche */}
          <div>
            <label className="text-slate-300 text-sm font-semibold block mb-1">
              {t('emploi.profilSearch')}
            </label>
            <p className="text-slate-500 text-xs mb-2">{t('emploi.profileDesc')}</p>
            <textarea
              value={profilTexte}
              onChange={(e) => setProfilTexte(e.target.value)}
              rows={4}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500 resize-none"
              placeholder="Ex : Comptable senior 8 ans d'expérience SYSCOHADA, cherche poste DAF ou RAF, Douala ou Abidjan, secteur banque ou industrie. Disponible immédiatement."
            />
          </div>

          <button
            onClick={sauvegarderConfig}
            disabled={saving}
            className="w-full py-3 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-bold rounded-xl transition-colors"
          >
            {saving ? t('common.saving') : t('emploi.saveConfig')}
          </button>

          {/* ── Section CV ──────────────────────────────────────────────── */}
          <div className="pt-4 border-t border-slate-700">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-violet-400" />
                <span className="text-white font-semibold text-sm">Mon CV</span>
                {config?.cv_disponible && (
                  <span className="px-2 py-0.5 bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 text-xs rounded-full">
                    Enregistré ✓
                  </span>
                )}
              </div>
              {config?.cv_disponible && (
                <button onClick={supprimerCV} className="flex items-center gap-1 text-red-400 hover:text-red-300 text-xs transition-colors">
                  <Trash2 size={13} /> Supprimer
                </button>
              )}
            </div>

            {/* Tabs texte / fichier */}
            <div className="flex gap-1 mb-3 bg-slate-900 rounded-xl p-1 w-fit">
              {(["texte", "fichier"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setCvMode(m)}
                  className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors
                    ${cvMode === m ? "bg-violet-600 text-white" : "text-slate-400 hover:text-white"}`}
                >
                  {m === "texte" ? t('emploi.pasteText') : t('emploi.uploadFile')}
                </button>
              ))}
            </div>

            {cvMode === "texte" ? (
              <div className="space-y-2">
                <textarea
                  value={cvTexte}
                  onChange={(e) => setCvTexte(e.target.value)}
                  rows={5}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500 resize-none"
                  placeholder={t('emploi.cvPastePlaceholder')}
                />
                <button
                  onClick={uploadCVTexte}
                  disabled={uploadingCV || !cvTexte.trim()}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-sm rounded-xl transition-colors"
                >
                  {uploadingCV ? <RefreshCw size={14} className="animate-spin" /> : <Upload size={14} />}
                  {t('emploi.saveCV')}
                </button>
              </div>
            ) : (
              <label className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed
                rounded-xl p-6 cursor-pointer transition-colors
                ${uploadingCV ? "border-violet-500/50 bg-violet-500/10" : "border-slate-600 hover:border-slate-500 bg-slate-900/50"}`}>
                <Upload size={22} className="text-slate-400" />
                <span className="text-slate-300 text-sm font-medium">
                  {uploadingCV ? t('emploi.uploading') : t('emploi.clickOrDrop')}
                </span>
                <span className="text-slate-500 text-xs">{t('emploi.cvFormats')}</span>
                <input
                  type="file"
                  accept=".pdf,.docx,.doc,.txt,.md"
                  className="hidden"
                  onChange={uploadCVFichier}
                  disabled={uploadingCV}
                />
              </label>
            )}
          </div>
        </div>
      )}

      {/* ── Barre de statut ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          icon={config?.recherche_emploi_active ? <Bell size={16} className="text-violet-400" /> : <BellOff size={16} className="text-slate-500" />}
          label={t('emploi.veille')}
          value={config?.recherche_emploi_active ? t('emploi.activeLabel') : t('emploi.inactiveLabel')}
          color={config?.recherche_emploi_active ? "text-violet-400" : "text-slate-400"}
        />
        <StatCard
          icon={<Briefcase size={16} className="text-amber-400" />}
          label={t('emploi.offresFound')}
          value={String(offres.length)}
          color="text-amber-400"
        />
        <StatCard
          icon={<Clock size={16} className="text-slate-400" />}
          label={t('emploi.lastSearch')}
          value={formatDate(config?.derniere_recherche_emploi)}
          color="text-slate-300"
        />
        <StatCard
          icon={<Zap size={16} className="text-emerald-400" />}
          label={t('emploi.frequencyLabel')}
          value={`${config?.frequence_recherche_heures || 24}h`}
          color="text-emerald-400"
        />
      </div>

      {/* ── Alerte profil manquant ────────────────────────────────────────── */}
      {!config?.profil_recherche_emploi && (
        <div className="flex items-start gap-3 p-4 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-xl">
          <AlertCircle size={18} className="text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-amber-800 dark:text-amber-300 text-sm font-semibold">{t('emploi.profileMissing')}</p>
            <p className="text-amber-700 dark:text-amber-400/70 text-xs mt-0.5">{t('emploi.profileMissingDesc')}</p>
          </div>
          <button
            onClick={() => setShowConfig(true)}
            className="ml-auto text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 text-xs font-semibold whitespace-nowrap"
          >
            {t('emploi.configure')}
          </button>
        </div>
      )}

      {/* ── CV badge ─────────────────────────────────────────────────────── */}
      {config?.cv_disponible && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-emerald-500/10 border border-emerald-500/30 rounded-xl">
          <FileText size={15} className="text-emerald-400" />
          <span className="text-emerald-300 text-sm font-medium">{t('emploi.cvUsed')}</span>
        </div>
      )}

      {/* ── Recherche libre dans les offres ──────────────────────────────── */}
      {offres.length > 0 && (
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder={t('marches.searchPlaceholder')}
            className="w-full pl-10 pr-10 py-2.5 bg-slate-800 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500 transition-colors"
          />
          {keyword && (
            <button onClick={() => setKeyword("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white">
              <X size={14} />
            </button>
          )}
        </div>
      )}

      {/* ── Liste des offres ──────────────────────────────────────────────── */}
      {offres.length === 0 ? (
        <EmptyState onSearch={lancerRecherche} searching={searching} />
      ) : offresFiltrees.length === 0 ? (
        <div className="rounded-2xl p-8 text-center space-y-3" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
          <p className="text-white font-semibold">{t('emploi.noKeyword', { keyword })}</p>
          <p className="text-slate-400 text-sm">{t('emploi.emptyDesc')}</p>
          <button
            onClick={() => setKeyword("")}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded-xl transition-colors"
          >
            <X size={14} /> {t('emploi.clearSearch')}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <h2 className="text-white font-bold text-base">
            {keyword ? t('emploi.resultsFor', { keyword }) : t('emploi.recentOffers')}
          </h2>
          {offresFiltrees.map((offre, idx) => (
            <OffreCard
              key={idx}
              offre={offre}
              expanded={expandedIdx === idx}
              onToggle={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
            />
          ))}
        </div>
      )}

      <p className="text-slate-600 text-xs text-center pb-4">
        Sources : Indeed · Emploi.cm · JobAfrica · LinkedIn · Emploi.ci — mis à jour automatiquement
      </p>
    </div>
  );
};

// ── Composants internes ───────────────────────────────────────────────────────

const StatCard = ({ icon, label, value, color }: {
  icon: React.ReactNode; label: string; value: string; color: string;
}) => (
  <div className="rounded-xl p-4 flex items-center gap-3" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
    <div className="flex-shrink-0">{icon}</div>
    <div>
      <p className="text-slate-400 text-xs">{label}</p>
      <p className={`font-bold text-sm ${color}`}>{value}</p>
    </div>
  </div>
);

const EmptyState = ({ onSearch, searching }: { onSearch: () => void; searching: boolean }) => (
  <div className="flex flex-col items-center justify-center py-12 gap-4 text-center">
    <div className="w-16 h-16 bg-slate-800 rounded-2xl flex items-center justify-center">
      <Briefcase size={32} className="text-slate-500" />
    </div>
    <div>
      <h3 className="text-white font-bold text-lg">Aucune offre trouvée</h3>
      <p className="text-slate-400 text-sm mt-1 max-w-sm">
        Activez la veille automatique ou lancez une recherche manuelle.
        Yukpo Pro parcourt Google Jobs, Adzuna, Remotive, Jooble et d'autres sources internationales et locales.
      </p>
    </div>
    <button
      onClick={onSearch}
      disabled={searching}
      className="flex items-center gap-2 px-6 py-3 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-bold rounded-xl transition-colors"
    >
      {searching ? <RefreshCw size={16} className="animate-spin" /> : <Search size={16} />}
      {searching ? "Recherche en cours…" : "Lancer la recherche maintenant"}
    </button>
  </div>
);

const OffreCard = ({ offre, expanded, onToggle }: {
  offre: OffreEmploi; expanded: boolean; onToggle: () => void;
}) => {
  const isSimule  = offre.source_type === "simule";
  const texte     = offre.description || offre.resume || "";
  const dateAff   = offre.date_pub || offre.date_publication;

  return (
    <div
      className={`rounded-2xl p-5 cursor-pointer transition-all ${
        isSimule
          ? "bg-amber-900/10 border border-amber-700/30 hover:border-amber-600/50"
          : "hover:border-slate-600"
      }`}
      style={!isSimule ? { background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" } : {}}
      onClick={onToggle}
    >
      {/* Badge simulation */}
      {isSimule && (
        <div className="flex items-center gap-1.5 mb-3 px-2.5 py-1 bg-amber-500/15 border border-amber-500/25 rounded-lg w-fit">
          <AlertCircle size={12} className="text-amber-400" />
          <span className="text-amber-400 text-xs font-medium">Suggestion YukpoPro — aucune offre réelle trouvée</span>
        </div>
      )}

      {/* En-tête */}
      <div className="flex items-start gap-4">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
          isSimule ? "bg-amber-500/15 border border-amber-500/20" : "bg-violet-500/15 border border-violet-500/20"
        }`}>
          <Briefcase size={18} className={isSimule ? "text-amber-400" : "text-violet-400"} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-white font-bold text-sm leading-snug">{offre.titre}</h3>
          <p className="text-slate-400 text-xs mt-0.5">
            {offre.entreprise}{offre.lieu ? ` · ${offre.lieu}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {offre.score !== undefined && !isSimule && (
            <div className={`px-3 py-1 rounded-lg text-xs font-bold ${scoreBg(offre.score)} ${scoreColor(offre.score)}`}>
              {offre.score}% · {scoreLabel(offre.score)}
            </div>
          )}
          {expanded ? <ChevronUp size={16} className="text-slate-500" /> : <ChevronDown size={16} className="text-slate-500" />}
        </div>
      </div>

      {/* Tags */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        {offre.type_contrat && (
          <span className="px-2.5 py-1 bg-slate-700 text-slate-300 text-xs rounded-full">
            {offre.type_contrat}
          </span>
        )}
        {offre.salaire && (
          <span className="px-2.5 py-1 bg-green-500/10 border border-green-500/20 text-green-400 text-xs rounded-full">
            {offre.salaire}
          </span>
        )}
        {offre.source && !isSimule && (
          <span className="px-2.5 py-1 bg-violet-500/15 border border-violet-500/20 text-violet-400 text-xs rounded-full truncate max-w-[180px]">
            {offre.source}
          </span>
        )}
        {dateAff && (
          <span className="ml-auto text-slate-500 text-xs">{dateAff}</span>
        )}
      </div>

      {/* Détail expandable */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-slate-700 space-y-3" onClick={(e) => e.stopPropagation()}>
          {texte && (
            <p className="text-slate-300 text-sm leading-relaxed">{texte}</p>
          )}
          {isSimule && (
            <p className="text-amber-500/80 text-xs">
              Ces suggestions sont générées par YukpoPro car les sources d'emploi (Google Jobs, Adzuna, Jooble…) étaient indisponibles lors de la dernière recherche. Relancez une recherche pour obtenir de vraies offres.
            </p>
          )}
          <div className="flex items-center gap-3">
            {offre.url && !isSimule && (
              <a
                href={offre.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 bg-violet-600/20 hover:bg-violet-600/40 border border-violet-500/30 text-violet-300 text-sm font-semibold rounded-xl transition-colors"
              >
                <ExternalLink size={14} /> Voir l'offre complète
              </a>
            )}
            {offre.score !== undefined && !isSimule && (
              <span className={`text-sm font-medium ${scoreColor(offre.score)}`}>
                Compatibilité {scoreLabel(offre.score).toLowerCase()} avec votre profil
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
