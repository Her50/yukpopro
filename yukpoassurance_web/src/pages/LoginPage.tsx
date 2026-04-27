import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, Eye, EyeOff, LogIn, UserPlus, Loader2 } from "lucide-react";
import toast from "react-hot-toast";
import { authApi } from "@/api/client";
import { useAuthStore } from "@/store";
import { cn } from "@/components/ui";
import type { User } from "@/types";

type Mode = "login" | "register";

export function LoginPage() {
  const navigate   = useNavigate();
  const { setAuth } = useAuthStore();
  const [mode, setMode]         = useState<Mode>("login");
  const [loading, setLoading]   = useState(false);
  const [showPwd, setShowPwd]   = useState(false);
  const [form, setForm]         = useState({ email: "", password: "", nom: "", compagnie: "" });
  const [error, setError]       = useState("");

  const set = (k: keyof typeof form, v: string) =>
    setForm((prev) => ({ ...prev, [k]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        const res = await authApi.login(form.email, form.password);
        const { access_token, user } = res.data as { access_token: string; user: User };
        setAuth(user, access_token);
        toast.success(`Bienvenue, ${user.nom || user.email} !`);
        navigate("/chat");
      } else {
        await authApi.register({ email: form.email, password: form.password, nom: form.nom, compagnie: form.compagnie });
        toast.success("Compte créé — connectez-vous.");
        setMode("login");
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || (mode === "login" ? "Email ou mot de passe incorrect." : "Erreur lors de l'inscription."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: "linear-gradient(135deg, #0D1117 0%, #111827 50%, #0D1117 100%)" }}>

      {/* Halo décoratif */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] opacity-20 pointer-events-none"
        style={{ background: "radial-gradient(ellipse, #0054A6 0%, transparent 70%)" }} />

      <div className="w-full max-w-md relative">

        {/* Card */}
        <div className="rounded-2xl border border-white/[0.08] p-8"
          style={{ background: "rgba(17,24,39,0.9)", backdropFilter: "blur(20px)", boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }}>

          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
              style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)", boxShadow: "0 0 30px rgba(0,84,166,0.4)" }}>
              <ShieldCheck className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              Yukpo<span style={{ color: "#00B0F0" }}>Assurance</span>
            </h1>
            <p className="text-sm text-gray-400 mt-1">Plateforme IA · Zone CIMA</p>
          </div>

          {/* Toggle mode */}
          <div className="flex rounded-xl border border-white/[0.06] mb-6 p-1" style={{ background: "rgba(255,255,255,0.03)" }}>
            {(["login", "register"] as Mode[]).map((m) => (
              <button key={m} onClick={() => { setMode(m); setError(""); }}
                className={cn(
                  "flex-1 py-2 text-sm font-medium rounded-lg transition-all",
                  mode === m ? "text-white" : "text-gray-400 hover:text-gray-200"
                )}
                style={mode === m ? { background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" } : {}}>
                {m === "login" ? "Connexion" : "Inscription"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">

            {/* Nom (register only) */}
            {mode === "register" && (
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">Nom complet</label>
                <input
                  className="w-full bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-ciel-500/50 focus:ring-1 focus:ring-ciel-500/30 transition-all"
                  placeholder="Votre nom"
                  value={form.nom}
                  onChange={(e) => set("nom", e.target.value)}
                  required
                />
              </div>
            )}

            {/* Email */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Adresse email</label>
              <input
                type="email"
                className="w-full bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-ciel-500/50 focus:ring-1 focus:ring-ciel-500/30 transition-all"
                placeholder="vous@compagnie.com"
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                required
                autoComplete="email"
              />
            </div>

            {/* Compagnie (register only) */}
            {mode === "register" && (
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">Compagnie d'assurance</label>
                <input
                  className="w-full bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-ciel-500/50 focus:ring-1 focus:ring-ciel-500/30 transition-all"
                  placeholder="Nom de votre compagnie"
                  value={form.compagnie}
                  onChange={(e) => set("compagnie", e.target.value)}
                />
              </div>
            )}

            {/* Mot de passe */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Mot de passe</label>
              <div className="relative">
                <input
                  type={showPwd ? "text" : "password"}
                  className="w-full bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-2.5 pr-11 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-ciel-500/50 focus:ring-1 focus:ring-ciel-500/30 transition-all"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={(e) => set("password", e.target.value)}
                  required
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                />
                <button type="button" onClick={() => setShowPwd((p) => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors">
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Erreur */}
            {error && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2.5 text-sm text-red-400">
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-white disabled:opacity-60 transition-all hover:brightness-110 active:scale-[0.98]"
              style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}
            >
              {loading ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Connexion…</>
              ) : mode === "login" ? (
                <><LogIn className="w-4 h-4" /> Se connecter</>
              ) : (
                <><UserPlus className="w-4 h-4" /> Créer le compte</>
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-gray-600 mt-4">
          Conforme Code CIMA · Zone Afrique
        </p>
      </div>
    </div>
  );
}
