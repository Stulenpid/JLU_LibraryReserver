"""
吉林大学图书馆预约助手 —— 后端服务

把原 test.py 的配置区全局变量提升为「可远程读写的运行时配置」，
前端通过 /config/schema 自动渲染表单，PUT /config 后热生效并落盘。

启动：
    pip install fastapi uvicorn requests
    ADMIN_KEY=xxx python3 -m uvicorn backend:app --host 127.0.0.1 --port 8010
"""

import os
import re
import json
import time
import queue
import base64
import smtplib
import asyncio
import threading
from contextlib import asynccontextmanager
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from concurrent.futures import ThreadPoolExecutor,as_completed

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from zoneinfo import ZoneInfo



# ============================================================
# 零、.env 加载：必须在读取任何环境变量之前完成
#     优先用 python-dotenv；未安装时退化为内置极简解析器
# ============================================================
_executor = ThreadPoolExecutor(max_workers=12)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_LOADED_FROM: Optional[str] = None

try:
    LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=8))
def now_local() -> datetime:
    """统一的「当前北京时间」入口。

    容器基于 Debian，系统时区默认 UTC，裸 datetime.now() 比实际早 8 小时，
    会让 HH:MM 定时比对和 DATE_CUTOFF_HOUR 判断整体错位一天。
    全文件所有「现在几点」的判断一律走这里。
    """
    return datetime.now(LOCAL_TZ)

def _fallback_load_env(path: str, override: bool = False) -> int:
    """支持 KEY=VALUE、# 注释、export 前缀、引号包裹、\\n 转义。"""
    count = 0
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if not key:
                continue
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                quote = val[0]
                val = val[1:-1]
                if quote == '"':
                    val = val.replace("\\n", "\n").replace('\\"', '"')
            else:
                val = val.split(" #", 1)[0].rstrip()  # 行尾注释仅在无引号时剥离
            if override or key not in os.environ:
                os.environ[key] = val
                count += 1
    return count


def load_env_file() -> None:
    """依次尝试 ENV_FILE 指定路径、backend/.env、当前工作目录 .env。"""
    global _ENV_LOADED_FROM
    candidates = [
        os.environ.get("ENV_FILE"),
        os.path.join(BASE_DIR, ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            from dotenv import load_dotenv  # type: ignore
            load_dotenv(path, override=False)
            _ENV_LOADED_FROM = f"{path}（python-dotenv）"
        except ImportError:
            n = _fallback_load_env(path)
            _ENV_LOADED_FROM = f"{path}（内置解析，注入 {n} 项）"
        except Exception as e:
            print(f"[warn] .env 读取失败 {path}: {e}", flush=True)
            continue
        return


load_env_file()

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
CONFIG_PATH = os.environ.get(
    "CONFIG_PATH", os.path.join(BASE_DIR, "config.json"))


# ============================================================
# 一、配置定义：原脚本配置区的每个全局变量在这里登记一次
#     type 决定前端控件；group 决定分组；secret 表示读取时脱敏
# ============================================================

CONFIG_SCHEMA: List[Dict[str, Any]] = [
    # ---- 凭证 ----
    {"key": "TOKEN", "label": "Token", "type": "string", "group": "凭证",
     "default": "", "secret": True,
     "help": "形如 junyue-server <base64>，抓包获取；失效后在此更新即可，无需重启"},
    {"key": "BASE_URL", "label": "接口基址", "type": "string", "group": "凭证",
     "default": "https://libseat.jlu.edu.cn"},

    # ---- 座位预约 ----
    {"key": "SEAT_ID", "label": "座位 ID", "type": "int", "group": "座位预约",
     "default": 3421, "min": 1},
    {"key": "START_TIME", "label": "开始时间", "type": "time", "group": "座位预约",
     "default": "18:00"},
    {"key": "END_TIME", "label": "结束时间", "type": "time", "group": "座位预约",
     "default": "22:00"},

    # ---- 会议室预约 ----
    {"key": "MEETING_ROOM_ID", "label": "会议室 ID", "type": "int", "group": "会议室预约",
     "default": 30, "min": 1},
    {"key": "MEETING_START_TIME", "label": "开始时间", "type": "time", "group": "会议室预约",
     "default": "13:00"},
    {"key": "MEETING_END_TIME", "label": "结束时间", "type": "time", "group": "会议室预约",
     "default": "17:00"},
    {"key": "MEETING_TITLE", "label": "会议主题", "type": "string", "group": "会议室预约",
     "default": "小组讨论"},
    {"key": "MEETING_CONTENT", "label": "会议内容", "type": "string", "group": "会议室预约",
     "default": "无"},
    {"key": "MEETING_ATTENDEES", "label": "参会人 ID", "type": "int_list", "group": "会议室预约",
     "default": [24545, 25420], "help": "逗号分隔的用户 ID"},

    # ---- 时间策略 ----
    {"key": "WAIT_UNTIL", "label": "等待至", "type": "datetime_or_null", "group": "时间策略",
     "default": None, "help": "如 2026-06-18 08:00:00；留空表示立即执行"},
    {"key": "DATE_CUTOFF_HOUR", "label": "日期分界小时", "type": "int", "group": "时间策略",
     "default": 21, "min": 0, "max": 23,
     "help": "到达此小时（含）后默认预约明天，之前预约今天"},
    {"key": "DEFAULT_MANUAL_END_TIME", "label": "默认结束时间", "type": "time", "group": "时间策略",
     "default": "21:00"},

    # ---- 定时任务 ----
    {"key": "SCHEDULER_TRIGGER_TIME", "label": "会议室定时触发", "type": "time", "group": "定时任务",
     "default": "21:00"},
    {"key": "SEAT_SCHEDULER_TRIGGER_TIME", "label": "座位定时触发", "type": "time", "group": "定时任务",
     "default": "21:01"},
    {"key": "SLOT_SUBMIT_INTERVAL", "label": "分段提交间隔(秒)", "type": "float", "group": "定时任务",
     "default": 0.5, "min": 0},
    {"key": "SLOT_RETRY_DELAY", "label": "补发等待(秒)", "type": "float", "group": "定时任务",
     "default": 1.0, "min": 0},
    {"key": "SLOT_MAX_ATTEMPTS", "label": "单段最多提交次数", "type": "int", "group": "定时任务",
     "default": 2, "min": 1, "max": 5},
    {"key": "GUARD_POLL_INTERVAL", "label": "守护轮询间隔(秒)", "type": "int", "group": "定时任务",
     "default": 600, "min": 30},
    {"key": "TOKEN_MONITOR_INTERVAL_MIN", "label": "Token 检测间隔(分)", "type": "int", "group": "定时任务",
     "default": 10, "min": 1},

    # ---- 邮件 ----
    {"key": "EMAIL_SENDER", "label": "发件人", "type": "string", "group": "邮件提醒",
     "default": ""},
    {"key": "EMAIL_RECEIVER", "label": "收件人", "type": "string", "group": "邮件提醒",
     "default": ""},
    {"key": "EMAIL_SMTP_AUTHCODE", "label": "SMTP 授权码", "type": "string", "group": "邮件提醒",
     "default": "", "secret": True},
    {"key": "EMAIL_SMTP_HOST", "label": "SMTP 服务器", "type": "string", "group": "邮件提醒",
     "default": "smtp.qq.com"},
    {"key": "EMAIL_SMTP_PORT", "label": "SMTP 端口", "type": "int", "group": "邮件提醒",
     "default": 465},
]

SCHEMA_BY_KEY = {item["key"]: item for item in CONFIG_SCHEMA}
SECRET_KEYS = {i["key"] for i in CONFIG_SCHEMA if i.get("secret")}


class ConfigStore:
    """线程安全的配置容器，负责校验、落盘、热生效。"""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {i["key"]: i["default"] for i in CONFIG_SCHEMA}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            # 首次启动允许用环境变量注入敏感项，避免明文写死
            for k in ("TOKEN", "EMAIL_SENDER", "EMAIL_RECEIVER", "EMAIL_SMTP_AUTHCODE"):
                v = os.environ.get(f"LIB_{k}")
                if v:
                    self._data[k] = v
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k in SCHEMA_BY_KEY:
                    self._data[k] = v
        except Exception as e:
            log("err", f"配置文件读取失败，使用默认值：{e}")

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data[key]

    def snapshot(self, mask: bool = True) -> Dict[str, Any]:
        with self._lock:
            out = dict(self._data)
        if mask:
            for k in SECRET_KEYS:
                if out.get(k):
                    s = str(out[k])
                    out[k] = s[:6] + "******" + s[-4:] if len(s) > 12 else "******"
        return out

    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.get("TOKEN"),
            "Content-Type": "application/json",
            "space": "LIBRARY",
        }

    # ---- 校验 ----
    @staticmethod
    def _coerce(spec: Dict[str, Any], raw: Any) -> Any:
        t = spec["type"]
        key = spec["key"]
        if t == "string":
            return "" if raw is None else str(raw)
        if t == "int":
            try:
                v = int(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{key} 需为整数")
            if "min" in spec and v < spec["min"]:
                raise ValueError(f"{key} 不得小于 {spec['min']}")
            if "max" in spec and v > spec["max"]:
                raise ValueError(f"{key} 不得大于 {spec['max']}")
            return v
        if t == "float":
            try:
                v = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{key} 需为数字")
            if "min" in spec and v < spec["min"]:
                raise ValueError(f"{key} 不得小于 {spec['min']}")
            return v
        if t == "time":
            s = str(raw).strip()
            try:
                datetime.strptime(s, "%H:%M")
            except ValueError:
                raise ValueError(f"{key} 需为 HH:MM 格式")
            return s
        if t == "datetime_or_null":
            if raw in (None, "", "null"):
                return None
            s = str(raw).strip()
            try:
                datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise ValueError(f"{key} 需为 YYYY-MM-DD HH:MM:SS 或留空")
            return s
        if t == "int_list":
            if isinstance(raw, str):
                parts = [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]
            elif isinstance(raw, list):
                parts = raw
            else:
                raise ValueError(f"{key} 需为 ID 列表")
            try:
                return [int(p) for p in parts]
            except (TypeError, ValueError):
                raise ValueError(f"{key} 中含非整数项")
        raise ValueError(f"{key} 类型未知")

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """部分更新。secret 字段传入脱敏占位符时视为不修改。"""
        cleaned: Dict[str, Any] = {}
        for k, raw in patch.items():
            spec = SCHEMA_BY_KEY.get(k)
            if not spec:
                continue  # 忽略未知字段，避免前端旧版本写入垃圾
            if k in SECRET_KEYS and isinstance(raw, str) and "******" in raw:
                continue
            cleaned[k] = self._coerce(spec, raw)

        with self._lock:
            changed = {k: v for k, v in cleaned.items() if self._data.get(k) != v}
            self._data.update(cleaned)
            self._persist()
        for k in changed:
            shown = "******" if k in SECRET_KEYS else changed[k]
            log("info", f"配置更新：{k} = {shown}")
        return changed

    def reset(self) -> None:
        with self._lock:
            self._data = {i["key"]: i["default"] for i in CONFIG_SCHEMA}
            self._persist()
        log("warn", "配置已重置为默认值")


# ============================================================
# 二、日志总线：替代原脚本 ok/err/warn/info/prog，推给前端 SSE
# ============================================================

_log_lock = threading.Lock()
_log_buffer: List[Dict[str, str]] = []
_log_subscribers: List["queue.Queue[Dict[str, str]]"] = []


def log(level: str, text: str) -> None:
    entry = {
        "ts": now_local().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level if level in ("ok", "err", "warn", "info", "prog") else "info",
        "text": text,
    }
    with _log_lock:
        _log_buffer.append(entry)
        del _log_buffer[:-500]
        subs = list(_log_subscribers)
    print(f"[{entry['ts']}] [{entry['level']}] {text}", flush=True)
    # 订阅者是 (事件循环, asyncio.Queue)。log() 多数从后台线程调用，
    # 不能直接碰 asyncio.Queue，必须经 call_soon_threadsafe 回到循环里投递。
    for loop, q in subs:
        try:
            loop.call_soon_threadsafe(_offer_log, q, entry)
        except RuntimeError:
            # 循环已关闭（进程收尾阶段），忽略即可
            pass


def _offer_log(q: "asyncio.Queue", entry: Dict[str, str]) -> None:
    """在事件循环线程内投递；队列满时丢最老的一条，保证永不阻塞。"""
    if q.full():
        try:
            q.get_nowait()
        except Exception:
            pass
    try:
        q.put_nowait(entry)
    except Exception:
        pass

# ============================================================
# 三、业务逻辑：全部从 cfg 实时取值，改配置立刻影响下一次调用
# ============================================================

cfg = ConfigStore(CONFIG_PATH)


def get_default_date() -> str:
    now = now_local()
    offset = 1 if now.hour >= cfg.get("DATE_CUTOFF_HOUR") else 0
    return (now + timedelta(days=offset)).strftime("%Y-%m-%d")


def now_hm() -> str:
    return now_local().strftime("%H:%M")


def manual_defaults() -> Dict[str, str]:
    """手动预约的默认日期与起止时间。

    日期用 get_default_date() 推断（过了 DATE_CUTOFF_HOUR 就是明天），
    开始时间取当前时刻，结束时间取 DEFAULT_MANUAL_END_TIME（默认 21:00）。
    这正是原脚本手动模式的取值方式：定时任务才用 START_TIME/END_TIME，
    手动提交是「从现在坐到闭馆」。

    一个边界：若当前时刻已晚于默认结束时间（或日期已滚到明天），
    「现在 ~ 21:00」是个空区间，此时退回配置里的 START_TIME/END_TIME，
    否则前端一打开就是一组红框。
    """
    date = get_default_date()
    end = str(cfg.get("DEFAULT_MANUAL_END_TIME"))
    start = now_hm()
    if date != now_local().strftime("%Y-%m-%d") or start >= end:
        start = str(cfg.get("START_TIME"))
        end = str(cfg.get("END_TIME"))
    return {"date": date, "startTime": start, "endTime": end}


_RE_DATE_STRICT = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_TIME_STRICT = re.compile(r"^(\d{1,2}):(\d{2})$")


def need_date(raw: Any, field: str = "date") -> str:
    """校验 YYYY-MM-DD，失败抛 400 并说明原因（前端据此标红并提示）。"""
    s = str(raw).strip()
    if not _RE_DATE_STRICT.match(s):
        raise HTTPException(400, f"{field} 需为 YYYY-MM-DD 格式，收到「{s}」")
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, f"{field} 不是有效日期：「{s}」")
    return s


def need_time(raw: Any, field: str = "time") -> str:
    """校验 HH:MM，统一补零输出，避免上游收到 9:00 这种不规范写法。"""
    s = str(raw).strip()
    m = _RE_TIME_STRICT.match(s)
    if not m:
        raise HTTPException(400, f"{field} 需为 HH:MM 格式，收到「{s}」")
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        raise HTTPException(400, f"{field} 时刻超出范围：「{s}」")
    return f"{hh:02d}:{mm:02d}"


def need_range(date: str, start: str, end: str) -> None:
    if end <= start:
        raise HTTPException(400, f"结束时间需晚于开始时间（{date} {start} ~ {end}）")


# 日期：2026年9月9日 / 2026-09-09 / 2026/9/9 / 9月9日 / 09-09
_RE_DATE_CN_FULL = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?")
_RE_DATE_CN_MD = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日?")
_RE_DATE_ISO = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
_RE_DATE_MD = re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})(?!\d)")
# 时间：取字符串里第一个 HH:MM，即时间段的开始时间，可含秒
_RE_TIME = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")


