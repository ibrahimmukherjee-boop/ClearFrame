"""sandbox/tests/test_behavioural.py — Test suite for the behavioural fine-tuning layer.

Runs with:  python -m pytest sandbox/tests/test_behavioural.py -v
No external dependencies beyond stdlib + the sandbox package itself.
"""

from __future__ import annotations

import json
import math
import sys
import os
import unittest

# Allow running from repo root without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sandbox.behavioural.events import (
    AppLifecycleEvent,
    BehaviouralEvent,
    CognitiveLabel,
    EventType,
    FineTuneExample,
    KeystrokeEvent,
    MouseEvent,
    SessionRecording,
)
from sandbox.behavioural.collector import BehaviouralCollector
from sandbox.behavioural.finetune_layer import (
    BehaviouralFeatures,
    FineTuneLayer,
    _mean,
    _std,
)
from sandbox.behavioural.synthetic_bridge import (
    DatasetCard,
    SyntheticBridge,
    quick_build,
)


# ===========================================================================
# Helper factories
# ===========================================================================

def _make_collector(operator_id: str = "test-op") -> BehaviouralCollector:
    return BehaviouralCollector(operator_id=operator_id)


def _make_recording(
    n_keys: int = 20,
    n_mouse: int = 10,
    n_apps: int = 3,
    task: str = "generic_task",
    profile: CognitiveLabel = CognitiveLabel.FOCUSED,
) -> SessionRecording:
    c = _make_collector()
    return c.simulate_session(
        task_label=task,
        n_keystrokes=n_keys,
        n_mouse_events=n_mouse,
        n_app_events=n_apps,
        cognitive_profile=profile,
    )


# ===========================================================================
# Test: events module
# ===========================================================================

class TestEvents(unittest.TestCase):

    def test_keystroke_event_to_dict(self):
        ev = KeystrokeEvent(
            key_code="a",
            dwell_time_ms=80.0,
            flight_time_ms=110.0,
            is_backspace=False,
        )
        d = ev.to_dict()
        self.assertEqual(d["key_code"], "a")
        self.assertEqual(d["event_type"], EventType.KEYSTROKE.value)
        self.assertAlmostEqual(d["dwell_time_ms"], 80.0)

    def test_mouse_event_to_dict(self):
        ev = MouseEvent(
            event_type=EventType.MOUSE_CLICK,
            x=100.0, y=200.0,
            click_button="left",
            double_click=True,
        )
        d = ev.to_dict()
        self.assertEqual(d["event_type"], "mouse_click")
        self.assertTrue(d["double_click"])

    def test_app_lifecycle_event_to_dict(self):
        ev = AppLifecycleEvent(
            event_type=EventType.APP_SWITCH,
            app_name="VSCode",
            previous_app="Chrome",
        )
        d = ev.to_dict()
        self.assertEqual(d["app_name"], "VSCode")
        self.assertEqual(d["previous_app"], "Chrome")

    def test_session_recording_filters(self):
        rec = SessionRecording()
        rec.events.append(KeystrokeEvent())
        rec.events.append(MouseEvent())
        rec.events.append(AppLifecycleEvent())
        self.assertEqual(len(rec.keystroke_events), 1)
        self.assertEqual(len(rec.mouse_events), 1)
        self.assertEqual(len(rec.app_events), 1)

    def test_finetune_example_jsonl(self):
        ex = FineTuneExample(
            instruction="Do something",
            context="You are an agent",
            response="I will act",
            task_type="generic_task",
            cognitive_label="focused",
            quality_score=0.9,
            tags=["test"],
        )
        row = ex.to_jsonl()
        self.assertIn("messages", row)
        self.assertEqual(len(row["messages"]), 3)
        self.assertEqual(row["messages"][0]["role"], "system")
        self.assertEqual(row["messages"][1]["role"], "user")
        self.assertEqual(row["messages"][2]["role"], "assistant")
        self.assertIn("metadata", row)
        self.assertAlmostEqual(row["metadata"]["quality_score"], 0.9)


# ===========================================================================
# Test: collector
# ===========================================================================

