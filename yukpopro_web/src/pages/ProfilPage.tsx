import { useState, FormEvent, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { User, Save, Sparkles, PartyPopper, CheckCircle2, ArrowRight } from "lucide-react";
import toast from "react-hot-toast";
import { Card, Button, Input, Select, Badge } from "@/components/ui";
import { useProfilStore } from "@/store";
import { profilApi } from "@/api/client";
import { METIERS, PAYS_AFRIQUE } from "@/types";

const NIVEAUX_EXPERTISE = [
  { value: "debutant",       label: "Débutant (0-2 ans)" },
  { value: "intermediaire",  label: "Intermédiaire (2-5 ans)" },
  { value: "senior",         label: "Senior (5-10 ans)" },
  { value: "expert",         label: "Expert (10+ ans)" },
];

export const ProfilPage = () => {
  const { profil, setProfil } = useProfilStore();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isWelcome = searchParams.get("welcome") === "1";
  const [loading, setLoading] = useState(false);

  const [metier, setMetier] = useState(profil?.metier || "");
  const [pays, setPays] = useState(profil?.pays || "CM");
  const [secteur, setSecteur] = useState(profil?.secteur || "");
  const [entreprise, setEntreprise] = useState(profil?.entreprise || "");
  const [niveau, setNiveau] = useState(profil?.niveau_expertise || "intermediaire");
  const [annees, setAnnees] = useState(String(profil?.annees_experience || ""));
  const [bio, setBio] = useState(profil?.bio || "");

  useEffect(() => {
    if (!profil) {
      profilApi.get().then(setProfil).catch(console.error);
    }
  }, []);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const updated = await profilApi.update({
        metier,
        pays,
        secteur,
        entreprise,
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
  const niveauColor = {
    Starter: "text-slate-400",
    Junior:  "text-accent-400",
    Senior:  "text-yukpo-400",
    Expert:  "text-gold-400",
    Master:  "text-transparent bg-clip-text bg-gradient-to-r from-yukpo-400 to-gold-400",
  }[niveauPro] || "text-slate-400";

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto animate-fade-in">

      {/* ── Bannière de bienvenue — visible et orientante ─────────────────────── */}
      {isWelcome && (
        <div
          className="relative overflow-hidden rounded-2xl p-5"
          style={{
            background: "linear-gradient(135deg, #0054A6 0%, #003476 50%, #00B0F0 100%)",
            boxShadow: "0 4px 24px rgba(0,84,166,0.4)",
          }}
        >
          {/* Cercle décoratif */}
          <div
            className="absolute -top-6 -right-6 w-32 h-32 rounded-full opacity-20"
            style={{ background: "radial-gradient(circle, #00B0F0, transparent)" }}
          />
          <div className="relative flex items-start gap-4">
            <div
              className="flex-shrink-0 w-11 h-11 rounded-xl flex items-center justify-center"
              style={{ background: "rgba(255,255,255,0.2)" }}
            >
              <PartyPopper className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white font-bold text-base leading-tight">
                🎉 Bienvenue sur YukpoPro !
              </p>
              <p className="text-blue-100 text-sm mt-1 leading-relaxed">
                Votre compte est créé. <strong className="text-white">Configurez votre profil métier</strong> ci-dessous
                pour que votre assistant IA se spécialise dans votre domaine et votre pays.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {[
                  "Réponses adaptées à votre métier",
                  "Corpus juridique de votre pays",
                  "Agents spécialisés activés",
                ].map((item) => (
                  <span
                    key={item}
                    className="inline-flex items-center gap-1 text-xs text-blue-100 bg-white/15 rounded-full px-2.5 py-1"
                  >
                    <CheckCircle2 className="w-3 h-3 text-blue-200" />
                    {item}
                  </span>
                ))}
              </div>
              <div className="mt-3 flex items-center gap-1.5 text-xs text-blue-200 font-medium">
                <ArrowRight className="w-3.5 h-3.5" />
                Remplissez le formulaire et cliquez sur <strong className="text-white ml-1">Enregistrer le profil</strong>
              </div>
            </div>
          </div>
        </div>
      )}

      <div>
        <h1 className="text-2xl font-display font-bold text-white">Mon Profil</h1>
        <p className="text-slate-400 text-sm mt-1">Votre profil configure l'agent Yukpo spécialisé qui vous assiste.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Colonne gauche : carte identité + stats ─────────────────────────── */}
        <div className="space-y-4">
          {/* Carte identité */}
          <Card className="p-5 text-center space-y-3" style={{ border: "1px solid rgba(0,176,240,0.2)" }}>
            <div
              className="w-16 h-16 rounded-2xl mx-auto flex items-center justify-center shadow-lg"
              style={{ background: "linear-gradient(135deg, #0054A6, #00B0F0)" }}
            >
              <span className="text-2xl font-bold text-white">
                {(profil?.metier || "P").charAt(0).toUpperCase()}
              </span>
            </div>
            <div>
              <p className="text-white font-bold text-base">
                {profil?.metier
                  ? profil.metier.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
                  : "Professionnel"}
              </p>
              <p className="text-slate-400 text-sm mt-0.5">
                {[profil?.pays, profil?.secteur].filter(Boolean).join(" · ") || "Profil à configurer"}
              </p>
            </div>
            <div className="flex items-center justify-center gap-2 py-1 px-4 rounded-full mx-auto w-fit"
              style={{ background: "rgba(255,193,7,0.1)", border: "1px solid rgba(255,193,7,0.3)" }}>
              <Sparkles className="w-3.5 h-3.5 text-yellow-400" />
              <span className={`text-sm font-bold ${niveauColor}`}>{niveauPro}</span>
            </div>
            <p className="text-xs text-slate-500 font-medium">
              {(profil?.xp_points || 0).toLocaleString("fr-FR")} XP
            </p>
          </Card>

          {/* Stats utilisation */}
          <Card className="p-4 space-y-2.5" style={{ border: "1px solid rgba(0,176,240,0.15)" }}>
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-widest mb-3">Utilisation</h3>
            {[
              { icon: "💬", label: "Copilote", value: profil?.nb_requetes_copilote || 0 },
              { icon: "🤖", label: "Agents Yukpo", value: profil?.nb_requetes_agent || 0 },
              { icon: "📄", label: "Rapports", value: profil?.nb_rapports_generes || 0 },
              { icon: "📊", label: "Slides", value: profil?.nb_slides_generes || 0 },
              { icon: "🌍", label: "Traductions", value: profil?.nb_traductions || 0 },
            ].map(({ icon, label, value }) => (
              <div key={label} className="flex items-center justify-between py-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-base">{icon}</span>
                  <span className="text-sm text-slate-300">{label}</span>
                </div>
                <span className="text-sm font-bold text-white tabular-nums">
                  {value.toLocaleString("fr-FR")}
                </span>
              </div>
            ))}
          </Card>
        </div>

        {/* ── Formulaire ─────────────────────────────────────────────────────── */}
        <div className="lg:col-span-2">
          <Card className="p-6" style={{ border: "1px solid rgba(0,176,240,0.2)" }}>
            <form onSubmit={handleSave} className="space-y-5">
              <div className="flex items-center gap-2 pb-3 border-b border-slate-700/60">
                <User className="w-4 h-4 text-blue-400" />
                <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                  Informations professionnelles
                </h2>
              </div>

              <div>
                <label className="text-sm font-semibold text-slate-200 block mb-2">
                  Métier / Profession <span className="text-blue-400">*</span>
                </label>
                <select
                  value={metier}
                  onChange={(e) => setMetier(e.target.value)}
                  className="w-full rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  style={{
                    background: "rgba(15,23,42,0.8)",
                    border: "1px solid rgba(100,116,139,0.5)",
                    color: metier ? "white" : "rgb(148,163,184)",
                  }}
                >
                  <option value="" style={{ background: "#1e293b" }}>— Sélectionner votre métier —</option>
                  {METIERS.map((m) => (
                    <option key={m.value} value={m.value} style={{ background: "#1e293b" }}>{m.label}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-semibold text-slate-200 block mb-2">
                    Pays <span className="text-blue-400">*</span>
                  </label>
                  <select
                    value={pays}
                    onChange={(e) => setPays(e.target.value)}
                    className="w-full rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    style={{ background: "rgba(15,23,42,0.8)", border: "1px solid rgba(100,116,139,0.5)" }}
                  >
                    {PAYS_AFRIQUE.map((p) => (
                      <option key={p.value} value={p.value} style={{ background: "#1e293b" }}>{p.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-semibold text-slate-200 block mb-2">Niveau d'expertise</label>
                  <select
                    value={niveau}
                    onChange={(e) => setNiveau(e.target.value)}
                    className="w-full rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    style={{ background: "rgba(15,23,42,0.8)", border: "1px solid rgba(100,116,139,0.5)" }}
                  >
                    {NIVEAUX_EXPERTISE.map((n) => (
                      <option key={n.value} value={n.value} style={{ background: "#1e293b" }}>{n.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Secteur d'activité"
                  placeholder="Finance, BTP, Agroalimentaire…"
                  value={secteur}
                  onChange={(e) => setSecteur(e.target.value)}
                />
                <Input
                  label="Entreprise"
                  placeholder="Nom de votre organisation"
                  value={entreprise}
                  onChange={(e) => setEntreprise(e.target.value)}
                />
              </div>

              <Input
                label="Années d'expérience"
                type="number"
                min="0"
                max="50"
                placeholder="Ex: 8"
                value={annees}
                onChange={(e) => setAnnees(e.target.value)}
              />

              <div>
                <label className="text-sm font-semibold text-slate-200 block mb-2">Bio professionnelle</label>
                <textarea
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Décrivez votre expertise, vos spécialités, votre contexte de travail…"
                  rows={3}
                  className="w-full rounded-xl text-white placeholder-slate-500 px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                  style={{ background: "rgba(15,23,42,0.8)", border: "1px solid rgba(100,116,139,0.5)" }}
                />
              </div>

              {/* Bouton de sauvegarde — prominent pour le mode welcome */}
              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-bold text-white text-sm transition-all"
                style={{
                  background: loading
                    ? "rgba(0,84,166,0.5)"
                    : "linear-gradient(135deg, #0054A6, #00B0F0)",
                  boxShadow: loading ? "none" : "0 4px 16px rgba(0,84,166,0.4)",
                  opacity: loading ? 0.7 : 1,
                }}
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
