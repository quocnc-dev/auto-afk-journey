"""
Bộ kiểm tra và tự động cập nhật ứng dụng (In-App Update) qua GitHub Releases.
Hỗ trợ cả bản đóng gói Windows (.exe onedir) và macOS (.app bundle).
"""

import json
import logging
import os
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Callable

import config

logger = logging.getLogger("AFK_Bot.Updater")


class _NoAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Gỡ header Authorization khi redirect sang host khác (vd GitHub API -> S3 CDN)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newReq = super().redirect_request(req, fp, code, msg, headers, newurl)
        if newReq is not None:
            oldHost = urllib.parse.urlsplit(req.full_url).netloc.lower()
            newHost = urllib.parse.urlsplit(newurl).netloc.lower()
            if oldHost != newHost:
                for hdr in list(newReq.headers) + list(newReq.unredirected_hdrs):
                    if hdr.lower() == "authorization":
                        newReq.remove_header(hdr)
        return newReq


@dataclass
class UpdateInfo:
    """Thông tin kết quả kiểm tra phiên bản từ GitHub Releases."""

    currentTag: str
    latestTag: str
    hasUpdate: bool
    downloadUrl: str
    assetName: str
    assetSize: int
    releaseNotes: str
    htmlUrl: str
    isPackaged: bool


