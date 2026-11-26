"""
Luồng sao chép đội hình sau khi thua: màn chuẩn bị đấu -> 'Thành tích' -> (lọc đội đã sở hữu,
chuyển team kế tiếp) -> 'Sao chép'.
Dùng helper của modules.auto_afk (import lúc gọi) để test vẫn thay được auto_afk._wait.
"""

import time

import config
from modules.afk_detectors import AfkLoopState
from ocr_engine import findNextTeamArrow, inspectCheckboxByText


def _core():
    from modules import auto_afk
    return auto_afk


def scanUntilKey(bot, keyName: str, timeout: float):
    """
    Quét lại màn hình tới khi thấy nút `keyName` (màn mới load chậm), tối đa `timeout` giây.
    Chỉ bot thật (có peekScreen, quan sát được màn hình theo thời gian) mới quét lại; bot giả lập quét 1 lần.
    Trả về (screen, ox, oy, rect, items, hit) hoặc None nếu hết giờ / mất cửa sổ / Stop.
    """
    core = _core()
    deadline = time.monotonic() + (timeout if hasattr(bot, "peekScreen") else 0.0)
    while True:
        screen, ox, oy, rect, items = core._scanGame(bot)
        if screen is None:
            return None
        hit = core._findKey(bot, items, keyName)
        if hit:
            return screen, ox, oy, rect, items, hit
        if time.monotonic() >= deadline or not core._wait(bot, config.SCREEN_RESCAN_INTERVAL):
            return None


def applyStatsModalTeam(bot, statsScreen, ox: int, oy: int, statsRect, statsItems,
                        st: AfkLoopState | None = None, failedAttempts: int = 1):
    """Bật lọc đội hình đã sở hữu, chuyển sang team kế tiếp (nếu cần) và bấm Sao chép."""
    core = _core()
    ownedHit = core._findKey(bot, statsItems, "owned_team")
    if ownedHit:
        isChecked, cbX, cbY = inspectCheckboxByText(statsScreen, ownedHit[3], ox, oy)
        if not isChecked:
            bot._log("🖱 Tích chọn ô 'Chỉ hiển thị đội hình đã sở hữu'...")
            if not core._safeClick(bot, cbX, cbY, statsRect) or not core._settle(bot, statsScreen, 1.0):
                return
            statsScreen, ox, oy, statsRect, statsItems = core._scanGame(bot)
            if statsScreen is None:
                return

    attempts = st.failedAttempts if st is not None else failedAttempts
    teamMoves = max(0, attempts - 1)
    alreadySwitched = st.teamSwitchedInStats if st is not None else False
    if teamMoves > 0 and not alreadySwitched:
        nextArrow = findNextTeamArrow(statsScreen, ox, oy)
        if nextArrow:
            bot._log(f"🖱 Click chuyển sang Team tiếp theo ({teamMoves} lần)...")
            for _ in range(teamMoves):
                if not core._safeClick(bot, nextArrow[0], nextArrow[1], statsRect):
                    return
                # Chỉ đổi ảnh chân dung team (vùng nhỏ) -> chờ ngắn cố định thay vì chờ cả màn hình đổi
                if not core._wait(bot, config.TEAM_SWITCH_WAIT):
                    return
            if st is not None:
                st.teamSwitchedInStats = True
            statsScreen, ox, oy, statsRect, statsItems = core._scanGame(bot)
            if statsScreen is None:
                return
        else:
            bot._log("⚠️ Không tìm thấy nút chuyển Team, sao chép đội hình đang hiển thị...")

    copyHit = core._findKey(bot, statsItems, "copy_team")
    if copyHit:
        bot._log("🖱 Click 'Sao chép' đội hình...")
        clicked = core._safeClick(bot, copyHit[0], copyHit[1], statsRect)
        if st is not None:
            st.teamSwitchedInStats = False
        core._settle(bot, statsScreen, 2.0) if clicked else core._wait(bot, 1.0)
    else:
        bot._log("⚠️ Không tìm thấy nút 'Sao chép', nhấn ESC.")
        core._safeEscape(bot)
        core._wait(bot, 1.0)


def handlePickTeamInStats(bot, st: AfkLoopState):
    """Sau 'Thử Lại': chờ màn chuẩn bị đấu load xong, mở 'Thành tích' và sao chép đội hình."""
    core = _core()
    prep = scanUntilKey(bot, "stats", config.PREP_SCREEN_WAIT)
    if prep is None:
        if not bot._stop_event.is_set():
            bot._log("⚠️ Không tìm thấy nút 'Thành tích' ở màn hình chuẩn bị đấu.")
        return
    prepScreen, _, _, prepRect, _, statsHit = prep
    bot._log("🖱 Click 'Thành tích'...")
    if not core._safeClick(bot, statsHit[0], statsHit[1], prepRect) or not core._settle(bot, prepScreen, 2.0):
        return
    stats = scanUntilKey(bot, "copy_team", config.PREP_SCREEN_WAIT)
    if stats is not None:
        statsScreen, ox, oy, statsRect, statsItems, _ = stats
        applyStatsModalTeam(bot, statsScreen, ox, oy, statsRect, statsItems, st=st)
    elif not bot._stop_event.is_set():
        bot._log("⚠️ Bảng 'Thành tích' không hiện nút 'Sao chép', nhấn ESC.")
        core._safeEscape(bot)
        core._wait(bot, 1.0)
