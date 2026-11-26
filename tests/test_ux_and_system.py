"""Unit tests cho KeepAwake, GlobalStopHotkey, Webhook, tự dừng khi kẹt 2 nhánh và tiến độ UI."""

import json
import os
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import numpy as np

import config
from modules import auto_afk, system_helpers
from modules.loop_state import AfkLoopState
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot


def _ocrItem(raw: str, cx: int, cy: int, w: int = 120, h: int = 24) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.95, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


class _DummyResp:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestSystemHelpers(unittest.TestCase):
    """Kiểm thử KeepAwake, GlobalStopHotkey, Webhook và đọc AFK_BOT_WEBHOOK_URL."""

    def test_keep_awake_darwin_and_win32(self):
        terminated = []

        class FakeProc:
            def poll(self):
                return None

            def terminate(self):
                terminated.append("terminate")

            def wait(self, timeout=None):
                terminated.append("wait")

        kaMac = system_helpers.KeepAwake(platform="darwin")
        with patch("modules.system_helpers.subprocess.Popen", return_value=FakeProc()) as popenMock:
            self.assertTrue(kaMac.start())
            self.assertTrue(kaMac.start())  # idempotent
            self.assertEqual(popenMock.call_count, 1)
            kaMac.stop()
            self.assertEqual(terminated, ["terminate", "wait"])

        calls = []
        fakeKernel = types.SimpleNamespace(SetThreadExecutionState=lambda flags: calls.append(flags))
        fakeWindll = types.SimpleNamespace(kernel32=fakeKernel)
        kaWin = system_helpers.KeepAwake(platform="win32")
        with patch.object(system_helpers.ctypes, "windll", fakeWindll, create=True):
            self.assertTrue(kaWin.start())
            kaWin.stop()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1], system_helpers._ES_CONTINUOUS)

    def test_global_stop_hotkey_triggers_once_on_press(self):
        triggered = threading.Event()
        states = [False, True, True]

        def checkFn():
            return states.pop(0) if states else False

        hotkey = system_helpers.GlobalStopHotkey(triggered.set, pollInterval=0.02, keyCheckFn=checkFn)
        hotkey.start()
        try:
            self.assertTrue(triggered.wait(timeout=1.0))
        finally:
            hotkey.stop()

    def test_webhook_validation_and_payload(self):
        self.assertFalse(system_helpers.sendWebhookNotification("T", "M", webhookUrl="http://insecure.local/hook"))

        sent = []

        def fakeUrlopen(req, timeout=None, context=None):
            sent.append((req.full_url, json.loads(req.data.decode("utf-8"))))
            return _DummyResp()

        with patch("modules.system_helpers.urllib.request.urlopen", side_effect=fakeUrlopen):
            okDiscord = system_helpers.sendWebhookNotification(
                "AFK Bot", "Hoàn tất", webhookUrl="https://discord.com/api/webhooks/123/abc"
            )
            okGeneric = system_helpers.sendWebhookNotification(
                "AFK Bot", "Dừng", webhookUrl="https://example.com/hook"
            )
        self.assertTrue(okDiscord)
        self.assertTrue(okGeneric)
        self.assertEqual(sent[0][1], {"content": "**AFK Bot**\nHoàn tất"})
        self.assertEqual(sent[1][1]["text"], "AFK Bot\nDừng")

    def test_webhook_url_from_env_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            envPath = os.path.join(tmp, ".env.local")
            with open(envPath, "w", encoding="utf-8") as f:
                f.write('AFK_BOT_WEBHOOK_URL="https://discord.com/api/webhooks/9/z"\n')
            origCwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch.dict(os.environ, {"AFK_BOT_WEBHOOK_URL": ""}):
                    self.assertEqual(config.getWebhookUrl(), "https://discord.com/api/webhooks/9/z")
            finally:
                os.chdir(origCwd)


