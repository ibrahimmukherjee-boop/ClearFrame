"""sandbox package — Erasys AI Governance and Safety PoC modules.

Modules
-------
state           : Shared in-memory state (SandboxState, AgentConfig, …)
agent_builder   : Agent configuration UI (Gradio tab)
overview        : Sandbox overview tab
safepulse       : Behavioural authentication module (typing + mouse patterns)
trust_registry  : Agent trust certificate registry
clearframe_live : ClearFrame runtime governance tab
behavioural     : Human behavioural fine-tuning layer for AI agents
                  ├─ events.py          : Event data models
                  ├─ collector.py       : Event collector + simulator
                  ├─ finetune_layer.py  : Behavioural → FineTuneExample pipeline
                  └─ synthetic_bridge.py: Dataset builder + JSONL export
"""

# Expose behavioural fine-tuning layer at top level for convenience
from sandbox.behavioural.synthetic_bridge import quick_build as behavioural_quick_build
from sandbox.behavioural.collector import BehaviouralCollector
from sandbox.behavioural.finetune_layer import FineTuneLayer

__all__ = [
    "BehaviouralCollector",
    "FineTuneLayer",
    "behavioural_quick_build",
]