def parse_start_dt(time_str: str) -> Optional[datetime]:
    """从活跃列表的 time 字段解析**开始时间**。

    上游实际返回的是中文格式 `2026年9月9日 18:00-22:00`，另外还见过
    `2026-09-09 18:00~22:00`、`18:00 - 22:00` 等写法。早前版本枚举
    strptime 格式表，既漏了「年月日」，也把 `-` 分隔符写成必须两侧带空格，
    于是整条解析失败、该预约被 skip_ids 永久跳过，等于完全没被守护。
    同时残串会触发「无年份月日」的 DeprecationWarning。

    改成正则分别提取日期和第一个 HH:MM 再组装，不再依赖分隔符形态：
    时间段两端都是 HH:MM，取第一个即开始时间，无需先切左右半段。
    缺日期按今天补（等价原脚本 %H:%M 分支），缺年份按今年补。
    解析不出返回 None，排序时沉到最后。
    """
    if not time_str:
        return None
    s = str(time_str).strip()
    if not s:
        return None

    now = now_local()
    year = month = day = None

    m = _RE_DATE_CN_FULL.search(s)
    if m:
        year, month, day = (int(g) for g in m.groups())
    else:
        m = _RE_DATE_ISO.search(s)
        if m:
            year, month, day = (int(g) for g in m.groups())
        else:
            m = _RE_DATE_CN_MD.search(s)
            if m:
                year = now.year
                month, day = int(m.group(1)), int(m.group(2))
            else:
                # 纯数字 M-D 容易和 HH:MM 混淆，先把时间整体摘掉再找日期
                stripped = _RE_TIME.sub(" ", s)
                m = _RE_DATE_MD.search(stripped)
                if m:
                    year = now.year
                    month, day = int(m.group(1)), int(m.group(2))

    tm = _RE_TIME.search(s)
    if not tm:
        return None
    hour, minute = int(tm.group(1)), int(tm.group(2))
    second = int(tm.group(3)) if tm.group(3) else 0

    if month is None:
        year, month, day = now.year, now.month, now.day

    try:
        return datetime(year, month, day, hour, minute, second,tzinfo=LOCAL_TZ)
    except ValueError:
        # 例如闰日缺年份造成的非法组合，宁可返回 None 也不猜
        return None


