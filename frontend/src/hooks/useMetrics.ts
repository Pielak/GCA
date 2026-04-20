import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'

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
      } catch (error: unknown) {
        toast.error(getErrorMessage(error))
        throw error
      }
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchInterval: 1000 * 60, // 1 minute
  })
}
