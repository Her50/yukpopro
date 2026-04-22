import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bot, FileText, MessageSquare, Languages, TrendingUp, Sparkles,
  Zap, Users, ChevronRight, CreditCard, Calendar, Briefcase, MapPin, Building2,
  Gavel, ExternalLink,
} from "lucide-react";
import { Card, Badge, Spinner } from "@/components/ui";
import { useProfilStore, useCopiloteStore, useAuthStore } from "@/store";
import { profilApi, abonnementApi, emploiApi, marchesApi } from "@/api/client";
import type { ProfilPro } from "@/types";
import type { OffreEmploi, MarchePublic } from "@/api/client";

// ── Barre XP ──────────────────────────────────────────────────────────────────

const XPBar = ({ xp }: { xp: number }) => {
  const levels = [
    { name: "Starter", min: 0,    max: 100,      color: "bg-slate-500" },
    { name: "Junior",  min: 100,  max: 500,       color: "bg-accent-500" },
    { name: "Senior",  min: 500,  max: 2000,      color: "bg-yukpo-500" },
    { name: "Expert",  min: 2000, max: 5000,      color: "bg-gold-500" },
    { name: "Master",  min: 5000, max: Infinity,  color: "bg-gradient-to-r from-yukpo-500 to-gold-400" },
  ];
  const level = levels.find((l) => xp >= l.min && xp < l.max) || levels[levels.length - 1];
  const nextLevel = levels[levels.indexOf(level) + 1];
  const pct = nextLevel ? Math.min(((xp - level.min) / (nextLevel.min - level.min)) * 100, 100) : 100;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-gold-400" />
          <span className="text-sm font-bold text-gold-400">{level.name}</span>
        </div>
        <span className="text-sm text-slate-400">{xp.toLocaleString("fr-FR")} XP</span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${level.color}`} style={{ width: `${pct}%` }} />
      </div>
      {nextLevel && (
        <p className="text-xs text-slate-500">
          {(nextLevel.min - xp).toLocaleString("fr-FR")} XP pour atteindre <strong>{nextLevel.name}</strong>
        </p>
      )}
    </div>
  );
};

// ── Carte stat ────────────────────────────────────────────────────────────────

const StatCard = ({ icon: Icon, label, value, sub, color }: {
  icon: typeof Bot; label: string; value: number | string; sub?: string; color: string;
}) => (
  <Card className="p-4 flex items-center gap-3">
    <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
      <Icon className="w-5 h-5 text-white" />
    </div>
    <div>
      <p className="text-xl font-bold text-white">
        {typeof value === "number" ? value.toLocaleString("fr-FR") : value}
      </p>
      <p className="text-xs text-slate-400">{label}</p>
      {sub && <p className="text-xs text-slate-600">{sub}</p>}
    </div>
  </Card>
);

// ── Composant principal ───────────────────────────────────────────────────────

export const DashboardPage = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { profil, setProfil } = useProfilStore();
  const { sessions } = useCopiloteStore();
  const [loading, setLoading] = useState(!profil);
  const [abonnement, setAbonnement] = useState<Record<string, any> | null>(null);
  const [offresEmploi, setOffresEmploi] = useState<OffreEmploi[]>([]);
  const [marches, setMarches]           = useState<MarchePublic[]>([]);

  const prenom = user?.prenom || user?.nom?.split(" ")[0] || "";

  useEffect(() => {
    const load = async () => {
      try {
        if (!profil) {
          const p = await profilApi.get();
          setProfil(p);
        }
        const [a, config, marc] = await Promise.allSettled([
          abonnementApi.monAbonnement(),
          emploiApi.getConfig(),
          marchesApi.getRecents(),
        ]);
        if (a.status === "fulfilled") setAbonnement(a.value);
        if (config.status === "fulfilled") {
          setOffresEmploi((config.value.offres_emploi_recentes || []).slice(0, 3));
        }
        if (marc.status === "fulfilled") setMarches(marc.value.slice(0, 4));
      } catch (_) {}
      setLoading(false);
    };
    load();
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center space-y-3">
        <Spinner size="lg" />
        <p className="text-slate-400 text-sm">Chargement…</p>
      </div>
    </div>
  );

  const p = profil as ProfilPro | null;
  const totalDocs = (p?.nb_rapports_generes || 0) + (p?.nb_slides_generes || 0);
  const totalConvs = (p?.nb_requetes_copilote || 0) + (p?.nb_requetes_agent || 0);

  // Quota mensuel
  const quotaUsed   = abonnement?.requetes_utilisees || 0;
  const quotaTotal  = abonnement?.quota_jour || 10;
  const quotaPct    = Math.min(100, (quotaUsed / quotaTotal) * 100);
  const quotaColor  = quotaPct > 85 ? "bg-red-500" : quotaPct > 60 ? "bg-amber-500" : "bg-yukpo-500";

  // Dernières sessions (5 max)
  const recentSessions = [...sessions].slice(0, 5);

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto overflow-y-auto h-full">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl md:text-2xl font-display font-bold text-white">
            {prenom ? `Bonjour, ${prenom} 👋` : "Tableau de bord"}
          </h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {p
              ? `${p.metier?.replace(/_/g, " ")} · ${p.pays} · Niveau ${p.niveau_pro || "Starter"}`
              : "Bienvenue sur Yukpo Pro"}
          </p>
        </div>
        <button
          onClick={() => navigate("/chat")}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-yukpo-600 hover:bg-yukpo-500 text-white text-sm font-semibold transition-colors"
        >
          <Sparkles className="w-4 h-4" />
          Ouvrir Yukpo Pro
        </button>
      </div>

      {/* ── XP + Quota ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {p && (
          <Card className="p-5">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-gold-400" /> Progression
            </h3>
            <XPBar xp={p.xp_points || 0} />
          </Card>
        )}

        {abonnement && (
          <Card className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <CreditCard className="w-3.5 h-3.5" /> Quota mensuel
              </h3>
              <button
                onClick={() => navigate("/abonnement")}
                className="text-xs text-yukpo-400 hover:text-yukpo-300 transition-colors"
              >
                Voir mon plan →
              </button>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-300 font-semibold capitalize">{abonnement.plan || "Gratuit"}</span>
                <span className={quotaPct > 85 ? "text-red-400 font-semibold" : "text-slate-400"}>
                  {quotaUsed} / {quotaTotal === 9999 ? "∞" : quotaTotal} requêtes
                </span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${quotaColor}`}
                  style={{ width: `${quotaTotal === 9999 ? 5 : quotaPct}%` }}
                />
              </div>
              {quotaPct > 80 && quotaTotal !== 9999 && (
                <p className="text-xs text-amber-400">
                  Quota presque atteint —{" "}
                  <button onClick={() => navigate("/abonnement")} className="underline hover:text-white">
                    mettre à niveau
                  </button>
                </p>
              )}
            </div>
          </Card>
        )}
      </div>

      {/* ── Stats d'utilisation ── */}
      <div>
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
          Votre activité sur la plateforme
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            icon={MessageSquare} label="Conversations"
            value={totalConvs}
            sub={`dont ${p?.nb_requetes_agent || 0} via agents`}
            color="bg-yukpo-gradient"
          />
          <StatCard
            icon={FileText} label="Documents générés"
            value={totalDocs}
            sub={`${p?.nb_rapports_generes || 0} rapports · ${p?.nb_slides_generes || 0} slides`}
            color="bg-gradient-to-br from-gold-500 to-gold-600"
          />
          <StatCard
            icon={Languages} label="Traductions"
            value={p?.nb_traductions || 0}
            color="bg-gradient-to-br from-green-500 to-green-600"
          />
          <StatCard
            icon={Bot} label="Agents activés"
            value={p?.nb_requetes_agent || 0}
            color="bg-gradient-to-br from-accent-500 to-accent-600"
          />
        </div>
      </div>

      {/* ── Historique récent ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Dernières conversations */}
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-yukpo-400" />
              Conversations récentes
            </h3>
            <button
              onClick={() => navigate("/chat")}
              className="text-xs text-yukpo-400 hover:text-yukpo-300 transition-colors"
            >
              Voir tout →
            </button>
          </div>
          {recentSessions.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">
              Aucune conversation encore.{" "}
              <button onClick={() => navigate("/chat")} className="text-yukpo-400 hover:underline">
                Démarrer
              </button>
            </p>
          ) : (
            <div className="space-y-2">
              {recentSessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => navigate("/chat")}
                  className="w-full flex items-center gap-3 p-2.5 rounded-lg hover:bg-slate-800 transition-colors text-left group"
                >
                  <div className="w-8 h-8 rounded-lg bg-yukpo-500/20 flex items-center justify-center flex-shrink-0">
                    <MessageSquare className="w-3.5 h-3.5 text-yukpo-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-300 text-sm truncate group-hover:text-white">{s.title}</p>
                    <p className="text-slate-600 text-xs">{s.messages.length} message{s.messages.length > 1 ? "s" : ""}</p>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-400 flex-shrink-0" />
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* Accès rapide */}
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Zap className="w-4 h-4 text-gold-400" /> Accès rapide
          </h3>
          <div className="space-y-2">
            {[
              { icon: MessageSquare, label: "Yukpo Pro",      sub: "Assistant & agents spécialisés", path: "/chat",    color: "bg-yukpo-500/20 text-yukpo-400" },
              { icon: Users,         label: "Réunions",      sub: "Rapports & suivi auto",      path: "/reunions",   color: "bg-blue-500/20 text-blue-400" },
              { icon: TrendingUp,    label: "Mon Profil",     sub: "Personnaliser mon assistant", path: "/profil",    color: "bg-green-500/20 text-green-400" },
              { icon: Calendar,      label: "Abonnement",     sub: "Gérer mon plan",             path: "/abonnement", color: "bg-gold-500/20 text-gold-400" },
            ].map(({ icon: Icon, label, sub, path, color }) => (
              <button
                key={path}
                onClick={() => navigate(path)}
                className="w-full flex items-center gap-3 p-2.5 rounded-lg hover:bg-slate-800 transition-colors text-left group"
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${color}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <p className="text-slate-300 text-sm group-hover:text-white">{label}</p>
                  <p className="text-slate-600 text-xs">{sub}</p>
                </div>
                <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-400" />
              </button>
            ))}
          </div>
        </Card>
      </div>

      {/* ── Offres d'emploi ── */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Briefcase className="w-4 h-4 text-amber-400" />
            Offres d'emploi matchées
          </h3>
          <button
            onClick={() => navigate("/emploi")}
            className="text-xs text-yukpo-400 hover:text-yukpo-300 transition-colors"
          >
            Voir tout →
          </button>
        </div>
        {offresEmploi.length === 0 ? (
          <div className="text-center py-4 space-y-2">
            <p className="text-slate-500 text-sm">Aucune offre récente.</p>
            <button
              onClick={() => navigate("/emploi")}
              className="text-xs text-yukpo-400 hover:text-yukpo-300 transition-colors"
            >
              Configurer la veille emploi →
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {offresEmploi.map((offre, i) => {
              const score = offre.score ?? 0;
              const scoreColor = score >= 75 ? "text-green-400" : score >= 50 ? "text-amber-400" : "text-red-400";
              return (
                <div key={i} className="flex items-start gap-3 p-2.5 rounded-lg bg-slate-800/50 hover:bg-slate-800 transition-colors">
                  <div className="w-8 h-8 rounded-lg bg-amber-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Briefcase className="w-3.5 h-3.5 text-amber-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-200 text-sm font-medium truncate">{offre.titre}</p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      {offre.entreprise && (
                        <span className="flex items-center gap-1 text-xs text-slate-400">
                          <Building2 className="w-3 h-3" />{offre.entreprise}
                        </span>
                      )}
                      {offre.lieu && (
                        <span className="flex items-center gap-1 text-xs text-slate-500">
                          <MapPin className="w-3 h-3" />{offre.lieu}
                        </span>
                      )}
                    </div>
                  </div>
                  {score > 0 && (
                    <span className={`text-xs font-bold flex-shrink-0 ${scoreColor}`}>{score}%</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ── Marchés publics ── */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Gavel className="w-4 h-4 text-blue-400" />
            Marchés publics — Appels d'offres
          </h3>
          <span className="text-xs text-slate-500">Mis à jour toutes les 6h</span>
        </div>
        {marches.length === 0 ? (
          <div className="text-center py-4 space-y-1">
            <p className="text-slate-500 text-sm">Aucun appel d'offres récent dans votre secteur.</p>
            <p className="text-slate-600 text-xs">Yukpo surveille ARMP, dgMarket (Banque Mondiale), UNGM et les plateformes nationales.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {marches.map((m, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-blue-500/5 border border-blue-500/15 hover:border-blue-500/30 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-blue-500/15 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Gavel className="w-3.5 h-3.5 text-blue-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-slate-200 text-sm font-medium leading-snug line-clamp-2">{m.titre}</p>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    {m.organisme && (
                      <span className="flex items-center gap-1 text-xs text-slate-400">
                        <Building2 className="w-3 h-3" />{m.organisme}
                      </span>
                    )}
                    {m.source && (
                      <span className="text-xs text-blue-400/70">{m.source}</span>
                    )}
                    {m.date_pub && (
                      <span className="text-xs text-slate-600 ml-auto">{m.date_pub}</span>
                    )}
                  </div>
                </div>
                {m.url && (
                  <a
                    href={m.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 text-blue-400 hover:text-blue-300 transition-colors mt-1"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

    </div>
  );
};
