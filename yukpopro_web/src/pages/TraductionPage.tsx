import { useState, useRef, FormEvent } from "react";
import {
  Languages, ArrowRight, Copy, Download, CheckCircle,
  Upload, FileText, X, File as FileIcon,
} from "lucide-react";
import toast from "react-hot-toast";
import { Card, Button, Textarea, Select, Badge } from "@/components/ui";
import { generateurApi } from "@/api/client";
import { useProfilStore } from "@/store";

const LANGUES = [
  { value: "fr", label: "🇫🇷 Français" },
  { value: "en", label: "🇬🇧 Anglais" },
  { value: "es", label: "🇪🇸 Espagnol" },
  { value: "pt", label: "🇵🇹 Portugais" },
  { value: "ar", label: "🇸🇦 Arabe" },
  { value: "zh", label: "🇨🇳 Mandarin" },
];

const CONTEXTES_METIER = [
  { value: "", label: "Général (aucun contexte spécifique)" },
  { value: "comptabilite", label: "Comptabilité / Fiscalité" },
  { value: "juridique", label: "Juridique / Droit OHADA" },
  { value: "rh", label: "Ressources humaines" },
  { value: "finance", label: "Finance / Banque" },
  { value: "ingenierie", label: "Ingénierie / BTP" },
  { value: "ong_developpement", label: "ONG / Développement" },
  { value: "microfinance", label: "Microfinance / SFD" },
  { value: "douane", label: "Douane / Commerce international" },
  { value: "assurance", label: "Assurance / CIMA" },
];

// Formats acceptés pour l'upload
const FORMATS_ACCEPTES = ".pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.xls,.pptx,.png,.jpg,.jpeg";
const FORMATS_LABEL = "PDF, Word, TXT, CSV, Excel, PowerPoint, Image";

type ModeTraduction = "texte" | "fichier";

interface ResultatTraduction {
  texte_traduit: string;
  nb_mots_source: number;
  nb_mots_cible: number;
  chemin_docx?: string;
  fichier_traduit?: string;
  format_sortie?: string;
  sauvegarde_mes_documents?: boolean;
  fichier_source?: string;
}

