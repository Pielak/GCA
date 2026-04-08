import { useState } from 'react'
import { Card, Badge, Modal, SkeletonLoader } from '@/components/common'
import { useSuspiciousAccess, useUnblockAccess, type AccessAttempt } from '@/hooks/useSuspiciousAccess'
import { AlertCircle, Unlock } from 'lucide-react'

export const SecurityPage: React.FC = () => {
  const [blockedOnly, setBlockedOnly] = useState(true)
  const [selectedAttempt, setSelectedAttempt] = useState<AccessAttempt | null>(null)

  const { data: attempts, isLoading, error } = useSuspiciousAccess(blockedOnly)
  const unblockMutation = useUnblockAccess()

  const handleUnblock = (attempt: AccessAttempt) => {
    setSelectedAttempt(attempt)
  }

  const confirmUnblock = async () => {
    if (!selectedAttempt) return
    try {
      await unblockMutation.mutateAsync(selectedAttempt.id)
      setSelectedAttempt(null)
    } catch (error) {
      // Error already handled by toast
    }
  }

  const blockedCount = attempts?.filter(a => a.blocked).length || 0
  const totalCount = attempts?.length || 0

  if (error) {
    return (
      <div>
        <h1 className="text-3xl font-bold text-white mb-8">Segurança</h1>
        <div className="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">
          <p>Erro ao carregar dados de segurança. Tente novamente.</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-white mb-8">Segurança</h1>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Card>
          <div>
            <p className="text-gray-400 text-sm mb-1">Acessos Bloqueados</p>
            {isLoading ? (
              <SkeletonLoader height="h-8" width="w-20" />
            ) : (
              <p className="text-3xl font-bold text-red-400">{blockedCount}</p>
            )}
          </div>
        </Card>
        <Card>
          <div>
            <p className="text-gray-400 text-sm mb-1">Total de Tentativas</p>
            {isLoading ? (
              <SkeletonLoader height="h-8" width="w-20" />
            ) : (
              <p className="text-3xl font-bold text-white">{totalCount}</p>
            )}
          </div>
        </Card>
        <Card>
          <div>
            <p className="text-gray-400 text-sm mb-1">Taxa de Bloqueio</p>
            {isLoading ? (
              <SkeletonLoader height="h-8" width="w-20" />
            ) : (
              <p className="text-3xl font-bold text-blue-400">
                {totalCount > 0 ? ((blockedCount / totalCount) * 100).toFixed(1) : 0}%
              </p>
            )}
          </div>
        </Card>
      </div>

      {/* Filter */}
      <Card className="mb-6">
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={blockedOnly}
              onChange={(e) => setBlockedOnly(e.target.checked)}
              className="w-4 h-4 rounded bg-gray-700 border-gray-600"
            />
            <span className="text-gray-300 text-sm">Mostrar apenas bloqueados</span>
          </label>
        </div>
      </Card>

      {/* Attempts List */}
      {isLoading && !attempts ? (
        <Card>
          <SkeletonLoader count={3} height="h-12" />
        </Card>
      ) : !attempts || attempts.length === 0 ? (
        <Card>
          <div className="flex items-center justify-center py-8">
            <div className="text-center">
              <AlertCircle size={32} className="mx-auto mb-2 text-green-500" />
              <p className="text-gray-400">Nenhum acesso suspeito encontrado</p>
            </div>
          </div>
        </Card>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700 bg-gray-700">
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Email</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Tentativas</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Status</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Data</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Ação</th>
              </tr>
            </thead>
            <tbody>
              {attempts.map((attempt) => (
                <tr key={attempt.id} className="border-b border-gray-700 hover:bg-gray-700 transition">
                  <td className="px-6 py-4 text-sm text-gray-300">
                    {attempt.user_email || 'Usuário desconhecido'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-300">{attempt.attempt_number}</td>
                  <td className="px-6 py-4 text-sm">
                    <Badge variant={attempt.blocked ? 'error' : 'success'}>
                      {attempt.blocked ? 'Bloqueado' : 'Ativo'}
                    </Badge>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-400">
                    {new Date(attempt.created_at).toLocaleDateString('pt-BR')}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    {attempt.blocked && (
                      <button
                        onClick={() => handleUnblock(attempt)}
                        className="p-1.5 text-gray-400 hover:text-green-400 transition"
                        title="Desbloquear"
                      >
                        <Unlock size={16} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Unblock Confirmation Modal */}
      {selectedAttempt && (
        <Modal
          isOpen={true}
          title="Desbloquear Acesso"
          onClose={() => setSelectedAttempt(null)}
          onConfirm={confirmUnblock}
          confirmText="Desbloquear"
          cancelText="Cancelar"
          loading={unblockMutation.isPending}
        >
          <div className="space-y-4">
            <p className="text-gray-300">Deseja realmente desbloquear este acesso?</p>
            <div className="bg-gray-700 rounded-lg p-3">
              <p className="text-sm text-gray-400">
                Email: <span className="text-white">{selectedAttempt.user_email}</span>
              </p>
              <p className="text-sm text-gray-400">
                Tentativas: <span className="text-white">{selectedAttempt.attempt_number}</span>
              </p>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