def sort_by_start(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按开始时间升序，无法解析的排最后。原脚本各处排序都是这个规则。"""
    return sorted(records,
                  key=lambda r: parse_start_dt(r.get("time", "")) or datetime.max)


def reservation_type_of(record: Dict[str, Any]) -> str:
    """取记录的类型，缺失时回退 MEETING_ROOM。

    回退值照原脚本 `chosen.get("type", "MEETING_ROOM")`。这个默认值很关键：
    座位取消走 POST /v1/seat-reservations/...，会议室走 PUT /v1/meeting-reservations/...，
    类型猜错就是打到错误端点。早前版本默认成 seat，是与原脚本相反的。
    """
    t = record.get("type")
    return t if t in ("SEAT", "MEETING_ROOM") else "MEETING_ROOM"


def parse_user_id_from_token(token: str) -> Optional[str]:
    """Token 形如 `junyue-server <base64>`，base64 解出 `1:11768:<hash>`。

    用户 ID 是**第二段**（索引 1），第一段是版本号之类的固定值。
    早前版本误取第一段，导致请求打到 /v1/users/1/detail 被上游回 400，
    表现为「Token 验证失败」——与 Token 本身是否有效无关。
    """
    try:
        parts = token.split(" ", 1)
        if len(parts) != 2:
            return None
        payload = parts[1].strip()
        payload += "=" * (-len(payload) % 4)
        decoded = base64.b64decode(payload).decode("utf-8")
        segments = decoded.split(":")
        if len(segments) >= 2:
            return str(int(segments[1]))  # int() 顺带校验是纯数字
    except Exception:
        pass
    return None


# requests 中代表「网络/链路问题」而非「凭证问题」的异常
_NETWORK_EXC = (
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ReadTimeout,
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)


def raw_request(method: str, path: str, **kw) -> requests.Response:
    """只发请求、不做任何判定，把原始 Response 交给调用方。"""
    url = f"{cfg.get('BASE_URL')}{path}"
    kw.setdefault("timeout", 10)
    return requests.request(method, url, headers=cfg.headers(), **kw)


def api_call(method: str, path: str, **kw) -> Any:
    """提交/取消类接口用：语义完全照原脚本。

    原脚本对提交接口是 `resp.json()` 后直接把 body 交给 print_result，
    **不看状态码**——因为上游的业务失败（时段冲突、已有预约）会带着
    code/message 回来，状态码可能是 200 也可能是 4xx。若在这里抛异常，
    那条最有用的 message 就丢了，前端只剩一句「上游错误」。

    返回 None 只代表**没拿到任何响应**（网络异常/超时/非 JSON），这是
    submit_with_retry 判断是否补发的唯一依据，不能与业务失败混为一谈。
    """
    try:
        resp = raw_request(method, path, **kw)
    except Exception as e:
        log("err", f"请求失败：{e}")
        return None
    try:
        data = resp.json()
    except ValueError:
        snippet = (resp.text or "")[:300].replace("\n", " ")
        log("err", f"上游返回非 JSON（HTTP {resp.status_code}）：{snippet}")
        return None
    if resp.status_code >= 400:
        # 状态码异常但有 JSON body：仍交给上层解读，只补一条提示便于排查
        log("warn", f"上游状态码 {resp.status_code}，按返回体内容解读")
    log("info", f"接口返回：{json.dumps(data, ensure_ascii=False)[:600]}")
    return data


def api_request(method: str, path: str, **kw) -> Any:
    """查询类接口用：非 2xx 显式报错。

    与 api_call 分开是有意的：原脚本查询失败时返回空列表并打日志，
    但 Web 端返回空列表会被用户读成「真的没有记录」，所以这里改成报错。
    这是相对原脚本有意的偏离，仅限查询，不影响提交语义。
    """
    resp = raw_request(method, path, **kw)
    if resp.status_code in (401, 403):
        raise HTTPException(401, f"Token 已过期或无效（状态码：{resp.status_code}）")
    try:
        data = resp.json()
    except ValueError:
        snippet = (resp.text or "")[:200].replace("\n", " ")
        raise HTTPException(
            502, f"上游返回非 JSON（HTTP {resp.status_code}）：{snippet}")
    if resp.status_code >= 400:
        msg = data.get("message") if isinstance(data, dict) else None
        raise HTTPException(502, f"上游错误 HTTP {resp.status_code}：{msg or data}")
    return data


def check_token() -> Dict[str, Any]:
    """严格对齐原脚本 check_token 的判定阶梯。

    返回 valid=True/False；networkError=True 表示本轮不足以判定失效，
    调用方（后台监控）必须跳过、不发邮件，避免网络抖动造成误报。
    """
    token = cfg.get("TOKEN")
    if not token:
        log("err", "Token 为空，请先在配置页填写")
        return {"valid": False, "message": "Token 未配置"}

    user_id = parse_user_id_from_token(token)
    if not user_id:
        log("err", "Token 格式无法解析，请检查配置")
        return {"valid": False, "message": "Token 格式无法解析"}

    try:
        resp = raw_request("GET", f"/v1/users/{user_id}/detail")
    except _NETWORK_EXC as e:
        log("warn", f"Token 验证网络异常，不判定失效：{e}")
        return {"valid": False, "networkError": True,
                "message": f"网络异常：{e}", "userId": user_id}
    except Exception as e:
        # 与原脚本一致：未识别异常保守归为网络问题，绝不误报失效
        log("warn", f"Token 验证遇未知异常，保守跳过：{e}")
        return {"valid": False, "networkError": True,
                "message": str(e), "userId": user_id}

    status = resp.status_code

    if status in (401, 403):
        log("err", f"Token 已过期或无效（状态码：{status}）")
        return {"valid": False, "status": status,
                "message": f"Token 已过期或无效（HTTP {status}）", "userId": user_id}

    if status != 200:
        # 非 200 且非 401/403：几乎都是请求本身有问题（URL、user_id、header），
        # 而不是凭证失效。这类一律标 networkError 以抑制邮件，只记日志，
        # 否则一个拼错的路径会每 10 分钟发一封假的「Token 已失效」。
        snippet = (resp.text or "")[:300].replace("\n", " ")
        log("err", f"Token 验证失败（状态码：{status}），不判定失效")
        log("info", f"请求 URL：{cfg.get('BASE_URL')}/v1/users/{user_id}/detail")
        log("info", f"原始响应：{snippet}")
        return {"valid": False, "status": status,
                "networkError": True,
                "message": f"验证失败（HTTP {status}）", "userId": user_id,
                "raw": snippet}

    try:
        data = resp.json()
    except ValueError:
        snippet = (resp.text or "")[:200].replace("\n", " ")
        log("warn", f"Token 验证响应非 JSON，不判定失效：{snippet}")
        return {"valid": False, "networkError": True,
                "message": "响应非 JSON（疑似维护页）", "userId": user_id}

    nickname = data.get("nickname") if isinstance(data, dict) else None
    if not nickname:
        msg = data.get("message", "无法获取用户信息") if isinstance(data, dict) else "响应格式异常"
        code = data.get("code") if isinstance(data, dict) else None
        log("err", f"Token 无效：{msg}" + (f"（code={code}）" if code else ""))
        log("info", f"原始响应：{str(data)[:300]}")
        return {"valid": False, "status": 200, "code": code,
                "message": msg, "userId": user_id, "raw": data}

    log("ok", f"Token 有效，当前用户：{nickname}（ID: {user_id}）")
    return {"valid": True, "userId": user_id, "nickname": nickname,
            "detail": data if isinstance(data, dict) else None}


# ---- 返回体解读：对齐原脚本 print_result / print_cancel_result ----

_STATUS_LABELS = {
    "AUTO_APPROVED": "自动审核通过",
    "PENDING": "等待审核",
    "APPROVED": "审核通过",
    "RESERVED": "已预约",
    "CANCELED": "已取消",
}


def unwrap_list(data: Any) -> List[Dict[str, Any]]:
    """上游列表接口有三种壳：裸数组、{content:[]}、{data:[]}，全都兜住。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("content", "data", "records", "list"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


def log_submit_result(data: Any, kind: str) -> tuple:
    """把提交结果逐字段打进日志，并返回 (是否真正成功, 给用户看的一句话摘要)。

    原脚本以「同时存在 id 和 status」判定成功，这里保持一致：
    失败时上游同样回 HTTP 200，只是 body 换成 code/message——这正是前端
    「点提交就弹成功」问题的根源：早前前端只要没抛异常就当成功，完全没看
    这层业务判定。现在把这里算好的结论（success + message）原样交给
    /seat/reserve、/meeting/reserve 塞进响应体，前端据此弹提示，
    不再凡是 HTTP 200 就报喜。
    """
    if data is None:
        msg = f"{kind}预约失败：无返回数据（可能网络超时，请检查是否已提交成功）"
        log("err", msg)
        return False, msg
    if not isinstance(data, dict):
        msg = f"{kind}预约失败：返回格式异常 {str(data)[:200]}"
        log("err", msg)
        return False, msg

    if data.get("id") and data.get("status"):
        status = data["status"]
        log("ok", f"{kind}预约成功！编号 {data['id']}")
        log("info", f"    时间：{data.get('time', '?')}")
        seat = data.get("seat")
        if isinstance(seat, dict):
            log("info", f"    座位：{seat.get('name', '?')}  {seat.get('parentNamePath', '')}")
        room = data.get("meetingRoom")
        if isinstance(room, dict):
            log("info", f"    会议室：{room.get('name', '?')}  {room.get('parentNamePath', '')}")
            if data.get("meetingTitle"):
                log("info", f"    主题：{data['meetingTitle']}")
        log("info", f"    状态：{_STATUS_LABELS.get(status, status)}")
        msg = f"{kind}预约成功，编号 {data['id']}，状态：{_STATUS_LABELS.get(status, status)}"
        return True, msg

    code = str(data.get("code", "") or "")
    message = data.get("message", "未知错误")
    if code == "reservation.user_has_other_reservation":
        hint = "账号在该时段已有其他预约，请先取消后再预约"
    elif "time" in code.lower() or "conflict" in code.lower():
        hint = "时间段冲突"
    else:
        hint = "时间段已被占用 / Token 过期 / ID 有误"
    log("err", f"{kind}预约失败：{message}" + (f"（code={code}）" if code else ""))
    log("info", f"    可能原因：{hint}")
    msg = f"{kind}预约失败：{message}（{hint}）"
    return False, msg


def log_cancel_result(data: Any) -> bool:
    if not isinstance(data, dict):
        log("err", "取消失败：无返回数据")
        return False
    if data.get("status") == "CANCELED":
        log("ok", f"取消成功！预约ID：{data.get('id', '?')}")
        log("info", f"    时间：{data.get('startTime') or data.get('time', '?')}")
        return True
    code = data.get("code", "")
    log("err", f"取消失败：{data.get('message', '未知错误')}"
               + (f"（code={code}）" if code else ""))
    return False


def cancel_reservation_by_type(reservation_type: str, reservation_id: Any) -> Any:
    """按类型取消，对齐原脚本 cancel_reservation_by_type。

    上游两类接口的动词不一致：座位 POST，会议室 PUT。抽成函数是因为守护线程
    的自动取消和 /cancel 接口都要用，两处逻辑必须完全相同。
    """
    if reservation_type == "SEAT":
        return api_call("POST", f"/v1/seat-reservations/{reservation_id}/cancel")
    return api_call("PUT", f"/v1/meeting-reservations/{reservation_id}/cancel")


def get_active_reservations() -> List[Dict[str, Any]]:
    """活跃预约列表。

    路径照原脚本：GET /v1/users/reservations/active，不带查询参数。
    早前版本写成 /v1/reservations?status=RESERVED —— 该路径不存在，稳定 404，
    这就是前端「刷新列表」一直失败的原因。状态过滤在本地做。
    """
    return unwrap_list(api_request("GET", "/v1/users/reservations/active"))


def refresh_active_summary(action: str = "操作") -> List[Dict[str, Any]]:
    """预约或取消成功后拉一次列表并打摘要，等价原脚本 _on_reservation_changed。"""
    log("prog", f"{action}成功，正在刷新预约列表...")
    try:
        records = get_active_reservations()
    except Exception as e:
        log("warn", f"刷新预约列表失败（不影响本次操作结果）：{e}")
        return []
    reserved = [r for r in records
                if r.get("status") == "RESERVED"
                and r.get("type") in ("SEAT", "MEETING_ROOM")]
    if reserved:
        log("info", f"当前活跃预约（RESERVED，共 {len(reserved)} 条）：")
        for r in sort_by_start(reserved):  # 原脚本按开始时间升序打印
            res = r.get("resource") or {}
            label = "座位" if r.get("type") == "SEAT" else "会议室"
            log("info", f"    {label} {res.get('name', '?')}  "
                        f"{r.get('time', '?')}  ID:{r.get('reservationId', '?')}")
    else:
        log("info", "当前无待签到预约")
    # 原脚本 _on_reservation_changed 末尾会唤醒守护线程，让它立刻重新选目标，
    # 不必等满一个轮询周期。取消掉当前守护的那条预约后，这一步是必需的。
    notify_guard_refresh()
    return reserved


def create_seat_reservation(seat_id: int, date: str, start: str, end: str) -> Any:
    payload = {
        "seatId": seat_id,
        "startTime": f"{date} {start}",
        "endTime": f"{date} {end}",
        "needMaterial": False, "scan": False, "use": False,
    }
    log("prog", f"提交座位预约：{json.dumps(payload, ensure_ascii=False)}")
    data = api_call("POST", "/v1/seat-applications", json=payload)
    if data is None:
        return None  # 无响应，交给 submit_with_retry 决定是否补发
    ok, msg = log_submit_result(data, "座位")
    # 把业务层判定结果挂在返回体上，_ 前缀避免和上游真实字段撞名；
    # /seat/reserve 直接读这两个字段回给前端，不用再自己猜一遍成败。
    data["_submitOk"] = ok
    data["_submitMessage"] = msg
    return data


def create_meeting_reservation(room_id: int, date: str, start: str, end: str,
                              title: str, content: str, attendees: List[int]) -> Any:
    payload = {
        "meetingRoomId": room_id,
        "startTime": f"{date} {start}",
        "endTime": f"{date} {end}",
        "meetingTitle": title,
        "meetingContent": content,
        "attendees": attendees,
        "scan": False,
    }
    log("prog", f"提交会议室预约：{json.dumps(payload, ensure_ascii=False)}")
    data = api_call("POST", "/v1/meeting-applications", json=payload)
    if data is None:
        return None
    ok, msg = log_submit_result(data, "会议室")
    data["_submitOk"] = ok
    data["_submitMessage"] = msg
    return data


def split_time_slots(date: str, start_hm: str, end_hm: str, granularity: int) -> List[tuple]:
    s = datetime.strptime(f"{date} {start_hm}", "%Y-%m-%d %H:%M")
    e = datetime.strptime(f"{date} {end_hm}", "%Y-%m-%d %H:%M")
    if e <= s:
        raise HTTPException(400, "结束时间需晚于开始时间")
    slots, cur = [], s
    step = timedelta(hours=granularity)
    while cur < e:
        nxt = min(cur + step, e)
        slots.append((cur.strftime("%H:%M"), nxt.strftime("%H:%M")))
        cur = nxt
    return slots


def submit_with_retry(submit, verify=None) -> Any:
    """仅在「完全没拿到响应」时补发，严格对齐原脚本 _submit_slot_with_retry。

    原脚本的补发条件写得很明确：拿到 dict（无论业务成功或失败）就直接返回、
    不再补发；只有 None（超时/高负载导致无返回）才等待后重试。
    早前版本用 try/except 包住提交，把「时段冲突」这类业务失败也当成无返回
    重发了一遍——抢座场景下可能造成重复占位，是必须避免的。
    """
    attempts = cfg.get("SLOT_MAX_ATTEMPTS")
    delay = cfg.get("SLOT_RETRY_DELAY")
    result = None
    for i in range(1, attempts + 1):
        result = submit()
        if isinstance(result, dict):
            return result  # 有返回即终止，业务成败由上层判定
        if i < attempts:
            log("warn", f"第 {i} 次提交无返回，{delay}s 后补发...")
            time.sleep(delay)
            if verify:
                # 原脚本没有这步。无返回不等于没提交成功，补发前查一遍更稳
                try:
                    existing = verify()
                    if existing:
                        log("ok", "补发前发现该段已生效，跳过重复提交")
                        return existing
                except Exception:
                    pass
    return result

EMAIL_TAG = "【图书馆预约助手】"
EMAIL_LINE = "═" * 40
EMAIL_FOOTER = "此邮件由图书馆预约助手自动发送，请勿回复。"


def _mail_body(intro: str, sections: List[str]) -> str:
    """统一正文骨架：问候 → 分隔线包裹的正文块 → 落款。"""
    parts = ["您好，", "", intro, "", EMAIL_LINE]
    parts.extend(sections)
    parts.extend([EMAIL_LINE, "", EMAIL_FOOTER])
    return "\n".join(parts)

def send_email(subject: str, body: str) -> bool:
    host = cfg.get("EMAIL_SMTP_HOST")
    sender = cfg.get("EMAIL_SENDER")
    receiver = cfg.get("EMAIL_RECEIVER")
    code = cfg.get("EMAIL_SMTP_AUTHCODE")
    if not all([host, sender, receiver, code]):
        log("warn", "邮件配置不完整，跳过发送")
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = sender
        msg["To"] = receiver
        with smtplib.SMTP_SSL(host, cfg.get("EMAIL_SMTP_PORT"), timeout=15) as s:
            s.login(sender, code)
            s.sendmail(sender, [receiver], msg.as_string())
        log("ok", f"提醒邮件已发送至 {receiver}")
        return True
    except Exception as e:
        log("err", f"邮件发送失败：{e}")
        return False

def _send_seat_report_email(date: str, seat_id: int, start: str, end: str,
                            success: bool, detail: str = "") -> bool:
    icon = "✅ 成功" if success else "❌ 失败"
    body = _mail_body(
        f"定时座位预约已于 {now_local():%Y-%m-%d %H:%M:%S} 执行完毕。",
        [
            f"预约日期：{date}",
            f"座位编号：{seat_id}",
            f"时间区间：{start} - {end}",
            f"预约结果：{icon}",
            f"接口反馈：{detail or '无'}",
        ],
    )
    return send_email(f"{EMAIL_TAG}定时座位预约汇报｜{icon}", body)

def _send_slot_report_email(date: str, results: List[tuple]) -> bool:
    """分段预约汇总。results 为 [(start, end, ok_flag, msg), ...]"""
    total = len(results)
    ok_n = sum(1 for r in results if r[2])
    fail_n = total - ok_n
    if fail_n == 0:
        icon = "✅ 全部成功"
    elif ok_n == 0:
        icon = "❌ 全部失败"
    else:
        icon = "⚠️ 部分成功"

    sections = [
        f"预约日期：{date}",
        f"分段总数：{total}",
        f"成功 {ok_n} 段，失败 {fail_n} 段",
        "",
        "分段详情：",
    ]
    for i, (s, e, flag, msg) in enumerate(results, 1):
        mark = "✅" if flag else f"❌ {msg}"
        sections.append(f"  [{i}/{total}] {s} - {e}  {mark}")

    body = _mail_body(
        f"分段预约已于 {now_local():%Y-%m-%d %H:%M:%S} 执行完毕。", sections)
    return send_email(f"{EMAIL_TAG}分段预约汇报｜{icon}", body)


def _send_token_expired_email(extra_msg: str = "") -> bool:
    body = _mail_body(
        "检测到图书馆预约助手的 Token 已失效。",
        [
            f"失效时间：{now_local():%Y-%m-%d %H:%M:%S}",
            f"附加信息：{extra_msg or '接口鉴权失败'}",
            "",
            "请在预约面板的「参数配置」页更新 TOKEN 字段，",
            "保存后立即热生效，无需重启服务。",
        ],
    )
    return send_email(f"{EMAIL_TAG}⚠️ Token 已失效，请及时更新", body)

# ============================================================
# 四、后台线程：Token 监控 + 两个定时预约，配置改动后可重启
# ============================================================

_threads: Dict[str, Dict[str, Any]] = {
    "token_monitor": {"on": False, "thread": None, "stop": None, "last": None},
    "checkin_guard": {"on": False, "thread": None, "stop": None, "last": None},
    "meeting_scheduler": {"on": False, "thread": None, "stop": None, "last": None},
    "seat_scheduler": {"on": False, "thread": None, "stop": None, "last": None},
}
_threads_lock = threading.Lock()


def _sleep_interruptible(stop: threading.Event, seconds: float) -> bool:
    return not stop.wait(seconds)


# ------------------------------------------------------------
# 签到守护：移植原脚本 run_guard / do_auto_cancel / _continuous_guard_worker
#
# 规则：预约开始后 10 分钟仍为 RESERVED（未签到）→ 自动取消；15 分钟兜底再查
# 一次。等待期间定期刷新列表，若当前预约消失或出现更早的预约则中止/切换。
# ------------------------------------------------------------

_guard_state: Dict[str, Any] = {
    "running": False,
    "current": None,
    "history": [],
    "refresh_event": None,
}
_guard_state_lock = threading.Lock()


def notify_guard_refresh() -> None:
    """通知守护线程立即放弃等待、重新拉取预约列表。"""
    with _guard_state_lock:
        ev = _guard_state.get("refresh_event")
    if ev:
        ev.set()


def _guard_set_phase(label: str) -> None:
    with _guard_state_lock:
        if _guard_state["current"]:
            _guard_state["current"]["phase"] = label


def _finalize_guard(reservation_id: Any, final_status: str) -> None:
    """把当前守护对象归档进 history，对齐原脚本 _finalize_guard。"""
    with _guard_state_lock:
        current = _guard_state.get("current")
        if current and current.get("reservationId") == reservation_id:
            entry = dict(current)
            entry["phase"] = f"已完成（{final_status}）"
            entry["finishTime"] = now_local().strftime("%H:%M:%S")
            _guard_state["history"].append(entry)
            del _guard_state["history"][:-50]
            _guard_state["current"] = None


def guard_query_active(reservation_id: Any):
    """返回 (本条预约的状态或 None, 所有 RESERVED 中最早的开始时间或 None)。

    第二个值用于抢占判断：如果冒出一条比当前守护对象更早的预约，应当先去守
    护那条。异常时返回 (None, None) 会被上层读成「预约已消失」，所以这里让
    异常向上抛，由调用方区分处理。
    """
    records = get_active_reservations()
    my_status = None
    for r in records:
        if r.get("reservationId") == reservation_id:
            my_status = r.get("status", "UNKNOWN")
            break
    candidates = [r for r in records
                  if r.get("status") == "RESERVED"
                  and r.get("type") in ("SEAT", "MEETING_ROOM")]
    earliest_dt = None
    if candidates:
        earliest_dt = parse_start_dt(sort_by_start(candidates)[0].get("time", ""))
    return my_status, earliest_dt


def get_next_reserved(exclude_ids=None) -> Optional[Dict[str, Any]]:
    """选出最早的一条 RESERVED 预约作为守护目标，对齐原脚本 get_next_reserved。

    exclude_ids 只装「时间解析失败」的异常记录，不排除已守护过的 ID——每轮都
    重新从全量列表里选最早的，这样新预约能立即被接管。
    """
    skip = set(exclude_ids or [])
    try:
        records = get_active_reservations()
    except Exception as e:
        log("warn", f"守护：拉取活跃列表失败，本轮跳过：{e}")
        return None
    candidates = [r for r in records
                  if r.get("status") == "RESERVED"
                  and r.get("type") in ("SEAT", "MEETING_ROOM")
                  and r.get("reservationId") not in skip]
    if not candidates:
        return None
    return sort_by_start(candidates)[0]


def do_auto_cancel(reservation_id: Any, reason: str,
                   reservation_type: str = "SEAT") -> None:
    """守护触发的自动取消，对齐原脚本 do_auto_cancel。"""
    log("warn", f"触发守护：{reason}")
    log("warn", f"正在自动取消预约 {reservation_id}...")
    try:
        data = cancel_reservation_by_type(reservation_type, reservation_id)
    except Exception as e:
        log("err", f"自动取消失败：{e}")
        return
    if isinstance(data, dict) and data.get("status") == "CANCELED":
        log("ok", f"自动取消成功！预约ID：{data.get('id', '?')}")
        refresh_active_summary("自动取消")
    else:
        msg = data.get("message", "未知错误") if isinstance(data, dict) else "无返回数据"
        log("err", f"自动取消失败：{msg}")


def _guard_wait_until(stop: threading.Event, target_dt: datetime,
                      start_dt: datetime, reservation_id: Any,
                      label_name: str, phase_label: str) -> str:
    """等到 target_dt，期间定期（或被外部信号唤醒）刷新列表做两项检查。

    返回 OK / CANCELED / PREEMPTED / STOPPED，语义与原脚本 wait_until_dt 相同。
    单次等待上限是 GUARD_POLL_INTERVAL，这样改配置后最迟一个周期就能生效。
    """
    _guard_set_phase(phase_label)
    with _guard_state_lock:
        refresh_ev = _guard_state.get("refresh_event")

    while True:
        if stop.is_set():
            return "STOPPED"
        now = now_local()
        if now >= target_dt:
            return "OK"

        sleep_secs = min((target_dt - now).total_seconds(),
                         float(cfg.get("GUARD_POLL_INTERVAL")))
        triggered = False
        if refresh_ev:
            refresh_ev.clear()
            # 用 refresh_event 而不是 stop.wait，才能被预约/取消操作立即唤醒；
            # 返回 True 表示外部信号，False 表示到点的定期刷新
            triggered = refresh_ev.wait(timeout=sleep_secs)
        else:
            stop.wait(sleep_secs)
        if stop.is_set():
            return "STOPPED"
        if now_local() >= target_dt:
            return "OK"

        reason = "外部信号" if triggered else "定期刷新"
        try:
            my_status, earliest_dt = guard_query_active(reservation_id)
        except Exception as e:
            # 拉取失败绝不能当成「预约已消失」而中止守护，只记日志继续等
            log("warn", f"守护：[{reason}] 刷新失败，继续守护：{e}")
            continue

        if my_status is None:
            log("warn", f"守护：[{reason}] 预约 {reservation_id} 已不在活跃列表，守护中止")
            return "CANCELED"
        if my_status in ("FINISHED", "CANCELED", "AUTO_CANCELED"):
            log("ok", f"守护：[{reason}] 预约已变为 {my_status}，守护中止")
            return "CANCELED"
        if earliest_dt and earliest_dt < start_dt:
            log("warn", f"守护：[{reason}] 发现更早预约（{earliest_dt:%H:%M}），切换守护")
            return "PREEMPTED"
        log("info", f"守护：[{reason}] {label_name} 状态正常（{my_status}），继续守护")


def run_guard(stop: threading.Event, reservation_id: Any, start_dt: datetime,
              label_name: str, reservation_type: str = "SEAT") -> str:
    """守护单条预约。返回 DONE / CANCELED / PREEMPTED / STOPPED。"""
    check1_dt = start_dt + timedelta(minutes=10)
    check2_dt = start_dt + timedelta(minutes=15)

    with _guard_state_lock:
        _guard_state["current"] = {
            "reservationId": reservation_id,
            "type": reservation_type,
            "typeLabel": "座位" if reservation_type == "SEAT" else "会议室",
            "name": label_name,
            "start": start_dt.strftime("%Y-%m-%d %H:%M"),
            "check1": check1_dt.strftime("%H:%M"),
            "check2": check2_dt.strftime("%H:%M"),
            "phase": "等待预约开始",
        }

    # 只报一条：守护对象 + 两个检查点。规则说明属于静态知识，
    # 每接管一条预约就刷两行等于噪声；检查时刻已随 current 状态
    # 通过 GET /guard 暴露（check1/check2），前端要展示从那里取。
    log("ok", f"开始守护 {label_name}，开始 {start_dt:%H:%M}，"
              f"检查点 {check1_dt:%H:%M} / {check2_dt:%H:%M}")

    def stage(target_dt: datetime, phase: str) -> Optional[str]:
        """到点返回 None，需要提前退出则返回信号并已归档。"""
        if now_local() >= target_dt:
            return None
        sig = _guard_wait_until(stop, target_dt, start_dt,
                                reservation_id, label_name, phase)
        if sig == "OK":
            return None
        if sig in ("CANCELED", "PREEMPTED"):
            _finalize_guard(reservation_id, sig)
        return sig

    for target, phase in ((start_dt, "等待预约开始"),
                          (check1_dt, "等待第一次检查")):
        sig = stage(target, phase)
        if sig:
            return sig

    # ---- 规则1：开始后 10 分钟 ----
    _guard_set_phase("执行规则1检查")
    log("info", f"{now_local():%H:%M:%S} 执行规则1检查（开始后10分钟）...")
    try:
        my_status, _ = guard_query_active(reservation_id)
    except Exception as e:
        # 检查点拉不到列表时绝不自动取消——宁可漏取消也不能误取消有效预约
        log("err", f"规则1检查失败，跳过本次判定（不自动取消）：{e}")
        my_status = "UNKNOWN"
    status = my_status if my_status is not None else "FINISHED"
    log("info", f"当前预约状态：{status}")

    if status in ("IN_USE", "FINISHED", "CANCELED", "AUTO_CANCELED"):
        log("ok", f"预约状态为 {status}，守护结束")
        _finalize_guard(reservation_id, status)
        return "DONE"
    if status == "RESERVED":
        do_auto_cancel(reservation_id, "开始后10分钟仍未签到，视为用户未到馆",
                       reservation_type)
        _finalize_guard(reservation_id, "AUTO_CANCELED")
        return "DONE"

    # ---- 规则2：开始后 15 分钟兜底 ----
    sig = stage(check2_dt, "等待兜底检查")
    if sig:
        return sig

    _guard_set_phase("执行规则2兜底")
    log("info", f"{now_local():%H:%M:%S} 执行规则2兜底检查（开始后15分钟）...")
    try:
        my_status, _ = guard_query_active(reservation_id)
    except Exception as e:
        log("err", f"规则2检查失败，跳过本次判定（不自动取消）：{e}")
        my_status = "UNKNOWN"
    status = my_status if my_status is not None else "FINISHED"
    log("info", f"当前预约状态：{status}")

    if status == "RESERVED":
        do_auto_cancel(reservation_id, "开始后15分钟仍未签到（兜底）", reservation_type)
        _finalize_guard(reservation_id, "AUTO_CANCELED")
    else:
        log("ok", f"预约状态为 {status}，守护结束")
        _finalize_guard(reservation_id, status)
    return "DONE"


def _checkin_guard(stop: threading.Event) -> None:
    """守护主循环，对齐原脚本 _continuous_guard_worker。"""
    with _guard_state_lock:
        _guard_state["running"] = True
        _guard_state["current"] = None
        refresh_event = threading.Event()
        _guard_state["refresh_event"] = refresh_event

    skip_ids: set = set()  # 只装时间解析失败的记录
    try:
        while not stop.is_set():
            chosen = get_next_reserved(exclude_ids=skip_ids)

            if chosen is None:
                with _guard_state_lock:
                    _guard_state["current"] = None
                interval = int(cfg.get("GUARD_POLL_INTERVAL"))
                log("info", f"守护：暂无待签到预约，{interval // 60} 分钟后再次检查...")
                refresh_event.clear()
                refresh_event.wait(timeout=interval)
                continue

            reservation_id = chosen.get("reservationId")
            reservation_type = chosen.get("type", "SEAT")
            res = chosen.get("resource") or {}
            resource_name = res.get("name", "?")
            type_label = "座位" if reservation_type == "SEAT" else "会议室"
            time_str = chosen.get("time", "?")
            start_dt = parse_start_dt(time_str)

            if not start_dt:
                # 只在本进程内跳过，避免解析器有缺陷时把预约永久丢掉；
                # 日志里带上原始字符串，便于补充解析规则
                log("err", f"守护：无法解析时间「{time_str}」，本次跳过该预约"
                           f"（预约ID {reservation_id}）")
                skip_ids.add(reservation_id)
                continue

            label_name = f"{type_label} {resource_name}"
            log("prog", f"守护：开始守护 {label_name}  时间：{time_str}  "
                        f"预约ID：{reservation_id}")

            sig = run_guard(stop, reservation_id, start_dt,
                            label_name, reservation_type)
            with _threads_lock:
                _threads["checkin_guard"]["last"] = \
                    f"{now_local():%H:%M:%S} {label_name} → {sig}"

            if sig == "STOPPED":
                break
            if sig == "PREEMPTED":
                log("info", "守护：切换到更早的预约...")
            else:
                log("info", "守护：本轮结束，检查是否还有待签到预约...")
    finally:
        with _guard_state_lock:
            _guard_state["running"] = False
            _guard_state["current"] = None
            _guard_state["refresh_event"] = None


def _token_monitor(stop: threading.Event) -> None:
    notified = False
    while not stop.is_set():
        res = check_token()
        if res.get("networkError"):
            log("warn", "后台检测：网络异常，本轮跳过（不判定 Token 失效）")
        elif res.get("valid"):
            notified = False
        elif not notified:
            log("warn", f"后台检测：Token 已失效（{res.get('message')}），发送提醒邮件")
            if _send_token_expired_email(str(res.get("message") or "")):
                notified = True
        with _threads_lock:
            _threads["token_monitor"]["last"] = now_local().strftime("%H:%M:%S")
        if not _sleep_interruptible(stop, cfg.get("TOKEN_MONITOR_INTERVAL_MIN") * 60):
            return


def _wait_for_trigger(stop: threading.Event, key: str) -> bool:
    """
    轮询到达 HH:MM 触发时间；返回 True 表示应当执行。
    改进版本：缩小轮询间隔，精度从 ±10s 提升到 ±0.05s
    """
    last_minute = None
    while not stop.is_set():
        target = cfg.get(key)          # 每轮重读，改配置立刻生效
        now = now_local()
        current_hm = now.strftime("%H:%M")
        
        # 只在分钟变化时重新检查，避免频繁字符串比较
        if now.minute != last_minute:
            last_minute = now.minute
            if current_hm == target:
                log("info", f"触发时间 {target} 已到达，准备执行")
                return True
        
        # 检查间隔改为 100ms，精度足以捕捉 HH:MM 的分钟跳转
        # 高峰期即使偶尔卡顿，最多延迟也就 100-300ms
        if not _sleep_interruptible(stop, 0.1):
            return False
    return False


def _format_meeting_result(r: dict) -> str:
    """格式化单条预约结果用于邮件显示
    
    输入：
    {
        "start": "09:00",
        "end": "10:00",
        "success": True/False,
        "reservation_id": 126854 or None,
        "message": "失败原因或空"
    }
    
    输出示例：
    09:00 ~ 10:00  ✅ 预约ID: 126854
    或
    09:00 ~ 10:00  ❌ 时间段已被占用
    """
    start = r.get("start", "?")
    end = r.get("end", "?")
    success = r.get("success", False)
    res_id = r.get("reservation_id")
    msg = r.get("message", "")
    
    if success and res_id:
        return f"{start} ~ {end}  ✅ 预约ID: {res_id}"
    elif success:
        return f"{start} ~ {end}  ✅"
    else:
        reason = msg if msg else "预约失败"
        return f"{start} ~ {end}  ❌ {reason}"


def _send_meeting_report_email_async(
    date: str, room_id: int, start_time: str, end_time: str, 
    results: list
) -> bool:
    """
    发送会议室分时段预约报告邮件/短信
    
    results 格式：
    [
        {
            "start": "08:00",
            "end": "09:00", 
            "success": True/False,
            "reservation_id": "126854" (成功时有值),
            "message": "错误信息或状态" (失败时有值)
        },
        ...
    ]
    """
    # 先按 start 时间排序（确保顺序一致）
    sorted_results = sorted(results, key=lambda r: r.get("start", ""))
    
    succ_count = sum(1 for r in sorted_results if r.get("success"))
    fail_count = len(sorted_results) - succ_count
    
    # 构建邮件内容
    detail_lines = [f"预约日期：{date}", f"时间范围：{start_time} ~ {end_time}"]
    
    if succ_count == len(sorted_results):
        status_icon = "✅"
        summary = f"全部成功（{len(sorted_results)}/{len(sorted_results)} 段）"
    elif succ_count == 0:
        status_icon = "❌"
        summary = f"全部失败（0/{len(sorted_results)} 段）"
    else:
        status_icon = "⚠️"
        summary = f"部分成功（{succ_count}/{len(sorted_results)} 段）"
    
    detail_lines.append(f"执行结果：{status_icon} {summary}")
    detail_lines.append("")
    detail_lines.append("分段明细（按时间排序）：")
    
    # 逐段显示结果
    for i, result in enumerate(sorted_results, 1):
        st = result.get("start", "?")
        et = result.get("end", "?")
        
        if result.get("success"):
            res_id = result.get("reservation_id", "N/A")
            detail_lines.append(f"  [{i}/{len(sorted_results)}] {st} ~ {et}  ✅ 预约ID: {res_id}")
        else:
            msg = result.get("message", "未知错误")
            detail_lines.append(f"  [{i}/{len(sorted_results)}] {st} ~ {et}  ❌ {msg}")
    
    body = _mail_body(
        f"定时会议室分时段预约已于 {now_local():%Y-%m-%d %H:%M:%S} 执行完毕。",
        detail_lines,
    )
    
    mail_status = send_email(
        f"{EMAIL_TAG}定时会议室预约汇报｜{status_icon} {summary}",
        body
    )
    
    return mail_status


def _meeting_scheduler(stop: threading.Event) -> None:
    """定时触发会议室分时段预约，异步并发提交版本"""
    
    last_date = None
    while not stop.is_set():
        # 等待触发时间
        if not _wait_for_trigger(stop, "SCHEDULER_TRIGGER_TIME"):
            return
        
        today = now_local().strftime("%Y-%m-%d")
        # 同一天只执行一次
        if today == last_date:
            _sleep_interruptible(stop, 60)
            continue
        last_date = today
        
        # 读取配置
        date = get_default_date()
        room_id = cfg.get("MEETING_ROOM_ID")
        start = cfg.get("MEETING_START_TIME")
        end = cfg.get("MEETING_END_TIME")
        
        # 检查时间配置
        try:
            slots = split_time_slots(date, start, end, 1)
        except HTTPException as e:
            log("err", f"定时会议室预约配置有误：{e.detail}")
            _sleep_interruptible(stop, 60)
            continue
        
        log("info", f"定时触发：会议室分时段预约 {date}，共 {len(slots)} 段（异步并发）")
        
        # ========== 并发提交所有时段 ==========
        futures = {}
        for i, (st, et) in enumerate(slots, 1):
            # 在线程池中执行单个时段的提交
            future = _executor.submit(
                _submit_single_slot,
                room_id, date, st, et,
                cfg.get("MEETING_TITLE"), 
                cfg.get("MEETING_CONTENT"),
                cfg.get("MEETING_ATTENDEES"), 
                i, len(slots)
            )
            futures[future] = i  # 记录序号便于追踪
        
        log("prog", f"向线程池提交 {len(slots)} 个任务，并发执行...")
        start_time = time.time()
        
        # 等待所有任务完成，并按原始顺序重建结果
        results_by_index = {}  # {index: result_dict}
        succ_count = 0
        
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                results_by_index[idx] = result
                if result.get("success"):
                    succ_count += 1
            except Exception as e:
                log("err", f"第 {idx} 段异常：{e}")
                results_by_index[idx] = {
                    "index": idx,
                    "start": slots[idx - 1][0],
                    "end": slots[idx - 1][1],
                    "success": False,
                    "message": str(e),
                    "result": None
                }
        
        elapsed = time.time() - start_time
        
        # ========== 构建邮件用的结果列表（按时间顺序，已排好序）==========
        email_results = []
        for idx in range(1, len(slots) + 1):
            if idx in results_by_index:
                result = results_by_index[idx]
                st = result.get("start", "?")
                et = result.get("end", "?")
                
                # 从响应体中提取预约 ID
                reservation_id = None
                if result.get("success"):
                    resp = result.get("result", {})
                    if isinstance(resp, dict):
                        reservation_id = resp.get("id")
                
                email_results.append({
                    "start": st,
                    "end": et,
                    "success": result.get("success", False),
                    "reservation_id": reservation_id,
                    "message": result.get("message", "")
                })
            else:
                # 理论上不应该发生，但做防御性处理
                st, et = slots[idx - 1]
                email_results.append({
                    "start": st,
                    "end": et,
                    "success": False,
                    "reservation_id": None,
                    "message": "未收到结果"
                })
        
        # 记录统计信息
        summary = f"{date} 成功 {succ_count}/{len(slots)} 段，耗时 {elapsed:.2f}s"
        log("ok" if succ_count == len(slots) else ("warn" if succ_count > 0 else "err"), 
            f"分时段预约完成：{summary}")
        
        with _threads_lock:
            _threads["meeting_scheduler"]["last"] = summary
        
        # 发送邮件/短信（已按时间排序，含预约ID）
        _send_meeting_report_email_async(date, room_id, start, end, email_results)
        
        _sleep_interruptible(stop, 60)


def _seat_scheduler(stop: threading.Event) -> None:
    last_date = None
    while not stop.is_set():
        if not _wait_for_trigger(stop, "SEAT_SCHEDULER_TRIGGER_TIME"):
            return
        today = now_local().strftime("%Y-%m-%d")
        if today == last_date:
            _sleep_interruptible(stop, 60)
            continue
        last_date = today

        date = get_default_date()
        start, end = cfg.get("START_TIME"), cfg.get("END_TIME")
        seat_id = cfg.get("SEAT_ID")
        log("info", f"定时触发：座位预约 {date}")

        r = submit_with_retry(lambda: create_seat_reservation(seat_id, date, start, end))
        okk = isinstance(r, dict) and bool(r.get("id"))
        detail = ""
        if isinstance(r, dict):
            detail = str(r.get("message") or r.get("msg") or "")
        summary = f"{date} {'成功' if okk else '失败'}"
        log("ok" if okk else "err", f"定时座位预约{summary}")
        with _threads_lock:
            _threads["seat_scheduler"]["last"] = summary

        _send_seat_report_email(date, seat_id, start, end, okk, detail)
        _sleep_interruptible(stop, 60)


_WORKERS = {
    "token_monitor": _token_monitor,
    "checkin_guard": _checkin_guard,
    "meeting_scheduler": _meeting_scheduler,
    "seat_scheduler": _seat_scheduler,
}


def start_task(name: str) -> None:
    with _threads_lock:
        st = _threads[name]
        if st["on"]:
            return
        stop = threading.Event()
        t = threading.Thread(target=_WORKERS[name], args=(stop,), daemon=True, name=name)
        st.update(on=True, stop=stop, thread=t)
    t.start()
    log("ok", f"后台任务已启动：{name}")


def stop_task(name: str) -> None:
    with _threads_lock:
        st = _threads[name]
        if not st["on"]:
            return
        st["stop"].set()
        st.update(on=False, stop=None, thread=None)
    if name == "checkin_guard":
        # 守护线程多半卡在 refresh_event.wait 上，光置 stop 不会立刻醒
        notify_guard_refresh()
    log("info", f"后台任务已停止：{name}")


def restart_running_tasks() -> None:
    """配置变更后重启在跑的任务，让新参数立即生效。"""
    with _threads_lock:
        running = [k for k, v in _threads.items() if v["on"]]
    for name in running:
        stop_task(name)
        start_task(name)


# ============================================================
# 五、HTTP 接口
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- 启动阶段 ----
    if _ENV_LOADED_FROM:
        log("info", f".env 已加载：{_ENV_LOADED_FROM}")
    else:
        log("info", "未找到 .env，仅使用系统环境变量")
    log("info", f"后端启动，配置文件：{CONFIG_PATH}")
    if not ADMIN_KEY:
        log("warn", "未设置 ADMIN_KEY，接口无鉴权，请仅监听 127.0.0.1")
    if cfg.get("TOKEN"):
        start_task("token_monitor")
        start_task("checkin_guard")

    yield

    # ---- 关闭阶段：让后台线程收到停止信号，避免 Ctrl+C 后残留 ----
    with _threads_lock:
        running = [k for k, v in _threads.items() if v["on"]]
    for name in running:
        stop_task(name)
    log("info", "后端已关闭")


app = FastAPI(title="图书馆预约助手后端", version="2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    if ADMIN_KEY and request.method != "OPTIONS" and request.url.path != "/health":
        if request.headers.get("X-Admin-Key") != ADMIN_KEY:
            token = request.query_params.get("key")  # EventSource 无法设置请求头
            if token != ADMIN_KEY:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "未授权"}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health():
    return {"ok": True, "time": now_local().isoformat()}


# ---- 配置：前端表单的全部依据 ----

@app.get("/config/schema")
def config_schema():
    groups: List[str] = []
    for i in CONFIG_SCHEMA:
        if i["group"] not in groups:
            groups.append(i["group"])
    return {"groups": groups, "fields": CONFIG_SCHEMA}


@app.get("/config")
def config_get(reveal: bool = False):
    return {"config": cfg.snapshot(mask=not reveal), "defaultDate": get_default_date()}


@app.put("/config")
async def config_put(request: Request):
    body = await request.json()
    patch = body.get("config", body)
    if not isinstance(patch, dict):
        raise HTTPException(400, "请求体应为对象")
    try:
        changed = cfg.update(patch)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if changed:
        restart_running_tasks()
    return {"changed": list(changed.keys()), "config": cfg.snapshot()}


@app.post("/config/reset")
def config_reset():
    cfg.reset()
    restart_running_tasks()
    return {"config": cfg.snapshot()}


# ---- Token ----

@app.get("/token/check")
def token_check():
    return check_token()


# ---- 表单默认值 ----

@app.get("/form/defaults")
def form_defaults():
    """前端座位/会议室表单的初始值，由后端统一推断，避免两端算法漂移。"""
    d = manual_defaults()
    return {
        "date": d["date"],
        "seat": {"seatId": cfg.get("SEAT_ID"), **d},
        "meeting": {"roomId": cfg.get("MEETING_ROOM_ID"),
                    "granularity": 0, **d},
        "cutoffHour": cfg.get("DATE_CUTOFF_HOUR"),
    }


# ---- 座位 ----

# 已结束/已取消的记录不占用时段，列出来只会让人误判座位是满的。
# 默认隐藏，includeFinished=true 时返回全部（排查上游数据时用）。
_SEAT_QUERY_HIDDEN = ("FINISHED", "CANCELED", "AUTO_CANCELED")


@app.post("/seat/query")
async def seat_query(request: Request):
    b = await request.json()
    seat_id = int(b.get("seatId") or cfg.get("SEAT_ID"))
    date = need_date(b.get("date") or get_default_date())
    include_finished = bool(b.get("includeFinished"))
    # 原脚本 get_seat_reservations：座位 ID 在路径上，只带 date 一个参数
    records = unwrap_list(api_request(
        "GET", f"/v1/seats/{seat_id}/reservations", params={"date": date}))
    total = len(records)

    if not include_finished:
        kept = [r for r in records
                if str(r.get("status", "")).upper() not in _SEAT_QUERY_HIDDEN]
    else:
        kept = list(records)
    hidden = total - len(kept)

    # 按开始时间排序，便于一眼看出空档；startTime 是完整日期时间字符串
    kept.sort(key=lambda r: str(r.get("startTime") or ""))

    if kept:
        log("info", f"{date} 该座位有效占用 {len(kept)} 条"
                    + (f"（已隐藏 {hidden} 条已结束/已取消）" if hidden else "") + "：")
        for r in kept:
            status = r.get("status", "?")
            log("info", f"    {r.get('startTime', '?')} ~ {r.get('endTime', '?')}  "
                        f"状态：{_STATUS_LABELS.get(status, status)}")
    elif hidden:
        log("ok", f"{date} 该座位当前无有效占用（{hidden} 条已结束/已取消未显示）")
    else:
        log("info", f"{date} 该座位暂无预约记录")

    return {"seatId": seat_id, "date": date, "data": kept,
            "total": total, "hidden": hidden}


@app.post("/seat/reserve")
async def seat_reserve(request: Request):
    b = await request.json()
    seat_id = int(b.get("seatId") or cfg.get("SEAT_ID"))
    # 手动提交的默认值与 /form/defaults 完全同源：日期按分界小时推断，
    # 开始=当前时刻，结束=DEFAULT_MANUAL_END_TIME。定时任务不走这里，
    # 仍用 START_TIME/END_TIME，两套语义不要混。
    d = manual_defaults()
    date = need_date(b.get("date") or d["date"])
    start = need_time(b.get("startTime") or d["startTime"], "开始时间")
    end = need_time(b.get("endTime") or d["endTime"], "结束时间")
    need_range(date, start, end)
    result = submit_with_retry(lambda: create_seat_reservation(seat_id, date, start, end))
    ok = bool(isinstance(result, dict) and result.get("_submitOk"))
    message = (result.get("_submitMessage") if isinstance(result, dict) else None) \
        or "座位预约失败：未收到上游响应（网络异常或请求超时，请稍后在活跃预约中核实是否已生效）"
    active = refresh_active_summary("座位预约") if ok else []
    # success 是前端弹「成功/失败」提示的唯一依据，不能再凡是 HTTP 200 就报喜——
    # 上游时段冲突、规则不符等业务失败也是 200，只是 body 换成 code/message。
    return {"success": ok, "message": message, "result": result, "active": active}


# ---- 会议室 ----

# 上游实际接口（抓包核实）：
#   GET /v1/meeting-room?limit=10&offset=0&startTime=YYYY-MM-DD HH:MM
#                        &endTime=YYYY-MM-DD HH:MM&parentIdPath=
# 三点与早前的写法不同，都会导致查询失效或结果不全：
#   1. 路径是 meeting-room（单数），不是 meeting-rooms；
#   2. 没有 date 参数，时间只通过 startTime/endTime 两个完整日期时间传；
#   3. 返回是 {"total": 43, "list": [...]} 分页壳，默认 limit 只给 10 条。
# 条目字段（抓包实测全集）：
#   id / name / parentNamePath / desc / cover / capacity
#   canReserve / cannotReserveReason  ← 能否预约的**权威判据**
#   openTime / closeTime / time        ← 开放时段，如 "07:00 - 21:30"
#   status / statusLabel               ← 房间**当前**状态（IN_USE / 使用中）
#   realAdvanceReservationDays
#   rule: { customStartTime, minAttendees, minDurationMinutes,
#           maxDurationMinutes, needApproval, needMaterial,
#           checkInAheadMinutes, advanceReservationDays,
#           availableStartTime, availableEndTime }
# 注意 status 与 canReserve 是两件事：实测出现过 status=IN_USE 但
# canReserve=true —— status 说的是「此刻房间有人」，canReserve 说的是
# 「你查询的那个时段能不能约」。判断可约性只能用 canReserve，
# 拿 status 当可约性会把大量实际可约的房间标成占用。
_MEETING_PAGE_SIZE = 50
_MEETING_MAX_PAGES = 20  # 硬上限，防上游 total 异常时空转


def fetch_meeting_rooms(start_dt: str, end_dt: str,
                        parent_id_path: str = "") -> Dict[str, Any]:
    """翻页取全量可用会议室，返回 {"total": n, "list": [...], "fetched": m}。

    total=43 而默认 limit=10，只发一次请求会漏掉三分之二的房间。这里按
    _MEETING_PAGE_SIZE 连续取，直到凑满 total 或某页返回空。上游若把
    total 报大（比含权限过滤前的数量），空页会兜住循环。
    """
    rooms: List[Dict[str, Any]] = []
    total = 0
    offset = 0
    for _ in range(_MEETING_MAX_PAGES):
        data = api_request("GET", "/v1/meeting-room", params={
            "limit": _MEETING_PAGE_SIZE,
            "offset": offset,
            "startTime": start_dt,
            "endTime": end_dt,
            "parentIdPath": parent_id_path,
        })
        page = unwrap_list(data)
        if isinstance(data, dict) and isinstance(data.get("total"), int):
            total = data["total"]
        if not page:
            break
        rooms.extend(page)
        offset += len(page)
        if total and offset >= total:
            break
        if len(page) < _MEETING_PAGE_SIZE:
            break
    return {"total": total or len(rooms), "list": rooms, "fetched": len(rooms)}


def _hm(raw: Any) -> Optional[str]:
    """把 "21:00:00" 截成 "21:00"；已是 HH:MM 或空值原样返回。

    rule 里的 availableStartTime/availableEndTime 带秒，而 openTime/closeTime
    不带，前端要对齐展示就得统一。
    """
    if raw in (None, ""):
        return None
    s = str(raw).strip()
    m = _RE_TIME.match(s)
    return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}" if m else s


# occState 三态：纯按 status 字段判定，不再参考时长/人数规则文字
# （那类「时长 336 分钟超过最长 240 分钟」的提示对用户没价值，已去掉）：
#   in_use   房间此刻正在使用 —— status == IN_USE          → 前端标灰色
#   reserved 此刻没人，但当天已有预约占位 —— status == RESERVED → 前端标黄色
#   free     以上都不是，视为可预约                          → 前端标绿色
_OCC_STATE_LABELS = {"in_use": "使用中", "reserved": "有预约", "free": "空闲中"}


def _occ_state_of(status: Any) -> str:
    s = str(status or "").upper()
    if s == "IN_USE":
        return "in_use"
    if s == "RESERVED":
        return "reserved"
    return "free"


def normalize_meeting_room(r: Dict[str, Any]) -> Dict[str, Any]:
    """整理成前端直接可渲染的形状，键名照上游实测字段，不再前端猜。"""
    open_time = _hm(r.get("openTime"))
    close_time = _hm(r.get("closeTime"))
    occ_state = _occ_state_of(r.get("status"))
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "location": r.get("parentNamePath"),
        "capacity": r.get("capacity"),
        "desc": r.get("desc"),
        "cover": r.get("cover"),
        # 房间当前状态：occState 是三色判定的唯一依据（灰/黄/绿）
        "status": r.get("status"),
        "statusLabel": r.get("statusLabel") or _STATUS_LABELS.get(
            str(r.get("status") or ""), r.get("status")),
        "occState": occ_state,
        "occStateLabel": _OCC_STATE_LABELS[occ_state],
        "openTime": open_time,
        "closeTime": close_time,
        # time 上游已给成 "07:00 - 21:30"，缺失时用 openTime/closeTime 拼
        "openRange": r.get("time") or (
            f"{open_time} - {close_time}" if open_time and close_time else None),
        "advanceDays": r.get("realAdvanceReservationDays"),
        "raw": r,
    }


