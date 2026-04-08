import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Code2, Lock, Eye, EyeOff, CheckCircle2, AlertCircle, Loader2, Shield } from 'lucide-react'
import { apiClient } from '@/lib/api'

type Step = 'validate' | 'setPassword' | 'success'

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

export function AcceptInvitationPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''

  const [step, setStep] = useState<Step>('validate')
  const [tempPassword, setTempPassword] = useState('')
  const [showTemp, setShowTemp] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [userEmail, setUserEmail] = useState('')

  useEffect(() => {
    if (!token) {
      setError('Token de convite nao encontrado. Verifique o link no seu email.')
    }
  }, [token])

  const handleValidateTemp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await apiClient.post('/auth/validate-invitation-token', {
        token,
        temporary_password: tempPassword,
      })
      if (res.data.valid) {
        setUserEmail(res.data.email || '')
        setStep('setPassword')
      } else {
        setError(res.data.message || 'Senha temporaria invalida')
      }
    } catch (err: any) {
      setError(err?.message || 'Erro ao validar senha temporaria')
    } finally {
      setLoading(false)
    }
  }

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await apiClient.post('/auth/set-permanent-password-from-invitation', {
        token,
        temporary_password: tempPassword,
        new_password: newPassword,
      })
      setStep('success')
      setTimeout(() => navigate('/login'), 3000)
    } catch (err: any) {
      setError(err?.message || 'Erro ao definir senha')
    } finally {
      setLoading(false)
    }
  }

  const allRulesPass = PASSWORD_RULES.every(r => r.test(newPassword))
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword

  return (
    <div className="min-h-screen bg-dark flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <img src="/images/gca-icon-40.png" alt="GCA" className="w-10 h-10" />
          <span className="text-white text-lg font-semibold">GCA</span>
        </div>

        {/* Step: Validate Temp Password */}
        {step === 'validate' && (
          <div className="bg-dark-100 border border-slate-700 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-600/30 flex items-center justify-center">
                <Shield className="w-5 h-5 text-violet-400" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">Aceitar Convite</h1>
                <p className="text-slate-400 text-sm">Passo 1: Validar senha temporaria</p>
              </div>
            </div>

            <p className="text-slate-300 text-sm mb-4">
              Insira a senha temporaria que voce recebeu por email para confirmar sua identidade.
            </p>

            {error && (
              <div className="mb-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            )}

            <form onSubmit={handleValidateTemp} className="space-y-5">
              <div>
                <label className="block text-sm text-slate-300 font-medium mb-1.5">Senha Temporaria</label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    type={showTemp ? 'text' : 'password'}
                    value={tempPassword}
                    onChange={e => setTempPassword(e.target.value)}
                    className="w-full bg-dark-200 border border-slate-700 rounded-lg pl-9 pr-10 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
                    placeholder="Cole a senha do email"
                    required
                    disabled={loading || !token}
                    autoFocus
                  />
                  <button type="button" onClick={() => setShowTemp(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300" tabIndex={-1}>
                    {showTemp ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !tempPassword || !token}
                className="w-full bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Validando...</> : 'Validar Senha'}
              </button>
            </form>
          </div>
        )}

        {/* Step: Set Permanent Password */}
        {step === 'setPassword' && (
          <div className="bg-dark-100 border border-slate-700 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-emerald-600/20 border border-emerald-600/30 flex items-center justify-center">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">Definir Senha</h1>
                <p className="text-slate-400 text-sm">Passo 2: Criar senha permanente</p>
              </div>
            </div>

            {userEmail && (
              <p className="text-slate-300 text-sm mb-4">
                Bem-vindo, <span className="text-violet-400 font-medium">{userEmail}</span>. Defina sua senha permanente.
              </p>
            )}

            {error && (
              <div className="mb-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            )}

            <form onSubmit={handleSetPassword} className="space-y-5">
              <div>
                <label className="block text-sm text-slate-300 font-medium mb-1.5">Nova Senha</label>
                <div className="relative">
                  <input
                    type={showNew ? 'text' : 'password'}
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    className="w-full bg-dark-200 border border-slate-700 rounded-lg px-4 pr-10 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
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
                  <input
                    type={showConfirm ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    className={`w-full bg-dark-200 border rounded-lg px-4 pr-10 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 transition-colors ${
                      confirmPassword.length > 0 && !passwordsMatch ? 'border-red-500 focus:ring-red-500/30' : 'border-slate-700 focus:ring-violet-600/30'
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
                      : <><AlertCircle className="w-3.5 h-3.5 text-red-400" /><span className="text-xs text-red-400">Senhas nao conferem</span></>}
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={loading || !allRulesPass || !passwordsMatch}
                className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Salvando...</> : <><CheckCircle2 className="w-4 h-4" />Criar Conta</>}
              </button>
            </form>
          </div>
        )}

        {/* Step: Success */}
        {step === 'success' && (
          <div className="bg-dark-100 border border-emerald-700/30 rounded-2xl p-8 shadow-xl text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-white mb-2">Conta Criada!</h1>
            <p className="text-slate-400 mb-4">Sua senha foi definida. Redirecionando para o login...</p>
            <Loader2 className="w-5 h-5 text-violet-400 animate-spin mx-auto" />
          </div>
        )}
      </div>
    </div>
  )
}

export default AcceptInvitationPage
