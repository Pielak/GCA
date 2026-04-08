import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "react-hot-toast";
import { HelpIcon } from "@/components/HelpIcon";
import {
  CheckSquare, AlertOctagon, Lock, Eye, EyeOff, ChevronDown, ChevronUp,
  Bot, ArrowRight, Shield, Play, FileCode, FileText, Loader2, X,
  CheckCircle2, XCircle, Clock, Download,
} from "lucide-react";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";
import { clsx } from "clsx";

// ── Types ────────────────────────────────────────────────────────────────────

interface TestCase {
  id: string;
  title: string;
  steps: string[];
  expected_result: string;
  status: "pending" | "executing" | "passed" | "failed" | "blocked";
  req_ref: string;
  test_type: string;
  priority: number;
  qa_notes: string | null;
  executed_at: string | null;
}

interface TestPlan {
  id: string;
  title: string;
  description: string;
  status: "draft" | "approved" | "show_stopper";
  plan_type: string;
  source: string;
  evaluation_id: string | null;
  is_qa_exclusive: boolean;
  requirements_refs: string[];
  created_by: string;
  created_at: string;
  due_at: string | null;
  test_cases: TestCase[];
}

interface TestFile {
  id: string;
  plan_id: string;
  framework: string;
  language: string;
  file_path: string;
  content: string;
  version: number;
  commit_sha: string | null;
  pushed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface ExecutionResult {
  case_id: string;
  title: string;
  status: "passed" | "failed" | "pending";
  reason: string;
}

interface TestExecution {
  id: string;
  plan_id: string;
  executed_by: string;
  passed_count: number;
  failed_count: number;
  pending_count: number;
  total_count: number;
  results: ExecutionResult[];
  report_markdown: string;
  report_path: string | null;
  commit_sha: string | null;
  emails_sent: string[];
  created_at: string;
}

// ── Constants ────────────────────────────────────────────────────────────────

const statusColors: Record<string, string> = {
  draft: "bg-gray-800 text-gray-300 border-gray-700",
  approved: "bg-emerald-900/40 text-emerald-300 border-emerald-700/50",
  show_stopper: "bg-red-900/40 text-red-300 border-red-700/50",
};
const statusLabels: Record<string, string> = {
  draft: "Rascunho",
  approved: "Aprovado",
  show_stopper: "⚠ Show Stopper",
};
const caseStatusDot: Record<string, string> = {
  pending: "bg-gray-500",
  executing: "bg-blue-500",
  passed: "bg-emerald-500",
  failed: "bg-red-500",
  blocked: "bg-amber-500",
};
const caseStatusColors: Record<string, string> = {
  pending: "text-gray-400",
  executing: "text-blue-400",
  passed: "text-emerald-400",
  failed: "text-red-400",
  blocked: "text-amber-400",
};
const resultIcon = {
  passed: <CheckCircle2 size={14} className="text-emerald-400" />,
  failed: <XCircle size={14} className="text-red-400" />,
  pending: <Clock size={14} className="text-gray-400" />,
};

const QA_ROLES = ["admin", "qa_engineer", "tech_lead"];

// ── Modals ───────────────────────────────────────────────────────────────────

function ModalOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      {children}
    </div>
  );
}

interface FileEditorModalProps {
  planId: string;
  projectId: string;
  onClose: () => void;
}

function FileEditorModal({ planId, projectId, onClose }: FileEditorModalProps) {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery<{ success: boolean; data: TestFile | null }>({
    queryKey: ["qa-file", planId],
    queryFn: () => api.get(`/projects/${projectId}/qa/${planId}/file`).then((r) => r.data),
    staleTime: 0,          // sempre buscar dado fresco ao abrir o modal
    refetchOnMount: true,
  });

  const [content, setContent] = useState<string | null>(null);
  const tf = data?.data;
  const displayContent = content !== null ? content : (tf?.content ?? "");

  const save = useMutation({
    mutationFn: (c: string) =>
      api.put(`/projects/${projectId}/qa/${planId}/file`, { content: c }),
    onSuccess: () => {
      toast.success("Arquivo salvo e enviado ao repositório.");
      qc.invalidateQueries({ queryKey: ["qa-file", planId] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao salvar arquivo.");
    },
  });

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-dark-100 border border-gray-700 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <FileCode size={16} className="text-violet-400" />
            <span className="text-white font-medium">
              {tf ? `${tf.file_path}  v${tf.version}` : "Arquivo de Teste"}
            </span>
            {tf?.framework && (
              <span className="text-xs bg-violet-900/30 text-violet-300 border border-violet-700/40 px-2 py-0.5 rounded">
                {tf.framework}
              </span>
            )}
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center gap-2 text-gray-400">
              <Loader2 size={20} className="animate-spin text-violet-400" />
              <span className="text-sm">Carregando arquivo…</span>
            </div>
          ) : isError ? (
            <div className="flex-1 flex items-center justify-center text-red-400 text-sm">
              Erro ao carregar arquivo. Verifique os logs do servidor.
            </div>
          ) : !tf ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 text-gray-500">
              <FileCode size={32} className="text-gray-700" />
              <p className="text-sm">Arquivo ainda não gerado para este plano.</p>
              <p className="text-xs text-gray-600">Feche este modal e clique em <strong className="text-gray-400">Gerar Arquivo de Teste</strong>.</p>
            </div>
          ) : (
            <textarea
              className="w-full font-mono text-sm bg-dark text-gray-200 border border-gray-700 rounded-lg p-3 resize-y focus:outline-none focus:border-violet-600"
              rows={Math.max(20, displayContent.split("\n").length)}
              value={displayContent}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
            />
          )}
        </div>

        {tf && (
          <div className="p-4 border-t border-gray-700 flex items-center justify-between">
            <div className="text-xs text-gray-500">
              {tf.pushed_at
                ? `Enviado ao repositório em ${new Date(tf.pushed_at).toLocaleString("pt-BR")}`
                : "Ainda não enviado ao repositório"}
              {tf.commit_sha && (
                <span className="ml-2 font-mono text-gray-600">{tf.commit_sha.slice(0, 8)}</span>
              )}
            </div>
            <button
              className="btn-primary text-sm flex items-center gap-2"
              disabled={save.isPending}
              onClick={() => save.mutate(displayContent)}
            >
              {save.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              Salvar e Enviar ao Repositório
            </button>
          </div>
        )}
      </div>
    </ModalOverlay>
  );
}

