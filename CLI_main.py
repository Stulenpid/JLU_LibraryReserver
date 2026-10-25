#CLI版本
#CMD:   python ./CLI_main.py
#请在配置区填写抓包获取的必要信息

import requests
import json
import time
import threading
import os
import re
import sys
import urllib3
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ==================== 配置区 ====================
TOKEN = "junyue-server *************"
BASE_URL = "https://libseat.jlu.edu.cn"

# 座位预约配置
SEAT_ID = 3421 #座位编号与真实座位对应关系，需抓包查看
START_TIME = "18:00"
END_TIME = "22:00"

# 会议室预约配置
MEETING_ROOM_ID = 30 #会议室编号与房间对应关系，需抓包查看
MEETING_START_TIME = "13:00"
MEETING_END_TIME = "17:00"
MEETING_TITLE = "小组讨论"
MEETING_CONTENT = "无"
MEETING_ATTENDEES = []  # 参会人 ID 列表，例如 [12345, 67890]；不需要邀请参会人时留空

# 定时抢座配置（提前到达此时间开始等待）
WAIT_UNTIL = None  # 例如 "2026-06-18 08:00:00"，None 表示立即执行

# 日期自动推断分界时间：到达此小时（含）后默认预约明天，之前默认预约今天
DATE_CUTOFF_HOUR = 21  # 整数，24小时制

# 手动输入时间为空时的默认结束时间
DEFAULT_MANUAL_END_TIME = "21:00"

# 定时会议室预约触发时间（每天到此时间自动执行功能5）
SCHEDULER_TRIGGER_TIME = "21:00"  # 格式 HH:MM

# 定时座位预约触发时间（每天到此时间自动执行座位预约）
SEAT_SCHEDULER_TRIGGER_TIME = "21:01"  # 格式 HH:MM

# 定时预约：单段无返回时的补发配置
SLOT_SUBMIT_INTERVAL = 0.5   # 每段之间的间隔（秒）
SLOT_RETRY_DELAY = 1.0       # 无返回后等待多久补发（秒）
SLOT_MAX_ATTEMPTS = 2        # 单段最多提交次数（含首次）
VERIFY_TIMEOUT = 4.0         # 补发前复查活跃列表的超时（秒）

# 邮件提醒配置（Token 失效时发送提醒）
EMAIL_SENDER = "123456789@example.com"
EMAIL_RECEIVER = "123456789@example.com"
EMAIL_SMTP_AUTHCODE = "*******EXAMPLE********"
# 校内站点常缺中间证书；如果本机证书链完整，可改为 True
VERIFY_TLS = False
# ==================== 配置区结束 ====================

if not VERIFY_TLS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "Authorization": TOKEN,
    "Content-Type": "application/json",
    "space": "LIBRARY",
}

# ==================== ANSI 颜色定义 ====================
C_RESET  = "\033[0m"
C_GREEN  = "\033[92m"   # 成功 ✓
C_RED    = "\033[91m"   # 失败 ✗
C_YELLOW = "\033[93m"   # 警告 !
C_CYAN   = "\033[96m"   # 进行中 …
C_BLUE   = "\033[94m"   # 信息 i
C_BOLD   = "\033[1m"
C_DIM    = "\033[2m"

def ok(msg):    print(f"{C_GREEN}[✓]{C_RESET} {msg}")
def err(msg):   print(f"{C_RED}[✗]{C_RESET} {msg}")
def warn(msg):  print(f"{C_YELLOW}[!]{C_RESET} {msg}")
def info(msg):  print(f"{C_BLUE}[i]{C_RESET} {msg}")
def prog(msg):  print(f"{C_CYAN}[…]{C_RESET} {msg}")
def arrow(msg): print(f"{C_CYAN}[→]{C_RESET} {msg}")

# 后台线程专用输出：前后空行隔离，输出后恢复提示符
_bg_print_lock = threading.Lock()

def _bg_block(lines):
    """后台线程输出一组行，前后空行，末尾恢复 > 提示符。"""
    with _bg_print_lock:
        print()  # 与上方内容隔开
        for line in lines:
            print(line)
        print(f"\n> ", end="", flush=True)  # 恢复输入提示符

