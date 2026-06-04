from __future__ import annotations
import socket
import struct
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QFrame,
)
from state import AppState

_DEFAULT_PORT = 9001


def _set_prop(widget, **props):
    for k, v in props.items():
        widget.setProperty(k, v)


class _FrameThread(QThread):
    """Connects to bridge.exe image server and receives raw RGB frames.

    Protocol:
      Client → Server: 4-byte LE int32 camera ID
      Server → Client (repeated): [4-byte LE int32 width][4-byte LE int32 height]
                                   [width*height*3 bytes RGB]
    """

    frame_ready = Signal(QImage)
    error_occurred = Signal(str)
    status_message = Signal(str)

    def __init__(self, host: str, port: int, camera_id: int, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._camera_id = camera_id
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        sock = None
        try:
            self.status_message.emit(
                f"[camera] connecting to localhost:{self._port}…"
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self._host, self._port))

            self.status_message.emit(
                f"[camera] connected — requesting camera ID {self._camera_id}"
            )
            sock.sendall(struct.pack('<i', self._camera_id))
            sock.settimeout(5.0)  # give the server time to switch streaming modes

            self.status_message.emit(
                f"[camera] waiting for frames (camera {self._camera_id})…"
            )
            first_frame = True
            while self._running:
                header = self._recv_exactly(sock, 8)
                if not header:
                    self.status_message.emit("[camera] server closed connection")
                    break
                width, height = struct.unpack('<ii', header)
                if width <= 0 or height <= 0 or width > 8192 or height > 8192:
                    self.status_message.emit(
                        f"[camera] bad frame dimensions {width}x{height} — "
                        "check CapturyLive image streaming is enabled"
                    )
                    break

                size = width * height * 3
                raw = self._recv_exactly(sock, size)
                if not raw:
                    self.status_message.emit("[camera] incomplete frame data")
                    break

                if first_frame:
                    self.status_message.emit(
                        f"[camera] receiving {width}x{height} frames"
                    )
                    first_frame = False

                img = QImage(raw, width, height, width * 3, QImage.Format.Format_RGB888)
                if not img.isNull():
                    self.frame_ready.emit(img.copy())

        except socket.timeout:
            if self._running:
                self.status_message.emit(
                    "[camera] timed out waiting for frames — "
                    "CapturyLive may not have image streaming enabled for this camera"
                )
                self.error_occurred.emit(
                    "No frames received — check CapturyLive camera/image settings"
                )
        except ConnectionRefusedError:
            self.status_message.emit(
                f"[camera] connection refused on port {self._port} — bridge.exe not running?"
            )
            self.error_occurred.emit(
                f"Cannot connect to image server on port {self._port}"
            )
        except Exception as e:
            if self._running:
                self.status_message.emit(f"[camera] error: {e}")
                self.error_occurred.emit(str(e))
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    @staticmethod
    def _recv_exactly(sock: socket.socket, n: int) -> bytes | None:
        buf = bytearray(n)
        view = memoryview(buf)
        received = 0
        while received < n:
            count = sock.recv_into(view[received:], n - received)
            if count == 0:
                return None
            received += count
        return bytes(buf)


