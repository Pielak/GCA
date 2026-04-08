import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  MessageSquare, CheckCircle, RefreshCw, Lock, Zap, Layers,
  Database, Server, Code2, Wrench, AlertTriangle, HelpCircle, Users, ChevronDown,
} from "lucide-react";
import clsx from "clsx";
import { Combobox } from "@headlessui/react";
import { api } from "@/services/api";
import { languageStackApi } from "@/services/languageStackApi";
import { HelpIcon } from "@/components/HelpIcon";
import { VersionNotificationBanner } from "@/components/layout/VersionNotificationBanner";

// ── Types ──────────────────────────────────────────────────────────────────────

interface StackFormOptions {
  application_type: string[];
  architecture_profile: string[];
  database: string[];
  authentication: string[];
  message_broker: string[];
  deploy_strategy: string[];
  cache: string[];
  api_style: string[];
  by_language: Record<string, Record<string, string[]>>;
  incompatible_tools: string[];
  extra_stack_suggestions: string[];
  infra_warnings: Record<string, Record<string, string>>;
}

interface StackForm {
  language: string | null;
  available_languages: string[];
  fields: Record<string, string>;
  universal_fields: string[];
  lang_fields: string[];
  options: StackFormOptions;
  scenario_defaults: Record<string, Record<string, string>>;
  current: Record<string, string | string[]>;
}

interface Plan {
  evaluation_id: string | null;
  evaluation_score: number | null;
  stack_form: StackForm;
  argumentation_questions: unknown[];
  qa_responses: unknown[];
  has_saved_responses: boolean;
  last_updated: string | null;
}

// ── Textos de ajuda (HelpIcon) — linguagem leiga ───────────────────────────────

const FIELD_HELP: Record<string, string> = {
  application_type:
    "Que tipo de sistema você está construindo? Uma API expõe dados para outros sistemas ou apps móveis. Web App é acessado pelo navegador. CLI é uma ferramenta de linha de comando. Worker processa tarefas em segundo plano.",
  architecture_profile:
    "Como o sistema será organizado internamente? Moderno usa os padrões atuais do mercado. Corporativo é voltado para grandes empresas com processos rígidos. Legado é para modernizar código antigo. Microserviços divide o sistema em partes independentes.",
  runtime_or_platform:
    "Qual versão do ambiente de execução será usada? É como escolher qual geração de um motor colocar no carro — versões mais novas trazem mais recursos e segurança.",
  framework:
    "O framework é a estrutura base que acelera o desenvolvimento. Ele já resolve problemas comuns (roteamento, autenticação, validação) para que você foque na regra de negócio.",
  orm_odm:
    "Ferramenta que converte o código do sistema para comandos do banco de dados automaticamente. Evita escrever SQL manualmente e protege contra ataques de injeção.",
  test_framework:
    "Ambiente para escrever e rodar testes automatizados. Garante que o sistema continua funcionando corretamente após cada mudança de código.",
  build_or_package:
    "Gerenciador de dependências e pacotes. Controla quais bibliotecas externas o projeto usa, suas versões e como o código é compilado.",
  database:
    "Onde o sistema armazena os dados permanentemente (usuários, pedidos, configurações). Bancos relacionais (PostgreSQL, MySQL) organizam dados em tabelas. MongoDB é flexível para dados variados.",
  authentication:
    "Define como o sistema confirma a identidade dos usuários e controla o que cada um pode fazer. JWT é o padrão moderno para APIs. OAuth2 permite login com Google ou GitHub. LDAP integra com o Active Directory corporativo.",
  cache:
    "Guarda temporariamente dados muito acessados na memória RAM, evitando buscar no banco toda vez. Acelera o sistema drasticamente. 'Nenhum' é válido apenas para sistemas simples ou de baixo acesso.",
  api_style:
    "O 'idioma' de comunicação entre o sistema e quem o consome. REST é o padrão universal. GraphQL deixa o cliente escolher exatamente o que quer. gRPC é otimizado para comunicação entre serviços internos de alta performance. WebSocket mantém conexão aberta para tempo real.",
  message_broker:
    "Permite que partes do sistema se comuniquem sem esperar resposta imediata — como uma caixa postal. Essencial para tarefas demoradas (envio de email, processamento de arquivos, notificações) e integração entre sistemas diferentes.",
  deploy_strategy:
    "Como o sistema será empacotado e executado nos servidores. Docker cria um contêiner portátil. Kubernetes gerencia múltiplos contêineres com escala automática. Serverless executa apenas quando chamado, sem servidor fixo.",
  extra_stack:
    "Bibliotecas e ferramentas complementares que o sistema vai usar além do stack principal. Ex: Celery para tarefas em segundo plano, Elasticsearch para buscas avançadas, MinIO para armazenamento de arquivos.",
  personas:
    "Personas são perfis dos usuários reais do sistema. Definir quem vai usar o sistema guia decisões de interface, funcionalidades e segurança. Ex: 'Carlos, gerente financeiro, 48 anos, usa celular, precisa aprovar pagamentos rapidamente e não tem muita paciência com tecnologia'.",
};

