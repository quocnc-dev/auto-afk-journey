"""Module tự động vượt ải Auto AFK bằng OCR + Neo tọa độ + HSV (không cần template)."""

import re
import time
import logging

import config
from modules.afk_detectors import (
    AfkLoopState, detectPassiveWaitState, findAutoProgressState, findInBattleAuto,
    findMainLobbyEntry, findPauseAutoConfirmCancel, isMainOverworldScreen, parseStagesCleared, roiToScreenRect,
)
from modules.debug_snapshot import saveSnapshot
from modules.game_actions import describePopupCause, safeClick as _safeClick, safeEscape as _safeEscape
from modules.game_actions import waitForScreenChange, waitWatchingFocus
from modules.team_copy import applyStatsModalTeam as _applyStatsModalTeam, handlePickTeamInStats as _handlePickTeamInStats

logger = logging.getLogger("AFK_Bot.AutoAFK")

FAIL_THRESHOLD_TO_SWITCH_MODE = 5
NO_ACTION_LIMIT_SECONDS = 1200
PASSIVE_WAIT_KEYS = ("auto_progress_running", "in_battle_auto")


def _wait(bot, seconds: float) -> bool:
    """Chờ có ngắt sớm khi nhận tín hiệu Stop; trả về False nếu đã dừng."""
    if bot._stop_event.is_set():
        return False
    return not bot._stop_event.wait(seconds)


def _settle(bot, prevScreen, seconds: float) -> bool:
    """Sau click: chờ màn hình đổi rồi đứng yên (tối đa `seconds`), thay cho ngủ cố định."""
    return waitForScreenChange(bot, prevScreen, seconds, _wait)


def _clickSettle(bot, x: int, y: int, rect, prevScreen, seconds: float) -> bool:
    """Click rồi chờ màn hình đổi; click bị hủy (mất focus / ngoài cửa sổ) thì chỉ chờ ngắn rồi quét lại."""
    if _safeClick(bot, x, y, rect):
        return _settle(bot, prevScreen, seconds)
    _wait(bot, 1.0)
    return False


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


def _waitKeyGone(bot, keyName: str, timeout: float, **findArgs) -> bool:
    """Bot thật: quét lại tới khi nút `keyName` biến mất (đã chuyển màn), tối đa timeout giây; True nếu đã biến mất."""
    if not hasattr(bot, "peekScreen"):
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        screen, _, _, _, items = _scanGame(bot)
        if screen is None or not _findKey(bot, items, keyName, **findArgs):
            return True
        if not _wait(bot, config.SCREEN_RESCAN_INTERVAL):
            return False
    return False


def _confirmStillThere(bot, keyName: str, **findArgs) -> bool:
    """Bot thật: quét lại 1 lần sau giây lát; chữ thoáng qua (hiệu ứng/kỹ năng trong trận) sẽ không còn."""
    if not hasattr(bot, "peekScreen"):
        return True
    if not _wait(bot, config.SCREEN_CONFIRM_DELAY):
        return False
    screen, _, _, _, items = _scanGame(bot)
    return screen is not None and bool(_findKey(bot, items, keyName, **findArgs))


def _handleDefeatSwitchMode(bot, screen, originX: int, originY: int, rect, items, retryHit, preferChallenge: bool) -> bool:
    """Quay về sảnh khi thua đủ mốc và đổi nhánh ưu tiên giữa Huyền Linh và Thường."""
    newPrefer = not preferChallenge
    modeName = "Thách Đấu Huyền Linh SV" if newPrefer else "Chiến Đấu Thường"
    bot._log(f"🔄 Thất bại liên tiếp đạt mốc! Quay về sảnh và đổi mode ưu tiên sang: {modeName}")

    backHit = _findKey(bot, items, "back")
    if backHit:
        bot._log("🖱 Click nút 'Back' (OCR)...")
        clicked = _safeClick(bot, backHit[0], backHit[1], rect)
    else:
        retryItem = retryHit[3]
        backX = max(originX + 10, retryItem.x1 + int(retryItem.height * config.DEFEAT_BACK_HEIGHT_MULT))
        bot._log(f"🖱 Click tọa độ nút Back tương đối ({backX}, {retryHit[1]})...")
        clicked = _safeClick(bot, backX, retryHit[1], rect)
    _settle(bot, screen, 2.5) if clicked else _wait(bot, 1.0)
    return newPrefer


