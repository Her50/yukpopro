import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { View, StyleSheet, ScrollView } from 'react-native'
import { Modal, Portal, Button, Text, Card, List, Divider } from 'react-native-paper'
import {
  configureCreditHandlers,
  creditsAPI,
  parseCreditError,
  CreditError,
  SoldeCredits,
} from '../api/client'

interface CreditsContextType {
  solde: SoldeCredits | null
  rafraichir: () => Promise<void>
  ouvrirRecharge: (motif?: CreditError) => void
}

const CreditsContext = createContext<CreditsContextType | null>(null)

interface Pack {
  id: string
  nom: string
  credits: number
  prix_fcfa: number
  description?: string
  badge?: string
}

interface Plan {
  id: string
  nom: string
  prix_fcfa: number
  credits_mois?: number
  description?: string
  badge?: string
}

export function CreditsProvider({ children }: { children: ReactNode }) {
  const [solde, setSolde] = useState<SoldeCredits | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [motif, setMotif] = useState<CreditError | null>(null)
  const [packs, setPacks] = useState<Pack[]>([])
  const [plans, setPlans] = useState<Plan[]>([])
  const [loadingAction, setLoadingAction] = useState(false)

  const rafraichir = async () => {
    try {
      const s = await creditsAPI.getSolde()
      setSolde(s)
    } catch { /* non bloquant — pas connecté ou API indisponible */ }
  }

  const chargerOptions = async () => {
    try {
      const [p, pl] = await Promise.all([
        creditsAPI.listerPacks().catch(() => ({ packs: [] })),
        creditsAPI.listerPlans().catch(() => ({ plans: [] })),
      ])
      setPacks(p.packs ?? [])
      setPlans(pl.plans ?? [])
    } catch { /* ignore */ }
  }

  const ouvrirRecharge = (m?: CreditError) => {
    setMotif(m ?? null)
    setModalOpen(true)
    chargerOptions()
    rafraichir()
  }

  useEffect(() => {
    configureCreditHandlers({
      onCreditsEpuises: (e) => ouvrirRecharge(e),
      onModuleNonAutorise: (e) => ouvrirRecharge(e),
    })
    rafraichir()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const acheterPack = async (packId: string) => {
    setLoadingAction(true)
    try {
      const res = await creditsAPI.initierRecharge(packId)
      if (res?.url_paiement) {
        // TODO: ouvrir le WebView paiement mobile money
      }
      await rafraichir()
      setModalOpen(false)
    } finally {
      setLoadingAction(false)
    }
  }

  const choisirPlan = async (planId: string) => {
    // Ouvrir le flux paiement plein écran dans une page dédiée
    // Pour rester simple ici : on stocke l'ID et on invite l'utilisateur
    // à compléter via l'écran de souscription.
    setLoadingAction(true)
    try {
      const res = await creditsAPI.initierUpgrade(planId, 'OM', '')
      if (res?.url_paiement) {
        // TODO: navigation webview
      }
      setModalOpen(false)
    } catch { /* laisser la modale ouverte */ } finally {
      setLoadingAction(false)
    }
  }

  return (
    <CreditsContext.Provider value={{ solde, rafraichir, ouvrirRecharge }}>
      {children}
      <Portal>
        <Modal
          visible={modalOpen}
          onDismiss={() => setModalOpen(false)}
          contentContainerStyle={styles.modal}
        >
          <ScrollView>
            <Text variant="titleLarge" style={styles.title}>
              {motif?.kind === 'module_non_autorise'
                ? 'Module non inclus dans votre plan'
                : 'Crédits Yukpo épuisés'}
            </Text>
            {motif?.message && (
              <Text variant="bodyMedium" style={styles.subtitle}>
                {motif.message}
              </Text>
            )}
            {solde && (
              <Card style={styles.card} mode="contained">
                <Card.Content>
                  <Text variant="titleSmall">Plan actuel : {solde.label_plan}</Text>
                  <Text variant="bodySmall">
                    {solde.credits_restants.toFixed(0)} / {solde.credits_alloues} crédits restants
                  </Text>
                  {solde.renouvellement_le && (
                    <Text variant="bodySmall">Renouvellement le {solde.renouvellement_le}</Text>
                  )}
                </Card.Content>
              </Card>
            )}

            {packs.length > 0 && (
              <>
                <Text variant="titleMedium" style={styles.sectionTitle}>
                  Recharger maintenant
                </Text>
                {packs.map((p) => (
                  <List.Item
                    key={p.id}
                    title={`${p.nom} — ${p.credits.toLocaleString()} crédits`}
                    description={`${p.prix_fcfa.toLocaleString()} FCFA${p.badge ? ` · ${p.badge}` : ''}`}
                    onPress={() => acheterPack(p.id)}
                    disabled={loadingAction}
                    left={(props) => <List.Icon {...props} icon="wallet-plus" />}
                  />
                ))}
              </>
            )}

            {motif?.kind === 'module_non_autorise' && plans.length > 0 && (
              <>
                <Divider style={styles.divider} />
                <Text variant="titleMedium" style={styles.sectionTitle}>
                  Changer de plan
                </Text>
                {plans
                  .filter((pl) => motif?.plansEligibles?.length ? motif.plansEligibles.includes(pl.id) : true)
                  .map((pl) => (
                    <List.Item
                      key={pl.id}
                      title={`${pl.nom} — ${pl.prix_fcfa.toLocaleString()} FCFA`}
                      description={pl.description ?? (pl.credits_mois ? `${pl.credits_mois.toLocaleString()} crédits/mois` : '')}
                      onPress={() => choisirPlan(pl.id)}
                      disabled={loadingAction}
                      left={(props) => <List.Icon {...props} icon="arrow-up-bold-circle" />}
                    />
                  ))}
              </>
            )}

            <Button
              mode="text"
              onPress={() => setModalOpen(false)}
              style={styles.closeBtn}
            >
              Fermer
            </Button>
          </ScrollView>
        </Modal>
      </Portal>
    </CreditsContext.Provider>
  )
}

export function useCredits() {
  const ctx = useContext(CreditsContext)
  if (!ctx) throw new Error('useCredits must be used within CreditsProvider')
  return ctx
}

const styles = StyleSheet.create({
  modal: {
    backgroundColor: '#ffffff',
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 20,
    maxHeight: '85%',
  },
  title: { marginBottom: 6, color: '#1d4ed8' },
  subtitle: { marginBottom: 12, color: '#475569' },
  card: { marginBottom: 12, backgroundColor: '#eff6ff' },
  sectionTitle: { marginTop: 8, marginBottom: 4, color: '#0f172a' },
  divider: { marginVertical: 12 },
  closeBtn: { marginTop: 16 },
})
