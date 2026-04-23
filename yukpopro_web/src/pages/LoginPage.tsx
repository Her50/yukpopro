import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, Mail, Lock, ArrowRight, CheckCircle2, Globe2, Shield, Zap } from "lucide-react";
import toast from "react-hot-toast";
import { Button, Input, YukpoLogo } from "@/components/ui";
import { useAuthStore, useProfilStore } from "@/store";
import { authApi, profilApi } from "@/api/client";
import { METIERS, PAYS_AFRIQUE } from "@/types";

type Mode = "login" | "register" | "onboarding";

const FEATURES = [
  { icon: Zap,          label: "13 agents IA spécialisés",     desc: "Comptable, DRH, Juriste, Banquier, DAF, ONG…" },
  { icon: Globe2,       label: "Corpus réglementaire africain", desc: "SYSCOHADA, OHADA, COBAC, CIMA, Codes fiscaux" },
  { icon: Shield,       label: "Sécurité niveau entreprise",    desc: "Données hébergées en Afrique, RGPD compatible" },
];

export const LoginPage = () => {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const { setProfil } = useProfilStore();

  const [mode, setMode] = useState<Mode>("login");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nom, setNom] = useState("");
  const [prenom, setPrenom] = useState("");
  const [metier, setMetier] = useState(METIERS[0]?.value || "comptable");
  const [pays, setPays] = useState(PAYS_AFRIQUE[0]?.value || "CM");
  const [secteur, setSecteur] = useState("");
  const [entreprise, setEntreprise] = useState("");

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    try {
      const data = await authApi.login(email, password);
      const me = await authApi.me();
      setAuth({ ...me, token: data.access_token }, data.access_token);
      const profil = await profilApi.get().catch(() => null);
      if (profil) { setProfil(profil); navigate("/dashboard"); }
      else setMode("onboarding");
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Email ou mot de passe incorrect";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password || !nom) return;
    setLoading(true);
    try {
      await authApi.register({ email, password, nom, prenom });
      const data = await authApi.login(email, password);
      const me = await authApi.me();
      setAuth({ ...me, token: data.access_token }, data.access_token);
      setMode("onboarding");
      toast.success("Compte créé ! Complétez votre profil métier.");
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Erreur lors de la création du compte";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleOnboarding = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const profil = await profilApi.create({ metier, pays, secteur, entreprise });
      setProfil(profil);
      navigate("/dashboard");
    } catch {
      toast.error("Erreur création profil");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" style={{ background: "#0f172a" }}>

      {/* ── Panneau gauche — identité Yukpo ──────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-[55%] xl:w-1/2 flex-col justify-between p-12 relative overflow-hidden"
        style={{ background: "linear-gradient(160deg, #1e2640 0%, #162033 60%, #0f172a 100%)" }}
      >
        {/* Fond décoratif */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
          {/* Halo corporate blue */}
          <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full opacity-20"
            style={{ background: "radial-gradient(circle, #0054A6, transparent 70%)" }} />
          {/* Halo bright accent */}
          <div className="absolute bottom-0 right-0 w-80 h-80 rounded-full opacity-10"
            style={{ background: "radial-gradient(circle, #00B0F0, transparent 70%)" }} />
          {/* Grille subtile */}
          <div className="absolute inset-0 opacity-[0.03]"
            style={{ backgroundImage: "linear-gradient(rgba(255,255,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.3) 1px, transparent 1px)", backgroundSize: "40px 40px" }} />
        </div>

        {/* Filet supérieur corporate */}
        <div className="absolute top-0 left-0 right-0 h-0.5"
          style={{ background: "linear-gradient(90deg, #0054A6, #00B0F0, #0054A6)" }} aria-hidden="true" />

        {/* Logo */}
        <div className="relative z-10">
          <YukpoLogo size={36} />
        </div>

        {/* Hero text */}
        <div className="relative z-10 space-y-8">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold"
              style={{ background: "rgba(0,84,166,0.2)", border: "1px solid rgba(0,176,240,0.3)", color: "#00B0F0" }}>
              ✦ Intelligence Professionnelle Africaine
            </div>
            <h1 className="text-4xl xl:text-5xl font-display font-bold text-white leading-[1.15] tracking-tight">
              Vos agents IA<br />
              <span style={{ background: "linear-gradient(90deg, #0054A6, #00B0F0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                pensent africain
              </span>
            </h1>
            <p className="text-base text-slate-400 leading-relaxed max-w-sm">
              Corpus juridique OHADA, SYSCOHADA, COBAC, CIMA — vos agents connaissent
              le droit et la comptabilité de vos marchés.
            </p>
          </div>

          {/* Feature list */}
          <div className="space-y-4">
            {FEATURES.map(({ icon: Icon, label, desc }) => (
              <div key={label} className="flex items-start gap-4">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                  style={{ background: "rgba(0,84,166,0.2)", border: "1px solid rgba(0,84,166,0.35)" }}>
                  <Icon className="w-4 h-4" style={{ color: "#00B0F0" }} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-100">{label}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Stat badges */}
          <div className="flex items-center gap-3 flex-wrap">
            {[
              { val: "13",   lbl: "agents IA" },
              { val: "6+",   lbl: "pays couverts" },
              { val: "99,9%",lbl: "disponibilité" },
            ].map(({ val, lbl }) => (
              <div key={lbl} className="px-4 py-2 rounded-lg text-center"
                style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
                <p className="text-xl font-bold text-white">{val}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider">{lbl}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <p className="text-xs text-slate-600 relative z-10">
          © {new Date().getFullYear()} Yukpo · Connect. Create. Solve.
        </p>
      </div>

      {/* ── Panneau droit — formulaires ──────────────────────────────────── */}
      <div
        className="flex-1 flex items-center justify-center p-6 lg:p-10"
        style={{ background: "linear-gradient(160deg, #162033 0%, #0f172a 100%)" }}
      >
        <div className="w-full max-w-md animate-fade-in">
          {/* Logo mobile */}
          <div className="lg:hidden flex justify-center mb-8">
            <YukpoLogo size={32} />
          </div>

          {/* ── LOGIN ──────────────────────────────────────────────────── */}
          {mode === "login" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-2xl font-display font-bold text-white">Connexion</h2>
                <p className="text-sm text-slate-400 mt-1">Accédez à vos agents professionnels IA</p>
              </div>

              <div className="p-8 rounded-xl space-y-5"
                style={{ background: "rgba(30,38,64,0.8)", border: "1px solid rgba(0,84,166,0.15)", boxShadow: "0 8px 40px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.03)" }}>
                <form onSubmit={handleLogin} className="space-y-4">
                  <Input
                    label="Email"
                    type="email"
                    placeholder="votre@email.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    icon={<Mail className="w-4 h-4" />}
                    required
                    autoComplete="email"
                  />
                  <div className="relative">
                    <Input
                      label="Mot de passe"
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      icon={<Lock className="w-4 h-4" />}
                      required
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-8 text-slate-500 hover:text-slate-300 transition-colors"
                      aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>

                  <Button type="submit" loading={loading} className="w-full mt-2" size="lg">
                    Se connecter <ArrowRight className="w-4 h-4" />
                  </Button>
                </form>
              </div>

              <p className="text-center text-sm text-slate-500">
                Pas encore de compte ?{" "}
                <button
                  onClick={() => setMode("register")}
                  className="font-semibold transition-colors"
                  style={{ color: "#00B0F0" }}
                >
                  Créer un compte
                </button>
              </p>
            </div>
          )}

          {/* ── REGISTER ───────────────────────────────────────────────── */}
          {mode === "register" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-2xl font-display font-bold text-white">Créer un compte</h2>
                <p className="text-sm text-slate-400 mt-1">Rejoignez les professionnels africains sur YukpoPro</p>
              </div>

              <div className="p-8 rounded-xl space-y-4"
                style={{ background: "rgba(30,38,64,0.8)", border: "1px solid rgba(0,84,166,0.15)", boxShadow: "0 8px 40px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.03)" }}>
                <form onSubmit={handleRegister} className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <Input label="Nom *" placeholder="KOME" value={nom} onChange={(e) => setNom(e.target.value)} required />
                    <Input label="Prénom" placeholder="Anatole" value={prenom} onChange={(e) => setPrenom(e.target.value)} />
                  </div>
                  <Input
                    label="Email *"
                    type="email"
                    placeholder="votre@email.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    icon={<Mail className="w-4 h-4" />}
                    required
                  />
                  <div className="relative">
                    <Input
                      label="Mot de passe *"
                      type={showPassword ? "text" : "password"}
                      placeholder="8 caractères minimum"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      icon={<Lock className="w-4 h-4" />}
                      required
                    />
                    <button type="button" onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-8 text-slate-500 hover:text-slate-300 transition-colors">
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>

                  <Button type="submit" loading={loading} className="w-full" size="lg">
                    Créer mon compte <ArrowRight className="w-4 h-4" />
                  </Button>
                </form>
              </div>

              <p className="text-center text-sm text-slate-500">
                Déjà un compte ?{" "}
                <button onClick={() => setMode("login")} className="font-semibold" style={{ color: "#00B0F0" }}>
                  Se connecter
                </button>
              </p>
            </div>
          )}

          {/* ── ONBOARDING ─────────────────────────────────────────────── */}
          {mode === "onboarding" && (
            <div className="space-y-6">
              {/* Progress */}
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1">
                  <CheckCircle2 className="w-4 h-4" style={{ color: "#10b981" }} />
                  <span className="text-xs text-slate-500">Compte créé</span>
                </div>
                <div className="flex-1 h-px" style={{ background: "rgba(0,84,166,0.3)" }} />
                <div className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold text-white"
                  style={{ background: "#0054A6" }}>2</div>
                <span className="text-xs text-slate-300 font-medium">Profil métier</span>
              </div>

              <div>
                <h2 className="text-2xl font-display font-bold text-white">Votre profil métier</h2>
                <p className="text-sm text-slate-400 mt-1">
                  Yukpo adapte automatiquement ses 13 agents à votre contexte professionnel.
                </p>
              </div>

              <div className="p-8 rounded-xl space-y-4"
                style={{ background: "rgba(30,38,64,0.8)", border: "1px solid rgba(0,84,166,0.15)", boxShadow: "0 8px 40px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.03)" }}>
                <form onSubmit={handleOnboarding} className="space-y-4">
                  <div>
                    <label className="text-xs font-semibold text-slate-300 tracking-wide uppercase block mb-1.5">
                      Votre métier *
                    </label>
                    <select
                      value={metier}
                      onChange={(e) => setMetier(e.target.value as any)}
                      className="w-full rounded-lg text-slate-100 px-4 py-2.5 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-corp-500/60"
                      style={{ background: "#1e2640", border: "1px solid rgba(255,255,255,0.09)" }}
                    >
                      {METIERS.map((m) => (
                        <option key={m.value} value={m.value} style={{ background: "#1e2640" }}>{m.label}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-slate-300 tracking-wide uppercase block mb-1.5">
                      Votre pays *
                    </label>
                    <select
                      value={pays}
                      onChange={(e) => setPays(e.target.value as any)}
                      className="w-full rounded-lg text-slate-100 px-4 py-2.5 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-corp-500/60"
                      style={{ background: "#1e2640", border: "1px solid rgba(255,255,255,0.09)" }}
                    >
                      {PAYS_AFRIQUE.map((p) => (
                        <option key={p.value} value={p.value} style={{ background: "#1e2640" }}>{p.label}</option>
                      ))}
                    </select>
                  </div>

                  <Input
                    label="Secteur d'activité"
                    placeholder="Finance, BTP, Agroalimentaire…"
                    value={secteur}
                    onChange={(e) => setSecteur(e.target.value)}
                  />
                  <Input
                    label="Entreprise / Organisation"
                    placeholder="Nom de votre organisation"
                    value={entreprise}
                    onChange={(e) => setEntreprise(e.target.value)}
                  />

                  <Button type="submit" loading={loading} className="w-full" size="lg" variant="gold">
                    Accéder à YukpoPro <ArrowRight className="w-4 h-4" />
                  </Button>
                </form>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
