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
  const ref = useRef<HTMLDivElement>(null);

  const selectedLabel = options.find((o) => o.value === value)?.label ?? "";

  const filtered = options.filter((o) =>
    o.label.toLowerCase().includes(search.toLowerCase())
  );

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <label className="block text-sm font-medium text-slate-300 mb-1.5">
        {label}{required && <span className="text-sky-400 ml-1">*</span>}
      </label>
      <button
        type="button"
        onClick={() => { setOpen((o) => !o); setSearch(""); }}
        className="w-full flex items-center justify-between rounded-lg px-3 py-2.5 text-sm bg-white border border-slate-300 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500/40 transition-colors text-left"
      >
        <span className={value ? "text-slate-900" : "text-slate-400"}>
          {selectedLabel || placeholder || "— Sélectionner —"}
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-lg bg-white border border-slate-300 shadow-xl overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-200">
            <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <input
              autoFocus
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher…"
              className="flex-1 bg-transparent text-sm text-slate-900 placeholder-slate-400 focus:outline-none"
            />
          </div>
          <ul className="max-h-52 overflow-y-auto py-1">
            {filtered.length === 0 && (
              <li className="px-3 py-2 text-sm text-slate-400 italic">Aucun résultat</li>
            )}
            {filtered.map((o) => (
              <li
                key={o.value}
                onMouseDown={() => { onChange(o.value); setOpen(false); setSearch(""); }}
                className={`px-3 py-2 text-sm cursor-pointer transition-colors ${
                  o.value === value
                    ? "bg-sky-50 text-sky-700 font-medium"
                    : "text-slate-800 hover:bg-slate-100"
                }`}
              >
                {o.label}
              </li>
            ))}
          </ul>
        </div>
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
      setCvAvailable(profil.cv_disponible ?? false);
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
          // Auto-switch langue interface si pas encore changée par l'utilisateur
          const stored = localStorage.getItem("yukpo_lang");
          if (!stored) {
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
    } catch {
      toast.error("Erreur lors de la mise à jour");
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
    <div className="p-6 space-y-5 max-w-4xl mx-auto animate-fade-in">

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Colonne gauche — identité */}
        <div className="space-y-4">
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
              {/* Overlay caméra au survol */}
              <div className="absolute inset-0 rounded-2xl flex items-center justify-center
                              bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
                {photoUploading
                  ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  : <Camera className="w-6 h-6 text-white" />}
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
              <p className="text-xs text-slate-500">Cliquez sur l'avatar pour ajouter une photo</p>
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
        <div className="lg:col-span-2">
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

              <div className="grid grid-cols-2 gap-3">
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

              <div className="grid grid-cols-2 gap-3">
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
                  <div
                    className="relative border-2 border-dashed border-slate-600 rounded-lg p-4 text-center cursor-pointer hover:border-sky-500/60 transition-colors group"
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
                )}

                <input
                  ref={cvFileRef}
                  type="file"
                  accept=".pdf,.docx,.doc,.txt"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCvFile(f); }}
                />
              </div>

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

            </form>
          </Card>
        </div>
      </div>
    </div>
  );
};
