import { useToastStore } from '@/stores/toastStore'
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react'

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useToastStore()

  const icons = {
    success: CheckCircle,
    error: AlertCircle,
    warning: AlertTriangle,
    info: Info,
  }

  const bgColors = {
    success: 'bg-green-900 border-green-700',
    error: 'bg-red-900 border-red-700',
    warning: 'bg-yellow-900 border-yellow-700',
    info: 'bg-blue-900 border-blue-700',
  }

  const textColors = {
    success: 'text-green-300',
    error: 'text-red-300',
    warning: 'text-yellow-300',
    info: 'text-blue-300',
  }

  const iconColors = {
    success: 'text-green-400',
    error: 'text-red-400',
    warning: 'text-yellow-400',
    info: 'text-blue-400',
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2 max-w-md pointer-events-none">
      {toasts.map((toast) => {
        const Icon = icons[toast.type]
        return (
          <div
            key={toast.id}
            className={`flex items-start gap-3 p-4 rounded-lg border ${bgColors[toast.type]} text-white pointer-events-auto animate-in fade-in slide-in-from-right-4`}
          >
            <Icon className={`w-5 h-5 flex-shrink-0 mt-0.5 ${iconColors[toast.type]}`} />
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${textColors[toast.type]} break-words`}>
                {toast.message}
              </p>
            </div>
            <button
              onClick={() => removeToast(toast.id)}
              className="flex-shrink-0 text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
