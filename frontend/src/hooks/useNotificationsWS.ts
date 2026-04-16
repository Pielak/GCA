/**
 * useNotificationsWS — conexão WebSocket para notificações em tempo real.
 *
 * Substitui o poll de 60s. Quando uma notificação é criada no backend,
 * chega via WebSocket em ~ms; o callback `onNotification` é invocado.
 *
 * - Auto-reconnect com exponential backoff (1s → 2s → 4s → ... cap 30s).
 * - Ping a cada 25s para manter conexão atrás de proxies/load balancers.
 * - Retorna `connected` boolean — caller pode usar para fallback de poll.
 */
import { useEffect, useRef, useState } from 'react'

export type WsNotification = {
  type: 'notification.created'
  id: string
  event_type: string
  title: string
  message: string
  severity: string
  link: string | null
  project_id: string | null
  created_at: string | null
}

const PING_INTERVAL_MS = 25_000
const RECONNECT_MIN_MS = 1_000
const RECONNECT_MAX_MS = 30_000

export function useNotificationsWS(opts: {
  enabled: boolean
  onNotification: (n: WsNotification) => void
}) {
  const { enabled, onNotification } = opts
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const pingTimerRef = useRef<number | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const backoffRef = useRef(RECONNECT_MIN_MS)
  const onNotificationRef = useRef(onNotification)
  onNotificationRef.current = onNotification

  useEffect(() => {
    if (!enabled) return

    let cancelled = false

    const cleanup = () => {
      if (pingTimerRef.current) {
        window.clearInterval(pingTimerRef.current)
        pingTimerRef.current = null
      }
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (wsRef.current) {
        try { wsRef.current.close() } catch { /* */ }
        wsRef.current = null
      }
    }

    const connect = () => {
      if (cancelled) return
      const token = localStorage.getItem('access_token')
      if (!token) {
        // Sem token, retry mais lento
        reconnectTimerRef.current = window.setTimeout(connect, RECONNECT_MAX_MS)
        return
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      const url = `${protocol}//${host}/api/v1/notifications/ws?token=${encodeURIComponent(token)}`

      let ws: WebSocket
      try {
        ws = new WebSocket(url)
      } catch {
        scheduleReconnect()
        return
      }

      wsRef.current = ws

      ws.onopen = () => {
        if (cancelled) { try { ws.close() } catch { /* */ }; return }
        setConnected(true)
        backoffRef.current = RECONNECT_MIN_MS  // reset backoff em sucesso
        // Ping periódico
        pingTimerRef.current = window.setInterval(() => {
          try { ws.send('{"type":"ping"}') } catch { /* */ }
        }, PING_INTERVAL_MS)
      }

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data)
          if (data?.type === 'notification.created') {
            onNotificationRef.current(data as WsNotification)
          }
          // ping/pong: ignorado
        } catch { /* mensagem malformada — ignorar */ }
      }

      ws.onerror = () => { /* onclose vai disparar logo em seguida */ }

      ws.onclose = () => {
        setConnected(false)
        if (pingTimerRef.current) {
          window.clearInterval(pingTimerRef.current)
          pingTimerRef.current = null
        }
        wsRef.current = null
        if (!cancelled) scheduleReconnect()
      }
    }

    const scheduleReconnect = () => {
      if (cancelled) return
      const delay = backoffRef.current
      backoffRef.current = Math.min(backoffRef.current * 2, RECONNECT_MAX_MS)
      reconnectTimerRef.current = window.setTimeout(connect, delay)
    }

    connect()

    return () => {
      cancelled = true
      cleanup()
    }
  }, [enabled])

  return { connected }
}