def _tryClickStageOption(bot, screen, items, rect, preferChallenge: bool) -> bool:
    """Thử vào trận ở sảnh AFK theo thứ tự ưu tiên."""
    fightArgs = ("fight", "Chiến Đấu thường", config.FIGHT_EXCLUDE_KEYS, config.FIGHT_EXTRA_EXCLUDES, True)
    challengeArgs = ("challenge_hl", "Thách Đấu Huyền Linh SV", None, config.CHALLENGE_HL_EXTRA_EXCLUDES, False)
    order = [challengeArgs, fightArgs] if preferChallenge else [fightArgs, challengeArgs]

    for keyName, label, excludeKeys, extraExcludes, wholePhrase in order:
        hit = _findKey(bot, items, keyName, excludeKeys=excludeKeys, extraExcludes=extraExcludes, wholePhrase=wholePhrase)
        if hit:
            bot._log(f"🖱 Click '{label}' tại ({hit[0]}, {hit[1]})...")
            if _clickSettle(bot, hit[0], hit[1], rect, screen, 2.5):
                # Game load chậm: nút còn trên màn chưa chắc là bấm hụt -> chờ nút biến mất trước khi tính lại
                _waitKeyGone(bot, keyName, config.STAGE_ENTER_WAIT, excludeKeys=excludeKeys,
                             extraExcludes=extraExcludes, wholePhrase=wholePhrase)
            return True
    return False


