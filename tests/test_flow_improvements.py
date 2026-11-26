"""Unit tests: chờ màn hình đổi sau click, đếm thua chỉ khi thật sự thua, ROI cho từ khóa chung, giới hạn OCR sâu, mss theo thread."""

import os
import shutil
import tempfile
import threading
import unittest

import cv2
import numpy as np

import config
import vision
from modules import auto_afk
from modules.afk_detectors import findMainLobbyEntry, findPauseAutoConfirmCancel
from modules.debug_snapshot import DebugSnapshotter
from modules.game_actions import frameDiff, waitForScreenChange
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot


def _ocrItem(raw: str, cx: int, cy: int, w: int = 120, h: int = 24) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


def _frame(value: int) -> np.ndarray:
    return np.full((200, 300, 3), value, dtype=np.uint8)


class _PeekBot:
    def __init__(self, frames):
        self._frames = list(frames)
        self._stop_event = threading.Event()
        self.logs = []
        self.peeks = 0

    def _log(self, msg):
        self.logs.append(msg)

    def peekScreen(self):
        self.peeks += 1
        return self._frames.pop(0) if self._frames else self._last

    @property
    def _last(self):
        return _frame(200)


class TestScreenSettle(unittest.TestCase):

    def setUp(self):
        self.waits = []
        self.waitFn = lambda b, s: (self.waits.append(s) or not b._stop_event.is_set())

    def test_frame_diff(self):
        self.assertLess(frameDiff(_frame(10), _frame(10)), 0.5)
        self.assertGreater(frameDiff(_frame(10), _frame(200)), 100)
        self.assertEqual(frameDiff(None, _frame(10)), 255.0)

    def test_returns_early_once_changed_and_stable(self):
        bot = _PeekBot([_frame(10), _frame(200), _frame(200)])
        self.assertTrue(waitForScreenChange(bot, _frame(10), 30.0, self.waitFn))
        self.assertEqual(bot.peeks, 3)
        self.assertFalse(any("không đổi" in m for m in bot.logs))

    def test_logs_when_click_has_no_effect(self):
        bot = _PeekBot([])
        bot.peekScreen = lambda: _frame(10)
        orig = config.SCREEN_SETTLE_POLL
        config.SCREEN_SETTLE_POLL = 0.01
        try:
            realWait = lambda b, s: not b._stop_event.wait(s)
            self.assertTrue(waitForScreenChange(bot, _frame(10), 0.45, realWait))
        finally:
            config.SCREEN_SETTLE_POLL = orig
        self.assertTrue(any("không đổi" in m for m in bot.logs))

    def test_fallback_without_peek_waits_fixed_time(self):
        bot = MockBot(OcrEngine(), [])
        self.assertTrue(waitForScreenChange(bot, _frame(10), 2.5, self.waitFn))
        self.assertEqual(self.waits, [2.5])

    def test_stop_interrupts(self):
        bot = _PeekBot([])
        bot._stop_event.set()
        self.assertFalse(waitForScreenChange(bot, _frame(10), 2.5, self.waitFn))


