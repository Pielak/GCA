/**
 * API Client para operações de arquivo em repositório
 * Suporta: listar, ler, editar, aprovar, sincronizar com GitHub
 */

import { api } from "./api";

export interface RepositoryFile {
  path: string;
  name: string;
  type: "file" | "dir";
  size?: number;
  sha?: string;
  content?: string;
  language?: string;
  last_modified?: string;
}

export interface RepositoryFileDraft {
  draft_id: string;
  file_path: string;
  language: string;
  status: "editing" | "pending_approval" | "approved" | "synced" | "rejected";
  original_content: string;
  edited_content: string;
  change_summary?: string;
  line_count_before: number;
  line_count_after: number;
  created_at?: string;
  updated_at?: string;
}

export interface DiffPreview {
  original_content: string;
  edited_content: string;
  diff: string;
  added_lines: number;
  change_summary?: string;
}

export const repositoryFilesApi = {
  /**
   * Lista arquivos do repositório
   */
  async listFiles(
    projectId: string,
    integrationId: string,
    dirPath = "",
    recursive = true
  ): Promise<RepositoryFile[]> {
    const response = await api.get(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/files`,
      {
        params: { dir_path: dirPath, recursive },
      }
    );
    return response.data.data || [];
  },

  /**
   * Lê conteúdo completo de arquivo
   */
  async getFileContent(
    projectId: string,
    integrationId: string,
    filePath: string,
    ref?: string
  ): Promise<RepositoryFile> {
    const response = await api.get(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/files/${encodeURIComponent(filePath)}/content`,
      {
        params: ref ? { ref } : {},
      }
    );
    return response.data.data;
  },

  /**
   * Cria novo draft para edição de arquivo
   */
  async createDraft(
    projectId: string,
    integrationId: string,
    filePath: string,
    editedContent: string
  ): Promise<{
    draft_id: string;
    status: string;
    file_path: string;
    language: string;
    change_summary: string;
    line_count_before: number;
    line_count_after: number;
    diff_preview: DiffPreview;
  }> {
    const response = await api.post(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/files/${encodeURIComponent(filePath)}/edit`,
      { edited_content: editedContent }
    );
    return response.data.data;
  },

  /**
   * Recupera draft existente
   */
  async getDraft(
    projectId: string,
    integrationId: string,
    draftId: string
  ): Promise<RepositoryFileDraft> {
    const response = await api.get(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/drafts/${draftId}`
    );
    return response.data.data;
  },

  /**
   * Obtém preview de diff
   */
  async getDiff(
    projectId: string,
    integrationId: string,
    draftId: string
  ): Promise<DiffPreview> {
    const response = await api.get(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/drafts/${draftId}/diff`
    );
    return response.data.data;
  },

  /**
   * Atualiza draft com novo conteúdo
   */
  async saveDraft(
    projectId: string,
    integrationId: string,
    draftId: string,
    editedContent: string
  ): Promise<{ draft_id: string; change_summary: string; line_count_after: number; updated_at: string }> {
    const response = await api.patch(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/drafts/${draftId}/save`,
      { edited_content: editedContent }
    );
    return response.data.data;
  },

  /**
   * Cancela draft e descarta alterações
   */
  async deleteDraft(
    projectId: string,
    integrationId: string,
    draftId: string
  ): Promise<{ success: boolean; message: string }> {
    const response = await api.delete(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/drafts/${draftId}`
    );
    return response.data;
  },

  /**
   * Aprova draft para sincronização
   */
  async approveDraft(
    projectId: string,
    integrationId: string,
    draftId: string,
    comment?: string
  ): Promise<{
    draft_id: string;
    status: string;
    approved_by: string;
    approved_at: string;
  }> {
    const response = await api.post(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/drafts/${draftId}/approve`,
      { comment }
    );
    return response.data.data;
  },

  /**
   * Sincroniza draft aprovado com GitHub (faz push)
   * @param force Se true, ignora detecção de conflitos e força o push
   */
  async syncToGithub(
    projectId: string,
    integrationId: string,
    draftId: string,
    force = false
  ): Promise<{
    success: boolean;
    draft_id: string;
    commit_sha: string;
    push_url: string;
    pushed_at: string;
  }> {
    const response = await api.post(
      `/projects/${projectId}/repo-integrations/${integrationId}/repository/drafts/${draftId}/sync`,
      { force }
    );
    return response.data.data;
  },
};
