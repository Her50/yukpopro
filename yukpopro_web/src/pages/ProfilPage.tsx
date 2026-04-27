import { useState, FormEvent, useEffect, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { User, Save, Sparkles, ChevronDown, Search, Upload, Trash2, FileText, Camera } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Card, Input } from "@/components/ui";
import { useProfilStore } from "@/store";
import { profilApi, emploiApi } from "@/api/client";
import { METIERS, PAYS_MONDE, SECTEURS_ACTIVITE } from "@/types";
import { detectLanguageFromCountry } from "@/i18n";

function useIsMobile() {
  const [m, setM] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setM(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return m;
}

const NIVEAUX_EXPERTISE = [
  { value: "debutant",       label: "Débutant (0-2 ans)" },
  { value: "intermediaire",  label: "Intermédiaire (2-5 ans)" },
  { value: "senior",         label: "Senior (5-10 ans)" },
  { value: "expert",         label: "Expert (10+ ans)" },
];

// Select simple pour niveau (liste courte)
const FieldSelect = ({
  label, required, value, onChange, children,
}: {
  label: string; required?: boolean; value: string;
  onChange: (v: string) => void; children: React.ReactNode;
}) => (
  <div>
    <label className="block text-sm font-medium text-slate-300 mb-1.5">
      {label}{required && <span className="text-sky-400 ml-1">*</span>}
    </label>
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg px-3 py-2.5 text-sm text-slate-900 bg-white border border-slate-300 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500/40 transition-colors appearance-none"
    >
      {children}
    </select>
  </div>
);

// Combobox avec recherche pour listes longues (Métier, Secteur)
const ComboSelect = ({
  label, required, value, onChange, options, placeholder,
}: {
  label: string; required?: boolean; value: string;
  onChange: (v: string) => void;
  options: readonly { value: string; label: string }[];
  placeholder?: string;
}) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [rect, setRect] = useState<DOMRect | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const isMobile = useIsMobile();

  const selectedLabel = options.find((o) => o.value === value)?.label ?? "";

  const filtered = options.filter((o) =>
    o.label.toLowerCase().includes(search.toLowerCase())
  );

  const openDropdown = () => {
    if (btnRef.current) setRect(btnRef.current.getBoundingClientRect());
    setOpen(true);
    setSearch("");
  };

  const closeDropdown = () => { setOpen(false); setSearch(""); };

  useEffect(() => {
    if (!open || isMobile) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        closeDropdown();
      }
    };
    const onResize = () => {
      if (btnRef.current) setRect(btnRef.current.getBoundingClientRect());
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onResize, true);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onResize, true);
    };
  }, [open, isMobile]);

  // Lock body scroll while bottom-sheet open on mobile
  useEffect(() => {
    if (!open || !isMobile) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open, isMobile]);

  const dropdownStyle: React.CSSProperties = rect
    ? {
        position: "fixed",
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
        zIndex: 9999,
      }
    : {};

  return (
    <div ref={ref} className="relative">
      <label className="block text-sm font-medium text-slate-300 mb-1.5">
        {label}{required && <span className="text-sky-400 ml-1">*</span>}
      </label>
      <button
        ref={btnRef}
        type="button"
        onClick={() => open ? setOpen(false) : openDropdown()}
        className="w-full flex items-center justify-between rounded-lg px-3 py-2.5 text-sm bg-white border border-slate-300 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500/40 transition-colors text-left"
      >
        <span className={value ? "text-slate-900" : "text-slate-400"}>
          {selectedLabel || placeholder || "— Sélectionner —"}
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && !isMobile && (
        <div className="rounded-lg bg-white border border-slate-300 shadow-xl overflow-hidden" style={dropdownStyle}>
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-200">
            <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher…"
              className="flex-1 bg-transparent text-sm text-slate-900 placeholder-slate-400 focus:outline-none"
            />
          </div>
          <ul className="max-h-60 overflow-y-auto py-1">
            {filtered.length === 0 && (
              <li className="px-3 py-2 text-sm text-slate-400 italic">Aucun résultat</li>
            )}
            {filtered.map((o) => (
              <li
                key={o.value}
                onMouseDown={(e) => { e.preventDefault(); onChange(o.value); closeDropdown(); }}
                onTouchEnd={(e) => { e.preventDefault(); onChange(o.value); closeDropdown(); }}
                className={`px-3 py-2.5 text-sm cursor-pointer transition-colors leading-snug ${
                  o.value === value
                    ? "bg-sky-50 text-sky-700 font-medium"
                    : "text-slate-800 hover:bg-slate-100 active:bg-slate-200"
                }`}
              >
                {o.label}
              </li>
            ))}
          </ul>
        </div>
      )}

      {open && isMobile && (
        <>
          <div className="fixed inset-0 bg-black/60 z-[9998]" onClick={closeDropdown} />
          <div className="fixed inset-x-0 bottom-0 z-[9999] bg-white rounded-t-2xl shadow-2xl flex flex-col max-h-[85vh] animate-slide-up">
            <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-slate-200">
              <span className="text-sm font-semibold text-slate-700">{label}</span>
              <button type="button" onClick={closeDropdown}
                      className="text-sm text-sky-600 font-medium px-2 py-1">Fermer</button>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-200">
              <Search className="w-4 h-4 text-slate-400 shrink-0" />
              <input
                autoFocus
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Rechercher…"
                className="flex-1 bg-transparent text-base text-slate-900 placeholder-slate-400 focus:outline-none py-1.5"
              />
            </div>
            <ul className="overflow-y-auto py-1 flex-1 overscroll-contain">
              {filtered.length === 0 && (
                <li className="px-4 py-3 text-sm text-slate-400 italic">Aucun résultat</li>
              )}
              {filtered.map((o) => (
                <li
                  key={o.value}
                  onClick={() => { onChange(o.value); closeDropdown(); }}
                  className={`px-4 py-3 text-base cursor-pointer transition-colors leading-snug ${
                    o.value === value
                      ? "bg-sky-50 text-sky-700 font-semibold"
                      : "text-slate-800 active:bg-slate-200"
                  }`}
                >
                  {o.label}
                </li>
              ))}
            </ul>
            <div className="h-[env(safe-area-inset-bottom)]" />
          </div>
        </>
      )}
    </div>
  );
};

