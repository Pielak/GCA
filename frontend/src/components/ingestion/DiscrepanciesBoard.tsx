/**
 * DiscrepanciesBoard — Visualização e resolução de conflitos entre personas
 *
 * Mostra:
 * - Lista de conflitos detectados (não resolvidos)
 * - Detalhe de cada conflito (personas divergentes, valores propostos)
 * - Opções para resolver (aceitar consolidado ou override)
 */

import React, { useState, useEffect } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  AlertOctagon,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader,
} from 'lucide-react'
import { useToast } from '@/hooks/useToast'

interface ConflictingValue {
  [persona: string]: string
}

interface Discrepancy {
  id: string
  project_id: string
  field_path: string
  conflicting_personas: string[]
  conflicting_values: ConflictingValue
  severity: 'low' | 'medium' | 'high' | 'critical'
  category: string | null
  status: 'unresolved' | 'voted' | 'overridden' | 'resolved' | 'arbitrated'
  context: string | null
  created_at: string
}

interface DiscrepancyListResponse {
  total: number
  unresolved: number
  resolved: number
  items: Discrepancy[]
}

interface Props {
  projectId: string
  documentId?: string
  onClose?: () => void
}

const severityConfig = {
  low: {
    icon: AlertCircle,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    badge: 'bg-blue-100 text-blue-800',
  },
  medium: {
    icon: AlertTriangle,
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-50',
    borderColor: 'border-yellow-200',
    badge: 'bg-yellow-100 text-yellow-800',
  },
  high: {
    icon: AlertTriangle,
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
    badge: 'bg-orange-100 text-orange-800',
  },
  critical: {
    icon: AlertOctagon,
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    badge: 'bg-red-100 text-red-800',
  },
}

