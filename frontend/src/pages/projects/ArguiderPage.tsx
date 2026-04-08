import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Zap, MessageSquare, Paperclip, Send, CheckCircle, Clock, AlertCircle, RotateCcw } from 'lucide-react';
import { getProjectById } from '../../data/mockData';

const QUESTIONS = [
  {
    id: 'q1',
    pillar: 'Cobertura de Segurança',
    question: 'O modelo de ameaças do projeto foi formalmente validado por um especialista de segurança? Se sim, anexe o documento aprovado com data e assinatura.',
    status: 'pending' as const,
    priority: 'blocker',
    requestedAt: '2026-03-18T14:00:00Z',
    response: null,
  },
  {
    id: 'q2',
    pillar: 'Clareza Técnica',
    question: 'Os contratos de API (OpenAPI/Swagger) para os endpoints críticos de autenticação e perfil foram definidos? Quais endpoints ainda estão indefinidos?',
    status: 'answered' as const,
    priority: 'warning',
    requestedAt: '2026-03-18T14:01:00Z',
    response: 'Os contratos OpenAPI para /auth/login, /auth/refresh e /auth/logout foram definidos. O endpoint /users/profile/{id} ainda está em definição. Prazo: 2026-04-10.',
    answeredAt: '2026-03-20T09:00:00Z',
  },
  {
    id: 'q3',
    pillar: 'Qualidade e Testabilidade',
    question: 'Qual é a cobertura mínima de testes exigida para aprovação? O plano de QA inclui cenários de teste para os fluxos críticos de pagamento e autenticação?',
    status: 'pending' as const,
    priority: 'warning',
    requestedAt: '2026-03-18T14:02:00Z',
    response: null,
  },
];

