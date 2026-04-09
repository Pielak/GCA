import { useState, useEffect } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, FolderOpen, Users, Shield, ChevronDown, ChevronRight,
  LogOut, Settings, Code2, FileText, GitBranch, Zap, TestTube2,
  History, BookOpen, Activity, ScrollText, Menu, X, Clock, ClipboardList
} from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { useAuth } from '@/hooks/useAuth'
import { apiClient } from '@/lib/api'

interface SidebarProject {
  id: string
  name: string
  status: string
}

const statusDot = (status: string) => {
  const colors: Record<string, string> = {
    active: 'bg-emerald-400',
    degraded: 'bg-amber-400',
    provisioning: 'bg-blue-400 animate-pulse',
    draft: 'bg-slate-500',
  }
  return <span className={`w-2 h-2 rounded-full inline-block ${colors[status] || 'bg-slate-600'}`} />
}

export function Sidebar() {
  const { user } = useAuthStore()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [projectsOpen, setProjectsOpen] = useState(true)
  const [projects, setProjects] = useState<SidebarProject[]>([])

  const isAdmin = user?.is_admin || false
  const userName = user?.full_name || user?.email || 'Usuario'

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get('/projects')
        const data = res.data.projects || res.data || []
        setProjects(data.map((p: any) => ({ id: p.id, name: p.name, status: p.status })))
      } catch {
        // No projects available
      }
    }
    load()
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  if (!sidebarOpen) {
    return (
      <div className="flex flex-col items-center w-14 bg-dark border-r border-slate-800 py-4 gap-4">
        <button onClick={() => setSidebarOpen(true)} className="p-2 rounded-lg text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors">
          <Menu className="w-5 h-5" />
        </button>
        <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center text-white text-xs font-bold">G</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col w-60 bg-dark border-r border-slate-800 h-screen overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <img src="/images/gca-icon-40.png" alt="GCA" className="w-8 h-8" />
          <div>
            <span className="text-slate-100 text-sm font-semibold">GCA</span>
            <p className="text-slate-500 text-[10px] leading-none">Gestao de Codigo</p>
          </div>
        </div>
        <button onClick={() => setSidebarOpen(false)} className="p-1 rounded text-slate-500 hover:text-slate-300 transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* User + Sign-Out */}
      <div className="px-3 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2.5 px-2 py-2">
          <div className="w-7 h-7 rounded-full bg-violet-700 flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">
            {userName.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-slate-200 text-xs font-medium truncate">{userName}</p>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${isAdmin ? 'bg-violet-600/20 text-violet-300' : 'bg-emerald-500/20 text-emerald-300'}`}>
              {isAdmin ? 'Admin' : 'GP'}
            </span>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-2 px-4 py-1.5 mt-1 rounded-md text-slate-500 hover:bg-slate-800 hover:text-red-400 transition-colors text-xs"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign-Out
        </button>
      </div>

      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        {/* Admin section */}
        {isAdmin && (
          <div className="mb-4">
            <p className="text-slate-500 text-[10px] uppercase tracking-wider px-2 mb-2 font-semibold">Administracao</p>
            <NavItem to="/admin" icon={<LayoutDashboard className="w-4 h-4" />} label="Dashboard Global" end />
            <NavItem to="/admin/projects" icon={<FolderOpen className="w-4 h-4" />} label="Projetos" />
            <NavItem to="/admin/users" icon={<Users className="w-4 h-4" />} label="Usuarios" />
            <NavItem to="/admin/audit" icon={<ScrollText className="w-4 h-4" />} label="Auditoria Global" />
          </div>
        )}

        {/* Projects */}
        <div>
          <button
            onClick={() => setProjectsOpen(v => !v)}
            className="w-full flex items-center justify-between px-2 py-1 text-slate-500 text-[10px] uppercase tracking-wider font-semibold hover:text-slate-400 transition-colors"
          >
            <span>Meus Projetos</span>
            {projectsOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
          {projectsOpen && (
            <div className="mt-1 space-y-0.5">
              {projects.map(proj => {
                const isInProject = location.pathname.startsWith(`/projects/${proj.id}`)
                return (
                  <div key={proj.id}>
                    <NavLink
                      to={`/projects/${proj.id}`}
                      className={({ isActive }) =>
                        `flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
                          isActive || isInProject ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-300'
                        }`
                      }
                      end
                    >
                      {statusDot(proj.status)}
                      <span className="truncate text-xs">{proj.name}</span>
                    </NavLink>
                    {isInProject && (
                      <div className="ml-4 mt-0.5 space-y-0.5 border-l border-slate-700 pl-2">
                        <SubNavItem to={`/projects/${proj.id}`} label="Dashboard" icon={<Activity className="w-3 h-3" />} end />
                        <SubNavItem to={`/projects/${proj.id}/ocg`} label="OCG" icon={<Settings className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/questionnaire`} label="Questionario" icon={<ClipboardList className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/ingestion`} label="M4 - Ingestao" icon={<FileText className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/gatekeeper`} label="M5 - Gatekeeper" icon={<Shield className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/merge`} label="M6 - Merge" icon={<GitBranch className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/arguider`} label="M7 - Arguidor" icon={<Zap className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/codegen`} label="M8 - Code Gen" icon={<Code2 className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/qa`} label="M9 - QA" icon={<TestTube2 className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/tester-review`} label="Tester Review" icon={<FileText className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/legacy`} label="M10 - Legado" icon={<History className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/roadmap`} label="M11 - Roadmap" icon={<Clock className="w-3 h-3" />} />
                        <SubNavItem to={`/projects/${proj.id}/docs`} label="M12 - Docs" icon={<BookOpen className="w-3 h-3" />} />
                      </div>
                    )}
                  </div>
                )
              })}
              <NavLink
                to="/projects"
                className="flex items-center gap-2 px-2 py-1.5 rounded-md text-xs text-slate-500 hover:text-slate-300 hover:bg-slate-800/60 transition-colors"
              >
                Ver todos os projetos
              </NavLink>
            </div>
          )}
        </div>
      </nav>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-slate-800">
        <p className="text-slate-600 text-[9px] text-center">GCA v4.0</p>
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
        `flex items-center gap-2.5 px-2 py-2 rounded-md text-sm transition-colors ${
          isActive ? 'bg-violet-600/20 text-violet-300 border border-violet-600/30' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
        }`
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  )
}

function SubNavItem({ to, label, icon, end }: { to: string; label: string; icon: React.ReactNode; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-1.5 py-1 px-1 rounded text-xs transition-colors ${
          isActive ? 'text-violet-400 font-medium' : 'text-slate-500 hover:text-slate-300'
        }`
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  )
}
