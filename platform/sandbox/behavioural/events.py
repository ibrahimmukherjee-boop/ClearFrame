"""sandbox/behavioural/events.py — Data models for behavioural fine-tuning.

Defines the event types captured from human operator interactions:
  - KeystrokeEvent   : key press timings, dwell times, flight times
  - MouseEvent       : movement velocity, click patterns, scroll behaviour
  - AppLifecycleEvent: app open/close/focus/blur/switch signals
  - SessionRecording : a complete labelled operator session
  - FineTuneExample  : an (instruction, context, response) triple for LLM fine-tuning
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    KEYSTROKE       = "keystroke"
    MOUSE_MOVE      = "mouse_move"
    MOUSE_CLICK     = "mouse_click"
    MOUSE_SCROLL    = "mouse_scroll"
    APP_OPEN        = "app_open"
    APP_CLOSE       = "app_close"
    APP_FOCUS       = "app_focus"
    APP_BLUR        = "app_blur"
    APP_SWITCH      = "app_switch"
    TAB_OPEN        = "tab_open"
    TAB_CLOSE       = "tab_close"
    PASTE           = "paste"
    COPY            = "copy"
    IDLE            = "idle"


class CognitiveLabel(str, Enum):
    """High-level label inferred from behavioural signals."""
    FOCUSED         = "focused"       # smooth, deliberate keystrokes
    EXPLORING       = "exploring"     # lots of mouse movement, tab switching
    DECIDING        = "deciding"      # pause + short bursts
    STRESSED        = "stressed"      # fast irregular keystrokes, high error rate
    IDLE            = "idle"          # no meaningful activity


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------

@dataclass
class BehaviouralEvent:
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    event_type: EventType = EventType.KEYSTROKE
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    operator_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id":    self.event_id,
            "event_type":  self.event_type.value,
            "timestamp":   self.timestamp,
            "session_id":  self.session_id,
            "operator_id": self.operator_id,
            "metadata":    self.metadata,
        }


# ---------------------------------------------------------------------------
# Keystroke event
# ---------------------------------------------------------------------------

@dataclass
class KeystrokeEvent(BehaviouralEvent):
    """Captures timing dynamics of keyboard input.

    dwell_time   : ms key was held down
    flight_time  : ms between key-up and next key-down
    is_backspace : correction signal
    is_special   : modifier / function key
    """
    event_type: EventType = EventType.KEYSTROKE
    key_code: str = ""
    dwell_time_ms: float = 0.0
    flight_time_ms: float = 0.0
    is_backspace: bool = False
    is_special: bool = False
    shift_held: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "key_code":       self.key_code,
            "dwell_time_ms":  self.dwell_time_ms,
            "flight_time_ms": self.flight_time_ms,
            "is_backspace":   self.is_backspace,
            "is_special":     self.is_special,
            "shift_held":     self.shift_held,
        })
        return d


# ---------------------------------------------------------------------------
# Mouse event
# ---------------------------------------------------------------------------

@dataclass
class MouseEvent(BehaviouralEvent):
    """Captures mouse / pointer dynamics.

    velocity     : pixels/ms of movement
    click_button : 'left' | 'right' | 'middle' | None
    scroll_delta : positive = down, negative = up
    target_id    : DOM element id or widget label
    """
    event_type: EventType = EventType.MOUSE_MOVE
    x: float = 0.0
    y: float = 0.0
    velocity: float = 0.0          # px/ms
    acceleration: float = 0.0
    click_button: Optional[str] = None
    scroll_delta: float = 0.0
    target_id: str = ""
    double_click: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "x":            self.x,
            "y":            self.y,
            "velocity":     self.velocity,
            "acceleration": self.acceleration,
            "click_button": self.click_button,
            "scroll_delta": self.scroll_delta,
            "target_id":    self.target_id,
            "double_click": self.double_click,
        })
        return d


# ---------------------------------------------------------------------------
# App lifecycle event
# ---------------------------------------------------------------------------

@dataclass
class AppLifecycleEvent(BehaviouralEvent):
    """Captures application open/close/focus events.

    app_name     : human-readable name  (e.g. 'VSCode', 'Chrome')
    app_id       : bundle id or process name
    window_title : active window title
    duration_ms  : for close/blur events — how long app was active
    previous_app : for switch events
    """
    event_type: EventType = EventType.APP_OPEN
    app_name: str = ""
    app_id: str = ""
    window_title: str = ""
    duration_ms: float = 0.0
    previous_app: str = ""
    url: str = ""  # for browser tabs

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "app_name":     self.app_name,
            "app_id":       self.app_id,
            "window_title": self.window_title,
            "duration_ms":  self.duration_ms,
            "previous_app": self.previous_app,
            "url":          self.url,
        })
        return d


# ---------------------------------------------------------------------------
# Session recording
# ---------------------------------------------------------------------------

@dataclass
class SessionRecording:
    """A labelled sequence of events from one operator work session.

    This is the primary unit fed into the FineTuneLayer.
    A session may span multiple tasks and produce multiple FineTuneExamples.
    """
    recording_id: str = field(default_factory=lambda: "rec-" + uuid.uuid4().hex[:8])
    operator_id: str = ""
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    events: List[BehaviouralEvent] = field(default_factory=list)
    task_label: str = ""            # e.g. 'write_code', 'research', 'data_entry'
    cognitive_label: CognitiveLabel = CognitiveLabel.FOCUSED
    annotations: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    @property
    def keystroke_events(self) -> List[KeystrokeEvent]:
        return [e for e in self.events if isinstance(e, KeystrokeEvent)]

    @property
    def mouse_events(self) -> List[MouseEvent]:
        return [e for e in self.events if isinstance(e, MouseEvent)]

    @property
    def app_events(self) -> List[AppLifecycleEvent]:
        return [e for e in self.events if isinstance(e, AppLifecycleEvent)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recording_id":    self.recording_id,
            "operator_id":     self.operator_id,
            "started_at":      self.started_at,
            "ended_at":        self.ended_at,
            "duration_s":      self.duration_s,
            "task_label":      self.task_label,
            "cognitive_label": self.cognitive_label.value,
            "event_count":     len(self.events),
            "annotations":     self.annotations,
        }


# ---------------------------------------------------------------------------
# Fine-tune example
# ---------------------------------------------------------------------------

@dataclass
class FineTuneExample:
    """A single (instruction, context, response) training triple.

    Compatible with standard JSONL fine-tuning formats used by
    OpenAI, Hugging Face TRL, Axolotl, and LLaMA-Factory.
    """
    example_id: str = field(default_factory=lambda: "ft-" + uuid.uuid4().hex[:8])
    source_recording_id: str = ""
    instruction: str = ""
    context: str = ""          # behavioural context injected as system prompt
    response: str = ""         # ideal agent action / response
    task_type: str = ""        # e.g. 'tool_selection', 'step_planning', 'error_recovery'
    cognitive_label: str = ""
    quality_score: float = 1.0  # 0.0 – 1.0, used for data filtering
    tags: List[str] = field(default_factory=list)

    def to_jsonl(self) -> Dict[str, Any]:
        """Returns dict ready to be serialised as a JSONL fine-tuning row."""
        return {
            "messages": [
                {"role": "system",    "content": self.context},
                {"role": "user",      "content": self.instruction},
                {"role": "assistant", "content": self.response},
            ],
            "metadata": {
                "example_id":           self.example_id,
                "source_recording_id":  self.source_recording_id,
                "task_type":            self.task_type,
                "cognitive_label":      self.cognitive_label,
                "quality_score":        self.quality_score,
                "tags":                 self.tags,
            }
        }
