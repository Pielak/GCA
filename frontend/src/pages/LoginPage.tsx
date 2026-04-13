import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Lock, Mail, Eye, EyeOff, Loader2, FolderPlus, ArrowRight, Hexagon, Activity, Shield, Cpu, Database, GitBranch } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'

function OrbitalRing({ size, duration, delay, opacity }: { size: number; duration: number; delay: number; opacity: number }) {
  return (
    <div
      className="absolute rounded-full border border-brand-500/[var(--ring-opacity)]"
      style={{
        width: size,
        height: size,
        left: '50%',
        top: '50%',
        transform: 'translate(-50%, -50%)',
        '--ring-opacity': opacity,
        animation: `spin ${duration}s linear infinite`,
        animationDelay: `${delay}s`,
      } as React.CSSProperties}
    >
      <div
        className="absolute w-1.5 h-1.5 rounded-full bg-brand-400"
        style={{ top: 0, left: '50%', transform: 'translate(-50%, -50%)', opacity: opacity * 3 }}
      />
    </div>
  )
}

function GridPattern() {
  return (
    <svg className="absolute inset-0 w-full h-full" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
          <path d="M 60 0 L 0 0 0 60" fill="none" stroke="rgba(112, 56, 224, 0.04)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#grid)" />
    </svg>
  )
}

function FloatingIcon({ icon: Icon, x, y, delay }: { icon: typeof Shield; x: string; y: string; delay: number }) {
  return (
    <div
      className="absolute animate-float"
      style={{
        left: x,
        top: y,
        animationDelay: `${delay}s`,
        animationDuration: `${5 + delay}s`,
      }}
    >
      <div className="w-10 h-10 rounded-xl bg-surface-raised/80 border border-edge-subtle backdrop-blur-sm flex items-center justify-center shadow-card">
        <Icon className="w-4.5 h-4.5 text-brand-300/60" />
      </div>
    </div>
  )
}

