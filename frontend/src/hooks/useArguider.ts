import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'

export interface GatekeeperItem {
  id: string
  item_type: 'gap' | 'show_stopper' | 'poor_definition' | 'improvement'
  item_id: string
  // MVP 14 Fase 14.9: stop-rule hit — migração unknown cascata em ArguiderPage.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>
  status: 'pending' | 'resolved' | 'ignored'
  resolution_note: string | null
  resolved_at: string | null
}

export interface GatekeeperSummary {
  total_gaps: number
  open_gaps: number
  total_show_stoppers: number
  open_show_stoppers: number
  total_poor_definitions: number
  total_suggestions: number
  total_modules: number
  modules_pending_approval: number
  modules_approved: number
  modules_rejected: number
  has_blockers: boolean
}

export interface GatekeeperData {
  summary: GatekeeperSummary
  gaps: GatekeeperItem[]
  show_stoppers: GatekeeperItem[]
  poor_definitions: GatekeeperItem[]
  improvement_suggestions: GatekeeperItem[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  module_candidates: any[]
}

// Busca consolidado do Gatekeeper
export const useGatekeeperData = (projectId: string | undefined) => {
  return useQuery({
    queryKey: ['gatekeeper', projectId],
    queryFn: async () => {
      const response = await apiClient.get<GatekeeperData>(`/projects/${projectId}/gatekeeper`)
      return response.data
    },
    enabled: !!projectId,
    staleTime: 1000 * 60,
  })
}

// Resolver um item (enviar resposta/evidência)
export const useResolveItem = (projectId: string | undefined) => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async ({ itemId, note }: { itemId: string; note: string }) => {
      const response = await apiClient.post(`/projects/${projectId}/gatekeeper/items/${itemId}/resolve`, {
        resolution_note: note,
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gatekeeper', projectId] })
      toast.success('Item resolvido com sucesso')
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })
}

// Ignorar um item
export const useIgnoreItem = (projectId: string | undefined) => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async ({ itemId, reason }: { itemId: string; reason: string }) => {
      const response = await apiClient.post(`/projects/${projectId}/gatekeeper/items/${itemId}/ignore`, {
        reason,
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gatekeeper', projectId] })
      toast.success('Item ignorado')
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })
}
