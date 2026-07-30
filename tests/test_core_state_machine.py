import unittest
from threading import Event
from unittest.mock import patch

try:
    from gacha_core import GachaCore
except ModuleNotFoundError:
    GachaCore = None

BaseCore = GachaCore or object


@unittest.skipIf(
    GachaCore is None, "OpenCV/numpy are installed by requirements.txt on Windows"
)
class CoreStateMachineTests(unittest.TestCase):
    class FakeCore(BaseCore):
        def __init__(self, prompts, *, menu_after_unknown=True):
            self.is_running = True
            self.phase_timeout = 600
            self.stats = self._empty_stats()
            self.dup_stats = self.stats
            self.prompts = list(prompts)
            self.menu_after_unknown = menu_after_unknown
            self.entry_clicked = False
            self.keys = []
            self.key_modes = []
            self.logs = []

        def log(self, message):
            self.logs.append(message)

        def focus_game(self):
            return True

        def enter_menu(self):
            return True

        def _ensure_focus(self):
            return True

        def find_image(self, name, *args, **kwargs):
            if name in ("wheelspin_btn.png", "super_wheelspin_btn.png"):
                if not self.entry_clicked:
                    return (100, 100)
                return (100, 100) if self.menu_after_unknown else None
            return None

        def game_click(self, _pos):
            self.entry_clicked = True

        def check_duplicate_car(self):
            return False

        def check_gacha_prompt(self):
            if self.prompts:
                return self.prompts.pop(0)
            return "none"

        def _handle_all_duplicates(self):
            return True

        def return_to_main_menu(self, timeout=30):
            return True

        def hw_press(self, key, delay=0.08, use_send=False):
            self.keys.append(key)
            self.key_modes.append(use_send)

        def _notify_stats(self):
            pass

    @patch("gacha_core.time.sleep", return_value=None)
    def test_claims_normal_spin_and_returns_to_menu(self, _sleep):
        core = self.FakeCore(["skip", "claim"])
        self.assertTrue(core._gacha_loop(1, is_super=False))
        self.assertEqual(core.stats["normal_spins"], 1)
        self.assertEqual(core.stats["super_spins"], 0)
        self.assertIn("enter", core.keys)
        self.assertGreaterEqual(core.keys.count("esc"), 2)

    @patch("gacha_core.time.sleep", return_value=None)
    def test_exhausted_menu_finishes_without_counting_spin(self, _sleep):
        core = self.FakeCore([])
        self.assertTrue(core._gacha_loop(999, is_super=True))
        self.assertEqual(core.stats["super_spins"], 0)
        self.assertTrue(any("次数已耗尽" in message for message in core.logs))

    @patch("gacha_core.time.sleep", return_value=None)
    def test_unknown_page_stops_after_bounded_recovery(self, _sleep):
        core = self.FakeCore([], menu_after_unknown=False)
        self.assertFalse(core._gacha_loop(10, is_super=False))
        self.assertEqual(core.keys.count("enter"), 3)
        self.assertTrue(any("安全推进上限" in message for message in core.logs))

    @patch("gacha_core.time.sleep", return_value=None)
    def test_threshold_ocr_failure_keeps_duplicate(self, _sleep):
        core = self.FakeCore([])
        core.duplicate_policy = "threshold"
        core.price_threshold = 100_000
        core._read_duplicate_price = lambda: None
        self.assertTrue(core.handle_duplicate_vehicle())
        self.assertEqual(core.keys, ["enter"])
        self.assertEqual(core.key_modes, [True])
        self.assertEqual(core.stats["kept"], 1)
        self.assertEqual(core.stats["ocr_failed"], 1)

    @patch("gacha_core.time.sleep", return_value=None)
    def test_sell_all_still_records_recognized_income(self, _sleep):
        core = self.FakeCore([])
        core.duplicate_policy = "sell_all"
        core.price_threshold = 100_000
        core._read_duplicate_price = lambda: 55_000
        self.assertTrue(core.handle_duplicate_vehicle())
        self.assertEqual(core.keys, ["down", "down", "enter"])
        self.assertEqual(core.key_modes, [True, True, True])
        self.assertEqual(core.stats["sold"], 1)
        self.assertEqual(core.stats["earned"], 55_000)

    @patch("gacha_core.time.sleep", return_value=None)
    def test_unconfirmed_duplicate_action_is_not_counted(self, _sleep):
        core = self.FakeCore([])
        core.duplicate_policy = "sell_all"
        core.price_threshold = 100_000
        core._read_duplicate_price = lambda: 55_000
        core._wait_duplicate_dismissed = lambda: False
        self.assertFalse(core.handle_duplicate_vehicle())
        self.assertEqual(core.stats["total"], 0)
        self.assertEqual(core.stats["sold"], 0)
        self.assertEqual(core.stats["earned"], 0)

    @patch("gacha_core.time.sleep", return_value=None)
    def test_capture_failure_does_not_confirm_duplicate_dismissal(self, _sleep):
        core = self.FakeCore([])
        states = iter((None, False))
        core.check_duplicate_car = lambda: next(states)
        self.assertTrue(core._wait_duplicate_dismissed())

    def test_price_ocr_waits_for_initialization_result(self):
        core = self.FakeCore([])
        core._easyocr_ready = Event()
        core._easyocr_done = Event()
        core._easyocr_done.set()
        core._preload_ocr = lambda: None
        self.assertFalse(core._ensure_ocr_ready())
        core._easyocr_ready.set()
        self.assertTrue(core._ensure_ocr_ready())


if __name__ == "__main__":
    unittest.main()
