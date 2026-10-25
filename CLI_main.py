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
            print(f"    时间：{data.get('startTime') or data.get('time','?')}")
            return
        code    = data.get("code", "")
        message = data.get("message", "未知错误")
        err(f"取消失败：{message}")
        if code:
            print(f"    {C_DIM}错误码：{code}{C_RESET}")


def wait_until(target_time_str):
    '''等待到指定时刻；格式错误返回 False，已过则立即执行。'''
    text = str(target_time_str or '').strip()
    target = None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            target = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if target is None:
        err('WAIT_UNTIL 格式错误，应为 YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD HH:MM')
        return False

    target_label = target.strftime('%Y-%m-%d %H:%M:%S')
    info(f'定时模式：将在 {target_label} 执行预约')
    if target <= datetime.now():
        warn('WAIT_UNTIL 已过，立即执行')
        return True

    while True:
        diff = (target - datetime.now()).total_seconds()
        if diff <= 0:
            info('到达预定时间，开始执行...')
            break
        print(f'\r{C_CYAN}[…]{C_RESET} 距离执行还有 {C_BOLD}{int(diff)}{C_RESET} 秒', end='', flush=True)
        time.sleep(1)
    print()
    return True


def resolve_manual_time_range(start_input, end_input, fallback_start, fallback_end,
                              start_label='开始时间', end_label='结束时间'):
    '''在真正提交前生成手写预约时段；等待跨过 21 点后也按新时刻重算默认值。'''
    now_hm = datetime.now().strftime('%H:%M')
    start_is_default = not str(start_input or '').strip()
    end_is_default = not str(end_input or '').strip()
    start = parse_hm(start_input or now_hm, start_label)
    end = parse_hm(end_input or DEFAULT_MANUAL_END_TIME, end_label)
    if start < end:
        return start, end, False
    if start_is_default and end_is_default:
        fallback_start = parse_hm(fallback_start, '配置开始时间')
        fallback_end = parse_hm(fallback_end, '配置结束时间')
        if fallback_start >= fallback_end:
            raise ValueError('配置开始时间必须早于配置结束时间')
        return fallback_start, fallback_end, True
    raise ValueError(f'{end_label}必须晚于{start_label}')


def get_user_inlib_status(records=None):
    if records is None:
        try:
            records = get_active_reservations()
        except Exception:
            return False
    for r in records:
        if r.get("type") == "SEAT" and r.get("status") == "IN_USE":
            return True
    return False


def _notify_guard_refresh():
    """通知守护线程立即放弃等待、重新拉取预约列表。"""
    with _guard_state_lock:
        ev = _guard_state.get("refresh_event")
    if ev:
        ev.set()


def _on_reservation_changed(action="操作"):
    """
    预约或取消成功后调用：
      1. 重新从远程拉取活跃列表并打印摘要
      2. 通知守护线程立即刷新（无需等待下一个轮询周期）
    """
    prog(f"{action}成功，正在刷新预约列表...")
    try:
        records = get_active_reservations()
    except Exception as e:
        warn(f'刷新预约列表失败（不影响本次操作结果）：{e}')
        _notify_guard_refresh()
        return
    reserved = [
        r for r in records
        if r.get("status") == "RESERVED"
        and r.get("type") in ("SEAT", "MEETING_ROOM")
    ]
    if reserved:
        info(f"当前活跃预约（RESERVED，共 {len(reserved)} 条）：")
        for r in sorted(reserved, key=lambda x: parse_start_dt(x.get("time", "")) or datetime.max):
            res = r.get("resource") or {}
            type_label = "座位" if r.get("type") == "SEAT" else "会议室"
            print(f"    {C_CYAN}{type_label}{C_RESET} {res.get('name','?')}  {r.get('time','?')}  ID:{r['reservationId']}")
    else:
        info("当前无待签到预约")
    _notify_guard_refresh()


def do_auto_cancel(reservation_id, reason, reservation_type="SEAT"):
    _bg_block([
        f"{C_YELLOW}[!]{C_RESET} 触发守护：{reason}",
        f"{C_YELLOW}[!]{C_RESET} 正在自动取消预约 {reservation_id}...",
    ])
    try:
        data = cancel_reservation_by_type(reservation_type, reservation_id)
        lines = [f"{C_BLUE}[i]{C_RESET} 接口返回：{json.dumps(data, ensure_ascii=False, indent=2)}"]
        if isinstance(data, dict):
            if data.get("status") == "CANCELED":
                lines.append(f"{C_GREEN}[✓]{C_RESET} 自动取消成功！预约ID：{data.get('id','?')}")
            else:
                lines.append(f"{C_RED}[✗]{C_RESET} 取消失败：{data.get('message','未知错误')}")
        _bg_block(lines)
        if isinstance(data, dict) and data.get("status") == "CANCELED":
            _on_reservation_changed("取消预约")
    except Exception as e:
        bg_err(f"自动取消失败：{e}")


# 守护轮询间隔：每隔此秒数刷新一次活跃列表（检测预约是否消失或有更早新预约）
GUARD_POLL_INTERVAL = 10 * 60  # 10 分钟


