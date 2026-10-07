"""End-of-day review: classify leftovers, pick which work blocks go into the report."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .classifier import IGNORED, NONWORK, UNKNOWN, WORK, Classifier
from .config import EXPORT_DIR, AppConfig
from .database import Database
from .dialogs import add_rule_interactively
from .reporter import (
    BRIEF,
    LEVEL_LABELS,
    ReviewedBlock,
    block_summary,
    build_daily_stats,
    build_review_ai_prompt,
    human_duration,
    make_markdown,
    make_review_markdown,
    time_range,
)

LEVEL_COL = 3
COMMENT_COL = 4


def _readonly(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class ReviewDialog(QDialog):
    def __init__(self, db: Database, config: AppConfig, target: date, parent=None):
        super().__init__(parent)
        self.db = db
        self.config = config
        # Block start time -> (level, comment); survives re-classification refreshes.
        self._choices: dict[float, tuple[str, str]] = {}
        self._row_keys: list[float] = []
        self.setWindowTitle("Progress Recorder — 審閱工作")
        self.resize(1150, 820)
        self._build_ui(target)
        self._reload()

    # ----- layout -------------------------------------------------------------

    def _build_ui(self, target: date) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("日期："))
        self.date_edit = QDateEdit(QDate(target.year, target.month, target.day))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self._date_changed)
        top.addWidget(self.date_edit)
        self.summary_label = QLabel()
        top.addWidget(self.summary_label, stretch=1)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, stretch=1)

        # 1. Unclassified activity -> rules
        unknown_box = QWidget()
        unknown_layout = QVBoxLayout(unknown_box)
        unknown_layout.setContentsMargins(0, 0, 0, 0)
        unknown_layout.addWidget(QLabel(
            "① 未分類項目：選取後設定分類，會存成規則，之後自動套用（也會套用到過去的紀錄）。"
        ))
        self.unknown_table = QTableWidget(0, 3)
        self.unknown_table.setHorizontalHeaderLabels(["項目", "依據", "時間"])
        self.unknown_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.unknown_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.unknown_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.unknown_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        unknown_layout.addWidget(self.unknown_table)
        rule_buttons = QHBoxLayout()
        for label, category in (("設為工作…", WORK), ("設為非工作…", NONWORK), ("忽略…", IGNORED)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, c=category: self._classify_selected(c))
            rule_buttons.addWidget(button)
        rule_buttons.addStretch()
        unknown_layout.addLayout(rule_buttons)
        splitter.addWidget(unknown_box)

        # 2. Work blocks -> report choices
        blocks_box = QWidget()
        blocks_layout = QVBoxLayout(blocks_box)
        blocks_layout.setContentsMargins(0, 0, 0, 0)
        blocks_layout.addWidget(QLabel(
            "② 工作區塊：決定每段要不要寫進報告；「補充說明」可雙擊輸入，例如「完成 Results 第 8–10 頁」。"
        ))
        self.block_table = QTableWidget(0, 5)
        self.block_table.setHorizontalHeaderLabels(["時間", "工作時長", "內容", "處理", "補充說明"])
        self.block_table.setWordWrap(True)
        header = self.block_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(LEVEL_COL, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COMMENT_COL, QHeaderView.ResizeMode.Interactive)
        self.block_table.setColumnWidth(COMMENT_COL, 280)
        blocks_layout.addWidget(self.block_table)
        splitter.addWidget(blocks_box)

        # 3. Output preview
        self.preview = QTextEdit()
        self.preview.setPlaceholderText("③ 按「預覽」或「輸出 .md」後，報告會出現在這裡。")
        splitter.addWidget(self.preview)
        splitter.setSizes([220, 340, 260])

        buttons = QHBoxLayout()
        for label, handler in (
            ("預覽", self._show_preview),
            ("輸出 .md", self._export_markdown),
            ("複製 AI Prompt", self._copy_ai_prompt),
            ("匯出原始紀錄", self._export_raw),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.status_label = QLabel()
        buttons.addWidget(self.status_label, stretch=1)
        close = QPushButton("關閉")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    # ----- data ---------------------------------------------------------------

    def target_date(self) -> date:
        return self.date_edit.date().toPython()

    def _date_changed(self) -> None:
        self._choices = {}
        self._row_keys = []
        self.preview.clear()
        self._reload()

    def _reload(self) -> None:
        self._capture_choices()
        classifier = Classifier(self.config.classification_rules)
        self.stats = build_daily_stats(self.db, self.target_date(), classifier)
        self._fill_unknown()
        self._fill_blocks()

        seconds = self.stats.category_seconds
        self.summary_label.setText(
            f"工作 {human_duration(seconds.get(WORK, 0))}，{len(self.stats.blocks)} 個區塊；"
            f"未分類 {human_duration(seconds.get(UNKNOWN, 0))}"
        )

    def _fill_unknown(self) -> None:
        items = self.stats.unknown_items
        self.unknown_table.setRowCount(len(items))
        for row, item in enumerate(items):
            basis = "網頁標題" if item.field == "title" else "程式"
            label = item.value if item.field == "app" else f"{item.value}（{item.app_name}）"
            for col, text in enumerate([label, basis, human_duration(item.seconds)]):
                self.unknown_table.setItem(row, col, QTableWidgetItem(text))

    def _fill_blocks(self) -> None:
        blocks = self.stats.blocks
        self._row_keys = [round(b.start) for b in blocks]
        self.block_table.setRowCount(0)  # drop old rows and their combo boxes
        self.block_table.setRowCount(len(blocks))
        for row, block in enumerate(blocks):
            level, comment = self._choices.get(self._row_keys[row], (BRIEF, ""))
            self.block_table.setItem(row, 0, _readonly(time_range(block)))
            self.block_table.setItem(row, 1, _readonly(human_duration(block.work_seconds)))
            self.block_table.setItem(row, 2, _readonly(block_summary(block)))
            combo = QComboBox()
            for key, label in LEVEL_LABELS.items():
                combo.addItem(label, key)
            combo.setCurrentIndex(max(0, combo.findData(level)))
            self.block_table.setCellWidget(row, LEVEL_COL, combo)
            self.block_table.setItem(row, COMMENT_COL, QTableWidgetItem(comment))
        self.block_table.resizeRowsToContents()

    def _capture_choices(self) -> None:
        for row, key in enumerate(self._row_keys):
            combo = self.block_table.cellWidget(row, LEVEL_COL)
            item = self.block_table.item(row, COMMENT_COL)
            if combo is not None:
                self._choices[key] = (combo.currentData(), item.text() if item else "")

    def reviewed_blocks(self) -> list[ReviewedBlock]:
        self._capture_choices()
        return [
            ReviewedBlock(block, *self._choices.get(key, (BRIEF, "")))
            for key, block in zip(self._row_keys, self.stats.blocks)
        ]

    # ----- actions ------------------------------------------------------------

    def _classify_selected(self, category: str) -> None:
        rows = self.unknown_table.selectionModel().selectedRows()
        if not rows:
            self.status_label.setText("請先在①選一個項目")
            return
        item = self.stats.unknown_items[rows[0].row()]
        if add_rule_interactively(self.config, self, item.field, item.value, category):
            self._reload()
            self.status_label.setText("規則已儲存")

    def _show_preview(self) -> str:
        markdown = make_review_markdown(self.target_date(), self.reviewed_blocks())
        self.preview.setPlainText(markdown)
        return markdown

    def _export_markdown(self) -> None:
        markdown = self._show_preview()
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = EXPORT_DIR / f"progress-{self.target_date().isoformat()}.md"
        out.write_text(markdown, encoding="utf-8")
        self.status_label.setText(f"已輸出：{out}")

    def _copy_ai_prompt(self) -> None:
        prompt = build_review_ai_prompt(self.target_date(), self.reviewed_blocks())
        QApplication.clipboard().setText(prompt)
        self.status_label.setText("AI Prompt 已複製，可直接貼到任何 AI 聊天框")

    def _export_raw(self) -> None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = EXPORT_DIR / f"raw-{self.target_date().isoformat()}.md"
        out.write_text(make_markdown(self.stats), encoding="utf-8")
        self.status_label.setText(f"已輸出原始紀錄：{out}")
