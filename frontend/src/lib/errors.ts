/**
 * MVP 12 Fase 12.7 — Helper canônico para extrair mensagem de erro.
 *
 * Substitui o padrão ubíquo `catch (err: unknown)` + `err.response?.data?.detail`.
 * Compatível com AxiosError, Error nativo, strings e objetos arbitrários.
 * Mantém type safety: o caller recebe `unknown` do catch do TS 4.4+ e
 * delega a extração a esta função.
 */
import type { AxiosError } from 'axios'

interface ApiErrorPayload {
  detail?: string | { msg?: string } | Array<{ msg?: string }>
  message?: string
  error?: string
}

/**
 * Shape do erro rejeitado pelo interceptor do axios em `lib/api.ts`.
 * Uso típico: `catch (err) { const e = err as ApiError; if (e.status === 401) ... }`.
 */
export type ApiError = {
  status?: number
  message?: string
  data?: {
    detail?: string | { msg?: string; code?: string } | Array<{ msg?: string }>
    message?: string
    [key: string]: unknown
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function isAxiosError(err: unknown): err is AxiosError<ApiErrorPayload> {
  return isRecord(err) && (err as { isAxiosError?: boolean }).isAxiosError === true
}

/**
 * Extrai HTTP status code de um erro.
 * Cobre tanto AxiosError (err.response.status) quanto o shape
 * rejeitado pelo interceptor de `lib/api.ts` (err.status direto no topo).
 */
export function getErrorStatus(err: unknown): number | undefined {
  if (isAxiosError(err)) return err.response?.status
  if (isRecord(err) && typeof (err as { status?: unknown }).status === 'number') {
    return (err as { status: number }).status
  }
  return undefined
}

/**
 * Extrai mensagem legível de qualquer error vindo de try/catch ou onError.
 * - AxiosError: lê response.data.detail/message/error em ordem.
 * - Error: usa message.
 * - string: retorna como está.
 * - outros: serializa via String().
 */
export function getErrorMessage(err: unknown, fallback = 'Erro inesperado'): string {
  if (isAxiosError(err)) {
    const data = err.response?.data
    if (data) {
      if (typeof data.detail === 'string') return data.detail
      if (Array.isArray(data.detail) && data.detail[0]?.msg) return String(data.detail[0].msg)
      if (isRecord(data.detail) && typeof (data.detail as { msg?: unknown }).msg === 'string') {
        return (data.detail as { msg: string }).msg
      }
      if (typeof data.message === 'string') return data.message
      if (typeof data.error === 'string') return data.error
    }
    return err.message || fallback
  }
  if (err instanceof Error) return err.message || fallback
  if (typeof err === 'string') return err
  return fallback
}
