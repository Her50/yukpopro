import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Wallet, TrendingUp, TrendingDown, Zap, ArrowRight, RefreshCw,
  BarChart3, Activity, CreditCard, PlusCircle, Calendar, PieChart,
} from "lucide-react";
import { Card, Badge, Spinner, Button } from "@/components/ui";
import { abonnementApi } from "@/api/client";

type Solde = {
  plan: string;
  credits_alloues: number;
  credits_utilises: number;
  credits_restants: number;
  pct_utilise: number;
  label_plan: string;
  renouvellement_auto: boolean;
  renouvellement_le?: string;
  credits_en_fcfa_equiv: number;
};

type TopModule = { module: string; credits: number; appels: number; tokens: number };
type SerieJour = { jour: string; credits: number; appels: number };
type HistoriqueLigne = {
  id: number; date: string; modele: string; module: string;
  tokens_input: number; tokens_output: number; cout_fcfa: number; credits_debites: number;
};

type WalletData = {
  solde: Solde;
  periode_jours: number;
  totaux: { credits_consommes: number; appels: number; valeur_fcfa_payee: number };
  top_modules: TopModule[];
  serie_jour: SerieJour[];
  historique: HistoriqueLigne[];
};

const PLAN_COLORS: Record<string, string> = {
  gratuit: "#64748b",
  starter: "#0054A6",
  pro: "#00B0F0",
  business: "#FFD700",
};

const MODULE_LABELS: Record<string, string> = {
  chat: "Chat IA",
  traduction: "Traduction",
  translate_live: "Live",
  reunion: "Réunions",
  rapport: "Rapports",
  slides: "Slides",
  document: "Documents",
  ocr: "OCR",
  audio: "Audio",
  emploi: "Emploi",
  marches: "Marchés",
  enquetes: "Enquêtes",
  forfait: "Forfait",
  inconnu: "Autre",
};

