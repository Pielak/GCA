import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Lock, Mail, Eye, EyeOff, Loader2, FolderPlus, ArrowRight, X } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'
import { useCodeGenProgressStore } from '@/stores/codeGenProgressStore'
import { apiClient as api } from '@/lib/api'
import { getErrorMessage, type ApiError } from '@/lib/errors'
import { AnimatedGearsBackground } from '@/components/AnimatedGearsBackground'

// ═══════════════════════════════════════════════════════════════════════
// Particle Network — canvas animado de fundo
// ═══════════════════════════════════════════════════════════════════════

interface Particle {
  x: number; y: number; vx: number; vy: number; r: number; o: number
}

function ParticleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particles = useRef<Particle[]>([])
  const mouse = useRef({ x: -1000, y: -1000 })
  const raf = useRef<number>(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    let w = 0, h = 0

    const resize = () => {
      w = canvas.width = canvas.offsetWidth * devicePixelRatio
      h = canvas.height = canvas.offsetHeight * devicePixelRatio
      ctx.scale(devicePixelRatio, devicePixelRatio)
    }

    const init = () => {
      resize()
      const count = Math.floor((canvas.offsetWidth * canvas.offsetHeight) / 8000)
      particles.current = Array.from({ length: Math.min(count, 120) }, () => ({
        x: Math.random() * canvas.offsetWidth,
        y: Math.random() * canvas.offsetHeight,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        r: Math.random() * 1.5 + 0.5,
        o: Math.random() * 0.5 + 0.2,
      }))
    }

    const draw = () => {
      const cw = canvas.offsetWidth, ch = canvas.offsetHeight
      ctx.clearRect(0, 0, cw, ch)

      const pts = particles.current
      const mx = mouse.current.x, my = mouse.current.y

      for (let i = 0; i < pts.length; i++) {
        const p = pts[i]
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > cw) p.vx *= -1
        if (p.y < 0 || p.y > ch) p.vy *= -1

        // Mouse repulsion
        const dx = p.x - mx, dy = p.y - my
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 120) {
          p.vx += dx / dist * 0.15
          p.vy += dy / dist * 0.15
        }

        // Draw particle
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(133, 80, 246, ${p.o})`
        ctx.fill()

        // Draw connections
        for (let j = i + 1; j < pts.length; j++) {
          const q = pts[j]
          const d = Math.hypot(p.x - q.x, p.y - q.y)
          if (d < 100) {
            ctx.beginPath()
            ctx.moveTo(p.x, p.y)
            ctx.lineTo(q.x, q.y)
            ctx.strokeStyle = `rgba(133, 80, 246, ${0.08 * (1 - d / 100)})`
            ctx.lineWidth = 0.5
            ctx.stroke()
          }
        }
      }

      raf.current = requestAnimationFrame(draw)
    }

    const handleMouse = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      mouse.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    }

    init()
    draw()
    window.addEventListener('resize', () => { resize(); })
    canvas.addEventListener('mousemove', handleMouse)

    return () => {
      cancelAnimationFrame(raf.current)
      window.removeEventListener('resize', resize)
      canvas.removeEventListener('mousemove', handleMouse)
    }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
}

// ═══════════════════════════════════════════════════════════════════════
// Feature cards com expansão
// ═══════════════════════════════════════════════════════════════════════

const FEATURES = [
  {
    id: 'personas',
    icon: '👥',
    label: '5 Personas',
    summary: 'Governança por função',
    detail: 'Admin (instância), Gerente de Projetos (escopo), Arquiteto (design), DBA (dados), Dev Sênior (implementação), Tester-QA (qualidade). Cada persona valida seu domínio no fluxo Gatekeeper antes de avançar.',
    gradient: 'from-blue-600/20 to-cyan-600/20',
    border: 'border-blue-500/30',
    glow: 'hover:shadow-[0_0_30px_rgba(59,130,246,0.15)]',
  },
  {
    id: 'ia',
    icon: '🧠',
    label: 'IA Assistida',
    summary: 'Multi-linguagem',
    detail: 'Suporte para TypeScript, Python, Go, Java, Kotlin, C#, SQL, Bash, YAML e mais. Cada linguagem tem especialista IA que entende padrões, convenções e melhores práticas do ecossistema. Análise cruzada em tempo real.',
    gradient: 'from-cyan-600/20 to-blue-600/20',
    border: 'border-cyan-500/30',
    glow: 'hover:shadow-[0_0_30px_rgba(6,182,212,0.15)]',
  },
  {
    id: 'tenant',
    icon: '🔐',
    label: 'Multi-tenant',
    summary: 'Isolamento por schema',
    detail: 'Cada projeto opera em schema PostgreSQL isolado com RLS. Contextos nunca se misturam — mesmo usuários em múltiplos projetos veem apenas dados do projeto ativo. Credenciais segregadas por projeto.',
    gradient: 'from-emerald-600/20 to-green-600/20',
    border: 'border-emerald-500/30',
    glow: 'hover:shadow-[0_0_30px_rgba(16,185,129,0.15)]',
  },
  {
    id: 'codegen',
    icon: '⚡',
    label: 'CodeGen',
    summary: 'Geração governada',
    detail: 'Código gerado pela IA passa por avaliação de políticas, revisão técnica por QA e GP, e só é publicado via PR com aprovação humana. Toda decisão fica registrada com aprovador, data e motivo.',
    gradient: 'from-amber-600/20 to-orange-600/20',
    border: 'border-amber-500/30',
    glow: 'hover:shadow-[0_0_30px_rgba(245,158,11,0.15)]',
  },
]

// ═══════════════════════════════════════════════════════════════════════
// LoginPage
// ═══════════════════════════════════════════════════════════════════════

interface ProjectOption {
  id: string
  name: string
  slug: string
}

const LAST_PROJECT_KEY = 'gca:last_project_slug'

export function LoginPage() {
  const navigate = useNavigate()
  const { login, projectLogin } = useAuth()
  const { user } = useAuthStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [mounted, setMounted] = useState(false)
  const [expandedCard, setExpandedCard] = useState<string | null>(null)
  const [projects, setProjects] = useState<ProjectOption[]>([])
  const [selectedSlug, setSelectedSlug] = useState<string>('')

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 50)
    return () => clearTimeout(t)
  }, [])

  // Carrega lista de projetos ativos para o combo + auto-seleciona o último
  // acessado (gravado em localStorage no login anterior bem-sucedido).
  useEffect(() => {
    let cancelled = false
    api.get('/auth/projects').then(res => {
      if (cancelled) return
      const list: ProjectOption[] = res.data?.projects || []
      // Ordena com o último acessado (localStorage) primeiro
      const lastSlug = localStorage.getItem(LAST_PROJECT_KEY) || ''
      list.sort((a, b) => {
        if (a.slug === lastSlug) return -1
        if (b.slug === lastSlug) return 1
        return a.name.localeCompare(b.name)
      })
      setProjects(list)
      // Pré-seleciona o último (mas user pode escolher "—" para entrar como admin)
      if (lastSlug && list.some(p => p.slug === lastSlug)) {
        setSelectedSlug(lastSlug)
      }
    }).catch(() => {
      // Sem combo (rota indisponível) — login só admin via /auth/login
    })
    return () => { cancelled = true }
  }, [])

  const handleNewProject = () => {
    setToast(
      'Ao clicar em Continuar, será aberto um questionário para ser respondido em até 5 dias úteis. ' +
      'Se existirem dúvidas, clique em Cancelar e entre em contato com o Admin. ' +
      'Você terá informações detalhadas no questionário para responder.'
    )
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      // Branch principal: projeto selecionado → projectLogin (valida membership)
      // Sem projeto selecionado → login (só funciona pra admin)
      if (selectedSlug) {
        const result = await projectLogin(email, password, selectedSlug)
        // Sucesso = backend devolveu access_token + project.id. projectLogin
        // joga em caso de 4xx — então cair aqui sem project_id é bug,
        // não credencial inválida.
        if (result?.project_id) {
          // Limpa dados de scaffold do projeto anterior antes de trocar
          useCodeGenProgressStore.getState().reset()
          localStorage.setItem(LAST_PROJECT_KEY, selectedSlug)
          navigate('/')
        } else {
          setError('Resposta inesperada do servidor — tente novamente em instantes.')
        }
      } else {
        const ok = await login(email, password)
        if (ok) {
          navigate('/')
        } else {
          setError('Email ou senha incorretos')
        }
      }
    } catch (err: unknown) {
      // O api.ts interceptor já achata o erro em { status, message, data }.
      // (err as ApiError).data é o body da resposta (com .detail).
      const detail = (err as ApiError)?.data?.detail
      const detailStr = typeof detail === 'string' ? detail : ''

      if ((err as ApiError)?.status === 401) {
        setError('Email ou senha inválidos.')
      } else if ((err as ApiError)?.status === 403) {
        // 403 com code='project_required' = não-admin tentou entrar sem projeto.
        if (detail && typeof detail === 'object' && !Array.isArray(detail) && detail.code === 'project_required') {
          setError('Selecione seu projeto no combo acima — apenas administradores podem entrar sem projeto.')
        } else if (detailStr.toLowerCase().includes('membro')) {
          setError('Você não é membro deste projeto. Verifique com o GP do projeto se foi adicionado à equipe.')
        } else {
          setError(detailStr || 'Acesso negado. Contate o administrador.')
        }
      } else if ((err as ApiError)?.status === 404) {
        setError('Projeto não encontrado.')
      } else if ((err as ApiError)?.status === 410) {
        setError('Projeto arquivado.')
      } else {
        setError(detailStr || getErrorMessage(err))
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex bg-[#0f0f1e] overflow-hidden relative">
      {/* ── Animated gears background ── */}
      <div className="absolute inset-0 z-0 lg:w-[55%]">
        <AnimatedGearsBackground />
      </div>

      {/* ── Gradient overlays (tech-forward: ciano + dark) ── */}
      <div className="absolute inset-0 z-[1] bg-gradient-to-br from-slate-950/40 via-transparent to-cyan-950/15 pointer-events-none" />
      <div className="absolute bottom-0 left-0 right-0 h-1/3 z-[1] bg-gradient-to-t from-[#0f0f1e] to-transparent pointer-events-none" />

      {/* ── Animated glow orbs (tech-forward: ciano) ── */}
      <div className="absolute top-[15%] left-[10%] w-[600px] h-[600px] rounded-full z-[1] pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(0,184,204,0.06) 0%, transparent 70%)',
          animation: 'breathe 12s ease-in-out infinite',
        }}
      />
      <div className="absolute bottom-[5%] right-[5%] w-[500px] h-[500px] rounded-full z-[1] pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(34,197,94,0.04) 0%, transparent 70%)',
          animation: 'breathe 14s ease-in-out infinite 2s',
        }}
      />

      {/* ═══ LEFT PANEL ═══ */}
      <div className="hidden lg:flex lg:w-[55%] relative z-10 flex-col justify-between p-12 xl:p-16">

        {/* Logo */}
        <div className={`transition-all duration-1000 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-6'}`}>
          <div className="flex items-center gap-4">
            <div className="relative">
              <img src="/images/gca-logo-120.png" alt="GCA" className="h-12 drop-shadow-[0_0_20px_rgba(112,56,224,0.3)]" />
              <div className="absolute -inset-2 bg-violet-500/10 rounded-2xl blur-xl -z-10" />
            </div>
            <div>
              <span className="text-white font-display text-2xl font-bold tracking-tight">GCA</span>
              <div className="flex items-center gap-2 mt-0.5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <p className="text-slate-500 text-xs tracking-[0.2em] uppercase">Sistema Operacional</p>
              </div>
            </div>
          </div>
        </div>

        {/* Hero text */}
        <div className="max-w-xl">
          <h1
            className={`font-display text-[3.5rem] leading-[1.05] font-bold text-white tracking-tight transition-all duration-1000 delay-200 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}
          >
            Orquestre.<br />
            <span className="bg-gradient-to-r from-violet-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
              Governe.
            </span><br />
            Entregue.
          </h1>
          <p className={`mt-6 text-slate-400 text-lg leading-relaxed max-w-md transition-all duration-1000 delay-400 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
            Meta-plataforma de orquestração, governança e geração assistida
            de software com rastreabilidade total.
          </p>
        </div>

        {/* Feature cards — reativos */}
        <div className={`transition-all duration-1000 delay-500 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
          <div className="grid grid-cols-2 gap-3">
            {FEATURES.map((f) => {
              const isExpanded = expandedCard === f.id
              return (
                <button
                  key={f.id}
                  onClick={() => setExpandedCard(isExpanded ? null : f.id)}
                  className={`
                    relative text-left p-4 rounded-2xl border backdrop-blur-sm
                    transition-all duration-500 ease-out cursor-pointer group
                    ${isExpanded
                      ? `bg-gradient-to-br ${f.gradient} ${f.border} scale-[1.02]`
                      : `bg-white/[0.03] border-white/[0.06] hover:bg-white/[0.06] hover:border-white/[0.12] ${f.glow}`
                    }
                  `}
                >
                  {/* Icon + label */}
                  <div className="flex items-center gap-3 mb-1">
                    <span className={`text-xl transition-transform duration-300 ${isExpanded ? 'scale-125' : 'group-hover:scale-110'}`}>
                      {f.icon}
                    </span>
                    <div>
                      <p className="text-white text-sm font-semibold">{f.label}</p>
                      <p className={`text-xs transition-all duration-300 ${isExpanded ? 'text-slate-300' : 'text-slate-500'}`}>
                        {f.summary}
                      </p>
                    </div>
                  </div>

                  {/* Expanded detail */}
                  <div className={`overflow-hidden transition-all duration-500 ease-out ${isExpanded ? 'max-h-40 opacity-100 mt-3' : 'max-h-0 opacity-0 mt-0'}`}>
                    <div className="h-px bg-gradient-to-r from-transparent via-white/10 to-transparent mb-3" />
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {f.detail}
                    </p>
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Footer */}
        <div className={`flex items-center gap-4 transition-all duration-1000 delay-700 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
          <p className="text-slate-600 text-xs">&copy; 2026 GCA</p>
          <div className="h-px flex-1 bg-gradient-to-r from-white/5 to-transparent" />
          <p className="text-slate-600 text-xs font-mono">v0.8.0</p>
        </div>
      </div>

      {/* ═══ ADMIN ACCESS BUTTON — Top Right ═══ */}
      <button
        onClick={() => navigate('/admin')}
        className="absolute top-6 right-6 z-20 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-lg flex items-center gap-2 shadow-lg transition-all transform hover:scale-105"
      >
        <Lock size={16} />
        🔐 Admin
      </button>

      {/* ═══ RIGHT PANEL — Login ═══ */}
      <div className="flex-1 flex flex-col items-center justify-center p-8 relative z-10">
        {/* Glass card */}
        <div
          className={`
            w-full max-w-[400px] p-8 rounded-3xl
            bg-white/[0.04] backdrop-blur-xl border border-white/[0.08]
            shadow-[0_8px_60px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.05)]
            transition-all duration-1000 delay-300
            ${mounted ? 'opacity-100 translate-y-0 scale-100' : 'opacity-0 translate-y-10 scale-95'}
          `}
        >
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <img src="/images/gca-icon-40.png" alt="GCA" className="w-10 h-10" />
            <span className="text-white font-display text-xl font-bold">GCA</span>
          </div>

          {/* Heading */}
          <div className="mb-8">
            <h2 className="font-display text-2xl font-bold text-white">Acesse o GCA</h2>
            <p className="mt-2 text-slate-400 text-sm">
              Suas credenciais protegidas com criptografia end-to-end.
            </p>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-5 flex items-center gap-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 animate-[shake_0.5s_ease-in-out]">
              <div className="w-8 h-8 rounded-full bg-red-500/20 flex items-center justify-center flex-shrink-0">
                <X className="w-4 h-4 text-red-400" />
              </div>
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}

          {/* Admin button — visible only to admins */}
          {user?.is_admin && (
            <div className="mb-6">
              <button
                type="button"
                onClick={() => navigate('/admin')}
                className="w-full bg-gradient-to-r from-red-600 to-orange-600 hover:from-red-700 hover:to-orange-700 text-white font-semibold py-3 px-6 rounded-xl flex items-center justify-center gap-3 shadow-lg hover:shadow-xl transition-all transform hover:scale-105"
              >
                <Lock size={20} />
                🔐 Painel de Administração
              </button>
              <p className="text-slate-500 text-xs mt-2 text-center">Gerencie toda a instância GCA (usuários, projetos globais, configurações)</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-5">
            {/* Projeto (combo) — obrigatório para membros */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs text-slate-400 font-medium">
                <FolderPlus className="w-3.5 h-3.5" />
                PROJETO
              </label>
              <select
                value={selectedSlug}
                onChange={e => setSelectedSlug(e.target.value)}
                disabled={loading}
                className="
                  w-full bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-3.5
                  text-sm text-white
                  focus:outline-none focus:border-violet-500/50 focus:bg-white/[0.08]
                  transition-all duration-300 appearance-none cursor-pointer
                "
              >
                <option value="" className="bg-[#1c1c34]">Selecione um projeto</option>
                {projects.map(p => (
                  <option key={p.id} value={p.slug} className="bg-[#1c1c34]">
                    {p.name}
                  </option>
                ))}
              </select>
              <p className="text-[10px] text-slate-600">
                {selectedSlug
                  ? 'Suas credenciais serão validadas neste projeto.'
                  : 'Selecione seu projeto para continuar. Administradores podem usar o painel acima.'}
              </p>
            </div>

            {/* Email */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs text-slate-400 font-medium">
                <Mail className="w-3.5 h-3.5" />
                EMAIL
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="
                  w-full bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-3.5
                  text-sm text-white placeholder-slate-600
                  focus:outline-none focus:border-violet-500/50 focus:bg-white/[0.08]
                  focus:shadow-[0_0_0_3px_rgba(112,56,224,0.1),inset_0_0_20px_rgba(112,56,224,0.03)]
                  transition-all duration-300
                "
                placeholder="seu@email.com"
                required
                autoComplete="email"
                disabled={loading}
              />
            </div>

            {/* Password */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs text-slate-400 font-medium">
                <Lock className="w-3.5 h-3.5" />
                SENHA
              </label>
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="
                    w-full bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 pr-12 py-3.5
                    text-sm text-white placeholder-slate-600
                    focus:outline-none focus:border-violet-500/50 focus:bg-white/[0.08]
                    focus:shadow-[0_0_0_3px_rgba(112,56,224,0.1),inset_0_0_20px_rgba(112,56,224,0.03)]
                    transition-all duration-300
                  "
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={() => setShowPass(v => !v)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                  tabIndex={-1}
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !email || !password}
              className="
                relative w-full py-3.5 rounded-xl text-sm font-semibold text-white
                bg-gradient-to-r from-violet-600 via-violet-500 to-purple-600
                hover:from-violet-500 hover:via-violet-400 hover:to-purple-500
                disabled:opacity-40 disabled:cursor-not-allowed
                shadow-[0_4px_20px_rgba(112,56,224,0.3),0_0_60px_rgba(112,56,224,0.1)]
                hover:shadow-[0_4px_30px_rgba(112,56,224,0.45),0_0_80px_rgba(112,56,224,0.15)]
                transition-all duration-300 group overflow-hidden
              "
            >
              {/* Shine sweep */}
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500">
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/15 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700" />
              </div>
              <span className="relative flex items-center justify-center gap-2">
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Autenticando
                    <span className="animate-pulse">...</span>
                  </>
                ) : (
                  <>
                    Entrar
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
                  </>
                )}
              </span>
            </button>
          </form>

          {/* Links */}
          <div className="mt-5 text-center space-y-2">
            <Link
              to="/reset-password"
              className="block text-sm text-slate-500 hover:text-violet-400 transition-colors duration-300"
            >
              Esqueci minha senha
            </Link>
            <div className="text-xs text-slate-600">
              Não tem projeto?{" "}
              <Link
                to="/solicitar-projeto"
                className="text-violet-400 hover:text-violet-300 underline-offset-2 hover:underline transition-colors"
              >
                Solicitar novo projeto
              </Link>
            </div>
          </div>
        </div>

        {/* Security badge */}
        <div className={`mt-6 flex items-center gap-2 text-slate-600 text-xs transition-all duration-1000 delay-500 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
          <Lock className="w-3 h-3" />
          <span>Criptografia end-to-end ativa</span>
          <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 max-w-sm z-50 animate-[fadeUp_0.4s_ease-out]">
          <div className="bg-[#1c1c34]/95 backdrop-blur-xl border border-violet-500/20 rounded-2xl p-5 shadow-[0_8px_40px_rgba(0,0,0,0.5)]">
            <p className="text-slate-200 text-sm leading-relaxed">{toast}</p>
            <div className="flex gap-2.5 mt-4">
              <button
                onClick={() => { setToast(null); navigate('/solicitar-projeto') }}
                className="flex-1 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 text-white rounded-xl py-2.5 text-xs font-semibold transition-colors"
              >
                Continuar
              </button>
              <button
                onClick={() => setToast(null)}
                className="flex-1 bg-white/5 hover:bg-white/10 text-slate-300 rounded-xl py-2.5 text-xs font-medium border border-white/10 transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Animations */}
      <style>{`
        @keyframes breathe {
          0%, 100% { transform: scale(1); opacity: 0.5; }
          50% { transform: scale(1.15); opacity: 1; }
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          20% { transform: translateX(-6px); }
          40% { transform: translateX(6px); }
          60% { transform: translateX(-4px); }
          80% { transform: translateX(4px); }
        }
      `}</style>
    </div>
  )
}
