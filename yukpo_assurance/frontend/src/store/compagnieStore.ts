/**
 * YukpoAssurance — Store branding compagnie
 * Permet à chaque compagnie d'assurance de personnaliser l'interface :
 * logo, nom, couleur primaire, pays, slogan.
 * Persisté dans localStorage pour ne pas recharger à chaque session.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface BrandingCompagnie {
  nom: string
  slogan: string
  logo_url: string | null          // URL absolue ou data:image/... base64
  logo_base64: string | null       // Base64 brut pour upload
  couleur_primaire: string         // Hex — ex: '#1d4ed8'
  couleur_secondaire: string       // Hex — ex: '#0ea5e9'
  pays: 'CM' | 'CI' | 'SN' | 'GA' | 'CG' | 'CF' | 'TD' | 'NE' | 'ML' | 'BF' | 'TG' | 'BJ' | 'GW' | 'GQ' | 'KM'
  devise: 'XAF' | 'XOF'
  telephone_support: string
  email_support: string
  site_web: string
}

interface CompagnieState {
  branding: BrandingCompagnie
  setBranding: (partial: Partial<BrandingCompagnie>) => void
  setLogo: (url: string, base64?: string) => void
  resetBranding: () => void
}

const BRANDING_PAR_DEFAUT: BrandingCompagnie = {
  nom: 'YukpoAssurance',
  slogan: 'Votre partenaire assurance en zone CIMA',
  logo_url: null,
  logo_base64: null,
  couleur_primaire: '#1d4ed8',
  couleur_secondaire: '#0ea5e9',
  pays: 'CM',
  devise: 'XAF',
  telephone_support: '',
  email_support: '',
  site_web: '',
}

export const useCompagnieStore = create<CompagnieState>()(
  persist(
    (set) => ({
      branding: BRANDING_PAR_DEFAUT,

      setBranding: (partial) =>
        set((state) => ({
          branding: { ...state.branding, ...partial },
        })),

      setLogo: (url, base64) =>
        set((state) => ({
          branding: { ...state.branding, logo_url: url, logo_base64: base64 || null },
        })),

      resetBranding: () => set({ branding: BRANDING_PAR_DEFAUT }),
    }),
    {
      name: 'yukpo-compagnie-branding',
    }
  )
)
