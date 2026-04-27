import { Check, Zap, Building2, Rocket, Star } from "lucide-react";
import { cn, formatMontant } from "@/components/ui";

const PLANS = [
  {
    id: "decouverte",
    label: "Découverte",
    prix: 0,
    periode: "Gratuit",
    icon: Star,
    color: "gray",
    features: [
      "Agent copilote CIMA",
      "5 sinistres / mois",
      "Q&A Code CIMA",
      "Tableau de bord basique",
    ],
    cta: "Actif",
    actif: true,
  },
  {
    id: "essentiel",
    label: "Essentiel",
    prix: 25_000,
    periode: "/ mois",
    icon: Zap,
    color: "blue",
    features: [
      "Agents sinistres + souscription",
      "50 sinistres / mois",
      "Tarification IA RC Auto",
      "Émission polices",
      "Documents PDF illimités",
    ],
    cta: "Choisir",
    actif: false,
  },
  {
    id: "professionnel",
    label: "Professionnel",
    prix: 75_000,
    periode: "/ mois",
    icon: Rocket,
    color: "assurance",
    features: [
      "Tous les agents métier",
      "500 sinistres / mois",
      "Comptabilité PCSA complète",
      "Ratios CIMA automatiques",
      "Réassurance & PML",
      "Intégration ORASS",
    ],
    cta: "Choisir",
    actif: false,
    recommande: true,
  },
  {
    id: "entreprise",
    label: "Entreprise",
    prix: 200_000,
    periode: "/ mois",
    icon: Building2,
    color: "purple",
    features: [
      "Tous les modules illimités",
      "Sinistres illimités",
      "Multi-compagnie",
      "API dédiée",
      "Support prioritaire",
      "Formation équipe incluse",
    ],
    cta: "Contacter",
    actif: false,
  },
];

const COLOR_STYLES: Record<string, { border: string; badge: string; btn: string }> = {
  gray:       { border: "rgba(255,255,255,0.06)", badge: "bg-gray-500/10 text-gray-400 border-gray-500/20", btn: "bg-gray-700 text-gray-300" },
  blue:       { border: "rgba(0,176,240,0.2)",    badge: "bg-assurance-500/10 text-ciel-400 border-assurance-500/20", btn: "" },
  assurance:  { border: "rgba(0,84,166,0.4)",     badge: "bg-assurance-500/20 text-ciel-300 border-ciel-500/30", btn: "" },
  purple:     { border: "rgba(168,85,247,0.2)",   badge: "bg-purple-500/10 text-purple-400 border-purple-500/20", btn: "" },
};

export function AbonnementPage() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4 text-center">
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          Abonnement
        </h1>
        <p className="text-sm text-gray-400 mt-1">Choisissez le plan adapté à votre compagnie</p>
      </div>

      <div className="px-8 pb-8">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5 max-w-6xl mx-auto mt-6">
          {PLANS.map((plan) => {
            const Icon   = plan.icon;
            const styles = COLOR_STYLES[plan.color];

            return (
              <div key={plan.id}
                className={cn("relative rounded-2xl border p-6 flex flex-col")}
                style={{ background: "rgba(17,24,39,0.8)", borderColor: styles.border }}>

                {plan.recommande && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full text-xs font-bold text-white"
                    style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
                    Recommandé
                  </div>
                )}

                <div className="flex items-center gap-3 mb-4">
                  <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center border", styles.badge)}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-white">{plan.label}</p>
                    <p className="text-xs text-gray-500">{plan.periode}</p>
                  </div>
                </div>

                <div className="mb-5">
                  <span className="text-3xl font-bold text-white">{plan.prix === 0 ? "0" : formatMontant(plan.prix).replace(" FCFA", "")}</span>
                  {plan.prix > 0 && <span className="text-sm text-gray-500 ml-1">FCFA / mois</span>}
                </div>

                <ul className="space-y-2.5 flex-1 mb-6">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-xs text-gray-300">
                      <Check className="w-3.5 h-3.5 text-ciel-400 mt-0.5 flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>

                <button
                  disabled={plan.actif}
                  className={cn(
                    "w-full py-2.5 rounded-xl text-sm font-semibold transition-all",
                    plan.actif
                      ? "text-gray-500 border border-white/[0.06] cursor-default"
                      : "text-white hover:brightness-110"
                  )}
                  style={!plan.actif ? { background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" } : {}}>
                  {plan.actif ? "Plan actuel" : plan.cta}
                </button>
              </div>
            );
          })}
        </div>

        <div className="mt-8 text-center">
          <p className="text-xs text-gray-600">
            Paiement via Mobile Money (MTN, Orange, Moov) · Virement bancaire · Facturation mensuelle
          </p>
          <p className="text-xs text-gray-700 mt-1">
            Conformité Zone CIMA · Données hébergées en région Afrique
          </p>
        </div>
      </div>
    </div>
  );
}
