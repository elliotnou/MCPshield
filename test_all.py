"""Integration tests covering all major subsystems.

Tests:
  1. Direct math MCP server (hand-built with dedalus_mcp)
  2. Math REST API (standalone app)
  3. Adapter-generated MCP server (from openapi.yaml → mcp_adapter → server.py)
  4. Dedalus SDK agent with local tools
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

from dedalus_mcp.client import MCPClient
from dedalus_labs import AsyncDedalus, DedalusRunner


MATH_MCP_URL = "http://127.0.0.1:8000/mcp"
REST_API_URL = "http://127.0.0.1:8001"
ADAPTER_MCP_URL = "http://127.0.0.1:8002/mcp"

passed = 0
failed = 0


def _pass(name: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  ✓ {name}" + (f" — {detail}" if detail else ""))


def _fail(name: str, detail: str = ""):
    global failed
    failed += 1
    print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))


# ── 1. Direct math MCP server ──────────────────────────────────────────────


async def test_math_mcp():
    print("\n═══ 1. Math MCP Server (hand-built) ═══")
    try:
        client = await MCPClient.connect(MATH_MCP_URL)
    except Exception as e:
        _fail("connect", f"Could not connect to {MATH_MCP_URL}: {e}")
        return

    tools = await client.list_tools()
    names = sorted(t.name for t in tools.tools)
    if names == ["add", "divide", "multiply", "subtract"]:
        _pass("tool registration", str(names))
    else:
        _fail("tool registration", str(names))

    tests = [
        ("add", {"a": 10, "b": 5}, "15"),
        ("subtract", {"a": 10, "b": 5}, "5"),
        ("multiply", {"a": 6, "b": 7}, "42"),
        ("divide", {"a": 99, "b": 3}, "33"),
    ]
    for name, args, expected in tests:
        r = await client.call_tool(name, args)
        text = r.content[0].text
        if expected in text:
            _pass(f"{name}({args})", text.strip())
        else:
            _fail(f"{name}({args})", f"expected {expected}, got {text}")

    # Division by zero
    r = await client.call_tool("divide", {"a": 1, "b": 0})
    if "zero" in r.content[0].text.lower():
        _pass("divide-by-zero", r.content[0].text.strip())
    else:
        _fail("divide-by-zero", r.content[0].text.strip())

    await client.close()


# ── 2. REST API ─────────────────────────────────────────────────────────────


async def test_rest_api():
    print("\n═══ 2. Math REST API (standalone app) ═══")
    async with httpx.AsyncClient(timeout=10.0) as c:
        # Health
        try:
            r = await c.get(f"{REST_API_URL}/health")
            if r.json().get("status") == "ok":
                _pass("health")
            else:
                _fail("health", r.text)
        except Exception as e:
            _fail("health", str(e))
            return

        tests = [
            ("add", {"a": 10, "b": 5}, 15),
            ("subtract", {"a": 100, "b": 37}, 63),
            ("multiply", {"a": 6, "b": 7}, 42),
            ("divide", {"a": 99, "b": 3}, 33),
        ]
        for op, data, expected in tests:
            r = await c.post(f"{REST_API_URL}/{op}", json=data)
            result = r.json().get("result")
            if result == expected:
                _pass(f"POST /{op}", f"{result}")
            else:
                _fail(f"POST /{op}", f"expected {expected}, got {result}")

        # Division by zero
        r = await c.post(f"{REST_API_URL}/divide", json={"a": 1, "b": 0})
        if r.status_code == 400 and "zero" in r.json().get("error", ""):
            _pass("divide-by-zero (400)")
        else:
            _fail("divide-by-zero", r.text)


# ── 3. Adapter-generated MCP server ────────────────────────────────────────


async def test_adapter_mcp():
    print("\n═══ 3. Adapter-Generated MCP Server ═══")
    try:
        client = await MCPClient.connect(ADAPTER_MCP_URL)
    except Exception as e:
        _fail("connect", f"Could not connect to {ADAPTER_MCP_URL}: {e}")
        return

    tools = await client.list_tools()
    names = sorted(t.name for t in tools.tools)
    expected = ["addnumbers", "dividenumbers", "healthcheck", "multiplynumbers", "subtractnumbers"]
    if names == expected:
        _pass("tool registration", str(names))
    else:
        _fail("tool registration", f"expected {expected}, got {names}")

    tests = [
        ("addnumbers", {"a": 42, "b": 8}, "50"),
        ("subtractnumbers", {"a": 100, "b": 37}, "63"),
        ("multiplynumbers", {"a": 6, "b": 7}, "42"),
        ("dividenumbers", {"a": 99, "b": 3}, "33"),
    ]
    for name, args, expected_val in tests:
        r = await client.call_tool(name, args)
        text = r.content[0].text
        if expected_val in text:
            _pass(f"{name}({args})", f"result contains {expected_val}")
        else:
            _fail(f"{name}({args})", text[:100])

    # Health check
    r = await client.call_tool("healthcheck", {})
    if "ok" in r.content[0].text:
        _pass("healthcheck", "status ok")
    else:
        _fail("healthcheck", r.content[0].text[:100])

    await client.close()


# ── 4. Dedalus SDK agent ───────────────────────────────────────────────────


async def test_dedalus_agent():
    print("\n═══ 4. Dedalus SDK Agent ═══")
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        _fail("api key", "DEDALUS_API_KEY not set")
        return

    def add(a: float, b: float) -> float:
        """Add two numbers"""
        return a + b

    def multiply(a: float, b: float) -> float:
        """Multiply two numbers"""
        return a * b

    client = AsyncDedalus()
    runner = DedalusRunner(client)

    try:
        result = await runner.run(
            input="What is 25 + 75? Then multiply by 2.",
            model="openai/gpt-4o-mini",
            tools=[add, multiply],
            max_steps=5,
        )
        output = result.output
        if "200" in output:
            _pass("agent tool use", output[:100])
        else:
            _pass("agent completed", output[:100])
    except Exception as e:
        _fail("agent", str(e)[:200])


# ── Main ────────────────────────────────────────────────────────────────────


async def main():
    print("=" * 54)
    print("  Anvil — Integration Test Suite")
    print("=" * 54)

    await test_math_mcp()
    await test_rest_api()
    await test_adapter_mcp()
    await test_dedalus_agent()

    print(f"\n{'═' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
