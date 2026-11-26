"""
Thao tác an toàn lên cửa sổ game (click, ESC) và chờ màn hình đổi thật sự sau khi click
thay vì chỉ ngủ một khoảng cố định rồi OCR trúng khung hình đang chuyển cảnh.
"""

import time

import cv2
import numpy as np

import config


def safeClick(bot, x: int, y: int, expectedRect=None) -> bool:
    """Chỉ click khi chưa Stop, cửa sổ game đang foreground và giữ nguyên vị trí đã chụp."""
    if bot._stop_event.is_set():
        return False
    guardFn = (lambda: bot.canInteractAt(x, y, expectedRect=expectedRect)) if hasattr(bot, "canInteractAt") else None
    if guardFn is not None and not guardFn():
        bot._log("⚠️ Cửa sổ game đã bị che, dịch chuyển hoặc mất focus — hủy click!")
        return False
    res = bot.ctrl.click(x, y, stop_event=bot._stop_event, guard_fn=guardFn)
    return (res is not False) and not bot._stop_event.is_set()


def safeEscape(bot) -> bool:
    """Chỉ gửi phím ESC khi chưa Stop và cửa sổ game đang foreground."""
    if bot._stop_event.is_set():
        return False
    guardFn = bot.canSendKey if hasattr(bot, "canSendKey") else None
    if guardFn is not None and not guardFn():
        bot._log("⚠️ Mất focus cửa sổ game — hủy gửi phím ESC!")
        return False
    res = bot.ctrl.press_escape(stop_event=bot._stop_event, guard_fn=guardFn)
    return (res is not False) and not bot._stop_event.is_set()


def _diffMap(a, b) -> np.ndarray:
    """Bản đồ độ lệch tuyệt đối (0..255) giữa 2 khung hình đã thu nhỏ + làm mờ để bỏ qua nhiễu nhỏ."""
    size = (config.SCREEN_DIFF_SIZE, config.SCREEN_DIFF_SIZE)

    def prep(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if getattr(img, "ndim", 0) == 3 else img
        return cv2.GaussianBlur(cv2.resize(gray, size, interpolation=cv2.INTER_AREA), (3, 3), 0).astype(np.int16)

    return np.abs(prep(a) - prep(b))


def frameDiff(a, b) -> float:
    """Độ khác trung bình (0..255) giữa 2 khung hình."""
    if a is None or b is None:
        return 255.0
    return float(np.mean(_diffMap(a, b)))


def hasScreenChanged(a, b) -> bool:
    """Đã chuyển màn: lệch trung bình lớn, hoặc một vùng nhỏ đổi rõ (popup / nút / ảnh team)."""
    if a is None or b is None:
        return True
    diff = _diffMap(a, b)
    if float(np.mean(diff)) >= config.SCREEN_CHANGE_THRESHOLD:
        return True
    return float(np.mean(diff > config.SCREEN_LOCAL_PIXEL_DIFF)) >= config.SCREEN_LOCAL_CHANGE_RATIO


def waitForScreenChange(bot, prevScreen, maxWait: float, waitFn) -> bool:
    """
    Chờ sau click tới khi màn hình đã đổi so với prevScreen rồi đứng yên, tối đa maxWait giây.
    Bot không hỗ trợ peekScreen (vd bot giả lập trong test) thì chờ cố định maxWait như cũ.
    Trả về False nếu đã nhận lệnh Stop.
    """
    peek = getattr(bot, "peekScreen", None)
    if peek is None or prevScreen is None:
        return waitFn(bot, maxWait)
    minWait = min(config.SCREEN_SETTLE_MIN_WAIT, maxWait)
    if not waitFn(bot, minWait):
        return False
    deadline = time.monotonic() + max(0.0, maxWait - minWait)
    changed, last = False, None
    while time.monotonic() < deadline:
        cur = peek()
        if cur is None:
            return not bot._stop_event.is_set()  # mất cửa sổ: để vòng lặp chính xử lý
        if not changed:
            changed = hasScreenChanged(prevScreen, cur)
        elif last is not None and frameDiff(cur, last) < config.SCREEN_STABLE_THRESHOLD:
            return True
        last = cur
        if not waitFn(bot, config.SCREEN_SETTLE_POLL):
            return False
    if not changed:
        bot._log("⚠️ Click xong nhưng màn hình không đổi — có thể click trượt, sẽ quét lại.")
    return not bot._stop_event.is_set()


def waitWatchingFocus(bot, st, seconds: float, waitFn, step: float = 0.5) -> bool:
    """Đứng chờ như waitFn nhưng kiểm tra mỗi `step` giây xem game có bị mất focus không (ghi vào st)."""
    isForeground = getattr(bot, "isGameForeground", None)
    if isForeground is None:
        return waitFn(bot, seconds)
    remaining = seconds
    while remaining > 0:
        if not waitFn(bot, min(step, remaining)):
            return False
        remaining -= step
        if not isForeground():
            now = time.time()
            if st.lastFocusLossTime is None or now - st.lastFocusLossTime > 5:
                bot._log("🔎 Cửa sổ game vừa mất focus (đang ở cửa sổ khác) trong lúc auto.")
            st.lastFocusLossTime = now
    return True


def describePopupCause(bot, st, now: float) -> str:
    """Câu chẩn đoán khi popup 'Tắt chế độ Chiến Đấu Tự Động?' hiện ra: do bot click, chuột người dùng hay mất focus."""
    parts = []
    lastClick = getattr(bot.ctrl, "lastClick", None)
    if lastClick:
        parts.append(f"click gần nhất của bot {now - lastClick[0]:.0f}s trước tại ({lastClick[1]}, {lastClick[2]})")
    else:
        parts.append("bot chưa click lần nào")
    cursorFn = getattr(bot.ctrl, "cursorPos", None)
    cursor = cursorFn() if cursorFn else None
    if cursor and lastClick:
        moved = abs(cursor[0] - lastClick[1]) > 3 or abs(cursor[1] - lastClick[2]) > 3
        parts.append(f"chuột đang ở ({cursor[0]}, {cursor[1]})"
                     + (" — đã bị di chuyển, KHÔNG phải do bot" if moved else " — vẫn ở chỗ bot click cuối"))
    if st.lastFocusLossTime is not None:
        parts.append(f"game mất focus lần cuối {now - st.lastFocusLossTime:.0f}s trước")
    else:
        parts.append("game không bị mất focus từ lúc bắt đầu")
    return "🔎 Chẩn đoán popup: " + "; ".join(parts) + "."
