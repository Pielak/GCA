import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  Database, Download, History, Loader2, RefreshCw, RotateCcw,
  AlertCircle, CheckCircle2, XCircle, Clock, Zap,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useProjectPermissions } from '@/hooks/useProjectPermissions'
import { useAuthStore } from '@/stores/authStore'
import { getErrorMessage } from '@/lib/errors'
import { formatDateTimeBR } from '@/lib/datetime'

interface BackupItem {
  id: string
  project_id: string
  created_at: string
  completed_at: string | null
  trigger_source: string
  status: 'running' | 'completed' | 'failed'
  size_bytes: number
  sha256: string | null
  error_message: string | null
  restored_at: string | null
  restored_by: string | null
  created_by: string | null
}

const TRIGGER_LABELS: Record<string, { label: string; color: string }> = {
  scheduled: { label: 'Automático (12:00)', color: 'text-cyan-400' },
  manual_gp: { label: 'Manual (GP)', color: 'text-emerald-400' },
  manual_admin: { label: 'Manual (Admin)', color: 'text-violet-400' },
  startup_catchup: { label: 'Catch-up (servidor reiniciou)', color: 'text-amber-400' },
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(2)} MB`
}

export function ProjectBackupPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { hasRole } = useProjectPermissions()
  const isAdmin = useAuthStore(s => s.user?.is_admin || false)
  const isGP = hasRole('gp')
  const canOperate = isAdmin || isGP

  const [items, setItems] = useState<BackupItem[]>([])
  const [retentionLimit, setRetentionLimit] = useState(10)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)

  const load = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await apiClient.get(`/projects/${projectId}/backups`)
      setItems(res.data.items || [])
      setRetentionLimit(res.data.retention_limit ?? 10)
    } catch (e: unknown) {
      setError(getErrorMessage(e) || 'Erro ao carregar backups')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { load() }, [load])

  // Polling enquanto algum backup estiver running (atualiza barra de status)
  useEffect(() => {
    const hasRunning = items.some(b => b.status === 'running')
    if (!hasRunning) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [items, load])

  const triggerBackup = async () => {
    if (!projectId) return
    setCreating(true)
    setError(null)
    try {
      await apiClient.post(`/projects/${projectId}/backups`)
      setToast({ kind: 'ok', msg: 'Backup iniciado.' })
      await load()
    } catch (e: unknown) {
      const msg = getErrorMessage(e) || 'Falha ao disparar backup'
      setError(msg)
      setToast({ kind: 'err', msg })
    } finally {
      setCreating(false)
      setTimeout(() => setToast(null), 4000)
    }
  }

  const restoreBackup = async (backupId: string) => {
    if (!projectId) return
    const ok = window.confirm(
      'Restaurar este backup vai SUBSTITUIR todos os dados atuais do projeto pelos dados do backup.\n\n' +
      'Esta operação é destrutiva. Deseja continuar?'
    )
    if (!ok) return
    setRestoringId(backupId)
    setError(null)
    try {
      await apiClient.post(`/projects/${projectId}/backups/${backupId}/restore?confirm=true`)
      setToast({ kind: 'ok', msg: 'Restore concluído.' })
      await load()
    } catch (e: unknown) {
      const msg = getErrorMessage(e) || 'Falha no restore'
      setError(msg)
      setToast({ kind: 'err', msg })
    } finally {
      setRestoringId(null)
      setTimeout(() => setToast(null), 5000)
    }
  }

  const downloadBackup = (backupId: string) => {
    if (!projectId) return
    const url = `/api/v1/projects/${projectId}/backups/${backupId}/download`
    window.open(url, '_blank')
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando backups...
      </div>
    )
  }

  const completed = items.filter(b => b.status === 'completed')
  const running = items.filter(b => b.status === 'running')

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-violet-400" />
            <h1 className="text-xl font-semibold text-slate-100">Backups do Projeto</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Backup automático diário às 12:00. Mantém os últimos {retentionLimit} backups.
            {' '}<span className="text-slate-600">Compartimentalizado por projeto.</span>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Atualizar
          </button>
          {canOperate && (
            <button
              onClick={triggerBackup}
              disabled={creating || running.length > 0}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs rounded-lg"
              title={running.length > 0 ? 'Já existe um backup em andamento' : 'Dispara backup imediato'}
            >
              {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              {creating ? 'Iniciando...' : 'Backup agora'}
            </button>
          )}
        </div>
      </div>

      {toast && (
        <div className={`px-3 py-2 rounded text-sm ${
          toast.kind === 'ok' ? 'bg-emerald-950/30 border border-emerald-900/40 text-emerald-300'
          : 'bg-red-950/30 border border-red-900/40 text-red-300'
        }`}>
          {toast.msg}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {running.length > 0 && (
        <div className="flex items-center gap-2 p-3 bg-amber-950/30 border border-amber-900/40 rounded-lg text-amber-300 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          Backup em andamento... atualizando automaticamente.
        </div>
      )}

      {/* Cards de backup */}
      {items.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-10 text-center text-slate-500 text-sm">
          Nenhum backup ainda. {canOperate && 'Clique em "Backup agora" pra criar o primeiro.'}
        </div>
      ) : (
        <div className="space-y-2">
          {items.map(b => {
            const trigger = TRIGGER_LABELS[b.trigger_source] || { label: b.trigger_source, color: 'text-slate-400' }
            const statusIcon = b.status === 'completed' ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              : b.status === 'failed' ? <XCircle className="w-4 h-4 text-red-400" />
              : <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />
            return (
              <div
                key={b.id}
                className={`bg-slate-900/40 border rounded-xl p-4 ${
                  b.status === 'failed' ? 'border-red-900/40' :
                  b.status === 'running' ? 'border-amber-900/40' : 'border-slate-800'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {statusIcon}
                      <span className="text-slate-200 text-sm font-medium">
                        {formatDateTimeBR(b.created_at)}
                      </span>
                      <span className={`text-xs ${trigger.color}`}>· {trigger.label}</span>
                      {b.restored_at && (
                        <span className="text-xs text-cyan-400">
                          · ↺ usado em restore em {formatDateTimeBR(b.restored_at)}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-slate-500 text-xs">
                      {b.status === 'completed' && (
                        <>
                          <span>{formatBytes(b.size_bytes)}</span>
                          <span>·</span>
                          <span className="font-mono">SHA {b.sha256?.slice(0, 12)}…</span>
                          {b.completed_at && (
                            <>
                              <span>·</span>
                              <span>
                                <Clock className="inline w-3 h-3 mr-0.5" />
                                durou {Math.max(0, Math.round((new Date(b.completed_at).getTime() - new Date(b.created_at).getTime()) / 1000))}s
                              </span>
                            </>
                          )}
                        </>
                      )}
                      {b.status === 'failed' && b.error_message && (
                        <span className="text-red-400">{b.error_message.slice(0, 200)}</span>
                      )}
                    </div>
                  </div>
                  {b.status === 'completed' && (
                    <div className="flex gap-2 flex-shrink-0">
                      <button
                        onClick={() => downloadBackup(b.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg"
                        title="Baixar .zip do backup"
                      >
                        <Download className="w-3.5 h-3.5" /> Baixar
                      </button>
                      {canOperate && (
                        <button
                          onClick={() => restoreBackup(b.id)}
                          disabled={restoringId !== null}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-700/30 hover:bg-amber-700/50 disabled:opacity-40 border border-amber-700/40 text-amber-200 text-xs rounded-lg"
                          title="Restaurar projeto a partir deste backup (destrutivo)"
                        >
                          {restoringId === b.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                          Rollback
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <p className="text-xs text-slate-600">
        <History className="inline w-3 h-3 mr-1" />
        Backup automático: <code className="bg-slate-800/50 px-1 py-0.5 rounded">cron 0 12 * * * America/Sao_Paulo</code>
        {' · '}
        Catch-up automático no startup se servidor estava down no horário.
      </p>
    </div>
  )
}
