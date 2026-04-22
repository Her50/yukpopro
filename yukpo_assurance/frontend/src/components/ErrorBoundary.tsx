import { Component, ErrorInfo, ReactNode } from 'react'
import { ExclamationTriangleIcon, ArrowPathIcon } from '@heroicons/react/24/outline'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  onReset?: () => void
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

/**
 * ErrorBoundary — Capture les erreurs React non gérées.
 * Évite que toute l'application crashe sur une erreur dans un composant.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, errorInfo: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo })
    // Log en production (remplacer par Sentry ou autre service)
    console.error('[ErrorBoundary] Erreur capturée:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
    this.props.onReset?.()
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 text-center">
          <div className="bg-red-50 border border-red-200 rounded-2xl p-8 max-w-md w-full">
            <ExclamationTriangleIcon className="h-12 w-12 text-red-400 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-red-800 mb-2">
              Une erreur est survenue
            </h2>
            <p className="text-sm text-red-600 mb-4">
              {this.state.error?.message || 'Erreur inattendue dans ce module.'}
            </p>
            {import.meta.env.DEV && this.state.errorInfo && (
              <details className="text-left mb-4">
                <summary className="text-xs text-red-500 cursor-pointer">Détails techniques</summary>
                <pre className="text-xs text-red-400 mt-2 overflow-auto max-h-32 bg-red-100 p-2 rounded">
                  {this.state.errorInfo.componentStack}
                </pre>
              </details>
            )}
            <button
              onClick={this.handleReset}
              className="flex items-center gap-2 mx-auto px-4 py-2 bg-red-600 text-white text-sm rounded-xl hover:bg-red-700 transition-colors"
            >
              <ArrowPathIcon className="h-4 w-4" />
              Réessayer
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

/**
 * withErrorBoundary — HOC pour envelopper un composant dans un ErrorBoundary.
 */
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallback?: ReactNode,
) {
  return function WrappedComponent(props: P) {
    return (
      <ErrorBoundary fallback={fallback}>
        <Component {...props} />
      </ErrorBoundary>
    )
  }
}
