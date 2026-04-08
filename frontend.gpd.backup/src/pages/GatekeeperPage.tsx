import { useState, useEffect, useRef } from "react";
import { HelpIcon } from "@/components/HelpIcon";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  ShieldCheck,
  ShieldX,
  ShieldAlert,
  Play,
  ChevronDown,
  ChevronRight,
  X,
  CheckCircle,
  AlertCircle,
  Lightbulb,
  FileSearch,
  AlertTriangle,
  FolderX,
  PlusCircle,
  ArrowRight,
  Info,
  FolderTree,
  Code2,
  CheckCircle2,
  Clock,
  Lock,
} from "lucide-react";
import { toast } from "react-hot-toast";
import clsx from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Pillar {
  id: string;
  pillar: string;
  score: number;
  is_blocking: boolean;
  summary: string;
  score_justification: string | null;
  recommendations: string[];
  what_to_add: string[];
}

interface Gap {
  id: string;
  pillar: string;
  severity: "show_stopper" | "critical" | "high" | "medium" | "low";
  description: string;
  recommendation: string | null;
  responsible: string | null;
  dismissed: boolean;
}

interface PlanModule {
  id: string;
  name: string;
  description: string;
  file_path: string;
  layer: "infrastructure" | "data" | "business" | "api" | "presentation";
  priority: number;
  dependencies: string[];
  built: boolean;
  requirements_detail: string;
  // Prontidão de construção (manifesto § 5)
  readiness?: "full" | "partial" | "blocked";
  missing_pillars?: string[];
  blocking_reason?: string | null;
  can_generate_stub?: boolean;
  pillar_origin?: string;
}

interface ArgPlanItem {
  theme: string;
  pillar: string;
  questions: string[];
  priority: "critical" | "high" | "medium";
}

interface BlockingMatrixItem {
  file_path: string;
  module_name: string;
  status: "blocked" | "partial";
  reason: string;
  missing_pillars: string[];
  missing_artifact: string;
  can_generate_stub: boolean;
}

interface Evaluation {
  id: string;
  overall_score: number;
  status: "pending" | "running" | "approved" | "blocked" | "approved_with_override" | "failed";
  ai_provider_used: string;
  ai_model_used: string;
  executed_by: string;
  override_justification: string | null;
  document_coverage: number;
  improvement_suggestions: string[];
  missing_documents: { category: string; title: string; description: string; priority: string; pillar: string }[];
  advance_requirements: string[];
  module_plan: PlanModule[];
  directory_tree: string | null;
  // Motor de prontidão de engenharia
  argumentation_plan: ArgPlanItem[];
  blocking_matrix: BlockingMatrixItem[];
  created_at: string;
  error_message?: string | null;
  progress_label?: string | null;
  pillars: Pillar[];
  gaps: Gap[];
}

// ─── Constants ───────────────────────────────────────────────────────────────

// Labels dos 7 pilares documentais do manifesto + aliases legados para retrocompatibilidade
const PILLAR_LABELS: Record<string, string> = {
  // Novos (7 pilares documentais)
  business_requirements:       "P1 — Negociais",
  business_rules:              "P2 — Regras de Negócio",
  functional_requirements:     "P3 — Funcionais",
  non_functional_requirements: "P4 — Não Funcionais",
  solution_architecture:       "P5 — Arquitetura",
  data_integration_legacy:     "P6 — Dados/Integrações",
  security_compliance_qa:      "P7 — Segurança/QA",
  // Legados (avaliações anteriores ao alinhamento)
  functional:     "Funcional",
  business:       "Negócio",
  capacity:       "Capacidade",
  non_functional: "Não-Funcional",
  exceptions:     "Exceções",
  ux:             "UX/Usabilidade",
  compliance:     "Conformidade",
};

const SEVERITY_ORDER = ["show_stopper", "critical", "high", "medium", "low"] as const;

const SEVERITY_LABELS: Record<string, string> = {
  show_stopper: "Show Stopper",
  critical: "Crítico",
  high: "Alto",
  medium: "Médio",
  low: "Baixo",
};

const LAYER_ORDER: PlanModule["layer"][] = [
  "infrastructure", "data", "business", "api", "presentation",
];

const LAYER_LABELS: Record<PlanModule["layer"], string> = {
  infrastructure: "Infraestrutura",
  data: "Dados",
  business: "Negócio",
  api: "API",
  presentation: "Apresentação",
};

const LAYER_COLORS: Record<PlanModule["layer"], string> = {
  infrastructure: "bg-orange-900/40 text-orange-300 border-orange-700/40",
  data: "bg-blue-900/40 text-blue-300 border-blue-700/40",
  business: "bg-violet-900/40 text-violet-300 border-violet-700/40",
  api: "bg-cyan-900/40 text-cyan-300 border-cyan-700/40",
  presentation: "bg-pink-900/40 text-pink-300 border-pink-700/40",
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 70) return "text-emerald-400";
  if (score >= 40) return "text-amber-400";
  return "text-red-400";
}

function scoreBarColor(score: number): string {
  if (score >= 70) return "bg-emerald-500";
  if (score >= 40) return "bg-amber-500";
  return "bg-red-500";
}