def bg_ok(msg):    _bg_block([f"{C_GREEN}[✓]{C_RESET} {msg}"])
def bg_err(msg):   _bg_block([f"{C_RED}[✗]{C_RESET} {msg}"])
def bg_warn(msg):  _bg_block([f"{C_YELLOW}[!]{C_RESET} {msg}"])
def bg_info(msg):  _bg_block([f"{C_BLUE}[i]{C_RESET} {msg}"])
def bg_prog(msg):  _bg_block([f"{C_CYAN}[…]{C_RESET} {msg}"])
def bg_arrow(msg): _bg_block([f"{C_CYAN}[→]{C_RESET} {msg}"])
# =====================================================

# ==================== 后台守护状态 ====================
_guard_state = {
    "running": False,
    "current": None,
    "history": [],
    "thread": None,
    "stop_event": None,
    "refresh_event": None,   # 取消成功时立即唤醒守护线程
}
_guard_state_lock = threading.Lock()
# =====================================================


def get_date(offset=1):
    return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")


def get_default_date():
    """到达 DATE_CUTOFF_HOUR 后默认预约明天，之前默认预约今天。"""
    now = datetime.now()
    if now.hour >= DATE_CUTOFF_HOUR:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _request_json(method, url, timeout=10, **kwargs):
    '''带状态码检查的上游请求；失败抛 ApiError，避免把错误伪装成空列表。'''
    try:
        resp = requests.request(method, url, headers=HEADERS, timeout=timeout,
                                verify=VERIFY_TLS, **kwargs)
    except requests.RequestException as e:
        raise ApiError(f'网络请求失败：{e}') from e

    if resp.status_code in (401, 403):
        raise ApiError(f'登录状态失效（HTTP {resp.status_code}），请更新 TOKEN',
                       resp.status_code)
    if not 200 <= resp.status_code < 300:
        detail = ''
        try:
            data = resp.json()
            if isinstance(data, dict):
                detail = data.get('message') or data.get('msg') or data.get('error') or ''
            else:
                detail = str(data)
        except ValueError:
            detail = (resp.text or '').strip()[:200]
        msg = f'HTTP {resp.status_code}'
        if detail:
            msg += f'：{detail}'
        raise ApiError(msg, resp.status_code)

    try:
        return resp.json()
    except ValueError as e:
        raise ApiError('上游返回的不是合法 JSON', resp.status_code) from e


def unwrap_list(data):
    '''兼容裸数组、content/data/records/list 壳；错误体不再伪装成空列表。'''
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('content', 'data', 'records', 'list'):
            value = data.get(key)
            if isinstance(value, list):
                return value
        msg = data.get('message') or data.get('msg') or data.get('error')
        if msg:
            raise ApiError(f'上游返回错误：{msg}', data.get('_httpStatus'))
        return []
    return []


_RE_HM = re.compile(r'^(\d{1,2}):(\d{2})$')


def parse_hm(value, field='时间'):
    '''把 9:00 / 09:00 归一成 09:00，并校验范围。'''
    text = str(value or '').strip()
    match = _RE_HM.match(text)
    if not match:
        raise ValueError(f'{field}需为 HH:MM 格式，收到「{text}」')
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f'{field}超出范围：「{text}」')
    return f'{hour:02d}:{minute:02d}'


def parse_user_id_from_token(token):
    try:
        import base64
        parts = token.split(" ", 1)
        if len(parts) != 2:
            return None
        decoded = base64.b64decode(parts[1]).decode("utf-8")
        segments = decoded.split(":")
        if len(segments) >= 2:
            return int(segments[1])
    except Exception:
        pass
    return None


def check_token():
    user_id = parse_user_id_from_token(TOKEN)
    if not user_id:
        err("Token 格式无法解析，请检查配置")
        return None
    url = f"{BASE_URL}/v1/users/{user_id}/detail"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, verify=VERIFY_TLS)
        if resp.status_code in (401, 403):
            err(f"Token 已过期或无效（状态码：{resp.status_code}）")
            return None
        if resp.status_code != 200:
            err(f"Token 验证失败（状态码：{resp.status_code}）")
            return None
        data = resp.json()
        nickname = data.get("nickname") if isinstance(data, dict) else None
        if not nickname:
            msg = data.get("message", "无法获取用户信息") if isinstance(data, dict) else "响应格式异常"
            err(f"Token 无效：{msg}")
            return None
        ok(f"Token 有效，当前用户：{C_BOLD}{nickname}{C_RESET}（ID: {user_id}）")
        return data
    except Exception as e:
        err(f"Token 验证失败：{e}")
        return None


