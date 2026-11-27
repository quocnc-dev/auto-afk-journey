"""
Bộ nhận diện trạng thái màn hình chính cho Auto AFK:
- Nút 'Tự Động Xử Lý' (đang chạy ngầm hay đã 'Xong!')
- Nút vào sảnh AFK ('AFK' hoặc 'Màn Chơi Đỉnh Cao')
"""

import re

import cv2
import numpy as np

import config
from modules.loop_state import AfkLoopState  # noqa: F401  (giữ import cũ: from modules.afk_detectors import AfkLoopState)


_OCR_DIGIT_FIX = str.maketrans({"l": "1", "i": "1", "|": "1", "o": "0"})


def parseStagesCleared(items) -> int | None:
    """
    Đọc số màn auto đã vượt trên màn 'Chiến Đấu Tự Động Hoàn Tất':
    'Đã hoàn thành màn x1' (OCR hay đọc 1 thành 'l') hoặc 'Tiến Trình ... 846 >> 847'.
    Trả về None nếu không đọc được.
    """
    for item in items:
        m = re.search(r"hoan thanh man\s*x\s*([0-9ilo|]+)", item.normText)
        if m:
            digits = m.group(1).translate(_OCR_DIGIT_FIX)
            if digits.isdigit():
                return int(digits)
    for item in items:
        m = re.search(r"tien trinh.*?(\d+)\s*>+\s*(\d+)", item.normText)
        if m:
            return max(0, int(m.group(2)) - int(m.group(1)))
    return None


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


def hasBattleTimer(items, rect: tuple[int, int, int, int] | None) -> bool:
    """Nhận diện bộ đếm thời gian trận đấu (vd '88giây') ở góc trên phải màn hình."""
    timerRect = roiToScreenRect(rect, config.ROI_BATTLE_TIMER)
    for item in items:
        if timerRect is not None:
            rx, ry, rw, rh = timerRect
            if not (rx <= item.centerX <= rx + rw and ry <= item.centerY <= ry + rh):
                continue
        cleaned = re.sub(r"[^a-z0-9\s]", "", item.normText).strip()
        if re.fullmatch(r"\d{1,3}\s*(giay|s)", cleaned):
            return True
    return False


def findPauseAutoConfirmCancel(bot, screen, originX: int, originY: int, items, findKeyFn) -> tuple[int, int] | None:
    """
    Phát hiện popup 'Tắt chế độ Chiến Đấu Tự Động?' và trả về tọa độ nút X (hủy) để tiếp tục auto.
    Nút X nằm cùng hàng, bên trái nút ✓ xanh lá một khoảng ~1.35 lần bề rộng nút ✓ (đo trên ảnh thật).
    Không dò theo vùng trắng vì nền popup cũng màu kem sáng, sẽ khớp nhầm cả nền.
    """
    hit = findKeyFn(bot, items, "pause_auto_prompt")
    if not hit or findKeyFn(bot, items, "auto_battle_complete"):
        return None  # Màn 'Chiến Đấu Tự Động Hoàn Tất' không phải popup tắt auto
    pItem = hit[3]
    imgH, imgW = screen.shape[:2]
    # 1) OCR thường đọc được luôn chữ 'X' trên nút hủy -> chính xác nhất (giới hạn khoảng cách ngang)
    maxDx = imgW * config.PAUSE_CANCEL_X_MAX_DX_RATIO
    xItems = [it for it in items if it.normText.strip() in ("x", "×")
              and pItem.y2 < it.centerY <= pItem.y2 + imgH * 0.30
              and abs(it.centerX - pItem.centerX) <= maxDx]
    if xItems:
        xi = min(xItems, key=lambda it: abs(it.centerX - pItem.centerX))
        return (xi.centerX, xi.centerY)
    # 2) Không đọc được 'X': định vị theo nút ✓ xanh lá
    if hasattr(cv2, "findContours") and getattr(screen, "ndim", 0) == 3:
        y1 = max(0, pItem.y2 - originY)
        y2 = min(imgH, y1 + int(imgH * 0.30))
        x1, x2 = int(imgW * 0.25), int(imgW * 0.90)
        if y2 > y1 + 10 and x2 > x1 + 10:
            hsv = cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
            button = _findGreenRoundButton(hsv, minRadius=imgW * 0.03)
            if button is not None:
                gcx, gcy, gw = button
                estX = gcx - int(gw * config.PAUSE_CANCEL_OFFSET_MULT)
                cx, cy = _refineCancelGlyph(hsv, estX, gcy, gw, gw) or (estX, gcy)
                return (originX + x1 + cx, originY + y1 + cy)
    return (originX + int(imgW * 0.56), originY + int(imgH * 0.66))


