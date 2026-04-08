import { useState } from 'react'
import { Card, Badge, Modal, SkeletonLoader } from '@/components/common'
import { useAlerts, useAcknowledgeAlert, type SystemAlert } from '@/hooks/useAlerts'
import { ChevronLeft, ChevronRight, Check } from 'lucide-react'

export const AlertsPage: React.FC = () => {
  const [page, setPage] = useState(1)
  const [severity, setSeverity] = useState<string>('')
  const [status, setStatus] = useState<string>('')
  const [selectedAlert, setSelectedAlert] = useState<SystemAlert | null>(null)

  const { data, isLoading, error } = useAlerts(page, severity || undefined, status || undefined)
  const acknowledgeMutation = useAcknowledgeAlert()

  const handleAcknowledge = (alert: SystemAlert) => {
    setSelectedAlert(alert)
  }

  const confirmAcknowledge = async () => {
    if (!selectedAlert) return
    try {
      await acknowledgeMutation.mutateAsync(selectedAlert.id)
      setSelectedAlert(null)
    } catch (error) {
      // Error already handled by toast
    }
  }

  const severityColors = {
    critical: 'error',
    warning: 'warning',
    info: 'info',
  } as const

  const statusColors = {
    pending: 'warning',
    acknowledged: 'success',
  } as const

  if (error) {
    return (
      <div>
        <h1 className="text-3xl font-bold text-white mb-8">Alertas do Sistema</h1>
        <div className="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">
          <p>Erro ao carregar alertas. Tente novamente.</p>
        </div>
      </div>
    )
  }

  const alerts = data?.alerts || []
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1

  return (
    <div>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-white">Alertas do Sistema</h1>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Card>
          <div>
            <p className="text-gray-400 text-sm mb-1">Alertas Pendentes</p>
            {isLoading ? (
              <SkeletonLoader height="h-8" width="w-20" />
            ) : (
              <p className="text-3xl font-bold text-red-400">
                {alerts.filter(a => a.status === 'pending').length}
              </p>
            )}
          </div>
        </Card>
        <Card>
          <div>
            <p className="text-gray-400 text-sm mb-1">Críticos</p>
            {isLoading ? (
              <SkeletonLoader height="h-8" width="w-20" />
            ) : (
              <p className="text-3xl font-bold text-red-500">
                {alerts.filter(a => a.severity === 'critical').length}
              </p>
            )}
          </div>
        </Card>
        <Card>
          <div>
            <p className="text-gray-400 text-sm mb-1">Total</p>
            {isLoading ? (
              <SkeletonLoader height="h-8" width="w-20" />
            ) : (
              <p className="text-3xl font-bold text-white">{data?.total || 0}</p>
            )}
          </div>
        </Card>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-300 text-sm font-medium mb-2">Severidade</label>
            <select
              value={severity}
              onChange={(e) => {
                setSeverity(e.target.value)
                setPage(1)
              }}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
            >
              <option value="">Todos</option>
              <option value="critical">Crítico</option>
              <option value="warning">Aviso</option>
              <option value="info">Informação</option>
            </select>
          </div>
          <div>
            <label className="block text-gray-300 text-sm font-medium mb-2">Status</label>
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value)
                setPage(1)
              }}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
            >
              <option value="">Todos</option>
              <option value="pending">Pendente</option>
              <option value="acknowledged">Reconhecido</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Alerts Table */}
      {isLoading && !data ? (
        <Card>
          <SkeletonLoader count={5} height="h-12" />
        </Card>
      ) : alerts.length === 0 ? (
        <Card>
          <p className="text-gray-400 text-center py-8">Nenhum alerta encontrado</p>
        </Card>
      ) : (
        <>
          <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700 bg-gray-700">
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Título</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Severidade</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Status</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Data</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Ação</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((alert) => (
                  <tr key={alert.id} className="border-b border-gray-700 hover:bg-gray-700 transition">
                    <td className="px-6 py-4 text-sm text-gray-300 max-w-sm truncate">
                      <div>
                        <p className="font-medium">{alert.title}</p>
                        <p className="text-xs text-gray-400">{alert.message}</p>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <Badge variant={severityColors[alert.severity]}>
                        {alert.severity.charAt(0).toUpperCase() + alert.severity.slice(1)}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <Badge variant={statusColors[alert.status]}>
                        {alert.status === 'pending' ? 'Pendente' : 'Reconhecido'}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-400">
                      {new Date(alert.created_at).toLocaleDateString('pt-BR')}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {alert.status === 'pending' && (
                        <button
                          onClick={() => handleAcknowledge(alert)}
                          className="p-1.5 text-gray-400 hover:text-green-400 transition"
                          title="Reconhecer alerta"
                        >
                          <Check size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-6 px-2">
            <p className="text-gray-400 text-sm">
              Página {page} de {totalPages}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="p-2 text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                <ChevronLeft size={20} />
              </button>
              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
                className="p-2 text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                <ChevronRight size={20} />
              </button>
            </div>
          </div>
        </>
      )}

      {/* Acknowledge Modal */}
      {selectedAlert && (
        <Modal
          isOpen={true}
          title="Reconhecer Alerta"
          onClose={() => setSelectedAlert(null)}
          onConfirm={confirmAcknowledge}
          confirmText="Reconhecer"
          cancelText="Cancelar"
          loading={acknowledgeMutation.isPending}
        >
          <div className="space-y-4">
            <p className="text-gray-300">Deseja reconhecer este alerta?</p>
            <div className="bg-gray-700 rounded-lg p-4">
              <p className="text-sm font-medium text-white mb-2">{selectedAlert.title}</p>
              <p className="text-sm text-gray-300">{selectedAlert.message}</p>
              {selectedAlert.details && (
                <p className="text-xs text-gray-400 mt-2">{selectedAlert.details}</p>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
