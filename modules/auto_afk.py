"""
Module tự động vượt ải Auto AFK bằng OCR + Neo tọa độ + Kiểm tra màu HSV.
Không yêu cầu người dùng tự chụp bất kỳ ảnh template nào.
"""

import time
import logging

import config
from ocr_engine import inspectCheckboxByText, findNextTeamArrow

logger = logging.getLogger("AFK_Bot.AutoAFK")

# Cấu hình số lần thất bại liên tiếp trước khi đổi mode ưu tiên nhánh đấu
FAIL_THRESHOLD_TO_SWITCH_MODE = 5
NO_ACTION_LIMIT_SECONDS = 1200


def _scanGame(bot):
    """Chụp đúng cửa sổ game và chạy OCR 1 lần cho cả frame."""
    screen, originX, originY, rect = bot.captureGameScreen()
    items = bot.ocr.scanImage(screen, originX=originX, originY=originY)
    return screen, originX, originY, rect, items


def _findKey(bot, items, keyName: str, excludeKeys: list[str] | None = None, exactOnly: bool = False):
    """Tìm cụm chữ theo key đã khai báo trong config.OCR_KEYWORDS."""
    keywords = config.OCR_KEYWORDS.get(keyName, [])
    excludeWords = []
    if excludeKeys:
        for exKey in excludeKeys:
            excludeWords.extend(config.OCR_KEYWORDS.get(exKey, []))
    return bot.ocr.findText(
        items,
        keywords,
        excludeKeywords=excludeWords or None,
        exactOnly=exactOnly,
    )


def _handleDefeatSwitchMode(bot, screen, originX: int, originY: int, items, retryHit, preferChallenge: bool) -> bool:
    """Quay về sảnh khi thua đủ mốc và đổi nhánh ưu tiên giữa Huyền Linh và Thường."""
    newPrefer = not preferChallenge
    modeName = "Thách Đấu Huyền Linh SV" if newPrefer else "Chiến Đấu Thường"
    bot._log(f"🔄 Thất bại liên tiếp đạt mốc! Quay về sảnh và đổi mode ưu tiên sang: {modeName}")

    backHit = _findKey(bot, items, "back")
    if backHit:
        bot._log("🖱 Click nút 'Back' (OCR)...")
        bot.ctrl.click(backHit[0], backHit[1])
    else:
        tplBack = bot.matcher.find(screen, "btn_afk_back_from_defeat")
        if tplBack:
            bot._log("🖱 Click nút 'Back' (fallback)...")
            bot.ctrl.click(tplBack[0] + originX, tplBack[1] + originY)
        else:
            winWidth = screen.shape[1]
            backX = max(originX + 10, retryHit[0] + int(winWidth * config.DEFEAT_BACK_OFFSET_X_RATIO))
            backY = retryHit[1]
            bot._log(f"🖱 Click tọa độ nút Back tương đối ({backX}, {backY})...")
            bot.ctrl.click(backX, backY)

    time.sleep(2.5)
    return newPrefer


def _handlePickTeamInStats(bot, failedAttempts: int):
    """Mở bảng Thành Tích, bật lọc đội hình đã sở hữu và sao chép đội hình phù hợp."""
    prepScreen, _, _, _, prepItems = _scanGame(bot)
    statsHit = _findKey(bot, prepItems, "stats")
    if not statsHit:
        bot._log("⚠️ Không tìm thấy nút 'Thành tích' ở màn hình chuẩn bị đấu.")
        return

    bot._log("🖱 Click 'Thành tích'...")
    bot.ctrl.click(statsHit[0], statsHit[1])
    time.sleep(2.0)

    statsScreen, ox, oy, _, statsItems = _scanGame(bot)

    # Kiểm tra checkbox "Chỉ hiển thị đội hình đã sở hữu" dựa trên neo chữ + màu HSV
    ownedHit = _findKey(bot, statsItems, "owned_team")
    if ownedHit:
        isChecked, cbX, cbY = inspectCheckboxByText(statsScreen, ownedHit[3], ox, oy)
        if not isChecked:
            bot._log("🖱 Tích chọn ô 'Chỉ hiển thị đội hình đã sở hữu'...")
            bot.ctrl.click(cbX, cbY)
            time.sleep(1.0)
            statsScreen, ox, oy, _, statsItems = _scanGame(bot)

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
                if bot._stop_event.is_set():
                    return
                bot.ctrl.click(nextArrow[0], nextArrow[1])
                if bot._stop_event.wait(0.8):
                    return
            statsScreen, ox, oy, _, statsItems = _scanGame(bot)
        else:
            bot._log("⚠️ Không tìm thấy nút chuyển Team, nhấn ESC.")
            bot.ctrl.press_escape()
            time.sleep(1.0)
            return

    copyHit = _findKey(bot, statsItems, "copy_team")
    if copyHit:
        bot._log("🖱 Click 'Sao chép' đội hình...")
        bot.ctrl.click(copyHit[0], copyHit[1])
        time.sleep(2.0)
    else:
        bot._log("⚠️ Không tìm thấy nút 'Sao chép', nhấn ESC.")
        bot.ctrl.press_escape()
        time.sleep(1.0)