class TestBehaviouralCollector(unittest.TestCase):

    def test_start_end_session(self):
        c = _make_collector()
        sid = c.start_session(task_label="test")
        self.assertTrue(sid.startswith("bhv-"))
        self.assertTrue(c.is_recording)
        rec = c.end_session()
        self.assertFalse(c.is_recording)
        self.assertIsInstance(rec, SessionRecording)
        self.assertGreater(rec.ended_at, 0)

    def test_record_keystroke(self):
        c = _make_collector()
        c.start_session()
        c.record_keystroke("a", dwell_ms=80, flight_ms=120)
        c.record_keystroke("Backspace", dwell_ms=60, flight_ms=90, is_backspace=True)
        rec = c.end_session()
        self.assertEqual(len(rec.keystroke_events), 2)
        self.assertTrue(rec.keystroke_events[1].is_backspace)

    def test_record_mouse(self):
        c = _make_collector()
        c.start_session()
        c.record_mouse_move(100, 200, velocity=1.0)
        c.record_mouse_click(150, 250, button="left")
        c.record_scroll(100, 200, delta=-3)
        rec = c.end_session()
        self.assertEqual(rec.mouse_events[0].event_type, EventType.MOUSE_MOVE)
        self.assertEqual(rec.mouse_events[1].event_type, EventType.MOUSE_CLICK)
        self.assertEqual(rec.mouse_events[2].event_type, EventType.MOUSE_SCROLL)

    def test_record_app_events(self):
        c = _make_collector()
        c.start_session()
        c.record_app_open("VSCode")
        c.record_app_switch("Chrome", previous_app="VSCode")
        c.record_tab_open("https://github.com")
        c.record_app_close("Chrome", duration_ms=5000)
        rec = c.end_session()
        types = [e.event_type for e in rec.app_events]
        self.assertIn(EventType.APP_OPEN, types)
        self.assertIn(EventType.APP_SWITCH, types)
        self.assertIn(EventType.TAB_OPEN, types)
        self.assertIn(EventType.APP_CLOSE, types)

    def test_error_without_session(self):
        c = _make_collector()
        with self.assertRaises(RuntimeError):
            c.record_keystroke("a", dwell_ms=80)

    def test_simulate_session_produces_events(self):
        c = _make_collector()
        rec = c.simulate_session(
            task_label="research",
            n_keystrokes=50,
            n_mouse_events=30,
            n_app_events=4,
            cognitive_profile=CognitiveLabel.EXPLORING,
        )
        self.assertEqual(rec.task_label, "research")
        self.assertGreater(len(rec.keystroke_events), 0)
        self.assertGreater(len(rec.mouse_events), 0)
        self.assertGreater(len(rec.app_events), 0)

    def test_cognitive_labels(self):
        """Each profile should produce a recognisable inferred label."""
        # Stressed profile should not produce FOCUSED label
        c = _make_collector()
        rec = c.simulate_session(
            task_label="data_entry",
            n_keystrokes=80,
            n_mouse_events=20,
            n_app_events=1,
            cognitive_profile=CognitiveLabel.STRESSED,
        )
        # Stressed sessions have high backspace rate → should not be FOCUSED
        self.assertIsInstance(rec.cognitive_label, CognitiveLabel)


# ===========================================================================
# Test: finetune layer
# ===========================================================================

