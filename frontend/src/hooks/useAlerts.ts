import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

export interface SystemAlert {
  id: string
  alert_type: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  message: string
  details?: string
  status: 'pending' | 'acknowledged'
  acknowledged_at?: string
  acknowledged_by?: string
  sent_to_teams: boolean
  sent_to_slack: boolean
  sent_via_email: boolean
  created_at: string
}

export interface AlertsResponse {
  alerts: SystemAlert[]
  total: number
  page: number
  page_size: number
}

export const useAlerts = (
  page: number = 1,
  severity?: string,
  status?: string,
  limit: number = 50
) => {
  const toast = useToast()

  return useQuery({
    queryKey: ['alerts', page, severity, status, limit],
    queryFn: async () => {
      try {
        const response = await apiClient.get<any>('/admin/alerts/history', {
          params: {
            page,
            page_size: limit,
            ...(severity && { severity }),
            ...(status && { status }),
          },
        })

        // Backend returns nested format: { alerts: [...], count: n, filters: {...} }
        if (response.data?.alerts && Array.isArray(response.data.alerts)) {
          return {
            alerts: response.data.alerts,
            total: response.data.count,
            page,
            page_size: limit,
          } as AlertsResponse
        }

        return response.data as AlertsResponse
      } catch (error: any) {
        toast.error(error.message || 'Erro ao carregar alertas')
        throw error
      }
    },
    staleTime: 1000 * 60, // 1 minute
    refetchInterval: 1000 * 60, // Auto-refresh every minute
  })
}

export const useAcknowledgeAlert = () => {
  const queryClient = useQueryClient()
  const toast = useToast()

  return useMutation({
    mutationFn: async (alertId: string) => {
      try {
        const response = await apiClient.post(`/admin/alerts/${alertId}/acknowledge`, {})
        return response.data
      } catch (error: any) {
        throw error
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      toast.success('Alerta reconhecido')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Erro ao reconhecer alerta')
    },
  })
}
