"""
Các tab giao diện (Log, Preview, Template) và bảng màu cho AFK Journey Auto Bot.
Tách khỏi main.py để mỗi file giữ gọn dưới 300 dòng.
"""

import os
import threading
import time
import customtkinter as ctk
from PIL import Image

import config
from vision import ScreenCapture

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


def buildLogTab(app, tab):
    """Dựng tab hiển thị log hoạt động của bot."""
    tab.grid_rowconfigure(0, weight=1)
    tab.grid_columnconfigure(0, weight=1)
    logFrame = ctk.CTkFrame(tab, fg_color=COLORS["log_bg"], corner_radius=8)
    logFrame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
    logFrame.grid_rowconfigure(0, weight=1)
    logFrame.grid_columnconfigure(0, weight=1)
    app.log_text = ctk.CTkTextbox(
        logFrame,
        fg_color=COLORS["log_bg"],
        text_color="#A0B4CC",
        font=ctk.CTkFont(family="Consolas", size=12),
        wrap="word",
        state="disabled",
        scrollbar_button_color=COLORS["border"],
        scrollbar_button_hover_color=COLORS["accent"],
    )
    app.log_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
    bottom = ctk.CTkFrame(tab, fg_color="transparent", height=36)
    bottom.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
    ctk.CTkButton(
        bottom,
        text="🗑  Xóa Log",
        width=100,
        height=28,
        fg_color=COLORS["bg_card2"],
        hover_color=COLORS["border"],
        text_color=COLORS["text_muted"],
        font=ctk.CTkFont(size=11),
        command=app._clear_log,
    ).pack(side="left")
    ctk.CTkButton(
        bottom,
        text="💾  Lưu Log",
        width=100,
        height=28,
        fg_color=COLORS["bg_card2"],
        hover_color=COLORS["border"],
        text_color=COLORS["text_muted"],
        font=ctk.CTkFont(size=11),
        command=app._save_log,
    ).pack(side="left", padx=8)
    app.log_count_lbl = ctk.CTkLabel(
        bottom, text="0 dòng", font=ctk.CTkFont(size=10), text_color=COLORS["text_muted"]
    )
    app.log_count_lbl.pack(side="right")


def buildPreviewTab(app, tab):
    """Dựng tab xem trước màn hình real-time."""
    tab.grid_rowconfigure(1, weight=1)
    tab.grid_columnconfigure(0, weight=1)
    ctrl = ctk.CTkFrame(tab, fg_color="transparent")
    ctrl.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
    app.btn_preview = ctk.CTkButton(
        ctrl,
        text="📷  Bật Preview",
        width=130,
        height=32,
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent2"],
        command=app._toggle_preview,
    )
    app.btn_preview.pack(side="left")
    app.preview_fps_lbl = ctk.CTkLabel(
        ctrl, text="FPS: —", font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"]
    )
    app.preview_fps_lbl.pack(side="left", padx=12)
    app.preview_label = ctk.CTkLabel(
        tab,
        text="[ Preview tắt ]\nNhấn 'Bật Preview' để xem màn hình real-time",
        font=ctk.CTkFont(size=13),
        text_color=COLORS["text_muted"],
        fg_color=COLORS["log_bg"],
        corner_radius=8,
    )
    app.preview_label.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))


def buildTemplateTab(app, tab):
    """Dựng tab quản lý danh sách template tùy chọn."""
    tab.grid_rowconfigure(1, weight=1)
    tab.grid_columnconfigure(0, weight=1)
    top = ctk.CTkFrame(tab, fg_color="transparent")
    top.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
    ctk.CTkButton(
        top,
        text="📂  Mở thư mục Template",
        height=32,
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent2"],
        command=app._open_templates_dir,
    ).pack(side="left")
    ctk.CTkButton(
        top,
        text="🔄  Reload",
        width=80,
        height=32,
        fg_color=COLORS["bg_card2"],
        hover_color=COLORS["border"],
        text_color=COLORS["text_primary"],
        command=app._reload_templates,
    ).pack(side="left", padx=8)
    ctk.CTkLabel(
        top,
        text="Chế độ chính dùng OCR (không cần template); ảnh ở đây chỉ làm fallback tùy chọn",
        font=ctk.CTkFont(size=11),
        text_color=COLORS["text_muted"],
    ).pack(side="left", padx=8)
    app.template_list_frame = ctk.CTkScrollableFrame(tab, fg_color=COLORS["log_bg"], corner_radius=8)
    app.template_list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
    refreshTemplateList(app)


def refreshTemplateList(app):
    """Cập nhật danh sách template trong thư mục templates/."""
    for w in app.template_list_frame.winfo_children():
        w.destroy()
    os.makedirs(config.TEMPLATES_DIR, exist_ok=True)
    files = [
        f for f in os.listdir(config.TEMPLATES_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    if not files:
        ctk.CTkLabel(
            app.template_list_frame,
            text="Chưa có template nào (bot chạy tự động bằng OCR).",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
        ).pack(pady=20)
        return

    header = ctk.CTkFrame(app.template_list_frame, fg_color=COLORS["bg_card2"], corner_radius=6)
    header.pack(fill="x", padx=4, pady=(4, 0))
    for colText, colWidth in [("Tên Template", 200), ("Kích thước", 100), ("Trạng thái", 100)]:
        ctk.CTkLabel(
            header,
            text=colText,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["text_muted"],
            width=colWidth,
            anchor="w",
        ).pack(side="left", padx=10, pady=6)

    for fname in sorted(files):
        fpath = os.path.join(config.TEMPLATES_DIR, fname)
        try:
            img = Image.open(fpath)
            sizeStr = f"{img.width}×{img.height}"
            status, statusColor = "✅ OK", COLORS["success"]
        except Exception:
            sizeStr = "—"
            status, statusColor = "❌ Lỗi", COLORS["danger"]
        row = ctk.CTkFrame(app.template_list_frame, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=1)
        ctk.CTkLabel(
            row,
            text=f"🖼  {fname}",
            width=200,
            anchor="w",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"],
        ).pack(side="left", padx=10)
        ctk.CTkLabel(
            row,
            text=sizeStr,
            width=100,
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
        ).pack(side="left")
        ctk.CTkLabel(
            row,
            text=status,
            width=100,
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=statusColor,
        ).pack(side="left")


def runPreviewWorker(app, stopEvent: threading.Event, gen: int):
    """Luồng chụp preview riêng, tự dừng theo stopEvent và bỏ qua frame lỗi thời."""
    import cv2

    capture = ScreenCapture()
    lastTime = time.time()
    while not stopEvent.is_set() and app._preview_active and app._preview_gen == gen:
        try:
            screen = capture.capture_full()
            widgetW = app.preview_label.winfo_width() or 600
            widgetH = app.preview_label.winfo_height() or 380
            h, w = screen.shape[:2]
            scale = min(widgetW / w, widgetH / h, 1.0)
            newW, newH = max(1, int(w * scale)), max(1, int(h * scale))
            resized = cv2.resize(screen, (newW, newH))
            resizedRgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            pilImg = Image.fromarray(resizedRgb)
            ctkImg = ctk.CTkImage(light_image=pilImg, dark_image=pilImg, size=(newW, newH))
            now = time.time()
            fps = 1.0 / max(now - lastTime, 0.001)
            lastTime = now
            if not stopEvent.is_set() and app._preview_gen == gen:
                app.after(0, app._update_preview_ui, ctkImg, fps, gen)
        except Exception:
            pass
        stopEvent.wait(0.1)
