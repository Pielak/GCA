import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, CheckCircle, XCircle, Loader2, Trash2, Mail, Pencil, Clock, Eye, Users, ExternalLink, Package, UserCog, FileText, MessageSquareWarning } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { OperationBar, PageTransition, SkeletonPulse } from '@/components/ui/PipelineProgress'
import { getQuestionsForType } from '@/data/projectRequestQuestions'

interface PendingProject {
  id: string
  project_name: string
  project_slug: string
  description: string
  deliverable_type: string
  custom_deliverable_type?: string
  requirements?: Record<string, string>
  status: string
  gp_name: string
  gp_email: string
  requested_at: string
  rejection_reason: string
}

const DELIVERABLE_LABELS: Record<string, { label: string; color: string }> = {
  new_system:     { label: 'Sistema Novo',       color: 'bg-blue-500/20 text-blue-300' },
  mobile_app:     { label: 'Mobile',             color: 'bg-purple-500/20 text-purple-300' },
  module:         { label: 'Módulo Funcional',   color: 'bg-cyan-500/20 text-cyan-300' },
  enhancement:    { label: 'Melhoria',           color: 'bg-emerald-500/20 text-emerald-300' },
  integration:    { label: 'Integração',         color: 'bg-orange-500/20 text-orange-300' },
  modernization:  { label: 'Modernização',       color: 'bg-yellow-500/20 text-yellow-300' },
  etl:            { label: 'ETL / Dados',        color: 'bg-indigo-500/20 text-indigo-300' },
  maintenance:    { label: 'Sustentação',        color: 'bg-slate-500/20 text-slate-300' },
  other:          { label: 'Outro',               color: 'bg-amber-500/20 text-amber-300' },
}

const STATUS_LABELS: Record<string, { label: string; bg: string; text: string }> = {
  pending:       { label: 'Pendente',       bg: 'bg-amber-500/20',   text: 'text-amber-300' },
  approved:      { label: 'Aprovado',       bg: 'bg-emerald-500/20', text: 'text-emerald-300' },
  rejected:      { label: 'Rejeitado',      bg: 'bg-red-500/20',     text: 'text-red-300' },
  active:        { label: 'Ativo',          bg: 'bg-emerald-500/20', text: 'text-emerald-300' },
  provisioning:  { label: 'Provisionando',  bg: 'bg-blue-500/20',    text: 'text-blue-300' },
  draft:         { label: 'Rascunho',       bg: 'bg-slate-600/30',   text: 'text-slate-400' },
}

