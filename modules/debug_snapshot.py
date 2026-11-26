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
import unicodedata

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

    def save(self, reason: str, screen, items=None, rect=None, extra: dict | None = None,
             allowNoImage: bool = False) -> str | None:
        """Lưu snapshot; trả về đường dẫn .png (hoặc .json nếu allowNoImage và không có ảnh), None nếu bỏ qua / lỗi."""
        hasImage = screen is not None and getattr(screen, "size", 0) > 0
        if not self.enabled or (not hasImage and not allowNoImage):
            return None
        safeReason = re.sub(r"[^a-z0-9_]+", "_", reason.lower()).strip("_") or "snapshot"
        now = time.time()
        if now - self._lastSaved.get(safeReason, float("-inf")) < self.minInterval:
            return None
        try:
            os.makedirs(self.baseDir, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now)) + f"_{int(now * 1000) % 1000:03d}"
            base = os.path.join(self.baseDir, f"{stamp}_{safeReason}")
            if hasImage:
                ok, buf = cv2.imencode(".png", screen)
                if not ok:
                    return None
                # Ghi bytes thay vì cv2.imwrite để hỗ trợ đường dẫn có ký tự Unicode trên Windows
                with open(base + ".png", "wb") as f:
                    f.write(buf.tobytes())
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump(self._buildMeta(reason, rect, items, extra), f, ensure_ascii=False, indent=1, default=str)
            self._lastSaved[safeReason] = now
            self._prune()
            return base + (".png" if hasImage else ".json")
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
        stems = sorted({f.rsplit(".", 1)[0] for f in os.listdir(self.baseDir) if f.endswith((".png", ".json"))})
        for name in stems[:max(0, len(stems) - self.maxSnapshots)]:
            stem = os.path.join(self.baseDir, name)
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


def slugify(text: str, maxLen: int | None = None) -> str:
    """Bỏ dấu tiếng Việt, emoji, số -> chuỗi a-z_ để gom các log giống nhau (khác số/tọa độ vẫn là 1 lỗi)."""
    t = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z]+", "_", re.sub(r"\d+", " ", t)).strip("_")
    if maxLen:
        t = t[:maxLen].strip("_")
    return t or "issue"


class IssueTracker:
    """Đếm log cảnh báo/lỗi (⚠️ ❌ 💥) giống nhau; lặp đủ ngưỡng trong cửa sổ thời gian thì báo cần chụp debug."""

    PREFIXES = ("⚠️", "⚠", "❌", "💥")

    def __init__(self, threshold: int | None = None, windowSeconds: float | None = None, ignore=None):
        self.threshold = threshold or config.ISSUE_REPEAT_THRESHOLD
        self.windowSeconds = windowSeconds or config.ISSUE_WINDOW_SECONDS
        self.ignore = list(config.ISSUE_IGNORE_SUBSTRINGS if ignore is None else ignore)
        self._hits: dict[str, list[float]] = {}

    def keyOf(self, msg: str) -> str | None:
        if not msg.startswith(self.PREFIXES) or any(p in msg for p in self.ignore):
            return None
        return slugify(msg)

    def observe(self, msg: str, now: float | None = None) -> tuple[str, int] | None:
        """Ghi nhận 1 dòng log; trả về (key, số lần) khi vừa chạm ngưỡng (rồi đếm lại từ đầu), ngược lại None."""
        key = self.keyOf(msg)
        if key is None:
            return None
        now = time.time() if now is None else now
        hits = [t for t in self._hits.get(key, []) if now - t <= self.windowSeconds] + [now]
        if len(hits) >= self.threshold:
            self._hits[key] = []
            return (key, len(hits))
        self._hits[key] = hits
        return None
