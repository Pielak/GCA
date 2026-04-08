import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { BookOpen, GitBranch, GitPullRequest, RefreshCw, Eye, Download, Sparkles, CheckCircle, Clock, ArrowRight } from 'lucide-react';
import { HelpTooltip } from '@/components/ui/HelpTooltip';

const DOC_SECTIONS = [
  { id: 'ds1', title: 'Visão Geral Técnica', lastGen: '2026-04-01', status: 'published', wordCount: 1240, trigger: 'Push em main' },
  { id: 'ds2', title: 'Arquitetura de Serviços', lastGen: '2026-03-28', status: 'published', wordCount: 2870, trigger: 'Aprovação interna' },
  { id: 'ds3', title: 'Contratos de API (OpenAPI)', lastGen: '2026-03-25', status: 'outdated', wordCount: 3120, trigger: 'Push em main' },
  { id: 'ds4', title: 'Guia de Deploy e Operação', lastGen: '2026-03-20', status: 'published', wordCount: 890, trigger: 'Aprovação interna' },
  { id: 'ds5', title: 'Análise de Segurança', lastGen: '—', status: 'pending', wordCount: 0, trigger: 'Aprovação interna' },
  { id: 'ds6', title: 'Cobertura de Testes e Evidências', lastGen: '2026-03-30', status: 'draft', wordCount: 450, trigger: 'Evento QA' },
];

const DOC_STATUS: Record<string, { label: string; cls: string }> = {
  published: { label: 'Publicado', cls: 'bg-emerald-900/40 text-emerald-400' },
  outdated: { label: 'Desatualizado', cls: 'bg-amber-900/40 text-amber-400' },
  pending: { label: 'Pendente', cls: 'bg-slate-800 text-slate-500' },
  draft: { label: 'Rascunho', cls: 'bg-blue-900/40 text-blue-400' },
};

