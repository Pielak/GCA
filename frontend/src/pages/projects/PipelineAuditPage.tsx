import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Shield, Clock, Loader2, Download, AlertTriangle, CheckCircle2, XCircle, FileCode } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { formatDateTimeBR } from '@/lib/datetime'

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

interface CodeAuditFinding {
  id: string
  run_id: string
  file_path: string
  severity: 'info' | 'warn' | 'critical'
  category: 'rnf' | 'stack' | 'security' | 'ptbr' | 'scope' | 'doc'
  finding: string
  suggested_fix: string | null
  owner_action: 'dismissed' | 'accepted' | 'fix_created' | null
  owner_note: string | null
  owner_acted_at: string | null
  backlog_fix_item_id: string | null
  created_at: string
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

const SEVERITY_STYLE: Record<string, { bg: string; text: string; icon: typeof AlertTriangle }> = {
  info: { bg: 'bg-slate-800/60', text: 'text-slate-300', icon: FileCode },
  warn: { bg: 'bg-amber-900/30', text: 'text-amber-300', icon: AlertTriangle },
  critical: { bg: 'bg-red-900/30', text: 'text-red-300', icon: XCircle },
}

const CATEGORY_LABEL: Record<string, string> = {
  rnf: 'RNF',
  stack: 'Stack',
  security: 'Segurança',
  ptbr: 'PT-BR',
  scope: 'Escopo',
  doc: 'Docstring',
}

type TabKey = 'trilha' | 'findings'

export function PipelineAuditPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [activeTab, setActiveTab] = useState<TabKey>('trilha')

