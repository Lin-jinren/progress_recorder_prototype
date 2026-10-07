from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .blocks import UnknownItem, WorkBlock, build_blocks, unknown_items
from .classifier import IDLE, IGNORED, NONWORK, UNKNOWN, WORK, Classifier, clean_title
from .database import Database, Event, day_bounds

# Window runs shorter than this are alt-tab noise in the timeline (still counted in totals).
MIN_TIMELINE_SECONDS = 10


@dataclass
class DailyStats:
    target_date: date
    events: list[Event]
    categories: dict[int, str]  # event id -> category
    category_seconds: dict[str, float]
    app_seconds: dict[str, float]  # work windows only
    unknown_seconds: dict[str, float]  # "app — title" -> seconds, for user review
    file_counts: dict[str, int]
    notes: list[str]
    blocks: list[WorkBlock]
    unknown_items: list[UnknownItem]


def _clipped_seconds(event: Event, day_start: float, day_end: float) -> float:
    return max(0.0, min(event.ended_at, day_end) - max(event.started_at, day_start))


def build_daily_stats(
    db: Database, target_date: date, classifier: Optional[Classifier] = None
) -> DailyStats:
    classifier = classifier or Classifier()
    day_start, day_end = day_bounds(target_date)
    events = db.events_for_day(target_date)

    categories: dict[int, str] = {}
    category_seconds: dict[str, float] = defaultdict(float)
    app_seconds: dict[str, float] = defaultdict(float)
    unknown_seconds: dict[str, float] = defaultdict(float)
    file_counts: Counter[str] = Counter()
    notes: list[str] = []

    for event in events:
        category = classifier.classify(event)
        categories[event.id] = category
        seconds = _clipped_seconds(event, day_start, day_end)
        category_seconds[category] += seconds

        if event.event_type == "window":
            app = event.app_name or "Unknown app"
            if category == WORK:
                app_seconds[app] += seconds
            elif category == UNKNOWN:
                unknown_seconds[f"{app} — {clean_title(event.title)}".strip(" —")] += seconds
        elif event.event_type == "file" and event.file_path:
            file_counts[event.file_path] += 1
        elif event.event_type == "note" and event.detail.strip():
            notes.append(event.detail.strip())

    return DailyStats(
        target_date=target_date,
        events=events,
        categories=categories,
        category_seconds=dict(category_seconds),
        app_seconds=dict(app_seconds),
        unknown_seconds=dict(unknown_seconds),
        file_counts=dict(file_counts),
        notes=notes,
        blocks=build_blocks(events, categories, day_start, day_end),
        unknown_items=unknown_items(events, categories, day_start, day_end),
    )


def human_duration(seconds: float) -> str:
    minutes = max(0, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} 分鐘"
    hours, mins = divmod(minutes, 60)
    return f"{hours} 小時 {mins} 分鐘" if mins else f"{hours} 小時"


