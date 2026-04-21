import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  BookOpen, Check, X, Edit2, Plus, Loader2, RefreshCw, Sparkles, AlertCircle, CheckCircle2,
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'

// MVP 19 Fase 19.3 — Glossário vivo por projeto.
//
// Alimenta a seção 1.3 do ERS quando os termos são aprovados.
// UI com 3 colunas: candidatos (a revisar) | aprovados | rejeitados.
// Ações por termo: aprovar, rejeitar, editar definition.
// Ação global: "Extrair candidatos" (dispara heurísticas no backend).
// Ação global: "+ Termo manual" (cadastra direto como aprovado).

type TermStatus = 'candidate' | 'approved' | 'rejected'

interface GlossaryTerm {
  id: string
  term: string
  definition: string
  source: string
  source_reference: string | null
  status: TermStatus
  created_at: string | null
  approved_at: string | null
  rejected_at: string | null
}

interface GlossaryListResponse {
  count: number
  terms: GlossaryTerm[]
}

interface ExtractResult {
  project_id: string
  scanned_sources: number
  candidates_found: number
  inserted: number
  skipped_existing: number
}

interface Props {
  projectId: string
}

const STATUS_LABELS: Record<TermStatus, { label: string; theme: string; icon: React.ReactNode }> = {
  candidate: {
    label: 'Candidatos',
    theme: 'border-amber-700/40 bg-amber-950/10',
    icon: <AlertCircle className="w-3.5 h-3.5 text-amber-400" />,
  },
  approved: {
    label: 'Aprovados (entram no ERS)',
    theme: 'border-emerald-800/40 bg-emerald-950/10',
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />,
  },
  rejected: {
    label: 'Rejeitados',
    theme: 'border-slate-700 bg-slate-900/20',
    icon: <X className="w-3.5 h-3.5 text-slate-500" />,
  },
}

