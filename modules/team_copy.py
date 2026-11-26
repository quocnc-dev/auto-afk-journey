"""
Luồng sao chép đội hình sau khi thua: màn chuẩn bị đấu -> 'Thành tích' -> (lọc đội đã sở hữu,
chuyển team kế tiếp) -> 'Sao chép'.
Dùng helper của modules.auto_afk (import lúc gọi) để test vẫn thay được auto_afk._wait.
"""

import time

import config
from modules.afk_detectors import AfkLoopState
from modules.debug_snapshot import saveSnapshot
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


def _snapshotIfArrowMoved(bot, arrow, screen, items, rect) -> None:
    """
    Mũi tên chuyển team nằm khác chỗ lần trước -> có thể dò nhầm (vd 1482,320) -> lưu ảnh bảng Thành tích.
    So theo tọa độ trong cửa sổ game để kéo cửa sổ đi chỗ khác không bị báo nhầm.
    """
    left, top = (rect[0], rect[1]) if rect else (0, 0)
    rel = (arrow[0] - left, arrow[1] - top)
    prev = getattr(bot, "_lastTeamArrow", None)
    bot._lastTeamArrow = rel
    if prev is None or max(abs(rel[0] - prev[0]), abs(rel[1] - prev[1])) <= config.TEAM_ARROW_MOVED_PX:
        return
    path = saveSnapshot(bot, "team_arrow_moved", screen, items, rect,
                        extra={"arrow": list(arrow), "arrowInWindow": list(rel), "prevArrowInWindow": list(prev)})
    bot._log(f"🔎 Mũi tên chuyển team ở ({rel[0]}, {rel[1]}) trong cửa sổ, khác lần trước ({prev[0]}, {prev[1]})"
             + (" — đã lưu ảnh để kiểm tra." if path else "."))


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

    # Mỗi lần thua chép team kế tiếp: bảng mở ở team đầu -> bấm mũi tên `teamCursor` lần để tới team (teamCursor + 1)
    teamMoves = st.teamCursor if st is not None else max(0, failedAttempts - 1)
    targetTeam = teamMoves + 1
    # Lần trước bị hủy giữa chừng (mất focus...) thì bảng đã lệch sẵn vài team -> chỉ bấm phần còn thiếu
    clicksDone = st.statsArrowClicks if st is not None else 0
    if teamMoves > clicksDone:
        nextArrow = findNextTeamArrow(statsScreen, ox, oy)
        if nextArrow:
            _snapshotIfArrowMoved(bot, nextArrow, statsScreen, statsItems, statsRect)
            bot._log(f"🖱 Click chuyển sang Team tiếp theo ({teamMoves - clicksDone} lần)...")
            for _ in range(teamMoves - clicksDone):
                if not core._safeClick(bot, nextArrow[0], nextArrow[1], statsRect):
                    return
                if st is not None:
                    st.statsArrowClicks += 1
                # Chỉ đổi ảnh chân dung team (vùng nhỏ) -> chờ ngắn cố định thay vì chờ cả màn hình đổi
                if not core._wait(bot, config.TEAM_SWITCH_WAIT):
                    return
            statsScreen, ox, oy, statsRect, statsItems = core._scanGame(bot)
            if statsScreen is None:
                return
        else:
            # Bảng Thành tích (đã lọc đội sở hữu) chỉ có 1 đội hoặc đã hết danh sách — không phải lỗi bot
            targetTeam = clicksDone + 1
            bot._log(f"🔎 Bảng Thành tích không có nút chuyển team (chỉ có {targetTeam} đội phù hợp / đã hết danh sách)"
                     f" — chép team #{targetTeam}.")

    copyHit = core._findKey(bot, statsItems, "copy_team")
    if copyHit:
        bot._log(f"🖱 Click 'Sao chép' đội hình (team #{targetTeam} trong bảng Thành tích)...")
        clicked = core._safeClick(bot, copyHit[0], copyHit[1], statsRect)
        if st is not None:
            st.statsArrowClicks = 0
            if clicked:
                st.teamCursor = targetTeam
                st.needTeamChange = False
        core._settle(bot, statsScreen, 2.0) if clicked else core._wait(bot, 1.0)
    else:
        bot._log("⚠️ Không tìm thấy nút 'Sao chép', nhấn ESC.")
        core._safeEscape(bot)
        core._wait(bot, 1.0)


def handlePickTeamInStats(bot, st: AfkLoopState, prepFrame=None):
    """Ở màn chuẩn bị đấu (sau 'Thử Lại' hoặc vào lại từ sảnh): mở 'Thành tích' và chép team kế tiếp."""
    core = _core()
    st.needTeamChange = False  # Chỉ thử 1 lần mỗi lần thua, tránh mở Thành tích lặp mãi nếu có lỗi
    # prepFrame = (screen, rect, items, statsHit) khi vòng lặp chính đã có sẵn khung hình -> khỏi OCR lại
    prep = (prepFrame[0], 0, 0, prepFrame[1], prepFrame[2], prepFrame[3]) if prepFrame else \
        scanUntilKey(bot, "stats", config.PREP_SCREEN_WAIT)
    if prep is None:
        if not bot._stop_event.is_set():
            bot._log("⚠️ Không tìm thấy nút 'Thành tích' ở màn hình chuẩn bị đấu.")
        return
    prepScreen, _, _, prepRect, _, statsHit = prep
    st.statsArrowClicks = 0  # Bảng Thành tích mới mở luôn bắt đầu ở team đầu
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
