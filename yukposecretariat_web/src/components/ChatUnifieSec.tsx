/**
 * Sprint S1 — Chat Unifié YukpoSecrétariat.
 *
 * Un seul chat qui consolide tous les modules :
 *   - Rédaction (lettres, courriers, contrats, CV, etc.)
 *   - OCR / scan d'images
 *   - Transcription audio
 *   - Infographie mono-page (carte de visite, flyer, affiche, diplôme, etc.)
 *   - Designer Pro multi-page (livret, brochure, magazine — basculé sur chat C1)
 *   - Traduction texte / fichier
 *
 * L'utilisateur tape juste son besoin + (optionnel) attache image/PDF/audio.
 * Yukpo détecte l'intention via /bureau/chat/message puis route auto.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Loader2, Sparkles, Paperclip, Mic, Image as ImageIcon,
  FileText, Send, X, Download, Camera, ListPlus,
} from 'lucide-react'
import toast from 'react-hot-toast'
import {
  secChatAPI, redactionAPI, ocrAPI, audioAPI, traductionAPI, infographieAPI,
  infographieProAPI, bureauSessionAPI,
} from '../api/client'
import SuggestionsChips, { type Suggestion } from './SuggestionsChips'

type Attachment = {
  file: File
  type: 'image' | 'pdf' | 'audio' | 'autre'
  preview?: string
}

type ChatTurn = {
  role: 'user' | 'yukpo'
  ts: string
  content: string
  intent?: string
  resultat?: any
  attachments?: Attachment[]
}

function detecterTypeFichier(file: File): Attachment['type'] {
  const t = (file.type || '').toLowerCase()
  const n = file.name.toLowerCase()
  if (t.startsWith('image/') || /\.(png|jpe?g|webp|bmp|gif)$/.test(n)) return 'image'
  if (t === 'application/pdf' || n.endsWith('.pdf')) return 'pdf'
  if (t.startsWith('audio/') || /\.(mp3|wav|m4a|ogg|webm)$/.test(n)) return 'audio'
  return 'autre'
}

// Téléchargement direct d'un fichier base64 (DOCX, PDF). Utilisé pour les
// résultats OCR/Audio/Rédaction qui renvoient word_base64 dans la réponse.
function b64download(b64: string, filename: string, mime: string) {
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const blob = new Blob([arr], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export default function ChatUnifieSec() {
  const { t } = useTranslation()
  const [message, setMessage] = useState('')
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [loading, setLoading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const audioRef = useRef<HTMLInputElement>(null)
  const [recording, setRecording] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  // Camera scan (document, reçu, carte de visite, ordonnance, identité, etc.)
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null)

  // Sprint S1 — Web Audio capture (📤 enregistrer dictée vocale)
  const demarrerEnregistrement = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      audioChunksRef.current = []
      recorder.ondataavailable = e => audioChunksRef.current.push(e.data)
      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        const file = new File([blob], `dictee_${Date.now()}.webm`, { type: 'audio/webm' })
        setAttachments(prev => [...prev, { file, type: 'audio' }])
        stream.getTracks().forEach(t => t.stop())
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setRecording(true)
      toast(t('chatUnifie.recordingStarted', '🎤 Enregistrement…'))
    } catch (e: any) {
      toast.error(t('chatUnifie.micRefused', 'Micro refusé : ') + (e?.message || ''))
    }
  }

  const arreterEnregistrement = () => {
    mediaRecorderRef.current?.stop()
    mediaRecorderRef.current = null
    setRecording(false)
  }

  // ── Camera scan (cas d'usage secrétariat : ordonnance, factures, cartes,
  // documents administratifs photographiés directement plutôt que scannés)
  const demarrerCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
      })
      setCameraStream(stream)
      setCameraOpen(true)
      setTimeout(() => {
        if (videoRef.current) videoRef.current.srcObject = stream
      }, 100)
    } catch (e: any) {
      toast.error(t('chatUnifie.cameraRefused', 'Caméra refusée : ') + (e?.message || ''))
    }
  }

  const fermerCamera = () => {
    if (cameraStream) {
      cameraStream.getTracks().forEach(tr => tr.stop())
      setCameraStream(null)
    }
    setCameraOpen(false)
  }

  const capturerPhoto = () => {
    if (!videoRef.current || !canvasRef.current) return
    const ctx = canvasRef.current.getContext('2d')
    if (!ctx) return
    canvasRef.current.width = videoRef.current.videoWidth
    canvasRef.current.height = videoRef.current.videoHeight
    ctx.drawImage(videoRef.current, 0, 0)
    canvasRef.current.toBlob(
      (blob) => {
        if (!blob) return
        const file = new File([blob], `scan_${Date.now()}.jpg`, { type: 'image/jpeg' })
        ajouterFichier(file)
        fermerCamera()
      },
      'image/jpeg',
      0.92,
    )
  }

  const ajouterFichier = (file: File | null) => {
    if (!file) return
    const att: Attachment = { file, type: detecterTypeFichier(file) }
    if (att.type === 'image') {
      att.preview = URL.createObjectURL(file)
    }
    setAttachments(prev => [...prev, att])
  }

  const retirerAttachment = (i: number) => {
    setAttachments(prev => prev.filter((_, idx) => idx !== i))
  }

  // ─── Routage par intent ────────────────────────────────────────────────
  const executerSelonIntent = async (intent: string, msg: string, atts: Attachment[]) => {
    const imageAtt = atts.find(a => a.type === 'image')
    const audioAtt = atts.find(a => a.type === 'audio')
    const pdfAtt = atts.find(a => a.type === 'pdf')

    switch (intent) {
      case 'redaction': {
        // Backend /bureau/redaction/generer attend {type_doc, informations,
        // pays, mode, reformuler_texte}. Pas de "brief" ni "langue". Default
        // type_doc='lettre' (intent classifier ne sous-classe pas encore).
        const r = await redactionAPI.generer({
          type_doc: 'lettre',
          informations: { description: msg },
          pays: 'CM',
          mode: 'standard',
        })
        return { type: 'document', data: r.data }
      }
      case 'ocr_image':
      case 'ocr_manuscrit': {
        if (!imageAtt) throw new Error('Image attendue mais absente')
        const fd = new FormData()
        fd.append('fichier', imageAtt.file)
        // export_word=true → on récupère word_base64 + fichier_id pour
        // proposer un téléchargement DOCX dans le chat.
        if (intent === 'ocr_image') fd.append('export_word', 'true')
        const r = intent === 'ocr_manuscrit'
          ? await ocrAPI.manuscrit(fd) : await ocrAPI.scanner(fd)
        return { type: 'ocr', data: r.data, sub_intent: intent }
      }
      case 'audio_transcrire': {
        if (!audioAtt) throw new Error('Audio attendu mais absent')
        // Backend /bureau/audio/transcrire attend "fichier" (UploadFile) et
        // "type_document_cible" (Form, default "dictee"). Le chat enregistre
        // une dictée → on garde "dictee" qui produit un document Word formaté.
        const fd = new FormData()
        fd.append('fichier', audioAtt.file)
        fd.append('type_document_cible', 'dictee')
        fd.append('pays', 'CM')
        const r = await audioAPI.transcrire(fd)
        return { type: 'audio', data: r.data }
      }
      case 'infographie_mono': {
        const r = await infographieAPI.generer({
          brief: msg, type_gabarit: 'auto' as any, pays: 'CM', export_cmyk: true,
        })
        return { type: 'visuel_mono', data: r.data }
      }
      case 'designer_pro': {
        // Sous-chat Designer Pro (Sprint C1) — bascule
        const subChat = await infographieProAPI.chatMessage({
          message: msg, pays: 'CM', langue: 'fr',
        })
        const subIntent = subChat?.data?.intent || 'nouveau_projet'
        const projetActif = subChat?.data?.projet_actif_id
        if (subIntent === 'modification' && projetActif) {
          const r = await infographieProAPI.modifier({
            projet_id: projetActif, instructions: msg, pays: 'CM',
          })
          if (r?.data?.projet_json_id) await infographieProAPI.chatUpdateProjetActif(r.data.projet_json_id).catch(() => {})
          return { type: 'designer_pro', data: r.data, sub_intent: 'modification' }
        } else {
          const r = await infographieProAPI.genererAuto({
            brief: msg, pays: 'CM', langue: 'fr', export_cmyk: true,
            mode_visuel: 'auto', directives_visuelles: {},
          } as any)
          if (r?.data?.projet_json_id) await infographieProAPI.chatUpdateProjetActif(r.data.projet_json_id).catch(() => {})
          return { type: 'designer_pro', data: r.data, sub_intent: 'nouveau_projet' }
        }
      }
      case 'traduction_texte': {
        const r = await traductionAPI.traduireTexte({
          contenu: msg, langue_source: 'auto', langue_cible: 'en',
          format_sortie: 'texte',
        })
        return { type: 'traduction', data: r.data }
      }
      case 'traduction_fichier': {
        if (!pdfAtt) throw new Error('PDF/DOCX attendu mais absent')
        const fd = new FormData()
        fd.append('fichier', pdfAtt.file)
        fd.append('langue_source', 'auto')
        // Langue cible par défaut anglais — l'intent classifier ne l'extrait
        // pas encore. L'utilisateur peut préciser dans un message suivant.
        fd.append('langue_cible', 'en')
        const r = await traductionAPI.traduireFichier(fd)
        return { type: 'traduction_fichier', data: r.data }
      }
      default:
        return { type: 'inconnu', data: null }
    }
  }

  // ── Queue multi-input pendant génération (BATCH-4) ────────────────────
  // L'utilisateur peut continuer à taper, joindre, dicter pendant que Yukpo
  // répond. Les inputs additionnels sont stockés dans `pendingQueue` et
  // envoyés automatiquement à la fin de la réponse en cours (FIFO).
  type PendingItem = { message: string; attachments: Attachment[] }
  const [pendingQueue, setPendingQueue] = useState<PendingItem[]>([])

  // Flush queue dès que loading passe à false ET qu'il y a des items en attente.
  useEffect(() => {
    if (!loading && pendingQueue.length > 0) {
      const next = pendingQueue[0]
      setPendingQueue(prev => prev.slice(1))
      // Petit delay pour laisser le DOM mettre à jour l'historique
      setTimeout(() => executerEnvoi(next.message, next.attachments), 80)
    }
  }, [loading, pendingQueue.length])  // eslint-disable-line react-hooks/exhaustive-deps

  const retirerDeLaQueue = (idx: number) =>
    setPendingQueue(prev => prev.filter((_, i) => i !== idx))

  // Helper interne : exécute réellement l'envoi (utilisé par envoyer + queue flush)
  const executerEnvoi = async (msg: string, atts: Attachment[]) => {
    const userTurn: ChatTurn = {
      role: 'user', ts: new Date().toISOString(),
      content: msg, attachments: [...atts],
    }
    setTurns(prev => [...prev, userTurn])
    setLoading(true)

    try {
      // ── Nouveaux pipelines web (slides Reveal.js + landing page) ──────
      // Détection keyword AVANT orchestrer pour gain de latence + clarté.
      if (atts.length === 0 && msg.trim()) {
        const txt = msg.toLowerCase()

        // ─── Pipeline vidéo IA (text-to-video Kling/LTX) ──────────────
        // Cf. ChatPage YPro pour la logique de parsing (durée/aspect/mode).
        const videoMatch = /(g[ée]n[èe]re|cr[ée]e|fais|produis|veux)[^.]*\bvid[ée]o\b|\bvid[ée]o\s+(promo|tv|pub|reels?|teaser)|\bteaser\b|\breel\b|short\s*video|clip\s*vid[ée]o|spot\s*(pub|tv|publicitaire)|motion\s*ad/i.test(txt)
        if (videoMatch) {
          try {
            // Durée 5-60s : extraction depuis le prompt (voir ChatPage YPro
            // pour la logique détaillée). 5/10s = appel natif ; 15-60s =
            // stitching N×10s clips parallèles + FFmpeg concat crossfade.
            let duree_s = 5
            const mMin = txt.match(/\b(1|une?)\s*(min(?:ute)?s?)\b/)
            if (mMin) {
              duree_s = 60
            } else {
              const mSec = txt.match(/\b(\d{1,2})\s*s(?:ec(?:ondes?)?)?\b/)
              if (mSec) {
                duree_s = Math.max(5, Math.min(60, parseInt(mSec[1], 10)))
              } else {
                const motsToNum: Record<string, number> = {
                  'cinq': 5, 'dix': 10, 'quinze': 15, 'vingt': 20,
                  'trente': 30, 'quarante': 40, 'cinquante': 50, 'soixante': 60,
                }
                for (const [mot, n] of Object.entries(motsToNum)) {
                  if (new RegExp(`\\b${mot}\\s*secondes?\\b`, 'i').test(txt)) {
                    duree_s = n
                    break
                  }
                }
              }
            }
            duree_s = Math.max(5, Math.min(60, Math.round(duree_s / 5) * 5))
            const aspect_ratio: '9:16' | '1:1' | '4:3' | '16:9' =
              /\breel|story|tiktok|insta\s*story|9\s*:\s*16|vertical/.test(txt) ? '9:16'
              : /\binsta\s*(feed|post)?|carr[ée]|square|1\s*:\s*1/.test(txt) ? '1:1'
              : /\b4\s*:\s*3|classique\b/.test(txt) ? '4:3'
              : '16:9'
            const mode: 'standard' | 'premium' | 'ultra' =
              /ultra|cin[ée]ma|broadcast|sora|sota|haute\s*qualit[ée]|tv\s*pro|professionnel|qualit[ée]\s*max/.test(txt) ? 'ultra'
              : /rapide|standard|\b(eco|pas\s*cher|low[-\s]?cost)\b|ltx/.test(txt) ? 'standard'
              : 'premium'
            const { videoAPI } = await import('../api/client')
            const res = await videoAPI.generer({
              prompt: msg, duree_s, mode, aspect_ratio,
            })
            const d = res.data as any
            const tok = localStorage.getItem('bureau_token') || ''
            const baseUrl = d.url_telechargement || ''
            const url = baseUrl + (baseUrl.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(tok)
            const yukpoTurn: ChatTurn = {
              role: 'yukpo', ts: new Date().toISOString(),
              content: `✓ Vidéo ${duree_s}s ${aspect_ratio} (${mode}, ${d.size_kb} KB) — ${d.cout_fcfa} XAF\n` +
                `[▶ Lire / Télécharger MP4](${url})`,
              intent: 'video',
              resultat: { type: 'video', data: d },
            }
            setTurns(prev => [...prev, yukpoTurn])
            return
          } catch (e: any) {
            const detail = e?.response?.data?.detail || e?.message || 'inconnue'
            const yukpoTurn: ChatTurn = {
              role: 'yukpo', ts: new Date().toISOString(),
              content: `❌ Erreur génération vidéo : ${detail}`,
              intent: 'erreur',
            }
            setTurns(prev => [...prev, yukpoTurn])
            return
          }
        }

        const slidesWebMatch = /(slides?\s*web|pr[ée]sentation\s*(web|interactive|reveal|partage|en ligne)|reveal\.?js|html\s*pr[ée]sentation)/i.test(txt)
        const landingMatch = /(landing\s*page|landing|one[-\s]?pager|page\s*(d'?accueil|produit|web\s*unique)|site\s*(web\s*)?une\s*page)/i.test(txt)
        if (slidesWebMatch || landingMatch) {
          try {
            const { slidesWebAPI, landingPageAPI } = await import('../api/client')
            const res = slidesWebMatch
              ? await slidesWebAPI.generer({ sujet: msg })
              : await landingPageAPI.generer({ sujet: msg })
            const d = res.data as any
            // Le lien markdown est rendu en <a href> sans Bearer header.
            // Backend get_current_user accepte ?token=... en query (SSE-compat).
            const tok = localStorage.getItem('bureau_token') || ''
            const baseUrl = d.url_telechargement || ''
            const url = baseUrl
              + (baseUrl.includes('?') ? '&' : '?')
              + 'token=' + encodeURIComponent(tok)
            const yukpoTurn: ChatTurn = {
              role: 'yukpo', ts: new Date().toISOString(),
              content: (slidesWebMatch ? '✓ Présentation web Reveal.js générée' : '✓ Landing page web générée') +
                ` — ${d.size_kb} KB.\n[Ouvrir dans le navigateur](${url})`,
              intent: slidesWebMatch ? 'slides_web' : 'landing_page',
              resultat: { type: slidesWebMatch ? 'slides_web' : 'landing_page', data: d },
            }
            setTurns(prev => [...prev, yukpoTurn])
            return
          } catch (_e_pw) {
            // Fallback flow normal si échec
          }
        }
      }

      // ── R1-R5 : DÉTECTION MODIFICATION INCRÉMENTALE EN PREMIER ─────────
      // Si l'user a un document précédent en session + son message classe
      // 'modification', on route vers /modifier du pipeline mémorisé au lieu
      // de regénérer from scratch. Évite perte de cohérence + coût LLM ×2.
      // Pas de fichier joint = condition requise (un fichier joint = nouvelle
      // intention obligatoire genre OCR/audio/traduction).
      if (atts.length === 0 && msg.trim()) {
        try {
          const intentRes = await bureauSessionAPI.intent(msg)
          const i = intentRes.data as {
            intent: string; pipeline: string | null;
            dernier_fichier_id: string | null; route_modifier?: string | null;
          }
          if (i.intent === 'modification' && i.route_modifier && i.dernier_fichier_id) {
            const modRes = await bureauSessionAPI.executeModifier(
              i.route_modifier, i.dernier_fichier_id, msg,
            )
            const yukpoTurn: ChatTurn = {
              role: 'yukpo', ts: new Date().toISOString(),
              content: `✓ Modification appliquée sur le document précédent (${i.pipeline}).`,
              intent: 'modification',
              resultat: { type: i.pipeline || 'document', data: modRes.data },
            }
            setTurns(prev => [...prev, yukpoTurn])
            return
          }
        } catch (_e_intent) {
          // Si /session/intent échoue → fallback flow standard
        }
      }

      // 1. Détection d'intention
      const orch = await secChatAPI.message({
        message: msg || `[${atts.map(a => a.type).join(', ')} attaché(s)]`,
        has_image: atts.some(a => a.type === 'image'),
        has_pdf: atts.some(a => a.type === 'pdf'),
        has_audio: atts.some(a => a.type === 'audio'),
        pays: 'CM', langue: 'fr',
      })
      const intent = orch.data?.intent || 'inconnu'
      const confiance = orch.data?.confiance || 0
      const suggestions = orch.data?.suggestion_questions || []

      if (intent === 'inconnu') {
        const yukpoTurn: ChatTurn = {
          role: 'yukpo', ts: new Date().toISOString(),
          content: t('chatUnifie.askClarif', "J'ai besoin d'une précision pour bien faire :") + '\n• ' + suggestions.join('\n• '),
          intent,
        }
        setTurns(prev => [...prev, yukpoTurn])
        return
      }

      // Pattern boîte noire (aligné YPro) : pas de toast intent/confiance, pas
      // de "Action exécutée: X" — l'utilisateur voit juste le résultat.
      const result = await executerSelonIntent(intent, msg, atts)

      const yukpoTurn: ChatTurn = {
        role: 'yukpo', ts: new Date().toISOString(),
        content: '', intent, resultat: result,
      }
      setTurns(prev => [...prev, yukpoTurn])
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      // Solde insuffisant (backend renvoie 402 ou code CREDITS_EPUISES) → toast
      // simple sans prix affiché, lien vers /abonnement (politique produit ferme).
      if (e?.response?.status === 402 ||
          (typeof detail === 'string' && detail.includes('CREDITS_EPUISES')) ||
          (detail && typeof detail === 'object' && detail.code === 'CREDITS_EPUISES')) {
        const yukpoTurn: ChatTurn = {
          role: 'yukpo', ts: new Date().toISOString(),
          content: '⚠️ Crédits insuffisants. [→ Recharger mon compte](/abonnement)',
          intent: 'erreur',
        }
        setTurns(prev => [...prev, yukpoTurn])
        toast.error('Crédits insuffisants. Rechargez votre compte pour continuer.', { duration: 6000 })
      } else {
        const errMsg = (typeof detail === 'string' ? detail : detail?.message) || e?.message || 'Erreur'
        const yukpoTurn: ChatTurn = {
          role: 'yukpo', ts: new Date().toISOString(),
          content: `❌ ${errMsg}`, intent: 'erreur',
        }
        setTurns(prev => [...prev, yukpoTurn])
        toast.error(errMsg)
      }
    } finally {
      setLoading(false)
    }
  }

  // Wrapper public : clic Envoyer / Entrée. Si génération en cours →
  // push dans la queue ; sinon → executerEnvoi immédiat.
  const envoyer = () => {
    if (!message.trim() && attachments.length === 0) {
      toast.error(t('chatUnifie.empty', 'Tape un message ou attache un fichier'))
      return
    }
    if (loading) {
      // Génération en cours → mise en file d'attente
      setPendingQueue(prev => [...prev, {
        message, attachments: [...attachments],
      }])
      toast.success(
        t('chatUnifie.queued',
          'Mis en file d\'attente — sera envoyé après la réponse en cours'),
        { duration: 3000 },
      )
    } else {
      executerEnvoi(message, attachments)
    }
    // Dans les 2 cas, on libère le textarea + attachments pour le prochain input
    setMessage(''); setAttachments([])
  }

  // ─── Rendu visuel d'un résultat selon son type ────────────────────────
  const RenduResultat = ({ result }: { result: any }) => {
    if (!result) return null
    const t_ = result.type
    if (t_ === 'document' || t_ === 'redaction') {
      // Backend /bureau/redaction/generer renvoie {titre, contenu_markdown,
      // type_doc, prix_fcfa, nb_mots, a_fichier_word, fichier_id}.
      const titre = result.data?.titre || 'Document'
      const md = result.data?.contenu_markdown || ''
      const wordB64 = result.data?.word_base64
      return (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-amber-900">📄 {titre}</p>
          {md && (
            <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto bg-white rounded p-2 border border-amber-100">
              {md.slice(0, 2000)}
            </pre>
          )}
          {wordB64 && (
            <button onClick={() => b64download(wordB64, `${titre.replace(/\s+/g, '_')}.docx`,
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document')}
              className="inline-flex items-center gap-1 bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg">
              <Download size={12} /> Télécharger .docx
            </button>
          )}
        </div>
      )
    }
    if (t_ === 'ocr') {
      // Backend /bureau/ocr/{scanner|manuscrit} renvoie {texte_brut,
      // texte_structure, type_document, confiance, fichier_id, word_base64}.
      const texte = result.data?.texte_structure || result.data?.texte_brut || ''
      const wordB64 = result.data?.word_base64
      const conf = result.data?.confiance
      return (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-blue-900">
            🔍 Texte extrait (OCR){typeof conf === 'number' ? ` — ${Math.round(conf * 100)}%` : ''}
          </p>
          <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto bg-white rounded p-2 border border-blue-100">
            {texte.slice(0, 2000)}
          </pre>
          {wordB64 && (
            <button onClick={() => b64download(wordB64, 'document-ocr.docx',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document')}
              className="inline-flex items-center gap-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg">
              <Download size={12} /> Télécharger .docx
            </button>
          )}
        </div>
      )
    }
    if (t_ === 'audio') {
      // Backend /bureau/audio/transcrire renvoie {transcription_brute,
      // document_formate, type_document, duree_secondes, fichier_id, word_base64}.
      const docFormate = result.data?.document_formate || ''
      const brut = result.data?.transcription_brute || ''
      const wordB64 = result.data?.word_base64
      return (
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-purple-900">🎤 Transcription</p>
          <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto bg-white rounded p-2 border border-purple-100">
            {(docFormate || brut).slice(0, 2000)}
          </pre>
          {wordB64 && (
            <button onClick={() => b64download(wordB64, 'transcription.docx',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document')}
              className="inline-flex items-center gap-1 bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg">
              <Download size={12} /> Télécharger .docx
            </button>
          )}
          {brut && docFormate && brut !== docFormate && (
            <details className="text-[10px] text-gray-500 mt-1">
              <summary className="cursor-pointer">Transcription brute</summary>
              <pre className="text-[10px] text-gray-600 whitespace-pre-wrap mt-1 p-1 italic">{brut.slice(0, 1500)}</pre>
            </details>
          )}
        </div>
      )
    }
    if (t_ === 'visuel_mono') {
      const png = result.data?.preview_png_base64 || result.data?.png_base64
      return (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-emerald-900">🎨 Visuel généré</p>
          {png && <img src={`data:image/png;base64,${png}`} alt="preview"
            className="max-h-64 rounded border border-emerald-100" />}
        </div>
      )
    }
    if (t_ === 'designer_pro') {
      const png = result.data?.pages_png_base64?.[0]
      return (
        <div className="bg-fuchsia-50 border border-fuchsia-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-fuchsia-900">
            🌟 Designer Pro {result.sub_intent === 'modification' ? '(modifié)' : '(créé)'} :
            {' '}{result.data?.projet?.titre}
          </p>
          {png && <img src={`data:image/png;base64,${png}`} alt="page 1"
            className="max-h-64 rounded border border-fuchsia-100" />}
          <p className="text-[10px] text-fuchsia-700">
            {result.data?.meta?.nombre_pages} page(s) — continue à taper pour modifier !
          </p>
        </div>
      )
    }
    if (t_ === 'traduction') {
      // Backend /bureau/traduction/texte renvoie {texte_traduit,
      // nb_mots_source, nb_mots_cible, langue_source, langue_cible, fichier_id}.
      const traduit = result.data?.texte_traduit || ''
      const lc = result.data?.langue_cible || ''
      return (
        <div className="bg-cyan-50 border border-cyan-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-cyan-900">
            🌍 Traduction{lc ? ` → ${lc.toUpperCase()}` : ''}
          </p>
          <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto bg-white rounded p-2 border border-cyan-100">
            {traduit.slice(0, 2000)}
          </pre>
          {result.data?.fichier_id && (
            <button onClick={() => telechargerTraductionDocx(result.data.fichier_id)}
              className="inline-flex items-center gap-1 bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg">
              <Download size={12} /> Télécharger .docx
            </button>
          )}
        </div>
      )
    }
    if (t_ === 'traduction_fichier') {
      const lc = result.data?.langue_cible || ''
      return (
        <div className="bg-cyan-50 border border-cyan-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-cyan-900">
            🌍 Fichier traduit{lc ? ` → ${lc.toUpperCase()}` : ''}
          </p>
          {result.data?.texte_traduit && (
            <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-48 overflow-auto bg-white rounded p-2 border border-cyan-100">
              {result.data.texte_traduit.slice(0, 1500)}
            </pre>
          )}
          {result.data?.fichier_id && (
            <button onClick={() => telechargerTraductionDocx(result.data.fichier_id)}
              className="inline-flex items-center gap-1 bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg">
              <Download size={12} /> Télécharger la traduction
            </button>
          )}
        </div>
      )
    }
    return null
  }

  // Helper auth-aware : récupère le DOCX traduit via l'API client (qui injecte
  // le Bearer token) puis déclenche un download depuis le Blob obtenu.
  const telechargerTraductionDocx = async (fichierId: string) => {
    try {
      const r = await traductionAPI.telecharger(fichierId)
      const url = URL.createObjectURL(r.data as Blob)
      const a = document.createElement('a')
      a.href = url; a.download = fichierId.split('/').pop() || 'traduction.docx'
      a.click(); URL.revokeObjectURL(url)
    } catch (e: any) {
      toast.error(e?.message || 'Téléchargement échoué')
    }
  }

  // Re-injecte une suggestion dans le textarea + relance (UX YPro)
  const onPickSuggestion = (prompt: string) => {
    setMessage(prompt)
    setTimeout(() => envoyer(), 0)
  }

  return (
    <div className="flex flex-col h-full max-h-[85vh]">
      {/* ── En-tête compact ────────────────────────────────────────── */}
      <div className="flex items-center gap-2 mb-3 px-1">
        <Sparkles size={16} className="text-amber-600 flex-shrink-0" />
        <p className="text-sm font-semibold text-amber-900">
          {t('chatUnifie.title', 'Chat Yukpo Secrétariat')}
        </p>
        <span className="text-[11px] text-amber-700/80 hidden sm:inline">
          · {t('chatUnifie.subtitle',
            'tape ton besoin, attache image/PDF/audio si nécessaire — Yukpo détecte et exécute')}
        </span>
      </div>

      {/* ── Historique ──────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-3 pr-1">
        {turns.length === 0 && (
          <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
            <div className="text-3xl mb-3">👋</div>
            <p className="text-sm text-gray-600 mb-1 text-center">
              {t('chatUnifie.welcome', 'Décris ton besoin')}
            </p>
            <p className="text-[11px] text-gray-400 mb-6 text-center max-w-md">
              {t('chatUnifie.welcomeSub',
                'Quelques choses que Yukpo sait faire à partir d\'un simple message')}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl w-full">
              {([
                { icon: '✍️', label: t('chatUnifie.ex.redaction',  'Rédiger une lettre, un courrier, une note ou un contrat') },
                { icon: '📷', label: t('chatUnifie.ex.ocr',        'Extraire le texte d\'une photo ou d\'un document scanné') },
                { icon: '🎤', label: t('chatUnifie.ex.audio',      'Transcrire automatiquement une note vocale ou un enregistrement') },
                { icon: '🎨', label: t('chatUnifie.ex.visuel',     'Créer une carte de visite, un flyer, une affiche imprimable') },
                { icon: '📖', label: t('chatUnifie.ex.livret',     'Concevoir un livret, faire-part ou brochure multi-pages') },
                { icon: '🌍', label: t('chatUnifie.ex.traduction', 'Traduire un texte ou un document dans une autre langue') },
              ] as { icon: string; label: string }[]).map((ex, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50/60 border border-amber-100 text-[11px] text-amber-900"
                >
                  <span className="text-base leading-none mt-0.5">{ex.icon}</span>
                  <span className="leading-snug">{ex.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, i) => (
          <div key={i} className={`flex ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-3 py-2 ${
              turn.role === 'user'
                ? 'bg-amber-600 text-white'
                : 'bg-white border border-gray-200 text-gray-800'
            }`}>
              {turn.content && <p className="text-sm whitespace-pre-wrap">{turn.content}</p>}
              {turn.attachments && turn.attachments.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {turn.attachments.map((a, j) => (
                    <span key={j} className="text-[10px] bg-white/20 rounded px-1.5 py-0.5">
                      {a.type === 'image' && '📷'}{a.type === 'audio' && '🎤'}
                      {a.type === 'pdf' && '📄'}{a.type === 'autre' && '📎'} {a.file.name.slice(0, 30)}
                    </span>
                  ))}
                </div>
              )}
              {turn.role === 'yukpo' && turn.resultat && (
                <>
                  <RenduResultat result={turn.resultat} />
                  <SuggestionsChips
                    suggestions={turn.resultat.data?.suggestions as Suggestion[] | undefined}
                    onPick={onPickSuggestion}
                  />
                </>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl px-3 py-2 text-xs text-gray-500 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" /> Yukpo réfléchit…
            </div>
          </div>
        )}
      </div>

      {/* ── Queue file d'attente (BATCH-4) ──────────────────────────── */}
      {pendingQueue.length > 0 && (
        <div className="mb-2 px-2 py-1.5 bg-blue-50 border border-blue-200 rounded-lg text-xs">
          <p className="text-blue-900 font-medium flex items-center gap-1.5">
            <ListPlus size={13} />
            {pendingQueue.length} {pendingQueue.length === 1 ? 'message en attente' : 'messages en attente'}
            <span className="text-blue-700 font-normal ml-1">
              — sera envoyé{pendingQueue.length > 1 ? 's' : ''} dès la fin de la réponse en cours
            </span>
          </p>
          <ul className="mt-1 space-y-0.5">
            {pendingQueue.map((p, i) => (
              <li key={i} className="flex items-center gap-2 text-blue-800">
                <span className="text-blue-500 font-mono">#{i + 1}</span>
                <span className="flex-1 truncate">
                  {p.message || `[${p.attachments.map(a => a.type).join(', ')}]`}
                  {p.attachments.length > 0 && p.message && (
                    <span className="text-blue-600 ml-1">
                      (+{p.attachments.length} fichier{p.attachments.length > 1 ? 's' : ''})
                    </span>
                  )}
                </span>
                <button onClick={() => retirerDeLaQueue(i)}
                  className="text-red-500 hover:text-red-700" title="Retirer de la file">
                  <X size={11} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Attachments preview ─────────────────────────────────────── */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 px-1">
          {attachments.map((a, i) => (
            <div key={i} className="flex items-center gap-1 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1 text-[11px]">
              {a.type === 'image' && a.preview && (
                <img src={a.preview} alt="" className="w-8 h-8 object-cover rounded" />
              )}
              {a.type === 'image' && !a.preview && <ImageIcon size={14} />}
              {a.type === 'audio' && <Mic size={14} className="text-purple-600" />}
              {a.type === 'pdf' && <FileText size={14} className="text-blue-600" />}
              <span className="max-w-[150px] truncate">{a.file.name}</span>
              <button onClick={() => retirerAttachment(i)} className="text-red-500 hover:text-red-700">
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Composer ─────────────────────────────────────────────────── */}
      <div className="bg-white border border-gray-300 rounded-2xl p-2 flex items-end gap-2 shadow-sm">
        <input ref={fileRef} type="file"
          accept=".pdf,.doc,.docx,.odt,.rtf,.xls,.xlsx,.ods,.csv,.tsv,.ppt,.pptx,.odp,.txt,.md,image/*,.heic,.heif,audio/*,.zip"
          onChange={e => ajouterFichier(e.target.files?.[0] || null)}
          className="hidden" />
        <input ref={audioRef} type="file" accept="audio/*"
          onChange={e => ajouterFichier(e.target.files?.[0] || null)}
          className="hidden" />
        <button onClick={() => fileRef.current?.click()} type="button"
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"
          title={t('chatUnifie.attachFile', 'Attacher fichier (image/PDF/Word/PPT/Excel/audio)')}>
          <Paperclip size={18} />
        </button>
        <button onClick={recording ? arreterEnregistrement : demarrerEnregistrement}
          type="button"
          className={`p-2 rounded-lg ${recording ? 'bg-red-100 text-red-600 animate-pulse' : 'hover:bg-gray-100 text-gray-600'}`}
          title={recording ? t('chatUnifie.stopRecord', 'Arrêter l\'enregistrement') : t('chatUnifie.startRecord', 'Enregistrer une note vocale')}>
          <Mic size={18} />
        </button>
        <button onClick={demarrerCamera} type="button"
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"
          title={t('chatUnifie.cameraScan', 'Scanner avec la caméra (document, ordonnance, carte)')}>
          <Camera size={18} />
        </button>
        <textarea
          value={message} onChange={e => setMessage(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              envoyer()
            }
          }}
          placeholder={t('chatUnifie.placeholder', 'Décris ton besoin… (Entrée pour envoyer)')}
          rows={1}
          className="flex-1 resize-none text-sm py-2 px-2 outline-none max-h-32" />
        {/* BATCH-4 — bouton Envoyer SAUF disabled si génération en cours :
            on permet d'envoyer (= mettre en queue). Disabled UNIQUEMENT si
            rien à envoyer (message vide ET pas d'attachment). Visuel adapté :
            icône Send normale OU ListPlus si génération en cours. */}
        <button onClick={envoyer}
          disabled={!message.trim() && attachments.length === 0}
          title={loading
            ? t('chatUnifie.queueAdd', 'Mettre en file (envoi après la réponse en cours)')
            : t('chatUnifie.send', 'Envoyer')}
          className={`disabled:opacity-50 text-white p-2 rounded-lg transition-colors ${
            loading ? 'bg-amber-500 hover:bg-amber-600' : 'bg-amber-600 hover:bg-amber-700'
          }`}>
          {loading ? <ListPlus size={18} /> : <Send size={18} />}
        </button>
      </div>

      {/* ── Modal Camera (scan document) ─────────────────────────────── */}
      {cameraOpen && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-gray-300 rounded-2xl p-4 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-gray-900 font-semibold text-sm flex items-center gap-2">
                <Camera size={16} className="text-amber-600" />
                {t('chatUnifie.cameraScan', 'Scanner avec la caméra')}
              </h3>
              <button onClick={fermerCamera} className="p-1 text-gray-400 hover:text-gray-700"
                aria-label="Fermer">
                <X size={16} />
              </button>
            </div>
            <video ref={videoRef} autoPlay playsInline muted
              className="w-full rounded-lg mb-3 bg-black aspect-video object-cover" />
            <canvas ref={canvasRef} className="hidden" />
            <div className="flex gap-2">
              <button onClick={fermerCamera}
                className="flex-1 px-3 py-2 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 text-sm">
                {t('common.cancel', 'Annuler')}
              </button>
              <button onClick={capturerPhoto}
                className="flex-1 px-3 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-medium flex items-center justify-center gap-2 text-sm">
                <Camera size={16} /> {t('chatUnifie.takePhoto', 'Capturer')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
