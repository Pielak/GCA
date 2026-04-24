import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, AlertTriangle, BookOpen, Loader2, Edit3 } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAppliedDefaults, AppliedDefaultItem } from '@/hooks/useAppliedDefaults'
import { formatDateTimeBR } from '@/lib/datetime'

const CATEGORY_LABEL: Record<string, string> = {
  legal: 'Jurídico',
  security: 'Segurança',
  technical: 'Técnico',
  compliance: 'Compliance',
  architecture: 'Arquitetura',
}

const CATEGORY_COLOR: Record<string, string> = {
  legal: 'text-amber-400',
  security: 'text-red-400',
  technical: 'text-cyan-400',
  compliance: 'text-violet-400',
  architecture: 'text-emerald-400',
}

export function AppliedDefaultsPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { data, loading, refetch } = useAppliedDefaults(projectId)
  const [contestingId, setContestingId] = useState<string | null>(null)
  const [contestValue, setContestValue] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="p-8 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
      </div>
    )
  }

  if (!data) {
    return <div className="p-8 text-slate-500">Não foi possível carregar as decisões.</div>
  }

  if (data.items.length === 0) {
    return (
      <div className="p-6 max-w-5xl">
        <h1 className="text-xl font-semibold text-slate-100 mb-1">Decisões Automáticas</h1>
        <p className="text-xs text-slate-500 mb-6">
          Aqui aparecem decisões que o GCA aplicou automaticamente no seu projeto com base
          em domínio público (LGPD, Código Civil, defaults técnicos). Você pode contestar
          qualquer decisão.
        </p>
        <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-6 text-sm text-slate-500">
          Ainda não há decisões automáticas. Elas aparecem à medida que o Arguidor
          identifica gaps com resposta canônica de domínio público.
        </div>
      </div>
    )
  }

  const groups: Record<string, AppliedDefaultItem[]> = {}
  for (const it of data.items) {
    const cat = it.category
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(it)
  }

  const startContest = (it: AppliedDefaultItem) => {
    setContestingId(it.id)
    setContestValue(it.contested_value || it.decision_value)
    setError(null)
  }

  const submitContest = async (decisionId: string) => {
    if (!projectId || !contestValue.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await apiClient.post(
        `/projects/${projectId}/applied-defaults/${decisionId}/contest`,
        { new_value: contestValue },
      )
      setContestingId(null)
      setContestValue('')
      await refetch()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Falha ao contestar')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100 mb-1">Decisões Automáticas</h1>
        <p className="text-xs text-slate-500">
          {data.items.length} decisões aplicadas · {data.contested_count} contestadas.
          Cada decisão vem de domínio público (citação verificável). Contestar substitui o valor pro CodeGen.
        </p>
      </header>

      {error && (
        <div className="mb-4 px-3 py-2 bg-red-950/30 border border-red-900/40 rounded text-xs text-red-400">{error}</div>
      )}

      {Object.entries(groups).map(([cat, items]) => (
        <section key={cat} className="mb-6">
          <h2 className={`text-xs uppercase tracking-wide font-semibold mb-2 ${CATEGORY_COLOR[cat] || 'text-slate-300'}`}>
            {CATEGORY_LABEL[cat] || cat} ({items.length})
          </h2>
          <div className="space-y-2">
            {items.map((it) => {
              const isContested = it.contested_at !== null
              const isEditing = contestingId === it.id
              return (
                <div
                  key={it.id}
                  className={`border rounded-lg p-4 ${isContested ? 'border-amber-700/40 bg-amber-950/10' : 'border-slate-800 bg-slate-900'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {isContested ? (
                          <Edit3 className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                        ) : (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                        )}
                        <span className="text-xs font-mono text-slate-400">{it.decision_key}</span>
                        <span className="text-[10px] text-slate-600">({it.gap_id})</span>
                      </div>
                      <pre className="text-xs text-slate-200 whitespace-pre-wrap font-sans mb-2">
                        {isContested ? it.contested_value : it.decision_value}
                      </pre>
                      <div className="flex items-center gap-2 text-[10px] text-slate-500">
                        <BookOpen className="w-3 h-3" />
                        <span>{it.source_citation}</span>
                        <span className="text-slate-700">·</span>
                        <span>aplicado {formatDateTimeBR(it.applied_at)}</span>
                        {isContested && it.contested_at && (
                          <>
                            <span className="text-slate-700">·</span>
                            <span className="text-amber-400">contestado {formatDateTimeBR(it.contested_at)}</span>
                          </>
                        )}
                      </div>
                      {it.rationale && (
                        <p className="mt-2 text-[10px] text-slate-500 italic">{it.rationale}</p>
                      )}
                    </div>
                    {!isEditing && (
                      <button
                        onClick={() => startContest(it)}
                        className="flex-shrink-0 inline-flex items-center gap-1 px-3 py-1 rounded text-xs bg-slate-800 hover:bg-slate-700 text-slate-300"
                      >
                        <Edit3 className="w-3 h-3" /> {isContested ? 'Reeditar' : 'Contestar'}
                      </button>
                    )}
                  </div>

                  {isEditing && (
                    <div className="mt-3 pt-3 border-t border-slate-800">
                      <p className="text-[10px] text-slate-500 mb-2">
                        Escreva o valor correto pro seu caso específico. Será usado pelo CodeGen em vez do default.
                      </p>
                      <textarea
                        value={contestValue}
                        onChange={(e) => setContestValue(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 font-sans"
                        rows={4}
                      />
                      <div className="mt-2 flex gap-2">
                        <button
                          onClick={() => submitContest(it.id)}
                          disabled={submitting || !contestValue.trim()}
                          className="px-3 py-1 rounded text-xs bg-violet-600 hover:bg-violet-700 text-white disabled:opacity-50"
                        >
                          {submitting ? 'Salvando...' : 'Salvar contestação'}
                        </button>
                        <button
                          onClick={() => { setContestingId(null); setContestValue('') }}
                          className="px-3 py-1 rounded text-xs bg-slate-800 hover:bg-slate-700 text-slate-300"
                        >
                          Cancelar
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      ))}

      <div className="mt-6 p-4 rounded border border-amber-800/40 bg-amber-950/10">
        <div className="flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-amber-200/90">
            Cada default foi aplicado com base em citação pública verificável. Se o seu caso difere, use
            "Contestar" — o valor que você escrever substitui o default no CodeGen sem remover a
            rastreabilidade da decisão original.
          </p>
        </div>
      </div>
    </div>
  )
}
