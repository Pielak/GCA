import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { GitMerge, Save, Loader2, CheckCircle2, AlertCircle, Trash2 } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'

// MVP 20 Fase 20.1d — painel de config do Issue Tracker Bridge.
//
// Suporta Jira e Trello em V1 (config por projeto, decisão binária #1).
// Credenciais não voltam em plaintext do backend — o flag `has_credentials`
// indica quais já estão no vault. GP preenche novo valor e envia; vault
// encrypta via pgcrypto.

type Provider = 'jira' | 'trello'

interface ProviderSettings {
  base_url: string
  default_project_key: string
  status_mapping: Record<string, string>
  extra: Record<string, unknown>
}

interface SafeConfig {
  enabled: boolean
  active_provider: Provider | null
  providers: Partial<Record<Provider, ProviderSettings>>
  has_credentials: Record<Provider, Record<string, boolean>>
  registered_providers: string[]
}

interface Props {
  projectId: string
}

const CRED_LABELS: Record<Provider, Record<string, string>> = {
  jira: {
    email: 'Email Atlassian',
    api_token: 'API Token',
    webhook_secret: 'Webhook Secret',
  },
  trello: {
    api_key: 'API Key',
    api_token: 'User Token',
    webhook_secret: 'Webhook Secret',
  },
}

export function IssueTrackerPanel({ projectId }: Props) {
  const qc = useQueryClient()
  const { success, error } = useToast()

  const { data: config, isLoading } = useQuery<SafeConfig>({
    queryKey: ['issue-tracker-config', projectId],
    queryFn: async () => {
      const res = await apiClient.get<SafeConfig>(
        `/projects/${projectId}/integrations/issue-tracker`,
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
        `/projects/${projectId}/integrations/issue-tracker`,
        body,
      )
      return res.data
    },
    onSuccess: () => {
      success('Configuração salva.')
      qc.invalidateQueries({ queryKey: ['issue-tracker-config', projectId] })
      setDraft(null)
    },
    onError: (e) => error(getErrorMessage(e)),
  })

  const saveCredential = useMutation({
    mutationFn: async (v: { provider: Provider; key: string; value: string }) => {
      await apiClient.put(
        `/projects/${projectId}/integrations/issue-tracker/credentials/${v.provider}/${v.key}`,
        { value: v.value },
      )
    },
    onSuccess: () => {
      success('Credencial armazenada no vault.')
      qc.invalidateQueries({ queryKey: ['issue-tracker-config', projectId] })
    },
    onError: (e) => error(getErrorMessage(e)),
  })

  const deleteCredential = useMutation({
    mutationFn: async (v: { provider: Provider; key: string }) => {
      await apiClient.delete(
        `/projects/${projectId}/integrations/issue-tracker/credentials/${v.provider}/${v.key}`,
      )
    },
    onSuccess: () => {
      success('Credencial removida.')
      qc.invalidateQueries({ queryKey: ['issue-tracker-config', projectId] })
    },
    onError: (e) => error(getErrorMessage(e)),
  })

  if (isLoading || !current) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm p-6">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando config…
      </div>
    )
  }

  const setProviderField = (
    prov: Provider,
    field: 'base_url' | 'default_project_key',
    val: string,
  ) => {
    const next: SafeConfig = {
      ...current,
      providers: {
        ...current.providers,
        [prov]: {
          base_url: '',
          default_project_key: '',
          status_mapping: {},
          extra: {},
          ...(current.providers[prov] ?? {}),
          [field]: val,
        },
      },
    }
    setDraft(next)
  }

  return (
    <div className="space-y-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-1">
        <div className="flex items-center gap-2">
          <GitMerge className="w-4 h-4 text-violet-400" />
          <h3 className="text-slate-200 text-sm font-semibold">Issue Tracker</h3>
        </div>
        <p className="text-slate-500 text-xs">
          Conecte o tracker que seu time já usa. Cada módulo aprovado pelo GP
          vira automaticamente issue no tracker configurado — status é
          sincronizado nas duas direções via webhook.
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
          Integração habilitada
        </label>

        <div>
          <label className="block text-xs text-slate-400 mb-1.5">
            Provider ativo
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
                {p === 'jira' ? 'Jira (Atlassian Cloud / on-prem)' : 'Trello'}
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
      {(['jira', 'trello'] as Provider[]).map((prov) => {
        const p: ProviderSettings = current.providers[prov] ?? {
          base_url: '', default_project_key: '',
          status_mapping: {}, extra: {},
        }
        const hasCreds = current.has_credentials[prov] ?? {}
        const credKeys = Object.keys(CRED_LABELS[prov])
        const isActive = current.active_provider === prov
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
                {prov === 'jira' ? 'Jira' : 'Trello'}
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
                  {prov === 'jira' ? 'Base URL' : 'Base URL (API)'}
                </label>
                <input
                  type="text"
                  value={p.base_url}
                  placeholder={
                    prov === 'jira'
                      ? 'https://empresa.atlassian.net'
                      : 'https://api.trello.com'
                  }
                  onChange={(e) => setProviderField(prov, 'base_url', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm text-slate-200"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  {prov === 'jira' ? 'Project Key' : 'Board ID'}
                </label>
                <input
                  type="text"
                  value={p.default_project_key}
                  placeholder={prov === 'jira' ? 'ex: PROJ' : 'ex: board-id'}
                  onChange={(e) => setProviderField(prov, 'default_project_key', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm text-slate-200"
                />
              </div>
            </div>

            {/* Credentials */}
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <p className="text-[11px] text-slate-500 uppercase tracking-wide">
                Credenciais (gravadas encrypted no vault)
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
        <strong className="text-slate-400">Como funciona:</strong> quando um módulo
        é aprovado pelo GP, o GCA cria automaticamente uma issue no provider ativo
        com título <code>RF-XXX — nome do módulo</code>. Mudanças de status no
        tracker voltam pelo webhook{' '}
        <code>POST /api/v1/integrations/webhooks/issue-tracker/{'{'}provider{'}'}/{'{'}project_id{'}'}</code>.
        Credenciais nunca saem do vault em plaintext.
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
      <div className="flex items-center gap-1.5 min-w-[9rem]">
        {hasValue
          ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
          : <AlertCircle className="w-3.5 h-3.5 text-amber-500" />}
        <span className="text-xs text-slate-300">{label}</span>
      </div>
      <input
        type="password"
        placeholder={hasValue ? '•••••••• (substituir)' : 'digite o valor'}
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
          title="Remover credencial"
          className="p-1.5 text-slate-500 hover:text-rose-400"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  )
}
