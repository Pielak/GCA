/**
 * ComparisonView — Comparação side-by-side de duas análises de personas
 *
 * Mostra campos em comum vs campos divergentes com diferenças destacadas
 */

import React, { useState, useEffect } from 'react'
import { Loader, X, TrendingUp } from 'lucide-react'
import { useToast } from '@/hooks/useToast'

interface ComparisonResponse {
  persona_a: string
  persona_b: string
  fields_matching: string[]
  fields_diverging: Record<string, Record<string, any>>
  similarity_score: number
}

interface Props {
  projectId: string
  documentId: string
  personaAId: string
  personaBId: string
  onClose: () => void
}

export function ComparisonView({ projectId, documentId, personaAId, personaBId, onClose }: Props) {
  const [loading, setLoading] = useState(true)
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null)
  const toast = useToast()

  useEffect(() => {
    fetchComparison()
  }, [personaAId, personaBId])

  const fetchComparison = async () => {
    try {
      setLoading(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}/compare-analyses?persona_a_id=${personaAId}&persona_b_id=${personaBId}`,
        {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        }
      )

      if (response.ok) {
        const data = await response.json()
        setComparison(data)
      } else {
        toast.error('Erro ao carregar comparação')
      }
    } catch (error) {
      console.error('Erro ao buscar comparação:', error)
      toast.error('Erro ao carregar comparação')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-8 w-full max-w-4xl mx-4">
          <div className="flex items-center justify-center gap-3">
            <Loader className="h-6 w-6 animate-spin text-emerald-600" />
            <span className="text-gray-700">Carregando comparação...</span>
          </div>
        </div>
      </div>
    )
  }

  if (!comparison) {
    return null
  }

  const getSimilarityColor = (score: number) => {
    if (score >= 0.8) return 'text-emerald-600'
    if (score >= 0.6) return 'text-amber-600'
    return 'text-red-600'
  }

  const getSimilarityBg = (score: number) => {
    if (score >= 0.8) return 'bg-emerald-50 border-emerald-200'
    if (score >= 0.6) return 'bg-amber-50 border-amber-200'
    return 'bg-red-50 border-red-200'
  }

  const formatValue = (value: any) => {
    if (Array.isArray(value)) {
      return value.join(', ')
    }
    if (typeof value === 'object' && value !== null) {
      return JSON.stringify(value, null, 2)
    }
    return String(value)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg w-full max-w-6xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 p-6 flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Comparação de Análises</h2>
            <p className="text-sm text-gray-600 mt-1">
              {comparison.persona_a} vs {comparison.persona_b}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg text-gray-500 hover:text-gray-700"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Similarity Score */}
        <div className={`m-6 p-4 rounded-lg border-2 ${getSimilarityBg(comparison.similarity_score)}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className={`h-5 w-5 ${getSimilarityColor(comparison.similarity_score)}`} />
              <span className="font-medium text-gray-900">Índice de Similaridade</span>
            </div>
            <span className={`text-2xl font-bold ${getSimilarityColor(comparison.similarity_score)}`}>
              {(comparison.similarity_score * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-xs text-gray-600 mt-2">
            {comparison.fields_matching.length} campo(s) em comum ·{' '}
            {Object.keys(comparison.fields_diverging).length} campo(s) divergente(s)
          </p>
        </div>

        {/* Content */}
        <div className="space-y-6 px-6 pb-6">
          {/* Campos em Comum */}
          {comparison.fields_matching.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <span className="w-2 h-2 bg-emerald-600 rounded-full"></span>
                Campos em Comum ({comparison.fields_matching.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {comparison.fields_matching.map((field) => (
                  <div key={field} className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
                    <p className="text-sm font-medium text-emerald-900">{field}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Campos Divergentes */}
          {Object.keys(comparison.fields_diverging).length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <span className="w-2 h-2 bg-red-600 rounded-full"></span>
                Campos Divergentes ({Object.keys(comparison.fields_diverging).length})
              </h3>
              <div className="space-y-4">
                {Object.entries(comparison.fields_diverging).map(([field, values]) => (
                  <div key={field} className="border border-gray-200 rounded-lg overflow-hidden">
                    <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
                      <h4 className="font-medium text-gray-900">{field}</h4>
                    </div>
                    <div className="grid grid-cols-2 divide-x divide-gray-200">
                      {/* Persona A */}
                      <div className="p-4">
                        <p className="text-xs font-medium text-gray-500 uppercase mb-2">
                          {comparison.persona_a}
                        </p>
                        <div className="bg-blue-50 rounded p-3 min-h-[60px]">
                          <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">
                            {formatValue(values[comparison.persona_a])}
                          </p>
                        </div>
                      </div>

                      {/* Persona B */}
                      <div className="p-4">
                        <p className="text-xs font-medium text-gray-500 uppercase mb-2">
                          {comparison.persona_b}
                        </p>
                        <div className="bg-purple-50 rounded p-3 min-h-[60px]">
                          <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">
                            {formatValue(values[comparison.persona_b])}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {comparison.fields_matching.length === 0 && Object.keys(comparison.fields_diverging).length === 0 && (
            <div className="text-center py-8">
              <p className="text-gray-600">Nenhum campo para comparar</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
