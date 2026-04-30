/**
 * PilaresVivosView — Visualização elegante do documento vivo com análise de 7 personas
 *
 * Mostra resultado da consolidação com abas por persona.
 * Cada seção contém análise, DTs, status e recomendações estruturadas.
 */

import React, { useEffect, useState } from 'react'
import {
  Loader,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Download,
  Copy,
} from 'lucide-react'
import { usePilaresVivos } from '@/hooks/usePilaresVivos'
import { exportarMarkdown, exportarPDF, copiarParaClipboard } from '@/lib/pilares-export'
import { useToast } from '@/hooks/useToast'

interface Props {
  projectId: string
}

const PERSONAS_INFO = {
  P4_Arquiteto: { label: 'Arquiteto', color: 'emerald', icon: '🏗️' },
  P1_DBA: { label: 'DBA', color: 'blue', icon: '💾' },
  P2_Compliance: { label: 'Compliance', color: 'purple', icon: '⚖️' },
  P3_Seguranca: { label: 'Segurança', color: 'red', icon: '🔒' },
  P5_Dev: { label: 'Desenvolvimento', color: 'cyan', icon: '💻' },
  P6_Tester: { label: 'Tester', color: 'amber', icon: '🧪' },
  P7_QA: { label: 'QA', color: 'green', icon: '✓' },
}

const PERSONAS_ORDER = ['P4_Arquiteto', 'P1_DBA', 'P2_Compliance', 'P3_Seguranca', 'P5_Dev', 'P6_Tester', 'P7_QA']

