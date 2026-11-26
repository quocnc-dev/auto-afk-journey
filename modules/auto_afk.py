"""Module tự động vượt ải Auto AFK bằng OCR + Neo tọa độ + HSV (không cần template)."""

import time
import logging

import config
from modules.afk_detectors import (
    AfkLoopState, detectPassiveWaitState, findAutoProgressState,
    findMainLobbyEntry, findPauseAutoConfirmCancel, isMainOverworldScreen, roiToScreenRect,
)
from modules.debug_snapshot import saveSnapshot
from modules.game_actions import safeClick as _safeClick, safeEscape as _safeEscape, waitForScreenChange
from ocr_engine import inspectCheckboxByText, findNextTeamArrow

logger = logging.getLogger("AFK_Bot.AutoAFK")

FAIL_THRESHOLD_TO_SWITCH_MODE = 5
NO_ACTION_LIMIT_SECONDS = 1200


def _wait(bot, seconds: float) -> bool:
    """Chờ có ngắt sớm khi nhận tín hiệu Stop; trả về False nếu đã dừng."""
    if bot._stop_event.is_set():
        return False
    return not bot._stop_event.wait(seconds)


def _settle(bot, prevScreen, seconds: float) -> bool:
    """Sau click: chờ màn hình đổi rồi đứng yên (tối đa `seconds`), thay cho ngủ cố định."""
    return waitForScreenChange(bot, prevScreen, seconds, _wait)


def _scanGame(bot):
    """Chụp đúng cửa sổ game và chạy OCR; trả về screen=None nếu mất cửa sổ game."""
    if bot._stop_event.is_set():
        return None, 0, 0, None, []
    screen, originX, originY, rect = bot.captureGameScreen()
    if screen is None:
        return None, 0, 0, None, []
    bot._scanRect = rect
    items = bot.ocr.scanImage(screen, originX=originX, originY=originY)
    return screen, originX, originY, rect, items


def _findKey(bot, items, keyName: str, excludeKeys=None, extraExcludes=None, exactOnly=False, wholePhrase=False):
    """Tìm cụm chữ theo key đã khai báo trong config.OCR_KEYWORDS."""
    keywords = config.OCR_KEYWORDS.get(keyName, [])
    excludeWords = list(extraExcludes) if extraExcludes else []
    if excludeKeys:
        for exKey in excludeKeys:
            excludeWords.extend(config.OCR_KEYWORDS.get(exKey, []))
    keyRoi = config.OCR_KEY_ROIS.get(keyName)
    roiRect = roiToScreenRect(getattr(bot, "_scanRect", None), keyRoi) if keyRoi else None
    return bot.ocr.findText(items, keywords, excludeKeywords=excludeWords or None, roiScreenRect=roiRect,
                            exactOnly=exactOnly, wholePhrase=wholePhrase)


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
        retryItem = retryHit[3]
        backX = max(originX + 10, retryItem.x1 + int(retryItem.height * config.DEFEAT_BACK_HEIGHT_MULT))
        bot._log(f"🖱 Click tọa độ nút Back tương đối ({backX}, {retryHit[1]})...")
        _safeClick(bot, backX, retryHit[1], rect)
    _settle(bot, screen, 2.5)
    return newPrefer


def _applyStatsModalTeam(bot, statsScreen, ox: int, oy: int, statsRect, statsItems, st: AfkLoopState | None = None, failedAttempts: int = 1):
    """Bật lọc đội hình đã sở hữu, chuyển sang team kế tiếp (nếu cần) và bấm Sao chép."""
    ownedHit = _findKey(bot, statsItems, "owned_team")
    if ownedHit:
        isChecked, cbX, cbY = inspectCheckboxByText(statsScreen, ownedHit[3], ox, oy)
        if not isChecked:
            bot._log("🖱 Tích chọn ô 'Chỉ hiển thị đội hình đã sở hữu'...")
            if not _safeClick(bot, cbX, cbY, statsRect) or not _settle(bot, statsScreen, 1.0):
                return
            statsScreen, ox, oy, statsRect, statsItems = _scanGame(bot)
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
                if not _safeClick(bot, nextArrow[0], nextArrow[1], statsRect) or not _settle(bot, statsScreen, 0.8):
                    return
            if st is not None:
                st.teamSwitchedInStats = True
            statsScreen, ox, oy, statsRect, statsItems = _scanGame(bot)
            if statsScreen is None:
                return
        else:
            bot._log("⚠️ Không tìm thấy nút chuyển Team, sao chép đội hình đang hiển thị...")

    copyHit = _findKey(bot, statsItems, "copy_team")
    if copyHit:
        bot._log("🖱 Click 'Sao chép' đội hình...")
        _safeClick(bot, copyHit[0], copyHit[1], statsRect)
        if st is not None:
            st.teamSwitchedInStats = False
        _settle(bot, statsScreen, 2.0)
    else:
        bot._log("⚠️ Không tìm thấy nút 'Sao chép', nhấn ESC.")
        _safeEscape(bot)
        _wait(bot, 1.0)


