"""SDK/Client Library ingestion pipeline.

Parse SDK source code to extract callable methods as tool definitions.

Usage:
    # From GitHub (fetches key files)
    python sdk_ingest.py --github https://github.com/stripe/stripe-python
    
    # From local file
    python sdk_ingest.py --file client.py
    
    # From local directory
    python sdk_ingest.py --dir ./my-sdk --lang python
    
    # Specify output
    python sdk_ingest.py --github https://github.com/encode/httpx --output httpx_tools.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from .logger import get_logger

load_dotenv()

logger = get_logger()


# ── Language Detection ────────────────────────────────────────────────────────

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript",
    ".js": "javascript",
    ".d.ts": "typescript",
    ".java": "java",
}

# Files to skip when parsing SDKs
SKIP_PATTERNS = [
    r"test[s]?/",
    r"__pycache__",
    r"\.git/",
    r"setup\.py$",
    r"conftest\.py$",
    r"_test\.py$",
    r"test_.*\.py$",
    r"\.spec\.ts$",
    r"\.test\.ts$",
]

# Priority files to include (checked first)
PRIORITY_PATTERNS = [
    r"client\.py$",
    r"api\.py$",
    r"resources/.*\.py$",
    r"src/.*\.ts$",
    r"lib/.*\.ts$",
]


def detect_language(filename: str) -> str | None:
    """Detect language from file extension."""
    for ext, lang in LANGUAGE_EXTENSIONS.items():
        if filename.endswith(ext):
            return lang
    return None


def should_skip_file(filepath: str) -> bool:
    """Check if file should be skipped."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, filepath):
            return True
    return False


def is_priority_file(filepath: str) -> bool:
    """Check if file is a priority file."""
    for pattern in PRIORITY_PATTERNS:
        if re.search(pattern, filepath):
            return True
    return False


# ── GitHub Fetching ───────────────────────────────────────────────────────────


def parse_github_url(url: str) -> tuple[str, str, str]:
    """Parse GitHub URL to extract owner, repo, and branch.
    
    Returns: (owner, repo, branch)
    """
    # Handle various GitHub URL formats
    # https://github.com/owner/repo
    # https://github.com/owner/repo/tree/branch
    url = url.rstrip("/")
    
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {url}")
    
    owner = parts[0]
    repo = parts[1]
    branch = "main"  # Default
    
    if len(parts) >= 4 and parts[2] == "tree":
        branch = parts[3]
    
    return owner, repo, branch


def fetch_github_tree(owner: str, repo: str, branch: str) -> list[dict]:
    """Fetch repository file tree from GitHub API."""
    logger.info("Fetching file tree for %s/%s@%s", owner, repo, branch)
    
    api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(api_url, headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code == 404:
            # Try 'master' branch if 'main' fails
            if branch == "main":
                return fetch_github_tree(owner, repo, "master")
            raise ValueError(f"Repository not found: {owner}/{repo}")
        resp.raise_for_status()
    
    data = resp.json()
    return data.get("tree", [])


def fetch_github_file(owner: str, repo: str, branch: str, filepath: str) -> str:
    """Fetch raw file content from GitHub."""
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filepath}"
    
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(raw_url)
        resp.raise_for_status()
    
    return resp.text


def select_sdk_files(tree: list[dict], language: str | None = None, max_files: int = 10) -> list[str]:
    """Select relevant SDK files from repository tree.
    
    Prioritizes main SDK files, skips tests and configs.
    """
    candidates = []
    
    for item in tree:
        if item.get("type") != "blob":
            continue
        
        filepath = item.get("path", "")
        file_lang = detect_language(filepath)
        
        if file_lang is None:
            continue
        
        if language and file_lang != language:
            continue
        
        if should_skip_file(filepath):
            continue
        
        # Score files by priority
        priority = 1 if is_priority_file(filepath) else 0
        candidates.append((priority, filepath, file_lang))
    
    # Sort by priority (highest first), then by path
    candidates.sort(key=lambda x: (-x[0], x[1]))
    
    # Return top files
    selected = []
    for _, filepath, _ in candidates[:max_files]:
        selected.append(filepath)
    
    logger.info("Selected %d files for parsing", len(selected))
    for f in selected:
        logger.info("  - %s", f)
    
    return selected


