import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'

/**
 * MVP 27 Fase 2 + Fase 3 — Timeline de mudanças do OCG que afetam
 * Backlog e Roadmap.
 *
 * Card accordion reutilizável que consome `GET /projects/:pid/ocg/history`
 * (endpoint já existente desde MVP 9). Renderiza eventos cronológicos com
 * versão from→to, resumo, trigger, autor e timestamp. Backlog e Roadmap
 * são views diferentes do MESMO grafo de mudanças (OCG cascateia pra
 * ambos), então a timeline é comum.
 *
 * Uso:
 *   <OCGChangesTimelineCard projectId={id} scope="backlog" />
 *   <OCGChangesTimelineCard projectId={id} scope="roadmap" />
 *
 * `scope` controla só o label do header — a fonte de dados é a mesma.
 */

interface OCGHistoryEntry {
  id: string
  version_from: number
  version_to: number
  change_summary: string | null
  fields_changed: string | null
  created_at: string | null
  changed_by: { id: string; full_name: string; email: string } | null
  trigger_source: string | null
  can_rollback: boolean
}

interface OCGHistoryResponse {
  current_version: number
  history: OCGHistoryEntry[]
}

interface Props {
  projectId: string
  scope: 'backlog' | 'roadmap'
}

const SCOPE_LABEL: Record<Props['scope'], string> = {
  backlog: 'Histórico de alterações — Backlog',
  roadmap: 'Histórico de alterações — Roadmap',
}

const SCOPE_HINT: Record<Props['scope'], string> = {
  backlog: 'Backlog é regenerado a partir do OCG a cada mudança relevante',
  roadmap: 'Roadmap é derivado do OCG e do Arguidor — mudanças no OCG cascateiam aqui',
}

function triggerBadge(t: string | null): { text: string; cls: string } {
  const map: Record<string, { text: string; cls: string }> = {
    document_ingestion: { text: 'ingestão', cls: 'bg-sky-500/10 text-sky-300 border-sky-500/30' },
    manual_reconsolidate: { text: 'reconsolidação manual', cls: 'bg-violet-500/10 text-violet-300 border-violet-500/30' },
    manual_rollback: { text: 'rollback', cls: 'bg-red-500/10 text-red-300 border-red-500/30' },
    arguider_response: { text: 'resposta Arguidor', cls: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' },
  }
  const fallback = { text: t ?? 'desconhecido', cls: 'bg-slate-800/60 text-slate-400 border-slate-700' }
  return map[t ?? ''] ?? fallback
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function OCGChangesTimelineCard({ projectId, scope }: Props) {
  const [open, setOpen] = useState(false)

  const { data, isLoading, error } = useQuery<OCGHistoryResponse>({
    queryKey: ['ocg', 'history', projectId],
    queryFn: async () => {
      const res = await apiClient.get<OCGHistoryResponse>(
        `/projects/${projectId}/ocg/history`,
      )
      return res.data
    },
    enabled: !!projectId && open,
    staleTime: 1000 * 30,
  })

  const history = data?.history ?? []
  const hasEvents = history.length > 0

  return (
    <div className="mt-6 border border-slate-800 rounded-xl bg-slate-900/40">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-slate-800/40 rounded-xl transition-colors"
      >
        <div className="flex flex-col gap-0.5">
          <span className="text-sm font-semibold text-slate-200">
            {SCOPE_LABEL[scope]}
          </span>
          <span className="text-[11px] text-slate-500">{SCOPE_HINT[scope]}</span>
        </div>
        <div className="flex items-center gap-3">
          {open && data && (
            <span className="text-[10px] text-slate-500 tabular-nums">
              versão atual: <span className="text-slate-300 font-semibold">v{data.current_version}</span>
            </span>
          )}
          <span className="text-sm text-slate-400">{open ? '▾' : '▸'}</span>
        </div>
      </button>

      {open && (
        <div className="px-5 pb-4 space-y-3 border-t border-slate-800">
          {isLoading && (
            <div className="text-xs text-slate-500 py-3">Carregando histórico...</div>
          )}

          {error && (
            <div className="text-xs text-red-400 py-3">
              Erro ao carregar histórico: {(error as Error).message}
            </div>
          )}

          {!isLoading && !error && !hasEvents && (
            <div className="text-xs text-slate-400 py-4 leading-relaxed">
              Nenhuma alteração registrada no OCG ainda. Conforme você ingere
              documentos ou reconsolida manualmente, cada evento aparece aqui
              cronologicamente.
            </div>
          )}

          {!isLoading && !error && hasEvents && (
            <div className="pt-3">
              <div className="grid grid-cols-[auto_auto_1fr_auto] gap-3 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 border-b border-slate-800">
                <span>Quando</span>
                <span>Versão</span>
                <span>Resumo</span>
                <span>Trigger</span>
              </div>
              <div className="divide-y divide-slate-800/60">
                {history.map(ev => {
                  const trig = triggerBadge(ev.trigger_source)
                  return (
                    <div
                      key={ev.id}
                      className="grid grid-cols-[auto_auto_1fr_auto] gap-3 px-3 py-2 text-xs items-start hover:bg-slate-800/30"
                    >
                      <span className="text-slate-500 tabular-nums whitespace-nowrap">
                        {formatDate(ev.created_at)}
                      </span>
                      <span className="tabular-nums text-slate-400">
                        <span className="text-slate-500">v{ev.version_from}</span>
                        <span className="text-slate-600"> → </span>
                        <span className="text-slate-200 font-semibold">v{ev.version_to}</span>
                      </span>
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <span className="text-slate-300 leading-snug break-words">
                          {ev.change_summary ?? '(sem resumo)'}
                        </span>
                        {ev.changed_by && (
                          <span className="text-[10px] text-slate-600">
                            por {ev.changed_by.full_name}
                          </span>
                        )}
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded border whitespace-nowrap ${trig.cls}`}>
                        {trig.text}
                      </span>
                    </div>
                  )
                })}
              </div>
              {history.length >= 50 && (
                <div className="text-[10px] text-slate-600 text-center pt-3">
                  Exibindo os 50 eventos mais recentes. Eventos anteriores ficam
                  preservados no audit log.
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
