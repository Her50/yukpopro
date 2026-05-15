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
  ArrowLeft, BarChart3, Check, ExternalLink, Facebook, Flame, Gift, Image as ImageIcon,
  Loader2, Mail, MapPin, MessageSquare, Package, Palette, RefreshCw, Reply,
  Send, Shield, ShoppingCart, Sparkles, Star, Tag, Trash2, Truck, Upload, Users,
  Video, Wand2, Globe, AlertTriangle, ChevronRight, X, Zap,
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

function urlBase64ToUint8Array(b64: string): Uint8Array {
  const padding = "=".repeat((4 - b64.length % 4) % 4);
  const base64 = (b64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function activerPushNotifications(): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;
  if (Notification.permission === "denied") return false;
  try {
    const { public_key } = await generateurApi.shopPushVapidKey();
    if (!public_key) return false;
    if (Notification.permission !== "granted") {
      const p = await Notification.requestPermission();
      if (p !== "granted") return false;
    }
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      });
    }
    await generateurApi.shopPushSubscribe(sub);
    return true;
  } catch (e) {
    console.warn("[Push] subscribe échec", e);
    return false;
  }
}

export const MaBoutiquePage = () => {
  const { t } = useTranslation();
  const [boutique, setBoutique] = useState<any>(null);
  const [produits, setProduits] = useState<Produit[]>([]);
  const [commandes, setCommandes] = useState<Commande[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"produits" | "commandes" | "social" | "roas" | "crm" | "livraison" | "marketplace" | "messages" | "avis" | "branding" | "promos">("produits");
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
  // Gaps management — modals édition + partage
  const [editProduit, setEditProduit] = useState<Produit | null>(null);
  const [shareProduit, setShareProduit] = useState<Produit | null>(null);

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

  // Auto-subscribe push (permission déjà accordée) au montage de MaBoutique.
  // Le 1er prompt de permission se fait via le bouton dans Branding.
  useEffect(() => {
    if (boutique && typeof Notification !== "undefined" && Notification.permission === "granted") {
      activerPushNotifications().catch(() => {});
    }
  }, [boutique?.id]);

  // Pré-remplissage du formulaire init depuis sessionStorage si l'user
  // vient du chat avec un brief (ex : "ouvre ma boutique de bijoux à Douala").
  // ChatPage stocke {nom, description, devise, pays_principal} sous
  // 'yukposhop_init_suggestions' avec TTL 30 min. On lit ces valeurs dès
  // que showInit passe à true.
  useEffect(() => {
    if (!showInit) return;
    try {
      const raw = sessionStorage.getItem("yukposhop_init_suggestions");
      if (!raw) return;
      const sug = JSON.parse(raw);
      if (sug?.expires_at && Date.now() > sug.expires_at) {
        sessionStorage.removeItem("yukposhop_init_suggestions");
        return;
      }
      setInitForm(prev => ({
        nom: prev.nom || sug.nom || "",
        description: prev.description || sug.description || "",
        devise: sug.devise || prev.devise,
        pays_principal: sug.pays_principal || prev.pays_principal,
      }));
      toast.success("Yukpo a pré-rempli le formulaire — modifie si besoin");
      sessionStorage.removeItem("yukposhop_init_suggestions");
    } catch { /* silencieux : sessionStorage indispo / JSON corrompu */ }
  }, [showInit]);

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

  const onDupliquer = async (id: number) => {
    setBusy(`dup-${id}`);
    try {
      const res = await generateurApi.shopDupliquerProduit(id);
      toast.success(`✓ Produit dupliqué : "${res.produit.titre}"`);
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur duplication");
    } finally { setBusy(null); }
  };

  const onGenererVideo = async (p: Produit) => {
    if (!p.photos_urls_json?.length) {
      toast.error("Ajoute au moins 1 photo avant de générer une vidéo");
      return;
    }
    const ton = prompt(
      "Ton de la vidéo (dynamique / luxueux / chaleureux / pro) :",
      "dynamique",
    ) || "dynamique";
    const dureeStr = prompt("Durée en secondes (5-60) :", "15") || "15";
    const duree = Math.max(5, Math.min(60, parseInt(dureeStr) || 15));
    setBusy(`vid-${p.id}`);
    toast.loading(`🎬 Génération vidéo pub IA (~${duree * 2}s)…`, { id: "vid" });
    try {
      const res = await generateurApi.shopGenererVideo(p.id, ton, duree);
      if (res.ok && res.video_url) {
        toast.success("✓ Vidéo générée — visible dans VideoFeed mobile Yukpo", { id: "vid" });
        await refresh();
      } else {
        toast(res.error || "Génération non disponible (Rust Remotion en Phase B)",
              { id: "vid", icon: "⚠️", duration: 8000 });
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur génération", { id: "vid" });
    } finally { setBusy(null); }
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

  // Override transversal contraste : tous les inputs/selects/textareas de
  // cette page (et de ses modals) hériteront de bg blanc + texte slate-900
  // + placeholder slate-400. Évite de réécrire 20+ className individuels.
  const _contrastFix = (
    <style>{`
      .maboutique-scope input:not([type="file"]):not([type="checkbox"]):not([type="radio"]),
      .maboutique-scope select,
      .maboutique-scope textarea {
        background-color: #ffffff;
        color: #0f172a;            /* slate-900 */
      }
      .maboutique-scope input::placeholder,
      .maboutique-scope textarea::placeholder { color: #94a3b8; }  /* slate-400 */
      .maboutique-scope h1, .maboutique-scope h2, .maboutique-scope h3,
      .maboutique-scope h4, .maboutique-scope label { color: #0f172a; }
      /* Boutons "neutres" (bg-slate-100/200, bg-white) — couleur de texte par défaut */
      .maboutique-scope button:not([class*="text-white"]):not([class*="text-violet-"]):not([class*="text-emerald-"]):not([class*="text-rose-"]):not([class*="text-amber-"]):not([class*="text-blue-"]):not([class*="text-fuchsia-"]):not([class*="text-sky-"]) {
        color: #1e293b;            /* slate-800 */
      }
    `}</style>
  );

  if (showInit) {
    return (
      <div className="ykp-page maboutique-scope p-4 md:p-6 max-w-xl mx-auto">
        {_contrastFix}
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
                   className="w-full px-4 py-2.5 rounded-lg border border-slate-300 bg-white text-slate-900 placeholder-slate-400 min-h-[44px]" />
            <textarea placeholder={t("shop.init_desc", "Description (optionnelle)") as string}
                      value={initForm.description}
                      onChange={e => setInitForm({ ...initForm, description: e.target.value })}
                      rows={3} className="w-full px-4 py-2.5 rounded-lg border border-slate-300 bg-white text-slate-900 placeholder-slate-400" />
            <div className="grid grid-cols-2 gap-3">
              <select value={initForm.devise}
                      onChange={e => setInitForm({ ...initForm, devise: e.target.value })}
                      className="px-4 py-2.5 rounded-lg border border-slate-300 bg-white text-slate-900 min-h-[44px]">
                <option value="XAF">XAF (FCFA Afrique centrale)</option>
                <option value="XOF">XOF (FCFA Ouest)</option>
                <option value="NGN">NGN (Naira)</option>
                <option value="MAD">MAD (Dirham)</option>
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
              </select>
              <select value={initForm.pays_principal}
                      onChange={e => setInitForm({ ...initForm, pays_principal: e.target.value })}
                      className="px-4 py-2.5 rounded-lg border border-slate-300 bg-white text-slate-900 min-h-[44px]">
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
    <div className="ykp-page maboutique-scope p-4 md:p-6 max-w-6xl mx-auto">
      {_contrastFix}
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

      {/* Suggestion identité visuelle si manquante */}
      {boutique && !boutique.logo_url && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mb-4 flex items-center gap-3">
          <Palette className="w-5 h-5 text-amber-700 flex-shrink-0" />
          <div className="flex-1 text-sm text-amber-900">
            <b>Ajoutez votre logo</b> — il sert d'icône PWA (écran d'accueil mobile des visiteurs) et de favicon. Vous pouvez l'uploader ou demander à l'IA de le générer.
          </div>
          <button onClick={() => setTab("branding")}
                  className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-semibold whitespace-nowrap">
            Ouvrir Branding
          </button>
        </div>
      )}

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

      {/* Modal édition produit complète */}
      {editProduit && (
        <EditProduitModal
          produit={editProduit}
          onClose={() => setEditProduit(null)}
          onSaved={async () => {
            setEditProduit(null);
            await refresh();
          }}
        />
      )}

      {/* Modal partage produit (WA / email / SMS / copier lien) */}
      {shareProduit && boutique && (
        <ShareProduitModal
          produit={shareProduit}
          boutique={boutique}
          onClose={() => setShareProduit(null)}
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
        <TabBtn icon={<MessageSquare className="w-4 h-4" />} label={t("shop.tab_messages", "Messages")}
                active={tab === "messages"} onClick={() => setTab("messages")} />
        <TabBtn icon={<Star className="w-4 h-4" />} label={t("shop.tab_avis", "Avis")}
                active={tab === "avis"} onClick={() => setTab("avis")} />
        <TabBtn icon={<Palette className="w-4 h-4" />} label={t("shop.tab_branding", "Branding")}
                active={tab === "branding"} onClick={() => setTab("branding")} />
        <TabBtn icon={<Tag className="w-4 h-4" />} label={t("shop.tab_promos", "Promos")}
                active={tab === "promos"} onClick={() => setTab("promos")} />
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

                <div className="mt-auto pt-2">
                  <div className="flex gap-1 mb-1">
                    <button onClick={() => onActiverProduit(p.id, p.statut)}
                            className="flex-grow text-xs px-2 py-1.5 rounded bg-slate-100 hover:bg-slate-200 min-h-[36px]">
                      {p.statut === "actif" ? t("shop.depublier_prod", "Brouillon") : t("shop.publier_prod", "Activer")}
                    </button>
                    <button onClick={() => setEditProduit(p)}
                            className="text-xs px-2 py-1.5 rounded bg-blue-100 hover:bg-blue-200 text-blue-700 min-h-[36px]"
                            title="Modifier (édition complète)">
                      ✎
                    </button>
                    <button onClick={() => onSupprimerProduit(p.id)}
                            className="text-xs px-2 py-1.5 rounded bg-rose-100 hover:bg-rose-200 text-rose-700 min-h-[36px]"
                            title="Supprimer">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="grid grid-cols-4 gap-1">
                    <button onClick={() => onDupliquer(p.id)}
                            disabled={busy === `dup-${p.id}`}
                            className="text-[10px] px-1.5 py-1.5 rounded bg-slate-50 hover:bg-slate-100 text-slate-700 disabled:opacity-50 inline-flex items-center justify-center"
                            title="Dupliquer">
                      {busy === `dup-${p.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : "⎘"}
                    </button>
                    <button onClick={() => setShareProduit(p)}
                            className="text-[10px] px-1.5 py-1.5 rounded bg-emerald-50 hover:bg-emerald-100 text-emerald-700 inline-flex items-center justify-center"
                            title="Partager (WA, email, SMS, lien)">
                      <Send className="w-3 h-3" />
                    </button>
                    <button onClick={() => onGenererVideo(p)}
                            disabled={busy === `vid-${p.id}`}
                            className="text-[10px] px-1.5 py-1.5 rounded bg-fuchsia-50 hover:bg-fuchsia-100 text-fuchsia-700 disabled:opacity-50 inline-flex items-center justify-center"
                            title={p.video_url ? "Vidéo générée — VideoFeed Yukpo" : "Générer vidéo pub IA"}>
                      {busy === `vid-${p.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <Video className="w-3 h-3" />}
                    </button>
                    <button onClick={() => onShowSimilar(p.id)}
                            className="text-[10px] px-1.5 py-1.5 rounded bg-violet-50 hover:bg-violet-100 text-violet-700 inline-flex items-center justify-center"
                            title="Produits similaires marketplace">
                      <Globe className="w-3 h-3" />
                    </button>
                  </div>
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

      {/* Q1 — Messages visiteurs */}
      {tab === "messages" && <OngletMessages />}

      {/* Q1 — Avis clients (modération) */}
      {tab === "avis" && <OngletAvis />}

      {/* Branding — logo + bannière + génération IA + PWA */}
      {tab === "branding" && (
        <OngletBranding boutique={boutique} onUpdated={refresh} />
      )}

      {/* Promos — coupons + flash sales + Black Friday Yukpo */}
      {tab === "promos" && <OngletPromos produits={produits} />}
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


/**
 * EditProduitModal — édition complète d'un produit existant.
 * Tous les champs de ShopProductDB modifiables sont exposés.
 */
const EditProduitModal = ({
  produit, onClose, onSaved,
}: {
  produit: Produit;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) => {
  const [titre, setTitre] = useState(produit.titre);
  const [descCourte, setDescCourte] = useState((produit as any).description_courte || "");
  const [descLongue, setDescLongue] = useState((produit as any).description_longue || "");
  const [prix, setPrix] = useState(produit.prix_unit);
  const [prixPromo, setPrixPromo] = useState((produit as any).prix_unit_promo || 0);
  const [stock, setStock] = useState(produit.stock);
  const [tva, setTva] = useState((produit as any).tva_pct || 0);
  const [videoUrl, setVideoUrl] = useState(produit.video_url || "");
  const [tagsStr, setTagsStr] = useState(
    Array.isArray((produit as any).tags_json)
      ? (produit as any).tags_json.join(", ")
      : ""
  );
  const [saving, setSaving] = useState(false);

  // Si l'IA Yukpo a généré une description enrichie, proposer de l'adopter
  const hasIASuggestion = !!produit.yukpo_description_enriched &&
                          produit.yukpo_description_enriched !== descLongue;

  const onSave = async () => {
    setSaving(true);
    try {
      await generateurApi.shopPatchProduit(produit.id, {
        titre,
        description_courte: descCourte || null,
        description_longue: descLongue || null,
        prix_unit: prix,
        prix_unit_promo: prixPromo > 0 ? prixPromo : null,
        stock,
        tva_pct: tva,
        video_url: videoUrl || null,
        tags_json: tagsStr.split(",").map(s => s.trim()).filter(Boolean),
      });
      toast.success("Produit mis à jour");
      await onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h3 className="font-bold text-lg">✎ Modifier le produit</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-6 py-5 flex-grow space-y-3">
          <div>
            <label className="block text-sm font-semibold mb-1">Titre vendeur</label>
            <input value={titre} onChange={e => setTitre(e.target.value)}
                   className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-violet-500 focus:outline-none" />
          </div>
          <div>
            <label className="block text-sm font-semibold mb-1">Description courte</label>
            <input value={descCourte} onChange={e => setDescCourte(e.target.value)}
                   className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-semibold mb-1 flex items-center justify-between">
              <span>Description longue</span>
              {hasIASuggestion && (
                <button onClick={() => setDescLongue(produit.yukpo_description_enriched!)}
                        className="text-[11px] text-violet-600 hover:underline">
                  ✨ Adopter la description IA Yukpo
                </button>
              )}
            </label>
            <textarea value={descLongue} onChange={e => setDescLongue(e.target.value)} rows={6}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-semibold mb-1">Prix</label>
              <input type="number" value={prix} onChange={e => setPrix(Number(e.target.value))}
                     className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
            </div>
            <div>
              <label className="block text-sm font-semibold mb-1">Prix promo</label>
              <input type="number" value={prixPromo} onChange={e => setPrixPromo(Number(e.target.value))}
                     placeholder="0 = pas de promo"
                     className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
            </div>
            <div>
              <label className="block text-sm font-semibold mb-1">Stock</label>
              <input type="number" value={stock} onChange={e => setStock(Number(e.target.value))}
                     className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-semibold mb-1">TVA %</label>
              <input type="number" value={tva} onChange={e => setTva(Number(e.target.value))}
                     className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
            </div>
            <div>
              <label className="block text-sm font-semibold mb-1">URL vidéo (VideoFeed)</label>
              <input value={videoUrl} onChange={e => setVideoUrl(e.target.value)}
                     placeholder="https://… ou laisse vide"
                     className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-semibold mb-1">Tags (séparés par virgule)</label>
            <input value={tagsStr} onChange={e => setTagsStr(e.target.value)}
                   placeholder="smartphone, 5G, écran amoled"
                   className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
            {Array.isArray(produit.yukpo_tags_json) && produit.yukpo_tags_json.length > 0 && (
              <button onClick={() => setTagsStr(produit.yukpo_tags_json!.join(", "))}
                      className="mt-1 text-[11px] text-violet-600 hover:underline">
                ✨ Utiliser les tags IA Yukpo : {produit.yukpo_tags_json.slice(0, 3).join(", ")}…
              </button>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2 px-6 py-4 border-t bg-slate-50 rounded-b-2xl">
          <button onClick={onClose}
                  className="px-4 py-2 rounded-lg bg-white border border-slate-300 text-sm hover:bg-slate-50">
            Annuler
          </button>
          <button onClick={onSave} disabled={saving}
                  className="px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-50">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <ChevronRight className="w-4 h-4" />}
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  );
};


/**
 * ShareProduitModal — partage externe d'un produit (WA / email / SMS / lien).
 *
 * Construit l'URL publique du storefront `https://<slug>.yukpomnang.com/p/<produit-slug>`
 * + un message commercial pré-rempli. Le client peut copier ou cliquer
 * directement sur WA Web/SMS/mailto pour ouvrir l'app native.
 */
const ShareProduitModal = ({
  produit, boutique, onClose,
}: {
  produit: Produit;
  boutique: any;
  onClose: () => void;
}) => {
  const baseUrl = boutique?.url_public ||
                  `https://${boutique?.slug}.yukpomnang.com`;
  const lienPublic = `${baseUrl}/p/${produit.slug}`;
  const prix = (produit as any).prix_unit_promo || produit.prix_unit;
  const devise = produit.devise;

  // Message commercial pré-rempli (utilisé pour WA/SMS/email)
  const message =
    `🛍 *${produit.titre}*\n` +
    `💰 ${Math.round(prix)} ${devise}` +
    ((produit as any).prix_unit_promo ? ` (promo !)` : "") + "\n" +
    `📍 ${boutique?.nom || "Yukpo Shop"}\n\n` +
    ((produit as any).description_courte
      ? `${(produit as any).description_courte}\n\n`
      : "") +
    `👉 Commander : ${lienPublic}`;

  const onCopy = () => {
    navigator.clipboard.writeText(lienPublic);
    toast.success("Lien copié dans le presse-papier");
  };

  const onCopyMsg = () => {
    navigator.clipboard.writeText(message);
    toast.success("Message copié dans le presse-papier");
  };

  const waUrl = `https://wa.me/?text=${encodeURIComponent(message)}`;
  const smsUrl = `sms:?body=${encodeURIComponent(message)}`;
  const mailUrl = `mailto:?subject=${encodeURIComponent(
    `${produit.titre} — ${Math.round(prix)} ${devise}`
  )}&body=${encodeURIComponent(message)}`;
  const fbUrl = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(lienPublic)}`;

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl max-w-md w-full" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h3 className="font-bold text-lg inline-flex items-center gap-2">
            <Send className="w-5 h-5 text-emerald-600" />
            Partager ce produit
          </h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs whitespace-pre-line max-h-32 overflow-y-auto">
            {message}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <a href={waUrl} target="_blank" rel="noopener"
               className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white font-semibold text-sm">
              💬 WhatsApp
            </a>
            <a href={smsUrl}
               className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-blue-500 hover:bg-blue-600 text-white font-semibold text-sm">
              📱 SMS
            </a>
            <a href={mailUrl}
               className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-slate-500 hover:bg-slate-600 text-white font-semibold text-sm">
              📧 Email
            </a>
            <a href={fbUrl} target="_blank" rel="noopener"
               className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-[#1877F2] hover:opacity-90 text-white font-semibold text-sm">
              <Facebook className="w-4 h-4" /> Facebook
            </a>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">
              Lien direct produit
            </label>
            <div className="flex gap-2">
              <input value={lienPublic} readOnly
                     className="flex-grow px-3 py-2 rounded-lg border border-slate-300 text-sm bg-slate-50" />
              <button onClick={onCopy}
                      className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold">
                Copier
              </button>
            </div>
            <button onClick={onCopyMsg}
                    className="mt-2 text-xs text-violet-600 hover:underline">
              📋 Copier le message complet
            </button>
          </div>

          <div className="text-[11px] text-slate-500 italic">
            💡 Chaque clic sur ce lien depuis un canal social peut être tracké
            côté Yukpo Rust (`/api/social/track`) pour mesurer l'attribution.
          </div>
        </div>
      </div>
    </div>
  );
};


// ═══════════════════════════════════════════════════════════════════════════
// Q1 — Onglet Messages visiteurs
// ═══════════════════════════════════════════════════════════════════════════

const OngletMessages = () => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [replyText, setReplyText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await generateurApi.shopListerMessages(filter ? { statut: filter } : undefined);
      setItems(r.items || []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur de chargement");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

  const repondre = async (mid: number) => {
    if (!replyText.trim()) return;
    setBusy(true);
    try {
      await generateurApi.shopRepondreMessage(mid, replyText, true);
      toast.success("Réponse envoyée");
      setReplyText(""); setOpenId(null); load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur");
    } finally { setBusy(false); }
  };

  const suggererIA = async (mid: number) => {
    setBusy(true);
    try {
      const r = await generateurApi.shopMessageSuggererReponse(mid);
      if (r.draft) setReplyText(r.draft);
      toast.success(r.cached ? "Brouillon récupéré" : "Réponse suggérée");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "IA indisponible");
    } finally { setBusy(false); }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <h3 className="text-lg font-bold text-slate-900 flex-1">Messages visiteurs</h3>
        <select value={filter} onChange={e => setFilter(e.target.value)}
                className="px-3 py-1.5 border rounded-lg text-sm">
          <option value="">Tous</option>
          <option value="non_lu">Non lus</option>
          <option value="lu">Lus</option>
          <option value="repondu">Répondus</option>
          <option value="archive">Archivés</option>
        </select>
        <button onClick={load} className="px-3 py-1.5 rounded-lg border text-sm">
          <RefreshCw className="w-3.5 h-3.5 inline mr-1" />Rafraîchir
        </button>
      </div>
      {loading && <div className="text-center py-8 text-slate-500">Chargement…</div>}
      {!loading && items.length === 0 && (
        <div className="text-center py-12 text-slate-500">
          <Mail className="w-12 h-12 mx-auto text-slate-300 mb-3" />
          Aucun message.
        </div>
      )}
      <div className="space-y-2">
        {items.map(m => (
          <div key={m.id} className={`border rounded-lg p-3 ${m.statut === "non_lu" ? "bg-violet-50 border-violet-200" : "border-slate-200"}`}>
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap text-sm">
                  <span className="font-semibold">{m.visitor_nom}</span>
                  {m.visitor_telephone && <span className="text-slate-500">{m.visitor_telephone}</span>}
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100">{m.statut}</span>
                  <span className="text-xs text-slate-400">{new Date(m.cree_le).toLocaleString()}</span>
                </div>
                {m.sujet && <div className="text-sm font-medium mt-1">{m.sujet}</div>}
                <div className="text-sm text-slate-700 mt-1 whitespace-pre-wrap">{m.contenu}</div>
                {m.reponse_marchand && (
                  <div className="mt-2 pl-3 border-l-2 border-emerald-400 text-sm">
                    <div className="text-xs text-emerald-700 font-semibold">Votre réponse · {m.repondu_le && new Date(m.repondu_le).toLocaleString()}</div>
                    <div className="text-slate-700 whitespace-pre-wrap">{m.reponse_marchand}</div>
                  </div>
                )}
                {openId === m.id && (
                  <div className="mt-2">
                    <textarea value={replyText} onChange={e => setReplyText(e.target.value)}
                              rows={4} maxLength={4000}
                              placeholder="Votre réponse (envoyée par WhatsApp au visiteur)…"
                              className="w-full px-3 py-2 border rounded-lg text-sm" />
                    <div className="flex gap-2 mt-1 flex-wrap">
                      <button disabled={busy} onClick={() => repondre(m.id)}
                              className="px-3 py-1.5 rounded-lg bg-violet-600 text-white text-sm font-semibold disabled:opacity-50">
                        <Send className="w-3.5 h-3.5 inline mr-1" />Envoyer
                      </button>
                      <button disabled={busy} onClick={() => suggererIA(m.id)}
                              className="px-3 py-1.5 rounded-lg border border-violet-300 bg-violet-50 text-violet-700 text-sm font-semibold disabled:opacity-50">
                        <Sparkles className="w-3.5 h-3.5 inline mr-1" />Suggestion IA
                      </button>
                      <button onClick={() => { setOpenId(null); setReplyText(""); }}
                              className="px-3 py-1.5 rounded-lg border text-sm">Annuler</button>
                    </div>
                  </div>
                )}
              </div>
              {openId !== m.id && (
                <button onClick={() => setOpenId(m.id)} className="px-3 py-1.5 rounded-lg border text-sm whitespace-nowrap">
                  <Reply className="w-3.5 h-3.5 inline mr-1" />Répondre
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};


// ═══════════════════════════════════════════════════════════════════════════
// Q1 — Onglet Avis (modération commentaires)
// ═══════════════════════════════════════════════════════════════════════════

const OngletAvis = () => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>("pending");

  const load = async () => {
    setLoading(true);
    try {
      const r = await generateurApi.shopListerCommentaires(filter ? { statut: filter } : undefined);
      setItems(r.items || []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

  const moderer = async (cid: number, statut: "approved" | "rejected") => {
    try {
      await generateurApi.shopModererCommentaire(cid, statut);
      toast.success(statut === "approved" ? "Avis approuvé" : "Avis rejeté");
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur");
    }
  };
  const supprimer = async (cid: number) => {
    if (!confirm("Supprimer définitivement cet avis ?")) return;
    try {
      await generateurApi.shopSupprimerCommentaire(cid);
      toast.success("Avis supprimé"); load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur");
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <h3 className="text-lg font-bold text-slate-900 flex-1">Avis clients</h3>
        <select value={filter} onChange={e => setFilter(e.target.value)}
                className="px-3 py-1.5 border rounded-lg text-sm">
          <option value="pending">À modérer</option>
          <option value="approved">Approuvés</option>
          <option value="rejected">Rejetés</option>
          <option value="">Tous</option>
        </select>
        <button onClick={load} className="px-3 py-1.5 rounded-lg border text-sm">
          <RefreshCw className="w-3.5 h-3.5 inline mr-1" />Rafraîchir
        </button>
      </div>
      {loading && <div className="text-center py-8 text-slate-500">Chargement…</div>}
      {!loading && items.length === 0 && (
        <div className="text-center py-12 text-slate-500">
          <Star className="w-12 h-12 mx-auto text-slate-300 mb-3" />
          Aucun avis {filter ? `(${filter})` : ""}.
        </div>
      )}
      <div className="space-y-2">
        {items.map(c => (
          <div key={c.id} className="border border-slate-200 rounded-lg p-3">
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap text-sm">
                  <span className="font-semibold">{c.author_nom}</span>
                  {c.note && <span className="text-amber-500">{"⭐".repeat(c.note)}</span>}
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100">{c.statut}</span>
                  <span className="text-xs text-slate-400">produit #{c.product_id}</span>
                  <span className="text-xs text-slate-400">{new Date(c.cree_le).toLocaleString()}</span>
                </div>
                <div className="text-sm text-slate-700 mt-1 whitespace-pre-wrap">{c.contenu}</div>
                {(c.author_telephone || c.author_email) && (
                  <div className="text-xs text-slate-500 mt-1">
                    {c.author_telephone && <span>📞 {c.author_telephone}</span>}
                    {c.author_email && <span className="ml-2">✉ {c.author_email}</span>}
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-1">
                {c.statut !== "approved" && (
                  <button onClick={() => moderer(c.id, "approved")}
                          className="px-3 py-1 rounded-lg bg-emerald-600 text-white text-xs font-semibold">
                    <Check className="w-3 h-3 inline mr-1" />Approuver
                  </button>
                )}
                {c.statut !== "rejected" && (
                  <button onClick={() => moderer(c.id, "rejected")}
                          className="px-3 py-1 rounded-lg bg-amber-600 text-white text-xs font-semibold">
                    <X className="w-3 h-3 inline mr-1" />Rejeter
                  </button>
                )}
                <button onClick={() => supprimer(c.id)}
                        className="px-3 py-1 rounded-lg border border-rose-300 text-rose-600 text-xs font-semibold">
                  <Trash2 className="w-3 h-3 inline mr-1" />Supprimer
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};


// ═══════════════════════════════════════════════════════════════════════════
// Branding — logo + bannière + génération IA (sert aussi d'icône PWA)
// ═══════════════════════════════════════════════════════════════════════════

const OngletBranding = ({ boutique, onUpdated }: { boutique: any; onUpdated: () => Promise<void> }) => {
  const [logoUrl, setLogoUrl] = useState<string>(boutique?.logo_url || "");
  const [bannUrl, setBannUrl] = useState<string>(boutique?.banniere_url || "");
  const [busy, setBusy] = useState<string | null>(null);
  const [briefLogo, setBriefLogo] = useState("");
  const [styleLogo, setStyleLogo] = useState("");
  const [briefBann, setBriefBann] = useState("");
  const [styleBann, setStyleBann] = useState("");
  const logoFile = useRef<HTMLInputElement>(null);
  const bannFile = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setLogoUrl(boutique?.logo_url || "");
    setBannUrl(boutique?.banniere_url || "");
  }, [boutique]);

  const uploaderLogo = async (f: File) => {
    setBusy("upload_logo");
    try {
      const r = await generateurApi.shopUploaderLogo(f);
      setLogoUrl(r.url); await onUpdated();
      toast.success("Logo mis à jour");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur upload");
    } finally { setBusy(null); }
  };
  const uploaderBanniere = async (f: File) => {
    setBusy("upload_bann");
    try {
      const r = await generateurApi.shopUploaderBanniere(f);
      setBannUrl(r.url); await onUpdated();
      toast.success("Bannière mise à jour");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur upload");
    } finally { setBusy(null); }
  };
  const genererLogo = async () => {
    setBusy("gen_logo");
    try {
      const r = await generateurApi.shopGenererLogoIA({ brief: briefLogo, style: styleLogo });
      setLogoUrl(r.url); await onUpdated();
      toast.success("Logo généré par IA");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur génération");
    } finally { setBusy(null); }
  };
  const genererBanniere = async () => {
    setBusy("gen_bann");
    try {
      const r = await generateurApi.shopGenererBanniereIA({ brief: briefBann, style: styleBann });
      setBannUrl(r.url); await onUpdated();
      toast.success("Bannière générée par IA");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur génération");
    } finally { setBusy(null); }
  };

  return (
    <div className="space-y-6">
      <div className="bg-violet-50 border border-violet-200 rounded-xl p-4 text-sm text-violet-900">
        <div className="flex items-start gap-2">
          <Sparkles className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold mb-1">Logo + Bannière = identité visuelle de votre boutique</div>
            <div>Le <b>logo</b> sert d'icône PWA (écran d'accueil mobile de vos visiteurs) et de favicon dans le navigateur. La <b>bannière</b> est l'image hero sur la page d'accueil. Uploadez ou demandez à l'IA de les générer pour vous.</div>
          </div>
        </div>
      </div>

      {/* Logo */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <ImageIcon className="w-5 h-5 text-violet-600" />
          <h3 className="text-lg font-bold">Logo</h3>
          <span className="text-xs text-slate-500">(carré 1:1 · icône PWA · favicon)</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="aspect-square rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 flex items-center justify-center overflow-hidden">
              {logoUrl
                ? <img src={logoUrl} alt="logo" className="w-full h-full object-contain" />
                : <div className="text-slate-400 text-sm">Aucun logo</div>}
            </div>
            <input ref={logoFile} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml"
                   className="hidden" onChange={e => e.target.files?.[0] && uploaderLogo(e.target.files[0])} />
            <button onClick={() => logoFile.current?.click()} disabled={!!busy}
                    className="w-full mt-2 px-4 py-2 rounded-lg border border-slate-300 font-semibold disabled:opacity-50">
              {busy === "upload_logo"
                ? <><Loader2 className="w-4 h-4 inline animate-spin mr-2" />Upload…</>
                : <><Upload className="w-4 h-4 inline mr-2" />Uploader un logo</>}
            </button>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-semibold text-slate-700">Ou générer avec l'IA :</div>
            <textarea value={briefLogo} onChange={e => setBriefLogo(e.target.value)}
                      placeholder="Brief (optionnel) : « pharmacie moderne, croix verte stylisée »"
                      rows={2} className="w-full px-3 py-2 border rounded-lg text-sm" />
            <input value={styleLogo} onChange={e => setStyleLogo(e.target.value)}
                   placeholder="Style (optionnel) : « minimaliste », « luxueux », « ludique »…"
                   className="w-full px-3 py-2 border rounded-lg text-sm" />
            <button onClick={genererLogo} disabled={!!busy}
                    className="w-full px-4 py-2 rounded-lg bg-violet-600 text-white font-semibold disabled:opacity-50">
              {busy === "gen_logo"
                ? <><Loader2 className="w-4 h-4 inline animate-spin mr-2" />Génération…</>
                : <><Wand2 className="w-4 h-4 inline mr-2" />Générer un logo par IA</>}
            </button>
            <div className="text-xs text-slate-500">~1 crédit par génération</div>
          </div>
        </div>
      </div>

      {/* Bannière */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <ImageIcon className="w-5 h-5 text-violet-600" />
          <h3 className="text-lg font-bold">Bannière</h3>
          <span className="text-xs text-slate-500">(format 16:9 · image hero de l'accueil)</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="aspect-video rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 flex items-center justify-center overflow-hidden">
              {bannUrl
                ? <img src={bannUrl} alt="bannière" className="w-full h-full object-cover" />
                : <div className="text-slate-400 text-sm">Aucune bannière</div>}
            </div>
            <input ref={bannFile} type="file" accept="image/png,image/jpeg,image/webp"
                   className="hidden" onChange={e => e.target.files?.[0] && uploaderBanniere(e.target.files[0])} />
            <button onClick={() => bannFile.current?.click()} disabled={!!busy}
                    className="w-full mt-2 px-4 py-2 rounded-lg border border-slate-300 font-semibold disabled:opacity-50">
              {busy === "upload_bann"
                ? <><Loader2 className="w-4 h-4 inline animate-spin mr-2" />Upload…</>
                : <><Upload className="w-4 h-4 inline mr-2" />Uploader une bannière</>}
            </button>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-semibold text-slate-700">Ou générer avec l'IA :</div>
            <textarea value={briefBann} onChange={e => setBriefBann(e.target.value)}
                      placeholder="Brief (optionnel) : « pharmacie chaleureuse, lumière du matin, ambiance accueillante »"
                      rows={2} className="w-full px-3 py-2 border rounded-lg text-sm" />
            <input value={styleBann} onChange={e => setStyleBann(e.target.value)}
                   placeholder="Style (optionnel) : « photographique », « illustration », « cinématique »…"
                   className="w-full px-3 py-2 border rounded-lg text-sm" />
            <button onClick={genererBanniere} disabled={!!busy}
                    className="w-full px-4 py-2 rounded-lg bg-violet-600 text-white font-semibold disabled:opacity-50">
              {busy === "gen_bann"
                ? <><Loader2 className="w-4 h-4 inline animate-spin mr-2" />Génération…</>
                : <><Wand2 className="w-4 h-4 inline mr-2" />Générer une bannière par IA</>}
            </button>
            <div className="text-xs text-slate-500">~1 crédit par génération</div>
          </div>
        </div>
      </div>

      {/* Info PWA */}
      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm text-emerald-900">
        <div className="font-semibold mb-1">📱 PWA — Installation sur l'écran d'accueil</div>
        <div>Dès que votre boutique est publiée et qu'un visiteur a un logo défini, Chrome / Safari proposent automatiquement « Ajouter à l'écran d'accueil ». L'icône utilisée est votre logo, le nom est celui de votre boutique. Aucune configuration supplémentaire requise.</div>
      </div>

      {/* Push notifications marchand */}
      <PushNotifSection />
    </div>
  );
};


const PushNotifSection = () => {
  const [statut, setStatut] = useState<"unsupported" | "granted" | "denied" | "default" | "loading">("loading");
  useEffect(() => {
    if (typeof Notification === "undefined" || !("PushManager" in window)) {
      setStatut("unsupported"); return;
    }
    setStatut(Notification.permission as any);
  }, []);
  const activer = async () => {
    const ok = await activerPushNotifications();
    setStatut(ok ? "granted" : (Notification.permission as any));
    if (ok) toast.success("Notifications activées — vous recevrez commandes/messages instantanément");
    else toast.error("Permission refusée ou navigateur non compatible");
  };
  if (statut === "loading") return null;
  return (
    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-900">
      <div className="font-semibold mb-1">🔔 Notifications instantanées (PWA)</div>
      <div className="mb-2">
        Recevez commandes, messages et avis en temps réel sur votre téléphone — même app fermée. Aucun coût SMS, fonctionne via la PWA installée.
      </div>
      {statut === "unsupported" && <div className="text-blue-700">Navigateur non compatible Web Push.</div>}
      {statut === "denied" && <div className="text-rose-700">Permission refusée — débloquez-la dans les paramètres du site.</div>}
      {statut === "default" && (
        <button onClick={activer}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold">
          Activer les notifications
        </button>
      )}
      {statut === "granted" && <div className="text-emerald-700 font-semibold">✓ Notifications activées</div>}
    </div>
  );
};


// ═══════════════════════════════════════════════════════════════════════════
// Promos — Coupons + Flash sales + Black Friday Yukpo
// ═══════════════════════════════════════════════════════════════════════════

const OngletPromos = ({ produits }: { produits: Produit[] }) => {
  const [sub, setSub] = useState<"coupons" | "flash" | "global">("coupons");
  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-slate-200">
        <SubTab label="Codes promo" icon={<Tag className="w-4 h-4" />} active={sub === "coupons"} onClick={() => setSub("coupons")} />
        <SubTab label="Ventes flash" icon={<Zap className="w-4 h-4" />} active={sub === "flash"} onClick={() => setSub("flash")} />
        <SubTab label="Événements Yukpo" icon={<Flame className="w-4 h-4" />} active={sub === "global"} onClick={() => setSub("global")} />
      </div>
      {sub === "coupons" && <CouponsSection />}
      {sub === "flash" && <FlashSaleSection produits={produits} />}
      {sub === "global" && <GlobalPromosSection produits={produits} />}
    </div>
  );
};

const SubTab = ({ label, icon, active, onClick }: any) => (
  <button onClick={onClick}
          className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium ${active ? "border-b-2 border-violet-600 text-violet-700" : "text-slate-600"}`}>
    {icon}<span>{label}</span>
  </button>
);

const CouponsSection = () => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ code: "", type: "pct", valeur: 10, min_panier: "", valable_au: "", usage_max: "", description: "", actif: true });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const r = await generateurApi.shopListerCoupons(); setItems(r.items || []); }
    catch (e: any) { toast.error(e?.response?.data?.detail || "Erreur"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const creer = async () => {
    if (!form.code.trim() || form.valeur <= 0) return toast.error("Code et valeur requis");
    setBusy(true);
    try {
      await generateurApi.shopCreerCoupon({
        code: form.code.trim().toUpperCase(),
        type: form.type, valeur: form.valeur,
        min_panier: form.min_panier ? Number(form.min_panier) : null,
        valable_au: form.valable_au || null,
        usage_max: form.usage_max ? Number(form.usage_max) : null,
        description: form.description || null,
        actif: form.actif,
      });
      toast.success("Coupon créé");
      setForm({ code: "", type: "pct", valeur: 10, min_panier: "", valable_au: "", usage_max: "", description: "", actif: true });
      load();
    } catch (e: any) { toast.error(e?.response?.data?.detail || "Erreur"); }
    finally { setBusy(false); }
  };

  const supprimer = async (id: number) => {
    if (!confirm("Supprimer ce coupon ?")) return;
    try { await generateurApi.shopSupprimerCoupon(id); toast.success("Supprimé"); load(); }
    catch (e: any) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <h3 className="font-bold mb-3">Nouveau code promo</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <input value={form.code} onChange={e => setForm({ ...form, code: e.target.value })}
                 placeholder="CODE (ex: OFFRE10)" className="px-3 py-2 border rounded-lg text-sm uppercase" />
          <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}
                  className="px-3 py-2 border rounded-lg text-sm">
            <option value="pct">% réduction</option>
            <option value="fixe">Montant fixe</option>
          </select>
          <input type="number" min={0} value={form.valeur} onChange={e => setForm({ ...form, valeur: Number(e.target.value) })}
                 placeholder={form.type === "pct" ? "% (1-100)" : "Montant"}
                 className="px-3 py-2 border rounded-lg text-sm" />
          <input type="number" min={0} value={form.min_panier} onChange={e => setForm({ ...form, min_panier: e.target.value })}
                 placeholder="Panier min (optionnel)" className="px-3 py-2 border rounded-lg text-sm" />
          <input type="datetime-local" value={form.valable_au} onChange={e => setForm({ ...form, valable_au: e.target.value })}
                 placeholder="Expire le" className="px-3 py-2 border rounded-lg text-sm" />
          <input type="number" min={1} value={form.usage_max} onChange={e => setForm({ ...form, usage_max: e.target.value })}
                 placeholder="Usage max (optionnel)" className="px-3 py-2 border rounded-lg text-sm" />
          <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                 placeholder="Description (visible client)" className="px-3 py-2 border rounded-lg text-sm md:col-span-2" />
        </div>
        <button disabled={busy} onClick={creer}
                className="mt-3 px-4 py-2 rounded-lg bg-violet-600 text-white font-semibold disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 inline animate-spin" /> : "Créer"}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center mb-3">
          <h3 className="font-bold flex-1">Coupons actifs ({items.length})</h3>
          <button onClick={load} className="px-2 py-1 text-sm border rounded-lg">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
        {!loading && items.length === 0 && <div className="text-center py-8 text-slate-500">Aucun coupon.</div>}
        <div className="space-y-2">
          {items.map(c => (
            <div key={c.id} className="flex items-center gap-3 p-3 border border-slate-200 rounded-lg">
              <div className="font-mono font-bold text-violet-700">{c.code}</div>
              <div className="flex-1 text-sm">
                <div>{c.type === "pct" ? `-${c.valeur}%` : `-${c.valeur} fixe`}{c.min_panier ? ` (min ${c.min_panier})` : ""}</div>
                <div className="text-xs text-slate-500">
                  {c.description || "—"} · Usages : {c.usage_count}{c.usage_max ? `/${c.usage_max}` : ""}
                  {c.valable_au && ` · expire ${new Date(c.valable_au).toLocaleDateString()}`}
                </div>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full ${c.actif ? "bg-emerald-100 text-emerald-700" : "bg-slate-100"}`}>{c.actif ? "actif" : "inactif"}</span>
              <button onClick={() => supprimer(c.id)} className="text-rose-500 hover:bg-rose-50 p-1.5 rounded">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const FlashSaleSection = ({ produits }: { produits: Produit[] }) => {
  const [form, setForm] = useState({ produit_id: 0, prix_flash: 0, debut: "", fin: "", stock_target: 10 });
  const [busy, setBusy] = useState(false);
  const creer = async () => {
    if (!form.produit_id || !form.debut || !form.fin || form.prix_flash <= 0) {
      return toast.error("Tous les champs requis");
    }
    setBusy(true);
    try {
      await generateurApi.shopCreerFlashSale({
        produit_id: form.produit_id, prix_flash: form.prix_flash,
        debut: new Date(form.debut).toISOString(),
        fin: new Date(form.fin).toISOString(),
        stock_target: form.stock_target,
      });
      toast.success("Vente flash créée — visible sur marketplace Yukpo");
      setForm({ produit_id: 0, prix_flash: 0, debut: "", fin: "", stock_target: 10 });
    } catch (e: any) { toast.error(e?.response?.data?.detail || "Erreur"); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <div className="bg-violet-50 border border-violet-200 rounded-xl p-4 text-sm text-violet-900">
        <Zap className="w-5 h-5 inline mr-1" /><b>Vente flash</b> — apparaît dans le flux <i>flash sales</i> du marketplace mobile Yukpo + push notif aux abonnés. Idéal pour écouler du stock ou booster un produit.
      </div>
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <h3 className="font-bold mb-3">Créer une vente flash</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <select value={form.produit_id} onChange={e => setForm({ ...form, produit_id: Number(e.target.value) })}
                  className="px-3 py-2 border rounded-lg text-sm">
            <option value={0}>— Choisir un produit —</option>
            {produits.filter(p => p.statut === "actif").map(p => (
              <option key={p.id} value={p.id}>{p.titre} ({p.prix_unit} {p.devise})</option>
            ))}
          </select>
          <input type="number" min={1} value={form.prix_flash} onChange={e => setForm({ ...form, prix_flash: Number(e.target.value) })}
                 placeholder="Prix flash" className="px-3 py-2 border rounded-lg text-sm" />
          <input type="datetime-local" value={form.debut} onChange={e => setForm({ ...form, debut: e.target.value })}
                 placeholder="Début" className="px-3 py-2 border rounded-lg text-sm" />
          <input type="datetime-local" value={form.fin} onChange={e => setForm({ ...form, fin: e.target.value })}
                 placeholder="Fin" className="px-3 py-2 border rounded-lg text-sm" />
          <input type="number" min={1} value={form.stock_target} onChange={e => setForm({ ...form, stock_target: Number(e.target.value) })}
                 placeholder="Stock à écouler" className="px-3 py-2 border rounded-lg text-sm md:col-span-2" />
        </div>
        <button disabled={busy} onClick={creer}
                className="mt-3 px-4 py-2 rounded-lg bg-violet-600 text-white font-semibold disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 inline animate-spin" /> : "Lancer la vente flash"}
        </button>
      </div>
    </div>
  );
};

const GlobalPromosSection = ({ produits }: { produits: Produit[] }) => {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<string>("");
  const [reduction, setReduction] = useState<number>(20);
  const [selectedProduits, setSelectedProduits] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const r = await generateurApi.shopGlobalPromosDisponibles(); setEvents(r.items || []); }
    catch { setEvents([]); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const inscrire = async () => {
    if (!selectedEvent || selectedProduits.size === 0) return toast.error("Sélectionnez événement + produits");
    setBusy(true);
    try {
      await generateurApi.shopJoindreGlobalPromo({
        event_id: selectedEvent,
        produit_ids: Array.from(selectedProduits),
        reduction_pct: reduction,
      });
      toast.success("Produits inscrits à l'événement Yukpo");
      setSelectedProduits(new Set());
    } catch (e: any) { toast.error(e?.response?.data?.detail || "Erreur"); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-900">
        <Flame className="w-5 h-5 inline mr-1" /><b>Événements Yukpo</b> (Black Friday, soldes…) — visibilité maximale : listing dédié sur l'app mobile + push notif à tous les utilisateurs Yukpo. Yukpo gère la promotion globale, vous gérez vos produits.
      </div>
      {loading && <div className="text-center py-8 text-slate-500">Chargement…</div>}
      {!loading && events.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500">
          Aucun événement actif pour le moment. Reviens lors du prochain Black Friday Yukpo.
        </div>
      )}
      {events.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <h3 className="font-bold mb-3">Inscrire mes produits</h3>
          <div className="space-y-2 mb-3">
            <select value={selectedEvent} onChange={e => setSelectedEvent(e.target.value)}
                    className="w-full px-3 py-2 border rounded-lg text-sm">
              <option value="">— Choisir un événement —</option>
              {events.map(ev => (
                <option key={ev.id || ev.event_id} value={ev.id || ev.event_id}>
                  {ev.nom || ev.name || "Événement"}
                  {ev.debut && ` · ${new Date(ev.debut).toLocaleDateString()}`}
                </option>
              ))}
            </select>
            <input type="number" min={1} max={90} value={reduction}
                   onChange={e => setReduction(Number(e.target.value))}
                   placeholder="% réduction"
                   className="w-full px-3 py-2 border rounded-lg text-sm" />
            <div className="text-sm font-semibold mt-3 mb-1">Produits à inscrire :</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1 max-h-60 overflow-y-auto">
              {produits.filter(p => p.statut === "actif").map(p => (
                <label key={p.id} className="flex items-center gap-2 p-2 hover:bg-slate-50 rounded">
                  <input type="checkbox" checked={selectedProduits.has(p.id)}
                         onChange={(e) => {
                           const s = new Set(selectedProduits);
                           if (e.target.checked) s.add(p.id); else s.delete(p.id);
                           setSelectedProduits(s);
                         }} />
                  <span className="text-sm">{p.titre}</span>
                </label>
              ))}
            </div>
          </div>
          <button disabled={busy} onClick={inscrire}
                  className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold disabled:opacity-50">
            {busy ? <Loader2 className="w-4 h-4 inline animate-spin" /> : `Inscrire ${selectedProduits.size} produit(s)`}
          </button>
        </div>
      )}
    </div>
  );
};