class TestFineTuneLayer(unittest.TestCase):

    def setUp(self):
        self.layer = FineTuneLayer(quality_threshold=0.0)  # accept all

    def test_extract_features_basic(self):
        rec = _make_recording(n_keys=30, n_mouse=15, n_apps=3)
        feat = self.layer.extract_features(rec)
        self.assertIsInstance(feat, BehaviouralFeatures)
        self.assertEqual(feat.n_keystrokes, 30)
        self.assertGreater(feat.avg_dwell_ms, 0)
        self.assertGreater(feat.avg_flight_ms, 0)
        self.assertGreaterEqual(feat.backspace_rate, 0)
        self.assertLessEqual(feat.backspace_rate, 1)

    def test_extract_features_scores_in_range(self):
        rec = _make_recording(n_keys=50, n_mouse=30, n_apps=5)
        feat = self.layer.extract_features(rec)
        self.assertGreaterEqual(feat.focus_score, 0.0)
        self.assertLessEqual(feat.focus_score, 1.0)
        self.assertGreaterEqual(feat.stress_score, 0.0)
        self.assertLessEqual(feat.stress_score, 1.0)
        self.assertGreaterEqual(feat.exploration_score, 0.0)
        self.assertLessEqual(feat.exploration_score, 1.0)

    def test_generate_examples_not_empty(self):
        rec = _make_recording(task="research", n_keys=40, n_mouse=20, n_apps=3)
        examples = self.layer.process(rec)
        self.assertGreater(len(examples), 0)

    def test_examples_have_required_fields(self):
        rec = _make_recording(task="write_code", n_keys=50, n_mouse=20, n_apps=2)
        examples = self.layer.process(rec)
        for ex in examples:
            self.assertIsInstance(ex, FineTuneExample)
            self.assertTrue(ex.instruction)
            self.assertTrue(ex.context)
            self.assertTrue(ex.response)
            self.assertEqual(ex.task_type, "write_code")
            self.assertGreater(ex.quality_score, 0)

    def test_jsonl_serialisation(self):
        rec = _make_recording(task="data_entry", n_keys=30, n_mouse=15, n_apps=2)
        examples = self.layer.process(rec)
        for ex in examples:
            row = ex.to_jsonl()
            # Ensure it roundtrips through JSON
            serialised = json.dumps(row)
            parsed = json.loads(serialised)
            self.assertEqual(len(parsed["messages"]), 3)

    def test_quality_threshold_filters(self):
        strict_layer = FineTuneLayer(quality_threshold=0.99)
        rec = _make_recording(n_keys=5, n_mouse=2, n_apps=0)  # very sparse
        examples = strict_layer.process(rec)
        # Sparse session should be filtered
        for ex in examples:
            self.assertGreaterEqual(ex.quality_score, 0.99)

    def test_all_task_types_produce_examples(self):
        for task in ["research", "write_code", "data_entry", "generic_task"]:
            rec = _make_recording(task=task, n_keys=40, n_mouse=20, n_apps=3)
            examples = self.layer.process(rec)
            self.assertGreater(len(examples), 0, f"No examples for task: {task}")

    def test_process_batch(self):
        recs = [_make_recording(n_keys=30, n_mouse=15, n_apps=2) for _ in range(3)]
        all_examples = self.layer.process_batch(recs)
        self.assertGreater(len(all_examples), 0)

    def test_feature_to_prompt_text(self):
        rec = _make_recording()
        feat = self.layer.extract_features(rec)
        prompt = feat.to_prompt_text()
        self.assertIn("Operator behavioural context", prompt)
        self.assertIn("Cognitive state", prompt)
        self.assertIn("Focus score", prompt)


# ===========================================================================
# Test: statistical helpers
# ===========================================================================

