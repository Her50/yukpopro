import { BrowserRouter, useRoutes } from 'react-router-dom'
import { routes } from './router'
import { ErrorBoundary } from './components/ErrorBoundary'

function AppRoutes() {
  return useRoutes(routes)
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ErrorBoundary>
  )
}
