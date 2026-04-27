import { useState } from "react";
import { User, Building2, Mail, Phone, Save, CheckCircle } from "lucide-react";
import { useAuthStore } from "@/store";
import toast from "react-hot-toast";

export function ProfilPage() {
  const { user } = useAuthStore();
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState({
    nom:       user?.nom || "",
    prenom:    user?.prenom || "",
    email:     user?.email || "",
    telephone: "",
    compagnie: user?.compagnie_nom || "",
    pays:      "Cameroun",
    fonction:  "Gestionnaire sinistres",
  });

  const handleSave = async () => {
    setSaved(true);
    toast.success("Profil mis à jour.");
    setTimeout(() => setSaved(false), 3000);
  };

  const PAYS_CIMA = ["Bénin", "Burkina Faso", "Cameroun", "Congo", "Côte d'Ivoire", "Gabon", "Mali", "Niger", "Sénégal", "Tchad", "Togo"];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4">
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          Mon Profil
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">Informations personnelles et compagnie</p>
      </div>

      <div className="px-8 max-w-xl pb-8">
        {/* Avatar */}
        <div className="flex items-center gap-5 mb-8 p-5 rounded-2xl border border-white/[0.06]"
          style={{ background: "rgba(17,24,39,0.8)" }}>
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold text-white flex-shrink-0"
            style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
            {(form.nom?.charAt(0) || user?.email?.charAt(0) || "U").toUpperCase()}
          </div>
          <div>
            <p className="text-base font-semibold text-white">{form.nom || user?.email}</p>
            <p className="text-sm text-gray-400">{form.compagnie || "YukpoAssurance"}</p>
            <p className="text-xs text-ciel-400 mt-0.5 capitalize">{user?.role?.replace(/_/g, " ") || "Utilisateur"}</p>
          </div>
        </div>

        {/* Formulaire */}
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            {[
              { key: "nom", label: "Nom", icon: User, placeholder: "Votre nom" },
              { key: "prenom", label: "Prénom", icon: User, placeholder: "Votre prénom" },
            ].map(({ key, label, icon: Icon, placeholder }) => (
              <div key={key}>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">{label}</label>
                <div className="relative">
                  <Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
                  <input
                    className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
                    placeholder={placeholder}
                    value={(form as Record<string, string>)[key]}
                    onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))}
                  />
                </div>
              </div>
            ))}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Email</label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
              <input type="email"
                className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
                value={form.email}
                onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Téléphone</label>
            <div className="relative">
              <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
              <input
                className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
                placeholder="+237 6XX XXX XXX"
                value={form.telephone}
                onChange={(e) => setForm((p) => ({ ...p, telephone: e.target.value }))}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Compagnie</label>
            <div className="relative">
              <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
              <input
                className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
                placeholder="Nom de votre compagnie"
                value={form.compagnie}
                onChange={(e) => setForm((p) => ({ ...p, compagnie: e.target.value }))}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Pays</label>
              <select
                className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-assurance-500/40 transition-all"
                value={form.pays}
                onChange={(e) => setForm((p) => ({ ...p, pays: e.target.value }))}>
                {PAYS_CIMA.map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Fonction</label>
              <select
                className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-assurance-500/40 transition-all"
                value={form.fonction}
                onChange={(e) => setForm((p) => ({ ...p, fonction: e.target.value }))}>
                {["Directeur", "Gestionnaire sinistres", "Souscripteur", "Actuaire", "Comptable", "Commercial"].map((f) => (
                  <option key={f}>{f}</option>
                ))}
              </select>
            </div>
          </div>

          <button onClick={handleSave}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-white hover:brightness-110 transition-all"
            style={{ background: saved ? "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)" : "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
            {saved ? <><CheckCircle className="w-4 h-4" />Enregistré</> : <><Save className="w-4 h-4" />Sauvegarder</>}
          </button>
        </div>
      </div>
    </div>
  );
}
