import { useState } from 'react'
import { FolderOpen, Download, Trash2, Loader2, RefreshCw, Search, Wand2, X } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsAPI, infographieAPI } from '../api/client'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { DemoBanner } from '../components/DemoBanner'

interface Document {
  fichier_id: string; type: string; type_label: string; icone: string;
  extension: string; taille_ko: number; date_creation: number; nom_affiche: string
}

function dateLocale(ts: number) {
  return new Date(ts * 1000).toLocaleString('fr-FR', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// Filtres : la valeur reste la chaîne FR (utilisée pour matcher d.type_label côté API),
// l'affichage est traduit via i18n
const FILTRES_KEYS: { value: string; tKey: string }[] = [
  { value: 'Tous',             tKey: 'documents.filterAll' },
  { value: 'Rédaction Yukpo',  tKey: 'documents.filterRedaction' },
  { value: 'Scan / OCR',       tKey: 'documents.filterOcr' },
  { value: 'Traduction Yukpo', tKey: 'documents.filterTraduction' },
  { value: 'Audio → Doc',      tKey: 'documents.filterAudio' },
  { value: 'Infographie PDF',  tKey: 'documents.filterInfographie' },
  { value: 'Devis',            tKey: 'documents.filterDevis' },
  { value: 'Facture',          tKey: 'documents.filterDevis' },
]

type ModifierResult = { pdf_base64?: string; png_base64?: string; pdf_id?: string; png_id?: string; titre?: string }

export default function MesDocumentsPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [recherche, setRecherche] = useState('')
  const [filtre, setFiltre] = useState('Tous')
  const [modifierDoc, setModifierDoc] = useState<Document | null>(null)
  const [instructions, setInstructions] = useState('')
  const [modifierResult, setModifierResult] = useState<ModifierResult | null>(null)
  const [modifierLoading, setModifierLoading] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['mes-documents'],
    queryFn: () => documentsAPI.lister().then(r => r.data),
    refetchOnWindowFocus: true,
  })

  const supprimerMutation = useMutation({
    mutationFn: (fichier_id: string) => documentsAPI.supprimer(fichier_id),
    onSuccess: () => {
      toast.success(t('documents.deleted'))
      qc.invalidateQueries({ queryKey: ['mes-documents'] })
    },
    onError: () => toast.error(t('documents.deleteErr')),
  })

  const telecharger = async (doc: Document) => {
    try {
      const r = await documentsAPI.telecharger(doc.fichier_id)
      const url = URL.createObjectURL(new Blob([r.data]))
      const a = document.createElement('a')
      a.href = url; a.download = doc.fichier_id; a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error(t('traduction.downloadErr'))
    }
  }

  const confirmerSuppression = (doc: Document) => {
    if (window.confirm(t('documents.deleteConfirm'))) {
      supprimerMutation.mutate(doc.fichier_id)
    }
  }

  const docs: Document[] = data?.documents ?? []
  const filtres = docs.filter(d => {
    const ok_filtre = filtre === 'Tous' || d.type_label === filtre
    const ok_search = !recherche || d.nom_affiche.toLowerCase().includes(recherche.toLowerCase())
    return ok_filtre && ok_search
  })

  const lancerModification = async () => {
    if (!modifierDoc || !instructions.trim()) return
    setModifierLoading(true)
    setModifierResult(null)
    try {
      const r = await infographieAPI.modifier({ fichier_id: modifierDoc.fichier_id, instructions })
      setModifierResult(r.data)
      qc.invalidateQueries({ queryKey: ['mes-documents'] })
      toast.success(t('documents.visualUpdated'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || t('documents.modifyErr'))
    } finally {
      setModifierLoading(false)
    }
  }

  const telechargerBase64 = (b64: string, nom: string, mime: string) => {
    const bytes = atob(b64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const url = URL.createObjectURL(new Blob([arr], { type: mime }))
    const a = document.createElement('a'); a.href = url; a.download = nom; a.click()
    URL.revokeObjectURL(url)
  }

  const extColor: Record<string, string> = {
    PDF: 'bg-red-100 text-red-700', DOCX: 'bg-blue-100 text-blue-700',
    PNG: 'bg-green-100 text-green-700', JPG: 'bg-green-100 text-green-700',
  }

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <FolderOpen className="text-orange-500" size={24} />
            {t('documents.title')}
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            {t('documents.countGenerated', { n: docs.length })}
          </p>
        </div>
        <button onClick={() => refetch()}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-orange-500 transition-colors px-3 py-2 rounded-xl hover:bg-orange-50">
          <RefreshCw size={15} />
          {t('documents.refresh')}
        </button>
      </div>

      {/* Filtres + recherche */}
      <div className="space-y-3">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={recherche} onChange={e => setRecherche(e.target.value)}
            placeholder={t('documents.search')}
            className="w-full border border-gray-300 rounded-xl pl-9 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
        </div>
        <div className="flex flex-wrap gap-2">
          {FILTRES_KEYS.map(f => (
            <button key={f.value} onClick={() => setFiltre(f.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${filtre === f.value ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              {t(f.tKey)}
            </button>
          ))}
        </div>
      </div>

      {/* Liste */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <Loader2 size={24} className="animate-spin mr-2" />
          {t('common.loading')}
        </div>
      ) : filtres.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-12 text-center">
          <FolderOpen size={40} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500 font-medium">{t('documents.noDocs')}</p>
          <p className="text-gray-400 text-sm mt-1">{t('documents.noDocsHint')}</p>
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
                  <span className="text-xs text-gray-400">{t('common.fileSizeKo', { n: doc.taille_ko })}</span>
                  <span className="text-xs text-gray-400 hidden sm:inline">·</span>
                  <span className="text-xs text-gray-400 hidden sm:inline">{dateLocale(doc.date_creation)}</span>
                </div>
              </div>

              {/* Actions — toujours visibles (mobile-friendly) */}
              <div className="flex items-center gap-1.5 shrink-0">
                {doc.type === 'pdf' && (
                  <button
                    onClick={() => { setModifierDoc(doc); setInstructions(''); setModifierResult(null) }}
                    className="p-2 rounded-lg bg-purple-50 text-purple-500 hover:bg-purple-100 transition-colors"
                    title={t('documents.modifyWithYukpo')} aria-label={t('common.edit')}>
                    <Wand2 size={16} />
                  </button>
                )}
                <button onClick={() => telecharger(doc)}
                  className="p-2 rounded-lg bg-orange-50 text-orange-500 hover:bg-orange-100 transition-colors"
                  title={t('common.download')} aria-label={t('common.download')}>
                  <Download size={16} />
                </button>
                <button onClick={() => confirmerSuppression(doc)}
                  className="p-2 rounded-lg bg-red-50 text-red-500 hover:bg-red-100 transition-colors"
                  title={t('common.delete')} aria-label={t('common.delete')}>
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal : modifier infographie via chat */}
      {modifierDoc && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg space-y-4 p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-bold text-gray-900 flex items-center gap-2">
                <Wand2 size={18} className="text-purple-500" />
                {t('documents.modifyVisual')}
              </h2>
              <button onClick={() => setModifierDoc(null)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>

            <p className="text-xs text-gray-500 truncate">{modifierDoc.nom_affiche}</p>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                {t('documents.modifyInstructions')}
              </label>
              <textarea
                value={instructions}
                onChange={e => setInstructions(e.target.value)}
                rows={3}
                placeholder={t('documents.modifyInstructionsPlaceholder')}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
              />
            </div>

            <button
              onClick={lancerModification}
              disabled={modifierLoading || !instructions.trim()}
              className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {modifierLoading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
              {modifierLoading ? t('documents.modifying') : t('documents.applyModifications')}
            </button>

            {modifierResult && (
              <div className="space-y-3 border-t border-gray-100 pt-3">
                <p className="text-xs font-semibold text-green-600">{t('documents.visualUpdatedHint')}</p>
                {modifierResult.png_base64 && (
                  <img
                    src={`data:image/png;base64,${modifierResult.png_base64}`}
                    alt={t('documents.previewAlt')}
                    className="w-full rounded-xl border border-gray-200 object-contain max-h-72"
                  />
                )}
                <div className="flex gap-2">
                  {modifierResult.pdf_base64 && (
                    <button
                      onClick={() => telechargerBase64(modifierResult.pdf_base64!, `visuel-modifie.pdf`, 'application/pdf')}
                      className="flex-1 flex items-center justify-center gap-1.5 bg-red-500 text-white text-xs font-medium px-3 py-2 rounded-xl">
                      <Download size={14} /> PDF
                    </button>
                  )}
                  {modifierResult.png_base64 && (
                    <button
                      onClick={() => telechargerBase64(modifierResult.png_base64!, `visuel-modifie.png`, 'image/png')}
                      className="flex-1 flex items-center justify-center gap-1.5 bg-blue-500 text-white text-xs font-medium px-3 py-2 rounded-xl">
                      <Download size={14} /> PNG
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
