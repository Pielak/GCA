import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  Boxes, FolderOpen, CheckCircle, XCircle, Clock,
  Loader2, ChevronDown, ChevronUp, AlertTriangle, Zap,
} from "lucide-react";
import { clsx } from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";
import { HelpIcon } from "@/components/HelpIcon";

interface ProposedModule {
  id: string;
  name: string;
  module_type: string | null;
  responsibility: string | null;
  priority: string;
  status: "suggested" | "approved" | "rejected" | "generated";
  derived_directory: string | null;
  technical_context: string | null;
  dependency_list: string[];
  readiness: number | null;
  missing_pillars: string[];
  can_generate_stub: boolean;
  evaluation_id: string;
  created_at: string;
}

const PRIORITY_BADGE: Record<string, string> = {
  critical: "bg-red-900/40 text-red-300 border-red-700/50",
  high:     "bg-orange-900/40 text-orange-300 border-orange-700/50",
  medium:   "bg-amber-900/40 text-amber-300 border-amber-700/50",
  low:      "bg-gray-800 text-gray-400 border-gray-700",
};

const STATUS_BADGE: Record<string, string> = {
  suggested: "bg-blue-900/30 text-blue-300 border-blue-700/50",
  approved:  "bg-emerald-900/40 text-emerald-300 border-emerald-700/50",
  rejected:  "bg-red-900/30 text-red-400 border-red-700/50",
  generated: "bg-violet-900/40 text-violet-300 border-violet-700/50",
};

const STATUS_LABEL: Record<string, string> = {
  suggested: "Sugerido", approved: "Aprovado", rejected: "Rejeitado", generated: "Gerado",
};

const CAN_WRITE = ["admin", "project_manager", "tech_lead"];