export const TraductionPage = () => {
  const { profil } = useProfilStore();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<ModeTraduction>("texte");

  // Mode texte
  const [contenu, setContenu] = useState("");

  // Mode fichier
  const [fichierSelectionne, setFichierSelectionne] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Commun
  const [langueSource, setLangueSource] = useState("fr");
  const [langueCible, setLangueCible] = useState("en");
  const [contexteMetier, setContexteMetier] = useState(profil?.metier || "");
  const [formatSortie, setFormatSortie] = useState("docx");
  const [resultat, setResultat] = useState<ResultatTraduction | null>(null);
  const [copie, setCopie] = useState(false);

  const inverserLangues = () => {
    const tmp = langueSource;
    setLangueSource(langueCible);
    setLangueCible(tmp);
    if (resultat) {
      setContenu(resultat.texte_traduit);
      setResultat(null);
    }
  };

  // ── Traduction texte ──────────────────────────────────────────────────────

  const handleTraduireTexte = async (e: FormEvent) => {
    e.preventDefault();
    if (!contenu.trim()) return;
    setLoading(true);
    setResultat(null);
    try {
      const res = await generateurApi.traduire({
        contenu,
        langue_source: langueSource,
        langue_cible: langueCible,
        contexte_metier: contexteMetier || undefined,
        format_sortie: formatSortie,
      });
      setResultat(res);
      toast.success("Traduction terminée !");
    } catch {
      toast.error("Erreur lors de la traduction");
    } finally {
      setLoading(false);
    }
  };

  // ── Traduction fichier ────────────────────────────────────────────────────

  const handleFichierChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      if (f.size > 20 * 1024 * 1024) {
        toast.error("Fichier trop volumineux (max 20 MB)");
        return;
      }
      setFichierSelectionne(f);
      setResultat(null);
    }
  };

  const handleTraduireFichier = async (e: FormEvent) => {
    e.preventDefault();
    if (!fichierSelectionne) return;
    setLoading(true);
    setResultat(null);

    const formData = new FormData();
    formData.append("fichier", fichierSelectionne);
    formData.append("langue_source", langueSource);
    formData.append("langue_cible", langueCible);
    formData.append("contexte_metier", contexteMetier);
    formData.append("format_sortie", formatSortie);

    try {
      const res = await generateurApi.traduireFichier(formData);
      setResultat(res);
      toast.success("Fichier traduit avec succès !");
    } catch (err: any) {
      const detail = err?.response?.data?.detail || "Erreur lors de la traduction du fichier";
      toast.error(detail.slice(0, 120));
    } finally {
      setLoading(false);
    }
  };

  const handleCopier = () => {
    if (!resultat) return;
    navigator.clipboard.writeText(resultat.texte_traduit).then(() => {
      setCopie(true);
      setTimeout(() => setCopie(false), 2000);
    });
  };

  const supprimerFichier = () => {
    setFichierSelectionne(null);
    setResultat(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const formatTaille = (bytes: number) => {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  };

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto animate-fade-in">
      <div>
        <h1 className="text-2xl font-display font-bold text-white">Traduction Professionnelle</h1>
        <p className="text-slate-400 text-sm mt-1">
          Traduction avec terminologie métier africaine — SYSCOHADA, OHADA, COBAC, FCFA, UEMOA, CEMAC préservés.
        </p>
      </div>

      {/* ── Sélecteur mode ──────────────────────────────────────────────────── */}
      <div className="flex gap-1 bg-slate-800/50 p-1 rounded-xl w-fit">
        <button
          onClick={() => { setMode("texte"); setResultat(null); }}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            mode === "texte" ? "bg-yukpo-500 text-white" : "text-slate-400 hover:text-white"
          }`}
        >
          <Languages className="w-4 h-4" /> Traduire du texte
        </button>
        <button
          onClick={() => { setMode("fichier"); setResultat(null); }}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            mode === "fichier" ? "bg-yukpo-500 text-white" : "text-slate-400 hover:text-white"
          }`}
        >
          <Upload className="w-4 h-4" /> Traduire un fichier
        </button>
      </div>

      {/* ── Config langues ──────────────────────────────────────────────────── */}
      <Card className="p-5">
        <div className="flex items-center gap-4 flex-wrap">
          <Select
            options={LANGUES}
            value={langueSource}
            onChange={(e) => setLangueSource(e.target.value)}
            className="w-44"
          />
          <button
            onClick={inverserLangues}
            className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors"
            title="Inverser les langues"
          >
            <ArrowRight className="w-4 h-4" />
          </button>
          <Select
            options={LANGUES}
            value={langueCible}
            onChange={(e) => setLangueCible(e.target.value)}
            className="w-44"
          />
          <Select
            options={CONTEXTES_METIER}
            value={contexteMetier}
            onChange={(e) => setContexteMetier(e.target.value)}
            className="flex-1 min-w-48"
          />
          <div className="flex gap-2">
            {["texte", "docx"].map((fmt) => (
              <label key={fmt} className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border cursor-pointer text-sm transition-colors ${
                formatSortie === fmt ? "border-yukpo-500 bg-yukpo-500/10 text-yukpo-300" : "border-slate-600 text-slate-400 hover:border-slate-500"
              }`}>
                <input type="radio" name="fmt-trad" value={fmt} checked={formatSortie === fmt} onChange={() => setFormatSortie(fmt)} className="hidden" />
                {fmt === "docx" ? "DOCX" : "Texte"}
              </label>
            ))}
          </div>
        </div>
      </Card>

      {/* ══ MODE TEXTE ══════════════════════════════════════════════════════════ */}
      {mode === "texte" && (
        <form onSubmit={handleTraduireTexte}>
          {/* Bouton en haut — toujours visible quelle que soit la hauteur de l'écran */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-slate-500">{contenu.split(/\s+/).filter(Boolean).length} mots</span>
            <Button type="submit" loading={loading} size="sm" icon={<Languages className="w-4 h-4" />} disabled={!contenu.trim()}>
              Traduire
            </Button>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Source */}
            <div className="space-y-3">
              <label className="text-sm font-medium text-slate-300">Texte source</label>
              <Textarea
                placeholder="Collez ici le texte à traduire — rapport, contrat, email, note de synthèse…"
                value={contenu}
                onChange={(e) => setContenu(e.target.value)}
                rows={14}
              />
            </div>
            {/* Résultat */}
            <ZoneResultat
              loading={loading}
              resultat={resultat}
              copie={copie}
              onCopier={handleCopier}
              generateurApi={generateurApi}
              modeFichier={false}
            />
          </div>
        </form>
      )}

      {/* ══ MODE FICHIER ════════════════════════════════════════════════════════ */}
      {mode === "fichier" && (
        <form onSubmit={handleTraduireFichier}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Zone upload */}
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-slate-300 block mb-2">
                  Document à traduire
                </label>
                {!fichierSelectionne ? (
                  <div
                    className="border-2 border-dashed border-slate-600 hover:border-yukpo-500 rounded-xl p-8 text-center cursor-pointer transition-colors group"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="w-10 h-10 text-slate-600 group-hover:text-yukpo-400 mx-auto mb-3 transition-colors" />
                    <p className="text-slate-300 font-medium text-sm mb-1">
                      Cliquez pour sélectionner un fichier
                    </p>
                    <p className="text-slate-500 text-xs">{FORMATS_LABEL}</p>
                    <p className="text-slate-600 text-xs mt-1">Maximum 20 MB</p>
                  </div>
                ) : (
                  <div className="border border-slate-600 rounded-xl p-4 flex items-center gap-3 bg-slate-800/50">
                    <div className="w-10 h-10 rounded-lg bg-yukpo-500/20 flex items-center justify-center flex-shrink-0">
                      <FileText className="w-5 h-5 text-yukpo-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-white text-sm font-medium truncate">{fichierSelectionne.name}</p>
                      <p className="text-slate-400 text-xs">{formatTaille(fichierSelectionne.size)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={supprimerFichier}
                      className="text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={FORMATS_ACCEPTES}
                  onChange={handleFichierChange}
                  className="hidden"
                />
              </div>

              {/* Info formats */}
              <Card className="p-4">
                <p className="text-slate-400 text-xs font-semibold uppercase tracking-wide mb-2">Formats supportés</p>
                <div className="flex flex-wrap gap-1.5">
                  {["PDF", "DOCX", "PPTX", "TXT", "CSV", "XLSX", "PNG", "JPG"].map((fmt) => (
                    <span key={fmt} className="px-2 py-0.5 rounded-md bg-slate-700 text-slate-300 text-xs font-mono">
                      {fmt}
                    </span>
                  ))}
                </div>
                <p className="text-slate-500 text-xs mt-2">
                  Les images sont analysées par reconnaissance intelligente (OCR). Le texte extrait est traduit et retourné.
                </p>
              </Card>

              {/* Bouton — dans la colonne gauche, toujours visible */}
              <Button
                type="submit"
                loading={loading}
                size="lg"
                icon={<Languages className="w-4 h-4" />}
                disabled={!fichierSelectionne}
                className="w-full"
              >
                {loading ? "Traduction en cours…" : "Traduire le fichier"}
              </Button>
            </div>

            {/* Résultat */}
            <ZoneResultat
              loading={loading}
              resultat={resultat}
              copie={copie}
              onCopier={handleCopier}
              generateurApi={generateurApi}
              modeFichier={true}
            />
          </div>
        </form>
      )}
    </div>
  );
};

// ── Composant carte téléchargement ───────────────────────────────────────────

function CarteTelechargement({
  resultat,
  generateurApi,
}: {
  resultat: ResultatTraduction;
  generateurApi: typeof import("@/api/client")["generateurApi"];
}) {
  const nomFichier = resultat.chemin_docx ?? "";
  if (!nomFichier) return null;
  const ext = nomFichier.split(".").pop()?.toUpperCase() ?? "DOCX";
  const icone = ext === "PPTX" ? "📊" : "📄";

  return (
    <div className="rounded-xl border border-yukpo-500/40 bg-yukpo-500/10 p-4 space-y-3">
      {/* En-tête */}
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-yukpo-500/20 flex items-center justify-center text-xl flex-shrink-0">
          {icone}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-white font-semibold text-sm">Fichier traduit prêt</p>
          <p className="text-slate-400 text-xs truncate mt-0.5">{nomFichier}</p>
          <p className="text-slate-500 text-xs mt-0.5">{resultat.nb_mots_cible} mots • Format {ext}</p>
        </div>
      </div>

      {/* Bouton télécharger */}
      <a
        href={generateurApi.telecharger(nomFichier)}
        download={nomFichier}
        className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg bg-yukpo-500 hover:bg-yukpo-600 text-white font-medium text-sm transition-colors"
      >
        <Download className="w-4 h-4" />
        Télécharger le fichier traduit ({ext})
      </a>

      {/* Badge Mes Documents */}
      {resultat.sauvegarde_mes_documents && (
        <div className="flex items-center gap-1.5 text-xs text-green-400">
          <CheckCircle className="w-3.5 h-3.5" />
          Sauvegardé dans Mes Documents
        </div>
      )}
    </div>
  );
}

// ── Composant zone résultat partagé ──────────────────────────────────────────

interface ZoneResultatProps {
  loading: boolean;
  resultat: ResultatTraduction | null;
  copie: boolean;
  onCopier: () => void;
  generateurApi: typeof import("@/api/client")["generateurApi"];
  modeFichier?: boolean;
}

function ZoneResultat({ loading, resultat, copie, onCopier, generateurApi, modeFichier }: ZoneResultatProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-300">Traduction</label>
          {resultat && (
            <Badge variant="green" size="sm">✓ {resultat.nb_mots_cible} mots</Badge>
          )}
        </div>
        {resultat && (
          <button
            type="button"
            onClick={onCopier}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            {copie ? <CheckCircle className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
            {copie ? "Copié !" : "Copier le texte"}
          </button>
        )}
      </div>

      {/* Carte téléchargement — mode fichier, en haut de la zone résultat */}
      {modeFichier && resultat?.chemin_docx && (
        <CarteTelechargement resultat={resultat} generateurApi={generateurApi} />
      )}

      {loading ? (
        <Card className="flex items-center justify-center h-[300px] border-dashed">
          <div className="text-center space-y-3">
            <Languages className="w-8 h-8 text-yukpo-400 animate-pulse mx-auto" />
            <p className="text-slate-400 text-sm">Yukpo Pro traduit votre document…</p>
            <p className="text-slate-600 text-xs">Yukpo applique la terminologie métier africaine</p>
          </div>
        </Card>
      ) : resultat ? (
        <div className="h-[300px] overflow-y-auto bg-slate-800 border border-slate-600 rounded-xl p-4 text-sm text-slate-100 leading-relaxed whitespace-pre-wrap">
          {resultat.texte_traduit}
        </div>
      ) : (
        <Card className="flex items-center justify-center h-[300px] border-dashed">
          <p className="text-slate-600 text-sm">La traduction apparaîtra ici</p>
        </Card>
      )}
    </div>
  );
}
