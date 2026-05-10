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

const CAT_SESSION = ['photo', 'illustration', 'scan', 'qr', 'icone', 'reference_style']
const CAT_COMPTE  = ['logo', 'banniere', 'signature', 'cachet', 'filigrane', 'tampon', 'reference_style']
const CAT_LABELS: Record<string, string> = {
  photo: 'Photo', illustration: 'Illustration', scan: 'Scan', qr: 'QR code', icone: 'Icône',
  logo: 'Logo', banniere: 'Bannière', signature: 'Signature', cachet: 'Cachet',
  filigrane: 'Filigrane', tampon: 'Tampon', reference_style: '🎨 Référence style',
}

// Sprint UX4 — emoji par mode visuel (cohérent avec selector options avancées)
function modeEmoji(mode: string): string {
  return ({ sans: '📋', standard: '✨', premium: '🎨', ultra: '🌟', ultra_plus: '🚀' } as any)[mode] || '✨'
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
  // Sprint UX4 : default 'auto' = backend résout via orchestrateur
  const [modeVisuel, setModeVisuel]   = useState<'auto' | 'sans' | 'standard' | 'premium' | 'ultra' | 'ultra_plus'>('auto')
  // Charte d'organisation NON-négociable côté backend si configurée — pas de toggle UI

  // Sprint UX4 — Devis automatique (debounced)
  const [devis, setDevis] = useState<any | null>(null)
  const [devisLoading, setDevisLoading] = useState(false)
  const devisTimerRef = useRef<any>(null)

  const [creativite, setCreativite]     = useState(50)
  const [densite, setDensite]           = useState(50)
  const [importanceImg, setImportanceImg] = useState(50)
  const [elegance, setElegance]         = useState(50)
  const directives = { creativite, densite_texte: densite, importance_images: importanceImg, elegance }

  // Sprint 1.7 — Auto-orchestrateur LLM
  const [autoPrompt, setAutoPrompt] = useState('')
  const [orchestrating, setOrchestrating] = useState(false)
  const [orchestration, setOrchestration] = useState<any | null>(null)

  // Sprint UX2 — Frontend épuré : options avancées repliées par défaut
  const [showAdvanced, setShowAdvanced] = useState(false)


  // Sprint L1.4 — Multilingual export
  const [showMultilingual, setShowMultilingual] = useState(false)
  const [multilingualLangues, setMultilingualLangues] = useState<string[]>(['en'])
  const [multilingualLoading, setMultilingualLoading] = useState(false)
  const [multilingualResults, setMultilingualResults] = useState<any | null>(null)

  // Sprint UX3 — Bulk CSV
  const [showBulk, setShowBulk] = useState(false)
  const [bulkAnalysing, setBulkAnalysing] = useState(false)
  const [bulkLaunching, setBulkLaunching] = useState(false)
  const [bulkAnalysis, setBulkAnalysis] = useState<any | null>(null)
  const [bulkAccepter, setBulkAccepter] = useState(false)
  const [bulkResults, setBulkResults] = useState<any | null>(null)
  const bulkFileRef = useRef<HTMLInputElement>(null)

  // Sprint 1.6b — Brand LoRA UI
  const [showLoraPanel, setShowLoraPanel] = useState(false)
  const [showLoraForm, setShowLoraForm] = useState(false)
  const [loraLabel, setLoraLabel] = useState('')
  const [loraTrigger, setLoraTrigger] = useState('')
  const [loraDesc, setLoraDesc] = useState('')
  const [loraAccept, setLoraAccept] = useState(false)
  const [loraTraining, setLoraTraining] = useState(false)
  const [brandLoraId, setBrandLoraId] = useState<string>('')

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

  // Sprint 1.6b — Brand LoRAs de l'organisation
  const { data: brandLoras, refetch: refetchLoras } = useQuery<any[]>({
    queryKey: ['designer-pro-brand-loras'],
    queryFn: () => infographieProApi.brandLoraList(),
    enabled: !!user && showLoraPanel,
    refetchInterval: showLoraPanel ? 15_000 : false,   // poll training status
  })
  const lorasReady = (brandLoras || []).filter(l => l.statut === 'ready')

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
      // Sprint 1.6 — détection auto d'une réf. style parmi les médias sélectionnés
      const refStyle = tousMedias.find(m => m.categorie === 'reference_style'
        && refsSelectionnees.includes(`${m.portee}:${m.media_id}`))
      const payload: any = { brief, pays, langue, medias_refs: refsSelectionnees, export_cmyk: true,
        directives_visuelles: directives, mode_visuel: modeVisuel }
      if (refStyle) {
        payload.reference_style_ref = `${refStyle.portee}:${refStyle.media_id}`
      }
      if (brandLoraId) payload.brand_lora_id = brandLoraId
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
      // Sprint 1.8a — passe les médias déjà uploadés sélectionnés ou tous si rien sélectionné
      const allRefs = tousMedias.map(m => `${m.portee}:${m.media_id}`)
      const refsToAnalyze = refsSelectionnees.length > 0 ? refsSelectionnees : allRefs
      const r = await infographieProApi.orchestrer({
        prompt: autoPrompt, pays, langue,
        medias_refs: refsToAnalyze.length > 0 ? refsToAnalyze : undefined,
      } as any)
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
    // Sprint 1.8a — pré-cocher les médias jugés pertinents par l'IA
    if (Array.isArray(orchestration.medias_refs_actifs) && orchestration.medias_refs_actifs.length > 0) {
      setRefsSelectionnees(orchestration.medias_refs_actifs)
    }
    toast.success('Formulaire pré-rempli — vérifie et lance la génération ↓')
    setTimeout(() => {
      const el = document.querySelector('textarea')
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 200)
  }

  // Sprint UX4 — Fetch devis quand brief assez long (debounced 800ms)
  useEffect(() => {
    if (devisTimerRef.current) clearTimeout(devisTimerRef.current)
    if (!brief || brief.trim().length < 30) { setDevis(null); return }
    devisTimerRef.current = setTimeout(async () => {
      setDevisLoading(true)
      try {
        const r = await infographieProApi.devis({
          brief, pays, langue, medias_refs: refsSelectionnees,
          cle_projet: cleHint || undefined,
        })
        setDevis(r)
      } catch {
        setDevis(null)
      } finally { setDevisLoading(false) }
    }, 800)
    return () => devisTimerRef.current && clearTimeout(devisTimerRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brief, pays, langue, refsSelectionnees, cleHint])

  // Sprint L1.4 — Lance export multilingual
  const lancerMultilingual = async () => {
    if (!resultat?.projet_json_id) return
    if (multilingualLangues.length === 0) { toast.error('Sélectionne au moins 1 langue'); return }
    setMultilingualLoading(true); setMultilingualResults(null)
    try {
      const r = await infographieProApi.multilingual({
        projet_id: resultat.projet_json_id,
        langues_cibles: multilingualLangues,
      })
      setMultilingualResults(r)
      toast.success(`${r.nb_succes}/${r.total_langues} langues OK`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Export multilingue échoué')
    } finally { setMultilingualLoading(false) }
  }

  // Sprint UX3 — Bulk CSV : analyse
  const bulkAnalyser = async () => {
    const f = bulkFileRef.current?.files?.[0]
    if (!f) { toast.error('Sélectionne un fichier CSV ou XLSX'); return }
    setBulkAnalysing(true); setBulkAnalysis(null); setBulkResults(null); setBulkAccepter(false)
    try {
      const fd = new FormData()
      fd.append('fichier', f)
      const r = await infographieProApi.bulkAnalyser(fd)
      setBulkAnalysis(r)
      toast.success(`${r.nb_lignes} ligne(s) analysée(s) — vérifie & lance`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Analyse échouée')
    } finally { setBulkAnalysing(false) }
  }

  const bulkLancer = async () => {
    if (!bulkAnalysis) return
    if (!bulkAccepter) { toast.error('Confirme le coût estimé pour lancer'); return }
    setBulkLaunching(true); setBulkResults(null)
    try {
      const r = await infographieProApi.bulkLancer({
        rows: bulkAnalysis.rows_complete || [],
        template_brief: bulkAnalysis.template_brief,
        mapping: bulkAnalysis.mapping,
        cle_projet: bulkAnalysis.cle_projet_recommande,
        mode_visuel: 'standard',
        pays, langue,
        accepter_cout: true,
      })
      setBulkResults(r)
      toast.success(`Bulk terminé : ${r.nb_done}/${r.total} OK`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Bulk échoué')
    } finally { setBulkLaunching(false) }
  }

  // Sprint 1.6b — Lance training Brand LoRA
  const lancerTrainingLora = async () => {
    if (!loraLabel.trim() || !loraTrigger.trim()) {
      toast.error('Label + trigger word requis'); return
    }
    if (refsSelectionnees.length < 10) {
      toast.error(`Sélectionne au moins 10 images dans la médiathèque (actuel: ${refsSelectionnees.length})`)
      return
    }
    if (!loraAccept) {
      toast.error('Coche la confirmation du coût (200 000 FCFA)')
      return
    }
    setLoraTraining(true)
    try {
      await infographieProApi.brandLoraTrain({
        label: loraLabel, trigger_word: loraTrigger,
        description: loraDesc || undefined,
        images_refs: refsSelectionnees, accepter_cout: true,
      })
      toast.success('Training lancé — suivi statut ci-dessous (15-30 min)')
      setShowLoraForm(false)
      setLoraLabel(''); setLoraTrigger(''); setLoraDesc(''); setLoraAccept(false)
      refetchLoras()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Échec training')
    } finally {
      setLoraTraining(false)
    }
  }

  const supprimerLora = async (loraId: string) => {
    if (!confirm('Désactiver ce Brand LoRA ?')) return
    try {
      await infographieProApi.brandLoraDelete(loraId)
      toast.success('LoRA désactivé')
      if (brandLoraId === loraId) setBrandLoraId('')
      refetchLoras()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Échec suppression')
    }
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
            {Array.isArray(orchestration.recommandation_medias) && orchestration.recommandation_medias.length > 0 && (
              <div className="text-[11px] bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1.5 text-emerald-800 space-y-0.5">
                <p className="font-semibold">📷 Médias recommandés :</p>
                {orchestration.recommandation_medias.slice(0, 6).map((m: any, i: number) => (
                  <p key={i}>• <b>{m.role_suggere}</b> {m.page_cible ? `(p.${m.page_cible})` : ''} — <span className="opacity-80">{m.raison}</span></p>
                ))}
              </div>
            )}
            {Array.isArray(orchestration.medias_manquants) && orchestration.medias_manquants.length > 0 && (
              <div className="text-[11px] bg-orange-50 border border-orange-200 rounded-lg px-2 py-1.5 text-orange-800">
                <span className="font-semibold">📤 À uploader pour optimum : </span>{orchestration.medias_manquants.join(', ')}
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

      {/* ── Sprint 1.6 — Brand LoRA (collapsible) ─────────────────────────── */}
      <div className={CARD}>
        <button onClick={() => setShowLoraPanel(v => !v)} type="button"
          className="w-full flex items-center justify-between text-left">
          <p className="text-sm font-bold text-gray-800 flex items-center gap-2">
            <Sparkles size={15} className="text-fuchsia-600" />
            Brand LoRA — Style de marque entraîné
          </p>
          <ChevronDown size={16} className={`text-gray-400 transition-transform ${showLoraPanel ? 'rotate-180' : ''}`} />
        </button>
        {showLoraPanel && (
          <div className="space-y-3">
            <p className="text-[11px] text-gray-500 leading-relaxed">
              Entraîne un LoRA Flux à partir de 10-30 images de ta marque (logo, photos
              produit, charte). Réutilisable à vie pour générer dans le style exact de
              ton entreprise. <b>Coût : 200 000 FCFA / LoRA (one-shot)</b>.
            </p>

            {/* Liste LoRA existants */}
            {(brandLoras || []).length > 0 && (
              <div className="space-y-1.5">
                {(brandLoras || []).map(l => (
                  <div key={l.lora_id} className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-gray-800 truncate">{l.label}</span>
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                          l.statut === 'ready' ? 'bg-green-100 text-green-700'
                          : l.statut === 'training' ? 'bg-blue-100 text-blue-700 animate-pulse'
                          : l.statut === 'pending' ? 'bg-amber-100 text-amber-700'
                          : 'bg-red-100 text-red-700'
                        }`}>{l.statut}</span>
                        <span className="text-[10px] text-gray-500 font-mono">@{l.trigger_word}</span>
                      </div>
                      <div className="text-[10px] text-gray-500">
                        {l.nb_images_train} images · {l.cout_paye_fcfa} FCFA
                        {l.erreur && <span className="text-red-600"> · {l.erreur.slice(0,80)}</span>}
                      </div>
                    </div>
                    <button onClick={() => supprimerLora(l.lora_id)}
                      className="text-red-500 hover:text-red-700 p-1">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Sélecteur LoRA actif (si LoRA ready) */}
            {lorasReady.length > 0 && (
              <div>
                <label className={LABEL}>LoRA à appliquer pour la prochaine génération</label>
                <select value={brandLoraId} onChange={e => setBrandLoraId(e.target.value)}
                  className={INPUT + ' text-sm'}>
                  <option value="">— Aucun (génération standard) —</option>
                  {lorasReady.map(l => (
                    <option key={l.lora_id} value={l.lora_id}>
                      {l.label} (@{l.trigger_word})
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-gray-500 mt-1">
                  ⚠ Brand LoRA n'agit qu'en mode visuel <b>Premium</b> (Flux dev).
                  Pense à inclure le mot déclencheur dans ton brief.
                </p>
              </div>
            )}

            {/* Form création */}
            {!showLoraForm ? (
              <button onClick={() => setShowLoraForm(true)} type="button"
                className="w-full bg-fuchsia-100 hover:bg-fuchsia-200 text-fuchsia-800 font-semibold text-xs py-2 rounded-xl">
                + Entraîner un nouveau Brand LoRA
              </button>
            ) : (
              <div className="space-y-2 bg-fuchsia-50 border border-fuchsia-200 rounded-xl p-3">
                <p className="text-xs font-bold text-fuchsia-900">Nouveau Brand LoRA</p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={LABEL + ' text-xs'}>Label</label>
                    <input value={loraLabel} onChange={e => setLoraLabel(e.target.value)}
                      placeholder="Ex : ACME hiver 2026"
                      className={INPUT + ' text-sm'} maxLength={120} />
                  </div>
                  <div>
                    <label className={LABEL + ' text-xs'}>Trigger word</label>
                    <input value={loraTrigger} onChange={e => setLoraTrigger(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g,''))}
                      placeholder="ACMECORP"
                      className={INPUT + ' text-sm font-mono'} maxLength={80} />
                  </div>
                </div>
                <div>
                  <label className={LABEL + ' text-xs'}>Description (optionnel)</label>
                  <input value={loraDesc} onChange={e => setLoraDesc(e.target.value)}
                    placeholder="Ton, palette dominante, sujets typiques…"
                    className={INPUT + ' text-sm'} maxLength={500} />
                </div>
                <div className="text-[11px] bg-amber-50 border border-amber-200 rounded-lg px-2 py-2 text-amber-800">
                  <p className="font-semibold mb-0.5">⚠ Pré-requis :</p>
                  <p>Sélectionne <b>10-30 images</b> représentatives dans la médiathèque ci-dessus
                  ({refsSelectionnees.length} sélectionnée(s)) — variez angles/sujets/lumière.</p>
                </div>
                <label className="flex items-start gap-2 cursor-pointer text-xs">
                  <input type="checkbox" checked={loraAccept} onChange={e => setLoraAccept(e.target.checked)}
                    className="mt-0.5" />
                  <span className="text-gray-700">
                    J'accepte le débit de <b>200 000 FCFA</b> immédiat et non-remboursable
                    (couvre training fal.ai ~$200 USD + marge plateforme).
                  </span>
                </label>
                <div className="flex gap-2">
                  <button onClick={() => setShowLoraForm(false)} type="button"
                    className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold text-xs py-2 rounded-xl">
                    Annuler
                  </button>
                  <button onClick={lancerTrainingLora}
                    disabled={loraTraining || !loraAccept || refsSelectionnees.length < 10
                      || !loraLabel.trim() || !loraTrigger.trim()}
                    className="flex-1 bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50 text-white font-semibold text-xs py-2 rounded-xl flex items-center justify-center gap-1.5">
                    {loraTraining ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                    Lancer l'entraînement
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Sprint UX3 — Bulk CSV (collapsible) ────────────────────────── */}
      <div className={CARD}>
        <button onClick={() => setShowBulk(v => !v)} type="button"
          className="w-full flex items-center justify-between text-left">
          <p className="text-sm font-bold text-gray-800 flex items-center gap-2">
            📊 {t('designerPro.bulkTitle', 'Génération bulk depuis CSV/XLSX')}
            <span className="text-[10px] bg-amber-100 text-amber-700 rounded px-1.5 py-0.5 font-normal">
              50 visuels max
            </span>
          </p>
          <ChevronDown size={16} className={`text-gray-400 transition-transform ${showBulk ? 'rotate-180' : ''}`} />
        </button>
        {showBulk && (
          <div className="space-y-3">
            <p className="text-[11px] text-gray-500 leading-relaxed">
              {t('designerPro.bulkSub', "Uploade un CSV/XLSX (≤50 lignes, ≤10 MB). Yukpo détecte le mapping colonnes → visuel et génère N visuels personnalisés en parallèle.")}
            </p>

            {!bulkAnalysis && (
              <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2">
                <input ref={bulkFileRef} type="file" accept=".csv,.xlsx,.xlsm,.tsv,.txt"
                  className="flex-1 min-w-0 text-xs text-gray-600 file:mr-2 file:py-1 file:px-2 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-amber-100 file:text-amber-700 hover:file:bg-amber-200 cursor-pointer" />
                <button onClick={bulkAnalyser} disabled={bulkAnalysing}
                  className="shrink-0 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded-xl flex items-center gap-1.5 shadow-sm">
                  {bulkAnalysing ? <Loader2 size={13} className="animate-spin" /> : '🔍'}
                  Analyser
                </button>
              </div>
            )}

            {bulkAnalysis && (
              <div className="space-y-2 bg-amber-50 border border-amber-200 rounded-xl p-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <p className="text-xs font-bold text-amber-900">
                    {bulkAnalysis.nb_lignes} ligne(s) · {bulkAnalysis.format_detecte.toUpperCase()}
                  </p>
                  <span className="text-[10px] bg-white border border-amber-200 rounded px-2 py-0.5 font-mono text-amber-700">
                    {bulkAnalysis.cle_projet_recommande}
                  </span>
                </div>
                <p className="text-[11px] text-amber-800">{bulkAnalysis.raison_ia}</p>
                <div className="text-[11px] text-gray-700">
                  <p className="font-semibold">Template brief auto-détecté :</p>
                  <code className="block bg-white border border-amber-200 rounded px-2 py-1 mt-0.5 text-[10px] break-words">
                    {bulkAnalysis.template_brief}
                  </code>
                </div>
                <div className="text-[11px] text-gray-700">
                  <p className="font-semibold">Mapping colonnes → champs :</p>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {Object.entries(bulkAnalysis.mapping || {}).map(([k, v]) => (
                      <span key={k} className="text-[10px] bg-white border border-amber-200 rounded px-1.5 py-0.5">
                        <b>{k}</b> ← {String(v)}
                      </span>
                    ))}
                  </div>
                </div>
                {Array.isArray(bulkAnalysis.champs_manquants) && bulkAnalysis.champs_manquants.length > 0 && (
                  <div className="text-[10px] bg-orange-50 border border-orange-200 rounded px-2 py-1 text-orange-800">
                    ⚠ Champs manquants : {bulkAnalysis.champs_manquants.join(', ')}
                  </div>
                )}
                <div className="text-[11px] bg-white border border-amber-200 rounded-lg px-2 py-1.5">
                  <p className="font-semibold">💰 Estimation coût :</p>
                  <p>≈ <b>{bulkAnalysis.estimation_cout?.credits_total} crédits</b> (~{bulkAnalysis.estimation_cout?.fcfa_total} FCFA),
                  durée ≈ {bulkAnalysis.estimation_cout?.duree_estimee_sec}s</p>
                </div>
                <label className="flex items-start gap-2 cursor-pointer text-xs">
                  <input type="checkbox" checked={bulkAccepter}
                    onChange={e => setBulkAccepter(e.target.checked)} className="mt-0.5" />
                  <span>J'accepte le coût estimé ci-dessus pour générer {bulkAnalysis.nb_lignes} visuels.</span>
                </label>
                <div className="flex gap-2">
                  <button onClick={() => { setBulkAnalysis(null); setBulkAccepter(false) }}
                    type="button" className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold text-xs py-2 rounded-xl">
                    Annuler
                  </button>
                  <button onClick={bulkLancer}
                    disabled={bulkLaunching || !bulkAccepter}
                    className="flex-1 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-semibold text-xs py-2 rounded-xl flex items-center justify-center gap-1.5">
                    {bulkLaunching ? <Loader2 size={13} className="animate-spin" /> : '🚀'}
                    Générer les {bulkAnalysis.nb_lignes} visuels
                  </button>
                </div>
              </div>
            )}

            {bulkResults && (
              <div className="space-y-1 bg-emerald-50 border border-emerald-200 rounded-xl p-3">
                <p className="text-xs font-bold text-emerald-900">
                  ✓ Bulk terminé : {bulkResults.nb_done}/{bulkResults.total} OK · {bulkResults.nb_failed} échec(s)
                </p>
                <div className="max-h-48 overflow-y-auto space-y-0.5">
                  {bulkResults.results?.map((r: any) => (
                    <div key={r.index} className="text-[10px] bg-white border border-emerald-200 rounded px-2 py-1 flex items-center gap-2">
                      <span className={`text-[9px] font-bold px-1 rounded ${
                        r.statut === 'done' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                      }`}>{r.statut}</span>
                      <span className="font-mono text-gray-600">#{r.index + 1}</span>
                      <span className="flex-1 truncate text-gray-700">{r.brief?.slice(0, 80)}</span>
                      {r.download_url && (
                        <a href={r.download_url} target="_blank" rel="noreferrer"
                          className="text-amber-600 hover:underline shrink-0">PDF ↗</a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Brief minimal (zero-config UX2) ─────────────────────────────────── */}
      <div className={CARD}>
        <div>
          <label className={LABEL}>{t('designerPro.briefLabel', 'Brief du projet')}</label>
          <textarea value={brief} onChange={e => setBrief(e.target.value)} rows={5}
            placeholder={t('designerPro.briefPlaceholder',
              "Ex : Faire-part de décès en livret 8 pages pour M. Jean MBARGA, décédé le 5 mars 2026 à Yaoundé. Famille MBARGA-NGONO. Obsèques le 12 mars à 10h à la cathédrale.")}
            className={INPUT + ' resize-none leading-relaxed'} />
          <p className="text-[10px] text-gray-500 mt-1.5">
            {t('designerPro.briefHint', "💡 Décris en langage naturel — Yukpo détecte format, mode visuel et directives automatiquement.")}
          </p>
        </div>

        {/* Sprint UX4 — Card devis automatique */}
        {brief.trim().length >= 30 && (
          <div className="space-y-2">
            {devisLoading && !devis && (
              <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-xs text-gray-600">
                <Loader2 size={14} className="animate-spin" />
                {t('designerPro.devisLoading', 'Estimation du coût en cours…')}
              </div>
            )}
            {devis && devis.peut_payer && (
              <div className="rounded-xl border-2 border-emerald-300 bg-gradient-to-br from-emerald-50 to-green-50 p-3 space-y-1">
                <p className="text-xs font-bold text-emerald-900">
                  {modeEmoji(devis.mode_visuel_recommande)} {t('designerPro.modeAutoDetected', '{{mode}} recommandé', { mode: devis.mode_visuel_recommande })}
                  <span className="ml-2 text-[11px] text-emerald-700 font-normal">
                    ({devis.label_projet} · {devis.nombre_pages_estime} page(s))
                  </span>
                </p>
                <p className="text-xs text-emerald-800">
                  {t('designerPro.devisEstime', 'Coût estimé')} : <b>{devis.fcfa_user.toLocaleString()} FCFA</b>
                  <span className="text-[11px] opacity-70 ml-1">({devis.credits_estimes.toLocaleString()} crédits)</span>
                  · Solde : {devis.credits_disponibles.toLocaleString()} crédits ✓
                </p>
              </div>
            )}
            {devis && !devis.peut_payer && (
              <div className="rounded-xl border-2 border-amber-300 bg-amber-50 p-3 space-y-2">
                <p className="text-xs font-bold text-amber-900">
                  ⚠ {t('designerPro.creditsInsuffisants', 'Solde insuffisant')}
                </p>
                <p className="text-xs text-amber-800">
                  Mode {devis.mode_visuel_recommande} demanderait {devis.fcfa_user.toLocaleString()} FCFA
                  ({devis.credits_estimes.toLocaleString()} crédits). Tu as {devis.credits_disponibles.toLocaleString()} crédits.
                </p>
                {devis.fallback_si_solde_insuffisant && (
                  <button onClick={() => setModeVisuel(devis.fallback_si_solde_insuffisant)}
                    className="w-full bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold py-1.5 rounded-lg">
                    Utiliser le mode {devis.fallback_si_solde_insuffisant} à la place
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        <button onClick={generer} disabled={loading || !brief.trim()} className={BTN_PRIMARY}>
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {loading
            ? t('designerPro.generating', 'Génération en cours (1–2 min)…')
            : t('designerPro.generate', 'Générer le visuel')}
        </button>

        {/* ── Options avancées (repliables par défaut) ──────────────────── */}
        <button type="button" onClick={() => setShowAdvanced(v => !v)}
          className="w-full flex items-center justify-between text-left text-xs font-semibold text-gray-600 hover:text-gray-900 border-t border-gray-100 pt-3">
          <span className="flex items-center gap-1.5">
            ⚙️ {t('designerPro.advanced', 'Options avancées')}
            <span className="text-[10px] text-gray-400 font-normal">
              {showAdvanced ? '' : t('designerPro.advancedHint', '— format, mode visuel, sliders créatifs, langue/pays')}
            </span>
          </span>
          <ChevronDown size={14} className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
        </button>

        {showAdvanced && (
          <div className="space-y-4 pt-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-gray-700">{t('designerPro.formatSection', 'Format')}</p>
              <label className="flex items-center gap-2 cursor-pointer">
                <div className={`relative w-9 h-5 rounded-full transition-colors ${autoMode ? 'bg-amber-600' : 'bg-gray-300'}`}
                  onClick={() => setAutoMode(v => !v)}>
                  <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${autoMode ? 'left-4' : 'left-0.5'}`} />
                </div>
                <span className="text-xs font-medium text-gray-700">{t('designerPro.autoFormat', 'IA choisit')}</span>
              </label>
            </div>

            {!autoMode && (
              <div>
                <label className={LABEL}>{t('designerPro.formatProjet', 'Format de projet')}</label>
                <div className="relative">
                  <select value={cleHint} onChange={e => setCleHint(e.target.value)} className={INPUT + ' pr-8 appearance-none'}>
                    <option value="">— {t('designerPro.chooseFormat', 'Choisis un format')} —</option>
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

            <div className="rounded-xl bg-amber-50 border border-amber-100 p-3 space-y-2.5">
              <p className="text-xs font-bold text-amber-900 mb-1">{t('designerPro.directivesTitle', 'Directives visuelles')}</p>
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
              <label className={LABEL}>{t('designerPro.advancedOverride', 'Forcer un mode visuel (avancé)')}</label>
              <p className="text-[10px] text-gray-500 mb-1">
                Par défaut "auto" = Yukpo détecte le mode optimal. Force ici pour bypass.
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-1">
                {([
                  { v: 'auto',       emoji: '🤖', titleKey: 'designerPro.modeAuto',     fb: 'Auto (recommandé)', descKey: 'designerPro.modeAutoDesc',     fbDesc: 'IA décide selon brief' },
                  { v: 'sans',       emoji: '📋', titleKey: 'designerPro.modeSans',     fb: 'Sans IA visuelle',  descKey: 'designerPro.modeSansDesc',     fbDesc: 'Templates seuls' },
                  { v: 'standard',   emoji: '✨', titleKey: 'designerPro.modeStandard', fb: 'Standard',          descKey: 'designerPro.modeStandardDesc', fbDesc: 'Flux schnell — rapide' },
                  { v: 'premium',    emoji: '🎨', titleKey: 'designerPro.modePremium',  fb: 'Premium',           descKey: 'designerPro.modePremiumDesc',  fbDesc: 'Flux dev + variants' },
                  { v: 'ultra',      emoji: '🌟', titleKey: 'designerPro.modeUltra',    fb: 'Ultra',             descKey: 'designerPro.modeUltraDesc',    fbDesc: 'Flux Pro Ultra' },
                  { v: 'ultra_plus', emoji: '🚀', titleKey: 'designerPro.modeUltraPlus',fb: 'Ultra+',            descKey: 'designerPro.modeUltraPlusDesc',fbDesc: 'Ensemble 3 modèles' },
                ] as const).map(opt => (
                  <button key={opt.v} type="button" onClick={() => setModeVisuel(opt.v)}
                    className={`p-2.5 rounded-lg border-2 text-left transition-all ${
                      modeVisuel === opt.v
                        ? 'border-amber-500 bg-amber-50 shadow-sm'
                        : 'border-gray-200 hover:border-gray-300 bg-white'
                    }`}>
                    <div className="text-lg">{opt.emoji}</div>
                    <div className="text-xs font-bold text-gray-900 mt-0.5">{t(opt.titleKey, opt.fb)}</div>
                    <div className="text-[10px] text-gray-500 leading-tight">{t(opt.descKey, opt.fbDesc)}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
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

          {/* Sprint L1.4 — Export multilingual */}
          {resultat.projet_json_id && (
            <div className="border-t border-gray-200 pt-4">
              <button onClick={() => setShowMultilingual(v => !v)} type="button"
                className="flex items-center gap-2 text-sm font-bold text-gray-800 hover:text-amber-700">
                🌍 {t('designerPro.exportMultilingual', 'Exporter en plusieurs langues')}
                <ChevronDown size={14} className={`transition-transform ${showMultilingual ? 'rotate-180' : ''}`} />
              </button>
              {showMultilingual && (
                <div className="mt-2 space-y-2 bg-blue-50 border border-blue-200 rounded-xl p-3">
                  <p className="text-xs text-blue-800">
                    Génère le même projet dans plusieurs langues (~24 FCFA/langue, traduction Sonnet).
                  </p>
                  <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5">
                    {[
                      ['fr','🇫🇷 FR'],['en','🇬🇧 EN'],['es','🇪🇸 ES'],['pt','🇵🇹 PT'],['ar','🇸🇦 AR'],
                      ['de','🇩🇪 DE'],['zh','🇨🇳 ZH'],['sw','🇹🇿 SW'],['ha','🇳🇬 HA'],['wo','🇸🇳 WO'],
                      ['ln','🇨🇩 LN'],['am','🇪🇹 AM'],['ru','🇷🇺 RU'],['hi','🇮🇳 HI'],['tr','🇹🇷 TR'],
                    ].map(([code, label]) => (
                      <button key={code} type="button"
                        onClick={() => setMultilingualLangues(p =>
                          p.includes(code) ? p.filter(x => x !== code) : [...p, code])}
                        className={`text-xs px-2 py-1 rounded border transition-all ${
                          multilingualLangues.includes(code)
                            ? 'bg-blue-600 text-white border-blue-700'
                            : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400'
                        }`}>
                        {label}
                      </button>
                    ))}
                  </div>
                  <button onClick={lancerMultilingual}
                    disabled={multilingualLoading || multilingualLangues.length === 0}
                    className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold py-2 rounded-xl flex items-center justify-center gap-2">
                    {multilingualLoading ? <Loader2 size={13} className="animate-spin" /> : '🌍'}
                    Générer {multilingualLangues.length} langue(s) (~{multilingualLangues.length * 24} FCFA)
                  </button>
                  {multilingualResults && (
                    <div className="space-y-1">
                      {multilingualResults.results?.map((r: any) => (
                        <div key={r.langue} className="flex items-center gap-2 bg-white border border-blue-200 rounded px-2 py-1 text-[10px]">
                          <span className={`font-bold px-1 rounded ${r.ok ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                            {r.langue.toUpperCase()}
                          </span>
                          {r.ok ? (
                            <button onClick={() => b64download(r.pdf_base64, `projet_${r.langue}.pdf`, 'application/pdf')}
                              className="text-blue-600 hover:underline">Télécharger PDF ({r.size_kb} KB)</button>
                          ) : (
                            <span className="text-red-600">{r.erreur}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
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