function severityBadgeClass(severity: string): string {
  switch (severity) {
    case "show_stopper":
      return "bg-red-600/80 text-white border border-red-500 animate-pulse";
    case "critical":
      return "bg-red-900/60 text-red-300 border border-red-700/50";
    case "high":
      return "badge-high";
    case "medium":
      return "badge-medium";
    case "low":
      return "badge-low";
    default:
      return "badge-low";
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR");
}

// ─── Sub-components ──────────────────────────────────────────────────────────

const STEPS = [
  "Carregando documentos do projeto...",
  "Acionando agentes de pré-análise (n8n)...",
  "Avaliando os 7 pilares com IA (pode levar 2–4 min)...",
  "Registrando pilares, lacunas e roadmap...",
];
// Tempo estimado por etapa (segundos acumulados até o final da etapa)
const STEP_THRESHOLDS = [5, 40, 240, 260];
const TOTAL_EXPECTED_SEC = 280;

function EvaluationProgressBanner({
  status,
  progressLabel,
  startedAt,
}: {
  status: string;
  progressLabel?: string | null;
  startedAt?: string;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = startedAt ? new Date(startedAt).getTime() : Date.now();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  // Progresso baseado em tempo, máximo 97% até concluir
  const pct = Math.min(97, Math.round((elapsed / TOTAL_EXPECTED_SEC) * 100));

  // Label: usa o do backend se disponível, senão inferido pelo tempo
  const inferredLabel = (() => {
    for (let i = 0; i < STEP_THRESHOLDS.length; i++) {
      if (elapsed < STEP_THRESHOLDS[i]) return STEPS[i];
    }
    return STEPS[STEPS.length - 1];
  })();
  const label = progressLabel || (status === "pending" ? "Aguardando início..." : inferredLabel);

  // Minutos e segundos decorridos
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const elapsedStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

  return (
    <div className="bg-violet-900/20 border border-violet-600/50 rounded-xl px-4 py-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Clock size={16} className="text-violet-400 shrink-0 animate-spin" style={{ animationDuration: "3s" }} />
          <span className="text-sm font-semibold text-violet-300">
            {status === "pending" ? "Aguardando início..." : "Avaliação em andamento"}
          </span>
        </div>
        <span className="text-xs text-violet-500 tabular-nums">{elapsedStr}</span>
      </div>

      {/* Barra de progresso */}
      <div className="w-full bg-violet-900/40 rounded-full h-2 overflow-hidden">
        <div
          className="h-2 rounded-full bg-violet-500 transition-all duration-1000 ease-linear"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-violet-400 leading-relaxed">{label}</p>
        <span className="text-xs font-semibold text-violet-400 tabular-nums shrink-0">{pct}%</span>
      </div>
    </div>
  );
}

function PillarCard({ pillar }: { pillar: Pillar }) {
  const [open, setOpen] = useState(false);
  const hasDetails = !!(
    pillar.score_justification ||
    pillar.what_to_add?.length > 0 ||
    pillar.recommendations?.length > 0
  );

  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-semibold text-gray-200 uppercase tracking-wide">
            {PILLAR_LABELS[pillar.pillar] ?? pillar.pillar}
          </span>
          {pillar.is_blocking && (
            <span className="text-xs font-bold text-red-400 bg-red-900/40 border border-red-700/50 px-2 py-0.5 rounded-full w-fit">
              BLOQUEANTE
            </span>
          )}
        </div>
        <span className={clsx("text-3xl font-extrabold tabular-nums", scoreColor(pillar.score))}>
          {pillar.score}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-dark-200 rounded-full h-1.5">
        <div
          className={clsx("h-1.5 rounded-full transition-all", scoreBarColor(pillar.score))}
          style={{ width: `${pillar.score}%` }}
        />
      </div>

      <p className="text-xs text-gray-400 leading-relaxed">{pillar.summary}</p>

      {hasDetails && (
        <button
          onClick={() => setOpen((p) => !p)}
          className="flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 transition-colors mt-1 self-start"
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {open ? "Ocultar detalhes" : "Ver justificativa e ações"}
        </button>
      )}

      {open && (
        <div className="space-y-3 mt-1">
          {/* Por que esta nota */}
          {pillar.score_justification && (
            <div className="rounded-lg bg-dark-200/60 px-3 py-2.5 space-y-1">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wide">
                <Info size={12} className="text-amber-400" />
                Por que esta nota
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">{pillar.score_justification}</p>
            </div>
          )}

          {/* O que adicionar */}
          {pillar.what_to_add?.length > 0 && (
            <div className="rounded-lg bg-dark-200/60 px-3 py-2.5 space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wide">
                <PlusCircle size={12} className="text-emerald-400" />
                O que adicionar para melhorar
              </div>
              <ul className="space-y-1">
                {pillar.what_to_add.map((item, i) => (
                  <li key={i} className="text-xs text-gray-300 flex gap-2">
                    <ArrowRight size={12} className="text-emerald-500 mt-0.5 shrink-0" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Recomendações */}
          {pillar.recommendations?.length > 0 && (
            <ul className="space-y-1">
              {pillar.recommendations.map((rec, i) => (
                <li key={i} className="text-xs text-gray-400 flex gap-2">
                  <span className="text-violet-500 mt-0.5 shrink-0">•</span>
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function GapItem({
  gap,
  onDismiss,
  canDismiss,
}: {
  gap: Gap;
  onDismiss: (id: string) => void;
  canDismiss: boolean;
}) {
  return (
    <div
      className={clsx(
        "card border-l-4 transition-opacity",
        gap.dismissed ? "opacity-40 line-through" : "",
        gap.severity === "show_stopper" ? "border-l-red-600 bg-red-950/20" :
        gap.severity === "critical" ? "border-l-red-500" :
        gap.severity === "high" ? "border-l-red-400" :
        gap.severity === "medium" ? "border-l-amber-400" :
        "border-l-emerald-500"
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex flex-col gap-1 flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={clsx("text-xs px-2 py-0.5 rounded-full font-semibold", severityBadgeClass(gap.severity))}>
              {SEVERITY_LABELS[gap.severity]}
            </span>
            <span className="text-xs text-gray-500 bg-dark-200 px-2 py-0.5 rounded-full">
              {PILLAR_LABELS[gap.pillar] ?? gap.pillar}
            </span>
            {gap.dismissed && (
              <span className="text-xs text-gray-600 italic">Descartado</span>
            )}
          </div>
          <p className="text-sm text-gray-200 mt-1">{gap.description}</p>
          {gap.recommendation && (
            <p className="text-xs text-gray-400 mt-0.5">
              <span className="text-violet-400 font-medium">Recomendação:</span> {gap.recommendation}
            </p>
          )}
          {gap.responsible && (
            <p className="text-xs text-gray-500 mt-0.5">
              <span className="font-medium">Responsável:</span> {gap.responsible}
            </p>
          )}
        </div>
        {!gap.dismissed && canDismiss && (
          <button
            onClick={() => onDismiss(gap.id)}
            className="shrink-0 text-xs text-gray-500 hover:text-red-400 transition-colors flex items-center gap-1 mt-0.5"
          >
            <X size={13} /> Descartar
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Module Plan Section ──────────────────────────────────────────────────────

function ModulePlanSection({
  modules,
  directoryTree,
}: {
  modules: PlanModule[];
  directoryTree: string | null;
}) {
  const [treeOpen, setTreeOpen] = useState(false);
  const [expandedModule, setExpandedModule] = useState<string | null>(null);

  const builtCount = modules.filter((m) => m.built).length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-200 flex items-center gap-2">
          <Code2 size={18} className="text-violet-400" />
          Plano de Desenvolvimento
          <span className="text-sm font-normal text-gray-500">
            ({modules.length} módulos · {builtCount} construídos)
          </span>
        </h2>
      </div>

      {/* Directory tree */}
      {directoryTree && (
        <div className="card border border-gray-700/40 bg-dark-100">
          <button
            className="w-full flex items-center justify-between text-left"
            onClick={() => setTreeOpen((v) => !v)}
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-gray-300">
              <FolderTree size={14} className="text-amber-400" />
              Árvore de Diretórios
            </span>
            {treeOpen ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
          </button>
          {treeOpen && (
            <pre className="mt-3 text-xs font-mono text-gray-300 bg-dark rounded-lg p-4 overflow-x-auto leading-relaxed border border-gray-800">
              {directoryTree}
            </pre>
          )}
        </div>
      )}

      {/* Modules by layer */}
      {LAYER_ORDER.map((layer) => {
        const layerModules = modules
          .filter((m) => m.layer === layer)
          .sort((a, b) => a.priority - b.priority);
        if (layerModules.length === 0) return null;
        return (
          <div key={layer}>
            <h3 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-2 flex items-center gap-2">
              <span className={clsx("px-2 py-0.5 rounded text-xs border", LAYER_COLORS[layer])}>
                {LAYER_LABELS[layer]}
              </span>
              <span className="text-gray-600">{layerModules.length} módulo(s)</span>
            </h3>
            <div className="space-y-1.5">
              {layerModules.map((m) => (
                <div
                  key={m.id}
                  className={clsx(
                    "card border transition-colors cursor-pointer",
                    m.built
                      ? "border-emerald-700/30 bg-emerald-950/10"
                      : "border-gray-700/40 hover:border-gray-600/60"
                  )}
                  onClick={() => setExpandedModule(expandedModule === m.id ? null : m.id)}
                >
                  <div className="flex items-start gap-3">
                    {/* Priority badge */}
                    <span className="shrink-0 w-6 h-6 rounded bg-dark-200 text-gray-400 text-xs font-bold flex items-center justify-center mt-0.5">
                      {m.priority}
                    </span>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-gray-200">{m.name}</span>
                        {m.built ? (
                          <span className="flex items-center gap-1 text-xs text-emerald-400">
                            <CheckCircle2 size={11} /> Construído
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-gray-600">
                            <Clock size={11} /> Pendente
                          </span>
                        )}
                        {/* Badge de prontidão */}
                        {m.readiness === "partial" && (
                          <span className="text-xs text-amber-400 bg-amber-900/30 px-1.5 py-0.5 rounded">
                            parcial
                          </span>
                        )}
                        {m.readiness === "blocked" && (
                          <span className="text-xs text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">
                            bloqueado
                          </span>
                        )}
                        {m.dependencies.length > 0 && (
                          <span className="flex items-center gap-1 text-xs text-gray-600">
                            <Lock size={10} /> {m.dependencies.length} dep.
                          </span>
                        )}
                      </div>
                      <code className="text-xs text-violet-400 font-mono mt-0.5 block truncate">
                        {m.file_path}
                      </code>
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{m.description}</p>
                    </div>

                    <ChevronDown
                      size={14}
                      className={clsx(
                        "shrink-0 text-gray-600 transition-transform mt-1",
                        expandedModule === m.id && "rotate-180"
                      )}
                    />
                  </div>

                  {/* Expanded: requirements detail + blocking info */}
                  {expandedModule === m.id && (
                    <div className="mt-3 pt-3 border-t border-gray-700/40 space-y-2">
                      <p className="text-xs text-gray-400 leading-relaxed">{m.requirements_detail}</p>
                      {m.blocking_reason && (
                        <div className="rounded bg-red-950/30 border border-red-700/30 px-2.5 py-2">
                          <p className="text-xs text-red-400">
                            <span className="font-semibold">Motivo do bloqueio:</span> {m.blocking_reason}
                          </p>
                          {m.missing_pillars && m.missing_pillars.length > 0 && (
                            <div className="flex gap-1 flex-wrap mt-1">
                              {m.missing_pillars.map((p, pi) => (
                                <span key={pi} className="text-xs bg-dark-200 text-gray-500 px-1.5 py-0.5 rounded">
                                  {PILLAR_LABELS[p] ?? p}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                      {m.dependencies.length > 0 && (
                        <div className="flex items-start gap-1.5 flex-wrap">
                          <span className="text-xs text-gray-600">Depende de:</span>
                          {m.dependencies.map((dep) => {
                            const depModule = modules.find((x) => x.id === dep);
                            return (
                              <span
                                key={dep}
                                className={clsx(
                                  "text-xs px-1.5 py-0.5 rounded font-mono",
                                  depModule?.built
                                    ? "bg-emerald-900/30 text-emerald-400"
                                    : "bg-red-900/30 text-red-400"
                                )}
                              >
                                {depModule?.name ?? dep}
                                {!depModule?.built && " ⚠"}
                              </span>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function GatekeeperPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);

  const [modalOpen, setModalOpen] = useState(false);
  const [overrideModalOpen, setOverrideModalOpen] = useState(false);
  const [justification, setJustification] = useState("");
  const [overrideJustification, setOverrideJustification] = useState("");
  const [progress, setProgress] = useState(0);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [noChangesMsg, setNoChangesMsg] = useState<string | null>(null);

  const canDismissGap = ["tech_lead", "admin"].includes(user?.role ?? "");

  // Fetch latest evaluation — faz polling enquanto estiver pending/running
  const isInProgress = (status?: string) => status === "pending" || status === "running";
  const { data: evalData, isLoading } = useQuery({
    queryKey: ["gatekeeper", projectId],
    queryFn: async () => {
      const { data } = await api.get<{ success: boolean; data: Evaluation | null }>(
        `/projects/${projectId}/gatekeeper/latest`
      );
      return data.data;
    },
    enabled: !!projectId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return isInProgress(status) ? 5000 : false;
    },
  });

  // Fetch artifact count and master document to detect stale evaluation
  const { data: artifactsData } = useQuery({
    queryKey: ["artifacts-count", projectId],
    queryFn: () =>
      api.get<{ success: boolean; total: number }>(`/projects/${projectId}/artifacts`, {
        params: { limit: 1, offset: 0 },
      }).then(r => r.data),
    enabled: !!projectId,
    staleTime: 30_000,
  });
  const { data: verifiedArtifactsData } = useQuery({
    queryKey: ["artifacts-verified-count", projectId],
    queryFn: () =>
      api.get<{ success: boolean; total: number }>(`/projects/${projectId}/artifacts`, {
        params: { limit: 1, offset: 0, status: "verified" },
      }).then(r => r.data),
    enabled: !!projectId,
    staleTime: 30_000,
  });
  const { data: masterDocData } = useQuery({
    queryKey: ["master-document", projectId],
    queryFn: () =>
      api.get<{ success: boolean; data: { id: string; status: string; created_at: string; version_label: string } | null }>(
        `/projects/${projectId}/merge/master-document`
      ).then(r => r.data),
    enabled: !!projectId,
    staleTime: 30_000,
  });

  const artifactCount = artifactsData?.total ?? null;
  const verifiedCount = verifiedArtifactsData?.total ?? null;
  const masterDoc = masterDocData?.data ?? null;

  // Stale detection
  const hasNoArtifacts = artifactCount === 0;
  const hasNoVerifiedArtifacts = verifiedCount === 0 && artifactCount !== null && artifactCount > 0;
  const evalIsInvalid = hasNoArtifacts || hasNoVerifiedArtifacts;
  const hasMasterDoc = !!masterDoc;
  const masterDocNewerThanEval =
    masterDoc && evalData
      ? new Date(masterDoc.created_at) > new Date(evalData.created_at)
      : false;
  const evalIsStale = evalData && (hasNoArtifacts || masterDocNewerThanEval);

  // Detecta transição de running→final para exibir toast
  const prevEvalStatusRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    const prev = prevEvalStatusRef.current;
    const curr = evalData?.status;
    if (prev && isInProgress(prev) && curr && !isInProgress(curr)) {
      if (curr === "approved" || curr === "approved_with_override") {
        toast.success(`Avaliação concluída: ${curr === "approved_with_override" ? "aprovada com override" : "aprovada"} (score: ${evalData!.overall_score.toFixed(1)})`);
      } else if (curr === "blocked") {
        toast.error(`Avaliação concluída: bloqueada (score: ${evalData!.overall_score.toFixed(1)})`);
      } else if (curr === "failed") {
        toast.error(`Avaliação falhou. ${evalData?.error_message ?? ""}`);
      }
    }
    prevEvalStatusRef.current = curr;
  }, [evalData?.status]);

  // Run evaluation
  const runMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, string> = {};
      if (justification.trim()) body.override_justification = justification.trim();
      const { data } = await api.post<{ success: boolean; no_changes_detected?: boolean; pending?: boolean; message: string; data: Evaluation | null }>(
        `/projects/${projectId}/gatekeeper`,
        body,
      );
      return data;
    },
    onSuccess: (res) => {
      if (!res.success) {
        toast.error(res.message ?? "Não foi possível iniciar a avaliação.");
        return;
      }
      if (res.no_changes_detected) {
        setNoChangesMsg(res.message ?? "Nenhuma mudança detectada desde a última avaliação.");
        toast(res.message ?? "Resultado anterior reutilizado.", { icon: "ℹ️" });
      } else if (res.pending) {
        toast("Avaliação iniciada. Aguarde o resultado...", { icon: "⏳" });
        setNoChangesMsg(null);
      } else {
        setNoChangesMsg(null);
        toast.success(res.message ?? "Avaliação concluída.");
      }
      queryClient.invalidateQueries({ queryKey: ["gatekeeper", projectId] });
      setModalOpen(false);
      setJustification("");
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Não foi possível iniciar a avaliação.");
    },
  });

  const isEvaluating = runMutation.isPending || isInProgress(evalData?.status);

  // Animar barra de progresso durante avaliação (mutation + polling running)
  useEffect(() => {
    if (isEvaluating) {
      setProgress(0);
      progressRef.current = setInterval(() => {
        setProgress((p) => {
          if (p >= 88) { clearInterval(progressRef.current!); return 88; }
          return p + (88 - p) * 0.04 + 0.5;
        });
      }, 200);
    } else {
      if (progressRef.current) clearInterval(progressRef.current);
      setProgress((p) => {
        if (p > 0) setTimeout(() => setProgress(0), 800);
        return p > 0 ? 100 : 0;
      });
    }
    return () => { if (progressRef.current) clearInterval(progressRef.current); };
  }, [isEvaluating]);

  // Override sem re-avaliação
  const overrideMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.patch(
        `/projects/${projectId}/gatekeeper/${evalData?.id}/override`,
        { justification: overrideJustification.trim() }
      );
      return data;
    },
    onSuccess: (res) => {
      toast.success(res.message ?? "Override aplicado.");
      queryClient.invalidateQueries({ queryKey: ["gatekeeper", projectId] });
      setOverrideModalOpen(false);
      setOverrideJustification("");
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Não foi possível aplicar o override.");
    },
  });

  // Dismiss gap
  const dismissMutation = useMutation({
    mutationFn: async (gapId: string) => {
      const { data } = await api.patch(
        `/projects/${projectId}/gatekeeper/${evalData?.id}/gaps/${gapId}/dismiss`
      );
      return data;
    },
    onSuccess: () => {
      toast.success("Gap descartado.");
      queryClient.invalidateQueries({ queryKey: ["gatekeeper", projectId] });
    },
    onError: () => toast.error("Não foi possível descartar o gap. Esta ação é restrita a Tech Lead e Admin."),
  });

  // Radar data
  const radarData =
    evalData?.pillars.map((p) => ({
      subject: PILLAR_LABELS[p.pillar] ?? p.pillar,
      score: p.score,
    })) ?? [];

  // Gaps grouped
  const gapsBySeverity = SEVERITY_ORDER.map((sev) => ({
    severity: sev,
    items: evalData?.gaps.filter((g) => g.severity === sev) ?? [],
  })).filter((g) => g.items.length > 0);

  // P7 é bloqueante — verifica novo nome e legado para retrocompatibilidade
  const compliancePillar = evalData?.pillars.find(
    (p) => p.pillar === "security_compliance_qa" || p.pillar === "compliance"
  );
  const complianceBlocking = compliancePillar && compliancePillar.score < 60;
  // Override disponível quando bloqueado MAS P7 está ok (score geral baixo, não compliance)
  const canOverride = evalData?.status === "blocked" && !complianceBlocking && canDismissGap;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <ShieldCheck size={24} className="text-violet-400" />
          Gatekeeper — Motor de Prontidão
          <HelpIcon text="O Gatekeeper avalia os 7 pilares documentais do manifesto GPD. P7 (Segurança/Compliance/QA) é bloqueante com score < 60. Para os demais pilares, prontidão parcial permite geração de stubs rastreáveis." />
        </h1>
        <div className="flex items-center gap-2">
          {canOverride && (
            <button
              className="btn-secondary flex items-center gap-2 border-amber-600/60 text-amber-300 hover:border-amber-500"
              onClick={() => setOverrideModalOpen(true)}
            >
              <ShieldAlert size={15} />
              Prosseguir para Código
            </button>
          )}
          <button
            className="btn-primary flex items-center gap-2"
            onClick={() => setModalOpen(true)}
            disabled={isEvaluating}
          >
            {isEvaluating ? (
              <>
                <Clock size={15} className="animate-spin" />
                {evalData?.status === "running" ? "Avaliando..." : "Iniciando..."}
              </>
            ) : (
              <>
                <Play size={15} />
                Executar Avaliação
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── Banner de avaliação em andamento ─────────────────────────────── */}
      {isInProgress(evalData?.status) && (
        <EvaluationProgressBanner
          status={evalData!.status}
          progressLabel={evalData?.progress_label}
          startedAt={evalData?.created_at}
        />
      )}

      {/* Banner de falha ─────────────────────────────────────────────────── */}
      {evalData?.status === "failed" && (
        <div className="flex items-center gap-3 bg-red-900/20 border border-red-700/50 rounded-xl px-4 py-3">
          <AlertCircle size={18} className="text-red-400 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-300">Avaliação anterior falhou</p>
            {evalData.error_message && (
              <p className="text-xs text-red-500 mt-0.5">{evalData.error_message}</p>
            )}
            <p className="text-xs text-red-500 mt-0.5">Clique em "Executar Avaliação" para tentar novamente.</p>
          </div>
        </div>
      )}

      {/* ── Staleness / workflow banners ─────────────────────────────────── */}

      {/* Sem artefatos e sem avaliação → guia do fluxo */}
      {!isLoading && !evalData && artifactCount === 0 && (
        <div className="card border border-gray-700/60 px-5 py-5 space-y-3">
          <div className="flex items-center gap-2 text-gray-300 font-semibold">
            <Info size={16} className="text-violet-400 shrink-0" />
            Como funciona o fluxo de avaliação
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="px-2.5 py-1 rounded-lg bg-dark-200 border border-gray-700 text-xs font-medium text-gray-300">1. Artefatos</span>
            <ArrowRight size={14} className="text-gray-600 shrink-0" />
            <span className="px-2.5 py-1 rounded-lg bg-dark-200 border border-gray-700 text-xs font-medium text-gray-300">2. Consolidação</span>
            <ArrowRight size={14} className="text-gray-600 shrink-0" />
            <span className="px-2.5 py-1 rounded-lg bg-violet-900/40 border border-violet-700/60 text-xs font-medium text-violet-300">3. Gatekeeper</span>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">
            Faça upload dos documentos do projeto em <strong className="text-gray-400">Artefatos</strong>, execute a
            <strong className="text-gray-400"> Consolidação</strong> para gerar o Documento Mestre e depois
            clique em <strong className="text-gray-400">Executar Avaliação</strong> aqui.
          </p>
        </div>
      )}

      {/* Tem avaliação mas sem documento mestre → sugerir Consolidação */}
      {!isLoading && evalData && !hasMasterDoc && (
        <div className="flex items-start gap-3 bg-violet-900/20 border border-violet-700/40 rounded-xl px-4 py-3">
          <Info size={16} className="text-violet-400 mt-0.5 shrink-0" />
          <p className="text-sm text-gray-300">
            Esta avaliação foi feita sem Documento Mestre consolidado. Execute a{" "}
            <strong className="text-violet-300">Consolidação</strong> e depois re-avalie para resultados mais precisos.
          </p>
        </div>
      )}

      {/* Sem artefatos verificados — artefatos existem mas nenhum está verificado */}
      {!isLoading && hasNoVerifiedArtifacts && (
        <div className="flex items-start gap-3 bg-amber-900/20 border border-amber-700/50 rounded-xl px-4 py-3">
          <AlertTriangle size={16} className="text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-300">Nenhum artefato verificado</p>
            <p className="text-xs text-amber-500 mt-0.5">
              Existem artefatos no projeto, mas nenhum está com status <strong>verified</strong>.
              Altere o status dos artefatos desejados para <strong>verified</strong> e re-execute.
            </p>
          </div>
        </div>
      )}

      {/* Avaliação desatualizada — artefatos foram removidos */}
      {!isLoading && evalIsStale && hasNoArtifacts && (
        <div className="flex items-start gap-3 bg-amber-900/20 border border-amber-700/50 rounded-xl px-4 py-3">
          <AlertTriangle size={16} className="text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-300">Avaliação desatualizada</p>
            <p className="text-xs text-amber-500 mt-0.5">
              Todos os artefatos foram removidos após esta avaliação. Adicione novos artefatos, execute a
              Consolidação e re-avalie para obter resultados válidos.
            </p>
          </div>
        </div>
      )}

      {/* Documento Mestre mais recente que a avaliação */}
      {!isLoading && evalIsStale && masterDocNewerThanEval && !hasNoArtifacts && (
        <div className="flex items-start gap-3 bg-blue-900/20 border border-blue-700/50 rounded-xl px-4 py-3">
          <AlertTriangle size={16} className="text-blue-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-blue-300">Documento Mestre atualizado</p>
            <p className="text-xs text-blue-400 mt-0.5">
              Existe um Documento Mestre consolidado mais recente que esta avaliação
              {masterDoc?.version_label ? ` (${masterDoc.version_label})` : ""}. Re-execute o Gatekeeper para
              refletir os novos artefatos.
            </p>
          </div>
        </div>
      )}

      {/* Nenhuma mudança detectada — resultado anterior reutilizado */}
      {noChangesMsg && (
        <div className="flex items-start gap-3 bg-gray-800/60 border border-gray-600 rounded-xl px-4 py-3">
          <Info size={16} className="text-gray-400 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="text-sm text-gray-300">{noChangesMsg}</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Para forçar uma nova avaliação, adicione ou atualize artefatos antes de executar novamente.
            </p>
          </div>
          <button onClick={() => setNoChangesMsg(null)} className="text-gray-600 hover:text-gray-400 mt-0.5">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="card text-center text-gray-500 py-10">Carregando avaliação...</div>
      )}

      {/* No evaluation yet */}
      {!isLoading && !evalData && artifactCount !== 0 && (
        <div className="card text-center text-gray-500 py-10">
          Nenhuma avaliação realizada. Clique em "Executar Avaliação" para iniciar.
        </div>
      )}

      {evalData && !evalIsInvalid && (
        <>
          {/* Status banner */}
          {evalData.status === "approved" && (
            <div className="flex items-center gap-3 bg-emerald-900/30 border border-emerald-700/50 rounded-xl px-4 py-3">
              <CheckCircle size={20} className="text-emerald-400 shrink-0" />
              <div>
                <span className="font-semibold text-emerald-300">
                  Aprovado — Score: {evalData.overall_score.toFixed(1)}/100
                </span>
                <p className="text-xs text-emerald-500 mt-0.5">
                  Executado por {evalData.executed_by} em {formatDate(evalData.created_at)} · {evalData.ai_provider_used} / {evalData.ai_model_used}
                </p>
              </div>
            </div>
          )}

          {evalData.status === "blocked" && (
            <div className="flex items-center gap-3 bg-red-900/30 border border-red-600/60 rounded-xl px-4 py-3 animate-pulse">
              <ShieldX size={20} className="text-red-400 shrink-0" />
              <div>
                <span className="font-semibold text-red-300">
                  BLOQUEADO — Compliance insuficiente. Geração de código desabilitada.
                </span>
                <p className="text-xs text-red-500 mt-0.5">
                  Score: {evalData.overall_score.toFixed(1)}/100 · {evalData.ai_provider_used} / {evalData.ai_model_used} · {formatDate(evalData.created_at)}
                </p>
              </div>
            </div>
          )}

          {evalData.status === "approved_with_override" && (
            <div className="flex items-center gap-3 bg-amber-900/30 border border-amber-700/50 rounded-xl px-4 py-3">
              <ShieldAlert size={20} className="text-amber-400 shrink-0" />
              <div>
                <span className="font-semibold text-amber-300">
                  Aprovado com Override — Score: {evalData.overall_score.toFixed(1)}/100
                </span>
                {evalData.override_justification && (
                  <p className="text-xs text-amber-500 mt-0.5">
                    Justificativa: {evalData.override_justification}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* P7 compliance warning */}
          {complianceBlocking && (
            <div className="flex items-start gap-3 bg-red-950/50 border border-red-800/60 rounded-xl px-4 py-3">
              <AlertCircle size={18} className="text-red-400 mt-0.5 shrink-0" />
              <p className="text-sm text-red-300">
                <span className="font-bold">Bloqueio P7:</span> O pilar{" "}
                <strong>Segurança, Compliance e QA</strong> está com score crítico ({compliancePillar?.score}/100).
                Score mínimo exigido: 60. Corrija as não-conformidades de segurança e LGPD antes de gerar código.
              </p>
            </div>
          )}

          {/* Sugestões de melhoria — não bloqueadores */}
          {evalData.advance_requirements?.length > 0 && (
            <div className="card border border-gray-700/40 bg-gray-900/20 space-y-3">
              <div className="flex items-center gap-2">
                <ArrowRight size={16} className="text-gray-400" />
                <h2 className="text-sm font-semibold text-gray-300">
                  Sugestões de Melhoria da Documentação
                </h2>
                <span className="text-xs text-gray-600 bg-gray-800 px-2 py-0.5 rounded-full">opcional</span>
              </div>
              <p className="text-xs text-gray-500">
                Itens opcionais sugeridos pela IA para enriquecer a documentação. O projeto pode avançar para geração de código sem atendê-los.
              </p>
              <ul className="space-y-2">
                {evalData.advance_requirements.map((req, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm text-gray-400">
                    <span className="mt-0.5 shrink-0 w-5 h-5 rounded-full text-xs font-bold flex items-center justify-center bg-gray-700/60 text-gray-400">
                      {i + 1}
                    </span>
                    <span>{req}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Pillars grid */}
          <div>
            <h2 className="text-lg font-semibold text-gray-200 mb-3">Pilares de Qualidade</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {evalData.pillars.map((p) => (
                <PillarCard key={p.id} pillar={p} />
              ))}
            </div>
          </div>

          {/* Radar chart */}
          {radarData.length > 0 && (
            <div className="card">
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">
                Visão Radar dos Pilares
              </h2>
              <ResponsiveContainer width="100%" height={300}>
                <RadarChart data={radarData} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
                  <PolarGrid stroke="#374151" />
                  <PolarAngleAxis
                    dataKey="subject"
                    tick={{ fill: "#9ca3af", fontSize: 11 }}
                  />
                  <Radar
                    name="Score"
                    dataKey="score"
                    stroke="#7C3AED"
                    fill="#7C3AED"
                    fillOpacity={0.25}
                    strokeWidth={2}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151", borderRadius: 8 }}
                    labelStyle={{ color: "#e5e7eb" }}
                    itemStyle={{ color: "#a78bfa" }}
                    formatter={(v: number) => [`${v}/100`, "Score"]}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Cobertura da documentação */}
          {evalData.document_coverage > 0 && (
            <div className="card space-y-2">
              <div className="flex items-center gap-2">
                <FileSearch size={16} className="text-violet-400" />
                <h2 className="text-sm font-semibold text-gray-300">Cobertura da Documentação Analisada</h2>
                <span className={clsx(
                  "ml-auto text-sm font-bold tabular-nums",
                  evalData.document_coverage >= 70 ? "text-emerald-400" :
                  evalData.document_coverage >= 40 ? "text-amber-400" : "text-red-400"
                )}>
                  {evalData.document_coverage.toFixed(0)}%
                </span>
              </div>
              <div className="w-full bg-dark-200 rounded-full h-3 overflow-hidden">
                <div
                  className={clsx("h-3 rounded-full transition-all duration-700", scoreBarColor(evalData.document_coverage))}
                  style={{ width: `${evalData.document_coverage}%` }}
                />
              </div>
              <p className="text-xs text-gray-500">
                {evalData.document_coverage >= 70
                  ? "Boa cobertura — a documentação permite análise confiável."
                  : evalData.document_coverage >= 40
                  ? "Cobertura parcial — adicione mais artefatos para uma análise mais precisa."
                  : "Cobertura insuficiente — a análise pode não refletir o estado real do projeto."}
              </p>
            </div>
          )}

          {/* Gaps */}
          {gapsBySeverity.length > 0 && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-200">
                Gaps Identificados
                <span className="ml-2 text-sm font-normal text-gray-500">
                  ({evalData.gaps.length} total)
                </span>
              </h2>
              {gapsBySeverity.map(({ severity, items }) => (
                <div key={severity}>
                  <h3 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-2 flex items-center gap-2">
                    <span className={clsx("w-2 h-2 rounded-full", {
                      "bg-red-600 animate-pulse": severity === "show_stopper",
                      "bg-red-500": severity === "critical",
                      "bg-red-400": severity === "high",
                      "bg-amber-400": severity === "medium",
                      "bg-emerald-500": severity === "low",
                    })} />
                    {SEVERITY_LABELS[severity]} ({items.length})
                  </h3>
                  <div className="space-y-2">
                    {items.map((gap) => (
                      <GapItem
                        key={gap.id}
                        gap={gap}
                        canDismiss={canDismissGap}
                        onDismiss={(id) => dismissMutation.mutate(id)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          {/* Documentos faltantes */}
          {evalData.missing_documents?.length > 0 && (
            <div className="card border border-red-700/30 bg-red-950/10 space-y-3">
              <div className="flex items-center gap-2">
                <FolderX size={16} className="text-red-400" />
                <h2 className="text-sm font-semibold text-red-300">
                  Documentos Necessários para Completude
                </h2>
                <span className="ml-auto text-xs text-red-500 bg-red-900/30 px-2 py-0.5 rounded-full">
                  {evalData.missing_documents.length} pendente(s)
                </span>
              </div>
              <p className="text-xs text-gray-500">
                Envie os artefatos abaixo para aumentar a completude da documentação e melhorar o score do Gatekeeper.
              </p>
              <div className="space-y-2">
                {evalData.missing_documents.map((doc, i) => (
                  <div key={i} className="flex gap-3 rounded-lg bg-dark px-3 py-2.5">
                    <div className="shrink-0 mt-0.5">
                      <AlertTriangle size={14} className={clsx(
                        doc.priority === "critical" ? "text-red-400" :
                        doc.priority === "high" ? "text-orange-400" :
                        doc.priority === "medium" ? "text-amber-400" : "text-gray-500"
                      )} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-semibold text-gray-200">{doc.title}</span>
                        <span className="text-xs text-gray-600 bg-dark-200 px-1.5 py-0.5 rounded">
                          {PILLAR_LABELS[doc.pillar] ?? doc.pillar}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">{doc.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sugestões de melhoria */}
          {evalData.improvement_suggestions?.length > 0 && (
            <div className="card border border-violet-700/30 bg-violet-950/10 space-y-3">
              <div className="flex items-center gap-2">
                <Lightbulb size={16} className="text-violet-400" />
                <h2 className="text-sm font-semibold text-violet-300">
                  Sugestões de Melhoria da Documentação
                </h2>
              </div>
              <ul className="space-y-2">
                {evalData.improvement_suggestions.map((suggestion, i) => (
                  <li key={i} className="flex gap-3 text-sm text-gray-300">
                    <span className="mt-0.5 shrink-0 w-5 h-5 rounded-full bg-violet-600/30 text-violet-400 text-xs font-bold flex items-center justify-center">
                      {i + 1}
                    </span>
                    <span>{suggestion}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ── Plano de Arguição ── */}
          {evalData.argumentation_plan?.length > 0 && (
            <div className="card border border-amber-700/30 bg-amber-950/10 space-y-4">
              <div className="flex items-center gap-2">
                <AlertTriangle size={16} className="text-amber-400" />
                <h2 className="text-sm font-semibold text-amber-300">
                  Plano de Arguição — Perguntas Técnicas Pendentes
                </h2>
                <span className="ml-auto text-xs text-amber-500 bg-amber-900/30 px-2 py-0.5 rounded-full">
                  {evalData.argumentation_plan.length} tema(s) em aberto
                </span>
              </div>
              <p className="text-xs text-gray-500">
                Responda às perguntas abaixo para aumentar a prontidão de construção do projeto.
                As respostas devem ser adicionadas como artefatos no pilar correspondente.
              </p>
              <div className="space-y-3">
                {evalData.argumentation_plan.map((item, i) => (
                  <div key={i} className={clsx(
                    "rounded-lg border px-4 py-3 space-y-2",
                    item.priority === "critical"
                      ? "border-red-700/40 bg-red-950/10"
                      : item.priority === "high"
                      ? "border-orange-700/40 bg-orange-950/10"
                      : "border-amber-700/30 bg-amber-950/10"
                  )}>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-gray-200 uppercase tracking-wide">
                        {item.theme}
                      </span>
                      <span className="text-xs text-gray-500 bg-dark-200 px-1.5 py-0.5 rounded">
                        {PILLAR_LABELS[item.pillar] ?? item.pillar}
                      </span>
                      <span className={clsx(
                        "ml-auto text-xs px-2 py-0.5 rounded-full font-semibold",
                        item.priority === "critical" ? "text-red-300 bg-red-900/40" :
                        item.priority === "high" ? "text-orange-300 bg-orange-900/40" :
                        "text-amber-300 bg-amber-900/40"
                      )}>
                        {item.priority === "critical" ? "Crítico" : item.priority === "high" ? "Alto" : "Médio"}
                      </span>
                    </div>
                    <ul className="space-y-1.5">
                      {item.questions.map((q, qi) => (
                        <li key={qi} className="flex gap-2 text-xs text-gray-300">
                          <span className="text-amber-500 shrink-0 mt-0.5">?</span>
                          <span>{q}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Matriz de Bloqueios ── */}
          {evalData.blocking_matrix?.length > 0 && (
            <div className="card border border-red-700/30 bg-red-950/10 space-y-3">
              <div className="flex items-center gap-2">
                <FolderX size={16} className="text-red-400" />
                <h2 className="text-sm font-semibold text-red-300">
                  Matriz de Bloqueios — Módulos que não podem ser gerados completamente
                </h2>
                <span className="ml-auto text-xs text-red-500 bg-red-900/30 px-2 py-0.5 rounded-full">
                  {evalData.blocking_matrix.filter(m => m.status === "blocked").length} bloqueado(s) ·{" "}
                  {evalData.blocking_matrix.filter(m => m.status === "partial").length} parcial(is)
                </span>
              </div>
              <p className="text-xs text-gray-500">
                Módulos bloqueados podem ter stubs rastreáveis gerados. Adicione os artefatos indicados
                para desbloquear a geração completa.
              </p>
              <div className="space-y-2">
                {evalData.blocking_matrix.map((item, i) => (
                  <div key={i} className={clsx(
                    "rounded-lg border px-3 py-2.5 space-y-1.5",
                    item.status === "blocked"
                      ? "border-red-700/40 bg-red-950/10"
                      : "border-amber-700/30 bg-amber-950/10"
                  )}>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={clsx(
                        "text-xs font-bold px-1.5 py-0.5 rounded",
                        item.status === "blocked"
                          ? "text-red-300 bg-red-900/40"
                          : "text-amber-300 bg-amber-900/40"
                      )}>
                        {item.status === "blocked" ? "BLOQUEADO" : "PARCIAL"}
                      </span>
                      <span className="text-xs font-semibold text-gray-200">{item.module_name}</span>
                      {item.can_generate_stub && (
                        <span className="text-xs text-emerald-400 ml-auto">stub disponível</span>
                      )}
                    </div>
                    <code className="text-xs font-mono text-violet-400 block">{item.file_path}</code>
                    <p className="text-xs text-gray-400">{item.reason}</p>
                    <div className="flex items-start gap-2 flex-wrap">
                      {item.missing_pillars.map((p, pi) => (
                        <span key={pi} className="text-xs bg-dark-200 text-gray-400 px-1.5 py-0.5 rounded">
                          {PILLAR_LABELS[p] ?? p}
                        </span>
                      ))}
                      {item.missing_artifact && (
                        <span className="text-xs text-orange-400 ml-1">
                          ← Necessário: {item.missing_artifact}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Plano de Módulos ── */}
          {evalData.module_plan?.length > 0 && (
            <ModulePlanSection
              modules={evalData.module_plan}
              directoryTree={evalData.directory_tree}
            />
          )}

          {/* Geração pendente */}
          {(!evalData.module_plan || evalData.module_plan.length === 0) && (
            <div className="card border border-gray-700/40 text-center py-8 space-y-2">
              <Code2 size={32} className="mx-auto text-gray-600" />
              <p className="text-sm text-gray-500">
                Plano de módulos ainda não gerado para esta avaliação.
              </p>
              <p className="text-xs text-gray-600">
                Execute uma nova avaliação para gerar automaticamente o plano de desenvolvimento.
              </p>
            </div>
          )}
        </>
      )}

      {/* Modal: override / prosseguir para código */}
      {overrideModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-dark-100 border border-amber-700/50 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <ShieldAlert size={18} className="text-amber-400" />
                Prosseguir para Geração de Código
              </h3>
              <button
                onClick={() => { setOverrideModalOpen(false); setOverrideJustification(""); }}
                className="text-gray-500 hover:text-gray-300"
              >
                <X size={18} />
              </button>
            </div>

            <div className="rounded-lg bg-amber-900/20 border border-amber-700/40 px-3 py-2.5 text-xs text-amber-200 space-y-1">
              <p className="font-semibold">Score geral insuficiente, mas compliance está ok.</p>
              <p className="text-amber-400">
                Score atual: <strong>{evalData?.overall_score.toFixed(1)}/100</strong> (mínimo: 70).
                Como Tech Lead, você pode prosseguir sob sua responsabilidade.
              </p>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-gray-400 font-medium">
                Justificativa <span className="text-red-400">*</span>
                <span className="text-gray-600 font-normal"> — por que o projeto está pronto para geração de código?</span>
              </label>
              <textarea
                className="input-field text-sm resize-none"
                rows={4}
                placeholder="Ex: Os gaps identificados são não-críticos e serão endereçados na próxima sprint. O núcleo funcional está completamente especificado..."
                value={overrideJustification}
                onChange={(e) => setOverrideJustification(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                className="btn-secondary text-sm"
                onClick={() => { setOverrideModalOpen(false); setOverrideJustification(""); }}
                disabled={overrideMutation.isPending}
              >
                Cancelar
              </button>
              <button
                className="text-sm px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-semibold flex items-center gap-2 disabled:opacity-50 transition-colors"
                onClick={() => overrideMutation.mutate()}
                disabled={overrideMutation.isPending || overrideJustification.trim().length < 10}
              >
                {overrideMutation.isPending ? (
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <ShieldAlert size={14} />
                )}
                Confirmar Override
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: executar avaliação */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-dark-100 border border-gray-700 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Play size={18} className="text-violet-400" />
                Executar Avaliação Gatekeeper
              </h3>
              <button
                onClick={() => { setModalOpen(false); setJustification(""); }}
                className="text-gray-500 hover:text-gray-300 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            <p className="text-sm text-gray-400">
              A IA irá ler o conteúdo dos artefatos e avaliar os 7 pilares de qualidade. Isso pode levar alguns segundos.
            </p>

            {runMutation.isPending && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-gray-500">
                  <span>Analisando documentação...</span>
                  <span>{Math.round(progress)}%</span>
                </div>
                <div className="w-full bg-dark-200 rounded-full h-2 overflow-hidden">
                  <div
                    className="h-2 rounded-full bg-violet-500 transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="text-xs text-gray-600 italic">
                  {progress < 30 ? "Carregando artefatos..." : progress < 60 ? "Avaliando pilares de conformidade..." : progress < 85 ? "Identificando gaps e melhorias..." : "Finalizando análise..."}
                </p>
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs text-gray-400 font-medium">
                Justificativa de Override{" "}
                <span className="text-gray-600">(opcional — permite aprovar mesmo bloqueado)</span>
              </label>
              <textarea
                className="input-field text-sm resize-none"
                rows={3}
                placeholder="Descreva o motivo para forçar aprovação..."
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                className="btn-secondary text-sm"
                onClick={() => { setModalOpen(false); setJustification(""); }}
                disabled={runMutation.isPending}
              >
                Cancelar
              </button>
              <button
                className="btn-primary text-sm flex items-center gap-2"
                onClick={() => runMutation.mutate()}
                disabled={runMutation.isPending}
              >
                {runMutation.isPending ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Avaliando...
                  </>
                ) : (
                  <>
                    <Play size={14} /> Executar
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
