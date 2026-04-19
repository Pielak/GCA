import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

// MVP 8 Fase 1 — estágios canônicos do pipeline de ingestão/análise
export type ArguiderStage =
  | 'queued'               // aguardando análise
  | 'extracting_text'      // extraindo texto do documento
  | 'analyzing'            // chamando LLM do Arguidor
  | 'updating_ocg'         // aplicando deltas ao OCG
  | 'regenerating_backlog' // propagando pro backlog / roadmap / gatekeeper
  | 'completed'            // terminou com sucesso
  | 'failed'               // alguma etapa falhou

export interface IngestedDocument {
  id: string
  original_filename: string
  file_type: string
  document_category: string | null
  arguider_status: 'pending' | 'processing' | 'completed' | 'error' | 'quarantined'
  // DT-022: mensagem crua do provider/Arguidor quando arguider_status='error'.
  // A UI humaniza para o GP (ex: 401 → "chave IA rejeitada pelo provedor").
  arguider_error_message?: string | null
  // DT-029: estado de quarentena + tipos PII detectados. GP usa pra decidir
  // se é falso-positivo e clicar em "Liberar".
  quarantine_status?: 'none' | 'quarantined' | 'released'
  pii_fields?: string[]
  ocg_updated: boolean
  file_size_bytes: number
  created_at: string
  source_type?: string | null
  source_url?: string | null
  source_repo_id?: string | null
  content_status?: 'available' | 'lost'
  // MVP 8 Fase 1 — feedback de progresso
  arguider_stage?: ArguiderStage
  arguider_progress_percent?: number
  arguider_stage_updated_at?: string | null
}

export interface DocumentDetail extends IngestedDocument {
  arguider_error_message: string | null
  analysis?: {
    classification: Record<string, any>
    gaps: any[]
    show_stoppers: any[]
    poor_definitions: any[]
    improvement_suggestions: any[]
    module_candidates: any[]
    ocg_fields_to_update: any[]
    tokens_used: number
    latency_ms: number
  }
}

export interface DocumentStatus {
  document_id: string
  arguider_status: 'pending' | 'processing' | 'completed' | 'error' | 'quarantined'
  arguider_started_at: string | null
  arguider_completed_at: string | null
  ocg_updated: boolean
  // MVP 8 Fase 1 — feedback de progresso
  arguider_stage?: ArguiderStage
  arguider_progress_percent?: number
  arguider_stage_updated_at?: string | null
}

// Lista documentos do projeto
export const useDocuments = (projectId: string | undefined) => {
  return useQuery({
    queryKey: ['ingestion', projectId],
    queryFn: async () => {
      const response = await apiClient.get<IngestedDocument[]>(`/projects/${projectId}/ingestion`)
      return response.data
    },
    enabled: !!projectId,
    staleTime: 1000 * 3,
    // MVP 8 Fase 1 — polling adaptativo: 2s enquanto houver doc
    // processando (pra barra avançar visivelmente); 15s caso contrário.
    refetchInterval: (query) => {
      const data = query.state.data as IngestedDocument[] | undefined
      const anyProcessing = Array.isArray(data) && data.some(d =>
        d.arguider_status === 'pending' || d.arguider_status === 'processing'
      )
      return anyProcessing ? 2000 : 15000
    },
  })
}

// MVP 8 Fase 5 — relatório de extração (o que o pipeline entende do doc
// antes do Arguidor). Permite GP confirmar se o doc foi bem interpretado
// ou decidir reenviar em outro formato.
export interface ExtractionReport {
  ok: boolean
  document_id: string
  original_filename: string
  file_type: string
  chars: number
  paragraphs: number
  tables_detected: number
  text_boxes: number
  headers_footers: number
  pdf_layers: string[]
  pdf_pages_with_text: number
  acroform_fields: number
  requirements_functional: string[]
  requirements_non_functional: string[]
  module_hints: string[]
  warnings: string[]
  text_sample: string
}

export const useExtractionReport = (projectId: string | undefined, documentId: string | undefined, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['ingestion', 'extraction-report', projectId, documentId],
    queryFn: async () => {
      const response = await apiClient.get<ExtractionReport>(
        `/projects/${projectId}/ingestion/${documentId}/extraction-report`
      )
      return response.data
    },
    enabled: !!projectId && !!documentId && enabled,
    staleTime: 1000 * 60, // report é caro — cacheia 1min
  })
}

// Detalhe de um documento
export const useDocumentDetail = (projectId: string | undefined, documentId: string | undefined) => {
  return useQuery({
    queryKey: ['ingestion', projectId, documentId],
    queryFn: async () => {
      const response = await apiClient.get<DocumentDetail>(`/projects/${projectId}/ingestion/${documentId}`)
      return response.data
    },
    enabled: !!projectId && !!documentId,
  })
}

// Polling de status (ativo apenas quando há docs processando)
export const useDocumentStatusPolling = (projectId: string | undefined, documentId: string | undefined, enabled: boolean) => {
  return useQuery({
    queryKey: ['ingestion', 'status', projectId, documentId],
    queryFn: async () => {
      const response = await apiClient.get<DocumentStatus>(`/projects/${projectId}/ingestion/${documentId}/status`)
      return response.data
    },
    enabled: !!projectId && !!documentId && enabled,
    refetchInterval: 3000, // Poll a cada 3s
  })
}

// MVP 9 Fase 9.5.2 — módulos elegíveis pra receber vínculo de upload.
export interface EligibleModule {
  id: string
  name: string
  module_type: string
  priority: string
  status: string
  source: string
}

export const useEligibleModules = (projectId: string | undefined, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['ingestion', 'eligible-modules', projectId],
    queryFn: async () => {
      const r = await apiClient.get<EligibleModule[]>(
        `/projects/${projectId}/modules/eligible-for-link`
      )
      return r.data
    },
    enabled: !!projectId && enabled,
    staleTime: 30 * 1000,
  })
}

// Upload de documento (multipart/form-data)
// MVP 9 Fase 9.5.2 — opcionalmente vincula a um módulo do Roadmap via
// target_module_id. Se omitido E for PDF de template GCA, backend tenta
// extrair automaticamente.
export interface UploadDocumentArgs {
  file: File
  targetModuleId?: string | null
}

export const useUploadDocument = (projectId: string | undefined) => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (args: File | UploadDocumentArgs) => {
      const formData = new FormData()
      const file = args instanceof File ? args : args.file
      const targetModuleId = args instanceof File ? null : args.targetModuleId
      formData.append('file', file)
      if (targetModuleId) {
        formData.append('target_module_id', targetModuleId)
      }
      // Não setar Content-Type manualmente — axios detecta FormData e adiciona o
      // boundary. Setar 'multipart/form-data' sem boundary quebra o parser FastAPI.
      const response = await apiClient.post(`/projects/${projectId}/ingestion`, formData)
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['ingestion', projectId] })
      toast.success(`Documento recebido. Análise iniciada.`)
    },
    onError: (error: any) => {
      if (error.status === 409) {
        toast.error('Documento já foi ingerido neste projeto (duplicata).')
      } else if (error.status === 413) {
        toast.error('Arquivo excede o tamanho máximo de 50MB.')
      } else {
        toast.error(error.message || 'Erro ao enviar documento')
      }
    },
  })
}

// Deletar documento
export const useDeleteDocument = (projectId: string | undefined) => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (documentId: string) => {
      const response = await apiClient.delete(`/projects/${projectId}/ingestion/${documentId}`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ingestion', projectId] })
      toast.success('Documento removido com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao remover documento')
    },
  })
}
