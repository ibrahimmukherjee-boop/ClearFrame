"""clearframe/builder/graph.py

Graph specification and builder utilities for ClearFrame agent graphs.
Defines EdgeSpec, GraphSpec, and the GraphBuilder fluent API used to
construct, introspect, and export agent workflow graphs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .nodes import NodeSpec, NodeRegistry, PortSpec


# ---------------------------------------------------------------------------
# Edge specification
# ---------------------------------------------------------------------------

@dataclass
class EdgeSpec:
    """Describes a directed data connection between two node ports."""

    source_node: str          # node id in the graph
    source_port: str          # output port name on the source node
    target_node: str          # node id in the graph
    target_port: str          # input port name on the target node
    edge_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source": {"node": self.source_node, "port": self.source_port},
            "target": {"node": self.target_node, "port": self.target_port},
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EdgeSpec":
        return cls(
            source_node=data["source"]["node"],
            source_port=data["source"]["port"],
            target_node=data["target"]["node"],
            target_port=data["target"]["port"],
            edge_id=data.get("edge_id", str(uuid.uuid4())),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Node instance inside a graph
# ---------------------------------------------------------------------------

@dataclass
class NodeInstance:
    """A concrete node placed inside a graph, referencing a NodeSpec by kind."""

    node_id: str
    kind: str                          # NodeKind value
    display_name: str
    config: Dict[str, Any] = field(default_factory=dict)
    position: Tuple[float, float] = (0.0, 0.0)   # canvas x, y
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "display_name": self.display_name,
            "config": self.config,
            "position": list(self.position),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeInstance":
        pos = data.get("position", [0.0, 0.0])
        return cls(
            node_id=data["node_id"],
            kind=data["kind"],
            display_name=data["display_name"],
            config=data.get("config", {}),
            position=tuple(pos),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Graph specification
# ---------------------------------------------------------------------------

@dataclass
class GraphSpec:
    """Complete specification of a ClearFrame agent graph."""

    graph_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Graph"
    description: str = ""
    version: str = "1.0.0"
    nodes: Dict[str, NodeInstance] = field(default_factory=dict)
    edges: List[EdgeSpec] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def add_node(self, instance: NodeInstance) -> None:
        """Register a node instance; raises if the id already exists."""
        if instance.node_id in self.nodes:
            raise ValueError(f"Node id '{instance.node_id}' already exists in graph.")
        self.nodes[instance.node_id] = instance

    def add_edge(self, edge: EdgeSpec) -> None:
        """Append an edge; raises if source or target node ids are unknown."""
        for nid in (edge.source_node, edge.target_node):
            if nid not in self.nodes:
                raise ValueError(f"Node id '{nid}' not found in graph.")
        self.edges.append(edge)

    def get_node(self, node_id: str) -> NodeInstance:
        try:
            return self.nodes[node_id]
        except KeyError:
            raise KeyError(f"Node '{node_id}' not found.")

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all edges that reference it."""
        self.nodes.pop(node_id, None)
        self.edges = [
            e for e in self.edges
            if e.source_node != node_id and e.target_node != node_id
        ]

    def remove_edge(self, edge_id: str) -> None:
        self.edges = [e for e in self.edges if e.edge_id != edge_id]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphSpec":
        spec = cls(
            graph_id=data.get("graph_id", str(uuid.uuid4())),
            name=data.get("name", "Untitled Graph"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            metadata=data.get("metadata", {}),
        )
        for nid, nd in data.get("nodes", {}).items():
            spec.nodes[nid] = NodeInstance.from_dict(nd)
        for ed in data.get("edges", []):
            spec.edges.append(EdgeSpec.from_dict(ed))
        return spec

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<GraphSpec name={self.name!r} "
            f"nodes={len(self.nodes)} edges={len(self.edges)}>"
        )


# ---------------------------------------------------------------------------
# Fluent GraphBuilder
# ---------------------------------------------------------------------------

class GraphBuilder:
    """Fluent builder API for constructing ClearFrame GraphSpec objects.

    Example
    -------
    >>> graph = (
    ...     GraphBuilder(name="My Agent")
    ...     .add_node("input",  "INPUT",  "Input")
    ...     .add_node("llm",    "LLM_CALL", "GPT-4o",
    ...               config={"model": "gpt-4o", "system_prompt": "You are helpful."})
    ...     .add_node("output", "OUTPUT", "Output")
    ...     .connect("input", "data", "llm", "prompt")
    ...     .connect("llm",   "response", "output", "data")
    ...     .build()
    ... )
    """

    def __init__(
        self,
        name: str = "Untitled Graph",
        description: str = "",
        version: str = "1.0.0",
        graph_id: Optional[str] = None,
    ) -> None:
        self._spec = GraphSpec(
            graph_id=graph_id or str(uuid.uuid4()),
            name=name,
            description=description,
            version=version,
        )

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        kind: str,
        display_name: str,
        config: Optional[Dict[str, Any]] = None,
        position: Tuple[float, float] = (0.0, 0.0),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "GraphBuilder":
        """Add a node instance to the graph."""
        instance = NodeInstance(
            node_id=node_id,
            kind=kind,
            display_name=display_name,
            config=config or {},
            position=position,
            metadata=metadata or {},
        )
        self._spec.add_node(instance)
        return self

    def remove_node(self, node_id: str) -> "GraphBuilder":
        self._spec.remove_node(node_id)
        return self

    def update_node_config(
        self, node_id: str, config: Dict[str, Any]
    ) -> "GraphBuilder":
        """Merge *config* into the existing node configuration."""
        node = self._spec.get_node(node_id)
        node.config.update(config)
        return self

    def set_node_position(
        self, node_id: str, x: float, y: float
    ) -> "GraphBuilder":
        self._spec.get_node(node_id).position = (x, y)
        return self

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def connect(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
        edge_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "GraphBuilder":
        """Connect an output port on *source_node* to an input port on *target_node*."""
        edge = EdgeSpec(
            source_node=source_node,
            source_port=source_port,
            target_node=target_node,
            target_port=target_port,
            edge_id=edge_id or str(uuid.uuid4()),
            metadata=metadata or {},
        )
        self._spec.add_edge(edge)
        return self

    def disconnect(self, edge_id: str) -> "GraphBuilder":
        self._spec.remove_edge(edge_id)
        return self

    # ------------------------------------------------------------------
    # Graph-level metadata
    # ------------------------------------------------------------------

    def set_metadata(self, key: str, value: Any) -> "GraphBuilder":
        self._spec.metadata[key] = value
        return self

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------

    def build(self) -> GraphSpec:
        """Return the completed GraphSpec."""
        return self._spec

    def reset(self) -> "GraphBuilder":
        """Clear all nodes and edges but preserve name / description."""
        self._spec.nodes.clear()
        self._spec.edges.clear()
        return self

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GraphBuilder graph={self._spec!r}>"
