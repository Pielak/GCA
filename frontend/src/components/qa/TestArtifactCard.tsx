import { CheckCircle, XCircle, Play, Edit2 } from 'lucide-react'

interface TestArtifact {
  id: string
  name: string
  type: string
  status: string
  content?: string
  [key: string]: any
}

interface Props {
  test: TestArtifact
  canEdit: boolean
  onEdit: (test: TestArtifact) => void
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onExecute: (id: string) => void
}

export function TestArtifactCard({ test, canEdit, onEdit, onApprove, onReject, onExecute }: Props) {
  const statusColors: Record<string, string> = {
    pending: 'bg-amber-500/20 text-amber-300',
    approved: 'bg-emerald-500/20 text-emerald-300',
    rejected: 'bg-red-500/20 text-red-300',
    executed: 'bg-blue-500/20 text-blue-300',
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-slate-200 text-sm font-medium">{test.name}</p>
          <p className="text-slate-500 text-xs mt-0.5">{test.type}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full ${statusColors[test.status] || 'bg-slate-700 text-slate-400'}`}>
            {test.status}
          </span>
          {canEdit && (
            <div className="flex items-center gap-1">
              <button onClick={() => onEdit(test)} className="p-1 text-slate-500 hover:text-slate-300"><Edit2 className="w-3.5 h-3.5" /></button>
              <button onClick={() => onApprove(test.id)} className="p-1 text-slate-500 hover:text-emerald-400"><CheckCircle className="w-3.5 h-3.5" /></button>
              <button onClick={() => onReject(test.id)} className="p-1 text-slate-500 hover:text-red-400"><XCircle className="w-3.5 h-3.5" /></button>
              <button onClick={() => onExecute(test.id)} className="p-1 text-slate-500 hover:text-blue-400"><Play className="w-3.5 h-3.5" /></button>
            </div>
          )}
        </div>
      </div>
      {test.content && (
        <pre className="mt-2 text-xs text-slate-400 bg-slate-800/50 rounded p-2 overflow-x-auto max-h-32">{test.content}</pre>
      )}
    </div>
  )
}
