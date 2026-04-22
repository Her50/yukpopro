import { useState, FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Eye, EyeOff, Mail, Lock, ArrowRight } from "lucide-react";
import toast from "react-hot-toast";
import { Button, Input, YukpoLogo, Card } from "@/components/ui";
import { useAuthStore, useProfilStore } from "@/store";
import { authApi, profilApi } from "@/api/client";
import { METIERS, PAYS_AFRIQUE } from "@/types";

type Mode = "login" | "register" | "onboarding";

export const LoginPage = () => {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const { setProfil } = useProfilStore();

  const [mode, setMode] = useState<Mode>("login");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  // Login form
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Register form
  const [nom, setNom] = useState("");
  const [prenom, setPrenom] = useState("");

  // Onboarding
  const [metier, setMetier] = useState(METIERS[0].value);
  const [pays, setPays] = useState(PAYS_AFRIQUE[0].value);
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
      // Charger le profil
      const profil = await profilApi.get().catch(() => null);
      if (profil) {
        setProfil(profil);
        navigate("/dashboard");
      } else {
        setMode("onboarding");
      }
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Email ou mot de passe incorrect";
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
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erreur lors de la création du compte";
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
      toast.success(`Bienvenue sur YukpoPro ! Agent ${metier} activé.`);
      navigate("/dashboard");
    } catch {
      toast.error("Erreur création profil");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" style={{ background: "#111827" }}>
      {/* Left — branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-dark-gradient relative overflow-hidden flex-col justify-between p-12">
        {/* Glow effects */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -left-40 w-96 h-96 bg-yukpo-500/20 rounded-full blur-3xl" />
          <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-accent-500/10 rounded-full blur-3xl" />
        </div>

        <YukpoLogo size={42} />

        <div className="relative z-10 space-y-6">
          <div>
            <h1 className="text-4xl font-display font-bold text-white leading-tight">
              L'Intelligence Professionnelle<br />
              <span className="text-transparent bg-clip-text bg-yukpo-gradient">Africaine</span>
            </h1>
            <p className="mt-4 text-lg text-slate-400 leading-relaxed">
              Vos 13 agents Yukpo spécialisés pour la comptabilité, le droit OHADA, les RH,
              la finance et plus encore — conçus pour l'Afrique francophone.
            </p>
          </div>

          {/* Feature bullets */}
          <div className="space-y-3">
            {[
              ["13 agents Yukpo spécialisés", "Comptable, DRH, Juriste, Banquier, DAF, ONG…"],
              ["Corpus réglementaire africain", "SYSCOHADA, OHADA, COBAC, CIMA, Codes fiscaux"],
              ["Yukpo Assistant", "Votre assistant naturel, toujours disponible"],
            ].map(([title, desc]) => (
              <div key={title} className="flex items-start gap-3">
                <div className="w-5 h-5 rounded-full bg-yukpo-gradient flex items-center justify-center flex-shrink-0 mt-0.5">
                  <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{title}</p>
                  <p className="text-xs text-slate-400">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs text-slate-600 relative z-10">
          © 2025 Yukpo · Connect. Create. Solve.
        </p>
      </div>

      {/* Right — auth forms */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md space-y-6 animate-fade-in">
          {/* Mobile logo */}
          <div className="lg:hidden flex justify-center mb-8">
            <YukpoLogo size={36} />
          </div>

          {/* ── LOGIN ─────────────────────────────────────────────────────── */}
          {mode === "login" && (
            <Card className="p-8 space-y-6">
              <div>
                <h2 className="text-2xl font-display font-bold text-white">Connexion</h2>
                <p className="text-slate-400 text-sm mt-1">Accédez à vos agents professionnels IA</p>
              </div>

              <form onSubmit={handleLogin} className="space-y-4">
                <Input
                  label="Email"
                  type="email"
                  placeholder="votre@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  icon={<Mail className="w-4 h-4" />}
                  required
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
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-9 text-slate-400 hover:text-white"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                <Button type="submit" loading={loading} className="w-full" size="lg">
                  Se connecter <ArrowRight className="w-4 h-4" />
                </Button>
              </form>

              <p className="text-center text-sm text-slate-400">
                Pas encore de compte ?{" "}
                <button onClick={() => setMode("register")} className="text-yukpo-400 hover:text-yukpo-300 font-medium">
                  Créer un compte
                </button>
              </p>
            </Card>
          )}

          {/* ── REGISTER ──────────────────────────────────────────────────── */}
          {mode === "register" && (
            <Card className="p-8 space-y-6">
              <div>
                <h2 className="text-2xl font-display font-bold text-white">Créer un compte</h2>
                <p className="text-slate-400 text-sm mt-1">Rejoignez les professionnels africains sur YukpoPro</p>
              </div>

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
                <Input
                  label="Mot de passe *"
                  type={showPassword ? "text" : "password"}
                  placeholder="8 caractères minimum"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  icon={<Lock className="w-4 h-4" />}
                  required
                />

                <Button type="submit" loading={loading} className="w-full" size="lg">
                  Créer mon compte <ArrowRight className="w-4 h-4" />
                </Button>
              </form>

              <p className="text-center text-sm text-slate-400">
                Déjà un compte ?{" "}
                <button onClick={() => setMode("login")} className="text-yukpo-400 hover:text-yukpo-300 font-medium">
                  Se connecter
                </button>
              </p>
            </Card>
          )}

          {/* ── ONBOARDING ────────────────────────────────────────────────── */}
          {mode === "onboarding" && (
            <Card className="p-8 space-y-6">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-6 h-6 rounded-full bg-yukpo-gradient flex items-center justify-center">
                    <span className="text-xs text-white font-bold">2</span>
                  </div>
                  <span className="text-xs text-yukpo-400 font-medium">Configuration initiale</span>
                </div>
                <h2 className="text-2xl font-display font-bold text-white">Votre profil métier</h2>
                <p className="text-slate-400 text-sm mt-1">
                  Yukpo adapte automatiquement tous ses agents à votre profil et contexte professionnel.
                </p>
              </div>

              <form onSubmit={handleOnboarding} className="space-y-4">
                <div>
                  <label className="text-sm font-medium text-slate-300 block mb-1.5">Votre métier *</label>
                  <select
                    value={metier}
                    onChange={(e) => setMetier(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                  >
                    {METIERS.map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-300 block mb-1.5">Votre pays *</label>
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
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};
