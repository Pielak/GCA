import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Settings,
  CheckCircle,
  XCircle,
  Loader2,
  Eye,
  EyeOff,
  Save,
  Info,
  ChevronDown,
  ChevronRight,
  Cpu,
  Activity,
  Mail,
  Send,
} from "lucide-react";
import { toast } from "react-hot-toast";
import clsx from "clsx";
import { api } from "@/services/api";

// ─── Types ───────────────────────────────────────────────────────────────────

interface ProviderConfig {
  model: string;
  temperature: number;
  max_tokens: number;
  api_key_configured: boolean;
}

interface AISettings {
  active_provider: string;
  default_model: string;
  providers: {
    anthropic: ProviderConfig;
    openai: ProviderConfig;
    gemini: ProviderConfig;
    deepseek: ProviderConfig;
    grok: ProviderConfig;
  };
}

interface AIHealth {
  anthropic: boolean;
  openai: boolean;
  gemini: boolean;
  deepseek: boolean;
  grok: boolean;
}

interface SystemSettings {
  app_version: string;
  app_env: string;
  active_ai_provider: string;
  default_model?: string;
  storage_backend?: string;
  [key: string]: unknown;
}

type ProviderKey = "anthropic" | "openai" | "gemini" | "deepseek" | "grok";

interface SmtpStatus {
  host: string;
  port: number;
  user: string;
  from: string;
  password_set: boolean;
  configured: boolean;
}

// ─── Provider metadata ────────────────────────────────────────────────────────

const PROVIDERS: {
  key: ProviderKey;
  name: string;
  icon: string;
  models: string[];
  color: string;
}[] = [
  {
    key: "anthropic",
    name: "Anthropic Claude",
    icon: "🧠",
    models: [
      "claude-opus-4-5",
      "claude-sonnet-4-5",
      "claude-haiku-4-5",
      "claude-3-5-sonnet-20241022",
      "claude-3-5-haiku-20241022",
      "claude-3-opus-20240229",
    ],
    color: "violet",
  },
  {
    key: "openai",
    name: "OpenAI GPT",
    icon: "✨",
    models: [
      "gpt-4o",
      "gpt-4o-mini",
      "gpt-4-turbo",
      "gpt-4",
      "gpt-3.5-turbo",
      "o1-preview",
      "o1-mini",
    ],
    color: "emerald",
  },
  {
    key: "gemini",
    name: "Google Gemini",
    icon: "💎",
    models: [
      "gemini-1.5-pro",
      "gemini-1.5-flash",
      "gemini-1.0-pro",
      "gemini-ultra",
    ],
    color: "blue",
  },
  {
    key: "deepseek",
    name: "DeepSeek",
    icon: "🐋",
    models: [
      "deepseek-chat",
      "deepseek-reasoner",
    ],
    color: "cyan",
  },
  {
    key: "grok",
    name: "xAI Grok",
    icon: "⚡",
    models: [
      "grok-3",
      "grok-3-mini",
      "grok-2",
      "grok-beta",
    ],
    color: "orange",
  },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function HealthIndicator({ status }: { status: boolean | undefined }) {
  if (status === undefined)
    return (
      <span className="flex items-center gap-1 text-xs text-gray-500">
        <Loader2 size={11} className="animate-spin" />
        Verificando...
      </span>
    );
  return status ? (
    <span className="flex items-center gap-1 text-xs text-emerald-400">
      <CheckCircle size={11} /> Online
    </span>
  ) : (
    <span className="flex items-center gap-1 text-xs text-red-400">
      <XCircle size={11} /> Offline
    </span>
  );
}

// ─── Provider Config Form ────────────────────────────────────────────────────

function ProviderConfigForm({
  providerKey,
  config,
  models,
}: {
  providerKey: ProviderKey;
  config: ProviderConfig;
  models: string[];
}) {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [model, setModel] = useState(config.model);
  const [temperature, setTemperature] = useState(config.temperature);
  const [maxTokens, setMaxTokens] = useState(config.max_tokens);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = { model, temperature, max_tokens: maxTokens };
      if (apiKey.trim()) body.api_key = apiKey.trim();
      const { data } = await api.patch(`/settings/ai/providers/${providerKey}`, body);
      return data;
    },
    onSuccess: () => {
      toast.success(`Configurações de ${providerKey} salvas.`);
      queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
      setApiKey("");
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Não foi possível salvar as configurações. Verifique se a API key é válida para o provedor selecionado.");
    },
  });

  return (
    <div className="space-y-4 pt-2">
      {/* API Key */}
      <div className="space-y-1">
        <label className="text-xs text-gray-400 font-medium flex items-center gap-1">
          API Key
          {config.api_key_configured && (
            <span className="text-emerald-400 text-xs flex items-center gap-0.5">
              <CheckCircle size={10} /> Configurada
            </span>
          )}
        </label>
        <div className="relative">
          <input
            type={showKey ? "text" : "password"}
            className="input-field text-sm pr-10 font-mono"
            placeholder={
              config.api_key_configured ? "••••••••••••••• (manter atual)" : "sk-..."
            }
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
          <button
            type="button"
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
            onClick={() => setShowKey((p) => !p)}
          >
            {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>
        <div className="flex items-start gap-1.5 bg-amber-900/15 border border-amber-800/30 rounded-lg px-2.5 py-2 mt-1">
          <Info size={12} className="text-amber-500 mt-0.5 shrink-0" />
          <p className="text-xs text-amber-500">
            A API key é armazenada apenas em memória nesta versão MVP. Para persistir, configure no arquivo{" "}
            <code className="font-mono">.env</code>.
          </p>
        </div>
      </div>

      {/* Model */}
      <div className="space-y-1">
        <label className="text-xs text-gray-400 font-medium">Modelo Padrão</label>
        <select
          className="input-field text-sm"
          value={model}
          onChange={(e) => setModel(e.target.value)}
        >
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      {/* Temperature */}
      <div className="space-y-1">
        <label className="text-xs text-gray-400 font-medium flex items-center justify-between">
          <span>Temperature</span>
          <span className="text-violet-400 font-mono tabular-nums">{temperature.toFixed(1)}</span>
        </label>
        <input
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={temperature}
          onChange={(e) => setTemperature(parseFloat(e.target.value))}
          className="w-full accent-violet-600 h-1.5 cursor-pointer"
        />
        <div className="flex justify-between text-xs text-gray-600">
          <span>0.0 (determinístico)</span>
          <span>2.0 (criativo)</span>
        </div>
      </div>

      {/* Max tokens */}
      <div className="space-y-1">
        <label className="text-xs text-gray-400 font-medium">Max Tokens</label>
        <input
          type="number"
          className="input-field text-sm"
          min={256}
          max={32768}
          step={256}
          value={maxTokens}
          onChange={(e) => setMaxTokens(parseInt(e.target.value, 10))}
        />
        <p className="text-xs text-gray-600">256 – 32768</p>
      </div>

      <button
        className="btn-primary text-sm flex items-center gap-2 w-full justify-center"
        onClick={() => saveMutation.mutate()}
        disabled={saveMutation.isPending}
      >
        {saveMutation.isPending ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Save size={14} />
        )}
        Salvar Configurações
      </button>
    </div>
  );
}