@app.post("/meeting/query")
async def meeting_query(request: Request):
    b = await request.json()
    d = manual_defaults()
    date = need_date(b.get("date") or d["date"])
    start = need_time(b.get("startTime") or d["startTime"], "开始时间")
    end = need_time(b.get("endTime") or d["endTime"], "结束时间")
    need_range(date, start, end)
    parent_id_path = str(b.get("parentIdPath") or "")

    log("prog", f"查询 {date} {start}~{end} 可用会议室...")
    fetched = fetch_meeting_rooms(f"{date} {start}", f"{date} {end}",
                                  parent_id_path)
    rooms = [normalize_meeting_room(r) for r in fetched["list"]]
    # 按楼层再按房间号排：name 是 "412" 这类纯数字字符串，按字符串排会把
    # "1001" 排到 "412" 前面，所以数字优先、非数字兜底为字符串
    rooms.sort(key=lambda r: (
        str(r.get("location") or ""),
        (0, int(r["name"])) if str(r.get("name") or "").isdigit()
        else (1, str(r.get("name") or "")),
    ))

    if rooms:
        log("info", f"{date} {start}~{end} 会议室 {len(rooms)} 间"
                    + (f"（上游报 total {fetched['total']}）"
                       if fetched["total"] != len(rooms) else "") + "：")
        for r in rooms:
            cap = f"可容 {r['capacity']} 人" if r.get("capacity") else "容量未知"
            log("info", f"    [{r.get('occStateLabel')}] ID:{r.get('id')}  {r.get('name')}  "
                        f"{r.get('location') or ''}  {cap}  "
                        f"开放 {r.get('openRange') or '?'}")
        free_n = sum(1 for r in rooms if r["occState"] == "free")
        reserved_n = sum(1 for r in rooms if r["occState"] == "reserved")
        in_use_n = sum(1 for r in rooms if r["occState"] == "in_use")
        log("ok" if free_n else "warn",
            f"可预约 {free_n} 间，有预约 {reserved_n} 间，使用中 {in_use_n} 间")
    else:
        log("warn", f"{date} {start}~{end} 暂无会议室数据")

    return {"date": date, "startTime": start, "endTime": end,
            "data": rooms, "count": len(rooms), "total": fetched["total"],
            "free": sum(1 for r in rooms if r["occState"] == "free"),
            "reserved": sum(1 for r in rooms if r["occState"] == "reserved"),
            "inUse": sum(1 for r in rooms if r["occState"] == "in_use")}


