import { useState } from 'react'
import { Receipt, Plus, Trash2, Loader2, Download } from 'lucide-react'
import { gestionAPI } from '../api/client'
import toast from 'react-hot-toast'

interface Ligne { description: string; quantite: number; prix_unitaire_fcfa: number; unite: string }

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

export default function DevisPage() {
  const [mode, setMode] = useState<'devis' | 'facture'>('devis')
  const [infos, setInfos] = useState({
    client_nom: '', client_contact: '', nom_secretariat: 'Mon Secrétariat',
    adresse_secretariat: '', tel_secretariat: '', notes: '', validite_jours: 15,
  })
  const [lignes, setLignes] = useState<Ligne[]>([
    { description: '', quantite: 1, prix_unitaire_fcfa: 0, unite: 'u' },
  ])
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{ pdf_base64: string; sous_total: number; tva: number; total_ttc: number } | null>(null)

  const ajouterLigne = () => setLignes(l => [...l, { description: '', quantite: 1, prix_unitaire_fcfa: 0, unite: 'u' }])
  const supprimerLigne = (i: number) => setLignes(l => l.filter((_, idx) => idx !== i))
  const modifierLigne = (i: number, key: keyof Ligne, val: string | number) =>
    setLignes(l => l.map((x, idx) => idx === i ? { ...x, [key]: val } : x))

  const sousTotal = lignes.reduce((s, l) => s + l.quantite * l.prix_unitaire_fcfa, 0)
  const tva = Math.round(sousTotal * 0.1925)
  const total = sousTotal + tva

  const generer = async () => {
    if (!infos.client_nom) { toast.error('Nom du client requis'); return }
    if (lignes.some(l => !l.description)) { toast.error('Toutes les lignes doivent avoir une description'); return }
    setLoading(true)
    try {
      const payload = { ...infos, lignes, validite_jours: +infos.validite_jours }
      const r = mode === 'devis'
        ? await gestionAPI.genererDevis(payload)
        : await gestionAPI.genererFacture(payload)
      setResultat(r.data)
      toast.success(`${mode === 'devis' ? 'Devis' : 'Facture'} généré(e) !`)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Erreur de génération')
    } finally {
      setLoading(false)
    }
  }

  const telechargerPDF = () => {
    if (!resultat) return
    const bytes = atob(resultat.pdf_base64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const blob = new Blob([arr], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${mode}-${infos.client_nom}.pdf`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Receipt className="text-teal-600" size={24} />
          Devis & Factures
        </h1>
        <p className="text-gray-500 text-sm mt-1">PDF professionnel en FCFA avec TVA 19.25%</p>
      </div>

      {/* Mode */}
      <div className="flex gap-2">
        {(['devis', 'facture'] as const).map(m => (
          <button key={m} onClick={() => setMode(m)}
            className={`flex-1 py-2.5 rounded-xl text-sm font-semibold capitalize transition-colors ${
              mode === m ? 'bg-teal-600 text-white' : 'bg-gray-100 text-gray-600'
            }`}
          >{m}</button>
        ))}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        {/* Infos */}
        <div className="grid grid-cols-2 gap-3">
          {[
            { key: 'client_nom', label: 'Client *', span: 2 },
            { key: 'client_contact', label: 'Tel/Email client', span: 2 },
            { key: 'nom_secretariat', label: 'Nom secrétariat', span: 1 },
            { key: 'tel_secretariat', label: 'Téléphone', span: 1 },
            { key: 'adresse_secretariat', label: 'Adresse', span: 2 },
          ].map(({ key, label, span }) => (
            <div key={key} className={`col-span-${span}`}>
              <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
              <input
                type="text"
                value={infos[key as keyof typeof infos]}
                onChange={e => setInfos(i => ({ ...i, [key]: e.target.value }))}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </div>
          ))}
        </div>

        {/* Lignes */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-semibold text-gray-700">Lignes du document</label>
            <button onClick={ajouterLigne}
              className="flex items-center gap-1 text-xs text-teal-600 hover:text-teal-700 font-medium">
              <Plus size={14} /> Ajouter
            </button>
          </div>
          <div className="space-y-2">
            {lignes.map((l, i) => (
              <div key={i} className="flex gap-2 items-start">
                <input
                  type="text" placeholder="Description"
                  value={l.description}
                  onChange={e => modifierLigne(i, 'description', e.target.value)}
                  className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
                />
                <input
                  type="number" placeholder="Qté" value={l.quantite} min={1}
                  onChange={e => modifierLigne(i, 'quantite', +e.target.value)}
                  className="w-14 border border-gray-200 rounded-lg px-2 py-2 text-sm text-center focus:outline-none"
                />
                <input
                  type="number" placeholder="Prix" value={l.prix_unitaire_fcfa} min={0}
                  onChange={e => modifierLigne(i, 'prix_unitaire_fcfa', +e.target.value)}
                  className="w-24 border border-gray-200 rounded-lg px-2 py-2 text-sm text-right focus:outline-none"
                />
                <button onClick={() => supprimerLigne(i)} disabled={lignes.length === 1}>
                  <Trash2 size={16} className="text-gray-300 hover:text-red-400 mt-2" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Totaux aperçu */}
        <div className="border-t border-gray-100 pt-3 space-y-1 text-sm">
          <div className="flex justify-between text-gray-500">
            <span>Sous-total HT</span><span>{formatFCFA(sousTotal)}</span>
          </div>
          <div className="flex justify-between text-gray-500">
            <span>TVA 19.25%</span><span>{formatFCFA(tva)}</span>
          </div>
          <div className="flex justify-between font-bold text-gray-900 text-base">
            <span>Total TTC</span><span>{formatFCFA(total)}</span>
          </div>
        </div>

        <button
          onClick={generer}
          disabled={loading}
          className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Receipt size={18} />}
          {loading ? 'Génération…' : `Générer le ${mode}`}
        </button>
      </div>

      {resultat && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-bold text-gray-900">Total TTC : {formatFCFA(resultat.total_ttc)}</div>
              <div className="text-xs text-gray-400">TVA incluse : {formatFCFA(resultat.tva)}</div>
            </div>
            <button onClick={telechargerPDF}
              className="flex items-center gap-2 bg-red-500 hover:bg-red-600 text-white font-semibold px-4 py-2 rounded-xl text-sm transition-colors">
              <Download size={16} /> Télécharger PDF
            </button>
          </div>
          <p className="text-xs text-gray-400 text-center">Paiement : Espèces · Orange Money · MTN MoMo</p>
        </div>
      )}
    </div>
  )
}
