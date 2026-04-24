/**
 * Helpers canônicos de data/hora do GCA.
 *
 * Todo timestamp exibido na UI deve passar por um destes helpers pra
 * garantir timezone America/Sao_Paulo (GMT-3, com DST quando aplicável)
 * e locale pt-BR. Backend armazena em UTC (TIMESTAMPTZ + datetime.now(utc));
 * a conversão pra timezone do usuário acontece AQUI, nunca no servidor.
 */

const TZ = 'America/Sao_Paulo'
const LOCALE = 'pt-BR'

type DateInput = string | number | Date | null | undefined

function _toDate(input: DateInput): Date | null {
  if (input === null || input === undefined || input === '') return null
  const d = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(d.getTime())) return null
  return d
}

/** Formato `dd/MM/yyyy, HH:mm` em America/Sao_Paulo. Retorna '—' se inválido. */
export function formatDateTimeBR(input: DateInput): string {
  const d = _toDate(input)
  if (!d) return '—'
  return d.toLocaleString(LOCALE, {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Formato `dd/MM/yyyy, HH:mm:ss` em America/Sao_Paulo. */
export function formatDateTimeSecondsBR(input: DateInput): string {
  const d = _toDate(input)
  if (!d) return '—'
  return d.toLocaleString(LOCALE, {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Formato `dd/MM/yyyy` em America/Sao_Paulo. */
export function formatDateBR(input: DateInput): string {
  const d = _toDate(input)
  if (!d) return '—'
  return d.toLocaleDateString(LOCALE, {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

/** Formato `HH:mm` em America/Sao_Paulo. */
export function formatTimeBR(input: DateInput): string {
  const d = _toDate(input)
  if (!d) return '—'
  return d.toLocaleTimeString(LOCALE, {
    timeZone: TZ,
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * "Há X min/h/dias" relativo ao agora, pt-BR. Útil em timelines.
 * Fallback pra formatDateTimeBR quando diff > 7 dias.
 */
export function formatRelativeBR(input: DateInput): string {
  const d = _toDate(input)
  if (!d) return '—'
  const diffMs = Date.now() - d.getTime()
  const sec = Math.floor(diffMs / 1000)
  if (sec < 60) return 'agora há pouco'
  const min = Math.floor(sec / 60)
  if (min < 60) return `há ${min} min`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `há ${hr}h`
  const days = Math.floor(hr / 24)
  if (days < 7) return `há ${days} ${days === 1 ? 'dia' : 'dias'}`
  return formatDateTimeBR(input)
}
