import { useState, useMemo } from "react";
import { HelpIcon } from "@/components/HelpIcon";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  Code2,
  Zap,
  X,
  Check,
  Edit3,
  ShieldAlert,
  Hash,
  ChevronRight,
  Save,
  MessageSquare,
  Layers,
  AlertTriangle,
  RefreshCw,
  CheckCircle2,
  Lock,
  FolderOpen,
  Folder,
  FileCode,
  BarChart2,
  ChevronDown,
  Shield,
  GitBranch,
  Sparkles,
  Eye,
  EyeOff,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { toast } from "react-hot-toast";
import clsx from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Module {
  id: string;
  name: string;
  description: string;
  file_path: string;
  layer: "infrastructure" | "data" | "business" | "api" | "presentation";
  priority: number;
  dependencies: string[];
  built: boolean;
  requirements_detail: string;
}

interface GeneratedFile {
  id: string;
  file_path: string;
  language: string;
  status: "draft" | "pending_review" | "approved" | "rejected";
  todos_count: number;
  requirements_refs: string[];
  ai_provider: string;
  ai_model: string;
  traceability_uuid: string;
  has_manual_edits: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  content?: string;
  // Push ao repositório
  commit_sha: string | null;
  pushed_at: string | null;
  push_url: string | null;
}

interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  file?: GeneratedFile;
  children: TreeNode[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const LANG_COLORS: Record<string, string> = {
  python: "bg-blue-900/50 text-blue-300 border-blue-700/50",
  javascript: "bg-yellow-900/50 text-yellow-300 border-yellow-700/50",
  typescript: "bg-blue-900/50 text-blue-300 border-blue-700/50",
  java: "bg-orange-900/50 text-orange-300 border-orange-700/50",
  go: "bg-cyan-900/50 text-cyan-300 border-cyan-700/50",
  rust: "bg-orange-900/50 text-orange-300 border-orange-700/50",
  sql: "bg-green-900/50 text-green-300 border-green-700/50",
  html: "bg-red-900/50 text-red-300 border-red-700/50",
  css: "bg-pink-900/50 text-pink-300 border-pink-700/50",
};

function langBadge(lang: string) {
  const cls = LANG_COLORS[lang.toLowerCase()] ?? "bg-gray-800 text-gray-400 border-gray-700";
  return `text-xs px-2 py-0.5 rounded-full border font-mono ${cls}`;
}

function prismLang(lang: string): string {
  const map: Record<string, string> = {
    python: "python", javascript: "javascript", typescript: "typescript",
    java: "java", go: "go", rust: "rust", sql: "sql", html: "html", css: "css",
  };
  return map[lang.toLowerCase()] ?? "text";
}

/** Completeness % for a single file */
function fileCompleteness(f: GeneratedFile): number {
  if (f.status === "approved") return f.todos_count === 0 ? 100 : 80;
  if (f.status === "pending_review") return 60;
  // draft
  return Math.max(10, 40 - f.todos_count * 5);
}

/** Build tree from flat file list */
function buildTree(files: GeneratedFile[]): TreeNode {
  const root: TreeNode = { name: "", path: "", isDir: true, children: [] };
  for (const file of files) {
    const parts = file.file_path.split("/");
    let cur = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const seg = parts[i];
      const dirPath = parts.slice(0, i + 1).join("/");
      let dir = cur.children.find(c => c.isDir && c.name === seg);
      if (!dir) {
        dir = { name: seg, path: dirPath, isDir: true, children: [] };
        cur.children.push(dir);
      }
      cur = dir;
    }
    cur.children.push({
      name: parts[parts.length - 1],
      path: file.file_path,
      isDir: false,
      file,
      children: [],
    });
  }
  return root;
}

const CAN_APPROVE_ROLES = ["tech_lead", "dev_senior", "admin"];

// ─── Module Layer Config ──────────────────────────────────────────────────────

const LAYER_ORDER: Module["layer"][] = [
  "infrastructure", "data", "business", "api", "presentation",
];

const LAYER_LABELS: Record<Module["layer"], string> = {
  infrastructure: "Infraestrutura",
  data: "Dados",
  business: "Negócio",
  api: "API",
  presentation: "Apresentação",
};

const LAYER_COLORS: Record<Module["layer"], string> = {
  infrastructure: "bg-orange-900/50 text-orange-300 border-orange-700/50",
  data: "bg-blue-900/50 text-blue-300 border-blue-700/50",
  business: "bg-violet-900/50 text-violet-300 border-violet-700/50",
  api: "bg-cyan-900/50 text-cyan-300 border-cyan-700/50",
  presentation: "bg-pink-900/50 text-pink-300 border-pink-700/50",
};

