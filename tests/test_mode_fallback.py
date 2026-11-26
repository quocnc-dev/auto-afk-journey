"""Unit tests cho fallback hết ải Huyễn Linh và đổi 2 chiều Huyễn Linh <-> Thường."""

import unittest

import numpy as np

import config
from modules import auto_afk
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot


def _ocrItem(raw: str, cx: int, cy: int, w: int = 120, h: int = 24) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


class TestModeFallback(unittest.TestCase):
    """Kiểm thử fallback hết ải và chuyển mode 2 chiều qua cả Thử Lại lẫn Tự Động Xử Lý."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def _runWithScenes(self, scenes: list[list[OcrItem]], frame: np.ndarray | None = None):
        if frame is None:
            frame = np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [frame] * len(scenes))
        queue = list(scenes)
        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: queue.pop(0) if queue else []
        auto_afk._wait = lambda b, s: True
        try:
            ok = auto_afk.run_auto_afk(bot)
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        self.assertTrue(ok)
        return bot.ctrl.clicks

    def test_missing_huyen_linh_falls_back_to_normal_fight(self):
        lobbyOnlyNormal = [_ocrItem("Chiến Đấu", 510, 800)]
        clicks = self._runWithScenes([lobbyOnlyNormal])
        self.assertEqual(clicks, [(510, 800)])

    def test_stuck_lobby_button_switches_to_normal_fight(self):
        lobbyBoth = [
            _ocrItem("Thách Đấu Huyền Linh SV", 180, 800),
            _ocrItem("Chiến Đấu", 510, 800),
        ]
        clicks = self._runWithScenes([lobbyBoth, lobbyBoth, lobbyBoth])
        self.assertEqual(clicks, [(180, 800), (180, 800), (510, 800)])

    def test_two_way_switch_across_auto_progress_done_and_complete(self):
        doneScene = [_ocrItem("Tự Động Xử Lý", 75, 880), _ocrItem("Xong!", 75, 910)]
        completeScene = [_ocrItem("Chiến Đấu Tự Động Hoàn Tất", 340, 300)]
        autoBattleScene = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
        lobbyBoth = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]
        victoryScene = [_ocrItem("Đã Tăng Phần Thưởng AFK", 338, 250)]

        # 5 chu kỳ thua Huyễn Linh qua Xong! -> Hoàn Tất -> sảnh phải chuyển sang Chiến Đấu thường (510, 800)
        defeatCycle = [doneScene, completeScene, autoBattleScene]
        scenes = (defeatCycle * 4) + [doneScene, completeScene, lobbyBoth]
        # Thắng 1 trận thường -> reset đếm thua nhưng giữ mode thường, rồi thua 5 lần thường -> về lại Huyễn Linh (180, 800)
        scenes += [victoryScene] + (defeatCycle * 4) + [doneScene, completeScene, lobbyBoth]

        clicks = self._runWithScenes(scenes)
        lobbyClicks = [c for c in clicks if c in ((180, 800), (510, 800))]
        self.assertEqual(lobbyClicks, [(510, 800), (180, 800)])

    def test_xong_then_retry_does_not_double_count_defeat(self):
        doneScene = [_ocrItem("Tự Động Xử Lý", 75, 880), _ocrItem("Xong!", 75, 910)]
        retryScene = [_ocrItem("Thử Lại", 450, 820), _ocrItem("Quay Lại", 150, 820)]
        prepEmpty = []
        lobbyBoth = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]

        # 4 chu kỳ (Xong! -> Thử Lại) chỉ tính 4 lần thua -> về sảnh vẫn chọn Huyễn Linh (180, 800)
        scenes = ([doneScene, retryScene, prepEmpty] * 4) + [lobbyBoth]
        clicks = self._runWithScenes(scenes)
        self.assertEqual(clicks[-1], (180, 800))
        self.assertNotIn((150, 820), clicks)

    def test_close_button_after_stage2_defeat_preserves_and_counts_defeats(self):
        retryScene = [_ocrItem("Thử Lại", 450, 820)]
        autoBattleScene = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
        closeOnlyDefeat = [
            _ocrItem("Chiến Đấu Tự Động Hoàn Tất", 340, 280),
            _ocrItem("Đóng", 340, 780),
        ]
        lobbyBoth = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]

        # Thua 4 lần (Thử Lại) + lần 5 thắng màn 1 rồi thua màn 2 chỉ có nút Đóng -> phải đủ 5 để chuyển Thường (510, 800)
        scenes = ([retryScene, autoBattleScene] * 4) + [closeOnlyDefeat, lobbyBoth]
        clicks = self._runWithScenes(scenes)
        self.assertIn((340, 780), clicks)
        self.assertEqual(clicks[-1], (510, 800))
        self.assertIsNone(auto_afk._findKey(MockBot(self.ocr, []), autoBattleScene, "close_btn", exactOnly=True))

    def test_main_screen_never_clicks_bottom_nav_and_clicks_bottom_left_peak(self):
        mainScreenItems = [
            _ocrItem("Cẩm Nang Mùa Giải", 120, 60),
            _ocrItem("Ngôi Nhà Huyền Bí", 215, 900),
            _ocrItem("Chế Độ", 310, 890),
            _ocrItem("Chiến Đấu", 310, 912),
            _ocrItem("Hội Trường", 390, 890),
            _ocrItem("Cộng Hưởng", 390, 912),
            _ocrItem("Bang Hội", 465, 900),
            _ocrItem("Trang Viên", 640, 795),
            _ocrItem("Màn Chơi Đỉnh Cao", 52, 888, w=90, h=14),
            _ocrItem("785", 52, 912, w=50, h=20),
        ]
        clicks = self._runWithScenes([mainScreenItems])
        self.assertEqual(clicks, [(52, 888)])

        # Kể cả khi OCR bỏ sót chữ nhỏ 'Màn Chơi Đỉnh Cao', tuyệt đối không click Ngôi Nhà / Chế Độ / Hội Trường
        noCornerText = mainScreenItems[:-2]
        self.assertEqual(self._runWithScenes([noCornerText]), [])

    def test_prep_screen_with_buff_text_clicks_auto_battle_not_blocked_as_main_screen(self):
        prepItems = [
            _ocrItem("Màn Chơi Đỉnh Cao Huyễn", 338, 42, w=260, h=20),
            _ocrItem("Linh Sinh Vật 552", 338, 64, w=180, h=20),
            _ocrItem("Băng Giá Tiên Phong", 120, 190, w=180, h=22),
            _ocrItem("Tất cả đồng minh tăng 35%", 120, 230, w=220, h=20),
            _ocrItem("hiệu ứng thời tiết bão tuyết", 120, 280, w=220, h=20),
            _ocrItem("Thành Tích", 125, 900, w=80, h=22),
            _ocrItem("Chiến Đấu Tự Động", 285, 892, w=180, h=28),
            _ocrItem("Chiến Đấu", 545, 892, w=150, h=30),
        ]
        clicks = self._runWithScenes([prepItems])
        self.assertEqual(clicks, [(285, 892)])

    def test_copy_team_screen_detected_directly_in_main_loop(self):
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        frame[8:34, 14:40] = (50, 220, 50)  # Ô checkbox màu xanh lá đã tích ở bên trái chữ
        copyModalItems = [
            _ocrItem("Chỉ hiển thị đội hình đã sở hữu", 180, 20, w=260, h=20),
            _ocrItem("Màn Chơi Đỉnh Cao Huyễn Linh", 338, 52, w=260, h=20),
            _ocrItem("Sinh Vật 557", 338, 74, w=140, h=20),
            _ocrItem("Sao chép", 380, 880, w=160, h=30),
        ]
        clicks = self._runWithScenes([copyModalItems], frame=frame)
        self.assertEqual(clicks, [(380, 880)])

    def test_battle_timer_stands_still_and_pause_prompt_clicks_cancel_x(self):
        timerOnlyBattle = [
            _ocrItem("88giây", 610, 46, w=70, h=24),
            _ocrItem("Tự Động", 260, 845, w=90, h=24),
        ]
        self.assertEqual(self._runWithScenes([timerOnlyBattle]), [])

        pausePromptItems = [
            _ocrItem("88giây", 610, 46, w=70, h=24),
            _ocrItem("Tắt chế độ Chiến Đấu Tự Động?", 338, 440, w=320, h=26),
            _ocrItem("Tiến Trình AFK trong Mùa Giải Hiện Tại :", 338, 476, w=360, h=22),
        ]
        clicks = self._runWithScenes([pausePromptItems])
        self.assertEqual(len(clicks), 1)
        self.assertTrue(300 <= clicks[0][0] <= 460)
        self.assertTrue(500 <= clicks[0][1] <= 750)


if __name__ == "__main__":
    unittest.main()
