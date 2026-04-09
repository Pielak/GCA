import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, FlaskConical, X, AlertTriangle } from 'lucide-react'
import { HelpTooltip } from '@/components/ui/HelpTooltip'
import { TestArtifactCard } from '@/components/qa/TestArtifactCard'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

interface TestArtifact {
  id: string
  title: string
  test_type: string
  status: string
  content: string
  description?: string
  created_by: string
  last_edited_by?: string
  last_edited_at?: string
  version: number
  created_at: string
}

interface TestLog {
  id: string
  status: string
  output: string
  executed_by: string
  executed_at: string
  duration_ms?: number
}

const TEST_TABS = [
  { key: 'unit', label: 'Unit' },
  { key: 'integration', label: 'Integration' },
  { key: 'e2e', label: 'E2E' },
  { key: 'regression', label: 'Regression' },
  { key: 'load', label: 'Load' },
  { key: 'security', label: 'Security' },
] as const

type TestTab = typeof TEST_TABS[number]['key']

export function TesterReviewPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuthStore()

  const [activeTab, setActiveTab] = useState<TestTab>('unit')
  const [tests, setTests] = useState<TestArtifact[]>([])
  const [loading, setLoading] = useState(true)

  // Edit modal
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingTest, setEditingTest] = useState<TestArtifact | null>(null)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)

  // Reject modal
  const [rejectModalOpen, setRejectModalOpen] = useState(false)
  const [rejectingTestId, setRejectingTestId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [rejecting, setRejecting] = useState(false)

  // Logs
  const [logsOpen, setLogsOpen] = useState<Record<string, boolean>>({})
  const [logsData, setLogsData] = useState<Record<string, TestLog[]>>({})
  const [logsLoading, setLogsLoading] = useState<Record<string, boolean>>({})

  // RBAC: derive canEdit from user role
  // The user object from authStore has is_admin. For role-based checks,
  // we check project membership role. Since authStore doesn't store project role,
  // we derive from a separate endpoint or fallback to admin check.
  const [userRole, setUserRole] = useState<string>('')

  useEffect(() => {
    const loadRole = async () => {
      if (!id || !user) return
      if (user.is_admin) {
        setUserRole('admin')
        return
      }
      try {
        const res = await apiClient.get(`/projects/${id}/members/me`)
        setUserRole(res.data?.role || '')
      } catch {
        setUserRole('')
      }
    }
    loadRole()
  }, [id, user])

  // RBAC: Apenas Tester edita testes. Admin NÃO atua em projeto. QA NÃO edita.
  const canEdit = userRole === 'tester'

  const loadTests = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const res = await apiClient.get(`/projects/${id}/tests`, { params: { test_type: activeTab } })
      setTests(Array.isArray(res.data) ? res.data : res.data?.items || [])
    } catch {
      setTests([])
    } finally {
      setLoading(false)
    }
  }, [id, activeTab])

  useEffect(() => {
    loadTests()
  }, [loadTests])

  // Handlers
  const handleEdit = (testId: string) => {
    const test = tests.find(t => t.id === testId)
    if (!test) return
    setEditingTest(test)
    setEditContent(test.content)
    setEditModalOpen(true)
  }

  const handleSaveEdit = async () => {
    if (!editingTest || !id) return
    setSaving(true)
    try {
      await apiClient.put(`/projects/${id}/tests/${editingTest.id}`, { content: editContent })
      setEditModalOpen(false)
      setEditingTest(null)
      await loadTests()
    } catch {
      // Error handled by interceptor
    } finally {
      setSaving(false)
    }
  }

  const handleApprove = async (testId: string) => {
    if (!id) return
    try {
      await apiClient.post(`/projects/${id}/tests/${testId}/approve`)
      await loadTests()
    } catch {
      // Error handled by interceptor
    }
  }

  const handleReject = (testId: string) => {
    setRejectingTestId(testId)
    setRejectReason('')
    setRejectModalOpen(true)
  }

  const handleConfirmReject = async () => {
    if (!rejectingTestId || !id || rejectReason.trim().length < 10) return
    setRejecting(true)
    try {
      await apiClient.post(`/projects/${id}/tests/${rejectingTestId}/reject`, { reason: rejectReason })
      setRejectModalOpen(false)
      setRejectingTestId(null)
      await loadTests()
    } catch {
      // Error handled by interceptor
    } finally {
      setRejecting(false)
    }
  }

  const handleExecute = async (testId: string) => {
    if (!id) return
    try {
      await apiClient.post(`/projects/${id}/qa/execute/${testId}`)
      await loadTests()
    } catch {
      // Error handled by interceptor
    }
  }

  const toggleLogs = async (testId: string) => {
    const isOpen = logsOpen[testId]
    setLogsOpen(prev => ({ ...prev, [testId]: !isOpen }))

    if (!isOpen && !logsData[testId] && id) {
      setLogsLoading(prev => ({ ...prev, [testId]: true }))
      try {
        const res = await apiClient.get(`/projects/${id}/qa/logs/${testId}`)
        setLogsData(prev => ({ ...prev, [testId]: Array.isArray(res.data) ? res.data : res.data?.items || [] }))
      } catch {
        setLogsData(prev => ({ ...prev, [testId]: [] }))
      } finally {
        setLogsLoading(prev => ({ ...prev, [testId]: false }))
      }
    }
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-1.5">
          <h2 className="text-lg font-semibold text-slate-100">Tester Review</h2>
          <HelpTooltip text="O Tester Review permite que testadores revisem, editem e aprovem os testes gerados automaticamente pelo GCA antes da execucao. Cada teste passa por revisao obrigatória: o codigo gerado pela IA pode ser ajustado pelo tester para cobrir cenarios especificos do projeto. Somente testes aprovados ou editados sao executados no QA Readiness." />
        </div>
        <p className="text-slate-500 text-sm mt-0.5">Revisão e aprovação de artefatos de teste por categoria</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-900 border border-slate-800 rounded-xl p-1">
        {TEST_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-violet-600 text-white'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
        </div>
      ) : tests.length === 0 ? (
        <div className="flex items-center justify-center h-32 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-center">
            <FlaskConical className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-slate-500 text-sm">Nenhum teste {activeTab} encontrado</p>
            <p className="text-slate-600 text-xs mt-1">Os testes serao gerados automaticamente após a fase de codificacao</p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {tests.map(test => (
            <div key={test.id}>
              <TestArtifactCard
                test={test}
                canEdit={canEdit}
                onEdit={handleEdit}
                onApprove={handleApprove}
                onReject={handleReject}
                onExecute={handleExecute}
              />
              {/* Logs toggle */}
              <div className="mt-1 ml-4">
                <button
                  onClick={() => toggleLogs(test.id)}
                  className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
                >
                  {logsOpen[test.id] ? 'Ocultar logs' : 'Ver logs de execucao'}
                </button>
                {logsOpen[test.id] && (
                  <div className="mt-2 bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                    {logsLoading[test.id] ? (
                      <div className="flex items-center justify-center py-4">
                        <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />
                      </div>
                    ) : !logsData[test.id] || logsData[test.id].length === 0 ? (
                      <p className="text-slate-600 text-xs p-3">Nenhum log de execucao encontrado</p>
                    ) : (
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-slate-800 text-slate-500">
                            <th className="text-left p-2 font-medium">Status</th>
                            <th className="text-left p-2 font-medium">Executado por</th>
                            <th className="text-left p-2 font-medium">Data</th>
                            <th className="text-left p-2 font-medium">Duracao</th>
                            <th className="text-left p-2 font-medium">Output</th>
                          </tr>
                        </thead>
                        <tbody>
                          {logsData[test.id].map(log => (
                            <tr key={log.id} className="border-b border-slate-800/50">
                              <td className="p-2">
                                <span className={`px-1.5 py-0.5 rounded text-xs ${
                                  log.status === 'passed' ? 'bg-emerald-900/30 text-emerald-400' :
                                  log.status === 'failed' ? 'bg-red-900/30 text-red-400' :
                                  'bg-amber-900/30 text-amber-400'
                                }`}>
                                  {log.status}
                                </span>
                              </td>
                              <td className="p-2 text-slate-400">{log.executed_by}</td>
                              <td className="p-2 text-slate-400">
                                {new Date(log.executed_at).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                              </td>
                              <td className="p-2 text-slate-400">{log.duration_ms ? `${log.duration_ms}ms` : '-'}</td>
                              <td className="p-2">
                                <pre className="text-slate-500 font-mono truncate max-w-xs">{log.output}</pre>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Edit Modal */}
      {editModalOpen && editingTest && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-[#0D0D18] border border-slate-800 rounded-2xl w-full max-w-3xl shadow-2xl flex flex-col max-h-[80vh]">
            <div className="flex items-center justify-between p-5 border-b border-slate-800">
              <div>
                <h3 className="text-slate-100 font-semibold">Editar Teste</h3>
                <p className="text-slate-500 text-xs mt-0.5">{editingTest.title} (v{editingTest.version})</p>
              </div>
              <button onClick={() => setEditModalOpen(false)} className="text-slate-500 hover:text-slate-300 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 flex-1 overflow-y-auto">
              <textarea
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                rows={20}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-3 text-sm text-slate-200 font-mono resize-none focus:outline-none focus:border-violet-500"
              />
            </div>
            <div className="flex gap-3 p-5 border-t border-slate-800">
              <button
                onClick={() => setEditModalOpen(false)}
                className="flex-1 px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-sm hover:bg-slate-700 transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={saving || editContent === editingTest.content}
                className="flex-1 px-4 py-2 rounded-lg bg-violet-600 text-white text-sm hover:bg-violet-500 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                Salvar Alteracoes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {rejectModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-[#0D0D18] border border-red-900/40 rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-900/40 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h3 className="text-slate-100 font-semibold">Rejeitar Teste</h3>
                <p className="text-red-400 text-xs">Justificativa obrigatória (mínimo 10 caracteres)</p>
              </div>
            </div>
            <textarea
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              rows={4}
              placeholder="Descreva o motivo da rejeicao..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:border-red-500"
            />
            {rejectReason.length > 0 && rejectReason.trim().length < 10 && (
              <p className="text-red-400 text-xs mt-1">Minimo 10 caracteres ({rejectReason.trim().length}/10)</p>
            )}
            <div className="flex gap-3 mt-4">
              <button
                onClick={() => { setRejectModalOpen(false); setRejectingTestId(null) }}
                className="flex-1 px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-sm hover:bg-slate-700 transition-colors"
              >
                Cancelar
              </button>
              <button
                disabled={rejectReason.trim().length < 10 || rejecting}
                onClick={handleConfirmReject}
                className="flex-1 px-4 py-2 rounded-lg bg-red-600 text-white text-sm hover:bg-red-500 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {rejecting && <Loader2 className="w-4 h-4 animate-spin" />}
                Confirmar Rejeicao
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
