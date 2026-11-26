"""
Điều phối luồng kiểm tra, tải và áp dụng In-App Update trên giao diện Tkinter.
"""

import threading
import webbrowser
from tkinter import messagebox

import updater
from ui_tabs import COLORS


def _setUpdateButton(app, text: str, state: str = "normal", fgColor: str = "transparent", textColor: str | None = None):
    btn = getattr(app, "btn_update", None)
    if btn is None:
        return
    btn.configure(
        text=text,
        state=state,
        fg_color=fgColor,
        text_color=textColor or COLORS["text_muted"],
    )


def checkUpdateAsync(app, silent: bool = False):
    """Kiểm tra bản cập nhật mới trên thread nền và thông báo trên UI thread."""
    if getattr(app, "_update_busy", False):
        return
    app._update_busy = True
    if not silent:
        _setUpdateButton(app, "⏳ Đang kiểm tra...", state="disabled")

    def worker():
        try:
            info = updater.checkForUpdate()
            app.after(0, _handleCheckResult, app, info, None, silent)
        except Exception as exc:
            app.after(0, _handleCheckResult, app, None, exc, silent)

    threading.Thread(target=worker, daemon=True, name="UpdateChecker").start()


def _handleCheckResult(app, info: updater.UpdateInfo | None, err: Exception | None, silent: bool):
    app._update_busy = False
    if err is not None:
        _setUpdateButton(app, "🔄  Kiểm tra cập nhật")
        app.update_idletasks()
        if not silent:
            messagebox.showerror("Lỗi kiểm tra cập nhật", f"Không thể kết nối GitHub:\n{err}", parent=app)
        else:
            app._on_log(f"[Updater] Không kiểm tra được bản mới: {err}")
        return

    assert info is not None
    if not info.hasUpdate:
        _setUpdateButton(app, "🔄  Kiểm tra cập nhật")
        app.update_idletasks()
        if not silent:
            messagebox.showinfo(
                "Đã cập nhật mới nhất",
                f"Bạn đang dùng phiên bản mới nhất ({info.currentTag}).",
                parent=app,
            )
        return

    _setUpdateButton(
        app,
        f"⬆  Cập nhật {info.latestTag}",
        fgColor=COLORS["bg_card2"],
        textColor=COLORS["success"],
    )
    if silent and (app._is_running or app.bot.is_running()):
        app._on_log(f"[Updater] Có phiên bản mới {info.latestTag}. Hãy dừng bot để cập nhật.")
        return

    notesPreview = f"\n\nGhi chú phát hành:\n{info.releaseNotes[:400]}" if info.releaseNotes else ""
    askMsg = (
        f"Đã có phiên bản mới: {info.latestTag}\n"
        f"Phiên bản hiện tại: {info.currentTag}"
        f"{notesPreview}\n\n"
        "Bạn có muốn tải và cập nhật ngay không?"
    )
    if messagebox.askyesno("Có bản cập nhật mới", askMsg, parent=app):
        _startDownloadAndApply(app, info)


def _startDownloadAndApply(app, info: updater.UpdateInfo):
    if app._is_running or app.bot.is_running():
        messagebox.showwarning(
            "Bot đang chạy",
            "Vui lòng bấm Stop để dừng bot trước khi cập nhật.",
            parent=app,
        )
        return

    if not info.isPackaged:
        openPage = messagebox.askyesno(
            "Đang chạy từ mã nguồn",
            "Bạn đang chạy bản Python từ mã nguồn (chưa đóng gói .exe/.app).\n"
            "Hãy chạy 'git pull' để cập nhật mã nguồn.\n\n"
            "Bạn có muốn mở trang GitHub Release không?",
            parent=app,
        )
        if openPage and info.htmlUrl:
            webbrowser.open(info.htmlUrl)
        return

    if not info.downloadUrl:
        openPage = messagebox.askyesno(
            "Chưa tìm thấy file tải",
            f"Release {info.latestTag} chưa có gói '{info.assetName}' cho hệ điều hành này.\n"
            "Bạn có muốn mở trang GitHub Release để kiểm tra không?",
            parent=app,
        )
        if openPage and info.htmlUrl:
            webbrowser.open(info.htmlUrl)
        return

    app._update_busy = True
    _setUpdateButton(app, "⬇ Đang tải 0%...", state="disabled", textColor=COLORS["accent"])
    app._on_log(f"[Updater] Đang tải {info.latestTag} ({info.assetName})...")

    def onProgress(done: int, total: int):
        label = f"⬇ Đang tải {int(done * 100 / total)}%..." if total > 0 else f"⬇ Đã tải {done // 1024} KB..."
        app.after(0, _setUpdateButton, app, label, "disabled", COLORS["bg_card2"], COLORS["accent"])

    def worker():
        try:
            workDir, extractDir = updater.downloadAndExtractUpdate(info.downloadUrl, progressCb=onProgress)
            app.after(0, _setUpdateButton, app, "⚙ Đang cài đặt...", "disabled", COLORS["bg_card2"], COLORS["warning"])
            updater.launchUpdateInstaller(workDir, extractDir)
            app.after(0, _finishAndRestart, app, info.latestTag)
        except Exception as exc:
            app.after(0, _onDownloadError, app, exc)

    threading.Thread(target=worker, daemon=True, name="UpdateDownloader").start()


def _onDownloadError(app, exc: Exception):
    app._update_busy = False
    _setUpdateButton(app, "🔄  Kiểm tra cập nhật")
    app._on_log(f"[Updater] Cập nhật thất bại: {exc}")
    messagebox.showerror("Cập nhật thất bại", f"Không thể tải hoặc cài bản cập nhật:\n{exc}", parent=app)


def _finishAndRestart(app, latestTag: str):
    app._on_log(f"[Updater] Đã sẵn sàng cài {latestTag}. Đang khởi động lại ứng dụng...")
    app.destroy()
