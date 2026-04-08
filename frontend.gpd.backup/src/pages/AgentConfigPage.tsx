// ─────────────────────────────────────────────────────────────────────────────
// Módulo: pages/AgentConfigPage.tsx
// Projeto: GPD v4.0
// Propósito: Configuração de agentes IA por projeto
//            Provedores disponíveis carregados dinamicamente da parametrização global
//            Escrita: admin, project_manager, tech_lead
// ─────────────────────────────────────────────────────────────────────────────

import { useState } from "react";
import { HelpIcon } from "@/components/HelpIcon";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { Bot, Save, Lock, Cpu, Code2, ClipboardCheck, Puzzle, AlertCircle, Loader2 } from "lucide-react";
import clsx from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

// ─── Types ───────────────────────────────────────────────────────────────────

interface AgentItemConfig {
  ativo: boolean;
  provider: string;
  model: string | null;
}

interface AgentConfig {
  projeto_id: string;
  updated_at: string;
  arquiteto: AgentItemConfig;
  desenvolvedor: AgentItemConfig;
  revisor: AgentItemConfig;
  integrador: AgentItemConfig;
}

interface AvailableProvider {
  key: string;
  name: string;
  available_models: string[];
  current_model: string | null;
}

type AgentKey = "arquiteto" | "desenvolvedor" | "revisor" | "integrador";

// ─── Fallback: provedores padrão usados se a API não responder ───────────────

const FALLBACK_PROVIDERS: AvailableProvider[] = [
  {
    key: "anthropic",
    name: "Anthropic Claude",
    available_models: ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
    current_model: "claude-sonnet-4-6",
  },
  {
    key: "openai",
    name: "OpenAI GPT",
    available_models: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    current_model: "gpt-4o",
  },
  {
    key: "gemini",
    name: "Google Gemini",
    available_models: ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    current_model: "gemini-2.0-flash",
  },
  {
    key: "deepseek",
    name: "DeepSeek",
    available_models: ["deepseek-chat", "deepseek-reasoner"],
    current_model: "deepseek-chat",
  },
  {
    key: "grok",
    name: "xAI Grok",
    available_models: ["grok-3", "grok-3-mini", "grok-2"],
    current_model: "grok-3",
  },
];

// ─── Constants ────────────────────────────────────────────────────────────────

const CAN_WRITE_ROLES = ["admin", "project_manager", "tech_lead"];

const AGENT_META: Record<AgentKey, {
  label: string;
  description: string;
  icon: React.ElementType;
  alwaysActive: boolean;
}> = {
  arquiteto: {
    label: "Arquiteto",
    description: "Analisa os artefatos e define a estrutura de alto nível do sistema — camadas, módulos, padrões e contratos de API.",
    icon: Cpu,
    alwaysActive: true,
  },
  desenvolvedor: {
    label: "Desenvolvedor",
    description: "Gera o código-fonte a partir da arquitetura definida pelo Arquiteto, seguindo os padrões e tecnologias do projeto.",
    icon: Code2,
    alwaysActive: true,
  },
  revisor: {
    label: "Revisor",
    description: "Revisa o código gerado em busca de inconsistências, más práticas e desvios dos requisitos — pode ser desativado.",
    icon: ClipboardCheck,
    alwaysActive: false,
  },
  integrador: {
    label: "Integrador",
    description: "Consolida os módulos gerados, resolve dependências e prepara o pacote final para push ao repositório — pode ser desativado.",
    icon: Puzzle,
    alwaysActive: false,
  },
};

// ─── Component ───────────────────────────────────────────────────────────────

