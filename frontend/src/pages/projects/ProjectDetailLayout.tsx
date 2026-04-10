import { useState, useEffect } from 'react'
import { Outlet, NavLink, useParams, useNavigate, Link } from 'react-router-dom'
import {
  ChevronLeft, Activity, Settings, FileText, Shield, GitBranch, Zap,
  Code2, TestTube2, Clock, BookOpen, AlertTriangle, ClipboardList, Loader2
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useProjectPermissions } from '@/hooks/useProjectPermissions'
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner'
import { useAuthStore } from '@/stores/authStore'

interface ProjectHeader {
  id: string
  name: string
  slug: string
  status: string
  phase: number
  language: string
  database: string
  gatekeeperScore: number
  pendingIssues: number
}

const MODULES = [
  { path: '', label: 'Dashboard', icon: Activity, end: true },
  { path: 'ocg', label: 'OCG', icon: Settings },
  { path: 'questionnaire', label: 'Questionário', icon: ClipboardList },
  { path: 'repository', label: 'Repositório', icon: Shield },
  { path: 'external-repos', label: 'Repos Externos', icon: GitBranch },
  { path: 'ingestion', label: 'Ingestão', icon: FileText },
  { path: 'gatekeeper', label: 'Gatekeeper', icon: Shield },
  { path: 'arguider', label: 'Arguidor', icon: Zap },
  { path: 'codegen', label: 'Geração de Código', icon: Code2 },
  { path: 'qa', label: 'Testes', icon: TestTube2 },
  { path: 'tester-review', label: 'Revisão de Testes', icon: FileText },
  { path: 'backlog', label: 'Backlog', icon: ClipboardList },
  { path: 'roadmap', label: 'Roadmap', icon: Clock },
  { path: 'docs', label: 'Documentação Viva', icon: BookOpen },
  { path: 'audit', label: 'Auditoria', icon: Shield },
]

const PIPELINE_PATHS = new Set([
  'ingestion', 'gatekeeper', 'arguider', 'codegen',
  'qa', 'tester-review', 'backlog', 'roadmap', 'docs',
])

export function ProjectDetailLayout() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [project, setProject] = useState<ProjectHeader | null>(null)
  const [repoConnected, setRepoConnected] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const { can, role, roles, isReadOnly } = useProjectPermissions()
  const user = useAuthStore((s) => s.user)

  useEffect(() => {
    const load = async () => {
      try {
        const [projRes, repoRes] = await Promise.all([
          apiClient.get(`/projects/${id}`),
          apiClient.get(`/projects/${id}/git/status`).catch(() => ({ data: { connected: false } })),
        ])
        setProject(projRes.data)
        setRepoConnected(repoRes.data?.connected || false)
      } catch {
        setProject(null)
      } finally {
        setLoading(false)
      }
    }
    if (id) load()
  }, [id])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>
  }

  if (!project) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-slate-500">Projeto não encontrado.</p>
      </div>
    )
  }

  const score = project.gatekeeperScore || 0
  const scoreColor = score >= 90 ? '#34d399' : score >= 70 ? '#fbbf24' : '#f87171'

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-4 px-6 py-4 bg-slate-900/50 border-b border-slate-800">
        <button onClick={() => navigate('/projects')} className="p-1.5 rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-violet-900/40 border border-violet-800/40 flex items-center justify-center text-violet-400 font-bold text-sm flex-shrink-0">
            {project.name.charAt(0)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-slate-100 font-semibold text-sm">{project.name}</h2>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                project.status === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
                project.status === 'degraded' ? 'bg-amber-500/20 text-amber-300' :
                'bg-slate-700 text-slate-400'
              }`}>{project.status}</span>
              {(project.pendingIssues || 0) > 0 && (
                <span className="flex items-center gap-1 text-amber-400 text-xs">
                  <AlertTriangle className="w-3 h-3" />{project.pendingIssues} pendencias
                </span>
              )}
            </div>
            <p className="text-slate-500 text-xs truncate">
              {project.slug} - Fase {project.phase}{project.language ? ` - ${project.language}` : ''}{project.database ? ` - ${project.database}` : ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {user?.is_admin && (
            <Link to="/admin" className="flex items-center gap-1 rounded-lg bg-violet-600/20 px-3 py-1.5 text-xs text-violet-300 hover:bg-violet-600/30">
              <Shield className="h-3.5 w-3.5" />
              Painel Admin
            </Link>
          )}
          <span className="text-slate-500 text-xs">GK:</span>
          <div className="flex items-center gap-1.5">
            <div className="w-20 bg-slate-700 rounded-full h-1.5">
              <div className="h-1.5 rounded-full transition-all" style={{ width: `${score}%`, backgroundColor: scoreColor }} />
            </div>
            <span className="text-slate-400 text-xs">{score}/100</span>
          </div>
        </div>
      </div>

      {/* Read-Only Banner */}
      {isReadOnly && <div className="px-6 pt-2"><ReadOnlyBanner /></div>}

      {/* Module Tabs */}
      <div className="flex items-center gap-0.5 px-6 py-2 border-b border-slate-800 bg-slate-900/30 overflow-x-auto">
        {MODULES.map(mod => {
          const Icon = mod.icon
          const to = mod.path ? `/projects/${id}/${mod.path}` : `/projects/${id}`
          const isBlocked = project?.status === 'initializing' && PIPELINE_PATHS.has(mod.path)

          if (isBlocked) {
            return (
              <span
                key={mod.path || 'dashboard'}
                title="Complete a configuracao obrigatoria para acessar"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap text-slate-600 cursor-not-allowed opacity-50"
              >
                <Icon className="w-3.5 h-3.5" />
                {mod.label}
              </span>
            )
          }

          return (
            <NavLink
              key={mod.path || 'dashboard'}
              to={to}
              end={mod.end}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
                  isActive ? 'bg-violet-600/20 text-violet-300 border border-violet-600/30' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
                }`
              }
            >
              <Icon className="w-3.5 h-3.5" />
              {mod.label}
            </NavLink>
          )
        })}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <Outlet context={{ repoConnected, can, role, roles, isReadOnly, projectStatus: project?.status }} />
      </div>
    </div>
  )
}
