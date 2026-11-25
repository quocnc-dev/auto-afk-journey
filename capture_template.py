"""
Tool chụp và cắt template từ màn hình - Chạy độc lập (tùy chọn fallback).
Dùng để tạo các file ảnh template cho bot nhận diện.
"""

import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

import cv2
import mss
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import config

os.makedirs(config.TEMPLATES_DIR, exist_ok=True)


def sanitizeTemplateName(rawName: str) -> str:
    """Làm sạch tên file template, loại bỏ ký tự đường dẫn để tránh ghi ra ngoài thư mục templates."""
    base = os.path.basename(rawName.strip())
    base = re.sub(r"\.(png|jpe?g)$", "", base, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", base).strip("_")
    return cleaned


def openFolder(path: str):
    """Mở thư mục đa nền tảng (Windows / macOS / Linux)."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class TemplateCapturer(tk.Tk):
    """Giao diện nhỏ hỗ trợ chụp vùng màn hình lưu thành ảnh template."""

    def __init__(self):
        super().__init__()
        self.title("📸 Capture Template")
        self.geometry("400x180")
        self.resizable(False, False)
        self.configure(bg="#0D0F1A")

        tk.Label(
            self,
            text="📸 AFK Journey - Capture Template",
            font=("Consolas", 13, "bold"),
            fg="#4F8EF7",
            bg="#0D0F1A",
        ).pack(pady=(20, 8))

        tk.Label(
            self,
            text="Nhấn nút bên dưới, sau đó kéo chọn vùng trên màn hình",
            font=("Consolas", 10),
            fg="#6B7280",
            bg="#0D0F1A",
        ).pack(pady=(0, 12))

        btnFrame = tk.Frame(self, bg="#0D0F1A")
        btnFrame.pack()

        tk.Button(
            btnFrame,
            text="  📷  Chụp vùng màn hình  ",
            font=("Consolas", 11, "bold"),
            bg="#4F8EF7",
            fg="white",
            relief="flat",
            padx=10,
            pady=6,
            command=self._start_capture,
        ).pack(side="left", padx=8)

        tk.Button(
            btnFrame,
            text="  📂  Mở thư mục  ",
            font=("Consolas", 11),
            bg="#1A1F35",
            fg="#A0B4CC",
            relief="flat",
            padx=10,
            pady=6,
            command=lambda: openFolder(config.TEMPLATES_DIR),
        ).pack(side="left")

        self.status_lbl = tk.Label(
            self, text="Sẵn sàng", font=("Consolas", 10), fg="#22C55E", bg="#0D0F1A"
        )
        self.status_lbl.pack(pady=10)

    def _start_capture(self):
        self.withdraw()
        self.after(200, self._show_overlay)

    def _show_overlay(self):
        overlay = SelectionOverlay(self)
        self.wait_window(overlay)
        self.deiconify()
        if overlay.result:
            x, y, w, h = overlay.result
            self._save_template(x, y, w, h)

    def _save_template(self, x, y, w, h):
        if w < 5 or h < 5:
            self.status_lbl.configure(text="Vùng chọn quá nhỏ!", fg="#EF4444")
            return

        with mss.mss() as sct:
            region = {"top": y, "left": x, "width": w, "height": h}
            shot = sct.grab(region)
            img = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

        rawName = simpledialog.askstring(
            "Tên Template",
            "Nhập tên cho template (không cần .png):\nVí dụ: popup_close, btn_close ...",
            parent=self,
        )
        if not rawName:
            self.status_lbl.configure(text="Đã huỷ", fg="#F59E0B")
            return

        safeName = sanitizeTemplateName(rawName)
        if not safeName:
            self.status_lbl.configure(text="Tên template không hợp lệ!", fg="#EF4444")
            messagebox.showerror("Lỗi", "Tên template chỉ nên chứa chữ, số, '-' hoặc '_'.")
            return

        baseDir = os.path.abspath(config.TEMPLATES_DIR)
        outPath = os.path.abspath(os.path.join(baseDir, f"{safeName}.png"))
        if os.path.commonpath([baseDir, outPath]) != baseDir:
            self.status_lbl.configure(text="Đường dẫn không hợp lệ!", fg="#EF4444")
            return

        if os.path.exists(outPath):
            overwrite = messagebox.askyesno(
                "Xác nhận ghi đè", f"Template '{safeName}.png' đã tồn tại. Bạn có muốn ghi đè?"
            )
            if not overwrite:
                self.status_lbl.configure(text="Đã huỷ ghi đè", fg="#F59E0B")
                return

        if not cv2.imwrite(outPath, img):
            self.status_lbl.configure(text="Lưu file thất bại!", fg="#EF4444")
            messagebox.showerror("Lỗi", f"Không thể ghi file ảnh:\n{outPath}")
            return

        self.status_lbl.configure(text=f"✅ Đã lưu: {safeName}.png", fg="#22C55E")
        messagebox.showinfo("Thành công", f"Template đã lưu:\n{outPath}")


class SelectionOverlay(tk.Toplevel):
    """Cửa sổ trong suốt phủ toàn màn hình để kéo chọn vùng."""

    def __init__(self, master):
        super().__init__(master)
        self.result = None
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.25)
        self.configure(bg="black")
        self.attributes("-topmost", True)

        self.canvas = tk.Canvas(self, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self._start_x = 0
        self._start_y = 0
        self._rect = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self.destroy())

        tk.Label(
            self.canvas,
            text="Kéo để chọn vùng chụp  •  ESC để huỷ",
            font=("Consolas", 13, "bold"),
            fg="white",
            bg="#222244",
        ).place(relx=0.5, rely=0.05, anchor="center")

    def _on_press(self, e):
        self._start_x, self._start_y = e.x, e.y
        self._rect = self.canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="#4F8EF7", width=2, fill=""
        )

    def _on_drag(self, e):
        if self._rect:
            self.canvas.coords(self._rect, self._start_x, self._start_y, e.x, e.y)

    def _on_release(self, e):
        x1, y1 = min(self._start_x, e.x), min(self._start_y, e.y)
        x2, y2 = max(self._start_x, e.x), max(self._start_y, e.y)
        self.result = (x1, y1, x2 - x1, y2 - y1)
        self.destroy()


if __name__ == "__main__":
    app = TemplateCapturer()
    app.mainloop()
