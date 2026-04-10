import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { UserPlus, Loader2, CheckCircle2, Clock, Lightbulb, Users } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useProjectPermissions } from '@/hooks/useProjectPermissions'

interface PendingInvite {
  invite_id: string
  email: string
  role: string
  status: string
  invited_at: string
  expires_at: string
}

interface TeamMember {
  id: string
  email: string
  full_name: string
  role: string
  joined_at: string
}

type InviteRole = 'tech_lead' | 'dev_senior' | 'dev_pleno' | 'qa' | 'compliance' | 'stakeholder'

const ROLE_OPTIONS: { value: InviteRole; label: string }[] = [
  { value: 'tech_lead', label: 'Tech Lead' },
  { value: 'dev_senior', label: 'Dev Senior' },
  { value: 'dev_pleno', label: 'Dev Pleno' },
  { value: 'qa', label: 'QA' },
  { value: 'compliance', label: 'Compliance / Segurança' },
  { value: 'stakeholder', label: 'Stakeholder / Gestão' },
]

const ROLE_COLORS: Record<string, string> = {
  gp: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  tech_lead: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  dev_senior: 'bg-slate-500/20 text-slate-200 border-slate-500/30',
  dev_pleno: 'bg-slate-600/20 text-slate-300 border-slate-600/30',
  qa: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  compliance: 'bg-violet-500/20 text-violet-300 border-violet-500/30',
  stakeholder: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
}

function getRoleLabel(role: string): string {
  return ROLE_OPTIONS.find(r => r.value === role)?.label || role
}

function formatDate(dateString: string): string {
  try {
    return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(dateString))
  } catch {
    return dateString
  }
}

const SELF_ROLE_OPTIONS = [
  { value: 'tech_lead', label: 'Tech Lead' },
  { value: 'dev_senior', label: 'Dev Senior' },
  { value: 'dev_pleno', label: 'Dev Pleno' },
  { value: 'qa', label: 'QA' },
  { value: 'compliance', label: 'Compliance' },
  { value: 'stakeholder', label: 'Stakeholder' },
]

