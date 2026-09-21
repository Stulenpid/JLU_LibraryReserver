#CLI版本
#CMD:   python ./CLI_main.py
#请在配置区填写抓包获取的必要信息

import requests
import json
import time
import threading
from datetime import datetime, timedelta

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
MEETING_ATTENDEES = [****, ****] #对于会议室预约，需要要其他同学的ID，获取方法同TOKEN

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

# 邮件提醒配置（Token 失效时发送提醒）
EMAIL_SENDER = "123456789@example.com"
EMAIL_RECEIVER = "123456789@example.com"
EMAIL_SMTP_AUTHCODE = "*******EXAMPLE********"
# ==================== 配置区结束 ====================

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
        resp = requests.get(url, headers=HEADERS, timeout=10)
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
    url = f"{BASE_URL}/v1/seats/{seat_id}/reservations"
    params = {"date": date}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        err(f"查询座位预约失败：{e}")
        return []


def show_seat_reservations(seat_id, date):
    records = get_seat_reservations(seat_id, date)
    if not records:
        info(f"{date} 该座位暂无预约记录")
    else:
        info(f"{date} 该座位已有以下预约：")
        for r in records:
            print(f"    {C_DIM}{r.get('startTime','?')} ~ {r.get('endTime','?')}  状态：{r.get('status','?')}{C_RESET}")


def create_seat_reservation(seat_id, date, start_time, end_time):
    url = f"{BASE_URL}/v1/seat-applications"
    payload = {
        "seatId": seat_id,
        "startTime": f"{date} {start_time}",
        "endTime": f"{date} {end_time}",
        "needMaterial": False,
        "scan": False,
        "use": False,
    }
    prog(f"提交座位预约：{json.dumps(payload, ensure_ascii=False)}")
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        data = resp.json()
        info(f"接口返回：{json.dumps(data, ensure_ascii=False, indent=2)}")
        return data
    except Exception as e:
        err(f"请求失败：{e}")
        return None


def list_meeting_rooms(date, start_time, end_time):
    url = f"{BASE_URL}/v1/meeting-rooms"
    params = {
        "date": date,
        "startTime": f"{date} {start_time}",
        "endTime": f"{date} {end_time}",
    }
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
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
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        data = resp.json()
        info(f"接口返回：{json.dumps(data, ensure_ascii=False, indent=2)}")
        return data
    except Exception as e:
        err(f"请求失败：{e}")
        return None


def _submit_slot_with_retry(room_id, date, st, et, title, content, attendees,
                            max_attempts=None, retry_delay=None):
    """
    提交单段会议室预约，带补发机制（用于功能5定时分段预约）。
      - 服务器有返回（dict，无论业务成功或失败）→ 直接返回，不再补发
      - 服务器无返回（None，多为超时/高负载）→ 等待 retry_delay 秒后补发
    最多尝试 max_attempts 次。
    """
    if max_attempts is None:
        max_attempts = SLOT_MAX_ATTEMPTS
    if retry_delay is None:
        retry_delay = SLOT_RETRY_DELAY

    result = None
    for attempt in range(1, max_attempts + 1):
        result = create_meeting_reservation(
            room_id, date, st, et, title, content, attendees
        )
        # 拿到服务器返回（业务成功或失败都算"有返回"），不再补发
        if isinstance(result, dict):
            return result
        # 无返回：高负载/超时，等待后补发
        if attempt < max_attempts:
            bg_warn(f"{st}~{et} 第 {attempt} 次提交无返回，{retry_delay}s 后补发...")
            time.sleep(retry_delay)
    return result


def _submit_seat_with_retry(seat_id, date, st, et,
                            max_attempts=None, retry_delay=None):
    """
    提交单次座位预约，带补发机制（用于定时座位预约）。
      - 服务器有返回（dict）→ 直接返回，不再补发
      - 服务器无返回（None，多为超时/高负载）→ 等待 retry_delay 秒后补发
    """
    if max_attempts is None:
        max_attempts = SLOT_MAX_ATTEMPTS
    if retry_delay is None:
        retry_delay = SLOT_RETRY_DELAY

    result = None
    for attempt in range(1, max_attempts + 1):
        result = create_seat_reservation(seat_id, date, st, et)
        if isinstance(result, dict):
            return result
        if attempt < max_attempts:
            bg_warn(f"座位预约 {st}~{et} 第 {attempt} 次提交无返回，{retry_delay}s 后补发...")
            time.sleep(retry_delay)
    return result


