import { useState, FormEvent, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { User, Save, Sparkles } from "lucide-react";
import toast from "react-hot-toast";
import { Card, Input } from "@/components/ui";
import { useProfilStore } from "@/store";
import { profilApi } from "@/api/client";
import { METIERS, PAYS_AFRIQUE } from "@/types";

const NIVEAUX_EXPERTISE = [
  { value: "debutant",       label: "Débutant (0-2 ans)" },
  { value: "intermediaire",  label: "Intermédiaire (2-5 ans)" },
  { value: "senior",         label: "Senior (5-10 ans)" },
  { value: "expert",         label: "Expert (10+ ans)" },
];

// Champ select stylé pour le thème sombre
const FieldSelect = ({
  label, required, value, onChange, children,
}: {
  label: string;
  required?: boolean;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) => (
  <div>
    <label className="block text-sm font-medium text-slate-300 mb-1.5">
      {label}{required && <span className="text-sky-400 ml-1">*</span>}
    </label>
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg px-3 py-2.5 text-sm text-slate-100 bg-slate-700/60 border border-slate-600 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500/40 transition-colors appearance-none"
    >
      {children}
    </select>
  </div>
);

export const ProfilPage = () => {
  const { profil, setProfil } = useProfilStore();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isWelcome = searchParams.get("welcome") === "1";
  const [loading, setLoading] = useState(false);

  const [metier, setMetier] = useState(profil?.metier || "");
  const [pays, setPays]     = useState(profil?.pays || "CM");
  const [secteur, setSecteur]     = useState(profil?.secteur || "");
  const [entreprise, setEntreprise] = useState(profil?.entreprise || "");
  const [niveau, setNiveau] = useState<string>(profil?.niveau_expertise || "intermediaire");
  const [annees, setAnnees] = useState(String(profil?.annees_experience || ""));
  const [bio, setBio]       = useState(profil?.bio || "");

  useEffect(() => {
    if (!profil) profilApi.get().then(setProfil).catch(console.error);
  }, []);

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
    Starter: "text-slate-400",
    Junior:  "text-emerald-400",
    Senior:  "text-sky-400",
    Expert:  "text-amber-400",
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
            ? "Renseignez votre métier et votre pays pour personnaliser votre assistant IA."
            : "Votre profil configure l'assistant IA Yukpo spécialisé pour vous."}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Colonne gauche — identité */}
        <div className="space-y-4">
          <Card className="p-5 text-center space-y-3 bg-slate-800/50 border border-slate-700">
            <div className="w-14 h-14 rounded-xl mx-auto flex items-center justify-center bg-gradient-to-br from-sky-600 to-blue-700 shadow-md">
              <span className="text-xl font-bold text-white">
                {(profil?.metier || "P").charAt(0).toUpperCase()}
              </span>
            </div>
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

              <FieldSelect label="Métier / Profession" required value={metier} onChange={setMetier}>
                <option value="" className="bg-slate-800">— Sélectionner votre métier —</option>
                {METIERS.map((m) => (
                  <option key={m.value} value={m.value} className="bg-slate-800">{m.label}</option>
                ))}
              </FieldSelect>

              <div className="grid grid-cols-2 gap-3">
                <FieldSelect label="Pays" required value={pays} onChange={setPays}>
                  {PAYS_AFRIQUE.map((p) => (
                    <option key={p.value} value={p.value} className="bg-slate-800">{p.label}</option>
                  ))}
                </FieldSelect>

                <FieldSelect label="Niveau d'expertise" value={niveau} onChange={setNiveau}>
                  {NIVEAUX_EXPERTISE.map((n) => (
                    <option key={n.value} value={n.value} className="bg-slate-800">{n.label}</option>
                  ))}
                </FieldSelect>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Secteur d'activité"
                  placeholder="Finance, BTP, Agro…"
                  value={secteur}
                  onChange={(e) => setSecteur(e.target.value)}
                />
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
                  className="w-full rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 bg-slate-700/60 border border-slate-600 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500/40 resize-none transition-colors"
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
                {loading ? "Enregistrement…" : isWelcome ? "Enregistrer et accéder à YukpoPro →" : "Enregistrer le profil"}
              </button>

            </form>
          </Card>
        </div>
      </div>
    </div>
  );
};
