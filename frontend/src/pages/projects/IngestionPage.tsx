import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Upload, FileText, AlertTriangle, Shield, Hash, CheckCircle, Eye, XCircle, Clock, Play, Terminal } from 'lucide-react';
import { HelpTooltip } from '@/components/ui/HelpTooltip';
import { StatusBadge } from '../../components/ui/StatusBadge';

interface Document {
  id: string;
  name: string;
  type: string;
  size: string;
  uploadedAt: string;
  arguidorStatus: 'aguardando' | 'processando' | 'processado' | 'erro';
  sectionsExtracted?: number;
}

const INITIAL_DOCUMENTS: Document[] = [
  {
    id: '1',
    name: 'requisitos-funcionais-v2.pdf',
    type: 'PDF',
    size: '2.4 MB',
    uploadedAt: '2026-04-07T14:30:00Z',
    arguidorStatus: 'processado',
    sectionsExtracted: 14,
  },
  {
    id: '2',
    name: 'arquitetura-sistema.docx',
    type: 'DOCX',
    size: '1.1 MB',
    uploadedAt: '2026-04-07T15:00:00Z',
    arguidorStatus: 'processado',
    sectionsExtracted: 8,
  },
  {
    id: '3',
    name: 'wireframe-dashboard.png',
    type: 'PNG',
    size: '850 KB',
    uploadedAt: '2026-04-08T09:15:00Z',
    arguidorStatus: 'aguardando',
  },
  {
    id: '4',
    name: 'regras-negocio.xlsx',
    type: 'XLSX',
    size: '340 KB',
    uploadedAt: '2026-04-08T09:20:00Z',
    arguidorStatus: 'aguardando',
  },
  {
    id: '5',
    name: 'api-specs.md',
    type: 'MD',
    size: '120 KB',
    uploadedAt: '2026-04-08T10:00:00Z',
    arguidorStatus: 'erro',
  },
];

const INITIAL_LOGS: { time: string; message: string }[] = [
  { time: '2026-04-07 14:31:12', message: '[Arguidor] Iniciando análise: requisitos-funcionais-v2.pdf' },
  { time: '2026-04-07 14:31:45', message: '[Arguidor] Extraídas 14 seções do documento requisitos-funcionais-v2.pdf' },
  { time: '2026-04-07 14:31:46', message: '[Arguidor] OCG atualizado com sucesso (14 novos campos populados)' },
  { time: '2026-04-07 15:01:03', message: '[Arguidor] Iniciando análise: arquitetura-sistema.docx' },
  { time: '2026-04-07 15:01:38', message: '[Arguidor] Extraídas 8 seções do documento arquitetura-sistema.docx' },
  { time: '2026-04-07 15:01:39', message: '[Arguidor] OCG atualizado com sucesso (8 novos campos populados)' },
  { time: '2026-04-08 10:00:15', message: '[Arguidor] Erro ao processar api-specs.md — tentativa 1/3. Motivo: encoding não suportado.' },
];

const statusIcon: Record<Document['arguidorStatus'], React.ReactNode> = {
  aguardando: <span title="Aguardando">⚪</span>,
  processando: <span title="Processando">⏳</span>,
  processado: <span title="Processado">✅</span>,
  erro: <span title="Erro">❌</span>,
};

const statusLabel: Record<Document['arguidorStatus'], string> = {
  aguardando: 'Aguardando',
  processando: 'Processando',
  processado: 'Processado',
  erro: 'Erro',
};

