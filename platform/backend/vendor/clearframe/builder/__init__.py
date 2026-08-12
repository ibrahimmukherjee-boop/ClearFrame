"""ClearFrame Builder – drag-and-drop AI agent construction engine.

Public API
----------
Nodes
    NodeKind, NodeSpec, PortSpec, NodeRegistry
Graph
    EdgeSpec, NodeInstance, GraphSpec, GraphBuilder
Serialisation
    graph_to_dict, graph_from_dict, graph_to_json, graph_from_json,
    save_graph, load_graph, GraphCodec, default_codec
Validation
    Severity, ValidationIssue, ValidationResult, validate
Templates
    minimal_graph, simple_llm_agent, react_agent, rag_pipeline,
    hitl_approval_graph, list_templates, get_template
"""

from .nodes import NodeKind, NodeSpec, PortSpec, NodeRegistry
from .graph import EdgeSpec, NodeInstance, GraphSpec, GraphBuilder
from .serializer import (
    graph_to_dict,
    graph_from_dict,
    graph_to_json,
    graph_from_json,
    save_graph,
    load_graph,
    GraphCodec,
    default_codec,
)
from .validator import Severity, ValidationIssue, ValidationResult, validate
from .templates import (
    minimal_graph,
    simple_llm_agent,
    react_agent,
    rag_pipeline,
    hitl_approval_graph,
    list_templates,
    get_template,
    TEMPLATES,
)

__all__ = [
    # nodes
    "NodeKind",
    "NodeSpec",
    "PortSpec",
    "NodeRegistry",
    # graph
    "EdgeSpec",
    "NodeInstance",
    "GraphSpec",
    "GraphBuilder",
    # serializer
    "graph_to_dict",
    "graph_from_dict",
    "graph_to_json",
    "graph_from_json",
    "save_graph",
    "load_graph",
    "GraphCodec",
    "default_codec",
    # validator
    "Severity",
    "ValidationIssue",
    "ValidationResult",
    "validate",
    # templates
    "minimal_graph",
    "simple_llm_agent",
    "react_agent",
    "rag_pipeline",
    "hitl_approval_graph",
    "list_templates",
    "get_template",
    "TEMPLATES",
]
