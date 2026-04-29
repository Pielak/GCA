/**
 * RefinementTimeline — Timeline visual de refinements de uma análise
 *
 * Mostra iterações com mudanças destacadas
 */

import React from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

interface Refinement {
  iteration: number
  parecer_refined: Record<string, any>
  changed_fields: string[]
  change_summary: string
  created_at: string
}

interface Props {
  originalParecer: Record<string, any>
  refinements: Refinement[]
  expanded?: boolean
  onToggle?: () => void
}

export function RefinementTimeline({ originalParecer, refinements, expanded = false, onToggle }: Props) {
  if (refinements.length === 0) {
    return null
  }

  const [isExpanded, setIsExpanded] = React.useState(expanded)

  const toggle = () => {
    setIsExpanded(!isExpanded)
    onToggle?.()
  }

  return (
    <div className="border-t border-gray-200 pt-4">
      <button
        onClick={toggle}
        className="flex items-center justify-between w-full mb-3 hover:opacity-80"
      >
        <h4 className="font-medium text-gray-900">Histórico de Refinements ({refinements.length})</h4>
        {isExpanded ? (
          <ChevronUp className="h-5 w-5 text-gray-600" />
        ) : (
          <ChevronDown className="h-5 w-5 text-gray-600" />
        )}
      </button>

      {isExpanded && (
        <div className="space-y-4">
          {/* Original State */}
          <div className="relative pl-8">
            <div className="absolute left-0 top-1 w-4 h-4 bg-gray-300 rounded-full border-2 border-white"></div>
            <div className="text-sm">
              <p className="font-medium text-gray-700">Original (análise inicial)</p>
              <p className="text-xs text-gray-600 mt-1">
                {Object.keys(originalParecer).length} campo(s)
              </p>
            </div>
          </div>

          {/* Timeline connector */}
          <div className="relative pl-8">
            <div className="absolute left-1.5 top-0 bottom-0 w-0.5 bg-gradient-to-b from-purple-300 via-blue-300 to-emerald-300"></div>
          </div>

          {/* Iterations */}
          {refinements.map((refinement, index) => (
            <div key={refinement.iteration} className="relative pl-8">
              {/* Timeline dot */}
              <div className="absolute left-0 top-1 w-4 h-4 bg-purple-600 rounded-full border-2 border-white"></div>

              {/* Iteration card */}
              <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-purple-900">Iteração {refinement.iteration}</span>
                  <span className="text-xs text-purple-700">
                    {new Date(refinement.created_at).toLocaleDateString('pt-BR', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>

                {/* Summary */}
                <p className="text-sm text-purple-700 mb-3">{refinement.change_summary}</p>

                {/* Changed fields */}
                {refinement.changed_fields.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-purple-600 uppercase">Campos alterados:</p>
                    <div className="flex flex-wrap gap-2">
                      {refinement.changed_fields.map((field) => (
                        <span
                          key={field}
                          className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-purple-100 text-purple-800"
                        >
                          {field}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Connector to next */}
              {index < refinements.length - 1 && (
                <div className="relative pl-0 mt-2">
                  <div className="absolute left-1.5 top-0 bottom-0 w-0.5 bg-gradient-to-b from-purple-300 to-transparent"></div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
