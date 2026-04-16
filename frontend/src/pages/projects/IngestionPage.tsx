import React, { useState, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Upload, FileText, Trash2, Play, Terminal, Loader2, RefreshCw } from 'lucide-react';
import { HelpTooltip } from '@/components/ui/HelpTooltip';
import { useDocuments, useUploadDocument, useDeleteDocument, type IngestedDocument } from '@/hooks/useIngestion';
import { PulseIndicator, OperationBar, PageTransition } from '@/components/ui/PipelineProgress';

type FilterStatus = 'all' | IngestedDocument['arguider_status'];

const STATUS_MAP: Record<IngestedDocument['arguider_status'], { icon: string; label: string; color: string }> = {
  pending:    { icon: '⚪', label: 'Aguardando',  color: 'text-slate-400' },
  processing: { icon: '⏳', label: 'Processando', color: 'text-amber-400' },
  completed:  { icon: '✅', label: 'Processado',  color: 'text-emerald-500' },
  error:      { icon: '❌', label: 'Erro',        color: 'text-red-400' },
};

const FILTER_LABELS: Record<FilterStatus, string> = {
  all: 'Todos',
  pending: 'Aguardando',
  processing: 'Processando',
  completed: 'Processado',
  error: 'Erro',
};

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

function fileTypeLabel(ft: string): string {
  const map: Record<string, string> = {
    pdf: 'PDF', docx: 'DOCX', markdown: 'MD', image: 'IMG',
    spreadsheet: 'XLSX', code: 'CODE',
  };
  return map[ft] || ft.toUpperCase();
}