// ─── Tag Input ────────────────────────────────────────────────────────────────

function TagInput({ tags, onChange, placeholder }: {
  tags: string[]; onChange: (tags: string[]) => void; placeholder?: string;
}) {
  const [input, setInput] = useState("");
  function add() {
    const val = input.trim().toUpperCase();
    if (val && !tags.includes(val)) onChange([...tags, val]);
    setInput("");
  }
  return (
    <div className="flex flex-wrap gap-1 bg-dark-100 border border-gray-600 rounded-lg px-2 py-1.5 min-h-[38px] focus-within:ring-2 focus-within:ring-violet-600 focus-within:border-transparent">
      {tags.map((t) => (
        <span key={t} className="flex items-center gap-1 bg-violet-900/50 text-violet-300 border border-violet-700/50 text-xs px-2 py-0.5 rounded-full">
          {t}
          <button type="button" onClick={() => onChange(tags.filter((x) => x !== t))} className="hover:text-red-400 transition-colors">
            <X size={10} />
          </button>
        </span>
      ))}
      <input
        className="bg-transparent text-gray-100 text-sm outline-none flex-1 min-w-[80px] placeholder-gray-500"
        value={input}
        placeholder={tags.length === 0 ? placeholder : ""}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (["Enter", ",", " "].includes(e.key)) { e.preventDefault(); add(); }
        }}
        onBlur={add}
      />
    </div>
  );
}

// ─── Tree Node Component ──────────────────────────────────────────────────────

