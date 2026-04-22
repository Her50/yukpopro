/**
 * QuestionCard — Demande de complément d'information par l'agent.
 *
 * L'agent se met en pause et pose une question précise.
 * L'utilisateur répond → l'agent reprend où il s'était arrêté.
 *
 * Supporte 5 types de réponse : texte libre, choix multiple, oui/non, nombre, date.
 * Affiche l'historique des questions/réponses précédentes dans cette session.
 * Compatible agents autonomes (schema_si, meta_factory) avec badge [SYSTÈME].
 */
import { useState, useRef, useCallback } from 'react'
import {
  QuestionMarkCircleIcon,
  PaperAirplaneIcon as Send,
  ArrowPathIcon as RotateCcw,
  CheckCircleIcon,
  CpuChipIcon,
  ShieldCheckIcon,
  PhotoIcon,
  DocumentIcon,
  XMarkIcon,
  ArrowUpTrayIcon,
} from '@heroicons/react/24/outline'
import type { ValidationItem } from '../../store/approvalStore'
import { useApprovalStore } from '../../store/approvalStore'

interface MediaPreview {
  file: File
  url:  string
  type: 'image' | 'pdf' | 'autre'
}

interface Props {
  item: ValidationItem
  onRefresh: () => void
  /** Numéro de la question dans la session (pour afficher "Question 2/?" ) */
  numeroQuestion?: number
  /** Historique des échanges précédents pour montrer le fil */
  historique?: { question: string; reponse: string }[]
}

const API = import.meta.env.VITE_API_URL ?? ''

const AGENTS_SYSTEME = ['schema_si', 'meta_factory']

/** Taille max par fichier : 10 Mo */
const MAX_TAILLE_MO = 10
const FORMATS_IMAGES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
const FORMATS_DOCS   = ['application/pdf']

