"""
Module tự động vượt ải Auto AFK bằng OCR + Neo tọa độ + Kiểm tra màu HSV.
Không yêu cầu người dùng tự chụp bất kỳ ảnh template nào.
"""

import time
import logging

import config
from modules.afk_detectors import detectPassiveWaitState, findAutoProgressState, findMainLobbyEntry
from ocr_engine import inspectCheckboxByText, findNextTeamArrow

logger = logging.getLogger("AFK_Bot.AutoAFK")

FAIL_THRESHOLD_TO_SWITCH_MODE = 5
NO_ACTION_LIMIT_SECONDS = 1200


def _wait(bot, seconds: float) -> bool:
    """Chờ có ngắt sớm khi nhận tín hiệu Stop; trả về False nếu đã dừng."""
    if bot._stop_event.is_set():
        return False
    return not bot._stop_event.wait(seconds)


def _safeClick(bot, x: int, y: int, expectedRect=None) -> bool:
    """Chỉ click khi chưa Stop, cửa sổ game đang foreground và giữ nguyên vị trí đã chụp."""
    if bot._stop_event.is_set():
        return False
    guardFn = (lambda: bot.canInteractAt(x, y, expectedRect=expectedRect)) if hasattr(bot, "canInteractAt") else None
    if guardFn is not None and not guardFn():
        bot._log("⚠️ Cửa sổ game đã bị che, dịch chuyển hoặc mất focus — hủy click!")
        return False
    res = bot.ctrl.click(x, y, stop_event=bot._stop_event, guard_fn=guardFn)
    return (res is not False) and not bot._stop_event.is_set()


def _safeEscape(bot) -> bool:
    """Chỉ gửi phím ESC khi chưa Stop và cửa sổ game đang foreground."""
    if bot._stop_event.is_set():
        return False
    guardFn = bot.canSendKey if hasattr(bot, "canSendKey") else None
    if guardFn is not None and not guardFn():
        bot._log("⚠️ Mất focus cửa sổ game — hủy gửi phím ESC!")
        return False
    res = bot.ctrl.press_escape(stop_event=bot._stop_event, guard_fn=guardFn)
    return (res is not False) and not bot._stop_event.is_set()


def _scanGame(bot):
    """Chụp đúng cửa sổ game và chạy OCR; trả về screen=None nếu mất cửa sổ game."""
    if bot._stop_event.is_set():
        return None, 0, 0, None, []
    screen, originX, originY, rect = bot.captureGameScreen()
    if screen is None:
        return None, 0, 0, None, []
    items = bot.ocr.scanImage(screen, originX=originX, originY=originY)
    return screen, originX, originY, rect, items


def _findKey(bot, items, keyName: str, excludeKeys=None, extraExcludes=None, exactOnly=False, wholePhrase=False):
    """Tìm cụm chữ theo key đã khai báo trong config.OCR_KEYWORDS."""
    keywords = config.OCR_KEYWORDS.get(keyName, [])
    excludeWords = list(extraExcludes) if extraExcludes else []
    if excludeKeys:
        for exKey in excludeKeys:
            excludeWords.extend(config.OCR_KEYWORDS.get(exKey, []))
    return bot.ocr.findText(
        items, keywords, excludeKeywords=excludeWords or None, exactOnly=exactOnly, wholePhrase=wholePhrase
    )


def _handleDefeatSwitchMode(bot, screen, originX: int, originY: int, rect, items, retryHit, preferChallenge: bool) -> bool:
    """Quay về sảnh khi thua đủ mốc và đổi nhánh ưu tiên giữa Huyền Linh và Thường."""
    newPrefer = not preferChallenge
    modeName = "Thách Đấu Huyền Linh SV" if newPrefer else "Chiến Đấu Thường"
    bot._log(f"🔄 Thất bại liên tiếp đạt mốc! Quay về sảnh và đổi mode ưu tiên sang: {modeName}")

    backHit = _findKey(bot, items, "back")
    if backHit:
        bot._log("🖱 Click nút 'Back' (OCR)...")
        _safeClick(bot, backHit[0], backHit[1], rect)
    else:
        tplBack = bot.matcher.find(screen, "btn_afk_back_from_defeat")
        if tplBack:
            bot._log("🖱 Click nút 'Back' (fallback)...")
            _safeClick(bot, tplBack[0] + originX, tplBack[1] + originY, rect)
        else:
            retryItem = retryHit[3]
            backX = max(originX + 10, retryItem.x1 + int(retryItem.height * config.DEFEAT_BACK_HEIGHT_MULT))
            bot._log(f"🖱 Click tọa độ nút Back tương đối ({backX}, {retryHit[1]})...")
            _safeClick(bot, backX, retryHit[1], rect)
    _wait(bot, 2.5)
    return newPrefer