export const ProfilPage = () => {
  const { t, i18n } = useTranslation();
  const { profil, setProfil } = useProfilStore();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isWelcome = searchParams.get("welcome") === "1";
  const [loading, setLoading] = useState(false);
  const [cvUploading, setCvUploading] = useState(false);
  const [cvAvailable, setCvAvailable] = useState(false);
  const cvFileRef = useRef<HTMLInputElement>(null);
  const photoFileRef = useRef<HTMLInputElement>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoUploading, setPhotoUploading] = useState(false);

  const [metier, setMetier] = useState(profil?.metier || "");
  const [pays, setPays]     = useState(profil?.pays || "CM");

  // Secteur : si valeur en base n'est pas dans la liste → "autre" + custom
  const _secteurInitial = profil?.secteur || "";
  const _inList = SECTEURS_ACTIVITE.some((s) => s.value === _secteurInitial);
  const [secteurSelect, setSecteurSelect] = useState(_inList ? _secteurInitial : (_secteurInitial ? "autre" : ""));
  const [secteurCustom, setSecteurCustom] = useState(!_inList ? _secteurInitial : "");
  const secteur = secteurSelect === "autre" ? secteurCustom : secteurSelect;

  const [entreprise, setEntreprise] = useState(profil?.entreprise || "");
  const [niveau, setNiveau] = useState<string>(profil?.niveau_expertise || "intermediaire");
  const [annees, setAnnees] = useState(String(profil?.annees_experience || ""));
  const [bio, setBio]       = useState(profil?.bio || "");

  useEffect(() => {
    if (!profil) profilApi.get().then(setProfil).catch(console.error);
    else {
      setCvAvailable((profil as any).cv_disponible ?? false);
      if ((profil as any).has_photo && !photoUrl) {
        profilApi.getPhotoBlobUrl().then(setPhotoUrl).catch(() => {});
      }
    }
  }, [profil]);

  // Auto-détection pays + langue par IP si pas encore défini
  useEffect(() => {
    if (pays && pays !== "CM") return;
    fetch("https://ipapi.co/json/")
      .then((r) => r.json())
      .then((d) => {
        if (d?.country_code && d.country_code !== pays) {
          setPays(d.country_code);
          // Auto-switch langue UI uniquement si NI choix explicite NI langue OS détectée.
          // navigator.language reflète mieux la préférence réelle dans les pays bilingues.
          const stored = localStorage.getItem("yukpo_lang");
          const navLang = (navigator.language || "").slice(0, 2).toLowerCase();
          const supported = ["fr","en","es","pt","ar","de","zh","sw","ha","ru","hi","tr","wo","ln","am"];
          if (!stored && !supported.includes(navLang)) {
            const lang = detectLanguageFromCountry(d.country_code);
            i18n.changeLanguage(lang);
          }
        }
      })
      .catch(() => {});
  }, []);

  const handlePhotoFile = async (file: File) => {
    if (!file.type.startsWith("image/")) { toast.error("Fichier image requis"); return; }
    setPhotoUploading(true);
    try {
      await profilApi.uploadPhoto(file);
      const url = URL.createObjectURL(file);
      setPhotoUrl(url);
      toast.success("Photo de profil mise à jour");
    } catch {
      toast.error("Erreur lors de l'upload de la photo");
    } finally { setPhotoUploading(false); }
  };

  const handleDeletePhoto = async () => {
    if (!window.confirm("Supprimer la photo de profil ?")) return;
    try {
      await profilApi.supprimerPhoto();
      setPhotoUrl(null);
      toast.success("Photo supprimée");
    } catch { toast.error("Erreur"); }
  };

  const handleCvFile = async (file: File) => {
    if (!file) return;
    setCvUploading(true);
    try {
      await emploiApi.uploadCVFichier(file);
      setCvAvailable(true);
      toast.success(t("profil.cvUploadSuccess"));
    } catch {
      toast.error(t("profil.cvUploadError"));
    } finally {
      setCvUploading(false);
    }
  };

  const handleDeleteCv = async () => {
    if (!window.confirm(t("profil.cvDeleteConfirm"))) return;
    try {
      await emploiApi.supprimerCV();
      setCvAvailable(false);
      toast.success(t("profil.cvDeleteSuccess"));
    } catch {
      toast.error(t("common.error"));
    }
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const updated = await profilApi.update({
        metier, pays, secteur, entreprise,
        niveau_expertise: niveau as "debutant" | "intermediaire" | "senior" | "expert",
        annees_experience: annees ? parseInt(annees) : undefined,
        bio,
      });
      setProfil(updated);
      if (isWelcome) {
        toast.success("Profil configuré ! Bienvenue sur YukpoPro.");
        navigate("/chat");
      } else {
        toast.success("Profil mis à jour !");
      }
    } catch (err: unknown) {
      // Log détaillé pour diagnostic
      // eslint-disable-next-line no-console
      console.error("[ProfilPage] update failed:", err);
      const e = err as { response?: { status?: number; data?: { detail?: unknown } }; message?: string };
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      const detailStr = typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string; loc?: string[] }) => `${d.loc?.join(".")}: ${d.msg}`).join(" | ")
          : (e?.message ?? "Erreur inconnue");
      toast.error(`Erreur ${status ?? ""}: ${detailStr}`.slice(0, 200));
    } finally {
      setLoading(false);
    }
  };

  const niveauPro = profil?.niveau_pro || "Starter";
  const niveauColor: Record<string, string> = {
    Starter: "text-slate-200",
    Junior:  "text-emerald-300",
    Senior:  "text-sky-300",
    Expert:  "text-amber-300",
    Master:  "text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-amber-400",
  };

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-4xl mx-auto animate-fade-in pb-28 md:pb-6">

      {/* En-tête page */}
      <div>
        <h1 className="text-xl font-bold text-white">
          {isWelcome ? "🎉 Bienvenue ! Configurez votre profil" : "Mon Profil"}
        </h1>
        <p className="text-slate-400 text-sm mt-0.5">
          {isWelcome
            ? "Renseignez votre métier et votre pays pour personnaliser votre YukpoPro."
            : "Votre profil configure YukpoPro, votre assistant spécialisé."}
        </p>
      </div>

      <div className="flex flex-col gap-5 lg:grid lg:grid-cols-3">

        {/* Identité — toujours en haut */}
        <div className="order-1 lg:col-span-1">
          <Card className="p-5 text-center space-y-3 bg-slate-800/50 border border-slate-700">
            {/* Avatar cliquable avec photo ou initiale */}
            <div className="relative mx-auto w-20 h-20 group cursor-pointer"
                 onClick={() => photoFileRef.current?.click()}>
              {photoUrl ? (
                <img src={photoUrl} alt="Photo de profil"
                     className="w-20 h-20 rounded-2xl object-cover shadow-md border-2 border-slate-600" />
              ) : (
                <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-gradient-to-br from-sky-600 to-blue-700 shadow-md">
                  <span className="text-2xl font-bold text-white">
                    {(profil?.metier || "P").charAt(0).toUpperCase()}
                  </span>
                </div>
              )}
              {/* Overlay caméra au survol (desktop) */}
              <div className="absolute inset-0 rounded-2xl items-center justify-center
                              bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity hidden md:flex">
                {photoUploading
                  ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  : <Camera className="w-6 h-6 text-white" />}
              </div>
              {/* Badge caméra permanent (mobile + visuel discret desktop) */}
              <div className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-sky-600 border-2 border-slate-800 flex items-center justify-center shadow-md md:hidden">
                {photoUploading
                  ? <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  : <Camera className="w-3.5 h-3.5 text-white" />}
              </div>
            </div>
            <input ref={photoFileRef} type="file" accept="image/*" className="hidden"
                   onChange={(e) => e.target.files?.[0] && handlePhotoFile(e.target.files[0])} />
            {photoUrl && (
              <button onClick={handleDeletePhoto}
                      className="text-xs text-red-400 hover:text-red-300 transition-colors">
                <Trash2 className="w-3 h-3 inline mr-1" />Supprimer la photo
              </button>
            )}
            {!photoUrl && (
              <p className="text-xs text-slate-500">Touchez l'avatar pour ajouter une photo</p>
            )}
            <div>
              <p className="text-white font-semibold text-sm">
                {profil?.metier
                  ? profil.metier.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
                  : "Professionnel"}
              </p>
              <p className="text-slate-400 text-xs mt-0.5">
                {[profil?.pays, profil?.secteur].filter(Boolean).join(" · ") || "Profil à configurer"}
              </p>
            </div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-700/60 border border-slate-600">
              <Sparkles className="w-3 h-3 text-amber-400" />
              <span className={`text-xs font-semibold ${niveauColor[niveauPro] || "text-slate-400"}`}>
                {niveauPro}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              {(profil?.xp_points || 0).toLocaleString("fr-FR")} XP
            </p>
          </Card>
        </div>

        {/* Stats — sous le formulaire en mobile, sous l'identité en desktop */}
        <div className="order-3 lg:order-2 lg:col-span-1 lg:row-start-2">
          <Card className="p-4 space-y-2 bg-slate-800/50 border border-slate-700">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Utilisation</p>
            {[
              { icon: "💬", label: "Copilote",      value: profil?.nb_requetes_copilote || 0 },
              { icon: "🤖", label: "Agents",         value: profil?.nb_requetes_agent || 0 },
              { icon: "📄", label: "Rapports",       value: profil?.nb_rapports_generes || 0 },
              { icon: "📊", label: "Slides",         value: profil?.nb_slides_generes || 0 },
              { icon: "🌍", label: "Traductions",    value: profil?.nb_traductions || 0 },
            ].map(({ icon, label, value }) => (
              <div key={label} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{icon}</span>
                  <span className="text-sm text-slate-300">{label}</span>
                </div>
                <span className="text-sm font-semibold text-white tabular-nums">{value}</span>
              </div>
            ))}
          </Card>
        </div>

        {/* Formulaire */}
        <div className="order-2 lg:order-3 lg:col-span-2 lg:row-span-2 lg:row-start-1 lg:col-start-2">
          <Card className="p-5 bg-slate-800/50 border border-slate-700">
            <form onSubmit={handleSave} className="space-y-4">

              <div className="flex items-center gap-2 pb-3 border-b border-slate-700">
                <User className="w-4 h-4 text-sky-400" />
                <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wide">
                  Informations professionnelles
                </h2>
              </div>

              <ComboSelect
                label="Métier / Profession"
                required
                value={metier}
                onChange={setMetier}
                options={METIERS}
                placeholder="— Rechercher votre métier —"
              />

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <ComboSelect
                  label="Pays"
                  required
                  value={pays}
                  onChange={setPays}
                  options={PAYS_MONDE}
                  placeholder="— Rechercher votre pays —"
                />

                <FieldSelect label="Niveau d'expertise" value={niveau} onChange={setNiveau}>
                  {NIVEAUX_EXPERTISE.map((n) => (
                    <option key={n.value} value={n.value} className="bg-white">{n.label}</option>
                  ))}
                </FieldSelect>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <ComboSelect
                    label="Secteur d'activité"
                    value={secteurSelect}
                    onChange={setSecteurSelect}
                    options={SECTEURS_ACTIVITE}
                    placeholder="— Rechercher un secteur —"
                  />
                  {secteurSelect === "autre" && (
                    <input
                      type="text"
                      placeholder="Précisez votre secteur…"
                      value={secteurCustom}
                      onChange={(e) => setSecteurCustom(e.target.value)}
                      className="mt-2 w-full rounded-lg px-3 py-2 text-sm text-slate-900 bg-white border border-slate-300 placeholder-slate-400 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500/40 transition-colors"
                    />
                  )}
                </div>
                <Input
                  label="Entreprise / Organisation"
                  placeholder="Nom de l'organisation"
                  value={entreprise}
                  onChange={(e) => setEntreprise(e.target.value)}
                />
              </div>

              <Input
                label="Années d'expérience"
                type="number"
                min="0"
                max="50"
                placeholder="Ex : 8"
                value={annees}
                onChange={(e) => setAnnees(e.target.value)}
              />

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">
                  Bio professionnelle
                </label>
                <textarea
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Décrivez votre expertise, vos spécialités, votre contexte…"
                  rows={3}
                  className="w-full rounded-lg px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 bg-white border border-slate-300 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500/40 resize-none transition-colors"
                />
              </div>

              {/* ── Section CV ── */}
              <div className="pt-2 border-t border-slate-700/50">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-300 mb-2">
                  <FileText size={15} className="text-sky-400" />
                  {t("profil.cv")}
                </label>

                {cvAvailable ? (
                  <div className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg bg-emerald-50 border border-emerald-300 dark:bg-emerald-900/30 dark:border-emerald-500/30">
                    <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-200 text-sm font-medium">
                      <FileText size={15} />
                      <span>{t("profil.cvUploaded")}</span>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => cvFileRef.current?.click()}
                        className="text-xs text-sky-600 hover:text-sky-500 dark:text-sky-400 dark:hover:text-sky-300 underline font-medium"
                      >
                        {t("common.edit")}
                      </button>
                      <button
                        type="button"
                        onClick={handleDeleteCv}
                        className="text-xs text-red-400 hover:text-red-300"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    {/* Bouton plein sur mobile */}
                    <button
                      type="button"
                      onClick={() => cvFileRef.current?.click()}
                      disabled={cvUploading}
                      className="md:hidden w-full flex items-center justify-center gap-2 py-3 px-4 rounded-lg bg-sky-600/90 hover:bg-sky-500 text-white text-sm font-semibold disabled:opacity-60 transition-colors"
                    >
                      {cvUploading ? (
                        <>
                          <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                          {t("common.uploading")}
                        </>
                      ) : (
                        <>
                          <Upload size={16} />
                          {t("profil.cvUploadDesc")}
                        </>
                      )}
                    </button>

                    {/* Zone drag-drop sur desktop */}
                    <div
                      className="hidden md:block relative border-2 border-dashed border-slate-600 rounded-lg p-4 text-center cursor-pointer hover:border-sky-500/60 transition-colors group"
                      onClick={() => cvFileRef.current?.click()}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const f = e.dataTransfer.files?.[0];
                        if (f) handleCvFile(f);
                      }}
                    >
                      {cvUploading ? (
                        <div className="flex flex-col items-center gap-2 text-slate-400">
                          <span className="w-5 h-5 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
                          <span className="text-xs">{t("common.uploading")}</span>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center gap-1.5">
                          <Upload size={22} className="text-slate-500 group-hover:text-sky-400 transition-colors" />
                          <span className="text-sm text-slate-400 group-hover:text-slate-300">{t("profil.dragDropFile")}</span>
                          <span className="text-xs text-slate-500">{t("profil.cvUploadDesc")}</span>
                        </div>
                      )}
                    </div>
                  </>
                )}

                <input
                  ref={cvFileRef}
                  type="file"
                  accept=".pdf,.docx,.doc,.txt"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCvFile(f); }}
                />
              </div>

              <div className="md:static md:p-0 md:bg-transparent md:border-0
                              fixed inset-x-0 bottom-0 z-40 px-4 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]
                              bg-slate-900/95 backdrop-blur border-t border-slate-700">
                <div className="max-w-4xl mx-auto md:max-w-none md:mx-0">
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full flex items-center justify-center gap-2 py-3 rounded-lg text-sm font-semibold text-white transition-all bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed shadow-md"
                  >
                    {loading ? (
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <Save className="w-4 h-4" />
                    )}
                    {loading ? t("common.saving") : isWelcome ? `${t("profil.saveBtn")} →` : t("profil.saveBtn")}
                  </button>
                </div>
              </div>

            </form>
          </Card>
        </div>
      </div>
    </div>
  );
};
