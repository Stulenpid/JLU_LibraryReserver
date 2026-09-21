import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

/* ============================================================
   内联图标：不依赖 lucide-react，避免图标改名与预构建问题
   统一 24x24 viewBox / currentColor / stroke-width 2
   ============================================================ */

type IconProps = { className?: string }

function Svg({ className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  )
}

const Settings = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H10a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V10a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </Svg>
)

const Armchair = (p: IconProps) => (
  <Svg {...p}>
    <path d="M19 9V6a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v3" />
    <path d="M3 11v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v2H7v-2a2 2 0 0 0-4 0z" />
    <path d="M5 18v2" />
    <path d="M19 18v2" />
  </Svg>
)

const Users = (p: IconProps) => (
  <Svg {...p}>
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </Svg>
)

const ListChecks = (p: IconProps) => (
  <Svg {...p}>
    <path d="m3 17 2 2 4-4" />
    <path d="m3 7 2 2 4-4" />
    <path d="M13 6h8" />
    <path d="M13 12h8" />
    <path d="M13 18h8" />
  </Svg>
)

const Clock = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 6v6l4 2" />
  </Svg>
)

const RefreshCw = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 12a9 9 0 0 1-9 9 9 9 0 0 1-6.7-3L3 16" />
    <path d="M3 12a9 9 0 0 1 9-9 9 9 0 0 1 6.7 3L21 8" />
    <path d="M21 3v5h-5" />
    <path d="M3 21v-5h5" />
  </Svg>
)

const Save = (p: IconProps) => (
  <Svg {...p}>
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
    <path d="M17 21v-8H7v8" />
    <path d="M7 3v5h8" />
  </Svg>
)

const RotateCcw = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 1 0 9-9 9 9 0 0 0-6.7 3L3 8" />
    <path d="M3 3v5h5" />
  </Svg>
)

const Play = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 4l14 8-14 8z" />
  </Svg>
)

const Square = (p: IconProps) => (
  <Svg {...p}>
    <rect x="5" y="5" width="14" height="14" rx="2" />
  </Svg>
)

const Eye = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
)

const EyeOff = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10.7 6.2A9.8 9.8 0 0 1 12 6c6.4 0 10 6 10 6a18 18 0 0 1-2.4 3.2" />
    <path d="M6.6 6.8A18 18 0 0 0 2 12s3.6 6 10 6a9.7 9.7 0 0 0 4.3-1" />
    <path d="M14.1 14.1a3 3 0 0 1-4.2-4.2" />
    <path d="m3 3 18 18" />
  </Svg>
)

const CheckCircle2 = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="m8 12 3 3 5-6" />
  </Svg>
)

const XCircle = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="m15 9-6 6" />
    <path d="m9 9 6 6" />
  </Svg>
)

const AlertTriangle = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
  </Svg>
)

const Info = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 16v-4" />
    <path d="M12 8h.01" />
  </Svg>
)

const Loader2 = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 12a9 9 0 1 1-6.2-8.6" />
  </Svg>
)

const ChevronDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
)

const Trash2 = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 6h18" />
    <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
  </Svg>
)

/* ============================================================
   类型
   ============================================================ */

type FieldType =
  | 'string' | 'int' | 'float' | 'time'
  | 'datetime_or_null' | 'int_list'

interface ConfigField {
  key: string
  label: string
  type: FieldType
  group: string
  default: unknown
  secret?: boolean
  help?: string
  min?: number
  max?: number
}

interface ConfigSchema {
  groups: string[]
  fields: ConfigField[]
}

type ConfigValues = Record<string, unknown>

interface LogEntry {
  ts: string
  level: 'ok' | 'err' | 'warn' | 'info' | 'prog'
  text: string
}

interface TaskState {
  running: boolean
  last: string | null
}

/**
 * 滚动条样式。默认滚动条在深色底上是浅灰粗条，非常抢眼，
 * 尤其日志区和 JSON 区各一条时更乱。这里统一收细并调成
 * 与 slate 背景同调，hover 才提亮。
 *
 * 用 \<style\> 注入而不是写进 index.css，是为了让这个面板
 * 保持单文件可移植；scrollbar-width 走标准属性，
 * ::-webkit-scrollbar 兜 Chrome/Edge/Safari。
 */
const SCROLLBAR_CSS = `
.lib-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgb(51 65 85) transparent;
}
.lib-scroll::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.lib-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.lib-scroll::-webkit-scrollbar-thumb {
  background-color: rgb(51 65 85);
  border-radius: 9999px;
  border: 2px solid transparent;
  background-clip: content-box;
}
.lib-scroll::-webkit-scrollbar-thumb:hover {
  background-color: rgb(71 85 105);
}
.lib-scroll::-webkit-scrollbar-corner {
  background: transparent;
}
`

const TASK_LABELS: Record<string, string> = {
  token_monitor: 'Token 监控',
  checkin_guard: '签到守护',
  meeting_scheduler: '定时会议室预约',
  seat_scheduler: '定时座位预约',
}

/** 后端 /reservations 归一化后的一行。字段名与后端保持一致，
 *  取消时必须回传 reservationId + cancelType，不要自行推断类型。 */
interface Reservation {
  index: number
  group: 'SEAT' | 'MEETING_ROOM' | 'OTHER'
  reservationId: string | number
  type: string | null
  cancelType: string
  typeLabel: string
  name: string | null
  location: string | null
  time: string | null
  startAt: string | null
  status: string | null
  statusLabel: string | null
  meetingTitle: string | null
  cancelable: boolean
  raw: unknown
}

/** 后端 /seat/query 的返回。data 已在后端筛掉 FINISHED/CANCELED
 *  并按 startTime 升序排好，hidden 是被隐藏的条数。 */
interface SeatQueryResult {
  seatId?: number | string
  date?: string
  data?: unknown[]
  count?: number
  total?: number
  hidden?: number
}

/** 占用条目展示用的归一化结果 */
interface Occupancy {
  key: string
  start: string
  end: string
  span: string
  status: string | null
  statusLabel: string
  who: string | null
  mine: boolean
}

/** 后端 /seat/reserve、/meeting/reserve 的返回。success 是后端已经判定好的
 *  业务层面结果——上游即使预约失败（时段冲突等）也会回 HTTP 200，body 换成
 *  code/message，所以绝不能拿「请求没抛异常」当成功依据，必须读这个字段。
 *  message 是后端拼好的可读摘要，直接展示即可，不用前端再猜结构。 */
interface ReserveOutcome {
  success?: boolean
  message?: string
  partial?: boolean
  successCount?: number
  total?: number
}

/** 后端 /meeting/query 的返回。上游把可约会议室放在 data，
 *  不同版本外层键名不一，取值时逐个试。 */
interface MeetingQueryResult {
  date?: string
  startTime?: string
  endTime?: string
  data?: unknown[]
  rooms?: unknown[]
  list?: unknown[]
  count?: number
  total?: number
}

/** 会议室条目展示用的归一化结果。三态直接取后端算好的 occState：
 *  in_use（使用中）/ reserved（有预约）/ free（可预约），
 *  纯按房间当前 status 分类，不再掺杂时段可约性判断。 */
interface RoomItem {
  key: string
  roomId: string | null
  name: string
  location: string | null
  capacity: string | null
  occState: 'in_use' | 'reserved' | 'free'
  occStateLabel: string
}

/** 单房间当天占用的展开态：加载中 / 已加载结果 / 出错信息 */
interface RoomDetail {
  loading: boolean
  result: SeatQueryResult | null
  error: string | null
}

/* ============================================================
   API 层
   ============================================================ */

const BASE = '/api'

