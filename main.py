from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path


def _resource_path(relative: str) -> Path:
    """Read-only bundled resources — maps to sys._MEIPASS in a PyInstaller build."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).parent / relative


def _app_dir() -> Path:
    """Writable directory next to the executable (or next to main.py in dev mode)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import (
    QFont, QKeySequence, QShortcut, QAction,
    QColor, QTextCursor, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QSplitter, QSpinBox,
    QDoubleSpinBox, QFileDialog, QMenuBar, QTabWidget, QFrame,
)

from state import AppState, OscDestination
from bridge_manager import BridgeManager
from skeleton_view import SkeletonView
from joint_selector import JointSelector
from osc_router import OscRouter
from destinations_panel import DestinationsPanel
from actor_panel import ActorPanel
from recording_panel import RecordingPanel
from angles_panel import AnglesPanel
from camera_view import CameraView

_DEFAULT_BRIDGE_EXE = _resource_path("bridge.exe" if sys.platform == "win32" else "bridge")
_DEFAULT_HOST = "192.168.10.106"
_DEFAULT_PORT = 2101
_CONFIG_FILE = _app_dir() / "config.json"


def _set_prop(widget, **props):
    for k, v in props.items():
        widget.setProperty(k, v)


class MainWindow(QMainWindow):
    def __init__(self, fake: bool = False):
        super().__init__()
        self._fake = fake
        self._state = AppState()
        self._osc_router = OscRouter(self._state)
        self._bridge: BridgeManager | None = None
        self._bridge_exe = _DEFAULT_BRIDGE_EXE

        self.setWindowTitle("Captury Student Streamer" + (" [FAKE]" if fake else ""))
        self.resize(1500, 900)
        self.setMinimumSize(1200, 700)

        self._build_ui()
        self._build_menu()
        self._setup_shortcuts()
        self._load_config()

        self._state.connection_status_changed.connect(self._on_status_changed)

        if not self._osc_router.has_osc():
            self._log("[router] WARNING: python-osc not installed — OSC disabled.")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(8)

        root.addLayout(self._build_connection_bar())
        root.addLayout(self._build_controls_bar())
        root.addWidget(self._build_main_area(), 1)
        root.addWidget(self._build_log())

    def _build_connection_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("Host"))
        self._host_edit = QLineEdit(_DEFAULT_HOST)
        self._host_edit.setFixedWidth(150)
        _set_prop(self._host_edit, mono=True)
        row.addWidget(self._host_edit)

        row.addWidget(QLabel("Port"))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(_DEFAULT_PORT)
        self._port_spin.setFixedWidth(72)
        _set_prop(self._port_spin, mono=True)
        row.addWidget(self._port_spin)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(100)
        self._connect_btn.setFixedHeight(32)
        _set_prop(self._connect_btn, primary=True)
        self._connect_btn.clicked.connect(self._toggle_connection)
        row.addWidget(self._connect_btn)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #9a9aa3; font-size: 9px;")
        row.addWidget(self._status_dot)

        self._status_label = QLabel("Disconnected")
        self._status_label.setStyleSheet("color: #9a9aa3;")
        row.addWidget(self._status_label)
        row.addStretch()

        self._osc_pause_label = QLabel("")
        self._osc_pause_label.setStyleSheet("color: #fbbf24; font-weight: 600;")
        row.addWidget(self._osc_pause_label)

        bridge_btn = QPushButton("bridge.exe…" if sys.platform == "win32" else "bridge…")
        bridge_btn.setToolTip("Choose path to bridge.exe")
        _set_prop(bridge_btn, ghost=True)
        bridge_btn.clicked.connect(self._choose_bridge_exe)
        row.addWidget(bridge_btn)

        self._bridge_path_label = QLabel(str(self._bridge_exe.name))
        self._bridge_path_label.setStyleSheet("color: #5d5d65; font-size: 11px;")
        self._bridge_path_label.setToolTip(str(self._bridge_exe))
        row.addWidget(self._bridge_path_label)

        return row

    def _build_controls_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        # Snap controls
        snap_lbl = QLabel("Snap Actor")
        snap_lbl.setStyleSheet("color: #9a9aa3;")
        row.addWidget(snap_lbl)

        row.addWidget(QLabel("X"))
        self._snap_x = QDoubleSpinBox()
        self._snap_x.setRange(-100000, 100000)
        self._snap_x.setValue(0.0)
        self._snap_x.setSuffix(" mm")
        self._snap_x.setFixedWidth(110)
        _set_prop(self._snap_x, mono=True)
        row.addWidget(self._snap_x)

        row.addWidget(QLabel("Z"))
        self._snap_z = QDoubleSpinBox()
        self._snap_z.setRange(-100000, 100000)
        self._snap_z.setValue(0.0)
        self._snap_z.setSuffix(" mm")
        self._snap_z.setFixedWidth(110)
        _set_prop(self._snap_z, mono=True)
        row.addWidget(self._snap_z)

        row.addWidget(QLabel("Heading"))
        self._snap_heading = QDoubleSpinBox()
        self._snap_heading.setRange(0, 9999)
        self._snap_heading.setValue(500.0)
        self._snap_heading.setSuffix("°")
        self._snap_heading.setFixedWidth(90)
        self._snap_heading.setToolTip(">360 = unknown orientation")
        _set_prop(self._snap_heading, mono=True)
        row.addWidget(self._snap_heading)

        snap_btn = QPushButton("Snap")
        snap_btn.setFixedWidth(60)
        snap_btn.setToolTip("SNAP x z heading")
        snap_btn.clicked.connect(self._snap_actor)
        row.addWidget(snap_btn)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("color: #2e2e34;")
        row.addWidget(div)

        # Recording controls
        self._recording_panel = RecordingPanel(self._state)
        row.addWidget(self._recording_panel)

        row.addStretch()
        return row

    def _build_main_area(self) -> QSplitter:
        main_split = QSplitter(Qt.Orientation.Horizontal)

        # ---- Left: skeleton view + actor panel ----
        left_split = QSplitter(Qt.Orientation.Vertical)

        self._skeleton_view = SkeletonView(self._state)
        self._skeleton_view.joint_clicked.connect(self._state.toggle_joint)
        left_split.addWidget(self._skeleton_view)

        self._actor_panel = ActorPanel(self._state)
        self._actor_panel.setMinimumHeight(60)
        left_split.addWidget(self._actor_panel)

        left_split.setSizes([520, 160])
        main_split.addWidget(left_split)

        # ---- Right: tabs ----
        tabs = QTabWidget()
        tabs.setDocumentMode(False)

        # Tab 0: Joints + Destinations
        joints_widget = QWidget()
        joints_layout = QVBoxLayout(joints_widget)
        joints_layout.setContentsMargins(0, 0, 0, 0)
        joints_layout.setSpacing(0)
        joint_dest_split = QSplitter(Qt.Orientation.Vertical)
        self._joint_selector = JointSelector(self._state)
        joint_dest_split.addWidget(self._joint_selector)
        self._dest_panel = DestinationsPanel(self._state)
        joint_dest_split.addWidget(self._dest_panel)
        joint_dest_split.setSizes([400, 240])
        joints_layout.addWidget(joint_dest_split)
        tabs.addTab(joints_widget, "Joints")

        # Tab 1: Angles
        self._angles_panel = AnglesPanel(self._state)
        tabs.addTab(self._angles_panel, "Angles")

        # Camera view kept but not shown in tabs (re-add when image streaming is resolved)
        self._camera_view = CameraView(self._state)
        self._camera_view.log_message.connect(self._log)

        main_split.addWidget(tabs)
        main_split.setSizes([720, 500])
        return main_split

    def _build_log(self) -> QTextEdit:
        self._log_widget = QTextEdit()
        self._log_widget.setReadOnly(True)
        self._log_widget.setMaximumHeight(120)
        self._log_widget.document().setMaximumBlockCount(400)
        return self._log_widget

    def _build_menu(self):
        menu = self.menuBar()
        view_menu = menu.addMenu("View")

        toggle_log = QAction("Toggle Log", self)
        toggle_log.setShortcut("Ctrl+L")
        toggle_log.triggered.connect(
            lambda: self._log_widget.setVisible(not self._log_widget.isVisible())
        )
        view_menu.addAction(toggle_log)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space), self).activated.connect(
            self._toggle_osc
        )
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(
            self._disconnect
        )

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _toggle_connection(self):
        if self._bridge is not None:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        host = self._host_edit.text().strip()
        port = self._port_spin.value()
        self._bridge = BridgeManager(
            state=self._state,
            bridge_exe=self._bridge_exe,
            fake=self._fake,
        )
        self._bridge.log_message.connect(self._log)
        self._bridge.start(host, port)
        self._recording_panel.set_bridge(self._bridge)
        self._connect_btn.setText("Disconnect")
        _set_prop(self._connect_btn, primary=False)
        self._connect_btn.style().unpolish(self._connect_btn)
        self._connect_btn.style().polish(self._connect_btn)

    def _disconnect(self):
        self._recording_panel.set_bridge(None)
        if self._bridge:
            self._bridge.stop()
            self._bridge = None
        self._connect_btn.setText("Connect")
        _set_prop(self._connect_btn, primary=True)
        self._connect_btn.style().unpolish(self._connect_btn)
        self._connect_btn.style().polish(self._connect_btn)

    # ------------------------------------------------------------------
    # OSC / Snap control
    # ------------------------------------------------------------------

    def _toggle_osc(self):
        self._osc_router.active = not self._osc_router.active
        if self._osc_router.active:
            self._osc_pause_label.setText("")
            self._log("[router] OSC output resumed")
        else:
            self._osc_pause_label.setText("OSC PAUSED")
            self._log("[router] OSC output paused")

    def _snap_actor(self):
        if not self._bridge:
            self._log("[snap] not connected")
            return
        x = self._snap_x.value()
        z = self._snap_z.value()
        h = self._snap_heading.value()
        cmd = f"SNAP {x:.1f} {z:.1f} {h:.1f}"
        sent = self._bridge.send_command(cmd)
        self._log(f"[snap] {cmd} {'-> sent' if sent else '-> fake mode, ignored'}")

    # ------------------------------------------------------------------
    # Status / logging
    # ------------------------------------------------------------------

    def _on_status_changed(self, status: str):
        self._status_label.setText(status)
        low = status.lower()
        if "streaming" in low or "connected" in low:
            color = "#4ade80"
        elif "connecting" in low:
            color = "#fbbf24"
        elif "error" in low or "failed" in low or "not found" in low:
            color = "#ef4444"
        else:
            color = "#9a9aa3"
        self._status_label.setStyleSheet(f"color: {color};")
        self._status_dot.setStyleSheet(f"color: {color}; font-size: 9px;")

    @staticmethod
    def _log_line_color(line: str) -> str:
        low = line.lower()
        if "error" in low or "failed" in low or "not found" in low:
            return "#ef4444"
        if "streaming" in low or "appeared" in low or "ready" in low or (
                "snap" in low and "sent" in low):
            return "#4ade80"
        if "warning" in low or "warn" in low or "paused" in low:
            return "#fbbf24"
        return "#9a9aa3"

    def _log(self, line: str):
        sb = self._log_widget.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        old_val = sb.value()

        color = self._log_line_color(line)
        safe = (line.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))
        self._log_widget.append(f'<span style="color:{color};">{safe}</span>')

        if not at_bottom:
            sb.setValue(old_val)

    # ------------------------------------------------------------------
    # Bridge exe picker
    # ------------------------------------------------------------------

    def _choose_bridge_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select bridge.exe",
            str(self._bridge_exe.parent),
            "Executables (*.exe);;All files (*)",
        )
        if path:
            self._bridge_exe = Path(path)
            self._bridge_path_label.setText(self._bridge_exe.name)
            self._bridge_path_label.setToolTip(str(self._bridge_exe))
            self._save_config()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _load_config(self):
        if not _CONFIG_FILE.exists():
            return
        try:
            cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            self._host_edit.setText(cfg.get("host", _DEFAULT_HOST))
            self._port_spin.setValue(cfg.get("port", _DEFAULT_PORT))
            exe = cfg.get("bridge_exe")
            if exe:
                p = Path(exe)
                self._bridge_exe = p if p.exists() else _DEFAULT_BRIDGE_EXE
                self._bridge_path_label.setText(self._bridge_exe.name)
                self._bridge_path_label.setToolTip(str(self._bridge_exe))
            dests = [
                OscDestination(
                    ip=d.get("ip", "127.0.0.1"),
                    port=d.get("port", 7000),
                    address_template=d.get("template", "/captury/{actor}/{joint}"),
                    enabled=d.get("enabled", True),
                )
                for d in cfg.get("destinations", [])
            ]
            if dests:
                self._dest_panel.load_destinations(dests)
            geo = cfg.get("geometry")
            if geo:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
        except Exception as e:
            self._log(f"[config] load error: {e}")

    def _save_config(self):
        cfg = {
            "host": self._host_edit.text().strip(),
            "port": self._port_spin.value(),
            "bridge_exe": str(self._bridge_exe),
            "destinations": [
                {
                    "ip": d.ip,
                    "port": d.port,
                    "template": d.address_template,
                    "enabled": d.enabled,
                }
                for d in self._state.destinations
            ],
            "geometry": self.saveGeometry().toBase64().data().decode(),
        }
        try:
            _CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception as e:
            self._log(f"[config] save error: {e}")

    def closeEvent(self, event):
        self._save_config()
        self._disconnect()
        super().closeEvent(event)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Captury Student Streamer")
    parser.add_argument(
        "--fake", action="store_true",
        help="Generate synthetic skeleton data (no Captury hardware needed)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    style_path = _resource_path("style.qss")
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    window = MainWindow(fake=args.fake)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
