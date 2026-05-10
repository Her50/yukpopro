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
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Loader2, Sparkles, Paperclip, Mic, Image as ImageIcon,
  FileText, Send, X, Download,
} from 'lucide-react'
import toast from 'react-hot-toast'
import {
  secChatAPI, redactionAPI, ocrAPI, audioAPI, traductionAPI, infographieAPI,
  infographieProAPI,
} from '../api/client'

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
        const r = await redactionAPI.generer({
          type_doc: 'auto', brief: msg, pays: 'CM', langue: 'fr',
        })
        return { type: 'document', data: r.data }
      }
      case 'ocr_image':
      case 'ocr_manuscrit': {
        if (!imageAtt) throw new Error('Image attendue mais absente')
        const fd = new FormData()
        fd.append('fichier', imageAtt.file)
        const r = intent === 'ocr_manuscrit'
          ? await ocrAPI.manuscrit(fd) : await ocrAPI.scanner(fd)
        return { type: 'ocr', data: r.data }
      }
      case 'audio_transcrire': {
        if (!audioAtt) throw new Error('Audio attendu mais absent')
        const fd = new FormData()
        fd.append('audio', audioAtt.file)
        fd.append('type_doc', 'transcription')
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
        fd.append('langue_cible', 'en')
        const r = await traductionAPI.traduireFichier(fd)
        return { type: 'traduction_fichier', data: r.data }
      }
      default:
        return { type: 'inconnu', data: null }
    }
  }

  const envoyer = async () => {
    if (!message.trim() && attachments.length === 0) {
      toast.error(t('chatUnifie.empty', 'Tape un message ou attache un fichier'))
      return
    }
    const userTurn: ChatTurn = {
      role: 'user', ts: new Date().toISOString(),
      content: message, attachments: [...attachments],
    }
    setTurns(prev => [...prev, userTurn])
    setLoading(true)

    try {
      // 1. Détection d'intention
      const orch = await secChatAPI.message({
        message: message || `[${attachments.map(a => a.type).join(', ')} attaché(s)]`,
        has_image: attachments.some(a => a.type === 'image'),
        has_pdf: attachments.some(a => a.type === 'pdf'),
        has_audio: attachments.some(a => a.type === 'audio'),
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
        setMessage(''); setAttachments([])
        return
      }

      toast.success(`${t('chatUnifie.intentDetected', 'Détecté')} : ${intent} (${Math.round(confiance * 100)}%)`)

      // 2. Exécution selon intent
      const result = await executerSelonIntent(intent, message, attachments)

      const yukpoTurn: ChatTurn = {
        role: 'yukpo', ts: new Date().toISOString(),
        content: `${t('chatUnifie.actionDone', 'Action exécutée')} : ${intent}`,
        intent, resultat: result,
      }
      setTurns(prev => [...prev, yukpoTurn])
      setMessage(''); setAttachments([])
    } catch (e: any) {
      const errMsg = e?.response?.data?.detail || e?.message || 'Erreur'
      const yukpoTurn: ChatTurn = {
        role: 'yukpo', ts: new Date().toISOString(),
        content: `❌ ${errMsg}`, intent: 'erreur',
      }
      setTurns(prev => [...prev, yukpoTurn])
      toast.error(errMsg)
    } finally {
      setLoading(false)
    }
  }

  // ─── Rendu visuel d'un résultat selon son type ────────────────────────
  const RenduResultat = ({ result }: { result: any }) => {
    if (!result) return null
    const t_ = result.type
    if (t_ === 'document' || t_ === 'redaction') {
      return (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-amber-900">📄 Document rédigé</p>
          {result.data?.texte_genere && (
            <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto bg-white rounded p-2 border border-amber-100">
              {result.data.texte_genere.slice(0, 2000)}
            </pre>
          )}
          {result.data?.fichier_id && (
            <a href={`/api/v1/bureau/redaction/fichier/${result.data.fichier_id}`}
              className="text-xs text-amber-700 hover:underline inline-flex items-center gap-1">
              <Download size={12} /> Télécharger
            </a>
          )}
        </div>
      )
    }
    if (t_ === 'ocr') {
      return (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-blue-900">🔍 Texte extrait (OCR)</p>
          <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto bg-white rounded p-2 border border-blue-100">
            {(result.data?.texte_extrait || result.data?.texte || '').slice(0, 2000)}
          </pre>
        </div>
      )
    }
    if (t_ === 'audio') {
      return (
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-purple-900">🎤 Transcription</p>
          <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto bg-white rounded p-2 border border-purple-100">
            {(result.data?.transcription || result.data?.texte || '').slice(0, 2000)}
          </pre>
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
      return (
        <div className="bg-cyan-50 border border-cyan-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-cyan-900">🌍 Traduction</p>
          <pre className="text-[11px] text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto bg-white rounded p-2 border border-cyan-100">
            {(result.data?.traduction || result.data?.texte || '').slice(0, 2000)}
          </pre>
        </div>
      )
    }
    if (t_ === 'traduction_fichier') {
      return (
        <div className="bg-cyan-50 border border-cyan-200 rounded-xl p-3 mt-2 space-y-1">
          <p className="text-xs font-bold text-cyan-900">🌍 Fichier traduit</p>
          {result.data?.fichier_id && (
            <a href={`/api/v1/bureau/traduction/fichier/${result.data.fichier_id}`}
              className="text-xs text-cyan-700 hover:underline inline-flex items-center gap-1">
              <Download size={12} /> Télécharger la traduction
            </a>
          )}
        </div>
      )
    }
    return null
  }

  return (
    <div className="flex flex-col h-full max-h-[85vh]">
      {/* ── En-tête ─────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-4 mb-3">
        <p className="text-sm font-bold text-amber-900 flex items-center gap-2">
          <Sparkles size={15} className="text-amber-600" />
          {t('chatUnifie.title', 'Chat Yukpo Secrétariat')}
        </p>
        <p className="text-[11px] text-amber-800 mt-1">
          {t('chatUnifie.subtitle',
            "Tape ton besoin + attache (optionnel) image/PDF/audio. " +
            "Yukpo détecte automatiquement et fait le reste : rédaction, OCR, transcription, " +
            "infographie, traduction. Plus besoin d'onglets.")}
        </p>
      </div>

      {/* ── Historique ──────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-3 pr-1">
        {turns.length === 0 && (
          <div className="text-center text-xs text-gray-400 py-12">
            {t('chatUnifie.welcome',
              "👋 Décris ton besoin… Quelques exemples :")}
            <ul className="mt-3 space-y-1 text-left max-w-md mx-auto text-[11px]">
              <li>• "Rédige une lettre de relance pour facture impayée à M. NGONO"</li>
              <li>• 📷 attache une photo + "Extrais le texte de cette ordonnance"</li>
              <li>• 🎤 enregistre une note vocale → transcription auto</li>
              <li>• "Carte de visite pour Jean MBARGA, avocat à Yaoundé"</li>
              <li>• "Livret faire-part de mariage 4 pages, format A5"</li>
              <li>• "Traduis ce contrat en anglais" + 📎 PDF</li>
            </ul>
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
              {turn.role === 'yukpo' && turn.resultat && <RenduResultat result={turn.resultat} />}
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
        <input ref={fileRef} type="file" accept="image/*,.pdf,.docx,.xlsx,.txt"
          onChange={e => ajouterFichier(e.target.files?.[0] || null)}
          className="hidden" />
        <input ref={audioRef} type="file" accept="audio/*"
          onChange={e => ajouterFichier(e.target.files?.[0] || null)}
          className="hidden" />
        <button onClick={() => fileRef.current?.click()} type="button"
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"
          title={t('chatUnifie.attachFile', 'Attacher fichier (image/PDF/DOCX)')}>
          <Paperclip size={18} />
        </button>
        <button onClick={recording ? arreterEnregistrement : demarrerEnregistrement}
          type="button"
          className={`p-2 rounded-lg ${recording ? 'bg-red-100 text-red-600 animate-pulse' : 'hover:bg-gray-100 text-gray-600'}`}
          title={recording ? t('chatUnifie.stopRecord', 'Arrêter l\'enregistrement') : t('chatUnifie.startRecord', 'Enregistrer une note vocale')}>
          <Mic size={18} />
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
        <button onClick={envoyer} disabled={loading || (!message.trim() && attachments.length === 0)}
          className="bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white p-2 rounded-lg transition-colors">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
        </button>
      </div>
    </div>
  )
}
