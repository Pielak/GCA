import { ShieldAlert } from 'lucide-react'

export function ReadOnlyBanner() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-300">
      <ShieldAlert className="h-4 w-4 shrink-0" />
      <span>Modo somente leitura — voce nao e membro deste projeto</span>
    </div>
  )
}
