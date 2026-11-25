"""
Quản lý cửa sổ game AFK Journey đa nền tảng (Windows dùng pywin32, macOS dùng Quartz).
Chỉ nhận diện đúng cửa sổ game (khớp chính xác tiêu đề, kiểm tra foreground và tọa độ click).
"""

import logging
import os
import subprocess
import sys

logger = logging.getLogger("AFK_Bot.Window")

if sys.platform == "win32":
    import win32con
    import win32gui
    import win32process
elif sys.platform == "darwin":
    import Quartz


def isExactGameTitle(title: str, titleKeyword: str) -> bool:
    """Chỉ khớp tiêu đề game chính xác (bỏ qua hoa thường và khoảng trắng)."""
    if not title or not titleKeyword:
        return False
    return title.strip().lower().replace(" ", "") == titleKeyword.strip().lower().replace(" ", "")


def _findWindowWin32(titleKeyword: str) -> int | None:
    """Tìm HWND trên Windows có tiêu đề khớp chính xác game, bỏ qua cửa sổ cùng PID."""
    currentPid = os.getpid()
    matches = []

    def enumHandler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not isExactGameTitle(title, titleKeyword):
            return
        _, windowPid = win32process.GetWindowThreadProcessId(hwnd)
        if windowPid == currentPid:
            return
        matches.append(hwnd)

    win32gui.EnumWindows(enumHandler, None)
    return matches[0] if matches else None


def _getMacWindows() -> list[dict]:
    """Lấy danh sách cửa sổ đang hiển thị trên macOS qua Quartz."""
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    windowList = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    return list(windowList) if windowList else []


def _findWindowMac(titleKeyword: str) -> int | None:
    """Tìm CGWindowNumber trên macOS có tên app/tiêu đề khớp chính xác game."""
    currentPid = os.getpid()
    for win in _getMacWindows():
        if win.get("kCGWindowOwnerPID") == currentPid or win.get("kCGWindowLayer", 0) != 0:
            continue
        ownerName = str(win.get("kCGWindowOwnerName", "") or "")
        winTitle = str(win.get("kCGWindowName", "") or "")
        bounds = win.get("kCGWindowBounds", {})
        if bounds.get("Width", 0) < 200 or bounds.get("Height", 0) < 200:
            continue
        if isExactGameTitle(ownerName, titleKeyword) or isExactGameTitle(winTitle, titleKeyword):
            return win.get("kCGWindowNumber")
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


def isWindowForeground(hwnd: int | None) -> bool:
    """Kiểm tra cửa sổ game có đang ở trên cùng (không bị cửa sổ khác che/chiếm focus)."""
    if not hwnd:
        return False
    if sys.platform == "win32":
        return isWindowReady(hwnd) and win32gui.GetForegroundWindow() == hwnd
    if sys.platform == "darwin":
        for win in _getMacWindows():
            if win.get("kCGWindowLayer", 0) != 0:
                continue
            bounds = win.get("kCGWindowBounds", {})
            if bounds.get("Width", 0) < 200 or bounds.get("Height", 0) < 200:
                continue
            return win.get("kCGWindowNumber") == hwnd
    return False


def getClientRectScreen(hwnd: int, minWidth: int = 200, minHeight: int = 200) -> tuple[int, int, int, int] | None:
    """Lấy vùng client thực tế của cửa sổ game theo tọa độ logic: (left, top, width, height)."""
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
                return (int(bounds.get("X", 0)), int(bounds.get("Y", 0)), width, height)
    return None


def isPointInClientRect(rect: tuple[int, int, int, int] | None, x: int, y: int) -> bool:
    """Kiểm tra tọa độ (x, y) có nằm trong vùng client hiện tại của cửa sổ game không."""
    if rect is None:
        return False
    left, top, width, height = rect
    return left <= x < left + width and top <= y < top + height


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
