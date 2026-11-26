"""Unit tests cho In-App Updater: so sánh version, metadata, zip-slip và script cài đặt."""

import io
import json
import os
import ssl
import tempfile
import unittest
import zipfile

import config
import updater


class _FakeResponse:
    def __init__(self, payload: bytes, headers: dict | None = None):
        self._buf = io.BytesIO(payload)
        self.headers = headers or {"Content-Length": str(len(payload))}

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestUpdater(unittest.TestCase):
    """Kiểm thử logic updater không cần mạng thật."""

    def test_version_parsing_and_comparison(self):
        self.assertEqual(updater.parseVersionKey("v1.0.0-build.12"), (1, 0, 0, 12))
        self.assertEqual(updater.parseVersionKey("1.2.3"), (1, 2, 3, 0))
        self.assertTrue(updater.isNewerRelease("v1.0.0-build.9", "v1.0.0-build.10"))
        self.assertTrue(updater.isNewerRelease("v1.0.0", "v1.0.0-build.6"))
        self.assertTrue(updater.isNewerRelease("v1.0.0-build.20", "v1.0.1"))
        self.assertFalse(updater.isNewerRelease("v1.0.0-build.10", "v1.0.0-build.10"))
        self.assertFalse(updater.isNewerRelease("v1.0.0-build.10", "v1.0.0-build.9"))

    def test_get_current_build_info_reads_json_and_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            origBundle = config.BUNDLE_DIR
            config.BUNDLE_DIR = tmp
            try:
                fallback = updater.getCurrentBuildInfo()
                self.assertEqual(fallback["tag"], f"v{config.APP_VERSION}")

                with open(os.path.join(tmp, config.BUILD_INFO_FILENAME), "w", encoding="utf-8") as f:
                    json.dump({"tag": "v1.0.0-build.15", "run_number": 15}, f)
                info = updater.getCurrentBuildInfo()
                self.assertEqual(info["tag"], "v1.0.0-build.15")
                self.assertEqual(updater.getDisplayVersion(), "v1.0.0-build.15")
            finally:
                config.BUNDLE_DIR = origBundle

    def test_check_for_update_selects_platform_asset(self):
        expectedAsset = updater.getPlatformAssetName()
        if not expectedAsset:
            self.skipTest("Platform không dùng asset release mặc định")

        fakePayload = json.dumps({
            "tag_name": "v1.0.0-build.999",
            "body": "Fix auto progress",
            "html_url": "https://github.com/quocnc-dev/auto-afk-journey/releases/tag/v1.0.0-build.999",
            "assets": [
                {"name": "other.zip", "browser_download_url": "https://example.com/other.zip", "size": 10},
                {"name": expectedAsset, "browser_download_url": "https://example.com/app.zip", "size": 2048},
            ],
        }).encode("utf-8")

        origOpen = updater.urllib.request.urlopen
        updater.urllib.request.urlopen = lambda req, timeout=None, context=None: _FakeResponse(fakePayload)
        try:
            info = updater.checkForUpdate()
        finally:
            updater.urllib.request.urlopen = origOpen

        self.assertIsInstance(updater.buildSslContext(), ssl.SSLContext)

        self.assertTrue(info.hasUpdate)
        self.assertEqual(info.latestTag, "v1.0.0-build.999")
        self.assertEqual(info.downloadUrl, "https://example.com/app.zip")
        self.assertEqual(info.assetSize, 2048)

    def test_zip_slip_rejected_and_payload_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            badZip = os.path.join(tmp, "bad.zip")
            with zipfile.ZipFile(badZip, "w") as zf:
                zf.writestr("../../evil.txt", "boom")
            with self.assertRaises(ValueError):
                updater.validateZipEntries(badZip, os.path.join(tmp, "out"))

            winExtract = os.path.join(tmp, "win")
            os.makedirs(os.path.join(winExtract, "AFKJourneyBot"), exist_ok=True)
            with open(os.path.join(winExtract, "AFKJourneyBot", "AFKJourneyBot.exe"), "wb") as f:
                f.write(b"MZ")
            self.assertEqual(
                updater.findExtractedPayload(winExtract, platform="win32"),
                os.path.join(winExtract, "AFKJourneyBot"),
            )

            macExtract = os.path.join(tmp, "mac")
            os.makedirs(os.path.join(macExtract, "AFKJourneyBot.app", "Contents", "MacOS"), exist_ok=True)
            self.assertEqual(
                updater.findExtractedPayload(macExtract, platform="darwin"),
                os.path.join(macExtract, "AFKJourneyBot.app"),
            )

    def test_update_scripts_contain_expected_commands(self):
        winScript = updater.buildWindowsUpdateScript(1234, r"C:\tmp\src", r"C:\app", r"C:\tmp\work")
        self.assertIn("robocopy", winScript)
        self.assertIn("AFKJourneyBot.exe", winScript)
        self.assertIn("1234", winScript)

        macScript = updater.buildMacUpdateScript(5678, "/tmp/src/AFKJourneyBot.app", "/Applications/AFKJourneyBot.app", "/tmp/work")
        self.assertIn("/usr/bin/ditto", macScript)
        self.assertIn("kill -0 5678", macScript)
        self.assertIn("open /Applications/AFKJourneyBot.app", macScript)

    def test_private_repo_token_read_from_env_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            envPath = os.path.join(tmp, ".env.local")
            with open(envPath, "w", encoding="utf-8") as f:
                f.write("AFK_BOT_GITHUB_TOKEN=ghp_test123\n")
            origCwd = os.getcwd()
            origEnv = os.environ.pop("AFK_BOT_GITHUB_TOKEN", None)
            os.chdir(tmp)
            try:
                self.assertEqual(config.getGithubUpdateToken(), "ghp_test123")
            finally:
                os.chdir(origCwd)
                if origEnv is not None:
                    os.environ["AFK_BOT_GITHUB_TOKEN"] = origEnv


if __name__ == "__main__":
    unittest.main()
