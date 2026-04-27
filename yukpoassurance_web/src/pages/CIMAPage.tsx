import { useState } from "react";
import { Scale, AlertTriangle, CheckCircle, Send, FileText } from "lucide-react";
import { cn, formatMontant } from "@/components/ui";
import { cimaApi } from "@/api/client";

const RATIOS_DEMO = [
  { label: "Marge de solvabilité",        valeur: 138.7, seuil: 100,  unite: "%",    statut: "ok",      art: "Art. 337-1" },
  { label: "Ratio S/P (charges/primes)",  valeur: 62.4,  seuil: 80,   unite: "%",    statut: "ok",      art: "Art. 10" },
  { label: "Provisions techniques / PA",  valeur: 95.2,  seuil: 100,  unite: "%",    statut: "warning", art: "Art. 334" },
  { label: "Couverture provisions",       valeur: 112.0, seuil: 100,  unite: "%",    statut: "ok",      art: "Art. 335" },
  { label: "Ratio de liquidité",          valeur: 1.8,   seuil: 1.0,  unite: "x",    statut: "ok",      art: "Art. 340" },
  { label: "Taux de cession réassurance", valeur: 28.5,  seuil: 50,   unite: "%",    statut: "ok",      art: "Art. 308" },
];

const ETATS_CIMA = [
  { code: "C1",  label: "Bilan", echeance: "30/04/2026", statut: "a_deposer" },
  { code: "C2",  label: "Compte de résultat", echeance: "30/04/2026", statut: "a_deposer" },
  { code: "C5",  label: "Portefeuille contrats vie", echeance: "30/04/2026", statut: "a_deposer" },
  { code: "C10", label: "Inventaire placements", echeance: "30/04/2026", statut: "a_deposer" },
  { code: "C12", label: "Tableau de bord réassurance", echeance: "30/03/2026", statut: "depose" },
  { code: "C20", label: "Calcul marge solvabilité", echeance: "30/04/2026", statut: "en_cours" },
];

export function CIMAPage() {
  const [question, setQuestion] = useState("");
  const [reponse, setReponse]   = useState("");
  const [loading, setLoading]   = useState(false);
  const [onglet, setOnglet]     = useState<"ratios" | "etats" | "qa">("ratios");

  const handleQa = async () => {
    if (!question.trim()) return;
    setLoading(true);
    try {
      const res = await cimaApi.qa(question);
      const d = res.data as { reponse?: string; answer?: string };
      setReponse(d.reponse || d.answer || "Réponse non disponible.");
    } catch {
      setReponse("L'agent CIMA est momentanément indisponible. Art. 12-bis : délai offre indemnisation = 90 jours.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4">
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          CIMA · Conformité réglementaire
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">Ratios prudentiels · États règlementaires · Q&A Code CIMA</p>
      </div>

      {/* Onglets */}
      <div className="px-8 flex gap-2 mb-6">
        {[
          { id: "ratios", label: "Ratios prudentiels", icon: Scale },
          { id: "etats",  label: "États règlementaires", icon: FileText },
          { id: "qa",     label: "Q&A Code CIMA", icon: Send },
        ].map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setOnglet(id as typeof onglet)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all border",
              onglet === id
                ? "text-white border-assurance-500/40"
                : "text-gray-400 border-white/[0.06] hover:text-gray-200 hover:bg-white/[0.04]"
            )}
            style={onglet === id ? { background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)", borderColor: "transparent" } : {}}>
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Ratios */}
      {onglet === "ratios" && (
        <div className="px-8 space-y-3 max-w-2xl pb-8">
          {RATIOS_DEMO.map((r) => {
            const ok = r.statut === "ok";
            return (
              <div key={r.label} className="rounded-2xl border p-5 flex items-center justify-between"
                style={{ background: "rgba(17,24,39,0.8)", borderColor: ok ? "rgba(34,197,94,0.15)" : "rgba(249,115,22,0.2)" }}>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    {ok
                      ? <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
                      : <AlertTriangle className="w-4 h-4 text-alerte-400 flex-shrink-0" />}
                    <p className="text-sm font-medium text-white">{r.label}</p>
                  </div>
                  <p className="text-xs text-gray-500 ml-6">{r.art} — seuil : {r.seuil}{r.unite}</p>
                </div>
                <div className="text-right ml-4">
                  <p className={cn("text-xl font-bold", ok ? "text-green-400" : "text-alerte-400")}>
                    {r.valeur}{r.unite}
                  </p>
                  <p className={cn("text-xs", ok ? "text-green-500" : "text-alerte-500")}>
                    {ok ? "Conforme" : "Vigilance"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* États CIMA */}
      {onglet === "etats" && (
        <div className="px-8 space-y-3 max-w-xl pb-8">
          {ETATS_CIMA.map((e) => {
            const config = e.statut === "depose"
              ? { label: "Déposé", classes: "text-green-400 bg-green-500/10 border-green-500/20" }
              : e.statut === "en_cours"
              ? { label: "En cours", classes: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" }
              : { label: "À déposer", classes: "text-alerte-400 bg-alerte-500/10 border-alerte-500/20" };
            return (
              <div key={e.code} className="rounded-2xl border p-4 flex items-center justify-between"
                style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm text-ciel-400 w-8">{e.code}</span>
                  <div>
                    <p className="text-sm font-medium text-white">{e.label}</p>
                    <p className="text-xs text-gray-500">Échéance : {e.echeance}</p>
                  </div>
                </div>
                <span className={cn("text-xs font-semibold px-2.5 py-1 rounded-full border", config.classes)}>
                  {config.label}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Q&A */}
      {onglet === "qa" && (
        <div className="px-8 max-w-2xl pb-8">
          <p className="text-sm text-gray-400 mb-4">Posez une question sur le Code CIMA :</p>
          <div className="flex gap-3 mb-4">
            <input
              className="flex-1 bg-white/[0.04] border border-white/[0.06] rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
              placeholder="Ex: Quel est le délai légal d'offre d'indemnisation ? (Art. 12-bis)"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleQa()}
            />
            <button onClick={handleQa} disabled={loading || !question.trim()}
              className="w-10 h-10 flex items-center justify-center rounded-xl text-white disabled:opacity-40 hover:brightness-110 transition-all flex-shrink-0"
              style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
              <Send className="w-4 h-4" />
            </button>
          </div>

          {/* Suggestions */}
          <div className="flex flex-wrap gap-2 mb-6">
            {[
              "Délai offre indemnisation Art. 12-bis",
              "Calcul marge solvabilité Art. 337-1",
              "Provisions PSAP obligatoires",
              "Délai paiement Art. 12-ter",
            ].map((s) => (
              <button key={s} onClick={() => { setQuestion(s); }}
                className="text-xs px-3 py-1.5 rounded-full border border-white/[0.06] text-gray-400 hover:text-gray-200 hover:bg-white/[0.04] transition-all">
                {s}
              </button>
            ))}
          </div>

          {reponse && (
            <div className="rounded-2xl border border-assurance-500/20 p-5" style={{ background: "rgba(0,84,166,0.08)" }}>
              <p className="text-xs text-ciel-400 font-semibold mb-2">Agent CIMA</p>
              <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">{reponse}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
