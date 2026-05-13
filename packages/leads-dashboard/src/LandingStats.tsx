/**
 * LandingStats — Carte stats Plausible inline pour 1 slug.
 *
 * Affichage compact : visiteurs, pageviews, taux rebond, sources top 5, pays
 * top 5. Récupéré depuis /pro/landing-publications/{slug}/stats?periode=30d.
 */
import { useEffect, useState } from "react";
import { BarChart3, Globe, TrendingUp } from "lucide-react";

export interface LandingStatsProps {
  http: { get: (url: string, config?: any) => Promise<any> };
  slug: string;
  periode?: string;
  t?: (key: string, fallback?: string) => string;
}

const _tf = (_k: string, fb?: string) => fb || _k;

export const LandingStats = ({
  http, slug, periode = "30d", t = _tf,
}: LandingStatsProps) => {
  const [data, setData] = useState<any | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let annule = false;
    setLoading(true); setErreur(null);
    http.get(`/pro/landing-publications/${slug}/stats`, { params: { periode } })
      .then(r => { if (!annule) setData(r.data); })
      .catch((e: any) => {
        if (annule) return;
        const detail = e?.response?.data?.detail || e?.message || "Erreur";
        // 503 = Plausible non configuré → message doux, pas alarmant
        if (e?.response?.status === 503) {
          setErreur(t("stats.plausible_off",
                      "Plausible Analytics non activé (clé API manquante)."));
        } else {
          setErreur(String(detail).slice(0, 200));
        }
      })
      .finally(() => { if (!annule) setLoading(false); });
    return () => { annule = true; };
  }, [http, slug, periode, t]);

  if (loading) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-4 text-sm text-slate-500">
        {t("stats.chargement", "Chargement statistiques…")}
      </div>
    );
  }
  if (erreur) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-900">
        {erreur}
      </div>
    );
  }
  if (!data) return null;

  const agg = data.aggregate || {};
  const visiteurs = agg.visitors?.value ?? 0;
  const pageviews = agg.pageviews?.value ?? 0;
  const bounce = agg.bounce_rate?.value ?? 0;
  const duree = agg.visit_duration?.value ?? 0;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
        <BarChart3 className="w-4 h-4 text-violet-600" />
        {t("stats.titre", "Statistiques")} {slug} · {periode}
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        <Kpi label={t("stats.visiteurs", "Visiteurs")} valeur={String(visiteurs)} />
        <Kpi label={t("stats.pageviews", "Pages vues")} valeur={String(pageviews)} />
        <Kpi label={t("stats.bounce", "Rebond")} valeur={`${bounce}%`} />
        <Kpi label={t("stats.duree", "Durée moy.")} valeur={`${Math.round(duree)}s`} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        <ListeTop
          icon={<TrendingUp className="w-3.5 h-3.5" />}
          titre={t("stats.sources", "Top sources")}
          items={(data.sources || []).slice(0, 5).map((s: any) => ({
            label: s.source || "(direct)", valeur: s.visitors,
          }))}
        />
        <ListeTop
          icon={<Globe className="w-3.5 h-3.5" />}
          titre={t("stats.pays", "Top pays")}
          items={(data.pays || []).slice(0, 5).map((c: any) => ({
            label: c.country || "?", valeur: c.visitors,
          }))}
        />
      </div>
    </div>
  );
};

const Kpi = ({ label, valeur }: { label: string; valeur: string }) => (
  <div className="bg-slate-50 rounded-lg p-2">
    <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
    <div className="text-lg font-bold text-slate-900">{valeur}</div>
  </div>
);

const ListeTop = ({ icon, titre, items }: {
  icon: React.ReactNode; titre: string;
  items: { label: string; valeur: number }[];
}) => (
  <div>
    <div className="font-medium text-slate-700 mb-1 flex items-center gap-1">
      {icon}{titre}
    </div>
    {items.length === 0 && (
      <div className="text-slate-400">{"—"}</div>
    )}
    <ul className="space-y-1">
      {items.map((it, i) => (
        <li key={i} className="flex justify-between gap-2">
          <span className="text-slate-700 truncate">{it.label}</span>
          <span className="text-slate-500 font-medium">{it.valeur}</span>
        </li>
      ))}
    </ul>
  </div>
);
