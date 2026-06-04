from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QCheckBox, QScrollArea, QFrame, QSpinBox,
)
from state import AppState, OscDestination


def _mono(w):
    w.setProperty("mono", True)
    return w


class _DestinationRow(QFrame):
    def __init__(self, dest: OscDestination, panel: "DestinationsPanel"):
        super().__init__()
        self._dest = dest
        self._panel = panel
        self.setObjectName("destRow")
        self.setFrameShape(QFrame.Shape.NoFrame)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        self._enabled = QCheckBox()
        self._enabled.setChecked(dest.enabled)
        self._enabled.setToolTip("Enable this destination")
        self._enabled.toggled.connect(self._changed)
        row.addWidget(self._enabled)

        self._ip = _mono(QLineEdit(dest.ip))
        self._ip.setPlaceholderText("IP address")
        self._ip.setFixedWidth(130)
        self._ip.textChanged.connect(self._changed)
        row.addWidget(self._ip)

        colon = QLabel(":")
        colon.setFixedWidth(6)
        colon.setStyleSheet("color: #5d5d65;")
        row.addWidget(colon)

        self._port = _mono(QSpinBox())
        self._port.setRange(1, 65535)
        self._port.setValue(dest.port)
        self._port.setFixedWidth(72)
        self._port.valueChanged.connect(self._changed)
        row.addWidget(self._port)

        self._template = _mono(QLineEdit(dest.address_template))
        self._template.setPlaceholderText("/captury/{actor}/{joint}")
        self._template.setToolTip("{actor} {joint} {timestamp}")
        self._template.textChanged.connect(self._changed)
        row.addWidget(self._template)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Remove destination")
        del_btn.setProperty("ghost", True)
        del_btn.setProperty("danger", True)
        del_btn.clicked.connect(lambda: panel.remove_row(self))
        row.addWidget(del_btn)

    def _changed(self):
        self._dest.ip = self._ip.text().strip()
        self._dest.port = self._port.value()
        template = self._template.text().strip()
        self._dest.address_template = template or "/captury/{actor}/{joint}"
        self._dest.enabled = self._enabled.isChecked()
        self._panel._notify()

    @property
    def destination(self) -> OscDestination:
        return self._dest


class DestinationsPanel(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._rows: list[_DestinationRow] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header = QLabel("OSC Destinations")
        header.setStyleSheet("font-size: 13px; font-weight: 600; color: #9a9aa3;")
        header_row.addWidget(header)
        header_row.addStretch()
        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(24)
        add_btn.setProperty("ghost", True)
        add_btn.clicked.connect(self._add)
        header_row.addWidget(add_btn)
        layout.addLayout(header_row)

        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        self._rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._rows_widget)
        layout.addWidget(scroll)

    def _add(self):
        dest = OscDestination(ip="127.0.0.1", port=7000)
        row = _DestinationRow(dest, self)
        self._rows.append(row)
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        self._notify()

    def remove_row(self, row: _DestinationRow):
        self._rows.remove(row)
        row.deleteLater()
        self._notify()

    def _notify(self):
        self._state.set_destinations([r.destination for r in self._rows])

    def load_destinations(self, destinations: list[OscDestination]):
        for row in list(self._rows):
            row.deleteLater()
        self._rows.clear()
        for dest in destinations:
            row = _DestinationRow(dest, self)
            self._rows.append(row)
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        self._notify()
