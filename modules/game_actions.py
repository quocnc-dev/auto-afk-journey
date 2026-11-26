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


def frameDiff(a, b) -> float:
    """Độ khác trung bình (0..255) giữa 2 khung hình, thu nhỏ + làm mờ để bỏ qua nhiễu nhỏ."""
    if a is None or b is None:
        return 255.0
    size = (config.SCREEN_DIFF_SIZE, config.SCREEN_DIFF_SIZE)

    def prep(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if getattr(img, "ndim", 0) == 3 else img
        return cv2.GaussianBlur(cv2.resize(gray, size, interpolation=cv2.INTER_AREA), (3, 3), 0).astype(np.int16)

    return float(np.mean(np.abs(prep(a) - prep(b))))


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
            changed = frameDiff(cur, prevScreen) >= config.SCREEN_CHANGE_THRESHOLD
        elif last is not None and frameDiff(cur, last) < config.SCREEN_STABLE_THRESHOLD:
            return True
        last = cur
        if not waitFn(bot, config.SCREEN_SETTLE_POLL):
            return False
    if not changed:
        bot._log("⚠️ Click xong nhưng màn hình không đổi — có thể click trượt, sẽ quét lại.")
    return not bot._stop_event.is_set()