def get_active_reservations():
    url = f"{BASE_URL}/v1/users/reservations/active"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("content") or data.get("data") or []
    except Exception as e:
        err(f"获取活跃预约失败：{e}")
        return []


def cancel_reservation_by_type(reservation_type, reservation_id):
    if reservation_type == "SEAT":
        url = f"{BASE_URL}/v1/seat-reservations/{reservation_id}/cancel"
        resp = requests.post(url, headers=HEADERS, timeout=10)
    else:
        url = f"{BASE_URL}/v1/meeting-reservations/{reservation_id}/cancel"
        resp = requests.put(url, headers=HEADERS, timeout=10)
    return resp.json()


def cancel_mode():
    prog("正在获取活跃预约列表...")
    records = get_active_reservations()

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
        err("预约失败：无返回数据")
        return
    if isinstance(data, dict):
        if data.get("id") and data.get("status"):
            status_map = {
                "AUTO_APPROVED": "自动审核通过",
                "PENDING": "等待审核",
                "APPROVED": "审核通过",
                "RESERVED": "已预约",
            }
            status_label = status_map.get(data["status"], data["status"])
            ok(f"{C_BOLD}预约成功！{C_RESET}")
            print(f"    {C_BLUE}预约编号{C_RESET}：{data['id']}")
            print(f"    {C_BLUE}时间{C_RESET}    ：{data.get('time','?')}")
            seat = data.get("seat")
            if seat:
                print(f"    {C_BLUE}座位{C_RESET}    ：{seat.get('name','?')}  {seat.get('parentNamePath','')}")
            mr = data.get("meetingRoom")
            if mr:
                print(f"    {C_BLUE}会议室{C_RESET}  ：{mr.get('name','?')}")
            print(f"    {C_BLUE}状态{C_RESET}    ：{status_label}")
            return
        code = data.get("code", "")
        message = data.get("message", "未知错误")
        if code == "reservation.user_has_other_reservation":
            hint = "账号在该时段已有其他预约，请先取消后再预约"
        elif "time" in code.lower() or "conflict" in code.lower():
            hint = "时间段冲突"
        else:
            hint = "时间段已被占用 / Token 过期 / ID 有误"
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
    target = datetime.strptime(target_time_str, "%Y-%m-%d %H:%M:%S")
    info(f"定时模式：将在 {target_time_str} 执行预约")
    while True:
        diff = (target - datetime.now()).total_seconds()
        if diff <= 0:
            info("到达预定时间，开始执行...")
            break
        print(f"\r{C_CYAN}[…]{C_RESET} 距离执行还有 {C_BOLD}{int(diff)}{C_RESET} 秒", end="", flush=True)
        time.sleep(1)
    print()


def get_user_inlib_status(records=None):
    if records is None:
        records = get_active_reservations()
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
    records = get_active_reservations()
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
                my_status, earliest_dt = query_active()
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
    my_status, _ = query_active()
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
    my_status, _ = query_active()
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


