import { useState, useEffect, useCallback } from 'react'
import {
  Package, Loader2, AlertCircle, Sparkles, ChevronDown, ChevronRight,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

interface ReleaseItemDetail {
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
  status: string
  applied_at: string | null
  item_count: number
}

const KIND_ICON: Record<string, string> = {
  mvp: '🚀',
  mvp_emenda: '🔧',
  ticket: '🎫',
  feature: '✨',
  fix: '🐛',
  schema_change: '🧱',
}

const KIND_LABELS: Record<string, string> = {
  mvp: 'MVP',
  mvp_emenda: 'MVP (emenda)',
  ticket: 'Ticket',
  feature: 'Feature',
  fix: 'Correção',
  schema_change: 'Mudança técnica',
}

export function ReleasesPage() {
  const [items, setItems] = useState<Release[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [expandedItems, setExpandedItems] = useState<ReleaseItemDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/releases')
      setItems(res.data.items || [])
      setError(null)
    } catch (e: unknown) {
      setError(getErrorMessage(e) || 'Erro ao carregar releases.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggleExpand = async (releaseId: string) => {
    if (expandedId === releaseId) {
      setExpandedId(null)
      setExpandedItems([])
      return
    }
    setExpandedId(releaseId)
    setExpandedItems([])
    try {
      const res = await apiClient.get(`/releases/${releaseId}`)
      setExpandedItems(res.data.items || [])
    } catch (e: unknown) {
      setExpandedItems([])
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      <div className="flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-violet-400" />
        <h1 className="text-xl font-semibold text-slate-100">Novidades e entregas</h1>
      </div>
      <p className="text-slate-500 text-sm">
        Changelog das versões do GCA aplicadas nesta instância. Cada item lista o que foi entregue e quem é afetado.
      </p>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 p-6 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
        </div>
      ) : items.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-10 text-center text-slate-500 text-sm">
          Nenhuma release aplicada ainda.
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(r => {
            const isOpen = expandedId === r.id
            return (
              <div
                key={r.id}
                className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden"
              >
                <button
                  onClick={() => toggleExpand(r.id)}
                  className="w-full flex items-start gap-3 px-4 py-3 hover:bg-slate-900/70 transition-colors text-left"
                >
                  <Package className="w-4 h-4 mt-0.5 text-violet-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="text-violet-300 text-xs font-mono font-bold">{r.tag}</code>
                      <h3 className="text-slate-100 text-sm font-medium truncate">{r.title}</h3>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-500">
                      <span>{r.item_count} destaque(s)</span>
                      {r.applied_at && (
                        <>
                          <span>·</span>
                          <span>{new Date(r.applied_at).toLocaleString('pt-BR')}</span>
                        </>
                      )}
                    </div>
                  </div>
                  {isOpen ? <ChevronDown className="w-4 h-4 text-slate-500 mt-1" /> : <ChevronRight className="w-4 h-4 text-slate-500 mt-1" />}
                </button>
                {isOpen && (
                  <div className="border-t border-slate-800 bg-slate-950/30 p-4 space-y-3">
                    {r.body && (
                      <p className="text-slate-400 text-xs whitespace-pre-wrap">{r.body}</p>
                    )}
                    {expandedItems.length === 0 ? (
                      <p className="text-slate-500 text-xs italic">Sem destaques relevantes para você nesta release.</p>
                    ) : (
                      <ul className="space-y-2">
                        {expandedItems.map(it => (
                          <li key={it.id} className="flex items-start gap-2">
                            <span className="text-sm flex-shrink-0">{KIND_ICON[it.kind] || '•'}</span>
                            <div className="flex-1 min-w-0">
                              <p className="text-slate-200 text-sm">{it.title}</p>
                              {it.description && (
                                <p className="text-slate-400 text-xs mt-0.5">{it.description}</p>
                              )}
                              <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                                {KIND_LABELS[it.kind] || it.kind}{it.ref_id ? ` · ${it.ref_id}` : ''}
                              </span>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
