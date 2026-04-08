import { useQuery } from "@tanstack/react-query";
import { HelpIcon } from "@/components/HelpIcon";
import { Link } from "react-router-dom";
import { FolderOpen, Plus, CheckCircle2, Circle, Lock, Inbox } from "lucide-react";
import clsx from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

type ProjectStatus = "pending_config" | "active" | "archived";
type Methodology = "scrum" | "kanban" | "cascata" | "scrumban" | "hybrid";

interface ProjectSteps {
  step1: boolean;
  step2: boolean;
  step3: boolean;
  step4: boolean;
}

interface Project {
  id: string;
  name: string;
  slug: string;
  description: string;
  methodology: Methodology;
  status: ProjectStatus;
  steps: ProjectSteps;
  created_at: string;
}

interface ProjectsResponse {
  success: boolean;
  data: Project[];
}

const METHODOLOGY_LABELS: Record<Methodology, string> = {
  scrum: "Scrum",
  kanban: "Kanban",
  cascata: "Cascata",
  scrumban: "Scrumban",
  hybrid: "Hybrid",
};

const STATUS_CONFIG: Record<ProjectStatus, { label: string; classes: string }> = {
  active: {
    label: "Ativo",
    classes: "bg-emerald-900/40 text-emerald-300 border border-emerald-700/50",
  },
  pending_config: {
    label: "Pendente Config.",
    classes: "bg-amber-900/40 text-amber-300 border border-amber-700/50",
  },
  archived: {
    label: "Arquivado",
    classes: "bg-gray-800/60 text-gray-400 border border-gray-600/50",
  },
};

const CREATE_PROJECT_ROLES = new Set(["admin", "project_manager"]);

function StepIndicators({ steps }: { steps: ProjectSteps }) {
  const stepList = [steps.step1, steps.step2, steps.step3, steps.step4];
  return (
    <div className="flex items-center gap-1.5">
      {stepList.map((done, i) => (
        <div key={i} className="flex items-center gap-1">
          {done ? (
            <CheckCircle2 size={14} className="text-emerald-400" />
          ) : (
            <Circle size={14} className="text-gray-600" />
          )}
          {i < 3 && <div className={clsx("h-px w-4", done ? "bg-emerald-700" : "bg-gray-700")} />}
        </div>
      ))}
      <span className="text-xs text-gray-500 ml-1">
        {stepList.filter(Boolean).length}/4 passos
      </span>
    </div>
  );
}

function ProjectCardSkeleton() {
  return (
    <div className="card animate-pulse space-y-3">
      <div className="flex items-start justify-between">
        <div className="h-5 bg-dark-200 rounded w-2/5" />
        <div className="h-5 bg-dark-200 rounded w-16" />
      </div>
      <div className="h-4 bg-dark-200 rounded w-1/4" />
      <div className="space-y-1.5">
        <div className="h-3 bg-dark-200 rounded w-full" />
        <div className="h-3 bg-dark-200 rounded w-3/4" />
      </div>
      <div className="flex items-center justify-between pt-1">
        <div className="h-4 bg-dark-200 rounded w-36" />
        <div className="h-8 bg-dark-200 rounded w-16" />
      </div>
    </div>
  );
}

function ProjectCard({ project }: { project: Project }) {
  const status = STATUS_CONFIG[project.status];
  return (
    <div className="card flex flex-col gap-3 hover:border-violet-700/50 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-white font-semibold text-base leading-tight">{project.name}</h3>
        <span
          className={clsx(
            "text-xs px-2 py-0.5 rounded-full whitespace-nowrap flex-shrink-0",
            status.classes
          )}
        >
          {status.label}
        </span>
      </div>

      <span className="inline-flex items-center text-xs px-2 py-0.5 rounded-full bg-violet-900/40 text-violet-300 border border-violet-700/50 self-start">
        {METHODOLOGY_LABELS[project.methodology] ?? project.methodology}
      </span>

      {project.description ? (
        <p className="text-sm text-gray-400 line-clamp-2 leading-relaxed">
          {project.description}
        </p>
      ) : (
        <p className="text-sm text-gray-600 italic">Sem descrição</p>
      )}

      <div className="flex items-center justify-between mt-auto pt-1 border-t border-gray-700/50">
        <StepIndicators steps={project.steps} />
        <Link
          to={`/projects/${project.id}/artifacts`}
          className="btn-primary text-sm px-3 py-1.5"
        >
          Abrir
        </Link>
      </div>
    </div>
  );
}

export function ProjectsPage() {
  const user = useAuthStore((s) => s.user);
  const canCreate = user ? CREATE_PROJECT_ROLES.has(user.role) : false;

  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery<ProjectsResponse>({
    queryKey: ["projects"],
    queryFn: async () => {
      const res = await api.get<ProjectsResponse>("/projects");
      return res.data;
    },
  });

  const projects = data?.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <FolderOpen size={22} className="text-violet-400" />
          Projetos
          <HelpIcon text="Gerencie seus projetos GPD. O fluxo de uso de cada projeto é: Artefatos → Consolidação → Gatekeeper → Módulos → Gerador de Código → QA Readiness. Admin e Tech Lead podem criar novos projetos." />
        </h1>
        {canCreate && (
          <Link to="/projects/new" className="btn-primary flex items-center gap-2">
            <Plus size={16} />
            Novo Projeto
          </Link>
        )}
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <ProjectCardSkeleton key={i} />
          ))}
        </div>
      )}

      {isError && (
        <div className="card border-red-700/50 bg-red-900/10 text-red-300 py-6 text-center">
          <p className="font-semibold">Não foi possível carregar os projetos</p>
          <p className="text-sm text-red-400 mt-1">
            {(error as Error)?.message ?? "Verifique sua conexão com a internet e tente recarregar a página. Se o problema persistir, contate o administrador."}
          </p>
        </div>
      )}

      {!isLoading && !isError && projects.length === 0 && (
        <div className="card text-center py-16 flex flex-col items-center gap-3">
          <Inbox size={40} className="text-gray-600" />
          <p className="text-gray-400 font-medium">Nenhum projeto encontrado</p>
          {canCreate ? (
            <p className="text-gray-500 text-sm">
              Comece{" "}
              <Link to="/projects/new" className="text-violet-400 hover:underline">
                criando seu primeiro projeto
              </Link>
              .
            </p>
          ) : (
            <p className="text-gray-500 text-sm">
              Aguarde ser adicionado a um projeto por um administrador ou gerente.
            </p>
          )}
        </div>
      )}

      {!isLoading && !isError && projects.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}
