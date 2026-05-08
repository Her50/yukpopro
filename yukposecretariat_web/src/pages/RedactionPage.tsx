/**
 * Hub Rédaction IA — unifie 4 modes :
 *   ✍️  Texte    : générer un document depuis instructions
 *   📷 Scan     : OCR d'image (document scanné ou manuscrit)
 *   🎙 Audio    : transcription audio + mise en forme
 *   📂 Document : améliorer / reformuler / résumer un texte existant
 *
 * Chaque mode affiche son résultat avec un bouton commun
 * "→ Améliorer dans Rédaction IA" qui passe le texte à l'onglet Texte
 * (champ "reformuler") pour le retravailler / formaliser / changer de
 * type de doc.
 */
import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  FileText, Scan, Mic, FolderOpen, Download, Loader2, Wand2, Upload,
  Square, Circle, Sparkles, ChevronDown, ChevronRight,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { redactionAPI, ocrAPI, audioAPI } from '../api/client'
import { DemoBanner } from '../components/DemoBanner'
import { CountryPicker } from '../components/CountryPicker'
import { useLongOps, useLongOpField } from '../store/longOpsStore'
import { acquireWakeLock, releaseWakeLock, wakeLockSupported } from '../utils/wakeLock'
import { useState } from 'react'

interface TypeDoc { cle: string; label: string; categorie: string; prix_base_fcfa: number; description: string }

type RedactionResult = {
  titre: string; contenu_markdown: string; prix_fcfa: number; nb_mots: number;
  fichier_id?: string; word_base64?: string
}
type OcrResult = {
  texte_structure: string; type_document: string; confiance: number;
  word_base64?: string; titre?: string
}
type AudioResult = {
  transcription_brute: string; document_formate: string; duree_secondes?: number;
  word_base64?: string; type_document: string
}

type TabKey = 'texte' | 'scan' | 'audio' | 'doc'

const TABS: { key: TabKey; labelKey: string; icon: any; color: string; ring: string; descKey: string }[] = [
  { key: 'texte', labelKey: 'redaction.tabText',     icon: FileText,   color: 'text-blue-600',   ring: 'ring-blue-500',
    descKey: 'redaction.tabTextDesc' },
  { key: 'scan',  labelKey: 'redaction.tabScan',     icon: Scan,       color: 'text-green-600',  ring: 'ring-green-500',
    descKey: 'redaction.tabScanDesc' },
  { key: 'audio', labelKey: 'redaction.tabAudio',    icon: Mic,        color: 'text-purple-600', ring: 'ring-purple-500',
    descKey: 'redaction.tabAudioDesc' },
  { key: 'doc',   labelKey: 'redaction.tabDocument', icon: FolderOpen, color: 'text-amber-600',  ring: 'ring-amber-500',
    descKey: 'redaction.tabDocumentDesc' },
]