def getCurrentBuildInfo() -> dict:
    """Đọc metadata build_info.json đóng gói kèm app; fallback về APP_VERSION."""
    fallback = {"tag": f"v{config.APP_VERSION}", "sha": "", "run_number": 0, "is_packaged": bool(getattr(sys, "frozen", False))}
    infoPath = os.path.join(config.BUNDLE_DIR, config.BUILD_INFO_FILENAME)
    if not os.path.exists(infoPath):
        return fallback
    try:
        with open(infoPath, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("tag"):
            fallback.update(data)
    except Exception as exc:
        logger.warning(f"Không đọc được {infoPath}: {exc}")
    return fallback


def getDisplayVersion() -> str:
    """Trả về chuỗi phiên bản để hiển thị trên giao diện."""
    return str(getCurrentBuildInfo().get("tag") or f"v{config.APP_VERSION}")


def parseVersionKey(tag: str) -> tuple[int, int, int, int] | None:
    """Phân tích tag dạng v1.0.0-build.12 thành tuple số để so sánh chính xác."""
    m = re.match(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:[-._]build\.(\d+))?", (tag or "").strip())
    if not m:
        return None
    major, minor, patch, build = m.groups()
    return (int(major), int(minor), int(patch), int(build or 0))


def isNewerRelease(currentTag: str, latestTag: str) -> bool:
    """So sánh xem latestTag có mới hơn currentTag hay không."""
    cur = (currentTag or "").strip()
    lat = (latestTag or "").strip()
    if not lat or cur == lat:
        return False
    curKey = parseVersionKey(cur)
    latKey = parseVersionKey(lat)
    if curKey is not None and latKey is not None:
        return latKey > curKey
    return lat != cur


def getPlatformAssetName(platform: str | None = None) -> str:
    """Trả về tên file zip release tương ứng với hệ điều hành."""
    plat = platform or sys.platform
    if plat == "win32":
        return config.UPDATE_ASSET_WINDOWS
    return config.UPDATE_ASSET_DARWIN if plat == "darwin" else ""


def buildSslContext() -> ssl.SSLContext:
    """Tạo SSLContext có CA bundle (certifi hoặc /etc/ssl/cert.pem trên macOS)."""
    try:
        import certifi
        caPath = certifi.where()
        if caPath and os.path.isfile(caPath):
            return ssl.create_default_context(cafile=caPath)
    except Exception:
        pass
    if os.path.isfile("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


def checkForUpdate(releaseUrl: str | None = None) -> UpdateInfo:
    """Gọi GitHub Releases API để kiểm tra bản phát hành mới nhất."""
    buildInfo = getCurrentBuildInfo()
    currentTag = str(buildInfo.get("tag", f"v{config.APP_VERSION}"))
    expectedAsset = getPlatformAssetName()
    url = releaseUrl or config.GITHUB_RELEASES_LATEST_URL
    token = config.getGithubUpdateToken()

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AFKJourneyBot-Updater"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=config.UPDATE_HTTP_TIMEOUT, context=buildSslContext()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError("Không tìm thấy GitHub Release (404). Nếu repo đang Private, hãy chuyển Public hoặc đặt AFK_BOT_GITHUB_TOKEN trong .env.local.") from exc
        raise

    latestTag = str(data.get("tag_name") or data.get("name") or "")
    downloadUrl, assetSize = "", 0
    for asset in data.get("assets") or []:
        if asset.get("name") == expectedAsset:
            downloadUrl = str((asset.get("url") if token else asset.get("browser_download_url")) or asset.get("browser_download_url") or "")
            assetSize = int(asset.get("size") or 0)
            break

    return UpdateInfo(
        currentTag=currentTag, latestTag=latestTag, hasUpdate=isNewerRelease(currentTag, latestTag),
        downloadUrl=downloadUrl, assetName=expectedAsset, assetSize=assetSize,
        releaseNotes=str(data.get("body") or "").strip(), htmlUrl=str(data.get("html_url") or ""),
        isPackaged=bool(getattr(sys, "frozen", False)),
    )


def validateZipEntries(zipPath: str, destDir: str):
    """Kiểm tra chống Zip-Slip trước khi giải nén file zip."""
    realDest = os.path.abspath(destDir)
    with zipfile.ZipFile(zipPath, "r") as zf:
        for member in zf.infolist():
            target = os.path.abspath(os.path.join(realDest, member.filename))
            if target != realDest and not target.startswith(realDest + os.sep):
                raise ValueError(f"Đường dẫn zip không an toàn: {member.filename}")


def downloadAndExtractUpdate(downloadUrl: str, progressCb: Callable[[int, int], None] | None = None) -> tuple[str, str]:
    """Tải file zip cập nhật về thư mục tạm và giải nén an toàn."""
    if not downloadUrl.startswith("https://"):
        raise ValueError("URL tải bản cập nhật phải dùng HTTPS.")

    workDir = tempfile.mkdtemp(prefix="afk_bot_update_")
    zipPath, extractDir = os.path.join(workDir, "update.zip"), os.path.join(workDir, "extracted")
    os.makedirs(extractDir, exist_ok=True)

    try:
        dlHeaders = {"User-Agent": "AFKJourneyBot-Updater"}
        token = config.getGithubUpdateToken()
        if token and "/releases/assets/" in downloadUrl:
            dlHeaders["Authorization"] = f"Bearer {token}"
            dlHeaders["Accept"] = "application/octet-stream"
        req = urllib.request.Request(downloadUrl, headers=dlHeaders)
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=buildSslContext()), _NoAuthRedirectHandler())
        with opener.open(req, timeout=config.UPDATE_DOWNLOAD_TIMEOUT) as resp:
            totalSize = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(zipPath, "wb") as outFile:
                while True:
                    chunk = resp.read(config.UPDATE_CHUNK_SIZE)
                    if not chunk:
                        break
                    outFile.write(chunk)
                    downloaded += len(chunk)
                    if progressCb:
                        progressCb(downloaded, totalSize)

        validateZipEntries(zipPath, extractDir)
        if sys.platform == "darwin":
            subprocess.run(["/usr/bin/ditto", "-x", "-k", zipPath, extractDir], check=True)
        else:
            with zipfile.ZipFile(zipPath, "r") as zf:
                zf.extractall(extractDir)
        return workDir, extractDir
    except Exception:
        shutil.rmtree(workDir, ignore_errors=True)
        raise


def findExtractedPayload(extractDir: str, platform: str | None = None) -> str:
    """Tìm thư mục nguồn (Windows) hoặc gói .app (macOS) bên trong thư mục đã giải nén."""
    plat = platform or sys.platform
    targetName = "AFKJourneyBot.exe" if plat == "win32" else "AFKJourneyBot.app"
    for root, dirs, files in os.walk(extractDir):
        relDepth = os.path.relpath(root, extractDir).count(os.sep)
        if relDepth > 2:
            continue
        if plat == "win32" and targetName in files:
            return root
        if plat == "darwin" and targetName in dirs:
            return os.path.join(root, targetName)
    raise FileNotFoundError(f"Không tìm thấy {targetName} trong gói cập nhật.")


