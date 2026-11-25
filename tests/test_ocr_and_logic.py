"""Unit tests cho OCR engine, luồng state machine, nhận diện checkbox/arrow và import đa nền tảng."""

import os
import threading
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


class _MockCtrl:
    """Bộ điều khiển giả lập để ghi lại tọa độ click và phím nhấn trong test."""

    def __init__(self):
        self.clicks = []
        self.escapes = 0

    def click(self, x, y, button="left", delay=None):
        self.clicks.append((x, y))

    def press_escape(self):
        self.escapes += 1


class _MockMatcher:
    def find(self, screen, name, threshold=None):
        return None


class _MockBot:
    """Bot giả lập phát lại chuỗi ảnh màn hình theo từng bước của vòng lặp Auto AFK."""

    def __init__(self, ocr: OcrEngine, frames: list[np.ndarray]):
        self.ocr = ocr
        self.matcher = _MockMatcher()
        self.ctrl = _MockCtrl()
        self._frames = frames
        self._index = 0
        self._stop_event = threading.Event()
        self.logs = []

    def _log(self, msg: str):
        self.logs.append(msg)

    def captureGameScreen(self):
        if self._index >= len(self._frames):
            self._stop_event.set()
            img = np.zeros((720, 1280, 3), dtype=np.uint8)
        else:
            img = self._frames[self._index]
            self._index += 1
        return img, 0, 0, (0, 0, img.shape[1], img.shape[0])


class TestOcrAndLogic(unittest.TestCase):
    """Kiểm thử khả năng nhận diện chữ, checkbox, mũi tên và luồng Auto AFK."""

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

    def test_full_1080p_scene_ocr(self):
        if not os.path.isdir(self.tplDir):
            self.skipTest("Thư mục templates chưa tồn tại")

        bg = np.full((1080, 1920, 3), 45, dtype=np.uint8)
        placements = [
            ("btn_retry.png", 1100, 920),
            ("btn_afk_stats.png", 150, 920),
            ("btn_afk_copy_team.png", 820, 820),
            ("btn_afk_auto_battle.png", 1600, 920),
            ("btn_afk_challenge_hl.png", 1600, 750),
            ("btn_afk_fight.png", 1600, 620),
            ("txt_victory.png", 830, 180),
            ("txt_auto_battle_complete.png", 760, 280),
            ("icon_afk.png", 1750, 940),
            ("cb_owned_team_unchecked.png", 420, 830),
        ]
        for fname, x, y in placements:
            fpath = os.path.join(self.tplDir, fname)
            if not os.path.exists(fpath):
                self.skipTest(f"Thiếu {fname}")
            im = cv2.imread(fpath)
            h, w = im.shape[:2]
            bg[y:y + h, x:x + w] = im

        items = self.ocr.scanImage(bg)
        checks = [
            ("retry", None, False),
            ("stats", None, False),
            ("copy_team", None, False),
            ("auto_battle", ["auto_battle_complete"], False),
            ("challenge_hl", None, False),
            ("fight", ["auto_battle", "auto_battle_complete", "challenge_hl"], False),
            ("victory", None, False),
            ("auto_battle_complete", None, False),
            ("afk_icon", ["victory", "auto_battle_complete"], True),
            ("owned_team", None, False),
        ]
        for key, exKeys, exact in checks:
            exWords = []
            if exKeys:
                for ek in exKeys:
                    exWords.extend(config.OCR_KEYWORDS[ek])
            hit = self.ocr.findText(
                items, config.OCR_KEYWORDS[key], excludeKeywords=exWords or None, exactOnly=exact
            )
            self.assertIsNotNone(hit, f"Không khớp '{key}' trên khung 1920x1080")

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

    def test_auto_afk_state_flow_mock(self):
        needed = ["icon_afk.png", "btn_afk_challenge_hl.png", "btn_afk_auto_battle.png", "txt_victory.png"]
        frames = []
        for fname in needed:
            fpath = os.path.join(self.tplDir, fname)
            if not os.path.exists(fpath):
                self.skipTest(f"Thiếu {fname} để test luồng")
            canvas = np.full((720, 1280, 3), 40, dtype=np.uint8)
            im = cv2.imread(fpath)
            h, w = im.shape[:2]
            canvas[300:300 + h, 500:500 + w] = im
            frames.append(canvas)

        bot = _MockBot(self.ocr, frames)
        origSleep = auto_afk.time.sleep
        auto_afk.time.sleep = lambda _: None
        try:
            ok = auto_afk.run_auto_afk(bot)
        finally:
            auto_afk.time.sleep = origSleep

        self.assertTrue(ok)
        # Phải click đủ 4 bước: icon AFK -> Huyền Linh -> Chiến Đấu Tự Động -> đóng màn thắng
        self.assertEqual(len(bot.ctrl.clicks), 4)
        self.assertEqual(bot.ctrl.clicks[-1], (640, 360))


if __name__ == "__main__":
    unittest.main()
