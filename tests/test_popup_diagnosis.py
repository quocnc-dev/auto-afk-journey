"""Unit tests cho log chẩn đoán popup 'Tắt chế độ Chiến Đấu Tự Động?': bot click, chuột người dùng hay mất focus."""

import time
import unittest

import numpy as np

import controller
from modules import auto_afk
from modules.afk_detectors import AfkLoopState
from modules.game_actions import describePopupCause, waitWatchingFocus
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot


def _ocrItem(raw: str, cx: int, cy: int, w: int = 120, h: int = 24) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


class TestPopupDiagnosis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def _bot(self, lastClick=None, cursor=None):
        bot = MockBot(self.ocr, [])
        bot.ctrl.lastClick = lastClick
        bot.ctrl.cursorPos = lambda: cursor
        return bot

    def test_user_moved_mouse(self):
        st = AfkLoopState()
        msg = describePopupCause(self._bot((100.0, 1307, 902), (500, 300)), st, 123.0)
        self.assertIn("23s trước tại (1307, 902)", msg)
        self.assertIn("KHÔNG phải do bot", msg)
        self.assertIn("không bị mất focus", msg)

    def test_cursor_still_at_bot_click_and_focus_loss(self):
        st = AfkLoopState()
        st.lastFocusLossTime = 118.0
        msg = describePopupCause(self._bot((100.0, 1307, 902), (1308, 903)), st, 123.0)
        self.assertIn("vẫn ở chỗ bot đặt cuối cùng", msg)
        self.assertIn("mất focus lần cuối 5s trước", msg)

    def test_parked_cursor_is_not_user_movement(self):
        bot = self._bot((100.0, 1307, 902), (1340, 42))
        bot.ctrl.lastBotCursor = (1340, 42)  # bot đã tự đỗ chuột lên thanh tiêu đề
        msg = describePopupCause(bot, AfkLoopState(), 123.0)
        self.assertIn("vẫn ở chỗ bot đặt cuối cùng", msg)
        self.assertNotIn("KHÔNG phải do bot", msg)

    def test_no_click_yet(self):
        msg = describePopupCause(self._bot(None, (1, 1)), AfkLoopState(), 10.0)
        self.assertIn("bot chưa click", msg)

    def test_wait_watching_focus_records_loss_and_logs_once(self):
        bot = MockBot(self.ocr, [])
        states = iter([True, False, False, True, True])
        bot.isGameForeground = lambda: next(states, True)
        st = AfkLoopState()
        ok = waitWatchingFocus(bot, st, 2.5, lambda b, s: True)
        self.assertTrue(ok)
        self.assertIsNotNone(st.lastFocusLossTime)
        self.assertEqual(sum("mất focus" in m for m in bot.logs), 1)

    def test_wait_without_focus_check_falls_back(self):
        bot = MockBot(self.ocr, [])
        waits = []
        self.assertTrue(waitWatchingFocus(bot, AfkLoopState(), 2.5, lambda b, s: waits.append(s) or True))
        self.assertEqual(waits, [2.5])

    def test_controller_records_last_click(self):
        ctrl = controller.Controller(delay_after_click=0)
        orig = controller._moveCursor, controller._sendMouseClick, controller._sleepWithStop
        controller._moveCursor = lambda x, y: True
        controller._sendMouseClick = lambda button="left": True
        controller._sleepWithStop = lambda s, e=None: True
        try:
            self.assertTrue(ctrl.click(10, 20))
        finally:
            controller._moveCursor, controller._sendMouseClick, controller._sleepWithStop = orig
        self.assertEqual(ctrl.lastClick[1:], (10, 20))
        self.assertLess(abs(ctrl.lastClick[0] - time.time()), 5)

    def test_loop_logs_diagnosis_once_per_popup(self):
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        popup = [_ocrItem("Tắt chế độ Chiến Đấu Tự Động?", 338, 440, w=320, h=26)]
        bot = MockBot(self.ocr, [frame, frame])
        queue = [popup, popup]
        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: queue.pop(0) if queue else []
        auto_afk._wait = lambda b, s: True
        try:
            auto_afk.run_auto_afk(bot)
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        self.assertEqual(sum("Chẩn đoán popup" in m for m in bot.logs), 1)


if __name__ == "__main__":
    unittest.main()
