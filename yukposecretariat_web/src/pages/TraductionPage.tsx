import { useRef } from 'react'
import { Languages, Loader2, Download, Upload, FileText, ArrowRight } from 'lucide-react'
import { traductionAPI } from '../api/client'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { DemoBanner } from '../components/DemoBanner'
import { useLongOps, useLongOpField } from '../store/longOpsStore'

const LANGUES = [
  { code: 'fr', label: '🇫🇷 Français' }, { code: 'en', label: '🇬🇧 Anglais' },
  { code: 'es', label: '🇪🇸 Espagnol' }, { code: 'pt', label: '🇵🇹 Portugais' },
  { code: 'ar', label: '🇲🇦 Arabe' }, { code: 'zh', label: '🇨🇳 Mandarin' },
  { code: 'wo', label: '🇸🇳 Wolof' }, { code: 'ha', label: '🇳🇬 Haoussa' },
  { code: 'sw', label: '🇹🇿 Swahili' },
]

const CONTEXTES: { code: string; labelKey: string }[] = [
  { code: '', labelKey: 'traduction.ctxGeneral' },
  { code: 'comptabilite', labelKey: 'traduction.ctxComptabilite' },
  { code: 'juridique', labelKey: 'traduction.ctxJuridique' },
  { code: 'rh', labelKey: 'traduction.ctxRh' },
  { code: 'finance', labelKey: 'traduction.ctxFinance' },
  { code: 'assurance', labelKey: 'traduction.ctxAssurance' },
  { code: 'commercial', labelKey: 'traduction.ctxCommercial' },
  { code: 'medical', labelKey: 'traduction.ctxMedical' },
  { code: 'ong', labelKey: 'traduction.ctxOng' },
]

type Mode = 'texte' | 'fichier'
type TradResult = {
  texte_traduit: string; nb_mots_source: number; nb_mots_cible: number; fichier_id?: string
}

