from __future__ import annotations
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)
from state import AppState


def _set_prop(widget, **props):
    for k, v in props.items():
        widget.setProperty(k, v)


class RecordingPanel(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._bridge = None
        self._recording_start: float | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        rec_lbl = QLabel("Recording")
        rec_lbl.setStyleSheet("color: #9a9aa3;")
        layout.addWidget(rec_lbl)

        shot_lbl = QLabel("Shot")
        shot_lbl.setStyleSheet("color: #5d5d65;")
        layout.addWidget(shot_lbl)

        self._shot_edit = QLineEdit()
        self._shot_edit.setPlaceholderText("take_001")
        self._shot_edit.setFixedWidth(130)
        _set_prop(self._shot_edit, mono=True)
        layout.addWidget(self._shot_edit)

        self._start_btn = QPushButton("● Record")
        self._start_btn.setFixedWidth(90)
        self._start_btn.setFixedHeight(32)
        _set_prop(self._start_btn, primary=True)
        self._start_btn.clicked.connect(self._start_recording)
        layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("■ Stop")
        self._stop_btn.setFixedWidth(70)
        self._stop_btn.setFixedHeight(32)
        self._stop_btn.clicked.connect(self._stop_recording)
        self._stop_btn.setEnabled(False)
        layout.addWidget(self._stop_btn)

        self._elapsed_label = QLabel("")
        self._elapsed_label.setStyleSheet(
            "color: #ef4444; font-family: monospace; font-size: 12px; font-weight: 600;"
        )
        self._elapsed_label.setFixedWidth(58)
        layout.addWidget(self._elapsed_label)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(500)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        state.recording_changed.connect(self._on_recording_changed)

    def set_bridge(self, bridge) -> None:
        self._bridge = bridge

    def _start_recording(self):
        if self._bridge:
            name = self._shot_edit.text().strip()
            if name:
                self._bridge.send_command(f"SET_SHOT {name}")
            self._bridge.send_command("START_RECORDING")
        # Optimistic UI update
        self._on_recording_changed(True)

    def _stop_recording(self):
        if self._bridge:
            self._bridge.send_command("STOP_RECORDING")
        self._on_recording_changed(False)

    def _on_recording_changed(self, recording: bool):
        if recording:
            self._recording_start = time.monotonic()
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
            _set_prop(self._start_btn, primary=False)
            self._start_btn.style().unpolish(self._start_btn)
            self._start_btn.style().polish(self._start_btn)
            self._elapsed_timer.start()
            self._tick_elapsed()
        else:
            self._recording_start = None
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
            _set_prop(self._start_btn, primary=True)
            self._start_btn.style().unpolish(self._start_btn)
            self._start_btn.style().polish(self._start_btn)
            self._elapsed_timer.stop()
            self._elapsed_label.setText("")

    def _tick_elapsed(self):
        if self._recording_start is None:
            return
        secs = int(time.monotonic() - self._recording_start)
        m, s = divmod(secs, 60)
        self._elapsed_label.setText(f"● {m:02d}:{s:02d}")
