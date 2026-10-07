"""Decide whether each recorded event was work.

Rules are plain substring matches (case-insensitive) on the process name ("app")
or the window title ("title"). The first matching rule wins. User rules from
config.json are checked before the built-in defaults, so they can override them:

    "classification_rules": [
        {"field": "title", "contains": "lecture", "category": "work"},
        {"field": "app", "contains": "line.exe", "category": "nonwork"}
    ]

Users normally create these from the review dialog instead of editing JSON.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .database import Event

WORK = "work"
NONWORK = "nonwork"
UNKNOWN = "unknown"
IDLE = "idle"
IGNORED = "ignored"  # OS shell surfaces etc.: neither work nor a break

CATEGORY_LABELS = {
    WORK: "工作",
    NONWORK: "非工作",
    UNKNOWN: "未分類",
    IDLE: "閒置",
    IGNORED: "忽略",
}
# Categories a user rule may assign.
RULE_CATEGORIES = (WORK, NONWORK, IGNORED)


@dataclass(frozen=True)
class Rule:
    field: str  # "app" | "title"
    contains: str  # lowercase substring
    category: str  # one of RULE_CATEGORIES


def _rules(field: str, category: str, needles: Iterable[str]) -> list[Rule]:
    return [Rule(field, needle.lower(), category) for needle in needles]


# Order matters: dedicated work tools first (so a VS Code file named
# "youtube_api.py" is still work), then distractions, then browser-title hints.
# Browsers themselves are deliberately left UNKNOWN.
DEFAULT_RULES: list[Rule] = [
    *_rules("app", IGNORED, [
        "shellhost.exe", "shellexperiencehost.exe", "searchhost.exe",
        "startmenuexperiencehost.exe", "lockapp.exe", "searchapp.exe",
    ]),
    *_rules("app", WORK, [
        "powerpnt.exe", "winword.exe", "excel.exe", "onenote",
        "code.exe", "cursor.exe", "pycharm", "spyder", "notepad++",
        "matlab", "fdtd", "mode-solutions", "lumerical", "comsol", "ansys",
        "origin64.exe", "igor", "texstudio", "texworks", "inkscape",
        "acrobat", "acrord32", "sumatrapdf", "zotero", "mendeley",
        "obsidian", "notion", "windowsterminal", "powershell", "cmd.exe",
    ]),
    *_rules("app", NONWORK, [
        "spotify", "steam", "epicgameslauncher", "battle.net",
        "leagueclient", "riotclient",
    ]),
    *_rules("title", NONWORK, [
        "youtube", "netflix", "twitch", "bilibili", "facebook", "instagram",
        "threads", "dcard", "巴哈姆特", "動畫瘋", "disney+", "reddit",
        "蝦皮購物", "momo購物", "pchome",
    ]),
    *_rules("title", WORK, [
        "overleaf", "google scholar", "arxiv", "ieee xplore", "sciencedirect",
        "researchgate", "jupyter", "github", "stack overflow",
    ]),
]

BROWSERS = {
    "msedge.exe", "chrome.exe", "firefox.exe", "brave.exe", "opera.exe",
    "vivaldi.exe", "arc.exe",
}

_ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
_OTHER_TABS = re.compile(r"\s*(和其他\s*\d+\s*個頁面|and \d+ more pages?)", re.IGNORECASE)
_APP_SUFFIX = re.compile(
    r"\s+[-—]\s+(Microsoft Edge|Google Chrome|Mozilla Firefox|Brave|Opera|Vivaldi"
    r"|Visual Studio Code|Cursor|PowerPoint|Word|Excel|Discord|AnyDesk)$",
    re.IGNORECASE,
)
_BROWSER_PROFILE = re.compile(r"\s+-\s+(個人|Personal|Profile|設定檔)\s*\d*$", re.IGNORECASE)
_PREFIX = re.compile(r"^(\(\d+\)\s*|[●•*]\s*)+")


def is_browser(app_name: str) -> bool:
    return app_name.lower() in BROWSERS


def clean_title(title: str) -> str:
    """Drop browser / editor decoration so only the page or document name is left.

    "foo 和其他 9 個頁面 - 個人 2 - Microsoft Edge" -> "foo"
    "● sweep.py - lab - Visual Studio Code"          -> "sweep.py - lab"
    """
    text = _ZERO_WIDTH.sub("", title).strip()
    text = _APP_SUFFIX.sub("", text)
    text = _BROWSER_PROFILE.sub("", text)
    text = _OTHER_TABS.sub("", text)
    text = _PREFIX.sub("", text)
    return text.strip() or title.strip()


def parse_user_rules(raw_rules: Iterable[dict]) -> list[Rule]:
    """Turn config.json rules into Rule objects, skipping malformed entries."""
    rules = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        field = str(raw.get("field", "")).lower()
        contains = str(raw.get("contains", "")).strip().lower()
        category = str(raw.get("category", "")).lower()
        if field in ("app", "title") and contains and category in RULE_CATEGORIES:
            rules.append(Rule(field, contains, category))
    return rules


class Classifier:
    def __init__(self, user_rules: Iterable[dict] = ()):
        self.user_rules = parse_user_rules(user_rules)

    def classify(self, event: Event) -> str:
        if event.event_type == "idle":
            return IDLE
        if event.event_type in ("file", "note"):
            # File changes come from folders the user chose; notes are typed on purpose.
            return WORK
        if event.event_type != "window":
            return UNKNOWN

        app = event.app_name.lower()
        title = _ZERO_WIDTH.sub("", event.title).lower()
        category = self._match(self.user_rules, app, title)
        if category:
            return category
        if not title.strip():
            # Taskbar, desktop and other untitled shell surfaces.
            return IGNORED
        return self._match(DEFAULT_RULES, app, title) or UNKNOWN

    @staticmethod
    def _match(rules: list[Rule], app: str, title: str) -> str:
        for rule in rules:
            haystack = app if rule.field == "app" else title
            if rule.contains in haystack:
                return rule.category
        return ""
