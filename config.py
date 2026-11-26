"""
Config chung - chỉnh các thông số tại đây
"""

import os
import sys

# ========================
#  PHIÊN BẢN & THƯ MỤC GỐC
# ========================
APP_VERSION = "1.0.0"

# Thư mục chứa dữ liệu đóng gói (hỗ trợ PyInstaller _MEIPASS)
BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _resolveLogDir() -> str:
    """Chọn thư mục ghi log có quyền ghi trên cả Windows và macOS (.app bundle)."""
    override = os.environ.get("AFK_BOT_LOG_DIR", "").strip()
    if override:
        return override
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return os.path.expanduser("~/Library/Logs/AFKJourneyBot")
        return os.path.join(os.path.dirname(sys.executable), "logs")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# ========================
#  ĐƯỜNG DẪN GAME / LAUNCHER
# ========================
GAME_WINDOW_TITLE = "AFK Journey"       # Tiêu đề cửa sổ game (dùng để tìm window)

# ========================
#  THÔNG SỐ NHẬN DIỆN OCR & HSV
# ========================
OCR_FUZZY_THRESHOLD = 0.75          # Ngưỡng khớp mờ cho OCR tiếng Việt/Anh

# Ngưỡng HSV nhận diện checkbox đã tick (màu xanh lá)
CHECKBOX_GREEN_HSV_LOW = (35, 40, 60)
CHECKBOX_GREEN_HSV_HIGH = (90, 255, 255)
CHECKBOX_GREEN_MIN_RATIO = 0.12

# ========================
#  TỪ KHÓA & VÙNG ROI (tỷ lệ 0.0 -> 1.0 theo cửa sổ game)
# ========================
# Format ROI: (xMinRatio, yMinRatio, xMaxRatio, yMaxRatio)
ROI_NEXT_TEAM_AREA = (0.60, 0.20, 0.99, 0.80)
ROI_AFK_CORNER = (0.55, 0.65, 1.0, 1.0)
ROI_AFK_CORNER_LEFT = (0.0, 0.78, 0.35, 1.0)
ROI_BATTLE_TIMER = (0.70, 0.0, 1.0, 0.16)

# Thông số nhận diện & chờ trạng thái Tự Động Xử Lý ở màn hình chính
AUTO_PROGRESS_POLL_INTERVAL = 2.5
AUTO_PROGRESS_DONE_WORD = "xong"
AUTO_PROGRESS_MAX_DX_HEIGHT_MULT = 4
AUTO_PROGRESS_MAX_DY_HEIGHT_MULT = 4.0
AUTO_PROGRESS_SPLIT_DY_MULT = 2.5
PAUSE_CANCEL_OFFSET_MULT = 1.35     # Nút X của popup tắt auto: cách tâm nút ✓ xanh N lần bề rộng nút ✓ về bên trái
PAUSE_PROMPT_STUCK_REPEAT = 3       # Popup tắt auto còn sau N lần bấm X liên tiếp -> lưu ảnh debug
STAGE_CLICK_FALLBACK_THRESHOLD = 2  # Số lần bấm sảnh liên tiếp không vào trận -> đổi chế độ còn lại

# Từ khóa OCR đã chuẩn hóa (không dấu, chữ thường)
OCR_KEYWORDS = {
    "retry": ["thu lai", "thie lai", "retry"],
    "stats": ["thanh tich", "records"],
    "owned_team": ["doi hinh da so", "hien thi doi hinh", "owned"],
    "copy_team": ["sao chep", "copy"],
    "auto_battle_complete": ["tu dong hoan", "tu dong hoan tat", "auto battle complete"],
    "close_btn": ["dong", "close"],
    "auto_battle": ["tu dong", "chien dau tu dong", "tudong", "auto battle"],
    "auto_progress": ["tu dong xu ly", "auto progress"],
    "auto_progress_part": ["xu ly"],
    "in_battle_auto": ["tu dong chien dau", "auto battling"],
    "pause_auto_prompt": ["tat che do chien dau"],
    "main_world_nav": ["ngoi nha huyen bi", "bang hoi", "trang vien", "cam nang mua giai"],
    "challenge_hl": ["huyen linh", "huyen linh sv", "thach dau huyen linh"],
    "fight": ["chien dau", "battle"],
    "afk_icon": ["afk"],
    "peak_stage_icon": ["man choi dinh cao"],
    "victory": ["da tang phan", "thuong afk", "thurong afk", "victory"],
    "back": ["quay lai", "back"],
    "defeat": ["that bai", "defeat"],
}

