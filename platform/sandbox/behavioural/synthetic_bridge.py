"""sandbox/behavioural/synthetic_bridge.py — SyntheticBridge.

Bridges the behavioural fine-tuning layer with the broader synthetic data
pipeline already present in the sandbox.

Responsibilities
----------------
1. AUGMENT  : Take real SessionRecordings and augment them with synthetic
              variations (noise injection, profile mixing) to increase
              dataset diversity.

2. BLEND    : Merge behaviourally-grounded FineTuneExamples with any
              existing synthetic JSONL data to produce a unified training
              dataset.

3. EXPORT   : Serialise the final dataset to JSONL format compatible with
              OpenAI fine-tune API, HuggingFace TRL, Axolotl, and
              LLaMA-Factory.

4. REPORT   : Generate a markdown dataset card summarising statistics.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sandbox.behavioural.collector import BehaviouralCollector
from sandbox.behavioural.events import (
    CognitiveLabel,
    FineTuneExample,
    SessionRecording,
)
from sandbox.behavioural.finetune_layer import BehaviouralFeatures, FineTuneLayer


# ---------------------------------------------------------------------------
# Dataset card
# ---------------------------------------------------------------------------

@dataclass
class DatasetCard:
    """Summary statistics for the generated training dataset."""
    total_examples: int = 0
    real_examples: int = 0
    synthetic_examples: int = 0
    augmented_examples: int = 0
    task_distribution: Dict[str, int] = field(default_factory=dict)
    cognitive_distribution: Dict[str, int] = field(default_factory=dict)
    avg_quality_score: float = 0.0
    filtered_count: int = 0
    generated_at: str = ""

    def to_markdown(self) -> str:
        task_rows = "\n".join(
            f"| {t} | {c} |" for t, c in sorted(self.task_distribution.items())
        )
        cog_rows = "\n".join(
            f"| {l} | {c} |" for l, c in sorted(self.cognitive_distribution.items())
        )
        return f"""# Behavioural Fine-Tune Dataset Card

Generated: {self.generated_at}

## Summary

| Metric | Value |
|--------|-------|
| Total examples | {self.total_examples} |
| Real (from operator sessions) | {self.real_examples} |
| Synthetic (simulated) | {self.synthetic_examples} |
| Augmented (real + noise) | {self.augmented_examples} |
| Filtered out (low quality) | {self.filtered_count} |
| Avg quality score | {self.avg_quality_score:.2f} |

## Task Distribution

| Task | Count |
|------|-------|
{task_rows}

## Cognitive State Distribution

| Cognitive Label | Count |
|-----------------|-------|
{cog_rows}

## Format

Each row is a JSONL object with:
- `messages`: [{{'role': 'system', 'content': <behavioural_context>}},
               {{'role': 'user',   'content': <instruction>}},
               {{'role': 'assistant', 'content': <agent_response>}}]
- `metadata`: {{example_id, source_recording_id, task_type,
               cognitive_label, quality_score, tags}}