export function IngestionPage() {
  const { id } = useParams<{ id: string }>();
  const [dragging, setDragging] = useState(false);
  const [documents, setDocuments] = useState<Document[]>(INITIAL_DOCUMENTS);
  const [logs] = useState(INITIAL_LOGS);
  const [filter, setFilter] = useState<'all' | Document['arguidorStatus']>('all');

  const filtered = filter === 'all' ? documents : documents.filter(d => d.arguidorStatus === filter);
  const aguardandoCount = documents.filter(d => d.arguidorStatus === 'aguardando').length;

  return (
    <div className="p-6 space-y-6">
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
          <button
            disabled={aguardandoCount === 0}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play className="w-4 h-4" />
            Iniciar Arguidor{aguardandoCount > 0 && ` (${aguardandoCount})`}
          </button>
        </div>
      </div>

      {/* Upload Area */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); }}
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
        <button className="mt-4 px-4 py-2 rounded-lg bg-violet-600 text-white text-sm hover:bg-violet-500 transition-colors">
          Selecionar Arquivo
        </button>
      </div>

      {/* Documents Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="text-slate-200 text-sm font-semibold">Documentos ({documents.length})</h3>
          <div className="flex gap-1">
            {(['all', 'aguardando', 'processando', 'processado', 'erro'] as const).map(s => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-2.5 py-1 rounded-md text-xs transition-colors ${filter === s ? 'bg-violet-600/20 text-violet-300 border border-violet-600/30' : 'text-slate-500 hover:text-slate-300'}`}
              >
                {s === 'all' ? 'Todos' : statusLabel[s]}
              </button>
            ))}
          </div>
        </div>

        {/* Table Header */}
        <div className="grid grid-cols-[1fr_80px_80px_120px_140px] gap-4 px-5 py-2 border-b border-slate-800 text-xs text-slate-500 font-medium">
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
        </div>

        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-slate-500 text-sm">Nenhum documento encontrado.</div>
        ) : (
          <div className="divide-y divide-slate-800">
            {filtered.map(doc => (
              <div key={doc.id} className="grid grid-cols-[1fr_80px_80px_120px_140px] gap-4 items-center px-5 py-3 hover:bg-slate-800/30 transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0">
                    <FileText className="w-4 h-4 text-slate-400" />
                  </div>
                  <span className="text-slate-200 text-sm font-medium truncate">{doc.name}</span>
                </div>
                <span className="text-slate-400 text-xs">{doc.type}</span>
                <span className="text-slate-400 text-xs">{doc.size}</span>
                <span className="text-slate-500 text-xs">{new Date(doc.uploadedAt).toLocaleDateString('pt-BR')}</span>
                <div className="flex items-center gap-2 text-xs">
                  {statusIcon[doc.arguidorStatus]}
                  <span className={
                    doc.arguidorStatus === 'processado' ? 'text-emerald-500' :
                    doc.arguidorStatus === 'erro' ? 'text-red-400' :
                    doc.arguidorStatus === 'processando' ? 'text-amber-400' :
                    'text-slate-400'
                  }>
                    {statusLabel[doc.arguidorStatus]}
                  </span>
                  {doc.sectionsExtracted !== undefined && (
                    <span className="text-slate-500">({doc.sectionsExtracted} seções)</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Log do Arguidor */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-800">
          <Terminal className="w-4 h-4 text-violet-400" />
          <h3 className="text-slate-200 text-sm font-semibold">Log do Arguidor em Tempo Real</h3>
          <HelpTooltip
            text="Registro em tempo real das operações do Arguidor. Cada linha mostra: horário, documento processado, número de seções extraídas e ações realizadas no OCG. O log é persistido no banco e visível para todos os membros do projeto. Útil para diagnóstico de falhas e auditoria do processo de ingestão."
            maxWidth="max-w-96"
          />
        </div>
        <div className="p-4 max-h-56 overflow-y-auto font-mono text-xs space-y-1">
          {logs.length === 0 ? (
            <p className="text-slate-500">Nenhum log disponível. Inicie o Arguidor para ver atividade.</p>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="flex gap-3">
                <span className="text-slate-600 flex-shrink-0">{log.time}</span>
                <span className={
                  log.message.includes('Erro') ? 'text-red-400' :
                  log.message.includes('sucesso') ? 'text-emerald-500' :
                  'text-slate-300'
                }>
                  {log.message}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
