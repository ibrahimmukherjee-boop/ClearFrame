"""clearframe/clearframe/behavioural/__init__.py

Behavioural biometrics sub-package.

Exposes the public API for event capture, feature extraction,
and session collection used by the ClearFrame pipeline.
"""

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
from .collector import BehaviouralCollector
from .features import FeatureExtractor, FeatureVector

__all__ = [
    # Events
    "AppFocusEvent",
    "AppLifecycleAction",
    "AppLifecycleEvent",
    "BehaviouralEvent",
    "ClipboardAction",
    "ClipboardEvent",
    "EventKind",
    "KeyEvent",
    "MouseClickEvent",
    "MouseMoveEvent",
    "MouseScrollEvent",
    "SessionAction",
    "SessionEvent",
    "TextEditEvent",
    # Collector
    "BehaviouralCollector",
    # Features
    "FeatureExtractor",
    "FeatureVector",
]
