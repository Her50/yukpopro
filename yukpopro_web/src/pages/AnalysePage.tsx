import { useRef } from "react";
import { Upload, BarChart2, FileUp, X, TrendingUp } from "lucide-react";
import toast from "react-hot-toast";
import ReactMarkdown from "react-markdown";
import { Card, Button, Badge, Spinner } from "@/components/ui";
import { DemoBanner } from "@/components/DemoBanner";
import { generateurApi } from "@/api/client";
import { useAnalyseStore } from "@/store/analyseStore";

export const AnalysePage = () => {
  const loading       = useAnalyseStore(s => s.loading);
  const stats         = useAnalyseStore(s => s.stats);
  const renduMarkdown = useAnalyseStore(s => s.renduMarkdown);
  const fichierNom    = useAnalyseStore(s => s.fichierNom);
  const apercu        = useAnalyseStore(s => s.apercu);
  const setLoading    = useAnalyseStore(s => s.setLoading);
  const setResult     = useAnalyseStore(s => s.setResult);
  const resetAnalyse  = useAnalyseStore(s => s.reset);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File) => {
    setLoading(true);
    setResult({ fichierNom: file.name, stats: null, renduMarkdown: "", apercu: null });
    try {
      const res = await generateurApi.uploadData(file);
      setResult({
        fichierNom: file.name,
        stats: res.stats,
        renduMarkdown: res.rendu_markdown || "",
        apercu: res.apercu_200 || null,
      });
      toast.success(`${file.name} analysé — ${res.nb_lignes} lignes, ${res.nb_colonnes} colonnes`);
    } catch {
      toast.error("Erreur analyse fichier");
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
  };

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto animate-fade-in">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-display font-bold text-white">Analyse de Données</h1>
        <p className="text-slate-400 text-sm mt-1">
          Importez un fichier CSV ou Excel — l'Agent Data Analyst fournit une analyse statistique complète.
        </p>
      </div>

      {/* Zone d'upload */}
      {!stats && !loading && (
        <Card
          className="p-12 border-dashed border-2 border-slate-600 hover:border-yukpo-500/50 transition-colors cursor-pointer"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={handleFileInput}
          />
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="w-16 h-16 rounded-2xl bg-slate-700 flex items-center justify-center">
              <Upload className="w-8 h-8 text-slate-400" />
            </div>
            <div>
              <p className="text-white font-semibold">Glissez votre fichier ici</p>
              <p className="text-slate-400 text-sm mt-1">ou cliquez pour sélectionner</p>
              <p className="text-slate-500 text-xs mt-2">CSV, XLSX, XLS — max 5 000 lignes</p>
            </div>
            <Button variant="secondary" icon={<FileUp className="w-4 h-4" />}>
              Choisir un fichier
            </Button>
          </div>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <Card className="p-12 flex flex-col items-center gap-4">
          <Spinner size="lg" />
          <div className="text-center">
            <p className="text-white font-medium">Analyse de {fichierNom} en cours…</p>
            <p className="text-slate-400 text-sm mt-1">L'agent DAA calcule les statistiques descriptives</p>
          </div>
        </Card>
      )}

      {/* Résultats */}
      {stats && !loading && (
        <div className="space-y-4 animate-fade-in">
          {/* Toolbar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart2 className="w-5 h-5 text-yukpo-400" />
              <span className="font-semibold text-white">{fichierNom}</span>
              <Badge variant="purple" size="sm">Analysé</Badge>
            </div>
            <Button
              variant="ghost"
              size="sm"
              icon={<X className="w-4 h-4" />}
              onClick={() => resetAnalyse()}
            >
              Nouveau fichier
            </Button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Résumé Markdown */}
            <Card className="p-5">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-4 h-4 text-accent-400" />
                <h3 className="text-sm font-semibold text-white">Résumé statistique</h3>
              </div>
              <div className="max-h-96 overflow-y-auto">
                <ReactMarkdown
                  className="prose prose-sm prose-invert max-w-none"
                  components={{
                    table: ({ children }) => (
                      <div className="overflow-x-auto">
                        <table className="text-xs border-collapse border border-slate-600 w-full">{children}</table>
                      </div>
                    ),
                    th: ({ children }) => <th className="border border-slate-600 px-2 py-1 bg-slate-700 text-left">{children}</th>,
                    td: ({ children }) => <td className="border border-slate-600 px-2 py-1">{children}</td>,
                    code: ({ children }) => <code className="bg-slate-900 text-yukpo-300 px-1 py-0.5 rounded text-xs font-mono">{children}</code>,
                  }}
                >
                  {renduMarkdown}
                </ReactMarkdown>
              </div>
            </Card>

            {/* Statistiques détaillées par colonne */}
            <Card className="p-5">
              <h3 className="text-sm font-semibold text-white mb-3">Détail par colonne</h3>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {Object.entries(stats as Record<string, Record<string, unknown>>).map(([col, st]) => (
                  <div key={col} className="p-3 rounded-xl" style={{ background: "var(--ykp-elevated)", border: "1px solid var(--ykp-border)" }}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm font-medium text-white">{col}</span>
                      <Badge variant={(st as Record<string, unknown>).type === "numerique" ? "cyan" : "slate"} size="sm">
                        {String((st as Record<string, unknown>).type || "texte")}
                      </Badge>
                    </div>
                    {(st as Record<string, unknown>).type === "numerique" ? (
                      <div className="grid grid-cols-3 gap-1 text-xs text-slate-400">
                        <span>Moy: <span className="text-white">{String((st as Record<string, unknown>).moyenne ?? "-")}</span></span>
                        <span>Min: <span className="text-white">{String((st as Record<string, unknown>).min ?? "-")}</span></span>
                        <span>Max: <span className="text-white">{String((st as Record<string, unknown>).max ?? "-")}</span></span>
                        <span>Std: <span className="text-white">{String((st as Record<string, unknown>).std ?? "-")}</span></span>
                        <span>Nuls: <span className="text-red-400">{String((st as Record<string, unknown>).nb_nuls ?? 0)}</span></span>
                        <span>Outliers: <span className="text-yellow-400">{String((st as Record<string, unknown>).nb_outliers ?? 0)}</span></span>
                      </div>
                    ) : (
                      <div className="text-xs text-slate-400">
                        <span>Valeurs uniques: <span className="text-white">{String((st as Record<string, unknown>).nb_uniques ?? "-")}</span></span>
                        {Boolean((st as Record<string, unknown>).valeur_la_plus_frequente) && (
                          <span className="ml-2">Plus fréquent: <span className="text-white">{String((st as Record<string, unknown>).valeur_la_plus_frequente)}</span></span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* Aperçu données */}
          {apercu && apercu.length > 0 && (
            <Card className="p-5">
              <h3 className="text-sm font-semibold text-white mb-3">
                Aperçu (premières lignes)
              </h3>
              <div className="overflow-x-auto max-h-64">
                <table className="text-xs border-collapse border border-slate-700 w-full">
                  <thead>
                    <tr>
                      {Object.keys(apercu[0]).slice(0, 10).map((col) => (
                        <th key={col} className="border border-slate-600 px-2 py-1.5 bg-slate-700 text-left text-slate-300 whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {apercu.slice(0, 10).map((row, i) => (
                      <tr key={i} className={i % 2 === 0 ? "bg-slate-800/30" : ""}>
                        {Object.values(row).slice(0, 10).map((val, j) => (
                          <td key={j} className="border border-slate-700/50 px-2 py-1 text-slate-300 whitespace-nowrap">
                            {String(val ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-500 mt-2">
                Utilisez le Copilote pour des analyses approfondies sur ce dataset.
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};
