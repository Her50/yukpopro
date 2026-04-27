import { useState } from "react";
import { Car, Heart, Home, Truck, Briefcase, ChevronRight, Check, FileText } from "lucide-react";
import { cn, formatMontant } from "@/components/ui";

type Branche = "rc_auto" | "mrh" | "transport" | "vie" | "accident" | "rc_pro";
type Step = "branche" | "details" | "tarif" | "emission";

const BRANCHES: { id: Branche; label: string; icon: React.ComponentType<{ className?: string }>; color: string; desc: string }[] = [
  { id: "rc_auto",   label: "RC Auto",        icon: Car,       color: "blue",   desc: "Responsabilité civile automobile CIMA B03" },
  { id: "mrh",       label: "MRH / Incendie", icon: Home,      color: "orange", desc: "Multi-risques habitation et incendie CIMA B08" },
  { id: "transport", label: "Transport CMR",   icon: Truck,     color: "cyan",   desc: "Marchandises transportées CIMA B07" },
  { id: "vie",       label: "Vie / Prévoyance",icon: Heart,     color: "rose",   desc: "Vie entière, décès, épargne CIMA B20-B23" },
  { id: "accident",  label: "Accidents Corp.", icon: Heart,     color: "red",    desc: "Accidents corporels CIMA B01" },
  { id: "rc_pro",    label: "RC Professionnelle",icon: Briefcase,color: "purple","desc": "RC entreprise et professionnel CIMA B13" },
];

const COLOR_MAP: Record<string, string> = {
  blue:   "border-blue-500/30 bg-blue-500/10 text-blue-400",
  orange: "border-orange-500/30 bg-orange-500/10 text-orange-400",
  cyan:   "border-cyan-500/30 bg-cyan-500/10 text-cyan-400",
  rose:   "border-rose-500/30 bg-rose-500/10 text-rose-400",
  red:    "border-red-500/30 bg-red-500/10 text-red-400",
  purple: "border-purple-500/30 bg-purple-500/10 text-purple-400",
};