def _handlePickTeamInStats(bot, failedAttempts: int):
    """Mở bảng Thành Tích, bật lọc đội hình đã sở hữu và sao chép đội hình phù hợp."""
    prepScreen, _, _, prepRect, prepItems = _scanGame(bot)
    if prepScreen is None:
        return
    statsHit = _findKey(bot, prepItems, "stats")
    if not statsHit:
        bot._log("⚠️ Không tìm thấy nút 'Thành tích' ở màn hình chuẩn bị đấu.")
        return
    bot._log("🖱 Click 'Thành tích'...")
    if not _safeClick(bot, statsHit[0], statsHit[1], prepRect) or not _wait(bot, 2.0):
        return

    statsScreen, ox, oy, statsRect, statsItems = _scanGame(bot)
    if statsScreen is None:
        return

    ownedHit = _findKey(bot, statsItems, "owned_team")
    if ownedHit:
        isChecked, cbX, cbY = inspectCheckboxByText(statsScreen, ownedHit[3], ox, oy)
        if not isChecked:
            bot._log("🖱 Tích chọn ô 'Chỉ hiển thị đội hình đã sở hữu'...")
            if not _safeClick(bot, cbX, cbY, statsRect) or not _wait(bot, 1.0):
                return
            statsScreen, ox, oy, statsRect, statsItems = _scanGame(bot)
            if statsScreen is None:
                return

    teamMoves = max(0, failedAttempts - 1)
    if teamMoves > 0:
        nextArrow = findNextTeamArrow(statsScreen, ox, oy)
        if not nextArrow:
            tplNext = bot.matcher.find(statsScreen, "btn_afk_next_team")
            if tplNext:
                nextArrow = (tplNext[0] + ox, tplNext[1] + oy)
        if nextArrow:
            bot._log(f"🖱 Click chuyển sang Team tiếp theo ({teamMoves} lần)...")
            for _ in range(teamMoves):
                if not _safeClick(bot, nextArrow[0], nextArrow[1], statsRect) or not _wait(bot, 0.8):
                    return
            statsScreen, ox, oy, statsRect, statsItems = _scanGame(bot)
            if statsScreen is None:
                return
        else:
            bot._log("⚠️ Không tìm thấy nút chuyển Team, nhấn ESC.")
            _safeEscape(bot)
            _wait(bot, 1.0)
            return

    copyHit = _findKey(bot, statsItems, "copy_team")
    if copyHit:
        bot._log("🖱 Click 'Sao chép' đội hình...")
        _safeClick(bot, copyHit[0], copyHit[1], statsRect)
        _wait(bot, 2.0)
    else:
        bot._log("⚠️ Không tìm thấy nút 'Sao chép', nhấn ESC.")
        _safeEscape(bot)
        _wait(bot, 1.0)


def _tryClickStageOption(bot, items, rect, preferChallenge: bool) -> bool:
    """Thử vào trận ở sảnh AFK theo thứ tự ưu tiên."""
    fightArgs = ("fight", "Chiến Đấu thường", config.FIGHT_EXCLUDE_KEYS, config.FIGHT_EXTRA_EXCLUDES, True)
    challengeArgs = ("challenge_hl", "Thách Đấu Huyền Linh SV", None, config.CHALLENGE_HL_EXTRA_EXCLUDES, False)
    order = [challengeArgs, fightArgs] if preferChallenge else [fightArgs, challengeArgs]

    for keyName, label, excludeKeys, extraExcludes, wholePhrase in order:
        hit = _findKey(bot, items, keyName, excludeKeys=excludeKeys, extraExcludes=extraExcludes, wholePhrase=wholePhrase)
        if hit:
            bot._log(f"🖱 Click '{label}' tại ({hit[0]}, {hit[1]})...")
            if _safeClick(bot, hit[0], hit[1], rect):
                _wait(bot, 2.5)
            return True
    return False


def _markProgress(stateKey: str, lastStateKey: str | None, lastProgressTime: float) -> tuple[str, float]:
    """Cập nhật mốc thời gian tiến triển khi chuyển sang trạng thái mới."""
    if lastStateKey != stateKey:
        return stateKey, time.time()
    return lastStateKey, lastProgressTime


