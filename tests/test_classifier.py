import unittest

from progress_recorder.classifier import IDLE, NONWORK, UNKNOWN, WORK, Classifier
from progress_recorder.database import Event


def window(app, title):
    return Event(0, "window", 0.0, 0.0, app, title, "", "")


class ClassifierTests(unittest.TestCase):
    def test_defaults(self):
        c = Classifier()
        self.assertEqual(c.classify(window("POWERPNT.EXE", "report.pptx - PowerPoint")), WORK)
        self.assertEqual(c.classify(window("chrome.exe", "Lo-fi beats - YouTube - Google Chrome")), NONWORK)
        self.assertEqual(c.classify(window("chrome.exe", "Overleaf, Online LaTeX Editor")), WORK)
        self.assertEqual(c.classify(window("chrome.exe", "Gmail")), UNKNOWN)

    def test_work_app_wins_over_distracting_title(self):
        c = Classifier()
        self.assertEqual(c.classify(window("Code.exe", "youtube_api.py - Visual Studio Code")), WORK)

    def test_user_rules_override_defaults(self):
        c = Classifier([
            {"field": "title", "contains": "Lecture", "category": "work"},
            {"field": "app", "contains": "LINE.exe", "category": "nonwork"},
            {"field": "bogus", "contains": "x", "category": "work"},  # ignored
        ])
        self.assertEqual(c.classify(window("chrome.exe", "Photonics Lecture 5 - YouTube")), WORK)
        self.assertEqual(c.classify(window("LINE.exe", "LINE")), NONWORK)

    def test_non_window_events(self):
        c = Classifier()
        self.assertEqual(c.classify(Event(0, "idle", 0, 0, "", "", "", "")), IDLE)
        self.assertEqual(c.classify(Event(0, "note", 0, 0, "", "", "done", "")), WORK)
        self.assertEqual(c.classify(Event(0, "file", 0, 0, "", "", "modified", "a.py")), WORK)


if __name__ == "__main__":
    unittest.main()
