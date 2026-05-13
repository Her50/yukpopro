/**
 * LeadsDashboard — Composant partagé "Mes Leads" YukpoPro + YukpoSecrétariat.
 *
 * Filtres : landing (slug), statut, période. Actions : marquer contacté/converti,
 * appeler/whatsapp/email direct, export CSV, copier coordonnées.
 *
 * Mobile-first responsive Tailwind. Toutes les chaînes passent par `t()`
 * fourni en prop (pour rester agnostique au backend i18n de l'app hôte).
 */
import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2, Copy, Download, Filter, Mail, MessageCircle,
  Phone, RefreshCw, Search, Tag, TrendingUp, X,
} from "lucide-react";
import {
  leadsApi, type HttpClient, type LeadRow, type LeadsListResponse,
  type PublicationRow, type StatutLead,
} from "./api";
import { LandingStats } from "./LandingStats";

export interface LeadsDashboardProps {
  /** Client HTTP injecté (axios ou équivalent), avec auth + baseURL "/api/v1". */
  http: HttpClient;
  /** Traduction t('key', fallback?). Si non fourni, utilise les fallbacks FR. */
  t?: (key: string, fallback?: string) => string;
  /** Pré-filtre slug (utile sur page dédiée d'une publication). */
  slug?: string;
  /** Affiche le sélecteur de slug (faux si déjà filtré par route). */
  showSlugFilter?: boolean;
}

const STATUTS: { value: StatutLead; labelKey: string; fallback: string; tone: string }[] = [
  { value: "non_lu",   labelKey: "leads.statut.non_lu",   fallback: "Non lu",    tone: "bg-blue-100 text-blue-800" },
  { value: "lu",       labelKey: "leads.statut.lu",       fallback: "Lu",        tone: "bg-slate-100 text-slate-700" },
  { value: "contacte", labelKey: "leads.statut.contacte", fallback: "Contacté",  tone: "bg-amber-100 text-amber-800" },
  { value: "converti", labelKey: "leads.statut.converti", fallback: "Converti",  tone: "bg-green-100 text-green-800" },
  { value: "perdu",    labelKey: "leads.statut.perdu",    fallback: "Perdu",     tone: "bg-rose-100 text-rose-700" },
];

const PERIODES = [
  { jours: 7,   labelKey: "leads.periode.7j",   fallback: "7j" },
  { jours: 30,  labelKey: "leads.periode.30j",  fallback: "30j" },
  { jours: 90,  labelKey: "leads.periode.90j",  fallback: "90j" },
  { jours: 365, labelKey: "leads.periode.1an",  fallback: "1 an" },
];

const _tFallback = (_k: string, fb?: string) => fb || _k;

