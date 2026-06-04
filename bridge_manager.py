from __future__ import annotations
import subprocess
import threading
import math
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer
from state import Actor, Pose, AppState


# Fake skeleton: (name, parent_index, base_position_mm)
_FAKE_JOINTS = [
    ("Root",           -1, (  0.0,  950.0,   0.0)),
    ("Hips",            0, (  0.0, 1000.0,   0.0)),
    ("Spine",           1, (  0.0, 1100.0,   0.0)),
    ("Spine1",          2, (  0.0, 1200.0,   0.0)),
    ("Spine2",          3, (  0.0, 1300.0,   0.0)),
    ("Neck",            4, (  0.0, 1380.0,   0.0)),
    ("Head",            5, (  0.0, 1480.0,   0.0)),
    ("LeftShoulder",    4, (-120.0, 1320.0,   0.0)),
    ("LeftArm",         7, (-280.0, 1270.0,   0.0)),
    ("LeftForearm",     8, (-480.0, 1150.0,   0.0)),
    ("LeftHand",        9, (-620.0, 1020.0,   0.0)),
    ("RightShoulder",   4, ( 120.0, 1320.0,   0.0)),
    ("RightArm",       11, ( 280.0, 1270.0,   0.0)),
    ("RightForearm",   12, ( 480.0, 1150.0,   0.0)),
    ("RightHand",      13, ( 620.0, 1020.0,   0.0)),
    ("LeftUpLeg",       1, (-100.0,  900.0,   0.0)),
    ("LeftLeg",        15, (-110.0,  530.0,   0.0)),
    ("LeftFoot",       16, (-110.0,   80.0,   0.0)),
    ("LeftToe",        17, ( -80.0,    0.0,  60.0)),
    ("RightUpLeg",      1, ( 100.0,  900.0,   0.0)),
    ("RightLeg",       19, ( 110.0,  530.0,   0.0)),
    ("RightFoot",      20, ( 110.0,   80.0,   0.0)),
    ("RightToe",       21, (  80.0,    0.0,  60.0)),
]
_FAKE_ACTOR_ID = 99001

_FAKE_ANGLES = [
    "LeftKneeFlexion", "RightKneeFlexion",
    "LeftHipFlexion", "RightHipFlexion",
    "LeftHipAbduction", "RightHipAbduction",
    "LeftAnkleDorsiflexion", "RightAnkleDorsiflexion",
    "LeftElbowFlexion", "RightElbowFlexion",
    "LeftShoulderFlexion", "RightShoulderFlexion",
    "TorsoInclination", "TorsoRotation",
    "NeckFlexion",
]


