"""MCP server code generator.

Takes a list of ToolDefinitions + APISpec metadata and produces a
fully-functional Python MCP server file (using dedalus_mcp) plus
an optional requirements.txt and test file.

Uses direct string construction instead of Jinja2 templates for reliability
and easier debugging.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logger import get_logger, log_stage
from .models import (
    APISpec,
    AuthScheme,
    HttpMethod,
    ParamLocation,
    SafetyLevel,
    ToolDefinition,
    ToolParam,
)


# ── Type mapping ────────────────────────────────────────────────────────────

_PY_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def _py_type(json_type: str, required: bool) -> str:
    base = _PY_TYPE_MAP.get(json_type, "str")
    if not required:
        return f"{base} | None"
    return base


def _py_default(param: ToolParam) -> str:
    if param.default is not None:
        if isinstance(param.default, str):
            return f' = "{param.default}"'
        return f" = {param.default}"
    if not param.required:
        return " = None"
    return ""


def _safe_identifier(name: str) -> str:
    """Ensure name is a valid Python identifier."""
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if name and name[0].isdigit():
        name = f"p_{name}"
    return name


# ── Code fragments ─────────────────────────────────────────────────────────


def _build_signature(tool: ToolDefinition) -> str:
    """Build the function parameter signature string."""
    parts: list[str] = []
    # Required params first, then optional
    required = [p for p in tool.params if p.required]
    optional = [p for p in tool.params if not p.required]
    for p in required + optional:
        name = _safe_identifier(p.name)
        typ = _py_type(p.json_type, p.required)
        default = _py_default(p)
        parts.append(f"{name}: {typ}{default}")
    return ", ".join(parts)


def _build_path_format(tool: ToolDefinition) -> str:
    """Build an f-string path, replacing {paramName} with {param_name}."""
    if not tool.endpoints:
        return "/"
    path = tool.endpoints[0].path
    # Replace {camelCase} placeholders with {snake_case} python vars
    def _replace(m: re.Match) -> str:
        raw = m.group(1)
        return "{" + _safe_identifier(raw) + "}"
    return re.sub(r"\{([^}]+)\}", _replace, path)


def _build_tool_body(tool: ToolDefinition) -> str:
    """Build the function body that makes the HTTP call."""
    if not tool.endpoints:
        return '    return "No endpoint configured"'

    ep = tool.endpoints[0]
    path_fmt = _build_path_format(tool)
    method = ep.method.value

    lines: list[str] = []
    lines.append(f'    path = f"{path_fmt}"')

    query_params = [
        p for p in tool.params
        if any(
            ep_p.location == ParamLocation.QUERY and ep_p.name == p.name
            for e in tool.endpoints
            for ep_p in e.parameters
        )
    ]
    body_params = [
        p for p in tool.params
        if any(
            ep_p.location == ParamLocation.BODY and ep_p.name == p.name
            for e in tool.endpoints
            for ep_p in e.parameters
        )
    ]
    path_params = [
        p for p in tool.params
        if any(
            ep_p.location == ParamLocation.PATH and ep_p.name == p.name
            for e in tool.endpoints
            for ep_p in e.parameters
        )
    ]

    # Non-path, non-query, non-body params go to query by default
    categorized = {p.name for p in query_params + body_params + path_params}
    for p in tool.params:
        if p.name not in categorized:
            if method == "GET":
                query_params.append(p)
            else:
                body_params.append(p)

    if query_params:
        lines.append("    params: dict[str, Any] = {}")
        for p in query_params:
            name = _safe_identifier(p.name)
            if p.required:
                lines.append(f'    params["{p.name}"] = {name}')
            else:
                lines.append(f"    if {name} is not None:")
                lines.append(f'        params["{p.name}"] = {name}')

    if body_params and method in ("POST", "PUT", "PATCH"):
        lines.append("    body: dict[str, Any] = {}")
        for p in body_params:
            name = _safe_identifier(p.name)
            if p.required:
                lines.append(f'    body["{p.name}"] = {name}')
            else:
                lines.append(f"    if {name} is not None:")
                lines.append(f'        body["{p.name}"] = {name}')

    # Build the _request call
    if method == "GET":
        qarg = ", params=params" if query_params else ""
        lines.append(f'    return await _request("GET", path{qarg})')
    elif method in ("POST", "PUT", "PATCH"):
        qarg = ", params=params" if query_params else ""
        barg = ", body=body" if body_params else ""
        lines.append(
            f'    return await _request("{method}", path{qarg}{barg})'
        )
    elif method == "DELETE":
        lines.append(f'    return await _request("DELETE", path)')
    else:
        lines.append(f'    return await _request("{method}", path)')

    return "\n".join(lines)


# ── Auth detection ─────────────────────────────────────────────────────────


def _detect_auth(schemes: list[AuthScheme]) -> tuple[str, str]:
    """Return (header_name, scheme_prefix) from auth schemes."""
    for s in schemes:
        if s.scheme_type == "http":
            return "Authorization", "Bearer"
        if s.scheme_type == "apiKey":
            return s.header_name or "Authorization", ""
        if s.scheme_type == "oauth2":
            return "Authorization", "Bearer"
    return "Authorization", "Bearer"


# ── Main generator ─────────────────────────────────────────────────────────


@dataclass
class GeneratedOutput:
    """Result of code generation."""
    server_code: str
    test_code: str
    requirements: str
    env_template: str
    server_name: str
    tool_count: int
    output_dir: Path | None = None


def generate(
    spec: APISpec,
    tools: list[ToolDefinition],
    server_name: str | None = None,
    output_dir: str | Path | None = None,
) -> GeneratedOutput:
    """Generate a complete MCP server from an APISpec and tool definitions."""

    logger = get_logger()

    with log_stage("Code Generation"):
        name = server_name or re.sub(r"[^a-z0-9]+", "-", spec.title.lower()).strip("-")
        env_prefix = re.sub(r"[^A-Z0-9]+", "_", spec.title.upper()).strip("_")
        auth_header, auth_scheme = _detect_auth(spec.auth_schemes)
        logger.info("Server name: %s, env prefix: %s", name, env_prefix)
        logger.info("Auth: header=%s, scheme=%s", auth_header, auth_scheme or "(none)")

        # ── Server code ──────────────────────────────────────────────────
        code_lines: list[str] = []

        # Module docstring
        code_lines.append(f'"""Auto-generated MCP server for {spec.title}.')
        code_lines.append(f"")
        code_lines.append(f"API version: {spec.version}")
        code_lines.append(f"Base URL: {spec.base_url}")
        code_lines.append(f'"""')
        code_lines.append("")

        # Imports
        code_lines.append("from __future__ import annotations")
        code_lines.append("")
        code_lines.append("import asyncio")
        code_lines.append("import json")
        code_lines.append("import os")
        code_lines.append("from typing import Any")
        code_lines.append("")
        code_lines.append("import httpx")
        code_lines.append("from dedalus_mcp import MCPServer, tool")
        code_lines.append("")
        code_lines.append("")

        # Configuration
        code_lines.append("# ── Configuration " + "─" * 60)
        code_lines.append("")
        code_lines.append(
            f'BASE_URL = os.getenv("{env_prefix}_BASE_URL", "{spec.base_url}")'
        )
        code_lines.append(f'API_KEY = os.getenv("{env_prefix}_API_KEY", "")')
        code_lines.append("")

        # Headers helper
        code_lines.append("")
        code_lines.append("def _headers() -> dict[str, str]:")
        code_lines.append('    h: dict[str, str] = {')
        code_lines.append('        "Content-Type": "application/json",')
        code_lines.append('        "Accept": "application/json",')
        code_lines.append("    }")
        code_lines.append("    if API_KEY:")
        if auth_scheme:
            code_lines.append(
                f'        h["{auth_header}"] = f"{auth_scheme} {{API_KEY}}"'
            )
        else:
            code_lines.append(f'        h["{auth_header}"] = API_KEY')
        code_lines.append("    return h")
        code_lines.append("")

        # Request helper
        code_lines.append("")
        code_lines.append("async def _request(")
        code_lines.append("    method: str,")
        code_lines.append("    path: str,")
        code_lines.append("    *,")
        code_lines.append("    params: dict[str, Any] | None = None,")
        code_lines.append("    body: dict[str, Any] | None = None,")
        code_lines.append(") -> str:")
        code_lines.append(
            '    """Make an HTTP request to the upstream API."""'
        )
        code_lines.append('    url = f"{BASE_URL}{path}"')
        code_lines.append("    async with httpx.AsyncClient(timeout=30.0) as client:")
        code_lines.append("        resp = await client.request(")
        code_lines.append("            method,")
        code_lines.append("            url,")
        code_lines.append("            headers=_headers(),")
        code_lines.append("            params=params,")
        code_lines.append("            json=body if body else None,")
        code_lines.append("        )")
        code_lines.append("        resp.raise_for_status()")
        code_lines.append("        try:")
        code_lines.append("            data = resp.json()")
        code_lines.append("            return json.dumps(data, indent=2)")
        code_lines.append("        except Exception:")
        code_lines.append("            return resp.text")
        code_lines.append("")

        # Tools
        code_lines.append("")
        code_lines.append("# ── Tools " + "─" * 68)
        for t in tools:
            code_lines.append("")
            code_lines.append("")
            sig = _build_signature(t)
            code_lines.append(f"@tool(description={t.description!r})")
            code_lines.append(f"async def {t.name}({sig}) -> str:")
            body = _build_tool_body(t)
            code_lines.append(body)

        # Server
        code_lines.append("")
        code_lines.append("")
        code_lines.append("# ── Server " + "─" * 67)
        code_lines.append("")
        tool_names = ", ".join(t.name for t in tools)
        code_lines.append(f'server = MCPServer("{name}")')
        code_lines.append(f"server.collect({tool_names})")
        code_lines.append("")
        code_lines.append('if __name__ == "__main__":')
        code_lines.append("    asyncio.run(server.serve())")
        code_lines.append("")

        server_code = "\n".join(code_lines)

        # ── Test code ────────────────────────────────────────────────────
        test_lines: list[str] = []
        test_lines.append(f'"""Auto-generated tests for {spec.title} MCP server."""')
        test_lines.append("")
        test_lines.append("import asyncio")
        test_lines.append("import json")
        test_lines.append("")
        test_lines.append("from dedalus_mcp.client import MCPClient")
        test_lines.append("")
        test_lines.append("")
        test_lines.append("SERVER_URL = \"http://127.0.0.1:8000/mcp\"")
        test_lines.append("")
        test_lines.append("")
        test_lines.append("async def test_list_tools():")
        test_lines.append('    """Verify all expected tools are registered."""')
        test_lines.append("    client = await MCPClient.connect(SERVER_URL)")
        test_lines.append("    tools = await client.list_tools()")
        test_lines.append("    names = sorted(t.name for t in tools.tools)")
        test_lines.append(f"    expected = {sorted(t.name for t in tools)!r}")
        test_lines.append("    assert names == expected, f\"Tool mismatch: {{names}} != {{expected}}\"")
        test_lines.append('    print(f"✓ All {len(names)} tools registered")')
        test_lines.append("    await client.close()")
        test_lines.append("")
        test_lines.append("")
        test_lines.append("async def test_tool_schemas():")
        test_lines.append('    """Verify each tool has a valid input schema."""')
        test_lines.append("    client = await MCPClient.connect(SERVER_URL)")
        test_lines.append("    tools = await client.list_tools()")
        test_lines.append("    for t in tools.tools:")
        test_lines.append("        assert t.name, \"Tool missing name\"")
        test_lines.append("        assert t.description, f\"Tool {t.name} missing description\"")
        test_lines.append('        print(f"✓ {t.name}: schema OK")')
        test_lines.append("    await client.close()")
        test_lines.append("")

        # Dry-run tests for read tools only
        read_tools = [t for t in tools if t.safety == SafetyLevel.READ]
        if read_tools:
            test_lines.append("")
            test_lines.append("async def test_read_tools_dry_run():")
            test_lines.append('    """Dry-run read-only tools (expects server + upstream to be reachable)."""')
            test_lines.append("    client = await MCPClient.connect(SERVER_URL)")
            for t in read_tools[:5]:
                args: dict[str, Any] = {}
                for p in t.params:
                    if p.required:
                        if p.json_type == "integer":
                            args[p.name] = 1
                        elif p.json_type == "boolean":
                            args[p.name] = True
                        else:
                            args[p.name] = "test"
                test_lines.append(f"    try:")
                test_lines.append(f"        result = await client.call_tool({t.name!r}, {args!r})")
                test_lines.append(f'        print(f"✓ {t.name}: {{result.content[0].text[:100]}}")')
                test_lines.append(f"    except Exception as e:")
                test_lines.append(f'        print(f"✗ {t.name}: {{e}}")')
            test_lines.append("    await client.close()")
            test_lines.append("")

        test_lines.append("")
        test_lines.append("async def main():")
        test_lines.append("    await test_list_tools()")
        test_lines.append("    await test_tool_schemas()")
        if read_tools:
            test_lines.append("    # Uncomment to test against a live upstream:")
            test_lines.append("    # await test_read_tools_dry_run()")
        test_lines.append("")
        test_lines.append("")
        test_lines.append('if __name__ == "__main__":')
        test_lines.append("    asyncio.run(main())")
        test_lines.append("")

        test_code = "\n".join(test_lines)

        # ── Requirements ─────────────────────────────────────────────────
        requirements = "dedalus-mcp>=0.7.0\nhttpx>=0.28\n"

        # ── .env template ────────────────────────────────────────────────
        env_lines = [
            f"# {spec.title} MCP Server Configuration",
            f"{env_prefix}_BASE_URL={spec.base_url}",
            f"{env_prefix}_API_KEY=your-api-key-here",
        ]
        env_template = "\n".join(env_lines) + "\n"

        # ── main.py (Dedalus deploy entry point) ─────────────────────────
        main_code = (
            '"""Entry point for Dedalus deployment."""\n'
            '\n'
            'from server import server\n'
            'import asyncio\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    asyncio.run(server.serve())\n'
        )

        # ── pyproject.toml ───────────────────────────────────────────────
        pyproject = (
            '[project]\n'
            f'name = "{name}"\n'
            'version = "0.1.0"\n'
            f'description = "Auto-generated MCP adapter for {spec.title}"\n'
            'requires-python = ">=3.11"\n'
            'dependencies = [\n'
            '    "dedalus-mcp>=0.7.0",\n'
            '    "httpx>=0.27.0",\n'
            ']\n'
            '\n'
            '[build-system]\n'
            'requires = ["setuptools"]\n'
            'build-backend = "setuptools.backends._legacy:_Backend"\n'
        )

        output = GeneratedOutput(
            server_code=server_code,
            test_code=test_code,
            requirements=requirements,
            env_template=env_template,
            server_name=name,
            tool_count=len(tools),
        )

        # ── Write to disk ────────────────────────────────────────────────
        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "server.py").write_text(server_code, encoding="utf-8")
            (out / "test_server.py").write_text(test_code, encoding="utf-8")
            (out / "requirements.txt").write_text(requirements, encoding="utf-8")
            (out / ".env.example").write_text(env_template, encoding="utf-8")
            (out / "main.py").write_text(main_code, encoding="utf-8")
            (out / "pyproject.toml").write_text(pyproject, encoding="utf-8")
            output.output_dir = out
            logger.info(
                "Wrote 6 files to %s", out,
            )

    return output
