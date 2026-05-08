/**
 * Organisation — plan Entreprise pour YukpoSecrétariat.
 * Backend partagé avec YukpoPro (/api/v1/pro/orgs/*) — un seul compte
 * organisation peut être utilisé sur les deux apps.
 */
import { useEffect, useState, useCallback, FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Building2, Users, Mail, Trash2, Crown, Shield, UserMinus,
  Plus, RefreshCw, Copy, Check, Receipt, AlertCircle, Loader2,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { orgsAPI, type Organisation, type OrgMembre, type OrgInvite, type OrgFacture } from '../api/client'
import { CountryPicker } from '../components/CountryPicker'

const fmtFCFA = (n: number) => new Intl.NumberFormat('fr-FR').format(Math.round(n))

export default function OrganisationPage() {
  const { t } = useTranslation()
  const [org, setOrg] = useState<Organisation | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'membres' | 'invitations' | 'facturation' | 'settings'>('membres')
  const [membres, setMembres] = useState<OrgMembre[]>([])
  const [invitations, setInvitations] = useState<OrgInvite[]>([])
  const [factures, setFactures] = useState<OrgFacture[]>([])

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const o = await orgsAPI.monOrg()
      setOrg(o)
      if (o) {
        const m = await orgsAPI.membres(o.id)
        setMembres(m.membres)
      }
    } catch {
      toast.error(t('common.loadingError'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!org) return
    const isAdmin = org.mon_role === 'owner' || org.mon_role === 'admin'
    if (tab === 'invitations' && isAdmin) {
      orgsAPI.invitations(org.id).then(r => setInvitations(r.invitations)).catch(() => {})
    }
    if (tab === 'facturation' && isAdmin) {
      orgsAPI.factures(org.id).then(r => setFactures(r.factures)).catch(() => {})
    }
  }, [tab, org])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        <Loader2 className="animate-spin mr-2" size={20} /> {t('common.loading')}
      </div>
    )
  }

  if (!org) return <CreerOrgForm onCreated={charger} />

  const isAdmin = org.mon_role === 'owner' || org.mon_role === 'admin'

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-500 to-sky-500 flex items-center justify-center shadow-sm">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{org.nom}</h1>
            <div className="flex items-center gap-2 text-xs text-gray-500 mt-1 flex-wrap">
              <span>{t('organisation.planLabel', { plan: org.plan })}</span>
              <span>·</span>
              <span>{t('organisation.pricePerSeat', { price: fmtFCFA(org.prix_par_siege_fcfa), devise: org.devise })}</span>
              <span>·</span>
              <span>{t('organisation.activeMembers', { count: membres.length })}</span>
              {org.max_seats && <><span>·</span><span>{t('organisation.maxSeats', { n: org.max_seats })}</span></>}
            </div>
          </div>
        </div>
        <RoleBadge role={org.mon_role!} />
      </div>

      {/* Tabs */}
      <nav className="flex gap-2 border-b border-gray-200 overflow-x-auto">
        {([
          { id: 'membres',     labelKey: 'organisation.tabMembres',      icon: Users,   adminOnly: false },
          { id: 'invitations', labelKey: 'organisation.tabInvitations',  icon: Mail,    adminOnly: true  },
          { id: 'facturation', labelKey: 'organisation.tabFacturation',  icon: Receipt, adminOnly: true  },
          { id: 'settings',    labelKey: 'organisation.tabSettings',     icon: Shield,  adminOnly: true  },
        ] as const).filter(x => !x.adminOnly || isAdmin).map(x => {
          const Icon = x.icon
          const active = tab === x.id
          return (
            <button key={x.id} onClick={() => setTab(x.id as typeof tab)}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                active ? 'border-brand-600 text-brand-700' : 'border-transparent text-gray-500 hover:text-gray-800'
              }`}>
              <Icon size={14} /> {t(x.labelKey)}
            </button>
          )
        })}
      </nav>

      {tab === 'membres' && <MembresTab org={org} membres={membres} onRefresh={charger} />}
      {tab === 'invitations' && isAdmin && (
        <InvitationsTab org={org} invitations={invitations}
          onRefresh={() => orgsAPI.invitations(org.id).then(r => setInvitations(r.invitations))} />
      )}
      {tab === 'facturation' && isAdmin && <FacturationTab factures={factures} />}
      {tab === 'settings' && isAdmin && <SettingsTab org={org} onUpdated={charger} />}
    </div>
  )
}

// ── Sous-composants ─────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: string }) {
  const { t } = useTranslation()
  const map: Record<string, { labelKey: string; cls: string; icon: typeof Crown }> = {
    owner:  { labelKey: 'organisation.roleOwner',  cls: 'bg-amber-50 text-amber-700 border-amber-200', icon: Crown },
    admin:  { labelKey: 'organisation.roleAdmin',  cls: 'bg-blue-50 text-blue-700 border-blue-200',    icon: Shield },
    member: { labelKey: 'organisation.roleMember', cls: 'bg-gray-100 text-gray-600 border-gray-200',   icon: Users },
  }
  const r = map[role] || map.member
  const Icon = r.icon
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border text-xs font-medium ${r.cls}`}>
      <Icon size={14} /> {t(r.labelKey)}
    </span>
  )
}

function CreerOrgForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation()
  const [nom, setNom] = useState('')
  const [pays, setPays] = useState('CM')
  const [secteur, setSecteur] = useState('')
  const [prix, setPrix] = useState(8000)
  const [domain, setDomain] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (nom.trim().length < 2) return toast.error(t('organisation.errNameTooShort'))
    setBusy(true)
    try {
      await orgsAPI.creer({
        nom, pays, secteur: secteur || undefined,
        prix_par_siege_fcfa: prix,
        domain_auto_join: domain.trim().toLowerCase() || undefined,
      })
      toast.success(t('organisation.okCreated'))
      onCreated()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || t('organisation.errCreate'))
    } finally { setBusy(false) }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-500 to-sky-500 flex items-center justify-center shadow-sm">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{t('organisation.createTitle')}</h1>
            <p className="text-xs text-gray-500 mt-0.5">{t('organisation.createSubtitle')}</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <Field label={t('organisation.fieldName')}>
            <input value={nom} onChange={e => setNom(e.target.value)} required
              placeholder={t('organisation.fieldNamePh')}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
          </Field>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <CountryPicker label={t('common.country')} value={pays} onChange={setPays} />
            <Field label={t('organisation.fieldSector')}>
              <input value={secteur} onChange={e => setSecteur(e.target.value)}
                placeholder={t('organisation.fieldSectorPh')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
            </Field>
          </div>

          <Field label={t('organisation.fieldPricePerSeat')}>
            <input type="number" value={prix} min={0} step={500}
              onChange={e => setPrix(parseInt(e.target.value) || 0)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
            <p className="text-xs text-gray-500 mt-1 leading-relaxed">
              {t('organisation.pricePerSeatHint', { example: (prix * 5).toLocaleString('fr-FR') })}
            </p>
          </Field>

          <Field label={t('organisation.fieldDomain')}>
            <input value={domain} onChange={e => setDomain(e.target.value)}
              placeholder="entreprise.com"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
            <p className="text-xs text-gray-500 mt-1">
              {t('organisation.domainHint', { domain: domain || 'entreprise.com' })}
            </p>
          </Field>

          <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-800 flex gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <p>{t('organisation.ownerNote')}</p>
          </div>

          <button type="submit" disabled={busy}
            className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 transition-colors">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
            {t('organisation.createBtn')}
          </button>
        </form>
      </div>
    </div>
  )
}

