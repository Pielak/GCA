import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  Lock, Mail, Eye, EyeOff, Loader2, ArrowRight, X, ArrowLeft,
  Shield, CheckCircle2, AlertCircle, AlertTriangle,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { apiClient } from '@/lib/api'
import { getErrorMessage, type ApiError } from '@/lib/errors'

// ═══════════════════════════════════════════════════════════════════════
// Particle Network — canvas animado de fundo (reutilizado do LoginPage)
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

        const dx = p.x - mx, dy = p.y - my
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 120) {
          p.vx += dx / dist * 0.15
          p.vy += dy / dist * 0.15
        }

        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(133, 80, 246, ${p.o})`
        ctx.fill()

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
    window.addEventListener('resize', resize)
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
// Regras de senha (reutilizadas do FirstAccessModal)
// ═══════════════════════════════════════════════════════════════════════

interface PasswordRule {
  id: string
  test: (pw: string) => boolean
  label: string
}

const PASSWORD_RULES: PasswordRule[] = [
  { id: 'length', test: pw => pw.length >= 10, label: 'Mínimo 10 caracteres' },
  { id: 'upper', test: pw => /[A-Z]/.test(pw), label: 'Pelo menos 1 letra maiúscula' },
  { id: 'digit', test: pw => /[0-9]/.test(pw), label: 'Pelo menos 1 número' },
  { id: 'special', test: pw => /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(pw), label: 'Pelo menos 1 caractere especial' },
]

// ═══════════════════════════════════════════════════════════════════════
// Estados da página
// ═══════════════════════════════════════════════════════════════════════

type PageState = 'loading' | 'not-found' | 'login' | 'first-access' | 'forgot-password' | 'reset-sent'

// ═══════════════════════════════════════════════════════════════════════
// ProjectLoginPage
// ═══════════════════════════════════════════════════════════════════════

export function ProjectLoginPage() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const { projectLogin } = useAuth()
  const { setUser, user } = useAuthStore()

  // Estado da página
  const [pageState, setPageState] = useState<PageState>('loading')
  const [projectName, setProjectName] = useState<string>('')
  const [projectStatus, setProjectStatus] = useState<string>('')

  // Formulário de login
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Esqueci minha senha
  const [resetEmail, setResetEmail] = useState('')
  const [resetLoading, setResetLoading] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)

  const handleForgotPassword = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resetEmail || !slug) return
    setResetError(null)
    setResetLoading(true)

    try {
      await api.post('/auth/reset-password', { email: resetEmail })
      setPageState('reset-sent')
    } catch (err: unknown) {
      // Não revelar se email existe ou não — sempre mostrar sucesso
      setPageState('reset-sent')
    } finally {
      setResetLoading(false)
    }
  }, [resetEmail, slug])

  // First access — troca de senha
  const [tempPassword, setTempPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const [changeError, setChangeError] = useState<string | null>(null)
  const [pendingProjectId, setPendingProjectId] = useState<string | null>(null)

  // Animação de entrada
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 50)
    return () => clearTimeout(t)
  }, [])

  // Busca dados do projeto pelo slug
  useEffect(() => {
    if (!slug) {
      setPageState('not-found')
      return
    }

    let cancelled = false

    const fetchProject = async () => {
      try {
        const response = await api.get(`/projects/by-slug/${slug}`)
        if (cancelled) return
        const { name, status } = response.data
        setProjectName(name)
        setProjectStatus(status)
        setPageState('login')
      } catch {
        if (!cancelled) {
          setPageState('not-found')
        }
      }
    }

    fetchProject()
    return () => { cancelled = true }
  }, [slug])

  // Login no projeto
  const handleLogin = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!slug) return
    setError(null)
    setLoading(true)

    try {
      const result = await projectLogin(email, password, slug)

      if (!result.first_access_completed) {
        // Precisa trocar senha antes de prosseguir
        setTempPassword(password)
        setPendingProjectId(result.project_id)
        setPageState('first-access')
      } else {
        navigate(`/projects/${result.project_id}`)
      }
    } catch (err: unknown) {
      if ((err as ApiError)?.status === 404) {
        setError('Projeto não encontrado.')
      } else if ((err as ApiError)?.status === 403) {
        setError('Você não é membro deste projeto.')
      } else if ((err as ApiError)?.status === 401) {
        setError('Email ou senha incorretos.')
      } else {
        setError(getErrorMessage(err))
      }
    } finally {
      setLoading(false)
    }
  }, [slug, email, password, projectLogin, navigate])

  // Troca de senha (first access)
  const allRulesPass = PASSWORD_RULES.every(r => r.test(newPassword))
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword
  const canSubmitChange = allRulesPass && passwordsMatch && !changingPassword

  const handleChangePassword = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    setChangeError(null)
    setChangingPassword(true)

    try {
      await apiClient.post('/auth/change-first-password', {
        temporary_password: tempPassword,
        new_password: newPassword,
      })

      if (user) {
        setUser({ ...user, first_access_completed: true })
      }

      // Redireciona ao projeto
      if (pendingProjectId) {
        navigate(`/projects/${pendingProjectId}`)
      }
    } catch (err: unknown) {
      setChangeError(getErrorMessage(err))
    } finally {
      setChangingPassword(false)
    }
  }, [tempPassword, newPassword, user, setUser, pendingProjectId, navigate])

  // ─── Render: Loading ───
  if (pageState === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#06060e]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
          <p className="text-slate-400 text-sm">Carregando projeto...</p>
        </div>
      </div>
    )
  }

  // ─── Render: Projeto nao encontrado ───
  if (pageState === 'not-found') {
    return (
      <div className="min-h-screen flex bg-[#06060e] overflow-hidden relative">
        <div className="absolute inset-0 z-0">
          <ParticleCanvas />
        </div>
        <div className="absolute inset-0 z-[1] bg-gradient-to-br from-violet-950/30 via-transparent to-cyan-950/20 pointer-events-none" />

        <div className="flex-1 flex flex-col items-center justify-center p-8 relative z-10">
          <div className={`
            w-full max-w-[440px] p-8 rounded-3xl text-center
            bg-white/[0.04] backdrop-blur-xl border border-white/[0.08]
            shadow-[0_8px_60px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.05)]
            transition-all duration-1000
            ${mounted ? 'opacity-100 translate-y-0 scale-100' : 'opacity-0 translate-y-10 scale-95'}
          `}>
            <div className="w-16 h-16 mx-auto rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-5">
              <X className="w-8 h-8 text-red-400" />
            </div>
            <h2 className="font-display text-2xl font-bold text-white mb-2">Projeto não encontrado</h2>
            <p className="text-slate-400 text-sm mb-6">
              O link <span className="text-violet-400 font-mono text-xs">/p/{slug}</span> não corresponde a nenhum projeto ativo.
            </p>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Ir para login principal
            </Link>
          </div>
        </div>

        <style>{`
          @keyframes breathe {
            0%, 100% { transform: scale(1); opacity: 0.5; }
            50% { transform: scale(1.15); opacity: 1; }
          }
        `}</style>
      </div>
    )
  }

  // ─── Render: First Access (troca de senha) ───
  if (pageState === 'first-access') {
    return (
      <div className="min-h-screen flex bg-[#06060e] overflow-hidden relative">
        <div className="absolute inset-0 z-0">
          <ParticleCanvas />
        </div>
        <div className="absolute inset-0 z-[1] bg-gradient-to-br from-violet-950/30 via-transparent to-cyan-950/20 pointer-events-none" />
        <div className="absolute bottom-0 left-0 right-0 h-1/3 z-[1] bg-gradient-to-t from-[#06060e] to-transparent pointer-events-none" />

        <div className="flex-1 flex flex-col items-center justify-center p-8 relative z-10">
          <div className={`
            w-full max-w-[440px] p-8 rounded-3xl
            bg-white/[0.04] backdrop-blur-xl border border-white/[0.08]
            shadow-[0_8px_60px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.05)]
            transition-all duration-1000
            ${mounted ? 'opacity-100 translate-y-0 scale-100' : 'opacity-0 translate-y-10 scale-95'}
          `}>
            {/* Header */}
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-600/30 flex items-center justify-center">
                <Shield className="w-5 h-5 text-violet-400" />
              </div>
              <div>
                <h2 className="font-display text-xl font-bold text-white">Definir Senha Segura</h2>
                <p className="text-slate-400 text-sm">Primeiro acesso ao projeto</p>
              </div>
            </div>

            {/* Nome do projeto */}
            <div className="mt-4 mb-4 bg-violet-500/10 border border-violet-500/20 rounded-xl px-4 py-3">
              <p className="text-violet-300 text-sm font-semibold">{projectName}</p>
            </div>

            {/* Aviso */}
            <div className="mb-5 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-amber-300 text-xs font-semibold">Importante</p>
                <p className="text-amber-200/80 text-xs mt-0.5">
                  Crie uma nova senha para continuar. Sua senha temporária será invalidada.
                </p>
              </div>
            </div>

            {/* Erro */}
            {changeError && (
              <div className="mb-5 flex items-center gap-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 animate-[shake_0.5s_ease-in-out]">
                <div className="w-8 h-8 rounded-full bg-red-500/20 flex items-center justify-center flex-shrink-0">
                  <X className="w-4 h-4 text-red-400" />
                </div>
                <p className="text-red-300 text-sm">{changeError}</p>
              </div>
            )}

            <form onSubmit={handleChangePassword} className="space-y-5">
              {/* Nova Senha */}
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-xs text-slate-400 font-medium">
                  <Lock className="w-3.5 h-3.5" />
                  NOVA SENHA
                </label>
                <div className="relative">
                  <input
                    type={showNew ? 'text' : 'password'}
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    className="
                      w-full bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 pr-12 py-3.5
                      text-sm text-white placeholder-slate-600
                      focus:outline-none focus:border-violet-500/50 focus:bg-white/[0.08]
                      focus:shadow-[0_0_0_3px_rgba(112,56,224,0.1),inset_0_0_20px_rgba(112,56,224,0.03)]
                      transition-all duration-300
                    "
                    placeholder="Mínimo 10 caracteres"
                    disabled={changingPassword}
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={() => setShowNew(v => !v)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                    tabIndex={-1}
                  >
                    {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                {newPassword.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {PASSWORD_RULES.map(rule => {
                      const passes = rule.test(newPassword)
                      return (
                        <div key={rule.id} className="flex items-center gap-2">
                          {passes ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                          )}
                          <span className={`text-xs ${passes ? 'text-emerald-400' : 'text-red-400'}`}>
                            {rule.label}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Confirmar Senha */}
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-xs text-slate-400 font-medium">
                  <Lock className="w-3.5 h-3.5" />
                  CONFIRMAR SENHA
                </label>
                <div className="relative">
                  <input
                    type={showConfirm ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    className={`
                      w-full bg-white/[0.05] border rounded-xl px-4 pr-12 py-3.5
                      text-sm text-white placeholder-slate-600
                      focus:outline-none focus:bg-white/[0.08]
                      transition-all duration-300
                      ${confirmPassword.length > 0 && !passwordsMatch
                        ? 'border-red-500/50 focus:border-red-500/50 focus:shadow-[0_0_0_3px_rgba(239,68,68,0.1)]'
                        : 'border-white/[0.08] focus:border-violet-500/50 focus:shadow-[0_0_0_3px_rgba(112,56,224,0.1),inset_0_0_20px_rgba(112,56,224,0.03)]'
                      }
                    `}
                    placeholder="Repita a nova senha"
                    disabled={changingPassword}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirm(v => !v)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                    tabIndex={-1}
                  >
                    {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                {confirmPassword.length > 0 && (
                  <div className="mt-2 flex items-center gap-2">
                    {passwordsMatch ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-xs text-emerald-400">Senhas conferem</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                        <span className="text-xs text-red-400">Senhas não conferem</span>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={!canSubmitChange}
                className="
                  relative w-full py-3.5 rounded-xl text-sm font-semibold text-white
                  bg-gradient-to-r from-emerald-600 via-emerald-500 to-teal-600
                  hover:from-emerald-500 hover:via-emerald-400 hover:to-teal-500
                  disabled:opacity-40 disabled:cursor-not-allowed
                  shadow-[0_4px_20px_rgba(16,185,129,0.3)]
                  transition-all duration-300 group overflow-hidden
                "
              >
                <span className="relative flex items-center justify-center gap-2">
                  {changingPassword ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Salvando...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      Salvar e Continuar
                    </>
                  )}
                </span>
              </button>
            </form>
          </div>

          {/* Security badge */}
          <div className={`mt-6 flex items-center gap-2 text-slate-600 text-xs transition-all duration-1000 delay-500 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
            <Lock className="w-3 h-3" />
            <span>Criptografia end-to-end ativa</span>
            <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
          </div>
        </div>

        <style>{`
          @keyframes breathe {
            0%, 100% { transform: scale(1); opacity: 0.5; }
            50% { transform: scale(1.15); opacity: 1; }
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

  // ─── Render: Email de reset enviado ───
  if (pageState === 'reset-sent') {
    return (
      <div className="min-h-screen flex bg-[#06060e] overflow-hidden relative">
        <div className="absolute inset-0 z-0"><ParticleCanvas /></div>
        <div className="absolute inset-0 z-[1] bg-gradient-to-br from-violet-950/30 via-transparent to-cyan-950/20 pointer-events-none" />
        <div className="flex-1 flex flex-col items-center justify-center p-8 relative z-10">
          <div className="w-full max-w-sm">
            <div className="bg-slate-900/80 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-8 shadow-2xl text-center">
              <div className="w-14 h-14 rounded-full bg-emerald-500/20 flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-7 h-7 text-emerald-400" />
              </div>
              <h2 className="text-lg font-bold text-white mb-2">Email enviado</h2>
              <p className="text-slate-400 text-sm mb-6">
                Se o email informado estiver cadastrado neste projeto, você receberá instruções para redefinir sua senha.
              </p>
              <button
                onClick={() => setPageState('login')}
                className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 transition-colors"
              >
                Voltar ao login
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ─── Render: Esqueci minha senha ───
  if (pageState === 'forgot-password') {
    return (
      <div className="min-h-screen flex bg-[#06060e] overflow-hidden relative">
        <div className="absolute inset-0 z-0"><ParticleCanvas /></div>
        <div className="absolute inset-0 z-[1] bg-gradient-to-br from-violet-950/30 via-transparent to-cyan-950/20 pointer-events-none" />
        <div className="flex-1 flex flex-col items-center justify-center p-8 relative z-10">
          <div className="w-full max-w-sm">
            <div className="bg-slate-900/80 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-8 shadow-2xl">
              <div className="mb-6">
                <h2 className="text-xl font-bold text-white mb-1">Redefinir senha</h2>
                <p className="text-slate-400 text-sm">
                  Projeto: <span className="text-violet-400 font-medium">{projectName}</span>
                </p>
                <p className="text-slate-500 text-xs mt-1">
                  Informe seu email para receber o link de redefinição.
                </p>
              </div>

              {resetError && (
                <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center gap-2">
                  <X className="w-4 h-4 text-red-400 flex-shrink-0" />
                  <span className="text-red-300 text-xs">{resetError}</span>
                </div>
              )}

              <form onSubmit={handleForgotPassword} className="space-y-4">
                <div>
                  <label className="flex items-center gap-2 text-xs font-medium text-slate-400 mb-1.5">
                    <Mail className="w-3.5 h-3.5" /> EMAIL
                  </label>
                  <input
                    type="email"
                    value={resetEmail}
                    onChange={e => setResetEmail(e.target.value)}
                    placeholder="seu@email.com"
                    required
                    className="w-full px-4 py-3 rounded-xl bg-slate-800/80 border border-white/[0.08] text-slate-200 text-sm placeholder:text-slate-600 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/25 transition-colors"
                  />
                </div>

                <button
                  type="submit"
                  disabled={resetLoading || !resetEmail}
                  className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
                >
                  {resetLoading ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Enviando...</>
                  ) : (
                    <>Enviar link de redefinição</>
                  )}
                </button>
              </form>

              <div className="mt-4 text-center">
                <button
                  type="button"
                  onClick={() => setPageState('login')}
                  className="inline-flex items-center gap-2 text-xs text-slate-500 hover:text-violet-400 transition-colors"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  Voltar ao login
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ─── Render: Login do projeto ───
  return (
    <div className="min-h-screen flex bg-[#06060e] overflow-hidden relative">
      {/* ── Particle network background ── */}
      <div className="absolute inset-0 z-0">
        <ParticleCanvas />
      </div>

      {/* ── Gradient overlays ── */}
      <div className="absolute inset-0 z-[1] bg-gradient-to-br from-violet-950/30 via-transparent to-cyan-950/20 pointer-events-none" />
      <div className="absolute bottom-0 left-0 right-0 h-1/3 z-[1] bg-gradient-to-t from-[#06060e] to-transparent pointer-events-none" />

      {/* ── Animated glow orbs ── */}
      <div className="absolute top-[15%] left-[20%] w-[500px] h-[500px] rounded-full z-[1] pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(112,56,224,0.08) 0%, transparent 70%)',
          animation: 'breathe 8s ease-in-out infinite',
        }}
      />
      <div className="absolute bottom-[10%] right-[15%] w-[400px] h-[400px] rounded-full z-[1] pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(0,184,204,0.06) 0%, transparent 70%)',
          animation: 'breathe 10s ease-in-out infinite 3s',
        }}
      />

      {/* ═══ LEFT PANEL — Contexto do Projeto ═══ */}
      <div className="hidden lg:flex lg:w-[45%] relative z-10 flex-col justify-between p-12 xl:p-16">

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
                <p className="text-slate-500 text-xs tracking-[0.2em] uppercase">Acesso ao Projeto</p>
              </div>
            </div>
          </div>
        </div>

        {/* Nome do projeto */}
        <div className="max-w-xl">
          <p className={`text-violet-400 text-sm font-medium tracking-wider uppercase mb-3 transition-all duration-1000 delay-100 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
            Projeto
          </p>
          <h1
            className={`font-display text-[3rem] leading-[1.1] font-bold text-white tracking-tight transition-all duration-1000 delay-200 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}
          >
            {projectName}
          </h1>
          <p className={`mt-4 text-slate-400 text-lg leading-relaxed transition-all duration-1000 delay-400 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
            Acesse com suas credenciais para visualizar o painel do projeto, pipeline e artefatos.
          </p>

          {/* Status badge */}
          <div className={`mt-6 inline-flex items-center gap-2 bg-white/[0.04] border border-white/[0.08] rounded-full px-4 py-2 transition-all duration-1000 delay-500 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-slate-300 text-xs font-medium capitalize">{projectStatus || 'Ativo'}</span>
          </div>
        </div>

        {/* Footer */}
        <div className={`flex items-center gap-4 transition-all duration-1000 delay-700 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
          <p className="text-slate-600 text-xs">&copy; 2026 GCA</p>
          <div className="h-px flex-1 bg-gradient-to-r from-white/5 to-transparent" />
          <p className="text-slate-600 text-xs font-mono">v0.8.0</p>
        </div>
      </div>

      {/* ═══ RIGHT PANEL — Login Form ═══ */}
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
          {/* Mobile — nome do projeto */}
          <div className="lg:hidden mb-6">
            <div className="flex items-center gap-3 mb-3">
              <img src="/images/gca-icon-40.png" alt="GCA" className="w-10 h-10" />
              <span className="text-white font-display text-xl font-bold">GCA</span>
            </div>
            <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl px-4 py-3">
              <p className="text-violet-300 text-sm font-semibold">{projectName}</p>
            </div>
          </div>

          {/* Heading */}
          <div className="mb-8">
            <h2 className="font-display text-2xl font-bold text-white">Acesso ao Projeto</h2>
            <p className="mt-2 text-slate-400 text-sm">
              Entre com suas credenciais de membro.
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

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-5">
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
                    Entrar no Projeto
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
                  </>
                )}
              </span>
            </button>
          </form>

          {/* Esqueci minha senha */}
          <div className="mt-4 text-center">
            <button
              type="button"
              onClick={() => { setPageState('forgot-password'); setResetEmail(email); setResetError(null) }}
              className="text-xs text-slate-500 hover:text-violet-400 transition-colors duration-300"
            >
              Esqueci minha senha
            </button>
          </div>

          {/* Link para login principal */}
          <div className="mt-4 pt-4 border-t border-white/[0.06] text-center">
            <Link
              to="/login"
              className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-violet-400 transition-colors duration-300"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Login principal do GCA
            </Link>
          </div>
        </div>

        {/* Security badge */}
        <div className={`mt-6 flex items-center gap-2 text-slate-600 text-xs transition-all duration-1000 delay-500 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
          <Lock className="w-3 h-3" />
          <span>Criptografia end-to-end ativa</span>
          <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
        </div>
      </div>

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