class CameraView(QWidget):
    log_message = Signal(str)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._thread: _FrameThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ---- Controls bar ----
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        ctrl.addWidget(QLabel("Camera"))
        self._cam_combo = QComboBox()
        self._cam_combo.setMinimumWidth(140)
        self._cam_combo.setPlaceholderText("(none found)")
        self._cam_combo.currentIndexChanged.connect(self._on_combo_changed)
        ctrl.addWidget(self._cam_combo)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("color: #2e2e34;")
        ctrl.addWidget(div)

        id_lbl = QLabel("ID")
        id_lbl.setToolTip(
            "Camera ID to request.\n"
            "Auto-filled from the combo above when cameras are found.\n"
            "If none are listed, try 0, 1, 2… manually."
        )
        ctrl.addWidget(id_lbl)
        self._cam_id_spin = QSpinBox()
        self._cam_id_spin.setRange(0, 9999)
        self._cam_id_spin.setValue(0)
        self._cam_id_spin.setFixedWidth(64)
        _set_prop(self._cam_id_spin, mono=True)
        self._cam_id_spin.setToolTip(id_lbl.toolTip())
        ctrl.addWidget(self._cam_id_spin)

        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.VLine)
        div2.setStyleSheet("color: #2e2e34;")
        ctrl.addWidget(div2)

        ctrl.addWidget(QLabel("Port"))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(_DEFAULT_PORT)
        self._port_spin.setFixedWidth(64)
        _set_prop(self._port_spin, mono=True)
        self._port_spin.setToolTip("TCP port that bridge.exe's image server listens on")
        ctrl.addWidget(self._port_spin)

        self._toggle_btn = QPushButton("Stream Camera")
        self._toggle_btn.setFixedHeight(30)
        _set_prop(self._toggle_btn, primary=True)
        self._toggle_btn.clicked.connect(self._toggle_stream)
        ctrl.addWidget(self._toggle_btn)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # ---- Frame display ----
        self._frame_label = QLabel()
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setMinimumHeight(200)
        self._set_placeholder("No camera signal")
        layout.addWidget(self._frame_label, 1)

        state.cameras_updated.connect(self._on_cameras_updated)
        state.connection_status_changed.connect(self._on_connection_status)

    # ------------------------------------------------------------------
    # Camera list
    # ------------------------------------------------------------------

    def _on_cameras_updated(self, cameras: list[tuple[int, str]]):
        current_data = self._cam_combo.currentData()
        self._cam_combo.blockSignals(True)
        self._cam_combo.clear()
        for cam_id, name in cameras:
            label = f"{name} (#{cam_id})" if name else f"Camera #{cam_id}"
            self._cam_combo.addItem(label, userData=cam_id)
        if current_data is not None:
            for i in range(self._cam_combo.count()):
                if self._cam_combo.itemData(i) == current_data:
                    self._cam_combo.setCurrentIndex(i)
                    break
        self._cam_combo.blockSignals(False)
        # Sync spinbox to the selected combo item (if any)
        self._sync_id_spin_from_combo()

    def _on_combo_changed(self, _index: int):
        self._sync_id_spin_from_combo()

    def _sync_id_spin_from_combo(self):
        cam_id = self._cam_combo.currentData()
        if cam_id is not None:
            self._cam_id_spin.setValue(cam_id)

    def _on_connection_status(self, status: str):
        if status == "Disconnected":
            self._stop_stream()

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def _toggle_stream(self):
        if self._thread is not None:
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self):
        cam_id = self._cam_id_spin.value()
        port = self._port_spin.value()

        self._thread = _FrameThread("localhost", port, cam_id, self)
        self._thread.frame_ready.connect(self._on_frame)
        self._thread.error_occurred.connect(self._on_error)
        self._thread.status_message.connect(self._on_status_message)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

        self._toggle_btn.setText("Stop Camera")
        _set_prop(self._toggle_btn, primary=False)
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)
        self._set_placeholder("Connecting…")

    def _stop_stream(self):
        if self._thread:
            self._thread.frame_ready.disconnect()
            self._thread.error_occurred.disconnect()
            self._thread.status_message.disconnect()
            self._thread.stop()
            self._thread.wait(2000)
            if self._thread.isRunning():
                self._thread.terminate()
            self._thread = None

        self._toggle_btn.setText("Stream Camera")
        _set_prop(self._toggle_btn, primary=True)
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)
        self._frame_label.clear()
        self._set_placeholder("No camera signal")

    # ------------------------------------------------------------------
    # Frame / error handling
    # ------------------------------------------------------------------

    def _on_frame(self, img: QImage):
        lbl = self._frame_label
        px = QPixmap.fromImage(img).scaled(
            lbl.width(), lbl.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        lbl.setPixmap(px)
        if lbl.styleSheet():
            lbl.setStyleSheet("background: #0e0e10;")

    def _on_status_message(self, msg: str):
        self.log_message.emit(msg)

    def _on_error(self, msg: str):
        self._set_placeholder(msg, error=True)
        self._stop_stream()

    def _on_thread_finished(self):
        if self._thread and not self._frame_label.pixmap():
            self._set_placeholder("Stream ended")

    def _set_placeholder(self, text: str, *, error: bool = False):
        color = "#ef4444" if error else "#5d5d65"
        self._frame_label.setText(text)
        self._frame_label.setStyleSheet(
            f"background: #0e0e10; color: {color}; font-size: 12px;"
        )
