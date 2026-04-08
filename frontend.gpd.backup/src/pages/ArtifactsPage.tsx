import { useState, useCallback, useEffect } from "react";
import { HelpIcon } from "@/components/HelpIcon";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import toast from "react-hot-toast";
import clsx from "clsx";
import {
  Upload,
  FileText,
  File,
  FileImage,
  FileSpreadsheet,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Loader2,
  Download,
  Trash2,
  ChevronDown,
  ChevronUp,
  Sparkles,
  ShieldAlert,
  X,
} from "lucide-react";
import { api } from "@/services/api";
import { WireframeArtifactCard } from "@/components/artifacts/WireframeArtifactCard";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Artifact {
  id: string;
  project_id: string;
  category: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256_hash: string;
  status: "pending" | "classifying" | "verified" | "quarantine" | "rejected";
  relevance_score: number | null;
  relevance_notes: string | null;
  uploaded_by: string;
  approved_by: string | null;
  created_at: string;
  parent_artifact_id: string | null;
  // Design system fields (optional, for wireframe artifacts)
  accessibility_score?: number;
  responsiveness_score?: number;
  completeness_score?: number;
  components_count?: number;
  tokens_count?: number;
}

interface ArtifactsResponse {
  success: boolean;
  data: Artifact[];
  total: number;
}

// ─── Constants ───────────────────────────────────────────────────────────────

// 7 pilares documentais do manifesto GPD
const CATEGORIES: { value: string; label: string; description?: string }[] = [
  {
    value: "business_requirements",
    label: "P1 — Requisitos Negociais",
    description: "Objetivos, problema de negócio, atores, escopo, valor esperado, KPIs",
  },
  {
    value: "business_rules",
    label: "P2 — Regras de Negócio",
    description: "Validações, restrições, exceções, políticas de aprovação, estados",
  },
  {
    value: "functional_requirements",
    label: "P3 — Requisitos Funcionais",
    description: "Jornadas, telas, APIs, eventos, fluxos, critérios de aceite",
  },
  {
    value: "non_functional_requirements",
    label: "P4 — Requisitos Não Funcionais",
    description: "Performance, disponibilidade, segurança, SLA, escalabilidade",
  },
  {
    value: "solution_architecture",
    label: "P5 — Arquitetura da Solução",
    description: "Stack, padrões, módulos, boundaries, integrações, ADRs",
  },
  {
    value: "data_integration_legacy",
    label: "P6 — Dados, Integrações e Legado",
    description: "Modelo de dados, ETL, contratos de API, mensageria, legado",
  },
  {
    value: "security_compliance_qa",
    label: "P7 — Segurança, Compliance e QA",
    description: "LGPD, autenticação, auditoria, plano de testes, critérios de aceite",
  },
];

const STATUS_TABS = [
  { value: "", label: "Todos" },
  { value: "verified", label: "Verificados" },
  { value: "quarantine", label: "Em Quarentena" },
  { value: "pending", label: "Pendentes" },
  { value: "rejected", label: "Rejeitados" },
];

