import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Card, Badge, Modal, SkeletonLoader } from '@/components/common'
import { useTickets, useTicketDetail, useRespondToTicket, type SupportTicket } from '@/hooks/useTickets'
import { respondToTicketSchema, type RespondToTicketInput } from '@/schemas/forms'
import { ChevronLeft, ChevronRight, Eye } from 'lucide-react'

export const TicketsPage: React.FC = () => {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string>('')
  const [severity, setSeverity] = useState<string>('')
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null)

  const { register, handleSubmit, reset, formState: { errors }, watch } = useForm<RespondToTicketInput>({
    resolver: zodResolver(respondToTicketSchema),
    defaultValues: {
      message: '',
      isResolution: false,
    },
  })

  const { data, isLoading, error } = useTickets(page, status || undefined, severity || undefined)
  const { data: ticketDetail, isLoading: detailLoading } = useTicketDetail(selectedTicketId)
  const respondMutation = useRespondToTicket()

  const handleRespond = async (formData: RespondToTicketInput) => {
    if (!selectedTicketId) return

    try {
      await respondMutation.mutateAsync({
        ticketId: selectedTicketId,
        message: formData.message,
        isResolution: formData.isResolution,
      })
      reset()
      closeDetail()
    } catch (error) {
      // Error already handled by toast
    }
  }

  const closeDetail = () => {
    setSelectedTicketId(null)
    reset()
  }

  const severityColors = {
    BAIXO: 'info',
    MÉDIO: 'warning',
    ALTO: 'warning',
    CRÍTICO: 'error',
  } as const

  const statusColors = {
    ABERTO: 'warning',
    RESOLVIDO: 'success',
    FECHADO: 'info',
  } as const

  if (error) {
    return (
      <div>
        <h1 className="text-3xl font-bold text-white mb-8">Tickets de Suporte</h1>
        <div className="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">
          <p>Erro ao carregar tickets. Tente novamente.</p>
        </div>
      </div>
    )
  }

  const tickets = data?.tickets || []
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1

  return (
    <div>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-white">Tickets de Suporte</h1>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
              <option value="ABERTO">Aberto</option>
              <option value="RESOLVIDO">Resolvido</option>
              <option value="FECHADO">Fechado</option>
            </select>
          </div>
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
              <option value="BAIXO">Baixo</option>
              <option value="MÉDIO">Médio</option>
              <option value="ALTO">Alto</option>
              <option value="CRÍTICO">Crítico</option>
            </select>
          </div>
          <div className="flex items-end">
            <p className="text-gray-400 text-sm">
              Total: {data?.total || 0} ticket(s)
            </p>
          </div>
        </div>
      </Card>

      {/* Table */}
      {isLoading && !data ? (
        <Card>
          <SkeletonLoader count={5} height="h-12" />
        </Card>
      ) : tickets.length === 0 ? (
        <Card>
          <p className="text-gray-400 text-center py-8">Nenhum ticket encontrado</p>
        </Card>
      ) : (
        <>
          <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700 bg-gray-700">
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Título</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Email</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Severidade</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Status</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Data</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Ação</th>
                </tr>
              </thead>
              <tbody>
                {tickets.map((ticket) => (
                  <tr key={ticket.id} className="border-b border-gray-700 hover:bg-gray-700 transition">
                    <td className="px-6 py-4 text-sm text-gray-300 max-w-xs truncate">{ticket.title}</td>
                    <td className="px-6 py-4 text-sm text-gray-300">{ticket.user_email || 'Desconhecido'}</td>
                    <td className="px-6 py-4 text-sm">
                      <Badge variant={severityColors[ticket.severity] as any}>
                        {ticket.severity}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <Badge variant={statusColors[ticket.status] as any}>
                        {ticket.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-400">
                      {new Date(ticket.created_at).toLocaleDateString('pt-BR')}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <button
                        onClick={() => setSelectedTicketId(ticket.id)}
                        className="p-1.5 text-gray-400 hover:text-blue-400 transition"
                        title="Visualizar detalhes"
                      >
                        <Eye size={16} />
                      </button>
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

      {/* Detail Modal */}
      {selectedTicketId && (
        <Modal
          isOpen={true}
          title="Detalhes do Ticket"
          onClose={closeDetail}
          size="lg"
        >
          {detailLoading ? (
            <SkeletonLoader count={3} />
          ) : ticketDetail ? (
            <div className="space-y-4">
              {/* Ticket Info */}
              <div className="bg-gray-700 rounded-lg p-4 space-y-2">
                <p className="text-sm text-gray-400">
                  <span className="font-medium">Título:</span> {ticketDetail.title}
                </p>
                <p className="text-sm text-gray-400">
                  <span className="font-medium">Email:</span> {ticketDetail.user_email}
                </p>
                <p className="text-sm text-gray-400">
                  <span className="font-medium">Descrição:</span> {ticketDetail.description}
                </p>
                {ticketDetail.error_message && (
                  <p className="text-sm text-gray-400">
                    <span className="font-medium">Erro:</span> {ticketDetail.error_message}
                  </p>
                )}
              </div>

              {/* Previous Responses */}
              {ticketDetail.responses && ticketDetail.responses.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-gray-300">Respostas anteriores</h4>
                  <div className="bg-gray-700 rounded-lg p-3 max-h-32 overflow-y-auto space-y-2">
                    {ticketDetail.responses.map((response) => (
                      <div key={response.id} className="text-sm text-gray-300 pb-2 border-b border-gray-600 last:border-0">
                        <p className="font-medium text-blue-300">{response.responder_email}</p>
                        <p>{response.message}</p>
                        <p className="text-xs text-gray-400 mt-1">
                          {new Date(response.created_at).toLocaleDateString('pt-BR')}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* New Response Form */}
              {ticketDetail.status !== 'FECHADO' && (
                <form onSubmit={handleSubmit(handleRespond)} className="space-y-3 border-t border-gray-700 pt-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">Sua resposta</label>
                    <textarea
                      {...register('message')}
                      placeholder="Digite sua resposta (mínimo 10 caracteres)..."
                      className={`w-full px-3 py-2 bg-gray-700 border rounded-lg text-white placeholder-gray-500 focus:outline-none transition ${
                        errors.message ? 'border-red-500' : 'border-gray-600 focus:border-blue-500'
                      }`}
                      rows={3}
                    />
                    {errors.message && (
                      <p className="text-red-400 text-xs mt-1">{errors.message.message}</p>
                    )}
                  </div>

                  <label className="flex items-center gap-2 text-sm text-gray-300">
                    <input
                      type="checkbox"
                      {...register('isResolution')}
                      className="w-4 h-4 rounded bg-gray-700 border-gray-600 cursor-pointer"
                    />
                    <span>Marcar como resolvido</span>
                  </label>

                  <button
                    type="submit"
                    disabled={respondMutation.isPending}
                    className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                  >
                    {respondMutation.isPending ? 'Enviando...' : 'Enviar Resposta'}
                  </button>
                </form>
              )}
            </div>
          ) : null}
        </Modal>
      )}
    </div>
  )
}
