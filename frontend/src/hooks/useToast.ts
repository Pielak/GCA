import { useToastStore, type ToastType } from '@/stores/toastStore'

export const useToast = () => {
  const { addToast, removeToast, clearAll } = useToastStore()

  return {
    success: (message: string, duration?: number) =>
      addToast(message, 'success', duration),
    error: (message: string, duration?: number) =>
      addToast(message, 'error', duration),
    warning: (message: string, duration?: number) =>
      addToast(message, 'warning', duration),
    info: (message: string, duration?: number) =>
      addToast(message, 'info', duration),
    show: (message: string, type: ToastType, duration?: number) =>
      addToast(message, type, duration),
    remove: removeToast,
    clearAll,
  }
}
