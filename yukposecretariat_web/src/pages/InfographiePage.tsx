import { useState } from 'react'
import { Image, Wand2, Loader2, Download, ChevronDown } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { infographieAPI } from '../api/client'
import toast from 'react-hot-toast'

const PAYS = [
  { code: 'CM', label: '🇨🇲 Cameroun' }, { code: 'SN', label: '🇸🇳 Sénégal' },
  { code: 'CI', label: '🇨🇮 Côte d\'Ivoire' }, { code: 'TG', label: '🇹🇬 Togo' },
]

interface Gabarit {
  cle: string; label: string; width_mm: number; height_mm: number;
  categorie: string; prix_fcfa: number; description: string
}

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

export default function InfographiePage() {
  const [gabarit, setGabarit] = useState('')
  const [brief, setBrief] = useState('')
  const [pays, setPays] = useState('CM')
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{
    pdf_base64?: string; png_base64?: string; titre: string;
    palette: string; prix_fcfa: number; pdf_id?: string
  } | null>(null)

  const { data: gabaritsData } = useQuery({
    queryKey: ['infographie-gabarits'],
    queryFn: () => infographieAPI.gabarits().then(r => r.data),
  })

  const gabarits: Gabarit[] = gabaritsData?.gabarits ?? []
  const categories = [...new Set(gabarits.map((g: Gabarit) => g.categorie))]
  const gabaritChoisi = gabarits.find(g => g.cle === gabarit)

  const generer = async () => {
    if (!gabarit) { toast.error('Choisissez un gabarit'); return }
    if (!brief.trim()) { toast.error('Décrivez votre besoin'); return }
    setLoading(true)
    try {
      const r = await infographieAPI.generer({ brief, type_gabarit: gabarit, pays })
      setResultat(r.data)
      toast.success('Infographie générée !')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Erreur de génération')
    } finally {
      setLoading(false)
    }
  }

  const telecharger = (type: 'pdf' | 'png') => {
    const b64 = type === 'pdf' ? resultat?.pdf_base64 : resultat?.png_base64
    if (!b64) return
    const bytes = atob(b64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const mimeType = type === 'pdf' ? 'application/pdf' : 'image/png'
    const blob = new Blob([arr], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `infographie-${gabarit}.${type}`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Image className="text-orange-500" size={24} />
          Infographie
        </h1>
        <p className="text-gray-500 text-sm mt-1">Flyers, cartes, affiches, faire-part — print-ready en 1 clic</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        {/* Gabarit */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">Gabarit</label>
          <div className="relative">
            <select
              value={gabarit}
              onChange={e => setGabarit(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm appearance-none bg-white pr-10 focus:outline-none focus:ring-2 focus:ring-orange-400"
            >
              <option value="">— Sélectionner —</option>
              {categories.map(cat => (
                <optgroup key={cat} label={cat.replace('_', ' ')}>
                  {gabarits.filter(g => g.categorie === cat).map(g => (
                    <option key={g.cle} value={g.cle}>
                      {g.label} ({g.width_mm}×{g.height_mm}mm) — {formatFCFA(g.prix_fcfa)}
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

        {/* Pays */}
        <div className="flex flex-wrap gap-2">
          {PAYS.map(p => (
            <button key={p.code} onClick={() => setPays(p.code)}
              className={`px-3 py-1.5 rounded-lg text-sm ${pays === p.code ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-600'}`}
            >{p.label}</button>
          ))}
        </div>

        {/* Brief */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">Brief client</label>
          <p className="text-xs text-gray-400 mb-2">Décrivez en langage naturel : nom, slogan, couleurs, textes, date, lieu…</p>
          <textarea
            value={brief}
            onChange={e => setBrief(e.target.value)}
            rows={5}
            placeholder={`Exemple :\n"Flyer pour l'ouverture de ma boutique 'Mode Chic' à Akwa, Douala. 30% de réduction le 1er jour. Numéro WhatsApp : 699 00 11 22. Couleurs vertes et dorées."`}
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none"
          />
        </div>

        <button
          onClick={generer}
          disabled={loading || !gabarit || !brief.trim()}
          className="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {loading ? 'Génération en cours…' : 'Générer l\'infographie'}
        </button>
      </div>

      {/* Résultat */}
      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-bold text-gray-900">{resultat.titre}</h2>
              <span className="text-xs text-gray-400">Palette : {resultat.palette} · {formatFCFA(resultat.prix_fcfa)}</span>
            </div>
            <div className="flex gap-2">
              {resultat.pdf_base64 && (
                <button onClick={() => telecharger('pdf')}
                  className="flex items-center gap-1 bg-red-500 text-white text-xs font-medium px-3 py-2 rounded-xl">
                  <Download size={14} /> PDF
                </button>
              )}
              {resultat.png_base64 && (
                <button onClick={() => telecharger('png')}
                  className="flex items-center gap-1 bg-blue-500 text-white text-xs font-medium px-3 py-2 rounded-xl">
                  <Download size={14} /> PNG
                </button>
              )}
            </div>
          </div>

          {/* Preview PNG */}
          {resultat.png_base64 ? (
            <img
              src={`data:image/png;base64,${resultat.png_base64}`}
              alt="Aperçu infographie"
              className="w-full rounded-xl border border-gray-200 object-contain max-h-96"
            />
          ) : (
            <div className="bg-gray-50 rounded-xl p-8 text-center text-gray-400 text-sm">
              PDF généré — aperçu non disponible (pdf2image non installé)
              <br />Téléchargez le PDF pour voir le résultat
            </div>
          )}
        </div>
      )}
    </div>
  )
}
