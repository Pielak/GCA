import React, { useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Archive,
  GitBranch,
  Upload,
  Link2,
  AlertTriangle,
  CheckCircle,
  Loader2,
  FolderCode,
  ShieldAlert,
  Merge,
  FileWarning,
  ChevronDown,
} from 'lucide-react';
import { HelpTooltip } from '@/components/ui/HelpTooltip';

/* ── Tipos ───────────────────────────────────────────────────────── */

type SourceMode = 'url' | 'zip';

interface DebitoTecnico {
  id: string;
  severity: 'critico' | 'medio' | 'baixo';
  file: string;
  line: number;
  description: string;
}

interface ConflitoStack {
  id: string;
  tecnologiaAtual: string;
  tecnologiaEsperada: string;
  impacto: string;
}

interface ModuloImplementado {
  id: string;
  nome: string;
  cobertura: number; // 0–100
  recomendacao: 'merge' | 'reescrever' | 'descartar';
}

/* ── Mock data ───────────────────────────────────────────────────── */

const MOCK_DEBITOS: DebitoTecnico[] = [
  { id: 'd1', severity: 'critico', file: 'auth/views.py', line: 142, description: 'SQL query construída via concatenação — risco de SQLi' },
  { id: 'd2', severity: 'critico', file: 'payments/processor.py', line: 201, description: 'Sem tratamento de race condition em transações concorrentes' },
  { id: 'd3', severity: 'critico', file: 'models/user.py', line: 15, description: 'Uso de MD5 para hash de senha — migrar para bcrypt/argon2' },
  { id: 'd4', severity: 'medio', file: 'utils/pdf_parser.py', line: 88, description: 'Biblioteca PDFMiner v1.2 com CVE-2023-4512 reportado' },
  { id: 'd5', severity: 'medio', file: 'requirements.txt', line: 23, description: 'Django 3.2 — sem suporte desde abril 2024' },
  { id: 'd6', severity: 'medio', file: 'api/serializers.py', line: 34, description: 'Serialização manual sem validação de tipos' },
  { id: 'd7', severity: 'medio', file: 'core/middleware.py', line: 12, description: 'Middleware de CORS configurado com allow_all=True' },
  { id: 'd8', severity: 'medio', file: 'config/settings.py', line: 5, description: 'DEBUG=True hardcoded — nunca desabilitado em produção' },
  { id: 'd9', severity: 'medio', file: 'tasks/celery_worker.py', line: 67, description: 'Tasks sem retry com backoff — falhas silenciosas' },
  { id: 'd10', severity: 'medio', file: 'db/migrations/0042.py', line: 3, description: 'Migração com RunSQL sem reverse — rollback impossível' },
  { id: 'd11', severity: 'baixo', file: 'templates/base.html', line: 1, description: 'HTML sem atributo lang — acessibilidade' },
  { id: 'd12', severity: 'baixo', file: 'static/js/app.js', line: 500, description: 'jQuery 2.x — considerar remoção' },
  { id: 'd13', severity: 'baixo', file: 'utils/helpers.py', line: 22, description: 'Função utilitária com 340 linhas — extrair classes' },
  { id: 'd14', severity: 'baixo', file: 'tests/__init__.py', line: 1, description: 'Cobertura de testes < 15% — sem testes de integração' },
  { id: 'd15', severity: 'baixo', file: 'docs/README.md', line: 1, description: 'Documentação desatualizada — última edição há 18 meses' },
  { id: 'd16', severity: 'baixo', file: 'manage.py', line: 8, description: 'Python 2 shebang ainda presente' },
  { id: 'd17', severity: 'baixo', file: 'scripts/deploy.sh', line: 14, description: 'Deploy script sem verificação de health check' },
  { id: 'd18', severity: 'baixo', file: 'locale/pt_BR/LC_MESSAGES/django.po', line: 200, description: 'Traduções incompletas — 43% das strings sem tradução' },
  { id: 'd19', severity: 'baixo', file: 'api/urls.py', line: 45, description: 'Rotas sem versionamento — /api/ em vez de /api/v1/' },
  { id: 'd20', severity: 'baixo', file: 'core/cache.py', line: 10, description: 'Cache com TTL fixo de 60s — sem estratégia de invalidação' },
  { id: 'd21', severity: 'baixo', file: 'logging.conf', line: 1, description: 'Logs sem structured logging — difícil parsear em produção' },
  { id: 'd22', severity: 'baixo', file: 'Dockerfile', line: 3, description: 'Imagem base python:3.8 — versão em EOL' },
];