def get_seat_reservations(seat_id, date):
    url = f'{BASE_URL}/v1/seats/{seat_id}/reservations'
    params = {'date': date}
    return unwrap_list(_request_json('GET', url, params=params))


def show_seat_reservations(seat_id, date):
    try:
        records = get_seat_reservations(seat_id, date)
    except Exception as e:
        err(f'查询座位预约失败：{e}')
        return False

    active = [r for r in records
              if str(r.get('status', '')).upper() not in ('FINISHED', 'CANCELED', 'AUTO_CANCELED')]
    hidden_count = len(records) - len(active)

    if not active:
        if hidden_count:
            info(f'{date} 该座位暂无有效占用（已隐藏 {hidden_count} 条已结束/已取消记录）')
        else:
            info(f'{date} 该座位暂无预约记录')
        return True

    info(f'{date} 该座位已有以下预约：')
    for r in active:
        print(f"    {C_DIM}{r.get('startTime','?')} ~ {r.get('endTime','?')}  状态：{r.get('status','?')}{C_RESET}")
    if hidden_count:
        info(f'已隐藏 {hidden_count} 条已结束/已取消记录')
    return True


def create_seat_reservation(seat_id, date, start_time, end_time):
    url = f'{BASE_URL}/v1/seat-applications'
    payload = {
        'seatId': seat_id,
        'startTime': f'{date} {start_time}',
        'endTime': f'{date} {end_time}',
        'needMaterial': False,
        'scan': False,
        'use': False,
    }
    prog(f'提交座位预约：{json.dumps(payload, ensure_ascii=False)}')
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10,
                             verify=VERIFY_TLS)
    except requests.RequestException as e:
        err(f'请求失败：{e}')
        return None

    try:
        data = resp.json()
    except ValueError:
        data = {'message': (resp.text or '').strip()[:200] or '响应不是合法 JSON'}
    if not isinstance(data, dict):
        data = {'data': data}
    data['_httpStatus'] = resp.status_code
    data['_submitOk'] = bool(200 <= resp.status_code < 300 and data.get('id') and data.get('status'))
    info(f'接口返回：{json.dumps(data, ensure_ascii=False, indent=2)}')
    return data


def list_meeting_rooms(date, start_time, end_time):
    url = f"{BASE_URL}/v1/meeting-rooms"
    params = {
        "date": date,
        "startTime": f"{date} {start_time}",
        "endTime": f"{date} {end_time}",
    }
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10, verify=VERIFY_TLS)
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("content") or data.get("data") or []
    except Exception as e:
        err(f"查询会议室列表失败：{e}")
        return []


def show_available_meeting_rooms(date, start_time, end_time):
    rooms = list_meeting_rooms(date, start_time, end_time)
    if not rooms:
        info("该时间段暂无可用会议室")
        return
    info("可用会议室列表：")
    for r in rooms:
        print(f"    {r.get('id')}  {r.get('name')}  {r.get('parentNamePath','')}")


def create_meeting_reservation(room_id, date, start_time, end_time, title, content, attendees):
    try:
        start_time = parse_hm(start_time, '会议室开始时间')
        end_time = parse_hm(end_time, '会议室结束时间')
        if start_time >= end_time:
            raise ValueError('会议室结束时间必须晚于开始时间')
    except ValueError as e:
        err(str(e))
        return {'message': str(e), '_httpStatus': 400, '_submitOk': False}

    url = f"{BASE_URL}/v1/meeting-applications"
    payload = {
        "meetingRoomId": room_id,
        "startTime": f"{date} {start_time}",
        "endTime": f"{date} {end_time}",
        "meetingTitle": title,
        "meetingContent": content,
        "attendees": attendees,
        "scan": False,
    }
    prog(f"提交会议室预约：{json.dumps(payload, ensure_ascii=False)}")
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10, verify=VERIFY_TLS)
    except requests.RequestException as e:
        err(f'请求失败：{e}')
        return None

    try:
        data = resp.json()
    except ValueError:
        data = {'message': (resp.text or '').strip()[:200] or '响应不是合法 JSON'}
    if not isinstance(data, dict):
        data = {'data': data, 'message': '上游响应格式异常'}
    data['_httpStatus'] = resp.status_code
    data['_submitOk'] = bool(
        200 <= resp.status_code < 300
        and data.get('id') and data.get('status')
    )
    info(f"接口返回：{json.dumps(data, ensure_ascii=False, indent=2)}")
    return data


