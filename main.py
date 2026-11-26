"""
GUI chính - AFK Journey Auto Bot
Dùng CustomTkinter cho giao diện hiện đại (dark mode)
"""

import logging
import os
import subprocess
import sys
import threading
import time
from tkinter import filedialog, messagebox
import customtkinter as ctk

import config
from bot_engine import BotEngine, State
from ui_layout import buildMainArea, buildSidebar
from ui_tabs import COLORS, runPreviewWorker
from ui_updater import checkUpdateAsync

# ──────────────────────────────────────────────────────────
#  Logging setup
# ──────────────────────────────────────────────────────────
def setupLogging():
    """Gắn FileHandler khi chạy app thật (không chạy lúc import để test không ghi vào log thật)."""
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


logger = logging.getLogger("AFK_Bot")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AFKBotApp(ctk.CTk):
    """Cửa sổ điều khiển chính của AFK Journey Auto Bot."""

    def __init__(self):
        super().__init__()
        self.title("⚡ AFK Journey Auto Bot")
        self.geometry("960x700")
        self.minsize(860, 620)
        self.configure(fg_color=COLORS["bg_main"])

        self.bot = BotEngine(
            log_callback=self._on_log,
            prompt_callback=self._on_prompt,
            progress_callback=self._on_progress,
        )

        self._log_lines = []
        self._is_running = False
        self._start_time = 0.0
        self._preview_active = False
        self._preview_gen = 0
        self._preview_stop_event: threading.Event | None = None
        self._preview_thread: threading.Thread | None = None

        self._build_ui()
        self._update_status_idle()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(500, self._check_bot_status)
        self.after(1500, lambda: checkUpdateAsync(self, silent=True))

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        buildSidebar(self)
        buildMainArea(self)

    def _update_stat(self, key, value):
        card = self.stat_cards.get(key)
        if card and hasattr(card, "_value_label"):
            card._value_label.configure(text=value)

    def _on_start(self):
        if self._is_running or self.bot.is_running():
            return
        self.bot.task_auto_afk = self.var_auto_afk.get()

        if not self.bot.task_auto_afk:
            messagebox.showwarning("Cảnh báo", "Hãy chọn nhiệm vụ Auto AFK!")
            return

        try:
            failThreshold = max(1, min(50, int(self.var_fail_threshold.get())))
        except Exception:
            failThreshold = config.DEFAULT_FAIL_THRESHOLD

        startMode = self.var_start_mode.get()
        self.bot.failThreshold = failThreshold
        self.bot.preferChallengeStart = startMode == "Huyễn Linh"
        self.bot.maxStuckSwitches = config.MAX_STUCK_MODE_SWITCHES if self.var_auto_stop_stuck.get() else 0
        self.bot.keepAwakeEnabled = bool(self.var_keep_awake.get())
        self.bot.notifyEnabled = True

        self._is_running = True
        self._start_time = time.time()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal", text="■  Stop")
        self._update_stat("current_task", f"{startMode} • +0 ải • 0/{failThreshold}")
        self._update_stat("bot_state", "RUNNING")
        self.status_dot.configure(text="● RUNNING", text_color=COLORS["success"])
        self.bot.start()
        self._update_timer()

    def _on_stop(self):
        """Gửi yêu cầu dừng và khóa nút Start cho tới khi worker thread thoát hẳn."""
        self.bot.stop()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="disabled", text="⏳ Đang dừng...")
        self._update_stat("bot_state", "STOPPING")
        self.status_dot.configure(text="● STOPPING", text_color=COLORS["warning"])

    def _on_log(self, msg):
        self.after(0, self._append_log, msg)

    def _on_progress(self, text: str):
        self.after(0, self._update_stat, "current_task", text)

    def _on_prompt(self, title: str, message: str) -> bool:
        """
        Hiển thị hộp thoại OK/Cancel trên main UI thread (tránh crash Cocoa trên macOS).
        Trả về False khi người dùng bấm Cancel -> bot dừng (hộp thoại modal chặn nút Stop).
        """
        doneEvent = threading.Event()
        answer = {"ok": True}

        def showDialog():
            try:
                answer["ok"] = bool(messagebox.askokcancel(title, message, parent=self))
                if not answer["ok"]:
                    self._on_stop()
            finally:
                doneEvent.set()

        self.after(0, showDialog)
        doneEvent.wait()
        return answer["ok"]

    def _append_log(self, msg):
        self._log_lines.append(msg)
        if len(self._log_lines) > config.MAX_LOG_LINES:
            self._log_lines = self._log_lines[-config.MAX_LOG_LINES:]
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > config.MAX_LOG_LINES:
            self.log_text.delete("1.0", f"{lines - config.MAX_LOG_LINES}.0")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")
        self.log_count_lbl.configure(text=f"{len(self._log_lines)} dòng")

    def _clear_log(self):
        self._log_lines.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log_count_lbl.configure(text="0 dòng")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            initialfile=f"afk_bot_log_{time.strftime('%Y%m%d_%H%M%S')}.txt",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._log_lines))
            messagebox.showinfo("Đã lưu", f"Log đã lưu tại:\n{path}")

    def _toggle_preview(self):
        if self._preview_active:
            self._preview_active = False
            self._preview_gen += 1
            if self._preview_stop_event:
                self._preview_stop_event.set()
            self.btn_preview.configure(text="📷  Bật Preview")
            self.preview_label.configure(
                image=None, text="[ Preview tắt ]\nNhấn 'Bật Preview' để xem màn hình real-time"
            )
            self.preview_fps_lbl.configure(text="FPS: —")
        else:
            if self._preview_stop_event:
                self._preview_stop_event.set()
            self._preview_active = True
            self._preview_gen += 1
            gen = self._preview_gen
            stopEvent = threading.Event()
            self._preview_stop_event = stopEvent
            self.btn_preview.configure(text="⏹  Tắt Preview")
            self._preview_thread = threading.Thread(
                target=runPreviewWorker, args=(self, stopEvent, gen), daemon=True, name="PreviewThread"
            )
            self._preview_thread.start()

    def _update_preview_ui(self, img, fps, gen=None):
        if not self._preview_active or (gen is not None and gen != self._preview_gen):
            return
        self.preview_label.configure(image=img, text="")
        self.preview_fps_lbl.configure(text=f"FPS: {fps:.1f}")

    def _open_path(self, path: str):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _open_log_dir(self):
        logDir = os.path.dirname(config.LOG_FILE)
        os.makedirs(logDir, exist_ok=True)
        self._open_path(logDir)

    def _open_debug_dir(self):
        os.makedirs(config.DEBUG_DIR, exist_ok=True)
        self._open_path(config.DEBUG_DIR)

    def _on_close(self):
        if self._preview_stop_event:
            self._preview_stop_event.set()
        self.bot.stop()
        self.bot._sysGuard.stop()
        self.destroy()

    def _on_check_update(self):
        checkUpdateAsync(self, silent=False)

    def _update_timer(self):
        if not self._is_running:
            return
        elapsed = int(time.time() - self._start_time)
        m, s = divmod(elapsed, 60)
        h, m = divmod(m, 60)
        timeStr = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        self._update_stat("run_time", timeStr)
        self.after(1000, self._update_timer)

    def _check_bot_status(self):
        if self._is_running and not self.bot.is_running():
            self._is_running = False
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled", text="■  Stop")
            if self.bot.state == State.DONE:
                self._update_stat("bot_state", "DONE")
                self.status_dot.configure(text="● DONE", text_color=COLORS["success"])
            elif self.bot.state == State.ERROR:
                self._update_stat("bot_state", "ERROR")
                self.status_dot.configure(text="● ERROR", text_color=COLORS["danger"])
            else:
                self._update_status_idle()
        elif self._is_running and self.bot._stop_event.is_set():
            self.btn_stop.configure(state="disabled", text="⏳ Đang dừng...")
            self._update_stat("bot_state", "STOPPING")
            self.status_dot.configure(text="● STOPPING", text_color=COLORS["warning"])
        elif self._is_running:
            self._update_stat("bot_state", self.bot.state.name)
        self.after(1000, self._check_bot_status)

    def _update_status_idle(self):
        self._update_stat("bot_state", "IDLE")
        self.status_dot.configure(text="● IDLE", text_color=COLORS["text_muted"])
        self._update_stat("current_task", "—")
        self._update_stat("run_time", "00:00")


def main():
    setupLogging()
    app = AFKBotApp()
    app.mainloop()


if __name__ == "__main__":
    main()
