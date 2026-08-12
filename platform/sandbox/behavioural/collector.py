"""sandbox/behavioural/collector.py — BehaviouralCollector.

Collects and buffers raw human-interaction events into a SessionRecording.
Designed to be driven by:
  - A browser extension / Comet Browser hooks (keyboard + mouse events)
  - OS-level app-lifecycle callbacks (open/close/focus)
  - Manual simulation (for testing and synthetic augmentation)

The collector is intentionally stateless between sessions — each
start_session() call creates a fresh SessionRecording.
"""

from __future__ import annotations

import math
import random
import time
import uuid
from typing import List, Optional

from sandbox.behavioural.events import (
    AppLifecycleEvent,
    BehaviouralEvent,
    CognitiveLabel,
    EventType,
    KeystrokeEvent,
    MouseEvent,
    SessionRecording,
)


class BehaviouralCollector:
    """Records and buffers human interaction events into a SessionRecording.

    Usage (real integration)::

        collector = BehaviouralCollector(operator_id="op-abc123")
        collector.start_session(task_label="write_code")

        # ... events arrive from browser hooks / OS callbacks ...
        collector.record_keystroke(key_code="a", dwell_ms=82, flight_ms=110)
        collector.record_mouse_move(x=450, y=300, velocity=1.2)
        collector.record_app_open(app_name="VSCode")

        recording = collector.end_session()

    Usage (simulation)::

        collector = BehaviouralCollector(operator_id="op-sim")
        recording = collector.simulate_session(
            task_label="research",
            n_keystrokes=120,
            n_mouse_events=80,
            n_app_events=5,
        )
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, operator_id: str = "") -> None:
        self.operator_id = operator_id or "op-" + uuid.uuid4().hex[:8]
        self._recording: Optional[SessionRecording] = None
        self._session_id: str = ""
        self._last_key_up_time: float = 0.0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        task_label: str = "",
        cognitive_label: CognitiveLabel = CognitiveLabel.FOCUSED,
    ) -> str:
        """Begin a new recording session.  Returns session_id."""
        self._session_id = "bhv-" + uuid.uuid4().hex[:8]
        self._recording = SessionRecording(
            operator_id=self.operator_id,
            started_at=time.time(),
            task_label=task_label,
            cognitive_label=cognitive_label,
        )
        self._last_key_up_time = time.time()
        return self._session_id

    def end_session(self) -> SessionRecording:
        """Finalise and return the completed SessionRecording."""
        if self._recording is None:
            raise RuntimeError("No active session. Call start_session() first.")
        self._recording.ended_at = time.time()
        # Infer cognitive label from collected metrics
        self._recording.cognitive_label = self._infer_cognitive_label()
        recording = self._recording
        self._recording = None
        self._session_id = ""
        return recording

    @property
    def is_recording(self) -> bool:
        return self._recording is not None

    # ------------------------------------------------------------------
    # Event recording methods
    # ------------------------------------------------------------------

    def record_keystroke(
        self,
        key_code: str,
        dwell_ms: float,
        flight_ms: float = 0.0,
        is_backspace: bool = False,
        is_special: bool = False,
        shift_held: bool = False,
    ) -> None:
        self._ensure_session()
        ev = KeystrokeEvent(
            session_id=self._session_id,
            operator_id=self.operator_id,
            key_code=key_code,
            dwell_time_ms=dwell_ms,
            flight_time_ms=flight_ms,
            is_backspace=is_backspace,
            is_special=is_special,
            shift_held=shift_held,
        )
        self._recording.events.append(ev)  # type: ignore[union-attr]

    def record_mouse_move(
        self,
        x: float,
        y: float,
        velocity: float = 0.0,
        acceleration: float = 0.0,
        target_id: str = "",
    ) -> None:
        self._ensure_session()
        ev = MouseEvent(
            event_type=EventType.MOUSE_MOVE,
            session_id=self._session_id,
            operator_id=self.operator_id,
            x=x, y=y,
            velocity=velocity,
            acceleration=acceleration,
            target_id=target_id,
        )
        self._recording.events.append(ev)  # type: ignore[union-attr]

    def record_mouse_click(
        self,
        x: float,
        y: float,
        button: str = "left",
        double_click: bool = False,
        target_id: str = "",
    ) -> None:
        self._ensure_session()
        ev = MouseEvent(
            event_type=EventType.MOUSE_CLICK,
            session_id=self._session_id,
            operator_id=self.operator_id,
            x=x, y=y,
            click_button=button,
            double_click=double_click,
            target_id=target_id,
        )
        self._recording.events.append(ev)  # type: ignore[union-attr]

    def record_scroll(
        self,
        x: float,
        y: float,
        delta: float,
        target_id: str = "",
    ) -> None:
        self._ensure_session()
        ev = MouseEvent(
            event_type=EventType.MOUSE_SCROLL,
            session_id=self._session_id,
            operator_id=self.operator_id,
            x=x, y=y,
            scroll_delta=delta,
            target_id=target_id,
        )
        self._recording.events.append(ev)  # type: ignore[union-attr]

    def record_app_open(
        self,
        app_name: str,
        app_id: str = "",
        window_title: str = "",
        url: str = "",
    ) -> None:
        self._record_app_event(
            EventType.APP_OPEN, app_name, app_id, window_title, url=url
        )

    def record_app_close(
        self,
        app_name: str,
        duration_ms: float = 0.0,
    ) -> None:
        self._record_app_event(
            EventType.APP_CLOSE, app_name, duration_ms=duration_ms
        )

    def record_app_switch(
        self,
        app_name: str,
        previous_app: str = "",
        window_title: str = "",
        url: str = "",
    ) -> None:
        self._record_app_event(
            EventType.APP_SWITCH,
            app_name,
            window_title=window_title,
            previous_app=previous_app,
            url=url,
        )

    def record_tab_open(self, url: str, window_title: str = "") -> None:
        self._record_app_event(
            EventType.TAB_OPEN, "browser", window_title=window_title, url=url
        )

    def record_tab_close(self, url: str, duration_ms: float = 0.0) -> None:
        self._record_app_event(
            EventType.TAB_CLOSE, "browser", url=url, duration_ms=duration_ms
        )

    # ------------------------------------------------------------------
    # Simulation helpers
    # ------------------------------------------------------------------

    def simulate_session(
        self,
        task_label: str = "generic_task",
        n_keystrokes: int = 100,
        n_mouse_events: int = 60,
        n_app_events: int = 4,
        cognitive_profile: CognitiveLabel = CognitiveLabel.FOCUSED,
    ) -> SessionRecording:
        """Generate a synthetic session with realistic behavioural statistics.

        Cognitive profiles influence timing distributions:
          FOCUSED   → lower dwell variance, consistent flight times
          EXPLORING → high mouse velocity, frequent app switches
          DECIDING  → long flight times (pauses), short bursts
          STRESSED  → high backspace rate, irregular dwell times
        """
        self.start_session(task_label=task_label, cognitive_label=cognitive_profile)

        # Keystroke simulation
        dwell_mean, dwell_std = self._profile_keystroke_params(cognitive_profile)
        backspace_rate = self._profile_backspace_rate(cognitive_profile)
        for i in range(n_keystrokes):
            dwell = max(20.0, random.gauss(dwell_mean, dwell_std))
            flight = max(10.0, random.gauss(
                self._profile_flight_mean(cognitive_profile), 40.0
            ))
            is_bs = random.random() < backspace_rate
            self.record_keystroke(
                key_code="Backspace" if is_bs else chr(random.randint(97, 122)),
                dwell_ms=dwell,
                flight_ms=flight,
                is_backspace=is_bs,
            )

        # Mouse simulation
        x, y = 640.0, 400.0
        for _ in range(n_mouse_events):
            dx = random.gauss(0, 80)
            dy = random.gauss(0, 60)
            x = max(0.0, min(1280.0, x + dx))
            y = max(0.0, min(800.0, y + dy))
            vel = abs(random.gauss(
                self._profile_mouse_velocity(cognitive_profile), 0.5
            ))
            if random.random() < 0.2:  # 20% are clicks
                self.record_mouse_click(x, y, target_id=f"widget_{random.randint(1,20)}")
            elif random.random() < 0.1:  # 10% are scrolls
                self.record_scroll(x, y, delta=random.choice([-3, -1, 1, 3]))
            else:
                self.record_mouse_move(x, y, velocity=vel)

        # App lifecycle simulation
        apps = ["VSCode", "Chrome", "Terminal", "Slack", "Figma", "Notion"]
        urls = [
            "https://github.com", "https://docs.python.org",
            "https://arxiv.org", "https://stackoverflow.com",
        ]
        prev = apps[0]
        for _ in range(n_app_events):
            app = random.choice(apps)
            if cognitive_profile == CognitiveLabel.EXPLORING:
                self.record_app_switch(
                    app_name=app, previous_app=prev,
                    url=random.choice(urls) if app == "Chrome" else "",
                )
            else:
                if random.random() < 0.5:
                    self.record_tab_open(url=random.choice(urls))
                else:
                    self.record_app_open(app_name=app)
            prev = app

        return self.end_session()

    # ------------------------------------------------------------------
    # Cognitive inference
    # ------------------------------------------------------------------

    def _infer_cognitive_label(self) -> CognitiveLabel:
        """Heuristic label inference from collected events."""
        if self._recording is None:
            return CognitiveLabel.IDLE

        keys = self._recording.keystroke_events
        mouse = self._recording.mouse_events
        apps = self._recording.app_events

        if not keys and not mouse:
            return CognitiveLabel.IDLE

        # Backspace rate → stress signal
        if keys:
            bs_rate = sum(1 for k in keys if k.is_backspace) / len(keys)
            avg_dwell = sum(k.dwell_time_ms for k in keys) / len(keys)
            dwell_std = math.sqrt(
                sum((k.dwell_time_ms - avg_dwell) ** 2 for k in keys) / len(keys)
            )
            if bs_rate > 0.15 or dwell_std > 60:
                return CognitiveLabel.STRESSED

        # Many app switches → exploring
        switches = [e for e in apps if e.event_type == EventType.APP_SWITCH]
        if len(switches) >= 3:
            return CognitiveLabel.EXPLORING

        # Long flight times (pauses) → deciding
        if keys:
            avg_flight = sum(k.flight_time_ms for k in keys) / len(keys)
            if avg_flight > 300:
                return CognitiveLabel.DECIDING

        return CognitiveLabel.FOCUSED

    # ------------------------------------------------------------------
    # Profile helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _profile_keystroke_params(
        profile: CognitiveLabel,
    ) -> tuple[float, float]:
        return {
            CognitiveLabel.FOCUSED:   (80.0, 15.0),
            CognitiveLabel.EXPLORING: (90.0, 20.0),
            CognitiveLabel.DECIDING:  (100.0, 30.0),
            CognitiveLabel.STRESSED:  (65.0, 40.0),
            CognitiveLabel.IDLE:      (120.0, 50.0),
        }[profile]

    @staticmethod
    def _profile_backspace_rate(profile: CognitiveLabel) -> float:
        return {
            CognitiveLabel.FOCUSED:   0.04,
            CognitiveLabel.EXPLORING: 0.06,
            CognitiveLabel.DECIDING:  0.08,
            CognitiveLabel.STRESSED:  0.20,
            CognitiveLabel.IDLE:      0.02,
        }[profile]

    @staticmethod
    def _profile_flight_mean(profile: CognitiveLabel) -> float:
        return {
            CognitiveLabel.FOCUSED:   120.0,
            CognitiveLabel.EXPLORING: 140.0,
            CognitiveLabel.DECIDING:  350.0,
            CognitiveLabel.STRESSED:  90.0,
            CognitiveLabel.IDLE:      500.0,
        }[profile]

    @staticmethod
    def _profile_mouse_velocity(profile: CognitiveLabel) -> float:
        return {
            CognitiveLabel.FOCUSED:   1.2,
            CognitiveLabel.EXPLORING: 2.5,
            CognitiveLabel.DECIDING:  0.8,
            CognitiveLabel.STRESSED:  3.0,
            CognitiveLabel.IDLE:      0.3,
        }[profile]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_session(self) -> None:
        if self._recording is None:
            raise RuntimeError("No active session. Call start_session() first.")

    def _record_app_event(
        self,
        event_type: EventType,
        app_name: str,
        app_id: str = "",
        window_title: str = "",
        previous_app: str = "",
        url: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        self._ensure_session()
        ev = AppLifecycleEvent(
            event_type=event_type,
            session_id=self._session_id,
            operator_id=self.operator_id,
            app_name=app_name,
            app_id=app_id,
            window_title=window_title,
            previous_app=previous_app,
            url=url,
            duration_ms=duration_ms,
        )
        self._recording.events.append(ev)  # type: ignore[union-attr]
