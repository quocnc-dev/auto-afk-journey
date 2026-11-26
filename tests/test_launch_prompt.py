"""
Regression (build 35, 26/11): hộp thoại 'Yêu cầu mở / focus game' hiện liên tục và không bấm Stop được.
Bấm OK xong focus đang ở app bot nên kiểm tra lại ngay luôn thất bại -> hỏi lại; hộp thoại modal chặn nút Stop.
"""

import time
import unittest

import bot_engine
import config


class TestLaunchPrompt(unittest.TestCase):

    def setUp(self):
        self.orig = (bot_engine.findGameWindow, bot_engine.focusGameWindow,
                     bot_engine.getClientRectScreen, bot_engine.isWindowForeground, config.LAUNCH_FOREGROUND_WAIT)
        bot_engine.findGameWindow = lambda _: 999
        bot_engine.focusGameWindow = lambda _: False
        bot_engine.getClientRectScreen = lambda _: (0, 0, 678, 936)
        self.foreground = False
        bot_engine.isWindowForeground = lambda _: self.foreground

    def tearDown(self):
        (bot_engine.findGameWindow, bot_engine.focusGameWindow, bot_engine.getClientRectScreen,
         bot_engine.isWindowForeground, config.LAUNCH_FOREGROUND_WAIT) = self.orig

    def _engine(self, answer):
        prompts = []

        def prompt(title, message):
            prompts.append(title)
            return answer
        eng = bot_engine.BotEngine(prompt_callback=prompt)
        eng.debugSnap.enabled = False
        eng.state = bot_engine.State.LAUNCH_GAME
        return eng, prompts

    def test_cancel_stops_bot(self):
        eng, prompts = self._engine(False)
        eng._state_launch_game()
        self.assertEqual(len(prompts), 1)
        self.assertTrue(eng._stop_event.is_set())
        self.assertTrue(any("chọn dừng bot" in m for m in eng.recentLogs))

    def test_ok_waits_for_user_to_focus_game_instead_of_reprompting(self):
        config.LAUNCH_FOREGROUND_WAIT = 5.0
        eng, prompts = self._engine(True)
        # Người dùng bấm vào game ~1s sau khi đóng hộp thoại
        import threading
        threading.Timer(1.0, lambda: setattr(self, "foreground", True)).start()
        start = time.monotonic()
        eng._state_launch_game()
        self.assertLess(time.monotonic() - start, 3.0)   # không chờ đủ 5s khi game đã lên trên cùng
        self.assertEqual(len(prompts), 1)
        self.assertFalse(eng._stop_event.is_set())

    def test_no_prompt_after_stop_requested(self):
        eng, prompts = self._engine(True)
        eng._stop_event.set()
        eng._state_launch_game()
        self.assertEqual(prompts, [])


if __name__ == "__main__":
    unittest.main()