export function IngestionPage() {
  const { id: projectId } = useParams<{ id: string }>();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [filter, setFilter] = useState<FilterStatus>('all');

  const { data: documents = [], isLoading, refetch } = useDocuments(projectId);
  const uploadMutation = useUploadDocument(projectId);
  const deleteMutation = useDeleteDocument(projectId);

  const filtered = filter === 'all' ? documents : documents.filter(d => d.arguider_status === filter);
  const pendingCount = documents.filter(d => d.arguider_status === 'pending').length;
  const processingCount = documents.filter(d => d.arguider_status === 'processing').length;

  const handleFiles = useCallback((files: FileList | File[]) => {
    Array.from(files).forEach(file => {
      uploadMutation.mutate(file);
    });
  }, [uploadMutation]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  }, [handleFiles]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
      e.target.value = ''; // Reset para permitir re-upload do mesmo arquivo
    }
  }, [handleFiles]);

  const handleDelete = useCallback((docId: string, filename: string) => {
    if (confirm(`Remover "${filename}"?`)) {
      deleteMutation.mutate(docId);
    }
  }, [deleteMutation]);

  return (
    <PageTransition>
    <div className="p-6 space-y-6">
      {/* Upload operation feedback */}
      {uploadMutation.isPending && (
        <OperationBar
          message="Enviando documento"
          detail="Processando upload e validando formato"
          status="running"
        />
      )}

      {/* Header + Iniciar Arguidor */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            Ingestão de Documentos
            <HelpTooltip
              text="Ingestão é o processo de carregar documentos do projeto (requisitos, arquitetura, regras de negócio, mockups) para que o Arguidor — o agente de IA analítico do GCA — extraia informações estruturadas e popule o OCG. Documentos de baixa qualidade ou incompletos resultam em um OCG impreciso, o que reduz diretamente a qualidade do código gerado nas fases posteriores."
              maxWidth="max-w-96"
            />
          </h2>
          <p className="text-slate-500 text-sm mt-0.5">Upload de documentos para análise pelo Arguidor e população do OCG</p>
        </div>
        <div className="flex items-center gap-2">
          <HelpTooltip
            text="Dispara a análise de todos os documentos com status 'Aguardando'. O Arguidor processa um documento por vez para evitar conflitos de escrita no OCG. Durante o processamento, o OCG fica em modo somente-leitura. Tempo estimado: 30 segundos a 5 minutos por documento, dependendo do tamanho e do provedor LLM configurado. Só o GP pode iniciar o Arguidor."
            position="left"
            maxWidth="max-w-96"
          />
          {processingCount > 0 && (
            <PulseIndicator message={`${processingCount} processando`} variant="warning" />
          )}
          <button
            onClick={() => refetch()}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            title="Atualizar lista"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Upload Area */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-10 text-center transition-all ${dragging ? 'border-violet-500 bg-violet-900/10' : 'border-slate-700 hover:border-slate-600'}`}
      >
        <Upload className="w-10 h-10 text-slate-500 mx-auto mb-3" />
        <p className="text-slate-300 text-sm font-medium flex items-center justify-center gap-2">
          Arraste documentos ou clique para selecionar
          <HelpTooltip
            text="Formatos suportados: PDF e DOCX (extração de texto completa), PNG/JPG (análise visual via visão computacional para wireframes), XLSX (extração de tabelas e regras de negócio), MD (documentação técnica). Tamanho máximo: 50MB por arquivo. Arquivos maiores são processados em chunks de 8.000 tokens pelo Arguidor."
            maxWidth="max-w-96"
          />
        </p>
        <p className="text-slate-500 text-xs mt-1">PDF &bull; DOCX &bull; XLSX &bull; PNG &bull; JPG &bull; MD &mdash; max. 50MB por arquivo</p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.gif,.webp,.md,.txt,.py,.ts,.js,.java,.cs,.go,.rs"
          onChange={handleFileSelect}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMutation.isPending}
          className="mt-4 px-4 py-2 rounded-lg bg-violet-600 text-white text-sm hover:bg-violet-500 transition-colors disabled:opacity-50"
        >
          {uploadMutation.isPending ? (
            <span className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Enviando...
            </span>
          ) : (
            'Selecionar Arquivo'
          )}
        </button>
      </div>

      {/* Documents Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="text-slate-200 text-sm font-semibold">Documentos ({documents.length})</h3>
          <div className="flex gap-1">
            {(['all', 'pending', 'processing', 'completed', 'error'] as FilterStatus[]).map(s => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-2.5 py-1 rounded-md text-xs transition-colors ${filter === s ? 'bg-violet-600/20 text-violet-300 border border-violet-600/30' : 'text-slate-500 hover:text-slate-300'}`}
              >
                {FILTER_LABELS[s]}
              </button>
            ))}
          </div>
        </div>

        {/* Table Header */}
        <div className="grid grid-cols-[1fr_80px_80px_120px_140px_40px] gap-4 px-5 py-2 border-b border-slate-800 text-xs text-slate-500 font-medium">
          <span>Nome</span>
          <span>Tipo</span>
          <span>Tamanho</span>
          <span>Upload</span>
          <span className="flex items-center gap-1">
            Status Arguidor
            <HelpTooltip
              text="Status do processamento pelo Arguidor: ⚪ Aguardando = na fila de análise; ⏳ Processando = sendo analisado pelo LLM agora; ✅ Processado = extraído e adicionado ao OCG com sucesso; ❌ Erro = falha na análise. Erros são retentados automaticamente até 3 vezes (self-healing). Se persistir, verifique se o arquivo está corrompido."
              maxWidth="max-w-96"
            />
          </span>
          <span></span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-slate-500 text-sm">
            {documents.length === 0 ? 'Nenhum documento ingerido. Faça upload para começar.' : 'Nenhum documento encontrado com este filtro.'}
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {filtered.map(doc => {
              const st = STATUS_MAP[doc.arguider_status];
              return (
                <div key={doc.id} className="grid grid-cols-[1fr_80px_80px_120px_140px_40px] gap-4 items-center px-5 py-3 hover:bg-slate-800/30 transition-colors">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0">
                      <FileText className="w-4 h-4 text-slate-400" />
                    </div>
                    {doc.content_status === 'lost' ? (
                      <span
                        className="text-slate-500 text-sm font-medium truncate line-through cursor-not-allowed"
                        title="Conteúdo perdido — bytes não disponíveis para visualização"
                      >
                        {doc.original_filename}
                      </span>
                    ) : (
                      <a
                        href={`/api/v1/projects/${projectId}/ingestion/${doc.id}/content`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-slate-200 text-sm font-medium truncate hover:text-violet-300 hover:underline"
                        title="Abrir documento (read-only)"
                      >
                        {doc.original_filename}
                      </a>
                    )}
                    {doc.source_type === 'external_repo' && (
                      <span className="flex items-center gap-1 flex-shrink-0">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300" title="Documento gerado a partir de Repositório Externo">
                          📦 Repo Externo
                        </span>
                        {doc.source_url && (
                          <a
                            href={doc.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-violet-300 hover:text-violet-200 text-xs"
                            title={doc.source_url}
                            onClick={e => e.stopPropagation()}
                          >
                            ↗
                          </a>
                        )}
                      </span>
                    )}
                  </div>
                  <span className="text-slate-400 text-xs">{fileTypeLabel(doc.file_type)}</span>
                  <span className="text-slate-400 text-xs">{formatFileSize(doc.file_size_bytes)}</span>
                  <span className="text-slate-500 text-xs">{new Date(doc.created_at).toLocaleDateString('pt-BR')}</span>
                  <div className="flex items-center gap-2 text-xs">
                    {doc.arguider_status === 'processing' ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" />
                    ) : (
                      <span title={st.label}>{st.icon}</span>
                    )}
                    <span className={st.color}>{st.label}</span>
                    {doc.ocg_updated && <span className="text-emerald-600 text-[10px]">(OCG)</span>}
                  </div>
                  <button
                    onClick={() => handleDelete(doc.id, doc.original_filename)}
                    disabled={doc.arguider_status === 'processing' || deleteMutation.isPending}
                    className="p-1 rounded text-slate-600 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    title="Remover documento"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Status summary */}
      {documents.length > 0 && (
        <div className="grid grid-cols-4 gap-3">
          {([
            { key: 'pending', label: 'Aguardando', bg: 'bg-slate-900 border-slate-800', tc: 'text-slate-300' },
            { key: 'processing', label: 'Processando', bg: 'bg-amber-950/20 border-amber-800/30', tc: 'text-amber-400' },
            { key: 'completed', label: 'Processados', bg: 'bg-emerald-950/20 border-emerald-800/30', tc: 'text-emerald-400' },
            { key: 'error', label: 'Erros', bg: 'bg-red-950/20 border-red-800/30', tc: 'text-red-400' },
          ] as const).map(({ key, label, bg, tc }) => (
            <div key={key} className={`${bg} border rounded-xl p-3 text-center`}>
              <p className={`text-xl font-semibold ${tc}`}>{documents.filter(d => d.arguider_status === key).length}</p>
              <p className="text-slate-500 text-xs mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}
    </div>
    </PageTransition>
  );
}
