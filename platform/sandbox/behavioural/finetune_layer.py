"""sandbox/behavioural/finetune_layer.py — FineTuneLayer.

Transforms SessionRecording objects into FineTuneExample training triples
that can be used to fine-tune autonomous AI agents.

Core idea
---------
Human operators using an app naturally demonstrate:
  1. WHAT to do next (tool selection, navigation intent)
  2. HOW to do it (speed, precision, confidence)
  3. WHEN to pause, reconsider, or backtrack

The FineTuneLayer extracts these signals from raw behavioural data and
formats them as (system_context, instruction, response) triples, which
are the standard input format for LLM supervised fine-tuning.

Pipeline
--------
  SessionRecording
       ↓  extract_features()
  BehaviouralFeatures  (statistical summary)
       ↓  build_context_prompt()
  system context string
       ↓  generate_examples()
  List[FineTuneExample]  ←― ready for JSONL export
"""

from __future__ import annotations

import math
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sandbox.behavioural.events import (
    AppLifecycleEvent,
    CognitiveLabel,
    EventType,
    FineTuneExample,
    KeystrokeEvent,
    MouseEvent,
    SessionRecording,
)


# ---------------------------------------------------------------------------
# Behavioural feature vector
# ---------------------------------------------------------------------------

@dataclass
class BehaviouralFeatures:
    """Compact statistical summary of a SessionRecording.

    Used as the numerical/textual context injected into fine-tune prompts.
    """
    # Keystroke features
    n_keystrokes: int = 0
    avg_dwell_ms: float = 0.0
    std_dwell_ms: float = 0.0
    avg_flight_ms: float = 0.0
    std_flight_ms: float = 0.0
    backspace_rate: float = 0.0
    typing_speed_wpm: float = 0.0     # estimated words-per-minute

    # Mouse features
    n_mouse_events: int = 0
    n_clicks: int = 0
    n_scrolls: int = 0
    avg_velocity: float = 0.0
    std_velocity: float = 0.0
    double_click_rate: float = 0.0

    # App lifecycle features
    n_app_events: int = 0
    n_app_switches: int = 0
    n_tab_opens: int = 0
    unique_apps: int = 0
    unique_urls: int = 0

    # Session-level features
    duration_s: float = 0.0
    cognitive_label: str = ""
    task_label: str = ""

    # Derived signals
    focus_score: float = 0.0     # 0.0 – 1.0  (higher = more focused)
    stress_score: float = 0.0    # 0.0 – 1.0  (higher = more stressed)
    exploration_score: float = 0.0  # 0.0 – 1.0

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()

    def to_prompt_text(self) -> str:
        """Render features as a human-readable context block for prompts."""
        return (
            f"Operator behavioural context:\n"
            f"  Task: {self.task_label or 'unspecified'}\n"
            f"  Cognitive state: {self.cognitive_label}\n"
            f"  Duration: {self.duration_s:.1f}s\n"
            f"  Typing speed: {self.typing_speed_wpm:.0f} WPM  "
            f"(avg dwell {self.avg_dwell_ms:.0f}ms, avg flight {self.avg_flight_ms:.0f}ms)\n"
            f"  Backspace rate: {self.backspace_rate:.1%}\n"
            f"  Mouse: {self.n_clicks} clicks, {self.n_scrolls} scrolls, "
            f"avg velocity {self.avg_velocity:.2f} px/ms\n"
            f"  App switches: {self.n_app_switches}  |  Tabs opened: {self.n_tab_opens}\n"
            f"  Focus score: {self.focus_score:.2f}  "
            f"Stress score: {self.stress_score:.2f}  "
            f"Exploration score: {self.exploration_score:.2f}"
        )


# ---------------------------------------------------------------------------
# Fine-tune layer
# ---------------------------------------------------------------------------

