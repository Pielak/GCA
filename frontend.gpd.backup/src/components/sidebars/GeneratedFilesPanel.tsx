import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileCode,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  Edit2,
  Copy,
  Download,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/services/api";
import toast from "react-hot-toast";

interface GeneratedFile {
  id: string;
  component_name: string;
  target_framework: string;
  file_path: string | null;
  file_ext: string | null;
  todos_count: number;
  status: string;
  created_at: string;
}

interface TodoItem {
  line_number: number;
  content: string;
  priority: "high" | "medium" | "low";
}

interface GeneratedFilePanelProps {
  projectId: string;
  onEditComponent?: (componentId: string, componentName: string) => void;
}

export function GeneratedFilesPanel({
  projectId,
  onEditComponent
}: GeneratedFilePanelProps) {
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  // Fetch generated components
  const { data: componentsData, isLoading: isLoadingComponents } = useQuery({
    queryKey: ["generated-components", projectId],
    queryFn: async () => {
      const response = await api.get(
        `/projects/${projectId}/components?limit=100`
      );
      return response.data;
    },
  });

  // Fetch TODOs for selected file
  const { data: todosData, isLoading: isLoadingTodos } = useQuery({
    queryKey: ["component-todos", projectId, selectedFileId],
    queryFn: async () => {
      if (!selectedFileId) return null;
      const response = await api.get(
        `/projects/${projectId}/components/${selectedFileId}/todos`
      );
      return response.data;
    },
    enabled: !!selectedFileId,
  });

  // Fetch component code
  const { data: codeData } = useQuery({
    queryKey: ["component-code", projectId, selectedFileId],
    queryFn: async () => {
      if (!selectedFileId) return null;
      const response = await api.get(
        `/projects/${projectId}/components/${selectedFileId}`
      );
      return response.data;
    },
    enabled: !!selectedFileId,
  });

  const toggleFileExpand = (fileId: string) => {
    const newSet = new Set(expandedFiles);
    if (newSet.has(fileId)) {
      newSet.delete(fileId);
    } else {
      newSet.add(fileId);
    }
    setExpandedFiles(newSet);
  };

  const handleCopyCode = () => {
    if (codeData?.data?.code_content) {
      navigator.clipboard.writeText(codeData.data.code_content);
      toast.success("Código copiado!");
    }
  };

  const handleDownloadFile = () => {
    if (!codeData?.data) return;

    const element = document.createElement("a");
    const file = new Blob([codeData.data.code_content], {
      type: "text/plain",
    });
    element.href = URL.createObjectURL(file);
    element.download = codeData.data.file_path || "generated-file.tsx";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "high":
        return "text-red-400 bg-red-500/10";
      case "medium":
        return "text-yellow-400 bg-yellow-500/10";
      default:
        return "text-blue-400 bg-blue-500/10";
    }
  };

  const files = componentsData?.data || [];

  return (
    <div className="flex h-full flex-col bg-slate-900 border-l border-slate-700">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-slate-700 p-4">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <FileCode size={16} />
          Arquivos Gerados
        </h3>
        <p className="text-xs text-slate-400 mt-1">
          {files.length} arquivo{files.length !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Files List */}
      <div className="flex-1 overflow-y-auto">
        {isLoadingComponents ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-slate-400 text-sm">Carregando arquivos...</div>
          </div>
        ) : files.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-slate-400 text-xs text-center p-4">
              Nenhum arquivo gerado ainda. Gere componentes ou páginas.
            </div>
          </div>
        ) : (
          <div className="space-y-1 p-2">
            {files.map((file: GeneratedFile) => (
              <div key={file.id} className="space-y-1">
                {/* File Item */}
                <button
                  onClick={() => {
                    setSelectedFileId(file.id);
                    toggleFileExpand(file.id);
                  }}
                  className={clsx(
                    "w-full flex items-center gap-2 px-3 py-2 rounded text-sm text-left transition-colors",
                    selectedFileId === file.id
                      ? "bg-blue-600/20 text-blue-300"
                      : "text-slate-300 hover:bg-slate-700/50"
                  )}
                >
                  {expandedFiles.has(file.id) ? (
                    <ChevronDown size={14} />
                  ) : (
                    <ChevronRight size={14} />
                  )}
                  <FileCode size={14} className="flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="truncate font-medium">{file.component_name}</div>
                    <div className="text-xs text-slate-500">
                      {file.target_framework}
                    </div>
                  </div>
                  {file.todos_count > 0 && (
                    <div className="flex-shrink-0 bg-orange-500/20 text-orange-400 text-xs font-bold px-2 py-1 rounded">
                      {file.todos_count}
                    </div>
                  )}
                </button>

                {/* Expanded Details */}
                {expandedFiles.has(file.id) && selectedFileId === file.id && (
                  <div className="pl-8 border-l border-slate-700 space-y-3 py-2">
                    {/* File Info */}
                    <div className="space-y-1 text-xs">
                      {file.file_path && (
                        <div>
                          <div className="text-slate-500">Caminho:</div>
                          <div className="text-slate-300 font-mono break-all">
                            {file.file_path}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Action Buttons */}
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={handleCopyCode}
                        className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded text-xs bg-slate-700/50 hover:bg-slate-600 text-slate-300 transition-colors"
                        title="Copiar código"
                      >
                        <Copy size={12} />
                        Copiar
                      </button>
                      <button
                        onClick={handleDownloadFile}
                        className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded text-xs bg-slate-700/50 hover:bg-slate-600 text-slate-300 transition-colors"
                        title="Baixar arquivo"
                      >
                        <Download size={12} />
                        Baixar
                      </button>
                      <button
                        onClick={() => {
                          if (onEditComponent) {
                            onEditComponent(file.id, file.component_name);
                          } else {
                            setIsEditing(!isEditing);
                          }
                        }}
                        className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded text-xs bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 transition-colors"
                        title="Editar código"
                      >
                        <Edit2 size={12} />
                        Editar
                      </button>
                    </div>

                    {/* TODOs Section */}
                    {isLoadingTodos ? (
                      <div className="text-xs text-slate-400">Carregando TODOs...</div>
                    ) : todosData?.data?.todos && todosData.data.todos.length > 0 ? (
                      <div className="space-y-2 border-t border-slate-700 pt-2">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                          <AlertTriangle size={12} />
                          TODOs ({todosData.data.total_todos})
                        </div>

                        <div className="space-y-1">
                          {todosData.data.todos.map(
                            (todo: TodoItem, idx: number) => (
                              <div
                                key={idx}
                                className={clsx(
                                  "text-xs p-2 rounded border-l-2",
                                  todo.priority === "high"
                                    ? "border-red-500/50 bg-red-500/5"
                                    : todo.priority === "medium"
                                    ? "border-yellow-500/50 bg-yellow-500/5"
                                    : "border-blue-500/50 bg-blue-500/5"
                                )}
                              >
                                <div className="flex items-start gap-2">
                                  <span
                                    className={clsx(
                                      "font-bold text-xs flex-shrink-0 mt-0.5",
                                      getPriorityColor(todo.priority)
                                    )}
                                  >
                                    {todo.priority === "high"
                                      ? "🔴"
                                      : todo.priority === "medium"
                                      ? "🟡"
                                      : "🔵"}
                                  </span>
                                  <div className="flex-1">
                                    <div className="text-slate-300">
                                      {todo.content}
                                    </div>
                                    <div className="text-slate-500 text-xs mt-1">
                                      Linha {todo.line_number}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            )
                          )}
                        </div>

                        {/* Priority Summary */}
                        <div className="flex gap-2 text-xs border-t border-slate-700 pt-2 mt-2">
                          {todosData.data.high_priority > 0 && (
                            <div className="flex items-center gap-1">
                              <span className="text-red-400">🔴</span>
                              <span className="text-slate-400">
                                {todosData.data.high_priority}
                              </span>
                            </div>
                          )}
                          {todosData.data.medium_priority > 0 && (
                            <div className="flex items-center gap-1">
                              <span className="text-yellow-400">🟡</span>
                              <span className="text-slate-400">
                                {todosData.data.medium_priority}
                              </span>
                            </div>
                          )}
                          {todosData.data.low_priority > 0 && (
                            <div className="flex items-center gap-1">
                              <span className="text-blue-400">🔵</span>
                              <span className="text-slate-400">
                                {todosData.data.low_priority}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-slate-500 flex items-center gap-1 border-t border-slate-700 pt-2">
                        <CheckCircle2 size={12} />
                        Nenhum TODO neste arquivo
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
