import { useState, useEffect } from 'react'
import { Loader2, Database } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

interface ActiveBackup {
  id: string
  project_id: string
  project_name: string | null
  trigger_source: string
}

/**
 * Backup-4: banner global mostrado enquanto algum backup do escopo do
 * usuário (Admin → todos; demais → projetos onde é membro) está com
 * status='running'. Polling a cada 5s.
 */
export function BackupActiveBanner() {
  const isAuthenticated = useAuthStore(s => Boolean(s.user))
  const [active, setActive] = useState<ActiveBackup[]>([])

  useEffect(() => {
    if (!isAuthenticated) return
    let cancelled = false
    const tick = async () => {
      try {
        const res = await apiClient.get('/backups/active')
        if (!cancelled) setActive(res.data.items || [])
      } catch {
        // silencioso — banner só aparece quando há dado
      }
    }
    tick()
    const t = setInterval(tick, 5000)
    return () => { cancelled = true; clearInterval(t) }
  }, [isAuthenticated])

  if (active.length === 0) return null

  return (
    <div className="fixed top-2 right-2 z-50 max-w-md bg-amber-950/80 backdrop-blur border border-amber-700/50 rounded-lg p-3 shadow-lg">
      <div className="flex items-center gap-2 text-amber-200 text-sm">
        <Database className="w-4 h-4" />
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="font-medium">
          Backup em andamento ({active.length})
        </span>
      </div>
      <ul className="mt-1 text-xs text-amber-300/80 space-y-0.5">
        {active.slice(0, 3).map(b => (
          <li key={b.id}>· {b.project_name || b.project_id.slice(0, 8)}</li>
        ))}
        {active.length > 3 && <li>· e mais {active.length - 3}…</li>}
      </ul>
    </div>
  )
}
