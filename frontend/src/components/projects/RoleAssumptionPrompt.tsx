import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { ShieldPlus, Loader2 } from 'lucide-react'
import { apiClient } from '@/lib/api'

// Mapeia ação → papel canônico necessário (GCA_CANONICAL_CONTRACT.md §4).
// Alinha com ROLE_ACTIONS em backend/app/core/permissions.py.
const ACTION_ROLES: Record<string, { role: string; label: string }> = {
  'code:write': { role: 'dev', label: 'Dev' },
  'code:review': { role: 'dev', label: 'Dev' },
  'git:commit': { role: 'dev', label: 'Dev' },
  'pipeline:execute': { role: 'dev', label: 'Dev' },
  'security:review': { role: 'qa', label: 'QA' },
  'compliance:validate': { role: 'qa', label: 'QA' },
  'qa:approve': { role: 'qa', label: 'QA' },
  'backlog:manage': { role: 'gp', label: 'GP' },
  'project:manage_team': { role: 'gp', label: 'GP' },
  'project:edit': { role: 'gp', label: 'GP' },
  'audit:export': { role: 'gp', label: 'GP' },
}

interface Props {
  action: string
  onRoleAssumed: () => void
  onCancel: () => void
}

export function RoleAssumptionPrompt({ action, onRoleAssumed, onCancel }: Props) {
  const { id: projectId } = useParams<{ id: string }>()
  const [assuming, setAssuming] = useState(false)

  const roleInfo = ACTION_ROLES[action]
  if (!roleInfo) return null

  const handleAssume = async () => {
    if (!projectId) return
    setAssuming(true)
    try {
      await apiClient.post(`/projects/${projectId}/members/self/roles`, { roles: [roleInfo.role] })
      onRoleAssumed()
    } catch {
      // silently handle
    } finally {
      setAssuming(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-xl border border-violet-600/30 bg-dark-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <ShieldPlus className="h-6 w-6 text-violet-400" />
          <h3 className="text-lg font-semibold text-white">Papel necessario</h3>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          Esta ação requer o papel de <strong className="text-violet-300">{roleInfo.label}</strong>.
          Deseja assumir este papel e continuar?
        </p>
        <p className="text-xs text-slate-500 mb-6">
          Esta ação será registrada na trilha de auditoria do projeto.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={handleAssume}
            disabled={assuming}
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-500 disabled:opacity-50 transition-colors"
          >
            {assuming ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldPlus className="h-4 w-4" />}
            Assumir {roleInfo.label}
          </button>
        </div>
      </div>
    </div>
  )
}
