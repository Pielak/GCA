import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  GitMerge, FileText, AlertTriangle, CheckCircle, Clock,
  Loader2, Play, Eye, EyeOff, MessageSquare, ChevronDown, ChevronUp, Shield,
} from "lucide-react";
import { clsx } from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";
import { HelpIcon } from "@/components/HelpIcon";

interface Conflict {
  id: string;
  severity: "low" | "medium" | "high" | "critical";
  conflict_type: string | null;
  section_refs: { artifact_id: string; title: string }[];
  proposed_resolution: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
}

interface MasterDocSummary {
  id: string;
  version_label: string;
  status: string;
  approved_at: string | null;
}

interface MergeData {
  id: string;
  version_label: string;
  status: string;
  artifact_count: number;
  conflict_count: number;
  sections_count: number;
  created_at: string;
  conflicts: Conflict[];
  master_document: MasterDocSummary | null;
}

interface MasterDocument {
  id: string;
  version_label: string;
  status: string;
  content_markdown: string;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "text-red-400 bg-red-900/30 border-red-700/50",
  high:     "text-orange-400 bg-orange-900/30 border-orange-700/50",
  medium:   "text-amber-400 bg-amber-900/30 border-amber-700/50",
  low:      "text-gray-400 bg-gray-800 border-gray-700",
};

const STATUS_BADGES: Record<string, string> = {
  draft:          "bg-gray-800 text-gray-400 border-gray-700",
  processing:     "bg-blue-900/30 text-blue-400 border-blue-700/50",
  review_required:"bg-amber-900/30 text-amber-400 border-amber-700/50",
  published:      "bg-emerald-900/30 text-emerald-400 border-emerald-700/50",
  approved:       "bg-violet-900/30 text-violet-400 border-violet-700/50",
  superseded:     "bg-gray-800 text-gray-500 border-gray-700",
  failed:         "bg-red-900/30 text-red-400 border-red-700/50",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Rascunho", processing: "Processando", review_required: "Revisão Necessária",
  published: "Publicado", approved: "Aprovado", superseded: "Substituído", failed: "Falhou",
};

const CAN_WRITE = ["admin", "project_manager", "tech_lead"];

// ── Textos explicativos em linguagem leiga para as perguntas de arguição ──────
// Mapeamento por palavras-chave no tema da pergunta
function getQuestionHelp(theme: string, question: string): string {
  const t = (theme + " " + question).toLowerCase();
  if (t.includes("stack") || t.includes("tecnolog") || t.includes("framework"))
    return "Pergunta sobre as ferramentas e tecnologias escolhidas para construir o sistema. Explique as razões da escolha e como cada ferramenta se encaixa no projeto.";
  if (t.includes("banco") || t.includes("dados") || t.includes("database"))
    return "Pergunta sobre como e onde os dados serão armazenados. Detalhe o tipo de banco, volume esperado e estratégia de backup.";
  if (t.includes("segurança") || t.includes("autenticação") || t.includes("auth"))
    return "Pergunta sobre como o sistema protegerá os dados e controlará quem pode fazer o quê. Descreva o modelo de controle de acesso e proteções planejadas.";
  if (t.includes("performance") || t.includes("escala") || t.includes("sla"))
    return "Pergunta sobre o desempenho esperado do sistema. Informe quantos usuários simultâneos, tempo máximo de resposta e disponibilidade exigida.";
  if (t.includes("deploy") || t.includes("infraestrutura") || t.includes("servidor"))
    return "Pergunta sobre onde e como o sistema será instalado e mantido em funcionamento. Detalhe o ambiente (nuvem, on-premise) e a estratégia de atualização.";
  if (t.includes("exception") || t.includes("erro") || t.includes("falha") || t.includes("fallback"))
    return "Pergunta sobre o que acontece quando algo dá errado. Descreva como o sistema vai se comportar em caso de falha, timeout ou dado inválido.";
  if (t.includes("ux") || t.includes("interface") || t.includes("usuário") || t.includes("design"))
    return "Pergunta sobre a experiência do usuário. Descreva os padrões visuais, acessibilidade e como as telas foram ou serão desenhadas.";
  if (t.includes("lgpd") || t.includes("compliance") || t.includes("legal") || t.includes("privacidade"))
    return "Pergunta sobre conformidade com leis e regulamentos (especialmente LGPD). Detalhe como dados pessoais serão coletados, usados e protegidos.";
  if (t.includes("integração") || t.includes("api") || t.includes("externo"))
    return "Pergunta sobre como o sistema vai se comunicar com outros sistemas. Liste as integrações externas previstas e os contratos de API.";
  if (t.includes("teste") || t.includes("qa") || t.includes("qualidade"))
    return "Pergunta sobre a estratégia de testes. Descreva os tipos de testes planejados (unitários, integração, e2e) e critérios de qualidade.";
  return "Pergunta de contexto gerada pelo Gatekeeper para entender melhor o projeto. Responda de forma clara e objetiva, com base nas decisões já tomadas no Arguidor.";
}

