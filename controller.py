"""
Module điều khiển chuột và bàn phím đa nền tảng:
- Windows: hỗ trợ đa màn hình qua Virtual Desktop (MOUSEEVENTF_VIRTUALDESK) + pydirectinput
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

    # Bật DPI awareness ngay khi import trên Windows
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    def _moveCursor(x: int, y: int):
        """Di chuyển chuột theo Virtual Desktop để đúng cả trên màn hình phụ."""
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
        _inputBackend.SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))
else:
    import pyautogui as _inputBackend

    _inputBackend.FAILSAFE = False
    _inputBackend.PAUSE = 0.05

    def _moveCursor(x: int, y: int):
        _inputBackend.moveTo(int(x), int(y))


class Controller:
    """Điều khiển chuột/bàn phím đa nền tảng (Windows / macOS)"""

    def __init__(self, delay_after_click: float = 0.5):
        self.delay_after_click = delay_after_click

    def click(self, x: int, y: int, button: str = "left", delay: float = None):
        """Di chuyển chuột đến (x, y) và click"""
        try:
            _moveCursor(x, y)
            time.sleep(0.05)
            _inputBackend.click(button=button)

            sleep_time = delay if delay is not None else self.delay_after_click
            time.sleep(sleep_time)
            logger.debug(f"Click {button} tại ({x}, {y})")
        except Exception as e:
            logger.error(f"Lỗi click tại ({x}, {y}): {e}")

    def double_click(self, x: int, y: int, delay: float = None):
        """Double click tại (x, y)"""
        try:
            _moveCursor(x, y)
            time.sleep(0.05)
            _inputBackend.doubleClick()

            sleep_time = delay if delay is not None else self.delay_after_click
            time.sleep(sleep_time)
            logger.debug(f"Double click tại ({x}, {y})")
        except Exception as e:
            logger.error(f"Lỗi double click tại ({x}, {y}): {e}")

    def move_to(self, x: int, y: int):
        """Di chuyển chuột đến (x, y) không click"""
        try:
            _moveCursor(x, y)
        except Exception as e:
            logger.error(f"Lỗi di chuyển chuột đến ({x}, {y}): {e}")

    def press_key(self, key: str, delay: float = 0.3):
        """Nhấn phím (ví dụ: 'esc', 'enter', 'space')"""
        try:
            _inputBackend.press(key)
            time.sleep(delay)
            logger.debug(f"Nhấn phím: {key}")
        except Exception as e:
            logger.error(f"Lỗi nhấn phím {key}: {e}")

    def press_escape(self):
        self.press_key("esc")

    def press_enter(self):
        self.press_key("enter")

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.4):
        """Kéo từ (x1,y1) đến (x2,y2)"""
        try:
            _moveCursor(x1, y1)
            time.sleep(0.05)
            _inputBackend.mouseDown()
            steps = max(5, int(duration / 0.03))
            for step in range(1, steps + 1):
                curX = int(x1 + (x2 - x1) * step / steps)
                curY = int(y1 + (y2 - y1) * step / steps)
                _moveCursor(curX, curY)
                time.sleep(duration / steps)
            _inputBackend.mouseUp()
            time.sleep(0.2)
            logger.debug(f"Drag ({x1},{y1}) → ({x2},{y2})")
        except Exception as e:
            logger.error(f"Lỗi drag từ ({x1}, {y1}) đến ({x2}, {y2}): {e}")

    def click_template_result(self, result: tuple, delay: float = None):
        """Click vào kết quả từ ImageMatcher.find()"""
        if result and len(result) >= 2:
            self.click(result[0], result[1], delay=delay)
