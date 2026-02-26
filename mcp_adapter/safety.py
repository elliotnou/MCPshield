"""Safety classification and policy enforcement.

Assigns risk levels to tools, applies allowlist/denylist policies,
annotates descriptions with side-effect warnings, and redacts
sensitive parameter names so MCP clients can enforce human-in-the-loop
where appropriate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .logger import get_logger, log_stage
from .models import SafetyLevel, ToolDefinition


# ── Configurable policy ────────────────────────────────────────────────────

_DEFAULT_REDACT_PATTERNS = [
    r"(?i)password",
    r"(?i)secret",
    r"(?i)token",
    r"(?i)ssn",
    r"(?i)credit.?card",
]


@dataclass
class SafetyPolicy:
    """Controls what the generated MCP server is allowed to expose."""

    allowlist: list[str] = field(default_factory=list)
    denylist: list[str] = field(default_factory=list)
    block_destructive: bool = False
    require_write_confirmation: bool = True
    redact_patterns: list[str] = field(default_factory=lambda: list(_DEFAULT_REDACT_PATTERNS))
    max_tools: int = 0       # 0 = unlimited


# ── Keyword-based reclassification ─────────────────────────────────────────

_RE_DESTRUCTIVE = re.compile(
    r"(?i)\b(delete|remove|destroy|purge|drop|revoke|terminate|cancel)\b",
)
_RE_WRITE = re.compile(
    r"(?i)\b(create|update|set|add|assign|upload|import|modify|enable|disable|patch|put)\b",
)


def reclassify_safety(tool: ToolDefinition) -> SafetyLevel:
    """Refine safety using name + description keyword heuristics."""
    combined = f"{tool.name} {tool.description}"
    if _RE_DESTRUCTIVE.search(combined):
        return SafetyLevel.DESTRUCTIVE
    if _RE_WRITE.search(combined):
        return SafetyLevel.WRITE
    return tool.safety


# ── Description badges ─────────────────────────────────────────────────────

_BADGES: dict[SafetyLevel, str] = {
    SafetyLevel.READ: "",
    SafetyLevel.WRITE: " [WRITES DATA]",
    SafetyLevel.DESTRUCTIVE: " [⚠️ DESTRUCTIVE — may permanently delete data]",
}


def _add_safety_badge(tool: ToolDefinition) -> str:
    """Append a safety badge to the tool description if not already present."""
    badge = _BADGES.get(tool.safety, "")
    if badge and badge not in tool.description:
        return tool.description + badge
    return tool.description


# ── PII / secret redaction ─────────────────────────────────────────────────

def _is_sensitive(param_name: str, patterns: list[str]) -> bool:
    """Return True if the parameter name matches any redaction pattern."""
    return any(re.search(pat, param_name) for pat in patterns)


def _redact_sensitive_params(tool: ToolDefinition, patterns: list[str]) -> None:
    """Prefix sensitive params with a [REDACTED] marker."""
    for p in tool.params:
        if _is_sensitive(p.name, patterns):
            if not p.description.startswith("[REDACTED"):
                p.description = f"[REDACTED — sensitive field] {p.description}"


# ── Public entry point ─────────────────────────────────────────────────────

def apply_safety(
    tools: list[ToolDefinition],
    policy: SafetyPolicy | None = None,
) -> list[ToolDefinition]:
    """Run the full safety pipeline: classify, filter, annotate, redact.

    Returns a new list containing only the tools that pass the policy.
    """
    pol = policy or SafetyPolicy()

    with log_stage("Safety Classification") as logger:
        accepted: list[ToolDefinition] = []
        rejected: list[str] = []

        for tool in tools:
            # Step 1 — keyword reclassification
            prev = tool.safety
            tool.safety = reclassify_safety(tool)
            if prev != tool.safety:
                logger.debug(
                    "  Reclassified '%s': %s → %s",
                    tool.name, prev.value, tool.safety.value,
                )

            # Step 2 — allowlist / denylist filtering
            if pol.allowlist and tool.name not in pol.allowlist:
                rejected.append(f"{tool.name} (not in allowlist)")
                continue
            if tool.name in pol.denylist:
                rejected.append(f"{tool.name} (denylisted)")
                continue

            # Step 3 — block destructive if policy says so
            if pol.block_destructive and tool.safety == SafetyLevel.DESTRUCTIVE:
                rejected.append(f"{tool.name} (destructive blocked)")
                continue

            # Step 4 — badge + redact
            tool.description = _add_safety_badge(tool)
            _redact_sensitive_params(tool, pol.redact_patterns)

            accepted.append(tool)

        # Step 5 — cap total tool count
        if pol.max_tools > 0:
            accepted = accepted[: pol.max_tools]

        if rejected:
            logger.info("Blocked %d tools: %s", len(rejected), rejected)

        counts = {
            level: sum(1 for t in accepted if t.safety == level)
            for level in SafetyLevel
        }
        logger.info(
            "Passed %d tools (read=%d, write=%d, destructive=%d)",
            len(accepted), counts[SafetyLevel.READ],
            counts[SafetyLevel.WRITE], counts[SafetyLevel.DESTRUCTIVE],
        )

    return accepted