function formatFCFA(n: number) { return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA' }

function downloadDocx(b64: string, name: string) {
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const blob = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

// ─────────────────────────────────────────────────────────────────────────────

export default function RedactionPage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const initialTab = (params.get('tab') as TabKey) || 'texte'
  const [tab, setTab] = useState<TabKey>(
    (['texte', 'scan', 'audio', 'doc'] as TabKey[]).includes(initialTab) ? initialTab : 'texte'
  )

  useEffect(() => {
    if (params.get('tab') !== tab) {
      const next = new URLSearchParams(params)
      next.set('tab', tab)
      setParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  // Champ reformuler partagé — alimenté par les autres onglets
  const [reformuler, setReformuler] = useLongOpField<string>('redaction', 'reformuler', '')

  const goToTexteAvecReformulation = (texteSource: string, hint?: string) => {
    setReformuler(texteSource + (hint ? `\n\n[${t('redaction.sourceMarker', { source: hint })}]` : ''))
    setTab('texte')
    toast.success(t('redaction.transferredToText'))
    // Scroll en haut pour voir le formulaire
    setTimeout(() => window.scrollTo({ top: 0, behavior: 'smooth' }), 100)
  }

  return (
    <div className="space-y-5">
      <DemoBanner />

      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Sparkles className="text-brand-600" size={24} />
          {t('redaction.title')}
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          {t('redaction.subtitle')}
        </p>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-2 flex gap-1 overflow-x-auto">
        {TABS.map(tb => {
          const Icon = tb.icon
          const active = tab === tb.key
          return (
            <button
              key={tb.key}
              onClick={() => setTab(tb.key)}
              className={`flex-1 min-w-32 px-3 py-3 rounded-xl text-sm font-medium transition-all ${
                active
                  ? `bg-gradient-to-br from-gray-50 to-white shadow-sm ring-1 ${tb.ring} ${tb.color}`
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center justify-center gap-2">
                <Icon size={16} />
                <span>{t(tb.labelKey)}</span>
              </div>
              <p className="text-[10px] text-gray-400 mt-0.5 leading-tight hidden sm:block">{t(tb.descKey)}</p>
            </button>
          )
        })}
      </div>

      {tab === 'texte' && <TabTexte reformuler={reformuler} setReformuler={setReformuler} />}
      {tab === 'scan'  && <TabScan onAmeliorer={(txt) => goToTexteAvecReformulation(txt, t('redaction.sourceScan'))} />}
      {tab === 'audio' && <TabAudio onAmeliorer={(txt) => goToTexteAvecReformulation(txt, t('redaction.sourceAudio'))} />}
      {tab === 'doc'   && <TabDocExistant onAmeliorer={(txt) => goToTexteAvecReformulation(txt, t('redaction.sourceDoc'))} />}
    </div>
  )
}

// ─── Onglet Texte ───────────────────────────────────────────────────────────

function TabTexte({ reformuler, setReformuler }: { reformuler: string; setReformuler: (v: string) => void }) {
  const { t } = useTranslation()
  const [typeDoc, setTypeDoc] = useLongOpField<string>('redaction', 'typeDoc', '')
  const [pays, setPays] = useLongOpField<string>('redaction', 'pays', 'CM')
  const [informations, setInformations] = useLongOpField<string>('redaction', 'informations', '')
  const [mode, setMode] = useLongOpField<'court' | 'standard' | 'long'>('redaction', 'mode', 'standard')
  const loading = useLongOps((s) => s.loading.redaction)
  const resultat = useLongOps((s) => s.resultats.redaction) as RedactionResult | null
  const runOp = useLongOps((s) => s.run)

  const { data: typesData } = useQuery({
    queryKey: ['redaction-types'],
    queryFn: async (): Promise<{ types?: TypeDoc[]; categories?: Record<string, string> }> => {
      const r = await redactionAPI.types()
      return r.data as { types?: TypeDoc[]; categories?: Record<string, string> }
    },
  })
  const types: TypeDoc[] = typesData?.types ?? []
  const categories = [...new Set(types.map(t => t.categorie))]

  const infosParsed = () => {
    if (!informations.trim()) return {}
    try { return JSON.parse(informations) } catch { return { description: informations } }
  }

  const generer = async () => {
    if (!typeDoc) { toast.error(t('redaction.errType')); return }
    try {
      await runOp<RedactionResult>('redaction', async () => {
        const r = await redactionAPI.generer({
          type_doc: typeDoc,
          informations: infosParsed(),
          pays,
          reformuler_texte: reformuler || undefined,
          mode,
        })
        return r.data as RedactionResult
      })
      toast.success(t('redaction.okGen'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || t('redaction.errGen'))
    }
  }

  const typeChoisi = types.find(t => t.cle === typeDoc)

  return (
    <>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">{t('redaction.selectType')}</label>
          <div className="relative">
            <select
              value={typeDoc}
              onChange={e => setTypeDoc(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white pr-10"
            >
              <option value="">{t('infographie.labelSelect')}</option>
              {categories.map(cat => (
                <optgroup key={cat} label={typesData?.categories?.[cat] ?? cat /* API-provided */}>
                  {types.filter(t => t.categorie === cat).map(t => (
                    <option key={t.cle} value={t.cle}>{t.label} — {formatFCFA(t.prix_base_fcfa)}</option>
                  ))}
                </optgroup>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>
          {typeChoisi && <p className="text-xs text-gray-400 mt-1">{typeChoisi.description}</p>}
        </div>

        <CountryPicker label={t('redaction.countryContext')} value={pays} onChange={setPays} />

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">{t('redaction.infosTitle')}</label>
          <p className="text-xs text-gray-400 mb-2">
            {t('redaction.infosFreeText')}
          </p>
          <textarea
            value={informations}
            onChange={e => setInformations(e.target.value)}
            rows={4}
            placeholder={t('redaction.infosPlaceholderExample')}
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            {t('redaction.textToReformulate')} <span className="text-gray-400 font-normal">{t('redaction.reformulateOptional')}</span>
          </label>
          <textarea
            value={reformuler}
            onChange={e => setReformuler(e.target.value)}
            rows={4}
            placeholder={t('redaction.reformulatePlaceholder')}
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
          {reformuler && (
            <div className="mt-1 flex items-center justify-between text-xs">
              <span className="text-gray-400">{reformuler.length} {t('common.characters')}</span>
              <button onClick={() => setReformuler('')} className="text-red-500 hover:text-red-600">{t('redaction.clear')}</button>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">{t('redaction.depth')}</label>
          <div className="grid grid-cols-3 gap-2">
            {([
              { cle: 'court',    label: t('redaction.depthShort'),    desc: t('redaction.depthShortDesc'),    emoji: '⚡' },
              { cle: 'standard', label: t('redaction.depthStandard'), desc: t('redaction.depthStandardDesc'), emoji: '📄' },
              { cle: 'long',     label: t('redaction.depthLong'),     desc: t('redaction.depthLongDesc'),     emoji: '📚' },
            ] as const).map(m => (
              <button key={m.cle} type="button" onClick={() => setMode(m.cle)}
                className={`p-2.5 rounded-lg border text-left transition-colors ${
                  mode === m.cle
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}>
                <div className="text-sm font-semibold flex items-center gap-1">
                  <span>{m.emoji}</span> {m.label}
                </div>
                <div className="text-[10px] text-gray-400 mt-0.5">{m.desc}</div>
              </button>
            ))}
          </div>
          {mode === 'long' && (
            <p className="text-xs text-blue-600 mt-1">
              {t('redaction.longModeNote')}
            </p>
          )}
        </div>

        <button
          onClick={generer}
          disabled={loading || !typeDoc}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {loading ? t('redaction.generating') : t('redaction.generate')}
        </button>
      </div>

      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mt-5">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div>
              <h2 className="font-bold text-gray-900">{resultat.titre}</h2>
              <p className="text-xs text-gray-400">{t('redaction.wordsAndPrice', { n: resultat.nb_mots, price: formatFCFA(resultat.prix_fcfa) })}</p>
            </div>
            {resultat.word_base64 && (
              <button
                onClick={() => downloadDocx(resultat.word_base64!, `${resultat.titre || 'document'}.docx`)}
                className="flex items-center gap-1.5 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors shrink-0"
              >
                <Download size={16} /> .docx
              </button>
            )}
          </div>
          <div className="prose prose-sm max-w-none text-gray-700 border-t border-gray-100 pt-4">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{resultat.contenu_markdown}</ReactMarkdown>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Onglet Scan ────────────────────────────────────────────────────────────

const FORMATS_VALIDES = ['lettre', 'formulaire', 'recu', 'manuscrit', 'tableau']
const FORMATS_MANUSCRIT = ['lettre', 'rapport', 'liste', 'paragraphe']
const FMT_LABEL_KEYS: Record<string, string> = {
  lettre: 'redaction.fmtLettre',
  formulaire: 'redaction.fmtFormulaire',
  recu: 'redaction.fmtRecu',
  manuscrit: 'redaction.fmtManuscrit',
  tableau: 'redaction.fmtTableau',
  rapport: 'redaction.fmtRapport',
  liste: 'redaction.fmtListe',
  paragraphe: 'redaction.fmtParagraphe',
}

function TabScan({ onAmeliorer }: { onAmeliorer: (texte: string) => void }) {
  const { t } = useTranslation()
  type Mode = 'scanner' | 'manuscrit'
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

  const select = (f: File) => {
    setFichier(f)
    setPreview(URL.createObjectURL(f))
    setResultat(null)
  }

  const scanner = async () => {
    if (!fichier) { toast.error(t('ocr.noFile')); return }
    try {
      await runOp<OcrResult>('ocr', async () => {
        const fd = new FormData()
        fd.append('fichier', fichier)
        if (mode === 'manuscrit') {
          fd.append('formater_en', formaterEn)
          const r2 = await ocrAPI.manuscrit(fd)
          return r2.data as OcrResult
        }
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

  return (
    <>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        <div className="flex gap-2">
          {(['scanner', 'manuscrit'] as Mode[]).map(m => (
            <button key={m} onClick={() => { setMode(m); setResultat(null) }}
              className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                mode === m ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}>
              {m === 'scanner' ? t('ocr.scanModePrint') : t('ocr.scanModeHand')}
            </button>
          ))}
        </div>

        <div onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) select(f) }}
          onDragOver={e => e.preventDefault()}
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center cursor-pointer hover:border-green-400 hover:bg-green-50 transition-colors">
          {preview ? (
            <img src={preview} alt={t('common.preview')} className="max-h-48 mx-auto rounded-lg object-contain" />
          ) : (
            <>
              <Upload size={32} className="mx-auto text-gray-300 mb-2" />
              <p className="text-sm text-gray-500">{t('redaction.scanDropHint')}</p>
              <p className="text-xs text-gray-400 mt-1">{t('redaction.scanDropAccept')}</p>
            </>
          )}
          <input ref={inputRef} type="file" accept="image/*" className="hidden"
            onChange={e => { if (e.target.files?.[0]) select(e.target.files[0]) }} />
        </div>

        {mode === 'scanner' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">{t('ocr.expectedType')}</label>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => setTypeAttendu('')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${!typeAttendu ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600'}`}>{t('ocr.autoDetect')}</button>
              {FORMATS_VALIDES.map(f => (
                <button key={f} onClick={() => setTypeAttendu(f)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize ${typeAttendu === f ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600'}`}>{t(FMT_LABEL_KEYS[f])}</button>
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
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize ${formaterEn === f ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600'}`}>{t(FMT_LABEL_KEYS[f])}</button>
              ))}
            </div>
          </div>
        )}

        <button onClick={scanner} disabled={loading || !fichier}
          className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Scan size={18} />}
          {loading ? t('redaction.scanning') : t('redaction.doScan')}
        </button>
      </div>

      {resultat && (
        <ResultatBlock
          title={resultat.type_document /* API-provided */}
          subtitle={t('ocr.confidence', { pct: Math.round(resultat.confiance * 100) })}
          markdown={resultat.texte_structure}
          wordB64={resultat.word_base64}
          downloadName="document-ocr.docx"
          onAmeliorer={() => onAmeliorer(resultat.texte_structure)}
          color="green"
        />
      )}
    </>
  )
}

// ─── Onglet Audio ───────────────────────────────────────────────────────────

function TabAudio({ onAmeliorer }: { onAmeliorer: (texte: string) => void }) {
  const { t } = useTranslation()
  const [fichier, setFichier] = useLongOpField<File | null>('audio', 'fichier', null)
  const [typeDoc, setTypeDoc] = useLongOpField<string>('audio', 'typeDoc', 'dictee')
  const [pays, setPays] = useLongOpField<string>('audio', 'pays', 'CM')
  const [contexte, setContexte] = useLongOpField<string>('audio', 'contexte', '')
  const loading = useLongOps((s) => s.loading.audio)
  const resultat = useLongOps((s) => s.resultats.audio) as AudioResult | null
  const runOp = useLongOps((s) => s.run)
  const [recording, setRecording] = useState(false)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: typesData } = useQuery({
    queryKey: ['audio-types'],
    queryFn: async (): Promise<{ types?: { cle: string; label: string }[] }> => {
      const r = await audioAPI.types()
      return r.data as { types?: { cle: string; label: string }[] }
    },
  })
  const types: { cle: string; label: string }[] = typesData?.types ?? []

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      chunksRef.current = []
      mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setFichier(new File([blob], 'dictee.webm', { type: 'audio/webm' }))
        stream.getTracks().forEach(t => t.stop())
        releaseWakeLock()
      }
      mr.start(); mediaRef.current = mr; setRecording(true)
      // Empêche l'écran de s'éteindre pendant la dictée (Chrome/Edge/Android).
      // Sur iOS Safari : pas supporté → l'utilisateur doit garder l'écran allumé.
      acquireWakeLock()
    } catch { toast.error(t('redaction.micUnavailable')) }
  }
  const stop = () => { mediaRef.current?.stop(); setRecording(false); releaseWakeLock() }

  const transcrire = async () => {
    if (!fichier) { toast.error(t('audio.noAudio')); return }
    try {
      await runOp<AudioResult>('audio', async () => {
        const fd = new FormData()
        fd.append('fichier', fichier)
        fd.append('type_document_cible', typeDoc)
        fd.append('pays', pays)
        if (contexte) fd.append('contexte', contexte)
        const r = await audioAPI.transcrire(fd)
        return r.data as AudioResult
      })
      toast.success(t('audio.okTranscribe'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || t('audio.errTranscribe'))
    }
  }

  return (
    <>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        <div className="flex gap-3">
          <button onClick={recording ? stop : start}
            className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-colors ${
              recording ? 'bg-red-500 hover:bg-red-600 text-white' : 'bg-purple-600 hover:bg-purple-700 text-white'
            }`}>
            {recording ? <><Square size={18} /> {t('redaction.stop')}</> : <><Circle size={18} className="fill-white" /> {t('redaction.dictate')}</>}
          </button>
          <button onClick={() => inputRef.current?.click()}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm bg-gray-100 hover:bg-gray-200 text-gray-700">
            <Upload size={18} /> {t('redaction.import')}
          </button>
          <input ref={inputRef} type="file" accept="audio/*" className="hidden"
            onChange={e => { if (e.target.files?.[0]) setFichier(e.target.files[0]) }} />
        </div>

        {fichier && (
          <div className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2 flex items-center gap-2">
            <Mic size={14} className="text-purple-500" />
            {fichier.name} — {t('common.fileSizeKo', { n: (fichier.size / 1024).toFixed(0) })}
          </div>
        )}
        {recording && (
          <>
            <div className="flex items-center gap-2 text-red-500 text-sm animate-pulse">
              <Circle size={10} className="fill-red-500" /> {t('redaction.recording')}
            </div>
            {!wakeLockSupported() && (
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                ⚠️ {t('redaction.keepScreenOnHint')}
              </div>
            )}
          </>
        )}

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">{t('redaction.docTypeToProduce')}</label>
          <div className="flex flex-wrap gap-2">
            {types.map(t => (
              <button key={t.cle} onClick={() => setTypeDoc(t.cle)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${typeDoc === t.cle ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-600'}`}>{t.label /* API-provided */}</button>
            ))}
          </div>
        </div>

        <CountryPicker label={t('common.country')} value={pays} onChange={setPays} />

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            {t('redaction.context')} <span className="font-normal text-gray-400">{t('redaction.audioContextOptional')}</span>
          </label>
          <textarea value={contexte} onChange={e => setContexte(e.target.value)} rows={2}
            placeholder={t('redaction.audioContextPlaceholder')}
            className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none" />
        </div>

        <button onClick={transcrire} disabled={loading || !fichier}
          className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Mic size={18} />}
          {loading ? t('redaction.transcribingLong') : t('redaction.transcribeAndFormat')}
        </button>
      </div>

      {resultat && (
        <ResultatBlock
          title={resultat.type_document /* API-provided */}
          subtitle={resultat.duree_secondes ? t('audio.durationSec', { n: Math.round(resultat.duree_secondes) }) : ''}
          markdown={resultat.document_formate}
          wordB64={resultat.word_base64}
          downloadName="transcription.docx"
          onAmeliorer={() => onAmeliorer(resultat.document_formate)}
          color="purple"
          extra={(
            <details className="border-t border-gray-100 pt-3 mt-3">
              <summary className="text-xs text-gray-400 cursor-pointer">{t('redaction.rawTranscriptLabel')}</summary>
              <p className="text-xs text-gray-500 mt-2 italic">{resultat.transcription_brute}</p>
            </details>
          )}
        />
      )}
    </>
  )
}

// ─── Onglet Document existant ───────────────────────────────────────────────

function TabDocExistant({ onAmeliorer }: { onAmeliorer: (texte: string) => void }) {
  const { t } = useTranslation()
  const [texte, setTexte] = useLongOpField<string>('docameliore', 'texte', '')
  const [registre, setRegistre] = useLongOpField<string>('docameliore', 'registre', 'professionnel')
  const [pays, setPays] = useLongOpField<string>('docameliore', 'pays', 'CM')
  const loading = useLongOps((s) => s.loading.docameliore)
  const resultat = useLongOps((s) => s.resultats.docameliore) as { texte_reformule?: string; nb_mots?: number; prix_fcfa?: number } | null
  const runOp = useLongOps((s) => s.run)

  const REGISTRES = [
    { cle: 'professionnel', label: t('redaction.regProfessionnel') },
    { cle: 'administratif', label: t('redaction.regAdministratif') },
    { cle: 'commercial',    label: t('redaction.regCommercial') },
    { cle: 'juridique',     label: t('redaction.regJuridique') },
    { cle: 'simplifie',     label: t('redaction.regSimplifie') },
    { cle: 'concis',        label: t('redaction.regConcis') },
  ]

  const reformulerTexte = async () => {
    if (!texte.trim()) { toast.error(t('redaction.errPasteText')); return }
    try {
      await runOp('docameliore', async () => {
        const r = await redactionAPI.reformuler({ texte, registre, pays })
        return r.data
      })
      toast.success(t('redaction.okReformulated'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || t('redaction.errReformulate'))
    }
  }

  return (
    <>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        <p
          className="text-xs text-gray-500 bg-amber-50 border border-amber-200 rounded-lg p-3"
          dangerouslySetInnerHTML={{ __html: t('redaction.docHint') }}
        />

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">{t('redaction.textToImprove')}</label>
          <textarea value={texte} onChange={e => setTexte(e.target.value)} rows={10}
            placeholder={t('redaction.textPlaceholder')}
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 resize-y" />
          {texte && (
            <div className="mt-1 flex items-center justify-between text-xs">
              <span className="text-gray-400">{t('redaction.charsAndWords', { c: texte.length, w: Math.round(texte.split(/\s+/).length) })}</span>
              <button onClick={() => setTexte('')} className="text-red-500 hover:text-red-600">{t('redaction.clear')}</button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">{t('redaction.targetRegister')}</label>
            <div className="flex flex-wrap gap-2">
              {REGISTRES.map(r => (
                <button key={r.cle} onClick={() => setRegistre(r.cle)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium ${registre === r.cle ? 'bg-amber-600 text-white' : 'bg-gray-100 text-gray-600'}`}>{r.label}</button>
              ))}
            </div>
          </div>
          <CountryPicker label={t('common.country')} value={pays} onChange={setPays} />
        </div>

        <div className="flex flex-col sm:flex-row gap-2">
          <button onClick={reformulerTexte} disabled={loading || !texte.trim()}
            className="flex-1 bg-amber-600 hover:bg-amber-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
            {loading ? t('redaction.reformulating') : t('redaction.reformulate')}
          </button>
          <button onClick={() => onAmeliorer(texte)} disabled={!texte.trim()}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
            <ChevronRight size={16} /> {t('redaction.convertToOtherDoc')}
          </button>
        </div>
      </div>

      {resultat?.texte_reformule && (
        <ResultatBlock
          title={t('redaction.reformulatedText')}
          subtitle={resultat.nb_mots ? t('redaction.wordsAndPrice', { n: resultat.nb_mots, price: formatFCFA(resultat.prix_fcfa || 0) }) : ''}
          markdown={resultat.texte_reformule}
          onAmeliorer={() => onAmeliorer(resultat.texte_reformule!)}
          color="amber"
        />
      )}
    </>
  )
}

// ─── Bloc résultat commun ───────────────────────────────────────────────────

function ResultatBlock({
  title, subtitle, markdown, wordB64, downloadName, onAmeliorer, color, extra,
}: {
  title: string; subtitle?: string; markdown: string;
  wordB64?: string; downloadName?: string;
  onAmeliorer: () => void;
  color: 'green' | 'purple' | 'amber';
  extra?: React.ReactNode;
}) {
  const { t } = useTranslation()
  const colorMap = {
    green:  { btn: 'bg-green-600 hover:bg-green-700',   tag: 'bg-green-100 text-green-700' },
    purple: { btn: 'bg-purple-600 hover:bg-purple-700', tag: 'bg-purple-100 text-purple-700' },
    amber:  { btn: 'bg-amber-600 hover:bg-amber-700',   tag: 'bg-amber-100 text-amber-700' },
  }[color]
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mt-5 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <span className={`text-xs px-2 py-1 rounded-lg capitalize ${colorMap.tag}`}>{title}</span>
          {subtitle && <span className="ml-2 text-xs text-gray-400">{subtitle}</span>}
        </div>
        <div className="flex gap-2">
          <button onClick={onAmeliorer}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-3 py-2 rounded-xl">
            <Sparkles size={14} /> {t('redaction.improveInRedaction')}
          </button>
          {wordB64 && downloadName && (
            <button onClick={() => downloadDocx(wordB64, downloadName)}
              className={`flex items-center gap-1.5 text-white text-xs font-medium px-3 py-2 rounded-xl ${colorMap.btn}`}>
              <Download size={14} /> .docx
            </button>
          )}
        </div>
      </div>
      <div className="prose prose-sm max-w-none text-gray-700 border-t border-gray-100 pt-3">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      </div>
      {extra}
    </div>
  )
}
