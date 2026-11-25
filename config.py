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
#  TEMPLATE IMAGES (fallback tùy chọn)
# ========================
TEMPLATES_DIR = os.path.join(BUNDLE_DIR, "templates")

# ========================
#  THÔNG SỐ NHẬN DIỆN ẢNH & OCR
# ========================
MATCH_THRESHOLD = 0.80              # Ngưỡng confidence cho template fallback (0.0 - 1.0)
OCR_FUZZY_THRESHOLD = 0.75          # Ngưỡng khớp mờ cho OCR tiếng Việt/Anh
SCAN_INTERVAL = 0.5                 # Giây giữa mỗi lần quét màn hình

# Ngưỡng HSV nhận diện checkbox đã tick (màu xanh lá)
CHECKBOX_GREEN_HSV_LOW = (35, 40, 60)
CHECKBOX_GREEN_HSV_HIGH = (90, 255, 255)
CHECKBOX_GREEN_MIN_RATIO = 0.12

# ========================
#  TỪ KHÓA & VÙNG ROI (tỷ lệ 0.0 -> 1.0 theo cửa sổ game)
# ========================
# Format ROI: (xMinRatio, yMinRatio, xMaxRatio, yMaxRatio)
ROI_FULL_WINDOW = (0.0, 0.0, 1.0, 1.0)
ROI_NEXT_TEAM_AREA = (0.65, 0.25, 0.98, 0.75)

# Từ khóa OCR đã chuẩn hóa (không dấu, chữ thường)
OCR_KEYWORDS = {
    "retry": ["thu lai", "thie lai", "retry"],
    "stats": ["thanh tich", "records"],
    "owned_team": ["doi hinh da so", "hien thi doi hinh", "owned"],
    "copy_team": ["sao chep", "copy"],
    "auto_battle_complete": ["hoan tat", "dong hoan", "auto battle complete"],
    "auto_battle": ["tu dong", "tudong", "auto battle"],
    "challenge_hl": ["huyen linh", "thach dau"],
    "fight": ["chien dau", "battle"],
    "afk_icon": ["afk"],
    "victory": ["da tang phan", "thuong afk", "thurong afk", "victory"],
    "back": ["quay lai", "back"],
}

# Tỷ lệ dịch chuyển tương đối (theo kích thước cửa sổ hoặc box chữ)
DEFEAT_BACK_OFFSET_X_RATIO = -0.18  # Nếu không thấy nút Back, dịch trái ~18% bề rộng cửa sổ từ nút Thử Lại
CHECKBOX_LEFT_HEIGHT_MULT = 1.15    # Tâm checkbox nằm bên trái chữ ~1.15 lần chiều cao dòng chữ
CHECKBOX_SAMPLE_HEIGHT_MULT = 0.45

# ========================
#  TIMEOUT
# ========================
TIMEOUT_WAIT_SCREEN = 30            # Giây tối đa chờ màn hình chuyển
TIMEOUT_BATTLE = 180                # Giây tối đa cho 1 trận đấu Arena/Guild Boss

# ========================
#  LOG
# ========================
LOG_FILE = os.path.join(_resolveLogDir(), "bot.log")
MAX_LOG_LINES = 500                # Số dòng log tối đa hiển thị trên UI

# ========================
#  DELAY (giây)
# ========================
DELAY_AFTER_CLICK = 0.5
DELAY_AFTER_SCREEN_CHANGE = 1.5
DELAY_SHORT = 0.3
