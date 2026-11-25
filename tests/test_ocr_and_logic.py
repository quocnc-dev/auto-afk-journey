"""Unit tests cho OCR engine, 1080p scene, checkbox/arrow và luồng Auto AFK."""

import os
import threading
import unittest

import cv2
import numpy as np

import config
from modules import auto_afk
from modules.afk_detectors import findAutoProgressState, findMainLobbyEntry
from ocr_engine import OcrEngine, OcrItem, findNextTeamArrow, inspectCheckboxByText, normalizeText


class _MockCtrl:
    def __init__(self, onClick=None):
        self.clicks = []
        self.escapes = 0
        self._onClick = onClick

    def click(self, x, y, button="left", delay=None, stop_event=None, guard_fn=None):
        if stop_event is not None and stop_event.is_set():
            return False
        if guard_fn is not None and not guard_fn():
            return False
        self.clicks.append((x, y))
        if self._onClick:
            self._onClick(len(self.clicks))
        return True

    def press_escape(self, stop_event=None, guard_fn=None):
        if stop_event is not None and stop_event.is_set():
            return False
        if guard_fn is not None and not guard_fn():
            return False
        self.escapes += 1
        return True


class _MockMatcher:
    def find(self, screen, name, threshold=None):
        return None


class MockBot:
    """Bot giả lập phát lại chuỗi ảnh màn hình cho unit test."""

    def __init__(self, ocr: OcrEngine, frames: list[np.ndarray | None], onClick=None):
        self.ocr = ocr
        self.matcher = _MockMatcher()
        self.ctrl = _MockCtrl(onClick=onClick)
        self._frames = frames
        self._index = 0
        self._stop_event = threading.Event()
        self.logs = []

    def _log(self, msg: str):
        self.logs.append(msg)

    def captureGameScreen(self):
        if self._index >= len(self._frames):
            self._stop_event.set()
            return np.zeros((720, 1280, 3), dtype=np.uint8), 0, 0, (0, 0, 1280, 720)
        img = self._frames[self._index]
        self._index += 1
        if img is None:
            return None, 0, 0, None
        return img, 0, 0, (0, 0, img.shape[1], img.shape[0])