export function LiveDocsPage() {
  const { id } = useParams<{ id: string }>();
  const [strategy, setStrategy] = useState<'direct' | 'pr'>('pr');
  const [regenerating, setRegenerating] = useState<string | null>(null);

  const handleRegen = (docId: string) => {
    setRegenerating(docId);
    setTimeout(() => setRegenerating(null), 1500);
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-1.5">
            Documentação Viva
            <HelpTooltip text="A Documentação Viva (LiveDocs) é gerada e mantida automaticamente pelo GCA ao longo de todo o ciclo de desenvolvimento. Diferente de documentação estática escrita manualmente, ela é atualizada a cada ingestão de documento, aprovação de módulo no Gatekeeper e evolução do OCG. Nunca fica desatualizada porque está diretamente vinculada ao estado atual do projeto e ao repositório Git. É a fonte de verdade do projeto para o cliente e para o time." />
          </h2>
          <p className="text-slate-500 text-sm mt-0.5">Regeneração e publicação documental técnica e negocial do projeto</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleRegen('all')}
            disabled={regenerating !== null}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 text-white text-sm hover:bg-violet-500 disabled:opacity-50 transition-colors"
          >
            {regenerating === 'all' ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Sincronizar
          </button>
          <HelpTooltip text="Força a ressincronização da LiveDocs com o estado atual do repositório Git. Use quando suspeitar que a documentação exibida está desatualizada em relação ao repositório. A sincronização automática ocorre após cada evento relevante (ingestão, aprovação de módulo)." />
        </div>
      </div>

      {/* Publication Strategy */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-4">Estratégia de Publicação</h3>
        <div className="grid grid-cols-2 gap-4">
          <button
            onClick={() => setStrategy('direct')}
            className={`p-4 rounded-xl border text-left transition-all ${strategy === 'direct' ? 'border-violet-600/50 bg-violet-950/10' : 'border-slate-800 hover:border-slate-700'}`}
          >
            <div className="flex items-center gap-2 mb-2">
              <GitBranch className="w-4 h-4 text-blue-400" />
              <p className="text-slate-200 text-sm font-medium">Commit Direto</p>
              {strategy === 'direct' && <CheckCircle className="w-4 h-4 text-violet-400 ml-auto" />}
            </div>
            <p className="text-slate-400 text-xs">Commit automático na branch <code className="text-violet-400">docs/gca</code>. Mais rápido, sem aprovação.</p>
          </button>
          <button
            onClick={() => setStrategy('pr')}
            className={`p-4 rounded-xl border text-left transition-all ${strategy === 'pr' ? 'border-violet-600/50 bg-violet-950/10' : 'border-slate-800 hover:border-slate-700'}`}
          >
            <div className="flex items-center gap-2 mb-2">
              <GitPullRequest className="w-4 h-4 text-violet-400" />
              <p className="text-slate-200 text-sm font-medium">Pull Request</p>
              {strategy === 'pr' && <CheckCircle className="w-4 h-4 text-violet-400 ml-auto" />}
            </div>
            <p className="text-slate-400 text-xs">Branch <code className="text-violet-400">docs/gca-{'{uuid}'}</code> + PR automático para revisão antes da publicação.</p>
          </button>
        </div>
        <div className="mt-4 p-3 rounded-lg bg-slate-800/50 border border-slate-700/30 flex items-center gap-3">
          <div className="text-slate-400 text-xs">
            <span className="text-slate-500">Disparos configurados:</span>{' '}
            <span className="text-violet-300">Aprovação interna</span>
            <span className="text-slate-600 mx-2">·</span>
            <span className="text-violet-300">Push/Merge aprovado</span>
            <span className="text-slate-600 mx-2">·</span>
            <span className="text-violet-300">Evento QA</span>
          </div>
        </div>
      </div>

      {/* Docs Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="text-slate-200 text-sm font-semibold">Seções Documentais ({DOC_SECTIONS.length})</h3>
          <span className="text-xs text-slate-500">
            {DOC_SECTIONS.filter(d => d.status === 'published').length} publicadas · {DOC_SECTIONS.filter(d => d.status === 'outdated').length} desatualizadas
          </span>
        </div>
        <div className="divide-y divide-slate-800">
          {DOC_SECTIONS.map(doc => (
            <div key={doc.id} className="flex items-center gap-4 px-5 py-4 hover:bg-slate-800/30 transition-colors">
              <div className="w-9 h-9 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0">
                <BookOpen className="w-4 h-4 text-slate-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-slate-200 text-sm font-medium">{doc.title}</p>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  <span className="text-slate-500 text-xs">Gatilho: {doc.trigger}</span>
                  {doc.lastGen !== '—' && (
                    <><span className="text-slate-600">·</span><span className="text-slate-500 text-xs">Última geração: {doc.lastGen}</span></>
                  )}
                  {doc.wordCount > 0 && (
                    <><span className="text-slate-600">·</span><span className="text-slate-500 text-xs">{doc.wordCount.toLocaleString('pt-BR')} palavras</span></>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className={`text-xs px-2 py-0.5 rounded ${DOC_STATUS[doc.status].cls}`}>{DOC_STATUS[doc.status].label}</span>
                {doc.status !== 'pending' && (
                  <button className="p-1.5 rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-700 transition-colors">
                    <Eye className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  onClick={() => handleRegen(doc.id)}
                  disabled={regenerating !== null}
                  className="p-1.5 rounded-md text-slate-500 hover:text-violet-400 hover:bg-violet-900/20 transition-colors disabled:opacity-40"
                >
                  {regenerating === doc.id ? <span className="w-3.5 h-3.5 border-2 border-violet-400/30 border-t-violet-400 rounded-full animate-spin inline-block" /> : <RefreshCw className="w-3.5 h-3.5" />}
                </button>
                {doc.status === 'published' && (
                  <button className="p-1.5 rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-700 transition-colors">
                    <Download className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Publication Flow */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-4">Fluxo de Publicação</h3>
        <div className="flex items-center gap-3 flex-wrap">
          {[
            { label: 'Código aprovado / Push', icon: <CheckCircle className="w-3.5 h-3.5" /> },
            { label: 'Leitura do OCG', icon: <BookOpen className="w-3.5 h-3.5" /> },
            { label: 'Geração / Consolidação', icon: <Sparkles className="w-3.5 h-3.5" /> },
            { label: strategy === 'pr' ? 'Branch + Pull Request' : 'Commit em docs/', icon: <GitBranch className="w-3.5 h-3.5" /> },
          ].map((step, i, arr) => (
            <React.Fragment key={step.label}>
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 text-xs">
                {step.icon}{step.label}
              </div>
              {i < arr.length - 1 && <ArrowRight className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
