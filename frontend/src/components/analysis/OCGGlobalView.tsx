/**
 * OCGGlobalView — Visualização do parecer consolidado (OCG Global)
 *
 * Mostra resultado da consolidação com indicadores de consenso vs votação
 */

import React, { useState, useEffect } from 'react'
import { Loader, AlertCircle, CheckCircle2, ChevronDown, ChevronUp } from 'lucide-react'
import { useToast } from '@/hooks/useToast'

interface OCGGlobalData {
  ocg_global_id: string
  parecer_consolidated: Record<string, any>
  consensus_fields: string[]
  conflicting_fields: Record<string, Record<string, any>>
  voting_results: Record<string, Record<string, number>>
  consolidated_at: string
}

interface Props {
  projectId: string
  documentId: string
}

export function OCGGlobalView({ projectId, documentId }: Props) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<OCGGlobalData | null>(null)
  const [expandedFields, setExpandedFields] = useState<Set<string>>(new Set())
  const toast = useToast()

  useEffect(() => {
    fetchOCGGlobal()
  }, [projectId, documentId])

  const fetchOCGGlobal = async () => {
    try {
      setLoading(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}/ocg-global`,
        {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        }
      )

      if (response.ok) {
        const ocgData = await response.json()
        setData(ocgData)
      } else if (response.status === 404) {
        // OCG não consolidado ainda
        setData(null)
      } else {
        toast.error('Erro ao carregar OCG Global')
      }
    } catch (error) {
      console.error('Erro ao buscar OCG Global:', error)
      toast.error('Erro ao carregar OCG Global')
    } finally {
      setLoading(false)
    }
  }

  const toggleField = (field: string) => {
    const newExpanded = new Set(expandedFields)
    if (newExpanded.has(field)) {
      newExpanded.delete(field)
    } else {
      newExpanded.add(field)
    }
    setExpandedFields(newExpanded)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader className="h-6 w-6 animate-spin text-emerald-600" />
        <span className="ml-3 text-gray-700">Carregando parecer consolidado...</span>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-amber-900">OCG Global não consolidado</h3>
            <p className="text-sm text-amber-800 mt-1">
              Consolide as análises para gerar um parecer consolidado das 7 personas.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const consensusCount = data.consensus_fields.length
  const conflictCount = Object.keys(data.conflicting_fields).length
  const totalFields = consensusCount + conflictCount

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-2xl font-bold text-gray-900">Parecer Consolidado (OCG Global)</h2>
        <p className="text-sm text-gray-600 mt-2">
          Consolidado em {new Date(data.consolidated_at).toLocaleString('pt-BR')}
        </p>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="text-sm font-medium text-gray-500">Total de Campos</div>
          <div className="text-3xl font-bold text-gray-900 mt-1">{totalFields}</div>
        </div>
        <div className="bg-emerald-50 rounded-lg border border-emerald-200 p-4">
          <div className="text-sm font-medium text-emerald-600">Em Consenso</div>
          <div className="text-3xl font-bold text-emerald-900 mt-1">{consensusCount}</div>
          <p className="text-xs text-emerald-700 mt-1">100% acordo</p>
        </div>
        <div className="bg-amber-50 rounded-lg border border-amber-200 p-4">
          <div className="text-sm font-medium text-amber-600">Divergentes</div>
          <div className="text-3xl font-bold text-amber-900 mt-1">{conflictCount}</div>
          <p className="text-xs text-amber-700 mt-1">Com votação</p>
        </div>
      </div>

      {/* Campos em Consenso */}
      {consensusCount > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="bg-emerald-50 border-b border-emerald-200 px-6 py-4">
            <h3 className="font-semibold text-emerald-900 flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5" />
              Campos em Consenso ({consensusCount})
            </h3>
          </div>
          <div className="p-6 space-y-3">
            {data.consensus_fields.map((field) => (
              <div key={field} className="bg-emerald-50 rounded-lg p-3 border border-emerald-200">
                <p className="font-medium text-emerald-900">{field}</p>
                <p className="text-sm text-emerald-700 mt-1">
                  {typeof data.parecer_consolidated[field] === 'object'
                    ? JSON.stringify(data.parecer_consolidated[field], null, 2)
                    : String(data.parecer_consolidated[field])}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Campos Divergentes */}
      {conflictCount > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="bg-amber-50 border-b border-amber-200 px-6 py-4">
            <h3 className="font-semibold text-amber-900 flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              Campos Divergentes ({conflictCount})
            </h3>
          </div>
          <div className="p-6 space-y-4">
            {Object.entries(data.conflicting_fields).map(([field, personas]) => {
              const isExpanded = expandedFields.has(field)
              const votes = data.voting_results[field] || {}
              const voteCounts = Object.entries(votes).map(([value, count]) => ({
                value: value,
                count: count as number,
              }))

              return (
                <div
                  key={field}
                  className="border border-amber-200 rounded-lg bg-amber-50 overflow-hidden"
                >
                  <button
                    onClick={() => toggleField(field)}
                    className="w-full p-4 flex items-center justify-between hover:bg-amber-100 text-left"
                  >
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900">{field}</h4>
                      <p className="text-sm text-gray-600 mt-1">
                        {Object.keys(personas).length} personas com valores diferentes
                      </p>
                    </div>
                    {isExpanded ? (
                      <ChevronUp className="h-5 w-5 text-amber-600" />
                    ) : (
                      <ChevronDown className="h-5 w-5 text-amber-600" />
                    )}
                  </button>

                  {isExpanded && (
                    <div className="border-t border-amber-200 p-4 space-y-4 bg-white">
                      {/* Voting Results */}
                      <div>
                        <p className="text-sm font-medium text-gray-900 mb-2">Votação</p>
                        <div className="space-y-2">
                          {voteCounts.map(({ value, count }, index) => {
                            let parsedValue: any
                            try {
                              parsedValue = JSON.parse(value)
                            } catch {
                              parsedValue = value
                            }
                            return (
                              <div key={index} className="flex items-center gap-3">
                                <div className="flex-1">
                                  <p className="text-sm text-gray-700 break-words">
                                    {typeof parsedValue === 'object'
                                      ? JSON.stringify(parsedValue)
                                      : String(parsedValue)}
                                  </p>
                                </div>
                                <div className="flex items-center gap-2 whitespace-nowrap">
                                  <div className="h-2 bg-amber-400 rounded-full" style={{ width: `${(count / Math.max(...voteCounts.map(v => v.count))) * 40}px` }}></div>
                                  <span className="text-sm font-medium text-amber-700 w-6 text-right">
                                    {count}
                                  </span>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>

                      {/* Personas */}
                      <div>
                        <p className="text-sm font-medium text-gray-900 mb-2">Posições das Personas</p>
                        <div className="space-y-2">
                          {Object.entries(personas).map(([persona, value]) => (
                            <div key={persona} className="bg-gray-50 rounded p-2">
                              <p className="text-xs font-medium text-gray-700 mb-1">{persona}</p>
                              <p className="text-sm text-gray-600">
                                {typeof value === 'object'
                                  ? JSON.stringify(value, null, 2)
                                  : String(value)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
