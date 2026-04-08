/**
 * Módulo 12 — Gestão de Repositórios de Terceiros
 * GPD v4.0 — GitHub, GitLab, Bitbucket
 */
import { useState } from "react";
import { HelpIcon } from "@/components/HelpIcon";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import {
  GitBranch, Plus, Trash2, RefreshCw, ExternalLink,
  GitPullRequest, GitCommit, ChevronDown, ChevronUp, AlertCircle, Info, KeyRound,
  Eye, EyeOff, FileCode,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

// ─── Types ───────────────────────────────────────────────────

type Provider = "github" | "gitlab" | "bitbucket";

interface RepoIntegration {
  id: string;
  provider: Provider;
  owner: string;
  repo_name: string;
  full_name: string;
  default_branch: string;
  web_url: string;
  token_type: string;
  token_expires_at: string | null;
  status: "active" | "expired" | "revoked" | "error";
  last_error: string | null;
  last_sync_at: string | null;
  repo_metadata: Record<string, unknown>;
  linked_modules: unknown[];
  created_at: string;
}

interface PR {
  number: number;
  title: string;
  state: string;
  url: string;
  author: string;
  head_branch: string;
  base_branch: string;
  created_at: string;
}

interface Commit {
  sha: string;
  message: string;
  author: string;
  date: string;
  url: string;
}

// ─── Constants ────────────────────────────────────────────────

const PROVIDER_CONFIG: Record<Provider, { label: string; color: string; icon: string }> = {
  github: { label: "GitHub", color: "bg-gray-800 text-gray-200 border-gray-600", icon: "GH" },
  gitlab: { label: "GitLab", color: "bg-orange-900/40 text-orange-300 border-orange-700/50", icon: "GL" },
  bitbucket: { label: "Bitbucket", color: "bg-blue-900/40 text-blue-300 border-blue-700/50", icon: "BB" },
};

const STATUS_CONFIG = {
  active: { label: "Ativo", classes: "bg-emerald-900/40 text-emerald-300 border border-emerald-700/50" },
  expired: { label: "Token expirado", classes: "bg-red-900/40 text-red-300 border border-red-700/50" },
  revoked: { label: "Revogado", classes: "bg-gray-800/60 text-gray-400 border border-gray-600/50" },
  error: { label: "Erro", classes: "bg-red-900/40 text-red-300 border border-red-700/50" },
};

const WRITE_ROLES = new Set(["admin", "project_manager", "tech_lead"]);

const TOKEN_HINTS: Record<string, { steps: string[]; scopes: string }> = {
  github: {
    steps: [
      "GitHub → Settings → Developer settings → Personal access tokens",
      "Escolha 'Tokens (classic)' ou 'Fine-grained tokens' — ambos funcionam",
      "Permissões mínimas necessárias: repo (leitura e escrita)",
      "Token clássico começa com ghp_  ·  Fine-grained começa com github_pat_",
    ],
    scopes: "repo (Full control of private repositories)",
  },
  gitlab: {
    steps: [
      "GitLab → User Settings → Access Tokens → Add new token",
      "Scopes: read_repository + write_repository",
      "Token começa com glpat-",
    ],
    scopes: "read_repository, write_repository",
  },
  bitbucket: {
    steps: [
      "Bitbucket → Personal settings → App passwords → Create app password",
      "Permissões: Repositories → Read + Write",
      "Use seu nome de usuário + App Password (não sua senha da conta)",
    ],
    scopes: "Repositories: Read, Write",
  },
};

function TokenHint({ provider }: { provider: string }) {
  const hint = TOKEN_HINTS[provider];
  if (!hint) return null;
  return (
    <div className="mt-2 bg-dark-200 border border-gray-700/50 rounded-lg px-3 py-2.5 space-y-1.5">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-400">
        <Info size={12} className="text-violet-400" />
        Como gerar o token
      </div>
      <ol className="space-y-0.5">
        {hint.steps.map((s, i) => (
          <li key={i} className="text-xs text-gray-400 flex gap-1.5">
            <span className="text-violet-500 shrink-0">{i + 1}.</span>
            {s}
          </li>
        ))}
      </ol>
      <p className="text-xs text-gray-600 pt-0.5">
        Scopes: <span className="text-gray-400">{hint.scopes}</span>
      </p>
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────

export function RepoIntegrationsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const qc = useQueryClient();
  const canWrite = user ? WRITE_ROLES.has(user.role) : false;

  const [showForm, setShowForm] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [updatingTokenId, setUpdatingTokenId] = useState<string | null>(null);
  const [newTokenValue, setNewTokenValue] = useState("");

  const { data, isLoading } = useQuery<{ success: boolean; data: RepoIntegration[] }>({
    queryKey: ["repo-integrations", projectId],
    queryFn: () => api.get(`/projects/${projectId}/repo-integrations`).then(r => r.data),
  });

  const { data: prsData } = useQuery<{ success: boolean; data: PR[] }>({
    queryKey: ["repo-prs", projectId, expandedId],
    queryFn: () =>
      api.get(`/projects/${projectId}/repo-integrations/${expandedId}/pulls`).then(r => r.data),
    enabled: !!expandedId,
  });

  const { data: commitsData } = useQuery<{ success: boolean; data: Commit[] }>({
    queryKey: ["repo-commits", projectId, expandedId],
    queryFn: () =>
      api.get(`/projects/${projectId}/repo-integrations/${expandedId}/commits`).then(r => r.data),
    enabled: !!expandedId,
  });

  const connectMutation = useMutation({
    mutationFn: (body: { provider: string; full_name: string; access_token: string }) =>
      api.post(`/projects/${projectId}/repo-integrations`, { ...body, token_type: "pat" }),
    onSuccess: () => {
      toast.success("Repositório conectado com sucesso!");
      qc.invalidateQueries({ queryKey: ["repo-integrations", projectId] });
      setShowForm(false);
      reset();
    },
    onError: (e: any) =>
      toast.error(
        e.response?.data?.detail ||
        "Não foi possível conectar o repositório. Verifique o token e o nome do repositório (owner/repo)."
      ),
  });

  const disconnectMutation = useMutation({
    mutationFn: (id: string) =>
      api.delete(`/projects/${projectId}/repo-integrations/${id}`),
    onSuccess: () => {
      toast.success("Integração removida.");
      qc.invalidateQueries({ queryKey: ["repo-integrations", projectId] });
      setExpandedId(null);
    },
    onError: () => toast.error("Não foi possível remover a integração. Tente novamente."),
  });

  const updateTokenMutation = useMutation({
    mutationFn: ({ id, token }: { id: string; token: string }) =>
      api.patch(`/projects/${projectId}/repo-integrations/${id}/token`, { access_token: token }),
    onSuccess: () => {
      toast.success("Token atualizado com sucesso!");
      qc.invalidateQueries({ queryKey: ["repo-integrations", projectId] });
      setUpdatingTokenId(null);
      setNewTokenValue("");
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail ?? "Token inválido ou sem acesso ao repositório."),
  });

  const { register, handleSubmit, reset, watch } = useForm<{
    provider: Provider;
    full_name: string;
    access_token: string;
  }>({ defaultValues: { provider: "github" } });

  const integrations = data?.data ?? [];

  const handleSync = async (id: string) => {
    setSyncingId(id);
    try {
      await api.post(`/projects/${projectId}/repo-integrations/${id}/sync`);
      qc.invalidateQueries({ queryKey: ["repo-integrations", projectId] });
      qc.invalidateQueries({ queryKey: ["repo-prs", projectId, id] });
      qc.invalidateQueries({ queryKey: ["repo-commits", projectId, id] });
      toast.success("Repositório sincronizado.");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Não foi possível sincronizar. Verifique se o token ainda é válido.");
    } finally {
      setSyncingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <GitBranch size={22} className="text-violet-400" />
          Repositório do Projeto
          <HelpIcon text="Conecte repositórios GitHub, GitLab ou Bitbucket via PAT ou OAuth. Visualize PRs, commits e vincule módulos gerados pelo GPD a branches e pull requests." />
        </h1>
        {canWrite && (
          <button onClick={() => setShowForm(!showForm)} className="btn-primary flex items-center gap-2">
            <Plus size={16} />
            Conectar Repositório
          </button>
        )}
      </div>

      {/* Form */}
      {showForm && canWrite && (
        <div className="card border-violet-700/50">
          <h3 className="font-semibold text-white mb-4">Conectar Repositório</h3>
          <form
            onSubmit={handleSubmit(d => connectMutation.mutate(d))}
            className="space-y-4"
          >
            {/* Provider */}
            <div>
              <label className="block text-sm text-gray-300 mb-1">Provedor</label>
              <select {...register("provider")} className="input-field">
                <option value="github">GitHub</option>
                <option value="gitlab">GitLab</option>
                <option value="bitbucket">Bitbucket</option>
              </select>
            </div>

            {/* Repositório */}
            <div>
              <label className="block text-sm text-gray-300 mb-1">Repositório</label>
              <input
                {...register("full_name", { required: true })}
                className="input-field font-mono"
                placeholder="owner/repo ou https://github.com/owner/repo.git"
              />
              <p className="text-xs text-gray-500 mt-1">
                Aceita <span className="text-violet-400">owner/repo</span> ou a URL completa do repositório.
              </p>
            </div>

            {/* Token */}
            <div>
              <label className="block text-sm text-gray-300 mb-1">Token de acesso</label>
              <div className="relative">
                <input
                  {...register("access_token", { required: true })}
                  type={showToken ? "text" : "password"}
                  className="input-field font-mono pr-10"
                  placeholder={
                    watch("provider") === "github" ? "ghp_... ou github_pat_..." :
                    watch("provider") === "gitlab" ? "glpat-..." :
                    "App Password do Bitbucket"
                  }
                />
                <button
                  type="button"
                  onClick={() => setShowToken(!showToken)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300 transition-colors"
                  title={showToken ? "Ocultar token" : "Mostrar token"}
                >
                  {showToken ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              <TokenHint provider={watch("provider")} />
            </div>

            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                disabled={connectMutation.isPending}
                className="btn-primary disabled:opacity-50"
              >
                {connectMutation.isPending ? "Conectando..." : "Conectar"}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="text-gray-500 text-sm animate-pulse py-8 text-center">
          Carregando integrações...
        </div>
      ) : integrations.length === 0 ? (
        <div className="card text-center py-16 text-gray-500">
          <GitBranch size={36} className="mx-auto mb-3 text-gray-700" />
          <p>Nenhum repositório conectado.</p>
          {canWrite && (
            <p className="text-sm mt-1">
              Clique em{" "}
              <button
                className="text-violet-400 hover:underline"
                onClick={() => setShowForm(true)}
              >
                Conectar Repositório
              </button>{" "}
              para começar.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {integrations.map(integration => {
            const provCfg = PROVIDER_CONFIG[integration.provider];
            const statusCfg = STATUS_CONFIG[integration.status];
            const isExpanded = expandedId === integration.id;
            const prs = prsData?.data ?? [];
            const commits = commitsData?.data ?? [];

            return (
              <div key={integration.id} className="card">
                {/* Header row */}
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span
                      className={clsx(
                        "w-9 h-9 rounded-lg flex items-center justify-center text-xs font-bold border",
                        provCfg.color
                      )}
                    >
                      {provCfg.icon}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white">{integration.full_name}</span>
                        <a
                          href={integration.web_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-gray-500 hover:text-violet-400"
                        >
                          <ExternalLink size={12} />
                        </a>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs text-gray-500">{provCfg.label}</span>
                        <span className="text-gray-700">·</span>
                        <span className="text-xs text-gray-500">branch: {integration.default_branch}</span>
                        {integration.last_sync_at && (
                          <>
                            <span className="text-gray-700">·</span>
                            <span className="text-xs text-gray-500">
                              sync: {new Date(integration.last_sync_at).toLocaleString("pt-BR")}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className={clsx("text-xs px-2 py-0.5 rounded-full", statusCfg.classes)}>
                      {statusCfg.label}
                    </span>

                    <button
                      onClick={() => handleSync(integration.id)}
                      disabled={syncingId === integration.id}
                      title="Sincronizar"
                      className="p-1.5 text-gray-500 hover:text-violet-400 disabled:opacity-40"
                    >
                      <RefreshCw
                        size={14}
                        className={syncingId === integration.id ? "animate-spin" : ""}
                      />
                    </button>

                    <button
                      onClick={() => navigate(`/projects/${projectId}/repos/${integration.id}/files`)}
                      title="Ver e editar arquivos"
                      className="p-1.5 text-gray-500 hover:text-blue-400 transition-colors"
                    >
                      <FileCode size={14} />
                    </button>

                    {canWrite && (
                      <>
                        <button
                          onClick={() => {
                            setUpdatingTokenId(updatingTokenId === integration.id ? null : integration.id);
                            setNewTokenValue("");
                          }}
                          title="Atualizar token de acesso"
                          className={clsx(
                            "p-1.5 transition-colors",
                            updatingTokenId === integration.id
                              ? "text-amber-400"
                              : "text-gray-500 hover:text-amber-400"
                          )}
                        >
                          <KeyRound size={14} />
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Remover integração com ${integration.full_name}?`)) {
                              disconnectMutation.mutate(integration.id);
                            }
                          }}
                          title="Remover integração"
                          className="p-1.5 text-gray-500 hover:text-red-400"
                        >
                          <Trash2 size={14} />
                        </button>
                      </>
                    )}

                    <button
                      onClick={() => setExpandedId(isExpanded ? null : integration.id)}
                      className="text-gray-500 hover:text-gray-200"
                    >
                      {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                  </div>
                </div>

                {/* Error message */}
                {integration.last_error && (
                  <div className="mt-3 flex items-start gap-2 text-xs text-red-300 bg-red-900/20 border border-red-700/30 rounded-lg px-3 py-2">
                    <AlertCircle size={12} className="mt-0.5 flex-shrink-0" />
                    {integration.last_error}
                  </div>
                )}

                {/* Update token inline panel */}
                {updatingTokenId === integration.id && (
                  <div className="mt-3 flex gap-2 items-center p-3 bg-amber-900/10 border border-amber-700/30 rounded-lg">
                    <KeyRound size={13} className="text-amber-400 shrink-0" />
                    <input
                      type="password"
                      className="flex-1 bg-dark border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 font-mono focus:outline-none focus:border-amber-600"
                      placeholder="Cole o novo PAT (ghp_... ou token OAuth)"
                      value={newTokenValue}
                      onChange={(e) => setNewTokenValue(e.target.value)}
                      autoFocus
                    />
                    <button
                      className="text-xs px-3 py-1 rounded bg-amber-700/30 text-amber-300 border border-amber-700/50 hover:bg-amber-700/50 disabled:opacity-50 whitespace-nowrap"
                      disabled={!newTokenValue.trim() || updateTokenMutation.isPending}
                      onClick={() => updateTokenMutation.mutate({ id: integration.id, token: newTokenValue.trim() })}
                    >
                      {updateTokenMutation.isPending ? "Salvando…" : "Salvar token"}
                    </button>
                    <button
                      className="text-xs text-gray-500 hover:text-gray-300"
                      onClick={() => { setUpdatingTokenId(null); setNewTokenValue(""); }}
                    >
                      Cancelar
                    </button>
                  </div>
                )}

                {/* Expanded: PRs + Commits */}
                {isExpanded && (
                  <div className="mt-4 pt-4 border-t border-gray-700 grid grid-cols-2 gap-6">
                    {/* Pull Requests */}
                    <div>
                      <h4 className="flex items-center gap-1.5 text-sm font-semibold text-gray-200 mb-3">
                        <GitPullRequest size={14} className="text-violet-400" />
                        Pull Requests abertos ({prs.length})
                      </h4>
                      {prs.length === 0 ? (
                        <p className="text-xs text-gray-500">Nenhum PR aberto.</p>
                      ) : (
                        <div className="space-y-2">
                          {prs.map(pr => (
                            <a
                              key={pr.number}
                              href={pr.url}
                              target="_blank"
                              rel="noreferrer"
                              className="block p-2 rounded-lg bg-dark-200 hover:bg-dark-100 transition-colors"
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-xs text-violet-400">#{pr.number}</span>
                                <span className="text-xs text-gray-500">{pr.author}</span>
                              </div>
                              <p className="text-xs text-gray-300 mt-0.5 line-clamp-1">{pr.title}</p>
                              <p className="text-xs text-gray-600 mt-0.5">
                                {pr.head_branch} → {pr.base_branch}
                              </p>
                            </a>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Commits */}
                    <div>
                      <h4 className="flex items-center gap-1.5 text-sm font-semibold text-gray-200 mb-3">
                        <GitCommit size={14} className="text-violet-400" />
                        Commits recentes
                      </h4>
                      {commits.length === 0 ? (
                        <p className="text-xs text-gray-500">Nenhum commit encontrado.</p>
                      ) : (
                        <div className="space-y-2">
                          {commits.slice(0, 8).map(commit => (
                            <a
                              key={commit.sha}
                              href={commit.url}
                              target="_blank"
                              rel="noreferrer"
                              className="block p-2 rounded-lg bg-dark-200 hover:bg-dark-100 transition-colors"
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-mono text-amber-400">{commit.sha}</span>
                                <span className="text-xs text-gray-500">
                                  {new Date(commit.date).toLocaleDateString("pt-BR")}
                                </span>
                              </div>
                              <p className="text-xs text-gray-300 mt-0.5 line-clamp-1">{commit.message}</p>
                              <p className="text-xs text-gray-600">{commit.author}</p>
                            </a>
                          ))}
                        </div>
                      )}
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