# 单房间当天预约明细：点某间会议室即拉它当天已被占用的时段，
# 与座位「查占用」对称。上游（抓包核实）：
#   GET /v1/meeting-room/{roomId}/reservations/by-date?date=YYYY-MM-DD
# 返回裸数组，每条：
#   reservationId / userId / user（脱敏姓名，如 "李*飞"）
#   status（IN_USE / RESERVED / ...）/ startTime / endTime / time（"13:13 - 17:13"）
# 与座位一致：已结束/已取消不占位，默认隐藏，includeFinished=true 取全量。
_ROOM_OCCUPY_HIDDEN = ("FINISHED", "CANCELED", "AUTO_CANCELED")


@app.post("/meeting/room/reservations")
async def meeting_room_reservations(request: Request):
    b = await request.json()
    room_id = int(b.get("roomId") or b.get("id") or cfg.get("MEETING_ROOM_ID"))
    date = need_date(b.get("date") or get_default_date())
    room_name = b.get("roomName") or b.get("name")
    include_finished = bool(b.get("includeFinished"))

    records = unwrap_list(api_request(
        "GET", f"/v1/meeting-room/{room_id}/reservations/by-date",
        params={"date": date}))
    total = len(records)

    if not include_finished:
        kept = [r for r in records
                if str(r.get("status", "")).upper() not in _ROOM_OCCUPY_HIDDEN]
    else:
        kept = list(records)
    hidden = total - len(kept)

    # startTime 是完整日期时间字符串，直接字符串排序即按时间升序
    kept.sort(key=lambda r: str(r.get("startTime") or ""))

    out = []
    for r in kept:
        status = r.get("status", "")
        out.append({
            "reservationId": r.get("reservationId"),
            "userId": r.get("userId"),
            "user": r.get("user"),
            "status": status,
            "statusLabel": _STATUS_LABELS.get(status, status or "未知状态"),
            "startTime": r.get("startTime"),
            "endTime": r.get("endTime"),
            # time 上游已给成 "13:13 - 17:13"，缺失时用起止拼
            "time": r.get("time") or (
                f"{_hm(r.get('startTime'))} - {_hm(r.get('endTime'))}"
                if r.get("startTime") and r.get("endTime") else None),
            "raw": r,
        })

    label = f"会议室 {room_name}" if room_name else f"会议室 {room_id}"
    if out:
        log("info", f"{date} {label} 有效占用 {len(out)} 条"
                    + (f"（已隐藏 {hidden} 条已结束/已取消）" if hidden else "") + "：")
        for it in out:
            log("info", f"    {it.get('time') or '?'}  "
                        f"状态：{it.get('statusLabel')}  "
                        f"占用者：{it.get('user') or '?'}")
    elif hidden:
        log("ok", f"{date} {label} 当前无有效占用"
                  f"（{hidden} 条已结束/已取消未显示）")
    else:
        log("ok", f"{date} {label} 全天空闲，无任何预约")

    return {"roomId": room_id, "roomName": room_name, "date": date,
            "data": out, "total": total, "hidden": hidden,
            "occupied": len(out)}