class TestStatHelpers(unittest.TestCase):

    def test_mean_empty(self):
        self.assertEqual(_mean([]), 0.0)

    def test_mean_values(self):
        self.assertAlmostEqual(_mean([1.0, 2.0, 3.0]), 2.0)

    def test_std_single(self):
        self.assertEqual(_std([5.0]), 0.0)

    def test_std_values(self):
        result = _std([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        self.assertAlmostEqual(result, 2.0, places=1)


# ===========================================================================
# Test: synthetic bridge
# ===========================================================================

class TestSyntheticBridge(unittest.TestCase):

    def setUp(self):
        self.bridge = SyntheticBridge(quality_threshold=0.0, random_seed=42)

    def test_build_dataset_synthetic_only(self):
        examples = self.bridge.build_dataset(
            n_synthetic_sessions=5,
            n_augmented_per_real=0,
        )
        self.assertGreater(len(examples), 0)
        for ex in examples:
            self.assertIn("source:synthetic", ex.tags)

    def test_build_dataset_with_real_recordings(self):
        real_rec = _make_recording(n_keys=50, n_mouse=25, n_apps=4)
        examples = self.bridge.build_dataset(
            real_recordings=[real_rec],
            n_synthetic_sessions=3,
            n_augmented_per_real=2,
        )
        sources = set()
        for ex in examples:
            for tag in ex.tags:
                if tag.startswith("source:"):
                    sources.add(tag)
        self.assertIn("source:real", sources)
        self.assertIn("source:augmented", sources)
        self.assertIn("source:synthetic", sources)

    def test_to_jsonl_valid(self):
        examples = self.bridge.build_dataset(n_synthetic_sessions=3)
        jsonl_str = SyntheticBridge.to_jsonl(examples)
        for line in jsonl_str.strip().split("\n"):
            parsed = json.loads(line)
            self.assertIn("messages", parsed)
            self.assertIn("metadata", parsed)

    def test_to_jsonl_rows(self):
        examples = self.bridge.build_dataset(n_synthetic_sessions=3)
        rows = SyntheticBridge.to_jsonl_rows(examples)
        self.assertEqual(len(rows), len(examples))
        for row in rows:
            self.assertIn("messages", row)

    def test_dataset_card(self):
        examples = self.bridge.build_dataset(n_synthetic_sessions=5)
        card = self.bridge.dataset_card(examples)
        self.assertIsInstance(card, DatasetCard)
        self.assertEqual(card.total_examples, len(examples))
        self.assertGreater(card.avg_quality_score, 0)
        self.assertGreater(len(card.task_distribution), 0)
        self.assertGreater(len(card.cognitive_distribution), 0)

    def test_dataset_card_to_markdown(self):
        examples = self.bridge.build_dataset(n_synthetic_sessions=5)
        card = self.bridge.dataset_card(examples)
        md = card.to_markdown()
        self.assertIn("Behavioural Fine-Tune Dataset Card", md)
        self.assertIn("Task Distribution", md)
        self.assertIn("Cognitive State Distribution", md)

    def test_quick_build(self):
        examples, card = quick_build(n_synthetic=5, random_seed=0)
        self.assertGreater(len(examples), 0)
        self.assertIsInstance(card, DatasetCard)

    def test_augmentation_changes_events(self):
        real_rec = _make_recording(n_keys=40, n_mouse=20, n_apps=3)
        augmented = self.bridge._augment_recording(real_rec)
        self.assertNotEqual(augmented.recording_id, real_rec.recording_id)
        self.assertTrue(augmented.recording_id.startswith("aug-"))

    def test_task_distribution_respected(self):
        # Force all synthetic to write_code
        examples = self.bridge.build_dataset(
            n_synthetic_sessions=10,
            task_distribution={"write_code": 1.0},
        )
        for ex in examples:
            self.assertEqual(ex.task_type, "write_code")


# ===========================================================================
# Test: end-to-end pipeline
# ===========================================================================

class TestEndToEndPipeline(unittest.TestCase):

    def test_full_pipeline(self):
        """Simulate operator → collect → fine-tune → export."""
        # Step 1: Collect a session
        collector = BehaviouralCollector(operator_id="op-e2e")
        collector.start_session(task_label="research")
        for i in range(30):
            collector.record_keystroke(
                key_code=chr(97 + (i % 26)),
                dwell_ms=75 + i % 20,
                flight_ms=110 + i % 40,
            )
        for _ in range(15):
            collector.record_mouse_move(400 + _, 300 + _, velocity=1.1)
        collector.record_app_open("Chrome")
        collector.record_tab_open("https://arxiv.org")
        collector.record_app_switch("VSCode", previous_app="Chrome")
        recording = collector.end_session()

        # Step 2: Extract features
        layer = FineTuneLayer(quality_threshold=0.0)
        features = layer.extract_features(recording)
        self.assertGreater(features.n_keystrokes, 0)
        self.assertGreater(features.n_mouse_events, 0)

        # Step 3: Generate examples
        examples = layer.process(recording)
        self.assertGreater(len(examples), 0)

        # Step 4: Export via bridge
        bridge = SyntheticBridge(quality_threshold=0.0)
        jsonl = SyntheticBridge.to_jsonl(examples)
        lines = jsonl.strip().split("\n")
        self.assertEqual(len(lines), len(examples))
        for line in lines:
            parsed = json.loads(line)
            self.assertEqual(len(parsed["messages"]), 3)

    def test_bulk_synthetic_pipeline(self):
        """Build 20 synthetic sessions, verify dataset card."""
        examples, card = quick_build(n_synthetic=20, random_seed=99)
        self.assertGreater(len(examples), 0)
        self.assertEqual(card.total_examples, len(examples))
        self.assertGreaterEqual(card.avg_quality_score, 0.0)
        self.assertLessEqual(card.avg_quality_score, 1.0)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