def run_guard(reservation_id, start_dt, label_name, reservation_type="SEAT"):
    """
    守护单条预约，返回值：
      "DONE"      — 守护正常结束（签到/完成/已取消）
      "CANCELED"  — 守护期间预约已消失，守护中止
      "PREEMPTED" — 发现更早的新预约，需要切换
      "STOPPED"   — stop_event 触发，程序退出
    """
    check1_dt = start_dt + timedelta(minutes=10)
    check2_dt = start_dt + timedelta(minutes=15)

    with _guard_state_lock:
        _guard_state["current"] = {
            "reservationId": reservation_id,
            "type": reservation_type,
            "name": label_name,
            "start": start_dt.strftime("%Y-%m-%d %H:%M"),
            "check1": check1_dt.strftime("%H:%M"),
            "check2": check2_dt.strftime("%H:%M"),
            "phase": "等待预约开始",
        }

    _bg_block([
        f"{C_GREEN}[✓]{C_RESET} 开始守护 {C_BOLD}{label_name}{C_RESET}，预约开始时间：{start_dt.strftime('%H:%M')}",
        f"{C_BLUE}[i]{C_RESET} 规则1：{check1_dt.strftime('%H:%M')} 检查一次，仍为 RESERVED → 视为未到馆，自动取消",
        f"{C_BLUE}[i]{C_RESET} 规则2：{check2_dt.strftime('%H:%M')} 兜底检查，仍为 RESERVED → 强制取消",
    ])

    stop_event = _guard_state.get("stop_event")

    def set_phase(label):
        with _guard_state_lock:
            if _guard_state["current"]:
                _guard_state["current"]["phase"] = label

    def query_active():
        """返回 (当前预约状态或None, 活跃列表中最早预约的start_dt或None)"""
        records = get_active_reservations()
        my_status = None
        for r in records:
            if r.get("reservationId") == reservation_id:
                my_status = r.get("status", "UNKNOWN")
                break
        # 找出所有 RESERVED 中开始时间最早的
        candidates = [
            r for r in records
            if r.get("status") == "RESERVED"
            and r.get("type") in ("SEAT", "MEETING_ROOM")
        ]
        earliest_dt = None
        if candidates:
            candidates.sort(key=lambda r: parse_start_dt(r.get("time", "")) or datetime.max)
            earliest_dt = parse_start_dt(candidates[0].get("time", ""))
        return my_status, earliest_dt

    def wait_until_dt(target_dt, phase_label):
        """
        等待到 target_dt，期间每 GUARD_POLL_INTERVAL 秒（或到目标点，取较小值）
        刷新一次活跃列表，或收到 refresh_event 时立即刷新，检查：
          1. 当前预约是否已消失/完成 → 返回 "CANCELED"
          2. 是否有比 start_dt 更早的新预约 → 返回 "PREEMPTED"
        正常到达目标时间 → 返回 "OK"
        stop_event 触发 → 返回 "STOPPED"
        """
        set_phase(phase_label)
        with _guard_state_lock:
            refresh_ev = _guard_state.get("refresh_event")
        while True:
            if stop_event and stop_event.is_set():
                return "STOPPED"
            now = datetime.now()
            if now >= target_dt:
                return "OK"
            # 距下次定期刷新的等待时长，不超过 GUARD_POLL_INTERVAL
            secs_to_target = (target_dt - now).total_seconds()
            sleep_secs = min(secs_to_target, GUARD_POLL_INTERVAL)
            # 优先响应 refresh_event（取消/预约成功后立即唤醒）
            if refresh_ev:
                refresh_ev.clear()
                triggered = refresh_ev.wait(timeout=sleep_secs)
                # triggered=True 表示被外部信号唤醒，False 表示超时（定期刷新）
            else:
                # 无 refresh_event 则退回秒级睡眠
                deadline = datetime.now() + timedelta(seconds=sleep_secs)
                triggered = False
                while datetime.now() < deadline:
                    if stop_event and stop_event.is_set():
                        return "STOPPED"
                    time.sleep(1)
            if stop_event and stop_event.is_set():
                return "STOPPED"
            # 还没到检查点时刷新列表（定期 or 被信号唤醒）
            if datetime.now() < target_dt:
                reason = "外部信号触发" if triggered else "定期刷新"
                try:
                    my_status, earliest_dt = query_active()
                except ApiError as e:
                    if e.status in (401, 403):
                        bg_err(f'后台守护：登录状态失效，守护中止：{e}')
                        return 'STOPPED'
                    bg_warn(f'后台守护：[{reason}] 刷新失败，继续守护：{e}')
                    continue
                except Exception as e:
                    bg_warn(f'后台守护：[{reason}] 刷新失败，继续守护：{e}')
                    continue
                if my_status is None:
                    bg_warn(f"后台守护：[{reason}] 预约 {reservation_id} 已不在活跃列表，守护中止")
                    return "CANCELED"
                if my_status in ("FINISHED", "CANCELED", "AUTO_CANCELED"):
                    bg_ok(f"后台守护：[{reason}] 预约已变为 {my_status}，守护中止")
                    return "CANCELED"
                if earliest_dt and earliest_dt < start_dt:
                    bg_warn(f"后台守护：[{reason}] 发现更早预约（{earliest_dt.strftime('%H:%M')}），切换守护")
                    return "PREEMPTED"
                if triggered:
                    bg_info(f"后台守护：[外部信号] {label_name} 状态正常（{my_status}），继续守护")
                else:
                    bg_info(f"后台守护：[定期刷新] {label_name} 状态正常（{my_status}），继续守护")
        return "OK"

    # ── 等待预约开始 ──
    if datetime.now() < start_dt:
        sig = wait_until_dt(start_dt, "等待预约开始")
        if sig != "OK":
            if sig in ("CANCELED", "PREEMPTED"):
                _finalize_guard(reservation_id, label_name, sig)
            return sig

    # ── 等待规则1检查点 ──
    if datetime.now() < check1_dt:
        sig = wait_until_dt(check1_dt, "等待第一次检查")
        if sig != "OK":
            if sig in ("CANCELED", "PREEMPTED"):
                _finalize_guard(reservation_id, label_name, sig)
            return sig

    set_phase("执行规则1检查")
    bg_info(f"{datetime.now().strftime('%H:%M:%S')} 执行规则1检查（开始后10分钟）...")
    try:
        my_status, _ = query_active()
    except ApiError as e:
        if e.status in (401, 403):
            bg_err(f'规则1检查失败：登录状态失效，守护中止：{e}')
            return 'STOPPED'
        bg_err(f'规则1检查失败，跳过本次判定（不自动取消）：{e}')
        my_status = 'UNKNOWN'
    except Exception as e:
        bg_err(f'规则1检查失败，跳过本次判定（不自动取消）：{e}')
        my_status = 'UNKNOWN'
    status = my_status if my_status is not None else "FINISHED"
    bg_info(f"当前预约状态：{C_YELLOW}{status}{C_RESET}")

    if status in ("IN_USE", "FINISHED", "CANCELED", "AUTO_CANCELED"):
        bg_ok(f"预约状态为 {status}，守护结束")
        _finalize_guard(reservation_id, label_name, status)
        return "DONE"

    if status == "RESERVED":
        do_auto_cancel(reservation_id, "开始后10分钟仍未签到，视为用户未到馆", reservation_type)
        _finalize_guard(reservation_id, label_name, "AUTO_CANCELED")
        return "DONE"

    # ── 等待规则2兜底检查点 ──
    if datetime.now() < check2_dt:
        sig = wait_until_dt(check2_dt, "等待兜底检查")
        if sig != "OK":
            if sig in ("CANCELED", "PREEMPTED"):
                _finalize_guard(reservation_id, label_name, sig)
            return sig

    set_phase("执行规则2兜底")
    bg_info(f"{datetime.now().strftime('%H:%M:%S')} 执行规则2兜底检查（开始后15分钟）...")
    try:
        my_status, _ = query_active()
    except ApiError as e:
        if e.status in (401, 403):
            bg_err(f'规则2检查失败：登录状态失效，守护中止：{e}')
            return 'STOPPED'
        bg_err(f'规则2检查失败，跳过本次判定（不自动取消）：{e}')
        my_status = 'UNKNOWN'
    except Exception as e:
        bg_err(f'规则2检查失败，跳过本次判定（不自动取消）：{e}')
        my_status = 'UNKNOWN'
    status = my_status if my_status is not None else "FINISHED"
    bg_info(f"当前预约状态：{C_YELLOW}{status}{C_RESET}")

    if status == "RESERVED":
        do_auto_cancel(reservation_id, "开始后15分钟仍未签到（兜底）", reservation_type)
        _finalize_guard(reservation_id, label_name, "AUTO_CANCELED")
    else:
        bg_ok(f"预约状态为 {status}，守护结束")
        _finalize_guard(reservation_id, label_name, status)
    return "DONE"


def _finalize_guard(reservation_id, label_name, final_status):
    with _guard_state_lock:
        current = _guard_state.get("current")
        if current and current.get("reservationId") == reservation_id:
            entry = dict(current)
            entry["phase"]       = f"已完成（{final_status}）"
            entry["finish_time"] = datetime.now().strftime("%H:%M:%S")
            _guard_state["history"].append(entry)
            _guard_state["current"] = None


