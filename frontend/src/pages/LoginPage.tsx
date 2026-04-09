import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Code2, Lock, Mail, Eye, EyeOff, Shield, Zap, Loader2, FolderPlus } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'

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
        // useAuth already stores token and user
        // Check if first access requires password change
        const currentUser = useAuthStore.getState().user
        if (currentUser && !(currentUser as any).first_access_completed) {
          // AppLayout will detect this and show FirstAccessModal
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

  return (
    <div className="min-h-screen flex bg-dark">
      {/* Left panel - Branding */}
      <div className="hidden lg:flex lg:w-[45%] bg-gradient-to-br from-dark via-dark-100 to-dark flex-col justify-between p-12">
        <div className="flex items-center gap-3">
          <img src="/images/gca-logo-120.png" alt="GCA" className="h-10" />
          <div>
            <span className="text-white text-lg font-semibold">GCA</span>
            <p className="text-slate-400 text-xs">Gestao de Codificação Assistida</p>
          </div>
        </div>

        <div className="space-y-8">
          <div>
            <h2 className="text-3xl font-semibold text-white leading-tight">
              Orquestre projetos.<br />
              <span className="text-violet-400">Governe com confianca.</span>
            </h2>
            <p className="mt-4 text-slate-300 text-base leading-relaxed">
              Meta-plataforma de orquestracao, governanca e visibilidade de projetos de software
              com isolamento por tenant, ciclo documental completo e rastreabilidade total.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {[
              { icon: Shield, label: '7 Pilares', desc: 'Gatekeeper documental' },
              { icon: Code2, label: 'Code Gen', desc: 'Geração assistida de codigo' },
              { icon: Zap, label: 'QA Readiness', desc: 'Testes em containers isolados' },
              { icon: Lock, label: 'Multi-tenant', desc: 'Isolamento por schema' },
            ].map(({ icon: Icon, label, desc }) => (
              <div key={label} className="flex items-start gap-3 p-3 rounded-lg bg-white/5 border border-slate-700">
                <div className="w-8 h-8 rounded-md bg-violet-600/20 border border-violet-600/30 flex items-center justify-center flex-shrink-0">
                  <Icon className="w-4 h-4 text-violet-400" />
                </div>
                <div>
                  <p className="text-white text-sm font-medium">{label}</p>
                  <p className="text-slate-400 text-xs">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-slate-500 text-sm">&copy; 2026 GCA</p>
      </div>

      {/* Right panel - Login form */}
      <div className="flex-1 flex flex-col items-center justify-center p-8 bg-dark-100">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <img src="/images/gca-icon-40.png" alt="GCA" className="w-9 h-9" />
            <span className="text-white text-lg font-semibold">GCA</span>
          </div>

          <h2 className="text-2xl font-semibold text-white">Entrar no GCA</h2>
          <p className="mt-1 text-slate-400 text-sm">
            Informe suas credenciais para acessar a plataforma.
          </p>

          {error && (
            <div className="mt-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3 flex items-center gap-2">
              <span className="text-red-300 text-sm">{error}</span>
            </div>
          )}

          <form onSubmit={handleLogin} className="mt-8 space-y-5">
            <div>
              <label className="block text-sm text-slate-300 font-medium mb-1.5">Email</label>
              <div className="relative">
                <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full bg-dark-200 border border-slate-700 rounded-lg pl-9 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                  placeholder="seu@email.com"
                  required
                  autoComplete="email"
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-300 font-medium mb-1.5">Senha</label>
              <div className="relative">
                <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full bg-dark-200 border border-slate-700 rounded-lg pl-9 pr-10 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                  placeholder="Sua senha"
                  required
                  autoComplete="current-password"
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={() => setShowPass(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                  tabIndex={-1}
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !email || !password}
              className="w-full bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Autenticando...
                </>
              ) : (
                'Entrar'
              )}
            </button>
          </form>

          <div className="mt-4 text-center">
            <Link
              to="/reset-password"
              className="text-sm text-violet-400 hover:text-violet-300 transition-colors"
            >
              Esqueci minha senha
            </Link>
          </div>

          {/* Criar Novo Projeto */}
          <div className="mt-6 pt-6 border-t border-slate-700">
            <button
              type="button"
              onClick={handleNewProject}
              className="w-full flex items-center justify-center gap-2 bg-emerald-600/20 border border-emerald-600/30 hover:bg-emerald-600/30 text-emerald-400 rounded-lg py-2.5 text-sm font-medium transition-colors"
            >
              <FolderPlus className="w-4 h-4" />
              Criar Novo Projeto GCA
            </button>
          </div>

          <p className="mt-6 text-xs text-slate-500 text-center">
            Seus dados estão protegidos com criptografia de ponta a ponta.
          </p>

          {/* Toast */}
          {toast && (
            <div className="fixed bottom-6 right-6 max-w-sm bg-dark-100 border border-violet-600/30 rounded-xl p-4 shadow-2xl animate-fade-in z-50">
              <p className="text-slate-200 text-sm leading-relaxed">{toast}</p>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => { setToast(null); navigate('/novo-projeto') }}
                  className="flex-1 bg-violet-600 hover:bg-violet-500 text-white rounded-lg py-2 text-xs font-medium transition-colors"
                >
                  Continuar
                </button>
                <button
                  onClick={() => setToast(null)}
                  className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg py-2 text-xs font-medium transition-colors"
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