class BridgeManager(QObject):
    log_message = Signal(str)

    def __init__(self, state: AppState, bridge_exe: Path | None = None, fake: bool = False):
        super().__init__()
        self._state = state
        self._bridge_exe = bridge_exe
        self._fake = fake
        self._process: subprocess.Popen | None = None
        self._stop_event = threading.Event()
        self._fake_timer: QTimer | None = None
        self._fake_t0 = 0.0
        self._fake_tick = 0
        self._cameras: list[tuple[int, str]] = []

    def start(self, host: str, port: int = 2101):
        self._cameras.clear()
        if self._fake:
            self._start_fake()
        else:
            self._start_real(host, port)

    def send_command(self, line: str) -> bool:
        if self._fake or not self._process or not self._process.stdin:
            return False
        try:
            self._process.stdin.write(line + "\n")
            self._process.stdin.flush()
            return True
        except Exception as e:
            self.log_message.emit(f"[bridge] stdin write error: {e}")
            return False

    def stop(self):
        self._stop_event.set()
        if self._fake_timer:
            self._fake_timer.stop()
            self._fake_timer = None
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        self._cameras.clear()
        self._state.reset()
        self._state.connection_status = "Disconnected"
        self.log_message.emit("[bridge] disconnected")

    # ------------------------------------------------------------------
    # Real bridge
    # ------------------------------------------------------------------

    def _start_real(self, host: str, port: int):
        if not self._bridge_exe or not Path(self._bridge_exe).exists():
            self._state.connection_status = "Error: bridge.exe not found"
            self.log_message.emit(f"[bridge] bridge.exe not found: {self._bridge_exe}")
            return

        self._stop_event.clear()
        self._state.connection_status = "Connecting..."

        # Launch bridge.exe in a thread so the UI stays responsive during startup
        threading.Thread(
            target=self._launch_bridge, args=(host, port), daemon=True
        ).start()

    def _launch_bridge(self, host: str, port: int):
        try:
            self._process = subprocess.Popen(
                [str(self._bridge_exe), host, str(port)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            self._state.connection_status = f"Error: {e}"
            self.log_message.emit(f"[bridge] failed to start: {e}")
            return

        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self):
        proc = self._process
        if not proc or not proc.stdout:
            return
        try:
            for line in proc.stdout:
                if self._stop_event.is_set():
                    break
                line = line.rstrip("\n\r")
                if line:
                    self._parse_line(line)
        except Exception as e:
            self.log_message.emit(f"[bridge] stdout error: {e}")
        finally:
            if not self._stop_event.is_set():
                self._state.connection_status = "Disconnected"

    def _read_stderr(self):
        proc = self._process
        if not proc or not proc.stderr:
            return
        try:
            for line in proc.stderr:
                if self._stop_event.is_set():
                    break
                line = line.rstrip("\n\r")
                if line:
                    self.log_message.emit(line)
        except Exception:
            pass

    def _parse_line(self, line: str):
        parts = line.split()
        if not parts:
            return
        msg_type = parts[0]
        if msg_type == "READY":
            self._state.connection_status = "Connected — waiting for actors"
            self.log_message.emit("[bridge] ready")
        elif msg_type == "ACTOR":
            self._parse_actor(parts)
        elif msg_type == "ACTOR_NAME":
            self._parse_actor_name(parts)
        elif msg_type == "POSE":
            self._parse_pose(parts)
        elif msg_type == "STATUS":
            self._parse_status(parts)
        elif msg_type == "ANGLE":
            self._parse_angle(parts)
        elif msg_type == "CAMERA":
            self._parse_camera(parts)
        elif msg_type == "RECORDING_STARTED":
            self._state.set_recording(True)
            self.log_message.emit("[bridge] recording started")
        elif msg_type == "RECORDING_STOPPED":
            self._state.set_recording(False)
            self.log_message.emit("[bridge] recording stopped")
        elif msg_type == "ACTOR_CHANGED":
            if len(parts) >= 3:
                self.log_message.emit(
                    f"[bridge] actor {parts[1]} changed, mode={parts[2]}"
                )

    def _parse_actor(self, parts: list[str]):
        # ACTOR <id> <numJoints> <name1>:<parent1> <name2>:<parent2> ...
        # Fallback (old bridge): ACTOR <id> <numJoints> <name1> <name2> ...
        if len(parts) < 3:
            return
        try:
            actor_id = int(parts[1])
            num_joints = int(parts[2])
        except ValueError:
            return

        joint_names: list[str] = []
        joint_parents: list[int] = []
        for token in parts[3 : 3 + num_joints]:
            if ":" in token:
                name, parent_str = token.rsplit(":", 1)
                try:
                    parent = int(parent_str)
                except ValueError:
                    parent = -1
            else:
                name = token
                parent = -1
            joint_names.append(name)
            joint_parents.append(parent)

        existing = self._state.actors.get(actor_id)
        existing_name = existing.name if existing else ""
        actor = Actor(id=actor_id, joint_names=joint_names, joint_parents=joint_parents,
                      name=existing_name)
        self._state.add_actor(actor)
        self.log_message.emit(
            f"[bridge] actor {actor_id} appeared with {len(joint_names)} joints"
        )

    def _parse_actor_name(self, parts: list[str]):
        # ACTOR_NAME <id> <name...>
        if len(parts) < 3:
            return
        try:
            actor_id = int(parts[1])
        except ValueError:
            return
        name = " ".join(parts[2:])
        actor = self._state.actors.get(actor_id)
        if actor:
            actor.name = name

    def _parse_pose(self, parts: list[str]):
        # POSE <id> <timestamp> <numJoints> <quality> <name> <x> <y> <z> <rx> <ry> <rz> ...
        # Optional trailing: <foot_l:0|1> <foot_r:0|1>
        if len(parts) < 5:
            return
        try:
            actor_id = int(parts[1])
            timestamp_us = int(parts[2])
            num_joints = int(parts[3])
            quality = int(parts[4])
        except ValueError:
            return

        transforms: list[tuple[float, float, float, float, float, float]] = []
        idx = 5
        for _ in range(num_joints):
            if idx >= len(parts):
                break
            idx += 1  # skip joint name
            if idx + 6 > len(parts):
                break
            try:
                x  = float(parts[idx])
                y  = float(parts[idx + 1])
                z  = float(parts[idx + 2])
                rx = float(parts[idx + 3])
                ry = float(parts[idx + 4])
                rz = float(parts[idx + 5])
                transforms.append((x, y, z, rx, ry, rz))
                idx += 6
            except ValueError:
                break

        foot_left = False
        foot_right = False
        if idx + 1 < len(parts):
            try:
                foot_left = bool(int(parts[idx]))
                foot_right = bool(int(parts[idx + 1]))
            except (ValueError, IndexError):
                pass

        self._state.update_pose(
            Pose(
                actor_id=actor_id,
                timestamp_us=timestamp_us,
                quality=quality,
                transforms=transforms,
                foot_left=foot_left,
                foot_right=foot_right,
            )
        )

    def _parse_status(self, parts: list[str]):
        # STATUS <actorId> <SCALING|TRACKING|STOPPED|DELETED>
        if len(parts) < 3:
            return
        try:
            actor_id = int(parts[1])
        except ValueError:
            return
        self._state.update_status(actor_id, parts[2])

    def _parse_angle(self, parts: list[str]):
        # ANGLE <actorId> <angleName> <valueDegrees>
        if len(parts) < 4:
            return
        try:
            actor_id = int(parts[1])
            value = float(parts[3])
        except ValueError:
            return
        self._state.update_angle(actor_id, parts[2], value)

    def _parse_camera(self, parts: list[str]):
        # CAMERA <id> <name...>
        if len(parts) < 3:
            return
        try:
            cam_id = int(parts[1])
        except ValueError:
            return
        name = " ".join(parts[2:])
        if not any(c[0] == cam_id for c in self._cameras):
            self._cameras.append((cam_id, name))
            self._state.set_cameras(list(self._cameras))
            self.log_message.emit(f"[bridge] camera {cam_id}: {name}")

    # ------------------------------------------------------------------
    # Fake mode
    # ------------------------------------------------------------------

    def _start_fake(self):
        self._stop_event.clear()
        self._fake_t0 = time.monotonic()
        self._fake_tick = 0

        names = [j[0] for j in _FAKE_JOINTS]
        parents = [j[1] for j in _FAKE_JOINTS]
        actor = Actor(id=_FAKE_ACTOR_ID, joint_names=names, joint_parents=parents,
                      name="Fake Actor")
        self._state.add_actor(actor)
        self._state.update_status(_FAKE_ACTOR_ID, "TRACKING")
        self.log_message.emit(
            f"[fake] actor {_FAKE_ACTOR_ID} with {len(names)} joints"
        )

        self._state.set_cameras([(0, "Front Camera"), (1, "Side Camera")])

        self._fake_timer = QTimer(self)
        self._fake_timer.setInterval(16)  # ~60 Hz
        self._fake_timer.timeout.connect(self._emit_fake_pose)
        self._fake_timer.start()

    def _emit_fake_pose(self):
        t = time.monotonic() - self._fake_t0
        timestamp_us = int(t * 1_000_000)
        self._fake_tick += 1

        gait_phase = t * 1.2 * 2 * math.pi
        foot_left = math.sin(gait_phase) > 0
        foot_right = math.sin(gait_phase + math.pi) > 0

        transforms: list[tuple[float, float, float, float, float, float]] = []
        for name, _parent, base in _FAKE_JOINTS:
            bx, by, bz = base
            dx = dy = dz = 0.0
            if "LeftForearm" in name or "LeftHand" in name:
                dy = 120.0 * math.sin(t * 1.4)
                dz =  50.0 * math.sin(t * 1.4 + 0.5)
            elif "RightForearm" in name or "RightHand" in name:
                dy = 120.0 * math.sin(t * 1.4 + math.pi)
                dz =  50.0 * math.sin(t * 1.4 + math.pi + 0.5)
            if name in ("Hips", "Root", "Spine", "Spine1", "Spine2"):
                dx = 25.0 * math.sin(t * 0.6)
            transforms.append((bx + dx, by + dy, bz + dz, 0.0, 0.0, 0.0))

        self._state.update_pose(
            Pose(
                actor_id=_FAKE_ACTOR_ID,
                timestamp_us=timestamp_us,
                quality=max(60, int(85 + 15 * math.sin(t * 0.3))),
                transforms=transforms,
                foot_left=foot_left,
                foot_right=foot_right,
            )
        )

        # Emit angles at ~10 Hz (every 6 ticks)
        if self._fake_tick % 6 == 0:
            self._emit_fake_angles(t, gait_phase)

    def _emit_fake_angles(self, t: float, gait_phase: float):
        angles = {
            "LeftKneeFlexion":        max(0.0, 30 * math.sin(gait_phase) + 15),
            "RightKneeFlexion":       max(0.0, 30 * math.sin(gait_phase + math.pi) + 15),
            "LeftHipFlexion":         20 * math.sin(gait_phase),
            "RightHipFlexion":        20 * math.sin(gait_phase + math.pi),
            "LeftHipAbduction":        5 * math.sin(gait_phase * 0.5),
            "RightHipAbduction":       5 * math.sin(gait_phase * 0.5 + math.pi),
            "LeftAnkleDorsiflexion":  10 * math.sin(gait_phase + 0.5),
            "RightAnkleDorsiflexion": 10 * math.sin(gait_phase + math.pi + 0.5),
            "LeftElbowFlexion":       max(0.0, 40 * math.sin(gait_phase + math.pi) + 20),
            "RightElbowFlexion":      max(0.0, 40 * math.sin(gait_phase) + 20),
            "LeftShoulderFlexion":    25 * math.sin(gait_phase + math.pi),
            "RightShoulderFlexion":   25 * math.sin(gait_phase),
            "TorsoInclination":        5 * math.sin(t * 0.3),
            "TorsoRotation":           8 * math.sin(t * 1.2),
            "NeckFlexion":             3 * math.sin(t * 0.5),
        }
        for name, value in angles.items():
            self._state.update_angle(_FAKE_ACTOR_ID, name, round(value, 1))
