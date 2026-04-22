import { useState, useEffect } from 'react'
import {
  ChatBubbleLeftRightIcon,
  PhotoIcon,
  PlusIcon,
  ChartBarIcon,
  HandThumbUpIcon,
  EyeIcon,
  ShareIcon,
} from '@heroicons/react/24/outline'

interface PostSocial {
  id: string
  contenu: string
  plateforme: 'facebook' | 'instagram' | 'linkedin' | 'whatsapp'
  statut: 'brouillon' | 'planifie' | 'publie' | 'erreur'
  date_publication: string
  likes: number
  vues: number
  partages: number
  generated_by_ia: boolean
}

const DEMO_POSTS: PostSocial[] = [
  {
    id: '1',
    contenu: '🛡️ Saviez-vous que votre assurance auto couvre également les dommages causés par des catastrophes naturelles ? Contactez-nous pour réviser votre contrat. #Assurance #Protection',
    plateforme: 'facebook',
    statut: 'publie',
    date_publication: '2026-04-08T10:00:00',
    likes: 45, vues: 1230, partages: 12,
    generated_by_ia: true,
  },
  {
    id: '2',
    contenu: '✅ Notre engagement : indemnisation en 48h pour les sinistres auto déclarés via notre application. Téléchargez YukpoAssurance maintenant ! #Rapidité #Innovation',
    plateforme: 'instagram',
    statut: 'planifie',
    date_publication: '2026-04-10T09:00:00',
    likes: 0, vues: 0, partages: 0,
    generated_by_ia: true,
  },
  {
    id: '3',
    contenu: 'Rejoignez nos 5 000+ clients assurés en zone CIMA. Devis gratuit en 2 minutes sur notre portail en ligne.',
    plateforme: 'linkedin',
    statut: 'brouillon',
    date_publication: '',
    likes: 0, vues: 0, partages: 0,
    generated_by_ia: false,
  },
  {
    id: '4',
    contenu: '📱 Déclarez votre sinistre depuis WhatsApp ! Envoyez simplement les photos de l\'accident à notre chatbot IA disponible 24h/24. #DigitalAssurance',
    plateforme: 'whatsapp',
    statut: 'publie',
    date_publication: '2026-04-07T14:00:00',
    likes: 89, vues: 2450, partages: 34,
    generated_by_ia: true,
  },
]

const PLATEFORME_CONFIG = {
  facebook: { label: 'Facebook', color: 'bg-blue-600', emoji: '👥' },
  instagram: { label: 'Instagram', color: 'bg-pink-500', emoji: '📸' },
  linkedin: { label: 'LinkedIn', color: 'bg-blue-700', emoji: '💼' },
  whatsapp: { label: 'WhatsApp', color: 'bg-green-500', emoji: '💬' },
}

const STATUT_CONFIG = {
  brouillon: { label: 'Brouillon', color: 'bg-gray-100 text-gray-600' },
  planifie: { label: 'Planifié', color: 'bg-blue-100 text-blue-700' },
  publie: { label: 'Publié', color: 'bg-green-100 text-green-700' },
  erreur: { label: 'Erreur', color: 'bg-red-100 text-red-700' },
}

