"""clearframe/builder/templates.py

Pre-built agent graph templates for ClearFrame.
Each factory function returns a ready-to-use GraphSpec built with
GraphBuilder.  Templates serve as starting points for common
agent architectures and can be further customised by the caller.
"""

from __future__ import annotations

from typing import Optional

from .graph import GraphBuilder, GraphSpec


# ---------------------------------------------------------------------------
# 1. Minimal passthrough graph
# ---------------------------------------------------------------------------

def minimal_graph(
    name: str = "Minimal Graph",
    description: str = "Bare-minimum INPUT → OUTPUT passthrough.",
) -> GraphSpec:
    """Return a minimal two-node graph (INPUT → OUTPUT).

    Useful as a blank-slate template before adding processing nodes.
    """
    return (
        GraphBuilder(name=name, description=description)
        .add_node("input",  "INPUT",  "Input",  position=(100.0, 300.0))
        .add_node("output", "OUTPUT", "Output", position=(700.0, 300.0))
        .connect("input", "data", "output", "data")
        .build()
    )


# ---------------------------------------------------------------------------
# 2. Simple LLM chat agent
# ---------------------------------------------------------------------------

def simple_llm_agent(
    name: str = "Simple LLM Agent",
    model: str = "gpt-4o",
    system_prompt: str = "You are a helpful assistant.",
    description: str = "Single LLM call sandwiched between I/O nodes.",
) -> GraphSpec:
    """Return a three-node graph: INPUT → LLM_CALL → OUTPUT.

    Parameters
    ----------
    name:
        Human-readable graph name.
    model:
        LLM model identifier, e.g. ``"gpt-4o"`` or ``"claude-3-5-sonnet"``.
    system_prompt:
        System-level instruction sent to the model.
    description:
        Graph description string.
    """
    return (
        GraphBuilder(name=name, description=description)
        .add_node("input",  "INPUT",    "Input",   position=(100.0, 300.0))
        .add_node(
            "llm", "LLM_CALL", "LLM Call",
            config={
                "model": model,
                "system_prompt": system_prompt,
                "temperature": 0.7,
                "max_tokens": 2048,
            },
            position=(400.0, 300.0),
        )
        .add_node("output", "OUTPUT",   "Output",  position=(700.0, 300.0))
        .connect("input", "data",     "llm",    "prompt")
        .connect("llm",   "response", "output", "data")
        .build()
    )


# ---------------------------------------------------------------------------
# 3. ReAct-style tool-using agent
# ---------------------------------------------------------------------------

def react_agent(
    name: str = "ReAct Agent",
    model: str = "gpt-4o",
    system_prompt: str = (
        "You are an agent that reasons step-by-step and uses tools to answer questions."
    ),
    description: str = "ReAct loop with tool execution and memory.",
) -> GraphSpec:
    """Return a graph implementing a ReAct-style reasoning loop.

    Architecture
    ------------
    INPUT
      └── LLM_CALL (reason + decide action)
            ├── TOOL_CALL (execute tool)
            │     └── LLM_CALL (observe + next step)  [loop via LOOP node]
            └── OUTPUT (final answer)
    """
    return (
        GraphBuilder(name=name, description=description)
        .add_node("input",   "INPUT",     "Input",         position=(50.0,  300.0))
        .add_node(
            "reason", "LLM_CALL",  "Reason & Plan",
            config={
                "model": model,
                "system_prompt": system_prompt,
                "temperature": 0.2,
                "max_tokens": 1024,
            },
            position=(300.0, 300.0),
        )
        .add_node(
            "tool",   "TOOL_CALL", "Tool Executor",
            config={"tool_name": "", "timeout_seconds": 30},
            position=(550.0, 200.0),
        )
        .add_node(
            "loop",   "LOOP",      "ReAct Loop",
            config={"max_iterations": 10, "exit_condition": ""},
            position=(550.0, 400.0),
        )
        .add_node(
            "observe", "LLM_CALL", "Observe & Reflect",
            config={
                "model": model,
                "system_prompt": "Summarise the tool result and decide next action.",
                "temperature": 0.2,
                "max_tokens": 512,
            },
            position=(800.0, 200.0),
        )
        .add_node("output",  "OUTPUT",    "Output",         position=(1050.0, 300.0))
        # Wiring
        .connect("input",   "data",      "reason",  "prompt")
        .connect("reason",  "response",  "tool",    "input")
        .connect("tool",    "output",    "observe",  "prompt")
        .connect("observe", "response",  "loop",    "input")
        .connect("loop",    "output",    "reason",  "prompt")
        .connect("loop",    "output",    "output",  "data")
        .build()
    )


# ---------------------------------------------------------------------------
# 4. RAG pipeline
# ---------------------------------------------------------------------------

