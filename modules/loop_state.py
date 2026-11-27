"""Trạng thái vòng lặp Auto AFK: chuỗi thua, team đang dùng, mode ưu tiên và mốc tiến triển."""

import time
from dataclasses import dataclass, field

import config


@dataclass
class AfkLoopState:
    """Theo dõi số lần thua, chế độ ưu tiên (Huyễn Linh/Thường) và mốc tiến triển."""

    failedAttempts: int = 0          # Chuỗi thua liên tiếp (reset khi thắng) -> đủ ngưỡng thì đổi mode
    defeatCounted: bool = False
    statsArrowClicks: int = 0        # Số lần đã bấm mũi tên chuyển team thành công trong bảng Thành tích đang mở
    # Team thứ mấy trong bảng Thành tích của MÀN HIỆN TẠI đã chép (0 = chưa chép). Bảng Thành tích là theo từng màn:
    # vượt màn thì về 0 (màn mới chép lại từ team #1), thua tiếp trên cùng màn thì sang team #2, #3...
    teamCursor: int = 0
    needTeamChange: bool = False     # Vừa thua -> lần tới vào màn chuẩn bị đấu phải chép team kế tiếp
    pendingModeExit: int = 0         # Vừa đổi mode do thua: còn N lần thử thoát màn chuẩn bị của mode cũ về sảnh
    lobbyClicksSameMode: int = 0
    preferChallenge: bool = True
    stagesCleared: int = 0
    stuckModeSwitches: int = 0
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
        # Đánh dấu đã đếm cho trận thua hiện tại (tránh cộng dồn nếu click 'Thử Lại' trượt/mất focus)
        self.defeatCounted = True
        self.statsArrowClicks = 0
        self.lobbyClicksSameMode = 0
        self.needTeamChange = True
        return self.failedAttempts

    def onEnterBattle(self):
        self.defeatCounted = False
        self.statsArrowClicks = 0
        self.lobbyClicksSameMode = 0

    def onModeSwitched(self, countAsStuck: bool = True):
        """Đổi mode: bảng Thành tích là của màn khác -> chép lại từ team đầu tiên."""
        self.failedAttempts = 0
        self.defeatCounted = False
        self.teamCursor = 0
        self.needTeamChange = True
        if countAsStuck:
            self.stuckModeSwitches += 1

    def onVictory(self, clearedCount: int = 1):
        self.teamCursor = 0
        self.failedAttempts = 0
        self.defeatCounted = False
        self.statsArrowClicks = 0
        self.lobbyClicksSameMode = 0
        self.stagesCleared += max(0, int(clearedCount))
        self.stuckModeSwitches = 0

    def isStuckBothModes(self, maxSwitches: int) -> bool:
        return maxSwitches > 0 and self.stuckModeSwitches >= maxSwitches

    def modeLabel(self) -> str:
        return "Huyễn Linh" if self.preferChallenge else "Thường"

    def summaryText(self, failThreshold: int) -> str:
        return f"{self.modeLabel()} • +{self.stagesCleared} ải • {self.failedAttempts}/{failThreshold}"

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
            self.stuckModeSwitches += 1
        return self.preferChallenge


def emitProgress(bot, st: AfkLoopState, failThreshold: int):
    """Đẩy tóm tắt tiến độ hiện tại lên Dashboard UI (an toàn với MockBot không có callback)."""
    cb = getattr(bot, "progress_callback", None)
    if cb is not None:
        try:
            cb(st.summaryText(failThreshold))
        except Exception:
            pass


def checkStuckStop(bot, st: AfkLoopState, failThreshold: int, maxStuck: int) -> bool:
    """Cập nhật tiến độ và kiểm tra xem đã đổi qua lại cả 2 nhánh mà không qua ải nào chưa."""
    emitProgress(bot, st, failThreshold)
    if not st.isStuckBothModes(maxStuck):
        return False
    bot._log(
        f"🛑 Đã đổi qua lại 2 chế độ {st.stuckModeSwitches} lần không vượt thêm ải nào "
        f"(Tổng +{st.stagesCleared} ải). Tự dừng Auto AFK!"
    )
    bot.lastStopReason = f"Kẹt cả 2 chế độ ({st.stuckModeSwitches} lần đổi, +{st.stagesCleared} ải)"
    return True
