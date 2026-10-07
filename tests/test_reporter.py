import tempfile
import unittest
from datetime import date
from pathlib import Path

from progress_recorder.classifier import IDLE, NONWORK, WORK
from progress_recorder.database import Database, day_bounds
from progress_recorder.reporter import build_ai_prompt, build_daily_stats, make_markdown


class ReporterTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp = Path(self._temp.name)
        self.db = Database(self.temp / "test.db")
        # Fixed mid-day anchor so the test never straddles midnight.
        self.noon = day_bounds(date.today())[0] + 12 * 3600

    def tearDown(self):
        self._temp.cleanup()

    def test_report_contains_real_events(self):
        now = self.noon
        self.db.add_event(
            "window",
            app_name="POWERPNT.EXE",
            title="paper_report.pptx - PowerPoint",
            started_at=now - 1800,
            ended_at=now,
        )
        self.db.add_event(
            "file",
            file_path=str(self.temp / "paper_report.pptx"),
            detail="modified",
            started_at=now,
            ended_at=now,
        )
        self.db.add_event(
            "note",
            detail="完成 Results 圖說修改",
            started_at=now,
            ended_at=now,
        )

        stats = build_daily_stats(self.db, date.today())
        report = make_markdown(stats)
        prompt = build_ai_prompt(stats)

        self.assertIn("POWERPNT.EXE", report)
        self.assertIn("paper_report.pptx", report)
        self.assertIn("完成 Results 圖說修改", report)
        self.assertIn("不可臆測", prompt)

    def test_nonwork_and_idle_are_excluded_from_work(self):
        t = self.noon
        self.db.add_event("window", app_name="POWERPNT.EXE", title="a.pptx", started_at=t, ended_at=t + 3600)
        self.db.add_event("window", app_name="chrome.exe", title="Cat video - YouTube", started_at=t + 3600, ended_at=t + 4200)
        self.db.add_event("idle", started_at=t + 4200, ended_at=t + 7800)

        stats = build_daily_stats(self.db, date.today())
        report = make_markdown(stats)

        self.assertEqual(stats.category_seconds[WORK], 3600)
        self.assertEqual(stats.category_seconds[NONWORK], 600)
        self.assertEqual(stats.category_seconds[IDLE], 3600)
        self.assertNotIn("chrome.exe", stats.app_seconds)
        self.assertNotIn("Cat video", report)
        self.assertIn("工作 1 小時", report)

    def test_session_crossing_midnight_is_split_between_days(self):
        midnight = day_bounds(date.today())[0]
        self.db.add_event("window", app_name="Code.exe", title="sim.py", started_at=midnight - 1800, ended_at=midnight + 1800)

        stats = build_daily_stats(self.db, date.today())
        self.assertEqual(stats.app_seconds["Code.exe"], 1800)

    def test_timeline_merges_consecutive_windows_of_same_app(self):
        t = self.noon
        for i in range(30):
            self.db.add_event("window", app_name="Code.exe", title=f"file{i % 5}.py", started_at=t + i * 60, ended_at=t + (i + 1) * 60)

        report = make_markdown(build_daily_stats(self.db, date.today()))
        timeline = report.split("## 工作時間軸")[1]
        self.assertEqual(timeline.count("Code.exe"), 1)
        self.assertIn("等 5 個視窗", timeline)


if __name__ == "__main__":
    unittest.main()
