from __future__ import annotations
from dataclasses import dataclass, field
from PySide6.QtCore import QObject, Signal


@dataclass
class Actor:
    id: int
    joint_names: list[str]
    joint_parents: list[int]
    name: str = ""


@dataclass
class Pose:
    actor_id: int
    timestamp_us: int
    quality: int
    transforms: list[tuple[float, float, float, float, float, float]]
    foot_left: bool = False
    foot_right: bool = False


@dataclass
class OscDestination:
    ip: str
    port: int
    address_template: str = "/captury/{actor}/{joint}"
    enabled: bool = True


class AppState(QObject):
    actor_added = Signal(object)            # Actor
    pose_updated = Signal(object)           # Pose
    connection_status_changed = Signal(str)
    selected_joints_changed = Signal(set)
    selected_angles_changed = Signal(set)
    destinations_changed = Signal(list)
    status_updated = Signal(int, str)       # actorId, status string
    cameras_updated = Signal(list)          # list[tuple[int, str]]
    recording_changed = Signal(bool)
    angles_updated = Signal(int, str, float)  # actorId, angleName, degrees

    def __init__(self, parent=None):
        super().__init__(parent)
        self.actors: dict[int, Actor] = {}
        self.latest_poses: dict[int, Pose] = {}
        self.selected_joints: set[str] = set()
        self.selected_angles: set[str] = set()
        self.destinations: list[OscDestination] = []
        self._connection_status: str = "Disconnected"
        self.actor_status: dict[int, str] = {}
        self.actor_angles: dict[int, dict[str, float]] = {}
        self.cameras: list[tuple[int, str]] = []
        self.is_recording: bool = False

    @property
    def connection_status(self) -> str:
        return self._connection_status

    @connection_status.setter
    def connection_status(self, value: str):
        if self._connection_status != value:
            self._connection_status = value
            self.connection_status_changed.emit(value)

    def add_actor(self, actor: Actor):
        self.actors[actor.id] = actor
        self.actor_added.emit(actor)
        self.connection_status = f"Streaming — {len(self.actors)} actor(s)"

    def update_pose(self, pose: Pose):
        self.latest_poses[pose.actor_id] = pose
        self.pose_updated.emit(pose)

    def update_status(self, actor_id: int, status: str):
        self.actor_status[actor_id] = status
        self.status_updated.emit(actor_id, status)
        if status == "DELETED":
            self.actor_angles.pop(actor_id, None)
            self.latest_poses.pop(actor_id, None)

    def update_angle(self, actor_id: int, angle_name: str, value: float):
        if actor_id not in self.actor_angles:
            self.actor_angles[actor_id] = {}
        self.actor_angles[actor_id][angle_name] = value
        self.angles_updated.emit(actor_id, angle_name, value)

    def set_cameras(self, cameras: list[tuple[int, str]]):
        self.cameras = cameras
        self.cameras_updated.emit(cameras)

    def set_recording(self, recording: bool):
        if self.is_recording != recording:
            self.is_recording = recording
            self.recording_changed.emit(recording)

    def reset(self):
        self.actors.clear()
        self.latest_poses.clear()
        self.actor_status.clear()
        self.actor_angles.clear()
        if self.cameras:
            self.cameras.clear()
            self.cameras_updated.emit([])
        if self.is_recording:
            self.is_recording = False
            self.recording_changed.emit(False)

    def toggle_joint(self, joint_name: str):
        if joint_name in self.selected_joints:
            self.selected_joints.discard(joint_name)
        else:
            self.selected_joints.add(joint_name)
        self.selected_joints_changed.emit(set(self.selected_joints))

    def set_joint_selected(self, joint_name: str, selected: bool):
        changed = False
        if selected and joint_name not in self.selected_joints:
            self.selected_joints.add(joint_name)
            changed = True
        elif not selected and joint_name in self.selected_joints:
            self.selected_joints.discard(joint_name)
            changed = True
        if changed:
            self.selected_joints_changed.emit(set(self.selected_joints))

    def toggle_angle(self, angle_name: str):
        if angle_name in self.selected_angles:
            self.selected_angles.discard(angle_name)
        else:
            self.selected_angles.add(angle_name)
        self.selected_angles_changed.emit(set(self.selected_angles))

    def set_angle_selected(self, angle_name: str, selected: bool):
        changed = False
        if selected and angle_name not in self.selected_angles:
            self.selected_angles.add(angle_name)
            changed = True
        elif not selected and angle_name in self.selected_angles:
            self.selected_angles.discard(angle_name)
            changed = True
        if changed:
            self.selected_angles_changed.emit(set(self.selected_angles))

    def set_destinations(self, destinations: list[OscDestination]):
        self.destinations = list(destinations)
        self.destinations_changed.emit(self.destinations)
