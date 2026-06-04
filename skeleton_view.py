from __future__ import annotations
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import QWidget
from state import Actor, Pose, AppState

_HIT_RADIUS   = 14
_R_DEFAULT    = 5
_R_SELECTED   = 6
_R_HOVER      = 7

_C_BG         = QColor(0x0e, 0x0e, 0x10)
_C_HORIZON    = QColor(0x2e, 0x2e, 0x34)
_C_OUTLINE    = QColor(0x0e, 0x0e, 0x10)          # joint outline = bg color
_C_JOINT      = QColor(0x5d, 0x5d, 0x65)          # TEXT_TERTIARY
_C_SELECTED   = QColor(0x4a, 0xde, 0x80)          # ACCENT
_C_HOVER      = QColor(0xe8, 0xe8, 0xea)          # TEXT_PRIMARY
_C_BONE       = QColor(0x5d, 0x5d, 0x65, 100)     # TEXT_TERTIARY @~40% opacity
_C_OVERLAY    = QColor(0x5d, 0x5d, 0x65)          # TEXT_TERTIARY
_C_NODATA     = QColor(0x5d, 0x5d, 0x65)

_MONO_FONT    = QFont("Consolas", 9)


class SkeletonView(QWidget):
    joint_clicked = Signal(str)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._actor: Actor | None = None
        self._pose: Pose | None = None
        self._screen_pts: list[QPoint] = []
        self._hover_idx: int | None = None

        self.setMinimumSize(280, 380)
        self.setMouseTracking(True)

        state.actor_added.connect(self._on_actor)
        state.pose_updated.connect(self._on_pose)
        state.selected_joints_changed.connect(lambda _: self.update())
        state.connection_status_changed.connect(self._on_status)

    def _on_actor(self, actor: Actor):
        self._actor = actor
        self.update()

    def _on_pose(self, pose: Pose):
        if self._actor and pose.actor_id == self._actor.id:
            self._pose = pose
            self.update()

    def _on_status(self, status: str):
        if status == "Disconnected":
            self._pose = None
            self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), _C_BG)

        w, h = self.width(), self.height()

        if not self._actor or not self._pose:
            p.setPen(_C_NODATA)
            p.setFont(_MONO_FONT)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No skeleton data")
            return

        actor = self._actor
        pose  = self._pose
        n = min(len(actor.joint_names), len(pose.transforms))
        if n == 0:
            return

        pos2d = [(pose.transforms[i][0], pose.transforms[i][1]) for i in range(n)]
        xs = [p2[0] for p2 in pos2d]
        ys = [p2[1] for p2 in pos2d]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        range_x = max(max_x - min_x, 1.0)
        range_y = max(max_y - min_y, 1.0)

        scale = min(w * 0.80 / range_x, h * 0.80 / range_y)
        cx = w / 2 - (min_x + max_x) / 2 * scale
        cy = h / 2 + (min_y + max_y) / 2 * scale

        def to_screen(wx: float, wy: float) -> QPoint:
            return QPoint(int(wx * scale + cx), int(-wy * scale + cy))

        pts = [to_screen(pos2d[i][0], pos2d[i][1]) for i in range(n)]
        self._screen_pts = pts

        # Horizon line (world Y=0)
        ground_y = int(cy)
        if 0 < ground_y < h:
            p.setPen(QPen(_C_HORIZON, 1))
            p.drawLine(0, ground_y, w, ground_y)

        # Bones
        bone_pen = QPen(_C_BONE, 1.5)
        bone_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bone_pen)
        for i in range(n):
            pi = actor.joint_parents[i] if i < len(actor.joint_parents) else -1
            if 0 <= pi < n:
                p.drawLine(pts[i], pts[pi])

        # Joints (outline then fill, back to front doesn't matter at this scale)
        for i in range(n):
            name = actor.joint_names[i]
            is_hover    = (i == self._hover_idx)
            is_selected = name in self._state.selected_joints

            if is_hover:
                color, r = _C_HOVER, _R_HOVER
            elif is_selected:
                color, r = _C_SELECTED, _R_SELECTED
            else:
                color, r = _C_JOINT, _R_DEFAULT

            p.setPen(QPen(_C_OUTLINE, 1.5))
            p.setBrush(QBrush(color))
            p.drawEllipse(pts[i], r, r)

        # Overlay
        p.setFont(_MONO_FONT)
        p.setPen(_C_OVERLAY)
        p.drawText(10, 16, f"Quality: {pose.quality}")
        p.drawText(10, 30, f"Actor: {actor.id}")

        # Axis hint (bottom-right)
        p.drawText(w - 42, h - 8, "X→  Y↑")

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event):
        new_hover = self._joint_at(event.position().toPoint())
        if new_hover != self._hover_idx:
            self._hover_idx = new_hover
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._joint_at(event.position().toPoint())
            if idx is not None and self._actor:
                self.joint_clicked.emit(self._actor.joint_names[idx])

    def leaveEvent(self, event):
        self._hover_idx = None
        self.update()

    def _joint_at(self, pos: QPoint) -> int | None:
        best_dist = float(_HIT_RADIUS)
        best_idx  = None
        for i, pt in enumerate(self._screen_pts):
            dx = pos.x() - pt.x()
            dy = pos.y() - pt.y()
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_idx  = i
        return best_idx