  // Trilha
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loadingEntries, setLoadingEntries] = useState(true)
  const [phaseFilter, setPhaseFilter] = useState('all')

  // Findings
  const [findings, setFindings] = useState<CodeAuditFinding[]>([])
  const [loadingFindings, setLoadingFindings] = useState(false)
  const [severityFilter, setSeverityFilter] = useState<string>('all')
  const [pendingOnly, setPendingOnly] = useState(false)
  const [actingId, setActingId] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId || activeTab !== 'trilha') return
    setLoadingEntries(true)
    const params = phaseFilter !== 'all' ? `?phase=${phaseFilter}` : ''
    apiClient.get(`/projects/${projectId}/audit/pipeline${params}`)
      .then(res => setEntries(res.data.entries || []))
      .catch(() => setEntries([]))
      .finally(() => setLoadingEntries(false))
  }, [projectId, phaseFilter, activeTab])

  const loadFindings = useCallback(async () => {
    if (!projectId) return
    setLoadingFindings(true)
    const qs = new URLSearchParams()
    if (severityFilter !== 'all') qs.set('severity', severityFilter)
    if (pendingOnly) qs.set('pending_only', 'true')
    try {
      const res = await apiClient.get(`/projects/${projectId}/audit/findings?${qs.toString()}`)
      setFindings(res.data.items || [])
    } catch {
      setFindings([])
    } finally {
      setLoadingFindings(false)
    }
  }, [projectId, severityFilter, pendingOnly])

  useEffect(() => {
    if (activeTab === 'findings') loadFindings()
  }, [activeTab, loadFindings])

  const handleExportAll = () => {
    const data = activeTab === 'trilha' ? entries : findings
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit-${activeTab}-${projectId}.json`
    a.click()
  }

  const handleDismiss = async (id: string) => {
    const note = window.prompt('Nota (opcional) sobre por que está descartando:', '') || ''
    setActingId(id)
    try {
      await apiClient.post(`/audit/findings/${id}/dismiss`, { note })
      await loadFindings()
    } finally {
      setActingId(null)
    }
  }

  const handleAccept = async (id: string, createFix: boolean) => {
    const note = createFix
      ? (window.prompt('Nota sobre o fix (opcional):', '') || '')
      : (window.prompt('Nota (opcional):', '') || '')
    setActingId(id)
    try {
      await apiClient.post(`/audit/findings/${id}/accept`, {
        create_fix: createFix,
        note,
      })
      await loadFindings()
    } finally {
      setActingId(null)
    }
  }

  const renderTrilha = () => (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div className="flex gap-2">
          <select
            value={phaseFilter}
            onChange={e => setPhaseFilter(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
          >
            <option value="all">Todas as fases</option>
            {Object.entries(PHASE_LABELS).map(([key, cfg]) => (
              <option key={key} value={key}>{cfg.label}</option>
            ))}
          </select>
        </div>
        <button
          onClick={handleExportAll}
          disabled={entries.length === 0}
          className="flex items-center gap-1.5 px-3 py-2 bg-violet-600/20 border border-violet-600/30 text-violet-400 text-sm rounded-lg hover:bg-violet-600/30 disabled:opacity-40"
        >
          <Download className="w-4 h-4" />
          Exportar JSON
        </button>
      </div>

      {loadingEntries ? (
        <div className="flex items-center justify-center h-32"><Loader2 className="w-5 h-5 text-violet-400 animate-spin" /></div>
      ) : entries.length > 0 ? (
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
                    <p className="text-xs text-slate-500 mt-1 truncate">{JSON.stringify(entry.context).slice(0, 120)}</p>
                  )}
                </div>
                <div className="text-right shrink-0">
                  <div className="flex items-center gap-1 text-xs text-slate-500">
                    <Clock className="w-3 h-3" />
                    {entry.timestamp ? formatDateTimeBR(entry.timestamp) : '-'}
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
          <p className="text-slate-600 text-xs mt-1">Os registros aparecem após o pipeline de qualidade rodar.</p>
        </div>
      )}
    </div>
  )

  const renderFindings = () => (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div className="flex gap-2 items-center">
          <select
            value={severityFilter}
            onChange={e => setSeverityFilter(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
          >
            <option value="all">Todas as severidades</option>
            <option value="critical">Critical</option>
            <option value="warn">Warn</option>
            <option value="info">Info</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={pendingOnly}
              onChange={e => setPendingOnly(e.target.checked)}
              className="accent-violet-500"
            />
            só pendentes
          </label>
        </div>
        <button
          onClick={handleExportAll}
          disabled={findings.length === 0}
          className="flex items-center gap-1.5 px-3 py-2 bg-violet-600/20 border border-violet-600/30 text-violet-400 text-sm rounded-lg hover:bg-violet-600/30 disabled:opacity-40"
        >
          <Download className="w-4 h-4" />
          Exportar JSON
        </button>
      </div>

      {loadingFindings ? (
        <div className="flex items-center justify-center h-32"><Loader2 className="w-5 h-5 text-violet-400 animate-spin" /></div>
      ) : findings.length > 0 ? (
        <div className="space-y-3">
          {findings.map(f => {
            const sev = SEVERITY_STYLE[f.severity] || SEVERITY_STYLE.info
            const SevIcon = sev.icon
            const decided = f.owner_action !== null
            return (
              <div key={f.id} className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-xs px-2 py-0.5 rounded inline-flex items-center gap-1 ${sev.bg} ${sev.text}`}>
                        <SevIcon className="w-3 h-3" /> {f.severity.toUpperCase()}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-violet-900/30 text-violet-300">
                        {CATEGORY_LABEL[f.category] || f.category}
                      </span>
                      <code className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">{f.file_path}</code>
                      {decided && (
                        <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/30 text-emerald-300 inline-flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> {f.owner_action}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-200">{f.finding}</p>
                    {f.suggested_fix && (
                      <p className="text-xs text-slate-400">
                        <span className="text-slate-500">Sugestão:</span> {f.suggested_fix}
                      </p>
                    )}
                    {f.owner_note && (
                      <p className="text-xs text-slate-500 italic">
                        Nota do owner: {f.owner_note}
                      </p>
                    )}
                  </div>
                  <span className="text-xs text-slate-500 shrink-0">
                    {f.created_at ? formatDateTimeBR(f.created_at) : '-'}
                  </span>
                </div>
                {!decided && (
                  <div className="flex gap-2 pt-2 border-t border-slate-800">
                    <button
                      onClick={() => handleDismiss(f.id)}
                      disabled={actingId === f.id}
                      className="text-xs px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded disabled:opacity-50"
                    >
                      Descartar
                    </button>
                    <button
                      onClick={() => handleAccept(f.id, false)}
                      disabled={actingId === f.id}
                      className="text-xs px-3 py-1.5 bg-emerald-600/20 border border-emerald-600/30 text-emerald-300 hover:bg-emerald-600/30 rounded disabled:opacity-50"
                    >
                      Aceitar
                    </button>
                    <button
                      onClick={() => handleAccept(f.id, true)}
                      disabled={actingId === f.id}
                      className="text-xs px-3 py-1.5 bg-violet-600/20 border border-violet-600/30 text-violet-300 hover:bg-violet-600/30 rounded disabled:opacity-50"
                    >
                      Aceitar + criar Fix no Backlog
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
          <FileCode className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-500">Nenhum finding de auditoria de código.</p>
          <p className="text-slate-600 text-xs mt-1">
            A auditoria roda automaticamente após cada apply do scaffold.
          </p>
        </div>
      )}
    </div>
  )

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
          <Shield className="w-5 h-5 text-violet-400" />
          Auditoria
        </h2>
        <p className="text-slate-500 text-sm mt-0.5">
          Trilha do pipeline de qualidade + findings da auditoria pós-CodeGen.
        </p>
      </div>

      <div className="flex gap-1 border-b border-slate-800">
        <button
          onClick={() => setActiveTab('trilha')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === 'trilha'
              ? 'border-violet-500 text-violet-400'
              : 'border-transparent text-slate-500 hover:text-slate-300'
          }`}
        >
          <Clock className="w-3.5 h-3.5" /> Trilha do Pipeline
        </button>
        <button
          onClick={() => setActiveTab('findings')}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === 'findings'
              ? 'border-violet-500 text-violet-400'
              : 'border-transparent text-slate-500 hover:text-slate-300'
          }`}
        >
          <FileCode className="w-3.5 h-3.5" /> Findings de Código
        </button>
      </div>

      {activeTab === 'trilha' ? renderTrilha() : renderFindings()}
    </div>
  )
}
