from __future__ import annotations
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
)
from state import AppState


class AnglesPanel(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._filter = ""
        self._updating = False  # blocks itemChanged re-entrancy

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header row
        header_row = QHBoxLayout()
        header_lbl = QLabel("Biomechanical Angles")
        header_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#9a9aa3;")
        header_row.addWidget(header_lbl)
        header_row.addStretch()
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("font-size:11px; color:#5d5d65;")
        header_row.addWidget(self._count_lbl)
        layout.addLayout(header_row)

        # Filter + OSC select buttons
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter angles…")
        self._search.textChanged.connect(self._on_filter_changed)
        ctrl_row.addWidget(self._search, 1)

        osc_lbl = QLabel("OSC:")
        osc_lbl.setStyleSheet("color:#5d5d65; font-size:11px;")
        ctrl_row.addWidget(osc_lbl)

        all_btn = QPushButton("All")
        all_btn.setFixedHeight(24)
        all_btn.clicked.connect(self._select_all)
        ctrl_row.addWidget(all_btn)

        none_btn = QPushButton("None")
        none_btn.setFixedHeight(24)
        none_btn.clicked.connect(self._select_none)
        ctrl_row.addWidget(none_btn)

        layout.addLayout(ctrl_row)

        # Table: [OSC checkbox] | [Angle name] | [° value]
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["OSC", "Angle", "°"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 36)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 72)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table, 1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(100)  # 10 Hz
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()

        state.connection_status_changed.connect(self._on_connection_status)
        state.selected_angles_changed.connect(self._sync_checkboxes)

    # ------------------------------------------------------------------
    # Angle selection
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != 0 or self._updating:
            return
        row = item.row()
        name_item = self._table.item(row, 1)
        if name_item:
            checked = item.checkState() == Qt.CheckState.Checked
            self._state.set_angle_selected(name_item.text(), checked)

    def _sync_checkboxes(self, selected: set):
        self._updating = True
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, 0)
            name_item = self._table.item(row, 1)
            if chk and name_item:
                state = Qt.CheckState.Checked if name_item.text() in selected else Qt.CheckState.Unchecked
                chk.setCheckState(state)
        self._updating = False

    def _select_all(self):
        for name, _ in self._visible_angles():
            self._state.selected_angles.add(name)
        self._state.selected_angles_changed.emit(set(self._state.selected_angles))

    def _select_none(self):
        for name, _ in self._visible_angles():
            self._state.selected_angles.discard(name)
        self._state.selected_angles_changed.emit(set(self._state.selected_angles))

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def _on_filter_changed(self, text: str):
        self._filter = text.lower()
        self._rebuild_rows()

    def _on_connection_status(self, status: str):
        if status == "Disconnected":
            self._updating = True
            self._table.setRowCount(0)
            self._updating = False
            self._count_lbl.setText("")

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _collect_angles(self) -> dict[str, float]:
        merged: dict[str, float] = {}
        actors = self._state.actor_angles
        if len(actors) == 1:
            merged = dict(next(iter(actors.values())))
        else:
            for actor_id, angles in actors.items():
                for name, val in angles.items():
                    merged[f"A{actor_id}:{name}"] = val
        return merged

    def _visible_angles(self) -> list[tuple[str, float]]:
        angles = self._collect_angles()
        flt = self._filter
        return [
            (name, val) for name, val in sorted(angles.items())
            if not flt or flt in name.lower()
        ]

    # ------------------------------------------------------------------
    # Table build / refresh
    # ------------------------------------------------------------------

    def _rebuild_rows(self):
        self._updating = True
        visible = self._visible_angles()
        selected = self._state.selected_angles

        self._table.setRowCount(len(visible))
        for row, (name, val) in enumerate(visible):
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(
                Qt.CheckState.Checked if name in selected else Qt.CheckState.Unchecked
            )
            self._table.setItem(row, 0, chk_item)

            name_item = QTableWidgetItem(name)
            name_item.setForeground(Qt.GlobalColor.white)
            self._table.setItem(row, 1, name_item)

            val_item = QTableWidgetItem(f"{val:+.1f}")
            val_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            val_item.setForeground(Qt.GlobalColor.white)
            self._table.setItem(row, 2, val_item)

        self._updating = False
        self._update_count(len(self._collect_angles()), len(visible))

    def _refresh(self):
        visible = self._visible_angles()

        if self._table.rowCount() != len(visible):
            self._rebuild_rows()
            return

        self._updating = True
        for row, (name, val) in enumerate(visible):
            val_item = self._table.item(row, 2)
            new_text = f"{val:+.1f}"
            if val_item and val_item.text() != new_text:
                val_item.setText(new_text)
        self._updating = False

        total = len(self._collect_angles())
        self._update_count(total, len(visible))

    def _update_count(self, total: int, shown: int):
        if total:
            self._count_lbl.setText(
                f"{shown} of {total}" if shown < total else str(total)
            )
        else:
            self._count_lbl.setText("")
