import { useEffect, useState } from 'react'
import { X, Bug, Loader2, AlertCircle, Paperclip, Trash2 } from 'lucide-react'
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

const MAX_FILES = 5
const MAX_SIZE_BYTES = 10 * 1024 * 1024
const ALLOWED_EXT = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.txt', '.log', '.json', '.pdf']

function validateFile(f: File): string | null {
  const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
  if (!ALLOWED_EXT.includes(ext)) return `Extensão não permitida: ${ext}`
  if (f.size > MAX_SIZE_BYTES) return `${f.name}: excede 10 MB`
  return null
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(2)} MB`
}

export function NewIncidentModal({ projectId, onClose, onCreated }: Props) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('bug')
  const [priority, setPriority] = useState('media')
  // Emenda 2026-04-19: section autodetectada pela rota; flow obrigatório
  const [sectionReference, setSectionReference] = useState('')
  const [flowDescription, setFlowDescription] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState<string | null>(null)

  useEffect(() => {
    // Autopreenche com a rota atual (ex: /projects/.../ocg) — editável
    setSectionReference(window.location.pathname)
  }, [])

  const onFilesPicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files || [])
    const merged = [...files, ...picked].slice(0, MAX_FILES)
    const invalid = merged.map(validateFile).find(Boolean)
    if (invalid) {
      setError(invalid)
      return
    }
    setError(null)
    setFiles(merged)
    e.target.value = ''  // permite re-selecionar mesmo arquivo
  }

  const removeFile = (idx: number) => {
    setFiles(files.filter((_, i) => i !== idx))
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !description.trim() || !flowDescription.trim()) {
      setError('Título, descrição e fluxo do incidente são obrigatórios.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const res = await apiClient.post(`/projects/${projectId}/incidents`, {
        title: title.trim(),
        description: description.trim(),
        category,
        priority,
        flow_description: flowDescription.trim(),
        section_reference: sectionReference.trim() || null,
      })
      const ticketId: string = res.data.id

      // Upload de anexos sequencial
      for (let i = 0; i < files.length; i++) {
        setUploadProgress(`Enviando ${i + 1}/${files.length}: ${files[i].name}`)
        const fd = new FormData()
        fd.append('file', files[i])
        await apiClient.post(`/incidents/${ticketId}/attachments`, fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      }

      onCreated()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Falha ao abrir ticket.')
    } finally {
      setSubmitting(false)
      setUploadProgress(null)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm overflow-y-auto"
      onClick={onClose}
    >
      <form
        onSubmit={submit}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-lg my-8 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Bug className="w-4 h-4 text-violet-400" />
            <h2 className="text-slate-100 text-sm font-semibold">Abrir ticket de incidente</h2>
          </div>
          <button type="button" onClick={onClose} className="text-slate-500 hover:text-slate-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          {error && (
            <div className="flex items-start gap-2 p-2.5 bg-red-950/30 border border-red-900/40 rounded-lg text-red-300 text-xs">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" /> <span>{error}</span>
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
              rows={4}
              placeholder="Descreva o problema observado."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50 resize-none"
              required
            />
          </div>

          {/* Seção onde o erro ocorreu (autopreenchida, editável) */}
          <div>
            <label className="text-slate-400 text-xs block mb-1">
              Seção onde o erro ocorreu
              <span className="text-slate-500 ml-2">(autopreenchida, editável)</span>
            </label>
            <input
              type="text"
              value={sectionReference}
              onChange={e => setSectionReference(e.target.value)}
              maxLength={300}
              placeholder="/projects/.../ocg"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50 font-mono"
            />
          </div>

          {/* Fluxo obrigatório */}
          <div>
            <label className="text-slate-400 text-xs block mb-1">
              Fluxo que estava sendo executado
              <span className="text-red-400 ml-1">*</span>
            </label>
            <textarea
              value={flowDescription}
              onChange={e => setFlowDescription(e.target.value)}
              rows={4}
              placeholder="Descreva passo a passo o que você estava fazendo quando o erro apareceu. Ex: cliquei em 'Regenerar OCG', esperei X segundos, vi a mensagem Y."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500/50 resize-none"
              required
            />
          </div>

          {/* Anexos */}
          <div>
            <label className="text-slate-400 text-xs block mb-1">
              Anexos ({files.length}/{MAX_FILES})
              <span className="text-slate-500 ml-2">imagem / log / txt / json / pdf — 10 MB cada</span>
            </label>
            <label className="flex items-center gap-2 px-3 py-2 bg-slate-800 border border-dashed border-slate-700 rounded-lg text-slate-400 text-xs hover:border-violet-500/50 cursor-pointer transition-colors">
              <Paperclip className="w-3.5 h-3.5" />
              <span>Adicionar arquivos</span>
              <input
                type="file"
                multiple
                accept={ALLOWED_EXT.join(',')}
                onChange={onFilesPicked}
                disabled={files.length >= MAX_FILES}
                className="hidden"
              />
            </label>
            {files.length > 0 && (
              <ul className="mt-2 space-y-1">
                {files.map((f, idx) => (
                  <li key={idx} className="flex items-center justify-between text-xs text-slate-300 bg-slate-800/60 rounded px-2 py-1">
                    <span className="truncate">{f.name}</span>
                    <span className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-slate-500">{formatBytes(f.size)}</span>
                      <button
                        type="button"
                        onClick={() => removeFile(idx)}
                        className="text-slate-500 hover:text-red-400"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between gap-2 px-5 py-3 border-t border-slate-800">
          <span className="text-slate-500 text-[11px]">
            {uploadProgress || (submitting ? 'Criando ticket…' : '')}
          </span>
          <div className="flex items-center gap-2">
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
        </div>
      </form>
    </div>
  )
}
