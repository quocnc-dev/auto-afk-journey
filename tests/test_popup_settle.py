"""
Regression (build 33, 26/11): popup 'Tắt chế độ Chiến Đấu Tự Động?' bị bắt khi còn đang trượt vào ->
click X đầu tiên lệch ~23px lên trên và bị game bỏ qua. Bot thật phải chờ popup đứng yên rồi dò lại nút X.
Kèm: ghi ảnh debug khi mũi tên chuyển team nằm khác chỗ lần trước (từng dò nhầm ra (1482, 320)).
"""

import os
import unittest

import cv2
import numpy as np

import config
from modules import auto_afk, team_copy
from modules.game_actions import waitScreenStable
from modules.loop_state import AfkLoopState
from ocr_engine import OcrEngine, findNextTeamArrow
from tests.test_defeat_streak import STATS
from tests.test_ocr_and_logic import MockBot
from tests.test_smooth_flow import _ocrItem, _runScenes


def _popup(xCenterY: int):
    return [_ocrItem("Tắt chế độ Chiến Đấu Tự Động?", 344, xCenterY - 170, w=330, h=30),
            _ocrItem("X", 384, xCenterY, w=36, h=36)]


class TestPopupSettle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_real_bot_clicks_x_after_popup_settles(self):
        # Khung 1: popup đang trượt (X ở y=617); khung 2 sau khi đứng yên: X ở y=640
        bot, _, _ = _runScenes(self.ocr, [_popup(617), _popup(640)], auto_afk.run_auto_afk, peek=True)
        self.assertEqual(bot.ctrl.clicks, [(384, 640)])

    def test_skips_click_when_popup_closed_while_settling(self):
        bot, _, _ = _runScenes(self.ocr, [_popup(617), []], auto_afk.run_auto_afk, peek=True)
        self.assertEqual(bot.ctrl.clicks, [])

    def test_mock_bot_without_peek_clicks_immediately(self):
        bot, _, _ = _runScenes(self.ocr, [_popup(640)], auto_afk.run_auto_afk)
        self.assertEqual(bot.ctrl.clicks, [(384, 640)])


class _Snapper:
    def __init__(self):
        self.reasons = []

    def save(self, reason, *args, **kwargs):
        self.reasons.append(reason)
        return f"/tmp/{reason}.png"


class TestTeamArrowSnapshot(unittest.TestCase):

    def _bot(self):
        bot = type("B", (), {})()
        bot.logs, bot.debugSnap = [], _Snapper()
        bot._log = bot.logs.append
        return bot

    def test_snapshot_only_when_arrow_moves(self):
        bot = self._bot()
        rect = (1000, 30, 678, 936)
        team_copy._snapshotIfArrowMoved(bot, (1414, 699), None, [], rect)   # lần đầu: chỉ ghi nhớ
        team_copy._snapshotIfArrowMoved(bot, (1415, 700), None, [], rect)   # lệch 1px: bình thường
        team_copy._snapshotIfArrowMoved(bot, (1454, 739), None, [], (1040, 70, 678, 936))  # kéo cửa sổ: vẫn cùng chỗ
        self.assertEqual(bot.debugSnap.reasons, [])
        team_copy._snapshotIfArrowMoved(bot, (1482, 320), None, [], rect)   # nhảy chỗ khác: chụp
        self.assertEqual(bot.debugSnap.reasons, ["team_arrow_moved"])
        self.assertTrue(any("(482, 290)" in m and "đã lưu ảnh" in m for m in bot.logs))

    def test_log_does_not_claim_saved_when_rate_limited(self):
        bot = self._bot()
        bot.debugSnap.save = lambda *a, **k: None  # snapshotter bỏ qua (giới hạn 60s)
        team_copy._snapshotIfArrowMoved(bot, (100, 100), None, [], None)
        team_copy._snapshotIfArrowMoved(bot, (300, 300), None, [], None)
        self.assertFalse(any("đã lưu ảnh" in m for m in bot.logs))