# Vùng màn hình hợp lệ cho các nút có chữ chung chung ("đóng", "chiến đấu", "tự động"...).
# Chữ khớp nằm ngoài vùng (vd tiêu đề, banner phía trên) bị bỏ qua để tránh click nhầm.
# Format như ROI ở trên; xóa 1 dòng để tắt giới hạn cho nút đó.
ROI_LOWER_SCREEN = (0.0, 0.40, 1.0, 1.0)
OCR_KEY_ROIS = {
    "retry": ROI_LOWER_SCREEN,
    "close_btn": ROI_LOWER_SCREEN,
    "fight": ROI_LOWER_SCREEN,
    "challenge_hl": ROI_LOWER_SCREEN,
    "auto_battle": ROI_LOWER_SCREEN,
    "copy_team": ROI_LOWER_SCREEN,
    "stats": ROI_LOWER_SCREEN,
}

# Từ khóa loại trừ khi tìm nút Chiến Đấu thường và nút Tự Động
FIGHT_EXCLUDE_KEYS = ["auto_battle", "auto_battle_complete", "challenge_hl", "stats", "in_battle_auto", "pause_auto_prompt"]
FIGHT_EXTRA_EXCLUDES = ["cap nhat", "update", "che do"]
AUTO_BATTLE_EXCLUDE_KEYS = ["auto_battle_complete", "auto_progress", "in_battle_auto", "pause_auto_prompt"]
AUTO_BATTLE_EXTRA_EXCLUDES = []
CHALLENGE_HL_EXTRA_EXCLUDES = ["man choi", "dinh cao", "sinh vat", "ngoi nha", "ngoi nha huyen bi"]
IN_BATTLE_EXTRA_EXCLUDES = ["che do"]

# Tỷ lệ dịch chuyển tương đối (theo kích thước cửa sổ hoặc chiều cao chữ)
DEFEAT_BACK_HEIGHT_MULT = -3.2      # Dịch trái theo chiều cao chữ 'Thử Lại' (hỗ trợ cả màn dọc iPad)
CHECKBOX_LEFT_HEIGHT_MULT = 1.15    # Tâm checkbox nằm bên trái chữ ~1.15 lần chiều cao dòng chữ
CHECKBOX_SAMPLE_HEIGHT_MULT = 0.45

# ========================
#  TIMEOUT
# ========================
TIMEOUT_WAIT_SCREEN = 30            # Giây tối đa chờ màn hình chuyển

# ========================
#  LOG
# ========================
LOG_FILE = os.path.join(_resolveLogDir(), "bot.log")
MAX_LOG_LINES = 500                # Số dòng log tối đa hiển thị trên UI

# Lưu ảnh + kết quả OCR khi bot kẹt / gặp màn hình lạ (để chỉnh từ khóa từ dữ liệu thật)
DEBUG_SNAPSHOT_ENABLED = True
DEBUG_DIR = os.path.join(_resolveLogDir(), "debug")
DEBUG_MAX_SNAPSHOTS = 40            # Giữ tối đa N snapshot gần nhất, xóa bản cũ hơn
DEBUG_SNAPSHOT_MIN_INTERVAL = 60    # Giây tối thiểu giữa 2 snapshot cùng lý do
DEBUG_UNKNOWN_STREAK = 8            # Số vòng liên tiếp không nhận ra màn hình -> chụp snapshot

