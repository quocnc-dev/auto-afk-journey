"""
State Machine - Logic bot AFK Journey

Các State:
  IDLE          -> Chờ lệnh từ UI
  LAUNCH_GAME   -> Tìm cửa sổ game đang chạy và đang foreground
  AUTO_AFK      -> Chạy luồng Auto AFK bằng OCR + Neo tọa độ
  DONE          -> Hoàn thành tất cả task, về IDLE
  ERROR         -> Gặp lỗi hoặc timeout, dừng bot
"""

import time
import threading
import logging
from enum import Enum, auto
from typing import Callable

import config
from vision import ScreenCapture
from controller import Controller
from ocr_engine import OcrEngine
from window_manager import (
    findGameWindow,
    focusGameWindow,
    getClientRectScreen,
    hasInputPermission,
    isPointInClientRect,
    isWindowForeground,
    openMacAccessibilitySettings,
    requestInputPermission,
)
from modules.auto_afk import run_auto_afk
from modules.debug_snapshot import DebugSnapshotter

logger = logging.getLogger("AFK_Bot")


class State(Enum):
    IDLE = auto()
    LAUNCH_GAME = auto()
    AUTO_AFK = auto()
    DONE = auto()
    ERROR = auto()


class BotEngine:
    """
    Engine điều phối toàn bộ logic bot theo mô hình State Machine.
    Chạy trên thread riêng, giao tiếp với UI qua callback.
    """

    def __init__(
        self,
        log_callback: Callable[[str], None] = None,
        prompt_callback: Callable[[str, str], None] = None,
    ):
        self.capture = ScreenCapture()
        self.ocr = OcrEngine(config.OCR_FUZZY_THRESHOLD)
        self.ctrl = Controller(delay_after_click=config.DELAY_AFTER_CLICK)
        self.debugSnap = DebugSnapshotter()

        self.log_callback = log_callback or (lambda msg: None)
        self.prompt_callback = prompt_callback
        self.state = State.IDLE
        self.gameHwnd: int | None = None

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self.task_auto_afk = True
        self.progress_callback: Callable[[str, int, int], None] | None = None

    def start(self):
        """Bắt đầu chạy bot"""
        if self._thread and self._thread.is_alive():
            self._log("⚠️ Bot đang chạy rồi!")
            return
        self._stop_event.clear()
        self.state = State.LAUNCH_GAME
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BotEngine")
        self._thread.start()
        self._log("🚀 Bot đã khởi động (Chế độ OCR - không cần template)!")

    def stop(self):
        """Dừng bot (graceful)"""
        self._stop_event.set()
        self._log("🛑 Đang dừng bot...")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def captureGameScreen(self):
        """
        Chụp riêng vùng client của cửa sổ game AFK Journey khi đang foreground.
        Không fallback toàn màn hình hoặc chụp khi bị cửa sổ khác che.
        """
        hwnd = findGameWindow(config.GAME_WINDOW_TITLE)
        self.gameHwnd = hwnd
        if not hwnd or not isWindowForeground(hwnd):
            return None, 0, 0, None
        rect = getClientRectScreen(hwnd)
        if rect is None:
            return None, 0, 0, None
        img, originX, originY = self.capture.capture_window(rect)
        return img, originX, originY, rect

    def peekScreen(self):
        """Chụp nhanh cửa sổ game (không OCR) để kiểm tra màn hình đã đổi sau click."""
        return self.captureGameScreen()[0]

    def canInteractAt(self, x: int, y: int, expectedRect: tuple[int, int, int, int] | None = None) -> bool:
        """Kiểm tra cửa sổ game đang foreground, đúng rect đã chụp và chứa điểm (x, y)."""
        if self._stop_event.is_set():
            return False
        hwnd = findGameWindow(config.GAME_WINDOW_TITLE)
        if not hwnd or not isWindowForeground(hwnd):
            return False
        rect = getClientRectScreen(hwnd)
        if expectedRect is not None and rect != expectedRect:
            return False
        return isPointInClientRect(rect, x, y)

    def canSendKey(self) -> bool:
        """Kiểm tra chưa Stop và cửa sổ game đang ở foreground trước khi gửi phím."""
        if self._stop_event.is_set():
            return False
        hwnd = findGameWindow(config.GAME_WINDOW_TITLE)
        return bool(hwnd) and isWindowForeground(hwnd)

    def _run_loop(self):
        try:
            while not self._stop_event.is_set():
                if self.state == State.LAUNCH_GAME:
                    self._state_launch_game()
                elif self.state == State.AUTO_AFK:
                    self._state_auto_afk()
                elif self.state == State.DONE:
                    self._log("✅ Hoàn thành tất cả nhiệm vụ hôm nay!")
                    break
                elif self.state == State.ERROR:
                    self._log("❌ Bot gặp lỗi, đã dừng.")
                    break
                elif self.state == State.IDLE:
                    break
        except Exception as e:
            self._log(f"💥 Lỗi không xử lý được: {e}")
            logger.exception("Lỗi không xử lý được trong BotEngine")
            self.state = State.ERROR
        finally:
            if self._stop_event.is_set() and self.state not in (State.ERROR, State.DONE):
                self.state = State.IDLE
            self._log("🔴 Bot đã dừng.")

    def _state_launch_game(self):
        self._log("🎮 Kiểm tra cửa sổ game đang chạy...")

        hwnd = findGameWindow(config.GAME_WINDOW_TITLE)
        if hwnd:
            self.gameHwnd = hwnd
            focusGameWindow(hwnd)
            if self._stop_event.wait(0.3):
                return
            rect = getClientRectScreen(hwnd)
            if rect and isWindowForeground(hwnd):
                if not hasInputPermission():
                    requestInputPermission()
                    self._log("⚠️ Thiếu quyền Trợ năng (Accessibility) trên macOS — bot chưa thể click chuột!")
                    accMsg = (
                        "Bot chưa có quyền Trợ năng (Accessibility) trên macOS nên click chuột vào game bị chặn.\n\n"
                        "Vui lòng:\n"
                        "1. Mở System Settings → Privacy & Security → Accessibility.\n"
                        "2. Bật quyền cho AFKJourneyBot (nếu vừa cập nhật bản mới, hãy tắt/xóa rồi thêm lại).\n"
                        "3. Bấm OK dưới đây để bot kiểm tra lại."
                    )
                    if self.prompt_callback is not None:
                        openMacAccessibilitySettings()
                        self.prompt_callback("Yêu cầu quyền Trợ năng (macOS)", accMsg)
                    else:
                        self._stop_event.wait(3.0)
                    return
                self._log(f"✅ Đã bắt được cửa sổ '{config.GAME_WINDOW_TITLE}' ({rect[2]}x{rect[3]}), tiếp tục...")
                self.state = State.AUTO_AFK if self.task_auto_afk else State.DONE
                return

        # Game chưa mở hoặc hệ điều hành từ chối đưa lên foreground → báo người dùng
        self._log("⚠️ Cửa sổ game chưa sẵn sàng hoặc chưa ở trên cùng! Đang chờ người dùng...")
        promptMsg = (
            f"Không thể tự đưa cửa sổ '{config.GAME_WINDOW_TITLE}' lên trên cùng hoặc game chưa mở.\n\n"
            "Vui lòng:\n"
            "1. Mở game AFK Journey lên và bấm chuột vào cửa sổ game để đưa lên trên cùng.\n"
            "2. Đảm bảo game đã vào sảnh chính và không bị thu nhỏ.\n"
            "3. Bấm OK dưới đây để bot tiếp tục."
        )
        if self.prompt_callback is not None:
            self.prompt_callback("Yêu cầu mở / focus game", promptMsg)
        else:
            self._stop_event.wait(3.0)

        self._log("🔄 Đang kiểm tra lại cửa sổ game...")

    def _state_auto_afk(self):
        """Chạy nhánh nhiệm vụ Auto AFK và cập nhật trạng thái DONE/IDLE/ERROR chính xác."""
        try:
            success = run_auto_afk(self)
            if self._stop_event.is_set():
                self.state = State.IDLE
            elif success:
                self._log("✅ Auto AFK hoàn thành thành công!")
                self.state = State.DONE
            else:
                self._log("❌ Auto AFK dừng do timeout hoặc mất cửa sổ game.")
                self.state = State.ERROR
        except Exception as e:
            self._log(f"❌ Lỗi khi chạy Auto AFK: {e}")
            logger.exception("Lỗi trong run_auto_afk")
            self.state = State.ERROR

    def _log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        logger.info(msg)
        self.log_callback(full_msg)