interface ExecuteModalProps {
  plan: TestPlan;
  projectId: string;
  onClose: () => void;
}

function ExecuteModal({ plan, projectId, onClose }: ExecuteModalProps) {
  const qc = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [execution, setExecution] = useState<TestExecution | null>(null);

  const toggle = (id: string) =>
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );

  const selectAll = () =>
    setSelectedIds(plan.test_cases.map((c) => c.id));

  const execute = useMutation({
    mutationFn: () =>
      api
        .post(`/projects/${projectId}/qa/${plan.id}/execute`, { case_ids: selectedIds })
        .then((r) => r.data),
    onSuccess: (data) => {
      setExecution(data.data);
      qc.invalidateQueries({ queryKey: ["qa", projectId] });
      qc.invalidateQueries({ queryKey: ["qa-executions", plan.id] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao executar testes. Verifique se o arquivo de teste foi gerado.");
    },
  });

  const allSelected = selectedIds.length === plan.test_cases.length;

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-dark-100 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <Play size={16} className="text-emerald-400" />
            <span className="text-white font-medium">Executar Testes</span>
            <span className="text-xs text-gray-500">{plan.title}</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {execution ? (
            <div className="space-y-4">
              {/* Resumo */}
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: "Aprovados", count: execution.passed_count, color: "emerald" },
                  { label: "Reprovados", count: execution.failed_count, color: "red" },
                  { label: "Pendentes", count: execution.pending_count, color: "gray" },
                ].map(({ label, count, color }) => (
                  <div
                    key={label}
                    className={`rounded-xl border p-3 text-center border-${color}-700/40 bg-${color}-900/20`}
                  >
                    <p className={`text-2xl font-bold text-${color}-400`}>{count}</p>
                    <p className="text-xs text-gray-400">{label}</p>
                  </div>
                ))}
              </div>

              {/* Resultados por caso */}
              <div className="space-y-2">
                {execution.results.map((r) => (
                  <div
                    key={r.case_id}
                    className="flex items-start gap-3 p-3 bg-dark rounded-lg border border-gray-700/50"
                  >
                    <span className="mt-0.5">{resultIcon[r.status]}</span>
                    <div className="min-w-0">
                      <p className="text-sm text-white font-medium">{r.title}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{r.reason}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Info relatório */}
              {execution.report_path && (
                <div className="flex items-center gap-2 text-xs text-gray-500 bg-dark rounded-lg px-3 py-2 border border-gray-700/50">
                  <Download size={12} />
                  Relatório DOCX enviado ao repositório: <span className="font-mono text-gray-400">{execution.report_path}</span>
                </div>
              )}
              {execution.emails_sent.length > 0 && (
                <p className="text-xs text-gray-500">
                  E-mails enviados para {execution.emails_sent.length} destinatários.
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-400">
                  Selecione os casos a executar (vazio = todos):
                </p>
                <button
                  className="text-xs text-violet-400 hover:text-violet-300"
                  onClick={allSelected ? () => setSelectedIds([]) : selectAll}
                >
                  {allSelected ? "Desmarcar todos" : "Selecionar todos"}
                </button>
              </div>
              {plan.test_cases.map((tc) => (
                <label
                  key={tc.id}
                  className="flex items-start gap-3 p-3 bg-dark rounded-lg border border-gray-700/50 cursor-pointer hover:border-violet-700/50 transition-colors"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-violet-500"
                    checked={selectedIds.includes(tc.id)}
                    onChange={() => toggle(tc.id)}
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-white">{tc.title}</p>
                    <p className="text-xs text-gray-500">{tc.req_ref} · {tc.test_type}</p>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-700 flex items-center justify-end gap-3">
          {execution ? (
            <button className="btn-primary text-sm" onClick={onClose}>
              Fechar
            </button>
          ) : (
            <>
              <button className="btn-ghost text-sm" onClick={onClose}>
                Cancelar
              </button>
              <button
                className="btn-primary text-sm flex items-center gap-2"
                disabled={execute.isPending}
                onClick={() => execute.mutate()}
              >
                {execute.isPending ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Executando…
                  </>
                ) : (
                  <>
                    <Play size={14} />
                    Executar {selectedIds.length > 0 ? `(${selectedIds.length})` : "(todos)"}
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

interface ReportsModalProps {
  plan: TestPlan;
  projectId: string;
  onClose: () => void;
}

function ReportsModal({ plan, projectId, onClose }: ReportsModalProps) {
  const [selected, setSelected] = useState<TestExecution | null>(null);

  const { data, isLoading } = useQuery<{ success: boolean; data: TestExecution[] }>({
    queryKey: ["qa-executions", plan.id],
    queryFn: () =>
      api.get(`/projects/${projectId}/qa/${plan.id}/executions`).then((r) => r.data),
  });

  const executions = data?.data ?? [];

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-dark-100 border border-gray-700 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-blue-400" />
            <span className="text-white font-medium">Relatórios de Execução</span>
            <span className="text-xs text-gray-500">{plan.title}</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={24} className="animate-spin text-violet-400" />
            </div>
          ) : executions.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              Nenhuma execução registrada para este plano.
            </div>
          ) : selected ? (
            <div className="space-y-4">
              <button
                className="text-sm text-violet-400 hover:text-violet-300 flex items-center gap-1"
                onClick={() => setSelected(null)}
              >
                ← Voltar à lista
              </button>

              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: "Aprovados", count: selected.passed_count, color: "emerald" },
                  { label: "Reprovados", count: selected.failed_count, color: "red" },
                  { label: "Pendentes", count: selected.pending_count, color: "gray" },
                ].map(({ label, count, color }) => (
                  <div
                    key={label}
                    className={`rounded-xl border p-3 text-center border-${color}-700/40 bg-${color}-900/20`}
                  >
                    <p className={`text-2xl font-bold text-${color}-400`}>{count}</p>
                    <p className="text-xs text-gray-400">{label}</p>
                  </div>
                ))}
              </div>

              <div className="space-y-2">
                {selected.results.map((r) => (
                  <div
                    key={r.case_id}
                    className="flex items-start gap-3 p-3 bg-dark rounded-lg border border-gray-700/50"
                  >
                    <span className="mt-0.5">{resultIcon[r.status]}</span>
                    <div>
                      <p className="text-sm text-white font-medium">{r.title}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{r.reason}</p>
                    </div>
                  </div>
                ))}
              </div>

              {selected.report_path && (
                <div className="flex items-center gap-2 text-xs text-gray-500 bg-dark rounded-lg px-3 py-2 border border-gray-700/50">
                  <Download size={12} />
                  <span className="font-mono text-gray-400">{selected.report_path}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {executions.map((ex) => (
                <button
                  key={ex.id}
                  className="w-full flex items-center justify-between p-3 bg-dark rounded-lg border border-gray-700/50 hover:border-violet-700/50 transition-colors text-left"
                  onClick={() => setSelected(ex)}
                >
                  <div>
                    <p className="text-sm text-white">
                      {new Date(ex.created_at).toLocaleString("pt-BR")}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {ex.total_count} casos · {ex.passed_count} ✅ · {ex.failed_count} ❌ · {ex.pending_count} ⏳
                    </p>
                  </div>
                  <ChevronDown size={14} className="text-gray-500 rotate-[-90deg]" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

// ── Plan Card ────────────────────────────────────────────────────────────────

interface PlanCardProps {
  plan: TestPlan;
  projectId: string;
  canSeeQAExclusive: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}

function PlanCard({ plan, projectId, canSeeQAExclusive, isExpanded, onToggle }: PlanCardProps) {
  const qc = useQueryClient();
  const [modal, setModal] = useState<"file" | "execute" | "reports" | null>(null);

  const passedCount = plan.test_cases.filter((c) => c.status === "passed").length;
  const totalCount = plan.test_cases.length;

  const generateFile = useMutation({
    mutationFn: () =>
      api.post(`/projects/${projectId}/qa/${plan.id}/generate-file`).then((r) => r.data),
    onSuccess: (data) => {
      // Pré-popular cache com o arquivo recém-gerado para o modal abrir instantaneamente
      qc.setQueryData(["qa-file", plan.id], { success: true, data: data.data });
      toast.success("Arquivo de teste gerado! Clique em 'Ver / Editar Arquivo' para visualizar.");
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.message ?? "Erro ao gerar arquivo de teste.";
      toast.error(msg, { duration: 6000 });
    },
  });

  return (
    <>
      <div
        className={clsx(
          "card border transition-colors",
          plan.status === "show_stopper" && "border-red-700/60 bg-red-950/10"
        )}
      >
        {/* Header */}
        <button className="w-full flex items-center justify-between gap-4" onClick={onToggle}>
          <div className="flex items-center gap-3 min-w-0">
            {plan.is_qa_exclusive && canSeeQAExclusive && (
              <Lock size={13} className="text-amber-400 shrink-0" aria-label="QA Exclusivo" />
            )}
            {plan.source === "gatekeeper" && (
              <span
                className="flex items-center gap-1 text-xs text-violet-400 bg-violet-900/30 border border-violet-700/40 px-1.5 py-0.5 rounded shrink-0"
                title="Gerado automaticamente pelo Gatekeeper"
              >
                <Bot size={11} />
                IA
              </span>
            )}
            <span className="text-white font-medium truncate">{plan.title}</span>
            <span
              className={clsx(
                "text-xs px-2 py-0.5 rounded-full border shrink-0",
                statusColors[plan.status]
              )}
            >
              {statusLabels[plan.status]}
            </span>
            {totalCount > 0 && (
              <span className="text-xs text-gray-500 shrink-0">
                {passedCount}/{totalCount} passando
              </span>
            )}
          </div>
          {isExpanded ? (
            <ChevronUp size={14} className="text-gray-500 shrink-0" />
          ) : (
            <ChevronDown size={14} className="text-gray-500 shrink-0" />
          )}
        </button>

        {/* Expanded content */}
        {isExpanded && (
          <div className="mt-4 pt-4 border-t border-gray-700 space-y-4">
            {/* Action buttons */}
            <div className="flex flex-wrap gap-2">
              <button
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-violet-700/60 text-violet-300 bg-violet-900/20 hover:bg-violet-900/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => generateFile.mutate()}
                disabled={generateFile.isPending}
                title="Gera arquivo executável de testes com IA e faz push para /tests/ no repositório"
              >
                {generateFile.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Bot size={12} />
                )}
                {generateFile.isPending ? "Gerando… (pode levar alguns segundos)" : "Gerar Arquivo de Teste"}
              </button>

              <button
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-600 text-gray-300 hover:border-violet-600 hover:text-violet-300 transition-colors"
                onClick={() => setModal("file")}
                title="Visualizar e editar o arquivo de testes gerado pela IA"
              >
                <FileCode size={12} />
                Ver / Editar Arquivo
              </button>

              <button
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-emerald-700/60 text-emerald-300 bg-emerald-900/20 hover:bg-emerald-900/40 transition-colors"
                onClick={() => setModal("execute")}
                title="Executar testes via análise da IA — requer arquivo de teste gerado"
              >
                <Play size={12} />
                Executar Testes
              </button>

              <button
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-blue-700/60 text-blue-300 bg-blue-900/20 hover:bg-blue-900/40 transition-colors"
                onClick={() => setModal("reports")}
                title="Ver histórico de execuções e relatórios DOCX"
              >
                <FileText size={12} />
                Relatórios
              </button>
            </div>

            {/* Test cases */}
            {totalCount > 0 && (
              <div className="space-y-2">
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
                  Casos de Teste
                </p>
                {plan.test_cases.map((tc) => (
                  <div key={tc.id} className="flex items-start gap-3 p-3 bg-dark rounded-lg">
                    <div
                      className={clsx(
                        "w-2 h-2 rounded-full mt-1.5 shrink-0",
                        caseStatusDot[tc.status]
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm text-white">{tc.title}</span>
                        <span className={clsx("text-xs", caseStatusColors[tc.status])}>
                          {tc.status}
                        </span>
                        {tc.req_ref && (
                          <span className="text-xs text-gray-600 font-mono">{tc.req_ref}</span>
                        )}
                      </div>
                      {tc.expected_result && (
                        <p className="text-xs text-gray-400 mt-1">{tc.expected_result}</p>
                      )}
                      {tc.qa_notes && (
                        <p className="text-xs text-gray-500 italic mt-0.5">{tc.qa_notes}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {modal === "file" && (
        <FileEditorModal
          planId={plan.id}
          projectId={projectId}
          onClose={() => setModal(null)}
        />
      )}
      {modal === "execute" && (
        <ExecuteModal
          plan={plan}
          projectId={projectId}
          onClose={() => setModal(null)}
        />
      )}
      {modal === "reports" && (
        <ReportsModal
          plan={plan}
          projectId={projectId}
          onClose={() => setModal(null)}
        />
      )}
    </>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

type Tab = "all" | "unit" | "integration";
type ModalState = { type: "file"; testType: "unit" | "integration" } | null;

export function QAReadinessPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { user } = useAuthStore();
  const canSeeQAExclusive = user ? QA_ROLES.includes(user.role) : false;
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showQAOnly, setShowQAOnly] = useState(false);
  const [tab, setTab] = useState<Tab>("all");
  const [modal, setModal] = useState<ModalState>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["qa", projectId],
    queryFn: () => api.get(`/projects/${projectId}/qa`).then((r) => r.data),
    enabled: !!projectId,
  });

  const { data: evalData } = useQuery({
    queryKey: ["gatekeeper", projectId],
    queryFn: () =>
      api
        .get(`/projects/${projectId}/gatekeeper/latest`)
        .then((r) => r.data?.data ?? null),
    enabled: !!projectId,
    staleTime: 30_000,
  });

  // Buscar arquivos consolidados
  // Se query retorna dados, assume modo consolidado ativado
  const { data: consolidatedData, isLoading: isLoadingConsolidated } = useQuery({
    queryKey: ["qa-consolidated", projectId],
    queryFn: () =>
      api
        .get(`/projects/${projectId}/qa/consolidated/files`)
        .then((r) => r.data?.data ?? { unit_tests: null, integration_tests: null })
        .catch(() => null), // Se endpoint não existe, retorna null (fallback)
    enabled: !!projectId,
    staleTime: 30_000,
    retry: 1, // Tenta apenas 1x se falhar
  });

  // Se consolidatedData foi retornado (mesmo que vazio), estamos em modo consolidado
  // Se consolidatedData é null, endpoint não existe ou deu erro - usar fallback
  const isConsolidatedMode = consolidatedData !== null;

  const allPlans: TestPlan[] = data?.data ?? [];
  const visiblePlans = canSeeQAExclusive
    ? showQAOnly
      ? allPlans.filter((p) => p.is_qa_exclusive)
      : allPlans
    : allPlans.filter((p) => !p.is_qa_exclusive);

  const filteredPlans =
    tab === "all"
      ? visiblePlans
      : visiblePlans.filter((p) => p.plan_type === tab);

  const showStoppers = visiblePlans.filter((p) => p.status === "show_stopper");

  const unitCount = visiblePlans.filter((p) => p.plan_type === "unit").length;
  const integrationCount = visiblePlans.filter((p) => p.plan_type === "integration").length;

  // Se estamos em modo consolidado, usar os 2 arquivos
  // Se não, mostrar lista individual de planos
  const isConsolidatedModeFiles = consolidatedData?.unit_tests?.id || consolidatedData?.integration_tests?.id;

  // Agrupar planos por tipo se consolidado
  const consolidatedUnitPlans = visiblePlans.filter((p) => p.plan_type === "unit");
  const consolidatedIntegrationPlans = visiblePlans.filter((p) => p.plan_type === "integration");

  const toggleExpanded = (id: string) =>
    setExpanded((prev) => (prev === id ? null : id));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <CheckSquare size={22} className="text-violet-400" />
          QA Readiness
          <HelpIcon text="Planos de teste gerados automaticamente. Para cada plano você pode: Gerar Arquivo (IA cria arquivo pytest/jest/etc.), Editar Arquivo (ajuste manual + push para /tests/), Executar Testes (IA simula execução caso a caso) e ver Relatórios DOCX enviados para /tests/doc/ e por e-mail." />
        </h1>
        <div className="flex items-center gap-3">
          {canSeeQAExclusive && (
            <button
              onClick={() => setShowQAOnly(!showQAOnly)}
              className={clsx(
                "flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg border transition-colors",
                showQAOnly
                  ? "bg-violet-600/20 border-violet-600 text-violet-300"
                  : "border-gray-700 text-gray-400 hover:text-gray-200"
              )}
            >
              {showQAOnly ? <Eye size={14} /> : <EyeOff size={14} />}
              QA Exclusivos
            </button>
          )}
        </div>
      </div>

      {/* Show stoppers banner */}
      {showStoppers.length > 0 && (
        <div className="card border-red-700/60 bg-red-950/20 flex items-start gap-3">
          <AlertOctagon size={20} className="text-red-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-red-300 font-semibold">
              {showStoppers.length} Show Stopper{showStoppers.length > 1 ? "s" : ""} identificado
              {showStoppers.length > 1 ? "s" : ""}
            </p>
            <p className="text-red-400 text-sm mt-0.5">
              Deploy bloqueado até resolução dos itens críticos de QA.
            </p>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card animate-pulse h-20" />
          ))}
        </div>
      )}

      {isError && (
        <div className="card border-red-700/50 text-red-400 text-center py-8">
          Erro ao carregar planos de QA.
        </div>
      )}

      {!isLoading && visiblePlans.length === 0 && (
        <div className="card border border-gray-700/60 px-5 py-8 space-y-4 text-center">
          <CheckSquare size={36} className="text-gray-600 mx-auto" />
          {evalData ? (
            <>
              <p className="text-amber-300 font-medium">
                Gatekeeper já foi executado, mas sem planos de teste.
              </p>
              <div className="flex items-start gap-3 bg-amber-900/20 border border-amber-700/40 rounded-xl px-4 py-3 text-left">
                <Shield size={16} className="text-amber-400 mt-0.5 shrink-0" />
                <p className="text-sm text-gray-300">
                  A funcionalidade de geração automática de planos de teste foi adicionada recentemente.
                  <strong className="text-amber-300"> Re-execute o Gatekeeper</strong> para gerar os planos
                  de testes unitários e integrados a partir da documentação atual do projeto.
                </p>
              </div>
            </>
          ) : (
            <p className="text-gray-400 font-medium">Nenhum plano de teste disponível.</p>
          )}
          <div className="flex items-center justify-center gap-2 text-sm text-gray-500 flex-wrap">
            {["1. Artefatos", "2. Consolidação", "3. Gatekeeper"].map((step) => (
              <React.Fragment key={step}>
                <span className="px-2.5 py-1 rounded-lg bg-dark-200 border border-gray-700 text-xs font-medium text-gray-300">
                  {step}
                </span>
                <ArrowRight size={13} className="text-gray-600 shrink-0" />
              </React.Fragment>
            ))}
            <span className="px-2.5 py-1 rounded-lg bg-violet-900/40 border border-violet-700/60 text-xs font-medium text-violet-300">
              4. QA Readiness ← aqui
            </span>
          </div>
        </div>
      )}

      {/* Tabs — Ocultos se consolidado */}
      {!isLoading && visiblePlans.length > 0 && !isConsolidatedMode && (
        <div className="flex gap-2 border-b border-gray-700 pb-0">
          {(
            [
              { id: "all", label: "Todos", count: visiblePlans.length },
              { id: "unit", label: "Unitários", count: unitCount },
              { id: "integration", label: "Integrados", count: integrationCount },
            ] as { id: Tab; label: string; count: number }[]
          ).map(({ id, label, count }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={clsx(
                "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
                tab === id
                  ? "border-violet-500 text-violet-300"
                  : "border-transparent text-gray-500 hover:text-gray-300"
              )}
            >
              {label}
              {count > 0 && (
                <span
                  className={clsx(
                    "ml-2 text-xs px-1.5 py-0.5 rounded-full",
                    tab === id ? "bg-violet-800/60 text-violet-300" : "bg-gray-800 text-gray-400"
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Consolidated Files (Testes Unitários + Integrados) — Modo Consolidado */}
      {isConsolidatedMode && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <FileCode size={16} className="text-emerald-400" />
            📁 Arquivos Consolidados (2 arquivos)
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Testes Unitários */}
            <div className="card border border-blue-700/40 bg-blue-950/10">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <FileCode size={16} className="text-blue-400" />
                  <div>
                    <p className="text-white font-medium">Testes Unitários</p>
                    <p className="text-xs text-gray-500">{consolidatedUnitPlans.length} planos consolidados</p>
                  </div>
                </div>
              </div>
              {consolidatedData?.unit_tests ? (
                <button
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-600/20 border border-blue-700/60 text-blue-300 hover:bg-blue-600/30 transition-colors text-sm"
                  onClick={() => setModal({ type: "file", testType: "unit" })}
                >
                  <FileText size={14} />
                  Ver / Editar Arquivo
                </button>
              ) : (
                <button
                  disabled
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-600/10 border border-blue-700/30 text-blue-400/50 text-sm opacity-50"
                >
                  <FileText size={14} />
                  Gerar via Gatekeeper
                </button>
              )}
            </div>

            {/* Testes Integrados */}
            <div className="card border border-green-700/40 bg-green-950/10">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <FileCode size={16} className="text-green-400" />
                  <div>
                    <p className="text-white font-medium">Testes Integrados</p>
                    <p className="text-xs text-gray-500">{consolidatedIntegrationPlans.length} planos consolidados</p>
                  </div>
                </div>
              </div>
              {consolidatedData?.integration_tests ? (
                <button
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-green-600/20 border border-green-700/60 text-green-300 hover:bg-green-600/30 transition-colors text-sm"
                  onClick={() => setModal({ type: "file", testType: "integration" })}
                >
                  <FileText size={14} />
                  Ver / Editar Arquivo
                </button>
              ) : (
                <button
                  disabled
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-green-600/10 border border-green-700/30 text-green-400/50 text-sm opacity-50"
                >
                  <FileText size={14} />
                  Gerar via Gatekeeper
                </button>
              )}
            </div>
          </div>

          {/* Info card */}
          <div className="card border border-emerald-700/40 bg-emerald-950/10 text-sm text-emerald-300">
            <p className="font-medium flex items-center gap-2">
              <CheckSquare size={14} />
              ✅ Consolidação Automática Ativada
            </p>
            <p className="text-xs text-emerald-300/80 mt-1">
              {consolidatedUnitPlans.length + consolidatedIntegrationPlans.length} testes consolidados em apenas 2 arquivos: Unitários e Integrados. Edite, execute e gere relatórios direto neles. {!consolidatedData?.unit_tests && !consolidatedData?.integration_tests && "Execute Gatekeeper para gerar os arquivos."}
            </p>
          </div>
        </div>
      )}

      {/* Individual Plans List — Escondido quando consolidado */}
      {!isConsolidatedMode && visiblePlans.length > 0 && (
        <div className="space-y-3">
          {filteredPlans.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              projectId={projectId!}
              canSeeQAExclusive={canSeeQAExclusive}
              isExpanded={expanded === plan.id}
              onToggle={() => toggleExpanded(plan.id)}
            />
          ))}
        </div>
      )}

      {/* Consolidated File Editor Modal */}
      {modal?.type === "file" && (
        <ModalOverlay onClose={() => setModal(null)}>
          <div className="bg-dark-100 border border-gray-700 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <FileCode size={16} className={modal.testType === "unit" ? "text-blue-400" : "text-green-400"} />
                <span className="text-white font-medium">
                  Arquivo Consolidado — {modal.testType === "unit" ? "Testes Unitários" : "Testes Integrados"}
                </span>
              </div>
              <button onClick={() => setModal(null)} className="text-gray-400 hover:text-white">
                <X size={16} />
              </button>
            </div>

            <ConsolidatedFileEditor
              projectId={projectId!}
              testType={modal.testType}
              onClose={() => setModal(null)}
            />
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

// ── Consolidated Execute Modal ────────────────────────────────────────

interface ConsolidatedExecuteModalProps {
  projectId: string;
  testType: "unit" | "integration";
  onClose: () => void;
}

function ConsolidatedExecuteModal({ projectId, testType, onClose }: ConsolidatedExecuteModalProps) {
  const qc = useQueryClient();
  const [execution, setExecution] = useState<TestExecution | null>(null);

  const execute = useMutation({
    mutationFn: () =>
      api
        .post(`/projects/${projectId}/qa/consolidated/file/${testType}/execute`)
        .then((r) => r.data),
    onSuccess: (data) => {
      setExecution(data.data);
      qc.invalidateQueries({ queryKey: ["qa-consolidated", projectId] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao executar testes consolidados.");
    },
  });

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-dark-100 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <Play size={16} className="text-emerald-400" />
            <span className="text-white font-medium">
              Executar Testes Consolidados — {testType === "unit" ? "Unitários" : "Integrados"}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {execution ? (
            <div className="space-y-4">
              {/* Resumo */}
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: "Aprovados", count: execution.passed_count, color: "emerald" },
                  { label: "Reprovados", count: execution.failed_count, color: "red" },
                  { label: "Pendentes", count: execution.pending_count, color: "gray" },
                ].map(({ label, count, color }) => (
                  <div
                    key={label}
                    className={`rounded-xl border p-3 text-center border-${color}-700/40 bg-${color}-900/20`}
                  >
                    <p className={`text-2xl font-bold text-${color}-400`}>{count}</p>
                    <p className="text-xs text-gray-400">{label}</p>
                  </div>
                ))}
              </div>

              {/* Resultados por caso */}
              <div className="space-y-2">
                <p className="text-xs text-gray-500 font-medium">Resultados:</p>
                {execution.results.map((r) => (
                  <div
                    key={r.case_id}
                    className="flex items-start gap-3 p-3 bg-dark rounded-lg border border-gray-700/50"
                  >
                    <span className="mt-0.5">{resultIcon[r.status]}</span>
                    <div className="min-w-0">
                      <p className="text-sm text-white font-medium">{r.title}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{r.reason}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Info relatório */}
              {execution.report_path && (
                <div className="flex items-center gap-2 text-xs text-gray-500 bg-dark rounded-lg px-3 py-2 border border-gray-700/50">
                  <Download size={12} />
                  Relatório gerado: <span className="font-mono text-gray-400">{execution.report_path}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4 text-center py-8">
              <Play size={48} className="text-emerald-400/30 mx-auto" />
              <div>
                <p className="text-white font-medium">Pronto para executar testes?</p>
                <p className="text-gray-400 text-sm mt-1">
                  Todos os testes consolidados ({testType === "unit" ? "unitários" : "integrados"}) serão executados via IA.
                </p>
                <p className="text-gray-500 text-xs mt-2">
                  O resultado será um relatório DOCX enviado para o repositório e e-mail.
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-700 flex items-center justify-end gap-3">
          {execution ? (
            <button className="btn-primary text-sm" onClick={onClose}>
              Fechar
            </button>
          ) : (
            <>
              <button className="btn-ghost text-sm" onClick={onClose}>
                Cancelar
              </button>
              <button
                className="btn-success text-sm flex items-center gap-2"
                disabled={execute.isPending}
                onClick={() => execute.mutate()}
              >
                {execute.isPending ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Executando…
                  </>
                ) : (
                  <>
                    <Play size={14} />
                    Executar Testes
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

// ── Consolidated File Editor ────────────────────────────────────────

interface ConsolidatedFileEditorProps {
  projectId: string;
  testType: "unit" | "integration";
  onClose: () => void;
}

function ConsolidatedFileEditor({ projectId, testType, onClose }: ConsolidatedFileEditorProps) {
  const qc = useQueryClient();
  const { user } = useAuthStore();
  const [hasSaved, setHasSaved] = useState(false);
  const [showExecuteModal, setShowExecuteModal] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["qa-consolidated-file", projectId, testType],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}/qa/consolidated/files`);
      const consolidatedData = res.data?.data;
      const fileKey = testType === "unit" ? "unit_tests" : "integration_tests";
      return consolidatedData?.[fileKey] || null;
    },
    staleTime: 0,
    refetchOnMount: true,
  });

  const [content, setContent] = useState<string>("");
  const tf = data;
  const displayContent = content !== "" ? content : (tf?.content ?? "");

  // Verificar permissões para editar e aprovar
  const canEdit = user ? ["admin", "qa_engineer", "compliance_officer", "security_officer", "legal_officer", "tech_lead"].includes(user.role) : false;
  const canApprove = user ? ["admin", "qa_engineer", "tech_lead"].includes(user.role) : false;
  const isDraft = tf?.status === "draft" || !tf?.status;

  const save = useMutation({
    mutationFn: (c: string) =>
      api
        .put(`/projects/${projectId}/qa/consolidated/file/${testType}`, { content: c })
        .then((r) => r.data),
    onSuccess: () => {
      setContent("");
      setHasSaved(true);  // ← Marca como salvo
      toast.success("Arquivo salvo com sucesso! ✅ Agora você pode executar os testes.");
      qc.invalidateQueries({ queryKey: ["qa-consolidated", projectId] });
      qc.invalidateQueries({ queryKey: ["qa-consolidated-file", projectId, testType] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao salvar arquivo.");
    },
  });

  const approve = useMutation({
    mutationFn: () =>
      api
        .patch(`/projects/${projectId}/qa/consolidated/file/${testType}/approve`)
        .then((r) => r.data),
    onSuccess: () => {
      toast.success("Arquivo aprovado! ✅ Pronto para execução de testes.");
      qc.invalidateQueries({ queryKey: ["qa-consolidated", projectId] });
      qc.invalidateQueries({ queryKey: ["qa-consolidated-file", projectId, testType] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao aprovar arquivo.");
    },
  });

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-violet-400" />
      </div>
    );
  }

  return (
    <>
      {/* Status Badge */}
      {tf && (
        <div className="flex-shrink-0 flex items-center gap-2 px-4 py-3 border-b border-gray-700 bg-gray-900/50">
          <div
            className={clsx(
              "text-xs font-bold px-2.5 py-1 rounded-full",
              tf.status === "draft" || !tf.status
                ? "bg-amber-900/60 text-amber-300"
                : "bg-emerald-900/60 text-emerald-300"
            )}
          >
            {tf.status === "draft" || !tf.status ? "📝 RASCUNHO" : "✅ PRONTO PARA TESTES"}
          </div>
          <div className="text-xs text-gray-500 ml-auto">
            v{tf.version || 1} • {new Date(tf.created_at).toLocaleDateString("pt-BR")}
          </div>
        </div>
      )}

      {/* Editor */}
      <div className="flex-1 overflow-y-auto">
        {!displayContent ? (
          <div className="flex items-center justify-center h-full text-gray-500 p-8">
            <p>Nenhum arquivo consolidado gerado ainda. Execute o Gatekeeper para gerar os testes.</p>
          </div>
        ) : (
          <textarea
            className={clsx(
              "w-full h-full p-4 bg-dark-100 text-gray-200 font-mono text-sm border-0 resize-none focus:outline-none focus:ring-0",
              !canEdit && "opacity-75 cursor-not-allowed"
            )}
            value={displayContent}
            onChange={(e) => setContent(e.target.value)}
            disabled={!canEdit}
            spellCheck="false"
          />
        )}
      </div>

      {displayContent && (
        <div className="p-4 border-t border-gray-700 space-y-3">
          {/* Info */}
          <div className="text-xs text-gray-500">
            {tf?.pushed_at
              ? `Enviado ao repositório em ${new Date(tf.pushed_at).toLocaleString("pt-BR")}`
              : "Ainda não enviado ao repositório"}
            {tf?.commit_sha && (
              <span className="ml-2 font-mono text-gray-600">{tf.commit_sha.slice(0, 8)}</span>
            )}
          </div>

          {/* Permissions Notice */}
          {!canEdit && (
            <div className="text-xs bg-red-900/20 border border-red-700/40 text-red-400 px-2 py-1.5 rounded">
              Você não tem permissão para editar. Apenas QA Engineer, Compliance, Segurança e Jurídico podem editar.
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 flex-col">
            {/* Linha 1: Salvar + Aprovar */}
            <div className="flex gap-2">
              {isDraft && canEdit && (
                <button
                  className="btn-primary text-sm flex items-center gap-2 flex-1"
                  disabled={save.isPending}
                  onClick={() => save.mutate(displayContent)}
                >
                  {save.isPending ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
                  Salvar como Rascunho
                </button>
              )}

              {isDraft && canApprove && (
                <button
                  className="btn-success text-sm flex items-center gap-2 flex-1"
                  disabled={approve.isPending}
                  onClick={() => approve.mutate()}
                >
                  {approve.isPending ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                  Aprovar ✅
                </button>
              )}

              {!isDraft && (
                <div className="text-sm px-3 py-2 rounded-lg bg-emerald-900/20 border border-emerald-700/40 text-emerald-300 flex-1 flex items-center gap-2">
                  <CheckCircle2 size={14} />
                  Pronto para execução de testes
                </div>
              )}
            </div>

            {/* Linha 2: Realizar Teste (habilitado após salvar OU após aprovar) */}
            {(hasSaved || !isDraft) && (
              <button
                className="btn-success text-sm flex items-center gap-2 w-full"
                onClick={() => setShowExecuteModal(true)}
                title="Executa os testes consolidados via IA"
              >
                <Play size={14} />
                🚀 Realizar Teste
              </button>
            )}

            {/* Mensagem quando não foi salvo ainda */}
            {!hasSaved && isDraft && (
              <div className="text-xs px-3 py-2 rounded-lg bg-amber-900/20 border border-amber-700/40 text-amber-300 text-center">
                💾 Salve o arquivo primeiro para executar os testes
              </div>
            )}
          </div>
        </div>
      )}

      {/* Consolidated Execute Modal */}
      {showExecuteModal && (
        <ConsolidatedExecuteModal
          projectId={projectId}
          testType={testType}
          onClose={() => setShowExecuteModal(false)}
        />
      )}
    </>
  );
}
