"""Điều khiển chuột/bàn phím: Windows dùng SendInput (Virtual Desktop), macOS dùng Quartz (điểm logic)."""

import ctypes
import logging
import sys
import time

import config
from window_manager import hasInputPermission

logger = logging.getLogger("AFK_Bot")

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

_BUTTON_FLAGS = {
    "left": MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP,
    "right": MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_RIGHTUP,
    "middle": MOUSEEVENTF_MIDDLEDOWN | MOUSEEVENTF_MIDDLEUP,
}


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

    def _sendMouseEvent(nx: int, ny: int, flags: int) -> bool:
        """Gửi sự kiện chuột qua SendInput và kiểm tra hệ điều hành có nhận đủ 1 event không."""
        extra = ctypes.c_ulong(0)
        inpUnion = _inputBackend.Input_I()
        inpUnion.mi = _inputBackend.MouseInput(nx, ny, 0, flags, 0, ctypes.pointer(extra))
        cmd = _inputBackend.Input(ctypes.c_ulong(0), inpUnion)
        sent = _inputBackend.SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))
        if sent != 1:
            logger.warning(f"SendInput thất bại (flags={hex(flags)}, sent={sent})")
            return False
        return True

    def _moveCursor(x: int, y: int) -> bool:
        """Di chuyển chuột theo Virtual Desktop; trả về False nếu SendInput không gửi được."""
        user32 = ctypes.windll.user32
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        nx, ny = toVirtualDesktopCoords(int(x), int(y), vx, vy, vw, vh)
        return _sendMouseEvent(nx, ny, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK)

    def _sendMouseClick(button: str = "left") -> bool:
        """Phát sự kiện click qua SendInput và trả về True chỉ khi SendInput nhận lệnh."""
        flags = _BUTTON_FLAGS.get(button)
        if flags is None:
            raise ValueError(f"Button không hợp lệ: {button}")
        if hasattr(_inputBackend, "SendInput") and hasattr(_inputBackend, "MouseInput"):
            return _sendMouseEvent(0, 0, flags)
        _inputBackend.click(button=button)
        return True
else:
    import pyautogui as _inputBackend

    try:
        import Quartz as _quartz
    except Exception:
        _quartz = None

    _inputBackend.FAILSAFE = False
    _inputBackend.PAUSE = 0.05
    _lastCursorPos = [0, 0]

    def _moveCursor(x: int, y: int) -> bool:
        if not hasInputPermission():
            logger.warning("Thiếu quyền Accessibility trên macOS — hủy di chuyển chuột!")
            return False
        tx, ty = int(x), int(y)
        _lastCursorPos[0], _lastCursorPos[1] = tx, ty
        try:
            if _quartz is not None:
                _quartz.CGWarpMouseCursorPosition((tx, ty))
                ev = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventMouseMoved, (tx, ty), _quartz.kCGMouseButtonLeft)
                _quartz.CGEventPost(_quartz.kCGHIDEventTap, ev)
            else:
                _inputBackend.moveTo(tx, ty)
            return True
        except Exception as exc:
            logger.warning(f"Di chuyển chuột thất bại tại ({x}, {y}): {exc}")
            return False

    def _sendMouseClick(button: str = "left") -> bool:
        if not hasInputPermission():
            logger.warning("Thiếu quyền Accessibility trên macOS — hủy click chuột!")
            return False
        try:
            if _quartz is not None:
                btnMap = {
                    "left": (_quartz.kCGEventLeftMouseDown, _quartz.kCGEventLeftMouseUp, _quartz.kCGMouseButtonLeft),
                    "right": (_quartz.kCGEventRightMouseDown, _quartz.kCGEventRightMouseUp, _quartz.kCGMouseButtonRight),
                    "middle": (_quartz.kCGEventOtherMouseDown, _quartz.kCGEventOtherMouseUp, _quartz.kCGMouseButtonCenter),
                }
                downType, upType, cgBtn = btnMap.get(button, btnMap["left"])
                pos = (_lastCursorPos[0], _lastCursorPos[1])
                _quartz.CGEventPost(_quartz.kCGHIDEventTap, _quartz.CGEventCreateMouseEvent(None, downType, pos, cgBtn))
                time.sleep(config.MAC_CLICK_HOLD_SECONDS)
                _quartz.CGEventPost(_quartz.kCGHIDEventTap, _quartz.CGEventCreateMouseEvent(None, upType, pos, cgBtn))
            else:
                _inputBackend.mouseDown(button=button)
                time.sleep(config.MAC_CLICK_HOLD_SECONDS)
                _inputBackend.mouseUp(button=button)
            return True
        except Exception as exc:
            logger.warning(f"Click thất bại ({button}): {exc}")
            return False


