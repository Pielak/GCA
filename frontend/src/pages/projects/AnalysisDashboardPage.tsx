/**
 * AnalysisDashboardPage — Visualização consolidada de análises de personas
 *
 * Mostra:
 * - 7 análises de personas lado-a-lado
 * - Comparação entre análises
 * - Histórico de refinements
 * - Consensus vs conflitos
 */

import React, { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Loader, ChevronDown, ChevronUp, AlertCircle, CheckCircle2, GitCompare } from 'lucide-react'
import { useToast } from '@/hooks/useToast'
import { ComparisonView } from '@/components/analysis/ComparisonView'
import { RefinementTimeline } from '@/components/analysis/RefinementTimeline'
import { OCGGlobalView } from '@/components/analysis/OCGGlobalView'

interface PersonaAnalysis {
  persona_id: string
  persona_name: string
  status: string
  parecer: Record<string, any>
  ai_provider: string | null
  ai_model: string | null
  created_at: string
  completed_at: string | null
  follow_up_count: number
  refined_iteration: number | null
}

interface AnalysisDashboard {
  document_id: string
  document_name: string
  total_personas: number
  analyses: PersonaAnalysis[]
  ocg_global: Record<string, any> | null
  statistics: {
    total_analyses: number
    completed_count: number
    pending_count: number
    with_follow_up: number
    with_refinement: number
    criticality_distribution: Record<string, number>
  }
}

interface Refinement {
  iteration: number
  parecer_refined: Record<string, any>
  changed_fields: string[]
  change_summary: string
  created_at: string
}

interface RefinementHistory {
  ocg_individual_id: string
  persona_name: string
  original_parecer: Record<string, any>
  refinements: Refinement[]
  total_iterations: number
}

