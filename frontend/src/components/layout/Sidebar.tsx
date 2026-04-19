import { useState, useEffect } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, FolderOpen, Users, Shield, ChevronDown, ChevronRight,
  LogOut, Settings, Code2, FileText, GitBranch, Zap, TestTube2,
  History, BookOpen, Activity, ScrollText, Menu, X, Clock, ClipboardList,
  CheckCircle2, BarChart3, Database, Bug, LifeBuoy
} from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { useAuth } from '@/hooks/useAuth'
import { apiClient } from '@/lib/api'

interface SidebarProject {
  id: string
  name: string
  status: string
  role: string
}

// Papéis canônicos (GCA_CANONICAL_CONTRACT.md §4): Admin, GP, Dev, Tester, QA.
const ROLE_LABELS: Record<string, { label: string; bg: string; text: string }> = {
  admin: { label: 'Admin', bg: 'bg-violet-500/15', text: 'text-violet-300' },
  gp: { label: 'GP', bg: 'bg-emerald-500/15', text: 'text-emerald-300' },
  dev: { label: 'Dev', bg: 'bg-cyan-500/15', text: 'text-cyan-300' },
  tester: { label: 'Tester', bg: 'bg-orange-500/15', text: 'text-orange-300' },
  qa: { label: 'QA', bg: 'bg-amber-500/15', text: 'text-amber-300' },
}

const statusDot = (status: string) => {
  const colors: Record<string, string> = {
    active: 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.4)]',
    degraded: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.4)]',
    provisioning: 'bg-blue-400 animate-pulse shadow-[0_0_6px_rgba(96,165,250,0.4)]',
    draft: 'bg-slate-600',
  }
  return <span className={`w-2 h-2 rounded-full inline-block flex-shrink-0 ${colors[status] || 'bg-slate-600'}`} />
}

