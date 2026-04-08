/**
 * WireframeSection — Seção para upload e gerenciamento de wireframes
 *
 * Funcionalidades:
 * - Upload de wireframes (imagens, Figma files)
 * - Preview de wireframes
 * - Extração automática de design tokens
 * - Validação de design (WCAG, responsiveness, completeness)
 * - Ligação com Design System Artifact
 */

import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Upload, FileImage, Zap, AlertTriangle, CheckCircle2, Loader, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { api } from '@/services/api';
import { HelpIcon } from '@/components/HelpIcon';

interface WireframeFile {
  id: string;
  name: string;
  file_type: 'image_png' | 'image_svg' | 'figma_file' | 'figma_component';
  file_size: number;
  status: 'draft' | 'synced' | 'validating' | 'approved' | 'archived';
  pages_count?: number;
  components_count?: number;
  design_tokens?: Record<string, any>;
  created_at: string;
}

interface DesignSystemArtifact {
  id: string;
  accessibility_score: number;
  responsiveness_score: number;
  completeness_score: number;
  status: 'draft' | 'exported' | 'in_codegen' | 'completed';
}

interface WireframeSectionProps {
  projectId: string;
  isLocked?: boolean;
}

export function WireframeSection({ projectId, isLocked = false }: WireframeSectionProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [autoDraftJobId, setAutoDraftJobId] = useState<string | null>(null);
  const [autoDraftStatus, setAutoDraftStatus] = useState<'idle' | 'generating' | 'completed' | 'failed'>('idle');
  const queryClient = useQueryClient();

  // ── Queries ────────────────────────────────────────────────────────────

  const { data: wireframes, isLoading: wireframesLoading } = useQuery<{ wireframes: WireframeFile[] }>({
    queryKey: ['wireframes', projectId],
    queryFn: () => api.get(`/projects/${projectId}/wireframes`).then(r => r.data),
    enabled: !isLocked,
  });

  const { data: designSystem, isLoading: designSystemLoading } = useQuery<{ design_system: DesignSystemArtifact }>({
    queryKey: ['design-system', projectId],
    queryFn: () => api.get(`/projects/${projectId}/design-systems/latest`).then(r => r.data),
    enabled: !isLocked,
  });

  const { data: designStatus } = useQuery({
    queryKey: ['design-status', projectId],
    queryFn: () => api.get(`/projects/${projectId}/artifacts/design-status`).then(r => r.data),
    enabled: !isLocked,
    refetchInterval: autoDraftJobId ? 3000 : false, // Poll every 3s during generation
  });

  // ── Auto-Draft Figma Generation ────────────────────────────────────────

  const startAutoDraftMutation = useMutation({
    mutationFn: () =>
      api.post(`/projects/${projectId}/artifacts/generate-figma-draft`, {}),
    onSuccess: (response) => {
      const job_id = response.data?.data?.job_id;
      if (job_id) {
        setAutoDraftJobId(job_id);
        setAutoDraftStatus('generating');
        toast.success('Gerando esboço de design no Figma...');
      }
    },
    onError: (error: any) => {
      toast.error(`Erro ao iniciar geração: ${error.response?.data?.detail || 'Tente novamente'}`);
      setAutoDraftStatus('failed');
    },
  });

  const pollAutoDraftMutation = useMutation({
    mutationFn: (job_id: string) =>
      api.get(`/projects/${projectId}/artifacts/figma-draft/${job_id}`).then(r => r.data?.data),
    onSuccess: (data) => {
      if (data?.status === 'completed') {
        setAutoDraftStatus('completed');
        toast.success('✅ Design criado no Figma!');
        // Refresh wireframes list
        queryClient.invalidateQueries({ queryKey: ['wireframes', projectId] });
        queryClient.invalidateQueries({ queryKey: ['design-system', projectId] });
        queryClient.invalidateQueries({ queryKey: ['design-status', projectId] });
        setAutoDraftJobId(null);
      } else if (data?.status === 'failed') {
        setAutoDraftStatus('failed');
        toast.error(`Falha na geração: ${data?.error || 'Erro desconhecido'}`);
        setAutoDraftJobId(null);
      }
    },
  });

  // Poll for draft status when job is active
  useEffect(() => {
    if (!autoDraftJobId || autoDraftStatus !== 'generating') return;

    const interval = setInterval(() => {
      pollAutoDraftMutation.mutate(autoDraftJobId);
    }, 3000);

    return () => clearInterval(interval);
  }, [autoDraftJobId, autoDraftStatus]);

  // ── Mutations ──────────────────────────────────────────────────────────

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);

      const config = {
        onUploadProgress: (progressEvent: any) => {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(prev => ({ ...prev, [file.name]: progress }));
        },
      };

      return api.post(`/projects/${projectId}/wireframes`, formData, config);
    },
    onSuccess: () => {
      setUploadProgress({});
      queryClient.invalidateQueries({ queryKey: ['wireframes', projectId] });
    },
  });

  const validateMutation = useMutation({
    mutationFn: (wireframeId: string) =>
      api.post(`/projects/${projectId}/wireframes/${wireframeId}/validate`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wireframes', projectId] });
    },
  });

  const generateDesignSystemMutation = useMutation({
    mutationFn: (wireframeId: string) =>
      api.post(`/projects/${projectId}/wireframes/${wireframeId}/design-system`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['design-system', projectId] });
      queryClient.invalidateQueries({ queryKey: ['wireframes', projectId] });
    },
  });

  // ── Handlers ───────────────────────────────────────────────────────────

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files;
    if (!files) return;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      // Validar tipo de arquivo
      if (!['image/png', 'image/svg+xml', 'application/pdf'].includes(file.type)) {
        alert(`Tipo de arquivo não suportado: ${file.type}. Use PNG, SVG ou PDF.`);
        continue;
      }
      uploadMutation.mutate(file);
    }

    // Limpar input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();

    const files = e.dataTransfer.files;
    if (!files) return;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (['image/png', 'image/svg+xml', 'application/pdf'].includes(file.type)) {
        uploadMutation.mutate(file);
      }
    }
  };

  // ── Score Badge ────────────────────────────────────────────────────────

  function ScoreBadge({ score, label }: { score: number; label: string }) {
    const isGood = score >= 75;
    return (
      <div className="flex flex-col items-center">
        <div className={clsx(
          'text-2xl font-bold rounded-lg w-16 h-16 flex items-center justify-center',
          isGood ? 'bg-green-900/40 border border-green-700 text-green-300' : 'bg-amber-900/40 border border-amber-700 text-amber-300'
        )}>
          {score}
        </div>
        <p className="text-xs text-gray-400 mt-1">{label}</p>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────

  if (isLocked) {
    return (
      <div className="bg-dark-100 rounded-xl border border-gray-800 p-5 opacity-50 pointer-events-none">
        <div className="flex items-center gap-2 text-gray-500 font-semibold mb-4">
          <FileImage size={15} />
          <span>Wireframes & Design System</span>
          <span className="text-xs text-gray-600 ml-1">Selecione a linguagem primeiro</span>
        </div>
      </div>
    );
  }

  return (
    <section className="bg-dark-100 rounded-xl border border-gray-800 p-5">
      {/* Header */}
      <div className="flex items-center gap-2 text-white font-semibold mb-4">
        <FileImage size={15} className="text-violet-400" />
        <span>Wireframes & Design System</span>
        <HelpIcon text="Faça upload de wireframes (Figma, PNG, SVG) para extrair automaticamente design tokens, validar design contra requisitos (WCAG, responsiveness), e gerar componentes React/Vue/Svelte." />
      </div>

      {/* Upload Area */}
      <div
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className="border-2 border-dashed border-gray-700 rounded-lg p-8 text-center mb-6 hover:border-violet-600 transition-colors cursor-pointer"
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload size={32} className="mx-auto mb-2 text-gray-400" />
        <p className="text-sm text-gray-300 mb-1">Arraste wireframes aqui ou clique para selecionar</p>
        <p className="text-xs text-gray-500">PNG, SVG, PDF, ou integração com Figma</p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/png,image/svg+xml,application/pdf"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {/* Upload Progress */}
      {Object.entries(uploadProgress).map(([name, progress]) => (
        <div key={name} className="mb-3 p-3 bg-dark rounded-lg">
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-gray-300">{name}</span>
            <span className="text-xs text-gray-500">{progress}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-1.5">
            <div
              className="bg-violet-500 h-1.5 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      ))}

      {/* Auto-Draft Figma Section */}
      {autoDraftStatus === 'generating' && (
        <div className="mb-6 p-4 bg-violet-900/20 border border-violet-700/50 rounded-lg">
          <div className="flex items-center gap-2 mb-3">
            <Loader size={16} className="animate-spin text-violet-400" />
            <span className="text-sm font-semibold text-violet-300">Gerando esboço de design no Figma...</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div className="bg-violet-500 h-2 rounded-full w-1/3 animate-pulse" />
          </div>
          <p className="text-xs text-gray-400 mt-2">Isso pode levar alguns segundos</p>
        </div>
      )}

      {autoDraftStatus === 'completed' && (
        <div className="mb-6 p-4 bg-green-900/20 border border-green-700/50 rounded-lg">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle2 size={16} className="text-green-400" />
            <span className="text-sm font-semibold text-green-300">✅ Design criado com sucesso!</span>
          </div>
          <p className="text-xs text-gray-400">O arquivo foi criado no Figma e está sendo processado. Você pode fazer o download em breve.</p>
        </div>
      )}

      {autoDraftStatus === 'failed' && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-700/50 rounded-lg">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} className="text-red-400" />
            <span className="text-sm font-semibold text-red-300">Erro na geração de design</span>
          </div>
          <button
            onClick={() => {
              setAutoDraftStatus('idle');
              setAutoDraftJobId(null);
            }}
            className="text-xs text-red-300 hover:text-red-200 underline mt-2"
          >
            Tentar novamente
          </button>
        </div>
      )}

      {/* Wireframes List */}
      {wireframesLoading ? (
        <div className="flex items-center justify-center py-8 text-gray-500">
          <Loader size={16} className="animate-spin mr-2" />
          Carregando wireframes…
        </div>
      ) : wireframes && wireframes.wireframes.length > 0 ? (
        <div className="space-y-3 mb-6">
          <p className="text-xs text-gray-500 mb-3">Wireframes carregados:</p>
          {wireframes.wireframes.map(wf => (
            <div key={wf.id} className="p-3 bg-dark border border-gray-700 rounded-lg flex items-start justify-between">
              <div>
                <p className="text-sm text-gray-300">{wf.name}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {wf.file_type} · {(wf.file_size / 1024 / 1024).toFixed(2)} MB · Status: {wf.status}
                </p>
                {wf.pages_count && (
                  <p className="text-xs text-gray-500">
                    {wf.pages_count} páginas · {wf.components_count || 0} componentes
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => validateMutation.mutate(wf.id)}
                  disabled={validateMutation.isPending}
                  className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded transition-colors disabled:opacity-50"
                >
                  {validateMutation.isPending ? 'Validando…' : 'Validar'}
                </button>
                <button
                  onClick={() => generateDesignSystemMutation.mutate(wf.id)}
                  disabled={generateDesignSystemMutation.isPending}
                  className="px-2 py-1 text-xs bg-violet-700 hover:bg-violet-600 rounded transition-colors disabled:opacity-50"
                >
                  {generateDesignSystemMutation.isPending ? 'Gerando…' : 'Gerar System'}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-8">
          <p className="text-xs text-gray-500 text-center mb-4">Nenhum wireframe ainda</p>
          {designStatus?.can_auto_generate && autoDraftStatus === 'idle' && (
            <div className="flex justify-center">
              <button
                onClick={() => startAutoDraftMutation.mutate()}
                disabled={startAutoDraftMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-700 rounded-lg text-sm font-semibold text-white transition-colors disabled:opacity-50"
              >
                <Sparkles size={16} />
                {startAutoDraftMutation.isPending ? 'Iniciando…' : '📐 Gerar Design Automático'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Design System Scores */}
      {designSystem && (
        <div className="border-t border-gray-700 pt-4 mt-4">
          <p className="text-xs text-gray-400 mb-4 flex items-center gap-1">
            <CheckCircle2 size={12} className="text-green-400" /> Design System Validado
          </p>
          <div className="grid grid-cols-3 gap-4">
            <ScoreBadge
              score={designSystem.design_system.accessibility_score}
              label="Acessibilidade"
            />
            <ScoreBadge
              score={designSystem.design_system.responsiveness_score}
              label="Responsividade"
            />
            <ScoreBadge
              score={designSystem.design_system.completeness_score}
              label="Completude"
            />
          </div>
        </div>
      )}
    </section>
  );
}
