import React, { ReactNode, ErrorInfo } from 'react'
import { AlertCircle } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error Boundary caught:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
          <div className="max-w-md w-full bg-gray-800 border border-red-700 rounded-lg p-8">
            <div className="flex items-center gap-3 mb-4">
              <AlertCircle className="w-8 h-8 text-red-500" />
              <h1 className="text-xl font-bold text-white">Algo deu errado</h1>
            </div>
            <p className="text-gray-300 mb-4">
              Desculpe, algo inesperado aconteceu. Tente recarregar a página.
            </p>
            <details className="bg-gray-900 p-3 rounded border border-gray-700 mb-4">
              <summary className="text-gray-400 cursor-pointer text-sm">
                Detalhes do erro
              </summary>
              <pre className="text-xs text-red-400 mt-2 overflow-auto max-h-32">
                {this.state.error?.message}
              </pre>
            </details>
            <button
              onClick={() => window.location.reload()}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg transition"
            >
              Recarregar Página
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