export function DiscrepanciesBoard({ projectId, documentId, onClose }: Props) {
  const [discrepancies, setDiscrepancies] = useState<DiscrepancyListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [resolving, setResolving] = useState<string | null>(null)
  const [selectedValue, setSelectedValue] = useState<{ [key: string]: string }>({})
  const [notes, setNotes] = useState<{ [key: string]: string }>({})
  const toast = useToast()

  useEffect(() => {
    fetchDiscrepancies()
  }, [projectId])

  const fetchDiscrepancies = async () => {
    try {
      setLoading(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/discrepancies?status_filter=unresolved`,
        {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        }
      )
      const data = await response.json()
      setDiscrepancies(data)
    } catch (error) {
      console.error('Erro ao buscar discrepâncias:', error)
      toast.error('Erro ao carregar conflitos')
    } finally {
      setLoading(false)
    }
  }

  const handleResolve = async (discrepancyId: string) => {
    const selected = selectedValue[discrepancyId]
    if (!selected) {
      toast.warning('Selecione um valor antes de resolver')
      return
    }

    try {
      setResolving(discrepancyId)
      const response = await fetch(
        `/api/v1/projects/${projectId}/discrepancies/${discrepancyId}/resolve`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
          body: JSON.stringify({
            resolved_value: selected,
            resolution_notes: notes[discrepancyId] || null,
          }),
        }
      )

      if (response.ok) {
        toast.success('Conflito resolvido com sucesso')
        fetchDiscrepancies()
        setSelectedValue({ ...selectedValue, [discrepancyId]: '' })
        setNotes({ ...notes, [discrepancyId]: '' })
      } else {
        toast.error('Erro ao resolver conflito')
      }
    } catch (error) {
      console.error('Erro ao resolver:', error)
      toast.error('Erro ao resolver conflito')
    } finally {
      setResolving(null)
    }
  }

  const handleAccept = async (discrepancyId: string) => {
    try {
      setResolving(discrepancyId)
      const response = await fetch(
        `/api/v1/projects/${projectId}/discrepancies/${discrepancyId}/accept`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        }
      )

      if (response.ok) {
        toast.success('Conflito aceito com valor consolidado')
        fetchDiscrepancies()
      } else {
        toast.error('Erro ao aceitar conflito')
      }
    } catch (error) {
      console.error('Erro ao aceitar:', error)
      toast.error('Erro ao aceitar conflito')
    } finally {
      setResolving(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader className="h-6 w-6 animate-spin text-emerald-600" />
        <span className="ml-3 text-gray-700">Carregando conflitos...</span>
      </div>
    )
  }

  if (!discrepancies || discrepancies.unresolved === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8">
        <CheckCircle2 className="h-12 w-12 text-emerald-600 mb-3" />
        <h3 className="text-lg font-semibold text-gray-900">Sem conflitos</h3>
        <p className="text-sm text-gray-600 mt-1">
          Todas as personas estão alinhadas! Nenhuma discrepância detectada.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header com estatísticas */}
      <div className="flex items-center justify-between p-4 bg-white rounded-lg border border-gray-200">
        <div className="flex gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900">{discrepancies.unresolved}</div>
            <div className="text-xs text-gray-600">Não resolvido</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-emerald-600">{discrepancies.resolved}</div>
            <div className="text-xs text-gray-600">Resolvido</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900">{discrepancies.total}</div>
            <div className="text-xs text-gray-600">Total</div>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="px-3 py-1 text-sm rounded border border-gray-300 hover:bg-gray-50"
          >
            Fechar
          </button>
        )}
      </div>

      {/* Lista de conflitos */}
      <div className="space-y-2">
        {discrepancies.items.map((discrepancy) => {
          const config = severityConfig[discrepancy.severity]
          const Icon = config.icon
          const isExpanded = expandedId === discrepancy.id
          const selected = selectedValue[discrepancy.id] || ''

          return (
            <div
              key={discrepancy.id}
              className={`rounded-lg border ${config.borderColor} ${config.bgColor}`}
            >
              {/* Header colapsável */}
              <button
                onClick={() =>
                  setExpandedId(isExpanded ? null : discrepancy.id)
                }
                className="w-full flex items-start gap-3 p-4 hover:opacity-80 transition-opacity"
              >
                <Icon className={`h-5 w-5 ${config.color} flex-shrink-0 mt-0.5`} />
                <div className="flex-1 text-left">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">
                      {discrepancy.field_path}
                    </h3>
                    <span className={`px-2 py-1 text-xs font-medium rounded ${config.badge}`}>
                      {discrepancy.severity}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mt-1">
                    {discrepancy.conflicting_personas.length} personas em desacordo
                  </p>
                </div>
                {isExpanded ? (
                  <ChevronUp className="h-5 w-5 text-gray-500" />
                ) : (
                  <ChevronDown className="h-5 w-5 text-gray-500" />
                )}
              </button>

              {/* Detalhes expandidos */}
              {isExpanded && (
                <div className="border-t border-current border-opacity-10 p-4 space-y-3">
                  {/* Contexto */}
                  {discrepancy.context && (
                    <p className="text-sm text-gray-700 italic">
                      {discrepancy.context}
                    </p>
                  )}

                  {/* Valores divergentes */}
                  <div>
                    <label className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      Valores Propostos:
                    </label>
                    <div className="mt-2 space-y-2">
                      {Object.entries(discrepancy.conflicting_values).map(
                        ([persona, value]) => (
                          <label key={persona} className="flex items-center gap-3 p-2 rounded hover:bg-white hover:bg-opacity-50 cursor-pointer">
                            <input
                              type="radio"
                              name={`resolution-${discrepancy.id}`}
                              value={value}
                              checked={selected === value}
                              onChange={(e) =>
                                setSelectedValue({
                                  ...selectedValue,
                                  [discrepancy.id]: e.target.value,
                                })
                              }
                              className="rounded-full"
                            />
                            <div className="flex-1">
                              <div className="text-sm font-medium text-gray-900">
                                {value}
                              </div>
                              <div className="text-xs text-gray-600">
                                proposto por {persona}
                              </div>
                            </div>
                          </label>
                        )
                      )}
                    </div>
                  </div>

                  {/* Campo de notas */}
                  <div>
                    <label className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      Notas (opcional):
                    </label>
                    <textarea
                      value={notes[discrepancy.id] || ''}
                      onChange={(e) =>
                        setNotes({
                          ...notes,
                          [discrepancy.id]: e.target.value,
                        })
                      }
                      placeholder="Explique sua decisão..."
                      className="mt-2 w-full px-3 py-2 text-sm border border-current border-opacity-20 rounded focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none"
                      rows={2}
                    />
                  </div>

                  {/* Ações */}
                  <div className="flex gap-2 pt-2">
                    <button
                      onClick={() => handleResolve(discrepancy.id)}
                      disabled={!selected || resolving === discrepancy.id}
                      className="flex-1 px-3 py-2 bg-emerald-600 text-white text-sm font-medium rounded hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {resolving === discrepancy.id && (
                        <Loader className="h-4 w-4 animate-spin" />
                      )}
                      Resolver com Override
                    </button>
                    <button
                      onClick={() => handleAccept(discrepancy.id)}
                      disabled={resolving === discrepancy.id}
                      className="flex-1 px-3 py-2 bg-gray-200 text-gray-900 text-sm font-medium rounded hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {resolving === discrepancy.id && (
                        <Loader className="h-4 w-4 animate-spin" />
                      )}
                      Aceitar Consolidado
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