def _sleepWithStop(seconds: float, stop_event=None) -> bool:
    """Chờ có hỗ trợ ngắt sớm qua stop_event; trả về False nếu đã có lệnh Stop."""
    if stop_event is not None:
        return not stop_event.wait(seconds)
    time.sleep(seconds)
    return True


def _passesGuards(stop_event=None, guard_fn=None) -> bool:
    if stop_event is not None and stop_event.is_set():
        return False
    if guard_fn is not None and not guard_fn():
        return False
    return True


def getCursorPos() -> tuple[int, int] | None:
    """Vị trí chuột thật hiện tại (tọa độ màn hình logic); None nếu không đọc được."""
    try:
        if sys.platform == "win32":
            class _Point(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = _Point()
            return (pt.x, pt.y) if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)) else None
        if sys.platform == "darwin":
            import Quartz
            loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
            return (int(round(loc.x)), int(round(loc.y)))
    except Exception:
        return None
    return None


class Controller:
    """Điều khiển chuột/bàn phím đa nền tảng (Windows / macOS)"""

    def __init__(self, delay_after_click: float = 0.5):
        self.delay_after_click = delay_after_click
        self.lastClick: tuple[float, int, int] | None = None  # (time.time(), x, y) của click thành công gần nhất
        self.lastBotCursor: tuple[int, int] | None = None     # Vị trí chuột cuối cùng do bot đặt (click hoặc đỗ chuột)

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        delay: float = None,
        stop_event=None,
        guard_fn=None,
    ) -> bool:
        """Di chuyển chuột và click; kiểm tra lại guard_fn cả trước khi di chuyển lẫn ngay trước khi bấm."""
        try:
            if not _passesGuards(stop_event, guard_fn):
                return False
            if not _moveCursor(x, y):
                return False
            if not _sleepWithStop(0.05, stop_event):
                return False
            if not _passesGuards(stop_event, guard_fn):
                return False
            if not _sendMouseClick(button):
                return False

            self.lastClick = (time.time(), int(x), int(y))
            self.lastBotCursor = (int(x), int(y))
            sleepTime = delay if delay is not None else self.delay_after_click
            _sleepWithStop(sleepTime, stop_event)
            logger.debug(f"Click {button} tại ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"Lỗi click tại ({x}, {y}): {e}")
            return False

    def cursorPos(self) -> tuple[int, int] | None:
        return getCursorPos()

    def move_to(self, x: int, y: int) -> bool:
        """Di chuyển chuột đến (x, y) không click"""
        try:
            ok = _moveCursor(x, y)
            if ok:
                self.lastBotCursor = (int(x), int(y))
            return ok
        except Exception as e:
            logger.error(f"Lỗi di chuyển chuột đến ({x}, {y}): {e}")
            return False

    def press_key(self, key: str, delay: float = 0.3, stop_event=None, guard_fn=None) -> bool:
        """Nhấn phím (chỉ gửi khi pass stop_event và guard_fn)."""
        try:
            if not _passesGuards(stop_event, guard_fn):
                return False
            _inputBackend.press(key)
            _sleepWithStop(delay, stop_event)
            logger.debug(f"Nhấn phím: {key}")
            return True
        except Exception as e:
            logger.error(f"Lỗi nhấn phím {key}: {e}")
            return False

    def press_escape(self, stop_event=None, guard_fn=None) -> bool:
        return self.press_key("esc", stop_event=stop_event, guard_fn=guard_fn)
