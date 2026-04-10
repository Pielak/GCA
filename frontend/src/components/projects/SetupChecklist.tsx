import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, Circle, GitBranch, Cpu, Loader2, Rocket } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface SetupStatus {
  repo_configured: boolean
  llm_configured: boolean
  ready_to_activate: boolean
}

export function SetupChecklist() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [activating, setActivating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    apiClient.get(`/projects/${projectId}/setup-status`)
      .then((res) => setStatus(res.data))
      .catch(() => setStatus(null))
  }, [projectId])

  const handleActivate = async () => {
    if (!projectId) return
    setActivating(true)
    setError(null)
    try {
      await apiClient.post(`/projects/${projectId}/activate-project`)
      window.location.reload()
    } catch (err: any) {
      setError(err?.message || 'Erro ao ativar projeto')
    } finally {
      setActivating(false)
    }
  }

  if (!status) return null

  const items = [
    {
      label: 'Conectar Repositorio Git',
      description: 'Configure o provider, URL e token de acesso do repositorio do projeto.',
      done: status.repo_configured,
      icon: GitBranch,
      path: `/projects/${projectId}/repository`,
    },
    {
      label: 'Configurar Chaves de IA',
      description: 'Selecione o provider de IA e insira a API key para geracao de codigo.',
      done: status.llm_configured,
      icon: Cpu,
      path: `/projects/${projectId}/settings`,
    },
  ]

  return (
    <div className="rounded-xl border border-violet-600/30 bg-violet-950/20 p-6">
      <h2 className="text-lg font-semibold text-white mb-2">Configurar Projeto</h2>
      <p className="text-sm text-slate-400 mb-6">
        Bem-vindo ao seu projeto! Para que o pipeline fique funcional, complete as configuracoes obrigatorias abaixo.
      </p>

      <div className="space-y-4">
        {items.map((item) => {
          const Icon = item.icon
          return (
            <div
              key={item.label}
              className="flex items-center gap-4 rounded-lg border border-slate-700 bg-slate-900/50 p-4"
            >
              {item.done ? (
                <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-400" />
              ) : (
                <Circle className="h-6 w-6 shrink-0 text-slate-500" />
              )}
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${item.done ? 'text-emerald-300' : 'text-white'}`}>
                  {item.label}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">{item.description}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Icon className="h-4 w-4 text-slate-500" />
                {!item.done && (
                  <button
                    onClick={() => navigate(item.path)}
                    className="rounded-lg bg-violet-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-violet-500 transition-colors"
                  >
                    Configurar
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {error && (
        <div className="mt-4 rounded-lg bg-red-900/40 border border-red-800/50 p-3">
          <p className="text-red-300 text-sm">{error}</p>
        </div>
      )}

      {status.ready_to_activate && (
        <button
          onClick={handleActivate}
          disabled={activating}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-6 py-3 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors"
        >
          {activating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Rocket className="h-4 w-4" />
          )}
          Ativar Projeto
        </button>
      )}
    </div>
  )
}