export const LeadsDashboard = ({
  http, t = _tFallback, slug: slugProp, showSlugFilter = true,
}: LeadsDashboardProps) => {
  const api = useMemo(() => leadsApi(http), [http]);

  const [pubs, setPubs] = useState<PublicationRow[]>([]);
  const [slug, setSlug] = useState<string>(slugProp || "");
  const [statut, setStatut] = useState<StatutLead | "">("");
  const [jours, setJours] = useState<number>(30);
  const [recherche, setRecherche] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);
  const [data, setData] = useState<LeadsListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    if (!showSlugFilter) return;
    api.publications().then(r => setPubs(r.publications || [])).catch(() => { /* ignore */ });
  }, [api, showSlugFilter]);

  useEffect(() => {
    let annule = false;
    setLoading(true);
    setErreur(null);
    api.list({
      slug: slug || undefined,
      statut: (statut || undefined) as StatutLead | undefined,
      jours,
      limit: 100,
    })
      .then(r => { if (!annule) setData(r); })
      .catch((e: any) => {
        if (annule) return;
        setErreur(e?.response?.data?.detail || e?.message || "Erreur");
      })
      .finally(() => { if (!annule) setLoading(false); });
    return () => { annule = true; };
  }, [api, slug, statut, jours, refreshTick]);

  const leads = data?.leads || [];
  const leadsFiltres = useMemo(() => {
    if (!recherche.trim()) return leads;
    const q = recherche.toLowerCase();
    return leads.filter(l =>
      (l.nom || "").toLowerCase().includes(q)
      || (l.email || "").toLowerCase().includes(q)
      || (l.telephone || "").toLowerCase().includes(q)
      || (l.message || "").toLowerCase().includes(q),
    );
  }, [leads, recherche]);

  const setStatutLead = async (lead_id: number, st: StatutLead) => {
    try {
      await api.patch(lead_id, { statut: st });
      setRefreshTick(t => t + 1);
    } catch (e: any) {
      alert(t("leads.erreur_maj", "Erreur mise à jour : ") + (e?.message || ""));
    }
  };

  const copier = (val: string) => {
    if (!val) return;
    navigator.clipboard?.writeText(val).catch(() => { /* ignore */ });
  };

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      {/* En-tête + KPIs */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold">
            {t("leads.titre", "Mes leads")}
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {t("leads.sous_titre",
               "Contacts capturés via vos landings publiées")}
          </p>
        </div>
        <button
          onClick={() => setRefreshTick(t => t + 1)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg
                     bg-slate-100 hover:bg-slate-200 text-sm font-medium
                     min-h-[44px]"
          aria-label={t("leads.refresh", "Rafraîchir")}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          {t("leads.refresh", "Rafraîchir")}
        </button>
      </div>

      {/* Stats KPIs */}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <KpiCard
            label={t("leads.kpi.total", "Total leads")}
            valeur={String(data.total)} tone="bg-blue-50 text-blue-900"
          />
          <KpiCard
            label={t("leads.kpi.non_lu", "Non lus")}
            valeur={String(data.par_statut?.non_lu || 0)}
            tone="bg-rose-50 text-rose-900"
          />
          <KpiCard
            label={t("leads.kpi.converti", "Convertis")}
            valeur={String(data.par_statut?.converti || 0)}
            tone="bg-emerald-50 text-emerald-900"
          />
          <KpiCard
            label={t("leads.kpi.taux", "Taux conversion")}
            valeur={`${data.taux_conversion_pct}%`}
            tone="bg-violet-50 text-violet-900"
            icon={<TrendingUp className="w-4 h-4 opacity-60" />}
          />
        </div>
      )}

      {/* Filtres */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          {showSlugFilter && (
            <select
              value={slug} onChange={e => setSlug(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-300 text-sm
                         min-h-[44px] flex-grow min-w-[180px]"
            >
              <option value="">
                {t("leads.filtre.toutes_landings", "Toutes les landings")}
              </option>
              {pubs.map(p => (
                <option key={p.slug} value={p.slug}>{p.slug}</option>
              ))}
            </select>
          )}
          <select
            value={statut} onChange={e => setStatut(e.target.value as StatutLead | "")}
            className="px-3 py-2 rounded-lg border border-slate-300 text-sm
                       min-h-[44px]"
          >
            <option value="">
              {t("leads.filtre.tous_statuts", "Tous statuts")}
            </option>
            {STATUTS.map(s => (
              <option key={s.value} value={s.value}>
                {t(s.labelKey, s.fallback)}
              </option>
            ))}
          </select>
          <select
            value={jours} onChange={e => setJours(parseInt(e.target.value))}
            className="px-3 py-2 rounded-lg border border-slate-300 text-sm
                       min-h-[44px]"
          >
            {PERIODES.map(p => (
              <option key={p.jours} value={p.jours}>
                {t(p.labelKey, p.fallback)}
              </option>
            ))}
          </select>
          <div className="relative flex-grow min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={recherche}
              onChange={e => setRecherche(e.target.value)}
              placeholder={t("leads.recherche", "Recherche nom, email, message…")}
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300
                         text-sm min-h-[44px]"
            />
          </div>
          <a
            href={api.exportCsvUrl({ slug: slug || undefined, jours })}
            target="_blank" rel="noopener"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg
                       bg-slate-800 hover:bg-slate-900 text-white text-sm
                       font-medium min-h-[44px]"
          >
            <Download className="w-4 h-4" />
            {t("leads.export_csv", "CSV")}
          </a>
        </div>
      </div>

      {/* Stats Plausible si un slug est sélectionné */}
      {slug && (
        <div className="mb-4">
          <LandingStats http={http as any} slug={slug}
                        periode={jours === 7 ? "7d" : jours === 30 ? "30d" : "90d"}
                        t={t} />
        </div>
      )}

      {/* Erreur */}
      {erreur && (
        <div className="bg-rose-50 border border-rose-200 text-rose-900 rounded-lg p-3 mb-4 text-sm">
          {erreur}
        </div>
      )}

      {/* Liste */}
      <div className="space-y-2">
        {!loading && leadsFiltres.length === 0 && (
          <div className="text-center text-slate-500 py-12">
            {t("leads.vide", "Aucun lead pour ces filtres.")}
          </div>
        )}
        {leadsFiltres.map(lead => (
          <LeadCard
            key={lead.id} lead={lead} t={t}
            onStatut={st => setStatutLead(lead.id, st)}
            onCopier={copier}
          />
        ))}
      </div>
    </div>
  );
};

const KpiCard = ({ label, valeur, tone, icon }: {
  label: string; valeur: string; tone: string;
  icon?: React.ReactNode;
}) => (
  <div className={`rounded-xl p-4 ${tone}`}>
    <div className="flex items-center justify-between mb-1">
      <span className="text-xs uppercase tracking-wider opacity-70">{label}</span>
      {icon}
    </div>
    <div className="text-2xl font-bold">{valeur}</div>
  </div>
);

const LeadCard = ({ lead, t, onStatut, onCopier }: {
  lead: LeadRow;
  t: (k: string, fb?: string) => string;
  onStatut: (st: StatutLead) => void;
  onCopier: (v: string) => void;
}) => {
  const statutInfo = STATUTS.find(s => s.value === lead.statut) || STATUTS[0];
  const date = new Date(lead.created_at);
  const dateFmt = date.toLocaleDateString() + " " + date.toLocaleTimeString().slice(0, 5);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4
                    hover:shadow-md transition-shadow">
      <div className="flex flex-col md:flex-row md:items-start gap-3">
        <div className="flex-grow">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="font-semibold">
              {lead.nom || t("leads.anonyme", "Anonyme")}
            </span>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${statutInfo.tone}`}>
              {t(statutInfo.labelKey, statutInfo.fallback)}
            </span>
            <span className="text-xs text-slate-500 flex items-center gap-1">
              <Tag className="w-3 h-3" />{lead.slug}
            </span>
            <span className="text-xs text-slate-400 ml-auto">{dateFmt}</span>
          </div>
          <div className="flex flex-wrap gap-3 text-sm mb-2">
            {lead.email && (
              <button
                onClick={() => onCopier(lead.email!)}
                className="inline-flex items-center gap-1 text-slate-700 hover:text-blue-700"
              >
                <Mail className="w-3.5 h-3.5" />{lead.email}
                <Copy className="w-3 h-3 opacity-40" />
              </button>
            )}
            {lead.telephone && (
              <button
                onClick={() => onCopier(lead.telephone!)}
                className="inline-flex items-center gap-1 text-slate-700 hover:text-blue-700"
              >
                <Phone className="w-3.5 h-3.5" />{lead.telephone}
                <Copy className="w-3 h-3 opacity-40" />
              </button>
            )}
          </div>
          {lead.message && (
            <p className="text-sm text-slate-600 whitespace-pre-wrap mt-2">
              {lead.message}
            </p>
          )}
        </div>
        <div className="flex flex-row md:flex-col gap-2 flex-shrink-0">
          {lead.telephone && (
            <a
              href={`https://wa.me/${lead.telephone.replace(/[^0-9+]/g, "")}`}
              target="_blank" rel="noopener"
              className="inline-flex items-center justify-center gap-1
                         px-3 py-2 rounded-lg bg-green-600 hover:bg-green-700
                         text-white text-xs font-medium min-h-[44px] min-w-[44px]"
            >
              <MessageCircle className="w-4 h-4" />
              <span className="hidden md:inline">WhatsApp</span>
            </a>
          )}
          {lead.email && (
            <a
              href={`mailto:${lead.email}`}
              className="inline-flex items-center justify-center gap-1
                         px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700
                         text-white text-xs font-medium min-h-[44px] min-w-[44px]"
            >
              <Mail className="w-4 h-4" />
              <span className="hidden md:inline">Email</span>
            </a>
          )}
          {lead.statut !== "converti" && (
            <button
              onClick={() => onStatut("contacte")}
              className="inline-flex items-center justify-center gap-1
                         px-3 py-2 rounded-lg bg-amber-500 hover:bg-amber-600
                         text-white text-xs font-medium min-h-[44px] min-w-[44px]"
              title={t("leads.action.marquer_contacte", "Marquer comme contacté")}
            >
              <CheckCircle2 className="w-4 h-4" />
              <span className="hidden md:inline">
                {t("leads.action.contacte", "Contacté")}
              </span>
            </button>
          )}
          <select
            value={lead.statut}
            onChange={e => onStatut(e.target.value as StatutLead)}
            className="px-2 py-1 rounded-lg border border-slate-300 text-xs
                       min-h-[44px]"
          >
            {STATUTS.map(s => (
              <option key={s.value} value={s.value}>
                {t(s.labelKey, s.fallback)}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
};
