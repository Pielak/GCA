import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, Save, Loader2, CheckCircle2, AlertCircle, Trash2 } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'

// Fix pós-MVP 22 — painel de config do Notifier (Slack + Teams).
//
// Credenciais não voltam em plaintext — o flag `has_credentials`
// indica se existe valor no vault. GP preenche novo valor + salvar.

type Provider = 'slack' | 'teams'

interface ProviderSettings {
  channel: string
  opted_in_events: string[] | null
  link_only_mode: boolean
  gca_base_url: string
  extra: Record<string, unknown>
}

interface SafeConfig {
  enabled: boolean
  active_provider: Provider | null
  providers: Partial<Record<Provider, ProviderSettings>>
  has_credentials: Record<Provider, Record<string, boolean>>
  registered_providers: string[]
  canonical_events: string[]
}

interface Props {
  projectId: string
}

const CRED_LABELS: Record<Provider, Record<string, string>> = {
  slack: { webhook_url: 'Incoming Webhook URL' },
  teams: { webhook_url: 'Incoming Webhook URL (Power Automate ou Connector)' },
}

const EVENT_LABELS: Record<string, string> = {
  MODULE_APPROVED: 'Módulo aprovado',
  OCG_CONSOLIDATED: 'OCG consolidado',
  CODEGEN_COMPLETED: 'CodeGen concluído',
  ERS_REGENERATED: 'ERS regenerado',
  SECURITY_FINDING_HIGH: 'Finding crítico',
  BACKUP_FAILED: 'Backup falhou',
}

