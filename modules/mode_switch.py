"""
Đổi mode ưu tiên (Huyền Linh <-> Thường) khi thua liên tiếp đủ mốc và bảo đảm thật sự về được sảnh chọn chế độ.
Dùng helper của modules.auto_afk (import lúc gọi) để test vẫn thay được auto_afk._wait.
"""

import cv2
import numpy as np

import config
from modules.debug_snapshot import saveSnapshot
from modules.loop_state import AfkLoopState


def _core():
    from modules import auto_afk
    return auto_afk


def handleDefeatSwitchMode(bot, screen, originX: int, originY: int, rect, items, retryHit, preferChallenge: bool) -> bool:
    """Ở màn thua: đổi mode ưu tiên và bấm 'Quay lại' về sảnh. Trả về mode ưu tiên mới."""
    core = _core()
    newPrefer = not preferChallenge
    modeName = "Thách Đấu Huyền Linh SV" if newPrefer else "Chiến Đấu Thường"
    bot._log(f"🔄 Thất bại liên tiếp đạt mốc! Quay về sảnh và đổi mode ưu tiên sang: {modeName}")
    # Lưu màn thua để biết chính xác vị trí nút 'Quay lại' (OCR từng không đọc được, bấm theo tọa độ bị hụt)
    saveSnapshot(bot, "mode_switch_defeat_screen", screen, items, rect)

    backHit = core._findKey(bot, items, "back")
    if backHit:
        bot._log("🖱 Click nút 'Back' (OCR)...")
        clicked = core._safeClick(bot, backHit[0], backHit[1], rect)
    else:
        backX, backY = findDefeatBackButton(screen, originX, originY, retryHit[1])
        bot._log(f"🖱 Click nút Back '←' góc dưới trái ({backX}, {backY})...")
        clicked = core._safeClick(bot, backX, backY, rect)
    core._settle(bot, screen, 2.5) if clicked else core._wait(bot, 1.0)
    return newPrefer


def findDefeatBackButton(screen, originX: int, originY: int, retryY: int) -> tuple[int, int]:
    """
    Nút '←' ở màn thua là ô vuông trắng sát mép trái, cùng hàng với 'Thử Lại' (giữa là nút thống kê).
    Từng bấm theo khoảng cách tới chữ 'Thử Lại' -> rơi trúng mép nút 'Thử Lại' và đánh lại mode cũ.
    Dò nét mũi tên tối màu trong ô đó; không thấy thì bấm theo tỉ lệ bề rộng cửa sổ.
    """
    imgH, imgW = screen.shape[:2]
    rowY = retryY - originY
    fallback = (originX + int(imgW * config.DEFEAT_BACK_X_RATIO), retryY)
    y1, y2 = max(0, int(rowY - imgH * 0.04)), min(imgH, int(rowY + imgH * 0.04))
    x2 = int(imgW * config.DEFEAT_BACK_ROI_RIGHT)
    if y2 <= y1 or getattr(screen, "ndim", 0) != 3:
        return fallback
    value = cv2.cvtColor(screen[y1:y2, :x2], cv2.COLOR_BGR2HSV)[:, :, 2]
    ys, xs = np.nonzero(value < config.DEFEAT_BACK_DARK_V)
    if not (30 <= len(xs) <= (y2 - y1) * x2 * 0.15):
        return fallback  # không có nét / cả vùng tối (không phải nút sáng) -> dùng tỉ lệ
    return (originX + int((xs.min() + xs.max()) / 2), originY + y1 + int((ys.min() + ys.max()) / 2))


def exitOldModePrep(bot, st: AfkLoopState, screen, items, rect) -> None:
    """
    Vừa đổi mode nhưng vẫn đang ở màn chuẩn bị đấu của mode cũ (bấm 'Quay lại' bị hụt):
    không đánh tiếp mà nhấn ESC để thoát về sảnh, nơi bot sẽ chọn mode mới.
    """
    core = _core()
    if st.pendingModeExit == 1:
        bot._log("⚠️ Vẫn chưa thoát được màn chuẩn bị đấu của mode cũ — lưu ảnh debug để tìm nút quay lại.")
        saveSnapshot(bot, "mode_exit_prep_screen", screen, items, rect)
    st.pendingModeExit -= 1
    bot._log("↩️ Đang ở màn chuẩn bị đấu của mode cũ — nhấn ESC để về sảnh đổi mode...")
    if core._safeEscape(bot):
        core._settle(bot, screen, 2.0)
    else:
        core._wait(bot, 1.0)
