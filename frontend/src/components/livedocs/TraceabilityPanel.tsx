import { useQuery } from '@tanstack/react-query'
import {
  Network, Loader2, CheckCircle2, AlertCircle, FileCode, FlaskConical,
} from 'lucide-react'
import { apiClient } from '@/lib/api'

// MVP 19 Fase 19.4 — Matriz de rastreabilidade (read-only).
//
// Alimenta a Seção 4 do ERS ao regenerar; aqui o GP vê o estado ao vivo
// sem precisar commitar o docs/ERS.md.

type Category = 'functional' | 'non_functional' | 'business_rule' | null

interface TestSpecRef {
  id: string
  spec_type: string
  status: string
}

interface GeneratedModuleRef {
  id: string
  name: string
  status: string
  git_source_path: string | null
  git_unit_test_path: string | null
  git_integration_test_path: string | null
  git_uat_test_path: string | null
  git_docs_path: string | null
  generated_at: string | null
}

interface Row {
  requirement_id: string
  module_candidate_id: string
  name: string
  category: Category
  priority: string
  status: string
  test_specs: TestSpecRef[]
  generated_modules: GeneratedModuleRef[]
}

interface Summary {
  total_requirements: number
  by_category: {
    functional: number
    non_functional: number
    business_rule: number
    uncategorized: number
  }
  with_test_spec: number
  with_generated_code: number
  fully_traced: number
}

interface MatrixResponse {
  rows: Row[]
  summary: Summary
}

interface Props {
  projectId: string
}

const CATEGORY_META: Record<string, { label: string; chip: string }> = {
  functional: {
    label: 'RF',
    chip: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50',
  },
  non_functional: {
    label: 'RNF',
    chip: 'bg-sky-900/30 text-sky-300 border-sky-700/50',
  },
  business_rule: {
    label: 'BR',
    chip: 'bg-violet-900/30 text-violet-300 border-violet-700/50',
  },
  uncategorized: {
    label: '—',
    chip: 'bg-slate-800/40 text-slate-400 border-slate-700/50',
  },
}

