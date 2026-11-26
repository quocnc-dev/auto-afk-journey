"""Unit tests: cùng 1 lỗi lặp lại đủ ngưỡng -> tự lưu gói debug (ảnh + OCR + log gần nhất); crash -> lưu ngay."""

import json
import os
import shutil
import tempfile
import unittest

import numpy as np

import bot_engine
import config
from modules.debug_snapshot import DebugSnapshotter, IssueTracker, slugify


class TestIssueTracker(unittest.TestCase):

    def test_same_error_with_different_numbers_is_one_issue(self):
        tr = IssueTracker(threshold=5, windowSeconds=600, ignore=[])
        msgs = [f"⚠️ Click lệch tại ({x}, 600) — hủy click!" for x in range(5)]
        results = [tr.observe(m, now=float(i)) for i, m in enumerate(msgs)]
        self.assertEqual(results[:4], [None] * 4)
        self.assertIsNotNone(results[4])
        self.assertEqual(results[4][1], 5)
        # Đếm lại từ đầu sau khi đã báo
        self.assertIsNone(tr.observe(msgs[0], now=5.0))

    def test_old_hits_expire_outside_window(self):
        tr = IssueTracker(threshold=3, windowSeconds=10, ignore=[])
        self.assertIsNone(tr.observe("❌ Lỗi A", now=0))
        self.assertIsNone(tr.observe("❌ Lỗi A", now=1))
        self.assertIsNone(tr.observe("❌ Lỗi A", now=50))
        self.assertIsNone(tr.observe("❌ Lỗi A", now=51))
        self.assertIsNotNone(tr.observe("❌ Lỗi A", now=52))

    def test_ignores_info_and_normal_defeats(self):
        tr = IssueTracker(threshold=1, windowSeconds=600)
        self.assertIsNone(tr.observe("⏳ Đang theo dõi trận đấu..."))
        self.assertIsNone(tr.observe("🖱 Click 'Thử Lại'..."))
        self.assertIsNone(tr.observe("❌ Trận đấu THẤT BẠI (Lần thứ 2/5 liên tiếp)!"))
        self.assertIsNone(tr.observe("⚠️ Mất cửa sổ game AFK Journey, tạm dừng thao tác để tránh click nhầm..."))
        self.assertIsNotNone(tr.observe("⚠️ Không tìm thấy nút 'Sao chép', nhấn ESC."))

    def test_slugify(self):
        self.assertEqual(slugify("⚠️ Cửa sổ game đã bị che (12, 34)"), "cua_so_game_da_bi_che")
        self.assertEqual(slugify("Đóng", 2), "do")


class TestBotEngineIssueBundle(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="afk_issue_")
        self.eng = bot_engine.BotEngine()
        self.eng.debugSnap = DebugSnapshotter(baseDir=self.tmp, minInterval=0, enabled=True)
        frame = np.full((120, 160, 3), 60, dtype=np.uint8)
        self.eng.captureGameScreen = lambda: (frame, 5, 6, (5, 6, 160, 120))
        self.eng.isGameForeground = lambda: True
        self.eng.ctrl.cursorPos = lambda: (1, 2)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _jsons(self):
        out = []
        for f in sorted(os.listdir(self.tmp)):
            if f.endswith(".json"):
                with open(os.path.join(self.tmp, f), encoding="utf-8") as fh:
                    out.append((f, json.load(fh)))
        return out

    def test_repeated_warning_saves_bundle_once_at_threshold(self):
        self.eng._log("🖱 Click 'Chiến Đấu Tự Động'...")
        for i in range(config.ISSUE_REPEAT_THRESHOLD):
            self.eng._log(f"⚠️ Click xong nhưng màn hình không đổi ({i})")
        files = self._jsons()
        self.assertEqual(len(files), 1)
        name, meta = files[0]
        self.assertIn("repeat_click_xong_nhung_man_hinh_khong_doi", name)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, name[:-5] + ".png")))
        self.assertEqual(meta["extra"]["count"], config.ISSUE_REPEAT_THRESHOLD)
        self.assertEqual(meta["extra"]["cursor"], [1, 2])
        self.assertTrue(any("Chiến Đấu Tự Động" in line for line in meta["extra"]["recentLogs"]))
        self.assertTrue(any("📸 Lỗi lặp lại" in line for line in self.eng.recentLogs))

    def test_crash_saves_bundle_with_traceback(self):
        orig = bot_engine.run_auto_afk

        def boom(_):
            raise RuntimeError("OCR crash")

        bot_engine.run_auto_afk = boom
        try:
            import logging
            logging.disable(logging.CRITICAL)
            self.eng._state_auto_afk()
        finally:
            logging.disable(logging.NOTSET)
            bot_engine.run_auto_afk = orig
        crash = [m for n, m in self._jsons() if "crash" in n]
        self.assertEqual(len(crash), 1)
        self.assertIn("RuntimeError: OCR crash", crash[0]["extra"]["traceback"])

    def test_bundle_without_image_still_saves_json(self):
        self.eng.captureGameScreen = lambda: (None, 0, 0, None)
        path = self.eng.saveIssueBundle("crash", "no window", tracebackText="tb")
        self.assertTrue(path and path.endswith(".json"))


if __name__ == "__main__":
    unittest.main()
