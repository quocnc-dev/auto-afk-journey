"""
Module nhận diện chữ (OCR) và các phần tử neo theo chữ/màu sắc/hình học.
Giúp bot chạy 0 cần người dùng tự chụp template cho các nút có chữ hoặc checkbox.
"""

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

import config

logger = logging.getLogger("AFK_Bot.OCR")


@dataclass
class OcrItem:
    """Một cụm chữ được OCR phát hiện kèm tọa độ màn hình thật."""
    rawText: str
    normText: str
    compactText: str
    score: float
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def centerX(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def centerY(self) -> int:
        return (self.y1 + self.y2) // 2

    @property
    def height(self) -> int:
        return max(1, self.y2 - self.y1)

    @property
    def width(self) -> int:
        return max(1, self.x2 - self.x1)


def normalizeText(text: str) -> str:
    """Chuẩn hóa chuỗi: bỏ dấu tiếng Việt, chuyển chữ thường, gộp khoảng trắng."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


def compactText(text: str) -> str:
    """Chuẩn hóa không dấu và xóa toàn bộ khoảng trắng để bắt chữ dính liền."""
    return normalizeText(text).replace(" ", "")


class OcrEngine:
    """Bộ đọc OCR dùng RapidOCR (ONNX CPU), chỉ quét 1 lần mỗi frame rồi tra cứu nhanh."""

    def __init__(self, fuzzyThreshold: float = None):
        self.fuzzyThreshold = fuzzyThreshold or config.OCR_FUZZY_THRESHOLD
        self._engine = RapidOCR(use_angle_cls=False)

    def scanImage(
        self,
        image: np.ndarray,
        originX: int = 0,
        originY: int = 0,
        roi: tuple[float, float, float, float] | None = None,
    ) -> list[OcrItem]:
        """
        Chạy OCR trên ảnh BGR (hoặc vùng ROI tỷ lệ) và quy đổi tọa độ về màn hình thật.
        """
        if image is None or image.size == 0:
            return []

        imgH, imgW = image.shape[:2]
        cropX, cropY = 0, 0
        target = image

        if roi is not None:
            x1 = max(0, int(imgW * roi[0]))
            y1 = max(0, int(imgH * roi[1]))
            x2 = min(imgW, int(imgW * roi[2]))
            y2 = min(imgH, int(imgH * roi[3]))
            if x2 <= x1 or y2 <= y1:
                return []
            target = image[y1:y2, x1:x2]
            cropX, cropY = x1, y1

        rawResults, _ = self._engine(target, use_det=True, use_cls=False, use_rec=True)
        if not rawResults:
            return []

        items: list[OcrItem] = []
        for box, text, score in rawResults:
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            norm = normalizeText(text)
            if not norm:
                continue
            items.append(
                OcrItem(
                    rawText=text,
                    normText=norm,
                    compactText=norm.replace(" ", ""),
                    score=float(score),
                    x1=int(min(xs)) + cropX + originX,
                    y1=int(min(ys)) + cropY + originY,
                    x2=int(max(xs)) + cropX + originX,
                    y2=int(max(ys)) + cropY + originY,
                )
            )
        return items

    def _matchRatio(self, item: OcrItem, keyword: str) -> float:
        """Tính độ khớp giữa một OcrItem và từ khóa đã chuẩn hóa."""
        kwNorm = normalizeText(keyword)
        kwCompact = kwNorm.replace(" ", "")
        if not kwCompact:
            return 0.0

        if kwNorm in item.normText:
            return 1.0
        if kwCompact in item.compactText:
            return 0.98

        # Khớp mờ trên từng cụm từ có độ dài tương đương từ khóa
        if len(item.compactText) < len(kwCompact) * 0.7:
            return 0.0
        itemWords = item.normText.split()
        kwWords = kwNorm.split()
        best = difflib.SequenceMatcher(None, item.compactText, kwCompact).ratio()
        if len(itemWords) >= len(kwWords) and len(kwWords) > 0:
            winLen = len(kwWords)
            for idx in range(len(itemWords) - winLen + 1):
                candidate = " ".join(itemWords[idx:idx + winLen])
                ratio = difflib.SequenceMatcher(None, candidate, kwNorm).ratio()
                if ratio > best:
                    best = ratio
        return best

    def _hasNearbyExcluded(
        self,
        candidate: OcrItem,
        allItems: list[OcrItem],
        excludeKeywords: list[str],
    ) -> bool:
        """Kiểm tra xem cùng dòng hoặc ngay sát bên dưới có từ khóa loại trừ hay không."""
        if not excludeKeywords:
            return False
        maxYDist = candidate.height * 2.2
        maxXDist = max(candidate.width, candidate.height * 4)
        for other in allItems:
            dx = abs(other.centerX - candidate.centerX)
            dy = abs(other.centerY - candidate.centerY)
            if dx <= maxXDist and dy <= maxYDist:
                for exKw in excludeKeywords:
                    if self._matchRatio(other, exKw) >= self.fuzzyThreshold:
                        return True
        return False

    def findText(
        self,
        items: list[OcrItem],
        keywords: list[str],
        excludeKeywords: list[str] | None = None,
        roiScreenRect: tuple[int, int, int, int] | None = None,
        exactOnly: bool = False,
        wholePhrase: bool = False,
    ) -> tuple[int, int, float, OcrItem] | None:
        """Tìm cụm chữ khớp nhất trong danh sách OcrItem; trả về (cx, cy, score, item) hoặc None."""
        bestMatch = None
        bestScore = 0.0

        for item in items:
            if roiScreenRect is not None:
                rx, ry, rw, rh = roiScreenRect
                if not (rx <= item.centerX <= rx + rw and ry <= item.centerY <= ry + rh):
                    continue
            if excludeKeywords and self._hasNearbyExcluded(item, items, excludeKeywords):
                continue

            for kw in keywords:
                if exactOnly:
                    kwCompact = compactText(kw)
                    if not re.fullmatch(rf"\d*{re.escape(kwCompact)}\d*", item.compactText):
                        continue
                    ratio = 1.0
                elif wholePhrase:
                    cleanedWords = re.sub(r"\b\d+[km]?\b", " ", item.normText)
                    cleaned = " ".join(re.sub(r"[^a-z\s]", " ", cleanedWords).split())
                    kwNorm = normalizeText(kw)
                    if not cleaned or not kwNorm:
                        continue
                    ratio = 1.0 if cleaned == kwNorm else difflib.SequenceMatcher(None, cleaned, kwNorm).ratio()
                else:
                    ratio = self._matchRatio(item, kw)

                if ratio >= self.fuzzyThreshold and ratio > bestScore:
                    bestScore = ratio
                    bestMatch = (item.centerX, item.centerY, ratio, item)

        return bestMatch


def inspectCheckboxByText(image: np.ndarray, item: OcrItem, originX: int = 0, originY: int = 0) -> tuple[bool, int, int]:
    """Xác định ô checkbox bên trái dòng chữ OCR và kiểm tra đã tick chưa bằng HSV."""
    localLeftX = item.x1 - originX
    localCenterY = item.centerY - originY
    textHeight = item.height

    boxLocalX = max(0, localLeftX - int(textHeight * config.CHECKBOX_LEFT_HEIGHT_MULT))
    boxLocalY = max(0, localCenterY)
    halfSize = max(4, int(textHeight * config.CHECKBOX_SAMPLE_HEIGHT_MULT))

    imgH, imgW = image.shape[:2]
    y1 = max(0, boxLocalY - halfSize)
    y2 = min(imgH, boxLocalY + halfSize)
    x1 = max(0, boxLocalX - halfSize)
    x2 = min(imgW, boxLocalX + halfSize)

    isChecked = False
    if y2 > y1 and x2 > x1:
        patch = image[y1:y2, x1:x2]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        low = np.array(config.CHECKBOX_GREEN_HSV_LOW, dtype=np.uint8)
        high = np.array(config.CHECKBOX_GREEN_HSV_HIGH, dtype=np.uint8)
        greenRatio = float(np.mean(cv2.inRange(hsv, low, high) > 0))
        isChecked = greenRatio >= config.CHECKBOX_GREEN_MIN_RATIO

    return (isChecked, boxLocalX + originX, boxLocalY + originY)


def findNextTeamArrow(image: np.ndarray, originX: int = 0, originY: int = 0, roi: tuple[float, float, float, float] | None = None) -> tuple[int, int] | None:
    """Tìm nút mũi tên '>' tròn ở bên phải hộp thoại Thành Tích bằng hình học & màu sắc."""
    if image is None or image.size == 0:
        return None

    roi = roi or config.ROI_NEXT_TEAM_AREA
    imgH, imgW = image.shape[:2]
    rx1 = max(0, int(imgW * roi[0]))
    ry1 = max(0, int(imgH * roi[1]))
    rx2 = min(imgW, int(imgW * roi[2]))
    ry2 = min(imgH, int(imgH * roi[3]))
    if rx2 <= rx1 or ry2 <= ry1:
        return None

    region = image[ry1:ry2, rx1:rx2]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    # Mũi tên '>' màu trắng sáng nằm bên trong vòng tròn xám tím
    whiteMask = ((hsv[:, :, 1] < 45) & (hsv[:, :, 2] > 215)).astype(np.uint8) * 255
    contours, _ = cv2.findContours(whiteMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 20 or area > 1500:
            continue
        bx, by, bw, bh = cv2.boundingRect(contour)
        if bw <= 0 or bh <= 0:
            continue
        aspect = bh / bw
        # Ký tự '>' cao hơn rộng (thường ~1.4 -> 3.0) và nằm trong vòng tròn tối hơn xung quanh
        if 1.3 <= aspect <= 3.2 and 10 <= bh <= max(45, int(imgH * 0.08)):
            cx = bx + bw // 2
            cy = by + bh // 2
            # Kiểm tra nền xung quanh là nút tròn xám/tím (độ bão hòa thấp, không phải nền trắng tinh)
            pad = max(6, bh // 2)
            px1, py1 = max(0, cx - pad), max(0, cy - pad)
            px2, py2 = min(region.shape[1], cx + pad), min(region.shape[0], cy + pad)
            bgPatch = hsv[py1:py2, px1:px2]
            if bgPatch.size == 0:
                continue
            medianVal = float(np.median(bgPatch[:, :, 2]))
            if 70 <= medianVal <= 190:
                return (rx1 + cx + originX, ry1 + cy + originY)

    return None
