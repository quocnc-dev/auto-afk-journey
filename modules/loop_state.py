"""Trạng thái vòng lặp Auto AFK: chuỗi thua, team đang dùng, mode ưu tiên và mốc tiến triển."""

import time
from dataclasses import dataclass, field

import config


@dataclass
class AfkLoopState:
    """Theo dõi số lần thua, chế độ ưu tiên (Huyễn Linh/Thường) và mốc tiến triển."""

    failedAttempts: int = 0          # Chuỗi thua liên tiếp (reset khi thắng) -> đủ ngưỡng thì đổi mode
    defeatCounted: bool = False
    teamSwitchedInStats: bool = False
    # Team thứ mấy trong bảng Thành tích của MÀN HIỆN TẠI đã chép (0 = chưa chép). Bảng Thành tích là theo từng màn:
    # vượt màn thì về 0 (màn mới chép lại từ team #1), thua tiếp trên cùng màn thì sang team #2, #3...
    teamCursor: int = 0
    needTeamChange: bool = False     # Vừa thua -> lần tới vào màn chuẩn bị đấu phải chép team kế tiếp
    lobbyClicksSameMode: int = 0
    preferChallenge: bool = True
    lastStateKey: str | None = None
    lastProgressTime: float = field(default_factory=time.time)
    lastDeepScanTime: float = float("-inf")
    lastFocusLossTime: float | None = None

    def markProgress(self, stateKey: str, refreshAlways: bool = False):
        if refreshAlways or self.lastStateKey != stateKey:
            self.lastStateKey = stateKey
            self.lastProgressTime = time.time()

    def recordDefeat(self, fromMainDone: bool = False) -> int:
        if not self.defeatCounted:
            self.failedAttempts += 1
        self.defeatCounted = fromMainDone
        self.teamSwitchedInStats = False
        self.lobbyClicksSameMode = 0
        self.needTeamChange = True
        return self.failedAttempts

    def onEnterBattle(self):
        self.defeatCounted = False
        self.teamSwitchedInStats = False
        self.lobbyClicksSameMode = 0

    def onModeSwitched(self):
        """Đổi mode: bảng Thành tích là của màn khác -> chép lại từ team đầu tiên."""
        self.failedAttempts = 0
        self.defeatCounted = False
        self.teamCursor = 0
        self.needTeamChange = True

    def onVictory(self):
        self.teamCursor = 0
        self.failedAttempts = 0
        self.defeatCounted = False
        self.teamSwitchedInStats = False
        self.lobbyClicksSameMode = 0

    def resolveLobbySwitch(self, bot, failThreshold: int) -> bool:
        if self.failedAttempts >= failThreshold:
            self.preferChallenge = not self.preferChallenge
            modeName = "Thách Đấu Huyền Linh SV" if self.preferChallenge else "Chiến Đấu Thường"
            bot._log(f"🔄 Đã thua {self.failedAttempts} lần! Chuyển chế độ ưu tiên sang: {modeName}")
            self.onModeSwitched()
            self.defeatCounted = False
            self.lobbyClicksSameMode = 0
        elif self.lobbyClicksSameMode >= config.STAGE_CLICK_FALLBACK_THRESHOLD:
            self.preferChallenge = not self.preferChallenge
            modeName = "Thách Đấu Huyền Linh SV" if self.preferChallenge else "Chiến Đấu Thường"
            bot._log(f"⚠️ Nút ưu tiên không vào được trận (hết ải/khóa), fallback sang: {modeName}")
            self.lobbyClicksSameMode = 0
        return self.preferChallenge
