import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

/**
 * MVP 10 Fase 10.5 — Hooks pros Planos de Teste (TestSpec).
 *
 * Consumido pela QAReadinessPage (seção "Plano de Testes") e pelo
 * futuro TesterReviewPage tab "Specs" (Fase 10.6).
 */

export type TestSpecType = 'unit' | 'integration' | 'security' | 'compliance' | 'e2e'

export type TestSpecStatus = 'draft' | 'approved' | 'rejected' | 'stale'

export interface TestSpecListItem {
  id: string
  project_id: string
  module_id: string | null
  spec_type: TestSpecType
  status: TestSpecStatus
  content_preview: string
  content_chars: number
  ocg_version_at_generation: number | null
  generated_at: string | null
  generator_provider: string | null
  generator_model: string | null
  approved_by: string | null
  approved_at: string | null
  is_stale: boolean
  stale_reason: string | null
}

export interface TestSpecProvenance {
  ocg_version?: number
  questionnaire_id?: string | null
  ingested_doc_ids?: string[]
  module_snapshot?: {
    id: string
    name: string
    module_type: string
    readiness_status?: string | null
  }
  modules_considered?: string[]
  neighbors_considered?: string[]
  llm?: {
    provider: string
    model: string
    base_url_host?: string
  }
  prompt_hash?: string
  generated_at?: string
}

export interface TestSpecDetail extends TestSpecListItem {
  content: string
  provenance: TestSpecProvenance | null
  rejection_reason: string | null
  current_ocg_version: number | null
}

export interface StaleSummary {
  current_ocg_version: number | null
  test_specs: {
    total: number
    stale: number
    by_type: Record<string, { total: number; stale: number }>
  }
  live_docs: {
    total: number
    stale: number
    by_type: Record<string, { total: number; stale: number }>
  }
  needs_regeneration: boolean
}

// ============================================================================
// Queries
// ============================================================================

export const useTestSpecs = (
  projectId: string | undefined,
  filters?: { spec_type?: TestSpecType; module_id?: string },
) => {
  return useQuery({
    queryKey: ['test-specs', projectId, filters?.spec_type, filters?.module_id],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (filters?.spec_type) params.set('spec_type', filters.spec_type)
      if (filters?.module_id) params.set('module_id', filters.module_id)
      const qs = params.toString()
      const url = `/projects/${projectId}/test-specs${qs ? `?${qs}` : ''}`
      const r = await apiClient.get<TestSpecListItem[]>(url)
      return r.data
    },
    enabled: !!projectId,
    staleTime: 30_000,
  })
}

export const useTestSpecDetail = (
  projectId: string | undefined,
  specId: string | undefined,
  enabled: boolean = true,
) => {
  return useQuery({
    queryKey: ['test-specs', projectId, 'detail', specId],
    queryFn: async () => {
      const r = await apiClient.get<TestSpecDetail>(
        `/projects/${projectId}/test-specs/${specId}`,
      )
      return r.data
    },
    enabled: !!projectId && !!specId && enabled,
  })
}

export const useStaleSummary = (projectId: string | undefined) => {
  return useQuery({
    queryKey: ['test-specs', projectId, 'stale-summary'],
    queryFn: async () => {
      const r = await apiClient.get<StaleSummary>(
        `/projects/${projectId}/test-specs/stale-summary`,
      )
      return r.data
    },
    enabled: !!projectId,
    staleTime: 30_000,
  })
}

// ============================================================================
// Mutations — geradores
// ============================================================================

export const useGenerateModuleSpec = (projectId: string | undefined) => {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (args: { moduleId: string; specType: Exclude<TestSpecType, 'security' | 'compliance'> }) => {
      const r = await apiClient.post(
        `/projects/${projectId}/modules/${args.moduleId}/test-specs/generate?spec_type=${args.specType}`,
      )
      return r.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-specs', projectId] })
      toast.success('Spec gerado via Ollama.')
    },
    onError: (err: any) => {
      const status = err?.status || err?.response?.status
      if (status === 503) {
        toast.error('Ollama não configurado no projeto. Settings → IA.')
      } else if (status === 400) {
        toast.error(err?.message || 'Tipo de spec inválido.')
      } else {
        toast.error(err?.message || 'Falha ao gerar spec.')
      }
    },
  })
}

export const useGenerateGlobalSpec = (projectId: string | undefined) => {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (specType: 'security' | 'compliance') => {
      const r = await apiClient.post(
        `/projects/${projectId}/test-specs/generate-global?spec_type=${specType}`,
      )
      return r.data
    },
    onSuccess: (_data, specType) => {
      qc.invalidateQueries({ queryKey: ['test-specs', projectId] })
      toast.success(`Spec ${specType} gerado via Premium.`)
    },
    onError: (err: any) => {
      const status = err?.status || err?.response?.status
      if (status === 503) {
        toast.error('Provider Premium (Anthropic/OpenAI) não configurado.')
      } else if (status === 400) {
        toast.error(err?.message || 'Validação falhou.')
      } else {
        toast.error(err?.message || 'Falha ao gerar spec global.')
      }
    },
  })
}

export const useBulkRegenerateTestSpecs = (projectId: string | undefined) => {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (specTypes: Array<Exclude<TestSpecType, 'security' | 'compliance'>>) => {
      const csv = specTypes.join(',')
      const r = await apiClient.post(
        `/projects/${projectId}/test-specs/regenerate?spec_types=${csv}`,
      )
      return r.data as {
        total_modules: number
        spec_types: string[]
        generated: number
        failed: number
        errors: Array<{ module_id: string; module_name: string; spec_type: string; error: string }>
      }
    },
    onSuccess: (report) => {
      qc.invalidateQueries({ queryKey: ['test-specs', projectId] })
      if (report.failed === 0) {
        toast.success(`${report.generated} specs gerados.`)
      } else {
        toast.info(`${report.generated} gerados, ${report.failed} com falha.`)
      }
    },
    onError: (err: any) => {
      toast.error(err?.message || 'Falha no bulk regenerate.')
    },
  })
}

export const useBulkRegenerateGlobalSpecs = (projectId: string | undefined) => {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async () => {
      const r = await apiClient.post(
        `/projects/${projectId}/test-specs/regenerate-global`,
      )
      return r.data as {
        generated: number
        failed: number
        errors: Array<{ spec_type: string; error: string }>
      }
    },
    onSuccess: (report) => {
      qc.invalidateQueries({ queryKey: ['test-specs', projectId] })
      if (report.failed === 0) {
        toast.success('Security + Compliance gerados via Premium.')
      } else {
        toast.info(`${report.generated} gerados, ${report.failed} com falha.`)
      }
    },
    onError: (err: any) => {
      toast.error(err?.message || 'Falha ao regerar specs globais.')
    },
  })
}
