"""clearframe/clearframe/behavioural/events.py

Raw behavioural event dataclasses.

Inspired by WhiteMatter's typing/mouse stress-detection work, this module
generalises the signal capture layer: instead of measuring *stress* we
capture *intent and workflow patterns* that can be used to fine-tune AI
agents to operate more like the human they observed.

Event hierarchy
---------------
BehaviouralEvent          (abstract base)
  KeyEvent                keystroke down/up + timing
  MouseMoveEvent          cursor trajectory sample
  MouseClickEvent         button press/release
  MouseScrollEvent        scroll wheel delta
  AppFocusEvent           app gained / lost foreground focus
  AppLifecycleEvent       app opened / closed / minimised / restored
  ClipboardEvent          copy / cut / paste action
  TextEditEvent           higher-level: typed word or deleted region
  SessionEvent            session start / end marker
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EventKind(str, Enum):
    KEY_DOWN          = "key_down"
    KEY_UP            = "key_up"
    MOUSE_MOVE        = "mouse_move"
    MOUSE_CLICK       = "mouse_click"
    MOUSE_SCROLL      = "mouse_scroll"
    APP_FOCUS         = "app_focus"
    APP_LIFECYCLE     = "app_lifecycle"
    CLIPBOARD         = "clipboard"
    TEXT_EDIT         = "text_edit"
    SESSION           = "session"


class MouseButton(str, Enum):
    LEFT   = "left"
    RIGHT  = "right"
    MIDDLE = "middle"
    OTHER  = "other"


class ClickPhase(str, Enum):
    PRESS   = "press"
    RELEASE = "release"
    DOUBLE  = "double"


class AppLifecycleAction(str, Enum):
    OPEN      = "open"
    CLOSE     = "close"
    MINIMISE  = "minimise"
    RESTORE   = "restore"
    FOCUS     = "focus"
    BLUR      = "blur"
    SWITCH    = "switch"


class ClipboardAction(str, Enum):
    COPY  = "copy"
    CUT   = "cut"
    PASTE = "paste"


class SessionAction(str, Enum):
    START = "start"
    END   = "end"
    PAUSE = "pause"
    RESUME = "resume"


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------

@dataclass
class BehaviouralEvent:
    """Abstract base for all behavioural events."""

    kind: EventKind
    timestamp: float = field(default_factory=time.time)   # Unix epoch seconds
    session_id: str  = field(default_factory=lambda: str(uuid.uuid4()))
    app_name: Optional[str] = None          # Active application name
    app_window: Optional[str] = None        # Window title
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "app_name": self.app_name,
            "app_window": self.app_window,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Keyboard events
# ---------------------------------------------------------------------------

@dataclass
class KeyEvent(BehaviouralEvent):
    """A single key press or release.

    Attributes
    ----------
    key_code:
        Platform-agnostic key identifier (e.g. ``"a"``, ``"Shift"``).
    is_modifier:
        True for Shift, Ctrl, Alt, Meta etc.
    dwell_ms:
        Time between key-down and key-up in milliseconds (populated on UP
        events; None on DOWN events).
    flight_ms:
        Inter-key interval (time from previous key-up to this key-down)
        in milliseconds.  None when no prior key exists.
    """

    key_code: str = ""
    is_modifier: bool = False
    dwell_ms: Optional[float] = None
    flight_ms: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.kind:
            self.kind = EventKind.KEY_DOWN

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "key_code": self.key_code,
            "is_modifier": self.is_modifier,
            "dwell_ms": self.dwell_ms,
            "flight_ms": self.flight_ms,
        })
        return d


# ---------------------------------------------------------------------------
# Mouse events
# ---------------------------------------------------------------------------

@dataclass
class MouseMoveEvent(BehaviouralEvent):
    """Cursor position sample."""

    x: float = 0.0
    y: float = 0.0
    dx: float = 0.0   # delta from previous sample
    dy: float = 0.0
    speed_px_s: float = 0.0   # instantaneous speed in pixels/sec
    kind: EventKind = EventKind.MOUSE_MOVE

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"x": self.x, "y": self.y, "dx": self.dx, "dy": self.dy,
                  "speed_px_s": self.speed_px_s})
        return d


@dataclass
class MouseClickEvent(BehaviouralEvent):
    """Mouse button click."""

    x: float = 0.0
    y: float = 0.0
    button: MouseButton = MouseButton.LEFT
    phase: ClickPhase = ClickPhase.PRESS
    kind: EventKind = EventKind.MOUSE_CLICK

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"x": self.x, "y": self.y,
                  "button": self.button.value, "phase": self.phase.value})
        return d


@dataclass
class MouseScrollEvent(BehaviouralEvent):
    """Scroll wheel event."""

    x: float = 0.0
    y: float = 0.0
    delta_x: float = 0.0
    delta_y: float = 0.0
    kind: EventKind = EventKind.MOUSE_SCROLL

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"x": self.x, "y": self.y,
                  "delta_x": self.delta_x, "delta_y": self.delta_y})
        return d


# ---------------------------------------------------------------------------
# App-level events
# ---------------------------------------------------------------------------

@dataclass
class AppFocusEvent(BehaviouralEvent):
    """Application gained or lost focus."""

    gained_focus: bool = True
    previous_app: Optional[str] = None
    kind: EventKind = EventKind.APP_FOCUS

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"gained_focus": self.gained_focus,
                  "previous_app": self.previous_app})
        return d


@dataclass
class AppLifecycleEvent(BehaviouralEvent):
    """Application opened, closed, minimised, etc."""

    action: AppLifecycleAction = AppLifecycleAction.OPEN
    process_name: Optional[str] = None
    duration_s: Optional[float] = None   # e.g. how long app was open (on CLOSE)
    kind: EventKind = EventKind.APP_LIFECYCLE

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"action": self.action.value,
                  "process_name": self.process_name,
                  "duration_s": self.duration_s})
        return d


# ---------------------------------------------------------------------------
# Clipboard events
# ---------------------------------------------------------------------------

@dataclass
class ClipboardEvent(BehaviouralEvent):
    """Copy, cut or paste action.

    Note: content is intentionally NOT stored to preserve privacy.
    Only the length and action type are captured.
    """

    action: ClipboardAction = ClipboardAction.COPY
    content_length: int = 0   # character count, never the text itself
    kind: EventKind = EventKind.CLIPBOARD

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"action": self.action.value,
                  "content_length": self.content_length})
        return d


# ---------------------------------------------------------------------------
# Higher-level text edit event
# ---------------------------------------------------------------------------

@dataclass
class TextEditEvent(BehaviouralEvent):
    """Aggregated text editing action (word typed, region deleted, etc.).

    This is a higher-level event emitted by the collector after digesting
    a burst of KeyEvents.  The raw text is hashed, not stored.
    """

    char_count: int = 0
    word_count: int = 0
    delete_count: int = 0       # backspace / delete keystrokes
    duration_ms: float = 0.0    # total time for this edit burst
    wpm: float = 0.0            # words per minute during burst
    avg_dwell_ms: float = 0.0
    avg_flight_ms: float = 0.0
    kind: EventKind = EventKind.TEXT_EDIT

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "char_count": self.char_count,
            "word_count": self.word_count,
            "delete_count": self.delete_count,
            "duration_ms": self.duration_ms,
            "wpm": self.wpm,
            "avg_dwell_ms": self.avg_dwell_ms,
            "avg_flight_ms": self.avg_flight_ms,
        })
        return d


# ---------------------------------------------------------------------------
# Session marker
# ---------------------------------------------------------------------------

@dataclass
class SessionEvent(BehaviouralEvent):
    """Marks the start or end of a behavioural recording session."""

    action: SessionAction = SessionAction.START
    user_id: Optional[str] = None     # anonymised user identifier
    kind: EventKind = EventKind.SESSION

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"action": self.action.value, "user_id": self.user_id})
        return d


# ---------------------------------------------------------------------------
# Deserialisation helper
# ---------------------------------------------------------------------------

_KIND_TO_CLASS = {
    EventKind.KEY_DOWN:       KeyEvent,
    EventKind.KEY_UP:         KeyEvent,
    EventKind.MOUSE_MOVE:     MouseMoveEvent,
    EventKind.MOUSE_CLICK:    MouseClickEvent,
    EventKind.MOUSE_SCROLL:   MouseScrollEvent,
    EventKind.APP_FOCUS:      AppFocusEvent,
    EventKind.APP_LIFECYCLE:  AppLifecycleEvent,
    EventKind.CLIPBOARD:      ClipboardEvent,
    EventKind.TEXT_EDIT:      TextEditEvent,
    EventKind.SESSION:        SessionEvent,
}


def event_from_dict(data: Dict[str, Any]) -> BehaviouralEvent:
    """Reconstruct a BehaviouralEvent subclass from a plain dict."""
    kind = EventKind(data["kind"])
    cls  = _KIND_TO_CLASS.get(kind, BehaviouralEvent)
    # Strip keys that the base class doesn't accept as constructor args
    init_data = {k: v for k, v in data.items() if k != "kind"}
    return cls(kind=kind, **init_data)  # type: ignore[arg-type]
