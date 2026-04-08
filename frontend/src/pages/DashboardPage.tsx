import { Card, SkeletonLoader } from '@/components/common'
import { useMetrics } from '@/hooks/useMetrics'
import { Users, Activity, AlertCircle, TrendingUp } from 'lucide-react'

export const DashboardPage: React.FC = () => {
  const { data: metrics, isLoading, error } = useMetrics()

  const metricCards = [
    { icon: Users, label: 'Total de Usuários', value: metrics?.total_users ?? 0 },
    { icon: Activity, label: 'Sessões Ativas', value: metrics?.active_sessions ?? 0 },
    { icon: AlertCircle, label: 'Tickets Abertos', value: metrics?.open_tickets ?? 0 },
    { icon: TrendingUp, label: 'Alertas Críticos', value: metrics?.critical_alerts ?? 0 },
  ]

  if (error) {
    return (
      <div>
        <h1 className="text-3xl font-bold text-white mb-8">Dashboard</h1>
        <div className="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">
          <p>Erro ao carregar métricas do dashboard</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-white mb-8">Dashboard</h1>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {metricCards.map((card, idx) => {
          const Icon = card.icon
          return (
            <Card key={idx} className="flex flex-col">
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <p className="text-gray-400 text-sm mb-2">{card.label}</p>
                  {isLoading ? (
                    <SkeletonLoader height="h-8" width="w-20" />
                  ) : (
                    <p className="text-3xl font-bold text-white">{card.value}</p>
                  )}
                </div>
                <Icon className="w-8 h-8 text-blue-500 flex-shrink-0" />
              </div>
            </Card>
          )
        })}
      </div>

      {/* Additional Info */}
      <Card title="Status do Sistema">
        {isLoading ? (
          <SkeletonLoader count={3} />
        ) : (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Uptime</span>
              <span className="text-white font-medium">{metrics?.system_uptime?.toFixed(2)}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Tempo Médio de Resposta</span>
              <span className="text-white font-medium">{metrics?.avg_response_time?.toFixed(0)}ms</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Status do Backend</span>
              <span className="inline-block w-3 h-3 bg-green-500 rounded-full animate-pulse"></span>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
