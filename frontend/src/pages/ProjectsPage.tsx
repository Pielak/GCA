import { useState } from 'react'
import { Card, Badge, Modal, Button, Input, SkeletonLoader } from '@/components/common'
import {
  usePendingProjects,
  useAllProjects,
  useCreateProject,
  useApproveProject,
  useRejectProject,
  type ProjectRequest,
} from '@/hooks/useProjects'
import { Plus, CheckCircle, XCircle, AlertCircle } from 'lucide-react'

type ProjectTab = 'pending' | 'all'
type ActionType = 'approve' | 'reject' | null

export const ProjectsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ProjectTab>('pending')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [selectedProject, setSelectedProject] = useState<ProjectRequest | null>(null)
  const [actionType, setActionType] = useState<ActionType>(null)
  const [rejectReason, setRejectReason] = useState('')

  // Form fields
  const [projectName, setProjectName] = useState('')
  const [projectSlug, setProjectSlug] = useState('')
  const [description, setDescription] = useState('')

  // Queries & Mutations
  const pendingQuery = usePendingProjects()
  const allProjectsQuery = useAllProjects()
  const createMutation = useCreateProject()
  const approveMutation = useApproveProject()
  const rejectMutation = useRejectProject()

  const projects = activeTab === 'pending' ? pendingQuery.data : allProjectsQuery.data
  const isLoading = activeTab === 'pending' ? pendingQuery.isLoading : allProjectsQuery.isLoading
  const error = activeTab === 'pending' ? pendingQuery.error : allProjectsQuery.error

  const handleCreateProject = async () => {
    if (!projectName || !projectSlug) return

    try {
      await createMutation.mutateAsync({
        project_name: projectName,
        project_slug: projectSlug,
        description,
      })
      setProjectName('')
      setProjectSlug('')
      setDescription('')
      setShowCreateModal(false)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleApprove = async () => {
    if (!selectedProject) return
    try {
      await approveMutation.mutateAsync(selectedProject.id)
      setSelectedProject(null)
      setActionType(null)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleReject = async () => {
    if (!selectedProject || !rejectReason) return
    try {
      await rejectMutation.mutateAsync({
        projectId: selectedProject.id,
        reason: rejectReason,
      })
      setSelectedProject(null)
      setActionType(null)
      setRejectReason('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending':
        return 'warning'
      case 'approved':
      case 'active':
        return 'success'
      case 'rejected':
        return 'error'
      default:
        return 'info'
    }
  }

  if (error) {
    return (
      <div>
        <h1 className="text-3xl font-bold text-white mb-8">Projetos</h1>
        <div className="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">
          <p>Erro ao carregar projetos. Tente novamente.</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-white">Projetos</h1>
        <Button
          variant="primary"
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2"
        >
          <Plus size={20} />
          Novo Projeto
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-8 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('pending')}
          className={`px-4 py-3 font-medium transition ${
            activeTab === 'pending'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          <AlertCircle className="inline mr-2" size={18} />
          Pendentes
        </button>
        <button
          onClick={() => setActiveTab('all')}
          className={`px-4 py-3 font-medium transition ${
            activeTab === 'all'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          Todos os Projetos
        </button>
      </div>

      {/* Projects List */}
      {isLoading && !projects ? (
        <Card>
          <SkeletonLoader count={3} height="h-20" />
        </Card>
      ) : !projects || projects.length === 0 ? (
        <Card>
          <p className="text-gray-400 text-center py-8">
            {activeTab === 'pending' ? 'Nenhum projeto pendente' : 'Nenhum projeto encontrado'}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {projects.map((project: ProjectRequest) => (
            <Card key={project.id} className="p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-white mb-1">{project.project_name}</h3>
                  <p className="text-gray-400 text-sm mb-2">{project.description}</p>
                  <div className="flex items-center gap-3 text-xs text-gray-400">
                    <span>Slug: <code className="bg-gray-700 px-2 py-1 rounded">{project.project_slug}</code></span>
                    <span>•</span>
                    <span>GP: {project.gp_email}</span>
                    <span>•</span>
                    <span>{new Date(project.created_at).toLocaleDateString('pt-BR')}</span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Badge variant={getStatusColor(project.status)}>
                    {project.status === 'pending' && 'Pendente'}
                    {project.status === 'approved' && 'Aprovado'}
                    {project.status === 'active' && 'Ativo'}
                    {project.status === 'rejected' && 'Rejeitado'}
                  </Badge>

                  {project.status === 'pending' && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          setSelectedProject(project)
                          setActionType('approve')
                        }}
                        className="p-2 text-green-400 hover:bg-green-900 rounded-lg transition"
                        title="Aprovar"
                      >
                        <CheckCircle size={18} />
                      </button>
                      <button
                        onClick={() => {
                          setSelectedProject(project)
                          setActionType('reject')
                        }}
                        className="p-2 text-red-400 hover:bg-red-900 rounded-lg transition"
                        title="Rejeitar"
                      >
                        <XCircle size={18} />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Project Modal */}
      <Modal
        isOpen={showCreateModal}
        title="Novo Projeto"
        onClose={() => {
          setShowCreateModal(false)
          setProjectName('')
          setProjectSlug('')
          setDescription('')
        }}
        onConfirm={handleCreateProject}
        confirmText="Criar Projeto"
        loading={createMutation.isPending}
      >
        <div className="space-y-4">
          <Input
            label="Nome do Projeto"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="Ex: E-commerce"
          />

          <Input
            label="Slug (URL-friendly)"
            value={projectSlug}
            onChange={(e) => setProjectSlug(e.target.value)}
            placeholder="Ex: ecommerce"
            helperText="Use apenas letras, números e hífens"
          />

          <div>
            <label className="block text-gray-300 text-sm font-medium mb-2">Descrição</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Descrição do projeto..."
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              rows={3}
            />
          </div>
        </div>
      </Modal>

      {/* Approve Project Modal */}
      {selectedProject && actionType === 'approve' && (
        <Modal
          isOpen={true}
          title="Aprovar Projeto"
          onClose={() => {
            setSelectedProject(null)
            setActionType(null)
          }}
          onConfirm={handleApprove}
          confirmText="Aprovar"
          loading={approveMutation.isPending}
        >
          <div className="space-y-4">
            <p className="text-gray-300">Você tem certeza que deseja aprovar este projeto?</p>
            <div className="bg-gray-700 rounded-lg p-4">
              <p className="text-sm text-gray-400">
                <span className="font-medium">Projeto:</span> {selectedProject.project_name}
              </p>
              <p className="text-sm text-gray-400">
                <span className="font-medium">GP:</span> {selectedProject.gp_email}
              </p>
            </div>
            <p className="text-sm text-gray-400">
              Após aprovação, o GP poderá começar a usar o sistema para este projeto.
            </p>
          </div>
        </Modal>
      )}

      {/* Reject Project Modal */}
      {selectedProject && actionType === 'reject' && (
        <Modal
          isOpen={true}
          title="Rejeitar Projeto"
          onClose={() => {
            setSelectedProject(null)
            setActionType(null)
            setRejectReason('')
          }}
          onConfirm={handleReject}
          confirmText="Rejeitar"
          loading={rejectMutation.isPending}
        >
          <div className="space-y-4">
            <p className="text-gray-300">Por que você quer rejeitar este projeto?</p>
            <div className="bg-gray-700 rounded-lg p-4">
              <p className="text-sm text-gray-400">
                <span className="font-medium">Projeto:</span> {selectedProject.project_name}
              </p>
              <p className="text-sm text-gray-400">
                <span className="font-medium">GP:</span> {selectedProject.gp_email}
              </p>
            </div>
            <div>
              <label className="block text-gray-300 text-sm font-medium mb-2">Motivo da Rejeição</label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Explique por que o projeto foi rejeitado..."
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                rows={3}
              />
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