def _findGreenRoundButton(hsv, minRadius: float) -> tuple[int, int, int] | None:
    """
    Tâm và đường kính nút tròn xanh lá lớn nhất = hình tròn lớn nhất nằm gọn trong vùng xanh (distance transform).
    Không dùng khung bao vì vùng xanh của nền (cây, cỏ) dính vào nút làm khung to ra, tâm lệch (ảnh thật 14:42).
    """
    low = np.array(config.CHECKBOX_GREEN_HSV_LOW, dtype=np.uint8)
    high = np.array(config.CHECKBOX_GREEN_HSV_HIGH, dtype=np.uint8)
    contours, _ = cv2.findContours(cv2.inRange(hsv, low, high), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        if cv2.contourArea(c) < 250:
            continue
        filled = np.zeros(hsv.shape[:2], dtype=np.uint8)
        cv2.drawContours(filled, [c], -1, 255, thickness=cv2.FILLED)  # lấp dấu ✓ trắng bên trong nút
        _, radius, _, center = cv2.minMaxLoc(cv2.distanceTransform(filled, cv2.DIST_L2, 5))
        if radius >= minRadius and (best is None or radius > best[2]):
            best = (center[0], center[1], radius)
    return (best[0], best[1], int(round(best[2] * 2))) if best else None


def _refineCancelGlyph(hsv, estX: int, estY: int, gw: int, gh: int) -> tuple[int, int] | None:
    """Tinh chỉnh theo nét chữ 'X' tối màu gần vị trí ước lượng; chỉ nhận vùng đúng cỡ glyph."""
    darkMask = ((hsv[:, :, 2] < 150) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    contours, _ = cv2.findContours(darkMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        if not (0.15 * gw <= bw <= 0.6 * gw and 0.15 * gh <= bh <= 0.6 * gh):
            continue
        ccx, ccy = bx + bw // 2, by + bh // 2
        dist = abs(ccx - estX) + abs(ccy - estY)
        if abs(ccx - estX) <= 0.4 * gw and abs(ccy - estY) <= 0.35 * gh and (best is None or dist < best[0]):
            best = (dist, ccx, ccy)
    return (best[1], best[2]) if best else None


def findInBattleAuto(bot, items, findKeyFn, rect=None):
    """Nhận diện đang trong trận ('Tự Động Chiến Đấu...' hoặc bộ đếm giây góc trên phải)."""
    return bool(findKeyFn(bot, items, "in_battle_auto", extraExcludes=config.IN_BATTLE_EXTRA_EXCLUDES)) or hasBattleTimer(items, rect)


def isMainOverworldScreen(bot, items, findKeyFn) -> bool:
    """Kiểm tra có đang ở màn hình chính (khớp >= 2 nút điều hướng sảnh chính toàn cụm) để không click nhầm."""
    hits = 0
    for kw in config.OCR_KEYWORDS.get("main_world_nav", []):
        if bot.ocr.findText(items, [kw], wholePhrase=True) is not None:
            hits += 1
            if hits >= 2:
                return True
    return False


def _scanCornerUpscaled(bot, screen, originX: int, originY: int, roi: tuple[float, float, float, float], findKeyFn):
    """Phóng to 2x vùng góc dưới khi chữ 'Màn Chơi Đỉnh Cao' quá nhỏ khiến OCR 1x bỏ sót."""
    if screen is None or not hasattr(cv2, "resize") or getattr(screen, "ndim", 0) != 3:
        return None
    imgH, imgW = screen.shape[:2]
    x1, y1 = max(0, int(imgW * roi[0])), max(0, int(imgH * roi[1]))
    x2, y2 = min(imgW, int(imgW * roi[2])), min(imgH, int(imgH * roi[3]))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = screen[y1:y2, x1:x2]
    upscaled = cv2.resize(crop, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    upItems = bot.ocr.scanImage(upscaled, originX=0, originY=0)
    exclude = ["victory", "auto_battle_complete"]
    hit = findKeyFn(bot, upItems, "afk_icon", excludeKeys=exclude, exactOnly=True) or findKeyFn(
        bot, upItems, "peak_stage_icon", excludeKeys=exclude, wholePhrase=True
    )
    if not hit:
        return None
    cx, cy, score, item = hit
    return (originX + x1 + cx // 2, originY + y1 + cy // 2, score, item)


def detectPassiveWaitState(bot, items, findKeyFn, autoProgress=None, rect=None) -> tuple[str, str, bool] | None:
    """
    Trả về (stateKey, logMessage, keepAlive) nếu bot cần đứng yên chờ
    ('Tự Động Xử Lý' đang chạy ở sảnh hoặc đang đánh trận).
    """
    if autoProgress is not None and not autoProgress[0]:
        return ("auto_progress_running", "⏳ Đang 'Tự Động Xử Lý' ở màn hình chính — đứng im chờ tới khi thua/xong...", True)
    if findInBattleAuto(bot, items, findKeyFn, rect=rect):
        return ("in_battle_auto", "⏳ Đang 'Tự Động Chiến Đấu...' — đứng đợi kết thúc trận...", True)
    return None


def findMainLobbyEntry(bot, screen, originX: int, originY: int, rect, items, findKeyFn, deepScan: bool = True):
    """Tìm nút vào AFK ở sảnh chính ('AFK' hoặc 'Màn Chơi Đỉnh Cao' ở góc dưới); deepScan=False bỏ qua OCR lại vùng góc."""
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

    if not deepScan:
        return None
    for roi in cornerRois:
        cornerItems = bot.ocr.scanImage(screen, originX=originX, originY=originY, roi=roi)
        afkHit = findKeyFn(bot, cornerItems, "afk_icon", excludeKeys=exclude, exactOnly=True)
        if afkHit:
            return afkHit
        peakHit = findKeyFn(bot, cornerItems, "peak_stage_icon", excludeKeys=exclude, wholePhrase=True)
        if peakHit:
            return peakHit
        upHit = _scanCornerUpscaled(bot, screen, originX, originY, roi, findKeyFn)
        if upHit:
            return upHit

    return None
