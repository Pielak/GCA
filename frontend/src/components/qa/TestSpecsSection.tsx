import { useState } from 'react'
import {
  ClipboardList, Loader2, AlertTriangle, RefreshCw, Shield, Scale,
  CheckCircle2, Circle, FileText, Sparkles,
} from 'lucide-react'
import {
  useTestSpecs, useStaleSummary,
  useBulkRegenerateTestSpecs, useBulkRegenerateGlobalSpecs,
  type TestSpecListItem, type TestSpecType,
} from '@/hooks/useTestSpecs'
import { TestSpecModal } from './TestSpecModal'

/**
 * MVP 10 Fase 10.5 — Seção "Plano de Testes" da QAReadinessPage.
 *
 * Mostra test_specs do projeto agrupados por tipo, com chips de status
 * e badge stale. Banner no topo quando needs_regeneration. Botões
 * "Regenerar" granulares (unit/integration via Ollama; security/
 * compliance via Premium; tudo).
 *
 * Preserva QA Execution / Tester Review existentes — essa seção só
 * adiciona, não substitui.
 */

const TYPE_META: Record<TestSpecType, { label: string; icon: React.ReactNode; style: string }> = {
  unit: {
    label: 'Unitários',
    icon: <Circle className="w-3.5 h-3.5" />,
    style: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50',
  },
  integration: {
    label: 'Integração',
    icon: <ClipboardList className="w-3.5 h-3.5" />,
    style: 'bg-sky-900/30 text-sky-300 border-sky-700/50',
  },
  security: {
    label: 'Segurança',
    icon: <Shield className="w-3.5 h-3.5" />,
    style: 'bg-red-900/30 text-red-300 border-red-700/50',
  },
  compliance: {
    label: 'Compliance',
    icon: <Scale className="w-3.5 h-3.5" />,
    style: 'bg-amber-900/30 text-amber-300 border-amber-700/50',
  },
  e2e: {
    label: 'E2E',
    icon: <CheckCircle2 className="w-3.5 h-3.5" />,
    style: 'bg-violet-900/30 text-violet-300 border-violet-700/50',
  },
}

const TYPE_ORDER: TestSpecType[] = ['unit', 'integration', 'security', 'compliance', 'e2e']

const STATUS_LABEL: Record<string, string> = {
  draft: 'Rascunho',
  approved: 'Aprovado',
  rejected: 'Rejeitado',
  stale: 'Desatualizado',
}

const STATUS_STYLE: Record<string, string> = {
  draft: 'bg-slate-700/40 text-slate-300',
  approved: 'bg-emerald-500/20 text-emerald-300',
  rejected: 'bg-red-500/20 text-red-300',
  stale: 'bg-amber-500/20 text-amber-300',
}

interface Props {
  projectId: string
}

