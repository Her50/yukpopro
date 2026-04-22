/**
 * CorrespondancesModule — Composant partagé de gestion des correspondances
 *
 * Fonctionnalités :
 * - En-tête / pied de page compagnie (tiré du branding configuré dans Paramètres)
 * - Templates par module (sinistres, souscription, réassurance, comptabilité, juridique)
 * - Génération IA via Yukpo
 * - Export PDF (impression navigateur) et Word (.doc HTML)
 * - Workflow hiérarchique : Brouillon → N+1 → Direction → Approuvé → Envoyé
 * - Historique des correspondances du module
 */
import { useState, useRef, useCallback } from 'react'
import {
  SparklesIcon, ArrowDownTrayIcon, PrinterIcon, PaperAirplaneIcon,
  CheckCircleIcon, ClockIcon, XMarkIcon, ArrowPathIcon,
  DocumentTextIcon, PencilSquareIcon, UserCircleIcon,
  ChevronRightIcon, ExclamationTriangleIcon, DocumentArrowDownIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { useCompagnieStore, BrandingCompagnie } from '../store/compagnieStore'
import { apiClient } from '../api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

export type ModuleCorrespondance =
  | 'sinistres'
  | 'souscription'
  | 'reassurance'
  | 'comptabilite'
  | 'juridique'
  | 'rh'

type StatutLettre = 'brouillon' | 'en_validation' | 'approuve' | 'rejete' | 'envoye'

interface CircuitEtape {
  role: string
  nom: string
  statut: 'en_attente' | 'approuve' | 'rejete' | 'actif'
  commentaire?: string
  date?: string
}

interface LettreHistorique {
  id: string
  templateId: string
  templateLabel: string
  reference: string
  destinataire: string
  dateCreation: string
  statut: StatutLettre
  circuit: CircuitEtape[]
  contenu: string
  auteur: string
}

// ─── Templates par module ─────────────────────────────────────────────────────

const TEMPLATES_PAR_MODULE: Record<ModuleCorrespondance, { id: string; label: string; icon: string; description: string; contexte_ia: string }[]> = {
  sinistres: [
    { id: 'accuse_reception', label: 'Accusé de réception', icon: '📬', description: 'Confirmer la réception du dossier', contexte_ia: 'sinistre reçu, en cours d\'instruction' },
    { id: 'demande_pieces', label: 'Demande de pièces', icon: '📋', description: 'Demander des documents manquants', contexte_ia: 'pièces complémentaires manquantes' },
    { id: 'notification_reglement', label: 'Notification de règlement', icon: '✅', description: 'Informer du règlement', contexte_ia: 'sinistre réglé, virement en cours' },
    { id: 'rejet', label: 'Lettre de rejet', icon: '❌', description: 'Notifier le rejet avec motivations', contexte_ia: 'rejet pour exclusion contractuelle ou non-conformité' },
    { id: 'convocation_expertise', label: 'Convocation expertise', icon: '🔍', description: 'Convoquer pour expertise contradictoire', contexte_ia: 'expertise nécessaire, date et lieu à préciser' },
    { id: 'mise_demeure_tiers', label: 'Mise en demeure tiers', icon: '⚖️', description: 'Mise en demeure du tiers responsable', contexte_ia: 'recours subrogatoire contre tiers responsable' },
    { id: 'prolongation_delai', label: 'Prolongation de délai', icon: '⏳', description: 'Notifier une prolongation d\'instruction', contexte_ia: 'dossier complexe nécessitant investigations' },
  ],
  souscription: [
    { id: 'bienvenue', label: 'Lettre de bienvenue', icon: '🤝', description: 'Accueillir un nouveau souscripteur', contexte_ia: 'nouveau contrat souscrit' },
    { id: 'avenant', label: 'Notification d\'avenant', icon: '📝', description: 'Notifier une modification de contrat', contexte_ia: 'modification des garanties ou du montant' },
    { id: 'resiliation', label: 'Accusé de résiliation', icon: '🔚', description: 'Confirmer la résiliation du contrat', contexte_ia: 'résiliation à l\'échéance ou en cours d\'année' },
    { id: 'renouvellement', label: 'Avis de renouvellement', icon: '🔄', description: 'Notifier le renouvellement annuel', contexte_ia: 'renouvellement avec nouvelle prime' },
    { id: 'offre_produit', label: 'Offre commerciale', icon: '💼', description: 'Présenter une offre de produit', contexte_ia: 'offre personnalisée basée sur le profil' },
    { id: 'attestation', label: 'Attestation d\'assurance', icon: '📜', description: 'Délivrer une attestation', contexte_ia: 'attestation de couverture en cours' },
  ],
  reassurance: [
    { id: 'notification_cession', label: 'Notification de cession', icon: '📤', description: 'Notifier la cession au réassureur', contexte_ia: 'bordereau de primes cédées' },
    { id: 'demande_recuperation', label: 'Demande de récupération', icon: '💰', description: 'Demander remboursement sinistre', contexte_ia: 'sinistre relevant du traité de réassurance' },
    { id: 'accord_traite', label: 'Accord de traité', icon: '🤝', description: 'Confirmer les termes d\'un traité', contexte_ia: 'nouveau traité ou renouvellement annuel' },
    { id: 'avis_sinistre_reassureur', label: 'Avis au réassureur', icon: '🔔', description: 'Notifier un sinistre important', contexte_ia: 'sinistre dépassant la pleine rétention' },
  ],
  comptabilite: [
    { id: 'relance_paiement', label: 'Relance de paiement', icon: '💸', description: 'Relancer une prime impayée', contexte_ia: 'prime de renouvellement impayée depuis X jours' },
    { id: 'mise_en_recouvrement', label: 'Mise en recouvrement', icon: '⚠️', description: 'Notifier la mise en recouvrement', contexte_ia: 'retard de paiement important, action juridique' },
    { id: 'recu_paiement', label: 'Reçu de paiement', icon: '🧾', description: 'Confirmer la réception d\'un paiement', contexte_ia: 'règlement reçu en comptabilité' },
    { id: 'rapport_financier', label: 'Rapport financier', icon: '📊', description: 'Transmettre un rapport financier', contexte_ia: 'bilan ou état financier trimestriel' },
    { id: 'demande_regularisation', label: 'Demande de régularisation', icon: '🔧', description: 'Demander une régularisation comptable', contexte_ia: 'écart constaté dans les comptes' },
  ],
  juridique: [
    { id: 'mise_en_demeure', label: 'Mise en demeure', icon: '⚖️', description: 'Mettre en demeure de s\'exécuter', contexte_ia: 'obligation contractuelle non respectée, délai formel' },
    { id: 'assignation', label: 'Assignation en justice', icon: '🏛️', description: 'Acte introductif d\'instance', contexte_ia: 'procédure judiciaire, assignation devant tribunal' },
    { id: 'accord_amiable', label: 'Accord de règlement amiable', icon: '🤝', description: 'Formaliser un accord amiable', contexte_ia: 'transaction amiable, compromis trouvé' },
    { id: 'recours_cima', label: 'Notification recours CIMA', icon: '📣', description: 'Notifier un recours Commission CIMA', contexte_ia: 'recours réglementaire auprès Commission régionale' },
    { id: 'convention_subrogation', label: 'Convention de subrogation', icon: '🔄', description: 'Formaliser la subrogation', contexte_ia: 'transfert de créance par subrogation' },
    { id: 'transaction', label: 'Protocole transactionnel', icon: '📄', description: 'Protocole de transaction', contexte_ia: 'protocole mettant fin au litige' },
    { id: 'appel', label: 'Mémoire d\'appel', icon: '📮', description: 'Mémoire pour procédure d\'appel', contexte_ia: 'appel de la décision de première instance' },
    { id: 'requete_arbitrage', label: 'Requête en arbitrage', icon: '🧑‍⚖️', description: 'Saisir le comité d\'arbitrage', contexte_ia: 'arbitrage CIMA ou clause compromissoire' },
  ],
  rh: [
    { id: 'convocation_entretien', label: 'Convocation entretien', icon: '👥', description: 'Convoquer à un entretien', contexte_ia: 'entretien professionnel ou disciplinaire' },
    { id: 'lettre_sanction', label: 'Lettre de sanction', icon: '⚠️', description: 'Notifier une sanction disciplinaire', contexte_ia: 'sanction suite à faute professionnelle' },
    { id: 'contrat_travail', label: 'Contrat de travail', icon: '📋', description: 'Émettre un contrat de travail', contexte_ia: 'embauche nouveau collaborateur' },
    { id: 'attestation_travail', label: 'Attestation de travail', icon: '📜', description: 'Délivrer une attestation', contexte_ia: 'attestation emploi et rémunération' },
    { id: 'promotion', label: 'Lettre de promotion', icon: '🎖️', description: 'Notifier une promotion', contexte_ia: 'évolution de poste et de rémunération' },
  ],
}

// ─── Circuit hiérarchique ─────────────────────────────────────────────────────

const CIRCUIT_DEFAULT: CircuitEtape[] = [
  { role: 'Rédacteur', nom: 'Moi', statut: 'approuve' },
  { role: 'Responsable N+1', nom: 'Coulibaly Seydou', statut: 'en_attente' },
  { role: 'Direction', nom: 'Direction Générale', statut: 'en_attente' },
]

const STATUT_CFG: Record<StatutLettre, { label: string; classes: string; icon: React.ReactNode }> = {
  brouillon: { label: 'Brouillon', classes: 'bg-gray-100 text-gray-600', icon: <PencilSquareIcon className="h-3.5 w-3.5" /> },
  en_validation: { label: 'En validation', classes: 'bg-amber-100 text-amber-700', icon: <ClockIcon className="h-3.5 w-3.5" /> },
  approuve: { label: 'Approuvé', classes: 'bg-green-100 text-green-700', icon: <CheckCircleIcon className="h-3.5 w-3.5" /> },
  rejete: { label: 'Rejeté', classes: 'bg-red-100 text-red-700', icon: <XMarkIcon className="h-3.5 w-3.5" /> },
  envoye: { label: 'Envoyé', classes: 'bg-blue-100 text-blue-700', icon: <PaperAirplaneIcon className="h-3.5 w-3.5" /> },
}

// ─── Utilitaires ──────────────────────────────────────────────────────────────

function genererLettreDemo(
  templateId: string,
  reference: string,
  destinataire: string,
  contexte: string,
  branding: BrandingCompagnie
): string {
  const today = new Date().toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' })
  const ville = 'Douala'
  const ouverture = `Monsieur/Madame ${destinataire},`

  const corps: Record<string, string> = {
    accuse_reception: `Nous accusons bonne réception de votre déclaration de sinistre enregistrée sous la référence ${reference}.\n\nVotre dossier a été ouvert et sera instruit par notre service sinistres dans les meilleurs délais.\n\nConformément aux dispositions du Code CIMA (article 12), la compagnie dispose de 30 jours pour vous communiquer sa position définitive.\n\nNous vous tiendrons informé(e) de l'avancement de votre dossier et vous contacterons si des pièces complémentaires s'avèrent nécessaires.`,
    demande_pieces: `Suite à l'examen de votre dossier ${reference}, nous avons le regret de vous informer que votre dossier est incomplet.\n\nAfin de poursuivre l'instruction de votre dossier, nous vous prions de bien vouloir nous faire parvenir les pièces suivantes :\n\n  • ${contexte || 'Documents justificatifs complémentaires'}\n  • Relevé d'identité bancaire (RIB) original\n  • Justificatif de propriété ou de valeur\n\nNous vous remercions de nous adresser ces pièces dans un délai de 15 jours à compter de la présente.`,
    notification_reglement: `Nous avons le plaisir de vous informer que votre dossier sinistre référence ${reference} a été clôturé favorablement.\n\nMontant de l'indemnisation retenu : ${contexte || 'selon décision de règlement'}\n\nLe règlement sera effectué par virement bancaire sur le compte que vous nous avez communiqué dans un délai de 5 jours ouvrables.\n\nNous vous remercions de la confiance que vous nous témoignez.`,
    rejet: `Après examen approfondi de votre dossier de sinistre référencé ${reference}, nous avons le regret de vous informer que votre demande d'indemnisation ne peut être prise en charge.\n\nMotifs du rejet :\n  • ${contexte || 'Non-conformité aux conditions générales du contrat'}\n  • Exclusion contractuelle applicable\n\nConformément à l'article 18 du Code CIMA, vous disposez de voies de recours. Vous pouvez notamment saisir la Commission Régionale de Contrôle des Assurances (CRCA) dans un délai de 60 jours.`,
    mise_en_demeure: `Par la présente, nous vous mettons formellement en demeure de vous acquitter de vos obligations contractuelles concernant le dossier ${reference}.\n\nMontant ou obligation en cause : ${contexte || 'à préciser'}\n\nNous vous accordons un délai de 8 jours calendaires à compter de la réception de la présente pour satisfaire à cette obligation.\n\nPassé ce délai, nous nous réservons le droit de prendre toutes mesures judiciaires et extrajudiciaires pour le recouvrement de notre créance, sans autres formalités.`,
    bienvenue: `C'est avec un grand plaisir que nous vous accueillons parmi les clients de ${branding.nom}.\n\nVotre contrat d'assurance référence ${reference} est maintenant en vigueur. Vous bénéficiez désormais des garanties souscrites, dans les conditions définies aux conditions générales et particulières de votre police.\n\n${contexte || 'Votre conseiller attitré reste à votre disposition pour toute question.'}\n\nNous vous souhaitons la bienvenue et nous nous engageons à vous offrir un service de qualité tout au long de notre relation.`,
    relance_paiement: `Sauf erreur ou omission de notre part, notre comptabilité n'a pas enregistré le règlement de votre prime d'assurance référence ${reference}.\n\nMontant dû : ${contexte || 'à préciser'}\n\nNous vous prions de bien vouloir régulariser votre situation dans un délai de 8 jours.\n\nPassé ce délai, nous serions dans l'obligation de procéder à la suspension des garanties prévue par le Code CIMA, puis à la résiliation de votre contrat.`,
    assignation: `Par acte d'huissier de justice, la compagnie ${branding.nom} a l'honneur de vous assigner à comparaître devant le Tribunal compétent aux fins de :\n\n${contexte || 'condamnation au paiement des sommes dues avec intérêts légaux'}\n\nDossier référence : ${reference}\n\nNous vous informons que cette procédure est fondée sur les dispositions du Code CIMA et du droit commun des contrats. Vous êtes invité(e) à vous faire représenter par un conseil de votre choix.`,
    accord_amiable: `Suite aux négociations intervenues entre les parties concernant le dossier ${reference}, nous avons le plaisir de vous confirmer les termes de l'accord transactionnel suivant :\n\n${contexte || 'montant et modalités de règlement convenus entre les parties'}\n\nCet accord met définitivement fin au litige entre les parties, lesquelles se donnent mutuellement quittance et acquit de toutes leurs prétentions respectives liées au présent dossier.\n\nNous vous prions de bien vouloir signer et nous retourner un exemplaire du présent accord pour vaut accord.`,
  }

  const corpDefault = `En référence au dossier ${reference}, nous vous adressons la présente correspondance.\n\n${contexte || 'Veuillez trouver ci-après les informations relatives à votre dossier.'}\n\nNous restons à votre entière disposition pour tout renseignement complémentaire.`

  return `${ville}, le ${today}

Notre référence : ${reference}
Votre référence : —

${ouverture}

${corps[templateId] || corpDefault}

Veuillez agréer, Monsieur/Madame, l'expression de nos salutations distinguées.

${branding.nom}
Le Directeur Général

___________________________
${branding.nom}
${branding.telephone_support ? `Tél : ${branding.telephone_support}` : ''}
${branding.email_support ? `Email : ${branding.email_support}` : ''}
${branding.site_web ? `Web : ${branding.site_web}` : ''}`
}

// ─── Composant EntêteCompagnie ─────────────────────────────────────────────────

function EnteteCompagnie({ branding }: { branding: BrandingCompagnie }) {
  return (
    <div className="border-b-2 pb-4 mb-4" style={{ borderColor: branding.couleur_primaire }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {branding.logo_url ? (
            <img src={branding.logo_url} alt={branding.nom} className="h-12 w-auto object-contain" />
          ) : (
            <div className="h-12 w-12 rounded-lg flex items-center justify-center text-white text-xl font-bold"
              style={{ backgroundColor: branding.couleur_primaire }}>
              {branding.nom.charAt(0)}
            </div>
          )}
          <div>
            <p className="font-bold text-lg" style={{ color: branding.couleur_primaire }}>{branding.nom}</p>
            {branding.slogan && <p className="text-xs text-gray-500">{branding.slogan}</p>}
          </div>
        </div>
        <div className="text-right text-xs text-gray-500 space-y-0.5">
          {branding.telephone_support && <p>Tél : {branding.telephone_support}</p>}
          {branding.email_support && <p>{branding.email_support}</p>}
          {branding.site_web && <p>{branding.site_web}</p>}
        </div>
      </div>
    </div>
  )
}

function PiedPageCompagnie({ branding }: { branding: BrandingCompagnie }) {
  return (
    <div className="border-t pt-3 mt-4 text-center text-xs text-gray-400" style={{ borderColor: branding.couleur_primaire + '40' }}>
      <p>{branding.nom} — Société d'Assurance agréée — Zone CIMA</p>
      {(branding.telephone_support || branding.email_support) && (
        <p className="mt-0.5">
          {branding.telephone_support && `Tél : ${branding.telephone_support}`}
          {branding.telephone_support && branding.email_support && ' | '}
          {branding.email_support && branding.email_support}
        </p>
      )}
    </div>
  )
}

// ─── Modal Circuit Hiérarchique ────────────────────────────────────────────────

function ModalValidation({
  lettre,
  onClose,
  onSoumettre,
  onApprouver,
  onRejeter,
}: {
  lettre: LettreHistorique | null
  onClose: () => void
  onSoumettre: (id: string) => void
  onApprouver: (id: string, commentaire: string) => void
  onRejeter: (id: string, commentaire: string) => void
}) {
  const [commentaire, setCommentaire] = useState('')
  if (!lettre) return null

  const etapeActive = lettre.circuit.findIndex(e => e.statut === 'en_attente' || e.statut === 'actif')

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-lg w-full shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b">
          <h3 className="font-bold text-gray-900">Circuit de validation</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Circuit */}
          <div className="flex items-center gap-2">
            {lettre.circuit.map((e, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="text-center">
                  <div className={clsx('w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold',
                    e.statut === 'approuve' ? 'bg-green-100 text-green-700' :
                    e.statut === 'rejete' ? 'bg-red-100 text-red-700' :
                    e.statut === 'actif' ? 'bg-amber-100 text-amber-700 ring-2 ring-amber-400' :
                    'bg-gray-100 text-gray-400')}>
                    {e.statut === 'approuve' ? '✓' : e.statut === 'rejete' ? '✗' : i + 1}
                  </div>
                  <p className="text-xs text-gray-500 mt-1 whitespace-nowrap">{e.role}</p>
                  <p className="text-xs font-medium text-gray-700">{e.nom}</p>
                  {e.commentaire && <p className="text-xs text-amber-600 italic max-w-20 truncate">{e.commentaire}</p>}
                </div>
                {i < lettre.circuit.length - 1 && <ChevronRightIcon className="h-4 w-4 text-gray-300 flex-shrink-0" />}
              </div>
            ))}
          </div>

          {/* Actions */}
          {lettre.statut === 'brouillon' && (
            <button onClick={() => onSoumettre(lettre.id)}
              className="w-full bg-amber-500 text-white py-2.5 rounded-xl text-sm font-semibold hover:bg-amber-600">
              Soumettre pour validation →
            </button>
          )}

          {lettre.statut === 'en_validation' && etapeActive >= 0 && (
            <div className="space-y-3">
              <p className="text-sm text-gray-600">
                En attente de : <strong>{lettre.circuit[etapeActive]?.nom}</strong> ({lettre.circuit[etapeActive]?.role})
              </p>
              <textarea
                className="w-full border border-gray-300 rounded-lg p-3 text-sm resize-none"
                rows={2}
                placeholder="Commentaire / annotation (optionnel)…"
                value={commentaire}
                onChange={e => setCommentaire(e.target.value)}
              />
              <div className="grid grid-cols-2 gap-3">
                <button onClick={() => onApprouver(lettre.id, commentaire)}
                  className="flex items-center justify-center gap-2 bg-green-600 text-white py-2.5 rounded-xl text-sm font-semibold hover:bg-green-700">
                  <CheckCircleIcon className="h-4 w-4" /> Approuver
                </button>
                <button onClick={() => onRejeter(lettre.id, commentaire)}
                  className="flex items-center justify-center gap-2 border border-red-300 text-red-600 py-2.5 rounded-xl text-sm font-semibold hover:bg-red-50">
                  <XMarkIcon className="h-4 w-4" /> Rejeter / Annoter
                </button>
              </div>
            </div>
          )}

          {lettre.statut === 'approuve' && (
            <div className="bg-green-50 rounded-xl p-3 text-sm text-green-700 flex items-center gap-2">
              <CheckCircleIcon className="h-5 w-5" />
              Lettre approuvée — prête à l'envoi
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Composant principal ──────────────────────────────────────────────────────

interface Props {
  module: ModuleCorrespondance
  /** Références disponibles pour lier la lettre (numéros dossiers, polices, etc.) */
  references?: { value: string; label: string }[]
  /** Titre optionnel de section */
  titre?: string
}

export function CorrespondancesModule({ module, references = [], titre }: Props) {
  const { branding } = useCompagnieStore()
  const templates = TEMPLATES_PAR_MODULE[module] || []

  const [templateChoisi, setTemplateChoisi] = useState<string | null>(null)
  const [reference, setReference] = useState(references[0]?.value || '')
  const [destinataire, setDestinataire] = useState('')
  const [contexte, setContexte] = useState('')
  const [lettre, setLettre] = useState('')
  const [loading, setLoading] = useState(false)
  const [historique, setHistorique] = useState<LettreHistorique[]>([])
  const [modalLettre, setModalLettre] = useState<LettreHistorique | null>(null)
  const [vue, setVue] = useState<'composer' | 'historique'>('composer')
  const [previewMode, setPreviewMode] = useState(false)
  const previewRef = useRef<HTMLDivElement>(null)

  const template = templates.find(t => t.id === templateChoisi)

  const genererLettre = useCallback(async () => {
    if (!templateChoisi) return
    setLoading(true)
    try {
      const { data } = await apiClient.post('/api/v1/chat/message', {
        message: `Rédige une lettre professionnelle formelle de type "${template?.label}" pour le dossier ${reference || 'N/A'} (${module}). Destinataire : ${destinataire || 'Monsieur/Madame'}. Contexte : ${contexte || template?.contexte_ia}. Entêtes : ${branding.nom}, Zone CIMA. Format professionnel, formules de politesse africaines, références réglementaires CIMA appropriées.`,
        stream: false,
      })
      const d = data as Record<string, unknown>
      setLettre((d.response as string) || (d.content as string) || '')
    } catch {
      setLettre(genererLettreDemo(templateChoisi, reference, destinataire, contexte, branding))
    } finally {
      setLoading(false)
    }
  }, [templateChoisi, reference, destinataire, contexte, branding, module, template])

  const enregistrerBrouillon = () => {
    if (!lettre || !template) return
    const nouvelle: LettreHistorique = {
      id: Date.now().toString(),
      templateId: template.id,
      templateLabel: template.label,
      reference: reference || '—',
      destinataire: destinataire || 'Destinataire',
      dateCreation: new Date().toISOString(),
      statut: 'brouillon',
      circuit: JSON.parse(JSON.stringify(CIRCUIT_DEFAULT)),
      contenu: lettre,
      auteur: 'Moi',
    }
    setHistorique(prev => [nouvelle, ...prev])
    setVue('historique')
    setLettre('')
    setTemplateChoisi(null)
  }

  const soumettre = (id: string) => {
    setHistorique(prev => prev.map(l => l.id === id ? {
      ...l,
      statut: 'en_validation' as StatutLettre,
      circuit: l.circuit.map((e, i) => i === 1 ? { ...e, statut: 'actif' as const } : e),
    } : l))
    setModalLettre(prev => prev?.id === id ? { ...prev, statut: 'en_validation', circuit: prev.circuit.map((e, i) => i === 1 ? { ...e, statut: 'actif' as const } : e) } : prev)
  }

  const approuver = (id: string, commentaire: string) => {
    setHistorique(prev => prev.map(l => {
      if (l.id !== id) return l
      const etapeIdx = l.circuit.findIndex(e => e.statut === 'actif')
      const newCircuit = l.circuit.map((e, i) => {
        if (i === etapeIdx) return { ...e, statut: 'approuve' as const, commentaire, date: new Date().toLocaleDateString('fr-FR') }
        if (i === etapeIdx + 1) return { ...e, statut: 'actif' as const }
        return e
      })
      const tousApprouves = newCircuit.filter((_, i) => i > 0).every(e => e.statut === 'approuve')
      return { ...l, circuit: newCircuit, statut: tousApprouves ? 'approuve' as StatutLettre : 'en_validation' as StatutLettre }
    }))
    setModalLettre(null)
  }

  const rejeter = (id: string, commentaire: string) => {
    setHistorique(prev => prev.map(l => {
      if (l.id !== id) return l
      const etapeIdx = l.circuit.findIndex(e => e.statut === 'actif')
      return {
        ...l,
        statut: 'rejete' as StatutLettre,
        circuit: l.circuit.map((e, i) => i === etapeIdx ? { ...e, statut: 'rejete' as const, commentaire, date: new Date().toLocaleDateString('fr-FR') } : e),
      }
    }))
    setModalLettre(null)
  }

  const exporterPDF = () => {
    const today = new Date().toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' })
    const htmlContent = `
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>${template?.label || 'Correspondance'} — ${reference}</title>
<style>
  body { font-family: 'Times New Roman', serif; font-size: 12pt; margin: 2cm; color: #000; }
  .entete { border-bottom: 2px solid ${branding.couleur_primaire}; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-start; }
  .entete-gauche { display: flex; align-items: center; gap: 12px; }
  .entete-logo { width: 48px; height: 48px; background: ${branding.couleur_primaire}; color: white; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold; }
  .entete-nom { color: ${branding.couleur_primaire}; font-size: 16pt; font-weight: bold; }
  .entete-slogan { font-size: 9pt; color: #666; }
  .entete-contact { text-align: right; font-size: 9pt; color: #555; }
  .corps { white-space: pre-wrap; line-height: 1.8; margin: 20px 0; }
  .pied { border-top: 1px solid ${branding.couleur_primaire}40; margin-top: 30px; padding-top: 10px; text-align: center; font-size: 9pt; color: #888; }
  @media print { body { margin: 1.5cm; } }
</style>
</head>
<body>
<div class="entete">
  <div class="entete-gauche">
    ${branding.logo_url ? `<img src="${branding.logo_url}" style="height:48px;width:auto;">` : `<div class="entete-logo">${branding.nom.charAt(0)}</div>`}
    <div>
      <div class="entete-nom">${branding.nom}</div>
      ${branding.slogan ? `<div class="entete-slogan">${branding.slogan}</div>` : ''}
    </div>
  </div>
  <div class="entete-contact">
    ${branding.telephone_support ? `<div>Tél : ${branding.telephone_support}</div>` : ''}
    ${branding.email_support ? `<div>${branding.email_support}</div>` : ''}
    ${branding.site_web ? `<div>${branding.site_web}</div>` : ''}
  </div>
</div>
<div class="corps">${lettre}</div>
<div class="pied">
  ${branding.nom} — Société d'Assurance agréée — Zone CIMA<br>
  ${branding.telephone_support ? `Tél : ${branding.telephone_support}` : ''}${branding.email_support ? ` | ${branding.email_support}` : ''}
</div>
</body>
</html>`
    const win = window.open('', '_blank', 'width=800,height=900')
    if (win) {
      win.document.write(htmlContent)
      win.document.close()
      win.focus()
      setTimeout(() => win.print(), 500)
    }
  }

  const exporterWord = () => {
    const htmlContent = `
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="UTF-8"><title>${template?.label || 'Correspondance'}</title>
<style>body{font-family:Calibri,sans-serif;font-size:12pt;margin:2cm} .entete{border-bottom:2px solid ${branding.couleur_primaire};padding-bottom:10px;margin-bottom:16px;} .nom{color:${branding.couleur_primaire};font-size:16pt;font-weight:bold;} .corps{white-space:pre-wrap;line-height:1.8;} .pied{border-top:1px solid #ccc;margin-top:24px;padding-top:8px;font-size:9pt;color:#888;text-align:center;}</style>
</head><body>
<div class="entete"><span class="nom">${branding.nom}</span>${branding.slogan ? `<br><span style="font-size:9pt;color:#666">${branding.slogan}</span>` : ''}</div>
<div class="corps">${lettre.replace(/\n/g, '<br>')}</div>
<div class="pied">${branding.nom} — Société d'Assurance agréée — Zone CIMA${branding.telephone_support ? ` | Tél : ${branding.telephone_support}` : ''}</div>
</body></html>`
    const blob = new Blob([htmlContent], { type: 'application/msword' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${template?.label || 'lettre'}_${reference || 'ref'}_${new Date().toISOString().slice(0, 10)}.doc`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5">
      {titre && (
        <div>
          <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
            <PencilSquareIcon className="h-5 w-5 text-primary-600" />
            {titre}
          </h3>
        </div>
      )}

      {/* Sélecteur de vue */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        <button onClick={() => setVue('composer')}
          className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
            vue === 'composer' ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
          <PencilSquareIcon className="h-4 w-4" /> Composer
        </button>
        <button onClick={() => setVue('historique')}
          className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all relative',
            vue === 'historique' ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
          <DocumentTextIcon className="h-4 w-4" />
          Historique
          {historique.filter(l => l.statut === 'en_validation').length > 0 && (
            <span className="absolute -top-1 -right-1 bg-amber-500 text-white text-xs w-4 h-4 rounded-full flex items-center justify-center">
              {historique.filter(l => l.statut === 'en_validation').length}
            </span>
          )}
        </button>
      </div>

      {/* ── VUE COMPOSER ── */}
      {vue === 'composer' && (
        <div className="space-y-5">
          {/* Choix template */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
            {templates.map(t => (
              <button key={t.id} onClick={() => setTemplateChoisi(t.id)}
                className={clsx('p-3 rounded-xl border-2 text-left transition-all',
                  templateChoisi === t.id ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:border-primary-300 bg-white')}>
                <span className="text-xl">{t.icon}</span>
                <p className="text-xs font-semibold text-gray-800 mt-1 leading-tight">{t.label}</p>
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{t.description}</p>
              </button>
            ))}
          </div>

          {templateChoisi && (
            <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                {template?.icon} {template?.label}
              </h3>

              <div className="grid grid-cols-2 gap-3">
                {references.length > 0 ? (
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Référence dossier</label>
                    <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                      value={reference} onChange={e => setReference(e.target.value)}>
                      <option value="">— Sélectionner —</option>
                      {references.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                  </div>
                ) : (
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Référence dossier</label>
                    <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                      placeholder="N° dossier, police…" value={reference} onChange={e => setReference(e.target.value)} />
                  </div>
                )}
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Destinataire</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                    placeholder="Nom de la personne ou société…" value={destinataire} onChange={e => setDestinataire(e.target.value)} />
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Contexte / détails supplémentaires</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                  placeholder="Montant, motif, date, détails spécifiques…" value={contexte} onChange={e => setContexte(e.target.value)} />
              </div>

              <button onClick={genererLettre} disabled={loading}
                className="flex items-center gap-2 bg-primary-600 text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-primary-700 disabled:opacity-60 transition-colors">
                <SparklesIcon className="h-4 w-4" />
                {loading ? <><ArrowPathIcon className="h-4 w-4 animate-spin" /> Rédaction…</> : 'Générer avec Yukpo IA'}
              </button>

              {lettre && (
                <div className="space-y-3">
                  {/* Toggle aperçu */}
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-gray-600">Lettre générée — modifiable</p>
                    <button onClick={() => setPreviewMode(!previewMode)}
                      className="text-xs text-primary-600 hover:text-primary-700 font-medium">
                      {previewMode ? '✏️ Modifier' : '👁 Aperçu avec en-tête'}
                    </button>
                  </div>

                  {previewMode ? (
                    <div ref={previewRef} className="border border-gray-300 rounded-xl p-6 bg-white text-sm print:border-0">
                      <EnteteCompagnie branding={branding} />
                      <pre className="whitespace-pre-wrap font-sans leading-relaxed text-gray-800">{lettre}</pre>
                      <PiedPageCompagnie branding={branding} />
                    </div>
                  ) : (
                    <textarea
                      className="w-full border border-gray-300 rounded-xl p-4 text-sm font-mono h-72 resize-none focus:ring-2 focus:ring-primary-500"
                      value={lettre}
                      onChange={e => setLettre(e.target.value)}
                    />
                  )}

                  <div className="flex gap-2 flex-wrap">
                    <button onClick={enregistrerBrouillon}
                      className="flex items-center gap-1.5 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700">
                      <DocumentTextIcon className="h-4 w-4" /> Enregistrer & Soumettre
                    </button>
                    <button onClick={exporterPDF}
                      className="flex items-center gap-1.5 border border-gray-300 text-gray-700 px-4 py-2 rounded-lg text-sm hover:bg-gray-50">
                      <PrinterIcon className="h-4 w-4" /> Imprimer / PDF
                    </button>
                    <button onClick={exporterWord}
                      className="flex items-center gap-1.5 border border-blue-300 text-blue-700 px-4 py-2 rounded-lg text-sm hover:bg-blue-50">
                      <DocumentArrowDownIcon className="h-4 w-4" /> Télécharger Word
                    </button>
                    <button onClick={() => navigator.clipboard?.writeText(lettre)}
                      className="flex items-center gap-1.5 border border-gray-300 text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-50">
                      <ArrowDownTrayIcon className="h-4 w-4" /> Copier
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── VUE HISTORIQUE ── */}
      {vue === 'historique' && (
        <div className="space-y-3">
          {historique.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <DocumentTextIcon className="h-10 w-10 mx-auto mb-2" />
              <p className="text-sm">Aucune correspondance enregistrée</p>
              <button onClick={() => setVue('composer')} className="mt-2 text-sm text-primary-600 hover:underline">
                Composer une première lettre
              </button>
            </div>
          )}

          {historique.map(l => {
            const scfg = STATUT_CFG[l.statut]
            return (
              <div key={l.id} className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-gray-900">{l.templateLabel}</p>
                      <span className={clsx('flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium', scfg.classes)}>
                        {scfg.icon}{scfg.label}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">Réf : {l.reference} · Destinataire : {l.destinataire}</p>
                    <p className="text-xs text-gray-400">{new Date(l.dateCreation).toLocaleString('fr-FR')}</p>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <button onClick={() => setModalLettre(l)}
                      className="text-xs text-primary-600 hover:text-primary-700 font-medium px-2 py-1 rounded-lg hover:bg-primary-50">
                      Circuit
                    </button>
                    {l.statut === 'approuve' && (
                      <button
                        onClick={() => {
                          setLettre(l.contenu)
                          setTemplateChoisi(l.templateId)
                          exporterPDF()
                        }}
                        className="text-xs border border-gray-300 text-gray-600 px-2 py-1 rounded-lg hover:bg-gray-50">
                        PDF
                      </button>
                    )}
                  </div>
                </div>

                {/* Mini circuit */}
                <div className="flex items-center gap-1.5 mt-3">
                  {l.circuit.map((e, i) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <div className={clsx('w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold',
                        e.statut === 'approuve' ? 'bg-green-100 text-green-700' :
                        e.statut === 'rejete' ? 'bg-red-100 text-red-700' :
                        e.statut === 'actif' ? 'bg-amber-100 text-amber-700' :
                        'bg-gray-100 text-gray-400')}>
                        {e.statut === 'approuve' ? '✓' : e.statut === 'rejete' ? '✗' : i + 1}
                      </div>
                      {i < l.circuit.length - 1 && <ChevronRightIcon className="h-3 w-3 text-gray-300" />}
                    </div>
                  ))}
                  <span className="text-xs text-gray-500 ml-1">
                    {l.circuit.map(e => e.role).join(' → ')}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {modalLettre && (
        <ModalValidation
          lettre={modalLettre}
          onClose={() => setModalLettre(null)}
          onSoumettre={soumettre}
          onApprouver={approuver}
          onRejeter={rejeter}
        />
      )}
    </div>
  )
}
