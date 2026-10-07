from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .classifier import CATEGORY_LABELS, Classifier
from .config import DB_PATH, load_config
from .database import Database
from .dialogs import FoldersDialog, RulesDialog
from .file_watcher import FileWatcher
from .reporter import human_duration
from .review import ReviewDialog
from .tracker import ActivityTracker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Progress Recorder")
        self.resize(1050, 700)

        self.config = load_config()
        self.db = Database(DB_PATH)
        self.classifier = Classifier(self.config.classification_rules)
        self.tracker = ActivityTracker(
            self.db,
            idle_threshold=self.config.idle_threshold_seconds,
            poll_seconds=self.config.poll_seconds,
        )
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

        privacy = QLabel(
            "只記錄前景程式/視窗標題、你指定資料夾的檔案變更，以及你手動輸入的備註；不截圖、不記鍵盤內容。"
            "閒置偵測只讀取「最後一次操作的時間」。"
        )
        privacy.setWordWrap(True)
        layout.addWidget(privacy)

        controls = QHBoxLayout()
        self.record_button = QPushButton("開始記錄")
        self.record_button.clicked.connect(self._toggle_recording)
        controls.addWidget(self.record_button)

        for label, handler in (
            ("審閱 / 產生報告", self._open_review),
            ("監控資料夾", self._open_folders),
            ("分類規則", self._open_rules),
            ("開啟資料目錄", self._open_data_dir),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            controls.addWidget(button)
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

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["時間", "類型", "分類", "程式/檔案", "內容"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

    # ----- recording ----------------------------------------------------------

    def _toggle_recording(self) -> None:
        if self.recording:
            self._stop_recording()
            self._open_review()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self.recording = True
        self.record_button.setText("結束工作")
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
        elif state == "idle":
            self.status_label.setText("狀態：閒置中（不計入工作時間）")
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

    # ----- dialogs ------------------------------------------------------------

    def _open_review(self) -> None:
        ReviewDialog(self.db, self.config, date.today(), self).exec()
        self._rules_changed()

    def _open_folders(self) -> None:
        FoldersDialog(self.config, self).exec()
        if self.recording:
            self.file_watcher.start(self.config.watched_folders)
        self._update_watch_label()

    def _open_rules(self) -> None:
        RulesDialog(self.config, self).exec()
        self._rules_changed()

    def _rules_changed(self) -> None:
        self.classifier = Classifier(self.config.classification_rules)
        self._refresh_table()

    def _open_data_dir(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DB_PATH.parent)))

    # ----- display ------------------------------------------------------------

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
            elif event.event_type == "idle":
                subject = "閒置"
                detail = human_duration(event.duration_seconds)
            else:
                subject = "手動備註"
                detail = event.detail
            category = CATEGORY_LABELS.get(self.classifier.classify(event), "")
            for col, value in enumerate([clock, event.event_type, category, subject, detail]):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

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
