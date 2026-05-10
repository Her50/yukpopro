import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Loader2, Wand2, Upload, Trash2, Image as ImageIcon,
  Download, MessageSquare, Sparkles, ChevronDown,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { infographieProApi } from '@/api/client'
import { useAuthStore } from '@/store'
import { CountryPicker } from './CountryPicker'
import { LanguagePicker } from './LanguagePicker'

type Portee = 'session' | 'compte'

interface Media {
  media_id: string; categorie: string; label: string
  largeur_px: number; hauteur_px: number
  couleur_dominante_hex?: string; portee: Portee; mime: string
}
interface Projet {
  cle: string; label: string; description: string
  pages: number; width_mm: number; height_mm: number; prix_fcfa: number
}
interface ResultatPro {
  projet?: { cle_projet: string; titre: string; nombre_pages: number; palette: string }
  pdf_id?: string; pdf_base64?: string; pdf_cmyk_base64?: string
  pages_png_base64?: string[]; projet_json_id?: string; cle_projet_detectee?: string
  download_url?: string
}

const CAT_SESSION = ['photo', 'illustration', 'scan', 'qr', 'icone']
const CAT_COMPTE  = ['logo', 'banniere', 'signature', 'cachet', 'filigrane', 'tampon']
const CAT_LABELS: Record<string, string> = {
  photo: 'Photo', illustration: 'Illustration', scan: 'Scan', qr: 'QR code', icone: 'Icône',
  logo: 'Logo', banniere: 'Bannière', signature: 'Signature', cachet: 'Cachet',
  filigrane: 'Filigrane', tampon: 'Tampon',
}

