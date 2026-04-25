/**
 * MarchesPage — Veille marchés publics & appels d'offres
 * Filtres libres : mot-clé, secteur, source — sans restriction de profil
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Gavel, RefreshCw, ExternalLink, Building2, MapPin,
  Calendar, Bell, CheckCircle, AlertCircle,
  Search, Zap, Globe, Filter, X,
} from "lucide-react";
import { marchesApi, type MarchePublic } from "@/api/client";
import { useMarchesStore } from "@/store/marchesStore";
import { DemoBanner } from "@/components/DemoBanner";

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
];

export const MarchesPage = () => {
  const { t } = useTranslation();
  const [marches, setMarches]       = useState<MarchePublic[]>([]);
  const [loading, setLoading]       = useState(true);
  const [searching, setSearching]   = useState(false);
  const [toast, setToast]           = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  // Store persistant : filtres + fréquence + panneau sources survivent à la nav
  const frequence       = useMarchesStore(s => s.frequence);
  const setFrequence    = useMarchesStore(s => s.setFrequence);
  const showSources     = useMarchesStore(s => s.showSources);
  const setShowSources  = useMarchesStore(s => s.setShowSources);
  const keyword         = useMarchesStore(s => s.keyword);
  const setKeyword      = useMarchesStore(s => s.setKeyword);
  const filtreSecteur   = useMarchesStore(s => s.filtreSecteur);
  const setFiltreSecteur = useMarchesStore(s => s.setFiltreSecteur);
  const filtreSource    = useMarchesStore(s => s.filtreSource);
  const setFiltreSource = useMarchesStore(s => s.setFiltreSource);

  const secteurs = useMemo(
    () => [...new Set(marches.map(m => m.secteur).filter(Boolean) as string[])],
    [marches],
  );
  const sources = useMemo(
    () => [...new Set(marches.map(m => m.source).filter(Boolean) as string[])],
    [marches],
  );

  const marchesFiltres = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return marches.filter(m => {
      const matchKw = !kw ||
        m.titre?.toLowerCase().includes(kw) ||
        m.organisme?.toLowerCase().includes(kw) ||
        m.lieu?.toLowerCase().includes(kw) ||
        m.resume?.toLowerCase().includes(kw);
      const matchSecteur = !filtreSecteur || m.secteur === filtreSecteur;
      const matchSource  = !filtreSource  || m.source  === filtreSource;
      return matchKw && matchSecteur && matchSource;
    });
  }, [marches, keyword, filtreSecteur, filtreSource]);

  const filtresActifs = keyword || filtreSecteur || filtreSource;

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const charger = useCallback(async () => {
    setLoading(true);
    try {
      const data = await marchesApi.getRecents();
      setMarches(data);
    } catch {
      setMarches([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { charger(); }, [charger]);

  const lancerRecherche = async () => {
    setSearching(true);
    try {
      const result = await marchesApi.lancerRecherche();
      await charger();
      showToast(`${result.nb_marches} appel(s) d'offres chargé(s)`);
    } catch {
      showToast("Recherche impossible — réessayez", "err");
    } finally {
      setSearching(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4">
        <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-slate-400">{t('marches.loadingText')}</p>
      </div>
    );
  }

  return (
    <div className="ykp-page max-w-4xl mx-auto px-4 py-6 space-y-6">
      <DemoBanner />
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-medium transition-all
          ${toast.type === "ok" ? "bg-emerald-900/90 border border-emerald-500/40 text-emerald-300" : "bg-red-900/90 border border-red-500/40 text-red-300"}`}>
          {toast.type === "ok" ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          {toast.msg}
        </div>
      )}

      {/* En-tête */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Gavel className="text-blue-400" size={24} />
            {t('marches.title')}
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            {filtresActifs
              ? <><span className="text-blue-400 font-medium">{marchesFiltres.length}</span> sur {marches.length} résultat{marches.length !== 1 ? "s" : ""}</>
              : <><span className="text-blue-400 font-medium">{marches.length}</span> résultat{marches.length !== 1 ? "s" : ""} disponible{marches.length !== 1 ? "s" : ""}</>
            }
          </p>
        </div>
        <button
          onClick={lancerRecherche}
          disabled={searching}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold rounded-xl transition-colors"
        >
          {searching
            ? <RefreshCw size={15} className="animate-spin" />
            : <Search size={15} />
          }
          {searching ? t('common.searching') : t('marches.searchNow')}
        </button>
      </div>

      {/* ── Barre de filtres ──────────────────────────────────────────────────── */}
      <div className="rounded-2xl p-4 space-y-3" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
        <div className="flex items-center gap-2 mb-1">
          <Filter size={14} className="text-blue-400" />
          <span className="text-slate-300 text-sm font-semibold">{t('marches.filterTitle')}</span>
          {filtresActifs && (
            <button
              onClick={() => { setKeyword(""); setFiltreSecteur(""); setFiltreSource(""); }}
              className="ml-auto flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors"
            >
              <X size={12} /> {t('marches.resetFilters')}
            </button>
          )}
        </div>

        {/* Mot-clé */}
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder={t('marches.searchPlaceholder')}
            className="w-full pl-9 pr-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
          />
          {keyword && (
            <button onClick={() => setKeyword("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white">
              <X size={14} />
            </button>
          )}
        </div>

        {/* Secteur chips */}
        {secteurs.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-slate-500 self-center">{t('marches.sectorLabel')}</span>
            {secteurs.map(s => (
              <button
                key={s}
                onClick={() => setFiltreSecteur(filtreSecteur === s ? "" : s)}
                className={`px-3 py-1 text-xs rounded-lg border transition-colors ${
                  filtreSecteur === s
                    ? "bg-blue-600/30 border-blue-500/60 text-blue-300 font-semibold"
                    : "bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Source chips */}
        {sources.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-slate-500 self-center">{t('marches.sourceLabel')}</span>
            {sources.map(s => (
              <button
                key={s}
                onClick={() => setFiltreSource(filtreSource === s ? "" : s)}
                className={`px-3 py-1 text-xs rounded-lg border transition-colors ${
                  filtreSource === s
                    ? "bg-blue-600/30 border-blue-500/60 text-blue-300 font-semibold"
                    : "bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Sources actives */}
      <div className="rounded-2xl p-4" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
        <button
          onClick={() => setShowSources(!showSources)}
          className="w-full flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-2">
            <Globe size={15} className="text-blue-400" />
            <span className="text-slate-300 text-sm font-semibold">{t('marches.sourcesActiveTitle')}</span>
          </div>
          <span className="text-slate-500 text-xs">{showSources ? t('marches.hideLabel') : t('marches.showLabel')}</span>
        </button>
        {showSources && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-400">
            {[
              { nom: "dgMarket (Banque Mondiale)", gratuit: true, desc: "Marchés internationaux Afrique" },
              { nom: "UNGM (Nations Unies)", gratuit: true, desc: "Appels d'offres ONU/ONG" },
              { nom: "ARMP-CM / ARMP-CI / DGMP-SN", gratuit: true, desc: "Plateformes ARMP nationales" },
              { nom: "SerpAPI Google Search", gratuit: false, desc: "LinkedIn, portails gouvernementaux (clé API requise)" },
            ].map((s) => (
              <div key={s.nom} className="flex items-start gap-2 p-2 bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-transparent rounded-lg">
                <span className={`mt-0.5 text-xs font-bold ${s.gratuit ? "text-emerald-400" : "text-amber-400"}`}>
                  {s.gratuit ? "✓" : "⚙"}
                </span>
                <div>
                  <p className="text-slate-300 font-medium">{s.nom}</p>
                  <p className="text-slate-500">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Fréquence */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-slate-400 text-sm font-semibold flex items-center gap-1">
          <Bell size={14} className="text-blue-400" /> {t('marches.updateFreq')}
        </span>
        {FREQUENCES.map((f) => (
          <button
            key={f.val}
            onClick={() => setFrequence(f.val)}
            className={`px-3 py-1.5 text-xs rounded-lg border transition-colors
              ${frequence === f.val
                ? "bg-[#0054A6] dark:bg-blue-600/30 border-[#0054A6] dark:border-blue-500/60 text-white dark:text-blue-300 font-semibold"
                : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-500"}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Liste des appels d'offres */}
      {marches.length === 0 ? (
        <div className="rounded-2xl p-10 text-center space-y-4" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
          <div className="w-14 h-14 bg-blue-500/10 rounded-2xl flex items-center justify-center mx-auto">
            <Gavel className="text-blue-400" size={28} />
          </div>
          <div>
            <p className="text-white font-semibold">{t('marches.noMarchesLoaded')}</p>
            <p className="text-slate-400 text-sm mt-1">{t('marches.noMarchesLoadedDesc')}</p>
          </div>
          <button
            onClick={lancerRecherche}
            disabled={searching}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold rounded-xl transition-colors text-sm"
          >
            {searching ? <RefreshCw size={15} className="animate-spin" /> : <Zap size={15} />}
            {searching ? t('common.loading') : t('marches.launchSearchNow')}
          </button>
        </div>
      ) : marchesFiltres.length === 0 ? (
        <div className="rounded-2xl p-8 text-center space-y-3" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
          <p className="text-white font-semibold">{t('marches.noFilterResults')}</p>
          <p className="text-slate-400 text-sm">{t('marches.noFilterResultsDesc')}</p>
          <button
            onClick={() => { setKeyword(""); setFiltreSecteur(""); setFiltreSource(""); }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded-xl transition-colors"
          >
            <X size={14} /> {t('marches.deleteFilters')}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {marchesFiltres.map((m, i) => (
            <div
              key={i}
              className="hover:border-blue-500/30 rounded-2xl p-5 transition-colors"
              style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}
            >
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Gavel className="text-blue-400" size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-white font-semibold leading-snug">{m.titre}</p>
                    {m.source_type === "simule" && (
                      <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-400 whitespace-nowrap">
                        Yukpo IA
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-3 mt-2">
                    {m.organisme && (
                      <span className="flex items-center gap-1 text-xs text-slate-400">
                        <Building2 size={12} />{m.organisme}
                      </span>
                    )}
                    {m.lieu && (
                      <span className="flex items-center gap-1 text-xs text-slate-400">
                        <MapPin size={12} />{m.lieu}
                      </span>
                    )}
                    {m.date_pub && (
                      <span className="flex items-center gap-1 text-xs text-slate-500">
                        <Calendar size={12} />{formatDate(m.date_pub)}
                      </span>
                    )}
                    {m.source && (
                      <button
                        onClick={() => setFiltreSource(filtreSource === m.source ? "" : m.source!)}
                        className={`px-2 py-0.5 border text-xs rounded-full transition-colors cursor-pointer
                          ${filtreSource === m.source
                            ? "bg-blue-600/30 border-blue-500/60 text-blue-300"
                            : "bg-blue-500/10 border-blue-500/20 text-blue-400/80 hover:bg-blue-500/20"}`}
                      >
                        {m.source}
                      </button>
                    )}
                    {m.secteur && (
                      <button
                        onClick={() => setFiltreSecteur(filtreSecteur === m.secteur ? "" : m.secteur!)}
                        className={`px-2 py-0.5 text-xs rounded-full transition-colors cursor-pointer
                          ${filtreSecteur === m.secteur
                            ? "bg-blue-600/30 border border-blue-500/40 text-blue-300"
                            : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}
                      >
                        {m.secteur}
                      </button>
                    )}
                  </div>
                  {m.resume && (
                    <p className="text-slate-400 text-sm mt-2 leading-relaxed line-clamp-2">{m.resume}</p>
                  )}
                </div>
                {m.url && (
                  <a
                    href={m.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 bg-blue-600/20 hover:bg-blue-600/40 border border-blue-500/30 text-blue-400 text-xs font-semibold rounded-xl transition-colors mt-0.5"
                  >
                    <ExternalLink size={13} />
                    {t('marches.viewLink')}
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default MarchesPage;
