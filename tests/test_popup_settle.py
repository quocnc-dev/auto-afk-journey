"""
Regression (build 33, 26/11): popup 'Tắt chế độ Chiến Đấu Tự Động?' bị bắt khi còn đang trượt vào ->
click X đầu tiên lệch ~23px lên trên và bị game bỏ qua. Bot thật phải chờ popup đứng yên rồi dò lại nút X.
Kèm: ghi ảnh debug khi mũi tên chuyển team nằm khác chỗ lần trước (từng dò nhầm ra (1482, 320)).
"""

import unittest

from modules import auto_afk, team_copy
from ocr_engine import OcrEngine
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
        team_copy._snapshotIfArrowMoved(bot, (1414, 699), None, [], None)   # lần đầu: chỉ ghi nhớ
        team_copy._snapshotIfArrowMoved(bot, (1415, 700), None, [], None)   # lệch 1px: bình thường
        self.assertEqual(bot.debugSnap.reasons, [])
        team_copy._snapshotIfArrowMoved(bot, (1482, 320), None, [], None)   # nhảy chỗ khác: chụp
        self.assertEqual(bot.debugSnap.reasons, ["team_arrow_moved"])
        self.assertTrue(any("1482, 320" in m for m in bot.logs))


if __name__ == "__main__":
    unittest.main()
