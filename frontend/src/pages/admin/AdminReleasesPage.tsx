import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  Package, RefreshCw, Loader2, AlertCircle, AlertTriangle,
  CheckCircle2, Clock, ChevronRight,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

interface ReleaseItem {
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

const STATUS_META: Record<string, { label: string; classes: string; icon: any }> = {
  pending: { label: 'Pendente', classes: 'bg-amber-500/10 text-amber-300 border-amber-500/30', icon: Clock },
  applied: { label: 'Aplicada', classes: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30', icon: CheckCircle2 },
  rolled_back: { label: 'Revertida', classes: 'bg-slate-500/10 text-slate-400 border-slate-500/30', icon: AlertTriangle },
}

export function AdminReleasesPage() {
  const [items, setItems] = useState<ReleaseItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/admin/releases')
      setItems(res.data.items || [])
      setError(null)
    } catch (e: unknown) {
      setError(getErrorMessage(e) || 'Erro ao carregar releases.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const pending = items.filter(r => r.status === 'pending')
  const applied = items.filter(r => r.status !== 'pending')

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Package className="w-5 h-5 text-violet-400" />
            <h1 className="text-xl font-semibold text-slate-100">Releases — visão admin</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Releases aplicadas na instância e pendentes (destrutivas aguardando confirmação).
            Releases não-destrutivas são aplicadas automaticamente no startup.
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
        <div className="flex items-center gap-2 p-3 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 p-6 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
        </div>
      ) : (
        <>
          {pending.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-slate-300 text-sm font-medium flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Pendentes de aplicação ({pending.length})
              </h2>
              {pending.map(r => <ReleaseRow key={r.id} release={r} />)}
            </div>
          )}

          <div className="space-y-2">
            <h2 className="text-slate-300 text-sm font-medium">
              Histórico ({applied.length})
            </h2>
            {applied.length === 0 ? (
              <p className="text-slate-500 text-sm italic">Ainda não há releases aplicadas.</p>
            ) : (
              applied.map(r => <ReleaseRow key={r.id} release={r} />)
            )}
          </div>
        </>
      )}
    </div>
  )
}

function ReleaseRow({ release }: { release: ReleaseItem }) {
  const sm = STATUS_META[release.status]
  const SIcon = sm.icon
  return (
    <Link
      to={`/admin/releases/${release.id}`}
      className="block bg-slate-900/40 hover:bg-slate-900/70 border border-slate-800 hover:border-slate-700 rounded-xl px-4 py-3 transition-colors"
    >
      <div className="flex items-start gap-3">
        <Package className={`w-4 h-4 mt-0.5 flex-shrink-0 ${release.is_destructive ? 'text-amber-400' : 'text-slate-400'}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <code className="text-violet-300 text-xs font-mono font-bold">{release.tag}</code>
            <h3 className="text-slate-100 text-sm font-medium truncate">{release.title}</h3>
            <span className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md border ${sm.classes}`}>
              <SIcon className="w-3 h-3" /> {sm.label}
            </span>
            {release.is_destructive && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/30">
                Destrutiva
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1.5 text-[11px] text-slate-500">
            <span>{release.item_count} item(s)</span>
            {release.applied_at && (
              <>
                <span>·</span>
                <span>Aplicada em {new Date(release.applied_at).toLocaleString('pt-BR')}</span>
              </>
            )}
            {release.source_yaml && (
              <>
                <span>·</span>
                <span className="font-mono">{release.source_yaml}</span>
              </>
            )}
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-slate-600 mt-2" />
      </div>
    </Link>
  )
}
