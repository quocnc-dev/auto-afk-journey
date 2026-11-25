"""
Module chụp màn hình và nhận diện ảnh (hỗ trợ chụp riêng cửa sổ game và template fallback)
"""

import cv2
import numpy as np
import mss
import os
import time
import logging

logger = logging.getLogger("AFK_Bot")


class ScreenCapture:
    """Chụp toàn màn hình hoặc đúng vùng cửa sổ game bằng MSS (tốc độ cao)"""

    def __init__(self):
        self.sct = mss.mss()

    def capture_full(self) -> np.ndarray:
        """Chụp toàn màn hình, trả về numpy array BGR"""
        try:
            monitor = self.sct.monitors[1]   # Monitor chính
            shot = self.sct.grab(monitor)
            img = np.array(shot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception:
            # Fallback: dùng PIL.ImageGrab (chậm hơn nhưng ổn định hơn)
            from PIL import ImageGrab
            pil_img = ImageGrab.grab()
            img = np.array(pil_img)
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def capture_region(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """Chụp vùng chỉ định theo tọa độ màn hình thật"""
        region = {"top": int(y), "left": int(x), "width": int(w), "height": int(h)}
        try:
            shot = self.sct.grab(region)
            img = np.array(shot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception:
            from PIL import ImageGrab
            pil_img = ImageGrab.grab(bbox=(int(x), int(y), int(x + w), int(y + h)))
            img = np.array(pil_img)
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def capture_window(self, rect: tuple[int, int, int, int] | None) -> tuple[np.ndarray, int, int]:
        """
        Chụp vùng client của cửa sổ game nếu có rect=(left, top, w, h).
        Tự động chuẩn hóa kích thước về (w, h) logic (chống lệch tọa độ Retina trên macOS).
        Trả về (image_bgr, origin_x, origin_y). Nếu rect=None thì fallback chụp toàn màn hình.
        """
        if rect is not None:
            left, top, w, h = rect
            img = self.capture_region(left, top, w, h)
            if img.shape[1] != w or img.shape[0] != h:
                img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
            return (img, left, top)
        return (self.capture_full(), 0, 0)

    def get_screen_size(self):
        monitor = self.sct.monitors[1]
        return monitor["width"], monitor["height"]


class ImageMatcher:
    """Tìm kiếm template trong ảnh màn hình bằng OpenCV Template Matching (tùy chọn fallback)"""

    def __init__(self, templates_dir: str, threshold: float = 0.80):
        self.templates_dir = templates_dir
        self.threshold = threshold
        self._cache: dict = {}

    def _load_template(self, name: str) -> np.ndarray | None:
        """Load template từ disk (có cache)"""
        if name in self._cache:
            return self._cache[name]

        for ext in [".png", ".jpg", ".jpeg"]:
            path = os.path.join(self.templates_dir, name + ext)
            if os.path.exists(path):
                tpl = cv2.imread(path, cv2.IMREAD_COLOR)
                if tpl is not None:
                    self._cache[name] = tpl
                    logger.debug(f"Đã load template: {path}")
                    return tpl

        logger.debug(f"Không có template fallback: {name}")
        return None

    def find(self, screen: np.ndarray, template_name: str, threshold: float = None) -> tuple | None:
        """
        Tìm template trong ảnh màn hình.
        Trả về (center_x, center_y, confidence) hoặc None nếu không thấy.
        """
        tpl = self._load_template(template_name)
        if tpl is None:
            return None

        thresh = threshold if threshold is not None else self.threshold
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)

        if screen_gray.shape[0] < tpl_gray.shape[0] or screen_gray.shape[1] < tpl_gray.shape[1]:
            return None

        result = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= thresh:
            h, w = tpl_gray.shape
            cx = max_loc[0] + w // 2
            cy = max_loc[1] + h // 2
            return (cx, cy, max_val)
        return None

    def find_any(self, screen: np.ndarray, template_names: list, threshold: float = None) -> tuple | None:
        """Tìm bất kỳ template nào trong danh sách."""
        for name in template_names:
            result = self.find(screen, name, threshold)
            if result:
                cx, cy, conf = result
                return (name, cx, cy, conf)
        return None

    def wait_for_template(
        self,
        capture_fn,
        template_name: str,
        timeout: float = 30,
        interval: float = 0.5,
        threshold: float = None,
        stop_event=None,
    ) -> tuple | None:
        """Chờ cho đến khi template xuất hiện trên màn hình."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_event and stop_event.is_set():
                return None
            screen = capture_fn()
            result = self.find(screen, template_name, threshold)
            if result:
                return result
            time.sleep(interval)
        return None

    def reload_cache(self):
        """Xóa cache để reload template từ disk"""
        self._cache.clear()
        logger.info("Đã reload template cache")