# ── Gemini Parsing ────────────────────────────────────────────────────────────


def parse_sdk_with_gemini(
    source: str,
    code_content: str,
    language: str,
    max_retries: int = 3
) -> dict[str, Any]:
    """Parse SDK code with Gemini API to extract tool definitions."""
    from google import genai
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable required")
    
    client = genai.Client(api_key=api_key)
    
    # SDK-specific prompt
    prompt = f"""You are an expert SDK code analyzer. Analyze the following {language.upper()} SDK source code and extract all PUBLIC callable functions/methods that users of this library would call.

## Instructions

1. **Identify public functions/methods** - Skip private/internal ones (prefixed with _ in Python)
2. **Extract complete signatures** including all parameters with types
3. **Get descriptions** from docstrings, JSDoc, or Javadoc comments
4. **Infer parameter types** from type hints or documentation
5. **Note default values** where specified

## Output Format

Return ONLY valid JSON:

```json
{{
  "api_info": {{
    "title": "SDK or module name",
    "version": "",
    "description": "What this SDK/module does",
    "base_url": ""
  }},
  "tools": [
    {{
      "name": "module.class.method_name",
      "description": "What this function does",
      "method": "FUNCTION",
      "path": "full.import.path",
      "params": [
        {{
          "name": "param_name",
          "type": "string|int|bool|list|dict|object",
          "required": true,
          "location": "argument",
          "description": "Parameter description",
          "default": null
        }}
      ],
      "returns": "Return type description"
    }}
  ]
}}
```

## {language.upper()} Source Code

File: {source}

```{language}
{code_content[:40000]}
```

## Important

- Return ONLY the JSON, no markdown code blocks
- Include ONLY public/exported functions that users would call
- Skip internal/private methods
- Use the full qualified name for method paths (e.g., stripe.Customer.create)"""

    # Retry with exponential backoff
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            
            response_text = response.text.strip()
            
            # Clean up response - remove markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                end_idx = len(lines) - 1
                for i in range(len(lines) - 1, 0, -1):
                    if lines[i].strip() == "```":
                        end_idx = i
                        break
                response_text = "\n".join(lines[1:end_idx])
            
            # Extract JSON if there's extra text
            if not response_text.startswith("{"):
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start != -1 and end > start:
                    response_text = response_text[start:end]
            
            result = json.loads(response_text)
            
            return {
                "api_info": result.get("api_info", {}),
                "tools": result.get("tools", []),
            }
            
        except json.JSONDecodeError as e:
            logger.error("JSON parse failed (attempt %d): %s", attempt + 1, e)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise ValueError(f"Gemini returned invalid JSON: {e}")
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 2)
                    logger.warning("Rate limited, waiting %ds...", wait_time)
                    time.sleep(wait_time)
                else:
                    raise
            else:
                raise
    
    raise ValueError("Failed to parse with Gemini")


def merge_results(results: list[dict], source: str) -> dict[str, Any]:
    """Merge multiple file parsing results into one."""
    all_tools = []
    api_info = {"title": "", "version": "", "description": "", "base_url": ""}
    
    for result in results:
        all_tools.extend(result.get("tools", []))
        # Use first non-empty api_info
        if not api_info["title"] and result.get("api_info", {}).get("title"):
            api_info = result["api_info"]
    
    return {
        "source": source,
        "parser": "gemini",
        "api_info": api_info,
        "tools": all_tools,
    }


# ── Main Ingestion ────────────────────────────────────────────────────────────


def ingest_github(url: str, language: str | None = None, max_files: int = 10) -> dict[str, Any]:
    """Ingest SDK from GitHub repository."""
    owner, repo, branch = parse_github_url(url)
    
    # Fetch file tree
    tree = fetch_github_tree(owner, repo, branch)
    
    # Select relevant files
    files = select_sdk_files(tree, language, max_files)
    
    if not files:
        raise ValueError(f"No SDK files found in {url}")
    
    # Parse each file
    results = []
    for filepath in files:
        logger.info("Parsing: %s", filepath)
        
        try:
            content = fetch_github_file(owner, repo, branch, filepath)
            lang = detect_language(filepath) or "python"
            
            result = parse_sdk_with_gemini(filepath, content, lang)
            results.append(result)
            
            logger.info("  → Found %d tools", len(result.get('tools', [])))
            
            # Small delay between API calls
            time.sleep(1)
            
        except Exception as e:
            logger.warning("Failed to parse %s: %s", filepath, e)
    
    return merge_results(results, url)


