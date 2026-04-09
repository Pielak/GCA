import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { BookOpen, RefreshCw, Loader2, CheckCircle, Clock, AlertTriangle, FileText } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface DocSection {
  id: string
  title: string
  status: string
  lastGen: string | null
  source: string
  wordCount: number
}

const STATUS_CONFIG: Record<string, { label: string; cls: string }> = {
  published: { label: 'Publicado', cls: 'bg-emerald-900/40 text-emerald-400' },
  outdated: { label: 'Desatualizado', cls: 'bg-amber-900/40 text-amber-400' },
  pending: { label: 'Pendente', cls: 'bg-slate-800 text-slate-500' },
  draft: { label: 'Rascunho', cls: 'bg-blue-900/40 text-blue-400' },
  generating: { label: 'Gerando...', cls: 'bg-violet-900/40 text-violet-400' },
}

// Seções derivadas do OCG quando nenhuma doc real existe ainda
const OCG_DERIVED_SECTIONS = [
  { key: 'PROJECT_PROFILE', title: 'Perfil do Projeto', icon: '📋' },
  { key: 'STACK_RECOMMENDATION', title: 'Stack Tecnológica', icon: '⚙️' },
  { key: 'ARCHITECTURE_OVERVIEW', title: 'Visão Arquitetural', icon: '🏗️' },
  { key: 'COMPLIANCE_CHECKLIST', title: 'Conformidade e Regulatório', icon: '🔒' },
  { key: 'TESTING_REQUIREMENTS', title: 'Estratégia de Testes', icon: '🧪' },
  { key: 'RISK_ANALYSIS', title: 'Análise de Riscos', icon: '⚠️' },
  { key: 'DELIVERABLES', title: 'Entregáveis', icon: '📦' },
]

export function LiveDocsPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [sections, setSections] = useState<DocSection[]>([])
  const [ocgSections, setOcgSections] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  const loadData = useCallback(async () => {
    if (!projectId) return
    try {
      const [docsRes, ocgRes] = await Promise.all([
        apiClient.get(`/projects/${projectId}/docs`).catch(() => ({ data: { sections: [] } })),
        apiClient.get(`/projects/${projectId}/ocg`).catch(() => ({ data: {} })),
      ])

      setSections(docsRes.data?.sections || [])

      // Derivar seções do OCG se não há docs reais
      const ocg = ocgRes.data?.ocg
      if (ocg && ocg.ocg_data) {
        const data = typeof ocg.ocg_data === 'string' ? JSON.parse(ocg.ocg_data) : ocg.ocg_data
        const derived = OCG_DERIVED_SECTIONS
          .filter(s => {
            const val = data[s.key]
            return val && (typeof val === 'object' ? Object.keys(val).length > 0 : true)
          })
          .map(s => ({
            ...s,
            hasContent: true,
            status: 'pending',
          }))
        setOcgSections(derived)
      }
    } catch { /* ignore */ }
    setLoading(false)
  }, [projectId])

  useEffect(() => { loadData() }, [loadData])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await apiClient.post(`/projects/${projectId}/docs/refresh`)
      showToast('Documentação regenerada com sucesso', 'success')
      await loadData()
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao regenerar documentação', 'error')
    }
    setRefreshing(false)
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>

  const hasDocs = sections.length > 0
  const published = sections.filter(s => s.status === 'published').length
  const pending = sections.filter(s => s.status === 'pending').length

  return (
    <div className="p-6 space-y-6">
      {toast && (
        <div className={`p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
          {toast.message}
        </div>
      )}

      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Documentação Viva</h2>
          <p className="text-slate-500 text-sm mt-0.5">
            Documentação gerada e atualizada automaticamente a partir do OCG do projeto.
            Toda mudança no OCG dispara regeneração.
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-2 bg-violet-600/20 border border-violet-600/30 text-violet-400 text-sm rounded-lg hover:bg-violet-600/30 disabled:opacity-40 transition-colors"
        >
          {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Regenerar
        </button>
      </div>

      {/* Stats */}
      {hasDocs && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-center">
            <p className="text-2xl font-semibold text-slate-100">{sections.length}</p>
            <p className="text-slate-500 text-xs mt-1">Total de seções</p>
          </div>
          <div className="bg-emerald-950/20 border border-emerald-800/30 rounded-xl p-4 text-center">
            <p className="text-2xl font-semibold text-emerald-400">{published}</p>
            <p className="text-slate-500 text-xs mt-1">Publicadas</p>
          </div>
          <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-4 text-center">
            <p className="text-2xl font-semibold text-amber-400">{pending}</p>
            <p className="text-slate-500 text-xs mt-1">Pendentes</p>
          </div>
        </div>
      )}

      {/* Seções de documentação real */}
      {hasDocs ? (
        <div className="space-y-3">
          {sections.map(doc => {
            const st = STATUS_CONFIG[doc.status] || STATUS_CONFIG.pending
            return (
              <div key={doc.id} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <FileText className="w-5 h-5 text-slate-500" />
                    <div>
                      <p className="text-slate-200 text-sm font-medium">{doc.title}</p>
                      <p className="text-slate-500 text-xs mt-0.5">
                        Fonte: {doc.source} · {doc.wordCount > 0 ? `${doc.wordCount} palavras` : 'Sem conteúdo'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${st.cls}`}>{st.label}</span>
                    {doc.lastGen && <span className="text-slate-600 text-xs">{new Date(doc.lastGen).toLocaleDateString('pt-BR')}</span>}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        /* Seções derivadas do OCG (quando não há docs reais) */
        <div className="space-y-4">
          <div className="bg-slate-900/50 border border-slate-800/50 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <BookOpen className="w-4 h-4 text-violet-400" />
              <h3 className="text-slate-300 text-sm font-semibold">Seções disponíveis no OCG</h3>
            </div>
            <p className="text-slate-500 text-xs mb-4">
              Estas seções serão transformadas em documentação formal quando o botão "Regenerar" for acionado.
              A documentação é criada a partir do conteúdo do OCG.
            </p>

            {ocgSections.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {ocgSections.map(s => (
                  <div key={s.key} className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                    <span className="text-lg">{s.icon}</span>
                    <div>
                      <p className="text-slate-200 text-sm">{s.title}</p>
                      <p className="text-slate-500 text-xs flex items-center gap-1">
                        <CheckCircle className="w-3 h-3 text-emerald-500" />
                        Conteúdo disponível no OCG
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6">
                <AlertTriangle className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-slate-500 text-sm">OCG ainda não possui conteúdo suficiente para gerar documentação.</p>
                <p className="text-slate-600 text-xs mt-1">Ingira documentos e aguarde a análise do Arguidor.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