export function TraceabilityPanel({ projectId }: Props) {
  const { data, isLoading } = useQuery<MatrixResponse>({
    queryKey: ['traceability-matrix', projectId],
    queryFn: async () => {
      const res = await apiClient.get<MatrixResponse>(
        `/projects/${projectId}/traceability`,
      )
      return res.data
    },
  })

  return (
    <div className="space-y-3 bg-slate-950/30 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center gap-2">
        <Network className="w-4 h-4 text-violet-400" />
        <h3 className="text-sm font-semibold text-slate-200">
          Matriz de Rastreabilidade
        </h3>
        <span className="text-[11px] text-slate-500">
          (requisito × test spec × código gerado)
        </span>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-6 text-slate-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin mr-2" />
          Carregando matriz…
        </div>
      )}

      {!isLoading && data && data.rows.length === 0 && (
        <div className="text-center py-6 text-slate-500 text-[12px]">
          Nenhum requisito registrado ainda. Aprove candidatos do Arguidor
          ou popule módulos no backlog para a matriz aparecer aqui.
        </div>
      )}

      {!isLoading && data && data.rows.length > 0 && (
        <>
          <SummaryBar summary={data.summary} />

          <div className="overflow-x-auto">
            <table className="w-full text-[11px] text-left">
              <thead className="text-slate-500 uppercase tracking-wide">
                <tr className="border-b border-slate-800">
                  <th className="py-2 pr-3">ID</th>
                  <th className="py-2 pr-3">Requisito</th>
                  <th className="py-2 pr-3">Cat.</th>
                  <th className="py-2 pr-3">Test Specs</th>
                  <th className="py-2 pr-3">Código gerado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {data.rows.map((row) => (
                  <MatrixRow key={row.module_candidate_id} row={row} />
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[10px] text-slate-500 pt-1">
            A mesma consolidação é incluída na Seção 4 do ERS
            (<code>docs/ERS.md</code>) na próxima regeneração.
          </p>
        </>
      )}
    </div>
  )
}

function SummaryBar({ summary }: { summary: Summary }) {
  const { total_requirements, by_category, with_test_spec, with_generated_code, fully_traced } = summary
  return (
    <div className="flex flex-wrap gap-2 text-[11px]">
      <Pill label="Total" value={total_requirements} />
      <Pill label="RF" value={by_category.functional} chip={CATEGORY_META.functional.chip} />
      <Pill label="RNF" value={by_category.non_functional} chip={CATEGORY_META.non_functional.chip} />
      <Pill label="BR" value={by_category.business_rule} chip={CATEGORY_META.business_rule.chip} />
      <Pill label="Pend." value={by_category.uncategorized} />
      <Pill label="Com spec" value={with_test_spec} icon={<FlaskConical className="w-3 h-3" />} />
      <Pill label="Com código" value={with_generated_code} icon={<FileCode className="w-3 h-3" />} />
      <Pill
        label="Rastreado"
        value={fully_traced}
        icon={<CheckCircle2 className="w-3 h-3" />}
        chip="bg-emerald-900/30 text-emerald-300 border-emerald-700/50"
      />
    </div>
  )
}

function Pill({
  label, value, icon, chip,
}: { label: string; value: number; icon?: React.ReactNode; chip?: string }) {
  const theme = chip ?? 'bg-slate-900/40 text-slate-300 border-slate-700/60'
  return (
    <span className={`flex items-center gap-1 px-2 py-0.5 rounded border ${theme}`}>
      {icon}
      <span className="text-slate-500">{label}:</span>
      <strong>{value}</strong>
    </span>
  )
}

function MatrixRow({ row }: { row: Row }) {
  const catKey = row.category ?? 'uncategorized'
  const catMeta = CATEGORY_META[catKey] ?? CATEGORY_META.uncategorized

  return (
    <tr className="align-top">
      <td className="py-2 pr-3">
        <code className="text-violet-300 font-semibold">{row.requirement_id}</code>
      </td>
      <td className="py-2 pr-3 max-w-xs">
        <span className="text-slate-200">{row.name}</span>
        <div className="text-[10px] text-slate-500 mt-0.5">
          prio <code>{row.priority}</code> · status <code>{row.status}</code>
        </div>
      </td>
      <td className="py-2 pr-3">
        <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] ${catMeta.chip}`}>
          {catMeta.label}
        </span>
      </td>
      <td className="py-2 pr-3">
        {row.test_specs.length === 0 ? (
          <MissingChip label="sem spec" />
        ) : (
          <div className="flex flex-col gap-0.5">
            {row.test_specs.map((s) => (
              <span key={s.id} className="flex items-center gap-1 text-slate-300">
                <FlaskConical className="w-3 h-3 text-emerald-400/70" />
                <code className="text-[10px]">{s.spec_type}</code>
                <span className="text-[10px] text-slate-500">({s.status})</span>
              </span>
            ))}
          </div>
        )}
      </td>
      <td className="py-2 pr-3">
        {row.generated_modules.length === 0 ? (
          <MissingChip label="sem código" />
        ) : (
          <div className="flex flex-col gap-0.5">
            {row.generated_modules.map((g) => (
              <span
                key={g.id}
                className="flex items-center gap-1 text-slate-300 truncate max-w-[28ch]"
                title={g.git_source_path || g.name}
              >
                <FileCode className="w-3 h-3 text-sky-400/70 flex-shrink-0" />
                <code className="text-[10px] truncate">
                  {g.git_source_path || g.name}
                </code>
                <span className="text-[10px] text-slate-500">({g.status})</span>
              </span>
            ))}
          </div>
        )}
      </td>
    </tr>
  )
}

function MissingChip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-amber-300/80">
      <AlertCircle className="w-3 h-3" />
      {label}
    </span>
  )
}