export function AdminProjectsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [projects, setProjects] = useState<PendingProject[]>([])
  const [realProjects, setRealProjects] = useState<{id: string, slug: string}[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [operationMsg, setOperationMsg] = useState<{ message: string; detail: string; status: 'running' | 'success' | 'error' } | null>(null)

  // Modal de mensagem ao GP
  const [messageModal, setMessageModal] = useState<PendingProject | null>(null)
  const [messageText, setMessageText] = useState('')
  const [sendingMessage, setSendingMessage] = useState(false)

  // Modal de detalhes da solicitação (admin verifica antes de aprovar/rejeitar)
  const [detailsModal, setDetailsModal] = useState<PendingProject | null>(null)

  // Modal de rejeição com razão (notifica solicitante por email)
  const [rejectModal, setRejectModal] = useState<PendingProject | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [rejecting, setRejecting] = useState(false)

  // GP Substitution modal
  const [gpModal, setGpModal] = useState<{ project: PendingProject; realProjectId: string } | null>(null)
  const [availableGPs, setAvailableGPs] = useState<{ id: string; full_name: string; email: string }[]>([])
  const [currentGPs, setCurrentGPs] = useState<{ user_id: string; full_name: string; email: string }[]>([])
  const [selectedNewGP, setSelectedNewGP] = useState('')
  const [gpSubLoading, setGpSubLoading] = useState(false)
  const [gpSubStep, setGpSubStep] = useState<'select' | 'confirm_remove'>('select')
  const [gpToRemove, setGpToRemove] = useState<string>('')

  // Toast
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const openGpSubstitution = async (proj: PendingProject, realProjectId: string) => {
    setGpModal({ project: proj, realProjectId })
    setSelectedNewGP('')
    setGpSubStep('select')
    setGpToRemove('')
    try {
      const [usersRes, membersRes] = await Promise.all([
        apiClient.get('/admin/users'),
        apiClient.get(`/projects/${realProjectId}/members`).catch(() => ({ data: { members: [] } })),
      ])
      const allUsers = usersRes.data?.users || []
      const members = membersRes.data?.members || []
      const currentGPList = members.filter((m: any) => m.role === 'gp')
      setCurrentGPs(currentGPList.map((m: any) => ({ user_id: m.user_id, full_name: m.full_name || '', email: m.email || '' })))
      // Available GPs: all users that are NOT already GP on this project
      const currentGPIds = new Set(currentGPList.map((m: any) => m.user_id))
      setAvailableGPs(allUsers.filter((u: any) => !u.is_admin && !currentGPIds.has(u.id)).map((u: any) => ({
        id: u.id,
        full_name: u.full_name || '',
        email: u.email,
      })))
    } catch {
      setAvailableGPs([])
      setCurrentGPs([])
    }
  }

  const handleAddNewGP = async () => {
    if (!gpModal || !selectedNewGP) return
    setGpSubLoading(true)
    try {
      await apiClient.post(`/projects/${gpModal.realProjectId}/members`, {
        user_id: selectedNewGP,
        role: 'gp',
      })
      showToast('Novo GP adicionado ao projeto', 'success')
      // Refresh current GPs
      const membersRes = await apiClient.get(`/projects/${gpModal.realProjectId}/members`)
      const members = membersRes.data?.members || []
      const currentGPList = members.filter((m: any) => m.role === 'gp')
      setCurrentGPs(currentGPList.map((m: any) => ({ user_id: m.user_id, full_name: m.full_name || '', email: m.email || '' })))
      if (currentGPList.length > 1) {
        setGpSubStep('confirm_remove')
      } else {
        setGpModal(null)
      }
    } catch (err: any) {
      showToast(err?.message || 'Erro ao adicionar novo GP', 'error')
    } finally {
      setGpSubLoading(false)
    }
  }

  const handleRemoveOldGP = async () => {
    if (!gpModal || !gpToRemove) return
    if (currentGPs.length <= 1) {
      showToast('Não é possível remover o único GP do projeto', 'error')
      return
    }
    setGpSubLoading(true)
    try {
      await apiClient.delete(`/projects/${gpModal.realProjectId}/members/${gpToRemove}`)
      showToast('GP anterior removido do projeto', 'success')
      setGpModal(null)
      await loadData()
    } catch (err: any) {
      showToast(err?.message || 'Erro ao remover GP', 'error')
    } finally {
      setGpSubLoading(false)
    }
  }

  const loadData = useCallback(async () => {
    try {
      const [pendingRes, projectsRes] = await Promise.all([
        apiClient.get('/admin/projects/pending'),
        apiClient.get('/projects'),
      ])
      setProjects(pendingRes.data.pending_projects || [])
      setRealProjects((projectsRes.data.projects || []).map((p: any) => ({ id: p.id, slug: p.slug })))
    } catch {
      setProjects([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleApprove = async (p: PendingProject) => {
    setActionLoading(p.id)
    setOperationMsg({ message: 'Aprovando projeto', detail: `${p.project_name} — provisionando tenant e configurando agentes`, status: 'running' })
    try {
      await apiClient.post(`/admin/projects/${p.id}/approve`)
      setOperationMsg({ message: 'Projeto aprovado', detail: `${p.project_name} — tenant provisionado com sucesso`, status: 'success' })
      await loadData()
    } catch (err: any) {
      setOperationMsg({ message: 'Erro na aprovação', detail: err?.message || 'Falha ao provisionar tenant', status: 'error' })
      showToast(err?.message || 'Erro ao aprovar projeto', 'error')
    } finally {
      setActionLoading(null)
      setTimeout(() => setOperationMsg(null), 4000)
    }
  }

  const handleDelete = async (p: PendingProject) => {
    if (!confirm(`Tem certeza que deseja excluir a solicitação "${p.project_name}"?`)) return
    setActionLoading(p.id)
    try {
      await apiClient.delete(`/admin/projects/${p.id}`)
      showToast(`Solicitação "${p.project_name}" excluída`, 'success')
      await loadData()
    } catch (err: any) {
      showToast(err?.message || 'Erro ao excluir', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  const handleReject = async () => {
    if (!rejectModal || rejectReason.trim().length < 10) return
    setRejecting(true)
    try {
      await apiClient.post(`/admin/projects/${rejectModal.id}/reject`, {
        reason: rejectReason.trim(),
      })
      showToast(`Solicitação "${rejectModal.project_name}" rejeitada — solicitante notificado`, 'success')
      setRejectModal(null)
      setRejectReason('')
      await loadData()
    } catch (err: any) {
      showToast(err?.message || 'Erro ao rejeitar solicitação', 'error')
    } finally {
      setRejecting(false)
    }
  }

  const handleSendMessage = async () => {
    if (!messageModal || !messageText.trim()) return
    setSendingMessage(true)
    try {
      const res = await apiClient.post(`/admin/projects/${messageModal.id}/message`, {
        message: messageText.trim(),
        project_name: messageModal.project_name,
      })
      showToast(res.data.message || 'Mensagem enviada', 'success')
      setMessageModal(null)
      setMessageText('')
    } catch (err: any) {
      showToast(err?.message || 'Erro ao enviar mensagem', 'error')
    } finally {
      setSendingMessage(false)
    }
  }

  const filtered = projects.filter(p => {
    const matchSearch = p.project_name.toLowerCase().includes(search.toLowerCase()) ||
                        p.gp_name.toLowerCase().includes(search.toLowerCase())
    const matchStatus = statusFilter === 'all' || p.status === statusFilter
    return matchSearch && matchStatus
  })

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <SkeletonPulse className="h-8 w-64" />
        <SkeletonPulse className="h-10 w-full" />
        <div className="space-y-3">
          <SkeletonPulse className="h-16 w-full rounded-xl" />
          <SkeletonPulse className="h-16 w-full rounded-xl" />
          <SkeletonPulse className="h-16 w-full rounded-xl" />
        </div>
      </div>
    )
  }

  return (
    <PageTransition>
    <div className="p-6 space-y-6">
      {toast && (
        <div className={`p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
          {toast.message}
        </div>
      )}

      {operationMsg && (
        <OperationBar
          message={operationMsg.message}
          detail={operationMsg.detail}
          status={operationMsg.status}
          onComplete={() => setOperationMsg(null)}
        />
      )}

      <div>
        <h1 className="text-xl font-semibold text-slate-100">Gestão de Projetos</h1>
        <p className="text-slate-500 text-sm mt-0.5">Gerencie solicitações, aprove projetos e comunique-se com os Gerentes de Projeto.</p>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por projeto ou GP..."
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-violet-600"
        >
          <option value="all">Todos os status</option>
          <option value="pending">Pendente</option>
          <option value="approved">Aprovado</option>
          <option value="rejected">Rejeitado</option>
        </select>
      </div>

      {/* Tabela de Projetos */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">PROJETO</th>
                <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">TIPO</th>
                <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">STATUS</th>
                <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">GERENTE DE PROJETO</th>
                <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">PENDÊNCIAS</th>
                <th className="text-right px-4 py-3 text-xs text-slate-500 font-medium">AÇÕES</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length > 0 ? filtered.map((proj, i) => {
                const st = STATUS_LABELS[proj.status] || STATUS_LABELS.pending
                const isPending = proj.status === 'pending'
                return (
                  <tr key={proj.id} className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${i === filtered.length - 1 ? 'border-b-0' : ''}`}>
                    <td className="px-4 py-3">
                      <p className="text-slate-200 text-sm font-medium">{proj.project_name}</p>
                      <p className="text-slate-500 text-xs">{proj.project_slug}</p>
                    </td>
                    <td className="px-4 py-3">
                      {(() => {
                        const dt = DELIVERABLE_LABELS[proj.deliverable_type]
                        return dt ? (
                          <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${dt.color}`}>
                            <Package className="w-3 h-3" />
                            {dt.label}
                          </span>
                        ) : (
                          <span className="text-slate-600 text-xs">—</span>
                        )
                      })()}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${st.bg} ${st.text}`}>{st.label}</span>
                    </td>
                    <td className="px-4 py-3">
                      <a
                        href={`mailto:${proj.gp_email}`}
                        className="text-violet-400 hover:text-violet-300 text-sm transition-colors flex items-center gap-1.5"
                        title={proj.gp_email}
                      >
                        <Mail className="w-3.5 h-3.5" />
                        {proj.gp_name || proj.gp_email}
                      </a>
                    </td>
                    <td className="px-4 py-3">
                      {isPending ? (
                        <span className="flex items-center gap-1.5 text-amber-400 text-xs">
                          <Clock className="w-3.5 h-3.5" />
                          Aguardando aprovação
                        </span>
                      ) : proj.status === 'approved' ? (
                        <span className="flex items-center gap-1.5 text-emerald-400 text-xs">
                          <CheckCircle className="w-3.5 h-3.5" />
                          Provisionado — GP pode operar
                        </span>
                      ) : proj.rejection_reason ? (
                        <span className="text-red-400 text-xs" title={proj.rejection_reason}>
                          {proj.rejection_reason.length > 40 ? proj.rejection_reason.slice(0, 40) + '...' : proj.rejection_reason}
                        </span>
                      ) : (
                        <span className="text-slate-600 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {/* Botão de detalhes — sempre visível para qualquer status */}
                        <button
                          onClick={() => setDetailsModal(proj)}
                          className="p-1.5 rounded-lg text-slate-500 hover:text-violet-400 hover:bg-violet-900/20 transition-colors"
                          title="Ver detalhes da solicitação (descrição, tipo, perguntas/respostas)"
                        >
                          <FileText className="w-4 h-4" />
                        </button>

                        {proj.status === 'approved' && (() => {
                          const realProj = realProjects.find(rp => rp.slug === proj.project_slug)
                          return realProj ? (
                            <>
                              <button
                                onClick={() => navigate(`/admin/projects/${realProj.id}`)}
                                className="p-1.5 rounded-lg text-slate-500 hover:text-violet-400 hover:bg-violet-900/20 transition-colors"
                                title="Ver projeto (visão admin)"
                              >
                                <Eye className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => openGpSubstitution(proj, realProj.id)}
                                className="p-1.5 rounded-lg text-slate-500 hover:text-amber-400 hover:bg-amber-900/20 transition-colors"
                                title="Substituir GP"
                              >
                                <UserCog className="w-4 h-4" />
                              </button>
                            </>
                          ) : null
                        })()}
                        <button
                          onClick={() => { setMessageModal(proj); setMessageText('') }}
                          className="p-1.5 rounded-lg text-slate-500 hover:text-amber-400 hover:bg-amber-900/20 transition-colors"
                          title="Enviar mensagem ao solicitante"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        {isPending && (
                          <>
                            <button
                              onClick={() => handleApprove(proj)}
                              disabled={actionLoading === proj.id}
                              className="p-1.5 rounded-lg text-slate-500 hover:text-emerald-400 hover:bg-emerald-900/20 disabled:opacity-30 transition-colors"
                              title="Aprovar projeto"
                            >
                              {actionLoading === proj.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                            </button>
                            <button
                              onClick={() => { setRejectModal(proj); setRejectReason('') }}
                              disabled={actionLoading === proj.id}
                              className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-900/20 disabled:opacity-30 transition-colors"
                              title="Rejeitar solicitação (notifica solicitante por email)"
                            >
                              <MessageSquareWarning className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(proj)}
                              disabled={actionLoading === proj.id}
                              className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-900/20 disabled:opacity-30 transition-colors"
                              title="Excluir solicitação (sem notificar)"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              }) : (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500 text-sm">
                    Nenhum projeto encontrado
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal de substituição de GP */}
      {gpModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-semibold text-sm flex items-center gap-2">
                <UserCog className="w-4 h-4 text-amber-400" />
                Substituir GP — {gpModal.project.project_name}
              </h3>
              <button onClick={() => setGpModal(null)} className="text-slate-500 hover:text-slate-300">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {/* Current GPs */}
            <div className="mb-4">
              <p className="text-slate-400 text-xs mb-2">GP(s) atual(is):</p>
              <div className="space-y-1.5">
                {currentGPs.map(gp => (
                  <div key={gp.user_id} className="flex items-center gap-2 p-2 bg-slate-800 rounded-lg">
                    <div className="w-6 h-6 rounded bg-emerald-900/40 border border-emerald-800/30 flex items-center justify-center text-emerald-300 text-xs font-bold">
                      {(gp.full_name || gp.email).charAt(0).toUpperCase()}
                    </div>
                    <span className="text-slate-200 text-xs">{gp.full_name || gp.email}</span>
                    <span className="text-slate-500 text-[10px]">({gp.email})</span>
                  </div>
                ))}
                {currentGPs.length === 0 && <p className="text-slate-600 text-xs">Nenhum GP encontrado</p>}
              </div>
            </div>

            {gpSubStep === 'select' && (
              <div className="space-y-3">
                <div>
                  <label className="text-slate-400 text-xs mb-1 block">Selecione o novo GP</label>
                  <select
                    value={selectedNewGP}
                    onChange={e => setSelectedNewGP(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-violet-600"
                  >
                    <option value="">— Selecione um usuário —</option>
                    {availableGPs.map(u => (
                      <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.email})</option>
                    ))}
                  </select>
                </div>
                <div className="flex justify-end gap-2">
                  <button onClick={() => setGpModal(null)} className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
                    Cancelar
                  </button>
                  <button
                    onClick={handleAddNewGP}
                    disabled={!selectedNewGP || gpSubLoading}
                    className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
                  >
                    {gpSubLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Users className="w-4 h-4" />}
                    Adicionar novo GP
                  </button>
                </div>
              </div>
            )}

            {gpSubStep === 'confirm_remove' && (
              <div className="space-y-3">
                <div className="p-3 bg-amber-900/20 border border-amber-800/30 rounded-lg">
                  <p className="text-amber-300 text-xs">
                    Novo GP adicionado com sucesso. Deseja remover o GP anterior?
                    {currentGPs.length <= 1 && ' (Não é possível remover o único GP.)'}
                  </p>
                </div>
                {currentGPs.length > 1 && (
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">Selecione o GP a remover</label>
                    <select
                      value={gpToRemove}
                      onChange={e => setGpToRemove(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-violet-600"
                    >
                      <option value="">— Selecione —</option>
                      {currentGPs.map(gp => (
                        <option key={gp.user_id} value={gp.user_id}>{gp.full_name || gp.email}</option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <button onClick={() => setGpModal(null)} className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
                    Manter ambos
                  </button>
                  {currentGPs.length > 1 && (
                    <button
                      onClick={handleRemoveOldGP}
                      disabled={!gpToRemove || gpSubLoading}
                      className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
                    >
                      {gpSubLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                      Remover GP selecionado
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal de mensagem ao GP */}
      {messageModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-semibold text-sm">Mensagem para o Gerente de Projeto</h3>
              <button onClick={() => setMessageModal(null)} className="text-slate-500 hover:text-slate-300">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 mb-4">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-slate-400">Projeto:</span>
                <span className="text-slate-200 font-medium">{messageModal.project_name}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-slate-400">Destinatário:</span>
                <a href={`mailto:${messageModal.gp_email}`} className="text-violet-400 hover:text-violet-300">
                  {messageModal.gp_name} ({messageModal.gp_email})
                </a>
              </div>
              <div className="text-xs text-slate-500">
                Assunto: <span className="text-slate-400">Edição de Projeto - {messageModal.project_name}</span>
              </div>
            </div>

            <textarea
              value={messageText}
              onChange={e => setMessageText(e.target.value.slice(0, 1000))}
              rows={6}
              placeholder="Descreva as informações ou ajustes necessários para o projeto..."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors resize-none"
            />
            <div className="flex items-center justify-between mt-2">
              <span className="text-xs text-slate-500">{messageText.length}/1000 caracteres</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setMessageModal(null)}
                  className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSendMessage}
                  disabled={!messageText.trim() || sendingMessage}
                  className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
                >
                  {sendingMessage ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
                  Enviar Mensagem
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal de detalhes da solicitação ─────────────────────────────── */}
      {detailsModal && (() => {
        const dt = DELIVERABLE_LABELS[detailsModal.deliverable_type]
        const typeLabel = detailsModal.custom_deliverable_type
          ? `Outro: ${detailsModal.custom_deliverable_type}`
          : (dt?.label || detailsModal.deliverable_type)
        const reqType = detailsModal.custom_deliverable_type ? 'other' : detailsModal.deliverable_type
        const allQuestions = getQuestionsForType(reqType)
        const reqs = detailsModal.requirements || {}
        const answeredIds = new Set(allQuestions.map(q => q.id))
        const extraKeys = Object.keys(reqs).filter(k => !answeredIds.has(k))

        return (
          <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col">
              <div className="flex items-center justify-between p-5 border-b border-slate-800">
                <h3 className="text-white font-semibold text-sm flex items-center gap-2">
                  <FileText className="w-4 h-4 text-violet-400" />
                  Detalhes da solicitação — {detailsModal.project_name}
                </h3>
                <button onClick={() => setDetailsModal(null)} className="text-slate-500 hover:text-slate-300">
                  <XCircle className="w-5 h-5" />
                </button>
              </div>

              <div className="overflow-y-auto p-5 space-y-5">
                {/* Solicitante + tipo */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Solicitante</p>
                    <p className="text-sm text-slate-200">{detailsModal.gp_name || '—'}</p>
                    <a href={`mailto:${detailsModal.gp_email}`} className="text-xs text-violet-400 hover:text-violet-300">
                      {detailsModal.gp_email}
                    </a>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Tipo de entregável</p>
                    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${dt?.color || 'bg-slate-700/40 text-slate-300'}`}>
                      <Package className="w-3 h-3" />
                      {typeLabel}
                    </span>
                  </div>
                </div>

                {/* Descrição */}
                <div>
                  <p className="text-xs text-slate-500 mb-1.5">Descrição</p>
                  <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-3 text-sm text-slate-200 whitespace-pre-wrap">
                    {detailsModal.description || <span className="text-slate-600 italic">— sem descrição —</span>}
                  </div>
                </div>

                {/* Perguntas e respostas */}
                <div>
                  <p className="text-xs text-slate-500 mb-2">
                    Respostas do wizard
                    <span className="text-slate-600 ml-2">
                      ({Object.keys(reqs).length} respondidas / {allQuestions.length} esperadas)
                    </span>
                  </p>
                  {allQuestions.length === 0 && extraKeys.length === 0 ? (
                    <p className="text-xs text-slate-600 italic">— sem perguntas registradas —</p>
                  ) : (
                    <div className="space-y-3">
                      {allQuestions.map(q => {
                        const ans = (reqs[q.id] || '').trim()
                        return (
                          <div key={q.id} className="border border-slate-800 rounded-lg p-3 bg-slate-800/30">
                            <p className="text-xs text-slate-400 font-medium mb-1">
                              {q.label}
                              {q.required && <span className="text-red-400 ml-1">*</span>}
                            </p>
                            {ans ? (
                              <p className="text-sm text-slate-200 whitespace-pre-wrap">{ans}</p>
                            ) : (
                              <p className="text-xs text-amber-400 italic">— não respondida —</p>
                            )}
                          </div>
                        )
                      })}
                      {extraKeys.map(k => (
                        <div key={k} className="border border-slate-800 rounded-lg p-3 bg-slate-800/30">
                          <p className="text-xs text-slate-500 font-mono mb-1">{k}</p>
                          <p className="text-sm text-slate-200 whitespace-pre-wrap">{reqs[k]}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Datas + status */}
                <div className="text-xs text-slate-500 flex items-center gap-4 pt-2 border-t border-slate-800">
                  <span>
                    Solicitado em {detailsModal.requested_at ? new Date(detailsModal.requested_at).toLocaleString('pt-BR') : '—'}
                  </span>
                  <span>
                    Status: <span className="text-slate-300">{STATUS_LABELS[detailsModal.status]?.label || detailsModal.status}</span>
                  </span>
                </div>

                {detailsModal.rejection_reason && (
                  <div className="bg-red-900/20 border border-red-800/40 rounded-lg p-3">
                    <p className="text-xs text-red-300 font-medium mb-1">Motivo da rejeição</p>
                    <p className="text-sm text-red-200 whitespace-pre-wrap">{detailsModal.rejection_reason}</p>
                  </div>
                )}
              </div>

              <div className="border-t border-slate-800 p-4 flex justify-end">
                <button
                  onClick={() => setDetailsModal(null)}
                  className="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg transition-colors"
                >
                  Fechar
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {/* ── Modal de rejeição com razão ─────────────────────────────────── */}
      {rejectModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-red-900/40 rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-semibold text-sm flex items-center gap-2">
                <MessageSquareWarning className="w-4 h-4 text-red-400" />
                Rejeitar solicitação
              </h3>
              <button onClick={() => setRejectModal(null)} className="text-slate-500 hover:text-slate-300">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 mb-4">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-slate-400">Projeto:</span>
                <span className="text-slate-200 font-medium">{rejectModal.project_name}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-slate-400">Será notificado:</span>
                <a href={`mailto:${rejectModal.gp_email}`} className="text-violet-400 hover:text-violet-300">
                  {rejectModal.gp_name} ({rejectModal.gp_email})
                </a>
              </div>
            </div>

            <p className="text-xs text-slate-400 mb-1">Motivo (será enviado por email ao solicitante) *</p>
            <textarea
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value.slice(0, 2000))}
              rows={5}
              placeholder="Explique o motivo da rejeição. Esse texto vai por email ao solicitante."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-red-600 focus:ring-1 focus:ring-red-600/30 transition-colors resize-none"
            />
            <div className="flex items-center justify-between mt-2">
              <span className={`text-xs ${rejectReason.trim().length < 10 ? 'text-amber-500' : 'text-slate-500'}`}>
                {rejectReason.length}/2000 — mínimo 10 caracteres
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setRejectModal(null)}
                  className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleReject}
                  disabled={rejecting || rejectReason.trim().length < 10}
                  className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
                >
                  {rejecting ? <Loader2 className="w-4 h-4 animate-spin" /> : <MessageSquareWarning className="w-4 h-4" />}
                  Rejeitar e notificar
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
    </PageTransition>
  )
}
