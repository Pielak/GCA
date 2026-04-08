interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  helperText,
  className = '',
  ...props
}) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-gray-300 text-sm font-medium mb-2">
          {label}
        </label>
      )}
      <input
        {...props}
        className={`w-full px-4 py-2 bg-gray-700 border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition ${
          error ? 'border-red-500' : 'border-gray-600'
        } ${className}`}
      />
      {error && <p className="text-red-400 text-sm mt-1">{error}</p>}
      {helperText && !error && <p className="text-gray-400 text-sm mt-1">{helperText}</p>}
    </div>
  )
}
