/**
 * HistoriqueDocumentsPage — Historique des documents générés par l'IA.
 * Persisté en base de données. Permet de retrouver, retélécharger et améliorer
 * un document précédent via le chat.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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
  if (!type) return "secondary";
  if (type.startsWith("slides")) return "purple";
  if (type.startsWith("contrat") || type.startsWith("convention")) return "orange";
  if (type.startsWith("lettre") || type.startsWith("courrier")) return "green";
  if (type === "cv" || type === "lettre_emploi") return "pink";
  if (type === "traduction") return "green";
  if (type.startsWith("rapport") || type.startsWith("note") || type.startsWith("plan")) return "blue";
  return "secondary";
};

const resolveLabel = (type: string): string => {
  const labels: Record<string, string> = {
    rapport_analyse: "Rapport", rapport_financier: "Rapport financier",
    rapport_rh: "Rapport RH", rapport_audit: "Rapport audit",
    note_juridique: "Note juridique", note_de_synthese: "Note de synthèse",
    plan_action: "Plan d'action", compte_rendu: "Compte-rendu",
    contrat_bail: "Contrat de bail", contrat_travail: "Contrat de travail",
    contrat_prestation: "Contrat prestation", contrat_vente: "Contrat vente",
    contrat_generique: "Contrat", convention: "Convention",
    statuts: "Statuts", reglement_interieur: "Règlement intérieur",
    lettre_officielle: "Lettre officielle", lettre_commerciale: "Lettre commerciale",
    lettre_mise_en_demeure: "Mise en demeure", lettre_resiliation: "Résiliation",
    lettre_emploi: "Lettre emploi", attestation: "Attestation", certificat: "Certificat",
    cv: "CV", traduction: "Traduction",
  };
  if (labels[type]) return labels[type];
  if (type.startsWith("slides")) return "Présentation";
  return type.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
};

const TYPE_ICONS: Record<string, React.ReactNode> = {};   // legacy, non utilisé
const TYPE_COLORS: Record<string, string> = {};
const TYPE_LABELS: Record<string, string> = {};

export const HistoriqueDocumentsPage = () => {
  const navigate = useNavigate();
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
      toast.error("Impossible de charger l'historique");
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
    const prompt = doc.contenu_source
      ? `Je souhaite améliorer ce document (ID #${doc.id}) : "${doc.titre}".\n\nDemande initiale : ${doc.contenu_source}\n\nQue souhaitez-vous modifier ou améliorer ?`
      : `Je souhaite améliorer le document "${doc.titre}". Que voulez-vous modifier ?`;

    addMessage({
      id: crypto.randomUUID(),
      role: "assistant",
      content: `📄 Document chargé : **${doc.titre}**\n\n${
        doc.contenu_genere
          ? `Voici un aperçu du contenu actuel :\n\n${doc.contenu_genere.slice(0, 800)}${doc.contenu_genere.length > 800 ? "…" : ""}\n\n`
          : ""
      }Comment souhaitez-vous améliorer ou modifier ce document ? Décrivez vos changements.`,
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
      toast.success("Document supprimé");
    } catch {
      toast.error("Erreur lors de la suppression");
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
      return new Date(iso).toLocaleDateString("fr-FR", {
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
          <h1 className="text-2xl font-display font-bold text-white">Mes Documents</h1>
          <p className="text-slate-400 text-sm mt-1">
            {documents.length} document{documents.length !== 1 ? "s" : ""} générés · Retrouvez, retéléchargez ou améliorez via le chat
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw className="w-3.5 h-3.5" />} onClick={charger}>
            Actualiser
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon={<Plus className="w-3.5 h-3.5" />}
            onClick={() => navigate("/generateurs")}
          >
            Nouveau document
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
            placeholder="Rechercher un document…"
            value={recherche}
            onChange={e => setRecherche(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-yukpo-500"
          />
        </div>
        {/* Filtre type */}
        <div className="flex gap-1.5">
          {[
            { value: "all", label: "Tous" },
            { value: "rapport", label: "Rapports" },
            { value: "slides", label: "Slides" },
            { value: "traduction", label: "Traductions" },
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
              ? "Aucun document ne correspond à votre recherche"
              : "Aucun document généré pour l'instant"}
          </p>
          {!recherche && filtreType === "all" && (
            <p className="text-slate-600 text-sm mt-2">
              Créez votre premier rapport ou présentation via les Générateurs IA
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
                      {resolveLabel(doc.type_doc)}
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
                  title="Améliorer via le chat"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  Améliorer
                </button>

                {/* Télécharger */}
                {doc.fichier && (
                  <a
                    href={generateurApi.telecharger(doc.fichier)}
                    download={doc.fichier}
                    className="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
                    title="Télécharger"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </a>
                )}

                {/* Supprimer */}
                <button
                  onClick={() => handleSupprimer(doc)}
                  disabled={suppression === doc.id}
                  className="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-50"
                  title="Supprimer"
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
