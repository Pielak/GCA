import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { TechnicalQuestionnaireForm } from '@/components/questionnaire/TechnicalQuestionnaireForm'
import { PersonaBoard } from '@/components/questionnaire/PersonaBoard'

export function TechnicalQuestionnairePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [questionnaireId, setQuestionnaireId] = useState<string | null>(null)

  if (!projectId) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-gray-600">ID do projeto não fornecido</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <TechnicalQuestionnaireForm
        projectId={projectId}
        onSubmitted={(qId) => {
          setQuestionnaireId(qId || '')
          setIsSubmitted(true)
        }}
      />

      {isSubmitted && (
        <div className="max-w-4xl mx-auto p-6 mt-6 space-y-6">
          <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-green-600 flex-shrink-0 mt-0.5" size={24} />
              <div className="flex-1">
                <h3 className="font-semibold text-green-900">Questionário Submetido!</h3>
                <p className="text-sm text-green-700 mt-1">
                  Suas respostas foram salvas com sucesso. Os analistas estão avaliando seus requisitos em paralelo.
                </p>
                <p className="text-sm text-green-700 mt-2">
                  Próximo passo: carregue seus documentos de requisitos (especificações, regras de negócio, fluxos) para análise detalhada.
                </p>
                <a
                  href={`/projects/${projectId}/ingestion`}
                  className="inline-block mt-3 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
                >
                  Ir para Ingestão →
                </a>
              </div>
            </div>
          </div>

          {questionnaireId && (
            <div>
              <h2 className="text-2xl font-bold text-gray-900 mb-4">Análise de Personas</h2>
              <PersonaBoard
                projectId={projectId!}
                questionnaireId={questionnaireId}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