const MOCK_CONFLITOS: ConflitoStack[] = [
  { id: 'c1', tecnologiaAtual: 'Python 2.7', tecnologiaEsperada: 'Python 3.11', impacto: 'Incompatibilidade de sintaxe (print, unicode, division)' },
  { id: 'c2', tecnologiaAtual: 'Django 3.2', tecnologiaEsperada: 'FastAPI 0.110', impacto: 'Framework completamente diferente — requer reescrita de rotas e middlewares' },
  { id: 'c3', tecnologiaAtual: 'jQuery 2.x', tecnologiaEsperada: 'React 18', impacto: 'Paradigma imperativo vs declarativo — reescrita completa do frontend' },
  { id: 'c4', tecnologiaAtual: 'PostgreSQL 12', tecnologiaEsperada: 'PostgreSQL 16', impacto: 'Migração de schema necessária — verificar extensões deprecated' },
  { id: 'c5', tecnologiaAtual: 'Celery 4.x', tecnologiaEsperada: 'Celery 5.3', impacto: 'Mudanças na API de configuração e serialização' },
];

const MOCK_MODULOS: ModuloImplementado[] = [
  { id: 'm1', nome: 'AuthModule', cobertura: 85, recomendacao: 'merge' },
  { id: 'm2', nome: 'PaymentsModule', cobertura: 60, recomendacao: 'reescrever' },
  { id: 'm3', nome: 'UserManagement', cobertura: 92, recomendacao: 'merge' },
  { id: 'm4', nome: 'NotificationService', cobertura: 40, recomendacao: 'reescrever' },
  { id: 'm5', nome: 'ReportGenerator', cobertura: 15, recomendacao: 'descartar' },
  { id: 'm6', nome: 'FileUploader', cobertura: 78, recomendacao: 'merge' },
];

/* ── Helpers ──────────────────────────────────────────────────────── */

const severityConfig = {
  critico: { label: 'Crítico', dot: 'bg-red-500', text: 'text-red-400', border: 'border-red-800/40', bg: 'bg-red-950/20' },
  medio:   { label: 'Médio',   dot: 'bg-amber-500', text: 'text-amber-400', border: 'border-amber-800/40', bg: 'bg-amber-950/20' },
  baixo:   { label: 'Baixo',   dot: 'bg-emerald-500', text: 'text-emerald-400', border: 'border-emerald-800/40', bg: 'bg-emerald-950/20' },
} as const;

const recomendacaoConfig = {
  merge:      { label: 'Recomendar merge', color: 'text-emerald-400 bg-emerald-900/20 border-emerald-800/30' },
  reescrever: { label: 'Reescrever',       color: 'text-amber-400 bg-amber-900/20 border-amber-800/30' },
  descartar:  { label: 'Descartar',        color: 'text-red-400 bg-red-900/20 border-red-800/30' },
} as const;

/* ── Componente ──────────────────────────────────────────────────── */