def parse_start_dt(time_str):
    import re
    try:
        m = re.match(r"(\d+)年(\d+)月(\d+)日\s+(\d+:\d+)-(\d+:\d+)", time_str)
        if not m:
            return None
        y, mo, d, st, _ = m.groups()
        return datetime(int(y), int(mo), int(d),
                        int(st.split(":")[0]), int(st.split(":")[1]))
    except Exception:
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
            chosen = get_next_reserved(exclude_ids=skip_ids)

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
        if _guard_state["running"]:
            info("后台守护已在运行中")
            return
        stop_event = threading.Event()
        _guard_state["stop_event"]    = stop_event
        _guard_state["refresh_event"] = None
        _guard_state["history"]       = []

    t = threading.Thread(
        target=_continuous_guard_worker,
        args=(initial_exclude_ids,),
        daemon=True,
        name="CheckinGuard"
    )
    with _guard_state_lock:
        _guard_state["thread"] = t
    t.start()
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
    interval_sec = interval_min * 60
    notified = False

    while not (stop_event and stop_event.is_set()):
        user_id   = parse_user_id_from_token(TOKEN)
        is_valid   = False
        is_network_error = False   # 网络异常：连接超时/读超时/连接被重置等，不代表Token失效
        detail_msg = ""

        if not user_id:
            detail_msg = "Token 格式无法解析"
        else:
            url = f"{BASE_URL}/v1/users/{user_id}/detail"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    nickname = data.get("nickname") if isinstance(data, dict) else None
                    if nickname:
                        is_valid = True
                        notified = False
                    else:
                        detail_msg = data.get("message", "无法获取用户信息") if isinstance(data, dict) else "响应格式异常"
                else:
                    detail_msg = f"HTTP {resp.status_code}"
            except requests.exceptions.ConnectTimeout as e:
                is_network_error = True
                detail_msg = f"连接超时：{e}"
            except requests.exceptions.ReadTimeout as e:
                is_network_error = True
                detail_msg = f"读取超时：{e}"
            except requests.exceptions.ConnectionError as e:
                is_network_error = True
                detail_msg = f"连接异常：{e}"
            except requests.exceptions.Timeout as e:
                is_network_error = True
                detail_msg = f"请求超时：{e}"
            except Exception as e:
                # 其余未识别异常，保守起见也不当作Token失效，避免误报
                is_network_error = True
                detail_msg = str(e)

        if is_network_error:
            # 网络/服务器抖动：仅提示，不判定失效、不发邮件、不改变 notified 状态
            bg_warn(f"[{datetime.now().strftime('%H:%M:%S')}] 后台检测：网络异常，本轮跳过（{detail_msg}）")
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
    _th, _tm = map(int, SCHEDULER_TRIGGER_TIME.split(":"))

    while not stop_event.is_set():
        now = datetime.now()
        # 计算今天的触发时间点
        trigger_today = now.replace(hour=_th, minute=_tm, second=0, microsecond=0)
        # 若今天的触发点已过，目标为明天
        if now >= trigger_today:
            trigger_dt = trigger_today + timedelta(days=1)
        else:
            trigger_dt = trigger_today

        with _scheduler_state_lock:
            last_run = _scheduler_state["last_run"]

        # 检查今天是否已经执行过（避免重复触发）
        run_date = trigger_dt.strftime("%Y-%m-%d")  # 预约的那天（即明天）
        if last_run == run_date:
            # 今天已经跑过了，等到明天再触发
            trigger_dt += timedelta(days=1)

        secs_to_wait = (trigger_dt - datetime.now()).total_seconds()
        bg_info(f"定时会议室预约：下次执行时间 {trigger_dt.strftime('%Y-%m-%d %H:%M')}（约 {int(secs_to_wait // 3600)} 小时后）")

        # 等待到触发时间，每秒检查一次 stop_event
        while not stop_event.is_set():
            remaining = (trigger_dt - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 30))  # 最多30秒醒一次，节省CPU

        if stop_event.is_set():
            break

        # ── 执行定时分段预约 ──
        target_date = get_default_date()
        bg_info(f"定时会议室预约：开始执行，目标日期 {target_date}，"
                f"时间 {MEETING_START_TIME}~{MEETING_END_TIME}，粒度 1 小时")

        slots = split_time_slots(target_date, MEETING_START_TIME, MEETING_END_TIME, 1)
        success_count = 0
        fail_count    = 0
        slot_results  = []  # 每段结果：(st, et, success, msg)
        lines = [f"{C_BLUE}[i]{C_RESET} 定时会议室预约：共 {len(slots)} 段，开始提交..."]

        for i, (s, e) in enumerate(slots, 1):
            st = s.split()[1]
            et = e.split()[1]
            # 带补发：无返回则等待后重试，有返回（成功或失败）则立即返回
            result = _submit_slot_with_retry(
                MEETING_ROOM_ID, target_date, st, et,
                MEETING_TITLE, MEETING_CONTENT, MEETING_ATTENDEES
            )
            if result and isinstance(result, dict) and result.get("id") and result.get("status"):
                success_count += 1
                slot_results.append((st, et, True, ""))
                lines.append(f"{C_GREEN}[✓]{C_RESET}  [{i}/{len(slots)}] {st}~{et} 预约成功")
            else:
                fail_count += 1
                msg = result.get("message", "未知错误") if isinstance(result, dict) else "无返回（补发后仍无响应）"
                slot_results.append((st, et, False, msg))
                lines.append(f"{C_RED}[✗]{C_RESET}  [{i}/{len(slots)}] {st}~{et} 失败：{msg}")
            if i < len(slots):
                time.sleep(SLOT_SUBMIT_INTERVAL)

        summary = f"成功 {success_count}/{len(slots)} 段"
        lines.append(f"{C_GREEN if fail_count == 0 else C_YELLOW}[{'✓' if fail_count==0 else '!'}]{C_RESET} 定时会议室预约完成：{summary}")
        _bg_block(lines)

        with _scheduler_state_lock:
            _scheduler_state["last_run"]    = run_date
            _scheduler_state["last_result"] = summary

        # ── 发送汇报邮件 ──
        _send_scheduler_report_email(
            target_date, slots, slot_results, success_count, fail_count
        )

        if success_count > 0:
            _on_reservation_changed("定时分段预约")


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


