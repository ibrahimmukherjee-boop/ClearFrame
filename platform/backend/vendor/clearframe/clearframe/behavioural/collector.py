"""clearframe/clearframe/behavioural/collector.py

Event collection, buffering, and session management.

The BehaviouralCollector is the main entry point for recording human
interaction events.  It maintains an in-memory ring buffer, emits
higher-level TextEditEvents from raw keystroke bursts, and can persist
sessions to JSONL files for offline processing.
"""

from __future__ import annotations

import json
import pathlib
import threading
import time
import uuid
from collections import deque
from typing import Callable, Deque, List, Optional, Union

from .events import (
    AppFocusEvent,
    AppLifecycleAction,
    AppLifecycleEvent,
    BehaviouralEvent,
    ClipboardAction,
    ClipboardEvent,
    EventKind,
    KeyEvent,
    MouseClickEvent,
    MouseMoveEvent,
    MouseScrollEvent,
    SessionAction,
    SessionEvent,
    TextEditEvent,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BUFFER_SIZE   = 10_000   # max events kept in memory
_KEY_BURST_GAP_MS      = 2_000    # gap (ms) that ends a typing burst
_MOUSE_SAMPLE_RATE_MS  = 50       # min ms between stored move events


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class BehaviouralCollector:
    """Records and buffers raw behavioural events from a user session.

    Usage
    -----
    >>> collector = BehaviouralCollector(user_id="user_abc")
    >>> collector.start_session()
    >>> collector.record_key_down("a")
    >>> collector.record_key_up("a", dwell_ms=82.0)
    >>> collector.stop_session()
    >>> events = collector.flush()
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
        on_event: Optional[Callable[[BehaviouralEvent], None]] = None,
        auto_emit_text_edits: bool = True,
    ) -> None:
        self.user_id    = user_id or str(uuid.uuid4())
        self._buffer: Deque[BehaviouralEvent] = deque(maxlen=buffer_size)
        self._on_event  = on_event
        self._auto_emit = auto_emit_text_edits
        self._lock      = threading.Lock()

        # Session state
        self._session_id: Optional[str] = None
        self._session_start: Optional[float] = None
        self._active = False

        # Typing burst accumulator
        self._key_burst: List[KeyEvent] = []
        self._last_key_time: Optional[float] = None

        # Mouse move throttle
        self._last_mouse_time: float = 0.0
        self._prev_mouse_x: float = 0.0
        self._prev_mouse_y: float = 0.0

        # App tracking
        self._current_app: Optional[str] = None
        self._app_open_times: dict = {}   # app_name -> open timestamp

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self, session_id: Optional[str] = None) -> str:
        """Begin a new recording session.  Returns the session id."""
        with self._lock:
            self._session_id    = session_id or str(uuid.uuid4())
            self._session_start = time.time()
            self._active        = True
            evt = SessionEvent(
                kind=EventKind.SESSION,
                session_id=self._session_id,
                action=SessionAction.START,
                user_id=self.user_id,
            )
            self._emit(evt)
            return self._session_id

    def stop_session(self) -> None:
        """End the current session; flushes any pending typing burst."""
        with self._lock:
            if not self._active:
                return
            self._flush_key_burst()
            self._active = False
            evt = SessionEvent(
                kind=EventKind.SESSION,
                session_id=self._session_id or "",
                action=SessionAction.END,
                user_id=self.user_id,
            )
            self._emit(evt)

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    # ------------------------------------------------------------------
    # Keyboard recording
    # ------------------------------------------------------------------

    def record_key_down(
        self,
        key_code: str,
        app_name: Optional[str] = None,
        is_modifier: bool = False,
    ) -> None:
        """Record a key-down event."""
        if not self._active:
            return
        now = time.time()
        flight_ms: Optional[float] = None
        if self._last_key_time is not None:
            flight_ms = (now - self._last_key_time) * 1000

            # Gap too large → emit previous burst before starting a new one
            if flight_ms > _KEY_BURST_GAP_MS and self._auto_emit:
                with self._lock:
                    self._flush_key_burst()

        evt = KeyEvent(
            kind=EventKind.KEY_DOWN,
            session_id=self._session_id or "",
            timestamp=now,
            key_code=key_code,
            is_modifier=is_modifier,
            flight_ms=flight_ms,
            app_name=app_name or self._current_app,
        )
        with self._lock:
            self._key_burst.append(evt)
            self._emit(evt)
        self._last_key_time = now

    def record_key_up(
        self,
        key_code: str,
        dwell_ms: Optional[float] = None,
        app_name: Optional[str] = None,
    ) -> None:
        """Record a key-up event."""
        if not self._active:
            return
        now = time.time()
        evt = KeyEvent(
            kind=EventKind.KEY_UP,
            session_id=self._session_id or "",
            timestamp=now,
            key_code=key_code,
            dwell_ms=dwell_ms,
            app_name=app_name or self._current_app,
        )
        with self._lock:
            self._emit(evt)
        self._last_key_time = now

    # ------------------------------------------------------------------
    # Mouse recording
    # ------------------------------------------------------------------

    def record_mouse_move(
        self, x: float, y: float, app_name: Optional[str] = None
    ) -> None:
        """Record a cursor move (throttled by _MOUSE_SAMPLE_RATE_MS)."""
        if not self._active:
            return
        now_ms = time.time() * 1000
        if now_ms - self._last_mouse_time < _MOUSE_SAMPLE_RATE_MS:
            return
        dt_s = (now_ms - self._last_mouse_time) / 1000 or 0.001
        dx = x - self._prev_mouse_x
        dy = y - self._prev_mouse_y
        speed = ((dx**2 + dy**2) ** 0.5) / dt_s
        evt = MouseMoveEvent(
            kind=EventKind.MOUSE_MOVE,
            session_id=self._session_id or "",
            x=x, y=y, dx=dx, dy=dy, speed_px_s=speed,
            app_name=app_name or self._current_app,
        )
        with self._lock:
            self._emit(evt)
        self._last_mouse_time = now_ms
        self._prev_mouse_x = x
        self._prev_mouse_y = y

    def record_mouse_click(
        self,
        x: float,
        y: float,
        button: str = "left",
        phase: str = "press",
        app_name: Optional[str] = None,
    ) -> None:
        """Record a mouse button click."""
        if not self._active:
            return
        from .events import ClickPhase, MouseButton
        evt = MouseClickEvent(
            kind=EventKind.MOUSE_CLICK,
            session_id=self._session_id or "",
            x=x, y=y,
            button=MouseButton(button),
            phase=ClickPhase(phase),
            app_name=app_name or self._current_app,
        )
        with self._lock:
            self._emit(evt)

    def record_scroll(
        self,
        x: float, y: float,
        delta_x: float = 0.0, delta_y: float = 0.0,
        app_name: Optional[str] = None,
    ) -> None:
        """Record a scroll-wheel event."""
        if not self._active:
            return
        from .events import MouseScrollEvent
        evt = MouseScrollEvent(
            kind=EventKind.MOUSE_SCROLL,
            session_id=self._session_id or "",
            x=x, y=y, delta_x=delta_x, delta_y=delta_y,
            app_name=app_name or self._current_app,
        )
        with self._lock:
            self._emit(evt)

    # ------------------------------------------------------------------
    # App-level recording
    # ------------------------------------------------------------------

    def record_app_focus(
        self, app_name: str, gained: bool = True
    ) -> None:
        """Record an application focus change."""
        if not self._active:
            return
        previous = self._current_app if gained else None
        if gained:
            self._current_app = app_name
        evt = AppFocusEvent(
            kind=EventKind.APP_FOCUS,
            session_id=self._session_id or "",
            app_name=app_name,
            gained_focus=gained,
            previous_app=previous,
        )
        with self._lock:
            self._emit(evt)

    def record_app_open(self, app_name: str, process_name: Optional[str] = None) -> None:
        """Record that an application was opened."""
        if not self._active:
            return
        self._app_open_times[app_name] = time.time()
        evt = AppLifecycleEvent(
            kind=EventKind.APP_LIFECYCLE,
            session_id=self._session_id or "",
            app_name=app_name,
            action=AppLifecycleAction.OPEN,
            process_name=process_name,
        )
        with self._lock:
            self._emit(evt)

    def record_app_close(self, app_name: str, process_name: Optional[str] = None) -> None:
        """Record that an application was closed."""
        if not self._active:
            return
        open_time = self._app_open_times.pop(app_name, None)
        duration = (time.time() - open_time) if open_time else None
        evt = AppLifecycleEvent(
            kind=EventKind.APP_LIFECYCLE,
            session_id=self._session_id or "",
            app_name=app_name,
            action=AppLifecycleAction.CLOSE,
            process_name=process_name,
            duration_s=duration,
        )
        with self._lock:
            self._emit(evt)

    def record_clipboard(
        self,
        action: str = "copy",
        content_length: int = 0,
        app_name: Optional[str] = None,
    ) -> None:
        """Record a clipboard interaction."""
        if not self._active:
            return
        evt = ClipboardEvent(
            kind=EventKind.CLIPBOARD,
            session_id=self._session_id or "",
            action=ClipboardAction(action),
            content_length=content_length,
            app_name=app_name or self._current_app,
        )
        with self._lock:
            self._emit(evt)

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def flush(self) -> List[BehaviouralEvent]:
        """Return a copy of all buffered events and clear the buffer."""
        with self._lock:
            self._flush_key_burst()
            events = list(self._buffer)
            self._buffer.clear()
            return events

    def peek(self) -> List[BehaviouralEvent]:
        """Return a snapshot of buffered events WITHOUT clearing."""
        with self._lock:
            return list(self._buffer)

    def __len__(self) -> int:
        return len(self._buffer)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_session(
        self,
        path: Union[str, pathlib.Path],
        flush: bool = True,
    ) -> pathlib.Path:
        """Persist buffered events to a JSONL file.

        Each line is a JSON object representing one event.
        If *flush* is True the buffer is cleared after writing.
        """
        p = pathlib.Path(path)
        if not p.suffix:
            p = p.with_suffix(".jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        events = self.flush() if flush else self.peek()
        with p.open("w", encoding="utf-8") as fh:
            for evt in events:
                fh.write(json.dumps(evt.to_dict()) + "\n")
        return p.resolve()

    @classmethod
    def load_session(cls, path: Union[str, pathlib.Path]) -> List[BehaviouralEvent]:
        """Load events from a JSONL file previously written by save_session."""
        from .events import event_from_dict
        p = pathlib.Path(path)
        events: List[BehaviouralEvent] = []
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(event_from_dict(json.loads(line)))
        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(self, evt: BehaviouralEvent) -> None:
        """Add event to buffer and trigger callback (call under lock)."""
        self._buffer.append(evt)
        if self._on_event:
            try:
                self._on_event(evt)
            except Exception:  # pragma: no cover
                pass

    def _flush_key_burst(self) -> None:
        """Convert the current typing burst into a TextEditEvent."""
        if not self._key_burst:
            return
        burst = self._key_burst
        self._key_burst = []

        char_count  = sum(1 for k in burst if k.kind == EventKind.KEY_DOWN
                          and not k.is_modifier and len(k.key_code) == 1)
        delete_count = sum(1 for k in burst if k.kind == EventKind.KEY_DOWN
                           and k.key_code in ("Backspace", "Delete"))
        word_count  = max(1, char_count // 5)

        dwells  = [k.dwell_ms  for k in burst if k.dwell_ms  is not None]
        flights = [k.flight_ms for k in burst if k.flight_ms is not None]

        duration_ms = (burst[-1].timestamp - burst[0].timestamp) * 1000
        wpm = (word_count / (duration_ms / 60_000)) if duration_ms > 0 else 0.0

        te = TextEditEvent(
            kind=EventKind.TEXT_EDIT,
            session_id=burst[0].session_id,
            timestamp=burst[0].timestamp,
            app_name=burst[0].app_name,
            char_count=char_count,
            word_count=word_count,
            delete_count=delete_count,
            duration_ms=duration_ms,
            wpm=round(wpm, 2),
            avg_dwell_ms=round(sum(dwells)  / len(dwells),  2) if dwells  else 0.0,
            avg_flight_ms=round(sum(flights) / len(flights), 2) if flights else 0.0,
        )
        self._buffer.append(te)
        if self._on_event:
            try:
                self._on_event(te)
            except Exception:  # pragma: no cover
                pass
