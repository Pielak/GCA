/**
 * Página: RepositoryFilesPage
 * Integração bidirecional com GitHub — Ver, editar, sincronizar arquivos
 */

import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  ChevronRight,
  Code2,
  Save,
  RotateCcw,
  Eye,
  Check,
  X,
  GitBranch,
  AlertCircle,
  Loader,
} from "lucide-react";

import { CodeEditor } from "@/components/CodeEditor";
import { RepositoryFileTree } from "@/components/RepositoryFileTree";
import { FileDiffPreview } from "@/components/FileDiffPreview";
import { ConflictModal, ConflictType } from "@/components/ConflictModal";
import { repositoryFilesApi, RepositoryFile, DiffPreview } from "@/services/repositoryFilesApi";
import { useAuthStore } from "@/store/auth";

export function RepositoryFilesPage() {
  const { projectId, integrationId } = useParams<{
    projectId: string;
    integrationId: string;
  }>();

  if (!projectId || !integrationId) {
    return <div className="p-4 text-red-500">Invalid project or integration ID</div>;
  }

  const { user } = useAuthStore();
  const qc = useQueryClient();

  // State
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [editedContent, setEditedContent] = useState("");
  const [isDirty, setIsDirty] = useState(false);
  const [currentDraftId, setCurrentDraftId] = useState<string | null>(null);
  const [showDiffPreview, setShowDiffPreview] = useState(false);
  const [currentDiff, setCurrentDiff] = useState<DiffPreview | null>(null);
  const [showConflictModal, setShowConflictModal] = useState(false);
  const [conflictType, setConflictType] = useState<ConflictType>("sync_conflict");
  const [conflictMessage, setConflictMessage] = useState("");

  // Query: List files
  const { data: files = [], isLoading: filesLoading } = useQuery<RepositoryFile[]>({
    queryKey: ["repo-files", projectId, integrationId],
    queryFn: () =>
      repositoryFilesApi.listFiles(projectId, integrationId, "", true),
  });

  // Query: File content
  const { data: currentFile, isLoading: fileLoading } = useQuery({
    queryKey: ["repo-file-content", projectId, integrationId, selectedFile],
    queryFn: () =>
      repositoryFilesApi.getFileContent(projectId, integrationId, selectedFile!),
    enabled: !!selectedFile,
  });

  // Effect: Update editor when file changes
  useEffect(() => {
    if (currentFile) {
      setEditedContent(currentFile.content || "");
      setIsDirty(false);
      setCurrentDraftId(null);
    }
  }, [currentFile]);

  // Mutation: Create draft
  const createDraftMutation = useMutation({
    mutationFn: (content: string) =>
      repositoryFilesApi.createDraft(projectId, integrationId, selectedFile!, content),
    onSuccess: (data) => {
      setCurrentDraftId(data.draft_id);
      setIsDirty(false);
      toast.success("Rascunho criado");
      setCurrentDiff({
        original_content: editedContent,
        edited_content: editedContent,
        diff: data.diff_preview.diff,
        added_lines: data.diff_preview.added_lines,
        change_summary: data.diff_preview.change_summary,
      });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.message || "Falha ao criar rascunho");
    },
  });

  // Mutation: Save draft
  const saveDraftMutation = useMutation({
    mutationFn: (content: string) =>
      repositoryFilesApi.saveDraft(projectId, integrationId, currentDraftId!, content),
    onSuccess: (data) => {
      setIsDirty(false);
      toast.success("Rascunho atualizado");
      qc.invalidateQueries({
        queryKey: ["repo-draft", projectId, integrationId, currentDraftId],
      });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.message || "Falha ao salvar rascunho");
    },
  });

  // Mutation: Get diff
  const getDiffMutation = useMutation({
    mutationFn: async () => {
      if (!currentDraftId) throw new Error("No draft selected");
      return repositoryFilesApi.getDiff(projectId, integrationId, currentDraftId);
    },
    onSuccess: (data) => {
      setCurrentDiff(data);
      setShowDiffPreview(true);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.message || "Falha ao carregar diff");
    },
  });

  // Mutation: Approve draft
  const approveDraftMutation = useMutation({
    mutationFn: (comment?: string) =>
      repositoryFilesApi.approveDraft(projectId, integrationId, currentDraftId!, comment),
    onSuccess: () => {
      toast.success("Rascunho aprovado! Você pode sincronizar com GitHub.");
      qc.invalidateQueries({
        queryKey: ["repo-draft", projectId, integrationId, currentDraftId],
      });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.message || "Falha ao aprovar rascunho");
    },
  });

  // Mutation: Sync to GitHub
  const syncMutation = useMutation({
    mutationFn: () =>
      repositoryFilesApi.syncToGithub(projectId, integrationId, currentDraftId!),
    onSuccess: (data) => {
      toast.success(`Sincronizado com sucesso! Commit: ${data.commit_sha.slice(0, 7)}`);
      setCurrentDraftId(null);
      setEditedContent("");
      setSelectedFile(null);
      setShowConflictModal(false);
      qc.invalidateQueries({ queryKey: ["repo-files", projectId, integrationId] });
    },
    onError: (error: any) => {
      const status = error.response?.status;
      const message = error.response?.data?.message || "Falha ao sincronizar";

      if (status === 409) {
        setConflictType("sync_conflict");
        setConflictMessage(message);
        setShowConflictModal(true);
      } else {
        toast.error(message);
      }
    },
  });

  // Handlers
  const handleSelectFile = async (filePath: string) => {
    setSelectedFile(filePath);
  };

  const handleEditChange = (content: string) => {
    setEditedContent(content);
    setIsDirty(true);
  };

  const handleSaveDraft = () => {
    if (currentDraftId) {
      saveDraftMutation.mutate(editedContent);
    } else {
      createDraftMutation.mutate(editedContent);
    }
  };

  const handleCancel = () => {
    setEditedContent(currentFile?.content || "");
    setIsDirty(false);
    setCurrentDraftId(null);
  };

  const handlePreviewDiff = () => {
    if (currentDraftId) {
      getDiffMutation.mutate();
    }
  };

  const handleApprove = () => {
    approveDraftMutation.mutate(undefined);
  };

  const handleSync = () => {
    syncMutation.mutate(undefined);
  };

  const handleConflictDiscard = async () => {
    if (!selectedFile || !currentDraftId) return;

    try {
      // Fetch remote content
      const remoteFile = await repositoryFilesApi.getFileContent(
        projectId,
        integrationId,
        selectedFile
      );

      const remoteContent = remoteFile.content || "";

      // Update draft with remote content
      setEditedContent(remoteContent);
      setShowConflictModal(false);

      // Save draft with remote content
      saveDraftMutation.mutate(remoteContent, {
        onSuccess: () => {
          toast.success("Sincronizado com a versão do GitHub");
          // Re-attempt sync after a short delay
          setTimeout(() => {
            syncMutation.mutate(undefined);
          }, 500);
        },
        onError: () => {
          toast.error("Falha ao sincronizar com remoto");
        },
      });
    } catch (error) {
      toast.error("Falha ao carregar arquivo remoto");
    }
  };

  const handleConflictKeep = () => {
    // User wants to keep their edits and overwrite remote
    // Close modal and retry sync with force flag
    setShowConflictModal(false);

    setTimeout(() => {
      // Call syncToGithub with force=true to bypass conflict detection
      repositoryFilesApi
        .syncToGithub(projectId, integrationId, currentDraftId!, true)
        .then((data) => {
          toast.success(
            `Sincronizado com sucesso! Commit: ${data.commit_sha.slice(0, 7)}`
          );
          setCurrentDraftId(null);
          setEditedContent("");
          setSelectedFile(null);
          qc.invalidateQueries({ queryKey: ["repo-files", projectId, integrationId] });
        })
        .catch((error) => {
          toast.error(error.response?.data?.message || "Falha ao sincronizar");
        });
    }, 500);
  };

  const handleConflictCancel = () => {
    setShowConflictModal(false);
  };

  // Computed
  const canEdit = user && ["admin", "project_manager", "tech_lead", "dev_senior"].includes(user.role);
  const canApprove = user && ["tech_lead", "qa_engineer", "compliance", "security"].includes(user.role);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Code2 className="text-violet-400" size={28} />
          <div>
            <h1 className="text-2xl font-bold text-gray-100">Arquivos do Repositório</h1>
            <p className="text-sm text-gray-400 mt-1">
              Ver, editar e sincronizar arquivos com GitHub
            </p>
          </div>
        </div>

        {/* Breadcrumb */}
        {selectedFile && (
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-4 font-mono">
            <span>📁</span>
            {selectedFile.split("/").map((part, i) => (
              <span key={i}>
                {i > 0 && <ChevronRight className="inline mx-1" size={14} />}
                {part}
              </span>
            ))}
          </div>
        )}

        {/* Main Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          {/* Sidebar: File Tree */}
          <div className="lg:col-span-1 bg-gray-800/50 border border-gray-700 rounded-lg overflow-hidden flex flex-col">
            <div className="p-3 border-b border-gray-700 bg-gray-900/50">
              <h2 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                <GitBranch size={16} />
                Arquivos
              </h2>
            </div>
            <div className="flex-1 overflow-y-auto">
              {filesLoading ? (
                <div className="p-4 text-center text-gray-400">
                  <Loader className="animate-spin inline mb-2" size={20} />
                  <p className="text-xs">Carregando...</p>
                </div>
              ) : (
                <RepositoryFileTree
                  files={files}
                  selectedFile={selectedFile || undefined}
                  onSelectFile={handleSelectFile}
                />
              )}
            </div>
          </div>

          {/* Main: Code Editor */}
          <div className="lg:col-span-3 bg-gray-800/50 border border-gray-700 rounded-lg overflow-hidden flex flex-col">
            {selectedFile ? (
              <>
                {/* Editor Header */}
                <div className="flex items-center justify-between p-3 border-b border-gray-700 bg-gray-900/50">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-gray-400">
                      {currentFile?.language?.toUpperCase() || "TEXT"}
                    </span>
                    {currentDraftId && (
                      <span className="px-2 py-1 bg-violet-900/50 text-violet-200 text-xs rounded">
                        📝 RASCUNHO
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {isDirty && (
                      <span className="text-xs text-yellow-400 flex items-center gap-1">
                        ⚠️ Não salvo
                      </span>
                    )}
                  </div>
                </div>

                {/* Editor */}
                <div className="flex-1 overflow-auto">
                  {fileLoading ? (
                    <div className="h-full flex items-center justify-center">
                      <Loader className="animate-spin text-gray-500" size={32} />
                    </div>
                  ) : (
                    <CodeEditor
                      value={editedContent}
                      language={currentFile?.language}
                      onChange={handleEditChange}
                      height="100%"
                      className="border-0"
                    />
                  )}
                </div>

                {/* Action Buttons */}
                {canEdit && (
                  <div className="flex items-center justify-between p-3 border-t border-gray-700 bg-gray-900/50 flex-wrap gap-2">
                    <div className="flex gap-2">
                      <button
                        onClick={handleCancel}
                        disabled={!isDirty && !currentDraftId}
                        className="flex items-center gap-1 px-3 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-gray-100 rounded text-sm transition-colors"
                      >
                        <RotateCcw size={16} />
                        Cancelar
                      </button>

                      <button
                        onClick={handleSaveDraft}
                        disabled={!isDirty}
                        className="flex items-center gap-1 px-3 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors"
                      >
                        <Save size={16} />
                        Salvar Rascunho
                      </button>

                      {currentDraftId && (
                        <button
                          onClick={handlePreviewDiff}
                          className="flex items-center gap-1 px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-medium transition-colors"
                        >
                          <Eye size={16} />
                          Preview Diff
                        </button>
                      )}
                    </div>

                    {currentDraftId && canApprove && (
                      <div className="flex gap-2">
                        <button
                          onClick={handleApprove}
                          className="flex items-center gap-1 px-3 py-2 bg-green-600 hover:bg-green-500 text-white rounded text-sm font-medium transition-colors"
                        >
                          <Check size={16} />
                          Aprovar ✅
                        </button>

                        <button
                          onClick={handleSync}
                          disabled={approveDraftMutation.isPending}
                          className="flex items-center gap-1 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors"
                        >
                          <GitBranch size={16} />
                          🚀 Sincronizar
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="flex items-center justify-center h-96 text-gray-400">
                <div className="text-center">
                  <Code2 size={48} className="mx-auto mb-3 opacity-50" />
                  <p>Selecione um arquivo para editar</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Diff Preview Modal */}
      <FileDiffPreview
        isOpen={showDiffPreview}
        diff={currentDiff}
        fileName={selectedFile || undefined}
        onClose={() => setShowDiffPreview(false)}
      />

      {/* Conflict Modal */}
      <ConflictModal
        isOpen={showConflictModal}
        type={conflictType}
        fileName={selectedFile || undefined}
        message={conflictMessage}
        onDiscard={handleConflictDiscard}
        onKeep={handleConflictKeep}
        onCancel={handleConflictCancel}
        discardLoading={saveDraftMutation.isPending}
        keepLoading={syncMutation.isPending}
      />
    </div>
  );
}