def _submit_single_slot(
    room_id: int, date: str, st: str, et: str, 
    title: str, content: str, attendees: str,
    slot_index: int, total_slots: int
) -> Dict[str, Any]:
    """单个时段的提交任务，在线程池中执行。
    
    返回格式：
    {
        "index": 时段序号,
        "start": 开始时间,
        "end": 结束时间,
        "result": 上游返回的原始响应,
        "success": bool,
        "message": 错误信息（成功时为空）
    }
    """
    
    try:
        log("prog", f"[{slot_index}/{total_slots}] 约 {st}~{et} 线程内提交时刻：{time.time():.3f}")
        
        # 同步提交到上游 API，含重试逻辑
        r = submit_with_retry(
            lambda: create_meeting_reservation(
                room_id, date, st, et, title, content, attendees
            )
        )
        
        ok_i = bool(isinstance(r, dict) and r.get("_submitOk"))
        msg_i = ""
        if not ok_i:
            msg_i = (r.get("_submitMessage") if isinstance(r, dict) else None) or "无响应"
        
        result = {
            "index": slot_index,
            "start": st,
            "end": et,
            "result": r,
            "success": ok_i,
            "message": msg_i
        }
        
        log("ok" if ok_i else "err", 
            f"[{slot_index}/{total_slots}] 段 {st}~{et} {'✓' if ok_i else '✗'}")
        
        return result
        
    except Exception as e:
        log("err", f"[{slot_index}/{total_slots}] 段 {st}~{et} 异常：{e}")
        return {
            "index": slot_index,
            "start": st,
            "end": et,
            "result": None,
            "success": False,
            "message": str(e)
        }

