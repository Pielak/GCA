import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  Activity, AlertCircle, Brain, DollarSign, Loader2, RefreshCw, Zap,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

interface AIUsageRow {
  provider: string
  operation: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

interface ProjectDashboard {
  generated_at: string
  window_hours: number
  scope: 'project'
  project_id: string
  ai_usage: { since: string; rows: AIUsageRow[] }
  audit: { since: string; events: { event_type: string; count: number }[] }
}

const WINDOWS = [
  { label: '24h', value: 24 },
  { label: '7 dias', value: 168 },
  { label: '30 dias', value: 720 },
]

function formatUSD(v: number): string {
  return `$${v.toFixed(4)}`
}

export function ProjectMetricsPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [data, setData] = useState<ProjectDashboard | null>(null)
  const [hours, setHours] = useState(168)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const res = await apiClient.get(`/projects/${projectId}/metrics/dashboard?hours=${hours}`)
      setData(res.data)
      setError(null)
    } catch (e: unknown) {
      setError(getErrorMessage(e) || 'Erro ao carregar métricas do projeto.')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [projectId, hours])

  useEffect(() => { load() }, [load])

  const totalCalls = (data?.ai_usage?.rows || []).reduce((s, r) => s + r.calls, 0)
  const totalTokensIn = (data?.ai_usage?.rows || []).reduce((s, r) => s + r.tokens_in, 0)
  const totalTokensOut = (data?.ai_usage?.rows || []).reduce((s, r) => s + r.tokens_out, 0)
  const totalCost = (data?.ai_usage?.rows || []).reduce((s, r) => s + r.cost_usd, 0)

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-violet-400" />
            <h1 className="text-xl font-semibold text-slate-100">Métricas do projeto</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Uso de IA e eventos de auditoria deste projeto. Janela ajustável.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg overflow-hidden border border-slate-700">
            {WINDOWS.map(w => (
              <button
                key={w.value}
                onClick={() => setHours(w.value)}
                className={`text-xs px-3 py-1.5 ${
                  hours === w.value
                    ? 'bg-violet-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Atualizar
          </button>
        </div>
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
      ) : data ? (
        <>
          {/* Cards resumo */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SummaryCard icon={Brain} label="Chamadas LLM" value={totalCalls.toLocaleString('pt-BR')} color="text-violet-400" />
            <SummaryCard icon={Zap} label="Tokens in" value={totalTokensIn.toLocaleString('pt-BR')} color="text-cyan-400" />
            <SummaryCard icon={Zap} label="Tokens out" value={totalTokensOut.toLocaleString('pt-BR')} color="text-emerald-400" />
            <SummaryCard icon={DollarSign} label="Custo estimado" value={formatUSD(totalCost)} color="text-amber-400" />
          </div>

          {/* Uso de IA detalhado */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-xl">
            <div className="px-4 py-2.5 border-b border-slate-800 flex items-center gap-2">
              <Brain className="w-4 h-4 text-slate-400" />
              <h2 className="text-slate-200 text-sm font-medium">Uso de IA — {data.ai_usage.rows.length} combinações provider × operation</h2>
            </div>
            {data.ai_usage.rows.length === 0 ? (
              <p className="text-slate-500 text-sm p-4 italic">Sem chamadas de IA neste projeto na janela selecionada.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-slate-500 text-xs uppercase tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="text-left py-2 px-4">Provider</th>
                    <th className="text-left py-2 px-4">Operação</th>
                    <th className="text-right py-2 px-4">Chamadas</th>
                    <th className="text-right py-2 px-4">Tokens in</th>
                    <th className="text-right py-2 px-4">Tokens out</th>
                    <th className="text-right py-2 px-4">Custo</th>
                  </tr>
                </thead>
                <tbody>
                  {data.ai_usage.rows.map((r, i) => (
                    <tr key={i} className="border-b border-slate-800/50 last:border-b-0 hover:bg-slate-800/30">
                      <td className="py-2 px-4 text-slate-300">{r.provider}</td>
                      <td className="py-2 px-4 text-slate-400">{r.operation}</td>
                      <td className="py-2 px-4 text-right tabular-nums text-slate-200">{r.calls}</td>
                      <td className="py-2 px-4 text-right tabular-nums text-slate-400">{r.tokens_in.toLocaleString('pt-BR')}</td>
                      <td className="py-2 px-4 text-right tabular-nums text-slate-400">{r.tokens_out.toLocaleString('pt-BR')}</td>
                      <td className="py-2 px-4 text-right tabular-nums text-amber-300">{formatUSD(r.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Audit events */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-xl">
            <div className="px-4 py-2.5 border-b border-slate-800">
              <h2 className="text-slate-200 text-sm font-medium">Eventos de auditoria</h2>
              <p className="text-slate-500 text-[11px] mt-0.5">
                Apenas eventos cujo recurso direto é este projeto (limitação atual).
              </p>
            </div>
            {data.audit.events.length === 0 ? (
              <p className="text-slate-500 text-sm p-4 italic">Sem eventos diretos sobre o projeto na janela.</p>
            ) : (
              <ul className="divide-y divide-slate-800">
                {data.audit.events.map((e, i) => (
                  <li key={i} className="flex items-center justify-between px-4 py-2 text-sm">
                    <code className="text-slate-300 text-xs">{e.event_type}</code>
                    <span className="text-slate-400 tabular-nums">{e.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : null}
    </div>
  )
}

function SummaryCard({
  icon: Icon, label, value, color,
}: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; color: string }) {
  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-3">
      <div className="flex items-center gap-1.5 text-slate-500 text-[11px] uppercase tracking-wider">
        <Icon className={`w-3.5 h-3.5 ${color}`} /> {label}
      </div>
      <div className="text-slate-100 text-2xl font-semibold mt-1.5 tabular-nums">{value}</div>
    </div>
  )
}
