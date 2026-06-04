from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QCheckBox, QPushButton, QLabel, QFileDialog,
)
from state import Actor, AppState


class JointSelector(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._checkboxes: dict[str, QCheckBox] = {}
        self._updating = False
        self._build_ui()

        state.actor_added.connect(self._on_actor)
        state.selected_joints_changed.connect(self._sync_checkboxes)
        state.selected_joints_changed.connect(self._update_count)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_label = QLabel("Joints")
        header_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #9a9aa3;")
        header_row.addWidget(header_label)
        header_row.addStretch()
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("font-size: 11px; color: #5d5d65;")
        header_row.addWidget(self._count_label)
        layout.addLayout(header_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        for label, slot in [
            ("All",         self._select_all),
            ("None",        self._select_none),
            ("Save preset", self._save_preset),
            ("Load preset", self._load_preset),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(2, 2, 2, 2)
        self._scroll_layout.setSpacing(2)
        self._scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._scroll_content)
        layout.addWidget(scroll)

    def _on_actor(self, actor: Actor):
        self._checkboxes.clear()
        while self._scroll_layout.count() > 1:
            item = self._scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for name in actor.joint_names:
            cb = QCheckBox(name)
            cb.setChecked(name in self._state.selected_joints)
            cb.toggled.connect(lambda checked, n=name: self._on_checkbox(n, checked))
            self._checkboxes[name] = cb
            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, cb)

        self._update_count()

    def _on_checkbox(self, name: str, checked: bool):
        if not self._updating:
            self._state.set_joint_selected(name, checked)

    def _sync_checkboxes(self, selected: set):
        self._updating = True
        for name, cb in self._checkboxes.items():
            cb.setChecked(name in selected)
        self._updating = False

    def _update_count(self, *_):
        total = len(self._checkboxes)
        if not total:
            self._count_label.setText("")
            return
        n_sel = len(self._state.selected_joints & set(self._checkboxes.keys()))
        self._count_label.setText(f"{n_sel} of {total}")

    def _select_all(self):
        for name in list(self._checkboxes):
            self._state.set_joint_selected(name, True)

    def _select_none(self):
        for name in list(self._checkboxes):
            self._state.set_joint_selected(name, False)

    def _save_preset(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save joint preset", "", "JSON (*.json)"
        )
        if path:
            data = {"joints": sorted(self._state.selected_joints)}
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load joint preset", "", "JSON (*.json)"
        )
        if path:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            want = set(data.get("joints", []))
            for name in list(self._checkboxes):
                self._state.set_joint_selected(name, name in want)
