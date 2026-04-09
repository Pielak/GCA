import React, { useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { Zap, MessageSquare, Send, CheckCircle, Clock, AlertCircle, XCircle, Loader2, Eye, EyeOff } from 'lucide-react';
import { HelpTooltip } from '@/components/ui/HelpTooltip';
import { useGatekeeperData, useResolveItem, useIgnoreItem, type GatekeeperItem } from '@/hooks/useArguider';

type ItemFilter = 'all' | 'pending' | 'resolved' | 'ignored';

const PRIORITY_MAP: Record<string, { label: string; bg: string; text: string }> = {
  BLOCKER:  { label: 'Blocker',  bg: 'bg-red-900/40',    text: 'text-red-400' },
  CRITICAL: { label: 'Critical', bg: 'bg-orange-900/40', text: 'text-orange-400' },
  WARNING:  { label: 'Warning',  bg: 'bg-amber-900/40',  text: 'text-amber-400' },
  INFO:     { label: 'Info',     bg: 'bg-blue-900/40',    text: 'text-blue-400' },
};

const TYPE_LABELS: Record<string, string> = {
  gap: 'Gap',
  show_stopper: 'Show-Stopper',
  poor_definition: 'Má Definição',
  improvement: 'Sugestão',
};

function getItemPriority(item: GatekeeperItem): string {
  return item.data?.severity || item.data?.priority || (item.item_type === 'show_stopper' ? 'BLOCKER' : 'WARNING');
}

function getItemDescription(item: GatekeeperItem): string {
  return item.data?.description || item.data?.message || item.data?.text || item.item_id || 'Sem descrição';
}

function getItemPillar(item: GatekeeperItem): string {
  return item.data?.pillar || item.data?.category || item.item_type;
}

export function ArguiderPage() {
  const { id: projectId } = useParams<{ id: string }>();
  const [selected, setSelected] = useState<string | null>(null);
  const [response, setResponse] = useState('');
  const [ignoreReason, setIgnoreReason] = useState('');
  const [showIgnoreInput, setShowIgnoreInput] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ItemFilter>('all');
  const [showResolved, setShowResolved] = useState(false);

  const { data: gatekeeper, isLoading } = useGatekeeperData(projectId);
  const resolveMutation = useResolveItem(projectId);
  const ignoreMutation = useIgnoreItem(projectId);

  // Combinar todos os items em uma lista unificada
  const allItems = useMemo(() => {
    if (!gatekeeper) return [];
    return [
      ...gatekeeper.show_stoppers,
      ...gatekeeper.gaps,
      ...gatekeeper.poor_definitions,
      ...gatekeeper.improvement_suggestions,
    ].sort((a, b) => {
      // Pendentes primeiro, depois por prioridade
      if (a.status !== b.status) {
        if (a.status === 'pending') return -1;
        if (b.status === 'pending') return 1;
      }
      const priorityOrder = ['BLOCKER', 'CRITICAL', 'WARNING', 'INFO'];
      return priorityOrder.indexOf(getItemPriority(a)) - priorityOrder.indexOf(getItemPriority(b));
    });
  }, [gatekeeper]);

  const filteredItems = useMemo(() => {
    if (statusFilter === 'all') {
      return showResolved ? allItems : allItems.filter(i => i.status === 'pending');
    }
    return allItems.filter(i => i.status === statusFilter);
  }, [allItems, statusFilter, showResolved]);

  const selectedItem = allItems.find(i => i.id === selected);
  const pendingCount = allItems.filter(i => i.status === 'pending').length;
  const resolvedCount = allItems.filter(i => i.status === 'resolved').length;
  const ignoredCount = allItems.filter(i => i.status === 'ignored').length;

  const handleResolve = () => {
    if (!selected || !response.trim()) return;
    resolveMutation.mutate({ itemId: selected, note: response.trim() }, {
      onSuccess: () => {
        setResponse('');
        setSelected(null);
      },
    });
  };

  const handleIgnore = () => {
    if (!selected || !ignoreReason.trim()) return;
    ignoreMutation.mutate({ itemId: selected, reason: ignoreReason.trim() }, {
      onSuccess: () => {
        setIgnoreReason('');
        setShowIgnoreInput(false);
        setSelected(null);
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
      </div>
    );
  }

  if (!gatekeeper || allItems.length === 0) {
    return (
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            Arguidor Técnico
            <HelpTooltip
              text="O Arguidor Técnico apresenta os gaps, show-stoppers e definições imprecisas identificados pelo Gatekeeper após a análise dos documentos ingeridos. Cada item requer uma resposta com evidências documentais para ser resolvido. Items não resolvidos bloqueiam a geração de código."
              maxWidth="max-w-96"
            />
          </h2>
          <p className="text-slate-500 text-sm mt-0.5">Perguntas dirigidas para gaps identificados pelo Gatekeeper</p>
        </div>
        <div className="flex items-center justify-center h-48 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-center">
            <CheckCircle className="w-10 h-10 text-emerald-500/30 mx-auto mb-3" />
            <p className="text-slate-400 text-sm">Nenhum item pendente do Gatekeeper.</p>
            <p className="text-slate-600 text-xs mt-1">Faça upload e análise documentos na página de Ingestão primeiro.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            Arguidor Técnico
            <HelpTooltip
              text="O Arguidor Técnico apresenta os gaps, show-stoppers e definições imprecisas identificados pelo Gatekeeper após a análise dos documentos ingeridos. Cada item requer uma resposta com evidências documentais para ser resolvido. Items não resolvidos bloqueiam a geração de código."
              maxWidth="max-w-96"
            />
          </h2>
          <p className="text-slate-500 text-sm mt-0.5">Perguntas dirigidas para gaps identificados pelo Gatekeeper · Respostas versionadas</p>
        </div>
        {gatekeeper.summary.has_blockers && (
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-900/20 border border-red-800/30 text-red-400 text-xs font-medium">
            <AlertCircle className="w-3.5 h-3.5" />
            Bloqueadores ativos
          </span>
        )}
      </div>

      {/* Contexto OCG */}
      {(gatekeeper as any).ocg?.status && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-slate-400 text-xs">Score OCG:</span>
              <span className={`text-lg font-bold ${
                ((gatekeeper as any).ocg.status.overall_score || 0) >= 80 ? 'text-emerald-400' :
                ((gatekeeper as any).ocg.status.overall_score || 0) >= 60 ? 'text-amber-400' : 'text-red-400'
              }`}>{((gatekeeper as any).ocg.status.overall_score || 0).toFixed(1)}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                (gatekeeper as any).ocg.status.status === 'READY' ? 'bg-emerald-500/20 text-emerald-300' :
                (gatekeeper as any).ocg.status.status === 'NEEDS_REVIEW' ? 'bg-amber-500/20 text-amber-300' :
                (gatekeeper as any).ocg.status.status === 'AT_RISK' ? 'bg-amber-500/20 text-amber-300' :
                'bg-red-500/20 text-red-300'
              }`}>{(gatekeeper as any).ocg.status.status}</span>
            </div>
            <div className="flex items-center gap-4 text-xs text-slate-500">
              <span>Versão: v{(gatekeeper as any).ocg.status.version || 1}</span>
              {(gatekeeper as any).ocg.health?.confidence != null && (
                <span>Confiança: {Math.round(((gatekeeper as any).ocg.health.confidence || 0) * 100)}%</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-center">
          <p className="text-2xl font-semibold text-slate-100">{allItems.length}</p>
          <p className="text-slate-500 text-xs mt-1">Total de itens</p>
        </div>
        <div className="bg-red-950/20 border border-red-800/30 rounded-xl p-4 text-center">
          <p className="text-2xl font-semibold text-red-400">{pendingCount}</p>
          <p className="text-slate-500 text-xs mt-1">Pendentes</p>
        </div>
        <div className="bg-emerald-950/20 border border-emerald-800/30 rounded-xl p-4 text-center">
          <p className="text-2xl font-semibold text-emerald-400">{resolvedCount}</p>
          <p className="text-slate-500 text-xs mt-1">Resolvidos</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Item List */}
        <div className="lg:col-span-2 space-y-2">
          <div className="flex items-center justify-between px-1">
            <p className="text-slate-500 text-xs uppercase tracking-wider font-semibold">Itens ({filteredItems.length})</p>
            <button
              onClick={() => setShowResolved(!showResolved)}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              {showResolved ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
              {showResolved ? 'Ocultar resolvidos' : 'Mostrar resolvidos'}
            </button>
          </div>

          {filteredItems.length === 0 ? (
            <div className="p-6 text-center text-slate-500 text-sm">
              Todos os itens foram resolvidos.
            </div>
          ) : (
            filteredItems.map(item => {
              const priority = getItemPriority(item);
              const pConfig = PRIORITY_MAP[priority] || PRIORITY_MAP.WARNING;
              const isResolved = item.status === 'resolved';
              const isIgnored = item.status === 'ignored';

              return (
                <button
                  key={item.id}
                  onClick={() => { setSelected(item.id); setShowIgnoreInput(false); setResponse(''); setIgnoreReason(''); }}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    selected === item.id
                      ? 'border-indigo-600/50 bg-indigo-900/10'
                      : isResolved || isIgnored
                        ? 'border-slate-800 opacity-50'
                        : 'border-slate-800 hover:border-slate-700 hover:bg-slate-800/40'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex-shrink-0">
                      {isResolved ? (
                        <CheckCircle className="w-4 h-4 text-emerald-400" />
                      ) : isIgnored ? (
                        <XCircle className="w-4 h-4 text-slate-500" />
                      ) : priority === 'BLOCKER' ? (
                        <AlertCircle className="w-4 h-4 text-red-400" />
                      ) : (
                        <Clock className="w-4 h-4 text-amber-400" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${pConfig.bg} ${pConfig.text}`}>
                          {pConfig.label}
                        </span>
                        <span className="text-slate-600 text-[10px] uppercase">{TYPE_LABELS[item.item_type] || item.item_type}</span>
                        <span className="text-slate-600 text-xs ml-auto">{getItemPillar(item)}</span>
                      </div>
                      <p className="text-slate-300 text-xs leading-snug line-clamp-2">{getItemDescription(item)}</p>
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Detail Panel */}
        <div className="lg:col-span-3">
          {selectedItem ? (
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden h-full flex flex-col">
              {/* Header */}
              <div className="p-5 border-b border-slate-800">
                <div className="flex items-center gap-2 mb-2">
                  <Zap className="w-4 h-4 text-indigo-400" />
                  <span className="text-slate-500 text-xs">{TYPE_LABELS[selectedItem.item_type]}: {getItemPillar(selectedItem)}</span>
                  {(() => {
                    const p = getItemPriority(selectedItem);
                    const c = PRIORITY_MAP[p] || PRIORITY_MAP.WARNING;
                    return <span className={`text-xs px-1.5 py-0.5 rounded ml-auto ${c.bg} ${c.text}`}>{c.label}</span>;
                  })()}
                </div>
                <p className="text-slate-200 text-sm leading-relaxed">{getItemDescription(selectedItem)}</p>
                {selectedItem.data?.context && (
                  <p className="text-slate-500 text-xs mt-2 leading-relaxed">{selectedItem.data.context}</p>
                )}
              </div>

              {/* Content */}
              <div className="flex-1 p-5 space-y-4 overflow-y-auto">
                {/* Resolved answer */}
                {selectedItem.status === 'resolved' && selectedItem.resolution_note && (
                  <div className="p-4 rounded-xl bg-emerald-950/10 border border-emerald-800/20">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400 text-xs font-medium">Resolvido</span>
                      {selectedItem.resolved_at && (
                        <span className="text-slate-500 text-xs ml-auto">{new Date(selectedItem.resolved_at).toLocaleDateString('pt-BR')}</span>
                      )}
                    </div>
                    <p className="text-slate-300 text-sm leading-relaxed">{selectedItem.resolution_note}</p>
                  </div>
                )}

                {/* Ignored */}
                {selectedItem.status === 'ignored' && (
                  <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/30">
                    <div className="flex items-center gap-2 mb-2">
                      <XCircle className="w-3.5 h-3.5 text-slate-400" />
                      <span className="text-slate-400 text-xs font-medium">Ignorado</span>
                    </div>
                    <p className="text-slate-400 text-sm">{selectedItem.resolution_note?.replace('[IGNORADO] ', '')}</p>
                  </div>
                )}

                {/* Instructions for pending items */}
                {selectedItem.status === 'pending' && (
                  <div className="p-4 rounded-xl bg-indigo-950/10 border border-indigo-800/20">
                    <div className="flex items-center gap-2 mb-2">
                      <MessageSquare className="w-3.5 h-3.5 text-indigo-400" />
                      <span className="text-indigo-400 text-xs font-medium">Instruções</span>
                    </div>
                    <p className="text-slate-400 text-xs">
                      Responda com evidências específicas (links, documentos, decisões técnicas).
                      Após resolução, o Gatekeeper reavalia o pilar afetado.
                      {selectedItem.item_type === 'show_stopper' && ' Show-stoppers não resolvidos bloqueiam a geração de código.'}
                    </p>
                  </div>
                )}

                {/* Additional data from analysis */}
                {selectedItem.data?.affected_pillars && (
                  <div className="flex flex-wrap gap-1.5">
                    {(Array.isArray(selectedItem.data.affected_pillars) ? selectedItem.data.affected_pillars : [selectedItem.data.affected_pillars]).map((p: string, i: number) => (
                      <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">{p}</span>
                    ))}
                  </div>
                )}
              </div>

              {/* Response Input (only for pending items) */}
              {selectedItem.status === 'pending' && (
                <div className="p-4 border-t border-slate-800 space-y-3">
                  {!showIgnoreInput ? (
                    <>
                      <textarea
                        value={response}
                        onChange={e => setResponse(e.target.value)}
                        rows={4}
                        placeholder="Escreva sua resposta com evidências e referências documentais..."
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 resize-none focus:outline-none focus:border-indigo-500"
                      />
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setShowIgnoreInput(true)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 text-sm hover:text-red-400 hover:border-red-800/30 transition-colors"
                        >
                          <XCircle className="w-3.5 h-3.5" /> Ignorar
                        </button>
                        <button
                          onClick={handleResolve}
                          disabled={!response.trim() || resolveMutation.isPending}
                          className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500 disabled:opacity-50 transition-colors ml-auto"
                        >
                          {resolveMutation.isPending ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Send className="w-3.5 h-3.5" />
                          )}
                          Resolver Item
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <p className="text-slate-400 text-xs">Justifique por que este item pode ser ignorado:</p>
                      <textarea
                        value={ignoreReason}
                        onChange={e => setIgnoreReason(e.target.value)}
                        rows={3}
                        placeholder="Motivo para ignorar este item (obrigatório)..."
                        className="w-full bg-slate-800 border border-red-800/30 rounded-lg px-3 py-2.5 text-sm text-slate-200 resize-none focus:outline-none focus:border-red-500"
                      />
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => { setShowIgnoreInput(false); setIgnoreReason(''); }}
                          className="px-3 py-1.5 rounded-lg text-slate-400 text-sm hover:text-slate-200 transition-colors"
                        >
                          Cancelar
                        </button>
                        <button
                          onClick={handleIgnore}
                          disabled={!ignoreReason.trim() || ignoreMutation.isPending}
                          className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-red-600 text-white text-sm hover:bg-red-500 disabled:opacity-50 transition-colors ml-auto"
                        >
                          {ignoreMutation.isPending ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <XCircle className="w-3.5 h-3.5" />
                          )}
                          Confirmar Ignorar
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-64 bg-slate-900 border border-slate-800 rounded-xl">
              <div className="text-center">
                <MessageSquare className="w-8 h-8 text-slate-700 mx-auto mb-2" />
                <p className="text-slate-500 text-sm">Selecione um item para resolver</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
