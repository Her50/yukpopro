import { useRef } from 'react'
import { Scan, Upload, Download, Loader2, FileText } from 'lucide-react'
import { ocrAPI } from '../api/client'
import toast from 'react-hot-toast'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'
import { DemoBanner } from '../components/DemoBanner'
import { useLongOps, useLongOpField } from '../store/longOpsStore'

type Mode = 'scanner' | 'manuscrit'
type OcrResult = {
  texte_structure: string; type_document: string; confiance: number;
  word_base64?: string; titre?: string
}

const FORMATS_VALIDES = ['lettre', 'formulaire', 'recu', 'manuscrit', 'tableau']
const FORMATS_MANUSCRIT = ['lettre', 'rapport', 'liste', 'paragraphe']

export default function OcrPage() {
  const { t } = useTranslation()
  const [mode, setMode] = useLongOpField<Mode>('ocr', 'mode', 'scanner')
  const [fichier, setFichier] = useLongOpField<File | null>('ocr', 'fichier', null)
  const [preview, setPreview] = useLongOpField<string | null>('ocr', 'preview', null)
  const [typeAttendu, setTypeAttendu] = useLongOpField<string>('ocr', 'typeAttendu', '')
  const [formaterEn, setFormaterEn] = useLongOpField<string>('ocr', 'formaterEn', 'paragraphe')
  const loading = useLongOps((s) => s.loading.ocr)
  const resultat = useLongOps((s) => s.resultats.ocr) as OcrResult | null
  const setResultat = (r: OcrResult | null) => useLongOps.getState().setResultat('ocr', r)
  const runOp = useLongOps((s) => s.run)
  const inputRef = useRef<HTMLInputElement>(null)

  const selectionnerFichier = (f: File) => {
    setFichier(f)
    const url = URL.createObjectURL(f)
    setPreview(url)
    setResultat(null)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f) selectionnerFichier(f)
  }

  const scanner = async () => {
    if (!fichier) { toast.error(t('ocr.noFile')); return }
    try {
      await runOp<OcrResult>('ocr', async () => {
        if (mode === 'manuscrit') {
          const fd2 = new FormData()
          fd2.append('fichier', fichier)
          fd2.append('formater_en', formaterEn)
          const r2 = await ocrAPI.manuscrit(fd2)
          return r2.data as OcrResult
        }
        const fd = new FormData()
        fd.append('fichier', fichier)
        if (typeAttendu) fd.append('type_attendu', typeAttendu)
        fd.append('export_word', 'true')
        const r = await ocrAPI.scanner(fd)
        return r.data as OcrResult
      })
      toast.success(t('ocr.okExtract'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || t('ocr.errExtract'))
    }
  }

  const telechargerWord = () => {
    if (!resultat?.word_base64) return
    const bytes = atob(resultat.word_base64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const blob = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'document-ocr.docx'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Scan className="text-green-600" size={24} />
          {t('ocr.title')}
        </h1>
        <p className="text-gray-500 text-sm mt-1">{t('ocr.subtitle')}</p>
      </div>

      {/* Mode selector */}
      <div className="flex gap-2">
        {(['scanner', 'manuscrit'] as Mode[]).map(m => (
          <button
            key={m}
            onClick={() => { setMode(m); setResultat(null) }}
            className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-colors ${
              mode === m ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {m === 'scanner' ? t('ocr.scanModePrint') : t('ocr.scanModeHand')}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        {/* Upload zone */}
        <div
          onDrop={handleDrop}
          onDragOver={e => e.preventDefault()}
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center cursor-pointer hover:border-green-400 hover:bg-green-50 transition-colors"
        >
          {preview ? (
            <img src={preview} alt={t('common.preview')} className="max-h-48 mx-auto rounded-lg object-contain" />
          ) : (
            <>
              <Upload size={32} className="mx-auto text-gray-300 mb-2" />
              <p className="text-sm text-gray-500">{t('ocr.uploadHint')}</p>
              <p className="text-xs text-gray-400 mt-1">{t('ocr.uploadAccept')}</p>
            </>
          )}
          <input ref={inputRef} type="file" accept="image/*" className="hidden"
            onChange={e => { if (e.target.files?.[0]) selectionnerFichier(e.target.files[0]) }} />
        </div>

        {/* Options */}
        {mode === 'scanner' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">{t('ocr.expectedType')}</label>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setTypeAttendu('')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${!typeAttendu ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600'}`}
              >{t('ocr.autoDetect')}</button>
              {FORMATS_VALIDES.map(f => (
                <button key={f} onClick={() => setTypeAttendu(f)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize ${typeAttendu === f ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600'}`}
                >{f}</button>
              ))}
            </div>
          </div>
        )}

        {mode === 'manuscrit' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">{t('ocr.formatAs')}</label>
            <div className="flex flex-wrap gap-2">
              {FORMATS_MANUSCRIT.map(f => (
                <button key={f} onClick={() => setFormaterEn(f)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize ${formaterEn === f ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600'}`}
                >{f}</button>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={scanner}
          disabled={loading || !fichier}
          className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Scan size={18} />}
          {loading ? t('ocr.extracting') : t('ocr.extract')}
        </button>
      </div>

      {/* Résultat */}
      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-lg capitalize">{resultat.type_document}</span>
              <span className="ml-2 text-xs text-gray-400">{t('ocr.confidence', { pct: Math.round(resultat.confiance * 100) })}</span>
            </div>
            {resultat.word_base64 && (
              <button onClick={telechargerWord}
                className="flex items-center gap-1.5 bg-green-600 text-white text-xs font-medium px-3 py-2 rounded-xl">
                <Download size={14} /> .docx
              </button>
            )}
          </div>
          <div className="prose prose-sm max-w-none text-gray-700 border-t border-gray-100 pt-3">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{resultat.texte_structure}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}