export function AnalysisDashboardPage() {
  const { projectId, documentId } = useParams<{ projectId: string; documentId: string }>()
  const [loading, setLoading] = useState(true)
  const [dashboard, setDashboard] = useState<AnalysisDashboard | null>(null)
  const [expandedPersona, setExpandedPersona] = useState<string | null>(null)
  const [refinementHistory, setRefinementHistory] = useState<Record<string, RefinementHistory>>({})
  const [selectedForComparison, setSelectedForComparison] = useState<string[]>([])
  const [currentTab, setCurrentTab] = useState<'analyses' | 'consolidated'>('analyses')
  const toast = useToast()

  useEffect(() => {
    fetchDashboard()
  }, [projectId, documentId])

  const fetchDashboard = async () => {
    try {
      setLoading(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}/analysis-dashboard`,
        {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        }
      )

      if (response.ok) {
        const data = await response.json()
        setDashboard(data)
      } else {
        toast.error('Erro ao carregar dashboard de análises')
      }
    } catch (error) {
      console.error('Erro ao buscar dashboard:', error)
      toast.error('Erro ao carregar dashboard')
    } finally {
      setLoading(false)
    }
  }

  const fetchRefinementHistory = async (ocgId: string) => {
    try {
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}/ocg/${ocgId}/refinement-history`,
        {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        }
      )

      if (response.ok) {
        const data = await response.json()
        setRefinementHistory((prev) => ({ ...prev, [ocgId]: data }))
      }
    } catch (error) {
      console.error('Erro ao buscar histórico de refinements:', error)
    }
  }

  const togglePersonaExpand = async (personaId: string) => {
    if (expandedPersona === personaId) {
      setExpandedPersona(null)
    } else {
      setExpandedPersona(personaId)
      // Carregar histórico se não estiver em cache
      if (!refinementHistory[personaId]) {
        await fetchRefinementHistory(personaId)
      }
    }
  }

  const toggleComparison = (personaId: string) => {
    setSelectedForComparison((prev) => {
      if (prev.includes(personaId)) {
        return prev.filter((p) => p !== personaId)
      } else if (prev.length < 2) {
        return [...prev, personaId]
      } else {
        return [prev[1], personaId]
      }
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader className="h-6 w-6 animate-spin text-emerald-600" />
        <span className="ml-3 text-gray-700">Carregando análises...</span>
      </div>
    )
  }

  if (!dashboard) {
    return (
      <div className="flex items-center justify-center p-8">
        <AlertCircle className="h-6 w-6 text-amber-600 mr-2" />
        <span className="text-gray-700">Nenhuma análise disponível</span>
      </div>
    )
  }

  const stats = dashboard.statistics
  const criticityColor = (level: string) => {
    const colors: Record<string, string> = {
      BAIXA: 'bg-blue-50 border-blue-200 text-blue-900',
      MEDIA: 'bg-amber-50 border-amber-200 text-amber-900',
      ALTA: 'bg-red-50 border-red-200 text-red-900',
    }
    return colors[level] || 'bg-gray-50 border-gray-200 text-gray-900'
  }

  const getCriticalityBadgeColor = (criticality: string) => {
    const colors: Record<string, string> = {
      BAIXA: 'bg-blue-100 text-blue-800',
      MEDIA: 'bg-amber-100 text-amber-800',
      ALTA: 'bg-red-100 text-red-800',
    }
    return colors[criticality] || 'bg-gray-100 text-gray-800'
  }

  return (
    <div className="space-y-6">
      {/* Comparison Modal */}
      {selectedForComparison.length === 2 && (
        <ComparisonView
          projectId={projectId!}
          documentId={documentId!}
          personaAId={selectedForComparison[0]}
          personaBId={selectedForComparison[1]}
          onClose={() => setSelectedForComparison([])}
        />
      )}

      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h1 className="text-3xl font-bold text-gray-900">{dashboard.document_name}</h1>
        <p className="text-sm text-gray-600 mt-2">Análise consolidada de {dashboard.total_personas} personas</p>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="text-sm font-medium text-gray-500">Total de Análises</div>
          <div className="text-2xl font-bold text-gray-900 mt-1">{stats.total_analyses}</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="text-sm font-medium text-gray-500">Concluídas</div>
          <div className="text-2xl font-bold text-emerald-600 mt-1">{stats.completed_count}</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="text-sm font-medium text-gray-500">Com Follow-up</div>
          <div className="text-2xl font-bold text-blue-600 mt-1">{stats.with_follow_up}</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="text-sm font-medium text-gray-500">Refinadas</div>
          <div className="text-2xl font-bold text-purple-600 mt-1">{stats.with_refinement}</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="text-sm font-medium text-gray-500">Criticidade Média</div>
          <div className="flex gap-1 mt-2">
            <span className={`text-xs px-2 py-1 rounded ${getCriticalityBadgeColor('BAIXA')}`}>
              {stats.criticality_distribution.BAIXA || 0}
            </span>
            <span className={`text-xs px-2 py-1 rounded ${getCriticalityBadgeColor('MEDIA')}`}>
              {stats.criticality_distribution.MEDIA || 0}
            </span>
            <span className={`text-xs px-2 py-1 rounded ${getCriticalityBadgeColor('ALTA')}`}>
              {stats.criticality_distribution.ALTA || 0}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-gray-200">
        <button
          onClick={() => setCurrentTab('analyses')}
          className={`px-4 py-3 font-medium transition-colors ${
            currentTab === 'analyses'
              ? 'text-emerald-600 border-b-2 border-emerald-600'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          Análises Individuais
        </button>
        <button
          onClick={() => setCurrentTab('consolidated')}
          className={`px-4 py-3 font-medium transition-colors ${
            currentTab === 'consolidated'
              ? 'text-emerald-600 border-b-2 border-emerald-600'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          Parecer Consolidado
        </button>
      </div>

      {/* Personas Grid */}
      {currentTab === 'analyses' && (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Análises de Personas</h2>
          {selectedForComparison.length === 2 && (
            <button className="flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100">
              <GitCompare className="h-4 w-4" />
              Comparar ({selectedForComparison.length})
            </button>
          )}
        </div>

        {dashboard.analyses.map((analysis) => (
          <div key={analysis.persona_id} className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            {/* Persona Header */}
            <div
              className="p-4 bg-gray-50 border-b border-gray-200 cursor-pointer hover:bg-gray-100 flex items-start justify-between"
              onClick={() => togglePersonaExpand(analysis.persona_id)}
            >
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <h3 className="font-semibold text-gray-900">{analysis.persona_name}</h3>
                  <span className={`text-xs px-2 py-1 rounded-full ${getCriticalityBadgeColor(analysis.parecer?.criticidade || 'MEDIA')}`}>
                    {analysis.parecer?.criticidade || 'MEDIA'}
                  </span>
                  {analysis.status === 'completed' && (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
                  )}
                </div>
                <p className="text-xs text-gray-600 mt-1">
                  {analysis.ai_model && `${analysis.ai_provider} - ${analysis.ai_model}`}
                </p>
              </div>

              <div className="flex items-center gap-2">
                {analysis.refined_iteration && (
                  <span className="text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded">
                    Refinada v{analysis.refined_iteration}
                  </span>
                )}
                {analysis.follow_up_count > 0 && (
                  <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                    {analysis.follow_up_count} perguntas
                  </span>
                )}
                <label className="flex items-center gap-2 ml-3">
                  <input
                    type="checkbox"
                    checked={selectedForComparison.includes(analysis.persona_id)}
                    onChange={() => toggleComparison(analysis.persona_id)}
                    onClick={(e) => e.stopPropagation()}
                    className="w-4 h-4 rounded"
                  />
                </label>
                {expandedPersona === analysis.persona_id ? (
                  <ChevronUp className="h-4 w-4 text-gray-600" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-gray-600" />
                )}
              </div>
            </div>

            {/* Persona Content — Expandable */}
            {expandedPersona === analysis.persona_id && (
              <div className="p-4 space-y-4">
                {/* Main Parecer */}
                <div>
                  <h4 className="font-medium text-gray-900 mb-2">Parecer Técnico</h4>
                  <div className="bg-gray-50 rounded-lg p-3 space-y-2 text-sm">
                    {analysis.parecer?.parecer && (
                      <p className="text-gray-700 whitespace-pre-wrap">{analysis.parecer.parecer}</p>
                    )}
                  </div>
                </div>

                {/* Riscos/Recomendações */}
                {(analysis.parecer?.riscos || analysis.parecer?.vulnerabilidades) && (
                  <div>
                    <h4 className="font-medium text-gray-900 mb-2">Riscos</h4>
                    <ul className="space-y-1">
                      {(analysis.parecer?.riscos || analysis.parecer?.vulnerabilidades || []).map((risk: string, i: number) => (
                        <li key={i} className="text-sm text-gray-700 flex gap-2">
                          <span className="text-red-600">•</span> {risk}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {(analysis.parecer?.recomendacoes || analysis.parecer?.mitigacoes) && (
                  <div>
                    <h4 className="font-medium text-gray-900 mb-2">Recomendações</h4>
                    <ul className="space-y-1">
                      {(analysis.parecer?.recomendacoes || analysis.parecer?.mitigacoes || []).map((rec: string, i: number) => (
                        <li key={i} className="text-sm text-gray-700 flex gap-2">
                          <span className="text-emerald-600">✓</span> {rec}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Refinement Timeline */}
                {refinementHistory[analysis.persona_id] && (
                  <RefinementTimeline
                    originalParecer={refinementHistory[analysis.persona_id].original_parecer}
                    refinements={refinementHistory[analysis.persona_id].refinements}
                  />
                )}

                {/* Metadata */}
                <div className="border-t border-gray-200 pt-4 text-xs text-gray-600 space-y-1">
                  <p>Criado em: {new Date(analysis.created_at).toLocaleString('pt-BR')}</p>
                  {analysis.completed_at && (
                    <p>Concluído em: {new Date(analysis.completed_at).toLocaleString('pt-BR')}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      )}

      {/* Consolidated Tab */}
      {currentTab === 'consolidated' && (
        <OCGGlobalView projectId={projectId!} documentId={documentId!} />
      )}
    </div>
  )
}
