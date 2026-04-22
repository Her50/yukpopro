import { useState, FormEvent, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Send, Search, ChevronDown, ChevronUp, Clock, Shield, CreditCard, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { Card, Button, Textarea, Badge, Spinner } from "@/components/ui";
import { useProfilStore, useAuthStore } from "@/store";
import { agentApi, abonnementApi } from "@/api/client";
import type { AgentChatResponse } from "@/types";

const AGENTS_METIERS = [
  { id: "comptable",   label: "Comptable / Fiscaliste",   desc: "IRPP, TVA, IS, SYSCOHADA, liasse fiscale", color: "from-blue-500 to-blue-600", icon: "📊" },
  { id: "drh",         label: "DRH / Paie",               desc: "Bulletin de paie, licenciement, contrats, CNPS", color: "from-purple-500 to-purple-600", icon: "👥" },
  { id: "daf",         label: "DAF / Finance",            desc: "Cashflow, ratios, investissement, board pack", color: "from-indigo-500 to-indigo-600", icon: "💰" },
  { id: "juriste",     label: "Juriste / Avocat",         desc: "OHADA, contrats, contentieux, conformité", color: "from-red-500 to-red-600", icon: "⚖️" },
  { id: "banquier",    label: "Banquier / Finance",       desc: "TEG, tableau amortissement, scoring, KYC", color: "from-emerald-500 to-emerald-600", icon: "🏦" },
  { id: "ingenieur",   label: "Ingénieur / Chef projet",  desc: "CPM, planning, marchés publics, normes", color: "from-orange-500 to-orange-600", icon: "🏗️" },
  { id: "daa",         label: "Data Analyst",             desc: "Statistiques, tendances, visualisations", color: "from-cyan-500 to-cyan-600", icon: "📈" },
  { id: "commercial",  label: "Commercial / Entrepreneur", desc: "Business plan, pricing, pipeline, marché", color: "from-yellow-500 to-yellow-600", icon: "🚀" },
  { id: "charge_projets_ong", label: "ONG / Développement", desc: "Logframe, budgets bailleurs, rapports M&E", color: "from-teal-500 to-teal-600", icon: "🌍" },
  { id: "responsable_microfinance", label: "Microfinance / SFD", desc: "PAR, scoring crédit, ratios COBAC, produits", color: "from-pink-500 to-pink-600", icon: "💳" },
  { id: "transitaire",      label: "Transitaire / Douanier",  desc: "Droits douane, Incoterms, régimes douaniers", color: "from-amber-500 to-amber-600", icon: "🚢" },
  { id: "cv_emploi",        label: "CV & Emploi",             desc: "CV, lettre de motivation, entretiens, offres", color: "from-sky-500 to-sky-600", icon: "📄" },
  { id: "recherche_emploi", label: "Veille Emploi",           desc: "Veille marché, candidature, négociation salaire", color: "from-violet-500 to-violet-600", icon: "🔍" },
];

const EXEMPLES_PAR_METIER: Record<string, string[]> = {
  comptable: [
    "Calcule l'IRPP d'un salarié avec 850 000 FCFA de salaire brut au Cameroun",
    "Quelles sont les déclarations fiscales obligatoires pour une PME au Cameroun ?",
    "Comment passer l'écriture d'une facture de vente en SYSCOHADA ?",
  ],
  drh: [
    "Calcule le bulletin de paie d'un salarié avec 2 ans d'ancienneté, 2 enfants, 750 000 FCFA brut",
    "Quelles sont les indemnités de licenciement pour 8 ans d'ancienneté au Cameroun ?",
    "Rédige un contrat de travail à durée déterminée pour un commercial",
  ],
  banquier: [
    "Calcule le TEG d'un crédit de 10 000 000 FCFA sur 48 mois à 14% annuel",
    "Quels sont les ratios COBAC que je dois surveiller pour mon institution ?",
    "Score de crédit pour un client avec 850 000 FCFA de revenus, demande 5M FCFA",
  ],
  transitaire: [
    "Calcule les droits de douane pour l'importation de matériaux de construction (cat. 3) de 25M FCFA au Cameroun",
    "Quelle est la différence entre CIF et FOB et lequel choisir pour l'import ?",
    "Quel régime douanier pour du matériel de chantier importé temporairement ?",
  ],
  cv_emploi: [
    "Rédige un CV professionnel pour un DAF avec 10 ans d'expérience au Cameroun",
    "Rédige une lettre de motivation pour un poste de juriste OHADA",
    "Quelles questions préparer pour un entretien de directeur commercial ?",
  ],
  recherche_emploi: [
    "Quels sont les salaires du marché pour un Data Analyst senior à Douala ?",
    "Comment négocier une augmentation de 30% lors d'un changement de poste ?",
    "Rédige un email de candidature spontanée pour une banque de la zone CEMAC",
  ],
};

export const AgentsPage = () => {
  const { profil } = useProfilStore();
  const { user } = useAuthStore();
  const isAdmin = ["admin", "super_admin", "yukpo_owner"].includes(user?.role || "");
  const [abonnement, setAbonnement] = useState<Record<string, unknown> | null>(null);
  const [selectedAgent, setSelectedAgent] = useState(profil?.metier || "comptable");

  useEffect(() => {
    abonnementApi.monAbonnement().then(setAbonnement).catch(() => {});
  }, []);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [resultat, setResultat] = useState<AgentChatResponse | null>(null);
  const [showEtapes, setShowEtapes] = useState(false);
  const [rechercheQuery, setRechercheQuery] = useState("");
  const [rechercheResult, setRechercheResult] = useState<string | null>(null);
  const [rechercheLoading, setRechercheLoading] = useState(false);

  const handleSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;
    setLoading(true);
    setResultat(null);
    try {
      const res = await agentApi.chat({
        message,
        contexte: { agent_force: selectedAgent },
      });
      setResultat(res);
    } catch (err: unknown) {
      toast.error("Erreur de l'agent Yukpo");
    } finally {
      setLoading(false);
    }
  };

  const handleRecherche = async () => {
    if (!rechercheQuery.trim()) return;
    setRechercheLoading(true);
    setRechercheResult(null);
    try {
      const res = await agentApi.recherche({ question: rechercheQuery });
      setRechercheResult(res.contexte_rag || "Aucun passage trouvé.");
    } catch {
      toast.error("Erreur de recherche RAG");
    } finally {
      setRechercheLoading(false);
    }
  };

  const agentActif = AGENTS_METIERS.find((a) => a.id === selectedAgent);
  const exemples = EXEMPLES_PAR_METIER[selectedAgent] || [];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">Agents Yukpo Spécialisés</h1>
          <p className="text-slate-400 text-sm mt-1">
            13 agents spécialisés, accessibles à tous — limités uniquement par votre quota d'abonnement.
          </p>
        </div>
        {isAdmin && (
          <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2">
            <Shield className="w-4 h-4 text-red-400" />
            <span className="text-red-400 text-sm font-semibold">Mode Admin — Accès tous agents</span>
          </div>
        )}
        {!isAdmin && abonnement && (
          <div className={`flex items-center gap-3 rounded-xl px-4 py-2 border ${
            (abonnement.requetes_restantes as number) === 0
              ? "bg-red-500/10 border-red-500/30"
              : "bg-slate-800/60 border-slate-700/50"
          }`}>
            <Zap className={`w-4 h-4 ${(abonnement.requetes_restantes as number) === 0 ? "text-red-400" : "text-yukpo-400"}`} />
            <span className="text-sm text-slate-300">
              <span className={`font-bold ${(abonnement.requetes_restantes as number) === 0 ? "text-red-400" : "text-white"}`}>
                {abonnement.requetes_restantes as number}
              </span>
              /{abonnement.quota_jour as number} req. aujourd'hui · Plan <span className="text-yukpo-400 capitalize font-medium">{abonnement.plan as string}</span>
            </span>
            {(abonnement.requetes_restantes as number) === 0 && (
              <Link to="/abonnement">
                <Button size="sm" variant="primary" icon={<CreditCard className="w-3 h-3" />}>Upgrade</Button>
              </Link>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Sélection agent */}
        <div className="space-y-3">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Choisir l'agent</h2>
          <div className="space-y-2">
            {AGENTS_METIERS.map((agent) => (
              <button
                key={agent.id}
                onClick={() => { setSelectedAgent(agent.id); setResultat(null); }}
                className={`w-full text-left p-3 rounded-xl border transition-all ${
                  selectedAgent === agent.id
                    ? "bg-yukpo-500/20 border-yukpo-500/50 text-white"
                    : "bg-slate-800/50 border-slate-700/50 text-slate-300 hover:bg-slate-800 hover:text-white"
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-lg">{agent.icon}</span>
                  <div>
                    <p className="text-sm font-medium">{agent.label}</p>
                    <p className="text-xs text-slate-500">{agent.desc}</p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Zone principale */}
        <div className="lg:col-span-2 space-y-4">
          {/* Agent actif */}
          {agentActif && (
            <Card className={`p-4 bg-gradient-to-r ${agentActif.color} border-0`}>
              <div className="flex items-center gap-3">
                <span className="text-3xl">{agentActif.icon}</span>
                <div>
                  <h2 className="text-lg font-bold text-white">{agentActif.label}</h2>
                  <p className="text-sm text-white/80">{agentActif.desc}</p>
                </div>
                <Badge variant="gold" size="sm">PRO</Badge>
              </div>
            </Card>
          )}

          {/* Exemples */}
          {exemples.length > 0 && !resultat && (
            <div className="grid grid-cols-1 gap-2">
              <p className="text-xs text-slate-500 font-medium">Exemples :</p>
              {exemples.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => setMessage(ex)}
                  className="text-left text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-yukpo-500/30 rounded-xl px-3 py-2.5 transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSend} className="space-y-3">
            <Textarea
              label="Votre instruction"
              placeholder={`Demandez à l'agent ${agentActif?.label || ""} de faire un calcul, une analyse ou une rédaction…`}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
            />
            <Button type="submit" loading={loading} icon={<Send className="w-4 h-4" />} size="lg">
              Envoyer à l'agent
            </Button>
          </form>

          {/* Résultat */}
          {loading && (
            <Card className="p-6 flex items-center justify-center gap-3">
              <Spinner />
              <span className="text-slate-400 text-sm">Agent en train de traiter…</span>
            </Card>
          )}

          {resultat && !loading && (
            <Card className="p-5 space-y-4 animate-fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bot className="w-4 h-4 text-yukpo-400" />
                  <span className="text-sm font-semibold text-white">Réponse de l'agent</span>
                  <Badge variant="purple" size="sm">{resultat.profil_metier}</Badge>
                </div>
                <div className="flex items-center gap-1 text-xs text-slate-500">
                  <Clock className="w-3 h-3" />
                  {Math.round(resultat.duree_ms)}ms
                </div>
              </div>

              <div className="prose prose-sm prose-invert max-w-none border-t border-slate-700 pt-4">
                <ReactMarkdown
                  components={{
                    code: ({ children }) => (
                      <code className="bg-slate-900 text-yukpo-300 px-1.5 py-0.5 rounded font-mono text-xs">{children}</code>
                    ),
                    pre: ({ children }) => (
                      <pre className="bg-slate-900 p-3 rounded-xl overflow-x-auto text-xs border border-slate-700">{children}</pre>
                    ),
                    table: ({ children }) => (
                      <div className="overflow-x-auto">
                        <table className="text-xs border-collapse border border-slate-600 w-full">{children}</table>
                      </div>
                    ),
                    th: ({ children }) => <th className="border border-slate-600 px-2 py-1.5 bg-slate-700 text-left">{children}</th>,
                    td: ({ children }) => <td className="border border-slate-600 px-2 py-1.5">{children}</td>,
                  }}
                >
                  {resultat.reponse}
                </ReactMarkdown>
              </div>

              {resultat.nb_etapes > 0 && (
                <button
                  onClick={() => setShowEtapes(!showEtapes)}
                  className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
                >
                  {showEtapes ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                  {resultat.nb_etapes} étapes de raisonnement
                </button>
              )}
            </Card>
          )}

          {/* RAG Search */}
          <Card className="p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Search className="w-4 h-4 text-accent-400" />
              <h3 className="text-sm font-semibold text-white">Recherche réglementaire directe</h3>
              <Badge variant="cyan" size="sm">RAG</Badge>
            </div>
            <p className="text-xs text-slate-400">Cherchez directement dans le corpus réglementaire africain (base de connaissances Yukpo).</p>
            <div className="flex gap-2">
              <input
                value={rechercheQuery}
                onChange={(e) => setRechercheQuery(e.target.value)}
                placeholder="Ex: Taux IRPP Cameroun 2024, Délais prescription OHADA…"
                className="flex-1 bg-slate-700 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500"
                onKeyDown={(e) => e.key === "Enter" && handleRecherche()}
              />
              <Button variant="secondary" size="sm" onClick={handleRecherche} loading={rechercheLoading}>
                <Search className="w-4 h-4" />
              </Button>
            </div>
            {rechercheResult && (
              <div className="mt-2 p-3 bg-slate-900 rounded-xl border border-slate-700 text-xs text-slate-300 font-mono overflow-x-auto max-h-60 overflow-y-auto">
                <pre className="whitespace-pre-wrap">{rechercheResult}</pre>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};