def _tryClickStageOption(bot, items, preferChallenge: bool) -> bool:
    """Thử vào trận ở sảnh AFK theo thứ tự ưu tiên."""
    order = (
        [
            ("challenge_hl", "Thách Đấu Huyền Linh SV", None),
            ("fight", "Chiến Đấu thường", ["auto_battle", "auto_battle_complete", "challenge_hl"]),
        ]
        if preferChallenge
        else [
            ("fight", "Chiến Đấu thường", ["auto_battle", "auto_battle_complete", "challenge_hl"]),
            ("challenge_hl", "Thách Đấu Huyền Linh SV", None),
        ]
    )

    for keyName, label, excludeKeys in order:
        hit = _findKey(bot, items, keyName, excludeKeys=excludeKeys)
        if hit:
            bot._log(f"🖱 Click '{label}' tại ({hit[0]}, {hit[1]})...")
            bot.ctrl.click(hit[0], hit[1])
            time.sleep(2.5)
            return True
    return False


def run_auto_afk(bot):
    """
    Thực hiện nhiệm vụ Auto AFK bằng OCR + Neo tọa độ (không cần chụp template).
    Tích hợp tự động chuyển đổi Đội hình (Team) trong Thành tích khi gặp thất bại liên tiếp.
    """
    bot._log("🚀 Bắt đầu vòng lặp Auto AFK bằng OCR...")

    lastActionTime = time.time()
    failedAttempts = 0
    preferChallenge = True

    while not bot._stop_event.is_set():
        if time.time() - lastActionTime > NO_ACTION_LIMIT_SECONDS:
            bot._log("⚠️ Không phát hiện hành động khả thi nào. Dừng Auto AFK để đảm bảo an toàn!")
            return False

        screen, originX, originY, _, items = _scanGame(bot)

        # 1. Phát hiện màn hình bại trận ("Thử Lại")
        retryHit = _findKey(bot, items, "retry")
        if retryHit:
            failedAttempts += 1
            bot._log(f"❌ Trận đấu THẤT BẠI (Lần thứ {failedAttempts} liên tiếp)!")

            if failedAttempts % FAIL_THRESHOLD_TO_SWITCH_MODE == 0:
                preferChallenge = _handleDefeatSwitchMode(
                    bot, screen, originX, originY, items, retryHit, preferChallenge
                )
                failedAttempts = 0
                lastActionTime = time.time()
                continue

            bot._log("🖱 Click 'Thử Lại'...")
            bot.ctrl.click(retryHit[0], retryHit[1])
            lastActionTime = time.time()
            time.sleep(2.5)
            _handlePickTeamInStats(bot, failedAttempts)
            continue

        # 2. Phát hiện màn hình "Chiến Đấu Tự Động Hoàn Tất"
        finishHit = _findKey(bot, items, "auto_battle_complete")
        if finishHit:
            bot._log("🎉 Phát hiện 'Chiến Đấu Tự Động Hoàn Tất'. Click đóng...")
            bot.ctrl.click(finishHit[0], finishHit[1])
            failedAttempts = 0
            preferChallenge = True
            lastActionTime = time.time()
            time.sleep(2.5)
            continue

        # 3. Phát hiện nút "Chiến Đấu Tự Động" ở màn hình chuẩn bị đấu
        autoHit = _findKey(bot, items, "auto_battle", excludeKeys=["auto_battle_complete"])
        if autoHit:
            bot._log("🖱 Click 'Chiến Đấu Tự Động'...")
            bot.ctrl.click(autoHit[0], autoHit[1])
            lastActionTime = time.time()
            time.sleep(3.0)
            continue

        # 4. Phát hiện sảnh AFK theo mode ưu tiên
        if _tryClickStageOption(bot, items, preferChallenge):
            lastActionTime = time.time()
            continue

        # 5. Phát hiện màn hình chiến thắng ("Đã Tăng Phần Thưởng AFK") - kiểm tra TRƯỚC icon AFK
        victoryHit = _findKey(bot, items, "victory")
        if victoryHit:
            bot._log("🎉 Phát hiện màn hình CHIẾN THẮNG! Click tiếp tục...")
            h, w = screen.shape[:2]
            bot.ctrl.click(originX + int(w * 0.5), originY + int(h * 0.5))
            failedAttempts = 0
            preferChallenge = True
            lastActionTime = time.time()
            time.sleep(3.0)
            continue

        # 6. Phát hiện biểu tượng "AFK" ở sảnh chính
        afkHit = _findKey(bot, items, "afk_icon", excludeKeys=["victory", "auto_battle_complete"], exactOnly=True)
        if afkHit:
            bot._log("🖱 Tìm thấy sảnh chính. Click biểu tượng 'AFK'...")
            bot.ctrl.click(afkHit[0], afkHit[1])
            lastActionTime = time.time()
            time.sleep(2.0)
            continue

        bot._log("⏳ Đang theo dõi trận đấu hoặc trạng thái game...")
        time.sleep(1.5)

    bot._log("✅ Dừng nhiệm vụ Auto AFK.")
    return True
