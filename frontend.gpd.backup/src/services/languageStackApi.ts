/**
 * Language Stack & Test Documents API Integration
 *
 * Serviço para comunicação com endpoints Phase 2 Backend:
 * - GET /supported-languages
 * - GET /stacks-for-language/{language}
 * - GET /infrastructure-recommendation
 * - POST /tests/generate
 * - GET /tests
 * - GET /version-updates
 */

import { api } from './api';

// ── Types ──────────────────────────────────────────────────────────────────

export interface StackOptions {
  frameworks: Array<{ name: string; version: string; description?: string }>;
  orms: Array<{ name: string; version: string; description?: string }>;
  test_frameworks: Array<{ name: string; version: string; description?: string }>;
  build_tools: Array<{ name: string; version: string; description?: string }>;
  databases: Array<{ name: string; version: string; description?: string }>;
  cache_options: Array<{ name: string; version: string; description?: string }>;
  additional_tools: Array<{ name: string; version: string; description?: string }>;
  recommended_stack: {
    api_backend: Record<string, string>;
    web_app: Record<string, string>;
    cli_tool: Record<string, string>;
  };
}

export interface SupportedLanguagesResponse {
  project_id: string;
  supported_languages: string[];
  count: number;
}

export interface StacksForLanguageResponse {
  project_id: string;
  language: string;
  stacks: StackOptions;
}

export interface InfrastructureRecommendation {
  project_id: string;
  language: string;
  use_case: string;
  recommended_stack: Record<string, string>;
}

export interface TestDocument {
  id: string;
  type: 'unit' | 'integration';
  objective: string;
  scope: string;
  test_cases_count: number;
  status: 'template' | 'active' | 'archived';
  created_at: string;
  created_by: string;
}

export interface TestDocumentDetail {
  id: string;
  project_id: string;
  type: 'unit' | 'integration';
  objective: string;
  scope: string;
  test_cases: Array<{
    id: string;
    name: string;
    preconditions: string;
    steps: string[];
    expected_result: string;
  }>;
  status: 'template' | 'active' | 'archived';
  editable_by_qa: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface GenerateTestsRequest {
  generated_code_ids: string[];
  test_types: ('unit' | 'integration')[];
}

export interface GenerateTestsResponse {
  project_id: string;
  generated_tests: TestDocument[];
}

export interface VersionUpdate {
  id: string;
  tool_name: string;
  language: string;
  current_version: string;
  available_version: string;
  is_breaking_change: boolean;
  recommendation?: string;
  acknowledged: boolean;
  notified_at?: string;
  created_at: string;
}

export interface VersionUpdatesResponse {
  project_id: string;
  version_updates: VersionUpdate[];
  total: number;
  unread_count: number;
}

// ── Language Research Types (Phase 3B) ──────────────────────────────────────

export interface LanguageResearchStartResponse {
  job_id: string;
  language: string;
  status: 'researching' | 'cached';
  estimate_seconds: number;
  result?: LanguageResearchResult;
}

export interface LanguageResearchResult {
  frameworks: Array<{ name: string; stars?: number; trending?: boolean }>;
  orms: Array<{ name: string; stars?: number }>;
  test_frameworks: Array<{ name: string }>;
  build_tools: Array<{ name: string }>;
  description?: string;
}

export interface LanguageResearchPollResponse {
  status: 'researching' | 'completed' | 'failed';
  language: string;
  job_id: string;
  result?: LanguageResearchResult;
  error?: string;
}

// ── API Methods ────────────────────────────────────────────────────────────

export const languageStackApi = {
  /**
   * Obter lista de linguagens suportadas
   */
  getSupportedLanguages: async (projectId: string): Promise<SupportedLanguagesResponse> => {
    const response = await api.get<SupportedLanguagesResponse>(
      `/projects/${projectId}/supported-languages`
    );
    return response.data;
  },

  /**
   * Obter stacks compatíveis para uma linguagem
   */
  getStacksForLanguage: async (projectId: string, language: string): Promise<StacksForLanguageResponse> => {
    const response = await api.get<StacksForLanguageResponse>(
      `/projects/${projectId}/stacks-for-language/${language}`
    );
    return response.data;
  },

  /**
   * Obter recomendação de infraestrutura para linguagem + use case
   */
  getInfrastructureRecommendation: async (
    projectId: string,
    language: string,
    useCase: string = 'api_backend'
  ): Promise<InfrastructureRecommendation> => {
    const response = await api.get<InfrastructureRecommendation>(
      `/projects/${projectId}/infrastructure-recommendation?language=${language}&use_case=${useCase}`
    );
    return response.data;
  },

  /**
   * Gerar planos de teste (Unit + Integration) automaticamente
   */
  generateTests: async (
    projectId: string,
    request: GenerateTestsRequest
  ): Promise<GenerateTestsResponse> => {
    const response = await api.post<GenerateTestsResponse>(
      `/projects/${projectId}/tests/generate`,
      request
    );
    return response.data;
  },

  /**
   * Listar planos de teste
   */
  listTestDocuments: async (
    projectId: string,
    testType?: 'unit' | 'integration'
  ): Promise<{ project_id: string; test_documents: TestDocument[]; total: number }> => {
    let url = `/projects/${projectId}/tests`;
    if (testType) {
      url += `?test_type=${testType}`;
    }
    const response = await api.get(url);
    return response.data;
  },

  /**
   * Obter detalhes de um plano de teste
   */
  getTestDocument: async (projectId: string, testId: string): Promise<TestDocumentDetail> => {
    const response = await api.get<TestDocumentDetail>(
      `/projects/${projectId}/tests/${testId}`
    );
    return response.data;
  },

  /**
   * Disparar verificação imediata de atualizações
   */
  checkVersionUpdates: async (projectId: string): Promise<{ project_id: string; updates_found: number; updates: any[] }> => {
    const response = await api.post(`/projects/${projectId}/version-check`, {});
    return response.data;
  },

  /**
   * Listar notificações de atualização
   */
  listVersionUpdates: async (projectId: string, acknowledged?: boolean): Promise<VersionUpdatesResponse> => {
    let url = `/projects/${projectId}/version-updates`;
    if (acknowledged !== undefined) {
      url += `?acknowledged=${acknowledged}`;
    }
    const response = await api.get<VersionUpdatesResponse>(url);
    return response.data;
  },

  /**
   * Marcar notificação como lida
   */
  acknowledgeVersionUpdate: async (projectId: string, updateId: string): Promise<any> => {
    const response = await api.post(
      `/projects/${projectId}/version-updates/${updateId}/acknowledge`,
      {}
    );
    return response.data;
  },

  /**
   * Iniciar pesquisa dinâmica de stacks para uma linguagem (Phase 3B)
   * Dispara N8N webhook para pesquisar na internet
   */
  startLanguageResearch: async (
    projectId: string,
    language: string
  ): Promise<LanguageResearchStartResponse> => {
    const response = await api.post<LanguageResearchStartResponse>(
      `/projects/${projectId}/language-research/start?language=${encodeURIComponent(language)}`,
      {}
    );
    return response.data;
  },

  /**
   * Poll resultado da pesquisa de linguagem
   * Cliente deve chamar isso a cada 1-2 segundos até status != 'researching'
   */
  pollLanguageResearch: async (
    projectId: string,
    language: string,
    jobId: string
  ): Promise<LanguageResearchPollResponse> => {
    const response = await api.get<LanguageResearchPollResponse>(
      `/projects/${projectId}/language-research/${encodeURIComponent(language)}/${jobId}`
    );
    return response.data;
  },
};