_RE_DATE_CN_FULL = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?')
_RE_DATE_CN_MD = re.compile(r'(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日?')
_RE_DATE_ISO = re.compile(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})')
_RE_DATE_MD = re.compile(r'(?<!\d)(\d{1,2})[-/.](\d{1,2})(?!\d)')
_RE_TIME = re.compile(r'(\d{1,2}):(\d{2})(?::(\d{2}))?')


def _text_has_explicit_date(text):
    '''判断活跃预约的时间文本是否真的带日期，避免把 HH:MM 当成今天。'''
    if not text:
        return False
    value = str(text)
    if any(pattern.search(value) for pattern in
           (_RE_DATE_CN_FULL, _RE_DATE_ISO, _RE_DATE_CN_MD)):
        return True
    return bool(_RE_DATE_MD.search(_RE_TIME.sub(' ', value)))


def parse_start_dt(time_str):
    '''从活跃列表 time 字段解析开始时间，兼容中文/ISO/HH:MM 等写法。'''
    if not time_str:
        return None
    text = str(time_str).strip()
    if not text:
        return None

    now = datetime.now()
    year = month = day = None

    match = _RE_DATE_CN_FULL.search(text)
    if match:
        year, month, day = (int(value) for value in match.groups())
    else:
        match = _RE_DATE_ISO.search(text)
        if match:
            year, month, day = (int(value) for value in match.groups())
        else:
            match = _RE_DATE_CN_MD.search(text)
            if match:
                year = now.year
                month, day = int(match.group(1)), int(match.group(2))
            else:
                stripped = _RE_TIME.sub(' ', text)
                match = _RE_DATE_MD.search(stripped)
                if match:
                    year = now.year
                    month, day = int(match.group(1)), int(match.group(2))

    if month is None or day is None:
        year, month, day = now.year, now.month, now.day

    time_match = _RE_TIME.search(text)
    if not time_match:
        return None
    try:
        return datetime(year, month, day,
                        int(time_match.group(1)), int(time_match.group(2)))
    except ValueError:
        return None


def get_next_reserved(exclude_ids=None):
    if exclude_ids is None:
        exclude_ids = set()
    records = get_active_reservations()
    candidates = [
        r for r in records
        if r.get("status") == "RESERVED"
        and r.get("type") in ("SEAT", "MEETING_ROOM")
        and r.get("reservationId") not in exclude_ids
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda r: parse_start_dt(r.get("time", "")) or datetime.max)
    return candidates[0]


def _continuous_guard_worker(initial_exclude_ids=None):
    with _guard_state_lock:
        _guard_state["running"]       = True
        _guard_state["current"]       = None
        refresh_event                  = threading.Event()
        _guard_state["refresh_event"] = refresh_event

    # guarded_ids 仅用于跳过解析失败的异常预约，正常情况不排除已守护的 ID，
    # 以便每次都从活跃列表中重新选出最早的 RESERVED 预约。
    skip_ids   = set(initial_exclude_ids or [])  # 解析失败才加入
    stop_event = _guard_state.get("stop_event")

    try:
        while not (stop_event and stop_event.is_set()):
            # 每次循环都从远程拉取最新列表，选出最早的 RESERVED 预约
            try:
                chosen = get_next_reserved(exclude_ids=skip_ids)
            except ApiError as e:
                if e.status in (401, 403):
                    bg_err(f'后台守护：登录状态失效，签到守护停止：{e}')
                    break
                bg_warn(f'后台守护：拉取预约列表失败，30 秒后重试：{e}')
                refresh_event.wait(timeout=30)
                continue
            except Exception as e:
                bg_warn(f'后台守护：拉取预约列表失败，30 秒后重试：{e}')
                refresh_event.wait(timeout=30)
                continue

            if chosen is None:
                # 没有待签到预约，等待10分钟（或被取消成功立即唤醒）后再查
                with _guard_state_lock:
                    if _guard_state["current"] is not None:
                        _guard_state["current"] = None
                bg_info(f"后台守护：暂无待签到预约，{GUARD_POLL_INTERVAL // 60} 分钟后再次检查...")
                refresh_event.clear()
                refresh_event.wait(timeout=GUARD_POLL_INTERVAL)
                if stop_event and stop_event.is_set():
                    break
                continue

            reservation_id   = chosen["reservationId"]
            reservation_type = chosen.get("type", "SEAT")
            res              = chosen.get("resource") or {}
            resource_name    = res.get("name", "?")
            type_label       = "座位" if reservation_type == "SEAT" else "会议室"
            time_str         = chosen.get("time", "?")
            start_dt         = parse_start_dt(time_str)

            if not start_dt:
                err(f"后台守护：无法解析时间 {time_str}，跳过该预约")
                skip_ids.add(reservation_id)  # 解析失败才永久跳过
                continue

            bg_arrow(f"后台守护：开始守护 {C_BOLD}{type_label} {resource_name}{C_RESET}  "
                     f"时间：{time_str}  预约ID：{reservation_id}")

            sig = run_guard(reservation_id, start_dt,
                            f"{type_label} {resource_name}", reservation_type)

            if sig == "PREEMPTED":
                # 有更早的预约，立即重新拉取列表切换守护，不需要等待
                bg_info("后台守护：切换到更早的预约...")
                continue
            elif sig == "STOPPED":
                break
            else:
                # DONE / CANCELED：守护完成，立即重新拉取看有无剩余
                bg_info("后台守护：本轮结束，检查是否还有待签到预约...")
                continue
    finally:
        with _guard_state_lock:
            _guard_state["running"]       = False
            _guard_state["current"]       = None
            _guard_state["thread"]        = None
            _guard_state["refresh_event"] = None


def start_background_guard(initial_exclude_ids=None):
    with _guard_state_lock:
        old_thread = _guard_state.get("thread")
        if _guard_state["running"] or (old_thread and old_thread.is_alive()):
            info("后台守护已在运行中")
            return
        stop_event = threading.Event()
        _guard_state["stop_event"]    = stop_event
        _guard_state["refresh_event"] = None
        _guard_state["history"]       = []
        _guard_state["running"]       = True

    t = threading.Thread(
        target=_continuous_guard_worker,
        args=(initial_exclude_ids,),
        daemon=True,
        name="CheckinGuard"
    )
    with _guard_state_lock:
        _guard_state["thread"] = t
    try:
        t.start()
    except Exception as e:
        with _guard_state_lock:
            _guard_state["running"] = False
            _guard_state["thread"] = None
        err(f"后台签到守护启动失败：{e}")
        return
    ok("后台签到守护线程已启动，输入 g 可随时查看状态")


