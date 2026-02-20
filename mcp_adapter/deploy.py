"""Automated deployment: GitHub repo creation + push + Dedalus dashboard link.

Flow:
  1. Create a GitHub repo via REST API (or reuse existing)
  2. git init → add → commit → push the generated MCP server
  3. Open the Dedalus dashboard for the user to connect the repo

Requires:
  - GITHUB_TOKEN env var (personal access token with 'repo' scope)
  - git available on PATH
"""

from __future__ import annotations

import json
import os
import subprocess
import webbrowser
from pathlib import Path

import httpx

from .logger import get_logger

GITHUB_API = "https://api.github.com"
DEDALUS_DASHBOARD = "https://www.dedaluslabs.ai/dashboard/servers"


def _get_github_token() -> str:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is not set. "
            "Create a personal access token at https://github.com/settings/tokens "
            "with 'repo' scope and add it to your .env file."
        )
    return token


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_github_username(token: str) -> str:
    """Get the authenticated user's GitHub username."""
    resp = httpx.get(f"{GITHUB_API}/user", headers=_github_headers(token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()["login"]


def create_github_repo(
    name: str,
    *,
    description: str = "",
    token: str,
    org: str | None = None,
    private: bool = False,
) -> dict:
    """Create a GitHub repo. Returns the API response JSON.

    If the repo already exists, returns its info instead of failing.
    """
    logger = get_logger()

    payload = {
        "name": name,
        "description": description,
        "private": private,
        "auto_init": False,
    }

    if org:
        url = f"{GITHUB_API}/orgs/{org}/repos"
    else:
        url = f"{GITHUB_API}/user/repos"

    resp = httpx.post(
        url,
        headers=_github_headers(token),
        json=payload,
        timeout=15.0,
    )

    if resp.status_code == 422:
        # Repo likely already exists — fetch it instead
        owner = org or _get_github_username(token)
        logger.info("  Repo %s/%s already exists — reusing", owner, name)
        resp2 = httpx.get(
            f"{GITHUB_API}/repos/{owner}/{name}",
            headers=_github_headers(token),
            timeout=15.0,
        )
        resp2.raise_for_status()
        return resp2.json()

    resp.raise_for_status()
    logger.info("  Created GitHub repo: %s", resp.json()["full_name"])
    return resp.json()


def _run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def push_to_github(output_dir: str | Path, repo_url: str, *, branch: str = "main", force: bool = False) -> None:
    """Initialize a git repo in output_dir and push to GitHub."""
    logger = get_logger()
    cwd = str(output_dir)

    # Init if not already a git repo
    git_dir = Path(cwd) / ".git"
    if not git_dir.exists():
        _run_git(["init", "-b", branch], cwd)
        logger.info("  Initialized git repo")

    # Configure git user if not set (needed for commits)
    try:
        _run_git(["config", "user.email"], cwd)
    except RuntimeError:
        _run_git(["config", "user.email", "anvil@forge.local"], cwd)
        _run_git(["config", "user.name", "Anvil Forge"], cwd)

    # Add .gitignore
    gitignore = Path(cwd) / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            ".env\n__pycache__/\n*.pyc\n.venv/\n",
            encoding="utf-8",
        )

    # Stage and commit
    _run_git(["add", "-A"], cwd)

    # Check if there are changes to commit
    status = _run_git(["status", "--porcelain"], cwd)
    if status:
        _run_git(["commit", "-m", "Auto-generated MCP server"], cwd)
        logger.info("  Committed changes")
    else:
        logger.info("  No changes to commit")

    # Set remote (replace if exists)
    try:
        _run_git(["remote", "remove", "origin"], cwd)
    except RuntimeError:
        pass
    _run_git(["remote", "add", "origin", repo_url], cwd)

    # Push
    push_args = ["push", "-u", "origin", branch]
    if force:
        push_args.append("--force")
    _run_git(push_args, cwd)
    logger.info("  Pushed to %s", repo_url)


def open_dedalus_dashboard() -> None:
    """Open the Dedalus dashboard in the user's browser."""
    logger = get_logger()
    logger.info("  Opening Dedalus dashboard: %s", DEDALUS_DASHBOARD)
    webbrowser.open(DEDALUS_DASHBOARD)


def _read_manifest(output_dir: str | Path) -> dict:
    """Read dedalus.json manifest from the output directory."""
    manifest_path = Path(output_dir) / "dedalus.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {}


def deploy(
    output_dir: str | Path,
    repo_name: str,
    *,
    description: str = "",
    org: str | None = None,
    private: bool = False,
    open_dashboard: bool = True,
) -> dict:
    """Full deployment: create GitHub repo → push → open Dedalus dashboard.

    Returns a dict with deployment info including env vars from manifest.
    """
    logger = get_logger()
    token = _get_github_token()

    # Read deployment manifest for env vars
    manifest = _read_manifest(output_dir)
    env_vars = manifest.get("env_vars", {})

    # Step 1: Create GitHub repo
    logger.info("Creating GitHub repo: %s", repo_name)
    repo_info = create_github_repo(
        repo_name,
        description=description,
        token=token,
        org=org,
        private=private,
    )
    repo_url = repo_info["clone_url"]
    repo_full_name = repo_info["full_name"]
    html_url = repo_info["html_url"]

    # Step 2: Push code
    logger.info("Pushing generated code to GitHub...")
    push_to_github(output_dir, repo_url)

    # Step 3: Open Dedalus dashboard
    if open_dashboard:
        logger.info("Opening Dedalus dashboard for deployment...")
        open_dedalus_dashboard()

    return {
        "repo_full_name": repo_full_name,
        "repo_url": html_url,
        "clone_url": repo_url,
        "dashboard_url": DEDALUS_DASHBOARD,
        "env_vars": env_vars,
        "server_name": manifest.get("server_name", repo_name),
        "base_url": manifest.get("base_url", ""),
    }
