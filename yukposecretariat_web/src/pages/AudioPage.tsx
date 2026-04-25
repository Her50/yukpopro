import { useState, useRef } from 'react'
import { Mic, Upload, Download, Loader2, Square, Circle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { audioAPI } from '../api/client'
import { DemoBanner } from '../components/DemoBanner'
import { CountryPicker } from '../components/CountryPicker'
import toast from 'react-hot-toast'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useLongOps, useLongOpField } from '../store/longOpsStore'

type AudioResult = {
  transcription_brute: string; document_formate: string; duree_secondes?: number;
  word_base64?: string; type_document: string
}

export default function AudioPage() {
  const [fichier, setFichier] = useLongOpField<File | null>('audio', 'fichier', null)
  const [typeDoc, setTypeDoc] = useLongOpField<string>('audio', 'typeDoc', 'dictee')
  const [pays, setPays] = useLongOpField<string>('audio', 'pays', 'CM')
  const [contexte, setContexte] = useLongOpField<string>('audio', 'contexte', '')
  const loading = useLongOps((s) => s.loading.audio)
  const resultat = useLongOps((s) => s.resultats.audio) as AudioResult | null
  const setResultat = (r: AudioResult | null) => useLongOps.getState().setResultat('audio', r)
  const runOp = useLongOps((s) => s.run)
  const [recording, setRecording] = useState(false)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: typesData } = useQuery({
    queryKey: ['audio-types'],
    queryFn: () => audioAPI.types().then(r => r.data),
  })
  const types: { cle: string; label: string }[] = typesData?.types ?? []

  const demarrerEnregistrement = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      chunksRef.current = []
      mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setFichier(new File([blob], 'dictee.webm', { type: 'audio/webm' }))
        stream.getTracks().forEach(t => t.stop())
      }
      mr.start()
      mediaRef.current = mr
      setRecording(true)
    } catch {
      toast.error('Microphone non accessible')
    }
  }

  const arreterEnregistrement = () => {
    mediaRef.current?.stop()
    setRecording(false)
  }

  const transcrire = async () => {
    if (!fichier) { toast.error('Sélectionnez ou enregistrez un audio'); return }
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
      toast.success('Transcription terminée !')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Erreur de transcription')
    }
  }

  const telechargerWord = () => {
    if (!resultat?.word_base64) return
    const bytes = atob(resultat.word_base64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const blob = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'transcription.docx'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Mic className="text-purple-600" size={24} />
          Audio → Document
        </h1>
        <p className="text-gray-500 text-sm mt-1">Dictez ou importez un audio pour générer un document Word</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        {/* Enregistrement */}
        <div className="flex gap-3">
          <button
            onClick={recording ? arreterEnregistrement : demarrerEnregistrement}
            className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-colors ${
              recording
                ? 'bg-red-500 hover:bg-red-600 text-white'
                : 'bg-purple-600 hover:bg-purple-700 text-white'
            }`}
          >
            {recording ? <><Square size={18} /> Arrêter</> : <><Circle size={18} className="fill-white" /> Dicter</>}
          </button>
          <button
            onClick={() => inputRef.current?.click()}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 transition-colors"
          >
            <Upload size={18} /> Importer
          </button>
          <input ref={inputRef} type="file" accept="audio/*" className="hidden"
            onChange={e => { if (e.target.files?.[0]) setFichier(e.target.files[0]) }} />
        </div>

        {fichier && (
          <div className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2 flex items-center gap-2">
            <Mic size={14} className="text-purple-500" />
            {fichier.name} — {(fichier.size / 1024).toFixed(0)} Ko
          </div>
        )}

        {recording && (
          <div className="flex items-center gap-2 text-red-500 text-sm animate-pulse">
            <Circle size={10} className="fill-red-500" /> Enregistrement en cours…
          </div>
        )}

        {/* Type de document */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">Type de document à produire</label>
          <div className="flex flex-wrap gap-2">
            {types.map(t => (
              <button key={t.cle} onClick={() => setTypeDoc(t.cle)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${typeDoc === t.cle ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-600'}`}
              >{t.label}</button>
            ))}
          </div>
        </div>

        {/* Pays */}
        <CountryPicker label="Pays" value={pays} onChange={setPays} />

        {/* Contexte */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Contexte <span className="font-normal text-gray-400">(optionnel)</span>
          </label>
          <textarea
            value={contexte}
            onChange={e => setContexte(e.target.value)}
            rows={2}
            placeholder="Participants, objet de la réunion, date..."
            className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
          />
        </div>

        <button
          onClick={transcrire}
          disabled={loading || !fichier}
          className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Mic size={18} />}
          {loading ? 'Transcription en cours (peut prendre 30s)…' : 'Transcrire et formater'}
        </button>
      </div>

      {/* Résultat */}
      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded-lg">{resultat.type_document}</span>
              {resultat.duree_secondes && (
                <span className="ml-2 text-xs text-gray-400">{Math.round(resultat.duree_secondes)}s audio</span>
              )}
            </div>
            {resultat.word_base64 && (
              <button onClick={telechargerWord}
                className="flex items-center gap-1.5 bg-purple-600 text-white text-xs font-medium px-3 py-2 rounded-xl">
                <Download size={14} /> .docx
              </button>
            )}
          </div>

          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Document formaté</h3>
            <div className="prose prose-sm max-w-none text-gray-700">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{resultat.document_formate}</ReactMarkdown>
            </div>
          </div>

          <details className="border-t border-gray-100 pt-3">
            <summary className="text-xs text-gray-400 cursor-pointer">Transcription brute</summary>
            <p className="text-xs text-gray-500 mt-2 italic">{resultat.transcription_brute}</p>
          </details>
        </div>
      )}
    </div>
  )
}
