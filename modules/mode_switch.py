"""
Đổi mode ưu tiên (Huyền Linh <-> Thường) khi thua liên tiếp đủ mốc và bảo đảm thật sự về được sảnh chọn chế độ.
Dùng helper của modules.auto_afk (import lúc gọi) để test vẫn thay được auto_afk._wait.
"""

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
        retryItem = retryHit[3]
        backX = max(originX + 10, retryItem.x1 + int(retryItem.height * config.DEFEAT_BACK_HEIGHT_MULT))
        bot._log(f"🖱 Click tọa độ nút Back tương đối ({backX}, {retryHit[1]})...")
        clicked = core._safeClick(bot, backX, retryHit[1], rect)
    core._settle(bot, screen, 2.5) if clicked else core._wait(bot, 1.0)
    return newPrefer


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
