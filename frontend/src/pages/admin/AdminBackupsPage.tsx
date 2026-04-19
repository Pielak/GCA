import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Database, ExternalLink, Loader2, RefreshCw, CheckCircle2, XCircle,
  Filter, Zap, Download,
} from 'lucide-react'
import { apiClient } from '@/lib/api'

interface BackupItem {
  id: string
  project_id: string
  project_name: string | null
  project_slug: string | null
  created_at: string
  completed_at: string | null
  trigger_source: string
  status: 'running' | 'completed' | 'failed'
  size_bytes: number
  sha256: string | null
  error_message: string | null
  restored_at: string | null
}

const TRIGGER_LABELS: Record<string, string> = {
  scheduled: '⏰ Auto 12:00',
  manual_gp: '👤 Manual (GP)',
  manual_admin: '🛡️ Manual (Admin)',
  startup_catchup: '↻ Catch-up',
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(2)} MB`
}

export function AdminBackupsPage() {
  const [items, setItems] = useState<BackupItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [projectFilter, setProjectFilter] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [triggeringPid, setTriggeringPid] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await apiClient.get('/admin/backups')
      setItems(res.data.items || [])
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Erro ao carregar backups')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Polling enquanto há running (banner cross-projeto)
  useEffect(() => {
    if (!items.some(b => b.status === 'running')) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [items, load])

  const projects = useMemo(() => {
    const map = new Map<string, { id: string; name: string; slug: string }>()
    items.forEach(b => {
      if (b.project_id && !map.has(b.project_id)) {
        map.set(b.project_id, {
          id: b.project_id,
          name: b.project_name || 'sem nome',
          slug: b.project_slug || '',
        })
      }
    })
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [items])

  const filtered = items.filter(b => {
    if (projectFilter && b.project_id !== projectFilter) return false
    if (statusFilter !== 'all' && b.status !== statusFilter) return false
    return true
  })

  const triggerBackup = async (pid: string) => {
    setTriggeringPid(pid)
    try {
      await apiClient.post(`/projects/${pid}/backups`)
      await load()
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Falha ao disparar')
    } finally {
      setTriggeringPid(null)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-violet-400" />
            <h1 className="text-xl font-semibold text-slate-100">Backups · visão admin</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Agregação de todos os backups por projeto. Disparar a pedido do GP ou administrar retenção.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Atualizar
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {/* Filtros */}
      <div className="flex flex-wrap gap-3 items-end p-3 bg-slate-900/40 border border-slate-800 rounded-xl">
        <div className="flex-1 min-w-[200px]">
          <label className="text-slate-500 text-xs block mb-1">
            <Filter className="inline w-3 h-3 mr-1" /> Projeto
          </label>
          <select
            value={projectFilter}
            onChange={e => setProjectFilter(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200"
          >
            <option value="">Todos os projetos</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-slate-500 text-xs block mb-1">Status</label>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200"
          >
            <option value="all">Todos</option>
            <option value="completed">Completos</option>
            <option value="running">Em andamento</option>
            <option value="failed">Falhas</option>
          </select>
        </div>
        <span className="text-slate-500 text-xs ml-auto self-end">
          {filtered.length} de {items.length} backups
        </span>
      </div>

      {/* Quick action — disparar backup pra projeto específico */}
      {projectFilter && (
        <div className="flex items-center justify-between p-3 bg-slate-900/40 border border-slate-800 rounded-xl">
          <span className="text-slate-300 text-sm">
            Disparar backup imediato para <strong>{projects.find(p => p.id === projectFilter)?.name}</strong> (a pedido do GP)
          </span>
          <button
            onClick={() => triggerBackup(projectFilter)}
            disabled={triggeringPid === projectFilter}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs rounded-lg"
          >
            {triggeringPid === projectFilter ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            Backup agora
          </button>
        </div>
      )}

      {/* Lista */}
      {filtered.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-10 text-center text-slate-500 text-sm">
          Nenhum backup encontrado com esses filtros.
        </div>
      ) : (
        <div className="overflow-x-auto bg-slate-900/40 border border-slate-800 rounded-xl">
          <table className="w-full text-sm">
            <thead className="text-slate-500 text-xs uppercase tracking-wider border-b border-slate-800">
              <tr>
                <th className="text-left py-2 px-3">Status</th>
                <th className="text-left py-2 px-3">Projeto</th>
                <th className="text-left py-2 px-3">Criado em</th>
                <th className="text-left py-2 px-3">Trigger</th>
                <th className="text-right py-2 px-3">Tamanho</th>
                <th className="text-left py-2 px-3">SHA</th>
                <th className="text-right py-2 px-3"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(b => (
                <tr key={b.id} className="border-b border-slate-800/50 hover:bg-slate-900/40">
                  <td className="py-2 px-3">
                    {b.status === 'completed' ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      : b.status === 'failed' ? <XCircle className="w-4 h-4 text-red-400" />
                      : <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />}
                  </td>
                  <td className="py-2 px-3">
                    <Link to={`/projects/${b.project_id}/backups`} className="text-slate-300 hover:text-violet-400 inline-flex items-center gap-1">
                      {b.project_name || b.project_id.slice(0, 8)}
                      <ExternalLink className="w-3 h-3 opacity-60" />
                    </Link>
                  </td>
                  <td className="py-2 px-3 text-slate-400">{new Date(b.created_at).toLocaleString('pt-BR')}</td>
                  <td className="py-2 px-3 text-slate-400 text-xs">{TRIGGER_LABELS[b.trigger_source] || b.trigger_source}</td>
                  <td className="py-2 px-3 text-right text-slate-400 tabular-nums">
                    {b.status === 'completed' ? formatBytes(b.size_bytes) : '—'}
                  </td>
                  <td className="py-2 px-3 text-slate-500 font-mono text-xs">{b.sha256?.slice(0, 12) || '—'}</td>
                  <td className="py-2 px-3 text-right">
                    {b.status === 'completed' && (
                      <a
                        href={`/api/v1/projects/${b.project_id}/backups/${b.id}/download`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-slate-400 hover:text-violet-400 text-xs"
                      >
                        <Download className="w-3 h-3" /> .zip
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
