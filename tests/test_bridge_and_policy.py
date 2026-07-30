import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gacha_backend import _build_lparam
from gacha_bridge import (
    EVENT_FINAL,
    EVENT_NEW_LOOP,
    EVENT_PAUSED,
    EVENT_RESUMED,
    EVENT_STOPPED,
    BridgeController,
    DiagnosticLogFollower,
    FH6AutoConfigGuard,
    classify_fh6auto_message,
    validate_fh6auto_pipeline,
)
from gacha_policy import decide_duplicate_action


class PolicyTests(unittest.TestCase):
    def test_duplicate_policies(self):
        self.assertEqual(
            decide_duplicate_action("sell_all", None, 100_000), ("sell", True)
        )
        self.assertEqual(
            decide_duplicate_action("sell_all", 50_000, 100_000), ("sell", False)
        )
        self.assertEqual(
            decide_duplicate_action("keep_all", 1, 100_000), ("keep", False)
        )
        self.assertEqual(
            decide_duplicate_action("threshold", 200_000, 100_000), ("keep", False)
        )
        self.assertEqual(
            decide_duplicate_action("threshold", 50_000, 100_000), ("sell", False)
        )
        self.assertEqual(
            decide_duplicate_action("threshold", None, 100_000), ("keep", True)
        )

    def test_background_key_lparam(self):
        down = _build_lparam(0x48, True, down=True)
        up = _build_lparam(0x48, True, down=False)
        self.assertTrue(down & (1 << 24))
        self.assertFalse(down & (1 << 30))
        self.assertTrue(up & (1 << 30))
        self.assertTrue(up & (1 << 31))


class BridgeParsingTests(unittest.TestCase):
    def test_stable_markers(self):
        self.assertEqual(
            classify_fh6auto_message("开启新一轮大循环 (2/10)"), EVENT_NEW_LOOP
        )
        self.assertEqual(classify_fh6auto_message("达到设定的总循环次数"), EVENT_FINAL)
        self.assertEqual(
            classify_fh6auto_message("任务已停止,所有物理按键状态已强制重置"),
            EVENT_STOPPED,
        )
        self.assertEqual(
            classify_fh6auto_message("任务已暂停 (按 F9 恢复)"), EVENT_PAUSED
        )
        self.assertEqual(classify_fh6auto_message("任务已恢复"), EVENT_RESUMED)
        self.assertIsNone(classify_fh6auto_message("普通业务日志"))

    def test_pipeline_route_requires_complete_four_stage_loop(self):
        valid = {"global_loops": 3}
        for index, next_step in enumerate((2, 3, 4, 1), 1):
            valid[f"chk_{index}"] = True
            valid[f"next_{index}"] = next_step
        self.assertEqual(validate_fh6auto_pipeline(valid), [])
        invalid = dict(valid, next_2=1, chk_3=False)
        errors = validate_fh6auto_pipeline(invalid)
        self.assertTrue(any("第2阶段下一步" in error for error in errors))
        self.assertTrue(any("第3阶段未勾选" in error for error in errors))

    def test_follower_skips_old_lines_and_reads_new_session(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / "diagnostic_reports" / "old" / "logs.jsonl"
            old.parent.mkdir(parents=True)
            old.write_text(
                json.dumps({"message": "开启新一轮大循环 (old)"}) + "\n",
                encoding="utf-8",
            )
            follower = DiagnosticLogFollower(root)
            self.assertEqual(follower.wait(0), [])

            with old.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps({"message": "任务已暂停"}, ensure_ascii=False) + "\n"
                )
            self.assertEqual(follower.wait(0)[0][0], EVENT_PAUSED)

            new = root / "diagnostic_reports" / "new" / "logs.jsonl"
            new.parent.mkdir(parents=True)
            new.write_text(
                json.dumps({"message": "任务已恢复"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(follower.wait(0)[0][0], EVENT_RESUMED)


class ConfigGuardTests(unittest.TestCase):
    def test_guard_restores_only_forced_values(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "diagnostic_mode": False,
                        "debug_screenshots": False,
                        "auto_close_game": True,
                        "auto_shutdown": True,
                        "global_loops": 10,
                    }
                ),
                encoding="utf-8",
            )
            guard = FH6AutoConfigGuard(temp)
            guard.apply()
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(data["diagnostic_mode"])
            self.assertFalse(data["auto_shutdown"])

            data["global_loops"] = 20
            path.write_text(json.dumps(data), encoding="utf-8")
            guard.restore()
            restored = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(restored["diagnostic_mode"])
            self.assertTrue(restored["auto_shutdown"])
            self.assertEqual(restored["global_loops"], 20)

    def test_new_guard_can_recover_persisted_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps({"diagnostic_mode": False}), encoding="utf-8")
            first = FH6AutoConfigGuard(temp)
            first.apply()
            self.assertTrue(
                json.loads(path.read_text(encoding="utf-8"))["diagnostic_mode"]
            )
            FH6AutoConfigGuard(temp).restore()
            self.assertFalse(
                json.loads(path.read_text(encoding="utf-8"))["diagnostic_mode"]
            )


