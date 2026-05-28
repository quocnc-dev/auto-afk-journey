"""
Config chung - chỉnh các thông số tại đây
"""

import os

# ========================
#  ĐƯỜNG DẪN GAME / LAUNCHER
# ========================
GAME_WINDOW_TITLE = "AFK Journey"       # Tiêu đề cửa sổ game (dùng để tìm window)


# ========================
#  TEMPLATE IMAGES
# ========================
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# ========================
#  THÔNG SỐ NHẬN DIỆN ẢNH
# ========================
MATCH_THRESHOLD = 0.80              # Ngưỡng confidence (0.0 - 1.0)
SCAN_INTERVAL = 0.5                 # Giây giữa mỗi lần quét màn hình

# ========================
#  TIMEOUT
# ========================
TIMEOUT_WAIT_SCREEN = 30            # Giây tối đa chờ màn hình chuyển
TIMEOUT_BATTLE = 180                # Giây tối đa cho 1 trận đấu Arena/Guild Boss


# ========================
#  LOG
# ========================
LOG_FILE = os.path.join(os.path.dirname(__file__), "logs", "bot.log")
MAX_LOG_LINES = 500                # Số dòng log tối đa hiển thị trên UI

# ========================
#  DELAY (giây)
# ========================
DELAY_AFTER_CLICK = 0.5
DELAY_AFTER_SCREEN_CHANGE = 1.5
DELAY_SHORT = 0.3
