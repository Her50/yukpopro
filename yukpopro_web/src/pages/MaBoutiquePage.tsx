/**
 * MaBoutiquePage — YukpoPro (Phase D)
 *
 * Dashboard boutique e-commerce :
 *   • Init boutique si pas encore créée
 *   • Liste produits avec magic import IA (1-clic)
 *   • Liste commandes
 *   • Bouton publier (déploie storefront sur Netlify)
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft, BarChart3, ExternalLink, Facebook, Image as ImageIcon,
  Loader2, MapPin, MessageSquare, Package, RefreshCw, Send, Shield,
  ShoppingCart, Sparkles, Star, Trash2, Truck, Upload, Users, Video,
  Wand2, Globe, AlertTriangle, ChevronRight, X,
} from "lucide-react";
import toast from "react-hot-toast";
import { generateurApi } from "@/api/client";
import {
  OngletCRM, OngletLivraison, OngletROAS, OngletSocial,
} from "./maboutique/OngletsAvances";

type Produit = {
  id: number; titre: string; slug: string;
  prix_unit: number; devise: string; stock: number;
  photos_urls_json: string[] | null;
  statut: string; source: string;
  // Piste 6 — enrichissements Yukpo Rust (peuvent être null si Rust pas déployé)
  yukpo_category?: string | null;
  yukpo_specialized_type?: string | null;
  yukpo_tags_json?: string[] | null;
  yukpo_description_enriched?: string | null;
  yukpo_quality_score?: number | null;
  yukpo_language_detected?: string | null;
  yukpo_enriched_at?: string | null;
  yukpo_ai_moderation_status?: string | null;
  yukpo_ai_moderation_reason?: string | null;
  // Piste 6b — vidéo VideoFeed mobile Yukpo
  video_url?: string | null;
  video_thumbnail_url?: string | null;
  // Piste 1 — sync state
  rust_service_id?: number | null;
  rust_sync_status?: string | null;
};
type Commande = {
  id: number; numero: string;
  client_nom: string; client_telephone: string;
  montant_total: number; devise: string;
  statut: string; cree_le: string;
};

export const MaBoutiquePage = () => {
  const { t } = useTranslation();
  const [boutique, setBoutique] = useState<any>(null);
  const [produits, setProduits] = useState<Produit[]>([]);
  const [commandes, setCommandes] = useState<Commande[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"produits" | "commandes" | "social" | "roas" | "crm" | "livraison" | "marketplace">("produits");
  const [busy, setBusy] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [importBrief, setImportBrief] = useState("");
  const [showInit, setShowInit] = useState(false);
  const [initForm, setInitForm] = useState({
    nom: "", description: "", devise: "XAF", pays_principal: "CM",
  });
  // Piste 6 — modal chat IA + onglet marketplace
  const [showChatCreator, setShowChatCreator] = useState(false);
  const [marketplaceStats, setMarketplaceStats] = useState<
    { stats: Record<string, number>; total: number; rust_sync_enabled: boolean } | null
  >(null);
  const [similarItems, setSimilarItems] = useState<{ produitId: number; items: any[] } | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const b = await generateurApi.shopMaBoutique();
      setBoutique(b);
      const p = await generateurApi.shopListerProduits({ limit: 100 });
      setProduits(p.produits || []);
      const c = await generateurApi.shopListerCommandes({ limit: 50 });
      setCommandes(c.commandes || []);
    } catch (e: any) {
      if (e?.response?.status === 404) setShowInit(true);
      else toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const onInit = async () => {
    if (!initForm.nom.trim()) return toast.error("Nom requis");
    setBusy("init");
    try {
      await generateurApi.shopInitialiser(initForm);
      toast.success("Boutique créée !");
      setShowInit(false);
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally { setBusy(null); }
  };

  const onMagicImport = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    if (files.length > 10) return toast.error("Max 10 photos");
    setBusy("magic");
    toast.loading(`Analyse de ${files.length} photo(s) par IA Yukpo Vision…`, { id: "magic" });
    try {
      const arr = Array.from(files);
      const res = await generateurApi.shopMagicImport(arr, {
        brief: importBrief, auto_save: true,
      });
      toast.success(`✓ "${res.produit.titre}" créé en brouillon`, { id: "magic" });
      setImportBrief("");
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur", { id: "magic" });
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onActiverProduit = async (id: number, statut: string) => {
    try {
      await generateurApi.shopPatchProduit(id, { statut: statut === "actif" ? "brouillon" : "actif" });
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    }
  };

  const onSupprimerProduit = async (id: number) => {
    if (!confirm(t("shop.confirm_delete_produit", "Supprimer ce produit ?"))) return;
    try {
      await generateurApi.shopSupprimerProduit(id);
      toast.success("Produit supprimé");
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    }
  };

  // Piste 6c — voir produits similaires dans le marketplace Yukpo
  const onShowSimilar = async (id: number) => {
    toast.loading("Recherche dans le marketplace Yukpo…", { id: "sim" });
    try {
      const res = await generateurApi.shopProduitsSimilaires(id, 6);
      setSimilarItems({ produitId: id, items: res.items || [] });
      toast.dismiss("sim");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur", { id: "sim" });
    }
  };

  // Piste 6e — re-enrichir la boutique via Google Places
  const onGoogleEnrich = async () => {
    const ville = prompt("Ville (optionnelle, améliore la précision Google Places) :", "");
    setBusy("gp");
    try {
      const res = await generateurApi.shopGoogleEnrich(ville || undefined);
      if (res.ok) {
        toast.success(
          res.adresse_complete
            ? `✓ ${res.adresse_complete}`
            : "Boutique enrichie",
        );
        await refresh();
      } else {
        toast(res.error || "Aucun résultat Google Places");
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur");
    } finally { setBusy(null); }
  };

  const onPublier = async () => {
    setBusy("publish");
    try {
      const res = await generateurApi.shopPublier();
      toast.success("Boutique publiée !");
      window.open(res.url_public, "_blank");
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || "Erreur");
    } finally { setBusy(null); }
  };

  if (loading && !boutique && !showInit) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-violet-600" />
      </div>
    );
  }

  if (showInit) {
    return (
      <div className="p-4 md:p-6 max-w-xl mx-auto">
        <Link to="/chat" className="inline-flex items-center gap-1 text-sm text-slate-600 mb-4">
          <ArrowLeft className="w-4 h-4" /> Retour au chat
        </Link>
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h1 className="text-2xl font-bold mb-2 flex items-center gap-2">
            <ShoppingCart className="w-6 h-6 text-violet-600" />
            {t("shop.init_titre", "Créer ma boutique en ligne")}
          </h1>
          <p className="text-sm text-slate-600 mb-6">
            {t("shop.init_aide",
               "Vous pourrez ajouter vos produits via magic import IA "
               + "(upload de photos), puis publier votre boutique en 1 clic.")}
          </p>
          <div className="space-y-3">
            <input type="text" placeholder={t("shop.init_nom", "Nom de la boutique") as string}
                   value={initForm.nom} onChange={e => setInitForm({ ...initForm, nom: e.target.value })}
                   className="w-full px-4 py-2.5 rounded-lg border border-slate-300 min-h-[44px]" />
            <textarea placeholder={t("shop.init_desc", "Description (optionnelle)") as string}
                      value={initForm.description}
                      onChange={e => setInitForm({ ...initForm, description: e.target.value })}
                      rows={3} className="w-full px-4 py-2.5 rounded-lg border border-slate-300" />
            <div className="grid grid-cols-2 gap-3">
              <select value={initForm.devise}
                      onChange={e => setInitForm({ ...initForm, devise: e.target.value })}
                      className="px-4 py-2.5 rounded-lg border border-slate-300 min-h-[44px]">
                <option value="XAF">XAF (FCFA Afrique centrale)</option>
                <option value="XOF">XOF (FCFA Ouest)</option>
                <option value="NGN">NGN (Naira)</option>
                <option value="MAD">MAD (Dirham)</option>
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
              </select>
              <select value={initForm.pays_principal}
                      onChange={e => setInitForm({ ...initForm, pays_principal: e.target.value })}
                      className="px-4 py-2.5 rounded-lg border border-slate-300 min-h-[44px]">
                <option value="CM">Cameroun</option>
                <option value="CI">Côte d'Ivoire</option>
                <option value="SN">Sénégal</option>
                <option value="BF">Burkina Faso</option>
                <option value="ML">Mali</option>
                <option value="TG">Togo</option>
                <option value="BJ">Bénin</option>
              </select>
            </div>
            <button onClick={onInit} disabled={busy === "init"}
                    className="w-full px-5 py-3 rounded-lg bg-violet-600 hover:bg-violet-700 text-white font-semibold min-h-[44px] disabled:opacity-50">
              {busy === "init" ? <Loader2 className="w-4 h-4 inline animate-spin mr-2" /> : null}
              {t("shop.init_creer", "Créer ma boutique")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-6">
        <div>
          <Link to="/chat" className="inline-flex items-center gap-1 text-sm text-slate-600 mb-2">
            <ArrowLeft className="w-4 h-4" /> {t("commun.retour_chat", "Retour au chat")}
          </Link>
          <h1 className="text-2xl md:text-3xl font-bold flex items-center gap-2">
            <ShoppingCart className="w-6 h-6 text-violet-600" />
            {boutique?.nom || t("shop.titre", "Ma boutique")}
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {boutique?.url_public ? (
              <a href={boutique.url_public} target="_blank" rel="noopener"
                 className="text-violet-700 hover:underline inline-flex items-center gap-1">
                {boutique.url_public} <ExternalLink className="w-3.5 h-3.5" />
              </a>
            ) : (
              <span>Slug pressenti : {boutique?.slug}.yukpomnang.com</span>
            )}
            {" · "}{boutique?.stats?.nb_produits || 0} produits · {boutique?.stats?.nb_commandes || 0} commandes
          </p>
          {/* Piste 6e — affichage Google Places enrichment */}
          {(boutique?.adresse_complete || boutique?.gps || boutique?.google_rating) && (
            <div className="mt-2 text-xs text-slate-600 inline-flex flex-wrap items-center gap-x-3 gap-y-1">
              {boutique?.adresse_complete && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="w-3.5 h-3.5 text-violet-600" />
                  {boutique.adresse_complete}
                </span>
              )}
              {typeof boutique?.google_rating === "number" && boutique.google_rating > 0 && (
                <span className="inline-flex items-center gap-0.5 text-amber-600">
                  <Star className="w-3 h-3 fill-amber-500" /> {boutique.google_rating.toFixed(1)}
                </span>
              )}
              <button onClick={onGoogleEnrich}
                      disabled={busy === "gp"}
                      className="text-[11px] text-violet-700 hover:underline inline-flex items-center gap-1">
                {busy === "gp" ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                {boutique?.adresse_complete ? "Mettre à jour" : "📍 Enrichir via Google Places"}
              </button>
            </div>
          )}
          {!boutique?.adresse_complete && boutique?.id && (
            <div className="mt-2">
              <button onClick={onGoogleEnrich}
                      disabled={busy === "gp"}
                      className="text-xs text-violet-700 hover:underline inline-flex items-center gap-1">
                {busy === "gp" ? <Loader2 className="w-3 h-3 animate-spin" /> : <MapPin className="w-3 h-3" />}
                Enrichir ma boutique via Google Places (adresse + GPS + rating)
              </button>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={refresh}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm min-h-[44px]">
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button onClick={onPublier} disabled={busy === "publish"}
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium min-h-[44px] disabled:opacity-50">
            {busy === "publish" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {boutique?.statut === "publie" ? t("shop.republier", "Re-publier") : t("shop.publier", "Publier")}
          </button>
        </div>
      </div>

      {/* Création produit — paradigme conversationnel (aligné Yukpo Rust ChatModal) */}
      <div className="bg-gradient-to-br from-violet-50 to-fuchsia-50 border border-violet-200 rounded-xl p-5 mb-6">
        <h2 className="font-bold text-lg text-violet-900 mb-2 flex items-center gap-2">
          <Wand2 className="w-5 h-5" />
          {t("shop.creator_titre", "Créer un produit — Assistant IA Yukpo")}
        </h2>
        <p className="text-sm text-violet-800 mb-3">
          {t("shop.creator_aide",
             "Pas de formulaire à remplir. Décris ton produit en quelques mots ET/OU "
             + "ajoute des photos. L'IA Yukpo compose automatiquement la fiche complète "
             + "(titre, description, prix, catégorie, tags, variantes, modération).")}
        </p>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setShowChatCreator(true)}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white font-semibold min-h-[44px]">
            <MessageSquare className="w-4 h-4" />
            {t("shop.creator_chat_btn", "Décrire mon produit (chat IA)")}
          </button>
          <input ref={fileRef} type="file" accept="image/*" multiple
                 onChange={e => onMagicImport(e.target.files)}
                 disabled={busy === "magic"} className="hidden" />
          <button onClick={() => fileRef.current?.click()} disabled={busy === "magic"}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-white hover:bg-violet-50 text-violet-700 font-semibold min-h-[44px] disabled:opacity-50 border border-violet-200">
            {busy === "magic" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {t("shop.creator_photos_btn", "Juste mes photos (Magic Vision)")}
          </button>
        </div>
        <p className="text-[11px] text-violet-700 mt-2 italic">
          💡 L'assistant chat permet d'avoir un échange (préciser le ton, variantes, contexte cible).
          Le mode photo seul est plus rapide si tes images parlent d'elles-mêmes.
        </p>
      </div>

      {/* Modal Chat Creator — Piste 6, aligné paradigme Rust ChatModal */}
      {showChatCreator && (
        <ChatCreatorModal
          onClose={() => setShowChatCreator(false)}
          onCreated={async () => {
            setShowChatCreator(false);
            await refresh();
          }}
        />
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-slate-200 overflow-x-auto">
        <TabBtn icon={<Package className="w-4 h-4" />} label={`${t("shop.tab_produits", "Produits")} (${produits.length})`}
                active={tab === "produits"} onClick={() => setTab("produits")} />
        <TabBtn icon={<ShoppingCart className="w-4 h-4" />} label={`${t("shop.tab_commandes", "Commandes")} (${commandes.length})`}
                active={tab === "commandes"} onClick={() => setTab("commandes")} />
        <TabBtn icon={<Facebook className="w-4 h-4" />} label={t("shop.tab_social", "Social")}
                active={tab === "social"} onClick={() => setTab("social")} />
        <TabBtn icon={<BarChart3 className="w-4 h-4" />} label={t("shop.tab_roas", "Pubs & ROI")}
                active={tab === "roas"} onClick={() => setTab("roas")} />
        <TabBtn icon={<Users className="w-4 h-4" />} label={t("shop.tab_crm", "CRM")}
                active={tab === "crm"} onClick={() => setTab("crm")} />
        <TabBtn icon={<Truck className="w-4 h-4" />} label={t("shop.tab_livraison", "Livraison")}
                active={tab === "livraison"} onClick={() => setTab("livraison")} />
        <TabBtn icon={<Globe className="w-4 h-4" />}
                label={t("shop.tab_marketplace", "Marketplace Yukpo")}
                active={tab === "marketplace"}
                onClick={async () => {
                  setTab("marketplace");
                  if (!marketplaceStats) {
                    try {
                      const s = await generateurApi.shopRustSyncStats();
                      setMarketplaceStats({
                        stats: s.stats, total: s.total,
                        rust_sync_enabled: s.rust_sync_enabled,
                      });
                    } catch { /* silently */ }
                  }
                }} />
      </div>

      {tab === "produits" && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {produits.length === 0 && (
            <div className="col-span-full bg-white border border-slate-200 rounded-xl p-12 text-center">
              <Package className="w-12 h-12 mx-auto text-slate-300 mb-3" />
              <p className="text-slate-500">{t("shop.vide_produits",
                "Aucun produit. Uploadez vos photos avec Magic Import IA ci-dessus.")}</p>
            </div>
          )}
          {produits.map(p => (
            <div key={p.id} className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md transition flex flex-col">
              <div className="relative">
                {p.photos_urls_json?.[0] ? (
                  <img src={p.photos_urls_json[0]} alt="" className="w-full aspect-square object-cover" />
                ) : (
                  <div className="w-full aspect-square bg-slate-100 flex items-center justify-center text-slate-300">
                    <ImageIcon className="w-12 h-12" />
                  </div>
                )}
                {/* Piste 6b — badge vidéo (apparaît dans VideoFeed mobile Yukpo) */}
                {p.video_url && (
                  <div className="absolute top-2 left-2 bg-black/70 text-white text-[10px] font-semibold px-2 py-1 rounded-full inline-flex items-center gap-1">
                    <Video className="w-3 h-3" /> VideoFeed
                  </div>
                )}
                {/* Piste 6d — badge modération */}
                {p.yukpo_ai_moderation_status === "flagged" && (
                  <div className="absolute top-2 right-2 bg-amber-500 text-white text-[10px] font-semibold px-2 py-1 rounded-full inline-flex items-center gap-1"
                       title={p.yukpo_ai_moderation_reason || ""}>
                    <AlertTriangle className="w-3 h-3" /> Flagged
                  </div>
                )}
                {p.yukpo_ai_moderation_status === "rejected" && (
                  <div className="absolute top-2 right-2 bg-rose-600 text-white text-[10px] font-semibold px-2 py-1 rounded-full inline-flex items-center gap-1"
                       title={p.yukpo_ai_moderation_reason || ""}>
                    <Shield className="w-3 h-3" /> Rejeté IA
                  </div>
                )}
                {/* Piste 6a — Quality score */}
                {typeof p.yukpo_quality_score === "number" && (
                  <div className="absolute bottom-2 right-2 bg-white/95 backdrop-blur text-[10px] font-bold px-2 py-1 rounded-full shadow inline-flex items-center gap-1"
                       title="Score qualité fiche selon IA Yukpo (titre + photos + description + prix)">
                    <Star className="w-3 h-3 text-amber-500 fill-amber-500" />
                    {p.yukpo_quality_score}/100
                  </div>
                )}
              </div>
              <div className="p-3 flex flex-col flex-grow">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className={`text-[10px] uppercase font-semibold rounded px-1.5 py-0.5 ${
                    p.statut === "actif" ? "bg-emerald-100 text-emerald-700"
                    : p.statut === "brouillon" ? "bg-amber-100 text-amber-700"
                    : "bg-slate-100 text-slate-600"
                  }`}>
                    {p.statut}
                  </span>
                  {p.source === "import_ia" && (
                    <span className="text-[10px] uppercase font-semibold text-violet-600 inline-flex items-center gap-0.5">
                      <Sparkles className="w-3 h-3" /> IA
                    </span>
                  )}
                </div>
                <h3 className="text-sm font-semibold text-slate-900 line-clamp-2 min-h-[2.5em]">{p.titre}</h3>

                {/* Piste 6a — catégorie auto-détectée + specialized_type */}
                {(p.yukpo_category || p.yukpo_specialized_type) && (
                  <div className="text-[10px] mt-1 inline-flex flex-wrap gap-1">
                    {p.yukpo_category && (
                      <span className="bg-violet-50 text-violet-700 rounded px-1.5 py-0.5">
                        {p.yukpo_category}
                      </span>
                    )}
                    {p.yukpo_specialized_type && (
                      <span className="bg-fuchsia-50 text-fuchsia-700 rounded px-1.5 py-0.5">
                        {p.yukpo_specialized_type}
                      </span>
                    )}
                  </div>
                )}

                {/* Piste 6a — tags IA (3 max) */}
                {Array.isArray(p.yukpo_tags_json) && p.yukpo_tags_json.length > 0 && (
                  <div className="text-[10px] mt-1 text-slate-500 line-clamp-1">
                    #{p.yukpo_tags_json.slice(0, 3).join(" #")}
                  </div>
                )}

                <div className="text-sm font-bold text-violet-700 mt-1">
                  {Math.round(p.prix_unit)} {p.devise}
                </div>
                <div className="text-xs text-slate-500 mt-1">Stock : {p.stock}</div>

                {/* Piste 1 — état sync marketplace Rust */}
                {p.rust_sync_status && p.rust_sync_status !== "synced" && (
                  <div className={`text-[10px] mt-1 ${
                    p.rust_sync_status === "failed" ? "text-rose-600"
                    : "text-slate-500"
                  }`}>
                    Marketplace : {p.rust_sync_status}
                  </div>
                )}

                <div className="flex gap-1 mt-2">
                  <button onClick={() => onActiverProduit(p.id, p.statut)}
                          className="flex-grow text-xs px-2 py-1.5 rounded bg-slate-100 hover:bg-slate-200 min-h-[36px]">
                    {p.statut === "actif" ? t("shop.depublier_prod", "Brouillon") : t("shop.publier_prod", "Activer")}
                  </button>
                  <button onClick={() => onShowSimilar(p.id)}
                          className="text-xs px-2 py-1.5 rounded bg-violet-100 hover:bg-violet-200 text-violet-700 min-h-[36px]"
                          title="Voir produits similaires dans le marketplace Yukpo">
                    <Globe className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => onSupprimerProduit(p.id)}
                          className="text-xs px-2 py-1.5 rounded bg-rose-100 hover:bg-rose-200 text-rose-700 min-h-[36px]">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Piste 6c — onglet Marketplace Yukpo */}
      {tab === "marketplace" && (
        <div className="space-y-4">
          <div className="bg-gradient-to-br from-violet-50 to-fuchsia-50 border border-violet-200 rounded-xl p-5">
            <h3 className="font-bold text-lg text-violet-900 mb-2 flex items-center gap-2">
              <Globe className="w-5 h-5" /> Marketplace Yukpo
            </h3>
            <p className="text-sm text-violet-800 mb-3">
              Vos produits actifs sont automatiquement indexés dans la marketplace Yukpo
              (app mobile + recherche universelle) pour bénéficier d'un trafic gratuit.
              L'IA Yukpo enrichit chaque fiche (catégorie, tags, score qualité, modération).
            </p>
            {marketplaceStats ? (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-center">
                {["synced", "pending", "failed", "skipped", "disabled"].map(s => (
                  <div key={s} className="bg-white rounded-lg p-3 border border-violet-100">
                    <div className={`text-2xl font-bold ${
                      s === "synced" ? "text-emerald-600"
                      : s === "failed" ? "text-rose-600"
                      : "text-slate-700"
                    }`}>{marketplaceStats.stats[s] || 0}</div>
                    <div className="text-[11px] uppercase text-slate-500 mt-1">{s}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-500">Chargement…</div>
            )}
            {marketplaceStats && !marketplaceStats.rust_sync_enabled && (
              <div className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                ⚠️ Sync marketplace désactivée pour votre boutique.
                Activez-la dans Paramètres boutique pour profiter du trafic gratuit Yukpo.
              </div>
            )}
            <div className="flex flex-wrap gap-2 mt-3">
              <button onClick={async () => {
                setMarketplaceStats(null);
                try {
                  const s = await generateurApi.shopRustSyncStats();
                  setMarketplaceStats({
                    stats: s.stats, total: s.total, rust_sync_enabled: s.rust_sync_enabled,
                  });
                  toast.success("Stats rafraîchies");
                } catch (e: any) {
                  toast.error(e?.response?.data?.detail || "Erreur");
                }
              }} className="text-xs px-3 py-2 rounded bg-white border border-violet-200 hover:bg-violet-100">
                <RefreshCw className="w-3.5 h-3.5 inline mr-1" /> Rafraîchir stats
              </button>
              <button onClick={async () => {
                const failedIds = produits
                  .filter(p => (p as any).rust_sync_status === "failed")
                  .map(p => p.id);
                if (failedIds.length === 0) {
                  toast("Aucun produit en échec");
                  return;
                }
                toast.loading(`Re-sync de ${failedIds.length} produit(s)…`, { id: "rs" });
                for (const id of failedIds) {
                  try { await generateurApi.shopRepublierRust(id); }
                  catch { /* continue */ }
                }
                toast.success(`✓ ${failedIds.length} re-essais lancés`, { id: "rs" });
                refresh();
              }} className="text-xs px-3 py-2 rounded bg-violet-600 text-white hover:bg-violet-700">
                Re-tenter les échecs
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal "Produits similaires" — Piste 6c */}
      {similarItems && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
             onClick={() => setSimilarItems(null)}>
          <div className="bg-white rounded-2xl max-w-3xl w-full max-h-[80vh] overflow-y-auto p-6"
               onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-lg flex items-center gap-2">
                <Globe className="w-5 h-5 text-violet-600" />
                Produits similaires dans le marketplace Yukpo
              </h3>
              <button onClick={() => setSimilarItems(null)} className="p-2 hover:bg-slate-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              Utile pour vérifier votre positionnement prix et identifier des concurrents.
            </p>
            {similarItems.items.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                <Package className="w-12 h-12 mx-auto text-slate-300 mb-2" />
                <div>Aucun produit similaire trouvé dans le marketplace.</div>
                <div className="text-xs mt-1">(Possible si Rust pas encore déployé ou marketplace vide)</div>
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {similarItems.items.map((it: any, i: number) => (
                  <a key={i} href={it.boutique_url || "#"} target="_blank" rel="noopener"
                     className="block bg-white border border-slate-200 rounded-lg overflow-hidden hover:shadow-md">
                    {it.photo_url ? (
                      <img src={it.photo_url} alt="" className="w-full aspect-square object-cover" />
                    ) : (
                      <div className="w-full aspect-square bg-slate-100 flex items-center justify-center text-slate-300">
                        <Package className="w-10 h-10" />
                      </div>
                    )}
                    <div className="p-2">
                      <div className="text-xs font-semibold line-clamp-2">{it.titre}</div>
                      <div className="text-[11px] text-violet-700 font-bold mt-1">
                        {it.prix ? `${Math.round(it.prix)} ${it.devise}` : "—"}
                      </div>
                      {it.vendeur_nom && (
                        <div className="text-[10px] text-slate-500 truncate">{it.vendeur_nom}</div>
                      )}
                    </div>
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "commandes" && (
        <div className="space-y-2">
          {commandes.length === 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-12 text-center">
              <ShoppingCart className="w-12 h-12 mx-auto text-slate-300 mb-3" />
              <p className="text-slate-500">{t("shop.vide_commandes",
                "Aucune commande pour l'instant. Publiez votre boutique pour commencer à vendre.")}</p>
            </div>
          )}
          {commandes.map(c => (
            <div key={c.id} className="bg-white rounded-xl border border-slate-200 p-4 hover:shadow-md transition">
              <div className="flex flex-wrap justify-between gap-2">
                <div>
                  <div className="font-bold text-slate-900">{c.numero}</div>
                  <div className="text-sm text-slate-600">{c.client_nom} · {c.client_telephone}</div>
                  <div className="text-xs text-slate-500 mt-1">{new Date(c.cree_le).toLocaleString()}</div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-bold text-violet-700">{Math.round(c.montant_total)} {c.devise}</div>
                  <span className={`text-xs uppercase font-semibold rounded px-2 py-0.5 ${
                    c.statut === "payee" ? "bg-emerald-100 text-emerald-700"
                    : c.statut === "en_attente_paiement" ? "bg-amber-100 text-amber-700"
                    : c.statut === "expediee" ? "bg-blue-100 text-blue-700"
                    : c.statut === "livree" ? "bg-emerald-100 text-emerald-700"
                    : "bg-slate-100 text-slate-600"
                  }`}>
                    {c.statut.replace("_", " ")}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Phase D6 — Social */}
      {tab === "social" && <OngletSocial />}

      {/* Phase D7 — ROAS Pubs */}
      {tab === "roas" && <OngletROAS />}

      {/* Phase D8 — CRM clients */}
      {tab === "crm" && <OngletCRM />}

      {/* Phase D9 — Livraison */}
      {tab === "livraison" && <OngletLivraison />}
    </div>
  );
};

// Composant helper barre d'onglets responsive (icône + label)
const TabBtn = ({ icon, label, active, onClick }: {
  icon: React.ReactNode; label: string; active: boolean; onClick: () => void;
}) => (
  <button onClick={onClick}
          className={`inline-flex items-center gap-1.5 px-3 md:px-4 py-2 text-xs md:text-sm font-medium whitespace-nowrap ${
            active ? "border-b-2 border-violet-600 text-violet-700" : "text-slate-600 hover:text-slate-900"
          }`}>
    {icon}<span>{label}</span>
  </button>
);


/**
 * ChatCreatorModal — création produit chat-style (aligné paradigme Yukpo Rust).
 *
 * Pas de formulaire. L'utilisateur conduit une mini-conversation :
 *   1. Tape la description en langage naturel ("vends iPhone 15 Pro Max
 *      neuf scellé garantie 1 an Douala Bonamoussadi")
 *   2. (optionnel) ajoute photos via drag-drop ou file picker
 *   3. Bouton "Demander à l'IA" → backend extrait la fiche structurée
 *   4. Preview de la fiche IA + champs ajustables avant validation
 *   5. Validation → produit créé en brouillon (modérable + enrichi côté Rust)
 *
 * Réutilise l'endpoint /pro/shop/produits/import-ia (Opus Vision + texte).
 */
type ProductDraft = {
  titre?: string;
  description_courte?: string;
  description_longue?: string;
  prix_suggere?: number;
  stock_initial_suggere?: number;
  categorie?: string;
  tags?: string[];
  variantes_detectees?: any[];
  seo_titre?: string;
  seo_desc?: string;
  seo_keywords?: string[];
};

const ChatCreatorModal = ({
  onClose, onCreated,
}: {
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}) => {
  const [step, setStep] = useState<"input" | "preview">("input");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [filesPreview, setFilesPreview] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<ProductDraft | null>(null);
  const [editedTitle, setEditedTitle] = useState("");
  const [editedPrice, setEditedPrice] = useState<number>(0);

  const dropRef = useRef<HTMLDivElement>(null);

  const addFiles = (fl: FileList | null) => {
    if (!fl) return;
    const arr = Array.from(fl).slice(0, 10 - files.length);
    setFiles(prev => [...prev, ...arr].slice(0, 10));
    arr.forEach(f => {
      const reader = new FileReader();
      reader.onload = e => setFilesPreview(prev => [...prev, String(e.target?.result || "")]);
      reader.readAsDataURL(f);
    });
  };

  const removeFile = (i: number) => {
    setFiles(prev => prev.filter((_, j) => j !== i));
    setFilesPreview(prev => prev.filter((_, j) => j !== i));
  };

  const onAskAI = async () => {
    if (!description.trim() && files.length === 0) {
      toast.error("Décris ton produit ou ajoute au moins une photo");
      return;
    }
    setLoading(true);
    try {
      const res = await generateurApi.shopMagicImport(files, {
        brief: description, auto_save: false,
      });
      const spec = res.spec_ia || res.produit;
      setDraft(spec);
      setEditedTitle(spec?.titre || "");
      setEditedPrice(spec?.prix_suggere || spec?.prix_unit || 0);
      setStep("preview");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "L'IA n'a pas pu extraire la fiche");
    } finally { setLoading(false); }
  };

  const onValidate = async () => {
    if (!draft) return;
    setLoading(true);
    try {
      // 1. Crée le produit avec auto_save=true (relance le pipeline)
      await generateurApi.shopMagicImport(files, {
        brief: `${description}\n\nTitre validé : ${editedTitle}\nPrix validé : ${editedPrice}`,
        auto_save: true,
      });
      toast.success("✓ Produit créé en brouillon (sera enrichi par l'IA Yukpo Rust)");
      await onCreated();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur création");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
         onClick={onClose}>
      <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] flex flex-col"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h3 className="font-bold text-lg inline-flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-violet-600" />
            Assistant IA Yukpo — Créer un produit
          </h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-5 flex-grow">
          {step === "input" && (
            <>
              <div className="bg-violet-50 border border-violet-100 rounded-lg p-3 mb-4 text-sm text-violet-900">
                <div className="font-semibold mb-1">💬 Décris ton produit</div>
                <div className="text-xs opacity-80">
                  L'IA extrait titre, description vendeuse, prix, catégorie, tags,
                  variantes. Tu pourras ajuster avant validation finale.
                </div>
              </div>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={4}
                placeholder="Exemple : 'Vends iPhone 15 Pro Max 256GB titane bleu neuf scellé garantie Apple 1 an, livraison Douala Bonamoussadi, prix 850 000 FCFA négociable'"
                className="w-full px-3 py-2 mb-4 rounded-lg border border-slate-300 text-sm focus:border-violet-500 focus:outline-none"
              />

              <div
                ref={dropRef}
                onDragOver={e => { e.preventDefault(); dropRef.current?.classList.add("border-violet-500", "bg-violet-50"); }}
                onDragLeave={() => dropRef.current?.classList.remove("border-violet-500", "bg-violet-50")}
                onDrop={e => {
                  e.preventDefault();
                  dropRef.current?.classList.remove("border-violet-500", "bg-violet-50");
                  addFiles(e.dataTransfer.files);
                }}
                className="border-2 border-dashed border-slate-300 rounded-lg p-5 text-center transition mb-3 cursor-pointer"
                onClick={() => document.getElementById("chatcreator-file")?.click()}
              >
                <input
                  id="chatcreator-file" type="file" accept="image/*" multiple
                  className="hidden"
                  onChange={e => addFiles(e.target.files)}
                />
                <Upload className="w-8 h-8 mx-auto text-slate-400 mb-2" />
                <div className="text-sm text-slate-600">
                  Glisse-dépose tes photos OU clique pour parcourir (1-10 photos)
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  L'IA analyse les images pour enrichir la fiche
                </div>
              </div>

              {filesPreview.length > 0 && (
                <div className="grid grid-cols-3 md:grid-cols-5 gap-2 mb-4">
                  {filesPreview.map((src, i) => (
                    <div key={i} className="relative group">
                      <img src={src} alt="" className="w-full aspect-square object-cover rounded" />
                      <button onClick={() => removeFile(i)}
                              className="absolute top-1 right-1 bg-rose-600 text-white rounded-full w-5 h-5 inline-flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="text-[11px] text-slate-500">
                💡 Une fois créé, le produit est automatiquement enrichi par Yukpo Rust
                (catégorie, tags, score qualité, modération, indexation marketplace).
              </div>
            </>
          )}

          {step === "preview" && draft && (
            <>
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 mb-4 text-sm text-emerald-900">
                <div className="font-semibold mb-1">✨ L'IA a extrait cette fiche — ajuste et valide</div>
                <div className="text-xs opacity-80">
                  À la validation, le produit sera créé en brouillon. L'IA Yukpo Rust
                  l'enrichira ensuite (catégorie, tags, modération) avant publication.
                </div>
              </div>

              <label className="block text-sm font-semibold mb-1 mt-3">Titre vendeur</label>
              <input
                value={editedTitle}
                onChange={e => setEditedTitle(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-violet-500 focus:outline-none"
              />

              <label className="block text-sm font-semibold mb-1 mt-3">Prix suggéré</label>
              <input
                type="number"
                value={editedPrice}
                onChange={e => setEditedPrice(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-violet-500 focus:outline-none"
              />

              {draft.description_longue && (
                <>
                  <label className="block text-sm font-semibold mb-1 mt-3">Description IA</label>
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs whitespace-pre-line max-h-40 overflow-y-auto">
                    {draft.description_longue}
                  </div>
                </>
              )}

              {Array.isArray(draft.tags) && draft.tags.length > 0 && (
                <>
                  <label className="block text-sm font-semibold mb-1 mt-3">Tags auto</label>
                  <div className="flex flex-wrap gap-1.5">
                    {draft.tags.map((t, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-violet-100 text-violet-700">
                        #{t}
                      </span>
                    ))}
                  </div>
                </>
              )}

              {draft.categorie && (
                <div className="mt-3 text-xs text-slate-600">
                  Catégorie détectée : <strong>{draft.categorie}</strong>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t bg-slate-50 rounded-b-2xl">
          {step === "input" && (
            <>
              <button onClick={onClose}
                      className="px-4 py-2 rounded-lg bg-white border border-slate-300 text-sm hover:bg-slate-50">
                Annuler
              </button>
              <button onClick={onAskAI} disabled={loading}
                      className="px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                Demander à l'IA Yukpo
              </button>
            </>
          )}
          {step === "preview" && (
            <>
              <button onClick={() => setStep("input")}
                      className="px-4 py-2 rounded-lg bg-white border border-slate-300 text-sm hover:bg-slate-50">
                Modifier description
              </button>
              <button onClick={onValidate} disabled={loading}
                      className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ChevronRight className="w-4 h-4" />}
                Valider — créer le produit
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
