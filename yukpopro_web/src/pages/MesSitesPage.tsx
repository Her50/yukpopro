/**
 * MesSitesPage — YukpoPro (Phase C)
 *
 * Liste les mini-sites multi-pages générés par le user :
 *   • Statut brouillon / publié
 *   • Bouton "Publier" (déclenche déploiement Netlify)
 *   • Lien vers le site live
 *   • Bouton supprimer
 *
 * Génération initiale = via le chat ("génère un site 5 pages pour…").
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft, ExternalLink, FileText, Globe, Loader2,
  RefreshCw, Send, Trash2,
} from "lucide-react";
import toast from "react-hot-toast";
import { generateurApi } from "@/api/client";

type SiteRow = {
  id: number; slug: string; nom: string; statut: string;
  plan: string; url_public: string | null;
  cree_le: string; publie_le: string | null; derniere_modif: string;
};

export const MesSitesPage = () => {
  const { t } = useTranslation();
  const [sites, setSites] = useState<SiteRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let annule = false;
    setLoading(true);
    generateurApi.listerSites()
      .then(r => { if (!annule) setSites(r.sites); })
      .catch((e: any) => {
        if (annule) return;
        toast.error(e?.response?.data?.detail || e?.message || "Erreur");
      })
      .finally(() => { if (!annule) setLoading(false); });
    return () => { annule = true; };
  }, [refreshTick]);

  const onPublier = async (slug: string) => {
    setBusy(slug);
    try {
      const r = await generateurApi.publierSite(slug, "free");
      toast.success(t("sites.publie", "Site publié !"));
      window.open(r.url_public, "_blank");
      setRefreshTick(t => t + 1);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally {
      setBusy(null);
    }
  };

  const onSupprimer = async (slug: string) => {
    if (!confirm(t("sites.confirm_delete", "Supprimer définitivement ce site ?"))) return;
    setBusy(slug);
    try {
      await generateurApi.supprimerSite(slug);
      toast.success(t("sites.supprime", "Site supprimé"));
      setRefreshTick(t => t + 1);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-6">
        <div>
          <Link to="/chat" className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 mb-2">
            <ArrowLeft className="w-4 h-4" />
            {t("commun.retour_chat", "Retour au chat")}
          </Link>
          <h1 className="text-2xl md:text-3xl font-bold flex items-center gap-2">
            <Globe className="w-6 h-6 text-violet-600" />
            {t("sites.titre", "Mes mini-sites multi-pages")}
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {t("sites.sous_titre",
               "Sites vitrines générés par chat. Pour en créer un nouveau, "
               + "tapez « génère un site 5 pages pour … » dans le chat.")}
          </p>
        </div>
        <button
          onClick={() => setRefreshTick(t => t + 1)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium min-h-[44px]"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          {t("sites.refresh", "Rafraîchir")}
        </button>
      </div>

      {loading && sites.length === 0 && (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-violet-600" />
        </div>
      )}

      {!loading && sites.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center">
          <Globe className="w-12 h-12 mx-auto text-slate-300 mb-3" />
          <p className="text-slate-500">
            {t("sites.vide",
               "Aucun site pour l'instant. Tapez dans le chat : "
               + "« génère un site 5 pages pour mon cabinet d'expertise comptable Douala ».")}
          </p>
          <Link to="/chat" className="inline-block mt-4 px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium">
            {t("sites.aller_chat", "Aller au chat")}
          </Link>
        </div>
      )}

      <div className="space-y-3">
        {sites.map(s => (
          <div key={s.slug}
               className="bg-white border border-slate-200 rounded-xl p-4 hover:shadow-md transition-shadow">
            <div className="flex flex-col md:flex-row md:items-start gap-3">
              <div className="flex-grow">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <h2 className="font-bold text-lg text-slate-900">{s.nom}</h2>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    s.statut === "publie"
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-amber-100 text-amber-800"
                  }`}>
                    {s.statut === "publie"
                      ? t("sites.statut.publie", "Publié")
                      : t("sites.statut.brouillon", "Brouillon")}
                  </span>
                  <span className="text-xs text-slate-400">·</span>
                  <span className="text-xs text-slate-500">{s.slug}.yukpomnang.com</span>
                </div>
                {s.url_public && (
                  <a href={s.url_public} target="_blank" rel="noopener"
                     className="inline-flex items-center gap-1 text-sm text-violet-700 hover:underline mb-1">
                    <ExternalLink className="w-3.5 h-3.5" />{s.url_public}
                  </a>
                )}
                <div className="text-xs text-slate-500 mt-1">
                  {t("sites.cree_le", "Créé le")} {new Date(s.cree_le).toLocaleDateString()}
                  {s.publie_le && (
                    <> · {t("sites.publie_le", "Publié le")} {new Date(s.publie_le).toLocaleDateString()}</>
                  )}
                </div>
              </div>
              <div className="flex flex-row md:flex-col gap-2 flex-shrink-0">
                {s.statut !== "publie" ? (
                  <button
                    onClick={() => onPublier(s.slug)}
                    disabled={busy === s.slug}
                    className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white text-xs font-medium min-h-[44px]"
                  >
                    {busy === s.slug
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <Send className="w-4 h-4" />}
                    {t("sites.publier", "Publier")}
                  </button>
                ) : (
                  <button
                    onClick={() => onPublier(s.slug)}
                    disabled={busy === s.slug}
                    className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-xs font-medium min-h-[44px]"
                  >
                    {busy === s.slug
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <RefreshCw className="w-4 h-4" />}
                    {t("sites.republier", "Re-publier")}
                  </button>
                )}
                <Link
                  to={`/mes-sites/${s.slug}`}
                  className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium min-h-[44px]"
                >
                  <FileText className="w-4 h-4" />
                  {t("sites.editer", "Éditer")}
                </Link>
                <button
                  onClick={() => onSupprimer(s.slug)}
                  disabled={busy === s.slug}
                  className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-rose-100 hover:bg-rose-200 disabled:opacity-50 text-rose-700 text-xs font-medium min-h-[44px]"
                  title={t("sites.supprimer", "Supprimer")}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