export function ProposedModulesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const canWrite = CAN_WRITE.includes(user?.role ?? "");
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery<{ success: boolean; data: ProposedModule[] }>({
    queryKey: ["proposed-modules", projectId],
    queryFn: () => api.get(`/projects/${projectId}/modules`).then(r => r.data),
    enabled: !!projectId,
  });

  const approveMutation = useMutation({
    mutationFn: (moduleId: string) =>
      api.post(`/projects/${projectId}/modules/${moduleId}/approve`),
    onSuccess: () => {
      toast.success("Módulo aprovado!");
      queryClient.invalidateQueries({ queryKey: ["proposed-modules", projectId] });
    },
    onError: () => toast.error("Erro ao aprovar módulo."),
  });

  const rejectMutation = useMutation({
    mutationFn: (moduleId: string) =>
      api.post(`/projects/${projectId}/modules/${moduleId}/reject`, { reason: null }),
    onSuccess: () => {
      toast.success("Módulo rejeitado.");
      queryClient.invalidateQueries({ queryKey: ["proposed-modules", projectId] });
    },
    onError: () => toast.error("Erro ao rejeitar módulo."),
  });

  const modules = data?.data ?? [];
  const approvedCount = modules.filter(m => m.status === "approved").length;
  const suggestedCount = modules.filter(m => m.status === "suggested").length;

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-10">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Boxes size={22} className="text-violet-400" />
            Módulos Propostos
            <HelpIcon text="Lista de módulos técnicos gerados automaticamente pelo Gatekeeper com base na documentação do projeto. Revise cada módulo, verifique a prontidão (full/partial/blocked) e aprove os que devem ser gerados. Módulos aprovados ficam disponíveis para seleção no Gerador de Código." />
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Módulos técnicos gerados pelo Gatekeeper. Aprove os que devem ser gerados.
          </p>
        </div>
        {modules.length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <span className="bg-emerald-900/30 text-emerald-400 border border-emerald-700/30 px-2 py-1 rounded-full">
              {approvedCount} aprovado{approvedCount !== 1 ? "s" : ""}
            </span>
            <span className="bg-blue-900/30 text-blue-400 border border-blue-700/30 px-2 py-1 rounded-full">
              {suggestedCount} pendente{suggestedCount !== 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 gap-2 text-gray-500">
          <Loader2 size={18} className="animate-spin" />
          Carregando módulos…
        </div>
      )}

      {isError && (
        <div className="card text-red-400 text-center py-8">
          Erro ao carregar módulos.
        </div>
      )}

      {!isLoading && !isError && modules.length === 0 && (
        <div className="card text-center py-20 space-y-3">
          <Boxes size={40} className="text-gray-600 mx-auto" />
          <p className="text-gray-300 font-medium">Nenhum módulo proposto</p>
          <p className="text-sm text-gray-500 max-w-sm mx-auto">
            Execute o <strong className="text-violet-400">Gatekeeper</strong> para gerar o plano de módulos automaticamente.
          </p>
        </div>
      )}

      {modules.length > 0 && (
        <div className="space-y-2">
          {modules.map((mod) => {
            const isOpen = expanded === mod.id;
            return (
              <div key={mod.id} className={clsx(
                "card transition-opacity",
                mod.status === "rejected" && "opacity-50"
              )}>
                <div className="flex items-center justify-between gap-3">
                  <button
                    className="flex items-center gap-3 min-w-0 flex-1 text-left"
                    onClick={() => setExpanded(isOpen ? null : mod.id)}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-white text-sm">{mod.name}</span>
                        {mod.module_type && (
                          <span className="text-xs text-gray-500 bg-dark-200 px-1.5 py-0.5 rounded">
                            {mod.module_type}
                          </span>
                        )}
                        <span className={clsx(
                          "text-xs px-2 py-0.5 rounded-full border",
                          STATUS_BADGE[mod.status]
                        )}>
                          {STATUS_LABEL[mod.status]}
                        </span>
                        <span className={clsx(
                          "text-xs px-1.5 py-0.5 rounded border",
                          PRIORITY_BADGE[mod.priority] ?? PRIORITY_BADGE.medium
                        )}>
                          {mod.priority}
                        </span>
                        {mod.can_generate_stub && (
                          <span className="flex items-center gap-1 text-xs text-violet-400">
                            <Zap size={10} />
                            stub disponível
                          </span>
                        )}
                      </div>
                      {mod.derived_directory && (
                        <div className="flex items-center gap-1 mt-1 text-xs text-gray-500">
                          <FolderOpen size={11} />
                          <span className="font-mono">{mod.derived_directory}</span>
                        </div>
                      )}
                    </div>
                    <div className="shrink-0 ml-auto mr-2">
                      {mod.readiness !== null && (
                        <span className={clsx(
                          "text-xs font-bold",
                          mod.readiness >= 0.7 ? "text-emerald-400" :
                          mod.readiness >= 0.4 ? "text-amber-400" : "text-red-400"
                        )}>
                          {Math.round(mod.readiness * 100)}%
                        </span>
                      )}
                    </div>
                    {isOpen ? <ChevronUp size={14} className="text-gray-500 shrink-0" /> : <ChevronDown size={14} className="text-gray-500 shrink-0" />}
                  </button>

                  {canWrite && mod.status === "suggested" && (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => approveMutation.mutate(mod.id)}
                        disabled={approveMutation.isPending}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 bg-emerald-700/30 hover:bg-emerald-700/50 text-emerald-300 border border-emerald-700/40 rounded-lg transition-colors disabled:opacity-50"
                      >
                        <CheckCircle size={12} />
                        Aprovar
                      </button>
                      <button
                        onClick={() => rejectMutation.mutate(mod.id)}
                        disabled={rejectMutation.isPending}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 bg-red-900/20 hover:bg-red-900/30 text-red-400 border border-red-700/30 rounded-lg transition-colors disabled:opacity-50"
                      >
                        <XCircle size={12} />
                        Rejeitar
                      </button>
                    </div>
                  )}
                </div>

                {isOpen && (
                  <div className="mt-4 pt-4 border-t border-gray-700/50 space-y-3">
                    {mod.responsibility && (
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Responsabilidade</p>
                        <p className="text-sm text-gray-300">{mod.responsibility}</p>
                      </div>
                    )}
                    {mod.technical_context && (
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Contexto técnico</p>
                        <p className="text-sm text-gray-400 leading-relaxed">{mod.technical_context}</p>
                      </div>
                    )}
                    {mod.missing_pillars.length > 0 && (
                      <div className="flex items-start gap-2">
                        <AlertTriangle size={13} className="text-amber-400 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs text-gray-500 mb-1">Pilares ausentes</p>
                          <div className="flex flex-wrap gap-1">
                            {mod.missing_pillars.map(p => (
                              <span key={p} className="text-xs bg-amber-900/20 text-amber-400 border border-amber-700/30 px-1.5 py-0.5 rounded">
                                {p}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                    {mod.dependency_list.length > 0 && (
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Dependências</p>
                        <div className="flex flex-wrap gap-1">
                          {mod.dependency_list.map((d, i) => (
                            <span key={i} className="text-xs bg-dark-200 text-gray-400 border border-gray-700 px-1.5 py-0.5 rounded font-mono">
                              {d}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="flex items-center gap-1.5 text-xs text-gray-600">
                      <Clock size={11} />
                      Avaliação: {mod.evaluation_id.slice(0, 8)}…
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
