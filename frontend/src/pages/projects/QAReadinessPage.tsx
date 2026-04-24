import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { TestTube2, Play, Clock, CheckCircle, XCircle, AlertTriangle, Download, Box, Loader2, ExternalLink } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { HelpTooltip } from '@/components/ui/HelpTooltip';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { OperationBar, PageTransition, SkeletonPulse } from '@/components/ui/PipelineProgress';
import { useProjectPermissions } from '@/hooks/useProjectPermissions';
import { TestSpecsSection } from '@/components/qa/TestSpecsSection';

interface CoverageCategory {
  type: string;
  total: number;
  passed: number;
  failed: number;
  coverage: number;
}

interface QACoverageData {
  total_tests: number;
  passed: number;
  failed: number;
  avg_coverage: number;
  categories: CoverageCategory[];
}

interface TestExecution {
  id: string;
  name: string;
  type: string;
  status: string;
  duration?: string;
  coverage?: number;
  evidence?: string;
  executed_at?: string;
}

const statusIcon = (status: string) => {
  if (status === 'passed') return <CheckCircle className="w-4 h-4 text-emerald-400" />;
  if (status === 'failed') return <XCircle className="w-4 h-4 text-red-400" />;
  if (status === 'queued') return <Clock className="w-4 h-4 text-slate-400" />;
  if (status === 'running') return <span className="w-4 h-4 border-2 border-violet-400 border-t-transparent rounded-full animate-spin inline-block" />;
  if (status === 'blocked') return <AlertTriangle className="w-4 h-4 text-amber-400" />;
  return <Clock className="w-4 h-4 text-slate-400" />;
};