export function SouscriptionPage() {
  const [step, setStep]         = useState<Step>("branche");
  const [branche, setBranche]   = useState<Branche | null>(null);
  const [details, setDetails]   = useState<Record<string, string>>({});
  const [prime, setPrime]       = useState<number | null>(null);
  const [emis, setEmis]         = useState(false);

  const handleBranche = (b: Branche) => { setBranche(b); setStep("details"); };

  const STEPS: { id: Step; label: string }[] = [
    { id: "branche", label: "Branche" },
    { id: "details", label: "Détails risque" },
    { id: "tarif",   label: "Tarification" },
    { id: "emission",label: "Émission" },
  ];

  const currentIdx = STEPS.findIndex((s) => s.id === step);

  const simulerPrime = () => {
    const base = branche === "rc_auto" ? 185_000 : branche === "vie" ? 120_000 : branche === "mrh" ? 95_000 : 75_000;
    setPrime(base + Math.floor(Math.random() * 50_000));
    setStep("tarif");
  };

  if (emis) {
    const ref = `POL-${branche?.toUpperCase()}-${new Date().getFullYear()}-${Math.floor(Math.random() * 900) + 100}`;
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-6"
            style={{ background: "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)", boxShadow: "0 0 30px rgba(34,197,94,0.3)" }}>
            <Check className="w-10 h-10 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Police émise !</h2>
          <p className="text-gray-400 mb-2">Référence : <span className="font-mono text-ciel-400">{ref}</span></p>
          <p className="text-gray-400 mb-8">Prime : <span className="font-semibold text-white">{formatMontant(prime ?? 0)}</span></p>
          <button onClick={() => { setEmis(false); setBranche(null); setStep("branche"); setPrime(null); }}
            className="px-6 py-2.5 rounded-xl text-sm font-semibold text-white hover:brightness-110 transition-all"
            style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
            Nouvelle souscription
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4">
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          Souscription
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">Tarification IA · Émission police · Conformité CIMA</p>
      </div>

      {/* Stepper */}
      <div className="px-8 mb-8">
        <div className="flex items-center gap-3">
          {STEPS.map((s, i) => (
            <div key={s.id} className="flex items-center gap-3">
              <div className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                i < currentIdx ? "text-green-400 bg-green-500/10 border border-green-500/20" :
                i === currentIdx ? "text-white border" :
                "text-gray-600 border border-white/[0.04]"
              )} style={i === currentIdx ? { background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)", borderColor: "transparent" } : {}}>
                {i < currentIdx ? <Check className="w-3 h-3" /> : <span>{i + 1}</span>}
                {s.label}
              </div>
              {i < STEPS.length - 1 && <ChevronRight className="w-4 h-4 text-gray-700" />}
            </div>
          ))}
        </div>
      </div>

      {/* Step branche */}
      {step === "branche" && (
        <div className="px-8">
          <p className="text-sm text-gray-400 mb-4">Sélectionnez la branche d'assurance :</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-3xl">
            {BRANCHES.map((b) => {
              const Icon = b.icon;
              return (
                <button key={b.id} onClick={() => handleBranche(b.id)}
                  className={cn("rounded-2xl border p-5 text-left hover:scale-[1.01] transition-all", COLOR_MAP[b.color])}
                  style={{ background: "rgba(17,24,39,0.8)" }}>
                  <Icon className="w-8 h-8 mb-3" />
                  <p className="text-sm font-semibold text-white mb-1">{b.label}</p>
                  <p className="text-xs text-gray-500 leading-tight">{b.desc}</p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Step détails */}
      {step === "details" && branche && (
        <div className="px-8 max-w-lg">
          <p className="text-sm text-gray-400 mb-4">
            Informations souscripteur — <span className="text-ciel-400">{BRANCHES.find((b) => b.id === branche)?.label}</span>
          </p>
          <div className="space-y-4">
            {["Nom du souscripteur", "Téléphone", "Adresse", "Date d'effet"].map((label) => (
              <div key={label}>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">{label}</label>
                <input
                  className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
                  placeholder={label}
                  value={details[label] || ""}
                  onChange={(e) => setDetails((p) => ({ ...p, [label]: e.target.value }))}
                />
              </div>
            ))}
            {branche === "rc_auto" && (
              <>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">Immatriculation</label>
                  <input
                    className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
                    placeholder="LT-4521-A"
                    value={details["Immatriculation"] || ""}
                    onChange={(e) => setDetails((p) => ({ ...p, "Immatriculation": e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">Catégorie</label>
                  <select
                    className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-assurance-500/40 transition-all"
                    value={details["Catégorie"] || ""}
                    onChange={(e) => setDetails((p) => ({ ...p, "Catégorie": e.target.value }))}>
                    <option value="">Sélectionner</option>
                    {["Tourisme", "Transport en commun", "Utilitaire", "Camion", "Moto"].map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </div>
              </>
            )}
            <div className="flex gap-3 pt-2">
              <button onClick={() => setStep("branche")}
                className="flex-1 py-2.5 rounded-xl text-sm text-gray-400 border border-white/[0.06] hover:bg-white/[0.04] transition-all">
                Retour
              </button>
              <button onClick={simulerPrime}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white hover:brightness-110 transition-all"
                style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
                Calculer la prime IA
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step tarif */}
      {step === "tarif" && prime && (
        <div className="px-8 max-w-md">
          <div className="rounded-2xl border border-assurance-500/30 p-6 mb-6" style={{ background: "rgba(0,84,166,0.08)" }}>
            <p className="text-xs text-gray-400 mb-2">Prime calculée par IA — tarif CIMA</p>
            <p className="text-4xl font-bold text-white mb-1">{formatMontant(prime)}</p>
            <p className="text-xs text-ciel-400">Annuel TTC · {BRANCHES.find((b) => b.id === branche)?.label}</p>
            <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-gray-400">
              <div><span className="text-gray-500">Prime nette :</span> {formatMontant(Math.round(prime * 0.85))}</div>
              <div><span className="text-gray-500">Taxes (15%) :</span> {formatMontant(Math.round(prime * 0.15))}</div>
              <div><span className="text-gray-500">Garanties :</span> RC / Dommages</div>
              <div><span className="text-gray-500">Durée :</span> 12 mois</div>
            </div>
          </div>
          <div className="rounded-xl border border-white/[0.06] p-4 mb-4 text-xs" style={{ background: "rgba(17,24,39,0.8)" }}>
            <p className="text-ciel-400 font-semibold mb-2 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5" />
              Imputation comptable automatique
            </p>
            <div className="flex justify-between text-gray-400">
              <span>Débit 411 Clients :</span>
              <span className="font-mono">{formatMontant(prime)}</span>
            </div>
            <div className="flex justify-between text-gray-400">
              <span>Crédit 7001 Primes RC Auto :</span>
              <span className="font-mono">{formatMontant(Math.round(prime * 0.85))}</span>
            </div>
          </div>
          <div className="flex gap-3">
            <button onClick={() => setStep("details")}
              className="flex-1 py-2.5 rounded-xl text-sm text-gray-400 border border-white/[0.06] hover:bg-white/[0.04] transition-all">
              Modifier
            </button>
            <button onClick={() => setStep("emission")}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white hover:brightness-110 transition-all"
              style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
              Émettre la police
            </button>
          </div>
        </div>
      )}

      {/* Step émission */}
      {step === "emission" && (
        <div className="px-8 max-w-md">
          <p className="text-sm text-gray-400 mb-4">Confirmation avant émission :</p>
          <div className="rounded-2xl border border-white/[0.06] p-5 mb-6 space-y-3" style={{ background: "rgba(17,24,39,0.8)" }}>
            <div className="flex justify-between text-sm"><span className="text-gray-500">Branche</span><span className="text-white">{BRANCHES.find((b) => b.id === branche)?.label}</span></div>
            <div className="flex justify-between text-sm"><span className="text-gray-500">Souscripteur</span><span className="text-white">{details["Nom du souscripteur"] || "—"}</span></div>
            <div className="flex justify-between text-sm"><span className="text-gray-500">Prime annuelle</span><span className="font-semibold text-white">{formatMontant(prime ?? 0)}</span></div>
            <div className="flex justify-between text-sm"><span className="text-gray-500">Effet</span><span className="text-white">{details["Date d'effet"] || new Date().toLocaleDateString("fr-FR")}</span></div>
          </div>
          <div className="flex gap-3">
            <button onClick={() => setStep("tarif")}
              className="flex-1 py-2.5 rounded-xl text-sm text-gray-400 border border-white/[0.06] hover:bg-white/[0.04] transition-all">
              Retour
            </button>
            <button onClick={() => setEmis(true)}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white hover:brightness-110 transition-all"
              style={{ background: "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)" }}>
              Confirmer & Émettre
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