export function PilaresVivosView({ projectId }: Props) {
  const { data, loading, error, inicializar, regenerar } = usePilaresVivos(projectId)
  const [regenerando, setRegenerando] = useState(false)
  const [selectedPersona, setSelectedPersona] = useState('P4_Arquiteto')
  const [expandedDTs, setExpandedDTs] = useState<Set<string>>(new Set())
  const [exportOpen, setExportOpen] = useState(false)
  const toast = useToast()

  useEffect(() => {
    inicializar()
  }, [projectId, inicializar])

  const handleRegenerar = async () => {
    try {
      setRegenerando(true)
      await regenerar()
    } finally {
      setRegenerando(false)
    }
  }

  const toggleDT = (dtId: string) => {
    const newExpanded = new Set(expandedDTs)
    if (newExpanded.has(dtId)) {
      newExpanded.delete(dtId)
    } else {
      newExpanded.add(dtId)
    }
    setExpandedDTs(newExpanded)
  }

  const handleExportMarkdown = () => {
    if (!data) return
    exportarMarkdown(data, 'Projeto')
    toast.success('Markdown exportado com sucesso')
    setExportOpen(false)
  }

  const handleExportPDF = () => {
    if (!data) return
    exportarPDF(data, 'Projeto')
    toast.success('PDF aberto para impressão')
    setExportOpen(false)
  }

  const handleCopyClipboard = () => {
    if (!data) return
    copiarParaClipboard(data, 'Projeto')
    toast.success('Copiado para clipboard')
    setExportOpen(false)
  }

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader className="h-8 w-8 animate-spin text-emerald-600" />
        <span className="ml-4 text-gray-700 text-lg">Carregando Pilares Vivos...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <div className="flex items-start gap-4">
          <AlertCircle className="h-6 w-6 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-red-900">Erro ao carregar Pilares Vivos</h3>
            <p className="text-sm text-red-800 mt-1">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-6">
        <div className="flex items-start gap-4">
          <AlertTriangle className="h-6 w-6 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-amber-900">Pilares Vivos não gerado</h3>
            <p className="text-sm text-amber-800 mt-2">
              Para iniciar a análise consolidada das 7 personas, clique no botão abaixo.
              Isso levará ~45-60 segundos (chamadas paralelas ao LLM).
            </p>
            <button
              onClick={handleRegenerar}
              disabled={regenerando}
              className="mt-4 inline-flex items-center gap-2 px-6 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 text-sm font-medium transition-colors"
            >
              {regenerando ? (
                <>
                  <Loader className="h-4 w-4 animate-spin" />
                  Gerando Pilares Vivos...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Gerar Pilares Vivos
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    )
  }

  const currentPersona = selectedPersona as keyof typeof PERSONAS_INFO
  const currentParecer = data.documento[selectedPersona]
  const info = PERSONAS_INFO[currentPersona]

  // Estatísticas
  const totalPersonas = PERSONAS_ORDER.length
  const completasCount = PERSONAS_ORDER.filter(
    (p) => data.documento[p]?.status === 'completo'
  ).length
  const comErroCount = PERSONAS_ORDER.filter(
    (p) => data.documento[p]?.status === 'erro'
  ).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-emerald-50 to-cyan-50 border border-emerald-200 rounded-lg p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-emerald-900">Pilares Vivos</h1>
            <p className="text-sm text-emerald-700 mt-2">
              Análise consolidada das 7 personas sobre arquitetura do projeto
            </p>
            {data.gerado_em && (
              <p className="text-xs text-emerald-600 mt-3">
                🕐 Gerado em {new Date(data.gerado_em).toLocaleString('pt-BR')}
                {data.regenerado_em && (
                  <> • Atualizado {new Date(data.regenerado_em).toLocaleString('pt-BR')}</>
                )}
              </p>
            )}
          </div>
          <div className="flex gap-3">
            {/* Menu de Export */}
            <div className="relative">
              <button
                onClick={() => setExportOpen(!exportOpen)}
                className="inline-flex items-center gap-2 px-4 py-3 bg-white border border-emerald-200 text-emerald-600 rounded-lg hover:bg-emerald-50 font-medium transition-colors"
              >
                <Download className="h-4 w-4" />
                Exportar
              </button>
              {exportOpen && (
                <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 z-10">
                  <button
                    onClick={handleExportMarkdown}
                    className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 transition-colors first:rounded-t-lg"
                  >
                    📄 Exportar como Markdown
                  </button>
                  <button
                    onClick={handleExportPDF}
                    className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                  >
                    🖨️ Exportar como PDF
                  </button>
                  <button
                    onClick={handleCopyClipboard}
                    className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 transition-colors last:rounded-b-lg"
                  >
                    <Copy className="h-4 w-4 inline mr-2" />
                    Copiar para Clipboard
                  </button>
                </div>
              )}
            </div>

            {/* Botão Regenerar */}
            <button
              onClick={handleRegenerar}
              disabled={regenerando}
              className="inline-flex items-center gap-2 px-6 py-3 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 font-medium transition-colors"
            >
              {regenerando ? (
                <>
                  <Loader className="h-4 w-4 animate-spin" />
                  Regenerando...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Regenerar Análise
                </>
              )}
            </button>
          </div>
        </div>

        {/* Estatísticas */}
        <div className="grid grid-cols-3 gap-4 mt-6">
          <div className="bg-white rounded p-3 border border-emerald-100">
            <p className="text-xs text-gray-600">Análises Completas</p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">
              {completasCount}/{totalPersonas}
            </p>
          </div>
          <div className="bg-white rounded p-3 border border-amber-100">
            <p className="text-xs text-gray-600">Total de Personas</p>
            <p className="text-2xl font-bold text-amber-600 mt-1">{totalPersonas}</p>
          </div>
          <div className="bg-white rounded p-3 border border-red-100">
            <p className="text-xs text-gray-600">Com Erros</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{comErroCount}</p>
          </div>
        </div>
      </div>

      {/* Tabs de Personas */}
      <div className="border-b border-gray-200">
        <div className="flex gap-1 overflow-x-auto">
          {PERSONAS_ORDER.map((persona) => {
            const personaInfo = PERSONAS_INFO[persona as keyof typeof PERSONAS_INFO]
            const parecer = data.documento[persona]
            const isSelected = selectedPersona === persona
            const isComplete = parecer?.status === 'completo'
            const hasError = parecer?.status === 'erro'

            return (
              <button
                key={persona}
                onClick={() => setSelectedPersona(persona)}
                className={`px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap border-b-2 ${
                  isSelected
                    ? 'border-emerald-600 text-emerald-600 bg-emerald-50'
                    : 'border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                } ${hasError ? 'text-red-600' : isComplete ? 'text-emerald-600' : 'text-gray-600'}`}
              >
                <span className="mr-2">{personaInfo.icon}</span>
                {personaInfo.label}
                {isComplete && <CheckCircle2 className="h-4 w-4 inline ml-1" />}
                {hasError && <AlertCircle className="h-4 w-4 inline ml-1 text-red-600" />}
              </button>
            )
          })}
        </div>
      </div>

      {/* Conteúdo da Persona Selecionada */}
      {currentParecer ? (
        <div className="space-y-4">
          {/* Status Card */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <div className="flex items-start justify-between mb-4">
              <h2 className="text-2xl font-bold text-gray-900">
                {info.label} {info.icon}
              </h2>
              <div className="text-right">
                <p className="text-xs text-gray-500">Status</p>
                <p className={`text-sm font-semibold mt-1 ${
                  currentParecer.status === 'completo' ? 'text-emerald-600' :
                  currentParecer.status === 'erro' ? 'text-red-600' :
                  'text-amber-600'
                }`}>
                  {currentParecer.status === 'completo' ? '✓ Completo' :
                   currentParecer.status === 'erro' ? '✗ Erro' :
                   '⊙ Processando'}
                </p>
              </div>
            </div>

            {/* Parecer/Análise */}
            {currentParecer.parecer && (
              <div className="bg-gray-50 rounded p-4 text-sm text-gray-700 space-y-3">
                {typeof currentParecer.parecer === 'object' ? (
                  <details className="cursor-pointer">
                    <summary className="font-medium text-gray-900 hover:text-gray-700">
                      📋 Parecer Completo (clique para expandir)
                    </summary>
                    <pre className="mt-3 bg-white rounded p-3 overflow-auto max-h-64 text-xs border border-gray-200">
                      {JSON.stringify(currentParecer.parecer, null, 2)}
                    </pre>
                  </details>
                ) : (
                  <p className="whitespace-pre-wrap">{String(currentParecer.parecer)}</p>
                )}
              </div>
            )}

            {currentParecer.analise_texto && (
              <p className="mt-4 text-gray-700 text-sm">{currentParecer.analise_texto}</p>
            )}
          </div>

          {/* Discovery Tasks */}
          {currentParecer.dts && currentParecer.dts.length > 0 && (
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Discovery Tasks ({currentParecer.dts.length})
              </h3>
              <div className="space-y-3">
                {currentParecer.dts.map((dt: any, idx: number) => {
                  const dtId = `${selectedPersona}-dt-${idx}`
                  const isExpanded = expandedDTs.has(dtId)
                  const dtData = typeof dt === 'string' ? { descricao: dt } : dt

                  return (
                    <div
                      key={dtId}
                      className="border border-gray-200 rounded-lg overflow-hidden"
                    >
                      <button
                        onClick={() => toggleDT(dtId)}
                        className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 text-left transition-colors"
                      >
                        <div className="flex-1">
                          <p className="font-medium text-gray-900">
                            {dtData.id || dtData.titulo || `Task ${idx + 1}`}
                          </p>
                          {dtData.descricao && (
                            <p className="text-sm text-gray-600 mt-1 line-clamp-1">
                              {dtData.descricao}
                            </p>
                          )}
                        </div>
                        {isExpanded ? (
                          <ChevronUp className="h-5 w-5 text-gray-400" />
                        ) : (
                          <ChevronDown className="h-5 w-5 text-gray-400" />
                        )}
                      </button>

                      {isExpanded && (
                        <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 text-sm space-y-2">
                          {dtData.impacto && (
                            <p>
                              <span className="font-medium text-gray-900">Impacto:</span>{' '}
                              <span className={`px-2 py-1 rounded text-xs font-medium ${
                                dtData.impacto === 'BLOCKER' ? 'bg-red-100 text-red-800' :
                                dtData.impacto === 'CRITICAL' ? 'bg-orange-100 text-orange-800' :
                                dtData.impacto === 'WARNING' ? 'bg-yellow-100 text-yellow-800' :
                                'bg-blue-100 text-blue-800'
                              }`}>
                                {dtData.impacto}
                              </span>
                            </p>
                          )}
                          {dtData.descricao && (
                            <p>
                              <span className="font-medium text-gray-900">Descrição:</span>{' '}
                              {dtData.descricao}
                            </p>
                          )}
                          {dtData.recomendacao && (
                            <p>
                              <span className="font-medium text-gray-900">Recomendação:</span>{' '}
                              {dtData.recomendacao}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {(!currentParecer.dts || currentParecer.dts.length === 0) && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
              <p className="text-sm text-emerald-800">
                ✓ Nenhuma discovery task pendente para {info.label}
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-6">
          <p className="text-center text-gray-600">
            Selecione uma persona para visualizar análise
          </p>
        </div>
      )}
    </div>
  )
}