export function QAReadinessPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { can } = useProjectPermissions();
  // DT-053: GP não tem `pipeline:execute` (só Dev/Tester per contrato §4.1).
  // Sem o hook, frontend mostrava botão verde ativo e o backend retornava
  // 403 — UX confusa. Agora ocultamos quem não pode executar.
  const canExecutePlan = can('pipeline:execute');
  const [coverage, setCoverage] = useState<QACoverageData | null>(null);
  const [results, setResults] = useState<TestExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [ocgTesting, setOcgTesting] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [covRes, resRes, ocgRes] = await Promise.all([
          apiClient.get(`/projects/${id}/qa/coverage`),
          apiClient.get(`/projects/${id}/qa/results`),
          apiClient.get(`/projects/${id}/ocg`).catch(() => ({ data: {} })),
        ]);
        setCoverage(covRes.data);
        setResults(resRes.data);

        const ocg = ocgRes.data?.ocg;
        if (ocg?.ocg_data) {
          const data = typeof ocg.ocg_data === 'string' ? JSON.parse(ocg.ocg_data) : ocg.ocg_data;
          setOcgTesting(data.TESTING_REQUIREMENTS || null);
        }
      } catch {
        setCoverage(null);
        setResults([]);
      } finally {
        setLoading(false);
      }
    };
    if (id) load();
  }, [id]);

  const handleExecute = async () => {
    setRunning(true);
    try {
      await apiClient.post(`/projects/${id}/qa/execute`, { test_types: null });
      // Recarregar dados após execucao
      const [covRes, resRes] = await Promise.all([
        apiClient.get(`/projects/${id}/qa/coverage`),
        apiClient.get(`/projects/${id}/qa/results`),
      ]);
      setCoverage(covRes.data);
      setResults(resRes.data);
    } catch {
      // erro silencioso, dados permanecem como estavam
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <SkeletonPulse className="h-8 w-48" />
        <div className="grid grid-cols-4 gap-4">
          <SkeletonPulse className="h-24 rounded-xl" />
          <SkeletonPulse className="h-24 rounded-xl" />
          <SkeletonPulse className="h-24 rounded-xl" />
          <SkeletonPulse className="h-24 rounded-xl" />
        </div>
        <SkeletonPulse className="h-48 rounded-xl" />
      </div>
    );
  }

  const total = coverage?.total_tests ?? 0;
  const passed = coverage?.passed ?? 0;
  const failed = coverage?.failed ?? 0;
  const avgCoverage = coverage?.avg_coverage ?? 0;
  const categories = coverage?.categories ?? [];

  return (
    <PageTransition>
    <div className="p-6 space-y-6">
      {running && (
        <OperationBar
          message="Executando testes"
          detail="Rodando suíte completa em containers isolados"
          status="running"
        />
      )}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            QA Readiness
            <HelpTooltip
              text="O QA Readiness consolida os resultados de todos os testes do projeto, organizados por categoria (unitário, integração, E2E, regressão, carga, segurança). Os testes são gerados automaticamente pelo CodeGen e revisados no Tester Review antes da execução. Os resultados alimentam o pilar P5 (Testabilidade) do Gatekeeper."
              maxWidth="max-w-sm"
            />
          </h2>
          <p className="text-slate-500 text-sm mt-0.5">Planejamento e execução de testes em containers isolados por projeto</p>
        </div>
      </div>

      {/* MVP 10 Fase 10.5 — Plano de Testes derivado de OCG/Roadmap */}
      {id && <TestSpecsSection projectId={id} />}

      {/* Requisitos de testes do OCG (DT-052) */}
      {ocgTesting && Object.keys(ocgTesting).length > 0 && (
        <div className="bg-slate-900/50 border border-slate-800/50 rounded-xl p-4">
          <p className="text-slate-400 text-xs font-semibold mb-2">Requisitos de Testes (OCG)</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(ocgTesting)
              .filter(([key]) => key !== 'source') // metadado interno do fallback determinístico
              .map(([key, val]) => {
                const label = key.replace(/_/g, ' ')
                let display: string | null = null
                if (typeof val === 'boolean') {
                  display = val ? 'sim' : 'não'
                } else if (Array.isArray(val)) {
                  display = val.length > 0 ? val.join(', ') : '—'
                } else if (val !== null && val !== undefined && val !== '') {
                  display = String(val)
                }
                if (display === null) return null
                return (
                  <div
                    key={key}
                    className={`px-2.5 py-1.5 rounded-lg border ${
                      typeof val === 'boolean' && !val
                        ? 'bg-slate-800/30 border-slate-700/30 opacity-60'
                        : 'bg-slate-800/60 border-slate-700/40'
                    }`}
                  >
                    <span className="text-violet-400 text-xs font-medium">{label}:</span>
                    <span className="text-slate-300 text-xs ml-1.5">{display}</span>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      <div className="flex items-start justify-between">
        <div></div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(`/projects/${id}/tester-review`)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600/20 border border-violet-600/30 text-violet-400 text-sm hover:bg-violet-600/30 transition-colors"
          >
            <ExternalLink className="w-4 h-4" />
            Ver Tester Review
          </button>
          {/* DT-053: oculta botão para quem não tem pipeline:execute (GP, QA, Admin sem membership) */}
          {canExecutePlan && (
          <span className="relative inline-flex items-center">
            <button
              onClick={handleExecute}
              disabled={running}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 text-sm hover:bg-emerald-600/30 transition-colors disabled:opacity-50"
            >
              {running ? <span className="w-4 h-4 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" /> : <Play className="w-4 h-4" />}
              {running ? 'Executando...' : 'Executar Plano'}
            </button>
            <HelpTooltip
              text="Dispara a execução de todos os testes aprovados ou editados do projeto, agrupados por categoria. Cada teste é executado em subprocess isolado. O tempo de execução varia de segundos (unitários) a minutos (E2E/carga). Os resultados são gravados no banco e em arquivo JSONL para auditoria."
              maxWidth="max-w-sm"
              position="left"
            />
          </span>
          )}
        </div>
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
        <div className="bg-violet-950/20 border border-violet-800/30 rounded-xl p-4">
          <p className="text-2xl font-semibold text-violet-400">{avgCoverage}%</p>
          <p className="text-slate-500 text-xs mt-1">Cobertura média</p>
        </div>
      </div>

      {/* Test Executions */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="text-slate-200 text-sm font-semibold">Execuções de Testes</h3>
          {total > 0 && (
            <div className="flex items-center gap-2">
              <div className="w-32 bg-slate-700 rounded-full h-2">
                <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${total > 0 ? (passed / total) * 100 : 0}%` }} />
              </div>
              <span className="text-slate-400 text-xs">{passed}/{total}</span>
            </div>
          )}
        </div>
        {results.length === 0 ? (
          <div className="flex items-center justify-center h-40">
            <div className="text-center">
              <TestTube2 className="w-8 h-8 text-slate-700 mx-auto mb-2" />
              <p className="text-slate-500 text-sm">Nenhuma execução registrada</p>
              <p className="text-slate-600 text-xs mt-1">Execute o plano de testes para iniciar</p>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {results.map(exec => (
              <div key={exec.id} className="flex items-center gap-4 px-5 py-4 hover:bg-slate-800/30 transition-colors">
                <div className="flex-shrink-0">{statusIcon(exec.status)}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-slate-200 text-sm font-medium">{exec.name}</p>
                  <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                    <span className="text-xs text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">{exec.type}</span>
                    {exec.duration && <span className="text-slate-500 text-xs">{exec.duration}</span>}
                    {exec.coverage != null && exec.coverage > 0 && <span className="text-slate-500 text-xs">Cobertura: {exec.coverage}%</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {exec.evidence && (
                    <button
                      type="button"
                      onClick={() => {
                        const ev = exec.evidence || ''
                        if (/^https?:\/\//i.test(ev)) {
                          window.open(ev, '_blank', 'noopener,noreferrer')
                        } else {
                          // Não é URL — mostra o conteúdo numa nova janela pra o GP copiar/ler
                          const w = window.open('', '_blank', 'width=700,height=500')
                          if (w) {
                            w.document.title = `Evidência — ${exec.name}`
                            w.document.body.innerText = ev
                          }
                        }
                      }}
                      title="Abrir evidência da execução"
                      className="flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 transition-colors"
                    >
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

      {/* Coverage by Category */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-slate-200 text-sm font-semibold mb-4">Cobertura por Categoria</h3>
        <div className="grid grid-cols-3 md:grid-cols-7 gap-3">
          {categories.length > 0 ? categories.map(cat => {
            const hasFailed = cat.failed > 0;
            const hasPassed = cat.passed > 0;
            return (
              <div key={cat.type} className={`p-3 rounded-xl border text-center ${cat.total === 0 ? 'border-slate-800 opacity-40' : hasFailed ? 'border-red-800/30 bg-red-950/10' : hasPassed ? 'border-emerald-800/30 bg-emerald-950/10' : 'border-slate-800'}`}>
                <div className="mb-1 flex justify-center">
                  {cat.total === 0 ? <Clock className="w-4 h-4 text-slate-600" /> : hasFailed ? <XCircle className="w-4 h-4 text-red-400" /> : <CheckCircle className="w-4 h-4 text-emerald-400" />}
                </div>
                <p className="text-xs text-slate-400">{cat.type}</p>
                <p className="text-xs text-slate-600 mt-0.5">{cat.total} exec.</p>
              </div>
            );
          }) : (
            <p className="text-slate-500 text-sm col-span-full text-center py-4">Nenhuma categoria disponível</p>
          )}
        </div>
      </div>
    </div>
    </PageTransition>
  );
}
