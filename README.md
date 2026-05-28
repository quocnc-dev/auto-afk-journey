# AFK Journey Auto Bot 🤖

Bot tự động hoàn thành nhiệm vụ hàng ngày trong game AFK Journey bằng Python + OpenCV.

## 🏗 Cấu trúc project

```
auto-afk-journey/
├── main.py              # GUI chính (CustomTkinter)
├── bot_engine.py        # State Machine - Logic bot
├── vision.py            # Chụp màn hình + nhận diện ảnh (OpenCV)
├── controller.py        # Điều khiển chuột/bàn phím (PyDirectInput)
├── config.py            # Cấu hình chung
├── capture_template.py  # Tool chụp template từ màn hình
├── requirements.txt     # Thư viện cần cài
├── setup.bat            # Script cài đặt tự động
├── run_bot.bat          # Script chạy bot
├── templates/           # ← Bỏ ảnh template vào đây
└── logs/                # Log tự động tạo
```

## 🚀 Cài đặt

```bat
# Bước 1: Cài thư viện (chỉ cần làm 1 lần)
setup.bat

# Hoặc thủ công:
pip install -r requirements.txt
```

## ▶ Chạy bot

```bat
run_bot.bat
# hoặc
python main.py
```

## 🚀 Cấu hình Farlight Launcher (QUAN TRỌNG)

AFK Journey không mở trực tiếp được mà phải qua **Farlight Launcher**. Bot xử lý được điều này theo luồng:

```
Mở FarlightLauncher.exe
    → Chờ nút "Bắt đầu / Start" hiện ra
        → Click vào nút đó
            → Chờ game vào sảnh chính
                → Tiếp tục chạy nhiệm vụ
```

### Cài đặt trong GUI:
1. Bật switch **"Dùng Farlight Launcher"** (mặc định bật)
2. Nhấn 📂 chọn đường dẫn `FarlightLauncher.exe`
3. Chụp template nút **Start** trong launcher (xem bên dưới)

### Template bắt buộc cho Launcher:

| Tên file | Mô tả |
|---|---|
| `btn_launcher_start.png` | Nút "Bắt đầu chơi" / "Start Game" trong Farlight Launcher |
| `btn_launcher_confirm.png` | Nút confirm nếu có popup xác nhận (tuỳ chọn) |

> 💡 **Mẹo**: Mở Farlight Launcher, đến màn hình có nút Start → chạy `python capture_template.py` → chụp đúng vùng nút → đặt tên `btn_launcher_start`

## 🖼 Thêm Template (BẮT BUỘC trước khi dùng)

Bot dùng **Template Matching** → cần ảnh chụp của các nút/icon trong game.

### Cách chụp template:
```bat
python capture_template.py
```
1. Mở game AFK Journey
2. Chạy `capture_template.py`
3. Nhấn **"Chụp vùng màn hình"**
4. Kéo để khoanh vùng nút/icon cần nhận diện
5. Đặt tên theo bảng dưới đây

### Danh sách tên template cần có:

| Tên file | Mô tả |
|---|---|
| `home_indicator.png` | Bất kỳ element nào trên màn hình chính (để detect game đang mở) |
| `icon_daily_quest.png` | Icon sách/nhiệm vụ hàng ngày |
| `btn_claim_all.png` | Nút "Nhận tất cả" |
| `btn_claim.png` | Nút "Nhận" từng phần thưởng |
| `icon_arena.png` | Icon vào Arena |
| `btn_challenge.png` | Nút thách đấu đối thủ |
| `btn_auto_battle.png` | Nút Auto chiến đấu |
| `txt_victory.png` | Màn hình Victory sau trận |
| `txt_defeat.png` | Màn hình Defeat sau trận |
| `btn_result_close.png` | Nút đóng màn hình kết quả |
| `icon_guild.png` | Icon vào Guild |
| `btn_guild_checkin.png` | Nút điểm danh Guild |
| `btn_guild_boss.png` | Nút đánh Guild Boss |
| `popup_close.png` | Nút X đóng popup quảng cáo |
| `btn_close.png` | Nút đóng chung |
| `btn_back.png` | Nút quay lại |
| `btn_confirm.png` | Nút xác nhận |

> 💡 **Mẹo**: Chụp vùng nhỏ, đặc trưng. Tránh chụp vùng quá to hoặc có chữ số thay đổi.

## ⚙ Cấu hình (config.py)

| Tham số | Mặc định | Mô tả |
|---|---|---|
| `GAME_WINDOW_TITLE` | `"AFK Journey"` | Tiêu đề cửa sổ game |
| `GAME_EXE_PATH` | `""` | Đường dẫn .exe để tự mở game |
| `MATCH_THRESHOLD` | `0.80` | Độ chính xác nhận diện (0.5~1.0) |
| `ARENA_BATTLES_PER_DAY` | `5` | Số trận Arena mỗi ngày |
| `TIMEOUT_BATTLE` | `180` | Giây chờ tối đa 1 trận |

## 🔄 State Machine

```
IDLE → LAUNCH_GAME → CHECK_POPUP → DAILY_QUEST → ARENA → GUILD → DONE
                          ↑______________|__________|________|
                          (đóng popup bất cứ lúc nào)
```

## ⚠️ Lưu ý quan trọng

1. **Chạy với quyền Admin** nếu bot không click được vào game
2. **Độ phân giải cố định**: Template chụp ở độ phân giải nào thì chạy bot ở độ phân giải đó
3. **Không dùng chuột** khi bot đang chạy
4. Nếu bot kẹt, nhấn nút **Stop** → kiểm tra log để debug
5. Tuân thủ ToS của game, dùng cho mục đích cá nhân
