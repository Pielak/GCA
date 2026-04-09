import { useOutletContext, useParams, useNavigate } from 'react-router-dom'
import { AlertTriangle, GitBranch } from 'lucide-react'

interface ProjectContext {
  repoConnected: boolean | null
}

/**
 * Componente bloqueante — exibe alerta se repositório não configurado.
 * Envolve seções que dependem do repositório (Repos Externos, Ingestão, Gatekeeper, etc.)
 */
export function RequireRepository({ children }: { children: React.ReactNode }) {
  const { repoConnected } = useOutletContext<ProjectContext>()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  if (repoConnected === false) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-800/40 rounded-xl p-6 text-center max-w-lg mx-auto">
          <AlertTriangle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h3 className="text-red-300 text-lg font-semibold mb-2">Repositório não configurado</h3>
          <p className="text-slate-400 text-sm mb-4">
            Esta seção requer que o repositório do projeto esteja configurado.
            O repositório é a fonte de verdade para artefatos, documentação e código.
          </p>
          <button
            onClick={() => navigate(`/projects/${id}/repository`)}
            className="flex items-center gap-2 mx-auto px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm rounded-lg transition-colors"
          >
            <GitBranch className="w-4 h-4" />
            Configurar Repositório
          </button>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