def resolveInstallTarget(executablePath: str | None = None, platform: str | None = None) -> str:
    """Xác định thư mục cài đặt hoặc .app bundle của ứng dụng đang chạy."""
    plat = platform or sys.platform
    exe = os.path.abspath(executablePath or sys.executable)
    if plat == "win32":
        return os.path.dirname(exe)
    if plat == "darwin":
        bundlePath = os.path.abspath(os.path.join(os.path.dirname(exe), "..", ".."))
        if not bundlePath.endswith(".app"):
            raise RuntimeError(f"Không xác định được .app bundle từ: {exe}")
        return bundlePath
    raise RuntimeError(f"Không hỗ trợ tự cập nhật trên hệ điều hành: {plat}")


def buildWindowsUpdateScript(pid: int, sourceDir: str, targetDir: str, workDir: str) -> str:
    """Tạo nội dung batch script chờ thoát PID, ghi đè file mới và mở lại AFKJourneyBot.exe."""
    exePath = os.path.join(targetDir, "AFKJourneyBot.exe")
    return "\r\n".join([
        "@echo off", "chcp 65001 >NUL", "setlocal", "set /a tries=0",
        ":wait_loop",
        f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL',
        "if errorlevel 1 goto copy_files",
        "set /a tries+=1",
        "if %tries% GEQ 20 goto copy_files",
        "timeout /t 1 /nobreak >NUL",
        "goto wait_loop",
        ":copy_files",
        f'robocopy "{sourceDir}" "{targetDir}" /E /IS /IT /R:5 /W:1 >NUL',
        "if errorlevel 8 goto cleanup",
        f'start "" "{exePath}"',
        ":cleanup",
        f'rmdir /S /Q "{workDir}" >NUL 2>&1',
        'del "%~f0" >NUL 2>&1',
    ])


def buildMacUpdateScript(pid: int, sourceApp: str, targetApp: str, workDir: str) -> str:
    """Tạo shell script chờ thoát PID, thay thế .app bundle an toàn và mở lại ứng dụng."""
    qSrc, qDst, qBak, qWork = map(shlex.quote, (sourceApp, targetApp, f"{targetApp}.bak", workDir))
    return "\n".join([
        "#!/bin/bash", "tries=0",
        f"while kill -0 {pid} 2>/dev/null && [ $tries -lt 30 ]; do sleep 0.5; tries=$((tries+1)); done",
        f"rm -rf {qBak}",
        f"if mv {qDst} {qBak}; then",
        f"  if /usr/bin/ditto {qSrc} {qDst}; then",
        f"    rm -rf {qBak}; xattr -dr com.apple.quarantine {qDst} 2>/dev/null || true; open {qDst}",
        f"  else mv {qBak} {qDst}; fi",
        "fi",
        f'rm -rf {qWork}; rm -f "$0"',
    ])


def launchUpdateInstaller(workDir: str, extractDir: str) -> str:
    """Tạo và chạy script nền để áp dụng bản cập nhật sau khi app thoát."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Chỉ hỗ trợ tự cài đè khi chạy từ bản đóng gói (.exe / .app).")
    payload, target, pid = findExtractedPayload(extractDir), resolveInstallTarget(), os.getpid()
    suffix = ".bat" if sys.platform == "win32" else ".sh" if sys.platform == "darwin" else ""
    if not suffix:
        raise RuntimeError(f"Không hỗ trợ tự cài đặt trên: {sys.platform}")
    scriptText = buildWindowsUpdateScript(pid, payload, target, workDir) if suffix == ".bat" else buildMacUpdateScript(pid, payload, target, workDir)
    fd, scriptPath = tempfile.mkstemp(prefix="afk_apply_", suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8", newline="" if suffix == ".bat" else "\n") as f:
        f.write(scriptText)
    if suffix == ".bat":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(["cmd.exe", "/c", scriptPath], creationflags=flags, close_fds=True)
    else:
        os.chmod(scriptPath, 0o700)
        subprocess.Popen(["/bin/bash", scriptPath], start_new_session=True, close_fds=True)
    return scriptPath