def _submit_slot_with_retry(room_id, date, st, et, title, content, attendees,
                            max_attempts=None, retry_delay=None):
    '''提交单段会议室预约：网络失败或上游临时错误补发，补发前先复查。'''
    try:
        max_attempts = int(max_attempts if max_attempts is not None else SLOT_MAX_ATTEMPTS)
    except (TypeError, ValueError):
        max_attempts = 2
    max_attempts = max(1, max_attempts)
    try:
        retry_delay = float(retry_delay if retry_delay is not None else SLOT_RETRY_DELAY)
    except (TypeError, ValueError):
        retry_delay = 1.0
    retry_delay = max(0.0, retry_delay)

    try:
        st = parse_hm(st, '会议室开始时间')
        et = parse_hm(et, '会议室结束时间')
        if st >= et:
            raise ValueError('会议室结束时间必须晚于开始时间')
    except ValueError as e:
        _submit_warn(str(e))
        return {'message': str(e), '_httpStatus': 400, '_submitOk': False}

    result = None
    for attempt in range(1, max_attempts + 1):
        result = create_meeting_reservation(
            room_id, date, st, et, title, content, attendees
        )
        if _submit_succeeded(result):
            return result
        if isinstance(result, dict) and not _retryable_submit_result(result):
            if _submit_result_ambiguous(result):
                existing = verify_own_slot(
                    'MEETING_ROOM', room_id, st, et, date=date
                )
                if existing:
                    _submit_ok(f'会议室预约 {st}~{et} 已生效，跳过重复提交')
                    return existing
            return result

        if attempt >= max_attempts:
            break

        reason = _submit_failure_message(result, '上游临时错误')
        _submit_warn(
            f'会议室预约 {st}~{et} 第 {attempt} 次提交失败（{reason}），'
            f'{retry_delay}s 后补发...'
        )
        time.sleep(retry_delay)

        existing = verify_own_slot('MEETING_ROOM', room_id, st, et, date=date)
        if existing:
            _submit_ok(f'会议室预约 {st}~{et} 已生效，跳过重复提交')
            return existing

    if (result is None or _retryable_submit_result(result)
            or _submit_result_ambiguous(result)):
        existing = verify_own_slot('MEETING_ROOM', room_id, st, et, date=date)
        if existing:
            _submit_ok(f'会议室预约 {st}~{et} 已生效（复查确认）')
            return existing
    return result


_FORMAT_ERROR_HINTS = (
    'json parse error', 'localdatetime', 'datetimeparseexception',
    'failed to deserialize', 'cannot deserialize', 'could not be parsed',
    'invalidformat', 'invalid format', '格式错误', '时间格式',
)
_RETRYABLE_STATUS = (408, 425, 429, 500, 502, 503, 504)
_RETRYABLE_HINTS = (
    '数据库', 'database', '系统繁忙', '服务繁忙', '系统错误', 'busy',
    '请稍后', '稍后再试', '稍后重试', 'timeout', 'timed out',
    'internal error', 'server error', 'gateway', 'too many requests',
    '限流', '死锁', 'deadlock', '连接超时', '连接失败', 'connection reset',
    'temporarily',
)
_NON_RETRYABLE_HINTS = _FORMAT_ERROR_HINTS + (
    'user_has_other_reservation', '已被预约', '已存在', '冲突', '重复预约',
    'unauthorized', 'forbidden', 'token', '登录状态失效',
)


def _submit_succeeded(data):
    '''统一判定提交是否真正成功，兼容上游原始字段和复查生成的字段。'''
    return bool(
        isinstance(data, dict)
        and (data.get('_submitOk') or (data.get('id') and data.get('status')))
    )