def run_auto_afk(bot):
    """Chạy Auto AFK; dừng an toàn nếu mất cửa sổ game quá lâu hoặc kẹt một trạng thái quá 20 phút."""
    bot._log("🚀 Bắt đầu vòng lặp Auto AFK bằng OCR...")

    st = AfkLoopState()
    missingWindowSince, lastFrame, unknownStreak, pauseRepeat = None, (None, None, None), 0, 0

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
            st.lastFocusLossTime = now
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
        pauseRepeat = pauseRepeat + 1 if pauseCancel is not None else 0
        if pauseCancel is not None:
            st.markProgress("pause_auto_prompt")
            if pauseRepeat == config.PAUSE_PROMPT_STUCK_REPEAT:
                bot._log(f"⚠️ Popup tắt auto vẫn còn sau {pauseRepeat} lần bấm X — lưu ảnh debug để kiểm tra vị trí nút.")
                saveSnapshot(bot, "pause_prompt_stuck", screen, items, rect, extra={"click": list(pauseCancel)})
            bot._log("⚠️ Phát hiện hộp thoại 'Tắt chế độ Chiến Đấu Tự Động?'. Bấm X để tiếp tục auto...")
            if pauseRepeat == 1:
                bot._log(describePopupCause(bot, st, now))
            _clickSettle(bot, pauseCancel[0], pauseCancel[1], rect, screen, 1.5)
            continue

        retryHit = _findKey(bot, items, "retry", wholePhrase=True)
        if retryHit:
            st.markProgress("retry")
            fails = st.recordDefeat(fromMainDone=False)
            bot._log(f"❌ Trận đấu THẤT BẠI (Lần thứ {fails}/{FAIL_THRESHOLD_TO_SWITCH_MODE} liên tiếp)!")
            if fails >= FAIL_THRESHOLD_TO_SWITCH_MODE:
                st.preferChallenge = _handleDefeatSwitchMode(bot, screen, originX, originY, rect, items, retryHit, st.preferChallenge)
                st.onModeSwitched()
                continue
            bot._log("🖱 Click 'Thử Lại'...")
            if _safeClick(bot, retryHit[0], retryHit[1], rect) and _settle(bot, screen, 2.5):
                _handlePickTeamInStats(bot, st)
            continue

        if _findKey(bot, items, "copy_team"):
            st.markProgress("copy_team")
            _applyStatsModalTeam(bot, screen, originX, originY, rect, items, st=st)
            continue

        # Đang trong trận (đồng hồ / thanh 'Tự Động Chiến Đấu') thì không có màn Hoàn Tất hay nút Đóng thật
        inBattle = findInBattleAuto(bot, items, _findKey, rect=rect)
        finishArgs = dict(excludeKeys=["in_battle_auto"], extraExcludes=config.FIGHT_EXTRA_EXCLUDES)
        closeHit = None if inBattle else _findKey(bot, items, "close_btn", exactOnly=True)
        finishHit = None if inBattle else _findKey(bot, items, "auto_battle_complete", **finishArgs)
        if finishHit and not re.search(r"hoan\s*tat|complete", finishHit[3].normText):
            finishHit = None  # Khớp mờ kiểu 'Tự Động Hoán Đổi' (kỹ năng) — không có chữ 'hoàn tất' thật
        if (closeHit or finishHit) and not (_confirmStillThere(bot, "close_btn", exactOnly=True) if closeHit
                                            else _confirmStillThere(bot, "auto_battle_complete", **finishArgs)):
            continue
        if closeHit or finishHit:
            target = closeHit or finishHit
            # Chỉ tính thua khi có màn 'Hoàn Tất' / 'Thất bại'; nút 'Đóng' của popup khác thì chỉ đóng
            isDefeat = bool(finishHit) or bool(_findKey(bot, items, "defeat"))
            cleared = parseStagesCleared(items) if finishHit else None
            if cleared:
                # Auto đã thắng qua >= 1 màn rồi mới dừng -> chuỗi thua liên tiếp phải tính lại từ đầu
                st.onVictory()
                bot._log(f"🎉 Auto đã vượt {cleared} màn trước khi dừng — reset chuỗi thua liên tiếp.")
            if isDefeat:
                fails = st.recordDefeat(fromMainDone=True)
                bot._log(f"🖱 Màn 'Hoàn Tất' (thua lần {fails}/{FAIL_THRESHOLD_TO_SWITCH_MODE} liên tiếp). Click đóng quay lại chọn chế độ...")
            else:
                bot._log("🖱 Phát hiện popup có nút 'Đóng' (không phải màn thua). Click đóng...")
            st.markProgress("auto_battle_complete" if isDefeat else "close_popup")
            _clickSettle(bot, target[0], target[1], rect, screen, 2.5)
            continue

        autoProgress = findAutoProgressState(bot, items, _findKey)
        if autoProgress is not None and autoProgress[0]:
            st.markProgress("auto_progress_done")
            fails = st.recordDefeat(fromMainDone=True)
            bot._log(f"❌ Phát hiện 'Tự Động Xử Lý Xong!' (Thua lần {fails}/{FAIL_THRESHOLD_TO_SWITCH_MODE}). Click vào chạy lại...")
            _clickSettle(bot, autoProgress[1], autoProgress[2], rect, screen, 2.5)
            continue

        waitState = detectPassiveWaitState(bot, items, _findKey, autoProgress=autoProgress, rect=rect)
        if waitState is not None:
            waitKey, waitMsg, keepAlive = waitState
            if st.lastStateKey not in PASSIVE_WAIT_KEYS:  # 2 trạng thái chờ xen kẽ trong trận -> chỉ log lúc bắt đầu chờ
                bot._log(waitMsg)
            st.markProgress(waitKey, refreshAlways=keepAlive)
            st.onEnterBattle()
            waitWatchingFocus(bot, st, config.AUTO_PROGRESS_POLL_INTERVAL, _wait)
            continue

        isMainScreen = isMainOverworldScreen(bot, items, _findKey)
        if not isMainScreen:
            statsHit = _findKey(bot, items, "stats") if st.needTeamChange else None
            if statsHit:
                # Thua kiểu 'Hoàn Tất' / 'Xong!' -> về chọn chế độ rồi vào lại: đổi team trước khi đánh
                bot._log("🔁 Vừa thua — chép team kế tiếp trước khi vào trận...")
                _handlePickTeamInStats(bot, st, prepFrame=(screen, rect, items, statsHit))
                continue
            autoHit = _findKey(bot, items, "auto_battle", excludeKeys=config.AUTO_BATTLE_EXCLUDE_KEYS, extraExcludes=config.AUTO_BATTLE_EXTRA_EXCLUDES, wholePhrase=True)
            if autoHit:
                st.markProgress("auto_battle")
                st.onEnterBattle()
                bot._log("🖱 Click 'Chiến Đấu Tự Động'...")
                _clickSettle(bot, autoHit[0], autoHit[1], rect, screen, 3.0)
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
                st.onVictory()
                st.markProgress("victory")
                _clickSettle(bot, originX + int(w * 0.5), originY + int(h * 0.5), rect, screen, 3.0)
                continue

        deepScan = isMainScreen or now - st.lastDeepScanTime >= config.LOBBY_DEEP_SCAN_INTERVAL
        if deepScan:
            st.lastDeepScanTime = now
        afkHit = findMainLobbyEntry(bot, screen, originX, originY, rect, items, _findKey, deepScan=deepScan)
        if afkHit:
            st.markProgress("afk_icon")
            st.lobbyClicksSameMode = 0
            bot._log("🖱 Tìm thấy sảnh chính. Click vào màn AFK...")
            _clickSettle(bot, afkHit[0], afkHit[1], rect, screen, 2.0)
            continue

        bot._log("⏳ Đang theo dõi trận đấu hoặc trạng thái game...")
        unknownStreak = prevUnknown + 1
        if unknownStreak == config.DEBUG_UNKNOWN_STREAK:
            saveSnapshot(bot, "unknown_screen", screen, items, rect, extra={"lastState": st.lastStateKey})
        _wait(bot, 1.5)

    bot._log("✅ Dừng nhiệm vụ Auto AFK.")
    return True
