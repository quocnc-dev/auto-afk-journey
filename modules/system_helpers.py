"""Tiện ích hệ thống khi bot chạy: chống tắt màn hình, phím dừng toàn cục (F9) và thông báo."""

import ctypes
import json
import logging
import os
import subprocess
import sys
import threading
import urllib.request
from typing import Callable

import config
import updater

logger = logging.getLogger("AFK_Bot.System")

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002


class KeepAwake:
    """Giữ màn hình không tự tắt trong lúc bot đang chạy (macOS caffeinate / Windows ExecutionState)."""

    def __init__(self, platform: str | None = None):
        self._platform = platform or sys.platform
        self._proc = None
        self._active = False

    def start(self) -> bool:
        """Bật chế độ chống tắt màn hình; an toàn nếu gọi lặp lại."""
        if self._active:
            return True
        try:
            if self._platform == "darwin":
                self._proc = subprocess.Popen(
                    ["caffeinate", "-d", "-i", "-w", str(os.getpid())],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._active = True
            elif self._platform == "win32":
                flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
                ctypes.windll.kernel32.SetThreadExecutionState(flags)
                self._active = True
        except Exception as exc:
            logger.debug(f"Không bật được chống ngủ màn hình: {exc}")
            self._proc = None
            self._active = False
        return self._active

    def stop(self):
        """Tắt chế độ chống ngủ màn hình và dọn subprocess nếu có."""
        proc = self._proc
        self._proc = None
        wasActive = self._active
        self._active = False
        try:
            if proc is not None:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        proc.kill()
            elif wasActive and self._platform == "win32":
                ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        except Exception as exc:
            logger.debug(f"Lỗi khi tắt chống ngủ màn hình: {exc}")


def isStopHotkeyPressed() -> bool:
    """Kiểm tra phím tắt dừng khẩn cấp (F9) đang được nhấn hay không."""
    try:
        if sys.platform == "darwin":
            import Quartz
            return bool(
                Quartz.CGEventSourceKeyState(
                    Quartz.kCGEventSourceStateCombinedSessionState,
                    config.STOP_HOTKEY_MAC_KEYCODE,
                )
            )
        if sys.platform == "win32":
            return bool(ctypes.windll.user32.GetAsyncKeyState(config.STOP_HOTKEY_WIN_VK) & 0x8000)
    except Exception:
        return False
    return False


class GlobalStopHotkey:
    """Theo dõi phím dừng toàn cục trên luồng nền khi bot đang chạy."""

    def __init__(
        self,
        onTrigger: Callable[[], None],
        pollInterval: float = config.HOTKEY_POLL_INTERVAL,
        keyCheckFn: Callable[[], bool] | None = None,
    ):
        self._onTrigger = onTrigger
        self._pollInterval = max(0.02, float(pollInterval))
        self._keyCheckFn = keyCheckFn or isStopHotkeyPressed
        self._stopEvent = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stopEvent.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="StopHotkey")
        self._thread.start()

    def stop(self):
        self._stopEvent.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None

    def _loop(self):
        wasDown = False
        while not self._stopEvent.is_set():
            isDown = False
            try:
                isDown = bool(self._keyCheckFn())
            except Exception:
                isDown = False
            if isDown and not wasDown:
                try:
                    self._onTrigger()
                except Exception as exc:
                    logger.debug(f"Lỗi callback phím tắt dừng: {exc}")
                return
            wasDown = isDown
            self._stopEvent.wait(self._pollInterval)


def _escapeAppleScript(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def sendDesktopNotification(title: str, message: str) -> bool:
    """Gửi thông báo hệ thống nhẹ nhàng khi bot xong hoặc gặp lỗi."""
    try:
        if sys.platform == "darwin":
            script = f'display notification "{_escapeAppleScript(message)}" with title "{_escapeAppleScript(title)}"'
            subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            return True
        if sys.platform == "win32":
            safeTitle = (title or "").replace("'", "''").replace("\r", " ").replace("\n", " ")
            safeMsg = (message or "").replace("'", "''").replace("\r", " ").replace("\n", " ")
            ps = (
                "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
                f"$n.ShowBalloonTip(4000,'{safeTitle}','{safeMsg}',[System.Windows.Forms.ToolTipIcon]::Info);"
                "Start-Sleep -Milliseconds 4200;$n.Visible=$false;$n.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
    except Exception as exc:
        logger.debug(f"Không gửi được desktop notification: {exc}")
    return False


def sendWebhookNotification(title: str, message: str, webhookUrl: str | None = None) -> bool:
    """Gửi thông báo qua HTTPS webhook (Discord/Telegram) nếu đã cấu hình AFK_BOT_WEBHOOK_URL."""
    url = (webhookUrl if webhookUrl is not None else config.getWebhookUrl()).strip()
    if not url.startswith("https://"):
        return False
    isDiscord = "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url
    payload = {"content": f"**{title}**\n{message}"} if isDiscord else {
        "text": f"{title}\n{message}",
        "content": f"**{title}**\n{message}",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "AFKJourneyBot-Notifier"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.WEBHOOK_TIMEOUT, context=updater.buildSslContext()):
            return True
    except Exception as exc:
        logger.warning(f"Không gửi được webhook thông báo: {exc}")
        return False


class BotSystemGuard:
    """Điều phối KeepAwake, Hotkey F9 và Thông báo kết thúc cho BotEngine."""

    def __init__(self):
        self._keepAwake = KeepAwake()
        self._hotkey: GlobalStopHotkey | None = None

    def start(self, keepAwake: bool, onHotkeyStop: Callable[[], None]):
        if keepAwake:
            self._keepAwake.start()
        self._hotkey = GlobalStopHotkey(onHotkeyStop)
        self._hotkey.start()

    def stop(self):
        if self._hotkey is not None:
            self._hotkey.stop()
            self._hotkey = None
        self._keepAwake.stop()

    def notifyFinish(self, stateName: str, reason: str, enabled: bool):
        if not enabled or stateName not in ("DONE", "ERROR"):
            return
        if stateName == "DONE":
            title = "AFK Bot — Đã hoàn tất"
            body = reason or "Nhiệm vụ Auto AFK đã dừng an toàn."
        else:
            title = "AFK Bot — Gặp lỗi"
            body = reason or "Bot dừng do lỗi hoặc timeout. Kiểm tra tab Log để xem chi tiết."
        sendDesktopNotification(title, body)
        sendWebhookNotification(title, body)
