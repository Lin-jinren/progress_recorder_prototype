"""Small settings dialogs. Every change is saved to config.json immediately."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .classifier import CATEGORY_LABELS, RULE_CATEGORIES
from .config import AppConfig, save_config

FIELD_LABELS = {"app": "程式名稱", "title": "視窗標題"}


class FoldersDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Progress Recorder — 監控資料夾")
        self.resize(640, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "這些資料夾（含子資料夾）中的工作檔案被新增、修改或移動時會被記錄。\n"
            "副檔名：" + " ".join(config.watched_extensions)
        ))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list)

        buttons = QHBoxLayout()
        add = QPushButton("新增…")
        add.clicked.connect(self._add)
        remove = QPushButton("移除選取")
        remove.clicked.connect(self._remove)
        close = QPushButton("關閉")
        close.clicked.connect(self.accept)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        self.list.addItems(self.config.watched_folders)

    def _add(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇要監控的工作資料夾")
        if not folder:
            return
        normalized = str(Path(folder).resolve())
        if normalized not in self.config.watched_folders:
            self.config.watched_folders.append(normalized)
            save_config(self.config)
            self._refresh()

    def _remove(self) -> None:
        selected = {item.text() for item in self.list.selectedItems()}
        if not selected:
            return
        self.config.watched_folders = [f for f in self.config.watched_folders if f not in selected]
        save_config(self.config)
        self._refresh()


class RuleEditDialog(QDialog):
    """Create one classification rule; returns it via `rule` after exec()."""

    def __init__(self, field: str = "app", contains: str = "", category: str = "work", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Progress Recorder — 新增分類規則")
        self.resize(520, 200)
        self.rule: Optional[dict] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.field_box = QComboBox()
        for key, label in FIELD_LABELS.items():
            self.field_box.addItem(label, key)
        self.field_box.setCurrentIndex(max(0, self.field_box.findData(field)))
        form.addRow("比對", self.field_box)

        self.contains_edit = QLineEdit(contains)
        form.addRow("包含文字", self.contains_edit)

        self.category_box = QComboBox()
        for key in RULE_CATEGORIES:
            self.category_box.addItem(CATEGORY_LABELS[key], key)
        self.category_box.setCurrentIndex(max(0, self.category_box.findData(category)))
        form.addRow("分類為", self.category_box)
        layout.addLayout(form)

        hint = QLabel("不分大小寫，只要包含這段文字就符合。網頁標題建議只留關鍵字，例如「Synology NAS」。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        contains = self.contains_edit.text().strip()
        if not contains:
            return
        self.rule = {
            "field": self.field_box.currentData(),
            "contains": contains,
            "category": self.category_box.currentData(),
        }
        self.accept()


def add_rule_interactively(
    config: AppConfig, parent, field: str = "app", contains: str = "", category: str = "work"
) -> bool:
    """Ask for a rule and save it. Newest rules go first so they win over older ones."""
    dialog = RuleEditDialog(field, contains, category, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted or dialog.rule is None:
        return False
    config.classification_rules.insert(0, dialog.rule)
    save_config(config)
    return True


class RulesDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Progress Recorder — 分類規則")
        self.resize(640, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("你的規則（由上往下，第一條符合的生效；優先於內建規則）："))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["比對", "包含文字", "分類為"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        add = QPushButton("新增…")
        add.clicked.connect(self._add)
        remove = QPushButton("刪除選取")
        remove.clicked.connect(self._remove)
        close = QPushButton("關閉")
        close.clicked.connect(self.accept)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._refresh()

    def _refresh(self) -> None:
        rules = self.config.classification_rules
        self.table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            values = [
                FIELD_LABELS.get(rule.get("field", ""), rule.get("field", "")),
                rule.get("contains", ""),
                CATEGORY_LABELS.get(rule.get("category", ""), rule.get("category", "")),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def _add(self) -> None:
        if add_rule_interactively(self.config, self):
            self._refresh()

    def _remove(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        if not rows:
            return
        self.config.classification_rules = [
            rule for i, rule in enumerate(self.config.classification_rules) if i not in rows
        ]
        save_config(self.config)
        self._refresh()