export function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const { user } = useAuthStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    requestAnimationFrame(() => setMounted(true))
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
      const success = await login(email, password)
      if (success) {
        const currentUser = useAuthStore.getState().user
        if (currentUser && !(currentUser as any).first_access_completed) {
          navigate('/')
        } else {
          navigate('/')
        }
      } else {
        setError('Email ou senha incorretos')
      }
    } catch (err: any) {
      if (err?.status === 403) {
        setError('Conta bloqueada. Contate o administrador.')
      } else {
        setError(err?.message || 'Erro ao fazer login')
      }
    } finally {
      setLoading(false)
    }
  }

  const features = [
    { icon: Shield, label: '7 Pilares', desc: 'Gatekeeper documental com avaliação por pilar' },
    { icon: Cpu, label: 'IA Assistida', desc: 'Agentes especializados para cada domínio' },
    { icon: Database, label: 'Multi-tenant', desc: 'Isolamento total por schema por projeto' },
    { icon: GitBranch, label: 'CodeGen', desc: 'Geração governada com gates humanos' },
  ]

  return (
    <div className="min-h-screen flex bg-surface-void overflow-hidden">
      {/* Noise texture overlay */}
      <div className="fixed inset-0 bg-noise pointer-events-none z-10" />

      {/* === LEFT PANEL — Identity & Atmosphere === */}
      <div className="hidden lg:flex lg:w-[52%] relative flex-col justify-between p-12 xl:p-16">
        {/* Background layers */}
        <div className="absolute inset-0 bg-gradient-to-br from-surface-deep via-surface-base to-surface-void" />
        <GridPattern />

        {/* Radial glow */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-radial from-brand-glow via-transparent to-transparent rounded-full" />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-gradient-radial from-accent-glow via-transparent to-transparent rounded-full" />

        {/* Floating tech icons */}
        <FloatingIcon icon={Shield} x="15%" y="25%" delay={0} />
        <FloatingIcon icon={Activity} x="75%" y="18%" delay={1.2} />
        <FloatingIcon icon={Hexagon} x="65%" y="65%" delay={2.4} />
        <FloatingIcon icon={Cpu} x="20%" y="72%" delay={0.8} />

        {/* Orbital rings - centro decorativo */}
        <div className="absolute top-[40%] left-[45%]">
          <OrbitalRing size={180} duration={20} delay={0} opacity={0.08} />
          <OrbitalRing size={280} duration={30} delay={2} opacity={0.05} />
          <OrbitalRing size={400} duration={45} delay={4} opacity={0.03} />
        </div>

        {/* Content - relative to sit above decorations */}
        <div className="relative z-20">
          <div
            className={`flex items-center gap-3.5 transition-all duration-700 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4'}`}
          >
            <img src="/images/gca-logo-120.png" alt="GCA" className="h-11 drop-shadow-lg" />
            <div>
              <span className="text-ink-primary font-display text-xl font-bold tracking-tight">GCA</span>
              <p className="text-ink-muted text-xs tracking-wide uppercase">Governança e Codificação Assistida</p>
            </div>
          </div>
        </div>

        <div className="relative z-20 max-w-lg">
          <div
            className={`transition-all duration-700 delay-200 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}
          >
            <h1 className="font-display text-display-xl text-ink-primary">
              Orquestre.{' '}
              <span className="bg-gradient-brand bg-clip-text text-transparent">
                Governe.
              </span>
              <br />
              Entregue.
            </h1>
            <p className="mt-6 text-ink-secondary text-base leading-relaxed max-w-md">
              Plataforma de orquestração e governança de projetos de software com
              IA assistida, isolamento por tenant e rastreabilidade ponta a ponta.
            </p>
          </div>

          {/* Feature cards */}
          <div
            className={`grid grid-cols-2 gap-3 mt-10 transition-all duration-700 delay-500 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}
          >
            {features.map(({ icon: Icon, label, desc }, i) => (
              <div
                key={label}
                className="group relative p-4 rounded-2xl bg-surface-raised/60 border border-edge-subtle backdrop-blur-sm hover:border-edge-brand hover:bg-surface-raised transition-all duration-300"
                style={{ animationDelay: `${600 + i * 100}ms` }}
              >
                <div className="w-9 h-9 rounded-xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center mb-3 group-hover:bg-brand-500/20 group-hover:border-brand-500/30 transition-colors duration-300">
                  <Icon className="w-4 h-4 text-brand-300" />
                </div>
                <p className="text-ink-primary text-sm font-semibold">{label}</p>
                <p className="text-ink-muted text-xs mt-1 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        <div
          className={`relative z-20 flex items-center gap-6 transition-all duration-700 delay-700 ${mounted ? 'opacity-100' : 'opacity-0'}`}
        >
          <p className="text-ink-muted text-xs">&copy; 2026 GCA — Gestão de Codificação Assistida</p>
          <div className="h-px flex-1 bg-gradient-to-r from-edge-subtle to-transparent" />
        </div>
      </div>

      {/* === RIGHT PANEL — Login Form === */}
      <div className="flex-1 flex flex-col items-center justify-center p-8 relative">
        {/* Subtle gradient background */}
        <div className="absolute inset-0 bg-gradient-to-b from-surface-base via-surface-deep to-surface-void" />
        <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-edge-brand to-transparent" />

        <div
          className={`relative z-20 w-full max-w-[380px] transition-all duration-700 delay-300 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}
        >
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-10">
            <img src="/images/gca-icon-40.png" alt="GCA" className="w-10 h-10" />
            <span className="text-ink-primary font-display text-xl font-bold">GCA</span>
          </div>

          <div className="mb-8">
            <h2 className="font-display text-display-md text-ink-primary">Bem-vindo</h2>
            <p className="mt-2 text-ink-secondary text-sm">
              Informe suas credenciais para acessar a plataforma.
            </p>
          </div>

          {error && (
            <div className="mb-6 bg-status-error/10 border border-status-error/20 rounded-xl p-3.5 animate-fade-in">
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-5">
            <div className="space-y-1.5">
              <label className="block text-xs text-ink-secondary font-medium uppercase tracking-wider">Email</label>
              <div className="relative group">
                <Mail className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-muted group-focus-within:text-brand-400 transition-colors" />
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full bg-surface-raised border border-edge rounded-xl pl-10 pr-4 py-3 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-glow transition-all duration-200"
                  placeholder="seu@email.com"
                  required
                  autoComplete="email"
                  disabled={loading}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs text-ink-secondary font-medium uppercase tracking-wider">Senha</label>
              <div className="relative group">
                <Lock className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-muted group-focus-within:text-brand-400 transition-colors" />
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full bg-surface-raised border border-edge rounded-xl pl-10 pr-11 py-3 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-glow transition-all duration-200"
                  placeholder="Sua senha"
                  required
                  autoComplete="current-password"
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={() => setShowPass(v => !v)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-secondary transition-colors"
                  tabIndex={-1}
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !email || !password}
              className="relative w-full bg-brand-500 hover:bg-brand-400 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl py-3 text-sm font-semibold transition-all duration-200 flex items-center justify-center gap-2 shadow-glow-brand hover:shadow-glow-brand group overflow-hidden"
            >
              {/* Shimmer effect on hover */}
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent opacity-0 group-hover:opacity-100 group-hover:animate-shimmer" style={{ backgroundSize: '200% 100%' }} />
              <span className="relative">
                {loading ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Autenticando...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    Entrar
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </span>
                )}
              </span>
            </button>
          </form>

          <div className="mt-5 text-center">
            <Link
              to="/reset-password"
              className="text-sm text-ink-secondary hover:text-brand-300 transition-colors"
            >
              Esqueci minha senha
            </Link>
          </div>

          {/* Criar Novo Projeto */}
          <div className="mt-8 pt-8 border-t border-edge-subtle">
            <button
              type="button"
              onClick={handleNewProject}
              className="w-full flex items-center justify-center gap-2.5 bg-accent-500/10 border border-accent-500/20 hover:bg-accent-500/15 hover:border-accent-500/30 text-accent-300 rounded-xl py-3 text-sm font-medium transition-all duration-200"
            >
              <FolderPlus className="w-4 h-4" />
              Criar Novo Projeto
            </button>
          </div>

          <p className="mt-8 text-xs text-ink-muted text-center flex items-center justify-center gap-1.5">
            <Lock className="w-3 h-3" />
            Dados protegidos com criptografia ponta a ponta
          </p>
        </div>

        {/* Toast */}
        {toast && (
          <div className="fixed bottom-6 right-6 max-w-sm bg-surface-overlay border border-edge-brand rounded-2xl p-5 shadow-elevated animate-fade-up z-50">
            <p className="text-ink-primary text-sm leading-relaxed">{toast}</p>
            <div className="flex gap-2.5 mt-4">
              <button
                onClick={() => { setToast(null); navigate('/novo-projeto') }}
                className="flex-1 bg-brand-500 hover:bg-brand-400 text-white rounded-xl py-2.5 text-xs font-semibold transition-colors"
              >
                Continuar
              </button>
              <button
                onClick={() => setToast(null)}
                className="flex-1 bg-surface-raised hover:bg-surface-float text-ink-secondary rounded-xl py-2.5 text-xs font-medium border border-edge-subtle transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>

      {/* CSS for orbital animation */}
      <style>{`
        @keyframes spin {
          from { transform: translate(-50%, -50%) rotate(0deg); }
          to { transform: translate(-50%, -50%) rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
