"""Unit tests kiểm chứng các lỗi P1/P2 (cửa sổ, foreground, Stop 50ms, SendInput click, timeout kết quả)."""

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
    """Kiểm thử các ca hồi quy cho P1 và P2."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()
        cls.tplDir = config.TEMPLATES_DIR

    def test_exact_window_title_and_rect_shift_guard(self):
        self.assertFalse(window_manager.isExactGameTitle("AFK Journey guide - Mozilla Firefox", "AFK Journey"))
        self.assertTrue(window_manager.isExactGameTitle("AFK Journey", "AFK Journey"))
        self.assertTrue(window_manager.isExactGameTitle("AFKJourney", "AFK Journey"))

        eng = bot_engine.BotEngine()
        origFind, origFg, origRect = (
            bot_engine.findGameWindow,
            bot_engine.isWindowForeground,
            bot_engine.getClientRectScreen,
        )
        try:
            bot_engine.findGameWindow = lambda _: 1234
            bot_engine.isWindowForeground = lambda _: False
            bot_engine.getClientRectScreen = lambda _: (100, 100, 800, 600)
            img, _, _, rect = eng.captureGameScreen()
            self.assertIsNone(img)
            self.assertIsNone(rect)
            self.assertFalse(eng.canInteractAt(200, 200, expectedRect=(100, 100, 800, 600)))

            # Cửa sổ dịch nhẹ từ (100,100,800,600) -> (110,105,800,600): điểm cũ (200,200) vẫn trong rect mới nhưng phải bị từ chối
            bot_engine.isWindowForeground = lambda _: True
            bot_engine.getClientRectScreen = lambda _: (110, 105, 800, 600)
            self.assertFalse(eng.canInteractAt(200, 200, expectedRect=(100, 100, 800, 600)))
            self.assertTrue(eng.canInteractAt(200, 200, expectedRect=(110, 105, 800, 600)))
        finally:
            bot_engine.findGameWindow, bot_engine.isWindowForeground, bot_engine.getClientRectScreen = (
                origFind,
                origFg,
                origRect,
            )

    def test_controller_stop_and_focus_loss_during_50ms_wait(self):
        ctrl = controller.Controller(delay_after_click=0.01)
        clicked = []
        origClick, origMove, origSleep = (
            controller._sendMouseClick,
            controller._moveCursor,
            controller._sleepWithStop,
        )
        controller._sendMouseClick = lambda btn="left": clicked.append(btn) or True
        try:
            # 1. Stop đặt trong khoảng chờ 50ms -> hủy click
            stopEv = threading.Event()
            controller._moveCursor = lambda x, y: True

            def stopInSleep(sec, ev=None):
                if ev is not None:
                    ev.set()
                return False

            controller._sleepWithStop = stopInSleep
            self.assertFalse(ctrl.click(100, 200, stop_event=stopEv))
            self.assertEqual(clicked, [])

            # 2. Game mất focus ngay sau khi di chuột (trong lúc chờ 50ms) -> guard_fn lần 2 chặn click
            fgState = [True]

            def loseFocusInSleep(sec, ev=None):
                fgState[0] = False
                return True

            controller._sleepWithStop = loseFocusInSleep
            self.assertFalse(ctrl.click(100, 200, guard_fn=lambda: fgState[0]))
            self.assertEqual(clicked, [])
        finally:
            controller._sendMouseClick, controller._moveCursor, controller._sleepWithStop = (
                origClick,
                origMove,
                origSleep,
            )

    def test_popup_stop_after_move_and_escape_without_focus(self):
        # 1. Đóng popup trong _state_check_popup bị Stop sau move -> không click
        eng = bot_engine.BotEngine()
        popupClicks = []
        origFind, origFg, origRect, origCap = (
            bot_engine.findGameWindow,
            bot_engine.isWindowForeground,
            bot_engine.getClientRectScreen,
            eng.capture.capture_window,
        )
        origMove, origSendClick, origSleep = (
            controller._moveCursor,
            controller._sendMouseClick,
            controller._sleepWithStop,
        )
        try:
            bot_engine.findGameWindow = lambda _: 1234
            bot_engine.isWindowForeground = lambda _: True
            bot_engine.getClientRectScreen = lambda _: (0, 0, 1280, 720)
            eng.capture.capture_window = lambda rect: (np.zeros((720, 1280, 3), dtype=np.uint8), 0, 0)
            eng.matcher.find_any = lambda screen, names: ("popup_close", 600, 300, 0.99)
            controller._moveCursor = lambda x, y: True
            controller._sendMouseClick = lambda btn="left": popupClicks.append(btn) or True

            def stopDuring50ms(sec, ev=None):
                eng._stop_event.set()
                return False

            controller._sleepWithStop = stopDuring50ms
            eng._state_check_popup()
            self.assertEqual(popupClicks, [])
        finally:
            bot_engine.findGameWindow, bot_engine.isWindowForeground, bot_engine.getClientRectScreen = (
                origFind,
                origFg,
                origRect,
            )
            eng.capture.capture_window = origCap
            controller._moveCursor, controller._sendMouseClick, controller._sleepWithStop = (
                origMove,
                origSendClick,
                origSleep,
            )

        # 2. _safeEscape phải hủy ESC nếu game mất focus trong lúc OCR
        bot = MockBot(self.ocr, [])
        bot.canSendKey = lambda: False
        self.assertFalse(auto_afk._safeEscape(bot))
        self.assertEqual(bot.ctrl.escapes, 0)

    def test_launch_game_prompts_when_foreground_denied(self):
        prompts = []
        eng = bot_engine.BotEngine(prompt_callback=lambda t, m: prompts.append((t, m)))
        origFind, origFocus, origRect, origFg = (
            bot_engine.findGameWindow,
            bot_engine.focusGameWindow,
            bot_engine.getClientRectScreen,
            bot_engine.isWindowForeground,
        )
        try:
            bot_engine.findGameWindow = lambda _: 999
            bot_engine.focusGameWindow = lambda _: False
            bot_engine.getClientRectScreen = lambda _: (0, 0, 1280, 720)
            bot_engine.isWindowForeground = lambda _: False
            eng.state = bot_engine.State.LAUNCH_GAME
            eng._state_launch_game()
            self.assertEqual(eng.state, bot_engine.State.LAUNCH_GAME)
            self.assertEqual(len(prompts), 1)
        finally:
            (
                bot_engine.findGameWindow,
                bot_engine.focusGameWindow,
                bot_engine.getClientRectScreen,
                bot_engine.isWindowForeground,
            ) = (origFind, origFocus, origRect, origFg)

    @unittest.skipUnless(sys.platform == "win32", "Kiểm tra SendInput Windows")
    def test_win32_sendinput_move_ok_click_zero_returns_false(self):
        ctrl = controller.Controller(delay_after_click=0.01)
        origSend = controller._inputBackend.SendInput
        origSleep = controller._sleepWithStop
        calls = [0]

        def sendSideEffect(n, ptr, size):
            calls[0] += 1
            return 1 if calls[0] == 1 else 0

        controller._inputBackend.SendInput = sendSideEffect
        controller._sleepWithStop = lambda sec, ev=None: True
        try:
            self.assertFalse(ctrl.click(100, 100))
            self.assertEqual(calls[0], 2)
        finally:
            controller._inputBackend.SendInput = origSend
            controller._sleepWithStop = origSleep

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
            origTime, origWait = auto_afk.time.time, auto_afk._wait
            auto_afk.time.time = lambda: (fakeNow.__setitem__(0, fakeNow[0] + 500.0) or fakeNow[0])
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
        origGrab = cap.sct.grab
        from PIL import ImageGrab
        origPilGrab = ImageGrab.grab
        cap.sct.grab = lambda _: (_ for _ in ()).throw(RuntimeError("mss failed"))
        ImageGrab.grab = lambda bbox=None, all_screens=False: (grabCalls.append((bbox, all_screens)) or fakeImage)
        try:
            img = cap.capture_region(-1920, 100, 300, 200)
            self.assertEqual(img.shape, (200, 300, 3))
            self.assertEqual(grabCalls[-1], ((-1920, 100, -1620, 300), True))
        finally:
            cap.sct.grab = origGrab
            ImageGrab.grab = origPilGrab

    def test_daily_challenge_does_not_match_huyen_linh(self):
        self.assertIsNone(self.ocr.findText([_item("Thách Đấu Hằng Ngày")], config.OCR_KEYWORDS["challenge_hl"]))

    def test_launch_game_prompts_when_input_permission_missing(self):
        prompts = []
        eng = bot_engine.BotEngine(prompt_callback=lambda t, m: prompts.append((t, m)))
        origFind, origFocus, origRect, origFg, origPerm, origReq, origOpen = (
            bot_engine.findGameWindow,
            bot_engine.focusGameWindow,
            bot_engine.getClientRectScreen,
            bot_engine.isWindowForeground,
            bot_engine.hasInputPermission,
            bot_engine.requestInputPermission,
            bot_engine.openMacAccessibilitySettings,
        )
        try:
            bot_engine.findGameWindow = lambda _: 999
            bot_engine.focusGameWindow = lambda _: True
            bot_engine.getClientRectScreen = lambda _: (0, 0, 1280, 720)
            bot_engine.isWindowForeground = lambda _: True
            bot_engine.hasInputPermission = lambda: False
            bot_engine.requestInputPermission = lambda: False
            bot_engine.openMacAccessibilitySettings = lambda: None
            eng.state = bot_engine.State.LAUNCH_GAME
            eng._state_launch_game()
            self.assertEqual(eng.state, bot_engine.State.LAUNCH_GAME)
            self.assertEqual(len(prompts), 1)
        finally:
            (
                bot_engine.findGameWindow,
                bot_engine.focusGameWindow,
                bot_engine.getClientRectScreen,
                bot_engine.isWindowForeground,
                bot_engine.hasInputPermission,
                bot_engine.requestInputPermission,
                bot_engine.openMacAccessibilitySettings,
            ) = (origFind, origFocus, origRect, origFg, origPerm, origReq, origOpen)


if __name__ == "__main__":
    unittest.main()
