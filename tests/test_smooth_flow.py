"""Unit tests tối ưu luồng: nhận thay đổi vùng nhỏ, chờ màn chuẩn bị đấu load chậm, bớt log trùng khi chờ trận."""

import os
import unittest

import cv2
import numpy as np

import config
from modules import auto_afk, team_copy
from modules.afk_detectors import AfkLoopState
from modules.game_actions import frameDiff, hasScreenChanged
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pause_auto_prompt_678x936.jpg")


def _ocrItem(raw: str, cx: int, cy: int, w: int = 120, h: int = 24) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


def _runScenes(ocr, scenes, fn, peek=False):
    frame = np.zeros((934, 676, 3), dtype=np.uint8)
    bot = MockBot(ocr, [frame] * len(scenes))
    if peek:
        bot.peekScreen = lambda: frame
    queue = list(scenes)
    origScan, origWait = bot.ocr.scanImage, auto_afk._wait
    bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: queue.pop(0) if queue else []
    auto_afk._wait = lambda b, s: True
    try:
        result = fn(bot)
    finally:
        bot.ocr.scanImage, auto_afk._wait = origScan, origWait
    return bot, result, queue


class TestLocalChange(unittest.TestCase):

    def test_small_region_change_counts_as_changed(self):
        img = cv2.imread(FIXTURE)
        local = img.copy()
        local[300:420, 250:370] = 255 - local[300:420, 250:370]  # đổi ảnh team ~2% màn hình
        self.assertLess(frameDiff(img, local), config.SCREEN_CHANGE_THRESHOLD)  # trung bình không đủ...
        self.assertTrue(hasScreenChanged(img, local))  # ...nhưng vùng nhỏ đổi rõ vẫn nhận ra
        self.assertFalse(hasScreenChanged(img, img.copy()))

    def test_noise_is_not_change(self):
        img = cv2.imread(FIXTURE)
        rng = np.random.default_rng(0)
        noisy = np.clip(img.astype(np.int16) + rng.integers(-6, 7, img.shape), 0, 255).astype(np.uint8)
        self.assertFalse(hasScreenChanged(img, noisy))


class TestSlowPrepScreen(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_rescans_until_stats_button_loads(self):
        loading = [_ocrItem("Đang tải...", 338, 460)]
        prep = [_ocrItem("Thành Tích", 125, 900, w=80, h=22), _ocrItem("Chiến Đấu Tự Động", 285, 892, w=180, h=28)]
        statsModal = [_ocrItem("Sao chép", 380, 880, w=160, h=30)]
        st = AfkLoopState()
        bot, _, queue = _runScenes(self.ocr, [loading, loading, prep, statsModal],
                                   lambda b: team_copy.handlePickTeamInStats(b, st), peek=True)
        self.assertEqual(bot.ctrl.clicks, [(125, 900), (380, 880)])
        self.assertEqual(queue, [])

    def test_gives_up_after_timeout_without_crash(self):
        orig = config.PREP_SCREEN_WAIT
        config.PREP_SCREEN_WAIT = 0.0
        try:
            bot, _, _ = _runScenes(self.ocr, [[], []], lambda b: team_copy.handlePickTeamInStats(b, AfkLoopState()),
                                   peek=True)
        finally:
            config.PREP_SCREEN_WAIT = orig
        self.assertEqual(bot.ctrl.clicks, [])
        self.assertTrue(any("Thành tích" in m for m in bot.logs))

    def test_team_switch_uses_short_fixed_wait(self):
        img = cv2.imread(FIXTURE)
        waits = []
        bot = MockBot(self.ocr, [])
        st = AfkLoopState(failedAttempts=3)
        origWait, origArrow, origScan = auto_afk._wait, team_copy.findNextTeamArrow, auto_afk._scanGame
        auto_afk._wait = lambda b, s: waits.append(s) or True
        team_copy.findNextTeamArrow = lambda *a, **k: (600, 500)
        auto_afk._scanGame = lambda b: (img, 0, 0, (0, 0, 678, 936), [_ocrItem("Sao chép", 380, 880)])
        try:
            team_copy.applyStatsModalTeam(bot, img, 0, 0, (0, 0, 678, 936), [], st=st)
        finally:
            auto_afk._wait, team_copy.findNextTeamArrow, auto_afk._scanGame = origWait, origArrow, origScan
        self.assertEqual(bot.ctrl.clicks, [(600, 500), (600, 500), (380, 880)])
        self.assertEqual(waits.count(config.TEAM_SWITCH_WAIT), 2)
        self.assertFalse(any("không đổi" in m for m in bot.logs))


class TestQuietBattleWait(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_alternating_wait_states_log_once(self):
        battle = [_ocrItem("Tự Động Chiến Đấu...", 338, 845, w=220, h=24)]
        progress = [_ocrItem("Tự Động Xử Lý", 75, 880, w=130, h=22)]
        bot, _, _ = _runScenes(self.ocr, [battle, progress, battle, progress, battle], auto_afk.run_auto_afk)
        waitLogs = [m for m in bot.logs if m.startswith("⏳")]
        self.assertEqual(len(waitLogs), 1, waitLogs)


if __name__ == "__main__":
    unittest.main()
