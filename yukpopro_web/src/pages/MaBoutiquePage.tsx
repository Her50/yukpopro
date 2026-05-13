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
  ArrowLeft, ExternalLink, Image as ImageIcon, Loader2, Package,
  RefreshCw, Send, ShoppingCart, Sparkles, Trash2, Upload, Wand2,
} from "lucide-react";
import toast from "react-hot-toast";
import { generateurApi } from "@/api/client";

type Produit = {
  id: number; titre: string; slug: string;
  prix_unit: number; devise: string; stock: number;
  photos_urls_json: string[] | null;
  statut: string; source: string;
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
  const [tab, setTab] = useState<"produits" | "commandes">("produits");
  const [busy, setBusy] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [importBrief, setImportBrief] = useState("");
  const [showInit, setShowInit] = useState(false);
  const [initForm, setInitForm] = useState({
    nom: "", description: "", devise: "XAF", pays_principal: "CM",
  });

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
    toast.loading(`Analyse de ${files.length} photo(s) par IA Opus Vision…`, { id: "magic" });
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

      {/* Magic Import IA */}
      <div className="bg-gradient-to-br from-violet-50 to-fuchsia-50 border border-violet-200 rounded-xl p-5 mb-6">
        <h2 className="font-bold text-lg text-violet-900 mb-2 flex items-center gap-2">
          <Wand2 className="w-5 h-5" />
          {t("shop.magic_titre", "Magic Import IA — Photos → produit complet")}
        </h2>
        <p className="text-sm text-violet-800 mb-3">
          {t("shop.magic_aide",
             "Uploadez 1 à 10 photos de votre produit. L'IA Opus Vision compose "
             + "automatiquement : titre vendeur SEO, description, prix suggéré, "
             + "catégorie, tags, variantes détectées.")}
        </p>
        <textarea value={importBrief} onChange={e => setImportBrief(e.target.value)}
                  placeholder={t("shop.magic_brief", "Brief optionnel : ex. 'sac à main cuir Italie haut de gamme'") as string}
                  rows={2} className="w-full px-3 py-2 mb-3 rounded-lg border border-violet-200 text-sm bg-white" />
        <input ref={fileRef} type="file" accept="image/*" multiple
               onChange={e => onMagicImport(e.target.files)}
               disabled={busy === "magic"} className="hidden" />
        <button onClick={() => fileRef.current?.click()} disabled={busy === "magic"}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white font-semibold min-h-[44px] disabled:opacity-50">
          {busy === "magic" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {t("shop.magic_btn", "Sélectionner photos (max 10)")}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-4 border-b border-slate-200">
        <button onClick={() => setTab("produits")}
                className={`px-4 py-2 text-sm font-medium ${tab === "produits" ? "border-b-2 border-violet-600 text-violet-700" : "text-slate-600"}`}>
          {t("shop.tab_produits", "Produits")} ({produits.length})
        </button>
        <button onClick={() => setTab("commandes")}
                className={`px-4 py-2 text-sm font-medium ${tab === "commandes" ? "border-b-2 border-violet-600 text-violet-700" : "text-slate-600"}`}>
          {t("shop.tab_commandes", "Commandes")} ({commandes.length})
        </button>
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
            <div key={p.id} className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md transition">
              {p.photos_urls_json?.[0] ? (
                <img src={p.photos_urls_json[0]} alt="" className="w-full aspect-square object-cover" />
              ) : (
                <div className="w-full aspect-square bg-slate-100 flex items-center justify-center text-slate-300">
                  <ImageIcon className="w-12 h-12" />
                </div>
              )}
              <div className="p-3">
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
                <div className="text-sm font-bold text-violet-700 mt-1">
                  {Math.round(p.prix_unit)} {p.devise}
                </div>
                <div className="text-xs text-slate-500 mt-1">Stock : {p.stock}</div>
                <div className="flex gap-1 mt-2">
                  <button onClick={() => onActiverProduit(p.id, p.statut)}
                          className="flex-grow text-xs px-2 py-1.5 rounded bg-slate-100 hover:bg-slate-200 min-h-[36px]">
                    {p.statut === "actif" ? t("shop.depublier_prod", "Brouillon") : t("shop.publier_prod", "Activer")}
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
    </div>
  );
};