export function ArguiderPage() {
  const { id } = useParams<{ id: string }>();
  const project = getProjectById(id!);
  const [selected, setSelected] = useState<string | null>('q1');
  const [response, setResponse] = useState('');
  const [answeredIds, setAnsweredIds] = useState<Set<string>>(new Set(['q2']));
  if (!project) return null;

  const selectedQ = QUESTIONS.find(q => q.id === selected);
  const pending = QUESTIONS.filter(q => !answeredIds.has(q.id));

  const handleSend = () => {
    if (!selected || !response.trim()) return;
    setAnsweredIds(prev => new Set([...prev, selected]));
    setResponse('');
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">M7 — Arguidor Técnico</h2>
        <p className="text-slate-500 text-sm mt-0.5">Perguntas dirigidas para gaps identificados pelo Gatekeeper · Respostas versionadas</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-center">
          <p className="text-2xl font-semibold text-slate-100">{QUESTIONS.length}</p>
          <p className="text-slate-500 text-xs mt-1">Total de perguntas</p>
        </div>
        <div className="bg-red-950/20 border border-red-800/30 rounded-xl p-4 text-center">
          <p className="text-2xl font-semibold text-red-400">{pending.length}</p>
          <p className="text-slate-500 text-xs mt-1">Pendentes</p>
        </div>
        <div className="bg-emerald-950/20 border border-emerald-800/30 rounded-xl p-4 text-center">
          <p className="text-2xl font-semibold text-emerald-400">{answeredIds.size}</p>
          <p className="text-slate-500 text-xs mt-1">Respondidas</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Question List */}
        <div className="lg:col-span-2 space-y-2">
          <p className="text-slate-500 text-xs uppercase tracking-wider font-semibold px-1">Perguntas em aberto</p>
          {QUESTIONS.map(q => {
            const isAnswered = answeredIds.has(q.id);
            return (
              <button
                key={q.id}
                onClick={() => setSelected(q.id)}
                className={`w-full text-left p-4 rounded-xl border transition-all ${
                  selected === q.id ? 'border-indigo-600/50 bg-indigo-900/10' : isAnswered ? 'border-slate-800 opacity-60' : 'border-slate-800 hover:border-slate-700 hover:bg-slate-800/40'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex-shrink-0">
                    {isAnswered ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : q.priority === 'blocker' ? <AlertCircle className="w-4 h-4 text-red-400" /> : <Clock className="w-4 h-4 text-amber-400" />}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${q.priority === 'blocker' ? 'bg-red-900/40 text-red-400' : 'bg-amber-900/40 text-amber-400'}`}>
                        {q.priority}
                      </span>
                      <span className="text-slate-500 text-xs">{q.pillar}</span>
                    </div>
                    <p className="text-slate-300 text-xs leading-snug line-clamp-2">{q.question}</p>
                    <p className="text-slate-600 text-xs mt-1.5">{new Date(q.requestedAt).toLocaleDateString('pt-BR')}</p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Q&A Panel */}
        <div className="lg:col-span-3">
          {selectedQ ? (
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden h-full flex flex-col">
              <div className="p-5 border-b border-slate-800">
                <div className="flex items-center gap-2 mb-2">
                  <Zap className="w-4 h-4 text-indigo-400" />
                  <span className="text-slate-500 text-xs">Pilar: {selectedQ.pillar}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ml-auto ${selectedQ.priority === 'blocker' ? 'bg-red-900/40 text-red-400' : 'bg-amber-900/40 text-amber-400'}`}>
                    {selectedQ.priority}
                  </span>
                </div>
                <p className="text-slate-200 text-sm leading-relaxed">{selectedQ.question}</p>
              </div>

              {/* Previous answers */}
              <div className="flex-1 p-5 space-y-4 overflow-y-auto">
                {(answeredIds.has(selectedQ.id) || selectedQ.response) && (
                  <div className="p-4 rounded-xl bg-emerald-950/10 border border-emerald-800/20">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400 text-xs font-medium">Resposta registrada</span>
                      {selectedQ.answeredAt && <span className="text-slate-500 text-xs ml-auto">{new Date(selectedQ.answeredAt).toLocaleDateString('pt-BR')}</span>}
                    </div>
                    <p className="text-slate-300 text-sm leading-relaxed">{selectedQ.response ?? response}</p>
                  </div>
                )}

                {!answeredIds.has(selectedQ.id) && (
                  <div className="p-4 rounded-xl bg-indigo-950/10 border border-indigo-800/20">
                    <div className="flex items-center gap-2 mb-2">
                      <MessageSquare className="w-3.5 h-3.5 text-indigo-400" />
                      <span className="text-indigo-400 text-xs font-medium">Instruções</span>
                    </div>
                    <p className="text-slate-400 text-xs">Responda com evidências específicas. Após aprovação do Arguidor, o ciclo de merge é reaberto com os novos artefatos versionados.</p>
                  </div>
                )}
              </div>

              {/* Response Input */}
              {!answeredIds.has(selectedQ.id) && (
                <div className="p-4 border-t border-slate-800">
                  <textarea
                    value={response}
                    onChange={e => setResponse(e.target.value)}
                    rows={4}
                    placeholder="Escreva sua resposta com evidências e referências documentais..."
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 resize-none focus:outline-none focus:border-indigo-500 mb-3"
                  />
                  <div className="flex items-center gap-2">
                    <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 text-sm hover:text-slate-200 hover:border-slate-600 transition-colors">
                      <Paperclip className="w-3.5 h-3.5" /> Anexar
                    </button>
                    <button
                      onClick={handleSend}
                      disabled={!response.trim()}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500 disabled:opacity-50 transition-colors ml-auto"
                    >
                      <Send className="w-3.5 h-3.5" /> Enviar e Reabrir Ciclo
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-64 bg-slate-900 border border-slate-800 rounded-xl">
              <div className="text-center">
                <MessageSquare className="w-8 h-8 text-slate-700 mx-auto mb-2" />
                <p className="text-slate-500 text-sm">Selecione uma pergunta para responder</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
