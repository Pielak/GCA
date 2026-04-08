/**
 * HelpTooltip — Ajuda contextual em nível pleno para todos os campos do GCA.
 *
 * Posição: ícone "?" à direita do label, tooltip aparece abaixo e à direita do ícone.
 * Nunca sobrepõe o conteúdo principal (z-50).
 * Acessível via teclado (Tab + Enter/Space abre, Escape fecha).
 *
 * Uso:
 *   <label className="flex items-center gap-1.5">
 *     Nome do campo
 *     <HelpTooltip text="Explicação completa..." />
 *   </label>
 */
import { useState, useRef, useEffect } from 'react'
import { CircleHelp } from 'lucide-react'

interface HelpTooltipProps {
  text: string
  position?: 'right' | 'left' | 'top' | 'bottom'
  maxWidth?: string
}

export function HelpTooltip({
  text,
  position = 'right',
  maxWidth = 'max-w-72'
}: HelpTooltipProps) {
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  // Fechar ao clicar fora
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setVisible(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const positionClass = {
    right:  'left-6 top-0',
    left:   'right-6 top-0',
    top:    'bottom-6 left-0',
    bottom: 'top-6 left-0',
  }[position]

  return (
    <span ref={ref} className="relative inline-flex items-center">
      <button
        type="button"
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onClick={() => setVisible(v => !v)}
        onKeyDown={(e) => e.key === 'Escape' && setVisible(false)}
        className="text-slate-400 hover:text-violet-400 transition-colors
                   focus:outline-none focus:ring-1 focus:ring-violet-500 rounded-full"
        aria-label="Ajuda sobre este campo"
        aria-expanded={visible}
      >
        <CircleHelp className="w-4 h-4" />
      </button>

      {visible && (
        <div
          role="tooltip"
          className={`absolute z-50 ${maxWidth} p-3 bg-slate-900 border border-slate-700
                      rounded-lg shadow-xl text-xs text-slate-300 leading-relaxed
                      whitespace-normal ${positionClass}`}
        >
          {text}
        </div>
      )}
    </span>
  )
}