// ─── SMTP Config Section ─────────────────────────────────────────────────────

function SmtpConfigSection() {
  const queryClient = useQueryClient();
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [smtpFrom, setSmtpFrom] = useState("");
  const [showPw, setShowPw] = useState(false);

  const { data: smtp, isLoading } = useQuery<SmtpStatus>({
    queryKey: ["smtp-settings"],
    queryFn: async () => {
      const { data } = await api.get<{ success: boolean; data: SmtpStatus }>("/settings/smtp");
      return data.data;
    },
    staleTime: 30_000,
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, string | number> = {};
      if (host.trim())     body.host      = host.trim();
      if (port.trim())     body.port      = parseInt(port, 10);
      if (user.trim())     body.user      = user.trim();
      if (password.trim()) body.password  = password.trim();
      if (smtpFrom.trim()) body.smtp_from = smtpFrom.trim();
      const { data } = await api.put("/settings/smtp", body);
      return data;
    },
    onSuccess: () => {
      toast.success("Configuração SMTP salva.");
      queryClient.invalidateQueries({ queryKey: ["smtp-settings"] });
      setPassword("");
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Falha ao salvar configuração SMTP.");
    },
  });

  const testMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/settings/smtp/test");
      return data;
    },
    onSuccess: (data: any) => {
      toast.success(data.message ?? "E-mail de teste enviado!");
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.message ?? "Falha ao enviar e-mail de teste.";
      toast.error(msg, { duration: 8000 });
    },
  });

  const reloadEnvMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/settings/smtp/reload-env");
      return data;
    },
    onSuccess: (data: any) => {
      toast.success(data.message ?? "SMTP recarregado do .env.");
      queryClient.invalidateQueries({ queryKey: ["smtp-settings"] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Falha ao recarregar .env.");
    },
  });

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
        <Mail size={14} />
        Configuração de E-mail (SMTP)
      </h2>

      <div className="card space-y-5">
        {/* Status banner */}
        {!isLoading && smtp && (
          <div className={clsx(
            "flex items-center gap-2 text-sm px-3 py-2 rounded-lg border",
            smtp.configured
              ? "bg-emerald-900/20 border-emerald-700/40 text-emerald-400"
              : "bg-red-900/20 border-red-700/40 text-red-400"
          )}>
            {smtp.configured
              ? <><CheckCircle size={14} /> SMTP configurado — {smtp.host}:{smtp.port} ({smtp.user})</>
              : <><XCircle size={14} /> SMTP não configurado. Preencha os campos abaixo.</>
            }
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Host */}
          <div className="space-y-1">
            <label className="text-xs text-gray-400 font-medium">
              Servidor SMTP
              {smtp?.host && <span className="ml-2 text-gray-600 font-normal font-mono">{smtp.host}</span>}
            </label>
            <input
              type="text"
              className="input-field text-sm"
              placeholder="smtp.gmail.com"
              value={host}
              onChange={e => setHost(e.target.value)}
            />
          </div>

          {/* Port */}
          <div className="space-y-1">
            <label className="text-xs text-gray-400 font-medium">
              Porta
              {smtp?.port && <span className="ml-2 text-gray-600 font-normal font-mono">{smtp.port}</span>}
            </label>
            <input
              type="number"
              className="input-field text-sm"
              placeholder="587"
              value={port}
              onChange={e => setPort(e.target.value)}
            />
          </div>

          {/* User */}
          <div className="space-y-1">
            <label className="text-xs text-gray-400 font-medium">
              Usuário (e-mail)
              {smtp?.user && <span className="ml-2 text-gray-600 font-normal font-mono">{smtp.user}</span>}
            </label>
            <input
              type="email"
              className="input-field text-sm"
              placeholder="seuemail@gmail.com"
              value={user}
              onChange={e => setUser(e.target.value)}
            />
          </div>

          {/* Password */}
          <div className="space-y-1">
            <label className="text-xs text-gray-400 font-medium flex items-center gap-1">
              Senha / App Password
              {smtp?.password_set && (
                <span className="text-emerald-400 text-xs flex items-center gap-0.5">
                  <CheckCircle size={10} /> Configurada
                </span>
              )}
            </label>
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                className="input-field text-sm pr-10 font-mono"
                placeholder={smtp?.password_set ? "••••••••••••••• (manter atual)" : "App Password do Gmail"}
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                onClick={() => setShowPw(p => !p)}
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {/* From */}
          <div className="space-y-1 sm:col-span-2">
            <label className="text-xs text-gray-400 font-medium">
              Remetente
              {smtp?.from && <span className="ml-2 text-gray-600 font-normal font-mono">{smtp.from}</span>}
            </label>
            <input
              type="text"
              className="input-field text-sm"
              placeholder='GPD - Gerenciador de Projetos <no-reply@empresa.com>'
              value={smtpFrom}
              onChange={e => setSmtpFrom(e.target.value)}
            />
            <p className="text-xs text-gray-600">Formato: Nome Exibido &lt;email@dominio.com&gt;</p>
          </div>
        </div>

        {/* Gmail hint */}
        <div className="flex items-start gap-2 bg-blue-900/15 border border-blue-800/30 rounded-lg px-3 py-2">
          <Info size={13} className="text-blue-400 mt-0.5 shrink-0" />
          <p className="text-xs text-blue-400">
            Para Gmail: ative a verificação em duas etapas e gere uma{" "}
            <strong>App Password</strong> em{" "}
            <span className="font-mono">Conta Google → Segurança → Senhas de app</span>.
            Use essa senha de 16 caracteres no campo acima.
          </p>
        </div>

        {/* Buttons */}
        <div className="flex flex-wrap gap-3">
          <button
            className="btn-primary text-sm flex items-center gap-2"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            Salvar SMTP
          </button>

          <button
            className="btn-secondary text-sm flex items-center gap-2"
            onClick={() => testMutation.mutate()}
            disabled={testMutation.isPending || !smtp?.configured}
            title={!smtp?.configured ? "Configure o SMTP antes de testar" : "Envia um e-mail de teste para o seu usuário"}
          >
            {testMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Enviar E-mail de Teste
          </button>

          <button
            className="btn-ghost text-sm flex items-center gap-2 text-amber-400 hover:text-amber-300 border-amber-700/40 hover:border-amber-600"
            onClick={() => reloadEnvMutation.mutate()}
            disabled={reloadEnvMutation.isPending}
            title="Descarta configuração salva no Redis e recarrega os valores do arquivo .env"
          >
            {reloadEnvMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <span>↺</span>}
            Recarregar do .env
          </button>
        </div>
      </div>
    </section>
  );
}