def _submit_failure_message(data, default='上游临时错误'):
    if not isinstance(data, dict):
        return '无返回（补发后仍无响应）'
    message = (data.get('message') or data.get('msg')
               or data.get('error') or data.get('code') or default)
    text = str(message).strip() or default
    if any(hint in text.lower() for hint in _FORMAT_ERROR_HINTS):
        return '上游不接受当前时间格式，请检查开始/结束时间'
    return text


def _submit_result_ambiguous(data):
    '''空对象、无业务字段的返回无法判断成败，需要用活跃列表复查。'''
    if not isinstance(data, dict) or _submit_succeeded(data):
        return False
    return not any(data.get(key) for key in ('code', 'message', 'msg', 'error'))


def _retryable_submit_result(data):
    '''只补发系统级临时错误；业务冲突/格式/鉴权错误不重复提交。'''
    if not isinstance(data, dict):
        return False
    if data.get('_submitOk') or (data.get('id') and data.get('status')):
        return False
    blob = ' '.join(str(data.get(key) or '') for key in ('code', 'message', 'msg', 'error')).lower()
    if any(hint in blob for hint in _NON_RETRYABLE_HINTS):
        return False
    try:
        status = int(data.get('_httpStatus') or 0)
    except (TypeError, ValueError):
        status = 0
    if status in (400, 401, 403, 404, 409, 422):
        return False
    if status in _RETRYABLE_STATUS:
        return True
    return any(hint in blob for hint in _RETRYABLE_HINTS)


def _is_main_thread():
    return threading.current_thread() is threading.main_thread()


def _submit_warn(message):
    (warn if _is_main_thread() else bg_warn)(message)


def _submit_ok(message):
    (ok if _is_main_thread() else bg_ok)(message)


def _submit_seat_with_retry(seat_id, date, st, et,
                            max_attempts=None, retry_delay=None):
    '''提交座位预约：网络失败或上游临时错误补发，补发前先查活跃列表。'''
    try:
        max_attempts = int(max_attempts if max_attempts is not None else SLOT_MAX_ATTEMPTS)
    except (TypeError, ValueError):
        max_attempts = 2
    max_attempts = max(1, max_attempts)
    try:
        retry_delay = float(retry_delay if retry_delay is not None else SLOT_RETRY_DELAY)
    except (TypeError, ValueError):
        retry_delay = 1.0
    retry_delay = max(0.0, retry_delay)

    try:
        st = parse_hm(st, '座位开始时间')
        et = parse_hm(et, '座位结束时间')
        if st >= et:
            raise ValueError('座位结束时间必须晚于开始时间')
    except ValueError as e:
        _submit_warn(str(e))
        return {'message': str(e), '_httpStatus': 400, '_submitOk': False}

    result = None
    for attempt in range(1, max_attempts + 1):
        result = create_seat_reservation(seat_id, date, st, et)
        if _submit_succeeded(result):
            return result
        if isinstance(result, dict) and not _retryable_submit_result(result):
            if _submit_result_ambiguous(result):
                existing = verify_own_slot('SEAT', seat_id, st, et, date=date)
                if existing:
                    _submit_ok(f'座位预约 {st}~{et} 已生效，跳过重复提交')
                    return existing
            return result

        if attempt >= max_attempts:
            break

        reason = _submit_failure_message(result, '上游临时错误')
        _submit_warn(
            f'座位预约 {st}~{et} 第 {attempt} 次提交失败（{reason}），'
            f'{retry_delay}s 后补发...'
        )
        time.sleep(retry_delay)

        existing = verify_own_slot('SEAT', seat_id, st, et, date=date)
        if existing:
            _submit_ok(f'座位预约 {st}~{et} 已生效，跳过重复提交')
            return existing

    if (result is None or _retryable_submit_result(result)
            or _submit_result_ambiguous(result)):
        existing = verify_own_slot('SEAT', seat_id, st, et, date=date)
        if existing:
            _submit_ok(f'座位预约 {st}~{et} 已生效（复查确认）')
            return existing
    return result


def _time_range_of(raw):
    '''从 time/startTime 中取起止 HH:MM，兼容中文、ISO、~ 等写法。'''
    found = _RE_TIME.findall(str(raw or ''))
    if len(found) < 2:
        return None
    return (f'{int(found[0][0]):02d}:{found[0][1]}',
            f'{int(found[1][0]):02d}:{found[1][1]}')


