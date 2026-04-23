import { useEffect, useState } from 'react'
import { Loader2, Save, AlertTriangle, CheckCircle2, Plus, Trash2 } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

// MVP 23 Fase 23.5 — editor canônico de RNF_CONTRACTS.
// As 4 categorias seguem schema do backend (app.services.rnf_contracts):
//   performance, security, compliance, availability

interface RnfContracts {
  performance?: {
    latency_p95_ms?: number | null
    throughput_rps?: number | null
    per_operation?: Array<{ op: string; budget_ms: number }>
  }
  security?: {
    required_cwe_protections?: string[]
    rate_limit_rpm_public?: number | null
    rate_limit_rpm_authenticated?: number | null
    sensitive_data_categories?: string[]
  }
  compliance?: Array<{
    regulation: string
    requirement_id: string
    enforcement?: 'runtime' | 'static' | 'both'
  }>
  availability?: {
    uptime_pct?: number | null
    rpo_minutes?: number | null
    rto_minutes?: number | null
  }
}

interface ValidationError {
  path: string
  message: string
}

interface Props {
  projectId: string
}

const CWE_SUGGESTIONS = ['CWE-79', 'CWE-89', 'CWE-200', 'CWE-287', 'CWE-352', 'CWE-798']
const REGULATION_SUGGESTIONS = [
  'LGPD', 'GDPR', 'SOX', 'PCI-DSS', 'HIPAA', 'BACEN', 'CVM', 'ANS', 'SOC2', 'ISO-27001',
]

