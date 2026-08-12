"""clearframe/clearframe/behavioural/features.py

Feature extraction from raw behavioural event streams.

Converts lists of BehaviouralEvents into structured numeric/categorical
feature vectors (FeatureVector) that can be consumed by downstream
fine-tuning pipelines or used to build agent behaviour profiles.

Feature groups
--------------
typing     - WPM, dwell/flight stats, error-correction rate
mouse      - speed, click rate, scroll velocity, trajectory smoothness
app_usage  - app switch rate, session length per app, multitasking index
workflow   - task sequence patterns, clipboard usage, focus duration
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .events import (
    AppLifecycleEvent,
    BehaviouralEvent,
    ClipboardEvent,
    EventKind,
    MouseClickEvent,
    MouseMoveEvent,
    MouseScrollEvent,
    TextEditEvent,
    AppFocusEvent,
)


# ---------------------------------------------------------------------------
# Feature vector
# ---------------------------------------------------------------------------

@dataclass
class FeatureVector:
    """Numeric feature representation of a behavioural session window."""

    session_id: str = ""
    window_start: float = 0.0
    window_end: float = 0.0

    # --- Typing features ---
    typing_wpm_mean: float = 0.0
    typing_wpm_std: float = 0.0
    typing_dwell_mean_ms: float = 0.0
    typing_dwell_std_ms: float = 0.0
    typing_flight_mean_ms: float = 0.0
    typing_flight_std_ms: float = 0.0
    typing_error_rate: float = 0.0      # delete_count / char_count
    typing_burst_count: int = 0
    typing_total_chars: int = 0

    # --- Mouse features ---
    mouse_speed_mean_px_s: float = 0.0
    mouse_speed_std_px_s: float = 0.0
    mouse_click_rate_per_min: float = 0.0
    mouse_scroll_rate_per_min: float = 0.0
    mouse_trajectory_smoothness: float = 0.0   # 1 = perfectly straight
    mouse_total_distance_px: float = 0.0

    # --- App usage features ---
    app_switch_rate_per_min: float = 0.0
    app_unique_count: int = 0
    app_session_duration_mean_s: float = 0.0
    multitasking_index: float = 0.0    # fraction of time with >1 app focused

    # --- Workflow features ---
    clipboard_copy_rate_per_min: float = 0.0
    clipboard_paste_rate_per_min: float = 0.0
    focus_duration_mean_s: float = 0.0
    session_duration_s: float = 0.0

    # --- Metadata ---
    event_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_numeric_array(self) -> List[float]:
        """Return a flat list of all numeric features (for ML pipelines)."""
        skip = {"session_id", "metadata"}
        return [
            float(v) for k, v in asdict(self).items()
            if k not in skip and isinstance(v, (int, float))
        ]

    @classmethod
    def feature_names(cls) -> List[str]:
        """Return the ordered list of numeric feature names."""
        skip = {"session_id", "metadata"}
        return [
            k for k, v in cls.__dataclass_fields__.items()
            if k not in skip
        ]


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class BehaviouralFeatureExtractor:
    """Extracts a FeatureVector from a list of BehaviouralEvents.

    Usage
    -----
    >>> extractor = BehaviouralFeatureExtractor()
    >>> fv = extractor.extract(events)
    >>> print(fv.typing_wpm_mean)
    """

    def extract(
        self,
        events: List[BehaviouralEvent],
        session_id: Optional[str] = None,
    ) -> FeatureVector:
        """Compute a FeatureVector from *events*."""
        if not events:
            return FeatureVector(session_id=session_id or "")

        sid  = session_id or events[0].session_id
        t0   = events[0].timestamp
        t1   = events[-1].timestamp
        dur  = max(t1 - t0, 1e-6)
        dur_min = dur / 60

        fv = FeatureVector(
            session_id=sid,
            window_start=t0,
            window_end=t1,
            session_duration_s=dur,
            event_count=len(events),
        )

        self._extract_typing(events, fv)
        self._extract_mouse(events, fv, dur_min)
        self._extract_app_usage(events, fv, dur_min)
        self._extract_workflow(events, fv, dur_min)

        return fv

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    def _extract_typing(
        self, events: List[BehaviouralEvent], fv: FeatureVector
    ) -> None:
        bursts: List[TextEditEvent] = [
            e for e in events if isinstance(e, TextEditEvent)
        ]
        if not bursts:
            return

        wpms   = [b.wpm for b in bursts if b.wpm > 0]
        dwells = [b.avg_dwell_ms  for b in bursts if b.avg_dwell_ms  > 0]
        flights= [b.avg_flight_ms for b in bursts if b.avg_flight_ms > 0]
        total_chars   = sum(b.char_count   for b in bursts)
        total_deletes = sum(b.delete_count for b in bursts)

        fv.typing_burst_count    = len(bursts)
        fv.typing_total_chars    = total_chars
        fv.typing_wpm_mean       = _mean(wpms)
        fv.typing_wpm_std        = _std(wpms)
        fv.typing_dwell_mean_ms  = _mean(dwells)
        fv.typing_dwell_std_ms   = _std(dwells)
        fv.typing_flight_mean_ms = _mean(flights)
        fv.typing_flight_std_ms  = _std(flights)
        fv.typing_error_rate     = (
            total_deletes / total_chars if total_chars > 0 else 0.0
        )

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def _extract_mouse(
        self,
        events: List[BehaviouralEvent],
        fv: FeatureVector,
        dur_min: float,
    ) -> None:
        moves  = [e for e in events if isinstance(e, MouseMoveEvent)]
        clicks = [e for e in events if isinstance(e, MouseClickEvent)]
        scrolls= [e for e in events if isinstance(e, MouseScrollEvent)]

        if moves:
            speeds = [m.speed_px_s for m in moves]
            fv.mouse_speed_mean_px_s = _mean(speeds)
            fv.mouse_speed_std_px_s  = _std(speeds)
            fv.mouse_total_distance_px = sum(
                math.hypot(m.dx, m.dy) for m in moves
            )
            fv.mouse_trajectory_smoothness = _trajectory_smoothness(moves)

        fv.mouse_click_rate_per_min  = len(clicks)  / dur_min if dur_min else 0
        fv.mouse_scroll_rate_per_min = len(scrolls) / dur_min if dur_min else 0

    # ------------------------------------------------------------------
    # App usage
    # ------------------------------------------------------------------

    def _extract_app_usage(
        self,
        events: List[BehaviouralEvent],
        fv: FeatureVector,
        dur_min: float,
    ) -> None:
        focus_events = [
            e for e in events
            if isinstance(e, AppFocusEvent) and e.gained_focus
        ]
        app_lifecycle = [
            e for e in events if isinstance(e, AppLifecycleEvent)
        ]

        apps = {e.app_name for e in focus_events if e.app_name}
        fv.app_unique_count = len(apps)
        fv.app_switch_rate_per_min = len(focus_events) / dur_min if dur_min else 0

        # Session durations from lifecycle events
        durations = [
            e.duration_s for e in app_lifecycle
            if e.duration_s is not None
        ]
        fv.app_session_duration_mean_s = _mean(durations)

        # Multitasking index: app switches per unique app (normalised)
        if fv.app_unique_count > 1:
            fv.multitasking_index = min(
                1.0, fv.app_switch_rate_per_min / fv.app_unique_count
            )

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def _extract_workflow(
        self,
        events: List[BehaviouralEvent],
        fv: FeatureVector,
        dur_min: float,
    ) -> None:
        clipboard = [e for e in events if isinstance(e, ClipboardEvent)]
        copies  = [e for e in clipboard if e.action.value == "copy"]
        pastes  = [e for e in clipboard if e.action.value == "paste"]

        fv.clipboard_copy_rate_per_min  = len(copies)  / dur_min if dur_min else 0
        fv.clipboard_paste_rate_per_min = len(pastes)  / dur_min if dur_min else 0

        # Focus durations
        focus_events = [
            e for e in events
            if isinstance(e, AppFocusEvent) and e.gained_focus
        ]
        if len(focus_events) >= 2:
            intervals = [
                focus_events[i+1].timestamp - focus_events[i].timestamp
                for i in range(len(focus_events) - 1)
            ]
            fv.focus_duration_mean_s = _mean(intervals)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mean(values: List[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _std(values: List[float]) -> float:
    return statistics.stdev(values) if len(values) >= 2 else 0.0


def _trajectory_smoothness(moves: List[MouseMoveEvent]) -> float:
    """Compute trajectory smoothness: ratio of straight-line to arc length."""
    if len(moves) < 2:
        return 1.0
    total_arc = sum(math.hypot(m.dx, m.dy) for m in moves)
    if total_arc == 0:
        return 1.0
    straight_line = math.hypot(
        moves[-1].x - moves[0].x,
        moves[-1].y - moves[0].y,
    )
    return min(1.0, straight_line / total_arc)
