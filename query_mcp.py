"""Query any deployed Dedalus MCP server in natural language.

Usage:
    python query_mcp.py --server user/my-api "What is 10 divided by 3?"
    python query_mcp.py --server user/my-api --interactive
    python query_mcp.py --server user/my-api --model openai/gpt-4o "Describe the API"

Requires DEDALUS_API_KEY in .env
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys

from dotenv import load_dotenv
from dedalus_labs import AsyncDedalus, DedalusRunner

load_dotenv()

DEFAULT_MODEL = "openai/gpt-4o-mini"

# Patterns that indicate an auth failure in MCP tool responses
_AUTH_ERROR_PATTERNS = re.compile(
    r"(401|403|unauthorized|forbidden|authentication required|"
    r"invalid api.?key|missing api.?key|access denied|not authenticated|"
    r"api key is required|invalid token|expired token)",
    re.IGNORECASE,
)


def _derive_env_prefix(server_slug: str) -> str:
    """Derive likely env var prefix from server slug (e.g. user/petstore-mcp → PETSTORE_MCP)."""
    name = server_slug.split("/")[-1] if "/" in server_slug else server_slug
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def _check_auth_errors(mcp_results: list) -> list[str]:
    """Check MCP tool results for auth-related errors. Returns list of error messages."""
    errors = []
    for r in mcp_results:
        result_str = str(r.result) if r.result else ""
        if r.is_error or _AUTH_ERROR_PATTERNS.search(result_str):
            if _AUTH_ERROR_PATTERNS.search(result_str):
                errors.append(f"{r.tool_name}: {result_str}")
    return errors


def _print_auth_prompt(server: str, errors: list[str]) -> None:
    """Print auth error details and tell the user what to configure."""
    prefix = _derive_env_prefix(server)
    print(f"\n🔒 Authentication required for '{server}'")
    print(f"   The MCP server returned auth errors:\n")
    for err in errors:
        print(f"   ❌ {err}")
    print(f"\n   To fix, configure these env vars on the Dedalus dashboard:")
    print(f"     {prefix}_BASE_URL = <your-api-base-url>")
    print(f"     {prefix}_API_KEY  = <your-api-key>")
    print(f"\n   Dashboard: https://www.dedaluslabs.ai/dashboard/servers")
    print(f"   Select '{server}' → Environment Variables → set the values → Redeploy\n")


async def query(
    prompt: str,
    *,
    server: str,
    model: str = DEFAULT_MODEL,
) -> str | None:
    """Send a natural-language query to a Dedalus MCP server."""
    client = AsyncDedalus()
    runner = DedalusRunner(client)

    print(f"\n🧮 Query:  {prompt}")
    print(f"📡 Server: {server}")
    print(f"🤖 Model:  {model}")
    print("─" * 55)

    result = await runner.run(
        input=prompt,
        model=model,
        mcp_servers=[server],
    )

    # Check for auth errors in tool responses
    if result.mcp_results:
        auth_errors = _check_auth_errors(result.mcp_results)
        if auth_errors:
            _print_auth_prompt(server, auth_errors)
            return None

    # Show tool calls
    if result.mcp_results:
        for r in result.mcp_results:
            print(f"  🔧 {r.tool_name}({r.arguments})")
            print(f"     → {r.result}")
            print(f"     ⏱ {r.duration_ms}ms")
        print("─" * 55)

    answer = result.final_output
    print(f"\n✅ {answer}\n")
    return answer


async def interactive_mode(
    *,
    server: str,
    model: str = DEFAULT_MODEL,
) -> None:
    """Run queries in a loop until the user exits."""
    print(f"\n🔄 Interactive mode — querying '{server}'")
    print(f"   Type 'exit' or 'quit' to stop.\n")
    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye!")
            break
        if not prompt or prompt.lower() in ("exit", "quit", "q"):
            print("👋 Bye!")
            break
        await query(prompt, server=server, model=model)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query any deployed Dedalus MCP server in natural language.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query_mcp.py --server user/math-api "What is 10 divided by 3?"
  python query_mcp.py --server user/my-api --interactive
  python query_mcp.py --server user/my-api --model openai/gpt-4o "Describe the API"
        """,
    )
    parser.add_argument("prompt", nargs="?", help="Natural language query")
    parser.add_argument(
        "--server", "-s",
        required=True,
        help="MCP server slug (e.g. 'user/math-api')",
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"AI model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode — keep querying in a loop",
    )
    args = parser.parse_args()

    if args.interactive:
        asyncio.run(interactive_mode(server=args.server, model=args.model))
    elif args.prompt:
        asyncio.run(query(args.prompt, server=args.server, model=args.model))
    else:
        parser.error("Provide a prompt or use --interactive mode")


if __name__ == "__main__":
    main()
