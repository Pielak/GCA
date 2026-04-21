import { useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  BookOpen, RefreshCw, Loader2, AlertTriangle, FileText, Network, Sparkles,
} from 'lucide-react'
import {
  useLiveDocs, useBulkRegenerateModuleDocs, useGenerateConsolidatedDoc,
  type LiveDocListItem, type LiveDocType,
} from '@/hooks/useLiveDocs'
import { useStaleSummary } from '@/hooks/useTestSpecs'
import { LiveDocModal } from '@/components/livedocs/LiveDocModal'
import { ERSCard } from '@/components/livedocs/ERSCard'
import { GlossaryPanel } from '@/components/livedocs/GlossaryPanel'
import { TraceabilityPanel } from '@/components/livedocs/TraceabilityPanel'

/**
 * MVP 10 Fase 10.7 — Documentação Viva real (LiveDocs).
 *
 * Substitui o placeholder anterior (seções derivadas do OCG sem
 * conteúdo textual) por LiveDocs efetivos:
 *   - module_doc (1 por módulo) via Ollama §6.2
 *   - index + architecture (globais) via Premium §6.3
 *
 * Cada item exibe stale flag + modal com provenance.
 */

const TYPE_META: Record<LiveDocType, {
  label: string; icon: React.ReactNode; border: string; chip: string;
}> = {
  module_doc: {
    label: 'Documentação de Módulo',
    icon: <FileText className="w-4 h-4" />,
    border: 'border-emerald-700/40',
    chip: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50',
  },
  index: {
    label: 'Índice Executivo',
    icon: <BookOpen className="w-4 h-4" />,
    border: 'border-violet-700/40',
    chip: 'bg-violet-900/30 text-violet-300 border-violet-700/50',
  },
  architecture: {
    label: 'Arquitetura',
    icon: <Network className="w-4 h-4" />,
    border: 'border-sky-700/40',
    chip: 'bg-sky-900/30 text-sky-300 border-sky-700/50',
  },
}

const TYPE_ORDER: LiveDocType[] = ['index', 'architecture', 'module_doc']

