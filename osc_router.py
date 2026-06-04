from __future__ import annotations
from PySide6.QtCore import QObject
from state import AppState, Pose

try:
    from pythonosc.udp_client import SimpleUDPClient
    from pythonosc.osc_bundle_builder import OscBundleBuilder, IMMEDIATELY
    from pythonosc.osc_message_builder import OscMessageBuilder
    _HAS_OSC = True
except ImportError:
    _HAS_OSC = False


class OscRouter(QObject):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._clients: dict[tuple[str, int], object] = {}
        self._active = True

        state.pose_updated.connect(self._on_pose)
        state.angles_updated.connect(self._on_angle)
        state.destinations_changed.connect(self._on_destinations_changed)

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool):
        self._active = value

    def has_osc(self) -> bool:
        return _HAS_OSC

    def _on_destinations_changed(self, destinations):
        if not _HAS_OSC:
            return
        needed = {(d.ip, d.port) for d in destinations if d.enabled}
        for key in list(self._clients):
            if key not in needed:
                del self._clients[key]

    def _get_client(self, ip: str, port: int) -> object | None:
        if not _HAS_OSC:
            return None
        key = (ip, port)
        if key not in self._clients:
            self._clients[key] = SimpleUDPClient(ip, port)
        return self._clients[key]

    def _on_pose(self, pose: Pose):
        if not self._active or not _HAS_OSC:
            return
        actor = self._state.actors.get(pose.actor_id)
        if not actor:
            return
        selected = self._state.selected_joints
        if not selected:
            return
        active_dests = [d for d in self._state.destinations if d.enabled]
        if not active_dests:
            return

        n = min(len(actor.joint_names), len(pose.transforms))

        for dest in active_dests:
            client = self._get_client(dest.ip, dest.port)
            if not client:
                continue

            bundle = OscBundleBuilder(IMMEDIATELY)
            msg_count = 0

            for i in range(n):
                name = actor.joint_names[i]
                if name not in selected:
                    continue
                x, y, z, rx, ry, rz = pose.transforms[i]
                try:
                    addr = dest.address_template.format(
                        actor=pose.actor_id,
                        joint=name,
                        timestamp=pose.timestamp_us,
                    )
                except (KeyError, ValueError):
                    addr = f"/captury/{pose.actor_id}/{name}"

                msg = OscMessageBuilder(address=addr)
                msg.add_arg(x / 1000.0)   # mm → m
                msg.add_arg(y / 1000.0)
                msg.add_arg(z / 1000.0)
                msg.add_arg(rx)
                msg.add_arg(ry)
                msg.add_arg(rz)
                bundle.add_content(msg.build())
                msg_count += 1

            if msg_count > 0:
                try:
                    client.send(bundle.build())
                except Exception:
                    pass

    def _on_angle(self, actor_id: int, angle_name: str, value: float):
        if not self._active or not _HAS_OSC:
            return
        if angle_name not in self._state.selected_angles:
            return
        active_dests = [d for d in self._state.destinations if d.enabled]
        if not active_dests:
            return
        for dest in active_dests:
            client = self._get_client(dest.ip, dest.port)
            if not client:
                continue
            try:
                msg = OscMessageBuilder(address=f"/captury/{actor_id}/angles/{angle_name}")
                msg.add_arg(float(value))
                client.send(msg.build())
            except Exception:
                pass