def show_guard_status():
    with _guard_state_lock:
        running = _guard_state["running"]
        current = _guard_state["current"]
        history = list(_guard_state["history"])

    print(f"\n{C_BOLD}{'=' * 44}{C_RESET}")
    print(f"{C_BOLD}  后台签到守护状态{C_RESET}")
    print(f"{C_BOLD}{'=' * 44}{C_RESET}")

    if not running and current is None and not history:
        info("守护线程未启动")
    elif running:
        print(f"  状态：{C_GREEN}运行中{C_RESET}")
        if current:
            print(f"  {C_BOLD}当前守护{C_RESET}：{C_CYAN}{current.get('name','?')}{C_RESET}")
            print(f"    预约ID    : {current.get('reservationId','?')}")
            print(f"    类型      : {'座位' if current.get('type') == 'SEAT' else '会议室'}")
            print(f"    开始时间  : {current.get('start','?')}")
            print(f"    当前阶段  : {C_YELLOW}{current.get('phase','?')}{C_RESET}")
            print(f"    规则1检查 : {current.get('check1','?')}")
            print(f"    规则2兜底 : {current.get('check2','?')}")
        else:
            info("等待下一个待签到预约...")
    else:
        print(f"  状态：{C_DIM}已结束{C_RESET}")

    if history:
        print(f"\n  {C_BOLD}已处理记录（{len(history)} 条）：{C_RESET}")
        for i, h in enumerate(history, 1):
            phase = h.get('phase', '?')
            color = C_GREEN if "IN_USE" in phase or "FINISHED" in phase else C_RED
            print(f"    [{i}] {h.get('name','?')}  开始:{h.get('start','?')}  "
                  f"结果:{color}{phase}{C_RESET}  完成:{h.get('finish_time','?')}")
    print(f"{C_BOLD}{'=' * 44}{C_RESET}\n")


def send_email(subject, body):
    """通用邮件发送函数。"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.header import Header
    from email.utils import formataddr

    if not EMAIL_SENDER or not EMAIL_RECEIVER or not EMAIL_SMTP_AUTHCODE:
        warn("邮件配置不完整，跳过邮件发送")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"]    = formataddr(("图书馆预约助手", EMAIL_SENDER))
        msg["To"]      = formataddr(("", EMAIL_RECEIVER))
        msg["Subject"] = Header(subject, "utf-8")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=15) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_SMTP_AUTHCODE)
            smtp.sendmail(EMAIL_SENDER, [EMAIL_RECEIVER], msg.as_string())
        ok(f"邮件已发送至 {EMAIL_RECEIVER}")
        return True
    except smtplib.SMTPAuthenticationError:
        err("邮件发送失败：SMTP 认证错误，请检查授权码是否正确")
    except smtplib.SMTPException as e:
        err(f"邮件发送失败（SMTP 错误）：{e}")
    except Exception as e:
        err(f"邮件发送失败：{e}")
    return False


def send_token_expired_email(extra_msg=""):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""您好，

检测到吉林大学图书馆预约助手的 Token 已失效。

失效时间：{now_str}
{('附加信息：' + extra_msg) if extra_msg else ''}

请重新登录吉林大学图书馆系统，通过浏览器抓包获取新的 Token，并更新脚本配置区中的 TOKEN 字段后重新启动。

此邮件由预约助手自动发送，请勿回复。
"""
    subject = "【图书馆预约助手】Token 已失效，请及时更新"
    return send_email(subject, body)


def _token_monitor_worker(interval_min=10, stop_event=None):
    try:
        interval_sec = max(60, int(float(interval_min) * 60))
    except (TypeError, ValueError):
        interval_sec = 600
    notified = False

    while not (stop_event and stop_event.is_set()):
        user_id   = parse_user_id_from_token(TOKEN)
        is_valid   = False
        is_transient = False       # 网络/上游临时异常：本轮不判定 Token 失效
        detail_msg = ""

        if not user_id:
            detail_msg = "Token 格式无法解析"
        else:
            url = f"{BASE_URL}/v1/users/{user_id}/detail"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=10, verify=VERIFY_TLS)
                if resp.status_code == 200:
                    data = resp.json()
                    nickname = data.get("nickname") if isinstance(data, dict) else None
                    if nickname:
                        is_valid = True
                        notified = False
                    else:
                        detail_msg = data.get("message", "无法获取用户信息") if isinstance(data, dict) else "响应格式异常"
                elif resp.status_code in (401, 403):
                    detail_msg = f"HTTP {resp.status_code}"
                else:
                    is_transient = True
                    detail_msg = f"HTTP {resp.status_code}（本轮无法判定）"
            except requests.exceptions.ConnectTimeout as e:
                is_transient = True
                detail_msg = f"连接超时：{e}"
            except requests.exceptions.ReadTimeout as e:
                is_transient = True
                detail_msg = f"读取超时：{e}"
            except requests.exceptions.ConnectionError as e:
                is_transient = True
                detail_msg = f"连接异常：{e}"
            except requests.exceptions.Timeout as e:
                is_transient = True
                detail_msg = f"请求超时：{e}"
            except Exception as e:
                # 其余未识别异常，保守起见也不当作Token失效，避免误报
                is_transient = True
                detail_msg = str(e)

        if is_transient:
            # 网络/服务器抖动：仅提示，不判定失效、不发邮件、不改变 notified 状态
            bg_warn(f"[{datetime.now().strftime('%H:%M:%S')}] 后台检测：上游暂时不可用，本轮跳过（{detail_msg}）")
        elif not is_valid and not notified:
            bg_warn(f"[{datetime.now().strftime('%H:%M:%S')}] 后台检测：Token 已失效（{detail_msg}），正在发送提醒邮件...")
            if send_token_expired_email(detail_msg):
                notified = True

        for _ in range(interval_sec):
            if stop_event and stop_event.is_set():
                return
            time.sleep(1)


# ==================== 定时会议室预约状态 ====================
_scheduler_state = {
    "enabled": False,
    "thread": None,
    "stop_event": None,
    "last_run": None,       # 上次执行日期 ("YYYY-MM-DD")
    "last_result": None,    # 上次执行结果摘要
}
_scheduler_state_lock = threading.Lock()
# ==========================================================


