import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { HelpIcon } from "@/components/HelpIcon";
import {
  LayoutDashboard, Code2, FileText, AlertTriangle,
  Activity, FolderOpen, Shield, ChevronRight, ServerCrash,
} from "lucide-react";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";
import { clsx } from "clsx";

interface Project {
  id: string;
  name: string;
  methodology: string;
  status: string;
  steps: { step1: boolean; step2: boolean; step3: boolean; step4: boolean };
}

const statusColors: Record<string, string> = {
  active: "text-emerald-400",
  pending_config: "text-amber-400",
  archived: "text-gray-500",
};
const statusLabels: Record<string, string> = {
  active: "Ativo",
  pending_config: "Configurando",
  archived: "Arquivado",
};

export function DashboardPage() {
  const { user } = useAuthStore();

  const { data: projectsData, isLoading, isError } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get("/projects").then((r) => r.data),
  });

  const projects: Project[] = projectsData?.data ?? [];
  const activeProjects = projects.filter((p) => p.status === "active");
  const pendingProjects = projects.filter((p) => p.status === "pending_config");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <LayoutDashboard size={22} className="text-violet-400" />
            Dashboard
            <HelpIcon text="Visão geral dos seus projetos GPD: status, etapas concluídas e atalhos rápidos para artefatos, Gatekeeper e geração de código." />
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Bem-vindo, {user?.name} · {user?.role}
          </p>
        </div>
        <Link to="/projects/new" className="btn-primary flex items-center gap-2 text-sm">
          <FolderOpen size={15} />
          Novo Projeto
        </Link>
      </div>

      {/* Erro de carregamento */}
      {isError && (
        <div className="card border-red-700/50 bg-red-950/10 flex items-center gap-3">
          <ServerCrash size={18} className="text-red-400 shrink-0" />
          <p className="text-red-300 text-sm">
            Não foi possível carregar os projetos. Verifique se o servidor está acessível e tente recarregar a página.
          </p>
        </div>
      )}

      {/* Métricas */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          {
            label: "Projetos Ativos",
            value: isLoading ? "…" : String(activeProjects.length),
            color: "text-emerald-400",
            icon: FolderOpen,
          },
          {
            label: "Em Configuração",
            value: isLoading ? "…" : String(pendingProjects.length),
            color: "text-amber-400",
            icon: Activity,
          },
          {
            label: "Projetos Total",
            value: isLoading ? "…" : String(projects.length),
            color: "text-violet-400",
            icon: Code2,
          },
          {
            label: user?.name ?? "Usuário",
            value: user?.role ?? "–",
            color: "text-blue-400",
            icon: Shield,
          },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="card">
            <div className={clsx("text-3xl font-bold mb-1", color)}>{value}</div>
            <div className="text-sm text-gray-400 flex items-center gap-1">
              <Icon size={14} />
              {label}
            </div>
          </div>
        ))}
      </div>

      {/* Lista de projetos */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <FolderOpen size={16} className="text-violet-400" />
            Seus Projetos
          </h2>
          <Link to="/projects" className="text-sm text-violet-400 hover:text-violet-300 flex items-center gap-1">
            Ver todos <ChevronRight size={14} />
          </Link>
        </div>

        {isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="animate-pulse h-12 bg-dark rounded-lg" />
            ))}
          </div>
        )}

        {!isLoading && projects.length === 0 && (
          <div className="text-center py-10">
            <p className="text-gray-500 mb-3">Nenhum projeto ainda.</p>
            <Link to="/projects/new" className="btn-primary text-sm inline-flex items-center gap-2">
              <FolderOpen size={14} />
              Criar primeiro projeto
            </Link>
          </div>
        )}

        <div className="space-y-2">
          {projects.slice(0, 5).map((project) => {
            const dest = project.status === "archived"
              ? `/projects`
              : `/projects/${project.id}/artifacts`;
            return (
              <Link
                key={project.id}
                to={dest}
                className="flex items-center justify-between p-3 rounded-lg bg-dark hover:bg-dark-200 transition-colors group"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className={clsx(
                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                    project.status === "pending_config" ? "bg-amber-900/40" : "bg-violet-900/40"
                  )}>
                    <FolderOpen size={15} className={project.status === "pending_config" ? "text-amber-400" : "text-violet-400"} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-white font-medium truncate">{project.name}</p>
                    <p className="text-xs text-gray-500">{project.methodology}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4 shrink-0">
                  <div className="flex gap-1">
                    {[1, 2, 3, 4].map((s) => {
                      const done = project.steps[`step${s}` as keyof typeof project.steps];
                      return (
                        <div
                          key={s}
                          className={clsx(
                            "w-1.5 h-1.5 rounded-full",
                            done ? "bg-emerald-400" : "bg-gray-700"
                          )}
                        />
                      );
                    })}
                  </div>
                  <span className={clsx("text-xs font-medium", statusColors[project.status])}>
                    {statusLabels[project.status]}
                  </span>
                  <ChevronRight
                    size={14}
                    className="text-gray-600 group-hover:text-gray-400 transition-colors"
                  />
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Dica se sem projetos ativos */}
      {!isLoading && activeProjects.length === 0 && projects.length > 0 && (
        <div className="card border-amber-700/50 bg-amber-950/10">
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="text-amber-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-amber-300 font-medium text-sm">Projeto em configuração</p>
              <p className="text-amber-400/80 text-sm mt-0.5">
                Complete o wizard de criação para ativar o projeto e começar a gerar código.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