// ─── Main Page ────────────────────────────────────────────────────────────────

export function ParametrizationPage() {
  const queryClient = useQueryClient();
  const [openProvider, setOpenProvider] = useState<ProviderKey | null>(null);
  const [healthData, setHealthData] = useState<AIHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  // AI settings
  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ["ai-settings"],
    queryFn: async () => {
      const { data } = await api.get<{ success: boolean; data: AISettings }>("/settings/ai");
      return data.data;
    },
  });

  // System settings
  const { data: sysSettings } = useQuery({
    queryKey: ["sys-settings"],
    queryFn: async () => {
      const { data } = await api.get<{ success: boolean; data: SystemSettings }>("/settings/system");
      return data.data;
    },
  });

  // Set active provider
  const setActiveMutation = useMutation({
    mutationFn: async (provider: string) => {
      const { data } = await api.patch("/settings/ai/active-provider", { provider });
      return data;
    },
    onSuccess: (_, provider) => {
      toast.success(`Provedor ativo alterado para ${provider}.`);
      queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Não foi possível alterar o provedor ativo. Verifique se o provedor selecionado está configurado corretamente com uma API key válida.");
    },
  });

  // Check health
  async function checkHealth() {
    setHealthLoading(true);
    setHealthData(null);
    try {
      const { data } = await api.get<{ success: boolean; data: AIHealth }>("/settings/ai/health");
      setHealthData(data.data);
      toast.success("Verificação de saúde concluída.");
    } catch {
      toast.error("Não foi possível verificar a conectividade dos provedores. Confira as API keys configuradas e se há conexão com a internet.");
    } finally {
      setHealthLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Settings size={24} className="text-violet-400" />
          Parametrização de IA
        </h1>
        <button
          className="btn-secondary flex items-center gap-2 text-sm"
          onClick={checkHealth}
          disabled={healthLoading}
        >
          {healthLoading ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Activity size={14} />
          )}
          Verificar Saúde dos Provedores
        </button>
      </div>

      {/* Section 1: Active provider */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
          <Cpu size={14} />
          Provedor Ativo
        </h2>

        {settingsLoading ? (
          <div className="card text-center text-gray-500 py-8">Carregando configurações...</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
            {PROVIDERS.map((p) => {
              const providerCfg = settings?.providers[p.key];
              const isActive = settings?.active_provider === p.key;
              const isConfigured = providerCfg?.api_key_configured ?? false;
              const health =
                healthData !== null ? healthData[p.key as keyof AIHealth] : undefined;

              return (
                <div
                  key={p.key}
                  className={clsx(
                    "card flex flex-col gap-3 transition-all",
                    isActive
                      ? "border-violet-600/70 bg-violet-950/20"
                      : "border-gray-700"
                  )}
                >
                  {/* Provider header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-2xl">{p.icon}</span>
                      <div>
                        <p className="font-semibold text-gray-100 text-sm">{p.name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {p.models.length} modelos disponíveis
                        </p>
                      </div>
                    </div>
                    {isActive && (
                      <span className="text-xs font-bold bg-violet-600 text-white px-2 py-0.5 rounded-full">
                        ATIVO
                      </span>
                    )}
                  </div>

                  {/* Status row */}
                  <div className="flex items-center gap-3 text-xs">
                    {isConfigured ? (
                      <span className="flex items-center gap-1 text-emerald-400">
                        <CheckCircle size={11} /> Configurado
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-gray-500">
                        <XCircle size={11} /> Não configurado
                      </span>
                    )}
                    <HealthIndicator
                      status={healthData !== null ? health : undefined}
                    />
                  </div>

                  {/* Model info */}
                  {providerCfg && (
                    <p className="text-xs text-gray-500 font-mono truncate">
                      {providerCfg.model}
                    </p>
                  )}

                  {/* Action */}
                  {!isActive && (
                    <button
                      className={clsx(
                        "btn-secondary text-xs py-1",
                        !isConfigured && "opacity-40 cursor-not-allowed"
                      )}
                      disabled={!isConfigured || setActiveMutation.isPending}
                      onClick={() =>
                        isConfigured && setActiveMutation.mutate(p.key)
                      }
                      title={!isConfigured ? "Configure o provedor primeiro" : undefined}
                    >
                      {setActiveMutation.isPending && setActiveMutation.variables === p.key ? (
                        <Loader2 size={11} className="animate-spin inline mr-1" />
                      ) : null}
                      Tornar Ativo
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Section 2: Provider configurations (accordion) */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
          <Settings size={14} />
          Configurações por Provedor
        </h2>

        <div className="space-y-2">
          {PROVIDERS.map((p) => {
            const cfg = settings?.providers[p.key];
            const isOpen = openProvider === p.key;

            return (
              <div key={p.key} className="card overflow-hidden p-0">
                {/* Accordion header */}
                <button
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-dark-200/50 transition-colors text-left"
                  onClick={() => setOpenProvider(isOpen ? null : p.key)}
                >
                  <span className="flex items-center gap-2 text-sm font-medium text-gray-200">
                    <span>{p.icon}</span>
                    {p.name}
                    {settings?.active_provider === p.key && (
                      <span className="text-xs bg-violet-600/30 text-violet-400 border border-violet-700/40 px-1.5 py-0.5 rounded-full">
                        ativo
                      </span>
                    )}
                  </span>
                  {isOpen ? (
                    <ChevronDown size={16} className="text-gray-500" />
                  ) : (
                    <ChevronRight size={16} className="text-gray-500" />
                  )}
                </button>

                {/* Accordion body */}
                {isOpen && cfg && (
                  <div className="px-4 pb-4 border-t border-gray-700/50">
                    <ProviderConfigForm
                      providerKey={p.key}
                      config={cfg}
                      models={p.models}
                    />
                  </div>
                )}

                {isOpen && !cfg && (
                  <div className="px-4 pb-4 border-t border-gray-700/50 pt-3 text-sm text-gray-500">
                    Carregando configurações...
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Section 3: SMTP */}
      <SmtpConfigSection />

      {/* Section 4: System info */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
          <Info size={14} />
          Informações do Sistema
        </h2>

        <div className="card">
          {!sysSettings ? (
            <p className="text-gray-500 text-sm text-center py-4">Carregando...</p>
          ) : (
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-4">
              {[
                { label: "Versão da Aplicação", value: sysSettings.app_version ?? "–" },
                { label: "Ambiente", value: sysSettings.app_env ?? "–" },
                { label: "Provedor IA Ativo", value: sysSettings.active_ai_provider ?? settings?.active_provider ?? "–" },
                { label: "Modelo Padrão", value: sysSettings.default_model ?? settings?.default_model ?? "–" },
                {
                  label: "Storage Backend",
                  value: (sysSettings.storage_backend as string) ?? "–",
                },
              ].map(({ label, value }) => (
                <div key={label}>
                  <dt className="text-xs text-gray-500 uppercase tracking-wide mb-0.5">{label}</dt>
                  <dd className="text-sm text-gray-200 font-mono">{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </section>

      {/* Health check results (if ran) */}
      {healthData && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
            <Activity size={14} />
            Resultado da Verificação de Saúde
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
            {PROVIDERS.map((p) => (
              <div
                key={p.key}
                className={clsx(
                  "card flex items-center gap-3",
                  healthData[p.key as keyof AIHealth]
                    ? "border-emerald-700/50"
                    : "border-red-700/50"
                )}
              >
                <span className="text-xl">{p.icon}</span>
                <div>
                  <p className="text-sm font-medium text-gray-200">{p.name}</p>
                  {healthData[p.key as keyof AIHealth] ? (
                    <span className="flex items-center gap-1 text-xs text-emerald-400">
                      <CheckCircle size={11} /> Online
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-red-400">
                      <XCircle size={11} /> Offline / Sem conexão
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Persistent warning about API keys */}
      <div className="flex items-start gap-3 bg-amber-900/15 border border-amber-800/30 rounded-xl px-4 py-3">
        <Info size={16} className="text-amber-500 mt-0.5 shrink-0" />
        <p className="text-sm text-amber-400">
          <span className="font-semibold">Atenção:</span> Configurações de API key são armazenadas
          apenas em memória nesta versão MVP. Para persistir entre reinicializações, configure as
          variáveis no arquivo <code className="font-mono text-amber-300 bg-amber-900/30 px-1 rounded">.env</code> do servidor.
        </p>
      </div>
    </div>
  );
}
