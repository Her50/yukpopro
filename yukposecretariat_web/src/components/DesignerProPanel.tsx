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
  download_url?: string
}

const CAT_SESSION = ['photo', 'illustration', 'scan', 'qr', 'icone', 'reference_style']
const CAT_COMPTE = ['logo', 'banniere', 'signature', 'cachet', 'filigrane', 'tampon', 'reference_style']
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
  reference_style: 'designerPro.catReferenceStyle',
}

// Sprint UX4 — emoji par mode visuel
function modeEmoji(mode: string): string {
  return ({ sans: '📋', standard: '✨', premium: '🎨', ultra: '🌟', ultra_plus: '🚀' } as any)[mode] || '✨'
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
  // Sprint UX4 : default 'auto' = backend résout via orchestrateur
  const [modeVisuel, setModeVisuel] = useState<'auto' | 'sans' | 'standard' | 'premium' | 'ultra' | 'ultra_plus'>('auto')
  // Charte d'organisation NON-négociable côté backend si configurée — pas de toggle UI
  // Sprint UX4 — Devis automatique
  const [devis, setDevis] = useState<any | null>(null)
  const [devisLoading, setDevisLoading] = useState(false)
  const devisTimerRef = useRef<any>(null)

  // Sprint 1.7 — Auto-orchestrateur LLM
  const [autoPrompt, setAutoPrompt] = useState('')
  const [orchestrating, setOrchestrating] = useState(false)
  const [orchestration, setOrchestration] = useState<any | null>(null)

  // Sprint 1.6b — Brand LoRA
  const [showLoraPanel, setShowLoraPanel] = useState(false)
  const [showLoraForm, setShowLoraForm] = useState(false)
  const [loraLabel, setLoraLabel] = useState('')
  const [loraTrigger, setLoraTrigger] = useState('')
  const [loraDesc, setLoraDesc] = useState('')
  const [loraAccept, setLoraAccept] = useState(false)
  const [loraTraining, setLoraTraining] = useState(false)
  const [brandLoraId, setBrandLoraId] = useState<string>('')

  // Sprint UX2 — Frontend épuré : options avancées repliées par défaut
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Sprint L1.4 — Multilingual
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

  // Sprint 1.6b — Brand LoRAs de l'organisation
  const { data: brandLoras, refetch: refetchLoras } = useQuery<any[]>({
    queryKey: ['designer-pro-brand-loras'],
    queryFn: () => infographieProAPI.brandLoraList().then(r => r.data),
    enabled: !!user && showLoraPanel,
    refetchInterval: showLoraPanel ? 15_000 : false,
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
    setLoading(true); setPageActive(0)
    try {
      // Sprint C1 — Détection d'intention via chat session
      let intent = 'nouveau_projet'
      let projetActifId: string | undefined
      try {
        const chatResp = await infographieProAPI.chatMessage({
          message: brief, medias_refs: refsSelectionnees, pays, langue,
        })
        intent = chatResp?.data?.intent || 'nouveau_projet'
        projetActifId = chatResp?.data?.projet_actif_id
      } catch { /* fallback */ }

      const refStyle = tousMedias.find(m => m.categorie === 'reference_style'
        && refsSelectionnees.includes(`${m.portee}:${m.media_id}`))

      let r: any
      if (intent === 'modification' || intent === 'traduction' || intent === 'regenerate_seed') {
        const projetId = projetActifId || resultat?.projet_json_id
        if (!projetId) {
          intent = 'nouveau_projet'
        } else {
          const instr = intent === 'regenerate_seed'
            ? `${brief}\n\n[Génère une autre variante]`
            : brief
          r = await infographieProAPI.modifier({
            projet_id: projetId, instructions: instr,
            medias_refs_supplementaires: refsSelectionnees, pays,
            directives_visuelles: directives,
          })
          setResultat(r.data as ResultatPro); setBrief('')
          toast.success(intent === 'traduction' ? 'Traduit ✓' : 'Modifié ✓')
        }
      }
      if (intent === 'nouveau_projet') {
        setResultat(null)
        const payload: any = {
          brief, pays, langue, medias_refs: refsSelectionnees, export_cmyk: true,
          directives_visuelles: directives, mode_visuel: modeVisuel,
        }
        if (refStyle) payload.reference_style_ref = `${refStyle.portee}:${refStyle.media_id}`
        if (brandLoraId) payload.brand_lora_id = brandLoraId
        r = autoMode
          ? await infographieProAPI.genererAuto({ ...payload, cle_projet_hint: cleHint || undefined })
          : await infographieProAPI.generer({ ...payload, cle_projet: cleHint || 'livret_deces_4p' })
        setResultat(r.data as ResultatPro)
        toast.success(t('designerPro.okGenerated'))
      }
      // Sprint C1 — MAJ projet_actif dans la session pour les futurs messages
      const pid = (r?.data || r)?.projet_json_id
      if (pid) {
        try { await infographieProAPI.chatUpdateProjetActif(pid) } catch {}
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || t('designerPro.errGenerate'))
    } finally {
      setLoading(false)
    }
  }

  // Sprint C1 — Reset session
  const resetChatSession = async () => {
    try {
      await infographieProAPI.chatReset()
      setResultat(null); setBrief(''); setRefsSelectionnees([])
      toast.success('Nouvelle session')
    } catch {
      toast.error('Reset échoué')
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

  // Sprint 1.7 — Auto-orchestrateur LLM
  const orchestrer = async () => {
    if (!autoPrompt.trim()) { toast.error(t('designerPro.autoErrEmpty', 'Décris ton besoin')); return }
    setOrchestrating(true); setOrchestration(null)
    try {
      // Sprint 1.8a — passe les médias déjà uploadés (sélectionnés ou tous)
      const allRefs = tousMedias.map(m => `${m.portee}:${m.media_id}`)
      const refsToAnalyze = refsSelectionnees.length > 0 ? refsSelectionnees : allRefs
      const r = await infographieProAPI.orchestrer({
        prompt: autoPrompt, pays, langue,
        medias_refs: refsToAnalyze.length > 0 ? refsToAnalyze : undefined,
      } as any)
      const data = r.data
      setOrchestration(data)
      if (data?.confiance >= 0.85) {
        toast.success(`${t('designerPro.autoDetected', 'Détecté')} : ${data.label_projet} (${Math.round(data.confiance * 100)}%)`)
      } else {
        toast(`${Math.round((data?.confiance || 0) * 100)}% — vérifie / précise`)
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err.response?.data?.detail || err.message || t('designerPro.autoErr', 'Orchestrateur indisponible'))
    } finally { setOrchestrating(false) }
  }

  const appliquerOrchestration = () => {
    if (!orchestration) return
    setBrief(orchestration.brief_enrichi || autoPrompt)
    setCleHint(orchestration.cle_projet || '')
    setAutoMode(false)
    if (orchestration.mode_visuel_suggere) setModeVisuel(orchestration.mode_visuel_suggere)
    const dv = orchestration.directives_visuelles_pre || {}
    if (typeof dv.creativite === 'number') setCreativite(dv.creativite)
    if (typeof dv.densite_texte === 'number') setDensite(dv.densite_texte)
    if (typeof dv.importance_images === 'number') setImportanceImg(dv.importance_images)
    if (typeof dv.elegance === 'number') setElegance(dv.elegance)
    // Sprint 1.8a — pré-cocher les médias jugés pertinents
    if (Array.isArray(orchestration.medias_refs_actifs) && orchestration.medias_refs_actifs.length > 0) {
      setRefsSelectionnees(orchestration.medias_refs_actifs)
    }
    toast.success(t('designerPro.autoApplied', 'Formulaire pré-rempli'))
  }

  // Sprint L1.4 — Lance export multilingual
  const lancerMultilingual = async () => {
    if (!resultat?.projet_json_id) return
    if (multilingualLangues.length === 0) { toast.error('Sélectionne au moins 1 langue'); return }
    setMultilingualLoading(true); setMultilingualResults(null)
    try {
      const r = await infographieProAPI.multilingual({
        projet_id: resultat.projet_json_id,
        langues_cibles: multilingualLangues,
      })
      setMultilingualResults(r.data)
      toast.success(`${r.data.nb_succes}/${r.data.total_langues} langues OK`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Export multilingue échoué')
    } finally { setMultilingualLoading(false) }
  }

  // Sprint UX4 — Fetch devis quand brief assez long (debounced 800ms)
  useEffect(() => {
    if (devisTimerRef.current) clearTimeout(devisTimerRef.current)
    if (!brief || brief.trim().length < 30) { setDevis(null); return }
    devisTimerRef.current = setTimeout(async () => {
      setDevisLoading(true)
      try {
        const r = await infographieProAPI.devis({
          brief, pays, langue, medias_refs: refsSelectionnees,
          cle_projet: cleHint || undefined,
        })
        setDevis(r.data)
      } catch {
        setDevis(null)
      } finally { setDevisLoading(false) }
    }, 800)
    return () => devisTimerRef.current && clearTimeout(devisTimerRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brief, pays, langue, refsSelectionnees, cleHint])

  // Sprint UX3 — Bulk CSV (Sec)
  const bulkAnalyser = async () => {
    const f = bulkFileRef.current?.files?.[0]
    if (!f) { toast.error('Sélectionne un fichier CSV ou XLSX'); return }
    setBulkAnalysing(true); setBulkAnalysis(null); setBulkResults(null); setBulkAccepter(false)
    try {
      const fd = new FormData()
      fd.append('fichier', f)
      const r = await infographieProAPI.bulkAnalyser(fd)
      setBulkAnalysis(r.data)
      toast.success(`${r.data.nb_lignes} ligne(s) analysée(s)`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Analyse échouée')
    } finally { setBulkAnalysing(false) }
  }
  const bulkLancer = async () => {
    if (!bulkAnalysis) return
    if (!bulkAccepter) { toast.error('Confirme le coût estimé'); return }
    setBulkLaunching(true); setBulkResults(null)
    try {
      const r = await infographieProAPI.bulkLancer({
        rows: bulkAnalysis.rows_complete || [],
        template_brief: bulkAnalysis.template_brief,
        mapping: bulkAnalysis.mapping,
        cle_projet: bulkAnalysis.cle_projet_recommande,
        mode_visuel: 'standard',
        pays, langue, accepter_cout: true,
      })
      setBulkResults(r.data)
      toast.success(`Bulk : ${r.data.nb_done}/${r.data.total} OK`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Bulk échoué')
    } finally { setBulkLaunching(false) }
  }

  // Sprint 1.6b — Brand LoRA training (Sec)
  const lancerTrainingLora = async () => {
    if (!loraLabel.trim() || !loraTrigger.trim()) {
      toast.error('Label + trigger word requis'); return
    }
    if (refsSelectionnees.length < 10) {
      toast.error(`≥10 images requises (actuel: ${refsSelectionnees.length})`); return
    }
    if (!loraAccept) { toast.error('Coche la confirmation du coût'); return }
    setLoraTraining(true)
    try {
      await infographieProAPI.brandLoraTrain({
        label: loraLabel, trigger_word: loraTrigger,
        description: loraDesc || undefined,
        images_refs: refsSelectionnees, accepter_cout: true,
      })
      toast.success('Training lancé (15-30 min)')
      setShowLoraForm(false); setLoraLabel(''); setLoraTrigger(''); setLoraDesc(''); setLoraAccept(false)
      refetchLoras()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Échec training')
    } finally { setLoraTraining(false) }
  }
  const supprimerLora = async (loraId: string) => {
    if (!confirm('Désactiver ce Brand LoRA ?')) return
    try {
      await infographieProAPI.brandLoraDelete(loraId)
      if (brandLoraId === loraId) setBrandLoraId('')
      toast.success('LoRA désactivé'); refetchLoras()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Échec suppression')
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
                  {orchestration.type_projet === 'mono' ? t('designerPro.autoMono', 'Visuel mono-page') : t('designerPro.autoMulti', 'Projet multi-page')}
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
                {Math.round(orchestration.confiance * 100)}% {t('designerPro.autoConfidence', 'confiance')}
              </span>
            </div>
            {Array.isArray(orchestration.alternatives) && orchestration.alternatives.length > 0 && (
              <div className="text-[11px] text-gray-600">
                <span className="font-semibold">{t('designerPro.autoAlts', 'Alternatives')} : </span>
                {orchestration.alternatives.map((a: any) => a.label).join(' · ')}
              </div>
            )}
            {Array.isArray(orchestration.manques) && orchestration.manques.length > 0 && (
              <div className="text-[11px] bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5 text-amber-800">
                <span className="font-semibold">⚠ {t('designerPro.autoMissing', 'Manques')} : </span>{orchestration.manques.join(', ')}
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
                <p className="font-semibold">{t('designerPro.autoQuestions', 'Pour affiner')} :</p>
                {orchestration.questions_clarification.map((q: string, i: number) => (
                  <p key={i}>• {q}</p>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-2 text-[11px] text-gray-600">
              <span className="bg-gray-100 rounded px-2 py-0.5">
                {t('designerPro.autoMode', 'Mode')} : <b className="text-violet-700">{orchestration.mode_visuel_suggere}</b>
              </span>
              {orchestration.archetype_dominant && (
                <span className="bg-gray-100 rounded px-2 py-0.5">
                  {t('designerPro.autoArche', 'Archétype')} : <b className="text-violet-700">{orchestration.archetype_dominant}</b>
                </span>
              )}
              <span className="bg-gray-100 rounded px-2 py-0.5">
                ~{orchestration.cout_estime_credits} {t('designerPro.credits', 'crédits')}
              </span>
            </div>
            <button onClick={appliquerOrchestration}
              className="w-full bg-violet-100 hover:bg-violet-200 text-violet-800 font-semibold py-2 rounded-xl transition-colors text-xs mt-2">
              {t('designerPro.autoApply', 'Pré-remplir le formulaire ↓')}
            </button>
          </div>
        )}
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
                      className="w-full bg-gray-50 aspect-square flex items-center justify-center text-[10px] text-gray-500 p-1">
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

      {/* ── Sprint 1.6 — Brand LoRA (collapsible) ─────────────────────────── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-5 space-y-3">
        <button onClick={() => setShowLoraPanel(v => !v)} type="button"
          className="w-full flex items-center justify-between text-left">
          <p className="text-sm font-semibold text-gray-800 flex items-center gap-2">
            <Sparkles size={15} className="text-fuchsia-600" />
            Brand LoRA — Style de marque entraîné
          </p>
          <span className={`text-gray-400 transition-transform ${showLoraPanel ? 'rotate-180' : ''}`}>▾</span>
        </button>
        {showLoraPanel && (
          <div className="space-y-3">
            <p className="text-[11px] text-gray-500 leading-relaxed">
              Entraîne un LoRA Flux à partir de 10-30 images de ta marque.
              Réutilisable à vie. <b>Coût : 200 000 FCFA / LoRA (one-shot)</b>.
            </p>
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
            {lorasReady.length > 0 && (
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  LoRA à appliquer (mode Premium uniquement)
                </label>
                <select value={brandLoraId} onChange={e => setBrandLoraId(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white">
                  <option value="">— Aucun —</option>
                  {lorasReady.map(l => (
                    <option key={l.lora_id} value={l.lora_id}>{l.label} (@{l.trigger_word})</option>
                  ))}
                </select>
              </div>
            )}
            {!showLoraForm ? (
              <button onClick={() => setShowLoraForm(true)} type="button"
                className="w-full bg-fuchsia-100 hover:bg-fuchsia-200 text-fuchsia-800 font-semibold text-xs py-2 rounded-xl">
                + Entraîner un nouveau Brand LoRA
              </button>
            ) : (
              <div className="space-y-2 bg-fuchsia-50 border border-fuchsia-200 rounded-xl p-3">
                <p className="text-xs font-bold text-fuchsia-900">Nouveau Brand LoRA</p>
                <div className="grid grid-cols-2 gap-2">
                  <input value={loraLabel} onChange={e => setLoraLabel(e.target.value)}
                    placeholder="Label (ex: ACME hiver 2026)"
                    className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm" maxLength={120} />
                  <input value={loraTrigger}
                    onChange={e => setLoraTrigger(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g,''))}
                    placeholder="TRIGGERWORD"
                    className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm font-mono" maxLength={80} />
                </div>
                <input value={loraDesc} onChange={e => setLoraDesc(e.target.value)}
                  placeholder="Description (optionnel)"
                  className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm" maxLength={500} />
                <p className="text-[11px] bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5 text-amber-800">
                  Sélectionne <b>10-30 images</b> dans la médiathèque ({refsSelectionnees.length} sélectionnée(s)).
                </p>
                <label className="flex items-start gap-2 cursor-pointer text-xs">
                  <input type="checkbox" checked={loraAccept} onChange={e => setLoraAccept(e.target.checked)} className="mt-0.5" />
                  <span>J'accepte le débit de <b>200 000 FCFA</b> non-remboursable.</span>
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
                    Lancer training
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Sprint UX3 — Bulk CSV (Sec) ────────────────────────────────── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-5 space-y-3">
        <button onClick={() => setShowBulk(v => !v)} type="button"
          className="w-full flex items-center justify-between text-left">
          <p className="text-sm font-semibold text-gray-800 flex items-center gap-2">
            📊 {t('designerPro.bulkTitle', 'Génération bulk depuis CSV/XLSX')}
            <span className="text-[10px] bg-amber-100 text-amber-700 rounded px-1.5 py-0.5 font-normal">
              50 visuels max
            </span>
          </p>
          <span className={`transition-transform ${showBulk ? 'rotate-180' : ''}`}>▾</span>
        </button>
        {showBulk && (
          <div className="space-y-3">
            <p className="text-[11px] text-gray-500">
              {t('designerPro.bulkSub', "Uploade un CSV/XLSX (≤50 lignes). Yukpo détecte le mapping et génère N visuels personnalisés.")}
            </p>
            {!bulkAnalysis && (
              <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2">
                <input ref={bulkFileRef} type="file" accept=".csv,.xlsx,.xlsm,.tsv,.txt"
                  className="flex-1 min-w-0 text-xs" />
                <button onClick={bulkAnalyser} disabled={bulkAnalysing}
                  className="shrink-0 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded-xl flex items-center gap-1.5">
                  {bulkAnalysing ? <Loader2 size={13} className="animate-spin" /> : '🔍'}
                  Analyser
                </button>
              </div>
            )}
            {bulkAnalysis && (
              <div className="space-y-2 bg-amber-50 border border-amber-200 rounded-xl p-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <p className="text-xs font-bold text-amber-900">
                    {bulkAnalysis.nb_lignes} ligne(s) · {bulkAnalysis.format_detecte?.toUpperCase()}
                  </p>
                  <span className="text-[10px] bg-white border border-amber-200 rounded px-2 py-0.5 font-mono text-amber-700">
                    {bulkAnalysis.cle_projet_recommande}
                  </span>
                </div>
                <p className="text-[11px] text-amber-800">{bulkAnalysis.raison_ia}</p>
                <code className="block bg-white border border-amber-200 rounded px-2 py-1 text-[10px]">
                  {bulkAnalysis.template_brief}
                </code>
                <div className="text-[11px] bg-white border border-amber-200 rounded-lg px-2 py-1.5">
                  💰 ≈ <b>{bulkAnalysis.estimation_cout?.credits_total} crédits</b>
                  (~{bulkAnalysis.estimation_cout?.fcfa_total} FCFA),
                  ~{bulkAnalysis.estimation_cout?.duree_estimee_sec}s
                </div>
                <label className="flex items-start gap-2 cursor-pointer text-xs">
                  <input type="checkbox" checked={bulkAccepter}
                    onChange={e => setBulkAccepter(e.target.checked)} className="mt-0.5" />
                  <span>J'accepte le coût pour {bulkAnalysis.nb_lignes} visuels.</span>
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
                    Générer
                  </button>
                </div>
              </div>
            )}
            {bulkResults && (
              <div className="space-y-1 bg-emerald-50 border border-emerald-200 rounded-xl p-3">
                <p className="text-xs font-bold text-emerald-900">
                  ✓ {bulkResults.nb_done}/{bulkResults.total} OK · {bulkResults.nb_failed} échec(s)
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

      {/* Génération zero-config (UX2) */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-5 space-y-4">
        {resultat && (
          <div className="flex justify-end">
            <button onClick={resetChatSession} type="button"
              className="text-[10px] text-amber-600 hover:text-amber-800 font-semibold">
              ↻ {t('designerPro.nouveauProjet', 'Nouveau projet')}
            </button>
          </div>
        )}
        <textarea value={brief} onChange={e => setBrief(e.target.value)} rows={5}
          placeholder={t('designerPro.briefPlaceholder')}
          className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 resize-none" />
        <p className="text-[10px] text-gray-500 -mt-2">
          💡 {t('designerPro.briefHint', "Décris en langage naturel — Yukpo détecte format/mode/directives auto.")}
        </p>

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

        <button onClick={generer} disabled={loading || !brief.trim()}
          className="w-full bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2 shadow-sm">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {loading ? t('designerPro.generating') : t('designerPro.generate')}
        </button>

        {/* ── Sprint UX2 — Options avancées repliables ──────────────────── */}
        <button type="button" onClick={() => setShowAdvanced(v => !v)}
          className="w-full flex items-center justify-between text-left text-xs font-semibold text-gray-600 hover:text-gray-900 border-t border-gray-100 pt-3">
          <span>⚙️ {t('designerPro.advanced', 'Options avancées')}
            <span className="text-[10px] text-gray-400 font-normal ml-1">
              {showAdvanced ? '' : t('designerPro.advancedHint', '— format, mode visuel, sliders, langue/pays')}
            </span>
          </span>
          <span className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`}>▾</span>
        </button>

        {showAdvanced && (
          <div className="space-y-4 pt-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-gray-700">{t('designerPro.briefAndOptions')}</p>
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

            <div className="space-y-2">
              <label className="block text-sm font-semibold text-gray-800">
                {t('designerPro.advancedOverride', 'Forcer un mode visuel (avancé)')}
              </label>
              <p className="text-[10px] text-gray-500 -mt-1">
                Par défaut "auto" = Yukpo détecte le mode optimal.
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {([
                  { v: 'auto',       emoji: '🤖', titleKey: 'designerPro.modeAuto',       descKey: 'designerPro.modeAutoDesc' },
                  { v: 'sans',       emoji: '📋', titleKey: 'designerPro.modeSans',       descKey: 'designerPro.modeSansDesc' },
                  { v: 'standard',   emoji: '✨', titleKey: 'designerPro.modeStandard',   descKey: 'designerPro.modeStandardDesc' },
                  { v: 'premium',    emoji: '🎨', titleKey: 'designerPro.modePremium',    descKey: 'designerPro.modePremiumDesc' },
                  { v: 'ultra',      emoji: '🌟', titleKey: 'designerPro.modeUltra',      descKey: 'designerPro.modeUltraDesc' },
                  { v: 'ultra_plus', emoji: '🚀', titleKey: 'designerPro.modeUltraPlus',  descKey: 'designerPro.modeUltraPlusDesc' },
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
          </div>
        )}
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
            <div className="flex gap-2 flex-wrap">
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
              {resultat.download_url && (
                <a href={resultat.download_url} target="_blank" rel="noreferrer"
                  className="flex items-center gap-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-medium px-3 py-2 rounded-xl"
                  title={t('designerPro.permanentLinkTitle')}>
                  🔗 {t('designerPro.permanentLink')}
                </a>
              )}
            </div>
          </div>

          {resultat.download_url && (
            <p className="text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
              📁 {t('designerPro.savedToDocuments')}
            </p>
          )}

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

          {/* Sprint L1.4 — Multilingual export (Sec) */}
          {resultat.projet_json_id && (
            <div className="border-t border-gray-100 pt-4">
              <button onClick={() => setShowMultilingual(v => !v)} type="button"
                className="flex items-center gap-2 text-sm font-semibold text-gray-800 hover:text-amber-700">
                🌍 {t('designerPro.exportMultilingual', 'Exporter en plusieurs langues')}
                <span className={`transition-transform ${showMultilingual ? 'rotate-180' : ''}`}>▾</span>
              </button>
              {showMultilingual && (
                <div className="mt-2 space-y-2 bg-blue-50 border border-blue-200 rounded-xl p-3">
                  <p className="text-xs text-blue-800">~24 FCFA/langue (traduction Sonnet).</p>
                  <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5">
                    {[['fr','🇫🇷 FR'],['en','🇬🇧 EN'],['es','🇪🇸 ES'],['pt','🇵🇹 PT'],['ar','🇸🇦 AR'],
                      ['de','🇩🇪 DE'],['zh','🇨🇳 ZH'],['sw','🇹🇿 SW'],['ha','🇳🇬 HA'],['wo','🇸🇳 WO'],
                      ['ln','🇨🇩 LN'],['am','🇪🇹 AM'],['ru','🇷🇺 RU'],['hi','🇮🇳 HI'],['tr','🇹🇷 TR'],
                    ].map(([code, label]) => (
                      <button key={code} type="button"
                        onClick={() => setMultilingualLangues(p =>
                          p.includes(code) ? p.filter(x => x !== code) : [...p, code])}
                        className={`text-xs px-2 py-1 rounded border ${
                          multilingualLangues.includes(code)
                            ? 'bg-blue-600 text-white border-blue-700'
                            : 'bg-white text-gray-700 border-gray-300'
                        }`}>{label}</button>
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
                              className="text-blue-600 hover:underline">PDF ({r.size_kb} KB)</button>
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
