import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Shield, Clock, Loader2, Download, Filter } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface AuditEntry {
  id: string
  user_id: string
  role_used: string
  phase: string
  status: string
  duration_seconds: number | null
  context: Record<string, unknown>
  timestamp: string
}

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  pipeline_start: { label: 'Pipeline Iniciado', color: 'text-violet-400' },
  code_generation: { label: 'Geração de Código', color: 'text-blue-400' },
  test_generation: { label: 'Geração de Testes', color: 'text-cyan-400' },
  test_execution: { label: 'Execução de Testes', color: 'text-emerald-400' },
  security_review: { label: 'Análise de Segurança', color: 'text-orange-400' },
  compliance_check: { label: 'Validação de Compliance', color: 'text-amber-400' },
  qa_approval: { label: 'Aprovação QA', color: 'text-emerald-300' },
  commit: { label: 'Commit', color: 'text-green-400' },
}

const STATUS_BADGES: Record<string, { bg: string; text: string }> = {
  COMPLETED: { bg: 'bg-emerald-900/30', text: 'text-emerald-400' },
  COMPLETED_WITH_WARNINGS: { bg: 'bg-amber-900/30', text: 'text-amber-400' },
  FAILED: { bg: 'bg-red-900/30', text: 'text-red-400' },
  APPROVED: { bg: 'bg-emerald-900/30', text: 'text-emerald-300' },
  REJECTED: { bg: 'bg-red-900/30', text: 'text-red-400' },
}

export function PipelineAuditPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [phaseFilter, setPhaseFilter] = useState('all')

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    const params = phaseFilter !== 'all' ? `?phase=${phaseFilter}` : ''
    apiClient.get(`/projects/${projectId}/audit/pipeline${params}`)
      .then(res => setEntries(res.data.entries || []))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false))
  }, [projectId, phaseFilter])

  const handleExportAll = () => {
    const blob = new Blob([JSON.stringify(entries, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit-pipeline-${projectId}.json`
    a.click()
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            <Shield className="w-5 h-5 text-violet-400" />
            Audit Log do Pipeline
          </h2>
          <p className="text-slate-500 text-sm mt-0.5">
            Trilha de auditoria completa de todas as fases do pipeline de qualidade.
            {entries.length > 0 && ` ${entries.length} registros.`}
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={phaseFilter}
            onChange={e => setPhaseFilter(e.target.value)}
            className="bg-dark-200 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
          >
            <option value="all">Todas as fases</option>
            {Object.entries(PHASE_LABELS).map(([key, cfg]) => (
              <option key={key} value={key}>{cfg.label}</option>
            ))}
          </select>
          <button
            onClick={handleExportAll}
            disabled={entries.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 bg-violet-600/20 border border-violet-600/30 text-violet-400 text-sm rounded-lg hover:bg-violet-600/30 disabled:opacity-40"
          >
            <Download className="w-4 h-4" />
            Exportar JSON
          </button>
        </div>
      </div>

      {entries.length > 0 ? (
        <div className="space-y-2">
          {entries.map(entry => {
            const phaseInfo = PHASE_LABELS[entry.phase] || { label: entry.phase, color: 'text-slate-400' }
            const statusInfo = STATUS_BADGES[entry.status] || { bg: 'bg-slate-800', text: 'text-slate-400' }

            return (
              <div key={entry.id} className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3">
                    <span className={`text-sm font-medium ${phaseInfo.color}`}>{phaseInfo.label}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${statusInfo.bg} ${statusInfo.text}`}>{entry.status}</span>
                    <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded">{entry.role_used}</span>
                  </div>
                  {entry.context && (
                    <p className="text-xs text-slate-500 mt-1 truncate">
                      {JSON.stringify(entry.context).slice(0, 120)}
                    </p>
                  )}
                </div>
                <div className="text-right shrink-0">
                  <div className="flex items-center gap-1 text-xs text-slate-500">
                    <Clock className="w-3 h-3" />
                    {entry.timestamp ? new Date(entry.timestamp).toLocaleString('pt-BR') : '-'}
                  </div>
                  {entry.duration_seconds && (
                    <span className="text-xs text-slate-600">{entry.duration_seconds}s</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
          <Shield className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-500">Nenhum registro de auditoria encontrado.</p>
        </div>
      )}
    </div>
  )
}
