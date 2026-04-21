import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, Users, Calendar, FolderOpen, Mail, Activity, DollarSign } from 'lucide-react'
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

const STATUS_LABELS: Record<string, { label: string; bg: string; text: string }> = {
  active:       { label: 'Ativo',          bg: 'bg-emerald-500/20', text: 'text-emerald-300' },
  provisioning: { label: 'Provisionando',  bg: 'bg-blue-500/20',    text: 'text-blue-300' },
  draft:        { label: 'Rascunho',       bg: 'bg-slate-600/30',   text: 'text-slate-400' },
  degraded:     { label: 'Degradado',      bg: 'bg-amber-500/20',   text: 'text-amber-300' },
  completed:    { label: 'Concluído',      bg: 'bg-blue-500/20',    text: 'text-blue-300' },
  archived:     { label: 'Arquivado',      bg: 'bg-slate-600/30',   text: 'text-slate-400' },
}

interface ProjectInfo {
  id: string
  name: string
  slug: string
  status: string
  created_at: string
  description?: string
}

interface Member {
  user_id: string
  full_name: string
  email: string
  role: string
}

interface PillarScore {
  pillar: string
  score: number
}

export function AdminProjectViewPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [project, setProject] = useState<ProjectInfo | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [pillarScores, setPillarScores] = useState<PillarScore[]>([])
  const [overallScore, setOverallScore] = useState<number | null>(null)
  const [totalCost, setTotalCost] = useState<number | null>(null)

  useEffect(() => {
    if (!id) return
    const load = async () => {
      try {
        const [projRes, membersRes, ocgRes, billingRes] = await Promise.all([
          apiClient.get(`/projects/${id}`),
          apiClient.get(`/projects/${id}/members`).catch(() => ({ data: { members: [] } })),
          apiClient.get(`/projects/${id}/ocg`).catch(() => ({ data: {} })),
          apiClient.get(`/projects/${id}/billing`).catch(() => ({ data: {} })),
        ])

        const p = projRes.data?.project || projRes.data || {}
        setProject({
          id: p.id || id,
          name: p.name || p.slug || '—',
          slug: p.slug || '—',
          status: p.status || 'draft',
          created_at: p.created_at || '',
          description: p.description || '',
        })

        setMembers(membersRes.data?.members || [])

        // OCG scores
        const ocg = ocgRes.data?.ocg || ocgRes.data || {}
        const scores = ocg.pillar_scores || ocg.scores || {}
        const parsed: PillarScore[] = Object.entries(scores).map(([k, v]) => ({
          pillar: k,
          score: typeof v === 'number' ? v : (v as { score?: number })?.score || 0,
        }))
        setPillarScores(parsed)
        setOverallScore(ocg.overall_score ?? ocg.score ?? null)

        // Billing
        const billing = billingRes.data || {}
        setTotalCost(billing.total_cost ?? billing.total ?? null)
      } catch {
        // Project may not exist or user lacks access
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
      </div>
    )
  }

  if (!project) {
    return (
      <div className="p-6">
        <button onClick={() => navigate('/admin/projects')} className="flex items-center gap-2 text-slate-400 hover:text-slate-200 text-sm mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Voltar para Projetos
        </button>
        <p className="text-slate-500 text-sm">Projeto não encontrado.</p>
      </div>
    )
  }

  const st = STATUS_LABELS[project.status] || STATUS_LABELS.draft
  const gpMembers = members.filter(m => m.role === 'gp')

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/admin/projects')} className="p-2 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/[0.05] transition-all">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-slate-100">{project.name}</h1>
            <span className={`text-xs px-2.5 py-0.5 rounded-full ${st.bg} ${st.text}`}>{st.label}</span>
          </div>
          <p className="text-slate-500 text-sm mt-0.5">Visão administrativa — dados agregados apenas</p>
        </div>
      </div>

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <FolderOpen className="w-4 h-4 text-violet-400" />
            <span className="text-slate-300 text-sm font-medium">Informações do Projeto</span>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-xs">Slug</span>
              <span className="text-slate-300 text-xs font-mono">{project.slug}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-xs">Status</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${st.bg} ${st.text}`}>{st.label}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-xs">Criado em</span>
              <span className="text-slate-300 text-xs">
                {project.created_at ? new Date(project.created_at).toLocaleDateString('pt-BR') : '—'}
              </span>
            </div>
            {project.description && (
              <div className="pt-2 border-t border-slate-800">
                <p className="text-slate-400 text-xs">{project.description}</p>
              </div>
            )}
          </div>
        </div>

        {/* GP */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Users className="w-4 h-4 text-emerald-400" />
            <span className="text-slate-300 text-sm font-medium">Gerente(s) de Projeto</span>
          </div>
          {gpMembers.length > 0 ? (
            <div className="space-y-2">
              {gpMembers.map(gp => (
                <div key={gp.user_id} className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-emerald-900/40 border border-emerald-800/30 flex items-center justify-center text-emerald-300 text-xs font-bold flex-shrink-0">
                    {(gp.full_name || gp.email).charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-slate-200 text-xs font-medium truncate">{gp.full_name || '—'}</p>
                    <p className="text-slate-500 text-[10px] truncate">{gp.email}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-xs">Nenhum GP atribuído</p>
          )}
        </div>

        {/* Aggregate metrics */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-4 h-4 text-blue-400" />
            <span className="text-slate-300 text-sm font-medium">Métricas Agregadas</span>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-xs">Score OCG Geral</span>
              <span className={`text-sm font-semibold ${overallScore !== null ? (overallScore >= 80 ? 'text-emerald-400' : overallScore >= 60 ? 'text-amber-400' : 'text-red-400') : 'text-slate-600'}`}>
                {overallScore !== null ? `${overallScore}%` : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-xs">Membros na equipe</span>
              <span className="text-slate-300 text-sm font-semibold">{members.length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-xs flex items-center gap-1"><DollarSign className="w-3 h-3" /> Custo IA total</span>
              <span className="text-slate-300 text-sm font-semibold">
                {totalCost !== null ? `R$ ${totalCost.toFixed(2)}` : '—'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Pillar Scores Table */}
      {pillarScores.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-4">Scores por Pilar</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left px-3 py-2 text-xs text-slate-500 font-medium">PILAR</th>
                  <th className="text-left px-3 py-2 text-xs text-slate-500 font-medium">NOME</th>
                  <th className="text-right px-3 py-2 text-xs text-slate-500 font-medium">SCORE</th>
                  <th className="text-left px-3 py-2 text-xs text-slate-500 font-medium w-1/3">PROGRESSO</th>
                </tr>
              </thead>
              <tbody>
                {pillarScores.map(ps => {
                  const scoreColor = ps.score >= 80 ? 'text-emerald-400' : ps.score >= 60 ? 'text-amber-400' : 'text-red-400'
                  const barColor = ps.score >= 80 ? 'bg-emerald-500' : ps.score >= 60 ? 'bg-amber-500' : 'bg-red-500'
                  return (
                    <tr key={ps.pillar} className="border-b border-slate-800/50">
                      <td className="px-3 py-2.5 text-sm text-slate-300 font-mono">{ps.pillar}</td>
                      <td className="px-3 py-2.5 text-sm text-slate-400">{PILLAR_NAMES[ps.pillar] || ps.pillar}</td>
                      <td className={`px-3 py-2.5 text-sm font-semibold text-right ${scoreColor}`}>{ps.score}%</td>
                      <td className="px-3 py-2.5">
                        <div className="w-full bg-slate-800 rounded-full h-1.5">
                          <div className={`h-1.5 rounded-full ${barColor} transition-all`} style={{ width: `${Math.min(ps.score, 100)}%` }} />
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Team Members Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-4">Equipe do Projeto</h3>
        {members.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left px-3 py-2 text-xs text-slate-500 font-medium">MEMBRO</th>
                  <th className="text-left px-3 py-2 text-xs text-slate-500 font-medium">EMAIL</th>
                  <th className="text-left px-3 py-2 text-xs text-slate-500 font-medium">PAPEL</th>
                </tr>
              </thead>
              <tbody>
                {members.map(m => {
                  const roleColor = ROLE_COLORS[m.role] || 'bg-slate-600/20 text-slate-400'
                  return (
                    <tr key={m.user_id} className="border-b border-slate-800/50">
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 text-xs font-bold flex-shrink-0">
                            {(m.full_name || m.email).charAt(0).toUpperCase()}
                          </div>
                          <span className="text-slate-200 text-sm">{m.full_name || '—'}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="text-slate-400 text-sm">{m.email}</span>
                      </td>
                      <td className="px-3 py-2.5">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${roleColor}`}>
                          {ROLE_LABELS[m.role] || m.role}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-slate-500 text-sm text-center py-4">Nenhum membro na equipe</p>
        )}
      </div>

      {/* Admin notice */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 flex items-start gap-3">
        <Calendar className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-slate-500">
          Esta é uma visão administrativa limitada. Para acessar dados completos do pipeline (Ingestão, Gatekeeper, Arguidor, CodeGen, QA, etc.),
          o Gerente de Projeto ou um membro da equipe deve ser consultado.
        </p>
      </div>
    </div>
  )
}
