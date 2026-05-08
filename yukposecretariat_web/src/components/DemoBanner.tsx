/**
 * Ce composant ne rend plus rien — la bannière "Données de démonstration"
 * a été retirée à la demande utilisateur. On garde l'export pour ne pas
 * casser les nombreux imports dans les pages existantes.
 */
interface DemoBannerProps {
  message?: string
  className?: string
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function DemoBanner(_props: DemoBannerProps) {
  return null
}