@app.post("/meeting/reserve")
async def meeting_reserve(request: Request):
    b = await request.json()
    room_id = int(b.get("roomId") or cfg.get("MEETING_ROOM_ID"))
    d = manual_defaults()
    date = need_date(b.get("date") or d["date"])
    start = need_time(b.get("startTime") or d["startTime"], "开始时间")
    end = need_time(b.get("endTime") or d["endTime"], "结束时间")
    need_range(date, start, end)
    granularity = int(b.get("granularity") or 0)
    title = b.get("title") or cfg.get("MEETING_TITLE")
    content = b.get("content") or cfg.get("MEETING_CONTENT")
    attendees = b.get("attendees") or cfg.get("MEETING_ATTENDEES")

    # 单段预约（原逻辑不变）
    if granularity <= 0:
        result = submit_with_retry(lambda: create_meeting_reservation(
            room_id, date, start, end, title, content, attendees))
        ok = bool(isinstance(result, dict) and result.get("_submitOk"))
        message = (result.get("_submitMessage") if isinstance(result, dict) else None) \
            or "会议室预约失败：未收到上游响应（网络异常或请求超时）"
        active = refresh_active_summary("会议室预约") if ok else []
        return {"success": ok, "message": message,
                "results": [{"start": start, "end": end, "result": result}],
                "active": active}

    # 多段异步并发预约
    slots = split_time_slots(date, start, end, granularity)
    total = len(slots)
    log("info", f"分时段异步提交：{date}，共 {total} 段，粒度 {granularity} 小时")
    
    # 构造所有任务
    tasks = []
    for i, (st, et) in enumerate(slots, 1):
        task = asyncio.get_event_loop().run_in_executor(
            _executor,
            _submit_single_slot,
            room_id, date, st, et, title, content, attendees, i, total
        )
        tasks.append(task)
    
    # 并发执行，等待全部完成
    log("prog", f"向线程池提交 {total} 个任务，并发执行...")
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start_time
    
    # 统计成败
    out = results  # 直接用返回的结果列表
    succ = sum(1 for r in results if r.get("success"))
    fail_messages = [f"{r['start']}~{r['end']}：{r['message']}" 
                     for r in results if not r.get("success")]
    
    all_ok = succ == total
    log("ok" if succ else "err", 
        f"分时段异步提交完成：成功 {succ}/{total} 段，耗时 {elapsed:.2f}s")
    
    if fail_messages:
        for msg in fail_messages[:3]:
            log("warn", f"  失败：{msg}")
    
    # 响应前端
    active = refresh_active_summary("分时段会议室预约") if succ else []
    
    if all_ok:
        message = f"全部 {total} 段预约成功（耗时 {elapsed:.2f}s）"
    elif succ > 0:
        message = f"部分成功：{succ}/{total} 段，失败段：" + "；".join(fail_messages[:3])
    else:
        message = f"全部失败：" + (fail_messages[0] if fail_messages else "未知错误")
    
    return {
        "success": all_ok,
        "partial": 0 < succ < total,
        "message": message,
        "date": date,
        "results": out,
        "successCount": succ,
        "total": total,
        "active": active,
        "elapsedSeconds": elapsed  # ← 新增：前端可展示实际耗时
    }