class TestScreenStable(unittest.TestCase):

    def _bot(self, frames):
        bot = MockBot(None, [])
        seq = list(frames)
        bot.peekScreen = lambda: seq.pop(0) if len(seq) > 1 else seq[0]
        return bot, seq

    def test_needs_two_stable_pairs(self):
        a, b = np.zeros((100, 60, 3), np.uint8), np.full((100, 60, 3), 200, np.uint8)
        bot, seq = self._bot([a, b, b, b, b])
        polls = []
        self.assertTrue(waitScreenStable(bot, 5.0, lambda _b, s: polls.append(s) or True))
        self.assertEqual(len(polls), 3)  # a->b đổi, b->b ổn 1, b->b ổn 2

    def test_ignores_changes_outside_popup_band(self):
        a = np.zeros((100, 60, 3), np.uint8)
        b = a.copy()
        b[:20] = 255  # chỉ đồng hồ / phần trên cùng đổi
        bot, _ = self._bot([a, b, a, b, a])
        polls = []
        waitScreenStable(bot, 5.0, lambda _b, s: polls.append(s) or True)
        self.assertEqual(len(polls), config.POPUP_STABLE_PAIRS)


class TestNextTeamArrow(unittest.TestCase):

    def test_prefers_round_button_over_white_glyph_on_art(self):
        tpl = cv2.imread(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "btn_afk_next_team.png"))
        modal = np.full((936, 678, 3), 35, np.uint8)
        modal[300:300 + tpl.shape[0], 380:380 + tpl.shape[1]] = tpl          # mũi tên thật
        # Ảnh tướng màu nâu cam (độ sáng vừa nên thuật toán cũ chấp nhận) có nét trắng giống '>', nằm dưới
        modal[600:680, 440:520] = (30, 80, 170)
        modal[630:653, 478:488] = 255
        hit = findNextTeamArrow(modal, 1000, 30)
        self.assertIsNotNone(hit)
        self.assertTrue(1380 <= hit[0] <= 1380 + tpl.shape[1] and 330 <= hit[1] <= 330 + tpl.shape[0], hit)

    def test_white_glyph_alone_is_not_an_arrow(self):
        modal = np.full((936, 678, 3), 35, np.uint8)
        modal[600:680, 440:520] = (30, 80, 170)
        modal[630:653, 478:488] = 255
        self.assertIsNone(findNextTeamArrow(modal))


class TestPartialArrowClicks(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_retry_only_clicks_remaining_moves(self):
        frame = np.zeros((934, 676, 3), np.uint8)
        rect = (0, 0, 676, 934)
        bot = MockBot(self.ocr, [])
        blocked = []

        def guard(x, y, expectedRect=None):  # chặn đúng 1 lần ở click thứ 3 (mất focus giữa chừng)
            if len(bot.ctrl.clicks) == 2 and not blocked:
                blocked.append(1)
                return False
            return True
        bot.canInteractAt = guard
        st = AfkLoopState(teamCursor=3)
        origArrow, origScan, origWait = team_copy.findNextTeamArrow, auto_afk._scanGame, auto_afk._wait
        team_copy.findNextTeamArrow = lambda *a, **k: (600, 500)
        auto_afk._scanGame = lambda b: (frame, 0, 0, rect, STATS)
        auto_afk._wait = lambda b, s: True
        try:
            team_copy.applyStatsModalTeam(bot, frame, 0, 0, rect, STATS, st=st)   # click thứ 3 bị hủy
            self.assertEqual(st.statsArrowClicks, 2)
            team_copy.applyStatsModalTeam(bot, frame, 0, 0, rect, STATS, st=st)   # vòng lặp chính thử lại
        finally:
            team_copy.findNextTeamArrow, auto_afk._scanGame, auto_afk._wait = origArrow, origScan, origWait
        self.assertEqual(bot.ctrl.clicks.count((600, 500)), 3)  # tổng đúng 3 lần -> team #4, không phải #6
        self.assertEqual(st.teamCursor, 4)
        self.assertEqual(st.statsArrowClicks, 0)


if __name__ == "__main__":
    unittest.main()
