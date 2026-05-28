import time
import logging

logger = logging.getLogger("AFK_Bot.AutoAFK")

# Cấu hình số lần thất bại liên tiếp trước khi đổi mode ưu tiên nhánh đấu
FAIL_THRESHOLD_TO_SWITCH_MODE = 5

def run_auto_afk(bot):
    """
    Thực hiện nhiệm vụ Auto AFK bằng cơ chế phát hiện trạng thái hình ảnh (OpenCV Template Matching):
    Tự động nhận diện màn hình hiện tại bằng template ảnh và thực hiện hành động tương ứng.
    Tích hợp tự động chuyển đổi Đội hình (Team) trong Thành tích khi gặp thất bại liên tiếp.
    """
    bot._log("🚀 Bắt đầu vòng lặp Auto AFK hướng trạng thái bằng OpenCV Matcher...")
    
    last_action_time = time.time()
    no_action_limit = 1200  # Giới hạn thời gian 20 phút không có hành động mới
    
    # Số lần thất bại liên tiếp trong cùng 1 ải (dùng để chọn team)
    failed_attempts = 0
    
    # Nhánh ưu tiên đấu: True = Huyền Linh SV, False = Chiến Đấu Thường
    prefer_challenge = True
    
    while not bot._stop_event.is_set():
        current_time = time.time()
        if current_time - last_action_time > no_action_limit:
            bot._log("⚠️ Không phát hiện hành động khả thi nào. Dừng Auto AFK để đảm bảo an toàn!")
            return False
            
        screen = bot.capture.capture_full()
        
        # 1. Phát hiện màn hình bại trận (có nút Thử Lại "btn_retry")
        btn_retry = bot.matcher.find(screen, "btn_retry")
        if btn_retry:
            failed_attempts += 1
            bot._log(f"❌ Trận đấu THẤT BẠI (Lần thứ {failed_attempts} liên tiếp)!")
            
            # Chỉ đổi mode khi số lần thất bại liên tiếp đạt mốc chia hết cho FAIL_THRESHOLD_TO_SWITCH_MODE
            if failed_attempts % FAIL_THRESHOLD_TO_SWITCH_MODE == 0:
                prefer_challenge = not prefer_challenge
                mode_name = "Thách Đấu Huyền Linh SV" if prefer_challenge else "Chiến Đấu Thường"
                bot._log(f"🔄 Thất bại liên tiếp đạt {failed_attempts} lần! Quay về sảnh và đổi mode ưu tiên sang: {mode_name}")
                
                # Tìm nút Back trên màn hình bại trận
                btn_back = bot.matcher.find(screen, "btn_afk_back_from_defeat")
                if btn_back:
                    bot._log("🖱 Click nút 'Back' trên màn hình bại trận...")
                    bot.ctrl.click(btn_back[0], btn_back[1])
                else:
                    # Click tọa độ tương đối từ nút Thử Lại (dịch sang trái 300px)
                    back_x = btn_retry[0] - 300
                    back_y = btn_retry[1]
                    bot._log(f"🖱 Click tọa độ nút Back tương đối ({back_x}, {back_y})...")
                    bot.ctrl.click(back_x, back_y)
                
                # Reset lại failed_attempts khi đã chuyển mode thành công
                failed_attempts = 0
                last_action_time = time.time()
                time.sleep(2.5)  # Đợi game quay về sảnh chính AFK
                continue
            
            # Nếu chưa đạt mốc đổi mode: Click "Thử Lại" để vào màn chuẩn bị đấu và đổi team
            bot._log("🖱 Click 'Thử Lại'...")
            bot.ctrl.click(btn_retry[0], btn_retry[1])
            last_action_time = time.time()
            time.sleep(2.5)  # Đợi màn hình chuẩn bị đấu tải xong
            
            # Ở màn hình chuẩn bị đấu: Tìm nút "Thành tích"
            prep_screen = bot.capture.capture_full()
            btn_stats = bot.matcher.find(prep_screen, "btn_afk_stats")
            if btn_stats:
                bot._log("🖱 Click 'Thành tích'...")
                bot.ctrl.click(btn_stats[0], btn_stats[1])
                time.sleep(2.0)
                
                # Trong giao diện Thành tích
                stats_screen = bot.capture.capture_full()
                
                # Checkbox "Chỉ hiển thị đội hình đã sở hữu"
                cb_unchecked = bot.matcher.find(stats_screen, "cb_owned_team_unchecked")
                if cb_unchecked:
                    bot._log("🖱 Tích chọn ô 'Chỉ hiển thị đội hình đã sở hữu'...")
                    bot.ctrl.click(cb_unchecked[0], cb_unchecked[1])
                    time.sleep(1.0)
                    stats_screen = bot.capture.capture_full()
                
                # RẼ NHÁNH ĐỔI TEAM:
                team_moves = failed_attempts - 1
                
                if team_moves <= 0:
                    # Lần đầu thất bại: Sao chép Team 1
                    btn_copy = bot.matcher.find(stats_screen, "btn_afk_copy_team")
                    if btn_copy:
                        bot._log("🖱 Click 'Sao chép' Team 1...")
                        bot.ctrl.click(btn_copy[0], btn_copy[1])
                        time.sleep(2.0)
                    else:
                        bot._log("⚠️ Không tìm thấy nút 'Sao chép', nhấn ESC.")
                        bot.ctrl.press_escape()
                        time.sleep(1.0)
                else:
                    # Từ lần thứ 2: Chuyển sang Team tiếp theo
                    btn_next_team = bot.matcher.find(stats_screen, "btn_afk_next_team")
                    if btn_next_team:
                        bot._log(f"🖱 Click chuyển sang Team tiếp theo ({team_moves} lần)...")
                        for _ in range(team_moves):
                            bot.ctrl.click(btn_next_team[0], btn_next_team[1])
                            time.sleep(0.8)
                        
                        # Chụp lại màn hình sau khi chuyển team và click Sao chép
                        stats_screen_after_move = bot.capture.capture_full()
                        btn_copy = bot.matcher.find(stats_screen_after_move, "btn_afk_copy_team")
                        if btn_copy:
                            bot._log("🖱 Click 'Sao chép' đội hình mới...")
                            bot.ctrl.click(btn_copy[0], btn_copy[1])
                            time.sleep(2.0)
                        else:
                            bot.ctrl.press_escape()
                            time.sleep(1.0)
                    else:
                        bot._log("⚠️ Không tìm thấy nút chuyển Team, nhấn ESC.")
                        bot.ctrl.press_escape()
                        time.sleep(1.0)
            else:
                bot._log("⚠️ Không tìm thấy nút 'Thành tích' ở màn hình chuẩn bị đấu.")
            continue

        # 2. Phát hiện màn hình "Chiến Đấu Tự Động Hoàn Tất"
        txt_finish = bot.matcher.find(screen, "txt_auto_battle_complete")
        if txt_finish:
            bot._log("🎉 Phát hiện màn hình 'Chiến Đấu Tự Động Hoàn Tất'. Click đóng...")
            bot.ctrl.click(txt_finish[0], txt_finish[1])
            failed_attempts = 0
            prefer_challenge = True
            last_action_time = time.time()
            time.sleep(2.5)
            continue

        # 3. Phát hiện nút "Chiến Đấu Tự Động" (Trong màn hình chuẩn bị đấu)
        btn_auto = bot.matcher.find(screen, "btn_afk_auto_battle")
        if btn_auto:
            bot._log("🖱 Click 'Chiến Đấu Tự Động'...")
            bot.ctrl.click(btn_auto[0], btn_auto[1])
            last_action_time = time.time()
            time.sleep(3.0)
            continue

        # 4. Phát hiện sảnh AFK dựa trên mode ưu tiên
        if prefer_challenge:
            btn_challenge = bot.matcher.find(screen, "btn_afk_challenge_hl")
            if btn_challenge:
                bot._log("🖱 Click 'Thách Đấu Huyền Linh SV'...")
                bot.ctrl.click(btn_challenge[0], btn_challenge[1])
                last_action_time = time.time()
                time.sleep(2.5)
                continue
            
            btn_fight = bot.matcher.find(screen, "btn_afk_fight")
            if btn_fight:
                bot._log("🖱 Click 'Chiến Đấu' thường (do không có Huyền Linh)...")
                bot.ctrl.click(btn_fight[0], btn_fight[1])
                last_action_time = time.time()
                time.sleep(2.5)
                continue
        else:
            btn_fight = bot.matcher.find(screen, "btn_afk_fight")
            if btn_fight:
                bot._log("🖱 Click 'Chiến Đấu' thường...")
                bot.ctrl.click(btn_fight[0], btn_fight[1])
                last_action_time = time.time()
                time.sleep(2.5)
                continue
            
            btn_challenge = bot.matcher.find(screen, "btn_afk_challenge_hl")
            if btn_challenge:
                bot._log("🖱 Click 'Thách Đấu Huyền Linh SV' (do không có Chiến đấu thường)...")
                bot.ctrl.click(btn_challenge[0], btn_challenge[1])
                last_action_time = time.time()
                time.sleep(2.5)
                continue

        # 5. Phát hiện biểu tượng "AFK" ở sảnh chính
        icon_afk = bot.matcher.find(screen, "icon_afk")
        if icon_afk:
            bot._log("🖱 Tìm thấy sảnh chính. Click biểu tượng 'AFK'...")
            bot.ctrl.click(icon_afk[0], icon_afk[1])
            last_action_time = time.time()
            time.sleep(2.0)
            continue

        # 6. Phát hiện màn hình chiến thắng (Ví dụ: chứa chữ "THẮNG" - txt_victory)
        txt_win = bot.matcher.find(screen, "txt_victory")
        if txt_win:
            bot._log("🎉 Phát hiện màn hình CHIẾN THẮNG! Click tiếp tục...")
            # Click vào giữa màn hình để đóng thông báo thắng
            h, w = screen.shape[:2]
            bot.ctrl.click(int(w * 0.5), int(h * 0.5))
            
            # Reset tất cả về mặc định khi vượt ải thành công
            failed_attempts = 0
            prefer_challenge = True
            
            last_action_time = time.time()
            time.sleep(3.0)
            continue

        # Nếu không khớp trạng thái nào, đợi một chút rồi quét lại
        bot._log("⏳ Đang theo dõi trận đấu hoặc trạng thái game...")
        time.sleep(2.0)

    bot._log("✅ Dừng nhiệm vụ Auto AFK.")
    return True
