import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  CalculatorIcon,
  ChartBarIcon,
  SparklesIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ResponsiveContainer,
} from 'recharts'
import axios from 'axios'

// ─── Schéma de validation ──────────────────────────────────────────────────

const schema = z.object({
  branche: z.string().min(1, 'Sélectionner une branche'),
  age_conducteur: z.number().min(18).max(99).optional(),
  anciennete_permis: z.number().min(0).max(60).optional(),
  valeur_vehicule: z.number().min(0).optional(),
  puissance_fiscale: z.number().min(1).max(30).optional(),
  usage: z.enum(['personnel', 'professionnel', 'mixte', 'taxi', 'transport']).optional(),
  score_bonus_malus: z.number().min(0.5).max(3.5).optional(),
  nb_sinistres_3ans: z.number().min(0).max(20).optional(),
  zone_immatriculation: z.string().optional(),
  valeur_assurée: z.number().min(0).optional(),
  nombre_employes: z.number().min(0).optional(),
  chiffre_affaires: z.number().min(0).optional(),
  duree_mois: z.number().min(1).max(12).default(12),
})

type FormData = z.infer<typeof schema>

// ─── Types ─────────────────────────────────────────────────────────────────

interface ResultatCalcul {
  prime_nette: number
  prime_commerciale: number
  prime_ttc: number
  taxes: number
  frais_accessoires: number
  commission: number
  detail_garanties: { garantie: string; prime: number; plafond: string }[]
  branche: string
  devise: string
}

interface ResultatML {
  score_risque: number
  segment_risque: string
  coefficient_ajustement: number
  prime_ajustee: number
  facteurs_risque: { facteur: string; impact: number; valeur: string }[]
  recommandation: string
  confiance: number
}

interface Scenario {
  nom: string
  description: string
  prime_ttc: number
  garanties: string[]
  franchise: string
  couleur: string
}

// ─── Constantes ────────────────────────────────────────────────────────────

const BRANCHES = [
  // ── Non-Vie ──
  { value: '10', label: 'Branche 10 — Automobile RC', famille: 'non_vie' },
  { value: '20', label: 'Branche 20 — Incendie & Risques Divers', famille: 'non_vie' },
  { value: '30', label: 'Branche 30 — RC Générale', famille: 'non_vie' },
  { value: '40', label: 'Branche 40 — Accidents Corporels', famille: 'non_vie' },
  { value: '50', label: 'Branche 50 — Transport / CMR', famille: 'non_vie' },
  { value: '60', label: 'Branche 60 — Aviation', famille: 'non_vie' },
  { value: 'mrh', label: 'MRH — Multirisque Habitation', famille: 'non_vie' },
  // ── Vie ──
  { value: '70', label: 'Branche 70 — Vie Entière / Capital Décès', famille: 'vie' },
  { value: '71', label: 'Branche 71 — Vie Mixte (Décès + Épargne)', famille: 'vie' },
  { value: '72', label: 'Branche 72 — Crédit-Vie / Emprunteur', famille: 'vie' },
  { value: '73', label: 'Branche 73 — Prévoyance / ITT / IPP', famille: 'vie' },
  { value: '74', label: 'Branche 74 — Éducation / Épargne Enfant', famille: 'vie' },
  { value: '75', label: 'Branche 75 — Retraite / Rente Viagère', famille: 'vie' },
  { value: '80', label: 'Branche 80 — Maladie / Santé', famille: 'vie' },
]

const ZONES = [
  'Douala', 'Yaoundé', 'Abidjan', 'Dakar', 'Libreville',
  'Brazzaville', 'Bangui', 'N\'Djamena', 'Niamey', 'Lomé',
  'Cotonou', 'Bamako', 'Ouagadougou', 'Conakry', 'Bujumbura',
]

const COULEURS_SCENARIO = {
  Basique: 'border-gray-300 bg-gray-50',
  Standard: 'border-primary-500 bg-primary-50 ring-2 ring-primary-500',
  Premium: 'border-amber-400 bg-amber-50',
}