export function Sidebar() {
  const { user } = useAuthStore()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [projectsOpen, setProjectsOpen] = useState(true)
  const [projects, setProjects] = useState<SidebarProject[]>([])
  const [pendingCount, setPendingCount] = useState(0)

  const isAdmin = user?.is_admin || false
  const userName = user?.full_name || user?.email || 'Usuario'
  const initials = userName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get('/projects')
        const data = res.data.projects || res.data || []
        setProjects(data.map((p: any) => ({ id: p.id, name: p.name, status: p.status, role: p.role || '' })))
      } catch {}
      if (isAdmin) {
        try {
          const res = await apiClient.get('/admin/projects/pending')
          setPendingCount(res.data.pending_count || 0)
        } catch {}
      } else {
        setPendingCount(0)
      }
    }
    load()
  }, [isAdmin, location.pathname])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  // ── Collapsed sidebar ──
  if (!sidebarOpen) {
    return (
      <div className="flex flex-col items-center w-16 bg-[#080814] border-r border-white/[0.04] py-4 gap-3">
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-2.5 rounded-xl text-slate-500 hover:bg-white/[0.05] hover:text-slate-200 transition-all duration-200"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-purple-700 flex items-center justify-center text-white text-xs font-bold shadow-[0_0_15px_rgba(112,56,224,0.2)]">
          G
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col w-[250px] bg-[#080814] border-r border-white/[0.04] h-screen overflow-hidden relative">
      {/* Ambient glow */}
      <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-violet-500/[0.03] to-transparent pointer-events-none" />

      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-white/[0.04] relative z-10">
        <div className="flex items-center gap-3">
          <div className="relative">
            <img src="/images/gca-icon-40.png" alt="GCA" className="w-9 h-9 drop-shadow-[0_0_8px_rgba(112,56,224,0.2)]" />
          </div>
          <div>
            <span className="text-white text-sm font-bold tracking-tight">GCA</span>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <p className="text-slate-600 text-[9px] tracking-[0.15em] uppercase">Online</p>
            </div>
          </div>
        </div>
        <button onClick={() => setSidebarOpen(false)} className="p-1.5 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-white/[0.05] transition-all duration-200">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── User card ── */}
      <div className="mx-3 mt-3 mb-2 p-3 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-purple-700 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 shadow-[0_0_12px_rgba(112,56,224,0.2)]">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-slate-200 text-xs font-medium truncate">{userName}</p>
            <span className={`inline-block mt-0.5 text-[9px] px-1.5 py-0.5 rounded-md ${isAdmin ? 'bg-violet-500/15 text-violet-300 border border-violet-500/20' : 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'}`}>
              {isAdmin ? 'Admin' : (user?.project_roles?.[0]?.role ? (ROLE_LABELS[user.project_roles[0].role]?.label || user.project_roles[0].role) : 'Membro')}
            </span>
          </div>
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto relative z-10 scrollbar-thin scrollbar-thumb-white/5">
        {/* Admin section */}
        {isAdmin && (
          <div className="mb-5">
            <p className="text-slate-600 text-[9px] uppercase tracking-[0.2em] px-2 mb-2 font-semibold">Administração</p>
            <NavItem to="/admin" icon={<LayoutDashboard className="w-4 h-4" />} label="Dashboard Global" end />
            <div className="relative">
              <NavItem to="/admin/projects" icon={<FolderOpen className="w-4 h-4" />} label="Projetos" />
              {pendingCount > 0 && (
                <span className="absolute top-2.5 right-2.5 flex items-center justify-center">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse shadow-[0_0_6px_rgba(239,68,68,0.5)]" />
                </span>
              )}
            </div>
            <NavItem to="/admin/users" icon={<Users className="w-4 h-4" />} label="Usuários" />
            <NavItem to="/admin/audit" icon={<ScrollText className="w-4 h-4" />} label="Auditoria Global" />
            <NavItem to="/admin/metrics" icon={<BarChart3 className="w-4 h-4" />} label="Métricas" />
            <NavItem to="/admin/backups" icon={<Database className="w-4 h-4" />} label="Backups" />
            <NavItem to="/admin/incidents" icon={<Bug className="w-4 h-4" />} label="Incidentes" />
            <NavItem to="/admin/support" icon={<LifeBuoy className="w-4 h-4" />} label="Equipe Sustentação" />
          </div>
        )}

        {/* Projects */}
        <div>
          <button
            onClick={() => setProjectsOpen(v => !v)}
            className="w-full flex items-center justify-between px-2 py-1.5 text-slate-600 text-[9px] uppercase tracking-[0.2em] font-semibold hover:text-slate-400 transition-colors"
          >
            <span>Meus Projetos</span>
            <div className={`transition-transform duration-200 ${projectsOpen ? 'rotate-0' : '-rotate-90'}`}>
              <ChevronDown className="w-3 h-3" />
            </div>
          </button>

          <div className={`overflow-hidden transition-all duration-300 ${projectsOpen ? 'max-h-[600px] opacity-100' : 'max-h-0 opacity-0'}`}>
            <div className="mt-1 space-y-0.5">
              {projects.map(proj => {
                const isInProject = location.pathname.startsWith(`/projects/${proj.id}`)
                return (
                  <div key={proj.id}>
                    <NavLink
                      to={`/projects/${proj.id}`}
                      className={({ isActive }) =>
                        `flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm transition-all duration-200 ${
                          isActive || isInProject
                            ? 'bg-white/[0.06] text-white border border-white/[0.08] shadow-[0_2px_8px_rgba(0,0,0,0.2)]'
                            : 'text-slate-500 hover:bg-white/[0.03] hover:text-slate-300'
                        }`
                      }
                      end
                    >
                      {statusDot(proj.status)}
                      <span className="truncate text-xs flex-1 font-medium">{proj.name}</span>
                      {proj.role && (() => {
                        const rc = ROLE_LABELS[proj.role] || { label: proj.role, bg: 'bg-slate-500/15', text: 'text-slate-400' }
                        return <span className={`text-[8px] px-1.5 py-0.5 rounded-md ${rc.bg} ${rc.text} flex-shrink-0 border border-white/[0.04]`}>{rc.label}</span>
                      })()}
                    </NavLink>
                    {isInProject && !isAdmin && (
                      <div className="ml-5 mt-1 mb-2 space-y-0.5 border-l border-white/[0.06] pl-3">
                        <SubNavItem to={`/projects/${proj.id}`} label="Dashboard" icon={<Activity className="w-3 h-3" />} end />
                        <SubNavItem to={`/projects/${proj.id}/team`} label="Equipe" icon={<Users className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/ocg`} label="OCG" icon={<Settings className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/questionnaire`} label="Questionário" icon={<ClipboardList className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/repository`} label="Repositório" icon={<Shield className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/external-repos`} label="Repos Externos" icon={<GitBranch className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/ingestion`} label="Ingestão" icon={<FileText className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/gatekeeper`} label="Gatekeeper" icon={<Shield className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/arguider`} label="Arguidor" icon={<Zap className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/backlog`} label="Backlog" icon={<ClipboardList className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/roadmap`} label="Roadmap" icon={<Clock className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/codegen`} label="Geração de Código" icon={<Code2 className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/qa`} label="Testes" icon={<TestTube2 className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/tester-review`} label="Revisão de Testes" icon={<FileText className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/docs`} label="Documentação Viva" icon={<BookOpen className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/readiness`} label="Definition of Done" icon={<CheckCircle2 className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/backups`} label="Backups" icon={<Database className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/incidents`} label="Incidentes" icon={<Bug className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/settings`} label="Configurações" icon={<Settings className="w-3 h-3" />} />
                      </div>
                    )}
                    {isInProject && isAdmin && (
                      <div className="ml-5 mt-1 mb-2 space-y-0.5 border-l border-white/[0.06] pl-3">
                        <SubNavItem to={`/admin/projects/${proj.id}`} label="Visão Admin" icon={<Activity className="w-3 h-3" />} end />
                      </div>
                    )}
                  </div>
                )
              })}
              <NavLink
                to="/projects"
                className="flex items-center gap-2 px-2.5 py-2 rounded-xl text-xs text-slate-600 hover:text-slate-400 hover:bg-white/[0.03] transition-all duration-200"
              >
                Ver todos os projetos
              </NavLink>
            </div>
          </div>
        </div>
      </nav>

      {/* ── Footer ── */}
      <div className="px-4 py-3 border-t border-white/[0.04]">
        <div className="flex items-center justify-between">
          <p className="text-slate-700 text-[9px] font-mono">GCA v0.8.0</p>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/60" />
            <p className="text-slate-700 text-[9px]">Todos os serviços ativos</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function NavItem({ to, icon, label, end }: { to: string; icon: React.ReactNode; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm transition-all duration-200 ${
          isActive
            ? 'bg-violet-500/[0.12] text-violet-300 border border-violet-500/20 shadow-[0_0_12px_rgba(112,56,224,0.08)]'
            : 'text-slate-500 hover:bg-white/[0.04] hover:text-slate-300'
        }`
      }
    >
      {icon}
      <span className="font-medium">{label}</span>
    </NavLink>
  )
}

function SubNavItem({ to, label, icon, end }: { to: string; label: string; icon: React.ReactNode; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-2 py-1.5 px-2 rounded-lg text-xs transition-all duration-200 ${
          isActive
            ? 'text-violet-300 bg-violet-500/[0.08] font-medium'
            : 'text-slate-600 hover:text-slate-300 hover:bg-white/[0.03]'
        }`
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  )
}
