import { useState, useRef } from 'react'
import { Image, Wand2, Loader2, Download, ChevronDown, Upload, Ruler } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { infographieAPI } from '../api/client'
import toast from 'react-hot-toast'
import { DemoBanner } from '../components/DemoBanner'

const PAYS = [
  { code: 'CM', label: '🇨🇲 Cameroun' }, { code: 'SN', label: '🇸🇳 Sénégal' },
  { code: 'CI', label: '🇨🇮 Côte d\'Ivoire' }, { code: 'TG', label: '🇹🇬 Togo' },
]

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

type Mode = 'brief' | 'modele' | 'custom'

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
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

export default function InfographiePage() {
  const [mode, setMode] = useState<Mode>('brief')
  const [gabarit, setGabarit] = useState('')
  const [brief, setBrief] = useState('')
  const [pays, setPays] = useState('CM')
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{
    pdf_base64?: string; png_base64?: string; titre?: string;
    palette?: string; prix_fcfa?: number; analyse_modele?: string
    dimensions_mm?: { width: number; height: number }
  } | null>(null)

  // Mode modèle image
  const fileRef = useRef<HTMLInputElement>(null)
  const [modeleNom, setModeleNom] = useState('')

  // Mode custom
  const [customW, setCustomW] = useState(210)
  const [customH, setCustomH] = useState(297)
  const [customBleed, setCustomBleed] = useState(3)

  const { data: gabaritsData } = useQuery({
    queryKey: ['infographie-gabarits'],
    queryFn: () => infographieAPI.gabarits().then(r => r.data),
  })

  const gabarits: Gabarit[] = gabaritsData?.gabarits ?? []
  const categories = [...new Set(gabarits.map((g: Gabarit) => g.categorie))]
  const gabaritChoisi = gabarits.find(g => g.cle === gabarit)

  const generer = async () => {
    if (mode !== 'custom' && !gabarit) { toast.error('Choisissez un gabarit'); return }
    if (!brief.trim()) { toast.error('Décrivez votre besoin'); return }
    setLoading(true)
    setResultat(null)
    try {
      let r
      if (mode === 'brief') {
        r = await infographieAPI.generer({ brief, type_gabarit: gabarit, pays })
      } else if (mode === 'modele') {
        const file = fileRef.current?.files?.[0]
        if (!file) { toast.error('Sélectionnez une image modèle'); setLoading(false); return }
        const fd = new FormData()
        fd.append('modele', file)
        fd.append('brief', brief)
        fd.append('type_gabarit', gabarit)
        fd.append('pays', pays)
        r = await infographieAPI.genererDepuisModele(fd)
        if (r.data.analyse_modele) {
          toast.success('Style analysé — infographie générée !')
        }
      } else {
        r = await infographieAPI.genererCustom({ width_mm: customW, height_mm: customH, bleed_mm: customBleed, brief, pays })
      }
      setResultat(r.data)
      if (mode !== 'modele') toast.success('Infographie générée !')
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
    const label = gabarit || 'custom'
    b64download(b64, `infographie-${label}.${type}`, type === 'pdf' ? 'application/pdf' : 'image/png')
  }

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Image className="text-orange-500" size={24} />
          Infographie
        </h1>
        <p className="text-gray-500 text-sm mt-1">Flyers, affiches, réseaux sociaux, grand format — print-ready en 1 clic</p>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit text-sm">
        {([
          { key: 'brief', label: '✨ Depuis brief' },
          { key: 'modele', label: '📷 Depuis modèle' },
          { key: 'custom', label: '📐 Format libre' },
        ] as { key: Mode; label: string }[]).map(m => (
          <button key={m.key} onClick={() => { setMode(m.key); setResultat(null) }}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${mode === m.key ? 'bg-white shadow text-orange-600' : 'text-gray-500 hover:text-gray-700'}`}>
            {m.label}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        {/* Gabarit (modes brief et modele) */}
        {mode !== 'custom' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Gabarit</label>
            <div className="relative">
              <select value={gabarit} onChange={e => setGabarit(e.target.value)}
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm appearance-none bg-white pr-10 focus:outline-none focus:ring-2 focus:ring-orange-400">
                <option value="">— Sélectionner —</option>
                {categories.map(cat => (
                  <optgroup key={cat} label={CAT_LABELS[cat] || cat}>
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
        )}

        {/* Dimensions custom */}
        {mode === 'custom' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
              <Ruler size={16} className="text-orange-500" /> Dimensions personnalisées
            </label>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Largeur (mm)', val: customW, set: setCustomW, min: 10, max: 3000 },
                { label: 'Hauteur (mm)', val: customH, set: setCustomH, min: 10, max: 3000 },
                { label: 'Fond perdu (mm)', val: customBleed, set: setCustomBleed, min: 0, max: 20 },
              ].map(f => (
                <div key={f.label}>
                  <label className="block text-xs text-gray-500 mb-1">{f.label}</label>
                  <input type="number" min={f.min} max={f.max} value={f.val}
                    onChange={e => f.set(Number(e.target.value))}
                    className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-2">Format : {customW}×{customH}mm — fond perdu : {customBleed}mm</p>
          </div>
        )}

        {/* Upload image modèle */}
        {mode === 'modele' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Image modèle à analyser</label>
            <div className="border-2 border-dashed border-gray-300 rounded-xl p-5 text-center cursor-pointer hover:border-orange-400 transition-colors"
              onClick={() => fileRef.current?.click()}>
              <Upload size={24} className="mx-auto text-gray-400 mb-2" />
              <p className="text-sm text-gray-500">{modeleNom || 'Cliquez pour uploader ou glissez votre image'}</p>
              <p className="text-xs text-gray-400 mt-1">PNG, JPG, JPEG, WEBP (max 10 MB)</p>
              <input ref={fileRef} type="file" className="hidden"
                accept=".png,.jpg,.jpeg,.webp"
                onChange={e => setModeleNom(e.target.files?.[0]?.name || '')} />
            </div>
            <p className="text-xs text-gray-400 mt-1.5">L'IA analyse le style, la palette et la mise en page de votre modèle pour s'en inspirer</p>
          </div>
        )}

        {/* Pays */}
        <div className="flex flex-wrap gap-2">
          {PAYS.map(p => (
            <button key={p.code} onClick={() => setPays(p.code)}
              className={`px-3 py-1.5 rounded-lg text-sm ${pays === p.code ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-600'}`}>
              {p.label}
            </button>
          ))}
        </div>

        {/* Brief */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            {mode === 'modele' ? 'Brief client (contexte à intégrer)' : 'Brief client'}
          </label>
          <p className="text-xs text-gray-400 mb-2">
            {mode === 'modele'
              ? 'Précisez le nom, le slogan, les textes et le contexte. L\'IA s\'inspirera du style de votre modèle.'
              : 'Décrivez en langage naturel : nom, slogan, couleurs, textes, date, lieu…'}
          </p>
          <textarea value={brief} onChange={e => setBrief(e.target.value)} rows={5}
            placeholder={mode === 'modele'
              ? "Ex : \"Flyer pour la conférence 'Leadership Africain' à Yaoundé le 15 mars. Logo CMEF. Speakers : Dr Mbarga, Prof Diallo. Inscription gratuite via WhatsApp.\""
              : "Ex : \"Flyer pour l'ouverture de ma boutique 'Mode Chic' à Akwa. 30% de réduction le 1er jour. Tél : 699 00 11 22. Couleurs vertes et dorées.\""}
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
        </div>

        <button onClick={generer}
          disabled={loading || (!gabarit && mode !== 'custom') || !brief.trim()}
          className="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {loading ? 'Génération en cours…' : 'Générer l\'infographie'}
        </button>
      </div>

      {/* Résultat */}
      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-bold text-gray-900">{resultat.titre || 'Infographie générée'}</h2>
              {resultat.palette && <span className="text-xs text-gray-400">Palette : {resultat.palette}</span>}
              {resultat.dimensions_mm && (
                <span className="text-xs text-gray-400 ml-2">
                  · {resultat.dimensions_mm.width}×{resultat.dimensions_mm.height}mm
                </span>
              )}
            </div>
            <div className="flex gap-2">
              {resultat.pdf_base64 && (
                <button onClick={() => telecharger('pdf')}
                  className="flex items-center gap-1 bg-red-500 text-white text-xs font-medium px-3 py-2 rounded-xl hover:bg-red-600 transition-colors">
                  <Download size={14} /> PDF
                </button>
              )}
              {resultat.png_base64 && (
                <button onClick={() => telecharger('png')}
                  className="flex items-center gap-1 bg-blue-500 text-white text-xs font-medium px-3 py-2 rounded-xl hover:bg-blue-600 transition-colors">
                  <Download size={14} /> PNG
                </button>
              )}
            </div>
          </div>

          {/* Analyse modèle si disponible */}
          {resultat.analyse_modele && resultat.analyse_modele !== '{}' && (
            <div className="bg-orange-50 border border-orange-200 rounded-xl p-3">
              <p className="text-xs font-semibold text-orange-700 mb-1">Style détecté sur votre modèle</p>
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
              PDF généré — aperçu non disponible (pdf2image non installé)<br />
              Téléchargez le PDF pour voir le résultat
            </div>
          )}
        </div>
      )}
    </div>
  )
}
