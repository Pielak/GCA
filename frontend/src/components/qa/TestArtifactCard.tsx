import { useState } from 'react'
import { ChevronDown, ChevronUp, Pencil, CheckCircle2, XCircle, Play, Clock, User } from 'lucide-react'

interface TestArtifact {
  id: string
  title: string
  test_type: string
  status: string
  content: string
  description?: string
  created_by: string
  last_edited_by?: string
  last_edited_at?: string
  version: number
  created_at: string
}

interface TestArtifactCardProps {
  test: TestArtifact
  canEdit: boolean
  onEdit: (id: string) => void
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onExecute: (id: string) => void
}

const statusConfig: Record<string, { label: string; bg: string; text: string; border: string }> = {
  pending_review: { label: 'Pending Review', bg: 'bg-amber-900/30', text: 'text-amber-400', border: 'border-amber-800/40' },
  approved: { label: 'Approved', bg: 'bg-emerald-900/30', text: 'text-emerald-400', border: 'border-emerald-800/40' },
  rejected: { label: 'Rejected', bg: 'bg-red-900/30', text: 'text-red-400', border: 'border-red-800/40' },
  edited: { label: 'Edited', bg: 'bg-violet-900/30', text: 'text-violet-400', border: 'border-violet-800/40' },
}

const typeConfig: Record<string, { label: string; bg: string; text: string; border: string }> = {
  unit: { label: 'Unit', bg: 'bg-blue-900/30', text: 'text-blue-400', border: 'border-blue-800/40' },
  integration: { label: 'Integration', bg: 'bg-violet-900/30', text: 'text-violet-400', border: 'border-violet-800/40' },
  e2e: { label: 'E2E', bg: 'bg-emerald-900/30', text: 'text-emerald-400', border: 'border-emerald-800/40' },
  regression: { label: 'Regression', bg: 'bg-amber-900/30', text: 'text-amber-400', border: 'border-amber-800/40' },
  load: { label: 'Load', bg: 'bg-orange-900/30', text: 'text-orange-400', border: 'border-orange-800/40' },
  security: { label: 'Security', bg: 'bg-red-900/30', text: 'text-red-400', border: 'border-red-800/40' },
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function TestArtifactCard({ test, canEdit, onEdit, onApprove, onReject, onExecute }: TestArtifactCardProps) {
  const [expanded, setExpanded] = useState(false)

  const status = statusConfig[test.status] || statusConfig.pending_review
  const type = typeConfig[test.test_type] || typeConfig.unit

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <h3 className="text-slate-200 text-sm font-semibold truncate">{test.title}</h3>
              <span className={`px-2 py-0.5 rounded text-xs border ${type.bg} ${type.text} ${type.border}`}>
                {type.label}
              </span>
              <span className={`px-2 py-0.5 rounded text-xs border ${status.bg} ${status.text} ${status.border}`}>
                {status.label}
              </span>
            </div>
            {test.description && (
              <p className="text-slate-500 text-xs mt-1 line-clamp-2">{test.description}</p>
            )}
          </div>
          <span className="text-slate-600 text-xs font-mono shrink-0">v{test.version}</span>
        </div>

        {/* Meta info */}
        <div className="flex items-center gap-4 mt-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <User className="w-3 h-3" /> {test.created_by}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" /> {formatDate(test.created_at)}
          </span>
          {test.last_edited_by && (
            <span className="flex items-center gap-1">
              <Pencil className="w-3 h-3" /> {test.last_edited_by} em {test.last_edited_at ? formatDate(test.last_edited_at) : ''}
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-slate-800 text-slate-400 hover:bg-slate-700 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {expanded ? 'Recolher' : 'Ver codigo'}
          </button>

          {canEdit && (
            <button
              onClick={() => onEdit(test.id)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-violet-900/30 text-violet-400 hover:bg-violet-900/50 transition-colors"
            >
              <Pencil className="w-3 h-3" /> Editar
            </button>
          )}

          {canEdit && (
            <button
              onClick={() => onApprove(test.id)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-emerald-900/30 text-emerald-400 hover:bg-emerald-900/50 transition-colors"
            >
              <CheckCircle2 className="w-3 h-3" /> Aprovar
            </button>
          )}

          {canEdit && (
            <button
              onClick={() => onReject(test.id)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-red-900/30 text-red-400 hover:bg-red-900/50 transition-colors"
            >
              <XCircle className="w-3 h-3" /> Rejeitar
            </button>
          )}

          <button
            onClick={() => onExecute(test.id)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-emerald-500 text-white hover:bg-emerald-400 transition-colors"
          >
            <Play className="w-3 h-3" /> Executar
          </button>
        </div>
      </div>

      {/* Expandable content */}
      {expanded && (
        <div className="border-t border-slate-800 p-4">
          <pre className="bg-slate-950 rounded-lg p-4 overflow-x-auto text-xs text-slate-300 font-mono whitespace-pre-wrap">
            {test.content}
          </pre>
        </div>
      )}
    </div>
  )
}