def _clock(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M")


def _work_timeline(stats: DailyStats) -> list[str]:
    """Work (and unclassified) activity only, with consecutive windows of one app merged."""
    entries: list[tuple[float, str]] = []
    run: Optional[dict] = None

    def flush() -> None:
        nonlocal run
        if run and run["end"] - run["start"] >= MIN_TIMELINE_SECONDS:
            titles = run["titles"]
            shown = " / ".join(titles[:3])
            if len(titles) > 3:
                shown += f" …等 {len(titles)} 個視窗"
            mark = "（未分類）" if run["category"] == UNKNOWN else ""
            text = f"{_clock(run['start'])}–{_clock(run['end'])} {run['app']}{mark}"
            entries.append((run["start"], f"{text}：{shown}" if shown else text))
        run = None

    for event in stats.events:
        category = stats.categories[event.id]
        if category == IGNORED:
            continue  # taskbar / quick settings must not split a run
        if category in (NONWORK, IDLE):
            flush()
        elif event.event_type == "window":
            key = (event.app_name, category)
            if run is None or run["key"] != key:
                flush()
                run = {
                    "key": key,
                    "app": event.app_name or "Unknown app",
                    "category": category,
                    "start": event.started_at,
                    "end": event.ended_at,
                    "titles": [],
                }
            run["end"] = max(run["end"], event.ended_at)
            title = clean_title(event.title)
            if title and title not in run["titles"]:
                run["titles"].append(title)
        elif event.event_type == "file":
            entries.append((event.started_at, f"{_clock(event.started_at)} 檔案 {event.detail}: {Path(event.file_path).name}"))
        elif event.event_type == "note":
            entries.append((event.started_at, f"{_clock(event.started_at)} 備註：{event.detail}"))
    flush()

    return [f"- {text}" for _, text in sorted(entries, key=lambda item: item[0])]


def make_markdown(stats: DailyStats) -> str:
    lines = [f"# {stats.target_date.isoformat()} 進度紀錄", ""]
    seconds = stats.category_seconds

    lines.append("## 今日摘要")
    if not stats.events:
        lines.append("今天尚未記錄活動。")
    else:
        lines.append(
            f"工作 {human_duration(seconds.get(WORK, 0))}"
            f"（另有未分類 {human_duration(seconds.get(UNKNOWN, 0))}；"
            f"非工作 {human_duration(seconds.get(NONWORK, 0))}、"
            f"閒置 {human_duration(seconds.get(IDLE, 0))} 不計入）。"
        )
        lines.append(
            f"偵測到 {len(stats.file_counts)} 個工作檔案有變更，手動備註 {len(stats.notes)} 筆。"
        )
    lines.append("")

    lines.append("## 主要工作程式")
    if stats.app_seconds:
        for app, secs in sorted(stats.app_seconds.items(), key=lambda item: item[1], reverse=True)[:8]:
            lines.append(f"- {app}: {human_duration(secs)}")
    else:
        lines.append("- 尚無資料")
    lines.append("")

    lines.append("## 修改過的檔案")
    if stats.file_counts:
        for path, count in sorted(stats.file_counts.items(), key=lambda item: item[1], reverse=True)[:20]:
            lines.append(f"- {Path(path).name}（偵測到 {count} 次儲存/變更）")
    else:
        lines.append("- 尚無資料")
    lines.append("")

    lines.append("## 我手動記下的重要進度")
    if stats.notes:
        for note in stats.notes:
            lines.append(f"- {note}")
    else:
        lines.append("- 尚無手動備註")
    lines.append("")

    unknown = [
        (label, secs) for label, secs in sorted(stats.unknown_seconds.items(), key=lambda item: item[1], reverse=True)
        if secs >= 60
    ][:10]
    if unknown:
        lines.append("## 未分類活動（請確認是否為工作）")
        for label, secs in unknown:
            lines.append(f"- {label}: {human_duration(secs)}")
        lines.append("")

    lines.append("## 工作時間軸")
    timeline = _work_timeline(stats)
    lines.extend(timeline or ["- 尚無資料"])

    return "\n".join(lines).strip() + "\n"


def build_ai_prompt(stats: DailyStats) -> str:
    """A provider-neutral prompt. Later you can send this to any LLM API."""
    raw = make_markdown(stats)
    return f"""你是研究工作進度整理助手。請根據下列原始紀錄，產生簡潔、具體、不可臆測的進度摘要。

規則：
1. 只描述紀錄中確實出現的工作，不要猜測使用者完成了什麼。
2. 格式固定為：今日完成、遇到問題、目前狀態、下一步。
3. 如果資料不足，就明確寫「紀錄不足」。
4. 優先保留檔名、軟體名稱與使用者手動輸入的備註。
5. 標記為「未分類」的活動不一定是工作；除非它和其他工作紀錄明顯相關，否則不要寫進摘要。

原始紀錄：
{raw}
"""


# ---------------------------------------------------------------------------
# Reviewed report: the user picked which work blocks to keep and which to detail.

SKIP = "skip"
BRIEF = "brief"
DETAIL = "detail"
LEVEL_LABELS = {SKIP: "不記錄", BRIEF: "簡述", DETAIL: "重點詳述"}


@dataclass
class ReviewedBlock:
    block: WorkBlock
    level: str = BRIEF
    comment: str = ""


def time_range(block: WorkBlock) -> str:
    return f"{_clock(block.start)}–{_clock(block.end)}"


def block_summary(block: WorkBlock) -> str:
    """One line describing a block: programs | main windows | files | notes."""
    parts = []
    if block.app_seconds:
        parts.append("、".join(f"{app} {human_duration(secs)}" for app, secs in block.top_apps()))
    titles = block.top_titles(3)
    if titles:
        parts.append("、".join(titles))
    files = block.top_files(3)
    if files:
        parts.append("檔案：" + "、".join(f"{name}×{count}" for name, count in files))
    if block.notes:
        parts.append("備註：" + "；".join(block.notes))
    return "｜".join(parts) or "（無細節）"


def make_review_markdown(target_date: date, reviewed: list[ReviewedBlock]) -> str:
    kept = [r for r in reviewed if r.level != SKIP]
    details = [r for r in kept if r.level == DETAIL]
    briefs = [r for r in kept if r.level == BRIEF]
    total = sum(r.block.work_seconds for r in kept)

    lines = [f"# {target_date.isoformat()} 工作進度", ""]
    if not kept:
        lines.append("今天沒有選擇要記錄的工作。")
        return "\n".join(lines) + "\n"
    lines.append(f"工作時間：{human_duration(total)}（{len(kept)} 個工作區塊）")
    lines.append("")

    if details:
        lines.append("## 重點")
        lines.append("")
        for r in details:
            b = r.block
            lines.append(f"### {time_range(b)}（{human_duration(b.work_seconds)}）")
            if r.comment.strip():
                lines.append("")
                lines.append(r.comment.strip())
                lines.append("")
            if b.app_seconds:
                lines.append("- 使用程式：" + "、".join(
                    f"{app} {human_duration(secs)}" for app, secs in b.top_apps(8)))
            titles = b.top_titles(8)
            if titles:
                lines.append("- 主要視窗：" + "、".join(titles))
            files = b.top_files(20)
            if files:
                lines.append("- 修改檔案：" + "、".join(f"{name}（{count} 次）" for name, count in files))
            for note in b.notes:
                lines.append(f"- 備註：{note}")
            lines.append("")

    if briefs:
        lines.append("## 其他工作")
        lines.append("")
        for r in briefs:
            b = r.block
            text = block_summary(b)
            if r.comment.strip():
                text = f"{r.comment.strip()}（{text}）"
            lines.append(f"- {time_range(b)}（{human_duration(b.work_seconds)}）{text}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def build_review_ai_prompt(target_date: date, reviewed: list[ReviewedBlock]) -> str:
    """Provider-neutral prompt built only from blocks the user chose to keep."""
    raw = make_review_markdown(target_date, reviewed)
    return f"""你是研究工作進度整理助手。下列是使用者審閱過的今日工作紀錄，請整理成可直接貼到 Notion 或簡報的進度報告。

規則：
1. 只根據紀錄內容撰寫，不要臆測使用者完成了什麼；資料不足時寫「紀錄不足」。
2. 「重點」中的每個區塊寫成一段具體說明（做了什麼、結果、遇到的問題）；使用者寫的說明最重要，以它為主。
3. 「其他工作」每項濃縮成一行。
4. 最後加「下一步」，只有在說明或備註中提到時才寫，否則省略。
5. 保留檔名、軟體名稱與使用者的原文說明；使用繁體中文、Markdown 格式。

紀錄：
{raw}
"""
