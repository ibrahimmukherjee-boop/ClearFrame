from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

PACKS_DIR = Path(__file__).resolve().parent / "packs"


class PolicyError(Exception):
    pass


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HITL = "require_hitl"


@dataclass
class PolicyDecision:
    decision: Decision
    policy: str = ""
    rule: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW


def load_pack(path: str | Path) -> dict[str, Any]:
    """Load one policy pack from YAML (or JSON — YAML is a superset)."""
    if yaml is None:
        raise PolicyError("Policy packs require PyYAML: pip install pyyaml")
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or "name" not in data:
        raise PolicyError(f"Policy pack {path} must be a mapping with a 'name' key.")
    return data


def packaged_packs() -> dict[str, Path]:
    """Return {pack_name: path} for the policy packs shipped with ClearFrame."""
    if not PACKS_DIR.exists():
        return {}
    return {p.stem: p for p in sorted(PACKS_DIR.glob("*.yaml"))}


class PolicyEngine:
    """Evaluates tool calls against one or more policy packs.

    The most restrictive decision wins: DENY > REQUIRE_HITL > ALLOW.
    """

    def __init__(self, packs: list[dict[str, Any]] | None = None) -> None:
        self._packs = packs or []
        self._call_counts: dict[str, int] = {}

    @classmethod
    def with_packs(cls, *names: str, extra_paths: list[str | Path] | None = None) -> "PolicyEngine":
        available = packaged_packs()
        packs = []
        for name in names:
            if name not in available:
                raise PolicyError(
                    f"Unknown policy pack '{name}'. Available: {sorted(available)}"
                )
            packs.append(load_pack(available[name]))
        for path in extra_paths or []:
            packs.append(load_pack(path))
        return cls(packs)

    @classmethod
    def baseline(cls) -> "PolicyEngine":
        return cls.with_packs("baseline")

    @property
    def pack_names(self) -> list[str]:
        return [p.get("name", "?") for p in self._packs]

    def add_pack(self, pack: dict[str, Any]) -> None:
        self._packs.append(pack)

    # ── Evaluation ────────────────────────────────────────────────────────

    def evaluate(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        trust_level: str | None = None,
    ) -> PolicyDecision:
        args = args or {}
        outcome = PolicyDecision(Decision.ALLOW)
        arg_text = " ".join(str(v) for v in args.values())

        self._call_counts[tool_name] = self._call_counts.get(tool_name, 0) + 1

        for pack in self._packs:
            pname = pack.get("name", "?")
            rules = pack.get("rules", {})

            # tools.deny
            for pattern in (rules.get("tools", {}) or {}).get("deny", []) or []:
                if fnmatch.fnmatch(tool_name, pattern):
                    return PolicyDecision(
                        Decision.DENY, pname, f"tools.deny:{pattern}",
                        [f"Tool '{tool_name}' matches deny pattern '{pattern}'."],
                    )

            # tools.allow (if present, everything else is denied)
            allow_list = (rules.get("tools", {}) or {}).get("allow")
            if allow_list:
                if not any(fnmatch.fnmatch(tool_name, p) for p in allow_list):
                    return PolicyDecision(
                        Decision.DENY, pname, "tools.allow",
                        [f"Tool '{tool_name}' is not in the allow list."],
                    )

            # domains.allow — check URL-ish args
            domain_allow = (rules.get("domains", {}) or {}).get("allow")
            if domain_allow:
                urls = re.findall(r"https?://([^/\s\"']+)", arg_text)
                for host in urls:
                    if not any(fnmatch.fnmatch(host, pat) for pat in domain_allow):
                        return PolicyDecision(
                            Decision.DENY, pname, "domains.allow",
                            [f"Host '{host}' is outside the allowed domains."],
                        )

            # data.deny_patterns — regex guards on arguments
            for entry in (rules.get("data", {}) or {}).get("deny_patterns", []) or []:
                pattern = entry["pattern"] if isinstance(entry, dict) else entry
                label = entry.get("label", pattern) if isinstance(entry, dict) else pattern
                if re.search(pattern, arg_text, re.IGNORECASE):
                    return PolicyDecision(
                        Decision.DENY, pname, f"data.deny_patterns:{label}",
                        [f"Arguments match forbidden data pattern '{label}'."],
                    )

            # limits.max_calls_per_tool
            limits = rules.get("limits", {}) or {}
            max_calls = limits.get("max_calls_per_tool")
            if max_calls is not None and self._call_counts[tool_name] > int(max_calls):
                return PolicyDecision(
                    Decision.DENY, pname, "limits.max_calls_per_tool",
                    [f"Tool '{tool_name}' exceeded {max_calls} calls this session."],
                )

            # trust.min_level
            min_level = (rules.get("trust", {}) or {}).get("min_level")
            if min_level and trust_level is not None:
                order = ["SANDBOX", "RESTRICTED", "STANDARD", "ELEVATED", "CRITICAL"]
                try:
                    if order.index(trust_level) < order.index(min_level):
                        return PolicyDecision(
                            Decision.DENY, pname, "trust.min_level",
                            [f"Trust level {trust_level} is below required {min_level}."],
                        )
                except ValueError:
                    pass

            # actions.require_approval → HITL (deny still wins over this)
            for pattern in (rules.get("actions", {}) or {}).get("require_approval", []) or []:
                if fnmatch.fnmatch(tool_name, pattern):
                    outcome = PolicyDecision(
                        Decision.REQUIRE_HITL, pname, f"actions.require_approval:{pattern}",
                        [f"Tool '{tool_name}' requires human approval (Aegis)."],
                    )

        return outcome

    def stats(self) -> dict[str, Any]:
        return {"packs": self.pack_names, "call_counts": dict(self._call_counts)}