class TestDefeatCountingAndRoi(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def _run(self, scenes, frame=None):
        frame = frame if frame is not None else np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [frame] * len(scenes))
        queue = list(scenes)
        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: queue.pop(0) if queue else []
        auto_afk._wait = lambda b, s: True
        try:
            self.assertTrue(auto_afk.run_auto_afk(bot))
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        return bot

    def test_plain_close_popup_does_not_count_as_defeat(self):
        retryScene = [_ocrItem("Thử Lại", 450, 820)]
        autoBattleScene = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
        popupClose = [_ocrItem("Phần thưởng mới", 338, 400), _ocrItem("Đóng", 340, 780)]
        lobbyBoth = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]
        # 4 lần thua thật + 1 popup Đóng thường -> chưa đủ 5, vẫn ưu tiên Huyền Linh (180, 800)
        bot = self._run(([retryScene, autoBattleScene] * 4) + [popupClose, lobbyBoth])
        self.assertIn((340, 780), bot.ctrl.clicks)
        self.assertEqual(bot.ctrl.clicks[-1], (180, 800))
        self.assertTrue(any("không phải màn thua" in m for m in bot.logs))

    def test_close_with_defeat_text_counts(self):
        retryScene = [_ocrItem("Thử Lại", 450, 820)]
        autoBattleScene = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
        defeatClose = [_ocrItem("Thất Bại", 338, 250), _ocrItem("Đóng", 340, 780)]
        lobbyBoth = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]
        bot = self._run(([retryScene, autoBattleScene] * 4) + [defeatClose, lobbyBoth])
        self.assertEqual(bot.ctrl.clicks[-1], (510, 800))

    def test_generic_button_text_in_top_area_is_ignored(self):
        bot = MockBot(self.ocr, [])
        bot._scanRect = (0, 0, 676, 934)
        topTitle = [_ocrItem("Chiến Đấu", 338, 60)]
        self.assertIsNone(auto_afk._findKey(bot, topTitle, "fight", wholePhrase=True))
        bottomBtn = [_ocrItem("Chiến Đấu", 510, 800)]
        self.assertIsNotNone(auto_afk._findKey(bot, bottomBtn, "fight", wholePhrase=True))
        # Không có rect (chưa quét) thì không giới hạn vùng
        self.assertIsNotNone(auto_afk._findKey(MockBot(self.ocr, []), topTitle, "fight", wholePhrase=True))

    def test_roi_keys_exist_in_keywords(self):
        for key in config.OCR_KEY_ROIS:
            self.assertIn(key, config.OCR_KEYWORDS)


class TestDeepScanThrottle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_find_lobby_entry_skips_rescan_when_not_deep(self):
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [])
        calls = []
        origScan = bot.ocr.scanImage
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: (calls.append(roi) or [])
        try:
            self.assertIsNone(findMainLobbyEntry(bot, frame, 0, 0, (0, 0, 676, 934), [], auto_afk._findKey, deepScan=False))
            self.assertEqual(calls, [])
            findMainLobbyEntry(bot, frame, 0, 0, (0, 0, 676, 934), [], auto_afk._findKey, deepScan=True)
            self.assertGreaterEqual(len(calls), 2)
        finally:
            bot.ocr.scanImage = origScan

    def test_unknown_screens_deep_scan_at_most_once_per_interval(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)  # cùng cỡ khung MockBot trả khi hết frame
        bot = MockBot(self.ocr, [frame] * 5)
        roiCalls = []

        def fakeScan(img, originX=0, originY=0, roi=None):
            if roi is not None or img.shape[:2] != frame.shape[:2]:
                roiCalls.append(roi)
            return []

        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = fakeScan
        auto_afk._wait = lambda b, s: True
        try:
            auto_afk.run_auto_afk(bot)
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        # 5 vòng liên tiếp trong cùng khoảng thời gian ngắn -> chỉ 1 lần quét sâu (2 vùng góc x 2 kiểu)
        self.assertLessEqual(len(roiCalls), 4)
        self.assertGreater(len(roiCalls), 0)


