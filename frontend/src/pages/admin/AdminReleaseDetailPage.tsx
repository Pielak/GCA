import { useState, useEffect, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft, Package, Loader2, AlertCircle, AlertTriangle,
  CheckCircle2, Clock, Camera, RotateCcw, PlayCircle, FileText,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

interface ReleaseItem {
  id: string
  kind: string
  ref_id: string | null
  title: string
  description: string | null
  affected_roles: string[]
  display_order: number
}

interface Release {
  id: string
  tag: string
  title: string
  body: string | null
  is_destructive: boolean
  status: 'pending' | 'applied' | 'rolled_back'
  declared_at: string | null
  applied_at: string | null
  applied_by: string | null
  source_yaml: string | null
  item_count: number
}

interface LogEntry {
  id: string
  event_type: string
  project_id: string | null
  actor_id: string | null
  metadata: Record<string, any> | null
  created_at: string | null
}

const KIND_LABELS: Record<string, string> = {
  mvp: 'MVP',
  mvp_emenda: 'MVP (emenda)',
  ticket: 'Ticket',
  feature: 'Feature',
  fix: 'Correção',
  schema_change: 'Mudança de schema',
}

const ROLE_LABELS: Record<string, string> = {
  all: 'Todos',
  admin: 'Admin',
  gp: 'GP',
  dev: 'Dev',
  tester: 'Tester',
  qa: 'QA',
}

const EVENT_LABELS: Record<string, string> = {
  applied: 'Aplicação registrada',
  snapshot_taken: 'Snapshot pré-release',
  rolled_back: 'Rollback de projeto',
  completion_task_created: 'Tarefa pós-release criada',
  completion_task_fulfilled: 'Tarefa pós-release concluída',
}

export function AdminReleaseDetailPage() {
  const { releaseId } = useParams<{ releaseId: string }>()
  const [release, setRelease] = useState<Release | null>(null)
  const [items, setItems] = useState<ReleaseItem[]>([])
  const [log, setLog] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)

  const load = useCallback(async () => {
    if (!releaseId) return
    try {
      const [detailRes, logRes] = await Promise.all([
        apiClient.get(`/admin/releases/${releaseId}`),
        apiClient.get(`/admin/releases/${releaseId}/log`),
      ])
      setRelease(detailRes.data.release)
      setItems(detailRes.data.items || [])
      setLog(logRes.data.entries || [])
      setError(null)
    } catch (e: unknown) {
      setError(getErrorMessage(e) || 'Erro ao carregar release.')
    } finally {
      setLoading(false)
    }
  }, [releaseId])

  useEffect(() => { load() }, [load])

  const applyDestructive = async () => {
    if (!releaseId || !release) return
    const msg = `Você está prestes a aplicar a release destrutiva ${release.tag}.\n\n` +
      `Será gerado um snapshot automático de cada projeto ativo ANTES das mudanças (via sistema de backup DT-063).\n\n` +
      `As migrations SQL destrutivas devem ter sido rodadas via upgrade.sh antes de o backend subir — este passo apenas registra a aplicação e captura o snapshot pré-release.\n\n` +
      `Confirmar?`
    if (!window.confirm(msg)) return
    setApplying(true)
    try {
      const res = await apiClient.post(`/admin/releases/${releaseId}/apply`, {
        confirm: true,
        take_snapshots: true,
      })
      alert(
        `Release ${release.tag} marcada como aplicada.\n` +
        `Snapshots criados: ${res.data.snapshots_taken}\n` +
        `Projetos afetados: ${res.data.affected_projects}`,
      )
      await load()
    } catch (e: unknown) {
      alert(getErrorMessage(e) || 'Falha ao aplicar release.')
    } finally {
      setApplying(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
      </div>
    )
  }
  if (error || !release) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <Link to="/admin/releases" className="text-violet-400 hover:text-violet-300 text-sm inline-flex items-center gap-1">
          <ArrowLeft className="w-3.5 h-3.5" /> Voltar
        </Link>
        <div className="mt-4 p-3 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-sm">
          {error || 'Release não encontrada.'}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      <Link to="/admin/releases" className="text-violet-400 hover:text-violet-300 text-sm inline-flex items-center gap-1">
        <ArrowLeft className="w-3.5 h-3.5" /> Voltar
      </Link>

      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex items-start gap-3">
          <Package className={`w-5 h-5 mt-1 ${release.is_destructive ? 'text-amber-400' : 'text-violet-400'}`} />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <code className="text-violet-300 text-sm font-mono font-bold">{release.tag}</code>
              {release.is_destructive && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/30">
                  Destrutiva
                </span>
              )}
              {release.status === 'pending' && (
                <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/30">
                  <Clock className="w-3 h-3" /> Pendente
                </span>
              )}
              {release.status === 'applied' && (
                <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                  <CheckCircle2 className="w-3 h-3" /> Aplicada
                </span>
              )}
            </div>
            <h1 className="text-slate-100 text-lg font-semibold mt-1">{release.title}</h1>
            {release.body && (
              <p className="text-slate-400 text-sm whitespace-pre-wrap mt-2">{release.body}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 text-[11px] text-slate-500 pt-2 border-t border-slate-800">
          {release.declared_at && <span>Declarada {new Date(release.declared_at).toLocaleString('pt-BR')}</span>}
          {release.applied_at && (
            <>
              <span>·</span>
              <span>Aplicada {new Date(release.applied_at).toLocaleString('pt-BR')}</span>
            </>
          )}
          {release.source_yaml && (
            <>
              <span>·</span>
              <span className="font-mono">{release.source_yaml}</span>
            </>
          )}
        </div>

        {/* Botão de apply para destrutiva pendente */}
        {release.status === 'pending' && release.is_destructive && (
          <div className="flex items-start gap-2 p-3 bg-amber-950/30 border border-amber-900/40 rounded-lg">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-amber-200 text-xs">
              Esta release é destrutiva. Ao confirmar, o sistema tira snapshot de cada projeto ativo antes de registrar a aplicação (as migrations SQL devem ter sido executadas via upgrade.sh).
            </div>
            <button
              onClick={applyDestructive}
              disabled={applying}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-xs rounded-lg flex-shrink-0"
            >
              {applying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PlayCircle className="w-3.5 h-3.5" />}
              Aplicar com snapshot
            </button>
          </div>
        )}
      </div>

      {/* Items do changelog */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5">
        <h2 className="text-slate-200 text-sm font-medium mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4 text-slate-400" /> Itens da release ({items.length})
        </h2>
        {items.length === 0 ? (
          <p className="text-slate-500 text-xs italic">Sem itens.</p>
        ) : (
          <ul className="space-y-2">
            {items.map(it => (
              <li key={it.id} className="border-l-2 border-slate-700 pl-3 py-1">
                <div className="flex items-center gap-2 text-[10px] text-slate-500 uppercase tracking-wider">
                  <span className="font-semibold text-slate-400">{KIND_LABELS[it.kind] || it.kind}</span>
                  {it.ref_id && <span className="font-mono text-violet-400">{it.ref_id}</span>}
                  <span>·</span>
                  <span>
                    Visível para: {it.affected_roles.map(r => ROLE_LABELS[r] || r).join(', ')}
                  </span>
                </div>
                <p className="text-slate-200 text-sm mt-0.5">{it.title}</p>
                {it.description && (
                  <p className="text-slate-400 text-xs mt-1 whitespace-pre-wrap">{it.description}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Log de eventos */}
      {log.length > 0 && (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5">
          <h2 className="text-slate-200 text-sm font-medium mb-3">Log de aplicação</h2>
          <ul className="space-y-1.5">
            {log.map(e => (
              <li key={e.id} className="flex items-start gap-2 text-xs">
                <span className="text-slate-500 flex-shrink-0 w-36">
                  {e.created_at && new Date(e.created_at).toLocaleString('pt-BR')}
                </span>
                <span className="text-slate-300 flex-1">
                  <strong className="text-violet-300">{EVENT_LABELS[e.event_type] || e.event_type}</strong>
                  {e.project_id && <span className="text-slate-500"> · projeto {e.project_id.slice(0, 8)}…</span>}
                  {e.metadata?.snapshot_id && (
                    <span className="text-slate-500"> · snapshot {String(e.metadata.snapshot_id).slice(0, 8)}…</span>
                  )}
                  {e.metadata?.trigger && (
                    <span className="text-slate-500"> · trigger {e.metadata.trigger}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
