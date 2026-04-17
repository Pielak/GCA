import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, Code2, TestTube2, Activity, Loader2 } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

interface Project {
  id: string
  name: string
  slug: string
  description: string
  status: string
  outputProfile: string
  phase: number
  stack: { language: string; framework: string; database: string }
  gatekeeperScore: number
  codeGenCount: number
  testsPassed: number
  testsTotal: number
  pendingIssues: number
  userRole?: string
}

// Papéis canônicos (GCA_CANONICAL_CONTRACT.md §4).
const ROLE_LABELS: Record<string, string> = {
  gp: 'Gerente de Projeto',
  dev: 'Dev',
  tester: 'Tester',
  qa: 'QA',
}

const OUTPUT_LABELS: Record<string, string> = {
  web_app: 'Web App', api: 'API', desktop: 'Desktop', mobile: 'Mobile', improvement: 'Melhoria', new_feature: 'Nova Feature',
}

const PHASES = ['--', 'Governanca', 'OCG + Prov.', 'Ingestão', 'Arguicao', 'Code Gen', 'QA', 'Docs Viva']

export function ProjectListPage() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get('/projects')
        setProjects(res.data.projects || res.data || [])
      } catch { /* empty */ } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>
  }

  const isAdmin = user?.is_admin ?? false
  const myProjects = projects.filter((p) => p.userRole && p.userRole !== 'admin_viewer')
  const otherProjects = isAdmin ? projects.filter((p) => !p.userRole || p.userRole === 'admin_viewer') : []

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Meus Projetos</h1>
        <p className="text-slate-500 text-sm mt-0.5">{myProjects.length} projeto{myProjects.length !== 1 ? 's' : ''} acessiveis ao seu perfil</p>
      </div>

      {myProjects.length > 0 && (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {myProjects.map(proj => (
          <div
            key={proj.id}
            onClick={() => navigate(`/projects/${proj.id}`)}
            className="bg-slate-900 border border-slate-800 rounded-xl p-5 cursor-pointer hover:border-violet-600/40 hover:bg-slate-800/60 transition-all group"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-violet-900/40 border border-violet-800/40 flex items-center justify-center text-violet-400 font-bold text-sm flex-shrink-0">
                  {proj.name.charAt(0)}
                </div>
                <div>
                  <p className="text-slate-200 text-sm font-medium group-hover:text-violet-300 transition-colors">{proj.name}</p>
                  <p className="text-slate-500 text-xs">{OUTPUT_LABELS[proj.outputProfile] || proj.outputProfile}</p>
                </div>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                proj.status === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
                proj.status === 'degraded' ? 'bg-amber-500/20 text-amber-300' :
                proj.status === 'provisioning' ? 'bg-blue-500/20 text-blue-300' :
                'bg-slate-700 text-slate-400'
              }`}>{proj.status}</span>
            </div>

            {proj.userRole && (
              <span className="inline-block mb-2 rounded-full bg-violet-600/20 px-2 py-0.5 text-xs text-violet-300">
                {ROLE_LABELS[proj.userRole] || proj.userRole}
              </span>
            )}

            <p className="text-slate-400 text-xs leading-relaxed mb-4">{proj.description}</p>

            {/* Phase progress */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-slate-500 text-xs">Fase {proj.phase} - {PHASES[proj.phase] || 'Operacao'}</span>
                <span className="text-slate-500 text-xs">{Math.round((proj.phase / 7) * 100)}%</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-1">
                <div className="h-1 rounded-full bg-violet-500 transition-all" style={{ width: `${(proj.phase / 7) * 100}%` }} />
              </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1 text-slate-400">
                  <Shield className="w-3 h-3" />
                  <span className="text-xs">{proj.gatekeeperScore || '--'}</span>
                </div>
                <p className="text-slate-600 text-[10px] mt-0.5">Gatekeeper</p>
              </div>
              <div className="text-center">
                <div className="flex items-center justify-center gap-1 text-slate-400">
                  <Code2 className="w-3 h-3" />
                  <span className="text-xs">{proj.codeGenCount || 0}</span>
                </div>
                <p className="text-slate-600 text-[10px] mt-0.5">Gerações</p>
              </div>
              <div className="text-center">
                <div className="flex items-center justify-center gap-1 text-slate-400">
                  <TestTube2 className="w-3 h-3" />
                  <span className="text-xs">{proj.testsPassed || 0}/{proj.testsTotal || 0}</span>
                </div>
                <p className="text-slate-600 text-[10px] mt-0.5">Testes</p>
              </div>
            </div>

            {/* Stack tags */}
            {proj.stack && (
              <div className="flex flex-wrap gap-1">
                {[proj.stack.language, proj.stack.framework, proj.stack.database].filter(Boolean).map(tag => (
                  <span key={tag} className="px-1.5 py-0.5 rounded text-xs bg-slate-800 text-slate-400 border border-slate-700">{tag}</span>
                ))}
              </div>
            )}

            {(proj.pendingIssues || 0) > 0 && (
              <div className="mt-3 flex items-center gap-1.5 text-amber-400 text-xs">
                <Activity className="w-3 h-3" />
                <span>{proj.pendingIssues} pendencia{proj.pendingIssues !== 1 ? 's' : ''}</span>
              </div>
            )}
          </div>
        ))}
      </div>
      )}

      {otherProjects.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-400">Todos os Projetos (somente leitura)</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {otherProjects.map(proj => (
              <div
                key={proj.id}
                onClick={() => navigate(`/projects/${proj.id}`)}
                className="bg-slate-900 border border-slate-800 rounded-xl p-5 cursor-pointer hover:border-violet-600/40 hover:bg-slate-800/60 transition-all group opacity-75"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-lg bg-violet-900/40 border border-violet-800/40 flex items-center justify-center text-violet-400 font-bold text-sm flex-shrink-0">
                      {proj.name.charAt(0)}
                    </div>
                    <div>
                      <p className="text-slate-200 text-sm font-medium group-hover:text-violet-300 transition-colors">{proj.name}</p>
                      <p className="text-slate-500 text-xs">{OUTPUT_LABELS[proj.outputProfile] || proj.outputProfile}</p>
                    </div>
                  </div>
                  <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-300">Somente Leitura</span>
                </div>
                <p className="text-slate-400 text-xs leading-relaxed mb-4">{proj.description}</p>
                <div className="flex items-center justify-between">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    proj.status === 'active' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-400'
                  }`}>{proj.status}</span>
                  {proj.gatekeeperScore > 0 && <span className="text-slate-500 text-xs">GK: {proj.gatekeeperScore}/100</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {projects.length === 0 && (
        <div className="text-center py-16">
          <p className="text-slate-500">Nenhum projeto encontrado.</p>
        </div>
      )}
    </div>
  )
}
