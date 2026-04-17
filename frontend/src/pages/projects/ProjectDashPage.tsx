import { useState, useEffect } from 'react'
import { useParams, useOutletContext } from 'react-router-dom'
import { SetupChecklist } from '@/components/project/SetupChecklist'
import { useSetupStatus } from '@/hooks/useSetupStatus'
import { FileText, Code2, TestTube2, Cpu, Shield, Users, GitBranch, Key, Loader2, AlertTriangle } from 'lucide-react'
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts'
import { apiClient } from '@/lib/api'

// Papéis canônicos (GCA_CANONICAL_CONTRACT.md §4): Admin, GP, Dev, Tester, QA.
const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  gp: 'Gerente de Projeto',
  dev: 'Dev',
  tester: 'Tester',
  qa: 'QA Engineer',
}

const ROLE_COLORS: Record<string, string> = {
  admin: 'bg-violet-600/20 text-violet-300',
  gp: 'bg-emerald-500/20 text-emerald-300',
  dev: 'bg-cyan-500/20 text-cyan-300',
  tester: 'bg-orange-500/20 text-orange-300',
  qa: 'bg-amber-500/20 text-amber-300',
}

const PILLAR_NAMES: Record<string, string> = {
  P1: 'Negócio', P2: 'Compliance', P3: 'Escopo', P4: 'Performance',
  P5: 'Arquitetura', P6: 'Dados', P7: 'Segurança',
}

function MiniKPI({ label, value, sub, icon }: { label: string; value: string | number; sub: string; icon: React.ReactNode }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">{icon}<span className="text-slate-400 text-xs">{label}</span></div>
      <p className="text-xl font-semibold text-slate-100">{value}</p>
      <p className="text-slate-500 text-xs mt-0.5">{sub}</p>
    </div>
  )
}