export function AgentConfigPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const canWrite = CAN_WRITE_ROLES.includes(user?.role ?? "");

  // Provedores configurados globalmente (fallback para lista padrão se API não responder)
  const { data: providersData, isLoading: providersLoading } = useQuery<AvailableProvider[]>({
    queryKey: ["ai-available-providers"],
    queryFn: () =>
      api.get<{ success: boolean; data: AvailableProvider[] }>("/settings/ai/available")
        .then(r => r.data.data)
        .catch(() => FALLBACK_PROVIDERS),
    staleTime: 60_000,
  });

  // Se a API retornou lista vazia, usa fallback com todos os provedores do sistema
  const providers = (providersData && providersData.length > 0) ? providersData : FALLBACK_PROVIDERS;

  // Configuração atual do projeto
  const { data, isLoading, isError } = useQuery<{ success: boolean; data: AgentConfig }>({
    queryKey: ["agent-config", projectId],
    queryFn: () => api.get(`/projects/${projectId}/agent-config`).then(r => r.data),
    enabled: !!projectId,
  });

  const config = data?.data;

  const [draft, setDraft] = useState<Record<AgentKey, AgentItemConfig> | null>(null);

  const effective = draft ?? (config
    ? {
        arquiteto:     { ...config.arquiteto,     model: config.arquiteto.model     ?? "" },
        desenvolvedor: { ...config.desenvolvedor, model: config.desenvolvedor.model ?? "" },
        revisor:       { ...config.revisor,       model: config.revisor.model       ?? "" },
        integrador:    { ...config.integrador,    model: config.integrador.model    ?? "" },
      }
    : null);

  const mutation = useMutation({
    mutationFn: (payload: Record<AgentKey, AgentItemConfig>) =>
      api.put(`/projects/${projectId}/agent-config`, {
        arquiteto:     { ativo: true,                     provider: payload.arquiteto.provider,     model: payload.arquiteto.model     || null },
        desenvolvedor: { ativo: true,                     provider: payload.desenvolvedor.provider, model: payload.desenvolvedor.model || null },
        revisor:       { ativo: payload.revisor.ativo,    provider: payload.revisor.provider,       model: payload.revisor.model       || null },
        integrador:    { ativo: payload.integrador.ativo, provider: payload.integrador.provider,    model: payload.integrador.model    || null },
      }),
    onSuccess: () => {
      toast.success("Configuração de agentes salva!");
      queryClient.invalidateQueries({ queryKey: ["agent-config", projectId] });
      setDraft(null);
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
        "Não foi possível salvar. Tente novamente.";
      toast.error(msg);
    },
  });

  const updateAgent = (agent: AgentKey, field: keyof AgentItemConfig, value: string | boolean) => {
    if (!effective) return;
    const updated = { ...effective, [agent]: { ...effective[agent], [field]: value } };
    // Ao trocar provedor, limpa o modelo para forçar escolha consciente
    if (field === "provider") {
      updated[agent] = { ...updated[agent], model: "" };
    }
    setDraft(updated);
  };

  // Retorna os modelos disponíveis para o provedor selecionado pelo agente
  function getModelsForProvider(providerKey: string): string[] {
    return providers.find(p => p.key === providerKey)?.available_models ?? [];
  }

  if (isLoading || providersLoading) return (
    <div className="flex items-center justify-center py-20 text-gray-500 text-sm gap-2">
      <Loader2 size={16} className="animate-spin" />
      Carregando configuração...
    </div>
  );

  if (isError) return (
    <div className="flex items-center justify-center py-20 text-red-400 text-sm">
      Não foi possível carregar a configuração. Recarregue a página.
    </div>
  );

  return (
    <div className="max-w-3xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Bot size={22} className="text-violet-400" />
          Agentes IA
          <HelpIcon text="Escolha o provedor e o modelo de IA para cada agente do pipeline de geração de código. Os provedores disponíveis são os configurados na Parametrização Global. Arquiteto e Desenvolvedor são sempre ativos. Revisor e Integrador podem ser desativados." />
        </h1>
        {canWrite && (
          <button
            onClick={() => effective && mutation.mutate(effective)}
            disabled={mutation.isPending || !draft}
            className="btn-primary flex items-center gap-2 disabled:opacity-50"
          >
            <Save size={16} />
            {mutation.isPending ? "Salvando..." : "Salvar configuração"}
          </button>
        )}
      </div>

      {/* Aviso somente-leitura */}
      {!canWrite && (
        <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-900/20 border border-amber-700/30 rounded-lg px-4 py-2.5">
          <Lock size={13} />
          Apenas Gerente de Projeto, Tech Lead e Admin podem alterar esta configuração.
        </div>
      )}

      {/* Badge: provedores via fallback (nenhum configurado na API) */}
      {providersData !== undefined && providersData.length === 0 && (
        <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-900/15 border border-amber-800/30 rounded-lg px-3 py-2">
          <AlertCircle size={12} />
          Usando provedores padrão. Para restringir às IAs configuradas, acesse a{" "}
          <span className="font-semibold">Parametrização Global</span> e configure ao menos um provedor.
        </div>
      )}

      {/* Cards de agentes */}
      {effective && (
        <div className="space-y-3">
          {(Object.keys(AGENT_META) as AgentKey[]).map((key) => {
            const meta = AGENT_META[key];
            const agent = effective[key];
            const Icon = meta.icon;
            const models = getModelsForProvider(agent.provider);
            const isActive = meta.alwaysActive || agent.ativo;

            // Garante que o provedor salvo ainda existe entre os configurados
            const providerExists = providers.some(p => p.key === agent.provider);

            return (
              <div
                key={key}
                className={clsx(
                  "card transition-opacity",
                  !isActive && "opacity-50"
                )}
              >
                <div className="flex items-start justify-between gap-4">
                  {/* Info do agente */}
                  <div className="flex items-start gap-3 min-w-0">
                    <div className={clsx(
                      "mt-0.5 p-2 rounded-lg shrink-0",
                      isActive ? "bg-violet-900/40" : "bg-gray-800"
                    )}>
                      <Icon size={16} className={isActive ? "text-violet-400" : "text-gray-600"} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white text-sm">{meta.label}</span>
                        {meta.alwaysActive ? (
                          <span className="text-xs bg-violet-900/40 text-violet-300 px-1.5 py-0.5 rounded-full">
                            sempre ativo
                          </span>
                        ) : (
                          <span className={clsx(
                            "text-xs px-1.5 py-0.5 rounded-full",
                            agent.ativo
                              ? "bg-emerald-900/40 text-emerald-300"
                              : "bg-gray-700/60 text-gray-500"
                          )}>
                            {agent.ativo ? "ativo" : "inativo"}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                        {meta.description}
                      </p>
                    </div>
                  </div>

                  {/* Toggle (apenas para revisor/integrador) */}
                  {!meta.alwaysActive && canWrite && (
                    <button
                      onClick={() => updateAgent(key, "ativo", !agent.ativo)}
                      className={clsx(
                        "shrink-0 w-10 h-5 rounded-full transition-colors relative mt-1",
                        agent.ativo ? "bg-violet-600" : "bg-gray-700"
                      )}
                    >
                      <span className={clsx(
                        "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform",
                        agent.ativo ? "translate-x-5" : "translate-x-0.5"
                      )} />
                    </button>
                  )}
                </div>

                {/* Seletores de provedor e modelo */}
                <div className="mt-4 grid grid-cols-2 gap-3">
                  {/* Provedor */}
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Provedor de IA</label>
                    <select
                      value={providerExists ? agent.provider : ""}
                      disabled={!canWrite || !isActive}
                      onChange={(e) => updateAgent(key, "provider", e.target.value)}
                      className="input-field py-1.5 text-sm disabled:opacity-50"
                    >
                      {!providerExists && (
                        <option value="" disabled>— provedor não configurado —</option>
                      )}
                      {providers.map(p => (
                        <option key={p.key} value={p.key}>{p.name}</option>
                      ))}
                    </select>
                  </div>

                  {/* Modelo */}
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Modelo</label>
                    <select
                      value={agent.model ?? ""}
                      disabled={!canWrite || !isActive || !providerExists}
                      onChange={(e) => updateAgent(key, "model", e.target.value)}
                      className="input-field py-1.5 text-sm disabled:opacity-50"
                    >
                      <option value="">— padrão do provedor —</option>
                      {models.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Alerta: provedor não está mais configurado globalmente */}
                {!providerExists && agent.provider && (
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-400">
                    <AlertCircle size={11} />
                    O provedor "{agent.provider}" não está mais configurado globalmente. Selecione outro.
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Rodapé com última atualização */}
      {config?.updated_at && (
        <p className="text-xs text-gray-600">
          Última atualização: {new Date(config.updated_at).toLocaleString("pt-BR")}
        </p>
      )}
    </div>
  );
}
