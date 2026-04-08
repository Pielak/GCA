type BadgeVariant = 'success' | 'error' | 'warning' | 'info' | 'pending' | 'inactive' | 'active'

interface BadgeProps {
  variant?: BadgeVariant
  children: React.ReactNode
}

const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-green-900 text-green-300 border border-green-700',
  error: 'bg-red-900 text-red-300 border border-red-700',
  warning: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
  info: 'bg-blue-900 text-blue-300 border border-blue-700',
  pending: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
  inactive: 'bg-gray-700 text-gray-300 border border-gray-600',
  active: 'bg-green-900 text-green-300 border border-green-700',
}

export const Badge: React.FC<BadgeProps> = ({ variant = 'info', children }) => {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${variantStyles[variant]}`}>
      {children}
    </span>
  )
}