export function NotifierPanel({ projectId }: Props) {
  const qc = useQueryClient()
  const { success, error } = useToast()

  const { data: config, isLoading } = useQuery<SafeConfig>({
    queryKey: ['notifier-config', projectId],
    queryFn: async () => {
      const res = await apiClient.get<SafeConfig>(
        `/projects/${projectId}/integrations/notifier`,
      )
      return res.data
    },
  })

  const [draft, setDraft] = useState<SafeConfig | null>(null)
  const current = draft ?? config ?? null

  const saveSettings = useMutation({
    mutationFn: async (payload: SafeConfig) => {
      const body = {
        enabled: payload.enabled,
        active_provider: payload.active_provider,
        providers: payload.providers,
      }
      const res = await apiClient.put(
        `/projects/${projectId}/integrations/notifier`,
        body,
      )
      return res.data
    },
    onSuccess: () => {
      success('Configuração de notificação salva.')
      qc.invalidateQueries({ queryKey: ['notifier-config', projectId] })
      setDraft(null)
    },
    onError: (e) => error(getErrorMessage(e)),
  })

  const saveCredential = useMutation({
    mutationFn: async (v: { provider: Provider; key: string; value: string }) => {
      await apiClient.put(
        `/projects/${projectId}/integrations/notifier/credentials/${v.provider}/${v.key}`,
        { value: v.value },
      )
    },
    onSuccess: () => {
      success('Webhook armazenado no vault.')
      qc.invalidateQueries({ queryKey: ['notifier-config', projectId] })
    },
    onError: (e) => error(getErrorMessage(e)),
  })

  const deleteCredential = useMutation({
    mutationFn: async (v: { provider: Provider; key: string }) => {
      await apiClient.delete(
        `/projects/${projectId}/integrations/notifier/credentials/${v.provider}/${v.key}`,
      )
    },
    onSuccess: () => {
      success('Webhook removido.')
      qc.invalidateQueries({ queryKey: ['notifier-config', projectId] })
    },
    onError: (e) => error(getErrorMessage(e)),
  })

  if (isLoading || !current) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm p-6">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando config de notificação…
      </div>
    )
  }

  const setProviderField = <K extends keyof ProviderSettings>(
    prov: Provider,
    field: K,
    val: ProviderSettings[K],
  ) => {
    const next: SafeConfig = {
      ...current,
      providers: {
        ...current.providers,
        [prov]: {
          channel: '',
          opted_in_events: null,
          link_only_mode: false,
          gca_base_url: '',
          extra: {},
          ...(current.providers[prov] ?? {}),
          [field]: val,
        },
      },
    }
    setDraft(next)
  }

  const toggleEvent = (prov: Provider, ev: string) => {
    const p = current.providers[prov] ?? {
      channel: '', opted_in_events: null, link_only_mode: false,
      gca_base_url: '', extra: {},
    }
    // null = opted in todos (default). Primeira edição captura a lista atual
    // explícita (todos) e então remove/add.
    const currentList = p.opted_in_events ?? [...current.canonical_events]
    const isIn = currentList.includes(ev)
    const next = isIn
      ? currentList.filter((e) => e !== ev)
      : [...currentList, ev]
    setProviderField(prov, 'opted_in_events', next)
  }

  return (
    <div className="space-y-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-1">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-violet-400" />
          <h3 className="text-slate-200 text-sm font-semibold">Notificações (Slack / Teams)</h3>
        </div>
        <p className="text-slate-500 text-xs">
          Eventos canônicos do pipeline (módulo aprovado, ERS regenerado,
          finding crítico, etc) disparam mensagem no canal configurado.
          Uni-direcional — mensagens vão, reações não voltam. ChatOps fica
          para MVP futuro.
        </p>
      </div>

      {/* Enabled + active provider */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
        <label className="flex items-center gap-3 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={current.enabled}
            onChange={(e) => setDraft({ ...current, enabled: e.target.checked })}
            className="w-4 h-4"
          />
          Notificações habilitadas
        </label>

        <div>
          <label className="block text-xs text-slate-400 mb-1.5">
            Canal ativo
          </label>
          <select
            value={current.active_provider ?? ''}
            onChange={(e) => setDraft({
              ...current,
              active_provider: (e.target.value || null) as Provider | null,
            })}
            className="w-full max-w-xs bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm text-slate-200"
          >
            <option value="">— nenhum —</option>
            {current.registered_providers.map((p) => (
              <option key={p} value={p}>
                {p === 'slack' ? 'Slack' : 'Microsoft Teams'}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          onClick={() => saveSettings.mutate(current)}
          disabled={saveSettings.isPending}
          className="flex items-center gap-2 px-3 py-1.5 text-xs rounded bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-50"
        >
          {saveSettings.isPending
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : <Save className="w-3.5 h-3.5" />}
          Salvar configuração
        </button>
      </div>

      {/* Per-provider config */}
      {(['slack', 'teams'] as Provider[]).map((prov) => {
        const p: ProviderSettings = current.providers[prov] ?? {
          channel: '', opted_in_events: null, link_only_mode: false,
          gca_base_url: '', extra: {},
        }
        const hasCreds = current.has_credentials[prov] ?? {}
        const credKeys = Object.keys(CRED_LABELS[prov])
        const isActive = current.active_provider === prov
        const events = p.opted_in_events ?? current.canonical_events
        return (
          <div
            key={prov}
            className={`border rounded-xl p-5 space-y-3 ${
              isActive
                ? 'bg-slate-900 border-violet-500/40'
                : 'bg-slate-900/60 border-slate-800'
            }`}
          >
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-slate-200">
                {prov === 'slack' ? 'Slack' : 'Microsoft Teams'}
                {isActive && (
                  <span className="ml-2 text-[10px] text-violet-400 uppercase tracking-wide">
                    ativo
                  </span>
                )}
              </h4>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Canal (referência visual)
                </label>
                <input
                  type="text"
                  value={p.channel}
                  placeholder={prov === 'slack' ? '#gca-events' : 'Notificações GCA'}
                  onChange={(e) => setProviderField(prov, 'channel', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm text-slate-200"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  URL pública do GCA (pra link profundo)
                </label>
                <input
                  type="text"
                  value={p.gca_base_url}
                  placeholder="https://gca.suaempresa.com"
                  onChange={(e) => setProviderField(prov, 'gca_base_url', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm text-slate-200"
                />
              </div>
            </div>

            <label className="flex items-start gap-3 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={p.link_only_mode}
                onChange={(e) => setProviderField(prov, 'link_only_mode', e.target.checked)}
                className="w-4 h-4 mt-0.5"
              />
              <div>
                <div>Modo link-only (regulado)</div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  Mensagem vai só com link pro GCA, sem payload sensível.
                  Obrigatório em cliente BACEN/ANS/órgão público.
                </div>
              </div>
            </label>

            {/* Eventos opt-in */}
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <p className="text-[11px] text-slate-500 uppercase tracking-wide">
                Eventos que disparam notificação
              </p>
              <div className="grid grid-cols-2 gap-2">
                {current.canonical_events.map((ev) => {
                  const isOptedIn = events.includes(ev)
                  return (
                    <label key={ev} className="flex items-center gap-2 text-xs text-slate-300">
                      <input
                        type="checkbox"
                        checked={isOptedIn}
                        onChange={() => toggleEvent(prov, ev)}
                        className="w-3.5 h-3.5"
                      />
                      <code className="text-[10px] text-slate-500">{ev}</code>
                      <span className="text-slate-400">
                        {EVENT_LABELS[ev] || ev}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>

            {/* Credentials */}
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <p className="text-[11px] text-slate-500 uppercase tracking-wide">
                Webhook (gravado encrypted no vault)
              </p>
              {credKeys.map((key) => (
                <CredentialRow
                  key={key}
                  provider={prov}
                  credKey={key}
                  label={CRED_LABELS[prov][key]}
                  hasValue={!!hasCreds[key]}
                  onSave={(value) => saveCredential.mutate({ provider: prov, key, value })}
                  onDelete={() => deleteCredential.mutate({ provider: prov, key })}
                  busy={saveCredential.isPending || deleteCredential.isPending}
                />
              ))}
            </div>
          </div>
        )
      })}

      <div className="bg-slate-900/50 border border-slate-800/60 rounded-xl p-4 text-[11px] text-slate-500 leading-relaxed">
        <strong className="text-slate-400">Como obter o webhook:</strong>{' '}
        <span className="text-slate-400">Slack:</span> api.slack.com → "Your Apps" → novo app → Incoming Webhooks → escolher canal.{' '}
        <span className="text-slate-400">Teams:</span> Power Automate → novo fluxo "Post to a channel when a webhook request is received" → copiar URL do trigger.
      </div>
    </div>
  )
}

function CredentialRow({
  provider: _provider, credKey: _credKey, label, hasValue, onSave, onDelete, busy,
}: {
  provider: Provider
  credKey: string
  label: string
  hasValue: boolean
  onSave: (value: string) => void
  onDelete: () => void
  busy: boolean
}) {
  const [value, setValue] = useState('')
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1.5 min-w-[14rem]">
        {hasValue
          ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
          : <AlertCircle className="w-3.5 h-3.5 text-amber-500" />}
        <span className="text-xs text-slate-300">{label}</span>
      </div>
      <input
        type="password"
        placeholder={hasValue ? '•••••••• (substituir)' : 'cole o webhook URL'}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="flex-1 bg-slate-950 border border-slate-800 rounded px-2 py-1.5 text-xs text-slate-200"
      />
      <button
        type="button"
        onClick={() => {
          if (!value) return
          onSave(value)
          setValue('')
        }}
        disabled={!value || busy}
        className="px-2 py-1.5 text-[11px] rounded bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-40"
      >
        Salvar
      </button>
      {hasValue && (
        <button
          type="button"
          onClick={onDelete}
          disabled={busy}
          title="Remover webhook"
          className="p-1.5 text-slate-500 hover:text-rose-400"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  )
}
