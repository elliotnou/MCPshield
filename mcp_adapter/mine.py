"""Capability mining — convert raw API endpoints into high-level MCP tools.

Approach:
  1. Bucket endpoints by tag (falling back to path prefix).
  2. Inside each bucket, cluster GET-only groups into a single search tool
     when the heuristic fires.
  3. Write/delete endpoints always get their own dedicated tool.
  4. Produce clean snake_case names and human-friendly descriptions.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .logger import get_logger, log_stage
from .models import (
    APISpec,
    Endpoint,
    HttpMethod,
    ParamLocation,
    SafetyLevel,
    ToolDefinition,
    ToolParam,
)


# ── Naming utilities ────────────────────────────────────────────────────────

_VERB_MAP: dict[HttpMethod, str] = {
    HttpMethod.GET: "get",
    HttpMethod.POST: "create",
    HttpMethod.PUT: "update",
    HttpMethod.PATCH: "update",
    HttpMethod.DELETE: "delete",
    HttpMethod.HEAD: "head",
    HttpMethod.OPTIONS: "options",
}

_PARAM_PLACEHOLDER = re.compile(r"\{[^}]+\}")


def _to_snake(text: str) -> str:
    """Convert arbitrary text to a valid snake_case identifier."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _resource_name(path: str) -> str:
    """Extract the primary resource from a URL path.

    /pets/{petId}/toys  →  pet_toys
    /api/v1/issues      →  issues
    """
    parts = [s for s in path.split("/") if s and not _PARAM_PLACEHOLDER.fullmatch(s)]
    # skip version-like segments (v1, v2, ...)
    parts = [s for s in parts if not re.fullmatch(r"v\d+", s)]
    if not parts:
        return "root"
    tail = parts[-2:] if len(parts) >= 2 else parts
    return "_".join(_to_snake(seg) for seg in tail)


def _derive_tool_name(ep: Endpoint) -> str:
    """Build a concise tool name from an endpoint."""
    if ep.operation_id:
        return _to_snake(ep.operation_id)
    verb = _VERB_MAP.get(ep.method, ep.method.value.lower())
    resource = _resource_name(ep.path)
    # "list_X" reads better than "get_X" for collection endpoints
    if verb == "get" and not _PARAM_PLACEHOLDER.search(ep.path):
        verb = "list"
    return f"{verb}_{resource}"


def _build_description(ep: Endpoint) -> str:
    """Human-readable one-liner for the tool."""
    text = ep.summary or (ep.description.split("\n")[0][:200] if ep.description else "")
    if not text:
        text = f"{ep.method.value} {ep.path}"
    if ep.deprecated:
        text += " [DEPRECATED]"
    return text


# ── Param conversion ───────────────────────────────────────────────────────

_JSON_TYPE_ALIAS = {
    "integer": "integer", "int": "integer",
    "number": "number", "float": "number",
    "boolean": "boolean", "bool": "boolean",
    "array": "array", "object": "object",
}


def _endpoint_params_to_tool_params(ep: Endpoint) -> list[ToolParam]:
    """Translate endpoint params into MCP tool params, deduplicating."""
    seen: set[str] = set()
    out: list[ToolParam] = []
    for p in ep.parameters:
        if p.name in seen:
            continue
        seen.add(p.name)
        out.append(ToolParam(
            name=p.name,
            description=p.description or f"{p.location.value} parameter",
            json_type=_JSON_TYPE_ALIAS.get(p.schema_type, "string"),
            required=p.required,
            enum=p.enum,
            default=p.default,
        ))
    return out


# ── Safety heuristic ───────────────────────────────────────────────────────

def _quick_safety(ep: Endpoint) -> SafetyLevel:
    """Fast safety guess based solely on the HTTP method."""
    if ep.method == HttpMethod.DELETE:
        return SafetyLevel.DESTRUCTIVE
    if ep.method in {HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH}:
        return SafetyLevel.WRITE
    return SafetyLevel.READ


# ── Grouping logic ─────────────────────────────────────────────────────────

def _bucket_key(ep: Endpoint) -> str:
    """Decide which bucket an endpoint belongs to."""
    return _to_snake(ep.tags[0]) if ep.tags else _resource_name(ep.path)


def _is_mergeable(endpoints: list[Endpoint]) -> bool:
    """Decide whether a group of GET endpoints should collapse into one tool."""
    if len(endpoints) < 3:
        return False
    return all(e.method == HttpMethod.GET for e in endpoints)


def _build_merged_tool(group: str, endpoints: list[Endpoint]) -> ToolDefinition:
    """Collapse several GET endpoints into a single search/list tool."""
    combined_params: dict[str, ToolParam] = {}
    for ep in endpoints:
        for tp in _endpoint_params_to_tool_params(ep):
            combined_params.setdefault(tp.name, tp)
    return ToolDefinition(
        name=f"search_{group}",
        description=f"Search or list {group.replace('_', ' ')} with flexible filtering.",
        safety=SafetyLevel.READ,
        params=list(combined_params.values()),
        endpoints=endpoints,
        tags=[group],
    )


# ── Public API ─────────────────────────────────────────────────────────────

def mine_tools(spec: APISpec) -> list[ToolDefinition]:
    """Main entry point: convert an APISpec into a list of ToolDefinitions."""
    with log_stage("Capability Mining") as logger:
        buckets: dict[str, list[Endpoint]] = defaultdict(list)
        for ep in spec.endpoints:
            buckets[_bucket_key(ep)].append(ep)

        logger.info(
            "Grouped %d endpoints into %d resource groups: %s",
            len(spec.endpoints), len(buckets), list(buckets.keys()),
        )

        tools: list[ToolDefinition] = []
        used_names: set[str] = set()

        def _register(td: ToolDefinition) -> None:
            """Add a tool, deduplicating by name."""
            name = td.name
            if name in used_names:
                suffix = _to_snake(td.endpoints[0].path.split("/")[-1]) if td.endpoints else "alt"
                name = f"{name}_{suffix}"
            if name not in used_names:
                td.name = name
                tools.append(td)
                used_names.add(name)

        for group_name, eps in buckets.items():
            reads = [e for e in eps if e.method == HttpMethod.GET]
            writes = [e for e in eps if e.method != HttpMethod.GET]

            # Try collapsing read-heavy groups
            if _is_mergeable(reads):
                _register(_build_merged_tool(group_name, reads))
            else:
                for ep in reads:
                    _register(ToolDefinition(
                        name=_derive_tool_name(ep),
                        description=_build_description(ep),
                        safety=_quick_safety(ep),
                        params=_endpoint_params_to_tool_params(ep),
                        endpoints=[ep],
                        tags=ep.tags or [group_name],
                    ))

            # Every write/delete endpoint gets its own tool
            for ep in writes:
                _register(ToolDefinition(
                    name=_derive_tool_name(ep),
                    description=_build_description(ep),
                    safety=_quick_safety(ep),
                    params=_endpoint_params_to_tool_params(ep),
                    endpoints=[ep],
                    tags=ep.tags or [group_name],
                ))

        logger.info("Extracted %d tools: %s", len(tools), [t.name for t in tools])
        return sorted(tools, key=lambda t: t.name)
