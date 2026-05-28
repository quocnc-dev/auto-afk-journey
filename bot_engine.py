"""
State Machine - Logic bot AFK Journey

Các State:
  IDLE          -> Chờ lệnh từ UI
  LAUNCH_GAME   -> Mở game nếu chưa chạy
  CHECK_POPUP   -> Kiểm tra và đóng popup quảng cáo
  DAILY_QUEST   -> Click nhận quà Daily Quest
  ARENA         -> Chạy vòng lặp trận Arena
  GUILD         -> Điểm danh + đánh Guild Boss
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
        self.ctrl = Controller(delay_after_click=config.DELAY_AFTER_CLICK)

        self.log_callback = log_callback or (lambda msg: None)
        self.state = State.IDLE

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Config task (sẽ set từ UI)
        self.task_auto_afk = True

        # Trạng thái tiến trình
        self.progress_callback: Callable[[str, int, int], None] | None = None  # (task, done, total)

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
        self._log("🚀 Bot đã khởi động!")

    def stop(self):
        """Dừng bot (graceful)"""
        self._stop_event.set()
        self._log("🛑 Đang dừng bot...")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

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
        self._log("🎮 Kiểm tra game đang chạy...")

        # Thử tìm màn hình Home của game (game đã mở sẵn)
        screen = self.capture.capture_full()
        home = self.matcher.find(screen, "home_indicator")
        if home:
            self._log("✅ Game đang mở, tiếp tục...")
            self.state = State.CHECK_POPUP
            return

        # Game chưa mở → Hiện popup yêu cầu người dùng mở game thủ công
        self._log("⚠️ Không tìm thấy game! Đang chờ người dùng mở game...")
        
        # Vì bot chạy trên thread phụ, chúng ta hiển thị messagebox thông qua tkinter.
        # Để tránh các vấn đề luồng, ta có thể dùng messagebox trực tiếp nhưng nó có thể lock thread phụ.
        # Nhấp chuột OK trên popup sẽ giúp bot tiếp tục kiểm tra lại.
        import tkinter as tk
        from tkinter import messagebox

        # Tạo một root ẩn tạm thời hoặc dùng dialog để show message
        root = tk.Tk()
        root.withdraw() # Ẩn cửa sổ chính
        root.attributes("-topmost", True) # Cho popup nổi lên trên cùng
        messagebox.showinfo(
            "Yêu cầu mở game",
            "Không tìm thấy game AFK Journey đang chạy (home_indicator).\n\n"
            "Vui lòng:\n"
            "1. Mở game AFK Journey lên (qua Launcher hoặc trực tiếp).\n"
            "2. Đảm bảo game đã tải xong vào sảnh chính.\n"
            "3. Bấm OK dưới đây để bot tiếp tục kiểm tra.",
            parent=root
        )
        root.destroy()

        # Sau khi người dùng click OK, loop sẽ chạy lại state này để check xem game đã được mở chưa.
        self._log("🔄 Người dùng xác nhận đã mở game, kiểm tra lại...")


    def _state_check_popup(self):
        """Đóng các popup quảng cáo nếu có"""
        self._log("🔍 Kiểm tra popup quảng cáo...")
        screen = self.capture.capture_full()

        popup_templates = ["popup_close", "popup_x", "btn_close", "btn_cancel"]
        result = self.matcher.find_any(screen, popup_templates)

        if result:
            name, cx, cy, conf = result
            self._log(f"🗑️ Đóng popup '{name}' tại ({cx},{cy})")
            self.ctrl.click(cx, cy, delay=config.DELAY_AFTER_CLICK)
            # Check lại lần nữa
            time.sleep(0.5)
            screen = self.capture.capture_full()
            result2 = self.matcher.find_any(screen, popup_templates)
            if result2:
                name2, cx2, cy2, _ = result2
                self._log(f"🗑️ Đóng thêm popup '{name2}'")
                self.ctrl.click(cx2, cy2, delay=config.DELAY_AFTER_CLICK)
        else:
            self._log("✅ Không có popup")

        # Quyết định state tiếp theo
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
        self.state = State.DONE

    # ────────────────────────────────────────────
    #  Helpers
    # ────────────────────────────────────────────

    def _log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        logger.info(msg)
        self.log_callback(full_msg)




