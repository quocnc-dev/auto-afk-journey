# AFK Journey Auto Bot 🤖

Bot tự động vượt ải AFK Journey trên **Windows** và **macOS (Apple Silicon)** bằng **OCR (`RapidOCR`) + Neo tọa độ**, không cần người dùng tự chụp template cho các nút.

## 🏗 Cấu trúc project

```text
auto-afk-journey/
├── main.py              # Giao diện chính (CustomTkinter)
├── ui_tabs.py           # Các tab Log / Preview / Template
├── bot_engine.py        # State Machine điều phối bot
├── window_manager.py    # Bắt cửa sổ game đa nền tảng (pywin32 / Quartz)
├── ocr_engine.py        # Nhận diện chữ OCR, checkbox & mũi tên
├── vision.py            # Chụp màn hình cửa sổ game & template fallback
├── controller.py        # Chuột/bàn phím (Virtual Desktop Windows / macOS)
├── config.py            # Cấu hình từ khóa OCR, ngưỡng, ROI
├── modules/
│   └── auto_afk.py      # Luồng tự động vượt ải Auto AFK
├── tests/               # Unit tests tự động
├── .github/workflows/   # GitHub Actions build & Release Windows + macOS
├── setup.bat            # Cài đặt thư viện trên Windows
├── run_bot.bat          # Chạy bot với quyền Admin trên Windows
└── build_exe.bat        # Đóng gói .exe trên Windows
```

## 🚀 Chạy từ mã nguồn

```bat
setup.bat
run_bot.bat
```

## 📦 Tải bản build sẵn từ GitHub Releases

Workflow [ci.yml](.github/workflows/ci.yml) tự động build và phát hành 2 gói sau mỗi lần push lên `master` / `main` hoặc gắn tag `v*`:
- **Windows x64**: `afk-journey-bot-windows-x64.zip` → giải nén và chạy `AFKJourneyBot.exe` (chạy quyền Admin nếu game chặn click).
- **macOS Apple Silicon**: `afk-journey-bot-macos-arm64.zip` → giải nén `AFKJourneyBot.app`.

### Lưu ý khi chạy trên macOS lần đầu
1. Nếu macOS chặn app chưa ký:
   ```bash
   xattr -cr AFKJourneyBot.app
   ```
2. Vào **System Settings → Privacy & Security** và cấp 2 quyền cho `AFKJourneyBot.app`:
   - **Screen Recording**: để chụp đúng cửa sổ game `"AFK Journey"` cho OCR đọc.
   - **Accessibility**: để điều khiển chuột click vào game.

## 🔄 State Machine

```text
IDLE → LAUNCH_GAME → CHECK_POPUP → AUTO_AFK → DONE / ERROR
```

## ⚠️ Lưu ý
- Giữ cửa sổ `"AFK Journey"` hiển thị (không bị thu nhỏ hoặc che khuất); nếu mất cửa sổ game, bot sẽ tự tạm dừng và không click ra ngoài ứng dụng khác.
- Có thể dùng `capture_template.py` để thêm ảnh popup quảng cáo (`popup_close.png`, `btn_close.png`) vào `templates/` làm fallback tùy chọn.
