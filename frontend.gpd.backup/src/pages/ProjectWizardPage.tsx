import { useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  Lock, ChevronRight, ChevronLeft, Check, Wand2, UserPlus, X, Mail,
  CheckCircle, Eye, EyeOff, Link2, ExternalLink, Loader2, Info,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/services/api";
import { HelpIcon } from "@/components/HelpIcon";

// ─── Schemas ────────────────────────────────────────────────────────────────

const step1Schema = z.object({
  name: z.string().min(3, "O nome do projeto deve ter ao menos 3 caracteres").max(100),
  description: z.string().max(500).optional(),
  methodology: z.enum(["scrum", "kanban", "cascata", "scrumban", "hybrid"], {
    required_error: "Selecione a metodologia ágil que o projeto irá adotar",
  }),
});

const step2Schema = z.object({
  alm_tool: z.enum(["jira", "azuredevops", "github", "trello", "asana"], {
    required_error: "Selecione a ferramenta de gerenciamento de tarefas do projeto (ex: Jira, Azure DevOps)",
  }),
  alm_url: z.string().url("Informe uma URL válida começando com https://").optional().or(z.literal("")),
  server_url: z.string().url("Informe uma URL válida começando com https://").optional().or(z.literal("")),
  primary_language: z.string().min(1, "Informe a linguagem de programação principal (ex: TypeScript, Python, Java)"),
});

const step3Schema = z.object({
  ai_provider: z.enum(["anthropic", "openai", "gemini"], {
    required_error: "Selecione qual provedor de IA irá gerar o código do projeto",
  }),
  ai_model: z.string().min(1, "Informe o nome exato do modelo de IA (ex: claude-sonnet-4-5, gpt-4o)"),
  code_language: z.enum(["pt-BR", "en", "es"], {
    required_error: "Selecione o idioma para comentários e documentação gerada",
  }),
  comment_style: z.enum(["docstrings", "jsdoc", "javadoc", "xml", "none"], {
    required_error: "Selecione o padrão de documentação compatível com a linguagem escolhida",
  }),
  custom_prompt: z.string().max(2000, "O prompt customizado deve ter no máximo 2000 caracteres.").optional(),
  generate_readme: z.boolean().optional(),
  generate_unit_tests: z.boolean().optional(),
});

type Step1Values = z.infer<typeof step1Schema>;
type Step2Values = z.infer<typeof step2Schema>;
type Step3Values = z.infer<typeof step3Schema>;

interface ConnectedRepo {
  id: string;
  provider: string;
  full_name: string;
  default_branch: string;
  web_url: string;
  status: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STEP_LABELS = [
  "Informações do Projeto",
  "Stack Técnica",
  "Repositório",
  "Configuração de IA",
  "Equipe",
];

const PROVIDER_NAMES: Record<string, string> = {
  github:    "GitHub",
  gitlab:    "GitLab",
  bitbucket: "Bitbucket",
};

const PROVIDER_ICONS: Record<string, string> = {
  github:    "🐙",
  gitlab:    "🦊",
  bitbucket: "🪣",
};

const PROVIDER_TOKEN_HINTS: Record<string, string> = {
  github:    "GitHub: Settings → Developer settings → Personal access tokens → Tokens (classic) ou Fine-grained · Scopes mínimos: repo",
  gitlab:    "GitLab: User Settings → Access Tokens · Scopes: read_repository + write_repository",
  bitbucket: "Bitbucket: Personal settings → App passwords · Permissões: Repositories Read + Write (use App Password, não a senha da conta)",
};

const AI_MODELS: Record<string, string[]> = {
  anthropic: ["claude-sonnet-4-6", "claude-opus-4-6", "claude-sonnet-4-5", "claude-haiku-4-5-20251001"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
  gemini: ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
};

const MEMBER_ROLES = [
  { value: "developer", label: "Desenvolvedor" },
  { value: "tech_lead", label: "Tech Lead" },
  { value: "product_owner", label: "Product Owner" },
  { value: "scrum_master", label: "Scrum Master" },
  { value: "qa_engineer", label: "QA Engineer" },
  { value: "viewer", label: "Visualizador" },
];

// ─── Types ───────────────────────────────────────────────────────────────────

interface Member {
  user_id: string;
  name: string;
  email: string;
  role: string;
}

interface AvailableUser {
  id: string;
  name: string;
  email: string;
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function Stepper({ current }: { current: number }) {
  return (
    <div className="flex items-center justify-center mb-8">
      {STEP_LABELS.map((label, i) => {
        const step = i + 1;
        const isActive = step === current;
        const isDone = step < current;
        const isFuture = step > current;
        return (
          <div key={step} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={clsx(
                  "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors",
                  isActive && "bg-violet-600 text-white",
                  isDone && "bg-emerald-600 text-white",
                  isFuture && "bg-dark-200 text-gray-500 border border-gray-600"
                )}
              >
                {isDone ? <Check size={14} /> : step}
              </div>
              <span
                className={clsx(
                  "text-xs font-medium hidden sm:block",
                  isActive && "text-violet-300",
                  isDone && "text-emerald-400",
                  isFuture && "text-gray-600"
                )}
              >
                {label}
              </span>
            </div>
            {i < STEP_LABELS.length - 1 && (
              <div
                className={clsx(
                  "h-px w-12 sm:w-20 mx-1 mb-5",
                  step < current ? "bg-emerald-700" : "bg-gray-700"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function ImmutableWarning() {
  return (
    <div className="flex items-start gap-2 bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-3 mb-4 text-amber-300 text-sm">
      <Lock size={16} className="mt-0.5 flex-shrink-0" />
      <span>
        <strong>Atenção:</strong> As informações deste passo são <strong>imutáveis</strong> após
        salvas. Revise cuidadosamente antes de avançar.
      </span>
    </div>
  );
}

// ─── Step 1 ──────────────────────────────────────────────────────────────────

function Step1Form({
  onNext,
}: {
  onNext: (values: Step1Values) => void;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Step1Values>({
    resolver: zodResolver(step1Schema),
    defaultValues: { methodology: "scrum" },
  });

  return (
    <form onSubmit={handleSubmit(onNext)} className="space-y-4">
      <div>
        <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
          Nome do Projeto <span className="text-red-400">*</span>
          <HelpIcon text="Nome único do projeto no GPD. Será usado como identificador em relatórios, artefatos e código gerado. Escolha um nome descritivo e sem ambiguidades — ex: 'Portal do Cliente v2', 'API de Pagamentos'. Não pode ser alterado após criação." />
        </label>
        <input
          {...register("name")}
          className="input-field"
          placeholder="Ex.: Portal do Cliente"
        />
        {errors.name && <p className="text-red-400 text-xs mt-1">{errors.name.message}</p>}
      </div>

      <div>
        <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
          Descrição
          <HelpIcon text="Resumo do objetivo do projeto. Será usado pelo Gatekeeper como contexto ao avaliar artefatos e gerar código. Quanto mais detalhada, melhor a qualidade das análises automáticas de requisitos e da geração de código." />
        </label>
        <textarea
          {...register("description")}
          className="input-field resize-none"
          rows={3}
          placeholder="Descreva brevemente o projeto..."
        />
        {errors.description && (
          <p className="text-red-400 text-xs mt-1">{errors.description.message}</p>
        )}
      </div>

      <div>
        <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
          Metodologia <span className="text-red-400">*</span>
          <HelpIcon text="A metodologia define como o GPD organiza artefatos e cerimônias esperadas. Scrum: sprints com papéis definidos (PO, SM, Dev). Kanban: fluxo contínuo, sem sprints. Cascata: fases sequenciais (levantamento → design → build → teste). Scrumban: híbrido Scrum+Kanban. Hybrid: mistura customizada definida pela equipe." />
        </label>
        <select {...register("methodology")} className="input-field">
          <option value="scrum">Scrum</option>
          <option value="kanban">Kanban</option>
          <option value="cascata">Cascata</option>
          <option value="scrumban">Scrumban</option>
          <option value="hybrid">Hybrid</option>
        </select>
        {errors.methodology && (
          <p className="text-red-400 text-xs mt-1">{errors.methodology.message}</p>
        )}
      </div>

      <div className="flex justify-end pt-2">
        <button type="submit" className="btn-primary flex items-center gap-2">
          Avançar <ChevronRight size={16} />
        </button>
      </div>
    </form>
  );
}

// ─── Step 2 ──────────────────────────────────────────────────────────────────

function Step2Form({
  projectId,
  onNext,
  onBack,
}: {
  projectId: string;
  onNext: () => void;
  onBack: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Step2Values>({
    resolver: zodResolver(step2Schema),
  });

  const onSubmit = async (values: Step2Values) => {
    setSaving(true);
    try {
      const body: Record<string, string | undefined> = {
        alm_tool: values.alm_tool,
        primary_language: values.primary_language,
      };
      if (values.alm_url) body.alm_url = values.alm_url;
      if (values.server_url) body.server_url = values.server_url;

      await api.patch(`/projects/${projectId}/step2`, body);
      toast.success("Stack técnica salva!");
      onNext();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
        "Não foi possível salvar a stack técnica. Verifique se as URLs informadas são válidas e tente novamente.";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <ImmutableWarning />

      <div>
        <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
          Ferramenta ALM <span className="text-red-400">*</span>
          <HelpIcon text="ALM (Application Lifecycle Management) é onde as tarefas e histórias do projeto são rastreadas. Jira é o mais comum em equipes ágeis. Azure DevOps integra código, pipeline e backlog em um só lugar. GitHub Projects é gratuito e simples para equipes menores. Trello e Asana são mais visuais, sem suporte nativo a sprints." />
        </label>
        <select {...register("alm_tool")} className="input-field">
          <option value="">Selecione...</option>
          <option value="jira">Jira</option>
          <option value="azuredevops">Azure DevOps</option>
          <option value="github">GitHub Projects</option>
          <option value="trello">Trello</option>
          <option value="asana">Asana</option>
        </select>
        {errors.alm_tool && (
          <p className="text-red-400 text-xs mt-1">{errors.alm_tool.message}</p>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
            URL do ALM
            <HelpIcon text="Endereço da sua instância da ferramenta ALM. Ex.: https://suaempresa.atlassian.net para Jira Cloud, https://dev.azure.com/suaorganizacao para Azure DevOps. Deixe em branco se usar a instância pública gratuita ou se a ferramenta não tiver URL própria." />
          </label>
          <input
            {...register("alm_url")}
            className="input-field"
            placeholder="https://..."
          />
          {errors.alm_url && (
            <p className="text-red-400 text-xs mt-1">{errors.alm_url.message}</p>
          )}
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
            URL do Servidor
            <HelpIcon text="URL do servidor de desenvolvimento, staging ou produção onde a aplicação será publicada. O GPD usa esta informação para gerar configurações de deploy e documentação de infraestrutura. Ex.: https://api.suaempresa.com ou http://192.168.1.100:8080 para ambiente interno." />
          </label>
          <input
            {...register("server_url")}
            className="input-field"
            placeholder="https://..."
          />
          {errors.server_url && (
            <p className="text-red-400 text-xs mt-1">{errors.server_url.message}</p>
          )}
        </div>
      </div>

      <div>
        <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
          Linguagem Principal <span className="text-red-400">*</span>
          <HelpIcon text="Linguagem de programação primária do projeto. O Gerador de Código usará esta informação para escolher frameworks, padrões de projeto e estilo de código adequados. Ex.: TypeScript (para React/Node), Python (FastAPI/Django), Java (Spring Boot), C# (.NET). Seja específico — evite respostas genéricas como 'web'." />
        </label>
        <input
          {...register("primary_language")}
          className="input-field"
          placeholder="Ex.: TypeScript, Python, Java..."
        />
        {errors.primary_language && (
          <p className="text-red-400 text-xs mt-1">{errors.primary_language.message}</p>
        )}
      </div>

      <div className="flex justify-between pt-2">
        <button type="button" onClick={onBack} className="btn-secondary flex items-center gap-2">
          <ChevronLeft size={16} /> Voltar
        </button>
        <button
          type="submit"
          className="btn-primary flex items-center gap-2"
          disabled={saving}
        >
          {saving ? "Salvando..." : "Avançar"} <ChevronRight size={16} />
        </button>
      </div>
    </form>
  );
}

// ─── Step 3 — Repositório ─────────────────────────────────────────────────────

function Step3RepoForm({
  projectId,
  onNext,
  onBack,
}: {
  projectId: string;
  onNext: () => void;
  onBack: () => void;
}) {
  const [provider, setProvider] = useState<"github" | "gitlab" | "bitbucket">("github");
  const [fullName, setFullName] = useState("");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [gitlabBaseUrl, setGitlabBaseUrl] = useState("https://gitlab.com");
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState<ConnectedRepo | null>(null);
  const [loadingExisting, setLoadingExisting] = useState(true);

  useEffect(() => {
    api.get(`/projects/${projectId}/repo-integrations`)
      .then((res) => {
        const repos: ConnectedRepo[] = res.data?.data ?? [];
        if (repos.length > 0) setConnected(repos[0]);
      })
      .catch(() => {})
      .finally(() => setLoadingExisting(false));
  }, [projectId]);

  const handleConnect = async () => {
    if (!fullName.trim() || !token.trim()) {
      toast.error("Preencha o repositório e o token de acesso.");
      return;
    }
    setConnecting(true);
    try {
      const body: Record<string, string> = {
        provider,
        full_name: fullName.trim(),
        access_token: token.trim(),
        token_type: "pat",
      };
      if (provider === "gitlab" && gitlabBaseUrl.trim() !== "https://gitlab.com") {
        body.gitlab_base_url = gitlabBaseUrl.trim();
      }
      const res = await api.post(`/projects/${projectId}/repo-integrations`, body);
      setConnected(res.data.data as ConnectedRepo);
      setToken("");
      toast.success("Repositório conectado com sucesso!");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string; message?: string } } })
          ?.response?.data?.detail ??
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
        "Não foi possível conectar. Verifique o repositório e o token.";
      toast.error(detail);
    } finally {
      setConnecting(false);
    }
  };

  if (loadingExisting) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 size={20} className="animate-spin text-violet-400" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-2 bg-blue-900/15 border border-blue-800/30 rounded-lg px-4 py-3">
        <Info size={14} className="text-blue-400 mt-0.5 shrink-0" />
        <p className="text-sm text-blue-300">
          O repositório é <strong>obrigatório</strong> — é onde o GPD fará push do código gerado.
          Configure um token com permissão de escrita antes de continuar.
        </p>
      </div>

      {connected ? (
        <div className="bg-emerald-900/20 border border-emerald-700/40 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2 text-emerald-400 font-semibold text-sm">
            <CheckCircle size={16} /> Repositório conectado
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Provedor</p>
              <p className="text-gray-200 capitalize">{PROVIDER_ICONS[connected.provider]} {PROVIDER_NAMES[connected.provider]}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Repositório</p>
              <p className="text-gray-200 font-mono text-xs">{connected.full_name}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Branch padrão</p>
              <p className="text-gray-200 font-mono text-xs">{connected.default_branch}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Status</p>
              <p className="text-emerald-400 text-xs capitalize">{connected.status}</p>
            </div>
          </div>
          {connected.web_url && (
            <a
              href={connected.web_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-violet-400 hover:underline flex items-center gap-1"
            >
              <ExternalLink size={11} /> Abrir repositório
            </a>
          )}
          <button
            type="button"
            onClick={() => setConnected(null)}
            className="text-xs text-gray-500 hover:text-red-400 transition-colors"
          >
            Trocar repositório
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Provider selector */}
          <div>
            <label className="block text-sm text-gray-300 mb-2 flex items-center gap-1">
              Provedor <span className="text-red-400">*</span>
              <HelpIcon text="GitHub é o mais popular e melhor suportado pelo GPD — recomendado para novos projetos. GitLab oferece CI/CD integrado e opção de instância própria (self-hosted), ideal para empresas com política de dados internos. Bitbucket é comum em equipes que usam o ecossistema Atlassian com Jira." />
            </label>
            <div className="flex gap-2">
              {(["github", "gitlab", "bitbucket"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setProvider(p)}
                  className={clsx(
                    "flex-1 py-2 px-2 rounded-lg border text-sm font-medium transition-colors",
                    provider === p
                      ? "bg-violet-600/20 border-violet-500 text-violet-300"
                      : "border-gray-700 text-gray-400 hover:border-gray-500"
                  )}
                >
                  {PROVIDER_ICONS[p]} {PROVIDER_NAMES[p]}
                </button>
              ))}
            </div>
          </div>

          {/* Repository full name */}
          <div>
            <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
              Repositório <span className="text-red-400">*</span>
              <HelpIcon text="Nome completo do repositório no formato owner/repo. Ex.: minha-empresa/portal-cliente ou joaosilva/meu-app. O repositório já deve existir na plataforma escolhida. O token informado deve ter permissão de escrita (push) — caso contrário o GPD não conseguirá enviar o código gerado." />
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="input-field font-mono"
              placeholder="owner/repo ou https://github.com/owner/repo.git"
            />
            <p className="text-xs text-gray-500 mt-1">
              Aceita <span className="text-violet-400">owner/repo</span> ou a URL completa (.git incluso ou não).
            </p>
          </div>

          {/* GitLab self-hosted URL */}
          {provider === "gitlab" && (
            <div>
              <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
                URL base do GitLab
                <HelpIcon text="Mantenha https://gitlab.com para GitLab Cloud (padrão). Se sua empresa usa uma instância própria (on-premises ou self-managed), informe o endereço aqui. Ex.: https://gitlab.suaempresa.com. Certifique-se de incluir o https:// e sem barra no final." />
              </label>
              <input
                type="url"
                value={gitlabBaseUrl}
                onChange={(e) => setGitlabBaseUrl(e.target.value)}
                className="input-field"
                placeholder="https://gitlab.com"
              />
              <p className="text-xs text-gray-500 mt-1">Mantenha para GitLab.com ou use sua instância self-hosted.</p>
            </div>
          )}

          {/* Access token */}
          <div>
            <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
              Token de acesso <span className="text-red-400">*</span>
              <HelpIcon text="Chave de autenticação com permissão de escrita no repositório. NUNCA compartilhe este token. GitHub: crie em Settings → Developer settings → Personal access tokens → Fine-grained, com escopo de Contents (read & write) apenas no repositório deste projeto. GitLab: User Settings → Access Tokens com scopes read_repository + write_repository. Bitbucket: Personal settings → App passwords (NÃO use a senha da conta)." />
            </label>
            <div className="relative">
              <input
                type={showToken ? "text" : "password"}
                value={token}
                onChange={(e) => setToken(e.target.value)}
                className="input-field font-mono pr-10"
                placeholder={
                  provider === "github" ? "ghp_... ou github_pat_..." :
                  provider === "gitlab" ? "glpat-..." : "App Password do Bitbucket"
                }
              />
              <button
                type="button"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                onClick={() => setShowToken((s) => !s)}
              >
                {showToken ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">{PROVIDER_TOKEN_HINTS[provider]}</p>
          </div>

          <button
            type="button"
            onClick={handleConnect}
            disabled={connecting || !fullName.trim() || !token.trim()}
            className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-40"
          >
            {connecting
              ? <><Loader2 size={14} className="animate-spin" /> Conectando...</>
              : <><Link2 size={14} /> Conectar Repositório</>
            }
          </button>
        </div>
      )}

      <div className="flex justify-between pt-2">
        <button type="button" onClick={onBack} className="btn-secondary flex items-center gap-2">
          <ChevronLeft size={16} /> Voltar
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={!connected}
          title={!connected ? "Conecte um repositório para continuar" : undefined}
          className="btn-primary flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Avançar <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

// ─── Agent Config types ───────────────────────────────────────────────────────

interface AgentItemState {
  ativo: boolean;
  provider: string;
  model: string;
}

interface AgentConfigState {
  arquiteto: AgentItemState;
  desenvolvedor: AgentItemState;
  revisor: AgentItemState;
  integrador: AgentItemState;
}

const AGENT_LABELS: Record<keyof AgentConfigState, { label: string; alwaysActive: boolean }> = {
  arquiteto:    { label: "Arquiteto",    alwaysActive: true },
  desenvolvedor:{ label: "Desenvolvedor",alwaysActive: true },
  revisor:      { label: "Revisor",      alwaysActive: false },
  integrador:   { label: "Integrador",   alwaysActive: false },
};

const defaultAgentItem = (): AgentItemState => ({ ativo: true, provider: "anthropic", model: "" });

// ─── Step 4 — Configuração de IA ─────────────────────────────────────────────

function Step4IAForm({
  projectId,
  onNext,
  onBack,
}: {
  projectId: string;
  onNext: () => void;
  onBack: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [agentConfig, setAgentConfig] = useState<AgentConfigState>({
    arquiteto:     defaultAgentItem(),
    desenvolvedor: defaultAgentItem(),
    revisor:       defaultAgentItem(),
    integrador:    defaultAgentItem(),
  });

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<Step3Values>({
    resolver: zodResolver(step3Schema),
    defaultValues: {
      code_language: "pt-BR",
      comment_style: "docstrings",
      generate_readme: true,
      generate_unit_tests: false,
    },
  });

  const selectedProvider = watch("ai_provider");
  const suggestedModels = selectedProvider ? AI_MODELS[selectedProvider] ?? [] : [];

  const updateAgent = (
    agent: keyof AgentConfigState,
    field: keyof AgentItemState,
    value: string | boolean
  ) => {
    setAgentConfig((prev) => ({
      ...prev,
      [agent]: { ...prev[agent], [field]: value },
    }));
  };

  const onSubmit = async (values: Step3Values) => {
    setSaving(true);
    try {
      await api.patch(`/projects/${projectId}/step3`, values);

      // Save agent config (best-effort; non-blocking for wizard progression)
      const agentPayload = {
        arquiteto:     { ativo: true, provider: agentConfig.arquiteto.provider,     model: agentConfig.arquiteto.model     || null },
        desenvolvedor: { ativo: true, provider: agentConfig.desenvolvedor.provider, model: agentConfig.desenvolvedor.model || null },
        revisor:       { ativo: agentConfig.revisor.ativo,     provider: agentConfig.revisor.provider,     model: agentConfig.revisor.model     || null },
        integrador:    { ativo: agentConfig.integrador.ativo,  provider: agentConfig.integrador.provider,  model: agentConfig.integrador.model  || null },
      };
      await api.put(`/projects/${projectId}/agent-config`, agentPayload);

      toast.success("Configuração de IA salva!");
      onNext();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
        "Não foi possível salvar a configuração de IA. Verifique o provedor selecionado e tente novamente.";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <ImmutableWarning />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
            Provedor de IA <span className="text-red-400">*</span>
            <HelpIcon text="Define qual IA gerará o código e análises do projeto. Anthropic (Claude) é o padrão recomendado — melhor raciocínio lógico e código complexo. OpenAI (GPT-4o) é amplamente documentado e com boa integração de ferramentas. Google (Gemini) tem bom custo-benefício para alto volume. A chave de API do provedor escolhido deve estar configurada no servidor." />
          </label>
          <select {...register("ai_provider")} className="input-field">
            <option value="">Selecione...</option>
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai">OpenAI (GPT)</option>
            <option value="gemini">Google (Gemini)</option>
          </select>
          {errors.ai_provider && (
            <p className="text-red-400 text-xs mt-1">{errors.ai_provider.message}</p>
          )}
        </div>

        <div>
          <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
            Modelo <span className="text-red-400">*</span>
            <HelpIcon text="Nome exato do modelo de IA. Modelos mais recentes são mais capazes mas também mais caros por token gerado. Recomendação por caso de uso: claude-sonnet-4-6 para projetos profissionais com alta complexidade; claude-haiku-4-5-20251001 para projetos simples com alto volume de geração; gpt-4o-mini para uso econômico com OpenAI. Digite ou selecione uma das sugestões abaixo." />
          </label>
          <input
            {...register("ai_model")}
            list="ai-models-list"
            className="input-field"
            placeholder="Ex.: claude-sonnet-4-6"
          />
          {suggestedModels.length > 0 && (
            <datalist id="ai-models-list">
              {suggestedModels.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          )}
          {errors.ai_model && (
            <p className="text-red-400 text-xs mt-1">{errors.ai_model.message}</p>
          )}
          {suggestedModels.length > 0 && (
            <p className="text-xs text-gray-500 mt-1">
              Sugestões: {suggestedModels.join(", ")}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
            Idioma do Código <span className="text-red-400">*</span>
            <HelpIcon text="Idioma dos comentários, docstrings e documentação gerada pela IA. Pt-BR é recomendado para equipes brasileiras — manter o código documentado no idioma da equipe facilita revisões de código, onboarding de novos membros e comunicação com stakeholders. Escolha Inglês se a equipe for internacional ou se o projeto for open-source." />
          </label>
          <select {...register("code_language")} className="input-field">
            <option value="pt-BR">Português (pt-BR)</option>
            <option value="en">Inglês (en)</option>
            <option value="es">Espanhol (es)</option>
          </select>
          {errors.code_language && (
            <p className="text-red-400 text-xs mt-1">{errors.code_language.message}</p>
          )}
        </div>

        <div>
          <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
            Estilo de Comentários <span className="text-red-400">*</span>
            <HelpIcon text="Padrão de documentação do código gerado. Docstrings: padrão Python, lido por ferramentas como Sphinx. JSDoc: padrão JavaScript/TypeScript, integrado ao VS Code e TypeDoc. Javadoc: padrão Java, usado pelo Maven e IDEs como IntelliJ. XML: padrão C# / .NET, processado pelo Visual Studio. Nenhum: código sem comentários inline — não recomendado para projetos colaborativos." />
          </label>
          <select {...register("comment_style")} className="input-field">
            <option value="docstrings">Docstrings (Python)</option>
            <option value="jsdoc">JSDoc (JavaScript/TS)</option>
            <option value="javadoc">Javadoc (Java)</option>
            <option value="xml">XML (C#)</option>
            <option value="none">Nenhum</option>
          </select>
          {errors.comment_style && (
            <p className="text-red-400 text-xs mt-1">{errors.comment_style.message}</p>
          )}
        </div>
      </div>

      <div>
        <label className="block text-sm text-gray-300 mb-1 flex items-center gap-1">
          Prompt Customizado <span className="text-gray-500 text-xs">(opcional)</span>
          <HelpIcon text="Instruções fixas que o GPD envia ao modelo de IA em toda geração de código deste projeto. Use para definir padrões arquiteturais obrigatórios, bibliotecas específicas ou restrições da equipe. Ex.: 'Use sempre async/await, evite callbacks. Prefira functional programming. Utilize Pydantic para validação. Todos os endpoints devem ter tratamento de erro explícito.' Limite de 2000 caracteres." />
        </label>
        <textarea
          {...register("custom_prompt")}
          className="input-field resize-none"
          rows={4}
          maxLength={2000}
          placeholder="Instruções adicionais para o modelo de IA ao gerar código neste projeto..."
        />
        <div className="flex justify-between items-center mt-1">
          {errors.custom_prompt
            ? <p className="text-red-400 text-xs">{errors.custom_prompt.message}</p>
            : <span />
          }
          <span className="text-xs text-gray-600">
            {watch("custom_prompt")?.length ?? 0}/2000
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            {...register("generate_readme")}
            className="w-4 h-4 accent-violet-600"
          />
          <span className="text-sm text-gray-300 flex items-center gap-1">
            Gerar README automaticamente
            <HelpIcon text="O GPD criará um README.md no repositório com visão geral do projeto, instruções de instalação, uso e arquitetura. Atualizado a cada geração de código. Recomendado para todos os projetos — é o primeiro documento que novos membros da equipe e stakeholders técnicos consultam." />
          </span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            {...register("generate_unit_tests")}
            className="w-4 h-4 accent-violet-600"
          />
          <span className="text-sm text-gray-300 flex items-center gap-1">
            Gerar testes unitários automaticamente
            <HelpIcon text="O GPD gerará arquivos de teste junto com o código de produção, no padrão da linguagem escolhida (pytest para Python, Jest para JS/TS, JUnit para Java). Os casos de teste são derivados dos requisitos do Gatekeeper e ficam disponíveis no QA Readiness para rastreamento de execução." />
          </span>
        </label>
      </div>

      {/* ── Configuração de Agentes IA ── */}
      <div className="border border-gray-700 rounded-lg overflow-hidden mt-2">
        <div className="bg-dark-200 px-4 py-2 border-b border-gray-700">
          <p className="text-sm font-semibold text-gray-200 flex items-center gap-1">
            Configuração de Agentes IA
            <HelpIcon text="O GPD usa múltiplos agentes especializados que trabalham em sequência. Arquiteto (sempre ativo): define estrutura de pastas, padrões e interfaces antes de gerar código. Desenvolvedor (sempre ativo): implementa o código seguindo o plano do Arquiteto. Revisor (opcional): analisa qualidade, segurança e boas práticas — recomendado para projetos críticos. Integrador (opcional): garante compatibilidade e consistência entre módulos diferentes do mesmo projeto." />
          </p>
          <p className="text-xs text-gray-500">Arquiteto e Desenvolvedor são sempre ativos</p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 border-b border-gray-700">
              <th className="text-left px-4 py-2">Agente</th>
              <th className="text-center px-2 py-2">Ativo</th>
              <th className="text-left px-2 py-2">Provedor</th>
              <th className="text-left px-2 py-2">Modelo</th>
            </tr>
          </thead>
          <tbody>
            {(Object.keys(AGENT_LABELS) as Array<keyof AgentConfigState>).map((agentKey) => {
              const { label, alwaysActive } = AGENT_LABELS[agentKey];
              const agent = agentConfig[agentKey];
              const agentModels = AI_MODELS[agent.provider] ?? [];
              return (
                <tr key={agentKey} className="border-b border-gray-700 last:border-b-0">
                  <td className="px-4 py-2 text-gray-300 font-medium">{label}</td>
                  <td className="px-2 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={alwaysActive ? true : agent.ativo}
                      disabled={alwaysActive}
                      onChange={(e) => !alwaysActive && updateAgent(agentKey, "ativo", e.target.checked)}
                      className="w-4 h-4 accent-violet-600 disabled:opacity-40"
                    />
                  </td>
                  <td className="px-2 py-2">
                    <select
                      value={agent.provider}
                      onChange={(e) => updateAgent(agentKey, "provider", e.target.value)}
                      className="input-field py-1 text-xs"
                    >
                      <option value="anthropic">Anthropic</option>
                      <option value="openai">OpenAI</option>
                      <option value="gemini">Gemini</option>
                    </select>
                  </td>
                  <td className="px-2 py-2">
                    <input
                      type="text"
                      list={`agent-models-${agentKey}`}
                      value={agent.model}
                      onChange={(e) => updateAgent(agentKey, "model", e.target.value)}
                      placeholder="padrão"
                      className="input-field py-1 text-xs"
                    />
                    {agentModels.length > 0 && (
                      <datalist id={`agent-models-${agentKey}`}>
                        {agentModels.map((m) => <option key={m} value={m} />)}
                      </datalist>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex justify-between pt-2">
        <button type="button" onClick={onBack} className="btn-secondary flex items-center gap-2">
          <ChevronLeft size={16} /> Voltar
        </button>
        <button
          type="submit"
          className="btn-primary flex items-center gap-2"
          disabled={saving}
        >
          {saving ? "Salvando..." : "Avançar"} <ChevronRight size={16} />
        </button>
      </div>
    </form>
  );
}

// ─── Step 5 — Equipe ─────────────────────────────────────────────────────────

interface PendingInvite {
  name: string;
  email: string;
  role: string;
}

function Step5TeamForm({
  projectId,
  onBack,
  onFinish,
}: {
  projectId: string;
  onBack: () => void;
  onFinish: () => void;
}) {
  const [pending, setPending] = useState<PendingInvite[]>([]);
  const [inviteName, setInviteName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("developer");
  const [saving, setSaving] = useState(false);

  const addPending = useCallback(() => {
    if (!inviteName.trim() || !inviteEmail.trim()) return;
    if (pending.some((p) => p.email.toLowerCase() === inviteEmail.toLowerCase())) {
      toast.error("Este e-mail já está na lista de convites.");
      return;
    }
    setPending((prev) => [...prev, { name: inviteName.trim(), email: inviteEmail.trim(), role: inviteRole }]);
    setInviteName("");
    setInviteEmail("");
    setInviteRole("developer");
  }, [inviteName, inviteEmail, inviteRole, pending]);

  const removePending = useCallback((email: string) => {
    setPending((prev) => prev.filter((p) => p.email !== email));
  }, []);

  const handleFinish = async () => {
    setSaving(true);
    try {
      // Enviar convites
      for (const invite of pending) {
        try {
          await api.post(`/projects/${projectId}/members/invite`, invite);
        } catch (err: unknown) {
          const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
            ?? `Falha ao convidar ${invite.email}.`;
          toast.error(msg);
        }
      }
      // Finalizar wizard
      await api.patch(`/projects/${projectId}/step4`, { members: [] });
      toast.success("Projeto criado com sucesso!");
      onFinish();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
        "Não foi possível finalizar o projeto. Tente novamente.";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Formulário de convite */}
      <div className="space-y-3 p-4 border border-gray-700 rounded-lg bg-dark-100">
        <p className="text-sm text-gray-300 font-medium flex items-center gap-2">
          <Mail size={14} className="text-violet-400" /> Convidar pessoa para o projeto
          <HelpIcon text="Adicione membros da equipe que terão acesso a este projeto. Cada pessoa recebe um papel que define o que pode visualizar e editar dentro do GPD. O convite é enviado por e-mail — a pessoa receberá um link para criar ou acessar sua conta. Você pode pular esta etapa e convidar depois na seção Equipe do projeto." />
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Nome completo</label>
            <input
              type="text"
              value={inviteName}
              onChange={(e) => setInviteName(e.target.value)}
              className="input-field"
              placeholder="Ex: João Silva"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">E-mail</label>
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              className="input-field"
              placeholder="joao@empresa.com"
              onKeyDown={(e) => e.key === "Enter" && addPending()}
            />
          </div>
        </div>
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-xs text-gray-400 mb-1 flex items-center gap-1">
              Perfil no projeto
              <HelpIcon text="Define as permissões da pessoa neste projeto. Desenvolvedor: acessa artefatos, código gerado e QA. Tech Lead: idem + pode aprovar módulos e revisar código. Product Owner: foco em requisitos — acessa artefatos e roadmap. Scrum Master: acesso amplo exceto configurações técnicas. QA Engineer: acessa QA Readiness e pode marcar Show Stoppers que bloqueiam deploy. Visualizador: somente leitura em todas as seções." />
            </label>
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="input-field"
            >
              {MEMBER_ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={addPending}
            disabled={!inviteName.trim() || !inviteEmail.trim()}
            className="btn-primary flex items-center gap-2 disabled:opacity-40"
          >
            <UserPlus size={14} /> Adicionar à lista
          </button>
        </div>
      </div>

      {/* Lista de convites pendentes */}
      {pending.length > 0 ? (
        <div>
          <p className="text-sm text-gray-400 mb-2">
            Convites a enviar ({pending.length}) — serão enviados ao finalizar
          </p>
          <ul className="space-y-2">
            {pending.map((invite) => (
              <li
                key={invite.email}
                className="flex items-center gap-3 bg-dark-200 border border-gray-700 rounded-lg px-3 py-2"
              >
                <Mail size={14} className="text-violet-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200 font-medium truncate">{invite.name}</p>
                  <p className="text-xs text-gray-500 truncate">{invite.email}</p>
                </div>
                <span className="text-xs text-gray-500 bg-dark px-2 py-0.5 rounded-full shrink-0">
                  {MEMBER_ROLES.find((r) => r.value === invite.role)?.label ?? invite.role}
                </span>
                <button
                  type="button"
                  onClick={() => removePending(invite.email)}
                  className="text-gray-500 hover:text-red-400 transition-colors shrink-0"
                >
                  <X size={15} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-gray-600 text-center py-4 border border-dashed border-gray-700 rounded-lg">
          Nenhum convite adicionado. Você pode finalizar agora e convidar a equipe depois em <strong className="text-gray-500">Equipe</strong>.
        </p>
      )}

      <div className="flex justify-between pt-2">
        <button type="button" onClick={onBack} className="btn-secondary flex items-center gap-2">
          <ChevronLeft size={16} /> Voltar
        </button>
        <button
          type="button"
          onClick={handleFinish}
          className="btn-primary flex items-center gap-2"
          disabled={saving}
        >
          {saving ? "Finalizando..." : "Finalizar"} <Check size={16} />
        </button>
      </div>
    </div>
  );
}

// ─── Main Wizard ─────────────────────────────────────────────────────────────

export function ProjectWizardPage() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const handleStep1Next = async (values: Step1Values) => {
    setCreating(true);
    try {
      const res = await api.post<{ id: string; status: string }>(
        "/projects",
        values
      );
      setProjectId(res.data.id);
      toast.success("Projeto criado! Configure a stack técnica.");
      setCurrentStep(2);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
        "Não foi possível criar o projeto. Verifique se já existe um projeto com este nome ou tente novamente.";
      toast.error(msg);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Wand2 size={22} className="text-violet-400" />
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          Novo Projeto
          <HelpIcon text="O wizard de criação tem 5 passos. Passos 2 e 4 (Stack Técnica e IA) são imutáveis após salvos — revise com atenção antes de avançar. Passo 1 e Passo 5 podem ser editados depois. O projeto fica com status 'Configurando' até todos os passos serem concluídos. Após finalizar, acesse Artefatos para iniciar o fluxo de análise." />
        </h1>
      </div>

      <div className="card">
        <Stepper current={currentStep} />

        <div className="mt-2">
          <h2 className="text-lg font-semibold text-white mb-4">
            Passo {currentStep}: {STEP_LABELS[currentStep - 1]}
          </h2>

          {currentStep === 1 && (
            <Step1Form
              onNext={
                creating
                  ? () => {}
                  : handleStep1Next
              }
            />
          )}

          {currentStep === 2 && projectId && (
            <Step2Form
              projectId={projectId}
              onNext={() => setCurrentStep(3)}
              onBack={() => setCurrentStep(1)}
            />
          )}

          {currentStep === 3 && projectId && (
            <Step3RepoForm
              projectId={projectId}
              onNext={() => setCurrentStep(4)}
              onBack={() => setCurrentStep(2)}
            />
          )}

          {currentStep === 4 && projectId && (
            <Step4IAForm
              projectId={projectId}
              onNext={() => setCurrentStep(5)}
              onBack={() => setCurrentStep(3)}
            />
          )}

          {currentStep === 5 && projectId && (
            <Step5TeamForm
              projectId={projectId}
              onBack={() => setCurrentStep(4)}
              onFinish={() => navigate("/projects")}
            />
          )}

          {creating && (
            <div className="text-center text-violet-400 text-sm py-2 animate-pulse">
              Criando projeto...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