function TreeItem({
  node, depth, selectedFileId, onSelect, expandedDirs, toggleDir,
}: {
  node: TreeNode;
  depth: number;
  selectedFileId: string | null;
  onSelect: (file: GeneratedFile) => void;
  expandedDirs: Set<string>;
  toggleDir: (path: string) => void;
}) {
  const isExpanded = expandedDirs.has(node.path);

  if (node.isDir) {
    return (
      <div>
        <button
          onClick={() => toggleDir(node.path)}
          className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-dark-200 rounded transition-colors text-left"
          style={{ paddingLeft: `${8 + depth * 12}px` }}
        >
          {isExpanded
            ? <FolderOpen size={13} className="text-violet-400 shrink-0" />
            : <Folder size={13} className="text-gray-500 shrink-0" />}
          <span className="text-xs text-gray-400 truncate flex-1">{node.name}</span>
          <ChevronDown
            size={11}
            className={clsx("text-gray-600 transition-transform shrink-0", !isExpanded && "-rotate-90")}
          />
        </button>
        {isExpanded && node.children.map(child => (
          <TreeItem
            key={child.path}
            node={child}
            depth={depth + 1}
            selectedFileId={selectedFileId}
            onSelect={onSelect}
            expandedDirs={expandedDirs}
            toggleDir={toggleDir}
          />
        ))}
      </div>
    );
  }

  const file = node.file!;
  const pct = fileCompleteness(file);
  const isSelected = selectedFileId === file.id;

  return (
    <button
      onClick={() => onSelect(file)}
      className={clsx(
        "w-full flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors text-left group",
        isSelected ? "bg-violet-900/40 border border-violet-700/50" : "hover:bg-dark-200 border border-transparent"
      )}
      style={{ paddingLeft: `${8 + depth * 12}px` }}
      title={file.file_path}
    >
      <FileCode size={12} className={clsx("shrink-0", isSelected ? "text-violet-300" : "text-gray-600 group-hover:text-gray-400")} />
      <span className={clsx("text-xs truncate flex-1 font-mono", isSelected ? "text-violet-200" : "text-gray-400")}>
        {node.name}
      </span>
      <div className="flex items-center gap-1 shrink-0">
        {file.todos_count > 0 && (
          <span className="text-[10px] px-1 rounded bg-amber-900/50 text-amber-400 font-mono">{file.todos_count}</span>
        )}
        {file.status === "approved"
          ? <Check size={11} className="text-emerald-400" />
          : file.status === "pending_review"
          ? <RefreshCw size={11} className="text-blue-400" />
          : <Edit3 size={11} className="text-amber-500" />}
      </div>
      {/* Completeness bar */}
      <div className="w-8 h-1 rounded-full bg-dark-300 overflow-hidden shrink-0">
        <div
          className={clsx("h-full rounded-full", pct === 100 ? "bg-emerald-500" : pct >= 60 ? "bg-blue-500" : "bg-amber-500")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </button>
  );
}

// ─── File Tree Sidebar ────────────────────────────────────────────────────────

function FileTreeSidebar({
  files, selectedFileId, onSelect, onToggleSidebar,
}: {
  files: GeneratedFile[];
  selectedFileId: string | null;
  onSelect: (file: GeneratedFile) => void;
  onToggleSidebar: () => void;
}) {
  const tree = useMemo(() => buildTree(files), [files]);

  // Initialize all dirs expanded
  const allDirs = useMemo(() => {
    const dirs = new Set<string>();
    function collect(node: TreeNode) {
      if (node.isDir && node.path) dirs.add(node.path);
      node.children.forEach(collect);
    }
    collect(tree);
    return dirs;
  }, [tree]);

  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(allDirs);

  // Update when new dirs appear
  useMemo(() => {
    setExpandedDirs(prev => {
      const next = new Set(prev);
      allDirs.forEach(d => next.add(d));
      return next;
    });
  }, [allDirs]);

  function toggleDir(path: string) {
    setExpandedDirs(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  const totalFiles = files.length;
  const approvedCount = files.filter(f => f.status === "approved").length;
  const overallPct = totalFiles === 0 ? 0 : Math.round(files.reduce((sum, f) => sum + fileCompleteness(f), 0) / totalFiles);
  const gatekeeperPct = totalFiles === 0 ? 0 : Math.round(files.filter(f => f.requirements_refs.length > 0).length / totalFiles * 100);
  const totalTodos = files.reduce((sum, f) => sum + f.todos_count, 0);

  return (
    <div className="flex flex-col h-full border-l border-gray-800">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-1.5 mb-2">
          <GitBranch size={13} className="text-violet-400" />
          <span className="text-xs font-semibold text-gray-300">Arquivos Gerados</span>
          <span className="text-xs text-gray-600">{totalFiles}</span>
          <button
            onClick={onToggleSidebar}
            className="ml-auto text-gray-500 hover:text-gray-300 transition-colors"
            title="Ocultar painel de arquivos"
          >
            <EyeOff size={13} />
          </button>
        </div>

        {totalFiles > 0 && (
          <div className="space-y-1.5">
            {/* Completeness */}
            <div>
              <div className="flex justify-between items-center mb-0.5">
                <span className="text-[10px] text-gray-500 flex items-center gap-1">
                  <BarChart2 size={9} /> Completude
                </span>
                <span className={clsx("text-[10px] font-semibold", overallPct === 100 ? "text-emerald-400" : overallPct >= 60 ? "text-blue-400" : "text-amber-400")}>
                  {overallPct}%
                </span>
              </div>
              <div className="h-1.5 bg-dark-300 rounded-full overflow-hidden">
                <div
                  className={clsx("h-full rounded-full transition-all", overallPct === 100 ? "bg-emerald-500" : overallPct >= 60 ? "bg-blue-500" : "bg-amber-500")}
                  style={{ width: `${overallPct}%` }}
                />
              </div>
            </div>
            {/* Gatekeeper adherence */}
            <div>
              <div className="flex justify-between items-center mb-0.5">
                <span className="text-[10px] text-gray-500 flex items-center gap-1">
                  <Shield size={9} /> Aderência GPD
                </span>
                <span className={clsx("text-[10px] font-semibold", gatekeeperPct >= 80 ? "text-emerald-400" : gatekeeperPct >= 50 ? "text-amber-400" : "text-red-400")}>
                  {gatekeeperPct}%
                </span>
              </div>
              <div className="h-1.5 bg-dark-300 rounded-full overflow-hidden">
                <div
                  className={clsx("h-full rounded-full transition-all", gatekeeperPct >= 80 ? "bg-emerald-500" : gatekeeperPct >= 50 ? "bg-amber-500" : "bg-red-500")}
                  style={{ width: `${gatekeeperPct}%` }}
                />
              </div>
            </div>
            {/* Quick stats */}
            <div className="flex gap-2 pt-0.5">
              <span className="text-[10px] text-gray-600">{approvedCount}/{totalFiles} aprovados</span>
              {totalTodos > 0 && <span className="text-[10px] text-amber-600">{totalTodos} TODOs</span>}
            </div>
          </div>
        )}
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1">
        {totalFiles === 0 ? (
          <div className="text-center py-8 px-3">
            <Code2 size={24} className="text-gray-700 mx-auto mb-2" />
            <p className="text-xs text-gray-600">Nenhum arquivo gerado ainda</p>
          </div>
        ) : (
          tree.children.map(child => (
            <TreeItem
              key={child.path}
              node={child}
              depth={0}
              selectedFileId={selectedFileId}
              onSelect={onSelect}
              expandedDirs={expandedDirs}
              toggleDir={toggleDir}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ─── Inline Code Editor ───────────────────────────────────────────────────────

function InlineCodeEditor({
  initialFile, projectId, canApprove, onClose, isFullFrame, onToggleFullFrame,
}: {
  initialFile: GeneratedFile;
  projectId: string;
  canApprove: boolean;
  onClose: () => void;
  isFullFrame: boolean;
  onToggleFullFrame: () => void;
}) {
  const queryClient = useQueryClient();
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [approveModal, setApproveModal] = useState(false);
  const [approveComment, setApproveComment] = useState("");

  const { data: file } = useQuery({
    queryKey: ["codegen-file", projectId, initialFile.id],
    queryFn: async () => {
      const { data } = await api.get<{ success: boolean; data: GeneratedFile }>(
        `/projects/${projectId}/codegen/files/${initialFile.id}`
      );
      return data.data;
    },
    initialData: initialFile,
    enabled: !initialFile.content,
  });

  const approveMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.patch(
        `/projects/${projectId}/codegen/files/${file!.id}/approve`,
        { comment: approveComment.trim() || undefined }
      );
      return data;
    },
    onSuccess: () => {
      toast.success("Arquivo aprovado.");
      queryClient.invalidateQueries({ queryKey: ["codegen-files", projectId] });
      queryClient.invalidateQueries({ queryKey: ["codegen-file", projectId, file!.id] });
      setApproveModal(false);
      setApproveComment("");
    },
    onError: () => toast.error("Não foi possível aprovar. Apenas Tech Lead, Dev Sênior e Admin têm permissão."),
  });

  const editMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.patch(
        `/projects/${projectId}/codegen/files/${file!.id}/edit`,
        { content: editContent }
      );
      return data;
    },
    onSuccess: () => {
      toast.success("Revisão salva.");
      queryClient.invalidateQueries({ queryKey: ["codegen-files", projectId] });
      queryClient.invalidateQueries({ queryKey: ["codegen-file", projectId, file!.id] });
      setEditMode(false);
    },
    onError: () => toast.error("Não foi possível salvar. Verifique sua conexão e tente novamente."),
  });

  const reviewMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(
        `/projects/${projectId}/codegen/files/${file!.id}/review`,
        { content: editContent }
      );
      return data;
    },
    onSuccess: (data: any) => {
      if (data?.data?.reviewed_content) {
        setEditContent(data.data.reviewed_content);
        toast.success("GPD revisou o código — comentários injetados. Salve para aplicar.");
      } else {
        toast.success("Revisão GPD concluída. Sem alterações necessárias.");
      }
    },
    onError: () => toast.error("Revisão GPD indisponível no momento."),
  });

  const content = file?.content ?? "";

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-dark-50">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800 shrink-0">
        <div className="flex flex-col gap-0.5 min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={langBadge(file?.language ?? "")}>{file?.language}</span>
            {file?.status === "approved" ? (
              <span className="badge-approved">Aprovado</span>
            ) : (
              <span className="badge-draft">
                {file?.status === "pending_review" ? "Em revisão" : "Rascunho GPD"}
              </span>
            )}
            {file?.has_manual_edits && (
              <span className="text-xs text-violet-400 flex items-center gap-1">
                <Edit3 size={10} /> Editado
              </span>
            )}
            {(file?.todos_count ?? 0) > 0 && (
              <span className="text-xs text-amber-400 flex items-center gap-1">
                <Hash size={10} /> {file!.todos_count} TODO{file!.todos_count > 1 ? "s" : ""}
              </span>
            )}
          </div>
          <p className="text-xs font-mono text-gray-400 truncate">{file?.file_path}</p>
        </div>
        <div className="flex items-center gap-1 ml-3 shrink-0">
          <button
            onClick={onToggleFullFrame}
            className="text-gray-600 hover:text-gray-300 transition-colors p-1 rounded hover:bg-dark-300"
            title={isFullFrame ? "Restaurar layout" : "Expandir para tela cheia"}
          >
            {isFullFrame ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button onClick={onClose} className="text-gray-600 hover:text-gray-300 transition-colors p-1 rounded hover:bg-dark-300">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-800 shrink-0 flex-wrap">
        {!editMode ? (
          <>
            <button
              className="btn-secondary text-xs flex items-center gap-1 py-1"
              onClick={() => { setEditContent(content); setEditMode(true); }}
            >
              <Edit3 size={12} /> Editar
            </button>
            {canApprove && file?.status !== "approved" && (
              <button
                className="btn-primary text-xs flex items-center gap-1 py-1"
                onClick={() => setApproveModal(true)}
              >
                <Check size={12} /> Aprovar
              </button>
            )}
          </>
        ) : (
          <>
            <button
              className="btn-primary text-xs flex items-center gap-1 py-1"
              onClick={() => editMutation.mutate()}
              disabled={editMutation.isPending}
            >
              {editMutation.isPending
                ? <span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
                : <Save size={12} />}
              Salvar revisão
            </button>
            <button
              className="text-xs flex items-center gap-1.5 px-3 py-1 rounded-lg border border-violet-700/50 text-violet-400 hover:bg-violet-900/20 transition-colors disabled:opacity-40"
              onClick={() => reviewMutation.mutate()}
              disabled={reviewMutation.isPending}
              title="O GPD analisa o código, injeta comentários de pontos de atenção e TODO rastreáveis"
            >
              {reviewMutation.isPending
                ? <span className="w-3 h-3 border border-violet-400/30 border-t-violet-400 rounded-full animate-spin" />
                : <Sparkles size={12} />}
              Revisar com GPD
            </button>
            <button
              className="btn-secondary text-xs flex items-center gap-1 py-1"
              onClick={() => setEditMode(false)}
            >
              <X size={12} /> Cancelar
            </button>
          </>
        )}
      </div>

      {/* Code area */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {editMode ? (
          <textarea
            className="flex-1 min-h-0 w-full bg-[#1e1e2e] text-gray-100 font-mono text-sm p-4 resize-none outline-none border-0"
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            spellCheck={false}
          />
        ) : content ? (
          <div className="flex-1 min-h-0 overflow-auto">
            <SyntaxHighlighter
              language={prismLang(file?.language ?? "")}
              style={vscDarkPlus}
              showLineNumbers
              customStyle={{ margin: 0, borderRadius: 0, minHeight: "100%", fontSize: "0.8rem" }}
            >
              {content}
            </SyntaxHighlighter>
          </div>
        ) : (
          <div className="flex items-center justify-center h-32 text-gray-600 text-sm">
            Carregando conteúdo...
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-1.5 border-t border-gray-800 text-[10px] text-gray-600 flex items-center gap-4 flex-wrap shrink-0">
        <span><span className="text-gray-500">Provider:</span> {file?.ai_provider}/{file?.ai_model}</span>
        {file?.reviewed_by && <span><span className="text-gray-500">Revisado por:</span> {file.reviewed_by}</span>}
        <span className="font-mono truncate">UUID: {file?.traceability_uuid}</span>
        {file?.commit_sha && (
          <a
            href={file.push_url ?? undefined}
            target="_blank"
            rel="noopener noreferrer"
            className={clsx(
              "flex items-center gap-1 font-mono",
              file.push_url ? "text-emerald-600 hover:text-emerald-400 transition-colors" : "text-emerald-700"
            )}
            title={`Commit: ${file.commit_sha}`}
          >
            <GitBranch size={9} />
            {file.commit_sha.slice(0, 8)}
          </a>
        )}
      </div>

      {/* Approve modal */}
      {approveModal && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/60">
          <div className="bg-dark-100 border border-gray-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl space-y-4 mx-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-white flex items-center gap-2">
                <MessageSquare size={16} className="text-emerald-400" />
                Aprovar Arquivo
              </h3>
              <button onClick={() => { setApproveModal(false); setApproveComment(""); }} className="text-gray-500 hover:text-gray-300">
                <X size={16} />
              </button>
            </div>
            <p className="text-xs font-mono text-gray-500 truncate">{file?.file_path}</p>
            <div>
              <label className="text-xs text-gray-400 font-medium">Comentário <span className="text-gray-600">(opcional)</span></label>
              <textarea
                className="input-field text-sm mt-1 resize-none"
                rows={3}
                placeholder="Observações sobre a revisão..."
                value={approveComment}
                onChange={(e) => setApproveComment(e.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button className="btn-secondary text-sm" onClick={() => { setApproveModal(false); setApproveComment(""); }} disabled={approveMutation.isPending}>
                Cancelar
              </button>
              <button className="btn-primary text-sm flex items-center gap-2" onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
                {approveMutation.isPending
                  ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  : <Check size={14} />}
                Confirmar Aprovação
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function CodegenPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canApprove = CAN_APPROVE_ROLES.includes(user?.role ?? "");

  // Form state
  const [selectedModuleId, setSelectedModuleId] = useState("");
  const [moduleName, setModuleName] = useState("");
  const [requirements, setRequirements] = useState("");
  const [modulesRefreshKey, setModulesRefreshKey] = useState(0);
  const [selectedProposedId, setSelectedProposedId] = useState("");

  // Tree/editor state
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [leftPanelVisible, setLeftPanelVisible] = useState(true);
  const [fullFrame, setFullFrame] = useState(false);

  // Fetch modules
  const { data: modules = [], isLoading: modulesLoading, isError: modulesError } = useQuery({
    queryKey: ["codegen-modules", projectId, modulesRefreshKey],
    queryFn: async () => {
      const qs = modulesRefreshKey > 0 ? "?refresh=true" : "";
      const { data } = await api.get<{ success: boolean; data: Module[]; cached: boolean; message?: string }>(
        `/projects/${projectId}/codegen/modules${qs}`
      );
      if (!data.success && data.data.length === 0) throw new Error(data.message || "Falha ao gerar plano");
      return data.data;
    },
    enabled: !!projectId,
    retry: false,
  });

  // Fetch approved proposed modules
  const { data: proposedModulesData } = useQuery<{ success: boolean; data: Array<{
    id: string; name: string; status: string; derived_directory: string | null;
    technical_context: string | null; priority: string; module_type: string | null;
  }> }>({
    queryKey: ["proposed-modules", projectId],
    queryFn: () => api.get(`/projects/${projectId}/modules`).then(r => r.data),
    enabled: !!projectId,
  });
  const approvedProposedModules = (proposedModulesData?.data ?? []).filter(m => m.status === "approved");

  function handleProposedModuleSelect(id: string) {
    setSelectedProposedId(id);
    const pm = approvedProposedModules.find(m => m.id === id);
    if (pm) {
      setModuleName(pm.derived_directory ?? pm.name);
      if (pm.technical_context) setRequirements(pm.technical_context);
    }
  }

  const selectedModule = modules.find((m) => m.id === selectedModuleId) ?? null;
  const unbuildDeps = selectedModule ? modules.filter((m) => selectedModule.dependencies.includes(m.id) && !m.built) : [];
  const isBlocked = unbuildDeps.length > 0;

  function handleModuleSelect(id: string) {
    setSelectedModuleId(id);
    const m = modules.find((mod) => mod.id === id);
    if (m) { setModuleName(m.file_path || m.name); setRequirements(m.requirements_detail); }
  }

  // Fetch files
  const { data: files = [], isLoading: filesLoading } = useQuery({
    queryKey: ["codegen-files", projectId],
    queryFn: async () => {
      const { data } = await api.get<{ success: boolean; data: GeneratedFile[] }>(
        `/projects/${projectId}/codegen/files`
      );
      return data.data;
    },
    enabled: !!projectId,
  });

  const selectedFile = files.find(f => f.id === selectedFileId) ?? null;

  // Run codegen
  const runMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ success: boolean; data: { job_id: string; status: string } }>(
        `/projects/${projectId}/codegen/run`,
        { module_name: moduleName.trim(), requirements: requirements.trim() }
      );
      return data;
    },
    onSuccess: () => {
      toast.success("Código gerado! Carregando arquivos...");
      queryClient.refetchQueries({ queryKey: ["codegen-files", projectId] });
      queryClient.refetchQueries({ queryKey: ["codegen-modules", projectId] });
      setSelectedModuleId("");
      setModuleName("");
      setRequirements("");
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.message ?? "Não foi possível iniciar a geração. Verifique se o Gatekeeper está aprovado.";
      toast.error(msg);
    },
  });

  const canGenerate = moduleName.trim().length > 0 && requirements.trim().length > 0 && !isBlocked;

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Header */}
      <h1 className="text-2xl font-bold text-white flex items-center gap-2 shrink-0">
        <Code2 size={24} className="text-violet-400" />
        Geração de Código
        <HelpIcon text="O GPD atua como desenvolvedor ativo: o Arquiteto planeja a estrutura, o Dev implementa e o Revisor valida. Selecione um módulo na árvore à direita para visualizar ou editar. Use 'Revisar com GPD' para injetar comentários de qualidade antes de aprovar." />
      </h1>

      {/* 3-panel layout */}
      <div className="flex gap-0 flex-1 min-h-0 rounded-xl overflow-hidden border border-gray-800">

        {/* ── Left: Generation Form ─────────────────────────────────────────── */}
        {/* Collapsed left strip */}
        {!fullFrame && !leftPanelVisible && (
          <div className="w-8 shrink-0 flex flex-col items-center pt-3 gap-2 border-r border-gray-800 bg-dark-100">
            <button
              onClick={() => setLeftPanelVisible(true)}
              className="text-gray-600 hover:text-gray-300 transition-colors p-1 rounded hover:bg-dark-200"
              title="Mostrar painel de geração"
            >
              <Eye size={14} />
            </button>
          </div>
        )}
        {!fullFrame && leftPanelVisible && (
        <div className="w-72 shrink-0 flex flex-col border-r border-gray-800 bg-dark-100">
          {/* Panel header */}
          <div className="flex items-center gap-1.5 px-3 py-2.5 border-b border-gray-800 shrink-0">
            <Zap size={12} className="text-violet-400" />
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex-1">Geração de Código</span>
            <button
              onClick={() => setLeftPanelVisible(false)}
              className="text-gray-500 hover:text-gray-300 transition-colors"
              title="Ocultar painel de geração"
            >
              <EyeOff size={13} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">

          {/* Módulo aprovado pelo Gatekeeper */}
          {approvedProposedModules.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
                <Layers size={11} className="text-violet-400" />
                Módulo do plano
              </h2>
              <select
                className="input-field text-sm bg-dark-100"
                value={selectedProposedId}
                onChange={(e) => handleProposedModuleSelect(e.target.value)}
              >
                <option value="">— Selecionar módulo aprovado —</option>
                {approvedProposedModules.map((pm) => (
                  <option key={pm.id} value={pm.id}>
                    {pm.name}{pm.module_type ? ` (${pm.module_type})` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Form */}
          <div className="space-y-3">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
              <Zap size={11} className="text-violet-400" />
              Novo Módulo
            </h2>

            {/* Module selector */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-xs text-gray-400 font-medium flex items-center gap-1">
                  <Layers size={10} className="text-violet-400" /> Módulo do Plano
                </label>
                <button
                  type="button"
                  onClick={() => setModulesRefreshKey((k) => k + 1)}
                  className="text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1 transition-colors"
                  disabled={modulesLoading}
                >
                  <RefreshCw size={10} className={modulesLoading ? "animate-spin" : ""} />
                  Regenerar
                </button>
              </div>

              {modulesLoading ? (
                <div className="input-field text-sm text-gray-500 flex items-center gap-2">
                  <span className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />
                  Carregando...
                </div>
              ) : modulesError || modules.length === 0 ? (
                <div className="bg-dark-200 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-500">
                  <p>{modulesError ? "Nenhum artefato ou erro ao gerar plano." : "Sem artefatos. Faça upload primeiro."}</p>
                  <p className="text-gray-600 mt-1">Após upload, clique em "Regenerar".</p>
                </div>
              ) : (
                <select
                  className="input-field text-sm bg-dark-100"
                  value={selectedModuleId}
                  onChange={(e) => handleModuleSelect(e.target.value)}
                >
                  <option value="">— Selecionar módulo —</option>
                  {LAYER_ORDER.map((layer) => {
                    const layerModules = modules.filter((m) => m.layer === layer).sort((a, b) => a.priority - b.priority);
                    if (layerModules.length === 0) return null;
                    return (
                      <optgroup key={layer} label={LAYER_LABELS[layer]}>
                        {layerModules.map((m) => {
                          const hasUnbuiltDeps = modules.some(dep => m.dependencies.includes(dep.id) && !dep.built);
                          const prefix = m.built ? "✓ " : hasUnbuiltDeps ? "⚠ " : "";
                          return (
                            <option key={m.id} value={m.id}>
                              {prefix}#{m.priority} {m.name}{m.file_path ? ` — ${m.file_path}` : ""}
                            </option>
                          );
                        })}
                      </optgroup>
                    );
                  })}
                </select>
              )}

              {selectedModule && (
                <div className="space-y-1 pt-0.5">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={clsx("text-xs px-2 py-0.5 rounded-full border", LAYER_COLORS[selectedModule.layer])}>
                      {LAYER_LABELS[selectedModule.layer]}
                    </span>
                    <span className="text-xs text-gray-500">#{selectedModule.priority}</span>
                    {selectedModule.built && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-900/40 text-emerald-300 border border-emerald-700/50 flex items-center gap-1">
                        <CheckCircle2 size={10} /> Construído
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 leading-relaxed">{selectedModule.description}</p>
                </div>
              )}

              {isBlocked && (
                <div className="flex items-start gap-2 bg-red-900/20 border border-red-800/40 rounded-lg p-2.5">
                  <Lock size={12} className="text-red-400 mt-0.5 shrink-0" />
                  <div className="space-y-0.5">
                    <p className="text-xs font-medium text-red-400">Dependências não construídas:</p>
                    {unbuildDeps.map((dep) => (
                      <p key={dep.id} className="text-xs text-red-300 flex items-center gap-1">
                        <AlertTriangle size={10} />
                        {dep.name} <span className="text-red-500">(#{dep.priority})</span>
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-1">
              <label className="text-xs text-gray-400 font-medium">Caminho / Nome do Arquivo *</label>
              <input
                type="text"
                className="input-field text-sm font-mono"
                placeholder="ex: backend/app/models/user.py"
                value={moduleName}
                onChange={(e) => setModuleName(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs text-gray-400 font-medium">Requisitos Técnicos *</label>
              <textarea
                className="input-field text-sm resize-none"
                rows={7}
                placeholder="Descreva o que deve ser implementado: classes, funções, regras de negócio, integrações..."
                value={requirements}
                onChange={(e) => setRequirements(e.target.value)}
              />
            </div>

            <button
              className="btn-primary w-full flex items-center justify-center gap-2"
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending || !canGenerate}
            >
              {runMutation.isPending ? (
                <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Gerando...</>
              ) : (
                <><Zap size={15} /> Gerar Código</>
              )}
            </button>

            <div className="flex items-start gap-2 bg-amber-900/20 border border-amber-800/40 rounded-lg p-2.5">
              <ShieldAlert size={13} className="text-amber-400 mt-0.5 shrink-0" />
              <p className="text-xs text-amber-400">
                Requer Gatekeeper aprovado.{" "}
                <Link to={`/projects/${projectId}/gatekeeper`} className="underline hover:text-amber-300 transition-colors">
                  Verificar <ChevronRight size={10} className="inline" />
                </Link>
              </p>
            </div>
          </div>
          </div>
        </div>
        )}

        {/* ── Center: Inline Code Editor ────────────────────────────────────── */}
        <div className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden">
          {filesLoading ? (
            <div className="flex items-center justify-center flex-1 text-gray-600">
              <span className="w-5 h-5 border-2 border-gray-700 border-t-gray-400 rounded-full animate-spin mr-2" />
              Carregando arquivos...
            </div>
          ) : selectedFile ? (
            <InlineCodeEditor
              key={selectedFile.id}
              initialFile={selectedFile}
              projectId={projectId!}
              canApprove={canApprove}
              onClose={() => { setSelectedFileId(null); setFullFrame(false); }}
              isFullFrame={fullFrame}
              onToggleFullFrame={() => setFullFrame((v) => !v)}
            />
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 text-center px-8 space-y-4">
              <div className="w-16 h-16 rounded-2xl bg-dark-200 flex items-center justify-center">
                <Code2 size={28} className="text-gray-600" />
              </div>
              <div>
                <p className="text-gray-400 font-medium">Selecione um arquivo</p>
                <p className="text-gray-600 text-sm mt-1">
                  Clique em qualquer arquivo na árvore à direita para visualizar, editar ou aprovar.
                </p>
              </div>
              {files.length === 0 && (
                <p className="text-gray-600 text-xs max-w-xs">
                  Nenhum arquivo gerado ainda. Use o formulário à esquerda para gerar o primeiro módulo.
                </p>
              )}
            </div>
          )}
        </div>

        {/* ── Right: File Tree Sidebar ──────────────────────────────────────── */}
        {!fullFrame && sidebarVisible && (
          <div className="w-56 shrink-0 overflow-hidden flex flex-col bg-dark-100">
            <FileTreeSidebar
              files={files}
              selectedFileId={selectedFileId}
              onSelect={(f) => setSelectedFileId(f.id)}
              onToggleSidebar={() => setSidebarVisible(false)}
            />
          </div>
        )}

        {/* Collapsed sidebar strip — show-eye button */}
        {!fullFrame && !sidebarVisible && (
          <div className="w-8 shrink-0 flex flex-col items-center pt-3 gap-2 border-l border-gray-800 bg-dark-100">
            <button
              onClick={() => setSidebarVisible(true)}
              className="text-gray-600 hover:text-gray-300 transition-colors p-1 rounded hover:bg-dark-200"
              title="Mostrar arquivos gerados"
            >
              <Eye size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
