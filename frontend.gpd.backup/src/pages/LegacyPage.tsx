/**
 * Tela de Repositórios Legados — GPD v4.0
 *
 * Funcionalidades:
 * - Solicitar acesso a repositório legado (GP)
 * - Visualizar relatório de análise com IA
 * - Mapa de prioridades de conexão (Alto/Médio/Baixo)
 * - Download do PDF de análise
 */
import { useState } from "react";
import { HelpIcon } from "@/components/HelpIcon";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import {
  Database, Plus, ChevronDown, ChevronUp, AlertTriangle,
  CheckCircle, Clock, FileText, Play, Lock,
} from "lucide-react";
import { api } from "@/services/api";

export function LegacyPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [showAddForm, setShowAddForm] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);
  const qc = useQueryClient();

  const { data: reposData } = useQuery({
    queryKey: ["legacy-repos", projectId],
    queryFn: () => api.get(`/projects/${projectId}/legacy/repos`).then((r) => r.data.data),
  });

  const { data: reportsData } = useQuery({
    queryKey: ["legacy-reports", projectId, selectedRepo],
    queryFn: () =>
      api.get(`/projects/${projectId}/legacy/repos/${selectedRepo}/reports`).then((r) => r.data.data),
    enabled: !!selectedRepo,
  });

  const { data: priorityData } = useQuery({
    queryKey: ["priority-map", projectId, selectedRepo, selectedReport],
    queryFn: () =>
      api
        .get(`/projects/${projectId}/legacy/repos/${selectedRepo}/reports/${selectedReport}/priority-map`)
        .then((r) => r.data.data),
    enabled: !!selectedRepo && !!selectedReport,
  });

  const requestAccess = useMutation({
    mutationFn: (body: any) => api.post(`/projects/${projectId}/legacy/repos`, body),
    onSuccess: () => {
      toast.success("Solicitação enviada! Aguarde aprovação do administrador.");
      qc.invalidateQueries({ queryKey: ["legacy-repos", projectId] });
      setShowAddForm(false);
      reset();
    },
    onError: (e: any) => toast.error(e.response?.data?.message || "Não foi possível enviar a solicitação. Verifique se a URL do repositório é válida e tente novamente."),
  });

  const runAnalysis = useMutation({
    mutationFn: ({ repoId, description }: { repoId: string; description: string }) =>
      api.post(`/projects/${projectId}/legacy/repos/${repoId}/analyze`, {
        project_description: description,
      }),
    onSuccess: () => {
      toast.success("Análise iniciada! Você será notificado quando concluída.");
      qc.invalidateQueries({ queryKey: ["legacy-repos", projectId] });
    },
    onError: (e: any) => toast.error(e.response?.data?.message || "Não foi possível iniciar a análise. Verifique se o acesso ao repositório foi autorizado pelo administrador."),
  });

  const { register, handleSubmit, reset } = useForm<{
    name: string;
    repo_url: string;
    repo_type: string;
    branch: string;
    environment: string;
  }>();

  const repos: any[] = reposData || [];
  const reports: any[] = reportsData || [];

  const statusIcon = (status: string) => {
    switch (status) {
      case "authorized": return <CheckCircle size={14} className="text-emerald-400" />;
      case "pending_auth": return <Clock size={14} className="text-amber-400" />;
      case "analysis_running": return <span className="animate-spin w-3 h-3 border-2 border-violet-400 border-t-transparent rounded-full inline-block" />;
      case "analyzed": return <CheckCircle size={14} className="text-violet-400" />;
      default: return <AlertTriangle size={14} className="text-red-400" />;
    }
  };

  const priorityColor = (priority: string) => {
    if (priority === "high") return "border-red-700 bg-red-900/20";
    if (priority === "medium") return "border-amber-700 bg-amber-900/20";
    return "border-emerald-700 bg-emerald-900/20";
  };

  const priorityBadge = (priority: string) => {
    if (priority === "high") return <span className="badge-high">ALTO</span>;
    if (priority === "medium") return <span className="badge-medium">MÉDIO</span>;
    return <span className="badge-low">BAIXO</span>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Database size={22} className="text-violet-400" />
            Repositórios Legados
            <HelpIcon text="Vincule repositórios legados (Git, SVN, etc.) para análise automática por IA. O GPD gera um mapa de prioridades e plano de migração/integração com o novo sistema." />
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Vincule repositórios legados para análise automática por IA e geração de mapa de prioridades
          </p>
        </div>
        <button onClick={() => setShowAddForm(!showAddForm)} className="btn-primary flex items-center gap-2">
          <Plus size={16} />
          Solicitar Acesso
        </button>
      </div>

      {/* Formulário de solicitação */}
      {showAddForm && (
        <div className="card border-violet-700">
          <h3 className="font-semibold text-white mb-4">Solicitar Acesso a Repositório Legado</h3>
          <div className="mb-3 p-3 bg-amber-900/20 border border-amber-700 rounded-lg text-amber-300 text-sm flex items-start gap-2">
            <Lock size={14} className="mt-0.5 flex-shrink-0" />
            <span>
              O acesso requer aprovação do administrador e expira em <strong>90 dias</strong>.
              O repositório será acessado somente em modo leitura.
            </span>
          </div>
          <form
            onSubmit={handleSubmit((data) => requestAccess.mutate(data))}
            className="grid grid-cols-2 gap-4"
          >
            <div>
              <label className="block text-sm text-gray-300 mb-1">Nome descritivo</label>
              <input {...register("name", { required: true })} className="input-field" placeholder="CRM Legado v2" />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">URL do repositório</label>
              <input {...register("repo_url", { required: true })} className="input-field" placeholder="https://github.com/org/repo" />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Tipo</label>
              <select {...register("repo_type")} className="input-field">
                <option value="github">GitHub</option>
                <option value="gitlab">GitLab</option>
                <option value="bitbucket">Bitbucket</option>
                <option value="azure">Azure Repos</option>
                <option value="svn">SVN</option>
                <option value="local">Local</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Branch</label>
              <input {...register("branch")} className="input-field" placeholder="main" defaultValue="main" />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Ambiente</label>
              <select {...register("environment")} className="input-field">
                <option value="production">Produção</option>
                <option value="homolog">Homologação</option>
                <option value="development">Desenvolvimento</option>
              </select>
            </div>
            <div className="flex items-end gap-2">
              <button type="submit" disabled={requestAccess.isPending} className="btn-primary">
                Solicitar Acesso
              </button>
              <button type="button" onClick={() => setShowAddForm(false)} className="btn-secondary">
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Lista de repositórios */}
      <div className="space-y-3">
        {repos.length === 0 ? (
          <div className="card text-center text-gray-500 py-10">
            Nenhum repositório legado vinculado. Clique em "Solicitar Acesso" para começar.
          </div>
        ) : (
          repos.map((repo: any) => (
            <div key={repo.id} className="card">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {statusIcon(repo.status)}
                  <div>
                    <div className="font-medium text-white">{repo.name}</div>
                    <div className="text-sm text-gray-400">{repo.repo_url}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-500">{repo.environment}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${
                    repo.status === "analyzed" ? "border-violet-600 bg-violet-900/30 text-violet-300"
                    : repo.status === "authorized" ? "border-emerald-600 bg-emerald-900/30 text-emerald-300"
                    : "border-amber-600 bg-amber-900/30 text-amber-300"
                  }`}>
                    {repo.status.replace("_", " ")}
                  </span>

                  {/* Botão de análise (somente se autorizado) */}
                  {(repo.status === "authorized" || repo.status === "analyzed") && (
                    <button
                      onClick={() => {
                        const desc = prompt("Descreva brevemente o novo projeto que usará este legado:");
                        if (desc) runAnalysis.mutate({ repoId: repo.id, description: desc });
                      }}
                      className="flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 border border-violet-700 px-2 py-1 rounded-lg"
                    >
                      <Play size={12} />
                      Analisar
                    </button>
                  )}

                  {/* Ver relatórios */}
                  <button
                    onClick={() => setSelectedRepo(selectedRepo === repo.id ? null : repo.id)}
                    className="text-gray-400 hover:text-gray-200"
                  >
                    {selectedRepo === repo.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>
              </div>

              {/* Relatórios expandidos */}
              {selectedRepo === repo.id && (
                <div className="mt-4 pt-4 border-t border-gray-700">
                  {reports.length === 0 ? (
                    <p className="text-gray-500 text-sm">Nenhuma análise disponível.</p>
                  ) : (
                    <div className="space-y-2">
                      {reports.map((r: any) => (
                        <button
                          key={r.id}
                          onClick={() => setSelectedReport(selectedReport === r.id ? null : r.id)}
                          className="w-full text-left flex items-center justify-between p-3 rounded-lg bg-dark-200 hover:bg-dark-100 transition-colors"
                        >
                          <div className="flex items-center gap-2">
                            <FileText size={14} className="text-violet-400" />
                            <span className="text-sm text-gray-300">
                              Análise de {new Date(r.created_at).toLocaleDateString("pt-BR")}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-xs">
                            <span className="text-red-400">⬤ {r.high_priority_count} alto</span>
                            <span className="text-amber-400">⬤ {r.medium_priority_count} médio</span>
                            <span className="text-emerald-400">⬤ {r.low_priority_count} baixo</span>
                            <span className="text-gray-500">{r.total_files_analyzed} arq.</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Mapa de prioridades */}
      {priorityData && selectedReport && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold text-white text-lg">
              Mapa de Prioridades de Conexão Legado ↔ Novo Projeto
            </h2>
            <div className="flex gap-3 text-sm">
              <span className="text-red-400 font-medium">{priorityData.totals?.high || 0} Alto</span>
              <span className="text-amber-400 font-medium">{priorityData.totals?.medium || 0} Médio</span>
              <span className="text-emerald-400 font-medium">{priorityData.totals?.low || 0} Baixo</span>
              <span className="text-violet-400 font-medium">
                {priorityData.compatibility_score?.toFixed(0)}% compatibilidade
              </span>
            </div>
          </div>

          <p className="text-gray-400 text-sm mb-4">
            Itens classificados por impacto no desenvolvimento do novo projeto.
            Itens de <strong className="text-red-400">alta prioridade</strong> devem ser tratados antes da geração de código.
          </p>

          {/* Itens por prioridade */}
          {["high", "medium", "low"].map((priority) => {
            const items = priorityData.priority_map?.[priority] || [];
            if (items.length === 0) return null;
            return (
              <div key={priority} className="mb-5">
                <h3 className={`text-sm font-semibold mb-3 ${
                  priority === "high" ? "text-red-400" : priority === "medium" ? "text-amber-400" : "text-emerald-400"
                }`}>
                  {priority === "high" ? "🔴 ALTA PRIORIDADE" : priority === "medium" ? "🟡 MÉDIA PRIORIDADE" : "🟢 BAIXA PRIORIDADE"}
                  ({items.length} {items.length === 1 ? "item" : "itens"})
                </h3>
                <div className="space-y-3">
                  {items.map((item: any, i: number) => (
                    <div key={i} className={`p-4 rounded-lg border ${priorityColor(priority)}`}>
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div>
                          {priorityBadge(priority)}
                          <span className="ml-2 text-xs bg-dark px-2 py-0.5 rounded text-gray-400">
                            {item.category?.toUpperCase()}
                          </span>
                        </div>
                        <span className="text-xs text-gray-500">
                          Esforço: {item.effort_estimate === "high" ? "Alto" : item.effort_estimate === "medium" ? "Médio" : "Baixo"}
                        </span>
                      </div>
                      <h4 className="font-medium text-white mb-1">{item.title}</h4>
                      <p className="text-sm text-gray-300 mb-2">{item.description}</p>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-gray-500">No legado: </span>
                          <span className="text-gray-300 font-mono">{item.legacy_location}</span>
                        </div>
                        <div>
                          <span className="text-gray-500">Ação: </span>
                          <span className="text-violet-300">{item.recommended_action}</span>
                        </div>
                      </div>
                      <p className="text-xs text-gray-400 mt-2">
                        <span className="text-gray-500">Impacto no novo projeto: </span>
                        {item.new_project_impact}
                      </p>
                      {item.compliance_risk && (
                        <div className="mt-2 flex items-start gap-1 text-xs text-red-300">
                          <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
                          <span>Risco LGPD/Segurança: {item.compliance_risk}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