export const WalletPage = () => {
  const [data, setData] = useState<WalletData | null>(null);
  const [loading, setLoading] = useState(true);
  const [jours, setJours] = useState(30);

  const charger = async () => {
    setLoading(true);
    try {
      const d = await abonnementApi.wallet(jours);
      setData(d);
    } catch (_) {}
    setLoading(false);
  };

  useEffect(() => { charger(); }, [jours]);

  const maxDay = useMemo(() => {
    if (!data?.serie_jour?.length) return 1;
    return Math.max(...data.serie_jour.map((s) => s.credits), 1);
  }, [data]);

  const maxModule = useMemo(() => {
    if (!data?.top_modules?.length) return 1;
    return Math.max(...data.top_modules.map((m) => m.credits), 1);
  }, [data]);

  if (loading || !data) {
    return <div className="flex items-center justify-center h-96"><Spinner /></div>;
  }

  const solde = data.solde;
  const pct = Math.min(100, Math.round(solde.pct_utilise));
  const pctColor = pct < 60 ? "#22c55e" : pct < 85 ? "#f59e0b" : "#ef4444";

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Wallet className="w-7 h-7 text-yukpo-500" />
            Mon Wallet
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Solde, consommations et historique de crédits IA
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={jours}
            onChange={(e) => setJours(Number(e.target.value))}
            className="px-3 py-2 rounded-lg border text-sm bg-card"
          >
            <option value={7}>7 jours</option>
            <option value={30}>30 jours</option>
            <option value={90}>90 jours</option>
            <option value={365}>1 an</option>
          </select>
          <Button variant="outline" size="sm" onClick={charger}>
            <RefreshCw className="w-4 h-4 mr-1" /> Actualiser
          </Button>
        </div>
      </div>

      {/* Hero : solde principal */}
      <Card className="p-6 relative overflow-hidden" style={{
        background: `linear-gradient(135deg, ${PLAN_COLORS[solde.plan] || "#0054A6"}18, transparent)`,
        borderLeft: `4px solid ${PLAN_COLORS[solde.plan] || "#0054A6"}`,
      }}>
        <div className="grid md:grid-cols-3 gap-6">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Solde disponible</p>
            <p className="text-4xl font-bold mt-2" style={{ color: PLAN_COLORS[solde.plan] || "#0054A6" }}>
              {solde.credits_restants.toLocaleString()}
            </p>
            <p className="text-xs text-muted-foreground mt-1">crédits Yukpo</p>
            <p className="text-sm font-medium mt-3">
              ≈ {(solde.credits_restants * 0.6).toLocaleString(undefined, { maximumFractionDigits: 0 })} FCFA de valeur
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Plan actif</p>
            <div className="mt-2 flex items-center gap-2">
              <Badge variant={solde.plan === "gratuit" ? "outline" : "default"} className="uppercase">{solde.plan}</Badge>
            </div>
            <p className="text-sm text-muted-foreground mt-2">{solde.label_plan}</p>
            {solde.renouvellement_le && (
              <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
                <Calendar className="w-3 h-3" /> Renouvellement : {solde.renouvellement_le}
              </p>
            )}
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Utilisation</p>
            <div className="mt-3 h-3 rounded-full bg-muted overflow-hidden">
              <div className="h-full transition-all" style={{ width: `${pct}%`, background: pctColor }} />
            </div>
            <div className="flex justify-between mt-2 text-xs">
              <span className="text-muted-foreground">{solde.credits_utilises.toLocaleString()} utilisés</span>
              <span className="font-semibold" style={{ color: pctColor }}>{pct}%</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">sur {solde.credits_alloues.toLocaleString()} alloués</p>
          </div>
        </div>

        {/* Raccourcis */}
        <div className="flex flex-wrap gap-2 mt-6 pt-4 border-t border-border/50">
          <Link to="/abonnement">
            <Button size="sm" className="gap-1">
              <CreditCard className="w-4 h-4" /> Gérer abonnement <ArrowRight className="w-3 h-3" />
            </Button>
          </Link>
          <Link to="/abonnement">
            <Button size="sm" variant="outline" className="gap-1">
              <PlusCircle className="w-4 h-4" /> Recharger crédits
            </Button>
          </Link>
        </div>
      </Card>

      {/* KPIs période */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-semibold uppercase">
            <Activity className="w-3 h-3" /> Consommés
          </div>
          <p className="text-2xl font-bold mt-2">{data.totaux.credits_consommes.toLocaleString()}</p>
          <p className="text-xs text-muted-foreground">crédits sur {jours}j</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-semibold uppercase">
            <Zap className="w-3 h-3" /> Appels IA
          </div>
          <p className="text-2xl font-bold mt-2">{data.totaux.appels.toLocaleString()}</p>
          <p className="text-xs text-muted-foreground">requêtes</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-semibold uppercase">
            <TrendingDown className="w-3 h-3" /> Valeur FCFA
          </div>
          <p className="text-2xl font-bold mt-2">{data.totaux.valeur_fcfa_payee.toLocaleString()}</p>
          <p className="text-xs text-muted-foreground">FCFA équiv.</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-semibold uppercase">
            <TrendingUp className="w-3 h-3" /> Moyenne/jour
          </div>
          <p className="text-2xl font-bold mt-2">
            {Math.round(data.totaux.credits_consommes / Math.max(1, jours)).toLocaleString()}
          </p>
          <p className="text-xs text-muted-foreground">crédits/jour</p>
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Graphique temporel */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold flex items-center gap-2">
              <BarChart3 className="w-5 h-5" /> Consommation quotidienne
            </h2>
            <span className="text-xs text-muted-foreground">{data.serie_jour.length} jours actifs</span>
          </div>
          {data.serie_jour.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">Aucune consommation sur la période.</p>
          ) : (
            <div className="flex items-end gap-1 h-48">
              {data.serie_jour.slice(-30).map((s) => {
                const h = (s.credits / maxDay) * 100;
                return (
                  <div key={s.jour} className="flex-1 flex flex-col items-center group relative">
                    <div
                      className="w-full rounded-t transition-all group-hover:opacity-80"
                      style={{
                        height: `${Math.max(h, 2)}%`,
                        background: `linear-gradient(180deg, #00B0F0, #0054A6)`,
                      }}
                    />
                    <div className="absolute -top-10 opacity-0 group-hover:opacity-100 bg-black text-white text-xs px-2 py-1 rounded whitespace-nowrap z-10 pointer-events-none">
                      {s.jour.slice(5)} : {s.credits.toFixed(0)} crédits ({s.appels} appels)
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Top modules consommateurs */}
        <Card className="p-6">
          <h2 className="font-bold flex items-center gap-2 mb-4">
            <PieChart className="w-5 h-5" /> Top consommateurs
          </h2>
          {data.top_modules.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">Aucune donnée.</p>
          ) : (
            <div className="space-y-3">
              {data.top_modules.slice(0, 8).map((m) => (
                <div key={m.module}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium">{MODULE_LABELS[m.module] || m.module}</span>
                    <span className="text-muted-foreground">
                      {m.credits.toLocaleString()} cr · {m.appels} appel(s)
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full transition-all"
                      style={{
                        width: `${(m.credits / maxModule) * 100}%`,
                        background: "linear-gradient(90deg, #00B0F0, #0054A6)",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Historique détaillé */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold flex items-center gap-2">
            <Activity className="w-5 h-5" /> Historique détaillé
          </h2>
          <span className="text-xs text-muted-foreground">{data.historique.length} dernière(s)</span>
        </div>
        {data.historique.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">Aucune consommation enregistrée.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground uppercase border-b">
                  <th className="py-2 pr-2">Date</th>
                  <th className="py-2 pr-2">Module</th>
                  <th className="py-2 pr-2">Modèle</th>
                  <th className="py-2 pr-2 text-right">Tokens</th>
                  <th className="py-2 pr-2 text-right">Coût</th>
                  <th className="py-2 text-right">Crédits</th>
                </tr>
              </thead>
              <tbody>
                {data.historique.map((h) => (
                  <tr key={h.id} className="border-b border-border/40 hover:bg-muted/30">
                    <td className="py-2 pr-2 text-xs">{new Date(h.date).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</td>
                    <td className="py-2 pr-2">
                      <Badge variant="outline" className="text-xs">{MODULE_LABELS[h.module] || h.module}</Badge>
                    </td>
                    <td className="py-2 pr-2 text-xs font-mono text-muted-foreground">{h.modele}</td>
                    <td className="py-2 pr-2 text-right text-xs text-muted-foreground">
                      {(h.tokens_input + h.tokens_output).toLocaleString()}
                    </td>
                    <td className="py-2 pr-2 text-right text-xs">{h.cout_fcfa.toFixed(2)} F</td>
                    <td className="py-2 text-right font-semibold">{h.credits_debites.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
