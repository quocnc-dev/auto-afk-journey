"""Unit tests cho OCR engine, nhận diện checkbox/arrow và import đa nền tảng."""

import os
import unittest

import cv2
import numpy as np

import config
import window_manager
import vision
import controller
import bot_engine
from modules import auto_afk
from ocr_engine import OcrEngine, inspectCheckboxByText, findNextTeamArrow, normalizeText


class TestOcrAndLogic(unittest.TestCase):
    """Kiểm thử khả năng nhận diện chữ, checkbox và mũi tên chuyển team."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()
        cls.tplDir = config.TEMPLATES_DIR

    def test_normalize_vietnamese(self):
        self.assertEqual(normalizeText("  Chiến   Đấu Tự Động "), "chien dau tu dong")
        self.assertEqual(normalizeText("Đã Tăng Phần Thưởng AFK"), "da tang phan thuong afk")

    def test_imports_and_modules(self):
        self.assertTrue(hasattr(window_manager, "findGameWindow"))
        self.assertTrue(hasattr(vision, "ScreenCapture"))
        self.assertTrue(hasattr(controller, "Controller"))
        self.assertTrue(hasattr(bot_engine, "BotEngine"))
        self.assertTrue(hasattr(auto_afk, "run_auto_afk"))

    def test_templates_ocr_if_available(self):
        if not os.path.isdir(self.tplDir):
            self.skipTest("Thư mục templates chưa tồn tại")

        cases = [
            ("btn_retry.png", "retry", None, False),
            ("btn_afk_stats.png", "stats", None, False),
            ("btn_afk_copy_team.png", "copy_team", None, False),
            ("btn_afk_auto_battle.png", "auto_battle", ["auto_battle_complete"], False),
            ("btn_afk_challenge_hl.png", "challenge_hl", None, False),
            ("btn_afk_fight.png", "fight", ["auto_battle", "auto_battle_complete", "challenge_hl"], False),
            ("txt_victory.png", "victory", None, False),
            ("txt_auto_battle_complete.png", "auto_battle_complete", None, False),
            ("icon_afk.png", "afk_icon", ["victory", "auto_battle_complete"], True),
        ]

        for fname, key, exKeys, exact in cases:
            fpath = os.path.join(self.tplDir, fname)
            if not os.path.exists(fpath):
                continue
            img = cv2.imread(fpath)
            items = self.ocr.scanImage(img, originX=100, originY=200)
            exWords = []
            if exKeys:
                for ek in exKeys:
                    exWords.extend(config.OCR_KEYWORDS[ek])
            hit = self.ocr.findText(
                items, config.OCR_KEYWORDS[key], excludeKeywords=exWords or None, exactOnly=exact
            )
            self.assertIsNotNone(hit, f"Không khớp OCR cho {fname} -> key={key}")

    def test_checkbox_detection(self):
        checkedPath = os.path.join(self.tplDir, "cb_owned_team_checked.png")
        uncheckedPath = os.path.join(self.tplDir, "cb_owned_team_unchecked.png")
        if not (os.path.exists(checkedPath) and os.path.exists(uncheckedPath)):
            self.skipTest("Thiếu ảnh mẫu checkbox để test")

        for path, expected in [(checkedPath, True), (uncheckedPath, False)]:
            img = cv2.imread(path)
            items = self.ocr.scanImage(img, originX=50, originY=80)
            hit = self.ocr.findText(items, config.OCR_KEYWORDS["owned_team"])
            self.assertIsNotNone(hit)
            isChecked, _, _ = inspectCheckboxByText(img, hit[3], originX=50, originY=80)
            self.assertEqual(isChecked, expected)

    def test_next_team_arrow_detection(self):
        nextPath = os.path.join(self.tplDir, "btn_afk_next_team.png")
        if not os.path.exists(nextPath):
            self.skipTest("Thiếu ảnh mẫu btn_afk_next_team.png")

        modal = np.full((720, 1280, 3), 35, dtype=np.uint8)
        nextTpl = cv2.imread(nextPath)
        nh, nw = nextTpl.shape[:2]
        modal[320:320 + nh, 1050:1050 + nw] = nextTpl
        arrowPos = findNextTeamArrow(modal, originX=10, originY=20)
        self.assertIsNotNone(arrowPos)
        self.assertTrue(1060 <= arrowPos[0] <= 1060 + nw)
        self.assertTrue(340 <= arrowPos[1] <= 340 + nh)


if __name__ == "__main__":
    unittest.main()
