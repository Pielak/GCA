import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, FolderOpen, FileText, Shield, Code2,
  GitBranch, CheckSquare, Settings, LogOut, Bell, Link2,
  DatabaseBackup, ShieldAlert, Users, MessageSquare, Folder,
  ChevronDown, ChevronRight, SlidersHorizontal, ExternalLink, GitMerge, Boxes,
} from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { api } from "@/services/api";
import { clsx } from "clsx";

// Itens globais — visíveis independente de projeto selecionado
const GLOBAL_ITEMS = [
  { label: "Dashboard", icon: LayoutDashboard, to: "/dashboard" },
  { label: "Projetos",  icon: FolderOpen,       to: "/projects"  },
];

// Itens exclusivos de Admin (globais)
const ADMIN_ITEMS = [
  { label: "Gerenciar Projetos", icon: ShieldAlert,    to: "/admin/projects"             },
  { label: "Gestão de Usuários", icon: Users,           to: "/admin/users"                },
  { label: "Parametrização",     icon: Settings,        to: "/settings/parametrization"   },
  { label: "Backup & Recovery",  icon: DatabaseBackup,  to: "/settings/backup"            },
];

// Itens do projeto — ordem segue o fluxo de desenvolvimento
const projectSubItems = (projectId: string) => [
  // ── Configuração do projeto ──────────────────────────────
  { label: "Equipe",                 icon: Users,         to: `/projects/${projectId}/team`          },
  { label: "Repositório do Projeto", icon: Link2,         to: `/projects/${projectId}/repos`         },
  { label: "Repositório Terceiros",  icon: ExternalLink,  to: `/projects/${projectId}/legacy`        },
  // ── Levantamento de requisitos ───────────────────────────
  { label: "Arguidor",               icon: MessageSquare, to: `/projects/${projectId}/arguidor`      },
  { label: "Artefatos",              icon: FileText,      to: `/projects/${projectId}/artifacts`     },
  // ── Avaliação e prontidão ────────────────────────────────
  { label: "Consolidação",           icon: GitMerge,      to: `/projects/${projectId}/merge`         },
  { label: "Gatekeeper",             icon: Shield,        to: `/projects/${projectId}/gatekeeper`    },
  { label: "Roadmap",                icon: GitBranch,     to: `/projects/${projectId}/roadmap`       },
  // ── Geração de código ────────────────────────────────────
  { label: "Módulos",                icon: Boxes,         to: `/projects/${projectId}/modules`       },
  { label: "Gerador de Código",      icon: Code2,         to: `/projects/${projectId}/codegen`       },
  // ── Qualidade e automação ────────────────────────────────
  { label: "QA Readiness",           icon: CheckSquare,   to: `/projects/${projectId}/qa`            },
  { label: "Notificações",           icon: Bell,          to: `/projects/${projectId}/notifications` },
];

// ── Componentes auxiliares ────────────────────────────────────────────────────

function NavLink({
  label, icon: Icon, to, pathname, indent = 0,
}: {
  label: string; icon: React.ElementType; to: string; pathname: string; indent?: number;
}) {
  const active = pathname === to || (to !== "/projects" && pathname.startsWith(to + "/"));
  return (
    <Link
      to={to}
      style={{ paddingLeft: `${indent * 10 + 12}px` }}
      className={clsx(
        "flex items-center gap-2.5 py-1.5 pr-3 rounded-lg text-sm font-medium transition-colors",
        active
          ? "bg-violet-600/20 text-violet-400"
          : "text-gray-400 hover:text-gray-200 hover:bg-dark-100"
      )}
    >
      <Icon size={14} className="shrink-0" />
      <span className="truncate">{label}</span>
    </Link>
  );
}

function CollapseSection({
  label, icon: Icon, children, defaultOpen = true, indent = 0,
}: {
  label: string; icon: React.ElementType; children: React.ReactNode;
  defaultOpen?: boolean; indent?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ paddingLeft: `${indent * 10 + 12}px` }}
        className="w-full flex items-center justify-between py-1.5 pr-3 text-xs font-semibold text-gray-500 uppercase tracking-wider hover:text-gray-300 transition-colors rounded-lg"
      >
        <div className="flex items-center gap-1.5">
          <Icon size={12} className="shrink-0" />
          <span className="truncate">{label}</span>
        </div>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </button>
      {open && <div>{children}</div>}
    </>
  );
}

// ── Sidebar principal ─────────────────────────────────────────────────────────

export function Sidebar() {
  const { pathname } = useLocation();
  const { projectId } = useParams();
  const { user, clearAuth, refresh_token } = useAuthStore();

  // Busca o nome do projeto ativo para exibir no nível primário
  const { data: project } = useQuery<{ name: string }>({
    queryKey: ["project-name", projectId],
    queryFn: () => api.get(`/projects/${projectId}`).then(r => r.data),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000,
  });

  const handleLogout = async () => {
    try {
      await api.post("/auth/logout", { refresh_token });
    } finally {
      clearAuth();
      window.location.href = "/login";
    }
  };

  return (
    <aside className="w-60 min-h-screen bg-dark flex flex-col border-r border-gray-800 fixed top-0 left-0 z-20">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-gray-800">
        <div className="flex items-center gap-2 min-w-0">
          <img src="/GPD.png" alt="Gestão de Processos de Desenvolvimento" className="w-8 h-8 rounded-lg object-contain flex-shrink-0" />
          <span className="font-bold text-violet-400 text-xs truncate" title="Gestão de Processos de Desenvolvimento">Gestão de Processos</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-2 space-y-0.5 overflow-y-auto">

        {/* ── Global ──────────────────────────────────────────── */}
        {GLOBAL_ITEMS.map(item => (
          <NavLink key={item.to} {...item} pathname={pathname} />
        ))}

        {/* ── Projeto [Nome] ──────────────────────────────────── */}
        {projectId && (
          <>
            <div className="pt-2" />
            <CollapseSection
              label={project?.name ?? "Projeto"}
              icon={Folder}
              indent={0}
            >
              {/* ── Parâmetros (subnível) ───────────────────── */}
              <CollapseSection
                label="Parâmetros"
                icon={SlidersHorizontal}
                indent={1}
              >
                {projectSubItems(projectId).map(item => (
                  <NavLink key={item.to} {...item} pathname={pathname} indent={2} />
                ))}
              </CollapseSection>
            </CollapseSection>
          </>
        )}

        {/* ── Admin ───────────────────────────────────────────── */}
        {user?.role === "admin" && (
          <>
            <div className="pt-2" />
            <CollapseSection label="Admin" icon={ShieldAlert} indent={0}>
              {ADMIN_ITEMS.map(item => (
                <NavLink key={item.to} {...item} pathname={pathname} indent={1} />
              ))}
            </CollapseSection>
          </>
        )}

      </nav>

      {/* User + Logout */}
      <div className="px-3 py-4 border-t border-gray-800">
        <div className="text-xs text-gray-500 mb-2 truncate">{user?.name}</div>
        <span className="text-xs bg-violet-900/40 text-violet-300 px-2 py-0.5 rounded-full">
          {user?.role}
        </span>
        <button
          onClick={handleLogout}
          className="mt-3 w-full flex items-center gap-2 text-sm text-gray-400 hover:text-red-400 transition-colors"
        >
          <LogOut size={14} />
          Sair
        </button>
      </div>
    </aside>
  );
}