export default function TraductionPage() {
  const { t } = useTranslation()
  const [mode, setMode] = useLongOpField<Mode>('traduction', 'mode', 'texte')
  const [langSource, setLangSource] = useLongOpField<string>('traduction', 'langSource', 'fr')
  const [langCible, setLangCible] = useLongOpField<string>('traduction', 'langCible', 'en')
  const [contexte, setContexte] = useLongOpField<string>('traduction', 'contexte', '')
  const [contenu, setContenu] = useLongOpField<string>('traduction', 'contenu', '')
  const loading = useLongOps((s) => s.loading.traduction)
  const resultat = useLongOps((s) => s.resultats.traduction) as TradResult | null
  const setResultat = (r: TradResult | null) => useLongOps.getState().setResultat('traduction', r)
  const runOp = useLongOps((s) => s.run)
  const fileRef = useRef<HTMLInputElement>(null)
  const [fichierNom, setFichierNom] = useLongOpField<string>('traduction', 'fichierNom', '')

  const swapLangues = () => {
    setLangSource(langCible)
    setLangCible(langSource)
  }

  const traduireTexte = async () => {
    if (!contenu.trim()) { toast.error(t('traduction.errEmpty')); return }
    if (langSource === langCible) { toast.error(t('traduction.errSameLang')); return }
    try {
      await runOp<TradResult>('traduction', async () => {
        const r = await traductionAPI.traduireTexte({
          contenu, langue_source: langSource, langue_cible: langCible,
          contexte_metier: contexte, format_sortie: 'docx',
        })
        return r.data as TradResult
      })
      toast.success(t('traduction.okTrans'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || t('traduction.errTrans'))
    }
  }

  const traduireFichier = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) { toast.error(t('traduction.errSelectFile')); return }
    try {
      await runOp<TradResult>('traduction', async () => {
        const fd = new FormData()
        fd.append('fichier', file)
        fd.append('langue_source', langSource)
        fd.append('langue_cible', langCible)
        fd.append('contexte_metier', contexte)
        const r = await traductionAPI.traduireFichier(fd)
        return r.data as TradResult
      })
      toast.success(t('traduction.okTrans'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || t('traduction.errTrans'))
    }
  }

  const telecharger = async (fichier_id: string) => {
    try {
      const r = await traductionAPI.telecharger(fichier_id)
      const url = URL.createObjectURL(new Blob([r.data as BlobPart]))
      const a = document.createElement('a')
      a.href = url; a.download = fichier_id; a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error(t('traduction.downloadErr'))
    }
  }

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Languages className="text-orange-500" size={24} />
          {t('traduction.title')}
        </h1>
        <p className="text-gray-500 text-sm mt-1">{t('traduction.subtitle')}</p>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-2 bg-gray-100 p-1 rounded-xl w-fit">
        {(['texte', 'fichier'] as Mode[]).map(m => (
          <button key={m} onClick={() => { setMode(m); setResultat(null) }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${mode === m ? 'bg-white shadow text-orange-600' : 'text-gray-500 hover:text-gray-700'}`}>
            {m === 'texte' ? t('traduction.modeText') : t('traduction.modeFile')}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        {/* Paire de langues */}
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <label className="block text-xs font-semibold text-gray-500 mb-1">{t('traduction.sourceLang')}</label>
            <select value={langSource} onChange={e => setLangSource(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white">
              {LANGUES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
          <button onClick={swapLangues} className="mt-5 p-2 rounded-full bg-orange-50 hover:bg-orange-100 transition-colors">
            <ArrowRight size={18} className="text-orange-500" />
          </button>
          <div className="flex-1">
            <label className="block text-xs font-semibold text-gray-500 mb-1">{t('traduction.targetLang')}</label>
            <select value={langCible} onChange={e => setLangCible(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white">
              {LANGUES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
        </div>

        {/* Contexte métier */}
        <div>
          <label className="block text-xs font-semibold text-gray-500 mb-1">{t('traduction.context')}</label>
          <select value={contexte} onChange={e => setContexte(e.target.value)}
            className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white">
            {CONTEXTES.map(c => <option key={c.code} value={c.code}>{t(c.labelKey)}</option>)}
          </select>
        </div>

        {/* Input selon mode */}
        {mode === 'texte' ? (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">{t('traduction.textToTranslate')}</label>
            <textarea value={contenu} onChange={e => setContenu(e.target.value)} rows={7}
              placeholder={t('traduction.textPlaceholder')}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
            <p className="text-xs text-gray-400 mt-1">{t('traduction.wordsCount', { n: contenu.split(/\s+/).filter(Boolean).length })}</p>
          </div>
        ) : (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">{t('traduction.fileToTranslate')}</label>
            <div
              className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center cursor-pointer hover:border-orange-400 transition-colors"
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={28} className="mx-auto text-gray-400 mb-2" />
              <p className="text-sm text-gray-500">{fichierNom || t('traduction.clickToSelect')}</p>
              <p className="text-xs text-gray-400 mt-1">{t('traduction.fileAccept')}</p>
              <input ref={fileRef} type="file" className="hidden"
                accept=".pdf,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp"
                onChange={e => setFichierNom(e.target.files?.[0]?.name || '')} />
            </div>
          </div>
        )}

        <button
          onClick={mode === 'texte' ? traduireTexte : traduireFichier}
          disabled={loading}
          className="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Languages size={18} />}
          {loading ? t('traduction.translating') : t('traduction.translate')}
        </button>
      </div>

      {/* Résultat */}
      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-bold text-gray-900">{t('traduction.result')}</h2>
              <p className="text-xs text-gray-400">{t('traduction.wordsCountStat', { src: resultat.nb_mots_source, tgt: resultat.nb_mots_cible })}</p>
            </div>
            {resultat.fichier_id && (
              <button onClick={() => telecharger(resultat.fichier_id!)}
                className="flex items-center gap-1.5 bg-orange-500 text-white text-xs font-medium px-3 py-2 rounded-xl hover:bg-orange-600 transition-colors">
                <Download size={14} /> {t('traduction.downloadDocx')}
              </button>
            )}
          </div>
          <div className="bg-gray-50 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <FileText size={14} className="text-orange-500" />
              <span className="text-xs font-semibold text-gray-500 uppercase">{t('traduction.translatedText')}</span>
            </div>
            <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{resultat.texte_traduit}</p>
          </div>
        </div>
      )}
    </div>
  )
}
