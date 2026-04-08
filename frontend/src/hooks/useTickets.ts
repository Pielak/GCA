import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

export interface TicketResponse {
  id: string
  message: string
  is_resolution: boolean
  responder_id: string
  responder_email?: string
  created_at: string
}

export interface SupportTicket {
  id: string
  user_id: string
  user_email?: string
  title: string
  description: string
  error_message?: string
  severity: 'BAIXO' | 'MÉDIO' | 'ALTO' | 'CRÍTICO'
  status: 'ABERTO' | 'RESOLVIDO' | 'FECHADO'
  responses?: TicketResponse[]
  created_at: string
}

export interface TicketsResponse {
  tickets: SupportTicket[]
  total: number
  page: number
  page_size: number
}

export const useTickets = (
  page: number = 1,
  status?: string,
  severity?: string
) => {
  const toast = useToast()

  return useQuery({
    queryKey: ['tickets', page, status, severity],
    queryFn: async () => {
      try {
        const response = await apiClient.get<any>('/admin/tickets', {
          params: {
            page,
            page_size: 25,
            ...(status && { status }),
            ...(severity && { severity }),
          },
        })

        // Backend returns nested format: { tickets: [...], count: n, filters: {...} }
        if (response.data?.tickets && Array.isArray(response.data.tickets)) {
          return {
            tickets: response.data.tickets,
            total: response.data.count,
            page,
            page_size: 25,
          } as TicketsResponse
        }

        return response.data as TicketsResponse
      } catch (error: any) {
        toast.error(error.message || 'Erro ao carregar tickets')
        throw error
      }
    },
    staleTime: 1000 * 60, // 1 minute
  })
}

export const useTicketDetail = (ticketId: string | null) => {
  const toast = useToast()

  return useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: async () => {
      if (!ticketId) return null
      try {
        const response = await apiClient.get<SupportTicket>(`/admin/tickets/${ticketId}`)
        return response.data
      } catch (error: any) {
        toast.error(error.message || 'Erro ao carregar ticket')
        throw error
      }
    },
    enabled: !!ticketId,
    staleTime: 1000 * 60,
  })
}

export const useRespondToTicket = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async ({
      ticketId,
      message,
      isResolution,
    }: {
      ticketId: string
      message: string
      isResolution: boolean
    }) => {
      try {
        const response = await apiClient.post(`/admin/tickets/${ticketId}/respond`, {
          message,
          is_resolution: isResolution,
        })
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['tickets'] })
      queryClient.invalidateQueries({ queryKey: ['ticket', variables.ticketId] })
      toast.success('Resposta enviada com sucesso')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao enviar resposta')
    },
  })
}