export default function RnfContractsEditor({ projectId }: Props) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [version, setVersion] = useState<number>(0)
  const [contracts, setContracts] = useState<RnfContracts>({})
  const [errors, setErrors] = useState<ValidationError[]>([])
  const [successMsg, setSuccessMsg] = useState<string>('')
  const [loadError, setLoadError] = useState<string>('')

  const load = async () => {
    setLoading(true)
    setLoadError('')
    try {
      const r = await apiClient.get(`/projects/${projectId}/ocg/rnf-contracts`)
      setContracts(r.data.rnf_contracts || {})
      setVersion(r.data.ocg_version || 0)
    } catch (err: unknown) {
      setLoadError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [projectId])

  const save = async () => {
    setSaving(true)
    setErrors([])
    setSuccessMsg('')
    try {
      const body = { rnf_contracts: stripEmptyCategories(contracts) }
      const r = await apiClient.put(
        `/projects/${projectId}/ocg/rnf-contracts`, body,
      )
      const applied = r.data.applied
      setVersion(r.data.ocg_version)
      setSuccessMsg(
        applied
          ? `Contratos salvos. OCG agora está na v${r.data.ocg_version}.`
          : 'Nenhuma mudança detectada (payload idêntico ao atual).',
      )
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (detail?.errors && Array.isArray(detail.errors)) {
        setErrors(detail.errors)
      } else {
        setErrors([{ path: '$', message: getErrorMessage(err) }])
      }
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-400 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando contratos...
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="p-3 rounded-lg bg-red-900/20 border border-red-800/40 text-red-300 text-sm">
        Falha ao carregar: {loadError}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-slate-300 text-sm">
            Contratos não-funcionais obrigatórios. Os valores aqui viram
            instruções duras no prompt do CodeGen, cenários de teste obrigatórios
            e checks estáticos pós-geração.
          </p>
          <p className="text-slate-500 text-xs mt-1">
            OCG atual: v{version} · qualquer mudança bumpa a versão.
          </p>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/20 border border-violet-600/40 text-violet-200 text-sm hover:bg-violet-600/30 disabled:opacity-40"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          Salvar contrato
        </button>
      </div>

      {errors.length > 0 && (
        <div className="p-3 rounded-lg bg-red-900/20 border border-red-800/40 text-red-300 text-sm space-y-1">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="w-4 h-4" /> Payload inválido
          </div>
          {errors.map((e, i) => (
            <div key={i} className="text-xs font-mono">
              <span className="text-red-400">{e.path}</span>: {e.message}
            </div>
          ))}
        </div>
      )}

      {successMsg && (
        <div className="p-3 rounded-lg bg-emerald-900/20 border border-emerald-800/40 text-emerald-300 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" /> {successMsg}
        </div>
      )}

      <PerformanceSection
        value={contracts.performance || {}}
        onChange={(v) => setContracts({ ...contracts, performance: v })}
      />
      <SecuritySection
        value={contracts.security || {}}
        onChange={(v) => setContracts({ ...contracts, security: v })}
      />
      <ComplianceSection
        value={contracts.compliance || []}
        onChange={(v) => setContracts({ ...contracts, compliance: v })}
      />
      <AvailabilitySection
        value={contracts.availability || {}}
        onChange={(v) => setContracts({ ...contracts, availability: v })}
      />
    </div>
  )
}

// Remove categorias totalmente vazias para o backend aceitar como "não
// declarado" em vez de "declarado vazio". Mantém simetria com o de/serializer.
function stripEmptyCategories(c: RnfContracts): RnfContracts {
  const out: RnfContracts = {}
  if (c.performance && !isEmpty(c.performance)) out.performance = c.performance
  if (c.security && !isEmpty(c.security)) out.security = c.security
  if (c.compliance && c.compliance.length > 0) out.compliance = c.compliance
  if (c.availability && !isEmpty(c.availability)) out.availability = c.availability
  return out
}

function isEmpty(obj: Record<string, any>): boolean {
  return Object.values(obj).every((v) =>
    v === null || v === undefined || v === '' ||
    (Array.isArray(v) && v.length === 0),
  )
}

function Section({ title, subtitle, children }: {
  title: string; subtitle: string; children: React.ReactNode
}) {
  return (
    <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-800">
      <p className="text-slate-200 text-sm font-semibold mb-1">{title}</p>
      <p className="text-slate-500 text-xs mb-3">{subtitle}</p>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function NumberInput({ label, value, onChange, placeholder }: {
  label: string; value: number | null | undefined;
  onChange: (v: number | null) => void; placeholder?: string
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-slate-400 w-48 flex-shrink-0">{label}</span>
      <input
        type="number"
        value={value ?? ''}
        placeholder={placeholder}
        onChange={(e) => {
          const v = e.target.value
          onChange(v === '' ? null : Number(v))
        }}
        className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
      />
    </label>
  )
}

function PerformanceSection({ value, onChange }: {
  value: NonNullable<RnfContracts['performance']>
  onChange: (v: RnfContracts['performance']) => void
}) {
  const perOps = value.per_operation || []
  return (
    <Section
      title="Performance"
      subtitle="Latência máxima, throughput esperado e budgets por operação."
    >
      <NumberInput
        label="Latência P95 (ms)"
        value={value.latency_p95_ms}
        onChange={(v) => onChange({ ...value, latency_p95_ms: v })}
        placeholder="ex: 300"
      />
      <NumberInput
        label="Throughput sustentado (req/s)"
        value={value.throughput_rps}
        onChange={(v) => onChange({ ...value, throughput_rps: v })}
        placeholder="ex: 200"
      />
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-slate-400 text-sm">Budgets por operação</p>
          <button
            onClick={() => onChange({
              ...value, per_operation: [...perOps, { op: '', budget_ms: 0 }],
            })}
            className="flex items-center gap-1 text-xs text-violet-300 hover:text-violet-200"
          >
            <Plus className="w-3 h-3" /> Adicionar
          </button>
        </div>
        {perOps.map((po, i) => (
          <div key={i} className="flex items-center gap-2 mb-2">
            <input
              type="text"
              value={po.op}
              placeholder="GET /api/users"
              onChange={(e) => {
                const copy = [...perOps]
                copy[i] = { ...po, op: e.target.value }
                onChange({ ...value, per_operation: copy })
              }}
              className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
            />
            <input
              type="number"
              value={po.budget_ms}
              onChange={(e) => {
                const copy = [...perOps]
                copy[i] = { ...po, budget_ms: Number(e.target.value || 0) }
                onChange({ ...value, per_operation: copy })
              }}
              className="w-28 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
              placeholder="ms"
            />
            <button
              onClick={() => onChange({
                ...value,
                per_operation: perOps.filter((_, j) => j !== i),
              })}
              className="text-red-400 hover:text-red-300"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </Section>
  )
}

function SecuritySection({ value, onChange }: {
  value: NonNullable<RnfContracts['security']>
  onChange: (v: RnfContracts['security']) => void
}) {
  const cwes = value.required_cwe_protections || []
  const sensitives = value.sensitive_data_categories || []
  return (
    <Section
      title="Segurança"
      subtitle="CWEs obrigatórios, rate limits e categorias de dado sensível."
    >
      <NumberInput
        label="Rate limit público (req/min)"
        value={value.rate_limit_rpm_public}
        onChange={(v) => onChange({ ...value, rate_limit_rpm_public: v })}
        placeholder="ex: 60"
      />
      <NumberInput
        label="Rate limit autenticado (req/min)"
        value={value.rate_limit_rpm_authenticated}
        onChange={(v) => onChange({ ...value, rate_limit_rpm_authenticated: v })}
        placeholder="ex: 300"
      />
      <TagListInput
        label="Proteções CWE obrigatórias"
        suggestions={CWE_SUGGESTIONS}
        value={cwes}
        onChange={(v) => onChange({ ...value, required_cwe_protections: v })}
      />
      <TagListInput
        label="Dados sensíveis (nunca logar)"
        suggestions={['password', 'token', 'cpf', 'cnpj', 'credit_card', 'ssn']}
        value={sensitives}
        onChange={(v) => onChange({ ...value, sensitive_data_categories: v })}
      />
    </Section>
  )
}

function TagListInput({ label, suggestions, value, onChange }: {
  label: string; suggestions: string[]; value: string[]; onChange: (v: string[]) => void
}) {
  const [draft, setDraft] = useState('')
  const add = (v: string) => {
    const clean = v.trim()
    if (!clean || value.includes(clean)) return
    onChange([...value, clean])
    setDraft('')
  }
  return (
    <div>
      <p className="text-slate-400 text-sm mb-1">{label}</p>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {value.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-violet-900/30 border border-violet-800/40 text-violet-200 text-xs">
            {v}
            <button onClick={() => onChange(value.filter((x) => x !== v))} className="text-violet-400 hover:text-violet-200">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(draft) } }}
          placeholder="digite e Enter"
          className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
        />
        <button onClick={() => add(draft)} className="px-2 py-1 text-xs rounded bg-slate-700 text-slate-200 hover:bg-slate-600">
          Adicionar
        </button>
      </div>
      {suggestions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {suggestions.filter((s) => !value.includes(s)).map((s) => (
            <button
              key={s}
              onClick={() => add(s)}
              className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700 text-slate-500 hover:text-slate-200 hover:border-slate-500"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ComplianceSection({ value, onChange }: {
  value: NonNullable<RnfContracts['compliance']>
  onChange: (v: RnfContracts['compliance']) => void
}) {
  return (
    <Section
      title="Compliance"
      subtitle="Regulações e requisitos obrigatórios (runtime/static/both)."
    >
      {value.map((item, i) => (
        <div key={i} className="flex items-center gap-2">
          <select
            value={item.regulation}
            onChange={(e) => {
              const copy = [...value]
              copy[i] = { ...item, regulation: e.target.value }
              onChange(copy)
            }}
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
          >
            <option value="">—</option>
            {REGULATION_SUGGESTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input
            type="text"
            value={item.requirement_id}
            placeholder="requirement_id (ex: Art. 46)"
            onChange={(e) => {
              const copy = [...value]
              copy[i] = { ...item, requirement_id: e.target.value }
              onChange(copy)
            }}
            className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
          />
          <select
            value={item.enforcement || 'both'}
            onChange={(e) => {
              const copy = [...value]
              copy[i] = { ...item, enforcement: e.target.value as any }
              onChange(copy)
            }}
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-sm"
          >
            <option value="runtime">runtime</option>
            <option value="static">static</option>
            <option value="both">both</option>
          </select>
          <button
            onClick={() => onChange(value.filter((_, j) => j !== i))}
            className="text-red-400 hover:text-red-300"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ))}
      <button
        onClick={() => onChange([...value, { regulation: 'LGPD', requirement_id: '', enforcement: 'both' }])}
        className="flex items-center gap-1 text-xs text-violet-300 hover:text-violet-200"
      >
        <Plus className="w-3 h-3" /> Adicionar requisito
      </button>
    </Section>
  )
}

function AvailabilitySection({ value, onChange }: {
  value: NonNullable<RnfContracts['availability']>
  onChange: (v: RnfContracts['availability']) => void
}) {
  return (
    <Section
      title="Disponibilidade"
      subtitle="SLA de uptime, RPO e RTO canônicos."
    >
      <NumberInput
        label="Uptime (%)"
        value={value.uptime_pct}
        onChange={(v) => onChange({ ...value, uptime_pct: v })}
        placeholder="ex: 99.9"
      />
      <NumberInput
        label="RPO (minutos)"
        value={value.rpo_minutes}
        onChange={(v) => onChange({ ...value, rpo_minutes: v })}
        placeholder="ex: 15"
      />
      <NumberInput
        label="RTO (minutos)"
        value={value.rto_minutes}
        onChange={(v) => onChange({ ...value, rto_minutes: v })}
        placeholder="ex: 60"
      />
    </Section>
  )
}
