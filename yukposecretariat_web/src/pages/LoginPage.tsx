import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import toast from 'react-hot-toast'
import { Loader2, UserPlus, LogIn } from 'lucide-react'
import { useTranslation } from 'react-i18next'

type Mode = 'login' | 'register'

export default function LoginPage() {
  const { t } = useTranslation()
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [nom, setNom] = useState('')
  const [loading, setLoading] = useState(false)

  const passwordOk = password.length >= 6
  const formOk =
    mode === 'login'
      ? email.includes('@') && password.length > 0
      : email.includes('@') && nom.trim().length >= 2 && passwordOk

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!formOk) return
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(email, password)
        toast.success(t('auth.loginOk'))
      } else {
        await register(email, password, nom.trim())
        toast.success(t('auth.registerOk'))
      }
      navigate('/dashboard')
    } catch (err: any) {
      toast.error(err?.message || (mode === 'login' ? t('auth.loginErr') : t('auth.registerErr')))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-700 to-brand-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-8">
        <div className="text-center mb-6 flex flex-col items-center">
          <div className="flex items-center justify-center bg-white rounded-2xl mb-3"
               style={{ width: 72, height: 72, padding: 8, boxShadow: "0 0 0 1px rgba(0,84,166,0.15), 0 4px 14px rgba(0,84,166,0.15)" }}>
            <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          </div>
          <h1 className="text-2xl font-bold text-brand-700">Yukpo<span className="text-sky-500">Secrétariat</span></h1>
          <p className="text-gray-500 text-sm mt-1">{t('auth.loginSubtitle')}</p>
        </div>

        {/* Toggle Connexion / Inscription */}
        <div className="flex gap-1 bg-gray-100 p-1 rounded-xl mb-5 text-sm">
          <button onClick={() => setMode('login')}
            className={`flex-1 py-2 rounded-lg font-medium flex items-center justify-center gap-1.5 transition-colors ${
              mode === 'login' ? 'bg-white shadow text-brand-700' : 'text-gray-500 hover:text-gray-700'
            }`}>
            <LogIn size={14} /> {t('auth.tabLogin')}
          </button>
          <button onClick={() => setMode('register')}
            className={`flex-1 py-2 rounded-lg font-medium flex items-center justify-center gap-1.5 transition-colors ${
              mode === 'register' ? 'bg-white shadow text-brand-700' : 'text-gray-500 hover:text-gray-700'
            }`}>
            <UserPlus size={14} /> {t('auth.tabRegister')}
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'register' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('auth.fullName')}</label>
              <input
                type="text"
                value={nom}
                onChange={e => setNom(e.target.value)}
                required
                placeholder={t('auth.fullNamePlaceholder')}
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('auth.email')}</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              placeholder={t('auth.emailPlaceholder')}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('auth.password')}</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              placeholder="••••••••"
              className={`w-full border rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 ${
                mode === 'register' && password && !passwordOk
                  ? 'border-red-300 focus:ring-red-500'
                  : 'border-gray-300 focus:ring-brand-500'
              }`}
            />
            {mode === 'register' && (
              <p className={`text-xs mt-1 ${passwordOk ? 'text-emerald-600' : 'text-gray-400'}`}>
                {passwordOk ? t('auth.passwordValid') : t('auth.passwordMin')}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || !formOk}
            className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {loading && <Loader2 size={18} className="animate-spin" />}
            {mode === 'login' ? t('auth.submitLogin') : t('auth.submitRegister')}
          </button>
        </form>

        <p className="text-center text-xs text-gray-400 mt-6">
          {mode === 'login' ? t('auth.footerLogin') : t('auth.footerRegister')}
        </p>
      </div>
    </div>
  )
}
