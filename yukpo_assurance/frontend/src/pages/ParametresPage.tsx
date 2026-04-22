import { useState, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  BuildingOfficeIcon,
  PhotoIcon,
  SwatchIcon,
  GlobeAltIcon,
  CheckCircleIcon,
  ArrowPathIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import { useCompagnieStore, BrandingCompagnie } from '../store/compagnieStore'

const PAYS_CIMA = [
  { code: 'CM', label: '🇨🇲 Cameroun', devise: 'XAF' },
  { code: 'CI', label: '🇨🇮 Côte d\'Ivoire', devise: 'XOF' },
  { code: 'SN', label: '🇸🇳 Sénégal', devise: 'XOF' },
  { code: 'GA', label: '🇬🇦 Gabon', devise: 'XAF' },
  { code: 'CG', label: '🇨🇬 Congo-Brazzaville', devise: 'XAF' },
  { code: 'CF', label: '🇨🇫 Centrafrique', devise: 'XAF' },
  { code: 'TD', label: '🇹🇩 Tchad', devise: 'XAF' },
  { code: 'NE', label: '🇳🇪 Niger', devise: 'XOF' },
  { code: 'ML', label: '🇲🇱 Mali', devise: 'XOF' },
  { code: 'BF', label: '🇧🇫 Burkina Faso', devise: 'XOF' },
  { code: 'TG', label: '🇹🇬 Togo', devise: 'XOF' },
  { code: 'BJ', label: '🇧🇯 Bénin', devise: 'XOF' },
  { code: 'GW', label: '🇬🇼 Guinée-Bissau', devise: 'XOF' },
  { code: 'GQ', label: '🇬🇶 Guinée Équatoriale', devise: 'XAF' },
  { code: 'KM', label: '🇰🇲 Comores', devise: 'KMF' },
]

const PALETTES = [
  { label: 'Bleu Corporate', primaire: '#1d4ed8', secondaire: '#0ea5e9' },
  { label: 'Vert Finances', primaire: '#047857', secondaire: '#059669' },
  { label: 'Violet Premium', primaire: '#6d28d9', secondaire: '#7c3aed' },
  { label: 'Rouge Dynamique', primaire: '#b91c1c', secondaire: '#dc2626' },
  { label: 'Orange Énergie', primaire: '#c2410c', secondaire: '#ea580c' },
  { label: 'Gris Sérieux', primaire: '#374151', secondaire: '#6b7280' },
  { label: 'Indigo Moderne', primaire: '#312e81', secondaire: '#4338ca' },
  { label: 'Teal Pro', primaire: '#0f766e', secondaire: '#0d9488' },
]

const schema = z.object({
  nom: z.string().min(2, 'Nom requis'),
  slogan: z.string().optional(),
  telephone_support: z.string().optional(),
  email_support: z.string().email('Email invalide').optional().or(z.literal('')),
  site_web: z.string().url('URL invalide').optional().or(z.literal('')),
  pays: z.string(),
})

type FormValues = z.infer<typeof schema>

export default function ParametresPage() {
  const { branding, setBranding, setLogo, resetBranding } = useCompagnieStore()
  const [saved, setSaved] = useState(false)
  const [logoPreview, setLogoPreview] = useState<string | null>(branding.logo_url)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nom: branding.nom,
      slogan: branding.slogan,
      telephone_support: branding.telephone_support,
      email_support: branding.email_support,
      site_web: branding.site_web,
      pays: branding.pays,
    },
  })

  const onSubmit = (data: FormValues) => {
    const pays = PAYS_CIMA.find(p => p.code === data.pays)
    setBranding({
      ...data,
      pays: data.pays as BrandingCompagnie['pays'],
      devise: (pays?.devise as BrandingCompagnie['devise']) || 'XAF',
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 2 * 1024 * 1024) {
      alert('Logo trop volumineux — max 2 MB.')
      return
    }
    const reader = new FileReader()
    reader.onload = (ev) => {
      const base64 = ev.target?.result as string
      setLogoPreview(base64)
      setLogo(base64, base64)
    }
    reader.readAsDataURL(file)
  }

  const supprimerLogo = () => {
    setLogoPreview(null)
    setLogo('', undefined)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Paramètres</h1>
        <p className="text-sm text-gray-500 mt-1">Personnalisation de l'interface pour votre compagnie d'assurance</p>
      </div>

      {/* Aperçu live */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <SwatchIcon className="w-4 h-4 text-primary-600" />
          Aperçu de l'interface
        </h2>
        <div className="flex items-center gap-4 p-4 rounded-lg border border-gray-200" style={{ backgroundColor: branding.couleur_primaire }}>
          {logoPreview ? (
            <img src={logoPreview} alt="Logo compagnie" className="w-10 h-10 rounded-lg object-contain bg-white p-1" />
          ) : (
            <div className="w-10 h-10 rounded-lg bg-white/20 flex items-center justify-center">
              <span className="text-white text-xl font-black">{branding.nom[0]}</span>
            </div>
          )}
          <div>
            <p className="text-white font-bold text-sm">{branding.nom}</p>
            <p className="text-white/70 text-xs">{branding.slogan || 'Zone CIMA'}</p>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">

        {/* Logo */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <PhotoIcon className="w-4 h-4 text-primary-600" />
            Logo de la compagnie
          </h2>

          <div className="flex items-start gap-5">
            {/* Preview */}
            <div className="w-24 h-24 rounded-xl border-2 border-dashed border-gray-300 flex items-center justify-center overflow-hidden bg-gray-50 flex-shrink-0">
              {logoPreview ? (
                <img src={logoPreview} alt="Logo" className="w-full h-full object-contain p-2" />
              ) : (
                <div className="text-center">
                  <PhotoIcon className="w-8 h-8 text-gray-300 mx-auto" />
                  <p className="text-xs text-gray-400 mt-1">Logo</p>
                </div>
              )}
            </div>

            {/* Upload controls */}
            <div className="flex-1">
              <p className="text-sm text-gray-600 mb-3">
                Importez le logo de votre compagnie. Il apparaîtra dans la barre latérale, l'en-tête et tous les documents générés.
              </p>
              <p className="text-xs text-gray-400 mb-3">PNG ou SVG recommandé · Fond transparent · Max 2 MB</p>
              <div className="flex gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/svg+xml,image/webp"
                  onChange={handleLogoUpload}
                  className="hidden"
                  id="logo-upload"
                />
                <label
                  htmlFor="logo-upload"
                  className="flex items-center gap-2 cursor-pointer px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
                >
                  <PhotoIcon className="w-4 h-4" />
                  Choisir un logo
                </label>
                {logoPreview && (
                  <button
                    type="button"
                    onClick={supprimerLogo}
                    className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-600 text-sm rounded-lg hover:bg-gray-50"
                  >
                    <TrashIcon className="w-4 h-4" />
                    Supprimer
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Informations compagnie */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <BuildingOfficeIcon className="w-4 h-4 text-primary-600" />
            Informations compagnie
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Nom de la compagnie *</label>
              <input
                {...register('nom')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                placeholder="ABC Assurances"
              />
              {errors.nom && <p className="text-red-500 text-xs mt-1">{errors.nom.message}</p>}
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Slogan</label>
              <input
                {...register('slogan')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                placeholder="Votre sécurité, notre priorité"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Pays siège</label>
              <select
                {...register('pays')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
              >
                {PAYS_CIMA.map(p => (
                  <option key={p.code} value={p.code}>{p.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Téléphone support</label>
              <input
                {...register('telephone_support')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                placeholder="+237 6XX XXX XXX"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email support</label>
              <input
                {...register('email_support')}
                type="email"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                placeholder="support@compagnie.cm"
              />
              {errors.email_support && <p className="text-red-500 text-xs mt-1">{errors.email_support.message}</p>}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Site web</label>
              <input
                {...register('site_web')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                placeholder="https://www.compagnie.cm"
              />
            </div>
          </div>
        </div>

        {/* Palette de couleurs */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <SwatchIcon className="w-4 h-4 text-primary-600" />
            Couleurs de l'interface
          </h2>
          <p className="text-xs text-gray-400 mb-4">
            Choisissez une palette prédéfinie ou configurez vos couleurs personnalisées. Les couleurs s'appliquent à la sidebar, l'en-tête, et les boutons principaux.
          </p>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            {PALETTES.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => setBranding({ couleur_primaire: p.primaire, couleur_secondaire: p.secondaire })}
                className={`relative rounded-lg p-3 border-2 transition-all hover:shadow-md ${
                  branding.couleur_primaire === p.primaire ? 'border-gray-800 shadow-md' : 'border-gray-200'
                }`}
              >
                <div className="flex gap-1 mb-2">
                  <div className="w-6 h-6 rounded-md" style={{ backgroundColor: p.primaire }} />
                  <div className="w-6 h-6 rounded-md" style={{ backgroundColor: p.secondaire }} />
                </div>
                <p className="text-xs font-medium text-gray-700 text-left">{p.label}</p>
                {branding.couleur_primaire === p.primaire && (
                  <CheckCircleIcon className="absolute top-2 right-2 w-4 h-4 text-gray-800" />
                )}
              </button>
            ))}
          </div>

          {/* Couleurs personnalisées */}
          <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">Couleur primaire</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={branding.couleur_primaire}
                  onChange={(e) => setBranding({ couleur_primaire: e.target.value })}
                  className="w-10 h-10 rounded cursor-pointer border border-gray-300"
                />
                <span className="text-sm font-mono text-gray-600">{branding.couleur_primaire}</span>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">Couleur secondaire</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={branding.couleur_secondaire}
                  onChange={(e) => setBranding({ couleur_secondaire: e.target.value })}
                  className="w-10 h-10 rounded cursor-pointer border border-gray-300"
                />
                <span className="text-sm font-mono text-gray-600">{branding.couleur_secondaire}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Boutons */}
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={resetBranding}
            className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 px-4 py-2 rounded-lg hover:bg-gray-50"
          >
            <ArrowPathIcon className="w-4 h-4" />
            Réinitialiser par défaut
          </button>

          <div className="flex items-center gap-3">
            {saved && (
              <div className="flex items-center gap-2 text-green-600 text-sm">
                <CheckCircleIcon className="w-4 h-4" />
                Paramètres sauvegardés
              </div>
            )}
            <button
              type="submit"
              className="flex items-center gap-2 bg-primary-600 text-white text-sm font-medium px-6 py-2.5 rounded-lg hover:bg-primary-700 transition-colors"
            >
              <CheckCircleIcon className="w-4 h-4" />
              Sauvegarder les paramètres
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