function b64download(b64: string, filename: string, mime: string) {
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const url = URL.createObjectURL(new Blob([arr], { type: mime }))
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

// ─── Styles tokens ─────────────────────────────────────────────────────────────
// card light-mode : fond blanc, bordure nette, ombre légère
const CARD  = 'bg-white rounded-2xl border border-gray-200 shadow-sm p-5 space-y-4'
const LABEL = 'block text-sm font-semibold text-gray-800 mb-1'
const INPUT = 'w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 bg-white'
const BTN_PRIMARY = 'w-full bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2 shadow-sm'
const BTN_SEC     = 'flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl transition-colors'

export default function DesignerProPanel() {
  const { t } = useTranslation()
  const user = useAuthStore(s => s.user)
  const sessionId = user ? `chat_${user.user_id}` : 'anon'

  const [brief, setBrief]             = useState('')
  const [pays, setPays]               = useState('CM')
  const [langue, setLangue]           = useState('fr')
  const [cleHint, setCleHint]         = useState<string>('')
  const [autoMode, setAutoMode]       = useState(true)
  const [loading, setLoading]         = useState(false)
  const [resultat, setResultat]       = useState<ResultatPro | null>(null)
  const [pageActive, setPageActive]   = useState(0)
  const [modifInstr, setModifInstr]   = useState('')
  const [loadingModif, setLoadingModif] = useState(false)
  const [modeVisuel, setModeVisuel]   = useState<'sans' | 'standard' | 'premium' | 'ultra' | 'ultra_plus'>('sans')

  const [creativite, setCreativite]     = useState(50)
  const [densite, setDensite]           = useState(50)
  const [importanceImg, setImportanceImg] = useState(50)
  const [elegance, setElegance]         = useState(50)
  const directives = { creativite, densite_texte: densite, importance_images: importanceImg, elegance }

  // Sprint 1.7 — Auto-orchestrateur LLM
  const [autoPrompt, setAutoPrompt] = useState('')
  const [orchestrating, setOrchestrating] = useState(false)
  const [orchestration, setOrchestration] = useState<any | null>(null)

  const [porteeUpload, setPorteeUpload]     = useState<Portee>('session')
  const [categorieUpload, setCategorieUpload] = useState<string>('photo')
  const [labelUpload, setLabelUpload]       = useState('')
  const fileRef   = useRef<HTMLInputElement>(null)
  const [uploading, setUploading]           = useState(false)
  const [refsSelectionnees, setRefsSelectionnees] = useState<string[]>([])

  const { data: projetsData } = useQuery({
    queryKey: ['designer-pro-projets'],
    queryFn: () => infographieProApi.projets(),
  })
  const projets: Projet[] = projetsData?.projets ?? []

  const { data: mediasSession, refetch: refetchSession } = useQuery({
    queryKey: ['designer-pro-medias', 'session', sessionId],
    queryFn: () => infographieProApi.listerMedias({ portee: 'session', session_id: sessionId }),
    enabled: !!user,
  })
  const { data: mediasCompte, refetch: refetchCompte } = useQuery({
    queryKey: ['designer-pro-medias', 'compte'],
    queryFn: () => infographieProApi.listerMedias({ portee: 'compte' }),
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
      await infographieProApi.uploadMedia(fd)
      toast.success('Média ajouté')
      setLabelUpload('')
      if (fileRef.current) fileRef.current.value = ''
      porteeUpload === 'session' ? refetchSession() : refetchCompte()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || 'Upload échoué')
    } finally { setUploading(false) }
  }

  const supprimer = async (m: Media) => {
    if (!confirm(`Supprimer "${m.label}" ?`)) return
    try {
      await infographieProApi.supprimerMedia(m.media_id, m.portee, m.portee === 'session' ? sessionId : undefined)
      toast.success('Supprimé')
      m.portee === 'session' ? refetchSession() : refetchCompte()
      setRefsSelectionnees(r => r.filter(ref => ref !== `${m.portee}:${m.media_id}`))
    } catch { toast.error('Échec suppression') }
  }

  const toggleRef = (m: Media) => {
    const ref = `${m.portee}:${m.media_id}`
    setRefsSelectionnees(r => r.includes(ref) ? r.filter(x => x !== ref) : [...r, ref])
  }

  const generer = async () => {
    if (!brief.trim()) { toast.error('Décris ton projet'); return }
    setLoading(true); setResultat(null); setPageActive(0)
    try {
      const payload = { brief, pays, langue, medias_refs: refsSelectionnees, export_cmyk: true, directives_visuelles: directives, mode_visuel: modeVisuel }
      const r = autoMode
        ? await infographieProApi.genererAuto({ ...payload, cle_projet_hint: cleHint || undefined })
        : await infographieProApi.generer({ ...payload, cle_projet: cleHint || 'livret_deces_4p' })
      setResultat(r as ResultatPro)
      toast.success('Visuel généré ↓')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || 'Échec génération')
    } finally { setLoading(false) }
  }

  const modifier = async () => {
    if (!resultat?.projet_json_id) { toast.error('Génère d\'abord un visuel'); return }
    if (!modifInstr.trim()) { toast.error('Décris la modification'); return }
    setLoadingModif(true)
    try {
      const r = await infographieProApi.modifier({
        projet_id: resultat.projet_json_id, instructions: modifInstr,
        medias_refs_supplementaires: refsSelectionnees, pays, directives_visuelles: directives,
      })
      setResultat(r as ResultatPro); setModifInstr(''); setPageActive(0)
      toast.success('Modifications appliquées')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || 'Échec modification')
    } finally { setLoadingModif(false) }
  }

  // Sprint 1.7 — Auto-orchestrateur LLM
  const orchestrer = async () => {
    if (!autoPrompt.trim()) { toast.error('Décris ton besoin en quelques mots'); return }
    setOrchestrating(true); setOrchestration(null)
    try {
      const r = await infographieProApi.orchestrer({ prompt: autoPrompt, pays, langue })
      setOrchestration(r)
      if (r?.confiance >= 0.85) {
        toast.success(`Détecté : ${r.label_projet} (${Math.round(r.confiance * 100)}%)`)
      } else {
        toast(`Détection à ${Math.round((r?.confiance || 0) * 100)}% — vérifie / précise`)
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || 'Orchestrateur indisponible')
    } finally { setOrchestrating(false) }
  }

  const appliquerOrchestration = () => {
    if (!orchestration) return
    setBrief(orchestration.brief_enrichi || autoPrompt)
    setCleHint(orchestration.cle_projet || '')
    setAutoMode(false)   // on a la clé exacte → mode manuel pré-rempli
    if (orchestration.mode_visuel_suggere) setModeVisuel(orchestration.mode_visuel_suggere)
    const dv = orchestration.directives_visuelles_pre || {}
    if (typeof dv.creativite === 'number') setCreativite(dv.creativite)
    if (typeof dv.densite_texte === 'number') setDensite(dv.densite_texte)
    if (typeof dv.importance_images === 'number') setImportanceImg(dv.importance_images)
    if (typeof dv.elegance === 'number') setElegance(dv.elegance)
    toast.success('Formulaire pré-rempli — vérifie et lance la génération ↓')
    setTimeout(() => {
      const el = document.querySelector('textarea')
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 200)
  }

  const cats = porteeUpload === 'session' ? CAT_SESSION : CAT_COMPTE

  return (
    <div className="space-y-4">

      {/* ── Bannière intro ─────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50 px-5 py-4">
        <p className="text-sm font-bold text-amber-900 flex items-center gap-2">
          <Sparkles size={15} className="text-amber-600" />
          {t('designerPro.heading', 'Designer Pro — visuels multi-page')}
        </p>
        <p className="mt-1 text-xs leading-relaxed text-amber-800">
          {t('designerPro.subheading', "Faire-part, brochures, menus, livres photo, programmes… L'IA choisit la mise en page, intègre tes médias et applique tes modifications en langage naturel.")}
        </p>
      </div>

      {/* ── Sprint 1.7 — Auto-orchestrateur LLM (hero) ───────────────────── */}
      <div className="rounded-2xl border-2 border-violet-300 bg-gradient-to-br from-violet-50 via-fuchsia-50 to-pink-50 p-5 space-y-3">
        <div className="flex items-start gap-2">
          <Wand2 size={18} className="text-violet-600 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-bold text-violet-900">
              {t('designerPro.autoTitle', 'Décris ton besoin — l\'IA s\'occupe du reste')}
            </p>
            <p className="text-[11px] text-violet-700 leading-relaxed mt-0.5">
              {t('designerPro.autoSub', "Pas besoin de parcourir 30 templates : Yukpo détecte le bon format, suggère le mode visuel, identifie les manques et pré-remplit le formulaire.")}
            </p>
          </div>
        </div>
        <textarea
          value={autoPrompt}
          onChange={e => setAutoPrompt(e.target.value)}
          rows={3}
          placeholder={t('designerPro.autoPlaceholder',
            "Ex : Je veux un flyer A5 pour annoncer la rentrée scolaire de mon école avec les photos des classes ; ou : Faire-part de décès de mon père M. Jean MBARGA, livret 8 pages avec les familles, programme et plan d'accès.")}
          className="w-full rounded-xl border border-violet-300 bg-white/80 px-3 py-2.5 text-sm text-violet-950 placeholder-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400 resize-none leading-relaxed"
        />
        <button onClick={orchestrer} disabled={orchestrating || !autoPrompt.trim()}
          className="w-full bg-violet-600 hover:bg-violet-700 active:bg-violet-800 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl transition-colors flex items-center justify-center gap-2 shadow-sm text-sm">
          {orchestrating ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
          {orchestrating
            ? t('designerPro.autoLoading', 'Analyse en cours…')
            : t('designerPro.autoCta', 'Détecter automatiquement')}
        </button>

        {orchestration && (
          <div className="rounded-xl bg-white border border-violet-200 p-3 space-y-2">
            <div className="flex items-start justify-between gap-2 flex-wrap">
              <div>
                <p className="text-xs text-violet-600 font-semibold">
                  {orchestration.type_projet === 'mono' ? 'Visuel mono-page' : 'Projet multi-page'}
                </p>
                <p className="text-sm font-bold text-gray-900">{orchestration.label_projet}</p>
                <p className="text-[11px] text-gray-500">{orchestration.description_projet}</p>
              </div>
              <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
                orchestration.confiance >= 0.85
                  ? 'bg-green-100 text-green-700'
                  : orchestration.confiance >= 0.65
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-red-100 text-red-700'
              }`}>
                {Math.round(orchestration.confiance * 100)}% confiance
              </span>
            </div>
            {Array.isArray(orchestration.alternatives) && orchestration.alternatives.length > 0 && (
              <div className="text-[11px] text-gray-600">
                <span className="font-semibold">Alternatives : </span>
                {orchestration.alternatives.map((a: any) => a.label).join(' · ')}
              </div>
            )}
            {Array.isArray(orchestration.manques) && orchestration.manques.length > 0 && (
              <div className="text-[11px] bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5 text-amber-800">
                <span className="font-semibold">⚠ Manques : </span>{orchestration.manques.join(', ')}
              </div>
            )}
            {Array.isArray(orchestration.questions_clarification) && orchestration.questions_clarification.length > 0 && (
              <div className="text-[11px] bg-blue-50 border border-blue-200 rounded-lg px-2 py-1.5 text-blue-800 space-y-0.5">
                <p className="font-semibold">Pour affiner :</p>
                {orchestration.questions_clarification.map((q: string, i: number) => (
                  <p key={i}>• {q}</p>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-2 text-[11px] text-gray-600">
              <span className="bg-gray-100 rounded px-2 py-0.5">
                Mode visuel suggéré : <b className="text-violet-700">{orchestration.mode_visuel_suggere}</b>
              </span>
              {orchestration.archetype_dominant && (
                <span className="bg-gray-100 rounded px-2 py-0.5">
                  Archétype : <b className="text-violet-700">{orchestration.archetype_dominant}</b>
                </span>
              )}
              <span className="bg-gray-100 rounded px-2 py-0.5">
                ~{orchestration.cout_estime_credits} crédits
              </span>
            </div>
            <button onClick={appliquerOrchestration}
              className="w-full bg-violet-100 hover:bg-violet-200 text-violet-800 font-semibold py-2 rounded-xl transition-colors text-xs mt-2">
              {t('designerPro.autoApply', 'Pré-remplir le formulaire ↓')}
            </button>
          </div>
        )}
      </div>

      {/* ── Médiathèque ────────────────────────────────────────────────────── */}
      <div className={CARD}>
        <p className="text-sm font-bold text-gray-800 flex items-center gap-2">
          <ImageIcon size={15} className="text-amber-600" />
          {t('designerPro.mediaLibrary', 'Médiathèque')}
        </p>

        {/* Portée: session / compte */}
        <div className="inline-flex rounded-xl bg-gray-100 p-1 gap-1 text-xs">
          {(['session', 'compte'] as Portee[]).map(p => (
            <button key={p} onClick={() => setPorteeUpload(p)}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                porteeUpload === p
                  ? 'bg-white shadow text-amber-700 border border-amber-200'
                  : 'text-gray-500 hover:text-gray-700'
              }`}>
              {p === 'session' ? '📁 Session (24h)' : '🏢 Mon compte'}
            </button>
          ))}
        </div>

        {/* Upload row — 2 lignes claires */}
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={LABEL}>Catégorie</label>
              <select value={categorieUpload} onChange={e => setCategorieUpload(e.target.value)} className={INPUT}>
                {cats.map(c => <option key={c} value={c}>{CAT_LABELS[c] || c}</option>)}
              </select>
            </div>
            <div>
              <label className={LABEL}>Étiquette</label>
              <input value={labelUpload} onChange={e => setLabelUpload(e.target.value)}
                placeholder="Ex : logo entreprise"
                className={INPUT} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2">
            <input ref={fileRef} type="file" accept="image/*"
              className="flex-1 min-w-0 text-xs text-gray-600 file:mr-2 file:py-1 file:px-2 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-amber-100 file:text-amber-700 hover:file:bg-amber-200 cursor-pointer" />
            <button onClick={uploader} disabled={uploading}
              className="shrink-0 w-full sm:w-auto justify-center bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded-xl flex items-center gap-1.5 shadow-sm transition-colors">
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              Ajouter
            </button>
          </div>
        </div>

        {/* Grille médias */}
        {tousMedias.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-600 mb-2">
              {refsSelectionnees.length > 0
                ? `${refsSelectionnees.length} média(s) sélectionné(s) — ils seront utilisés dans le visuel`
                : 'Clique pour sélectionner les médias à intégrer'}
            </p>
            <div className="grid grid-cols-4 sm:grid-cols-8 gap-1.5">
              {tousMedias.map(m => {
                const ref = `${m.portee}:${m.media_id}`
                const actif = refsSelectionnees.includes(ref)
                return (
                  <div key={ref} className={`relative rounded-xl border-2 overflow-hidden cursor-pointer transition-all ${
                    actif ? 'border-amber-500 ring-2 ring-amber-200 shadow-md' : 'border-gray-200 hover:border-amber-300'
                  }`}>
                    <button onClick={() => toggleRef(m)}
                      className="w-full bg-gray-50 aspect-square flex items-center justify-center p-1">
                      {m.couleur_dominante_hex && (
                        <span style={{ background: m.couleur_dominante_hex }}
                          className="absolute top-1 left-1 w-2.5 h-2.5 rounded-full border border-white shadow-sm" />
                      )}
                      <span className="text-[10px] text-gray-700 line-clamp-3 break-all leading-tight">
                        {m.label || m.categorie}
                      </span>
                    </button>
                    <div className="absolute bottom-0 inset-x-0 bg-black/70 text-white text-[9px] px-1.5 py-0.5 flex items-center justify-between">
                      <span className="truncate">{m.categorie}</span>
                      <button onClick={e => { e.stopPropagation(); supprimer(m) }} className="hover:text-red-300 ml-1 shrink-0">
                        <Trash2 size={9} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* ── Brief & options ────────────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="flex items-center justify-between">
          <p className="text-sm font-bold text-gray-800">Brief & options</p>
          <label className="flex items-center gap-2 cursor-pointer">
            <div className={`relative w-9 h-5 rounded-full transition-colors ${autoMode ? 'bg-amber-600' : 'bg-gray-300'}`}
              onClick={() => setAutoMode(v => !v)}>
              <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${autoMode ? 'left-4' : 'left-0.5'}`} />
            </div>
            <span className="text-xs font-medium text-gray-700">IA choisit le format</span>
          </label>
        </div>

        {!autoMode && (
          <div>
            <label className={LABEL}>Format de projet</label>
            <div className="relative">
              <select value={cleHint} onChange={e => setCleHint(e.target.value)} className={INPUT + ' pr-8 appearance-none'}>
                <option value="">— Choisis un format —</option>
                {projets.map(p => (
                  <option key={p.cle} value={p.cle}>
                    {p.label} — {p.pages}p · {p.width_mm}×{p.height_mm}mm
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-3 text-gray-400 pointer-events-none" />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <CountryPicker label="Pays" value={pays} onChange={setPays} />
          <LanguagePicker label="Langue" value={langue} onChange={setLangue} />
        </div>

        {/* Sliders créativité */}
        <div className="rounded-xl bg-amber-50 border border-amber-100 p-3 space-y-2.5">
          <p className="text-xs font-bold text-amber-900 mb-1">Directives visuelles</p>
          {([
            ['creativite', '🎨 Créativité', creativite, setCreativite, 'sobre ↔ audacieux'],
            ['densite', '📝 Densité texte', densite, setDensite, 'aéré ↔ dense'],
            ['img', '🖼️ Place images', importanceImg, setImportanceImg, 'texte ↔ images'],
            ['elegance', '✨ Élégance', elegance, setElegance, 'fonctionnel ↔ luxe'],
          ] as const).map(([key, label, val, setter, hint]) => (
            <div key={key as string} className="flex items-center gap-3">
              <span className="text-xs text-amber-800 font-medium w-32 shrink-0">{label}</span>
              <input type="range" min={0} max={100} value={val}
                onChange={e => (setter as (n: number) => void)(parseInt(e.target.value))}
                className="flex-1 accent-amber-600 h-1.5" />
              <span className="text-xs font-bold tabular-nums text-amber-700 w-8 text-right">{val}</span>
              <span className="text-[10px] text-gray-500 w-28 shrink-0">{hint}</span>
            </div>
          ))}
        </div>

        <div>
          <label className={LABEL}>Brief du projet</label>
          <textarea value={brief} onChange={e => setBrief(e.target.value)} rows={6}
            placeholder="Ex : Faire-part de décès en livret 8 pages pour M. Jean MBARGA, décédé le 5 mars 2026 à Yaoundé. Famille MBARGA-NGONO. Obsèques le 12 mars à 10h à la cathédrale, inhumation à Mbalmayo…"
            className={INPUT + ' resize-none leading-relaxed'} />
        </div>

        <div>
          <label className={LABEL}>{t('designerPro.visualMode', 'Mode visuel IA')}</label>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-1">
            {([
              { v: 'sans',       emoji: '📋', titleKey: 'designerPro.modeSans',     fb: 'Sans IA visuelle',  descKey: 'designerPro.modeSansDesc',     fbDesc: 'Templates seuls' },
              { v: 'standard',   emoji: '✨', titleKey: 'designerPro.modeStandard', fb: 'Standard',          descKey: 'designerPro.modeStandardDesc', fbDesc: 'Flux schnell — rapide' },
              { v: 'premium',    emoji: '🎨', titleKey: 'designerPro.modePremium',  fb: 'Premium',           descKey: 'designerPro.modePremiumDesc',  fbDesc: 'Flux dev + variants + vision' },
              { v: 'ultra',      emoji: '🌟', titleKey: 'designerPro.modeUltra',    fb: 'Ultra',             descKey: 'designerPro.modeUltraDesc',    fbDesc: 'Flux Pro Ultra — niveau Midjourney' },
              { v: 'ultra_plus', emoji: '🚀', titleKey: 'designerPro.modeUltraPlus',fb: 'Ultra+',            descKey: 'designerPro.modeUltraPlusDesc',fbDesc: 'Ensemble 3 modèles IA + pick auto' },
            ] as const).map(opt => (
              <button key={opt.v} type="button" onClick={() => setModeVisuel(opt.v)}
                className={`p-2.5 rounded-lg border-2 text-left transition-all ${
                  modeVisuel === opt.v
                    ? 'border-violet-500 bg-violet-500/10 shadow-sm'
                    : 'border-slate-700 hover:border-slate-600 bg-slate-900/40'
                }`}>
                <div className="text-lg">{opt.emoji}</div>
                <div className="text-xs font-bold text-slate-100 mt-0.5">{t(opt.titleKey, opt.fb)}</div>
                <div className="text-[10px] text-slate-400 leading-tight">{t(opt.descKey, opt.fbDesc)}</div>
              </button>
            ))}
          </div>
        </div>

        <button onClick={generer} disabled={loading || !brief.trim()} className={BTN_PRIMARY}>
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {loading
            ? t('designerPro.generating', 'Génération en cours (1–2 min)…')
            : t('designerPro.generate', 'Générer le visuel')}
        </button>
      </div>

      {/* ── Résultat multi-page ────────────────────────────────────────────── */}
      {resultat && (
        <div className={CARD}>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h3 className="text-base font-bold text-gray-900">{resultat.projet?.titre || 'Visuel généré'}</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                <span className="inline-block bg-gray-100 text-gray-600 rounded px-1.5 py-0.5 font-mono text-[10px] mr-1">
                  {resultat.projet?.cle_projet || resultat.cle_projet_detectee}
                </span>
                {resultat.projet?.nombre_pages || resultat.pages_png_base64?.length || 0} page(s) ·
                {' '}palette {resultat.projet?.palette || 'auto'}
              </p>
            </div>
            <div className="flex gap-2 flex-wrap">
              {resultat.pdf_base64 && (
                <button onClick={() => b64download(resultat.pdf_base64!, 'designer-pro.pdf', 'application/pdf')}
                  className={BTN_SEC + ' bg-red-600 hover:bg-red-700 text-white shadow-sm'}>
                  <Download size={13} /> PDF RVB
                </button>
              )}
              {resultat.pdf_cmyk_base64 && (
                <button onClick={() => b64download(resultat.pdf_cmyk_base64!, 'designer-pro-cmjn.pdf', 'application/pdf')}
                  className={BTN_SEC + ' bg-slate-700 hover:bg-slate-800 text-white shadow-sm'}
                  title="CMJN — fichier pour imprimerie professionnelle">
                  <Download size={13} /> PDF CMJN
                </button>
              )}
              {resultat.download_url && (
                <a href={resultat.download_url} target="_blank" rel="noreferrer"
                  className={BTN_SEC + ' bg-slate-800 hover:bg-slate-700 text-slate-100 shadow-sm'}
                  title="Lien permanent — fichier conservé dans Mes Documents">
                  🔗 Lien permanent
                </a>
              )}
            </div>
          </div>

          {resultat.download_url && (
            <p className="text-xs text-slate-400 bg-slate-900/50 border border-slate-700 rounded-lg px-3 py-2">
              📁 Sauvegardé dans <strong>Mes Documents</strong> — accessible depuis le menu pour téléchargement ultérieur.
            </p>
          )}

          {resultat.pages_png_base64 && resultat.pages_png_base64.length > 0 && (
            <>
              {/* Miniatures */}
              <div className="flex gap-1.5 overflow-x-auto pb-1">
                {resultat.pages_png_base64.map((png, i) => (
                  <button key={i} onClick={() => setPageActive(i)}
                    className={`relative shrink-0 rounded-lg overflow-hidden border-2 transition-all ${
                      pageActive === i
                        ? 'border-amber-500 ring-2 ring-amber-200 shadow-md'
                        : 'border-gray-200 hover:border-amber-300 opacity-70 hover:opacity-100'
                    }`}
                    style={{ width: 56 }}>
                    <img src={`data:image/png;base64,${png}`} alt={`p.${i + 1}`} className="w-full aspect-[3/4] object-cover" />
                    <span className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[8px] text-center py-0.5">
                      p.{i + 1}
                    </span>
                  </button>
                ))}
              </div>

              {/* Grande page active */}
              <div className="bg-gray-100 rounded-xl flex justify-center p-4 border border-gray-200">
                <img src={`data:image/png;base64,${resultat.pages_png_base64[pageActive]}`}
                  alt={`Page ${pageActive + 1}`}
                  className="max-h-[65vh] rounded-lg shadow-lg border border-gray-200 object-contain" />
              </div>
            </>
          )}

          {/* Modification langage naturel */}
          {resultat.projet_json_id && (
            <div className="border-t border-gray-200 pt-4 space-y-3">
              <p className="text-sm font-bold text-gray-800 flex items-center gap-2">
                <MessageSquare size={14} className="text-amber-600" />
                {t('designerPro.modify', 'Modifier en langage naturel')}
              </p>
              <p className="text-xs text-gray-500">
                Ex : "remplace la photo p.1", "change la couleur principale en vert forêt", "ajoute un témoignage p.5"
              </p>
              <textarea value={modifInstr} onChange={e => setModifInstr(e.target.value)} rows={2}
                placeholder="Décris les changements à appliquer…"
                className={INPUT + ' resize-none'} />
              <button onClick={modifier} disabled={loadingModif || !modifInstr.trim()}
                className="bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-sm font-bold px-5 py-2.5 rounded-xl flex items-center gap-2 shadow-sm transition-colors">
                {loadingModif ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                {loadingModif ? 'Application…' : t('designerPro.apply', 'Appliquer les modifications')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
