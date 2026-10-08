"""clearframe/builder/serializer.py

JSON / dict serialisation helpers for ClearFrame graph specifications.
Supports round-trip encoding to JSON strings, Python dicts, and files.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, Union

from .graph import GraphSpec


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def graph_to_dict(graph: GraphSpec) -> Dict[str, Any]:
    """Serialise *graph* to a plain Python dict."""
    return graph.to_dict()


def graph_from_dict(data: Dict[str, Any]) -> GraphSpec:
    """Deserialise a GraphSpec from a plain Python dict."""
    return GraphSpec.from_dict(data)


def graph_to_json(graph: GraphSpec, *, indent: int = 2) -> str:
    """Serialise *graph* to a JSON string."""
    return json.dumps(graph_to_dict(graph), indent=indent, ensure_ascii=False)


def graph_from_json(json_str: str) -> GraphSpec:
    """Deserialise a GraphSpec from a JSON string."""
    data = json.loads(json_str)
    return graph_from_dict(data)


def save_graph(
    graph: GraphSpec,
    path: Union[str, pathlib.Path],
    *,
    indent: int = 2,
    encoding: str = "utf-8",
) -> pathlib.Path:
    """Write *graph* as JSON to *path*.

    Parameters
    ----------
    graph:
        The GraphSpec to serialise.
    path:
        Destination file path.  The ``.json`` extension is appended
        automatically if the path has no suffix.
    indent:
        JSON indentation level (default 2).
    encoding:
        File encoding (default utf-8).

    Returns
    -------
    pathlib.Path
        The resolved path of the written file.
    """
    p = pathlib.Path(path)
    if not p.suffix:
        p = p.with_suffix(".json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(graph_to_json(graph, indent=indent), encoding=encoding)
    return p.resolve()


def load_graph(
    path: Union[str, pathlib.Path],
    *,
    encoding: str = "utf-8",
) -> GraphSpec:
    """Load a GraphSpec from a JSON file at *path*.

    Parameters
    ----------
    path:
        Source file path.
    encoding:
        File encoding (default utf-8).

    Returns
    -------
    GraphSpec
        The deserialised graph specification.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    json.JSONDecodeError
        If the file content is not valid JSON.
    """
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Graph file not found: {p}")
    return graph_from_json(p.read_text(encoding=encoding))


# ---------------------------------------------------------------------------
# Low-level codec (allows future pluggable formats, e.g. YAML / MessagePack)
# ---------------------------------------------------------------------------

class GraphCodec:
    """Pluggable codec interface.  Subclass to support alternative formats."""

    def encode(self, graph: GraphSpec) -> str:
        """Encode *graph* to a string representation."""
        return graph_to_json(graph)

    def decode(self, data: str) -> GraphSpec:
        """Decode a string representation back to a GraphSpec."""
        return graph_from_json(data)

    def save(self, graph: GraphSpec, path: Union[str, pathlib.Path]) -> pathlib.Path:
        """Persist *graph* to disk and return the resolved path."""
        return save_graph(graph, path)

    def load(self, path: Union[str, pathlib.Path]) -> GraphSpec:
        """Load and return a GraphSpec from disk."""
        return load_graph(path)


#: Module-level default codec instance.
default_codec = GraphCodec()
