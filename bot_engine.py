"""
State Machine - Logic bot AFK Journey

Các State:
  IDLE          -> Chờ lệnh từ UI
  LAUNCH_GAME   -> Tìm cửa sổ game đang chạy
  CHECK_POPUP   -> Kiểm tra và đóng popup quảng cáo (nếu có)
  AUTO_AFK      -> Chạy luồng Auto AFK bằng OCR + Neo tọa độ
  DONE          -> Hoàn thành tất cả task, về IDLE
  ERROR         -> Gặp lỗi, dừng bot
"""

import time
import threading
import logging
from enum import Enum, auto
from typing import Callable

import config
from vision import ScreenCapture, ImageMatcher
from controller import Controller
from ocr_engine import OcrEngine
from window_manager import findGameWindow, getClientRectScreen, focusGameWindow
from modules.auto_afk import run_auto_afk

logger = logging.getLogger("AFK_Bot")


class State(Enum):
    IDLE = auto()
    LAUNCH_GAME = auto()
    CHECK_POPUP = auto()
    AUTO_AFK = auto()
    DONE = auto()
    ERROR = auto()


class BotEngine:
    """
    Engine điều phối toàn bộ logic bot theo mô hình State Machine.
    Chạy trên thread riêng, giao tiếp với UI qua callback.
    """

    def __init__(self, log_callback: Callable[[str], None] = None):
        self.capture = ScreenCapture()
        self.matcher = ImageMatcher(config.TEMPLATES_DIR, config.MATCH_THRESHOLD)
        self.ocr = OcrEngine(config.OCR_FUZZY_THRESHOLD)
        self.ctrl = Controller(delay_after_click=config.DELAY_AFTER_CLICK)

        self.log_callback = log_callback or (lambda msg: None)
        self.state = State.IDLE
        self.gameHwnd: int | None = None

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Config task (sẽ set từ UI)
        self.task_auto_afk = True

        # Trạng thái tiến trình
        self.progress_callback: Callable[[str, int, int], None] | None = None

    # ────────────────────────────────────────────
    #  Public API (gọi từ UI thread)
    # ────────────────────────────────────────────

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
        Chụp riêng vùng client của cửa sổ game AFK Journey.
        Trả về (image_bgr, originX, originY, rect).
        """
        hwnd = findGameWindow(config.GAME_WINDOW_TITLE)
        if hwnd:
            self.gameHwnd = hwnd
        rect = getClientRectScreen(self.gameHwnd) if self.gameHwnd else None
        img, originX, originY = self.capture.capture_window(rect)
        return img, originX, originY, rect

    # ────────────────────────────────────────────
    #  Main Loop
    # ────────────────────────────────────────────

    def _run_loop(self):
        try:
            while not self._stop_event.is_set():
                if self.state == State.LAUNCH_GAME:
                    self._state_launch_game()
                elif self.state == State.CHECK_POPUP:
                    self._state_check_popup()
                elif self.state == State.AUTO_AFK:
                    self._state_auto_afk()
                elif self.state == State.DONE:
                    self._log("✅ Hoàn thành tất cả nhiệm vụ hôm nay!")
                    self.state = State.IDLE
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
            self._log("🔴 Bot đã dừng.")

    # ────────────────────────────────────────────
    #  States
    # ────────────────────────────────────────────

    def _state_launch_game(self):
        self._log("🎮 Kiểm tra cửa sổ game đang chạy...")

        hwnd = findGameWindow(config.GAME_WINDOW_TITLE)
        if hwnd:
            self.gameHwnd = hwnd
            focusGameWindow(hwnd)
            time.sleep(0.3)
            rect = getClientRectScreen(hwnd)
            if rect:
                self._log(f"✅ Đã bắt được cửa sổ '{config.GAME_WINDOW_TITLE}' ({rect[2]}x{rect[3]}), tiếp tục...")
                self.state = State.CHECK_POPUP
                return

        # Game chưa mở → Hiện popup yêu cầu người dùng mở game
        self._log("⚠️ Không tìm thấy cửa sổ game! Đang chờ người dùng mở game...")

        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(
            "Yêu cầu mở game",
            f"Không tìm thấy cửa sổ '{config.GAME_WINDOW_TITLE}' đang mở.\n\n"
            "Vui lòng:\n"
            "1. Mở game AFK Journey lên (qua Launcher hoặc trực tiếp).\n"
            "2. Đảm bảo game đã vào sảnh chính và không bị thu nhỏ.\n"
            "3. Bấm OK dưới đây để bot tiếp tục.",
            parent=root,
        )
        root.destroy()

        self._log("🔄 Người dùng xác nhận đã mở game, kiểm tra lại...")

    def _state_check_popup(self):
        """Đóng các popup quảng cáo nếu có (dùng template fallback nếu người dùng có sẵn)"""
        self._log("🔍 Kiểm tra popup quảng cáo...")
        screen, originX, originY, _ = self.captureGameScreen()

        popup_templates = ["popup_close", "popup_x", "btn_close", "btn_cancel"]
        result = self.matcher.find_any(screen, popup_templates)

        if result:
            name, cx, cy, _ = result
            self._log(f"🗑️ Đóng popup '{name}' tại ({cx + originX},{cy + originY})")
            self.ctrl.click(cx + originX, cy + originY, delay=config.DELAY_AFTER_CLICK)
            time.sleep(0.5)
            screen2, ox2, oy2, _ = self.captureGameScreen()
            result2 = self.matcher.find_any(screen2, popup_templates)
            if result2:
                name2, cx2, cy2, _ = result2
                self._log(f"🗑️ Đóng thêm popup '{name2}'")
                self.ctrl.click(cx2 + ox2, cy2 + oy2, delay=config.DELAY_AFTER_CLICK)
        else:
            self._log("✅ Không có popup")

        if self.task_auto_afk:
            self.state = State.AUTO_AFK
        else:
            self.state = State.DONE

    def _state_auto_afk(self):
        """Chạy nhánh nhiệm vụ Auto AFK"""
        try:
            success = run_auto_afk(self)
            if success:
                self._log("✅ Auto AFK hoàn thành thành công!")
            else:
                self._log("⚠️ Auto AFK dừng giữa chừng hoặc gặp sự cố.")
        except Exception as e:
            self._log(f"❌ Lỗi khi chạy Auto AFK: {e}")
            logger.exception("Lỗi trong run_auto_afk")
        self.state = State.DONE

    # ────────────────────────────────────────────
    #  Helpers
    # ────────────────────────────────────────────

    def _log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        logger.info(msg)
        self.log_callback(full_msg)
