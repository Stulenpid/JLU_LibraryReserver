const BASE = (import.meta.env.VITE_API_BASE as string) || '/api'
const KEY = (import.meta.env.VITE_ADMIN_KEY as string) || ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  headers.set('Accept', 'application/json')
  if (KEY) headers.set('X-Admin-Key', KEY)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let resp: Response
  try {
    resp = await fetch(`${BASE}${path}`, { ...init, headers })
  } catch (e: any) {
    throw new ApiError(0, `无法连接后端：${e?.message || e}`)
  }

  const text = await resp.text()
  let data: any = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text }
    }
  }

  if (!resp.ok) {
    const msg = data?.detail || data?.message || `HTTP ${resp.status}`
    throw new ApiError(resp.status, typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export type LogLevel = 'ok' | 'err' | 'warn' | 'info' | 'prog'

export interface LogItem {
  ts: string
  level: LogLevel
  msg: string
}

/**
 * 订阅后端日志流。EventSource 不能自定义请求头，
 * 所以密钥只能走查询参数，后端鉴权中间件对此额外放行。
 * 返回值调用一次即断开。
 */
export function subscribeLogs(
  onLog: (item: LogItem) => void,
  onState?: (connected: boolean) => void,
): () => void {
  let es: EventSource | null = null
  let timer: number | null = null
  let closed = false

  const connect = () => {
    if (closed) return
    const qs = KEY ? `?key=${encodeURIComponent(KEY)}` : ''
    es = new EventSource(`${BASE}/logs/stream${qs}`)

    es.onopen = () => onState?.(true)

    es.onmessage = (ev) => {
      if (!ev.data) return
      try {
        const obj = JSON.parse(ev.data)
        onLog({
          ts: obj.ts || new Date().toLocaleTimeString('zh-CN', { hour12: false }),
          level: (obj.level || 'info') as LogLevel,
          msg: String(obj.msg ?? ''),
        })
      } catch {
        onLog({
          ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
          level: 'info',
          msg: ev.data,
        })
      }
    }

    es.onerror = () => {
      onState?.(false)
      es?.close()
      es = null
      if (!closed) timer = window.setTimeout(connect, 3000)
    }
  }

  connect()

  return () => {
    closed = true
    if (timer) window.clearTimeout(timer)
    es?.close()
    onState?.(false)
  }
}