class TestPausePromptRealScreen(unittest.TestCase):
    """Ảnh thật (macOS, cửa sổ 678x936): nền popup màu kem từng bị nhận nhầm là nút X -> click lệch lên trên."""

    FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pause_auto_prompt_678x936.jpg")
    X_CENTER = (383, 613)  # Tâm nút X đo tay trên ảnh (tọa độ trong cửa sổ)

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()
        cls.img = cv2.imread(cls.FIXTURE)

    def test_cancel_x_hits_real_button(self):
        self.assertIsNotNone(self.img, "Thiếu ảnh fixture")
        ox, oy = 1001, 30
        items = self.ocr.scanImage(self.img, originX=ox, originY=oy)
        bot = MockBot(self.ocr, [])
        bot._scanRect = (ox, oy, 678, 936)
        pos = findPauseAutoConfirmCancel(bot, self.img, ox, oy, items, auto_afk._findKey)
        self.assertIsNotNone(pos)
        self.assertLessEqual(abs(pos[0] - (ox + self.X_CENTER[0])), 20, pos)
        self.assertLessEqual(abs(pos[1] - (oy + self.X_CENTER[1])), 20, pos)

    def test_stuck_popup_saves_debug_snapshot(self):
        tmp = tempfile.mkdtemp(prefix="afk_pause_")
        try:
            scene = [_ocrItem("Tắt chế độ Chiến Đấu Tự Động?", 338, 426, w=320, h=26)]
            bot = MockBot(self.ocr, [self.img] * config.PAUSE_PROMPT_STUCK_REPEAT)
            bot.debugSnap = DebugSnapshotter(baseDir=tmp, minInterval=0, enabled=True)
            origScan, origWait = bot.ocr.scanImage, auto_afk._wait
            bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: list(scene)
            auto_afk._wait = lambda b, s: True
            try:
                auto_afk.run_auto_afk(bot)
            finally:
                bot.ocr.scanImage, auto_afk._wait = origScan, origWait
            self.assertEqual(len(bot.ctrl.clicks), config.PAUSE_PROMPT_STUCK_REPEAT)
            self.assertTrue(any("pause_prompt_stuck" in f for f in os.listdir(tmp)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestAutoBattleCompleteRealScreen(unittest.TestCase):
    """Ảnh thật màn 'Chiến Đấu Tự Động Hoàn Tất': từng bị nhận nhầm là popup tắt auto (do chữ 'Tiến Trình')
    và tính vị trí X từ thanh xanh 'Tiến Trình Màn Chơi Đỉnh Cao' ra ngoài cửa sổ -> kẹt mãi."""

    FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "auto_battle_complete_678x936.jpg")

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()
        cls.img = cv2.imread(cls.FIXTURE)

    def test_not_detected_as_pause_popup(self):
        items = self.ocr.scanImage(self.img, originX=1001, originY=30)
        bot = MockBot(self.ocr, [])
        bot._scanRect = (1001, 30, 678, 936)
        self.assertIsNone(findPauseAutoConfirmCancel(bot, self.img, 1001, 30, items, auto_afk._findKey))

    def test_loop_clicks_to_close_complete_screen_inside_window(self):
        bot = MockBot(self.ocr, [self.img])
        origWait = auto_afk._wait
        auto_afk._wait = lambda b, s: True
        try:
            auto_afk.run_auto_afk(bot)
        finally:
            auto_afk._wait = origWait
        self.assertEqual(len(bot.ctrl.clicks), 1)
        x, y = bot.ctrl.clicks[0]
        self.assertTrue(0 <= x < 678 and 0 <= y < 936, bot.ctrl.clicks)
        self.assertFalse(any("Tắt chế độ" in m for m in bot.logs))

    def test_refused_click_does_not_log_no_change(self):
        bot = MockBot(self.ocr, [self.img])
        bot.canInteractAt = lambda x, y, expectedRect=None: False
        bot.peekScreen = lambda: self.img
        origWait = auto_afk._wait
        auto_afk._wait = lambda b, s: True
        try:
            auto_afk.run_auto_afk(bot)
        finally:
            auto_afk._wait = origWait
        self.assertEqual(bot.ctrl.clicks, [])
        self.assertTrue(any("hủy click" in m for m in bot.logs))
        self.assertFalse(any("màn hình không đổi" in m for m in bot.logs))


class TestCapturePerThread(unittest.TestCase):

    def test_each_thread_gets_own_mss(self):
        cap = vision.ScreenCapture()
        mainInst = cap.sct
        self.assertIs(cap.sct, mainInst)
        other = []
        t = threading.Thread(target=lambda: other.append(cap.sct))
        t.start()
        t.join()
        self.assertIsNot(other[0], mainInst)


if __name__ == "__main__":
    unittest.main()
