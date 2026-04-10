import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Shield, AlertTriangle, CheckCircle, Loader2, Zap, X } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface Issue {
  id: string
  category: string
  title: string
  description: string
  priority: string
  status: string
  fix_severity: string | null
  fix_remediation: string | null
  created_at: string | null
}

interface Progress {
  total: number
  resolved: number
  pending: number
  all_resolved: boolean
  progress_pct: number
}

interface Props {
  projectId: string
  itemId: string
  issuesTotal: number
  issuesResolved: number
}

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: 'bg-red-900/40 text-red-400 border-red-700/30',
  HIGH: 'bg-orange-900/40 text-orange-400 border-orange-700/30',
  MEDIUM: 'bg-amber-900/40 text-amber-400 border-amber-700/30',
  LOW: 'bg-slate-800 text-slate-400 border-slate-700/30',
}

export function BacklogIssuePanel({ projectId, itemId, issuesTotal, issuesResolved }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [issues, setIssues] = useState<Issue[]>([])
  const [progress, setProgress] = useState<Progress | null>(null)
  const [loading, setLoading] = useState(false)
  const [fixingId, setFixingId] = useState<string | null>(null)
  const [fixCode, setFixCode] = useState<{ id: string; code: string } | null>(null)

  const loadIssues = async () => {
    setLoading(true)
    try {
      const res = await apiClient.get(`/projects/${projectId}/backlog/${itemId}/issues`)
      setIssues(res.data.tickets || [])
      setProgress(res.data.progress || null)
    } catch { /* silently */ }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (expanded && issues.length === 0) loadIssues()
  }, [expanded])

  const handleResolve = async (fixId: string) => {
    await apiClient.post(`/projects/${projectId}/backlog/${itemId}/issues/${fixId}/resolve`)
    await loadIssues()
  }

  const handleFixWithAI = async (fixId: string) => {
    setFixingId(fixId)
    try {
      const res = await apiClient.post(`/projects/${projectId}/backlog/${itemId}/issues/${fixId}/fix-with-ai`)
      setFixCode({ id: fixId, code: res.data.fix_code })
    } catch { /* silently */ }
    finally { setFixingId(null) }
  }

  if (issuesTotal === 0) return null

  const pct = issuesTotal > 0 ? Math.round((issuesResolved / issuesTotal) * 100) : 0
  const allDone = issuesTotal > 0 && issuesResolved === issuesTotal

  return (
    <div className="mt-3">
      {/* Summary bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 rounded-lg bg-slate-800/50 border border-slate-700/50 px-3 py-2 hover:bg-slate-800 transition-colors"
      >
        {expanded ? <ChevronDown className="w-3.5 h-3.5 text-slate-500" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-500" />}

        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Shield className={`w-3.5 h-3.5 ${allDone ? 'text-emerald-400' : 'text-amber-400'}`} />
          <span className="text-xs text-slate-300">
            {issuesTotal} issue{issuesTotal !== 1 ? 's' : ''} encontrada{issuesTotal !== 1 ? 's' : ''}
          </span>
          <span className="text-xs text-slate-500">
            ({issuesResolved}/{issuesTotal} resolvidas)
          </span>
        </div>

        {/* Progress bar */}
        <div className="w-24 h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${allDone ? 'bg-emerald-500' : 'bg-amber-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={`text-xs font-medium ${allDone ? 'text-emerald-400' : 'text-amber-400'}`}>
          {pct}%
        </span>
      </button>

      {/* Expanded issues list */}
      {expanded && (
        <div className="mt-2 space-y-2 pl-6">
          {loading ? (
            <div className="flex items-center gap-2 py-3 text-slate-500 text-xs">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Carregando issues...
            </div>
          ) : (
            issues.map(issue => {
              const sevColor = SEVERITY_COLORS[issue.fix_severity || 'MEDIUM'] || SEVERITY_COLORS.MEDIUM
              const isDone = issue.status === 'done'

              return (
                <div key={issue.id} className={`rounded-lg border border-slate-700/50 bg-slate-900/50 p-3 ${isDone ? 'opacity-60' : ''}`}>
                  <div className="flex items-start gap-3">
                    {isDone ? (
                      <CheckCircle className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                    )}

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-medium text-white">{issue.title}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${sevColor}`}>
                          {issue.fix_severity}
                        </span>
                      </div>

                      {issue.description && (
                        <p className="text-xs text-slate-500 mt-1">{issue.description}</p>
                      )}

                      {issue.fix_remediation && (
                        <div className="mt-2 rounded bg-emerald-950/30 border border-emerald-800/20 px-2.5 py-1.5">
                          <p className="text-[10px] text-emerald-500 font-medium mb-0.5">Remediacao sugerida:</p>
                          <p className="text-xs text-emerald-300/80">{issue.fix_remediation}</p>
                        </div>
                      )}

                      {/* Fix code preview */}
                      {fixCode?.id === issue.id && (
                        <div className="mt-2 rounded bg-slate-950 border border-violet-700/30 p-2">
                          <div className="flex items-center justify-between mb-1">
                            <p className="text-[10px] text-violet-400 font-medium">Correcao gerada por IA:</p>
                            <button onClick={() => setFixCode(null)} className="text-slate-500 hover:text-white">
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                          <pre className="text-xs text-slate-300 overflow-x-auto max-h-48 whitespace-pre-wrap">{fixCode.code.slice(0, 1000)}</pre>
                        </div>
                      )}

                      {/* Action buttons */}
                      {!isDone && (
                        <div className="flex gap-2 mt-2">
                          <button
                            onClick={() => handleFixWithAI(issue.id)}
                            disabled={fixingId === issue.id}
                            className="flex items-center gap-1 px-2 py-1 text-[10px] bg-violet-600/20 border border-violet-600/30 text-violet-400 rounded hover:bg-violet-600/30 transition-colors disabled:opacity-40"
                          >
                            {fixingId === issue.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                            Corrigir com IA
                          </button>
                          <button
                            onClick={() => handleResolve(issue.id)}
                            className="flex items-center gap-1 px-2 py-1 text-[10px] bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 rounded hover:bg-emerald-600/30 transition-colors"
                          >
                            <CheckCircle className="w-3 h-3" />
                            Marcar resolvido
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
