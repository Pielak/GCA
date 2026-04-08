import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { TestTube2, Play, Clock, CheckCircle, XCircle, AlertTriangle, Download, Box, BarChart3 } from 'lucide-react';
import { getProjectById } from '../../data/mockData';
import { StatusBadge } from '../../components/ui/StatusBadge';

const TEST_TYPES = ['Smoke', 'Unitário', 'Integração', 'E2E', 'Segurança', 'DAST', 'Performance'];

const statusIcon = (status: string) => {
  if (status === 'passed') return <CheckCircle className="w-4 h-4 text-emerald-400" />;
  if (status === 'failed') return <XCircle className="w-4 h-4 text-red-400" />;
  if (status === 'queued') return <Clock className="w-4 h-4 text-slate-400" />;
  if (status === 'running') return <span className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin inline-block" />;
  if (status === 'blocked') return <AlertTriangle className="w-4 h-4 text-amber-400" />;
  return <Clock className="w-4 h-4 text-slate-400" />;
};

const IMAGE_BY_STACK: Record<string, string> = {
  Python: 'python:3.12-slim',
  TypeScript: 'node:20-bullseye',
  JavaScript: 'node:20-bullseye',
  Java: 'eclipse-temurin:21-jdk',
  Go: 'golang:1.22-alpine',
  '.NET': 'mcr.microsoft.com/dotnet/sdk:8.0',
};

export function QAReadinessPage() {
  const { id } = useParams<{ id: string }>();
  const project = getProjectById(id!);
  const [running, setRunning] = useState(false);
  if (!project) return null;

  const baseImage = IMAGE_BY_STACK[project.stack.language] ?? `node:20-bullseye`;
  const passed = project.testExecutions.filter(t => t.status === 'passed').length;
  const failed = project.testExecutions.filter(t => t.status === 'failed').length;
  const total = project.testExecutions.length;
  const avgCoverage = total > 0 ? Math.round(project.testExecutions.filter(t => t.coverage && t.coverage > 0).reduce((acc, t) => acc + (t.coverage ?? 0), 0) / project.testExecutions.filter(t => t.coverage && t.coverage > 0).length) : 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">M9 — QA Readiness</h2>
          <p className="text-slate-500 text-sm mt-0.5">Planejamento e execução de testes em containers isolados por projeto</p>
        </div>
        <button
          onClick={() => setRunning(true)}
          disabled={running}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 text-sm hover:bg-emerald-600/30 transition-colors disabled:opacity-50"
        >
          {running ? <span className="w-4 h-4 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" /> : <Play className="w-4 h-4" />}
          {running ? 'Executando...' : 'Executar Plano'}
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <p className="text-2xl font-semibold text-slate-100">{total}</p>
          <p className="text-slate-500 text-xs mt-1">Total de testes</p>
        </div>
        <div className="bg-emerald-950/20 border border-emerald-800/30 rounded-xl p-4">
          <p className="text-2xl font-semibold text-emerald-400">{passed}</p>
          <p className="text-slate-500 text-xs mt-1">Passaram</p>
        </div>
        <div className="bg-red-950/20 border border-red-800/30 rounded-xl p-4">
          <p className="text-2xl font-semibold text-red-400">{failed}</p>
          <p className="text-slate-500 text-xs mt-1">Falharam</p>
        </div>
        <div className="bg-blue-950/20 border border-blue-800/30 rounded-xl p-4">
          <p className="text-2xl font-semibold text-blue-400">{avgCoverage}%</p>
          <p className="text-slate-500 text-xs mt-1">Cobertura média</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Executor Config */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Box className="w-4 h-4 text-blue-400" />
            <h3 className="text-slate-200 text-sm font-semibold">Executor Isolado</h3>
          </div>
          <div className="space-y-3">
            <div>
              <p className="text-slate-500 text-xs mb-1">Imagem base (stack: {project.stack.language})</p>
              <code className="text-blue-300 text-xs bg-slate-800 px-2 py-1 rounded block font-mono">{baseImage}</code>
            </div>
            <div>
              <p className="text-slate-500 text-xs mb-1">Estratégia</p>
              <p className="text-slate-300 text-sm">Container efêmero por execução</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs mb-1">Política de rede</p>
              <p className="text-slate-300 text-sm">Isolada · Sem estado compartilhado</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs mb-1">Evidências</p>
              <p className="text-slate-300 text-sm">Storage isolado por projeto</p>
            </div>
          </div>
          {project.repository && (
            <div className="mt-4 p-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
              <p className="text-slate-400 text-xs">Repositório clonado com credenciais do projeto</p>
              <code className="text-indigo-400 text-xs font-mono break-all block mt-1">{project.repository.url.split('/').slice(-1)[0]}</code>
            </div>
          )}
        </div>

        {/* Test Executions */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
            <h3 className="text-slate-200 text-sm font-semibold">Execuções de Testes</h3>
            {total > 0 && (
              <div className="flex items-center gap-2">
                <div className="w-32 bg-slate-700 rounded-full h-2">
                  <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${(passed / total) * 100}%` }} />
                </div>
                <span className="text-slate-400 text-xs">{passed}/{total}</span>
              </div>
            )}
          </div>
          {project.testExecutions.length === 0 ? (
            <div className="flex items-center justify-center h-40">
              <div className="text-center">
                <TestTube2 className="w-8 h-8 text-slate-700 mx-auto mb-2" />
                <p className="text-slate-500 text-sm">Nenhuma execução registrada</p>
                <p className="text-slate-600 text-xs mt-1">Execute o plano de testes para iniciar</p>
              </div>
            </div>
          ) : (
            <div className="divide-y divide-slate-800">
              {project.testExecutions.map(exec => (
                <div key={exec.id} className="flex items-center gap-4 px-5 py-4 hover:bg-slate-800/30 transition-colors">
                  <div className="flex-shrink-0">{statusIcon(exec.status)}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-200 text-sm font-medium">{exec.name}</p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="text-xs text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">{exec.type}</span>
                      {exec.duration && <span className="text-slate-500 text-xs">{exec.duration}</span>}
                      {exec.coverage && exec.coverage > 0 && <span className="text-slate-500 text-xs">Cobertura: {exec.coverage}%</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {exec.evidence && (
                      <button className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
                        <Download className="w-3.5 h-3.5" /> Evidência
                      </button>
                    )}
                    <StatusBadge status={exec.status} size="sm" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Test Types Coverage */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-4">Cobertura por Tipo de Teste</h3>
        <div className="grid grid-cols-3 md:grid-cols-7 gap-3">
          {TEST_TYPES.map(type => {
            const execsOfType = project.testExecutions.filter(t => t.type === type);
            const hasPassed = execsOfType.some(t => t.status === 'passed');
            const hasFailed = execsOfType.some(t => t.status === 'failed');
            return (
              <div key={type} className={`p-3 rounded-xl border text-center ${execsOfType.length === 0 ? 'border-slate-800 opacity-40' : hasFailed ? 'border-red-800/30 bg-red-950/10' : hasPassed ? 'border-emerald-800/30 bg-emerald-950/10' : 'border-slate-800'}`}>
                <div className="mb-1 flex justify-center">
                  {execsOfType.length === 0 ? <Clock className="w-4 h-4 text-slate-600" /> : hasFailed ? <XCircle className="w-4 h-4 text-red-400" /> : <CheckCircle className="w-4 h-4 text-emerald-400" />}
                </div>
                <p className="text-xs text-slate-400">{type}</p>
                <p className="text-xs text-slate-600 mt-0.5">{execsOfType.length} exec.</p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}