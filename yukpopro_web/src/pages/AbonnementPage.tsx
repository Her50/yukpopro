import { useEffect, useState } from "react";
import {
  CreditCard, Smartphone, CheckCircle, Clock, AlertCircle,
  Zap, Star, Crown, Rocket, ArrowRight, RefreshCw, Copy, Check, PlusCircle,
} from "lucide-react";
import { Button, Card, Badge, Spinner } from "@/components/ui";
import { DemoBanner } from "@/components/DemoBanner";
import { abonnementApi } from "@/api/client";
import { useProfilStore } from "@/store";
import { PLANS, OPERATEURS_MOBILE_MONEY, type PlanAbonnement } from "@/types";
import toast from "react-hot-toast";

const PLAN_ICONS: Record<PlanAbonnement, typeof Zap> = {
  gratuit:  Zap,
  starter:  Rocket,
  pro:      Star,
  business: Crown,
};

type EtapePaiement = "plans" | "operateur" | "instructions" | "confirmation" | "succes";

export const AbonnementPage = () => {
  const { profil } = useProfilStore();
  const [abonnement, setAbonnement] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [etape, setEtape] = useState<EtapePaiement>("plans");
  const [planChoisi, setPlanChoisi] = useState<PlanAbonnement | null>(null);
  const [operateurChoisi, setOperateurChoisi] = useState("");
  const [telephone, setTelephone] = useState("");
  const [instructionsPaiement, setInstructionsPaiement] = useState<Record<string, unknown> | null>(null);
  const [reference, setReference] = useState("");
  const [transactionId, setTransactionId] = useState("");
  const [paiementLoading, setPaiementLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const pays = (profil as any)?.pays || "CM";

  const charger = async () => {
    setLoading(true);
    try {
      const a = await abonnementApi.monAbonnement();
      setAbonnement(a);
    } catch (_) {}
    setLoading(false);
  };

  useEffect(() => { charger(); }, []);

  const operateursFiltres = OPERATEURS_MOBILE_MONEY.filter((op) =>
    op.pays.includes(pays) || op.pays.length > 3
  );

  const handleChoisirPlan = (plan: PlanAbonnement) => {
    if (plan === "gratuit") return;
    setPlanChoisi(plan);
    setEtape("operateur");
  };

  const handleInitierPaiement = async () => {
    if (!planChoisi || !operateurChoisi || !telephone) {
      toast.error("Remplissez tous les champs");
      return;
    }
    setPaiementLoading(true);
    try {
      const res = await abonnementApi.initierPaiement({
        plan: planChoisi,
        operateur: operateurChoisi,
        numero_telephone: telephone,
        pays,
      });
      setInstructionsPaiement(res);
      setReference(res.reference || "");
      setEtape("instructions");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Erreur lors de l'initiation");
    } finally {
      setPaiementLoading(false);
    }
  };

  const handleConfirmerPaiement = async () => {
    if (!reference) { toast.error("Référence manquante"); return; }
    setPaiementLoading(true);
    try {
      await abonnementApi.confirmerPaiement(reference, transactionId || undefined);
      setEtape("succes");
      await charger();
      toast.success("Abonnement activé !");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Référence invalide ou expirée");
    } finally {
      setPaiementLoading(false);
    }
  };

  const copierReference = () => {
    navigator.clipboard.writeText(reference);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const [modeRecharge, setModeRecharge]     = useState(false);
  const [packChoisi, setPackChoisi]         = useState("");
  const [operateurR, setOperateurR]         = useState("");
  const [telephoneR, setTelephoneR]         = useState("");
  const [instrR, setInstrR]                 = useState<Record<string, unknown> | null>(null);
  const [refR, setRefR]                     = useState("");
  const [txIdR, setTxIdR]                   = useState("");
  const [etapeR, setEtapeR]                 = useState<"packs"|"operateur"|"instructions"|"confirmation"|"succes">("packs");
  const [loadingR, setLoadingR]             = useState(false);

  const PACKS = [
    { id: "pack_500",   nom: "Pack 500",    credits: 500,   prix: 300,  badge: "" },
    { id: "pack_2000",  nom: "Pack 2 000",  credits: 2000,  prix: 1200, badge: "Populaire" },
    { id: "pack_5000",  nom: "Pack 5 000",  credits: 5000,  prix: 3000, badge: "Meilleur prix" },
    { id: "pack_15000", nom: "Pack 15 000", credits: 15000, prix: 9000, badge: "" },
  ];

  const handleInitierRecharge = async () => {
    if (!packChoisi || !operateurR || telephoneR.length < 8) { toast.error("Remplissez tous les champs"); return; }
    setLoadingR(true);
    try {
      const res = await abonnementApi.initierRecharge({ pack_id: packChoisi, operateur: operateurR, numero_telephone: telephoneR, pays });
      setInstrR(res);
      setRefR(res.reference || "");
      setEtapeR("instructions");
    } catch (err: any) { toast.error(err?.response?.data?.detail || "Erreur d'initiation"); }
    finally { setLoadingR(false); }
  };

  const handleConfirmerRecharge = async () => {
    if (!refR) { toast.error("Référence manquante"); return; }
    setLoadingR(true);
    try {
      await abonnementApi.confirmerRecharge(refR, txIdR || undefined);
      setEtapeR("succes");
      await charger();
      toast.success("Crédits ajoutés à votre solde !");
    } catch (err: any) { toast.error(err?.response?.data?.detail || "Référence invalide"); }
    finally { setLoadingR(false); }
  };

  const planActuel = (abonnement?.plan as PlanAbonnement) || "gratuit";
  const planActuelInfo = PLANS.find((p) => p.id === planActuel);

  if (loading) {
    return <div className="flex items-center justify-center h-96"><Spinner size="lg" /></div>;
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8 animate-fade-in">
      <DemoBanner />
      {/* Header */}
      <div>
        <h1 className="text-2xl font-display font-bold text-white">Abonnement & Paiement</h1>
        <p className="text-slate-400 text-sm mt-1">
          Tous les 13 agents Yukpo sont accessibles à tous les utilisateurs. Seul le quota de crédits varie selon le plan.
        </p>
        <div className="mt-3 flex items-start gap-2 bg-slate-800/60 border border-slate-700/50 rounded-xl px-4 py-3 max-w-2xl">
          <span className="text-yukpo-400 text-sm">💡</span>
          <p className="text-slate-400 text-xs leading-relaxed">
            <strong className="text-white">Qu'est-ce qu'un crédit Yukpo ?</strong>{" "}
            Chaque échange avec Yukpo consomme des crédits selon la complexité de la demande.
            Une question simple coûte ~5 crédits, une analyse de document ~20-50 crédits, un rapport complet ~100-300 crédits.
            Vos crédits se renouvellent automatiquement chaque mois.
          </p>
        </div>
      </div>

      {/* Abonnement actuel */}
      {abonnement && (
        <Card className="p-5 border-yukpo-500/30 bg-yukpo-500/5">
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-yukpo-500/20 flex items-center justify-center flex-shrink-0">
                {(() => { const Icon = PLAN_ICONS[planActuel]; return <Icon className="w-6 h-6 text-yukpo-400" />; })()}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-white font-bold text-lg">{planActuelInfo?.nom || "Gratuit"}</span>
                  <Badge variant={planActuel === "gratuit" ? "secondary" : "purple"}>
                    {(abonnement.statut as string) || "actif"}
                  </Badge>
                </div>
                {/* Crédits IA (nouveau système) */}
                <div className="mt-2 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl font-bold text-white">
                      {((abonnement.credits_restants as number) ?? (abonnement.requetes_restantes as number) ?? 0).toLocaleString()}
                    </span>
                    <span className="text-slate-400 text-sm">
                      / {((abonnement.credits_alloues as number) ?? (abonnement.quota_jour as number) ?? 0).toLocaleString()} crédits Yukpo restants
                    </span>
                  </div>
                  {/* Barre de progression */}
                  <div className="w-64 h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        ((abonnement.pct_utilise as number) || 0) > 85 ? "bg-red-500"
                        : ((abonnement.pct_utilise as number) || 0) > 60 ? "bg-amber-500"
                        : "bg-yukpo-500"
                      }`}
                      style={{ width: `${Math.min(100, (abonnement.pct_utilise as number) || 0)}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-500">
                    {((abonnement.credits_utilises as number) ?? 0).toLocaleString()} crédits Yukpo utilisés ce mois
                    {abonnement.renouvellement_le && (
                      <span className="text-slate-600"> · Renouvellement le {abonnement.renouvellement_le as string}</span>
                    )}
                  </p>
                  {/* Équivalence FCFA */}
                  <p className="text-xs text-slate-600 italic">
                    ≈ {((abonnement.credits_restants as number) ?? 0)} FCFA d'utilisation Yukpo disponible
                  </p>
                </div>
                {abonnement.date_fin && (
                  <p className="text-xs text-slate-500 mt-1">
                    Abonnement expire le {new Date(abonnement.date_fin as string).toLocaleDateString("fr-FR")}
                  </p>
                )}
              </div>
            </div>
            <Button variant="ghost" size="sm" icon={<RefreshCw className="w-3 h-3" />} onClick={charger}>
              Actualiser
            </Button>
          </div>

          {/* Explication crédits */}
          {abonnement.explication_credits && (
            <p className="text-xs text-slate-600 mt-3 pt-3 border-t border-slate-700/50">
              {abonnement.explication_credits as string}
            </p>
          )}
        </Card>
      )}

      {/* ── Section Recharge de crédits ── */}
      {!modeRecharge ? (
        <div className="flex items-center justify-between bg-slate-800/40 border border-slate-700/50 rounded-2xl px-5 py-4">
          <div>
            <p className="text-white font-semibold">Recharger des crédits</p>
            <p className="text-slate-400 text-xs mt-0.5">Achetez des crédits supplémentaires sans changer de plan · 0,6 FCFA / crédit</p>
          </div>
          <Button variant="secondary" size="sm" icon={<PlusCircle className="w-4 h-4" />} onClick={() => { setModeRecharge(true); setEtapeR("packs"); }}>
            Recharger
          </Button>
        </div>
      ) : (
        <Card className="p-6 space-y-5 border-yukpo-500/30">
          <div className="flex items-center justify-between">
            <h2 className="text-white font-bold flex items-center gap-2"><PlusCircle className="w-5 h-5 text-yukpo-400" /> Recharger des crédits</h2>
            <button onClick={() => { setModeRecharge(false); setEtapeR("packs"); }} className="text-slate-500 hover:text-white text-xs">Annuler</button>
          </div>

          {etapeR === "packs" && (
            <>
              <p className="text-slate-400 text-sm">Choisissez un pack — les crédits s'ajoutent immédiatement à votre solde :</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {PACKS.map((pack) => (
                  <div key={pack.id} onClick={() => setPackChoisi(pack.id)}
                    className={`relative rounded-xl border p-4 cursor-pointer transition-all text-center ${packChoisi === pack.id ? "border-yukpo-500 bg-yukpo-500/10" : "border-slate-700 hover:border-slate-500"}`}>
                    {pack.badge && <span className="absolute -top-2 left-1/2 -translate-x-1/2 bg-yukpo-500 text-white text-xs px-2 py-0.5 rounded-full whitespace-nowrap">{pack.badge}</span>}
                    <p className="text-white font-bold text-lg">{pack.credits.toLocaleString()}</p>
                    <p className="text-slate-400 text-xs">crédits</p>
                    <p className="text-yukpo-300 font-semibold mt-2">{pack.prix.toLocaleString()} FCFA</p>
                  </div>
                ))}
              </div>
              <Button variant="primary" disabled={!packChoisi} onClick={() => setEtapeR("operateur")}>
                Continuer <ArrowRight className="w-4 h-4" />
              </Button>
            </>
          )}

          {etapeR === "operateur" && (
            <>
              <div className="grid grid-cols-2 gap-2">
                {operateursFiltres.map((op) => (
                  <button key={op.id} onClick={() => setOperateurR(op.id)}
                    className={`flex items-center gap-3 p-3 rounded-xl border transition-all text-left ${operateurR === op.id ? "border-yukpo-500 bg-yukpo-500/10 text-white" : "border-slate-700 text-slate-300 hover:border-slate-600"}`}>
                    <img src={op.logo} alt={op.label} className="w-8 h-8 rounded-full object-contain bg-white p-0.5" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                    <span className="text-sm font-medium">{op.label}</span>
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <span className="flex items-center px-3 bg-slate-800 border border-slate-700 rounded-xl text-slate-400 text-sm">+237</span>
                <input type="tel" placeholder="6XX XXX XXX" value={telephoneR}
                  onChange={(e) => setTelephoneR(e.target.value.replace(/\D/g, ""))}
                  className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-yukpo-500" />
              </div>
              <div className="flex gap-3">
                <Button variant="ghost" onClick={() => setEtapeR("packs")}>Retour</Button>
                <Button variant="primary" className="flex-1" loading={loadingR} disabled={!operateurR || telephoneR.length < 8} onClick={handleInitierRecharge}>
                  <Smartphone className="w-4 h-4" /> Recevoir les instructions
                </Button>
              </div>
            </>
          )}

          {etapeR === "instructions" && instrR && (
            <>
              <div className="bg-slate-900 rounded-xl p-4 border border-yukpo-500/30">
                <p className="text-slate-400 text-xs mb-1">Référence de recharge</p>
                <div className="flex items-center gap-3">
                  <code className="text-yukpo-300 text-xl font-bold tracking-widest flex-1">{refR}</code>
                  <button onClick={() => { navigator.clipboard.writeText(refR); toast.success("Copié !"); }} className="text-slate-400 hover:text-white"><Copy className="w-4 h-4" /></button>
                </div>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Montant</span>
                <span className="text-white font-bold">{(instrR.montant_fcfa as number)?.toLocaleString()} FCFA</span>
              </div>
              <Button variant="primary" className="w-full" onClick={() => setEtapeR("confirmation")}>
                <CheckCircle className="w-4 h-4" /> J'ai effectué le paiement
              </Button>
            </>
          )}

          {etapeR === "confirmation" && (
            <>
              <input type="text" placeholder="YKP-RC-XXXXXXXX" value={refR} onChange={(e) => setRefR(e.target.value.toUpperCase())}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white font-mono tracking-widest placeholder-slate-600 focus:outline-none focus:border-green-500" />
              <input type="text" placeholder="ID Transaction Mobile Money (optionnel)" value={txIdR} onChange={(e) => setTxIdR(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-600 focus:outline-none focus:border-yukpo-500" />
              <div className="flex gap-3">
                <Button variant="ghost" onClick={() => setEtapeR("instructions")}>Retour</Button>
                <Button variant="primary" className="flex-1" loading={loadingR} disabled={!refR} onClick={handleConfirmerRecharge}>
                  <CheckCircle className="w-4 h-4" /> Confirmer la recharge
                </Button>
              </div>
            </>
          )}

          {etapeR === "succes" && (
            <div className="text-center space-y-3 py-4">
              <div className="w-14 h-14 rounded-2xl bg-green-500/20 flex items-center justify-center mx-auto">
                <CheckCircle className="w-7 h-7 text-green-400" />
              </div>
              <p className="text-white font-bold text-xl">Crédits ajoutés !</p>
              <p className="text-slate-400 text-sm">Vos crédits sont immédiatement disponibles.</p>
              <Button variant="secondary" onClick={() => { setModeRecharge(false); setEtapeR("packs"); setPackChoisi(""); setOperateurR(""); setTelephoneR(""); }}>
                Fermer
              </Button>
            </div>
          )}
        </Card>
      )}

      {/* ── ÉTAPE 1 : Choix du plan ── */}
      {etape === "plans" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {PLANS.map((plan) => {
            const Icon = PLAN_ICONS[plan.id];
            const estActuel = plan.id === planActuel;
            return (
              <div
                key={plan.id}
                className={`relative rounded-2xl border p-5 flex flex-col gap-4 transition-all ${
                  plan.badge ? "border-yukpo-500/50 shadow-lg shadow-yukpo-500/10" : "border-slate-700/50"
                } ${estActuel ? "opacity-60 cursor-not-allowed" : "cursor-pointer hover:border-yukpo-500/40 hover:bg-slate-800/50"}`}
                onClick={() => !estActuel && handleChoisirPlan(plan.id)}
              >
                {plan.badge && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="bg-yukpo-500 text-white text-xs font-bold px-3 py-1 rounded-full">{plan.badge}</span>
                  </div>
                )}
                {estActuel && (
                  <div className="absolute -top-3 right-3">
                    <span className="bg-green-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">Actuel</span>
                  </div>
                )}

                <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${plan.couleur} flex items-center justify-center`}>
                  <Icon className="w-5 h-5 text-white" />
                </div>

                <div>
                  <h3 className="text-white font-bold text-lg">{plan.nom}</h3>
                  <div className="flex items-baseline gap-1 mt-1">
                    {plan.prix_fcfa === 0 ? (
                      <span className="text-2xl font-bold text-white">Gratuit</span>
                    ) : (
                      <>
                        <span className="text-2xl font-bold text-white">{plan.prix_fcfa.toLocaleString()}</span>
                        <span className="text-slate-400 text-sm">FCFA/{plan.periode}</span>
                      </>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{plan.agents}</p>
                </div>

                <ul className="space-y-1.5 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-xs text-slate-300">
                      <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0 mt-0.5" />
                      {f}
                    </li>
                  ))}
                </ul>

                {!estActuel && plan.prix_fcfa > 0 && (
                  <Button variant={plan.badge ? "primary" : "secondary"} size="sm" className="w-full">
                    Choisir <ArrowRight className="w-3 h-3" />
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── ÉTAPE 2 : Choix opérateur ── */}
      {etape === "operateur" && planChoisi && (
        <Card className="p-6 max-w-lg mx-auto space-y-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-full bg-yukpo-500 text-white flex items-center justify-center text-sm font-bold">2</div>
            <div>
              <h2 className="text-white font-bold">Mode de paiement</h2>
              <p className="text-slate-400 text-sm">Plan {PLANS.find(p=>p.id===planChoisi)?.nom} — {PLANS.find(p=>p.id===planChoisi)?.prix_fcfa.toLocaleString()} FCFA</p>
            </div>
          </div>

          <div>
            <p className="text-slate-400 text-sm mb-3">Choisir votre opérateur Mobile Money :</p>
            <div className="grid grid-cols-2 gap-2">
              {operateursFiltres.map((op) => (
                <button
                  key={op.id}
                  onClick={() => setOperateurChoisi(op.id)}
                  className={`flex items-center gap-3 p-3 rounded-xl border transition-all text-left ${
                    operateurChoisi === op.id
                      ? "border-yukpo-500 bg-yukpo-500/10 text-white"
                      : "border-slate-700 text-slate-300 hover:border-slate-600"
                  }`}
                >
                  <span className="text-2xl">{op.logo}</span>
                  <span className="text-sm font-medium">{op.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-sm block mb-2">Numéro de téléphone Mobile Money</label>
            <div className="flex gap-2">
              <span className="flex items-center px-3 bg-slate-800 border border-slate-700 rounded-xl text-slate-400 text-sm">+237</span>
              <input
                type="tel"
                placeholder="6XX XXX XXX"
                value={telephone}
                onChange={(e) => setTelephone(e.target.value.replace(/\D/g, ""))}
                className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-yukpo-500"
              />
            </div>
          </div>

          <div className="flex gap-3">
            <Button variant="ghost" onClick={() => setEtape("plans")}>Retour</Button>
            <Button
              variant="primary"
              className="flex-1"
              loading={paiementLoading}
              onClick={handleInitierPaiement}
              disabled={!operateurChoisi || telephone.length < 8}
            >
              <Smartphone className="w-4 h-4" /> Recevoir les instructions
            </Button>
          </div>
        </Card>
      )}

      {/* ── ÉTAPE 3 : Instructions paiement ── */}
      {etape === "instructions" && instructionsPaiement && (
        <Card className="p-6 max-w-lg mx-auto space-y-5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-yukpo-500 text-white flex items-center justify-center text-sm font-bold">3</div>
            <div>
              <h2 className="text-white font-bold">Instructions de paiement</h2>
              <p className="text-slate-400 text-sm">Effectuez le paiement depuis votre téléphone</p>
            </div>
          </div>

          {/* Référence */}
          <div className="bg-slate-900 rounded-xl p-4 border border-yukpo-500/30">
            <p className="text-slate-400 text-xs mb-1">Votre référence de paiement</p>
            <div className="flex items-center gap-3">
              <code className="text-yukpo-300 text-xl font-bold tracking-widest flex-1">{reference}</code>
              <button onClick={copierReference} className="text-slate-400 hover:text-white">
                {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Montant */}
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">Montant à payer</span>
            <span className="text-white font-bold text-lg">{(instructionsPaiement.montant_fcfa as number)?.toLocaleString()} FCFA</span>
          </div>

          {/* Étapes opérateur */}
          {instructionsPaiement.instructions && (
            <div className="space-y-2">
              <p className="text-slate-300 text-sm font-semibold">Comment payer :</p>
              {Object.entries((instructionsPaiement.instructions as any).etapes || {}).map(([key, val]) => (
                <div key={key} className="flex gap-3 text-sm">
                  <span className="text-yukpo-400 font-medium w-16 flex-shrink-0 capitalize">{key}</span>
                  <span className="text-slate-300">{val as string}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-xl p-3">
            <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <p className="text-amber-300 text-xs">
              Conservez votre référence <strong>{reference}</strong>. Vous en aurez besoin pour confirmer votre abonnement.
              La demande expire dans 30 minutes.
            </p>
          </div>

          <Button variant="primary" className="w-full" onClick={() => setEtape("confirmation")}>
            <CheckCircle className="w-4 h-4" /> J'ai effectué le paiement
          </Button>
        </Card>
      )}

      {/* ── ÉTAPE 4 : Confirmation ── */}
      {etape === "confirmation" && (
        <Card className="p-6 max-w-lg mx-auto space-y-5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-green-500 text-white flex items-center justify-center text-sm font-bold">4</div>
            <div>
              <h2 className="text-white font-bold">Confirmer le paiement</h2>
              <p className="text-slate-400 text-sm">Entrez votre référence pour activer l'abonnement</p>
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-sm block mb-2">Référence de paiement *</label>
            <input
              type="text"
              placeholder="YKP-XXXXXXXX"
              value={reference}
              onChange={(e) => setReference(e.target.value.toUpperCase())}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white font-mono tracking-widest placeholder-slate-600 focus:outline-none focus:border-green-500"
            />
          </div>

          <div>
            <label className="text-slate-400 text-sm block mb-2">ID Transaction Mobile Money (optionnel)</label>
            <input
              type="text"
              placeholder="Numéro de transaction reçu par SMS"
              value={transactionId}
              onChange={(e) => setTransactionId(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-600 focus:outline-none focus:border-yukpo-500"
            />
          </div>

          <div className="flex gap-3">
            <Button variant="ghost" onClick={() => setEtape("instructions")}>Retour</Button>
            <Button
              variant="primary"
              className="flex-1"
              loading={paiementLoading}
              onClick={handleConfirmerPaiement}
              disabled={!reference}
            >
              <CheckCircle className="w-4 h-4" /> Activer mon abonnement
            </Button>
          </div>
        </Card>
      )}

      {/* ── ÉTAPE 5 : Succès ── */}
      {etape === "succes" && (
        <Card className="p-8 max-w-lg mx-auto text-center space-y-5 border-green-500/30 bg-green-500/5">
          <div className="w-16 h-16 rounded-2xl bg-green-500/20 flex items-center justify-center mx-auto">
            <CheckCircle className="w-8 h-8 text-green-400" />
          </div>
          <div>
            <h2 className="text-white font-bold text-2xl">Abonnement activé !</h2>
            <p className="text-slate-400 mt-2">
              Votre plan {PLANS.find(p => p.id === planChoisi)?.nom} est maintenant actif.
              Accédez à tous les agents et fonctionnalités YukpoPro.
            </p>
          </div>
          <Button variant="primary" className="w-full" onClick={() => setEtape("plans")}>
            <Zap className="w-4 h-4" /> Commencer à utiliser YukpoPro
          </Button>
        </Card>
      )}

      {/* Historique paiements */}
      {etape === "plans" && (
        <HistoriquePaiements />
      )}
    </div>
  );
};

const HistoriquePaiements = () => {
  const [historique, setHistorique] = useState<unknown[]>([]);
  useEffect(() => {
    abonnementApi.historique().then((r) => setHistorique(r.historique || [])).catch(() => {});
  }, []);

  if (historique.length === 0) return null;

  return (
    <Card className="p-5">
      <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
        <Clock className="w-4 h-4 text-slate-400" /> Historique des paiements
      </h3>
      <div className="space-y-2">
        {historique.map((h: any, i) => (
          <div key={i} className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0">
            <div>
              <span className="text-white text-sm font-medium capitalize">{h.plan}</span>
              <span className="text-slate-500 text-xs ml-3">{h.reference}</span>
            </div>
            <div className="text-right">
              <span className="text-gold-400 text-sm font-medium">{(h.montant_fcfa || 0).toLocaleString()} FCFA</span>
              <p className="text-slate-500 text-xs">{new Date(h.date).toLocaleDateString("fr-FR")}</p>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
