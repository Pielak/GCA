import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Trash2, Archive, RefreshCw, ShieldAlert,
  CheckCircle2, Clock, ExternalLink, AlertTriangle, X,
} from "lucide-react";
import { api } from "@/services/api";
import { toast } from "react-hot-toast";

interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  methodology: string;
  status: string;
  steps: { step1: boolean; step2: boolean; step3: boolean; step4: boolean };
  created_at: string;
}

const STATUS_LABEL: Record<string, { label: string; className: string }> = {
  active:         { label: "Ativo",        className: "bg-emerald-900/40 text-emerald-300 border border-emerald-700/40" },
  pending_config: { label: "Configurando", className: "bg-yellow-900/40 text-yellow-300 border border-yellow-700/40" },
  archived:       { label: "Arquivado",    className: "bg-gray-700/40 text-gray-400 border border-gray-600/40" },
};

function stepsCompleted(steps: Project["steps"]): number {
  return [steps.step1, steps.step2, steps.step3, steps.step4].filter(Boolean).length;
}

export function AdminProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [projects, setProjects]         = useState<Project[]>([]);
  const [loading, setLoading]           = useState(true);
  const [filter, setFilter]             = useState<string>("all");
  const [confirmId, setConfirmId]       = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const res = await api.get<{ success: boolean; data: Project[] }>("/projects");
      setProjects(res.data.data ?? []);
    } catch {
      toast.error("Não foi possível carregar os projetos.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchProjects(); }, []);

  const handleDelete = async (project: Project) => {
    setActionLoading(project.id);
    try {
      await api.delete(`/projects/${project.id}`);
      toast.success(`Projeto "${project.name}" removido permanentemente.`);
      setProjects((prev) => prev.filter((p) => p.id !== project.id));
      setConfirmId(null);
      // Limpa todo cache React Query para não exibir dados do projeto removido
      queryClient.clear();
    } catch (err: any) {
      const msg = err?.response?.data?.message
        ?? err?.response?.data?.detail
        ?? "Não foi possível remover o projeto. Verifique sua permissão.";
      toast.error(msg);
      setConfirmId(null);
    } finally {
      setActionLoading(null);
    }
  };

  const handleArchive = async (project: Project) => {
    setActionLoading(project.id);
    try {
      const res = await api.patch<{ success: boolean; data: Project }>(`/projects/${project.id}/archive`);
      toast.success(`Projeto "${project.name}" arquivado.`);
      setProjects((prev) => prev.map((p) => p.id === project.id ? res.data.data : p));
    } catch (err: any) {
      const msg = err?.response?.data?.message ?? "Não foi possível arquivar o projeto.";
      toast.error(msg);
    } finally {
      setActionLoading(null);
    }
  };

  const filtered = filter === "all" ? projects : projects.filter((p) => p.status === filter);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert size={22} className="text-violet-400" />
          <h1 className="text-2xl font-bold text-white">Gerenciamento de Projetos</h1>
        </div>
        <button
          onClick={fetchProjects}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <RefreshCw size={14} />
          Atualizar
        </button>
      </div>

      {/* Filtros */}
      <div className="flex gap-2 flex-wrap">
        {["all", "active", "pending_config", "archived"].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              filter === f
                ? "bg-violet-600 text-white"
                : "bg-dark-100 text-gray-400 hover:text-white"
            }`}
          >
            {f === "all" ? "Todos" : STATUS_LABEL[f]?.label ?? f}
          </button>
        ))}
        <span className="ml-auto text-sm text-gray-500 self-center">
          {filtered.length} projeto{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="card text-gray-500 text-sm py-8 text-center">Carregando projetos...</div>
      ) : filtered.length === 0 ? (
        <div className="card text-center text-gray-500 text-sm py-12">Nenhum projeto encontrado.</div>
      ) : (
        <div className="space-y-3">
          {filtered.map((project) => {
            const st = STATUS_LABEL[project.status] ?? { label: project.status, className: "bg-gray-700 text-gray-300 border border-gray-600/40" };
            const steps = stepsCompleted(project.steps);
            const isBusy   = actionLoading === project.id;
            const askConfirm = confirmId === project.id;

            return (
              <div
                key={project.id}
                className={`card border transition-colors ${askConfirm ? "border-red-700/60 bg-red-950/10" : "border-transparent"}`}
              >
                {/* Row principal */}
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  {/* Info */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-white">{project.name}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${st.className}`}>
                        {st.label}
                      </span>
                      <span className="text-xs text-gray-500 capitalize">{project.methodology}</span>
                    </div>
                    {project.description && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate max-w-xl">{project.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        {steps === 4 ? (
                          <CheckCircle2 size={12} className="text-emerald-400" />
                        ) : (
                          <Clock size={12} className="text-yellow-400" />
                        )}
                        Wizard {steps}/4
                      </span>
                      <span>Criado {new Date(project.created_at).toLocaleDateString("pt-BR")}</span>
                    </div>
                  </div>

                  {/* Ações normais */}
                  {!askConfirm && (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => navigate(`/projects/${project.id}/artifacts`)}
                        title="Acessar projeto"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-violet-300 hover:bg-violet-900/20 border border-gray-700 hover:border-violet-700/50 transition-colors"
                      >
                        <ExternalLink size={12} />
                        Abrir
                      </button>
                      {project.status !== "archived" && (
                        <button
                          onClick={() => handleArchive(project)}
                          disabled={isBusy}
                          title="Arquivar projeto"
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-amber-300 hover:bg-amber-900/20 border border-gray-700 hover:border-amber-700/50 transition-colors disabled:opacity-40"
                        >
                          <Archive size={12} />
                          Arquivar
                        </button>
                      )}
                      <button
                        onClick={() => setConfirmId(project.id)}
                        disabled={isBusy}
                        title="Excluir projeto permanentemente"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-red-300 hover:bg-red-900/20 border border-gray-700 hover:border-red-700/50 transition-colors disabled:opacity-40"
                      >
                        <Trash2 size={12} />
                        Excluir
                      </button>
                    </div>
                  )}
                </div>

                {/* Confirmação inline — aparece na própria linha, sem modal */}
                {askConfirm && (
                  <div className="mt-4 pt-4 border-t border-red-800/40 flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-2 text-sm">
                      <AlertTriangle size={16} className="text-red-400 shrink-0" />
                      <span className="text-gray-200">
                        Excluir <strong className="text-white">"{project.name}"</strong> permanentemente?
                        Todos os artefatos, avaliações, código gerado e histórico serão removidos.
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => setConfirmId(null)}
                        disabled={isBusy}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-gray-200 border border-gray-700 transition-colors"
                      >
                        <X size={12} />
                        Cancelar
                      </button>
                      <button
                        onClick={() => handleDelete(project)}
                        disabled={isBusy}
                        className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold text-white bg-red-600 hover:bg-red-700 transition-colors disabled:opacity-50"
                      >
                        {isBusy ? (
                          "Removendo..."
                        ) : (
                          <><Trash2 size={12} /> Confirmar exclusão</>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
