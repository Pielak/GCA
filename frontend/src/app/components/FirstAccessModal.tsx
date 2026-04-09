import { useState } from 'react'
import { Shield, Eye, EyeOff, CheckCircle2, AlertCircle, Loader2, AlertTriangle } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

interface FirstAccessModalProps {
  isOpen: boolean
  temporaryPassword: string
  onPasswordChanged: () => void
}

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

export function FirstAccessModal({ isOpen, temporaryPassword, onPasswordChanged }: FirstAccessModalProps) {
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { setUser, user } = useAuthStore()

  if (!isOpen) return null

  const allRulesPass = PASSWORD_RULES.every(r => r.test(newPassword))
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword
  const canSubmit = allRulesPass && passwordsMatch && !loading

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      await apiClient.post('/auth/change-first-password', {
        temporary_password: temporaryPassword,
        new_password: newPassword,
      })

      // Update user state to reflect password changed
      if (user) {
        setUser({ ...user, first_access_completed: true })
      }

      onPasswordChanged()
    } catch (err: any) {
      setError(err?.message || 'Erro ao alterar senha')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-dark-100 border border-slate-700 rounded-2xl p-8 w-[90%] max-w-[500px] shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-600/30 flex items-center justify-center">
            <Shield className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Definir Senha Segura</h2>
            <p className="text-slate-400 text-sm">Crie uma nova senha para continuar.</p>
          </div>
        </div>

        {/* Warning */}
        <div className="mt-4 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-amber-300 text-xs font-semibold">Importante</p>
            <p className="text-amber-200/80 text-xs mt-0.5">
              Esta ação e obrigatória. Sua senha temporária será invalidada após esta alteração.
            </p>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mt-4 bg-red-900/40 border border-red-800/50 rounded-lg p-3">
            <p className="text-red-300 text-sm">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          {/* New Password */}
          <div>
            <label className="block text-sm text-slate-300 font-medium mb-1.5">
              Nova Senha
            </label>
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
              <button
                type="button"
                onClick={() => setShowNew(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                tabIndex={-1}
              >
                {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>

            {/* Real-time validation indicators */}
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

          {/* Confirm Password */}
          <div>
            <label className="block text-sm text-slate-300 font-medium mb-1.5">
              Confirmar Senha
            </label>
            <div className="relative">
              <input
                type={showConfirm ? 'text' : 'password'}
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                className={`w-full bg-dark-200 border rounded-lg px-4 pr-10 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 transition-colors ${
                  confirmPassword.length > 0 && !passwordsMatch
                    ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                    : 'border-slate-700 focus:border-violet-600 focus:ring-violet-600/30'
                }`}
                placeholder="Repita a nova senha"
                disabled={loading}
              />
              <button
                type="button"
                onClick={() => setShowConfirm(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
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
            disabled={!canSubmit}
            className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
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
          </button>
        </form>

        <p className="mt-4 text-xs text-slate-500 text-center">
          Seus dados estao protegidos com criptografia de ponta a ponta.
        </p>
      </div>
    </div>
  )
}

export default FirstAccessModal
