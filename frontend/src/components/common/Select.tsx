interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  options: Array<{ value: string | number; label: string }>
}

export const Select: React.FC<SelectProps> = ({
  label,
  error,
  options,
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
      <select
        {...props}
        className={`w-full px-4 py-2 bg-gray-700 border rounded-lg text-white focus:outline-none focus:border-blue-500 transition ${
          error ? 'border-red-500' : 'border-gray-600'
        } ${className}`}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && <p className="text-red-400 text-sm mt-1">{error}</p>}
    </div>
  )
}