def _scheduled_split_worker(stop_event):
    """
    每天 SCHEDULER_TRIGGER_TIME 自动执行一次分时段会议室预约
    （使用配置默认值，粒度1小时，日期自动推断）。
    每段间隔 SLOT_SUBMIT_INTERVAL 秒；单段无返回时按补发规则重试。
    """
    try:
        trigger_hm = parse_hm(SCHEDULER_TRIGGER_TIME, 'SCHEDULER_TRIGGER_TIME')
        _th, _tm = map(int, trigger_hm.split(':'))
        room_id = int(str(MEETING_ROOM_ID).strip())
        start_hm = parse_hm(MEETING_START_TIME, 'MEETING_START_TIME')
        end_hm = parse_hm(MEETING_END_TIME, 'MEETING_END_TIME')
        if start_hm >= end_hm:
            raise ValueError('MEETING_START_TIME 必须早于 MEETING_END_TIME')
        try:
            slot_interval = max(0.0, float(SLOT_SUBMIT_INTERVAL))
        except (TypeError, ValueError):
            slot_interval = 0.5

        while not stop_event.is_set():
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            trigger_today = now.replace(hour=_th, minute=_tm, second=0, microsecond=0)

            with _scheduler_state_lock:
                last_run = _scheduler_state['last_run']

            if now >= trigger_today:
                # 启动时错过当天触发点则补跑一次；已在当天跑过则等明天。
                trigger_dt = now if last_run != today else trigger_today + timedelta(days=1)
            else:
                trigger_dt = trigger_today

            secs_to_wait = (trigger_dt - datetime.now()).total_seconds()
            bg_info(
                f"定时会议室预约：下次执行时间 {trigger_dt.strftime('%Y-%m-%d %H:%M')}"
                f"（约 {int(secs_to_wait // 3600)} 小时后）"
            )

            while not stop_event.is_set():
                remaining = (trigger_dt - datetime.now()).total_seconds()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 30))

            if stop_event.is_set():
                break

            run_day = datetime.now().strftime('%Y-%m-%d')
            target_date = get_default_date()
            bg_info(
                f"定时会议室预约：开始执行，目标日期 {target_date}，"
                f"会议室ID {room_id}，时间 {start_hm}~{end_hm}，粒度 1 小时"
            )

            slots = split_time_slots(target_date, start_hm, end_hm, 1)
            if not slots:
                raise ValueError('定时会议室预约时段无效，请检查 MEETING_START_TIME / MEETING_END_TIME')

            success_count = 0
            fail_count = 0
            slot_results = []
            lines = [f"{C_BLUE}[i]{C_RESET} 定时会议室预约：共 {len(slots)} 段，开始提交..."]

            for i, (slot_start, slot_end) in enumerate(slots, 1):
                st = slot_start.split()[1]
                et = slot_end.split()[1]
                result = _submit_slot_with_retry(
                    room_id, target_date, st, et,
                    MEETING_TITLE, MEETING_CONTENT, MEETING_ATTENDEES
                )
                if _submit_succeeded(result):
                    success_count += 1
                    slot_results.append((st, et, True, ''))
                    lines.append(f"{C_GREEN}[✓]{C_RESET}  [{i}/{len(slots)}] {st}~{et} 预约成功")
                else:
                    fail_count += 1
                    msg = _submit_failure_message(result, '未知错误')
                    slot_results.append((st, et, False, msg))
                    lines.append(f"{C_RED}[✗]{C_RESET}  [{i}/{len(slots)}] {st}~{et} 失败：{msg}")
                if i < len(slots):
                    time.sleep(slot_interval)

            summary = f"成功 {success_count}/{len(slots)} 段"
            lines.append(
                f"{C_GREEN if fail_count == 0 else C_YELLOW}"
                f"[{'✓' if fail_count == 0 else '!'}]{C_RESET} "
                f"定时会议室预约完成：{summary}"
            )
            _bg_block(lines)

            with _scheduler_state_lock:
                _scheduler_state['last_run'] = run_day
                _scheduler_state['last_result'] = summary
            _save_cli_state(
                meeting_last_run=run_day,
                meeting_last_result=summary,
                meeting_last_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            )

            _send_scheduler_report_email(
                target_date, slots, slot_results, success_count, fail_count
            )

            if success_count > 0:
                _on_reservation_changed('定时分段预约')
    except Exception as e:
        bg_err(f'定时会议室预约线程异常退出：{e}')
    finally:
        with _scheduler_state_lock:
            if _scheduler_state.get('thread') is threading.current_thread():
                _scheduler_state['enabled'] = False
                _scheduler_state['thread'] = None


def _send_scheduler_report_email(target_date, slots, slot_results, success_count, fail_count):
    """定时预约执行完毕后发送汇报邮件。"""
    now_str     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total       = len(slots)
    all_ok      = fail_count == 0
    result_icon = "✅ 全部成功" if all_ok else (f"❌ 全部失败" if success_count == 0 else f"⚠️ 部分成功")

    subject = f"【图书馆预约助手】{target_date} 定时分段预约汇报｜{result_icon}"

    lines = [
        f"您好，",
        f"",
        f"定时分段预约已于 {now_str} 执行完毕。",
        f"",
        f"═" * 40,
        f"目标日期：{target_date}",
        f"会议室：ID {MEETING_ROOM_ID}",
        f"主题：{MEETING_TITLE}",
        f"共 {total} 段，成功 {success_count} 段，失败 {fail_count} 段",
        f"═" * 40,
        f"",
        f"分段详情：",
    ]
    for i, (st, et, ok_flag, msg) in enumerate(slot_results, 1):
        status = "✅ 成功" if ok_flag else f"❌ 失败：{msg}"
        lines.append(f"  [{i}/{total}] {st} ~ {et}  {status}")

    lines += [
        f"",
        f"此邮件由预约助手自动发送，请勿回复。",
    ]
    body = "\n".join(lines)
    send_email(subject, body)


def _validate_meeting_scheduler_config():
    try:
        room_id = int(str(MEETING_ROOM_ID).strip())
    except (TypeError, ValueError):
        return 'MEETING_ROOM_ID 必须是整数'
    if room_id <= 0:
        return 'MEETING_ROOM_ID 必须大于 0'
    try:
        start = parse_hm(MEETING_START_TIME, 'MEETING_START_TIME')
        end = parse_hm(MEETING_END_TIME, 'MEETING_END_TIME')
        parse_hm(SCHEDULER_TRIGGER_TIME, 'SCHEDULER_TRIGGER_TIME')
    except ValueError as e:
        return str(e)
    if start >= end:
        return 'MEETING_START_TIME 必须早于 MEETING_END_TIME'
    if not isinstance(MEETING_ATTENDEES, list):
        return 'MEETING_ATTENDEES 必须是列表，例如 [12345, 67890]'
    for attendee in MEETING_ATTENDEES:
        try:
            if int(str(attendee).strip()) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return f'MEETING_ATTENDEES 含无效用户 ID：「{attendee}」'
    return None


def start_scheduler():
    with _scheduler_state_lock:
        old_thread = _scheduler_state.get('thread')
        if _scheduler_state["enabled"] or (old_thread and old_thread.is_alive()):
            info("定时分段预约已在运行中")
            return

    problem = _validate_meeting_scheduler_config()
    if problem:
        err(f'定时会议室预约配置有误：{problem}')
        return
    if not check_token():
        err('Token 无效，无法开启定时会议室预约；请更新 TOKEN 后重试')
        return

    saved_state = _load_cli_state()
    with _scheduler_state_lock:
        if _scheduler_state["enabled"]:
            info("定时分段预约已在运行中")
            return
        _scheduler_state['last_run'] = saved_state.get('meeting_last_run')
        _scheduler_state['last_result'] = saved_state.get('meeting_last_result')
        stop_event = threading.Event()
        _scheduler_state["stop_event"] = stop_event
        _scheduler_state["enabled"]    = True

    t = threading.Thread(
        target=_scheduled_split_worker,
        args=(stop_event,),
        daemon=True,
        name="ScheduledReservation"
    )
    with _scheduler_state_lock:
        _scheduler_state["thread"] = t
    try:
        t.start()
    except Exception as e:
        with _scheduler_state_lock:
            _scheduler_state['enabled'] = False
            _scheduler_state['thread'] = None
        err(f'定时分段预约启动失败：{e}')
        return
    trigger_hm = parse_hm(SCHEDULER_TRIGGER_TIME, 'SCHEDULER_TRIGGER_TIME')
    ok(f"定时分段预约已启动（每天 {trigger_hm} 自动预约会议室）")