class FineTuneLayer:
    """Converts SessionRecordings into structured fine-tuning examples.

    Usage::

        layer = FineTuneLayer()
        recording = collector.simulate_session(task_label="research")
        examples = layer.process(recording)
        jsonl_rows = [ex.to_jsonl() for ex in examples]
    """

    # Task-type templates: maps task labels to instruction/response patterns.
    # In production these would be learned from operator annotations.
    TASK_TEMPLATES: Dict[str, List[Dict[str, str]]] = {
        "research": [
            {
                "instruction": "Identify the most relevant next search query for the current task.",
                "response_template": "Based on the operator's {cognitive_label} state and "
                                     "{n_tab_opens} tabs opened, the next query should focus "
                                     "on refining the current hypothesis rather than broadening scope.",
            },
            {
                "instruction": "Decide whether to open a new tab or continue on the current page.",
                "response_template": "With {n_app_switches} context switches detected and an "
                                     "exploration score of {exploration_score:.2f}, the agent should "
                                     "consolidate findings on the current page before switching.",
            },
        ],
        "write_code": [
            {
                "instruction": "Determine whether to proceed with the current implementation or pause and refactor.",
                "response_template": "Backspace rate of {backspace_rate:.1%} and dwell std "
                                     "{std_dwell_ms:.0f}ms suggest the operator is {'reconsidering approach' if backspace_rate > 0.1 else 'confident in direction'}. "
                                     "Agent should {'pause and review' if backspace_rate > 0.1 else 'continue implementation'}.",
            },
            {
                "instruction": "Select the most appropriate next tool call to assist the operator.",
                "response_template": "Given typing speed {typing_speed_wpm:.0f} WPM and cognitive label "
                                     "{cognitive_label}, suggest a code completion call to reduce "
                                     "repetitive typing burden.",
            },
        ],
        "data_entry": [
            {
                "instruction": "Assess whether the operator needs autocomplete assistance.",
                "response_template": "Typing speed {typing_speed_wpm:.0f} WPM with "
                                     "{backspace_rate:.1%} error rate: "
                                     "{'high error rate detected, trigger autocomplete' if backspace_rate > 0.12 else 'operator performing well, no intervention needed'}.",
            },
        ],
        "generic_task": [
            {
                "instruction": "Summarise the operator's current work context to inform the next agent action.",
                "response_template": "Operator is in a {cognitive_label} state. "
                                     "Session duration: {duration_s:.0f}s. "
                                     "Focus score: {focus_score:.2f}. "
                                     "Recommended agent posture: {'active assistance' if focus_score < 0.5 else 'background monitoring'}.",
            },
        ],
    }

    def __init__(self, quality_threshold: float = 0.5) -> None:
        """Initialise the layer.

        Args:
            quality_threshold: Minimum quality score (0–1) for an example to
                               be included in the output dataset.
        """
        self.quality_threshold = quality_threshold

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process(self, recording: SessionRecording) -> List[FineTuneExample]:
        """Full pipeline: recording → features → examples."""
        features = self.extract_features(recording)
        examples = self.generate_examples(features, recording.recording_id)
        return [e for e in examples if e.quality_score >= self.quality_threshold]

    def process_batch(
        self, recordings: List[SessionRecording]
    ) -> List[FineTuneExample]:
        """Process multiple recordings and return a flat list."""
        out: List[FineTuneExample] = []
        for rec in recordings:
            out.extend(self.process(rec))
        return out

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def extract_features(self, recording: SessionRecording) -> BehaviouralFeatures:
        """Compute the statistical feature vector from a SessionRecording."""
        keys: List[KeystrokeEvent] = recording.keystroke_events
        mouse: List[MouseEvent] = recording.mouse_events
        apps: List[AppLifecycleEvent] = recording.app_events

        feat = BehaviouralFeatures(
            duration_s=recording.duration_s,
            cognitive_label=recording.cognitive_label.value,
            task_label=recording.task_label,
        )

        # --- Keystroke features ---
        if keys:
            feat.n_keystrokes = len(keys)
            dwells = [k.dwell_time_ms for k in keys]
            flights = [k.flight_time_ms for k in keys]
            feat.avg_dwell_ms = _mean(dwells)
            feat.std_dwell_ms = _std(dwells)
            feat.avg_flight_ms = _mean(flights)
            feat.std_flight_ms = _std(flights)
            feat.backspace_rate = (
                sum(1 for k in keys if k.is_backspace) / len(keys)
            )
            # Rough WPM: avg chars per second / 5 chars per word * 60
            if feat.avg_flight_ms > 0:
                chars_per_sec = 1000.0 / feat.avg_flight_ms
                feat.typing_speed_wpm = (chars_per_sec / 5.0) * 60.0

        # --- Mouse features ---
        clicks = [e for e in mouse if e.event_type == EventType.MOUSE_CLICK]
        scrolls = [e for e in mouse if e.event_type == EventType.MOUSE_SCROLL]
        moves = [e for e in mouse if e.event_type == EventType.MOUSE_MOVE]

        feat.n_mouse_events = len(mouse)
        feat.n_clicks = len(clicks)
        feat.n_scrolls = len(scrolls)
        if clicks:
            feat.double_click_rate = (
                sum(1 for c in clicks if c.double_click) / len(clicks)
            )
        if moves:
            vels = [m.velocity for m in moves]
            feat.avg_velocity = _mean(vels)
            feat.std_velocity = _std(vels)

        # --- App lifecycle features ---
        feat.n_app_events = len(apps)
        feat.n_app_switches = sum(
            1 for a in apps if a.event_type == EventType.APP_SWITCH
        )
        feat.n_tab_opens = sum(
            1 for a in apps if a.event_type == EventType.TAB_OPEN
        )
        feat.unique_apps = len({a.app_name for a in apps if a.app_name})
        feat.unique_urls = len({a.url for a in apps if a.url})

        # --- Derived scores ---
        feat.focus_score = self._compute_focus_score(feat)
        feat.stress_score = self._compute_stress_score(feat)
        feat.exploration_score = self._compute_exploration_score(feat)

        return feat

    # ------------------------------------------------------------------
    # Example generation
    # ------------------------------------------------------------------

    def generate_examples(
        self,
        features: BehaviouralFeatures,
        source_recording_id: str = "",
    ) -> List[FineTuneExample]:
        """Build FineTuneExample triples from a feature vector."""
        task = features.task_label or "generic_task"
        templates = self.TASK_TEMPLATES.get(task, self.TASK_TEMPLATES["generic_task"])
        context = self._build_context_prompt(features)
        examples: List[FineTuneExample] = []

        feat_dict = features.to_dict()

        for tmpl in templates:
            instruction = tmpl["instruction"]
            # Safely render response template with feature values
            try:
                response = tmpl["response_template"].format(**feat_dict)
            except (KeyError, ValueError):
                response = tmpl["response_template"]

            quality = self._compute_quality_score(features)

            example = FineTuneExample(
                source_recording_id=source_recording_id,
                instruction=instruction,
                context=context,
                response=response,
                task_type=task,
                cognitive_label=features.cognitive_label,
                quality_score=quality,
                tags=self._build_tags(features),
            )
            examples.append(example)

        return examples

    # ------------------------------------------------------------------
    # Context prompt builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context_prompt(features: BehaviouralFeatures) -> str:
        return (
            "You are an autonomous AI agent assisting a human operator. "
            "Use the following real-time behavioural context to calibrate "
            "your next action:\n\n"
            + features.to_prompt_text()
            + "\n\nRespond with a specific, actionable agent decision."
        )

    # ------------------------------------------------------------------
    # Score helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_focus_score(f: BehaviouralFeatures) -> float:
        """Higher when operator is calm and deliberate."""
        score = 1.0
        # High variance in keystrokes → lower focus
        if f.avg_dwell_ms > 0:
            cv = f.std_dwell_ms / max(f.avg_dwell_ms, 1.0)
            score -= min(0.4, cv * 0.4)
        # High backspace rate → lower focus
        score -= min(0.3, f.backspace_rate * 2)
        # Many app switches → lower focus
        score -= min(0.2, f.n_app_switches * 0.05)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _compute_stress_score(f: BehaviouralFeatures) -> float:
        """Higher when operator shows stress signals."""
        score = 0.0
        score += min(0.5, f.backspace_rate * 2.5)
        if f.avg_dwell_ms > 0:
            cv = f.std_dwell_ms / max(f.avg_dwell_ms, 1.0)
            score += min(0.3, cv * 0.3)
        score += min(0.2, f.avg_velocity * 0.05)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _compute_exploration_score(f: BehaviouralFeatures) -> float:
        """Higher when operator is navigating widely."""
        score = 0.0
        score += min(0.4, f.n_app_switches * 0.08)
        score += min(0.3, f.n_tab_opens * 0.06)
        score += min(0.3, f.unique_urls * 0.05)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _compute_quality_score(f: BehaviouralFeatures) -> float:
        """Estimate data quality: higher when session has enough events."""
        score = 1.0
        # Penalise very short sessions
        if f.duration_s < 10:
            score *= 0.5
        # Penalise sparse sessions
        if f.n_keystrokes < 10:
            score *= 0.7
        if f.n_mouse_events < 5:
            score *= 0.8
        return max(0.0, min(1.0, score))

    @staticmethod
    def _build_tags(f: BehaviouralFeatures) -> List[str]:
        tags = [f"cognitive:{f.cognitive_label}", f"task:{f.task_label or 'unknown'}"]
        if f.stress_score > 0.6:
            tags.append("high_stress")
        if f.exploration_score > 0.5:
            tags.append("exploration_mode")
        if f.focus_score > 0.7:
            tags.append("high_focus")
        if f.backspace_rate > 0.15:
            tags.append("high_error_rate")
        return tags


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance)
