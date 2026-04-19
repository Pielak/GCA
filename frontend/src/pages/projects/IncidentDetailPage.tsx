import { useState, useEffect, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft, Bug, Loader2, MessageSquare, Send, AlertCircle, Clock,
  CheckCircle2, XCircle, PlayCircle, Paperclip, Download, Trash2,
  FileText, Image as ImageIcon, FileCode,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useProjectPermissions } from '@/hooks/useProjectPermissions'
import { useAuthStore } from '@/stores/authStore'

interface Ticket {
  id: string
  project_id: string
  project_name: string | null
  author_id: string
  author_name: string | null
  target_scope: 'gp' | 'admin'
  category: string
  priority: 'baixa' | 'media' | 'alta' | 'critica'
  status: 'open' | 'in_progress' | 'resolved' | 'closed'
  title: string
  description: string
  section_reference: string | null
  flow_description: string | null
  created_at: string
  updated_at: string
  resolved_at: string | null
  resolved_by: string | null
}

interface Comment {
  id: string
  ticket_id: string
  author_id: string
  author_name: string | null
  body: string
  created_at: string
}

interface Attachment {
  id: string
  ticket_id: string
  uploader_id: string
  uploader_name: string | null
  filename: string
  mime: string
  size_bytes: number
  sha256: string
  created_at: string
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(2)} MB`
}

function iconForMime(mime: string) {
  if (mime.startsWith('image/')) return ImageIcon
  if (mime === 'application/json') return FileCode
  return FileText
}

const CATEGORY_LABELS: Record<string, string> = {
  bug: 'Bug',
  duvida: 'Dúvida',
  pedido_feature: 'Pedido de feature',
  incidente_pipeline: 'Incidente de pipeline',
}

const PRIORITY_LABELS: Record<string, { label: string; classes: string }> = {
  baixa: { label: 'Baixa', classes: 'bg-slate-500/10 text-slate-300 border-slate-500/30' },
  media: { label: 'Média', classes: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30' },
  alta: { label: 'Alta', classes: 'bg-amber-500/10 text-amber-300 border-amber-500/30' },
  critica: { label: 'Crítica', classes: 'bg-red-500/10 text-red-300 border-red-500/30' },
}

const STATUS_META: Record<string, { label: string; classes: string; icon: any }> = {
  open: { label: 'Aberto', classes: 'bg-amber-500/10 text-amber-300 border-amber-500/30', icon: AlertCircle },
  in_progress: { label: 'Em andamento', classes: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30', icon: PlayCircle },
  resolved: { label: 'Resolvido', classes: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30', icon: CheckCircle2 },
  closed: { label: 'Fechado', classes: 'bg-slate-500/10 text-slate-400 border-slate-500/30', icon: XCircle },
}

export function IncidentDetailPage() {
  const { id: projectId, ticketId } = useParams<{ id: string; ticketId: string }>()
  const { hasRole } = useProjectPermissions()
  const user = useAuthStore(s => s.user)
  const isAdmin = user?.is_admin || false
  const isGP = hasRole('gp')

  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [commentBody, setCommentBody] = useState('')
  const [submittingComment, setSubmittingComment] = useState(false)
  const [updatingStatus, setUpdatingStatus] = useState(false)
  const [uploadingAttachment, setUploadingAttachment] = useState(false)

  const load = useCallback(async () => {
    if (!ticketId) return
    try {
      const res = await apiClient.get(`/incidents/${ticketId}`)
      setTicket(res.data.ticket)
      setComments(res.data.comments || [])
      setAttachments(res.data.attachments || [])
      setError(null)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Erro ao carregar ticket.')
    } finally {
      setLoading(false)
    }
  }, [ticketId])

  useEffect(() => { load() }, [load])

  const submitComment = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!commentBody.trim() || !ticketId) return
    setSubmittingComment(true)
    try {
      await apiClient.post(`/incidents/${ticketId}/comments`, { body: commentBody.trim() })
      setCommentBody('')
      await load()
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Falha ao publicar comentário.')
    } finally {
      setSubmittingComment(false)
    }
  }

  const changeStatus = async (newStatus: string) => {
    if (!ticketId) return
    setUpdatingStatus(true)
    try {
      await apiClient.patch(`/incidents/${ticketId}/status`, { status: newStatus })
      await load()
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Falha ao mudar status.')
    } finally {
      setUpdatingStatus(false)
    }
  }

  const uploadAttachment = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f || !ticketId) return
    if (attachments.length >= 5) {
      alert('Máximo de 5 anexos por ticket.')
      return
    }
    setUploadingAttachment(true)
    try {
      const fd = new FormData()
      fd.append('file', f)
      await apiClient.post(`/incidents/${ticketId}/attachments`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      await load()
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Falha ao enviar anexo.')
    } finally {
      setUploadingAttachment(false)
      e.target.value = ''
    }
  }

  const deleteAttachment = async (att: Attachment) => {
    if (!ticketId) return
    if (!window.confirm(`Excluir anexo "${att.filename}"? Esta ação é irreversível.`)) return
    try {
      await apiClient.delete(`/incidents/${ticketId}/attachments/${att.id}`)
      await load()
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Falha ao excluir anexo.')
    }
  }

  const downloadAttachment = async (att: Attachment) => {
    if (!ticketId) return
    try {
      const res = await apiClient.get(
        `/incidents/${ticketId}/attachments/${att.id}/download`,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(new Blob([res.data], { type: att.mime }))
      const a = document.createElement('a')
      a.href = url
      a.download = att.filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Falha ao baixar anexo.')
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
      </div>
    )
  }
  if (error || !ticket) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <Link to={`/projects/${projectId}/incidents`} className="text-violet-400 hover:text-violet-300 text-sm inline-flex items-center gap-1">
          <ArrowLeft className="w-3.5 h-3.5" /> Voltar para a lista
        </Link>
        <div className="mt-4 p-3 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-sm">
          {error || 'Ticket não encontrado.'}
        </div>
      </div>
    )
  }

  const statusMeta = STATUS_META[ticket.status] ?? STATUS_META.open
  const StatusIcon = statusMeta.icon
  const priorityMeta = PRIORITY_LABELS[ticket.priority] ?? PRIORITY_LABELS.baixa
  const isAuthor = user?.id === ticket.author_id
  const canChangeStatus = isAdmin || isGP || isAuthor

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5">
      <Link
        to={`/projects/${projectId}/incidents`}
        className="text-violet-400 hover:text-violet-300 text-sm inline-flex items-center gap-1"
      >
        <ArrowLeft className="w-3.5 h-3.5" /> Voltar para a lista
      </Link>

      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex items-start gap-3">
          <Bug className="w-5 h-5 text-violet-400 mt-1" />
          <div className="flex-1">
            <h1 className="text-slate-100 text-lg font-semibold">{ticket.title}</h1>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={`flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md border ${statusMeta.classes}`}>
                <StatusIcon className="w-3 h-3" /> {statusMeta.label}
              </span>
              <span className={`text-[11px] px-2 py-0.5 rounded-md border ${priorityMeta.classes}`}>
                Prioridade {priorityMeta.label}
              </span>
              <span className="text-[11px] text-slate-500">
                {CATEGORY_LABELS[ticket.category] || ticket.category}
              </span>
              <span className="text-[11px] text-slate-500">
                {ticket.target_scope === 'admin' ? '· Escalado → Admin' : '· Direcionado → GP'}
              </span>
            </div>
          </div>
        </div>

        <p className="text-slate-300 text-sm whitespace-pre-wrap leading-relaxed">
          {ticket.description}
        </p>

        {/* Emenda: section + flow */}
        {(ticket.section_reference || ticket.flow_description) && (
          <div className="space-y-2 pt-3 border-t border-slate-800">
            {ticket.section_reference && (
              <div>
                <div className="text-slate-500 text-[10px] uppercase tracking-widest">Seção onde ocorreu</div>
                <code className="text-slate-300 text-xs font-mono">{ticket.section_reference}</code>
              </div>
            )}
            {ticket.flow_description && (
              <div>
                <div className="text-slate-500 text-[10px] uppercase tracking-widest">Fluxo executado</div>
                <p className="text-slate-300 text-sm whitespace-pre-wrap leading-relaxed mt-1">{ticket.flow_description}</p>
              </div>
            )}
          </div>
        )}

        <div className="flex items-center gap-3 text-[11px] text-slate-500 pt-2 border-t border-slate-800">
          <Clock className="w-3 h-3" />
          <span>Aberto por {ticket.author_name || 'autor desconhecido'}</span>
          <span>·</span>
          <span>{new Date(ticket.created_at).toLocaleString('pt-BR')}</span>
          {ticket.resolved_at && (
            <>
              <span>·</span>
              <span className="text-emerald-400">
                Resolvido em {new Date(ticket.resolved_at).toLocaleString('pt-BR')}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Ações de status */}
      {canChangeStatus && (
        <div className="flex items-center gap-2 p-3 bg-slate-900/40 border border-slate-800 rounded-xl">
          <span className="text-slate-500 text-xs">Mudar status:</span>
          {(['open', 'in_progress', 'resolved', 'closed'] as const).map(s => (
            <button
              key={s}
              disabled={updatingStatus || ticket.status === s}
              onClick={() => changeStatus(s)}
              className={`text-[11px] px-2 py-1 rounded-md border transition-colors ${
                ticket.status === s
                  ? 'bg-slate-700/50 text-slate-400 border-slate-600 cursor-default'
                  : 'bg-slate-800 text-slate-300 border-slate-700 hover:border-violet-500/50 hover:text-violet-300'
              }`}
            >
              {STATUS_META[s].label}
            </button>
          ))}
        </div>
      )}

      {/* Anexos */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Paperclip className="w-4 h-4 text-slate-400" />
            <h2 className="text-slate-200 text-sm font-medium">Anexos ({attachments.length}/5)</h2>
          </div>
          {attachments.length < 5 && (
            <label className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 cursor-pointer">
              {uploadingAttachment ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Paperclip className="w-3 h-3" />
              )}
              <span>Adicionar</span>
              <input
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.gif,.txt,.log,.json,.pdf"
                onChange={uploadAttachment}
                disabled={uploadingAttachment}
                className="hidden"
              />
            </label>
          )}
        </div>
        {attachments.length === 0 ? (
          <p className="text-slate-500 text-xs italic">Sem anexos.</p>
        ) : (
          <ul className="space-y-1">
            {attachments.map(att => {
              const Icon = iconForMime(att.mime)
              const canDelete = isAdmin || att.uploader_id === user?.id
              return (
                <li key={att.id} className="flex items-center justify-between text-xs bg-slate-800/40 hover:bg-slate-800/70 rounded px-3 py-2 transition-colors">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <Icon className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                    <span className="text-slate-200 truncate">{att.filename}</span>
                    <span className="text-slate-500 flex-shrink-0">{formatBytes(att.size_bytes)}</span>
                    <span className="text-slate-600 text-[10px] flex-shrink-0" title={att.sha256}>
                      sha:{att.sha256.slice(0, 8)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-slate-500 text-[10px]">
                      {att.uploader_name || 'autor desconhecido'}
                    </span>
                    <button
                      onClick={() => downloadAttachment(att)}
                      className="text-slate-500 hover:text-violet-400"
                      title="Baixar"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                    {canDelete && (
                      <button
                        onClick={() => deleteAttachment(att)}
                        className="text-slate-500 hover:text-red-400"
                        title="Excluir"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* Comentários */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <MessageSquare className="w-4 h-4 text-slate-400" />
          <h2 className="text-slate-200 text-sm font-medium">Comentários ({comments.length})</h2>
        </div>

        {comments.length === 0 ? (
          <p className="text-slate-500 text-xs italic">Sem comentários ainda.</p>
        ) : (
          <div className="space-y-3">
            {comments.map(c => (
              <div key={c.id} className="border-l-2 border-slate-700 pl-3 py-1">
                <div className="flex items-center gap-2 text-[11px] text-slate-500">
                  <strong className="text-slate-300">{c.author_name || 'Autor'}</strong>
                  <span>·</span>
                  <span>{new Date(c.created_at).toLocaleString('pt-BR')}</span>
                </div>
                <p className="text-slate-300 text-sm mt-1 whitespace-pre-wrap">{c.body}</p>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={submitComment} className="mt-4 space-y-2">
          <textarea
            value={commentBody}
            onChange={e => setCommentBody(e.target.value)}
            rows={3}
            placeholder="Adicione um comentário..."
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50 resize-none"
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!commentBody.trim() || submittingComment}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs rounded-lg"
            >
              {submittingComment ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              Publicar
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