class TestStuckAutoStopAndProgress(unittest.TestCase):
    """Kiểm thử ngưỡng thua tùy chỉnh, mode khởi đầu, tiến độ UI và tự dừng khi kẹt 2 nhánh."""

    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrEngine()

    def test_loop_state_summary_and_stuck_counter(self):
        st = AfkLoopState(preferChallenge=True)
        self.assertEqual(st.summaryText(5), "Huyễn Linh • +0 ải • 0/5")
        st.onModeSwitched()
        st.preferChallenge = False
        st.onModeSwitched()
        self.assertEqual(st.stuckModeSwitches, 2)
        self.assertTrue(st.isStuckBothModes(2))
        st.onVictory(3)
        self.assertEqual((st.stagesCleared, st.stuckModeSwitches), (3, 0))
        self.assertEqual(st.summaryText(3), "Thường • +3 ải • 0/3")

    def _runAuto(self, scenes, *, failThreshold=5, preferChallengeStart=True, maxStuckSwitches=0):
        frame = np.zeros((934, 676, 3), dtype=np.uint8)
        bot = MockBot(self.ocr, [frame] * len(scenes))
        bot.failThreshold = failThreshold
        bot.preferChallengeStart = preferChallengeStart
        bot.maxStuckSwitches = maxStuckSwitches
        progressLog = []
        bot.progress_callback = progressLog.append
        queue = list(scenes)
        origScan, origWait = bot.ocr.scanImage, auto_afk._wait
        bot.ocr.scanImage = lambda img, originX=0, originY=0, roi=None: queue.pop(0) if queue else []
        auto_afk._wait = lambda b, s: True
        try:
            ok = auto_afk.run_auto_afk(bot)
        finally:
            bot.ocr.scanImage, auto_afk._wait = origScan, origWait
        return ok, bot, progressLog

    def test_auto_stops_when_stuck_both_modes_and_emits_progress(self):
        retry = [_ocrItem("Thử Lại", 450, 820)]
        autoBtn = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
        lobby = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]

        # Ngưỡng thua = 2, maxStuckSwitches = 2: thua 2 ở Thường -> sang Huyễn Linh -> thua 2 -> tự dừng
        scenes = [retry, autoBtn, retry, lobby, retry, autoBtn, retry, lobby]
        ok, bot, progressLog = self._runAuto(
            scenes, failThreshold=2, preferChallengeStart=False, maxStuckSwitches=2
        )
        self.assertTrue(ok)
        self.assertIn("Kẹt cả 2 chế độ", getattr(bot, "lastStopReason", ""))
        self.assertTrue(progressLog[0].startswith("Thường • +0 ải • 0/2"))
        self.assertTrue(any("Huyễn Linh" in p for p in progressLog))

    def test_victory_resets_stuck_switches_and_counts_cleared_stages(self):
        retry = [_ocrItem("Thử Lại", 450, 820)]
        autoBtn = [_ocrItem("Chiến Đấu Tự Động", 500, 820)]
        victory = [_ocrItem("Đã Tăng Phần Thưởng AFK", 338, 250)]
        lobby = [_ocrItem("Thách Đấu Huyền Linh SV", 180, 800), _ocrItem("Chiến Đấu", 510, 800)]

        # Đổi mode 1 lần -> thắng (+1 ải, reset stuck) -> đổi mode lần nữa (chỉ 1 < max=2) -> KHÔNG tự dừng
        scenes = [retry, autoBtn, retry, victory, retry, autoBtn, retry, lobby]
        ok, bot, progressLog = self._runAuto(
            scenes, failThreshold=2, preferChallengeStart=True, maxStuckSwitches=2
        )
        self.assertTrue(ok)
        self.assertEqual(getattr(bot, "lastStopReason", ""), "")
        self.assertTrue(any("+1 ải" in p for p in progressLog))
        self.assertEqual(bot.ctrl.clicks[-1], (180, 800))


if __name__ == "__main__":
    unittest.main()
