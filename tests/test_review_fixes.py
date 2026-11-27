"""Unit tests kiểm chứng toàn bộ các lỗi đã phát hiện trong đợt review."""

import os
import subprocess
import types
import unittest
import urllib.request
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

import config
import ui_updater
import updater
from modules import auto_afk, system_helpers, team_copy
from modules.afk_detectors import findPauseAutoConfirmCancel
from modules.loop_state import AfkLoopState
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_defeat_streak import STATS
from tests.test_ocr_and_logic import MockBot


def _ocrItem(raw: str, cx: int, cy: int, w: int = 120, h: int = 24) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


class TestReviewFixes(unittest.TestCase):
    """Kiểm thử 7 lỗi từ báo cáo review."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_retry_refused_click_does_not_inflate_defeat_streak(self):
        retry = [_ocrItem("Thử Lại", 450, 820)]
        autoBtn = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
        lobby = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [frame] * 9)
        bot.failThreshold = 3
        blocked = [True, True, False, True, False]
        bot.canInteractAt = lambda x, y, expectedRect=None: not blocked.pop(0) if blocked else True
        # Chuỗi: 3 lần thấy retry (2 lần đầu bị hủy click do mất focus) -> vào trận -> thua thật lần 2 -> về sảnh
        scenes = [retry, retry, retry, autoBtn, retry, autoBtn, lobby]
        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: scenes.pop(0) if scenes else []
        auto_afk._wait = lambda b, s: True
        try:
            self.assertTrue(auto_afk.run_auto_afk(bot))
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        # Chỉ thua 2 trận thật (< ngưỡng 3) -> vẫn giữ Huyễn Linh (180, 800), không bị nhảy mode sớm
        self.assertEqual(bot.ctrl.clicks[-1], (180, 800))
        self.assertFalse(any("Đạt mốc" in m or "Chuyển chế độ" in m for m in bot.logs))

    def test_team_rotation_stops_when_arrow_disappears_and_wraps(self):
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        rect = (0, 0, 676, 934)
        bot = MockBot(self.ocr, [])
        bot.peekScreen = lambda: frame
        st = AfkLoopState(teamCursor=3)  # Đáng lẽ bấm 3 lần, nhưng chỉ có 2 đội (sau click 1 không còn '>')
        arrowSeq = [(600, 500), None]
        origArrow, origScan, origWait = team_copy.findNextTeamArrow, auto_afk._scanGame, auto_afk._wait
        team_copy.findNextTeamArrow = lambda *a, **k: arrowSeq.pop(0) if arrowSeq else None
        auto_afk._scanGame = lambda b: (frame, 0, 0, rect, STATS)
        auto_afk._wait = lambda b, s: True
        try:
            team_copy.applyStatsModalTeam(bot, frame, 0, 0, rect, STATS, st=st)
        finally:
            team_copy.findNextTeamArrow, auto_afk._scanGame, auto_afk._wait = origArrow, origScan, origWait
        self.assertEqual(bot.ctrl.clicks, [(600, 500), (380, 880)])
        self.assertEqual(st.teamCursor, 0)
        self.assertTrue(any("team cuối" in m for m in bot.logs))

    def test_lobby_focus_loss_does_not_trigger_fallback_switch(self):
        lobbyBoth = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [frame] * 4)
        allow = [False, False, False, True]
        bot.canInteractAt = lambda x, y, expectedRect=None: allow.pop(0) if allow else True
        scenes = [lobbyBoth, lobbyBoth, lobbyBoth, lobbyBoth]
        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: scenes.pop(0) if scenes else []
        auto_afk._wait = lambda b, s: True
        try:
            self.assertTrue(auto_afk.run_auto_afk(bot))
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        # Lần 4 mới có focus: vẫn ưu tiên Huyễn Linh (180, 800), không bị fallback sang Thường
        self.assertEqual(bot.ctrl.clicks, [(180, 800)])
        self.assertFalse(any("fallback" in m for m in bot.logs))

    def test_updater_utf8_script_redirect_strip_and_progress_throttle(self):
        winScript = updater.buildWindowsUpdateScript(123, r"C:\Người Dùng\App", r"C:\App", r"C:\Temp\w")
        self.assertIn("chcp 65001 >NUL", winScript)

        handler = updater._NoAuthRedirectHandler()
        origReq = urllib.request.Request(
            "https://api.github.com/repos/a/b/releases/assets/1",
            headers={"Authorization": "Bearer secret_tok", "Accept": "application/octet-stream"},
        )
        sameHost = handler.redirect_request(origReq, None, 302, "Found", {}, "https://api.github.com/other")
        self.assertIn("Authorization", sameHost.headers)
        crossHost = handler.redirect_request(origReq, None, 302, "Found", {}, "https://objects.githubusercontent.com/file.zip")
        self.assertFalse(any(k.lower() == "authorization" for k in crossHost.headers))
        self.assertFalse(any(k.lower() == "authorization" for k in crossHost.unredirected_hdrs))

        emitted = []
        clock = [0.0]
        with patch("ui_updater.time.monotonic", side_effect=lambda: clock[0]):
            cb = ui_updater.makeProgressThrottler(lambda d, t: emitted.append((d, t)), minInterval=0.2)
            for i in range(1, 101):
                clock[0] += 0.01
                cb(i, 100)
        self.assertLess(len(emitted), 15)
        self.assertEqual(emitted[-1], (100, 100))

    def test_pause_popup_ignores_far_edge_x_and_uses_green_fallback(self):
        img = cv2.imread(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pause_auto_prompt_678x936.jpg"))
        items = self.ocr.scanImage(img, originX=0, originY=0)
        # Bỏ X thật, thay bằng chữ 'x' giả ở sát mép trái màn hình
        itemsNoRealX = [it for it in items if it.normText.strip() not in ("x", "×")] + [_ocrItem("x", 30, 613, w=20, h=20)]
        bot = MockBot(self.ocr, [])
        pos = findPauseAutoConfirmCancel(bot, img, 0, 0, itemsNoRealX, auto_afk._findKey)
        self.assertIsNotNone(pos)
        self.assertGreater(pos[0], 250)  # không click vào (30, 613) ở mép trái

    def test_win32_notification_escapes_and_disposes_and_preview_is_threadsafe(self):
        popenCalls = []
        with patch.object(system_helpers.sys, "platform", "win32"), patch(
            "modules.system_helpers.subprocess.Popen",
            side_effect=lambda cmd, **kw: popenCalls.append((cmd, kw)),
        ):
            ok = system_helpers.sendDesktopNotification("Tiêu đề 'A'", "Nội dung 'B'\nDòng 2")
        self.assertTrue(ok)
        psCmd = popenCalls[0][0][-1]
        self.assertIn("''A''", psCmd)
        self.assertIn("''B'' Dòng 2", psCmd)
        self.assertIn("$n.Dispose()", psCmd)
        self.assertEqual(popenCalls[0][1].get("creationflags"), getattr(subprocess, "CREATE_NO_WINDOW", 0))

        import ui_tabs
        stopEv = system_helpers.threading.Event()
        afterCalls = []
        fakeApp = types.SimpleNamespace(
            _preview_active=True,
            _preview_gen=1,
            _preview_size=(320, 240),
            _update_preview_ui=lambda *a: None,
            preview_label=types.SimpleNamespace(
                winfo_width=lambda: (_ for _ in ()).throw(AssertionError("Tk winfo called off main thread")),
                winfo_height=lambda: (_ for _ in ()).throw(AssertionError("Tk winfo called off main thread")),
            ),
            after=lambda delay, fn, *args: (afterCalls.append((fn, args)), stopEv.set()),
        )
        fakeScreen = np.zeros((480, 640, 3), dtype=np.uint8)
        calls = [0]

        def capSideEffect():
            calls[0] += 1
            if calls[0] >= 3:
                stopEv.set()
            return fakeScreen

        with patch("ui_tabs.ScreenCapture") as capCls:
            capCls.return_value.capture_full.side_effect = capSideEffect
            ui_tabs.runPreviewWorker(fakeApp, stopEv, 1)
        self.assertEqual(len(afterCalls), 1)
        self.assertIsInstance(afterCalls[0][1][0], Image.Image)

    def test_default_github_repo_matches_origin(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AFK_BOT_GITHUB_REPO", None)
            import importlib
            importlib.reload(config)
            self.assertEqual(config.GITHUB_REPO, "betonamu/auto-afk-journey")


if __name__ == "__main__":
    unittest.main()
