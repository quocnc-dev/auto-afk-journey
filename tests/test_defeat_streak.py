"""Chuỗi thua liên tiếp: thắng (kể cả auto vượt màn rồi mới dừng ở màn 'Hoàn Tất') phải reset; đủ 5 lần thua liên tiếp mới đổi mode."""

import os
import unittest

import cv2
import numpy as np

from modules import auto_afk
from modules.afk_detectors import parseStagesCleared
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "auto_battle_complete_678x936.jpg")


def _ocrItem(raw: str, cx: int, cy: int, w: int = 120, h: int = 24) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


RETRY = [_ocrItem("Thử Lại", 450, 820)]
AUTO_BATTLE = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
LOBBY = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]
HL, NORMAL = (180, 800), (510, 800)


def _complete(*extra):
    return [_ocrItem("Chiến Đấu Tự Động Hoàn Tất", 338, 287, w=440, h=40)] + list(extra)


class TestParseStagesCleared(unittest.TestCase):

    def test_variants(self):
        self.assertEqual(parseStagesCleared([_ocrItem("Đã hoàn thành màn xl", 338, 345)]), 1)  # OCR đọc 1 thành l
        self.assertEqual(parseStagesCleared([_ocrItem("Đã hoàn thành màn x12", 338, 345)]), 12)
        self.assertEqual(parseStagesCleared([_ocrItem("Đã hoàn thành màn x0", 338, 345)]), 0)
        self.assertEqual(parseStagesCleared([_ocrItem("Tiến Trình Màn Chơi Đỉnh Cao 846 >> 848", 338, 470)]), 2)
        self.assertIsNone(parseStagesCleared([_ocrItem("Nhấn để đóng", 338, 900)]))

    def test_real_complete_screen(self):
        items = OcrEngine().scanImage(cv2.imread(FIXTURE))
        self.assertEqual(parseStagesCleared(items), 1)


class TestDefeatStreak(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def _run(self, scenes):
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [frame] * len(scenes))
        queue = list(scenes)
        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: queue.pop(0) if queue else []
        auto_afk._wait = lambda b, s: True
        try:
            auto_afk.run_auto_afk(bot)
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        return bot

    def test_complete_after_winning_a_stage_resets_streak(self):
        # 4 lần thua, rồi auto vượt 1 màn và dừng ở 'Hoàn Tất' -> chuỗi chỉ còn 1 -> vẫn giữ Huyền Linh
        won = _complete(_ocrItem("Đã hoàn thành màn xl", 338, 345))
        bot = self._run(([RETRY, AUTO_BATTLE] * 4) + [won, LOBBY])
        self.assertEqual(bot.ctrl.clicks[-1], HL)
        self.assertTrue(any("reset chuỗi thua" in m for m in bot.logs))
        self.assertTrue(any("thua lần 1/5" in m for m in bot.logs))

    def test_complete_without_progress_counts_as_fifth_defeat(self):
        lost = _complete(_ocrItem("Đã hoàn thành màn x0", 338, 345))
        bot = self._run(([RETRY, AUTO_BATTLE] * 4) + [lost, LOBBY])
        self.assertEqual(bot.ctrl.clicks[-1], NORMAL)

    def test_four_defeats_win_then_four_defeats_does_not_switch(self):
        victory = [_ocrItem("Đã Tăng Phần Thưởng AFK", 338, 250)]
        bot = self._run(([RETRY, AUTO_BATTLE] * 4) + [victory] + ([RETRY, AUTO_BATTLE] * 4) + [LOBBY])
        self.assertEqual(bot.ctrl.clicks[-1], HL)
        self.assertFalse(any("đổi mode" in m or "Chuyển chế độ" in m for m in bot.logs))


if __name__ == "__main__":
    unittest.main()