const ACCEPTED_MIME_TYPES: Record<string, string[]> = {
  "application/pdf": [".pdf"],
  "application/msword": [".doc"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/vnd.ms-excel": [".xls"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-powerpoint": [".ppt"],
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
  "text/plain": [".txt"],
  "text/markdown": [".md"],
  "text/csv": [".csv"],
  "application/json": [".json"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/gif": [".gif"],
  "image/webp": [".webp"],
  "image/svg+xml": [".svg"],
  "image/bmp": [".bmp"],
  "image/tiff": [".tif", ".tiff"],
  "image/avif": [".avif"],
  "image/heic": [".heic"],
  "image/heif": [".heif"],
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getCategoryLabel(value: string): string {
  return CATEGORIES.find((c) => c.value === value)?.label ?? value;
}

function FileIcon({ mimeType, filename }: { mimeType: string; filename: string }) {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (mimeType === "application/pdf" || ext === "pdf")
    return <File size={18} className="text-red-400 shrink-0" />;
  if (["doc", "docx"].includes(ext))
    return <FileText size={18} className="text-blue-400 shrink-0" />;
  if (["xls", "xlsx", "csv"].includes(ext))
    return <FileSpreadsheet size={18} className="text-green-400 shrink-0" />;
  if (["png", "jpg", "jpeg"].includes(ext))
    return <FileImage size={18} className="text-amber-400 shrink-0" />;
  return <FileText size={18} className="text-gray-400 shrink-0" />;
}

// ─── Upload file queue entry ──────────────────────────────────────────────────

interface QueueEntry {
  id: string;
  file: File;
  status: "queued" | "uploading" | "done" | "error";
  progress: number;
  error?: string;
  result?: Artifact;
}

// ─── Quarantine review form ───────────────────────────────────────────────────

const quarantineSchema = z.object({
  notes: z.string().min(1, "Informe o motivo da sua decisão para manter o histórico de revisão"),
});
type QuarantineFormData = z.infer<typeof quarantineSchema>;

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Artifact["status"] }) {
  if (status === "verified")
    return (
      <span className="flex items-center gap-1 text-xs text-emerald-400">
        <CheckCircle size={13} />
        Verificado
      </span>
    );
  if (status === "quarantine")
    return (
      <span className="flex items-center gap-1 text-xs text-amber-400">
        <AlertTriangle size={13} />
        Em Quarentena
      </span>
    );
  if (status === "rejected")
    return (
      <span className="flex items-center gap-1 text-xs text-red-400">
        <XCircle size={13} />
        Rejeitado
      </span>
    );
  // pending | classifying
  return (
    <span className="flex items-center gap-1 text-xs text-gray-400">
      <Loader2 size={13} className="animate-spin" />
      {status === "classifying" ? "Classificando…" : "Pendente"}
    </span>
  );
}

function RelevanceBar({ score }: { score: number | null }) {
  if (score === null) return <span className="text-xs text-gray-500">Sem score</span>;
  const pct = Math.round(score * 100);
  const color =
    pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-dark-200 rounded-full h-1.5 overflow-hidden">
        <div className={clsx("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-8 text-right">{pct}%</span>
    </div>
  );
}

// ─── Artifact Card ────────────────────────────────────────────────────────────

interface ArtifactCardProps {
  artifact: Artifact;
  projectId: string;
  onQuarantineReview: (artifact: Artifact) => void;
  onDelete: (artifact: Artifact) => void;
}

function ArtifactCard({ artifact, projectId, onQuarantineReview, onDelete }: ArtifactCardProps) {
  const [notesExpanded, setNotesExpanded] = useState(false);
  const queryClient = useQueryClient();

  const classifyMutation = useMutation({
    mutationFn: () =>
      api.post(`/projects/${projectId}/artifacts/${artifact.id}/classify`),
    onSuccess: () => {
      toast.success("Classificação iniciada pela IA.");
      queryClient.invalidateQueries({ queryKey: ["artifacts", projectId] });
    },
    onError: () => toast.error("Não foi possível iniciar a classificação por IA. Verifique se o serviço está online e tente novamente."),
  });

  const downloadMutation = useMutation({
    mutationFn: async () => {
      const response = await api.get(
        `/projects/${projectId}/artifacts/${artifact.id}/download`,
        { responseType: "blob" }
      );
      return response;
    },
    onSuccess: (response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", artifact.original_filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
    onError: () => toast.error("Não foi possível baixar o arquivo. Ele pode ter sido removido ou você não tem permissão de acesso."),
  });

  const hasLgpdWarning =
    artifact.relevance_notes?.includes("[AVISO LGPD]") ?? false;

  const notes = artifact.relevance_notes ?? "";
  const truncated = notes.length > 160;
  const displayNotes = notesExpanded || !truncated ? notes : notes.slice(0, 160) + "…";

  return (
    <div className="card flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <FileIcon mimeType={artifact.mime_type} filename={artifact.original_filename} />
          <span
            className="text-sm font-medium text-gray-100 truncate"
            title={artifact.original_filename}
          >
            {artifact.original_filename}
          </span>
        </div>
        <StatusBadge status={artifact.status} />
      </div>

      {/* Category + size + date */}
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
        <span className="bg-dark-200 border border-gray-700 rounded-full px-2 py-0.5 text-violet-300">
          {getCategoryLabel(artifact.category)}
        </span>
        {artifact.parent_artifact_id && (
          <span className="bg-violet-900/30 border border-violet-700/40 rounded-full px-2 py-0.5 text-violet-400 flex items-center gap-1">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor"><path d="M5 1L9 5H6v4H4V5H1L5 1z"/></svg>
            derivado
          </span>
        )}
        <span>{formatBytes(artifact.size_bytes)}</span>
        <span>·</span>
        <span>{formatDate(artifact.created_at)}</span>
      </div>

      {/* Relevance score */}
      <div>
        <div className="text-xs text-gray-500 mb-1">Score de Relevância</div>
        <RelevanceBar score={artifact.relevance_score} />
      </div>

      {/* LGPD warning */}
      {hasLgpdWarning && (
        <div className="flex items-center gap-2 bg-red-900/30 border border-red-700/50 rounded-lg px-3 py-2">
          <ShieldAlert size={14} className="text-red-400 shrink-0" />
          <span className="text-xs text-red-300 font-medium">
            Aviso LGPD detectado neste artefato
          </span>
        </div>
      )}

      {/* Relevance notes */}
      {notes && (
        <div className="text-xs text-gray-400 leading-relaxed">
          <p>{displayNotes}</p>
          {truncated && (
            <button
              className="text-violet-400 hover:text-violet-300 flex items-center gap-0.5 mt-1"
              onClick={() => setNotesExpanded((v) => !v)}
            >
              {notesExpanded ? (
                <>
                  <ChevronUp size={12} /> Recolher
                </>
              ) : (
                <>
                  <ChevronDown size={12} /> Ver mais
                </>
              )}
            </button>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-gray-700/50">
        {/* Classify (pending) */}
        {artifact.status === "pending" && (
          <button
            className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1"
            onClick={() => classifyMutation.mutate()}
            disabled={classifyMutation.isPending}
          >
            {classifyMutation.isPending ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Sparkles size={13} />
            )}
            Classificar
          </button>
        )}

        {/* Reclassify (verified — force re-run to detect all pillars) */}
        {artifact.status === "verified" && (
          <button
            className="text-xs px-3 py-1.5 rounded-lg font-semibold bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-700/50 transition-colors flex items-center gap-1"
            onClick={() => classifyMutation.mutate()}
            disabled={classifyMutation.isPending}
            title="Reclassificar para detectar todos os pilares cobertos"
          >
            {classifyMutation.isPending ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Sparkles size={13} />
            )}
            Reclassificar
          </button>
        )}

        {/* Quarantine actions */}
        {artifact.status === "quarantine" && (
          <button
            className="text-xs px-3 py-1.5 rounded-lg font-semibold bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-700/50 transition-colors"
            onClick={() => onQuarantineReview(artifact)}
          >
            Revisar
          </button>
        )}

        {/* Download */}
        <button
          className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1"
          onClick={() => downloadMutation.mutate()}
          disabled={downloadMutation.isPending}
        >
          {downloadMutation.isPending ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Download size={13} />
          )}
          Download
        </button>

        {/* Delete */}
        <button
          className="text-xs px-3 py-1.5 rounded-lg font-medium text-red-400 hover:text-red-300 hover:bg-red-900/20 transition-colors flex items-center gap-1 ml-auto"
          onClick={() => onDelete(artifact)}
        >
          <Trash2 size={13} />
          Excluir
        </button>
      </div>
    </div>
  );
}

// ─── Upload Modal ─────────────────────────────────────────────────────────────

interface UploadModalProps {
  projectId: string;
  onClose: () => void;
  onUploaded: () => void;
}

function UploadModal({ projectId, onClose, onUploaded }: UploadModalProps) {
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [running, setRunning] = useState(false);
  const allDone = queue.length > 0 && queue.every((e) => e.status === "done" || e.status === "error");

  const updateEntry = (id: string, patch: Partial<QueueEntry>) =>
    setQueue((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));

  const onDrop = useCallback((accepted: File[]) => {
    const newEntries: QueueEntry[] = accepted.map((f) => ({
      id: `${f.name}-${f.size}-${Date.now()}-${Math.random()}`,
      file: f,
      status: "queued",
      progress: 0,
    }));
    setQueue((prev) => [...prev, ...newEntries]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_MIME_TYPES,
    multiple: true,
  });

  const removeEntry = (id: string) =>
    setQueue((prev) => prev.filter((e) => e.id !== id));

  const startUpload = async () => {
    const pending = queue.filter((e) => e.status === "queued");
    if (!pending.length) return;
    setRunning(true);

    for (const entry of pending) {
      updateEntry(entry.id, { status: "uploading", progress: 0 });
      const formData = new FormData();
      formData.append("file", entry.file);
      formData.append("category", "auto");
      formData.append("auto_classify", "true");
      try {
        const res = await api.post(`/projects/${projectId}/artifacts`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (evt) => {
            if (evt.total)
              updateEntry(entry.id, { progress: Math.round((evt.loaded / evt.total) * 100) });
          },
        });
        updateEntry(entry.id, { status: "done", progress: 100, result: res.data.data });
      } catch (err: any) {
        const msg = err?.response?.data?.message ?? "Falha no envio";
        updateEntry(entry.id, { status: "error", error: msg });
      }
    }

    setRunning(false);
    onUploaded();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="bg-dark-100 border border-gray-700 rounded-2xl w-full max-w-xl shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 shrink-0">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Upload size={18} className="text-violet-400" />
            Upload de Artefatos
          </h2>
          <button className="text-gray-400 hover:text-gray-200 transition-colors" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4 overflow-y-auto flex-1">
          {/* Dropzone */}
          <div
            {...getRootProps()}
            className={clsx(
              "border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors",
              isDragActive ? "border-violet-500 bg-violet-900/20" : "border-gray-600 hover:border-gray-500"
            )}
          >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center gap-2 text-gray-500">
              <Upload size={28} />
              <p className="text-sm">
                {isDragActive ? "Solte os arquivos aqui…" : "Arraste arquivos ou clique para selecionar"}
              </p>
              <p className="text-xs text-gray-600">
                PDF, Word, Excel, PowerPoint, TXT, CSV, JSON · PNG, JPG, SVG, WEBP, GIF, BMP, TIFF, AVIF, HEIC
              </p>
              <p className="text-xs text-violet-400 flex items-center gap-1 mt-1">
                <Sparkles size={12} />
                A IA irá identificar automaticamente a categoria de cada arquivo
              </p>
            </div>
          </div>

          {/* File queue */}
          {queue.length > 0 && (
            <div className="space-y-2">
              {queue.map((entry) => (
                <div key={entry.id} className="bg-dark rounded-lg px-3 py-2 space-y-2">
                  <div className="flex items-center gap-3">
                    <FileIcon mimeType={entry.file.type} filename={entry.file.name} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-gray-200 truncate">{entry.file.name}</p>
                      <p className="text-xs text-gray-600">{formatBytes(entry.file.size)}</p>
                      {entry.status === "uploading" && (
                        <div className="mt-1 w-full bg-dark-200 rounded-full h-1">
                          <div
                            className="h-1 rounded-full bg-violet-500 transition-all duration-200"
                            style={{ width: `${entry.progress}%` }}
                          />
                        </div>
                      )}
                      {entry.status === "error" && (
                        <p className="text-xs text-red-400 mt-0.5">{entry.error}</p>
                      )}
                    </div>
                    <div className="shrink-0">
                      {entry.status === "queued" && (
                        <span className="text-xs text-gray-500">Na fila</span>
                      )}
                      {entry.status === "uploading" && (
                        <Loader2 size={14} className="animate-spin text-violet-400" />
                      )}
                      {entry.status === "done" && (
                        <CheckCircle size={14} className="text-emerald-400" />
                      )}
                      {entry.status === "error" && (
                        <XCircle size={14} className="text-red-400" />
                      )}
                    </div>
                    {entry.status === "queued" && !running && (
                      <button onClick={() => removeEntry(entry.id)} className="text-gray-600 hover:text-gray-400 ml-1">
                        <X size={13} />
                      </button>
                    )}
                  </div>

                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-700 flex gap-3 shrink-0">
          <button
            className="btn-secondary flex-1"
            onClick={allDone ? onClose : onClose}
            disabled={running}
          >
            {allDone ? "Fechar" : "Cancelar"}
          </button>
          {!allDone && (
            <button
              className="btn-primary flex-1 flex items-center justify-center gap-2"
              onClick={startUpload}
              disabled={running || queue.filter((e) => e.status === "queued").length === 0}
            >
              {running ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Enviando…
                </>
              ) : (
                <>
                  <Upload size={15} />
                  Enviar {queue.filter((e) => e.status === "queued").length} arquivo(s)
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Quarantine Review Modal ──────────────────────────────────────────────────

interface QuarantineModalProps {
  artifact: Artifact;
  projectId: string;
  onClose: () => void;
}

function QuarantineModal({ artifact, projectId, onClose }: QuarantineModalProps) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, formState: { errors } } = useForm<QuarantineFormData>({
    resolver: zodResolver(quarantineSchema),
    defaultValues: { notes: "" },
  });

  const reviewMutation = useMutation({
    mutationFn: ({ approve, notes }: { approve: boolean; notes: string }) =>
      api.patch(`/projects/${projectId}/artifacts/${artifact.id}/quarantine`, {
        approve,
        notes,
      }),
    onSuccess: (_, vars) => {
      toast.success(vars.approve ? "Artefato aprovado para uso." : "Artefato rejeitado.");
      queryClient.invalidateQueries({ queryKey: ["artifacts", projectId] });
      onClose();
    },
    onError: () => toast.error("Não foi possível processar a revisão. Verifique se preencheu as notas e tente novamente."),
  });

  const onApprove = handleSubmit((data) =>
    reviewMutation.mutate({ approve: true, notes: data.notes })
  );
  const onReject = handleSubmit((data) =>
    reviewMutation.mutate({ approve: false, notes: data.notes })
  );

  const hasLgpd = artifact.relevance_notes?.includes("[AVISO LGPD]") ?? false;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="bg-dark-100 border border-gray-700 rounded-2xl w-full max-w-lg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-400" />
            Revisar Quarentena
          </h2>
          <button
            className="text-gray-400 hover:text-gray-200 transition-colors"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* File info */}
          <div className="flex items-center gap-3 bg-dark-200 rounded-lg p-3">
            <FileIcon mimeType={artifact.mime_type} filename={artifact.original_filename} />
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-200 truncate">
                {artifact.original_filename}
              </p>
              <p className="text-xs text-gray-500">
                {getCategoryLabel(artifact.category)} · {formatBytes(artifact.size_bytes)}
              </p>
            </div>
          </div>

          {/* LGPD warning */}
          {hasLgpd && (
            <div className="flex items-start gap-2 bg-red-900/30 border border-red-700/50 rounded-lg px-3 py-2">
              <ShieldAlert size={14} className="text-red-400 shrink-0 mt-0.5" />
              <span className="text-xs text-red-300">
                Este artefato contém aviso LGPD. Revise com cuidado antes de aprovar.
              </span>
            </div>
          )}

          {/* IA notes */}
          {artifact.relevance_notes && (
            <div>
              <p className="text-xs font-medium text-gray-400 mb-1">Notas da IA:</p>
              <p className="text-xs text-gray-300 bg-dark-200 rounded-lg p-3 leading-relaxed">
                {artifact.relevance_notes}
              </p>
            </div>
          )}

          {/* Review notes */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Notas de revisão <span className="text-red-400">*</span>
            </label>
            <textarea
              {...register("notes")}
              rows={3}
              placeholder="Justifique sua decisão…"
              className="input-field resize-none"
            />
            {errors.notes && (
              <p className="text-xs text-red-400 mt-1">{errors.notes.message}</p>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              className="btn-secondary flex-1"
              onClick={onClose}
              disabled={reviewMutation.isPending}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="flex-1 bg-red-700 hover:bg-red-800 text-white font-semibold px-4 py-2 rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
              onClick={onReject}
              disabled={reviewMutation.isPending}
            >
              {reviewMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <XCircle size={14} />
              )}
              Rejeitar
            </button>
            <button
              type="button"
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-4 py-2 rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
              onClick={onApprove}
              disabled={reviewMutation.isPending}
            >
              {reviewMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <CheckCircle size={14} />
              )}
              Aprovar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Delete Confirm Modal ─────────────────────────────────────────────────────

interface DeleteModalProps {
  artifact: Artifact;
  projectId: string;
  onClose: () => void;
}

function DeleteModal({ artifact, projectId, onClose }: DeleteModalProps) {
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: () =>
      api.delete(`/projects/${projectId}/artifacts/${artifact.id}`),
    onSuccess: () => {
      toast.success("Artefato excluído.");
      queryClient.invalidateQueries({ queryKey: ["artifacts", projectId] });
      onClose();
    },
    onError: () => toast.error("Não foi possível excluir o artefato. Ele pode estar sendo utilizado pelo Gatekeeper ou você não tem permissão para esta ação."),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="bg-dark-100 border border-gray-700 rounded-2xl w-full max-w-md shadow-2xl p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-red-900/40 flex items-center justify-center shrink-0">
            <Trash2 size={18} className="text-red-400" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">Excluir Artefato</h2>
            <p className="text-xs text-gray-400 mt-0.5">Esta ação não pode ser desfeita.</p>
          </div>
        </div>
        <p className="text-sm text-gray-300">
          Tem certeza que deseja excluir{" "}
          <span className="font-medium text-white">{artifact.original_filename}</span>?
        </p>
        <div className="flex gap-3 pt-1">
          <button
            className="btn-secondary flex-1"
            onClick={onClose}
            disabled={deleteMutation.isPending}
          >
            Cancelar
          </button>
          <button
            className="flex-1 bg-red-700 hover:bg-red-800 text-white font-semibold px-4 py-2 rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Trash2 size={14} />
            )}
            Excluir
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function ArtifactsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [showUpload, setShowUpload] = useState(false);
  const [quarantineArtifact, setQuarantineArtifact] = useState<Artifact | null>(null);
  const [deleteArtifact, setDeleteArtifact] = useState<Artifact | null>(null);
  const [pollingEnabled, setPollingEnabled] = useState(false);

  const { data, isLoading, isError } = useQuery<ArtifactsResponse>({
    queryKey: ["artifacts", projectId, statusFilter, categoryFilter],
    queryFn: async () => {
      const params: Record<string, string> = { limit: "50", offset: "0" };
      if (statusFilter) params.status = statusFilter;
      if (categoryFilter) params.category = categoryFilter;
      const res = await api.get(`/projects/${projectId}/artifacts`, { params });
      return res.data;
    },
    enabled: !!projectId,
    refetchInterval: pollingEnabled ? 3000 : false,
  });

  // Enable polling while any artifact is classifying
  useEffect(() => {
    const artifacts = data?.data ?? [];
    const hasClassifying = artifacts.some((a) => a.status === "classifying");
    setPollingEnabled(hasClassifying);
  }, [data]);

  const artifacts = data?.data ?? [];
  const total = data?.total ?? 0;

  const handleUploaded = () => {
    setPollingEnabled(true);
    queryClient.invalidateQueries({ queryKey: ["artifacts", projectId] });
  };

  if (!projectId) {
    return (
      <div className="card text-center text-gray-500 py-16">
        Nenhum projeto selecionado.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <FileText size={22} className="text-violet-400" />
            Artefatos do Projeto
            <HelpIcon text="Registre e gerencie os artefatos do projeto: requisitos, histórias de usuário, especificações técnicas e documentação. Os artefatos alimentam o Gatekeeper e a geração de código por IA." />
          </h1>
          {!isLoading && (
            <p className="text-sm text-gray-500 mt-0.5">
              {total} artefato{total !== 1 ? "s" : ""} encontrado{total !== 1 ? "s" : ""}
            </p>
          )}
        </div>
        <button
          className="btn-primary flex items-center gap-2"
          onClick={() => setShowUpload(true)}
        >
          <Upload size={16} />
          Upload
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Status tabs */}
        <div className="flex items-center gap-1 bg-dark-100 border border-gray-700 rounded-xl p-1 flex-wrap">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setStatusFilter(tab.value)}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                statusFilter === tab.value
                  ? "bg-violet-600 text-white"
                  : "text-gray-400 hover:text-gray-200"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Category filter */}
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="input-field sm:w-64"
        >
          <option value="">Todas as categorias</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-gray-500">
          <Loader2 size={28} className="animate-spin mr-3" />
          Carregando artefatos…
        </div>
      ) : isError ? (
        <div className="card text-center text-red-400 py-16">
          Erro ao carregar artefatos. Tente novamente.
        </div>
      ) : artifacts.length === 0 ? (
        <div className="card text-center py-20 space-y-3">
          <FileText size={40} className="mx-auto text-gray-600" />
          <p className="text-gray-400 font-medium">Nenhum artefato encontrado</p>
          <p className="text-sm text-gray-600">
            {statusFilter || categoryFilter
              ? "Tente remover os filtros aplicados."
              : "Faça upload do primeiro artefato para começar."}
          </p>
          {!statusFilter && !categoryFilter && (
            <button
              className="btn-primary mx-auto flex items-center gap-2 mt-2"
              onClick={() => setShowUpload(true)}
            >
              <Upload size={15} />
              Upload de Artefato
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {artifacts.map((artifact) => {
            // Check if this is a wireframe/design system artifact
            if (artifact.mime_type === "application/design-system") {
              // Parse design metrics from relevance_notes
              const notes = artifact.relevance_notes || "";
              const componentMatch = notes.match(/(\d+)\s+componentes?/);
              const tokenMatch = notes.match(/(\d+)\s+tokens?/);
              const accessibilityMatch = notes.match(/Accessibility:\s+(\d+)%/);
              const responsivenessMatch = notes.match(/Responsiveness:\s+(\d+)%/);
              const completenessMatch = notes.match(/Completeness:\s+(\d+)%/);

              const designData = {
                components_count: componentMatch ? parseInt(componentMatch[1]) : 0,
                tokens_count: tokenMatch ? parseInt(tokenMatch[1]) : 0,
                accessibility_score: accessibilityMatch ? parseInt(accessibilityMatch[1]) : 50,
                responsiveness_score: responsivenessMatch ? parseInt(responsivenessMatch[1]) : 50,
                completeness_score: completenessMatch ? parseInt(completenessMatch[1]) : 50,
              };

              return (
                <WireframeArtifactCard
                  key={artifact.id}
                  artifactId={artifact.id}
                  designName={artifact.original_filename.replace("Design System - ", "")}
                  designSystem={designData}
                  createdAt={artifact.created_at}
                  onDelete={() => setDeleteArtifact(artifact)}
                />
              );
            }

            // Regular artifact card
            return (
              <ArtifactCard
                key={artifact.id}
                artifact={artifact}
                projectId={projectId}
                onQuarantineReview={setQuarantineArtifact}
                onDelete={setDeleteArtifact}
              />
            );
          })}
        </div>
      )}

      {/* Polling indicator */}
      {pollingEnabled && (
        <div className="fixed bottom-6 right-6 bg-dark-100 border border-violet-700/50 rounded-xl px-4 py-2.5 flex items-center gap-2 shadow-lg">
          <Loader2 size={14} className="animate-spin text-violet-400" />
          <span className="text-xs text-violet-300">Classificando via IA…</span>
        </div>
      )}

      {/* Modals */}
      {showUpload && (
        <UploadModal
          projectId={projectId}
          onClose={() => setShowUpload(false)}
          onUploaded={handleUploaded}
        />
      )}
      {quarantineArtifact && (
        <QuarantineModal
          artifact={quarantineArtifact}
          projectId={projectId}
          onClose={() => setQuarantineArtifact(null)}
        />
      )}
      {deleteArtifact && (
        <DeleteModal
          artifact={deleteArtifact}
          projectId={projectId}
          onClose={() => setDeleteArtifact(null)}
        />
      )}
    </div>
  );
}