export function ProjectDashPage() {
  const { id } = useParams<{ id: string }>()
  const context = useOutletContext<{ projectStatus?: string }>()
  const projectStatus = context?.projectStatus
  const { data: setupStatus } = useSetupStatus(id)
  const [loading, setLoading] = useState(true)
  const [ocg, setOcg] = useState<any>(null)
  const [members, setMembers] = useState<any[]>([])
  const [questionnaire, setQuestionnaire] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [billing, setBilling] = useState<any>(null)

  useEffect(() => {
    const load = async () => {
      if (!id) return
      try {
        const [ocgRes, membersRes, questRes, healthRes, billingRes] = await Promise.all([
          apiClient.get(`/projects/${id}/ocg`).catch(() => ({ data: {} })),
          apiClient.get(`/projects/${id}/members`).catch(() => ({ data: { members: [] } })),
          apiClient.get(`/projects/${id}/questionnaire`).catch(() => ({ data: {} })),
          apiClient.get(`/projects/${id}/ocg/health`).catch(() => ({ data: {} })),
          apiClient.get(`/projects/${id}/billing`).catch(() => ({ data: {} })),
        ])

        const ocgData = ocgRes.data?.ocg
        if (ocgData && ocgData.ocg_data) {
          setOcg({ ...ocgData, ...ocgData.ocg_data })
        } else {
          setOcg(ocgData || null)
        }
        setMembers(membersRes.data?.members || [])
        setQuestionnaire(questRes.data?.questionnaire || null)
        setHealth(healthRes.data || null)
        setBilling(billingRes.data || null)
      } catch { /* ignore */ }
      setLoading(false)
    }
    load()
  }, [id])

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>

  // Extrair scores dos pilares do OCG
  const pillarScores = ocg?.PILLAR_SCORES || {}
  const radarData = Object.entries(pillarScores).map(([key, val]: [string, any]) => {
    const shortKey = key.replace(/_.*/, '') // P1_Business -> P1
    return {
      subject: PILLAR_NAMES[shortKey] || shortKey,
      score: typeof val === 'object' ? (val.score ?? 0) : (val ?? 0),
      fullMark: 100,
    }
  })

  const overallScore = ocg?.overall_score ?? 0
  const ocgStatus = ocg?.status || ocg?.APPROVAL_STATUS?.status || 'Aguardando OCG'
  const stack = ocg?.STACK_RECOMMENDATION || {}
  const adherenceScore = questionnaire?.adherence_score ?? 0

  const statusLabel: Record<string, string> = {
    'READY': 'Aprovado',
    'APPROVED': 'Aprovado',
    'NEEDS_REVIEW': 'Em Revisão',
    'AT_RISK': 'Em Risco',
    'BLOCKED': 'Bloqueado',
  }
  const statusColor: Record<string, string> = {
    'READY': 'bg-emerald-500/20 text-emerald-300',
    'APPROVED': 'bg-emerald-500/20 text-emerald-300',
    'NEEDS_REVIEW': 'bg-amber-500/20 text-amber-300',
    'AT_RISK': 'bg-amber-500/20 text-amber-300',
    'BLOCKED': 'bg-red-500/20 text-red-300',
  }

  return (
    <div className="p-6 space-y-6">
      {/* Setup Checklist — visivel quando setup incompleto */}
      {setupStatus && !setupStatus.ready_to_activate && (
        <div className="mb-6">
          <SetupChecklist projectId={id!} status={setupStatus} />
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MiniKPI
          label="Score OCG"
          value={overallScore > 0 ? overallScore.toFixed(1) : '—'}
          sub={overallScore > 0 ? (statusLabel[ocgStatus] || ocgStatus) : 'Aguardando geração'}
          icon={<Shield className="w-4 h-4 text-violet-400" />}
        />
        <MiniKPI
          label="Aderência Questionário"
          value={adherenceScore > 0 ? `${adherenceScore}%` : '—'}
          sub={questionnaire ? (questionnaire.approved ? 'Aprovado' : questionnaire.status) : 'Sem questionário'}
          icon={<FileText className="w-4 h-4 text-blue-400" />}
        />
        <MiniKPI
          label="Equipe"
          value={members.length}
          sub={members.length === 1 ? '1 membro' : `${members.length} membros`}
          icon={<Users className="w-4 h-4 text-emerald-400" />}
        />
        <MiniKPI
          label="Pilares Avaliados"
          value={radarData.length > 0 ? `${radarData.length}/7` : '—'}
          sub={radarData.length > 0 ? 'Avaliação completa' : 'Aguardando OCG'}
          icon={<Cpu className="w-4 h-4 text-amber-400" />}
        />
      </div>

      {/* Context Health + Billing */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Saúde do Contexto OCG */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-violet-400" />
            Saúde do Contexto OCG
          </h3>
          {health?.health && Object.keys(health.health).length > 0 ? (
            <div className="space-y-3">
              {[
                { label: 'Profundidade', key: 'depth', format: (v: number) => `${Math.round(v * 100)}%` },
                { label: 'Confiança', key: 'confidence', format: (v: number) => `${Math.round(v * 100)}%` },
                { label: 'Qualidade', key: 'quality', format: (v: number) => `${Math.round(v * 100)}%` },
              ].map(item => {
                const val = health.health[item.key] ?? 0
                const numVal = typeof val === 'number' ? val : 0
                const pct = Math.round(numVal * 100)
                const color = pct >= 80 ? 'emerald' : pct >= 60 ? 'amber' : 'red'
                return (
                  <div key={item.key}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-slate-400 text-xs">{item.label}</span>
                      <span className={`text-xs font-semibold text-${color}-400`}>{item.format(numVal)}</span>
                    </div>
                    <div className="h-1.5 bg-slate-700 rounded-full">
                      <div className={`h-full rounded-full bg-${color}-500 transition-all`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                <span className="text-slate-500 text-xs">Versão OCG</span>
                <span className="text-slate-300 text-xs font-mono">v{health.version || 1}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 text-xs">Tipo de Mudança</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  health.change_type === 'EXPAND' ? 'bg-emerald-500/20 text-emerald-300' :
                  health.change_type === 'CONTRACT' ? 'bg-red-500/20 text-red-300' :
                  'bg-slate-700 text-slate-400'
                }`}>{health.change_type === 'EXPAND' ? 'Expandido' : health.change_type === 'CONTRACT' ? 'Contraído' : health.change_type || 'Inicial'}</span>
              </div>
            </div>
          ) : (
            <div className="text-center py-6">
              <p className="text-slate-500 text-sm italic">Aguardando ingestão de documentos</p>
              <p className="text-slate-600 text-xs mt-1">A saúde do contexto é calculada após a primeira atualização do OCG</p>
            </div>
          )}
        </div>

        {/* Billing IA */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-4 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-amber-400" />
            Consumo de IA do Projeto
          </h3>
          {billing && billing.total_calls > 0 ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center p-3 rounded-lg bg-slate-800/50">
                  <p className="text-lg font-bold text-emerald-400">${billing.total_cost_usd.toFixed(4)}</p>
                  <p className="text-slate-500 text-xs">Custo Total (USD)</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-slate-800/50">
                  <p className="text-lg font-bold text-blue-400">{(billing.total_tokens || 0).toLocaleString('pt-BR')}</p>
                  <p className="text-slate-500 text-xs">Tokens Totais</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-slate-800/50">
                  <p className="text-lg font-bold text-violet-400">{billing.total_calls}</p>
                  <p className="text-slate-500 text-xs">Chamadas IA</p>
                </div>
              </div>

              {billing.by_operation?.length > 0 && (
                <div>
                  <p className="text-slate-500 text-xs mb-2">Por Operação</p>
                  <div className="space-y-1.5">
                    {billing.by_operation.map((op: any) => (
                      <div key={op.operation} className="flex items-center justify-between">
                        <span className="text-slate-400 text-xs">{op.operation}</span>
                        <span className="text-slate-300 text-xs">${op.cost_usd.toFixed(4)} ({op.calls} chamadas)</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {billing.by_provider?.length > 0 && (
                <div>
                  <p className="text-slate-500 text-xs mb-2">Por Provedor</p>
                  <div className="space-y-1.5">
                    {billing.by_provider.map((prov: any) => (
                      <div key={prov.provider} className="flex items-center justify-between">
                        <span className="text-slate-400 text-xs capitalize">{prov.provider}</span>
                        <span className="text-slate-300 text-xs">${prov.cost_usd.toFixed(4)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-6">
              <p className="text-slate-500 text-sm italic">Nenhuma chamada de IA registrada</p>
              <p className="text-slate-600 text-xs mt-1">O billing é registrado automaticamente a cada interação com a IA</p>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Radar Gatekeeper */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-slate-200 text-sm font-semibold flex items-center gap-2">
              <Shield className="w-4 h-4 text-violet-400" />
              Gatekeeper — 7 Pilares
            </h3>
            {overallScore > 0 && (
              <span className={`text-xs px-2 py-0.5 rounded-full ${statusColor[ocgStatus] || 'bg-slate-700 text-slate-400'}`}>
                {statusLabel[ocgStatus] || ocgStatus}
              </span>
            )}
          </div>
          {radarData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <RadarChart data={radarData} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
                  <PolarGrid stroke="#334155" />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Radar name="Score" dataKey="score" stroke="#7c3aed" fill="#7c3aed" fillOpacity={0.25} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0', fontSize: '12px' }} />
                </RadarChart>
              </ResponsiveContainer>
              <div className="flex items-center justify-center gap-2 mt-2">
                <span className="text-slate-500 text-xs">Score composto:</span>
                <span className={`text-sm font-bold ${overallScore >= 80 ? 'text-emerald-400' : overallScore >= 60 ? 'text-amber-400' : 'text-red-400'}`}>
                  {overallScore.toFixed(1)}/100
                </span>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-40 text-slate-500">
              <AlertTriangle className="w-8 h-8 mb-2 text-slate-600" />
              <p className="text-sm">Aguardando geração do OCG</p>
            </div>
          )}
        </div>

        {/* Stack & Configuração */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-3 flex items-center gap-2">
            <Code2 className="w-4 h-4 text-slate-400" />
            Stack Recomendada
          </h3>
          {Object.keys(stack).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(stack).map(([layer, config]: [string, any]) => (
                <div key={layer} className="p-2 rounded-lg bg-slate-800/40">
                  <span className="text-violet-400 text-xs font-medium capitalize">{layer}</span>
                  {typeof config === 'object' && config !== null ? (
                    <div className="mt-1 space-y-0.5">
                      {Object.entries(config).filter(([k]) => k !== 'rationale').map(([k, v]) => (
                        <div key={k} className="flex justify-between">
                          <span className="text-slate-500 text-xs">{k}</span>
                          <span className="text-slate-300 text-xs">{String(v)}</span>
                        </div>
                      ))}
                      {config.rationale && (
                        <p className="text-slate-500 text-[10px] mt-1 italic">{String(config.rationale).slice(0, 100)}</p>
                      )}
                    </div>
                  ) : (
                    <p className="text-slate-300 text-xs">{String(config)}</p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-sm py-4 text-center italic">Aguardando geração do OCG</p>
          )}
        </div>

        {/* Equipe do Projeto */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-3 flex items-center gap-2">
            <Users className="w-4 h-4 text-slate-400" />
            Equipe ({members.length})
          </h3>
          <div className="space-y-2.5">
            {members.map((member, i) => (
              <div key={i} className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-violet-700/50 flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">
                  {(member.full_name || member.email || '?').charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0 overflow-hidden">
                  <p className="text-slate-200 text-xs truncate">{member.full_name || member.email}</p>
                  <p className="text-slate-500 text-[10px] truncate">{member.email}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded flex-shrink-0 whitespace-nowrap ${ROLE_COLORS[member.role] || 'bg-slate-700 text-slate-400'}`}>
                  {ROLE_LABELS[member.role] || member.role}
                </span>
              </div>
            ))}
            {members.length === 0 && <p className="text-slate-500 text-xs italic">Nenhum membro na equipe.</p>}
          </div>
        </div>
      </div>

      {/* Scores por Pilar (detalhado) */}
      {radarData.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-4">Distribuição de Scores por Pilar</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {Object.entries(pillarScores).map(([key, val]: [string, any]) => {
              const shortKey = key.replace(/_.*/, '')
              const score = typeof val === 'object' ? (val.score ?? 0) : (val ?? 0)
              const color = score >= 80 ? 'emerald' : score >= 60 ? 'amber' : 'red'
              return (
                <div key={key} className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-slate-300 text-xs font-medium">{PILLAR_NAMES[shortKey] || key}</span>
                    <span className={`text-xs font-bold text-${color}-400`}>{score}</span>
                  </div>
                  <div className="h-1.5 bg-slate-700 rounded-full">
                    <div className={`h-full rounded-full bg-${color}-500`} style={{ width: `${Math.min(100, score)}%` }} />
                  </div>
                  {typeof val === 'object' && val.adherence_level && (
                    <p className="text-slate-500 text-[10px] mt-1">{val.adherence_level}</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
