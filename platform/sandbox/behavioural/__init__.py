"""sandbox/behavioural/__init__.py — Human Behavioural Fine-Tuning Layer.

Captures typing patterns, mouse dynamics, and app lifecycle events from
human operators and converts them into structured fine-tuning signals
for autonomous AI agents.
"""

from sandbox.behavioural.events import (
    BehaviouralEvent,
    KeystrokeEvent,
    MouseEvent,
    AppLifecycleEvent,
    SessionRecording,
    FineTuneExample,
)
from sandbox.behavioural.collector import BehaviouralCollector
from sandbox.behavioural.finetune_layer import FineTuneLayer
from sandbox.behavioural.synthetic_bridge import SyntheticBridge

__all__ = [
    "BehaviouralEvent",
    "KeystrokeEvent",
    "MouseEvent",
    "AppLifecycleEvent",
    "SessionRecording",
    "FineTuneExample",
    "BehaviouralCollector",
    "FineTuneLayer",
    "SyntheticBridge",
]