def stop_scheduler():
    with _scheduler_state_lock:
        if not _scheduler_state["enabled"]:
            info("定时分段预约未在运行")
            return
        ev = _scheduler_state["stop_event"]
        _scheduler_state["enabled"] = False

    if ev:
        ev.set()
    ok("定时分段预约已关闭")


# ==================== 定时座位预约状态 ====================
_seat_scheduler_state = {
    "enabled": False,
    "thread": None,
    "stop_event": None,
    "last_run": None,
    "last_result": None,
}
_seat_scheduler_state_lock = threading.Lock()
# ==========================================================


_CLI_STATE_FILE = os.path.join(os.path.expanduser('~'), '.jlu_libseat_cli_state.json')
_cli_state_lock = threading.RLock()


def _load_cli_state():
    with _cli_state_lock:
        try:
            with open(_CLI_STATE_FILE, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            _submit_warn(f'读取本地状态失败：{e}')
            return {}


def _save_cli_state(**values):
    with _cli_state_lock:
        try:
            state = _load_cli_state()
            state.update(values)
            tmp_path = _CLI_STATE_FILE + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, _CLI_STATE_FILE)
        except Exception as e:
            _submit_warn(f'保存本地状态失败：{e}')


def _validate_seat_scheduler_config():
    try:
        seat_id = int(str(SEAT_ID).strip())
    except (TypeError, ValueError):
        return 'SEAT_ID 必须是整数'
    if seat_id <= 0:
        return 'SEAT_ID 必须大于 0'
    try:
        start = parse_hm(START_TIME, 'START_TIME')
        end = parse_hm(END_TIME, 'END_TIME')
    except ValueError as e:
        return str(e)
    if start >= end:
        return 'START_TIME 必须早于 END_TIME'
    try:
        parse_hm(SEAT_SCHEDULER_TRIGGER_TIME, 'SEAT_SCHEDULER_TRIGGER_TIME')
    except ValueError as e:
        return str(e)
    return None


def _prewarm_upstream():
    '''触发前轻量探测一次，提前暴露 Token/网络问题。'''
    user_id = parse_user_id_from_token(TOKEN)
    if not user_id:
        bg_warn('定时座位预约：预热跳过，Token 格式无法解析')
        return
    try:
        resp = requests.get(f'{BASE_URL}/v1/users/{user_id}/detail',
                            headers=HEADERS, timeout=5, verify=VERIFY_TLS)
        if resp.status_code == 200:
            bg_info('定时座位预约：上游预热完成')
        else:
            bg_warn(f'定时座位预约：预热返回 HTTP {resp.status_code}（不影响正式提交）')
    except Exception as e:
        bg_warn(f'定时座位预约：预热失败（不影响正式提交）：{e}')