export function LegacyPage() {
  const { id } = useParams<{ id: string }>();

  // Fonte do codebase
  const [sourceMode, setSourceMode] = useState<SourceMode>('zip');
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('main');
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Análise
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);
  const [progress, setProgress] = useState(0);

  const countBySeverity = (sev: DebitoTecnico['severity']) =>
    MOCK_DEBITOS.filter(d => d.severity === sev).length;

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.zip') || file.type === 'application/zip')) {
      setZipFile(file);
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setZipFile(file);
  }, []);

  const canAnalyze =
    (sourceMode === 'url' && repoUrl.trim().length > 0) ||
    (sourceMode === 'zip' && zipFile !== null);

  const startAnalysis = () => {
    if (!canAnalyze) return;
    setAnalyzing(true);
    setProgress(0);
    const interval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          setAnalyzing(false);
          setAnalyzed(true);
          return 100;
        }
        return prev + Math.random() * 15 + 5;
      });
    }, 300);
  };

  return (
    <div className="min-h-screen bg-[#0D0D18] p-6 space-y-6">
      {/* ── Toolbar ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <Archive className="w-5 h-5 text-violet-400" />
        <h2 className="text-lg font-semibold text-slate-100">
          Analise de Codigo Legado
        </h2>
        <HelpTooltip
          text="A LegacyPage permite ingerir um codebase existente para análise pelo Arguidor com foco em legado. O objetivo é entender o que já existe antes de gerar código novo, evitando duplicação ou conflitos. O resultado é um relatório de débito técnico, conflitos de stack e módulos já implementados que podem ser aproveitados via MergeEngine."
        />
        {analyzed && (
          <span className="ml-auto px-2.5 py-1 rounded text-xs font-medium bg-emerald-900/30 text-emerald-400 border border-emerald-800/30">
            Analise concluida
          </span>
        )}
      </div>

      {/* ── Fonte do Codebase ────────────────────────────────────── */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-5">
        <h3 className="text-sm font-semibold text-slate-200">Fonte do Codebase</h3>

        {/* Radio buttons */}
        <div className="flex items-center gap-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="source"
              checked={sourceMode === 'url'}
              onChange={() => setSourceMode('url')}
              className="accent-violet-600"
            />
            <span className="text-sm text-slate-300">URL de Repositorio Git</span>
            <HelpTooltip
              text="Cole a URL completa do repositório legado (ex: https://github.com/empresa/sistema-antigo). O GCA irá clonar o repositório usando o PAT configurado no projeto e analisar o código-fonte. Certifique-se de que o PAT tem permissão de leitura neste repositório."
            />
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="source"
              checked={sourceMode === 'zip'}
              onChange={() => setSourceMode('zip')}
              className="accent-violet-600"
            />
            <span className="text-sm text-slate-300">Upload de ZIP</span>
            <HelpTooltip
              text="Faça upload de um arquivo ZIP contendo o código-fonte legado. Útil quando o código não está em um repositório Git acessível. O ZIP deve conter a estrutura de diretórios do projeto. Tamanho máximo: 200MB. Arquivos de dependências (node_modules, venv, .git) serão ignorados automaticamente."
            />
          </label>
        </div>

        {/* URL mode */}
        {sourceMode === 'url' && (
          <div className="space-y-4">
            <div>
              <label className="text-xs text-slate-500 block mb-1.5">URL do repositorio</label>
              <div className="flex items-center gap-2">
                <Link2 className="w-4 h-4 text-slate-500 flex-shrink-0" />
                <input
                  value={repoUrl}
                  onChange={e => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/empresa/sistema-antigo"
                  className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono placeholder-slate-600 focus:outline-none focus:border-violet-500 transition-colors"
                />
              </div>
            </div>
            <div className="max-w-xs">
              <label className="text-xs text-slate-500 block mb-1.5">Branch</label>
              <div className="relative">
                <select
                  value={branch}
                  onChange={e => setBranch(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 appearance-none focus:outline-none focus:border-violet-500 transition-colors"
                >
                  <option value="main">main</option>
                  <option value="master">master</option>
                  <option value="develop">develop</option>
                  <option value="staging">staging</option>
                </select>
                <ChevronDown className="w-4 h-4 text-slate-500 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>
          </div>
        )}

        {/* ZIP mode */}
        {sourceMode === 'zip' && (
          <div
            onDrop={handleDrop}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            className={`
              border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer
              ${dragOver
                ? 'border-violet-500 bg-violet-950/20'
                : zipFile
                  ? 'border-emerald-700/50 bg-emerald-950/10'
                  : 'border-slate-700 bg-slate-800/30 hover:border-slate-600'
              }
            `}
            onClick={() => document.getElementById('zip-input')?.click()}
          >
            <input
              id="zip-input"
              type="file"
              accept=".zip"
              onChange={handleFileSelect}
              className="hidden"
            />
            {zipFile ? (
              <div className="space-y-2">
                <CheckCircle className="w-8 h-8 text-emerald-400 mx-auto" />
                <p className="text-sm text-emerald-300 font-medium">{zipFile.name}</p>
                <p className="text-xs text-slate-500">
                  {(zipFile.size / (1024 * 1024)).toFixed(1)} MB
                </p>
                <button
                  onClick={(e) => { e.stopPropagation(); setZipFile(null); }}
                  className="text-xs text-red-400 hover:text-red-300 mt-1"
                >
                  Remover arquivo
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <Upload className="w-8 h-8 text-slate-600 mx-auto" />
                <p className="text-sm text-slate-400">
                  Arraste um arquivo ZIP aqui ou clique para selecionar
                </p>
                <p className="text-xs text-slate-600">Maximo: 200MB. node_modules, venv e .git serao ignorados.</p>
              </div>
            )}
          </div>
        )}

        {/* Analyze button + progress */}
        <div className="flex items-center gap-4">
          <button
            onClick={startAnalysis}
            disabled={!canAnalyze || analyzing || analyzed}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {analyzing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Analisando...
              </>
            ) : (
              <>
                <FolderCode className="w-4 h-4" />
                Analisar Codebase
              </>
            )}
          </button>

          {analyzing && (
            <div className="flex-1 max-w-md">
              <div className="flex justify-between text-xs text-slate-500 mb-1">
                <span>Progresso</span>
                <span>{Math.min(Math.round(progress), 100)}%</span>
              </div>
              <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-violet-600 rounded-full transition-all duration-300"
                  style={{ width: `${Math.min(progress, 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Resultados (aparecem apos analise concluida) ──────── */}
      {analyzed && (
        <>
          {/* ── Debito Tecnico + Conflitos de Stack (side by side) ── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Debito Tecnico */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-red-400" />
                <h3 className="text-sm font-semibold text-slate-200">Debito Tecnico</h3>
              </div>

              {/* Summary badges */}
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-red-950/30 text-red-400 border border-red-800/30">
                  <span className="w-2 h-2 rounded-full bg-red-500" />
                  {countBySeverity('critico')} criticos
                </span>
                <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-amber-950/30 text-amber-400 border border-amber-800/30">
                  <span className="w-2 h-2 rounded-full bg-amber-500" />
                  {countBySeverity('medio')} medios
                </span>
                <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-emerald-950/30 text-emerald-400 border border-emerald-800/30">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  {countBySeverity('baixo')} baixos
                </span>
              </div>

              {/* List */}
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {MOCK_DEBITOS.map(d => {
                  const cfg = severityConfig[d.severity];
                  return (
                    <div
                      key={d.id}
                      className={`flex items-start gap-3 p-3 rounded-lg border ${cfg.border} ${cfg.bg}`}
                    >
                      <span className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${cfg.dot}`} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className={`text-xs font-medium ${cfg.text}`}>{cfg.label}</span>
                          <code className="text-xs text-slate-500 font-mono truncate">
                            {d.file}:{d.line}
                          </code>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed">{d.description}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Conflitos de Stack */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-semibold text-slate-200">Conflitos de Stack</h3>
              </div>

              <div className="space-y-3">
                {MOCK_CONFLITOS.map(c => (
                  <div
                    key={c.id}
                    className="p-3 rounded-lg border border-amber-800/30 bg-amber-950/10 space-y-2"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono px-2 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-800/30">
                        {c.tecnologiaAtual}
                      </span>
                      <span className="text-xs text-slate-500">→</span>
                      <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-800/30">
                        esperado {c.tecnologiaEsperada}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed">{c.impacto}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── Modulos Ja Implementados ──────────────────────────── */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Merge className="w-4 h-4 text-violet-400" />
              <h3 className="text-sm font-semibold text-slate-200">Modulos Ja Implementados</h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {MOCK_MODULOS.map(m => {
                const rec = recomendacaoConfig[m.recomendacao];
                return (
                  <div
                    key={m.id}
                    className="p-4 rounded-lg border border-slate-800 bg-slate-800/30 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-200">{m.nome}</span>
                      <span className={`text-xs px-2 py-0.5 rounded border ${rec.color}`}>
                        {rec.label}
                      </span>
                    </div>

                    {/* Progress bar */}
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-500">Cobertura</span>
                        <span className={
                          m.cobertura >= 80 ? 'text-emerald-400' :
                          m.cobertura >= 50 ? 'text-amber-400' :
                          'text-red-400'
                        }>
                          {m.cobertura}%
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            m.cobertura >= 80 ? 'bg-emerald-500' :
                            m.cobertura >= 50 ? 'bg-amber-500' :
                            'bg-red-500'
                          }`}
                          style={{ width: `${m.cobertura}%` }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* ── Estado vazio ─────────────────────────────────────────── */}
      {!analyzed && !analyzing && (
        <div className="flex items-center justify-center h-40 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-center">
            <FileWarning className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-slate-500 text-sm">Selecione a fonte do codebase legado e clique em Analisar</p>
            <p className="text-slate-600 text-xs mt-1">
              Obrigatorio para projetos de melhoria ou nova funcionalidade em sistema existente
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
