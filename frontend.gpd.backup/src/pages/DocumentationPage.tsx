/**
 * DocumentationPage — Documentação consolidada e exportação
 *
 * Funcionalidades:
 * - Exibir documentação consolidada automaticamente
 * - Download de DOCX, PDF, HTML
 * - Botão para regenerar consolidação
 * - Status de consolidação
 */

import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileText,
  Download,
  RefreshCw,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  FileJson,
  Zap,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { api } from '@/services/api';
import { HelpIcon } from '@/components/HelpIcon';

interface MasterDocument {
  id: string;
  project_id: string;
  version_label: string;
  status: 'draft' | 'published' | 'approved' | 'superseded';
  content_markdown: string;
  approved_by?: string;
  approved_at?: string;
  created_at: string;
  updated_at: string;
}

interface MergeVersion {
  id: string;
  project_id: string;
  version_label: string;
  status: string;
  artifact_count: number;
  conflict_count: number;
  created_at: string;
}

export default function DocumentationPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [expandedContent, setExpandedContent] = useState(false);

  // ── Queries ────────────────────────────────────────────────────────────

  const { data: masterDoc, isLoading: docLoading } = useQuery<{ data: MasterDocument }>({
    queryKey: ['master-document', projectId],
    queryFn: () => api.get(`/projects/${projectId}/merge/master-document`).then(r => r.data),
    enabled: !!projectId,
  });

  const { data: latestMerge, isLoading: mergeLoading } = useQuery<{ data: MergeVersion }>({
    queryKey: ['latest-merge', projectId],
    queryFn: () => api.get(`/projects/${projectId}/merge/latest`).then(r => r.data),
    enabled: !!projectId,
  });

  // ── Mutations ──────────────────────────────────────────────────────────

  const regenerateMutation = useMutation({
    mutationFn: () => api.post(`/projects/${projectId}/merge/run`, {}),
    onSuccess: () => {
      toast.success('Documentação regenerada com sucesso');
      queryClient.invalidateQueries({ queryKey: ['master-document', projectId] });
      queryClient.invalidateQueries({ queryKey: ['latest-merge', projectId] });
    },
    onError: (error: any) => {
      toast.error(`Erro ao regenerar: ${error.response?.data?.detail || 'Tente novamente'}`);
    },
  });

  const downloadDocxMutation = useMutation({
    mutationFn: async () => {
      const response = await api.get(
        `/projects/${projectId}/merge/master-document/export?format=docx`,
        { responseType: 'blob' }
      );
      return response;
    },
    onSuccess: (response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${masterDoc?.data.version_label || 'projeto'}.docx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Download iniciado');
    },
    onError: () => {
      toast.error('Erro ao baixar documento');
    },
  });

  const downloadPdfMutation = useMutation({
    mutationFn: async () => {
      const response = await api.get(
        `/projects/${projectId}/merge/master-document/export?format=pdf`,
        { responseType: 'blob' }
      );
      return response;
    },
    onSuccess: (response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${masterDoc?.data.version_label || 'projeto'}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Download iniciado');
    },
    onError: () => {
      toast.error('Erro ao baixar documento');
    },
  });

  // ── Render ─────────────────────────────────────────────────────────────

  if (!projectId) {
    return (
      <div className="card text-center text-gray-500 py-16">
        Nenhum projeto selecionado.
      </div>
    );
  }

  const doc = masterDoc?.data;
  const merge = latestMerge?.data;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <FileText size={24} className="text-violet-400" />
            Documentação
            <HelpIcon text="Documentação consolidada automaticamente de todos os artefatos do projeto. Inclui requisitos, arquitetura, design, dados, APIs, segurança e testes." />
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {doc ? `Versão: ${doc.version_label}` : 'Nenhuma documentação consolidada'}
          </p>
        </div>
        <button
          onClick={() => regenerateMutation.mutate()}
          disabled={regenerateMutation.isPending || docLoading}
          className={clsx(
            'px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors',
            regenerateMutation.isPending || docLoading
              ? 'bg-violet-600/50 text-gray-400 cursor-wait'
              : 'bg-violet-600 hover:bg-violet-500 text-white'
          )}
        >
          <RefreshCw size={16} className={regenerateMutation.isPending ? 'animate-spin' : ''} />
          {regenerateMutation.isPending ? 'Regenerando…' : 'Regenerar'}
        </button>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Consolidation Status */}
        <div className="card">
          <div className="flex items-start gap-3">
            <Zap size={16} className="text-amber-400 mt-1 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-400 mb-1">Status de Consolidação</p>
              <p className="text-sm font-medium text-gray-200">
                {merge?.status ? (merge.status === 'processing' ? '⏳ Processando' : '✅ Consolidado') : 'Pendente'}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {merge ? `${merge.artifact_count} artefatos` : '-'}
              </p>
            </div>
          </div>
        </div>

        {/* Conflicts */}
        <div className="card">
          <div className="flex items-start gap-3">
            <AlertTriangle size={16} className={(merge?.conflict_count && merge.conflict_count > 0 ? 'text-red-400' : 'text-green-400') + ' mt-1 shrink-0'} />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-400 mb-1">Conflitos Detectados</p>
              <p className="text-sm font-medium text-gray-200">
                {merge?.conflict_count || 0}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {merge && merge.conflict_count > 0 ? 'Requerem atenção' : 'Nenhum conflito'}
              </p>
            </div>
          </div>
        </div>

        {/* Last Updated */}
        <div className="card">
          <div className="flex items-start gap-3">
            <CheckCircle2 size={16} className="text-emerald-400 mt-1 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-400 mb-1">Última Atualização</p>
              <p className="text-sm font-medium text-gray-200">
                {doc ? new Date(doc.updated_at).toLocaleDateString('pt-BR', {
                  day: '2-digit',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                }) : '-'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Download Options */}
      {doc && (
        <div className="card">
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Download size={14} />
              Downloads
            </h3>
            <p className="text-xs text-gray-500 mt-1">Exporte a documentação em diferentes formatos</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <button
              onClick={() => downloadDocxMutation.mutate()}
              disabled={downloadDocxMutation.isPending}
              className={clsx(
                'px-4 py-3 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors',
                downloadDocxMutation.isPending
                  ? 'bg-blue-600/50 text-gray-400 cursor-wait'
                  : 'bg-blue-600 hover:bg-blue-500 text-white'
              )}
            >
              <FileText size={14} />
              {downloadDocxMutation.isPending ? 'Baixando…' : 'DOCX'}
            </button>

            <button
              onClick={() => downloadPdfMutation.mutate()}
              disabled={downloadPdfMutation.isPending}
              className={clsx(
                'px-4 py-3 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors',
                downloadPdfMutation.isPending
                  ? 'bg-red-600/50 text-gray-400 cursor-wait'
                  : 'bg-red-600 hover:bg-red-500 text-white'
              )}
            >
              <FileText size={14} />
              {downloadPdfMutation.isPending ? 'Baixando…' : 'PDF'}
            </button>

            <button
              disabled
              className="px-4 py-3 rounded-lg text-sm font-medium flex items-center justify-center gap-2 bg-gray-700/50 text-gray-500 cursor-not-allowed"
              title="Em breve"
            >
              <FileJson size={14} />
              JSON (em breve)
            </button>
          </div>
        </div>
      )}

      {/* Content Preview */}
      {docLoading || mergeLoading ? (
        <div className="flex items-center justify-center py-16 text-gray-500">
          <Loader2 size={24} className="animate-spin mr-3" />
          Carregando documentação…
        </div>
      ) : doc ? (
        <div className="card">
          <button
            onClick={() => setExpandedContent(!expandedContent)}
            className="w-full flex items-center justify-between p-4 hover:bg-dark-200 transition-colors rounded-lg"
          >
            <h3 className="text-sm font-semibold text-white">Prévia do Conteúdo</h3>
            <span className="text-xs text-gray-500">
              {expandedContent ? 'Recolher' : 'Expandir'}
            </span>
          </button>

          {expandedContent && (
            <div className="border-t border-gray-700 p-4">
              <div className="prose prose-invert max-w-none">
                <div className="bg-dark text-gray-300 text-sm p-4 rounded overflow-auto max-h-[500px]">
                  <pre className="whitespace-pre-wrap break-words font-mono text-xs">
                    {doc.content_markdown.slice(0, 2000)}
                    {doc.content_markdown.length > 2000 && (
                      <p className="text-gray-600 mt-4">
                        [... ({doc.content_markdown.length} caracteres totais) ...]
                      </p>
                    )}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="card text-center py-12">
          <FileText size={40} className="mx-auto text-gray-600 mb-3" />
          <p className="text-gray-400">Nenhuma documentação consolidada</p>
          <p className="text-sm text-gray-600 mt-2">
            Faça upload de artefatos para gerar documentação automática.
          </p>
          <button
            onClick={() => regenerateMutation.mutate()}
            disabled={regenerateMutation.isPending}
            className="mt-4 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Gerar Documentação Agora
          </button>
        </div>
      )}
    </div>
  );
}
