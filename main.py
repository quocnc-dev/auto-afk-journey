"""
GUI chính - AFK Journey Auto Bot
Dùng CustomTkinter cho giao diện hiện đại (dark mode)
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import logging
import os
import subprocess
import time
import sys
from PIL import Image, ImageTk
import mss

import config
from bot_engine import BotEngine, State
from vision import ScreenCapture, ImageMatcher

# ──────────────────────────────────────────────────────────
#  Logging setup
# ──────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────
#  Theme
# ──────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg_main":      "#0D0F1A",
    "bg_card":      "#141727",
    "bg_card2":     "#1A1F35",
    "accent":       "#4F8EF7",
    "accent2":      "#7C3AED",
    "success":      "#22C55E",
    "warning":      "#F59E0B",
    "danger":       "#EF4444",
    "text_primary": "#F0F4FF",
    "text_muted":   "#6B7280",
    "border":       "#2D3561",
    "log_bg":       "#090B14",
}


# ──────────────────────────────────────────────────────────
#  Main App
# ──────────────────────────────────────────────────────────
class AFKBotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("⚡ AFK Journey Auto Bot")
        self.geometry("960x700")
        self.minsize(860, 620)
        self.configure(fg_color=COLORS["bg_main"])

        self.bot = BotEngine(log_callback=self._on_log)
        self.bot.progress_callback = self._on_progress

        self._log_lines = []
        self._is_running = False
        self._preview_active = False

        self._build_ui()
        self._update_status_idle()
        self.after(500, self._check_bot_status)

    # ──────────────────────────────────────────────
    #  UI Builder
    # ──────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=230, fg_color=COLORS["bg_card"], corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(24, weight=1)

        # ── Logo ──
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=16, pady=(20, 8), sticky="ew")
        ctk.CTkLabel(logo_frame, text="⚡", font=ctk.CTkFont(size=32),
                     text_color=COLORS["accent"]).pack(side="left", padx=(0, 8))
        title_frame = ctk.CTkFrame(logo_frame, fg_color="transparent")
        title_frame.pack(side="left")
        ctk.CTkLabel(title_frame, text="AFK Bot",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=COLORS["text_primary"]).pack(anchor="w")
        ctk.CTkLabel(title_frame, text="Journey Auto",
                     font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_muted"]).pack(anchor="w")

        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(
            row=1, column=0, sticky="ew", padx=12, pady=8)

        # ── Status ──
        self.status_dot = ctk.CTkLabel(sidebar, text="● IDLE",
                                       font=ctk.CTkFont(size=12, weight="bold"),
                                       text_color=COLORS["text_muted"])
        self.status_dot.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")

        # ── Tasks ──
        ctk.CTkLabel(sidebar, text="NHIỆM VỤ",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=COLORS["text_muted"]).grid(
            row=3, column=0, padx=16, pady=(0, 6), sticky="w")

        self.var_auto_afk = ctk.BooleanVar(value=True)

        ctk.CTkCheckBox(sidebar, text="⏳  Auto AFK", variable=self.var_auto_afk,
                        font=ctk.CTkFont(size=13),
                        text_color=COLORS["text_primary"],
                        fg_color=COLORS["accent"],
                        hover_color=COLORS["accent2"],
                        border_color=COLORS["border"],
                        checkmark_color="#FFFFFF").grid(
            row=4, column=0, padx=16, pady=4, sticky="w")

        # ── Threshold ──
        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(
            row=11, column=0, sticky="ew", padx=12, pady=8)
        ctk.CTkLabel(sidebar, text="NGƯỠNG NHẬN DIỆN",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=COLORS["text_muted"]).grid(
            row=12, column=0, padx=16, pady=(0, 4), sticky="w")
        self.threshold_var = ctk.DoubleVar(value=config.MATCH_THRESHOLD)
        self.threshold_lbl = ctk.CTkLabel(sidebar,
                                          text=f"{config.MATCH_THRESHOLD:.0%}",
                                          font=ctk.CTkFont(size=12),
                                          text_color=COLORS["accent"])
        self.threshold_lbl.grid(row=13, column=0, padx=16, pady=(0, 2), sticky="w")
        ctk.CTkSlider(sidebar, from_=0.5, to=1.0, variable=self.threshold_var,
                      command=self._on_threshold_change,
                      fg_color=COLORS["border"], progress_color=COLORS["accent"],
                      button_color=COLORS["accent"],
                      button_hover_color=COLORS["accent2"]).grid(
            row=14, column=0, padx=14, pady=(0, 12), sticky="ew")

        # ── Spacer ──
        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(
            row=15, column=0, sticky="ew", padx=12, pady=0)

        # ── Quick buttons ──
        ctk.CTkButton(sidebar, text="🖼  Quản lý Template",
                      fg_color="transparent", hover_color=COLORS["bg_card2"],
                      text_color=COLORS["text_muted"], anchor="w",
                      command=self._open_template_manager).grid(
            row=16, column=0, padx=8, pady=(8, 2), sticky="ew")

        ctk.CTkButton(sidebar, text="📁  Mở thư mục log",
                      fg_color="transparent", hover_color=COLORS["bg_card2"],
                      text_color=COLORS["text_muted"], anchor="w",
                      command=self._open_log_dir).grid(
            row=17, column=0, padx=8, pady=2, sticky="ew")

        # ── Version ──
        ctk.CTkLabel(sidebar, text=f"v{config.APP_VERSION} • AFK Journey Bot",
                     font=ctk.CTkFont(size=9),
                     text_color=COLORS["text_muted"]).grid(
            row=21, column=0, padx=16, pady=(0, 12), sticky="sw")

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(2, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # ── Top bar ──
        top_bar = ctk.CTkFrame(main, fg_color=COLORS["bg_card"], height=52, corner_radius=0)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_propagate(False)
        top_bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top_bar, text="🎮  Dashboard",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLORS["text_primary"]).grid(
            row=0, column=0, padx=20, pady=14, sticky="w")

        ctrl_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        ctrl_frame.grid(row=0, column=1, padx=16, pady=8, sticky="e")
        self.btn_start = ctk.CTkButton(ctrl_frame, text="▶  Start Bot",
                                       width=120, height=36,
                                       fg_color=COLORS["success"], hover_color="#16A34A",
                                       font=ctk.CTkFont(size=13, weight="bold"),
                                       command=self._on_start)
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_stop = ctk.CTkButton(ctrl_frame, text="■  Stop",
                                      width=90, height=36,
                                      fg_color=COLORS["danger"], hover_color="#B91C1C",
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      state="disabled", command=self._on_stop)
        self.btn_stop.pack(side="left")

        # ── Stats row ──
        stats_frame = ctk.CTkFrame(main, fg_color="transparent")
        stats_frame.grid(row=1, column=0, padx=16, pady=(12, 8), sticky="ew")
        stats_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.stat_cards = {}
        for col, (key, label, default, color) in enumerate([
            ("current_task",    "📋 Nhiệm vụ",   "—",     COLORS["accent"]),
            ("run_time",        "⏱ Thời gian",   "00:00", COLORS["success"]),
            ("bot_state",       "🔧 Trạng thái", "IDLE",  COLORS["text_muted"]),
        ]):
            card = self._make_stat_card(stats_frame, label, default, color)
            card.grid(row=0, column=col, padx=(0 if col == 0 else 8, 0), sticky="ew")
            self.stat_cards[key] = card

        # ── Tabs ──
        self.tab_view = ctk.CTkTabview(
            main, fg_color=COLORS["bg_card"],
            segmented_button_fg_color=COLORS["bg_card2"],
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent2"],
            segmented_button_unselected_color=COLORS["bg_card2"],
            text_color=COLORS["text_primary"])
        self.tab_view.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")
        self.tab_view.add("📋 Log")
        self.tab_view.add("🖥 Preview")
        self.tab_view.add("🗺 Template")
        self._build_log_tab(self.tab_view.tab("📋 Log"))
        self._build_preview_tab(self.tab_view.tab("🖥 Preview"))
        self._build_template_tab(self.tab_view.tab("🗺 Template"))

    def _make_stat_card(self, parent, label, value, accent):
        card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card2"], corner_radius=10)
        ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                     text_color=COLORS["text_muted"]).pack(anchor="w", padx=14, pady=(10, 0))
        val_lbl = ctk.CTkLabel(card, text=value,
                               font=ctk.CTkFont(size=18, weight="bold"),
                               text_color=accent)
        val_lbl.pack(anchor="w", padx=14, pady=(2, 10))
        card._value_label = val_lbl
        return card

    def _update_stat(self, key, value):
        card = self.stat_cards.get(key)
        if card and hasattr(card, "_value_label"):
            card._value_label.configure(text=value)

    # ── Log Tab ──
    def _build_log_tab(self, tab):
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        log_frame = ctk.CTkFrame(tab, fg_color=COLORS["log_bg"], corner_radius=8)
        log_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.log_text = ctk.CTkTextbox(log_frame,
                                       fg_color=COLORS["log_bg"],
                                       text_color="#A0B4CC",
                                       font=ctk.CTkFont(family="Consolas", size=12),
                                       wrap="word", state="disabled",
                                       scrollbar_button_color=COLORS["border"],
                                       scrollbar_button_hover_color=COLORS["accent"])
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        bottom = ctk.CTkFrame(tab, fg_color="transparent", height=36)
        bottom.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        ctk.CTkButton(bottom, text="🗑  Xóa Log", width=100, height=28,
                      fg_color=COLORS["bg_card2"], hover_color=COLORS["border"],
                      text_color=COLORS["text_muted"], font=ctk.CTkFont(size=11),
                      command=self._clear_log).pack(side="left")
        ctk.CTkButton(bottom, text="💾  Lưu Log", width=100, height=28,
                      fg_color=COLORS["bg_card2"], hover_color=COLORS["border"],
                      text_color=COLORS["text_muted"], font=ctk.CTkFont(size=11),
                      command=self._save_log).pack(side="left", padx=8)
        self.log_count_lbl = ctk.CTkLabel(bottom, text="0 dòng",
                                          font=ctk.CTkFont(size=10),
                                          text_color=COLORS["text_muted"])
        self.log_count_lbl.pack(side="right")

    # ── Preview Tab ──
    def _build_preview_tab(self, tab):
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        self.btn_preview = ctk.CTkButton(ctrl, text="📷  Bật Preview",
                                         width=130, height=32,
                                         fg_color=COLORS["accent"],
                                         hover_color=COLORS["accent2"],
                                         command=self._toggle_preview)
        self.btn_preview.pack(side="left")
        self.preview_fps_lbl = ctk.CTkLabel(ctrl, text="FPS: —",
                                            font=ctk.CTkFont(size=11),
                                            text_color=COLORS["text_muted"])
        self.preview_fps_lbl.pack(side="left", padx=12)
        self.preview_label = ctk.CTkLabel(
            tab,
            text="[ Preview tắt ]\nNhấn 'Bật Preview' để xem màn hình real-time",
            font=ctk.CTkFont(size=13), text_color=COLORS["text_muted"],
            fg_color=COLORS["log_bg"], corner_radius=8)
        self.preview_label.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._preview_thread = None

    # ── Template Tab ──
    def _build_template_tab(self, tab):
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        ctk.CTkButton(top, text="📂  Mở thư mục Template",
                      height=32, fg_color=COLORS["accent"], hover_color=COLORS["accent2"],
                      command=self._open_templates_dir).pack(side="left")
        ctk.CTkButton(top, text="🔄  Reload", width=80, height=32,
                      fg_color=COLORS["bg_card2"], hover_color=COLORS["border"],
                      text_color=COLORS["text_primary"],
                      command=self._reload_templates).pack(side="left", padx=8)
        ctk.CTkLabel(top, text="Thêm ảnh .png vào 'templates/' để bot nhận diện",
                     font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_muted"]).pack(side="left", padx=8)
        self.template_list_frame = ctk.CTkScrollableFrame(
            tab, fg_color=COLORS["log_bg"], corner_radius=8)
        self.template_list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._refresh_template_list()

    # ──────────────────────────────────────────────
    #  Event handlers
    # ──────────────────────────────────────────────

    def _on_start(self):
        if self._is_running:
            return
        self.bot.task_auto_afk = self.var_auto_afk.get()
        self.bot.matcher.threshold = self.threshold_var.get()

        if not self.bot.task_auto_afk:
            messagebox.showwarning("Cảnh báo", "Hãy chọn nhiệm vụ Auto AFK!")
            return

        self._is_running = True
        self._start_time = time.time()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._update_stat("bot_state", "RUNNING")
        self.status_dot.configure(text="● RUNNING", text_color=COLORS["success"])
        self.bot.start()
        self._update_timer()

    def _on_stop(self):
        self.bot.stop()
        self._is_running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._update_status_idle()

    def _on_log(self, msg):
        self.after(0, self._append_log, msg)

    def _on_progress(self, task, done, total):
        self.after(0, self._update_stat, "current_task", task.upper())

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
            initialfile=f"afk_bot_log_{time.strftime('%Y%m%d_%H%M%S')}.txt")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._log_lines))
            messagebox.showinfo("Đã lưu", f"Log đã lưu tại:\n{path}")

    def _on_threshold_change(self, value):
        self.threshold_lbl.configure(text=f"{float(value):.0%}")



    def _toggle_preview(self):
        if self._preview_active:
            self._preview_active = False
            self.btn_preview.configure(text="📷  Bật Preview")
            self.preview_label.configure(
                image=None,
                text="[ Preview tắt ]\nNhấn 'Bật Preview' để xem màn hình real-time")
        else:
            self._preview_active = True
            self.btn_preview.configure(text="⏹  Tắt Preview")
            self._preview_thread = threading.Thread(
                target=self._preview_loop, daemon=True, name="PreviewThread")
            self._preview_thread.start()

    def _preview_loop(self):
        import cv2
        capture = ScreenCapture()
        last_time = time.time()
        while self._preview_active:
            try:
                screen = capture.capture_full()
                widget_w = self.preview_label.winfo_width() or 600
                widget_h = self.preview_label.winfo_height() or 380
                h, w = screen.shape[:2]
                scale = min(widget_w / w, widget_h / h, 1.0)
                new_w, new_h = int(w * scale), int(h * scale)
                resized = cv2.resize(screen, (new_w, new_h))
                resized_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(resized_rgb)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img,
                                       size=(new_w, new_h))
                now = time.time()
                fps = 1.0 / max(now - last_time, 0.001)
                last_time = now
                self.after(0, self._update_preview_ui, ctk_img, fps)
            except Exception:
                pass
            time.sleep(0.1)

    def _update_preview_ui(self, img, fps):
        self.preview_label.configure(image=img, text="")
        self.preview_fps_lbl.configure(text=f"FPS: {fps:.1f}")

    def _open_path(self, path: str):
        """Mở thư mục tương thích đa nền tảng (Windows / macOS / Linux)."""
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _open_templates_dir(self):
        os.makedirs(config.TEMPLATES_DIR, exist_ok=True)
        self._open_path(config.TEMPLATES_DIR)

    def _open_log_dir(self):
        log_dir = os.path.dirname(config.LOG_FILE)
        os.makedirs(log_dir, exist_ok=True)
        self._open_path(log_dir)

    def _open_template_manager(self):
        self.tab_view.set("🗺 Template")

    def _reload_templates(self):
        self.bot.matcher.reload_cache()
        self._refresh_template_list()
        self._on_log("[GUI] Đã reload templates")

    def _refresh_template_list(self):
        for w in self.template_list_frame.winfo_children():
            w.destroy()
        os.makedirs(config.TEMPLATES_DIR, exist_ok=True)
        files = [f for f in os.listdir(config.TEMPLATES_DIR)
                 if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        if not files:
            ctk.CTkLabel(self.template_list_frame,
                         text="Chưa có template nào.\nThêm file .png vào thư mục templates/",
                         font=ctk.CTkFont(size=12),
                         text_color=COLORS["text_muted"]).pack(pady=20)
            return
        header = ctk.CTkFrame(self.template_list_frame, fg_color=COLORS["bg_card2"],
                              corner_radius=6)
        header.pack(fill="x", padx=4, pady=(4, 0))
        for col_text, col_width in [("Tên Template", 200), ("Kích thước", 100), ("Trạng thái", 100)]:
            ctk.CTkLabel(header, text=col_text,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=COLORS["text_muted"], width=col_width,
                         anchor="w").pack(side="left", padx=10, pady=6)
        for fname in sorted(files):
            fpath = os.path.join(config.TEMPLATES_DIR, fname)
            try:
                img = Image.open(fpath)
                size_str = f"{img.width}×{img.height}"
                status, status_color = "✅ OK", COLORS["success"]
            except Exception:
                size_str = "—"
                status, status_color = "❌ Lỗi", COLORS["danger"]
            row = ctk.CTkFrame(self.template_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=1)
            ctk.CTkLabel(row, text=f"🖼  {fname}", width=200, anchor="w",
                         font=ctk.CTkFont(size=12),
                         text_color=COLORS["text_primary"]).pack(side="left", padx=10)
            ctk.CTkLabel(row, text=size_str, width=100, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_muted"]).pack(side="left")
            ctk.CTkLabel(row, text=status, width=100, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color=status_color).pack(side="left")

    # ──────────────────────────────────────────────
    #  Timer & Status
    # ──────────────────────────────────────────────

    def _update_timer(self):
        if not self._is_running:
            return
        elapsed = int(time.time() - self._start_time)
        m, s = divmod(elapsed, 60)
        h, m = divmod(m, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        self._update_stat("run_time", time_str)
        self.after(1000, self._update_timer)

    def _check_bot_status(self):
        if self._is_running and not self.bot.is_running():
            self._is_running = False
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self._update_status_idle()
            if self.bot.state in (State.DONE, State.IDLE):
                self._update_stat("bot_state", "DONE")
                self.status_dot.configure(text="● DONE", text_color=COLORS["success"])
            else:
                self._update_stat("bot_state", "ERROR")
                self.status_dot.configure(text="● ERROR", text_color=COLORS["danger"])
        if self._is_running:
            self._update_stat("bot_state", self.bot.state.name)
        self.after(1000, self._check_bot_status)

    def _update_status_idle(self):
        self._update_stat("bot_state", "IDLE")
        self.status_dot.configure(text="● IDLE", text_color=COLORS["text_muted"])
        self._update_stat("current_task", "—")
        self._update_stat("run_time", "00:00")


# ──────────────────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────────────────
def main():
    os.makedirs(config.TEMPLATES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
    app = AFKBotApp()
    app.mainloop()


if __name__ == "__main__":
    main()