def start_scheduler():
    with _scheduler_state_lock:
        if _scheduler_state["enabled"]:
            info("定时分段预约已在运行中")
            return
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
    t.start()
    ok(f"定时分段预约已启动（每天 {SCHEDULER_TRIGGER_TIME} 自动预约会议室）")


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


def _scheduled_seat_worker(stop_event):
    """
    每天 SEAT_SCHEDULER_TRIGGER_TIME 自动执行一次座位预约
    （使用配置默认值 SEAT_ID / START_TIME / END_TIME，日期自动推断）。
    单次提交无返回时按补发规则重试。
    """
    _th, _tm = map(int, SEAT_SCHEDULER_TRIGGER_TIME.split(":"))

    while not stop_event.is_set():
        now = datetime.now()
        trigger_today = now.replace(hour=_th, minute=_tm, second=0, microsecond=0)
        if now >= trigger_today:
            trigger_dt = trigger_today + timedelta(days=1)
        else:
            trigger_dt = trigger_today

        with _seat_scheduler_state_lock:
            last_run = _seat_scheduler_state["last_run"]

        run_date = trigger_dt.strftime("%Y-%m-%d")
        if last_run == run_date:
            trigger_dt += timedelta(days=1)

        secs_to_wait = (trigger_dt - datetime.now()).total_seconds()
        bg_info(f"定时座位预约：下次执行时间 {trigger_dt.strftime('%Y-%m-%d %H:%M')}（约 {int(secs_to_wait // 3600)} 小时后）")

        while not stop_event.is_set():
            remaining = (trigger_dt - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 30))

        if stop_event.is_set():
            break

        # ── 执行定时座位预约 ──
        target_date = get_default_date()
        bg_info(f"定时座位预约：开始执行，目标日期 {target_date}，座位ID {SEAT_ID}，时间 {START_TIME}~{END_TIME}")

        result = _submit_seat_with_retry(SEAT_ID, target_date, START_TIME, END_TIME)

        success = bool(result and isinstance(result, dict) and result.get("id") and result.get("status"))
        if success:
            msg = f"预约成功，预约ID：{result.get('id')}"
            bg_ok(f"定时座位预约完成：{msg}")
        else:
            msg = result.get("message", "未知错误") if isinstance(result, dict) else "无返回（补发后仍无响应）"
            bg_err(f"定时座位预约失败：{msg}")

        with _seat_scheduler_state_lock:
            _seat_scheduler_state["last_run"]    = run_date
            _seat_scheduler_state["last_result"] = msg

        _send_seat_scheduler_report_email(target_date, success, msg)

        if success:
            _on_reservation_changed("定时座位预约")


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
        if _seat_scheduler_state["enabled"]:
            info("定时座位预约已在运行中")
            return
        stop_event = threading.Event()
        _seat_scheduler_state["stop_event"] = stop_event
        _seat_scheduler_state["enabled"]    = True

    t = threading.Thread(
        target=_scheduled_seat_worker,
        args=(stop_event,),
        daemon=True,
        name="ScheduledSeatReservation"
    )
    with _seat_scheduler_state_lock:
        _seat_scheduler_state["thread"] = t
    t.start()
    ok(f"定时座位预约已启动（每天 {SEAT_SCHEDULER_TRIGGER_TIME} 自动预约座位）")


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

    default_date = get_default_date()
    info(f"默认日期：{default_date}")

    _now_hm = datetime.now().strftime("%H:%M")
    start_input = input(f"请输入开始时间 HH:MM（直接回车默认当前时间 {_now_hm}）：").strip()
    end_input   = input(f"请输入结束时间 HH:MM（直接回车默认 {DEFAULT_MANUAL_END_TIME}）：").strip()
    gran_input  = input("请输入区间粒度（小时，正整数，默认1）：").strip()

    start_input = start_input if start_input else _now_hm
    end_input   = end_input if end_input else DEFAULT_MANUAL_END_TIME

    try:
        datetime.strptime(start_input, "%H:%M")
        datetime.strptime(end_input, "%H:%M")
    except ValueError:
        err("时间格式错误，请使用 HH:MM 格式")
        return

    try:
        granularity = int(gran_input) if gran_input else 1
        if granularity <= 0:
            raise ValueError
    except ValueError:
        err("粒度必须为正整数")
        return

    slots = split_time_slots(default_date, start_input, end_input, granularity)
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
        result = create_meeting_reservation(
            MEETING_ROOM_ID, default_date, st, et,
            MEETING_TITLE, MEETING_CONTENT, MEETING_ATTENDEES
        )
        print_result(result)
        if result and isinstance(result, dict) and result.get("id") and result.get("status"):
            success_count += 1
        if i < len(slots):
            time.sleep(0.5)

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

    check_token()
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
            use_date = get_default_date()
            info(f"模式：普通座位预约")
            info(f"默认配置 → 日期：{use_date}，座位ID：{SEAT_ID}")

            seat_id_input = input(f"请输入座位 ID（直接回车使用默认 {SEAT_ID}）：").strip()
            use_seat_id   = int(seat_id_input) if seat_id_input else SEAT_ID

            _now_hm = datetime.now().strftime("%H:%M")
            start_input = input(f"请输入开始时间 HH:MM（直接回车默认当前时间 {_now_hm}）：").strip()
            use_start   = start_input if start_input else _now_hm

            end_input = input(f"请输入结束时间 HH:MM（直接回车默认 {DEFAULT_MANUAL_END_TIME}）：").strip()
            use_end   = end_input if end_input else DEFAULT_MANUAL_END_TIME

            try:
                datetime.strptime(use_start, "%H:%M")
                datetime.strptime(use_end, "%H:%M")
            except ValueError:
                err("时间格式错误，请使用 HH:MM 格式")
                continue

            info(f"预约日期：{use_date}")
            info(f"座位 ID：{use_seat_id}")
            info(f"预约时间：{use_start} ~ {use_end}")
            show_seat_reservations(use_seat_id, use_date)
            if WAIT_UNTIL:
                wait_until(WAIT_UNTIL)
            prog("正在提交座位预约...")
            result = create_seat_reservation(use_seat_id, use_date, use_start, use_end)
            print_result(result)
            if result and isinstance(result, dict) and result.get("id") and result.get("status"):
                _on_reservation_changed("座位预约")

        elif mode == "2":
            use_date = get_default_date()
            info("模式：会议室预约")
            info(f"默认配置 → 日期：{use_date}，房间ID：{MEETING_ROOM_ID}")

            room_id_input = input(f"请输入会议室 ID（直接回车使用默认 {MEETING_ROOM_ID}）：").strip()
            use_room_id   = int(room_id_input) if room_id_input else MEETING_ROOM_ID

            _now_hm = datetime.now().strftime("%H:%M")
            m_start_input = input(f"请输入开始时间 HH:MM（直接回车默认当前时间 {_now_hm}）：").strip()
            use_m_start   = m_start_input if m_start_input else _now_hm

            m_end_input = input(f"请输入结束时间 HH:MM（直接回车默认 {DEFAULT_MANUAL_END_TIME}）：").strip()
            use_m_end   = m_end_input if m_end_input else DEFAULT_MANUAL_END_TIME

            try:
                datetime.strptime(use_m_start, "%H:%M")
                datetime.strptime(use_m_end, "%H:%M")
            except ValueError:
                err("时间格式错误，请使用 HH:MM 格式")
                continue

            info(f"预约日期：{use_date}")
            info(f"会议室 ID：{use_room_id}")
            info(f"预约时间：{use_m_start} ~ {use_m_end}")
            info(f"会议主题：{MEETING_TITLE}")
            info(f"参会人 ID：{MEETING_ATTENDEES}")
            if WAIT_UNTIL:
                wait_until(WAIT_UNTIL)
            prog("正在提交会议室预约...")
            result = create_meeting_reservation(
                use_room_id, use_date, use_m_start, use_m_end,
                MEETING_TITLE, MEETING_CONTENT, MEETING_ATTENDEES
            )
            print_result(result)
            if result and isinstance(result, dict) and result.get("id") and result.get("status"):
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