def ingest_file(filepath: str) -> dict[str, Any]:
    """Ingest SDK from local file."""
    path = Path(filepath)
    
    if not path.exists():
        raise ValueError(f"File not found: {filepath}")
    
    content = path.read_text(encoding="utf-8")
    language = detect_language(str(path)) or "python"
    
    logger.info("Parsing local file: %s (%s)", filepath, language)
    
    result = parse_sdk_with_gemini(str(path), content, language)
    
    return {
        "source": str(path.absolute()),
        "parser": "gemini",
        "api_info": result.get("api_info", {}),
        "tools": result.get("tools", []),
    }


def ingest_directory(dirpath: str, language: str | None = None, max_files: int = 10) -> dict[str, Any]:
    """Ingest SDK from local directory."""
    path = Path(dirpath)
    
    if not path.is_dir():
        raise ValueError(f"Directory not found: {dirpath}")
    
    # Find relevant files
    files = []
    for ext in LANGUAGE_EXTENSIONS:
        for filepath in path.rglob(f"*{ext}"):
            rel_path = str(filepath.relative_to(path))
            if not should_skip_file(rel_path):
                file_lang = detect_language(str(filepath))
                if language is None or file_lang == language:
                    priority = 1 if is_priority_file(rel_path) else 0
                    files.append((priority, filepath))
    
    # Sort by priority
    files.sort(key=lambda x: -x[0])
    files = [f[1] for f in files[:max_files]]
    
    logger.info("Selected %d files from %s", len(files), dirpath)
    
    # Parse each file
    results = []
    for filepath in files:
        logger.info("Parsing: %s", filepath)
        
        try:
            content = filepath.read_text(encoding="utf-8")
            lang = detect_language(str(filepath)) or "python"
            
            result = parse_sdk_with_gemini(str(filepath), content, lang)
            results.append(result)
            
            logger.info("  → Found %d tools", len(result.get('tools', [])))
            time.sleep(1)
            
        except Exception as e:
            logger.warning("Failed to parse %s: %s", filepath, e)
    
    return merge_results(results, str(path.absolute()))


def ingest(
    source: str,
    source_type: str,
    language: str | None = None,
    max_files: int = 10,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Main ingestion function."""
    # Parse based on source type
    if source_type == "github":
        result = ingest_github(source, language, max_files)
    elif source_type == "file":
        result = ingest_file(source)
    elif source_type == "dir":
        result = ingest_directory(source, language, max_files)
    else:
        raise ValueError(f"Unknown source type: {source_type}")
    
    # Write output if path given
    if output_path:
        logger.info("Writing output to: %s", output_path)
        Path(output_path).write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    logger.info("SDK Ingestion complete — SDK: %s, Tools: %d",
                result['api_info'].get('title', 'Unknown'), len(result['tools']))
    
    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse SDK source code into tool definitions"
    )
    
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--github",
        help="GitHub repository URL",
    )
    source_group.add_argument(
        "--file",
        help="Local file path",
    )
    source_group.add_argument(
        "--dir",
        help="Local directory path",
    )
    
    parser.add_argument(
        "--lang",
        choices=["python", "typescript", "javascript", "java"],
        help="Filter by language (optional)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=10,
        help="Maximum number of files to parse (default: 10)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path",
    )
    
    args = parser.parse_args()
    
    # Determine source and type
    if args.github:
        source, source_type = args.github, "github"
    elif args.file:
        source, source_type = args.file, "file"
    else:
        source, source_type = args.dir, "dir"
    
    try:
        ingest(
            source=source,
            source_type=source_type,
            language=args.lang,
            max_files=args.max_files,
            output_path=args.output,
        )
    except Exception as e:
        print(f"[ERROR] SDK ingestion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
