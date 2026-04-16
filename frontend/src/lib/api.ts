import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

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
const api = axios.create({
  baseURL: getApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
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
  (response) => response,
  (error: AxiosError) => {
    // Handle 401 Unauthorized - redirect to login.
    // Não redirecionar se já estiver em qualquer tela de login (/login,
    // /p/<slug>, /reset-password) — caso contrário o redirect blinda
    // o estado de erro do form e o usuário fica sem feedback.
    if (error.response?.status === 401) {
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

    // Extract error message from response
    const errorMessage =
      (error.response?.data as any)?.detail ||
      (error.response?.data as any)?.message ||
      error.message ||
      'Erro ao processar requisição'

    return Promise.reject({
      status: error.response?.status,
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
