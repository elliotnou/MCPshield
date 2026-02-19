"""CLI entry point for Anvil — the MCP server forge.

Usage:
    python -m mcp_adapter generate --url http://host/openapi.json -o ./output --name my-api
    python -m mcp_adapter generate --url http://host/openapi.json -o ./output --name my-api --deploy
    python -m mcp_adapter generate --spec path/to/openapi.yaml -o ./output
    python -m mcp_adapter inspect  --spec path/to/openapi.yaml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from .agentic_codegen import generate as agentic_generate
from .codegen import generate as template_generate
from .deploy import deploy as deploy_to_github
from .ingest import ingest
from .logger import setup_logging, get_logger
from .mine import mine_tools
from .models import SafetyLevel
from .reasoning import enhance_tools_with_k2
from .safety import SafetyPolicy, apply_safety


@click.group()
@click.version_option(version="0.2.0", prog_name="anvil")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose logging.")
def cli(verbose: bool):
    """Anvil — forge safe MCP servers from any API spec."""
    setup_logging(verbose=verbose)


# ── generate ────────────────────────────────────────────────────────────────


@cli.command("generate")
@click.option(
    "--spec",
    default=None,
    type=click.Path(exists=True),
    help="Path to API spec file (OpenAPI YAML/JSON or Postman collection).",
)
@click.option(
    "--url",
    default=None,
    help="URL to fetch OpenAPI/Swagger spec from (e.g. http://host/openapi.json).",
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(),
    help="Output directory for generated MCP server.",
)
@click.option(
    "--name",
    default=None,
    help="Server name (defaults to API title).",
)
@click.option(
    "--use-k2",
    is_flag=True,
    default=False,
    help="Use AI to enhance tool names, descriptions, and schemas.",
)
@click.option(
    "--block-destructive",
    is_flag=True,
    default=False,
    help="Block all destructive (DELETE) tools.",
)
@click.option(
    "--max-tools",
    default=0,
    type=int,
    help="Max number of tools to generate (0 = no limit).",
)
@click.option(
    "--allowlist",
    default=None,
    help="Comma-separated list of tool names to include (others excluded).",
)
@click.option(
    "--denylist",
    default=None,
    help="Comma-separated list of tool names to exclude.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    default=False,
    help="Use template-based codegen (no LLM API key needed).",
)
@click.option(
    "--deploy",
    is_flag=True,
    default=False,
    help="Auto-deploy: push to GitHub + open Dedalus dashboard.",
)
@click.option(
    "--github-org",
    default=None,
    help="GitHub org to create the repo under (default: personal account).",
)
def generate_cmd(
    spec: str | None,
    url: str | None,
    output: str,
    name: str | None,
    use_k2: bool,
    block_destructive: bool,
    max_tools: int,
    allowlist: str | None,
    denylist: str | None,
    no_llm: bool,
    deploy: bool,
    github_org: str | None,
):
    """Generate an MCP server from an API specification."""
    logger = get_logger()

    if not spec and not url:
        click.echo("Error: Provide either --spec (file) or --url (Swagger URL).", err=True)
        sys.exit(1)

    # Validate required API key before starting the pipeline (skip if --no-llm)
    import os
    has_key = (os.getenv("ANTHROPIC_API_KEY")
               or os.getenv("LLM_API_KEY")
               or os.getenv("FEATHERLESS_API_KEY"))
    if not no_llm and not has_key:
        click.echo(
            "Error: No LLM API key found.\n"
            "Set one of these in your .env file:\n\n"
            "  ANTHROPIC_API_KEY=your-key   (Claude — recommended, cheap)\n"
            "  LLM_API_KEY=your-key         (any OpenAI-compatible provider)\n"
            "  FEATHERLESS_API_KEY=your-key  (Featherless)\n\n"
            "  Or use --no-llm for template-based generation (no key needed).",
            err=True,
        )
        sys.exit(1)

    source = url if url else spec

    logger.info("=" * 60)
    logger.info("ANVIL FORGE — WORKFLOW START")
    logger.info("=" * 60)
    logger.info("Source: %s", source)
    logger.info("Output: %s", output)
    logger.info("K2 reasoning: %s", "enabled" if use_k2 else "disabled")
    logger.info("Code generation: %s", "template (no LLM)" if no_llm else "LLM-powered")
    if deploy:
        logger.info("Deploy: GitHub + Dedalus (auto)")
    logger.info("")

    # ── Stage 1: Ingestion ────────────────────────────────────────────
    api_spec = ingest(source)
    logger.info(
        "Spec: %s v%s — %d endpoints, %d tags, %d auth schemes",
        api_spec.title, api_spec.version,
        len(api_spec.endpoints), len(api_spec.tags),
        len(api_spec.auth_schemes),
    )

    # ── Stage 2: Capability Mining ────────────────────────────────────
    tools = mine_tools(api_spec)

    # ── Stage 3: K2 Reasoning (optional) ──────────────────────────────
    if use_k2:
        tools = enhance_tools_with_k2(api_spec, tools)

    # ── Stage 4: Safety Classification ────────────────────────────────
    policy = SafetyPolicy(
        block_destructive=block_destructive,
        max_tools=max_tools,
        allowlist=allowlist.split(",") if allowlist else [],
        denylist=denylist.split(",") if denylist else [],
    )
    tools = apply_safety(tools, policy)

    # ── Stage 5: Code Generation ────────────────────────────────────────
    if no_llm:
        result = template_generate(api_spec, tools, server_name=name, output_dir=output)
    else:
        result = agentic_generate(api_spec, tools, server_name=name, output_dir=output)

    # ── Stage 6: Deploy (optional) ─────────────────────────────────────
    deploy_info = None
    if deploy:
        try:
            repo_name = result.server_name
            deploy_info = deploy_to_github(
                output_dir=output,
                repo_name=repo_name,
                description=f"Auto-generated MCP server for {api_spec.title}",
                org=github_org,
            )
        except Exception as e:
            logger.error("Deploy failed: %s", e)
            click.echo(f"\n⚠️  Deploy failed: {e}", err=True)

    # ── Summary ───────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("WORKFLOW COMPLETE")
    logger.info("=" * 60)
    logger.info("Server: %s (%d tools)", result.server_name, result.tool_count)
    logger.info("Output: %s", result.output_dir)
    if deploy_info:
        logger.info("GitHub: %s", deploy_info["repo_url"])
    logger.info("")

    if deploy_info:
        click.echo(f"\n✅ Done! Pushed to GitHub and opened Dedalus dashboard.")
        click.echo(f"")
        click.echo(f"   GitHub:    {deploy_info['repo_url']}")
        click.echo(f"   Dashboard: {deploy_info['dashboard_url']}")
        click.echo(f"")
        click.echo(f"   In the Dedalus dashboard:")
        click.echo(f"   1. Click 'Add Server' → connect repo '{deploy_info['repo_full_name']}'")
        click.echo(f"   2. Set environment variables:")
        click.echo(f"")
        env_vars = deploy_info.get("env_vars", {})
        required_vars = {k: v for k, v in env_vars.items() if v.get("required")}
        optional_vars = {k: v for k, v in env_vars.items() if not v.get("required")}
        if required_vars:
            click.echo(f"      Required:")
            for key, info in required_vars.items():
                val = info.get("value") or "<set-your-value>"
                desc = info.get("description", "")
                click.echo(f"        {key} = {val}")
                if desc:
                    click.echo(f"          └─ {desc}")
        if optional_vars:
            click.echo(f"      Optional:")
            for key, info in optional_vars.items():
                val = info.get("value") or ""
                desc = info.get("description", "")
                click.echo(f"        {key} = {val}")
                if desc:
                    click.echo(f"          └─ {desc}")
        click.echo(f"")
        click.echo(f"   3. Click 'Deploy'")
        click.echo(f"")
        click.echo(f"   After deploy, use in any AI agent:")
        click.echo(f"      mcp_servers=[\"{deploy_info['repo_full_name']}\"]")
    else:
        click.echo(f"\n✅ Done! To run your server:")
        click.echo(f"   cd {output}")
        click.echo(f"   pip install -r requirements.txt")
        click.echo(f"   cp .env.example .env  # fill in your API key")
        click.echo(f"   python server.py")


# ── inspect ─────────────────────────────────────────────────────────────────


@cli.command("inspect")
@click.option(
    "--spec",
    default=None,
    type=click.Path(exists=True),
    help="Path to API spec file.",
)
@click.option(
    "--url",
    default=None,
    help="URL to fetch OpenAPI/Swagger spec from.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output as JSON instead of human-readable.",
)
def inspect_cmd(spec: str | None, url: str | None, json_output: bool):
    """Inspect an API spec and show what tools would be generated."""
    if not spec and not url:
        click.echo("Error: Provide either --spec (file) or --url (Swagger URL).", err=True)
        sys.exit(1)

    source = url if url else spec
    api_spec = ingest(source)
    tools = mine_tools(api_spec)
    tools = apply_safety(tools)

    if json_output:
        data = {
            "api": {
                "title": api_spec.title,
                "version": api_spec.version,
                "base_url": api_spec.base_url,
                "endpoints": len(api_spec.endpoints),
                "tags": api_spec.tags,
            },
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "safety": t.safety.value,
                    "params": [
                        {
                            "name": p.name,
                            "type": p.json_type,
                            "required": p.required,
                        }
                        for p in t.params
                    ],
                }
                for t in tools
            ],
        }
        click.echo(json.dumps(data, indent=2))
        return

    click.echo(f"API: {api_spec.title} v{api_spec.version}")
    click.echo(f"Base URL: {api_spec.base_url}")
    click.echo(f"Endpoints: {len(api_spec.endpoints)}")
    click.echo(f"Tags: {', '.join(api_spec.tags) or 'none'}")
    click.echo(f"Auth: {', '.join(s.name for s in api_spec.auth_schemes) or 'none'}")
    click.echo("")
    click.echo(f"Tools ({len(tools)}):")
    click.echo("-" * 72)

    for t in tools:
        safety_icon = {"read": "🟢", "write": "🟡", "destructive": "🔴"}[
            t.safety.value
        ]
        params_str = ", ".join(
            f"{p.name}: {p.json_type}{'*' if p.required else '?'}"
            for p in t.params
        )
        click.echo(f"  {safety_icon} {t.name}({params_str})")
        click.echo(f"     {t.description}")


# ── Entry point ─────────────────────────────────────────────────────────────


def main():
    cli()


if __name__ == "__main__":
    main()
