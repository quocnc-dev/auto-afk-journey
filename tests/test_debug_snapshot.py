"""Unit tests cho debug snapshot (lưu ảnh + OCR khi kẹt) và việc tách log test khỏi log thật."""

import json
import logging
import os
import shutil
import tempfile
import unittest

import numpy as np

import config
from modules import auto_afk
from modules.debug_snapshot import DebugSnapshotter, saveSnapshot
from ocr_engine import OcrEngine, OcrItem, normalizeText
from tests.test_ocr_and_logic import MockBot


def _item(raw: str) -> OcrItem:
    norm = normalizeText(raw)
    return OcrItem(raw, norm, norm.replace(" ", ""), 0.9, 10, 20, 110, 44)


class TestDebugSnapshot(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="afk_debug_")
        self.screen = np.full((120, 160, 3), 80, dtype=np.uint8)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _files(self):
        return sorted(os.listdir(self.tmp))

    def test_saves_png_and_json_with_ocr_items(self):
        snap = DebugSnapshotter(baseDir=self.tmp, minInterval=0, enabled=True)
        path = snap.save("Unknown Screen!", self.screen, [_item("Chiến Đấu")], rect=(0, 0, 160, 120), extra={"k": 1})
        self.assertTrue(path and os.path.isfile(path))
        self.assertTrue(path.endswith("_unknown_screen.png"))
        with open(path[:-4] + ".json", encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["rect"], [0, 0, 160, 120])
        self.assertEqual(meta["items"][0]["raw"], "Chiến Đấu")
        self.assertEqual(meta["items"][0]["norm"], "chien dau")
        self.assertEqual(meta["extra"], {"k": 1})

    def test_rate_limit_per_reason(self):
        snap = DebugSnapshotter(baseDir=self.tmp, minInterval=3600, enabled=True)
        self.assertIsNotNone(snap.save("a", self.screen))
        self.assertIsNone(snap.save("a", self.screen))
        self.assertIsNotNone(snap.save("b", self.screen))
        self.assertEqual(len(self._files()), 4)

    def test_prunes_oldest(self):
        snap = DebugSnapshotter(baseDir=self.tmp, maxSnapshots=2, minInterval=0, enabled=True)
        for i in range(4):
            snap.save(f"r{i}", self.screen)
        files = self._files()
        self.assertEqual(len(files), 4)
        self.assertTrue(any("r3" in f for f in files))
        self.assertFalse(any("r0" in f for f in files))

    def test_disabled_or_empty_screen_is_noop(self):
        self.assertIsNone(DebugSnapshotter(baseDir=self.tmp, enabled=False).save("x", self.screen))
        self.assertIsNone(DebugSnapshotter(baseDir=self.tmp, enabled=True).save("x", None))
        self.assertEqual(self._files(), [])

    def test_write_error_never_raises(self):
        blocker = os.path.join(self.tmp, "file")
        open(blocker, "w").close()
        snap = DebugSnapshotter(baseDir=os.path.join(blocker, "sub"), minInterval=0, enabled=True)
        logging.disable(logging.CRITICAL)
        try:
            self.assertIsNone(snap.save("x", self.screen))
        finally:
            logging.disable(logging.NOTSET)

    def test_save_snapshot_without_snapshotter_is_noop(self):
        bot = MockBot(OcrEngine(), [])
        self.assertIsNone(saveSnapshot(bot, "x", self.screen))
        self.assertEqual(bot.logs, [])

    def test_auto_afk_snapshots_unknown_screen_once_per_streak(self):
        frames = [np.zeros((720, 1280, 3), dtype=np.uint8)] * (config.DEBUG_UNKNOWN_STREAK + 3)
        bot = MockBot(OcrEngine(), frames)
        bot.debugSnap = DebugSnapshotter(baseDir=self.tmp, minInterval=0, enabled=True)
        origWait = auto_afk._wait
        auto_afk._wait = lambda b, s: not b._stop_event.is_set()
        try:
            auto_afk.run_auto_afk(bot)
        finally:
            auto_afk._wait = origWait
        pngs = [f for f in self._files() if f.endswith(".png")]
        self.assertEqual(len(pngs), 1)
        self.assertIn("unknown_screen", pngs[0])
        self.assertTrue(any("📸" in m for m in bot.logs))


class TestLogIsolation(unittest.TestCase):

    def test_importing_main_does_not_attach_file_handler(self):
        import main  # noqa: F401
        handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)]
        self.assertFalse(any(os.path.abspath(h.baseFilename) == os.path.abspath(config.LOG_FILE) for h in handlers))

    def test_log_dir_env_override(self):
        orig = os.environ.get("AFK_BOT_LOG_DIR")
        os.environ["AFK_BOT_LOG_DIR"] = "/tmp/afk-test-logs"
        try:
            self.assertEqual(config._resolveLogDir(), "/tmp/afk-test-logs")
        finally:
            if orig is None:
                os.environ.pop("AFK_BOT_LOG_DIR", None)
            else:
                os.environ["AFK_BOT_LOG_DIR"] = orig


if __name__ == "__main__":
    unittest.main()
