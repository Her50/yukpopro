import { useState } from "react";
import { Lock, Bell, Palette, AlertTriangle, Eye, EyeOff, CheckCircle, Sun, Moon } from "lucide-react";
import toast from "react-hot-toast";
import { Card } from "@/components/ui";
import { authApi } from "@/api/client";
import { useUIStore } from "@/store";

const Section = ({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) => (
  <Card className="p-6 space-y-5 bg-slate-800/50 border border-slate-700">
    <div className="flex items-center gap-3 pb-3 border-b border-slate-700">
      <div className="w-8 h-8 rounded-lg bg-sky-600/20 border border-sky-500/30 flex items-center justify-center">
        <Icon className="w-4 h-4 text-sky-400" />
      </div>
      <h2 className="text-white font-semibold">{title}</h2>
    </div>
    {children}
  </Card>
);

export const ParametresPage = () => {
  const { theme, toggleTheme } = useUIStore();
  const isDark = theme === "dark";

  // Changement de mot de passe
  const [ancienMdp, setAncienMdp] = useState("");
  const [nouveauMdp, setNouveauMdp] = useState("");
  const [confirmMdp, setConfirmMdp] = useState("");
  const [showAncien, setShowAncien] = useState(false);
  const [showNouveau, setShowNouveau] = useState(false);
  const [mdpLoading, setMdpLoading] = useState(false);

  // Notifications (stockées en localStorage pour l'instant)
  const [notifEmail, setNotifEmail] = useState(() => localStorage.getItem("yukpo_notif_email") !== "false");
  const [notifPush, setNotifPush]   = useState(() => localStorage.getItem("yukpo_notif_push") !== "false");

  // Danger zone
  const [confirmSuppression, setConfirmSuppression] = useState("");

  const mdpValide = nouveauMdp.length >= 8
    && /[A-Z]/.test(nouveauMdp)
    && /[0-9]/.test(nouveauMdp)
    && nouveauMdp === confirmMdp;

  const handleChangerMdp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ancienMdp || !mdpValide) return;
    setMdpLoading(true);
    try {
      await authApi.changerMotDePasse(ancienMdp, nouveauMdp);
      toast.success("Mot de passe modifié avec succès");
      setAncienMdp(""); setNouveauMdp(""); setConfirmMdp("");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Erreur lors du changement de mot de passe");
    } finally { setMdpLoading(false); }
  };

  const toggleNotif = (key: "email" | "push", val: boolean) => {
    if (key === "email") { setNotifEmail(val); localStorage.setItem("yukpo_notif_email", String(val)); }
    else { setNotifPush(val); localStorage.setItem("yukpo_notif_push", String(val)); }
  };

  const regleMdp = [
    { label: "8 caractères minimum",    ok: nouveauMdp.length >= 8 },
    { label: "Une majuscule",            ok: /[A-Z]/.test(nouveauMdp) },
    { label: "Un chiffre",              ok: /[0-9]/.test(nouveauMdp) },
    { label: "Les mots de passe correspondent", ok: nouveauMdp === confirmMdp && confirmMdp.length > 0 },
  ];

  return (
    <div className="p-6 space-y-5 max-w-2xl mx-auto animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-white">Paramètres</h1>
        <p className="text-slate-400 text-sm mt-0.5">Sécurité, apparence et préférences de votre compte</p>
      </div>

      {/* Sécurité — Changement de mot de passe */}
      <Section icon={Lock} title="Sécurité">
        <form onSubmit={handleChangerMdp} className="space-y-4">
          {/* Ancien mot de passe */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Mot de passe actuel</label>
            <div className="relative">
              <input
                type={showAncien ? "text" : "password"}
                value={ancienMdp}
                onChange={(e) => setAncienMdp(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full rounded-lg px-3 py-2.5 pr-10 text-sm bg-slate-700/50 border border-slate-600
                           text-white placeholder-slate-500 focus:outline-none focus:border-sky-500
                           focus:ring-1 focus:ring-sky-500/40 transition-colors"
              />
              <button type="button" onClick={() => setShowAncien(v => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
                {showAncien ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Nouveau mot de passe */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Nouveau mot de passe</label>
            <div className="relative">
              <input
                type={showNouveau ? "text" : "password"}
                value={nouveauMdp}
                onChange={(e) => setNouveauMdp(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full rounded-lg px-3 py-2.5 pr-10 text-sm bg-slate-700/50 border border-slate-600
                           text-white placeholder-slate-500 focus:outline-none focus:border-sky-500
                           focus:ring-1 focus:ring-sky-500/40 transition-colors"
              />
              <button type="button" onClick={() => setShowNouveau(v => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
                {showNouveau ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Confirmer */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Confirmer le nouveau mot de passe</label>
            <input
              type="password"
              value={confirmMdp}
              onChange={(e) => setConfirmMdp(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full rounded-lg px-3 py-2.5 text-sm bg-slate-700/50 border border-slate-600
                         text-white placeholder-slate-500 focus:outline-none focus:border-sky-500
                         focus:ring-1 focus:ring-sky-500/40 transition-colors"
            />
          </div>

          {/* Règles de validation */}
          {nouveauMdp && (
            <ul className="space-y-1">
              {regleMdp.map(({ label, ok }) => (
                <li key={label} className={`flex items-center gap-2 text-xs ${ok ? "text-emerald-400" : "text-slate-500"}`}>
                  <CheckCircle className={`w-3.5 h-3.5 ${ok ? "text-emerald-400" : "text-slate-600"}`} />
                  {label}
                </li>
              ))}
            </ul>
          )}

          <button
            type="submit"
            disabled={!ancienMdp || !mdpValide || mdpLoading}
            className="w-full py-2.5 rounded-lg text-sm font-semibold text-white transition-all
                       bg-gradient-to-r from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500
                       disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {mdpLoading ? "Mise à jour…" : "Changer le mot de passe"}
          </button>
        </form>
      </Section>

      {/* Apparence */}
      <Section icon={Palette} title="Apparence">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-slate-200">Mode d'affichage</p>
            <p className="text-xs text-slate-500 mt-0.5">{isDark ? "Mode sombre activé" : "Mode clair activé"}</p>
          </div>
          <button
            onClick={toggleTheme}
            className={`relative w-12 h-6 rounded-full transition-colors ${isDark ? "bg-sky-600" : "bg-slate-600"}`}
          >
            <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform
                             ${isDark ? "translate-x-7" : "translate-x-1"}`} />
          </button>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-400 mt-1">
          <Sun className="w-4 h-4" /><span>Clair</span>
          <div className="flex-1 h-px bg-slate-700" />
          <span>Sombre</span><Moon className="w-4 h-4" />
        </div>
      </Section>

      {/* Notifications */}
      <Section icon={Bell} title="Notifications">
        {[
          { label: "Notifications par email", sub: "Résumés hebdomadaires, alertes de sécurité", val: notifEmail, key: "email" as const },
          { label: "Notifications push",      sub: "Alertes en temps réel dans le navigateur",  val: notifPush,  key: "push"  as const },
        ].map(({ label, sub, val, key }) => (
          <div key={key} className="flex items-center justify-between py-1">
            <div>
              <p className="text-sm font-medium text-slate-200">{label}</p>
              <p className="text-xs text-slate-500 mt-0.5">{sub}</p>
            </div>
            <button
              onClick={() => toggleNotif(key, !val)}
              className={`relative w-12 h-6 rounded-full transition-colors ${val ? "bg-sky-600" : "bg-slate-600"}`}
            >
              <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform
                               ${val ? "translate-x-7" : "translate-x-1"}`} />
            </button>
          </div>
        ))}
      </Section>

      {/* Danger zone */}
      <Section icon={AlertTriangle} title="Zone de danger">
        <p className="text-sm text-slate-400">
          La suppression de votre compte est irréversible. Toutes vos données (profil, documents, historique) seront définitivement effacées.
        </p>
        <div className="space-y-2">
          <label className="block text-sm font-medium text-slate-300">
            Tapez <span className="text-red-400 font-mono">SUPPRIMER</span> pour confirmer
          </label>
          <input
            type="text"
            value={confirmSuppression}
            onChange={(e) => setConfirmSuppression(e.target.value)}
            placeholder="SUPPRIMER"
            className="w-full rounded-lg px-3 py-2.5 text-sm bg-slate-700/50 border border-red-800/50
                       text-white placeholder-slate-600 focus:outline-none focus:border-red-500
                       focus:ring-1 focus:ring-red-500/40 transition-colors"
          />
          <button
            disabled={confirmSuppression !== "SUPPRIMER"}
            onClick={() => toast.error("Contactez le support à support@yukpomnang.com pour supprimer votre compte.")}
            className="w-full py-2.5 rounded-lg text-sm font-semibold text-white transition-all
                       bg-red-700/60 hover:bg-red-700 border border-red-600/50
                       disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Supprimer définitivement mon compte
          </button>
        </div>
      </Section>
    </div>
  );
};
