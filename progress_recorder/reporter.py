from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .database import Database, Event


@dataclass
class DailyStats:
    target_date: date
    events: list[Event]
    app_seconds: dict[str, float]
    file_counts: dict[str, int]
    notes: list[str]


def build_daily_stats(db: Database, target_date: date) -> DailyStats:
    events = db.events_for_day(target_date)
    app_seconds: dict[str, float] = defaultdict(float)
    file_counts: Counter[str] = Counter()
    notes: list[str] = []

    for event in events:
        if event.event_type == "window":
            app_seconds[event.app_name or "Unknown app"] += event.duration_seconds
        elif event.event_type == "file" and event.file_path:
            file_counts[event.file_path] += 1
        elif event.event_type == "note" and event.detail.strip():
            notes.append(event.detail.strip())

    return DailyStats(
        target_date=target_date,
        events=events,
        app_seconds=dict(app_seconds),
        file_counts=dict(file_counts),
        notes=notes,
    )


def _human_duration(seconds: float) -> str:
    minutes = max(0, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} 分鐘"
    hours, mins = divmod(minutes, 60)
    return f"{hours} 小時 {mins} 分鐘" if mins else f"{hours} 小時"


def make_markdown(stats: DailyStats) -> str:
    lines = [f"# {stats.target_date.isoformat()} 進度紀錄", ""]

    lines.append("## 今日摘要")
    if not stats.events:
        lines.append("今天尚未記錄活動。")
    else:
        total_work = sum(stats.app_seconds.values())
        unique_files = len(stats.file_counts)
        lines.append(
            f"共記錄 {_human_duration(total_work)} 的前景工作時間，"
            f"偵測到 {unique_files} 個工作檔案有變更，手動備註 {len(stats.notes)} 筆。"
        )
    lines.append("")

    lines.append("## 主要使用程式")
    if stats.app_seconds:
        for app, seconds in sorted(stats.app_seconds.items(), key=lambda item: item[1], reverse=True)[:8]:
            lines.append(f"- {app}: {_human_duration(seconds)}")
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

    lines.append("## 原始時間軸")
    for event in stats.events[-40:]:
        clock = datetime.fromtimestamp(event.started_at).strftime("%H:%M")
        if event.event_type == "window":
            text = f"{event.app_name} — {event.title}".strip(" —")
        elif event.event_type == "file":
            text = f"檔案 {event.detail}: {Path(event.file_path).name}"
        else:
            text = event.detail
        lines.append(f"- {clock} {text}")

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

原始紀錄：
{raw}
"""
