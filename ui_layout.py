"""
Dựng layout Sidebar và Dashboard chính cho AFK Journey Auto Bot.
Tách khỏi main.py để giữ mỗi module gọn dưới 300 dòng.
"""

import customtkinter as ctk

import config
import updater
from ui_tabs import COLORS, buildLogTab, buildPreviewTab


def buildSidebar(app):
    """Dựng thanh điều hướng bên trái (trạng thái, nhiệm vụ, ngưỡng, nút phụ)."""
    sidebar = ctk.CTkFrame(app, width=230, fg_color=COLORS["bg_card"], corner_radius=0)
    sidebar.grid(row=0, column=0, sticky="nsew")
    sidebar.grid_rowconfigure(24, weight=1)

    logoFrame = ctk.CTkFrame(sidebar, fg_color="transparent")
    logoFrame.grid(row=0, column=0, padx=16, pady=(20, 8), sticky="ew")
    ctk.CTkLabel(
        logoFrame, text="⚡", font=ctk.CTkFont(size=32), text_color=COLORS["accent"]
    ).pack(side="left", padx=(0, 8))
    titleFrame = ctk.CTkFrame(logoFrame, fg_color="transparent")
    titleFrame.pack(side="left")
    ctk.CTkLabel(
        titleFrame, text="AFK Bot", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text_primary"]
    ).pack(anchor="w")
    ctk.CTkLabel(
        titleFrame, text="Journey Auto", font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"]
    ).pack(anchor="w")

    ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(row=1, column=0, sticky="ew", padx=12, pady=8)

    app.status_dot = ctk.CTkLabel(
        sidebar, text="● IDLE", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLORS["text_muted"]
    )
    app.status_dot.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")

    ctk.CTkLabel(
        sidebar, text="NHIỆM VỤ", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["text_muted"]
    ).grid(row=3, column=0, padx=16, pady=(0, 6), sticky="w")

    app.var_auto_afk = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(
        sidebar,
        text="⏳  Auto AFK",
        variable=app.var_auto_afk,
        font=ctk.CTkFont(size=13),
        text_color=COLORS["text_primary"],
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent2"],
        border_color=COLORS["border"],
        checkmark_color="#FFFFFF",
    ).grid(row=4, column=0, padx=16, pady=4, sticky="w")

    ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(row=5, column=0, sticky="ew", padx=12, pady=8)
    ctk.CTkLabel(
        sidebar, text="CÀI ĐẶT NHANH", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["text_muted"]
    ).grid(row=6, column=0, padx=16, pady=(0, 6), sticky="w")

    app.var_start_mode = ctk.StringVar(value="Huyễn Linh")
    ctk.CTkSegmentedButton(
        sidebar,
        values=["Huyễn Linh", "Thường"],
        variable=app.var_start_mode,
        height=28,
        font=ctk.CTkFont(size=12),
        fg_color=COLORS["bg_card2"],
        selected_color=COLORS["accent"],
        selected_hover_color=COLORS["accent2"],
        unselected_color=COLORS["bg_card2"],
    ).grid(row=7, column=0, padx=16, pady=(0, 8), sticky="ew")

    thrRow = ctk.CTkFrame(sidebar, fg_color="transparent")
    thrRow.grid(row=8, column=0, padx=16, pady=(0, 6), sticky="ew")
    ctk.CTkLabel(
        thrRow, text="Đổi mode (thua):", font=ctk.CTkFont(size=12), text_color=COLORS["text_primary"]
    ).pack(side="left")
    app.var_fail_threshold = ctk.StringVar(value=str(config.DEFAULT_FAIL_THRESHOLD))
    ctk.CTkOptionMenu(
        thrRow,
        values=list(config.FAIL_THRESHOLD_CHOICES),
        variable=app.var_fail_threshold,
        width=68,
        height=26,
        fg_color=COLORS["bg_card2"],
        button_color=COLORS["accent"],
        button_hover_color=COLORS["accent2"],
    ).pack(side="right")

    app.var_auto_stop_stuck = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(
        sidebar,
        text="🛑  Dừng khi kẹt 2 nhánh",
        variable=app.var_auto_stop_stuck,
        font=ctk.CTkFont(size=12),
        text_color=COLORS["text_primary"],
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent2"],
        border_color=COLORS["border"],
        checkmark_color="#FFFFFF",
    ).grid(row=9, column=0, padx=16, pady=3, sticky="w")

    app.var_keep_awake = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(
        sidebar,
        text="☀️  Chống ngủ màn hình",
        variable=app.var_keep_awake,
        font=ctk.CTkFont(size=12),
        text_color=COLORS["text_primary"],
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent2"],
        border_color=COLORS["border"],
        checkmark_color="#FFFFFF",
    ).grid(row=10, column=0, padx=16, pady=3, sticky="w")

    ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(row=15, column=0, sticky="ew", padx=12, pady=8)
    ctk.CTkButton(
        sidebar,
        text="📁  Mở thư mục log",
        fg_color="transparent",
        hover_color=COLORS["bg_card2"],
        text_color=COLORS["text_muted"],
        anchor="w",
        command=app._open_log_dir,
    ).grid(row=17, column=0, padx=8, pady=2, sticky="ew")
    ctk.CTkButton(
        sidebar,
        text="📸  Mở thư mục Debug",
        fg_color="transparent",
        hover_color=COLORS["bg_card2"],
        text_color=COLORS["text_muted"],
        anchor="w",
        command=app._open_debug_dir,
    ).grid(row=18, column=0, padx=8, pady=2, sticky="ew")
    app.btn_update = ctk.CTkButton(
        sidebar,
        text="🔄  Kiểm tra cập nhật",
        fg_color="transparent",
        hover_color=COLORS["bg_card2"],
        text_color=COLORS["text_muted"],
        anchor="w",
        command=app._on_check_update,
    )
    app.btn_update.grid(row=19, column=0, padx=8, pady=2, sticky="ew")

    ctk.CTkLabel(
        sidebar,
        text=f"⌨️ Phím dừng nhanh: {config.STOP_HOTKEY_LABEL}",
        font=ctk.CTkFont(size=10),
        text_color=COLORS["text_muted"],
    ).grid(row=20, column=0, padx=16, pady=(8, 2), sticky="w")
    ctk.CTkLabel(
        sidebar,
        text=f"{updater.getDisplayVersion()} • AFK Journey Bot",
        font=ctk.CTkFont(size=9),
        text_color=COLORS["text_muted"],
    ).grid(row=21, column=0, padx=16, pady=(0, 12), sticky="sw")