def _handlePickTeamInStats(bot, st: AfkLoopState):
    """Mở bảng Thành Tích từ màn chuẩn bị đấu và chọn sao chép đội hình."""
    prepScreen, _, _, prepRect, prepItems = _scanGame(bot)
    if prepScreen is None:
        return
    statsHit = _findKey(bot, prepItems, "stats")
    if not statsHit:
        bot._log("⚠️ Không tìm thấy nút 'Thành tích' ở màn hình chuẩn bị đấu.")
        return
    bot._log("🖱 Click 'Thành tích'...")
    if not _safeClick(bot, statsHit[0], statsHit[1], prepRect) or not _settle(bot, prepScreen, 2.0):
        return
    statsScreen, ox, oy, statsRect, statsItems = _scanGame(bot)
    if statsScreen is not None:
        _applyStatsModalTeam(bot, statsScreen, ox, oy, statsRect, statsItems, st=st)


def _tryClickStageOption(bot, screen, items, rect, preferChallenge: bool) -> bool:
    """Thử vào trận ở sảnh AFK theo thứ tự ưu tiên."""
    fightArgs = ("fight", "Chiến Đấu thường", config.FIGHT_EXCLUDE_KEYS, config.FIGHT_EXTRA_EXCLUDES, True)
    challengeArgs = ("challenge_hl", "Thách Đấu Huyền Linh SV", None, config.CHALLENGE_HL_EXTRA_EXCLUDES, False)
    order = [challengeArgs, fightArgs] if preferChallenge else [fightArgs, challengeArgs]

    for keyName, label, excludeKeys, extraExcludes, wholePhrase in order:
        hit = _findKey(bot, items, keyName, excludeKeys=excludeKeys, extraExcludes=extraExcludes, wholePhrase=wholePhrase)
        if hit:
            bot._log(f"🖱 Click '{label}' tại ({hit[0]}, {hit[1]})...")
            if _safeClick(bot, hit[0], hit[1], rect):
                _settle(bot, screen, 2.5)
            return True
    return False


