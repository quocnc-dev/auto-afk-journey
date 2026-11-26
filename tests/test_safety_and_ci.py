"""Unit tests cho các ràng buộc an toàn P1/P2: mất cửa sổ, Stop, timeout, đa màn hình và cấu trúc file."""

import importlib
import os
import sys
import types
import unittest

import cv2
import numpy as np

import bot_engine
import config
import controller
import main
import ui_layout
import ui_tabs
import vision
import window_manager
from modules import auto_afk
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot


def _makeItem(raw: str, cx: int = 200, cy: int = 200) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - 40, cy - 12, cx + 40, cy + 12)


class TestSafetyAndCI(unittest.TestCase):
    """Kiểm thử an toàn luồng bot, chống nhận nhầm và giới hạn cấu trúc repo."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()
        cls.tplDir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

    def test_imports_and_300_line_limits(self):
        for mod in [window_manager, vision, controller, bot_engine, main, ui_layout, ui_tabs, auto_afk]:
            self.assertIsNotNone(mod)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in [
            "config.py", "window_manager.py", "ocr_engine.py", "vision.py",
            "controller.py", "bot_engine.py", "main.py", "ui_layout.py", "ui_tabs.py",
            "updater.py", "ui_updater.py", "modules/auto_afk.py", "modules/afk_detectors.py", "modules/debug_snapshot.py", "modules/game_actions.py", "modules/team_copy.py", "modules/loop_state.py", "modules/mode_switch.py", "modules/system_helpers.py",
            "tests/test_ocr_and_logic.py", "tests/test_safety_and_ci.py",
            "tests/test_p1_p2_fixes.py", "tests/test_mode_fallback.py", "tests/test_updater.py", "tests/test_debug_snapshot.py", "tests/test_flow_improvements.py", "tests/test_popup_diagnosis.py", "tests/test_issue_tracker.py", "tests/test_smooth_flow.py", "tests/test_defeat_streak.py", "tests/test_popup_settle.py", "tests/test_launch_prompt.py", "tests/test_ux_and_system.py",
        ]:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                self.assertLessEqual(len(f.readlines()), 300, f"{rel} vượt 300 dòng")

    def test_no_false_positives(self):
        items = [_makeItem("Battle Records"), _makeItem("Cập nhật hoàn tất", 200, 300)]
        fightEx = [w for k in config.FIGHT_EXCLUDE_KEYS for w in config.OCR_KEYWORDS[k]] + config.FIGHT_EXTRA_EXCLUDES
        self.assertIsNone(
            self.ocr.findText(items, config.OCR_KEYWORDS["fight"], excludeKeywords=fightEx, wholePhrase=True)
        )
        self.assertIsNone(
            self.ocr.findText(items, config.OCR_KEYWORDS["auto_battle_complete"], excludeKeywords=config.FIGHT_EXTRA_EXCLUDES)
        )

    def test_virtual_desktop_secondary_monitor_mapping(self):
        self.assertEqual(controller.toVirtualDesktopCoords(-1920, 0, -1920, 0, 3840, 1080), (0, 0))
        self.assertEqual(controller.toVirtualDesktopCoords(1919, 1079, -1920, 0, 3840, 1080), (65535, 65535))
        nxMid, _ = controller.toVirtualDesktopCoords(0, 540, -1920, 0, 3840, 1080)
        self.assertTrue(32700 <= nxMid <= 32850)

    def test_missing_window_never_captures_fullscreen_or_clicks(self):
        cap = vision.ScreenCapture()
        img, ox, oy = cap.capture_window(None)
        self.assertIsNone(img)
        self.assertEqual((ox, oy), (0, 0))

        bot = MockBot(self.ocr, [None, None, None])
        fakeNow = [0.0]

        def stepTime():
            fakeNow[0] += 20.0
            return fakeNow[0]

        origTime, origWait = auto_afk.time.time, auto_afk._wait
        auto_afk.time.time = stepTime
        auto_afk._wait = lambda b, s: True
        try:
            ok = auto_afk.run_auto_afk(bot)
        finally:
            auto_afk.time.time, auto_afk._wait = origTime, origWait

        self.assertFalse(ok)
        self.assertEqual(len(bot.ctrl.clicks), 0)

    def test_stop_mid_retry_blocks_subsequent_clicks(self):
        retryPath = os.path.join(self.tplDir, "btn_retry.png")
        statsPath = os.path.join(self.tplDir, "btn_afk_stats.png")
        copyPath = os.path.join(self.tplDir, "btn_afk_copy_team.png")
        if not (os.path.exists(retryPath) and os.path.exists(statsPath) and os.path.exists(copyPath)):
            self.skipTest("Thiếu ảnh mẫu để test Stop giữa chừng")

        def makeScene(path):
            canvas = np.full((720, 1280, 3), 40, dtype=np.uint8)
            im = cv2.imread(path)
            h, w = im.shape[:2]
            canvas[300:300 + h, 500:500 + w] = im
            return canvas

        frames = [makeScene(retryPath), makeScene(statsPath), makeScene(copyPath)]
        holder = {}
        bot = MockBot(self.ocr, frames, onClick=lambda c: holder["bot"]._stop_event.set() if c == 1 else None)
        holder["bot"] = bot
        self.assertTrue(auto_afk.run_auto_afk(bot))
        self.assertEqual(len(bot.ctrl.clicks), 1)

    def test_stuck_same_retry_screen_triggers_timeout(self):
        retryPath = os.path.join(self.tplDir, "btn_retry.png")
        if not os.path.exists(retryPath):
            self.skipTest("Thiếu btn_retry.png")
        canvas = np.full((720, 1280, 3), 40, dtype=np.uint8)
        im = cv2.imread(retryPath)
        h, w = im.shape[:2]
        canvas[300:300 + h, 500:500 + w] = im

        bot = MockBot(self.ocr, [canvas] * 10)
        fakeNow = [0.0]

        def advanceClock():
            fakeNow[0] += 500.0
            return fakeNow[0]

        origTime, origWait = auto_afk.time.time, auto_afk._wait
        auto_afk.time.time = advanceClock
        auto_afk._wait = lambda b, s: True
        try:
            ok = auto_afk.run_auto_afk(bot)
        finally:
            auto_afk.time.time, auto_afk._wait = origTime, origWait
        self.assertFalse(ok)

    def test_bot_engine_state_on_failure_and_exception(self):
        eng = bot_engine.BotEngine()
        eng.debugSnap.enabled = False  # test không ghi gói debug vào thư mục log thật
        origRun = bot_engine.run_auto_afk
        try:
            bot_engine.run_auto_afk = lambda _: False
            eng._state_auto_afk()
            self.assertEqual(eng.state, bot_engine.State.ERROR)

            def boom(_):
                raise RuntimeError("OCR crash")

            bot_engine.run_auto_afk = boom
            eng._state_auto_afk()
            self.assertEqual(eng.state, bot_engine.State.ERROR)

            eng._stop_event.set()
            bot_engine.run_auto_afk = lambda _: True
            eng._state_auto_afk()
            self.assertEqual(eng.state, bot_engine.State.IDLE)
        finally:
            bot_engine.run_auto_afk = origRun

    def test_test_click_import_safe(self):
        fakeMod = types.SimpleNamespace(
            click=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("click called on import")),
            moveTo=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("moveTo called on import")),
        )
        orig = sys.modules.get("pydirectinput")
        sys.modules["pydirectinput"] = fakeMod
        try:
            import test_click
            importlib.reload(test_click)
        finally:
            if orig is not None:
                sys.modules["pydirectinput"] = orig


if __name__ == "__main__":
    unittest.main()
