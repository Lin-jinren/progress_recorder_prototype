import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from progress_recorder.database import Database
from progress_recorder.reporter import build_ai_prompt, build_daily_stats, make_markdown


class ReporterTests(unittest.TestCase):
    def test_report_contains_real_events(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.db")
            now = datetime.now().timestamp()
            db.add_event(
                "window",
                app_name="POWERPNT.EXE",
                title="paper_report.pptx - PowerPoint",
                started_at=now - 1800,
                ended_at=now,
            )
            db.add_event(
                "file",
                file_path=str(Path(temp) / "paper_report.pptx"),
                detail="modified",
                started_at=now,
                ended_at=now,
            )
            db.add_event(
                "note",
                detail="完成 Results 圖說修改",
                started_at=now,
                ended_at=now,
            )

            stats = build_daily_stats(db, date.today())
            report = make_markdown(stats)
            prompt = build_ai_prompt(stats)

            self.assertIn("POWERPNT.EXE", report)
            self.assertIn("paper_report.pptx", report)
            self.assertIn("完成 Results 圖說修改", report)
            self.assertIn("不可臆測", prompt)


if __name__ == "__main__":
    unittest.main()