def run_auto_afk(bot):
    """Chạy Auto AFK; dừng an toàn nếu mất cửa sổ game quá lâu hoặc kẹt một trạng thái quá 20 phút."""
    bot._log("🚀 Bắt đầu vòng lặp Auto AFK bằng OCR...")

    st = AfkLoopState()
    missingWindowSince, lastFrame, unknownStreak = None, (None, None, None), 0

    while not bot._stop_event.is_set():
        now = time.time()
        if now - st.lastProgressTime > NO_ACTION_LIMIT_SECONDS:
            bot._log("⚠️ Màn hình không có tiến triển mới quá 20 phút. Dừng Auto AFK để đảm bảo an toàn!")
            saveSnapshot(bot, "no_progress", *lastFrame, extra={"lastState": st.lastStateKey})
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
        missingWindowSince, lastFrame, prevUnknown, unknownStreak = None, (screen, items, rect), unknownStreak, 0

        pauseCancel = findPauseAutoConfirmCancel(bot, screen, originX, originY, items, _findKey)
        if pauseCancel is not None:
            st.markProgress("pause_auto_prompt")
            bot._log("⚠️ Phát hiện hộp thoại 'Tắt chế độ Chiến Đấu Tự Động?'. Bấm X để tiếp tục auto...")
            _safeClick(bot, pauseCancel[0], pauseCancel[1], rect)
            _settle(bot, screen, 1.5)
            continue

        retryHit = _findKey(bot, items, "retry", wholePhrase=True)
        if retryHit:
            st.markProgress("retry")
            fails = st.recordDefeat(fromMainDone=False)
            bot._log(f"❌ Trận đấu THẤT BẠI (Lần thứ {fails}/{FAIL_THRESHOLD_TO_SWITCH_MODE} liên tiếp)!")
            if fails >= FAIL_THRESHOLD_TO_SWITCH_MODE:
                st.preferChallenge = _handleDefeatSwitchMode(bot, screen, originX, originY, rect, items, retryHit, st.preferChallenge)
                st.failedAttempts = 0
                continue
            bot._log("🖱 Click 'Thử Lại'...")
            if _safeClick(bot, retryHit[0], retryHit[1], rect) and _settle(bot, screen, 2.5):
                _handlePickTeamInStats(bot, st)
            continue

        if _findKey(bot, items, "copy_team"):
            st.markProgress("copy_team")
            _applyStatsModalTeam(bot, screen, originX, originY, rect, items, st=st)
            continue

        closeHit = _findKey(bot, items, "close_btn", exactOnly=True)
        finishHit = _findKey(bot, items, "auto_battle_complete", excludeKeys=["in_battle_auto"], extraExcludes=config.FIGHT_EXTRA_EXCLUDES)
        if closeHit or finishHit:
            target = closeHit or finishHit
            # Chỉ tính thua khi có màn 'Hoàn Tất' / 'Thất bại'; nút 'Đóng' của popup khác thì chỉ đóng
            isDefeat = bool(finishHit) or bool(_findKey(bot, items, "defeat"))
            bot._log("🖱 Phát hiện màn 'Hoàn Tất' / nút 'Đóng'. Click đóng quay lại chọn chế độ..." if isDefeat
                     else "🖱 Phát hiện popup có nút 'Đóng' (không phải màn thua). Click đóng...")
            _safeClick(bot, target[0], target[1], rect)
            if isDefeat:
                st.recordDefeat(fromMainDone=True)
            st.markProgress("auto_battle_complete" if isDefeat else "close_popup")
            _settle(bot, screen, 2.5)
            continue

        autoProgress = findAutoProgressState(bot, items, _findKey)
        if autoProgress is not None and autoProgress[0]:
            st.markProgress("auto_progress_done")
            fails = st.recordDefeat(fromMainDone=True)
            bot._log(f"❌ Phát hiện 'Tự Động Xử Lý Xong!' (Thua lần {fails}/{FAIL_THRESHOLD_TO_SWITCH_MODE}). Click vào chạy lại...")
            _safeClick(bot, autoProgress[1], autoProgress[2], rect)
            _settle(bot, screen, 2.5)
            continue

        waitState = detectPassiveWaitState(bot, items, _findKey, autoProgress=autoProgress, rect=rect)
        if waitState is not None:
            waitKey, waitMsg, keepAlive = waitState
            if st.lastStateKey != waitKey:
                bot._log(waitMsg)
            st.markProgress(waitKey, refreshAlways=keepAlive)
            st.onEnterBattle()
            _wait(bot, config.AUTO_PROGRESS_POLL_INTERVAL)
            continue

        isMainScreen = isMainOverworldScreen(bot, items, _findKey)
        if not isMainScreen:
            autoHit = _findKey(bot, items, "auto_battle", excludeKeys=config.AUTO_BATTLE_EXCLUDE_KEYS, extraExcludes=config.AUTO_BATTLE_EXTRA_EXCLUDES, wholePhrase=True)
            if autoHit:
                st.markProgress("auto_battle")
                st.onEnterBattle()
                bot._log("🖱 Click 'Chiến Đấu Tự Động'...")
                _safeClick(bot, autoHit[0], autoHit[1], rect)
                _settle(bot, screen, 3.0)
                continue

            st.resolveLobbySwitch(bot, FAIL_THRESHOLD_TO_SWITCH_MODE)
            if _tryClickStageOption(bot, screen, items, rect, st.preferChallenge):
                st.defeatCounted = False
                st.lobbyClicksSameMode += 1
                st.markProgress("stage_option")
                continue

            victoryHit = _findKey(bot, items, "victory")
            if victoryHit:
                bot._log("🎉 Phát hiện màn hình CHIẾN THẮNG! Click tiếp tục...")
                h, w = screen.shape[:2]
                _safeClick(bot, originX + int(w * 0.5), originY + int(h * 0.5), rect)
                st.onVictory()
                st.markProgress("victory")
                _settle(bot, screen, 3.0)
                continue

        deepScan = isMainScreen or now - st.lastDeepScanTime >= config.LOBBY_DEEP_SCAN_INTERVAL
        if deepScan:
            st.lastDeepScanTime = now
        afkHit = findMainLobbyEntry(bot, screen, originX, originY, rect, items, _findKey, deepScan=deepScan)
        if afkHit:
            st.markProgress("afk_icon")
            st.lobbyClicksSameMode = 0
            bot._log("🖱 Tìm thấy sảnh chính. Click vào màn AFK...")
            _safeClick(bot, afkHit[0], afkHit[1], rect)
            _settle(bot, screen, 2.0)
            continue

        bot._log("⏳ Đang theo dõi trận đấu hoặc trạng thái game...")
        unknownStreak = prevUnknown + 1
        if unknownStreak == config.DEBUG_UNKNOWN_STREAK:
            saveSnapshot(bot, "unknown_screen", screen, items, rect, extra={"lastState": st.lastStateKey})
        _wait(bot, 1.5)

    bot._log("✅ Dừng nhiệm vụ Auto AFK.")
    return True
