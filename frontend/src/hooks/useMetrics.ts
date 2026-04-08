import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

export interface DashboardMetrics {
  total_users: number
  active_sessions: number
  open_tickets: number
  critical_alerts: number
  system_uptime: number
  avg_response_time: number
}

export const useMetrics = () => {
  const toast = useToast()

  return useQuery({
    queryKey: ['dashboard', 'metrics'],
    queryFn: async () => {
      try {
        const response = await apiClient.get<{ data: DashboardMetrics }>('/admin/dashboard/metrics')
        return response.data.data || response.data
      } catch (error: any) {
        toast.error(error.message || 'Erro ao carregar métricas')
        throw error
      }
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchInterval: 1000 * 60, // 1 minute
  })
}
