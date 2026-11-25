"""
Quản lý cửa sổ game AFK Journey đa nền tảng (Windows dùng pywin32, macOS dùng Quartz).
Giúp phát hiện game đang mở, lấy tọa độ vùng client thực tế trên màn hình
và loại trừ chính cửa sổ của tool bot.
"""

import os
import sys
import logging
import subprocess

logger = logging.getLogger("AFK_Bot.Window")

if sys.platform == "win32":
    import win32gui
    import win32con
    import win32process
elif sys.platform == "darwin":
    import Quartz


def _findWindowWin32(titleKeyword: str) -> int | None:
    """Tìm HWND trên Windows theo tiêu đề cửa sổ, bỏ qua cửa sổ cùng PID."""
    currentPid = os.getpid()
    keywordLower = titleKeyword.strip().lower()
    exactMatches = []
    partialMatches = []

    def enumHandler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        _, windowPid = win32process.GetWindowThreadProcessId(hwnd)
        if windowPid == currentPid:
            return
        titleLower = title.strip().lower()
        if titleLower == keywordLower:
            exactMatches.append(hwnd)
        elif keywordLower in titleLower:
            partialMatches.append(hwnd)

    win32gui.EnumWindows(enumHandler, None)
    if exactMatches:
        return exactMatches[0]
    if partialMatches:
        return partialMatches[0]
    return None


def _getMacWindows() -> list[dict]:
    """Lấy danh sách cửa sổ đang hiển thị trên macOS qua Quartz."""
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    windowList = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    return list(windowList) if windowList else []


def _findWindowMac(titleKeyword: str) -> int | None:
    """Tìm CGWindowNumber trên macOS theo tên app hoặc tiêu đề cửa sổ."""
    currentPid = os.getpid()
    keywordLower = titleKeyword.strip().lower()
    keywordCompact = keywordLower.replace(" ", "")
    exactMatches = []
    partialMatches = []

    for win in _getMacWindows():
        if win.get("kCGWindowOwnerPID") == currentPid:
            continue
        layer = win.get("kCGWindowLayer", 0)
        if layer != 0:
            continue
        ownerName = str(win.get("kCGWindowOwnerName", "") or "").strip()
        winTitle = str(win.get("kCGWindowName", "") or "").strip()
        bounds = win.get("kCGWindowBounds", {})
        if bounds.get("Width", 0) < 200 or bounds.get("Height", 0) < 200:
            continue

        winId = win.get("kCGWindowNumber")
        ownerCompact = ownerName.lower().replace(" ", "")
        titleCompact = winTitle.lower().replace(" ", "")
        if ownerCompact == keywordCompact or titleCompact == keywordCompact:
            exactMatches.append(winId)
        elif keywordCompact in ownerCompact or keywordCompact in titleCompact:
            partialMatches.append(winId)

    if exactMatches:
        return exactMatches[0]
    if partialMatches:
        return partialMatches[0]
    return None


def findGameWindow(titleKeyword: str) -> int | None:
    """Tìm ID cửa sổ game trên hệ điều hành hiện tại."""
    if sys.platform == "win32":
        return _findWindowWin32(titleKeyword)
    if sys.platform == "darwin":
        return _findWindowMac(titleKeyword)
    return None


def isWindowReady(hwnd: int | None) -> bool:
    """Kiểm tra cửa sổ game còn tồn tại và đang hiển thị."""
    if not hwnd:
        return False
    if sys.platform == "win32":
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        return not win32gui.IsIconic(hwnd)
    if sys.platform == "darwin":
        return any(w.get("kCGWindowNumber") == hwnd for w in _getMacWindows())
    return False


def getClientRectScreen(hwnd: int, minWidth: int = 200, minHeight: int = 200) -> tuple[int, int, int, int] | None:
    """
    Lấy vùng client thực tế của cửa sổ game theo tọa độ logic: (left, top, width, height).
    Trả về None nếu cửa sổ bị thu nhỏ hoặc kích thước quá nhỏ.
    """
    if not hwnd:
        return None
    if sys.platform == "win32":
        if not isWindowReady(hwnd):
            return None
        try:
            rect = win32gui.GetClientRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width < minWidth or height < minHeight:
                return None
            left, top = win32gui.ClientToScreen(hwnd, (0, 0))
            return (left, top, width, height)
        except Exception as exc:
            logger.debug(f"Không lấy được client rect của hwnd={hwnd}: {exc}")
            return None

    if sys.platform == "darwin":
        for win in _getMacWindows():
            if win.get("kCGWindowNumber") == hwnd:
                bounds = win.get("kCGWindowBounds", {})
                width = int(bounds.get("Width", 0))
                height = int(bounds.get("Height", 0))
                if width < minWidth or height < minHeight:
                    return None
                left = int(bounds.get("X", 0))
                top = int(bounds.get("Y", 0))
                return (left, top, width, height)
    return None


def focusGameWindow(hwnd: int) -> bool:
    """Khôi phục cửa sổ nếu đang thu nhỏ và đưa cửa sổ game lên trên cùng."""
    if not hwnd:
        return False
    if sys.platform == "win32":
        if not win32gui.IsWindow(hwnd):
            return False
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as exc:
            logger.debug(f"Không thể focus cửa sổ game hwnd={hwnd}: {exc}")
            return False

    if sys.platform == "darwin":
        for win in _getMacWindows():
            if win.get("kCGWindowNumber") == hwnd:
                ownerName = str(win.get("kCGWindowOwnerName", "") or "").strip()
                if ownerName:
                    try:
                        subprocess.run(
                            ["osascript", "-e", f'tell application "{ownerName}" to activate'],
                            check=False,
                            capture_output=True,
                        )
                        return True
                    except Exception as exc:
                        logger.debug(f"Không thể focus app macOS '{ownerName}': {exc}")
    return False