# Cùng 1 cảnh báo/lỗi (log bắt đầu bằng ⚠️ ❌ 💥) lặp lại N lần trong M giây -> tự lưu gói debug
# (ảnh game + OCR + log gần nhất + vị trí chuột/focus). Bot crash thì lưu ngay kèm traceback.
ISSUE_REPEAT_THRESHOLD = 5
ISSUE_WINDOW_SECONDS = 600
ISSUE_IGNORE_SUBSTRINGS = ["THẤT BẠI", "Thua lần"]   # Thua trận là diễn biến bình thường, không phải lỗi bot
DEBUG_RECENT_LOG_LINES = 150        # Số dòng log gần nhất đính kèm trong gói debug

# ========================
#  DELAY (giây)
# ========================
DELAY_AFTER_CLICK = 0.15            # Nghỉ ngắn sau click; phần chờ màn hình đổi do SCREEN_* bên dưới đảm nhiệm

# Chờ màn hình đổi sau click (so sánh khung hình thu nhỏ, không chạy OCR)
SCREEN_DIFF_SIZE = 96               # Thu nhỏ khung hình về NxN pixel trước khi so
SCREEN_CHANGE_THRESHOLD = 6.0       # Độ khác trung bình (0..255) coi là đã chuyển màn
SCREEN_STABLE_THRESHOLD = 2.0       # Dưới mức này giữa 2 lần chụp liên tiếp coi là đã đứng yên
SCREEN_LOCAL_PIXEL_DIFF = 30        # Pixel lệch hơn mức này (0..255) coi là pixel đã đổi
SCREEN_LOCAL_CHANGE_RATIO = 0.01    # >=1% pixel đổi cũng tính là đã chuyển màn (popup/nút nhỏ hiện ra)
SCREEN_RESCAN_INTERVAL = 0.5        # Quét lại khi màn mới load chậm chưa có nút cần tìm
PREP_SCREEN_WAIT = 4.0              # Tối đa chờ màn chuẩn bị đấu / bảng Thành tích load (giây)
TEAM_SWITCH_WAIT = 0.6              # Chờ sau mỗi lần bấm mũi tên đổi team (chỉ đổi ảnh nhỏ)
SCREEN_SETTLE_MIN_WAIT = 0.4        # Chờ tối thiểu trước khi bắt đầu so khung hình
SCREEN_SETTLE_POLL = 0.3

# Quét OCR sâu (vùng góc + phóng to 2x) tìm nút vào AFK: tốn ~4 lần OCR nên chỉ chạy
# khi đang ở màn hình chính hoặc cách lần trước ít nhất N giây
LOBBY_DEEP_SCAN_INTERVAL = 6.0
MAC_CLICK_HOLD_SECONDS = 0.06       # Thời gian giữ chuột (giây) để game macOS/iPadOS nhận click

# ========================
#  CẬP NHẬT TỰ ĐỘNG (IN-APP UPDATE)
# ========================
GITHUB_REPO = os.environ.get("AFK_BOT_GITHUB_REPO", "quocnc-dev/auto-afk-journey")
GITHUB_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_HTTP_TIMEOUT = 15
UPDATE_DOWNLOAD_TIMEOUT = 180
UPDATE_CHUNK_SIZE = 65536
UPDATE_ASSET_DARWIN = "afk-journey-bot-macos-arm64.zip"
UPDATE_ASSET_WINDOWS = "afk-journey-bot-windows-x64.zip"
BUILD_INFO_FILENAME = "build_info.json"


def getGithubUpdateToken() -> str:
    """Đọc AFK_BOT_GITHUB_TOKEN từ biến môi trường hoặc file .env.local (dùng cho repo Private)."""
    envToken = os.environ.get("AFK_BOT_GITHUB_TOKEN", "").strip()
    if envToken:
        return envToken
    candidates = [
        os.path.join(os.getcwd(), ".env.local"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local"),
        os.path.join(os.path.dirname(sys.executable), ".env.local"),
        os.path.expanduser("~/.afk_journey_bot.env.local"),
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("AFK_BOT_GITHUB_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return ""