// ─── Composant principal ───────────────────────────────────────────────────

export default function TarificationPage() {
  const [resultatCalcul, setResultatCalcul] = useState<ResultatCalcul | null>(null)
  const [resultatML, setResultatML] = useState<ResultatML | null>(null)
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingML, setLoadingML] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)
  const [brancheSelectionnee, setBrancheSelectionnee] = useState('')

  const { register, handleSubmit, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { duree_mois: 12, score_bonus_malus: 1.0, nb_sinistres_3ans: 0 },
  })

  const branche = watch('branche')

  // ─── Calcul prime ──────────────────────────────────────────────────────

  const calculerPrime = async (data: FormData) => {
    setLoading(true)
    setErreur(null)
    try {
      const [calcRes, mlRes] = await Promise.allSettled([
        axios.post('/api/v1/tarification/calculer', data),
        axios.post('/api/v1/tarification/ml/predire', data),
      ])

      // Résultat calcul barème
      if (calcRes.status === 'fulfilled') {
        setResultatCalcul(calcRes.value.data as ResultatCalcul)
        genererScenarios((calcRes.value.data as ResultatCalcul).prime_ttc)
      } else {
        // Demo fallback
        const demoCalc = genererDemoCalcul(data)
        setResultatCalcul(demoCalc)
        genererScenarios(demoCalc.prime_ttc)
      }

      // Résultat ML
      if (mlRes.status === 'fulfilled') {
        setResultatML(mlRes.value.data as ResultatML)
      } else {
        setResultatML(genererDemoML(data))
      }
    } catch (e) {
      setErreur('Erreur lors du calcul. Mode démonstration activé.')
      const demoCalc = genererDemoCalcul(data)
      setResultatCalcul(demoCalc)
      setResultatML(genererDemoML(data))
      genererScenarios(demoCalc.prime_ttc)
    } finally {
      setLoading(false)
    }
  }

  // ─── Génération scénarios ──────────────────────────────────────────────

  const genererScenarios = (primeBase: number) => {
    setScenarios([
      {
        nom: 'Basique',
        description: 'Couverture minimale réglementaire CIMA',
        prime_ttc: Math.round(primeBase * 0.75),
        garanties: ['RC Obligatoire', 'Défense Recours', 'Assistance de base'],
        franchise: '50 000 XAF',
        couleur: 'gray',
      },
      {
        nom: 'Standard',
        description: 'Couverture équilibrée — recommandé',
        prime_ttc: Math.round(primeBase),
        garanties: ['RC Obligatoire', 'Tous Risques partiel', 'Assistance étendue', 'Bris de glace'],
        franchise: '25 000 XAF',
        couleur: 'primary',
      },
      {
        nom: 'Premium',
        description: 'Protection maximale tous risques',
        prime_ttc: Math.round(primeBase * 1.35),
        garanties: ['RC Obligatoire', 'Tous Risques complet', 'Assistance 24/7', 'Bris de glace', 'Accessoires', 'Véhicule de remplacement'],
        franchise: '0 XAF',
        couleur: 'amber',
      },
    ])
  }

  // ─── Demo fallbacks ────────────────────────────────────────────────────

  const genererDemoCalc = (data: FormData): ResultatCalcul => {
    const isVie = ['70','71','72','73','74','75','80'].includes(data.branche || '')
    if (isVie) {
      // Calcul vie simplifié : PM + chargement
      const age = data.age_conducteur || 35
      const duree = data.anciennete_permis || 20
      const capital = data.valeur_vehicule || 25000000
      const taux = data.score_bonus_malus || 0.5
      // Prime annuelle ≈ capital × q_x × (1 + chargement) — approx actuarielle
      const qx = Math.min(0.04, 0.0005 * Math.exp((age - 30) * 0.05)) // mortalité simplifiée
      const facteurActuariel = (1 - Math.pow(1 + taux / 100, -duree)) / (taux / 100)
      const prime_nette = Math.round(capital * qx * duree / facteurActuariel)
      const pm = Math.round(prime_nette * facteurActuariel * 0.85)
      return {
        prime_nette,
        prime_commerciale: Math.round(prime_nette * 1.20),
        prime_ttc: Math.round(prime_nette * 1.20 * 1.05),
        taxes: Math.round(prime_nette * 0.05),
        frais_accessoires: 3000,
        commission: Math.round(prime_nette * 0.20),
        devise: 'XAF',
        branche: data.branche || '70',
        detail_garanties: [
          { garantie: 'Capital Décès', prime: Math.round(prime_nette * 0.60), plafond: `${capital.toLocaleString('fr-FR')} XAF` },
          { garantie: 'Provision Mathématique', prime: Math.round(pm / duree), plafond: `PM ${pm.toLocaleString('fr-FR')} XAF` },
          { garantie: 'Rachat / Réduction', prime: Math.round(prime_nette * 0.15), plafond: 'Valeur de rachat' },
          { garantie: 'Chargements & Frais', prime: Math.round(prime_nette * 0.25), plafond: '—' },
        ],
      }
    }
    const base = (data.valeur_vehicule || 5000000) * 0.035 + (data.valeur_assurée || 0) * 0.02
    const prime_nette = Math.max(45000, base * (data.duree_mois / 12))
    return {
      prime_nette,
      prime_commerciale: prime_nette * 1.12,
      prime_ttc: prime_nette * 1.12 * 1.14,
      taxes: prime_nette * 0.14,
      frais_accessoires: 5000,
      commission: prime_nette * 0.12,
      devise: 'XAF',
      branche: data.branche || '10',
      detail_garanties: [
        { garantie: 'RC Obligatoire', prime: prime_nette * 0.45, plafond: '50 000 000 XAF' },
        { garantie: 'Dommages Véhicule', prime: prime_nette * 0.35, plafond: 'Valeur déclarée' },
        { garantie: 'Vol & Incendie', prime: prime_nette * 0.12, plafond: 'Valeur Vénale' },
        { garantie: 'Bris de Glace', prime: prime_nette * 0.08, plafond: '500 000 XAF' },
      ],
    }
  }

  const genererDemoCalcul = genererDemoCalc

  const genererDemoML = (data: FormData): ResultatML => {
    const isVie = ['70','71','72','73','74','75','80'].includes(data.branche || '')
    const age = data.age_conducteur || 35
    if (isVie) {
      const scoreAge = age > 55 ? 35 : age > 45 ? 20 : age > 35 ? 10 : 5
      const scoreDuree = (data.anciennete_permis || 20) > 25 ? 15 : 5
      const score = Math.min(100, scoreAge + scoreDuree + 20)
      return {
        score_risque: Math.round(score),
        segment_risque: score < 30 ? 'Risque faible' : score < 60 ? 'Risque moyen' : 'Risque élevé',
        coefficient_ajustement: 0.85 + score / 250,
        prime_ajustee: Math.round(180000 * (0.85 + score / 250)),
        confiance: 0.91,
        recommandation: age > 55 ? 'Surprime d\'âge applicable — vérifier tableau mortalité CIMA-2016' : 'Conditions actuarielles standards',
        facteurs_risque: [
          { facteur: 'Âge de l\'assuré', impact: scoreAge, valeur: `${age} ans` },
          { facteur: 'Durée du contrat', impact: scoreDuree, valeur: `${data.anciennete_permis || 20} ans` },
          { facteur: 'Taux technique', impact: 10, valeur: `${data.score_bonus_malus || 0.5}%` },
          { facteur: 'Table mortalité', impact: 5, valeur: 'CIMA-2016' },
        ],
      }
    }
    const sinistres = data.nb_sinistres_3ans || 0
    const score = Math.min(100, 30 + (age < 25 ? 20 : 0) + sinistres * 15 + ((data.score_bonus_malus || 1) - 1) * 20)
    return {
      score_risque: Math.round(score),
      segment_risque: score < 30 ? 'Faible' : score < 60 ? 'Moyen' : score < 80 ? 'Élevé' : 'Très élevé',
      coefficient_ajustement: 0.8 + score / 200,
      prime_ajustee: Math.round(120000 * (0.8 + score / 200)),
      confiance: 0.87,
      recommandation: score > 70 ? 'Franchise majorée recommandée' : 'Conditions standards applicables',
      facteurs_risque: [
        { facteur: 'Âge conducteur', impact: age < 25 ? 25 : age > 60 ? 15 : 0, valeur: `${age} ans` },
        { facteur: 'Sinistres 3 ans', impact: sinistres * 15, valeur: `${sinistres} sinistre(s)` },
        { facteur: 'Bonus/Malus', impact: Math.round(((data.score_bonus_malus || 1) - 1) * 30), valeur: `CRM ${data.score_bonus_malus || 1}` },
        { facteur: 'Zone géographique', impact: data.zone_immatriculation === 'Douala' ? 12 : 5, valeur: data.zone_immatriculation || 'Non spécifiée' },
      ],
    }
  }

  // ─── Formatage ─────────────────────────────────────────────────────────

  const fmt = (n: number) => n.toLocaleString('fr-FR') + ' XAF'

  const couleurScore = (score: number) => {
    if (score < 30) return 'text-green-600 bg-green-100'
    if (score < 60) return 'text-yellow-600 bg-yellow-100'
    if (score < 80) return 'text-orange-600 bg-orange-100'
    return 'text-red-600 bg-red-100'
  }

  const bgScore = (score: number) => {
    if (score < 30) return 'bg-green-500'
    if (score < 60) return 'bg-yellow-500'
    if (score < 80) return 'bg-orange-500'
    return 'bg-red-500'
  }

  const isBrancheAuto = ['10'].includes(branche)
  const isBrancheVie = ['70', '71', '72', '73', '74', '75', '80'].includes(branche)
  const isBrancheEntreprise = ['20', '30'].includes(branche)

  return (
    <div className="space-y-6">

      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tarification</h1>
          <p className="text-sm text-gray-500 mt-1">Calcul de primes par barèmes CIMA · Prédiction ML · Comparateur d'offres</p>
        </div>
        <div className="flex items-center gap-2 text-xs bg-primary-50 text-primary-700 px-3 py-1.5 rounded-full border border-primary-200">
          <SparklesIcon className="w-4 h-4" />
          Moteur IA actif
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

        {/* ── Formulaire ────────────────────────────────────────────────── */}
        <div className="xl:col-span-1">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-base font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <CalculatorIcon className="w-5 h-5 text-primary-600" />
              Paramètres du risque
            </h2>

            <form onSubmit={handleSubmit(calculerPrime)} className="space-y-4">

              {/* Branche */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Branche *</label>
                <select
                  {...register('branche')}
                  onChange={(e) => setBrancheSelectionnee(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  <option value="">— Sélectionner —</option>
                  <optgroup label="Assurance Non-Vie">
                    {BRANCHES.filter(b => b.famille === 'non_vie').map(b => (
                      <option key={b.value} value={b.value}>{b.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Assurance Vie & Épargne">
                    {BRANCHES.filter(b => b.famille === 'vie').map(b => (
                      <option key={b.value} value={b.value}>{b.label}</option>
                    ))}
                  </optgroup>
                </select>
                {errors.branche && <p className="text-red-500 text-xs mt-1">{errors.branche.message}</p>}
              </div>

              {/* Durée */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Durée (mois)</label>
                <input
                  type="number" min={1} max={12}
                  {...register('duree_mois', { valueAsNumber: true })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                />
              </div>

              {/* Champs Auto */}
              {(isBrancheAuto || branche === '50') && (
                <>
                  <div className="border-t border-gray-100 pt-3">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Véhicule & Conducteur</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Âge conducteur</label>
                      <input type="number" min={18} max={99}
                        {...register('age_conducteur', { valueAsNumber: true })}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                        placeholder="35"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Ancienneté permis</label>
                      <input type="number" min={0} max={60}
                        {...register('anciennete_permis', { valueAsNumber: true })}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                        placeholder="10"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Valeur véhicule (XAF)</label>
                    <input type="number" min={0}
                      {...register('valeur_vehicule', { valueAsNumber: true })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                      placeholder="8 000 000"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Puissance fiscale (CV)</label>
                      <input type="number" min={1} max={30}
                        {...register('puissance_fiscale', { valueAsNumber: true })}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                        placeholder="8"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">CRM Bonus/Malus</label>
                      <input type="number" min={0.5} max={3.5} step={0.05}
                        {...register('score_bonus_malus', { valueAsNumber: true })}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                        placeholder="1.00"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Usage</label>
                    <select {...register('usage')}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                    >
                      <option value="personnel">Personnel</option>
                      <option value="professionnel">Professionnel</option>
                      <option value="mixte">Mixte</option>
                      <option value="taxi">Taxi / VTC</option>
                      <option value="transport">Transport marchandises</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Sinistres (3 dernières années)</label>
                    <input type="number" min={0} max={20}
                      {...register('nb_sinistres_3ans', { valueAsNumber: true })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                      placeholder="0"
                    />
                  </div>
                </>
              )}

              {/* Champs Entreprise */}
              {isBrancheEntreprise && (
                <>
                  <div className="border-t border-gray-100 pt-3">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Entreprise</p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Valeur assurée (XAF)</label>
                    <input type="number" min={0}
                      {...register('valeur_assurée', { valueAsNumber: true })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                      placeholder="50 000 000"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Nombre d'employés</label>
                    <input type="number" min={0}
                      {...register('nombre_employes', { valueAsNumber: true })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                      placeholder="25"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Chiffre d'affaires annuel (XAF)</label>
                    <input type="number" min={0}
                      {...register('chiffre_affaires', { valueAsNumber: true })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                      placeholder="200 000 000"
                    />
                  </div>
                </>
              )}

              {/* Champs Vie */}
              {isBrancheVie && (
                <>
                  <div className="border-t border-gray-100 pt-3">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Paramètres Vie</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Âge de l'assuré</label>
                      <input type="number" min={1} max={85}
                        {...register('age_conducteur', { valueAsNumber: true })}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                        placeholder="35"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Durée (années)</label>
                      <input type="number" min={1} max={40}
                        {...register('anciennete_permis', { valueAsNumber: true })}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                        placeholder="20"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Capital garanti / Capital décès (XAF)</label>
                    <input type="number" min={0}
                      {...register('valeur_vehicule', { valueAsNumber: true })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                      placeholder="25 000 000"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Table de mortalité</label>
                    <select {...register('usage')}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                    >
                      <option value="personnel">TD 88-90 (Hommes)</option>
                      <option value="professionnel">TV 88-90 (Femmes)</option>
                      <option value="mixte">CIMA-2016 (Mixte)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Taux technique (%)</label>
                    <select {...register('score_bonus_malus', { valueAsNumber: true })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                    >
                      <option value={0.5}>0,50 % (prudentiel max CIMA)</option>
                      <option value={1.0}>1,00 %</option>
                      <option value={1.5}>1,50 %</option>
                      <option value={2.0}>2,00 %</option>
                      <option value={2.5}>2,50 %</option>
                      <option value={3.0}>3,00 %</option>
                      <option value={3.5}>3,50 %</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Mode de sortie</label>
                    <select {...register('zone_immatriculation')}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                    >
                      <option value="capital">Capital (versement unique)</option>
                      <option value="rente_mensuelle">Rente mensuelle viagère</option>
                      <option value="rente_trimestrielle">Rente trimestrielle</option>
                      <option value="rente_annuelle">Rente annuelle</option>
                    </select>
                  </div>
                </>
              )}

              {/* Zone (Non-Vie uniquement) */}
              {!isBrancheVie && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Zone d'immatriculation</label>
                  <select {...register('zone_immatriculation')}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">— Sélectionner —</option>
                    {ZONES.map(z => <option key={z} value={z}>{z}</option>)}
                  </select>
                </div>
              )}

              {erreur && (
                <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
                  <ExclamationTriangleIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  {erreur}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-60 text-white font-medium py-2.5 px-4 rounded-lg transition-colors text-sm"
              >
                {loading ? (
                  <><ArrowPathIcon className="w-4 h-4 animate-spin" /> Calcul en cours…</>
                ) : (
                  <><CalculatorIcon className="w-4 h-4" /> Calculer la prime</>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* ── Résultats ─────────────────────────────────────────────────── */}
        <div className="xl:col-span-2 space-y-6">

          {/* Prime barème CIMA */}
          {resultatCalcul && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
              <h2 className="text-base font-semibold text-gray-800 mb-4 flex items-center gap-2">
                <ChartBarIcon className="w-5 h-5 text-primary-600" />
                Prime calculée — Barèmes CIMA
              </h2>

              {/* KPI prime */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                {[
                  { label: 'Prime Nette', value: fmt(resultatCalcul.prime_nette), color: 'bg-gray-50' },
                  { label: 'Prime Commerciale', value: fmt(resultatCalcul.prime_commerciale), color: 'bg-blue-50' },
                  { label: 'Taxes', value: fmt(resultatCalcul.taxes), color: 'bg-yellow-50' },
                  { label: 'Prime TTC', value: fmt(resultatCalcul.prime_ttc), color: 'bg-primary-50 font-bold' },
                ].map(k => (
                  <div key={k.label} className={`${k.color} rounded-lg p-3 text-center`}>
                    <p className="text-xs text-gray-500">{k.label}</p>
                    <p className={`text-sm font-semibold text-gray-900 mt-0.5 ${k.color.includes('primary') ? 'text-primary-700 text-base' : ''}`}>{k.value}</p>
                  </div>
                ))}
              </div>

              {/* Détail garanties */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Détail par garantie</p>
                <div className="overflow-hidden rounded-lg border border-gray-200">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Garantie</th>
                        <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Prime nette</th>
                        <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Plafond</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {resultatCalcul.detail_garanties.map((g, i) => (
                        <tr key={i} className={i % 2 === 0 ? '' : 'bg-gray-50'}>
                          <td className="px-4 py-2.5 text-gray-700">{g.garantie}</td>
                          <td className="px-4 py-2.5 text-right font-mono text-gray-900">{fmt(g.prime)}</td>
                          <td className="px-4 py-2.5 text-right text-gray-500 text-xs">{g.plafond}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="bg-primary-50 border-t-2 border-primary-200">
                      <tr>
                        <td className="px-4 py-2.5 font-semibold text-primary-700">TOTAL TTC</td>
                        <td className="px-4 py-2.5 text-right font-bold text-primary-700 font-mono">{fmt(resultatCalcul.prime_ttc)}</td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>

              {/* Bar chart garanties */}
              <div className="mt-4 h-44">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={resultatCalcul.detail_garanties} barSize={28}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="garantie" tick={{ fontSize: 11 }} interval={0} />
                    <YAxis tickFormatter={(v) => (v / 1000).toFixed(0) + 'k'} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: number) => fmt(v)} />
                    <Bar dataKey="prime" fill="#3b82f6" name="Prime nette" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Score ML */}
          {resultatML && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
              <h2 className="text-base font-semibold text-gray-800 mb-4 flex items-center gap-2">
                <SparklesIcon className="w-5 h-5 text-purple-600" />
                Analyse YukpoPro — Score de risque ML
                <span className="ml-auto text-xs text-gray-400">Confiance {Math.round(resultatML.confiance * 100)}%</span>
              </h2>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
                {/* Score visuel */}
                <div className="sm:col-span-1 flex flex-col items-center justify-center p-4 rounded-xl border border-gray-100 bg-gray-50">
                  <div className={`text-4xl font-black mb-1 ${couleurScore(resultatML.score_risque).split(' ')[0]}`}>
                    {resultatML.score_risque}
                  </div>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${couleurScore(resultatML.score_risque)}`}>
                    {resultatML.segment_risque}
                  </span>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-3">
                    <div
                      className={`h-2 rounded-full transition-all ${bgScore(resultatML.score_risque)}`}
                      style={{ width: `${resultatML.score_risque}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-400 mt-1">Score / 100</p>
                </div>

                {/* Prime ajustée */}
                <div className="sm:col-span-2 grid grid-cols-2 gap-3">
                  <div className="bg-purple-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-gray-500">Coefficient ML</p>
                    <p className="text-lg font-bold text-purple-700">×{resultatML.coefficient_ajustement.toFixed(2)}</p>
                  </div>
                  <div className="bg-indigo-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-gray-500">Prime ML ajustée</p>
                    <p className="text-base font-bold text-indigo-700">{fmt(resultatML.prime_ajustee)}</p>
                  </div>
                  <div className="col-span-2 flex items-start gap-2 p-3 bg-blue-50 rounded-lg border border-blue-100">
                    <InformationCircleIcon className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-blue-700">{resultatML.recommandation}</p>
                  </div>
                </div>
              </div>

              {/* Facteurs de risque */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Facteurs d'impact</p>
                <div className="space-y-2">
                  {resultatML.facteurs_risque.map((f, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <span className="text-xs text-gray-600 w-32 flex-shrink-0">{f.facteur}</span>
                      <div className="flex-1 bg-gray-100 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${f.impact > 15 ? 'bg-red-400' : f.impact > 5 ? 'bg-orange-400' : 'bg-green-400'}`}
                          style={{ width: `${Math.min(100, Math.abs(f.impact) * 3)}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium text-gray-700 w-8 text-right">+{f.impact}</span>
                      <span className="text-xs text-gray-400 w-28 text-right">{f.valeur}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Comparateur scénarios */}
          {scenarios.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
              <h2 className="text-base font-semibold text-gray-800 mb-4">
                Comparateur d'offres
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {scenarios.map((s) => {
                  const borderClass =
                    s.nom === 'Standard'
                      ? 'border-primary-500 ring-2 ring-primary-400'
                      : s.nom === 'Premium'
                      ? 'border-amber-400'
                      : 'border-gray-200'
                  const bgClass =
                    s.nom === 'Standard'
                      ? 'bg-primary-50'
                      : s.nom === 'Premium'
                      ? 'bg-amber-50'
                      : 'bg-gray-50'

                  return (
                    <div key={s.nom} className={`relative rounded-xl border-2 ${borderClass} ${bgClass} p-4`}>
                      {s.nom === 'Standard' && (
                        <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary-600 text-white text-xs font-semibold px-3 py-0.5 rounded-full">
                          Recommandé
                        </span>
                      )}
                      <h3 className="font-bold text-gray-800 text-center mb-1">{s.nom}</h3>
                      <p className="text-xs text-gray-500 text-center mb-3">{s.description}</p>
                      <p className="text-2xl font-black text-center text-gray-900 mb-1">{fmt(s.prime_ttc)}</p>
                      <p className="text-xs text-center text-gray-400 mb-4">TTC / an</p>
                      <p className="text-xs text-gray-500 mb-2 font-medium">Franchise : {s.franchise}</p>
                      <ul className="space-y-1">
                        {s.garanties.map((g, i) => (
                          <li key={i} className="flex items-start gap-2 text-xs text-gray-600">
                            <CheckCircleIcon className="w-3.5 h-3.5 text-green-500 flex-shrink-0 mt-0.5" />
                            {g}
                          </li>
                        ))}
                      </ul>
                      <button className={`mt-4 w-full py-2 rounded-lg text-xs font-semibold transition-colors ${
                        s.nom === 'Standard'
                          ? 'bg-primary-600 text-white hover:bg-primary-700'
                          : s.nom === 'Premium'
                          ? 'bg-amber-500 text-white hover:bg-amber-600'
                          : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                      }`}>
                        Souscrire — {s.nom}
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* État vide */}
          {!resultatCalcul && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center">
              <CalculatorIcon className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">Renseigner les paramètres du risque et cliquer sur</p>
              <p className="text-gray-500 font-medium">"Calculer la prime" pour voir les résultats.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
