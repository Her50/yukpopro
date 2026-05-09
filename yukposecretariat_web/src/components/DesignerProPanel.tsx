import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Loader2, Wand2, Upload, Trash2, Image as ImageIcon, Download, MessageSquare, Sparkles } from 'lucide-react'
import toast from 'react-hot-toast'
import { infographieProAPI } from '../api/client'
import { CountryPicker } from './CountryPicker'
import { LanguagePicker } from './LanguagePicker'
import { useAuth } from '../context/AuthContext'

type Portee = 'session' | 'compte'

interface Media {
  media_id: string
  categorie: string
  label: string
  largeur_px: number
  hauteur_px: number
  couleur_dominante_hex?: string
  portee: Portee
  mime: string
}

interface Projet {
  cle: string
  label: string
  description: string
  pages: number
  width_mm: number
  height_mm: number
  prix_fcfa: number
}

interface ResultatPro {
  projet?: { cle_projet: string; titre: string; nombre_pages: number; palette: string }
  pdf_id?: string
  pdf_base64?: string
  pdf_cmyk_base64?: string
  pages_png_base64?: string[]
  projet_json_id?: string
  cle_projet_detectee?: string
}

const CAT_SESSION = ['photo', 'illustration', 'scan', 'qr', 'icone']
const CAT_COMPTE = ['logo', 'banniere', 'signature', 'cachet', 'filigrane', 'tampon']
const CAT_LABEL_KEYS: Record<string, string> = {
  photo: 'designerPro.catPhoto',
  illustration: 'designerPro.catIllustration',
  scan: 'designerPro.catScan',
  qr: 'designerPro.catQr',
  icone: 'designerPro.catIcone',
  logo: 'designerPro.catLogo',
  banniere: 'designerPro.catBanniere',
  signature: 'designerPro.catSignature',
  cachet: 'designerPro.catCachet',
  filigrane: 'designerPro.catFiligrane',
  tampon: 'designerPro.catTampon',
}

