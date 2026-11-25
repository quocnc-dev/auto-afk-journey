"""
Module điều khiển chuột và bàn phím đa nền tảng:
- Windows: dùng pydirectinput (tương thích DirectX + chống DPI scaling)
- macOS: dùng pyautogui (tọa độ điểm logic CoreGraphics)
"""

import ctypes
import logging
import sys
import time

logger = logging.getLogger("AFK_Bot")

if sys.platform == "win32":
    import pydirectinput as _inputBackend

    _inputBackend.FAILSAFE = False
    _inputBackend.PAUSE = 0.05

    # Bật DPI awareness ngay khi import trên Windows
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
else:
    import pyautogui as _inputBackend

    _inputBackend.FAILSAFE = False
    _inputBackend.PAUSE = 0.05


class Controller:
    """Điều khiển chuột/bàn phím đa nền tảng (Windows / macOS)"""

    def __init__(self, delay_after_click: float = 0.5):
        self.delay_after_click = delay_after_click

    def click(self, x: int, y: int, button: str = "left", delay: float = None):
        """Di chuyển chuột đến (x, y) và click"""
        try:
            _inputBackend.moveTo(int(x), int(y))
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
            _inputBackend.moveTo(int(x), int(y))
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
            _inputBackend.moveTo(int(x), int(y))
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
            _inputBackend.moveTo(int(x1), int(y1))
            time.sleep(0.05)
            _inputBackend.mouseDown()
            time.sleep(0.05)
            _inputBackend.moveTo(int(x2), int(y2), duration=duration)
            time.sleep(0.05)
            _inputBackend.mouseUp()
            time.sleep(0.2)
            logger.debug(f"Drag ({x1},{y1}) → ({x2},{y2})")
        except Exception as e:
            logger.error(f"Lỗi drag từ ({x1}, {y1}) đến ({x2}, {y2}): {e}")

    def click_template_result(self, result: tuple, delay: float = None):
        """Click vào kết quả từ ImageMatcher.find()"""
        if result and len(result) >= 2:
            self.click(result[0], result[1], delay=delay)