function adminKey(): string {
  try {
    return localStorage.getItem('libAdminKey') ?? ''
  } catch {
    return ''
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Key': adminKey(),
      ...(init?.headers ?? {}),
    },
  })
  const text = await res.text()
  let body: unknown = null
  let parseFailed = false
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = { detail: text }
      parseFailed = true
    }
  }
  if (!res.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${res.status}`
    throw new Error(detail)
  }
  // HTTP 200 不代表拿到了预期的 JSON——反向代理没配对（比如 /api 被 SPA 的
  // try_files 兜底吃掉、返回了 index.html）时状态码依然是 200，但 body 其实
  // 是网页原文。这里必须显式识破，否则下游代码会拿一个假的对象当真实结构用，
  // 直到某处 .map/.filter 撞上 undefined 才崩，报错信息完全不知所云。
  if (parseFailed) {
    throw new Error(
      '接口未返回 JSON，很可能是 /api 反向代理没生效（请求被前端路由兜底吃掉了），请检查 Nginx 配置与后端容器是否可达',
    )
  }
  return body as T
}

const api = {
  schema: () => call<ConfigSchema>('/config/schema'),
  formDefaults: () =>
    call<{
      date: string
      seat: { seatId: number; date: string; startTime: string; endTime: string }
      meeting: {
        roomId: number
        date: string
        startTime: string
        endTime: string
        granularity: number
      }
    }>('/form/defaults'),
  getConfig: (reveal = false) =>
    call<{ config: ConfigValues; defaultDate: string }>(
      `/config?reveal=${reveal ? 'true' : 'false'}`,
    ),
  putConfig: (config: ConfigValues) =>
    call<{ changed: string[]; config: ConfigValues }>('/config', {
      method: 'PUT',
      body: JSON.stringify({ config }),
    }),
  resetConfig: () =>
    call<{ config: ConfigValues }>('/config/reset', { method: 'POST' }),
  checkToken: () =>
    call<{ valid: boolean; nickname?: string; userId?: string; message?: string }>(
      '/token/check',
    ),
  tasks: () => call<{ tasks: Record<string, TaskState> }>('/tasks'),
  taskControl: (name: string, action: 'start' | 'stop') =>
    call<{ tasks: Record<string, TaskState> }>(`/tasks/${name}/${action}`, {
      method: 'POST',
    }),
  seatQuery: (b: unknown) =>
    call<SeatQueryResult>('/seat/query', {
      method: 'POST',
      body: JSON.stringify(b),
    }),
  seatReserve: (b: unknown) =>
    call<ReserveOutcome>('/seat/reserve', { method: 'POST', body: JSON.stringify(b) }),
  meetingQuery: (b: unknown) =>
    call<MeetingQueryResult>('/meeting/query', {
      method: 'POST',
      body: JSON.stringify(b),
    }),
  meetingReserve: (b: unknown) =>
    call<ReserveOutcome>('/meeting/reserve', { method: 'POST', body: JSON.stringify(b) }),
  // 单个会议室当天的预约明细，用于「查看当天占用」——与座位查占用对称
  roomReservations: (b: unknown) =>
    call<SeatQueryResult>('/meeting/room/reservations', {
      method: 'POST',
      body: JSON.stringify(b),
    }),
  // 不带 status 过滤：IN_USE（已签到进行中）也允许取消，
  // 之前写死 status=RESERVED 会把这类记录整个藏起来。
  reservations: () =>
    call<{ data: Reservation[]; count: number }>('/reservations'),
  cancel: (reservationId: string | number, cancelType: string) =>
    call<{ data: unknown; active: unknown }>('/cancel', {
      method: 'POST',
      body: JSON.stringify({ reservationId, cancelType }),
    }),
  recentLogs: () => call<{ logs: LogEntry[] }>('/logs?limit=200'),
}

/* ============================================================
   小组件
   ============================================================ */

/**
 * 日志级别图标。
 *
 * active 只对 prog 生效：一条 prog 只有在它仍是最后一行日志时才转圈，
 * 一旦后面又来了新日志，说明这一步已经过去了，图标必须停下来——
 * 否则整屏历史进度行会一直转，观感很糟且让人误以为任务还在跑。
 */
function LevelIcon({ level, active }: { level: LogEntry['level']; active?: boolean }) {
  const cls = 'w-4 h-4 shrink-0 mt-0.5'
  if (level === 'ok') return <CheckCircle2 className={`${cls} text-emerald-400`} />
  if (level === 'err') return <XCircle className={`${cls} text-red-400`} />
  if (level === 'warn') return <AlertTriangle className={`${cls} text-amber-400`} />
  if (level === 'prog') {
    // 这一步已经跑完（后面有新日志或请求已结束）就换成绿对号，
    // 而不是停住的灰圈——灰圈看上去像卡住了。失败会另起一条 err 日志，
    // 不会把错误隐藏在这个对号里。
    if (active) return <Loader2 className={`${cls} animate-spin text-cyan-400`} />
    return <CheckCircle2 className={`${cls} text-emerald-500/70`} />
  }
  return <Info className={`${cls} text-sky-400`} />
}

/* ---- 输入校验：规则与后端 need_date / need_time 一致 ---- */

const RE_DATE = /^\d{4}-\d{2}-\d{2}$/
const RE_TIME = /^(\d{1,2}):(\d{2})$/

/** 返回错误提示，空字符串表示通过。空值不报错（后端会填默认）。 */
function checkDate(v: string): string {
  const s = v.trim()
  if (!s) return ''
  if (!RE_DATE.test(s)) return '格式需为 YYYY-MM-DD'
  const [y, m, d] = s.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) {
    return '该日期不存在'
  }
  return ''
}

function checkTime(v: string): string {
  const s = v.trim()
  if (!s) return ''
  const m = RE_TIME.exec(s)
  if (!m) return '格式需为 HH:MM'
  if (Number(m[1]) > 23 || Number(m[2]) > 59) return '时刻超出范围'
  return ''
}

function checkInt(v: string, label = '此项'): string {
  const s = v.trim()
  if (!s) return ''
  if (!/^\d+$/.test(s)) return `${label}需为整数`
  return ''
}

/** HH:MM 补零后可直接字典序比较，比转 Date 稳 */
function hmValue(v: string): string {
  const m = RE_TIME.exec(v.trim())
  if (!m) return ''
  return `${m[1].padStart(2, '0')}:${m[2]}`
}

/**
 * 带校验边框的输入框：合法绿边、非法红边并在下方提示、
 * 空值保持中性灰边（交给后端填默认）。
 */
function VInput({
  label,
  value,
  onChange,
  error,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  error?: string
  placeholder?: string
}) {
  const border = error
    ? 'border-red-500 focus:border-red-400'
    : value.trim()
      ? 'border-emerald-500 focus:border-emerald-400'
      : 'border-slate-700 focus:border-sky-500'
  return (
    <label className="block">
      <span className="text-sm text-slate-300">{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={Boolean(error)}
        className={`mt-1 w-full rounded-md border bg-slate-900 px-3 py-2 text-sm outline-none transition ${border}`}
      />
      {error ? (
        <span className="mt-1 flex items-center gap-1 text-xs text-red-400">
          <AlertTriangle className="h-3 w-3" />
          {error}
        </span>
      ) : null}
    </label>
  )
}

function Field({
  spec,
  value,
  onChange,
  revealed,
}: {
  spec: ConfigField
  value: unknown
  onChange: (v: unknown) => void
  revealed: boolean
}) {
  const [show, setShow] = useState(false)
  const isSecret = Boolean(spec.secret)
  const masked = isSecret && typeof value === 'string' && value.includes('******')

  const display = useMemo(() => {
    if (spec.type === 'int_list') {
      return Array.isArray(value) ? value.join(', ') : String(value ?? '')
    }
    if (value === null || value === undefined) return ''
    return String(value)
  }, [spec.type, value])

  const inputType =
    isSecret && !show && !revealed
      ? 'password'
      : spec.type === 'int' || spec.type === 'float'
        ? 'number'
        : 'text'

  const placeholder =
    spec.type === 'time'
      ? 'HH:MM'
      : spec.type === 'datetime_or_null'
        ? 'YYYY-MM-DD HH:MM:SS（留空=立即）'
        : spec.type === 'int_list'
          ? '24545, 25420'
          : ''

  return (
    <label className="block">
      <span className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-slate-200">{spec.label}</span>
        <code className="text-xs text-slate-500">{spec.key}</code>
      </span>
      <span className="mt-1 flex items-center gap-2">
        <input
          type={inputType}
          step={spec.type === 'float' ? '0.1' : undefined}
          min={spec.min}
          max={spec.max}
          value={display}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className={`w-full rounded-md border bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-500 ${
            masked ? 'border-slate-700 text-slate-500' : 'border-slate-700'
          }`}
        />
        {isSecret && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="rounded-md border border-slate-700 p-2 text-slate-400 hover:text-slate-200"
            title={show ? '隐藏' : '显示'}
          >
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </span>
      {spec.help && (
        <span className="mt-1 block text-xs text-slate-500">{spec.help}</span>
      )}
      {masked && (
        <span className="mt-1 block text-xs text-amber-500/80">
          已脱敏显示，不修改则保留原值
        </span>
      )}
    </label>
  )
}

const OCC_STATUS_LABEL: Record<string, string> = {
  RESERVED: '待签到',
  IN_USE: '使用中',
  PAUSED: '暂离',
  FINISHED: '已结束',
  CANCELED: '已取消',
  AUTO_CANCELED: '超时取消',
}

/** 从任意形状的对象里取第一个非空字段，上游字段命名不完全稳定 */
function pick(o: Record<string, unknown>, keys: string[]): string | null {
  for (const k of keys) {
    const v = o[k]
    if (v !== null && v !== undefined && String(v).trim() !== '') return String(v)
  }
  return null
}

/** "2026-09-09 18:00" / ISO / "18:00" 一律压成 HH:MM，取不到就原样返回 */
function toHM(v: string | null): string {
  if (!v) return ''
  const m = /(\d{1,2}):(\d{2})/.exec(v)
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : v
}

/**
 * 把 /seat/query 的 data 归一化成可读列表。
 *
 * 这里做防御式取字段而不是写死键名：座位占用条目的字段命名没在原脚本里
 * 固化过（startTime/beginTime、userName/nickName 都出现过）。取不到就显示
 * 占位符，绝不让整块渲染崩掉——JSON 原文始终在下方可查。
 */
function normalizeOccupancy(data: unknown[]): Occupancy[] {
  return data.map((row, i) => {
    const o = (row ?? {}) as Record<string, unknown>
    const start = toHM(pick(o, ['startTime', 'beginTime', 'start', 'fromTime']))
    const end = toHM(pick(o, ['endTime', 'finishTime', 'end', 'toTime']))
    const status = pick(o, ['status', 'state'])
    const timeText = pick(o, ['time', 'timeRange'])
    const span = start || end ? `${start || '?'} – ${end || '?'}` : (timeText ?? '时间未知')
    return {
      key: String(pick(o, ['reservationId', 'id']) ?? `row-${i}`),
      start,
      end,
      span,
      status,
      statusLabel: status ? (OCC_STATUS_LABEL[status] ?? status) : '状态未知',
      who: pick(o, ['userName', 'nickName', 'nickname', 'realName', 'studentId']),
      mine: Boolean(o.mine ?? o.isMine ?? o.self),
    }
  })
}

/**
 * 座位占用情况列表：与活跃预约同一套行式布局。
 * 只显示时段、状态、占用者，一眼看出哪些时间还空着。
 */
function OccupancyList({ result }: { result: SeatQueryResult }) {
  const rows = useMemo(
    () => normalizeOccupancy(Array.isArray(result.data) ? result.data : []),
    [result],
  )
  const hidden = result.hidden ?? 0

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-sky-400">
          座位占用情况
          {result.seatId !== undefined && (
            <span className="ml-2 font-normal text-slate-500">
              座位 {String(result.seatId)}
              {result.date ? ` · ${result.date}` : ''}
            </span>
          )}
        </span>
        <span className="text-xs text-slate-500">
          未结束 {rows.length} 条
          {hidden > 0 && ` · 已隐藏 ${hidden} 条已结束/已取消`}
        </span>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-md border border-emerald-800/60 bg-emerald-950/40 px-3 py-3 text-sm text-emerald-300">
          该座位当日暂无未结束的占用，全天可约。
        </p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li
              key={r.key}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-slate-800 bg-slate-950 px-3 py-2"
            >
              <Clock className="h-4 w-4 shrink-0 text-amber-400" />
              <span className="font-mono text-sm text-slate-100">{r.span}</span>
              <span
                className={`rounded px-2 py-0.5 text-xs ${
                  r.status === 'IN_USE'
                    ? 'bg-emerald-900/60 text-emerald-300'
                    : r.status === 'RESERVED'
                      ? 'bg-amber-900/60 text-amber-300'
                      : 'bg-slate-800 text-slate-400'
                }`}
              >
                {r.statusLabel}
              </span>
              {r.mine && (
                <span className="rounded bg-sky-900/60 px-2 py-0.5 text-xs text-sky-300">
                  我的
                </span>
              )}
              {r.who && <span className="text-xs text-slate-500">{r.who}</span>}
              <span className="ml-auto text-xs text-slate-600">{r.key}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const OCC_STATE_LABEL: Record<string, string> = {
  in_use: '使用中',
  reserved: '有预约',
  free: '可预约',
}

/**
 * 把 /meeting/query 的结果归一化成可读列表。
 *
 * 三色约定纯按后端算好的 occState（= 房间当前 status 的直接映射）：
 *   in_use（此刻有人，灰色）/ reserved（此刻空但当天有预约，黄色）/
 *   free（可预约，绿色）。不再判断某个具体时段是否可约、
 *   也不展示时长/人数是否满足规则——这类文字对用户没价值。
 */
function normalizeRooms(data: unknown[]): RoomItem[] {
  return data.map((row, i) => {
    const o = (row ?? {}) as Record<string, unknown>
    const roomId = pick(o, ['roomId', 'id'])
    const occState = (pick(o, ['occState']) ?? 'free') as RoomItem['occState']
    const cap = pick(o, ['capacity'])
    return {
      key: String(roomId ?? `room-${i}`),
      roomId,
      name: pick(o, ['name']) ?? '未命名会议室',
      location: pick(o, ['location']),
      capacity: cap,
      occState,
      occStateLabel: pick(o, ['occStateLabel']) ?? OCC_STATE_LABEL[occState] ?? '可预约',
    }
  })
}

/**
 * 可用会议室列表：与座位占用、活跃预约同一套行式布局。
 * 右侧「填入」把 roomId 写回表单，省去手抄编号。
 */
function RoomList({
  result,
  onPick,
}: {
  result: MeetingQueryResult
  onPick: (roomId: string) => void
}) {
  const raw = Array.isArray(result.data)
    ? result.data
    : Array.isArray(result.rooms)
      ? result.rooms
      : Array.isArray(result.list)
        ? result.list
        : []
  const rows = useMemo(() => normalizeRooms(raw), [raw])

  // 展开的房间 key → 当天占用明细。点一下拉一次，再点收起；
  // 缓存已拉到的结果，重复展开不重拉。
  const [detail, setDetail] = useState<Record<string, RoomDetail>>({})

  const toggle = useCallback(
    (r: RoomItem) => {
      const cur = detail[r.key]
      if (cur && !cur.error) {
        // 已展开（含加载中/已加载）→ 收起
        setDetail((p) => {
          const next = { ...p }
          delete next[r.key]
          return next
        })
        return
      }
      if (!r.roomId) return
      setDetail((p) => ({ ...p, [r.key]: { loading: true, result: null, error: null } }))
      api
        .roomReservations({ roomId: r.roomId, date: result.date, roomName: r.name })
        .then((res) =>
          setDetail((p) => ({
            ...p,
            [r.key]: { loading: false, result: res, error: null },
          })),
        )
        .catch((e: unknown) =>
          setDetail((p) => ({
            ...p,
            [r.key]: {
              loading: false,
              result: null,
              error: e instanceof Error ? e.message : String(e),
            },
          })),
        )
    },
    [detail, result.date],
  )

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-sky-400">
          可用会议室
          {(result.date || result.startTime) && (
            <span className="ml-2 font-normal text-slate-500">
              {result.date ?? ''}
              {result.startTime ? ` ${result.startTime}` : ''}
              {result.endTime ? ` – ${result.endTime}` : ''}
            </span>
          )}
        </span>
        <span className="text-xs text-slate-500">共 {rows.length} 间</span>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-md border border-amber-800/60 bg-amber-950/40 px-3 py-3 text-sm text-amber-300">
          该时段没有可用会议室，换个时段或缩短时长再试。
        </p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => {
            const d = detail[r.key]
            const open = Boolean(d)
            return (
              <li
                key={r.key}
                className="rounded-md border border-slate-800 bg-slate-950"
              >
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                  <Users className="h-4 w-4 shrink-0 text-violet-400" />
                  <span className="text-sm font-medium text-slate-100">{r.name}</span>
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      r.occState === 'in_use'
                        ? 'bg-slate-800 text-slate-400'
                        : r.occState === 'reserved'
                          ? 'bg-amber-900/60 text-amber-300'
                          : 'bg-emerald-900/60 text-emerald-300'
                    }`}
                  >
                    {r.occStateLabel}
                  </span>
                  {r.capacity && (
                    <span className="text-xs text-slate-500">可容 {r.capacity} 人</span>
                  )}
                  {r.location && (
                    <span className="text-xs text-slate-500">{r.location}</span>
                  )}
                  <span className="ml-auto flex items-center gap-2">
                    <span className="text-xs text-slate-600">ID {r.key}</span>
                    {r.roomId && (
                      <button
                        type="button"
                        onClick={() => toggle(r)}
                        className={`rounded border px-2 py-0.5 text-xs transition ${
                          open
                            ? 'border-sky-700 bg-sky-950 text-sky-300'
                            : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        {open ? '收起占用' : '查看当天占用'}
                      </button>
                    )}
                    {r.roomId && (
                      <button
                        type="button"
                        onClick={() => onPick(r.roomId as string)}
                        className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                      >
                        填入
                      </button>
                    )}
                  </span>
                </div>

                {open && (
                  <div className="border-t border-slate-800 px-3 py-3">
                    {d.loading && (
                      <p className="flex items-center gap-2 text-xs text-slate-400">
                        <Loader2 className="h-3 w-3 animate-spin text-cyan-400" />
                        正在查询当天占用……
                      </p>
                    )}
                    {d.error && (
                      <p className="flex items-center gap-2 text-xs text-red-400">
                        <AlertTriangle className="h-3 w-3" />
                        {d.error}
                      </p>
                    )}
                    {!d.loading && !d.error && d.result && (
                      <OccupancyList result={d.result} />
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    
    </div>
    
  )
}

function Btn({
  children,
  onClick,
  tone = 'default',
  disabled,
}: {
  children: React.ReactNode
  onClick?: () => void
  tone?: 'default' | 'primary' | 'danger'
  disabled?: boolean
}) {
  const tones = {
    default: 'border-slate-700 text-slate-200 hover:bg-slate-800',
    primary: 'border-sky-600 bg-sky-600 text-white hover:bg-sky-500',
    danger: 'border-red-700 text-red-300 hover:bg-red-950',
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition disabled:opacity-40 ${tones[tone]}`}
    >
      {children}
    </button>
  )
}

