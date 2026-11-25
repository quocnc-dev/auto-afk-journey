"""Unit tests kiểm chứng 6 lỗi P1/P2 mới nhất (cửa sổ, Stop 50ms, SendInput, timeout kết quả, ImageGrab, Huyền Linh)."""

import os
import sys
import threading
import types
import unittest

import cv2
import numpy as np

import bot_engine
import config
import controller
import vision
import window_manager
from modules import auto_afk
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot


def _item(raw: str, cx: int = 200, cy: int = 200) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - 40, cy - 12, cx + 40, cy + 12)


class TestP1P2Fixes(unittest.TestCase):
    """Kiểm thử các ca hồi quy cho 2 lỗi P1 và 4 lỗi P2."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()
        cls.tplDir = config.TEMPLATES_DIR

    def test_exact_window_title_rejects_browser_and_occluded_window(self):
        self.assertFalse(window_manager.isExactGameTitle("AFK Journey guide - Mozilla Firefox", "AFK Journey"))
        self.assertTrue(window_manager.isExactGameTitle("AFK Journey", "AFK Journey"))
        self.assertTrue(window_manager.isExactGameTitle("AFKJourney", "AFK Journey"))

        # BotEngine phải từ chối chụp và từ chối click nếu mất focus hoặc điểm click nằm ngoài cửa sổ mới
        eng = bot_engine.BotEngine()
        origFind = bot_engine.findGameWindow
        origFg = bot_engine.isWindowForeground
        origRect = bot_engine.getClientRectScreen
        try:
            bot_engine.findGameWindow = lambda _: 1234
            bot_engine.isWindowForeground = lambda _: False
            bot_engine.getClientRectScreen = lambda _: (100, 100, 800, 600)
            img, _, _, rect = eng.captureGameScreen()
            self.assertIsNone(img)
            self.assertIsNone(rect)
            self.assertFalse(eng.canInteractAt(200, 200))

            # Khi đang foreground nhưng cửa sổ đã dịch chuyển khỏi tọa độ click cũ
            bot_engine.isWindowForeground = lambda _: True
            bot_engine.getClientRectScreen = lambda _: (900, 500, 400, 300)
            self.assertFalse(eng.canInteractAt(200, 200))
            self.assertTrue(eng.canInteractAt(1000, 600))
        finally:
            bot_engine.findGameWindow = origFind
            bot_engine.isWindowForeground = origFg
            bot_engine.getClientRectScreen = origRect

    def test_controller_stop_during_50ms_wait_and_sendinput_fail(self):
        ctrl = controller.Controller(delay_after_click=0.01)
        clicked = []
        origBackend = controller._inputBackend
        origMove = controller._moveCursor
        origSleepWait = controller._sleepWithStop

        controller._inputBackend = types.SimpleNamespace(
            click=lambda button="left": clicked.append(button),
            doubleClick=lambda: clicked.append("double"),
        )
        try:
            # 1. Đặt Stop ngay trong khoảng chờ 50ms sau khi di chuột -> click không được phép chạy
            stopEv = threading.Event()
            controller._moveCursor = lambda x, y: True

            def fakeSleep(sec, ev=None):
                if ev is not None:
                    ev.set()
                return False

            controller._sleepWithStop = fakeSleep
            res = ctrl.click(100, 200, stop_event=stopEv)
            self.assertFalse(res)
            self.assertEqual(clicked, [])

            # 2. _moveCursor thất bại (ví dụ SendInput trả về 0) -> không gọi click
            controller._sleepWithStop = lambda sec, ev=None: True
            controller._moveCursor = lambda x, y: False
            res2 = ctrl.click(100, 200)
            self.assertFalse(res2)
            self.assertEqual(clicked, [])
        finally:
            controller._inputBackend = origBackend
            controller._moveCursor = origMove
            controller._sleepWithStop = origSleepWait

    @unittest.skipUnless(sys.platform == "win32", "Kiểm tra SendInput trả 0 chỉ áp dụng trên Windows")
    def test_win32_sendinput_zero_returns_false(self):
        origSend = controller._inputBackend.SendInput
        try:
            controller._inputBackend.SendInput = lambda *a, **kw: 0
            self.assertFalse(controller._moveCursor(100, 100))
        finally:
            controller._inputBackend.SendInput = origSend

    def test_stuck_victory_and_auto_complete_trigger_timeout(self):
        for fname in ["txt_victory.png", "txt_auto_battle_complete.png"]:
            fpath = os.path.join(self.tplDir, fname)
            if not os.path.exists(fpath):
                self.skipTest(f"Thiếu {fname}")
            canvas = np.full((720, 1280, 3), 40, dtype=np.uint8)
            im = cv2.imread(fpath)
            h, w = im.shape[:2]
            canvas[300:300 + h, 400:400 + w] = im

            bot = MockBot(self.ocr, [canvas] * 10)
            fakeNow = [0.0]

            def advance():
                fakeNow[0] += 500.0
                return fakeNow[0]

            origTime, origWait = auto_afk.time.time, auto_afk._wait
            auto_afk.time.time = advance
            auto_afk._wait = lambda b, s: True
            try:
                ok = auto_afk.run_auto_afk(bot)
            finally:
                auto_afk.time.time, auto_afk._wait = origTime, origWait

            self.assertFalse(ok, f"{fname} lặp quá 35 phút phải timeout trả False")

    def test_pillow_fallback_uses_all_screens_true(self):
        cap = vision.ScreenCapture()
        grabCalls = []
        fakeImage = np.zeros((200, 300, 3), dtype=np.uint8)

        class _FakeGrabMod:
            @staticmethod
            def grab(bbox=None, all_screens=False):
                grabCalls.append((bbox, all_screens))
                return fakeImage

        origGrab = cap.sct.grab
        from PIL import ImageGrab
        origPilGrab = ImageGrab.grab
        cap.sct.grab = lambda _: (_ for _ in ()).throw(RuntimeError("mss failed"))
        ImageGrab.grab = _FakeGrabMod.grab
        try:
            img = cap.capture_region(-1920, 100, 300, 200)
            self.assertEqual(img.shape, (200, 300, 3))
            self.assertEqual(grabCalls[-1], ((-1920, 100, -1620, 300), True))
        finally:
            cap.sct.grab = origGrab
            ImageGrab.grab = origPilGrab

    def test_daily_challenge_does_not_match_huyen_linh(self):
        items = [_item("Thách Đấu Hằng Ngày")]
        hit = self.ocr.findText(items, config.OCR_KEYWORDS["challenge_hl"])
        self.assertIsNone(hit)


if __name__ == "__main__":
    unittest.main()
