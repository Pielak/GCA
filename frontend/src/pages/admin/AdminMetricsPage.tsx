import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Activity,
  AlertCircle,
  Brain,
  DollarSign,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Users as UsersIcon,
  Zap,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

// Tipos espelham o retorno de GET /api/v1/metrics/dashboard (DT-060).
interface AIUsageRow {
  provider: string
  operation: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

interface MetricsDashboard {
  generated_at: string
  window_hours: number
  ai_usage: { since: string; rows: AIUsageRow[] }
  audit: { since: string; events: { event_type: string; count: number }[] }
  projects: { by_status: { status: string; count: number }[] }
  users: { active: number; admin_active: number; inactive: number }
}

const WINDOW_OPTIONS = [
  { hours: 1, label: '1h' },
  { hours: 24, label: '24h' },
  { hours: 168, label: '7d' },
  { hours: 720, label: '30d' },
]

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k'
  return n.toLocaleString('pt-BR')
}

function formatCost(usd: number): string {
  if (usd === 0) return '$0'
  if (usd < 0.01) return '<$0.01'
  return '$' + usd.toFixed(2)
}

interface PerProjectRow {
  project_id: string | null
  project_name: string
  project_slug: string | null
  project_status: string | null
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

interface PerProjectResponse {
  generated_at: string
  window_hours: number
  since: string
  items: PerProjectRow[]
}

export function AdminMetricsPage() {
  const [hours, setHours] = useState(24)
  const [data, setData] = useState<MetricsDashboard | null>(null)
  const [perProject, setPerProject] = useState<PerProjectResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [globalRes, perProjectRes] = await Promise.all([
        apiClient.get(`/metrics/dashboard?hours=${hours}`),
        apiClient.get(`/metrics/per-project?hours=${hours}`),
      ])
      setData(globalRes.data)
      setPerProject(perProjectRes.data)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string }
      setError(getErrorMessage(e))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [hours])

  useEffect(() => { load() }, [load])

  // Totais derivados
  const totals = useMemo(() => {
    if (!data) return { calls: 0, tokens: 0, cost: 0 }
    return data.ai_usage.rows.reduce(
      (acc, r) => ({
        calls: acc.calls + r.calls,
        tokens: acc.tokens + r.tokens_in + r.tokens_out,
        cost: acc.cost + r.cost_usd,
      }),
      { calls: 0, tokens: 0, cost: 0 },
    )
  }, [data])

  if (loading && !data) {
    return (
      <div className="p-6 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" />
        Carregando métricas...
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-violet-400" />
            <h1 className="text-xl font-semibold text-slate-100">Métricas Operacionais</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Agregação de uso de IA, audit e atividade.{' '}
            {data && (
              <span className="text-slate-600 text-xs">
                Atualizado em {new Date(data.generated_at).toLocaleString('pt-BR')}
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Window selector */}
          <div className="flex bg-slate-800/50 border border-slate-700/50 rounded-lg p-0.5">
            {WINDOW_OPTIONS.map(opt => (
              <button
                key={opt.hours}
                onClick={() => setHours(opt.hours)}
                className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                  hours === opt.hours
                    ? 'bg-violet-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <button
            onClick={() => { setRefreshing(true); load() }}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg transition-colors disabled:opacity-50"
          >
            {refreshing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Atualizar
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-950/30 border border-red-900/50 rounded-lg text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {data && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard
              icon={<Brain className="w-4 h-4 text-violet-400" />}
              label="Chamadas LLM"
              value={formatNumber(totals.calls)}
              hint={`${data.ai_usage.rows.length} combinações provider×operation`}
            />
            <KpiCard
              icon={<Zap className="w-4 h-4 text-amber-400" />}
              label="Tokens consumidos"
              value={formatNumber(totals.tokens)}
              hint="entrada + saída"
            />
            <KpiCard
              icon={<DollarSign className="w-4 h-4 text-emerald-400" />}
              label="Custo agregado"
              value={formatCost(totals.cost)}
              hint="USD na janela"
            />
            <KpiCard
              icon={<UsersIcon className="w-4 h-4 text-cyan-400" />}
              label="Usuários ativos"
              value={data.users.active.toString()}
              hint={`${data.users.admin_active} admin · ${data.users.inactive} inativos`}
            />
          </div>

          {/* AI usage por (provider × operation) */}
          <Section title="Uso de IA por provider × operation" icon={<Brain className="w-4 h-4 text-violet-400" />}>
            {data.ai_usage.rows.length === 0 ? (
              <EmptyState message="Nenhuma chamada de LLM na janela." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-slate-500 text-xs uppercase tracking-wider border-b border-slate-800">
                    <tr>
                      <th className="text-left py-2 px-3 font-medium">Provider</th>
                      <th className="text-left py-2 px-3 font-medium">Operation</th>
                      <th className="text-right py-2 px-3 font-medium">Calls</th>
                      <th className="text-right py-2 px-3 font-medium">Tokens In</th>
                      <th className="text-right py-2 px-3 font-medium">Tokens Out</th>
                      <th className="text-right py-2 px-3 font-medium">Cost (USD)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.ai_usage.rows
                      .slice()
                      .sort((a, b) => b.cost_usd - a.cost_usd)
                      .map((r, i) => (
                        <tr
                          key={`${r.provider}-${r.operation}-${i}`}
                          className="border-b border-slate-800/50 hover:bg-slate-900/40"
                        >
                          <td className="py-2 px-3 text-slate-300">
                            <ProviderBadge provider={r.provider} />
                          </td>
                          <td className="py-2 px-3 text-slate-400 font-mono text-xs">{r.operation}</td>
                          <td className="py-2 px-3 text-right text-slate-300">{formatNumber(r.calls)}</td>
                          <td className="py-2 px-3 text-right text-slate-400">{formatNumber(r.tokens_in)}</td>
                          <td className="py-2 px-3 text-right text-slate-400">{formatNumber(r.tokens_out)}</td>
                          <td className="py-2 px-3 text-right text-emerald-400 font-mono">{formatCost(r.cost_usd)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* Uso de IA por PROJETO — breakdown compartimentalizado */}
          <Section
            title="Uso de IA por projeto"
            icon={<Brain className="w-4 h-4 text-violet-400" />}
            hint={perProject ? `${perProject.items.length} projeto(s) com consumo na janela` : undefined}
          >
            {!perProject || perProject.items.length === 0 ? (
              <EmptyState message="Nenhum projeto consumiu IA na janela." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-slate-500 text-xs uppercase tracking-wider border-b border-slate-800">
                    <tr>
                      <th className="text-left py-2 px-3 font-medium">Projeto</th>
                      <th className="text-left py-2 px-3 font-medium">Status</th>
                      <th className="text-right py-2 px-3 font-medium">Calls</th>
                      <th className="text-right py-2 px-3 font-medium">Tokens In</th>
                      <th className="text-right py-2 px-3 font-medium">Tokens Out</th>
                      <th className="text-right py-2 px-3 font-medium">Cost (USD)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {perProject.items.map((r) => {
                      const statusCls =
                        r.project_status === 'active'    ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' :
                        r.project_status === 'paused'    ? 'bg-amber-500/10 text-amber-300 border-amber-500/30' :
                        r.project_status === 'inactive'  ? 'bg-slate-500/10 text-slate-400 border-slate-500/30' :
                        'bg-slate-700/30 text-slate-500 border-slate-700/50'
                      return (
                        <tr
                          key={r.project_id || 'sem-vinculo'}
                          className="border-b border-slate-800/50 hover:bg-slate-900/40"
                        >
                          <td className="py-2 px-3">
                            <div className="text-slate-200">{r.project_name}</div>
                            {r.project_slug && (
                              <div className="text-[10px] text-slate-600 font-mono">{r.project_slug}</div>
                            )}
                          </td>
                          <td className="py-2 px-3">
                            {r.project_status ? (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded-md border ${statusCls}`}>
                                {r.project_status}
                              </span>
                            ) : (
                              <span className="text-slate-600 text-xs">—</span>
                            )}
                          </td>
                          <td className="py-2 px-3 text-right text-slate-300">{formatNumber(r.calls)}</td>
                          <td className="py-2 px-3 text-right text-slate-400">{formatNumber(r.tokens_in)}</td>
                          <td className="py-2 px-3 text-right text-slate-400">{formatNumber(r.tokens_out)}</td>
                          <td className="py-2 px-3 text-right text-emerald-400 font-mono">{formatCost(r.cost_usd)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* Eventos de audit */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Section title="Eventos de Auditoria (top 20)" icon={<ShieldCheck className="w-4 h-4 text-cyan-400" />}>
              {data.audit.events.length === 0 ? (
                <EmptyState message="Nenhum evento de audit na janela." />
              ) : (
                <div className="space-y-1.5">
                  {data.audit.events.map(ev => (
                    <div
                      key={ev.event_type}
                      className="flex items-center justify-between py-1.5 px-2 hover:bg-slate-900/40 rounded text-sm"
                    >
                      <span className="text-slate-300 font-mono text-xs">{ev.event_type}</span>
                      <span className="text-slate-400 tabular-nums">{formatNumber(ev.count)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            {/* Projetos por status */}
            <Section title="Projetos por status" icon={<Activity className="w-4 h-4 text-violet-400" />}>
              {data.projects.by_status.length === 0 ? (
                <EmptyState message="Nenhum projeto cadastrado." />
              ) : (
                <div className="space-y-1.5">
                  {data.projects.by_status.map(p => (
                    <div
                      key={p.status || 'unknown'}
                      className="flex items-center justify-between py-1.5 px-2 hover:bg-slate-900/40 rounded text-sm"
                    >
                      <span className="text-slate-300 capitalize">{p.status || 'unknown'}</span>
                      <span className="text-slate-400 tabular-nums">{p.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>

          <p className="text-xs text-slate-600">
            Endpoint: <code className="bg-slate-800/50 px-1.5 py-0.5 rounded">GET /api/v1/metrics/dashboard?hours={hours}</code>
            {' · '}
            Prometheus em <code className="bg-slate-800/50 px-1.5 py-0.5 rounded">/api/v1/metrics/prometheus</code>
          </p>
        </>
      )}
    </div>
  )
}

// ─── Componentes ───────────────────────────────────────────────────────────

function KpiCard({ icon, label, value, hint }: { icon: React.ReactNode; label: string; value: string; hint?: string }) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
        {icon}
        <span>{label}</span>
      </div>
      <p className="text-2xl font-semibold text-slate-100 tabular-nums">{value}</p>
      {hint && <p className="text-slate-500 text-xs mt-1">{hint}</p>}
    </div>
  )
}

function Section({ title, icon, hint, children }: { title: string; icon?: React.ReactNode; hint?: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h2 className="text-slate-200 text-sm font-semibold">{title}</h2>
        {hint && <span className="ml-2 text-slate-500 text-xs">{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-slate-600 text-sm py-6 text-center">{message}</div>
  )
}

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  openai: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  deepseek: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  grok: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  gemini: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  ollama: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  unknown: 'bg-slate-700/30 text-slate-400 border-slate-700/50',
}

function ProviderBadge({ provider }: { provider: string }) {
  const cls = PROVIDER_COLORS[provider] || PROVIDER_COLORS.unknown
  return (
    <span className={`inline-block text-[11px] px-2 py-0.5 rounded border ${cls}`}>
      {provider}
    </span>
  )
}
