"""
Regression (build 39, 27/11): thua 5 lần -> bấm 'Back' theo khoảng cách tới chữ 'Thử Lại' rơi vào (1301, 912)
= mép nút 'Thử Lại' -> đánh lại mode cũ thay vì về sảnh. Nút '←' thật ở góc dưới trái, tâm ~(1050, 910).
Fixture: ảnh màn thua thật, cửa sổ ở (1000, 30) kích thước 672x928.
"""

import os
import unittest

import cv2
import numpy as np

from modules import auto_afk
from modules.mode_switch import findDefeatBackButton, handleDefeatSwitchMode
from ocr_engine import OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "defeat_screen_672x928.jpg")
ORIGIN = (1000, 30)
RETRY_BOX = (1422, 893, 1530, 931)   # OCR 'Thử Lại' trên ảnh thật (tọa độ màn hình)
RETRY_Y = (RETRY_BOX[1] + RETRY_BOX[3]) // 2


def _retryHit():
    norm = normalizeText("Thử Lại")
    item = OcrItem("ThieLai", norm, norm.replace(" ", ""), 0.83, *RETRY_BOX)
    return (item.centerX, item.centerY, 0.83, item)


class TestDefeatBackButton(unittest.TestCase):

    def setUp(self):
        self.img = cv2.imread(FIXTURE)
        self.assertIsNotNone(self.img)

    def _assertOnBackButton(self, x, y):
        # Ô nút '←' trên ảnh thật: x 1010..1090, y 878..944 (màn hình); 'Thử Lại' bắt đầu từ x≈1292
        self.assertTrue(1015 <= x <= 1085 and 885 <= y <= 935, (x, y))

    def test_finds_arrow_on_real_defeat_screen(self):
        self._assertOnBackButton(*findDefeatBackButton(self.img, *ORIGIN, RETRY_Y))

    def test_fallback_ratio_still_lands_on_back_button(self):
        dark = np.zeros_like(self.img)  # không dò được nét -> dùng tỉ lệ bề rộng
        self._assertOnBackButton(*findDefeatBackButton(dark, *ORIGIN, RETRY_Y))

    def test_switch_mode_clicks_back_not_retry(self):
        bot = MockBot(None, [])
        rect = (ORIGIN[0], ORIGIN[1], self.img.shape[1], self.img.shape[0])
        origWait, origFind = auto_afk._wait, auto_afk._findKey
        auto_afk._wait = lambda b, s: True
        auto_afk._findKey = lambda b, items, key, **k: None   # OCR không đọc được chữ 'Quay lại'
        try:
            newPrefer = handleDefeatSwitchMode(bot, self.img, *ORIGIN, rect, [], _retryHit(), True)
        finally:
            auto_afk._wait, auto_afk._findKey = origWait, origFind
        self.assertFalse(newPrefer)
        self.assertEqual(len(bot.ctrl.clicks), 1)
        self._assertOnBackButton(*bot.ctrl.clicks[0])


if __name__ == "__main__":
    unittest.main()
