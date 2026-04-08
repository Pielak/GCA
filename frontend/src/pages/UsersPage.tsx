import { useState } from 'react'
import { Button, Table, Badge, Modal, SkeletonLoader, Card } from '@/components/common'
import { useUsers, useLockUser, useUnlockUser, useResetPassword, type User } from '@/hooks/useUsers'
import { ChevronLeft, ChevronRight, Lock, Unlock, RotateCcw } from 'lucide-react'

export const UsersPage: React.FC = () => {
  const [page, setPage] = useState(1)
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  const [action, setAction] = useState<'lock' | 'unlock' | 'reset' | null>(null)

  const { data, isLoading, error } = useUsers(page, filter)
  const lockMutation = useLockUser()
  const unlockMutation = useUnlockUser()
  const resetMutation = useResetPassword()

  const handleAction = async (user: User, actionType: 'lock' | 'unlock' | 'reset') => {
    setSelectedUser(user)
    setAction(actionType)
  }

  const confirmAction = async () => {
    if (!selectedUser || !action) return

    try {
      if (action === 'lock') {
        await lockMutation.mutateAsync(selectedUser.id)
      } else if (action === 'unlock') {
        await unlockMutation.mutateAsync(selectedUser.id)
      } else if (action === 'reset') {
        await resetMutation.mutateAsync(selectedUser.id)
      }
      closeModal()
    } catch (error) {
      // Error already handled by toast in hook
    }
  }

  const closeModal = () => {
    setSelectedUser(null)
    setAction(null)
  }

  const actionLabels = {
    lock: { title: 'Bloquear Usuário', message: 'Deseja realmente bloquear este usuário?' },
    unlock: { title: 'Desbloquear Usuário', message: 'Deseja realmente desbloquear este usuário?' },
    reset: { title: 'Resetar Senha', message: 'Deseja enviar um email de reset de senha para este usuário?' },
  }

  const isLoading_ = isLoading || lockMutation.isPending || unlockMutation.isPending || resetMutation.isPending

  if (error) {
    return (
      <div>
        <h1 className="text-3xl font-bold text-white mb-8">Usuários</h1>
        <div className="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">
          <p>Erro ao carregar usuários. Tente novamente.</p>
        </div>
      </div>
    )
  }

  const users = data?.users || []
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1

  return (
    <div>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-white">Usuários</h1>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-300 text-sm font-medium mb-2">Filtro de Status</label>
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value as 'all' | 'active' | 'inactive')
                setPage(1)
              }}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
            >
              <option value="all">Todos</option>
              <option value="active">Ativos</option>
              <option value="inactive">Inativos</option>
            </select>
          </div>
          <div className="flex items-end">
            <p className="text-gray-400 text-sm">
              Total: {data?.total || 0} usuário(s)
            </p>
          </div>
        </div>
      </Card>

      {/* Table */}
      {isLoading && !data ? (
        <Card>
          <SkeletonLoader count={5} height="h-12" />
        </Card>
      ) : users.length === 0 ? (
        <Card>
          <p className="text-gray-400 text-center py-8">Nenhum usuário encontrado</p>
        </Card>
      ) : (
        <>
          <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700 bg-gray-700">
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Email</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Nome</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Admin</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Status</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Ações</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-b border-gray-700 hover:bg-gray-700 transition">
                    <td className="px-6 py-4 text-sm text-gray-300">{user.email}</td>
                    <td className="px-6 py-4 text-sm text-gray-300">{user.full_name}</td>
                    <td className="px-6 py-4 text-sm">
                      <Badge variant={user.is_admin ? 'success' : 'info'}>
                        {user.is_admin ? 'Sim' : 'Não'}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <Badge variant={user.is_active ? 'active' : 'inactive'}>
                        {user.is_active ? 'Ativo' : 'Inativo'}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <div className="flex gap-2">
                        {user.is_active ? (
                          <button
                            onClick={() => handleAction(user, 'lock')}
                            className="p-1.5 text-gray-400 hover:text-red-400 transition"
                            title="Bloquear usuário"
                          >
                            <Lock size={16} />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleAction(user, 'unlock')}
                            className="p-1.5 text-gray-400 hover:text-green-400 transition"
                            title="Desbloquear usuário"
                          >
                            <Unlock size={16} />
                          </button>
                        )}
                        <button
                          onClick={() => handleAction(user, 'reset')}
                          className="p-1.5 text-gray-400 hover:text-blue-400 transition"
                          title="Resetar senha"
                        >
                          <RotateCcw size={16} />
                        </button>
                      </div>
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

      {/* Confirmation Modal */}
      {selectedUser && action && (
        <Modal
          isOpen={true}
          title={actionLabels[action].title}
          onClose={closeModal}
          onConfirm={confirmAction}
          confirmText="Confirmar"
          cancelText="Cancelar"
          loading={lockMutation.isPending || unlockMutation.isPending || resetMutation.isPending}
        >
          <div className="space-y-4">
            <p className="text-gray-300">{actionLabels[action].message}</p>
            <div className="bg-gray-700 rounded-lg p-3">
              <p className="text-sm text-gray-400">Email: <span className="text-white">{selectedUser.email}</span></p>
              <p className="text-sm text-gray-400">Nome: <span className="text-white">{selectedUser.full_name}</span></p>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