def rag_pipeline(
    name: str = "RAG Pipeline",
    model: str = "gpt-4o",
    retriever_top_k: int = 5,
    description: str = "Retrieval-Augmented Generation: retrieve then generate.",
) -> GraphSpec:
    """Return a RAG graph: INPUT → RETRIEVER → PROMPT_TEMPLATE → LLM_CALL → OUTPUT.

    Parameters
    ----------
    name:
        Human-readable graph name.
    model:
        Generator LLM model identifier.
    retriever_top_k:
        Number of documents to retrieve.
    description:
        Graph description string.
    """
    return (
        GraphBuilder(name=name, description=description)
        .add_node("input",    "INPUT",           "User Query",       position=(50.0,  300.0))
        .add_node(
            "retriever", "RETRIEVER",       "Document Retriever",
            config={"top_k": retriever_top_k, "index_name": ""},
            position=(300.0, 300.0),
        )
        .add_node(
            "prompt",    "PROMPT_TEMPLATE", "RAG Prompt",
            config={
                "template": (
                    "Use the following context to answer the question.\n\n"
                    "Context:\n{{ context }}\n\nQuestion: {{ question }}"
                ),
                "template_id": "rag_default",
            },
            position=(550.0, 300.0),
        )
        .add_node(
            "generator", "LLM_CALL",        "Answer Generator",
            config={"model": model, "temperature": 0.3, "max_tokens": 1024},
            position=(800.0, 300.0),
        )
        .add_node("output",    "OUTPUT",          "Answer",            position=(1050.0, 300.0))
        # Wiring
        .connect("input",     "data",      "retriever", "query")
        .connect("retriever", "documents", "prompt",    "variables")
        .connect("input",     "data",      "prompt",    "variables")
        .connect("prompt",    "rendered_prompt", "generator", "prompt")
        .connect("generator", "response",  "output",    "data")
        .build()
    )


# ---------------------------------------------------------------------------
# 5. Human-in-the-loop approval graph
# ---------------------------------------------------------------------------

def hitl_approval_graph(
    name: str = "Human-in-the-Loop Approval",
    model: str = "gpt-4o",
    aegis_url: str = "http://aegis:8000",
    timeout_seconds: int = 3600,
    description: str = "Agent drafts a response; a human approves or rejects it.",
) -> GraphSpec:
    """Return a graph where an LLM draft is gated by human approval via Aegis HITL.

    Architecture
    ------------
    INPUT → LLM_CALL (draft) → HUMAN_IN_LOOP (approve/reject) → OUTPUT
                                      └── LLM_CALL (revise on rejection) ──┘
    """
    return (
        GraphBuilder(name=name, description=description)
        .add_node("input",   "INPUT",         "Input",          position=(50.0,  300.0))
        .add_node(
            "draft",   "LLM_CALL",      "Draft Response",
            config={"model": model, "temperature": 0.7, "max_tokens": 1024},
            position=(300.0, 300.0),
        )
        .add_node(
            "review",  "HUMAN_IN_LOOP", "Human Reviewer",
            config={"aegis_url": aegis_url, "timeout_seconds": timeout_seconds},
            position=(600.0, 300.0),
        )
        .add_node(
            "revise",  "LLM_CALL",      "Revise on Rejection",
            config={"model": model, "temperature": 0.5, "max_tokens": 1024},
            position=(600.0, 500.0),
        )
        .add_node("output",  "OUTPUT",         "Final Output",   position=(900.0, 300.0))
        # Wiring
        .connect("input",  "data",     "draft",  "prompt")
        .connect("draft",  "response", "review", "payload")
        .connect("review", "approved", "output", "data")
        .connect("review", "rejected", "revise", "prompt")
        .connect("revise", "response", "review", "payload")
        .build()
    )


# ---------------------------------------------------------------------------
# Registry of all built-in templates
# ---------------------------------------------------------------------------

TEMPLATES: dict = {
    "minimal": minimal_graph,
    "simple_llm": simple_llm_agent,
    "react": react_agent,
    "rag": rag_pipeline,
    "hitl": hitl_approval_graph,
}


def list_templates() -> list:
    """Return the names of all built-in template factories."""
    return list(TEMPLATES.keys())


def get_template(template_name: str, **kwargs) -> GraphSpec:
    """Instantiate a built-in template by name.

    Parameters
    ----------
    template_name:
        One of the keys returned by :func:`list_templates`.
    **kwargs:
        Keyword arguments forwarded to the template factory.

    Raises
    ------
    KeyError
        If *template_name* is not a recognised template.
    """
    if template_name not in TEMPLATES:
        available = ", ".join(sorted(TEMPLATES))
        raise KeyError(
            f"Unknown template '{template_name}'. Available: {available}"
        )
    return TEMPLATES[template_name](**kwargs)