function b64download(b64: string, filename: string, mime: string) {
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const url = URL.createObjectURL(new Blob([arr], { type: mime }))
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export default function DesignerProPanel() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const sessionId = user ? `chat_${user.user_id}` : 'anon'
  const [brief, setBrief] = useState('')
  const [pays, setPays] = useState('CM')
  const [langue, setLangue] = useState('fr')
  const [cleHint, setCleHint] = useState<string>('')
  const [autoMode, setAutoMode] = useState(true)
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<ResultatPro | null>(null)
  const [pageActive, setPageActive] = useState(0)
  const [modifInstr, setModifInstr] = useState('')
  const [loadingModif, setLoadingModif] = useState(false)
  const [modeVisuel, setModeVisuel] = useState<'sans' | 'standard' | 'premium'>('sans')

  // Directives visuelles (sliders Phase 3)
  const [creativite, setCreativite] = useState(50)
  const [densite, setDensite] = useState(50)
  const [importanceImg, setImportanceImg] = useState(50)
  const [elegance, setElegance] = useState(50)
  const directives = {
    creativite, densite_texte: densite,
    importance_images: importanceImg, elegance,
  }

  // Médiathèque
  const [porteeUpload, setPorteeUpload] = useState<Portee>('session')
  const [categorieUpload, setCategorieUpload] = useState<string>('photo')
  const [labelUpload, setLabelUpload] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [refsSelectionnees, setRefsSelectionnees] = useState<string[]>([])

  const { data: projetsData } = useQuery({
    queryKey: ['designer-pro-projets'],
    queryFn: () => infographieProAPI.projets().then(r => r.data),
  })
  const projets: Projet[] = projetsData?.projets ?? []

  const { data: mediasSession, refetch: refetchSession } = useQuery({
    queryKey: ['designer-pro-medias', 'session', sessionId],
    queryFn: () => infographieProAPI.listerMedias({ portee: 'session', session_id: sessionId }).then(r => r.data),
    enabled: !!user,
  })
  const { data: mediasCompte, refetch: refetchCompte } = useQuery({
    queryKey: ['designer-pro-medias', 'compte'],
    queryFn: () => infographieProAPI.listerMedias({ portee: 'compte' }).then(r => r.data),
    enabled: !!user,
  })

  const tousMedias: Media[] = [
    ...((mediasSession?.medias as Media[]) || []),
    ...((mediasCompte?.medias as Media[]) || []),
  ]

  useEffect(() => {
    setCategorieUpload(porteeUpload === 'session' ? 'photo' : 'logo')
  }, [porteeUpload])

  const uploader = async () => {
    const f = fileRef.current?.files?.[0]
    if (!f) { fileRef.current?.click(); return }
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('fichier', f)
      fd.append('portee', porteeUpload)
      fd.append('categorie', categorieUpload)
      if (porteeUpload === 'session') fd.append('session_id', sessionId)
      if (labelUpload) fd.append('label', labelUpload)
      await infographieProAPI.uploadMedia(fd)
      toast.success(t('designerPro.mediaAdded'))
      setLabelUpload('')
      if (fileRef.current) fileRef.current.value = ''
      porteeUpload === 'session' ? refetchSession() : refetchCompte()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || t('designerPro.uploadFailed'))
    } finally {
      setUploading(false)
    }
  }

  const supprimer = async (m: Media) => {
    if (!confirm(t('designerPro.confirmDelete', { label: m.label }))) return
    try {
      await infographieProAPI.supprimerMedia(m.media_id, m.portee, m.portee === 'session' ? sessionId : undefined)
      toast.success(t('designerPro.deleted'))
      m.portee === 'session' ? refetchSession() : refetchCompte()
      setRefsSelectionnees(r => r.filter(ref => ref !== `${m.portee}:${m.media_id}`))
    } catch {
      toast.error(t('designerPro.deleteFailed'))
    }
  }

  const toggleRef = (m: Media) => {
    const ref = `${m.portee}:${m.media_id}`
    setRefsSelectionnees(r => r.includes(ref) ? r.filter(x => x !== ref) : [...r, ref])
  }

  const generer = async () => {
    if (!brief.trim()) { toast.error(t('designerPro.errDescribeProject')); return }
    setLoading(true); setResultat(null); setPageActive(0)
    try {
      const payload = {
        brief, pays, langue,
        medias_refs: refsSelectionnees,
        export_cmyk: true,
        directives_visuelles: directives,
        mode_visuel: modeVisuel,
      }
      const r = autoMode
        ? await infographieProAPI.genererAuto({ ...payload, cle_projet_hint: cleHint || undefined })
        : await infographieProAPI.generer({ ...payload, cle_projet: cleHint || 'livret_deces_4p' })
      setResultat(r.data as ResultatPro)
      toast.success(t('designerPro.okGenerated'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || t('designerPro.errGenerate'))
    } finally {
      setLoading(false)
    }
  }

  const modifier = async () => {
    if (!resultat?.projet_json_id) { toast.error(t('designerPro.errGenerateFirst')); return }
    if (!modifInstr.trim()) { toast.error(t('designerPro.errDescribeChange')); return }
    setLoadingModif(true)
    try {
      const r = await infographieProAPI.modifier({
        projet_id: resultat.projet_json_id,
        instructions: modifInstr,
        medias_refs_supplementaires: refsSelectionnees,
        pays,
        directives_visuelles: directives,
      })
      setResultat(r.data as ResultatPro)
      setModifInstr('')
      setPageActive(0)
      toast.success(t('designerPro.okModified'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || t('designerPro.errModify'))
    } finally {
      setLoadingModif(false)
    }
  }

  const cats = porteeUpload === 'session' ? CAT_SESSION : CAT_COMPTE

  return (
    <div className="space-y-5">
      <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-4">
        <p className="text-sm text-amber-900 font-semibold flex items-center gap-1.5">
          <Sparkles size={14} /> {t('designerPro.heading')}
        </p>
        <p className="text-xs text-amber-800 mt-1">
          {t('designerPro.subheading')}
        </p>
      </div>

      {/* Médiathèque */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-5 space-y-4">
        <p className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
          <ImageIcon size={14} className="text-amber-600" /> {t('designerPro.mediaLibrary')}
        </p>

        <div className="flex gap-1 bg-gray-100 border border-gray-200 p-1 rounded-xl w-fit text-xs">
          {(['session', 'compte'] as Portee[]).map(p => (
            <button key={p} onClick={() => setPorteeUpload(p)}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${porteeUpload === p ? 'bg-white shadow-sm border border-gray-200 text-amber-700' : 'text-gray-600 hover:text-gray-900'}`}>
              {p === 'session' ? t('designerPro.scopeSession') : t('designerPro.scopeAccount')}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">{t('designerPro.category')}</label>
            <select value={categorieUpload} onChange={e => setCategorieUpload(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-3 py-2 text-sm text-gray-800 bg-white">
              {cats.map(c => <option key={c} value={c}>{CAT_LABEL_KEYS[c] ? t(CAT_LABEL_KEYS[c]) : c}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">{t('designerPro.tag')}</label>
            <input value={labelUpload} onChange={e => setLabelUpload(e.target.value)}
              placeholder={t('designerPro.tagPlaceholder')}
              className="w-full border border-gray-300 rounded-xl px-3 py-2 text-sm text-gray-800" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2">
          <input ref={fileRef} type="file" accept="image/*"
            className="flex-1 min-w-0 text-xs text-gray-600 file:mr-2 file:py-1 file:px-2 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-amber-100 file:text-amber-700 hover:file:bg-amber-200 cursor-pointer" />
          <button onClick={uploader} disabled={uploading}
            className="shrink-0 w-full sm:w-auto justify-center bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded-xl flex items-center gap-1.5 shadow-sm transition-colors">
            {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
            {t('common.add')}
          </button>
        </div>

        {tousMedias.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-2">
              {t('designerPro.selectMediasHint', { n: refsSelectionnees.length })}
            </p>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
              {tousMedias.map(m => {
                const ref = `${m.portee}:${m.media_id}`
                const actif = refsSelectionnees.includes(ref)
                return (
                  <div key={ref} className={`relative rounded-xl border-2 overflow-hidden transition-colors ${actif ? 'border-amber-500 ring-2 ring-amber-200' : 'border-gray-200'}`}>
                    <button onClick={() => toggleRef(m)}
                      className="block w-full bg-gray-50 aspect-square flex items-center justify-center text-[10px] text-gray-500 p-1">
                      {m.couleur_dominante_hex && (
                        <span style={{ background: m.couleur_dominante_hex }}
                          className="absolute top-1 left-1 w-3 h-3 rounded-full border border-white shadow" />
                      )}
                      <span className="line-clamp-3 break-all">{m.label || (CAT_LABEL_KEYS[m.categorie] ? t(CAT_LABEL_KEYS[m.categorie]) : m.categorie)}</span>
                    </button>
                    <div className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[9px] px-1 py-0.5 flex items-center justify-between">
                      <span>{CAT_LABEL_KEYS[m.categorie] ? t(CAT_LABEL_KEYS[m.categorie]) : m.categorie}</span>
                      <button onClick={() => supprimer(m)} className="hover:text-red-300">
                        <Trash2 size={10} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* Génération */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-gray-800">{t('designerPro.briefAndOptions')}</p>
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={autoMode} onChange={e => setAutoMode(e.target.checked)} />
            <span className="text-gray-700">{t('designerPro.autoFormat')}</span>
          </label>
        </div>

        {!autoMode && (
          <select value={cleHint} onChange={e => setCleHint(e.target.value)}
            className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm">
            <option value="">{t('designerPro.selectProject')}</option>
            {projets.map(p => (
              <option key={p.cle} value={p.cle}>
                {p.label} — {t('designerPro.pagesCount', { n: p.pages })} ({p.width_mm}×{p.height_mm}mm)
              </option>
            ))}
          </select>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <CountryPicker label={t('common.country')} value={pays} onChange={setPays} />
          <LanguagePicker label={t('language.select')} value={langue} onChange={setLangue} />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-amber-50 rounded-xl p-3 border border-amber-100">
          {([
            ['creativite',    t('designerPro.sliderCreativity'),    creativite,    setCreativite,    t('designerPro.sliderCreativityHint')],
            ['densite',       t('designerPro.sliderDensity'),       densite,       setDensite,       t('designerPro.sliderDensityHint')],
            ['importanceImg', t('designerPro.sliderImageImportance'), importanceImg, setImportanceImg, t('designerPro.sliderImageImportanceHint')],
            ['elegance',      t('designerPro.sliderElegance'),      elegance,      setElegance,      t('designerPro.sliderEleganceHint')],
          ] as const).map(([key, label, val, setter, hint]) => (
            <div key={key as string}>
              <div className="flex justify-between items-center text-xs text-gray-800 font-semibold mb-0.5">
                <span>{label}</span><span className="tabular-nums text-amber-700">{val}</span>
              </div>
              <input type="range" min={0} max={100} value={val}
                onChange={e => (setter as (n: number) => void)(parseInt(e.target.value))}
                className="w-full accent-amber-600" />
              <p className="text-[10px] text-gray-500">{hint}</p>
            </div>
          ))}
        </div>

        <textarea value={brief} onChange={e => setBrief(e.target.value)} rows={6}
          placeholder={t('designerPro.briefPlaceholder')}
          className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 resize-none" />

        {/* Mode visuel IA — Niveau 3 hybride avec génération d'images Flux */}
        <div className="space-y-2">
          <label className="block text-sm font-semibold text-gray-800">
            {t('designerPro.visualMode')}
          </label>
          <div className="grid grid-cols-3 gap-2">
            {([
              { v: 'sans',     emoji: '📋', titleKey: 'designerPro.modeSans',     descKey: 'designerPro.modeSansDesc' },
              { v: 'standard', emoji: '✨', titleKey: 'designerPro.modeStandard', descKey: 'designerPro.modeStandardDesc' },
              { v: 'premium',  emoji: '🎨', titleKey: 'designerPro.modePremium',  descKey: 'designerPro.modePremiumDesc' },
            ] as const).map(opt => (
              <button key={opt.v} type="button" onClick={() => setModeVisuel(opt.v)}
                className={`p-3 rounded-xl border-2 text-left transition-all ${
                  modeVisuel === opt.v
                    ? 'border-amber-500 bg-amber-50 shadow-sm'
                    : 'border-gray-200 hover:border-gray-300 bg-white'
                }`}>
                <div className="text-xl">{opt.emoji}</div>
                <div className="text-xs font-bold text-gray-900 mt-1">{t(opt.titleKey)}</div>
                <div className="text-[10px] text-gray-500 leading-tight mt-0.5">{t(opt.descKey)}</div>
              </button>
            ))}
          </div>
        </div>

        <button onClick={generer} disabled={loading || !brief.trim()}
          className="w-full bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2 shadow-sm">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {loading ? t('designerPro.generating') : t('designerPro.generate')}
        </button>
      </div>

      {/* Aperçu multi-page */}
      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-5 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h2 className="font-bold text-gray-900">{resultat.projet?.titre || t('designerPro.visualGenerated')}</h2>
              <p className="text-xs text-gray-600">
                {resultat.projet?.cle_projet || resultat.cle_projet_detectee} ·
                {' '}{t('designerPro.pagesCount', { n: resultat.projet?.nombre_pages || (resultat.pages_png_base64?.length ?? 0) })} ·
                {' '}{resultat.projet?.palette || t('designerPro.autoPalette')}
              </p>
            </div>
            <div className="flex gap-2">
              {resultat.pdf_base64 && (
                <button onClick={() => b64download(resultat.pdf_base64!, 'designer-pro.pdf', 'application/pdf')}
                  className="flex items-center gap-1 bg-red-500 hover:bg-red-600 text-white text-xs font-medium px-3 py-2 rounded-xl">
                  <Download size={14} /> PDF
                </button>
              )}
              {resultat.pdf_cmyk_base64 && (
                <button onClick={() => b64download(resultat.pdf_cmyk_base64!, 'designer-pro-cmjn.pdf', 'application/pdf')}
                  className="flex items-center gap-1 bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium px-3 py-2 rounded-xl"
                  title={t('infographie.pdfCmykTitle')}>
                  <Download size={14} /> {t('infographie.pdfCmyk')}
                </button>
              )}
            </div>
          </div>

          {resultat.pages_png_base64 && resultat.pages_png_base64.length > 0 && (
            <>
              <div className="grid grid-cols-4 sm:grid-cols-8 gap-1.5">
                {resultat.pages_png_base64.map((png, i) => (
                  <button key={i} onClick={() => setPageActive(i)}
                    className={`relative rounded-lg overflow-hidden border-2 transition-colors ${pageActive === i ? 'border-amber-500 ring-2 ring-amber-200' : 'border-gray-200 hover:border-amber-300'}`}>
                    <img src={`data:image/png;base64,${png}`} alt={t('designerPro.pageAlt', { n: i + 1 })} className="w-full aspect-[3/4] object-cover" />
                    <span className="absolute top-1 left-1 bg-black/60 text-white text-[9px] px-1 rounded">{t('designerPro.pageShort', { n: i + 1 })}</span>
                  </button>
                ))}
              </div>

              <div className="bg-gray-50 rounded-xl p-3 flex justify-center">
                <img src={`data:image/png;base64,${resultat.pages_png_base64[pageActive]}`}
                  alt={t('designerPro.pagePreviewAlt', { n: pageActive + 1 })}
                  className="max-h-[600px] rounded-lg shadow border border-gray-200" />
              </div>
            </>
          )}

          {/* Modification chat-driven */}
          {resultat.projet_json_id && (
            <div className="border-t border-gray-100 pt-4">
              <p className="text-sm font-semibold text-gray-800 mb-2 flex items-center gap-1.5">
                <MessageSquare size={14} className="text-amber-600" /> {t('designerPro.modify')}
              </p>
              <p className="text-xs text-gray-500 mb-2">
                {t('designerPro.modifyExamples')}
              </p>
              <textarea value={modifInstr} onChange={e => setModifInstr(e.target.value)} rows={2}
                placeholder={t('designerPro.modifyPlaceholder')}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 resize-none" />
              <button onClick={modifier} disabled={loadingModif || !modifInstr.trim()}
                className="mt-2 bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white text-sm font-semibold px-4 py-2.5 rounded-xl disabled:opacity-50 flex items-center gap-2 shadow-sm transition-colors">
                {loadingModif ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                {loadingModif ? t('designerPro.applying') : t('designerPro.apply')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
