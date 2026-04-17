import { useParams } from 'react-router-dom'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { useSetupStatus } from '@/hooks/useSetupStatus'
import { SetupChecklist } from '@/components/project/SetupChecklist'

/**
 * Guard bloqueante — exibe checklist de setup se algum dos 3 pré-requisitos
 * (repo, IA, questionário) não estiver completo. Substitui RequireRepository
 * nos routes do pipeline.
 */
export function RequireProjectSetup({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>()
  const { data: status, isLoading, error } = useSetupStatus(id)

  if (!id) return null

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-800/40 rounded-xl p-4 text-center max-w-md mx-auto">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-red-300 text-sm">Falha ao verificar o setup do projeto. Recarregue a página.</p>
        </div>
      </div>
    )
  }

  if (!status?.ready_to_activate) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <div className="mb-5 bg-amber-950/20 border border-amber-800/30 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-amber-300 text-sm font-semibold mb-1">Seção bloqueada</h3>
              <p className="text-amber-200/80 text-xs">
                Esta aba faz parte do pipeline e só pode ser usada após o setup básico do projeto
                estar completo. Finalize os passos abaixo.
              </p>
            </div>
          </div>
        </div>
        <SetupChecklist projectId={id} status={status!} />
      </div>
    )
  }

  return <>{children}</>
}
