"""clearframe/builder/validator.py

Graph validation logic for ClearFrame agent graphs.
Runs a series of structural and semantic checks on a GraphSpec and
returns a list of ValidationError objects describing any issues found.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .graph import GraphSpec
from .nodes import NodeRegistry


# ---------------------------------------------------------------------------
# Severity levels and error dataclass
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: Severity
    code: str
    message: str
    node_id: Optional[str] = None
    edge_id: Optional[str] = None

    def __str__(self) -> str:
        loc = ""
        if self.node_id:
            loc += f" [node={self.node_id}]"
        if self.edge_id:
            loc += f" [edge={self.edge_id}]"
        return f"[{self.severity.value.upper()}] {self.code}{loc}: {self.message}"


# ---------------------------------------------------------------------------
# Validation result container
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Aggregated result of a full graph validation run."""

    issues: List[ValidationIssue] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def is_valid(self) -> bool:
        """True when there are no ERROR-level issues."""
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    def raise_if_invalid(self) -> None:
        """Raise a ValueError listing all errors if the graph is invalid."""
        if not self.is_valid:
            msgs = "\n".join(str(e) for e in self.errors)
            raise ValueError(f"Graph validation failed:\n{msgs}")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ValidationResult valid={self.is_valid} "
            f"errors={len(self.errors)} warnings={len(self.warnings)}>"
        )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_has_nodes(graph: GraphSpec, result: ValidationResult) -> None:
    if not graph.nodes:
        result.add(ValidationIssue(
            severity=Severity.ERROR,
            code="EMPTY_GRAPH",
            message="Graph contains no nodes.",
        ))


def _check_has_input_node(graph: GraphSpec, result: ValidationResult) -> None:
    input_nodes = [
        n for n in graph.nodes.values()
        if n.kind == "INPUT"
    ]
    if not input_nodes:
        result.add(ValidationIssue(
            severity=Severity.ERROR,
            code="NO_INPUT_NODE",
            message="Graph must contain at least one INPUT node.",
        ))
    elif len(input_nodes) > 1:
        result.add(ValidationIssue(
            severity=Severity.WARNING,
            code="MULTIPLE_INPUT_NODES",
            message=f"Graph has {len(input_nodes)} INPUT nodes; typically only one is expected.",
        ))


def _check_has_output_node(graph: GraphSpec, result: ValidationResult) -> None:
    output_nodes = [
        n for n in graph.nodes.values()
        if n.kind == "OUTPUT"
    ]
    if not output_nodes:
        result.add(ValidationIssue(
            severity=Severity.ERROR,
            code="NO_OUTPUT_NODE",
            message="Graph must contain at least one OUTPUT node.",
        ))


def _check_known_node_kinds(graph: GraphSpec, result: ValidationResult) -> None:
    known = {spec.kind for spec in NodeRegistry.all()}
    for node_id, node in graph.nodes.items():
        if node.kind not in known:
            result.add(ValidationIssue(
                severity=Severity.ERROR,
                code="UNKNOWN_NODE_KIND",
                message=f"Node kind '{node.kind}' is not registered.",
                node_id=node_id,
            ))


def _check_edge_port_existence(graph: GraphSpec, result: ValidationResult) -> None:
    """Verify that each edge references real ports on registered node specs."""
    spec_map = {s.kind: s for s in NodeRegistry.all()}
    for edge in graph.edges:
        src_node = graph.nodes.get(edge.source_node)
        tgt_node = graph.nodes.get(edge.target_node)

        if src_node and src_node.kind in spec_map:
            src_spec = spec_map[src_node.kind]
            out_ports = {p.name for p in src_spec.outputs}
            if edge.source_port not in out_ports:
                result.add(ValidationIssue(
                    severity=Severity.ERROR,
                    code="INVALID_SOURCE_PORT",
                    message=(
                        f"Edge references non-existent output port "
                        f"'{edge.source_port}' on node kind '{src_node.kind}'."
                    ),
                    edge_id=edge.edge_id,
                ))

        if tgt_node and tgt_node.kind in spec_map:
            tgt_spec = spec_map[tgt_node.kind]
            in_ports = {p.name for p in tgt_spec.inputs}
            if edge.target_port not in in_ports:
                result.add(ValidationIssue(
                    severity=Severity.ERROR,
                    code="INVALID_TARGET_PORT",
                    message=(
                        f"Edge references non-existent input port "
                        f"'{edge.target_port}' on node kind '{tgt_node.kind}'."
                    ),
                    edge_id=edge.edge_id,
                ))


def _check_no_self_loops(graph: GraphSpec, result: ValidationResult) -> None:
    for edge in graph.edges:
        if edge.source_node == edge.target_node:
            result.add(ValidationIssue(
                severity=Severity.ERROR,
                code="SELF_LOOP",
                message=f"Edge creates a self-loop on node '{edge.source_node}'.",
                edge_id=edge.edge_id,
            ))


def _check_duplicate_edge_ids(graph: GraphSpec, result: ValidationResult) -> None:
    seen: set = set()
    for edge in graph.edges:
        if edge.edge_id in seen:
            result.add(ValidationIssue(
                severity=Severity.ERROR,
                code="DUPLICATE_EDGE_ID",
                message=f"Duplicate edge id '{edge.edge_id}' detected.",
                edge_id=edge.edge_id,
            ))
        seen.add(edge.edge_id)


def _check_duplicate_node_ids(graph: GraphSpec, result: ValidationResult) -> None:
    """Node ids are dict keys so duplicates are impossible, but validate format."""
    for node_id, node in graph.nodes.items():
        if not node_id or not isinstance(node_id, str):
            result.add(ValidationIssue(
                severity=Severity.ERROR,
                code="INVALID_NODE_ID",
                message="Node id must be a non-empty string.",
                node_id=str(node_id),
            ))


def _check_disconnected_nodes(graph: GraphSpec, result: ValidationResult) -> None:
    """Warn about nodes that have no edges at all (isolated nodes)."""
    connected: set = set()
    for edge in graph.edges:
        connected.add(edge.source_node)
        connected.add(edge.target_node)
    for node_id in graph.nodes:
        if node_id not in connected:
            result.add(ValidationIssue(
                severity=Severity.WARNING,
                code="ISOLATED_NODE",
                message=f"Node '{node_id}' is not connected to any edge.",
                node_id=node_id,
            ))


# ---------------------------------------------------------------------------
# Main validate function
# ---------------------------------------------------------------------------

_CHECKS = [
    _check_has_nodes,
    _check_has_input_node,
    _check_has_output_node,
    _check_known_node_kinds,
    _check_edge_port_existence,
    _check_no_self_loops,
    _check_duplicate_edge_ids,
    _check_duplicate_node_ids,
    _check_disconnected_nodes,
]


def validate(graph: GraphSpec) -> ValidationResult:
    """Run all validation checks on *graph* and return a ValidationResult.

    Parameters
    ----------
    graph:
        The GraphSpec to validate.

    Returns
    -------
    ValidationResult
        Contains all issues found.  Call ``.raise_if_invalid()`` to raise
        a ``ValueError`` when errors are present.
    """
    result = ValidationResult()
    for check in _CHECKS:
        check(graph, result)
    return result
