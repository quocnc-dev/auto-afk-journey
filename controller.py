"""
Module điều khiển chuột và bàn phím sử dụng pydirectinput
Hỗ trợ game chạy dưới DirectX và chống DPI scaling.
"""

import ctypes
import time
import logging
import pydirectinput

# Tắt failsafe của pydirectinput để bot không bị crash khi di chuyển chuột ra rìa màn hình
pydirectinput.FAILSAFE = False
pydirectinput.PAUSE = 0.05

logger = logging.getLogger("AFK_Bot")

# ── Bật DPI awareness ngay khi import ─────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()   # fallback
    except Exception:
        pass


class Controller:
    """Điều khiển chuột/bàn phím qua pydirectinput — tương thích tốt với game DirectX"""

    def __init__(self, delay_after_click: float = 0.5):
        self.delay_after_click = delay_after_click

    def click(self, x: int, y: int, button: str = "left", delay: float = None):
        """Di chuyển chuột đến (x, y) và click thông qua pydirectinput"""
        try:
            pydirectinput.moveTo(x, y)
            time.sleep(0.05)
            pydirectinput.click(button=button)
            
            sleep_time = delay if delay is not None else self.delay_after_click
            time.sleep(sleep_time)
            logger.debug(f"pydirectinput Click {button} tại ({x}, {y})")
        except Exception as e:
            logger.error(f"Lỗi click tại ({x}, {y}): {e}")

    def double_click(self, x: int, y: int, delay: float = None):
        """Double click tại (x, y)"""
        try:
            pydirectinput.moveTo(x, y)
            time.sleep(0.05)
            pydirectinput.doubleClick()
            
            sleep_time = delay if delay is not None else self.delay_after_click
            time.sleep(sleep_time)
            logger.debug(f"pydirectinput Double click tại ({x}, {y})")
        except Exception as e:
            logger.error(f"Lỗi double click tại ({x}, {y}): {e}")

    def move_to(self, x: int, y: int):
        """Di chuyển chuột đến (x, y) không click"""
        try:
            pydirectinput.moveTo(x, y)
        except Exception as e:
            logger.error(f"Lỗi di chuyển chuột đến ({x}, {y}): {e}")

    def press_key(self, key: str, delay: float = 0.3):
        """
        Nhấn phím thông qua pydirectinput (ví dụ: 'esc', 'enter', 'space')
        """
        try:
            pydirectinput.press(key)
            time.sleep(delay)
            logger.debug(f"pydirectinput Nhấn phím: {key}")
        except Exception as e:
            logger.error(f"Lỗi nhấn phím {key}: {e}")

    def press_escape(self):
        self.press_key('esc')

    def press_enter(self):
        self.press_key('enter')

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.4):
        """Kéo từ (x1,y1) đến (x2,y2)"""
        try:
            pydirectinput.moveTo(x1, y1)
            time.sleep(0.05)
            pydirectinput.mouseDown()
            time.sleep(0.05)
            pydirectinput.moveTo(x2, y2, duration=duration)
            time.sleep(0.05)
            pydirectinput.mouseUp()
            time.sleep(0.2)
            logger.debug(f"pydirectinput Drag ({x1},{y1}) → ({x2},{y2})")
        except Exception as e:
            logger.error(f"Lỗi drag từ ({x1}, {y1}) đến ({x2}, {y2}): {e}")

    def click_template_result(self, result: tuple, delay: float = None):
        """Click vào kết quả từ ImageMatcher.find()"""
        if result and len(result) >= 2:
            self.click(result[0], result[1], delay=delay)
