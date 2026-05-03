/**
 * ConflictResolutionModal — Modal para resolver conflitos manualmente
 *
 * User escolhe qual valor usar entre as opções das 7 personas
 */

import React, { useState } from 'react'
import { X, Loader, CheckCircle2 } from 'lucide-react'
import { useToast } from '@/hooks/useToast'

interface Option {
  persona: string
  value: any
}

interface Props {
  projectId: string
  documentId: string
  field: string
  options: Option[]
  votes: Record<string, number>
  onClose: () => void
  onSuccess?: () => void
}

export function ConflictResolutionModal({
  projectId,
  documentId,
  field,
  options,
  votes,
  onClose,
  onSuccess,
}: Props) {
  const [selectedValue, setSelectedValue] = useState<any | null>(null)
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const toast = useToast()

  const handleSubmit = async () => {
    if (selectedValue === null) {
      toast.warning('Selecione um valor para continuar')
      return
    }

    try {
      setSubmitting(true)
      const response = await fetch(
        `/api/v1/projects/${projectId}/ingestion/${documentId}/ocg-global/override`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
          body: JSON.stringify({
            field,
            chosen_value: selectedValue,
            reason: reason || null,
          }),
        }
      )

      if (response.ok) {
        toast.success(`Campo '${field}' resolvido manualmente`)
        onSuccess?.()
        onClose()
      } else {
        toast.error('Erro ao resolver conflito')
      }
    } catch (error) {
      console.error('Erro ao enviar override:', error)
      toast.error('Erro ao resolver conflito')
    } finally {
      setSubmitting(false)
    }
  }

  const formatValue = (value: any) => {
    if (typeof value === 'object' && value !== null) {
      return JSON.stringify(value, null, 2)
    }
    return String(value)
  }

  const getMostVotedValue = () => {
    const maxVotes = Math.max(...Object.values(votes))
    return Object.entries(votes).find(([_, count]) => count === maxVotes)?.[0]
  }

  const mostVoted = getMostVotedValue()

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 p-6 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Resolver Conflito</h2>
            <p className="text-sm text-gray-600 mt-1">Campo: {field}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg text-gray-500"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Info */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-700">
              Selecione qual valor deve ser usado no parecer consolidado. Este override será registrado com o seu usuário e motivo.
            </p>
          </div>

          {/* Options */}
          <div className="space-y-3">
            <p className="text-sm font-medium text-gray-900">Opções das Personas:</p>
            {options.map((option, index) => {
              const isSelected = JSON.stringify(selectedValue) === JSON.stringify(option.value)
              const voteCount = votes[JSON.stringify(option.value)] || 0
              const isMostVoted = mostVoted === JSON.stringify(option.value)

              return (
                <div
                  key={index}
                  onClick={() => setSelectedValue(option.value)}
                  className={`p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                    isSelected
                      ? 'border-emerald-600 bg-emerald-50'
                      : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="conflict-option"
                          checked={isSelected}
                          onChange={() => setSelectedValue(option.value)}
                          className="w-4 h-4"
                        />
                        <span className="font-medium text-gray-900">{option.persona}</span>
                        {isMostVoted && (
                          <span className="text-xs bg-emerald-100 text-emerald-800 px-2 py-1 rounded">
                            Mais votado
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="text-sm text-gray-600">{voteCount} voto(s)</span>
                  </div>
                  <div className="bg-gray-50 rounded p-2 text-sm text-gray-700 font-mono whitespace-pre-wrap break-words">
                    {formatValue(option.value)}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Reason */}
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-2">
              Motivo do Override (opcional)
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Descreva por que você escolheu este valor..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm resize-none"
              rows={3}
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4 border-t border-gray-200">
            <button
              onClick={onClose}
              disabled={submitting}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting || selectedValue === null}
              className="flex-1 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <Loader className="h-4 w-4 animate-spin" />
                  Resolvendo...
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4" />
                  Aplicar Override
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