class FakeFollower:
    def __init__(self):
        self.events = [(EVENT_NEW_LOOP, "开启新一轮大循环")]

    def wait(self, _timeout=0):
        if not self.events:
            return []
        events = list(self.events)
        self.events.clear()
        return events


class ControllerTests(unittest.TestCase):
    @patch("gacha_bridge.time.sleep", return_value=None)
    def test_final_report_is_completion_evidence(self, _sleep):
        with tempfile.TemporaryDirectory() as temp:
            follower = FakeFollower()
            follower.active_session_dir = Path(temp)
            (Path(temp) / "report.txt").write_text("done", encoding="utf-8")
            controller = BridgeController(
                ".",
                lambda: True,
                follower=follower,
                send_hotkey=lambda _key: None,
            )
            self.assertTrue(controller._wait_for_final_report())

    @patch("gacha_bridge.time.sleep", return_value=None)
    def test_intermediate_and_final_handoffs(self, _sleep):
        follower = FakeFollower()
        hotkeys = []
        gacha_runs = []

        def send_hotkey(key):
            hotkeys.append(key)
            if len(hotkeys) == 1:
                follower.events.append((EVENT_PAUSED, "任务已暂停"))
            else:
                follower.events.extend(
                    [
                        (EVENT_RESUMED, "任务已恢复"),
                        (EVENT_FINAL, "达到设定的总循环次数"),
                        (EVENT_STOPPED, "任务已停止,所有物理按键状态已强制重置"),
                    ]
                )

        controller = BridgeController(
            ".",
            lambda: gacha_runs.append("run") or True,
            handshake_timeout=3,
            follower=follower,
            send_hotkey=send_hotkey,
            final_ready=lambda: True,
        )
        self.assertTrue(controller.run())
        self.assertEqual(hotkeys, ["f9", "f9"])
        self.assertEqual(gacha_runs, ["run", "run"])
        self.assertEqual(controller.completed_cycles, 2)

    def test_missing_pause_confirmation_never_runs_gacha(self):
        follower = FakeFollower()
        gacha_runs = []
        hotkeys = []
        controller = BridgeController(
            ".",
            lambda: gacha_runs.append("run") or True,
            handshake_timeout=0.1,
            follower=follower,
            send_hotkey=hotkeys.append,
        )
        self.assertFalse(controller.run())
        self.assertEqual(gacha_runs, [])
        self.assertEqual(hotkeys, ["f9", "f8"])
        self.assertIn("未收到 FH6Auto 暂停确认", controller.last_error)

    @patch("gacha_bridge.time.sleep", return_value=None)
    def test_failed_gacha_does_not_send_resume(self, _sleep):
        follower = FakeFollower()
        hotkeys = []

        def send_hotkey(key):
            hotkeys.append(key)
            follower.events.append((EVENT_PAUSED, "任务已暂停"))

        controller = BridgeController(
            ".",
            lambda: False,
            handshake_timeout=0.1,
            follower=follower,
            send_hotkey=send_hotkey,
        )
        self.assertFalse(controller.run())
        self.assertEqual(hotkeys, ["f9", "f8"])
        self.assertFalse(controller.paused_by_bridge)
        self.assertIn("安全停止", controller.last_error)

    @patch("gacha_bridge.time.sleep", return_value=None)
    def test_missing_resume_confirmation_stops_after_gacha(self, _sleep):
        follower = FakeFollower()
        hotkeys = []

        def send_hotkey(key):
            hotkeys.append(key)
            if len(hotkeys) == 1:
                follower.events.append((EVENT_PAUSED, "任务已暂停"))

        controller = BridgeController(
            ".",
            lambda: True,
            handshake_timeout=0.1,
            follower=follower,
            send_hotkey=send_hotkey,
        )
        self.assertFalse(controller.run())
        self.assertEqual(hotkeys, ["f9", "f9", "f8"])
        self.assertIn("未收到 FH6Auto 恢复确认", controller.last_error)

    def test_manual_bridge_stop_sends_f8_once(self):
        hotkeys = []
        controller = BridgeController(
            ".",
            lambda: True,
            follower=FakeFollower(),
            send_hotkey=hotkeys.append,
        )
        controller.stop()
        controller.stop()
        self.assertEqual(hotkeys, ["f8"])


if __name__ == "__main__":
    unittest.main()