def _active_record_date(record):
    for key in ('time', 'startTime'):
        raw = record.get(key)
        if raw in (None, ''):
            continue
        text = str(raw)
        if not _text_has_explicit_date(text):
            continue
        parsed = parse_start_dt(text)
        if parsed:
            return parsed.strftime('%Y-%m-%d')
    return None


def _active_record_time_range(record):
    value = _time_range_of(record.get('time'))
    if value:
        return value
    start_dt = parse_start_dt(record.get('startTime'))
    end_dt = parse_start_dt(record.get('endTime'))
    if start_dt and end_dt:
        return (start_dt.strftime('%H:%M'), end_dt.strftime('%H:%M'))
    return None


def find_own_active_slot(resource_type, resource_id, start, end, date=None, timeout=10):
    records = get_active_reservations(timeout=timeout)
    for record in records:
        if str(record.get('type') or '').upper() != resource_type:
            continue
        resource = record.get('resource') or {}
        ids = [resource.get(key) for key in ('id', 'roomId', 'seatId')]
        if not any(value is not None and str(value) == str(resource_id) for value in ids):
            continue
        if _active_record_time_range(record) != (start, end):
            continue
        record_date = _active_record_date(record)
        if date and record_date and record_date != date:
            continue
        return record
    return None


def verify_own_slot(resource_type, resource_id, start, end, date=None, timeout=None):
    '''补发前复查；命中说明上一次提交其实已经生效。'''
    try:
        timeout = float(timeout if timeout is not None else VERIFY_TIMEOUT)
    except (TypeError, ValueError):
        timeout = 4.0
    timeout = max(0.5, timeout)
    try:
        record = find_own_active_slot(resource_type, resource_id, start, end, date, timeout)
    except Exception as e:
        _submit_warn(f'补发前复查失败（按未命中处理）：{e}')
        return None
    if not record:
        return None
    reservation_id = record.get('reservationId') or record.get('id')
    id_label = reservation_id if reservation_id is not None else '未知'
    return {
        'id': reservation_id,
        'status': record.get('status'),
        '_submitOk': True,
        '_submitMessage': f'复查发现该时段已生效（预约ID {id_label}），跳过重复提交',
    }


def get_active_reservations(timeout=10):
    url = f'{BASE_URL}/v1/users/reservations/active'
    return unwrap_list(_request_json('GET', url, timeout=timeout))


def cancel_reservation_by_type(reservation_type, reservation_id):
    if reservation_type == 'SEAT':
        url = f'{BASE_URL}/v1/seat-reservations/{reservation_id}/cancel'
        return _request_json('POST', url)
    url = f'{BASE_URL}/v1/meeting-reservations/{reservation_id}/cancel'
    return _request_json('PUT', url)


