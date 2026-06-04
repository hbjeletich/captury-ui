from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QBrush, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
)
from state import Actor, Pose, AppState

_STATUS_COLORS: dict[str, tuple[str, str]] = {
    "TRACKING": ("#4ade80", "#18181b"),
    "SCALING":  ("#fbbf24", "#18181b"),
    "STOPPED":  ("#3a3a40", "#9a9aa3"),
    "DELETED":  ("#ef4444", "#e8e8ea"),
}


class _QualityBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self.setFixedSize(72, 7)

    def set_value(self, value: int):
        v = max(0, min(100, value))
        if v != self._value:
            self._value = v
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0x2e, 0x2e, 0x34)))
        p.drawRoundedRect(0, 0, w, h, 3, 3)
        fill = int(w * self._value / 100)
        if fill > 0:
            if self._value >= 70:
                c = QColor(0x4a, 0xde, 0x80)
            elif self._value >= 40:
                c = QColor(0xfb, 0xbf, 0x24)
            else:
                c = QColor(0xef, 0x44, 0x44)
            p.setBrush(QBrush(c))
            p.drawRoundedRect(0, 0, fill, h, 3, 3)


class _FootDot(QLabel):
    def __init__(self, letter: str, parent=None):
        super().__init__(letter, parent)
        self.setFixedSize(18, 18)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set(False)

    def set_contact(self, on: bool):
        self._set(on)

    def _set(self, on: bool):
        if on:
            self.setStyleSheet(
                "background:#4ade80; color:#18181b; border-radius:9px;"
                "font-size:10px; font-weight:700;"
            )
        else:
            self.setStyleSheet(
                "background:#232327; color:#5d5d65; border-radius:9px;"
                "font-size:10px; font-weight:600;"
            )


class _ActorRow(QWidget):
    def __init__(self, actor: Actor, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        display_name = actor.name if actor.name else f"Actor {actor.id}"
        self._name = QLabel(display_name)
        self._name.setStyleSheet("font-weight:600; font-size:12px;")
        self._name.setMinimumWidth(80)
        layout.addWidget(self._name)

        self._badge = QLabel("UNKNOWN")
        self._badge.setFixedWidth(68)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet(
            "font-size:10px; font-weight:700; border-radius:4px;"
            "padding:2px 4px; background:#232327; color:#5d5d65;"
        )
        layout.addWidget(self._badge)

        self._quality_bar = _QualityBar()
        layout.addWidget(self._quality_bar)

        self._quality_num = QLabel("--")
        self._quality_num.setFixedWidth(28)
        self._quality_num.setStyleSheet("font-size:10px; color:#5d5d65; font-family:monospace;")
        layout.addWidget(self._quality_num)

        self._foot_l = _FootDot("L")
        self._foot_r = _FootDot("R")
        layout.addWidget(self._foot_l)
        layout.addWidget(self._foot_r)

        layout.addStretch()

    def update_pose(self, pose: Pose):
        self._quality_bar.set_value(pose.quality)
        self._quality_num.setText(str(pose.quality))
        self._foot_l.set_contact(pose.foot_left)
        self._foot_r.set_contact(pose.foot_right)

    def update_status(self, status: str):
        bg, fg = _STATUS_COLORS.get(status, ("#232327", "#5d5d65"))
        self._badge.setText(status)
        self._badge.setStyleSheet(
            f"font-size:10px; font-weight:700; border-radius:4px;"
            f"padding:2px 4px; background:{bg}; color:{fg};"
        )


class ActorPanel(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._rows: dict[int, _ActorRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)

        header = QLabel("Actors")
        header.setStyleSheet(
            "color:#5d5d65; font-size:11px; font-weight:600;"
            "padding:0 10px; letter-spacing:0.05em;"
        )
        layout.addWidget(header)

        self._container = QWidget()
        self._vbox = QVBoxLayout(self._container)
        self._vbox.setContentsMargins(0, 2, 0, 2)
        self._vbox.setSpacing(2)
        self._vbox.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._container)
        layout.addWidget(scroll, 1)

        state.actor_added.connect(self._on_actor_added)
        state.pose_updated.connect(self._on_pose)
        state.status_updated.connect(self._on_status)
        state.connection_status_changed.connect(self._on_connection_status)

    def _on_actor_added(self, actor: Actor):
        if actor.id not in self._rows:
            row = _ActorRow(actor)
            self._rows[actor.id] = row
            self._vbox.insertWidget(self._vbox.count() - 1, row)
        # Restore status if already in state
        status = self._state.actor_status.get(actor.id)
        if status:
            self._rows[actor.id].update_status(status)

    def _on_pose(self, pose: Pose):
        row = self._rows.get(pose.actor_id)
        if row:
            row.update_pose(pose)

    def _on_status(self, actor_id: int, status: str):
        row = self._rows.get(actor_id)
        if row:
            row.update_status(status)

    def _on_connection_status(self, status: str):
        if status == "Disconnected":
            for row in self._rows.values():
                row.setParent(None)
                row.deleteLater()
            self._rows.clear()
