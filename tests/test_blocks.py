import tempfile
import unittest
from datetime import date
from pathlib import Path

from progress_recorder.blocks import BREAK_SECONDS
from progress_recorder.classifier import IGNORED, Classifier, clean_title
from progress_recorder.database import Database, Event, day_bounds
from progress_recorder.reporter import (
    BRIEF,
    DETAIL,
    SKIP,
    ReviewedBlock,
    build_daily_stats,
    build_review_ai_prompt,
    make_review_markdown,
)

ZWSP = chr(0x200B)  # Edge really puts a zero-width space in "Microsoft Edge"


class CleanTitleTests(unittest.TestCase):
    def test_edge_title_from_real_data(self):
        raw = f"ZacNAS-NYCU - Synology NAS 和其他 10 個頁面 - 個人 2 - Microsoft{ZWSP} Edge"
        self.assertEqual(clean_title(raw), "ZacNAS-NYCU - Synology NAS")

    def test_editor_titles(self):
        self.assertEqual(clean_title("● sweep.py - lab - Visual Studio Code"), "sweep.py - lab")
        self.assertEqual(clean_title("report.pptx - PowerPoint"), "report.pptx")
        self.assertEqual(clean_title("(3) Inbox - Google Chrome"), "Inbox")

    def test_shell_surfaces_are_ignored(self):
        c = Classifier()
        quick = Event(0, "window", 0, 0, "ShellHost.exe", "快速設定", "", "")
        taskbar = Event(0, "window", 0, 0, "explorer.exe", "", "", "")
        self.assertEqual(c.classify(quick), IGNORED)
        self.assertEqual(c.classify(taskbar), IGNORED)


class BlockTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._temp.name) / "test.db")
        self.t = day_bounds(date.today())[0] + 9 * 3600  # 09:00 today

    def tearDown(self):
        self._temp.cleanup()

    def window(self, app, title, start_min, end_min):
        self.db.add_event("window", app_name=app, title=title,
                          started_at=self.t + start_min * 60, ended_at=self.t + end_min * 60)

    def stats(self, rules=()):
        return build_daily_stats(self.db, date.today(), Classifier(rules))

    def test_long_break_splits_blocks_short_one_does_not(self):
        self.window("POWERPNT.EXE", "a.pptx - PowerPoint", 0, 60)
        self.window("chrome.exe", "Cats - YouTube", 60, 65)  # 5 min distraction
        self.window("Code.exe", "sim.py - lab - Visual Studio Code", 65, 120)
        self.db.add_event("idle", started_at=self.t + 120 * 60, ended_at=self.t + 180 * 60)  # lunch
        self.window("Code.exe", "sim.py - lab - Visual Studio Code", 180, 240)

        blocks = self.stats().blocks
        self.assertGreater(60 * 60, BREAK_SECONDS)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].work_seconds, 115 * 60)  # YouTube not counted
        self.assertEqual(set(blocks[0].app_seconds), {"POWERPNT.EXE", "Code.exe"})
        self.assertIn("a.pptx", blocks[0].top_titles())

    def test_files_and_notes_join_their_block(self):
        self.window("Code.exe", "mesh.lsf - Visual Studio Code", 0, 30)
        self.db.add_event("file", file_path="C:/lab/mesh.lsf", detail="modified", started_at=self.t + 10 * 60)
        self.db.add_event("note", detail="mesh 問題已解決", started_at=self.t + 29 * 60)

        (block,) = self.stats().blocks
        self.assertEqual(block.top_files(), [("mesh.lsf", 1)])
        self.assertEqual(block.notes, ["mesh 問題已解決"])

    def test_lone_file_sync_is_not_a_block(self):
        self.db.add_event("file", file_path="C:/lab/a.pptx", detail="modified", started_at=self.t)
        self.assertEqual(self.stats().blocks, [])

    def test_unknown_items_group_by_app_or_browser_page(self):
        self.window("AnyDesk.exe", "106 252 913 - AnyDesk", 0, 20)
        self.window("AnyDesk.exe", "AnyDesk", 20, 22)
        self.window("msedge.exe", f"ZacNAS-NYCU - Synology NAS 和其他 10 個頁面 - 個人 2 - Microsoft{ZWSP} Edge", 22, 25)

        items = {(i.field, i.value): i.seconds for i in self.stats().unknown_items}
        self.assertEqual(items[("app", "AnyDesk.exe")], 22 * 60)
        self.assertEqual(items[("title", "ZacNAS-NYCU - Synology NAS")], 3 * 60)

    def test_user_rule_turns_unknown_into_work_block(self):
        self.window("AnyDesk.exe", "106 252 913 - AnyDesk", 0, 30)
        self.assertEqual(self.stats().blocks, [])
        rules = [{"field": "app", "contains": "anydesk", "category": "work"}]
        self.assertEqual(len(self.stats(rules).blocks), 1)


class ReviewMarkdownTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._temp.name) / "test.db")
        t = day_bounds(date.today())[0] + 9 * 3600
        self.db.add_event("window", app_name="POWERPNT.EXE", title="results.pptx - PowerPoint",
                          started_at=t, ended_at=t + 3600)
        self.db.add_event("window", app_name="Code.exe", title="fdtd.py - Visual Studio Code",
                          started_at=t + 3 * 3600, ended_at=t + 4 * 3600)
        self.db.add_event("window", app_name="Code.exe", title="secret_side_project.py - Visual Studio Code",
                          started_at=t + 6 * 3600, ended_at=t + 7 * 3600)
        self.blocks = build_daily_stats(self.db, date.today()).blocks

    def tearDown(self):
        self._temp.cleanup()

    def test_levels_and_comments(self):
        reviewed = [
            ReviewedBlock(self.blocks[0], DETAIL, "完成 Results 第 8–10 頁"),
            ReviewedBlock(self.blocks[1], BRIEF, ""),
            ReviewedBlock(self.blocks[2], SKIP, ""),
        ]
        md = make_review_markdown(date.today(), reviewed)

        self.assertIn("工作時間：2 小時（2 個工作區塊）", md)
        self.assertIn("## 重點", md)
        self.assertIn("完成 Results 第 8–10 頁", md)
        self.assertIn("results.pptx", md)
        self.assertIn("## 其他工作", md)
        self.assertIn("fdtd.py", md)
        self.assertNotIn("secret_side_project", md)
        self.assertNotIn("secret_side_project", build_review_ai_prompt(date.today(), reviewed))

    def test_nothing_selected(self):
        md = make_review_markdown(date.today(), [ReviewedBlock(b, SKIP) for b in self.blocks])
        self.assertIn("沒有選擇要記錄的工作", md)


if __name__ == "__main__":
    unittest.main()