// ── WarningTooltip (vermelho — incompatibilidade) ──────────────────────────────

function WarningTooltip({ message }: { message: string }) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [tipStyle, setTipStyle] = useState<React.CSSProperties>({});

  useEffect(() => {
    if (!open || !btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const tipWidth = 288;
    const margin = 8;
    let left = rect.left;
    if (left + tipWidth > window.innerWidth - margin) left = window.innerWidth - tipWidth - margin;
    if (left < margin) left = margin;
    setTipStyle({ position: "fixed", top: rect.bottom + 6, left, width: tipWidth, zIndex: 9999 });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (btnRef.current?.contains(e.target as Node) || tipRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <span className="relative inline-flex items-center ml-1">
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen(v => !v)}
        className="text-red-400 hover:text-red-300 focus:outline-none"
        aria-label="Ver aviso de incompatibilidade"
      >
        <HelpCircle size={13} />
      </button>
      {open && (
        <div ref={tipRef} style={tipStyle}
          className="rounded-lg bg-gray-900 border border-red-700 p-3 shadow-xl text-xs text-red-200 leading-relaxed">
          <div className="flex items-start gap-1.5">
            <AlertTriangle size={11} className="text-red-400 mt-0.5 shrink-0" />
            <span>{message}</span>
          </div>
        </div>
      )}
    </span>
  );
}

// ── SelectField com HelpIcon e WarningTooltip ─────────────────────────────────

function SelectField({
  fieldKey, label, options, value, onChange, disabled, required, warning,
}: {
  fieldKey?: string;
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  required?: boolean;
  warning?: string;
}) {
  const helpText = fieldKey ? FIELD_HELP[fieldKey] : undefined;
  const hasWarning = !!warning && !!value;
  return (
    <div>
      <label className="flex items-center text-xs text-gray-400 mb-1 gap-0.5">
        <span>{label}{required && <span className="text-red-400 ml-0.5">*</span>}</span>
        {helpText && <HelpIcon text={helpText} />}
        {hasWarning && <WarningTooltip message={warning!} />}
      </label>
      <select
        value={value || ""}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        className={clsx(
          "w-full bg-dark border text-sm rounded-lg px-3 py-2 focus:outline-none transition-colors",
          disabled
            ? "border-gray-800 text-gray-600 cursor-not-allowed opacity-40"
            : hasWarning
              ? "border-red-600 text-red-300 focus:border-red-500"
              : "border-gray-700 text-gray-200 focus:border-violet-500",
          required && !value && !disabled ? "border-amber-700/50" : "",
        )}
      >
        <option value="">— Selecione —</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

// ── SectionHeader ──────────────────────────────────────────────────────────────

function SectionHeader({
  icon: Icon, title, locked, help,
}: {
  icon: React.ElementType; title: string; locked?: boolean; help?: string;
}) {
  return (
    <div className="flex items-center gap-2 text-white font-semibold mb-4">
      <Icon size={15} className={locked ? "text-gray-600" : "text-violet-400"} />
      <span className={locked ? "text-gray-500" : ""}>{title}</span>
      {help && !locked && <HelpIcon text={help} />}
      {locked && (
        <span className="flex items-center gap-1 text-xs text-gray-600 font-normal ml-1">
          <Lock size={10} /> Selecione a linguagem primeiro
        </span>
      )}
    </div>
  );
}

// ── Componente principal ───────────────────────────────────────────────────────

export function ArguidorPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [techStack, setTechStack] = useState<Record<string, string | string[]>>({});
  const [extraStack, setExtraStack] = useState<string[]>([]);
  const [extraSearch, setExtraSearch] = useState("");
  const [languageSearch, setLanguageSearch] = useState("");
  const [saved, setSaved] = useState(false);
  const [toolConflicts, setToolConflicts] = useState<string[]>([]);

  // ── Language Research State (Phase 3B) ────────────────────────────────────
  const [researchJobId, setResearchJobId] = useState<string>("");
  const [researchStatus, setResearchStatus] = useState<"idle" | "researching" | "completed" | "failed">("idle");
  const [researchMessage, setResearchMessage] = useState<string>("");
  const [researchAttempts, setResearchAttempts] = useState(0);
  const [researchSource, setResearchSource] = useState<"cache" | "fresh">("cache");

  // ── Queries para Language Stack (Phase 3) ────────────────────────────────────
  const { data: supportedLanguagesData } = useQuery({
    queryKey: ["supported-languages", projectId],
    queryFn: () => languageStackApi.getSupportedLanguages(projectId!),
  });

  const selectedLanguageState = (techStack.language as string) || "";
  const { data: languageStacksData } = useQuery({
    queryKey: ["stacks-for-language", projectId, selectedLanguageState],
    queryFn: () => languageStackApi.getStacksForLanguage(projectId!, selectedLanguageState),
    enabled: !!selectedLanguageState,
  });

  const { data, isLoading, isError, error } = useQuery<{ success: boolean; data: Plan }>({
    queryKey: ["argumentation-plan", projectId],
    queryFn: () => api.get(`/projects/${projectId}/argumentation/plan`).then(r => r.data),
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  useEffect(() => {
    if (!data) return;
    const plan = data.data;
    if (plan.stack_form?.current) {
      setTechStack(plan.stack_form.current);
      const extra = plan.stack_form.current["extra_stack"];
      if (Array.isArray(extra)) setExtraStack(extra as string[]);
    }
  }, [data]);

  // ── Effect: Trigger language research when language is selected (Phase 3B) ──
  useEffect(() => {
    if (!selectedLanguageState || researchStatus !== "idle") return;

    const startResearch = async () => {
      try {
        const result = await languageStackApi.startLanguageResearch(projectId!, selectedLanguageState);

        if (result.status === "cached") {
          // Dados frescos do cache (pesquisa anterior completada)
          setResearchMessage(`✅ Carregado do histórico`);
          setResearchSource("cache");
          setResearchStatus("completed");
          return;
        }

        // Status is "researching" - start polling
        setResearchStatus("researching");
        setResearchMessage(`🔍 Analisando o ecossistema de ${selectedLanguageState}...`);
        setResearchJobId(result.job_id);
        setResearchAttempts(0);
      } catch (error) {
        setResearchStatus("failed");
        setResearchMessage(`⚠️ Não foi possível pesquisar. Carregando dados conhecidos...`);
      }
    };

    startResearch();
  }, [selectedLanguageState, projectId]);

  // ── Effect: Poll language research results (Phase 3B) ──
  useEffect(() => {
    // Poll when actively researching
    if (!researchJobId || researchStatus !== "researching") return;

    const pollInterval = setInterval(async () => {
      try {
        const pollResult = await languageStackApi.pollLanguageResearch(
          projectId!,
          selectedLanguageState,
          researchJobId
        );

        if (pollResult.status === "completed") {
          setResearchStatus("completed");
          setResearchSource("fresh");

          // Update languageStacksData with fresh results
          if (pollResult.result) {
            const stackCount =
              (pollResult.result.frameworks?.length || 0) +
              (pollResult.result.orms?.length || 0) +
              (pollResult.result.test_frameworks?.length || 0) +
              (pollResult.result.build_tools?.length || 0);

            setResearchMessage(`✅ Encontrado ${stackCount} componentes. Pronto para usar!`);
          }
          clearInterval(pollInterval);
        } else if (pollResult.status === "failed") {
          setResearchStatus("failed");
          setResearchMessage(`⚠️ Análise não foi concluída. Usando dados padrão...`);
          clearInterval(pollInterval);
        } else {
          // Still researching — update attempt counter
          setResearchAttempts(prev => {
            const newAttempts = prev + 1;
            const elapsed = Math.floor(newAttempts / 2);
            if (elapsed > 0) {
              setResearchMessage(`🔍 Analisando ${selectedLanguageState}... (${elapsed}s)`);
            }
            if (newAttempts > 60) {
              // Timeout after 60 seconds
              setResearchStatus("failed");
              setResearchMessage(`⚠️ Análise levou muito tempo. Usando dados padrão...`);
              clearInterval(pollInterval);
            }
            return newAttempts;
          });
        }
      } catch (error) {
        setResearchAttempts(prev => prev + 1);
        if (researchAttempts > 60) {
          // Timeout
          setResearchStatus("failed");
          setResearchMessage(`⚠️ Sem conexão com internet. Usando dados em cache.`);
          clearInterval(pollInterval);
        }
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, [researchJobId, researchStatus, selectedLanguageState, projectId]);

  const mutation = useMutation({
    mutationFn: (payload: object) =>
      api.post(`/projects/${projectId}/argumentation/responses`, payload),
    onSuccess: () => {
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["argumentation-plan", projectId] });
      setTimeout(() => setSaved(false), 3000);
    },
  });

  const rerunMutation = useMutation({
    mutationFn: () => api.post(`/projects/${projectId}/gatekeeper`, {}).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["argumentation-plan", projectId] });
      queryClient.invalidateQueries({ queryKey: ["gatekeeper", projectId] });
    },
  });

  function getInfraWarning(field: string): string | undefined {
    const warnings = data?.data?.stack_form?.options?.infra_warnings || {};
    return warnings[field]?.[(techStack[field] as string) || ""];
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleStackChange = (field: string, value: string) => {
    if (field === "language") {
      setTechStack(prev => {
        const next: Record<string, string | string[]> = { ...prev, language: value };
        if (data?.data?.stack_form?.lang_fields) {
          data.data.stack_form.lang_fields.forEach(f => { delete next[f]; });
        }
        return next;
      });
      setToolConflicts([]);
      setLanguageSearch(""); // Clear search filter when language is selected
    } else {
      setTechStack(prev => ({ ...prev, [field]: value }));
    }
  };

  const applyPreset = (preset: Record<string, string>) => {
    const next: Record<string, string | string[]> = {};
    Object.entries(preset).forEach(([k, v]) => { next[k] = v; });
    setTechStack(next);
    setExtraStack([]);
    setToolConflicts([]);
  };

  const checkConflicts = (stack: string[]) => {
    const incompatible = form.options.incompatible_tools || [];
    setToolConflicts(stack.filter(v =>
      incompatible.some(ic => ic.includes(v.toLowerCase()) || v.toLowerCase().includes(ic))
    ));
  };

  const handleToggleExtra = (v: string) => {
    const next = extraStack.includes(v)
      ? extraStack.filter(x => x !== v)
      : [...extraStack, v];
    setExtraStack(next);
    checkConflicts(next);
  };

  const handleSave = () => {
    mutation.mutate({
      evaluation_id: plan.evaluation_id,
      tech_stack: { ...techStack, extra_stack: extraStack },
      qa_responses: [],
    });
  };

  // ── Render ────────────────────────────────────────────────────────────────

  // Guard: projectId não disponível
  if (!projectId) {
    return (
      <div className="flex items-center justify-center min-h-screen text-gray-400">
        <p>Projeto não encontrado</p>
      </div>
    );
  }

  // Guard: carregando
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-violet-400 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-400">Carregando decisões técnicas...</p>
        </div>
      </div>
    );
  }

  // Guard: erro ao carregar
  if (isError) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="max-w-md bg-red-900/20 border border-red-700 rounded-lg p-6 text-center">
          <AlertTriangle size={32} className="text-red-400 mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-red-300 mb-2">Erro ao carregar Arguidor</h2>
          <p className="text-sm text-gray-400 mb-4">
            {error instanceof Error ? error.message : "Falha na conexão com o servidor"}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm rounded-lg transition-colors"
          >
            Recarregar página
          </button>
        </div>
      </div>
    );
  }

  // Guard: dados não carregados
  if (!data || !data.data) {
    return (
      <div className="flex items-center justify-center min-h-screen text-gray-400">
        <p>Dados não disponíveis. Tente recarregar a página.</p>
      </div>
    );
  }

  // Now we know data.data exists, safe to destructure
  const plan = data.data as Plan;
  const form = plan.stack_form;
  const selectedLanguage = (techStack.language as string) || "";
  const isLocked = !selectedLanguage;
  const langOpts = selectedLanguage ? (form.options.by_language[selectedLanguage] || {}) : {};
  const infraWarnings = form.options.infra_warnings || {};
  const extraSuggestions = form.options.extra_stack_suggestions || [];
  const filteredSuggestions = extraSearch
    ? extraSuggestions.filter(s => s.toLowerCase().includes(extraSearch.toLowerCase()))
    : extraSuggestions;
  const availableLanguages = supportedLanguagesData?.supported_languages || form.available_languages || [];
  const filteredLanguages = languageSearch
    ? availableLanguages.filter(lang => lang.toLowerCase().includes(languageSearch.toLowerCase()))
    : availableLanguages;
  const relevantPresets = Object.entries(form.scenario_defaults).filter(
    ([, p]) => !selectedLanguage || p.language === selectedLanguage
  );

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-10">

      {/* Version Notifications Banner (Phase 3) */}
      <VersionNotificationBanner projectId={projectId} />

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <MessageSquare size={20} className="text-violet-400" />
            Arguidor Técnico
            <HelpIcon text="Define o stack tecnológico do projeto: linguagem, frameworks, banco de dados e infraestrutura. Essas decisões são injetadas automaticamente em cada geração de código, garantindo consistência técnica em todo o projeto." />
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Defina a linguagem e o stack. As decisões aqui são a base para a geração de código.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {plan.last_updated && (
            <span className="text-xs text-gray-500">
              Salvo em {new Date(plan.last_updated).toLocaleString("pt-BR")}
            </span>
          )}
          <button
            onClick={() => rerunMutation.mutate()}
            disabled={rerunMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 text-xs rounded-lg border border-gray-700 transition-colors"
          >
            <RefreshCw size={12} className={rerunMutation.isPending ? "animate-spin" : ""} />
            {rerunMutation.isPending ? "Avaliando…" : "Re-avaliar Gatekeeper"}
          </button>
        </div>
      </div>

      {/* Score do Gatekeeper */}
      {plan.evaluation_score !== null && (
        <div className="text-sm text-gray-400">
          Última avaliação Gatekeeper:{" "}
          <span className={`font-bold ${plan.evaluation_score >= 70 ? "text-green-400" : "text-red-400"}`}>
            {plan.evaluation_score.toFixed(0)}/100
          </span>
        </div>
      )}

      {/* ══ SEÇÃO 1 — CONTEXTO DO PROJETO ══════════════════════════════════════ */}
      <section className={clsx(
        "bg-dark-100 rounded-xl border p-5 transition-opacity",
        isLocked ? "border-gray-800 opacity-50 pointer-events-none" : "border-gray-800"
      )}>
        <SectionHeader
          icon={Layers}
          title="Contexto do projeto"
          locked={isLocked}
          help="Define o tipo e o perfil geral do sistema. Essas escolhas ajudam a orientar a arquitetura e os padrões recomendados."
        />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <SelectField
            fieldKey="application_type"
            label={form.fields.application_type}
            options={form.options.application_type}
            value={(techStack.application_type as string) || ""}
            onChange={v => handleStackChange("application_type", v)}
            disabled={isLocked}
          />
          <SelectField
            fieldKey="architecture_profile"
            label={form.fields.architecture_profile}
            options={form.options.architecture_profile}
            value={(techStack.architecture_profile as string) || ""}
            onChange={v => handleStackChange("architecture_profile", v)}
            disabled={isLocked}
          />
          <SelectField
            fieldKey="runtime_or_platform"
            label={form.fields.runtime_or_platform}
            options={langOpts.runtime_or_platform || []}
            value={(techStack.runtime_or_platform as string) || ""}
            onChange={v => handleStackChange("runtime_or_platform", v)}
            disabled={isLocked}
          />
        </div>
      </section>

      {/* ══ SEÇÃO 2 — LINGUAGEM PRINCIPAL ══════════════════════════════════════ */}
      <section className="bg-dark-100 rounded-xl border border-violet-800/50 p-5">
        <div className="flex items-center gap-2 text-white font-semibold mb-3">
          <Code2 size={15} className="text-violet-400" />
          Linguagem principal
          <span className="text-red-400 text-xs ml-1">obrigatória</span>
          <HelpIcon text="A linguagem principal é o alicerce de todo o projeto. Ao selecioná-la, todos os outros campos — frameworks, ORM, testes, pacotes — serão filtrados para mostrar apenas opções compatíveis com esse ecossistema." />
        </div>
        <p className="text-xs text-gray-500 mb-4">
          Todos os campos abaixo se adaptam automaticamente à linguagem escolhida.
        </p>

        {/* Dropdown Combobox para linguagens */}
        <div className="relative">
          <Combobox value={selectedLanguage} onChange={(value: string | null) => { if (value) handleStackChange("language", value); }}>
            <div className="relative">
              <Combobox.Input
                className="w-full bg-dark border border-gray-700 rounded-lg px-4 py-3 text-gray-200 placeholder-gray-500 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500/50 transition-colors"
                placeholder={selectedLanguage ? "Buscar linguagem..." : "👇 Clique aqui para escolher a linguagem de codificação"}
                displayValue={(lang: string) => lang}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLanguageSearch(e.target.value)}
              />
              <Combobox.Button className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200">
                <ChevronDown size={18} />
              </Combobox.Button>
            </div>

            <Combobox.Options className="absolute z-50 w-full mt-2 bg-dark-100 border border-gray-700 rounded-lg shadow-xl max-h-64 overflow-y-auto">
              {filteredLanguages.length === 0 ? (
                <div className="px-4 py-3 text-gray-500 text-sm">
                  Nenhuma linguagem encontrada
                </div>
              ) : (
                filteredLanguages.map((lang) => (
                  <Combobox.Option
                    key={lang}
                    value={lang}
                    className={({ active, selected }: { active: boolean; selected: boolean }) =>
                      clsx(
                        "px-4 py-3 cursor-pointer text-sm transition-colors border-b border-gray-800 last:border-b-0",
                        active ? "bg-violet-600/30 text-violet-300" : "text-gray-300",
                        selected ? "bg-violet-600/50 text-white font-medium" : ""
                      )
                    }
                  >
                    {lang}
                  </Combobox.Option>
                ))
              )}
            </Combobox.Options>
          </Combobox>
        </div>

        {!selectedLanguage && (
          <p className="text-xs text-amber-400/80 mt-3 flex items-center gap-1.5">
            <Lock size={11} /> Selecione a linguagem para desbloquear os demais campos.
          </p>
        )}

        {/* Language Research Status (Phase 3B) */}
        {selectedLanguage && researchStatus !== "idle" && (
          <div className="mt-4 p-3 bg-dark rounded-lg border border-gray-700">
            {researchStatus === "researching" && (
              <div className="flex items-center gap-2 text-sm text-violet-300">
                <div className="inline-block animate-spin">⏳</div>
                {researchMessage}
              </div>
            )}
            {researchStatus === "completed" && (
              <div className="text-sm text-green-400">
                ✓ {researchMessage}
              </div>
            )}
            {researchStatus === "failed" && (
              <div className="text-sm text-amber-400">
                {researchMessage}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Presets — após escolher linguagem */}
      {relevantPresets.length > 0 && (
        <section>
          <p className="text-xs text-gray-500 mb-2 flex items-center gap-1.5">
            <Zap size={11} className="text-violet-400" />
            Preencher automaticamente com configuração pré-definida:
          </p>
          <div className="flex flex-wrap gap-2">
            {relevantPresets.map(([name, preset]) => (
              <button
                key={name}
                onClick={() => applyPreset(preset)}
                className="px-3 py-1.5 text-xs bg-violet-900/30 hover:bg-violet-900/50 text-violet-300 border border-violet-700/40 rounded-lg transition-colors"
              >
                {name}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* ══ SEÇÃO 3 — STACK TÉCNICO ═════════════════════════════════════════════ */}
      <section className={clsx(
        "bg-dark-100 rounded-xl border p-5 transition-opacity",
        isLocked ? "border-gray-800 opacity-50 pointer-events-none" : "border-gray-800"
      )}>
        <SectionHeader
          icon={Wrench}
          title="Stack técnico"
          locked={isLocked}
          help="Ferramentas e bibliotecas específicas da linguagem selecionada. Apenas opções compatíveis são exibidas."
        />
        {selectedLanguage && (
          <p className="text-xs text-violet-400/70 mb-4 flex items-center gap-1.5">
            <Code2 size={11} />
            Exibindo apenas opções compatíveis com <strong>{selectedLanguage}</strong>
          </p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SelectField
            fieldKey="framework"
            label={form.fields.framework}
            options={languageStacksData?.stacks.frameworks?.map(f => f.name) || langOpts.framework || []}
            value={(techStack.framework as string) || ""}
            onChange={v => handleStackChange("framework", v)}
            disabled={isLocked}
          />
          <SelectField
            fieldKey="orm_odm"
            label={form.fields.orm_odm}
            options={languageStacksData?.stacks.orms?.map(o => o.name) || langOpts.orm_odm || []}
            value={(techStack.orm_odm as string) || ""}
            onChange={v => handleStackChange("orm_odm", v)}
            disabled={isLocked}
          />
          <SelectField
            fieldKey="test_framework"
            label={form.fields.test_framework}
            options={languageStacksData?.stacks.test_frameworks?.map(t => t.name) || langOpts.test_framework || []}
            value={(techStack.test_framework as string) || ""}
            onChange={v => handleStackChange("test_framework", v)}
            disabled={isLocked}
          />
          <SelectField
            fieldKey="build_or_package"
            label={form.fields.build_or_package}
            options={languageStacksData?.stacks.build_tools?.map(b => b.name) || langOpts.build_or_package || []}
            value={(techStack.build_or_package as string) || ""}
            onChange={v => handleStackChange("build_or_package", v)}
            disabled={isLocked}
          />
        </div>
      </section>

      {/* ══ SEÇÃO 4 — INFRAESTRUTURA ════════════════════════════════════════════ */}
      <section className="bg-dark-100 rounded-xl border border-gray-800 p-5">
        <SectionHeader
          icon={Server}
          title="Infraestrutura"
          help="Componentes de suporte ao sistema: banco de dados, autenticação, cache, comunicação e deploy. São independentes da linguagem, mas alguns podem ter ressalvas de compatibilidade."
        />
        {selectedLanguage && Object.keys(infraWarnings).length > 0 && (
          <p className="text-xs text-amber-400/70 mb-3 flex items-center gap-1.5">
            <AlertTriangle size={10} />
            Itens em vermelho têm ressalvas para <strong>{selectedLanguage}</strong> — clique no ícone vermelho para detalhes.
          </p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SelectField
            fieldKey="database"
            label={form.fields.database}
            options={form.options.database}
            value={(techStack.database as string) || ""}
            onChange={v => handleStackChange("database", v)}
            warning={getInfraWarning("database")}
          />
          <SelectField
            fieldKey="authentication"
            label={form.fields.authentication}
            options={form.options.authentication}
            value={(techStack.authentication as string) || ""}
            onChange={v => handleStackChange("authentication", v)}
            warning={getInfraWarning("authentication")}
          />
          <SelectField
            fieldKey="cache"
            label={form.fields.cache}
            options={form.options.cache}
            value={(techStack.cache as string) || ""}
            onChange={v => handleStackChange("cache", v)}
            warning={getInfraWarning("cache")}
          />
          <SelectField
            fieldKey="api_style"
            label={form.fields.api_style}
            options={form.options.api_style}
            value={(techStack.api_style as string) || ""}
            onChange={v => handleStackChange("api_style", v)}
            warning={getInfraWarning("api_style")}
          />
          <SelectField
            fieldKey="message_broker"
            label={form.fields.message_broker}
            options={form.options.message_broker}
            value={(techStack.message_broker as string) || ""}
            onChange={v => handleStackChange("message_broker", v)}
            warning={getInfraWarning("message_broker")}
          />
          <SelectField
            fieldKey="deploy_strategy"
            label={form.fields.deploy_strategy}
            options={form.options.deploy_strategy}
            value={(techStack.deploy_strategy as string) || ""}
            onChange={v => handleStackChange("deploy_strategy", v)}
            warning={getInfraWarning("deploy_strategy")}
          />
        </div>
      </section>

      {/* ══ SEÇÃO 5 — TECNOLOGIAS ADICIONAIS ════════════════════════════════════ */}
      <section className={clsx(
        "bg-dark-100 rounded-xl border p-5 space-y-4 transition-opacity",
        isLocked ? "border-gray-800 opacity-50 pointer-events-none" : "border-gray-800"
      )}>
        <SectionHeader
          icon={Database}
          title="Tecnologias adicionais"
          locked={isLocked}
          help={FIELD_HELP.extra_stack}
        />

        {/* Tags selecionadas */}
        {extraStack.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {extraStack.map(v => {
              const isConflict = toolConflicts.includes(v);
              return (
                <span key={v} className={clsx(
                  "flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border font-medium",
                  isConflict
                    ? "bg-red-900/30 text-red-300 border-red-700"
                    : "bg-violet-900/40 text-violet-200 border-violet-600"
                )}>
                  {isConflict && <AlertTriangle size={9} />}
                  {v}
                  <button onClick={() => handleToggleExtra(v)} className="ml-0.5 hover:text-white">
                    ×
                  </button>
                </span>
              );
            })}
          </div>
        )}

        {/* Aviso de conflito */}
        {toolConflicts.length > 0 && (
          <div className="bg-red-900/20 border border-red-700 rounded-lg p-3 space-y-1">
            <p className="text-xs text-red-300 font-semibold flex items-center gap-1.5">
              <AlertTriangle size={12} /> Ferramenta incompatível com {selectedLanguage}
            </p>
            {toolConflicts.map(c => (
              <p key={c} className="text-xs text-red-300/80">
                <span className="line-through">{c}</span>
                {" "}→ substitua por uma opção nativa do ecossistema {selectedLanguage}.
              </p>
            ))}
          </div>
        )}

        {/* Combo de sugestões */}
        {selectedLanguage && extraSuggestions.length > 0 && (
          <div className="border border-gray-800 rounded-lg overflow-hidden">
            <div className="px-3 py-2 bg-gray-900/50 border-b border-gray-800 flex items-center gap-2">
              <input
                type="text"
                value={extraSearch}
                onChange={e => setExtraSearch(e.target.value)}
                placeholder={`Buscar tecnologia compatível com ${selectedLanguage}…`}
                className="flex-1 bg-transparent text-xs text-gray-300 placeholder-gray-600 focus:outline-none"
              />
              {extraSearch && (
                <button onClick={() => setExtraSearch("")} className="text-gray-600 hover:text-gray-400 text-xs">×</button>
              )}
            </div>
            <div className="p-2.5 flex flex-wrap gap-1.5 max-h-44 overflow-y-auto">
              {filteredSuggestions.map(sug => {
                const sel = extraStack.includes(sug);
                return (
                  <button
                    key={sug}
                    onClick={() => handleToggleExtra(sug)}
                    className={clsx(
                      "text-xs px-2.5 py-1 rounded-full border transition-all",
                      sel
                        ? "bg-violet-700 border-violet-500 text-white"
                        : "bg-dark border-gray-700 text-gray-400 hover:border-violet-600 hover:text-gray-200"
                    )}
                  >
                    {sel && "✓ "}{sug}
                  </button>
                );
              })}
              {filteredSuggestions.length === 0 && (
                <p className="text-xs text-gray-600 px-1 py-1">Nenhuma sugestão encontrada.</p>
              )}
            </div>
          </div>
        )}

        {/* Notas de arquitetura */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            {form.fields.architecture_notes}
          </label>
          <textarea
            rows={3}
            value={(techStack.architecture_notes as string) || ""}
            onChange={e => handleStackChange("architecture_notes", e.target.value)}
            placeholder="Padrões, restrições ou decisões arquiteturais relevantes…"
            className="w-full bg-dark border border-gray-700 text-gray-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500 resize-none"
          />
        </div>
      </section>

      {/* ══ SEÇÃO 6 — PERSONAS ══════════════════════════════════════════════════ */}
      <section className="bg-dark-100 rounded-xl border border-gray-800 p-5">
        <SectionHeader
          icon={Users}
          title="Personas do projeto"
          help={FIELD_HELP.personas}
        />
        <p className="text-xs text-gray-500 mb-3">
          Descreva quem são os usuários reais do sistema. Isso orienta decisões de interface, segurança e funcionalidades.
        </p>
        <textarea
          rows={5}
          value={(techStack.personas as string) || ""}
          onChange={e => handleStackChange("personas", e.target.value)}
          placeholder={
            "Ex:\n• Maria, 45 anos, gerente de compras. Usa o sistema pelo celular para aprovar pedidos. Pouca familiaridade com tecnologia.\n• João, 28 anos, analista de TI. Responsável por configurar integrações e monitorar logs.\n• Carlos, 52 anos, diretor financeiro. Acessa apenas o painel de relatórios uma vez por semana."
          }
          className="w-full bg-dark border border-gray-700 text-gray-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500 resize-none"
        />
      </section>

      {/* Botão Salvar */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleSave}
          disabled={mutation.isPending || !selectedLanguage || toolConflicts.length > 0}
          className="px-6 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
          title={
            !selectedLanguage ? "Selecione a linguagem antes de salvar"
              : toolConflicts.length > 0 ? "Remova as ferramentas incompatíveis antes de salvar"
              : undefined
          }
        >
          {mutation.isPending ? "Salvando…" : "Salvar Decisões Técnicas"}
        </button>

        {!selectedLanguage && (
          <span className="text-xs text-gray-500 flex items-center gap-1">
            <Lock size={11} /> Selecione a linguagem para habilitar o salvamento
          </span>
        )}
        {toolConflicts.length > 0 && selectedLanguage && (
          <span className="text-xs text-red-400 flex items-center gap-1">
            <AlertTriangle size={11} /> Corrija as ferramentas incompatíveis antes de salvar
          </span>
        )}
        {saved && (
          <span className="flex items-center gap-1.5 text-green-400 text-sm">
            <CheckCircle size={14} /> Salvo! O próximo codegen usará este contexto.
          </span>
        )}
        {mutation.isError && (
          <span className="text-red-400 text-sm">Erro ao salvar. Tente novamente.</span>
        )}
      </div>

      {/* Aviso: perguntas de arguição foram movidas */}
      <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-4 text-xs text-gray-500 flex items-start gap-2">
        <MessageSquare size={13} className="text-violet-400/60 mt-0.5 shrink-0" />
        <span>
          As <strong className="text-gray-400">Perguntas de Arguição</strong> do Gatekeeper foram movidas para a etapa de{" "}
          <strong className="text-violet-400">Consolidação</strong>, onde fazem mais sentido — após todos os artefatos terem sido verificados.
        </span>
      </div>

    </div>
  );
}
