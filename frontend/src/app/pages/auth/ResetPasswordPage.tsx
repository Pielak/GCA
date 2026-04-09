import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { Code2, Mail, Lock, Eye, EyeOff, CheckCircle2, AlertCircle, Loader2, ArrowLeft } from 'lucide-react'
import { apiClient } from '@/lib/api'

type Step = 'request' | 'verify' | 'confirm'

interface PasswordRule {
  id: string
  test: (pw: string) => boolean
  label: string
}

const PASSWORD_RULES: PasswordRule[] = [
  { id: 'length', test: pw => pw.length >= 10, label: 'Minimo 10 caracteres' },
  { id: 'upper', test: pw => /[A-Z]/.test(pw), label: 'Pelo menos 1 letra maiuscula' },
  { id: 'digit', test: pw => /[0-9]/.test(pw), label: 'Pelo menos 1 numero' },
  { id: 'special', test: pw => /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(pw), label: 'Pelo menos 1 caractere especial' },
]

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [step, setStep] = useState<Step>(searchParams.get('token') ? 'verify' : 'request')
  const [email, setEmail] = useState('')
  const [token] = useState(searchParams.get('token') || '')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Auto-verify token on mount
  useEffect(() => {
    if (token && step === 'verify') {
      verifyToken()
    }
  }, [])

  const verifyToken = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiClient.post('/auth/verify-reset-token', { token })
      if (res.data.valid) {
        setStep('confirm')
      } else {
        setError('Token invalido ou expirado. Solicite um novo link.')
        setStep('request')
      }
    } catch (err: any) {
      setError(err?.message || 'Token invalido ou expirado')
      setStep('request')
    } finally {
      setLoading(false)
    }
  }

  const handleRequestReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await apiClient.post('/auth/reset-password', { email })
      setSuccess('Se o email existir no sistema, você receberá um link de recuperação.')
      setTimeout(() => setSuccess(null), 5000)
    } catch (err: any) {
      setError(err?.message || 'Erro ao solicitar reset')
    } finally {
      setLoading(false)
    }
  }

  const handleConfirmReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await apiClient.post('/auth/reset-password-confirm', {
        token,
        new_password: newPassword,
      })
      setSuccess('Senha alterada com sucesso! Redirecionando...')
      setTimeout(() => navigate('/login'), 2000)
    } catch (err: any) {
      setError(err?.message || 'Erro ao alterar senha')
    } finally {
      setLoading(false)
    }
  }

  const allRulesPass = PASSWORD_RULES.every(r => r.test(newPassword))
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword

  return (
    <div className="min-h-screen bg-dark flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-6">
            <img src="/images/gca-icon-40.png" alt="GCA" className="w-10 h-10" />
            <span className="text-white text-lg font-semibold">GCA</span>
          </div>
          <h1 className="text-2xl font-bold text-white">
            {step === 'request' && 'Recuperar Senha'}
            {step === 'verify' && 'Verificando Token...'}
            {step === 'confirm' && 'Definir Nova Senha'}
          </h1>
          <p className="mt-2 text-slate-400 text-sm">
            {step === 'request' && 'Informe seu email para receber o link de recuperação'}
            {step === 'verify' && 'Aguarde enquanto validamos seu token'}
            {step === 'confirm' && 'Crie uma senha segura para sua conta'}
          </p>
        </div>

        {/* Card */}
        <div className="bg-dark-100 border border-slate-700 rounded-2xl p-6 shadow-xl">
          {/* Error */}
          {error && (
            <div className="mb-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}

          {/* Success */}
          {success && (
            <div className="mb-4 bg-emerald-900/40 border border-emerald-800/50 rounded-lg p-3 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <p className="text-emerald-300 text-sm">{success}</p>
            </div>
          )}

          {/* Step: Request */}
          {step === 'request' && (
            <form onSubmit={handleRequestReset} className="space-y-5">
              <div>
                <label className="block text-sm text-slate-300 font-medium mb-1.5">Email cadastrado</label>
                <div className="relative">
                  <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    className="w-full bg-dark-200 border border-slate-700 rounded-lg pl-9 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                    placeholder="seu@email.com"
                    required
                    disabled={loading}
                    autoFocus
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !email}
                className="w-full bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 animate-spin" />Enviando...</>
                ) : (
                  <><Mail className="w-4 h-4" />Enviar Link de Recuperacao</>
                )}
              </button>
            </form>
          )}

          {/* Step: Verify (auto) */}
          {step === 'verify' && (
            <div className="flex flex-col items-center py-8">
              <Loader2 className="w-8 h-8 text-violet-400 animate-spin mb-4" />
              <p className="text-slate-300 text-sm">Verificando token...</p>
            </div>
          )}

          {/* Step: Confirm */}
          {step === 'confirm' && (
            <form onSubmit={handleConfirmReset} className="space-y-5">
              <div>
                <label className="block text-sm text-slate-300 font-medium mb-1.5">Nova Senha</label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    type={showNew ? 'text' : 'password'}
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    className="w-full bg-dark-200 border border-slate-700 rounded-lg pl-9 pr-10 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                    placeholder="Minimo 10 caracteres"
                    disabled={loading}
                    autoFocus
                  />
                  <button type="button" onClick={() => setShowNew(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300" tabIndex={-1}>
                    {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                {newPassword.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {PASSWORD_RULES.map(rule => {
                      const passes = rule.test(newPassword)
                      return (
                        <div key={rule.id} className="flex items-center gap-2">
                          {passes ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <AlertCircle className="w-3.5 h-3.5 text-red-400" />}
                          <span className={`text-xs ${passes ? 'text-emerald-400' : 'text-red-400'}`}>{rule.label}</span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm text-slate-300 font-medium mb-1.5">Confirmar Senha</label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    type={showConfirm ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    className={`w-full bg-dark-200 border rounded-lg pl-9 pr-10 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 transition-colors ${
                      confirmPassword.length > 0 && !passwordsMatch
                        ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                        : 'border-slate-700 focus:border-violet-600 focus:ring-violet-600/30'
                    }`}
                    placeholder="Repita a nova senha"
                    disabled={loading}
                  />
                  <button type="button" onClick={() => setShowConfirm(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300" tabIndex={-1}>
                    {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                {confirmPassword.length > 0 && (
                  <div className="mt-2 flex items-center gap-2">
                    {passwordsMatch
                      ? <><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /><span className="text-xs text-emerald-400">Senhas conferem</span></>
                      : <><AlertCircle className="w-3.5 h-3.5 text-red-400" /><span className="text-xs text-red-400">Senhas não conferem</span></>
                    }
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={loading || !allRulesPass || !passwordsMatch}
                className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 animate-spin" />Alterando...</>
                ) : (
                  <><Lock className="w-4 h-4" />Alterar Senha</>
                )}
              </button>
            </form>
          )}

          {/* Back to login */}
          <div className="mt-4 text-center">
            <Link to="/login" className="text-sm text-violet-400 hover:text-violet-300 transition-colors inline-flex items-center gap-1">
              <ArrowLeft className="w-3 h-3" />
              Voltar ao login
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ResetPasswordPage
