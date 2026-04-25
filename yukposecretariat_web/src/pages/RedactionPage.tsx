import { useQuery } from '@tanstack/react-query'
import { FileText, Download, Loader2, ChevronDown, Wand2 } from 'lucide-react'
import { redactionAPI } from '../api/client'
import toast from 'react-hot-toast'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { DemoBanner } from '../components/DemoBanner'
import { CountryPicker } from '../components/CountryPicker'
import { useLongOps, useLongOpField } from '../store/longOpsStore'

interface TypeDoc { cle: string; label: string; categorie: string; prix_base_fcfa: number; description: string }

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

type RedactionResult = {
  titre: string; contenu_markdown: string; prix_fcfa: number; nb_mots: number;
  fichier_id?: string; word_base64?: string
}

export default function RedactionPage() {
  const [typeDoc, setTypeDoc] = useLongOpField<string>('redaction', 'typeDoc', '')
  const [pays, setPays] = useLongOpField<string>('redaction', 'pays', 'CM')
  const [informations, setInformations] = useLongOpField<string>('redaction', 'informations', '')
  const [reformuler, setReformuler] = useLongOpField<string>('redaction', 'reformuler', '')
  const loading = useLongOps((s) => s.loading.redaction)
  const resultat = useLongOps((s) => s.resultats.redaction) as RedactionResult | null
  const runOp = useLongOps((s) => s.run)

  const { data: typesData } = useQuery({
    queryKey: ['redaction-types'],
    queryFn: () => redactionAPI.types().then(r => r.data),
  })

  const types: TypeDoc[] = typesData?.types ?? []
  const categories = [...new Set(types.map(t => t.categorie))]

  const infosParsed = () => {
    if (!informations.trim()) return {}
    try {
      return JSON.parse(informations)
    } catch {
      return { description: informations }
    }
  }

  const generer = async () => {
    if (!typeDoc) { toast.error('Choisissez un type de document'); return }
    try {
      await runOp<RedactionResult>('redaction', async () => {
        const r = await redactionAPI.generer({
          type_doc: typeDoc,
          informations: infosParsed(),
          pays,
          reformuler_texte: reformuler || undefined,
        })
        return r.data as RedactionResult
      })
      toast.success('Document généré !')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Erreur de génération')
    }
  }

  const telechargerWord = () => {
    if (!resultat?.word_base64) return
    const bytes = atob(resultat.word_base64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const blob = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${resultat.titre || 'document'}.docx`
    a.click()
    URL.revokeObjectURL(url)
  }

  const typeChoisi = types.find(t => t.cle === typeDoc)

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <FileText className="text-brand-600" size={24} />
          Rédaction IA
        </h1>
        <p className="text-gray-500 text-sm mt-1">Génération de documents professionnels adaptés à l'Afrique francophone</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        {/* Type de document */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">Type de document</label>
          <div className="relative">
            <select
              value={typeDoc}
              onChange={e => setTypeDoc(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white pr-10"
            >
              <option value="">— Sélectionner —</option>
              {categories.map(cat => (
                <optgroup key={cat} label={typesData?.categories?.[cat] ?? cat}>
                  {types.filter(t => t.categorie === cat).map(t => (
                    <option key={t.cle} value={t.cle}>{t.label} — {formatFCFA(t.prix_base_fcfa)}</option>
                  ))}
                </optgroup>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>
          {typeChoisi && (
            <p className="text-xs text-gray-400 mt-1">{typeChoisi.description}</p>
          )}
        </div>

        {/* Pays */}
        <CountryPicker label="Contexte pays" value={pays} onChange={setPays} />

        {/* Informations */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Informations du document
          </label>
          <p className="text-xs text-gray-400 mb-2">
            Décrivez librement : noms, dates, montants, objet, etc. (texte libre ou JSON)
          </p>
          <textarea
            value={informations}
            onChange={e => setInformations(e.target.value)}
            rows={4}
            placeholder={`Exemple :\nDestinataire : M. le Directeur de l'ANOR\nObjet : Demande d'agrément\nNom demandeur : SARL Techno Yaoundé\nDate : 22 avril 2026`}
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
          />
        </div>

        {/* Reformuler (optionnel) */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Texte à reformuler <span className="text-gray-400 font-normal">(optionnel)</span>
          </label>
          <textarea
            value={reformuler}
            onChange={e => setReformuler(e.target.value)}
            rows={3}
            placeholder="Collez un brouillon existant à corriger/améliorer…"
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
          />
        </div>

        <button
          onClick={generer}
          disabled={loading || !typeDoc}
          className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {loading ? 'Génération en cours…' : 'Générer le document'}
        </button>
      </div>

      {/* Résultat */}
      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div>
              <h2 className="font-bold text-gray-900">{resultat.titre}</h2>
              <p className="text-xs text-gray-400">{resultat.nb_mots} mots · {formatFCFA(resultat.prix_fcfa)}</p>
            </div>
            {resultat.word_base64 && (
              <button
                onClick={telechargerWord}
                className="flex items-center gap-1.5 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors shrink-0"
              >
                <Download size={16} />
                .docx
              </button>
            )}
          </div>
          <div className="prose prose-sm max-w-none text-gray-700 border-t border-gray-100 pt-4">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{resultat.contenu_markdown}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}