def cancel_mode():
    prog("正在获取活跃预约列表...")
    try:
        records = get_active_reservations()
    except Exception as e:
        err(f'获取活跃预约失败：{e}')
        return

    if not records:
        info("当前没有活跃预约")
        return

    seat_list    = [r for r in records if r.get("type") == "SEAT"]
    meeting_list = [r for r in records if r.get("type") == "MEETING_ROOM"]
    other_list   = [r for r in records if r.get("type") not in ("SEAT", "MEETING_ROOM")]
    all_display  = []

    if seat_list:
        print(f"\n{C_BOLD}--- 座位预约 ---{C_RESET}")
        for r in seat_list:
            res = r.get("resource") or {}
            idx = len(all_display) + 1
            print(f"  [{idx}] {C_CYAN}预约ID:{r['reservationId']}{C_RESET}  座位:{res.get('name','?')}  位置:{res.get('parentNamePath','')}  时间:{r.get('time','?')}  状态:{r.get('status','?')}")
            all_display.append(r)

    if meeting_list:
        print(f"\n{C_BOLD}--- 会议室预约 ---{C_RESET}")
        for r in meeting_list:
            res = r.get("resource") or {}
            idx = len(all_display) + 1
            print(f"  [{idx}] {C_CYAN}预约ID:{r['reservationId']}{C_RESET}  会议室:{res.get('name','?')}  主题:{r.get('meetingTitle','无')}  时间:{r.get('time','?')}  状态:{r.get('status','?')}")
            all_display.append(r)

    if other_list:
        print(f"\n{C_BOLD}--- 其他预约 ---{C_RESET}")
        for r in other_list:
            idx = len(all_display) + 1
            print(f"  [{idx}] {json.dumps(r, ensure_ascii=False)}")
            all_display.append(r)

    if not all_display:
        info("没有可取消的预约")
        return

    if len(all_display) == 1:
        chosen = all_display[0]
        c = input(f"\n只有一条预约，确认取消？(y/n): ").strip().lower()
        if c != "y":
            info("已取消操作")
            return
    else:
        try:
            idx = int(input(f"\n请输入要取消的序号 (1-{len(all_display)}): ").strip())
            if idx < 1 or idx > len(all_display):
                err("序号无效")
                return
            chosen = all_display[idx - 1]
        except ValueError:
            err("输入无效")
            return

    reservation_id   = chosen.get("reservationId")
    reservation_type = chosen.get("type", "MEETING_ROOM")
    prog(f"正在取消预约 {reservation_id}（类型：{reservation_type}）...")
    try:
        data = cancel_reservation_by_type(reservation_type, reservation_id)
        info(f"接口返回：{json.dumps(data, ensure_ascii=False, indent=2)}")
        print_cancel_result(data)
        if isinstance(data, dict) and data.get("status") == "CANCELED":
            _on_reservation_changed("取消预约")
    except Exception as e:
        err(f"请求失败：{e}")


def print_result(data):
    if data is None:
        err('预约失败：无返回数据（可能超时；请在活跃预约中确认是否已生效）')
        return
    if not isinstance(data, dict):
        err(f'预约失败：返回格式异常 {str(data)[:200]}')
        return

    if data.get('_submitMessage'):
        info(str(data['_submitMessage']))

    if _submit_succeeded(data):
        status_map = {
            "AUTO_APPROVED": "自动审核通过",
            "PENDING": "等待审核",
            "APPROVED": "审核通过",
            "RESERVED": "已预约",
            "IN_USE": "使用中",
        }
        status = data.get('status')
        status_label = status_map.get(status, status or '未知')
        ok(f"{C_BOLD}预约成功！{C_RESET}")
        print(f"    {C_BLUE}预约编号{C_RESET}：{data.get('id', '未知')}")
        print(f"    {C_BLUE}时间{C_RESET}    ：{data.get('time','?')}")
        seat = data.get("seat")
        if isinstance(seat, dict):
            print(f"    {C_BLUE}座位{C_RESET}    ：{seat.get('name','?')}  {seat.get('parentNamePath','')}")
        mr = data.get("meetingRoom")
        if isinstance(mr, dict):
            print(f"    {C_BLUE}会议室{C_RESET}  ：{mr.get('name','?')}")
        print(f"    {C_BLUE}状态{C_RESET}    ：{status_label}")
        return

    code = str(data.get("code") or "")
    message = _submit_failure_message(data, '未知错误')
    blob = ' '.join(str(data.get(key) or '') for key in ('code', 'message', 'msg', 'error')).lower()
    if code == "reservation.user_has_other_reservation":
        hint = "账号在该时段已有其他预约，请先取消后再预约"
    elif any(item in blob for item in _FORMAT_ERROR_HINTS):
        hint = "上游不接受当前时间格式；请使用 HH:MM，小时需补零（如 09:00）"
    elif "time" in code.lower() or "conflict" in code.lower():
        hint = "时间段冲突"
    elif data.get('_httpStatus') in (401, 403):
        hint = "Token 已失效，请更新配置区的 TOKEN"
    elif data.get('_httpStatus') in _RETRYABLE_STATUS:
        hint = "上游临时故障；如已补发仍失败，请在活跃预约中核对"
    else:
        hint = "时间段已被占用 / ID 有误 / 配置时间格式不正确"
    err(f"预约失败：{message}")
    print(f"    {C_DIM}可能原因：{hint}{C_RESET}")


def print_cancel_result(data):
    if data is None:
        err("取消失败：无返回数据")
        return
    if isinstance(data, dict):
        if data.get("status") == "CANCELED":
            ok("取消成功！")
            print(f"    预约ID：{data.get('id','?')}")
            print(f"    时