Compatible with: OpenAI fine-tuning API, HuggingFace TRL SFTTrainer,
Axolotl, LLaMA-Factory.
"""


# ---------------------------------------------------------------------------
# Synthetic bridge
# ---------------------------------------------------------------------------

class SyntheticBridge:
    """Bridges behavioural recordings with the synthetic data pipeline.

    Usage::

        bridge = SyntheticBridge()

        # Generate a mixed dataset of real + synthetic + augmented examples
        dataset = bridge.build_dataset(
            real_recordings=[my_recording],
            n_synthetic_sessions=20,
            n_augmented_per_real=3,
        )

        # Export
        jsonl = bridge.to_jsonl(dataset)
        card = bridge.dataset_card(dataset)
        print(card.to_markdown())
    """

    COGNITIVE_PROFILES = list(CognitiveLabel)
    TASK_LABELS = ["research", "write_code", "data_entry", "generic_task"]

    def __init__(
        self,
        quality_threshold: float = 0.5,
        random_seed: Optional[int] = None,
    ) -> None:
        self.quality_threshold = quality_threshold
        self.layer = FineTuneLayer(quality_threshold=quality_threshold)
        if random_seed is not None:
            random.seed(random_seed)

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def build_dataset(
        self,
        real_recordings: Optional[List[SessionRecording]] = None,
        n_synthetic_sessions: int = 10,
        n_augmented_per_real: int = 2,
        task_distribution: Optional[Dict[str, float]] = None,
    ) -> List[FineTuneExample]:
        """Build a mixed fine-tuning dataset.

        Args:
            real_recordings:        Optional list of real operator recordings.
            n_synthetic_sessions:   Number of fully synthetic sessions to generate.
            n_augmented_per_real:   For each real recording, how many augmented
                                    variants to produce.
            task_distribution:      Dict mapping task_label -> probability weight.
                                    Defaults to uniform over TASK_LABELS.
        """
        all_examples: List[FineTuneExample] = []

        # 1. Process real recordings
        if real_recordings:
            for rec in real_recordings:
                examples = self.layer.process(rec)
                for ex in examples:
                    ex.tags.append("source:real")
                all_examples.extend(examples)

                # Augmented variants
                for _ in range(n_augmented_per_real):
                    augmented = self._augment_recording(rec)
                    aug_examples = self.layer.process(augmented)
                    for ex in aug_examples:
                        ex.tags.append("source:augmented")
                    all_examples.extend(aug_examples)

        # 2. Generate fully synthetic sessions
        dist = task_distribution or {t: 1.0 for t in self.TASK_LABELS}
        for _ in range(n_synthetic_sessions):
            task = self._sample_task(dist)
            profile = random.choice(self.COGNITIVE_PROFILES)
            rec = self._generate_synthetic_session(task, profile)
            examples = self.layer.process(rec)
            for ex in examples:
                ex.tags.append("source:synthetic")
            all_examples.extend(examples)

        return all_examples

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @staticmethod
    def to_jsonl(examples: List[FineTuneExample]) -> str:
        """Serialise examples to a JSONL string."""
        lines = [json.dumps(ex.to_jsonl(), ensure_ascii=False) for ex in examples]
        return "\n".join(lines)

    @staticmethod
    def to_jsonl_rows(examples: List[FineTuneExample]) -> List[Dict[str, Any]]:
        """Return list of dicts (one per example) for programmatic use."""
        return [ex.to_jsonl() for ex in examples]

    def dataset_card(self, examples: List[FineTuneExample]) -> DatasetCard:
        """Build a DatasetCard summarising the dataset."""
        card = DatasetCard(
            total_examples=len(examples),
            generated_at=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        )
        quality_sum = 0.0
        pre_filter_count = 0

        for ex in examples:
            pre_filter_count += 1
            quality_sum += ex.quality_score
            card.task_distribution[ex.task_type] = (
                card.task_distribution.get(ex.task_type, 0) + 1
            )
            card.cognitive_distribution[ex.cognitive_label] = (
                card.cognitive_distribution.get(ex.cognitive_label, 0) + 1
            )
            if "source:real" in ex.tags:
                card.real_examples += 1
            elif "source:augmented" in ex.tags:
                card.augmented_examples += 1
            else:
                card.synthetic_examples += 1

        if pre_filter_count:
            card.avg_quality_score = quality_sum / pre_filter_count

        return card

    # ------------------------------------------------------------------
    # Augmentation
    # ------------------------------------------------------------------

    def _augment_recording(self, recording: SessionRecording) -> SessionRecording:
        """Create a noisy variant of a real recording.

        Techniques:
          - Add Gaussian noise to keystroke timings
          - Randomly drop 10–20% of mouse events
          - Optionally change cognitive label
        """
        from sandbox.behavioural.events import KeystrokeEvent, MouseEvent
        import copy

        aug = copy.deepcopy(recording)
        aug.recording_id = "aug-" + aug.recording_id

        new_events = []
        for ev in aug.events:
            if isinstance(ev, KeystrokeEvent):
                # Add timing noise (5–15% jitter)
                jitter = random.uniform(0.85, 1.15)
                ev.dwell_time_ms *= jitter
                ev.flight_time_ms *= jitter
                new_events.append(ev)
            elif isinstance(ev, MouseEvent):
                # Drop 15% of mouse events randomly
                if random.random() > 0.15:
                    ev.velocity *= random.uniform(0.8, 1.2)
                    new_events.append(ev)
            else:
                new_events.append(ev)

        aug.events = new_events
        # Occasionally flip cognitive label to a neighbour state
        if random.random() < 0.3:
            aug.cognitive_label = random.choice(self.COGNITIVE_PROFILES)

        return aug

    # ------------------------------------------------------------------
    # Synthetic session generation
    # ------------------------------------------------------------------

    def _generate_synthetic_session(
        self,
        task_label: str,
        profile: CognitiveLabel,
    ) -> SessionRecording:
        """Use BehaviouralCollector.simulate_session() to build a synthetic session."""
        collector = BehaviouralCollector(operator_id="synth-" + str(random.randint(1000, 9999)))
        n_keys = random.randint(60, 200)
        n_mouse = random.randint(30, 120)
        n_apps = random.randint(2, 8)
        return collector.simulate_session(
            task_label=task_label,
            n_keystrokes=n_keys,
            n_mouse_events=n_mouse,
            n_app_events=n_apps,
            cognitive_profile=profile,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sample_task(distribution: Dict[str, float]) -> str:
        tasks = list(distribution.keys())
        weights = [distribution[t] for t in tasks]
        total = sum(weights)
        r = random.uniform(0, total)
        cumulative = 0.0
        for t, w in zip(tasks, weights):
            cumulative += w
            if r <= cumulative:
                return t
        return tasks[-1]


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def quick_build(
    n_synthetic: int = 20,
    quality_threshold: float = 0.5,
    random_seed: int = 42,
) -> tuple[List[FineTuneExample], DatasetCard]:
    """One-liner to build a synthetic behavioural fine-tune dataset.

    Returns (examples, card) where examples is a list of FineTuneExample
    and card is a DatasetCard with summary statistics.

    Example::

        examples, card = quick_build(n_synthetic=50)
        print(card.to_markdown())
        jsonl = SyntheticBridge.to_jsonl(examples)
    """
    bridge = SyntheticBridge(
        quality_threshold=quality_threshold,
        random_seed=random_seed,
    )
    examples = bridge.build_dataset(n_synthetic_sessions=n_synthetic)
    card = bridge.dataset_card(examples)
    return examples, card
