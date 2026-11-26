"""
Dựng layout Sidebar và Dashboard chính cho AFK Journey Auto Bot.
Tách khỏi main.py để giữ mỗi module gọn dưới 300 dòng.
"""

import customtkinter as ctk

import config
import updater
from ui_tabs import COLORS, buildLogTab, buildPreviewTab, buildTemplateTab


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

    ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(row=11, column=0, sticky="ew", padx=12, pady=8)
    ctk.CTkLabel(
        sidebar, text="NGƯỠNG NHẬN DIỆN", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["text_muted"]
    ).grid(row=12, column=0, padx=16, pady=(0, 4), sticky="w")
    app.threshold_var = ctk.DoubleVar(value=config.MATCH_THRESHOLD)
    app.threshold_lbl = ctk.CTkLabel(
        sidebar, text=f"{config.MATCH_THRESHOLD:.0%}", font=ctk.CTkFont(size=12), text_color=COLORS["accent"]
    )
    app.threshold_lbl.grid(row=13, column=0, padx=16, pady=(0, 2), sticky="w")
    ctk.CTkSlider(
        sidebar,
        from_=0.5,
        to=1.0,
        variable=app.threshold_var,
        command=app._on_threshold_change,
        fg_color=COLORS["border"],
        progress_color=COLORS["accent"],
        button_color=COLORS["accent"],
        button_hover_color=COLORS["accent2"],
    ).grid(row=14, column=0, padx=14, pady=(0, 12), sticky="ew")

    ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(row=15, column=0, sticky="ew", padx=12, pady=0)
    ctk.CTkButton(
        sidebar,
        text="🖼  Quản lý Template",
        fg_color="transparent",
        hover_color=COLORS["bg_card2"],
        text_color=COLORS["text_muted"],
        anchor="w",
        command=app._open_template_manager,
    ).grid(row=16, column=0, padx=8, pady=(8, 2), sticky="ew")
    ctk.CTkButton(
        sidebar,
        text="📁  Mở thư mục log",
        fg_color="transparent",
        hover_color=COLORS["bg_card2"],
        text_color=COLORS["text_muted"],
        anchor="w",
        command=app._open_log_dir,
    ).grid(row=17, column=0, padx=8, pady=2, sticky="ew")
    app.btn_update = ctk.CTkButton(
        sidebar,
        text="🔄  Kiểm tra cập nhật",
        fg_color="transparent",
        hover_color=COLORS["bg_card2"],
        text_color=COLORS["text_muted"],
        anchor="w",
        command=app._on_check_update,
    )
    app.btn_update.grid(row=18, column=0, padx=8, pady=2, sticky="ew")

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
    for col, (key, label, default, color) in enumerate([
        ("current_task", "📋 Nhiệm vụ", "—", COLORS["accent"]),
        ("run_time", "⏱ Thời gian", "00:00", COLORS["success"]),
        ("bot_state", "🔧 Trạng thái", "IDLE", COLORS["text_muted"]),
    ]):
        card = _makeStatCard(statsFrame, label, default, color)
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
    app.tab_view.add("🗺 Template")
    buildLogTab(app, app.tab_view.tab("📋 Log"))
    buildPreviewTab(app, app.tab_view.tab("🖥 Preview"))
    buildTemplateTab(app, app.tab_view.tab("🗺 Template"))


def _makeStatCard(parent, label, value, accent):
    card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card2"], corner_radius=10)
    ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10), text_color=COLORS["text_muted"]).pack(
        anchor="w", padx=14, pady=(10, 0)
    )
    valLbl = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=18, weight="bold"), text_color=accent)
    valLbl.pack(anchor="w", padx=14, pady=(2, 10))
    card._value_label = valLbl
    return card
