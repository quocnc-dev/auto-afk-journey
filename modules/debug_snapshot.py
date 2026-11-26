"""
Lưu ảnh chụp + kết quả OCR khi bot kẹt hoặc gặp màn hình lạ.
Dùng để chỉnh từ khóa / ROI dựa trên dữ liệu thật thay vì đoán, và làm dữ liệu cho test hồi quy.
Mọi lỗi ghi file đều bị nuốt: debug không bao giờ được làm bot dừng.
"""

import json
import logging
import os
import re
import time

import cv2

import config

logger = logging.getLogger("AFK_Bot.Debug")


class DebugSnapshotter:
    """Ghi cặp file <thời gian>_<lý do>.png/.json, giới hạn tần suất theo lý do và số file giữ lại."""

    def __init__(self, baseDir: str | None = None, maxSnapshots: int | None = None,
                 minInterval: float | None = None, enabled: bool | None = None):
        self.baseDir = baseDir or config.DEBUG_DIR
        self.maxSnapshots = maxSnapshots if maxSnapshots is not None else config.DEBUG_MAX_SNAPSHOTS
        self.minInterval = minInterval if minInterval is not None else config.DEBUG_SNAPSHOT_MIN_INTERVAL
        self.enabled = config.DEBUG_SNAPSHOT_ENABLED if enabled is None else enabled
        self._lastSaved: dict[str, float] = {}

    def save(self, reason: str, screen, items=None, rect=None, extra: dict | None = None) -> str | None:
        """Lưu snapshot; trả về đường dẫn file .png hoặc None nếu bị bỏ qua / lỗi."""
        if not self.enabled or screen is None or getattr(screen, "size", 0) == 0:
            return None
        safeReason = re.sub(r"[^a-z0-9_]+", "_", reason.lower()).strip("_") or "snapshot"
        now = time.time()
        if now - self._lastSaved.get(safeReason, float("-inf")) < self.minInterval:
            return None
        try:
            os.makedirs(self.baseDir, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now)) + f"_{int(now * 1000) % 1000:03d}"
            base = os.path.join(self.baseDir, f"{stamp}_{safeReason}")
            ok, buf = cv2.imencode(".png", screen)
            if not ok:
                return None
            # Ghi bytes thay vì cv2.imwrite để hỗ trợ đường dẫn có ký tự Unicode trên Windows
            with open(base + ".png", "wb") as f:
                f.write(buf.tobytes())
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump(self._buildMeta(reason, rect, items, extra), f, ensure_ascii=False, indent=1)
            self._lastSaved[safeReason] = now
            self._prune()
            return base + ".png"
        except Exception:
            logger.exception("Không lưu được debug snapshot")
            return None

    @staticmethod
    def _buildMeta(reason: str, rect, items, extra: dict | None) -> dict:
        return {
            "reason": reason,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "appVersion": config.APP_VERSION,
            "rect": list(rect) if rect else None,
            "extra": extra or {},
            "items": [
                {
                    "raw": it.rawText, "norm": it.normText, "score": round(float(it.score), 3),
                    "box": [it.x1, it.y1, it.x2, it.y2],
                }
                for it in (items or [])
            ],
        }

    def _prune(self):
        """Xóa các snapshot cũ nhất khi vượt quá giới hạn."""
        pngs = sorted(f for f in os.listdir(self.baseDir) if f.endswith(".png"))
        for name in pngs[:max(0, len(pngs) - self.maxSnapshots)]:
            stem = os.path.join(self.baseDir, name[:-4])
            for ext in (".png", ".json"):
                try:
                    os.remove(stem + ext)
                except OSError:
                    pass


def saveSnapshot(bot, reason: str, screen, items=None, rect=None, extra: dict | None = None) -> str | None:
    """Gọi snapshotter của bot (nếu có) và log đường dẫn ra UI."""
    snapper = getattr(bot, "debugSnap", None)
    if snapper is None:
        return None
    path = snapper.save(reason, screen, items, rect, extra)
    if path:
        bot._log(f"📸 Đã lưu ảnh debug ({reason}): {path}")
    return path
