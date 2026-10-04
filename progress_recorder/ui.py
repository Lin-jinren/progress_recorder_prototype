from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import DB_PATH, EXPORT_DIR, load_config, save_config
from .database import Database
from .file_watcher import FileWatcher
from .reporter import build_ai_prompt, build_daily_stats, make_markdown
from .tracker import ActivityTracker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Progress Recorder")
        self.resize(1050, 700)

        self.config = load_config()
        self.db = Database(DB_PATH)
        self.tracker = ActivityTracker(self.db)
        self.file_watcher = FileWatcher(self.db, self.config.watched_extensions)
        self.recording = False

        self.timer = QTimer(self)
        self.timer.setInterval(self.config.poll_seconds * 1000)
        self.timer.timeout.connect(self._sample_activity)

        self._build_ui()
        self._refresh_table()
        self._update_watch_label()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        title = QLabel("Progress Recorder — 研究 / PPT 工作紀錄雛型")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        privacy = QLabel("只記錄前景程式/視窗標題、你指定資料夾的檔案變更，以及你手動輸入的備註；不截圖、不記鍵盤內容。")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)

        controls = QHBoxLayout()
        self.record_button = QPushButton("開始記錄")
        self.record_button.clicked.connect(self._toggle_recording)
        controls.addWidget(self.record_button)

        add_folder_button = QPushButton("加入監控資料夾")
        add_folder_button.clicked.connect(self._add_watch_folder)
        controls.addWidget(add_folder_button)

        report_button = QPushButton("產生今日進度")
        report_button.clicked.connect(self._generate_report)
        controls.addWidget(report_button)

        ai_prompt_button = QPushButton("複製 AI 整理 Prompt")
        ai_prompt_button.clicked.connect(self._copy_ai_prompt)
        controls.addWidget(ai_prompt_button)

        open_data_button = QPushButton("開啟資料目錄")
        open_data_button.clicked.connect(self._open_data_dir)
        controls.addWidget(open_data_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.status_label = QLabel("狀態：未記錄")
        self.watch_label = QLabel()
        self.watch_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addWidget(self.watch_label)

        note_row = QHBoxLayout()
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("例如：完成 Results 第 8–10 頁；FDTD mesh 問題已解決")
        self.note_input.returnPressed.connect(self._add_note)
        note_row.addWidget(self.note_input)
        note_button = QPushButton("記一筆")
        note_button.clicked.connect(self._add_note)
        note_row.addWidget(note_button)
        layout.addLayout(note_row)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, stretch=1)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["時間", "類型", "程式/檔案", "內容"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.table)

        self.report_preview = QTextEdit()
        self.report_preview.setPlaceholderText("按「產生今日進度」後，Markdown 會出現在這裡。")
        splitter.addWidget(self.report_preview)
        splitter.setSizes([380, 260])

    def _toggle_recording(self) -> None:
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self.recording = True
        self.record_button.setText("停止記錄")
        self.timer.start()
        self.file_watcher.start(self.config.watched_folders)
        self._sample_activity()
        self.status_label.setText("狀態：記錄中")

    def _stop_recording(self) -> None:
        self.recording = False
        self.timer.stop()
        self.tracker.stop_current()
        self.file_watcher.stop()
        self.record_button.setText("開始記錄")
        self.status_label.setText("狀態：已停止")
        self._refresh_table()

    def _sample_activity(self) -> None:
        state = self.tracker.sample()
        if state == "unavailable":
            self.status_label.setText(f"狀態：記錄中；{self.tracker.last_error}")
        else:
            self.status_label.setText("狀態：記錄中")
        self._refresh_table()

    def _add_note(self) -> None:
        text = self.note_input.text().strip()
        if not text:
            return
        self.db.add_event("note", detail=text)
        self.note_input.clear()
        self._refresh_table()

    def _add_watch_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇要監控的工作資料夾")
        if not folder:
            return
        normalized = str(Path(folder).resolve())
        if normalized not in self.config.watched_folders:
            self.config.watched_folders.append(normalized)
            save_config(self.config)
        if self.recording:
            self.file_watcher.start(self.config.watched_folders)
        self._update_watch_label()

    def _update_watch_label(self) -> None:
        if self.config.watched_folders:
            folders = "；".join(self.config.watched_folders)
            self.watch_label.setText(f"監控資料夾：{folders}")
        else:
            self.watch_label.setText("監控資料夾：尚未指定（可只使用前景視窗與手動備註）")

    def _refresh_table(self) -> None:
        events = self.db.latest_events(80)
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            clock = datetime.fromtimestamp(event.started_at).strftime("%m/%d %H:%M:%S")
            if event.event_type == "window":
                subject = event.app_name
                detail = event.title
            elif event.event_type == "file":
                subject = Path(event.file_path).name
                detail = event.detail
            else:
                subject = "手動備註"
                detail = event.detail
            for col, value in enumerate([clock, event.event_type, subject, detail]):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def _generate_report(self) -> None:
        stats = build_daily_stats(self.db, date.today())
        markdown = make_markdown(stats)
        self.report_preview.setPlainText(markdown)

        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = EXPORT_DIR / f"progress-{date.today().isoformat()}.md"
        out.write_text(markdown, encoding="utf-8")
        self.status_label.setText(f"已輸出：{out}")

    def _copy_ai_prompt(self) -> None:
        stats = build_daily_stats(self.db, date.today())
        prompt = build_ai_prompt(stats)
        QApplication.clipboard().setText(prompt)
        self.status_label.setText("AI Prompt 已複製到剪貼簿")

    def _open_data_dir(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DB_PATH.parent)))

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.tracker.stop_current()
        self.file_watcher.stop()
        event.accept()


def run_app() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Progress Recorder")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
