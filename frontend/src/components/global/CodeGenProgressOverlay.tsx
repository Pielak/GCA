import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, AlertTriangle, X, ArrowRight } from 'lucide-react'
import { useCodeGenProgressStore } from '@/stores/codeGenProgressStore'

/**
 * MVP 30 — overlay global de progresso de geração de scaffold.
 *
 * Renderizado no layout raiz do projeto. Aparece quando
 * `codeGenProgressStore.active === true` OU quando há resultado recente
 * ainda não dispensado. Permite ao usuário navegar livre enquanto a
 * geração roda — o for-loop vive no store, não no componente do
 * CodeGenerator.
 */
export function CodeGenProgressOverlay() {
  const navigate = useNavigate()
  const params = useParams<{ id: string }>()
  const currentProjectIdFromRoute = params.id

  const active = useCodeGenProgressStore((s) => s.active)
  const projectId = useCodeGenProgressStore((s) => s.projectId)
  const projectName = useCodeGenProgressStore((s) => s.projectName)
  const itemStatus = useCodeGenProgressStore((s) => s.itemStatus)
  const planSummary = useCodeGenProgressStore((s) => s.planSummary)
  const errorMessage = useCodeGenProgressStore((s) => s.errorMessage)
  const finishedAt = useCodeGenProgressStore((s) => s.finishedAt)
  const startedAt = useCodeGenProgressStore((s) => s.startedAt)
  const dismiss = useCodeGenProgressStore((s) => s.dismiss)

  const stats = useMemo(() => {
    const values = Array.from(itemStatus.values())
    const total = values.length
    const done = values.filter(v => v === 'complete').length
    const generating = values.filter(v => v === 'generating').length
    const errors = values.filter(v => v === 'error').length
    const pending = values.filter(v => v === 'pending').length
    const pct = total > 0 ? Math.round((done / total) * 100) : 0
    return { total, done, generating, errors, pending, pct }
  }, [itemStatus])

  const shouldShow = active || (finishedAt && !active)
  if (!shouldShow) return null
  if (!projectId || !projectName) return null

  const onCurrentProject = currentProjectIdFromRoute === projectId
  const elapsed = startedAt
    ? Math.round(((finishedAt || Date.now()) - startedAt) / 1000)
    : 0

  const goToCodeGen = () => {
    if (onCurrentProject) return
    navigate(`/projects/${projectId}/codegen`)
  }

  const isDone = !active && finishedAt !== null

  return (
    <div
      className="fixed bottom-4 right-4 z-50 w-[360px] bg-slate-900 border border-violet-700/50 rounded-xl shadow-2xl shadow-violet-900/30 overflow-hidden"
      role="status"
      aria-live="polite"
    >
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {active && <Loader2 className="w-4 h-4 text-violet-400 animate-spin flex-shrink-0" />}
          {isDone && stats.errors === 0 && <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />}
          {isDone && stats.errors > 0 && <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />}
          <div className="flex flex-col min-w-0">
            <span className="text-xs font-semibold text-slate-200 truncate">
              {active ? 'Gerando código' : isDone ? 'Geração concluída' : 'Preparando'}
            </span>
            <span className="text-[10px] text-slate-500 truncate">{projectName}</span>
          </div>
        </div>
        {isDone && (
          <button
            type="button"
            onClick={dismiss}
            className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors flex-shrink-0"
            title="Dispensar"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      <div className="px-4 py-3">
        {stats.total === 0 ? (
          <div className="text-xs text-slate-400">
            {errorMessage || 'Consultando OCG e stack pra listar os arquivos do scaffold...'}
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between text-xs text-slate-300 mb-1.5">
              <span>
                <strong className="text-violet-300">{stats.done}</strong>
                <span className="text-slate-500"> / {stats.total} arquivos</span>
                {stats.errors > 0 && (
                  <span className="text-amber-400 ml-2">{stats.errors} erro(s)</span>
                )}
              </span>
              <span className="text-[10px] text-slate-500">{elapsed}s</span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${isDone && stats.errors === 0 ? 'bg-emerald-500' : isDone && stats.errors > 0 ? 'bg-amber-500' : 'bg-violet-500'}`}
                style={{ width: `${stats.pct}%` }}
              />
            </div>
            {planSummary && (
              <p className="text-[10px] text-slate-500 mt-2 line-clamp-2">{planSummary}</p>
            )}
          </>
        )}

        {errorMessage && (
          <div className="mt-2 text-[11px] text-red-400 bg-red-950/30 border border-red-900/40 rounded px-2 py-1">
            {errorMessage}
          </div>
        )}

        {!onCurrentProject && (
          <button
            type="button"
            onClick={goToCodeGen}
            className="mt-3 w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md bg-violet-600/20 hover:bg-violet-600/30 border border-violet-700/40 text-xs text-violet-300 transition-colors"
          >
            Abrir Geração de Código
            <ArrowRight className="w-3 h-3" />
          </button>
        )}
      </div>
    </div>
  )
}
