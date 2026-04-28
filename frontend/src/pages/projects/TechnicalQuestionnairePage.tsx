import { useParams } from 'react-router-dom'
import { TechnicalQuestionnaireForm } from '@/components/questionnaire/TechnicalQuestionnaireForm'

export function TechnicalQuestionnairePage() {
  const { projectId } = useParams<{ projectId: string }>()

  if (!projectId) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-gray-600">ID do projeto não fornecido</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <TechnicalQuestionnaireForm projectId={projectId} />
    </div>
  )
}
