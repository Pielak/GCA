import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
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
    const detail = (error.response?.data as any)?.detail
    let errorMessage: string
    if (typeof detail === 'string') {
      errorMessage = detail
    } else if (Array.isArray(detail)) {
      errorMessage = detail
        .map((d: any) => {
          if (typeof d === 'string') return d
          const loc = Array.isArray(d?.loc) ? d.loc.join('.') : ''
          return loc ? `${loc}: ${d?.msg ?? JSON.stringify(d)}` : (d?.msg ?? JSON.stringify(d))
        })
        .join('; ')
    } else {
      errorMessage =
        (error.response?.data as any)?.message ||
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
export const apiClient = {
  get: <T = any>(url: string, config?: any) => api.get<T>(url, config),
  post: <T = any>(url: string, data?: any, config?: any) => api.post<T>(url, data, config),
  put: <T = any>(url: string, data?: any, config?: any) => api.put<T>(url, data, config),
  patch: <T = any>(url: string, data?: any, config?: any) => api.patch<T>(url, data, config),
  delete: <T = any>(url: string, config?: any) => api.delete<T>(url, config),
}

export default api
