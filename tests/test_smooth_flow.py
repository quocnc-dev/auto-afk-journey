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


class TestStageEnterAndCursorPark(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_slow_stage_load_does_not_trigger_false_fallback(self):
        lobbyBoth = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]
        prep = [_ocrItem("Thành Tích", 125, 900, w=80, h=22), _ocrItem("Chiến Đấu Tự Động", 285, 892, w=180, h=28)]
        # Bấm Huyền Linh -> game vẫn hiện sảnh 1 nhịp (load chậm) -> rồi mới vào màn chuẩn bị
        bot, _, _ = _runScenes(self.ocr, [lobbyBoth, lobbyBoth, prep, prep], auto_afk.run_auto_afk, peek=True)
        self.assertEqual(bot.ctrl.clicks[:2], [(180, 800), (285, 892)])
        self.assertNotIn((510, 800), bot.ctrl.clicks)
        self.assertFalse(any("fallback" in m for m in bot.logs))

    def test_cursor_parks_on_titlebar_after_click(self):
        moves = []
        bot = MockBot(self.ocr, [])
        bot.ctrl.move_to = lambda x, y: moves.append((x, y)) or True
        orig = config.CURSOR_PARK_AFTER_CLICK
        config.CURSOR_PARK_AFTER_CLICK = True
        try:
            from modules.game_actions import safeClick
            self.assertTrue(safeClick(bot, 300, 800, (1001, 30, 678, 936)))
        finally:
            config.CURSOR_PARK_AFTER_CLICK = orig
        self.assertEqual(bot.ctrl.clicks, [(300, 800)])
        self.assertEqual(moves, [(1001 + 339, 30 + config.CURSOR_PARK_TITLEBAR_OFFSET)])

    def test_no_park_when_disabled_or_click_refused(self):
        moves = []
        bot = MockBot(self.ocr, [])
        bot.ctrl.move_to = lambda x, y: moves.append((x, y)) or True
        bot.canInteractAt = lambda x, y, expectedRect=None: False
        orig = config.CURSOR_PARK_AFTER_CLICK
        config.CURSOR_PARK_AFTER_CLICK = True
        try:
            from modules.game_actions import safeClick
            self.assertFalse(safeClick(bot, 300, 800, (1001, 30, 678, 936)))
        finally:
            config.CURSOR_PARK_AFTER_CLICK = orig
        self.assertEqual(moves, [])


class TestNoFalseFinishInBattle(unittest.TestCase):
    """14:18:41 build 29: chữ kỹ năng trong trận khớp nhầm 'Hoàn Tất' -> bot click giữa sân đấu -> hiện popup tắt auto."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_skill_texts_do_not_match_finish(self):
        bot = MockBot(self.ocr, [])
        bot._scanRect = (1000, 30, 678, 936)
        for raw in ["Tự Động Hồi Phục", "Tự Động Hoán Đổi", "Tự động hóa"]:
            run = [_ocrItem(raw, 1413, 313)]
            bot2, _, _ = _runScenes(self.ocr, [run], auto_afk.run_auto_afk)
            self.assertEqual(bot2.ctrl.clicks, [], raw)

    def test_real_finish_text_still_matches(self):
        scene = [_ocrItem("Chien Dau Tur Dong Hoan Tat", 338, 287, w=440, h=40)]
        bot, _, _ = _runScenes(self.ocr, [scene], auto_afk.run_auto_afk)
        self.assertEqual(bot.ctrl.clicks, [(338, 287)])

    def test_no_close_or_finish_click_while_battle_timer_visible(self):
        scene = [_ocrItem("71giây", 610, 46, w=70, h=24), _ocrItem("Chiến Đấu Tự Động Hoàn Tất", 338, 287, w=440, h=40)]
        bot, _, _ = _runScenes(self.ocr, [scene], auto_afk.run_auto_afk)
        self.assertEqual(bot.ctrl.clicks, [])

    def test_transient_finish_text_is_confirmed_before_click(self):
        flash = [_ocrItem("Chiến Đấu Tự Động Hoàn Tất", 338, 287, w=440, h=40)]
        gone = [_ocrItem("Tự Động Chiến Đấu...", 338, 845, w=220, h=24)]
        bot, _, _ = _runScenes(self.ocr, [flash, gone, gone], auto_afk.run_auto_afk, peek=True)
        self.assertEqual(bot.ctrl.clicks, [])
        bot, _, _ = _runScenes(self.ocr, [flash, flash], auto_afk.run_auto_afk, peek=True)
        self.assertEqual(bot.ctrl.clicks, [(338, 287)])


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