def buildMainArea(app):
    """Dựng vùng Dashboard bên phải (Top bar, Stat cards, TabView)."""
    main = ctk.CTkFrame(app, fg_color="transparent")
    main.grid(row=0, column=1, sticky="nsew")
    main.grid_rowconfigure(2, weight=1)
    main.grid_columnconfigure(0, weight=1)

    topBar = ctk.CTkFrame(main, fg_color=COLORS["bg_card"], height=52, corner_radius=0)
    topBar.grid(row=0, column=0, sticky="ew")
    topBar.grid_propagate(False)
    topBar.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        topBar, text="🎮  Dashboard", font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["text_primary"]
    ).grid(row=0, column=0, padx=20, pady=14, sticky="w")

    ctrlFrame = ctk.CTkFrame(topBar, fg_color="transparent")
    ctrlFrame.grid(row=0, column=1, padx=16, pady=8, sticky="e")
    app.btn_start = ctk.CTkButton(
        ctrlFrame,
        text="▶  Start Bot",
        width=120,
        height=36,
        fg_color=COLORS["success"],
        hover_color="#16A34A",
        font=ctk.CTkFont(size=13, weight="bold"),
        command=app._on_start,
    )
    app.btn_start.pack(side="left", padx=(0, 8))
    app.btn_stop = ctk.CTkButton(
        ctrlFrame,
        text="■  Stop",
        width=110,
        height=36,
        fg_color=COLORS["danger"],
        hover_color="#B91C1C",
        font=ctk.CTkFont(size=13, weight="bold"),
        state="disabled",
        command=app._on_stop,
    )
    app.btn_stop.pack(side="left")

    statsFrame = ctk.CTkFrame(main, fg_color="transparent")
    statsFrame.grid(row=1, column=0, padx=16, pady=(12, 8), sticky="ew")
    statsFrame.grid_columnconfigure((0, 1, 2), weight=1)
    app.stat_cards = {}
    for col, (key, label, default, color, fontSize) in enumerate([
        ("current_task", "📋 Nhiệm vụ", "—", COLORS["accent"], 13),
        ("run_time", "⏱ Thời gian", "00:00", COLORS["success"], 18),
        ("bot_state", "🔧 Trạng thái", "IDLE", COLORS["text_muted"], 18),
    ]):
        card = _makeStatCard(statsFrame, label, default, color, fontSize=fontSize)
        card.grid(row=0, column=col, padx=(0 if col == 0 else 8, 0), sticky="ew")
        app.stat_cards[key] = card

    app.tab_view = ctk.CTkTabview(
        main,
        fg_color=COLORS["bg_card"],
        segmented_button_fg_color=COLORS["bg_card2"],
        segmented_button_selected_color=COLORS["accent"],
        segmented_button_selected_hover_color=COLORS["accent2"],
        segmented_button_unselected_color=COLORS["bg_card2"],
        text_color=COLORS["text_primary"],
    )
    app.tab_view.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")
    app.tab_view.add("📋 Log")
    app.tab_view.add("🖥 Preview")
    buildLogTab(app, app.tab_view.tab("📋 Log"))
    buildPreviewTab(app, app.tab_view.tab("🖥 Preview"))


def _makeStatCard(parent, label, value, accent, fontSize=18):
    card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card2"], corner_radius=10)
    ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10), text_color=COLORS["text_muted"]).pack(
        anchor="w", padx=14, pady=(10, 0)
    )
    valLbl = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=fontSize, weight="bold"), text_color=accent)
    valLbl.pack(anchor="w", padx=14, pady=(2, 10))
    card._value_label = valLbl
    return card
