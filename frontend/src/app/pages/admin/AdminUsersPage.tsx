import React, { useState } from 'react';
import { Search, Lock, Shield, Unlock, Eye, AlertTriangle, Archive, Zap } from 'lucide-react';
import { USERS, PROJECTS } from '../../data/mockData';

interface GPWithContext {
  id: string;
  name: string;
  email: string;
  active: boolean;
  createdAt: string;
  projectsActive: number;
  projectsArchived: number;
  projectsList: string[];
  lastCriticalAction?: { action: string; date: string };
}

export function AdminUsersPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [selectedGp, setSelectedGp] = useState<GPWithContext | null>(null);

  // Extrair apenas GPs e enriquecer com contexto de projetos
  const gpsWithContext: GPWithContext[] = USERS.filter(u => u.role === 'gp').map(gp => {
    const gpsProjects = PROJECTS.filter(p => p.gpId === gp.id);
    const activeProjects = gpsProjects.filter(p => p.status === 'active');
    const archivedProjects = gpsProjects.filter(p => p.status === 'archived');

    return {
      id: gp.id,
      name: gp.name,
      email: gp.email,
      active: gp.active,
      createdAt: gp.createdAt,
      projectsActive: activeProjects.length,
      projectsArchived: archivedProjects.length,
      projectsList: gpsProjects.map(p => p.name),
      // Simulado: em produção viria do audit log
      lastCriticalAction: gpsProjects.some(p => p.gatekeeper.status === 'blocked')
        ? { action: 'Override Gatekeeper', date: '2026-03-28T15:30:00Z' }
        : undefined,
    };
  });

  // Aplicar filtros
  const filtered = gpsWithContext.filter(gp => {
    const matchSearch = gp.name.toLowerCase().includes(search.toLowerCase()) ||
                       gp.email.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === 'all' ||
                       (statusFilter === 'active' ? gp.active : !gp.active);
    return matchSearch && matchStatus;
  });

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Gestão de Gerentes de Projeto (GPs)</h1>
          <p className="text-slate-500 text-sm mt-0.5">Auditoria · Controle de acesso · Histórico de projetos</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por nome ou e-mail..."
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as typeof statusFilter)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none"
        >
          <option value="all">Todos</option>
          <option value="active">Ativos</option>
          <option value="inactive">Inativos</option>
        </select>
      </div>

      {/* GPs Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-800/50">
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">GERENTE</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">PROJETOS</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">STATUS</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">ÚLTIMA AÇÃO</th>
              <th className="text-left px-4 py-3 text-xs text-slate-500 font-medium">DESDE</th>
              <th className="text-right px-4 py-3 text-xs text-slate-500 font-medium">AÇÕES</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length > 0 ? (
              filtered.map((gp, i) => (
                <tr
                  key={gp.id}
                  className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${
                    i === filtered.length - 1 ? 'border-b-0' : ''
                  }`}
                >
                  {/* Nome e E-mail */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-indigo-700/60 flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">
                        {gp.name.charAt(0)}
                      </div>
                      <div>
                        <p className="text-slate-200 text-sm font-medium">{gp.name}</p>
                        <p className="text-slate-500 text-xs">{gp.email}</p>
                      </div>
                    </div>
                  </td>

                  {/* Projetos */}
                  <td className="px-4 py-3">
                    <div className="space-y-1">
                      {gp.projectsActive > 0 && (
                        <p className="text-slate-300 text-xs">
                          <span className="font-medium text-emerald-400">{gp.projectsActive}</span> ativo{gp.projectsActive !== 1 ? 's' : ''}
                        </p>
                      )}
                      {gp.projectsArchived > 0 && (
                        <p className="text-slate-400 text-xs">
                          <span className="font-medium">{gp.projectsArchived}</span> arquivado{gp.projectsArchived !== 1 ? 's' : ''}
                        </p>
                      )}
                      {gp.projectsActive === 0 && gp.projectsArchived === 0 && (
                        <p className="text-slate-500 text-xs italic">Nenhum projeto</p>
                      )}
                    </div>
                  </td>

                  {/* Status */}
                  <td className="px-4 py-3">
                    {gp.active ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                        Ativo
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-700/50 text-slate-400 border border-slate-600">
                        <span className="w-2 h-2 rounded-full bg-slate-500"></span>
                        Bloqueado
                      </span>
                    )}
                  </td>

                  {/* Última Ação */}
                  <td className="px-4 py-3">
                    {gp.lastCriticalAction ? (
                      <div className="flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                        <div>
                          <p className="text-slate-300 text-xs font-medium">{gp.lastCriticalAction.action}</p>
                          <p className="text-slate-500 text-xs">
                            {new Date(gp.lastCriticalAction.date).toLocaleDateString('pt-BR')}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <span className="text-slate-500 text-xs">—</span>
                    )}
                  </td>

                  {/* Desde */}
                  <td className="px-4 py-3">
                    <span className="text-slate-500 text-xs">{new Date(gp.createdAt).toLocaleDateString('pt-BR')}</span>
                  </td>

                  {/* Ações */}
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => setSelectedGp(gp)}
                        className="p-1.5 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-700 transition-colors"
                        title="Ver auditoria"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <button
                        className={`p-1.5 rounded transition-colors ${
                          gp.active
                            ? 'text-slate-400 hover:text-amber-300 hover:bg-amber-500/10'
                            : 'text-slate-400 hover:text-emerald-300 hover:bg-emerald-500/10'
                        }`}
                        title={gp.active ? 'Bloquear acesso' : 'Desbloquear acesso'}
                      >
                        {gp.active ? (
                          <Lock className="w-4 h-4" />
                        ) : (
                          <Unlock className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        className="p-1.5 rounded text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        title="Revogar papel GP"
                      >
                        <Zap className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500 text-sm">
                  Nenhum GP encontrado com os critérios de busca
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Info Panel */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4 flex gap-3">
        <Shield className="w-5 h-5 text-indigo-400 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-slate-200 text-sm font-medium mb-1">Escopo de Admin para GPs</p>
          <p className="text-slate-400 text-xs">
            Admin audita apenas ações críticas (override Gatekeeper, aprovação de quarentena LGPD). Convites, credenciais e membros de projeto são responsabilidade do GP. Use a auditoria para revisar histórico de decisões.
          </p>
        </div>
      </div>

      {/* Detail Modal */}
      {selectedGp && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[80vh] overflow-auto shadow-2xl">
            <div className="sticky top-0 bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
              <div>
                <h3 className="text-slate-100 font-semibold text-lg">{selectedGp.name}</h3>
                <p className="text-slate-500 text-sm mt-0.5">{selectedGp.email}</p>
              </div>
              <button
                onClick={() => setSelectedGp(null)}
                className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Projetos */}
              <div>
                <h4 className="text-slate-200 font-medium text-sm mb-3">Projetos Gerenciados</h4>
                {selectedGp.projectsList.length > 0 ? (
                  <div className="grid grid-cols-1 gap-2">
                    {selectedGp.projectsList.map((proj, i) => (
                      <div
                        key={i}
                        className="px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg flex items-center justify-between"
                      >
                        <span className="text-slate-300 text-sm">{proj}</span>
                        <Archive className="w-4 h-4 text-slate-500" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-500 text-sm">Nenhum projeto</p>
                )}
              </div>

              {/* Últimas ações críticas (simulado) */}
              <div>
                <h4 className="text-slate-200 font-medium text-sm mb-3">Histórico de Ações Críticas</h4>
                <div className="space-y-2 text-sm text-slate-500">
                  <p>Integração com auditoria global em Session 09+</p>
                  <p className="text-xs italic mt-2">
                    Aqui aparecerão: overrides Gatekeeper, aprovações de quarentena, mudanças de credenciais
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
