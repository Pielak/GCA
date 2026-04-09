import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Shield, AlertTriangle, XCircle, Zap, Lock, Info, Loader2 } from 'lucide-react'
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts'
import { HelpTooltip } from '@/components/ui/HelpTooltip'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

interface PillarResult {
  pillar: string
  score: number
  status: string
  notes?: string
}

interface GatekeeperData {
  score: number
  status: string
  pillars: PillarResult[]
  stackRecommendation?: { backend: string; frontend: string; database: string; cache: string; infra: string }
  criticalFindings?: { pillar: string; severity: string; finding: string; action: string }[]
  complianceChecklist?: { requirement: string; status: string; implementation: string }[]
}

const pillarStatusColor = (status: string) => {
  if (status === 'ok') return 'text-emerald-400'
  if (status === 'warning') return 'text-amber-400'
  return 'text-red-400'
}

const pillarStatusBg = (status: string) => {
  if (status === 'ok') return 'border-emerald-800/30 bg-emerald-950/10'
  if (status === 'warning') return 'border-amber-800/30 bg-amber-950/10'
  return 'border-red-800/30 bg-red-950/10'
}

export function GatekeeperPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const [data, setData] = useState<GatekeeperData | null>(null)
  const [loading, setLoading] = useState(true)
  const [showOverride, setShowOverride] = useState(false)
  const [overrideReason, setOverrideReason] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get(`/projects/${id}/gatekeeper`)
        setData(res.data)
      } catch {
        setData(null)
      } finally {
        setLoading(false)
      }
    }
    if (id) load()
  }, [id])

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 text-violet-400 animate-spin" /></div>

  if (!data || !data.pillars || data.pillars.length === 0) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center h-32 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-center">
            <Shield className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-slate-500 text-sm">Gatekeeper não iniciado</p>
            <p className="text-slate-600 text-xs mt-1">Inicie após a consolidação dos artefatos</p>
          </div>
        </div>
      </div>
    )
  }

  const pillarTooltips = [
    'Verifica se o código segue exatamente os padrões definidos no OCG: linguagem correta, arquitetura escolhida (Clean Architecture, Microsserviços, etc.), nomenclatura de variáveis e funções, estrutura de pastas, imports e formatação. É o ÚNICO pilar bloqueante: score < 60 impede aprovação. Exemplos de falha: código Python quando o projeto exige TypeScript; nomes em inglês quando o padrão é português; violação da separação de camadas da Clean Architecture.',
    'Avalia aderência à arquitetura definida no projeto: separação de camadas (Controller, Service, Repository), injeção de dependências, ausência de acoplamento desnecessário, respeito ao DDD se aplicável. Score baixo indica que o módulo está \'vazando\' responsabilidades entre camadas ou criando dependências circulares.',
    'Detecta vulnerabilidades comuns: SQL Injection, XSS, exposição de segredos no código-fonte, endpoints sem autenticação, senhas hardcoded, algoritmos de hash fracos (MD5, SHA1), ausência de validação de entrada. Score < 70 gera alerta obrigatório mesmo que o módulo seja aprovado.',
    'Analisa gargalos potenciais: queries N+1, loops desnecessários em operações de banco, ausência de índices em campos de busca frequente, chamadas síncronas em contexto assíncrono, ausência de cache onde necessário, payloads excessivamente grandes. Score < 70 gera recomendações de otimização no relatório.',
    'Verifica se o código pode ser testado de forma isolada: injeção de dependências (sem singletons globais intestáveis), funções puras onde possível, interfaces bem definidas, ausência de efeitos colaterais ocultos. Também verifica se os testes unitários foram gerados para o módulo e se estão estruturados corretamente.',
    'Avalia legibilidade e sustentabilidade do código: complexidade ciclomática (funções com mais de 10 caminhos são penalizadas), tamanho de funções (mais de 50 linhas é penalizado), duplicação de código, uso de magic numbers sem constantes nomeadas, ausência de comentários em trechos complexos.',
    'Verifica presença de docstrings/JSDoc em todas as funções e classes públicas, README do módulo, cobertura na LiveDocs e changelog de alterações. Score baixo não bloqueia aprovação mas gera automaticamente uma tarefa de documentação pendente no roadmap.',
  ]

  const canOverride = user?.is_admin
  const blockers = data.pillars.filter(p => p.status === 'blocker')
  const warnings = data.pillars.filter(p => p.status === 'warning')
  const isBlocked = data.status === 'blocked'

  const radarData = data.pillars.map(p => ({
    subject: p.pillar.split(' ').pop() || p.pillar,
    score: p.score,
  }))

  const scoreColor = data.score >= 90 ? '#34d399' : data.score >= 70 ? '#fbbf24' : '#f87171'

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-1.5">
            <h2 className="text-lg font-semibold text-slate-100">Gatekeeper</h2>
            <HelpTooltip text="O Gatekeeper é o controle de qualidade automático do GCA. Antes de qualquer módulo ser commitado no repositório do projeto, o código gerado passa por avaliação simultânea nos 7 Pilares de qualidade. Cada pilar recebe um score de 0 a 100. O pilar P1 (Conformidade) é bloqueante: score < 60 impede aprovação automática e manual. Os demais pilares apenas geram avisos e recomendações." />
          </div>
          <p className="text-slate-500 text-sm mt-0.5">Avaliação dos 7 pilares com scoring formal</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs px-3 py-1 rounded-full font-medium ${
            data.status === 'approved' ? 'bg-emerald-500/20 text-emerald-300' :
            data.status === 'blocked' ? 'bg-red-500/20 text-red-300' :
            data.status === 'needs_review' ? 'bg-amber-500/20 text-amber-300' :
            'bg-slate-700 text-slate-400'
          }`}>{data.status?.toUpperCase()}</span>
          {canOverride && isBlocked && (
            <button onClick={() => setShowOverride(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-900/20 border border-amber-700/30 text-amber-400 text-sm hover:bg-amber-900/30 transition-colors">
              <Lock className="w-3.5 h-3.5" /> Override
            </button>
          )}
        </div>
      </div>

      {/* Score + Radar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col items-center justify-center">
          <div className="relative w-36 h-36">
            <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
              <circle cx="50" cy="50" r="40" fill="none" stroke="#1e293b" strokeWidth="12" />
              <circle cx="50" cy="50" r="40" fill="none" stroke={scoreColor} strokeWidth="12"
                strokeDasharray={`${2 * Math.PI * 40 * data.score / 100} ${2 * Math.PI * 40}`} strokeLinecap="round" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold text-slate-100">{data.score}</span>
              <span className="text-slate-500 text-xs">/ 100</span>
            </div>
          </div>
          <p className="text-slate-200 text-sm font-medium mt-3">Score Global</p>
          <div className="flex items-center gap-4 mt-3 text-xs">
            <span className="flex items-center gap-1 text-red-400"><XCircle className="w-3.5 h-3.5" />{blockers.length} blocker{blockers.length !== 1 ? 's' : ''}</span>
            <span className="flex items-center gap-1 text-amber-400"><AlertTriangle className="w-3.5 h-3.5" />{warnings.length} warning{warnings.length !== 1 ? 's' : ''}</span>
          </div>
          {!isBlocked && (
            <button
              onClick={() => navigate(`/projects/${id}/codegen`)}
              className="mt-4 flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-medium transition-colors"
            >
              Gerar Codigo
            </button>
          )}
          {isBlocked && (
            <p className="mt-4 text-red-400 text-xs text-center">Seguranca insuficiente. Corrija os findings de P7 antes de gerar codigo.</p>
          )}
        </div>

        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-3">Visao Radar -- 7 Pilares</h3>
          <ResponsiveContainer width="100%" height={220}>
            <RadarChart data={radarData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
              <PolarGrid stroke="#334155" />
              <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Radar name="Score" dataKey="score" stroke="#7c3aed" fill="#7c3aed" fillOpacity={0.3} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0', fontSize: '12px' }} formatter={(v: number) => [`${v}/100`, 'Score']} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Stack Recommendation */}
      {data.stackRecommendation && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-3">Stack Recomendado</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Object.entries(data.stackRecommendation).map(([k, v]) => (
              <div key={k}>
                <p className="text-slate-500 text-xs capitalize">{k}</p>
                <p className="text-slate-200 text-sm font-medium">{v}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pillar Details */}
      <div className="grid grid-cols-1 gap-3">
        {data.pillars.map((pillar, i) => (
          <div key={i} className={`border rounded-xl p-4 ${pillarStatusBg(pillar.status)}`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <span className="text-slate-400 text-xs font-mono w-4">{i + 1}</span>
                <p className="text-slate-200 text-sm font-medium">{pillar.pillar}</p>
                {pillarTooltips[i] && <HelpTooltip text={pillarTooltips[i]} />}
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <div className="w-28 bg-slate-700 rounded-full h-1.5">
                    <div className="h-1.5 rounded-full" style={{ width: `${pillar.score}%`, backgroundColor: pillar.status === 'ok' ? '#34d399' : pillar.status === 'warning' ? '#fbbf24' : '#f87171' }} />
                  </div>
                  <span className={`text-sm font-semibold ${pillarStatusColor(pillar.status)}`}>{pillar.score}</span>
                </div>
                <span className={`px-2 py-0.5 rounded text-xs border ${
                  pillar.status === 'blocker' ? 'bg-red-900/40 text-red-400 border-red-800/40' :
                  pillar.status === 'warning' ? 'bg-amber-900/40 text-amber-400 border-amber-800/40' :
                  'bg-emerald-900/40 text-emerald-400 border-emerald-800/40'
                }`}>{pillar.status.toUpperCase()}</span>
              </div>
            </div>
            {pillar.notes && <p className="text-slate-400 text-xs ml-7">{pillar.notes}</p>}
            {pillar.status === 'blocker' && (
              <div className="ml-7 mt-2 flex gap-2">
                <button className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-violet-900/30 text-violet-400 hover:bg-violet-900/50 transition-colors">
                  <Zap className="w-3 h-3" /> Acionar Arguidor
                </button>
                <button className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-slate-800 text-slate-400 hover:bg-slate-700 transition-colors">
                  <Info className="w-3 h-3" /> Ver detalhes
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Critical Findings */}
      {data.criticalFindings && data.criticalFindings.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-slate-200 text-sm font-semibold mb-3">Findings Criticos</h3>
          <div className="space-y-2">
            {data.criticalFindings.map((f, i) => (
              <div key={i} className="p-3 rounded-lg bg-red-950/20 border border-red-900/30">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-red-400 font-medium">{f.pillar}</span>
                  <span className="text-xs text-slate-500">{f.severity}</span>
                </div>
                <p className="text-slate-300 text-sm">{f.finding}</p>
                <p className="text-slate-500 text-xs mt-1">Acao: {f.action}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Override Modal */}
      {showOverride && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-dark-100 border border-amber-700/40 rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-amber-900/40 flex items-center justify-center">
                <Lock className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <h3 className="text-slate-100 font-semibold">Override do Gatekeeper</h3>
                <p className="text-amber-400 text-xs">Requer justificativa formal - Registrado em auditoria</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-slate-400 text-xs">Justificativa</span>
              <HelpTooltip text="Campo obrigatório ao rejeitar um módulo. Descreva claramente os motivos da rejeição e o que precisa ser corrigido antes da próxima avaliação. O comentário é enviado por e-mail ao desenvolvedor responsável e registrado no audit log imutável do projeto." />
            </div>
            <textarea
              value={overrideReason} onChange={e => setOverrideReason(e.target.value)}
              rows={4} placeholder="Justificativa tecnica obrigatória..."
              className="w-full bg-dark-200 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:border-amber-500"
            />
            <div className="flex gap-3 mt-4">
              <button onClick={() => setShowOverride(false)} className="flex-1 px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-sm hover:bg-slate-700 transition-colors">Cancelar</button>
              <button disabled={!overrideReason.trim()} onClick={() => setShowOverride(false)} className="flex-1 px-4 py-2 rounded-lg bg-amber-600 text-white text-sm hover:bg-amber-500 disabled:opacity-50 transition-colors">
                Registrar Override
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
