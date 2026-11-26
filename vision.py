"""
Module chụp màn hình (chụp riêng vùng cửa sổ game hoặc toàn màn hình).
"""

import logging
import threading

import cv2
import mss
import numpy as np

logger = logging.getLogger("AFK_Bot")

# mss.MSS là tên mới, mss.mss đã deprecated
_MssFactory = getattr(mss, "MSS", None) or mss.mss


class ScreenCapture:
    """Chụp toàn màn hình hoặc đúng vùng cửa sổ game bằng MSS (tốc độ cao)"""

    def __init__(self):
        # MSS giữ handle theo thread (Windows lỗi khi dùng chéo thread) -> mỗi thread một instance riêng
        self._local = threading.local()

    @property
    def sct(self):
        inst = getattr(self._local, "sct", None)
        if inst is None:
            inst = _MssFactory()
            self._local.sct = inst
        return inst

    def capture_full(self) -> np.ndarray:
        """Chụp toàn màn hình, trả về numpy array BGR"""
        try:
            monitor = self.sct.monitors[1]   # Monitor chính
            shot = self.sct.grab(monitor)
            img = np.array(shot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception as exc:
            logger.debug("MSS chụp toàn màn hình lỗi, dùng PIL: %s", exc)
            # Fallback: dùng PIL.ImageGrab (bật all_screens để hỗ trợ đa màn hình)
            from PIL import ImageGrab
            pil_img = ImageGrab.grab(all_screens=True)
            img = np.array(pil_img)
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def capture_region(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """Chụp vùng chỉ định theo tọa độ màn hình thật"""
        region = {"top": int(y), "left": int(x), "width": int(w), "height": int(h)}
        try:
            shot = self.sct.grab(region)
            img = np.array(shot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception as exc:
            logger.debug("MSS chụp vùng lỗi, dùng PIL: %s", exc)
            from PIL import ImageGrab
            pil_img = ImageGrab.grab(
                bbox=(int(x), int(y), int(x + w), int(y + h)),
                all_screens=True,
            )
            img = np.array(pil_img)
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def capture_window(self, rect: tuple[int, int, int, int] | None) -> tuple[np.ndarray | None, int, int]:
        """
        Chụp vùng client của cửa sổ game nếu có rect=(left, top, w, h).
        Không fallback sang chụp toàn màn hình khi rect=None để tránh click nhầm ngoài game.
        """
        if rect is None:
            return (None, 0, 0)
        left, top, w, h = rect
        img = self.capture_region(left, top, w, h)
        if img.shape[1] != w or img.shape[0] != h:
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        return (img, left, top)
