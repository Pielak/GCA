interface SkeletonLoaderProps {
  count?: number
  height?: string
  width?: string
  circle?: boolean
  className?: string
}

export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({
  count = 1,
  height = 'h-4',
  width = 'w-full',
  circle = false,
  className = '',
}) => {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, idx) => (
        <div
          key={idx}
          className={`bg-gray-700 animate-pulse ${width} ${circle ? 'rounded-full' : 'rounded'} ${height} ${className}`}
        />
      ))}
    </div>
  )
}
