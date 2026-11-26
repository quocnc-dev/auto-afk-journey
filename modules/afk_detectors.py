"""
Bộ nhận diện trạng thái màn hình chính cho Auto AFK:
- Nút 'Tự Động Xử Lý' (đang chạy ngầm hay đã 'Xong!')
- Nút vào sảnh AFK ('AFK' hoặc 'Màn Chơi Đỉnh Cao')
"""

import re

import config


def _hasDoneWord(item) -> bool:
    """Kiểm tra có từ 'xong' độc lập (tránh khớp nhầm 'không', 'trong'...)."""
    cleaned = re.sub(r"[^a-z\s]", " ", item.normText)
    return config.AUTO_PROGRESS_DONE_WORD in cleaned.split()


def roiToScreenRect(
    rect: tuple[int, int, int, int] | None,
    roiRatio: tuple[float, float, float, float],
) -> tuple[int, int, int, int] | None:
    """Chuyển ROI tỷ lệ (0..1) sang tọa độ màn hình (x, y, w, h)."""
    if rect is None:
        return None
    ox, oy, w, h = rect
    return (
        ox + int(w * roiRatio[0]),
        oy + int(h * roiRatio[1]),
        int(w * (roiRatio[2] - roiRatio[0])),
        int(h * (roiRatio[3] - roiRatio[1])),
    )


def findAutoProgressState(bot, items, findKeyFn) -> tuple[bool, int, int] | None:
    """
    Nhận diện nút 'Tự Động Xử Lý' ở màn hình chính.
    Trả về (isDone, clickX, clickY) hoặc None nếu không ở trạng thái tự động xử lý.
    """
    progressHit = findKeyFn(bot, items, "auto_progress")
    if not progressHit:
        tuDongHit = findKeyFn(bot, items, "auto_battle", excludeKeys=["auto_battle_complete"])
        xuLyHit = findKeyFn(bot, items, "auto_progress_part", wholePhrase=True)
        if tuDongHit and xuLyHit:
            ti, xi = tuDongHit[3], xuLyHit[3]
            maxDx = max(ti.width, xi.width, ti.height * config.AUTO_PROGRESS_MAX_DX_HEIGHT_MULT)
            maxDy = ti.height * config.AUTO_PROGRESS_SPLIT_DY_MULT
            if abs(ti.centerX - xi.centerX) <= maxDx and abs(ti.centerY - xi.centerY) <= maxDy:
                progressHit = tuDongHit

    if not progressHit:
        return None

    pItem = progressHit[3]
    if _hasDoneWord(pItem):
        return (True, pItem.centerX, pItem.centerY)

    maxDx = max(pItem.width, pItem.height * config.AUTO_PROGRESS_MAX_DX_HEIGHT_MULT)
    maxDy = pItem.height * config.AUTO_PROGRESS_MAX_DY_HEIGHT_MULT
    for other in items:
        if _hasDoneWord(other):
            if abs(other.centerX - pItem.centerX) <= maxDx and abs(other.centerY - pItem.centerY) <= maxDy:
                return (True, other.centerX, other.centerY)

    return (False, pItem.centerX, pItem.centerY)


def findInBattleAuto(bot, items, findKeyFn):
    """Nhận diện thanh trạng thái 'Tự Động Chiến Đấu...' khi đang đánh trận để bot đứng đợi."""
    return findKeyFn(bot, items, "in_battle_auto")


def detectPassiveWaitState(bot, items, findKeyFn, autoProgress=None) -> tuple[str, str, bool] | None:
    """
    Trả về (stateKey, logMessage, keepAlive) nếu bot cần đứng yên chờ
    ('Tự Động Xử Lý' đang chạy ở sảnh hoặc 'Tự Động Chiến Đấu...' đang đánh trận).
    """
    if autoProgress is not None and not autoProgress[0]:
        return ("auto_progress_running", "⏳ Đang 'Tự Động Xử Lý' ở màn hình chính — đứng im chờ tới khi thua/xong...", True)
    if findInBattleAuto(bot, items, findKeyFn):
        return ("in_battle_auto", "⏳ Đang 'Tự Động Chiến Đấu...' — đứng đợi kết thúc trận...", False)
    return None


def findMainLobbyEntry(bot, screen, originX: int, originY: int, rect, items, findKeyFn):
    """Tìm nút vào AFK ở sảnh chính ('AFK' hoặc 'Màn Chơi Đỉnh Cao' ở góc dưới)."""
    exclude = ["victory", "auto_battle_complete"]
    afkHit = findKeyFn(bot, items, "afk_icon", excludeKeys=exclude, exactOnly=True)
    if afkHit:
        return afkHit

    peakExcludeWords = [w for k in exclude for w in config.OCR_KEYWORDS.get(k, [])]
    cornerRois = (config.ROI_AFK_CORNER_LEFT, config.ROI_AFK_CORNER)
    for roi in cornerRois:
        screenRect = roiToScreenRect(rect, roi)
        peakHit = bot.ocr.findText(
            items,
            config.OCR_KEYWORDS["peak_stage_icon"],
            excludeKeywords=peakExcludeWords,
            roiScreenRect=screenRect,
            wholePhrase=True,
        )
        if peakHit:
            return peakHit

    for roi in cornerRois:
        cornerItems = bot.ocr.scanImage(screen, originX=originX, originY=originY, roi=roi)
        afkHit = findKeyFn(bot, cornerItems, "afk_icon", excludeKeys=exclude, exactOnly=True)
        if afkHit:
            return afkHit
        peakHit = findKeyFn(bot, cornerItems, "peak_stage_icon", excludeKeys=exclude, wholePhrase=True)
        if peakHit:
            return peakHit

    return None
