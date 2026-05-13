/**
 * Onglets avancés YukpoShop (Phase D6 + D7 + D8 + D9).
 *
 * 4 composants standalone, montés dans MaBoutiquePage.tsx selon le tab actif.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle, BarChart3, Building, Check, Download,
  Facebook, Instagram, Loader2, MapPin, MessageCircle, Package2,
  PlusCircle, RefreshCw, Sparkles, Tag, TrendingDown, TrendingUp,
  Trash2, Truck, UserPlus, Users, Wand2,
} from "lucide-react";
import toast from "react-hot-toast";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { generateurApi } from "@/api/client";

// ─── Onglet D6 — Social (Meta Catalog, FB posts, IG, WA Business) ─────────

export const OngletSocial = () => {
  const { t } = useTranslation();
  const [integrations, setIntegrations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await generateurApi.shopSocialList();
      setIntegrations(res.integrations || []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const onConnectMeta = async () => {
    setBusy(true);
    try {
      const { oauth_url } = await generateurApi.shopSocialOAuthUrl();
      window.location.href = oauth_url;
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (typeof detail === "string" && detail.includes("non configuré")) {
        toast.error("META_FB_APP_ID non configuré côté serveur Yukpo. Configuration admin requise.", { duration: 8000 });
      } else {
        toast.error(detail || e?.message || "Erreur");
      }
    } finally { setBusy(false); }
  };

  const onSyncCatalog = async () => {
    setBusy(true);
    try {
      const r = await generateurApi.shopSocialSyncCatalog();
      toast.success(`${r.nb_sync_ok || 0} produits synchronisés${r.nb_sync_erreur ? ` (${r.nb_sync_erreur} erreurs)` : ""}`);
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally { setBusy(false); }
  };

  const hasMeta = integrations.find(i => i.platform === "meta_fb" && i.statut === "actif");

  return (
    <div>
      <div className="bg-gradient-to-br from-blue-50 to-pink-50 border border-blue-200 rounded-xl p-5 mb-6">
        <h2 className="font-bold text-lg text-blue-900 mb-2 flex items-center gap-2">
          <Facebook className="w-5 h-5" /><Instagram className="w-5 h-5 text-pink-600" />
          {t("shop.social_titre", "Connexion sociale (Meta + TikTok)")}
        </h2>
        <p className="text-sm text-blue-800 mb-3">
          {t("shop.social_aide",
             "Connectez vos comptes pour synchroniser vos produits vers Facebook Shops + "
             + "Instagram Shopping, publier automatiquement à chaque nouveau produit, "
             + "et gérer les commandes WhatsApp Business depuis YukpoPro.")}
        </p>
        <div className="flex flex-wrap gap-2">
          {!hasMeta ? (
            <button onClick={onConnectMeta} disabled={busy}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium min-h-[44px] disabled:opacity-50">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Facebook className="w-4 h-4" />}
              {t("shop.social_connect_meta", "Connecter Meta Business")}
            </button>
          ) : (
            <button onClick={onSyncCatalog} disabled={busy}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white font-medium min-h-[44px] disabled:opacity-50">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              {t("shop.social_sync_catalog", "Synchroniser catalogue Meta")}
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-violet-600" /></div>
      ) : integrations.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
          <Facebook className="w-12 h-12 mx-auto text-slate-300 mb-3" />
          <p className="text-slate-500">{t("shop.social_vide", "Aucune intégration sociale connectée.")}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {integrations.map(i => (
            <div key={i.id} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <div className="text-3xl">
                  {i.platform === "meta_fb" ? "📘" : i.platform === "meta_ig" ? "📸" :
                   i.platform === "tiktok_shop" ? "🎵" : "💬"}
                </div>
                <div className="flex-grow">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-slate-900">{i.platform}</h3>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      i.statut === "actif" ? "bg-emerald-100 text-emerald-700" :
                      i.statut === "expire" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"
                    }`}>{i.statut}</span>
                  </div>
                  {i.compte_username && <p className="text-sm text-slate-600 mt-1">{i.compte_username}</p>}
                  {i.derniere_sync && (
                    <p className="text-xs text-slate-500 mt-1">
                      Sync : {new Date(i.derniere_sync).toLocaleString()}
                    </p>
                  )}
                  {i.catalog_id && (
                    <p className="text-xs text-slate-500 mt-1">Catalog ID : {i.catalog_id}</p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Onglet D7 — ROAS Pubs ────────────────────────────────────────────────

export const OngletROAS = () => {
  const { t } = useTranslation();
  const [data, setData] = useState<any>(null);
  const [recos, setRecos] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [jours, setJours] = useState(30);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await generateurApi.shopAdsDashboard(jours);
      setData(r);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally { setLoading(false); }
  }, [jours]);

  useEffect(() => { refresh(); }, [refresh]);

  const onSync = async () => {
    setBusy("sync");
    try {
      const r = await generateurApi.shopAdsSync();
      if (!r.ok) toast(r.message || "Aucune plateforme connectée", { icon: "⚠️" });
      else toast.success(`✓ ${r.nb_metrics_synced || 0} métriques synchronisées`);
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally { setBusy(null); }
  };

  const onRecos = async () => {
    setBusy("recos");
    toast.loading("Analyse IA Opus…", { id: "recos" });
    try {
      const r = await generateurApi.shopAdsRecommandations(jours);
      setRecos(r.recommandations_md || "");
      toast.success("✓ Recommandations générées", { id: "recos" });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur", { id: "recos" });
    } finally { setBusy(null); }
  };

  const global = data?.global || {};
  const meilleur = data?.meilleur_roas;
  const pire = data?.pire_roas;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select value={jours} onChange={e => setJours(Number(e.target.value))}
                className="px-3 py-2 rounded-lg border border-slate-300 text-sm min-h-[44px]">
          <option value={7}>7 jours</option>
          <option value={30}>30 jours</option>
          <option value={90}>90 jours</option>
          <option value={365}>1 an</option>
        </select>
        <button onClick={onSync} disabled={busy === "sync"}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium min-h-[44px] disabled:opacity-50">
          {busy === "sync" ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          {t("shop.ads_sync", "Synchroniser FB Ads")}
        </button>
        <button onClick={onRecos} disabled={busy === "recos" || !data?.par_campagne?.length}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium min-h-[44px] disabled:opacity-50">
          {busy === "recos" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {t("shop.ads_recos", "Recos IA Opus")}
        </button>
      </div>

      {loading ? (
        <Loader2 className="w-6 h-6 animate-spin text-violet-600 mx-auto my-8" />
      ) : (
        <>
          {/* KPIs globaux */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <KpiCard label={t("shop.ads_depenses", "Dépenses")}
                     valeur={`${Math.round(global.depenses || 0)}`}
                     suffix="FCFA" tone="slate" />
            <KpiCard label={t("shop.ads_revenu", "Revenu")}
                     valeur={`${Math.round(global.revenu_local || 0)}`}
                     suffix="FCFA" tone="emerald" />
            <KpiCard label="ROAS"
                     valeur={global.roas ? `×${global.roas}` : "—"}
                     tone={!global.roas ? "slate" : global.roas >= 2 ? "emerald" : global.roas >= 1 ? "amber" : "rose"} />
            <KpiCard label={t("shop.ads_conversions", "Conversions")}
                     valeur={String(global.conversions_locales || 0)} tone="violet" />
          </div>

          {/* Meilleur / Pire */}
          {(meilleur || pire) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
              {meilleur && <RoasCard titre={t("shop.ads_meilleur", "🏆 Meilleure campagne")}
                                      campagne={meilleur} tone="emerald" />}
              {pire && <RoasCard titre={t("shop.ads_pire", "⚠️ Pire campagne")}
                                  campagne={pire} tone="rose" />}
            </div>
          )}

          {/* Recommandations IA */}
          {recos && (
            <div className="bg-violet-50 border border-violet-200 rounded-xl p-5 mb-6">
              <h3 className="font-bold text-violet-900 mb-3 flex items-center gap-2">
                <Sparkles className="w-4 h-4" /> {t("shop.ads_recos_titre", "Recommandations IA Opus")}
              </h3>
              <div className="prose prose-sm max-w-none text-slate-800">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{recos}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* Table campagnes */}
          {data?.par_campagne?.length ? (
            <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="text-left p-3">{t("shop.ads_campagne", "Campagne")}</th>
                    <th className="text-right p-3">Dép.</th>
                    <th className="text-right p-3">Imp.</th>
                    <th className="text-right p-3">Clics</th>
                    <th className="text-right p-3">CTR</th>
                    <th className="text-right p-3">Conv.</th>
                    <th className="text-right p-3">Rev.</th>
                    <th className="text-right p-3">ROAS</th>
                  </tr>
                </thead>
                <tbody>
                  {data.par_campagne.map((c: any) => (
                    <tr key={c.campagne_id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="p-3 font-medium">{c.campagne_nom || c.campagne_id}</td>
                      <td className="p-3 text-right">{Math.round(c.depenses)}</td>
                      <td className="p-3 text-right">{c.impressions}</td>
                      <td className="p-3 text-right">{c.clics}</td>
                      <td className="p-3 text-right">{c.ctr_pct}%</td>
                      <td className="p-3 text-right">{c.conversions_locales}</td>
                      <td className="p-3 text-right">{Math.round(c.revenu_local)}</td>
                      <td className={`p-3 text-right font-bold ${
                        !c.roas ? "" : c.roas >= 2 ? "text-emerald-700" : c.roas >= 1 ? "text-amber-700" : "text-rose-700"
                      }`}>
                        {c.roas ? `×${c.roas}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
              <BarChart3 className="w-12 h-12 mx-auto text-slate-300 mb-3" />
              <p className="text-slate-500">
                {t("shop.ads_vide",
                   "Aucune donnée. Connectez Facebook Ads et synchronisez.")}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const KpiCard = ({ label, valeur, suffix, tone = "slate" }: {
  label: string; valeur: string; suffix?: string;
  tone?: "slate" | "emerald" | "violet" | "amber" | "rose";
}) => {
  const tones: Record<string, string> = {
    slate: "bg-slate-50 text-slate-900",
    emerald: "bg-emerald-50 text-emerald-900",
    violet: "bg-violet-50 text-violet-900",
    amber: "bg-amber-50 text-amber-900",
    rose: "bg-rose-50 text-rose-900",
  };
  return (
    <div className={`rounded-xl p-4 ${tones[tone]}`}>
      <div className="text-xs uppercase tracking-wider opacity-70 mb-1">{label}</div>
      <div className="text-2xl font-bold">{valeur} {suffix && <span className="text-sm font-normal opacity-70">{suffix}</span>}</div>
    </div>
  );
};

const RoasCard = ({ titre, campagne, tone }: {
  titre: string; campagne: any; tone: "emerald" | "rose";
}) => (
  <div className={`rounded-xl p-4 ${tone === "emerald" ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"} border`}>
    <div className="text-sm font-semibold mb-2">{titre}</div>
    <div className="font-bold text-slate-900 truncate">{campagne.campagne_nom || campagne.campagne_id}</div>
    <div className="flex justify-between mt-2 text-sm">
      <span>ROAS</span>
      <span className="font-bold">{campagne.roas ? `×${campagne.roas}` : "—"}</span>
    </div>
    <div className="flex justify-between text-sm">
      <span>Dépense</span><span>{Math.round(campagne.depenses)}</span>
    </div>
    <div className="flex justify-between text-sm">
      <span>Revenu</span><span>{Math.round(campagne.revenu_local)}</span>
    </div>
  </div>
);

// ─── Onglet D8 — CRM clients ──────────────────────────────────────────────

export const OngletCRM = () => {
  const { t } = useTranslation();
  const [clients, setClients] = useState<any[]>([]);
  const [segment, setSegment] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await generateurApi.shopCrmClients({ segment: segment || undefined, limit: 100 });
      setClients(r.clients || []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally { setLoading(false); }
  }, [segment]);

  useEffect(() => { refresh(); }, [refresh]);

  const onAgreger = async () => {
    setBusy("agreger");
    toast.loading("Agrégation depuis commandes…", { id: "ag" });
    try {
      const r = await generateurApi.shopCrmAgreger();
      toast.success(`✓ ${r.nb_clients_traites} clients agrégés`, { id: "ag" });
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur", { id: "ag" });
    } finally { setBusy(null); }
  };

  const onScorer = async () => {
    setBusy("scorer");
    toast.loading("Scoring IA Sonnet…", { id: "sc" });
    try {
      const r = await generateurApi.shopCrmScorer(50);
      toast.success(`✓ ${r.nb_clients_scores} clients scorés`, { id: "sc" });
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur", { id: "sc" });
    } finally { setBusy(null); }
  };

  const onRelancer = async (id: number, nom: string) => {
    const message = prompt(`Message WhatsApp pour ${nom} :`, "Bonjour, nous vous proposons une promo exclusive…");
    if (!message) return;
    try {
      const r = await generateurApi.shopCrmRelancer(id, message);
      if (r.ok) toast.success("✓ Relance envoyée (WA/SMS)");
      else toast.error("Échec envoi");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    }
  };

  const segmentColors: Record<string, string> = {
    vip: "bg-violet-100 text-violet-800",
    recurrent: "bg-emerald-100 text-emerald-800",
    new: "bg-blue-100 text-blue-800",
    risque: "bg-amber-100 text-amber-800",
    dormant: "bg-slate-100 text-slate-600",
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select value={segment} onChange={e => setSegment(e.target.value)}
                className="px-3 py-2 rounded-lg border border-slate-300 text-sm min-h-[44px]">
          <option value="">{t("shop.crm_tous", "Tous segments")}</option>
          <option value="vip">VIP</option>
          <option value="recurrent">Récurrent</option>
          <option value="new">Nouveau</option>
          <option value="risque">À risque</option>
          <option value="dormant">Dormant</option>
        </select>
        <button onClick={onAgreger} disabled={busy === "agreger"}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium min-h-[44px] disabled:opacity-50">
          {busy === "agreger" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Users className="w-4 h-4" />}
          {t("shop.crm_agreger", "Agréger commandes → clients")}
        </button>
        <button onClick={onScorer} disabled={busy === "scorer"}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium min-h-[44px] disabled:opacity-50">
          {busy === "scorer" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {t("shop.crm_scorer", "Scorer churn IA (50)")}
        </button>
      </div>

      {loading ? (
        <Loader2 className="w-6 h-6 animate-spin text-violet-600 mx-auto my-8" />
      ) : clients.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
          <Users className="w-12 h-12 mx-auto text-slate-300 mb-3" />
          <p className="text-slate-500">
            {t("shop.crm_vide", "Aucun client. Lancez l'agrégation depuis vos commandes.")}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {clients.map(c => (
            <div key={c.id} className="bg-white border border-slate-200 rounded-xl p-3 flex flex-wrap items-center gap-3">
              <div className="flex-grow min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <strong className="text-slate-900">{c.nom || c.telephone || c.email || `Client #${c.id}`}</strong>
                  {c.segment && (
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${segmentColors[c.segment] || "bg-slate-100"}`}>
                      {c.segment}
                    </span>
                  )}
                  {c.score_churn_pct !== null && c.score_churn_pct !== undefined && (
                    <span className={`text-xs font-medium ${c.score_churn_pct > 60 ? "text-rose-700" : c.score_churn_pct > 30 ? "text-amber-700" : "text-emerald-700"}`}>
                      churn {c.score_churn_pct}%
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {c.telephone} {c.email && `· ${c.email}`}
                  {" · "}{c.nb_commandes} cmd · {Math.round(c.revenu_total)} {c.devise || "XAF"}
                  {c.ltv_predite && ` · LTV ~${Math.round(c.ltv_predite)}`}
                </div>
              </div>
              {c.telephone && (
                <button onClick={() => onRelancer(c.id, c.nom || c.telephone)}
                        className="inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-xs font-medium min-h-[44px]">
                  <MessageCircle className="w-4 h-4" />
                  {t("shop.crm_relancer", "Relancer")}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Onglet D9 — Livraison ────────────────────────────────────────────────

export const OngletLivraison = () => {
  const { t } = useTranslation();
  const [zones, setZones] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    nom: "", villes: "", regions: "", pays: "",
    tarif: 0, devise: "XAF",
    delai_min: 1, delai_max: 3,
    transporteur_prefere: "local_whatsapp",
  });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await generateurApi.shopLivraisonZones();
      setZones(r.zones || []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const onCreer = async () => {
    if (!form.nom.trim()) return toast.error("Nom requis");
    setBusy(true);
    try {
      await generateurApi.shopLivraisonCreerZone({
        nom: form.nom,
        villes_json: form.villes ? form.villes.split(",").map(s => s.trim()).filter(Boolean) : undefined,
        regions_json: form.regions ? form.regions.split(",").map(s => s.trim()).filter(Boolean) : undefined,
        pays_json: form.pays ? form.pays.split(",").map(s => s.trim().toUpperCase()).filter(Boolean) : undefined,
        tarif: form.tarif, devise: form.devise,
        delai_jours_min: form.delai_min, delai_jours_max: form.delai_max,
        transporteur_prefere: form.transporteur_prefere,
      });
      toast.success("✓ Zone créée");
      setShowForm(false);
      setForm({ nom: "", villes: "", regions: "", pays: "", tarif: 0, devise: "XAF", delai_min: 1, delai_max: 3, transporteur_prefere: "local_whatsapp" });
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally { setBusy(false); }
  };

  const onSupprimer = async (id: number) => {
    if (!confirm("Supprimer cette zone ?")) return;
    try {
      await generateurApi.shopLivraisonSupprimerZone(id);
      toast.success("Zone supprimée");
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="font-bold text-lg text-slate-900">
            {t("shop.livraison_titre", "Zones de livraison")}
          </h2>
          <p className="text-sm text-slate-600">
            {t("shop.livraison_aide",
               "Définissez vos tarifs par ville/région/pays. Le matching se fait par priorité ville > région > pays > fallback.")}
          </p>
        </div>
        <button onClick={() => setShowForm(!showForm)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium min-h-[44px]">
          <PlusCircle className="w-4 h-4" />
          {showForm ? "Fermer" : t("shop.livraison_creer", "Créer zone")}
        </button>
      </div>

      {showForm && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-4 space-y-3">
          <input type="text" placeholder="Nom zone (ex: 'Douala intra-muros')"
                 value={form.nom} onChange={e => setForm({ ...form, nom: e.target.value })}
                 className="w-full px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]" />
          <input type="text" placeholder="Villes (séparées par virgules) — ex: Douala, Bonabéri"
                 value={form.villes} onChange={e => setForm({ ...form, villes: e.target.value })}
                 className="w-full px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]" />
          <input type="text" placeholder="Régions (optionnel)"
                 value={form.regions} onChange={e => setForm({ ...form, regions: e.target.value })}
                 className="w-full px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]" />
          <input type="text" placeholder="Pays (codes ISO ex: CM, CI, SN)"
                 value={form.pays} onChange={e => setForm({ ...form, pays: e.target.value })}
                 className="w-full px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]" />
          <div className="grid grid-cols-2 gap-3">
            <input type="number" placeholder="Tarif" value={form.tarif}
                   onChange={e => setForm({ ...form, tarif: Number(e.target.value) })}
                   className="px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]" />
            <select value={form.devise} onChange={e => setForm({ ...form, devise: e.target.value })}
                    className="px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]">
              <option>XAF</option><option>XOF</option><option>NGN</option><option>EUR</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input type="number" placeholder="Délai min (jours)" value={form.delai_min}
                   onChange={e => setForm({ ...form, delai_min: Number(e.target.value) })}
                   className="px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]" />
            <input type="number" placeholder="Délai max (jours)" value={form.delai_max}
                   onChange={e => setForm({ ...form, delai_max: Number(e.target.value) })}
                   className="px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]" />
          </div>
          <select value={form.transporteur_prefere}
                  onChange={e => setForm({ ...form, transporteur_prefere: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 min-h-[44px]">
            <option value="local_whatsapp">Livreur local (coordination WhatsApp)</option>
            <option value="dhl">DHL Express</option>
            <option value="speedaf">Speedaf</option>
            <option value="bollore">Bolloré Logistics</option>
          </select>
          <button onClick={onCreer} disabled={busy}
                  className="w-full px-5 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white font-medium min-h-[44px] disabled:opacity-50">
            {busy ? <Loader2 className="w-4 h-4 animate-spin inline mr-2" /> : null}
            {t("shop.livraison_valider", "Créer la zone")}
          </button>
        </div>
      )}

      {loading ? (
        <Loader2 className="w-6 h-6 animate-spin text-violet-600 mx-auto my-8" />
      ) : zones.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
          <Truck className="w-12 h-12 mx-auto text-slate-300 mb-3" />
          <p className="text-slate-500">
            {t("shop.livraison_vide", "Aucune zone configurée. Créez-en au moins une pour calculer les frais de livraison.")}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {zones.map(z => (
            <div key={z.id} className="bg-white border border-slate-200 rounded-xl p-3 flex items-center gap-3">
              <MapPin className="w-5 h-5 text-violet-600 flex-shrink-0" />
              <div className="flex-grow min-w-0">
                <strong className="text-slate-900">{z.nom}</strong>
                <div className="text-xs text-slate-500 mt-1">
                  {[
                    z.villes?.length ? `🏙️ ${z.villes.join(", ")}` : null,
                    z.regions?.length ? `🗺️ ${z.regions.join(", ")}` : null,
                    z.pays?.length ? `🌍 ${z.pays.join(", ")}` : null,
                  ].filter(Boolean).join(" · ") || "Catch-all"}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  💰 {z.tarif} {z.devise} · ⏱️ {z.delai_min}-{z.delai_max}j · 🚚 {z.transporteur_prefere}
                </div>
              </div>
              <button onClick={() => onSupprimer(z.id)}
                      className="p-2 rounded-lg bg-rose-100 hover:bg-rose-200 text-rose-700 min-h-[44px] min-w-[44px]">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