export function LiveDocsPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { data: docs, isLoading } = useLiveDocs(projectId)
  const { data: summary } = useStaleSummary(projectId)
  const bulkModule = useBulkRegenerateModuleDocs(projectId)
  const genConsolidated = useGenerateConsolidatedDoc(projectId)
  const [openDocId, setOpenDocId] = useState<string | null>(null)
  const [pending, setPending] = useState<LiveDocType | null>(null)

  const staleByType = summary?.live_docs?.by_type || {}
  const staleCountOf = (t: LiveDocType) => staleByType[t]?.stale ?? 0

  const runModuleBulk = () => {
    setPending('module_doc')
    bulkModule.mutate(undefined, { onSettled: () => setPending(null) })
  }
  const runConsolidated = (t: 'index' | 'architecture') => {
    setPending(t)
    genConsolidated.mutate(t, { onSettled: () => setPending(null) })
  }

  const byType: Record<LiveDocType, LiveDocListItem[]> = {
    module_doc: [], index: [], architecture: [],
  }
  for (const d of docs || []) {
    if (d.doc_type in byType) {
      byType[d.doc_type].push(d)
    }
  }

  const total = docs?.length ?? 0
  const staleCount = (docs || []).filter((d) => d.is_stale).length

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Documentação Viva</h2>
          <p className="text-slate-500 text-sm mt-0.5">
            Docs geradas por LLM a partir do OCG atual. Cada item registra
            sua procedência (versão do OCG, ingestões e modelo usado).
          </p>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            onClick={runModuleBulk}
            disabled={pending !== null}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded border border-slate-700 text-slate-300 hover:border-slate-500 hover:text-slate-100 disabled:opacity-50"
            title="Gera/regera uma doc por módulo via Ollama local"
          >
            {pending === 'module_doc' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Docs de Módulo
            {staleCountOf('module_doc') > 0 && (
              <span className="text-[10px] px-1 rounded bg-amber-500/20 text-amber-300">
                {staleCountOf('module_doc')}
              </span>
            )}
          </button>
          {(['index', 'architecture'] as const).map((t) => {
            const label = t === 'index' ? 'Índice' : 'Arquitetura'
            const n = staleCountOf(t)
            const busy = pending === t
            return (
              <button
                key={t}
                type="button"
                onClick={() => runConsolidated(t)}
                disabled={pending !== null}
                className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded bg-violet-600/30 border border-violet-500/40 text-violet-200 hover:bg-violet-600/40 disabled:opacity-50"
                title={`Gera/regera ${label.toLowerCase()} via Premium`}
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                {label}
                {n > 0 && (
                  <span className="text-[10px] px-1 rounded bg-amber-500/30 text-amber-200">
                    {n}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* MVP 19 Fase 19.2 — card do ERS (arquivo docs/ERS.md no Git).
          Vive separado dos LiveDocs tradicionais porque tem UX diferente:
          um único documento por projeto, commit no repo, histórico via git. */}
      {projectId && <ERSCard projectId={projectId} />}

      {/* MVP 19 Fase 19.3 — glossário vivo por projeto.
          Alimenta a seção 1.3 do ERS quando os termos são aprovados. */}
      {projectId && <GlossaryPanel projectId={projectId} />}

      {/* MVP 19 Fase 19.4 — matriz de rastreabilidade (read-only).
          Alimenta a seção 4 do ERS ao regenerar. */}
      {projectId && <TraceabilityPanel projectId={projectId} />}

      {/* Stale banner — aggregate via stale-summary quando disponível */}
      {staleCount > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/40 rounded p-3 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-[12px] text-amber-200 flex-1">
            <strong>{staleCount} documento(s) desatualizado(s)</strong> — OCG
            evoluiu desde a última geração.
            {summary?.current_ocg_version !== null && summary?.current_ocg_version !== undefined
              ? ` Versão atual: v${summary.current_ocg_version}.`
              : ''}
            {' '}Use os botões acima para regerar por tipo.
          </div>
        </div>
      )}

      {/* Stats */}
      {total > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-center">
            <p className="text-2xl font-semibold text-slate-100">{total}</p>
            <p className="text-slate-500 text-xs mt-1">Total de docs</p>
          </div>
          <div className="bg-emerald-950/20 border border-emerald-800/30 rounded-xl p-4 text-center">
            <p className="text-2xl font-semibold text-emerald-400">{total - staleCount}</p>
            <p className="text-slate-500 text-xs mt-1">Atualizados</p>
          </div>
          <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-4 text-center">
            <p className="text-2xl font-semibold text-amber-400">{staleCount}</p>
            <p className="text-slate-500 text-xs mt-1">Desatualizados</p>
          </div>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-10 text-slate-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin mr-2" />
          Carregando docs…
        </div>
      )}

      {/* Empty */}
      {!isLoading && total === 0 && (
        <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl text-slate-500">
          <FileText className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">Nenhuma documentação viva gerada ainda.</p>
          <p className="text-[11px] mt-1 text-slate-600">
            Clique nos botões acima para gerar — "Docs de Módulo" (uma por
            módulo do Roadmap) ou "Index + Architecture" (consolidados).
          </p>
        </div>
      )}

      {/* Listagem agrupada por tipo */}
      {!isLoading && total > 0 && (
        <div className="space-y-5">
          {TYPE_ORDER.map((t) => {
            const items = byType[t]
            if (items.length === 0) return null
            const meta = TYPE_META[t]
            return (
              <section key={t} className="space-y-2">
                <h3 className="flex items-center gap-2 text-slate-300 text-sm font-semibold">
                  <span className={`p-1 rounded ${meta.chip} border`}>{meta.icon}</span>
                  {meta.label}
                  <span className="text-[11px] text-slate-500">({items.length})</span>
                </h3>
                <div className="space-y-1.5">
                  {items.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => setOpenDocId(d.id)}
                      className={`w-full text-left px-3 py-2 rounded border hover:ring-1 hover:ring-violet-500/50 transition-all ${
                        d.is_stale
                          ? 'border-amber-500/40 bg-amber-950/10'
                          : `${meta.border} bg-slate-950/30 hover:bg-slate-900/40`
                      }`}
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[11px] text-slate-300 truncate flex-1">
                          {d.module_id
                            ? `Módulo ${d.module_id.slice(0, 8)}…`
                            : `Global do projeto`}
                        </span>
                        {d.generator_provider && (
                          <span className="text-[10px] text-slate-500 whitespace-nowrap">
                            {d.generator_provider} / {d.generator_model}
                          </span>
                        )}
                        {d.is_stale && (
                          <span
                            className="text-[10px] text-amber-300 flex items-center gap-1"
                            title={d.stale_reason || 'OCG evoluiu desde a geração'}
                          >
                            <AlertTriangle className="w-3 h-3" />
                            stale
                          </span>
                        )}
                        <span className="text-[10px] text-slate-500 whitespace-nowrap">
                          {d.content_chars.toLocaleString('pt-BR')} chars
                        </span>
                      </div>
                      {d.content_preview && (
                        <p className="text-[10px] text-slate-500 mt-1 truncate">
                          {d.content_preview}
                        </p>
                      )}
                    </button>
                  ))}
                </div>
              </section>
            )
          })}
        </div>
      )}

      {/* Modal */}
      {openDocId && projectId && (
        <LiveDocModal
          projectId={projectId}
          docId={openDocId}
          onClose={() => setOpenDocId(null)}
        />
      )}
    </div>
  )
}
