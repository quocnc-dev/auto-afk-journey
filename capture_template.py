"""
Tool chụp và cắt template từ màn hình - Chạy độc lập
Dùng để tạo các file ảnh template cho bot nhận diện

Cách dùng:
  python capture_template.py

Sau đó:
  1. Kéo vùng chọn trên màn hình
  2. Nhập tên template
  3. Ảnh được lưu vào thư mục templates/
"""

import tkinter as tk
from tkinter import simpledialog, messagebox
import mss
import numpy as np
import cv2
from PIL import Image, ImageTk
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config

os.makedirs(config.TEMPLATES_DIR, exist_ok=True)


class TemplateCapturer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("📸 Capture Template")
        self.geometry("400x180")
        self.resizable(False, False)
        self.configure(bg="#0D0F1A")

        tk.Label(
            self,
            text="📸 AFK Journey - Capture Template",
            font=("Consolas", 13, "bold"), fg="#4F8EF7", bg="#0D0F1A",
        ).pack(pady=(20, 8))

        tk.Label(
            self,
            text="Nhấn nút bên dưới, sau đó kéo chọn vùng trên màn hình",
            font=("Consolas", 10), fg="#6B7280", bg="#0D0F1A",
        ).pack(pady=(0, 12))

        btn_frame = tk.Frame(self, bg="#0D0F1A")
        btn_frame.pack()

        tk.Button(
            btn_frame,
            text="  📷  Chụp vùng màn hình  ",
            font=("Consolas", 11, "bold"),
            bg="#4F8EF7", fg="white",
            relief="flat", padx=10, pady=6,
            command=self._start_capture,
        ).pack(side="left", padx=8)

        tk.Button(
            btn_frame,
            text="  📂  Mở thư mục  ",
            font=("Consolas", 11),
            bg="#1A1F35", fg="#A0B4CC",
            relief="flat", padx=10, pady=6,
            command=lambda: os.startfile(config.TEMPLATES_DIR),
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
            img = np.array(shot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        name = simpledialog.askstring(
            "Tên Template",
            "Nhập tên cho template (không cần .png):\nVí dụ: icon_daily_quest, btn_close ...",
            parent=self,
        )
        if not name:
            self.status_lbl.configure(text="Đã huỷ", fg="#F59E0B")
            return

        name = name.strip().replace(" ", "_")
        out_path = os.path.join(config.TEMPLATES_DIR, f"{name}.png")
        cv2.imwrite(out_path, img)
        self.status_lbl.configure(text=f"✅ Đã lưu: {name}.png", fg="#22C55E")
        messagebox.showinfo("Thành công", f"Template đã lưu:\n{out_path}")


class SelectionOverlay(tk.Toplevel):
    """Cửa sổ trong suốt phủ toàn màn hình để kéo chọn vùng"""

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
            font=("Consolas", 13, "bold"), fg="white", bg="#222244",
        ).place(relx=0.5, rely=0.05, anchor="center")

    def _on_press(self, e):
        self._start_x, self._start_y = e.x, e.y
        self._rect = self.canvas.create_rectangle(
                e.x, e.y, e.x, e.y,
                outline="#4F8EF7", width=2, fill="",
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