# ---- 预约列表与取消 ----

@app.get("/reservations")
def reservations(status: str = ""):
    """活跃预约列表。status 为空返回全部；过滤在本地做，上游不接受该参数。"""
    log("prog", "正在获取活跃预约列表...")
    try:
        records = get_active_reservations()
    except HTTPException:
        raise
    except Exception as e:
        # 原脚本 get_active_reservations 捕获一切异常并返回 []，只打日志。
        log("err", f"获取活跃预约失败：{e}")
        raise HTTPException(502, f"获取活跃预约失败：{e}")

    if status:
        records = [r for r in records if r.get("status") == status]

    # 分组顺序照原脚本 cancel_mode：座位 → 会议室 → 其他，组内按开始时间升序，
    # 序号跨组连续编号（index 字段），前端可直接照此渲染。
    seat_list = sort_by_start([r for r in records if r.get("type") == "SEAT"])
    meeting_list = sort_by_start(
        [r for r in records if r.get("type") == "MEETING_ROOM"])
    other_list = [r for r in records
                  if r.get("type") not in ("SEAT", "MEETING_ROOM")]

    items = []
    for group, rows in (("SEAT", seat_list),
                        ("MEETING_ROOM", meeting_list),
                        ("OTHER", other_list)):
        for r in rows:
            res = r.get("resource") or {}
            rtype = r.get("type")
            items.append({
                "index": len(items) + 1,
                "group": group,
                "reservationId": r.get("reservationId"),
                # cancelType 是前端调 /cancel 时该回传的值，已按原脚本回退规则算好，
                # 前端不要自己猜，也不要用提交接口返回的 id。
                "type": rtype,
                "cancelType": reservation_type_of(r),
                "typeLabel": "座位" if rtype == "SEAT" else (
                    "会议室" if rtype == "MEETING_ROOM" else "其他"),
                "name": res.get("name"),
                "location": res.get("parentNamePath"),
                "time": r.get("time"),
                "startAt": (lambda d: d.strftime("%Y-%m-%d %H:%M") if d else None)(
                    parse_start_dt(r.get("time", ""))),
                "status": r.get("status"),
                "statusLabel": _STATUS_LABELS.get(r.get("status"), r.get("status")),
                "meetingTitle": r.get("meetingTitle"),
                "cancelable": r.get("status") in ("RESERVED", "IN_USE"),
                "raw": r,
            })

    if items:
        log("info", f"共 {len(items)} 条预约"
                    f"（座位 {len(seat_list)}，会议室 {len(meeting_list)}"
                    + (f"，其他 {len(other_list)}" if other_list else "") + "）")
        for it in items:
            log("info", f"    [{it['index']}] 预约ID:{it['reservationId']}  "
                        f"{it['typeLabel']}:{it.get('name') or '?'}  "
                        f"{it.get('location') or ''}  "
                        f"时间:{it.get('time') or '?'}  "
                        f"状态:{it.get('statusLabel') or '?'}")
    else:
        log("warn", "当前没有活跃预约")

    return {"data": items, "count": len(items),
            "groups": {"seat": len(seat_list), "meeting": len(meeting_list),
                       "other": len(other_list)}}


@app.post("/cancel")
async def cancel(request: Request):
    b = await request.json()
    # reservationId 是活跃列表里的字段名，id 作为兼容别名保留
    rid = b.get("reservationId") or b.get("id")
    if not rid:
        raise HTTPException(400, "缺少预约 ID（reservationId）")

    # 类型缺失或无法识别时回退会议室，与原脚本
    # `chosen.get("type", "MEETING_ROOM")` 一致。早前默认成 seat 是反的，
    # 会把会议室预约打到座位端点上去。
    raw_type = str(b.get("cancelType") or b.get("type") or "").strip().lower()
    if raw_type == "seat":
        rtype = "seat"
    elif raw_type in ("meeting", "meeting_room", "meetingroom"):
        rtype = "meeting"
    else:
        rtype = "meeting"
        if raw_type:
            log("warn", f"未识别的预约类型「{raw_type}」，按会议室处理（照原脚本回退）")
        else:
            log("warn", "请求未带预约类型，按会议室处理（照原脚本回退）")

    # 关键：路径名词是 reservations 而非 applications，且两类的方法不同——
    # 座位用 POST，会议室用 PUT。上游接口本身不一致，照原脚本区分。
    if rtype == "seat":
        log("prog", f"正在取消座位预约 {rid}...")
        data = api_call("POST", f"/v1/seat-reservations/{rid}/cancel")
    else:
        log("prog", f"正在取消会议室预约 {rid}...")
        data = api_call("PUT", f"/v1/meeting-reservations/{rid}/cancel")

    active = refresh_active_summary("取消预约") if log_cancel_result(data) else []
    return {"data": data, "active": active}


# ---- 签到守护状态 ----

@app.get("/guard")
def guard_status():
    """对齐原脚本 show_guard_status 的输出内容，供前端渲染守护面板。"""
    with _guard_state_lock:
        running = _guard_state["running"]
        current = dict(_guard_state["current"]) if _guard_state["current"] else None
        history = [dict(h) for h in _guard_state["history"]]
    return {"running": running, "current": current,
            "history": list(reversed(history)),
            "pollInterval": cfg.get("GUARD_POLL_INTERVAL")}


@app.post("/guard/refresh")
def guard_refresh():
    """手动唤醒守护线程立即重查，不必等满一个轮询周期。"""
    notify_guard_refresh()
    log("info", "已请求守护线程立即刷新")
    return guard_status()


# ---- 后台任务开关 ----

@app.get("/tasks")
def tasks_status():
    with _threads_lock:
        return {"tasks": {k: {"running": v["on"], "last": v["last"]}
                          for k, v in _threads.items()}}


@app.post("/tasks/{name}/{action}")
def tasks_control(name: str, action: str):
    if name not in _threads:
        raise HTTPException(404, "未知任务")
    if action == "start":
        start_task(name)
    elif action == "stop":
        stop_task(name)
    else:
        raise HTTPException(400, "action 需为 start 或 stop")
    return tasks_status()


# ---- 日志流 ----

@app.get("/logs")
def logs_recent(limit: int = 200):
    with _log_lock:
        return {"logs": _log_buffer[-limit:]}


@app.get("/logs/stream")
async def logs_stream():
    loop = asyncio.get_running_loop()
    q: "asyncio.Queue[Dict[str, str]]" = asyncio.Queue(maxsize=200)
    with _log_lock:
        backlog = list(_log_buffer[-50:])
        _log_subscribers.append((loop, q))

    async def gen():
        try:
            for e in backlog:
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            # 先吐一次注释行，逼迫 nginx / 浏览器立刻建立起流，
            # 否则首条真实日志到来前客户端可能一直处于"连接中"。
            yield ": connected\n\n"
            while True:
                try:
                    # 纯异步等待，不再占用线程池线程；
                    # 15 秒无日志就发心跳，既保活也用于探测客户端是否已断开
                    e = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            # 客户端断开时由 Starlette 取消，属正常路径
            raise
        finally:
            with _log_lock:
                for i, (_, sub_q) in enumerate(_log_subscribers):
                    if sub_q is q:
                        del _log_subscribers[i]
                        break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ============================================================
# 六、直接运行入口：python backend.py 等价于 uvicorn backend:app
#     生产容器仍建议显式用 uvicorn 命令，便于调 worker 与日志参数
# ============================================================

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8010"))
    print(f"启动中：http://{host}:{port}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="info")
