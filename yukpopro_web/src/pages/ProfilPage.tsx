import { useState, FormEvent, useEffect } from "react";
import { User, Save, Sparkles, Award, BarChart2 } from "lucide-react";
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
      toast.success("Profil mis à jour !");
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
      <div>
        <h1 className="text-2xl font-display font-bold text-white">Mon Profil</h1>
        <p className="text-slate-400 text-sm mt-1">Votre profil configure l'agent Yukpo spécialisé qui vous assiste.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Stats */}
        <div className="space-y-4">
          {/* Niveau */}
          <Card className="p-5 text-center space-y-3">
            <div className="w-16 h-16 rounded-2xl bg-yukpo-gradient mx-auto flex items-center justify-center shadow-yukpo">
              <span className="text-2xl font-bold text-white">
                {(profil?.metier || "P").charAt(0).toUpperCase()}
              </span>
            </div>
            <div>
              <p className="text-white font-semibold">{profil?.metier || "Professionnel"}</p>
              <p className="text-slate-400 text-sm">{profil?.pays} · {profil?.secteur || "Secteur non défini"}</p>
            </div>
            <div className="flex items-center justify-center gap-2">
              <Sparkles className="w-4 h-4 text-gold-400" />
              <span className={`text-lg font-bold font-display ${niveauColor}`}>{niveauPro}</span>
            </div>
            <p className="text-xs text-slate-500">{profil?.xp_points?.toLocaleString("fr-FR") || 0} XP</p>
          </Card>

          {/* Stats utilisation */}
          <Card className="p-4 space-y-3">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Utilisation</h3>
            {[
              { icon: "💬", label: "Copilote", value: profil?.nb_requetes_copilote || 0 },
              { icon: "🤖", label: "Agents Yukpo", value: profil?.nb_requetes_agent || 0 },
              { icon: "📄", label: "Rapports", value: profil?.nb_rapports_generes || 0 },
              { icon: "📊", label: "Slides", value: profil?.nb_slides_generes || 0 },
              { icon: "🌍", label: "Traductions", value: profil?.nb_traductions || 0 },
            ].map(({ icon, label, value }) => (
              <div key={label} className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <span>{icon}</span>
                  <span>{label}</span>
                </div>
                <span className="text-sm font-semibold text-white">{value.toLocaleString("fr-FR")}</span>
              </div>
            ))}
          </Card>
        </div>

        {/* Formulaire */}
        <div className="lg:col-span-2">
          <Card className="p-6">
            <form onSubmit={handleSave} className="space-y-4">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <User className="w-4 h-4 text-yukpo-400" />
                Informations professionnelles
              </h2>

              <div>
                <label className="text-sm font-medium text-slate-300 block mb-1.5">Métier / Profession</label>
                <select
                  value={metier}
                  onChange={(e) => setMetier(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                >
                  <option value="">— Sélectionner votre métier —</option>
                  {METIERS.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium text-slate-300 block mb-1.5">Pays</label>
                  <select
                    value={pays}
                    onChange={(e) => setPays(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                  >
                    {PAYS_AFRIQUE.map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-300 block mb-1.5">Niveau d'expertise</label>
                  <select
                    value={niveau}
                    onChange={(e) => setNiveau(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                  >
                    {NIVEAUX_EXPERTISE.map((n) => (
                      <option key={n.value} value={n.value}>{n.label}</option>
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
                <label className="text-sm font-medium text-slate-300 block mb-1.5">Bio professionnelle</label>
                <textarea
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Décrivez votre expertise, vos spécialités, votre contexte de travail…"
                  rows={3}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                />
              </div>

              <Button type="submit" loading={loading} icon={<Save className="w-4 h-4" />}>
                Enregistrer le profil
              </Button>
            </form>
          </Card>
        </div>
      </div>
    </div>
  );
};