interface ArgQuestion {
  question_id: string;
  theme: string;
  question: string;
  priority?: string;
}

interface QAResponse {
  question_id: string;
  theme: string;
  question: string;
  answer: string;
}

interface ArgPlan {
  evaluation_id: string | null;
  argumentation_questions: ArgQuestion[];
  qa_responses: QAResponse[];
  stack_form: { language: string | null };
}

const PRIORITY_COLORS: Record<string, string> = {
  high:   "bg-red-900/40 text-red-300 border border-red-700",
  medium: "bg-yellow-900/40 text-yellow-300 border border-yellow-700",
  low:    "bg-gray-800 text-gray-400 border border-gray-700",
};

export function MergePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const canWrite = CAN_WRITE.includes(user?.role ?? "");

  const [showMarkdown, setShowMarkdown] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolveText, setResolveText] = useState("");
  const [qaAnswers, setQaAnswers] = useState<Record<string, string>>({});
  const [expandedThemes, setExpandedThemes] = useState<Record<string, boolean>>({});
  const [qaSaved, setQaSaved] = useState(false);

  const { data: mergeData, isLoading } = useQuery<{ success: boolean; data: MergeData | null }>({
    queryKey: ["merge-latest", projectId],
    queryFn: () => api.get(`/projects/${projectId}/merge/latest`).then(r => r.data),
    enabled: !!projectId,
  });

  const { data: argPlanData } = useQuery<{ success: boolean; data: ArgPlan }>({
    queryKey: ["argumentation-plan", projectId],
    queryFn: () => api.get(`/projects/${projectId}/argumentation/plan`).then(r => r.data),
    enabled: !!projectId,
  });

  useEffect(() => {
    if (argPlanData?.data.qa_responses?.length) {
      const map: Record<string, string> = {};
      argPlanData.data.qa_responses.forEach((r: QAResponse) => { map[r.question_id] = r.answer; });
      setQaAnswers(map);
    }
  }, [argPlanData]);

  const qaMutation = useMutation({
    mutationFn: (payload: object) =>
      api.post(`/projects/${projectId}/argumentation/responses`, payload),
    onSuccess: () => {
      setQaSaved(true);
      queryClient.invalidateQueries({ queryKey: ["argumentation-plan", projectId] });
      setTimeout(() => setQaSaved(false), 3000);
    },
    onError: () => toast.error("Erro ao salvar perguntas de arguição."),
  });

  const { data: masterDocData } = useQuery<{ success: boolean; data: MasterDocument | null }>({
    queryKey: ["master-document", projectId],
    queryFn: () => api.get(`/projects/${projectId}/merge/master-document`).then(r => r.data),
    enabled: !!projectId,
  });

  const runMergeMutation = useMutation({
    mutationFn: () => api.post(`/projects/${projectId}/merge/run`, {}),
    onSuccess: () => {
      toast.success("Consolidação executada com sucesso!");
      queryClient.invalidateQueries({ queryKey: ["merge-latest", projectId] });
      queryClient.invalidateQueries({ queryKey: ["master-document", projectId] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao executar consolidação.");
    },
  });

  const approveMutation = useMutation({
    mutationFn: (docId: string) =>
      api.post(`/projects/${projectId}/merge/master-document/${docId}/approve`),
    onSuccess: () => {
      toast.success("Documento mestre aprovado!");
      queryClient.invalidateQueries({ queryKey: ["master-document", projectId] });
      queryClient.invalidateQueries({ queryKey: ["merge-latest", projectId] });
    },
    onError: () => toast.error("Erro ao aprovar documento."),
  });

  const resolveMutation = useMutation({
    mutationFn: ({ conflictId, notes }: { conflictId: string; notes: string }) =>
      api.patch(`/projects/${projectId}/merge/conflicts/${conflictId}/resolve`, { resolution_notes: notes }),
    onSuccess: () => {
      toast.success("Conflito resolvido!");
      queryClient.invalidateQueries({ queryKey: ["merge-latest", projectId] });
      setResolvingId(null);
      setResolveText("");
    },
    onError: () => toast.error("Erro ao resolver conflito."),
  });

  const merge = mergeData?.data;
  const masterDoc = masterDocData?.data;

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-10">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <GitMerge size={22} className="text-violet-400" />
            Consolidação Documental
            <HelpIcon text="Unifica todos os artefatos verificados do projeto em um único Documento Mestre versionado. Esse documento é a fonte primária que o Gatekeeper usa para avaliar os 7 pilares. Execute a Consolidação sempre que adicionar ou atualizar artefatos antes de rodar o Gatekeeper." />
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Consolida todos os artefatos elegíveis em um documento mestre versionado para avaliação pelo Gatekeeper.
          </p>
        </div>
        {canWrite && (
          <button
            onClick={() => runMergeMutation.mutate()}
            disabled={runMergeMutation.isPending}
            className="btn-primary flex items-center gap-2 shrink-0"
          >
            {runMergeMutation.isPending ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Play size={15} />
            )}
            {runMergeMutation.isPending ? "Consolidando…" : "Executar Consolidação"}
          </button>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 text-gray-500 gap-2">
          <Loader2 size={18} className="animate-spin" />
          Carregando…
        </div>
      )}

      {/* Master Document Card */}
      {masterDoc && (
        <div className="card border-violet-800/40 space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <FileText size={16} className="text-violet-400" />
              <span className="font-semibold text-white">Documento Mestre</span>
              <span className="font-mono text-xs text-violet-300">{masterDoc.version_label}</span>
              <span className={clsx(
                "text-xs px-2 py-0.5 rounded-full border",
                STATUS_BADGES[masterDoc.status] ?? STATUS_BADGES.draft
              )}>
                {STATUS_LABELS[masterDoc.status] ?? masterDoc.status}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowMarkdown(v => !v)}
                className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors"
              >
                {showMarkdown ? <EyeOff size={13} /> : <Eye size={13} />}
                {showMarkdown ? "Ocultar" : "Ver conteúdo"}
              </button>
              {canWrite && masterDoc.status === "published" && (
                <button
                  onClick={() => approveMutation.mutate(masterDoc.id)}
                  disabled={approveMutation.isPending}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-violet-700 hover:bg-violet-600 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  <CheckCircle size={12} />
                  Aprovar
                </button>
              )}
            </div>
          </div>

          {showMarkdown && (
            <div className="bg-dark rounded-lg p-4 max-h-96 overflow-y-auto">
              <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
                {masterDoc.content_markdown}
              </pre>
            </div>
          )}

          {masterDoc.approved_at && (
            <p className="text-xs text-gray-500">
              Aprovado em {new Date(masterDoc.approved_at).toLocaleString("pt-BR")}
            </p>
          )}
        </div>
      )}

      {/* Latest merge summary */}
      {merge && (
        <div className="card space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-3">
              <span className="font-semibold text-white">Última Consolidação</span>
              <span className="font-mono text-xs text-violet-300">{merge.version_label}</span>
              <span className={clsx(
                "text-xs px-2 py-0.5 rounded-full border",
                STATUS_BADGES[merge.status] ?? STATUS_BADGES.draft
              )}>
                {STATUS_LABELS[merge.status] ?? merge.status}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <Clock size={12} />
              {new Date(merge.created_at).toLocaleString("pt-BR")}
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Artefatos", value: merge.artifact_count },
              { label: "Seções", value: merge.sections_count },
              { label: "Conflitos", value: merge.conflict_count, warn: merge.conflict_count > 0 },
            ].map(({ label, value, warn }) => (
              <div key={label} className="bg-dark rounded-lg px-3 py-2 text-center">
                <p className={clsx("text-lg font-bold", warn ? "text-amber-400" : "text-violet-400")}>{value}</p>
                <p className="text-xs text-gray-500">{label}</p>
              </div>
            ))}
          </div>

          {/* Conflicts */}
          {merge.conflicts.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-gray-400 font-medium uppercase tracking-wider flex items-center gap-1.5">
                <AlertTriangle size={12} className="text-amber-400" />
                Conflitos a resolver
              </p>
              {merge.conflicts.map((c) => (
                <div key={c.id} className={clsx("rounded-lg border p-3 space-y-2", SEVERITY_COLORS[c.severity])}>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold uppercase">{c.severity}</span>
                      {c.conflict_type && (
                        <span className="text-xs opacity-70">{c.conflict_type}</span>
                      )}
                      {c.resolved_at && (
                        <span className="flex items-center gap-1 text-xs text-emerald-400">
                          <CheckCircle size={11} />
                          Resolvido
                        </span>
                      )}
                    </div>
                    {!c.resolved_at && canWrite && (
                      <button
                        onClick={() => setResolvingId(resolvingId === c.id ? null : c.id)}
                        className="text-xs px-2 py-1 rounded bg-dark/50 hover:bg-dark transition-colors"
                      >
                        {resolvingId === c.id ? "Cancelar" : "Resolver"}
                      </button>
                    )}
                  </div>

                  {c.proposed_resolution && (
                    <p className="text-xs opacity-80">{c.proposed_resolution}</p>
                  )}

                  {c.section_refs.length > 0 && (
                    <div className="text-xs opacity-60 space-y-0.5">
                      {c.section_refs.map((ref, i) => (
                        <p key={i}>· {ref.title} ({ref.artifact_id.slice(0, 8)}…)</p>
                      ))}
                    </div>
                  )}

                  {resolvingId === c.id && (
                    <div className="space-y-2 pt-1">
                      <textarea
                        rows={2}
                        value={resolveText}
                        onChange={e => setResolveText(e.target.value)}
                        placeholder="Descreva como o conflito foi resolvido…"
                        className="w-full bg-dark border border-gray-700 text-gray-300 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500 resize-none"
                      />
                      <button
                        onClick={() => resolveMutation.mutate({ conflictId: c.id, notes: resolveText })}
                        disabled={!resolveText.trim() || resolveMutation.isPending}
                        className="text-xs px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white rounded-lg disabled:opacity-50 flex items-center gap-1"
                      >
                        <CheckCircle size={11} />
                        Confirmar resolução
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!isLoading && !merge && !masterDoc && (
        <div className="card text-center py-20 space-y-3">
          <GitMerge size={40} className="text-gray-600 mx-auto" />
          <p className="text-gray-300 font-medium">Nenhuma consolidação executada</p>
          <p className="text-sm text-gray-500 max-w-sm mx-auto">
            Faça upload de artefatos nos pilares P1–P7 e clique em{" "}
            <strong className="text-violet-400">Executar Consolidação</strong> para gerar o documento mestre.
          </p>
        </div>
      )}

      {/* ══ PERGUNTAS DE ARGUIÇÃO (vindas do Gatekeeper) ═══════════════════════ */}
      {(() => {
        const argPlan = argPlanData?.data;
        const allQuestions = argPlan?.argumentation_questions || [];
        const selectedLanguage = argPlan?.stack_form?.language || "";

        if (allQuestions.length === 0) return null;

        // Agrupa por tema
        const themes: Record<string, ArgQuestion[]> = {};
        allQuestions.forEach(q => {
          const t = q.theme || "Geral";
          if (!themes[t]) themes[t] = [];
          themes[t].push(q);
        });

        const answered = allQuestions.filter(q => qaAnswers[q.question_id]).length;

        const handleSaveQA = () => {
          qaMutation.mutate({
            evaluation_id: argPlan?.evaluation_id,
            tech_stack: { language: selectedLanguage },
            qa_responses: allQuestions
              .filter(q => qaAnswers[q.question_id])
              .map(q => ({
                question_id: q.question_id,
                theme: q.theme,
                question: q.question,
                answer: qaAnswers[q.question_id] || "",
              })),
          });
        };

        return (
          <section className="space-y-4 pt-2">
            <div className="flex items-center justify-between">
              <h2 className="text-white font-semibold flex items-center gap-2">
                <Shield size={15} className="text-violet-400" />
                Perguntas de Contexto
                <HelpIcon text="Perguntas geradas pelo Gatekeeper após analisar os artefatos do projeto. Respondem lacunas de informação identificadas nos 7 pilares. Quanto mais completas as respostas, melhor o score do Gatekeeper e mais preciso o código gerado." />
              </h2>
              <span className="text-xs text-gray-400">{answered}/{allQuestions.length} respondidas</span>
            </div>

            <div className="bg-violet-900/10 border border-violet-800/30 rounded-lg px-4 py-3 text-xs text-gray-400 flex items-start gap-2">
              <MessageSquare size={12} className="text-violet-400 mt-0.5 shrink-0" />
              <span>
                Essas perguntas foram movidas do Arguidor para cá porque dependem dos artefatos já carregados.
                Responda após a consolidação para enriquecer o contexto do Gatekeeper.
              </span>
            </div>

            {Object.entries(themes).map(([theme, questions]) => {
              const isOpen = expandedThemes[theme] ?? true;
              const themeAnswered = questions.filter(q => qaAnswers[q.question_id]).length;
              return (
                <div key={theme} className="bg-dark-100 border border-gray-800 rounded-xl overflow-hidden">
                  <button
                    onClick={() => setExpandedThemes(prev => ({ ...prev, [theme]: !isOpen }))}
                    className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-gray-800/30 transition-colors"
                  >
                    <span className="text-sm font-medium text-gray-200">{theme}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-500">{themeAnswered}/{questions.length}</span>
                      {isOpen ? <ChevronUp size={14} className="text-gray-500" /> : <ChevronDown size={14} className="text-gray-500" />}
                    </div>
                  </button>

                  {isOpen && (
                    <div className="divide-y divide-gray-800">
                      {questions.map(q => {
                        const answer = qaAnswers[q.question_id] || "";
                        const helpText = getQuestionHelp(q.theme, q.question);
                        return (
                          <div key={q.question_id} className="px-5 py-4 space-y-2">
                            <div className="flex items-start gap-2">
                              {q.priority && (
                                <span className={clsx(
                                  "text-xs px-1.5 py-0.5 rounded shrink-0 mt-0.5",
                                  PRIORITY_COLORS[q.priority] || PRIORITY_COLORS.low
                                )}>
                                  {q.priority}
                                </span>
                              )}
                              <p className="text-sm text-gray-200 flex-1">{q.question}</p>
                              <HelpIcon text={helpText} />
                            </div>
                            <textarea
                              rows={2}
                              value={answer}
                              onChange={e => setQaAnswers(prev => ({ ...prev, [q.question_id]: e.target.value }))}
                              placeholder="Sua resposta em linguagem clara e objetiva…"
                              className="w-full bg-dark border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500 resize-none"
                            />
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}

            <div className="flex items-center gap-4">
              <button
                onClick={handleSaveQA}
                disabled={qaMutation.isPending || answered === 0}
                className="px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
              >
                {qaMutation.isPending ? "Salvando…" : "Salvar Respostas"}
              </button>
              {qaSaved && (
                <span className="flex items-center gap-1.5 text-green-400 text-sm">
                  <CheckCircle size={13} /> Respostas salvas com sucesso.
                </span>
              )}
            </div>
          </section>
        );
      })()}

    </div>
  );
}
