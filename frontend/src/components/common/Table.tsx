import { ReactNode } from 'react'
import { ChevronUp, ChevronDown } from 'lucide-react'

export interface Column<T> {
  key: keyof T | string
  label: string
  render?: (value: any, row: T, index: number) => ReactNode
  width?: string
  sortable?: boolean
}

interface TableProps<T> {
  columns: Column<T>[]
  data: T[]
  loading?: boolean
  onSort?: (key: string, direction: 'asc' | 'desc') => void
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
  emptyMessage?: string
}

export const Table = <T extends Record<string, any>>({
  columns,
  data,
  loading = false,
  onSort,
  sortKey,
  sortDirection = 'asc',
  emptyMessage = 'Nenhum dado encontrado',
}: TableProps<T>) => {
  const handleSort = (key: string) => {
    if (!onSort) return
    const direction = sortKey === key && sortDirection === 'asc' ? 'desc' : 'asc'
    onSort(key, direction)
  }

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
        <p className="text-gray-400">Carregando...</p>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 text-center">
        <p className="text-gray-400">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-700 bg-gray-700">
            {columns.map((column) => (
              <th
                key={String(column.key)}
                className="px-6 py-3 text-left text-sm font-semibold text-gray-300"
                style={{ width: column.width }}
              >
                <div className="flex items-center gap-2 cursor-pointer group">
                  <span>{column.label}</span>
                  {column.sortable && onSort && (
                    <button
                      onClick={() => handleSort(String(column.key))}
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      {sortKey === String(column.key) ? (
                        sortDirection === 'asc' ? (
                          <ChevronUp size={16} />
                        ) : (
                          <ChevronDown size={16} />
                        )
                      ) : (
                        <ChevronUp size={16} className="opacity-50" />
                      )}
                    </button>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className="border-b border-gray-700 hover:bg-gray-700 transition"
            >
              {columns.map((column) => (
                <td
                  key={String(column.key)}
                  className="px-6 py-4 text-sm text-gray-300"
                  style={{ width: column.width }}
                >
                  {column.render
                    ? column.render((row as any)[column.key as keyof T], row, rowIdx)
                    : (row as any)[column.key as keyof T]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