export function TestSpecsSection({ projectId }: Props) {
  const { data: specs, isLoading } = useTestSpecs(projectId)
  const { data: summary } = useStaleSummary(projectId)
  const bulkLocal = useBulkRegenerateTestSpecs(projectId)
  const bulkGlobal = useBulkRegenerateGlobalSpecs(projectId)

  const [openSpecId, setOpenSpecId] = useState<string | null>(null)
  const [filter, setFilter] = useState<TestSpecType | 'all'>('all')

  const bySpecType: Record<TestSpecType, TestSpecListItem[]> = {
    unit: [], integration: [], security: [], compliance: [], e2e: [],
  }
  for (const s of specs || []) {
    if (s.spec_type in bySpecType) {
      bySpecType[s.spec_type as TestSpecType].push(s)
    }
  }

  const total = specs?.length ?? 0
  const visible = (filter === 'all' ? specs : bySpecType[filter]) || []

  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-slate-100 font-semibold text-base flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-violet-300" />
            Plano de Testes
          </h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Derivado do OCG + Roadmap + Ingestão. Clique em qualquer item pra ver o conteúdo completo e como foi criado.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => bulkLocal.mutate(['unit', 'integration'])}
            disabled={bulkLocal.isPending}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-slate-700 text-slate-300 hover:border-slate-500 hover:text-slate-100 disabled:opacity-50"
            title="Gera/regera planos unitários e de integração via Ollama local"
          >
            {bulkLocal.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Unit + Integration (Ollama)
          </button>
          <button
            type="button"
            onClick={() => bulkGlobal.mutate()}
            disabled={bulkGlobal.isPending}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded bg-violet-600/30 border border-violet-500/40 text-violet-200 hover:bg-violet-600/40 disabled:opacity-50"
            title="Gera/regera planos globais de Segurança e Compliance via Premium"
          >
            {bulkGlobal.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            Security + Compliance (Premium)
          </button>
        </div>
      </div>

      {/* Stale banner */}
      {summary?.needs_regeneration && (
        <div className="bg-amber-500/10 border border-amber-500/40 rounded p-3 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-[12px] text-amber-200 flex-1">
            <strong>
              {summary.test_specs.stale + summary.live_docs.stale} itens desatualizados
            </strong>{' '}
            — OCG evoluiu desde a última geração.
            {summary.current_ocg_version !== null && ` Versão atual: v${summary.current_ocg_version}.`}{' '}
            Clique em "Regenerar" pra alinhar.
          </div>
        </div>
      )}

      {/* Filtro por tipo */}
      {total > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wide text-slate-500 mr-1">
            Filtrar:
          </span>
          <button
            onClick={() => setFilter('all')}
            className={`text-xs px-2 py-0.5 rounded border ${
              filter === 'all'
                ? 'bg-violet-600/30 border-violet-500/60 text-violet-100'
                : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200'
            }`}
          >
            Todos ({total})
          </button>
          {TYPE_ORDER.map((t) => {
            const count = bySpecType[t].length
            if (count === 0) return null
            const active = filter === t
            const meta = TYPE_META[t]
            return (
              <button
                key={t}
                onClick={() => setFilter(active ? 'all' : t)}
                className={`text-xs px-2 py-0.5 rounded border flex items-center gap-1 ${
                  active ? meta.style : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                {meta.icon}
                {meta.label} ({count})
              </button>
            )
          })}
        </div>
      )}

      {/* Lista */}
      {isLoading && (
        <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin mr-2" />
          Carregando specs…
        </div>
      )}

      {!isLoading && total === 0 && (
        <div className="text-center py-10 text-sm text-slate-500 border border-dashed border-slate-800 rounded">
          <FileText className="w-8 h-8 mx-auto mb-2 opacity-40" />
          Nenhum plano de teste gerado ainda.
          <br />
          <span className="text-[11px]">
            Clique em "Unit + Integration (Ollama)" ou "Security + Compliance (Premium)" pra começar.
          </span>
        </div>
      )}

      {!isLoading && visible.length > 0 && (
        <div className="space-y-1.5">
          {visible.map((s) => {
            const meta = TYPE_META[s.spec_type as TestSpecType]
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setOpenSpecId(s.id)}
                className={`w-full text-left px-3 py-2 rounded border hover:ring-1 hover:ring-violet-500/50 transition-all ${
                  s.is_stale
                    ? 'border-amber-500/40 bg-amber-950/10'
                    : 'border-slate-800 bg-slate-950/30 hover:bg-slate-900/40'
                }`}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  {meta ? (
                    <span
                      className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded border ${meta.style}`}
                    >
                      {meta.icon}
                      {meta.label}
                    </span>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {s.spec_type}
                    </span>
                  )}
                  <span className="text-[11px] text-slate-300 truncate flex-1">
                    {s.module_id
                      ? `Módulo (${s.module_id.slice(0, 8)}…)`
                      : `Global do projeto`}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded ${
                      STATUS_STYLE[s.status] || 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    {STATUS_LABEL[s.status] || s.status}
                  </span>
                  {s.is_stale && (
                    <span
                      className="text-[10px] text-amber-300 flex items-center gap-1"
                      title={s.stale_reason || 'OCG mudou desde a geração'}
                    >
                      <AlertTriangle className="w-3 h-3" />
                      stale
                    </span>
                  )}
                  <span className="text-[10px] text-slate-500 whitespace-nowrap">
                    {s.content_chars.toLocaleString('pt-BR')} chars
                  </span>
                </div>
                {s.content_preview && (
                  <p className="text-[10px] text-slate-500 mt-1 truncate">
                    {s.content_preview}
                  </p>
                )}
              </button>
            )
          })}
        </div>
      )}

      {/* Modal */}
      {openSpecId && (
        <TestSpecModal
          projectId={projectId}
          specId={openSpecId}
          onClose={() => setOpenSpecId(null)}
        />
      )}
    </div>
  )
}
