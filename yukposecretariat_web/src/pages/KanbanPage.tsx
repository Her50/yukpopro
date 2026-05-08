import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { KanbanSquare, Plus, Loader2, X, Check, MessageCircle, AlertTriangle } from 'lucide-react'
import { gestionAPI } from '../api/client'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { useTranslation } from 'react-i18next'
import { DemoBanner } from '../components/DemoBanner'

type Statut = 'en_attente' | 'en_cours' | 'en_revision' | 'livre' | 'paye' | 'annule'

const COLONNES: { statut: Statut; labelKey: string; color: string }[] = [
  { statut: 'en_attente', labelKey: 'kanban.colTodo',       color: 'border-gray-400' },
  { statut: 'en_cours',   labelKey: 'kanban.colInProgress', color: 'border-blue-400' },
  { statut: 'en_revision',labelKey: 'kanban.colReview',     color: 'border-yellow-400' },
  { statut: 'livre',      labelKey: 'kanban.colDelivered',  color: 'border-purple-400' },
  { statut: 'paye',       labelKey: 'kanban.colPaid',       color: 'border-green-400' },
]

// Types de travail clarifiés (libellés explicites + couleurs distinctes pour éviter la confusion)
const TYPES_TRAVAIL: { cle: string; labelKey: string; emoji: string; descKey: string; tag: string }[] = [
  { cle: 'redaction_doc', labelKey: 'kanban.typeRedactionDoc', emoji: '📝', descKey: 'kanban.typeRedactionDocDesc', tag: 'bg-blue-100 text-blue-700' },
  { cle: 'saisie',        labelKey: 'kanban.typeSaisie',       emoji: '⌨️', descKey: 'kanban.typeSaisieDesc',       tag: 'bg-slate-100 text-slate-700' },
  { cle: 'scan',          labelKey: 'kanban.typeScan',         emoji: '📷', descKey: 'kanban.typeScanDesc',         tag: 'bg-green-100 text-green-700' },
  { cle: 'audio',         labelKey: 'kanban.typeAudio',        emoji: '🎙', descKey: 'kanban.typeAudioDesc',        tag: 'bg-purple-100 text-purple-700' },
  { cle: 'traduction',    labelKey: 'kanban.typeTraduction',   emoji: '🌐', descKey: 'kanban.typeTraductionDesc',   tag: 'bg-cyan-100 text-cyan-700' },
  { cle: 'infographie',   labelKey: 'kanban.typeInfographie',  emoji: '🎨', descKey: 'kanban.typeInfographieDesc',  tag: 'bg-orange-100 text-orange-700' },
  { cle: 'impression',    labelKey: 'kanban.typeImpression',   emoji: '🖨️', descKey: 'kanban.typeImpressionDesc',   tag: 'bg-amber-100 text-amber-700' },
  { cle: 'autre',         labelKey: 'kanban.typeAutre',        emoji: '📄', descKey: 'kanban.typeAutreDesc',        tag: 'bg-gray-100 text-gray-700' },
]

const tagType   = (cle: string) => TYPES_TRAVAIL.find(t => t.cle === cle)?.tag   || 'bg-gray-100 text-gray-600'

interface BonTravail {
  id: number; client_nom: string; client_whatsapp?: string;
  description: string; type_travail: string;
  statut: Statut; montant_fcfa: number; acompte_fcfa: number; reste_a_payer: number; echeance?: string;
  notif_fin_envoyee?: boolean;
}