def run_auto_afk(bot):
    """
    Thực hiện nhiệm vụ Auto AFK bằng OCR + Neo tọa độ (không cần chụp template).
    Dừng an toàn nếu mất cửa sổ game quá lâu hoặc kẹt cùng một trạng thái quá 20 phút.
    """
    bot._log("🚀 Bắt đầu vòng lặp Auto AFK bằng OCR...")

    lastProgressTime = time.time()
    lastStateKey = None
    missingWindowSince = None
    failedAttempts = 0
    preferChallenge = True

    while not bot._stop_event.is_set():
        now = time.time()
        if now - lastProgressTime > NO_ACTION_LIMIT_SECONDS:
            bot._log("⚠️ Màn hình không có tiến triển mới quá 20 phút. Dừng Auto AFK để đảm bảo an toàn!")
            return False

        screen, originX, originY, rect, items = _scanGame(bot)
        if bot._stop_event.is_set():
            break

        if screen is None:
            if missingWindowSince is None:
                missingWindowSince = now
                bot._log("⚠️ Mất cửa sổ game AFK Journey, tạm dừng thao tác để tránh click nhầm...")
            elif now - missingWindowSince > config.TIMEOUT_WAIT_SCREEN:
                bot._log("❌ Không tìm lại được cửa sổ game sau thời gian chờ. Dừng Auto AFK!")
                return False
            _wait(bot, 1.0)
            continue
        missingWindowSince = None

        retryHit = _findKey(bot, items, "retry")
        if retryHit:
            lastStateKey, lastProgressTime = _markProgress("retry", lastStateKey, lastProgressTime)
            failedAttempts += 1
            bot._log(f"❌ Trận đấu THẤT BẠI (Lần thứ {failedAttempts} liên tiếp)!")
            if failedAttempts % FAIL_THRESHOLD_TO_SWITCH_MODE == 0:
                preferChallenge = _handleDefeatSwitchMode(
                    bot, screen, originX, originY, rect, items, retryHit, preferChallenge
                )
                failedAttempts = 0
                continue
            bot._log("🖱 Click 'Thử Lại'...")
            if _safeClick(bot, retryHit[0], retryHit[1], rect) and _wait(bot, 2.5):
                _handlePickTeamInStats(bot, failedAttempts)
            continue

        finishHit = _findKey(bot, items, "auto_battle_complete", excludeKeys=["in_battle_auto"], extraExcludes=config.FIGHT_EXTRA_EXCLUDES)
        if finishHit:
            bot._log("🎉 Phát hiện 'Chiến Đấu Tự Động Hoàn Tất'. Click đóng...")
            _safeClick(bot, finishHit[0], finishHit[1], rect)
            failedAttempts = 0
            preferChallenge = True
            lastStateKey, lastProgressTime = _markProgress("auto_battle_complete", lastStateKey, lastProgressTime)
            _wait(bot, 2.5)
            continue

        autoProgress = findAutoProgressState(bot, items, _findKey)
        if autoProgress is not None and autoProgress[0]:
            lastStateKey, lastProgressTime = _markProgress("auto_progress_done", lastStateKey, lastProgressTime)
            bot._log("❌ Phát hiện 'Tự Động Xử Lý Xong!' ở màn hình chính. Click vào chạy lại...")
            _safeClick(bot, autoProgress[1], autoProgress[2], rect)
            _wait(bot, 2.5)
            continue

        waitState = detectPassiveWaitState(bot, items, _findKey, autoProgress=autoProgress)
        if waitState is not None:
            waitKey, waitMsg, keepAlive = waitState
            if lastStateKey != waitKey:
                bot._log(waitMsg)
            lastStateKey, lastProgressTime = _markProgress(waitKey, lastStateKey, lastProgressTime)
            if keepAlive:
                lastProgressTime = time.time()
            _wait(bot, config.AUTO_PROGRESS_POLL_INTERVAL)
            continue

        autoHit = _findKey(bot, items, "auto_battle", excludeKeys=config.AUTO_BATTLE_EXCLUDE_KEYS, extraExcludes=config.AUTO_BATTLE_EXTRA_EXCLUDES)
        if autoHit:
            lastStateKey, lastProgressTime = _markProgress("auto_battle", lastStateKey, lastProgressTime)
            bot._log("🖱 Click 'Chiến Đấu Tự Động'...")
            _safeClick(bot, autoHit[0], autoHit[1], rect)
            _wait(bot, 3.0)
            continue

        if _tryClickStageOption(bot, items, rect, preferChallenge):
            lastStateKey, lastProgressTime = _markProgress("stage_option", lastStateKey, lastProgressTime)
            continue

        victoryHit = _findKey(bot, items, "victory")
        if victoryHit:
            bot._log("🎉 Phát hiện màn hình CHIẾN THẮNG! Click tiếp tục...")
            h, w = screen.shape[:2]
            _safeClick(bot, originX + int(w * 0.5), originY + int(h * 0.5), rect)
            failedAttempts = 0
            preferChallenge = True
            lastStateKey, lastProgressTime = _markProgress("victory", lastStateKey, lastProgressTime)
            _wait(bot, 3.0)
            continue

        # Logic cũ quét góc afk_icon đã chuyển sang findMainLobbyEntry (modules/afk_detectors.py)
        afkHit = findMainLobbyEntry(bot, screen, originX, originY, rect, items, _findKey)
        if afkHit:
            lastStateKey, lastProgressTime = _markProgress("afk_icon", lastStateKey, lastProgressTime)
            bot._log("🖱 Tìm thấy sảnh chính. Click vào màn AFK...")
            _safeClick(bot, afkHit[0], afkHit[1], rect)
            _wait(bot, 2.0)
            continue

        bot._log("⏳ Đang theo dõi trận đấu hoặc trạng thái game...")
        _wait(bot, 1.5)

    bot._log("✅ Dừng nhiệm vụ Auto AFK.")
    return True
