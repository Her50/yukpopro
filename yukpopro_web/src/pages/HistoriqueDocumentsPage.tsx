/**
 * HistoriqueDocumentsPage — Historique des documents générés par l'IA.
 * Persisté en base de données. Permet de retrouver, retélécharger et améliorer
 * un document précédent via le chat.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  FileText, Presentation, Download, Trash2, RefreshCw,
  MessageSquare, Clock, Search, Plus,
} from "lucide-react";
import { Card, Badge, Button, Spinner } from "@/components/ui";
import { DemoBanner } from "@/components/DemoBanner";
import { EmptyState } from "@/components/EmptyState";
import { generateurApi } from "@/api/client";
import { useDocsStore, useCopiloteStore } from "@/store";
import type { DocumentHistorique } from "@/types";
import toast from "react-hot-toast";
import { cn } from "@/components/ui";

// Résolution générique : retourne l'icône selon la famille du type
const resolveIcon = (type: string): React.ReactNode => {
  if (!type) return <FileText className="w-4 h-4 text-slate-400" />;
  if (type.startsWith("slides")) return <Presentation className="w-4 h-4 text-orange-400" />;
  if (type.startsWith("contrat") || type.startsWith("convention") || type.startsWith("statuts"))
    return <span className="text-base">📋</span>;
  if (type.startsWith("lettre") || type.startsWith("courrier"))
    return <span className="text-base">✉️</span>;
  if (type === "attestation" || type === "certificat")
    return <span className="text-base">🏅</span>;
  if (type === "cv" || type === "lettre_emploi")
    return <span className="text-base">👤</span>;
  if (type === "traduction") return <span className="text-base">🌐</span>;
  if (type.startsWith("rapport") || type.startsWith("note") || type.startsWith("plan"))
    return <FileText className="w-4 h-4 text-blue-400" />;
  return <FileText className="w-4 h-4 text-slate-400" />;
};

const resolveColor = (type: string): string => {
  if (!type) return "slate";
  if (type.startsWith("slides")) return "purple";
  if (type.startsWith("contrat") || type.startsWith("convention")) return "gold";
  if (type.startsWith("lettre") || type.startsWith("courrier")) return "green";
  if (type === "cv" || type === "lettre_emploi") return "red";
  if (type === "traduction") return "green";
  if (type.startsWith("rapport") || type.startsWith("note") || type.startsWith("plan")) return "cyan";
  return "slate";
};

const resolveLabel = (type: string, t: (k: string, opts?: any) => string): string => {
  if (!type || !type.trim()) return t("documents.types.default");
  // i18n key d'abord, fallback sur la clé brute
  const key = `documents.types.${type}`;
  const tr = t(key);
  if (tr && tr !== key) return tr;
  if (type.startsWith("slides")) return t("documents.types.slides");
  const cleaned = type.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()).trim();
  return cleaned || t("documents.types.default");
};

const TYPE_ICONS: Record<string, React.ReactNode> = {};   // legacy, non utilisé
const TYPE_COLORS: Record<string, string> = {};
const TYPE_LABELS: Record<string, string> = {};

export const HistoriqueDocumentsPage = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { newSession, addMessage, setActiveDocument } = useCopiloteStore();
  const { supprimerVersBackend } = useDocsStore();

  const [documents, setDocuments] = useState<DocumentHistorique[]>([]);
  const [loading, setLoading] = useState(true);
  const [recherche, setRecherche] = useState("");
  const [filtreType, setFiltreType] = useState<string>("all");
  const [suppression, setSuppression] = useState<number | null>(null);

  const charger = async () => {
    setLoading(true);
    try {
      const res = await generateurApi.historiqueDocuments();
      setDocuments(res.documents);
    } catch {
      toast.error(t("documents.errors.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { charger(); }, []);

  // Ouvre le chat avec le contexte du document pour amélioration
  const ameliorerViaChat = (doc: DocumentHistorique) => {
    newSession();
    setActiveDocument({
      id: doc.id,
      titre: doc.titre,
      type_doc: doc.type_doc,
      contenu_genere: doc.contenu_genere,
    });
    addMessage({
      id: crypto.randomUUID(),
      role: "assistant",
      content: `📄 ${t("documents.chat.documentLoaded", { titre: doc.titre })}\n\n${
        doc.contenu_genere
          ? `${t("documents.chat.previewIntro")}\n\n${doc.contenu_genere.slice(0, 800)}${doc.contenu_genere.length > 800 ? "…" : ""}\n\n`
          : ""
      }${t("documents.chat.improvePrompt")}`,
      timestamp: new Date().toISOString(),
      document_ref: { id: doc.id, titre: doc.titre, type: doc.type_doc },
    });

    navigate("/chat");
  };

  const handleSupprimer = async (doc: DocumentHistorique) => {
    setSuppression(doc.id);
    try {
      await generateurApi.supprimerDocument(doc.id);
      setDocuments(prev => prev.filter(d => d.id !== doc.id));
      toast.success(t("documents.toast.deleted"));
    } catch {
      toast.error(t("documents.errors.deleteFailed"));
    } finally {
      setSuppression(null);
    }
  };

  const docsFiltres = documents.filter(doc => {
    const matchRecherche = !recherche ||
      doc.titre.toLowerCase().includes(recherche.toLowerCase()) ||
      (doc.contenu_source || "").toLowerCase().includes(recherche.toLowerCase());
    const matchType = filtreType === "all" || doc.type_doc === filtreType;
    return matchRecherche && matchType;
  });

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6 animate-fade-in">
      <DemoBanner />
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">{t("documents.title")}</h1>
          <p className="text-slate-400 text-sm mt-1">
            {t("documents.subtitle", { count: documents.length })}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw className="w-3.5 h-3.5" />} onClick={charger}>
            {t("common.refresh")}
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon={<Plus className="w-3.5 h-3.5" />}
            onClick={() => navigate("/generateurs")}
          >
            {t("documents.newDocument")}
          </Button>
        </div>
      </div>

      {/* Filtres */}
      <div className="flex gap-3 flex-wrap">
        {/* Recherche */}
        <div className="flex-1 min-w-52 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder={t("documents.searchPlaceholder")}
            value={recherche}
            onChange={e => setRecherche(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-yukpo-500"
          />
        </div>
        {/* Filtre type */}
        <div className="flex gap-1.5">
          {[
            { value: "all", label: t("documents.filters.all") },
            { value: "rapport", label: t("documents.filters.reports") },
            { value: "slides", label: t("documents.filters.slides") },
            { value: "traduction", label: t("documents.filters.translations") },
          ].map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setFiltreType(value)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border",
                filtreType === value
                  ? "bg-yukpo-500 text-white border-yukpo-500"
                  : "bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-600"
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Liste */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Spinner size="lg" />
        </div>
      ) : docsFiltres.length === 0 ? (
        <Card className="p-12 text-center border-dashed">
          <FileText className="w-12 h-12 text-slate-700 mx-auto mb-4" />
          <p className="text-slate-400 font-medium">
            {recherche || filtreType !== "all"
              ? t("documents.empty.noMatch")
              : t("documents.empty.noDocuments")}
          </p>
          {!recherche && filtreType === "all" && (
            <p className="text-slate-600 text-sm mt-2">
              {t("documents.empty.cta")}
            </p>
          )}
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {docsFiltres.map(doc => (
            <Card key={doc.id} className="p-4 flex flex-col gap-3 hover:border-slate-600 transition-colors group">
              {/* Header */}
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-lg bg-slate-700 flex items-center justify-center flex-shrink-0">
                  {resolveIcon(doc.type_doc)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant={resolveColor(doc.type_doc) as any} size="sm">
                      {resolveLabel(doc.type_doc, t)}
                    </Badge>
                  </div>
                  <h3 className="text-white font-medium text-sm mt-1 line-clamp-2 leading-tight">
                    {doc.titre}
                  </h3>
                </div>
              </div>

              {/* Aperçu contenu */}
              {doc.contenu_source && (
                <p className="text-slate-500 text-xs line-clamp-2 leading-relaxed">
                  {doc.contenu_source}
                </p>
              )}

              {/* Date */}
              <div className="flex items-center gap-1.5 text-slate-600 text-xs">
                <Clock className="w-3 h-3" />
                {formatDate(doc.cree_le)}
              </div>

              {/* Actions */}
              <div className="flex gap-2 mt-auto pt-1 border-t border-slate-800">
                {/* Améliorer via chat */}
                <button
                  onClick={() => ameliorerViaChat(doc)}
                  className="flex-1 flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-yukpo-500/10 text-yukpo-400 hover:bg-yukpo-500/20 transition-colors border border-yukpo-500/20"
                  title={t("documents.actions.improveTitle")}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  {t("documents.actions.improve")}
                </button>

                {/* Télécharger */}
                {doc.fichier && (
                  <a
                    href={generateurApi.telecharger(doc.fichier)}
                    download={doc.fichier}
                    className="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
                    title={t("common.download")}
                  >
                    <Download className="w-3.5 h-3.5" />
                  </a>
                )}

                {/* Supprimer */}
                <button
                  onClick={() => handleSupprimer(doc)}
                  disabled={suppression === doc.id}
                  className="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-50"
                  title={t("common.delete")}
                >
                  {suppression === doc.id
                    ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    : <Trash2 className="w-3.5 h-3.5" />
                  }
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
