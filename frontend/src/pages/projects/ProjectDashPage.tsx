import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { GitBranch, Key, Cpu, Users, FileText, Code2, TestTube2, Shield, Loader2 } from 'lucide-react'
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts'
import { apiClient } from '@/lib/api'

interface ProjectDash {
  artifacts: { total: number; consolidated: number }
  codeGen: { total: number; pushed: number }
  tests: { total: number; passed: number }
  ai: { tokensUsed: number; costEstimated: number; provider: string; model: string }
  gatekeeper: { score: number; status: string; pillars: { pillar: string; score: number }[] }
  stack: { language: string; framework: string; database: string }
  repository?: { provider: string; branch: string; webhook: string }
  team: { name: string; email: string; role: string; capabilities?: string[] }[]
  credentials: { name: string; type: string; status: string; expiresAt?: string }[]
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

const ROLE_COLORS: Record<string, string> = {
  gp: 'bg-emerald-500/20 text-emerald-300',
  tech_lead: 'bg-blue-500/20 text-blue-300',
  dev_senior: 'bg-slate-500/20 text-slate-200',
  dev_pleno: 'bg-slate-600/20 text-slate-300',
  qa: 'bg-amber-500/20 text-amber-300',
  compliance: 'bg-violet-500/20 text-violet-300',
  admin: 'bg-violet-600/20 text-violet-300',
}

export function ProjectDashPage() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<ProjectDash | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get(`/dashboard/metrics?project_id=${id}`)
        setData(res.data)
      } catch {
        setData(null)
      } finally {
        setLoading(false)
      }
    }
    if (id) load()
  }, [id])

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>
  if (!data) return <div className="flex items-center justify-center h-64"><p className="text-slate-500">Dados do projeto nao disponiveis.</p></div>

  const radarData = (data.gatekeeper?.pillars || []).map(p => ({
    subject: p.pillar.split(' ').pop() || p.pillar,
    score: p.score,
    fullMark: 100,
  }))

  return (
    <div className="p-6 space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MiniKPI label="Artefatos" value={data.artifacts?.total || 0} sub={`${data.artifacts?.consolidated || 0} consolidados`} icon={<FileText className="w-4 h-4 text-blue-400" />} />
        <MiniKPI label="Geracoes" value={data.codeGen?.total || 0} sub={`${data.codeGen?.pushed || 0} enviadas`} icon={<Code2 className="w-4 h-4 text-violet-400" />} />
        <MiniKPI label="Testes" value={data.tests?.total || 0} sub={`${data.tests?.passed || 0} passaram`} icon={<TestTube2 className="w-4 h-4 text-emerald-400" />} />
        <MiniKPI label="Tokens IA" value={(data.ai?.tokensUsed || 0).toLocaleString('pt-BR')} sub={`R$ ${(data.ai?.costEstimated || 0).toFixed(2)} est.`} icon={<Cpu className="w-4 h-4 text-amber-400" />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Radar */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-slate-200 text-sm font-semibold flex items-center gap-2">
              <Shield className="w-4 h-4 text-violet-400" />
              Gatekeeper — 7 Pilares
            </h3>
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              data.gatekeeper?.status === 'approved' ? 'bg-emerald-500/20 text-emerald-300' :
              data.gatekeeper?.status === 'blocked' ? 'bg-red-500/20 text-red-300' :
              'bg-slate-700 text-slate-400'
            }`}>{data.gatekeeper?.status || 'N/A'}</span>
          </div>
          {radarData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
                <PolarGrid stroke="#334155" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <Radar name="Score" dataKey="score" stroke="#7c3aed" fill="#7c3aed" fillOpacity={0.25} />
                <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0', fontSize: '12px' }} />
              </RadarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-32 text-slate-500 text-sm">Gatekeeper nao iniciado</div>
          )}
        </div>

        {/* Stack + Repo */}
        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="text-slate-200 text-sm font-semibold mb-3 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-slate-400" />Stack & IA
            </h3>
            <div className="space-y-2">
              {[
                { k: 'Linguagem', v: data.stack?.language },
                { k: 'Framework', v: data.stack?.framework },
                { k: 'Banco', v: data.stack?.database },
                { k: 'Provedor IA', v: data.ai ? `${data.ai.provider} - ${data.ai.model}` : 'N/A' },
              ].map(({ k, v }) => (
                <div key={k} className="flex justify-between">
                  <span className="text-slate-500 text-xs">{k}</span>
                  <span className="text-slate-300 text-xs">{v || '--'}</span>
                </div>
              ))}
            </div>
          </div>
          {data.repository && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
              <h3 className="text-slate-200 text-sm font-semibold mb-3 flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-slate-400" />Repositorio
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between"><span className="text-slate-500 text-xs">Provedor</span><span className="text-slate-300 text-xs capitalize">{data.repository.provider}</span></div>
                <div className="flex justify-between"><span className="text-slate-500 text-xs">Branch</span><span className="text-slate-300 text-xs">{data.repository.branch}</span></div>
                <div className="flex justify-between"><span className="text-slate-500 text-xs">Webhook</span><span className="text-slate-300 text-xs">{data.repository.webhook}</span></div>
              </div>
            </div>
          )}
        </div>

        {/* Team */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-3 flex items-center gap-2">
            <Users className="w-4 h-4 text-slate-400" />Equipe ({data.team?.length || 0})
          </h3>
          <div className="space-y-2.5">
            {(data.team || []).map((member, i) => (
              <div key={i} className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-violet-700/50 flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">
                  {member.name.charAt(0)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-slate-200 text-xs truncate">{member.name}</p>
                  {member.capabilities && member.capabilities.length > 0 && (
                    <p className="text-slate-500 text-[10px] truncate">{member.capabilities.join(', ')}</p>
                  )}
                </div>
                <span className={`text-xs px-2 py-0.5 rounded ${ROLE_COLORS[member.role] || 'bg-slate-700 text-slate-400'}`}>
                  {member.role}
                </span>
              </div>
            ))}
            {(!data.team || data.team.length === 0) && <p className="text-slate-500 text-xs">Nenhum membro.</p>}
          </div>
        </div>
      </div>

      {/* Credentials */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Key className="w-4 h-4 text-slate-400" />
          <h3 className="text-slate-200 text-sm font-semibold">Credenciais do Projeto</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {(data.credentials || []).map((cred, i) => (
            <div key={i} className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
              <div className="flex items-center justify-between mb-1">
                <span className="text-slate-300 text-xs font-medium">{cred.name}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded ${
                  cred.status === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
                  cred.status === 'expired' ? 'bg-red-500/20 text-red-300' :
                  'bg-amber-500/20 text-amber-300'
                }`}>{cred.status}</span>
              </div>
              <p className="text-slate-500 text-xs capitalize">{cred.type}</p>
              {cred.expiresAt && <p className="text-slate-600 text-xs mt-1">Expira: {new Date(cred.expiresAt).toLocaleDateString('pt-BR')}</p>}
            </div>
          ))}
          {(!data.credentials || data.credentials.length === 0) && <p className="text-slate-500 text-sm col-span-4">Nenhuma credencial configurada.</p>}
        </div>
      </div>
    </div>
  )
}