export function ProjectTeamPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { can } = useProjectPermissions()
  const canManageTeam = can('project:manage_team')

  const [email, setEmail] = useState('')
  const [role, setRole] = useState<InviteRole>('dev_pleno')
  const [inviteLoading, setInviteLoading] = useState(false)
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null)

  const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([])
  const [members, setMembers] = useState<TeamMember[]>([])
  const [loadingData, setLoadingData] = useState(true)

  // Multi-papeis
  const [myRoles, setMyRoles] = useState<{role: string, is_base: boolean}[]>([])
  const [addingRole, setAddingRole] = useState(false)
  const [selectedNewRole, setSelectedNewRole] = useState('')

  const loadTeamData = useCallback(async () => {
    if (!projectId) return
    setLoadingData(true)
    try {
      const [invitesRes, membersRes] = await Promise.allSettled([
        apiClient.get(`/projects/${projectId}/pending-invites`),
        apiClient.get(`/projects/${projectId}/members`),
      ])
      if (invitesRes.status === 'fulfilled') {
        setPendingInvites(invitesRes.value.data.invites || invitesRes.value.data || [])
      }
      if (membersRes.status === 'fulfilled') {
        setMembers(membersRes.value.data.members || membersRes.value.data || [])
      }
    } catch {
      // Silently handle — data will show as empty
    } finally {
      setLoadingData(false)
    }
  }, [projectId])

  useEffect(() => {
    loadTeamData()
  }, [loadTeamData])

  // Carregar meus papeis
  useEffect(() => {
    if (!projectId) return
    apiClient.get(`/projects/${projectId}/members/self/roles`)
      .then(res => setMyRoles(res.data.roles || []))
      .catch(() => {})
  }, [projectId])

  const handleAddRole = async () => {
    if (!selectedNewRole || !projectId) return
    setAddingRole(true)
    try {
      await apiClient.post(`/projects/${projectId}/members/self/roles`, { roles: [selectedNewRole] })
      const res = await apiClient.get(`/projects/${projectId}/members/self/roles`)
      setMyRoles(res.data.roles || [])
      setSelectedNewRole('')
    } catch { /* silently handle */ }
    finally { setAddingRole(false) }
  }

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    setInviteError(null)
    setInviteSuccess(null)
    setInviteLoading(true)

    try {
      await apiClient.post(`/projects/${projectId}/invite`, { email, role })
      setInviteSuccess('Convite enviado com sucesso!')
      setEmail('')
      setRole('dev_pleno')
      await loadTeamData()
      setTimeout(() => setInviteSuccess(null), 3000)
    } catch (err: any) {
      setInviteError(err?.message || 'Erro ao enviar convite')
    } finally {
      setInviteLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <Users className="w-6 h-6 text-violet-400" />
          <h1 className="text-2xl font-bold text-white">Gerenciar Equipe</h1>
        </div>
        <p className="text-slate-400 text-sm ml-9">
          Convide membros da sua equipe para colaborar neste projeto.
        </p>
      </div>

      {/* Meus Papeis — auto-atribuicao para GP */}
      {canManageTeam && myRoles.length > 0 && (
      <div className="bg-dark-100 border border-slate-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Meus Papeis no Projeto</h2>
        <div className="flex flex-wrap gap-2 mb-4">
          {myRoles.map(r => (
            <span key={r.role} className={`px-3 py-1 rounded-full text-xs font-medium ${
              r.is_base ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-violet-500/20 text-violet-300 border border-violet-500/30'
            }`}>
              {SELF_ROLE_OPTIONS.find(o => o.value === r.role)?.label || getRoleLabel(r.role)}
              {r.is_base && ' (base)'}
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <select
            value={selectedNewRole}
            onChange={e => setSelectedNewRole(e.target.value)}
            className="bg-dark-200 border border-slate-700 rounded-lg px-4 py-2 text-sm text-slate-100 focus:outline-none focus:border-violet-600"
          >
            <option value="">Adicionar papel...</option>
            {SELF_ROLE_OPTIONS.filter(r => !myRoles.find(mr => mr.role === r.value)).map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
          <button
            onClick={handleAddRole}
            disabled={!selectedNewRole || addingRole}
            className="bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors"
          >
            Adicionar
          </button>
        </div>
      </div>
      )}

      {/* Invite Form — visivel apenas para quem pode gerenciar equipe */}
      {canManageTeam && (
      <div className="bg-dark-100 border border-slate-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
          <UserPlus className="w-5 h-5 text-violet-400" />
          Convidar Novo Membro
        </h2>

        {inviteError && (
          <div className="mb-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
            <p className="text-red-300 text-sm">{inviteError}</p>
          </div>
        )}

        {inviteSuccess && (
          <div className="mb-4 bg-emerald-900/40 border border-emerald-800/50 rounded-lg p-3 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <p className="text-emerald-300 text-sm">{inviteSuccess}</p>
          </div>
        )}

        <form onSubmit={handleInvite} className="grid grid-cols-1 md:grid-cols-[1fr_180px_auto] gap-3 items-end">
          <div>
            <label className="block text-sm text-slate-300 font-medium mb-1.5">Email do Membro</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-dark-200 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
              placeholder="dev@empresa.com"
              required
              disabled={inviteLoading}
            />
          </div>

          <div>
            <label className="block text-sm text-slate-300 font-medium mb-1.5">Papel</label>
            <select
              value={role}
              onChange={e => setRole(e.target.value as InviteRole)}
              className="w-full bg-dark-200 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
              disabled={inviteLoading}
            >
              {ROLE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <button
            type="submit"
            disabled={inviteLoading || !email}
            className="bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-5 py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
          >
            {inviteLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <UserPlus className="w-4 h-4" />
            )}
            Convidar
          </button>
        </form>
      </div>
      )}

      {/* Pending Invites — visivel para quem gerencia equipe */}
      {canManageTeam && (
      <div className="bg-dark-100 border border-slate-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
          <Clock className="w-5 h-5 text-amber-400" />
          Convites Pendentes ({pendingInvites.length})
        </h2>

        {loadingData ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
          </div>
        ) : pendingInvites.length === 0 ? (
          <div className="bg-emerald-900/20 border border-emerald-800/30 rounded-lg p-4 text-center">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 mx-auto mb-2" />
            <p className="text-emerald-300 text-sm">Nenhum convite pendente. Equipe completa!</p>
          </div>
        ) : (
          <div className="space-y-3">
            {pendingInvites.map(invite => (
              <div
                key={invite.invite_id}
                className="bg-dark-200 border border-slate-700/50 rounded-lg p-4 grid grid-cols-1 sm:grid-cols-[1fr_auto_auto_auto] gap-3 items-center"
              >
                <div>
                  <p className="text-white text-sm font-medium">{invite.email}</p>
                  <p className="text-slate-500 text-xs mt-0.5">Convidado em {formatDate(invite.invited_at)}</p>
                </div>
                <span className={`text-xs font-medium px-3 py-1 rounded-md border ${ROLE_COLORS[invite.role] || 'bg-slate-700 text-slate-300 border-slate-600'}`}>
                  {getRoleLabel(invite.role)}
                </span>
                <span className="text-slate-400 text-xs">
                  Expira: {formatDate(invite.expires_at)}
                </span>
                <span className="text-xs font-medium px-3 py-1 rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  Pendente
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      )}

      {/* Team Members — visivel para todos */}
      {members.length > 0 && (
        <div className="bg-dark-100 border border-slate-700 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
            <Users className="w-5 h-5 text-emerald-400" />
            Membros da Equipe ({members.length})
          </h2>
          <div className="space-y-3">
            {members.map(member => (
              <div
                key={member.id}
                className="bg-dark-200 border border-slate-700/50 rounded-lg p-4 flex items-center gap-4"
              >
                <div className="w-9 h-9 rounded-full bg-violet-600/20 border border-violet-600/30 flex items-center justify-center flex-shrink-0">
                  <span className="text-violet-300 text-sm font-bold">
                    {(member.full_name || member.email).charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">{member.full_name || member.email}</p>
                  <p className="text-slate-500 text-xs truncate">{member.email}</p>
                </div>
                <span className={`text-xs font-medium px-3 py-1 rounded-md border ${ROLE_COLORS[member.role] || 'bg-slate-700 text-slate-300 border-slate-600'}`}>
                  {getRoleLabel(member.role)}
                </span>
                <span className="text-slate-500 text-xs">
                  Desde {formatDate(member.joined_at)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tip */}
      <div className="bg-dark-100/50 border border-slate-800 rounded-lg p-4 flex items-start gap-3">
        <Lightbulb className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <p className="text-slate-400 text-xs">
          <span className="text-slate-300 font-medium">Dica:</span> Os convites expiram em 7 dias.
          Os membros receberão um email com um link para aceitar o convite e configurar sua senha.
        </p>
      </div>
    </div>
  )
}

export default ProjectTeamPage
