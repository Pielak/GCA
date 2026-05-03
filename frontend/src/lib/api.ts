import axios, { AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios'
import { getErrorMessage, getErrorStatus, type ApiError } from '@/lib/errors'

// Detect API URL based on how the frontend is being accessed
export function getApiBaseUrl(): string {
  // If accessed via production domain, use the API subdomain
  if (typeof window !== 'undefined' && window.location.hostname === 'gca.code-auditor.com.br') {
    return 'https://api.code-auditor.com.br/api/v1'
  }

  // Default: local development
  return 'http://localhost:8000/api/v1'
}

// Create axios instance
// IMPORTANTE: não setar Content-Type default aqui. Axios infere sozinho:
//   - objeto comum  → 'application/json'
//   - FormData       → 'multipart/form-data; boundary=…' (com boundary correto)
//   - Blob/string    → conforme o tipo
// Se fixarmos 'application/json' aqui, FormData vira JSON.stringify(formDataToJSON(data))
// e uploads de arquivo param de funcionar.
const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 30000,  // 30 segundos máximo por requisição
})

// Request interceptor: Add JWT token to all requests
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: Handle errors
api.interceptors.response.use(
  (response) => {
    // DT-066 — sliding session: se o backend emitiu novo token no header
    // (porque o atual estava perto de expirar), substitui silenciosamente.
    // Mantém user ativo na UI durante ingestões longas sem ver /login.
    const renewed = response.headers?.['x-access-token-renewed']
    if (typeof renewed === 'string' && renewed.length > 0) {
      try {
        localStorage.setItem('token', renewed)
        const raw = localStorage.getItem('auth-storage')
        if (raw) {
          const parsed = JSON.parse(raw)
          if (parsed?.state) {
            parsed.state.token = renewed
            localStorage.setItem('auth-storage', JSON.stringify(parsed))
          }
        }
      } catch {
        // best-effort — não quebra a resposta se o parse falhar
      }
    }
    return response
  },
  (error: AxiosError) => {
    // Handle 401 Unauthorized - redirect to login.
    // Não redirecionar se já estiver em qualquer tela de login (/login,
    // /p/<slug>, /reset-password) — caso contrário o redirect blinda
    // o estado de erro do form e o usuário fica sem feedback.
    if (getErrorStatus(error) === 401) {
      const path = window.location.pathname
      const isAuthPage =
        path === '/login' ||
        path.startsWith('/p/') ||
        path.startsWith('/reset-password') ||
        path.startsWith('/accept-invitation')
      if (!isAuthPage) {
        localStorage.removeItem('token')
        window.location.href = '/login'
      }
    }

    // Extract error message from response. FastAPI pode retornar `detail` como:
    //   - string  (HTTPException comum)
    //   - array de {msg, loc, type, …}  (validation do Pydantic)
    // Sem este normalize, ${message} em alerts vira "[object Object]".
    const data = error.response?.data as { detail?: unknown; message?: unknown } | undefined
    const detail = data?.detail
    let errorMessage: string
    if (typeof detail === 'string') {
      errorMessage = detail
    } else if (Array.isArray(detail)) {
      errorMessage = detail
        .map((d: unknown) => {
          if (typeof d === 'string') return d
          const item = d as { loc?: unknown; msg?: unknown }
          const loc = Array.isArray(item?.loc) ? item.loc.join('.') : ''
          return loc ? `${loc}: ${item?.msg ?? JSON.stringify(d)}` : (item?.msg ?? JSON.stringify(d)) as string
        })
        .join('; ')
    } else {
      errorMessage =
        (typeof data?.message === 'string' ? data.message : undefined) ||
        getErrorMessage(error)
    }

    return Promise.reject({
      status: getErrorStatus(error),
      message: errorMessage,
      data: error.response?.data,
    })
  }
)

// Helper methods
// MVP 14 Fase 14.9: T default permanece `any` aqui — migrá-lo para
// `unknown` vira refactor cross-file (stop-rule > 2d). Inner-handler
// acima usa tipos estreitos (data/detail/message).
export const apiClient = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  get: <T = any>(url: string, config?: AxiosRequestConfig) => api.get<T>(url, config),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  post: <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig) => api.post<T>(url, data, config),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  put: <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig) => api.put<T>(url, data, config),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  patch: <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig) => api.patch<T>(url, data, config),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete: <T = any>(url: string, config?: AxiosRequestConfig) => api.delete<T>(url, config),
}

export default api