export function QuestionCard({ item, onRefresh, numeroQuestion, historique = [] }: Props) {
  const [reponse, setReponse]         = useState('')
  const [medias, setMedias]           = useState<MediaPreview[]>([])
  const [dragOver, setDragOver]       = useState(false)
  const [erreurMedia, setErreurMedia] = useState('')
  const [chargement, setChargement]   = useState(false)
  const [reprise, setReprise]         = useState<{ statut: string; resume: string } | null>(null)
  const { mettreAJourItem }           = useApprovalStore()
  const inputFileRef                  = useRef<HTMLInputElement>(null)

  const question      = item.question        ?? item.description
  const contexteQ     = item.contexte_question ?? ''
  const choix         = item.choix_possibles ?? []
  const typeReponse   = item.type_reponse    ?? 'texte_libre'
  const agentType     = (item.donnees?.agent_type as string) ?? ''
  const estSysteme    = AGENTS_SYSTEME.includes(agentType)
  const nbImgsMax     = (item as any).nombre_images_max ?? (typeReponse === 'images' ? 5 : 1)
  const formatsAccept = (item as any).formats_acceptes ?? ['jpg', 'png', 'pdf']
  const estMedia      = typeReponse === 'image' || typeReponse === 'images'

  // ── Gestion des fichiers ──────────────────────────────────────────────────
  const ajouterFichiers = useCallback((fichiers: File[]) => {
    setErreurMedia('')
    const nouveaux: MediaPreview[] = []
    for (const f of fichiers) {
      if (medias.length + nouveaux.length >= nbImgsMax) {
        setErreurMedia(`Maximum ${nbImgsMax} fichier(s) autorisé(s)`)
        break
      }
      if (f.size > MAX_TAILLE_MO * 1024 * 1024) {
        setErreurMedia(`${f.name} dépasse ${MAX_TAILLE_MO} Mo`)
        continue
      }
      const estImg = FORMATS_IMAGES.includes(f.type)
      const estPdf = FORMATS_DOCS.includes(f.type)
      if (!estImg && !estPdf) {
        setErreurMedia(`Format non supporté : ${f.name} (JPG, PNG, PDF uniquement)`)
        continue
      }
      nouveaux.push({
        file: f,
        url:  URL.createObjectURL(f),
        type: estImg ? 'image' : estPdf ? 'pdf' : 'autre',
      })
    }
    setMedias((prev) => [...prev, ...nouveaux])
  }, [medias.length, nbImgsMax])

  const supprimerMedia = (idx: number) => {
    setMedias((prev) => {
      URL.revokeObjectURL(prev[idx].url)
      return prev.filter((_, i) => i !== idx)
    })
    setErreurMedia('')
  }

  const peutEnvoyer = () => {
    if (chargement || reprise) return false
    if (estMedia) return medias.length > 0  // au moins 1 média requis
    if (typeReponse === 'oui_non')        return reponse === 'Oui' || reponse === 'Non'
    if (typeReponse === 'choix_multiple') return choix.length > 0 ? choix.includes(reponse) : reponse.trim().length > 0
    return reponse.trim().length > 0
  }

  const envoyer = async () => {
    if (!peutEnvoyer()) return
    setChargement(true)
    try {
      const token = localStorage.getItem('access_token') || ''

      let res: Response
      if (estMedia && medias.length > 0) {
        // Multipart avec fichiers
        const form = new FormData()
        form.append('reponse', reponse.trim() || `${medias.length} fichier(s) fourni(s)`)
        for (const m of medias) form.append('medias', m.file)
        res = await fetch(`${API}/api/v1/agent/repondre/${item.id}/medias`, {
          method:  'POST',
          headers: { Authorization: `Bearer ${token}` },
          body:    form,
        })
      } else {
        res = await fetch(`${API}/api/v1/agent/repondre/${item.id}`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body:    JSON.stringify({ reponse: reponse.trim() }),
        })
      }

      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      mettreAJourItem(item.id, { statut: 'approuve', commentaire: reponse })
      if (data.reprise) {
        setReprise({ statut: data.reprise.statut, resume: data.reprise.resume })
      }
      onRefresh()
    } catch (err) {
      console.error('[QuestionCard] Erreur:', err)
    } finally {
      setChargement(false)
    }
  }

  return (
    <div className={`rounded-xl border-2 shadow-sm overflow-hidden bg-white ${
      estSysteme ? 'border-purple-200' : 'border-blue-200'
    }`}>

      {/* ── Historique questions précédentes (fil de conversation) ── */}
      {historique.length > 0 && (
        <div className="px-4 pt-3 pb-2 border-b border-gray-100 space-y-2">
          {historique.map((h, i) => (
            <div key={i} className="space-y-1">
              <div className="flex items-start gap-2">
                <QuestionMarkCircleIcon className="w-3.5 h-3.5 text-blue-400 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-gray-500 italic">{h.question}</p>
              </div>
              <div className="flex items-start gap-2 ml-5">
                <span className="text-xs text-green-600 font-medium">↳</span>
                <p className="text-xs text-gray-700 font-medium">{h.reponse}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── En-tête ── */}
      <div className={`flex items-start gap-3 px-4 py-3 ${
        estSysteme
          ? 'bg-gradient-to-r from-purple-50 to-indigo-50'
          : 'bg-gradient-to-r from-blue-50 to-sky-50'
      }`}>
        <div
          className="mt-0.5 w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm"
          style={{ background: estSysteme
            ? 'linear-gradient(135deg, #7c3aed, #4f46e5)'
            : 'linear-gradient(135deg, #0054A6, #00B0F0)'
          }}
        >
          {estSysteme
            ? <CpuChipIcon className="w-4 h-4 text-white" />
            : <QuestionMarkCircleIcon className="w-4 h-4 text-white" />
          }
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {estSysteme ? (
              <span className="text-xs font-bold uppercase tracking-wide text-purple-700 flex items-center gap-1">
                <ShieldCheckIcon className="w-3 h-3" />
                Question système Yukpo
              </span>
            ) : (
              <span className="text-xs font-bold uppercase tracking-wide text-blue-600">
                Complément d'information requis
              </span>
            )}
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              estSysteme ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'
            }`}>
              Agent en pause
            </span>
            {numeroQuestion && numeroQuestion > 1 && (
              <span className="text-xs text-gray-400 ml-auto">
                Question {numeroQuestion}
              </span>
            )}
          </div>

          <p className="text-sm font-semibold text-gray-800 leading-snug">{question}</p>

          {contexteQ && (
            <p className="text-xs text-gray-500 mt-1.5 leading-relaxed italic border-l-2 border-blue-200 pl-2">
              {contexteQ}
            </p>
          )}
        </div>
      </div>

      {/* ── Zone de réponse ── */}
      {item.statut === 'en_attente' && !reprise && (
        <div className="px-4 py-3 space-y-3">

          {/* OUI / NON */}
          {typeReponse === 'oui_non' && (
            <div className="flex gap-2">
              {(['Oui', 'Non'] as const).map((opt) => (
                <button
                  key={opt}
                  onClick={() => setReponse(opt)}
                  className={`flex-1 py-2.5 rounded-xl text-sm font-bold border-2 transition-all ${
                    reponse === opt
                      ? opt === 'Oui'
                        ? 'bg-green-600 border-green-600 text-white shadow-sm'
                        : 'bg-red-600 border-red-600 text-white shadow-sm'
                      : 'border-gray-200 text-gray-600 hover:border-blue-300 bg-white'
                  }`}
                >
                  {opt === 'Oui' ? '✓ Oui' : '✗ Non'}
                </button>
              ))}
            </div>
          )}

          {/* CHOIX MULTIPLE */}
          {typeReponse === 'choix_multiple' && choix.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {choix.map((opt) => (
                <button
                  key={opt}
                  onClick={() => setReponse(opt)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-medium border-2 transition-all text-left leading-snug ${
                    reponse === opt
                      ? 'border-blue-600 bg-blue-600 text-white shadow-sm'
                      : 'border-gray-200 text-gray-700 hover:border-blue-300 bg-white'
                  }`}
                  style={{ maxWidth: '100%' }}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}

          {/* TEXTE LIBRE */}
          {typeReponse === 'texte_libre' && (
            <textarea
              value={reponse}
              onChange={(e) => setReponse(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); envoyer() } }}
              placeholder="Votre réponse... (Entrée pour envoyer)"
              rows={2}
              className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 bg-gray-50 resize-none"
              style={{ '--tw-ring-color': '#0054A6' } as React.CSSProperties}
              disabled={chargement}
              autoFocus
            />
          )}

          {/* NOMBRE */}
          {typeReponse === 'nombre' && (
            <div className="flex gap-2">
              <input
                type="number"
                value={reponse}
                onChange={(e) => setReponse(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') envoyer() }}
                placeholder="Entrez un nombre..."
                className="flex-1 text-sm border border-gray-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 bg-gray-50"
                style={{ '--tw-ring-color': '#0054A6' } as React.CSSProperties}
                disabled={chargement}
                autoFocus
              />
              <span className="self-center text-xs text-gray-400">FCFA</span>
            </div>
          )}

          {/* DATE */}
          {typeReponse === 'date' && (
            <input
              type="date"
              value={reponse}
              onChange={(e) => setReponse(e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 bg-gray-50"
              style={{ '--tw-ring-color': '#0054A6' } as React.CSSProperties}
              disabled={chargement}
              autoFocus
            />
          )}

          {/* IMAGE / IMAGES */}
          {estMedia && (
            <div className="space-y-3">
              {/* Zone de drop */}
              <div
                className={`relative border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-colors ${
                  dragOver
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-300 hover:border-blue-400 bg-gray-50'
                } ${medias.length >= nbImgsMax ? 'opacity-50 pointer-events-none' : ''}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragOver(false)
                  ajouterFichiers(Array.from(e.dataTransfer.files))
                }}
                onClick={() => inputFileRef.current?.click()}
              >
                <input
                  ref={inputFileRef}
                  type="file"
                  accept=".jpg,.jpeg,.png,.webp,.pdf"
                  multiple={typeReponse === 'images'}
                  className="hidden"
                  onChange={(e) => ajouterFichiers(Array.from(e.target.files ?? []))}
                  disabled={chargement || medias.length >= nbImgsMax}
                />
                <ArrowUpTrayIcon className="w-7 h-7 mx-auto mb-2 text-gray-400" />
                <p className="text-sm font-medium text-gray-600">
                  {dragOver ? 'Déposez ici...' : 'Glisser-déposer ou cliquer pour parcourir'}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  JPG · PNG · PDF — max {MAX_TAILLE_MO} Mo par fichier
                  {typeReponse === 'images' && ` — jusqu'à ${nbImgsMax} fichier(s)`}
                </p>
                <button
                  type="button"
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg text-white"
                  style={{ background: estSysteme ? '#7c3aed' : '#0054A6' }}
                >
                  <PhotoIcon className="w-3.5 h-3.5" />
                  {typeReponse === 'images' ? `Ajouter des fichiers (${medias.length}/${nbImgsMax})` : 'Sélectionner un fichier'}
                </button>
              </div>

              {/* Prévisualisation des médias sélectionnés */}
              {medias.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {medias.map((m, idx) => (
                    <div key={idx} className="relative group rounded-xl overflow-hidden border border-gray-200 bg-white shadow-sm"
                      style={{ width: 96, height: 96 }}>
                      {m.type === 'image' ? (
                        <img src={m.url} alt={m.file.name} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex flex-col items-center justify-center bg-red-50 gap-1">
                          <DocumentIcon className="w-8 h-8 text-red-400" />
                          <span className="text-xs text-red-600 font-medium px-1 text-center truncate w-full">{m.file.name}</span>
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => supprimerMedia(idx)}
                        className="absolute top-1 right-1 w-5 h-5 rounded-full bg-gray-900/70 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <XMarkIcon className="w-3 h-3" />
                      </button>
                      <div className="absolute bottom-0 left-0 right-0 bg-black/40 px-1 py-0.5">
                        <p className="text-white text-[10px] truncate">{m.file.name}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Message d'erreur */}
              {erreurMedia && (
                <p className="text-xs text-red-600 font-medium flex items-center gap-1">
                  <XMarkIcon className="w-3.5 h-3.5" /> {erreurMedia}
                </p>
              )}

              {/* Commentaire optionnel en plus des médias */}
              <textarea
                value={reponse}
                onChange={(e) => setReponse(e.target.value)}
                placeholder="Commentaire optionnel sur les documents..."
                rows={1}
                className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 bg-gray-50 resize-none"
                style={{ '--tw-ring-color': '#0054A6' } as React.CSSProperties}
                disabled={chargement}
              />
            </div>
          )}

          {/* Bouton envoyer (toujours visible) */}
          <button
            onClick={envoyer}
            disabled={!peutEnvoyer()}
            className="w-full py-2.5 text-white rounded-xl font-semibold flex items-center justify-center gap-2 transition-all disabled:opacity-40 shadow-sm"
            style={{
              background: peutEnvoyer()
                ? estSysteme
                  ? 'linear-gradient(135deg, #7c3aed, #4f46e5)'
                  : 'linear-gradient(135deg, #0054A6, #00B0F0)'
                : '#94a3b8'
            }}
          >
            <Send className="w-4 h-4" />
            {chargement ? 'Agent reprend...' : 'Envoyer — l\'agent continue'}
          </button>

          <p className="text-xs text-center" style={{ color: estSysteme ? '#7c3aed' : '#0054A6', opacity: 0.7 }}>
            L'agent reprendra automatiquement avec votre réponse
          </p>
        </div>
      )}

      {/* ── Reprise après réponse ── */}
      {reprise && (
        <div className={`px-4 py-3 border-t ${
          reprise.statut === 'termine' ? 'bg-green-50 border-green-100' : 'bg-blue-50 border-blue-100'
        }`}>
          <div className="flex items-center gap-2 mb-1">
            <RotateCcw className="w-4 h-4 text-blue-600" />
            <span className="text-xs font-semibold text-gray-700">Agent a repris le processus</span>
            <span className={`ml-auto text-xs px-2 py-0.5 rounded-full font-medium ${
              reprise.statut === 'termine' ? 'bg-green-100 text-green-700'
              : reprise.statut === 'en_attente_validation' ? 'bg-orange-100 text-orange-700'
              : 'bg-blue-100 text-blue-700'
            }`}>
              {reprise.statut === 'termine' ? 'Terminé'
               : reprise.statut === 'en_attente_validation' ? 'Validation requise'
               : reprise.statut}
            </span>
          </div>
          {reprise.resume && (
            <p className="text-xs text-gray-600 leading-relaxed">{reprise.resume}</p>
          )}
        </div>
      )}

      {/* ── Déjà répondu ── */}
      {item.statut !== 'en_attente' && !reprise && (
        <div className="px-4 py-2 flex items-center gap-2 bg-green-50 border-t border-green-100">
          <CheckCircleIcon className="w-4 h-4 text-green-600" />
          <span className="text-xs text-gray-600">
            Répondu : <em className="text-gray-800">"{item.commentaire}"</em>
            {item.traite_le && ` — ${new Date(item.traite_le).toLocaleString('fr-FR')}`}
          </span>
        </div>
      )}
    </div>
  )
}
