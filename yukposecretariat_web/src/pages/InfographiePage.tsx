import { useRef, useState } from 'react'
import { Image, Wand2, Loader2, Download, ChevronDown, Upload, Ruler, Sparkles, Edit3 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { infographieAPI } from '../api/client'
import toast from 'react-hot-toast'
import { DemoBanner } from '../components/DemoBanner'
import { CountryPicker } from '../components/CountryPicker'
import DesignerProPanel from '../components/DesignerProPanel'
import { useLongOps, useLongOpField } from '../store/longOpsStore'

const CAT_LABELS: Record<string, string> = {
  print: '🖨️ Impression standard',
  evenement: '🎉 Événementiel',
  corporate: '🏢 Corporate',
  grand_format: '📐 Grand format',
  social_media: '📱 Réseaux sociaux',
  commercial: '🛍️ Commercial',
  officiel: '📜 Officiel / Diplômes',
  custom: '✏️ Format personnalisé',
}

interface Gabarit {
  cle: string; label: string; width_mm: number; height_mm: number;
  categorie: string; prix_fcfa: number; description: string
}

type Mode = 'brief' | 'modele' | 'custom' | 'pro'

function formatCredits(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' crédits'
}

function b64download(b64: string, filename: string, mimeType: string) {
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const url = URL.createObjectURL(new Blob([arr], { type: mimeType }))
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

type InfographieResult = {
  fichier_id?: string;
  pdf_base64?: string; png_base64?: string;
  pdf_cmyk_base64?: string; png_preview_base64?: string; svg_base64?: string;
  titre?: string;
  palette?: string; prix_fcfa?: number; analyse_modele?: string
  dimensions_mm?: { width: number; height: number };
  justification_direction?: string;
}

type Variante = {
  index?: number;
  fichier_id?: string;
  pdf_base64?: string; png_base64?: string;
  png_preview_base64?: string;
  titre?: string; palette?: string;
  justification_direction?: string;
  direction?: string;
}

export default function InfographiePage() {
  const { t } = useTranslation()
  const [mode, setMode] = useLongOpField<Mode>('infographie', 'mode', 'brief')
  const [gabarit, setGabarit] = useLongOpField<string>('infographie', 'gabarit', '')
  const [brief, setBrief] = useLongOpField<string>('infographie', 'brief', '')
  const [pays, setPays] = useLongOpField<string>('infographie', 'pays', 'CM')
  const loading = useLongOps((s) => s.loading.infographie)
  const resultat = useLongOps((s) => s.resultats.infographie) as InfographieResult | null
  const setResultat = (r: InfographieResult | null) => useLongOps.getState().setResultat('infographie', r)
  const runOp = useLongOps((s) => s.run)

  // Mode modèle image
  const fileRef = useRef<HTMLInputElement>(null)
  const [modeleNom, setModeleNom] = useLongOpField<string>('infographie', 'modeleNom', '')

  // Mode custom
  const [customW, setCustomW] = useLongOpField<number>('infographie', 'customW', 210)
  const [customH, setCustomH] = useLongOpField<number>('infographie', 'customH', 297)
  const [customBleed, setCustomBleed] = useLongOpField<number>('infographie', 'customBleed', 3)

  // Variantes & retouche
  const [variantes, setVariantes] = useState<Variante[] | null>(null)
  const [varianteActive, setVarianteActive] = useState<number>(0)
  const [retoucheInstr, setRetoucheInstr] = useState<string>('')
  const [loadingVariantes, setLoadingVariantes] = useState(false)
  const [loadingRetouche, setLoadingRetouche] = useState(false)

  const { data: gabaritsData } = useQuery({
    queryKey: ['infographie-gabarits'],
    queryFn: () => infographieAPI.gabarits().then(r => r.data),
  })

  const gabarits: Gabarit[] = gabaritsData?.gabarits ?? []
  const categories = [...new Set(gabarits.map((g: Gabarit) => g.categorie))]
  const gabaritChoisi = gabarits.find(g => g.cle === gabarit)

  const generer = async () => {
    if (mode !== 'custom' && !gabarit) { toast.error(t('infographie.errChooseGabarit')); return }
    if (!brief.trim()) { toast.error(t('infographie.errDescribe')); return }
    setResultat(null)
    setVariantes(null)
    try {
      const data = await runOp<InfographieResult>('infographie', async () => {
        if (mode === 'brief') {
          const r = await infographieAPI.generer({ brief, type_gabarit: gabarit, pays, export_cmyk: true, export_svg: true })
          return r.data as InfographieResult
        }
        if (mode === 'modele') {
          const file = fileRef.current?.files?.[0]
          if (!file) throw new Error(t('infographie.errSelectImage'))
          const fd = new FormData()
          fd.append('modele', file)
          fd.append('brief', brief)
          fd.append('type_gabarit', gabarit)
          fd.append('pays', pays)
          const r = await infographieAPI.genererDepuisModele(fd)
          return r.data as InfographieResult
        }
        const r = await infographieAPI.genererCustom({ width_mm: customW, height_mm: customH, bleed_mm: customBleed, brief, pays, export_cmyk: true, export_svg: true })
        return r.data as InfographieResult
      })
      if (data?.analyse_modele) toast.success(t('infographie.okStyleAnalyzed'))
      else toast.success(t('infographie.okGenerated'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || t('infographie.errGen'))
    }
  }

  const telecharger = (kind: 'pdf' | 'png' | 'pdf_cmyk' | 'png_hd' | 'svg') => {
    if (!resultat) return
    const label = gabarit || 'custom'
    let b64: string | undefined; let ext = 'pdf'; let mime = 'application/pdf'
    if (kind === 'pdf') { b64 = resultat.pdf_base64; ext = 'pdf'; mime = 'application/pdf' }
    else if (kind === 'pdf_cmyk') { b64 = resultat.pdf_cmyk_base64; ext = 'cmjn.pdf'; mime = 'application/pdf' }
    else if (kind === 'png') { b64 = resultat.png_base64; ext = 'png'; mime = 'image/png' }
    else if (kind === 'png_hd') { b64 = resultat.png_preview_base64 || resultat.png_base64; ext = 'hd.png'; mime = 'image/png' }
    else if (kind === 'svg') { b64 = resultat.svg_base64; ext = 'svg'; mime = 'image/svg+xml' }
    if (!b64) { toast.error(t('infographie.errFormat')); return }
    b64download(b64, `infographie-${label}.${ext}`, mime)
  }

  const genererVariantes = async () => {
    if (!gabarit) { toast.error(t('infographie.errChooseGabarit')); return }
    if (!brief.trim()) { toast.error(t('infographie.errDescribe')); return }
    setLoadingVariantes(true)
    setVariantes(null)
    try {
      const r = await infographieAPI.genererVariantes({ brief, type_gabarit: gabarit, pays, nombre: 4 })
      const list = (r.data?.variantes ?? r.data?.results ?? []) as Variante[]
      if (!list.length) throw new Error(t('infographie.variantsErr'))
      setVariantes(list)
      setVarianteActive(0)
      const first = list[0]
      if (first) setResultat(first as InfographieResult)
      toast.success(`${list.length} ${t('infographie.variantsOk')}`)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || t('infographie.variantsErrLabel'))
    } finally {
      setLoadingVariantes(false)
    }
  }

  const choisirVariante = (idx: number) => {
    if (!variantes || !variantes[idx]) return
    setVarianteActive(idx)
    setResultat(variantes[idx] as InfographieResult)
  }

  const retoucher = async () => {
    if (!resultat?.fichier_id) { toast.error(t('infographie.retouchErrEmpty')); return }
    if (!retoucheInstr.trim()) { toast.error(t('infographie.retouchErrEmptyInstr')); return }
    setLoadingRetouche(true)
    try {
      const r = await infographieAPI.modifier({ fichier_id: resultat.fichier_id, instructions: retoucheInstr, pays })
      setResultat(r.data as InfographieResult)
      setRetoucheInstr('')
      toast.success(t('infographie.retouchOk'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || t('infographie.retouchErr'))
    } finally {
      setLoadingRetouche(false)
    }
  }

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Image className="text-orange-500" size={24} />
          {t('infographie.title')}
        </h1>
        <p className="text-gray-500 text-sm mt-1">{t('infographie.subtitle')}</p>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit text-sm flex-wrap">
        {([
          { key: 'brief', label: t('infographie.modeBrief') },
          { key: 'modele', label: t('infographie.modeModele') },
          { key: 'custom', label: t('infographie.modeCustom') },
          { key: 'pro', label: '✨ Multi-page Yukpo' },
        ] as { key: Mode; label: string }[]).map(m => (
          <button key={m.key} onClick={() => { setMode(m.key); setResultat(null) }}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${mode === m.key ? 'bg-white shadow text-orange-600' : 'text-gray-800 hover:text-gray-900'}`}>
            {m.label}
          </button>
        ))}
      </div>

      {mode === 'pro' && <DesignerProPanel />}

      {mode !== 'pro' && (
      <>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        {/* Gabarit (modes brief et modele) */}
        {mode !== 'custom' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">{t('infographie.labelGabarit')}</label>
            <div className="relative">
              <select value={gabarit} onChange={e => setGabarit(e.target.value)}
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm appearance-none bg-white pr-10 focus:outline-none focus:ring-2 focus:ring-orange-400">
                <option value="">{t('infographie.labelSelect')}</option>
                {categories.map(cat => (
                  <optgroup key={cat} label={CAT_LABELS[cat] || cat}>
                    {gabarits.filter(g => g.categorie === cat).map(g => (
                      <option key={g.cle} value={g.cle}>
                        {g.label} ({g.width_mm}×{g.height_mm}mm) — {formatCredits(g.prix_fcfa)}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
            {gabaritChoisi && (
              <p className="text-xs text-gray-400 mt-1">{gabaritChoisi.description}</p>
            )}
          </div>
        )}

        {/* Dimensions custom */}
        {mode === 'custom' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
              <Ruler size={16} className="text-orange-500" /> {t('infographie.labelDimensions')}
            </label>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: t('infographie.labelWidth'), val: customW, set: setCustomW, min: 10, max: 3000 },
                { label: t('infographie.labelHeight'), val: customH, set: setCustomH, min: 10, max: 3000 },
                { label: t('infographie.labelBleed'), val: customBleed, set: setCustomBleed, min: 0, max: 20 },
              ].map(f => (
                <div key={f.label}>
                  <label className="block text-xs text-gray-500 mb-1">{f.label}</label>
                  <input type="number" min={f.min} max={f.max} value={f.val}
                    onChange={e => f.set(Number(e.target.value))}
                    className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-2">{t('infographie.formatInfo', { w: customW, h: customH, b: customBleed })}</p>
          </div>
        )}

        {/* Upload image modèle */}
        {mode === 'modele' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">{t('infographie.labelModele')}</label>
            <div className="border-2 border-dashed border-gray-300 rounded-xl p-5 text-center cursor-pointer hover:border-orange-400 transition-colors"
              onClick={() => fileRef.current?.click()}>
              <Upload size={24} className="mx-auto text-gray-400 mb-2" />
              <p className="text-sm text-gray-500">{modeleNom || t('infographie.modeleHint')}</p>
              <p className="text-xs text-gray-400 mt-1">{t('infographie.modeleAccept')}</p>
              <input ref={fileRef} type="file" className="hidden"
                accept=".png,.jpg,.jpeg,.webp"
                onChange={e => setModeleNom(e.target.files?.[0]?.name || '')} />
            </div>
            <p className="text-xs text-gray-400 mt-1.5">{t('infographie.modeleAnalyse')}</p>
          </div>
        )}

        {/* Pays */}
        <CountryPicker label={t('infographie.labelCountry')} value={pays} onChange={setPays} />

        {/* Brief */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            {mode === 'modele' ? t('infographie.labelBriefModele') : t('infographie.labelBrief')}
          </label>
          <p className="text-xs text-gray-400 mb-2">
            {mode === 'modele' ? t('infographie.briefHintModele') : t('infographie.briefHint')}
          </p>
          <textarea value={brief} onChange={e => setBrief(e.target.value)} rows={5}
            placeholder={mode === 'modele'
              ? "Ex : \"Flyer pour la conférence 'Leadership Africain' à Yaoundé le 15 mars. Logo CMEF. Speakers : Dr Mbarga, Prof Diallo. Inscription gratuite via WhatsApp.\""
              : "Ex : \"Flyer pour l'ouverture de ma boutique 'Mode Chic' à Akwa. 30% de réduction le 1er jour. Tél : 699 00 11 22. Couleurs vertes et dorées.\""}
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
        </div>

        <div className={mode === 'brief' ? 'grid grid-cols-1 sm:grid-cols-2 gap-2' : ''}>
          <button onClick={generer}
            disabled={loading || loadingVariantes || (!gabarit && mode !== 'custom') || !brief.trim()}
            className="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
            {loading ? t('infographie.generating') : t('infographie.oneVisual')}
          </button>
          {mode === 'brief' && (
            <button onClick={genererVariantes}
              disabled={loading || loadingVariantes || !gabarit || !brief.trim()}
              className="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
              {loadingVariantes ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />}
              {loadingVariantes ? t('infographie.generating') : t('infographie.fourVariants')}
            </button>
          )}
        </div>
      </div>

      {/* Galerie variantes */}
      {variantes && variantes.length > 1 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <p className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
            <Sparkles size={14} className="text-pink-500" /> {variantes.length} {t('infographie.variantsTitle')}
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {variantes.map((v, idx) => {
              const preview = v.png_base64 || v.png_preview_base64
              const active = varianteActive === idx
              return (
                <button key={idx} onClick={() => choisirVariante(idx)}
                  className={`relative rounded-xl overflow-hidden border-2 transition-colors ${active ? 'border-pink-500 ring-2 ring-pink-300' : 'border-gray-200 hover:border-pink-300'}`}>
                  {preview ? (
                    <img src={`data:image/png;base64,${preview}`} alt={`Variante ${idx + 1}`} className="w-full h-32 object-cover" />
                  ) : (
                    <div className="w-full h-32 bg-gray-100 flex items-center justify-center text-xs text-gray-400">N°{idx + 1}</div>
                  )}
                  <span className="absolute top-1 left-1 bg-black/60 text-white text-[10px] px-1.5 py-0.5 rounded">N°{idx + 1}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Résultat */}
      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-bold text-gray-900">{resultat.titre || t('infographie.titleGenerated')}</h2>
              {resultat.palette && <span className="text-xs text-gray-400">{t('infographie.labelPalette')} : {resultat.palette}</span>}
              {resultat.dimensions_mm && (
                <span className="text-xs text-gray-400 ml-2">
                  · {resultat.dimensions_mm.width}×{resultat.dimensions_mm.height}mm
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {resultat.pdf_base64 && (
                <button onClick={() => telecharger('pdf')}
                  className="flex items-center gap-1 bg-red-500 text-white text-xs font-medium px-3 py-2 rounded-xl hover:bg-red-600 transition-colors">
                  <Download size={14} /> {t('infographie.pdfRgb')}
                </button>
              )}
              {resultat.pdf_cmyk_base64 && (
                <button onClick={() => telecharger('pdf_cmyk')}
                  className="flex items-center gap-1 bg-amber-600 text-white text-xs font-medium px-3 py-2 rounded-xl hover:bg-amber-700 transition-colors"
                  title={t('infographie.pdfCmykTitle')}>
                  <Download size={14} /> {t('infographie.pdfCmyk')}
                </button>
              )}
              {resultat.svg_base64 && (
                <button onClick={() => telecharger('svg')}
                  className="flex items-center gap-1 bg-emerald-600 text-white text-xs font-medium px-3 py-2 rounded-xl hover:bg-emerald-700 transition-colors"
                  title={t('infographie.svgTitle')}>
                  <Download size={14} /> {t('infographie.svg')}
                </button>
              )}
              {(resultat.png_preview_base64 || resultat.png_base64) && (
                <button onClick={() => telecharger('png_hd')}
                  className="flex items-center gap-1 bg-blue-500 text-white text-xs font-medium px-3 py-2 rounded-xl hover:bg-blue-600 transition-colors">
                  <Download size={14} /> {t('infographie.pngHd')}
                </button>
              )}
            </div>
          </div>

          {/* Analyse modèle si disponible */}
          {resultat.analyse_modele && resultat.analyse_modele !== '{}' && (
            <div className="bg-orange-50 border border-orange-200 rounded-xl p-3">
              <p className="text-xs font-semibold text-orange-700 mb-1">{t('infographie.styleDetected')}</p>
              <pre className="text-xs text-orange-600 whitespace-pre-wrap overflow-hidden line-clamp-4">
                {resultat.analyse_modele}
              </pre>
            </div>
          )}

          {/* Preview PNG */}
          {resultat.png_base64 ? (
            <img src={`data:image/png;base64,${resultat.png_base64}`}
              alt="Aperçu infographie"
              className="w-full rounded-xl border border-gray-200 object-contain max-h-96" />
          ) : (
            <div className="bg-gray-50 rounded-xl p-8 text-center text-gray-400 text-sm">
              {t('infographie.previewUnavailable')}<br />
              {t('infographie.previewDownload')}
            </div>
          )}

          {/* Retouche IA */}
          {resultat.fichier_id && (
            <div className="border-t border-gray-100 pt-4">
              <p className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
                <Edit3 size={14} className="text-orange-500" /> {t('infographie.retouchTitle')}
              </p>
              <textarea value={retoucheInstr} onChange={e => setRetoucheInstr(e.target.value)} rows={2}
                placeholder={t('infographie.retouchPlaceholder')}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
              <button onClick={retoucher} disabled={loadingRetouche || !retoucheInstr.trim()}
                className="mt-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-xl transition-colors disabled:opacity-60 flex items-center gap-2">
                {loadingRetouche ? <Loader2 size={14} className="animate-spin" /> : <Edit3 size={14} />}
                {loadingRetouche ? t('infographie.retouching') : t('infographie.retouchApply')}
              </button>
            </div>
          )}
        </div>
      )}
      </>
      )}
    </div>
  )
}
