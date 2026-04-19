import { useState } from 'react'
import { X, Bug, Loader2, AlertCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface Props {
  projectId: string
  onClose: () => void
  onCreated: () => void
}

const CATEGORIES = [
  { value: 'bug', label: 'Bug' },
  { value: 'duvida', label: 'Dúvida' },
  { value: 'pedido_feature', label: 'Pedido de funcionalidade' },
  { value: 'incidente_pipeline', label: 'Incidente no pipeline' },
]

const PRIORITIES = [
  { value: 'baixa', label: 'Baixa' },
  { value: 'media', label: 'Média' },
  { value: 'alta', label: 'Alta' },
  { value: 'critica', label: 'Crítica' },
]

export function NewIncidentModal({ projectId, onClose, onCreated }: Props) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('bug')
  const [priority, setPriority] = useState('media')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !description.trim()) {
      setError('Título e descrição são obrigatórios.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await apiClient.post(`/projects/${projectId}/incidents`, {
        title: title.trim(),
        description: description.trim(),
        category,
        priority,
      })
      onCreated()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Falha ao abrir ticket.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <form
        onSubmit={submit}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-lg bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Bug className="w-4 h-4 text-violet-400" />
            <h2 className="text-slate-100 text-sm font-semibold">Abrir ticket de incidente</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          {error && (
            <div className="flex items-center gap-2 p-2.5 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-xs">
              <AlertCircle className="w-3.5 h-3.5" /> {error}
            </div>
          )}

          <div>
            <label className="text-slate-400 text-xs block mb-1">Título</label>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              maxLength={200}
              placeholder="Resuma o problema em uma frase"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-slate-400 text-xs block mb-1">Categoria</label>
              <select
                value={category}
                onChange={e => setCategory(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2 py-2 text-sm text-slate-200"
              >
                {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-slate-400 text-xs block mb-1">Prioridade</label>
              <select
                value={priority}
                onChange={e => setPriority(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2 py-2 text-sm text-slate-200"
              >
                {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-xs block mb-1">Descrição</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={6}
              placeholder="Descreva o que aconteceu, passos para reproduzir, comportamento esperado e qualquer contexto útil."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50 resize-none"
              required
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-slate-800">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-slate-400 hover:text-slate-200 text-xs"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs rounded-lg"
          >
            {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Abrir ticket
          </button>
        </div>
      </form>
    </div>
  )
}
