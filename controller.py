"""
Module điều khiển chuột và bàn phím đa nền tảng:
- Windows: Virtual Desktop (MOUSEEVENTF_VIRTUALDESK) + kiểm tra giá trị trả về của SendInput
- macOS: dùng pyautogui (tọa độ điểm logic CoreGraphics)
"""

import ctypes
import logging
import sys
import time

logger = logging.getLogger("AFK_Bot")

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def toVirtualDesktopCoords(
    x: int, y: int, vx: int, vy: int, vw: int, vh: int
) -> tuple[int, int]:
    """Chuẩn hóa tọa độ desktop (bao gồm màn hình phụ có x/y âm) về [0..65535]."""
    clampedX = min(max(x, vx), vx + max(1, vw) - 1)
    clampedY = min(max(y, vy), vy + max(1, vh) - 1)
    nx = round((clampedX - vx) * 65535 / max(1, vw - 1))
    ny = round((clampedY - vy) * 65535 / max(1, vh - 1))
    return (nx, ny)


if sys.platform == "win32":
    import pydirectinput as _inputBackend

    _inputBackend.FAILSAFE = False
    _inputBackend.PAUSE = 0.05

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    def _moveCursor(x: int, y: int) -> bool:
        """Di chuyển chuột theo Virtual Desktop; trả về False nếu SendInput không gửi được."""
        user32 = ctypes.windll.user32
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        nx, ny = toVirtualDesktopCoords(int(x), int(y), vx, vy, vw, vh)

        extra = ctypes.c_ulong(0)
        inpUnion = _inputBackend.Input_I()
        inpUnion.mi = _inputBackend.MouseInput(
            nx,
            ny,
            0,
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
            0,
            ctypes.pointer(extra),
        )
        cmd = _inputBackend.Input(ctypes.c_ulong(0), inpUnion)
        sent = _inputBackend.SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))
        if sent != 1:
            logger.warning(f"SendInput di chuyển chuột thất bại tại ({x}, {y}), sent={sent}")
            return False
        return True
else:
    import pyautogui as _inputBackend

    _inputBackend.FAILSAFE = False
    _inputBackend.PAUSE = 0.05

    def _moveCursor(x: int, y: int) -> bool:
        try:
            _inputBackend.moveTo(int(x), int(y))
            return True
        except Exception as exc:
            logger.warning(f"Di chuyển chuột thất bại tại ({x}, {y}): {exc}")
            return False


def _sleepWithStop(seconds: float, stop_event=None) -> bool:
    """Chờ có hỗ trợ ngắt sớm qua stop_event; trả về False nếu đã có lệnh Stop."""
    if stop_event is not None:
        return not stop_event.wait(seconds)
    time.sleep(seconds)
    return True


class Controller:
    """Điều khiển chuột/bàn phím đa nền tảng (Windows / macOS)"""

    def __init__(self, delay_after_click: float = 0.5):
        self.delay_after_click = delay_after_click

    def click(self, x: int, y: int, button: str = "left", delay: float = None, stop_event=None) -> bool:
        """Di chuyển chuột đến (x, y) và click nếu không bị hủy giữa chừng và move thành công."""
        try:
            if stop_event is not None and stop_event.is_set():
                return False
            if not _moveCursor(x, y):
                return False
            if not _sleepWithStop(0.05, stop_event):
                return False
            if stop_event is not None and stop_event.is_set():
                return False

            _inputBackend.click(button=button)
            sleepTime = delay if delay is not None else self.delay_after_click
            _sleepWithStop(sleepTime, stop_event)
            logger.debug(f"Click {button} tại ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"Lỗi click tại ({x}, {y}): {e}")
            return False

    def double_click(self, x: int, y: int, delay: float = None, stop_event=None) -> bool:
        """Double click tại (x, y) an toàn theo stop_event."""
        try:
            if stop_event is not None and stop_event.is_set():
                return False
            if not _moveCursor(x, y):
                return False
            if not _sleepWithStop(0.05, stop_event):
                return False
            if stop_event is not None and stop_event.is_set():
                return False

            _inputBackend.doubleClick()
            sleepTime = delay if delay is not None else self.delay_after_click
            _sleepWithStop(sleepTime, stop_event)
            logger.debug(f"Double click tại ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"Lỗi double click tại ({x}, {y}): {e}")
            return False

    def move_to(self, x: int, y: int) -> bool:
        """Di chuyển chuột đến (x, y) không click"""
        try:
            return _moveCursor(x, y)
        except Exception as e:
            logger.error(f"Lỗi di chuyển chuột đến ({x}, {y}): {e}")
            return False

    def press_key(self, key: str, delay: float = 0.3, stop_event=None) -> bool:
        """Nhấn phím (ví dụ: 'esc', 'enter', 'space')"""
        try:
            if stop_event is not None and stop_event.is_set():
                return False
            _inputBackend.press(key)
            _sleepWithStop(delay, stop_event)
            logger.debug(f"Nhấn phím: {key}")
            return True
        except Exception as e:
            logger.error(f"Lỗi nhấn phím {key}: {e}")
            return False

    def press_escape(self, stop_event=None):
        return self.press_key("esc", stop_event=stop_event)

    def press_enter(self, stop_event=None):
        return self.press_key("enter", stop_event=stop_event)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.4, stop_event=None) -> bool:
        """Kéo từ (x1,y1) đến (x2,y2)"""
        try:
            if not _moveCursor(x1, y1) or not _sleepWithStop(0.05, stop_event):
                return False
            _inputBackend.mouseDown()
            try:
                steps = max(5, int(duration / 0.03))
                for step in range(1, steps + 1):
                    if stop_event is not None and stop_event.is_set():
                        return False
                    curX = int(x1 + (x2 - x1) * step / steps)
                    curY = int(y1 + (y2 - y1) * step / steps)
                    if not _moveCursor(curX, curY):
                        return False
                    if not _sleepWithStop(duration / steps, stop_event):
                        return False
            finally:
                _inputBackend.mouseUp()
            _sleepWithStop(0.2, stop_event)
            return True
        except Exception as e:
            logger.error(f"Lỗi drag từ ({x1}, {y1}) đến ({x2}, {y2}): {e}")
            return False

    def click_template_result(self, result: tuple, delay: float = None, stop_event=None):
        """Click vào kết quả từ ImageMatcher.find()"""
        if result and len(result) >= 2:
            self.click(result[0], result[1], delay=delay, stop_event=stop_event)