export function GlossaryPanel({ projectId }: Props) {
  const toast = useToast()
  const qc = useQueryClient()

  const [editing, setEditing] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [newTerm, setNewTerm] = useState('')
  const [newDef, setNewDef] = useState('')

  const { data: candidates, isLoading: loadingCand } = useQuery<GlossaryListResponse>({
    queryKey: ['glossary', projectId, 'candidate'],
    queryFn: async () => {
      const res = await apiClient.get<GlossaryListResponse>(
        `/projects/${projectId}/glossary?status=candidate`
      )
      return res.data
    },
  })
  const { data: approved } = useQuery<GlossaryListResponse>({
    queryKey: ['glossary', projectId, 'approved'],
    queryFn: async () => {
      const res = await apiClient.get<GlossaryListResponse>(
        `/projects/${projectId}/glossary?status=approved`
      )
      return res.data
    },
  })
  const { data: rejected } = useQuery<GlossaryListResponse>({
    queryKey: ['glossary', projectId, 'rejected'],
    queryFn: async () => {
      const res = await apiClient.get<GlossaryListResponse>(
        `/projects/${projectId}/glossary?status=rejected`
      )
      return res.data
    },
  })

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['glossary', projectId] })
    qc.invalidateQueries({ queryKey: ['ers-freshness', projectId] })
  }

  const extract = useMutation<ExtractResult, unknown>({
    mutationFn: async () => {
      const res = await apiClient.post<ExtractResult>(
        `/projects/${projectId}/glossary/extract`
      )
      return res.data
    },
    onSuccess: (data) => {
      toast.success(`Extração concluída: ${data.inserted} novos candidatos (${data.skipped_existing} já existiam)`)
      invalidateAll()
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const approve = useMutation<unknown, unknown, string>({
    mutationFn: async (termId) =>
      (await apiClient.post(`/projects/${projectId}/glossary/${termId}/approve`)).data,
    onSuccess: () => invalidateAll(),
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const reject = useMutation<unknown, unknown, string>({
    mutationFn: async (termId) =>
      (await apiClient.post(`/projects/${projectId}/glossary/${termId}/reject`)).data,
    onSuccess: () => invalidateAll(),
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const updateDef = useMutation<unknown, unknown, { termId: string; definition: string }>({
    mutationFn: async ({ termId, definition }) =>
      (await apiClient.patch(`/projects/${projectId}/glossary/${termId}`, { definition })).data,
    onSuccess: () => {
      invalidateAll()
      setEditing(null)
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const createTerm = useMutation<unknown, unknown, { term: string; definition: string }>({
    mutationFn: async (body) =>
      (await apiClient.post(`/projects/${projectId}/glossary`, body)).data,
    onSuccess: () => {
      toast.success('Termo cadastrado')
      invalidateAll()
      setShowCreate(false)
      setNewTerm('')
      setNewDef('')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const startEdit = (t: GlossaryTerm) => {
    setEditing(t.id)
    setEditValue(t.definition)
  }

  const renderTerm = (t: GlossaryTerm) => {
    const isEditing = editing === t.id
    return (
      <li key={t.id} className="bg-slate-900/60 border border-slate-800 rounded p-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-slate-100 text-sm font-semibold">{t.term}</p>
            {isEditing ? (
              <textarea
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="w-full mt-1 text-[12px] text-slate-200 bg-slate-800 border border-slate-700 rounded px-2 py-1 focus:outline-none focus:border-violet-500 min-h-[60px]"
                placeholder="Definição do termo..."
              />
            ) : (
              <p className="text-[12px] text-slate-400 mt-0.5 break-words">
                {t.definition || <em className="text-slate-600">sem definição</em>}
              </p>
            )}
            {t.source_reference && !isEditing && (
              <p className="text-[10px] text-slate-600 mt-1">↳ {t.source_reference}</p>
            )}
          </div>

          <div className="flex items-center gap-1 flex-shrink-0">
            {isEditing ? (
              <>
                <button
                  type="button"
                  onClick={() => updateDef.mutate({ termId: t.id, definition: editValue })}
                  disabled={updateDef.isPending}
                  className="p-1.5 rounded text-emerald-400 hover:bg-emerald-500/10"
                  title="Salvar definição"
                >
                  <Check className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setEditing(null)}
                  className="p-1.5 rounded text-slate-500 hover:bg-slate-800"
                  title="Cancelar"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => startEdit(t)}
                  className="p-1.5 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800"
                  title="Editar definição"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>
                {t.status !== 'approved' && (
                  <button
                    type="button"
                    onClick={() => approve.mutate(t.id)}
                    disabled={approve.isPending}
                    className="p-1.5 rounded text-emerald-400 hover:bg-emerald-500/10"
                    title="Aprovar (entra no ERS)"
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                )}
                {t.status !== 'rejected' && (
                  <button
                    type="button"
                    onClick={() => reject.mutate(t.id)}
                    disabled={reject.isPending}
                    className="p-1.5 rounded text-red-400 hover:bg-red-500/10"
                    title="Rejeitar (não entra no ERS)"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </li>
    )
  }

  const columnData: Record<TermStatus, GlossaryTerm[]> = {
    candidate: candidates?.terms || [],
    approved: approved?.terms || [],
    rejected: rejected?.terms || [],
  }

  return (
    <section className="space-y-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div className="flex items-start gap-2">
          <BookOpen className="w-5 h-5 text-violet-400 mt-0.5" />
          <div>
            <h3 className="text-slate-100 text-sm font-semibold">Glossário do Projeto</h3>
            <p className="text-slate-500 text-xs mt-0.5">
              Termos específicos deste projeto. Apenas os <strong>aprovados</strong> aparecem na
              seção 1.3 do ERS. Acrônimos canônicos do GCA (OCG, RBAC, GP, etc) ficam
              no help global.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => setShowCreate((v) => !v)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-slate-700 text-slate-300 hover:border-slate-500 hover:text-slate-100"
          >
            <Plus className="w-3.5 h-3.5" />
            Termo manual
          </button>
          <button
            type="button"
            onClick={() => extract.mutate()}
            disabled={extract.isPending}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded bg-violet-600/30 border border-violet-500/40 text-violet-100 hover:bg-violet-600/50 disabled:opacity-50"
            title="Executa heurísticas de extração sobre módulos, análises do Arguidor, OCG e itens do Gatekeeper"
          >
            {extract.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            Extrair candidatos
          </button>
        </div>
      </div>

      {/* Form de cadastro manual */}
      {showCreate && (
        <div className="bg-slate-900/60 border border-slate-700 rounded p-3 space-y-2">
          <div className="flex gap-2">
            <input
              type="text"
              value={newTerm}
              onChange={(e) => setNewTerm(e.target.value)}
              placeholder="Termo (ex: NFE, Cliente VIP)"
              className="flex-1 text-sm bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-slate-200 focus:outline-none focus:border-violet-500"
              maxLength={200}
            />
          </div>
          <textarea
            value={newDef}
            onChange={(e) => setNewDef(e.target.value)}
            placeholder="Definição (opcional — pode editar depois)"
            className="w-full text-sm bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-slate-200 focus:outline-none focus:border-violet-500 min-h-[60px]"
            maxLength={2000}
          />
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => { setShowCreate(false); setNewTerm(''); setNewDef('') }}
              className="text-xs px-3 py-1.5 rounded text-slate-400 hover:text-slate-200"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => createTerm.mutate({ term: newTerm.trim(), definition: newDef.trim() })}
              disabled={!newTerm.trim() || createTerm.isPending}
              className="text-xs px-3 py-1.5 rounded bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-50"
            >
              {createTerm.isPending ? 'Salvando…' : 'Cadastrar'}
            </button>
          </div>
        </div>
      )}

      {loadingCand ? (
        <div className="flex items-center gap-2 text-slate-500 text-xs py-4">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Carregando glossário…
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {(['candidate', 'approved', 'rejected'] as const).map((status) => {
            const meta = STATUS_LABELS[status]
            const items = columnData[status]
            return (
              <div key={status} className={`border rounded-lg p-2.5 ${meta.theme}`}>
                <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-800/60">
                  {meta.icon}
                  <h4 className="text-slate-200 text-xs font-semibold flex-1">{meta.label}</h4>
                  <span className="text-[10px] text-slate-500">{items.length}</span>
                </div>
                {items.length === 0 ? (
                  <p className="text-slate-600 text-[11px] italic text-center py-4">
                    {status === 'candidate'
                      ? 'Nenhum candidato. Clique em "Extrair candidatos".'
                      : status === 'approved'
                        ? 'Nenhum termo aprovado.'
                        : 'Nenhum termo rejeitado.'}
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {items.map(renderTerm)}
                  </ul>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Hint após primeira extração */}
      {candidates && candidates.count === 0 && approved && approved.count === 0 && (
        <div className="text-xs text-slate-500 text-center py-2 border-t border-slate-800/60">
          <RefreshCw className="w-3 h-3 inline mr-1 -mt-0.5" />
          Rode a extração para descobrir candidatos a partir das análises do Arguidor,
          módulos do backlog, itens do Gatekeeper e PROJECT_PROFILE do OCG.
        </div>
      )}
    </section>
  )
}