def _scheduled_seat_worker(stop_event):
    '''每天触发一次座位预约；重启后补跑当天未执行的触发点。'''
    try:
        trigger_hm = parse_hm(SEAT_SCHEDULER_TRIGGER_TIME, 'SEAT_SCHEDULER_TRIGGER_TIME')
        _th, _tm = map(int, trigger_hm.split(':'))
        seat_id = int(str(SEAT_ID).strip())
        start_hm = parse_hm(START_TIME, 'START_TIME')
        end_hm = parse_hm(END_TIME, 'END_TIME')
        if start_hm >= end_hm:
            raise ValueError('START_TIME 必须早于 END_TIME')

        while not stop_event.is_set():
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            trigger_today = now.replace(hour=_th, minute=_tm, second=0, microsecond=0)
            with _seat_scheduler_state_lock:
                last_run = _seat_scheduler_state.get('last_run')

            if now >= trigger_today:
                if last_run == today:
                    trigger_dt = trigger_today + timedelta(days=1)
                else:
                    trigger_dt = now
            else:
                trigger_dt = trigger_today

            secs_to_wait = (trigger_dt - datetime.now()).total_seconds()
            trigger_label = trigger_dt.strftime('%Y-%m-%d %H:%M')
            bg_info(f'定时座位预约：下次执行时间 {trigger_label}（约 {int(secs_to_wait // 3600)} 小时后）')

            prewarmed = False
            while not stop_event.is_set():
                remaining = (trigger_dt - datetime.now()).total_seconds()
                if remaining <= 0:
                    break
                if remaining <= 30 and not prewarmed:
                    _prewarm_upstream()
                    prewarmed = True
                time.sleep(min(remaining, 1 if remaining <= 30 else 30))

            if stop_event.is_set():
                break

            run_date = datetime.now().strftime('%Y-%m-%d')
            target_date = get_default_date()
            bg_info(f'定时座位预约：开始执行，目标日期 {target_date}，座位ID {seat_id}，时间 {start_hm}~{end_hm}')

            result = _submit_seat_with_retry(seat_id, target_date, start_hm, end_hm)
            success = _submit_succeeded(result)
            if success:
                reservation_id = result.get('id') or '未知'
                msg = f'预约成功，预约ID：{reservation_id}'
                extra = result.get('_submitMessage')
                if extra:
                    msg += f'；{extra}'
                bg_ok(f'定时座位预约完成：{msg}')
            else:
                msg = _submit_failure_message(result, '未知错误')
                bg_err(f'定时座位预约失败：{msg}')

            with _seat_scheduler_state_lock:
                _seat_scheduler_state['last_run'] = run_date
                _seat_scheduler_state['last_result'] = msg
            _save_cli_state(seat_last_run=run_date, seat_last_result=msg,
                            seat_last_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

            _send_seat_scheduler_report_email(target_date, success, msg)

            if success:
                _on_reservation_changed('定时座位预约')
    except Exception as e:
        bg_err(f'定时座位预约线程异常退出：{e}')
    finally:
        with _seat_scheduler_state_lock:
            if _seat_scheduler_state.get('thread') is threading.current_thread():
                _seat_scheduler_state['enabled'] = False
                _seat_scheduler_state['thread'] = None


def _send_seat_scheduler_report_email(target_date, success, msg):
    """定时座位预约执行完毕后发送汇报邮件。"""
    now_str     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result_icon = "✅ 成功" if success else "❌ 失败"

    subject = f"【图书馆预约助手】{target_date} 定时座位预约汇报｜{result_icon}"
    body = f"""您好，

定时座位预约已于 {now_str} 执行完毕。

目标日期：{target_date}
座位ID：{SEAT_ID}
预约时间：{START_TIME} ~ {END_TIME}
结果：{result_icon}
详情：{msg}

此邮件由预约助手自动发送，请勿回复。
"""
    send_email(subject, body)


def start_seat_scheduler():
    with _seat_scheduler_state_lock:
        old_thread = _seat_scheduler_state.get('thread')
        if _seat_scheduler_state['enabled'] or (old_thread and old_thread.is_alive()):
            info('定时座位预约已在运行中')
            return

    problem = _validate_seat_scheduler_config()
    if problem:
        err(f'定时座位预约配置有误：{problem}')
        return
    if not check_token():
        err('Token 无效，无法开启定时座位预约；请更新 TOKEN 后重试')
        return

    state = _load_cli_state()
    with _seat_scheduler_state_lock:
        if _seat_scheduler_state['enabled']:
            info('定时座位预约已在运行中')
            return
        _seat_scheduler_state['last_run'] = state.get('seat_last_run')
        _seat_scheduler_state['last_result'] = state.get('seat_last_result')
        stop_event = threading.Event()
        _seat_scheduler_state['stop_event'] = stop_event
        _seat_scheduler_state['enabled'] = True

    t = threading.Thread(
        target=_scheduled_seat_worker,
        args=(stop_event,),
        daemon=True,
        name='ScheduledSeatReservation'
    )
    with _seat_scheduler_state_lock:
        _seat_scheduler_state['thread'] = t
    try:
        t.start()
    except Exception as e:
        with _seat_scheduler_state_lock:
            _seat_scheduler_state['enabled'] = False
            _seat_scheduler_state['thread'] = None
        err(f'定时座位预约启动失败：{e}')
        return
    trigger_hm = parse_hm(SEAT_SCHEDULER_TRIGGER_TIME, 'SEAT_SCHEDULER_TRIGGER_TIME')
    ok(f'定时座位预约已启动（每天 {trigger_hm} 自动预约座位）')


def stop_seat_scheduler():
    with _seat_scheduler_state_lock:
        if not _seat_scheduler_state["enabled"]:
            info("定时座位预约未在运行")
            return
        ev = _seat_scheduler_state["stop_event"]
        _seat_scheduler_state["enabled"] = False

    if ev:
        ev.set()
    ok("定时座位预约已关闭")


def start_background_token_monitor(interval_min=10):
    stop_event = threading.Event()
    t = threading.Thread(
        target=_token_monitor_worker,
        args=(interval_min, stop_event),
        daemon=True,
        name="TokenMonitor"
    )
    t.start()
    return stop_event


def split_time_slots(date_str, start_hm, end_hm, granularity):
    def to_minutes(hm):
        h, m = map(int, hm.split(":"))
        return h * 60 + m

    def to_hm(minutes):
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    gran_min   = granularity * 60
    start_min  = to_minutes(start_hm)
    end_min    = to_minutes(end_hm)

    if end_min <= start_min:
        err("结束时间必须晚于开始时间")
        return []

    first_boundary = start_min if start_min % gran_min == 0 else ((start_min // gran_min) + 1) * gran_min
    last_boundary  = end_min   if end_min   % gran_min == 0 else (end_min   // gran_min) * gran_min

    boundaries = []
    t = first_boundary
    while t <= last_boundary:
        boundaries.append(t)
        t += gran_min

    if not boundaries:
        return [(f"{date_str} {start_hm}", f"{date_str} {end_hm}")]

    slots = []
    if start_min == boundaries[0]:
        for s, e in zip(boundaries[:-1], boundaries[1:]):
            slots.append((f"{date_str} {to_hm(s)}", f"{date_str} {to_hm(e)}"))
        if end_min != last_boundary:
            slots.append((f"{date_str} {to_hm(last_boundary)}", f"{date_str} {end_hm}"))
    else:
        if len(boundaries) >= 2:
            slots.append((f"{date_str} {start_hm}", f"{date_str} {to_hm(boundaries[1])}"))
            for s, e in zip(boundaries[1:-1], boundaries[2:]):
                slots.append((f"{date_str} {to_hm(s)}", f"{date_str} {to_hm(e)}"))
            if end_min != last_boundary:
                slots.append((f"{date_str} {to_hm(last_boundary)}", f"{date_str} {end_hm}"))
        else:
            slots.append((f"{date_str} {start_hm}", f"{date_str} {end_hm}"))

    return slots


def meeting_split_mode():
    info(f"模式：分时段会议室预约")
    info(f"会议室 ID：{MEETING_ROOM_ID}，主题：{MEETING_TITLE}")

    try:
        room_id = int(str(MEETING_ROOM_ID).strip())
    except (TypeError, ValueError):
        err('MEETING_ROOM_ID 必须是整数')
        return
    if room_id <= 0:
        err('MEETING_ROOM_ID 必须大于 0')
        return

    _now_hm = datetime.now().strftime("%H:%M")
    start_input = input(f"请输入开始时间 HH:MM（直接回车默认当前时间 {_now_hm}）：").strip()
    end_input   = input(f"请输入结束时间 HH:MM（直接回车默认 {DEFAULT_MANUAL_END_TIME}）：").strip()
    gran_input  = input("请输入区间粒度（小时，正整数，默认1）：").strip()

    try:
        checked_start = parse_hm(start_input, '开始时间') if start_input else None
        checked_end = parse_hm(end_input, '结束时间') if end_input else None
        if checked_start and checked_end and checked_start >= checked_end:
            raise ValueError('结束时间必须晚于开始时间')
    except ValueError as e:
        err(str(e))
        return

    try:
        granularity = int(gran_input) if gran_input else 1
        if granularity <= 0:
            raise ValueError
    except ValueError:
        err("粒度必须为正整数")
        return

    if WAIT_UNTIL:
        if not wait_until(WAIT_UNTIL):
            return

    # 等待后再推断日期，避免在 21:00 前等待却预约了当天。
    default_date = get_default_date()
    try:
        use_start, use_end, used_fallback = resolve_manual_time_range(
            start_input, end_input, MEETING_START_TIME, MEETING_END_TIME
        )
    except ValueError as e:
        err(str(e))
        return
    if used_fallback:
        warn(f'默认时间已不可用，已改用配置时间 {use_start}~{use_end}')

    info(f"预约日期：{default_date}")
    info(f"预约时间：{use_start}~{use_end}，粒度 {granularity} 小时")

    slots = split_time_slots(default_date, use_start, use_end, granularity)
    if not slots:
        return

    print(f"\n{C_BOLD}将提交以下 {len(slots)} 个会议室预约：{C_RESET}")
    for i, (s, e) in enumerate(slots, 1):
        print(f"  [{i}] {default_date} {s.split()[1]} ~ {e.split()[1]}")

    if input("\n确认提交？(y/n): ").strip().lower() != "y":
        info("已取消操作")
        return

    success_count = 0
    for i, (s, e) in enumerate(slots, 1):
        st = s.split()[1]
        et = e.split()[1]
        prog(f"提交第 {i}/{len(slots)} 段：{st} ~ {et}")
        result = _submit_slot_with_retry(
            room_id, default_date, st, et,
            MEETING_TITLE, MEETING_CONTENT, MEETING_ATTENDEES
        )
        print_result(result)
        if _submit_succeeded(result):
            success_count += 1
        if i < len(slots):
            try:
                slot_interval = max(0.0, float(SLOT_SUBMIT_INTERVAL))
            except (TypeError, ValueError):
                slot_interval = 0.5
            time.sleep(slot_interval)

    print(f"\n[i] 完成！成功 {C_GREEN}{success_count}{C_RESET}/{len(slots)} 段")

    if success_count == 0:
        info("无成功预约，跳过守护")
        return

    info("提交完成，后台守护线程将自动接管...")
    start_background_guard()
    _on_reservation_changed("分时段会议室预约")


def main():
    print(f"{C_BOLD}{'=' * 50}{C_RESET}")
    print(f"{C_BOLD}  吉林大学图书馆预约助手{C_RESET}")
    print(f"{C_BOLD}{'=' * 50}{C_RESET}\n")

    token_data = check_token()
    if not token_data:
        warn('Token 无效：预约/签到守护可能无法工作，请更新配置区 TOKEN 后重启。')
    print()

    # 后台自动启动 Token 监控
    start_background_token_monitor(interval_min=10)
    ok(f"Token 监控已在后台启动（每10分钟检测，失效时邮件通知 {EMAIL_RECEIVER}）")

    # 后台自动启动签到守护
    start_background_guard()
    print()

    while True:
        print(f"{C_BOLD}请选择功能：{C_RESET}")
        print(f"  {C_CYAN}1{C_RESET}. 座位预约")
        print(f"  {C_CYAN}2{C_RESET}. 会议室预约")
        print(f"  {C_CYAN}3{C_RESET}. 取消预约")
        print(f"  {C_CYAN}4{C_RESET}. 分时段会议室预约")

        with _scheduler_state_lock:
            sched_on = _scheduler_state["enabled"]
        sched_tag = f"{C_GREEN}[开启]{C_RESET}" if sched_on else f"{C_DIM}[关闭]{C_RESET}"
        print(f"  {C_CYAN}5{C_RESET}. 定时会议室预约 {sched_tag}")

        with _seat_scheduler_state_lock:
            seat_sched_on = _seat_scheduler_state["enabled"]
        seat_sched_tag = f"{C_GREEN}[开启]{C_RESET}" if seat_sched_on else f"{C_DIM}[关闭]{C_RESET}"
        print(f"  {C_CYAN}6{C_RESET}. 定时座位预约 {seat_sched_tag}")

        print(f"  {C_CYAN}g{C_RESET}. 查看守护状态")
        print(f"  {C_CYAN}q{C_RESET}. 退出")
        try:
            mode = input("> ").strip().lower()
        except EOFError:
            break

        if mode == "1":
            info(f"模式：普通座位预约")
            info(f"默认配置 → 座位ID：{SEAT_ID}")

            seat_id_input = input(f"请输入座位 ID（直接回车使用默认 {SEAT_ID}）：").strip()
            try:
                use_seat_id = int(seat_id_input) if seat_id_input else int(SEAT_ID)
            except (TypeError, ValueError):
                err('座位 ID 必须是整数')
                continue
            if use_seat_id <= 0:
                err('座位 ID 必须大于 0')
                continue

            _now_hm = datetime.now().strftime("%H:%M")
            start_input = input(f"请输入开始时间 HH:MM（直接回车默认当前时间 {_now_hm}）：").strip()
            end_input = input(f"请输入结束时间 HH:MM（直接回车默认 {DEFAULT_MANUAL_END_TIME}）：").strip()

            # 先校验显式输入，避免等待很久后才因格式错误退出。
            try:
                checked_start = parse_hm(start_input, '开始时间') if start_input else None
                checked_end = parse_hm(end_input, '结束时间') if end_input else None
                if checked_start and checked_end and checked_start >= checked_end:
                    raise ValueError('结束时间必须晚于开始时间')
            except ValueError as e:
                err(str(e))
                continue

            if WAIT_UNTIL:
                if not wait_until(WAIT_UNTIL):
                    continue

            # 等待可能跨过 21 点，日期和“默认当前时间”必须在等待后重新计算。
            use_date = get_default_date()
            try:
                use_start, use_end, used_fallback = resolve_manual_time_range(
                    start_input, end_input, START_TIME, END_TIME
                )
            except ValueError as e:
                err(str(e))
                continue
            if used_fallback:
                warn(f'默认时间已不可用，已改用配置时间 {use_start}~{use_end}')

            info(f"预约日期：{use_date}")
            info(f"座位 ID：{use_seat_id}")
            info(f"预约时间：{use_start} ~ {use_end}")
            show_seat_reservations(use_seat_id, use_date)
            prog("正在提交座位预约...")
            result = _submit_seat_with_retry(use_seat_id, use_date, use_start, use_end)
            print_result(result)
            if _submit_succeeded(result):
                _on_reservation_changed("座位预约")

        elif mode == "2":
            info("模式：会议室预约")
            info(f"默认配置 → 房间ID：{MEETING_ROOM_ID}")

            room_id_input = input(f"请输入会议室 ID（直接回车使用默认 {MEETING_ROOM_ID}）：").strip()
            try:
                use_room_id = int(room_id_input) if room_id_input else int(MEETING_ROOM_ID)
            except (TypeError, ValueError):
                err('会议室 ID 必须是整数')
                continue
            if use_room_id <= 0:
                err('会议室 ID 必须大于 0')
                continue

            _now_hm = datetime.now().strftime("%H:%M")
            m_start_input = input(f"请输入开始时间 HH:MM（直接回车默认当前时间 {_now_hm}）：").strip()
            m_end_input = input(f"请输入结束时间 HH:MM（直接回车默认 {DEFAULT_MANUAL_END_TIME}）：").strip()

            try:
                checked_start = parse_hm(m_start_input, '开始时间') if m_start_input else None
                checked_end = parse_hm(m_end_input, '结束时间') if m_end_input else None
                if checked_start and checked_end and checked_start >= checked_end:
                    raise ValueError('结束时间必须晚于开始时间')
            except ValueError as e:
                err(str(e))
                continue

            if WAIT_UNTIL:
                if not wait_until(WAIT_UNTIL):
                    continue

            use_date = get_default_date()
            try:
                use_m_start, use_m_end, used_fallback = resolve_manual_time_range(
                    m_start_input, m_end_input, MEETING_START_TIME, MEETING_END_TIME
                )
            except ValueError as e:
                err(str(e))
                continue
            if used_fallback:
                warn(f'默认时间已不可用，已改用配置时间 {use_m_start}~{use_m_end}')

            info(f"预约日期：{use_date}")
            info(f"会议室 ID：{use_room_id}")
            info(f"预约时间：{use_m_start} ~ {use_m_end}")
            info(f"会议主题：{MEETING_TITLE}")
            info(f"参会人 ID：{MEETING_ATTENDEES}")
            prog("正在提交会议室预约...")
            result = _submit_slot_with_retry(
                use_room_id, use_date, use_m_start, use_m_end,
                MEETING_TITLE, MEETING_CONTENT, MEETING_ATTENDEES
            )
            print_result(result)
            if _submit_succeeded(result):
                _on_reservation_changed("会议室预约")

        elif mode == "3":
            info("模式：取消预约")
            cancel_mode()

        elif mode == "4":
            meeting_split_mode()

        elif mode == "5":
            with _scheduler_state_lock:
                sched_on = _scheduler_state["enabled"]
            if sched_on:
                stop_scheduler()
            else:
                start_scheduler()
        
        elif mode == "6":
            with _seat_scheduler_state_lock:
                seat_sched_on = _seat_scheduler_state["enabled"]
            if seat_sched_on:
                stop_seat_scheduler()
            else:
                start_seat_scheduler()

        elif mode == "g":
            show_guard_status()

        elif mode == "q":
            info("退出程序")
            break

        elif mode == "":
            pass  # 空回车：下方统一输出提示符

        else:
            err("无效输入，请重新选择")

        print()


if __name__ == "__main__":
    main()