function MembresTab({ org, membres, onRefresh }: { org: Organisation; membres: OrgMembre[]; onRefresh: () => void }) {
  const { t } = useTranslation()
  const isAdmin = org.mon_role === 'owner' || org.mon_role === 'admin'

  const handleChangeRole = async (m: OrgMembre, nouveau: 'admin' | 'member') => {
    try {
      await orgsAPI.changerRole(org.id, m.user_id, nouveau)
      toast.success(t('organisation.okRoleChanged', { who: m.nom || m.email, role: t(`organisation.role${nouveau.charAt(0).toUpperCase() + nouveau.slice(1)}` as 'organisation.roleAdmin' | 'organisation.roleMember') }))
      onRefresh()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || t('common.error'))
    }
  }

  const handleRetirer = async (m: OrgMembre) => {
    if (!confirm(t('organisation.confirmRemove', { who: m.nom || m.email }))) return
    try {
      await orgsAPI.retirerMembre(org.id, m.user_id)
      toast.success(t('organisation.okRemoved'))
      onRefresh()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || t('common.error'))
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-3 font-semibold">{t('organisation.colMember')}</th>
              <th className="text-left px-4 py-3 font-semibold">{t('organisation.colRole')}</th>
              <th className="text-left px-4 py-3 font-semibold">{t('organisation.colJoined')}</th>
              <th className="text-right px-4 py-3 font-semibold">{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {membres.map(m => (
              <tr key={m.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <div className="font-medium text-gray-900">{m.nom || m.username}</div>
                  <div className="text-xs text-gray-500">{m.email}</div>
                </td>
                <td className="px-4 py-3"><RoleBadge role={m.role} /></td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {new Date(m.joined_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3 text-right">
                  {isAdmin && m.role !== 'owner' && (
                    <div className="flex gap-2 justify-end">
                      {m.role === 'member' ? (
                        <button onClick={() => handleChangeRole(m, 'admin')}
                          className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100">
                          {t('organisation.promoteAdmin')}
                        </button>
                      ) : (
                        <button onClick={() => handleChangeRole(m, 'member')}
                          className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-700 hover:bg-gray-200">
                          {t('organisation.demote')}
                        </button>
                      )}
                      <button onClick={() => handleRetirer(m)}
                        className="text-xs px-2 py-1 rounded bg-red-50 text-red-700 hover:bg-red-100"
                        title={t('organisation.remove')}>
                        <UserMinus size={14} />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {membres.length === 0 && (
              <tr><td colSpan={4} className="text-center py-8 text-gray-500">{t('organisation.noMembers')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function InvitationsTab({ org, invitations, onRefresh }: { org: Organisation; invitations: OrgInvite[]; onRefresh: () => void }) {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'member' | 'admin'>('member')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)

  const inviter = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.includes('@')) return toast.error(t('organisation.errInvalidEmail'))
    setBusy(true)
    try {
      const inv = await orgsAPI.inviter(org.id, email, role)
      const url = `${window.location.origin}/orgs/invites/${inv.token}`
      navigator.clipboard?.writeText(url).catch(() => {})
      toast.success(t('organisation.okInvitedAndCopied'))
      setEmail('')
      onRefresh()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || t('common.error'))
    } finally { setBusy(false) }
  }

  const revoquer = async (inv: OrgInvite) => {
    if (!confirm(t('organisation.confirmRevoke', { email: inv.email }))) return
    try {
      await orgsAPI.revoquerInvite(org.id, inv.id)
      toast.success(t('organisation.okRevoked'))
      onRefresh()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || t('common.error'))
    }
  }

  const copyLink = (token?: string) => {
    if (!token) return
    const url = `${window.location.origin}/orgs/invites/${token}`
    navigator.clipboard?.writeText(url)
    setCopied(token); setTimeout(() => setCopied(null), 2000)
    toast.success(t('organisation.linkCopied'))
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-gray-200 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">{t('organisation.inviteTitle')}</h2>
        <form onSubmit={inviter} className="flex gap-2 flex-wrap">
          <input type="email" value={email} onChange={e => setEmail(e.target.value)}
            placeholder="email@entreprise.com"
            className="flex-1 min-w-64 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
          <select value={role} onChange={e => setRole(e.target.value as 'member' | 'admin')}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500">
            <option value="member">{t('organisation.roleMember')}</option>
            <option value="admin">{t('organisation.roleAdmin')}</option>
          </select>
          <button type="submit" disabled={busy}
            className="bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white font-medium px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />}
            {t('organisation.inviteBtn')}
          </button>
        </form>
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        {invitations.length === 0 ? (
          <p className="p-6 text-center text-sm text-gray-500">{t('organisation.noInvites')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-3 font-semibold">{t('common.email')}</th>
                  <th className="text-left px-4 py-3 font-semibold">{t('organisation.colRole')}</th>
                  <th className="text-left px-4 py-3 font-semibold">{t('common.status')}</th>
                  <th className="text-left px-4 py-3 font-semibold">{t('organisation.colExpires')}</th>
                  <th className="text-right px-4 py-3 font-semibold">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {invitations.map(i => (
                  <tr key={i.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-900">{i.email}</td>
                    <td className="px-4 py-3"><RoleBadge role={i.role} /></td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        i.statut === 'en_attente' ? 'bg-amber-50 text-amber-700' :
                        i.statut === 'accepte'    ? 'bg-emerald-50 text-emerald-700' :
                        'bg-gray-100 text-gray-600'
                      }`}>{t(`organisation.inviteStatus.${i.statut}`, i.statut)}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {new Date(i.expires_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {i.statut === 'en_attente' && (
                        <div className="flex gap-2 justify-end">
                          {i.token && (
                            <button onClick={() => copyLink(i.token)}
                              className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-700 hover:bg-gray-200"
                              title={t('organisation.copyLink')}>
                              {copied === i.token ? <Check size={14} /> : <Copy size={14} />}
                            </button>
                          )}
                          <button onClick={() => revoquer(i)}
                            className="text-xs px-2 py-1 rounded bg-red-50 text-red-700 hover:bg-red-100"
                            title={t('organisation.revoke')}>
                            <Trash2 size={14} />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function FacturationTab({ factures }: { factures: OrgFacture[] }) {
  const { t } = useTranslation()
  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
      {factures.length === 0 ? (
        <p className="p-6 text-center text-sm text-gray-500">{t('organisation.noInvoices')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-3 font-semibold">{t('organisation.colPeriod')}</th>
                <th className="text-right px-4 py-3 font-semibold">{t('organisation.colMaxSeats')}</th>
                <th className="text-right px-4 py-3 font-semibold">{t('organisation.colUnitPrice')}</th>
                <th className="text-right px-4 py-3 font-semibold">{t('organisation.colTotal')}</th>
                <th className="text-left px-4 py-3 font-semibold">{t('common.status')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {factures.map(f => (
                <tr key={f.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-900">
                    {new Date(f.period_debut).toLocaleDateString()} → {new Date(f.period_fin).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">{f.sieges_max}</td>
                  <td className="px-4 py-3 text-right">{fmtFCFA(f.prix_unitaire_fcfa)} {f.devise}</td>
                  <td className="px-4 py-3 text-right font-semibold text-gray-900">{fmtFCFA(f.montant_total_fcfa)} {f.devise}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      f.statut === 'paye' ? 'bg-emerald-50 text-emerald-700' :
                      f.statut === 'a_payer' ? 'bg-amber-50 text-amber-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>{t(`organisation.invoiceStatus.${f.statut}`, f.statut)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SettingsTab({ org, onUpdated }: { org: Organisation; onUpdated: () => void }) {
  const { t } = useTranslation()
  const [nom, setNom] = useState(org.nom)
  const [pays, setPays] = useState(org.pays || '')
  const [secteur, setSecteur] = useState(org.secteur || '')
  const [domain, setDomain] = useState(org.domain_auto_join || '')
  const [busy, setBusy] = useState(false)

  const sauvegarder = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await orgsAPI.update(org.id, {
        nom, pays: pays || undefined, secteur: secteur || undefined,
        domain_auto_join: domain.trim().toLowerCase() || undefined,
      })
      toast.success(t('organisation.okUpdated'))
      onUpdated()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || t('common.error'))
    } finally { setBusy(false) }
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5">
      <form onSubmit={sauvegarder} className="space-y-4">
        <Field label={t('organisation.fieldName')}>
          <input value={nom} onChange={e => setNom(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
        </Field>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <CountryPicker label={t('common.country')} value={pays} onChange={setPays} />
          <Field label={t('organisation.fieldSector')}>
            <input value={secteur} onChange={e => setSecteur(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
          </Field>
        </div>
        <Field label={
          <>
            {t('organisation.fieldDomain')}
            {org.domain_verifie
              ? <span className="text-emerald-600 normal-case font-normal text-xs"> · {t('organisation.domainVerified')}</span>
              : <span className="text-amber-600 normal-case font-normal text-xs"> · {t('organisation.domainPending')}</span>}
          </>
        }>
          <input value={domain} onChange={e => setDomain(e.target.value)}
            placeholder="entreprise.com"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
          <p className="text-xs text-gray-500 mt-1">{t('organisation.domainAutoJoinHint')}</p>
        </Field>
        <button type="submit" disabled={busy}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white font-medium px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          {t('common.save')}
        </button>
      </form>
    </div>
  )
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-semibold text-gray-700 mb-1">{label}</label>
      {children}
    </div>
  )
}