class TestOcrAndLogic(unittest.TestCase):
    """Kiểm thử nhận diện chữ OCR, checkbox, mũi tên và luồng Auto AFK."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()
        cls.tplDir = config.TEMPLATES_DIR

    def test_normalize_vietnamese(self):
        self.assertEqual(normalizeText("  Chiến   Đấu Tự Động "), "chien dau tu dong")
        self.assertEqual(normalizeText("Đã Tăng Phần Thưởng AFK"), "da tang phan thuong afk")

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
        fightEx = [w for k in config.FIGHT_EXCLUDE_KEYS for w in config.OCR_KEYWORDS[k]] + config.FIGHT_EXTRA_EXCLUDES
        checks = [
            ("retry", None, False, False),
            ("stats", None, False, False),
            ("copy_team", None, False, False),
            ("auto_battle", config.OCR_KEYWORDS["auto_battle_complete"], False, False),
            ("challenge_hl", None, False, False),
            ("fight", fightEx, False, True),
            ("victory", None, False, False),
            ("auto_battle_complete", config.FIGHT_EXTRA_EXCLUDES, False, False),
            ("afk_icon", config.OCR_KEYWORDS["victory"] + config.OCR_KEYWORDS["auto_battle_complete"], True, False),
            ("owned_team", None, False, False),
        ]
        for key, exWords, exact, wholePhrase in checks:
            hit = self.ocr.findText(
                items, config.OCR_KEYWORDS[key], excludeKeywords=exWords, exactOnly=exact, wholePhrase=wholePhrase
            )
            if not hit and key == "afk_icon":
                cornerItems = self.ocr.scanImage(bg, roi=config.ROI_AFK_CORNER)
                hit = self.ocr.findText(
                    cornerItems, config.OCR_KEYWORDS[key], excludeKeywords=exWords, exactOnly=exact
                )
            self.assertIsNotNone(hit, f"Không khớp '{key}' trên khung 1920x1080")

    def test_checkbox_and_next_team_arrow(self):
        checkedPath = os.path.join(self.tplDir, "cb_owned_team_checked.png")
        uncheckedPath = os.path.join(self.tplDir, "cb_owned_team_unchecked.png")
        nextPath = os.path.join(self.tplDir, "btn_afk_next_team.png")
        if not (os.path.exists(checkedPath) and os.path.exists(uncheckedPath) and os.path.exists(nextPath)):
            self.skipTest("Thiếu ảnh mẫu checkbox/next_team")

        for path, expected in [(checkedPath, True), (uncheckedPath, False)]:
            img = cv2.imread(path)
            items = self.ocr.scanImage(img, originX=50, originY=80)
            hit = self.ocr.findText(items, config.OCR_KEYWORDS["owned_team"])
            self.assertIsNotNone(hit)
            isChecked, _, _ = inspectCheckboxByText(img, hit[3], originX=50, originY=80)
            self.assertEqual(isChecked, expected)

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

        bot = MockBot(self.ocr, frames)
        origWait = auto_afk._wait
        auto_afk._wait = lambda b, s: True
        try:
            ok = auto_afk.run_auto_afk(bot)
        finally:
            auto_afk._wait = origWait

        self.assertTrue(ok)
        self.assertEqual(len(bot.ctrl.clicks), 4)
        self.assertEqual(bot.ctrl.clicks[-1], (640, 360))

    def _ocrItem(self, raw: str, cx: int, cy: int, w: int = 100, h: int = 24) -> OcrItem:
        norm = normalizeText(raw)
        return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)

    def test_main_screen_auto_progress_running_stands_still_and_done_reenters(self):
        frame = np.zeros((1013, 775, 3), dtype=np.uint8)
        runningItems = [
            self._ocrItem("Tự Động Xử Lý", 75, 960, w=130, h=22),
            self._ocrItem("Không", 130, 990, w=60, h=24),
            self._ocrItem("Chế Độ", 310, 955, w=70, h=20),
            self._ocrItem("Chiến Đấu", 310, 980, w=90, h=20),
        ]
        doneItems = [
            self._ocrItem("Tự Động Xử Lý", 75, 960, w=130, h=22),
            self._ocrItem("Xong!", 75, 990, w=90, h=28),
            self._ocrItem("Chế Độ", 310, 955, w=70, h=20),
            self._ocrItem("Chiến Đấu", 310, 980, w=90, h=20),
        ]
        splitRunning = [
            self._ocrItem("Tự Động", 70, 950, w=80, h=20),
            self._ocrItem("Xử Lý", 70, 974, w=70, h=20),
        ]

        bot = MockBot(self.ocr, [frame, frame, frame])
        seq = [runningItems, runningItems, doneItems]
        fakeNow = [0.0]
        origScan, origTime, origWait = bot.ocr.scanImage, auto_afk.time.time, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: seq.pop(0) if seq else []
        auto_afk.time.time = lambda: (fakeNow.__setitem__(0, fakeNow[0] + 900.0) or fakeNow[0])
        auto_afk._wait = lambda b, s: True
        try:
            stateSplit = findAutoProgressState(bot, splitRunning, auto_afk._findKey)
            self.assertEqual(stateSplit, (False, 70, 950))
            ok = auto_afk.run_auto_afk(bot)
        finally:
            bot.ocr.scanImage, auto_afk.time.time, auto_afk._wait = origScan, origTime, origWait

        self.assertTrue(ok)
        self.assertEqual(bot.ctrl.clicks, [(75, 990)])

    def test_peak_stage_entry_only_matches_bottom_corners(self):
        frame = np.zeros((1013, 775, 3), dtype=np.uint8)
        rect = (0, 0, 775, 1013)
        bot = MockBot(self.ocr, [frame])
        origScan = bot.ocr.scanImage
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: []
        try:
            topHeader = [self._ocrItem("Màn Chơi Đỉnh Cao", 380, 60, w=180, h=24)]
            self.assertIsNone(findMainLobbyEntry(bot, frame, 0, 0, rect, topHeader, auto_afk._findKey))
            cornerBtn = [self._ocrItem("Màn Chơi Đỉnh Cao", 75, 940, w=130, h=20)]
            hit = findMainLobbyEntry(bot, frame, 0, 0, rect, cornerBtn, auto_afk._findKey)
            self.assertIsNotNone(hit)
            self.assertEqual((hit[0], hit[1]), (75, 940))
        finally:
            bot.ocr.scanImage = origScan


if __name__ == "__main__":
    unittest.main()
