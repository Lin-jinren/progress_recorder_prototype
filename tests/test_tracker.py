import tempfile
import unittest
from pathlib import Path

from progress_recorder.database import Database
from progress_recorder.tracker import ActiveWindow, ActivityTracker

PPT = ActiveWindow("POWERPNT.EXE", "report.pptx - PowerPoint")
CODE = ActiveWindow("Code.exe", "sweep.py - Visual Studio Code")


class FakeSystem:
    """Stands in for the clock, the foreground window and the idle timer."""

    def __init__(self):
        self.now = 1_000_000.0
        self.window = PPT
        self.last_input = self.now

    def clock(self):
        return self.now

    def idle(self):
        return self.now - self.last_input

    def active_window(self):
        return self.window


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._temp.name) / "test.db")
        self.sys = FakeSystem()
        self.tracker = ActivityTracker(
            self.db,
            idle_threshold=300,
            poll_seconds=5,
            window_provider=self.sys.active_window,
            idle_provider=self.sys.idle,
            clock=self.sys.clock,
        )

    def tearDown(self):
        self._temp.cleanup()

    def step(self, seconds, *, active=True):
        self.sys.now += seconds
        if active:
            self.sys.last_input = self.sys.now
        return self.tracker.sample()

    def events(self):
        return list(reversed(self.db.latest_events()))

    def test_same_window_extends_and_switch_starts_new_session(self):
        t0 = self.sys.now
        self.assertEqual(self.tracker.sample(), "changed")
        self.assertEqual(self.step(5), "same")
        self.sys.window = CODE
        self.assertEqual(self.step(5), "changed")

        ppt, code = self.events()
        self.assertEqual((ppt.started_at, ppt.ended_at), (t0, t0 + 10))
        self.assertEqual(code.app_name, "Code.exe")

    def test_idle_trims_session_to_last_input_and_is_recorded_separately(self):
        t0 = self.sys.now
        self.tracker.sample()
        for _ in range(12):
            self.step(5)  # active until t0 + 60
        last_input = self.sys.now
        for _ in range(70):
            state = self.step(5, active=False)  # lunch
        self.assertEqual(state, "idle")
        self.step(5)  # back at the desk

        window, idle, resumed = self.events()
        self.assertEqual((window.started_at, window.ended_at), (t0, last_input))
        self.assertEqual(idle.event_type, "idle")
        self.assertEqual(idle.started_at, last_input)
        self.assertEqual(idle.ended_at, self.sys.now)
        self.assertEqual(resumed.event_type, "window")
        self.assertEqual(resumed.started_at, self.sys.now)

    def test_sleep_gap_is_not_counted(self):
        t0 = self.sys.now
        self.tracker.sample()
        self.step(5)
        self.assertEqual(self.step(3600), "changed")  # woke up, same window

        before, after = self.events()
        self.assertEqual(before.ended_at, t0 + 5)
        self.assertEqual(after.started_at, self.sys.now)

    def test_switching_to_recorder_ends_session(self):
        self.tracker.sample()
        self.step(5)
        self.sys.window = ActiveWindow("python.exe", "Progress Recorder")
        self.assertEqual(self.step(5), "ignored")
        switched_at = self.sys.now
        for _ in range(60):
            self.step(5)  # writing a note in the recorder for 5 minutes
        self.sys.window = PPT
        self.assertEqual(self.step(5), "changed")

        # The 5 minutes in the recorder must not be added to the PowerPoint session.
        first, second = self.events()
        self.assertEqual(first.ended_at, switched_at)
        self.assertEqual(second.started_at, self.sys.now)

    def test_unsupported_idle_detection_still_records(self):
        self.tracker.idle_provider = lambda: None
        self.tracker.sample()
        self.assertEqual(self.step(5), "same")


if __name__ == "__main__":
    unittest.main()