export default function CommunityManagerPage() {
  const [posts, setPosts] = useState<PostSocial[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const [prompt, setPrompt] = useState('')

  useEffect(() => {
    const load = async () => {
      setIsLoading(true)
      try {
        const res = await fetch('/api/v1/community-manager/posts', {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
        })
        if (res.ok) {
          const data = await res.json()
          setPosts(Array.isArray(data.posts) ? data.posts : DEMO_POSTS)
        } else {
          setPosts(DEMO_POSTS)
        }
      } catch {
        setPosts(DEMO_POSTS)
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [])

  const genererPost = async () => {
    if (!prompt.trim()) return
    setIsGenerating(true)
    try {
      const res = await fetch('/api/v1/community-manager/generer', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
        body: JSON.stringify({ sujet: prompt, plateformes: ['facebook', 'instagram'] }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.posts) setPosts(prev => [...data.posts, ...prev])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setIsGenerating(false)
      setPrompt('')
    }
  }

  const totalLikes = posts.reduce((s, p) => s + p.likes, 0)
  const totalVues = posts.reduce((s, p) => s + p.vues, 0)
  const publies = posts.filter(p => p.statut === 'publie').length

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <ChatBubbleLeftRightIcon className="h-6 w-6 text-primary-600" />
          Community Manager IA
        </h2>
        <p className="text-sm text-gray-500">Gérez vos réseaux sociaux avec l'IA — posts auto-générés, planification, analytics</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Posts publiés', value: publies, icon: ShareIcon, color: 'text-green-600' },
          { label: 'Total vues', value: totalVues.toLocaleString('fr-FR'), icon: EyeIcon, color: 'text-blue-600' },
          { label: 'Total likes', value: totalLikes, icon: HandThumbUpIcon, color: 'text-pink-500' },
          { label: 'Posts IA', value: posts.filter(p => p.generated_by_ia).length, icon: ChartBarIcon, color: 'text-purple-600' },
        ].map(stat => (
          <div key={stat.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
            <stat.icon className={`h-5 w-5 ${stat.color} mb-2`} />
            <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
            <p className="text-xs text-gray-500 mt-1">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Génération IA */}
      <div className="bg-gradient-to-r from-primary-50 to-purple-50 rounded-xl border border-primary-100 p-5">
        <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
          <span className="text-lg">🤖</span>
          Générer un post avec l'IA
        </h3>
        <div className="flex gap-3">
          <input
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="Ex: Post sur nos nouveaux contrats MRH, ou campagne de fidélisation clients auto..."
            className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:border-primary-500 outline-none"
            onKeyDown={e => e.key === 'Enter' && genererPost()}
          />
          <button
            onClick={genererPost}
            disabled={isGenerating || !prompt.trim()}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary-600 text-white rounded-xl text-sm hover:bg-primary-700 disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            {isGenerating ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
            ) : (
              <PlusIcon className="h-4 w-4" />
            )}
            Générer
          </button>
        </div>
      </div>

      {/* Liste des posts */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      ) : (
        <div className="space-y-3">
          {posts.map(post => (
            <div key={post.id} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-1 rounded-full text-white ${PLATEFORME_CONFIG[post.plateforme].color}`}>
                    {PLATEFORME_CONFIG[post.plateforme].emoji} {PLATEFORME_CONFIG[post.plateforme].label}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${STATUT_CONFIG[post.statut].color}`}>
                    {STATUT_CONFIG[post.statut].label}
                  </span>
                  {post.generated_by_ia && (
                    <span className="text-xs bg-purple-100 text-purple-600 px-2 py-0.5 rounded-full">🤖 IA</span>
                  )}
                </div>
                {post.date_publication && (
                  <span className="text-xs text-gray-400">
                    {new Date(post.date_publication).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
              </div>

              <p className="text-sm text-gray-700 mb-3">{post.contenu}</p>

              {post.statut === 'publie' && (
                <div className="flex gap-4 text-xs text-gray-400">
                  <span className="flex items-center gap-1"><EyeIcon className="h-3.5 w-3.5" />{post.vues.toLocaleString()}</span>
                  <span className="flex items-center gap-1"><HandThumbUpIcon className="h-3.5 w-3.5" />{post.likes}</span>
                  <span className="flex items-center gap-1"><ShareIcon className="h-3.5 w-3.5" />{post.partages}</span>
                </div>
              )}

              {post.statut === 'brouillon' && (
                <div className="flex gap-2 mt-2">
                  <button className="text-xs px-3 py-1.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
                    Publier
                  </button>
                  <button className="text-xs px-3 py-1.5 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-50">
                    Planifier
                  </button>
                  <button className="text-xs px-3 py-1.5 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-50">
                    Modifier
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