/* ============================================================
   主组件
   ============================================================ */

export default function LibraryPanel() {
  const [tab, setTab] = useState<'config' | 'seat' | 'meeting' | 'manage'>('config')
  const [schema, setSchema] = useState<ConfigSchema | null>(null)
  const [values, setValues] = useState<ConfigValues>({})
  const [dirty, setDirty] = useState<Record<string, unknown>>({})
  const [revealed, setRevealed] = useState(false)
  const [defaultDate, setDefaultDate] = useState('')
  const [tasks, setTasks] = useState<Record<string, TaskState>>({})
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
    const [showAppearanceModal, setShowAppearanceModal] = useState(false)
  const [faviconUrl, setFaviconUrl] = useState(localStorage.getItem('libFaviconUrl') || '../image/吉大校徽.png')
  const [bgImageUrl, setBgImageUrl] = useState(localStorage.getItem('libBgImageUrl') || '../image/background.png')
  const [keyInput, setKeyInput] = useState(adminKey())
  const [result, setResult] = useState<unknown>(null)
  // 座位查询结果单独存一份，用于在 JSON 上方渲染可读列表
  const [occupancy, setOccupancy] = useState<SeatQueryResult | null>(null)
  // 会议室查询结果同样单独存一份，渲染成可读列表
  const [rooms, setRooms] = useState<MeetingQueryResult | null>(null)
  // 「接口返回」原始 JSON 与「后端日志」两块默认折叠，避免占地方
  const [showResult, setShowResult] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const logTop = useRef<HTMLDivElement>(null)
  // 初始化 favicon 和背景
  useEffect(() => {
    const iconUrl = localStorage.getItem('libFaviconUrl') || '../image/吉大校徽.png'
    const bgUrl = localStorage.getItem('libBgImageUrl') || '../image/background.png'
    
    // 设置 favicon
    let link = document.querySelector("link[rel='icon']") as HTMLLinkElement
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.href = iconUrl
    
    // 设置背景
    if (bgUrl) {
      document.body.style.backgroundImage = `
        linear-gradient(rgba(0, 0, 0, 0.5), rgba(0, 0, 0, 0.5)),
        url('${bgUrl}')
      `
      document.body.style.backgroundAttachment = 'fixed'
      document.body.style.backgroundSize = 'cover'
      document.body.style.backgroundPosition = 'center'
    }
  }, [])

  const toast = useCallback((kind: 'ok' | 'err', text: string) => {
    setNotice({ kind, text })
    window.setTimeout(() => setNotice(null), 4000)
  }, [])

  const guard = useCallback(
    async (fn: () => Promise<void>) => {
      setBusy(true)
      try {
        await fn()
      } catch (e) {
        toast('err', e instanceof Error ? e.message : String(e))
      } finally {
        setBusy(false)
      }
    },
    [toast],
  )

  /* ---- 初始加载 ---- */
  const loadAll = useCallback(
    (reveal = false) =>
      guard(async () => {
        const [sc, cf, tk] = [await api.schema(), await api.getConfig(reveal), await api.tasks()]
        setSchema(sc)
        setValues(cf.config)
        setDefaultDate(cf.defaultDate)
        setTasks(tk.tasks)
        setDirty({})
      }),
    [guard],
  )

  useEffect(() => {
    void loadAll(false)
  }, [loadAll])

  /* ---- 日志 SSE；EventSource 不能带请求头，用 query 传 key ---- */
  // 清屏水位线：记住清屏那一刻的最后一条日志，重连补拉时据此裁掉
  // 用户已经清掉的部分，否则一次断线重连就把整屏历史灌回来。
  const clearMark = useRef<{ ts: string; text: string } | null>(null)

  useEffect(() => {
    let closed = false
    let es: EventSource | null = null
    let timer: number | undefined
    let retry = 0

    const pull = () =>
      api
        .recentLogs()
        .then((r) => {
          if (closed) return
          const mark = clearMark.current
          if (!mark) {
            setLogs(r.logs)
            return
          }
          const at = r.logs.findIndex((l) => l.ts === mark.ts && l.text === mark.text)
          // 找不到水位线说明后端环形缓冲已经把它滚出去了，
          // 这时整批都是清屏之前的旧内容，直接丢弃，不回灌。
          if (at >= 0) setLogs(r.logs.slice(at + 1))
        })
        .catch(() => undefined)

    const connect = () => {
      if (closed) return
      try {
        es = new EventSource(`${BASE}/logs/stream?key=${encodeURIComponent(adminKey())}`)
        es.onopen = () => {
          retry = 0
          // 断线期间产生的日志会丢，补拉一次历史兜底（已按水位线过滤）
          void pull()
        }
        es.onmessage = (ev) => {
          try {
            const entry = JSON.parse(ev.data) as LogEntry
            setLogs((prev) => [...prev.slice(-499), entry])
          } catch {
            /* 心跳注释行，忽略 */
          }
        }
        es.onerror = () => {
          // 不依赖浏览器自动重连：它在被代理掐断时经常不再发起，
          // 这里主动关闭并按退避重建，最长 30 秒一次。
          es?.close()
          es = null
          if (closed) return
          retry = Math.min(retry + 1, 6)
          timer = window.setTimeout(connect, Math.min(1000 * 2 ** retry, 30000))
        }
      } catch {
        /* 不支持 SSE 时降级为仅展示历史 */
      }
    }

    void pull()
    connect()

    return () => {
      closed = true
      if (timer) window.clearTimeout(timer)
      es?.close()
    }
  }, [])

  // 初始化 favicon 和背景
useEffect(() => {
  // 设置 favicon
  let link = document.querySelector("link[rel='icon']") as HTMLLinkElement
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  link.href = faviconUrl

  // 设置背景图片
  document.body.style.backgroundImage = `
    linear-gradient(rgba(0, 0, 0, 0.5), rgba(0, 0, 0, 0.5)),
    url('${bgImageUrl}')
  `
  document.body.style.backgroundAttachment = 'fixed'
  document.body.style.backgroundSize = 'cover'
  document.body.style.backgroundPosition = 'center'
}, [faviconUrl, bgImageUrl])
  // 新消息显示在最上面，所以有新日志进来时滚回顶部，而不是滚到底部
  
  // 新消息显示在最上面，所以有新日志进来时滚回顶部，而不是滚到底部。
  // 依赖 logs.length 而非 logs 本身，并用 rAF 折叠到下一帧，
  // 避免连续日志涌入时每条都同步触发一次布局重算、把主线程占满。
  useEffect(() => {
    const id = window.requestAnimationFrame(() => {
      logTop.current?.scrollIntoView({ block: 'start' })
    })
    return () => window.cancelAnimationFrame(id)
  }, [logs.length])

  // 仅用于渲染：logs 状态本身仍按时间正序存储（追加、slice(-499) 都更简单），
  // 展示时反转成新消息在前。
  const displayLogs = useMemo(
    () => logs.map((l, i) => ({ l, i })).reverse(),
    [logs],
  )

  /* ---- 配置操作 ---- */
  const setField = (key: string, v: unknown) => {
    setValues((prev) => ({ ...prev, [key]: v }))
    setDirty((prev) => ({ ...prev, [key]: v }))
  }

  const save = () =>
    guard(async () => {
      if (Object.keys(dirty).length === 0) {
        toast('ok', '没有需要保存的改动')
        return
      }
      const res = await api.putConfig(dirty)
      setValues(res.config)
      setDirty({})
      toast('ok', `已保存 ${res.changed.length} 项：${res.changed.join('、') || '无'}`)
      setTasks((await api.tasks()).tasks)
    })

  const reset = () =>
    guard(async () => {
      if (!window.confirm('确认重置所有配置为默认值？包括 Token 和邮件授权码。')) return
      const res = await api.resetConfig()
      setValues(res.config)
      setDirty({})
      toast('ok', '已重置')
    })

  const grouped = useMemo(() => {
    if (!schema || !Array.isArray(schema.groups) || !Array.isArray(schema.fields)) return []
    return schema.groups.map((g) => ({
      group: g,
      fields: schema.fields.filter((f) => f.group === g),
    }))
  }, [schema])

  const num = (key: string, fallback = 0): number => {
    const v = values[key]
    const n = typeof v === 'number' ? v : Number(v)
    return Number.isFinite(n) ? n : fallback
  }
  const str = (key: string): string => {
    const v = values[key]
    return v === null || v === undefined ? '' : String(v)
  }

  /* ---- 业务表单：初始值由后端 /form/defaults 推断后下发 ----
     日期 = 按分界小时推断的待预约日，开始 = 当前时刻，结束 = 21:00。
     不在前端自己算，否则分界小时一改两端结果就不一致。 */
  const [seatForm, setSeatForm] = useState({ seatId: '', date: '', start: '', end: '' })
  const [meetForm, setMeetForm] = useState({
    roomId: '', date: '', start: '', end: '', granularity: '0',
  })
  const [reservations, setReservations] = useState<Reservation[] | null>(null)

  useEffect(() => {
    let alive = true
    api
      .formDefaults()
      .then((d) => {
        if (!alive) return
        setSeatForm({
          seatId: String(d.seat.seatId ?? ''),
          date: d.seat.date,
          start: d.seat.startTime,
          end: d.seat.endTime,
        })
        setMeetForm({
          roomId: String(d.meeting.roomId ?? ''),
          date: d.meeting.date,
          start: d.meeting.startTime,
          end: d.meeting.endTime,
          granularity: String(d.meeting.granularity ?? 0),
        })
      })
      .catch(() => undefined) // 拉不到就留空，提交时后端仍会填默认
    return () => {
      alive = false
    }
  }, [])

  const seatErr = useMemo(() => {
    const e = {
      seatId: checkInt(seatForm.seatId, '座位 ID'),
      date: checkDate(seatForm.date),
      start: checkTime(seatForm.start),
      end: checkTime(seatForm.end),
    }
    const s = hmValue(seatForm.start)
    const t = hmValue(seatForm.end)
    if (!e.start && !e.end && s && t && t <= s) e.end = '需晚于开始时间'
    return e
  }, [seatForm])

  const meetErr = useMemo(() => {
    const e = {
      roomId: checkInt(meetForm.roomId, '会议室 ID'),
      date: checkDate(meetForm.date),
      start: checkTime(meetForm.start),
      end: checkTime(meetForm.end),
      granularity: checkInt(meetForm.granularity, '粒度'),
    }
    const s = hmValue(meetForm.start)
    const t = hmValue(meetForm.end)
    if (!e.start && !e.end && s && t && t <= s) e.end = '需晚于开始时间'
    return e
  }, [meetForm])

  const seatBad = Object.values(seatErr).some(Boolean)
  const meetBad = Object.values(meetErr).some(Boolean)

  const loadReservations = useCallback(
    () =>
      guard(async () => {
        const r = await api.reservations()
        setReservations(r.data)
      }),
    [guard],
  )

  /** 提交预约成功后，如果活跃预约列表已经加载过，就顺手重拉一次，
   *  免得用户还要手动点「刷新列表」才能看到刚提交的这条。
   *  列表从未加载过（仍是 null）时不主动拉，保持原来的按需加载习惯。 */
  const refreshReservationsIfLoaded = useCallback(() => {
    if (reservations === null) return
    api
      .reservations()
      .then((r) => setReservations(r.data))
      .catch(() => undefined)
  }, [reservations])

  /** 是否真正预约成功，只认后端算好的 success 字段——
   *  HTTP 200 不代表业务成功，上游冲突/超限等失败同样是 200。
   *  没有 success 字段（异常结构）时保守判失败，避免误报成功。 */
  const isReserveSuccess = (r: ReserveOutcome): boolean => r.success === true

  const reserveToastKind = (r: ReserveOutcome): 'ok' | 'err' =>
    isReserveSuccess(r) ? 'ok' : 'err'

  const reserveToastText = (r: ReserveOutcome): string =>
    r.message ?? (isReserveSuccess(r) ? '预约提交成功' : '预约提交失败，未获得明确结果')

  const cancelAllReservations = () =>
    guard(async () => {
      const active = (reservations ?? []).filter((r) => r.cancelable)
      if (active.length === 0) {
        toast('err', '没有可取消的活跃预约')
        return
      }
      if (!window.confirm(`确认取消全部 ${active.length} 条可取消预约？\n\n此操作不可撤销。`)) return

      const outcomes = await Promise.allSettled(
        active.map((r) => api.cancel(r.reservationId, r.cancelType)),
      )
      const succeeded = outcomes.filter((o) => o.status === 'fulfilled').length
      const failed = outcomes.length - succeeded
      const fresh = await api.reservations()
      setReservations(fresh.data)
      setResult({ action: 'cancel_all', succeeded, failed, results: outcomes })
      toast(
        failed === 0 ? 'ok' : 'err',
        failed === 0
          ? `已取消全部 ${succeeded} 条预约`
          : `取消完成：成功 ${succeeded} 条，失败 ${failed} 条`,
      )
    })

  const tabs = [
    { id: 'config' as const, label: '参数配置', icon: Settings },
    { id: 'seat' as const, label: '座位预约', icon: Armchair },
    { id: 'meeting' as const, label: '会议室', icon: Users },
    { id: 'manage' as const, label: '预约与任务', icon: ListChecks },
  ]

  return (
    <div className="lib-scroll min-h-screen bg-slate-950 p-4 text-slate-100">
      <style>{SCROLLBAR_CSS}</style>
      <div className="mx-auto max-w-7xl">
        {/* 顶部 */}
        <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">吉林大学图书馆预约面板</h1>
            <p className="text-sm text-slate-400">
              后端实时配置、定时任务与日志流
              {defaultDate && <span className="ml-2 text-slate-500">默认日期 {defaultDate}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={keyInput}
              placeholder="ADMIN_KEY"
              onChange={(e) => setKeyInput(e.target.value)}
              className="w-40 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-sky-500"
            />
            <Btn
              onClick={() => {
                try {
                  localStorage.setItem('libAdminKey', keyInput)
                } catch {
                  /* 隐私模式下忽略 */
                }
                void loadAll(false)
              }}
            >
              <RefreshCw className="h-4 w-4" />
              应用并刷新
            </Btn>
          </div>
        </header>

        {notice && (
          <div
            className={`mb-3 rounded-md border px-3 py-2 text-sm ${
              notice.kind === 'ok'
                ? 'border-emerald-700 bg-emerald-950 text-emerald-200'
                : 'border-red-700 bg-red-950 text-red-200'
            }`}
          >
            {notice.text}
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-3">
          {/* 左侧主区 */}
          <section className="lg:col-span-2 rounded-lg border border-slate-800 bg-slate-900">
            <nav className="flex flex-wrap gap-1 border-b border-slate-800 p-2">
              {tabs.map((t) => {
                const Icon = t.icon
                const active = tab === t.id
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTab(t.id)}
                    className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm transition ${
                      active
                        ? 'bg-sky-600 text-white'
                        : 'text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {t.label}
                  </button>
                )
              })}
            </nav>

            <div className="p-4">
              {/* ---- 配置页 ---- */}
              {tab === 'config' && (
                <div>
                  <div className="mb-4 flex flex-wrap items-center gap-2">
                    <Btn tone="primary" onClick={save} disabled={busy}>
                      <Save className="h-4 w-4" />
                      保存并热生效
                      {Object.keys(dirty).length > 0 && ` (${Object.keys(dirty).length})`}
                    </Btn>
                    <Btn onClick={() => loadAll(!revealed ? true : false)} disabled={busy}>
                      {revealed ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      {revealed ? '重新脱敏' : '明文读取'}
                    </Btn>
                    <Btn
                      onClick={() =>
                        guard(async () => {
                          const r = await api.checkToken()
                          toast(
                            r.valid ? 'ok' : 'err',
                            r.valid
                              ? `Token 有效：${r.nickname}（ID ${r.userId}）`
                              : `Token 无效：${r.message ?? '未知原因'}`,
                          )
                        })
                      }
                      disabled={busy}
                    >
                      <CheckCircle2 className="h-4 w-4" />
                      校验 Token
                    </Btn>
                    <Btn tone="danger" onClick={reset} disabled={busy}>
                      <RotateCcw className="h-4 w-4" />
                      重置默认
                    </Btn>
                  </div>

                  {!schema && (
                    <p className="text-sm text-slate-400">
                      正在拉取配置定义……如持续无响应，检查后端服务是否已启动、反向代理 /api 路径是否配置正确。
                    </p>
                  )}

                  <div className="space-y-5">
                    {grouped.map(({ group, fields }) => (
                      <fieldset
                        key={group}
                        className="rounded-lg border border-slate-800 bg-slate-950 p-4"
                      >
                        <legend className="px-2 text-sm font-semibold text-sky-400">
                          {group}
                        </legend>
                        <div className="grid gap-4 sm:grid-cols-2">
                          {fields.map((f) => (
                            <Field
                              key={f.key}
                              spec={f}
                              value={values[f.key]}
                              revealed={revealed}
                              onChange={(v) => setField(f.key, v)}
                            />
                          ))}
                        </div>
                      </fieldset>
                    ))}
                  </div>
                </div>
              )}

              {/* ---- 座位页 ---- */}
              {tab === 'seat' && (
                <div className="space-y-4">
                  <p className="text-sm text-slate-400">
                    已自动填入推断的预约日期、当前时刻与默认结束时间；清空则使用后端配置
                    （座位 {num('SEAT_ID')}）。
                  </p>
                  <div className="grid gap-3 sm:grid-cols-4">
                    <VInput
                      label="座位 ID"
                      value={seatForm.seatId}
                      error={seatErr.seatId}
                      placeholder={String(num('SEAT_ID'))}
                      onChange={(v) => setSeatForm((p) => ({ ...p, seatId: v }))}
                    />
                    <VInput
                      label="日期"
                      value={seatForm.date}
                      error={seatErr.date}
                      placeholder="YYYY-MM-DD"
                      onChange={(v) => setSeatForm((p) => ({ ...p, date: v }))}
                    />
                    <VInput
                      label="开始时间"
                      value={seatForm.start}
                      error={seatErr.start}
                      placeholder="HH:MM"
                      onChange={(v) => setSeatForm((p) => ({ ...p, start: v }))}
                    />
                    <VInput
                      label="结束时间"
                      value={seatForm.end}
                      error={seatErr.end}
                      placeholder="HH:MM"
                      onChange={(v) => setSeatForm((p) => ({ ...p, end: v }))}
                    />
                  </div>
                  <div className="flex gap-2">
                    <Btn
                      onClick={() =>
                        guard(async () => {
                          const r = await api.seatQuery({
                            seatId: seatForm.seatId || undefined,
                            date: seatForm.date || undefined,
                          })
                          setOccupancy(r)
                          setResult(r)
                        })
                      }
                      disabled={busy || seatBad}
                    >
                      查询占用
                    </Btn>
                    <Btn
                      tone="primary"
                      onClick={() =>
                        guard(async () => {
                          // 提交结果不是占用列表，清掉上一次查询的列表避免误读
                          setOccupancy(null)
                          const r = await api.seatReserve({
                            seatId: seatForm.seatId || undefined,
                            date: seatForm.date || undefined,
                            startTime: seatForm.start || undefined,
                            endTime: seatForm.end || undefined,
                          })
                          setResult(r)
                          toast(reserveToastKind(r), reserveToastText(r))
                          if (isReserveSuccess(r)) refreshReservationsIfLoaded()
                        })
                      }
                      disabled={busy || seatBad}
                    >
                      提交预约
                    </Btn>
                  </div>
                </div>
              )}

              {/* ---- 会议室页 ---- */}
              {tab === 'meeting' && (
                <div className="space-y-4">
                  <p className="text-sm text-slate-400">
                    已自动填入推断日期与当前时刻；清空则使用后端配置（会议室{' '}
                    {num('MEETING_ROOM_ID')}，主题「{str('MEETING_TITLE')}」）。
                  </p>
                  <div className="grid gap-3 sm:grid-cols-5">
                    <VInput
                      label="会议室 ID"
                      value={meetForm.roomId}
                      error={meetErr.roomId}
                      placeholder={String(num('MEETING_ROOM_ID'))}
                      onChange={(v) => setMeetForm((p) => ({ ...p, roomId: v }))}
                    />
                    <VInput
                      label="日期"
                      value={meetForm.date}
                      error={meetErr.date}
                      placeholder="YYYY-MM-DD"
                      onChange={(v) => setMeetForm((p) => ({ ...p, date: v }))}
                    />
                    <VInput
                      label="开始时间"
                      value={meetForm.start}
                      error={meetErr.start}
                      placeholder="HH:MM"
                      onChange={(v) => setMeetForm((p) => ({ ...p, start: v }))}
                    />
                    <VInput
                      label="结束时间"
                      value={meetForm.end}
                      error={meetErr.end}
                      placeholder="HH:MM"
                      onChange={(v) => setMeetForm((p) => ({ ...p, end: v }))}
                    />
                    <VInput
                      label="粒度(小时,0=不拆)"
                      value={meetForm.granularity}
                      error={meetErr.granularity}
                      placeholder="0"
                      onChange={(v) => setMeetForm((p) => ({ ...p, granularity: v }))}
                    />
                  </div>
                  <div className="flex gap-2">
                    <Btn
                      onClick={() =>
                        guard(async () => {
                          const r = await api.meetingQuery({
                            date: meetForm.date || undefined,
                            startTime: meetForm.start || undefined,
                            endTime: meetForm.end || undefined,
                          })
                          setRooms(r)
                          setResult(r)
                        })
                      }
                      disabled={busy || meetBad}
                    >
                      查可用会议室
                    </Btn>
                    <Btn
                      tone="primary"
                      onClick={() =>
                        guard(async () => {
                          // 提交结果不是可用列表，清掉上一次查询避免误读
                          setRooms(null)
                          const r = await api.meetingReserve({
                            roomId: meetForm.roomId || undefined,
                            date: meetForm.date || undefined,
                            startTime: meetForm.start || undefined,
                            endTime: meetForm.end || undefined,
                            granularity: Number(meetForm.granularity) || 0,
                          })
                          setResult(r)
                          toast(reserveToastKind(r), reserveToastText(r))
                          if (isReserveSuccess(r) || r.partial) refreshReservationsIfLoaded()
                        })
                      }
                      disabled={busy || meetBad}
                    >
                      提交（可分时段）
                    </Btn>
                  </div>
                </div>
              )}

              {/* ---- 预约与任务页 ---- */}
              {tab === 'manage' && (
                <div className="space-y-5">
                  <div>
                    <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-sky-400">
                      <Clock className="h-4 w-4" />
                      后台任务
                    </h3>
                    <div className="space-y-2">
                      {Object.entries(tasks).map(([name, st]) => (
                        <div
                          key={name}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-800 bg-slate-950 px-3 py-2"
                        >
                          <div>
                            <span className="text-sm text-slate-200">
                              {TASK_LABELS[name] ?? name}
                            </span>
                            <span
                              className={`ml-2 rounded px-2 py-0.5 text-xs ${
                                st.running
                                  ? 'bg-emerald-900 text-emerald-300'
                                  : 'bg-slate-800 text-slate-400'
                              }`}
                            >
                              {st.running ? '运行中' : '已停止'}
                            </span>
                            {st.last && (
                              <span className="ml-2 text-xs text-slate-500">
                                最近：{st.last}
                              </span>
                            )}
                          </div>
                          <Btn
                            onClick={() =>
                              guard(async () => {
                                const r = await api.taskControl(
                                  name,
                                  st.running ? 'stop' : 'start',
                                )
                                setTasks(r.tasks)
                              })
                            }
                            disabled={busy}
                          >
                            {st.running ? (
                              <Square className="h-4 w-4" />
                            ) : (
                              <Play className="h-4 w-4" />
                            )}
                            {st.running ? '停止' : '启动'}
                          </Btn>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-sky-400">
                        活跃预约
                        {reservations !== null && (
                          <span className="ml-2 font-normal text-slate-500">
                            共 {reservations.length} 条
                          </span>
                        )}
                      </h3>
                      <div className="flex items-center gap-2">
                        <Btn
                          tone="danger"
                          onClick={cancelAllReservations}
                          disabled={busy || reservations === null || !reservations.some((r) => r.cancelable)}
                        >
                          <Trash2 className="h-4 w-4" />
                          全部取消
                        </Btn>
                        <Btn onClick={loadReservations} disabled={busy}>
                          <RefreshCw className="h-4 w-4" />
                          刷新列表
                        </Btn>
                      </div>
                    </div>
                    <ReservationList
                      items={reservations}
                      disabled={busy}
                      onCancel={(r) =>
                        guard(async () => {
                          const res = await api.cancel(r.reservationId, r.cancelType)
                          setResult(res)
                          toast('ok', `已提交取消：${r.typeLabel} ${r.name ?? r.reservationId}`)
                          // 后端在取消成功后已重查一次，这里再拉一遍保证列表与服务端一致
                          const fresh = await api.reservations()
                          setReservations(fresh.data)
                        })
                      }
                    />
                  </div>
                </div>
              )}

              {occupancy !== null && tab === 'seat' && (
                <div className="mt-4">
                  <OccupancyList result={occupancy} />
                </div>
              )}

              {rooms !== null && tab === 'meeting' && (
                <div className="mt-4">
                  <RoomList
                    result={rooms}
                    onPick={(id) => setMeetForm((p) => ({ ...p, roomId: id }))}
                  />
                </div>
              )}

              {result !== null && tab !== 'config' && (
                <div className="mt-4">
                  <div className="mb-1 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setShowResult((s) => !s)}
                      className="inline-flex items-center gap-1 text-sm font-semibold text-sky-400 hover:text-sky-300"
                    >
                      <ChevronDown
                        className={`h-4 w-4 transition-transform ${showResult ? '' : '-rotate-90'}`}
                      />
                      接口返回
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setResult(null)
                        setOccupancy(null)
                        setRooms(null)
                      }}
                      className="text-xs text-slate-500 hover:text-slate-300"
                    >
                      清空
                    </button>
                  </div>
                  {showResult && (
                    <pre className="lib-scroll max-h-64 overflow-auto rounded-md border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* 右侧日志：sticky + 撑满视口高度，避免下方留大片空白 */}
          <section
            className="sticky top-4 flex flex-col self-start overflow-hidden rounded-lg border border-slate-800 bg-slate-900"
            style={
              showLogs
                ? { height: 'calc(100vh - 2rem)', minHeight: '20rem' }
                : undefined
            }
          >
            <div className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-3">
              <button
                type="button"
                onClick={() => setShowLogs((s) => !s)}
                className="inline-flex items-center gap-1 text-sm font-semibold hover:text-sky-300"
              >
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${showLogs ? '' : '-rotate-90'}`}
                />
                后端日志
                {!showLogs && logs.length > 0 && (
                  <span className="ml-1 font-normal text-slate-500">({logs.length})</span>
                )}
              </button>
              {showLogs && (
                <button
                  type="button"
                  onClick={() => {
                    // 记下水位线再清空：之后的补拉只会带回这条之后的新日志
                    clearMark.current = logs.length > 0
                      ? { ts: logs[logs.length - 1].ts, text: logs[logs.length - 1].text }
                      : null
                    setLogs([])
                  }}
                  className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
                >
                  <Trash2 className="h-3 w-3" />
                  清屏
                </button>
              )}
            </div>
            {showLogs && (
            <div className="lib-scroll min-h-0 flex-1 overflow-y-auto p-3 font-mono text-xs">
              <div ref={logTop} />
              {logs.length === 0 && (
                <p className="text-slate-500">暂无日志。连接建立后会自动推送。</p>
              )}
              {displayLogs.map(({ l, i }) => (
                  <div key={`${l.ts}-${l.level}-${l.text.length}-${i}`} className="mb-1 flex gap-2">
                  <LevelIcon level={l.level} active={busy && i === logs.length - 1} />
                  <div className="min-w-0">
                    <span className="text-slate-600">{l.ts.slice(11)}</span>
                    <span className="ml-2 break-words text-slate-300">{l.text}</span>
                  </div>
                </div>
              ))}
            </div>
            )}
          </section>
        </div>
      </div>
            {/* 外观设置模态框 */}
      {showAppearanceModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50">
          <div className="bg-slate-900 rounded-lg border border-slate-700 p-6 max-w-md w-full mx-4">
            <h2 className="text-lg font-semibold mb-4">外观设置</h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-300 mb-2">Favicon 图标 URL</label>
                <input
                  type="text"
                  value={faviconUrl}
                  onChange={(e) => setFaviconUrl(e.target.value)}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-sky-500"
                  placeholder="../image/吉大校徽.png"
                />
              </div>
              
              <div>
                <label className="block text-sm text-slate-300 mb-2">背景图片 URL</label>
                <input
                  type="text"
                  value={bgImageUrl}
                  onChange={(e) => setBgImageUrl(e.target.value)}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-sky-500"
                  placeholder="../image/background.png"
                />
              </div>
            </div>
            
            <div className="flex gap-2 mt-6">
              <Btn
                tone="primary"
                onClick={() => {
                  localStorage.setItem('libFaviconUrl', faviconUrl)
                  localStorage.setItem('libBgImageUrl', bgImageUrl)
                  
                  let link = document.querySelector("link[rel='icon']") as HTMLLinkElement
                  if (!link) {
                    link = document.createElement('link')
                    link.rel = 'icon'
                    document.head.appendChild(link)
                  }
                  link.href = faviconUrl
                  
                  document.body.style.backgroundImage = `
                    linear-gradient(rgba(0, 0, 0, 0.5), rgba(0, 0, 0, 0.5)),
                    url('${bgImageUrl}')
                  `
                  document.body.style.backgroundAttachment = 'fixed'
                  document.body.style.backgroundSize = 'cover'
                  document.body.style.backgroundPosition = 'center'
                  
                  toast('ok', '外观设置已保存')
                  setShowAppearanceModal(false)
                }}
              >
                保存设置
              </Btn>
              <Btn
                onClick={() => {
                  setFaviconUrl('../image/吉大校徽.png')
                  setBgImageUrl('../image/background.png')
                  localStorage.removeItem('libFaviconUrl')
                  localStorage.removeItem('libBgImageUrl')
                  
                  let link = document.querySelector("link[rel='icon']") as HTMLLinkElement
                  if (link) link.href = '../image/吉大校徽.png'
                  
                  document.body.style.backgroundImage = `
                    linear-gradient(rgba(0, 0, 0, 0.5), rgba(0, 0, 0, 0.5)),
                    url('../image/background.png')
                  `
                  
                  toast('ok', '已恢复默认外观')
                  setShowAppearanceModal(false)
                }}
              >
                重置默认
              </Btn>
              <Btn onClick={() => setShowAppearanceModal(false)}>
                关闭
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
function Palette(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="1" fill="currentColor" />
      <circle cx="19" cy="5" r="1" fill="currentColor" />
      <circle cx="5" cy="19" r="1" fill="currentColor" />
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
    </Svg>
  )
}

/** 状态徽章配色：待签到用琥珀色提示「还需到馆」，进行中用绿色。 */
function StatusBadge({ status, label }: { status: string | null; label: string | null }) {
  const tone =
    status === 'RESERVED'
      ? 'bg-amber-900/60 text-amber-300'
      : status === 'IN_USE'
        ? 'bg-emerald-900/60 text-emerald-300'
        : 'bg-slate-800 text-slate-400'
  return (
    <span className={`rounded px-2 py-0.5 text-xs ${tone}`}>{label ?? status ?? '?'}</span>
  )
}

/**
 * 活跃预约列表：每行只显示取消决策真正需要的信息——
 * 类型、名称位置、时间、状态，编号收进小字。类型由后端算好的
 * cancelType 决定，不再让用户手选，避免座位/会议室端点选错。
 */
function ReservationList({
  items,
  onCancel,
  disabled,
}: {
  items: Reservation[] | null
  onCancel: (r: Reservation) => void
  disabled?: boolean
}) {
  if (items === null) {
    return (
      <p className="rounded-md border border-slate-800 bg-slate-950 px-3 py-4 text-sm text-slate-500">
        点击「刷新列表」加载当前预约。
      </p>
    )
  }
  if (items.length === 0) {
    return (
      <p className="rounded-md border border-slate-800 bg-slate-950 px-3 py-4 text-sm text-slate-500">
        当前没有活跃预约。
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {items.map((r) => (
        <li
          key={String(r.reservationId)}
          className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-slate-800 bg-slate-950 px-3 py-2"
        >
          <span className="text-xs text-slate-600">[{r.index}]</span>
          {r.group === 'SEAT' ? (
            <Armchair className="h-4 w-4 shrink-0 text-sky-400" />
          ) : r.group === 'MEETING_ROOM' ? (
            <Users className="h-4 w-4 shrink-0 text-violet-400" />
          ) : (
            <Info className="h-4 w-4 shrink-0 text-slate-400" />
          )}

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-100">
                {r.typeLabel} {r.name ?? '?'}
              </span>
              <StatusBadge status={r.status} label={r.statusLabel} />
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-slate-400">
              <span>{r.time ?? '时间未知'}</span>
              {r.location && <span className="text-slate-500">{r.location}</span>}
              {r.meetingTitle && <span className="text-slate-500">主题：{r.meetingTitle}</span>}
              <span className="text-slate-600">ID {String(r.reservationId)}</span>
            </div>
          </div>

          <Btn
            tone="danger"
            disabled={disabled || !r.cancelable}
            onClick={() => {
              // 取消不可撤销，照原脚本保留一次确认
              const what = `${r.typeLabel} ${r.name ?? ''}（${r.time ?? '时间未知'}）`
              if (window.confirm(`确认取消该预约？\n\n${what}\nID ${r.reservationId}`)) {
                onCancel(r)
              }
            }}
          >
            取消
          </Btn>
        </li>
      ))}
    </ul>
  )
}

