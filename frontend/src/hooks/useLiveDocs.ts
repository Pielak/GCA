import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage, getErrorStatus } from '@/lib/errors'

/**
 * MVP 10 Fase 10.7 — Hooks pra LiveDocs reais (docs vivas).
 *
 * module_doc → Ollama (baixa criticidade §6.2)
 * index|architecture → Premium (alta criticidade §6.3)
 *
 * Mesmo padrão de stale/provenance das Fases 10.2/10.3 (TestSpecs).
 */

export type LiveDocType = 'module_doc' | 'index' | 'architecture'

export interface LiveDocProvenance {
  ocg_version?: number
  questionnaire_id?: string | null
  ingested_doc_ids?: string[]
  neighbors_considered?: string[]
  modules_considered?: string[]
  llm?: {
    provider: string
    model: string
  }
  prompt_hash?: string
  generated_at?: string
}

export interface LiveDocListItem {
  id: string
  project_id: string
  module_id: string | null
  doc_type: LiveDocType
  content_preview: string
  content_chars: number
  ocg_version_at_generation: number | null
  generated_at: string | null
  generator_provider: string | null
  generator_model: string | null
  is_stale: boolean
  stale_reason: string | null
}

export interface LiveDocDetail extends LiveDocListItem {
  content: string
  provenance: LiveDocProvenance | null
  current_ocg_version: number | null
}

// ============================================================================
// Queries
// ============================================================================

export const useLiveDocs = (
  projectId: string | undefined,
  filters?: { doc_type?: LiveDocType; module_id?: string },
) => {
  return useQuery({
    queryKey: ['live-docs', projectId, filters?.doc_type, filters?.module_id],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (filters?.doc_type) params.set('doc_type', filters.doc_type)
      if (filters?.module_id) params.set('module_id', filters.module_id)
      const qs = params.toString()
      const url = `/projects/${projectId}/live-docs${qs ? `?${qs}` : ''}`
      const r = await apiClient.get<LiveDocListItem[]>(url)
      return r.data
    },
    enabled: !!projectId,
    staleTime: 30_000,
  })
}

export const useLiveDocDetail = (
  projectId: string | undefined,
  docId: string | undefined,
  enabled: boolean = true,
) => {
  return useQuery({
    queryKey: ['live-docs', projectId, 'detail', docId],
    queryFn: async () => {
      const r = await apiClient.get<LiveDocDetail>(
        `/projects/${projectId}/live-docs/${docId}`,
      )
      return r.data
    },
    enabled: !!projectId && !!docId && enabled,
  })
}

// ============================================================================
// Mutations — geradores
// ============================================================================

export const useGenerateModuleDoc = (projectId: string | undefined) => {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (moduleId: string) => {
      const r = await apiClient.post(
        `/projects/${projectId}/modules/${moduleId}/live-docs/generate`,
      )
      return r.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['live-docs', projectId] })
      toast.success('Documentação do módulo gerada via Ollama.')
    },
    onError: (err: unknown) => {
      const status = getErrorStatus(err)
      if (status === 503) {
        toast.error('Ollama não configurado no projeto. Settings → IA.')
      } else if (status === 400) {
        toast.error(getErrorMessage(err))
      } else {
        toast.error(getErrorMessage(err))
      }
    },
  })
}

export const useGenerateConsolidatedDoc = (projectId: string | undefined) => {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (docType: 'index' | 'architecture') => {
      const r = await apiClient.post(
        `/projects/${projectId}/live-docs/generate-consolidated?doc_type=${docType}`,
      )
      return r.data
    },
    onSuccess: (_data, docType) => {
      qc.invalidateQueries({ queryKey: ['live-docs', projectId] })
      toast.success(`Doc ${docType} gerada via Premium.`)
    },
    onError: (err: unknown) => {
      const status = getErrorStatus(err)
      if (status === 503) {
        toast.error('Provider Premium (Anthropic/OpenAI) não configurado.')
      } else if (status === 400) {
        toast.error(getErrorMessage(err))
      } else {
        toast.error(getErrorMessage(err))
      }
    },
  })
}

export const useBulkRegenerateModuleDocs = (projectId: string | undefined) => {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async () => {
      const r = await apiClient.post(
        `/projects/${projectId}/live-docs/regenerate`,
      )
      return r.data as {
        total: number
        generated: number
        failed: number
        errors: Array<{ module_id: string; module_name: string; error: string }>
      }
    },
    onSuccess: (report) => {
      qc.invalidateQueries({ queryKey: ['live-docs', projectId] })
      if (report.failed === 0) {
        toast.success(`${report.generated} docs gerados.`)
      } else {
        toast.info(`${report.generated} gerados, ${report.failed} com falha.`)
      }
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err))
    },
  })
}

export const useBulkRegenerateConsolidatedDocs = (projectId: string | undefined) => {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async () => {
      const r = await apiClient.post(
        `/projects/${projectId}/live-docs/regenerate-consolidated`,
      )
      return r.data as {
        generated: number
        failed: number
        errors: Array<{ doc_type: string; error: string }>
      }
    },
    onSuccess: (report) => {
      qc.invalidateQueries({ queryKey: ['live-docs', projectId] })
      if (report.failed === 0) {
        toast.success('Index + Architecture gerados via Premium.')
      } else {
        toast.info(`${report.generated} gerados, ${report.failed} com falha.`)
      }
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err))
    },
  })
}
