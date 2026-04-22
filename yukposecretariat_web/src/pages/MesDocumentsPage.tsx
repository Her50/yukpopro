import { useState } from 'react'
import { FolderOpen, Download, Trash2, Loader2, RefreshCw, Search } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsAPI } from '../api/client'
import toast from 'react-hot-toast'

interface Document {
  fichier_id: string; type: string; type_label: string; icone: string;
  extension: string; taille_ko: number; date_creation: number; nom_affiche: string
}

function dateLocale(ts: number) {
  return new Date(ts * 1000).toLocaleString('fr-FR', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

const FILTRES = ['Tous', 'Rédaction IA', 'Scan / OCR', 'Traduction', 'Audio → Doc', 'Infographie PDF', 'Devis', 'Facture']

export default function MesDocumentsPage() {
  const qc = useQueryClient()
  const [recherche, setRecherche] = useState('')
  const [filtre, setFiltre] = useState('Tous')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['mes-documents'],
    queryFn: () => documentsAPI.lister().then(r => r.data),
    refetchOnWindowFocus: true,
  })

  const supprimerMutation = useMutation({
    mutationFn: (fichier_id: string) => documentsAPI.supprimer(fichier_id),
    onSuccess: () => {
      toast.success('Document supprimé')
      qc.invalidateQueries({ queryKey: ['mes-documents'] })
    },
    onError: () => toast.error('Erreur lors de la suppression'),
  })

  const telecharger = async (doc: Document) => {
    try {
      const r = await documentsAPI.telecharger(doc.fichier_id)
      const url = URL.createObjectURL(new Blob([r.data]))
      const a = document.createElement('a')
      a.href = url; a.download = doc.fichier_id; a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Erreur de téléchargement')
    }
  }

  const confirmerSuppression = (doc: Document) => {
    if (window.confirm(`Supprimer "${doc.nom_affiche}" ?`)) {
      supprimerMutation.mutate(doc.fichier_id)
    }
  }

  const docs: Document[] = data?.documents ?? []
  const filtres = docs.filter(d => {
    const ok_filtre = filtre === 'Tous' || d.type_label === filtre
    const ok_search = !recherche || d.nom_affiche.toLowerCase().includes(recherche.toLowerCase())
    return ok_filtre && ok_search
  })

  const extColor: Record<string, string> = {
    PDF: 'bg-red-100 text-red-700', DOCX: 'bg-blue-100 text-blue-700',
    PNG: 'bg-green-100 text-green-700', JPG: 'bg-green-100 text-green-700',
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <FolderOpen className="text-orange-500" size={24} />
            Mes Documents
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            {docs.length} document{docs.length !== 1 ? 's' : ''} généré{docs.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button onClick={() => refetch()}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-orange-500 transition-colors px-3 py-2 rounded-xl hover:bg-orange-50">
          <RefreshCw size={15} />
          Actualiser
        </button>
      </div>

      {/* Filtres + recherche */}
      <div className="space-y-3">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={recherche} onChange={e => setRecherche(e.target.value)}
            placeholder="Rechercher un document…"
            className="w-full border border-gray-300 rounded-xl pl-9 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
        </div>
        <div className="flex flex-wrap gap-2">
          {FILTRES.map(f => (
            <button key={f} onClick={() => setFiltre(f)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${filtre === f ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Liste */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <Loader2 size={24} className="animate-spin mr-2" />
          Chargement…
        </div>
      ) : filtres.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-12 text-center">
          <FolderOpen size={40} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500 font-medium">Aucun document trouvé</p>
          <p className="text-gray-400 text-sm mt-1">Les documents générés apparaîtront ici automatiquement</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 divide-y divide-gray-50">
          {filtres.map(doc => (
            <div key={doc.fichier_id} className="flex items-center gap-3 px-4 py-3.5 hover:bg-gray-50 transition-colors group">
              {/* Icône type */}
              <div className="text-2xl w-8 text-center shrink-0">{doc.icone}</div>

              {/* Infos */}
              <div className="flex-1 min-w-0">
                <div className="font-medium text-gray-900 text-sm truncate">{doc.nom_affiche}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${extColor[doc.extension] || 'bg-gray-100 text-gray-600'}`}>
                    {doc.extension}
                  </span>
                  <span className="text-xs text-gray-400">{doc.taille_ko} Ko</span>
                  <span className="text-xs text-gray-400 hidden sm:inline">·</span>
                  <span className="text-xs text-gray-400 hidden sm:inline">{dateLocale(doc.date_creation)}</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={() => telecharger(doc)}
                  className="p-2 rounded-lg hover:bg-orange-50 text-gray-400 hover:text-orange-500 transition-colors"
                  title="Télécharger">
                  <Download size={16} />
                </button>
                <button onClick={() => confirmerSuppression(doc)}
                  className="p-2 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                  title="Supprimer">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