function formatFCFA(n: number) { return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA' }

// Validation/normalisation simple côté client (le backend re-valide proprement)
function normaliserWhatsApp(num: string): string {
  let raw = num.trim().replace(/[\s.\-]/g, '')
  if (raw.startsWith('00')) raw = '+' + raw.slice(2)
  if (!raw.startsWith('+')) raw = '+237' + raw
  return raw
}
function whatsAppValide(num: string): boolean {
  const norm = normaliserWhatsApp(num)
  const digits = norm.slice(1).replace(/\D/g, '')
  return digits.length >= 8 && digits.length <= 15
}

export default function KanbanPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [showTerminer, setShowTerminer] = useState<BonTravail | null>(null)
  const [form, setForm] = useState({
    client_nom: '', client_whatsapp: '+237', description: '',
    type_travail: 'redaction_doc', montant_fcfa: 0, acompte_fcfa: 0,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['travaux'],
    queryFn: () => gestionAPI.travaux().then(r => r.data),
  })

  const creerMutation = useMutation({
    mutationFn: async (d: typeof form) => {
      // Normalisation côté client avant envoi (le backend re-normalise aussi)
      const payload = { ...d, client_whatsapp: normaliserWhatsApp(d.client_whatsapp) }
      return gestionAPI.creerTravail(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['travaux'] })
      setShowModal(false); setShowConfirm(false)
      setForm({ client_nom: '', client_whatsapp: '+237', description: '', type_travail: 'redaction_doc', montant_fcfa: 0, acompte_fcfa: 0 })
      toast.success(t('kanban.okCreate'))
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || t('kanban.errCreate')
      toast.error(typeof msg === 'string' ? msg : t('kanban.errCreate'))
    },
  })

  const modifierStatut = useMutation({
    mutationFn: ({ id, statut }: { id: number; statut: string }) =>
      gestionAPI.modifierTravail(id, { statut }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['travaux'] }),
  })

  const terminerMutation = useMutation({
    mutationFn: ({ id, message_personnalise, envoyer_whatsapp }: { id: number; message_personnalise?: string; envoyer_whatsapp: boolean }) =>
      gestionAPI.terminerTravail(id, { message_personnalise, envoyer_whatsapp }).then(r => r.data),
    onSuccess: (res: any) => {
      qc.invalidateQueries({ queryKey: ['travaux'] })
      setShowTerminer(null)
      if (res?.whatsapp_envoye) {
        toast.success(t('kanban.completed') + ' · WhatsApp ✓')
      } else if (res?.whatsapp_raison) {
        toast(`${t('kanban.completed')} · ${t('kanban.whatsappNotSent', { reason: res.whatsapp_raison.slice(0, 80) })}`, { icon: '⚠️' })
      } else {
        toast.success(t('kanban.completed'))
      }
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || t('kanban.errEnd'))
    },
  })

  const travaux: BonTravail[] = data?.travaux ?? []
  const parColonne = (statut: Statut) => travaux.filter(t => t.statut === statut)

  const prochainStatut = (statut: Statut): Statut | null => {
    const ordre: Statut[] = ['en_attente', 'en_cours', 'en_revision', 'livre', 'paye']
    const idx = ordre.indexOf(statut)
    return idx >= 0 && idx < ordre.length - 1 ? ordre[idx + 1] : null
  }

  const formValide = form.client_nom.trim().length >= 2
    && form.description.trim().length >= 2
    && whatsAppValide(form.client_whatsapp)

  // Étape de validation : ouvre la pop-up de confirmation
  const tenterCreer = () => {
    if (!formValide) {
      if (!whatsAppValide(form.client_whatsapp)) toast.error(t('kanban.errInvalidWhatsapp'))
      else toast.error(t('kanban.errFillRequired'))
      return
    }
    setShowConfirm(true)
  }

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <KanbanSquare className="text-indigo-600" size={24} />
            {t('kanban.title')}
          </h1>
          <p className="text-gray-500 text-sm mt-1">{t('kanban.tasksCount', { n: travaux.length })}</p>
        </div>
        <button onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2.5 rounded-xl text-sm transition-colors">
          <Plus size={18} /> {t('kanban.newTask')}
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><Loader2 size={24} className="animate-spin text-indigo-600" /></div>
      ) : (
        <div className="overflow-x-auto pb-2">
          <div className="flex gap-4 min-w-max">
            {COLONNES.map(({ statut, labelKey, color }) => {
              const bons = parColonne(statut)
              return (
                <div key={statut} className="w-72 shrink-0">
                  <div className={clsx('border-t-4 rounded-t-lg px-3 py-2 bg-white shadow-sm', color)}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-gray-700">{t(labelKey)}</span>
                      <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{bons.length}</span>
                    </div>
                  </div>
                  <div className="space-y-2 mt-2 min-h-32">
                    {bons.map(b => {
                      const next = prochainStatut(b.statut)
                      const peutTerminer = (b.statut === 'en_cours' || b.statut === 'en_revision' || b.statut === 'en_attente')
                      return (
                        <div key={b.id} className="bg-white rounded-xl p-3 shadow-sm border border-gray-100 space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="font-semibold text-sm text-gray-900 truncate">{b.client_nom}</div>
                              {b.client_whatsapp && (
                                <div className="text-[10px] text-gray-400 flex items-center gap-1 mt-0.5">
                                  <MessageCircle size={10} className="text-green-500" />
                                  {b.client_whatsapp}
                                </div>
                              )}
                            </div>
                            <span className={clsx('text-[10px] px-2 py-0.5 rounded-full font-medium shrink-0', tagType(b.type_travail))}>
                              {(() => { const tt = TYPES_TRAVAIL.find(x => x.cle === b.type_travail); return tt ? t(tt.labelKey) : b.type_travail })()}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500 line-clamp-2">{b.description}</div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-gray-700">{formatFCFA(b.montant_fcfa)}</span>
                            {b.reste_a_payer > 0 && (
                              <span className="text-orange-500">{t('kanban.remaining')} {formatFCFA(b.reste_a_payer)}</span>
                            )}
                          </div>
                          {b.notif_fin_envoyee && (
                            <div className="text-[10px] text-green-600 flex items-center gap-1">
                              <Check size={10} /> {t('kanban.clientNotified')}
                            </div>
                          )}
                          <div className="flex gap-1.5">
                            {next && (
                              <button onClick={() => modifierStatut.mutate({ id: b.id, statut: next })}
                                className="flex-1 text-xs py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-600 font-medium flex items-center justify-center gap-1">
                                <Check size={11} /> {next.replace('_', ' ')}
                              </button>
                            )}
                            {peutTerminer && (
                              <button onClick={() => setShowTerminer(b)}
                                className="text-xs py-1.5 px-2 rounded-lg bg-green-50 hover:bg-green-100 text-green-600 font-medium flex items-center gap-1"
                                title={t('kanban.complete')}>
                                <MessageCircle size={11} />
                                {t('kanban.complete')}
                              </button>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Modal création */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-5 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h2 className="font-bold text-gray-900">{t('kanban.newTask')}</h2>
              <button onClick={() => setShowModal(false)}><X size={20} className="text-gray-400" /></button>
            </div>

            <Field label={t('kanban.clientName')}>
              <input type="text" value={form.client_nom}
                onChange={e => setForm(f => ({ ...f, client_nom: e.target.value }))}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>

            <Field label={t('kanban.clientWhatsapp')}>
              <input type="tel" value={form.client_whatsapp}
                onChange={e => setForm(f => ({ ...f, client_whatsapp: e.target.value }))}
                placeholder={t('kanban.whatsappPlaceholder')}
                className={clsx(
                  "w-full border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2",
                  form.client_whatsapp.length > 4 && !whatsAppValide(form.client_whatsapp)
                    ? "border-red-300 focus:ring-red-500"
                    : "border-gray-300 focus:ring-indigo-500"
                )} />
              <p className="text-xs text-gray-400 mt-1">
                {t('kanban.whatsappFormatHint')}
              </p>
              {form.client_whatsapp.length > 4 && !whatsAppValide(form.client_whatsapp) && (
                <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                  <AlertTriangle size={11} /> {t('kanban.invalidNumber')}
                </p>
              )}
            </Field>

            <Field label={t('kanban.workDescription')}>
              <textarea rows={2} value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
            </Field>

            <Field label={t('kanban.workType')}>
              <div className="grid grid-cols-2 gap-2">
                {TYPES_TRAVAIL.map(tt => (
                  <button key={tt.cle} type="button"
                    onClick={() => setForm(f => ({ ...f, type_travail: tt.cle }))}
                    className={clsx(
                      "text-left p-2 rounded-lg border transition-colors",
                      form.type_travail === tt.cle
                        ? "border-indigo-500 bg-indigo-50"
                        : "border-gray-200 hover:border-gray-300"
                    )}>
                    <div className="text-xs font-semibold flex items-center gap-1.5">
                      <span>{tt.emoji}</span> {t(tt.labelKey)}
                    </div>
                    <div className="text-[10px] text-gray-400 mt-0.5 leading-tight">{t(tt.descKey)}</div>
                  </button>
                ))}
              </div>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label={t('kanban.amountFcfa')}>
                <input type="number" min={0} value={form.montant_fcfa}
                  onChange={e => setForm(f => ({ ...f, montant_fcfa: +e.target.value }))}
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </Field>
              <Field label={t('kanban.advance')}>
                <input type="number" min={0} value={form.acompte_fcfa}
                  onChange={e => setForm(f => ({ ...f, acompte_fcfa: +e.target.value }))}
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </Field>
            </div>

            <button onClick={tenterCreer} disabled={creerMutation.isPending || !formValide}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 rounded-xl disabled:opacity-60 flex items-center justify-center gap-2">
              {creerMutation.isPending && <Loader2 size={16} className="animate-spin" />}
              {t('kanban.createTask')}
            </button>
          </div>
        </div>
      )}

      {/* Modal confirmation WhatsApp avant création */}
      {showConfirm && (
        <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-5 space-y-4">
            <div className="flex items-center gap-2 text-amber-500">
              <AlertTriangle size={22} />
              <h3 className="font-bold text-gray-900">{t('kanban.confirmModalTitle')}</h3>
            </div>
            <p
              className="text-sm text-gray-600"
              dangerouslySetInnerHTML={{ __html: t('kanban.confirmModalDesc') }}
            />
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
              <div className="text-xs text-green-600 font-semibold uppercase">{t('kanban.whatsappLabel')}</div>
              <div className="text-2xl font-bold text-green-700 mt-1 font-mono">
                {normaliserWhatsApp(form.client_whatsapp)}
              </div>
              <div className="text-xs text-gray-500 mt-1">{t('kanban.clientLabel')} : {form.client_nom}</div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowConfirm(false)}
                className="flex-1 py-2.5 rounded-xl border border-gray-300 text-gray-600 font-medium">
                {t('common.edit')}
              </button>
              <button onClick={() => creerMutation.mutate(form)} disabled={creerMutation.isPending}
                className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold flex items-center justify-center gap-1.5 disabled:opacity-60">
                {creerMutation.isPending && <Loader2 size={14} className="animate-spin" />}
                <Check size={14} /> {t('kanban.confirmAndCreate')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal terminer + notifier */}
      {showTerminer && (
        <ModalTerminer bon={showTerminer}
          onClose={() => setShowTerminer(null)}
          onConfirm={(message_personnalise, envoyer_whatsapp) =>
            terminerMutation.mutate({ id: showTerminer.id, message_personnalise, envoyer_whatsapp: !!envoyer_whatsapp })}
          loading={terminerMutation.isPending} />
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      {children}
    </div>
  )
}

function ModalTerminer({ bon, onClose, onConfirm, loading }:
  { bon: BonTravail; onClose: () => void; onConfirm: (msg?: string, envoyer?: boolean) => void; loading: boolean }) {
  const { t } = useTranslation()
  const [message, setMessage] = useState('')
  const [envoyer, setEnvoyer] = useState(true)
  const reste = bon.montant_fcfa - bon.acompte_fcfa
  const paymentLine = reste > 0
    ? t('kanban.remainingDue', { amount: formatFCFA(reste) })
    : t('kanban.paymentUpToDate')
  const messageDefaut = t('kanban.messageDefault', {
    name: bon.client_nom,
    desc: bon.description.slice(0, 80),
    paymentLine,
  })

  return (
    <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-md p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-gray-900 flex items-center gap-2">
            <Check size={18} className="text-green-600" /> {t('kanban.completeWork')}
          </h3>
          <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
        </div>

        <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1">
          <div><strong>{t('kanban.clientLabel')} :</strong> {bon.client_nom}</div>
          <div><strong>{t('kanban.descriptionLabel')} :</strong> {bon.description}</div>
          {bon.client_whatsapp && (
            <div className="flex items-center gap-1 text-green-700">
              <MessageCircle size={12} /> <strong>{t('kanban.whatsappLabel')} :</strong> {bon.client_whatsapp}
            </div>
          )}
        </div>

        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={envoyer} onChange={e => setEnvoyer(e.target.checked)}
            className="w-4 h-4 text-green-600 rounded" />
          <span>{t('kanban.notifyClientWhatsapp')}</span>
        </label>

        {envoyer && (
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">
              {t('kanban.messageLabel')} <span className="text-gray-400 font-normal">{t('kanban.messageDefaultHint')}</span>
            </label>
            <textarea rows={6} value={message}
              onChange={e => setMessage(e.target.value)}
              placeholder={messageDefaut}
              className="w-full border border-gray-300 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-green-500 resize-none" />
          </div>
        )}

        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-gray-300 text-gray-600 font-medium">{t('common.cancel')}</button>
          <button onClick={() => onConfirm(message.trim() || undefined, envoyer)} disabled={loading}
            className="flex-1 py-2.5 rounded-xl bg-green-600 hover:bg-green-700 text-white font-semibold flex items-center justify-center gap-1.5 disabled:opacity-60">
            {loading && <Loader2 size={14} className="animate-spin" />}
            <Check size={14} />
            {envoyer ? t('kanban.completeAndNotify') : t('kanban.complete')}
          </button>
        </div>
      </div>
    </div>
  )
}
