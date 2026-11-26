"""Chuỗi thua liên tiếp: thắng (kể cả auto vượt màn rồi mới dừng ở màn 'Hoàn Tất') phải reset; đủ 5 lần thua liên tiếp mới đổi mode."""

import os
import unittest

import cv2
import numpy as np

from modules import auto_afk
from modules.afk_detectors import parseStagesCleared
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "auto_battle_complete_678x936.jpg")


def _ocrItem(raw: str, cx: int, cy: int, w: int = 120, h: int = 24) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


RETRY = [_ocrItem("Thử Lại", 450, 820)]
AUTO_BATTLE = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
LOBBY = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]
HL, NORMAL = (180, 800), (510, 800)


def _complete(*extra):
    return [_ocrItem("Chiến Đấu Tự Động Hoàn Tất", 338, 287, w=440, h=40)] + list(extra)


class TestParseStagesCleared(unittest.TestCase):

    def test_variants(self):
        self.assertEqual(parseStagesCleared([_ocrItem("Đã hoàn thành màn xl", 338, 345)]), 1)  # OCR đọc 1 thành l
        self.assertEqual(parseStagesCleared([_ocrItem("Đã hoàn thành màn x12", 338, 345)]), 12)
        self.assertEqual(parseStagesCleared([_ocrItem("Đã hoàn thành màn x0", 338, 345)]), 0)
        self.assertEqual(parseStagesCleared([_ocrItem("Tiến Trình Màn Chơi Đỉnh Cao 846 >> 848", 338, 470)]), 2)
        self.assertIsNone(parseStagesCleared([_ocrItem("Nhấn để đóng", 338, 900)]))

    def test_real_complete_screen(self):
        items = OcrEngine().scanImage(cv2.imread(FIXTURE))
        self.assertEqual(parseStagesCleared(items), 1)


class TestDefeatStreak(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def _run(self, scenes):
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [frame] * len(scenes))
        queue = list(scenes)
        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: queue.pop(0) if queue else []
        auto_afk._wait = lambda b, s: True
        try:
            auto_afk.run_auto_afk(bot)
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        return bot

    def test_complete_after_winning_a_stage_resets_streak(self):
        # 4 lần thua, rồi auto vượt 1 màn và dừng ở 'Hoàn Tất' -> chuỗi chỉ còn 1 -> vẫn giữ Huyền Linh
        won = _complete(_ocrItem("Đã hoàn thành màn xl", 338, 345))
        bot = self._run(([RETRY, AUTO_BATTLE] * 4) + [won, LOBBY])
        self.assertEqual(bot.ctrl.clicks[-1], HL)
        self.assertTrue(any("reset chuỗi thua" in m for m in bot.logs))
        self.assertTrue(any("thua lần 1/5" in m for m in bot.logs))

    def test_complete_without_progress_counts_as_fifth_defeat(self):
        lost = _complete(_ocrItem("Đã hoàn thành màn x0", 338, 345))
        bot = self._run(([RETRY, AUTO_BATTLE] * 4) + [lost, LOBBY])
        self.assertEqual(bot.ctrl.clicks[-1], NORMAL)

    def test_four_defeats_win_then_four_defeats_does_not_switch(self):
        victory = [_ocrItem("Đã Tăng Phần Thưởng AFK", 338, 250)]
        bot = self._run(([RETRY, AUTO_BATTLE] * 4) + [victory] + ([RETRY, AUTO_BATTLE] * 4) + [LOBBY])
        self.assertEqual(bot.ctrl.clicks[-1], HL)
        self.assertFalse(any("đổi mode" in m or "Chuyển chế độ" in m for m in bot.logs))



PREP = [_ocrItem("Thành Tích", 125, 900, w=80, h=22), _ocrItem("Chiến Đấu Tự Động", 285, 892, w=180, h=28)]
STATS = [_ocrItem("Sao chép", 380, 880, w=160, h=30)]
STATS_CLICK, COPY_CLICK, AUTO_CLICK = (125, 900), (380, 880), (285, 892)


class TestTeamChangeOnEveryDefeat(unittest.TestCase):
    """14:33 build 30: thua kiểu 'Hoàn Tất' -> về chọn chế độ -> vào lại thì bot đánh luôn, không đổi team."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def _run(self, scenes, st=None):
        return TestDefeatStreak._run(self, scenes)

    def test_complete_defeat_changes_team_before_reentering(self):
        won = _complete(_ocrItem("Đã hoàn thành màn x3", 338, 345))
        bot = self._run([won, LOBBY, PREP, STATS, PREP])
        clicks = bot.ctrl.clicks
        self.assertEqual(clicks[1:], [HL, STATS_CLICK, COPY_CLICK, AUTO_CLICK])
        self.assertTrue(any("chép team kế tiếp" in m for m in bot.logs))

    def test_no_team_change_when_entering_without_defeat(self):
        bot = self._run([LOBBY, PREP])
        self.assertEqual(bot.ctrl.clicks, [HL, AUTO_CLICK])

    def _arrowClicksPerDefeat(self, winBetween: bool):
        from modules.loop_state import AfkLoopState
        from modules import team_copy
        st = AfkLoopState()
        arrowClicks = []
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [])
        origArrow, origScan, origWait = team_copy.findNextTeamArrow, auto_afk._scanGame, auto_afk._wait
        team_copy.findNextTeamArrow = lambda *a, **k: (600, 500)
        auto_afk._scanGame = lambda b: (frame, 0, 0, (0, 0, 676, 934), STATS)
        auto_afk._wait = lambda b, s: True
        try:
            for _ in range(3):
                st.recordDefeat()
                before = len(bot.ctrl.clicks)
                team_copy.applyStatsModalTeam(bot, frame, 0, 0, (0, 0, 676, 934), STATS, st=st)
                arrowClicks.append(bot.ctrl.clicks[before:].count((600, 500)))
                if winBetween:
                    st.onVictory()
        finally:
            team_copy.findNextTeamArrow, auto_afk._scanGame, auto_afk._wait = origArrow, origScan, origWait
        return arrowClicks, st

    def test_repeated_defeats_on_same_stage_rotate_teams(self):
        arrowClicks, st = self._arrowClicksPerDefeat(winBetween=False)
        self.assertEqual(arrowClicks, [0, 1, 2])  # team #1, #2, #3 của cùng 1 màn
        self.assertEqual(st.teamCursor, 3)
        self.assertFalse(st.needTeamChange)

    def test_new_stage_after_win_starts_from_team_one(self):
        # Vượt màn -> bảng Thành tích là của màn mới -> lần thua đầu ở màn mới chép lại team #1
        arrowClicks, _ = self._arrowClicksPerDefeat(winBetween=True)
        self.assertEqual(arrowClicks, [0, 0, 0])

    def test_log_scenario_build30(self):
        # 14:33: auto vượt 3 màn rồi dừng ở 'Hoàn Tất' -> vào lại chép team #1; thua tiếp cùng màn -> team #2
        from modules.loop_state import AfkLoopState
        st = AfkLoopState(teamCursor=2)
        st.onVictory()
        st.recordDefeat(fromMainDone=True)
        self.assertEqual((st.teamCursor, st.needTeamChange, st.failedAttempts), (0, True, 1))

if __name__ == "__main__":
    unittest.main()
